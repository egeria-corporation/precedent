/**
 * Deciding when two award records are the same organization.
 *
 * A direct port of `precedent/analysis/identity.py`. The two statistics people quote from
 * this site - the new-entrant rate and the repeat-winner rate - are both counts of distinct
 * organizations, so splitting one grantee into two makes a program look more open than it
 * is and merging two makes it look closed. Either way the number reads as authoritative.
 *
 * This file and its Python original must agree exactly. Where a rule looks arbitrary it is
 * because it matches the reference implementation the numbers were verified against; change
 * one without the other and the site quietly disagrees with the tool it is a companion to.
 */

/** Applied repeatedly: "FOO SERVICES INC LLC" loses both, "THE FOO CO" loses CO then THE. */
const LEGAL_SUFFIXES = [
  "INCORPORATED",
  "CORPORATION",
  "COMPANY",
  "LIMITED",
  "INC",
  "LLC",
  "LLP",
  "LP",
  "CORP",
  "CO",
  "LTD",
  "PC",
  "PA",
  "THE",
];

/** Whole-token expansions only. Substring replacement would turn "COSTA" into "COMPANYSTA". */
const ABBREVIATIONS: Record<string, string> = {
  DEPT: "DEPARTMENT",
  UNIV: "UNIVERSITY",
  ASSN: "ASSOCIATION",
  ASSOC: "ASSOCIATION",
  NATL: "NATIONAL",
  INTL: "INTERNATIONAL",
  SVCS: "SERVICES",
  SVC: "SERVICES",
  CTR: "CENTER",
  CNTY: "COUNTY",
  US: "UNITED STATES",
  AAA: "AREA AGENCY ON AGING",
};

/** "ST LOUIS" is a city and "ST STATE" is nonsense, so this expands only in first position. */
const FIRST_TOKEN_ABBREVIATIONS: Record<string, string> = { ST: "STATE" };

/** The share resolved by name above which the statistics deserve a warning. */
export const NAME_TIER_WARNING_THRESHOLD = 0.1;

export type Tier = "uei" | "recipient_id" | "name";

export interface Identity {
  tier: Tier;
  value: string;
}

export interface HasIdentity {
  recipientUei: string | null;
  recipientId: string | null;
  recipientName: string | null;
}

export function identityKey(identity: Identity): string {
  return `${identity.tier}:${identity.value}`;
}

/** One organization name reduced to a comparable form. */
export function normalizeName(raw: string | null | undefined): string {
  if (!raw) return "";
  // NFKD then strip combining marks, matching the Python unicodedata pass.
  let text = raw
    .normalize("NFKD")
    .toUpperCase()
    .replace(/\p{M}/gu, "")
    .replace(/&/g, " AND ")
    .replace(/[^A-Z0-9 ]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!text) return "";

  const tokens = text.split(" ");
  const first = tokens[0];
  if (first !== undefined && FIRST_TOKEN_ABBREVIATIONS[first] !== undefined) {
    tokens[0] = FIRST_TOKEN_ABBREVIATIONS[first] as string;
  }
  text = tokens.map((t) => ABBREVIATIONS[t] ?? t).join(" ");

  // Strip trailing legal suffixes until none matches, then a leading THE.
  let changed = true;
  while (changed) {
    changed = false;
    for (const suffix of LEGAL_SUFFIXES) {
      if (text.endsWith(` ${suffix}`)) {
        text = text.slice(0, -(suffix.length + 1)).trim();
        changed = true;
      }
    }
  }
  if (text.startsWith("THE ")) text = text.slice(4).trim();
  return text;
}

/**
 * USAspending's recipient id without its `-C`/`-R`/`-P` level marker.
 *
 * The same organization appears as child, recipient and parent; keeping the suffix splits
 * one organization into three, and the reference implementation's verification notes name
 * this as one of the two most likely causes of a wrong answer.
 */
export function stripLevelSuffix(recipientId: string | null | undefined): string | null {
  if (!recipientId) return null;
  return recipientId.trim().replace(/-(C|R|P)$/i, "") || null;
}

/** The strongest identity available for one record, or null if there is nothing. */
export function resolve(record: HasIdentity): Identity | null {
  const uei = (record.recipientUei ?? "").trim().toUpperCase();
  if (uei.length === 12) return { tier: "uei", value: uei };
  const stripped = stripLevelSuffix(record.recipientId);
  if (stripped) return { tier: "recipient_id", value: stripped };
  const name = normalizeName(record.recipientName);
  if (name) return { tier: "name", value: name };
  return null;
}

/** The share of records resolved at each tier, rounded to four places. */
export function resolutionMix(identities: (Identity | null)[]): Record<string, number> {
  const total = identities.length;
  if (!total) return {};
  const counts = new Map<string, number>();
  for (const identity of identities) {
    const tier = identity ? identity.tier : "unresolved";
    counts.set(tier, (counts.get(tier) ?? 0) + 1);
  }
  const out: Record<string, number> = {};
  for (const [tier, n] of counts) out[tier] = Math.round((n / total) * 10000) / 10000;
  return out;
}

export function nameTierIsHigh(
  mix: Record<string, number>,
  threshold = NAME_TIER_WARNING_THRESHOLD,
): boolean {
  return (mix.name ?? 0) > threshold;
}
