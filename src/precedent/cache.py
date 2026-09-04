"""A keyed disk cache with a time to live, and provenance as its point.

Speed is the smaller reason this exists. The larger one: every number this tool prints has
to carry the date its data was retrieved, and a result assembled from a five-day-old cache
that claims "retrieved today" is a lie. So every entry stores ``fetched_at``, and a caller
that combines several responses reports the *oldest* of them. See ``oldest``.

Storage is one SQLite file rather than one file per key, because a large pull produces
thousands of entries. Bodies are zlib-compressed: these are JSON responses, and they shrink
by roughly an order of magnitude.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import zlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
  key        TEXT PRIMARY KEY,
  source     TEXT NOT NULL,
  fetched_at TEXT NOT NULL,   -- ISO 8601, UTC
  status     INTEGER NOT NULL,
  body       BLOB NOT NULL    -- zlib-compressed
);
CREATE INDEX IF NOT EXISTS idx_entries_source ON entries(source);
"""


def canonical(obj: Any) -> str:
    """The canonical form of a request's parameters or body, for keying.

    Sorted keys and no whitespace, so two callers that build the same query in a different
    order share one cache entry instead of two.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def cache_key(source: str, method: str, path: str, params: Any = None) -> str:
    """sha256 over the request identity: source, method, path, canonical parameters."""
    material = "\n".join(
        [source, method.upper(), path, canonical(params if params is not None else {})]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Entry:
    key: str
    source: str
    fetched_at: datetime
    status: int
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body)


@dataclass(frozen=True)
class CacheInfo:
    path: Path
    entries: int
    bytes_on_disk: int
    oldest: datetime | None
    newest: datetime | None


def _parse(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def oldest(dates: Iterable[datetime | None]) -> datetime | None:
    """The oldest retrieval date among the responses that fed one result, or None."""
    real = [d for d in dates if d is not None]
    return min(real) if real else None


class Cache:
    """SQLite-backed response cache. Safe to construct per command; cheap to open."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        # 0700: a cache of API responses is not secret, but it is nobody else's business,
        # and on a shared machine the default umask is not a decision we should inherit.
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / "cache.sqlite3"
        self._conn = sqlite3.connect(self.path)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Cache:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get(self, key: str, *, ttl_hours: int, now: datetime | None = None) -> Entry | None:
        """A live entry, or None when it is absent or older than its time to live.

        An expired row is deleted on the way out: a cache that never forgets is a disk leak,
        and the next write for that key would replace it anyway.
        """
        row = self._conn.execute(
            "SELECT key, source, fetched_at, status, body FROM entries WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        fetched_at = _parse(row[2])
        if (now or datetime.now(UTC)) - fetched_at > timedelta(hours=ttl_hours):
            self._conn.execute("DELETE FROM entries WHERE key = ?", (key,))
            self._conn.commit()
            return None
        return Entry(row[0], row[1], fetched_at, row[3], zlib.decompress(row[4]))

    def put(
        self,
        key: str,
        *,
        source: str,
        status: int,
        body: bytes,
        fetched_at: datetime | None = None,
    ) -> Entry:
        when = fetched_at or datetime.now(UTC)
        self._conn.execute(
            "INSERT INTO entries (key, source, fetched_at, status, body) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET source=excluded.source, fetched_at=excluded.fetched_at, "
            "status=excluded.status, body=excluded.body",
            (key, source, when.isoformat(), status, zlib.compress(body)),
        )
        self._conn.commit()
        return Entry(key, source, when, status, body)

    def info(self) -> CacheInfo:
        n, lo, hi = self._conn.execute(
            "SELECT COUNT(*), MIN(fetched_at), MAX(fetched_at) FROM entries"
        ).fetchone()
        size = self.path.stat().st_size if self.path.exists() else 0
        return CacheInfo(
            path=self.path,
            entries=n or 0,
            bytes_on_disk=size,
            oldest=_parse(lo) if lo else None,
            newest=_parse(hi) if hi else None,
        )

    def clear(self) -> int:
        """Empty the cache. Returns how many entries were removed."""
        n = self._conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0] or 0
        self._conn.execute("DELETE FROM entries")
        self._conn.commit()
        self._conn.execute("VACUUM")
        return n
