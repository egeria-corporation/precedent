"""Deciding when two award records are the same organization.

This is the most consequential code in the project. The repeat-winner and new-entrant rates
are the two statistics people will quote, and both are counts of *distinct organizations*.
Split one grantee into two and a program looks more open than it is; merge two into one and
it looks closed. Either way the number reads as authoritative.

Resolution runs in descending order of how much the identifier is worth:

1. **Unique Entity Identifier.** Assigned, unique, and the reason SAM.gov exists.
2. **USAspending's recipient id**, with its level suffix stripped. The same organization
   appears as ``...-C`` (child), ``-R`` (recipient) and ``-P`` (parent); keeping the suffix
   splits one organization into three.
3. **Normalized name.** A last resort, and the report says how often it was needed, because
   a program resolved mostly by name has weaker statistics than one resolved by UEI.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

# Applied repeatedly: "FOO SERVICES INC LLC" loses both, "THE FOO CO" loses CO then THE.
LEGAL_SUFFIXES = (
    "INCORPORATED",
    "CORPORATION",
    "COMPANY",
    "LIMITED",
    "INC",
    "LLC",
    "LLP",
    "LP",
    "CORP",
    "CO",
    "LTD",
    "PC",
    "PA",
    "THE",
)

# Whole-token expansions only. Substring replacement would turn "COSTA" into "COMPANYSTA".
ABBREVIATIONS = {
    "DEPT": "DEPARTMENT",
    "UNIV": "UNIVERSITY",
    "ASSN": "ASSOCIATION",
    "ASSOC": "ASSOCIATION",
    "NATL": "NATIONAL",
    "INTL": "INTERNATIONAL",
    "SVCS": "SERVICES",
    "SVC": "SERVICES",
    "CTR": "CENTER",
    "CNTY": "COUNTY",
    "US": "UNITED STATES",
    "AAA": "AREA AGENCY ON AGING",
}

# "ST LOUIS" is a city and "ST STATE" is nonsense, so this expands only in first position,
# where "ST DEPARTMENT OF HEALTH" means the state's.
FIRST_TOKEN_ABBREVIATIONS = {"ST": "STATE"}

_NOT_ALNUM = re.compile(r"[^A-Z0-9 ]")
_SPACES = re.compile(r"\s+")
_LEVEL_SUFFIX = re.compile(r"-(C|R|P)$", re.IGNORECASE)

# The share of records resolved by name above which the statistics deserve a warning.
NAME_TIER_WARNING_THRESHOLD = 0.10


def normalize_name(raw: str | None) -> str:
    """One organization name reduced to a comparable form.

    Used for identity here and for pass-through name clustering, deliberately the same
    function: two places that normalize differently would disagree about the same
    organization, and that disagreement would be invisible.
    """
    if not raw:
        return ""
    text = unicodedata.normalize("NFKD", raw).upper()
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("&", " AND ")
    text = _NOT_ALNUM.sub(" ", text)
    text = _SPACES.sub(" ", text).strip()
    if not text:
        return ""

    tokens = text.split()
    if tokens and tokens[0] in FIRST_TOKEN_ABBREVIATIONS:
        tokens[0] = FIRST_TOKEN_ABBREVIATIONS[tokens[0]]
    tokens = [ABBREVIATIONS.get(t, t) for t in tokens]
    text = " ".join(tokens)

    # Strip trailing legal suffixes until none matches, then a leading THE.
    changed = True
    while changed:
        changed = False
        for suffix in LEGAL_SUFFIXES:
            if text.endswith(f" {suffix}"):
                text = text[: -(len(suffix) + 1)].strip()
                changed = True
                break
    if text.startswith("THE "):
        text = text[4:].strip()
    return text


def strip_level_suffix(recipient_id: str | None) -> str | None:
    """USAspending's recipient id without its ``-C``/``-R``/``-P`` level marker."""
    if not recipient_id:
        return None
    return _LEVEL_SUFFIX.sub("", recipient_id.strip()) or None


class HasIdentity(Protocol):
    """What identity resolution needs from a record. ``Award`` satisfies it."""

    recipient_uei: str | None
    recipient_id: str | None
    recipient_name: str | None


@dataclass(frozen=True)
class Identity:
    """How one record was resolved, and to what."""

    tier: str  # "uei" | "recipient_id" | "name"
    value: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.tier, self.value)


def resolve(record: HasIdentity) -> Identity | None:
    """The strongest identity available for one record, or None if there is nothing."""
    uei = (record.recipient_uei or "").strip().upper()
    if len(uei) == 12:
        return Identity("uei", uei)
    stripped = strip_level_suffix(record.recipient_id)
    if stripped:
        return Identity("recipient_id", stripped)
    name = normalize_name(record.recipient_name)
    if name:
        return Identity("name", name)
    return None


def resolution_mix(identities: list[Identity | None]) -> dict[str, float]:
    """The share of records resolved at each tier, rounded to four places.

    Published in the report because it is the honest measure of how much the distinct-
    organization counts can bear.
    """
    total = len(identities)
    if not total:
        return {}
    counts = Counter(i.tier if i else "unresolved" for i in identities)
    return {tier: round(n / total, 4) for tier, n in counts.items()}


def name_tier_is_high(
    mix: dict[str, float], threshold: float = NAME_TIER_WARNING_THRESHOLD
) -> bool:
    """Whether enough records fell through to name matching to warrant a caveat."""
    return mix.get("name", 0.0) > threshold
