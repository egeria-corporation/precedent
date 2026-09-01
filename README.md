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

```bash
# Award history for a program you already have in mind
uvx precedent history 93.243

# Or find the program first
uvx precedent programs --search "opioid treatment"

# Machine-readable
uvx precedent history 93.243 --json
```

The `history` command needs no credentials at all. The `passthrough` command needs a free
Federal Audit Clearinghouse API key, which takes about two minutes to get by email. See
[`.env.example`](.env.example).

```bash
export FAC_API_KEY="..."          # free, from https://www.fac.gov/api/signup/
uvx precedent passthrough --state OH --program 93.045
```

Run it as an MCP server for Claude or any other MCP client:

```bash
uvx precedent mcp
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
$ uvx precedent history 93.243 --since FY2020 --until FY2024
```

```
93.243  Substance Abuse and Mental Health Services Projects of Regional and
        National Significance
        Department of Health and Human Services / SAMHSA
        Assistance awards with a base obligation date in FY2020-FY2024

  1,058 awards to 726 distinct recipients          $3,570,889,654 obligated

  NEW-ENTRANT RATE                                              39.1%
  284 of 726 recipients in FY2020-FY2024 had won no award under this
  program in the FY2015-FY2019 lookback window.

  Award size
    minimum                                                      $397
    25th percentile                                          $186,013
    MEDIAN                                                   $305,161
    75th percentile                                          $854,761
    90th percentile                                        $2,615,811
    maximum                                              $205,604,128
    mean                                                   $3,375,132   (skewed)

  Distribution
    under $100k        153  ###############                      14.5%
    $100k - $250k      287  ############################         27.1%
    $250k - $500k      221  #####################                20.9%
    $500k - $1M        164  ################                     15.5%
    $1M - $5M          162  ################                     15.3%
    $5M and over        71  #######                               6.7%

  Repeat winners                                                 28.7%
  208 of 726 recipients took 2 or more awards inside the window.
  Top 10 recipients by dollars hold 48.1% of all dollars obligated.

  Geography          57 place-of-performance state and territory codes
    CA 85    AK 79    OK 67    NY 58    WI 40    MI 39    MT 31    SD 30

  Most frequent recipients
    Great Plains Tribal Leaders Health Board          7 awards    $7,634,611
    The Mental Health Association of New York City    6 awards  $322,895,770
    New Jersey Department of Human Services           5 awards  $117,821,539
    MaineHealth                                       5 awards    $1,817,853

  Caveats for this program
    256 of 1,058 awards (24.2%) report more than one Assistance Listing, so
    the dollar figures include money that is not 93.243. Treat award-size
    percentiles for this program as an upper bound.

  Source: USAspending API, POST /api/v2/search/spending_by_award, retrieved
  2026-08-30. Award amounts are total obligations across the life of each
  award, not fiscal-year outlays.

  This is informational only, derived from public data on the dates shown. It
  is not an eligibility determination, and not legal, tax, or accounting
  advice. Verify against the official source before relying on it.
```

Those figures are real. They were computed against the live USAspending API on 2026-08-30
and the command above reproduces them, subject to the small drift that comes from USAspending
restating prior-year records.

**What a consultant does with this.** A median of $305,161 with 41.6% of awards under
$250,000 means a mid-sized community organization is inside the size band. A new-entrant
rate of 39.1% means this program genuinely takes newcomers, which is the opposite of what
the presence of $205 million awards at the top of the range would suggest on its own. The
new-entrant rate is the number that changes the advice, which is why it is the headline
and not a footnote.

---

## Worked example 2: pass-through finder

**State: Ohio. Assistance Listing 93.045, Special Programs for the Aging, Title III,
Part C, Nutrition Services.** This is a program almost no community organization receives
directly. Federal money goes from the Administration for Community Living to the state
unit on aging, which subawards to regional area agencies on aging, which subaward again to
local senior centers and meal providers.

```
$ export FAC_API_KEY="..."
$ uvx precedent passthrough --state OH --program 93.045
```

> **The output below is illustrative.** The structure it shows is real and verifiable:
> Ohio's federal aging nutrition money does move through the Ohio Department of Aging to
> regional area agencies on aging, and the organizations named are real Ohio area agencies
> on aging. The dollar figures and counts are shaped from typical Schedule of Expenditures
> of Federal Awards magnitudes rather than pulled live, because the pass-through query
> needs an API key. Run the command to get current figures.

```
93.045  Special Programs for the Aging, Title III, Part C, Nutrition Services
        Pass-through entities reaching organizations in OHIO
        Audit years 2019-2024, 1,214 Ohio single audits scanned

  WHO PASSES THIS MONEY DOWN
  Ranked by the number of distinct Ohio organizations that named this entity
  as their pass-through entity in their own single audit.

  1. Ohio Department of Aging                            state agency
     named by 11 Ohio subrecipients      $41.2M expended through it
     also passes: 93.044, 93.052, 93.053, 10.561
     -> this is the state unit on aging; it is the top of the Ohio chain

  2. Council on Aging of Southwestern Ohio               nonprofit, Blue Ash OH
     named by 9 Ohio subrecipients        $8.7M expended through it
     EIN 31-0896213   passes down 93.045, 93.044, 93.052
     -> funders.opengrants.io/funders/31-0896213

  3. Western Reserve Area Agency on Aging                nonprofit, Cleveland OH
     named by 7 Ohio subrecipients        $6.1M expended through it

  4. Area Office on Aging of Northwestern Ohio, Inc.     nonprofit, Toledo OH
     named by 5 Ohio subrecipients        $3.9M expended through it

  5. Central Ohio Area Agency on Aging                   public, Columbus OH
     named by 4 Ohio subrecipients        $3.4M expended through it

  OHIO ENTITIES REPORTING THEY PASSED 93.045 MONEY DOWN
  From SEFA lines where the auditee marked the award as passed through to
  subrecipients, ranked by reported pass-through amount.

    Ohio Department of Aging                             $39,800,000
    Council on Aging of Southwestern Ohio                 $7,900,000
    Direction Home Akron Canton Area Agency on Aging      $4,600,000
    Ohio District 5 Area Agency on Aging                  $2,100,000

  COVERAGE WARNING  read this before you use the list above
    Single audits are only filed by organizations that expend at or above the
    federal single audit threshold in a fiscal year. That threshold was
    $750,000 and rose to $1,000,000 for fiscal years beginning on or after
    2024-10-01. Organizations below the threshold file nothing, so they are
    absent from this data entirely, not counted as zero.

    That means this list is skewed toward larger recipients and larger
    intermediaries, and the subrecipient counts are a floor, not a total. An
    intermediary "named by 4 subrecipients" is named by 4 subrecipients that
    were themselves large enough to file. It may have fifty more.

    Pass-through entity names in this data are free text typed by the
    auditee. precedent normalizes and clusters them; run with
    --show-name-variants to see exactly which raw strings were merged.

    Amounts are federal expenditures in the audited fiscal year, not award
    amounts and not the year the award was made.

  Source: Federal Audit Clearinghouse API, general / federal_awards /
  passthrough endpoints, retrieved 2026-08-30. FAC production data refreshes
  weekly, typically Wednesdays, and covers audit years 2016 forward.

  This is informational only, derived from public data on the dates shown. It
  is not an eligibility determination, and not legal, tax, or accounting
  advice. Verify against the official source before relying on it.
```

**What a consultant does with this.** The client was never going to win 93.045 from the
Administration for Community Living. The five organizations at the top of that list are the
actual funders in their world, they are reachable by phone, they have subrecipient
procurement processes, and no subscription product this client's consultant is paying for
lists them.

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

The same capabilities are exposed as Model Context Protocol tools for agent use:
`award_history`, `passthrough_finder`, `recipient_profile`, `find_program`. Core logic
lives in the library; the CLI and the MCP server are both thin adapters over it.

```bash
uvx precedent mcp
```

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
