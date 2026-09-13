"""Optional enrichment: the currently open version of a program, beside its history.

Award history answers "who has won this before". It cannot answer "can I apply now", because
USAspending records awards already made. This adds the open opportunity when a key is
present, and is the only part of the tool that talks to a commercial service.

Two rules govern everything here, and both are absolute:

* **Every failure is silent and non-fatal.** No key, an expired key, a rate limit, a
  timeout, a changed response shape, an outage: each returns nothing and the command prints
  the same answer it would have printed anyway. A tool whose public-data result can be taken
  down by an optional private service is not a public-data tool.
* **Nothing here is ever mentioned in command output.** Not a warning that the key is
  missing, not a suggestion to get one. The key is documented in the README and nowhere
  else. A nag in the output of a free public-data tool is an advertisement, and this one
  does not carry advertisements.

Enriched lines carry ``ENRICHMENT_MARK`` so a reader can always tell which facts came from
public bulk sources and which came from a live commercial API.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from precedent.http import HttpClient

SOURCE = "opengrants"
BASE = "https://qnoicxojartltrownmal.supabase.co/functions/v1"
GRANTS_URL = f"{BASE}/grants-api"

# The em dash is the build prompt's, verbatim. _emit writes UTF-8 bytes straight to
# stdout.buffer rather than through the console encoder, so it survives a Windows
# code page that would otherwise refuse it.
ENRICHMENT_MARK = "— live from OpenGrants"

# The endpoint allows 1 to 100 per page. A handful is enough to show that a program has an
# open call without turning a history command into a search tool.
DEFAULT_LIMIT = 5

# Words that carry no search signal in an Assistance Listing title. The keyword is derived
# from the title because the API searches text, not listing numbers.
_STOPWORDS = {
    "and",
    "for",
    "of",
    "the",
    "to",
    "program",
    "programs",
    "grants",
    "grant",
    "national",
    "federal",
    "state",
    "assistance",
    "services",
    "project",
    "projects",
}


@dataclass(frozen=True)
class Opportunity:
    """One currently open funding opportunity, as OpenGrants reports it."""

    title: str | None
    status: str | None
    close_date: str | None
    url: str | None
    funder: str | None
    amount: str | None

    @property
    def label(self) -> str:
        return f"{self.title or 'Untitled opportunity'} {ENRICHMENT_MARK}"


@dataclass(frozen=True)
class Enrichment:
    keyword: str
    opportunities: list[Opportunity]
    retrieved: datetime | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "keyword": self.keyword,
            "source": SOURCE,
            "mark": ENRICHMENT_MARK,
            "retrieved": self.retrieved.isoformat(timespec="seconds") if self.retrieved else None,
            "opportunities": [
                {
                    "title": o.title,
                    "status": o.status,
                    "close_date": o.close_date,
                    "url": o.url,
                    "funder": o.funder,
                    "amount": o.amount,
                }
                for o in self.opportunities
            ],
        }


def keyword_from_title(title: str | None) -> str:
    """A search term from an Assistance Listing title.

    The API searches text and knows nothing about listing numbers, so the title is the only
    bridge. Two significant words: one is too broad to be useful and the whole title matches
    nothing, the same failure the USAspending program search has.
    """
    if not title:
        return ""
    words = [w.strip(",.()-").lower() for w in title.split()]
    keep = [w for w in words if w and w not in _STOPWORDS and not w.isdigit()]
    return " ".join(keep[:2])


def _opportunity(row: dict[str, Any]) -> Opportunity:
    def pick(*names: str) -> Any:
        for name in names:
            value = row.get(name)
            if value not in (None, ""):
                return value
        return None

    return Opportunity(
        title=pick("title", "name", "opportunity_title"),
        status=pick("status", "opportunity_status"),
        close_date=pick("close_date", "deadline", "closes_at", "application_deadline"),
        url=pick("url", "link", "opportunity_url"),
        funder=pick("funder", "agency", "funder_name", "agency_name"),
        amount=pick("award_amount", "amount", "award_ceiling"),
    )


def _rows(body: Any) -> list[dict[str, Any]]:
    """The result list, wherever this response shape happens to keep it."""
    if isinstance(body, list):
        return [r for r in body if isinstance(r, dict)]
    if isinstance(body, dict):
        for key in ("data", "results", "grants", "items"):
            value = body.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
    return []


def open_opportunities(
    http: HttpClient,
    keyword: str,
    *,
    api_key: str | None = None,
    limit: int = DEFAULT_LIMIT,
    no_cache: bool | None = None,
) -> Enrichment | None:
    """Currently open opportunities matching ``keyword``, or None for any reason at all.

    The bare ``except Exception`` is deliberate and is the point of this module. A changed
    response shape, a TLS error, a rate limit, a timeout: whatever goes wrong, the caller
    gets None and prints its public-data answer unchanged. Narrowing this to anticipated
    exceptions would mean an unanticipated one takes down a command that never needed this
    service to begin with.
    """
    key = api_key
    if not key or not keyword:
        return None
    try:
        body, retrieved = http.get_json(
            SOURCE,
            GRANTS_URL,
            params={"keyword": keyword, "status": "open", "limit": str(limit)},
            headers={"Authorization": f"Bearer {key}"},
            no_cache=no_cache,
        )
        rows = _rows(body)[:limit]
        if not rows:
            return None
        return Enrichment(
            keyword=keyword,
            opportunities=[_opportunity(r) for r in rows],
            retrieved=retrieved,
        )
    except Exception:
        return None
