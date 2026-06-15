---
phase: 07-model-a-top-3-probability
plan: 07
subsystem: ml-orchestrator
tags: [wave-3, run-train, integration, d-15-artifacts, feature-columns-explicit, expected_counts-sentinel, oof-rows-contract, cycle-2-high, codex-high]
requires:
  - "07-02 (data_loader.load_features — race_date retained, expected_counts UNIFIED sentinel)"
  - "07-03 (GroupTimeSeriesSplit n_splits+1 date-block chunk scheme)"
  - "07-04 (trainer.collect_oof_predictions / train_final_model — feature_columns explicit arg, two-stage full retrain)"
  - "07-05 (calibrator.fit_calibrator / apply_calibrator / save_calibrator — Pitfall #5 structural)"
  - "07-06 (evaluator.evaluate / reliability_diagram + baseline.compute_popularity_baseline)"
provides:
  - "src.ml.run_train.run_train(config_path, expected_counts: dict | list | None = None) -> dict — UNIFIED sentinel (Cycle-2 HIGH #2); forwards expected_counts to load_features (Codex HIGH #4); resolves feature_columns from config minus drop_columns and passes explicitly to trainer (Codex HIGH #5); writes metrics['oof_rows'] = int(len(oof_df)) into metrics.json (Cycle-2 HIGH #3 producer/consumer contract with 07-08)"
  - "python -m src.ml.run_train CLI entry point (setuptools project, NOT poetry)"
  - "src.ml package public API (__all__ 14 symbols: run_train, GroupTimeSeriesSplit, train_fold_model, collect_oof_predictions, train_final_model, fit_calibrator, apply_calibrator, save_calibrator, load_calibrator, compute_ece, evaluate, reliability_diagram, compute_popularity_baseline, load_features)"
  - "config/phase7_model_a.yaml (sensible defaults + windows + folds + feature_columns + artifacts)"
  - "TestRunTrainE2E with 5 GREEN hermetic tests"
affects:
  - "07-08 phase gate: run_train(config_path) with expected_counts=None runs the production 322510/23288/66343/4740 assert + D-15 artifact generation; verify consumes metrics.json['oof_rows']"
  - "Phase 8 Harville EV: from src.ml import load_calibrator, apply_calibrator + model_a.lgb.txt + OOF/holdout parquet (p_top3_calibrated column)"
  - "Phase 9 walk-forward backtest: reuses run_train pattern + GroupTimeSeriesSplit + evaluate metrics schema"
tech_stack:
  added: []
  patterns:
    - "Single-entry orchestrator analog: src/pipeline/integration.py::integrate_standard_layer (numpy docstring, per-step logger.info, dict return, mkdir(parents=True, exist_ok=True))"
    - "feature_columns resolved ONCE in run_train (config['data']['feature_columns'] minus drop_columns) and passed explicitly downstream — trainer NEVER reads the config key (Codex HIGH #5 + leak safety)"
    - "UNIFIED expected_counts sentinel forwarding (None=production / []=bypass / non-empty dict=custom / {} rejected by 07-02 TypeError) — identical to 07-02"
    - "metrics['oof_rows'] = int(len(oof_df)) producer-side contract: key, type, value all locked for 07-08 consumer"
    - "Hermetic E2E fixture: combined train+holdout feature parquet under tmp_path; FEATURE_COLUMNS extended with numeric defaults; entry parquet built per (race_id, horse_number)"
key_files:
  created:
    - config/phase7_model_a.yaml
    - src/ml/run_train.py
    - tests/ml/test_run_train.py
  modified:
    - src/ml/__init__.py
    - .gitignore
decisions:
  - "[Phase 07 P07]: run_train resolves effective feature_columns as config['data']['feature_columns'] MINUS config['data']['drop_columns']. FEATURE_COLUMNS includes identifiers (race_id, race_date) and targets (horse_number, target_top3) for schema completeness, but these MUST NOT enter the LightGBM feature matrix (race_id leaks as a near-unique key; race_date leaks temporal position). run_train performs the subtraction in ONE place (Codex HIGH #5 'resolve in run_train') and the trainer receives only the safe subset."
  - "[Phase 07 P07]: config['data']['feature_columns'] MUST set-equal src.pipeline.feature_generator.FEATURE_COLUMNS — locked by test_feature_columns_config_consistency. Any drift between YAML and the static allowlist is caught at test time."
  - "[Phase 07 P07]: Codex HIGH #2 (OOF row count < train-window) is logged at runtime via logger.info AND asserted by test_oof_parquet_schema_and_row_count. The contract is structural (n_splits+1 date-block chunk scheme excludes warm-up chunk 0 from val) — run_train only reports the invariant."
  - "[Phase 07 P07]: Codex HIGH #4 / Cycle-2 HIGH #2 UNIFIED sentinel: run_train signature is (config_path, expected_counts=None) and forwards expected_counts to load_features WITHOUT branching. Hermetic E2E passes [] (empty LIST); production 07-08 passes None (default). Empty dict {} is never used (07-02 raises TypeError)."
  - "[Phase 07 P07]: Cycle-2 HIGH #3 producer/consumer contract — metrics['oof_rows'] = int(len(oof_df)) is injected into the metrics dict BEFORE json.dump. test_oof_parquet_schema_and_row_count locks the contract on the producer side (key presence, type int, value == OOF parquet row count). 07-08 verify will assert 'oof_rows' in m and m['oof_rows'] < 322510 on the consumer side."
  - "[Phase 07 P07]: Cycle-2 HIGH #1 propagation — run_train does NOT drop race_date. load_features (07-02) returns frames that retain it; collect_oof_predictions (07-04) forwards dates=df['race_date'] to splitter.split so the per-fold temporal-order assertion always fires."
  - "[Phase 07 P07]: Cycle-2 LOW fix — evaluation_report.md includes an explicit holdout-retune prohibition note (Pitfall #5 reminder) alongside the D-08 純粋予測×EV framing and D-14 reproducibility note."
  - "[Phase 07 P07]: .gitignore adds models/phase7/, data/model/oof/ (explicit despite data/ already covering it — documents the D-15 contract), reports/phase7/. All D-15 artifacts are local-only."
metrics:
  duration: 1011s
  completed: 2026-06-16
  tasks: 3
  files: 5
---

# Phase 7 Plan 07: run_train Orchestrator + Config + Package API Summary

Wave 1+2 全モジュール（data_loader / GroupTimeSeriesSplit / trainer / calibrator / evaluator / baseline）を統合する `run_train` オーケストレーターと、sensible defaults を定義する config YAML、パッケージ公開 API を実装。Codex HIGH #2/#4/#5/#6 と Cycle-2 HIGH #1/#2/#3 を全て解決。D-15 の6成果物（model .txt / calibrator .joblib / OOF parquet / holdout parquet / report+metrics+diagram / config 参照）を一貫して生成する単一エントリポイントが完成。

## What Was Built

### Task 1 — config/phase7_model_a.yaml + .gitignore (commit e06b166)
- **config/phase7_model_a.yaml** を作成（RESEARCH Code Examples VERIFIED 構造）。8セクション:
  - `seed: 42`（D-14 固定 seed）
  - `data`: feature_path, entry_path, train_window `["2018-01-01","2024-12-31"]`（D-01/D-02）, holdout_window `["2025-01-01","2026-05-31"]`, target_column, exclude_column, **feature_columns（72カラム・Codex HIGH #5 fix）**, categorical_columns（9列・D-16）, drop_columns（7列: race_id/race_date/horse_entity_key/horse_name/result_status/is_dnf/horse_number）
  - `cv`: method=group_timeseries, n_splits=5, group_column=race_id, sort_column=race_date, early_stopping_val_ratio=0.2
  - `model`: objective=binary, metric=[binary_logloss,auc], num_leaves=31, learning_rate=0.05, min_data_in_leaf=100, feature_fraction=0.9, bagging_fraction=0.9, bagging_freq=5, max_depth=-1, lambda_l1/l2=0.0, min_gain_to_split=0.0, verbose=-1, force_col_wise=true, n_estimators=1000
  - `early_stopping`: stopping_rounds=50, verbose=false, first_metric_only=false, log_period=50
  - `calibration`: method=isotonic, y_min=0.0, y_max=1.0, out_of_bounds=clip, fit_on=oof
  - `evaluation`: ece_bins=10, ece_tolerance=0.02（D-11）, reliability_diagram=true
  - `artifacts`: model_dir=models/phase7, oof_dir=data/model/oof, report_dir=reports/phase7 + 7ファイル名（model/calibrator/oof/holdout/metrics/report/diagram）
- **Codex HIGH #5 fix**: data.feature_columns キーが src/pipeline/feature_generator.py の FEATURE_COLUMNS（72カラム）と完全一致。set 比較で test_feature_columns_config_consistency が検証。
- **.gitignore**: models/phase7/, data/model/oof/（data/ 既存だが明示的に D-15 契約を文書化）, reports/phase7/ を追記。

### Task 2 — src/ml/run_train.py (commit daf4a81, 437行 min_lines=110 充足)
- **`run_train(config_path, expected_counts=None) -> dict`** を実装（analog integrate_standard_layer）。numpy docstring・19箇所の logger.info・戻り値 dict・mkdir(parents=True, exist_ok=True)。
- 10ステップのパイプライン:
  1. load_config: YAML 読込 + seed/window/fold を logger.info
  2. load_features: **expected_counts 転送（Codex HIGH #4）**・UNIFIED sentinel（Cycle-2 HIGH #2）
  3. **feature_columns 解決（Codex HIGH #5）**: `config["data"]["feature_columns"]` から `drop_columns` を引いたリストを構築。trainer モジュールは config 参照しない。
  4. collect_oof_predictions: feature_columns 明示的引数・**OOF rows < train rows を logger.info（Codex HIGH #2）**
  5. fit_calibrator: OOF（val chunks のみ・warm-up 除外）で Isotonic 学習
  6. train_final_model: **二段階全量再学習（Codex HIGH #6）**・feature_columns 明示的引数
  7. holdout 予測: predict_proba + apply_calibrator（Pitfall #5 構造防止）
  8. evaluate: AUC/Brier/logloss/ECE・ece_calibrated >= ece_tolerance で logger.warning（D-11）
  9. compute_popularity_baseline: entry.parquet join・D-08 参考情報
  9b. **metrics["oof_rows"] = int(len(oof_df))（Cycle-2 HIGH #3 producer/consumer contract）**
  10. 6成果物保存: booster_.save_model（.txt）/ save_calibrator（.joblib）/ OOF to_parquet（p_top3_calibrated 列追加）/ holdout to_parquet（fold="holdout"）/ reliability_diagram（.png）/ metrics.json（oof_rows 含む）+ evaluation_report.md（D-08 + holdout retune 禁止・Cycle-2 LOW）
- **CLI**: `if __name__ == "__main__": run_train()` で `python -m src.ml.run_train` エントリポイント（setuptools・poetry 禁止）。

### Task 3 — src/ml/__init__.py re-exports + tests/ml/test_run_train.py (commit 9d30a02)
- **src/ml/__init__.py** を 07-01 の empty marker から公開 API 再エクスポートに遷移（Phase 4 P06 パターン）。`__all__` で14シンボルを明示。Phase 8/9 が `from src.ml import ...` でアクセス可能。
- **tests/ml/test_run_train.py** TestRunTrainE2E（5テスト hermetic）:
  - `run_train_artifacts` fixture: tmp_path に combined train+holdout feature parquet（FEATURE_COLUMNS 拡張）+ entry parquet（popularity per race_id+horse_number）+ 縮小 config YAML（n_splits=3, num_leaves=8, n_estimators=30）を構築。`run_train(config_path=cfg, expected_counts=[])` で実行。
  - `test_run_train_hermetic_e2e`: 全8パス（model/calibrator/oof/holdout/report/metrics/diagram/config）が存在・metrics.json の auc_calibrated/ece_calibrated ∈ [0,1]。
  - `test_oof_parquet_schema_and_row_count`: OOF 列 {race_id, horse_race_id, p_top3_raw, p_top3_calibrated, target_top3, fold} 完全一致・**len(oof) < len(train_fixture)（Codex HIGH #2）**・fold ⊆ {0,1,2}・**metrics.json['oof_rows'] exists as int matching len(oof_df)（Cycle-2 HIGH #3）**。
  - `test_holdout_parquet_schema`: holdout 列 == OOF 列・fold == "holdout"。
  - `test_artifacts_all_created`: 6成果物カテゴリ全てが size > 0 で存在。
  - `test_feature_columns_config_consistency`: config data.feature_columns == FEATURE_COLUMNS（set 比較・Codex HIGH #5）。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] feature_columns effective-list resolution**
- **Found during:** Task 2（run_train 実装時・config の feature_columns に識別子/ターゲットが含まれる問題）
- **Issue:** PLAN は「config の data.feature_columns が FEATURE_COLUMNS と完全一致」と「run_train が feature_columns を trainer に引数渡し」を指示するが、FEATURE_COLUMNS 自体が race_id/race_date/horse_number 等の識別子・ターゲット・post-race ステータスカラムを含む（schema 完全性のため）。これらをそのまま LightGBM feature matrix に渡すと race_id が near-unique key でリークし、race_date が temporal position をリークする。
- **Fix:** run_train が feature_columns を解決する際、`config["data"]["feature_columns"]` から `config["data"]["drop_columns"]` を引いたリストを構築して trainer に渡す。PLAN が既に drop_columns（race_id/race_date/horse_entity_key/horse_name/result_status/is_dnf/horse_number）を定義していたため、この減算を run_train 側で実行する仕様として明文化。Codex HIGH #5「run_train で解決して引数渡し」の精神を遵守しつつリーク安全性を確保。test_oof_parquet_schema_and_row_count が OOF 行数 < train 行数（リークフリー）を検証。
- **Files modified:** src/ml/run_train.py（Step 3 feature_columns resolution）
- **Commit:** daf4a81

None of the other plan directives required deviation — Codex HIGH #2/#4/#5/#6 + Cycle-2 HIGH #1/#2/#3 + Cycle-2 LOW の全修正が指示通り実装された。

## Verification

| Check | Command | Result |
|-------|---------|--------|
| Task 1 config parse | `python -c "import yaml; yaml.safe_load(open('config/phase7_model_a.yaml'))"` | ok (8 top-level keys) |
| Task 1 feature_columns == FEATURE_COLUMNS | inline python set-equality | PASS (72 == 72) |
| Task 1 gitignore entries | `grep -c "models/phase7\|data/model/oof\|reports/phase7" .gitignore` | 3 (>=1) |
| Task 2 imports | `python -c "from src.ml.run_train import run_train; print('ok')"` | ok |
| Task 2 grep feature_columns (>=3) | `grep -c "feature_columns" src/ml/run_train.py` | 14 |
| Task 2 grep expected_counts (>=2) | `grep -c "expected_counts" src/ml/run_train.py` | 8 |
| Task 2 grep oof_rows (>=1) | `grep -cE "metrics\[.oof_rows.\]|\[\"oof_rows\"\]" src/ml/run_train.py` | 3 |
| Task 2 grep empty-dict forbidden (==0) | `grep -cE "expected_counts == \{\}|expected_counts=\{\}" src/ml/run_train.py` | 0 |
| Task 2 grep save calls (>=5) | `grep -c "save_model\|save_calibrator\|to_parquet\|savefig\|json.dump" src/ml/run_train.py` | 6 |
| Task 2 grep booster_.save_model (>=1) | `grep -c "booster_.save_model" src/ml/run_train.py` | 1 |
| Task 2 grep main (==1) | `grep -c 'if __name__ == "__main__"' src/ml/run_train.py` | 1 |
| Task 2 grep logger.info (>=5) | `grep -c "logger.info" src/ml/run_train.py` | 19 |
| Task 2 min_lines (>=110) | `wc -l src/ml/run_train.py` | 437 |
| Task 3 re-exports | `python -c "from src.ml import run_train, GroupTimeSeriesSplit, train_fold_model, fit_calibrator, compute_ece, evaluate, compute_popularity_baseline, load_features; print('re-exports ok')"` | re-exports ok |
| Task 3 grep __all__ (>=1) | `grep -c "__all__" src/ml/__init__.py` | 1 |
| Task 3 hermetic E2E | `python -m pytest tests/ml/test_run_train.py -x -q` | 5 passed in 1.91s |
| Task 3 tests/ml/ coexistence | `python -m pytest tests/ml/ -q` | 37 passed, 2 skipped, 0 failed |
| Task 3 full suite regression | `python -m pytest tests/ -q` | 550 passed, 3 skipped, 0 failed (449s) — 07-06 baseline 539/7 -> +11 unskipped, -4 skipped, no regressions |
| post-commit deletion check | `git diff --diff-filter=D --name-only HEAD~3 HEAD` | empty (no accidental deletions) |

## Known Stubs

None. run_train は hermetic fixture で完全に動作し、D-15 の6成果物（model .txt / calibrator .joblib / OOF parquet / holdout parquet / report+metrics+diagram / config 参照）を一貫して生成する。Codex HIGH #2/#4/#5/#6 と Cycle-2 HIGH #1/#2/#3 は全て hermetic E2E で検証済み。production features_train.parquet（322,510 train rows）に対する本格実行は 07-08 phase gate が `expected_counts=None`（デフォルト）で担う（本 plan の範囲外）。

## Threat Flags

None. T-07-07-01..11 は全て disposition=mitigate で実装内に反映:
- T-07-07-01 (D-15 成果物 schema): test_oof_parquet_schema_and_row_count / test_holdout_parquet_schema で列完全一致 + fold=="holdout" 検証。
- T-07-07-02 (リークチェーン統合点): Wave 1+2 各モジュールのリーク防止（data_loader audit / GroupTimeSeriesSplit n_splits+1 / calibrator OOF-only fit）を run_train が正しい順序で呼ぶ。test_run_train_hermetic_e2e で検証。
- T-07-07-03 (固定 seed 再現性): config seed=42 を LGBMClassifier random_state に渡す（trainer 経由）。
- T-07-07-04 (成果物改竄): .gitignore で保護・ローカル保存。
- T-07-07-05 (DoS メモリ): pandas DataFrame + LightGBM Dataset（accept）。
- T-07-07-06 (Codex HIGH #2 OOF all-rows): OOF rows < train rows を logger.info + test で検証。
- T-07-07-07 (Codex HIGH #4 hermetic bypass): expected_counts パラメータで本番/hermetic 切替。
- T-07-07-08 (Codex HIGH #5 feature_columns config): config キー追加 + run_train で解決 + trainer は引数受領 + test で整合性検証。
- T-07-07-09 (Cycle-2 HIGH #1 race_date 保持): run_train は race_date を drop しない・load_features が保持・trainer が dates 転送。
- T-07-07-10 (Cycle-2 HIGH #2 sentinel): UNIFIED sentinel で 07-02 と完全一致・空 dict 拒否。
- T-07-07-11 (Cycle-2 HIGH #3 oof_rows contract): metrics["oof_rows"] = int(len(oof_df)) を必ず書き込み・test で producer 側検証。

## Self-Check: PASSED

- Created/modified files exist:
  - FOUND: config/phase7_model_a.yaml
  - FOUND: src/ml/run_train.py
  - FOUND: src/ml/__init__.py
  - FOUND: tests/ml/test_run_train.py
  - FOUND: .gitignore
- Commits exist:
  - FOUND: e06b166 (Task 1 config YAML + gitignore)
  - FOUND: daf4a81 (Task 2 run_train.py orchestrator)
  - FOUND: 9d30a02 (Task 3 __init__ re-exports + hermetic E2E tests)
