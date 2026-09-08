"""Pass-through clustering, the two evidence streams, and the coverage that rides along.

The bias under test throughout: a wrongly merged entity asserts a fact that is not true,
a split entity merely undercounts, and this tool would rather undercount.
"""

from __future__ import annotations

from datetime import UTC, datetime

from precedent.analysis.coverage import THRESHOLD_NOTE, build_coverage
from precedent.analysis.passthrough import (
    FUZZY_THRESHOLD,
    build_intermediaries,
    build_passthrough,
    build_suppliers,
    cluster_key,
    fuzzy_merge,
    load_aliases,
)
from precedent.sources.fac import Audit, PassThrough, SefaAward

NOW = datetime(2026, 9, 8, tzinfo=UTC)


def audit(
    rid: str,
    *,
    ein: str = "111",
    name: str = "Small Nonprofit",
    year: str = "2023",
    city: str = "Columbus",
    state: str = "OH",
    entity_type: str = "nonprofit",
) -> Audit:
    return Audit(
        report_id=rid,
        audit_year=year,
        auditee_name=name,
        auditee_ein=ein,
        auditee_uei=None,
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


class TestClustering:
    def test_an_initialism_resolves_only_through_the_committed_table(self) -> None:
        # The same three letters name a different agency in another state. Expanding them
        # by any automatic rule would state a fact that is not true.
        aliases = load_aliases()
        assert cluster_key("ODA", "OH", aliases) == "OHIO DEPARTMENT OF AGING"
        assert cluster_key("ODA", "TX", aliases) == "ODA", "never expanded outside its state"

    def test_spellings_in_the_table_land_on_one_canonical_key(self) -> None:
        aliases = load_aliases()
        keys = {
            cluster_key(n, "OH", aliases)
            for n in ("Ohio Department of Aging", "OHIO DEPT OF AGING", "ohio department on aging")
        }
        assert keys == {"OHIO DEPARTMENT OF AGING"}

    def test_names_outside_the_table_cluster_by_exact_normalized_match_only(self) -> None:
        aliases = load_aliases()
        # Normalization handles case, punctuation and legal suffixes; nothing else merges.
        assert cluster_key("Acme Council, Inc.", "OH", aliases) == cluster_key(
            "ACME COUNCIL INC", "OH", aliases
        )
        assert cluster_key("Acme Council", "OH", aliases) != cluster_key(
            "Acme Councils", "OH", aliases
        ), "one letter apart stays apart without --fuzzy"

    def test_a_cluster_never_crosses_a_state(self) -> None:
        audits = [audit("r1", ein="1", state="OH"), audit("r2", ein="2", state="OH")]
        awards = [sefa("r1"), sefa("r2")]
        rows = [
            named("r1", "AWARD-1", "DEPARTMENT OF AGING"),
            named("r2", "AWARD-1", "DEPARTMENT OF AGING"),
        ]
        oh, _ = build_intermediaries(audits, awards, rows, state="OH")
        assert len(oh) == 1 and oh[0].subrecipient_count == 2
        # The same names asked for as Texas produce a Texas cluster, never a merged one.
        tx, _ = build_intermediaries(audits, awards, rows, state="TX")
        assert all(e.state == "TX" for e in tx)


class TestFuzzyIsOffAndLoud:
    def test_the_default_does_not_merge_near_matches(self) -> None:
        audits = [audit("r1", ein="1"), audit("r2", ein="2")]
        awards = [sefa("r1"), sefa("r2")]
        rows = [
            named("r1", "AWARD-1", "WESTERN RESERVE AREA AGENCY ON AGING"),
            named("r2", "AWARD-1", "WESTERN RESERVE AREA ON AGING"),
        ]
        clusters, _ = build_intermediaries(audits, awards, rows, state="OH")
        assert len(clusters) == 2, "an undercount is preferable to a false merge"

    def test_fuzzy_merges_and_names_what_it_merged(self) -> None:
        merged = fuzzy_merge(["AREA AGENCY ON AGING PSA 2", "PSA 2 AREA AGENCY ON AGING"])
        assert len(set(merged.values())) == 1, "token order does not make two organizations"
        audits = [audit("r1", ein="1"), audit("r2", ein="2")]
        awards = [sefa("r1"), sefa("r2")]
        rows = [
            named("r1", "AWARD-1", "AREA AGENCY ON AGING PSA 2"),
            named("r2", "AWARD-1", "PSA 2 AREA AGENCY ON AGING"),
        ]
        clusters, _ = build_intermediaries(audits, awards, rows, state="OH", fuzzy=True)
        assert len(clusters) == 1
        assert clusters[0].merged_by_fuzzy, "every merge is reported, never silent"

    def test_the_threshold_is_high_because_this_merges_organizations(self) -> None:
        assert FUZZY_THRESHOLD == 92
        assert fuzzy_merge(["ACME COUNCIL OF OHIO", "BETA COUNCIL OF IOWA"]) == {
            "ACME COUNCIL OF OHIO": "ACME COUNCIL OF OHIO",
            "BETA COUNCIL OF IOWA": "BETA COUNCIL OF IOWA",
        }


class TestCounting:
    def test_one_organization_audited_twice_is_one_subrecipient(self) -> None:
        # Otherwise an organization audited five years running looks like five grantees and
        # the intermediary looks five times as reachable as it is.
        audits = [audit("r1", ein="99", year="2022"), audit("r2", ein="99", year="2023")]
        awards = [sefa("r1"), sefa("r2")]
        rows = [
            named("r1", "AWARD-1", "OHIO DEPARTMENT OF AGING"),
            named("r2", "AWARD-1", "OHIO DEPARTMENT OF AGING"),
        ]
        clusters, _ = build_intermediaries(audits, awards, rows, state="OH")
        assert clusters[0].subrecipient_count == 1, "distinct organizations"
        assert clusters[0].observation_count == 2, "distinct audits, the raw evidence"

    def test_ranking_is_by_subrecipient_count_before_dollars(self) -> None:
        # Deliberate: dollars name the biggest intermediary, subrecipient count names the
        # one that actually makes subawards to organizations like the client.
        audits = [audit(f"r{i}", ein=str(i)) for i in range(1, 4)]
        awards = [sefa("r1", amount=10_000_000), sefa("r2", amount=1), sefa("r3", amount=1)]
        rows = [
            named("r1", "AWARD-1", "ONE BIG GRANT COUNCIL"),
            named("r2", "AWARD-1", "MANY SMALL GRANTS COUNCIL"),
            named("r3", "AWARD-1", "MANY SMALL GRANTS COUNCIL"),
        ]
        clusters, _ = build_intermediaries(audits, awards, rows, state="OH")
        assert clusters[0].canonical_name == "MANY SMALL GRANTS COUNCIL"
        assert clusters[0].amount_expended_total < clusters[1].amount_expended_total

    def test_an_indirect_line_naming_nobody_is_counted_not_dropped(self) -> None:
        # A reporting gap in somebody's filing. Attributing it to anyone would be a guess.
        audits = [audit("r1", ein="1"), audit("r2", ein="2")]
        awards = [sefa("r1"), sefa("r2")]
        rows = [named("r1", "AWARD-1", "OHIO DEPARTMENT OF AGING")]
        clusters, unattributed = build_intermediaries(audits, awards, rows, state="OH")
        assert unattributed == 1
        assert sum(c.subrecipient_count for c in clusters) == 1

    def test_a_blank_name_is_unattributed_rather_than_an_empty_cluster(self) -> None:
        audits = [audit("r1", ein="1")]
        clusters, unattributed = build_intermediaries(
            audits, [sefa("r1")], [named("r1", "AWARD-1", "   ")], state="OH"
        )
        assert clusters == [] and unattributed == 1


class TestSupplySide:
    def test_only_lines_that_passed_real_dollars_down_count(self) -> None:
        audits = [audit("r1", name="Ohio Department of Aging", ein="31-0000")]
        awards = [
            sefa("r1", "A1", passthru="Y", passthru_amount=500_000, amount=900_000),
            sefa("r1", "A2", passthru="Y", passthru_amount=0, amount=100_000),
            sefa("r1", "A3", passthru="N", amount=50_000),
        ]
        suppliers = build_suppliers(audits, awards)
        assert len(suppliers) == 1
        assert suppliers[0].passthrough_amount_total == 500_000
        assert suppliers[0].ein == "31-0000", "the filer's own audit, so a real identifier"

    def test_a_name_match_is_recorded_as_a_name_match(self) -> None:
        # The supply side has an EIN and the demand side does not. Borrowing it is useful
        # and must never be presented as though the two records were linked by identity.
        audits = [
            audit("r1", ein="1"),
            audit("r2", name="Buckeye Hills Regional Council", ein="31-0807186"),
        ]
        demand = build_intermediaries(
            [audits[0]],
            [sefa("r1")],
            [named("r1", "AWARD-1", "Buckeye Hills Regional Council")],
            state="OH",
        )[0]
        suppliers = build_suppliers(
            [audits[1]], [sefa("r2", "A1", passthru="Y", passthru_amount=1_000)]
        )
        result = build_passthrough(
            state="OH",
            program="93.045",
            audits=audits,
            indirect_awards=[sefa("r1")],
            passthroughs=[named("r1", "AWARD-1", "Buckeye Hills Regional Council")],
            supply_awards=[sefa("r2", "A1", passthru="Y", passthru_amount=1_000)],
            retrieved=NOW,
        )
        assert demand[0].ein is None, "the demand side alone never has one"
        assert suppliers[0].ein == "31-0807186"
        matched = result.intermediaries[0]
        assert matched.ein == "31-0807186"
        assert matched.identifier_source == "supply_side_match", "how it was matched, on the record"


class TestCoverageAlwaysRides:
    def test_the_threshold_note_is_verbatim_and_says_absent_not_zero(self) -> None:
        c = build_coverage(
            state="OH",
            audits_scanned=10,
            audit_years=[2022, 2023],
            unattributed_indirect_lines=0,
            retrieved=NOW,
        )
        assert c.threshold_note == THRESHOLD_NOTE
        assert "absent from this data entirely, not counted as zero" in c.threshold_note
        assert c.counts_are_floors is True
        assert c.threshold_old == 750_000 and c.threshold_new == 1_000_000

    def test_every_result_carries_it_and_no_flag_removes_it(self) -> None:
        result = build_passthrough(
            state="oh",
            program=None,
            audits=[],
            indirect_awards=[],
            passthroughs=[],
            supply_awards=[],
            retrieved=NOW,
        )
        assert result.coverage.threshold_note == THRESHOLD_NOTE
        assert result.as_dict()["coverage"]["counts_are_floors"] is True
        assert result.state == "OH", "normalized, so a cluster key cannot miss on case"

    def test_a_window_before_coverage_is_disclosed_not_silently_clamped(self) -> None:
        c = build_coverage(
            state="OH",
            audits_scanned=1,
            audit_years=[2016],
            unattributed_indirect_lines=0,
            retrieved=NOW,
            requested_since_year=2009,
        )
        assert any("clamped to 2016" in n for n in c.notes)

    def test_unattributed_lines_are_explained_in_the_coverage(self) -> None:
        c = build_coverage(
            state="OH",
            audits_scanned=5,
            audit_years=[2023],
            unattributed_indirect_lines=7,
            retrieved=NOW,
        )
        assert any("without naming one" in n for n in c.notes)
        assert c.unattributed_indirect_lines == 7

    def test_the_retrieval_date_comes_from_provenance_not_from_now(self) -> None:
        c = build_coverage(
            state="OH",
            audits_scanned=1,
            audit_years=[2023],
            unattributed_indirect_lines=0,
            retrieved=datetime(2026, 1, 2, tzinfo=UTC),
        )
        assert c.fac_retrieved == "2026-01-02"
