# Changelog

All notable changes to `precedent` are documented here. This project follows [Semantic Versioning](https://semver.org/) and the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Added
- Repository scaffolding: documentation, research dossier, and build prompts.

### Added
- `analysis/passthrough.py`, `analysis/coverage.py`, `precedent passthrough`: who passes
  federal money down to organizations in one state. Two evidence streams computed
  separately - organizations reporting money received through somebody, and organizations
  reporting they passed money down - merged only for display. Clustering is the committed
  alias table plus exact normalized match within one state; `--fuzzy` is opt-in and names
  everything it merged. Every result carries the single-audit threshold note, because a
  subrecipient count from this source is a floor and reads like a total.
- `sources/fac.py`: the Federal Audit Clearinghouse client. PostgREST helpers, `in.(...)`
  chunked at 100 identifiers, pagination that always sends `order=` and stops at a hard
  bound, and the `is_direct` / `is_passthrough_award` distinction that decides whether an
  auditee received money through somebody or passed it down. Fixtures captured from the
  live API.

### Fixed
- `award_history` fetches a year past the window it reports on. `action_date` filters on an
  award's transaction activity, not on the `Base Obligation Date` that decides its cohort
  year, so awards obligated inside the window and modified after it were never fetched -
  521 of the 1,058 that belong to FY2020-FY2024 for Assistance Listing 93.243.
- The `is_direct` and `is_passthrough_award` filters use `eq.N` / `eq.Y`, not `is.false` /
  `is.true`. Those columns are text in FAC's schema, and PostgREST rejects an IS predicate
  against text with HTTP 400. The build prompt specifies the IS form and it does not work.
- Awards whose `Award Amount` is null, zero or negative leave the universe entirely rather
  than only the amount statistics. That figure is an award's lifetime obligation, so at or
  below zero the award was unwound and funded nobody; counting those organizations as
  recipients inflated the new-entrant rate for 93.243 from 39.1% to 51.9%.
