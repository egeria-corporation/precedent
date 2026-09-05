"""Human-readable output.

Two rules shape everything here. Every number carries its source and retrieval date, so no
figure can be quoted without its provenance. And the headline is the new-entrant rate stated
as a sentence, because "39.1%" invites a reader to substitute their own meaning while
"284 of 726 recipients had won nothing under this program in the five years before" does not.
"""

from __future__ import annotations

from precedent import DISCLOSURE
from precedent.analysis.profile import Profile
from precedent.api import HistoryResult

RULE = "-" * 78


def money(value: float | None) -> str:
    return "-" if value is None else f"${value:,.0f}"


def pct(value: float | None) -> str:
    return "-" if value is None else f"{value:.1%}"


def _headline(p: Profile) -> str:
    """The sentence a consultant can repeat to a client without misreading it."""
    if not p.recipient_count:
        return "No recipients found in this window."
    bound = " at most" if p.new_entrant_rate_is_upper_bound else ""
    return (
        f"{p.new_entrant_count} of {p.recipient_count} recipients in "
        f"FY{p.since_fy}-FY{p.until_fy} had{bound} won no award under this program in the "
        f"FY{p.lookback_since_fy}-FY{p.since_fy - 1} lookback."
    )


def render_history(result: HistoryResult) -> str:
    p = result.profile
    s = p.sizes
    out: list[str] = []
    add = out.append

    add(f"Assistance Listing {p.program}, FY{p.since_fy} through FY{p.until_fy}")
    add(RULE)
    add("")
    add(
        f"NEW-ENTRANT RATE  {pct(p.new_entrant_rate)}{' (upper bound)' if p.new_entrant_rate_is_upper_bound else ''}"
    )
    add(f"  {_headline(p)}")
    add("")
    add(
        f"{p.window_award_count:,} awards to {p.recipient_count:,} distinct recipients, "
        f"{money(s.total)} obligated."
    )
    add(
        f"Repeat winners: {p.repeat_winner_count:,} of {p.recipient_count:,} "
        f"({pct(p.repeat_winner_rate)}) won more than once in the window."
    )
    if p.concentration_top10_share is not None:
        add(f"The top 10 recipients hold {pct(p.concentration_top10_share)} of the dollars.")
    add("")

    if s.count:
        add("AWARD SIZE  (total obligated over the life of each award, not per year)")
        add(
            f"  median {money(s.median)}    mean {money(s.mean)}"
            f"{'  (skewed by large awards)' if s.mean_is_skewed else ''}"
        )
        add(
            f"  p10 {money(s.percentiles.get('p10'))}   p25 {money(s.percentiles.get('p25'))}   "
            f"p75 {money(s.percentiles.get('p75'))}   p90 {money(s.percentiles.get('p90'))}"
        )
        add(f"  range {money(s.minimum)} to {money(s.maximum)} across {s.count:,} awards")
        add("")
        add("  " + "  ".join(f"{b.name} {b.count} ({b.share_of_awards:.0%})" for b in s.buckets))
        add("")

    if p.top_recipients_by_dollars:
        add("TOP RECIPIENTS BY DOLLARS")
        for row in p.top_recipients_by_dollars:
            awards = f"{row.award_count} award{'' if row.award_count == 1 else 's'}"
            add(f"  {money(row.total_dollars):>16}  {awards:<11}  {row.display_name}")
        add("")

    if p.top_states_by_count:
        add(f"GEOGRAPHY  {p.states_covered} states or territories")
        add("  " + ", ".join(f"{st} {n}" for st, n in p.top_states_by_count))
        add("")

    if p.caveats:
        add("READ THIS BEFORE QUOTING ANY OF THE ABOVE")
        for caveat in p.caveats:
            add(f"  - {caveat}")
        add("")

    resolution = ", ".join(f"{k} {v:.0%}" for k, v in sorted(p.identity_resolution.items()))
    add(f"Recipients were matched by: {resolution}.")
    if p.excluded.missing_date or p.excluded.nonpositive_amount:
        add(
            f"Excluded: {p.excluded.missing_date} undated, "
            f"{p.excluded.nonpositive_amount} with no positive amount."
        )
    add("")
    retrieved = result.provenance.retrieved
    add(
        f"Source: USAspending, retrieved {retrieved.date().isoformat() if retrieved else 'unknown'}."
    )
    add(DISCLOSURE)
    return "\n".join(out)
