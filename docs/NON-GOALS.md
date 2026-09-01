# Non-goals

What `precedent` will never do, written down in advance so that the answer to a feature
request is a decision that was already made rather than an argument.

The rule behind all of these: this tool does one job, which is telling you who has
historically won a federal assistance program and who passes federal money down to smaller
organizations. When a feature would turn it into a platform, the answer is no.

---

## It will not tell you whether to apply

`precedent` reports what happened. It does not score fit, rank opportunities, produce a
"win probability", or say a client is a good candidate. A new-entrant rate of 39% is a
fact. "You should apply" is advice, and advice is what the consultant using this tool is
paid for. Building a recommendation engine would make the tool both less trustworthy and
less useful, because a consultant cannot defend a number they did not derive.

## It will not make eligibility determinations

Eligibility is set by statute, by the Notice of Funding Opportunity, and by the applicant's
own registration and audit status. This tool reads none of those authoritatively. Every
output carries the disclosure that it is not an eligibility determination, and no flag
removes that.

## It will not become a grant search engine

Finding open opportunities is a solved problem with several free and paid answers,
including Grants.gov, SAM.gov, and OpenGrants. `precedent` answers a question those
products do not: what does the winner of this program usually look like. Where the live
opportunity is genuinely useful next to the history, `precedent` links out or pulls a small
enrichment section from the OpenGrants API. It does not index opportunities, does not
maintain its own opportunity database, and does not add filters, saved searches, or alerts
for them.

## It will not become a customer relationship manager

No contact management, no outreach tracking, no notes on intermediaries, no pipeline, no
stages, no reminders. The pass-through finder produces a list. What you do with the list
happens somewhere else. The sibling `grantdesk` repository is where workflow lives.

## It will not write anything

No proposal drafting, no narrative generation, no letter of inquiry templates, no
summarization of a Notice of Funding Opportunity into talking points. The sibling
`answerbank` repository handles reusable proposal content.

## It will not host a hosted database of its own

`precedent` is a client. It reads two public APIs, caches responses on your machine, and
computes statistics locally. It does not stand up a warehouse, does not require Postgres,
does not ship a Docker Compose file, and does not need a migration step. If a feature would
require a persistent server-side datastore to work, it belongs in the hosted companion at
awards.opengrants.io, not in the tool.

## It will not add authentication, accounts, or usage tracking

No login, no telemetry, no phone-home, no anonymous usage statistics, no license check. The
only credentials it touches are the two documented in `.env.example`, and one of those is
optional.

## It will not predict future awards

No forecasting of the next round, no estimated award date, no modeling of agency budget
outcomes. Federal appropriations do not behave the way a forecast would need them to, and a
confidently wrong prediction is worse than no prediction.

## It will not silently fill gaps in single audit coverage

Organizations below the single audit threshold do not file. It would be technically
possible to estimate what they are receiving and present a smoothed, complete-looking
picture. That is exactly the thing a certified public accountant would correctly tear
apart, and it would destroy the credibility that makes the pass-through view valuable in
the first place. Missing data is reported as missing. Counts are reported as floors. Where
an estimate would help, it appears as a separately labeled estimate with its method stated,
never blended into an observed count.

## It will not merge pass-through entities across states

Two organizations with similar names in different states are two organizations until proven
otherwise. The clustering table errs toward splitting, because an understated count is a
smaller error than a fact that is not true.

## It will not resell or mirror the underlying datasets

USAspending data is public domain, and the Federal Audit Clearinghouse publishes terms of
use. `precedent` reads from the live APIs and caches locally for performance. It does not
republish bulk copies of either dataset, and any derived dataset the hosted companion
publishes carries source attribution, vintage, and a link back to the original.

## It will not support non-United-States funding

Federal assistance awards and single audits under 2 CFR 200. That is the scope.

## It will not add a graphical user interface

The command line interface is the human surface, the MCP server is the agent surface, and
awards.opengrants.io is the web surface. A fourth interface inside the package is not a
fourth audience, it is a fourth thing to maintain.

## It will not target sub-award data from FSRS as its primary pass-through source

The Federal Funding Accountability and Transparency Act Subaward Reporting System collects
subaward reports from prime recipients above a threshold, and that data flows into
USAspending. It is real and it is worth linking to, but for assistance awards it is
substantially incomplete, and it reflects what primes chose to report rather than what
auditors verified. The Schedule of Expenditures of Federal Awards is the better source for
this question, and choosing it is the entire differentiated bet of this repository.
Supporting FSRS as a supplementary cross-check is acceptable. Making it the backbone is
not.

---

## How to propose something anyway

If you believe a feature belongs here despite the above, open an issue that answers three
questions: which single job it serves, what it would replace rather than add, and what a
consultant would stop doing manually because of it. Features that only add are the ones
that turn a tool into a platform.
