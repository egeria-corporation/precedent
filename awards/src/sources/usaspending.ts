/**
 * USAspending: award history for one Assistance Listing. No key, no account.
 *
 * A port of `precedent/sources/usaspending.py`. It fetches and shapes and computes nothing,
 * so every number on this site can be checked against USAspending's own documentation
 * rather than against our arithmetic.
 *
 * Three things here exist because getting them wrong is the documented failure mode:
 *
 * - **Fetch on `action_date`, bucket on `Base Obligation Date`.** A window filtered by
 *   action date returns every award with *any* transaction in it, including awards first
 *   obligated years earlier. The window is deliberately wide and the bucketing happens in
 *   `analysis/profile.ts`.
 * - **Keyset pagination, not page numbers.** Page-based paging degrades badly past a few
 *   thousand records; feeding the cursor back stays fast to arbitrary depth.
 * - **Count before you pull.** A program larger than a record-by-record fetch can honestly
 *   serve gets a typed error naming a narrower query, not a request that never returns.
 */

import type { Award } from "../analysis/profile";
import { cachedFetch, canonicalRequest } from "../cache";
import { politeFetch } from "../fetcher";
import type { Env } from "../types";

const SOURCE = "usaspending" as const;
const ROOT = "https://api.usaspending.gov";
const SEARCH_URL = `${ROOT}/api/v2/search/spending_by_award/`;
const COUNT_URL = `${ROOT}/api/v2/search/spending_by_award_count/`;
const AUTOCOMPLETE_URL = `${ROOT}/api/v2/autocomplete/cfda/`;

/** 02 block grant, 03 formula grant, 04 project grant, 05 cooperative agreement. Contract
 *  codes must never join these in one request: the field vocabulary changes and the API 400s. */
export const GRANT_AWARD_TYPES = ["02", "03", "04", "05"];

const PAGE_LIMIT = 100;
export const MAX_RECORDS = 20_000;

/**
 * The pagination bound, in requests of 100 records.
 *
 * It exists to stop a runaway loop, not to cap a real program: truncating this pull does
 * not return less data, it returns *wrong* data. The upstream sorts by Award Amount
 * descending, so the records that fall off the end are the smallest awards, every
 * percentile shifts upward, and the median can be several times too high while the page
 * looks entirely normal. At 60 this silently reported a median of $1.95M for 93.243 against
 * a true $1.25M.
 *
 * So the bound is set above what any real program needs, `truncated` is returned when it is
 * hit anyway, and the caller refuses to render rather than publishing a biased number.
 *
 * The real ceiling is Cloudflare's subrequest budget per invocation: 50 on the free plan,
 * 1,000 on paid. A large program needs on the order of 80 sequential requests, so this only
 * fits on a paid plan - and on the free plan the guard turns that into an honest refusal
 * rather than a wrong answer.
 */
const MAX_PAGES = 120;

const FIELDS = [
  "Award ID",
  "Recipient Name",
  "Recipient UEI",
  "Recipient Location",
  "Award Amount",
  "Base Obligation Date",
  "Start Date",
  "End Date",
  "Awarding Agency",
  "Awarding Sub Agency",
  "Place of Performance State Code",
  "Assistance Listings",
  "recipient_id",
];

export class TooMuchData extends Error {}
export class UpstreamError extends Error {}

export interface ProgramRef {
  number: string;
  title: string | null;
  popularName: string | null;
}

function text(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  const s = String(value).trim();
  return s || null;
}

function listings(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const out: string[] = [];
  for (const item of value) {
    if (typeof item === "string") {
      const n = text(item);
      if (n) out.push(n);
    } else if (item && typeof item === "object") {
      const n = text((item as Record<string, unknown>).cfda_number);
      if (n) out.push(n);
    }
  }
  return out;
}

function stateOf(location: unknown): string | null {
  if (!location || typeof location !== "object") return null;
  return text((location as Record<string, unknown>).state_code);
}

export function toAward(row: Record<string, unknown>): Award {
  const amount = row["Award Amount"];
  return {
    generatedInternalId: String(row.generated_internal_id ?? row["Award ID"] ?? ""),
    awardId: text(row["Award ID"]),
    recipientName: text(row["Recipient Name"]),
    recipientUei: text(row["Recipient UEI"]),
    recipientId: text(row.recipient_id),
    amount: typeof amount === "number" ? amount : amount ? Number(amount) : null,
    baseObligationDate: text(row["Base Obligation Date"]),
    startDate: text(row["Start Date"]),
    awardingAgency: text(row["Awarding Agency"]),
    placeOfPerformanceState:
      text(row["Place of Performance State Code"]) ?? stateOf(row["Recipient Location"]),
    assistanceListings: listings(row["Assistance Listings"]),
  };
}

export function buildFilters(
  program: string,
  startDate: string,
  endDate: string,
  states?: string[],
): Record<string, unknown> {
  const filters: Record<string, unknown> = {
    award_type_codes: [...GRANT_AWARD_TYPES],
    program_numbers: [program],
    time_period: [{ start_date: startDate, end_date: endDate, date_type: "action_date" }],
  };
  if (states?.length) {
    filters.recipient_locations = states.map((s) => ({ country: "USA", state: s.toUpperCase() }));
  }
  return filters;
}

async function postJson(
  env: Env,
  vintage: string,
  url: string,
  payload: Record<string, unknown>,
): Promise<{ body: Record<string, unknown>; fetchedAt: string }> {
  const canonical = canonicalRequest("POST", url, payload);
  const cached = await cachedFetch<Record<string, unknown>>(
    env,
    SOURCE,
    canonical,
    vintage,
    async () => {
      const response = await politeFetch({
        source: SOURCE,
        url,
        method: "POST",
        body: payload,
      });
      return (await response.json()) as Record<string, unknown>;
    },
  );
  return { body: cached.body, fetchedAt: cached.fetchedAt };
}

export async function grantCount(
  env: Env,
  vintage: string,
  filters: Record<string, unknown>,
): Promise<number> {
  const { body } = await postJson(env, vintage, COUNT_URL, { filters, subawards: false });
  const results = (body.results ?? {}) as Record<string, unknown>;
  return typeof results.grants === "number" ? results.grants : 0;
}

export interface SearchResult {
  awards: Award[];
  /** The oldest retrieval date behind the result, which is what a page may claim. */
  fetchedAt: string | null;
  /** True when the page bound stopped the pull before the upstream ran out. */
  truncated: boolean;
}

/** Every matching award, deduplicated on `generated_internal_id`, keyset-paginated. */
export async function search(
  env: Env,
  vintage: string,
  filters: Record<string, unknown>,
  maxRecords = MAX_RECORDS,
): Promise<SearchResult> {
  const total = await grantCount(env, vintage, filters);
  if (total > maxRecords) {
    const programs = (filters.program_numbers as string[] | undefined)?.join(", ") ?? "this filter";
    throw new TooMuchData(
      [
        `${programs} matches ${total.toLocaleString()} grant awards in this window, more than`,
        `the ${maxRecords.toLocaleString()} this site will pull one record at a time.`,
        "Narrow it with a shorter window or a state.",
      ].join(" "),
    );
  }

  const awards = new Map<string, Award>();
  const dates: string[] = [];
  let lastId: unknown = null;
  let lastSort: unknown = null;
  let truncated = false;

  for (let page = 0; page < MAX_PAGES; page++) {
    const payload: Record<string, unknown> = {
      filters,
      fields: [...FIELDS],
      limit: PAGE_LIMIT,
      sort: "Award Amount",
      order: "desc",
      subawards: false,
    };
    if (lastId !== null) {
      payload.last_record_unique_id = lastId;
      payload.last_record_sort_value = lastSort;
    }
    const { body, fetchedAt } = await postJson(env, vintage, SEARCH_URL, payload);
    dates.push(fetchedAt);
    for (const row of (body.results as Record<string, unknown>[] | undefined) ?? []) {
      const award = toAward(row);
      // The same award can appear on two pages when the sort value ties.
      // generated_internal_id is the stable key; last write wins harmlessly.
      if (award.generatedInternalId) awards.set(award.generatedInternalId, award);
    }
    const meta = (body.page_metadata ?? {}) as Record<string, unknown>;
    if (!meta.hasNext) break;
    lastId = meta.last_record_unique_id ?? null;
    lastSort = meta.last_record_sort_value ?? null;
    // hasNext without a cursor would loop forever on page one.
    if (lastId === null) break;
    if (page === MAX_PAGES - 1) truncated = true;
  }

  return {
    awards: [...awards.values()],
    fetchedAt: dates.length ? (dates.sort()[0] as string) : null,
    truncated,
  };
}

/** Assistance Listings matching a keyword or a partial number. */
export async function findPrograms(
  env: Env,
  vintage: string,
  searchText: string,
  limit = 20,
): Promise<{ programs: ProgramRef[]; fetchedAt: string | null }> {
  const { body, fetchedAt } = await postJson(env, vintage, AUTOCOMPLETE_URL, {
    search_text: searchText,
    limit,
  });
  const rows = (body.results as Record<string, unknown>[] | undefined) ?? [];
  return {
    programs: rows.map((r) => ({
      number: String(r.program_number ?? ""),
      title: text(r.program_title),
      popularName: text(r.popular_name),
    })),
    fetchedAt,
  };
}
