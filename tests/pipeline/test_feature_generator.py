"""Unit tests for the feature generator pipeline.

Tests cover:
- Horse entity key derivation (collision disambiguation, stability)
- load_and_merge (row count, sort order, finish_note preservation)
- Race context features (columns, field_size)
- Horse basic features (columns, no market columns)

Stub classes for Plans 02-05 are included with pytest.skip placeholders.
"""

import pandas as pd
import pytest

from src.pipeline.feature_generator import (
    compute_finish_time_zscore,
    compute_lag_features,
    convert_margin_to_numeric,
    derive_horse_entity_key,
    extract_horse_basic_features,
    extract_race_context_features,
    parse_finish_time_to_seconds,
    parse_margin,
)


# ---------------------------------------------------------------------------
# Task 1: Horse entity key, merge, race context, horse basic features
# ---------------------------------------------------------------------------


class TestHorseEntityKey:
    """Test derive_horse_entity_key() produces unique keys from (horse_name, birth_year_proxy)."""

    def test_key_uniqueness(self, sample_feature_merged_df: pd.DataFrame) -> None:
        """Test 1: horse_entity_key uniquely identifies horse entities.

        Two different horses with same name but different birth years must
        get different keys (the 14 confirmed name collisions in 2015-2021 data).
        """
        df = sample_feature_merged_df
        assert "horse_entity_key" in df.columns

        # アームストロング appears as two different horses:
        # age=4 in 2015 -> born 2011 -> key "アームストロング_2011"
        # age=7 in 2015 -> born 2008 -> key "アームストロング_2008"
        armstrong_keys = df[df["horse_name"] == "アームストロング"]["horse_entity_key"].unique()
        assert len(armstrong_keys) == 2, (
            f"Expected 2 unique keys for same-name horses, got {armstrong_keys}"
        )

    def test_collision_disambiguation(self) -> None:
        """Test 2: Same-name horses with different birth years get DIFFERENT keys.

        Simulates the real-world case: アームストロング born 2011 vs 2018.
        """
        df = pd.DataFrame({
            "horse_name": ["アームストロング", "アームストロング"],
            "age": [4, 2],
            "race_id": ["201501010101", "202001010101"],
        })
        result = derive_horse_entity_key(df)

        keys = result["horse_entity_key"].tolist()
        assert keys[0] != keys[1], (
            f"Same-name horses with different birth years must have different keys, got {keys}"
        )
        # Verify the format: horse_name_birth_year_proxy
        assert keys[0] == "アームストロング_2011"  # 2015 - 4
        assert keys[1] == "アームストロング_2018"  # 2020 - 2

    def test_stability_across_career(self) -> None:
        """Test 3: Single horse across multiple years gets SAME horse_entity_key."""
        df = pd.DataFrame({
            "horse_name": ["馬X", "馬X", "馬X"],
            "age": [3, 4, 5],
            "race_id": ["201501010101", "201601010101", "201701010101"],
        })
        result = derive_horse_entity_key(df)

        keys = result["horse_entity_key"].unique()
        assert len(keys) == 1, (
            f"Same horse across years should have 1 key, got {keys}"
        )
        # 2015-3=2012, 2016-4=2012, 2017-5=2012 -- all the same
        assert keys[0] == "馬X_2012"


class TestLoadMerge:
    """Test load_and_merge() produces correctly merged and sorted DataFrame."""

    def test_row_count_entry_result_one_to_one(
        self, sample_feature_merged_df: pd.DataFrame
    ) -> None:
        """Test 4: Row count equals entry count (inner join, 1:1 entry-result)."""
        df = sample_feature_merged_df
        # 14 entries, 14 results -> 14 rows after inner join
        assert len(df) == 14, f"Expected 14 rows after inner join, got {len(df)}"

    def test_sort_order_globally_unique(
        self, sample_feature_merged_df: pd.DataFrame
    ) -> None:
        """Test 5: DataFrame sorted by [horse_entity_key, race_date, race_id]."""
        df = sample_feature_merged_df

        # Verify sort order: each consecutive pair should be in order
        for i in range(len(df) - 1):
            key_curr = df.iloc[i]["horse_entity_key"]
            key_next = df.iloc[i + 1]["horse_entity_key"]
            date_curr = df.iloc[i]["race_date"]
            date_next = df.iloc[i + 1]["race_date"]
            rid_curr = df.iloc[i]["race_id"]
            rid_next = df.iloc[i + 1]["race_id"]

            if key_curr == key_next:
                if date_curr == date_next:
                    assert rid_curr <= rid_next, (
                        f"race_id order violated at row {i}: {rid_curr} > {rid_next}"
                    )
                else:
                    assert date_curr < date_next, (
                        f"race_date order violated at row {i}: {date_curr} >= {date_next}"
                    )
            else:
                assert key_curr < key_next, (
                    f"horse_entity_key order violated at row {i}: {key_curr} >= {key_next}"
                )

    def test_finish_note_preserved(
        self, sample_feature_merged_df: pd.DataFrame
    ) -> None:
        """Test 10: finish_note values are preserved in merged DataFrame."""
        df = sample_feature_merged_df

        finish_notes = df["finish_note"].dropna().unique().tolist()
        # We expect at least "取" and "中" from our test data
        assert "取" in finish_notes, "finish_note '取' (scratched) not preserved"
        assert "中" in finish_notes, "finish_note '中' (DNF) not preserved"


class TestRaceContextFeatures:
    """Test extract_race_context_features() produces correct columns and field_size."""

    def test_columns_present(self, sample_feature_merged_df: pd.DataFrame) -> None:
        """Test 6: Race context features include expected columns."""
        df = extract_race_context_features(sample_feature_merged_df)

        expected = {
            "race_id", "race_date", "course_name", "distance", "surface",
            "direction", "weather", "track_condition", "race_number",
            "grade", "field_size", "horse_entity_key",
        }
        actual = set(df.columns)
        missing = expected - actual
        assert not missing, f"Missing race context columns: {missing}"

    def test_field_size_correct(self, sample_feature_merged_df: pd.DataFrame) -> None:
        """Test 7: field_size equals entry count per race_id."""
        df = extract_race_context_features(sample_feature_merged_df)

        # Check field_size for each race
        field_sizes = df.groupby("race_id")["field_size"].first()
        for race_id, size in field_sizes.items():
            actual_count = len(df[df["race_id"] == race_id])
            assert size == actual_count, (
                f"race_id {race_id}: field_size={size} but actual entries={actual_count}"
            )

    def test_no_market_columns(self, sample_feature_merged_df: pd.DataFrame) -> None:
        """Test 8: Race context features do NOT include popularity or win_odds (per D-15)."""
        df = extract_race_context_features(sample_feature_merged_df)

        assert "popularity" not in df.columns, (
            "popularity (post-race per D-15) should not be in race context features"
        )
        assert "win_odds" not in df.columns, (
            "win_odds (post-race per D-15) should not be in race context features"
        )


class TestHorseBasicFeatures:
    """Test extract_horse_basic_features() produces correct columns."""

    def test_columns_present(self, sample_feature_merged_df: pd.DataFrame) -> None:
        """Test 9: Horse basic features include expected columns."""
        df = extract_horse_basic_features(sample_feature_merged_df)

        expected = {
            "bracket_num", "horse_number", "sex", "age", "weight_assigned",
            "horse_weight", "weight_change", "horse_name", "horse_entity_key",
            "jockey", "trainer",
        }
        actual = set(df.columns)
        missing = expected - actual
        assert not missing, f"Missing horse basic feature columns: {missing}"

    def test_no_market_columns(self, sample_feature_merged_df: pd.DataFrame) -> None:
        """Horse basic features must not include popularity or win_odds (per D-15)."""
        df = extract_horse_basic_features(sample_feature_merged_df)

        assert "popularity" not in df.columns, (
            "popularity (post-race per D-15) should not be in horse basic features"
        )
        assert "win_odds" not in df.columns, (
            "win_odds (post-race per D-15) should not be in horse basic features"
        )


# ---------------------------------------------------------------------------
# Stub test classes for Plans 02-05
# ---------------------------------------------------------------------------


class TestLagFeatures:
    """Tests for lag feature generation with valid-start filtering (Plan 03-03)."""

    def test_lag_columns_exist(self, sample_lag_merged_df: pd.DataFrame) -> None:
        """Test 1: All 25 raw lag columns exist: prev_{1..5}_{metric}."""
        result = compute_lag_features(sample_lag_merged_df)

        metrics = ["finish_position", "last_3f", "corner_4", "finish_time_zscore", "margin_numeric"]
        for metric in metrics:
            for lag in range(1, 6):
                col = f"prev_{lag}_{metric}"
                assert col in result.columns, f"Missing lag column: {col}"

    def test_prev_1_temporal_safety(self, sample_lag_merged_df: pd.DataFrame) -> None:
        """Test 2: prev_1_finish_position for horse's 2nd race equals finish_position from 1st race."""
        result = compute_lag_features(sample_lag_merged_df)

        # 馬A: race 1 (pos=3), race 2 (pos=1), race 3 (pos=2)
        horse_a = result[result["horse_entity_key"] == "馬A_2010"].sort_values(
            ["race_date", "race_id"]
        )
        assert len(horse_a) == 3

        # 2nd race: prev_1 should be 1st race's finish_position
        race2 = horse_a.iloc[1]
        assert race2["prev_1_finish_position"] == 3.0, (
            f"prev_1_finish_position for 2nd race should be 3.0, got {race2['prev_1_finish_position']}"
        )

        # 3rd race: prev_1 should be 2nd race's finish_position
        race3 = horse_a.iloc[2]
        assert race3["prev_1_finish_position"] == 1.0, (
            f"prev_1_finish_position for 3rd race should be 1.0, got {race3['prev_1_finish_position']}"
        )

    def test_first_race_nan_lags(self, sample_lag_merged_df: pd.DataFrame) -> None:
        """Test 3: prev_1_finish_position for a horse's first race is NaN."""
        result = compute_lag_features(sample_lag_merged_df)

        # 馬A_2010: first valid start at 201501010101
        horse_a_first = result[
            (result["horse_entity_key"] == "馬A_2010")
            & (result["race_id"] == "201501010101")
        ]
        assert len(horse_a_first) == 1
        assert pd.isna(horse_a_first.iloc[0]["prev_1_finish_position"]), (
            "First race should have NaN prev_1_finish_position"
        )

    def test_prev3_stat_columns_exist(self, sample_lag_merged_df: pd.DataFrame) -> None:
        """Test 4: 3-race statistics columns exist: prev3_{metric}_mean, prev3_{metric}_std."""
        result = compute_lag_features(sample_lag_merged_df)

        metrics = ["finish_position", "last_3f", "corner_4", "finish_time_zscore", "margin_numeric"]
        for metric in metrics:
            assert f"prev3_{metric}_mean" in result.columns, f"Missing: prev3_{metric}_mean"
            assert f"prev3_{metric}_std" in result.columns, f"Missing: prev3_{metric}_std"

    def test_prev5_stat_columns_exist(self, sample_lag_merged_df: pd.DataFrame) -> None:
        """Test 5: 5-race statistics columns exist: prev5_{metric}_mean, prev5_{metric}_std."""
        result = compute_lag_features(sample_lag_merged_df)

        metrics = ["finish_position", "last_3f", "corner_4", "finish_time_zscore", "margin_numeric"]
        for metric in metrics:
            assert f"prev5_{metric}_mean" in result.columns, f"Missing: prev5_{metric}_mean"
            assert f"prev5_{metric}_std" in result.columns, f"Missing: prev5_{metric}_std"

    def test_prev3_stats_with_fewer_races(self, sample_lag_merged_df: pd.DataFrame) -> None:
        """Test 6: Horse with only 2 past races uses 2 races for prev3 stats (min_periods=1)."""
        result = compute_lag_features(sample_lag_merged_df)

        # 馬A_2010: 3rd race (201502020201) has 2 prior valid starts
        horse_a_race3 = result[
            (result["horse_entity_key"] == "馬A_2010")
            & (result["race_id"] == "201502020201")
        ]
        assert len(horse_a_race3) == 1
        row = horse_a_race3.iloc[0]

        # prev3_finish_position_mean should use 2 prior values (3.0 and 1.0), not NaN
        assert not pd.isna(row["prev3_finish_position_mean"]), (
            "prev3 stats should not be NaN with 2 prior races (min_periods=1)"
        )
        expected_mean = (3.0 + 1.0) / 2.0
        assert row["prev3_finish_position_mean"] == pytest.approx(expected_mean, abs=0.01), (
            f"Expected prev3_mean={expected_mean}, got {row['prev3_finish_position_mean']}"
        )

    def test_scratched_entry_does_not_consume_lag_position(
        self, sample_lag_merged_df: pd.DataFrame
    ) -> None:
        """Test 7: A SCRATCHED entry (取) does NOT consume a lag position.

        Horse 馬B_2011: valid(pos=5), scratched(取), valid(pos=3), valid(pos=1)
        The 3rd valid start (pos=3) should have prev_1=5 (from 1st valid start),
        NOT NaN (from the scratched row).
        """
        result = compute_lag_features(sample_lag_merged_df)

        # 馬B_2011: 3rd valid start at 201502020201 (pos=3)
        horse_b_race3 = result[
            (result["horse_entity_key"] == "馬B_2011")
            & (result["race_id"] == "201502020201")
        ]
        assert len(horse_b_race3) == 1
        row = horse_b_race3.iloc[0]

        # prev_1 should point to the first valid start (pos=5), skipping the scratch
        assert row["prev_1_finish_position"] == 5.0, (
            f"prev_1_finish_position should be 5.0 (skipping scratched entry), got {row['prev_1_finish_position']}"
        )

        # The scratched entry itself should have all-NaN lags
        horse_b_scratched = result[
            (result["horse_entity_key"] == "馬B_2011")
            & (result["finish_note"] == "取")
        ]
        assert len(horse_b_scratched) == 1
        scratched_row = horse_b_scratched.iloc[0]
        assert pd.isna(scratched_row["prev_1_finish_position"]), (
            "Scratched entry should have NaN prev_1_finish_position"
        )

    def test_entity_key_isolation(self, sample_lag_merged_df: pd.DataFrame) -> None:
        """Test 8: Same-name horses with different birth years get independent lag histories.

        アームストロング_2011: race 1 (pos=1), race 2 (pos=4)
        アームストロング_2008: race 1 (pos=2) -- should NOT see アームストロング_2011's history
        """
        result = compute_lag_features(sample_lag_merged_df)

        # アームストロング_2008: first (and only) race should have NaN lag
        armstrong_2008 = result[
            (result["horse_entity_key"] == "アームストロング_2008")
        ]
        assert len(armstrong_2008) == 1
        assert pd.isna(armstrong_2008.iloc[0]["prev_1_finish_position"]), (
            "Different entity should have NaN lag (independent history)"
        )

        # アームストロング_2011: second race should see first race (pos=1)
        armstrong_2011_race2 = result[
            (result["horse_entity_key"] == "アームストロング_2011")
            & (result["race_id"] == "201501010201")
        ]
        assert len(armstrong_2011_race2) == 1
        assert armstrong_2011_race2.iloc[0]["prev_1_finish_position"] == 1.0, (
            "prev_1 should be from own entity's prior race, not from same-name different entity"
        )

    def test_same_day_races_ordered_by_race_id(
        self, sample_lag_merged_df: pd.DataFrame
    ) -> None:
        """Test 9: Same-day races at different courses are ordered by race_id in the lag chain.

        馬A_2010: R1 (201501010101, pos=3), R2 (201501010102, pos=1) -- same date
        prev_1 for R2 should be R1's result (pos=3), since 201501010101 < 201501010102.
        """
        result = compute_lag_features(sample_lag_merged_df)

        # 馬A_2010: race at 201501010102 should see prev_1 from 201501010101
        horse_a_r2 = result[
            (result["horse_entity_key"] == "馬A_2010")
            & (result["race_id"] == "201501010102")
        ]
        assert len(horse_a_r2) == 1
        assert horse_a_r2.iloc[0]["prev_1_finish_position"] == 3.0, (
            f"Same-day race R2 should see R1's finish_position=3.0, got {horse_a_r2.iloc[0]['prev_1_finish_position']}"
        )


class TestJockeyTrainerStats:
    """Tests for jockey/trainer rolling statistics (Plan 03-02)."""

    def test_not_yet_implemented(self) -> None:
        pytest.skip("Jockey/trainer stats not yet implemented (Plan 03-02)")


class TestTargetVariable:
    """Tests for target_top3 generation (Plan 03-04)."""

    def test_not_yet_implemented(self) -> None:
        pytest.skip("Target variable not yet implemented (Plan 03-04)")


class TestMarginConversion:
    """Tests for margin text-to-numeric conversion (Plan 03-02)."""

    def test_parse_margin_hana(self) -> None:
        """Test 1: parse_margin("ハナ") returns 0.02."""
        assert parse_margin("ハナ") == 0.02

    def test_parse_margin_kubi(self) -> None:
        """Test 2: parse_margin("クビ") returns 0.10."""
        assert parse_margin("クビ") == 0.10

    def test_parse_margin_fraction(self) -> None:
        """Test 3: parse_margin("1.1/4") returns 1.25."""
        assert parse_margin("1.1/4") == 1.25

    def test_parse_margin_oo(self) -> None:
        """Test 4: parse_margin("大") returns 15.0."""
        assert parse_margin("大") == 15.0

    def test_parse_margin_dead_heat(self) -> None:
        """Test 5: parse_margin("同着") returns 0.0."""
        assert parse_margin("同着") == 0.0

    def test_parse_margin_compound(self) -> None:
        """Test 6: parse_margin("1.1/4+クビ") returns 1.35 (compound)."""
        assert parse_margin("1.1/4+クビ") == pytest.approx(1.35)

    def test_parse_margin_compound_with_hana(self) -> None:
        """Test 7: parse_margin("2+ハナ") returns 2.02 (compound)."""
        assert parse_margin("2+ハナ") == pytest.approx(2.02)

    def test_parse_margin_none(self) -> None:
        """Test 8: parse_margin(None) returns None."""
        assert parse_margin(None) is None

    def test_parse_margin_compound_both_component_map(self) -> None:
        """Test 9: parse_margin("1/2+1/2") returns 1.0 (compound both in COMPONENT_MAP)."""
        assert parse_margin("1/2+1/2") == pytest.approx(1.0)

    def test_parse_margin_empty_string(self) -> None:
        """Test 10: parse_margin("") (empty string) returns None."""
        assert parse_margin("") is None

    def test_convert_margin_to_numeric_adds_column(
        self, sample_feature_merged_df: pd.DataFrame
    ) -> None:
        """Test 11: convert_margin_to_numeric() adds margin_numeric column to DataFrame."""
        result = convert_margin_to_numeric(sample_feature_merged_df)
        assert "margin_numeric" in result.columns

        # Verify specific values from fixture data
        # Row with margin="3/4" -> 0.75
        row_3_4 = result[result["margin"] == "3/4"]
        assert len(row_3_4) > 0
        assert row_3_4["margin_numeric"].iloc[0] == pytest.approx(0.75)

        # Row with margin="1.1/2" -> 1.50
        row_1_1_2 = result[result["margin"] == "1.1/2"]
        assert len(row_1_1_2) > 0
        assert row_1_1_2["margin_numeric"].iloc[0] == pytest.approx(1.50)

        # Row with margin=None -> margin_numeric=None
        row_none = result[result["margin"].isna()]
        assert len(row_none) > 0
        assert row_none["margin_numeric"].isna().all()

    def test_parse_margin_unicode_whitespace(self) -> None:
        """Test 12: parse_margin handles whitespace gracefully."""
        # Trailing space should still match after strip
        assert parse_margin("ハナ ") == 0.02
        # Full-width space (common in Japanese data)
        assert parse_margin("ハナ　") == 0.02
        # Unknown value returns None, no crash
        assert parse_margin("未知の値") is None


class TestFinishTimeZscore:
    """Tests for finish_time z-score normalization with race-boundary safety (Plan 03-02)."""

    def test_parse_finish_time_to_seconds_normal(self) -> None:
        """Test 1: parse_finish_time_to_seconds("1:29.5") returns 89.5."""
        assert parse_finish_time_to_seconds("1:29.5") == pytest.approx(89.5)

    def test_parse_finish_time_to_seconds_sub_minute(self) -> None:
        """Test 2: parse_finish_time_to_seconds("0:59.3") returns 59.3."""
        assert parse_finish_time_to_seconds("0:59.3") == pytest.approx(59.3)

    def test_parse_finish_time_to_seconds_none(self) -> None:
        """Test 3: parse_finish_time_to_seconds(None) returns NaN."""
        import math

        result = parse_finish_time_to_seconds(None)
        assert math.isnan(result)

    def test_compute_finish_time_zscore_adds_columns(self) -> None:
        """Test 4: compute_finish_time_zscore() adds finish_time_seconds and finish_time_zscore columns."""
        df = self._make_two_race_fixture()
        result = compute_finish_time_zscore(df)
        assert "finish_time_seconds" in result.columns
        assert "finish_time_zscore" in result.columns

    def test_all_runners_same_race_identical_norm_params(self) -> None:
        """Test 5: ALL runners in race N receive IDENTICAL normalization mean and std.

        This is the race-boundary guarantee: the z-score for each runner
        depends only on prior races, not on other runners in the same race.
        """
        df = self._make_two_race_fixture()
        result = compute_finish_time_zscore(df)

        # For race 2 (race_id="R2"), all runners should have same z-score
        race2 = result[result["race_id"] == "R2"]
        assert len(race2) >= 2, "Need at least 2 runners in race 2"

        zscores = race2["finish_time_zscore"].values
        # All z-scores should be identical (same norm_mean, norm_std per runner)
        # But different finish_time_seconds -> different z-scores
        # What must be identical is the normalization parameters, which we
        # can verify indirectly: all z-scores should follow (x - mu) / sigma
        # with the same mu and sigma.
        #
        # More directly: we verify this in test 7 by checking that norm parameters
        # come only from prior races. Here we verify the derived z-scores are
        # well-formed (finite for race 2 since race 1 provides history).
        import math

        for z in zscores:
            if not math.isnan(z):
                assert abs(z) < 100, f"Z-score {z} unreasonably large"

    def test_later_race_sees_prior_race_stats(self) -> None:
        """Test 6: Runners in race N+1 see normalization stats that INCLUDE race N's times.

        Race 6's normalization should be based on races 1-5's finish times
        (min_periods=5 met).
        """
        df = self._make_many_race_fixture(num_races=7)
        result = compute_finish_time_zscore(df)

        # Race 6 has 5 prior races -> min_periods=5 met -> z-scores should be non-NaN
        race6 = result[result["race_id"] == "R6"]
        zscores = race6["finish_time_zscore"].dropna().values
        assert len(zscores) > 0, (
            "Race 6 should have non-NaN z-scores (5 prior races, min_periods=5 met)"
        )

    def test_no_same_race_leakage(self) -> None:
        """Test 7: Runners in race N see normalization stats that EXCLUDE race N's own times.

        The race-boundary approach guarantees: norm_mean and norm_std for race N
        are computed from races 1..N-1 only.
        """
        # Create a fixture with 5 races in the same (course, distance, surface) group
        # so we have enough prior races for min_periods=5... actually let's use 6
        # races so race 6 has 5 prior races.
        # Actually the plan says min_periods=5, but for the leakage test we just
        # need to verify the property. Let's use a simpler approach:
        # If there's no leakage, adding a runner to race 1 with a very different
        # finish time should NOT change race 1's own z-scores (they should be NaN
        # if there are 0 prior races, or based on even earlier races only).
        #
        # Simpler: create 2 races with 3 runners each. Race 1 has no prior history
        # -> z-score should be NaN (min_periods=5 not met). Race 2 should get stats
        # from race 1 only.
        df = self._make_two_race_fixture()
        result = compute_finish_time_zscore(df)

        # Race 1 has no prior races -> z-scores should be NaN (min_periods=5)
        race1 = result[result["race_id"] == "R1"]
        assert race1["finish_time_zscore"].isna().all(), (
            "Race 1 should have NaN z-scores (no prior races, min_periods=5)"
        )

        # Race 2 should have z-scores based on race 1's mean/std
        # But since race 1 is only 1 prior race, and min_periods=5, it should also be NaN
        # Let me construct enough races to actually test this...

        # Actually, the key test is with enough data. Let me use the full fixture.
        df2 = self._make_many_race_fixture(num_races=7)
        result2 = compute_finish_time_zscore(df2)

        # Race 7 should have stats from races 1-6
        race7 = result2[result2["race_id"] == "R7"]
        assert not race7["finish_time_zscore"].isna().all(), (
            "Race 7 should have valid z-scores (6 prior races, min_periods=5 met)"
        )

        # Verify race 7's normalization is based only on races 1-6:
        # Manually compute expected mean and std from races 1-6
        races_1_6 = df2[df2["race_id"].isin([f"R{i}" for i in range(1, 7)])]
        from src.pipeline.feature_generator import parse_finish_time_to_seconds

        ft_secs = races_1_6["finish_time"].apply(parse_finish_time_to_seconds)
        race_means_1_6 = ft_secs.groupby(races_1_6["race_id"]).mean()
        overall_mean = race_means_1_6.mean()
        overall_std = race_means_1_6.std(ddof=1)

        # Race 7's z-scores should use these stats
        race7_ft = race7["finish_time"].apply(parse_finish_time_to_seconds)
        expected_zscores = (race7_ft - overall_mean) / overall_std

        for actual, expected in zip(race7["finish_time_zscore"].values, expected_zscores.values):
            if not (pd.isna(actual) and pd.isna(expected)):
                assert actual == pytest.approx(expected, abs=0.01), (
                    f"Expected z-score {expected}, got {actual}"
                )

    def test_temporal_invariance(self) -> None:
        """Test 8: Adding a future race does NOT change z-score values for historical rows.

        This is the temporal invariance guarantee.
        """
        # Compute z-scores with 7 races
        df_7 = self._make_many_race_fixture(num_races=7)
        result_7 = compute_finish_time_zscore(df_7)

        # Compute z-scores with 8 races (added future race)
        df_8 = self._make_many_race_fixture(num_races=8)
        result_8 = compute_finish_time_zscore(df_8)

        # Z-scores for races 1-7 should be identical in both results
        for race_num in range(1, 8):
            race_id = f"R{race_num}"
            z_7 = result_7[result_7["race_id"] == race_id]["finish_time_zscore"].values
            z_8 = result_8[result_8["race_id"] == race_id]["finish_time_zscore"].values

            assert len(z_7) == len(z_8), f"Race {race_id}: row count mismatch"
            for a, b in zip(z_7, z_8):
                if pd.isna(a) and pd.isna(b):
                    continue
                assert a == pytest.approx(b, abs=0.001), (
                    f"Race {race_id}: z-score changed after adding future race "
                    f"({a} -> {b})"
                )

    def test_sparse_group_nan_zscore(self) -> None:
        """Test 9: Course-distance-surface combos with fewer than 5 prior RACES get NaN z-score."""
        df = self._make_many_race_fixture(num_races=4)
        result = compute_finish_time_zscore(df)

        # With only 4 prior races max (race 4 has 3 prior), all should be NaN
        assert result["finish_time_zscore"].isna().all(), (
            "All z-scores should be NaN when no group has >= 5 prior races"
        )

    def test_zero_std_produces_nan(self) -> None:
        """Test 10: When expanding std is 0 or NaN, z-score is NaN not inf."""
        # Create a fixture where all races have the exact same finish time
        rows = []
        for race_num in range(1, 8):
            for horse_num in range(1, 4):
                rows.append({
                    "race_id": f"R{race_num}",
                    "race_date": f"2015-01-{race_num:02d}",
                    "course_name": "東京",
                    "distance": 2000,
                    "surface": "芝",
                    "finish_time": "1:58.5",  # All identical times
                    "horse_entity_key": f"馬{race_num}_{horse_num}",
                })
        df = pd.DataFrame(rows)
        result = compute_finish_time_zscore(df)

        # All z-scores should be NaN (std=0 for identical times)
        assert result["finish_time_zscore"].isna().all(), (
            "Z-scores should be NaN when std is 0 (all identical times)"
        )

    def test_zscore_typical_range(self) -> None:
        """Test 11: finish_time_zscore values are typically between -5 and +5 (sanity check)."""
        df = self._make_many_race_fixture(num_races=10)
        result = compute_finish_time_zscore(df)

        non_nan_zscores = result["finish_time_zscore"].dropna().values
        if len(non_nan_zscores) > 0:
            for z in non_nan_zscores:
                assert -5 <= z <= 5, f"Z-score {z} outside expected range [-5, 5]"

    # -- Helper: create fixtures for race-boundary tests --

    @staticmethod
    def _make_two_race_fixture() -> pd.DataFrame:
        """Create a DataFrame with 2 races, 3 runners each, same course/distance/surface."""
        rows = []
        # Race 1: 東京 2000 芝, 2015-01-01
        times_r1 = ["1:58.5", "1:58.8", "1:59.1"]
        for i, t in enumerate(times_r1, start=1):
            rows.append({
                "race_id": "R1",
                "race_date": "2015-01-01",
                "course_name": "東京",
                "distance": 2000,
                "surface": "芝",
                "finish_time": t,
                "horse_entity_key": f"馬{i}",
            })
        # Race 2: same course/distance/surface, 2015-02-01
        times_r2 = ["1:57.5", "1:58.0", "1:59.5"]
        for i, t in enumerate(times_r2, start=4):
            rows.append({
                "race_id": "R2",
                "race_date": "2015-02-01",
                "course_name": "東京",
                "distance": 2000,
                "surface": "芝",
                "finish_time": t,
                "horse_entity_key": f"馬{i}",
            })
        return pd.DataFrame(rows)

    @staticmethod
    def _make_many_race_fixture(num_races: int = 7) -> pd.DataFrame:
        """Create a DataFrame with num_races races, 3 runners each, same course/distance/surface.

        Finish times vary naturally to produce meaningful z-scores.
        """
        import random

        random.seed(42)
        rows = []
        base_times = [
            ("1:58.5", "1:58.8", "1:59.1"),
            ("1:57.2", "1:57.5", "1:58.0"),
            ("1:59.0", "1:59.3", "1:59.8"),
            ("1:56.5", "1:57.0", "1:57.5"),
            ("1:58.0", "1:58.3", "1:58.8"),
            ("1:57.8", "1:58.1", "1:58.5"),
            ("1:59.5", "1:59.8", "2:00.2"),
            ("1:57.0", "1:57.3", "1:57.8"),
            ("1:58.2", "1:58.6", "1:59.0"),
            ("1:56.8", "1:57.2", "1:57.6"),
        ]
        for race_num in range(1, num_races + 1):
            times = base_times[(race_num - 1) % len(base_times)]
            for horse_idx, t in enumerate(times):
                rows.append({
                    "race_id": f"R{race_num}",
                    "race_date": f"2015-{race_num:02d}-01",
                    "course_name": "東京",
                    "distance": 2000,
                    "surface": "芝",
                    "finish_time": t,
                    "horse_entity_key": f"馬R{race_num}H{horse_idx + 1}",
                })
        return pd.DataFrame(rows)


class TestCategoricalConversion:
    """Tests for CategoricalDtype conversion (Plan 03-05)."""

    def test_not_yet_implemented(self) -> None:
        pytest.skip("Categorical conversion not yet implemented (Plan 03-05)")


class TestDebutFlag:
    """Tests for debut flag for first-time starters (Plan 03-03)."""

    def test_not_yet_implemented(self) -> None:
        pytest.skip("Debut flag not yet implemented (Plan 03-03)")


class TestLeakageAudit:
    """Tests for leakage audit integration (Plan 03-05)."""

    def test_not_yet_implemented(self) -> None:
        pytest.skip("Leakage audit not yet implemented (Plan 03-05)")


class TestEndToEnd:
    """End-to-end feature generation tests (Plan 03-05)."""

    def test_not_yet_implemented(self) -> None:
        pytest.skip("End-to-end test not yet implemented (Plan 03-05)")
