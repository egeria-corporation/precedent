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
from precedent.analysis.passthrough import PassthroughResult, build_passthrough
from precedent.analysis.profile import (
    DEFAULT_LOOKBACK_YEARS,
    Profile,
    build_profile,
    fiscal_year,
    fiscal_year_end,
    fiscal_year_start,
)
from precedent.analysis.recipient import (
    RecipientProfile,
    build_recipient_profile,
    classify_identifier,
    normalize_ein,
)
from precedent.cache import oldest
from precedent.config import Config
from precedent.errors import MissingCredential
from precedent.http import HttpClient
from precedent.sources.fac import Fac
from precedent.sources.opengrants import Enrichment, keyword_from_title, open_opportunities
from precedent.sources.usaspending import (
    ProgramSearch,
    UsaSpending,
    build_filters,
    build_recipient_filters,
)

# How far past the window to fetch. See award_history: action_date is not the cohort date.
FETCH_OVERHANG_YEARS = 1


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
    enrichment: Enrichment | None = None

    def as_dict(self) -> dict[str, Any]:
        """The JSON shape. The disclosure is in it, in every shape, always."""
        out: dict[str, Any] = {
            **self.profile.as_dict(),
            "provenance": self.provenance.as_dict(),
            "disclosure": self.disclosure,
        }
        if self.enrichment is not None:
            out["open_opportunities"] = self.enrichment.as_dict()
        return out


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

    The fetch runs a year past the end of the window. ``action_date`` filters an award on
    its transaction activity, not on the first obligation that decides its cohort year, so
    an award obligated inside the window that saw a later modification is only returned by
    the wider pull. Stopping at the window's own last day loses 521 of the 1,058 awards
    that belong to FY2020-FY2024 for Assistance Listing 93.243. Those awards are still
    bucketed by ``Base Obligation Date``, so the extra year widens what is *fetched* and
    never what is *counted*.
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
            fiscal_year_end(until_fy + FETCH_OVERHANG_YEARS).isoformat(),
            recipient_states=states,
        )
        source = UsaSpending(client)
        awards, retrieved = source.search(filters)
        # Optional, non-fatal, and never mentioned when absent. See sources/opengrants.py.
        enrichment = _enrich(client, source, program, config, no_cache)
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
        provenance=Provenance(
            sources=["usaspending"] + (["opengrants"] if enrichment else []),
            retrieved=oldest([retrieved]),
        ),
        enrichment=enrichment,
    )


def _enrich(
    client: HttpClient,
    source: UsaSpending,
    program: str,
    config: Config,
    no_cache: bool | None,
) -> Enrichment | None:
    """The open call for this program, when a key is set. Never raises, never complains.

    The title comes from the listing search because the enrichment API matches text and
    knows nothing about Assistance Listing numbers.
    """
    if not config.opengrants_api_key:
        return None
    try:
        found = source.find_programs(program, limit=1, no_cache=no_cache)
        title = found.programs[0].title if found.programs else None
    except Exception:
        return None
    return open_opportunities(
        client,
        keyword_from_title(title),
        api_key=config.opengrants_api_key,
        no_cache=no_cache,
    )


@dataclass
class PassthroughOutcome:
    result: PassthroughResult
    provenance: Provenance
    disclosure: str = field(default=DISCLOSURE)

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.result.as_dict(),
            "provenance": self.provenance.as_dict(),
            "disclosure": self.disclosure,
        }


DEFAULT_PASSTHROUGH_YEARS = 5


def passthrough(
    state: str,
    *,
    program: str | None = None,
    since_audit_year: int | None = None,
    until_audit_year: int | None = None,
    fuzzy: bool = False,
    config: Config | None = None,
    http: HttpClient | None = None,
    no_cache: bool | None = None,
) -> PassthroughOutcome:
    """Who passes federal money down to organizations in one state.

    Four requests per batch of audits, not one join: FAC asks partners for small restrictive
    queries and its own documentation says to join client side. The two award pulls are
    deliberately separate because they answer opposite questions - who funded these
    auditees, and whom did these auditees fund - and a single pull filtered afterwards would
    have to fetch the whole state's schedule to do it.
    """
    requested_since = since_audit_year
    if since_audit_year is None or until_audit_year is None:
        this_year = datetime.now().year
        # Audits are filed months after a fiscal year ends, so the most recent year with
        # meaningful coverage is behind the calendar.
        until_audit_year = until_audit_year if until_audit_year is not None else this_year - 1
        since_audit_year = (
            since_audit_year
            if since_audit_year is not None
            else until_audit_year - DEFAULT_PASSTHROUGH_YEARS + 1
        )

    config = config or Config.from_env()
    owned = http is None
    client = http or HttpClient(config)
    try:
        fac = Fac(client)
        audits, at_audits = fac.audits(
            state=state,
            since_year=since_audit_year,
            until_year=until_audit_year,
            no_cache=no_cache,
        )
        report_ids = [a.report_id for a in audits if a.report_id]
        indirect, at_indirect = fac.sefa_awards(
            listing=program,
            report_ids=report_ids,
            received_through_someone=True,
            no_cache=no_cache,
        )
        named, at_named = fac.passthroughs(report_ids, no_cache=no_cache)
        supply, at_supply = fac.sefa_awards(
            listing=program,
            report_ids=report_ids,
            passed_money_down=True,
            no_cache=no_cache,
        )
    finally:
        if owned:
            client.close()

    retrieved = oldest([at_audits, at_indirect, at_named, at_supply])
    result = build_passthrough(
        state=state,
        program=program,
        audits=audits,
        indirect_awards=indirect,
        passthroughs=named,
        supply_awards=supply,
        retrieved=retrieved,
        requested_since_year=requested_since,
        fuzzy=fuzzy,
    )
    return PassthroughOutcome(
        result=result,
        provenance=Provenance(sources=["fac"], retrieved=retrieved),
    )


@dataclass
class RecipientOutcome:
    profile: RecipientProfile
    provenance: Provenance
    disclosure: str = field(default=DISCLOSURE)

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.profile.as_dict(),
            "provenance": self.provenance.as_dict(),
            "disclosure": self.disclosure,
        }


RECIPIENT_LOOKBACK_YEARS = 10
RECIPIENT_AUDIT_YEARS = 6


def recipient_profile(
    identifier: str,
    *,
    config: Config | None = None,
    http: HttpClient | None = None,
    no_cache: bool | None = None,
) -> RecipientOutcome:
    """One organization, by Unique Entity Identifier, Employer Identification Number, or name.

    The three identifiers do not reach the same places. USAspending has no EIN field, so an
    EIN can only be resolved through a single audit - which then yields the Unique Entity
    Identifier that opens USAspending. That bridge is why this asks FAC first for an EIN
    rather than reporting nothing.

    A missing FAC key is not an error here. `history` and `programs` need no key and this
    should not either; it returns the USAspending half and says in a caveat what the other
    half would have added.
    """
    kind = classify_identifier(identifier)
    config = config or Config.from_env()
    owned = http is None
    client = http or HttpClient(config)

    audits: list[Any] = []
    sefa: list[Any] = []
    named: list[Any] = []
    awards: list[Any] = []
    dates: list[datetime | None] = []
    fac_available = bool(config.fac_api_key)

    try:
        if fac_available:
            fac = Fac(client)
            until = datetime.now().year - 1
            since = until - RECIPIENT_AUDIT_YEARS + 1
            audits, at = fac.audits(
                ein=normalize_ein(identifier) if kind == "ein" else None,
                uei=identifier if kind == "uei" else None,
                name=identifier if kind == "name" else None,
                since_year=since,
                until_year=until,
                no_cache=no_cache,
            )
            dates.append(at)
            report_ids = [a.report_id for a in audits if a.report_id]
            if report_ids:
                sefa, at_s = fac.sefa_awards(report_ids=report_ids, no_cache=no_cache)
                named, at_p = fac.passthroughs(report_ids, no_cache=no_cache)
                dates += [at_s, at_p]

        # An EIN cannot be sent to USAspending. If an audit supplied the Unique Entity
        # Identifier, use that instead: crossing to FAC first is the whole point.
        search_term = identifier
        if kind == "ein":
            search_term = next((a.auditee_uei for a in audits if a.auditee_uei), "")
        if search_term:
            today = datetime.now().date()
            end = fiscal_year_end(fiscal_year(today))
            start = fiscal_year_start(fiscal_year(today) - RECIPIENT_LOOKBACK_YEARS)
            awards, at_a = UsaSpending(client).search(
                build_recipient_filters(search_term, start.isoformat(), end.isoformat())
            )
            dates.append(at_a)
    except MissingCredential:
        fac_available = False
    finally:
        if owned:
            client.close()

    profile = build_recipient_profile(
        query=identifier,
        identifier_kind=kind,
        awards=awards,
        audits=audits,
        sefa_awards=sefa,
        passthroughs=named,
        fac_available=fac_available,
    )
    return RecipientOutcome(
        profile=profile,
        provenance=Provenance(sources=profile.sources, retrieved=oldest(dates)),
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
