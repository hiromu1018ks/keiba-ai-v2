---
status: complete
phase: 07-model-a-top-3-probability
source: [07-01-SUMMARY.md, 07-02-SUMMARY.md, 07-03-SUMMARY.md, 07-04-SUMMARY.md, 07-05-SUMMARY.md, 07-06-SUMMARY.md, 07-07-SUMMARY.md, 07-08-SUMMARY.md]
started: 2026-06-15T23:50:08Z
updated: 2026-06-15T23:56:56Z
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

[testing complete]

## Tests

### 1. Cold Start Smoke Test — run_train 完走
expected: `python -m src.ml.run_train` を実行すると、エラーなく完走し、最終行に `run_train: complete` が表示される。実行ログに PRODUCTION_COUNTS assert（train_rows=322510 / holdout_rows=66343）が有効なまま通過し、5 fold すべてで strict 時系列 assertion が PASS する。
result: pass
evidence: EXIT_CODE=0 / 最終ログ `run_train: complete` / `load_features done: mode=production (PRODUCTION_COUNTS) train=322510rows/23288races holdout=66343rows/4740races` / 5 fold 全て max_train_date < min_val_date（fold0: 2019-02-23<02-24 … fold4: 2023-10-22<10-28）・AssertionError なし / 実行約22秒

### 2. D-15 成果物の生成（7ファイル）
expected: run_train 完走後、以下7ファイルがすべて size>0 で生成される: `models/phase7/model_a.lgb.txt` / `models/phase7/isotonic_calibrator.joblib` / `data/model/oof/oof_predictions.parquet` / `data/model/oof/holdout_predictions.parquet` / `reports/phase7/metrics.json` / `reports/phase7/evaluation_report.md` / `reports/phase7/reliability_diagram.png`。Phase 8（Harville EV）と Phase 9（walk-forward backtest）が即時消費できる状態。
result: pass
evidence: model=913,270B / calibrator=4,791B / oof=4,099,253B / holdout=1,168,211B / metrics=424B / report=1,448B / diagram=41,792B — 全7ファイル存在・size>0

### 3. ホールドアウト AUC（D-07 成功判定）
expected: `reports/phase7/metrics.json` の `auc_calibrated` が 0.75 以上（07-08 実測 0.7669）。これは3着内確率推定の識別力が目安を満たすことを示す。純粋馬特性モデルが市場人気ベースライン（0.8100）に及ばないのは D-08 通説通りで必須条件ではない。
result: pass
evidence: auc_calibrated=0.7669 (>=0.75) / auc_raw=0.7669 / popularity baseline_auc=0.8100（参考情報・必須条件ではない）

### 4. ホールドアウト ECE（D-11 成功判定）
expected: `reports/phase7/metrics.json` の `ece_calibrated` が 0.02 未満（07-08 実測 0.0062）。予測確率が信頼できる校正状態にある。極端に0に近すぎない（0.0062 は Pitfall #5 リークの「不自然に0に近い」パターンではない）。
result: pass
evidence: ece_calibrated=0.0062 (<0.02) / ece_raw=0.0079（極端に0に近すぎず Pitfall #5 リーク形跡なし）

### 5. reliability diagram の視覚品質
expected: `reports/phase7/reliability_diagram.png` を開くと、各 bin の棒（観測3着内率）が対角点線（完全校正線）に [0, 0.8] 全域で近接し、極端に外れた bin がない。ECE_calibrated 0.0062 と整合する視覚的校正状態。
result: pass
evidence: bin-level 再計算で [0,0.8] の8 bin（データの99.8%）max gap=0.0489 (<=0.05) / 加重 ECE=0.006212 が metrics.json ece_calibrated と完全一致（D-14 再現性確認）/ 最上位 bin(0.9-1.0) gap=0.2219 は n=13(0.02%)のみで加重ECEへの寄与無視できる規模（07-08 評価と整合）

### 6. キャリブレーション品質（Pitfall #5 リーク確認）
expected: holdout 予測の平均が正例率にほぼ一致（pred_mean 0.2145 ≈ positive_rate 0.2146・差0.0001）。もし holdout データで calibrator を再 fit していれば、ECE が不自然に0に近くなるはず。この一致は Pitfall #5（holdout recalibration leak）がないことの証拠。
result: pass
evidence: pred_mean=0.2145 / positive_rate=0.2146 / diff=0.0001（差<=0.01・Pitfall #5 リーク形跡なし）

### 7. OOF リークフリー契約（Codex HIGH #2）
expected: `data/model/oof/oof_predictions.parquet` の行数が学習窓行数（322,510）未満（07-08 実測 268,648）。`metrics.json` の `oof_rows` も 322510 未満の int。これは warm-up chunk 0 が除外され、Isotonic キャリブレーションが in-sample 予測でリークしない構造的契約。
result: pass
evidence: oof parquet rows=268,648 (<322,510) / metrics oof_rows=268648 (<322,510) / metrics==parquet rows 一致 / oof fold={0,1,2,3,4} / holdout fold={holdout} / oof cols={race_id, horse_race_id, p_top3_raw, target_top3, fold, p_top3_calibrated}

### 8. evaluation_report.md の内容
expected: `reports/phase7/evaluation_report.md` を開くと、(a) D-08 純粋予測×EV 構図の注記、(b) holdout retune 禁止注記（Cycle-2 LOW / Codex HIGH #7）、(c) D-14 再現性注記が含まれる。ホールドアウトは一度きりの「封筒」であることが明記されている。
result: pass
evidence: report 内に 'D-08' / 'retune' / 'D-14' / '純粋予測' の4キーワード全て含む・holdout retune 禁止注記に「holdout 予測は評価のみに使用し、calibrator / model の再学習に絶対に使用しないこと」明記

## Summary

total: 8
passed: 8
issues: 0
pending: 0
skipped: 0

## Gaps

[none]
