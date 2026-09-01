# Prior art

Who built the things this repository stands on, what already exists in this space, and what
we intend to give back. Verified 2026-08-30.

The rule for this program: contribute fixes upstream first, credit prominently, and never
re-implement something a community project already does well. This community's endorsement
is a distribution channel, and burning it in order to own a codebase would be a bad trade.

---

## The public infrastructure this tool depends on

### USAspending and `usaspending-api`

- Site: <https://www.usaspending.gov/>
- Source: <https://github.com/fedspendingtransparency/usaspending-api>
- License: works of the United States federal government; the repository is released into
  the public domain under CC0 1.0 Universal.

`precedent` would not be buildable without the API contract documents in
`usaspending_api/api_contracts/`. The `spending_by_award` contract in particular documents
a filter object that is genuinely difficult to reverse engineer from responses alone. That
this team writes and maintains machine-checkable contracts for a public API is unusual and
worth saying out loud.

### Federal Audit Clearinghouse and `GSA-TTS/FAC`

- Site: <https://www.fac.gov/>
- API docs: <https://www.fac.gov/api/>
- Source: <https://github.com/GSA-TTS/FAC>
- License: works of the United States federal government.

The FAC moved from the Census Bureau to GSA Technology Transformation Services. In doing so
the team put a real PostgREST API in front of single audit data, published a
[field dictionary](https://www.fac.gov/api/dictionary/), published a
[crosswalk from the legacy Census column names](https://www.fac.gov/api/differences/), wrote
a [results management guide](https://www.fac.gov/api/results-management/) that is candid
about performance limits, and made the key free with an email address.

The entire differentiated half of this repository exists because they did that. Before that
migration, Schedule of Expenditures of Federal Awards data was practically inaccessible to
anyone without a bulk download pipeline and a tolerance for legacy Census column names.

### api.data.gov

- Site: <https://api.data.gov/>

Key issuance and rate limiting in front of the FAC API, and a large share of other federal
APIs. Shared plumbing that nobody notices until it is gone.

---

## The Form 990 community, credited here because the sibling repo depends on it

`precedent` cross-references organizations to the sibling `funder-graph` repository by
Employer Identification Number. That repository is built almost entirely on community work.

### Nonprofit Open Data Collective

- <https://github.com/Nonprofit-Open-Data-Collective>
- **IRS E-file Master Concordance File** —
  <https://nonprofit-open-data-collective.github.io/irs-efile-master-concordance-file/>
- **IRS-Efile-Database** —
  <https://nonprofit-open-data-collective.github.io/IRS-Efile-Database/>
- Overview and issue tracker —
  <https://nonprofit-open-data-collective.github.io/overview/>

The Master Concordance File is the crosswalk that makes IRS Form 990 XML tractable across
hundreds of schema versions. It is the single most important upstream asset in this
five-repository program, and it is the reason a small team can do in weeks what the
commercial products in this category treat as their moat.

### GivingTuesday 990 Data Collaborative

- Tool repository: <https://990data.givingtuesday.org/tool-repository/>
- `form-990-xml-mapper` — <https://github.com/Giving-Tuesday/form-990-xml-mapper>
- `form-990-xml-parser` — <https://github.com/Giving-Tuesday/form-990-xml-parser>
- Form 990 Variable Dictionary and the 990 Data Mart Dictionary

### Others

- `open990odl` — <https://github.com/990consulting/open990odl>
- `propublica990` — <https://github.com/Punderthings/propublica990>
- ProPublica Nonprofit Explorer API —
  <https://projects.propublica.org/nonprofits/api>, terms at
  <https://www.propublica.org/about/propublica-data-terms-of-use>
- NBER Form 990 data — <https://www.nber.org/research/data/irs-form-990-data>

---

## Existing tooling for these two specific APIs

**USAspending.** A number of thin client wrappers exist across PyPI, CRAN, and npm, mostly
covering authentication-free request construction and pagination. None found at
verification models assistance-award recipient cohorts, computes new-entrant rates, or
treats the multi-Assistance-Listing problem. The gap is not the HTTP client, it is the
statistics.

**Federal Audit Clearinghouse.** Because the GSA API is comparatively new, published
tooling is thin. The examples in the FAC's own documentation are the main reference
implementation. Substantial single-audit analysis exists in the accounting and oversight
world, but it is oriented toward audit quality, findings, and cognizant agency workload
rather than toward finding pass-through funders on behalf of a potential subrecipient.

**Nobody found, commercial or open source, that treats SEFA pass-through relationships as a
prospecting dataset for small nonprofits.** That is the bet.

> **Task for the build agent:** re-run this search before the first public release. Search
> PyPI, GitHub, CRAN, and npm for `usaspending`, `spending_by_award`, `federal audit
> clearinghouse`, `single audit`, `SEFA`, and `passthrough`. If a project exists that does
> part of this well, use it, credit it here, and delete the corresponding hand-rolled code.
> Do not re-implement something that already works in order to own it.

---

## What we intend to contribute back

Recorded here in advance so that "we will contribute upstream" is a plan with items in it
rather than a sentiment.

### 1. A public Unique Entity Identifier to Employer Identification Number crosswalk

FAC `general` carries both `auditee_ein` and `auditee_uei` on the same row. USAspending
publishes Unique Entity Identifiers and no Employer Identification Numbers. IRS data is
keyed on Employer Identification Number. Nothing public bridges the two at scale.

Deriving the crosswalk from FAC and publishing it as a plain CSV plus Parquet, with
vintage, coverage statistics, and a clear statement that it only covers audited
organizations, would be immediately useful to anyone joining federal spending data to
nonprofit financial data. It costs us nothing to publish and it is the most obviously
valuable thing this repository can give away.

Home: alongside the hosted companion at awards.opengrants.io, mirrored to the repository
releases, and announced to the Nonprofit Open Data Collective and the GivingTuesday
community.

### 2. A pass-through entity name normalization table

`passthrough.passthrough_name` is free text. Building a curated alias table that maps raw
strings to canonical entities, with the observed variants and a `report_id` citation for
each, is unglamorous work that everybody analyzing this data has to redo.

We publish ours as `src/precedent/data/passthrough_aliases.yaml`, licensed Apache 2.0, in a
format that is trivially convertible to CSV, and we accept pull requests against it. If the
FAC team wants it upstream, better still.

### 3. Issues and fixes upstream

Filed against the appropriate repository as encountered, and listed here with links:

- **FAC:** documentation gaps found while implementing, particularly around whether
  PostgREST resource embedding is supported across endpoints and what the intended
  behaviour is when `is_direct` is null. *(To file.)*
- **FAC:** the semantics of `passthrough_id` are underspecified. In practice it holds state
  contract numbers, Unique Entity Identifiers, Employer Identification Numbers, and blanks.
  Documenting the observed distribution would help every consumer. *(To file.)*
- **usaspending-api:** the interaction between `program_numbers` filtering and awards
  carrying multiple Assistance Listings is not called out in the `spending_by_award`
  contract, and it produces silently inflated award-size statistics for the roughly one
  award in four that is affected. A documentation note would prevent a common analytic
  error. *(To file.)*

When any of these is filed, replace the *(To file.)* marker with the issue link and the
date. When a local workaround exists for one, the code carries a comment linking the issue
and stating the condition under which the workaround can be removed.

### 4. Fixtures as documentation

The committed test fixtures in `tests/fixtures/` are small real responses with a sidecar
recording the exact request and retrieval date. They are useful to anyone else building on
these APIs, and they are explicitly licensed for reuse under the repository license, with
the underlying data remaining public domain or subject to the FAC terms as applicable.

---

## Attribution requirements we place on ourselves

- `NOTICE` names every upstream project, its author, and its license.
- The README carries a Credits section above the fold, not buried at the bottom.
- Where we fix a bug or extend a mapping in upstream work, the pull request goes upstream
  first and the fact is noted in this file.
- Every hosted page states its source and vintage inline.
- We never re-implement something a community project already does well just to own it.
