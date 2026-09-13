"""Optional enrichment, and the guarantee that it can never break anything.

The tests that matter here are the failure tests. This is the only commercial dependency in
a public-data tool, and a public-data answer that can be taken down by a private outage is
not a public-data answer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from precedent.config import Config
from precedent.http import HttpClient
from precedent.sources.opengrants import (
    ENRICHMENT_MARK,
    Enrichment,
    keyword_from_title,
    open_opportunities,
)

ROWS = [
    {
        "title": "Substance Use Prevention Grants 2027",
        "status": "open",
        "close_date": "2027-01-15",
        "url": "https://example.invalid/opp/1",
        "agency": "SAMHSA",
    }
]


def client(tmp_path: Path, handler: Any) -> HttpClient:
    cfg = Config.from_env({"PRECEDENT_CACHE_DIR": str(tmp_path), "PRECEDENT_NO_CACHE": "1"})
    return HttpClient(cfg, client=httpx.Client(transport=httpx.MockTransport(handler)))


def ok(body: Any):
    return lambda request: httpx.Response(200, json=body)


class TestKeyword:
    def test_the_keyword_comes_from_the_title_because_the_api_has_no_listing_numbers(
        self,
    ) -> None:
        assert keyword_from_title("Substance Abuse and Mental Health Services Projects") == (
            "substance abuse"
        )

    def test_filler_words_are_dropped(self) -> None:
        assert keyword_from_title("National Grants for the Aging Program") == "aging"

    def test_no_title_is_no_keyword_rather_than_a_blind_search(self) -> None:
        assert keyword_from_title(None) == ""
        assert keyword_from_title("  ") == ""


class TestEveryFailureIsSilent:
    """None, never an exception, whatever the upstream does."""

    def test_no_key_means_no_request_at_all(self, tmp_path: Path) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json=ROWS)

        assert open_opportunities(client(tmp_path, handler), "aging", api_key=None) is None
        assert seen == [], "an absent key is not a reason to call anybody"

    def test_no_keyword_means_no_request_at_all(self, tmp_path: Path) -> None:
        assert open_opportunities(client(tmp_path, ok(ROWS)), "", api_key="k") is None

    @pytest.mark.parametrize("status", [401, 403, 404, 429, 500, 503])
    def test_any_http_failure_degrades_to_nothing(self, tmp_path: Path, status: int) -> None:
        http = client(tmp_path, lambda request: httpx.Response(status, text="no"))
        assert open_opportunities(http, "aging", api_key="k") is None

    def test_a_transport_error_degrades_to_nothing(self, tmp_path: Path) -> None:
        def boom(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("the network is gone")

        assert open_opportunities(client(tmp_path, boom), "aging", api_key="k") is None

    @pytest.mark.parametrize(
        "body", [None, "not json shaped", {"unexpected": "shape"}, [], {"data": []}, 42]
    )
    def test_an_unrecognised_response_shape_degrades_to_nothing(
        self, tmp_path: Path, body: Any
    ) -> None:
        # The shape this API returns is not under our control and may change without notice.
        assert open_opportunities(client(tmp_path, ok(body)), "aging", api_key="k") is None


class TestSuccess:
    def test_a_result_is_parsed_and_marked(self, tmp_path: Path) -> None:
        out = open_opportunities(client(tmp_path, ok(ROWS)), "aging", api_key="k")
        assert isinstance(out, Enrichment)
        opp = out.opportunities[0]
        assert opp.title == "Substance Use Prevention Grants 2027"
        assert opp.funder == "SAMHSA"
        assert opp.close_date == "2027-01-15"
        assert opp.label.endswith(ENRICHMENT_MARK), "a reader can always tell which line is live"

    def test_the_wrapper_shapes_are_all_accepted(self, tmp_path: Path) -> None:
        for body in ({"data": ROWS}, {"results": ROWS}, {"grants": ROWS}, ROWS):
            out = open_opportunities(client(tmp_path, ok(body)), "aging", api_key="k")
            assert out and len(out.opportunities) == 1

    def test_the_key_travels_in_the_header_and_never_in_the_url(self, tmp_path: Path) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json=ROWS)

        open_opportunities(client(tmp_path, handler), "aging", api_key="secret")
        assert seen[0].headers["Authorization"] == "Bearer secret"
        assert "secret" not in str(seen[0].url)
        assert dict(seen[0].url.params)["status"] == "open"

    def test_the_limit_is_honoured_even_if_the_api_ignores_it(self, tmp_path: Path) -> None:
        many = [dict(ROWS[0], title=f"Opportunity {i}") for i in range(50)]
        out = open_opportunities(client(tmp_path, ok(many)), "aging", api_key="k", limit=3)
        assert out and len(out.opportunities) == 3


class TestHistoryIsUnaffected:
    def test_award_history_never_mentions_enrichment_without_a_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # No nag, ever. The key is documented in the README and nowhere else, so nothing in
        # the output may hint that a paid option exists.
        from precedent.analysis.profile import build_profile
        from precedent.api import HistoryResult, Provenance
        from precedent.render import render_history

        result = HistoryResult(
            profile=build_profile([], program="93.243", since_fy=2020, until_fy=2024),
            provenance=Provenance(sources=["usaspending"], retrieved=None),
        )
        text = render_history(result).lower()
        assert "opengrants" not in text
        assert "api key" not in text and "enrich" not in text

    def test_the_json_carries_no_enrichment_key_when_there_was_none(self) -> None:
        from precedent.analysis.profile import build_profile
        from precedent.api import HistoryResult, Provenance

        result = HistoryResult(
            profile=build_profile([], program="93.243", since_fy=2020, until_fy=2024),
            provenance=Provenance(sources=["usaspending"], retrieved=None),
        )
        assert "open_opportunities" not in result.as_dict()
