---
phase: 07-model-a-top-3-probability
plan: 05
subsystem: ml-calibrator
tags: [wave-1, isotonic-calibration, leak-prevention, joblib-persistence, pitfall-5, codex-high-2]
requires:
  - "07-01 (tests/ml scaffold + conftest fixtures + pyproject deps)"
  - "07-03 (GroupTimeSeriesSplit date-block chunking — produces OOF val-chunk predictions consumed by fit_calibrator)"
provides:
  - "src.ml.calibrator.fit_calibrator(oof_raw, y_oof) -> IsotonicRegression (OOF = validation chunks only, warm-up excluded — Codex HIGH #2 documented in docstring)"
  - "src.ml.calibrator.apply_calibrator(iso, raw_preds) -> np.ndarray (predict-only, no labels accepted — Pitfall #5 structural guard)"
  - "src.ml.calibrator.save_calibrator(iso, path) -> Path (joblib.dump, D-15 .joblib)"
  - "src.ml.calibrator.load_calibrator(path) -> IsotonicRegression (joblib.load, FileNotFoundError on missing)"
  - "TestCalibrator with 4 GREEN tests (leak-free + [0,1] range + monotonic non-decreasing + .joblib round-trip)"
affects:
  - "07-06 evaluator consumes apply_calibrator for holdout calibrated predictions (ECE<0.02 success criterion D-11)"
  - "07-07 run_train orchestrates fit_calibrator(oof_raw, y_oof) -> save_calibrator -> apply_calibrator(holdout)"
  - "Phase 8 Harville EV consumes p_top3_calibrated (calibrator-applied) — accuracy depends on leak-free fit"
  - "Phase 9 walk-forward reuses calibrator pattern on rolling OOF"
tech_stack:
  added: []
  patterns:
    - "IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds='clip') — D-10 [0,1] clip + monotonic non-decreasing"
    - "Pitfall #5 structural guard: apply_calibrator accepts ONLY (iso, raw_preds) — no API path for holdout labels to reach fit"
    - "Codex HIGH #2 docstring contract: oof_raw = validation chunks (1..n_splits) only, warm-up chunk 0 excluded (in-sample), len(oof_raw) < training-window row count is the leak-free state"
    - "inspect.signature assertion in test for forward-compatibility of the leak-free API surface"
    - "joblib.dump/load for D-15 .joblib persistence (NOT pickle)"
    - "FileNotFoundError fail-loud on missing calibrator (Rule 2: explicit over silent unfitted estimator at Phase 8 EV time)"
key_files:
  created:
    - src/ml/calibrator.py
  modified:
    - tests/ml/test_calibrator.py
decisions:
  - "[Phase 07 P05]: apply_calibrator signature is (iso, raw_preds) ONLY — Pitfall #5 enforced structurally (no labels parameter exists), not just by convention. test_leak_free_calibration uses inspect.signature to lock this for forward compatibility."
  - "[Phase 07 P05]: fit_calibrator adds input validation — ValueError on oof_raw/y_oof length mismatch and on non-1-D oof_raw. Rule 2 (missing critical functionality): a length mismatch would otherwise silently broadcast or raise a confusing sklearn error downstream."
  - "[Phase 07 P05]: load_calibrator raises FileNotFoundError (not generic OSError or silent None) on missing path — at Phase 8 Harville EV time, a missing calibrator must fail loud rather than return an unfitted estimator that would produce identity-like outputs."
  - "[Phase 07 P05]: Wave 0 skeleton shipped 3 tests; plan requires 4. 4th test test_save_load_roundtrip ADDED in Task 2 (not just unskipped) — covers D-15 .joblib round-trip + FileNotFoundError. _manual_ece helper kept local to test module; canonical ECE implementation belongs to 07-06 evaluator (no duplication)."
  - "[Phase 07 P05]: Codex HIGH #2 (OOF = validation chunks only, warm-up excluded) is a docstring contract in calibrator.py, NOT a runtime assertion — the len(oof_raw) < training-window check is the caller's responsibility (07-04 collect_oof_predictions) because calibrator.py cannot know the training-window row count. Documented explicitly in fit_calibrator docstring."
metrics:
  duration: 792s
  completed: 2026-06-15
  tasks: 2
  files: 2
---

# Phase 7 Plan 05: calibrator / Isotonic OOF→holdout Summary

OOF 予測で IsotonicRegression を学習しホールドアウトに適用するリーク防止キャリブレーター（fit/apply/save/load 4関数）を実装。RESEARCH Pattern 2 + Pitfall #5 を構造的にエンコードし、Codex HIGH #2（OOF = validation chunks のみ・warm-up 除外）を docstring 契約で明確化。MODA-04 キャリブレーション中核が完成。

## What Was Built

### Task 1 — src/ml/calibrator.py (commit 3c7bf40)
- **4関数**を実装（202行、min_lines=55 を充足）:
  - `fit_calibrator(oof_raw, y_oof) -> IsotonicRegression`: `IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(...)`。入力検証（長不一致・非1D で ValueError）+ loguru で fit 行数・raw 範囲・iso X_min_/X_max_ を出力。
  - `apply_calibrator(iso, raw_preds) -> np.ndarray`: `iso.predict(raw_preds)` のみ。**Pitfall #5 構造防止**: シグネチャは `(iso, raw_preds)` のみで holdout ラベルを受け取る経路が存在しない。
  - `save_calibrator(iso, path) -> Path`: `path.parent.mkdir(parents=True, exist_ok=True)` + `joblib.dump(iso, path)`（D-15 .joblib 形式・pickle ではない）。
  - `load_calibrator(path) -> IsotonicRegression`: path 存在確認 + `joblib.load(path)`。**FileNotFoundError fail-loud**（Rule 2: Phase 8 EV 計算時にキャリブレーター欠落は無言ではなく明示的失敗）。
- **リーク防止 docstring**（analog: `compute_finish_time_zscore` の race-boundary safety docstring・PATTERNS.md 指示）:
  - D-10/D-12: oof_raw は各 fold モデルが学習していない馬の予測（GroupTimeSeriesSplit 保証）。holdout は predict のみ・Pitfall #5。
  - **Codex HIGH #2**: oof_raw は validation chunks（chunks 1..n_splits）のみ。warm-up chunk 0 は expanding window で OOF 対象外（in-sample 予測になるため除外）。`len(oof_raw) < 学習窓全行数` が正常。warm-up 行に予測を強制すると Isotonic キャリブレーションがリークする。

### Task 2 — tests/ml/test_calibrator.py (commit cceb30a)
- 07-01 Wave 0 skip skeleton（3テスト）の skip を外し、**4テスト目 `test_save_load_roundtrip` を新規追加**（plan は4テスト要求・skeleton は3テストのみ）。4テスト全 GREEN。
  - `test_leak_free_calibration`: `inspect.signature(apply_calibrator)` が `(iso, raw_preds)` のみ・`inspect.signature(fit_calibrator)` が `(oof_raw, y_oof)` のみを assert（Pitfall #5 構造防止の前方互換ロック）。calibrator が identity でないことを assert（identity なら holdout で fit した可能性・Pitfall #5 リーク指標）。`_manual_ece` で OOF ECE が [0,1] かつ人工的に完全でないことを確認。
  - `test_isotonic_output_in_01_range`: `np.array([-10, -1, 0, 0.5, 1.5, 10, 1e6])` の極端入力で出力が全て `[0,1]` に clip（D-10 out_of_bounds='clip'）。`np.isfinite` で NaN/inf なし。
  - `test_isotonic_monotonic_non_decreasing`: `np.array([0.1, 0.2, 0.3, 0.5, 0.8])` で `np.diff(result) >= 0`（IsotonicRegression 単調非減少保証）。
  - `test_save_load_roundtrip`: `tmp_ml_output_dir/isotonic_calibrator.joblib` に save → load → apply 結果が保存前と `np.allclose`。`FileNotFoundError` を `pytest.raises`（Rule 2 fail-loud）。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Wave 0 skeleton shipped only 3 tests; plan requires 4**
- **Found during:** Task 2（07-01 SUMMARY は「TestCalibrator (3)」と宣言、plan は4テスト要求）
- **Issue:** Wave 0 (07-01) は `TestCalibrator` に3テスト（leak_free / 01_range / monotonic）のみ scaffold した。plan 07-05 の `<behavior>` と `<acceptance_criteria>` は4テスト（加えて `test_save_load_roundtrip`）を要求。Task 2 の `<action>` は「skip を外し実装する」と記載するが、4テスト目は存在しなかったため単なる skip 解除では不足。
- **Fix:** Task 2 で3テストの skip を外す実装を書くだけでなく、`test_save_load_roundtrip`（D-15 .joblib round-trip + FileNotFoundError）を新規追加。各テストに MODA-04 / D-10 / D-12 / D-15 / Pitfall #5 / Codex HIGH #2 引用の docstring を付与。
- **Files modified:** tests/ml/test_calibrator.py（3テストの skip 解除 + 1テスト新規 + クラス docstring）
- **Commit:** cceb30a

**2. [Rule 2 - Missing critical functionality] Input validation + fail-loud load missing**
- **Found during:** Task 1（plan `<action>` は RESEARCH Pattern 2 VERIFIED コードをベースにしたが、入力検証と load_calibrator の存在確認が明示要求されていない）
- **Issue:** RESEARCH Pattern 2 の素朴な fit_calibrator は `oof_raw`/`y_oof` 長不一致や非1D 入力を sklearn にそのまま渡し、混乱しやすい内部エラーになる。また load_calibrator で存在しないパスを joblib.load すると FileNotFoundError ではなく、joblib 内部の不可解なエラーになる可能性。
- **Fix:** fit_calibrator に長不一致・非1D の ValueError 検証を追加。load_calibrator に明示的な `if not path.exists(): raise FileNotFoundError(...)` を追加（Phase 8 EV 計算時の fail-loud）。
- **Files modified:** src/ml/calibrator.py
- **Commit:** 3c7bf40

## Verification

| Check | Command | Result |
|-------|---------|--------|
| Task 1 imports | `python -c "from src.ml.calibrator import fit_calibrator, apply_calibrator, save_calibrator, load_calibrator; print('ok')"` | ok |
| Task 1 manual round-trip | inline python: fit→apply→save→load→apply | holdout calibrated [0. 0.5 1. 1.], round-trip np.allclose OK |
| Task 2 calibrator tests | `python -m pytest tests/ml/test_calibrator.py -x -q` | 4 passed in 0.54s |
| Task 2 tests/ml/ coexistence | `python -m pytest tests/ml/ -q` | 17 passed, 14 skipped, 0 failed (07-02/07-03 と並存) |
| Full suite regression | `python -m pytest tests/ -q` | 530 passed, 15 skipped, 0 failed (445s) |
| grep IsotonicRegression | `grep -c IsotonicRegression src/ml/calibrator.py` | 17 (>=1) |
| grep [0,1] clip config | `grep -cE "y_min=0.0\|y_max=1.0\|out_of_bounds" src/ml/calibrator.py` | 4 (>=1) |
| grep joblib.dump/load | `grep -cE "joblib.dump\|joblib.load" src/ml/calibrator.py` | 3 (>=2) |
| grep leak/warm-up/OOF/holdout docstring | `grep -cE "OOF\|holdout\|リーク\|leak\|validation chunk\|warm-up" src/ml/calibrator.py` | 27 (>=2) |
| min_lines | `wc -l src/ml/calibrator.py` | 202 (>=55) |
| test_isotonic_output_in_01_range assert | manual code review | `(result >= 0.0).all() and (result <= 1.0).all()` ✓ |
| test_isotonic_monotonic_non_decreasing assert | manual code review | `np.diff(result) >= 0` ✓ |
| apply_calibrator leak-free signature | `inspect.signature(apply_calibrator).parameters` | ['iso', 'raw_preds'] (Pitfall #5 structural) |
| fit_calibrator leak-free signature | `inspect.signature(fit_calibrator).parameters` | ['oof_raw', 'y_oof'] (Pitfall #5 structural) |
| TDD RED→GREEN commits | git log | test(07-05) cceb30a after feat(07-05) 3c7bf40 (Wave 0 skeleton was the RED gate) |

## Known Stubs

None. 4関数全てが本番 OOF/holdout 予測に対して完全に動作する。Pitfall #5（holdout 再 fit リーク）は apply_calibrator シグネチャで構造的に防止済み。Codex HIGH #2（OOF = val chunks のみ・warm-up 除外）は fit_calibrator docstring 契約で明確化済み。D-10（[0,1] clip + 単調非減少）・D-12（calibrator 保存 + p_top3_raw 併存契約）・D-15（.joblib 形式）を満たす。Phase 8 Harville EV 計算の精度に直結する安全側設計が完成。

## Threat Flags

None. T-07-05-01..04 は全て disposition=mitigate で実装内に反映:
- T-07-05-01 (Pitfall #5 holdout recalibration): apply_calibrator は `(iso, raw_preds)` のみ受け取り holdout ラベルの経路が存在しない（構造的防止）。inspect.signature テストで前方互換ロック。
- T-07-05-02 (Codex HIGH #2 OOF all-rows leakage): fit_calibrator docstring に OOF = validation chunks（1..n_splits）のみ・warm-up chunk 0 除外を明記。len(oof_raw) < training-window row count が正常と明示。
- T-07-05-03 (D-12 .joblib 形式): save_calibrator は joblib.dump（pickle ではない）。test_save_load_roundtrip で .joblib round-trip 検証。
- T-07-05-04 (範囲違反): IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds='clip')。test_isotonic_output_in_01_range で極端入力 [-10, 1e6] が [0,1] clip されることを検証。

## Self-Check: PASSED

- Created/modified files exist:
  - FOUND: src/ml/calibrator.py
  - FOUND: tests/ml/test_calibrator.py
- Commits exist:
  - FOUND: 3c7bf40 (Task 1 calibrator implementation)
  - FOUND: cceb30a (Task 2 unskip + 4th test + Rule 2 input validation/load fail-loud)
