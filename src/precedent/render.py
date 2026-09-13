"""Human-readable output.

Two rules shape everything here. Every number carries its source and retrieval date, so no
figure can be quoted without its provenance. And the headline is the new-entrant rate stated
as a sentence, because "39.1%" invites a reader to substitute their own meaning while
"284 of 726 recipients had won nothing under this program in the five years before" does not.
"""

from __future__ import annotations

from precedent import DISCLOSURE
from precedent.analysis.profile import Profile
from precedent.api import HistoryResult, PassthroughOutcome, RecipientOutcome

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


def render_passthrough(outcome: PassthroughOutcome, *, show_name_variants: bool = False) -> str:
    """The pass-through answer, with the coverage qualification attached rather than footnoted.

    The threshold note is printed in full and not summarised. A reader who takes a
    subrecipient count from this output and treats it as a total will be wrong by however
    many organizations spend under the single audit threshold, which is most of them.
    """
    r = outcome.result
    c = r.coverage
    out: list[str] = []
    add = out.append

    scope = f"{r.state}" + (f", Assistance Listing {r.program}" if r.program else ", all programs")
    add(f"Federal pass-through funders in {scope}")
    add(RULE)
    add("")
    years = f"FY{c.audit_years[0]}-FY{c.audit_years[-1]}" if c.audit_years else "no audit years"
    add(f"{c.audits_scanned:,} single audits scanned, {years}.")
    add("")

    if not r.intermediaries:
        add("No organization in this state reported receiving money through a pass-through")
        add("entity under this filter. That is not the same as nobody doing it: see below.")
        add("")
    else:
        add("WHO PASSES MONEY DOWN TO ORGANIZATIONS HERE")
        add("  Ranked by how many distinct organizations name them, not by dollars: the")
        add("  question is who makes subawards to organizations like yours.")
        add("")
        for e in r.intermediaries:
            orgs = f"{e.subrecipient_count} org{'' if e.subrecipient_count == 1 else 's'}"
            add(f"  {orgs:<9} {money(e.amount_expended_total):>14}   {e.canonical_name}")
            marks = []
            if e.ein:
                marks.append(f"EIN {e.ein} ({e.identifier_source.replace('_', ' ')})")
            if e.entity_type:
                marks.append(e.entity_type.replace("_", " "))
            marks.append(
                f"seen in {e.observation_count} audit{'' if e.observation_count == 1 else 's'}"
            )
            if e.from_alias_table:
                marks.append("name from the alias table")
            if e.merged_by_fuzzy:
                marks.append(f"--fuzzy merged {len(e.merged_by_fuzzy)}")
            add(f"            {'; '.join(marks)}")
            if e.programs:
                add("            " + ", ".join(f"{p} x{n}" for p, n in e.programs[:5]))
            if show_name_variants and len(e.name_variants) > 1:
                add(f"            {len(e.name_variants)} spellings on the schedules:")
                for v in e.name_variants:
                    add(f"              {v.count:>3}  {v.raw}   ({v.example_report_id})")
        add("")

    if r.suppliers:
        add("ORGANIZATIONS HERE THAT REPORT PASSING MONEY DOWN")
        add("  Their own audits, so these carry a real EIN and a real city.")
        add("")
        for s in r.suppliers[:15]:
            add(f"  {money(s.passthrough_amount_total):>14}   {s.name}")
            bits = [b for b in (s.ein and f"EIN {s.ein}", s.city, s.entity_type) if b]
            add(f"            {'; '.join(bits)}")
        add("")

    add("READ THIS BEFORE QUOTING ANY COUNT ABOVE")
    for line in _wrap(c.threshold_note):
        add(f"  {line}")
    for note in c.notes:
        add("")
        for line in _wrap(note):
            add(f"  {line}")
    add("")
    add(f"Source: Federal Audit Clearinghouse, retrieved {c.fac_retrieved or 'unknown'}.")
    add(f"{c.fac_data_vintage_note}. Coverage begins with audit year {c.fac_earliest_audit_year}.")
    add(DISCLOSURE)
    return "\n".join(out)


def _wrap(text: str, width: int = 76) -> list[str]:
    import textwrap

    return textwrap.wrap(text, width=width)


def render_recipient(outcome: RecipientOutcome) -> str:
    """One organization, with each source's silence labelled as silence rather than zero."""
    p = outcome.profile
    out: list[str] = []
    add = out.append

    add(f"{p.resolved_name or p.query}")
    add(RULE)
    add("")
    ident = [
        b
        for b in (
            p.resolved_uei and f"UEI {p.resolved_uei}",
            p.resolved_ein and f"EIN {p.resolved_ein}",
            p.audits and p.audits.entity_type,
            p.audits and p.audits.city and f"{p.audits.city}, {p.audits.state}",
        )
        if b
    ]
    if ident:
        add("  " + "  ".join(ident))
    add(f"  searched as {p.identifier_kind}; answered from {', '.join(p.sources) or 'no source'}")
    add("")

    if p.audits:
        a = p.audits
        add("SINGLE AUDITS")
        add(f"  {a.audit_count} on file, {a.audit_years[0]}-{a.audit_years[-1]}")
        if a.latest_total_expended is not None:
            add(f"  most recent year federal expenditures: {money(a.latest_total_expended)}")
        if a.passes_money_down:
            add(f"  passes money down to subrecipients: {money(a.passthrough_amount_total)}")
        add("")

    if p.funded_by:
        add("FUNDED THROUGH  (named by this organization's own auditors)")
        for name, amount in p.funded_by:
            add(f"  {money(amount):>14}   {name}")
        add("")

    if p.awards:
        w = p.awards
        add("DIRECT FEDERAL AWARDS")
        add(
            f"  {w.award_count:,} awards, {money(w.total_obligated)} obligated, FY{w.first_fy}-FY{w.last_fy}"
        )
        if w.programs:
            add("  " + ", ".join(f"{code} x{n}" for code, n in w.programs[:6]))
        add("")

    if p.caveats:
        add("READ THIS BEFORE QUOTING ANY OF THE ABOVE")
        for caveat in p.caveats:
            for line in _wrap(caveat):
                add(f"  {line}")
            add("")

    retrieved = outcome.provenance.retrieved
    sources = " and ".join(p.sources) if p.sources else "no source"
    add(f"Source: {sources}, retrieved {retrieved.date().isoformat() if retrieved else 'unknown'}.")
    add(DISCLOSURE)
    return "\n".join(out)
