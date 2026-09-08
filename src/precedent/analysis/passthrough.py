"""Who actually hands federal money to organizations in one state.

Two evidence streams, computed separately and merged only for display, because they are
different facts and averaging them would produce a number that is neither:

* **Demand side.** Organizations that filed a single audit and reported money received
  *through* somebody. Their auditors typed the name of that somebody. This is the stream
  that answers "who would fund an organization like mine", and its identifiers are bad:
  a free-text name and an unstructured number, no state, no EIN.
* **Supply side.** Organizations in this state whose own audit says they *passed money
  down*. This stream has a real EIN, a real city and a real entity type, because the filer
  is the intermediary itself. It is used to attach identifiers to demand-side clusters, and
  when it does, the result records how - never presenting a name match as an identity match.

The clustering is the part that can produce a false fact, so it is deliberately timid. A
committed alias table does the work a person has checked; everything else clusters by exact
normalized match, within one state, and never across states. ``--fuzzy`` exists and is off,
because a wrongly merged entity asserts something untrue while a split entity merely
undercounts, and this tool would rather undercount.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from precedent.analysis.coverage import PassthroughCoverage, build_coverage
from precedent.analysis.identity import normalize_name
from precedent.sources.fac import Audit, PassThrough, SefaAward, assistance_listing

ALIAS_FILE = Path(__file__).resolve().parent.parent / "data" / "passthrough_aliases.yaml"

# Token-set ratio threshold for --fuzzy. High on purpose: this merges organizations.
FUZZY_THRESHOLD = 92

TOP_SUBRECIPIENTS = 25


@dataclass(frozen=True)
class AliasEntry:
    canonical: str
    state: str
    entity_type: str | None
    ein: str | None
    aliases: tuple[str, ...]


@lru_cache(maxsize=1)
def load_aliases(path: str | None = None) -> dict[tuple[str, str], AliasEntry]:
    """``(state, normalized name) -> entry``, for every canonical name and every alias.

    The canonical name maps to itself, so a table entry never has to repeat it.
    """
    import yaml

    source = Path(path) if path else ALIAS_FILE
    if not source.exists():
        return {}
    rows = yaml.safe_load(source.read_text(encoding="utf-8")) or []
    table: dict[tuple[str, str], AliasEntry] = {}
    for row in rows:
        state = str(row["state"]).strip().upper()
        entry = AliasEntry(
            canonical=str(row["canonical"]).strip(),
            state=state,
            entity_type=row.get("entity_type"),
            ein=row.get("ein"),
            aliases=tuple(row.get("aliases") or ()),
        )
        for name in (entry.canonical, *entry.aliases):
            key = normalize_name(name)
            if key:
                table[(state, key)] = entry
    return table


def cluster_key(name: str | None, state: str, aliases: dict[tuple[str, str], AliasEntry]) -> str:
    """The cluster a raw ``passthrough_name`` belongs to, within one state.

    The alias table first, then the normalized name itself. Nothing else: an initialism is
    only ever expanded through the table, because the same three letters name a different
    agency in another state and a wrong merge asserts a fact that is not true.
    """
    normalized = normalize_name(name)
    if not normalized:
        return ""
    entry = aliases.get((state.upper(), normalized))
    return normalize_name(entry.canonical) if entry else normalized


def _token_set_ratio(left: str, right: str) -> float:
    """Similarity on token sets, so word order and repetition do not matter."""
    a, b = set(left.split()), set(right.split())
    if not a or not b:
        return 0.0
    return 100.0 * len(a & b) / len(a | b)


def fuzzy_merge(keys: list[str], threshold: int = FUZZY_THRESHOLD) -> dict[str, str]:
    """``key -> surviving key`` for keys similar enough to merge. Off unless asked for.

    Deterministic: candidates are considered longest-first so the more specific name wins,
    and every merge is reported by the caller rather than applied silently.
    """
    survivors: list[str] = []
    mapping: dict[str, str] = {}
    for key in sorted(keys, key=lambda k: (-len(k), k)):
        match = next(
            (s for s in survivors if _token_set_ratio(key, s) >= threshold),
            None,
        )
        if match is None:
            survivors.append(key)
            mapping[key] = key
        else:
            mapping[key] = match
    return mapping


@dataclass
class NameVariant:
    raw: str
    count: int
    example_report_id: str


@dataclass
class Subrecipient:
    name: str | None
    city: str | None
    ein: str | None
    amount_expended: int


@dataclass
class Intermediary:
    """One clustered pass-through entity, from the demand side."""

    canonical_name: str
    cluster_key: str
    state: str
    subrecipient_count: int  # distinct auditee EIN: an organization audited five years is one
    observation_count: int  # distinct audits, which is the raw evidence count
    amount_expended_total: int
    programs: list[tuple[str, int]]
    name_variants: list[NameVariant]
    subrecipients: list[Subrecipient]
    entity_type: str | None = None
    ein: str | None = None
    uei: str | None = None
    city: str | None = None
    identifier_source: str = "none"
    from_alias_table: bool = False
    merged_by_fuzzy: list[str] = field(default_factory=list)


@dataclass
class Supplier:
    """One organization in this state whose own audit says it passed money down."""

    name: str | None
    ein: str | None
    uei: str | None
    city: str | None
    entity_type: str | None
    passthrough_amount_total: int
    amount_expended_total: int
    programs: list[tuple[str, int]]
    audit_years: list[str]
    cluster_key: str


@dataclass
class PassthroughResult:
    state: str
    program: str | None
    intermediaries: list[Intermediary]
    suppliers: list[Supplier]
    coverage: PassthroughCoverage

    def as_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)


def _programs(listings: Counter[str]) -> list[tuple[str, int]]:
    return sorted(listings.items(), key=lambda kv: (-kv[1], kv[0]))


def build_suppliers(
    audits: list[Audit],
    awards: list[SefaAward],
) -> list[Supplier]:
    """The supply side: entities whose own audit reports passing money down."""
    by_report = {a.report_id: a for a in audits}
    grouped: dict[str, list[SefaAward]] = defaultdict(list)
    for award in awards:
        if award.passed_money_down and award.report_id in by_report:
            grouped[award.report_id].append(award)

    merged: dict[str, Supplier] = {}
    for report_id, lines in grouped.items():
        audit = by_report[report_id]
        key = normalize_name(audit.auditee_name)
        listings = Counter(a.listing for a in lines if a.listing)
        passed = sum(a.passthrough_amount or 0 for a in lines)
        spent = sum(a.amount_expended or 0 for a in lines)
        existing = merged.get(key)
        if existing is None:
            merged[key] = Supplier(
                name=audit.auditee_name,
                ein=audit.auditee_ein,
                uei=audit.auditee_uei,
                city=audit.auditee_city,
                entity_type=audit.entity_type,
                passthrough_amount_total=passed,
                amount_expended_total=spent,
                programs=_programs(listings),
                audit_years=[audit.audit_year] if audit.audit_year else [],
                cluster_key=key,
            )
        else:
            existing.passthrough_amount_total += passed
            existing.amount_expended_total += spent
            existing.programs = _programs(
                Counter(dict(existing.programs)) + listings  # type: ignore[arg-type]
            )
            if audit.audit_year and audit.audit_year not in existing.audit_years:
                existing.audit_years.append(audit.audit_year)
    for s in merged.values():
        s.audit_years.sort()
    return sorted(
        merged.values(),
        key=lambda s: (-s.passthrough_amount_total, s.name or ""),
    )


def build_intermediaries(
    audits: list[Audit],
    indirect_awards: list[SefaAward],
    passthroughs: list[PassThrough],
    *,
    state: str,
    fuzzy: bool = False,
    alias_path: str | None = None,
) -> tuple[list[Intermediary], int]:
    """The demand side. Returns the clusters and the count of unattributed indirect lines.

    An indirect award line with no matching ``/passthrough`` row is a reporting gap in the
    filing, not an error here. It is counted and reported, never dropped and never guessed
    at.
    """
    aliases = load_aliases(alias_path)
    by_report = {a.report_id: a for a in audits}
    named = {p.key: p for p in passthroughs}

    unattributed = 0
    rows: list[tuple[str, SefaAward, PassThrough, Audit]] = []
    for award in indirect_awards:
        audit = by_report.get(award.report_id)
        if audit is None:
            continue
        entity = named.get(award.key)
        if entity is None or not entity.name:
            unattributed += 1
            continue
        key = cluster_key(entity.name, state, aliases)
        if not key:
            unattributed += 1
            continue
        rows.append((key, award, entity, audit))

    if fuzzy:
        mapping = fuzzy_merge(sorted({k for k, _, _, _ in rows}))
        rows = [(mapping[k], a, p, au) for k, a, p, au in rows]
        merged_into: dict[str, list[str]] = defaultdict(list)
        for original, survivor in mapping.items():
            if original != survivor:
                merged_into[survivor].append(original)
    else:
        merged_into = defaultdict(list)

    grouped: dict[str, list[tuple[SefaAward, PassThrough, Audit]]] = defaultdict(list)
    for key, award, entity, audit in rows:
        grouped[key].append((award, entity, audit))

    out: list[Intermediary] = []
    for key, group in grouped.items():
        alias = aliases.get((state.upper(), key))
        variants: Counter[str] = Counter()
        variant_example: dict[str, str] = {}
        listings: Counter[str] = Counter()
        by_org: dict[str, Subrecipient] = {}
        audit_ids: set[str] = set()
        total = 0
        for award, entity, audit in group:
            raw = entity.name or ""
            variants[raw] += 1
            variant_example.setdefault(raw, audit.report_id)
            listing = award.listing or assistance_listing(
                award.federal_agency_prefix, award.federal_award_extension
            )
            if listing:
                listings[listing] += 1
            amount = award.amount_expended or 0
            total += amount
            audit_ids.add(audit.report_id)
            # One organization audited five years running is one subrecipient, not five.
            org_key = audit.auditee_ein or normalize_name(audit.auditee_name) or audit.report_id
            row = by_org.get(org_key)
            if row is None:
                by_org[org_key] = Subrecipient(
                    name=audit.auditee_name,
                    city=audit.auditee_city,
                    ein=audit.auditee_ein,
                    amount_expended=amount,
                )
            else:
                row.amount_expended += amount

        canonical = alias.canonical if alias else _display_name(variants)
        out.append(
            Intermediary(
                canonical_name=canonical,
                cluster_key=key,
                state=state.upper(),
                subrecipient_count=len(by_org),
                observation_count=len(audit_ids),
                amount_expended_total=total,
                programs=_programs(listings),
                name_variants=[
                    NameVariant(raw=r, count=n, example_report_id=variant_example[r])
                    for r, n in variants.most_common()
                ],
                subrecipients=sorted(
                    by_org.values(), key=lambda s: (-s.amount_expended, s.name or "")
                ),
                entity_type=alias.entity_type if alias else None,
                ein=alias.ein if alias else None,
                identifier_source="alias_table" if alias and alias.ein else "none",
                from_alias_table=alias is not None,
                merged_by_fuzzy=sorted(merged_into.get(key, [])),
            )
        )

    # Rank by subrecipient count, then dollars. Deliberate: dollars name the biggest
    # intermediary, but subrecipient count names the one that actually makes subawards to
    # organizations like the client, and that is the question being asked.
    out.sort(key=lambda i: (-i.subrecipient_count, -i.amount_expended_total, i.canonical_name))
    return out, unattributed


def _display_name(variants: Counter[str]) -> str:
    """The spelling most auditors used, ties broken by spelling so output is stable."""
    if not variants:
        return ""
    best = max(variants.values())
    return sorted(n for n, c in variants.items() if c == best)[0]


def attach_identifiers(
    intermediaries: list[Intermediary],
    suppliers: list[Supplier],
) -> None:
    """Give demand-side clusters an EIN where the supply side names the same organization.

    Both sides are already confined to one state, so this cannot merge across states. It
    records ``identifier_source`` either way: a name agreeing with a name is a name match,
    and calling it an identity match would be the lie this whole module is arranged to
    avoid.
    """
    by_key = {s.cluster_key: s for s in suppliers if s.cluster_key}
    for entity in intermediaries:
        if entity.ein:
            continue
        supplier = by_key.get(entity.cluster_key)
        if supplier is None or not supplier.ein:
            continue
        entity.ein = supplier.ein
        entity.uei = supplier.uei
        entity.city = entity.city or supplier.city
        entity.entity_type = entity.entity_type or supplier.entity_type
        entity.identifier_source = "supply_side_match"


def build_passthrough(
    *,
    state: str,
    program: str | None,
    audits: list[Audit],
    indirect_awards: list[SefaAward],
    passthroughs: list[PassThrough],
    supply_awards: list[SefaAward],
    retrieved: datetime | None,
    requested_since_year: int | None = None,
    fuzzy: bool = False,
    alias_path: str | None = None,
) -> PassthroughResult:
    """Both streams, clustered, merged for display, with the coverage object attached."""
    state = state.strip().upper()
    intermediaries, unattributed = build_intermediaries(
        audits,
        indirect_awards,
        passthroughs,
        state=state,
        fuzzy=fuzzy,
        alias_path=alias_path,
    )
    suppliers = build_suppliers(audits, supply_awards)
    attach_identifiers(intermediaries, suppliers)
    years = sorted({int(a.audit_year) for a in audits if a.audit_year and a.audit_year.isdigit()})
    return PassthroughResult(
        state=state,
        program=program,
        intermediaries=intermediaries,
        suppliers=suppliers,
        coverage=build_coverage(
            state=state,
            audits_scanned=len(audits),
            audit_years=years,
            unattributed_indirect_lines=unattributed,
            retrieved=retrieved,
            requested_since_year=requested_since_year,
        ),
    )
