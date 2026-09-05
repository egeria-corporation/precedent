"""Award-history statistics, with values pinned.

Any change to a computed number here must be a deliberate, reviewed change, so these
assertions are exact rather than approximate wherever the arithmetic allows it.
"""

from __future__ import annotations

import json
import statistics
from datetime import date
from pathlib import Path

import pytest

from precedent.analysis.profile import (
    BUCKETS,
    award_fiscal_year,
    build_profile,
    fiscal_year,
    size_stats,
)
from precedent.sources.usaspending import Award, to_award

FIXTURES = Path(__file__).parent / "fixtures"


def award(
    key: str,
    *,
    amount: float | None = 100_000,
    base: str | None = "2021-03-01",
    uei: str | None = None,
    name: str | None = None,
    state: str | None = "OH",
    listings: list[str] | None = None,
    start: str | None = None,
) -> Award:
    return Award(
        generated_internal_id=key,
        award_id=key,
        recipient_name=name or f"ORG {key}",
        recipient_uei=uei,
        recipient_id=None,
        amount=amount,
        base_obligation_date=base,
        start_date=start,
        end_date=None,
        awarding_agency="HHS",
        awarding_sub_agency=None,
        place_of_performance_state=state,
        recipient_state=state,
        assistance_listings=listings or ["93.243"],
    )


class TestFiscalYear:
    @pytest.mark.parametrize(
        ("day", "expected"),
        [
            (date(2020, 9, 30), 2020),
            (date(2020, 10, 1), 2021),
            (date(2021, 1, 15), 2021),
            (date(2021, 9, 30), 2021),
        ],
    )
    def test_october_starts_the_next_fiscal_year(self, day: date, expected: int) -> None:
        assert fiscal_year(day) == expected

    def test_the_cohort_year_prefers_the_first_obligating_action(self) -> None:
        a = award("x", base="2018-09-27", start="2021-01-01")
        assert award_fiscal_year(a) == 2018, "not the year we happened to fetch it in"

    def test_a_missing_base_date_falls_back_to_the_start_date(self) -> None:
        assert award_fiscal_year(award("x", base=None, start="2021-01-01")) == 2021

    def test_an_award_with_no_usable_date_has_no_year(self) -> None:
        assert award_fiscal_year(award("x", base=None, start=None)) is None
        assert award_fiscal_year(award("x", base="not-a-date", start=None)) is None


class TestSizeStats:
    def test_p50_equals_the_median_to_within_a_cent(self) -> None:
        # Required by the spec: the two must not disagree, on odd or even counts.
        for amounts in ([1.0, 2.0, 3.0], [1.0, 2.0, 3.0, 4.0], [10.0, 3.0, 7.0, 1.0, 99.0]):
            s = size_stats(amounts)
            assert abs(s.percentiles["p50"] - s.median) < 0.01

    def test_percentiles_are_inclusive_not_the_library_default(self) -> None:
        amounts = [float(x) for x in range(1, 11)]
        s = size_stats(amounts)
        inclusive = statistics.quantiles(amounts, n=100, method="inclusive")
        assert s.percentiles["p90"] == inclusive[89]
        assert s.percentiles["p90"] != statistics.quantiles(amounts, n=100)[89]

    def test_bucket_shares_sum_to_one(self) -> None:
        amounts = [50_000.0, 150_000.0, 300_000.0, 750_000.0, 2_000_000.0, 9_000_000.0, 99.0]
        s = size_stats(amounts)
        assert sum(b.share_of_awards for b in s.buckets) == pytest.approx(1.0)
        assert sum(b.share_of_dollars for b in s.buckets) == pytest.approx(1.0)
        assert sum(b.count for b in s.buckets) == len(amounts)

    def test_buckets_are_half_open_so_a_boundary_lands_once(self) -> None:
        s = size_stats([100_000.0])
        placed = [b.name for b in s.buckets if b.count]
        assert placed == ["100k_250k"], "100,000 belongs to [100k, 250k), not to [0, 100k)"
        assert next(name for name, _lo, _hi in BUCKETS) == "under_100k"

    def test_a_skewed_mean_is_labelled(self) -> None:
        assert size_stats([1.0, 1.0, 1.0, 100.0]).mean_is_skewed is True
        assert size_stats([10.0, 11.0, 12.0]).mean_is_skewed is False

    def test_no_amounts_produces_empty_statistics_not_a_crash(self) -> None:
        s = size_stats([])
        assert s.count == 0 and s.median is None and s.buckets == []

    def test_a_single_award_still_reports_percentiles(self) -> None:
        s = size_stats([250_000.0])
        assert s.median == 250_000.0
        assert s.percentiles["p10"] == s.percentiles["p90"] == 250_000.0


class TestNewEntrantRate:
    def profile(self, awards, **kw):
        return build_profile(
            awards, program="93.243", since_fy=2020, until_fy=2024, lookback_years=5, **kw
        )

    def test_a_recipient_present_in_the_lookback_is_not_a_new_entrant(self) -> None:
        returning = award("w1", base="2021-01-01", uei="AAAAAAAAAAAA")
        earlier = award("l1", base="2017-01-01", uei="AAAAAAAAAAAA")
        fresh = award("w2", base="2021-01-01", uei="BBBBBBBBBBBB")
        p = self.profile([returning, earlier, fresh])
        assert p.recipient_count == 2
        assert p.new_entrant_count == 1, "only the UEI absent from the lookback is new"
        assert p.new_entrant_rate == 0.5
        assert p.lookback_award_count == 1

    def test_the_lookback_window_is_the_five_years_before_the_window(self) -> None:
        p = self.profile([award("w", base="2021-01-01")])
        assert (p.lookback_since_fy, p.since_fy, p.until_fy) == (2015, 2020, 2024)

    def test_an_empty_lookback_makes_the_rate_an_upper_bound(self) -> None:
        p = self.profile([award("w", base="2021-01-01")])
        assert p.new_entrant_rate == 1.0
        assert p.new_entrant_rate_is_upper_bound is True
        assert any("did not exist yet" in c for c in p.caveats)

    def test_a_lookback_crossing_the_coverage_floor_is_flagged(self) -> None:
        # FY2008 lookback starts 2007-10-01, which is exactly the floor: not truncated.
        ok = build_profile(
            [award("w", base="2013-01-01")],
            program="x",
            since_fy=2013,
            until_fy=2014,
            lookback_years=5,
        )
        assert not any("as far back as this search covers" in c for c in ok.caveats)
        crossing = build_profile(
            [award("w", base="2011-01-01")],
            program="x",
            since_fy=2011,
            until_fy=2012,
            lookback_years=5,
        )
        assert crossing.new_entrant_rate_is_upper_bound is True
        assert any("as far back as this search covers" in c for c in crossing.caveats)


class TestRepeatWinnersAndConcentration:
    def profile(self, awards):
        return build_profile(awards, program="93.243", since_fy=2020, until_fy=2024)

    def test_two_awards_in_the_window_make_a_repeat_winner(self) -> None:
        p = self.profile(
            [
                award("a", uei="AAAAAAAAAAAA"),
                award("b", uei="AAAAAAAAAAAA"),
                award("c", uei="BBBBBBBBBBBB"),
            ]
        )
        assert p.repeat_winner_count == 1
        assert p.repeat_winner_rate == 0.5

    def test_the_same_award_twice_is_not_a_repeat_winner(self) -> None:
        # Deduplication is on the award key, so one award seen twice stays one award.
        same = award("a", uei="AAAAAAAAAAAA")
        p = self.profile([same, same])
        assert p.window_award_count == 2, "the caller deduplicates; the profile counts rows"
        assert p.repeat_winner_count == 0, "both rows are the same generated_internal_id"

    def test_the_lookback_does_not_leak_into_the_repeat_rate(self) -> None:
        p = build_profile(
            [
                award("w", base="2021-01-01", uei="AAAAAAAAAAAA"),
                award("l", base="2017-01-01", uei="AAAAAAAAAAAA"),
            ],
            program="x",
            since_fy=2020,
            until_fy=2024,
        )
        assert p.repeat_winner_count == 0, "a within-window measure only"

    def test_concentration_is_the_top_ten_share_of_window_dollars(self) -> None:
        awards = [award(f"a{i}", amount=1000.0, uei=f"{i:012d}") for i in range(11)]
        awards.append(award("big", amount=989_000.0, uei="ZZZZZZZZZZZZ"))
        p = self.profile(awards)
        # 989,000 plus nine of the eleven 1,000s, over a 1,000,000 total.
        assert p.concentration_top10_share == pytest.approx(0.998)

    def test_no_dollars_means_no_concentration_rather_than_zero(self) -> None:
        p = self.profile([award("a", amount=0)])
        assert p.concentration_top10_share is None


class TestExclusionsAndCaveats:
    def test_a_zero_dollar_award_still_makes_its_recipient_a_recipient(self) -> None:
        p = build_profile(
            [award("a", amount=0, uei="AAAAAAAAAAAA")], program="x", since_fy=2020, until_fy=2024
        )
        assert p.recipient_count == 1, "winning a net-zero award still means they won"
        assert p.excluded.nonpositive_amount == 1
        assert p.sizes.count == 0, "but it is not an amount statistic"

    def test_an_undated_award_is_counted_out_loud(self) -> None:
        p = build_profile(
            [award("a", base=None, start=None), award("b")],
            program="x",
            since_fy=2020,
            until_fy=2024,
        )
        assert p.excluded.missing_date == 1
        assert p.window_award_count == 1
        assert any("no usable date" in c for c in p.caveats)

    def test_heavy_multi_listing_warns_that_amounts_are_an_upper_bound(self) -> None:
        awards = [award(f"m{i}", listings=["93.243", "93.788"]) for i in range(2)]
        awards.append(award("single"))
        p = build_profile(awards, program="93.243", since_fy=2020, until_fy=2024)
        assert p.multi_listing_share == pytest.approx(2 / 3)
        assert any("more than one Assistance Listing" in c for c in p.caveats)

    def test_name_only_matching_earns_its_caveat(self) -> None:
        p = build_profile(
            [award("a", name="Acme Inc"), award("b", name="Beta LLC")],
            program="x",
            since_fy=2020,
            until_fy=2024,
        )
        assert p.identity_resolution == {"name": 1.0}
        assert any("by name rather than" in c for c in p.caveats)


class TestTopLists:
    def test_the_display_name_is_the_one_a_consultant_would_recognize(self) -> None:
        p = build_profile(
            [
                award("a", uei="AAAAAAAAAAAA", name="County of Clackamas"),
                award("b", uei="AAAAAAAAAAAA", name="County of Clackamas"),
                award("c", uei="AAAAAAAAAAAA", name="CLACKAMAS CTY"),
            ],
            program="x",
            since_fy=2020,
            until_fy=2024,
        )
        top = p.top_recipients_by_count[0]
        assert top.display_name == "County of Clackamas", "most frequent raw name, not normalized"
        assert top.award_count == 3
        assert top.uei == "AAAAAAAAAAAA"

    def test_states_are_counted_and_ranked(self) -> None:
        p = build_profile(
            [award("a", state="OH"), award("b", state="OH"), award("c", state="KY")],
            program="x",
            since_fy=2020,
            until_fy=2024,
        )
        assert p.states_covered == 2
        assert p.top_states_by_count[0] == ("OH", 2)


class TestAgainstTheRealFixture:
    def test_the_captured_16842_awards_profile_cleanly(self) -> None:
        raw = json.loads((FIXTURES / "usaspending_search_16842.json").read_text(encoding="utf-8"))
        awards = [to_award(r) for r in raw["results"]]
        p = build_profile(awards, program="16.842", since_fy=2019, until_fy=2024)
        assert p.window_award_count + p.lookback_award_count == len(awards)
        assert p.identity_resolution.get("uei") == 1.0, "every real row carries a UEI"
        assert p.sizes.count >= 1
        assert p.sizes.median is not None
        assert abs(p.sizes.percentiles["p50"] - p.sizes.median) < 0.01
        assert sum(b.share_of_awards for b in p.sizes.buckets) == pytest.approx(1.0)
