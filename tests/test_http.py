"""The HTTP client: cache first, retry on the right statuses, give up honestly."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from precedent.cache import Cache, cache_key
from precedent.config import Config
from precedent.errors import UpstreamError
from precedent.http import ATTEMPTS, HttpClient, backoff_seconds


def config(tmp_path: Path, **over: object) -> Config:
    env = {"PRECEDENT_CACHE_DIR": str(tmp_path), **{k: str(v) for k, v in over.items()}}
    return Config.from_env(env)


def client(cfg: Config, handler, slept: list[float] | None = None) -> HttpClient:
    transport = httpx.MockTransport(handler)
    return HttpClient(
        cfg,
        client=httpx.Client(transport=transport, headers={"User-Agent": cfg.user_agent}),
        sleep=(slept.append if slept is not None else (lambda _s: None)),
    )


def test_a_live_cache_entry_is_served_without_touching_the_network(tmp_path: Path) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        return httpx.Response(200, json={"fresh": True})

    cfg = config(tmp_path)
    with Cache(cfg.cache_dir) as cache:
        cache.put(
            cache_key("usaspending", "GET", "https://api.usaspending.gov/x"),
            source="usaspending",
            status=200,
            body=b'{"cached": true}',
        )
        with client(cfg, handler) as http:
            http.cache = cache
            r = http.request("usaspending", "GET", "https://api.usaspending.gov/x")
    assert r.from_cache is True
    assert r.json() == {"cached": True}
    assert calls == [], "a hit must not reach the network"


def test_a_miss_fetches_stores_and_reports_a_fresh_retrieval_date(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    cfg = config(tmp_path)
    before = datetime.now(UTC) - timedelta(seconds=1)
    with client(cfg, handler) as http:
        r = http.request("usaspending", "GET", "https://api.usaspending.gov/y")
        assert r.from_cache is False and r.fetched_at > before
        again = http.request("usaspending", "GET", "https://api.usaspending.gov/y")
        assert again.from_cache is True, "the fetch must have been stored"
        assert again.fetched_at == r.fetched_at


def test_no_cache_bypasses_the_read_but_still_writes(tmp_path: Path) -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(1)
        return httpx.Response(200, json={"n": len(seen)})

    cfg = config(tmp_path, PRECEDENT_NO_CACHE="1")
    assert cfg.no_cache is True
    with client(cfg, handler) as http:
        http.request("usaspending", "GET", "https://api.usaspending.gov/z")
        http.request("usaspending", "GET", "https://api.usaspending.gov/z")
        assert len(seen) == 2, "reads are bypassed"
        stored = http.cache.get(
            cache_key("usaspending", "GET", "https://api.usaspending.gov/z"), ttl_hours=168
        )
        assert stored is not None, "writes still happen, so the next run is fast"


def test_rate_limits_and_server_errors_are_retried_then_reported(tmp_path: Path) -> None:
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(429, text="slow down")

    slept: list[float] = []
    with client(config(tmp_path), handler, slept) as http, pytest.raises(UpstreamError) as caught:
        http.request("fac", "GET", "https://api.fac.gov/general")
    assert len(attempts) == ATTEMPTS
    assert len(slept) == ATTEMPTS - 1, "it waits between attempts, not after the last"
    assert "429" in str(caught.value) and "gave up" in str(caught.value)


def test_a_transient_failure_that_recovers_returns_the_good_response(tmp_path: Path) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(503, text="unavailable")
        return httpx.Response(200, json={"ok": True})

    with client(config(tmp_path), handler, []) as http:
        r = http.request("usaspending", "GET", "https://api.usaspending.gov/flaky")
    assert r.json() == {"ok": True} and len(calls) == 3


def test_a_client_error_is_not_retried(tmp_path: Path) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, text="bad request")

    with client(config(tmp_path), handler, []) as http, pytest.raises(UpstreamError):
        http.request("usaspending", "GET", "https://api.usaspending.gov/bad")
    assert calls == [1], "a 400 fails identically five times over; do not hammer for it"


def test_backoff_grows_stays_capped_and_honours_retry_after() -> None:
    assert backoff_seconds(0, "7") == 7.0
    assert backoff_seconds(0, "not-a-number") <= 1.0
    assert backoff_seconds(99) <= 30.0, "the cap holds"
    assert all(backoff_seconds(i) > 0 for i in range(6))


def test_the_user_agent_names_the_project_and_a_contact(tmp_path: Path) -> None:
    cfg = config(tmp_path, PRECEDENT_CONTACT="ops@example.org")
    assert cfg.user_agent.startswith("precedent/")
    assert "egeria-corporation/precedent" in cfg.user_agent
    assert "ops@example.org" in cfg.user_agent
