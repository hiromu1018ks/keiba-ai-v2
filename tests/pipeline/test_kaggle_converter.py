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

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from src.schemas.race import RaceSchema


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
        race_ids = set(str(rid) for rid in entry_df["race_id"].unique())
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
        # 20 CSV flag columns coalesce into 12 unique schema fields (the (国際)
        # column no longer maps to graded_stakes per Phase 6 D-01)
        # + 8 unmapped flags (incl. graded_stakes, now regex-derived) = 20 total.
        assert len(flag_cols) == 20

        # Phase 6 D-01: the 3 grade-derived columns (graded_stakes, stakes,
        # listed) are produced by _apply_grade_detection via an OR-merge that
        # fills NA with False before merging, so non-graded rows can have a
        # concrete False (not just True/NA). The other 17 flags stay True/NA.
        grade_derived = {
            "race_flag_graded_stakes", "race_flag_stakes", "race_flag_listed",
        }
        for col in flag_cols:
            for val in race_df[col]:
                if col in grade_derived:
                    # Allow True, False, or NA for grade-derived columns.
                    assert pd.isna(val) or bool(val) in (True, False), (
                        f"Grade-derived flag '{col}' has unexpected value: {val!r}"
                    )
                else:
                    # Text-derived flags: only True or NA (never False).
                    assert pd.isna(val) or bool(val) is True, (
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


class TestGradeDetection:
    """HIGH #1 cycle-3: Kaggle-side grade detection via derive_race_flags.

    After D-01 removes the レース記号/(国際) -> race_flag_graded_stakes mapping,
    graded detection on the Kaggle side comes from _GRADE_REGEX (GI/GII/GIII/
    G1/G2/G3/JG*/重賞/ＧＩ...) via src.scraper.flag_crosswalk.derive_race_flags,
    invoked by kaggle_converter._apply_grade_detection AFTER the
    _UNMAPPED_RACE_FLAGS loop.
    """

    def test_kaggle_graded_derivation_matches_regex(self) -> None:
        """grade='G1' (half-width) sets graded_stakes=True via _GRADE_REGEX.

        HIGH #1 cycle-3: the cycle-2 test used grade='GⅠ' (half-width G + FULL-
        WIDTH Ⅰ U+FF21) which matched NEITHER the half-width 'GI' nor the
        full-width 'ＧＩ' alternatives in _GRADE_REGEX and was silently
        undetected. 'G1' matches the 'G3|G2|G1' alternation.
        """
        from src.pipeline.kaggle_converter import _apply_grade_detection

        race_df = pd.DataFrame({
            "grade": ["G1", None, None],
            "race_name": ["普通レース", "(国際)特別", "東京優駿(G1)"],
            # All 20 race_flag_* must exist (helper runs AFTER unmapped loop).
            **{
                f"race_flag_{n}": pd.NA
                for n in [
                    "handicap", "age_restricted", "filly_only", "colt_only",
                    "gelding_only", "mare_only", "stallion_only", "apprentice",
                    "amateur", "female_jockey", "young_horse", "condition_race",
                    "special_weight", "bonus_weight", "stakes", "graded_stakes",
                    "listed", "open", "maiden", "allowance",
                ]
            },
        })
        for col in race_df.columns:
            if col.startswith("race_flag_"):
                race_df[col] = race_df[col].astype("boolean")

        out = _apply_grade_detection(race_df.copy())

        # Row 0: grade='G1' -> graded_stakes=True (matches G3|G2|G1)
        assert bool(out["race_flag_graded_stakes"].iloc[0]) is True, (
            f"grade='G1' should set graded_stakes=True; got "
            f"{out['race_flag_graded_stakes'].iloc[0]!r}"
        )
        # Row 1: grade=None, race_name='(国際)特別' -> NOT graded ((国際) is not
        # a graded marker; only GI/G1/etc are). graded_stakes in {None, False}.
        v1 = out["race_flag_graded_stakes"].iloc[1]
        assert pd.isna(v1) or bool(v1) is False, (
            f"grade=None + '(国際)特別' must NOT be graded; got {v1!r}"
        )
        # Row 2: grade=None, race_name='東京優駿(G1)' -> STILL graded (proves the
        # race_condition=' ' bypass of derive_race_flags' early-return guard
        # works — the GI token in race_name alone triggers _GRADE_REGEX).
        assert bool(out["race_flag_graded_stakes"].iloc[2]) is True, (
            f"race_name='東京優駿(G1)' with grade=null should STILL be graded "
            f"(race_condition=' ' bypass); got "
            f"{out['race_flag_graded_stakes'].iloc[2]!r}"
        )

    def test_kaggle_bare_grade_L_detected_as_listed_and_stakes(self) -> None:
        """CR-01: grade='L' (bare, no parentheses) sets listed=True and stakes=True.

        Kaggle's リステッド・重賞競走 column stores the bare token "L" for
        Listed races (2,232 entry-rows 2015+ verified against the real CSV).
        _LISTED_REGEX in flag_crosswalk.py requires "(L)"/"（L）"/"(リステッド)"
        with PARENTHESES, so a bare L matches NEITHER _LISTED_REGEX nor
        _STAKES_REGEX and was previously misclassified as
        listed=False/stakes=False. _apply_grade_detection now classifies the
        bare token directly (the L is unambiguous only as a top-level grade
        token, not inside race_name).
        """
        from src.pipeline.kaggle_converter import _apply_grade_detection

        race_df = pd.DataFrame({
            "grade": ["L", None],
            "race_name": ["テストリステッド", "普通レース"],
            **{
                f"race_flag_{n}": pd.NA
                for n in [
                    "handicap", "age_restricted", "filly_only", "colt_only",
                    "gelding_only", "mare_only", "stallion_only", "apprentice",
                    "amateur", "female_jockey", "young_horse", "condition_race",
                    "special_weight", "bonus_weight", "stakes", "graded_stakes",
                    "listed", "open", "maiden", "allowance",
                ]
            },
        })
        for col in race_df.columns:
            if col.startswith("race_flag_"):
                race_df[col] = race_df[col].astype("boolean")

        out = _apply_grade_detection(race_df.copy())

        # Row 0: grade='L' -> listed=True AND stakes=True (a Listed race is a stakes)
        assert bool(out["race_flag_listed"].iloc[0]) is True, (
            f"grade='L' should set race_flag_listed=True (CR-01); got "
            f"{out['race_flag_listed'].iloc[0]!r}"
        )
        assert bool(out["race_flag_stakes"].iloc[0]) is True, (
            f"grade='L' should set race_flag_stakes=True (a Listed race is a "
            f"stakes); got {out['race_flag_stakes'].iloc[0]!r}"
        )
        # A Listed race is NOT graded (G1/G2/G3). graded_stakes stays False/NA.
        v0 = out["race_flag_graded_stakes"].iloc[0]
        assert pd.isna(v0) or bool(v0) is False, (
            f"grade='L' must NOT set race_flag_graded_stakes (Listed != graded); "
            f"got {v0!r}"
        )
        # Row 1: grade=None -> no listed token. The OR-merge uses fillna(False)
        # on both sides (see _apply_grade_detection docstring), so a non-Listed
        # row gets a concrete False, NOT NA. Assert listed is falsy (False/NA).
        v1 = out["race_flag_listed"].iloc[1]
        assert pd.isna(v1) or bool(v1) is False, (
            f"grade=None should NOT set race_flag_listed; got {v1!r}"
        )

    def test_kaggle_bare_grade_G_detected_as_graded_and_stakes(self) -> None:
        """CR-02: bare grade='G' (110 Kaggle entry-rows) sets graded_stakes + stakes.

        Kaggle stores the bare token "G" for 110 graded/stakes races where the
        actual G1/G2/G3 level is encoded in race_name (e.g. ターコイズステークス,
        葵ステークス). _GRADE_REGEX requires 2+ chars (GI/G1/...), so a bare G
        matched neither _GRADE_REGEX nor _STAKES_REGEX and was previously
        misclassified as graded_stakes=False/stakes=False.
        """
        from src.pipeline.kaggle_converter import _apply_grade_detection

        race_df = pd.DataFrame({
            "grade": ["G", None],
            "race_name": ["ターコイズステークス", "普通レース"],
            **{
                f"race_flag_{n}": pd.NA
                for n in [
                    "handicap", "age_restricted", "filly_only", "colt_only",
                    "gelding_only", "mare_only", "stallion_only", "apprentice",
                    "amateur", "female_jockey", "young_horse", "condition_race",
                    "special_weight", "bonus_weight", "stakes", "graded_stakes",
                    "listed", "open", "maiden", "allowance",
                ]
            },
        })
        for col in race_df.columns:
            if col.startswith("race_flag_"):
                race_df[col] = race_df[col].astype("boolean")

        out = _apply_grade_detection(race_df.copy())

        # Row 0: grade='G' -> graded_stakes=True AND stakes=True
        assert bool(out["race_flag_graded_stakes"].iloc[0]) is True, (
            f"grade='G' should set race_flag_graded_stakes=True (CR-02); got "
            f"{out['race_flag_graded_stakes'].iloc[0]!r}"
        )
        assert bool(out["race_flag_stakes"].iloc[0]) is True, (
            f"grade='G' should set race_flag_stakes=True (a graded stakes is a "
            f"stakes); got {out['race_flag_stakes'].iloc[0]!r}"
        )

    def test_grade_detection_preserves_existing_true(self) -> None:
        """WARNING-2: OR-merge never downgrades an existing True to None.

        Case A: convert_flags_to_bool already set race_flag_stakes=True for a
        row, and derive_race_flags returns None for that column (no grade
        token on this row). After _apply_grade_detection, the column STILL
        has True for that row.

        Case B (inverse): convert_flags_to_bool left race_flag_graded_stakes
        as None, and derive_race_flags returns True; after the helper, the
        column has True.
        """
        from src.pipeline.kaggle_converter import _apply_grade_detection

        # Row 0: existing stakes=True, grade has no token -> derive returns
        # None for stakes -> merge must preserve True.
        # Row 1: existing graded_stakes=None, grade='G1' -> derive returns
        # True for graded -> merge must produce True.
        race_df = pd.DataFrame({
            "grade": [None, "G1"],
            "race_name": ["普通レース", "重賞"],
            "race_flag_stakes": pd.array([True, pd.NA], dtype="boolean"),
            "race_flag_graded_stakes": pd.array([pd.NA, pd.NA], dtype="boolean"),
            "race_flag_listed": pd.array([pd.NA, pd.NA], dtype="boolean"),
        })
        out = _apply_grade_detection(race_df.copy())
        # Case A: existing True preserved despite new None.
        assert bool(out["race_flag_stakes"].iloc[0]) is True, (
            f"OR-merge downgraded existing stakes=True to {out['race_flag_stakes'].iloc[0]!r}"
        )
        # Case B: new True merged onto existing None.
        assert bool(out["race_flag_graded_stakes"].iloc[1]) is True, (
            f"OR-merge failed to set graded_stakes=True from grade='G1'; "
            f"got {out['race_flag_graded_stakes'].iloc[1]!r}"
        )
        # Case B also: grade='G1' sets BOTH graded_stakes AND stakes (a graded
        # stakes is by definition a stakes).
        assert bool(out["race_flag_stakes"].iloc[1]) is True, (
            f"grade='G1' should set stakes=True too; got "
            f"{out['race_flag_stakes'].iloc[1]!r}"
        )

    def test_apply_grade_detection_runs_after_unmapped_flags(self) -> None:
        """HIGH #1 cycle-3 ordering regression guard.

        After split_race_entry_result returns, the grade-derived True values
        for race_flag_stakes and race_flag_listed must be present (not
        clobbered to pd.NA by the _UNMAPPED_RACE_FLAGS loop). This guards
        against a future refactor moving _apply_grade_detection back to line
        ~248 (before the unmapped loop writes pd.NA over these columns).
        """
        from src.pipeline.kaggle_converter import split_race_entry_result

        # Build a tiny raw-style DataFrame with a grade token.
        data = {
            "レース馬番ID": ["R01", "R02"],
            "レースID": ["202001010101", "202001010102"],
            "レース日付": ["2020-01-01", "2020-01-01"],
            "開催回数": [1, 1],
            "競馬場コード": ["01", "02"],
            "競馬場名": ["東京", "中山"],
            "開催日数": [1, 1],
            "競争条件": ["3歳オープン", "4歳以上1000万下"],
            "レース番号": [1, 2],
            "重賞回次": [np.nan, np.nan],
            "レース名": ["テストG1", "テストリステッド"],
            "リステッド・重賞競走": ["G1", np.nan],  # grade column
            "障害区分": ["", ""],
            "芝・ダート区分": ["芝", "芝"],
            "芝・ダート区分2": [np.nan, np.nan],
            "右左回り・直線区分": ["左", "右"],
            "内・外・襷区分": [np.nan, np.nan],
            "距離(m)": [2000, 1600],
            "天候": ["晴", "晴"],
            "馬場状態1": ["良", "良"],
            "馬場状態2": [np.nan, np.nan],
            "発走時刻": ["10:00", "11:00"],
            "着順": [1, 1],
            "着順注記": [np.nan, np.nan],
            "枠番": [1, 1],
            "馬番": [1, 1],
            "馬名": ["馬A", "馬B"],
            "性別": ["牡", "牝"],
            "馬齢": [4, 4],
            "斤量": [57.0, 55.0],
            "騎手": ["騎手A", "騎手B"],
            "タイム": ["1:58.0", "1:35.0"],
            "着差": ["", ""],
            "1コーナー": [1, 1],
            "2コーナー": [1, 1],
            "3コーナー": [1, 1],
            "4コーナー": [1, 1],
            "上り": [34.0, 34.5],
            "単勝": [2.0, 3.0],
            "人気": [1, 2],
            "馬体重": [480, 460],
            "場体重増減": [0, 0],
            "東西・外国・地方区分": ["東", "西"],
            "調教師": ["調X", "調Y"],
            "馬主": ["主A", "主B"],
            "賞金(万円)": [100.0, 100.0],
        }
        # Add all 20 flag columns as empty strings (no text-derived flags).
        from src.pipeline.column_mapping import FLAG_COLUMNS
        for fc in FLAG_COLUMNS:
            data[fc] = ["", ""]
        df = pd.DataFrame(data)

        race_df, _, _ = split_race_entry_result(df)

        # After grade detection: race 0 (grade='G1') has graded_stakes=True
        # AND stakes=True (these columns come from _UNMAPPED_RACE_FLAGS, so
        # this asserts the helper ran AFTER that loop, not before).
        row0 = race_df[race_df["race_id"] == "202001010101"].iloc[0]
        assert bool(row0["race_flag_graded_stakes"]) is True, (
            f"grade='G1' row should have graded_stakes=True after "
            f"_apply_grade_detection (ran after unmapped loop); got "
            f"{row0['race_flag_graded_stakes']!r}"
        )
        assert bool(row0["race_flag_stakes"]) is True, (
            f"grade='G1' row should have stakes=True (graded => stakes); "
            f"got {row0['race_flag_stakes']!r}"
        )
        # race_flag_listed must EXIST as a column (KeyError guard) and be NA
        # for the G1 row (no (L)/(リステッド) token).
        assert "race_flag_listed" in race_df.columns, (
            "race_flag_listed column missing — _apply_grade_detection ran "
            "before _UNMAPPED_RACE_FLAGS added it (HIGH #1 cycle-3 regression)"
        )


class TestRecastAndDtypes:
    """Phase 6 D-02: _recast_to_canonical + regenerated Parquet dtypes."""

    def test_recast_raises_on_bad_data(self) -> None:
        """A non-coercible value (distance='abc') raises TypeError, not silent."""
        from src.pipeline.kaggle_converter import _recast_to_canonical

        df = pd.DataFrame({"distance": ["abc", "2000"], "race_id": ["X", "Y"]})
        with pytest.raises(TypeError, match="distance"):
            _recast_to_canonical(df, RaceSchema)

    def test_kaggle_parquet_post_d02_has_typed_flags(self) -> None:
        """Regenerated data/standard/kaggle/race.parquet has zero Arrow-null cols.

        HIGH #4 dtype: every race_flag_* column must be Arrow bool (not null).
        """
        import pyarrow.parquet as pq
        from pathlib import Path

        race_path = Path("data/standard/kaggle/race.parquet")
        if not race_path.exists():
            pytest.skip("data/standard/kaggle/race.parquet not regenerated yet")
        schema = pq.read_schema(race_path)
        null_cols = [f.name for f in schema if str(f.type) == "null"]
        assert null_cols == [], f"Arrow-null cols remain: {null_cols}"
        flag_fields = [f for f in schema if f.name.startswith("race_flag_")]
        assert len(flag_fields) >= 1, "no race_flag_* columns found"
        for f in flag_fields:
            assert str(f.type) == "bool", (
                f"{f.name} type={f.type} (expected bool)"
            )

    def test_kaggle_race_distance_is_int64(self) -> None:
        """distance column is Arrow int64 (D-02)."""
        import pyarrow.parquet as pq
        from pathlib import Path

        race_path = Path("data/standard/kaggle/race.parquet")
        if not race_path.exists():
            pytest.skip("data/standard/kaggle/race.parquet not regenerated yet")
        schema = pq.read_schema(race_path)
        dist = [f for f in schema if f.name == "distance"]
        assert len(dist) == 1, f"distance field count={len(dist)}"
        assert str(dist[0].type) == "int64", (
            f"distance type={dist[0].type} (expected int64)"
        )

    def test_kaggle_race_date_is_string(self) -> None:
        """race_date column is Arrow string (MEDIUM #5 — string, NOT datetime)."""
        import pyarrow.parquet as pq
        from pathlib import Path

        race_path = Path("data/standard/kaggle/race.parquet")
        if not race_path.exists():
            pytest.skip("data/standard/kaggle/race.parquet not regenerated yet")
        schema = pq.read_schema(race_path)
        rd = [f for f in schema if f.name == "race_date"]
        assert len(rd) == 1
        assert str(rd[0].type) == "string", (
            f"race_date type={rd[0].type} (expected string per MEDIUM #5)"
        )


class TestCoreTablesSubdir:
    """BLOCKER-1 + HIGH #2 cycle-3: core_tables_subdir redirect + odds/payoff SKIP."""

    def _write_sample_raw(self, tmp_path, sample_race_result_df, sample_odds_df):
        raw_dir = tmp_path / "raw" / "kaggle"
        raw_dir.mkdir(parents=True, exist_ok=True)
        sample_race_result_df.to_csv(
            raw_dir / "19860105-20210731_race_result.csv",
            index=False, encoding="utf-8-sig",
        )
        sample_odds_df.to_csv(
            raw_dir / "19860105-20210731_odds.csv",
            index=False, encoding="utf-8-sig",
        )
        return raw_dir

    def test_convert_writes_core_tables_to_subdir(
        self, sample_race_result_df, sample_odds_df, tmp_path,
    ):
        """BLOCKER-1: core_tables_subdir='kaggle' writes race/entry/result to subdir.

        Also verifies the root-level race.parquet is NOT created (redirect).
        """
        from src.pipeline.kaggle_converter import convert

        raw_dir = self._write_sample_raw(tmp_path, sample_race_result_df, sample_odds_df)
        standard_dir = tmp_path / "standard"
        standard_dir.mkdir(parents=True, exist_ok=True)

        result = convert(
            raw_dir=raw_dir, standard_dir=standard_dir,
            core_tables_subdir="kaggle",
        )

        # race/entry/result went to subdir.
        for tbl in ("race", "entry", "result"):
            assert tbl in result, f"{tbl} missing from output_paths"
            sub_path = standard_dir / "kaggle" / f"{tbl}.parquet"
            assert sub_path.exists(), f"subdir file not created: {sub_path}"
            assert result[tbl] == sub_path
        # root-level race.parquet NOT created (redirect).
        assert not (standard_dir / "race.parquet").exists(), (
            "root race.parquet should NOT exist when core_tables_subdir is set"
        )
        # output_paths has NO odds/payoff keys (they were skipped).
        assert "odds_trifecta" not in result, (
            "odds_trifecta should NOT be in output_paths when subdir is set"
        )
        assert "payoff" not in result, (
            "payoff should NOT be in output_paths when subdir is set"
        )

    def test_convert_skips_odds_payoff_when_subdir_set(
        self, sample_race_result_df, sample_odds_df, tmp_path,
    ):
        """HIGH #2 cycle-3 explicit SKIP: odds/payoff absent from empty tmp dir.

        Into an EMPTY standard_dir (no pre-existing odds/payoff), invoke
        convert(core_tables_subdir='kaggle'). After: odds_trifecta.parquet and
        payoff.parquet do NOT exist at the root (proves SKIP, not just
        non-overwrite of pre-existing files).
        """
        from src.pipeline.kaggle_converter import convert

        raw_dir = self._write_sample_raw(tmp_path, sample_race_result_df, sample_odds_df)
        standard_dir = tmp_path / "standard"
        standard_dir.mkdir(parents=True, exist_ok=True)

        convert(
            raw_dir=raw_dir, standard_dir=standard_dir,
            core_tables_subdir="kaggle",
        )

        assert not (standard_dir / "odds_trifecta.parquet").exists(), (
            "odds_trifecta.parquet must NOT exist in empty dir after subdir invocation"
        )
        assert not (standard_dir / "payoff.parquet").exists(), (
            "payoff.parquet must NOT exist in empty dir after subdir invocation"
        )

    def test_convert_preserves_odds_payoff(
        self, sample_race_result_df, sample_odds_df, tmp_path,
    ):
        """HIGH #2 cycle-3 NON-OVERWRITE: sentinel odds/payoff bytes UNCHANGED.

        Pre-write distinctive sentinel odds_trifecta.parquet + payoff.parquet
        with a marker row. Invoke convert(core_tables_subdir='kaggle'). After:
        (a) sentinel files' SHA-256 AND row count IDENTICAL (NON-OVERWRITE —
        convert did not touch them at all); (b) kaggle/ subdir race/entry/result
        exist and are non-empty; (c) root race.parquet does NOT exist.
        """
        import hashlib
        from src.pipeline.kaggle_converter import convert

        raw_dir = self._write_sample_raw(tmp_path, sample_race_result_df, sample_odds_df)
        standard_dir = tmp_path / "standard"
        standard_dir.mkdir(parents=True, exist_ok=True)

        # Write distinctive sentinel odds/payoff with a marker row.
        sentinel_odds = pd.DataFrame({
            "race_id": ["SENTINEL_ODDS_999"],
            "trifecta1_combo_1": [11], "trifecta1_combo_2": [22], "trifecta1_combo_3": [33],
            "trifecta1_odds": [123.4], "trifecta1_popularity": [1],
            "trifecta2_combo_1": [1], "trifecta2_combo_2": [2], "trifecta2_combo_3": [3],
            "trifecta2_odds": [456.7], "trifecta2_popularity": [2],
            "trifecta3_combo_1": [4], "trifecta3_combo_2": [5], "trifecta3_combo_3": [6],
            "trifecta3_odds": [789.0], "trifecta3_popularity": [3],
        })
        sentinel_payoff = pd.DataFrame({
            "race_id": ["SENTINEL_PAYOFF_999"],
            "combo_1": [11], "combo_2": [22], "combo_3": [33],
            "odds": [123.4], "payoff_amount": [None],
        })
        odds_path = standard_dir / "odds_trifecta.parquet"
        payoff_path = standard_dir / "payoff.parquet"
        sentinel_odds.to_parquet(odds_path, engine="pyarrow", index=False)
        sentinel_payoff.to_parquet(payoff_path, engine="pyarrow", index=False)

        def sha256(p):
            return hashlib.sha256(p.read_bytes()).hexdigest()

        odds_sha_pre = sha256(odds_path)
        payoff_sha_pre = sha256(payoff_path)
        odds_rows_pre = len(pd.read_parquet(odds_path))
        payoff_rows_pre = len(pd.read_parquet(payoff_path))

        convert(
            raw_dir=raw_dir, standard_dir=standard_dir,
            core_tables_subdir="kaggle",
        )

        # (a) NON-OVERWRITE: SHA-256 AND row count unchanged.
        assert sha256(odds_path) == odds_sha_pre, (
            "odds_trifecta.parquet SHA-256 changed — convert overwrote it "
            "(HIGH #2 cycle-3 violation)"
        )
        assert sha256(payoff_path) == payoff_sha_pre, (
            "payoff.parquet SHA-256 changed — convert overwrote it "
            "(HIGH #2 cycle-3 violation)"
        )
        assert len(pd.read_parquet(odds_path)) == odds_rows_pre
        assert len(pd.read_parquet(payoff_path)) == payoff_rows_pre

        # (b) subdir race/entry/result exist and are non-empty.
        for tbl in ("race", "entry", "result"):
            sub_path = standard_dir / "kaggle" / f"{tbl}.parquet"
            assert sub_path.exists(), f"subdir {tbl}.parquet not created"
            assert len(pd.read_parquet(sub_path)) > 0, f"subdir {tbl}.parquet empty"

        # (c) root race.parquet does NOT exist.
        assert not (standard_dir / "race.parquet").exists()

    def test_convert_default_writes_all_5_tables_to_root(
        self, sample_race_result_df, sample_odds_df, tmp_path,
    ):
        """Backwards-compat: default invocation (no subdir) writes all 5 tables.

        Phase 2 behavior is preserved: convert(..., standard_dir=X) with no
        core_tables_subdir writes race/entry/result AND odds_trifecta/payoff
        to X/'{table}.parquet'.
        """
        from src.pipeline.kaggle_converter import convert

        raw_dir = self._write_sample_raw(tmp_path, sample_race_result_df, sample_odds_df)
        standard_dir = tmp_path / "standard"
        standard_dir.mkdir(parents=True, exist_ok=True)

        result = convert(raw_dir=raw_dir, standard_dir=standard_dir)

        for tbl in ("race", "entry", "result", "odds_trifecta", "payoff"):
            assert tbl in result, f"{tbl} missing from output_paths (default path)"
            assert result[tbl].exists(), f"{tbl}.parquet not created (default path)"
            # All at root, NOT in a subdir.
            assert result[tbl] == standard_dir / f"{tbl}.parquet"
