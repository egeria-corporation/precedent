# Build prompt: `precedent` core library, CLI, and MCP server

You are building a Python package called `precedent` from an empty repository that
currently contains only documentation. Read this whole file before you write any code.
Everything you need to make decisions is in here or in the files it points you at. Where
something is genuinely undecidable, there is a "stop and ask the human" list at the bottom;
use it rather than guessing.

---

## 1. Mission

Two questions, one tool.

**Question one.** A grant consultant is deciding whether to advise a client to pursue a
federal program. They need the historical awardee profile: how big are the awards, how
spread out, who wins repeatedly, how many winners each year are organizations that had
never won it before, and where are they. That last number, the **new-entrant rate**, is the
single most decision-relevant statistic for a first-time applicant, and it is the headline
output of this tool, not a field buried in JSON.

**Question two, the differentiated one.** Most federal money that reaches small nonprofits
arrives as a **subaward** passed through a state agency, a university, a county, or a
larger nonprofit. That layer is invisible in every commercial grant research product,
because the data lives in the Schedule of Expenditures of Federal Awards inside single
audit filings. Given a state and a program area, this tool names the organizations that are
receiving federal money and passing it down, which is a prospect list nobody currently
sells.

The tool is thin. It is API composition over two well-documented federal endpoints plus a
statistics layer. There is no database, no ingest pipeline, no warehouse. Do not build one.

---

## 2. Read these first, in this order

1. `docs/program/CONVENTIONS.md` in this repository.
   Binding. Especially the two hard rules, the dual-interface requirement, the optional
   OpenGrants integration rules, the attribution requirements, and the required disclosure
   text.
2. `docs/research/data-sources.md` in this repository. This is the verified API reference.
   Every endpoint, request shape, field name, pagination convention, and rate-limit
   observation you need is in there, verified live on 2026-08-30. **Do not re-derive it
   from the upstream websites; trust this file, and where it says VERIFY, verify.**
3. `README.md` in this repository. It contains the two worked examples the finished tool
   must be able to produce, including real numbers you will check your implementation
   against.
4. `docs/NON-GOALS.md`. Read it so that you do not build something out of scope because it
   seemed helpful.
5. The USAspending `spending_by_award` API contract:
   <https://github.com/fedspendingtransparency/usaspending-api/blob/master/usaspending_api/api_contracts/contracts/v2/search/spending_by_award.md>
   **Fetch this and read it before writing the USAspending client.** The filter object is
   easy to get subtly wrong, the `fields` list is validated against the award types you
   requested, and a mismatch returns a terse 400 rather than a partial result.
6. The FAC data dictionary: <https://www.fac.gov/api/dictionary/> and the results
   management guide: <https://www.fac.gov/api/results-management/>.

---

## 3. Hard constraints

- **Python 3.11 or newer.** `uv` for dependency management. `ruff` for lint and format.
  `pytest` for tests. `pyproject.toml` with a console entry point. The package must be
  runnable as `uvx precedent ...` with no clone and no install ritual.
- **Dependencies stay small.** `httpx`, `typer` (or `click`), `rich` for terminal output,
  `pydantic` v2 for models, `mcp` for the server, `pyyaml` for the alias table. Justify
  anything beyond that in the pull request. No pandas, no numpy: the statistics here are
  computable from the standard library `statistics` module and the datasets are small
  enough that adding a numeric stack would be the largest thing in the dependency tree for
  no benefit.
- **`precedent history` must work with zero credentials.** This is hard rule one from
  CONVENTIONS.md. A first-time user must get a real result within 60 seconds of reading the
  README, with no account and no key. USAspending needs no key, so this is achievable and
  it is not negotiable.
- **`precedent passthrough` requires `FAC_API_KEY`.** That is unavoidable, because FAC
  requires a key. When the key is missing, fail with a message that states exactly where to
  get it, that it is free, and that it takes two minutes. Do not fail with a stack trace and
  do not fail with `KeyError`.
- **Core logic lives in the library.** The CLI and the MCP server are both thin adapters.
  Business logic in a command handler is a bug. Concrete test: if you cannot call a feature
  from the MCP server without copying code, it is in the wrong place.
- **Aggressive local caching is a requirement, not a nicety.** Both APIs are free public
  infrastructure and both are rate sensitive in practice even where limits are
  undocumented. See section 6.
- **Every output carries source and retrieval date.** No bare numbers, anywhere, in any
  format including `--json`.
- **Every pass-through output states the single audit threshold limitation.** No compact
  mode, no `--quiet`, no JSON shape omits it. See section 9.4.
- **The required disclosure appears in every command output footer**, verbatim:

  > This is informational only, derived from public data on the dates shown. It is not an
  > eligibility determination, and not legal, tax, or accounting advice. Verify against the
  > official source before relying on it.

- **No secrets in the repository, ever.** `.env` is gitignored, `.env.example` documents the
  variables, continuous integration uses repository secrets.
- **Never make an eligibility determination, predict an outcome, or give legal, tax, or
  accounting advice.** Report what happened. "This program takes new entrants" is a
  reportable fact. "Your client is a good fit" is not a sentence this tool may produce.

---

## 4. Module architecture

```
precedent/
├── pyproject.toml
├── src/precedent/
│   ├── __init__.py            __version__
│   ├── __main__.py            python -m precedent
│   ├── cli.py                 THIN. arg parsing, calls api, calls render
│   ├── mcp_server.py          THIN. tool definitions, calls api
│   ├── api.py                 the public library surface (see below)
│   ├── config.py              env, cache dir, TTLs, user agent, contact
│   ├── errors.py              typed exceptions with actionable messages
│   ├── models.py              pydantic models = the output schema
│   ├── render.py              human-readable terminal output
│   ├── cache.py               keyed disk cache with TTL and provenance
│   ├── http.py                shared client: retry, backoff, concurrency cap, UA
│   ├── sources/
│   │   ├── usaspending.py     typed client, no statistics
│   │   ├── fac.py             typed client, no statistics
│   │   └── opengrants.py      optional enrichment, always non-fatal
│   ├── analysis/
│   │   ├── identity.py        recipient identity resolution and name normalization
│   │   ├── profile.py         award history statistics
│   │   ├── passthrough.py     intermediary ranking
│   │   └── coverage.py        builds the coverage/limitation objects
│   ├── data/
│   │   └── passthrough_aliases.yaml
│   └── devtools/
│       └── capture_fixture.py capture a real response into tests/fixtures
└── tests/
    ├── fixtures/              real captured responses + .meta.json sidecars
    ├── test_usaspending.py
    ├── test_fac.py
    ├── test_profile.py        pinned statistical values
    ├── test_passthrough.py
    ├── test_identity.py
    ├── test_cache.py
    ├── test_cli.py
    └── test_mcp.py
```

`api.py` is the only thing the CLI and MCP server import from. It exposes roughly four
functions, each returning a pydantic model from `models.py`:

```python
def award_history(
    program: str,                    # "93.243"
    since_fy: int = ...,             # default: current FY - 5
    until_fy: int = ...,             # default: most recently completed FY
    lookback_years: int = 5,
    state: str | None = None,        # filter by place of performance
    enrich: bool = True,             # OpenGrants; silently skipped without a key
    use_cache: bool = True,
) -> AwardHistory: ...

def passthrough_finder(
    state: str,                      # "OH"
    program: str | None = None,      # "93.045"
    agency_prefix: str | None = None,# "93"
    since_audit_year: int = ...,     # default: current year - 6
    min_subrecipients: int = 1,
    use_cache: bool = True,
) -> PassthroughReport: ...

def recipient_profile(
    identifier: str,                 # UEI, EIN, or name
    use_cache: bool = True,
) -> RecipientProfile: ...

def find_program(query: str, limit: int = 10) -> list[ProgramRef]: ...
```

---

## 5. Data access layer one: USAspending

Everything in `docs/research/data-sources.md` section 1. Key points restated because
getting them wrong is the most likely failure:

- Root `https://api.usaspending.gov/`, no auth.
- Primary call: `POST /api/v2/search/spending_by_award/`.
- `award_type_codes` for assistance grants: `["02", "03", "04", "05"]`. Never mix contract
  codes into the same request.
- `program_numbers: ["93.243"]` is the Assistance Listing filter.
- `subawards: false` must be present.
- `time_period` with `date_type: "action_date"` selects awards with **any transaction** in
  the window. Fetch on a wide window, then bucket locally on **`Base Obligation Date`**.
  See section 8.1. This is the single most common way to produce a wrong new-entrant rate.
- Paginate with `last_record_unique_id` and `last_record_sort_value` from `page_metadata`,
  not with `page`. `limit` maxes at 100.
- Deduplicate on `generated_internal_id`.
- Before any large pull, call `POST /api/v2/search/spending_by_award_count/` with the same
  filters. If the grant count exceeds **20,000**, do not paginate: return a typed error
  telling the user to narrow the window or the state, and mention the bulk download
  endpoint. A program that large is not answerable with a record-by-record pull and
  pretending otherwise produces a ten-minute hang.
- Keyword and partial-number program resolution:
  `POST /api/v2/autocomplete/cfda/` with `{"search_text": ..., "limit": n}`.

Rate discipline: maximum 2 concurrent requests, sequential is fine and preferred,
exponential backoff with jitter on 429 and 5xx, at least 5 attempts, and a `User-Agent` of
the form `precedent/{version} (+https://github.com/egeria-corporation/precedent; {contact})`
where contact comes from `PRECEDENT_CONTACT` and falls back to the repository URL.

---

## 6. Data access layer two: Federal Audit Clearinghouse

Everything in `docs/research/data-sources.md` section 2. Key points:

- Request host `https://api.fac.gov`, header `X-Api-Key`.
- PostgREST. Filters are `?column=op.value`. Operators `eq`, `neq`, `gt`, `gte`, `lt`,
  `lte`, `like`, `ilike`, `in`, `is`. `&` is AND; OR needs `or=(...)`.
- **Always send `select=`.** Bandwidth is the main cost on this API.
- **Always send `order=`.** PostgREST does not guarantee stable ordering without it, so a
  paginated loop without an explicit order silently skips and duplicates rows. Use
  `order=report_id.asc,award_reference.asc` or another key unique enough for the query.
- `limit` and `offset` paginate. FAC caps results at 20,000 per request and recommends
  pages of about 5,000. **Every pagination loop needs a hard upper bound on iterations**
  so a bug cannot burn the whole key quota.
- Do not rely on PostgREST resource embedding across endpoints. Join client side by
  `report_id`, which is what FAC's own documentation recommends.
- Chunk `in.(...)` filters to roughly 100 identifiers per request.
- The Assistance Listing number is `federal_agency_prefix + "." + federal_award_extension`.
  There is no single column for it.
- Endpoints used: `/general`, `/federal_awards`, `/passthrough`, optionally
  `/notes_to_sefa`.
- Semantics you must not confuse, because the whole feature depends on the distinction:
  - `federal_awards.is_direct = false` means **this auditee received money through
    somebody**. The `/passthrough` rows for the same `(report_id, award_reference)` name
    who that was.
  - `federal_awards.is_passthrough_award = true` with `passthrough_amount > 0` means **this
    auditee passed money down to its own subrecipients**.
- Coverage: audit years 2016 forward. Production refreshes weekly, typically Wednesdays.

---

## 7. Caching design

Not optional. Both upstreams are free public infrastructure and both are rate sensitive.

- Location: `PRECEDENT_CACHE_DIR`, defaulting to the platform cache directory, for example
  `~/.cache/precedent` on Linux. Create with mode 0700.
- Storage: SQLite is fine and preferred over one file per key, since a large pull produces
  thousands of entries. One table: `key TEXT PRIMARY KEY, source TEXT, fetched_at TEXT,
  status INTEGER, body BLOB`. Body compressed with zlib.
- Key: `sha256(source + "\n" + method + "\n" + path + "\n" + canonical_params_or_body)`
  where canonicalization is `json.dumps(obj, sort_keys=True, separators=(",", ":"))`.
- Time to live: USAspending 168 hours, FAC 168 hours, OpenGrants 24 hours. Overridable by
  the environment variables in `.env.example`.
- **Provenance is the point, not just speed.** Every cached entry stores `fetched_at`, and
  every computed result carries the **oldest** `fetched_at` among the responses that fed it
  as its `retrieved` date. An output that says "retrieved today" when it was assembled from
  a five-day-old cache is a lie, and this tool's entire value proposition is that it does
  not lie about provenance.
- `--no-cache` bypasses reads and still writes.
- `precedent cache info` prints path, entry count, total size, oldest and newest entry.
  `precedent cache clear` empties it, with a confirmation prompt unless `--yes`.

---

## 8. Recipient identity

Getting this wrong corrupts the repeat-winner and new-entrant rates, which are the two
statistics people will actually quote. Implement it in `analysis/identity.py` and test it
directly.

Resolution order for a USAspending award record:

1. `Recipient UEI` if present and 12 characters. Identity is `("uei", value.upper())`.
2. `recipient_id` if present. **Strip the trailing level suffix** (`-C`, `-R`, `-P`) before
   using it, because the same organization appears at different levels with different
   values. Identity is `("rid", stripped)`.
3. Normalized name. Identity is `("name", normalized)`.

Name normalization, applied consistently everywhere including the pass-through clustering:

- Uppercase, Unicode NFKD, strip accents.
- Replace `&` with ` AND `.
- Remove all characters that are not A-Z, 0-9, or space.
- Collapse runs of whitespace, strip.
- Remove a trailing legal suffix from this list, repeatedly until none matches:
  `INC`, `INCORPORATED`, `LLC`, `LLP`, `LP`, `CORP`, `CORPORATION`, `CO`, `COMPANY`,
  `LTD`, `LIMITED`, `PC`, `PA`, `THE`.
- Expand a small, committed abbreviation table applied to whole tokens only:
  `DEPT`→`DEPARTMENT`, `UNIV`→`UNIVERSITY`, `ASSN`/`ASSOC`→`ASSOCIATION`,
  `NATL`→`NATIONAL`, `INTL`→`INTERNATIONAL`, `SVCS`/`SVC`→`SERVICES`, `CTR`→`CENTER`,
  `CNTY`→`COUNTY`, `ST`→`STATE` only when it is the first token, `US`→`UNITED STATES`,
  `AAA`→`AREA AGENCY ON AGING`.
- Remove a leading `THE`.

The report must expose how identity was resolved, because a program resolved mostly by name
has weaker statistics than one resolved by Unique Entity Identifier:

```python
identity_resolution = {"uei": 0.94, "recipient_id": 0.04, "name": 0.02}
```

When the name tier exceeds 10% of records, add a warning to the report's `caveats` list.

---

## 9. The statistical specification

This section is the part where ambiguity produces wrong numbers. Implement it exactly.
Where a convention is stated, do not substitute an equivalent-looking one.

### 9.1 Building the award universe

1. Determine the window: fiscal years `since_fy` through `until_fy` inclusive. A federal
   fiscal year `FY` runs from October 1 of `FY - 1` to September 30 of `FY`.
2. Determine the lookback: the `lookback_years` fiscal years immediately preceding
   `since_fy`. Default 5. So for FY2020 to FY2024 with the default, the lookback is FY2015
   to FY2019.
3. Fetch once, on the union of both ranges, using `date_type: "action_date"` from
   `date(since_fy - lookback_years - 1, 10, 1)` to `date(until_fy, 9, 30)`. One pull, not
   two, because an award straddles both.
4. Deduplicate on `generated_internal_id`.
5. Compute each award's fiscal year from **`Base Obligation Date`**:
   `fy = year + 1 if month >= 10 else year`. If `Base Obligation Date` is null, fall back to
   `Start Date`; if that is also null, drop the award and count it in
   `excluded.missing_date`.
6. `window_awards` = awards whose computed fiscal year is in the window.
   `lookback_awards` = awards whose computed fiscal year is in the lookback.
7. From `window_awards`, exclude awards with `Award Amount` null or less than or equal to
   zero from all **amount** statistics, and count them in `excluded.nonpositive_amount`.
   They still count for recipient identity, because winning a zero-dollar-net award still
   means the organization was a recipient. Report both counts.

### 9.2 Award size statistics

Computed over **awards**, not recipients. All amounts are `Award Amount`, which is total
obligation over the life of the award, and the output must say so.

- `median`: `statistics.median(amounts)`. For even n this is the mean of the two middle
  values. Round to whole dollars for display, keep full precision in JSON.
- `percentiles`: p10, p25, p50, p75, p90 from
  `statistics.quantiles(amounts, n=100, method="inclusive")`. **Pin `method="inclusive"`
  explicitly.** The default is `"exclusive"` and it gives different answers on small
  samples, and "different answers on small samples" is exactly the situation for a niche
  program. `p50` from this call must equal `median` to within a cent; assert it in a test.
- `mean`: report it, and label it as skewed whenever `mean > 2 * median`, which is the
  normal case for federal programs.
- `minimum`, `maximum`, `count`, `total`.
- **Distribution buckets are fixed, not data-derived**, so that two programs are
  comparable. Half-open intervals `[lo, hi)`:

  | Bucket | Range |
  |---|---|
  | `under_100k` | `[0, 100_000)` |
  | `100k_250k` | `[100_000, 250_000)` |
  | `250k_500k` | `[250_000, 500_000)` |
  | `500k_1m` | `[500_000, 1_000_000)` |
  | `1m_5m` | `[1_000_000, 5_000_000)` |
  | `5m_plus` | `[5_000_000, inf)` |

  Each bucket reports count, share of awards, and share of dollars. Shares are of the
  amount-eligible awards, and they must sum to 1.0 within floating-point tolerance. Assert
  that in a test.

### 9.3 The four headline rates

Let `A` = the set of distinct recipient identities in `window_awards`, and `B` = the set of
distinct recipient identities in `lookback_awards`.

**New-entrant rate.** The headline.

```
new_entrants      = A - B
new_entrant_rate  = len(new_entrants) / len(A)
```

Stated in prose in the output as: "N of M recipients in {window} had won no award under
this program in the {lookback} lookback window."

Left-censoring: USAspending search only reaches back to `2007-10-01`. If the lookback start
is earlier than that, the lookback is truncated, some recipients look new when they are
not, and the rate is an **upper bound**. Set
`new_entrant_rate_is_upper_bound = True`, add a caveat, and say so in the rendered output.
Do the same when `lookback_awards` is empty, which usually means the program did not exist
yet.

**Repeat-winner rate.** Count distinct awards per identity within the window only.

```
repeat_winners     = {i for i in A if award_count_in_window[i] >= 2}
repeat_winner_rate = len(repeat_winners) / len(A)
```

Distinct awards means distinct `generated_internal_id`. A modification is not a second
award. Do not use the lookback here; this is a within-window measure and mixing the two
produces a number nobody can interpret.

**Concentration.** Share of window dollars held by the top 10 identities by summed amount.
Ties broken by identity string, ascending, so the result is deterministic.

**Multi-listing share.** Share of `window_awards` whose `Assistance Listings` array has
length greater than one. When it exceeds 10%, add a caveat stating that award-size
percentiles are an upper bound because obligation amounts include money from other
programs.

### 9.4 Geography and recipients

- `states_covered`: count of distinct non-null `Place of Performance State Code` in the
  window.
- `top_states`: by award count and by dollars, top 10 each.
- `top_recipients_by_count` and `top_recipients_by_dollars`: top 10 each, with display
  name, award count, total dollars, and Unique Entity Identifier where known. Display name
  is the most frequent raw `Recipient Name` for that identity, not the normalized form,
  because a consultant needs to recognize it.

### 9.5 Recipient scale

Do **not** claim to report "typical recipient budget size". USAspending has no revenue
field and inventing one would be exactly the kind of confident wrongness this tool exists
to avoid.

Report instead, and label precisely:

- `median_awardee_federal_expenditures`: for the subset of window recipients whose Unique
  Entity Identifier is found in FAC `general`, the median of `total_amount_expended` from
  their most recent audit. Requires `FAC_API_KEY`; omitted entirely without one.
- `federal_expenditures_match_rate`: what share of window recipients that number covers.
- The label in the rendered output is
  `Median total federal expenditures of awardees that file a single audit (N of M matched)`.
  It is not "budget", it is not "revenue", and it is not "typical".

If `OPENGRANTS_API_KEY` is present, the profile may also carry organization-level context
from the OpenGrants funders endpoint, marked `— live from OpenGrants`.

---

## 10. The pass-through specification

Implement in `analysis/passthrough.py`. Two evidence streams, computed separately, merged
for display, never silently blended into one number.

### 10.1 Demand side: who do organizations in this state say funds them?

1. `GET /general` filtered by `auditee_state=eq.{STATE}` and
   `audit_year=gte.{since_audit_year}`, selecting `report_id, auditee_name, auditee_ein,
   auditee_uei, auditee_city, entity_type, total_amount_expended, fy_start_date,
   fy_end_date, dollar_threshold`, ordered by `report_id.asc`, paginated.
2. For `report_id` batches of ~100: `GET /federal_awards` with
   `report_id=in.(...)`, `is_direct=is.false`, and, when a program filter is given,
   `federal_agency_prefix=eq.{prefix}&federal_award_extension=eq.{ext}`. Select
   `report_id, award_reference, amount_expended, federal_program_name, cluster_name,
   federal_agency_prefix, federal_award_extension`.
3. For the same batches: `GET /passthrough` with `report_id=in.(...)`, selecting
   `report_id, award_reference, passthrough_name, passthrough_id`.
4. Join on `(report_id, award_reference)`. A `federal_awards` row with `is_direct = false`
   and no matching `passthrough` row is a **reporting gap**: count it in
   `unattributed_indirect_lines` and report the count. Do not drop it silently.
5. Cluster `passthrough_name` (section 10.3) and group.

Per cluster, report:

- `subrecipient_count`: **distinct `report_id` values**, which is distinct audits, and
  since one auditee files one audit per year, deduplicate further to distinct
  `auditee_ein` so that an organization audited five years running counts once. Report the
  distinct-organization figure as the headline and the distinct-audit figure as
  `observation_count`.
- `amount_expended_total`: sum of `amount_expended` on the joined lines.
- `programs`: the distinct Assistance Listing numbers seen, with counts.
- `name_variants`: every raw `passthrough_name` string merged into this cluster, with
  counts and an example `report_id` for each. Always in the JSON; shown in the terminal only
  with `--show-name-variants`.
- `subrecipients`: the auditee names, cities, and Employer Identification Numbers, capped
  at 25 in terminal output and complete in JSON.

**Rank by `subrecipient_count` descending, then `amount_expended_total` descending.** This
is a deliberate choice and it should carry a comment saying why: dollars tell you which
intermediary is biggest, subrecipient count tells you which one actually makes subawards to
organizations like the client, and that is the question being asked.

### 10.2 Supply side: who in this state reports passing money down?

1. Same `/general` query, same batches.
2. `GET /federal_awards` with `report_id=in.(...)`, `is_passthrough_award=is.true`,
   `passthrough_amount=gt.0`, plus the program filter if given.
3. Join back to `general` on `report_id`.

Per entity, report canonical name, city, `entity_type`, Employer Identification Number,
Unique Entity Identifier, total `passthrough_amount`, total `amount_expended`, the programs
involved, and audit years covered.

This side yields a real Employer Identification Number and a real state, which the demand
side does not. Use it to attach identifiers to demand-side clusters where the normalized
names match and the state agrees. Record how the match was made in
`identifier_source: "supply_side_match" | "passthrough_id" | "none"` so a reader can judge
it. Never present a name match as an identity match.

### 10.3 Clustering pass-through names

`passthrough_name` is free text typed by an auditee. Clustering is required and it will
never be perfect, so it must be auditable.

1. Normalize with the same function as section 8.
2. Apply `src/precedent/data/passthrough_aliases.yaml`, a committed table:

   ```yaml
   - canonical: "OHIO DEPARTMENT OF AGING"
     state: OH
     entity_type: state_agency
     ein: null
     aliases:
       - "OHIO DEPT OF AGING"
       - "STATE OF OHIO DEPARTMENT OF AGING"
       - "ODA"
   ```

3. For names not in the table, cluster within a state by exact normalized match only.
   **Do not fuzzy match by default.** Offer `--fuzzy` which uses a token-set ratio at a
   threshold of 92 and which always lists what it merged. A wrongly merged entity produces a
   fact that is not true, which is worse than a split entity producing an undercount.
4. **Never merge across states.**
5. Two-letter and three-letter aliases like `ODA` are only ever resolved through the
   committed table, never by any automatic rule.

### 10.4 The coverage object, required on every pass-through result

`analysis/coverage.py` builds this and every rendered surface and every JSON payload
carries it. There is no flag that removes it.

```python
class PassthroughCoverage(BaseModel):
    threshold_note: str          # the paragraph below, verbatim
    threshold_old: int = 750_000
    threshold_new: int = 1_000_000
    threshold_effective: str = "fiscal years beginning on or after 2024-10-01"
    audits_scanned: int
    audit_years: list[int]
    state: str
    counts_are_floors: bool = True
    unattributed_indirect_lines: int
    fac_earliest_audit_year: int = 2016
    fac_retrieved: str           # ISO date, from cache provenance
    fac_data_vintage_note: str   # "FAC production refreshes weekly, typically Wednesdays"
```

`threshold_note` text:

> Single audits are only filed by organizations that expend at or above the federal single
> audit threshold in a fiscal year. That threshold was $750,000 and rose to $1,000,000 for
> fiscal years beginning on or after 2024-10-01. Organizations below the threshold file
> nothing, so they are absent from this data entirely, not counted as zero. This list is
> therefore skewed toward larger recipients and larger intermediaries, and every
> subrecipient count is a floor rather than a total.

Additional rules:

- Read the applicable threshold from `general.dollar_threshold` per audit rather than
  inferring it from the fiscal year, and report the distinct values seen.
- Exclude or label loan programs (`is_loan = true`), because loan balances distort
  expenditure totals badly. Default: exclude from dollar totals, count separately, say so.
- Describe every count as a floor in the rendered text, not only in the coverage block.

---

## 11. Output schema

Pydantic v2 models in `models.py`. `--json` emits `model_dump_json` of the top-level model.
This is the contract the hosted companion and the MCP server both consume, so treat a
change to it as a breaking change.

```jsonc
// AwardHistory
{
  "schema_version": 1,
  "kind": "award_history",
  "program": {
    "number": "93.243",
    "title": "Substance Abuse and Mental Health Services Projects of Regional and National Significance",
    "agency": "Department of Health and Human Services",
    "sub_agency": "Substance Abuse and Mental Health Services Administration"
  },
  "window": {"since_fy": 2020, "until_fy": 2024},
  "lookback": {"since_fy": 2015, "until_fy": 2019, "truncated": false},
  "totals": {
    "awards": 1058,
    "distinct_recipients": 726,
    "obligated": 3570889654
  },
  "headline": {
    "new_entrant_rate": 0.391,
    "new_entrants": 284,
    "new_entrant_rate_is_upper_bound": false
  },
  "award_size": {
    "min": 397, "p10": 94452, "p25": 186013, "median": 305161,
    "p75": 854761, "p90": 2615811, "max": 205604128,
    "mean": 3375132, "mean_is_skewed": true
  },
  "distribution": [
    {"bucket": "under_100k", "label": "under $100k", "count": 153,
     "share_of_awards": 0.145, "share_of_dollars": 0.003}
  ],
  "repeat_winners": {"count": 208, "rate": 0.287},
  "concentration": {"top_10_share_of_dollars": 0.481},
  "geography": {
    "states_covered": 57,
    "top_states_by_count": [{"state": "CA", "awards": 85, "dollars": 0}]
  },
  "top_recipients_by_count": [
    {"name": "GREAT PLAINS TRIBAL LEADERS HEALTH BOARD", "uei": null,
     "awards": 7, "dollars": 7634611}
  ],
  "top_recipients_by_dollars": [],
  "recipient_scale": {
    "median_awardee_federal_expenditures": null,
    "match_rate": null,
    "label": "Median total federal expenditures of awardees that file a single audit"
  },
  "identity_resolution": {"uei": 0.94, "recipient_id": 0.04, "name": 0.02},
  "excluded": {"missing_date": 0, "nonpositive_amount": 3},
  "caveats": [
    "256 of 1,058 awards (24.2%) report more than one Assistance Listing, so amounts include money from other programs. Award-size percentiles are an upper bound."
  ],
  "enrichment": {
    "source": "opengrants",
    "open_opportunities": [],
    "available": false
  },
  "provenance": {
    "sources": [
      {"name": "USAspending",
       "endpoint": "POST /api/v2/search/spending_by_award",
       "retrieved": "2026-08-30",
       "note": "Award amounts are total obligations across the life of each award."}
    ]
  },
  "disclosure": "This is informational only, derived from public data on the dates shown. It is not an eligibility determination, and not legal, tax, or accounting advice. Verify against the official source before relying on it."
}
```

```jsonc
// PassthroughReport
{
  "schema_version": 1,
  "kind": "passthrough",
  "query": {"state": "OH", "program": "93.045", "since_audit_year": 2019},
  "program": {"number": "93.045", "title": "Special Programs for the Aging, Title III, Part C, Nutrition Services"},
  "intermediaries": [
    {
      "canonical_name": "Ohio Department of Aging",
      "entity_type": "state_agency",
      "state": "OH",
      "city": null,
      "ein": null,
      "uei": null,
      "identifier_source": "none",
      "subrecipient_count": 11,
      "observation_count": 26,
      "amount_expended_total": 41200000,
      "passthrough_amount_reported": 39800000,
      "programs": [{"aln": "93.045", "lines": 26}],
      "subrecipients": [
        {"name": "...", "ein": "...", "city": "...", "audit_years": [2021, 2022]}
      ],
      "name_variants": [
        {"raw": "OHIO DEPT OF AGING", "count": 4, "example_report_id": "2022-06-GSAFAC-0000012345"}
      ],
      "evidence": ["demand_side", "supply_side"],
      "sibling_links": {"funder_graph": null, "grantcheck": null}
    }
  ],
  "supply_side_only": [],
  "coverage": { /* PassthroughCoverage, see 10.4 */ },
  "provenance": {"sources": [{"name": "Federal Audit Clearinghouse", "endpoint": "GET /general, /federal_awards, /passthrough", "retrieved": "2026-08-30"}]},
  "disclosure": "..."
}
```

---

## 12. Command line interface

Human-readable by default with `rich`, `--json` for machines, on every command. No colors
when not a terminal. No progress spinner in `--json` mode.

```
precedent history 93.243 [--since FY2020] [--until FY2024] [--lookback 5]
                         [--state OH] [--no-enrich] [--json] [--no-cache]
precedent history --agency "Department of Education" --keyword "afterschool"
precedent passthrough --state OH [--program 93.045] [--agency-prefix 93]
                      [--since-audit-year 2019] [--min-subrecipients 2]
                      [--show-name-variants] [--fuzzy] [--json]
precedent recipient <UEI|EIN|name> [--json]
precedent programs --search "opioid treatment" [--json]
precedent cache (info | clear [--yes])
precedent mcp
precedent --version
```

Rendering rules:

- The **new-entrant rate is the first statistic on the screen** for `history`, above the
  median, in a visually distinct block. It is the number that changes the advice.
- Distribution renders as a horizontal bar chart in plain ASCII so it survives copy and
  paste into an email, which is what a consultant will do with it.
- Dollars with thousands separators and no cents.
- Rates as one decimal place.
- The coverage warning on `passthrough` renders **above** the intermediary table.
- Every command's footer prints the source line, the retrieval date, and the disclosure.
- Enriched lines carry `— live from OpenGrants`.
- The optional OpenGrants key is mentioned **only in the README**, never in command output.
  No nag, ever.

Exit codes: `0` success, `1` no results, `2` bad input, `3` upstream unavailable after
retries, `4` missing required credential. Every non-zero exit prints what to do next.

---

## 13. MCP server

`precedent mcp` runs an MCP server over stdio. Tools, each a thin call into `api.py`
returning the same JSON as `--json`:

| Tool | Arguments |
|---|---|
| `award_history` | `program`, `since_fy?`, `until_fy?`, `lookback_years?`, `state?` |
| `passthrough_finder` | `state`, `program?`, `agency_prefix?`, `since_audit_year?`, `min_subrecipients?` |
| `recipient_profile` | `identifier` |
| `find_program` | `query`, `limit?` |

Each tool description must state, in the description text the model sees, that pass-through
counts are floors because of the single audit threshold, and that no output is an
eligibility determination. An agent that reads only the tool description must still know the
limitation.

---

## 14. Testing

Fixture-based, against real captured responses. Mocked-shape tests do not catch schema
drift, and schema drift is the failure mode that actually matters here.

- `tests/fixtures/` holds real responses trimmed to the smallest set that exercises the
  path, each with a `.meta.json` sidecar recording the exact request, the endpoint, and the
  retrieval date.
- `devtools/capture_fixture.py` captures new ones.
- Live network tests sit behind `-m live` and are excluded from the default run and from
  continuous integration. Continuous integration must pass with no `FAC_API_KEY`.
- **Statistical tests pin exact values against fixtures.** Any change to a computed value
  must be a deliberate, reviewed change.
- Required specific tests:
  - `p50` from the percentile call equals `median` to within a cent
  - bucket shares sum to 1.0
  - identity resolution strips `-C`/`-R`/`-P` suffixes correctly
  - a recipient present in the lookback is not counted as a new entrant
  - an award appearing twice in paginated results is deduplicated on
    `generated_internal_id`
  - the truncated-lookback flag fires when the lookback crosses 2007-10-01
  - a `federal_awards` row with `is_direct = false` and no `passthrough` match is counted in
    `unattributed_indirect_lines` rather than dropped
  - pass-through name clustering never merges two states
  - the coverage object is present in every pass-through JSON payload, including with every
    flag combination
  - the disclosure string appears in every rendered footer and in every JSON payload
  - the CLI exits 4 with an actionable message when `passthrough` is run without a key

Continuous integration: GitHub Actions, `ruff check`, `ruff format --check`, `pytest`, on
push and pull request, on Python 3.11 and 3.12. Badge in the README already points at
`.github/workflows/ci.yml`, so name the workflow file that.

---

## 15. Milestones

Commit at each one. Each is independently reviewable.

**M0. Skeleton.** `pyproject.toml` with the console entry point, package layout, `ruff`
configured, `pytest` running, continuous integration green, `precedent --version` works via
`uvx`. Also add the files CONVENTIONS.md requires that are not yet present: `LICENSE`
(Apache 2.0 full text), `CODE_OF_CONDUCT.md`, `SECURITY.md`, `.gitignore` with `.env`,
`CHANGELOG.md`, `.github/workflows/ci.yml`.

**M1. HTTP and cache.** `http.py` with retry, backoff, concurrency cap, and User-Agent.
`cache.py` with SQLite storage, keying, time to live, and provenance. `precedent cache
info` and `clear` work. Tests for cache hit, miss, expiry, and provenance date.

**M2. USAspending client.** `sources/usaspending.py`, keyset pagination, count pre-check,
program autocomplete. `precedent programs --search "opioid"` returns real results. Fixtures
captured and committed.

**M3. Award history.** `analysis/identity.py`, `analysis/profile.py`, `models.py`,
`render.py`, `precedent history`. **Verify against section 16 before moving on.** This is
the gate.

**M4. FAC client.** `sources/fac.py`, PostgREST helpers, chunked `in.(...)`, bounded
pagination loops, fixtures captured and committed.

**M5. Pass-through finder.** `analysis/passthrough.py`, `analysis/coverage.py`, the alias
table seeded with the Ohio aging entities from the README example, `precedent passthrough`.

**M6. MCP server.** `mcp_server.py`, four tools, stdio transport, tested against fixtures.

**M7. Enrichment and polish.** `sources/opengrants.py` wrapped so any failure degrades
silently, `precedent recipient`, `CHANGELOG.md` entry, `README.md` reconciled with actual
output, version 0.1.0.

**Optional M8, only if M0 through M7 are done and green.** A `--bulk` mode for
`passthrough` that reads FAC's public CSV downloads instead of the API, so the pass-through
half works with no key at all. This would restore full compliance with hard rule one. Do
not start it early.

---

## 16. Verification: check your work against real numbers

Do not declare M3 complete until this passes. These figures were computed from the live
USAspending API on **2026-08-30** using exactly the method specified in section 9. If your
implementation does not reproduce them, your implementation is wrong, not the numbers.

**Setup.** Assistance Listing `93.243`. Pull `POST /api/v2/search/spending_by_award/` with
`award_type_codes: ["02","03","04","05"]`, `program_numbers: ["93.243"]`, `time_period`
`2014-10-01` to `2025-09-30` with `date_type: "action_date"`, keyset pagination at
`limit: 100`, sorted by `Award Amount` descending. That returns **7,683 award records**.

Bucket on `Base Obligation Date`. Window FY2020 through FY2024. Lookback FY2015 through
FY2019. Identity: Unique Entity Identifier first, normalized name as fallback.

| Statistic | Expected |
|---|---|
| Awards in window | 1,058 |
| Distinct recipients in window | 726 |
| Total obligated in window | $3,570,889,654 |
| Minimum award | $397 |
| 10th percentile | $94,452 |
| 25th percentile | $186,013 |
| **Median** | **$305,161** |
| 75th percentile | $854,761 |
| 90th percentile | $2,615,811 |
| Maximum award | $205,604,128 |
| Mean | $3,375,132 |
| Bucket: under $100k | 153 awards, 14.5% |
| Bucket: $100k to $250k | 287 awards, 27.1% |
| Bucket: $250k to $500k | 221 awards, 20.9% |
| Bucket: $500k to $1M | 164 awards, 15.5% |
| Bucket: $1M to $5M | 162 awards, 15.3% |
| Bucket: $5M and over | 71 awards, 6.7% |
| **New-entrant rate** | **39.1%, 284 of 726** |
| Repeat-winner rate | 28.7%, 208 of 726 |
| Top 10 recipients' share of dollars | 48.1% |
| Distinct place-of-performance state codes | 57 |
| Top states by award count | CA 85, AK 79, OK 67, NY 58, WI 40, MI 39, MT 31, SD 30 |
| Awards with more than one Assistance Listing | 256, 24.2% |

Percentiles above are `statistics.quantiles(amounts, n=100, method="inclusive")`. If you
leave the method at its default `"exclusive"` you will get $185,956 for p25 and $2,626,594
for p90 from this same data. Both are defensible statistics and only one of them is the
specification, which is exactly why section 9.2 pins it.

**Tolerance.** USAspending restates prior-period records, so exact reproduction months later
is not guaranteed. Counts within 2% and the median within 5% is a pass. A result off by more
than that is a bug in your bucketing or your identity resolution, not drift, and the two
most likely causes are (a) you bucketed on transaction window membership instead of
`Base Obligation Date`, or (b) you did not strip the `-C`/`-R`/`-P` suffix from
`recipient_id`.

**Also spot-check by hand.** Take the top result, award `H79TI081686` to the California
Department of Health Care Services, Unique Entity Identifier `JE73CDQUAPA7`, with `Award
Amount` 175,885,269.7 and `Base Obligation Date` 2018-09-19. Confirm your code assigns it
to FY2018 and therefore **excludes** it from the FY2020 to FY2024 window even though it
appears in the API response for that action-date window. If your window includes it, you
have implemented section 9.1 step 5 wrong, and that single error will inflate every dollar
figure you report.

Open <https://www.usaspending.gov/award/ASST_NON_H79TI081686_075> and check the recipient,
the amount, and the dates against what your code parsed. Do this once, by eye, before
trusting anything downstream.

**For the pass-through half**, once you have a `FAC_API_KEY`, spot-check
`precedent passthrough --state OH --program 93.045` against the fac.gov Advanced Search
interface for two named auditees: pull one Ohio auditee's actual single audit PDF from
fac.gov, find the 93.045 line on its Schedule of Expenditures of Federal Awards, and
confirm that the pass-through entity name your tool clustered matches the name printed on
the schedule and that `amount_expended` matches. One hand-verified filing is worth more
than any amount of unit testing here, because it validates the semantic model and not just
the parsing.

---

## 17. Stop and ask the human

Do not guess on any of these. Stop, state what you found, state the options, and wait.

1. **The FAC API key.** You cannot get one; it requires an email signup. Build everything
   behind it against fixtures, and ask for a key when you reach M4. If you cannot get one,
   stop at M4 rather than shipping untested FAC code.
2. **Verification numbers do not reproduce.** If section 16 fails by more than the stated
   tolerance after you have checked bucketing and identity resolution, stop. Report what you
   got, what you expected, and your diagnosis. Do not adjust the specification to match your
   output.
3. **An upstream field is missing or renamed** relative to `docs/research/data-sources.md`.
   That is schema drift, it affects the hosted companion too, and it is a decision about the
   whole program rather than a local fix.
4. **A statistic seems wrong in a way the specification does not cover.** For example, a
   program where more than half of awards have a null `Base Obligation Date`, or where the
   multi-listing share exceeds 60%. Report it rather than inventing a fallback rule, because
   the fallback rule becomes a number somebody quotes to a board.
5. **Any temptation to estimate, impute, smooth, or fill a gap in single audit coverage.**
   The answer is almost certainly no. Ask first. This is the thing that would destroy the
   tool's credibility fastest.
6. **Anything that looks like an eligibility determination or a recommendation.** If you
   find yourself writing output that says a program is a good fit, stop.
7. **Adding a dependency beyond the list in section 3.** Especially pandas, numpy, or
   anything that pulls a compiled wheel, since it changes `uvx` startup time, which is the
   60-second quickstart.
8. **Adding a database, a persistent server, a background daemon, or a Docker Compose
   file.** All are non-goals. If a feature seems to need one, the feature is wrong or it
   belongs in the hosted companion.
9. **Publishing the derived Unique Entity Identifier to Employer Identification Number
   crosswalk** described in `docs/research/prior-art.md`. Building it locally is fine.
   Publishing it is a redistribution decision under the FAC terms of use and needs a human.
10. **Any competitor name or price, anywhere.** The program rule is that no repository
    names a commercial competitor or quotes its price — not in code, help text, output,
    documentation, or a hosted page. Describe the category instead. See
    `docs/program/CONVENTIONS.md`, "No competitor naming or pricing."
11. **Rate limiting or blocking from either upstream.** If you get sustained 429 or a block,
    stop and report. Do not work around it, do not rotate anything, do not add parallelism.
    Being a good citizen of free public infrastructure is a requirement of this program.

---

## 18. Definition of done

- [ ] `uvx precedent history 93.243` returns a correct profile in under 60 seconds on a
      cold cache, with no credentials of any kind
- [ ] Section 16 verification passes within tolerance, and the `H79TI081686` hand check is
      correct
- [ ] The new-entrant rate is the first statistic a user sees
- [ ] `precedent passthrough --state OH --program 93.045` returns a ranked intermediary
      list with the coverage warning above it
- [ ] Every JSON payload contains `provenance`, `disclosure`, and, for pass-through,
      `coverage`
- [ ] No flag, mode, or format omits the single audit threshold limitation
- [ ] `precedent mcp` exposes four tools whose descriptions state the coverage limitation
- [ ] All four commands work with `--json` and produce schema-valid output
- [ ] Continuous integration is green with no `FAC_API_KEY` present
- [ ] Fixtures are real captured responses with `.meta.json` sidecars
- [ ] `ruff check` and `ruff format --check` pass
- [ ] `NOTICE` and the README Credits section are accurate against what the code actually
      uses
- [ ] The README's rendered examples match what the tool actually prints
- [ ] No secret is committed, and `.env` is gitignored
