---
phase: 07-model-a-top-3-probability
plan: 08
subsystem: ml-phase-gate
tags: [wave-4, phase-gate, real-data-execution, d-15-artifacts, d-07-auc, d-11-ece, codex-high, cycle-2-high]
requires:
  - "07-07 (run_train orchestrator + config + hermetic E2E — full pipeline integration tested)"
  - "07-02..07-06 (Wave 1+2 modules: data_loader / GroupTimeSeriesSplit / trainer / calibrator / evaluator / baseline)"
provides:
  - "Phase 7 成功判定（実データ完走 + D-07 AUC目安0.75 + D-11 ECE<0.02）の human-verify 完了（auto-advance 自己承認: 両指標 PASS・視覚品質確認済み）"
  - "D-15 全7物理成果物（6論理グループ）が本番 features_train.parquet（534,953行×78列）から生成され、Phase 8/9 が即時消費可能"
  - "metrics.json 実測値（テキスト固定）: holdout AUC=0.7669 / ECE=0.0062 / popularity baseline AUC=0.8100 / OOF rows=268,648 / holdout rows=66,343"
affects:
  - "Phase 8 (Harville EV): model_a.lgb.txt + isotonic_calibrator.joblib + holdout_predictions.parquet（p_top3_calibrated 列）を消費して三連複含意オッズ展開"
  - "Phase 9 (walk-forward backtest): run_train pattern + GroupTimeSeriesSplit + calibrator + holdout 予測を基準として再利用"
  - "ROADMAP.md Phase 7 progress table: 全8 plans complete（本 plan で close）"
tech_stack:
  added: []
  patterns:
    - "Phase gate execution-only pattern: 実行 + 検証のみ・ソース変更なし（全成果物は gitignored ディレクトリに生成・コミット対象外）"
    - "Auto-advance human-verify self-approval: auto_advance=true で checkpoint:human-verify（非 package-legitimacy）は自己承認可・視覚品質を Claude が代行確認"
key_files:
  created:
    - (gitignored) models/phase7/model_a.lgb.txt (913,270 bytes)
    - (gitignored) models/phase7/isotonic_calibrator.joblib (4,791 bytes)
    - (gitignored) data/model/oof/oof_predictions.parquet (4,099,253 bytes — 268,648 rows)
    - (gitignored) data/model/oof/holdout_predictions.parquet (1,168,211 bytes — 66,343 rows)
    - (gitignored) reports/phase7/metrics.json (424 bytes)
    - (gitignored) reports/phase7/evaluation_report.md (1,448 bytes)
    - (gitignored) reports/phase7/reliability_diagram.png (41,792 bytes)
  modified: []
decisions:
  - "[Phase 07 P08]: Phase 7 phase gate PASS — 実データ holdout AUC=0.7669 (D-07 目安0.75 以上 PASS)・ECE=0.0062 (D-11 <0.02 PASS). Isotonic キャリブレーションがホールドアウトで完働（pred_mean 0.2145 ≈ positive_rate 0.2146, 差0.0001）— Pitfall #5 リークなし。pure-properties model が人気ベースライン 0.8100 に AUC 0.043 及ばないのは D-08 通説通り（参考情報・必須条件ではない）"
  - "[Phase 07 P08]: Codex HIGH #2 fix 確認（実データ）— OOF rows=268,648 < train_rows=322,510. warm-up chunk 0 除外・validation chunks のみ。n_splits+1 date-block chunk scheme（Cycle-3 HIGH fix）が本番 corpus で assertion 無しに完走"
  - "[Phase 07 P08]: Codex HIGH #7 fix（holdout retune 禁止）— 本 phase gate で metrics を inspect した後にハイパラ retune は実施しなかった。holdout は一度きりの「封筒」・Phase 9 walk-forward で追加検証"
  - "[Phase 07 P08]: Cycle-2 HIGH #3（oof_rows producer/consumer contract）確認 — metrics.json に oof_rows=268648（型=int・計算=len(oof_df)）が記録され、07-08 verify が `'oof_rows' in m` と `m['oof_rows'] < 322510` を PASS。07-07 producer と 07-08 consumer の contract 完全一致"
  - "[Phase 07 P08]: Cycle-2 HIGH #4（ROADMAP success-criteria 整合）確認 — ROADMAP.md Phase 7 success criteria #1「trained on 2018-2024 data (D-05/D-01)」と #3「holdout baseline comparison is reference-only (D-07/D-08)」は既に LOCKED 決定と一致（前 cycle で修正済み）。本 plan 完了で Phase 7 完了宣言が記載基準を満たす"
  - "[Phase 07 P08]: AUC discrimination は auc_raw=0.7669 と auc_calibrated=0.7669 が実質同一（差0.0001・Isotonic ties の AUC-preserving 挙動・Codex MEDIUM suggestion の両確認を実施）"
metrics:
  duration: 137s
  completed: 2026-06-16
  tasks: 2
  files: 0
---

# Phase 7 Plan 08: Real-data Phase Gate Summary

Phase 7 の最終 phase gate: 実データ `features_train.parquet`（534,953行×78列・2015-01-04〜2026-05-31）で `python -m src.ml.run_train` を完走させ、D-15 の全7物理成果物を生成、ホールドアウト AUC（D-07 目安0.75以上）と ECE（D-11 <0.02）の成功判定を**両方 PASS** で確認。Phase 8（Harville EV）と Phase 9（walk-forward backtest）に引き渡す成果物が即時利用可能な状態で揃った。

## What Was Built

### Task 1 — 実データ run_train 完走 + D-15 6成果物生成（execution-only・ソース変更なし）

`python -m src.ml.run_train`（setuptools・`poetry run` 禁止）を本番データで実行。**expected_counts=None（デフォルト）で PRODUCTION_COUNTS assert（322510/23288/66343/4740）が有効なまま完走**。実行時間 約18秒（LightGBM native categorical + col_wise + CPU）。

**run_train 10ステップの実行ログ（要約）:**
1. config load（seed=42, train_window=[2018-01-01, 2024-12-31], holdout_window=[2025-01-01, 2026-05-31], n_splits=5）
2. load_features: train_rows=322,510 / holdout_rows=66,343（PRODUCTION_COUNTS assert PASS）
3. feature_columns 解決: raw=72 / dropped=7（race_id, race_date, horse_entity_key, horse_name, result_status, is_dnf, horse_number）→ effective=65 features（Codex HIGH #5）
4. collect_oof_predictions: **5 folds × date-block chunks・全 fold で max_train_date < min_val_date の strict assertion が PASS（Cycle-3 HIGH fix 実証）・oof_rows=268,648 < 322,510（Codex HIGH #2 warm-up 除外）**
5. fit_calibrator: IsotonicRegression on 268,648 OOF rows（raw range [0.0074, 0.8322]）
6. train_final_model: 二段階全量再学習（Codex HIGH #6）— Stage 1 inner_val で best_iteration_val=164 / Stage 2 fresh classifier on 322,510 rows at fixed iteration=164
7. holdout 予測: raw_mean=0.2112 → cal_mean=0.2145（apply_calibrator・Pitfall #5 構造防止）
8. evaluate: **auc_calibrated=0.7669, ece_calibrated=0.0062, n_samples=66,343**
9. compute_popularity_baseline: baseline_auc=0.8100, n_rows=66,343（D-08 参考情報）
9b. metrics["oof_rows"] = 268648（Cycle-2 HIGH #3 producer 側書込）
10. 7成果物保存（model .txt / calibrator .joblib / OOF parquet / holdout parquet / metrics.json / evaluation_report.md / reliability_diagram.png）

**全7物理成果物が size > 0 で生成（検証スクリプト PASS）:**

| 成果物 | path | size (bytes) |
|---|---|---|
| LightGBM model | models/phase7/model_a.lgb.txt | 913,270 |
| Isotonic calibrator | models/phase7/isotonic_calibrator.joblib | 4,791 |
| OOF predictions | data/model/oof/oof_predictions.parquet | 4,099,253 |
| Holdout predictions | data/model/oof/holdout_predictions.parquet | 1,168,211 |
| Metrics JSON | reports/phase7/metrics.json | 424 |
| Evaluation report | reports/phase7/evaluation_report.md | 1,448 |
| Reliability diagram | reports/phase7/reliability_diagram.png | 41,792 |

**Schema と行数の検証（plan verify スクリプト PASS）:**
- OOF parquet 列 = `{race_id, horse_race_id, p_top3_raw, target_top3, fold, p_top3_calibrated}` — 計画の仕様（`{race_id, horse_race_id, p_top3_raw, p_top3_calibrated, target_top3, fold}`）と完全一致（列順序は異なるが集合として同一）
- OOF rows = 268,648 < 322,510（Codex HIGH #2 fix PASS）
- holdout rows = 66,343（== 仕様）
- OOF fold 値 = {0, 1, 2, 3, 4}（5 fold 期待通り）
- holdout fold = "holdout"（全行）
- metrics.json keys に `oof_rows` 含む（型=int・Cycle-2 HIGH #3 contract PASS）

### Task 2 — Phase 7 成功判定 human-verify（auto-advance 自己承認・両指標 PASS）

`auto_advance: true`（config.json workflow.auto_advance）下で `checkpoint:human-verify`（非 package-legitimacy）のため auto-approve ルールを適用。Claude が metrics.json / reliability_diagram.png / evaluation_report.md の確認を代行し、視覚品質も bin-level 信頼度計算で客観検証。

**D-07 AUC 目安 0.75（guideline・discretion 領域）:**

| 指標 | 値 | 判定 |
|---|---|---|
| auc_raw | 0.7669 | PASS（≥ 0.75）|
| auc_calibrated | 0.7669 | PASS（≥ 0.75・Isotonic ties で auc_raw と実質同一）|
| popularity baseline_auc | 0.8100 | （参考情報・D-08 で必須条件ではない・pure-properties model が人気に及ばないのは通説通り）|

**D-11 ECE < 0.02（厳格）:**

| 指標 | 値 | 判定 |
|---|---|---|
| ece_raw | 0.0079 | （参考・raw LightGBM 出力）|
| ece_calibrated | 0.0062 | PASS（≪ 0.02）|

**キャリブレーション品質の客観検証（bin-level・holdout）:**

| bin 範囲 | n | pred_mean | obs_rate | gap |
|---|---|---|---|---|
| 0.00-0.10 | 19,696 | 0.0553 | 0.0521 | 0.0032 |
| 0.10-0.20 | 16,228 | 0.1458 | 0.1447 | 0.0011 |
| 0.20-0.30 | 12,440 | 0.2435 | 0.2371 | 0.0065 |
| 0.30-0.40 | 8,161 | 0.3391 | 0.3479 | 0.0088 |
| 0.40-0.50 | 5,001 | 0.4380 | 0.4301 | 0.0079 |
| 0.50-0.60 | 3,459 | 0.5385 | 0.5629 | 0.0244 |
| 0.60-0.70 | 984 | 0.6462 | 0.6951 | 0.0489 |
| 0.70-0.80 | 266 | 0.7392 | 0.7481 | 0.0089 |
| 0.80-0.90 | 95 | 0.8359 | 0.8632 | 0.0272 |
| 0.90-1.00 | 13 | 0.9911 | 0.7692 | 0.2219 |

- 加重 ECE（手動計算） = 0.006212（metrics.json の 0.0062 と完全一致）
- [0, 0.8] の8ビン（データの 99.8%）は gap 0.001〜0.05 で全て良好
- 最上位 bin（0.9-1.0）は gap 0.22 だが n=13 のみ（0.02%）で加重 ECE への寄与無視できる
- **pred_mean 0.2145 ≈ positive_rate 0.2146（差 0.0001）** — Pitfall #5（holdout recalibration leak）の形跡なし。もし holdout で calibrator を再 fit していれば ECE は不自然に 0 に近くなるはず

**reliability_diagram.png の視覚品質**: 各 bin の棒（観測 top-3 率）が点線（完全校正線）に [0, 0.8] 全域で近接。極端に外れた bin なし。ECE_calibrated 0.0062 と整合。

**evaluation_report.md の注記確認**: D-08 純粋予測×EV 構図注記あり・**holdout retune 禁止注記（Cycle-2 LOW fix・Codex HIGH #7）あり**・D-14 再現性注記あり。本 phase gate で metrics を inspect した後にハイパラ retune は実施していない（holdout は D-02 の一度きりの「封筒」）。

## Deviations from Plan

None — plan executed exactly as written. Codex HIGH #2 / HIGH #7 と Cycle-2 HIGH #3 / HIGH #4 の全修正指示が実データ実行で検証された。`autonomous: false` checkpoint は auto_advance ルール下で自己承認（package-legitimacy checkpoint ではないため）。視覚品質は Claude が代行確認し bin-level 客観検証で補強。

## Verification

| Check | Command | Result |
|-------|---------|--------|
| run_train 完走 | `python -m src.ml.run_train 2>&1 \| tail -5` | run_train: complete（18秒・全ステップ logger.info 出力）|
| PRODUCTION_COUNTS assert | loguru "train_rows=322510 holdout_rows=66343" | PASS（322510/66343 assert 有効なまま完走）|
| D-15 7成果物 存在 + size>0 | plan verify script | 7/7 OK（913KB / 4.8KB / 4.1MB / 1.2MB / 424B / 1.4KB / 41.8KB）|
| OOF 行数 < 322,510（Codex HIGH #2）| `assert len(oof) < 322510` | PASS（268,648 < 322,510）|
| holdout 行数 == 66,343 | `assert len(hold) == 66343` | PASS |
| OOF/holdout schema | `oof.columns == {race_id, horse_race_id, p_top3_raw, [p_top3_calibrated], target_top3, fold}` | PASS（集合として完全一致）|
| OOF fold 値 | `oof['fold'].unique()` | {0,1,2,3,4}（5 fold 期待通り）|
| holdout fold 値 | `hold['fold'].unique()` | {"holdout"}（全行）|
| oof_rows contract（Cycle-2 HIGH #3）| `'oof_rows' in m and m['oof_rows'] < 322510` | PASS（268648 int）|
| **D-07 AUC ≥ 0.75** | `metrics['auc_calibrated']` | **PASS 0.7669**（auc_raw も 0.7669）|
| **D-11 ECE < 0.02** | `metrics['ece_calibrated']` | **PASS 0.0062**（≪ 0.02）|
| キャリブレーション品質 | holdout pred_mean vs positive_rate | 0.2145 vs 0.2146（差 0.0001・Pitfall #5 リークなし）|
| bin-level 加重 ECE | 手動計算 | 0.006212（metrics.json と完全一致）|
| reliability_diagram 視覚品質 | Claude 画像確認 + bin-level 表 | bars が diagonal に近接・[0,0.8] 全域で gap ≤ 0.05 |
| evaluation_report.md 注記 | grep "retune\|Pitfall #5\|D-08" | holdout retune 禁止 + Pitfall #5 + D-08 注記 全て存在 |
| ROADMAP criteria 整合（Cycle-2 HIGH #4）| `grep "2015-2023\|beat baseline on OOF" .planning/ROADMAP.md` | 0 件（stale 文言は既に解消済み・LOCKED 決定と一致）|

## Known Stubs

None. Phase 7 全成果物が本番データで生成済み・Phase 8/9 が即時消費可能。p_top3_calibrated 列が OOF/holdout 両 parquet に含まれ、Phase 8 Harville EV と Phase 9 walk-forward の基準として利用可能。

## Threat Flags

None. T-07-08-01..08 は全て disposition=mitigate で実行結果に反映:
- T-07-08-01（リークチェーン最終検証）: OOF 268,648 < 322,510 / holdout 66,343 の両 assert が PASS。Cycle-3 date-block chunk scheme が実データ（30.75 races/date mean）で strict per-fold temporal-order assertion 無しに完走（genuine invariant by construction）。
- T-07-08-02（D-07/D-11 成功判定）: auc_raw と auc_calibrated の両方を確認（Codex MEDIUM suggestion）。ECE は極端に低すぎず（0.0062・Pitfall #5 リーク疑いの「不自然に 0 に近い」パターンではない）。
- T-07-08-03（成果物改竄）: 全成果物は .gitignore で保護・ローカル保存・commit 対象外。
- T-07-08-04（Phase 9 引き渡し）: model_a.lgb.txt + calibrator.joblib + holdout_predictions.parquet が即時利用可能。
- T-07-08-05（Codex HIGH #2 OOF all-rows）: OOF rows < 322,510 を assert PASS。
- T-07-08-06（Codex HIGH #7 holdout retune）: 本 phase gate で retune 実施せず・evaluation_report.md に禁止注記存在・resume-signal にも制約明記。
- T-07-08-07（Cycle-2 HIGH #3 oof_rows contract）: metrics.json の oof_rows=268648（型=int・計算=len(oof_df)）を 07-08 verify が PASS。
- T-07-08-08（Cycle-2 HIGH #4 ROADMAP divergence）: ROADMAP.md Phase 7 success criteria は既に LOCKED 決定 D-05/D-07/D-08 と一致（stale 文言なし）。

## Self-Check: PASSED

- Created artifacts exist (all gitignored — verified on disk, not in git):
  - FOUND: models/phase7/model_a.lgb.txt (913,270 bytes)
  - FOUND: models/phase7/isotonic_calibrator.joblib (4,791 bytes)
  - FOUND: data/model/oof/oof_predictions.parquet (4,099,253 bytes)
  - FOUND: data/model/oof/holdout_predictions.parquet (1,168,211 bytes)
  - FOUND: reports/phase7/metrics.json (424 bytes)
  - FOUND: reports/phase7/evaluation_report.md (1,448 bytes)
  - FOUND: reports/phase7/reliability_diagram.png (41,792 bytes)
- No source-file commits expected (execution-only plan, artifacts gitignored). The only working-tree change is the pre-existing `.planning/debug/demotion-finish-parse.md` (untracked, not from this task — left untouched).
- ROADMAP Phase 7 criteria verified to match LOCKED decisions (Cycle-2 HIGH #4) — no edit required.
- D-07 (AUC ≥ 0.75) PASS: 0.7669.
- D-11 (ECE < 0.02) PASS: 0.0062.
