# Data sources

Everything below was verified against the live APIs on **2026-08-30**. Where a fact came
from a vendor document rather than a live call, it is marked. Where something could not be
verified without a key, it is marked **VERIFY**. Re-verify anything marked that way before
it appears in public-facing copy.

Two sources do the work. USAspending gives the direct award history. The Federal Audit
Clearinghouse gives the pass-through layer. They do not share an identifier, and bridging
them is one of the more interesting problems in this repository, so it gets its own section
at the end.

---

## 1. USAspending

- **Root:** `https://api.usaspending.gov/`
- **Auth:** none. No key, no signup, no header.
- **Docs index:** <https://api.usaspending.gov/docs/endpoints>
- **Authoritative request contracts:**
  <https://github.com/fedspendingtransparency/usaspending-api/tree/master/usaspending_api/api_contracts/contracts/v2>
- **Coverage:** search endpoints reach back to **2007-10-01**. For earlier data the API
  returns a message directing you to the bulk download endpoints or the site's Custom Award
  Download. This message is returned in the `messages` array on every search response.

### 1.1 The endpoint that matters: `POST /api/v2/search/spending_by_award/`

Contract:
<https://github.com/fedspendingtransparency/usaspending-api/blob/master/usaspending_api/api_contracts/contracts/v2/search/spending_by_award.md>

This is the endpoint that is easy to get subtly wrong. The filter object is nested, the
`fields` list is validated against the award type you asked for, and a mismatch produces a
400 with a terse message rather than a partial result.

A request that works, verified live:

```json
{
  "filters": {
    "award_type_codes": ["02", "03", "04", "05"],
    "program_numbers": ["93.243"],
    "time_period": [
      {
        "start_date": "2019-10-01",
        "end_date": "2024-09-30",
        "date_type": "action_date"
      }
    ]
  },
  "fields": [
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
    "recipient_id"
  ],
  "limit": 100,
  "sort": "Award Amount",
  "order": "desc",
  "subawards": false,
  "page": 1
}
```

Things that will bite you:

- **`award_type_codes` selects the field vocabulary.** Assistance award codes are `02`
  block grant, `03` formula grant, `04` project grant, `05` cooperative agreement, `06`
  direct payment for specified use, `07` direct loan, `08` guaranteed or insured loan, `09`
  insurance, `10` direct payment unrestricted, `11` other financial assistance. For grant
  history use `02, 03, 04, 05`. Mixing contract codes (`A`, `B`, `C`, `D`) into the same
  request, or asking for a contract-only field such as `Award Type` alongside assistance
  codes, returns a 400.
- **`program_numbers` is the Assistance Listing filter.** It takes the dotted string form,
  `"93.243"`, as a list. This is the old Catalog of Federal Domestic Assistance number.
- **`subawards` must be present and false.** When true, the endpoint switches to the FSRS
  subaward table and the `fields` vocabulary changes completely.
- **`date_type` accepts `action_date`, `date_signed`, `new_awards_only`.** With
  `action_date`, the endpoint returns any award that had **any transaction** in the window,
  including awards first obligated years earlier. That is almost never what you want for a
  cohort statistic. Fetch on a wide `action_date` window, then bucket locally on **`Base
  Obligation Date`**, which is the award's earliest obligating action. This distinction is
  the single most common way to compute a wrong new-entrant rate.
- **`Award Amount` is the total obligated over the life of the award**, not the amount
  obligated inside your window. There is no per-window split available on this endpoint.
- **Pagination.** `limit` maxes at 100. `page`-based paging works but degrades badly past a
  few thousand records. The response carries `page_metadata` with `page`, `hasNext`,
  `last_record_unique_id`, and `last_record_sort_value`. Feed those two back as top-level
  request keys `last_record_unique_id` and `last_record_sort_value` for keyset pagination,
  which stays fast to arbitrary depth. Verified: a 7,683-record pull of 93.243 over
  2014-10-01 to 2025-09-30 completed cleanly this way at 100 per page.
- **Response envelope**, verified:

  ```json
  {
    "spending_level": "awards",
    "limit": 100,
    "results": [ ... ],
    "page_metadata": {
      "page": 1,
      "hasNext": true,
      "last_record_unique_id": 267887531,
      "last_record_sort_value": "12523781936"
    },
    "messages": ["For searches, time period start and end dates are currently limited ..."]
  }
  ```

- **Fields you did not ask for come back anyway.** Every result carries `internal_id` and
  `generated_internal_id` regardless of the `fields` list. `generated_internal_id` (for
  example `ASST_NON_H79TI081686_075`) is the stable award key and the correct deduplication
  key.
- **`awarding_agency_id` is sometimes null** even when `Awarding Agency` is populated.
  Do not key anything on it.

### 1.2 The multi-Assistance-Listing problem

`Assistance Listings` returns an array. An award can be reported under several programs:

```json
"Assistance Listings": [
  {"cfda_number": "93.243", "cfda_program_title": "SUBSTANCE ABUSE AND MENTAL HEALTH SERVICES PROJECTS OF REGIONAL AND NATIONAL SIGNIFICANCE"},
  {"cfda_number": "93.788", "cfda_program_title": "OPIOID STR"}
]
```

Filtering on `program_numbers: ["93.243"]` returns every award that touches 93.243, and
`Award Amount` is the whole award, not the 93.243 share. There is no field that splits the
obligation by program.

Measured on the live data: **24.2% of the 1,058 awards under 93.243 with a base obligation
date in FY2020 through FY2024 report more than one Assistance Listing.** For programs with
a high multi-listing share, award-size percentiles are an upper bound. The tool must
compute and display this share on every program profile rather than silently absorbing the
distortion.

### 1.3 Supporting endpoints

| Endpoint | Method | Use |
|---|---|---|
| `/api/v2/autocomplete/cfda/` | POST `{"search_text": "...", "limit": n}` | Resolve a keyword or a partial number to an Assistance Listing. Returns `program_number`, `program_title`, `popular_name`. Verified working. |
| `/api/v2/search/spending_by_award_count/` | POST, same filter object | Award counts by category before pulling records. Returns `{"contracts", "direct_payments", "grants", "idvs", "loans", "other"}`. Use it to decide whether a pull is cheap or expensive. Verified: 3,875 grants for 93.243 over FY2020-FY2024 by action date. |
| `/api/v2/search/spending_by_category/recipient/` | POST | Recipient-level aggregation. **Careful:** the response reports `"spending_level": "transactions"`, so its totals are transaction sums and will not match award-level sums. Returns `recipient_id`, `name`, `uei`, and `code`, where `code` is the legacy DUNS number, not an Employer Identification Number. |
| `/api/v2/search/spending_over_time/` | POST | Program totals by fiscal year, for the trend line. |
| `/api/v2/awards/{generated_internal_id}/` | GET | Full detail for one award. |
| `/api/v2/recipient/{recipient_id}/` | GET | Recipient profile, including parent and child relationships. |
| `/api/v2/bulk_download/awards/` | POST | Asynchronous bulk export. The correct escape hatch when a program has tens of thousands of awards; do not paginate a very large program record by record. |

### 1.4 Identifiers

- `Recipient UEI` is the twelve-character Unique Entity Identifier from SAM.gov. Present on
  most modern records, absent on older ones.
- `recipient_id` is a USAspending hash with a level suffix: `-C` for a child record at the
  UEI level, `-R` for a recipient without a parent, `-P` for a parent. Two rows with the
  same organization at different levels get different `recipient_id` values, so it is not
  safe as a bare identity key without normalizing the suffix.
- **There is no Employer Identification Number anywhere in USAspending.** See section 3.

### 1.5 Rate behavior

Undocumented, and in practice real. Observed behavior:

- Sequential requests at roughly 2 to 3 per second are fine.
- Aggressive parallelism produces 429 and intermittent 502/503 from the edge rather than a
  clean documented error.
- Large `spending_by_award` pulls are server-expensive; response times of 5 to 20 seconds
  for a 100-record page on a big program are normal.

Client requirements: no more than 2 concurrent requests, exponential backoff with jitter on
429/5xx, a descriptive `User-Agent` including a contact address, and a local cache with a
7-day time to live. Nothing about this data changes hourly.

---

## 2. Federal Audit Clearinghouse

- **Request host:** `https://api.fac.gov` (verified: a keyless request returns HTTP 403
  with `{"error": {"code": "API_KEY_MISSING"}}`)
- **Documentation host:** <https://www.fac.gov/api/>
- **Auth:** `X-Api-Key: <key>` header. Free key by email at
  <https://www.fac.gov/api/signup/>. It is an api.data.gov key, so the rate limit is per
  key.
- **Terms:** <https://www.fac.gov/api/terms/>
- **Technology:** PostgREST. Standard PostgREST filtering, ordering, embedding, and range
  headers apply. <https://postgrest.org/>
- **Environments**, from the FAC getting-started page:
  - `api.fac.gov` production, submitted data only, **updated once per week, typically
    Wednesdays**
  - `api-staging.fac.gov` mixed real and test data, refreshed daily at 5am Eastern
  - `api-dev.fac.gov` unstable, updates on every merge to main
  - `api-preview.fac.gov` internal, do not use
- **Scale**, from the FAC results-management page: roughly 40,000 to 50,000 audits
  submitted per year, more than 200,000 audits and more than 2.5 million `federal_awards`
  records total, covering **audit year 2016 forward**. Earlier single audits are in the
  legacy Census extracts and are not in this API.
- **Hard result cap: 20,000 rows per request.** FAC explicitly asks partners to issue small
  restrictive queries rather than large joins.

### 2.1 Smoke test

```bash
curl -s -X GET "https://api.fac.gov/general?limit=5" -H "X-Api-Key: ${FAC_API_KEY}"
```

### 2.2 The four endpoints this tool uses

Field names below are taken from the FAC data dictionary at
<https://www.fac.gov/api/dictionary/>, which also publishes the crosswalk from the legacy
Census column names. The legacy name is given in parentheses because a great deal of
existing single-audit tooling and documentation still uses it.

#### `/general` — one row per audit submission

| Field | Type | Legacy | Why it matters |
|---|---|---|---|
| `report_id` | text | `AUDITYEAR + DBKEY` | The join key for every other endpoint |
| `audit_year` | text | `AUDITYEAR` | Cohort assignment |
| `fy_start_date`, `fy_end_date` | date | `FYSTARTDATE`, `FYENDDATE` | Determines which single audit threshold applies |
| `auditee_ein` | text | `EIN` | **The bridge to Form 990 data** |
| `auditee_uei` | text | `EUI` | **The bridge to USAspending** |
| `auditee_name` | text | `AUDITEENAME` | Display |
| `auditee_city`, `auditee_state`, `auditee_zip` | text | `CITY`, `STATE`, `ZIPCODE` | The state filter for the pass-through view |
| `entity_type` | text | `TYPEOFENTITY` | State, local, tribal, higher education, nonprofit. Lets you label an intermediary correctly |
| `total_amount_expended` | bigint | `TOTFEDEXPEND` | Total federal expenditures. The only defensible proxy this tool has for organization scale |
| `dollar_threshold` | bigint | `DOLLARTHRESHOLD` | The threshold applied to this audit. Read it rather than assuming |
| `cognizant_agency`, `oversight_agency` | text | `COGAGENCY`, `OVERSIGHTAGENCY` | Which agency oversees this auditee |
| `fac_accepted_date`, `submitted_date` | date | `FACACCEPTEDDATE` | Vintage stamping |
| `is_low_risk_auditee`, `is_going_concern_included`, `is_internal_control_material_weakness_disclosed` | boolean | `LOWRISK`, `GOINGCONCERN`, `MATERIALWEAKNESS` | Context, not a judgment. Report, never score |
| `auditor_firm_name`, `auditor_state` | text | `CPAFIRMNAME`, `CPASTATE` | Occasionally useful for validating a cluster |

#### `/federal_awards` — one row per SEFA line

This is the Schedule of Expenditures of Federal Awards, and it is the heart of the
pass-through analysis.

| Field | Type | Legacy | Why it matters |
|---|---|---|---|
| `report_id` | text | | Join to `general` |
| `award_reference` | text | `ELECAUDITSID` | Join to `passthrough`, within a `report_id` |
| `federal_agency_prefix` | text | first half of `CFDA` | `"93"` |
| `federal_award_extension` | text | second half of `CFDA` | `"045"`. **Concatenate with a dot to get the Assistance Listing number.** There is no single ALN column |
| `federal_program_name` | text | `FEDERALPROGRAMNAME` | As typed by the auditee, so it varies |
| `amount_expended` | bigint | `AMOUNT` | Federal dollars **expended** in the audited year, not awarded |
| `is_direct` | boolean | `DIRECT` | **False means this money came through a pass-through entity.** This is the flag that finds subrecipients |
| `is_passthrough_award` | boolean | `PASSTHROUGHAWARD` | **True means the auditee passed money down to its own subrecipients.** This is the flag that finds intermediaries |
| `passthrough_amount` | bigint | `PASSTHROUGHAMOUNT` | How much they passed down |
| `cluster_name`, `state_cluster_name`, `other_cluster_name`, `cluster_total` | text/bigint | `CLUSTERNAME`, `STATECLUSTERNAME`, `OTHERCLUSTERNAME`, `CLUSTERTOTAL` | Programs audited together, for example the Aging Cluster. A program-area query should consider the cluster, not only the single ALN |
| `federal_program_total` | bigint | `PROGRAMTOTAL` | Total across all lines for this program in this audit |
| `is_major` | boolean | `MAJORPROGRAM` | Whether it was a major program for this audit |
| `audit_report_type` | text | `TYPEREPORT_MP` | Opinion type on the major program |
| `findings_count` | int | `FINDINGSCOUNT` | Number of findings on this award |
| `is_loan`, `loan_balance` | boolean/text | `LOANS`, `LOANBALANCE` | Loan programs distort expenditure totals; exclude or label |
| `additional_award_identification` | text | `AWARDIDENTIFICATION` | Free-text award or contract number, sometimes the state contract number |

#### `/passthrough` — who passed money to this auditee

| Field | Type | Legacy | Notes |
|---|---|---|---|
| `report_id` | text | | Join to `general` |
| `award_reference` | text | `ELECAUDITSID` | Join to the specific `federal_awards` row |
| `passthrough_name` | text | `PASSTHROUGHNAME` | **Free text typed by the auditee.** The normalization problem |
| `passthrough_id` | text | `PASSTHROUGHID` | The identifying number the auditee was given by the pass-through entity. Sometimes a state contract number, sometimes a Unique Entity Identifier, sometimes an Employer Identification Number, sometimes blank |

Note what is **not** here: no state, no Employer Identification Number for the pass-through
entity, no canonical identifier. The pass-through entity is a name and an unstructured
number. Everything downstream of that is a normalization problem, and pretending otherwise
is how a pass-through tool produces confident nonsense.

#### `/notes_to_sefa` — the auditor's notes on the schedule

`title`, `content`, `accounting_policies`, `is_minimis_rate_used`, `rate_explained`,
`contains_chart_or_table`. Useful for showing an auditor's own description of the
pass-through arrangement, and for the indirect cost rate, which consultants care about.

Other endpoints available and not used by default: `findings`, `findings_text`,
`corrective_action_plans`, `secondary_auditors`, `additional_ueis`, `additional_eins`,
`resubmission`.

### 2.3 PostgREST conventions

Filtering is `?column=operator.value`:

```
?auditee_state=eq.OH
?audit_year=gte.2019
?amount_expended=gt.1000000
?federal_agency_prefix=eq.93&federal_award_extension=eq.045
?is_passthrough_award=is.true
?report_id=in.(2023-06-GSAFAC-0000012345,2023-09-GSAFAC-0000067890)
?passthrough_name=ilike.*DEPARTMENT OF AGING*
```

Common operators: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `like`, `ilike`, `in`, `is`,
`not.`. Combine with `&`, which is AND. OR needs the `or=(...)` syntax.

Other conventions that matter:

- `select=col1,col2` projects columns. Always use it. Bandwidth on this API is the main
  cost.
- `order=amount_expended.desc,auditee_name.asc` orders. **PostgREST does not guarantee a
  stable order without an explicit `order`,** so paginating without one silently skips and
  duplicates rows. Always order by something unique enough, for example
  `order=report_id.asc,award_reference.asc`.
- `limit` and `offset` paginate. FAC's own documentation recommends pages of about 5,000
  and a hard upper bound on the loop so a bug cannot burn the whole key quota.
- `Range` and `Content-Range` headers work in the PostgREST way, and
  `Prefer: count=exact` returns a total in `Content-Range`. Exact counts on large tables
  are slow; prefer `count=planned` or no count at all.
- Cross-endpoint joins via PostgREST resource embedding are **not** reliably available
  here. Do the joins client side by `report_id`, which is also what FAC's own
  documentation recommends.

### 2.4 The query pattern for the pass-through finder

Two independent evidence streams, run separately and merged.

**Demand side, the differentiated one.** Which entities do organizations in this state say
they receive money from?

1. `GET /general?auditee_state=eq.OH&audit_year=gte.2019&select=report_id,auditee_name,auditee_ein,auditee_uei,auditee_city,entity_type,total_amount_expended,fy_end_date&order=report_id.asc`
2. Chunk the resulting `report_id` values into `in.(...)` batches of roughly 100 and pull
   `GET /federal_awards?report_id=in.(...)&is_direct=is.false&federal_agency_prefix=eq.93&federal_award_extension=eq.045&select=report_id,award_reference,amount_expended,federal_program_name,cluster_name`
3. For the same batches pull
   `GET /passthrough?report_id=in.(...)&select=report_id,award_reference,passthrough_name,passthrough_id`
4. Join on `(report_id, award_reference)`, normalize `passthrough_name`, and group. For
   each cluster report the count of **distinct auditees** naming it, the sum of
   `amount_expended` on those lines, and the list of raw name variants merged.

Ranking by distinct subrecipient count rather than dollars is the deliberate choice. Dollars
tell you which intermediary is biggest. Subrecipient count tells you which intermediary
actually makes subawards to organizations like the client, which is the question being
asked.

**Supply side.** Which entities in this state report passing money down?

1. Same `general` query for the state.
2. `GET /federal_awards?report_id=in.(...)&is_passthrough_award=is.true&passthrough_amount=gt.0&select=report_id,federal_agency_prefix,federal_award_extension,amount_expended,passthrough_amount,federal_program_name`
3. Join back to `general` on `report_id` for the entity name, Employer Identification
   Number, city, and entity type. This side gives you a real EIN, unlike the demand side.

The two lists overlap heavily and disagree usefully. An entity that appears on the supply
side but not the demand side passes money to organizations too small to file. An entity on
the demand side but not the supply side is likely out of state, or reported inconsistently.
Both facts are worth showing.

### 2.5 The threshold, stated precisely

Under 2 CFR 200 Subpart F, a non-federal entity that expends federal awards at or above the
single audit threshold in its fiscal year must have a single audit or a program-specific
audit. The threshold was **$750,000**. The 2024 revision to the Uniform Guidance raised it
to **$1,000,000, effective for fiscal years beginning on or after 2024-10-01**.

Consequences the tool must state every time it presents pass-through results:

1. Organizations under the threshold file nothing. They are **absent**, not zero.
2. Coverage is therefore skewed toward larger recipients and larger intermediaries.
3. Every subrecipient count is a **floor**.
4. The applicable threshold varies by the auditee's fiscal year during the transition, so
   two organizations audited in the same calendar year may have faced different thresholds.
   The `general.dollar_threshold` field records what was actually applied; read it rather
   than inferring it.
5. For-profit subrecipients are generally outside Subpart F, so commercial intermediaries
   are underrepresented.

### 2.6 Rate behavior

api.data.gov keys are rate limited per key. FAC additionally caps results at 20,000 rows
per request and asks for small queries. Client requirements: sequential requests with a
small delay, chunk `in.(...)` filters to roughly 100 identifiers, always use `select` and
`order`, cache with a 7-day time to live keyed on the FAC weekly refresh, and never write a
pagination loop without a hard upper bound.

---

## 3. Bridging the two sources

USAspending publishes Unique Entity Identifiers and no Employer Identification Numbers. IRS
Form 990 data, and therefore the sibling `funder-graph` repository, is keyed on Employer
Identification Number. There is no public federal crosswalk between the two.

**FAC `general` contains both `auditee_ein` and `auditee_uei` on the same row.**

That makes the Federal Audit Clearinghouse a free, public, government-published Unique
Entity Identifier to Employer Identification Number crosswalk covering roughly 200,000
audited organizations from audit year 2016 forward. It is not complete, since it only
covers organizations that file single audits, but for this program it covers exactly the
organizations that matter: the ones large enough to take federal money at scale.

Practical consequences:

- Resolving a USAspending recipient to an Employer Identification Number means looking up
  its Unique Entity Identifier in FAC `general`, not doing name matching.
- The crosswalk should be built once, cached, and treated as a first-class artifact. It is
  also the most obviously useful thing this repository could contribute back to the
  community, and `docs/research/prior-art.md` proposes publishing it.
- Where a Unique Entity Identifier is not in FAC, fall back to normalized name plus state
  matching against the IRS Exempt Organizations Business Master File, and carry a match
  confidence field. Never present a name match as an identity match.
- A single audit can cover several Employer Identification Numbers and several Unique Entity
  Identifiers. The `additional_eins` and `additional_ueis` endpoints list them. A one-to-one
  assumption is wrong for large systems, universities in particular.

---

## 4. OpenGrants, optional enrichment

- **Base:** `https://qnoicxojartltrownmal.supabase.co/functions/v1/`
- **Auth:** `Authorization: Bearer <key>`
- **Docs:** <https://ops.opengrants.io/api-docs>
- **Used here:** `GET /grants-api` with a keyword derived from the Assistance Listing title
  and `status=open`, to show the currently open version of the program next to its history.
- **Pagination:** 1 to 100 per page. Search modes: semantic, keyword, hybrid.
- **Rate limit headers:** `X-RateLimit-Limit`, `X-RateLimit-Remaining`.
- **Cadence:** daily. Cache for 24 hours.
- **Requirement:** wrapped so that any failure degrades silently to the un-enriched result,
  with enriched lines marked `— live from OpenGrants`.

---

## 5. Caching, stated as a requirement

Both upstream APIs are free public infrastructure, both are rate sensitive in practice, and
neither changes fast. A tool that hammers them is both slow for its user and a bad citizen.

| Source | Time to live | Reason |
|---|---|---|
| USAspending | 7 days | Daily loads, but no consultant-facing statistic moves meaningfully day to day |
| FAC | 7 days | Production refreshes weekly, typically Wednesdays. A shorter time to live buys nothing |
| OpenGrants | 24 hours | Opportunity status is the only thing here that is genuinely time sensitive |

Cache key: SHA-256 over `(source, method, path, canonicalized sorted parameters or JSON
body)`. Stored value carries `fetched_at`, HTTP status, and the response body, so every
downstream output can print an accurate retrieval date rather than "now".

`--no-cache` bypasses reads and still writes. `precedent cache info` prints location, entry
count, size, and oldest and newest entries. `precedent cache clear` empties it.

---

## 6. Reference: Assistance Listing numbers used in examples and tests

All verified live against `POST /api/v2/autocomplete/cfda/` on 2026-08-30.

| Number | Title | Why it is a good test case |
|---|---|---|
| 93.243 | Substance Abuse and Mental Health Services Projects of Regional and National Significance | Large discretionary program, wide award-size range, heavy multi-listing at 24.2%, mix of states, tribes, and nonprofits |
| 93.045 | Special Programs for the Aging, Title III, Part C, Nutrition Services | Almost purely pass-through. The canonical demonstration of the second half of the tool |
| 16.575 | Crime Victim Assistance | Formula to state administering agencies, then subawarded to local victim service nonprofits. Clean two-level chain |
| 84.287 | Twenty-First Century Community Learning Centers | State education agency to local subgrantees. Familiar to most consultants |
| 14.218 | Community Development Block Grants/Entitlement Grants | Entitlement cities to local nonprofits. Municipal rather than state intermediaries |
| 45.024 | Promotion of the Arts Grants to Organizations and Individuals | Many small direct awards plus regional arts organizations acting as intermediaries. Good mixed case |
| 93.600 | Head Start | Direct federal to grantees with delegate agency structures underneath |
| 16.588 | Violence Against Women Formula Grants | State administering agency pass-through, high nonprofit subrecipient density |
