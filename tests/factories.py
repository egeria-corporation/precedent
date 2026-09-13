"""Builders shared by more than one test module.

They live here rather than in whichever test happened to define them first, so importing
one test module from another is never the mechanism. That import also only works when the
repository root is on ``sys.path``, which is true under ``python -m pytest`` and false
under ``uv run pytest`` - so it passes locally and fails in continuous integration.
"""

from __future__ import annotations

from precedent.sources.fac import Audit, PassThrough, SefaAward


def audit(
    rid: str,
    *,
    ein: str = "111",
    name: str = "Small Nonprofit",
    year: str = "2023",
    city: str = "Columbus",
    state: str = "OH",
    entity_type: str = "nonprofit",
    uei: str | None = None,
) -> Audit:
    return Audit(
        report_id=rid,
        audit_year=year,
        auditee_name=name,
        auditee_ein=ein,
        auditee_uei=uei,
        auditee_city=city,
        auditee_state=state,
        entity_type=entity_type,
        total_amount_expended=900_000,
        fy_start_date=None,
        fy_end_date=None,
        fac_accepted_date=None,
    )


def sefa(
    rid: str,
    ref: str = "AWARD-1",
    *,
    amount: int = 100_000,
    direct: str = "N",
    passthru: str = "N",
    passthru_amount: int | None = None,
    prefix: str = "93",
    ext: str = "045",
) -> SefaAward:
    return SefaAward(
        report_id=rid,
        award_reference=ref,
        federal_agency_prefix=prefix,
        federal_award_extension=ext,
        federal_program_name="Aging",
        amount_expended=amount,
        is_direct=direct == "Y",
        is_passthrough_award=passthru == "Y",
        passthrough_amount=passthru_amount,
        cluster_name="AGING CLUSTER",
        federal_program_total=amount,
        is_major=False,
        is_loan=False,
        findings_count=0,
        additional_award_identification=None,
        audit_year="2023",
        auditee_uei=None,
    )


def named(rid: str, ref: str, name: str, ident: str | None = None) -> PassThrough:
    return PassThrough(
        report_id=rid,
        award_reference=ref,
        name=name,
        identifier=ident,
        audit_year="2023",
        auditee_uei=None,
    )
