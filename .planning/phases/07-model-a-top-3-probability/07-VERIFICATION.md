---
phase: 07-model-a-top-3-probability
verified: 2026-06-16T00:00:00Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: n/a
  gaps_closed: []
  gaps_remaining: []
  regressions: []
---

# Phase 7: Model A — Top-3 Probability Verification Report

**Phase Goal:** A LightGBM model predicts each horse's probability of finishing in the top 3, trained on 2018-2024 data (D-05), validated with race-grouped temporal cross-validation (GroupTimeSeriesSplit), calibrated via Isotonic regression (holdout ECE < 0.02 per D-11), and compared against a popularity-rank baseline on holdout as reference information (D-07/D-08 — beating the baseline is NOT a required gate because the pure-properties model excludes odds).
**Verified:** 2026-06-16
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| #   | Truth (ROADMAP SC) | Status | Evidence |
| --- | --- | --- | --- |
| 1 | LightGBM binary classifier outputs p_top3, trained on 2018-2024 data with temporal splits (D-05/D-01; holdout = 2025-01〜2026-05 per D-02) | ✓ VERIFIED | `models/phase7/model_a.lgb.txt` is a real LightGBM Booster (v4, objective=binary sigmoid, 164 trees, 69 features). `config/phase7_model_a.yaml` train_window=2018-01-01..2024-12-31, holdout_window=2025-01-01..2026-05-31. `train_final_model` (trainer.py:357) implements the two-stage full retrain on ALL 322,510 train rows. Holdout parquet = 66,343 rows / 4,740 races, 0 race_id overlap with train window. holdout_predictions.parquet carries `p_top3_raw`/`p_top3_calibrated`. |
| 2 | GroupTimeSeriesSplit (race_id-grouped, n_splits+1 expanding-window chunks) for all CV; no future data in any training fold (temporal-order assertion enforced on real execution path) | ✓ VERIFIED | `src/ml/group_timeseries_split.py` implements `GroupTimeSeriesSplit(BaseCrossValidator)` with the n_splits+1 date-block chunk scheme (`_compute_date_block_sizes`). Per-fold runtime assertion at line 283: `assert max(train_dates) < min(val_dates)` ALWAYS fires because `collect_oof_predictions` (trainer.py:301) forwards `dates=df["race_date"]` explicitly. `test_dates_arg_assertion_always_fires` + `test_temporal_order` pass; assertion raises `AssertionError` on out-of-order input (verified via pytest.raises). OOF data confirms 0 races span multiple folds (19,462 OOF races × nunique fold = 1 each). |
| 3 | Holdout AUC compared against popularity-rank baseline as reference info (beating baseline NOT a gate); baseline reported in evaluation_report.md | ✓ VERIFIED | `src/ml/baseline.py::compute_popularity_baseline` joins entry.popularity and computes `roc_auc_score(target_top3, -popularity)`. `run_train.py:296-303` writes `metrics["baseline_auc"]` and `metrics["baseline_n_rows"]`. `reports/phase7/metrics.json` records `baseline_auc=0.8100`, `baseline_n_rows=66343`. `reports/phase7/evaluation_report.md:16-17` reports the baseline and explicitly notes D-08 "純粋予測×EV 構図" (beating baseline is NOT required). D-07 note explicitly says reference-only. |
| 4 | OOF calibrated via Isotonic (fit on OOF val chunks only, warm-up excluded); holdout ECE < 0.02 (D-11), verified via reliability diagram; oof_rows recorded in metrics.json (producer/consumer contract) | ✓ VERIFIED | `src/ml/calibrator.py` fits `IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip")` on OOF only. Structural leak-prevention: `apply_calibrator(iso, raw_preds)` does NOT accept labels (Pitfall #5 impossible). `reports/phase7/metrics.json` records `ece_calibrated=0.0062 < 0.02 (D-11)` ✓, `oof_rows=268648`. `reliability_diagram.png` is a real 820x819 PNG (494 distinct colors, non-blank). OOF=268,648 < train window 322,510 (warm-up chunk 0 excluded — Codex HIGH #2). Calibrator X range [0.0074, 0.8322] EXACTLY matches OOF p_top3_raw range; holdout range [0.0078, 0.8602] extends beyond, confirming holdout was NOT used in calibration fit. |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `models/phase7/model_a.lgb.txt` | Real trained LightGBM model | ✓ VERIFIED | 913k; v4 binary sigmoid booster, 164 trees, 69 features, reload via `lgb.Booster(model_file=...)` succeeds |
| `models/phase7/isotonic_calibrator.joblib` | IsotonicRegression fit on OOF only | ✓ VERIFIED | 4.8k; y_min=0 y_max=1 out_of_bounds=clip; X range matches OOF exactly |
| `data/model/oof/oof_predictions.parquet` | OOF predictions (val chunks only, warm-up excluded) | ✓ VERIFIED | 268,648 rows × 6 cols (race_id, horse_race_id, p_top3_raw, p_top3_calibrated, target_top3, fold); folds=[0,1,2,3,4]; < 322,510 |
| `data/model/oof/holdout_predictions.parquet` | Holdout predictions | ✓ VERIFIED | 66,343 rows × 6 cols; fold="holdout" |
| `reports/phase7/metrics.json` | All metrics incl. oof_rows | ✓ VERIFIED | Strict JSON; auc_calibrated=0.7669, ece_calibrated=0.0062, baseline_auc=0.8100, oof_rows=268648, n_samples=66343 |
| `reports/phase7/reliability_diagram.png` | Reliability diagram | ✓ VERIFIED | 820x819 RGBA PNG, 494 distinct colors |
| `reports/phase7/evaluation_report.md` | Evaluation report with D-08 framing + holdout retune prohibition | ✓ VERIFIED | Contains D-08 純粋予測×EV note, D-11 ECE row, baseline row, holdout retune prohibition (Cycle-2 LOW) |
| `src/ml/data_loader.py` | load_features with audit_leakage + race_date sort | ✓ VERIFIED | Lines 154-158 audit_leakage, 141-148 sort+monotonicity assert, PRODUCTION_COUNTS=322510/23288/66343/4740 |
| `src/ml/group_timeseries_split.py` | GroupTimeSeriesSplit BaseCrossValidator | ✓ VERIFIED | 401 lines; date-block chunking; runtime temporal-order assertion |
| `src/ml/trainer.py` | train_fold_model + collect_oof_predictions + train_final_model | ✓ VERIFIED | LightGBM 4.x callback API (early_stopping), dates=df["race_date"] forwarded, two-stage full retrain |
| `src/ml/calibrator.py` | Isotonic leak-free pattern | ✓ VERIFIED | apply_calibrator signature blocks holdout recalibration structurally |
| `src/ml/evaluator.py` | compute_ece + evaluate + reliability_diagram | ✓ VERIFIED | Hand-rolled ECE (sklearn unimpl), NaN-safe (WR-04), single-class-safe (CR-01) |
| `src/ml/baseline.py` | compute_popularity_baseline | ✓ VERIFIED | NaN-safe (Pitfall #6), D-08 reference framing |
| `src/ml/run_train.py` | Orchestrator | ✓ VERIFIED | 9-step pipeline, all 6 D-15 artifacts persisted, oof_rows producer/consumer contract |
| `config/phase7_model_a.yaml` | Config with feature_columns + drop_columns | ✓ VERIFIED | seed=42, train/holdout windows, n_splits=5, feature_columns=69 items, drop_columns excludes identifiers/targets |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `run_train.py` | `data_loader.load_features` | `from src.ml.data_loader import load_features` | ✓ WIRED | run_train.py:66 import; called at line 189 |
| `run_train.py` | `GroupTimeSeriesSplit` | `from src.ml.group_timeseries_split import GroupTimeSeriesSplit` | ✓ WIRED | run_train.py:68 import; instantiated at line 226 |
| `run_train.py` | `trainer.collect_oof_predictions` | explicit feature_columns arg | ✓ WIRED | run_train.py:69 import; called at line 227 with feature_columns=feature_columns |
| `run_train.py` | `trainer.train_final_model` | explicit feature_columns arg | ✓ WIRED | called at line 246 with feature_columns=feature_columns |
| `run_train.py` | `calibrator.fit_calibrator` / `apply_calibrator` | leak-free boundary | ✓ WIRED | fit on OOF only (line 239), apply to holdout (line 260); apply signature structurally blocks holdout recalibration |
| `run_train.py` | `evaluator.evaluate` + `reliability_diagram` | — | ✓ WIRED | evaluate at line 269, reliability_diagram at line 364 |
| `run_train.py` | `baseline.compute_popularity_baseline` | — | ✓ WIRED | line 297; writes metrics["baseline_auc"], ["baseline_n_rows"] |
| `data_loader.py` | `schemas.audit.audit_leakage` | `from src.schemas.audit import audit_leakage` | ✓ WIRED | line 67 import; called at line 154 |
| `data_loader.py` | `feature_generator.CATEGORICAL_COLUMNS` | — | ✓ WIRED | line 66 import; consumed at lines 166-168 |
| `trainer.py` | `group_timeseries_split.split_train_validation` | module-level import | ✓ WIRED | line 101 module-level import; used in collect_oof_predictions (line 309) and train_final_model (line 390) |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| --- | --- | --- | --- | --- |
| `oof_predictions.parquet` (p_top3_raw) | per-fold clf.predict_proba | LightGBM Booster trained on 322,510 real rows | Yes (mean=0.2137, std=0.1522, 268,228 unique values) | ✓ FLOWING |
| `oof_predictions.parquet` (p_top3_calibrated) | apply_calibrator(iso, p_top3_raw) | IsotonicRegression fit on OOF | Yes (range [0.0, 1.0], real monotonic map) | ✓ FLOWING |
| `holdout_predictions.parquet` (p_top3_raw) | final_clf.predict_proba(holdout) | Two-stage final model trained on full 2018-2024 window | Yes (mean=0.2112, std=0.1591, base rate match) | ✓ FLOWING |
| `metrics.json` (auc_calibrated) | evaluate(holdout) on real holdout | Real predictions vs real target_top3 labels | Yes (0.7669, both classes present n=66,343) | ✓ FLOWING |
| `metrics.json` (ece_calibrated) | compute_ece on holdout | Real predictions | Yes (0.0062 < 0.02) | ✓ FLOWING |
| `metrics.json` (baseline_auc) | compute_popularity_baseline | entry.parquet popularity join on holdout | Yes (0.8100, n=66,343, post-dropna) | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| LightGBM booster reloads with trees | `lgb.Booster(model_file=...)` | 164 trees, 69 features, binary sigmoid | ✓ PASS |
| Real data predictions are non-degenerate | read parquet, compute stats | OOF mean=0.2137 std=0.1522; 268,228 unique values | ✓ PASS |
| Same-race-same-fold invariant | `oof.groupby('race_id').fold.nunique() > 0` count | 0 races span multiple folds | ✓ PASS |
| Train/holdout race_id disjointness | set intersection | 0 overlap | ✓ PASS |
| OOF < train window (warm-up excluded) | row count compare | 268,648 < 322,510 | ✓ PASS |
| Calibrator fit on OOF only | calibrator X range vs OOF range | Exact match [0.0074, 0.8322]; holdout extends to [0.0078, 0.8602] | ✓ PASS |
| Holdout ECE < 0.02 (D-11) | metrics.json | 0.0062 < 0.02 | ✓ PASS |
| Holdout AUC ≥ 0.75 (D-07 目安) | metrics.json | 0.7669 ≥ 0.75 | ✓ PASS |
| Reliability diagram is non-blank PNG | PIL open + distinct colors | 820x819 RGBA, 494 distinct colors | ✓ PASS |

### Probe Execution

| Probe | Command | Result | Status |
| --- | --- | --- | --- |
| Full phase 7 test suite | `python -m pytest tests/ml/ -q` | 37 passed, 2 skipped | PASS |
| Temporal-order assertion test | `pytest test_dates_arg_assertion_always_fires + test_temporal_order` | 7 passed | PASS |
| Calibrator leak-prevention suite | `pytest tests/ml/test_calibrator.py` | PASS | PASS |

Note: 2 skipped tests are gated integration tests requiring `RUN_GATED=1` and the real `features_train.parquet` corpus — intentional gating, not failures. The 07-08 phase-gate run already validated the real corpus (production row counts in metrics.json confirm it).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| MODA-01 | 07-02, 07-04, 07-07, 07-08 | LightGBM 3着内確率モデル構築、各馬のp_top3出力 | ✓ SATISFIED | model_a.lgb.txt is a real LightGBM binary classifier outputting p_top3; run_train orchestrates full training; data_loader loads features; trainer implements train_fold_model + two-stage train_final_model |
| MODA-02 | 07-03, 07-07, 07-08 | TimeSeriesSplit による時系列CV、未来データリーク防止 | ✓ SATISFIED | GroupTimeSeriesSplit(BaseCrossValidator) with race_id grouping + date-block chunking + runtime temporal-order assertion; OOF data shows 0 fold boundary violations; tests verify assertion fires |
| MODA-03 | 07-06, 07-07, 07-08 | 人気順ベースライン比較でモデル確率の優位性確認 | ✓ SATISFIED | compute_popularity_baseline joins entry.popularity, reports baseline_auc=0.8100 as reference info in evaluation_report.md; D-08 framing documented (NOT a success gate) |
| MODA-04 | 07-05, 07-06, 07-07, 07-08 | OOF 確率キャリブレーション、推定確率と的中率一致確認 | ✓ SATISFIED | IsotonicRegression fit on OOF val chunks only (warm-up excluded); holdout ECE=0.0062 < 0.02 (D-11); reliability diagram generated; oof_rows=268648 in metrics.json |

No orphaned requirements. All 4 MODA IDs in REQUIREMENTS.md map to Phase 7 and are claimed by the plans.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| (none) | — | — | — | No TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER markers in src/ml/. No empty stub implementations. No placeholder strings. |

### Human Verification Required

The D-11 success criterion and D-07 reference framing are automatically verified via metrics.json (ECE=0.0062 < 0.02, AUC=0.7669). The reliability diagram is a non-blank PNG and ECE confirms calibration success numerically. No additional human verification is required for the phase gate. Phase 7 07-08 PLAN explicitly defers the human verify of D-07/D-11/D-15 to this phase gate — those are satisfied by the metrics.json numerical evidence (machine-verifiable, not a subjective visual quality check).

### Gaps Summary

No gaps. All 4 ROADMAP Success Criteria are met with codebase + data evidence. All 4 MODA requirements satisfied. All 6 D-15 artifacts exist, are substantive, are wired, and have real data flowing through. Calibration leak-prevention is structurally enforced (apply_calibrator signature). Temporal-order assertion fires on the real execution path (dates=df["race_date"] forwarded explicitly). Holdout ECE=0.0062 < 0.02 (D-11). AUC=0.7669 ≥ 0.75 目安 (D-07). oof_rows=268648 recorded (Cycle-2 HIGH #3 producer/consumer contract).

---

_Verified: 2026-06-16_
_Verifier: Claude (gsd-verifier)_
