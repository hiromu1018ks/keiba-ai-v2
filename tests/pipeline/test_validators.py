"""Tests for data quality validation functions (D-05 checks).

Covers all 8 validators + run_all_validations orchestrator:
1. validate_row_counts
2. validate_schema_conformance
3. validate_audit
4. validate_null_rates
5. validate_distributions
6. validate_referential_integrity
7. validate_sample_rows
8. validate_value_ranges
9. run_all_validations
"""

from pathlib import Path

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Fixtures for validator tests
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_parquet_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with 5 Parquet files for validator tests.

    Tables and row counts:
    - race: 2 rows (race_ids: 201501010101, 201502020202)
    - entry: 5 rows (3 horses in race 1, 2 in race 2)
    - result: 5 rows (1:1 with entry)
    - odds_trifecta: 2 rows (one per race)
    - payoff: 3 rows (2 combos for race 1, 1 combo for race 2)
    """
    parquet_dir = tmp_path / "standard"
    parquet_dir.mkdir(parents=True, exist_ok=True)

    race_df = pd.DataFrame({
        "race_id": ["201501010101", "201502020202"],
        "race_date": ["2015-01-05", "2015-02-10"],
        "meeting_num": [1, 2],
        "course_code": ["01", "02"],
        "course_name": ["Tokyo", "Nakayama"],
        "meeting_day": [1, 2],
        "race_condition": ["4up1000", "3yo500"],
        "race_number": [1, 5],
        "grade_revision": [None, None],
        "race_name": ["Race A", "Race B"],
        "grade": [None, None],
        "obstacle": [None, None],
        "surface": ["Turf", "Dirt"],
        "surface_detail": [None, None],
        "direction": ["Right", "Left"],
        "course_detail": [None, None],
        "distance": [2000, 1400],
        "weather": ["Fine", "Cloudy"],
        "track_condition": ["Good", "Yielding"],
        "track_condition_detail": [None, None],
        "start_time": ["10:00", "11:30"],
        "race_flag_handicap": pd.array([None, True], dtype="boolean"),
        "race_flag_age_restricted": pd.array([True, None], dtype="boolean"),
        "race_flag_filly_only": pd.array([None, None], dtype="boolean"),
        "race_flag_colt_only": pd.array([None, None], dtype="boolean"),
        "race_flag_gelding_only": pd.array([None, None], dtype="boolean"),
        "race_flag_mare_only": pd.array([None, None], dtype="boolean"),
        "race_flag_stallion_only": pd.array([None, None], dtype="boolean"),
        "race_flag_apprentice": pd.array([None, None], dtype="boolean"),
        "race_flag_amateur": pd.array([None, None], dtype="boolean"),
        "race_flag_female_jockey": pd.array([None, None], dtype="boolean"),
        "race_flag_young_horse": pd.array([None, None], dtype="boolean"),
        "race_flag_condition_race": pd.array([None, None], dtype="boolean"),
        "race_flag_special_weight": pd.array([None, None], dtype="boolean"),
        "race_flag_bonus_weight": pd.array([None, None], dtype="boolean"),
        "race_flag_stakes": pd.array([None, None], dtype="boolean"),
        "race_flag_graded_stakes": pd.array([None, None], dtype="boolean"),
        "race_flag_listed": pd.array([None, None], dtype="boolean"),
        "race_flag_open": pd.array([None, None], dtype="boolean"),
        "race_flag_maiden": pd.array([None, None], dtype="boolean"),
        "race_flag_allowance": pd.array([None, None], dtype="boolean"),
    })

    entry_df = pd.DataFrame({
        "horse_race_id": ["20150101010101", "20150101010102", "20150101010103",
                          "20150202020204", "20150202020205"],
        "race_id": ["201501010101", "201501010101", "201501010101",
                     "201502020202", "201502020202"],
        "bracket_num": [1, 2, 3, 1, 4],
        "horse_number": [1, 2, 3, 4, 5],
        "horse_name": ["Horse A", "Horse B", "Horse C", "Horse D", "Horse E"],
        "sex": ["Colt", "Filly", "Colt", "Gelding", "Colt"],
        "age": [4, 3, 5, 4, 3],
        "weight_assigned": [57.0, 55.0, 57.0, 57.0, 54.0],
        "jockey": ["Jockey A", "Jockey B", "Jockey C", "Jockey D", "Jockey E"],
        "trainer": ["Trainer A", "Trainer B", "Trainer C", "Trainer D", "Trainer E"],
        "owner": ["Owner A", "Owner B", "Owner C", "Owner D", "Owner E"],
        "horse_weight": [480, 460, 500, 510, 470],
        "weight_change": [2, -3, 0, 5, -1],
        "region": ["East", "East", "East", "West", "West"],
        "popularity": [1, 2, 3, 2, 4],
        "win_odds": [2.1, 3.5, 5.0, 4.2, 6.8],
    })

    result_df = pd.DataFrame({
        "horse_race_id": ["20150101010101", "20150101010102", "20150101010103",
                          "20150202020204", "20150202020205"],
        "race_id": ["201501010101", "201501010101", "201501010101",
                     "201502020202", "201502020202"],
        "finish_position": [1, 2, 3, 1, 2],
        "finish_note": [None, None, None, None, None],
        "finish_time": ["1:58.5", "1:58.8", "1:59.1", "1:23.4", "1:23.7"],
        "margin": [None, "3/4", "1.1/2", None, "1.3/4"],
        "corner_1": [1, 3, 2, 2, 1],
        "corner_2": [1, 3, 2, 2, 1],
        "corner_3": [1, 2, 3, 1, 2],
        "corner_4": [1, 2, 3, 1, 2],
        "last_3f": [34.5, 34.8, 35.0, 33.2, 33.5],
        "prize_money": [750.0, 300.0, 190.0, 500.0, 200.0],
    })

    odds_trifecta_df = pd.DataFrame({
        "race_id": ["201501010101", "201502020202"],
        "trifecta1_combo_1": pd.array([1, 4], dtype="Int64"),
        "trifecta1_combo_2": pd.array([2, 5], dtype="Int64"),
        "trifecta1_combo_3": pd.array([3, None], dtype="Int64"),
        "trifecta1_odds": pd.array([990, 1500], dtype="Int64"),
        "trifecta1_popularity": pd.array([1, 1], dtype="Int64"),
        "trifecta2_combo_1": pd.array([None, None], dtype="Int64"),
        "trifecta2_combo_2": pd.array([None, None], dtype="Int64"),
        "trifecta2_combo_3": pd.array([None, None], dtype="Int64"),
        "trifecta2_odds": pd.array([None, None], dtype="Int64"),
        "trifecta2_popularity": pd.array([None, None], dtype="Int64"),
        "trifecta3_combo_1": pd.array([None, None], dtype="Int64"),
        "trifecta3_combo_2": pd.array([None, None], dtype="Int64"),
        "trifecta3_combo_3": pd.array([None, None], dtype="Int64"),
        "trifecta3_odds": pd.array([None, None], dtype="Int64"),
        "trifecta3_popularity": pd.array([None, None], dtype="Int64"),
    })

    payoff_df = pd.DataFrame({
        "race_id": ["201501010101", "201501010101", "201502020202"],
        "combo_1": [1, 2, 4],
        "combo_2": [2, 3, 5],
        "combo_3": [3, 1, 6],
        "odds": [99.0, 150.0, 150.0],
        "payoff_amount": pd.array([None, None, None], dtype="Int64"),
    })

    for name, df in [
        ("race", race_df),
        ("entry", entry_df),
        ("result", result_df),
        ("odds_trifecta", odds_trifecta_df),
        ("payoff", payoff_df),
    ]:
        df.to_parquet(parquet_dir / f"{name}.parquet", engine="pyarrow", index=False)

    return parquet_dir


@pytest.fixture
def source_counts() -> dict[str, int]:
    """Expected row counts matching sample_parquet_dir."""
    return {
        "race": 2,
        "entry": 5,
        "result": 5,
        "odds_trifecta": 2,
        "payoff": 3,
    }


@pytest.fixture
def sample_source_stats() -> dict:
    """Sample source statistics for null rate and distribution checks."""
    return {
        "entry": {
            "null_rates": {
                "popularity": 0.0,
                "win_odds": 0.0,
                "horse_weight": 0.0,
                "weight_change": 0.0,
                "region": 0.0,
            },
            "distributions": {
                "age": {"min": 3, "max": 5, "mean": 3.8},
                "weight_assigned": {"min": 54.0, "max": 57.0, "mean": 56.0},
            },
        },
    }


# ---------------------------------------------------------------------------
# Test 1: validate_row_counts
# ---------------------------------------------------------------------------

class TestValidateRowCounts:
    """Tests for validate_row_counts function."""

    def test_matching_counts_return_true(
        self, sample_parquet_dir: Path, source_counts: dict[str, int]
    ) -> None:
        """All tables with matching counts return True."""
        from src.pipeline.validators import validate_row_counts

        result = validate_row_counts(source_counts, sample_parquet_dir)
        assert all(result.values()), f"Expected all True, got {result}"

    def test_mismatched_count_returns_false(
        self, sample_parquet_dir: Path
    ) -> None:
        """Table with wrong expected count returns False."""
        from src.pipeline.validators import validate_row_counts

        wrong_counts = {"race": 999, "entry": 5}
        result = validate_row_counts(wrong_counts, sample_parquet_dir)
        assert result["race"] is False
        assert result["entry"] is True

    def test_missing_parquet_file_returns_false(
        self, tmp_path: Path
    ) -> None:
        """Table with missing Parquet file returns False."""
        from src.pipeline.validators import validate_row_counts

        empty_dir = tmp_path / "standard"
        empty_dir.mkdir()
        result = validate_row_counts({"race": 2}, empty_dir)
        assert result["race"] is False


# ---------------------------------------------------------------------------
# Test 2: validate_schema_conformance
# ---------------------------------------------------------------------------

class TestValidateSchemaConformance:
    """Tests for validate_schema_conformance function."""

    def test_conformant_schema_passes(self, sample_parquet_dir: Path) -> None:
        """Parquet files with correct columns and dtypes produce no errors."""
        from src.pipeline.validators import validate_schema_conformance

        result = validate_schema_conformance(sample_parquet_dir)
        for table_name, errors in result.items():
            assert errors == [], f"{table_name} has errors: {errors}"

    def test_missing_column_reported(self, tmp_path: Path) -> None:
        """Parquet file missing a schema column reports an error."""
        from src.pipeline.validators import validate_schema_conformance

        parquet_dir = tmp_path / "standard"
        parquet_dir.mkdir()
        # Create a race.parquet missing required columns
        bad_df = pd.DataFrame({"race_id": ["001"], "race_date": ["2020-01-01"]})
        bad_df.to_parquet(parquet_dir / "race.parquet", engine="pyarrow", index=False)

        result = validate_schema_conformance(parquet_dir)
        assert len(result["race"]) > 0, "Expected errors for missing columns"


# ---------------------------------------------------------------------------
# Test 3: validate_audit
# ---------------------------------------------------------------------------

class TestValidateAudit:
    """Tests for validate_audit function."""

    def test_race_table_no_leaked_columns(self, sample_parquet_dir: Path) -> None:
        """Race table (all pre-race) should have no leaked columns."""
        from src.pipeline.validators import validate_audit

        result = validate_audit(sample_parquet_dir)
        assert result["race"] == [], f"Race table has leaked columns: {result['race']}"

    def test_entry_table_has_post_race_columns(self, sample_parquet_dir: Path) -> None:
        """Entry table should detect popularity and win_odds as post-race."""
        from src.pipeline.validators import validate_audit

        result = validate_audit(sample_parquet_dir)
        assert "popularity" in result["entry"], "Expected popularity in entry leaked"
        assert "win_odds" in result["entry"], "Expected win_odds in entry leaked"

    def test_result_table_all_post_race(self, sample_parquet_dir: Path) -> None:
        """Result table (all post-race) should list all columns as leaked."""
        from src.pipeline.validators import validate_audit

        result = validate_audit(sample_parquet_dir)
        # Result table has all fields as post-race
        assert len(result["result"]) > 0, "Expected post-race columns in result"


# ---------------------------------------------------------------------------
# Test 4: validate_null_rates
# ---------------------------------------------------------------------------

class TestValidateNullRates:
    """Tests for validate_null_rates function."""

    def test_null_rates_within_tolerance(
        self, sample_parquet_dir: Path, sample_source_stats: dict
    ) -> None:
        """Null rates within tolerance produce no flags."""
        from src.pipeline.validators import validate_null_rates

        result = validate_null_rates(sample_source_stats, sample_parquet_dir, tolerance=0.01)
        # Entry should have no flagged columns (source matches Parquet)
        entry_flags = result.get("entry", {})
        flagged = {col: diff for col, diff in entry_flags.items() if diff > 0.01}
        assert flagged == {}, f"Unexpected null rate flags: {flagged}"

    def test_null_rate_exceeding_tolerance_flagged(self, tmp_path: Path) -> None:
        """Null rate exceeding tolerance is flagged."""
        from src.pipeline.validators import validate_null_rates

        parquet_dir = tmp_path / "standard"
        parquet_dir.mkdir()

        # Create entry with 50% nulls in popularity
        entry_df = pd.DataFrame({
            "popularity": [1, None, 3, None, 5],
            "win_odds": [2.1, 3.5, 5.0, 4.2, 6.8],
        })
        entry_df.to_parquet(parquet_dir / "entry.parquet", engine="pyarrow", index=False)

        source_stats = {
            "entry": {
                "null_rates": {"popularity": 0.0, "win_odds": 0.0},
            },
        }

        result = validate_null_rates(source_stats, parquet_dir, tolerance=0.01)
        assert "popularity" in result.get("entry", {}), "Expected popularity flagged"


# ---------------------------------------------------------------------------
# Test 5: validate_distributions
# ---------------------------------------------------------------------------

class TestValidateDistributions:
    """Tests for validate_distributions function."""

    def test_matching_distributions_pass(
        self, sample_parquet_dir: Path, sample_source_stats: dict
    ) -> None:
        """Distributions within tolerance produce no flags."""
        from src.pipeline.validators import validate_distributions

        result = validate_distributions(sample_source_stats, sample_parquet_dir, tolerance=0.5)
        entry_mismatches = result.get("entry", {})
        flagged = {k: v for k, v in entry_mismatches.items() if v}
        assert flagged == {}, f"Unexpected distribution mismatches: {flagged}"

    def test_mismatched_distribution_flagged(self, tmp_path: Path) -> None:
        """Distribution mismatch is flagged."""
        from src.pipeline.validators import validate_distributions

        parquet_dir = tmp_path / "standard"
        parquet_dir.mkdir()

        entry_df = pd.DataFrame({
            "age": [3, 3, 3, 3, 3],  # All 3, mean=3 (source says 3.8)
            "weight_assigned": [54.0] * 5,
        })
        entry_df.to_parquet(parquet_dir / "entry.parquet", engine="pyarrow", index=False)

        source_stats = {
            "entry": {
                "distributions": {
                    "age": {"min": 3, "max": 5, "mean": 3.8},
                },
            },
        }

        result = validate_distributions(source_stats, parquet_dir, tolerance=0.5)
        assert "age" in result.get("entry", {}), "Expected age distribution flagged"


# ---------------------------------------------------------------------------
# Test 6: validate_referential_integrity
# ---------------------------------------------------------------------------

class TestValidateReferentialIntegrity:
    """Tests for validate_referential_integrity function."""

    def test_consistent_race_ids_no_errors(self, sample_parquet_dir: Path) -> None:
        """Tables with consistent race_ids return empty error list."""
        from src.pipeline.validators import validate_referential_integrity

        errors = validate_referential_integrity(sample_parquet_dir)
        assert errors == [], f"Unexpected integrity errors: {errors}"

    def test_missing_race_id_produces_error(self, tmp_path: Path) -> None:
        """Entry with race_id not in race table produces error."""
        from src.pipeline.validators import validate_referential_integrity

        parquet_dir = tmp_path / "standard"
        parquet_dir.mkdir()

        race_df = pd.DataFrame({"race_id": ["001"]})
        entry_df = pd.DataFrame({"race_id": ["001", "999"]})  # 999 not in race
        result_df = pd.DataFrame({"race_id": ["001"]})

        race_df.to_parquet(parquet_dir / "race.parquet", engine="pyarrow", index=False)
        entry_df.to_parquet(parquet_dir / "entry.parquet", engine="pyarrow", index=False)
        result_df.to_parquet(parquet_dir / "result.parquet", engine="pyarrow", index=False)

        errors = validate_referential_integrity(parquet_dir)
        assert len(errors) > 0, "Expected referential integrity errors"


# ---------------------------------------------------------------------------
# Test 7: validate_sample_rows
# ---------------------------------------------------------------------------

class TestValidateSampleRows:
    """Tests for validate_sample_rows function."""

    def test_matching_samples_pass(self, tmp_path: Path) -> None:
        """Sample rows matching between source CSV and Parquet return True."""
        from src.pipeline.validators import validate_sample_rows

        raw_dir = tmp_path / "raw"
        parquet_dir = tmp_path / "standard"
        raw_dir.mkdir()
        parquet_dir.mkdir()

        # Create a CSV source with Japanese column names (matching real Kaggle format)
        # and a matching Parquet with English column names
        csv_content = (
            "レースID,競馬場コード,距離(m)\n"
            "001,01,2000\n"
            "002,02,1400\n"
        )
        (raw_dir / "race_result.csv").write_text(csv_content, encoding="utf-8-sig")

        race_df = pd.DataFrame({
            "race_id": ["001", "002"],
            "course_code": ["01", "02"],
            "distance": [2000, 1400],
        })
        race_df.to_parquet(parquet_dir / "race.parquet", engine="pyarrow", index=False)

        result = validate_sample_rows(raw_dir, parquet_dir, n_samples=2)
        assert result.get("race", False), "Expected sample rows to match"

    def test_mismatched_values_flagged(self, tmp_path: Path) -> None:
        """Sample rows with different values between CSV and Parquet return False."""
        from src.pipeline.validators import validate_sample_rows

        raw_dir = tmp_path / "raw"
        parquet_dir = tmp_path / "standard"
        raw_dir.mkdir()
        parquet_dir.mkdir()

        # Use Japanese CSV column names with consistent race_id values
        csv_content = (
            "レースID,競馬場コード,距離(m)\n"
            "R001,01,2000\n"
            "R002,02,1400\n"
        )
        (raw_dir / "race_result.csv").write_text(csv_content, encoding="utf-8-sig")

        # Different distance value for R002
        race_df = pd.DataFrame({
            "race_id": ["R001", "R002"],
            "course_code": ["01", "02"],
            "distance": [2000, 9999],  # Mismatched for R002
        })
        race_df.to_parquet(parquet_dir / "race.parquet", engine="pyarrow", index=False)

        result = validate_sample_rows(raw_dir, parquet_dir, n_samples=2)
        assert result.get("race", True) is False, "Expected sample mismatch detected"


# ---------------------------------------------------------------------------
# Test 8: validate_value_ranges
# ---------------------------------------------------------------------------

class TestValidateValueRanges:
    """Tests for validate_value_ranges function."""

    def test_valid_ranges_pass(self, sample_parquet_dir: Path) -> None:
        """Valid course codes and distances produce no errors."""
        from src.pipeline.validators import validate_value_ranges

        result = validate_value_ranges(sample_parquet_dir)
        for table_name, errors in result.items():
            assert errors == [], f"{table_name} has range errors: {errors}"

    def test_invalid_course_code_reported(self, tmp_path: Path) -> None:
        """Course code outside 01-10 range is reported."""
        from src.pipeline.validators import validate_value_ranges

        parquet_dir = tmp_path / "standard"
        parquet_dir.mkdir()

        race_df = pd.DataFrame({
            "race_id": ["001"],
            "course_code": ["99"],  # Invalid
            "distance": [2000],
        })
        race_df.to_parquet(parquet_dir / "race.parquet", engine="pyarrow", index=False)

        result = validate_value_ranges(parquet_dir)
        assert len(result.get("race", [])) > 0, "Expected course_code range error"

    def test_negative_distance_reported(self, tmp_path: Path) -> None:
        """Negative distance is reported."""
        from src.pipeline.validators import validate_value_ranges

        parquet_dir = tmp_path / "standard"
        parquet_dir.mkdir()

        race_df = pd.DataFrame({
            "race_id": ["001"],
            "course_code": ["01"],
            "distance": [-100],  # Invalid
        })
        race_df.to_parquet(parquet_dir / "race.parquet", engine="pyarrow", index=False)

        result = validate_value_ranges(parquet_dir)
        assert len(result.get("race", [])) > 0, "Expected distance range error"

    def test_invalid_bracket_num_reported(self, tmp_path: Path) -> None:
        """Bracket number outside 1-8 is reported."""
        from src.pipeline.validators import validate_value_ranges

        parquet_dir = tmp_path / "standard"
        parquet_dir.mkdir()

        entry_df = pd.DataFrame({
            "horse_race_id": ["00101"],
            "race_id": ["001"],
            "bracket_num": [9],  # Invalid (max 8)
            "horse_number": [1],
            "age": [4],
            "weight_assigned": [57.0],
        })
        entry_df.to_parquet(parquet_dir / "entry.parquet", engine="pyarrow", index=False)

        result = validate_value_ranges(parquet_dir)
        assert len(result.get("entry", [])) > 0, "Expected bracket_num range error"


# ---------------------------------------------------------------------------
# Test 9: run_all_validations
# ---------------------------------------------------------------------------

class TestRunAllValidations:
    """Tests for run_all_validations orchestrator."""

    def test_aggregates_all_check_results(
        self, sample_parquet_dir: Path, source_counts: dict[str, int]
    ) -> None:
        """run_all_validations returns results for all 8 check types."""
        from src.pipeline.validators import run_all_validations

        result = run_all_validations(
            raw_dir=sample_parquet_dir.parent,
            parquet_dir=sample_parquet_dir,
            source_counts=source_counts,
        )

        expected_checks = [
            "row_counts", "schema_conformance", "audit",
            "null_rates", "distributions", "referential_integrity",
            "sample_rows", "value_ranges",
        ]
        for check in expected_checks:
            assert check in result, f"Missing check result: {check}"

        assert "overall_pass" in result, "Missing overall_pass field"

    def test_overall_pass_when_all_checks_pass(
        self, sample_parquet_dir: Path, source_counts: dict[str, int]
    ) -> None:
        """overall_pass is True when all individual checks pass."""
        from src.pipeline.validators import run_all_validations

        result = run_all_validations(
            raw_dir=sample_parquet_dir.parent,
            parquet_dir=sample_parquet_dir,
            source_counts=source_counts,
        )

        assert result["overall_pass"] is True, f"Expected overall pass, got: {result}"


# ---------------------------------------------------------------------------
# Test 10: Integration test (conditional on real data)
# ---------------------------------------------------------------------------

STANDARD_DIR = Path("data/standard")


def _parquet_files_exist() -> bool:
    """Check if all 5 Parquet files exist in data/standard/."""
    return all(
        (STANDARD_DIR / f"{name}.parquet").exists()
        for name in ["race", "entry", "result", "odds_trifecta", "payoff"]
    )


@pytest.mark.skipif(
    not _parquet_files_exist(),
    reason="Integration test requires data/standard/*.parquet files"
)
class TestIntegration:
    """Integration tests against real generated Parquet files."""

    def test_all_validations_pass_on_real_data(self) -> None:
        """Run full validation suite on real Parquet data and assert all pass."""
        from src.pipeline.validators import run_all_validations

        result = run_all_validations(
            raw_dir=Path("data/raw/kaggle"),
            parquet_dir=STANDARD_DIR,
        )

        assert result["overall_pass"] is True, (
            f"Validation failures: "
            f"{[k for k, v in result.items() if k != 'overall_pass' and v is False]}"
        )

    def test_row_counts_within_expected_range(self) -> None:
        """Verify row counts are within 5% of expected.

        Post-Phase-6 integration (Plan 06-03), the unified corpus covers
        2015-2026/5 (Kaggle 2015-2021 + scraped 2021-08..2026-05). The
        expected counts below reflect the UNIFIED corpus, not the Kaggle-only
        pre-integration counts. Updated when Phase 6 grew the corpus from
        Kaggle-only (race=21929, entry/result=311806) to unified.
        """
        from src.pipeline.validators import validate_row_counts

        expected = {
            "race": 38009,
            "entry": 534953,
            "result": 534953,
        }
        result = validate_row_counts(expected, STANDARD_DIR)
        for table, passed in result.items():
            assert passed, f"{table} row count outside 5% tolerance"

    def test_referential_integrity_holds(self) -> None:
        """Every race_id in child tables exists in race table."""
        from src.pipeline.validators import validate_referential_integrity

        errors = validate_referential_integrity(STANDARD_DIR)
        assert errors == [], f"Referential integrity errors: {errors}"
