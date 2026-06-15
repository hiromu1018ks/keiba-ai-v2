# Phase 7: Model A -- Top-3 Probability - Pattern Map

**Mapped:** 2026-06-15
**Files analyzed:** 16（新規 `src/ml/` 7ファイル + `config/phase7_model_a.yaml` + `tests/ml/` 8ファイル）
**Analogs found:** 13 / 16（3ファイルは近接するデータ構造・型定義 analog でカバー）

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/ml/__init__.py` | package-init | — | `src/pipeline/__init__.py` | exact（re-export パターン） |
| `src/ml/data_loader.py` | service | file-I/O + transform | `src/pipeline/feature_generator.py`（load_and_merge + dtype 整備） | exact（同一 parquet 読込・categorical 変換・audit_leakage 再実行） |
| `src/ml/group_timeseries_split.py` | utility | transform | `sklearn.model_selection.BaseCrossValidator`（新規・独自実装） | role-match（D-03 要件。sklearn 互換インターフェースは RESEARCH.md Pattern 1） |
| `src/ml/trainer.py` | service | batch (training) | `src/pipeline/feature_generator.py::generate()`（オーケストレーション + loguru logger） | role-match（LightGBM 学習は新規だが、ステップ関数の積み上げパターンは同じ） |
| `src/ml/calibrator.py` | service | transform | `src/pipeline/feature_generator.py::compute_finish_time_zscore()`（race-boundary 安全な変換関数） | role-match（リーク防止境界を明示する点が類似） |
| `src/ml/evaluator.py` | service | transform | `src/pipeline/validators.py`（指標計算 + dict 返却） | role-match（評価指標の集約パターン） |
| `src/ml/baseline.py` | service | transform | `src/pipeline/feature_generator.py::compute_jockey_trainer_stats()`（groupby + merge 集計） | role-match（race_id 単位集計 + entry join のパターン） |
| `src/ml/run_train.py` | route (orchestrator) | batch | `src/pipeline/integration.py::integrate_standard_layer()`（エントリポイント・成果物保存・loguru） | exact（パイプラインオーケストレーション関数の構造が完全一致） |
| `config/phase7_model_a.yaml` | config | — | （新規・プロジェクト初の YAML config） | no-analog（pyyaml は pyproject.toml で依存宣言済みだが、読込パターンは RESEARCH.md Code Examples を踏襲） |
| `tests/ml/__init__.py` | package-marker | — | `tests/pipeline/__init__.py` | exact |
| `tests/ml/conftest.py` | test-fixture | — | `tests/pipeline/conftest.py`（hermetic fixture パターン） | exact（小規模 race データ fixture の作り方が完全一致） |
| `tests/ml/test_group_timeseries_split.py` | test | unit | `tests/pipeline/test_feature_generator.py::TestLoadMerge`（プロパティベース検証） | role-match（CV の境界・順序・グループ化の assert パターン） |
| `tests/ml/test_trainer.py` | test | unit (hermetic) | `tests/pipeline/test_feature_generator.py::TestEndToEnd`（hermetic で小規模データを生成して検証） | role-match（学習実行・early stopping 発火の assert） |
| `tests/ml/test_calibrator.py` | test | unit | `tests/pipeline/test_feature_generator.py::TestFinishTimeZscore`（race-boundary リーク防止のテスト設計） | role-match（リーク防止・[0,1] 範囲・単調非減少の assert） |
| `tests/ml/test_evaluator.py` | test | unit | `tests/schemas/test_audit.py`（指標計算の健全性テスト：完全予測=0・最悪=最大） | role-match（ECE 計算の健全性検証パターン） |
| `tests/ml/test_baseline.py` | test | unit | `tests/pipeline/test_feature_generator.py::TestJockeyTrainerStats`（groupby 集計の正しさ検証） | role-match（人気順位 AUC の join 健全性） |

---

## Pattern Assignments

### `src/ml/__init__.py` (package-init)

**Analog:** `src/pipeline/__init__.py` (25行)

**Re-export パターン** (lines 1-25):
```python
"""Data pipeline package for the 3-layer data architecture.

Re-exports key column mapping dicts and helper functions for downstream
phases to access via ``from src.pipeline import ...``.
"""

from src.pipeline.column_mapping import (
    KAGGLE_COLUMN_MAP,
    ...
)
from src.pipeline.validators import run_all_validations

__all__ = [
    "KAGGLE_COLUMN_MAP",
    ...
    "run_all_validations",
]
```

**planner 指示:** `src/ml/__init__.py` は公開 API を `__all__` で明示。Phase 7 完了時点では `from src.ml import run_train, GroupTimeSeriesSplit, train_fold_model, fit_calibrator, compute_ece` を想定。Phase 8/9 で import しやすいように、将来の下流フェーズ（Harville EV・walk-forward）が使う関数のみ公開する。Phase 4 パターン（`src/scraper/__init__.py` も同じ re-export 構造）に従う。

---

### `src/ml/data_loader.py` (service, file-I/O + transform)

**Analog:** `src/pipeline/feature_generator.py` (1026行)

**Imports パターン** (lines 25-34):
```python
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger

from src.schemas.audit import audit_leakage  # noqa: F401 -- used by generate()
from src.schemas.entry import EntrySchema  # noqa: F401
from src.schemas.race import RaceSchema  # noqa: F401
from src.schemas.result import ResultSchema  # noqa: F401
```

**Key point:** `from src.xxx import ...` の絶対パス import。`src.schemas.audit.audit_leakage` と `src.schemas.entry.EntrySchema` / `src.schemas.race.RaceSchema` を import して feature 読込後にリーク監査を再実行する。

**Parquet I/O パターン** (lines 780-803):
```python
def load_and_merge(standard_dir: Path) -> pd.DataFrame:
    """Read standard-layer Parquet files and merge into a single DataFrame."""
    standard_dir = Path(standard_dir)
    # T-03-01: Validate directory exists
    if not standard_dir.is_dir():
        raise FileNotFoundError(f"Standard directory not found: {standard_dir}")

    race_path = standard_dir / "race.parquet"
    # ...
    for p in [race_path, entry_path, result_path]:
        if not p.exists():
            raise FileNotFoundError(f"Required file not found: {p}")

    logger.info(f"Reading race.parquet from {race_path}")
    race_df = pd.read_parquet(race_path, engine="pyarrow")
    # ...
    logger.info(f"Loaded: race={len(race_df)} rows, entry={len(entry_df)} rows, result={len(result_df)} rows")
```

**planner 指示:** `data_loader.py` は `pd.read_parquet(path, engine="pyarrow")` を使用。`Path` を `Path()` でラップし、`is_dir()` / `exists()` で存在確認（T-03-01 パターン）。logger.info で読込元・行数を必ず出力（MEMORY.md scraper-logging-no-per-item に従い per-row ログは禁止、per-table ログのみ）。

**Categorical 変換パターン（Feature Generator は不十分 - Pitfall #3）** (lines 690-717):
```python
CATEGORICAL_COLUMNS = [
    "course_name", "surface", "direction", "weather", "track_condition",
    "sex", "jockey", "trainer", "grade",
]

def convert_to_categorical(df: pd.DataFrame) -> pd.DataFrame:
    """Convert CATEGORICAL_COLUMNS to pandas CategoricalDtype for LightGBM."""
    df = df.copy()
    for col in CATEGORICAL_COLUMNS:
        if col in df.columns and df[col].dtype == object:  # ← string dtype を見逃す
            df[col] = df[col].str.strip()
            df[col] = df[col].astype("category")
    return df
```

**CRITICAL (RESEARCH Pitfall #3):** `features_train.parquet` の実測 dtype（codebase 検証済み）:
```
course_name: string   surface: string   direction: string   weather: string
track_condition: string   grade: string   sex: string
jockey: category   trainer: category   ← 既に変換済み（feature_generator で処理）
```

`feature_generator.py::convert_to_categorical()` は `df[col].dtype == object` 条件で変換するが、Phase 6 統合 corpus は `string` dtype なので**7列が未変換**。Phase 7 の `data_loader.py` では、CATEGORICAL_COLUMNS の全列を無条件で `astype("category")` する（`feature_generator.CATEGORICAL_COLUMNS` を import して再利用）。`grade` は 95% NaN（506,349件）を含むため、変換後に `pd.isna(df["grade"]).sum()` が維持されているか assert で検証（Pitfall #4）。

**FEATURE_COLUMNS allowlist の再利用** (lines 94-107):
```python
FEATURE_COLUMNS = (
    RACE_FEATURES + HORSE_FEATURES + LAG_RAW_FEATURES + LAG_STAT_FEATURES
    + PERSON_FEATURES + DEBUT_FEATURE
)
# 78列。target/auxiliary は含まない
```

**planner 指示:** `data_loader.py` は `from src.pipeline.feature_generator import FEATURE_COLUMNS, CATEGORICAL_COLUMNS` を import して feature と整合する学習カラムを取得。feature 層の契約を feature_generator 側に維持し、Phase 7 は読むだけ（D-15 契約）。

**audit_leakage 再実行パターン** (lines 994-1003):
```python
# Step 12: Run leakage audit on prediction output
pred_col_set = set(FEATURE_COLUMNS + ENTITY_KEY)
pred_df_audit = df[[c for c in pred_col_set if c in df.columns]]
leaked = audit_leakage(
    [RaceSchema, EntrySchema], pred_df_audit, "pred output gate"
)
if leaked:
    logger.warning(f"Leakage detected in pred output: {leaked}")
```

**planner 指示:** `data_loader.py` で feature を読み込んだ直後に `audit_leakage([RaceSchema, EntrySchema], df, "phase7 feature load")` を呼び出し、post-race 列（popularity/win_odds 等）混入を再確認。ResultSchema は除外（race_id が post-race 扱いになるため）。leakage が見つかったら warning で止めず継続（D-12 互換）。

**horse_race_id derive パターン（Pitfall #2）:**
```python
# EntrySchema D-09: {race_id}_{horse_number:02d}
df["horse_race_id"] = df["race_id"] + "_" + df["horse_number"].astype(str).str.zfill(2)
```

**planner 指示:** features_train.parquet は horse_race_id を含まない（実測確認）。`race_id`（文字列）+ `horse_number`（Int64）から derive。標準 entry.parquet の horse_race_id と join して整合性を assert するテストを追加（Open Question #1 の推奨）。

---

### `src/ml/group_timeseries_split.py` (utility, transform)

**Analog:** RESEARCH.md Pattern 1（新規・sklearn BaseCrossValidator 準拠）

**sklearn 互換インターフェース** (RESEARCH.md lines 270-318):
```python
from sklearn.model_selection import BaseCrossValidator

class GroupTimeSeriesSplit(BaseCrossValidator):
    """race_id グループ単位で時系列 split する CV。"""
    def __init__(self, n_splits: int = 5):
        self.n_splits = n_splits

    def get_n_splits(self, X=None, y=None, groups=None):
        return self.n_splits

    def split(self, X, y=None, groups=None):
        if groups is None:
            raise ValueError("groups (race_id) は必須")
        unique_groups = pd.unique(groups)
        # ... fold 境界を race_id 単位で切る
        yield np.where(train_mask)[0], np.where(val_mask)[0]
```

**planner 指示:** 既存コードベースに cross-validator の analog はない。RESEARCH.md Pattern 1 のコードをベースにする（`_compute_fold_sizes` 含む）。mlxtend 依存を避け、独自実装で Phase 8/9 の walk-forward にも拡張可能な資産にする（CLAUDE.md「Use Instead: 必要なものだけ」）。docstring には D-03 要件（同一 race 同一 fold・race_date 時系列順）を明記。

---

### `src/ml/trainer.py` (service, batch training)

**Analog:** `src/pipeline/feature_generator.py::generate()` (lines 894-1025)

**オーケストレーション関数パターン** (lines 924-966):
```python
def generate(
    standard_dir: Path = Path("data/standard"),
    feature_dir: Path = Path("data/feature"),
) -> dict[str, Path]:
    """Generate feature-layer Parquet from standard-layer data."""
    logger.info("Starting feature generation pipeline")

    # Step 1: Load and merge
    df = load_and_merge(standard_dir)
    logger.info(f"Loaded and merged: {len(df)} rows")
    # ... 各ステップで logger.info を出す
    # Step 13-14: Write Parquet files
    feature_dir = Path(feature_dir)
    feature_dir.mkdir(parents=True, exist_ok=True)
    train_df.to_parquet(train_path, engine="pyarrow", index=False)
    logger.info(f"Wrote features_train.parquet: {len(train_df)} rows, {len(train_df.columns)} columns")

    return {"train": train_path, "pred": pred_path}
```

**planner 指示:** `trainer.py` は `train_fold_model(X_train, y_train, X_val, y_val, config) -> LGBMClassifier`（単 fold 学習）と `collect_oof_predictions(df, splitter, config) -> pd.DataFrame`（全 fold OOF 収集）と `train_final_model(df, config) -> LGBMClassifier`（全量再学習）を定義。各関数の冒頭で `logger.info(f"Training fold model: train={len(X_train)} rows")` を出力。

**early stopping callback（LightGBM 4.x API - Pitfall #1）** (RESEARCH.md lines 542-581):
```python
import lightgbm as lgb

def train_fold_model(X_train, y_train, X_val, y_val, config: dict) -> lgb.LGBMClassifier:
    """1 fold の学習。early stopping は callback で指定（4.x API）。

    CRITICAL: early_stopping_rounds は fit() に渡さない（4.x で削除）。
    callbacks=[lgb.early_stopping(stopping_rounds=N)] を使う。
    """
    m = config["model"]
    clf = lgb.LGBMClassifier(
        objective=m["objective"],
        num_leaves=m["num_leaves"],
        learning_rate=m["learning_rate"],
        # ... sensible defaults
        random_state=config["seed"],
        verbose=m["verbose"],
    )
    clf.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        callbacks=[
            lgb.early_stopping(
                stopping_rounds=es["stopping_rounds"],
                verbose=es["verbose"],
                first_metric_only=es["first_metric_only"],
            ),
            lgb.log_evaluation(period=50),
        ],
    )
    return clf
```

**planner 指示:** `early_stopping_rounds` を `fit()` に渡すと TypeError（LightGBM 4.x で削除済み・Pitfall #1 VERIFIED）。必ず `callbacks=[lgb.early_stopping(...)]` を使う。`best_iteration_` は callback 使用時のみ populated。

---

### `src/ml/calibrator.py` (service, transform)

**Analog:** `src/pipeline/feature_generator.py::compute_finish_time_zscore()` (lines 237-318)

**リーク防止境界の明示パターン**（analog の核心）:
```python
def compute_finish_time_zscore(df: pd.DataFrame) -> pd.DataFrame:
    """Compute finish_time z-score with race-boundary temporal safety.

    The z-score normalization operates at RACE BOUNDARY level to prevent
    same-race leakage. Each race's normalization parameters (mean, std)
    come from all prior races ... with no contribution from any runner
    in the current race.
    """
    # ... shift(1) で現レースを統計から除外
```

**Isotonic キャリブレーション（リーク防止）** (RESEARCH.md lines 340-375):
```python
import joblib
from sklearn.isotonic import IsotonicRegression

def fit_calibrator(oof_raw: np.ndarray, y_oof: np.ndarray) -> IsotonicRegression:
    """OOF 予測と実績から Isotonic キャリブレーターを学習。

    D-10/D-12 リーク防止:
    - oof_raw は各 fold モデルが学習していない馬の予測（GroupTimeSeriesSplit で保証）
    - したがってキャリブレーターは「未知データ上の予測分布」を学習
    """
    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    iso.fit(oof_raw, y_oof)
    return iso

def apply_calibrator(iso: IsotonicRegression, raw_preds: np.ndarray) -> np.ndarray:
    """キャリブレーターを適用（holdout にも使用可能、リークなし）。"""
    return iso.predict(raw_preds)

# 保存（D-15: .joblib）
# joblib.dump(iso, "models/phase7/isotonic_calibrator.joblib")
```

**planner 指示:** `calibrator.py` は IsotonicRegression の fit は OOF のみ、predict は holdout も可能な設計（Pitfall #5: holdout で再 fit するとリーク）。docstring にリーク防止理由を明記（analog の race-boundary safety docstring パターンに倣う）。保存は joblib.dump（`.joblib` 形式・D-15）。

---

### `src/ml/evaluator.py` (service, transform)

**Analog:** `src/pipeline/validators.py`（指標計算 + dict 返却）

**指標計算と dict 集約パターン** (lines 905-1068):
```python
def run_all_validations(...) -> dict[str, Any]:
    """Run all 8 D-05 validation checks and aggregate results."""
    logger.info(f"Running full validation suite on {parquet_dir}")
    # ... 各チェックを実行
    result = {
        "row_counts": row_pass,
        "schema_conformance": schema_pass,
        # ...
        "overall_pass": all_checks_passed,
        # Detailed results for inspection
        "row_counts_detail": row_counts_result,
    }
    if all_checks_passed:
        logger.info("All validation checks PASSED")
    else:
        failed = [k for k, v in result.items() if v is False and k != "overall_pass"]
        logger.warning(f"Validation failures: {failed}")
    return result
```

**ECE 計算（手動実装）** (RESEARCH.md lines 590-622):
```python
def compute_ece(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    """Expected Calibration Error を計算。

    ECE = Σ_m (|B_m| / N) × |acc(B_m) - conf(B_m)|
    """
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    bin_indices = np.digitize(y_prob, bins[1:-1], right=False)
    n = len(y_true)
    ece = 0.0
    for b in range(n_bins):
        mask = bin_indices == b
        if not mask.any():
            continue
        bin_size = mask.sum()
        acc = y_true[mask].mean()
        conf = y_prob[mask].mean()
        ece += (bin_size / n) * abs(acc - conf)
    return float(ece)
```

**planner 指示:** `evaluator.py` は sklearn.metrics（roc_auc_score / brier_score_loss / log_loss）と手動 ECE を組み合わせて `evaluate(y_true, y_prob_raw, y_prob_calibrated, n_bins=10) -> dict` を返す。analog の `run_all_validations` と同じく dict で結果を集約し、logger.info/warning で成功・失敗を出力。reliability diagram は matplotlib（Agg backend・Pitfall: ヘッドレス環境向け）。

---

### `src/ml/baseline.py` (service, transform)

**Analog:** `src/pipeline/feature_generator.py::compute_jockey_trainer_stats()` (lines 421-575)

**groupby 集計 + merge パターン** (lines 538-575):
```python
def compute_jockey_trainer_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Compute jockey and trainer rolling statistics."""
    df = df.copy()
    jockey_stats = _compute_person_stats(df, "jockey", "jockey_rolling_")
    df = df.merge(jockey_stats, on=["jockey", "race_id"], how="left")
    trainer_stats = _compute_person_stats(df, "trainer", "trainer_rolling_")
    df = df.merge(trainer_stats, on=["trainer", "race_id"], how="left")
    return df
```

**人気ベースライン AUC** (RESEARCH.md lines 666-702):
```python
from sklearn.metrics import roc_auc_score

def compute_popularity_baseline(
    features_df: pd.DataFrame, entry_df: pd.DataFrame
) -> dict:
    """人気（単勝オッズ順位）を score とした baseline AUC。

    D-07/D-08: 純粋馬特性モデルが市場集合知（人気）を AUC で超えるのは困難。
    baseline は参考情報（必須成功条件ではない）。
    """
    merged = features_df.merge(
        entry_df[["race_id", "horse_number", "popularity"]],
        on=["race_id", "horse_number"],
        how="inner",
    )
    valid = merged.dropna(subset=["popularity", "target_top3"])
    baseline_auc = roc_auc_score(
        valid["target_top3"].astype(int), -valid["popularity"].astype(float)
    )
    return {
        "baseline_auc": float(baseline_auc),
        "n_rows": len(valid),
        "note": "人気(単勝オッズ順位)ベースライン。D-08: 純粋モデルがこれを"
                "AUC で超えるのは競馬ML通説上非常に困難（参考情報）",
    }
```

**planner 指示:** `baseline.py` は entry.parquet の popularity（533,009 non-null / 1,944 NaN = 取消/除外馬・Pitfall #6）を features_train に join して AUC 計算。popularity NaN は drop（D-08: 参考情報なので厳密な rank→疑似確率変換は不要・`-popularity` を score とする）。docstring に D-08 の理論的骨格（純粋予測×EV 構図・人気ベースライン超えは困難）を明記。

---

### `src/ml/run_train.py` (route/orchestrator, batch)

**Analog:** `src/pipeline/integration.py::integrate_standard_layer()` (lines 176-451)

**エントリポイント関数パターン** (lines 176-220):
```python
def integrate_standard_layer(
    standard_dir: Path = Path("data/standard"),
    kaggle_input_dir: Path | None = None,
) -> dict:
    """Merge Kaggle + scraped corpora into a unified standard-layer corpus.

    Parameters
    ----------
    standard_dir : pathlib.Path, default ``Path("data/standard")``
        ...
    Returns
    -------
    dict
        ``{"race": Path, "entry": Path, "result": Path, "audit": {...}}``.
    Raises
    ------
    FileNotFoundError
        ...
    ValueError
        ...
    """
    standard_dir = Path(standard_dir)
    # ...
    logger.info(
        f"integrate_standard_layer: starting "
        f"(standard_dir={standard_dir!s}, kaggle_input_dir={kaggle_input_dir!s})"
    )
    # ... 各ステップ
    logger.info(
        f"integrate_standard_layer: complete -- wrote race/entry/result to "
        f"{standard_dir!s}"
    )
    return {
        "race": standard_dir / "race.parquet",
        # ...
    }
```

**成果物保存パターン** (lines 389-436):
```python
    # validate-before-swap with idempotent recovery
    staging_dir = Path(
        tempfile.mkdtemp(prefix=".integration_staging_", dir=str(standard_dir))
    )
    try:
        # Stage all 3 merged frames via atomic_write_parquet
        for table, merged in merged_by_table.items():
            atomic_write_parquet(merged, staging_dir / f"{table}.parquet")
        # ... validate staged files
        _commit_staging(staging_dir, standard_dir)
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)
```

**planner 指示:** `run_train.py` は `run_train(config_path: Path = Path("config/phase7_model_a.yaml")) -> dict` を定義。Numpy/pandas docstring スタイル（analog 準拠）。ステップ順序: (1) load_config (2) data_loader.load_features (3) GroupTimeSeriesSplit で OOF 収集 (4) fit_calibrator (5) train_final_model (6) holdout 評価 (7) 成果物保存（models/phase7/・data/model/oof/・reports/phase7/）。各ステップで `logger.info(f"run_train: step N - ...")`。戻り値は dict でパスを返す（analog 準拠）。`mkdir(parents=True, exist_ok=True)` で出力ディレクトリを作成。

**planner の裁量（成果物アトミック性）:** integration.py の atomic_write_parquet + validate-before-swap パターンは、53万行×78列の feature を再生成する Phase 3 のリスクに見合う設計。Phase 7 の成果物（モデル・OOF・report）は新規ディレクトリへの書き込みのみで既存ファイルの破壊リスクが低いため、シンプルに `pathlib.Path.mkdir(parents=True, exist_ok=True)` + `to_parquet` / `joblib.dump` / `booster.save_model` で十分。atomic_write は過剰（planner 判断）。

---

### `config/phase7_model_a.yaml` (config)

**Analog:** なし（プロジェクト初の YAML config）

**planner 指示:** RESEARCH.md Code Examples「Sensible Defaults Config YAML」(lines 454-525) をほぼそのまま採用。構造: `seed` / `data` / `cv` / `model` / `early_stopping` / `calibration` / `evaluation` / `artifacts`。読込は `run_train.py` で `yaml.safe_load(open(path))`（pyyaml 6.x・pyproject.toml で依存宣言済みだが明示的な依存追加は不要・setuptools なので pyproject.toml `[project] dependencies` は更新しない（libomp/sklearn/matplotlib/joblib のみ Wave 0 で追加））。

**固定 seed の再現性** (D-14):
```yaml
seed: 42
# ...
model:
  # ...
  random_state: config["seed"]  # ← trainer.py で参照
```

---

### `tests/ml/conftest.py` (test-fixture)

**Analog:** `tests/pipeline/conftest.py` (820行)

**小規模 fixture データパターン** (lines 23-35):
```python
@pytest.fixture
def sample_race_result_df() -> pd.DataFrame:
    """DataFrame mimicking race_result.csv with 10 rows and all 66 columns.

    Row breakdown:
    - 5 rows: 2015 flat races (2 unique race_ids: 2015A, 2015B, 2+3 horses each)
    # ...
    """
    data: dict[str, list] = {}
    data["レース馬番ID"] = [...]
    # ... 列ごとに data を構築
    return pd.DataFrame(data)
```

**planner 指示:** `conftest.py` は小規模 fixture（数レース・時系列順・categorical mix・target_top3 含む・18-30行程度）を定義。analog の `sample_standard_race_df` / `sample_standard_entry_df` / `sample_standard_result_df` と同じ構造だが、feature 層のカラム（prev_* / rolling_*）を含む点が異なる。各 fixture の docstring に「Key design」セクションでテスト観光点を明記（analog パターン）。`tmp_feature_dir` / `tmp_ml_output_dir` も定義。

**hermetic fixture の原則**（analog 全体）:
- 全て `@pytest.fixture` デコレータで関数として定義
- 外部データ（data/feature/features_train.parquet）に依存しない
- `tmp_path` を使って一時ディレクトリに Parquet を書き出す（`sample_feature_merged_df` パターン・lines 491-511）

---

### `tests/ml/test_group_timeseries_split.py` (test, unit)

**Analog:** `tests/pipeline/test_feature_generator.py::TestLoadMerge` (lines 95-145)

**プロパティベース検証パターン** (lines 106-134):
```python
def test_sort_order_globally_unique(
    self, sample_feature_merged_df: pd.DataFrame
) -> None:
    """Test 5: DataFrame sorted by [horse_entity_key, race_date, race_id]."""
    df = sample_feature_merged_df

    # Verify sort order: each consecutive pair should be in order
    for i in range(len(df) - 1):
        key_curr = df.iloc[i]["horse_entity_key"]
        key_next = df.iloc[i + 1]["horse_entity_key"]
        # ...
        if key_curr == key_next:
            if date_curr == date_next:
                assert rid_curr <= rid_next, (...)
```

**planner 指示:** テストケースは RESEARCH.md Test Map（lines 786-790）に準拠:
- `test_same_race_same_fold`（同一 race_id は同一 fold）
- `test_temporal_order`（race_date 昇順を厳守）
- `test_no_boundary_split`（境界割れ検出）
- `test_get_n_splits`（sklearn 互換）

クラス構造は `class TestGroupTimeSeriesSplit:`（analog の `class TestLoadMerge:` 準拠）。docstring に D-03 要件を引用。

---

### `tests/ml/test_trainer.py` (test, unit hermetic)

**Analog:** `tests/pipeline/test_feature_generator.py::TestEndToEnd` (lines 1584-1771)

**hermetic E2E パターン** (lines 1587-1728):
```python
def _generate_full_pipeline(self, tmp_path: Path) -> dict:
    """Helper: run full generate() with test fixtures as standard data."""
    from src.pipeline.feature_generator import generate
    standard_dir = tmp_path / "data" / "standard"
    feature_dir = tmp_path / "data" / "feature"
    standard_dir.mkdir(parents=True, exist_ok=True)
    feature_dir.mkdir(parents=True, exist_ok=True)
    # ... 小規模データを DataFrame として構築して Parquet 書き出し
    race_df.to_parquet(standard_dir / "race.parquet", engine="pyarrow", index=False)
    # ...
    return generate(standard_dir=standard_dir, feature_dir=feature_dir)

def test_features_train_contains_target_and_auxiliary(self, tmp_path: Path) -> None:
    """Test 4: features_train.parquet contains target_top3, ..."""
    paths = self._generate_full_pipeline(tmp_path)
    train_df = pd.read_parquet(paths["train"])
    assert "target_top3" in train_df.columns
```

**planner 指示:** `test_trainer.py` は hermetic fixture（conftest.py の小規模 race データ）で LightGBM 学習を実行。Wave 0 で `brew install libomp` 完了後に実行可能。テストケース: `test_train_fold_model_returns_classifier`（clf が返る）・`test_early_stopping_fires`（best_iteration_ < n_estimators）・`test_collect_oof_predictions`（OOF 行数 = 学習データ行数・fold 列が 0..4 の値を取る）。ML 学習は~1秒で完了するよう fixture を最小化（数レース・数fold）。

---

### `tests/ml/test_calibrator.py` (test, unit)

**Analog:** `tests/pipeline/test_feature_generator.py::TestFinishTimeZscore` (lines 1013-1297)

**リーク防止テスト設計パターン** (lines 1083-1142):
```python
def test_no_same_race_leakage(self) -> None:
    """Test 7: Runners in race N see normalization stats that EXCLUDE race N's own times.

    The race-boundary approach guarantees: norm_mean and norm_std for race N
    are computed from races 1..N-1 only.
    """
    # ... 十分な履歴を持つ fixture を構築
    df2 = self._make_many_race_fixture(num_races=7)
    result2 = compute_finish_time_zscore(df2)
    race7 = result2[result2["race_id"] == "R7"]
    # ... race 1-6 の手動計算と比較
```

**planner 指示:** `test_calibrator.py` は以下を検証:
- `test_leak_free_calibration`（OOF→iso.fit→holdout predict のリーク防止・Pitfall #5）
- `test_isotonic_output_in_01_range`（予測が [0, 1] に制限される）
- `test_isotonic_monotonic_non_decreasing`（予測が単調非減少）
- `test_holdout_ece_not_suspiciously_low`（holdout ECE が 0.0 に近すぎない＝リーク検出）

analog と同じく、手動で構築した小規模データで期待値を計算して比較するパターン。

---

### `tests/ml/test_evaluator.py` (test, unit)

**Analog:** `tests/schemas/test_audit.py`（指標計算の健全性テスト）

**健全性検証パターン** (lines 16-34):
```python
class TestGetPostRaceColumns:
    """Tests for get_post_race_columns function."""

    def test_entry_schema_returns_popularity_and_win_odds(self) -> None:
        """Test 1: get_post_race_columns(EntrySchema) returns popularity and win_odds."""
        result = get_post_race_columns(EntrySchema)
        assert result == {"popularity", "win_odds"}
```

**planner 指示:** `test_evaluator.py` は ECE 計算の健全性を検証（RESEARCH.md Test Map lines 793-794）:
- `test_ece_perfect_prediction`（完全予測 y_prob == y_true で ECE = 0.0）
- `test_ece_worst_case`（最悪ケースで ECE が [0, 1] 範囲）
- `test_ece_bin_weighting`（bin のサンプル割合が正しく重み付けされる）
- `test_reliability_diagram_generates_file`（画像が tmp_path に保存される）

analog と同じく、各テストの docstring に「Test N: ...」で期待動作を明記。

---

### `tests/ml/test_baseline.py` (test, unit)

**Analog:** `tests/pipeline/test_feature_generator.py::TestJockeyTrainerStats` (lines 391-738)

**groupby 集計の正しさ検証パターン** (lines 445-469):
```python
def test_sum_based_trainer_rate(self) -> None:
    """Test 4: Trainer with 3 runners (2 top-3, 1 not) produces rate 2/3 = 0.667."""
    df = self._make_person_stats_df()
    result = compute_jockey_trainer_stats(df)
    trainer_a_r2 = result[
        (result["trainer"] == "調教師A") & (result["race_id"] == "R2")
    ]
    assert len(trainer_a_r2) == 1
    row = trainer_a_r2.iloc[0]
    assert row["trainer_rolling_top3_rate"] == pytest.approx(2.0 / 3.0, abs=0.01), (...)
```

**planner 指示:** `test_baseline.py` は人気ベースライン AUC の正しさを検証:
- `test_popularity_baseline_auc`（人気順位と target_top3 が完全一致する fixture で AUC = 1.0）
- `test_popularity_baseline_random`（ランダムな人気順位で AUC ≈ 0.5）
- `test_popularity_nan_dropped`（popularity NaN 行が除外される・Pitfall #6）
- `test_join_integrity`（features_train と entry.parquet の join で行数が妥当）

analog と同じく、小規模 fixture（数レース・人気順位が既知）で期待 AUC を手動計算して比較。

---

## Shared Patterns

### loguru Logging Convention
**Source:** `src/pipeline/feature_generator.py` (lines 29, 793-1023) / `src/pipeline/integration.py` (lines 64, 226-438) / `src/schemas/audit.py` (lines 17, 76-83)
**Apply to:** 全 `src/ml/*.py` ファイル

```python
from loguru import logger

# パターン:
# - 各関数の冒頭で logger.info(f"Function name: starting (args=...)")
# - 各ステップ完了で logger.info(f"Step N: description complete")
# - ファイル読込/書込で logger.info(f"Reading/Writing X from/to {path}")
# - 行数を必ず含める: logger.info(f"Loaded: {len(df)} rows")
# - per-row ログは禁止（MEMORY.md scraper-logging-no-per-item）
# - warning は異常時のみ（leakage 検出・行数不一致等）
```

### audit_leakage 再実行（post-race 混入検出）
**Source:** `src/schemas/audit.py::audit_leakage()` (lines 45-84) / `src/pipeline/feature_generator.py` (lines 994-1003) / `src/pipeline/integration.py` (lines 353-388)
**Apply to:** `src/ml/data_loader.py`

```python
from src.schemas.audit import audit_leakage
from src.schemas.entry import EntrySchema
from src.schemas.race import RaceSchema

# feature 読込後に呼び出し
leaked = audit_leakage(
    [RaceSchema, EntrySchema], df, "phase7 feature load"
)
if leaked:
    logger.warning(f"Leakage detected during phase7 feature load: {leaked}")
# ResultSchema は除外（race_id が post-race 扱いになるため）
# D-12: warning のみで raise しない
```

### Parquet I/O + Path Validation
**Source:** `src/pipeline/feature_generator.py::load_and_merge()` (lines 757-820)
**Apply to:** `src/ml/data_loader.py` / `src/ml/run_train.py`

```python
from pathlib import Path
import pandas as pd

# T-03-01 パターン（feature_generator と integration.py で一貫）:
path = Path(path)
if not path.is_dir():
    raise FileNotFoundError(f"Directory not found: {path}")
for p in [path / "features_train.parquet"]:
    if not p.exists():
        raise FileNotFoundError(f"Required file not found: {p}")

df = pd.read_parquet(path, engine="pyarrow")
# engine="pyarrow" は全ファイルで明示（既存スタック）

# 書込:
path.parent.mkdir(parents=True, exist_ok=True)
df.to_parquet(path, engine="pyarrow", index=False)
```

### Pydantic BaseModel による型定義（DataFrame レベル一括処理）
**Source:** `src/schemas/result.py` / `src/schemas/entry.py` / CLAUDE.md「Pydantic BaseModel は型定義用、DataFrame レベルで一括処理（Phase 1 D-02）」
**Apply to:** 53万行の一括処理全般（Phase 7 は feature を読むだけなので新規 schema 定義不要）

```python
# Pydantic は型定義 ONLY。53万行を per-row validate しない。
# DataFrame レベルで処理する（pandas groupby/merge/astype）。
# EntrySchema.model_fields / ResultSchema.model_fields で
# カラム名・pre_race 分類を参照する（audit_leakage が利用）。
```

### Import Path Convention（絶対 import）
**Source:** `src/pipeline/feature_generator.py` (lines 31-34) / `src/pipeline/integration.py` (lines 67-75) / `src/pipeline/__init__.py`
**Apply to:** 全 `src/ml/*.py` ファイル

```python
# 絶対パス import（src. から始める）
from src.schemas.audit import audit_leakage
from src.schemas.entry import EntrySchema
from src.pipeline.feature_generator import FEATURE_COLUMNS, CATEGORICAL_COLUMNS

# `from src.ml.xxx import yyy` でパッケージ内参照
# __init__.py で __all__ を定義して公開 API を明示
```

### setuptools（Poetry ではない）
**Source:** `pyproject.toml` (lines 30-36) / MEMORY.md「Repo uses setuptools, not Poetry」
**Apply to:** Wave 0 の依存追加・実行コマンド

```toml
# pyproject.toml（setuptools・Poetry ではない）:
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

# 実行コマンド（poetry run を使わない）:
# python -m src.ml.run_train
# python -m pytest tests/ml/ -x -q
```

### Test Structure（hermetic + gated の2層）
**Source:** `tests/pipeline/conftest.py` / `tests/scraper/test_end_to_end.py::TestOptInLiveSmoke` (lines 713-738) / pyproject.toml markers (lines 44-46)
**Apply to:** `tests/ml/conftest.py` / `tests/ml/test_*.py`

```python
# hermetic unit test（デフォルト実行）:
# - 外部データ（data/feature/features_train.parquet）に依存しない
# - tmp_path で一時ディレクトリに小規模 fixture を書き出す
# - python -m pytest tests/ml/ -x -q で全て通る

# gated integration test（opt-in）:
# - pyproject.toml [tool.pytest.ini_options] markers に "gated" を追加
# - @pytest.mark.gated + fixture で LIVE_DATA=1 等の env var を要求
# - python -m pytest tests/ml/test_run_train.py -k e2e --run-gated で実行
# - features_train.parquet（53万行）を使った本格 E2E（RESEARCH.md Test Map line 796）

# 既存の @pytest.mark.live パターン（test_end_to_end.py:713）を踏襲:
@pytest.mark.gated
class TestE2ETraining:
    @pytest.fixture(autouse=True)
    def _require_gated_env(self) -> None:
        if os.environ.get("RUN_GATED") != "1":
            pytest.skip("Set RUN_GATED=1 to run gated E2E tests")
```

**planner 指示:** pyproject.toml の markers に `gated` を追加すること（既存 `live` marker と同列）。Wave 0 タスクに含める。

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `src/ml/group_timeseries_split.py` | utility | transform | 既存コードベースに cross-validator の analog なし。sklearn BaseCrossValidator 互換の独自実装（RESEARCH.md Pattern 1 のコードをベースにする）。 |
| `src/ml/trainer.py`（LightGBM 学習部分） | service | batch training | 既存コードベースに LightGBM 学習コードなし。RESEARCH.md Code Examples（lines 527-586）と LightGBM 4.6 公式ドキュメント（early_stopping callback API）を参照。オーケストレーション構造は analog あり（feature_generator.generate）。 |
| `config/phase7_model_a.yaml` | config | — | プロジェクト初の YAML config。既存コードベースに YAML 読込パターンなし。RESEARCH.md Code Examples（lines 454-525）と pyyaml 標準の `yaml.safe_load` を使用。 |

**RESEARCH.md 優先の領域:** 上記3ファイルは RESEARCH.md の Code Examples / Pattern 1-2 を直接参照すること。planner は analog から推測せず、RESEARCH.md の VERIFIED コードを plan に引用すること。

---

## Metadata

**Analog search scope:**
- `src/`（pipeline, schemas, scraper 全ディレクトリ）
- `tests/`（pipeline, schemas, scraper 全ディレクトリ）
- `pyproject.toml`（依存・pytest 設定・ruff/mypy 設定）
- `data/feature/features_train.parquet`（dtype・カラム構造の実測確認）

**Files scanned:** 18（analog 候補）+ features_train.parquet スキーマ検証

**Key codebase insights（RESEARCH.md と cross-check 済み）:**
- features_train.parquet: 534,953行 × 78列（target_top3 含む）。jockey/trainer のみ category 変換済み、他7列は string dtype（Pitfall #3 VERIFIED）
- `horse_race_id` は features_train.parquet に含まれない（Pitfall #2 VERIFIED）
- `grade` は 95% NaN（Pitfall #4 VERIFIED）
- `popularity` は entry.parquet に存在（533,009 non-null / 1,944 NaN・Pitfall #6 VERIFIED）

**Pattern extraction date:** 2026-06-15
