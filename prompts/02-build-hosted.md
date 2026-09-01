# Build prompt: `awards.opengrants.io`, the hosted companion

You are building the public web companion to the `precedent` command line tool: a
Cloudflare Worker that renders federal award history and federal pass-through funder
analysis as server-rendered pages that search engines and language models can read, cite,
and quote.

Read this whole file before writing code.

---

## 1. Mission

The repository does not rank. These pages do.

The strategic objective is category ownership. When a nonprofit executive director or a
grant consultant searches for "who passes through federal aging funds in Ohio" or
"93.243 past awardees", the answer should be a page on this site, and when a language model
is asked the same question, the page it quotes should be this one.

There are two page families and they matter for different reasons.

**Program pages** are the parity play. Several products show past awardees behind a
paywall. We show a defined statistical profile, free, with the method published.

**Pass-through pages** are the reason this site exists. Nothing else on the internet
currently answers "which organizations pass federal money down to nonprofits in this
state". Those pages should be the best pages on the site, and every editorial and
structured-data decision should favor them.

---

## 2. Read these first

1. `docs/program/HOSTING.md` in this repository. Binding. The platform decision, the caching
   strategy, and the search-engine and generative-engine requirements all come from there.
2. `docs/hosted/architecture.md` in this repository. The full design: request path, cache
   layers, vintage keying, page taxonomy, failure behavior, deployment layout.
3. `docs/research/data-sources.md`. The verified API reference. Do not re-derive it.
4. `prompts/01-build-core.md`, sections 9 and 10 in particular. **The statistics rendered
   here must be numerically identical to the ones the Python tool computes.** You are
   porting a specification, not reimplementing an idea.
5. `docs/program/CONVENTIONS.md`, for the required disclosure and the attribution rules.

If the Python library exists already, port from it directly and add a test that pins the
same values in both. If it does not exist yet, implement from the specification in
`prompts/01-build-core.md` section 9, and note in the pull request that the cross-check
test is pending.

---

## 3. Platform and stack

Non-negotiable, from `HOSTING.md`:

- **Cloudflare Workers.** Not Pages, not Netlify.
- **TypeScript strict mode**, `pnpm`, `biome` for lint and format, `vitest` for tests,
  **Hono** for HTTP.
- **Workers KV** for the upstream response cache and the vintage pointer.
- **R2** for sitemap chunks and any published dataset. R2 is never in the request path for
  a page render.
- **No D1 in v1.** `precedent` has no bulk dataset behind it, which makes it the lightest
  of the five sites. Do not invent a warehouse it does not need. If a query pattern cannot
  be served from cached upstream responses, the answer is a precomputed artifact in R2, not
  a database, and it is a decision to bring to a human.
- **No pre-rendering at build time.** Everything renders at the edge.
- Secrets `FAC_API_KEY` and `OPENGRANTS_API_KEY` via `wrangler secret put`. Never in
  `wrangler.toml`, never in the repository.

Repository layout:

```
awards/
├── src/
│   ├── index.ts              Hono app and routes
│   ├── scheduled.ts          cron handler
│   ├── cache.ts              KV + Cache API, vintage keying
│   ├── sources/
│   │   ├── usaspending.ts
│   │   ├── fac.ts
│   │   └── opengrants.ts
│   ├── analysis/
│   │   ├── profile.ts        port of prompts/01 section 9
│   │   ├── passthrough.ts    port of prompts/01 section 10
│   │   ├── identity.ts
│   │   └── coverage.ts
│   ├── render/
│   │   ├── layout.ts         shell, head, footer, nav
│   │   ├── program.ts
│   │   ├── passthrough.ts
│   │   ├── intermediary.ts
│   │   ├── agency.ts
│   │   ├── recipient.ts
│   │   ├── editorial.ts
│   │   └── jsonld.ts
│   ├── seo/
│   │   ├── sitemap.ts
│   │   ├── llms.ts
│   │   └── canonical.ts
│   └── styles.ts             one small inlined stylesheet
├── test/
├── wrangler.toml
└── package.json
```

---

## 4. Caching, and why the vintage key is the whole design

Two layers, doing different jobs. Get this right first, before any page looks good, because
a cold cache under crawler load is the realistic outage scenario for this site.

**Layer one: KV, upstream responses.**
Key: `u:{schemaVersion}:{source}:{sha256(canonicalRequest)}:{vintage}`.
Value: raw upstream JSON plus `fetchedAt`.
Time to live: USAspending 7 days, FAC 7 days, OpenGrants 24 hours.
This layer is what keeps the site from becoming a load problem for two free public APIs. It
is not optional and it is not a performance nicety.

**Layer two: Cache API, rendered HTML.**
Key: `https://awards.opengrants.io{path}?v={schemaVersion}-{vintage}`.

**Vintage keying, not expiry.** Per `HOSTING.md`, cache keys carry the data vintage so a
new upstream refresh invalidates everything cleanly rather than waiting for expiry.

- `meta:vintage` in KV holds a string like `fac2026-08-26-usa2026-08-29`.
- Every cache key on both layers includes it.
- Bumping it invalidates the entire site atomically, with no purge call and no deploy.
- `SCHEMA_VERSION` is an exported integer constant sitting immediately next to the
  statistics module, with a comment saying that changing a calculation without bumping it
  serves stale wrong numbers. That is the most likely serious bug on this site.

**Stale while revalidate.** Serve stale and refresh in the background with
`ctx.waitUntil()`. A four-day-old median is always better than a spinner, and a cold
program page can take twenty seconds of upstream calls.

**Scheduled Worker**, cron `0 9 * * 4`, Thursday 09:00 UTC, because FAC production
refreshes weekly and typically on Wednesdays:

1. Probe FAC for the newest `fac_accepted_date` and USAspending for its latest load.
2. If either moved, write a new `meta:vintage`.
3. Warm the top few hundred program pages and all 56 state pass-through pages, sequentially
   with backoff. Never in parallel; you are warming against free public APIs.
4. Regenerate the sitemap index and chunks into R2.

---

## 5. Page taxonomy

Full detail in `docs/hosted/architecture.md`. Build in this order.

### Phase A, program pages

| Route | Notes |
|---|---|
| `/programs/{aln}` | Canonical. Full award history profile |
| `/programs/{aln}/{state}` | Same program, one state's place of performance |
| `/programs/{aln}/recipients` | Full paginated awardee list |
| `/programs/{aln}/passthrough` | Who passes this program's money down, nationally |
| `/programs` | Browse and search index |

Canonical form is `/programs/93.243`. Permanently redirect `/programs/93243`,
`/programs/cfda/93.243`, `/cfda/93.243`, and title-slug variants such as
`/programs/93.243-substance-abuse-...`. **Never serve two URLs for one program.**

### Phase B, pass-through pages, the differentiated set

| Route | Notes |
|---|---|
| `/passthrough` | All 56 states and territories |
| `/passthrough/{state}` | **The flagship page.** Entities passing federal money to organizations in this state, ranked by distinct subrecipient count |
| `/passthrough/{state}/{aln}` | State by program |
| `/passthrough/{state}/{agency}` | State by agency |
| `/intermediaries/{slug}` | One pass-through entity: programs it passes down, subrecipient count, states reached, name variants clustered, source report identifiers, Employer Identification Number where known |

### Phase C, the rest

| Route | Notes |
|---|---|
| `/agencies`, `/agencies/{slug}`, `/agencies/{slug}/{subslug}` | Agency slugs from USAspending's own `agency_slug` field |
| `/recipients/{uei}` | One awardee, with sibling cross-links |
| `/` | What this is, the two questions, one live worked example. Not marketing copy |
| `/methodology` | Every statistic defined exactly as in `prompts/01-build-core.md` section 9, with worked arithmetic |
| `/coverage` | The threshold, the multi-listing distortion, the 2016 FAC floor, the 2007 USAspending floor. Linked from every page footer |
| `/data` | The published crosswalk from R2, if and when a human approves publishing it |
| `/about` | Egeria, OpenGrants sponsorship, repository, license |
| `/api/programs/{aln}.json` | Same computation as JSON. Documented, rate limited, CORS enabled. Cheap, because the renderer already holds the object |

---

## 6. Search engine and generative engine requirements

From `HOSTING.md`. These are acceptance criteria, not suggestions.

**Server-rendered HTML with real content in the initial response.** No client-side fetching
for primary content. Test it: `curl` the page, and the median, the new-entrant rate, and the
pass-through table must all be present in the HTML with JavaScript disabled. Interactivity
is progressive enhancement over content that already exists.

**`schema.org` structured data as JSON-LD in the head of every entity page.**

- Program pages: `GovernmentService` with `serviceOperator` as the awarding agency, plus a
  `Dataset` describing the derived statistics with `temporalCoverage`, `dateModified`,
  `creator`, and `isBasedOn` pointing at the USAspending API.
- Intermediary and recipient pages: `Organization` or `NGO` with **`taxID` set to the
  Employer Identification Number where known**, `address`, and `funder` relationships where
  the pass-through data establishes them. This is what makes a page machine-quotable, and it
  is the single highest-leverage markup on the site.
- All pages: `BreadcrumbList`.
- `FAQPage` only where the content genuinely is questions and answers. Do not use it as a
  markup trick.

**One canonical URL per entity**, with `<link rel="canonical">` on every page including the
canonical one, and 301 redirects from every variant.

**Every page states its source and vintage inline, in visible body text.** For example:
"Computed 2026-08-30 from the USAspending API. Single audit data from the Federal Audit
Clearinghouse, audit years 2016 through 2024, retrieved 2026-08-28." Pages that show their
work get cited. Pages that assert bare numbers do not.

**Every page carrying single-audit-derived figures repeats the threshold limitation in
visible body text, above the table it qualifies.** Not a footer, not a tooltip, not a
collapsed disclosure. This is a correctness requirement and it is also what will make a
certified public accountant trust the site rather than dismantle it. Write it once in
`analysis/coverage.ts` and render it from there, so it cannot drift between pages.

**The required disclosure** appears in the footer of every page, verbatim:

> This is informational only, derived from public data on the dates shown. It is not an
> eligibility determination, and not legal, tax, or accounting advice. Verify against the
> official source before relying on it.

**Titles and meta descriptions built from the data**, because that text is what appears in
results and in model summaries:

- `93.243 Substance Abuse and Mental Health Services Projects of Regional and National Significance: award history, median $305,161, 39% new entrants`
- `Federal pass-through funders in Ohio: who subawards federal money to Ohio nonprofits`
- `Ohio Department of Aging: federal programs it passes through to subrecipients`

Also emit Open Graph and Twitter card tags, and generate an OG image at the edge from the
headline statistics rather than shipping a static one.

**Cross-link the portfolio.** Every organization page links to the same Employer
Identification Number on the sibling sites:

- `https://funders.opengrants.io/funders/{ein}`
- `https://check.opengrants.io/{ein}`
- global footer links to `answers.opengrants.io` and `desk.opengrants.io`

Five sites that reference each other read as one authoritative body of work rather than five
orphans. Where the sibling site does not yet exist, omit the link rather than shipping a
dead one.

**Performance.** Cache hits under 100ms. No client-side framework, no hydration, no
render-blocking web font. Inline the stylesheet, which should be small enough to inline.

### `/llms.txt`

Serve the file in `docs/hosted/architecture.md` verbatim at the root, updating the vintage
line at render time. Keep the "Coverage limitation you must state if you quote this data"
section exactly as written; the entire point of it is that a model summarizing this site
carries the threshold caveat forward.

Also serve `/robots.txt`: allow all, point at `/sitemap.xml`. Do not block any crawler,
including model crawlers. Being quoted is the objective.

### Sitemap

URL count here is bounded and modest, unlike the sibling sites: roughly 2,300 active
Assistance Listings, about 130 agencies and sub-agencies, 56 states and territories, the
state-by-program combinations that actually have data, and intermediaries above a minimum
evidence threshold.

Even so, **ship a sitemap index with 50,000-URL chunks from day one**, generated by the
scheduled Worker into R2. Retrofitting an index later is worse than having a one-chunk index
now. Include `lastmod` from the data vintage.

**Do not emit a URL for a combination with no data.** An empty page that ranks is worse than
no page, and generating the full cross product of state by program would produce tens of
thousands of thin pages that would damage the site rather than help it. Only emit a
`/passthrough/{state}/{aln}` URL when that combination has at least one intermediary meeting
the minimum evidence threshold.

---

## 7. Rendering rules

- **The new-entrant rate is the first statistic on a program page**, above the median, in a
  visually distinct block. It is the number that changes a reader's decision.
- The distribution renders as a real chart in inline SVG, with a plain table beneath it for
  crawlers and for people who copy and paste. Never a chart alone.
- The coverage warning renders **above** any table it qualifies.
- Dollars with thousands separators and no cents. Rates to one decimal place.
- Never render an empty statistic. If a number cannot be computed, say what is missing and
  why, in a sentence.
- Enrichment from OpenGrants renders in a distinct block marked `live from OpenGrants`, and
  the OpenGrants API key is mentioned nowhere on the site.
- Print the raw pass-through name variants on intermediary pages. Showing the clustering is
  what makes it auditable, and auditability is the trust argument for the whole site.
- Every page links to the `precedent` repository and to `/methodology`.

---

## 8. Failure behavior

The site sits in front of two APIs it does not control.

- **A page must never render an empty statistic.** If FAC times out, render the award
  history half and state plainly that pass-through data is temporarily unavailable, with the
  time of the last successful refresh.
- **Serve stale on upstream failure, at any age, with the age shown.** There is no age at
  which a stale figure is worse than an error page.
- **The OpenGrants enrichment is never in the critical path.** Short timeout, omitted
  entirely on failure, never a visible error, never blocking a render.
- **Upstream 429 backs off globally**, using a KV flag with a short time to live, so one
  crawler cannot push the site into a rate-limit spiral against a free public API.
- **Rate limit uncached renders per client** so a crawler cannot force thousands of cold
  misses.

---

## 9. Milestones

**H0. Skeleton.** Worker, Hono, `wrangler.toml`, `biome`, `vitest`, a health route, deploy
to a `workers.dev` subdomain. Continuous integration green.

**H1. Cache and sources.** `cache.ts` with both layers and vintage keying, `sources/*.ts`
ported from the verified reference. A route that returns raw JSON for one program, correct
and cached. Verify the second request is a cache hit.

**H2. Program pages.** `analysis/profile.ts` producing numbers identical to the Python
library, `/programs/{aln}` rendered, canonical redirects, JSON-LD, inline source and vintage
line, disclosure footer.

**H3. Pass-through pages.** `analysis/passthrough.ts`, `analysis/coverage.ts`,
`/passthrough/{state}`, `/passthrough/{state}/{aln}`, `/intermediaries/{slug}`. The coverage
warning is present and above the fold on every one.

**H4. Search and generative engine surfaces.** `/llms.txt`, `/robots.txt`, sitemap index and
chunks into R2, Open Graph images, titles and descriptions built from data, sibling
cross-links.

**H5. Scheduled Worker.** Vintage probe and bump, cache warming, sitemap regeneration.

**H6. Editorial pages.** `/`, `/methodology`, `/coverage`, `/about`.

**H7. Launch.** DNS, custom domain, the checklist in section 11.

---

## 10. Acceptance criteria

- [ ] `curl https://awards.opengrants.io/programs/93.243` returns HTML containing the median
      and the new-entrant rate, with no JavaScript executed
- [ ] The statistics on `/programs/93.243` match `uvx precedent history 93.243 --json`
      exactly, and a test pins both
- [ ] Every entity page has valid JSON-LD, checked against Google's Rich Results Test and a
      schema validator
- [ ] Every page has exactly one `<link rel="canonical">`, and every variant URL 301s to it
- [ ] `/passthrough/oh` renders the threshold limitation in visible body text above the
      intermediary table
- [ ] No page, route, query parameter, or JSON endpoint omits the threshold limitation from
      pass-through data
- [ ] `/llms.txt` and `/robots.txt` serve correctly and the sitemap index resolves to chunks
      in R2
- [ ] No sitemap URL points at a page with no data
- [ ] Second request to any page is a cache hit; check the header
- [ ] Bumping `meta:vintage` invalidates every page with no deploy and no purge call
- [ ] The site renders correctly with `OPENGRANTS_API_KEY` unset
- [ ] The site renders the award-history half correctly with FAC returning 500
- [ ] Cache-hit response under 100ms from a nearby edge location
- [ ] Every organization page cross-links to the sibling sites by Employer Identification
      Number, or omits the link when the sibling has no such page
- [ ] The disclosure footer is on every page
- [ ] No secret in `wrangler.toml` or in the repository

---

## 11. Launch checklist

**Before the launch date is set:**

- [ ] **Confirm who holds DNS for `opengrants.io`.** It is managed externally rather than at
      the registrar default. This is the step most likely to sit blocked for a day, and it is
      the only part of this deployment that cannot be fixed by the person doing the work.

**Deployment:**

- [ ] KV namespace created and bound
- [ ] R2 bucket created and bound
- [ ] `FAC_API_KEY` and `OPENGRANTS_API_KEY` set with `wrangler secret put`
- [ ] Cron trigger `0 9 * * 4` configured and observed to fire once
- [ ] `compatibility_date` pinned in `wrangler.toml`
- [ ] Custom domain `awards.opengrants.io` attached, CNAME added in the external zone,
      Cloudflare validation record added
- [ ] HTTPS certificate issued and verified
- [ ] Workers Paid plan active, so the request volume is covered

**Content:**

- [ ] `/methodology` matches `prompts/01-build-core.md` section 9 exactly, statistic for
      statistic
- [ ] `/coverage` states the threshold, its change date, the 2016 FAC floor, the 2007
      USAspending floor, and the multi-listing distortion
- [ ] Credits and attribution present, matching `NOTICE`
- [ ] Sitemap submitted to Google Search Console and Bing Webmaster Tools
- [ ] Ten spot-checked pages across programs, states, agencies, and intermediaries, each
      verified by eye against the underlying source
- [ ] At least one intermediary page verified against an actual single audit filing pulled
      from fac.gov, confirming the name clustering and the amounts

**Monitoring:**

- [ ] Cloudflare analytics enabled
- [ ] An alert on the scheduled Worker failing, since a silent cron failure means the site
      quietly freezes at one vintage and nobody notices
- [ ] A log of upstream 429 responses, so a rate problem surfaces before it becomes a block

---

## 12. Stop and ask the human

1. **DNS.** Do not attempt a workaround if the zone is not reachable. Report and wait.
2. **Publishing the derived crosswalk** from Unique Entity Identifier to Employer
   Identification Number, or any other derived dataset. That is a redistribution decision
   under the Federal Audit Clearinghouse terms of use.
3. **Adding D1 or any persistent store.** If a page cannot be served from cached upstream
   responses, bring the case rather than adding a database.
4. **Statistics that disagree between the site and the Python tool.** They must be
   identical. A discrepancy is a bug in one of them and possibly a specification ambiguity
   that affects both.
5. **Any estimate, imputation, or smoothing to make single-audit coverage look complete.**
   The answer is almost certainly no.
6. **Sustained 429 or a block from either upstream.** Stop, report, do not work around it,
   do not add parallelism.
7. **Anything reading as an eligibility determination, a recommendation, or a prediction.**
8. **A competitor name or price appearing anywhere on the site.** All competitor references
   belong in `docs/research/competitive.md`, date-stamped and re-verified before use.
9. **Generating pages for combinations with no data** in order to grow the URL count. That
   is the single most effective way to make this site look like spam, and it needs an
   explicit human decision, which will be no.
