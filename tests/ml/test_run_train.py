"""Hermetic E2E tests for src.ml.run_train (Plan 07-07 Task 3).

TestRunTrainE2E exercises the full Wave 1+2 orchestration against a small
synthetic fixture written to ``tmp_path``. No external corpus is touched —
``expected_counts=[]`` (UNIFIED bypass sentinel, Cycle-2 HIGH #2 / Codex
HIGH #4) skips the production row-count assert.

Coverage:
- test_run_train_hermetic_e2e — full pipeline completes on a tiny fixture;
  all 6 D-15 artifacts exist; metrics.json has sane AUC/ECE ranges.
- test_oof_parquet_schema_and_row_count — OOF parquet column set matches
  D-15 contract EXACTLY; OOF row count < train-window row count (Codex
  HIGH #2 warm-up exclusion); fold values are {0..n_splits-1};
  metrics.json['oof_rows'] exists, is int, and matches the OOF parquet row
  count (Cycle-2 HIGH #3 producer/consumer contract).
- test_holdout_parquet_schema — holdout parquet has the same column set
  as OOF and fold == 'holdout'.
- test_artifacts_all_created — all 6 D-15 artifacts are present on disk.
- test_feature_columns_config_consistency — config/phase7_model_a.yaml
  data.feature_columns set-equals src.pipeline.feature_generator.
  FEATURE_COLUMNS (Codex HIGH #5).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

import pandas as pd
import pytest
import yaml

from src.pipeline.feature_generator import FEATURE_COLUMNS
from src.ml.run_train import run_train


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _build_train_feature_df(base_df: pd.DataFrame) -> pd.DataFrame:
    """Extend sample_feature_df to include EVERY FEATURE_COLUMNS column.

    sample_feature_df (conftest) ships only a representative subset of the
    lag/rolling columns. run_train resolves feature_columns from config
    (Codex HIGH #5) and asserts every column is present in the train frame.
    For the hermetic E2E we synthesize the missing columns with simple
    numeric defaults so the LightGBM fit is well-defined without depending
    on the real 534k-row corpus.
    """
    df = base_df.copy()
    for col in FEATURE_COLUMNS:
        if col not in df.columns:
            # Numeric default for lag/rolling stat columns; categorical
            # columns (jockey/trainer) are already present in the base df.
            df[col] = 0.0
    # Ensure the supporting columns run_train reads are present.
    if "horse_race_id" not in df.columns:
        df["horse_race_id"] = [
            f"{r['race_id']}{r['horse_number']:02d}"
            for r in df.to_dict("records")
        ]
    if "exclude_from_training" not in df.columns:
        df["exclude_from_training"] = 0
    # Coerce race_date to datetime (load_features + splitter require it).
    df["race_date"] = pd.to_datetime(df["race_date"])
    return df


def _build_holdout_feature_df(base_df: pd.DataFrame) -> pd.DataFrame:
    """Build a small holdout frame from sample_feature_df.

    The holdout rows are dated 2025+ so they fall inside the holdout window
    the tmp config declares. We reuse the base df but shift race_date into
    the holdout window and derive fresh race_ids.
    """
    df = base_df.copy()
    # Shift to 2025 holdout window
    holdout_dates = [
        "2025-01-15", "2025-03-20", "2025-05-10", "2025-07-01",
        "2025-09-05", "2025-11-20",
    ]
    race_ids = df["race_id"].unique().tolist()
    date_map = {rid: holdout_dates[i] for i, rid in enumerate(race_ids)}
    df["race_date"] = df["race_id"].map(date_map)
    df["race_date"] = pd.to_datetime(df["race_date"])
    # New race_ids in the 2025 namespace to avoid collision with train
    df["race_id"] = df["race_id"].astype(str).str.replace(
        "20", "25", n=1
    )
    if "horse_race_id" not in df.columns:
        df["horse_race_id"] = [
            f"{r['race_id']}{r['horse_number']:02d}"
            for r in df.to_dict("records")
        ]
    if "exclude_from_training" not in df.columns:
        df["exclude_from_training"] = 0
    # Extend with every FEATURE_COLUMNS column (same as train builder)
    for col in FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = 0.0
    # race_date column may have been overwritten by FEATURE_COLUMNS default
    # above if it was missing; reset to the mapped holdout dates.
    df["race_date"] = df["race_id"].map(
        {rid.replace("20", "25", 1): d for rid, d in date_map.items()}
    )
    df["race_date"] = pd.to_datetime(df["race_date"])
    return df


def _write_config_yaml(
    tmp_path: Path,
    *,
    feature_path: Path,
    entry_path: Path,
    model_dir: Path,
    oof_dir: Path,
    report_dir: Path,
    n_splits: int = 3,
) -> Path:
    """Write a shrunk config YAML pointing at tmp_path for every artifact."""
    cfg = {
        "seed": 42,
        "data": {
            "feature_path": str(feature_path),
            "entry_path": str(entry_path),
            "train_window": ["2018-01-01", "2024-12-31"],
            "holdout_window": ["2025-01-01", "2026-12-31"],
            "target_column": "target_top3",
            "exclude_column": "exclude_from_training",
            "feature_columns": list(FEATURE_COLUMNS),
            "categorical_columns": [
                "course_name", "surface", "direction", "weather",
                "track_condition", "sex", "jockey", "trainer", "grade",
            ],
            "drop_columns": [
                "race_id", "race_date", "horse_entity_key", "horse_name",
                "result_status", "is_dnf", "horse_number",
            ],
        },
        "cv": {
            "method": "group_timeseries",
            "n_splits": n_splits,
            "group_column": "race_id",
            "sort_column": "race_date",
            "early_stopping_val_ratio": 0.2,
        },
        "model": {
            "objective": "binary",
            "metric": ["binary_logloss", "auc"],
            "num_leaves": 8,
            "learning_rate": 0.1,
            "min_data_in_leaf": 2,
            "feature_fraction": 0.9,
            "bagging_fraction": 0.9,
            "bagging_freq": 5,
            "max_depth": -1,
            "lambda_l1": 0.0,
            "lambda_l2": 0.0,
            "min_gain_to_split": 0.0,
            "verbose": -1,
            "force_col_wise": True,
            "n_estimators": 30,
        },
        "early_stopping": {
            "stopping_rounds": 5,
            "verbose": False,
            "first_metric_only": False,
            "log_period": 50,
        },
        "calibration": {
            "method": "isotonic",
            "y_min": 0.0,
            "y_max": 1.0,
            "out_of_bounds": "clip",
            "fit_on": "oof",
        },
        "evaluation": {
            "ece_bins": 5,
            "ece_tolerance": 0.02,
            "reliability_diagram": True,
        },
        "artifacts": {
            "model_dir": str(model_dir),
            "oof_dir": str(oof_dir),
            "report_dir": str(report_dir),
            "model_filename": "model_a.lgb.txt",
            "calibrator_filename": "isotonic_calibrator.joblib",
            "oof_filename": "oof_predictions.parquet",
            "holdout_filename": "holdout_predictions.parquet",
            "metrics_filename": "metrics.json",
            "report_filename": "evaluation_report.md",
            "diagram_filename": "reliability_diagram.png",
        },
    }
    cfg_path = tmp_path / "phase7_model_a.yaml"
    with cfg_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)
    return cfg_path


@pytest.fixture
def run_train_artifacts(tmp_path, sample_feature_df, sample_entry_df):
    """Run run_train on a tiny hermetic fixture and return the paths dict +
    supporting artifacts for downstream assertions."""
    train_df = _build_train_feature_df(sample_feature_df)
    holdout_df = _build_holdout_feature_df(sample_feature_df)

    # The combined feature parquet MUST contain both train + holdout rows
    # because load_features splits by race_date window.
    combined = pd.concat([train_df, holdout_df], ignore_index=True)
    feature_path = tmp_path / "features_train.parquet"
    combined.to_parquet(feature_path, engine="pyarrow", index=False)

    # entry parquet: popularity + win_odds per (race_id, horse_number).
    # Build from the combined frame so the popularity-baseline join works
    # for BOTH train and holdout race_ids.
    entry_rows = []
    for r in combined.to_dict("records"):
        entry_rows.append({
            "horse_race_id": r["horse_race_id"],
            "race_id": r["race_id"],
            "horse_number": int(r["horse_number"]),
            "popularity": ((int(r["horse_number"]) % 4) + 1),
            "win_odds": 2.0 + (int(r["horse_number"]) % 6) * 1.5,
        })
    entry_df = pd.DataFrame(entry_rows)
    entry_path = tmp_path / "entry.parquet"
    entry_df.to_parquet(entry_path, engine="pyarrow", index=False)

    model_dir = tmp_path / "models" / "phase7"
    oof_dir = tmp_path / "data" / "model" / "oof"
    report_dir = tmp_path / "reports" / "phase7"

    cfg_path = _write_config_yaml(
        tmp_path,
        feature_path=feature_path,
        entry_path=entry_path,
        model_dir=model_dir,
        oof_dir=oof_dir,
        report_dir=report_dir,
        n_splits=3,
    )

    # Codex HIGH #4 / Cycle-2 HIGH #2: expected_counts=[] bypasses the
    # production row-count assert for hermetic fixtures.
    paths = run_train(config_path=cfg_path, expected_counts=[])
    return {
        "paths": paths,
        "cfg_path": cfg_path,
        "train_rows": len(train_df),
        "holdout_rows": len(holdout_df),
        "n_splits": 3,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRunTrainE2E:
    """E2E + contract tests for run_train (Plan 07-07 Task 3)."""

    def test_run_train_hermetic_e2e(self, run_train_artifacts):
        """Full pipeline completes on a tiny fixture; all artifacts exist.

        Codex HIGH #4: expected_counts=[] bypasses the production assert.
        """
        paths = run_train_artifacts["paths"]
        for key in ("model", "calibrator", "oof", "holdout",
                    "report", "metrics", "diagram", "config"):
            assert key in paths, f"missing return key: {key}"
            assert Path(paths[key]).is_file(), (
                f"artifact not on disk: {key}={paths[key]}"
            )

        # metrics.json has sane AUC/ECE ranges
        with Path(paths["metrics"]).open("r", encoding="utf-8") as f:
            metrics = json.load(f)
        assert 0.0 <= metrics["auc_calibrated"] <= 1.0, metrics["auc_calibrated"]
        assert 0.0 <= metrics["ece_calibrated"] <= 1.0, metrics["ece_calibrated"]
        assert metrics["n_samples"] > 0

    def test_oof_parquet_schema_and_row_count(self, run_train_artifacts):
        """OOF parquet schema = D-15 contract; rows < train-window total
        (Codex HIGH #2); metrics.json oof_rows contract (Cycle-2 HIGH #3).
        """
        paths = run_train_artifacts["paths"]
        oof_df = pd.read_parquet(paths["oof"], engine="pyarrow")

        expected_cols = {
            "race_id", "horse_race_id", "p_top3_raw", "p_top3_calibrated",
            "target_top3", "fold",
        }
        assert set(oof_df.columns) == expected_cols, (
            f"OOF columns mismatch: {set(oof_df.columns)} != {expected_cols}"
        )

        # Codex HIGH #2: warm-up chunk 0 excluded => oof rows < train rows
        train_rows = run_train_artifacts["train_rows"]
        assert len(oof_df) < train_rows, (
            f"OOF rows {len(oof_df)} must be < train rows {train_rows} "
            "(Codex HIGH #2: warm-up chunk 0 excluded)"
        )

        # fold values are exactly {0, 1, ..., n_splits-1}
        n_splits = run_train_artifacts["n_splits"]
        assert set(oof_df["fold"].unique()) == set(range(n_splits)), (
            f"fold values {set(oof_df['fold'].unique())} != "
            f"set(range({n_splits}))"
        )

        # Cycle-2 HIGH #3 producer/consumer contract: metrics.json has
        # oof_rows key of type int matching the OOF parquet row count.
        with Path(paths["metrics"]).open("r", encoding="utf-8") as f:
            metrics = json.load(f)
        assert "oof_rows" in metrics, (
            "metrics.json missing 'oof_rows' key "
            "(Cycle-2 HIGH #3 producer/consumer contract)"
        )
        assert isinstance(metrics["oof_rows"], int), (
            f"metrics['oof_rows'] must be int, got "
            f"{type(metrics['oof_rows']).__name__}"
        )
        assert metrics["oof_rows"] == len(oof_df), (
            f"metrics['oof_rows']={metrics['oof_rows']} != "
            f"len(oof_df)={len(oof_df)} (producer/consumer contract breach)"
        )

    def test_holdout_parquet_schema(self, run_train_artifacts):
        """Holdout parquet has the same schema as OOF; fold == 'holdout'."""
        paths = run_train_artifacts["paths"]
        holdout_df = pd.read_parquet(paths["holdout"], engine="pyarrow")

        expected_cols = {
            "race_id", "horse_race_id", "p_top3_raw", "p_top3_calibrated",
            "target_top3", "fold",
        }
        assert set(holdout_df.columns) == expected_cols, (
            f"holdout columns mismatch: {set(holdout_df.columns)}"
        )
        assert set(holdout_df["fold"].unique()) == {"holdout"}, (
            f"holdout fold must be 'holdout', got "
            f"{set(holdout_df['fold'].unique())}"
        )
        assert len(holdout_df) == run_train_artifacts["holdout_rows"], (
            f"holdout rows {len(holdout_df)} != "
            f"{run_train_artifacts['holdout_rows']}"
        )

    def test_artifacts_all_created(self, run_train_artifacts):
        """All 6 D-15 artifact categories exist on disk."""
        paths = run_train_artifacts["paths"]
        # (1) LightGBM .txt model
        assert Path(paths["model"]).is_file() and Path(paths["model"]).stat().st_size > 0
        # (2) Calibrator .joblib
        assert Path(paths["calibrator"]).is_file() and Path(paths["calibrator"]).stat().st_size > 0
        # (3) OOF parquet
        assert Path(paths["oof"]).is_file() and Path(paths["oof"]).stat().st_size > 0
        # (4) Holdout parquet
        assert Path(paths["holdout"]).is_file() and Path(paths["holdout"]).stat().st_size > 0
        # (5) Reliability diagram PNG
        assert Path(paths["diagram"]).is_file() and Path(paths["diagram"]).stat().st_size > 0
        # (6) evaluation_report.md + metrics.json
        assert Path(paths["report"]).is_file() and Path(paths["report"]).stat().st_size > 0
        assert Path(paths["metrics"]).is_file() and Path(paths["metrics"]).stat().st_size > 0
        # config referenced (not copied)
        assert Path(paths["config"]).is_file()

    def test_feature_columns_config_consistency(self):
        """config/phase7_model_a.yaml data.feature_columns set-equals
        src.pipeline.feature_generator.FEATURE_COLUMNS (Codex HIGH #5)."""
        cfg_path = Path("config/phase7_model_a.yaml")
        assert cfg_path.is_file(), "config/phase7_model_a.yaml not found"
        with cfg_path.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert "feature_columns" in cfg["data"], (
            "Codex HIGH #5: data.feature_columns key missing in config"
        )
        cfg_cols = set(cfg["data"]["feature_columns"])
        src_cols = set(FEATURE_COLUMNS)
        assert cfg_cols == src_cols, (
            f"config feature_columns != FEATURE_COLUMNS\n"
            f"  only in config: {cfg_cols - src_cols}\n"
            f"  only in FEATURE_COLUMNS: {src_cols - cfg_cols}"
        )
