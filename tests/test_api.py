"""The library surface: what award_history asks the API for, and what it does with it."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from precedent.api import FETCH_OVERHANG_YEARS, award_history, default_window
from precedent.config import Config
from precedent.http import HttpClient


def recording_http(tmp_path: Path, captured: list[dict[str, Any]]) -> HttpClient:
    """An HttpClient that records every request body and answers with no results."""

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        if request.url.path.endswith("_count/"):
            return httpx.Response(200, json={"results": {"grants": 0}})
        return httpx.Response(200, json={"results": [], "page_metadata": {"hasNext": False}})

    cfg = Config.from_env({"PRECEDENT_CACHE_DIR": str(tmp_path), "PRECEDENT_NO_CACHE": "1"})
    return HttpClient(cfg, client=httpx.Client(transport=httpx.MockTransport(handler)))


class TestFetchWindow:
    def test_the_pull_runs_a_year_past_the_window_it_reports_on(self, tmp_path: Path) -> None:
        # action_date filters on transaction activity, not on the Base Obligation Date that
        # decides an award's cohort year, so an award obligated inside the window and
        # modified after it is only returned by the wider pull. Stopping at the window's own
        # last day loses 521 of the 1,058 awards belonging to FY2020-FY2024 for 93.243.
        seen: list[dict[str, Any]] = []
        http = recording_http(tmp_path, seen)
        award_history("93.243", since_fy=2020, until_fy=2024, http=http)
        period = seen[0]["filters"]["time_period"][0]
        assert period["start_date"] == "2014-10-01", "lookback start, five years before FY2020"
        assert period["end_date"] == "2025-09-30", "a year past FY2024, not 2024-09-30"
        assert period["date_type"] == "action_date"

    def test_the_overhang_is_one_year_and_named(self) -> None:
        # Pinned so that widening or narrowing it is a deliberate edit with a test to answer
        # to, rather than an arithmetic slip inside a call.
        assert FETCH_OVERHANG_YEARS == 1

    def test_the_default_window_is_the_last_five_complete_fiscal_years(self) -> None:
        from datetime import datetime

        assert default_window(datetime(2026, 1, 15)) == (2021, 2025)
        assert default_window(datetime(2025, 10, 1)) == (2021, 2025), "FY2026 is partial"
