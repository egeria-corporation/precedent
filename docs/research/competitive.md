# Competitive landscape

What a grant consultant pays for today that `precedent` gives away, and where the tool has
no competitor at all.

Pricing figures below carry the date they were verified. **Re-verify any competitor price
on the vendor's own pricing page before it appears in public copy, and date-stamp it in the
text.** Stale competitor pricing is both an accuracy problem and an easy thing for a
competitor to make us look bad over.

---

## Summary

The tool has two halves with completely different competitive positions.

| Half | Position |
|---|---|
| **Federal award history** | Parity play. Instrumentl's past-awardees view is the target. Several products do a version of this. We match the useful part, do the statistics better and more transparently, and charge nothing |
| **SEFA pass-through finder** | No commercial equivalent found. Nothing on the market sells a view of which state agencies, universities, and large nonprofits pass federal money down to smaller organizations, derived from single audit filings |

The second half is the reason this repository exists. The first half is what makes people
open it.

---

## Parity target: Instrumentl

- <https://www.instrumentl.com/>
- **Pricing: $179, $299, $499, and $899 per month across four tiers.** Source: Capterra,
  verified 2026-08-30 via the program research dossier. Re-verify on Instrumentl's own
  pricing page before publishing.

Instrumentl is the market leader for small and mid-sized nonprofit prospecting, and the
feature that matters here is its past-awardees view: for a funder or a program, see who has
received awards before, with amounts. It is genuinely useful, it is well executed, and it
is a large part of why the product converts.

**Where Instrumentl is stronger.** Foundation coverage is far deeper than anything derived
from federal sources alone, because it is built on Form 990 data at scale. Saved searches,
deadline tracking, team collaboration, and matching are a real product with real workflow
value. It is a polished commercial application and `precedent` is a command line tool.

**Where `precedent` is stronger, specifically.**

1. **Defined statistics rather than a list.** A list of past awardees is not an answer to
   "can my client win this". A median, a percentile spread, a fixed-bucket distribution,
   a repeat-winner share, and above all a new-entrant rate is an answer. `precedent`
   publishes the exact definition of each statistic, so a consultant can defend the number
   in front of a board.
2. **The new-entrant rate.** Nothing in this market surfaces the share of awardees in a
   period that had never previously won the program. It is the single most decision-relevant
   number for a first-time applicant, and it is a headline output here rather than
   something you could theoretically derive by exporting a list and doing it yourself.
3. **Honest coverage statements.** The multi-Assistance-Listing distortion, the truncated
   lookback window, and the single audit threshold are all printed in the output.
4. **Price.** Free, Apache 2.0, `uvx precedent history 93.243`.
5. **Agent-native.** The MCP server means an agent can ask the question. Subscription
   products are not built to be called by somebody else's assistant.
6. **The pass-through half, which Instrumentl does not have in any form.**

---

## The rest of the field

### Candid, Foundation Directory

- <https://candid.org/>
- **$1,599 per year, or $219.99 per month, for the professional level; a lower "essential"
  tier exists.** Source: a May 2024 comparison, carried in the program research dossier.
  **VERIFY** on Candid's own pricing page before publishing.
- The reference standard for private foundation research. Federal award history is not what
  it is for, and it does not touch single audit data.

### Cause IQ

- <https://www.causeiq.com/>
- **$199 per month or $999 per year, with a limited free tier.** Source: same May 2024
  comparison. **VERIFY.**
- Strong on nonprofit financial profiles built from Form 990. Sells to vendors selling *to*
  nonprofits at least as much as to fundraisers. Does surface some grant relationships.
  Not a federal award history product.

### Grant Gopher

- **$9 per month with a limited free option.** **VERIFY.**
- Opportunity listings. No historical analysis.

### Plinth

- <https://www.useplinth.com/> and <https://data.useplinth.com/us-nonprofit-data>
- Newest entrant, positioning a Form 990-derived funding graph. Pricing not public at
  verification.
- The most direct competitor to the sibling `funder-graph` repository rather than to this
  one. Worth watching: if they extend into federal data, the award-history half of
  `precedent` becomes a parity feature quickly. The pass-through half does not, because it
  is not derived from Form 990 at all.

### HigherGov, GovTribe, GovSpend and the federal contracting tools

- <https://www.highergov.com/>, <https://govtribe.com/>
- These are the closest thing to a competitor on the pass-through axis, and honesty about
  them is more useful than a clean claim of novelty.
- They index USAspending comprehensively, including grants, and they surface **subaward
  reports from the Federal Funding Accountability and Transparency Act Subaward Reporting
  System**, which prime recipients file for subawards above a reporting threshold.
- **That is a different and much thinner dataset than the Schedule of Expenditures of
  Federal Awards.** For assistance awards, subaward reporting compliance is inconsistent,
  it reflects what primes chose to file rather than what auditors examined, and it is
  organized around the prime's reporting obligation rather than around the subrecipient's
  experience of where its money came from.
- These products are also priced and designed for federal contractors, not for a nonprofit
  consultant with a $600,000-budget client.
- Where they are genuinely better: contract data, opportunity intelligence, and vendor
  competitive analysis. `precedent` should link to subaward reports as a cross-check and
  should not pretend they do not exist.

### The free public tools

- **USAspending.gov** itself has an excellent award search and a Custom Award Download. It
  will happily give you every 93.243 award as a spreadsheet. It will not give you a median,
  a new-entrant rate, or a distribution, and getting those from the download is an
  afternoon of pivot tables per program.
- **fac.gov Advanced Search** lets you search single audits and download the data. It is
  built for audit oversight: you search by auditee, by agency, by findings. There is no
  view that answers "which organizations pass money to nonprofits in Ohio".
- **Grants.gov** and **SAM.gov** are opportunity and registration systems, not history.

The pattern across all three: the raw material is public and free, and the analysis is
missing. That is the whole opportunity.

---

## The gap, stated plainly

Take a real case. A consultant has an Ohio client with a $600,000 budget doing senior
nutrition and wellness work.

**What every product on this list can tell them:** here are open opportunities matching
"senior nutrition"; here is a list of past awardees under Assistance Listing 93.045, most
of whom are state agencies; here are foundations in Ohio that fund aging services.

**What none of them can tell them:** that they will never win 93.045 directly, that the
money reaches organizations like them through the Ohio Department of Aging and then through
a regional area agency on aging, which specific area agency covers their counties, how many
subrecipients that area agency already reports, roughly how much it passes down, and what
its Employer Identification Number is so the consultant can pull its Form 990 and its board
list before making a call.

That second answer is worth more than the first, it takes about four seconds to compute,
and nobody sells it.

---

## Why the moat holds for a while

It is not a technical moat. Any competent team could build this in a few weeks once they
knew it was worth building. The defensibility is in three softer things.

1. **Nobody in this market is looking at single audit data.** Grant research products are
   built by people who came from fundraising and Form 990 data. Single audits live in the
   accounting and federal compliance world, and the two populations barely overlap. The
   insight travels slowly across that gap.
2. **The honest version is harder than the impressive version.** The obvious way to build
   this produces a confident, complete-looking list that a certified public accountant will
   take apart in one question about the threshold. Doing it correctly means shipping a
   product whose headline feature is partially covered and saying so on every screen. A
   subscription business has a real disincentive to do that. An open source tool does not.
3. **Content compounds.** "The federal funding nonprofits do not know they can access"
   writes itself, with every number computed live by the tool, per state and per program
   area. Fifty state-level pass-through analyses is fifty pieces of genuinely new
   journalism that nobody else can produce, and each one is a page on
   awards.opengrants.io that ranks and gets cited.

---

## Re-verification checklist

Before any public copy quotes a competitor:

- [ ] Instrumentl pricing, from instrumentl.com/pricing, dated
- [ ] Candid Foundation Directory pricing, from candid.org, dated
- [ ] Cause IQ pricing, from causeiq.com, dated
- [ ] Grant Gopher pricing, dated
- [ ] Plinth pricing, if it has become public, dated
- [ ] Confirm Instrumentl has not shipped a federal award history or subaward feature
- [ ] Confirm HigherGov has not added Schedule of Expenditures of Federal Awards data
- [ ] Re-run the open source search in `prior-art.md`

Comparison source used for the pre-existing figures:
<https://fundingforgood.org/comparing-grant-research-databases/>
