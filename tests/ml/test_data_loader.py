"""MODA-01 data_loader tests (Wave 1 GREEN).

RESEARCH.md Test Map lines 786-787, 795. PATTERNS.md analog:
tests/pipeline/test_feature_generator.py::TestLoadMerge.

These tests exercise ``src.ml.data_loader.load_features`` against the hermetic
fixtures defined in tests/ml/conftest.py (no external data dependency). Two
tests are gated against the real ``data/feature/features_train.parquet`` corpus
and only run under ``RUN_GATED=1``. The skip is implemented inline
(``os.environ.get("RUN_GATED") != "1"`` -> ``pytest.skip``) mirroring the
existing ``live`` marker pattern at tests/scraper/test_end_to_end.py:713-720;
the ``gated`` marker in pyproject.toml only suppresses the
PytestUnknownMarkWarning and does NOT auto-skip.

Covers:
- MODA-01 (categorical conversion, horse_race_id derive)
- T-data-leak (post-race column audit via audit_leakage)
- D-01/D-02 train/holdout window splits
- Pitfall #3 (categorical dtype), #2 (horse_race_id authority — no underscore),
  #4 (grade NaN preserved through category conversion),
  #7 (train/holdout time gap)
- Codex HIGH #4 (fixed-count assert breaks hermetic E2E -> expected_counts)
- Cycle-2 HIGH #1 (race_date sort + monotonicity + column retention)
- Cycle-2 HIGH #2 (UNIFIED empty-list [] bypass sentinel; {} rejected)
"""

import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.ml.data_loader import PRODUCTION_COUNTS, load_features
from src.pipeline.feature_generator import CATEGORICAL_COLUMNS
from src.schemas.audit import audit_leakage
from src.schemas.entry import EntrySchema
from src.schemas.race import RaceSchema


class TestFeatureLoad:
    """Tests for src/ml/data_loader.load_features.

    MODA-01: feature loading with dtype safety, horse_race_id derivation,
    leakage audit. The expected_counts parameter enables hermetic E2E
    (Codex HIGH #4 fix) and the UNIFIED empty-list [] sentinel (Cycle-2 HIGH #2
    fix) is enforced across spec/signature/tests/07-07 forwarding.
    """

    # ------------------------------------------------------------------
    # Hermetic tests (run by default; no RUN_GATED required)
    # ------------------------------------------------------------------

    def test_categorical_conversion(
        self,
        sample_feature_df: pd.DataFrame,
        tmp_path: Path,
    ) -> None:
        """MODA-01 / Pitfall #3: every CATEGORICAL_COLUMNS entry is category dtype after load.

        feature_generator.convert_to_categorical gated on dtype=='object'
        which misses pandas nullable `string` columns. load_features must
        convert unconditionally so course_name/surface/direction/weather/
        track_condition/sex/grade (all `string` on the real corpus) plus
        jockey/trainer (already category) end up as category dtype.
        """
        # Write the hermetic fixture to a parquet, then load through
        # load_features with an adapted window + bypass sentinel so the
        # small fixture does not trip the production-count assert.
        # All fixture rows (2018-01-01..2024-11-11) fall in the train window;
        # the production holdout window (2025-01-01..2026-05-31) is empty here.
        feature_path = tmp_path / "feature_hermetic.parquet"
        sample_feature_df.to_parquet(feature_path, engine="pyarrow")
        result = load_features(
            feature_path=feature_path,
            train_window=("2018-01-01", "2024-12-31"),
            holdout_window=("2025-01-01", "2026-05-31"),
            entry_path=tmp_path / "nonexistent_entry.parquet",  # skip join check
            expected_counts=[],  # Codex HIGH #4: bypass for hermetic fixture
        )
        # train has all rows; holdout is empty by design (mirrors production
        # split where the small fixture only spans the train window).
        assert len(result["train"]) > 0, "hermetic fixture produced zero train rows"
        train = result["train"]
        for col in [
            "course_name",
            "surface",
            "direction",
            "weather",
            "track_condition",
            "sex",
            "grade",
            "jockey",
            "trainer",
        ]:
            assert col in train.columns, f"missing categorical col {col}"
            assert train[col].dtype.name == "category", (
                f"Pitfall #3: {col} must be category dtype after load_features, "
                f"got {train[col].dtype}"
            )

    def test_horse_race_id_derive(
        self,
        sample_feature_df: pd.DataFrame,
        sample_entry_df: pd.DataFrame,
        tmp_path: Path,
    ) -> None:
        """MODA-01 / Pitfall #2: horse_race_id = f"{race_id}{horse_number:02d}" (no underscore).

        RESEARCH A5 assumed the underscore form "{race_id}_{horse_number:02d}"
        but real data/standard/entry.parquet uses NO underscore (verified:
        '20150101010102' for race_id=201501010101, horse_number=2). The
        derived column must round-trip 1:1 against sample_entry_df.
        """
        feature_path = tmp_path / "feature_hermetic.parquet"
        sample_feature_df.to_parquet(feature_path, engine="pyarrow")
        result = load_features(
            feature_path=feature_path,
            train_window=("2018-01-01", "2024-12-31"),
            holdout_window=("2025-01-01", "2026-05-31"),
            entry_path=tmp_path / "nonexistent_entry.parquet",
            expected_counts=[],
        )
        train = result["train"]
        # Format check: first row should match no-underscore form.
        first = train.iloc[0]
        expected_first = f"{first['race_id']}{int(first['horse_number']):02d}"
        assert first["horse_race_id"] == expected_first, (
            f"Pitfall #2: expected no-underscore form {expected_first!r}, "
            f"got {first['horse_race_id']!r}"
        )
        # No underscore in any derived value.
        assert not train["horse_race_id"].astype(str).str.contains("_").any(), (
            "Pitfall #2: derived horse_race_id must NOT contain underscore"
        )
        # 1:1 round-trip against sample_entry_df (sort both for set equality).
        derived_set = set(train["horse_race_id"].astype(str))
        entry_set = set(sample_entry_df["horse_race_id"].astype(str))
        assert derived_set == entry_set, (
            f"Pitfall #2: derived horse_race_id set diverges from entry set "
            f"(only-in-derived={len(derived_set - entry_set)}, "
            f"only-in-entry={len(entry_set - derived_set)})"
        )

    def test_leakage_audit(
        self,
        sample_feature_df: pd.DataFrame,
    ) -> None:
        """T-data-leak: audit_leakage returns empty on clean feature, ['popularity'] on poisoned.

        D-12: audit_leakage is warning-only, never raises. The caller decides
        how to proceed. Here we verify both the clean path (sample_feature_df
        has no popularity/win_odds by construction) and the detection path
        (intentional post-race column mixed in).
        """
        # Clean path: sample_feature_df has no post-race columns.
        clean_leaked = audit_leakage(
            [RaceSchema, EntrySchema],
            sample_feature_df,
            context="phase7 feature load (clean)",
        )
        assert clean_leaked == [], (
            f"clean feature leaked post-race columns unexpectedly: {clean_leaked}"
        )
        # Poisoned path: add popularity (post-race per EntrySchema D-03).
        poisoned = sample_feature_df.copy()
        poisoned["popularity"] = 1.0
        poisoned_leaked = audit_leakage(
            [RaceSchema, EntrySchema],
            poisoned,
            context="phase7 feature load (poisoned)",
        )
        assert "popularity" in poisoned_leaked, (
            f"audit_leakage failed to detect popularity (D-03 post-race); "
            f"got {poisoned_leaked}"
        )

    def test_expected_counts_bypass(
        self,
        sample_feature_df: pd.DataFrame,
        tmp_path: Path,
    ) -> None:
        """Codex HIGH #4 + Cycle-2 HIGH #2: empty list [] bypasses row-count assert.

        (1) load_features(expected_counts=[]) on a small fixture must succeed
            without AssertionError.
        (2) load_features(expected_counts=None) on the SAME small fixture must
            raise AssertionError because counts differ from PRODUCTION_COUNTS,
            proving the bypass is necessary.
        (3) load_features(expected_counts={}) (empty dict) must raise TypeError
            per Cycle-2 HIGH #2 + Cycle-5 MEDIUM tightening.
        """
        feature_path = tmp_path / "feature_hermetic.parquet"
        sample_feature_df.to_parquet(feature_path, engine="pyarrow")
        # All fixture rows (2018-01-01..2024-11-11) land in the train window;
        # the production holdout window is empty here, so train+holdout == 20.
        train_window = ("2018-01-01", "2024-12-31")
        holdout_window = ("2025-01-01", "2026-05-31")

        # (1) bypass path: [] skips the assert, small fixture loads fine.
        result = load_features(
            feature_path=feature_path,
            train_window=train_window,
            holdout_window=holdout_window,
            entry_path=tmp_path / "nonexistent_entry.parquet",
            expected_counts=[],
        )
        total_rows = len(result["train"]) + len(result["holdout"])
        assert total_rows == len(sample_feature_df), (
            f"bypass returned wrong total rows: {total_rows} vs "
            f"{len(sample_feature_df)}"
        )
        # The small fixture is NOT the production count.
        assert total_rows != PRODUCTION_COUNTS["train_rows"], (
            "fixture accidentally matches production count; test invalid"
        )

        # (2) production path: None asserts PRODUCTION_COUNTS -> AssertionError.
        with pytest.raises(AssertionError):
            load_features(
                feature_path=feature_path,
                train_window=train_window,
                holdout_window=holdout_window,
                entry_path=tmp_path / "nonexistent_entry.parquet",
                expected_counts=None,
            )

        # (3) empty dict {} rejected with TypeError.
        with pytest.raises(TypeError):
            load_features(
                feature_path=feature_path,
                train_window=train_window,
                holdout_window=holdout_window,
                entry_path=tmp_path / "nonexistent_entry.parquet",
                expected_counts={},
            )

    def test_race_date_sorted_monotonic(
        self,
        sample_feature_df: pd.DataFrame,
        tmp_path: Path,
    ) -> None:
        """Cycle-2 HIGH #1: load_features sorts by race_date ascending and asserts monotonicity.

        Builds a REVERSE-ORDER (descending race_date) fixture, writes it to
        parquet, and verifies that load_features returns train/holdout frames
        with race_date ascending. GroupTimeSeriesSplit (07-03) requires the
        input to be ascending; parquet row order is NOT guaranteed chronological
        (verified on the real corpus), so the read boundary must enforce sort.

        Also asserts that the race_date column is RETAINED on train/holdout
        (not dropped) so the downstream trainer can pass dates=df["race_date"]
        to splitter.split.
        """
        # Reverse the fixture by race_date so the on-disk parquet is descending.
        reversed_df = sample_feature_df.copy()
        reversed_df["race_date"] = pd.to_datetime(reversed_df["race_date"])
        reversed_df = (
            reversed_df.sort_values("race_date", ascending=False)
            .reset_index(drop=True)
            .assign(race_date=lambda d: d["race_date"].dt.strftime("%Y-%m-%d"))
        )
        # Sanity: the parquet we write is descending.
        sanity_dates = pd.to_datetime(reversed_df["race_date"])
        assert not sanity_dates.is_monotonic_increasing, (
            "test setup invalid: fixture must be descending before load_features"
        )

        feature_path = tmp_path / "feature_reversed.parquet"
        reversed_df.to_parquet(feature_path, engine="pyarrow")

        result = load_features(
            feature_path=feature_path,
            train_window=("2018-01-01", "2024-12-31"),
            holdout_window=("2025-01-01", "2026-05-31"),
            entry_path=tmp_path / "nonexistent_entry.parquet",
            expected_counts=[],
        )

        # (a) race_date column RETAINED on both frames (Cycle-2 HIGH #1).
        assert "race_date" in result["train"].columns, (
            "Cycle-2 HIGH #1: train must retain race_date column"
        )
        assert "race_date" in result["holdout"].columns, (
            "Cycle-2 HIGH #1: holdout must retain race_date column"
        )

        # (b) Both frames are race_date ascending despite descending input.
        assert result["train"]["race_date"].is_monotonic_increasing, (
            "Cycle-2 HIGH #1: train race_date must be ascending after load_features"
        )
        assert result["holdout"]["race_date"].is_monotonic_increasing, (
            "Cycle-2 HIGH #1: holdout race_date must be ascending after load_features"
        )

        # (c) metadata flags race_date_sorted=True.
        assert result["metadata"]["race_date_sorted"] is True, (
            "Cycle-2 HIGH #1: metadata.race_date_sorted must be True"
        )

    # ------------------------------------------------------------------
    # Gated tests (require RUN_GATED=1; real corpus dependency)
    # ------------------------------------------------------------------

    @pytest.mark.gated
    def test_train_holdout_window_counts(self) -> None:
        """MODA-01 / D-01 / D-02 / Pitfall #7: production train/holdout counts.

        Runs against data/feature/features_train.parquet (534,953 rows).
        Verifies the D-01 (2018-2024) / D-02 (2025-2026/5) window split with
        exclude_from_training=True removed from BOTH windows.
        Gated because it needs the real corpus (CI skips by default).
        """
        if os.environ.get("RUN_GATED") != "1":
            pytest.skip(
                "Set RUN_GATED=1 to run the gated test against the real "
                "features_train.parquet corpus"
            )
        result = load_features()  # default expected_counts=None asserts prod.
        md = result["metadata"]
        assert md["train_rows"] == PRODUCTION_COUNTS["train_rows"] == 322510, (
            f"train_rows mismatch: {md['train_rows']}"
        )
        assert md["train_races"] == PRODUCTION_COUNTS["train_races"] == 23288, (
            f"train_races mismatch: {md['train_races']}"
        )
        assert md["holdout_rows"] == PRODUCTION_COUNTS["holdout_rows"] == 66343, (
            f"holdout_rows mismatch: {md['holdout_rows']}"
        )
        assert md["holdout_races"] == PRODUCTION_COUNTS["holdout_races"] == 4740, (
            f"holdout_races mismatch: {md['holdout_races']}"
        )

    @pytest.mark.gated
    def test_grade_nan_preserved(self) -> None:
        """Pitfall #4: grade NaN count preserved through category conversion.

        Real features_train.parquet has 506,349 NaN grades (~95%, non-graded
        races). load_features converts grade to category; the NaN count must
        be identical before/after (verified internally in load_features; this
        test asserts the externally observable NaN count on the loaded frame).
        Gated because it needs the real corpus.
        """
        if os.environ.get("RUN_GATED") != "1":
            pytest.skip(
                "Set RUN_GATED=1 to run the gated test against the real "
                "features_train.parquet corpus"
            )
        result = load_features()
        combined = pd.concat([result["train"], result["holdout"]], ignore_index=True)
        # Grade NaN must be preserved through the category conversion. The
        # internal preservation assertion in load_features logs a warning if
        # before != after; we additionally verify the externally-observable
        # NaN count is the dominant value (~95% on the real corpus) and that
        # the dtype is category (Pitfall #3 + #4 together).
        assert combined["grade"].dtype.name == "category", (
            f"Pitfall #3/#4: grade must be category dtype, got {combined['grade'].dtype}"
        )
        nan_count = int(pd.isna(combined["grade"]).sum())
        total = len(combined)
        # ~95% of rows are non-graded races (grade is NaN). Allow a wide band
        # (>80%) so the test is robust to small corpus changes; the load_features
        # internal before==after assertion is the precise preservation check.
        assert nan_count / total > 0.80, (
            f"Pitfall #4: grade NaN ratio dropped below 80%: {nan_count}/{total}"
        )
        assert nan_count > 0, "Pitfall #4: grade NaN count is zero (filled?)"
