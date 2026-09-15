/**
 * Who actually hands federal money to organizations in one state.
 *
 * A port of `precedent/analysis/passthrough.py`. Two evidence streams, computed separately
 * and merged only for display, because they are different facts:
 *
 * - **Demand side.** Organizations reporting money received *through* somebody. Their
 *   auditors typed the name. This answers "who would fund an organization like mine", and
 *   its identifiers are bad: free text, no state, no EIN.
 * - **Supply side.** Organizations whose own audit says they *passed money down*. A real
 *   EIN, a real city, a real entity type, because the filer is the intermediary itself.
 *
 * The second lends identifiers to the first and records how, because a name agreeing with a
 * name is a name match and calling it an identity match would be the lie this module is
 * arranged to avoid.
 *
 * Clustering is deliberately timid: the committed alias table does what a person checked,
 * everything else is exact normalized match within one state, and nothing crosses a state.
 * A wrongly merged entity asserts a fact that is not true; a split entity merely undercounts.
 */

import {
  type Audit,
  type PassThrough,
  type SefaAward,
  assistanceListing,
  awardKey,
  passedMoneyDown,
  receivedThroughSomeone,
} from "../sources/fac";
import { ALIAS_TABLE, type AliasEntry } from "./aliases";
import { type PassthroughCoverage, buildCoverage } from "./coverage";
import { normalizeName } from "./identity";

export const TOP_SUBRECIPIENTS = 25;

/** A composite key that cannot collide, whatever characters a name contains. */
function aliasKey(state: string, normalized: string): string {
  return JSON.stringify([state, normalized]);
}

/** `(state, normalized name) -> entry`, for every canonical name and every alias. */
const ALIAS_INDEX: Map<string, AliasEntry> = (() => {
  const index = new Map<string, AliasEntry>();
  for (const entry of ALIAS_TABLE) {
    for (const name of [entry.canonical, ...entry.aliases]) {
      const key = normalizeName(name);
      if (key) index.set(aliasKey(entry.state, key), entry);
    }
  }
  return index;
})();

export function aliasFor(name: string | null, state: string): AliasEntry | undefined {
  const normalized = normalizeName(name);
  if (!normalized) return undefined;
  return ALIAS_INDEX.get(aliasKey(state.toUpperCase(), normalized));
}

/**
 * The cluster a raw `passthrough_name` belongs to, within one state.
 *
 * The alias table first, then the normalized name itself. Nothing else: an initialism is
 * only ever expanded through the table, because the same three letters name a different
 * agency in another state and a wrong merge asserts something untrue.
 */
export function clusterKey(name: string | null, state: string): string {
  const normalized = normalizeName(name);
  if (!normalized) return "";
  const entry = aliasFor(name, state);
  return entry ? normalizeName(entry.canonical) : normalized;
}

export interface NameVariant {
  raw: string;
  count: number;
  exampleReportId: string;
}

export interface Subrecipient {
  name: string | null;
  city: string | null;
  ein: string | null;
  amountExpended: number;
}

export interface Intermediary {
  canonicalName: string;
  clusterKey: string;
  state: string;
  /** Distinct organizations: one audited five years running counts once. */
  subrecipientCount: number;
  /** Distinct audits, which is the raw evidence count. */
  observationCount: number;
  amountExpendedTotal: number;
  programs: [string, number][];
  nameVariants: NameVariant[];
  subrecipients: Subrecipient[];
  entityType: string | null;
  ein: string | null;
  city: string | null;
  identifierSource: "alias_table" | "supply_side_match" | "none";
  fromAliasTable: boolean;
}

export interface Supplier {
  name: string | null;
  ein: string | null;
  uei: string | null;
  city: string | null;
  entityType: string | null;
  passthroughAmountTotal: number;
  amountExpendedTotal: number;
  auditYears: string[];
  clusterKey: string;
}

export interface PassthroughResult {
  state: string;
  program: string | null;
  intermediaries: Intermediary[];
  suppliers: Supplier[];
  coverage: PassthroughCoverage;
}

function rank(counts: Map<string, number>): [string, number][] {
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1));
}

/** The spelling most auditors used, ties broken by spelling so output is stable. */
function displayName(variants: Map<string, number>): string {
  if (!variants.size) return "";
  const best = Math.max(...variants.values());
  return [...variants.entries()]
    .filter(([, c]) => c === best)
    .map(([n]) => n)
    .sort()[0] as string;
}

export function buildSuppliers(audits: Audit[], awards: SefaAward[]): Supplier[] {
  const byReport = new Map(audits.map((a) => [a.reportId, a]));
  const merged = new Map<string, Supplier>();
  for (const award of awards) {
    if (!passedMoneyDown(award)) continue;
    const audit = byReport.get(award.reportId);
    if (!audit) continue;
    const key = normalizeName(audit.auditeeName);
    const existing = merged.get(key);
    if (!existing) {
      merged.set(key, {
        name: audit.auditeeName,
        ein: audit.auditeeEin,
        uei: audit.auditeeUei,
        city: audit.auditeeCity,
        entityType: audit.entityType,
        passthroughAmountTotal: award.passthroughAmount ?? 0,
        amountExpendedTotal: award.amountExpended ?? 0,
        auditYears: audit.auditYear ? [audit.auditYear] : [],
        clusterKey: key,
      });
    } else {
      existing.passthroughAmountTotal += award.passthroughAmount ?? 0;
      existing.amountExpendedTotal += award.amountExpended ?? 0;
      if (audit.auditYear && !existing.auditYears.includes(audit.auditYear)) {
        existing.auditYears.push(audit.auditYear);
      }
    }
  }
  for (const s of merged.values()) s.auditYears.sort();
  return [...merged.values()].sort(
    (a, b) =>
      b.passthroughAmountTotal - a.passthroughAmountTotal ||
      ((a.name ?? "") < (b.name ?? "") ? -1 : 1),
  );
}

export function buildIntermediaries(
  audits: Audit[],
  indirectAwards: SefaAward[],
  passthroughRows: PassThrough[],
  state: string,
): { intermediaries: Intermediary[]; unattributed: number } {
  const upper = state.toUpperCase();
  const byReport = new Map(audits.map((a) => [a.reportId, a]));
  const named = new Map(passthroughRows.map((p) => [awardKey(p.reportId, p.awardReference), p]));

  let unattributed = 0;
  const grouped = new Map<string, { award: SefaAward; entity: PassThrough; audit: Audit }[]>();

  for (const award of indirectAwards) {
    if (!receivedThroughSomeone(award)) continue;
    const audit = byReport.get(award.reportId);
    if (!audit) continue;
    const entity = named.get(awardKey(award.reportId, award.awardReference));
    // An indirect line naming nobody is a reporting gap in that filing. It is counted and
    // reported, never dropped and never guessed at.
    if (!entity?.name) {
      unattributed += 1;
      continue;
    }
    const key = clusterKey(entity.name, upper);
    if (!key) {
      unattributed += 1;
      continue;
    }
    if (!grouped.has(key)) grouped.set(key, []);
    (grouped.get(key) as { award: SefaAward; entity: PassThrough; audit: Audit }[]).push({
      award,
      entity,
      audit,
    });
  }

  const out: Intermediary[] = [];
  for (const [key, group] of grouped) {
    const alias = ALIAS_INDEX.get(aliasKey(upper, key));
    const variants = new Map<string, number>();
    const variantExample = new Map<string, string>();
    const listings = new Map<string, number>();
    const byOrg = new Map<string, Subrecipient>();
    const auditIds = new Set<string>();
    let total = 0;

    for (const { award, entity, audit } of group) {
      const raw = entity.name ?? "";
      variants.set(raw, (variants.get(raw) ?? 0) + 1);
      if (!variantExample.has(raw)) variantExample.set(raw, audit.reportId);
      const listing = assistanceListing(award.federalAgencyPrefix, award.federalAwardExtension);
      if (listing) listings.set(listing, (listings.get(listing) ?? 0) + 1);
      const amount = award.amountExpended ?? 0;
      total += amount;
      auditIds.add(audit.reportId);
      // One organization audited five years running is one subrecipient, not five.
      const orgKey = audit.auditeeEin ?? normalizeName(audit.auditeeName) ?? audit.reportId;
      const row = byOrg.get(orgKey);
      if (!row) {
        byOrg.set(orgKey, {
          name: audit.auditeeName,
          city: audit.auditeeCity,
          ein: audit.auditeeEin,
          amountExpended: amount,
        });
      } else {
        row.amountExpended += amount;
      }
    }

    out.push({
      canonicalName: alias ? alias.canonical : displayName(variants),
      clusterKey: key,
      state: upper,
      subrecipientCount: byOrg.size,
      observationCount: auditIds.size,
      amountExpendedTotal: total,
      programs: rank(listings),
      nameVariants: [...variants.entries()]
        .sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1))
        .map(([raw, count]) => ({
          raw,
          count,
          exampleReportId: variantExample.get(raw) as string,
        })),
      subrecipients: [...byOrg.values()].sort(
        (a, b) => b.amountExpended - a.amountExpended || ((a.name ?? "") < (b.name ?? "") ? -1 : 1),
      ),
      entityType: alias?.entityType ?? null,
      ein: alias?.ein ?? null,
      city: null,
      identifierSource: alias?.ein ? "alias_table" : "none",
      fromAliasTable: alias !== undefined,
    });
  }

  // Rank by subrecipient count, then dollars. Deliberate: dollars name the biggest
  // intermediary, but subrecipient count names the one that actually makes subawards to
  // organizations like the reader's, and that is the question being asked.
  out.sort(
    (a, b) =>
      b.subrecipientCount - a.subrecipientCount ||
      b.amountExpendedTotal - a.amountExpendedTotal ||
      (a.canonicalName < b.canonicalName ? -1 : 1),
  );
  return { intermediaries: out, unattributed };
}

/**
 * Give demand-side clusters an EIN where the supply side names the same organization.
 *
 * Both sides are confined to one state, so this cannot merge across states. It records
 * `identifierSource` either way.
 */
export function attachIdentifiers(intermediaries: Intermediary[], suppliers: Supplier[]): void {
  const byKey = new Map(suppliers.filter((s) => s.clusterKey).map((s) => [s.clusterKey, s]));
  for (const entity of intermediaries) {
    if (entity.ein) continue;
    const supplier = byKey.get(entity.clusterKey);
    if (!supplier?.ein) continue;
    entity.ein = supplier.ein;
    entity.city = entity.city ?? supplier.city;
    entity.entityType = entity.entityType ?? supplier.entityType;
    entity.identifierSource = "supply_side_match";
  }
}

export function buildPassthrough(input: {
  state: string;
  program: string | null;
  audits: Audit[];
  indirectAwards: SefaAward[];
  passthroughRows: PassThrough[];
  supplyAwards: SefaAward[];
  retrieved: string | null;
  requestedSinceYear?: number;
}): PassthroughResult {
  const state = input.state.trim().toUpperCase();
  const { intermediaries, unattributed } = buildIntermediaries(
    input.audits,
    input.indirectAwards,
    input.passthroughRows,
    state,
  );
  const suppliers = buildSuppliers(input.audits, input.supplyAwards);
  attachIdentifiers(intermediaries, suppliers);
  const years = [
    ...new Set(
      input.audits.map((a) => Number(a.auditYear)).filter((y) => Number.isFinite(y) && y > 0),
    ),
  ];
  return {
    state,
    program: input.program,
    intermediaries,
    suppliers,
    coverage: buildCoverage({
      state,
      auditsScanned: input.audits.length,
      auditYears: years,
      unattributedIndirectLines: unattributed,
      retrieved: input.retrieved,
      requestedSinceYear: input.requestedSinceYear,
    }),
  };
}

/** A stable, readable slug for an intermediary's own page. */
export function intermediarySlug(state: string, key: string): string {
  return `${state.toLowerCase()}-${key
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")}`;
}
