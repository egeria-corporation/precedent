# Hosted companion: awards.opengrants.io

The web surface for `precedent`. Same computations, same honesty rules, rendered as pages
that search engines and language models can read, cite, and quote.

The repository does not rank. These pages do. That is the point of the hosted companion.

---

## Platform decision

**Cloudflare Workers.** Not Pages, not Netlify. Per the program hosting plan:

- Workers Paid at $5 per month covers the request volume for the whole five-site portfolio
  well past launch.
- R2 has no egress fees, which matters if we publish the Unique Entity Identifier to
  Employer Identification Number crosswalk as a downloadable dataset.
- Pre-rendering is not viable at scale for the sibling sites and is not needed here either.
  This site renders on demand at the edge and caches.

`precedent` is the lightest of the five sites in storage terms, because it has **no bulk
dataset behind it**. It is a caching, rendering layer over two upstream APIs. There is no
D1 database and no ingest pipeline in the first release. This is a real architectural
advantage over its siblings and the design should not give it away by inventing a warehouse
it does not need.

| Concern | Decision |
|---|---|
| Runtime | Cloudflare Workers, TypeScript strict mode, Hono |
| Rendering | Server-side at the edge. Real HTML with real content in the initial response |
| Cache | Workers KV, keyed on data vintage |
| Object storage | R2, for sitemaps and any published dataset. No R2 in the request path |
| Database | None in v1 |
| Package manager | `pnpm`. Lint and format with `biome`. Tests with `vitest` |
| Secrets | `FAC_API_KEY`, `OPENGRANTS_API_KEY` as Worker secrets |
| Domain | `awards.opengrants.io` |

---

## Request path

```
Browser or crawler
   |
   v
Cloudflare edge  -->  Cache API  (rendered HTML, immutable per vintage)
   |  miss
   v
Worker (Hono router)
   |
   +--> KV: upstream response cache, keyed on source + query + vintage
   |       |  miss
   |       v
   |    USAspending  api.usaspending.gov      (no key)
   |    FAC          api.fac.gov              (X-Api-Key)
   |    OpenGrants   .../functions/v1/        (Bearer, optional, non-blocking)
   |
   +--> shared statistics module (port of the Python analysis layer)
   |
   v
HTML response  +  Cache-Control  +  schema.org JSON-LD
```

Two cache layers, doing different jobs.

**KV, upstream responses.** Key:
`u:{source}:{sha256(canonical request)}:{vintage}`. Value: the raw upstream JSON plus
`fetched_at`. Time to live matches the tool: 7 days for USAspending, 7 days for FAC, 24
hours for OpenGrants. This layer is what keeps us from becoming a load problem for two free
public APIs, and it is not optional.

**Cache API, rendered pages.** Key:
`https://awards.opengrants.io{path}?v={vintage}`. The rendered HTML is cached at the edge.

### Vintage keying, not time-to-live expiry

Per the program caching strategy, the cache is keyed on **data vintage** rather than
relying on expiry, so a new upstream refresh invalidates everything cleanly.

Vintage is a single string in KV at `meta:vintage`, of the form
`fac{YYYY-MM-DD}-usa{YYYY-MM-DD}`. It is rewritten by a scheduled Worker. Every cache key
includes it. Bumping it invalidates the whole site atomically without a purge API call and
without a deploy.

A `schema_version` integer is prefixed to every key as well, so a change to the statistics
or the page template invalidates cached output the same way. Forgetting to bump it after
changing a calculation is the most likely way to serve a stale wrong number, so it lives in
one exported constant next to the statistics module with a comment saying exactly that.

### Stale while revalidate

Serve stale content and refresh in the background with `ctx.waitUntil()`. A four-day-old
median is always better than a spinner, and the upstream calls behind a program page can
take twenty seconds on a cold miss.

### Scheduled Worker

Cron `0 9 * * 4`, Thursday 09:00 UTC. FAC production refreshes weekly, typically
Wednesdays, so Thursday morning is the right time to pick it up.

1. Probe FAC for the newest `fac_accepted_date` and USAspending for its latest load date.
2. If either moved, write a new `meta:vintage`.
3. Warm the cache for the top few hundred program pages and all 56 state pass-through
   pages, sequentially with backoff.
4. Regenerate `sitemap.xml` and the sitemap chunks into R2.

---

## Page taxonomy

Every URL is canonical, one per entity, with slug variants redirecting rather than
duplicating.

### Program pages

| Route | Content |
|---|---|
| `/programs/93.243` | **Canonical program page.** Full award history profile: new-entrant rate as the headline, median and percentile spread, fixed-bucket distribution, repeat-winner share, concentration, geography, most frequent recipients, multi-listing caveat, source and retrieval date. Optional open-opportunity section from OpenGrants |
| `/programs/93.243/OH` | Same program, awards with place of performance in one state |
| `/programs/93.243/recipients` | Full paginated awardee list. Paginated so it stays cacheable |
| `/programs/93.243/passthrough` | Who passes this program's money down, nationally |

Canonicalization: `/programs/93.243` is the only canonical form. Accept and 301 from
`/programs/93243`, `/programs/cfda/93.243`, `/cfda/93.243`, and a title slug form such as
`/programs/93.243-substance-abuse-and-mental-health-services...`. Never serve two URLs for
one program.

### Agency pages

| Route | Content |
|---|---|
| `/agencies` | All awarding agencies with assistance programs, by obligated dollars |
| `/agencies/department-of-health-and-human-services` | Agency overview and its Assistance Listings, each with median award size and new-entrant rate so the table itself is the useful artifact |
| `/agencies/department-of-health-and-human-services/substance-abuse-and-mental-health-services-administration` | Sub-agency, same shape |

Agency slugs come from USAspending's own `agency_slug` field so they match the source.

### Pass-through pages, the differentiated set

| Route | Content |
|---|---|
| `/passthrough` | Index of all 56 states and territories |
| `/passthrough/oh` | **The state pass-through view.** Entities passing federal money to Ohio organizations, ranked by distinct subrecipient count, with the supply-side list alongside. The coverage warning is above the table, not below it |
| `/passthrough/oh/93.045` | State by program |
| `/passthrough/oh/hhs` | State by agency, aggregating that agency's programs |
| `/intermediaries/{slug}` | **One pass-through entity.** Which programs it passes down, how many subrecipients name it, which states they are in, the raw name variants clustered into it, and the source `report_id` values. Employer Identification Number where the supply-side data provides it |

`/passthrough/oh` and `/intermediaries/*` are the pages nothing else on the internet
currently serves. They are the reason this site is worth building, and they should be the
best pages on it.

### Organization pages

| Route | Content |
|---|---|
| `/recipients/{uei}` | One awardee: federal award history, single audit history where it files, whether it passes money down, and cross-links to siblings by Employer Identification Number |

### Editorial and reference

| Route | Content |
|---|---|
| `/` | What this is, the two questions it answers, and one live worked example rather than marketing copy |
| `/methodology` | Every statistic defined exactly as in the README table, with worked arithmetic |
| `/coverage` | The single audit threshold, the multi-listing distortion, the 2016 FAC floor, the 2007 USAspending floor, and what each one does to the numbers. Linked from every page footer |
| `/data` | The published Unique Entity Identifier to Employer Identification Number crosswalk, from R2, with vintage and coverage statistics |
| `/about` | Egeria, OpenGrants sponsorship, the repository, the license |

### Machine surfaces

| Route | Content |
|---|---|
| `/llms.txt` | Required. See below |
| `/robots.txt` | Allow all, point at the sitemap index |
| `/sitemap.xml` | Sitemap index, chunks at 50,000 URLs, served from R2 |
| `/api/programs/93.243.json` | The same computation as JSON. Documented, rate limited, CORS enabled. Cheap to add because the renderer already has the object |

---

## Search engine and generative engine requirements

These come from the program hosting plan and apply to every page.

**Server-rendered HTML with real content in the initial response.** No client-side fetching
for primary content. If a language model crawler renders no JavaScript, it must still see
the median, the new-entrant rate, and the pass-through table. Interactivity is progressive
enhancement over content that is already there.

**Structured data on every entity page.** JSON-LD in the head.

- Program pages: `GovernmentService` with `serviceOperator` as the awarding agency, plus a
  `Dataset` describing the derived statistics with `temporalCoverage`, `dateModified`, and
  `isBasedOn` pointing at the USAspending API.
- Intermediary and recipient pages: `Organization` or `NGO` with `taxID` set to the
  Employer Identification Number where known, `address`, and `funder` relationships where
  the pass-through data establishes them. This is what makes the pages machine-quotable.
- All pages: `BreadcrumbList`.
- Editorial pages: `FAQPage` where the content genuinely is questions and answers, not as a
  markup trick.

**One canonical URL per entity**, with a `<link rel="canonical">` on every page, including
the canonical page itself.

**Every page states its source and vintage inline, in visible text**, not only in metadata.
"Computed 2026-08-30 from the USAspending API. Single audit data from the Federal Audit
Clearinghouse, audit years 2016 through 2024, retrieved 2026-08-28." Pages that show their
work get cited. Pages that assert bare numbers do not.

**Every page carrying single-audit-derived figures repeats the threshold limitation in
visible body text**, above the table it qualifies. Not in a footer, not in a tooltip, not
collapsed behind a disclosure triangle. This is a correctness requirement, not a design
preference, and it is also the thing that will make a certified public accountant trust the
site instead of dismantling it.

**Titles and descriptions built from the data**, because they are what appears in results:

- `93.243 Substance Abuse and Mental Health Services Projects of Regional and National Significance: award history, median $305,161, 39% new entrants`
- `Federal pass-through funders in Ohio: who subawards federal money to Ohio nonprofits`

**Cross-link the portfolio.** Every organization page links to the same organization on the
sibling sites by Employer Identification Number:

- `funders.opengrants.io/funders/{ein}`
- `check.opengrants.io/{ein}`
- `desk.opengrants.io` and `answers.opengrants.io` from the global footer

Five sites that reference each other read as one authoritative body of work rather than
five orphans.

**Performance.** Edge-rendered and cached means sub-100ms for a cache hit. No client-side
framework, no hydration, no web font that blocks rendering. Inline the small stylesheet.

### `/llms.txt`

Served at the root, plain text, and it is cheap to write.

```
# awards.opengrants.io

Federal award history and pass-through funder analysis for United States
federal assistance programs.

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
https://funders.opengrants.io   private foundation funding graph
https://check.opengrants.io     nonprofit status and eligibility checks
https://answers.opengrants.io   reusable grant application content
https://desk.opengrants.io      grant workflow

## Not
Not an eligibility determination. Not legal, tax, or accounting advice.
```

### Sitemap

Unlike the sibling sites, the URL count here is small and bounded: roughly 2,300 active
Assistance Listings, about 130 agencies and sub-agencies, 56 states and territories, the
state-by-program combinations that actually have data, and the intermediaries above a
minimum evidence threshold. Tens of thousands of URLs, not millions.

Ship a sitemap index from day one anyway, with 50,000-URL chunks written to R2 by the
scheduled Worker, because retrofitting an index later is worse than having a one-chunk
index now. Include `lastmod` from the data vintage. Do not include a URL for a
state-by-program combination with no data; an empty page that ranks is worse than no page.

---

## Failure behavior

The site sits in front of two APIs it does not control. Requirements:

- **A page must never render an empty statistic.** If FAC times out, render the award
  history half and say plainly that pass-through data is temporarily unavailable, with the
  time of the last successful refresh.
- **Serve stale on upstream failure**, at any age, with the age shown. There is no age at
  which a stale figure is worse than an error page.
- **The OpenGrants enrichment is never in the critical path.** Fetch with a short timeout
  in `waitUntil` where possible, and omit the section entirely on failure. It never blocks
  a render and it never produces a visible error.
- **Upstream 429 backs off globally**, not per request, using a KV flag with a short time
  to live so one crawler cannot push us into a rate limit spiral against a free public API.
- **The cache is the load-bearing component.** A cold cache under crawler load is the
  realistic outage scenario. Warm the top pages on every vintage bump, and rate limit
  uncached renders per client.

---

## Deployment

```
awards/
├── src/
│   ├── index.ts              Hono app, routes
│   ├── render/               HTML templates, JSON-LD builders
│   ├── sources/              usaspending.ts, fac.ts, opengrants.ts
│   ├── analysis/             statistics, ported from the Python library
│   ├── cache.ts              KV plus Cache API, vintage keying
│   └── scheduled.ts          cron: vintage bump, warm, sitemap
├── wrangler.toml
└── package.json
```

`wrangler.toml` needs: the KV namespace binding, the R2 bucket binding, the cron trigger,
the custom domain, and `compatibility_date` pinned.

Secrets via `wrangler secret put FAC_API_KEY` and `wrangler secret put
OPENGRANTS_API_KEY`. Never in `wrangler.toml`, never in the repository.

### DNS

`awards.opengrants.io` is a subdomain of `opengrants.io`, whose DNS is managed externally
rather than at the registrar default. Adding the Workers custom domain requires a record in
whatever zone actually holds `opengrants.io`, plus the Cloudflare validation record.

**Confirm who holds that zone before the launch date is set.** It is the step most likely to
sit blocked for a day, and it is the only part of this deployment that cannot be fixed by
the person doing the work.

---

## What is deliberately not here

- No user accounts, no saved searches, no email alerts. The tool is the product; the site
  is the public face of the tool.
- No D1 database in v1. If a query pattern genuinely cannot be served from cached upstream
  responses, that is a signal to add a precomputed artifact in R2, not a database.
- No pre-rendering at build time. Everything renders at the edge.
- No paywall, no gate, no signup wall on any page.
