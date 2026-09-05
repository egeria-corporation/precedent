"""Identity resolution, tested directly because the headline statistics rest on it."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from precedent.analysis.identity import (
    Identity,
    name_tier_is_high,
    normalize_name,
    resolution_mix,
    resolve,
    strip_level_suffix,
)


@dataclass
class Record:
    recipient_uei: str | None = None
    recipient_id: str | None = None
    recipient_name: str | None = None


class TestNormalizeName:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Acme Services, Inc.", "ACME SERVICES"),
            ("ACME SERVICES INC LLC", "ACME SERVICES"),
            ("The Ohio State University", "OHIO STATE UNIVERSITY"),
            ("Smith & Jones Co", "SMITH AND JONES"),
            ("  spaced   out  ", "SPACED OUT"),
            ("Café Society", "CAFE SOCIETY"),
            ("St. Louis Dept of Health", "STATE LOUIS DEPARTMENT OF HEALTH"),
            ("Franklin Cnty Bd of Commissioners", "FRANKLIN COUNTY BD OF COMMISSIONERS"),
            ("Univ of Toledo", "UNIVERSITY OF TOLEDO"),
            ("Natl Assn of Counties", "NATIONAL ASSOCIATION OF COUNTIES"),
            ("Area AAA 3", "AREA AREA AGENCY ON AGING 3"),
            ("", ""),
            (None, ""),
            ("!!!", ""),
        ],
    )
    def test_names_reduce_to_a_comparable_form(self, raw: str | None, expected: str) -> None:
        assert normalize_name(raw) == expected

    def test_abbreviations_expand_as_whole_tokens_only(self) -> None:
        # Substring replacement would mangle these; the expansion table is token-scoped.
        assert normalize_name("Costa Mesa Center") == "COSTA MESA CENTER"
        assert normalize_name("Association House") == "ASSOCIATION HOUSE"
        assert normalize_name("Ctr for Employment") == "CENTER FOR EMPLOYMENT"

    def test_st_expands_only_in_first_position(self) -> None:
        # "ST" leading a filer name means the state; anywhere else it is usually a saint
        # or a street, and expanding it would merge organizations that are not the same.
        assert normalize_name("St Dept of Health") == "STATE DEPARTMENT OF HEALTH"
        assert normalize_name("Hospital of St Francis") == "HOSPITAL OF ST FRANCIS"

    def test_two_spellings_of_one_organization_agree(self) -> None:
        assert normalize_name("The Smith & Jones Company, Inc.") == normalize_name(
            "Smith and Jones"
        )


class TestLevelSuffix:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("abc-def-C", "abc-def"),
            ("abc-def-R", "abc-def"),
            ("abc-def-P", "abc-def"),
            ("abc-def-c", "abc-def"),
            ("abc-def", "abc-def"),
            ("", None),
            (None, None),
        ],
    )
    def test_the_level_marker_is_stripped(self, raw: str | None, expected: str | None) -> None:
        assert strip_level_suffix(raw) == expected

    def test_one_organization_at_three_levels_is_one_organization(self) -> None:
        keys = {resolve(Record(recipient_id=f"1f8c-{level}")).key for level in ("C", "R", "P")}
        assert len(keys) == 1, "keeping the suffix would split one grantee into three"


class TestResolutionOrder:
    def test_uei_wins_when_it_is_present_and_well_formed(self) -> None:
        got = resolve(
            Record(recipient_uei="nvwkavb8jnd6", recipient_id="x-C", recipient_name="Acme")
        )
        assert got == Identity("uei", "NVWKAVB8JND6")

    def test_a_malformed_uei_falls_through_rather_than_being_trusted(self) -> None:
        got = resolve(Record(recipient_uei="TOOSHORT", recipient_id="x-C", recipient_name="Acme"))
        assert got == Identity("recipient_id", "x")

    def test_name_is_the_last_resort(self) -> None:
        assert resolve(Record(recipient_name="Acme, Inc.")) == Identity("name", "ACME")

    def test_a_record_with_nothing_usable_resolves_to_nothing(self) -> None:
        assert resolve(Record()) is None
        assert resolve(Record(recipient_uei="   ", recipient_name="!!!")) is None


class TestResolutionMix:
    def test_the_mix_reports_how_much_the_counts_can_bear(self) -> None:
        identities = [Identity("uei", "A")] * 94 + [Identity("recipient_id", "B")] * 4
        identities += [Identity("name", "C")] * 2
        mix = resolution_mix(identities)
        assert mix == {"uei": 0.94, "recipient_id": 0.04, "name": 0.02}
        assert sum(mix.values()) == pytest.approx(1.0)

    def test_unresolved_records_are_counted_not_hidden(self) -> None:
        mix = resolution_mix([Identity("uei", "A"), None])
        assert mix == {"uei": 0.5, "unresolved": 0.5}

    def test_an_empty_set_has_no_mix(self) -> None:
        assert resolution_mix([]) == {}

    def test_heavy_name_matching_earns_a_caveat(self) -> None:
        assert name_tier_is_high({"uei": 0.8, "name": 0.2}) is True
        assert name_tier_is_high({"uei": 0.95, "name": 0.05}) is False
        assert name_tier_is_high({"name": 0.10}) is False, "the threshold is exclusive"
