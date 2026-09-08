"""The Federal Audit Clearinghouse client: query shape, paging, and the two flags.

The paging tests matter more than they look. PostgREST does not guarantee an order, so a
limit/offset loop over an unordered result skips and duplicates rows without raising
anything, and the wrong answer is indistinguishable from the right one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from precedent.config import Config
from precedent.errors import MissingCredential, TooMuchData
from precedent.http import HttpClient
from precedent.sources.fac import (
    COVERAGE_START_YEAR,
    IN_CHUNK,
    MAX_PAGES,
    PAGE_LIMIT,
    Fac,
    assistance_listing,
    chunked,
    in_filter,
    split_listing,
    to_passthrough,
    to_sefa_award,
)

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def client(tmp_path: Path, rows: Any, seen: list[httpx.Request] | None = None) -> HttpClient:
    """A client answering every request from ``rows``, which may be a callable."""

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        body = rows(request) if callable(rows) else rows
        return httpx.Response(200, json=body)

    cfg = Config.from_env(
        {"PRECEDENT_CACHE_DIR": str(tmp_path), "PRECEDENT_NO_CACHE": "1", "FAC_API_KEY": "k"}
    )
    return HttpClient(cfg, client=httpx.Client(transport=httpx.MockTransport(handler)))


def query(request: httpx.Request) -> dict[str, str]:
    return dict(request.url.params)


class TestAssistanceListing:
    def test_the_number_is_two_columns_joined_by_a_dot(self) -> None:
        # FAC publishes no single Assistance Listing column. Filtering on one is the most
        # common way to query this API for the wrong thing.
        assert assistance_listing("93", "045") == "93.045"
        assert split_listing("93.045") == ("93", "045")

    def test_a_leading_zero_in_the_extension_survives(self) -> None:
        assert split_listing("93.045")[1] == "045", "not 45; it is text, not a number"

    def test_a_missing_half_is_not_a_listing(self) -> None:
        assert assistance_listing("93", None) is None
        assert assistance_listing(None, "045") is None
        for bad in ("93", "93.", ".045", ""):
            with pytest.raises(ValueError, match="Assistance Listing"):
                split_listing(bad)


class TestFilters:
    def test_in_filter_quotes_so_a_comma_cannot_split_a_value(self) -> None:
        assert in_filter(["a", "b"]) == 'in.("a","b")'
        assert in_filter(["x,y"]) == 'in.("x,y")', "a comma inside a value is not a separator"

    def test_chunking_matches_the_documented_batch_size(self) -> None:
        assert [len(c) for c in chunked([str(i) for i in range(250)])] == [100, 100, 50]
        assert IN_CHUNK == 100


class TestBooleansAreYesNoStrings:
    def test_the_flags_arrive_as_Y_and_N_not_as_booleans(self) -> None:
        # The FAC data dictionary types these as boolean. The API returns "Y" and "N".
        # Reading them as truthy Python makes every "N" mean True and inverts the feature.
        raw = fixture("fac_federal_awards_93045")[0]
        assert raw["is_direct"] == "N" and isinstance(raw["is_direct"], str)
        assert to_sefa_award(raw).is_direct is False

    def test_the_two_flags_are_opposite_ends_of_the_same_pipe(self) -> None:
        received = to_sefa_award({"report_id": "r", "is_direct": "N"})
        assert received.received_through_someone, "is_direct false: money came through somebody"
        assert not received.passed_money_down

        passed = to_sefa_award(
            {
                "report_id": "r",
                "is_direct": "Y",
                "is_passthrough_award": "Y",
                "passthrough_amount": 5000,
            }
        )
        assert passed.passed_money_down, "this auditee handed money to its own subrecipients"
        assert not passed.received_through_someone

    def test_a_passthrough_flag_without_dollars_is_not_passing_money_down(self) -> None:
        flagged = to_sefa_award(
            {"report_id": "r", "is_passthrough_award": "Y", "passthrough_amount": 0}
        )
        assert not flagged.passed_money_down


class TestJoiningRealFixtures:
    def test_sefa_lines_join_to_passthrough_rows_on_report_and_award(self) -> None:
        # FAC's own documentation says join client side. The key is the pair, not report_id
        # alone: one audit has many SEFA lines and each has its own pass-through entity.
        awards = [to_sefa_award(r) for r in fixture("fac_federal_awards_93045")]
        rows = [to_passthrough(r) for r in fixture("fac_passthrough_93045")]
        by_key = {p.key: p for p in rows}
        joined = [(a, by_key[a.key]) for a in awards if a.key in by_key]
        assert joined, "the captured fixtures overlap, or this test proves nothing"
        assert all(a.listing == "93.045" for a in awards)
        assert all(p.name for _, p in joined)

    def test_a_report_id_alone_would_over_join(self) -> None:
        rows = [to_passthrough(r) for r in fixture("fac_passthrough_93045")]
        per_report: dict[str, set[str | None]] = {}
        for p in rows:
            per_report.setdefault(p.report_id, set()).add(p.award_reference)
        assert any(len(v) > 1 for v in per_report.values()), (
            "one audit carries several award references, so report_id alone is not the key"
        )


class TestQueryShape:
    def test_every_request_sends_select_and_order(self, tmp_path: Path) -> None:
        # Bandwidth is the main cost on this API, and an unordered paginated read is wrong.
        seen: list[httpx.Request] = []
        Fac(client(tmp_path, [], seen)).audits(state="OH", since_year=2022, until_year=2023)
        q = query(seen[0])
        assert q["select"] and q["order"] == "report_id.asc"
        assert q["auditee_state"] == "eq.OH"
        assert q["and"] == "(audit_year.gte.2022,audit_year.lte.2023)"

    def test_a_listing_filters_on_both_halves_separately(self, tmp_path: Path) -> None:
        seen: list[httpx.Request] = []
        Fac(client(tmp_path, [], seen)).sefa_awards(listing="93.045")
        q = query(seen[0])
        assert q["federal_agency_prefix"] == "eq.93"
        assert q["federal_award_extension"] == "eq.045"
        assert q["order"] == "report_id.asc,award_reference.asc"

    def test_a_window_reaching_before_coverage_is_clamped(self, tmp_path: Path) -> None:
        # Audit years 2016 forward. Earlier single audits live in the legacy Census
        # extracts, which this API does not serve.
        seen: list[httpx.Request] = []
        Fac(client(tmp_path, [], seen)).audits(since_year=2009, until_year=2020)
        assert (
            query(seen[0])["and"] == f"(audit_year.gte.{COVERAGE_START_YEAR},audit_year.lte.2020)"
        )

    def test_report_ids_are_chunked_into_several_requests(self, tmp_path: Path) -> None:
        seen: list[httpx.Request] = []
        ids = [f"2023-01-GSAFAC-{i:010d}" for i in range(250)]
        Fac(client(tmp_path, [], seen)).passthroughs(ids)
        assert len(seen) == 3, "250 identifiers at 100 per request"
        assert all("report_id" in query(r) for r in seen)
        assert query(seen[0])["report_id"].startswith("in.(")

    def test_no_identifiers_makes_no_request_at_all(self, tmp_path: Path) -> None:
        seen: list[httpx.Request] = []
        rows, retrieved = Fac(client(tmp_path, [], seen)).passthroughs([])
        assert rows == [] and retrieved is None and seen == []


class TestPagination:
    def pages(self, total: int):
        """Answer offset/limit out of a synthetic ordered table of ``total`` rows."""

        def handler(request: httpx.Request) -> list[dict[str, Any]]:
            q = query(request)
            start, limit = int(q["offset"]), int(q["limit"])
            return [
                {"report_id": f"r{i:06d}", "audit_year": "2023"}
                for i in range(start, min(start + limit, total))
            ]

        return handler

    def test_a_full_page_is_followed_and_a_short_page_ends_it(self, tmp_path: Path) -> None:
        seen: list[httpx.Request] = []
        total = PAGE_LIMIT * 2 + 7
        audits, _ = Fac(client(tmp_path, self.pages(total), seen)).audits(state="OH")
        assert len(audits) == total
        assert len(seen) == 3, "two full pages then a short one"
        assert len({a.report_id for a in audits}) == total, "no row fetched twice"
        assert [q["offset"] for q in map(query, seen)] == [
            "0",
            str(PAGE_LIMIT),
            str(2 * PAGE_LIMIT),
        ]

    def test_an_exactly_full_last_page_costs_one_more_request(self, tmp_path: Path) -> None:
        seen: list[httpx.Request] = []
        audits, _ = Fac(client(tmp_path, self.pages(PAGE_LIMIT), seen)).audits(state="OH")
        assert len(audits) == PAGE_LIMIT
        assert len(seen) == 2, "a full page cannot be known to be the last one"

    def test_the_loop_is_bounded_so_a_bug_cannot_spend_the_quota(self, tmp_path: Path) -> None:
        # One key per person, rate limited per key. An unbounded loop spends somebody's
        # quota; this raises with a narrower query to try instead.
        seen: list[httpx.Request] = []
        endless = self.pages(PAGE_LIMIT * (MAX_PAGES + 5))
        with pytest.raises(TooMuchData, match="Narrow it"):
            Fac(client(tmp_path, endless, seen)).audits(state="OH")
        assert len(seen) == MAX_PAGES


class TestCredential:
    def test_no_key_is_an_actionable_error_not_a_stack_trace(self, tmp_path: Path) -> None:
        cfg = Config.from_env({"PRECEDENT_CACHE_DIR": str(tmp_path)})
        http = HttpClient(cfg, client=httpx.Client(transport=httpx.MockTransport(lambda r: None)))
        with pytest.raises(MissingCredential) as caught:
            Fac(http)
        message = str(caught.value)
        assert "free" in message and "fac.gov/api/signup" in message
        assert "precedent history" in message, "and says what still works without a key"

    def test_the_key_travels_in_the_header_and_never_in_the_query(self, tmp_path: Path) -> None:
        seen: list[httpx.Request] = []
        Fac(client(tmp_path, [], seen), api_key="secret-key").audits(state="OH")
        assert seen[0].headers["X-Api-Key"] == "secret-key"
        assert "secret-key" not in str(seen[0].url), "a key in a URL lands in logs and caches"
