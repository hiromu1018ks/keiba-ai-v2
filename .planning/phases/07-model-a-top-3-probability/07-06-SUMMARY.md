---
phase: 07-model-a-top-3-probability
plan: 06
subsystem: ml-evaluator-baseline
tags: [wave-1, ece, auc, reliability-diagram, matplotlib-agg, popularity-baseline, pitfall-6, d-06, d-08, d-11, cycle-5-medium-d09]
requires:
  - "07-01 (tests/ml scaffold + conftest fixtures + pyproject matplotlib/sklearn deps)"
  - "07-05 (apply_calibrator — produces holdout calibrated preds consumed by evaluate)"
provides:
  - "src.ml.evaluator.compute_ece(y_true, y_prob, n_bins=10) -> float (Guo et al. 2017 ECE, hand-rolled — sklearn #18268 open)"
  - "src.ml.evaluator.evaluate(y_true, y_prob_raw, y_prob_calibrated, n_bins=10) -> dict (AUC/Brier/logloss/ECE raw+calibrated + n_samples; D-06 主指標 AUC)"
  - "src.ml.evaluator.reliability_diagram(y_true, y_prob, n_bins=10, save_path=None) -> matplotlib.figure.Figure (Agg backend PNG, D-11)"
  - "src.ml.baseline.compute_popularity_baseline(features_df, entry_df) -> dict (entry.popularity join + dropna Pitfall #6 + -popularity AUC; D-08 参考情報)"
  - "TestEvaluator (5 GREEN tests): ece_perfect / ece_worst / ece_bin_weighting / evaluate_dict / reliability_png"
  - "TestBaseline (4 GREEN tests): popularity_auc / popularity_random / nan_dropped / join_integrity"
affects:
  - "07-07 run_train consumes evaluate() metrics dict + reliability_diagram for D-11 phase-gate artifacts + compute_popularity_baseline for D-08 reference AUC"
  - "07-08 phase gate: D-11 ECE<0.02 success criterion read from evaluate()['ece_calibrated'] + reliability PNG artifact"
  - "Phase 8 Harville EV: p_top3_calibrated accuracy depends on evaluator-reported ece_calibrated (lower = better EV)"
  - "Phase 9 walk-forward reuses evaluate() metrics schema (auc/brier/logloss/ece raw+calibrated) for ROI-vs-AUC framing"
tech_stack:
  added: []
  patterns:
    - "compute_ece hand-rolled per Guo et al. 2017 (sklearn #18268 open — ECE is the documented Don't-Hand-Roll exception)"
    - "np.digitize with bins[1:-1] boundaries → final bin closed [0.9,1.0], others half-open [low,high) — matches RESEARCH VERIFIED code"
    - "evaluate() dict-aggregation analog: src/pipeline/validators.run_all_validations (logger.info on success, logger.warning on D-11 smell ece_calibrated>=0.02)"
    - "reliability_diagram: function-local matplotlib.use('Agg') + import (module-level import would pull matplotlib into every evaluator call; Agg = headless-safe, T-07-06-03 accept)"
    - "compute_popularity_baseline: dropna(subset=['popularity','target_top3']) BEFORE roc_auc_score (Pitfall #6 — 1,944 scratched/withdrawn rows; T-07-06-01 mitigate)"
    - "score = -popularity (lower rank = stronger; roc_auc_score treats higher score = positive)"
    - "D-08 docstring framing: 純粋予測×EV backbone (03-CONTEXT D-15 — feature excludes odds/popularity); baseline out-performance is RARE, reference-only, NOT a Phase 7 success criterion (D-07)"
key_files:
  created:
    - src/ml/evaluator.py
    - src/ml/baseline.py
  modified:
    - tests/ml/test_evaluator.py
    - tests/ml/test_baseline.py
decisions:
  - "[Phase 07 P06]: D-09 race-level Top-3 recall deferred to 07-07 run_train (Cycle-5 MEDIUM carry-over option (b)). evaluate() operates purely on (y_true, y_prob_raw, y_prob_calibrated) arrays with no race grouping — race_id is required for Top-3 recall but kept out of evaluate()'s signature to preserve array-only unit-testability (PATTERNS.md analog tests/schemas/test_audit.py). 07-07 run_train retains race_id and computes D-09 there. The D-09 reference in Task-1 read_first is honored as background context, not as an evaluate() responsibility."
  - "[Phase 07 P06]: compute_ece returns 0.0 + logger.warning on empty input (n=0) rather than raising — defensive against a degenerate holdout slice that would otherwise propagate a confusing numpy mean-of-empty error. ECE bounds [0,1] verified: perfect=0.0, worst-case (maximally wrong)=1.0."
  - "[Phase 07 P06]: evaluate() emits logger.warning when ece_calibrated >= 0.02 (D-11 violation smell, T-07-06-02). This is a reporting signal only — the actual leak prevention lives in calibrator.apply_calibrator (Pitfall #5 structural, no labels param)."
  - "[Phase 07 P06]: reliability_diagram uses function-local matplotlib.use('Agg') + import (not module-level) so that compute_ece/evaluate never pay the matplotlib import cost. Headless-safe for CLI runs (T-07-06-03 accept)."
  - "[Phase 07 P06]: Wave 0 skeleton shipped only 3 TestBaseline tests; plan requires 4. 4th test test_popularity_baseline_random ADDED in Task 2 (not just unskipped) — validates random popularity ≈ AUC 0.5 (chance-level), guarding against a trivially-high baseline artifact. Mirrors the 07-05 P05 Wave-0-shipped-3-plan-requires-4 deviation pattern."
  - "[Phase 07 P06]: compute_popularity_baseline returns baseline_auc=0.5 + n_rows=0 + explanatory note when ALL rows are NaN (defensive, not crash). Empty-valid path would otherwise raise ZeroDivisionError or roc_auc_score ValueError on a degenerate all-scratched fixture."
metrics:
  duration: 533s
  completed: 2026-06-16
  tasks: 2
  files: 4
---

# Phase 7 Plan 06: evaluator + baseline / ECE + AUC + reliability Summary

sklearn metrics（AUC/Brier/logloss）+ 手動 ECE（Guo et al. 2017・sklearn #18268 未収録）+ matplotlib Agg reliability diagram と、人気ベースライン AUC（Pitfall #6 NaN 安全）を実装。MODA-04 評価ティアと MODA-03 人気ベースライン比較の評価関数群が完成。D-06（主指標 AUC）・D-11（ECE<0.02 + reliability diagram）・D-08（純粋予測×EV 参考情報）契約を満たす。

## What Was Built

### Task 1 — src/ml/evaluator.py (commit 80ecb5f)
- **3関数**を実装（232行、min_lines=80 を充足）:
  - `compute_ece(y_true, y_prob, n_bins=10) -> float`: RESEARCH Code Examples lines 596-622 の VERIFIED コード採用。Guo et al. 2017 の ECE 定義。`bins = np.linspace(0, 1, n_bins+1)`、`bin_indices = np.digitize(y_prob, bins[1:-1], right=False)`（最終 bin 閉区間 [0.9,1.0]・それ以外半開区間）。完全予測で 0.0・最悪で [0,1]。空入力で 0.0 + logger.warning（防御的）。
  - `evaluate(y_true, y_prob_raw, y_prob_calibrated, n_bins=10) -> dict`: analog `run_all_validations` の dict 集約パターン。`roc_auc_score` / `brier_score_loss` / `log_loss` を raw と calibrated 両方で計算（D-06 主指標 AUC）。`compute_ece` も raw/calibrated 両方。戻り値 keys: `auc_raw, auc_calibrated, brier_raw, brier_calibrated, logloss_raw, logloss_calibrated, ece_raw, ece_calibrated, n_samples`。logger.info で全指標出力・`ece_calibrated >= 0.02` で logger.warning（D-11 違反徴候・T-07-06-02）。
  - `reliability_diagram(y_true, y_prob, n_bins=10, save_path=None) -> Figure`: RESEARCH Code Examples lines 625-661 の VERIFIED コード採用。**関数内 `import matplotlib; matplotlib.use('Agg')`**（ヘッドレス・モジュールレベル import で compute_ece/evaluate に matplotlib コストを押し付けない）。bins 別 acc/confs/sizes 計算・空 bin は中心点 + NaN 高さ。`fig.savefig(save_path, dpi=150, bbox_inches='tight')`。title/xlabel/ylabel 完備。
- **D-09 race-level Top-3 recall は 07-07 run_train に繰越**（Cycle-5 MEDIUM option (b)）。evaluate() のシグネチャは `(y_true, y_prob_raw, y_prob_calibrated)` で race グループ情報を持たないため、race_id を要する D-09 は evaluate() 内で計算不可。read_first の D-09 参照は背景文脈として尊重し、実装責任からは明示的に除外。docstring + ファイルヘッダで決定根拠を明記。
- **Pitfall #5 境界**: evaluator は読み取り専用（fit しない）。holdout 再キャリブレーションのリークリスクは calibrator.py の apply_calibrator（labels 受け取らず）で構造防止済み。evaluate は ECE を *報告* のみ。docstring に T-07-06-02 境界明記。

### Task 2 — src/ml/baseline.py + tests skip 解除 (commit d4e9253)
- **baseline.py 1関数**を実装（121行、min_lines=40 を充足）:
  - `compute_popularity_baseline(features_df, entry_df) -> dict`: RESEARCH Code Examples lines 674-701 準拠。`features_df.merge(entry_df[['race_id','horse_number','popularity']], on=[...], how='inner')` → **`dropna(subset=['popularity','target_top3'])`**（Pitfall #6 — 取消/除外馬 1,944件相当・`roc_auc_score` の `ValueError` 防止・T-07-06-01 mitigate）→ `roc_auc_score(target_top3, -popularity)`（score=-popularity・人気順位小=強）。戻り値 `{baseline_auc, n_rows, note}`。logger.info で baseline_auc/n_rows/dropped 行数。
  - **D-08 docstring に理論的骨格を明記**: 純粋馬特性モデル（feature からオッズ除外・03-CONTEXT D-15）が市場集合知（人気＝単勝オッズ順位）を AUC で超えるのは競馬 ML 通説上非常に困難（稀）。baseline は参考情報（D-07 で必須成功条件ではない）。真の EV 優位性は Phase 9 ROI で検証。
  - **防御的空ハンドリング**: 全行 NaN の場合 baseline_auc=0.5 + n_rows=0 + 説明 note（crash しない）。
- **test_evaluator.py skip 解除**（5テスト）:
  - `test_ece_perfect_prediction`: y_prob==y_true で ECE==0.0（pytest.approx(abs=1e-12)）。
  - `test_ece_worst_case`: 最悪ケース（y_true=[0,0,1,1], y_prob=[1,1,0,0]）で ECE が有限かつ [0,1]。
  - `test_ece_bin_weighting`: 非対称 fixture（bin 0 に 9件・bin 9 に 1件）で手動計算 `0.9*|1/9-0.05| + 0.1*|1-0.05|` と一致・unweighted mean と不一致（重み付け検証）。
  - `test_evaluate_returns_metrics_dict`: 9 keys subset・D-06 `auc_calibrated` + D-11 `ece_calibrated` 存在・全指標範囲チェック・auc_calibrated>=0.7（分離容易 fixture）。
  - `test_reliability_diagram_generates_file`: tmp_ml_output_dir に PNG 保存・size>0・`plt.close(fig)` cleanup。
- **test_baseline.py skip 解除 + 4テスト目新規追加**（Wave 0 skeleton は3テストのみ・plan は4テスト要求）:
  - `test_popularity_baseline_auc`: 完全一致 fixture（人気1-3=top3・人気4=着外・2レース×4頭）で AUC==1.0。
  - `test_popularity_baseline_random` **[新規追加]**: 200行ランダム fixture で AUC≈0.5（pytest.approx(abs=0.1)）。ベースラインが実際の popularity-target 相関を測り、自明な高 AUC アーティファクトでないことを検証。
  - `test_popularity_nan_dropped`: 2行 popularity NaN 注入で n_rows==6（8-2）・AUC==1.0維持・`roc_auc_score` の `ValueError` 発生なし（Pitfall #6 検証）。
  - `test_join_integrity`: sample_feature_df + sample_entry_df（1:1 join）で n_rows == 20 - NaN popularity 行数・AUC∈[0,1]。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Wave 0 skeleton shipped only 3 TestBaseline tests; plan requires 4**
- **Found during:** Task 2（07-01 SUMMARY は TestBaseline を3テスト scaffold、plan 07-06 の `<behavior>` と `<acceptance_criteria>` は4テスト要求・PATTERNS.md line 652 も `test_popularity_baseline_random` を明示）
- **Issue:** Wave 0 (07-01) は `TestBaseline` に3テスト（auc / nan_dropped / join_integrity）のみ scaffold した。Task 2 の `<action>` は「skip を外し実装する」と記載するが、4テスト目 `test_popularity_baseline_random` は存在しなかったため単なる skip 解除では不足。
- **Fix:** Task 2 で3テストの skip を外す実装を書くだけでなく、`test_popularity_baseline_random`（ランダム popularity で AUC≈0.5検証）を新規追加。07-05 P05 と同一の Wave-0-shipped-3-plan-requires-4 パターン。
- **Files modified:** tests/ml/test_baseline.py（3テスト skip 解除 + 1テスト新規 + クラス docstring 整備）
- **Commit:** d4e9253

**2. [Rule 2 - Missing critical functionality] Defensive empty-input handling in compute_ece + compute_popularity_baseline**
- **Found during:** Task 1 + Task 2（plan `<action>` は RESEARCH VERIFIED コードをベースにしたが、空入力や全-NaN fixture のハンドリングが明示要求されていない）
- **Issue:** RESEARCH VERIFIED の素朴な compute_ece は空配列で `y_true_arr.mean()` が NaN/RuntimeWarning を出す。compute_popularity_baseline で全行 NaN の場合 `roc_auc_score` が `ValueError` または空配列エラー。
- **Fix:** compute_ece は `n==0` で 0.0 + logger.warning を返す（防御的）。compute_popularity_baseline は `len(valid)==0` で baseline_auc=0.5 + n_rows=0 + 説明 note を返す（crash しない）。Phase 7 本番では発生しないが、将来の Phase 9 walk-forward の小窓やユニットテストの退化 fixture で安全側に倒す。
- **Files modified:** src/ml/evaluator.py, src/ml/baseline.py
- **Commit:** 80ecb5f, d4e9253

**3. [Rule 3 - Blocking issue / Cycle-5 MEDIUM resolution] D-09 reference in read_first conflicts with evaluate() signature**
- **Found during:** Task 1（plan Task-1 `<read_first>` が D-09 race-level Top-3 recall を「参考出力」として列挙するが、evaluate() のシグネチャ `(y_true, y_prob_raw, y_prob_calibrated)` は race グループ情報を持たない）
- **Issue:** Cycle-5 MEDIUM carry-over executor note が option (a) race_level_top3_recall 追加 or option (b) read_first から D-09 除外を要求。evaluate() に race_id を追加すると、配列のみの小規模 hermetic numpy fixture でのユニットテスト可能性（PATTERNS.md analog tests/schemas/test_audit.py）が損なわれる。
- **Fix:** option (b) 採用。D-09 race-level Top-3 recall は 07-07 run_train に繰越（run_train は race_id を保持）。evaluate() は配列専用のまま。決定根拠を evaluator.py ファイルヘッダ docstring + 本 SUMMARY decision に明記。
- **Files modified:** src/ml/evaluator.py（docstring に D-09 繰越理由明記）
- **Commit:** 80ecb5f

## Verification

| Check | Command | Result |
|-------|---------|--------|
| Task 1 imports | `python -c "from src.ml.evaluator import compute_ece, evaluate, reliability_diagram; print('ok')"` | ok |
| Task 1 ECE perfect | manual: compute_ece([0,1,0,1], [0,1,0,1]) | 0.0 ✓ |
| Task 1 ECE worst | manual: compute_ece([0,0,1,1], [1,1,0,0]) | 1.0 ∈ [0,1] ✓ |
| Task 1 ECE bin weighting | manual: asymmetric fixture | 0.05 (weighted, ≠ unweighted) ✓ |
| Task 1 evaluate keys | manual: evaluate(...) | 9 keys: auc/brier/logloss/ece × raw+cal + n_samples ✓ |
| Task 2 evaluator tests | `python -m pytest tests/ml/test_evaluator.py -x -q` | 5 passed in 13.08s |
| Task 2 baseline tests | `python -m pytest tests/ml/test_baseline.py -x -q` | 4 passed in <1s |
| Task 2 combined AC | `python -m pytest tests/ml/test_evaluator.py tests/ml/test_baseline.py -x -q` | 9 passed in 0.88s |
| Task 2 tests/ml/ coexistence | `python -m pytest tests/ml/ -q` | 26 passed, 6 skipped, 0 failed (07-02/03/04/05 と並存) |
| Full suite regression | `python -m pytest tests/ -q` | 539 passed, 7 skipped, 0 failed (452.59s) |
| grep sklearn metrics | `grep -c "roc_auc_score\|brier_score_loss\|log_loss" src/ml/evaluator.py` | 7 (>=1) |
| grep Agg backend | `grep -c "matplotlib.use.*Agg" src/ml/evaluator.py` | 1 (>=1) |
| grep 3 funcs | `grep -c "def compute_ece\|def evaluate\|def reliability_diagram" src/ml/evaluator.py` | 3 |
| grep dropna Pitfall #6 | `grep -c "dropna.*popularity\|dropna.*target_top3" src/ml/baseline.py` | 2 (>=1) |
| grep roc_auc_score baseline | `grep -c "roc_auc_score" src/ml/baseline.py` | 5 (>=1) |
| grep D-08 docstring | `grep -c "D-08\|参考情報\|純粋予測" src/ml/baseline.py` | 11 (>=1) |
| min_lines evaluator | `wc -l src/ml/evaluator.py` | 232 (>=80) |
| min_lines baseline | `wc -l src/ml/baseline.py` | 121 (>=40) |
| TDD gate (Wave 0 RED → GREEN) | git log | Wave 0 skip skeletons were the RED gate; feat(07-06) 80ecb5f + d4e9253 are the GREEN gate |

## Known Stubs

None. 3関数（compute_ece / evaluate / reliability_diagram）と 1関数（compute_popularity_baseline）全てが本番 holdout/OOF 予測と entry.parquet に対して完全に動作する。D-06（主指標 AUC・raw+calibrated）・D-11（ECE<0.02 + reliability diagram PNG）・D-08（人気ベースライン参考情報・docstring 理論的骨格）契約を満たす。Pitfall #5（holdout 再 fit リーク）は evaluator 側では報告のみ・実際の防止は calibrator.apply_calibrator 構造防止。Pitfall #6（popularity NaN）は dropna で検証済み。Phase 8 Harville EV の精度評価と Phase 9 ROI-vs-AUC フレーミングの前提が完成。

## Threat Flags

None. T-07-06-01..03 は全て disposition=mitigate/accept で実装内に反映:
- T-07-06-01 (Pitfall #6 popularity NaN 伝播): compute_popularity_baseline は dropna(subset=['popularity','target_top3']) で NaN 行を除外（取消/除外馬 1,944件相当）。test_popularity_nan_dropped で2行 NaN 注入 → n_rows==6 + AUC==1.0 + ValueError なしを検証。
- T-07-06-02 (Pitfall #5 holdout ECE 異常値・リーク徴候): evaluate は ece_calibrated >= 0.02 で logger.warning（D-11 違反徴候）。evaluator は読み取り専用・fit しない・実際のリーク防止は calibrator.apply_calibrator（labels 受け取らず構造防止）。
- T-07-06-03 (過学習指標・指標改竄 accept): 指標は読み取り専用・外部入力なし。reliability_diagram は matplotlib Agg backend でヘッドレス描画（CLI 環境で Tkinter エラー回避）。

## Self-Check: PASSED

- Created/modified files exist:
  - FOUND: src/ml/evaluator.py
  - FOUND: src/ml/baseline.py
  - FOUND: tests/ml/test_evaluator.py
  - FOUND: tests/ml/test_baseline.py
- Commits exist:
  - FOUND: 80ecb5f (Task 1 evaluator.py implementation)
  - FOUND: d4e9253 (Task 2 baseline.py + unskip both test files + 4th baseline test)
