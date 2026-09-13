# precedent

**Federal award history and pass-through finder.** Find out who actually wins a federal
program before you advise a client to apply for it, and find the state agencies,
universities, and large nonprofits that pass federal money down to organizations too small
to win it directly.

[![CI](https://github.com/egeria-corporation/precedent/actions/workflows/ci.yml/badge.svg)](https://github.com/egeria-corporation/precedent/actions/workflows/ci.yml)

---

## The problem

You are sitting with a client. They have a $600,000 operating budget, three program staff,
and no federal award history. Someone forwards them a Notice of Funding Opportunity that
looks like a perfect programmatic fit, and they want to know whether to spend six weeks
writing to it.

The thing you need in order to answer that question is not in the NOFO. You need to know
who has won this program before. If the last five years of awards under that Assistance
Listing went to state health departments and university medical centers at a median of
$4 million each, your client is not a marginal candidate. They are not a candidate. If the
median award is $180,000, four in ten winners each year are organizations that had never
won the program before, and the awardee list is full of community-based groups in eleven
states, that is a completely different conversation.

Today that answer is either invisible at the moment of decision or it costs $179 to $899 a
month to look up. So most of the time the question does not get asked, and consultants
advise clients into pursuits they realistically cannot win.

There is a second, larger problem hiding behind the first.

Most nonprofit leaders think of federal funding as something you apply for on Grants.gov.
For small organizations that is usually wrong. A very large share of federal money reaches
community nonprofits as a **subaward**: the federal agency awards to a state agency, a
county, a university, or a large intermediary nonprofit, and that entity passes the money
down under a subrecipient agreement. Head Start, victim services, aging nutrition
programs, workforce development, community development block grants, and most block grant
funding in general move this way.

If you are a $600,000 organization, the pass-through layer is where your actual odds live.
And essentially no commercial grant research product surfaces it, because the data lives
somewhere nobody in this market looks: the Schedule of Expenditures of Federal Awards
inside single audit filings at the Federal Audit Clearinghouse.

`precedent` does both halves. It reads the direct award history from USAspending, and it
reads the pass-through layer from single audits, and it tells you what it does not know.

---

## Quickstart

Sixty seconds, no account, no API key, no database.

The package is `federal-precedent` on PyPI and the command it installs is `precedent`.
They differ because `precedent` on PyPI is a name reservation for an unrelated
architecture-decision-record project. `uvx federal-precedent ...` below runs without
installing anything; if you install it properly, the command is just `precedent`.

```bash
# Award history for a program you already have in mind
uvx federal-precedent history 93.243

# Or find the program first
uvx federal-precedent programs "opioid"

# Machine-readable
uvx federal-precedent history 93.243 --json
```

The `history` command needs no credentials at all. The `passthrough` command needs a free
Federal Audit Clearinghouse API key, which takes about two minutes to get by email. See
[`.env.example`](.env.example).

```bash
export FAC_API_KEY="..."          # free, from https://www.fac.gov/api/signup/
uvx federal-precedent passthrough --state OH --program 93.045
```

Look up one organization, by Unique Entity Identifier, Employer Identification Number, or
name:

```bash
uvx federal-precedent recipient 54-1939556
```

Run it as an MCP server for Claude or any other MCP client:

```bash
uvx --from 'federal-precedent[mcp]' precedent mcp
```

---

## Credits

`precedent` is a thin layer over public infrastructure that other people built and
maintain. Naming them is not a courtesy, it is the accurate description of where the value
comes from.

- **[USAspending](https://www.usaspending.gov/) and the
  [`usaspending-api`](https://github.com/fedspendingtransparency/usaspending-api) team** at
  the Bureau of the Fiscal Service and the Federal Spending Transparency community. The
  API is open, well documented, free, and requires no key. The
  [request contracts](https://github.com/fedspendingtransparency/usaspending-api/tree/master/usaspending_api/api_contracts)
  in that repo are the reason this tool could be built correctly rather than by guesswork.
- **The [Federal Audit Clearinghouse](https://www.fac.gov/) team at GSA Technology
  Transformation Services**, who moved the FAC from Census to GSA, put a real PostgREST API
  in front of single audit data, published a
  [field dictionary](https://www.fac.gov/api/dictionary/) and a legacy-field crosswalk, and
  give the key away for free. The pass-through half of this tool exists because they did
  that work.
- **The [Nonprofit Open Data Collective](https://github.com/Nonprofit-Open-Data-Collective)**
  and **[GivingTuesday](https://990data.givingtuesday.org/tool-repository/)**, whose Form
  990 tooling and Master Concordance File underpin the sibling `funder-graph` repo that
  `precedent` cross-references by EIN.
- **[ProPublica Nonprofit Explorer](https://projects.propublica.org/nonprofits/api)** for
  organization lookups used in gap-filling.

Full attribution and licenses are in [`NOTICE`](NOTICE). Our contribution posture, and the
issues we intend to file upstream rather than patch locally, are in
[`docs/research/prior-art.md`](docs/research/prior-art.md).

---

## Worked example 1: award history

**Assistance Listing 93.243, Substance Abuse and Mental Health Services Projects of
Regional and National Significance.** Awarding agency: Department of Health and Human
Services, Substance Abuse and Mental Health Services Administration.

```
$ uvx federal-precedent history 93.243 --since 2020 --until 2024
```

```
Assistance Listing 93.243, FY2020 through FY2024
------------------------------------------------------------------------------

NEW-ENTRANT RATE  39.7%
  288 of 725 recipients in FY2020-FY2024 had won no award under this program in the FY2015-FY2019 lookback.

1,056 awards to 725 distinct recipients, $3,565,889,654 obligated.
Repeat winners: 207 of 725 (28.6%) won more than once in the window.
The top 10 recipients hold 48.2% of the dollars.

AWARD SIZE  (total obligated over the life of each award, not per year)
  median $305,040    mean $3,376,789  (skewed by large awards)
  p10 $94,438   p25 $185,956   p75 $854,674   p90 $2,590,154
  range $397 to $205,604,128 across 1,056 awards

  under_100k 153 (14%)  100k_250k 287 (27%)  250k_500k 221 (21%)  500k_1m 164 (16%)  1m_5m 160 (15%)  5m_plus 71 (7%)

TOP RECIPIENTS BY DOLLARS
      $322,895,770  6 awards     THE MENTAL HEALTH ASSOCIATION OF NEW YORK CITY, INC.
      $220,092,263  2 awards     HEALTH CARE SERVICES, CALIFORNIA DEPARTMENT OF
      $218,976,104  3 awards     HEALTH & HUMAN SVC COMMN TX
      $193,295,399  2 awards     OHIO DEPARTMENT MENTAL HEALTH
      $176,908,364  2 awards     FLORIDA DEPARTMENT OF CHILDREN AND FAMILIES
      $159,645,496  1 award      PENNSYLVANIA DEPARTMENT OF DRUG AND ALCOHOL PROGRAMS
      $119,688,912  3 awards     RESEARCH FOUNDATION FOR MENTAL HYGIENE, INC.
      $117,821,539  5 awards     HUMAN SERVICES, NEW JERSEY DEPARTMENT OF
      $102,940,627  2 awards     DEPARTMENT OF BEHAVIORAL HEALTH & DEVELOPMENTAL SERVICES
       $86,667,882  3 awards     HEALTH AND HUMAN RESOURCES, WEST VIRGINIA DEPARTMENT OF

GEOGRAPHY  57 states or territories
  CA 85, AK 79, OK 67, NY 57, WI 40, MI 39, MT 31, SD 30, AZ 29, FL 27

READ THIS BEFORE QUOTING ANY OF THE ABOVE
  - 24% of awards are reported under more than one Assistance Listing. Award amounts include money from those other programs, so the size percentiles are an upper bound.
  - The mean award is more than twice the median, so a few large awards are pulling it upward. The median is the better guide to a typical award.

Recipients were matched by: uei 100%.
Excluded: 0 undated, 1086 with no positive amount.

Source: USAspending, retrieved 2026-09-13.
This is informational only, derived from public data on the dates shown. It is not an eligibility determination, and not legal, tax, or accounting advice. Verify against the official source before relying on it.
```

Captured from a live run on 2026-09-13. USAspending restates prior-period records, so a
run today may differ slightly; the retrieval date in the footer is the one that matters.
The headline is a sentence rather than a bare percentage, because "39.7%" invites a
reader to supply their own meaning and "288 of 725 recipients had won nothing under this
program in the five years before" does not.

---

## Worked example 2: pass-through finder

**Who actually hands Older Americans Act nutrition money to organizations in Ohio.**
USAspending shows the award to the state; the organizations it re-grants to appear only
in single audits, where each subrecipient's own auditor names who passed the money down.

```
$ uvx federal-precedent passthrough --state OH --program 93.045 --since 2022 --until 2023
```

```
Federal pass-through funders in OH, Assistance Listing 93.045
------------------------------------------------------------------------------

4,945 single audits scanned, FY2022-FY2023.

WHO PASSES MONEY DOWN TO ORGANIZATIONS HERE
  Ranked by how many distinct organizations name them, not by dollars: the
  question is who makes subawards to organizations like yours.

  18 orgs      $66,099,231   OHIO DEPARTMENT OF AGING
            state agency; seen in 30 audits; name from the alias table
            93.045 x113
  5 orgs        $1,828,239   COUNCIL ON AGING OF SOUTHWESTERN OHIO
            EIN 310807186 (supply side match); nonprofit; seen in 8 audits; name from the alias table
            93.045 x11
  5 orgs          $615,275   Western Reserve Area Agency on Aging
            EIN 341620774 (supply side match); non-profit; seen in 8 audits
            93.045 x12
  4 orgs        $1,385,258   Area Agency on Aging District 7, Inc.
            EIN 310971399 (supply side match); non-profit; seen in 7 audits
            93.045 x19
  3 orgs          $723,466   AREA OFFICE ON AGING OF NORTHWESTERN OHIO

  ... 96 further lines of intermediaries ...

READ THIS BEFORE QUOTING ANY COUNT ABOVE
  Single audits are only filed by organizations that expend at or above the
  federal single audit threshold in a fiscal year. That threshold was $750,000
  and rose to $1,000,000 for fiscal years beginning on or after 2024-10-01.
  Organizations below the threshold file nothing, so they are absent from this
  data entirely, not counted as zero. This list is therefore skewed toward
  larger recipients and larger intermediaries, and every subrecipient count is
  a floor rather than a total.

Source: Federal Audit Clearinghouse, retrieved 2026-09-08.
FAC production refreshes weekly, typically Wednesdays. Coverage begins with audit year 2016.
This is informational only, derived from public data on the dates shown. It is not an eligibility determination, and not legal, tax, or accounting advice. Verify against the official source before relying on it.
```

Needs a free `FAC_API_KEY`. Every count above is a floor rather than a total, for the
reason the output states in full: organizations below the single audit threshold file
nothing at all, so they are absent from this data rather than counted as zero.
---

## What it computes, and exactly how

Precise definitions matter more than the numbers themselves, because two tools can produce
different medians from the same data and both be defensible.

| Output | Definition |
|---|---|
| Award universe | Assistance awards (award type codes 02, 03, 04, 05) reported under the Assistance Listing, assigned to a fiscal year by **base obligation date**, deduplicated by USAspending's award identifier |
| Award amount | Total obligated across the life of the award, not fiscal-year outlays |
| Median | 50th percentile of award amounts, over awards rather than recipients |
| Percentiles | p10/p25/p50/p75/p90 by inclusive linear interpolation |
| Distribution buckets | Fixed half-open bands so programs are comparable: under $100k, $100k-$250k, $250k-$500k, $500k-$1M, $1M-$5M, $5M and over |
| Recipient identity | Unique Entity Identifier where present, then USAspending's recipient hash, then normalized legal name |
| Repeat winner | A recipient with 2 or more distinct awards inside the window |
| **New-entrant rate** | Share of distinct recipients in the window that had **no** award under the same Assistance Listing during the lookback window (default: the 5 fiscal years immediately before) |
| Geographic spread | Count of distinct place-of-performance state and territory codes, plus leaders by count and by dollars |
| Concentration | Share of window dollars held by the top 10 recipients |
| Pass-through, demand side | Distinct organizations in the state that named an entity as their pass-through entity in their own single audit |
| Pass-through, supply side | Reported pass-through amounts from SEFA lines the auditee marked as passed down to subrecipients |

Full statistical specification, including tie-breaking and null handling, is in
[`prompts/01-build-core.md`](prompts/01-build-core.md).

---

## Coverage and limitations

Read this section before you quote a number from this tool to a client.

**The single audit threshold makes pass-through coverage inherently partial.** A
non-federal entity must have a single audit only if it expends at or above the threshold in
federal awards in a fiscal year. That threshold was $750,000 for many years and rose to
**$1,000,000 for fiscal years beginning on or after 2024-10-01** under the 2024 revision to
the Uniform Guidance. An organization spending $400,000 in federal pass-through money files
nothing and appears nowhere in this data. Every subrecipient count `precedent` reports is a
floor. Every intermediary ranking is a ranking among intermediaries visible to organizations
large enough to file. Treating these lists as complete is the single most likely way to be
wrong with this tool, and it is why the coverage warning is printed in the output and not
only here.

**Schedule of Expenditures of Federal Awards reports expenditures, not awards.** A SEFA line
says what an organization spent under a program during an audited fiscal year. It does not
say what they were awarded, when they were awarded it, or how long the award runs. Multi-year
awards appear across several audits at partial amounts.

**Pass-through entity names are free text.** The auditee types them. "Ohio Dept. of Aging",
"OHIO DEPARTMENT OF AGING", and "State of Ohio, Department of Aging" are three strings for
one agency. `precedent` normalizes and clusters, publishes the alias table it uses, and
shows you the raw variants on request. It will still occasionally split one entity or merge
two, and it never merges across states.

**Awards frequently report more than one Assistance Listing.** In the 93.243 example above,
24.2% of awards list a second program number, and USAspending reports one obligated total per
award rather than a split by program. Award-size statistics for programs with heavy
multi-listing are therefore an upper bound. `precedent` reports the multi-listing share on
every profile so you can judge it.

**FAC API coverage starts at audit year 2016.** Earlier single audits live in the legacy
Census extracts and are not queried by this tool.

**USAspending search reaches back to 2007-10-01.** A lookback window that crosses that
boundary is truncated, which inflates the new-entrant rate. `precedent` flags this on the
output when it happens.

**Federal spending data is restated.** Agencies correct prior submissions. Numbers pulled
today can differ slightly from numbers pulled last month. Every output carries a retrieval
date for this reason.

**For-profit subrecipients are generally outside single audit requirements**, so commercial
intermediaries are underrepresented in the pass-through view relative to governments and
nonprofits.

**This tool makes no eligibility determination.** It reports what other organizations
received. It does not know your client's registration status, their indirect cost rate,
their audit findings, or whether the program is open.

---

## Data sources

| Source | What it provides | Auth | Refresh cadence |
|---|---|---|---|
| [USAspending API](https://api.usaspending.gov/) | Direct federal assistance awards: recipient, Unique Entity Identifier, amounts, dates, Assistance Listing numbers, place of performance | None | Daily load from agency submissions; prior periods restated |
| [Federal Audit Clearinghouse API](https://www.fac.gov/api/) | Single audit submissions and Schedule of Expenditures of Federal Awards, including which entity passed money to whom | Free API key by email | Production endpoint updates weekly, typically Wednesdays. Covers audit years 2016 forward |
| [OpenGrants API](https://ops.opengrants.io/api-docs) | Currently open funding opportunities, optional enrichment only | Optional API key | Daily |

Detailed endpoint documentation, request shapes, field semantics, pagination behavior, and
observed rate limits are in
[`docs/research/data-sources.md`](docs/research/data-sources.md).

Terms of use worth reading before you redistribute anything derived from these:
[FAC API terms](https://www.fac.gov/api/terms/).

---

## Optional: pair history with what is open right now

`precedent` works completely without any OpenGrants credentials. If you set
`OPENGRANTS_API_KEY`, every program profile gains a section showing the currently open
opportunities under that Assistance Listing, drawn live from the OpenGrants
[`/grants-api`](https://ops.opengrants.io/api-docs) index, so you get the historical
awardee profile and the live application deadline in one place. Enriched lines are marked
`— live from OpenGrants` so you always know which facts came from public bulk sources and
which came from the API. If the key is missing, expired, or the network is down, the
command still returns its full public-data result.

---

## MCP server

Four Model Context Protocol tools for agent use — `award_history`, `passthrough_finder`,
`recipient_profile`, `find_program` — each returning exactly what `--json` returns, because
the CLI and the server are both thin adapters over the same library. Shipped in 0.2.0.

```bash
uvx --from 'federal-precedent[mcp]' precedent mcp
```

Each tool's *description* carries the limitations, not only its payload. A model picks a
tool by reading the description and may never open the `coverage` object it gets back, so
the two facts that most change how an answer should be used — that pass-through counts are
floors rather than totals, and that nothing here is an eligibility determination — are in
the text the model reads before it decides anything.

---

## Disclosure

> This is informational only, derived from public data on the dates shown. It is not an
> eligibility determination, and not legal, tax, or accounting advice. Verify against the
> official source before relying on it.

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Fixture-based tests against real committed
samples of upstream responses are required for any change touching a data source, because
mocked-shape tests do not catch schema drift and schema drift is the failure mode that
actually matters here.

## License

Apache License 2.0. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

---

Built and maintained by Egeria Corporation, sponsored by
[OpenGrants](https://opengrants.io).
