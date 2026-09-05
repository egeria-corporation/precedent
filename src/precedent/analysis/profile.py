"""Award history statistics for one program.

The headline is the **new-entrant rate**: the share of a window's recipients that had won
nothing under this program in the preceding lookback. Median award size tells a consultant
whether their client is in the right weight class. The new-entrant rate tells them whether
the door is open at all, and a program with a healthy median and a new-entrant rate near
zero is a closed shop with good optics.

Conventions here are pinned rather than chosen at the point of use, because two defensible
choices produce two different numbers and only one of them can be reproduced:

* A fiscal year runs from October 1 of the prior calendar year to September 30.
* An award belongs to the fiscal year of its **first obligating action**, not the year we
  happened to fetch it in.
* Percentiles use ``method="inclusive"``. The standard library default is exclusive and
  gives different answers on small samples, which is exactly a niche program's situation.
* Distribution buckets are fixed, not data-derived, so two programs can be compared.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from precedent.analysis.identity import Identity, name_tier_is_high, resolution_mix, resolve
from precedent.sources.usaspending import COVERAGE_START, Award

DEFAULT_LOOKBACK_YEARS = 5
TOP_N = 10
CONCENTRATION_TOP_N = 10

# Half-open [lo, hi). Fixed so that two programs are comparable; a data-derived scale would
# make every program look average.
BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("under_100k", 0, 100_000),
    ("100k_250k", 100_000, 250_000),
    ("250k_500k", 250_000, 500_000),
    ("500k_1m", 500_000, 1_000_000),
    ("1m_5m", 1_000_000, 5_000_000),
    ("5m_plus", 5_000_000, float("inf")),
)

MULTI_LISTING_CAVEAT_THRESHOLD = 0.10
SKEW_FACTOR = 2.0


def fiscal_year(day: date) -> int:
    """The federal fiscal year containing ``day``."""
    return day.year + 1 if day.month >= 10 else day.year


def fiscal_year_start(fy: int) -> date:
    return date(fy - 1, 10, 1)


def fiscal_year_end(fy: int) -> date:
    return date(fy, 9, 30)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value[:10]).date()
    except ValueError:
        return None


def award_fiscal_year(award: Award) -> int | None:
    """The fiscal year an award belongs to, from its first obligating action.

    Falls back to the start date, because an award with no base obligation date but a real
    start date is still evidence of a recipient; only an award with neither is dropped.
    """
    day = _parse_date(award.base_obligation_date) or _parse_date(award.start_date)
    return fiscal_year(day) if day else None


@dataclass
class Excluded:
    """Awards left out of some statistic, counted rather than silently dropped."""

    missing_date: int = 0
    nonpositive_amount: int = 0
    unresolved_identity: int = 0


@dataclass
class Bucket:
    name: str
    count: int
    share_of_awards: float
    share_of_dollars: float


@dataclass
class SizeStats:
    count: int
    total: float
    mean: float | None
    median: float | None
    minimum: float | None
    maximum: float | None
    percentiles: dict[str, float]
    buckets: list[Bucket]
    mean_is_skewed: bool


@dataclass
class RecipientRow:
    display_name: str
    identity: str
    uei: str | None
    award_count: int
    total_dollars: float


@dataclass
class Profile:
    """Everything ``precedent history`` reports for one program."""

    program: str
    since_fy: int
    until_fy: int
    lookback_years: int
    lookback_since_fy: int

    window_award_count: int
    lookback_award_count: int
    recipient_count: int

    new_entrant_count: int
    new_entrant_rate: float | None
    new_entrant_rate_is_upper_bound: bool
    repeat_winner_count: int
    repeat_winner_rate: float | None
    concentration_top10_share: float | None
    multi_listing_share: float

    sizes: SizeStats
    states_covered: int
    top_states_by_count: list[tuple[str, int]]
    top_states_by_dollars: list[tuple[str, float]]
    top_recipients_by_count: list[RecipientRow]
    top_recipients_by_dollars: list[RecipientRow]

    identity_resolution: dict[str, float]
    excluded: Excluded
    caveats: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)


def size_stats(amounts: list[float]) -> SizeStats:
    """Award-size statistics over amount-eligible awards."""
    if not amounts:
        return SizeStats(0, 0.0, None, None, None, None, {}, [], False)
    ordered = sorted(amounts)
    total = float(sum(ordered))
    mean = total / len(ordered)
    median = statistics.median(ordered)

    percentiles: dict[str, float] = {}
    if len(ordered) >= 2:
        # Inclusive is pinned: the default (exclusive) disagrees on small samples, and a
        # niche program is a small sample. p50 here must equal the median.
        cuts = statistics.quantiles(ordered, n=100, method="inclusive")
        percentiles = {f"p{p}": cuts[p - 1] for p in (10, 25, 50, 75, 90)}
    else:
        only = ordered[0]
        percentiles = {f"p{p}": only for p in (10, 25, 50, 75, 90)}

    buckets = []
    for name, lo, hi in BUCKETS:
        inside = [a for a in ordered if lo <= a < hi]
        buckets.append(
            Bucket(
                name=name,
                count=len(inside),
                share_of_awards=len(inside) / len(ordered),
                share_of_dollars=(sum(inside) / total) if total else 0.0,
            )
        )
    return SizeStats(
        count=len(ordered),
        total=total,
        mean=mean,
        median=median,
        minimum=ordered[0],
        maximum=ordered[-1],
        percentiles=percentiles,
        buckets=buckets,
        mean_is_skewed=mean > SKEW_FACTOR * median if median else False,
    )


def _display_name(names: Counter[str]) -> str:
    """The raw name a consultant would recognize: the most frequent one, ties by spelling."""
    if not names:
        return ""
    best = max(names.values())
    return sorted(n for n, c in names.items() if c == best)[0]


def build_profile(
    awards: list[Award],
    *,
    program: str,
    since_fy: int,
    until_fy: int,
    lookback_years: int = DEFAULT_LOOKBACK_YEARS,
) -> Profile:
    """Compute the full award-history profile from one deduplicated pull."""
    lookback_since_fy = since_fy - lookback_years
    excluded = Excluded()

    window: list[Award] = []
    lookback: list[Award] = []
    for award in awards:
        fy = award_fiscal_year(award)
        if fy is None:
            excluded.missing_date += 1
            continue
        if since_fy <= fy <= until_fy:
            window.append(award)
        elif lookback_since_fy <= fy < since_fy:
            lookback.append(award)

    # Identity is resolved for every window award, including zero-dollar ones: winning a
    # net-zero award still means the organization was a recipient.
    window_identities: list[Identity | None] = [resolve(a) for a in window]
    excluded.unresolved_identity = sum(1 for i in window_identities if i is None)

    awards_by_identity: dict[tuple[str, str], set[str]] = defaultdict(set)
    dollars_by_identity: dict[tuple[str, str], float] = defaultdict(float)
    names_by_identity: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    uei_by_identity: dict[tuple[str, str], str | None] = {}
    for award, ident in zip(window, window_identities, strict=True):
        if ident is None:
            continue
        key = ident.key
        awards_by_identity[key].add(award.generated_internal_id)
        if award.amount and award.amount > 0:
            dollars_by_identity[key] += award.amount
        if award.recipient_name:
            names_by_identity[key][award.recipient_name] += 1
        uei_by_identity.setdefault(key, award.recipient_uei)

    window_keys = set(awards_by_identity)
    lookback_keys = {i.key for i in (resolve(a) for a in lookback) if i is not None}

    new_entrants = window_keys - lookback_keys
    repeat_winners = {k for k, ids in awards_by_identity.items() if len(ids) >= 2}
    recipient_count = len(window_keys)

    amounts = [a.amount for a in window if a.amount and a.amount > 0]
    excluded.nonpositive_amount = len(window) - len(amounts)
    sizes = size_stats([float(a) for a in amounts])

    ranked_dollars = sorted(
        dollars_by_identity.items(), key=lambda kv: (-kv[1], kv[0])
    )  # ties by identity string, so the result is deterministic
    top10_dollars = sum(v for _, v in ranked_dollars[:CONCENTRATION_TOP_N])
    all_dollars = sum(dollars_by_identity.values())
    concentration = (top10_dollars / all_dollars) if all_dollars else None

    multi = sum(1 for a in window if len(a.assistance_listings) > 1)
    multi_share = (multi / len(window)) if window else 0.0

    states = Counter(a.place_of_performance_state for a in window if a.place_of_performance_state)
    state_dollars: dict[str, float] = defaultdict(float)
    for a in window:
        if a.place_of_performance_state and a.amount and a.amount > 0:
            state_dollars[a.place_of_performance_state] += a.amount

    def rows(order: list[tuple[tuple[str, str], Any]]) -> list[RecipientRow]:
        out = []
        for key, _ in order[:TOP_N]:
            out.append(
                RecipientRow(
                    display_name=_display_name(names_by_identity[key]),
                    identity=f"{key[0]}:{key[1]}",
                    uei=uei_by_identity.get(key),
                    award_count=len(awards_by_identity[key]),
                    total_dollars=dollars_by_identity.get(key, 0.0),
                )
            )
        return out

    by_count = sorted(awards_by_identity.items(), key=lambda kv: (-len(kv[1]), kv[0]))

    mix = resolution_mix(window_identities)
    lookback_truncated = fiscal_year_start(lookback_since_fy) < date.fromisoformat(COVERAGE_START)
    upper_bound = lookback_truncated or not lookback

    caveats: list[str] = []
    if lookback_truncated:
        caveats.append(
            f"The lookback reaches before {COVERAGE_START}, which is as far back as this "
            "search covers. Some recipients counted as new may have won earlier, so the "
            "new-entrant rate is an upper bound."
        )
    if not lookback:
        caveats.append(
            f"No awards at all in the FY{lookback_since_fy}-FY{since_fy - 1} lookback, which "
            "usually means the program did not exist yet. Every recipient therefore counts as "
            "new, and the new-entrant rate is an upper bound."
        )
    if name_tier_is_high(mix):
        caveats.append(
            f"{mix.get('name', 0):.0%} of awards were matched to a recipient by name rather "
            "than by an assigned identifier, so the distinct-organization counts are softer "
            "than usual."
        )
    if multi_share > MULTI_LISTING_CAVEAT_THRESHOLD:
        caveats.append(
            f"{multi_share:.0%} of awards are reported under more than one Assistance "
            "Listing. Award amounts include money from those other programs, so the size "
            "percentiles are an upper bound."
        )
    if sizes.mean_is_skewed:
        caveats.append(
            "The mean award is more than twice the median, so a few large awards are pulling "
            "it upward. The median is the better guide to a typical award."
        )
    if excluded.missing_date:
        caveats.append(
            f"{excluded.missing_date} award(s) had no usable date and were left out entirely."
        )

    return Profile(
        program=program,
        since_fy=since_fy,
        until_fy=until_fy,
        lookback_years=lookback_years,
        lookback_since_fy=lookback_since_fy,
        window_award_count=len(window),
        lookback_award_count=len(lookback),
        recipient_count=recipient_count,
        new_entrant_count=len(new_entrants),
        new_entrant_rate=(len(new_entrants) / recipient_count) if recipient_count else None,
        new_entrant_rate_is_upper_bound=upper_bound,
        repeat_winner_count=len(repeat_winners),
        repeat_winner_rate=(len(repeat_winners) / recipient_count) if recipient_count else None,
        concentration_top10_share=concentration,
        multi_listing_share=multi_share,
        sizes=sizes,
        states_covered=len(states),
        top_states_by_count=states.most_common(TOP_N),
        top_states_by_dollars=sorted(state_dollars.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_N],
        top_recipients_by_count=rows(by_count),
        top_recipients_by_dollars=rows(ranked_dollars),
        identity_resolution=mix,
        excluded=excluded,
        caveats=caveats,
    )
