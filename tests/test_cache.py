"""The cache: hit, miss, expiry, and the provenance date that is the point of it."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from precedent.cache import Cache, cache_key, canonical, oldest


def test_key_is_stable_across_parameter_order_and_separates_everything_else() -> None:
    a = cache_key("usaspending", "POST", "/api/v2/search/", {"b": 2, "a": 1})
    b = cache_key("usaspending", "POST", "/api/v2/search/", {"a": 1, "b": 2})
    assert a == b, "two callers building one query differently must share an entry"
    assert a != cache_key("fac", "POST", "/api/v2/search/", {"a": 1, "b": 2})
    assert a != cache_key("usaspending", "GET", "/api/v2/search/", {"a": 1, "b": 2})
    assert a != cache_key("usaspending", "POST", "/api/v2/other/", {"a": 1, "b": 2})
    assert a != cache_key("usaspending", "POST", "/api/v2/search/", {"a": 1, "b": 3})
    assert canonical({"b": 2, "a": 1}) == '{"a":1,"b":2}'


def test_miss_then_hit_round_trips_the_body(tmp_path: Path) -> None:
    with Cache(tmp_path) as cache:
        key = cache_key("usaspending", "GET", "/x")
        assert cache.get(key, ttl_hours=168) is None
        cache.put(key, source="usaspending", status=200, body=b'{"results": [1, 2]}')
        hit = cache.get(key, ttl_hours=168)
        assert hit is not None
        assert hit.status == 200
        assert hit.json() == {"results": [1, 2]}
        assert hit.source == "usaspending"


def test_an_entry_past_its_ttl_is_a_miss_and_is_dropped(tmp_path: Path) -> None:
    with Cache(tmp_path) as cache:
        key = cache_key("fac", "GET", "/general")
        eight_days_ago = datetime.now(UTC) - timedelta(days=8)
        cache.put(key, source="fac", status=200, body=b"{}", fetched_at=eight_days_ago)
        assert cache.get(key, ttl_hours=168) is None, "168 hours is seven days"
        assert cache.info().entries == 0, "an expired row is removed, not left to leak"
        cache.put(key, source="fac", status=200, body=b"{}", fetched_at=eight_days_ago)
        assert cache.get(key, ttl_hours=24 * 30) is not None, "a longer ttl keeps it"


def test_the_entry_reports_when_it_was_fetched_not_when_it_was_read(tmp_path: Path) -> None:
    # The whole provenance claim rests on this: a result assembled from a five-day-old
    # cache must say five days old, not today.
    five_days_ago = datetime.now(UTC) - timedelta(days=5)
    with Cache(tmp_path) as cache:
        key = cache_key("usaspending", "GET", "/awards")
        cache.put(key, source="usaspending", status=200, body=b"{}", fetched_at=five_days_ago)
        hit = cache.get(key, ttl_hours=168)
        assert hit is not None
        assert abs((hit.fetched_at - five_days_ago).total_seconds()) < 1


def test_oldest_picks_the_stalest_input_and_tolerates_gaps() -> None:
    now = datetime.now(UTC)
    older = now - timedelta(days=3)
    assert oldest([now, older, None]) == older
    assert oldest([None, None]) is None
    assert oldest([]) is None


def test_info_and_clear_describe_and_empty_the_store(tmp_path: Path) -> None:
    with Cache(tmp_path) as cache:
        old = datetime.now(UTC) - timedelta(days=2)
        cache.put(
            cache_key("fac", "GET", "/a"), source="fac", status=200, body=b"{}", fetched_at=old
        )
        cache.put(cache_key("fac", "GET", "/b"), source="fac", status=200, body=b"{}")
        info = cache.info()
        assert info.entries == 2
        assert info.bytes_on_disk > 0
        assert info.path == tmp_path / "cache.sqlite3"
        assert info.oldest is not None and info.newest is not None
        assert info.oldest < info.newest
        assert cache.clear() == 2
        assert cache.info().entries == 0
