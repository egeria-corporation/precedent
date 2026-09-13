"""One organization, from both sources, with each source's blind spot stated.

The two datasets identify organizations differently and neither is complete:

* **USAspending** knows a Unique Entity Identifier and a name. It does not know an
  Employer Identification Number, so an EIN cannot be looked up there at all.
* **The Federal Audit Clearinghouse** knows both, which makes it the bridge: an EIN
  resolves to an audit, the audit carries the UEI, and the UEI opens USAspending. It is
  also the only one of the two that knows who passed money *to* this organization.

So the answer for an EIN is richer than the answer for a name, and the answer without a
FAC key is thinner than the answer with one. ``identifier_kind`` and ``sources`` record
which of those situations produced the profile in hand, because a thin answer that does
not say it is thin reads as a complete one.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from precedent.analysis.identity import normalize_name
from precedent.analysis.profile import award_fiscal_year
from precedent.sources.fac import UEI_COVERAGE_FROM_YEAR, Audit, PassThrough, SefaAward
from precedent.sources.usaspending import Award

# A Unique Entity Identifier is twelve alphanumeric characters. SAM.gov excludes I and O to
# avoid confusion with 1 and 0, and never begins one with a zero.
_UEI = re.compile(r"^[A-HJ-NP-Z1-9][A-HJ-NP-Z0-9]{11}$", re.IGNORECASE)
_EIN = re.compile(r"^\d{2}-?\d{7}$")

TOP_N = 10


def classify_identifier(raw: str) -> str:
    """``"uei"``, ``"ein"`` or ``"name"``. Decides which source can even be asked."""
    text = (raw or "").strip()
    if _EIN.match(text):
        return "ein"
    if _UEI.match(text):
        return "uei"
    return "name"


def normalize_ein(raw: str) -> str:
    return re.sub(r"\D", "", raw or "")


@dataclass
class AwardsSummary:
    award_count: int
    total_obligated: float
    first_fy: int | None
    last_fy: int | None
    programs: list[tuple[str, int]]
    agencies: list[tuple[str, int]]
    names_seen: list[str]
    ueis_seen: list[str]


@dataclass
class AuditSummary:
    audit_count: int
    audit_years: list[str]
    latest_total_expended: int | None
    entity_type: str | None
    city: str | None
    state: str | None
    ein: str | None
    uei: str | None
    name: str | None
    passes_money_down: bool
    passthrough_amount_total: int


@dataclass
class RecipientProfile:
    """Everything both sources will say about one organization, and which said it."""

    query: str
    identifier_kind: str
    sources: list[str]
    resolved_name: str | None
    resolved_uei: str | None
    resolved_ein: str | None
    awards: AwardsSummary | None
    audits: AuditSummary | None
    funded_by: list[tuple[str, int]]
    caveats: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)


def summarize_awards(awards: list[Award]) -> AwardsSummary | None:
    if not awards:
        return None
    years = [fy for fy in (award_fiscal_year(a) for a in awards) if fy is not None]
    amounts = [a.amount for a in awards if a.amount and a.amount > 0]
    programs: Counter[str] = Counter()
    for a in awards:
        for listing in a.assistance_listings:
            programs[listing] += 1
    agencies = Counter(a.awarding_agency for a in awards if a.awarding_agency)
    names = Counter(a.recipient_name for a in awards if a.recipient_name)
    ueis = Counter(a.recipient_uei for a in awards if a.recipient_uei)
    return AwardsSummary(
        award_count=len(awards),
        total_obligated=float(sum(amounts)),
        first_fy=min(years) if years else None,
        last_fy=max(years) if years else None,
        programs=programs.most_common(TOP_N),
        agencies=agencies.most_common(TOP_N),
        names_seen=[n for n, _ in names.most_common(TOP_N)],
        ueis_seen=[u for u, _ in ueis.most_common(TOP_N)],
    )


def summarize_audits(audits: list[Audit], awards: list[SefaAward]) -> AuditSummary | None:
    if not audits:
        return None
    ordered = sorted(audits, key=lambda a: a.audit_year or "", reverse=True)
    latest = ordered[0]
    passed = sum(a.passthrough_amount or 0 for a in awards if a.passed_money_down)
    return AuditSummary(
        audit_count=len(audits),
        audit_years=sorted({a.audit_year for a in audits if a.audit_year}),
        latest_total_expended=latest.total_amount_expended,
        entity_type=latest.entity_type,
        city=latest.auditee_city,
        state=latest.auditee_state,
        ein=latest.auditee_ein,
        uei=latest.auditee_uei,
        name=latest.auditee_name,
        passes_money_down=passed > 0,
        passthrough_amount_total=passed,
    )


def summarize_funders(
    indirect: list[SefaAward],
    passthroughs: list[PassThrough],
) -> list[tuple[str, int]]:
    """Who this organization's own auditors say passed money to it, with dollar totals.

    Grouped on the normalized name, not the raw one. Auditors retype the same agency in
    different case and punctuation year to year, and grouping on what they typed lists one
    funder three times with its money split between the spellings. The label shown is the
    spelling used most often, so it still reads the way it appears on a schedule.
    """
    named = {p.key: p for p in passthroughs}
    totals: Counter[str] = Counter()
    spellings: dict[str, Counter[str]] = {}
    for award in indirect:
        entity = named.get(award.key)
        if not entity or not entity.name:
            continue
        raw = entity.name.strip()
        key = normalize_name(raw) or raw.upper()
        totals[key] += award.amount_expended or 0
        spellings.setdefault(key, Counter())[raw] += 1
    out = []
    for key, amount in totals.most_common(TOP_N):
        best = max(spellings[key].values())
        label = sorted(n for n, c in spellings[key].items() if c == best)[0]
        out.append((label, amount))
    return out


def build_recipient_profile(
    *,
    query: str,
    identifier_kind: str,
    awards: list[Award],
    audits: list[Audit],
    sefa_awards: list[SefaAward],
    passthroughs: list[PassThrough],
    fac_available: bool,
) -> RecipientProfile:
    """Assemble the profile and say plainly what each missing half would have added."""
    award_summary = summarize_awards(awards)
    audit_summary = summarize_audits(audits, sefa_awards)
    funded_by = summarize_funders(
        [a for a in sefa_awards if a.received_through_someone], passthroughs
    )

    sources: list[str] = []
    if awards:
        sources.append("usaspending")
    if audits:
        sources.append("fac")

    caveats: list[str] = []
    if identifier_kind == "name":
        caveats.append(
            "You searched by name, and USAspending matches a name loosely: this profile may "
            "combine organizations whose names merely resemble what you typed. Search by "
            "Unique Entity Identifier or Employer Identification Number for an exact answer."
        )
    if award_summary and len(award_summary.ueis_seen) > 1:
        caveats.append(
            f"{len(award_summary.ueis_seen)} distinct Unique Entity Identifiers appear in "
            "these awards, so this is more than one organization. Narrow the query."
        )
    if not fac_available:
        caveats.append(
            "No Federal Audit Clearinghouse key is set, so this profile cannot say what this "
            "organization spends, who passes money to it, or whether it passes money down. "
            "Those are the questions FAC answers and USAspending cannot."
        )
    elif not audits:
        caveats.append(
            "No single audit was found. Organizations spending below the federal single "
            "audit threshold file none at all, so this is not evidence that the "
            "organization is small or inactive, only that it is absent from that dataset."
        )
    if identifier_kind == "uei" and not audits and fac_available:
        caveats.append(
            "A Unique Entity Identifier only finds single audits from about "
            f"{UEI_COVERAGE_FROM_YEAR} onward: audits migrated from the legacy Census "
            "collection carry a placeholder in that column rather than a real identifier, "
            "which covers nearly every record before then. An Employer Identification "
            "Number reaches further back."
        )
    if identifier_kind == "ein" and not awards:
        if audit_summary and audit_summary.uei:
            caveats.append(
                "No direct federal awards were found for this organization. Combined with "
                "the pass-through funders listed above, that is the substantive finding "
                "rather than a gap: this organization is funded through intermediaries, not "
                "by the agency directly."
            )
        else:
            caveats.append(
                "USAspending cannot be searched by Employer Identification Number, and no "
                "single audit supplied a Unique Entity Identifier to look up instead, so "
                "direct award history could not be checked at all."
            )

    resolved_name = (audit_summary.name if audit_summary else None) or (
        award_summary.names_seen[0] if award_summary and award_summary.names_seen else None
    )
    resolved_uei = (audit_summary.uei if audit_summary else None) or (
        award_summary.ueis_seen[0] if award_summary and award_summary.ueis_seen else None
    )
    return RecipientProfile(
        query=query,
        identifier_kind=identifier_kind,
        sources=sources,
        resolved_name=resolved_name,
        resolved_uei=resolved_uei,
        resolved_ein=audit_summary.ein if audit_summary else None,
        awards=award_summary,
        audits=audit_summary,
        funded_by=funded_by,
        caveats=caveats,
    )


def matches_identity(audit: Audit, *, ein: str | None, uei: str | None, name: str | None) -> bool:
    """Whether a FAC audit is the organization asked about."""
    if ein and normalize_ein(audit.auditee_ein or "") == normalize_ein(ein):
        return True
    if uei and (audit.auditee_uei or "").upper() == uei.upper():
        return True
    return bool(
        name and audit.auditee_name and normalize_name(audit.auditee_name) == normalize_name(name)
    )
