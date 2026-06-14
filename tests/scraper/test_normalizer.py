"""Tests for ``src/scraper/normalizer``.

Covers the Cycle-1 / Cycle-2 / Cycle-3 review HIGH items for the normalizer:

  * Cycle-1 HIGH #7 -- schema reindex; empty input -> typed zero-row
    DataFrame with ALL schema columns.
  * Cycle-1 HIGH #8 -- date-partitioned atomic output (no single-file
    overwrite).
  * Cycle-2 #3 -- STRICT dtype enforcement; ``finish_position`` uses
    nullable ``Int64`` so ``None`` does NOT silently become ``float64``;
    genuine coercion failures RAISE; no ``errors="ignore"`` in source.
  * Cycle-2 #4 -- same-month re-run performs read-merge-dedup on the
    primary key; a sentinel row survives; duplicates collapse.
  * Cycle-2 #6 -- entry/result partitioned via ``partition_map``
    (race_id -> race_date); calling entry/result write WITHOUT the map
    raises a loud error.
  * Cycle-3 #1 -- ``corner_1..corner_4`` use nullable ``Float64`` (Kaggle
    double), NOT ``Int64``.
  * Integrity validation (duplicate keys, FK orphans, entry/result 1-to-1).
  * Obstacle filtering propagated to entry/result.
  * Atomic write leaves no ``.tmp`` files behind.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.schemas.entry import EntrySchema
from src.schemas.race import RaceSchema
from src.schemas.result import ResultSchema
from src.scraper.normalizer import (
    SCHEMA_DTYPE_MAP,
    _build_typed_dataframe,
    normalize_to_parquet,
    validate_integrity,
    write_partitioned_parquet,
)


# ---------------------------------------------------------------------------
# Sample data helpers
# ---------------------------------------------------------------------------


def _flat_race_dict(race_id: str = "202201050101", race_date: str = "2022-01-05") -> dict:
    """A flat (non-obstacle) race with 2 horses and full race/entry/result dicts."""
    race = {
        "race_id": race_id,
        "race_date": race_date,
        "meeting_num": 1,
        "course_code": "05",
        "course_name": "中山",
        "meeting_day": 1,
        "race_condition": "3歳新馬 (馬齢)",
        "race_number": 1,
        "grade_revision": None,
        "race_name": "3歳新馬",
        "grade": None,
        "obstacle": None,
        "surface": "芝",
        "surface_detail": None,
        "direction": "右",
        "course_detail": None,
        "distance": 1800,
        "weather": "晴",
        "track_condition": "良",
        "track_condition_detail": None,
        "start_time": "09:55",
        "race_flag_handicap": None,
        "race_flag_age_restricted": True,
        "race_flag_filly_only": None,
        "race_flag_colt_only": None,
        "race_flag_gelding_only": None,
        "race_flag_mare_only": None,
        "race_flag_stallion_only": None,
        "race_flag_apprentice": None,
        "race_flag_amateur": None,
        "race_flag_female_jockey": None,
        "race_flag_young_horse": None,
        "race_flag_condition_race": None,
        "race_flag_special_weight": None,
        "race_flag_bonus_weight": None,
        "race_flag_stakes": None,
        "race_flag_graded_stakes": None,
        "race_flag_listed": None,
        "race_flag_open": None,
        "race_flag_maiden": None,
        "race_flag_allowance": None,
    }
    entries = [
        {
            "horse_race_id": f"{race_id}01",
            "race_id": race_id,
            "bracket_num": 1,
            "horse_number": 1,
            "horse_name": "サンプルノウマ01",
            "sex": "牡",
            "age": 3,
            "weight_assigned": 55.0,
            "jockey": "騎手一",
            "trainer": "調教師一",
            "owner": "馬主一",
            "horse_weight": 456,
            "weight_change": 4,
            "region": "東",
            "popularity": 1,
            "win_odds": 2.5,
        },
        {
            "horse_race_id": f"{race_id}02",
            "race_id": race_id,
            "bracket_num": 2,
            "horse_number": 2,
            "horse_name": "サンプルノウマ02",
            "sex": "牝",
            "age": 3,
            "weight_assigned": 53.0,
            "jockey": "騎手二",
            "trainer": "調教師二",
            "owner": "馬主二",
            "horse_weight": 440,
            "weight_change": -2,
            "region": "西",
            "popularity": 2,
            "win_odds": 4.2,
        },
    ]
    results = [
        {
            "horse_race_id": f"{race_id}01",
            "race_id": race_id,
            "finish_position": 1,
            "finish_note": None,
            "finish_time": "1:48.2",
            "margin": "ハナ",
            "corner_1": 2,
            "corner_2": 1,
            "corner_3": 1,
            "corner_4": 1,
            "last_3f": 34.5,
            "prize_money": 700.0,
        },
        {
            "horse_race_id": f"{race_id}02",
            "race_id": race_id,
            "finish_position": 2,
            "finish_note": None,
            "finish_time": "1:48.3",
            "margin": "ハナ",
            "corner_1": 1,
            "corner_2": 2,
            "corner_3": 2,
            "corner_4": 2,
            "last_3f": 35.0,
            "prize_money": 280.0,
        },
    ]
    return {"race": race, "entries": entries, "results": results}


def _obstacle_race_dict(race_id: str = "202201050102", race_date: str = "2022-01-05") -> dict:
    """An obstacle race -- used to verify obstacle filtering drops it from all 3 tables."""
    race = {
        "race_id": race_id,
        "race_date": race_date,
        "meeting_num": 1,
        "course_code": "05",
        "course_name": "中山",
        "meeting_day": 1,
        "race_condition": "障害3歳以上OP",
        "race_number": 2,
        "grade_revision": None,
        "race_name": "障害3歳以上OP",
        "grade": None,
        "obstacle": "障害",
        "surface": "ダート",
        "surface_detail": None,
        "direction": None,
        "course_detail": None,
        "distance": 3110,
        "weather": "晴",
        "track_condition": "良",
        "track_condition_detail": None,
        "start_time": "10:30",
        # All flags None for simplicity
        "race_flag_handicap": None,
        "race_flag_age_restricted": None,
        "race_flag_filly_only": None,
        "race_flag_colt_only": None,
        "race_flag_gelding_only": None,
        "race_flag_mare_only": None,
        "race_flag_stallion_only": None,
        "race_flag_apprentice": None,
        "race_flag_amateur": None,
        "race_flag_female_jockey": None,
        "race_flag_young_horse": None,
        "race_flag_condition_race": None,
        "race_flag_special_weight": None,
        "race_flag_bonus_weight": None,
        "race_flag_stakes": None,
        "race_flag_graded_stakes": None,
        "race_flag_listed": None,
        "race_flag_open": None,
        "race_flag_maiden": None,
        "race_flag_allowance": None,
    }
    entries = [
        {
            "horse_race_id": f"{race_id}01",
            "race_id": race_id,
            "bracket_num": 1,
            "horse_number": 1,
            "horse_name": "障害ノウマ01",
            "sex": "セ",
            "age": 5,
            "weight_assigned": 60.0,
            "jockey": "障害騎手",
            "trainer": "障害調教師",
            "owner": "障害馬主",
            "horse_weight": 500,
            "weight_change": 0,
            "region": "東",
            "popularity": 1,
            "win_odds": 3.0,
        }
    ]
    results = [
        {
            "horse_race_id": f"{race_id}01",
            "race_id": race_id,
            "finish_position": 1,
            "finish_note": None,
            "finish_time": "3:30.0",
            "margin": "大差",
            "corner_1": 1,
            "corner_2": 1,
            "corner_3": 1,
            "corner_4": 1,
            "last_3f": 40.0,
            "prize_money": 500.0,
        }
    ]
    return {"race": race, "entries": entries, "results": results}


def _sample_parsed_races() -> list[dict]:
    """One flat race (2 horses) + one obstacle race (1 horse). Used in obstacle-filter tests."""
    return [_flat_race_dict(), _obstacle_race_dict()]


# ---------------------------------------------------------------------------
# TestTypedDataframe
# ---------------------------------------------------------------------------


class TestTypedDataframe:
    """Cycle-1 HIGH #7 (empty-input typed-DF), Cycle-2 #3 (strict dtype),
    Cycle-3 #1 (corner Float64), Cycle-2 #3 regression guards."""

    def test_empty_input_has_all_columns(self, tmp_standard_dir: Path) -> None:
        """normalize_to_parquet([]) produces a typed zero-row race Parquet
        with ALL RaceSchema columns."""
        paths = normalize_to_parquet([], standard_dir=tmp_standard_dir)
        # Placeholder race file exists.
        race_path = paths["race"][0]
        assert race_path.exists()
        df = pd.read_parquet(race_path, engine="pyarrow")
        assert len(df) == 0
        assert set(df.columns) == set(RaceSchema.model_fields.keys())

    def test_columns_match_schema(self, tmp_standard_dir: Path) -> None:
        """Output columns match RaceSchema/EntrySchema/ResultSchema model_fields exactly."""
        normalize_to_parquet([_flat_race_dict()], standard_dir=tmp_standard_dir)
        race_df = pd.read_parquet(
            tmp_standard_dir / "scraped" / "202201" / "race.parquet",
            engine="pyarrow",
        )
        entry_df = pd.read_parquet(
            tmp_standard_dir / "scraped" / "202201" / "entry.parquet",
            engine="pyarrow",
        )
        result_df = pd.read_parquet(
            tmp_standard_dir / "scraped" / "202201" / "result.parquet",
            engine="pyarrow",
        )
        assert set(race_df.columns) == set(RaceSchema.model_fields.keys())
        assert set(entry_df.columns) == set(EntrySchema.model_fields.keys())
        assert set(result_df.columns) == set(ResultSchema.model_fields.keys())

    def test_dtypes_applied(self, tmp_standard_dir: Path) -> None:
        """Output dtypes match the SCHEMA_DTYPE_MAP targets (nullable variants
        preserved through the write/read round-trip)."""
        normalize_to_parquet([_flat_race_dict()], standard_dir=tmp_standard_dir)
        race_df = pd.read_parquet(
            tmp_standard_dir / "scraped" / "202201" / "race.parquet",
            engine="pyarrow",
        )
        entry_df = pd.read_parquet(
            tmp_standard_dir / "scraped" / "202201" / "entry.parquet",
            engine="pyarrow",
        )
        result_df = pd.read_parquet(
            tmp_standard_dir / "scraped" / "202201" / "result.parquet",
            engine="pyarrow",
        )
        # race_id is object/string after round-trip (Arrow string).
        assert str(race_df["race_id"].dtype) in {"object", "string"}
        # race_flag_* is nullable boolean (boolean / bool / object-on-write).
        flag_dtype = str(race_df["race_flag_age_restricted"].dtype)
        assert flag_dtype in {"boolean", "bool", "object"}, (
            f"race_flag_age_restricted dtype was {flag_dtype!r}"
        )
        # distance is nullable Int64 (Int64 / int64 acceptable post-write).
        assert str(race_df["distance"].dtype) in {"Int64", "int64"}
        # weight_assigned is Float64 (Kaggle double).
        assert str(entry_df["weight_assigned"].dtype) in {"Float64", "float64"}
        # popularity is Float64 (Kaggle double, NOT int).
        assert str(entry_df["popularity"].dtype) in {"Float64", "float64"}
        # CYCLE-3 #1: corner_1..corner_4 are Float64 (Kaggle double), NOT Int64.
        for corner_col in ("corner_1", "corner_2", "corner_3", "corner_4"):
            dtype_str = str(result_df[corner_col].dtype)
            assert dtype_str in {"Float64", "float64"}, (
                f"{corner_col} dtype was {dtype_str!r} (must be Float64/double, NOT Int64)"
            )
        # Verify the Arrow physical type matches Kaggle (Cycle-3 #1: double).
        schema = pa.Table.from_pandas(
            result_df[["corner_1", "corner_2", "corner_3", "corner_4"]]
        ).schema
        for corner_col in ("corner_1", "corner_2", "corner_3", "corner_4"):
            arrow_type = str(schema.field(corner_col).type)
            assert arrow_type == "double", (
                f"{corner_col} Arrow physical type was {arrow_type!r} "
                f"(must be 'double' to match Kaggle result.parquet)"
            )

    def test_finish_position_none_preserves_int64_nullable(self) -> None:
        """CYCLE-2 #3 -- None values in finish_position do NOT silently
        downgrade the column to float64. The dtype stays nullable Int64."""
        rows = [
            {
                "horse_race_id": "20220105010101",
                "race_id": "202201050101",
                "finish_position": 1,
                "finish_note": None,
                "finish_time": "1:48.2",
                "margin": None,
                "corner_1": 1,
                "corner_2": 1,
                "corner_3": 1,
                "corner_4": 1,
                "last_3f": 34.5,
                "prize_money": 700.0,
            },
            {
                "horse_race_id": "20220105010102",
                "race_id": "202201050101",
                "finish_position": None,
                "finish_note": "取",
                "finish_time": None,
                "margin": None,
                "corner_1": None,
                "corner_2": None,
                "corner_3": None,
                "corner_4": None,
                "last_3f": None,
                "prize_money": None,
            },
        ]
        df = _build_typed_dataframe(rows, ResultSchema)
        assert df["finish_position"].dtype == pd.Int64Dtype(), (
            f"finish_position dtype was {df['finish_position'].dtype!r} "
            f"(must be Int64, NOT float64 -- Cycle-2 #3)"
        )
        # Mixed None+int values are preserved.
        assert pd.isna(df["finish_position"].iloc[1])
        assert df["finish_position"].iloc[0] == 1

    def test_genuine_coercion_failure_raises(self) -> None:
        """CYCLE-2 #3 -- non-numeric text in finish_position RAISES TypeError."""
        rows = [
            {
                "horse_race_id": "x",
                "race_id": "y",
                "finish_position": "not_a_number",
                "finish_note": None,
                "finish_time": None,
                "margin": None,
                "corner_1": None,
                "corner_2": None,
                "corner_3": None,
                "corner_4": None,
                "last_3f": None,
                "prize_money": None,
            }
        ]
        with pytest.raises((TypeError, ValueError)) as excinfo:
            _build_typed_dataframe(rows, ResultSchema)
        # Message should mention the column name so the failure is debuggable.
        msg = str(excinfo.value)
        assert "finish_position" in msg

    def test_no_head_count_column(self, tmp_standard_dir: Path) -> None:
        """head_count is NOT a RaceSchema field and must not appear in the output."""
        normalize_to_parquet([_flat_race_dict()], standard_dir=tmp_standard_dir)
        race_path = tmp_standard_dir / "scraped" / "202201" / "race.parquet"
        if not race_path.exists():
            race_path = tmp_standard_dir / "race.parquet"
        df = pd.read_parquet(race_path, engine="pyarrow")
        assert "head_count" not in df.columns

    def test_no_errors_ignore_in_source(self) -> None:
        """CYCLE-2 #3 -- the source file contains NO executable errors='ignore'."""
        source = Path("src/scraper/normalizer.py").read_text(encoding="utf-8")
        # All matches must be inside docstring/comment (no executable astype
        # call uses errors="ignore"). We check there is no astype(...errors="ignore")
        # executable pattern by stripping comments/docstrings would be ideal, but
        # a stricter guard: search for the executable signature
        # `.astype(<...>, errors="ignore")` -- which we never write.
        import re

        # Reject any astype call that passes errors="ignore" as a kwarg.
        bad_pattern = re.compile(r"\.astype\([^)]*errors\s*=\s*[\"']ignore[\"']")
        assert not bad_pattern.search(source), (
            "Found executable astype(..., errors='ignore') in normalizer.py -- Cycle-2 #3"
        )


# ---------------------------------------------------------------------------
# TestObstacleFiltering
# ---------------------------------------------------------------------------


class TestObstacleFiltering:
    """Obstacle races are dropped from all 3 tables (mirrors kaggle_converter)."""

    def test_obstacle_race_dropped(self, tmp_standard_dir: Path) -> None:
        """Sample with 1 flat + 1 obstacle -> race Parquet has exactly 1 row."""
        normalize_to_parquet(_sample_parsed_races(), standard_dir=tmp_standard_dir)
        race_df = pd.read_parquet(
            tmp_standard_dir / "scraped" / "202201" / "race.parquet",
            engine="pyarrow",
        )
        assert len(race_df) == 1
        assert (race_df["obstacle"] != "障害").all()

    def test_obstacle_entries_propagate(self, tmp_standard_dir: Path) -> None:
        """Entry/result tables exclude obstacle race entries."""
        normalize_to_parquet(_sample_parsed_races(), standard_dir=tmp_standard_dir)
        entry_df = pd.read_parquet(
            tmp_standard_dir / "scraped" / "202201" / "entry.parquet",
            engine="pyarrow",
        )
        result_df = pd.read_parquet(
            tmp_standard_dir / "scraped" / "202201" / "result.parquet",
            engine="pyarrow",
        )
        # Flat race has 2 horses; obstacle race has 1 horse (filtered out).
        assert len(entry_df) == 2
        assert len(result_df) == 2
        # None of the surviving rows belong to the obstacle race.
        assert (entry_df["race_id"] != "202201050102").all()
        assert (result_df["race_id"] != "202201050102").all()


# ---------------------------------------------------------------------------
# TestIntegrityValidation
# ---------------------------------------------------------------------------


class TestIntegrityValidation:
    """validate_integrity returns violation strings (never raises)."""

    def test_detects_duplicate_race_id(self) -> None:
        race_df = pd.DataFrame(
            {"race_id": ["A", "A", "B"], "obstacle": [None, None, None]}
        )
        entry_df = pd.DataFrame({"horse_race_id": [], "race_id": []})
        result_df = pd.DataFrame({"horse_race_id": [], "race_id": []})
        violations = validate_integrity(race_df, entry_df, result_df)
        joined = " | ".join(violations)
        assert "duplicate race_id" in joined

    def test_detects_duplicate_horse_race_id(self) -> None:
        race_df = pd.DataFrame({"race_id": ["A"], "obstacle": [None]})
        entry_df = pd.DataFrame(
            {"horse_race_id": ["X", "X"], "race_id": ["A", "A"]}
        )
        result_df = pd.DataFrame({"horse_race_id": ["X"], "race_id": ["A"]})
        violations = validate_integrity(race_df, entry_df, result_df)
        joined = " | ".join(violations)
        assert "duplicate horse_race_id" in joined

    def test_detects_entry_result_mismatch(self) -> None:
        """Entry has horse_race_id X but result does not (1-to-1 mismatch)."""
        race_df = pd.DataFrame({"race_id": ["A"], "obstacle": [None]})
        entry_df = pd.DataFrame({"horse_race_id": ["X", "Y"], "race_id": ["A", "A"]})
        result_df = pd.DataFrame({"horse_race_id": ["X"], "race_id": ["A"]})
        violations = validate_integrity(race_df, entry_df, result_df)
        joined = " | ".join(violations)
        assert "horse_race_id mismatch" in joined

    def test_detects_orphan_fk(self) -> None:
        """Entry race_id not in race_df triggers an orphan FK violation."""
        race_df = pd.DataFrame({"race_id": ["A"], "obstacle": [None]})
        entry_df = pd.DataFrame(
            {"horse_race_id": ["X"], "race_id": ["ORPHAN"]}
        )
        result_df = pd.DataFrame({"horse_race_id": ["X"], "race_id": ["A"]})
        violations = validate_integrity(race_df, entry_df, result_df)
        joined = " | ".join(violations)
        assert "orphan entry race_id" in joined

    def test_clean_data_no_violations(self) -> None:
        """Well-formed input yields zero violations."""
        race_df = pd.DataFrame({"race_id": ["A", "B"], "obstacle": [None, None]})
        entry_df = pd.DataFrame(
            {"horse_race_id": ["X", "Y"], "race_id": ["A", "B"]}
        )
        result_df = pd.DataFrame(
            {"horse_race_id": ["X", "Y"], "race_id": ["A", "B"]}
        )
        violations = validate_integrity(race_df, entry_df, result_df)
        assert violations == []


# ---------------------------------------------------------------------------
# TestPartitionedOutput
# ---------------------------------------------------------------------------


class TestPartitionedOutput:
    """Cycle-1 HIGH #8 partitioned output, Cycle-2 #4 merge-dedup,
    Cycle-2 #6 partition_map for entry/result."""

    def test_partitioned_by_year_month(self, tmp_standard_dir: Path) -> None:
        """Races in 2022-01 and 2022-02 produce 2 partition directories."""
        race_jan = _flat_race_dict(race_id="202201050101", race_date="2022-01-05")
        race_feb = _flat_race_dict(race_id="202202050101", race_date="2022-02-05")
        normalize_to_parquet([race_jan, race_feb], standard_dir=tmp_standard_dir)
        jan_dir = tmp_standard_dir / "scraped" / "202201"
        feb_dir = tmp_standard_dir / "scraped" / "202202"
        assert jan_dir.exists(), "202201 partition dir missing"
        assert feb_dir.exists(), "202202 partition dir missing"
        assert (jan_dir / "race.parquet").exists()
        assert (feb_dir / "race.parquet").exists()

    def test_no_single_overwrite_file(self, tmp_standard_dir: Path) -> None:
        """No single-file ``race_scraped.parquet`` at the standard root."""
        normalize_to_parquet([_flat_race_dict()], standard_dir=tmp_standard_dir)
        assert not (tmp_standard_dir / "race_scraped.parquet").exists()
        assert not (tmp_standard_dir / "entry_scraped.parquet").exists()
        assert not (tmp_standard_dir / "result_scraped.parquet").exists()

    def test_atomic_no_tmp_remains(self, tmp_standard_dir: Path) -> None:
        """No ``.parquet.tmp`` files remain after a normalize run."""
        normalize_to_parquet([_flat_race_dict()], standard_dir=tmp_standard_dir)
        leftovers = list(tmp_standard_dir.rglob("*.tmp"))
        leftovers += list(tmp_standard_dir.rglob("*.parquet.tmp"))
        assert leftovers == [], f"Leftover tmp files: {leftovers}"

    def test_does_not_overwrite_other_month(self, tmp_standard_dir: Path) -> None:
        """Pre-existing 202112 partition is untouched by a 202201 normalize."""
        other_dir = tmp_standard_dir / "scraped" / "202112"
        other_dir.mkdir(parents=True, exist_ok=True)
        sentinel_path = other_dir / "race.parquet"
        sentinel_df = pd.DataFrame(
            {"race_id": ["202112010101"], "race_date": ["2021-12-01"]}
        )
        sentinel_df.to_parquet(sentinel_path, engine="pyarrow", index=False)

        normalize_to_parquet([_flat_race_dict()], standard_dir=tmp_standard_dir)

        # The 202112 file should still exist and be readable.
        assert sentinel_path.exists()
        # Its content should not have been overwritten by the 202201 batch.
        back = pd.read_parquet(sentinel_path, engine="pyarrow")
        assert "202112010101" in back["race_id"].tolist()
        assert "202201050101" not in back["race_id"].tolist()

    def test_same_month_merge_dedup_preserves_sentinel(
        self, tmp_standard_dir: Path
    ) -> None:
        """CYCLE-2 #4 -- a pre-seeded sentinel row SURVIVES a same-month
        re-run, AND duplicate primary keys collapse via drop_duplicates."""
        # Pre-seed 202201/race.parquet with a sentinel row + 2 columns
        # (race_id, race_date) plus enough of the schema for merge-dedup.
        target_dir = tmp_standard_dir / "scraped" / "202201"
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / "race.parquet"

        sentinel_row = {
            "race_id": "202201010101",
            "race_date": "2022-01-01",
        }
        # Build a typed placeholder so the read-merge path picks up the same columns.
        sentinel_df = _build_typed_dataframe([sentinel_row], RaceSchema)
        sentinel_df.to_parquet(target_path, engine="pyarrow", index=False)

        # Run a 2022-01 batch that includes:
        #  * a NEW race (202201010102)
        #  * a DUPLICATE of the sentinel (202201010101) -- should collapse.
        race_new = _flat_race_dict(race_id="202201010102", race_date="2022-01-01")
        race_dup = _flat_race_dict(race_id="202201010101", race_date="2022-01-01")
        normalize_to_parquet([race_new, race_dup], standard_dir=tmp_standard_dir)

        # Read back and assert: BOTH ids present, no duplicates.
        back = pd.read_parquet(target_path, engine="pyarrow")
        ids = set(back["race_id"].dropna().tolist())
        assert "202201010101" in ids, "Sentinel race_id lost (Cycle-2 #4)"
        assert "202201010102" in ids, "New race_id not added (Cycle-2 #4)"
        # race_id should be unique -- the duplicate sentinel collapsed.
        assert back["race_id"].duplicated().sum() == 0, (
            "Duplicate race_id survived -- Cycle-2 #4 merge-dedup failed"
        )

    def test_merge_dedup_falls_back_when_existing_column_not_coercible(
        self, tmp_standard_dir: Path
    ) -> None:
        """CR-02 -- a non-coercible existing column triggers fallback to
        new-only write (rather than silently merging with a broken dtype).

        Pre-seed the result partition with a ``finish_position`` column stored
        as non-numeric text (``"not_a_number"``). The merge-dedup path reads
        this, calls ``_recast_for_storage`` to coerce back to Int64, which
        raises ``TypeError``. The caller's ``except Exception`` then falls back
        to writing only the NEW (correctly-typed) partition. The bad row is
        dropped; the new row survives with the strict Int64 dtype.
        """
        target_dir = tmp_standard_dir / "scraped" / "202201"
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / "result.parquet"

        # Build a result row with the FULL ResultSchema column set so the
        # read-merge-dedup path does not trip the WR-02 column-set guard; we
        # want to exercise the dtype-coercion failure path specifically.
        # We construct the bad DataFrame directly (NOT via _build_typed_dataframe,
        # which would itself raise on the non-coercible value) and write it
        # with object-typed finish_position.
        schema_cols = list(ResultSchema.model_fields.keys())
        bad_row = {
            "horse_race_id": "20220105010199",
            "race_id": "202201050101",
            "finish_position": "not_a_number",  # non-coercible to Int64
            "finish_note": None,
            "finish_time": None,
            "margin": None,
            "corner_1": None,
            "corner_2": None,
            "corner_3": None,
            "corner_4": None,
            "last_3f": None,
            "prize_money": None,
        }
        bad_df = pd.DataFrame([bad_row], columns=schema_cols)
        bad_df.to_parquet(target_path, engine="pyarrow", index=False)

        # Now run a normalize that targets the SAME partition with a valid row.
        # The merge-dedup path should detect the non-coercible existing column
        # and fall back to writing only the new partition.
        good_row = {
            "horse_race_id": "20220105010101",
            "race_id": "202201050101",
            "finish_position": 1,
            "finish_note": None,
            "finish_time": "1:48.0",
            "margin": None,
            "corner_1": 1,
            "corner_2": 1,
            "corner_3": 1,
            "corner_4": 1,
            "last_3f": 34.0,
            "prize_money": 700.0,
        }
        good_df = _build_typed_dataframe([good_row], ResultSchema)
        partition_map = {"202201050101": datetime.date(2022, 1, 5)}
        write_partitioned_parquet(
            "result",
            good_df,
            tmp_standard_dir,
            partition_map=partition_map,
            primary_key="horse_race_id",
        )

        # The written parquet should NOT contain the bad string value.
        back = pd.read_parquet(target_path, engine="pyarrow")
        assert "not_a_number" not in back["finish_position"].astype(str).tolist()
        # The good row survived.
        assert "20220105010101" in back["horse_race_id"].astype(str).tolist()
        # The dtype is the strict nullable Int64 (or plain int64 after a
        # read_parquet round-trip on a non-null column).
        assert str(back["finish_position"].dtype) in {"Int64", "int64"}, (
            f"finish_position dtype was {back['finish_position'].dtype!r} "
            f"(CR-02: merge-dedup should not silently break the dtype contract)"
        )

    def test_entry_result_partitioned_via_partition_map(
        self, tmp_standard_dir: Path
    ) -> None:
        """CYCLE-2 #6 -- entry/result partition files land under the YYYYMM
        derived from partition_map (race_id -> race_date), without a KeyError."""
        normalize_to_parquet([_flat_race_dict()], standard_dir=tmp_standard_dir)
        # Entry/result should land under 202201/ alongside race.parquet.
        assert (
            tmp_standard_dir / "scraped" / "202201" / "entry.parquet"
        ).exists(), "entry partition missing (Cycle-2 #6)"
        assert (
            tmp_standard_dir / "scraped" / "202201" / "result.parquet"
        ).exists(), "result partition missing (Cycle-2 #6)"

        entry_df = pd.read_parquet(
            tmp_standard_dir / "scraped" / "202201" / "entry.parquet",
            engine="pyarrow",
        )
        # Entry df must NOT have a race_date column (Cycle-2 #6).
        assert "race_date" not in entry_df.columns
        # And it should have the 2 expected entries.
        assert len(entry_df) == 2

    def test_entry_write_without_partition_map_raises(
        self, tmp_standard_dir: Path
    ) -> None:
        """CYCLE-2 #6 -- calling entry write WITHOUT partition_map raises a
        clear error (fail loud, not silent mis-partition)."""
        entry_rows = [
            {
                "horse_race_id": "20220105010101",
                "race_id": "202201050101",
                "bracket_num": 1,
                "horse_number": 1,
                "horse_name": "X",
                "sex": "牡",
                "age": 3,
                "weight_assigned": 55.0,
                "jockey": "J",
                "trainer": "T",
                "owner": "O",
                "horse_weight": 456,
                "weight_change": 4,
                "region": "東",
                "popularity": 1,
                "win_odds": 2.5,
            }
        ]
        entry_df = _build_typed_dataframe(entry_rows, EntrySchema)
        with pytest.raises(KeyError) as excinfo:
            write_partitioned_parquet(
                "entry", entry_df, tmp_standard_dir, partition_map=None
            )
        # Error message must mention partition_map so a future caller can debug.
        msg = str(excinfo.value)
        assert "partition_map" in msg

    def test_result_write_uses_partition_map(
        self, tmp_standard_dir: Path
    ) -> None:
        """Bonus guard: result write with an explicit partition_map routes to
        the correct YYYYMM directory."""
        result_rows = [
            {
                "horse_race_id": "20220305010101",
                "race_id": "202203050101",
                "finish_position": 1,
                "finish_note": None,
                "finish_time": "1:48.0",
                "margin": None,
                "corner_1": 1,
                "corner_2": 1,
                "corner_3": 1,
                "corner_4": 1,
                "last_3f": 34.0,
                "prize_money": 700.0,
            }
        ]
        result_df = _build_typed_dataframe(result_rows, ResultSchema)
        partition_map = {"202203050101": datetime.date(2022, 3, 5)}
        written = write_partitioned_parquet(
            "result",
            result_df,
            tmp_standard_dir,
            partition_map=partition_map,
            primary_key="horse_race_id",
        )
        assert any("202203" in str(p) for p in written), (
            f"result not written to 202203 partition: {written}"
        )
        back = pd.read_parquet(
            tmp_standard_dir / "scraped" / "202203" / "result.parquet",
            engine="pyarrow",
        )
        assert "20220305010101" in back["horse_race_id"].tolist()


# ---------------------------------------------------------------------------
# Bonus regression guards (cross-references with the Cycle-2 contracts)
# ---------------------------------------------------------------------------


class TestCycle2RegressionGuards:
    """Targeted regression guards for the Cycle-2 / Cycle-3 acceptance criteria."""

    def test_schema_dtype_map_has_all_three_schemas(self) -> None:
        """SCHEMA_DTYPE_MAP covers RaceSchema, EntrySchema, ResultSchema."""
        assert RaceSchema in SCHEMA_DTYPE_MAP
        assert EntrySchema in SCHEMA_DTYPE_MAP
        assert ResultSchema in SCHEMA_DTYPE_MAP

    def test_dtype_map_finish_position_int64(self) -> None:
        """Cycle-2 #3 -- finish_position dtype target is Int64 (nullable)."""
        assert SCHEMA_DTYPE_MAP[ResultSchema]["finish_position"] == "Int64"

    def test_dtype_map_corners_float64(self) -> None:
        """Cycle-3 #1 -- corner_1..corner_4 dtype target is Float64 (Kaggle double)."""
        for corner in ("corner_1", "corner_2", "corner_3", "corner_4"):
            assert SCHEMA_DTYPE_MAP[ResultSchema][corner] == "Float64", (
                f"{corner} target must be Float64 (Kaggle double)"
            )

    def test_dtype_map_popularity_float64(self) -> None:
        """popularity dtype target is Float64 (Kaggle double, NOT int)."""
        assert SCHEMA_DTYPE_MAP[EntrySchema]["popularity"] == "Float64"

    def test_dtype_map_covers_all_schema_fields(self) -> None:
        """SCHEMA_DTYPE_MAP covers every field of each schema."""
        for schema in (RaceSchema, EntrySchema, ResultSchema):
            schema_fields = set(schema.model_fields.keys())
            dtype_fields = set(SCHEMA_DTYPE_MAP[schema].keys())
            assert schema_fields == dtype_fields, (
                f"{schema.__name__}: missing={schema_fields - dtype_fields}, "
                f"extra={dtype_fields - schema_fields}"
            )

    def test_write_partitioned_parquet_signature(self) -> None:
        """write_partitioned_parquet exposes partition_map + primary_key (Cycle-2 #4/#6)."""
        import inspect

        sig = inspect.signature(write_partitioned_parquet)
        assert "partition_map" in sig.parameters
        assert "primary_key" in sig.parameters
        assert sig.parameters["primary_key"].default == "race_id"

    def test_audit_leakage_not_called_for_entry_table(
        self, tmp_standard_dir: Path
    ) -> None:
        """Cycle-1 MEDIUM -- normalize_to_parquet does NOT call audit_leakage
        (popularity/win_odds are intentionally in the entry table). The
        simplest observable guard: the run completes successfully with
        popularity/win_odds populated."""
        normalize_to_parquet([_flat_race_dict()], standard_dir=tmp_standard_dir)
        entry_df = pd.read_parquet(
            tmp_standard_dir / "scraped" / "202201" / "entry.parquet",
            engine="pyarrow",
        )
        # popularity/win_odds present and non-null (no leakage audit tripped).
        assert entry_df["popularity"].notna().any()
        assert entry_df["win_odds"].notna().any()

    def test_kaggle_physical_type_equality_for_corners(
        self, tmp_standard_dir: Path
    ) -> None:
        """Cycle-3 #1 -- the corner columns in our scraper output have the
        same Arrow physical type ('double') as the Kaggle result.parquet."""
        normalize_to_parquet([_flat_race_dict()], standard_dir=tmp_standard_dir)
        out_df = pd.read_parquet(
            tmp_standard_dir / "scraped" / "202201" / "result.parquet",
            engine="pyarrow",
        )
        out_arrow_schema = pa.Table.from_pandas(out_df).schema
        kaggle_schema = pq.read_schema("data/standard/result.parquet")
        for corner in ("corner_1", "corner_2", "corner_3", "corner_4"):
            our_type = str(out_arrow_schema.field(corner).type)
            kaggle_type = str(kaggle_schema.field(corner).type)
            assert our_type == kaggle_type, (
                f"{corner}: our Arrow type {our_type!r} != Kaggle {kaggle_type!r}"
            )
