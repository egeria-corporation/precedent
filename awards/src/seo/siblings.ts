/**
 * Cross-links to the rest of the portfolio.
 *
 * Five sites that reference each other read as one body of work rather than five orphans.
 * The rule that matters is the second one: **where a sibling does not yet exist, the link is
 * omitted rather than shipped dead.** A dead link on a site whose argument is that it tells
 * you what it does not know costs more than the cross-link is worth.
 *
 * So this file is the single place that decides which siblings are live, and it is edited
 * when one launches rather than discovered page by page.
 */

export interface Sibling {
  host: string;
  label: string;
  /** What this site can link to on that one, given an Employer Identification Number. */
  einPath?: (ein: string) => string;
}

/** Live today. `answers.opengrants.io` and `desk.opengrants.io` are deliberately absent. */
export const LIVE_SIBLINGS: Sibling[] = [
  {
    host: "https://funders.opengrants.io",
    label: "Private foundation funding graph",
    einPath: (ein) => `https://funders.opengrants.io/funders/${ein}`,
  },
  {
    host: "https://check.opengrants.io",
    label: "Nonprofit status and eligibility checks",
    einPath: (ein) => `https://check.opengrants.io/${ein}`,
  },
];

/** Digits only: both sibling sites key on the bare nine digits, not the hyphenated form. */
export function normalizeEin(ein: string | null | undefined): string | null {
  if (!ein) return null;
  const digits = ein.replace(/\D/g, "");
  return digits.length === 9 ? digits : null;
}

/** Sibling pages for one organization, empty when the identifier is not usable. */
export function siblingLinks(ein: string | null | undefined): { href: string; label: string }[] {
  const normalized = normalizeEin(ein);
  if (!normalized) return [];
  return LIVE_SIBLINGS.filter((s) => s.einPath).map((s) => ({
    href: (s.einPath as (e: string) => string)(normalized),
    label: s.label,
  }));
}
