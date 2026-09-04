"""Environment, cache location, time-to-live, and the User-Agent this tool identifies with.

Everything here is read from the environment with a working default, because the first rule
of this project is that `precedent history` runs for someone who has set nothing at all.

The platform cache directory is computed rather than taken from a dependency: it is fifteen
lines, and the dependency list in the build prompt is deliberately short.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from precedent import __version__

REPO_URL = "https://github.com/egeria-corporation/precedent"

# Hours. Chosen to match how often each upstream actually changes, not to be aggressive for
# its own sake: FAC's production data refreshes weekly, typically on Wednesdays, and
# USAspending's award records for closed fiscal years do not change at all.
DEFAULT_TTL_HOURS = {"usaspending": 168, "fac": 168, "opengrants": 24}

TTL_ENV = {
    "usaspending": "PRECEDENT_CACHE_TTL_USASPENDING_HOURS",
    "fac": "PRECEDENT_CACHE_TTL_FAC_HOURS",
    "opengrants": "PRECEDENT_CACHE_TTL_OPENGRANTS_HOURS",
}

# Maximum requests in flight against a single upstream. Sequential is fine and preferred;
# two is the ceiling the build prompt sets for free public infrastructure.
MAX_CONCURRENCY = 2

_TRUE = {"1", "true", "yes", "on"}


def _platform_cache_root() -> Path:
    """The conventional per-user cache directory for this platform."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        return Path(base) / "precedent" / "Cache" if base else Path.home() / ".cache" / "precedent"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "precedent"
    xdg = os.environ.get("XDG_CACHE_HOME")
    return (Path(xdg) if xdg else Path.home() / ".cache") / "precedent"


def _positive_int(raw: str, default: int) -> int:
    """A positive integer from an environment string, or the default. Never raises.

    A malformed override must not stop a command: the failure mode of refusing to run
    because `PRECEDENT_CACHE_TTL_FAC_HOURS=seven` is worse than quietly using the default.
    """
    try:
        value = int(raw.strip())
    except (AttributeError, ValueError):
        return default
    return value if value > 0 else default


@dataclass(frozen=True)
class Config:
    """One resolved view of the environment, passed explicitly rather than read globally."""

    cache_dir: Path
    ttl_hours: dict[str, int]
    contact: str | None
    no_cache: bool
    fac_api_key: str | None
    opengrants_api_key: str | None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Config:
        e = os.environ if env is None else env
        cache_dir = e.get("PRECEDENT_CACHE_DIR", "").strip()
        return cls(
            cache_dir=Path(cache_dir) if cache_dir else _platform_cache_root(),
            ttl_hours={
                source: _positive_int(e.get(var, ""), DEFAULT_TTL_HOURS[source])
                for source, var in TTL_ENV.items()
            },
            contact=e.get("PRECEDENT_CONTACT", "").strip() or None,
            no_cache=e.get("PRECEDENT_NO_CACHE", "").strip().lower() in _TRUE,
            fac_api_key=e.get("FAC_API_KEY", "").strip() or None,
            opengrants_api_key=e.get("OPENGRANTS_API_KEY", "").strip() or None,
        )

    def ttl_for(self, source: str) -> int:
        """Time to live in hours for one upstream, falling back to the shortest default."""
        return self.ttl_hours.get(source, min(DEFAULT_TTL_HOURS.values()))

    @property
    def user_agent(self) -> str:
        """Who we are, so an operator whose service we strain can reach us.

        Being a good citizen of free public infrastructure is a requirement of this project,
        and an unreachable client is the version of that requirement nobody can act on.
        """
        return f"precedent/{__version__} (+{REPO_URL}; {self.contact or REPO_URL})"
