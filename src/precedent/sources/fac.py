"""Federal Audit Clearinghouse: who actually handed the money over.

USAspending records the award the federal government made. It does not record what happened
next. When a state agency takes a formula grant and re-grants it to forty community
organizations, USAspending shows one award to the state; the forty never appear. Single
audits do record it, because an organization spending federal money above the threshold must
file a Schedule of Expenditures of Federal Awards naming who passed the money to it.

This client fetches and shapes. It computes nothing and clusters nothing: the normalization
problem lives in ``analysis/``, because ``passthrough_name`` is free text an auditee typed
and pretending otherwise is how a pass-through tool produces confident nonsense.

Five things here exist because getting them wrong is the documented failure mode:

* **There is no Assistance Listing column.** It is ``federal_agency_prefix`` and
  ``federal_award_extension``, and a query has to filter on both halves separately.
* **PostgREST does not guarantee an order.** A paginated loop without an explicit ``order``
  silently skips and duplicates rows - it does not error, it just returns the wrong answer.
  Every paginated call here orders by a key unique enough to be total.
* **Every loop is bounded.** FAC issues one key per person and the rate limit is per key, so
  a pagination bug must not be able to spend the user's whole quota. Past the bound this
  raises rather than continuing.
* **The boolean columns are not booleans.** The FAC data dictionary types ``is_direct``,
  ``is_passthrough_award``, ``is_major`` and ``is_loan`` as boolean; the API sends the
  strings ``"Y"`` and ``"N"``, both of which are truthy in Python. Reading one straight
  marks every row direct.
* **``is_direct`` and ``is_passthrough_award`` are opposite ends of the same pipe.**
  ``is_direct = false`` means this auditee *received* money through somebody, named in the
  ``/passthrough`` rows for the same ``(report_id, award_reference)``.
  ``is_passthrough_award = true`` means this auditee *passed money down* to its own
  subrecipients. Confusing them inverts the entire feature.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from precedent.errors import TooMuchData, fac_key_missing
from precedent.http import HttpClient

SOURCE = "fac"
ROOT = "https://api.fac.gov"
GENERAL_URL = f"{ROOT}/general"
FEDERAL_AWARDS_URL = f"{ROOT}/federal_awards"
PASSTHROUGH_URL = f"{ROOT}/passthrough"
NOTES_URL = f"{ROOT}/notes_to_sefa"

# FAC caps a response at 20,000 rows and asks partners for small restrictive queries; its
# own guidance suggests pages of about 5,000.
PAGE_LIMIT = 5_000
HARD_ROW_CAP = 20_000

# The bound. One key per person, rate limited per key, so a loop that fails to terminate
# spends somebody's quota rather than ours. Twelve pages of 5,000 is a deliberate ceiling,
# not a guess at what any real query needs.
MAX_PAGES = 12
MAX_ROWS = PAGE_LIMIT * MAX_PAGES

# `in.(...)` grows the URL, and a very long one is rejected by intermediaries before it
# reaches PostgREST. The research notes settle on roughly a hundred identifiers per request.
IN_CHUNK = 100

# Audit years 2016 forward. Earlier single audits are in the legacy Census extracts, which
# this API does not serve, so a window reaching before it is truncated and must say so.
COVERAGE_START_YEAR = 2016

# What the text "boolean" columns actually hold, and therefore what a filter has to compare
# against. See the module docstring.
TRUE_VALUE = "Y"
FALSE_VALUE = "N"

# `auditee_uei` is not always an identifier. Records migrated from the legacy Census
# collection carry the literal string "GSA_MIGRATION" in that column: 36,989 of 36,991
# audits in 2016 and 37,342 of 37,409 in 2019, against 1 in 2022 and 0 in 2023 (measured
# 2026-09-13). Treated as a value it silently joins tens of thousands of unrelated
# organizations to each other, so it is parsed to None and a UEI lookup is understood to
# reach only the years after the migration.
UEI_PLACEHOLDER = "GSA_MIGRATION"
UEI_COVERAGE_FROM_YEAR = 2020

GENERAL_FIELDS = (
    "report_id",
    "audit_year",
    "auditee_name",
    "auditee_ein",
    "auditee_uei",
    "auditee_city",
    "auditee_state",
    "entity_type",
    "total_amount_expended",
    "fy_start_date",
    "fy_end_date",
    "fac_accepted_date",
)

AWARD_FIELDS = (
    "report_id",
    "award_reference",
    "federal_agency_prefix",
    "federal_award_extension",
    "federal_program_name",
    "amount_expended",
    "is_direct",
    "is_passthrough_award",
    "passthrough_amount",
    "cluster_name",
    "federal_program_total",
    "is_major",
    "is_loan",
    "findings_count",
    "additional_award_identification",
    "audit_year",
    "auditee_uei",
)

PASSTHROUGH_FIELDS = (
    "report_id",
    "award_reference",
    "passthrough_name",
    "passthrough_id",
    "audit_year",
    "auditee_uei",
)

NOTE_FIELDS = ("report_id", "title", "content", "accounting_policies", "is_minimis_rate_used")


def assistance_listing(prefix: str | None, extension: str | None) -> str | None:
    """``"93"`` and ``"045"`` become ``"93.045"``.

    FAC publishes no single Assistance Listing column, which is the most common way a
    reader of this data ends up filtering on the wrong thing.
    """
    if not prefix or not extension:
        return None
    return f"{prefix.strip()}.{extension.strip()}"


def split_listing(listing: str) -> tuple[str, str]:
    """``"93.045"`` becomes ``("93", "045")``, the two columns FAC actually filters on."""
    text = listing.strip()
    if "." not in text:
        raise ValueError(f"{listing!r} is not an Assistance Listing number, e.g. 93.045")
    prefix, extension = text.split(".", 1)
    if not prefix or not extension:
        raise ValueError(f"{listing!r} is not an Assistance Listing number, e.g. 93.045")
    return prefix, extension


def chunked(values: Sequence[str], size: int = IN_CHUNK) -> Iterator[list[str]]:
    """Identifiers in batches small enough for one ``in.(...)`` filter."""
    for start in range(0, len(values), size):
        yield list(values[start : start + size])


def in_filter(values: Iterable[str]) -> str:
    """PostgREST ``in.(a,b,c)``, quoting so a comma or space in a value cannot split it."""
    quoted = ",".join('"' + str(v).replace('"', '""') + '"' for v in values)
    return f"in.({quoted})"


@dataclass(frozen=True)
class Audit:
    """One single-audit submission, from ``/general``."""

    report_id: str
    audit_year: str | None
    auditee_name: str | None
    auditee_ein: str | None
    auditee_uei: str | None
    auditee_city: str | None
    auditee_state: str | None
    entity_type: str | None
    total_amount_expended: int | None
    fy_start_date: str | None
    fy_end_date: str | None
    fac_accepted_date: str | None


@dataclass(frozen=True)
class SefaAward:
    """One line of a Schedule of Expenditures of Federal Awards."""

    report_id: str
    award_reference: str | None
    federal_agency_prefix: str | None
    federal_award_extension: str | None
    federal_program_name: str | None
    amount_expended: int | None
    is_direct: bool | None
    is_passthrough_award: bool | None
    passthrough_amount: int | None
    cluster_name: str | None
    federal_program_total: int | None
    is_major: bool | None
    is_loan: bool | None
    findings_count: int | None
    additional_award_identification: str | None
    audit_year: str | None
    auditee_uei: str | None

    @property
    def listing(self) -> str | None:
        return assistance_listing(self.federal_agency_prefix, self.federal_award_extension)

    @property
    def key(self) -> tuple[str, str | None]:
        """What ``/passthrough`` rows join on."""
        return (self.report_id, self.award_reference)

    @property
    def received_through_someone(self) -> bool:
        """This auditee got the money from a pass-through entity, not from the agency."""
        return self.is_direct is False

    @property
    def passed_money_down(self) -> bool:
        """This auditee handed money to its own subrecipients."""
        return bool(self.is_passthrough_award) and (self.passthrough_amount or 0) > 0


@dataclass(frozen=True)
class PassThrough:
    """Who an auditee says passed money to it, from ``/passthrough``.

    ``name`` is free text the auditee typed and ``identifier`` may be a state contract
    number, a Unique Entity Identifier, an Employer Identification Number, or blank. There
    is no state, no EIN for the entity, and no canonical identifier anywhere in this record.
    """

    report_id: str
    award_reference: str | None
    name: str | None
    identifier: str | None
    audit_year: str | None
    auditee_uei: str | None

    @property
    def key(self) -> tuple[str, str | None]:
        return (self.report_id, self.award_reference)


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return None
    text = str(value).strip().lower()
    if text in ("y", "yes", "true", "t", "1"):
        return True
    if text in ("n", "no", "false", "f", "0"):
        return False
    return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _uei(value: Any) -> str | None:
    """A Unique Entity Identifier, or None for the migration placeholder."""
    text = _text(value)
    return None if text is None or text.upper() == UEI_PLACEHOLDER else text


def to_audit(row: dict[str, Any]) -> Audit:
    return Audit(
        report_id=str(row.get("report_id") or ""),
        audit_year=_text(row.get("audit_year")),
        auditee_name=_text(row.get("auditee_name")),
        auditee_ein=_text(row.get("auditee_ein")),
        auditee_uei=_uei(row.get("auditee_uei")),
        auditee_city=_text(row.get("auditee_city")),
        auditee_state=_text(row.get("auditee_state")),
        entity_type=_text(row.get("entity_type")),
        total_amount_expended=_int(row.get("total_amount_expended")),
        fy_start_date=_text(row.get("fy_start_date")),
        fy_end_date=_text(row.get("fy_end_date")),
        fac_accepted_date=_text(row.get("fac_accepted_date")),
    )


def to_sefa_award(row: dict[str, Any]) -> SefaAward:
    return SefaAward(
        report_id=str(row.get("report_id") or ""),
        award_reference=_text(row.get("award_reference")),
        federal_agency_prefix=_text(row.get("federal_agency_prefix")),
        federal_award_extension=_text(row.get("federal_award_extension")),
        federal_program_name=_text(row.get("federal_program_name")),
        amount_expended=_int(row.get("amount_expended")),
        is_direct=_bool(row.get("is_direct")),
        is_passthrough_award=_bool(row.get("is_passthrough_award")),
        passthrough_amount=_int(row.get("passthrough_amount")),
        cluster_name=_text(row.get("cluster_name")),
        federal_program_total=_int(row.get("federal_program_total")),
        is_major=_bool(row.get("is_major")),
        is_loan=_bool(row.get("is_loan")),
        findings_count=_int(row.get("findings_count")),
        additional_award_identification=_text(row.get("additional_award_identification")),
        audit_year=_text(row.get("audit_year")),
        auditee_uei=_uei(row.get("auditee_uei")),
    )


def to_passthrough(row: dict[str, Any]) -> PassThrough:
    return PassThrough(
        report_id=str(row.get("report_id") or ""),
        award_reference=_text(row.get("award_reference")),
        name=_text(row.get("passthrough_name")),
        identifier=_text(row.get("passthrough_id")),
        audit_year=_text(row.get("audit_year")),
        auditee_uei=_uei(row.get("auditee_uei")),
    )


def year_filter(since_year: int, until_year: int) -> dict[str, str]:
    """An inclusive audit-year range. ``audit_year`` is text in FAC, so it compares as text."""
    return {"and": f"(audit_year.gte.{since_year},audit_year.lte.{until_year})"}


class Fac:
    """The Federal Audit Clearinghouse, one query shape at a time.

    Needs an API key. Every method returns rows and the date they were retrieved; nothing
    here decides what the rows mean.
    """

    def __init__(self, http: HttpClient, api_key: str | None = None) -> None:
        key = api_key if api_key is not None else http.config.fac_api_key
        if not key:
            raise fac_key_missing()
        self.http = http
        self._headers = {"X-Api-Key": key, "Accept": "application/json"}

    def _pages(
        self,
        url: str,
        params: dict[str, str],
        *,
        order: str,
        select: Sequence[str],
        no_cache: bool | None = None,
    ) -> tuple[list[dict[str, Any]], datetime]:
        """Every row matching ``params``, paginated, ordered, and bounded.

        ``order`` is not optional and is not a nicety. PostgREST returns rows in whatever
        order the planner produced, so ``limit``/``offset`` over an unordered result skips
        some rows and repeats others without any error to notice.
        """
        rows: list[dict[str, Any]] = []
        retrieved: datetime | None = None
        for page in range(MAX_PAGES):
            query = {
                **params,
                "select": ",".join(select),
                "order": order,
                "limit": str(PAGE_LIMIT),
                "offset": str(page * PAGE_LIMIT),
            }
            body, fetched_at = self.http.get_json(
                SOURCE, url, params=query, headers=self._headers, no_cache=no_cache
            )
            retrieved = fetched_at if retrieved is None else min(retrieved, fetched_at)
            batch = body if isinstance(body, list) else []
            rows.extend(batch)
            if len(batch) < PAGE_LIMIT:
                return rows, retrieved
        raise TooMuchData(
            f"this Federal Audit Clearinghouse query passed {MAX_ROWS:,} rows without "
            f"finishing ({url.rsplit('/', 1)[-1]}). Narrow it - a single state, a single "
            "Assistance Listing, or a shorter range of audit years - rather than widening "
            "the page bound, which exists so a runaway loop cannot spend your API quota."
        )

    def audits(
        self,
        *,
        state: str | None = None,
        since_year: int | None = None,
        until_year: int | None = None,
        report_ids: Sequence[str] | None = None,
        ein: str | None = None,
        uei: str | None = None,
        name: str | None = None,
        no_cache: bool | None = None,
    ) -> tuple[list[Audit], datetime | None]:
        """Audit submissions, by state and year, by identity, or by explicit report id.

        ``ein`` is the reason this endpoint matters for a recipient lookup: USAspending has
        no Employer Identification Number field at all, and an audit carries both that and
        the Unique Entity Identifier, so FAC is the bridge between the two datasets.
        """
        base = self._window(state=state, since_year=since_year, until_year=until_year)
        if ein:
            base["auditee_ein"] = f"eq.{ein.strip()}"
        if uei:
            base["auditee_uei"] = f"eq.{uei.strip().upper()}"
        if name:
            # Free text typed by a filer, so an exact match would miss almost everything.
            base["auditee_name"] = "ilike.*" + name.strip().replace("*", "") + "*"
        rows, retrieved = self._collect(
            GENERAL_URL,
            select=GENERAL_FIELDS,
            order="report_id.asc",
            base=base,
            id_column="report_id",
            ids=report_ids,
            no_cache=no_cache,
        )
        return [to_audit(r) for r in rows], retrieved

    def sefa_awards(
        self,
        *,
        listing: str | None = None,
        report_ids: Sequence[str] | None = None,
        since_year: int | None = None,
        until_year: int | None = None,
        received_through_someone: bool = False,
        passed_money_down: bool = False,
        no_cache: bool | None = None,
    ) -> tuple[list[SefaAward], datetime | None]:
        """SEFA lines, filtered on both halves of the Assistance Listing number.

        ``received_through_someone`` and ``passed_money_down`` are the two directions of
        the same pipe and are never both true in one query: one asks who funded this
        auditee, the other asks whom this auditee funded.
        """
        if received_through_someone and passed_money_down:
            raise ValueError(
                "received_through_someone and passed_money_down are opposite directions; "
                "ask for one stream at a time"
            )
        base = self._window(since_year=since_year, until_year=until_year)
        # eq.N / eq.Y, not is.false / is.true. These columns are text in FAC's schema
        # despite the data dictionary calling them boolean, and PostgREST rejects an IS
        # predicate against text outright: HTTP 400, "argument of IS FALSE must be type
        # boolean, not type text". The build prompt specifies the IS form; it does not work.
        if received_through_someone:
            base["is_direct"] = f"eq.{FALSE_VALUE}"
        if passed_money_down:
            base["is_passthrough_award"] = f"eq.{TRUE_VALUE}"
            base["passthrough_amount"] = "gt.0"
        if listing:
            prefix, extension = split_listing(listing)
            base["federal_agency_prefix"] = f"eq.{prefix}"
            base["federal_award_extension"] = f"eq.{extension}"
        rows, retrieved = self._collect(
            FEDERAL_AWARDS_URL,
            select=AWARD_FIELDS,
            order="report_id.asc,award_reference.asc",
            base=base,
            id_column="report_id",
            ids=report_ids,
            no_cache=no_cache,
        )
        return [to_sefa_award(r) for r in rows], retrieved

    def passthroughs(
        self,
        report_ids: Sequence[str],
        *,
        no_cache: bool | None = None,
    ) -> tuple[list[PassThrough], datetime | None]:
        """Who passed money to these auditees. Join to SEFA lines on ``key``."""
        if not report_ids:
            return [], None
        rows, retrieved = self._collect(
            PASSTHROUGH_URL,
            select=PASSTHROUGH_FIELDS,
            order="report_id.asc,award_reference.asc",
            base={},
            id_column="report_id",
            ids=report_ids,
            no_cache=no_cache,
        )
        return [to_passthrough(r) for r in rows], retrieved

    def notes(
        self,
        report_ids: Sequence[str],
        *,
        no_cache: bool | None = None,
    ) -> tuple[list[dict[str, Any]], datetime | None]:
        """The auditor's own notes on the schedule, for showing their description."""
        if not report_ids:
            return [], None
        return self._collect(
            NOTES_URL,
            select=NOTE_FIELDS,
            order="report_id.asc",
            base={},
            id_column="report_id",
            ids=report_ids,
            no_cache=no_cache,
        )

    @staticmethod
    def _window(
        *,
        state: str | None = None,
        since_year: int | None = None,
        until_year: int | None = None,
    ) -> dict[str, str]:
        params: dict[str, str] = {}
        if state:
            params["auditee_state"] = f"eq.{state.strip().upper()}"
        if since_year is not None and until_year is not None:
            params.update(year_filter(max(since_year, COVERAGE_START_YEAR), until_year))
        elif since_year is not None:
            params["audit_year"] = f"gte.{max(since_year, COVERAGE_START_YEAR)}"
        elif until_year is not None:
            params["audit_year"] = f"lte.{until_year}"
        return params

    def _collect(
        self,
        url: str,
        *,
        select: Sequence[str],
        order: str,
        base: dict[str, str],
        id_column: str,
        ids: Sequence[str] | None,
        no_cache: bool | None,
    ) -> tuple[list[dict[str, Any]], datetime | None]:
        """One query, or one per chunk of identifiers, with the results concatenated.

        Deduplicated on the ordering key: chunks are disjoint by construction, but a row
        restated between two requests would otherwise be counted twice.
        """
        if ids is None:
            rows, retrieved = self._pages(
                url, dict(base), order=order, select=select, no_cache=no_cache
            )
            return rows, retrieved
        collected: list[dict[str, Any]] = []
        retrieved: datetime | None = None
        seen: set[tuple[Any, ...]] = set()
        order_keys = [part.split(".", 1)[0] for part in order.split(",")]
        for batch in chunked(list(ids)):
            params = {**base, id_column: in_filter(batch)}
            rows, fetched_at = self._pages(
                url, params, order=order, select=select, no_cache=no_cache
            )
            if fetched_at is not None:
                retrieved = fetched_at if retrieved is None else min(retrieved, fetched_at)
            for row in rows:
                signature = tuple(row.get(k) for k in order_keys)
                if signature in seen:
                    continue
                seen.add(signature)
                collected.append(row)
        return collected, retrieved
