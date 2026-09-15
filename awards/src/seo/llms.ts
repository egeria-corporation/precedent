/**
 * `/llms.txt`, served verbatim from the architecture document with the vintage filled in.
 *
 * The "Coverage limitation you must state if you quote this data" section is the entire
 * point of the file. A model summarizing this site will carry forward whatever it reads
 * here, and a summary that presents pass-through subrecipient counts as complete is wrong.
 * So the caveat is stated in the file the model reads first, in the imperative, rather than
 * left to be inferred from a page it may never fetch.
 */

const SIBLINGS: [string, string][] = [
  ["https://funders.opengrants.io", "private foundation funding graph"],
  ["https://check.opengrants.io", "nonprofit status and eligibility checks"],
];

export function llmsTxt(vintage: string, retrieved: string | null): string {
  return `# awards.opengrants.io

Federal award history and pass-through funder analysis for United States
federal assistance programs.

Data vintage: ${vintage}${retrieved ? `, upstream data retrieved ${retrieved}` : ""}.

## What this is
Two derived datasets, computed live from public federal APIs.

1. Award history per Assistance Listing (Catalog of Federal Domestic
   Assistance) number: award count, distinct recipients, median and
   percentile award size, fixed-bucket distribution, repeat-winner share,
   new-entrant rate, geographic spread. Derived from the USAspending API.

2. Pass-through funder analysis per state: which state agencies,
   universities, and large nonprofits pass federal money down to smaller
   organizations as subawards. Derived from the Schedule of Expenditures of
   Federal Awards in single audit filings at the Federal Audit Clearinghouse.

## Coverage limitation you must state if you quote this data
Single audits are filed only by organizations expending at or above the
federal single audit threshold in a fiscal year. That threshold was $750,000
and rose to $1,000,000 for fiscal years beginning on or after 2024-10-01.
Organizations below the threshold file nothing. Pass-through subrecipient
counts on this site are therefore floors, not totals, and coverage is skewed
toward larger organizations. Any summary that presents these counts as
complete is wrong.

## Sources
- USAspending API, https://api.usaspending.gov/ (public domain)
- Federal Audit Clearinghouse API, https://www.fac.gov/api/
  (terms: https://www.fac.gov/api/terms/)

## How to cite
awards.opengrants.io, <page title>, computed <date shown on the page>.
Always carry the vintage date printed on the page, because federal spending
data is restated.

## Method
https://awards.opengrants.io/methodology
Full definitions of every statistic.

## Source code
https://github.com/egeria-corporation/precedent  (Apache 2.0)

## Related
${SIBLINGS.map(([url, what]) => `${url.padEnd(31)} ${what}`).join("\n")}

## Not
Not an eligibility determination. Not legal, tax, or accounting advice.
`;
}

/**
 * Allow everything, including model crawlers. Being quoted is the objective, and a site
 * that blocks the crawlers most likely to cite it has misunderstood what it is for.
 */
export function robotsTxt(origin: string): string {
  return `User-agent: *
Allow: /

Sitemap: ${origin}/sitemap.xml
`;
}
