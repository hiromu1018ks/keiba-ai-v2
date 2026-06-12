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
    convert_margin_to_numeric,
    derive_horse_entity_key,
    extract_horse_basic_features,
    extract_race_context_features,
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
    """Tests for lag feature generation (Plan 03-02)."""

    def test_not_yet_implemented(self) -> None:
        pytest.skip("Lag features not yet implemented (Plan 03-02)")


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
    """Tests for finish_time z-score normalization (Plan 03-02)."""

    def test_not_yet_implemented(self) -> None:
        pytest.skip("Finish time z-score not yet implemented (Plan 03-02)")


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
