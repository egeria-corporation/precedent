"""One organization across two datasets that identify organizations differently."""

from __future__ import annotations

import pytest
from factories import audit, named, sefa

from precedent.analysis.recipient import (
    build_recipient_profile,
    classify_identifier,
    normalize_ein,
    summarize_funders,
)
from precedent.sources.fac import UEI_PLACEHOLDER, to_audit, to_passthrough, to_sefa_award


class TestClassifyIdentifier:
    @pytest.mark.parametrize(
        ("raw", "kind"),
        [
            ("JE73CDQUAPA7", "uei"),
            ("54-1939556", "ein"),
            ("541939556", "ein"),
            ("Feeding Southwest Virginia", "name"),
            ("12345", "name"),
            ("", "name"),
        ],
    )
    def test_the_identifier_decides_which_source_can_be_asked(self, raw: str, kind: str) -> None:
        # USAspending has no EIN field and FAC is the only bridge between the two, so this
        # is not cosmetic: it decides whether an answer is reachable at all.
        assert classify_identifier(raw) == kind

    def test_a_uei_never_contains_i_or_o(self) -> None:
        # SAM.gov excludes them so they cannot be confused with 1 and 0. A twelve-character
        # string containing one is a name, not an identifier.
        assert classify_identifier("JE73CDQIAPA7") == "name"
        assert classify_identifier("JE73CDQOAPA7") == "name"

    def test_an_ein_keeps_its_digits_and_loses_its_punctuation(self) -> None:
        assert normalize_ein("54-1939556") == "541939556"
        assert normalize_ein("54 1939556") == "541939556"


class TestMigrationPlaceholder:
    def test_the_placeholder_is_not_read_as_an_identifier(self) -> None:
        # auditee_uei holds the literal string GSA_MIGRATION on records carried over from
        # the legacy Census collection - 36,989 of 36,991 audits in 2016. Kept as a value it
        # joins tens of thousands of unrelated organizations to one another.
        migrated = to_audit({"report_id": "r", "auditee_uei": UEI_PLACEHOLDER})
        assert migrated.auditee_uei is None
        real = to_audit({"report_id": "r", "auditee_uei": "KNY3ET8DBBB8"})
        assert real.auditee_uei == "KNY3ET8DBBB8"

    def test_the_same_holds_on_award_and_passthrough_rows(self) -> None:
        assert to_sefa_award({"report_id": "r", "auditee_uei": UEI_PLACEHOLDER}).auditee_uei is None
        assert (
            to_passthrough({"report_id": "r", "auditee_uei": UEI_PLACEHOLDER}).auditee_uei is None
        )

    def test_a_uei_search_that_finds_nothing_explains_the_blind_spot(self) -> None:
        p = build_recipient_profile(
            query="KNY3ET8DBBB8",
            identifier_kind="uei",
            awards=[],
            audits=[],
            sefa_awards=[],
            passthroughs=[],
            fac_available=True,
        )
        assert any("Employer Identification Number reaches further back" in c for c in p.caveats)


class TestFunderClustering:
    def test_one_agency_typed_two_ways_is_one_funder(self) -> None:
        # Auditors retype the same agency year to year. Grouping on the raw string lists it
        # twice and splits its money between the spellings.
        indirect = [sefa("r1", "A1", amount=100), sefa("r2", "A1", amount=50)]
        rows = [
            named("r1", "A1", "VIRGINIA DEPARTMENT OF AGRICULTURE AND CONSUMER SERVICES"),
            named("r2", "A1", "Virginia Department of Agriculture and Consumer Services"),
        ]
        funders = summarize_funders(indirect, rows)
        assert len(funders) == 1
        assert funders[0][1] == 150, "the totals add rather than split"

    def test_the_label_is_the_spelling_used_most_often(self) -> None:
        indirect = [sefa(f"r{i}", "A1", amount=10) for i in range(3)]
        rows = [
            named("r0", "A1", "CITY OF ROANOKE"),
            named("r1", "A1", "CITY OF ROANOKE"),
            named("r2", "A1", "City of Roanoke"),
        ]
        assert summarize_funders(indirect, rows)[0][0] == "CITY OF ROANOKE"

    def test_an_indirect_line_naming_nobody_contributes_nothing(self) -> None:
        assert summarize_funders([sefa("r1", "A1")], []) == []


class TestProfileHonesty:
    def profile(self, **kw):
        base = dict(
            query="q",
            identifier_kind="ein",
            awards=[],
            audits=[],
            sefa_awards=[],
            passthroughs=[],
            fac_available=True,
        )
        return build_recipient_profile(**{**base, **kw})

    def test_no_key_says_which_questions_went_unanswered(self) -> None:
        p = self.profile(fac_available=False)
        assert any("cannot say what this organization spends" in c for c in p.caveats)
        assert p.sources == []

    def test_no_audit_is_not_evidence_of_a_small_organization(self) -> None:
        # Below the threshold an organization files nothing, so absence is absence.
        p = self.profile()
        assert any("not evidence that the" in c for c in p.caveats)

    def test_a_name_search_admits_it_may_have_merged_organizations(self) -> None:
        p = self.profile(identifier_kind="name")
        assert any("matches a name loosely" in c for c in p.caveats)

    def test_no_direct_awards_beside_named_funders_is_the_finding_not_a_gap(self) -> None:
        # The bridge worked and USAspending simply has nothing: this organization is funded
        # through intermediaries. Reporting that as a gap would bury the answer.
        found = audit("r1", ein="541939556", name="Feeding Southwest Virginia", uei="KNY3ET8DBBB8")
        p = self.profile(audits=[found])
        assert any("funded through intermediaries" in c for c in p.caveats)
        assert p.resolved_uei == "KNY3ET8DBBB8"

    def test_a_failed_bridge_says_the_lookup_never_happened(self) -> None:
        p = self.profile(audits=[audit("r1", ein="541939556", uei=None)])
        assert any("could not be checked at all" in c for c in p.caveats)

    def test_two_ueis_in_one_answer_means_two_organizations(self) -> None:
        from precedent.sources.usaspending import Award

        def award(uei: str) -> Award:
            return Award(
                generated_internal_id=uei,
                award_id=uei,
                recipient_name="ACME",
                recipient_uei=uei,
                recipient_id=None,
                amount=1000.0,
                base_obligation_date="2022-01-01",
                start_date=None,
                end_date=None,
                awarding_agency="HHS",
                awarding_sub_agency=None,
                place_of_performance_state="OH",
                recipient_state="OH",
                assistance_listings=["93.243"],
            )

        p = self.profile(
            identifier_kind="name", awards=[award("AAAAAAAAAAAA"), award("BBBBBBBBBBBB")]
        )
        assert any("more than one organization" in c for c in p.caveats)
