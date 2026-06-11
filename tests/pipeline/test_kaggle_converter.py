"""Unit tests for the Kaggle CSV-to-Parquet converter.

Tests cover:
- Date filtering (2015+ only)
- Obstacle exclusion (D-01)
- Race/Entry/Result 3-way split with deduplication
- 20 flag column boolean conversion
- Finish position handling (normal, withdrawal, demoted)
- Odds table filtering and trifecta extraction
- Payoff table unpivoting
- Parquet file output existence
- audit_leakage() integration
"""

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from src.pipeline.column_mapping import FLAG_COLUMNS


class TestDateFilter:
    """Test that convert() filters to races on or after 2015-01-01."""

    def test_excludes_2014_race(self, sample_race_result_df, sample_odds_df, tmp_standard_dir):
        """Rows with race_date before 2015-01-01 are excluded from output."""
        from src.pipeline.kaggle_converter import convert

        # Create temp CSV files for convert() to read
        raw_dir = tmp_standard_dir.parent / "raw" / "kaggle"
        raw_dir.mkdir(parents=True, exist_ok=True)
        sample_race_result_df.to_csv(
            raw_dir / "19860105-20210731_race_result.csv", index=False, encoding="utf-8-sig"
        )
        sample_odds_df.to_csv(
            raw_dir / "19860105-20210731_odds.csv", index=False, encoding="utf-8-sig"
        )

        result = convert(raw_dir=raw_dir, standard_dir=tmp_standard_dir)

        # Read entry table - should have 7 rows (10 - 2 obstacle - 1 pre-2015)
        entry_df = pd.read_parquet(result["entry"])
        race_ids = entry_df["race_id"].unique()

        # 2014 race should NOT be present
        assert "201405050505" not in race_ids

    def test_includes_2015_and_2016_races(self, sample_race_result_df, sample_odds_df, tmp_standard_dir):
        """Rows with race_date >= 2015-01-01 are included."""
        from src.pipeline.kaggle_converter import convert

        raw_dir = tmp_standard_dir.parent / "raw" / "kaggle"
        raw_dir.mkdir(parents=True, exist_ok=True)
        sample_race_result_df.to_csv(
            raw_dir / "19860105-20210731_race_result.csv", index=False, encoding="utf-8-sig"
        )
        sample_odds_df.to_csv(
            raw_dir / "19860105-20210731_odds.csv", index=False, encoding="utf-8-sig"
        )

        result = convert(raw_dir=raw_dir, standard_dir=tmp_standard_dir)
        entry_df = pd.read_parquet(result["entry"])

        # Should include 2015 and 2016 flat races
        race_ids = set(entry_df["race_id"].unique())
        assert "201501010101" in race_ids  # 2015 flat race A
        assert "201502020202" in race_ids  # 2015 flat race B
        assert "201603030303" in race_ids  # 2016 flat race


class TestObstacleExclusion:
    """Test that obstacle races (障害区分=="障害") are excluded per D-01."""

    def test_obstacle_rows_excluded(self, sample_race_result_df, sample_odds_df, tmp_standard_dir):
        """Rows where obstacle=="障害" are not in the output."""
        from src.pipeline.kaggle_converter import convert

        raw_dir = tmp_standard_dir.parent / "raw" / "kaggle"
        raw_dir.mkdir(parents=True, exist_ok=True)
        sample_race_result_df.to_csv(
            raw_dir / "19860105-20210731_race_result.csv", index=False, encoding="utf-8-sig"
        )
        sample_odds_df.to_csv(
            raw_dir / "19860105-20210731_odds.csv", index=False, encoding="utf-8-sig"
        )

        result = convert(raw_dir=raw_dir, standard_dir=tmp_standard_dir)
        entry_df = pd.read_parquet(result["entry"])

        # Obstacle race_id should NOT be present
        assert "201504040404" not in set(entry_df["race_id"].unique())

    def test_obstacle_count_correct(self, sample_race_result_df, sample_odds_df, tmp_standard_dir):
        """After filtering, entry table has 7 rows (10 - 2 obstacle - 1 pre-2015)."""
        from src.pipeline.kaggle_converter import convert

        raw_dir = tmp_standard_dir.parent / "raw" / "kaggle"
        raw_dir.mkdir(parents=True, exist_ok=True)
        sample_race_result_df.to_csv(
            raw_dir / "19860105-20210731_race_result.csv", index=False, encoding="utf-8-sig"
        )
        sample_odds_df.to_csv(
            raw_dir / "19860105-20210731_odds.csv", index=False, encoding="utf-8-sig"
        )

        result = convert(raw_dir=raw_dir, standard_dir=tmp_standard_dir)
        entry_df = pd.read_parquet(result["entry"])

        assert len(entry_df) == 7  # 3 + 2 + 2 (flat 2015/2016 only)


class TestRaceEntryResultSplit:
    """Test the 3-way split into race/entry/result tables."""

    def test_race_table_deduplicated(self, sample_race_result_df):
        """Race table has one row per unique race_id."""
        from src.pipeline.kaggle_converter import split_race_entry_result

        # Filter first (as convert() would)
        df = sample_race_result_df[
            (sample_race_result_df["レース日付"] >= "2015-01-01") &
            (sample_race_result_df["障害区分"] != "障害")
        ].copy()

        race_df, entry_df, result_df = split_race_entry_result(df)

        # 3 unique flat race_ids: 201501010101, 201502020202, 201603030303
        assert len(race_df) == 3
        assert set(race_df["race_id"]) == {"201501010101", "201502020202", "201603030303"}

    def test_entry_table_all_rows(self, sample_race_result_df):
        """Entry table has one row per horse (all filtered rows)."""
        from src.pipeline.kaggle_converter import split_race_entry_result

        df = sample_race_result_df[
            (sample_race_result_df["レース日付"] >= "2015-01-01") &
            (sample_race_result_df["障害区分"] != "障害")
        ].copy()

        race_df, entry_df, result_df = split_race_entry_result(df)

        assert len(entry_df) == 7

    def test_result_table_all_rows(self, sample_race_result_df):
        """Result table has one row per horse (all filtered rows)."""
        from src.pipeline.kaggle_converter import split_race_entry_result

        df = sample_race_result_df[
            (sample_race_result_df["レース日付"] >= "2015-01-01") &
            (sample_race_result_df["障害区分"] != "障害")
        ].copy()

        race_df, entry_df, result_df = split_race_entry_result(df)

        assert len(result_df) == 7

    def test_entry_has_correct_columns(self, sample_race_result_df):
        """Entry table has the correct English column names from EntrySchema."""
        from src.pipeline.kaggle_converter import split_race_entry_result

        df = sample_race_result_df[
            (sample_race_result_df["レース日付"] >= "2015-01-01") &
            (sample_race_result_df["障害区分"] != "障害")
        ].copy()

        race_df, entry_df, result_df = split_race_entry_result(df)

        expected_entry_cols = {
            "horse_race_id", "race_id", "bracket_num", "horse_number",
            "horse_name", "sex", "age", "weight_assigned", "jockey", "trainer",
            "owner", "horse_weight", "weight_change", "region", "popularity",
            "win_odds",
        }
        actual_cols = set(entry_df.columns)
        assert expected_entry_cols == actual_cols, (
            f"Missing: {expected_entry_cols - actual_cols}, "
            f"Extra: {actual_cols - expected_entry_cols}"
        )


class TestFlagConversion:
    """Test that 20 flag columns convert from sparse text to Optional[bool]."""

    def test_non_empty_text_becomes_true(self):
        """Flag columns with non-empty text values become True."""
        from src.pipeline.kaggle_converter import convert_flags_to_bool

        df = pd.DataFrame({
            "race_flag_handicap": ["(ハンデ)", "", np.nan],
            "race_flag_allowance": ["(混)", "", np.nan],
            "race_flag_age_restricted": ["(馬齢)", "(馬齢)", np.nan],
        })

        result = convert_flags_to_bool(df)

        assert result["race_flag_handicap"].iloc[0] is True
        assert result["race_flag_allowance"].iloc[0] is True
        assert result["race_flag_age_restricted"].iloc[0] is True
        assert result["race_flag_age_restricted"].iloc[1] is True

    def test_empty_string_becomes_none(self):
        """Flag columns with empty string become None (pd.NA)."""
        from src.pipeline.kaggle_converter import convert_flags_to_bool

        df = pd.DataFrame({
            "race_flag_handicap": ["(ハンデ)", "", np.nan],
        })

        result = convert_flags_to_bool(df)

        assert pd.isna(result["race_flag_handicap"].iloc[1])

    def test_nan_becomes_none(self):
        """Flag columns with NaN become None (pd.NA)."""
        from src.pipeline.kaggle_converter import convert_flags_to_bool

        df = pd.DataFrame({
            "race_flag_handicap": ["(ハンデ)", "", np.nan],
        })

        result = convert_flags_to_bool(df)

        assert pd.isna(result["race_flag_handicap"].iloc[2])

    def test_all_flags_converted(self, sample_race_result_df):
        """All 20 flag columns in race table are converted to Optional[bool]."""
        from src.pipeline.kaggle_converter import split_race_entry_result

        df = sample_race_result_df[
            (sample_race_result_df["レース日付"] >= "2015-01-01") &
            (sample_race_result_df["障害区分"] != "障害")
        ].copy()

        race_df, _, _ = split_race_entry_result(df)

        # Get all flag column names (race_flag_*)
        flag_cols = [col for col in race_df.columns if col.startswith("race_flag_")]
        assert len(flag_cols) == 20

        # All flag values should be True, None, or pd.NA
        for col in flag_cols:
            for val in race_df[col]:
                assert pd.isna(val) or val is True, (
                    f"Flag column '{col}' has unexpected value: {val!r}"
                )


class TestFinishPosition:
    """Test finish position handling for normal/withdrawal/demoted cases."""

    def test_normal_finish_position(self):
        """Normal finish positions (1-18) convert to Int64 without null."""
        from src.pipeline.kaggle_converter import process_finish_position

        df = pd.DataFrame({
            "着順": [1, 2, 3],
            "着順注記": [np.nan, np.nan, np.nan],
        })

        result = process_finish_position(df)

        assert result["finish_position"].tolist() == [1, 2, 3]
        assert result["finish_note"].isna().all()

    def test_withdrawal_finish_note(self):
        """Finish note '中' (withdrawal) sets finish_position to None."""
        from src.pipeline.kaggle_converter import process_finish_position

        df = pd.DataFrame({
            "着順": [np.nan],
            "着順注記": ["中"],
        })

        result = process_finish_position(df)

        assert pd.isna(result["finish_position"].iloc[0])
        assert result["finish_note"].iloc[0] == "中"

    def test_demoted_keeps_position(self):
        """Finish note '降' (demoted) keeps original finish_position value."""
        from src.pipeline.kaggle_converter import process_finish_position

        df = pd.DataFrame({
            "着順": [2],
            "着順注記": ["降"],
        })

        result = process_finish_position(df)

        assert result["finish_position"].iloc[0] == 2
        assert result["finish_note"].iloc[0] == "降"

    def test_other_finish_notes_null_position(self):
        """Finish notes '取', '失', '除', '再' set finish_position to None."""
        from src.pipeline.kaggle_converter import process_finish_position

        for note in ["取", "失", "除", "再"]:
            df = pd.DataFrame({
                "着順": [3],
                "着順注記": [note],
            })

            result = process_finish_position(df)

            assert pd.isna(result["finish_position"].iloc[0]), (
                f"Finish note '{note}' should null finish_position"
            )
            assert result["finish_note"].iloc[0] == note


class TestOddsConversion:
    """Test odds.csv reading, filtering, and trifecta extraction."""

    def test_odds_obstacle_filter(self, sample_race_result_df, sample_odds_df):
        """Odds table filtered to only flat race_ids from race_result."""
        from src.pipeline.kaggle_converter import split_race_entry_result, extract_odds_tables

        df = sample_race_result_df[
            (sample_race_result_df["レース日付"] >= "2015-01-01") &
            (sample_race_result_df["障害区分"] != "障害")
        ].copy()

        _, entry_df, _ = split_race_entry_result(df)
        valid_race_ids = set(entry_df["race_id"].unique())

        odds_trifecta_df, payoff_df = extract_odds_tables(sample_odds_df, valid_race_ids)

        # Should NOT include obstacle race or non-existent race
        odds_race_ids = set(odds_trifecta_df["race_id"].unique())
        assert "201504040404" not in odds_race_ids  # obstacle
        assert "999999999999" not in odds_race_ids  # not in race_result

    def test_payoff_unpivot(self, sample_race_result_df, sample_odds_df):
        """Payoff table has up to 3 rows per race from trifecta1/2/3 columns."""
        from src.pipeline.kaggle_converter import split_race_entry_result, extract_odds_tables

        df = sample_race_result_df[
            (sample_race_result_df["レース日付"] >= "2015-01-01") &
            (sample_race_result_df["障害区分"] != "障害")
        ].copy()

        _, entry_df, _ = split_race_entry_result(df)
        valid_race_ids = set(entry_df["race_id"].unique())

        odds_trifecta_df, payoff_df = extract_odds_tables(sample_odds_df, valid_race_ids)

        # Payoff table should have correct columns
        assert "race_id" in payoff_df.columns
        assert "combo_1" in payoff_df.columns
        assert "combo_2" in payoff_df.columns
        assert "combo_3" in payoff_df.columns
        assert "odds" in payoff_df.columns

        # Race 201501010101 has trifecta1 data (1,2,3 combos, odds=990)
        race1_payoff = payoff_df[payoff_df["race_id"] == "201501010101"]
        assert len(race1_payoff) == 1  # only trifecta1 has data
        assert race1_payoff.iloc[0]["combo_1"] == 1
        assert race1_payoff.iloc[0]["combo_2"] == 2
        assert race1_payoff.iloc[0]["combo_3"] == 3
        assert race1_payoff.iloc[0]["odds"] == pytest.approx(99.0)  # 990 / 10

    def test_payoff_nan_rows_excluded(self, sample_race_result_df, sample_odds_df):
        """Payoff rows where all combo values are NaN are excluded."""
        from src.pipeline.kaggle_converter import split_race_entry_result, extract_odds_tables

        df = sample_race_result_df[
            (sample_race_result_df["レース日付"] >= "2015-01-01") &
            (sample_race_result_df["障害区分"] != "障害")
        ].copy()

        _, entry_df, _ = split_race_entry_result(df)
        valid_race_ids = set(entry_df["race_id"].unique())

        _, payoff_df = extract_odds_tables(sample_odds_df, valid_race_ids)

        # No rows should have NaN combo_1 (those are filtered out)
        assert payoff_df["combo_1"].notna().all()


class TestParquetOutput:
    """Test that convert() creates 5 Parquet files."""

    def test_parquet_output_exists(self, sample_race_result_df, sample_odds_df, tmp_standard_dir):
        """convert() creates 5 Parquet files in the output directory."""
        from src.pipeline.kaggle_converter import convert

        raw_dir = tmp_standard_dir.parent / "raw" / "kaggle"
        raw_dir.mkdir(parents=True, exist_ok=True)
        sample_race_result_df.to_csv(
            raw_dir / "19860105-20210731_race_result.csv", index=False, encoding="utf-8-sig"
        )
        sample_odds_df.to_csv(
            raw_dir / "19860105-20210731_odds.csv", index=False, encoding="utf-8-sig"
        )

        result = convert(raw_dir=raw_dir, standard_dir=tmp_standard_dir)

        expected_tables = ["race", "entry", "result", "odds_trifecta", "payoff"]
        for table_name in expected_tables:
            assert table_name in result, f"Missing table: {table_name}"
            assert result[table_name].exists(), f"File not created: {result[table_name]}"

    def test_audit_called_on_tables(self, sample_race_result_df, sample_odds_df, tmp_standard_dir):
        """audit_leakage() is called for race and entry tables."""
        from src.pipeline.kaggle_converter import convert

        raw_dir = tmp_standard_dir.parent / "raw" / "kaggle"
        raw_dir.mkdir(parents=True, exist_ok=True)
        sample_race_result_df.to_csv(
            raw_dir / "19860105-20210731_race_result.csv", index=False, encoding="utf-8-sig"
        )
        sample_odds_df.to_csv(
            raw_dir / "19860105-20210731_odds.csv", index=False, encoding="utf-8-sig"
        )

        with patch("src.pipeline.kaggle_converter.audit_leakage") as mock_audit:
            mock_audit.return_value = []
            convert(raw_dir=raw_dir, standard_dir=tmp_standard_dir)

            # audit_leakage should have been called at least twice (race, entry)
            assert mock_audit.call_count >= 2

            # Check that it was called with model classes and DataFrames
            for call in mock_audit.call_args_list:
                args, kwargs = call
                assert len(args) >= 2  # model_classes and df
