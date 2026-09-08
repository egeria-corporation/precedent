"""What a pass-through answer does not cover, attached to every pass-through answer.

Single audits are filed only by organizations that expend at or above the federal single
audit threshold. Everyone below it files nothing, so they are **absent from this data, not
counted as zero**. A subrecipient count from this source is therefore a floor, and a reader
who does not know that will read a floor as a total and conclude that a program reaches
twelve organizations when it reaches two hundred.

That is why there is no flag to remove this object. It is built here, it rides on every
JSON payload and every rendered surface, and the count fields are named so the qualification
travels with the number rather than sitting in a footnote somebody skipped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from precedent.sources.fac import COVERAGE_START_YEAR

THRESHOLD_OLD = 750_000
THRESHOLD_NEW = 1_000_000
THRESHOLD_EFFECTIVE = "fiscal years beginning on or after 2024-10-01"

THRESHOLD_NOTE = (
    "Single audits are only filed by organizations that expend at or above the federal "
    "single audit threshold in a fiscal year. That threshold was $750,000 and rose to "
    "$1,000,000 for fiscal years beginning on or after 2024-10-01. Organizations below the "
    "threshold file nothing, so they are absent from this data entirely, not counted as "
    "zero. This list is therefore skewed toward larger recipients and larger "
    "intermediaries, and every subrecipient count is a floor rather than a total."
)

FAC_VINTAGE_NOTE = "FAC production refreshes weekly, typically Wednesdays"


@dataclass
class PassthroughCoverage:
    """The qualification that travels with every pass-through number."""

    state: str
    audits_scanned: int
    audit_years: list[int]
    unattributed_indirect_lines: int
    fac_retrieved: str | None
    threshold_note: str = THRESHOLD_NOTE
    threshold_old: int = THRESHOLD_OLD
    threshold_new: int = THRESHOLD_NEW
    threshold_effective: str = THRESHOLD_EFFECTIVE
    counts_are_floors: bool = True
    fac_earliest_audit_year: int = COVERAGE_START_YEAR
    fac_data_vintage_note: str = FAC_VINTAGE_NOTE
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)


def build_coverage(
    *,
    state: str,
    audits_scanned: int,
    audit_years: list[int],
    unattributed_indirect_lines: int,
    retrieved: datetime | None,
    requested_since_year: int | None = None,
) -> PassthroughCoverage:
    """Assemble the coverage object, including anything else the caller should be told."""
    notes: list[str] = []
    if requested_since_year is not None and requested_since_year < COVERAGE_START_YEAR:
        notes.append(
            f"Audit years before {COVERAGE_START_YEAR} were requested but this API does not "
            f"serve them; earlier single audits are in the legacy Census extracts. The window "
            f"was clamped to {COVERAGE_START_YEAR}."
        )
    if unattributed_indirect_lines:
        notes.append(
            f"{unattributed_indirect_lines:,} award line(s) report money received through a "
            "pass-through entity without naming one. They are counted here and excluded from "
            "every cluster, because attributing them to anybody would be a guess."
        )
    if not audits_scanned:
        notes.append(
            "No single audits were found for this state and window, which usually means the "
            "filter is wrong rather than that no organization received federal money."
        )
    return PassthroughCoverage(
        state=state,
        audits_scanned=audits_scanned,
        audit_years=sorted(audit_years),
        unattributed_indirect_lines=unattributed_indirect_lines,
        fac_retrieved=retrieved.date().isoformat() if retrieved else None,
        notes=notes,
    )
