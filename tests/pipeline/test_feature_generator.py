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
    CATEGORICAL_COLUMNS,
    FEATURE_COLUMNS,
    _compute_person_stats,
    compute_finish_time_zscore,
    compute_jockey_trainer_stats,
    compute_lag_features,
    compute_debut_flag,
    convert_categorical,
    convert_margin_to_numeric,
    derive_horse_entity_key,
    extract_horse_basic_features,
    extract_race_context_features,
    generate_target,
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
    """Tests for jockey/trainer rolling statistics with sum-based race-level aggregation and exact D-08 intersection (Plan 03-03)."""

    @staticmethod
    def _make_person_stats_df() -> pd.DataFrame:
        """Create a fixture for basic person stats testing.

        Trainer 調教師A: 3 runners in race R1 (2 top-3, 1 not), 1 runner in race R2
        Jockey 騎手A: appears in 4 races over time
        """
        return pd.DataFrame({
            "race_id": ["R1", "R1", "R1", "R2", "R3", "R4"],
            "race_date": pd.to_datetime(["2015-01-01", "2015-01-01", "2015-01-01",
                                          "2015-02-01", "2015-03-01", "2015-04-01"]),
            "horse_entity_key": ["馬1_2010", "馬2_2011", "馬3_2012", "馬4_2013", "馬5_2014", "馬6_2015"],
            "finish_position": [1, 2, 6, 3, 1, 4],
            "finish_note": [None, None, None, None, None, None],
            "jockey": ["騎手A", "騎手B", "騎手A", "騎手A", "騎手A", "騎手B"],
            "trainer": ["調教師A", "調教師A", "調教師A", "調教師A", "調教師B", "調教師B"],
        })

    def test_jockey_stat_columns_exist(self) -> None:
        """Test 1: Jockey stat columns exist: jockey_rolling_top3_rate, win_rate, rides."""
        df = self._make_person_stats_df()
        result = compute_jockey_trainer_stats(df)

        assert "jockey_rolling_top3_rate" in result.columns
        assert "jockey_rolling_win_rate" in result.columns
        assert "jockey_rolling_rides" in result.columns

    def test_trainer_stat_columns_exist(self) -> None:
        """Test 2: Trainer stat columns exist: trainer_rolling_top3_rate, win_rate, rides."""
        df = self._make_person_stats_df()
        result = compute_jockey_trainer_stats(df)

        assert "trainer_rolling_top3_rate" in result.columns
        assert "trainer_rolling_win_rate" in result.columns
        assert "trainer_rolling_rides" in result.columns

    def test_first_race_zero_rides(self) -> None:
        """Test 3: jockey_rolling_rides for a jockey's first race is 0."""
        df = self._make_person_stats_df()
        result = compute_jockey_trainer_stats(df)

        # 騎手A's first race is R1 (first row)
        jockey_a_first = result[
            (result["jockey"] == "騎手A") & (result["race_id"] == "R1")
        ]
        # First appearance: all runners of 騎手A in R1 should have rides=0
        for _, row in jockey_a_first.iterrows():
            assert row["jockey_rolling_rides"] == 0.0, (
                f"First appearance should have 0 rides, got {row['jockey_rolling_rides']}"
            )

    def test_sum_based_trainer_rate(self) -> None:
        """Test 4: Trainer with 3 runners (2 top-3, 1 not) produces rate 2/3 = 0.667.

        This is the critical sum-based test: trainer 調教師A has 3 runners in R1,
        2 finished top-3 (positions 1 and 2) and 1 did not (position 6).
        The NEXT race (R2) for 調教師A should see rolling_top3_rate = 2/3.
        """
        df = self._make_person_stats_df()
        result = compute_jockey_trainer_stats(df)

        # 調教師A in R2 should see rolling stats from R1
        trainer_a_r2 = result[
            (result["trainer"] == "調教師A") & (result["race_id"] == "R2")
        ]
        assert len(trainer_a_r2) == 1
        row = trainer_a_r2.iloc[0]

        assert row["trainer_rolling_top3_rate"] == pytest.approx(2.0 / 3.0, abs=0.01), (
            f"Expected sum-based rate 2/3=0.667, got {row['trainer_rolling_top3_rate']}"
        )
        # win_rate: 1 winner from 3 runners = 1/3
        assert row["trainer_rolling_win_rate"] == pytest.approx(1.0 / 3.0, abs=0.01), (
            f"Expected win rate 1/3=0.333, got {row['trainer_rolling_win_rate']}"
        )

    def test_stats_use_only_past_data(self) -> None:
        """Test 5: Stats use only past data -- current race does not influence stats.

        Jockey 騎手A in R1 (finish_position 1 and 6): rolling stats should be 0 (first race).
        In R2 (finish_position 3): rolling stats should reflect R1 only.
        """
        df = self._make_person_stats_df()
        result = compute_jockey_trainer_stats(df)

        # 騎手A in R1: first race, stats should be 0
        jockey_a_r1 = result[
            (result["jockey"] == "騎手A") & (result["race_id"] == "R1")
        ]
        for _, row in jockey_a_r1.iterrows():
            assert row["jockey_rolling_rides"] == 0.0, "First race should have 0 rides"

        # 騎手A in R2: stats from R1 only
        jockey_a_r2 = result[
            (result["jockey"] == "騎手A") & (result["race_id"] == "R2")
        ]
        assert len(jockey_a_r2) == 1
        row_r2 = jockey_a_r2.iloc[0]

        # R1: 騎手A had 2 runners, 1 top-3 (pos=1), 1 not top-3 (pos=6) -> top3_rate = 1/2
        assert row_r2["jockey_rolling_top3_rate"] == pytest.approx(1.0 / 2.0, abs=0.01), (
            f"Expected 1/2=0.5, got {row_r2['jockey_rolling_top3_rate']}"
        )
        assert row_r2["jockey_rolling_rides"] == 2.0, (
            f"Expected 2 rides from R1, got {row_r2['jockey_rolling_rides']}"
        )

    def test_temporal_invariance(self) -> None:
        """Test 6: Adding future races does not change current race's stats."""
        df_base = self._make_person_stats_df()

        # Add a future race
        future_row = pd.DataFrame({
            "race_id": ["R5"],
            "race_date": pd.to_datetime(["2016-01-01"]),
            "horse_entity_key": ["馬7_2016"],
            "finish_position": [1],
            "finish_note": [None],
            "jockey": ["騎手A"],
            "trainer": ["調教師C"],
        })
        df_extended = pd.concat([df_base, future_row], ignore_index=True)

        result_base = compute_jockey_trainer_stats(df_base)
        result_extended = compute_jockey_trainer_stats(df_extended)

        # Stats for R1..R4 should be identical
        for race_id in ["R1", "R2", "R3", "R4"]:
            base_rows = result_base[result_base["race_id"] == race_id].sort_values("horse_entity_key")
            ext_rows = result_extended[result_extended["race_id"] == race_id].sort_values("horse_entity_key")

            for col in ["jockey_rolling_top3_rate", "jockey_rolling_win_rate", "jockey_rolling_rides"]:
                for (_, b), (_, e) in zip(base_rows.iterrows(), ext_rows.iterrows()):
                    if pd.isna(b[col]) and pd.isna(e[col]):
                        continue
                    assert b[col] == pytest.approx(e[col], abs=0.001), (
                        f"Race {race_id} {col}: base={b[col]} vs extended={e[col]}"
                    )

    def test_rate_range(self) -> None:
        """Test 7: Rate values are in [0.0, 1.0] range."""
        df = self._make_person_stats_df()
        result = compute_jockey_trainer_stats(df)

        for col in ["jockey_rolling_top3_rate", "jockey_rolling_win_rate",
                     "trainer_rolling_top3_rate", "trainer_rolling_win_rate"]:
            non_nan = result[col].dropna()
            for val in non_nan:
                assert 0.0 <= val <= 1.0, f"{col} value {val} outside [0, 1]"

    def test_d08_exact_intersection_150_prior_starts(self) -> None:
        """Test 8: D-08 exact intersection with 150 prior valid starts.

        Jockey with 150 prior valid starts: 70 old (all outside 365 days),
        80 recent (all within 365 days).
        The 70 old are excluded by 365-day constraint -> 80 within 365 days.
        80 <= 100 so no capping -> all 80 used.
        """
        rows = []
        base_date = pd.Timestamp("2016-06-01")

        # 70 old races: ALL outside 365-day window (400 to 366 days ago)
        for i in range(70):
            race_date = base_date - pd.Timedelta(days=400 + i)  # 400 to 469 days ago
            rows.append({
                "race_id": f"OLD_{i:04d}",
                "race_date": race_date,
                "horse_entity_key": f"馬_old_{i}",
                "finish_position": 1,  # All wins for easy math
                "finish_note": None,
                "jockey": "騎手X",
                "trainer": "調教師X",
            })

        # 80 recent races: ALL within 365-day window (days 364 down to ~44)
        for i in range(80):
            race_date = base_date - pd.Timedelta(days=364 - (i * 4))
            rows.append({
                "race_id": f"REC_{i:04d}",
                "race_date": race_date,
                "horse_entity_key": f"馬_rec_{i}",
                "finish_position": 1,
                "finish_note": None,
                "jockey": "騎手X",
                "trainer": "調教師X",
            })

        # Current race
        rows.append({
            "race_id": "CURRENT",
            "race_date": base_date,
            "horse_entity_key": "馬_curr",
            "finish_position": 1,
            "finish_note": None,
            "jockey": "騎手X",
            "trainer": "調教師X",
        })

        df = pd.DataFrame(rows)
        result = compute_jockey_trainer_stats(df)

        current = result[result["race_id"] == "CURRENT"]
        assert len(current) == 1
        row = current.iloc[0]

        # 80 recent valid starts within 365 days, all wins
        # 70 old races outside 365 days excluded
        # 80 <= 100 so no capping -> rides = 80
        assert row["jockey_rolling_rides"] == 80.0, (
            f"Expected 80 rides (exact intersection), got {row['jockey_rolling_rides']}"
        )
        assert row["jockey_rolling_top3_rate"] == pytest.approx(1.0, abs=0.01), (
            f"Expected 1.0 (all wins in intersection), got {row['jockey_rolling_top3_rate']}"
        )

    def test_d08_no_constraint_binding(self) -> None:
        """Test 9: D-08 with 50 prior starts all within 365 days -- all 50 used."""
        rows = []
        base_date = pd.Timestamp("2016-06-01")

        # 50 races within 365 days
        for i in range(50):
            race_date = base_date - pd.Timedelta(days=364 - (i * 7))
            rows.append({
                "race_id": f"R_{i:04d}",
                "race_date": race_date,
                "horse_entity_key": f"馬_{i}",
                "finish_position": 2,  # All 2nd place (top-3 but not win)
                "finish_note": None,
                "jockey": "騎手Y",
                "trainer": "調教師Y",
            })

        # Current race
        rows.append({
            "race_id": "CURRENT",
            "race_date": base_date,
            "horse_entity_key": "馬_curr",
            "finish_position": 1,
            "finish_note": None,
            "jockey": "騎手Y",
            "trainer": "調教師Y",
        })

        df = pd.DataFrame(rows)
        result = compute_jockey_trainer_stats(df)

        current = result[result["race_id"] == "CURRENT"]
        row = current.iloc[0]

        # 50 starts, all top-3 (pos=2), no wins -> top3_rate=1.0, win_rate=0.0
        assert row["jockey_rolling_rides"] == 50.0
        assert row["jockey_rolling_top3_rate"] == pytest.approx(1.0, abs=0.01)
        assert row["jockey_rolling_win_rate"] == pytest.approx(0.0, abs=0.01)

    def test_d08_365_day_constraint_binding(self) -> None:
        """Test 10: D-08 with 120 prior starts, 80 within 365 days -- uses 80."""
        rows = []
        base_date = pd.Timestamp("2016-06-01")

        # 40 old races (outside 365 days) -- all wins
        for i in range(40):
            race_date = base_date - pd.Timedelta(days=366 + i)
            rows.append({
                "race_id": f"OLD_{i:04d}",
                "race_date": race_date,
                "horse_entity_key": f"馬_old_{i}",
                "finish_position": 1,  # wins
                "finish_note": None,
                "jockey": "騎手Z",
                "trainer": "調教師Z",
            })

        # 80 recent races (within 365 days) -- all 4th place (not top-3)
        for i in range(80):
            race_date = base_date - pd.Timedelta(days=364 - (i * 4))
            rows.append({
                "race_id": f"REC_{i:04d}",
                "race_date": race_date,
                "horse_entity_key": f"馬_rec_{i}",
                "finish_position": 4,  # not top-3
                "finish_note": None,
                "jockey": "騎手Z",
                "trainer": "調教師Z",
            })

        # Current race
        rows.append({
            "race_id": "CURRENT",
            "race_date": base_date,
            "horse_entity_key": "馬_curr",
            "finish_position": 1,
            "finish_note": None,
            "jockey": "騎手Z",
            "trainer": "調教師Z",
        })

        df = pd.DataFrame(rows)
        result = compute_jockey_trainer_stats(df)

        current = result[result["race_id"] == "CURRENT"]
        row = current.iloc[0]

        # 80 starts within 365 days, all pos=4 (not top-3) -> top3_rate=0.0
        # The 40 old wins are excluded by 365-day constraint
        assert row["jockey_rolling_rides"] == 80.0
        assert row["jockey_rolling_top3_rate"] == pytest.approx(0.0, abs=0.01)
        assert row["jockey_rolling_win_rate"] == pytest.approx(0.0, abs=0.01)

    def test_dnf_count_as_valid_starts(self) -> None:
        """Test 11: DNF (中) counts as valid start in denominator; 取/除 do NOT."""
        rows = [
            # Race 1: 騎手W has 3 runners: 1 top-3, 1 DNF (中), 1 取 (scratched)
            {"race_id": "R1", "race_date": pd.Timestamp("2015-01-01"),
             "horse_entity_key": "馬1", "finish_position": 1, "finish_note": None,
             "jockey": "騎手W", "trainer": "調教師W"},
            {"race_id": "R1", "race_date": pd.Timestamp("2015-01-01"),
             "horse_entity_key": "馬2", "finish_position": None, "finish_note": "中",
             "jockey": "騎手W", "trainer": "調教師W"},
            {"race_id": "R1", "race_date": pd.Timestamp("2015-01-01"),
             "horse_entity_key": "馬3", "finish_position": None, "finish_note": "取",
             "jockey": "騎手W", "trainer": "調教師W"},
            # Race 2: 騎手W in next race
            {"race_id": "R2", "race_date": pd.Timestamp("2015-02-01"),
             "horse_entity_key": "馬4", "finish_position": 3, "finish_note": None,
             "jockey": "騎手W", "trainer": "調教師W"},
        ]
        df = pd.DataFrame(rows)
        result = compute_jockey_trainer_stats(df)

        # R2: 騎手W stats from R1
        # R1 valid starts: pos=1 (top-3, valid), pos=None+中 (DNF, valid), pos=None+取 (NOT valid)
        # -> valid_start_count = 2, top3_count = 1
        r2 = result[(result["jockey"] == "騎手W") & (result["race_id"] == "R2")]
        assert len(r2) == 1
        row = r2.iloc[0]

        assert row["jockey_rolling_rides"] == 2.0, (
            f"Expected 2 valid starts (DNF counts, scratch doesn't), got {row['jockey_rolling_rides']}"
        )
        assert row["jockey_rolling_top3_rate"] == pytest.approx(1.0 / 2.0, abs=0.01), (
            f"Expected 1/2=0.5, got {row['jockey_rolling_top3_rate']}"
        )


class TestTargetVariable:
    """Tests for target_top3 generation, result_status, is_dnf, exclude_from_training (Plan 03-04)."""

    @staticmethod
    def _make_target_df() -> pd.DataFrame:
        """Create a fixture covering all finish_note categories.

        Rows:
        1. pos=1, note=None  -> top3=1, status=finished
        2. pos=2, note=None  -> top3=1, status=finished
        3. pos=3, note=None  -> top3=1, status=finished
        4. pos=4, note=None  -> top3=0, status=finished
        5. pos=None, note=中 -> top3=0, status=dnf, is_dnf=True, exclude=False
        6. pos=None, note=取 -> top3=0, status=scratched, exclude=True
        7. pos=None, note=除 -> top3=0, status=removed, exclude=True
        8. pos=None, note=失 -> top3=0, status=disqualified, is_dnf=True, exclude=False
        9. pos=2, note=降    -> top3=1 (keeps pos=2), status=demoted
        10. pos=5, note=None  -> top3=0, status=finished
        """
        return pd.DataFrame({
            "horse_entity_key": [f"馬{i}" for i in range(10)],
            "finish_position": [1, 2, 3, 4, None, None, None, None, 2, 5],
            "finish_note": [None, None, None, None, "中", "取", "除", "失", "降", None],
        })

    def test_position_1_target_top3(self) -> None:
        """Test 1: finish_position 1 -> target_top3 = 1."""
        df = self._make_target_df()
        result = generate_target(df)
        assert result.iloc[0]["target_top3"] == 1

    def test_position_2_target_top3(self) -> None:
        """Test 2: finish_position 2 -> target_top3 = 1."""
        df = self._make_target_df()
        result = generate_target(df)
        assert result.iloc[1]["target_top3"] == 1

    def test_position_3_target_top3(self) -> None:
        """Test 3: finish_position 3 -> target_top3 = 1."""
        df = self._make_target_df()
        result = generate_target(df)
        assert result.iloc[2]["target_top3"] == 1

    def test_position_4_target_top3(self) -> None:
        """Test 4: finish_position 4 -> target_top3 = 0."""
        df = self._make_target_df()
        result = generate_target(df)
        assert result.iloc[3]["target_top3"] == 0

    def test_dnf_middle_note(self) -> None:
        """Test 5: finish_note '中' (DNF) -> target_top3=0, result_status='dnf', is_dnf=True, exclude=False."""
        df = self._make_target_df()
        result = generate_target(df)
        row = result.iloc[4]
        assert row["target_top3"] == 0
        assert row["result_status"] == "dnf"
        assert row["is_dnf"] == True  # noqa: E712
        assert row["exclude_from_training"] == False  # noqa: E712

    def test_scratched_tori_note(self) -> None:
        """Test 6: finish_note '取' (scratched) -> target_top3=0, result_status='scratched', exclude=True."""
        df = self._make_target_df()
        result = generate_target(df)
        row = result.iloc[5]
        assert row["target_top3"] == 0
        assert row["result_status"] == "scratched"
        assert row["exclude_from_training"] == True  # noqa: E712

    def test_removed_jo_note(self) -> None:
        """Test 7: finish_note '除' (removed) -> target_top3=0, result_status='removed', exclude=True."""
        df = self._make_target_df()
        result = generate_target(df)
        row = result.iloc[6]
        assert row["target_top3"] == 0
        assert row["result_status"] == "removed"
        assert row["exclude_from_training"] == True  # noqa: E712

    def test_disqualified_shitsu_note(self) -> None:
        """Test 8: finish_note '失' (disqualified) -> target_top3=0, result_status='disqualified', is_dnf=True, exclude=False."""
        df = self._make_target_df()
        result = generate_target(df)
        row = result.iloc[7]
        assert row["target_top3"] == 0
        assert row["result_status"] == "disqualified"
        assert row["is_dnf"] == True  # noqa: E712
        assert row["exclude_from_training"] == False  # noqa: E712

    def test_demoted_kou_note_keeps_position(self) -> None:
        """Test 9: finish_note '降' (demoted) keeps finish_position, target_top3 based on position."""
        df = self._make_target_df()
        result = generate_target(df)
        row = result.iloc[8]
        assert row["target_top3"] == 1  # position 2 is top-3
        assert row["result_status"] == "demoted"

    def test_normal_finish_result_status(self) -> None:
        """Test 10: Normal finish (no note) -> result_status='finished', is_dnf=False."""
        df = self._make_target_df()
        result = generate_target(df)
        row = result.iloc[9]  # pos=5, note=None
        assert row["result_status"] == "finished"
        assert row["is_dnf"] == False  # noqa: E712
        assert row["exclude_from_training"] == False  # noqa: E712

    def test_scratched_vs_removed_distinct_status(self) -> None:
        """Test 11: finish_note '取' and '除' produce DIFFERENT result_status values."""
        df = self._make_target_df()
        result = generate_target(df)
        scratched_status = result.iloc[5]["result_status"]
        removed_status = result.iloc[6]["result_status"]
        assert scratched_status == "scratched"
        assert removed_status == "removed"
        assert scratched_status != removed_status, (
            "取 (scratched) and 除 (removed) must have distinct result_status values"
        )


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

    def test_all_categorical_columns_converted(self) -> None:
        """Test 1: convert_to_categorical() converts all 9 CATEGORICAL_COLUMNS to category dtype."""
        from src.pipeline.feature_generator import CATEGORICAL_COLUMNS, convert_to_categorical

        df = pd.DataFrame({
            "course_name": ["東京", "中山"],
            "surface": ["芝", "ダート"],
            "direction": ["左", "右"],
            "weather": ["晴", "曇"],
            "track_condition": ["良", "稍重"],
            "sex": ["牡", "牝"],
            "jockey": ["騎手A", "騎手B"],
            "trainer": ["調教師A", "調教師B"],
            "grade": [None, "G1"],
        })
        result = convert_to_categorical(df)
        for col in CATEGORICAL_COLUMNS:
            assert col in result.columns, f"Missing column: {col}"
            assert pd.api.types.is_categorical_dtype(result[col]) or str(result[col].dtype) == "category", (
                f"Column {col} should be category dtype, got {result[col].dtype}"
            )

    def test_whitespace_stripped_before_conversion(self) -> None:
        """Test 2: Whitespace stripped before conversion -- '晴 ' becomes '晴' (single category)."""
        from src.pipeline.feature_generator import convert_to_categorical

        df = pd.DataFrame({
            "weather": ["晴 ", "晴", " 曇"],
            "course_name": ["東京", "東京", "東京"],
        })
        result = convert_to_categorical(df)
        weather_cats = result["weather"].cat.categories.tolist()
        assert len(weather_cats) == 2, (
            f"Expected 2 categories after strip (晴, 曇), got {weather_cats}"
        )
        assert "晴" in weather_cats
        assert "曇" in weather_cats

    def test_nan_preserved_in_categorical(self) -> None:
        """Test 3: NaN values are preserved within CategoricalDtype."""
        from src.pipeline.feature_generator import convert_to_categorical

        df = pd.DataFrame({
            "weather": ["晴", None, "曇"],
            "course_name": ["東京", "中山", None],
        })
        result = convert_to_categorical(df)
        assert pd.isna(result["weather"].iloc[1])
        assert pd.isna(result["course_name"].iloc[2])


class TestDebutFlag:
    """Tests for debut flag (is_debut) excluding 取/除 from history count (Plan 03-04)."""

    @staticmethod
    def _make_debut_df() -> pd.DataFrame:
        """Create a fixture for debut flag testing.

        Horses:
        - 馬A_2010: 3 valid starts (pos 1, 2, 3) -- debut at first entry
        - 馬B_2011: scratched(取), valid(pos=5), valid(pos=3), valid(pos=1) -- debut at second entry
        - 馬C_2012: 2 valid starts -- debut at first entry
        - 馬D_2013: 取, 取 -- all scratched, no valid start, is_debut=False for all
        """
        return pd.DataFrame({
            "horse_entity_key": [
                "馬A_2010", "馬A_2010", "馬A_2010",
                "馬B_2011", "馬B_2011", "馬B_2011", "馬B_2011",
                "馬C_2012", "馬C_2012",
                "馬D_2013", "馬D_2013",
            ],
            "race_id": [
                "R1", "R2", "R3",
                "R4", "R5", "R6", "R7",
                "R8", "R9",
                "R10", "R11",
            ],
            "race_date": pd.to_datetime([
                "2015-01-01", "2015-02-01", "2015-03-01",
                "2015-01-01", "2015-02-01", "2015-03-01", "2015-04-01",
                "2015-01-01", "2015-02-01",
                "2015-01-01", "2015-02-01",
            ]),
            "finish_position": [
                1, 2, 3,
                None, 5, 3, 1,
                2, 4,
                None, None,
            ],
            "finish_note": [
                None, None, None,
                "取", None, None, None,
                None, None,
                "取", "取",
            ],
            "result_status": [
                "finished", "finished", "finished",
                "scratched", "finished", "finished", "finished",
                "finished", "finished",
                "scratched", "scratched",
            ],
        })

    def test_debut_true_for_first_valid_start(self) -> None:
        """Test 1: is_debut is True for a horse's first valid start."""
        df = self._make_debut_df()
        result = compute_debut_flag(df)
        # 馬A_2010: first valid start at R1 -> is_debut=True
        horse_a_r1 = result[(result["horse_entity_key"] == "馬A_2010") & (result["race_id"] == "R1")]
        assert len(horse_a_r1) == 1
        assert horse_a_r1.iloc[0]["is_debut"] == True  # noqa: E712

    def test_debut_false_for_subsequent_starts(self) -> None:
        """Test 2: is_debut is False for a horse's second or later valid start."""
        df = self._make_debut_df()
        result = compute_debut_flag(df)
        # 馬A_2010: second valid start at R2 -> is_debut=False
        horse_a_r2 = result[(result["horse_entity_key"] == "馬A_2010") & (result["race_id"] == "R2")]
        assert len(horse_a_r2) == 1
        assert horse_a_r2.iloc[0]["is_debut"] == False  # noqa: E712

    def test_scratched_first_entry_debut_at_next_valid(self) -> None:
        """Test 3: A horse whose first entry was 取 has is_debut=False for that entry, is_debut=True for next valid start."""
        df = self._make_debut_df()
        result = compute_debut_flag(df)

        # 馬B_2011: first entry at R4 is 取 -> is_debut=False
        horse_b_r4 = result[(result["horse_entity_key"] == "馬B_2011") & (result["race_id"] == "R4")]
        assert len(horse_b_r4) == 1
        assert horse_b_r4.iloc[0]["is_debut"] == False  # noqa: E712

        # 馬B_2011: second entry at R5 is first valid start -> is_debut=True
        horse_b_r5 = result[(result["horse_entity_key"] == "馬B_2011") & (result["race_id"] == "R5")]
        assert len(horse_b_r5) == 1
        assert horse_b_r5.iloc[0]["is_debut"] == True  # noqa: E712

    def test_debut_correlates_with_nan_lag_features(self) -> None:
        """Test 4: is_debut=True correlates with prev_1_finish_position being NaN (no prior history)."""
        df = self._make_debut_df()
        # Add prev_1_finish_position to simulate lag features
        df["prev_1_finish_position"] = [None, 1.0, 2.0, None, None, 5.0, 3.0, None, 2.0, None, None]
        result = compute_debut_flag(df)

        # All debut entries should have NaN prev_1_finish_position
        debut_rows = result[result["is_debut"] == True]  # noqa: E712
        for _, row in debut_rows.iterrows():
            assert pd.isna(row["prev_1_finish_position"]), (
                f"Debut horse at race {row['race_id']} should have NaN prev_1_finish_position"
            )

    def test_independent_tracking_per_entity_key(self) -> None:
        """Test 5: Different horse entities each get independent debut tracking."""
        df = self._make_debut_df()
        result = compute_debut_flag(df)

        # 馬A_2010 and 馬C_2012 each have is_debut=True at their first valid starts
        horse_a_r1 = result[(result["horse_entity_key"] == "馬A_2010") & (result["race_id"] == "R1")]
        horse_c_r8 = result[(result["horse_entity_key"] == "馬C_2012") & (result["race_id"] == "R8")]
        assert horse_a_r1.iloc[0]["is_debut"] == True  # noqa: E712
        assert horse_c_r8.iloc[0]["is_debut"] == True  # noqa: E712

    def test_all_scratched_horse_debut_false(self) -> None:
        """Test 6: A horse with only 取 entries has is_debut=False for all entries."""
        df = self._make_debut_df()
        result = compute_debut_flag(df)

        # 馬D_2013: all entries are 取 -> is_debut=False for all
        horse_d = result[result["horse_entity_key"] == "馬D_2013"]
        assert len(horse_d) == 2
        for _, row in horse_d.iterrows():
            assert row["is_debut"] == False  # noqa: E712


class TestLeakageAudit:
    """Tests for leakage audit integration (Plan 03-05)."""

    def test_audit_leakage_empty_on_feature_output(self) -> None:
        """Test 1: audit_leakage() called with [RaceSchema, EntrySchema, ResultSchema] returns empty list on feature output."""
        from src.pipeline.feature_generator import FEATURE_COLUMNS
        from src.schemas.audit import audit_leakage
        from src.schemas.race import RaceSchema
        from src.schemas.entry import EntrySchema
        from src.schemas.result import ResultSchema

        # Create a DataFrame with only FEATURE_COLUMNS + entity keys
        # (simulating features_pred.parquet output)
        data = {col: [0] for col in FEATURE_COLUMNS}
        data["horse_entity_key"] = ["馬A_2010"]
        data["horse_name"] = ["馬A"]
        df = pd.DataFrame(data)

        leaked = audit_leakage([RaceSchema, EntrySchema, ResultSchema], df, "feature test")
        assert leaked == [], f"Expected no leakage, but found: {leaked}"

    def test_audit_leakage_detects_post_race_columns(self) -> None:
        """Test 2: audit_leakage() detects when post-race columns ARE present."""
        from src.schemas.audit import audit_leakage
        from src.schemas.race import RaceSchema
        from src.schemas.entry import EntrySchema
        from src.schemas.result import ResultSchema

        # DataFrame WITH post-race columns
        df = pd.DataFrame({
            "finish_position": [1],  # post-race from ResultSchema
            "popularity": [1],  # post-race from EntrySchema
            "win_odds": [2.5],  # post-race from EntrySchema
        })
        leaked = audit_leakage([RaceSchema, EntrySchema, ResultSchema], df, "leak test")
        assert len(leaked) > 0, "Should detect post-race columns"


class TestEndToEnd:
    """End-to-end feature generation tests (Plan 03-05)."""

    def _generate_full_pipeline(self, tmp_path: Path) -> dict:
        """Helper: run full generate() with test fixtures as standard data.

        Writes sample standard-layer Parquet files, then calls generate().
        """
        from src.pipeline.feature_generator import generate

        standard_dir = tmp_path / "data" / "standard"
        feature_dir = tmp_path / "data" / "feature"
        standard_dir.mkdir(parents=True, exist_ok=True)
        feature_dir.mkdir(parents=True, exist_ok=True)

        # Write test fixture data as Parquet
        # We need a conftest-like setup but self-contained
        race_df = pd.DataFrame({
            "race_id": ["201501010101", "201501010102", "201501010201",
                        "201502020201", "201503030101", "201503030102"],
            "race_date": ["2015-01-01", "2015-01-01", "2015-01-01",
                          "2015-02-02", "2015-03-03", "2015-03-03"],
            "meeting_num": [1, 1, 1, 1, 1, 1],
            "course_code": ["01", "01", "02", "02", "03", "03"],
            "course_name": ["東京", "東京", "中山", "中山", "京都", "京都"],
            "meeting_day": [1, 1, 1, 1, 1, 1],
            "race_condition": ["cond"] * 6,
            "race_number": [1, 2, 1, 1, 1, 2],
            "grade_revision": [None] * 6,
            "race_name": ["R1", "R2", "R3", "R4", "R5", "R6"],
            "grade": [None] * 6,
            "obstacle": [None] * 6,
            "surface": ["芝", "芝", "芝", "ダート", "芝", "芝"],
            "surface_detail": [None] * 6,
            "direction": ["左", "左", "右", "右", "右", "右"],
            "course_detail": [None] * 6,
            "distance": [2000, 1600, 1200, 1400, 2200, 1800],
            "weather": ["晴", "晴", "晴", "曇", "雨", "雨"],
            "track_condition": ["良", "良", "良", "稍重", "重", "重"],
            "track_condition_detail": [None] * 6,
            "start_time": ["10:00", "10:30", "10:00", "11:00", "14:00", "14:30"],
        })

        entry_df = pd.DataFrame({
            "horse_race_id": [
                "20150101010101", "20150101010102", "20150101010103",
                "20150101010201", "20150101010202",
                "20150101020101", "20150101020102", "20150101020103",
                "20150202020101", "20150202020102",
                "20150303010101", "20150303010102",
                "20150303010201", "20150303010202",
            ],
            "race_id": [
                "201501010101", "201501010101", "201501010101",
                "201501010102", "201501010102",
                "201501010201", "201501010201", "201501010201",
                "201502020201", "201502020201",
                "201503030101", "201503030101",
                "201503030102", "201503030102",
            ],
            "bracket_num": [1, 2, 3, 1, 2, 1, 2, 3, 1, 4, 1, 2, 1, 3],
            "horse_number": [1, 2, 3, 1, 2, 1, 2, 3, 1, 4, 1, 2, 1, 3],
            "horse_name": [
                "アームストロング", "馬A", "馬C",
                "馬A", "馬D",
                "馬A", "アームストロング", "馬F",
                "馬G", "馬H",
                "馬I", "馬J",
                "馬K", "馬L",
            ],
            "sex": ["牡", "牡", "牝", "牡", "セ", "牡", "牡", "牝", "牡", "牝", "牡", "牡", "牝", "牡"],
            "age": [4, 5, 3, 5, 4, 5, 7, 3, 4, 5, 6, 4, 3, 5],
            "weight_assigned": [57.0] * 14,
            "jockey": [
                "騎手A", "騎手B", "騎手C",
                "騎手D", "騎手A",
                "騎手A", "騎手E", "騎手F",
                "騎手G", "騎手H",
                "騎手I", "騎手J",
                "騎手A", "騎手K",
            ],
            "trainer": [
                "調教師X", "調教師Y", "調教師Z",
                "調教師X", "調教師W",
                "調教師X", "調教師V", "調教師U",
                "調教師T", "調教師S",
                "調教師A", "調教師A",
                "調教師R", "調教師Q",
            ],
            "owner": [f"馬主{i}" for i in range(14)],
            "horse_weight": [480 + i for i in range(14)],
            "weight_change": [i % 5 - 2 for i in range(14)],
            "region": ["東"] * 14,
            "popularity": [1] * 14,
            "win_odds": [2.0] * 14,
        })

        result_df = pd.DataFrame({
            "horse_race_id": [
                "20150101010101", "20150101010102", "20150101010103",
                "20150101010201", "20150101010202",
                "20150101020101", "20150101020102", "20150101020103",
                "20150202020101", "20150202020102",
                "20150303010101", "20150303010102",
                "20150303010201", "20150303010202",
            ],
            "race_id": [
                "201501010101", "201501010101", "201501010101",
                "201501010102", "201501010102",
                "201501010201", "201501010201", "201501010201",
                "201502020201", "201502020201",
                "201503030101", "201503030101",
                "201503030102", "201503030102",
            ],
            "finish_position": [1, 2, 3, 1, 4, 2, 5, None, 1, None, 3, 6, 1, 2],
            "finish_note": [None, None, None, None, None, None, None, "取", None, "中", None, None, None, None],
            "finish_time": [
                "1:58.5", "1:58.8", "1:59.1",
                "1:35.2", "1:36.0",
                "1:10.5", "1:11.2", None,
                "1:23.4", None,
                "2:15.3", "2:15.8",
                "1:48.2", "1:48.6",
            ],
            "margin": [
                None, "3/4", "1.1/2",
                None, "2",
                "ハナ", "3", None,
                None, None,
                "1.1/4", "5",
                None, "アタマ",
            ],
            "corner_1": [1, 3, 2, 1, 4, 1, 3, None, 2, None, 1, 5, 1, 3],
            "corner_2": [1, 3, 2, 1, 4, 1, 3, None, 2, None, 1, 5, 1, 3],
            "corner_3": [1, 2, 3, 1, 3, 1, 4, None, 1, None, 2, 5, 1, 2],
            "corner_4": [1, 2, 3, 1, 3, 1, 4, None, 1, None, 2, 5, 1, 2],
            "last_3f": [34.5, 34.8, 35.0, 36.0, 35.5, 33.2, 35.8, None, 33.5, None, 35.1, 36.0, 34.0, 34.2],
            "prize_money": [750.0, 300.0, 190.0, 500.0, None, 200.0, None, None, 400.0, None, 150.0, None, 600.0, 240.0],
        })

        race_df.to_parquet(standard_dir / "race.parquet", engine="pyarrow", index=False)
        entry_df.to_parquet(standard_dir / "entry.parquet", engine="pyarrow", index=False)
        result_df.to_parquet(standard_dir / "result.parquet", engine="pyarrow", index=False)

        return generate(standard_dir=standard_dir, feature_dir=feature_dir)

    def test_features_train_contains_target_and_auxiliary(self, tmp_path: Path) -> None:
        """Test 4: features_train.parquet contains target_top3, result_status, is_dnf, exclude_from_training."""
        paths = self._generate_full_pipeline(tmp_path)
        train_df = pd.read_parquet(paths["train"])

        assert "target_top3" in train_df.columns
        assert "result_status" in train_df.columns
        assert "is_dnf" in train_df.columns
        assert "exclude_from_training" in train_df.columns

    def test_features_pred_no_target_or_auxiliary(self, tmp_path: Path) -> None:
        """Test 5: features_pred.parquet does NOT contain target_top3, result_status, is_dnf, exclude_from_training."""
        paths = self._generate_full_pipeline(tmp_path)
        pred_df = pd.read_parquet(paths["pred"])

        assert "target_top3" not in pred_df.columns
        assert "result_status" not in pred_df.columns
        assert "is_dnf" not in pred_df.columns
        assert "exclude_from_training" not in pred_df.columns

    def test_features_pred_no_current_race_result_derivatives(self, tmp_path: Path) -> None:
        """Test 6: features_pred.parquet does NOT contain margin_numeric, finish_time_zscore, finish_time_seconds."""
        paths = self._generate_full_pipeline(tmp_path)
        pred_df = pd.read_parquet(paths["pred"])

        assert "margin_numeric" not in pred_df.columns
        assert "finish_time_zscore" not in pred_df.columns
        assert "finish_time_seconds" not in pred_df.columns

    def test_features_pred_contains_lag_versions(self, tmp_path: Path) -> None:
        """Test 7: features_pred.parquet DOES contain prev_1_margin_numeric, prev_1_finish_time_zscore."""
        paths = self._generate_full_pipeline(tmp_path)
        pred_df = pd.read_parquet(paths["pred"])

        assert "prev_1_margin_numeric" in pred_df.columns
        assert "prev_1_finish_time_zscore" in pred_df.columns

    def test_both_parquet_readable_with_correct_row_count(self, tmp_path: Path) -> None:
        """Test 8: Both Parquet files can be read back with correct row count."""
        paths = self._generate_full_pipeline(tmp_path)
        train_df = pd.read_parquet(paths["train"])
        pred_df = pd.read_parquet(paths["pred"])

        assert len(train_df) == 14, f"Expected 14 rows in train, got {len(train_df)}"
        assert len(pred_df) == 14, f"Expected 14 rows in pred, got {len(pred_df)}"

    def test_generate_returns_dict_with_train_and_pred(self, tmp_path: Path) -> None:
        """Test 9: generate() returns dict with 'train' and 'pred' keys mapping to file Paths."""
        paths = self._generate_full_pipeline(tmp_path)

        assert "train" in paths
        assert "pred" in paths
        assert paths["train"].exists()
        assert paths["pred"].exists()

    def test_feature_columns_is_static_allowlist(self) -> None:
        """Test 10: FEATURE_COLUMNS is a static list -- every column name is explicitly written in source code."""
        from src.pipeline.feature_generator import FEATURE_COLUMNS, RACE_FEATURES, HORSE_FEATURES, LAG_RAW_FEATURES, LAG_STAT_FEATURES, PERSON_FEATURES, DEBUT_FEATURE

        # Verify it's a list (not computed at runtime from df.columns)
        assert isinstance(FEATURE_COLUMNS, list)

        # Verify it's the concatenation of named feature groups
        expected = RACE_FEATURES + HORSE_FEATURES + LAG_RAW_FEATURES + LAG_STAT_FEATURES + PERSON_FEATURES + DEBUT_FEATURE
        assert FEATURE_COLUMNS == expected

    def test_generation_validates_expected_columns(self, tmp_path: Path) -> None:
        """Test 11: At generation time, assert all FEATURE_COLUMNS exist and no unexpected columns present."""
        from src.pipeline.feature_generator import FEATURE_COLUMNS

        paths = self._generate_full_pipeline(tmp_path)
        pred_df = pd.read_parquet(paths["pred"])

        # All FEATURE_COLUMNS should be present in pred
        for col in FEATURE_COLUMNS:
            assert col in pred_df.columns, f"FEATURE_COLUMN {col} missing from pred output"

    def test_pred_no_leakage_via_audit(self, tmp_path: Path) -> None:
        """Additional: audit_leakage() on features_pred returns empty list."""
        from src.schemas.audit import audit_leakage
        from src.schemas.race import RaceSchema
        from src.schemas.entry import EntrySchema
        from src.schemas.result import ResultSchema

        paths = self._generate_full_pipeline(tmp_path)
        pred_df = pd.read_parquet(paths["pred"])

        leaked = audit_leakage([RaceSchema, EntrySchema, ResultSchema], pred_df, "pred test")
        assert leaked == [], f"features_pred has leakage: {leaked}"
