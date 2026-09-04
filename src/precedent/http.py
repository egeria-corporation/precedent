"""The shared HTTP client: cache first, then a polite request with retry and backoff.

Both upstreams are free public infrastructure funded by taxpayers and neither owes us
throughput, so the defaults here are deliberately conservative: at most two requests in
flight, exponential backoff with jitter on 429 and 5xx, at least five attempts, and a
User-Agent that names the project and a way to reach whoever is running it.

Every response, cached or fresh, comes back with the date it was retrieved. Callers pass
those dates to ``cache.oldest`` so a computed result reports the age of its stalest input.
"""

from __future__ import annotations

import json
import random
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from precedent.cache import Cache, cache_key
from precedent.config import MAX_CONCURRENCY, Config
from precedent.errors import UpstreamError

RETRY_STATUS = {429, 500, 502, 503, 504}
ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 1.0
BACKOFF_CAP_SECONDS = 30.0
TIMEOUT = httpx.Timeout(30.0, read=120.0)


@dataclass(frozen=True)
class Response:
    """One upstream response and the provenance that has to travel with it."""

    status: int
    body: bytes
    fetched_at: datetime
    from_cache: bool

    def json(self) -> Any:
        return json.loads(self.body)


def backoff_seconds(attempt: int, retry_after: str | None = None) -> float:
    """Exponential backoff with jitter, honouring Retry-After when the server sends one.

    Jitter matters more than it looks: without it, several clients that hit the same rate
    limit retry in lockstep and reproduce the burst that caused it.
    """
    if retry_after:
        try:
            return min(float(retry_after), BACKOFF_CAP_SECONDS)
        except ValueError:
            pass
    ceiling = min(BACKOFF_BASE_SECONDS * (2**attempt), BACKOFF_CAP_SECONDS)
    return random.uniform(ceiling / 2, ceiling)


class HttpClient:
    """Cache-aware HTTP for one process. Construct once per command, close when done."""

    def __init__(
        self,
        config: Config,
        *,
        cache: Cache | None = None,
        client: httpx.Client | None = None,
        sleep=time.sleep,
    ) -> None:
        self.config = config
        self.cache = cache if cache is not None else Cache(config.cache_dir)
        self._owns_cache = cache is None
        self._client = client or httpx.Client(
            timeout=TIMEOUT, headers={"User-Agent": config.user_agent}, follow_redirects=True
        )
        self._owns_client = client is None
        self._gate = threading.Semaphore(MAX_CONCURRENCY)
        self._sleep = sleep

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
        if self._owns_cache:
            self.cache.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def request(
        self,
        source: str,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        headers: dict[str, str] | None = None,
        no_cache: bool | None = None,
    ) -> Response:
        """Fetch, preferring a live cache entry. Writes to the cache even when reads are off.

        ``--no-cache`` means "do not trust what I stored", not "do not store": the next run
        should still be fast, and the entry it writes carries an honest retrieval date.
        """
        bypass = self.config.no_cache if no_cache is None else no_cache
        key = cache_key(source, method, url, json_body if json_body is not None else params)
        if not bypass:
            hit = self.cache.get(key, ttl_hours=self.config.ttl_for(source))
            if hit is not None:
                return Response(hit.status, hit.body, hit.fetched_at, from_cache=True)

        last_detail = "no attempt was made"
        last_status: int | None = None
        for attempt in range(ATTEMPTS):
            retry_after: str | None = None
            try:
                with self._gate:
                    r = self._client.request(
                        method.upper(), url, params=params, json=json_body, headers=headers
                    )
            except httpx.HTTPError as error:
                last_detail, last_status = f"{type(error).__name__}: {error}", None
            else:
                if r.status_code < 400:
                    fetched_at = datetime.now(UTC)
                    self.cache.put(
                        key,
                        source=source,
                        status=r.status_code,
                        body=r.content,
                        fetched_at=fetched_at,
                    )
                    return Response(r.status_code, r.content, fetched_at, from_cache=False)
                last_status, last_detail = r.status_code, r.text[:300]
                # A 4xx that is not a rate limit fails identically five times over.
                if r.status_code not in RETRY_STATUS:
                    raise UpstreamError(source, last_status, last_detail)
                retry_after = r.headers.get("Retry-After")
            if attempt < ATTEMPTS - 1:
                self._sleep(backoff_seconds(attempt, retry_after))
        raise UpstreamError(
            source, last_status, f"gave up after {ATTEMPTS} attempts: {last_detail}"
        )

    def get_json(self, source: str, url: str, **kwargs: Any) -> tuple[Any, datetime]:
        """A parsed JSON body and the date it was retrieved."""
        r = self.request(source, "GET", url, **kwargs)
        return r.json(), r.fetched_at

    def post_json(
        self, source: str, url: str, json_body: Any, **kwargs: Any
    ) -> tuple[Any, datetime]:
        r = self.request(source, "POST", url, json_body=json_body, **kwargs)
        return r.json(), r.fetched_at
