"""USAspending: award history for one Assistance Listing. No key, no account.

This client fetches and shapes. It computes nothing: the statistics that make the tool
useful live in ``analysis/``, so that every number here can be checked against USAspending's
own documentation rather than against our arithmetic.

Three things in here exist because getting them wrong is the documented failure mode:

* **Fetch on ``action_date``, bucket on ``Base Obligation Date``.** A window filtered by
  action date returns every award that had *any* transaction in it, including awards first
  obligated years earlier. Cohort statistics need the award's first obligating action, which
  is a different field, so the window is deliberately wide and the bucketing happens later.
* **Keyset pagination, not page numbers.** Page-based paging degrades badly past a few
  thousand records; feeding ``last_record_unique_id`` and ``last_record_sort_value`` back
  stays fast to arbitrary depth.
* **Count before you pull.** A program with more grants than a record-by-record fetch can
  honestly serve gets a typed error naming a narrower query, not a ten-minute hang.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from precedent.errors import TooMuchData
from precedent.http import HttpClient

SOURCE = "usaspending"
ROOT = "https://api.usaspending.gov"
SEARCH_URL = f"{ROOT}/api/v2/search/spending_by_award/"
COUNT_URL = f"{ROOT}/api/v2/search/spending_by_award_count/"
AUTOCOMPLETE_URL = f"{ROOT}/api/v2/autocomplete/cfda/"

# 02 block grant, 03 formula grant, 04 project grant, 05 cooperative agreement. Contract
# codes must never join these in one request: the field vocabulary changes and the API 400s.
GRANT_AWARD_TYPES = ["02", "03", "04", "05"]

# The page size the endpoint allows, and the ceiling above which a record-by-record pull is
# the wrong tool. Both are the build prompt's numbers.
PAGE_LIMIT = 100
MAX_RECORDS = 20_000

FIELDS = [
    "Award ID",
    "Recipient Name",
    "Recipient UEI",
    "Recipient Location",
    "Award Amount",
    "Base Obligation Date",
    "Start Date",
    "End Date",
    "Awarding Agency",
    "Awarding Sub Agency",
    "Place of Performance State Code",
    "Assistance Listings",
    "recipient_id",
]

# The API says so itself, in every response: "time period start and end dates are currently
# limited to an earliest date of 2007-10-01". A lookback that crosses it is
# truncated, and a "never won before" claim resting on it is a claim about our data rather
# than about the world. `analysis` reads this to raise its truncated-lookback flag.
COVERAGE_START = "2007-10-01"


@dataclass(frozen=True)
class Award:
    """One assistance award, as USAspending reports it."""

    generated_internal_id: str
    award_id: str | None
    recipient_name: str | None
    recipient_uei: str | None
    recipient_id: str | None
    amount: float | None
    base_obligation_date: str | None
    start_date: str | None
    end_date: str | None
    awarding_agency: str | None
    awarding_sub_agency: str | None
    place_of_performance_state: str | None
    recipient_state: str | None
    assistance_listings: list[str] = field(default_factory=list)

    @property
    def base_obligation_year(self) -> int | None:
        """The calendar year of the award's first obligating action, or None.

        Callers that need a fiscal year convert; this stays literal so a caller can see
        exactly which field a cohort was built from.
        """
        if not self.base_obligation_date:
            return None
        try:
            return datetime.fromisoformat(self.base_obligation_date[:10]).year
        except ValueError:
            return None


@dataclass(frozen=True)
class Program:
    """One Assistance Listing, as the autocomplete endpoint reports it.

    ``number`` is not always numeric: 93.00D is a real Assistance Listing. Anything that
    validates or sorts these must treat them as strings.
    """

    number: str
    title: str | None
    popular_name: str | None = None


@dataclass(frozen=True)
class ProgramSearch:
    """What a program lookup found, and which term actually found it."""

    programs: list[Program]
    matched_term: str
    fell_back: bool
    retrieved: datetime


# Words too generic to be worth a fallback search of their own: matching every listing whose
# title contains "program" helps nobody.
_STOPWORDS = {
    "program",
    "programs",
    "grant",
    "grants",
    "federal",
    "national",
    "and",
    "for",
    "the",
    "of",
    "to",
    "in",
    "on",
    "services",
    "service",
    "assistance",
}


def _location_state(value: Any) -> str | None:
    return value.get("state_code") if isinstance(value, dict) else None


def _listings(value: Any) -> list[str]:
    """The Assistance Listing numbers on an award.

    An award can be reported under several programs, so filtering on one number returns
    awards that also touch others. Keeping the whole list lets a caller see that rather
    than silently assume the award belongs to the program it was filtered by.
    """
    if not isinstance(value, list):
        return []
    seen: list[str] = []
    for item in value:
        # One award really does carry the same number twice under variant titles - the
        # 16.842 fixture has "OPIOD" and "OPIOID" - so deduplicate while keeping order.
        if isinstance(item, dict) and item.get("cfda_number"):
            number = str(item["cfda_number"])
            if number not in seen:
                seen.append(number)
    return seen


def to_award(row: dict[str, Any]) -> Award:
    """One search result row as an ``Award``. Unknown extra fields are ignored."""
    return Award(
        generated_internal_id=str(row.get("generated_internal_id") or row.get("internal_id") or ""),
        award_id=row.get("Award ID"),
        recipient_name=row.get("Recipient Name"),
        recipient_uei=row.get("Recipient UEI"),
        recipient_id=row.get("recipient_id"),
        amount=row.get("Award Amount"),
        base_obligation_date=row.get("Base Obligation Date"),
        start_date=row.get("Start Date"),
        end_date=row.get("End Date"),
        awarding_agency=row.get("Awarding Agency"),
        awarding_sub_agency=row.get("Awarding Sub Agency"),
        place_of_performance_state=row.get("Place of Performance State Code"),
        recipient_state=_location_state(row.get("Recipient Location")),
        assistance_listings=_listings(row.get("Assistance Listings")),
    )


def build_filters(
    program: str,
    start_date: str,
    end_date: str,
    *,
    recipient_states: list[str] | None = None,
) -> dict[str, Any]:
    """The filter block for one program over one window.

    ``date_type`` is ``action_date`` on purpose, and the window should be wider than the
    period being reported on. See the module docstring.
    """
    filters: dict[str, Any] = {
        "award_type_codes": list(GRANT_AWARD_TYPES),
        "program_numbers": [program],
        "time_period": [
            {"start_date": start_date, "end_date": end_date, "date_type": "action_date"}
        ],
    }
    if recipient_states:
        filters["recipient_locations"] = [
            {"country": "USA", "state": s.upper()} for s in recipient_states
        ]
    return filters


class UsaSpending:
    """Fetches award history. Holds no statistics and no opinions about the data."""

    def __init__(self, http: HttpClient) -> None:
        self.http = http

    def count(self, filters: dict[str, Any]) -> dict[str, int]:
        """Result counts by award category, before committing to a pull."""
        body, _ = self.http.post_json(SOURCE, COUNT_URL, {"filters": filters, "subawards": False})
        results = body.get("results") or {}
        return {k: v for k, v in results.items() if isinstance(v, int)}

    def grant_count(self, filters: dict[str, Any]) -> int:
        counts = self.count(filters)
        return int(counts.get("grants", 0))

    def search(
        self,
        filters: dict[str, Any],
        *,
        max_records: int = MAX_RECORDS,
    ) -> tuple[list[Award], datetime | None]:
        """Every matching award, deduplicated, with the oldest retrieval date behind it.

        Raises ``TooMuchData`` before fetching anything when the program is larger than a
        record-by-record pull can honestly serve.
        """
        total = self.grant_count(filters)
        if total > max_records:
            programs = ", ".join(filters.get("program_numbers", [])) or "this filter"
            window = filters.get("time_period", [{}])[0]
            raise TooMuchData(
                f"{programs} matches {total:,} grant awards between "
                f"{window.get('start_date', '?')} and {window.get('end_date', '?')}, which is "
                f"more than the {max_records:,} this tool will pull one record at a time.\n"
                "Narrow it: a shorter window (--since), or one or more recipient states "
                "(--state). For a whole program across all years, USAspending's bulk download "
                "endpoint is the right tool: https://api.usaspending.gov/api/v2/bulk_download/awards/"
            )

        awards: dict[str, Award] = {}
        dates: list[datetime] = []
        last_id: Any = None
        last_sort: Any = None
        while True:
            payload: dict[str, Any] = {
                "filters": filters,
                "fields": list(FIELDS),
                "limit": PAGE_LIMIT,
                "sort": "Award Amount",
                "order": "desc",
                "subawards": False,
            }
            if last_id is not None:
                payload["last_record_unique_id"] = last_id
                payload["last_record_sort_value"] = last_sort
            body, fetched_at = self.http.post_json(SOURCE, SEARCH_URL, payload)
            dates.append(fetched_at)
            for row in body.get("results") or []:
                award = to_award(row)
                if award.generated_internal_id:
                    # The same award can appear on two pages when the sort value ties.
                    # generated_internal_id is the stable key; last write wins harmlessly.
                    awards[award.generated_internal_id] = award
            meta = body.get("page_metadata") or {}
            if not meta.get("hasNext"):
                break
            last_id = meta.get("last_record_unique_id")
            last_sort = meta.get("last_record_sort_value")
            if last_id is None:
                break  # hasNext without a cursor would loop forever on page one
        return list(awards.values()), (min(dates) if dates else None)

    def programs(
        self, search_text: str, *, limit: int = 20, no_cache: bool | None = None
    ) -> tuple[list[Program], datetime]:
        """Assistance Listings matching a keyword or a partial number."""
        body, fetched_at = self.http.post_json(
            SOURCE,
            AUTOCOMPLETE_URL,
            {"search_text": search_text, "limit": limit},
            no_cache=no_cache,
        )
        out = []
        for row in body.get("results") or []:
            if not isinstance(row, dict):
                continue
            number = row.get("program_number") or row.get("cfda_number")
            if number is None:
                continue
            out.append(
                Program(
                    number=str(number),
                    title=row.get("program_title") or row.get("cfda_program_title"),
                    popular_name=(row.get("popular_name") or "").strip() or None,
                )
            )
        return out, fetched_at

    def find_programs(
        self, search_text: str, *, limit: int = 20, no_cache: bool | None = None
    ) -> ProgramSearch:
        """Programs matching a phrase, narrowing to one word when the phrase matches nothing.

        The endpoint matches a contiguous substring of the listing title, so a natural
        phrase like "opioid treatment" finds nothing while "opioid" finds three. Rather
        than report an empty result for a program that plainly exists, retry on the longest
        meaningful word and say so: ``fell_back`` and ``matched_term`` carry that, and the
        renderer tells the user what was actually searched.
        """
        text = " ".join(search_text.split())
        found, retrieved = self.programs(text, limit=limit, no_cache=no_cache)
        if found or " " not in text:
            return ProgramSearch(found, text, fell_back=False, retrieved=retrieved)
        words = sorted(
            (w for w in text.split() if len(w) > 3 and w.lower() not in _STOPWORDS),
            key=len,
            reverse=True,
        )
        for word in words:
            found, retrieved = self.programs(word, limit=limit, no_cache=no_cache)
            if found:
                return ProgramSearch(found, word, fell_back=True, retrieved=retrieved)
        return ProgramSearch([], text, fell_back=False, retrieved=retrieved)
