# Changelog

All notable changes to `precedent` are documented here. This project follows [Semantic Versioning](https://semver.org/) and the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Added
- Repository scaffolding: documentation, research dossier, and build prompts.

### Added
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
- Awards whose `Award Amount` is null, zero or negative leave the universe entirely rather
  than only the amount statistics. That figure is an award's lifetime obligation, so at or
  below zero the award was unwound and funded nobody; counting those organizations as
  recipients inflated the new-entrant rate for 93.243 from 39.1% to 51.9%.
