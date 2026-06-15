"""Shared pytest fixtures for Phase 7 ML tests.

Provides hermetic (no external data) fixtures that reproduce the feature-layer
column structure so Wave 1 src/ml/ modules can be tested against realistic
categorical mixes and target_top3 without touching the 534k-row real corpus.

Fixtures:
- sample_feature_df: small (~20 rows, 6 races) feature-layer reproduction
- sample_entry_df: small entry table with popularity/win_odds + NaN rows
- tmp_ml_output_dir: tmp_path output directory for OOF/model/artifact writes
- ml_config: in-memory dict mirroring config/phase7_model_a.yaml structure

Key design (analog: tests/pipeline/conftest.py hermetic fixtures):
- ~20 rows / 6 races keeps each LightGBM training test under ~1 second
- Race dates span 2018-2024 so train/holdout time windows are exercisable
- Categorical mix per feature_generator.CATEGORICAL_COLUMNS:
    * course_name / surface / direction / weather / track_condition / sex / grade
      -> plain string dtype (NaN allowed on grade)
    * jockey / trainer -> pandas CategoricalDtype (the dtype LightGBM auto-detects)
- target_top3 + exclude_from_training + horse_number + race_id + race_date
  are present so data_loader / trainer / evaluator can select and audit them.
- popularity/win_odds/horse_race_id live in sample_entry_df (joined later in
  data_loader tests) -- kept SEPARATE so leakage audit on sample_feature_df
  has no post-race columns by construction.

MEMORY.md scraper-logging-no-per-item is respected: fixtures carry no logger
state. T-07: no network I/O anywhere.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def _build_feature_rows() -> list[dict]:
    """Build ~20 feature rows across 6 races dated 2018-2024 (time-sorted).

    Race layout (race_id, race_date, n_horses):
      201801010101  2018-01-01   4 horses  (train window start)
      201906060301  2019-06-06   3 horses
      202003030401  2020-03-03   4 horses
      202109090101  2021-09-09   3 horses
      202305050301  2023-05-05   3 horses
      202411110201  2024-11-11   3 horses  (most recent -> holdout window)

    This date spread lets GroupTimeSeriesSplit tests verify temporal ordering
    and trainer tests verify a non-trivial train/holdout window gap.
    """
    rows: list[dict] = []
    # (race_id, race_date, course, surface, direction, weather, track, grade,
    #  field_size, n_horses, base_jockeys, base_trainers)
    race_specs = [
        ("201801010101", "2018-01-01", "東京", "芝", "左", "晴", "良", None, 4),
        ("201906060301", "2019-06-06", "中山", "ダート", "右", "曇", "稍重", "G3", 3),
        ("202003030401", "2020-03-03", "京都", "芝", "右", "雨", "重", None, 4),
        ("202109090101", "2021-09-09", "東京", "芝", "左", "晴", "良", "G1", 3),
        ("202305050301", "2023-05-05", "阪神", "ダート", "右", "曇", "良", None, 3),
        ("202411110201", "2024-11-11", "京都", "芝", "左", "晴", "良", "G2", 3),
    ]
    jockeys_pool = ["騎手A", "騎手B", "騎手C", "騎手D", "騎手E"]
    trainers_pool = ["調教師X", "調教師Y", "調教師Z", "調教師W"]
    # finish_position per row: 1,2,3,4,... cycling so top-3 is well-defined
    horse_n = 0
    for r_idx, (rid, rdate, course, surface, direction, weather, track,
               grade, field_size) in enumerate(race_specs):
        for h in range(field_size):
            horse_n += 1
            pos = h + 1  # 1..field_size
            target = 1 if pos <= 3 else 0
            rows.append({
                "race_id": rid,
                "race_date": rdate,
                "course_name": course,
                "distance": [2000, 1400, 1600, 1800, 1200, 2200][r_idx],
                "surface": surface,
                "direction": direction,
                "weather": weather,
                "track_condition": track,
                "race_number": 1 + r_idx,
                "grade": grade,  # may be None (NaN) -> Pitfall #4 NaN preserved
                "field_size": field_size,
                "bracket_num": h + 1,
                "horse_number": h + 1,
                "sex": ["牡", "牝", "セ", "牡", "牝"][horse_n % 5],
                "age": 3 + (horse_n % 5),
                "weight_assigned": 55.0 + (horse_n % 3),
                "horse_weight": 460 + (horse_n % 4) * 10,
                "weight_change": (horse_n % 3) - 1,
                # Lag raw features (subset representative)
                "prev_1_finish_position": float((horse_n % 5) + 1),
                "prev_1_last_3f": 34.5 + (horse_n % 4) * 0.3,
                "prev_1_corner_4": float((horse_n % 4) + 1),
                "prev_1_finish_time_zscore": ((horse_n % 5) - 2) * 0.4,
                "prev_1_margin_numeric": float(horse_n % 3),
                # Lag stat features (representative subset)
                "prev3_finish_position_mean": 3.0 + (horse_n % 3) * 0.5,
                "prev5_last_3f_mean": 34.8 + (horse_n % 3) * 0.2,
                # Jockey/trainer rolling
                "jockey": jockeys_pool[horse_n % len(jockeys_pool)],
                "trainer": trainers_pool[horse_n % len(trainers_pool)],
                "jockey_rolling_top3_rate": 0.4 + (horse_n % 4) * 0.05,
                "jockey_rolling_win_rate": 0.15 + (horse_n % 3) * 0.03,
                "jockey_rolling_rides": float(20 + horse_n),
                "trainer_rolling_top3_rate": 0.35 + (horse_n % 4) * 0.04,
                "trainer_rolling_win_rate": 0.12 + (horse_n % 3) * 0.02,
                "trainer_rolling_rides": float(18 + horse_n),
                # Debut flag
                "is_debut": 1 if horse_n % 7 == 0 else 0,
                # Targets / flags (NOT model features but required by trainer/
                # evaluator selection)
                "target_top3": target,
                "exclude_from_training": 0,
            })
    return rows


@pytest.fixture
def sample_feature_df() -> pd.DataFrame:
    """Hermetic feature-layer reproduction (~20 rows, 6 races, 2018-2024).

    Key design:
    - 6 races / ~20 rows -> LightGBM training completes in <1s on this fixture
    - race_date spans 2018-01-01..2024-11-11 so train/holdout windows split cleanly
    - categorical mix per feature_generator.CATEGORICAL_COLUMNS:
        * course_name/surface/direction/weather/track_condition/sex/grade
          stay as plain Python strings (NaN on grade preserved for Pitfall #4)
        * jockey/trainer coerced to pandas CategoricalDtype so LightGBM's
          native categorical path is exercised (D-16: native categoricals,
          no one-hot)
    - target_top3 + exclude_from_training present so trainer/evaluator/baseline
      can select them directly
    - NO popularity/win_odds columns here (those live in sample_entry_df) so a
      leakage audit on this DataFrame returns empty by construction
    """
    df = pd.DataFrame(_build_feature_rows())
    # Apply the dtypes LightGBM must auto-detect (D-16: native categoricals)
    for col in ["jockey", "trainer"]:
        df[col] = df[col].astype("category")
    # grade stays object/string with NaN preserved (Pitfall #4 test guards this)
    return df


@pytest.fixture
def sample_entry_df() -> pd.DataFrame:
    """Hermetic entry table with popularity/win_odds/horse_race_id.

    Key design:
    - One row per (race_id, horse_number) in sample_feature_df so a join is 1:1
    - horse_race_id derived as f"{race_id}{horse_number:02d}" (Pitfall #2 authority)
    - popularity has 2 NaN rows (cancel/scratched reproduction) so Pitfall #6
      (NaN drop in popularity baseline) is exercisable
    - win_odds present for baseline AUC comparison (D-06: post-race market signal)
    """
    df = pd.DataFrame(_build_feature_rows())
    entry = pd.DataFrame({
        "horse_race_id": [f"{r['race_id']}{r['horse_number']:02d}"
                          for r in df.to_dict("records")],
        "race_id": df["race_id"].values,
        "horse_number": df["horse_number"].values,
        "popularity": [((i % 4) + 1 if i % 5 != 0 else np.nan)
                       for i in range(len(df))],
        "win_odds": [2.0 + (i % 6) * 1.5 for i in range(len(df))],
    })
    return entry


@pytest.fixture
def tmp_ml_output_dir(tmp_path: Path) -> Path:
    """Empty output directory for OOF predictions / model artifacts / diagrams."""
    out = tmp_path / "ml_output"
    out.mkdir(parents=True, exist_ok=True)
    return out


@pytest.fixture
def ml_config() -> dict:
    """Minimal in-memory config mirroring config/phase7_model_a.yaml structure.

    Values deliberately small (num_leaves=31, n_estimators=50, stopping_rounds=10)
    so Wave 1 hermetic trainer tests finish in <1s. RESEARCH.md "Sensible Defaults
    Config YAML" is the structural authority; this fixture is the test-shrunk version.

    Keys (mirrors the YAML top-level sections):
        seed / data / cv / model / early_stopping / calibration / evaluation / artifacts
    """
    return {
        "seed": 42,
        "data": {
            "train_start": "2018-01-01",
            "train_end": "2023-12-31",
            "holdout_start": "2024-01-01",
            "holdout_end": "2024-12-31",
        },
        "cv": {
            "method": "group_timeseries",
            "n_splits": 5,
            "group_col": "race_id",
            "time_col": "race_date",
        },
        "model": {
            "objective": "binary",
            "metric": "binary_logloss",
            "num_leaves": 31,
            "learning_rate": 0.05,
            "min_data_in_leaf": 20,
            "n_estimators": 50,
            "feature_fraction": 0.9,
            "bagging_fraction": 0.9,
            "bagging_freq": 5,
            "verbose": -1,
            "force_col_wise": True,
        },
        "early_stopping": {
            "stopping_rounds": 10,
            "stopping_metric": "binary_logloss",
            "first_metric_only": True,
        },
        "calibration": {
            "method": "isotonic",
            "fit_on": "oof",
        },
        "evaluation": {
            "n_bins": 10,
            "reliability_diagram": True,
        },
        "artifacts": {
            "model_filename": "model_a.lgbm",
            "oof_filename": "oof_predictions.parquet",
            "calibrator_filename": "calibrator.joblib",
            "reliability_filename": "reliability_diagram.png",
        },
    }
