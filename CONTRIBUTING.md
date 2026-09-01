# Contributing to precedent

Thanks for helping. This document is short on purpose. The rules that matter here are
about data honesty and test discipline, not about code style, which is enforced
automatically.

## What this project is

One job: report the historical awardee profile for a federal assistance program, and
identify the organizations that pass federal money through to smaller organizations in a
given state. Everything else is out of scope. Read
[`docs/NON-GOALS.md`](docs/NON-GOALS.md) before proposing a feature, because the answer to
most feature requests is written there in advance and it is no.

## Setup

Requires Python 3.11 or newer and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/egeria-corporation/precedent
cd precedent
uv sync --all-extras
cp .env.example .env        # then fill in FAC_API_KEY
uv run precedent history 93.243
```

Lint, format, and test:

```bash
uv run ruff check .
uv run ruff format .
uv run pytest
```

Continuous integration runs exactly those three on every push and pull request. A pull
request with a red build will not be reviewed.

## The test rule

**Every change that touches a data source needs a fixture test built from a real captured
response.** Not a hand-written dictionary shaped like the response. A real one.

Both upstream APIs change without warning, and a mocked-shape test passes happily while
production breaks. Fixtures live in `tests/fixtures/`, are small, are committed, and carry
a sidecar `.meta.json` recording the exact request, the retrieval date, and the endpoint
version.

To capture a new fixture:

```bash
uv run python -m precedent.devtools.capture_fixture \
  --source usaspending --name spending_by_award_93243_fy2024
```

Trim the captured file to the smallest number of records that still exercises the code
path. Fixtures over about 200 KB should be trimmed further or justified in the pull
request.

If you have no `FAC_API_KEY`, you can still work on everything except live Federal Audit
Clearinghouse calls, because the FAC tests run entirely off committed fixtures.

## The data honesty rules

These are not negotiable and a pull request that breaks one will be rejected even if the
code is good.

1. **Every derived output carries its source and its retrieval or filing date.** No bare
   numbers.
2. **Every pass-through result states the single audit threshold limitation.** The
   threshold was $750,000 and rose to $1,000,000 for fiscal years beginning on or after
   2024-10-01. Organizations under the threshold file nothing, so they are missing rather
   than zero. If you add a new pass-through output surface, it carries this disclosure.
   There is no compact mode, no `--quiet` that suppresses it, and no JSON shape that omits
   it.
3. **Counts derived from single audit data are described as floors, never as totals.**
4. **No output makes an eligibility determination, predicts an outcome, or gives legal,
   tax, or accounting advice.** "Your client is a good fit for this program" is not a
   sentence this tool is allowed to produce.
5. **The required disclosure text appears in the command output footer**, verbatim, exactly
   as it appears in the README.
6. **When a statistic is uncertain, say why in the output.** The multi-Assistance-Listing
   caveat and the truncated-lookback flag are the existing examples. Follow the pattern.

## Architecture rule

Core logic lives in the library. The command line interface and the MCP server are both
thin adapters over it.

Business logic in a CLI command handler is a bug, not a style preference. A concrete test:
if you cannot call the feature from the MCP server without copying code, the logic is in
the wrong place. The same applies in reverse.

## Changing a statistic

Changing how the median, the new-entrant rate, the repeat-winner rate, or any bucket
boundary is computed is a **breaking change**, because consultants will have quoted the old
number to clients.

Such a change requires, in the same pull request:

- an entry in `CHANGELOG.md` under a new minor or major version,
- an update to the definitions table in the README and the specification in
  `prompts/01-build-core.md`,
- a test that pins the new value against a committed fixture,
- a one-paragraph note in the pull request explaining why the old definition was wrong.

## Adding an alias to the pass-through name table

Pass-through entity names in single audit filings are free text. The clustering table in
`src/precedent/data/passthrough_aliases.yaml` maps raw variants to canonical entities.

To add one, include in the pull request the exact raw strings you observed, the state, and
at least one `report_id` where each appears, so a reviewer can verify it against the source
filing. Never merge entities across states. When in doubt, leave them separate: a split
entity understates a count, a wrongly merged entity produces a fact that is not true.

## Upstream first

If the bug is in USAspending, the Federal Audit Clearinghouse, or a community project we
depend on, open the issue or pull request there first, then note it in
[`docs/research/prior-art.md`](docs/research/prior-art.md) with a link. Local workarounds
are acceptable as a bridge and should carry a comment linking the upstream issue and the
condition under which the workaround can be removed.

## Reporting a data problem

If a number looks wrong, open an issue with the exact command, the full output, the
retrieval date, and what you believe the correct answer is with a link to the source
filing or award record. Data bugs are the highest priority issue type in this repository.

## Security

Never commit a key. `.env` is gitignored, `.env.example` documents the variables, and
continuous integration uses repository secrets. If you find a security issue, follow
[`SECURITY.md`](SECURITY.md) rather than opening a public issue.

## Code of conduct

Participation is governed by [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

## License

Contributions are accepted under the Apache License 2.0, the same license as the project.
