"""The public library surface. The CLI and the MCP server both call only this.

If a feature cannot be reached from the MCP server without copying code out of a command
handler, it is in the wrong place. That rule is why this module exists.

Every return value carries its provenance: which sources fed it and the *oldest* retrieval
date among them, so a result assembled from a week-old cache says a week rather than today.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from precedent import DISCLOSURE
from precedent.analysis.profile import (
    DEFAULT_LOOKBACK_YEARS,
    Profile,
    build_profile,
    fiscal_year,
    fiscal_year_end,
    fiscal_year_start,
)
from precedent.cache import oldest
from precedent.config import Config
from precedent.http import HttpClient
from precedent.sources.usaspending import (
    ProgramSearch,
    UsaSpending,
    build_filters,
)


@dataclass
class Provenance:
    """Where a result came from and how old its stalest input is."""

    sources: list[str]
    retrieved: datetime | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "sources": self.sources,
            "retrieved": self.retrieved.isoformat(timespec="seconds") if self.retrieved else None,
        }


@dataclass
class HistoryResult:
    profile: Profile
    provenance: Provenance
    disclosure: str = field(default=DISCLOSURE)

    def as_dict(self) -> dict[str, Any]:
        """The JSON shape. The disclosure is in it, in every shape, always."""
        return {
            **self.profile.as_dict(),
            "provenance": self.provenance.as_dict(),
            "disclosure": self.disclosure,
        }


@dataclass
class ProgramsResult:
    search: ProgramSearch
    provenance: Provenance
    disclosure: str = field(default=DISCLOSURE)

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.search.matched_term,
            "narrowed_from_phrase": self.search.fell_back,
            "programs": [
                {"number": p.number, "title": p.title, "popular_name": p.popular_name}
                for p in self.search.programs
            ],
            "provenance": self.provenance.as_dict(),
            "disclosure": self.disclosure,
        }


def default_window(today: datetime | None = None) -> tuple[int, int]:
    """The last five complete federal fiscal years.

    The current fiscal year is deliberately excluded: it is partial, and a partial year
    dragged into a cohort statistic reads as a collapse in awards that has not happened.
    """
    now = today or datetime.now()
    current_fy = fiscal_year(now.date())
    until = current_fy - 1
    return until - 4, until


def award_history(
    program: str,
    *,
    since_fy: int | None = None,
    until_fy: int | None = None,
    lookback_years: int = DEFAULT_LOOKBACK_YEARS,
    states: list[str] | None = None,
    config: Config | None = None,
    http: HttpClient | None = None,
    no_cache: bool | None = None,
) -> HistoryResult:
    """Award history and the new-entrant rate for one Assistance Listing.

    One pull covers the window and its lookback together, because an award straddles both
    and two pulls would fetch the boundary twice and disagree about it.
    """
    if since_fy is None or until_fy is None:
        auto_since, auto_until = default_window()
        since_fy = since_fy if since_fy is not None else auto_since
        until_fy = until_fy if until_fy is not None else auto_until

    config = config or Config.from_env()
    owned = http is None
    client = http or HttpClient(config)
    try:
        filters = build_filters(
            program,
            fiscal_year_start(since_fy - lookback_years).isoformat(),
            fiscal_year_end(until_fy).isoformat(),
            recipient_states=states,
        )
        awards, retrieved = UsaSpending(client).search(filters)
    finally:
        if owned:
            client.close()

    profile = build_profile(
        awards,
        program=program,
        since_fy=since_fy,
        until_fy=until_fy,
        lookback_years=lookback_years,
    )
    return HistoryResult(
        profile=profile,
        provenance=Provenance(sources=["usaspending"], retrieved=oldest([retrieved])),
    )


def find_programs(
    search_text: str,
    *,
    limit: int = 20,
    config: Config | None = None,
    http: HttpClient | None = None,
    no_cache: bool | None = None,
) -> ProgramsResult:
    """Assistance Listings matching a keyword or a partial number."""
    config = config or Config.from_env()
    owned = http is None
    client = http or HttpClient(config)
    try:
        found = UsaSpending(client).find_programs(search_text, limit=limit, no_cache=no_cache)
    finally:
        if owned:
            client.close()
    return ProgramsResult(
        search=found,
        provenance=Provenance(sources=["usaspending"], retrieved=found.retrieved),
    )
