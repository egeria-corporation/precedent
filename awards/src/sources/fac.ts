/**
 * Federal Audit Clearinghouse: who actually handed the money over.
 *
 * A port of `precedent/sources/fac.py`. USAspending records the award the government made
 * and nothing about what happened next; when a state agency re-grants a formula grant to
 * forty community organizations, USAspending shows one award to the state. Single audits
 * record the forty, because a subrecipient's own auditor has to name who passed the money.
 *
 * Four things here exist because getting them wrong is the documented failure mode, and two
 * of them were found by running the Python original against the live API rather than by
 * reading the data dictionary:
 *
 * - **There is no Assistance Listing column.** It is `federal_agency_prefix` and
 *   `federal_award_extension`, filtered separately and joined with a dot for display.
 * - **PostgREST guarantees no order**, so a limit/offset loop without an explicit `order`
 *   skips and duplicates rows silently. Every paginated call sends one.
 * - **The boolean columns are not booleans.** The dictionary types `is_direct` and
 *   `is_passthrough_award` as boolean; the API returns the strings `"Y"` and `"N"`, both
 *   truthy in JavaScript. Reading one straight marks every row direct.
 * - **So the filters are `eq.N` and `eq.Y`, not `is.false` and `is.true`.** Those columns
 *   are text in FAC's schema and PostgREST rejects an IS predicate against text outright,
 *   with HTTP 400: "argument of IS FALSE must be type boolean, not type text".
 */

import { cachedFetch, canonicalRequest } from "../cache";
import { politeFetch } from "../fetcher";
import type { Env } from "../types";

const SOURCE = "fac" as const;
const ROOT = "https://api.fac.gov";
const GENERAL_URL = `${ROOT}/general`;
const FEDERAL_AWARDS_URL = `${ROOT}/federal_awards`;
const PASSTHROUGH_URL = `${ROOT}/passthrough`;

/** FAC caps a response at 20,000 rows and asks partners for small restrictive queries. */
const PAGE_LIMIT = 5000;

/** One key per person, rate limited per key. A loop that fails to terminate spends
 *  somebody's quota rather than ours. */
const MAX_PAGES = 6;

/** `in.(...)` grows the URL, and a long one is rejected before it reaches PostgREST. */
const IN_CHUNK = 100;

/** Audit years 2016 forward. Earlier single audits are in the legacy Census extracts. */
export const COVERAGE_START_YEAR = 2016;

/** What the text "boolean" columns actually hold, and so what a filter compares against. */
export const TRUE_VALUE = "Y";
export const FALSE_VALUE = "N";

/**
 * `auditee_uei` holds this literal string on records carried over from the legacy Census
 * collection. Kept as a value it joins tens of thousands of unrelated organizations.
 */
export const UEI_PLACEHOLDER = "GSA_MIGRATION";

const GENERAL_FIELDS = [
  "report_id",
  "audit_year",
  "auditee_name",
  "auditee_ein",
  "auditee_uei",
  "auditee_city",
  "auditee_state",
  "entity_type",
  "total_amount_expended",
  "fac_accepted_date",
];

const AWARD_FIELDS = [
  "report_id",
  "award_reference",
  "federal_agency_prefix",
  "federal_award_extension",
  "federal_program_name",
  "amount_expended",
  "is_direct",
  "is_passthrough_award",
  "passthrough_amount",
  "cluster_name",
  "audit_year",
];

const PASSTHROUGH_FIELDS = [
  "report_id",
  "award_reference",
  "passthrough_name",
  "passthrough_id",
  "audit_year",
];

export class FacKeyMissing extends Error {}
export class FacTooMuchData extends Error {}
export class FacUpstreamError extends Error {}

export interface Audit {
  reportId: string;
  auditYear: string | null;
  auditeeName: string | null;
  auditeeEin: string | null;
  auditeeUei: string | null;
  auditeeCity: string | null;
  auditeeState: string | null;
  entityType: string | null;
  totalAmountExpended: number | null;
  facAcceptedDate: string | null;
}

export interface SefaAward {
  reportId: string;
  awardReference: string | null;
  federalAgencyPrefix: string | null;
  federalAwardExtension: string | null;
  federalProgramName: string | null;
  amountExpended: number | null;
  isDirect: boolean | null;
  isPassthroughAward: boolean | null;
  passthroughAmount: number | null;
  clusterName: string | null;
  auditYear: string | null;
}

export interface PassThrough {
  reportId: string;
  awardReference: string | null;
  name: string | null;
  identifier: string | null;
  auditYear: string | null;
}

/** `"93"` and `"045"` become `"93.045"`. FAC publishes no single column for this. */
export function assistanceListing(prefix: string | null, extension: string | null): string | null {
  if (!prefix || !extension) return null;
  return `${prefix.trim()}.${extension.trim()}`;
}

/** `"93.045"` becomes `["93", "045"]`, the two columns FAC actually filters on. */
export function splitListing(listing: string): [string, string] | null {
  const text = listing.trim();
  const match = /^(\d{2})\.(\d{3}[A-Za-z]?)$/.exec(text);
  return match ? [match[1] as string, match[2] as string] : null;
}

/** The join key between a SEFA line and the row naming who passed the money. */
export function awardKey(reportId: string, awardReference: string | null): string {
  // JSON rather than a separator character: any delimiter could occur inside a report
  // id or an award reference, and a collision here silently joins two different SEFA
  // lines to one pass-through entity.
  return JSON.stringify([reportId, awardReference ?? ""]);
}

export function chunked<T>(values: T[], size = IN_CHUNK): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < values.length; i += size) out.push(values.slice(i, i + size));
  return out;
}

/** PostgREST `in.(a,b,c)`, quoted so a comma inside a value cannot split it. */
export function inFilter(values: string[]): string {
  return `in.(${values.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(",")})`;
}

function text(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  const s = String(value).trim();
  return s || null;
}

function uei(value: unknown): string | null {
  const s = text(value);
  return !s || s === UEI_PLACEHOLDER ? null : s;
}

function int(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? Math.trunc(n) : null;
}

/** "Y" and "N" are what this API sends where its dictionary promises a boolean. */
function bool(value: unknown): boolean | null {
  if (typeof value === "boolean") return value;
  const s = text(value)?.toLowerCase();
  if (!s) return null;
  if (["y", "yes", "true", "t", "1"].includes(s)) return true;
  if (["n", "no", "false", "f", "0"].includes(s)) return false;
  return null;
}

export function toAudit(row: Record<string, unknown>): Audit {
  return {
    reportId: String(row.report_id ?? ""),
    auditYear: text(row.audit_year),
    auditeeName: text(row.auditee_name),
    auditeeEin: text(row.auditee_ein),
    auditeeUei: uei(row.auditee_uei),
    auditeeCity: text(row.auditee_city),
    auditeeState: text(row.auditee_state),
    entityType: text(row.entity_type),
    totalAmountExpended: int(row.total_amount_expended),
    facAcceptedDate: text(row.fac_accepted_date),
  };
}

export function toSefaAward(row: Record<string, unknown>): SefaAward {
  return {
    reportId: String(row.report_id ?? ""),
    awardReference: text(row.award_reference),
    federalAgencyPrefix: text(row.federal_agency_prefix),
    federalAwardExtension: text(row.federal_award_extension),
    federalProgramName: text(row.federal_program_name),
    amountExpended: int(row.amount_expended),
    isDirect: bool(row.is_direct),
    isPassthroughAward: bool(row.is_passthrough_award),
    passthroughAmount: int(row.passthrough_amount),
    clusterName: text(row.cluster_name),
    auditYear: text(row.audit_year),
  };
}

export function toPassThrough(row: Record<string, unknown>): PassThrough {
  return {
    reportId: String(row.report_id ?? ""),
    awardReference: text(row.award_reference),
    name: text(row.passthrough_name),
    identifier: text(row.passthrough_id),
    auditYear: text(row.audit_year),
  };
}

/** This auditee received the money through somebody, named in the passthrough rows. */
export function receivedThroughSomeone(award: SefaAward): boolean {
  return award.isDirect === false;
}

/** This auditee handed money to its own subrecipients. */
export function passedMoneyDown(award: SefaAward): boolean {
  return award.isPassthroughAward === true && (award.passthroughAmount ?? 0) > 0;
}

async function page(
  env: Env,
  vintage: string,
  url: string,
  params: Record<string, string>,
  apiKey: string,
): Promise<{ rows: Record<string, unknown>[]; fetchedAt: string }> {
  const query = new URLSearchParams(params).toString();
  const full = `${url}?${query}`;
  const canonical = canonicalRequest("GET", full, null);
  const cached = await cachedFetch<Record<string, unknown>[]>(
    env,
    SOURCE,
    canonical,
    vintage,
    async () => {
      const response = await politeFetch({
        source: SOURCE,
        url: full,
        headers: { "X-Api-Key": apiKey },
      });
      return (await response.json()) as Record<string, unknown>[];
    },
  );
  return { rows: Array.isArray(cached.body) ? cached.body : [], fetchedAt: cached.fetchedAt };
}

/**
 * Every row matching `params`, paginated, ordered, and bounded.
 *
 * `order` is not optional and not a nicety: PostgREST returns rows in whatever order the
 * planner produced, so limit/offset over an unordered result skips some and repeats others
 * with no error to notice.
 */
async function collect(
  env: Env,
  vintage: string,
  url: string,
  base: Record<string, string>,
  select: string[],
  order: string,
  apiKey: string,
): Promise<{ rows: Record<string, unknown>[]; fetchedAt: string | null }> {
  const rows: Record<string, unknown>[] = [];
  const dates: string[] = [];
  for (let i = 0; i < MAX_PAGES; i++) {
    const { rows: batch, fetchedAt } = await page(
      env,
      vintage,
      url,
      {
        ...base,
        select: select.join(","),
        order,
        limit: String(PAGE_LIMIT),
        offset: String(i * PAGE_LIMIT),
      },
      apiKey,
    );
    dates.push(fetchedAt);
    rows.push(...batch);
    if (batch.length < PAGE_LIMIT) {
      return { rows, fetchedAt: dates.sort()[0] ?? null };
    }
  }
  throw new FacTooMuchData(
    [
      `This Federal Audit Clearinghouse query passed ${(MAX_PAGES * PAGE_LIMIT).toLocaleString()}`,
      "rows without finishing. Narrow it to a single Assistance Listing or a shorter range of",
      "audit years rather than widening the bound, which exists so a runaway loop cannot spend",
      "the API quota.",
    ].join(" "),
  );
}

function requireKey(env: Env): string {
  if (!env.FAC_API_KEY) {
    throw new FacKeyMissing(
      "Pass-through data needs a Federal Audit Clearinghouse API key, which this deployment " +
        "does not have configured.",
    );
  }
  return env.FAC_API_KEY;
}

function yearWindow(sinceYear: number, untilYear: number): Record<string, string> {
  const since = Math.max(sinceYear, COVERAGE_START_YEAR);
  return { and: `(audit_year.gte.${since},audit_year.lte.${untilYear})` };
}

export async function audits(
  env: Env,
  vintage: string,
  state: string,
  sinceYear: number,
  untilYear: number,
): Promise<{ audits: Audit[]; fetchedAt: string | null }> {
  const { rows, fetchedAt } = await collect(
    env,
    vintage,
    GENERAL_URL,
    { auditee_state: `eq.${state.toUpperCase()}`, ...yearWindow(sinceYear, untilYear) },
    GENERAL_FIELDS,
    "report_id.asc",
    requireKey(env),
  );
  return { audits: rows.map(toAudit), fetchedAt };
}

export interface AwardQuery {
  reportIds: string[];
  listing?: string | null;
  /** Exactly one direction per query: they are opposite ends of the same pipe. */
  direction: "received" | "passed";
}

export async function sefaAwards(
  env: Env,
  vintage: string,
  query: AwardQuery,
): Promise<{ awards: SefaAward[]; fetchedAt: string | null }> {
  const key = requireKey(env);
  const base: Record<string, string> = {};
  if (query.direction === "received") base.is_direct = `eq.${FALSE_VALUE}`;
  else {
    base.is_passthrough_award = `eq.${TRUE_VALUE}`;
    base.passthrough_amount = "gt.0";
  }
  if (query.listing) {
    const split = splitListing(query.listing);
    if (split) {
      base.federal_agency_prefix = `eq.${split[0]}`;
      base.federal_award_extension = `eq.${split[1]}`;
    }
  }
  return collectByIds(
    env,
    vintage,
    FEDERAL_AWARDS_URL,
    base,
    AWARD_FIELDS,
    query.reportIds,
    key,
  ).then(({ rows, fetchedAt }) => ({ awards: rows.map(toSefaAward), fetchedAt }));
}

export async function passthroughs(
  env: Env,
  vintage: string,
  reportIds: string[],
): Promise<{ rows: PassThrough[]; fetchedAt: string | null }> {
  const key = requireKey(env);
  const { rows, fetchedAt } = await collectByIds(
    env,
    vintage,
    PASSTHROUGH_URL,
    {},
    PASSTHROUGH_FIELDS,
    reportIds,
    key,
  );
  return { rows: rows.map(toPassThrough), fetchedAt };
}

/** One query per chunk of report ids, concatenated and deduplicated on the ordering key. */
async function collectByIds(
  env: Env,
  vintage: string,
  url: string,
  base: Record<string, string>,
  select: string[],
  reportIds: string[],
  apiKey: string,
): Promise<{ rows: Record<string, unknown>[]; fetchedAt: string | null }> {
  if (!reportIds.length) return { rows: [], fetchedAt: null };
  const out: Record<string, unknown>[] = [];
  const dates: string[] = [];
  const seen = new Set<string>();
  for (const batch of chunked(reportIds)) {
    const { rows, fetchedAt } = await collect(
      env,
      vintage,
      url,
      { ...base, report_id: inFilter(batch) },
      select,
      "report_id.asc,award_reference.asc",
      apiKey,
    );
    if (fetchedAt) dates.push(fetchedAt);
    for (const row of rows) {
      const signature = awardKey(String(row.report_id ?? ""), text(row.award_reference));
      if (seen.has(signature)) continue;
      seen.add(signature);
      out.push(row);
    }
  }
  return { rows: out, fetchedAt: dates.sort()[0] ?? null };
}
