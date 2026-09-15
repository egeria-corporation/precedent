/**
 * Award history statistics for one program. A port of `precedent/analysis/profile.py`.
 *
 * The headline is the new-entrant rate: the share of a window's recipients that had won
 * nothing under this program in the preceding lookback. A program with a healthy median and
 * a new-entrant rate near zero is a closed shop with good optics, and that is the fact this
 * site exists to surface.
 *
 * Conventions are pinned rather than chosen at the point of use, because two defensible
 * choices produce two different numbers and only one of them is reproducible.
 */

import type { Identity } from "./identity";
import { identityKey, nameTierIsHigh, resolutionMix, resolve } from "./identity";

/**
 * The version of everything this site produces, as opposed to the data behind it.
 *
 * It sits here, immediately beside the statistics, because the worst way to get it wrong is
 * to change a calculation without bumping it: every page computed by the old code keeps
 * being served under the new code, and nothing about such a page looks wrong.
 *
 * **It covers renders too, not only arithmetic.** The vintage moves when the upstream data
 * moves; this number is the only thing that moves when *our* output changes, and a template
 * edit changes output exactly as much as a formula does. Version 1 shipped a placeholder
 * home page; version 2 replaced it, and without a bump the Cache API went on serving the
 * placeholder, which is how this rule earned its second sentence.
 *
 * Bump it for: a changed statistic, a changed page template, a changed JSON shape.
 */
export const SCHEMA_VERSION = 2;

export const DEFAULT_LOOKBACK_YEARS = 5;
const TOP_N = 10;
const CONCENTRATION_TOP_N = 10;
const MULTI_LISTING_CAVEAT_THRESHOLD = 0.1;
const SKEW_FACTOR = 2;

/** Coverage floor: USAspending's own data does not usefully reach before this. */
export const COVERAGE_START = "2007-10-01";

/** Half-open [lo, hi). Fixed so two programs are comparable; a data-derived scale would
 *  make every program look average. */
export const BUCKETS: [string, number, number][] = [
  ["under_100k", 0, 100_000],
  ["100k_250k", 100_000, 250_000],
  ["250k_500k", 250_000, 500_000],
  ["500k_1m", 500_000, 1_000_000],
  ["1m_5m", 1_000_000, 5_000_000],
  ["5m_plus", 5_000_000, Number.POSITIVE_INFINITY],
];

export interface Award {
  generatedInternalId: string;
  awardId: string | null;
  recipientName: string | null;
  recipientUei: string | null;
  recipientId: string | null;
  amount: number | null;
  baseObligationDate: string | null;
  startDate: string | null;
  awardingAgency: string | null;
  placeOfPerformanceState: string | null;
  assistanceListings: string[];
}

export interface Bucket {
  name: string;
  count: number;
  shareOfAwards: number;
  shareOfDollars: number;
}

export interface SizeStats {
  count: number;
  total: number;
  mean: number | null;
  median: number | null;
  minimum: number | null;
  maximum: number | null;
  percentiles: Record<string, number>;
  buckets: Bucket[];
  meanIsSkewed: boolean;
}

export interface RecipientRow {
  displayName: string;
  identity: string;
  uei: string | null;
  awardCount: number;
  totalDollars: number;
}

export interface Excluded {
  missingDate: number;
  nonpositiveAmount: number;
  unresolvedIdentity: number;
}

export interface Profile {
  program: string;
  sinceFy: number;
  untilFy: number;
  lookbackYears: number;
  lookbackSinceFy: number;
  windowAwardCount: number;
  lookbackAwardCount: number;
  recipientCount: number;
  newEntrantCount: number;
  newEntrantRate: number | null;
  newEntrantRateIsUpperBound: boolean;
  repeatWinnerCount: number;
  repeatWinnerRate: number | null;
  concentrationTop10Share: number | null;
  multiListingShare: number;
  sizes: SizeStats;
  statesCovered: number;
  topStatesByCount: [string, number][];
  topRecipientsByCount: RecipientRow[];
  topRecipientsByDollars: RecipientRow[];
  identityResolution: Record<string, number>;
  excluded: Excluded;
  caveats: string[];
}

/** The federal fiscal year containing a date. October belongs to the next one. */
export function fiscalYear(day: Date): number {
  // getUTCMonth is zero-based, so 9 is October.
  return day.getUTCMonth() >= 9 ? day.getUTCFullYear() + 1 : day.getUTCFullYear();
}

export function fiscalYearStart(fy: number): string {
  return `${fy - 1}-10-01`;
}

export function fiscalYearEnd(fy: number): string {
  return `${fy}-09-30`;
}

function parseDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const day = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(day.getTime()) ? null : day;
}

/**
 * The fiscal year an award belongs to, from its first obligating action.
 *
 * Falls back to the start date, because an award with no base obligation date but a real
 * start date is still evidence of a recipient; only an award with neither is dropped.
 */
export function awardFiscalYear(award: Award): number | null {
  const day = parseDate(award.baseObligationDate) ?? parseDate(award.startDate);
  return day ? fiscalYear(day) : null;
}

/**
 * Python's `statistics.quantiles(data, n=100, method="inclusive")`, exactly.
 *
 * The default in that library is the *exclusive* method, which gives different answers on
 * small samples - and a niche program is a small sample. The reference implementation pins
 * inclusive, its verification notes give the exclusive answers this would produce instead
 * ($185,956 for p25 rather than $186,013), and reproducing the published figures depends on
 * matching it here. This is deliberately the arithmetic from CPython rather than a rounder
 * formula that happens to be close.
 */
export function inclusiveQuantile(sorted: number[], p: number): number {
  const ld = sorted.length;
  if (ld === 0) return Number.NaN;
  if (ld === 1) return sorted[0] as number;
  const m = ld - 1;
  const j = Math.floor((p * m) / 100);
  const delta = p * m - j * 100;
  const lo = sorted[j] as number;
  const hi = sorted[j + 1] ?? lo;
  return (lo * (100 - delta) + hi * delta) / 100;
}

/** Python's `statistics.median`: the mean of the two middle values on an even count. */
export function median(sorted: number[]): number | null {
  const n = sorted.length;
  if (!n) return null;
  const mid = Math.floor(n / 2);
  if (n % 2 === 1) return sorted[mid] as number;
  return (((sorted[mid - 1] as number) + (sorted[mid] as number)) / 2) as number;
}

export function sizeStats(amounts: number[]): SizeStats {
  if (!amounts.length) {
    return {
      count: 0,
      total: 0,
      mean: null,
      median: null,
      minimum: null,
      maximum: null,
      percentiles: {},
      buckets: [],
      meanIsSkewed: false,
    };
  }
  const ordered = [...amounts].sort((a, b) => a - b);
  const total = ordered.reduce((s, a) => s + a, 0);
  const mean = total / ordered.length;
  const mid = median(ordered);

  const percentiles: Record<string, number> = {};
  for (const p of [10, 25, 50, 75, 90]) {
    percentiles[`p${p}`] =
      ordered.length >= 2 ? inclusiveQuantile(ordered, p) : (ordered[0] as number);
  }

  const buckets: Bucket[] = BUCKETS.map(([name, lo, hi]) => {
    const inside = ordered.filter((a) => a >= lo && a < hi);
    const sum = inside.reduce((s, a) => s + a, 0);
    return {
      name,
      count: inside.length,
      shareOfAwards: inside.length / ordered.length,
      shareOfDollars: total ? sum / total : 0,
    };
  });

  return {
    count: ordered.length,
    total,
    mean,
    median: mid,
    minimum: ordered[0] as number,
    maximum: ordered[ordered.length - 1] as number,
    percentiles,
    buckets,
    meanIsSkewed: mid ? mean > SKEW_FACTOR * mid : false,
  };
}

/** The raw name a consultant would recognise: most frequent, ties broken by spelling. */
function displayName(names: Map<string, number>): string {
  if (!names.size) return "";
  const best = Math.max(...names.values());
  return [...names.entries()]
    .filter(([, c]) => c === best)
    .map(([n]) => n)
    .sort()[0] as string;
}

export interface ProfileOptions {
  program: string;
  sinceFy: number;
  untilFy: number;
  lookbackYears?: number;
}

export function buildProfile(awards: Award[], options: ProfileOptions): Profile {
  const { program, sinceFy, untilFy } = options;
  const lookbackYears = options.lookbackYears ?? DEFAULT_LOOKBACK_YEARS;
  const lookbackSinceFy = sinceFy - lookbackYears;
  const excluded: Excluded = { missingDate: 0, nonpositiveAmount: 0, unresolvedIdentity: 0 };

  const windowAwards: Award[] = [];
  const lookback: Award[] = [];
  for (const award of awards) {
    const fy = awardFiscalYear(award);
    if (fy === null) {
      excluded.missingDate += 1;
      continue;
    }
    // `Award Amount` is the award's total obligation over its life, so at or below zero it
    // was fully de-obligated: approved, then unwound. Counting such an organization as a
    // recipient - and so as a possible new entrant - would say a program let somebody new
    // in when in the end it gave them nothing.
    if (!award.amount || award.amount <= 0) {
      excluded.nonpositiveAmount += 1;
      continue;
    }
    if (fy >= sinceFy && fy <= untilFy) windowAwards.push(award);
    else if (fy >= lookbackSinceFy && fy < sinceFy) lookback.push(award);
  }

  const windowIdentities = windowAwards.map((a) =>
    resolve({
      recipientUei: a.recipientUei,
      recipientId: a.recipientId,
      recipientName: a.recipientName,
    }),
  );
  excluded.unresolvedIdentity = windowIdentities.filter((i) => i === null).length;

  const awardsByIdentity = new Map<string, Set<string>>();
  const dollarsByIdentity = new Map<string, number>();
  const namesByIdentity = new Map<string, Map<string, number>>();
  const ueiByIdentity = new Map<string, string | null>();

  windowAwards.forEach((award, index) => {
    const identity = windowIdentities[index];
    if (!identity) return;
    const key = identityKey(identity);
    if (!awardsByIdentity.has(key)) awardsByIdentity.set(key, new Set());
    (awardsByIdentity.get(key) as Set<string>).add(award.generatedInternalId);
    dollarsByIdentity.set(key, (dollarsByIdentity.get(key) ?? 0) + (award.amount ?? 0));
    if (award.recipientName) {
      if (!namesByIdentity.has(key)) namesByIdentity.set(key, new Map());
      const names = namesByIdentity.get(key) as Map<string, number>;
      names.set(award.recipientName, (names.get(award.recipientName) ?? 0) + 1);
    }
    if (!ueiByIdentity.has(key)) ueiByIdentity.set(key, award.recipientUei);
  });

  const lookbackKeys = new Set<string>();
  for (const award of lookback) {
    const identity = resolve({
      recipientUei: award.recipientUei,
      recipientId: award.recipientId,
      recipientName: award.recipientName,
    });
    if (identity) lookbackKeys.add(identityKey(identity));
  }

  const windowKeys = [...awardsByIdentity.keys()];
  const newEntrants = windowKeys.filter((k) => !lookbackKeys.has(k));
  const repeatWinners = windowKeys.filter(
    (k) => (awardsByIdentity.get(k) as Set<string>).size >= 2,
  );
  const recipientCount = windowKeys.length;

  const sizes = sizeStats(windowAwards.map((a) => a.amount as number));

  const rankedDollars = [...dollarsByIdentity.entries()].sort(
    (a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1),
  );
  const allDollars = rankedDollars.reduce((s, [, v]) => s + v, 0);
  const top10Dollars = rankedDollars.slice(0, CONCENTRATION_TOP_N).reduce((s, [, v]) => s + v, 0);
  const concentration = allDollars ? top10Dollars / allDollars : null;

  const multi = windowAwards.filter((a) => a.assistanceListings.length > 1).length;
  const multiShare = windowAwards.length ? multi / windowAwards.length : 0;

  const states = new Map<string, number>();
  for (const award of windowAwards) {
    if (award.placeOfPerformanceState) {
      states.set(
        award.placeOfPerformanceState,
        (states.get(award.placeOfPerformanceState) ?? 0) + 1,
      );
    }
  }

  const rows = (order: [string, unknown][]): RecipientRow[] =>
    order.slice(0, TOP_N).map(([key]) => ({
      displayName: displayName(namesByIdentity.get(key) ?? new Map()),
      identity: key,
      uei: ueiByIdentity.get(key) ?? null,
      awardCount: (awardsByIdentity.get(key) as Set<string>).size,
      totalDollars: dollarsByIdentity.get(key) ?? 0,
    }));

  const byCount = [...awardsByIdentity.entries()].sort(
    (a, b) => b[1].size - a[1].size || (a[0] < b[0] ? -1 : 1),
  );

  const mix = resolutionMix(windowIdentities);
  const lookbackTruncated = fiscalYearStart(lookbackSinceFy) < COVERAGE_START;
  const upperBound = lookbackTruncated || lookback.length === 0;

  const caveats: string[] = [];
  if (lookbackTruncated) {
    caveats.push(
      [
        `The lookback reaches before ${COVERAGE_START}, which is as far back as this search`,
        "covers. Some recipients counted as new may have won earlier, so the new-entrant",
        "rate is an upper bound.",
      ].join(" "),
    );
  }
  if (!lookback.length) {
    caveats.push(
      [
        `No awards at all in the FY${lookbackSinceFy}-FY${sinceFy - 1} lookback, which usually`,
        "means the program did not exist yet. Every recipient therefore counts as new, and",
        "the new-entrant rate is an upper bound.",
      ].join(" "),
    );
  }
  if (nameTierIsHigh(mix)) {
    caveats.push(
      [
        `${Math.round((mix.name ?? 0) * 100)}% of awards were matched to a recipient by name`,
        "rather than by an assigned identifier, so the distinct-organization counts are",
        "softer than usual.",
      ].join(" "),
    );
  }
  if (multiShare > MULTI_LISTING_CAVEAT_THRESHOLD) {
    caveats.push(
      [
        `${Math.round(multiShare * 100)}% of awards are reported under more than one`,
        "Assistance Listing. Award amounts include money from those other programs, so the",
        "size percentiles are an upper bound.",
      ].join(" "),
    );
  }
  if (sizes.meanIsSkewed) {
    caveats.push(
      "The mean award is more than twice the median, so a few large awards are pulling it " +
        "upward. The median is the better guide to a typical award.",
    );
  }
  if (excluded.missingDate) {
    caveats.push(`${excluded.missingDate} award(s) had no usable date and were left out entirely.`);
  }

  return {
    program,
    sinceFy,
    untilFy,
    lookbackYears,
    lookbackSinceFy,
    windowAwardCount: windowAwards.length,
    lookbackAwardCount: lookback.length,
    recipientCount,
    newEntrantCount: newEntrants.length,
    newEntrantRate: recipientCount ? newEntrants.length / recipientCount : null,
    newEntrantRateIsUpperBound: upperBound,
    repeatWinnerCount: repeatWinners.length,
    repeatWinnerRate: recipientCount ? repeatWinners.length / recipientCount : null,
    concentrationTop10Share: concentration,
    multiListingShare: multiShare,
    sizes,
    statesCovered: states.size,
    topStatesByCount: [...states.entries()]
      .sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1))
      .slice(0, TOP_N),
    topRecipientsByCount: rows(byCount),
    topRecipientsByDollars: rows(rankedDollars),
    identityResolution: mix,
    excluded,
    caveats,
  };
}
