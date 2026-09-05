"""The USAspending client, against real captured responses.

Every fixture here is a real response with a `.meta.json` sidecar recording the request and
the date. Mocked shapes would pass while the API drifted underneath us, and this tool is a
thin layer over somebody else's API, so drift is the failure that actually matters.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from precedent.config import Config
from precedent.errors import TooMuchData
from precedent.http import HttpClient
from precedent.sources.usaspending import (
    COVERAGE_START,
    GRANT_AWARD_TYPES,
    MAX_RECORDS,
    UsaSpending,
    build_filters,
    to_award,
)

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def client(tmp_path: Path, routes: dict[str, Any]) -> UsaSpending:
    """A client whose upstream answers from fixtures, keyed by URL suffix."""

    def handler(request: httpx.Request) -> httpx.Response:
        for suffix, body in routes.items():
            if request.url.path.endswith(suffix):
                payload = body(request) if callable(body) else body
                return httpx.Response(200, json=payload)
        return httpx.Response(404, text=f"no fixture for {request.url.path}")

    cfg = Config.from_env({"PRECEDENT_CACHE_DIR": str(tmp_path), "PRECEDENT_NO_CACHE": "1"})
    http = HttpClient(cfg, client=httpx.Client(transport=httpx.MockTransport(handler)))
    return UsaSpending(http)


class TestFixturesAreReal:
    def test_every_fixture_records_where_it_came_from(self) -> None:
        for body in FIXTURES.glob("usaspending_*.json"):
            if body.name.endswith(".meta.json"):
                continue
            meta = FIXTURES / f"{body.stem}.meta.json"
            assert meta.exists(), f"{body.name} has no provenance sidecar"
            recorded = json.loads(meta.read_text(encoding="utf-8"))
            assert recorded["source"] == "usaspending"
            assert recorded["status"] == 200
            assert recorded["endpoint"].startswith("https://api.usaspending.gov/")
            assert recorded["retrieved"]

    def test_the_api_states_the_coverage_floor_we_encode(self) -> None:
        # Not a detail we inferred: the count endpoint says it in every response, and the
        # truncated-lookback flag depends on it being right.
        messages = " ".join(fixture("usaspending_count_16842").get("messages", []))
        assert COVERAGE_START in messages


class TestFilters:
    def test_grant_codes_only_and_the_window_is_by_action_date(self) -> None:
        f = build_filters("16.842", "2019-10-01", "2024-09-30")
        assert f["award_type_codes"] == GRANT_AWARD_TYPES
        assert "A" not in f["award_type_codes"], "contract codes change the field vocabulary"
        assert f["program_numbers"] == ["16.842"]
        assert f["time_period"][0]["date_type"] == "action_date"
        assert "recipient_locations" not in f

    def test_states_are_upper_cased_into_recipient_locations(self) -> None:
        f = build_filters("93.243", "2019-10-01", "2024-09-30", recipient_states=["oh", "KY"])
        assert f["recipient_locations"] == [
            {"country": "USA", "state": "OH"},
            {"country": "USA", "state": "KY"},
        ]


class TestSearch:
    def test_it_reads_the_real_award_shape(self, tmp_path: Path) -> None:
        us = client(
            tmp_path,
            {
                "spending_by_award_count/": fixture("usaspending_count_16842"),
                "spending_by_award/": fixture("usaspending_search_16842"),
            },
        )
        awards, retrieved = us.search(build_filters("16.842", "2019-10-01", "2024-09-30"))
        assert len(awards) == 4
        assert retrieved is not None
        first = next(a for a in awards if a.award_id == "2018YBFXK007")
        assert first.generated_internal_id == "ASST_NON_2018YBFXK007_015"
        assert first.recipient_name == "COUNTY OF CLACKAMAS"
        assert first.recipient_uei == "NVWKAVB8JND6"
        assert first.recipient_state == "OR", "pulled out of the Recipient Location object"
        assert first.amount == 1000999.0
        assert first.base_obligation_date == "2018-09-27"

    def test_the_cohort_year_comes_from_the_first_obligating_action(self, tmp_path: Path) -> None:
        # The whole new-entrant statistic rests on this field rather than on the window the
        # award was found in: this award was fetched by a 2019-2024 filter and belongs to
        # the 2018 cohort.
        us = client(
            tmp_path,
            {
                "spending_by_award_count/": fixture("usaspending_count_16842"),
                "spending_by_award/": fixture("usaspending_search_16842"),
            },
        )
        awards, _ = us.search(build_filters("16.842", "2019-10-01", "2024-09-30"))
        first = next(a for a in awards if a.award_id == "2018YBFXK007")
        assert first.base_obligation_year == 2018

    def test_one_award_reported_under_a_repeated_listing_is_deduplicated(self) -> None:
        # Real quirk: 16.842 appears twice on one award, once spelled "OPIOD".
        raw = fixture("usaspending_search_16842")["results"][0]
        assert len(raw["Assistance Listings"]) == 2
        assert to_award(raw).assistance_listings == ["16.842"]

    def test_an_award_on_two_pages_is_counted_once(self, tmp_path: Path) -> None:
        page = fixture("usaspending_search_16842")
        pages = iter(
            [
                {
                    **page,
                    "page_metadata": {
                        "page": 1,
                        "hasNext": True,
                        "last_record_unique_id": 1,
                        "last_record_sort_value": "1",
                    },
                },
                {**page, "page_metadata": {"page": 2, "hasNext": False}},
            ]
        )
        us = client(
            tmp_path,
            {
                "spending_by_award_count/": fixture("usaspending_count_16842"),
                "spending_by_award/": lambda _r: next(pages),
            },
        )
        awards, _ = us.search(build_filters("16.842", "2019-10-01", "2024-09-30"))
        assert len(awards) == 4, "the same four awards arrived twice; the award key deduplicates"

    def test_pagination_sends_the_cursor_back_and_stops(self, tmp_path: Path) -> None:
        seen: list[dict[str, Any]] = []
        page = fixture("usaspending_search_16842")

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("spending_by_award_count/"):
                return httpx.Response(200, json=fixture("usaspending_count_16842"))
            body = json.loads(request.content)
            seen.append(body)
            if len(seen) == 1:
                return httpx.Response(
                    200,
                    json={
                        **page,
                        "page_metadata": {
                            "page": 1,
                            "hasNext": True,
                            "last_record_unique_id": 234931512,
                            "last_record_sort_value": "1000999",
                        },
                    },
                )
            return httpx.Response(
                200, json={**page, "page_metadata": {"page": 2, "hasNext": False}}
            )

        cfg = Config.from_env({"PRECEDENT_CACHE_DIR": str(tmp_path), "PRECEDENT_NO_CACHE": "1"})
        us = UsaSpending(
            HttpClient(cfg, client=httpx.Client(transport=httpx.MockTransport(handler)))
        )
        us.search(build_filters("16.842", "2019-10-01", "2024-09-30"))
        assert len(seen) == 2
        assert "last_record_unique_id" not in seen[0], "the first page carries no cursor"
        assert seen[1]["last_record_unique_id"] == 234931512
        assert seen[1]["last_record_sort_value"] == "1000999"
        assert seen[0]["subawards"] is False, "true would switch to the FSRS subaward table"
        assert seen[0]["limit"] == 100

    def test_hasnext_without_a_cursor_does_not_loop_forever(self, tmp_path: Path) -> None:
        page = fixture("usaspending_search_16842")
        calls = []

        def search(_request: httpx.Request) -> Any:
            calls.append(1)
            return {
                **page,
                "page_metadata": {"page": 1, "hasNext": True, "last_record_unique_id": None},
            }

        us = client(
            tmp_path,
            {
                "spending_by_award_count/": fixture("usaspending_count_16842"),
                "spending_by_award/": search,
            },
        )
        us.search(build_filters("16.842", "2019-10-01", "2024-09-30"))
        assert len(calls) == 1


class TestCount:
    def test_the_count_precheck_reads_grants(self, tmp_path: Path) -> None:
        us = client(tmp_path, {"spending_by_award_count/": fixture("usaspending_count_16842")})
        assert us.grant_count(build_filters("16.842", "2019-10-01", "2024-09-30")) == 40

    def test_a_program_too_large_to_pull_says_how_to_narrow_it(self, tmp_path: Path) -> None:
        huge = {"results": {"grants": MAX_RECORDS + 1, "contracts": 0}, "spending_level": "awards"}
        us = client(tmp_path, {"spending_by_award_count/": huge})
        with pytest.raises(TooMuchData) as caught:
            us.search(build_filters("93.243", "2007-10-01", "2025-09-30"))
        message = str(caught.value)
        assert "93.243" in message
        assert f"{MAX_RECORDS:,}" in message
        assert "--state" in message and "--since" in message
        assert "bulk_download" in message, "name the endpoint that does answer this"


class TestPrograms:
    def test_autocomplete_returns_listings_including_non_numeric_ones(self, tmp_path: Path) -> None:
        us = client(tmp_path, {"autocomplete/cfda/": fixture("usaspending_autocomplete_opioid")})
        programs, retrieved = us.programs("opioid", limit=5)
        assert retrieved is not None
        numbers = [p.number for p in programs]
        assert numbers == ["16.046", "16.838", "16.842", "93.00D", "93.259"]
        assert "93.00D" in numbers, "Assistance Listing numbers are not all numeric"
        assert programs[2].title == "Opioid Affected Youth Initiative"
        assert programs[2].popular_name == "Opioid Affected Youth Initiative"
        assert programs[0].popular_name is None, "an empty popular_name is None, not ''"


class TestMultiWordFallback:
    """The endpoint matches a run of characters in the title, so phrases often find nothing."""

    def searcher(self, tmp_path: Path, by_term: dict[str, Any]) -> UsaSpending:
        def handler(request: httpx.Request) -> httpx.Response:
            term = json.loads(request.content)["search_text"]
            return httpx.Response(200, json={"results": by_term.get(term, [])})

        cfg = Config.from_env({"PRECEDENT_CACHE_DIR": str(tmp_path), "PRECEDENT_NO_CACHE": "1"})
        return UsaSpending(
            HttpClient(cfg, client=httpx.Client(transport=httpx.MockTransport(handler)))
        )

    def test_a_phrase_that_matches_is_used_as_typed(self, tmp_path: Path) -> None:
        hit = [{"program_number": "93.600", "program_title": "Head Start"}]
        found = self.searcher(tmp_path, {"head start": hit}).find_programs("head start")
        assert found.fell_back is False
        assert found.matched_term == "head start"
        assert [p.number for p in found.programs] == ["93.600"]

    def test_a_phrase_that_matches_nothing_falls_back_to_its_longest_word(
        self, tmp_path: Path
    ) -> None:
        hit = [{"program_number": "16.585", "program_title": "Treatment Court Grant"}]
        found = self.searcher(tmp_path, {"opioid treatment": [], "treatment": hit}).find_programs(
            "opioid treatment"
        )
        assert found.fell_back is True
        assert found.matched_term == "treatment", "longest meaningful word first"
        assert [p.number for p in found.programs] == ["16.585"]

    def test_generic_words_are_not_worth_falling_back_to(self, tmp_path: Path) -> None:
        # "program" would match hundreds of listings and tell the user nothing.
        everything = [{"program_number": "00.000", "program_title": "Some Program"}]
        found = self.searcher(tmp_path, {"program": everything}).find_programs("zzzz program")
        assert found.programs == []
        assert found.fell_back is False

    def test_a_single_word_that_finds_nothing_does_not_retry(self, tmp_path: Path) -> None:
        found = self.searcher(tmp_path, {}).find_programs("zzzzzzz")
        assert found.programs == [] and found.fell_back is False

    def test_extra_whitespace_does_not_change_the_search(self, tmp_path: Path) -> None:
        hit = [{"program_number": "93.600", "program_title": "Head Start"}]
        found = self.searcher(tmp_path, {"head start": hit}).find_programs("  head   start ")
        assert found.matched_term == "head start" and found.programs
