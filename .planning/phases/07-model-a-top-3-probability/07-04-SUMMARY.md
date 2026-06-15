---
phase: 07-model-a-top-3-probability
plan: 04
subsystem: ml-trainer
tags: [wave-2, lightgbm, fold-training, oof-collection, two-stage-retrain, early-stopping-callback, feature-columns-explicit, dates-forwarding, leakage-prevention]
requires:
  - "07-01 (tests/ml/ scaffold + conftest fixtures + pyproject deps)"
  - "07-02 (data_loader.load_features returns race_date-RETAINED frames; trainer forwards dates=df['race_date'])"
  - "07-03 (GroupTimeSeriesSplit n_splits+1 date-block chunk scheme + split_train_validation inner carve + dates explicit arg)"
provides:
  - "src.ml.trainer.train_fold_model(X_train, y_train, X_val, y_val, config) -> lgb.LGBMClassifier — sensible defaults (D-13) + lgb.early_stopping callback (Pitfall #1)"
  - "src.ml.trainer.collect_oof_predictions(df, splitter, config, feature_columns: list[str]) -> pd.DataFrame — OOF = validation chunks only (warm-up chunk 0 excluded, Codex HIGH #2); forwards dates=df['race_date'] to splitter (Cycle-2 HIGH #1)"
  - "src.ml.trainer.train_final_model(df, config, feature_columns: list[str]) -> lgb.LGBMClassifier — two-stage: Stage 1 decides best_iteration_val on val split, Stage 2 retrains a fresh classifier on ALL rows at fixed iteration count (Codex HIGH #6 / D-15)"
  - "TestTrainer with 6 GREEN tests"
affects:
  - "07-05 calibrator consumes OOF DataFrame schema (race_id, horse_race_id, p_top3_raw, target_top3, fold); OOF rows < train rows is the leak-free contract (Codex HIGH #2)"
  - "07-07 run_train resolves feature_columns from config and passes it explicitly to collect_oof_predictions + train_final_model (Codex HIGH #5)"
  - "Phase 8 Harville EV consumes final model p_top3 + calibrator"
tech_stack:
  added: []
  patterns:
    - "LightGBM 4.x callback API only: callbacks=[lgb.early_stopping(...), lgb.log_evaluation(...)] — NEVER early_stopping_rounds= kwarg (Pitfall #1 VERIFIED)"
    - "best_iteration_ is None detection — populated IFF early-stopping callback ran; used as Pitfall #1 runtime guard + Stage 1 fallback"
    - "Two-stage final retrain: Stage 1 best_iteration decision on inner val carve, Stage 2 fresh classifier at fixed n_estimators=best_iteration_val on ALL rows (no early stopping on Stage 2)"
    - "OOF row count < input row count is a load-bearing invariant (warm-up chunk 0 excluded) — documented as contract, NOT bug"
    - "AST-based source meta-guards in tests (docstring-safe): detect early_stopping_rounds= kwarg in fit() calls and config['data']['feature_columns'] subscript chain without false-positiving on docstring mentions"
    - "Noisy synthetic frame for test_early_stopping_fires — sample_feature_df's target_top3 is trivially separable (derived from horse_number) so val logloss monotonically decreases and never triggers stopping; pure-noise label makes the curve non-monotonic (Codex Cycle-5 carry-over determinism)"
key_files:
  created:
    - src/ml/trainer.py
  modified:
    - tests/ml/test_trainer.py
    - tests/ml/conftest.py
decisions:
  - "Pitfall #1 VERIFIED in implementation: fit() takes callbacks=[lgb.early_stopping(stopping_rounds=N, verbose, first_metric_only), lgb.log_evaluation(period=N)] ONLY. early_stopping_rounds= kwarg would raise TypeError on LightGBM 4.x. best_iteration_ None-warning logs the Pitfall #1 signature."
  - "Codex HIGH #2: collect_oof_predictions docstring + code treat len(oof_df) < len(input_df) as a CONTRACT (warm-up chunk 0 excluded from OOF). Forcing warm-up predictions would be in-sample and leak into Isotonic calibration (07-05)."
  - "Codex HIGH #5: feature_columns is an explicit list[str] argument on both collect_oof_predictions and train_final_model. Neither references config['data']['feature_columns'] internally — run_train (07-07) resolves the column list in one place. AST test guard prevents regressions."
  - "Codex HIGH #6: train_final_model is two-stage. Stage 1 = split_train_validation tail-20% val carve + train_fold_model + record best_iteration_val. Stage 2 = fresh LGBMClassifier with set_params(n_estimators=best_iteration_val), fit on ALL input rows, callbacks=log_evaluation only (no early stopping — iteration count is fixed). best_iteration_val exposed via _best_iteration_val custom attr because Stage 2's best_iteration_ is None by design."
  - "Cycle-2 HIGH #1: collect_oof_predictions calls splitter.split(X, y, groups=race_ids, dates=df['race_date']) explicitly. Trains on df[feature_columns] (race_date NOT a feature) but passes dates separately so the per-fold temporal-order assertion ALWAYS fires (X-column-presence independent). Requires load_features (07-02) to retain race_date — trainer never drops it."
  - "Codex HIGH #3: split_train_validation imported at module level (from src.ml.group_timeseries_split import split_train_validation) — 07-04 is Wave 2 / depends_on 07-03, lazy import was unnecessary obfuscation."
  - "[Rule 2 - missing critical functionality] conftest ml_config extended: added data.target_column, cv.group_column (canonical 07-07 key alongside existing cv.group_col), cv.early_stopping_val_ratio, full model block (max_depth/lambda_l1/lambda_l2/min_gain_to_split), shrunk num_leaves=8/min_data_in_leaf=2/stopping_rounds=5 so hermetic LightGBM fits finish <1s. Other ml tests (calibrator/evaluator/baseline) unaffected — they only consume evaluation.n_bins + top-level keys."
  - "[Rule 1 - bug] test_early_stopping_fires determinism: sample_feature_df's target_top3 is perfectly correlated with horse_number (finish_position cycles 1..field_size), so val logloss → ~0 monotonically and early stopping never fires. Replaced with a 300-row pure-noise synthetic frame (RandomState=42, single gaussian feature, coin-flip label) so val logloss is non-monotonic and stopping fires at iteration 1 < 200. Verified best_iteration_=1 < n_estimators=200."
  - "[Rule 1 - bug] Pitfall #1 + Codex HIGH #5 meta-guards use AST inspection (ast.walk) instead of raw substring search, because the source docstrings legitimately mention early_stopping_rounds and config['data']['feature_columns'] as part of the API documentation. AST distinguishes executable Call.keyword / Subscript nodes from docstring Constant strings."
metrics:
  duration: 895s
  completed: 2026-06-15
  tasks: 2
  files: 3
---

# Phase 7 Plan 04: Trainer Summary

LightGBM fold trainer + OOF collector + two-stage final retrain を実装。Pitfall #1（early_stopping callback API・LightGBM 4.x で fit() の early_stopping_rounds は削除済み）・Codex HIGH #2（OOF = validation chunks のみ・warm-up chunk 0 除外）・Codex HIGH #3（split_train_validation の module-level import）・Codex HIGH #5（feature_columns 明示的引数・config 参照廃止）・Codex HIGH #6（二段階全量再学習）・Cycle-2 HIGH #1（dates=df["race_date"] 転送で splitter の temporal-order assertion を常に発火）の全修正を実装・検証。

## What Was Built

### Task 1 — src/ml/trainer.py (RED a9c932a → GREEN 8b0fd3a, 433 行 min_lines=110 充足)
3 関数を実装（loguru logger・絶対 import・RESEARCH Code Examples VERIFIED コードベース）:

- **`train_fold_model(X_train, y_train, X_val, y_val, config) -> lgb.LGBMClassifier`**:
  - Pitfall #1 VERIFIED: `clf.fit(X_train, y_train, eval_set=[(X_val, y_val)], callbacks=[lgb.early_stopping(stopping_rounds, verbose, first_metric_only), lgb.log_evaluation(period)])`。**`early_stopping_rounds` を fit() に渡さない**（AST テストが違反を検出）。
  - sensible defaults (D-13): objective=binary, num_leaves, learning_rate, min_data_in_leaf, feature_fraction, bagging_fraction, bagging_freq, max_depth, lambda_l1, lambda_l2, min_gain_to_split, n_estimators, random_state=seed, verbose=-1。`_build_classifier(config)` が model block の欠落キーを D-13 default で補完。
  - `best_iteration_ is None` の場合 logger.warning（Pitfall #1 徴候・callback が正しく動いていない）。

- **`collect_oof_predictions(df, splitter, config, feature_columns: list[str]) -> pd.DataFrame`** (Codex HIGH #5 fix):
  - **Cycle-2 HIGH #1**: `splitter.split(X, y, groups=df[group_col].values, dates=df["race_date"])` を呼ぶ。race_date は feature_columns に含まれないが dates 引数で明示的に渡すため、per-fold `max(train_dates) < min(val_dates)` assertion が常に発火（X 列有無に依存しない）。df が race_date 列を持たない場合は KeyError（load_features 07-02 が保持することを前提・trainer は drop しない）。
  - **Codex HIGH #2**: n_splits+1 date-block chunk scheme のため warm-up chunk 0 はどの fold の val にも含まれず、OOF 予測は生成されない（expanding window の定義）。`len(oof_df) < len(df)` を docstring + logger.info で明示。これは leak-free 契約（warm-up 予測は in-sample で Isotonic キャリブレーションがリークするため除外）。
  - **Codex HIGH #5**: feature_columns を明示的引数に取り、`config["data"]["feature_columns"]` を内部参照しない（AST テストが Subscript chain 検出）。
  - D-04 discretion: 各 fold の train を `split_train_validation`（07-03 module-level import・Codex HIGH #3）で学習本体と early-stopping val に分割（末尾 val_ratio・時系列安全）。
  - 戻り値 schema (D-15 OOF parquet): `race_id, horse_race_id, p_top3_raw, target_top3, fold`。

- **`train_final_model(df, config, feature_columns: list[str]) -> lgb.LGBMClassifier`** (Codex HIGH #5 + #6):
  - **Codex HIGH #6 (二段階学習)**:
    - Stage 1: `split_train_validation(df, val_ratio=0.2)` で末尾 20% を val に切り出し、`train_fold_model` で学習し `best_iteration_val = clf.best_iteration_` を取得。best_iteration_val is None の場合（early stopping 未発火・退化 fixture）は n_estimators にフォールバック + logger.warning。
    - Stage 2: FRESH `LGBMClassifier` を `set_params(n_estimators=best_iteration_val)` で構築し、**全入力行**を `fit(X_all, y_all, callbacks=[lgb.log_evaluation(period)])` で再学習（early_stopping なし・iteration count 固定）。返すモデルは全 2018-2024 行で学習済み（~80% ではない・D-15/Open-Question-#3 契約）。
    - Stage 2 の `best_iteration_` は None（early stopping callback なし・正しい）。`_best_iteration_val` カスタム属性で Stage 1 の決定値を公開（run_train/tests 検証用）。

### Task 2 — tests/ml/test_trainer.py + tests/ml/conftest.py (RED a9c932a → GREEN 8b0fd3a)
- 07-01 skip skeleton を完全実装に置換。6 テスト GREEN。
- **conftest ml_config 拡張** (Rule 2): data.target_column / cv.group_column / cv.early_stopping_val_ratio / model の full block（max_depth, lambda_l1, lambda_l2, min_gain_to_split）/ num_leaves=8, min_data_in_leaf=2, stopping_rounds=5 に縮小。他 ml テストは evaluation.n_bins + top-level keys のみ消費で非影響（回帰 545 passed で検証済み）。
- `_TRAINER_FEATURE_COLUMNS`: sample_feature_df の数値+categorical カラム（race_id/race_date/horse_number/target/exclude を除外）。
- `_derive_horse_race_id`: テスト内で sample_feature_df に D-15 horse_race_id（アンダースコアなし）を付与。
- `_ensure_race_date_datetime`: race_date を datetime 化（GroupTimeSeriesSplit 要求）。
- `_SpySplitter(BaseCrossValidator)`: split() 呼び出しの kwargs を記録し、Cycle-2 HIGH #1 の dates 転送を検証。
- `_const_str` AST helper: 文字列定数 Subscript キーを抽出。

**6 テスト:**
- **test_train_fold_model_returns_classifier** (Test 1): 戻り値 isinstance LGBMClassifier、best_iteration_ int で None でない、predict_proba shape (n,2)。
- **test_early_stopping_fires** (Test 2, Pitfall #1・Rule 1 determinism fix): 300行 pure-noise synthetic frame（RandomState=42、gaussian feature 1つ・coin-flip label）で best_iteration_ < n_estimators=200 を assert（実測 best_iteration_=1）。AST で `early_stopping_rounds=` kwarg を fit() 呼出で検出しないこと + `lgb.early_stopping` callback 使用を検証。
- **test_collect_oof_predictions** (Test 3, Codex HIGH #2): 6レース fixture + GroupTimeSeriesSplit(n_splits=3)。戻り値列 {race_id, horse_race_id, p_top3_raw, target_top3, fold}、fold ⊆ {0,1,2}、**len(oof_df) < len(df)** を明示 assert、p_top3_raw ∈ [0,1]・非 NaN。
- **test_collect_oof_predictions_feature_columns_arg** (Test 4, Codex HIGH #5): inspect.signature に feature_columns パラメータ存在 + AST で config['data']['feature_columns'] Subscript chain を実行コードから検出しないこと。
- **test_train_final_model_two_stage** (Test 5, Codex HIGH #6): LGBMClassifier.fit をスパイして fit_calls を記録。Stage 1 が early stopping 使用・Stage 2 が非使用・**Stage 2 学習行数 == len(df)** を assert（~80% ではなく全量）。`_best_iteration_val` カスタム属性が int。
- **test_collect_oof_passes_dates_to_splitter** (Test 6, Cycle-2 HIGH #1): _SpySplitter で split() 呼出の dates kwarg を記録。全呼出で dates が渡り、値が df["race_date"].values と一致。df が race_date 列を持たない場合は KeyError（前提違反の早期検出）。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] conftest ml_config incomplete for trainer**
- **Found during:** Task 1（テスト実行時に config キーが不足）
- **Issue:** PLAN は `config["data"]["target_column"]`, `config["cv"]["group_column"]`, `config["cv"]["early_stopping_val_ratio"]`, model block の `max_depth/lambda_l1/lambda_l2/min_gain_to_split` を前提としていたが、07-01 conftest の ml_config はこれらを持たず、trainer が直接 KeyError を起こすか default fallback に頼る状態だった。07-07 は config YAML にこれらを追加するが、07-04 の時点ではテストが通らない。
- **Fix:** conftest ml_config に data.target_column=target_top3, cv.group_column=race_id（既存 cv.group_col と並存）, cv.early_stopping_val_ratio=0.2, model の full block（max_depth=-1, lambda_l1=0.0, lambda_l2=0.0, min_gain_to_split=0.0）を追加。trainer 側は `.get(key, default)` で D-13 sensible defaults にフォールバックする二重安全設計（07-07 config 完備時には config 値が優先）。他 ml テスト（calibrator/evaluator/baseline）は evaluation.n_bins + top-level keys のみ消費で非影響（回帰 545 passed 3 skipped で検証）。
- **Files modified:** tests/ml/conftest.py
- **Commit:** a9c932a

**2. [Rule 1 - Bug] test_early_stopping_fires never triggers on sample_feature_df**
- **Found during:** Task 1（初回テスト実行で best_iteration_=50 >= n_estimators=50 が失敗）
- **Issue:** sample_feature_df の target_top3 は finish_position（horse_number に従い 1,2,3,... を循環）から派生するため、horse_number と完全相関で分離が自明。10行 val で binary_logloss 0.00234（ほぼ完璧）まで単調減少し、stopping_rounds=5 の patience を超えずに 50 iteration 完走 → early stopping 非発火。Cycle-5 MEDIUM carry-over note が予言した非決定性。
- **Fix:** test_early_stopping_fires で sample_feature_df の代わりに **300行 pure-noise synthetic frame**（np.random.RandomState(42)・gaussian feature 1つ・coin-flip label）を使用。label が feature と無相関のため val logloss が非単調になり、stopping_rounds=10 で iteration 1 で早期停止（実測 best_iteration_=1 < n_estimators=200）。deterministic=True/num_threads=1 は不要だった（noise label で十分非単調）。
- **Files modified:** tests/ml/test_trainer.py (test_early_stopping_fires)
- **Commit:** a9c932a (RED) / 8b0fd3a (GREEN)

**3. [Rule 1 - Bug] Pitfall #1 + Codex HIGH #5 meta-guards false-positive on docstrings**
- **Found during:** Task 1（初回テスト実行で "early_stopping_rounds not in src" が docstring の言及で失敗・"config['data']['feature_columns'] not in src" も同様）
- **Issue:** PLAN 案の `assert "early_stopping_rounds" not in inspect.getsource(train_fold_model)` と `assert 'config["data"]["feature_columns"]' not in src` は raw substring 検索のため、API ドキュメントとして docstring に正当に記載したこれらのトークンを検出して false-positive。実行可能コードでの違反を検出したいのに docstring も引っかかる。
- **Fix:** AST-based meta-guard に変更。`ast.walk(tree)` で実行可能ノードのみ検査: (a) Pitfall #1 は `ast.Call.keywords` の `kw.arg == "early_stopping_rounds"` を検出（fit() への kwarg のみ）・(b) Codex HIGH #5 は `config["data"]["feature_columns"]` の Subscript chain（inner.value.id=="config" / inner.slice=="data" / outer.slice=="feature_columns"）を検出。docstring の Constant 文字列は AST ノードにならないため false-positive 解消。`_const_str` helper で Subscript キーを文字列定数として抽出。
- **Files modified:** tests/ml/test_trainer.py (test_early_stopping_fires, test_collect_oof_predictions_feature_columns_arg)
- **Commit:** a9c932a (RED) / 8b0fd3a (GREEN)

## Verification

| Check | Command | Result |
|-------|---------|--------|
| Task 1+2 GREEN | `python -m pytest tests/ml/test_trainer.py -x -q` | 6 passed in 1.10s |
| tests/ml/ full | `python -m pytest tests/ml/ -q` | 32 passed, 2 skipped, 0 failed |
| Full suite regression | `python -m pytest tests/ -q` | 545 passed, 3 skipped, 0 failed (07-03 baseline 526/18 -> +19 unskipped, no regressions; conftest extension safe) |
| imports | `python -c "from src.ml.trainer import train_fold_model, collect_oof_predictions, train_final_model; print('ok')"` | ok |
| grep early_stopping_rounds in code (Pitfall #1) | AST test (test_early_stopping_fires) | no `early_stopping_rounds=` kwarg in any fit() Call node |
| grep lgb.early_stopping (>=1) | `grep -c "lgb.early_stopping" src/ml/trainer.py` | 3 (>=1) |
| grep best_iteration_ (>=2) | `grep -c "best_iteration_" src/ml/trainer.py` | 26 (>=2) |
| grep module-level split_train_validation import (==1, Codex HIGH #3) | `grep -c "from src.ml.group_timeseries_split import split_train_validation" src/ml/trainer.py` | 1 (==1) |
| grep dates=df["race_date"] forward (>=1, Cycle-2 HIGH #1) | `grep -cE 'dates=df\["race_date"\]' src/ml/trainer.py` | 4 (>=1) |
| grep feature_columns (>=3) | `grep -c "feature_columns" src/ml/trainer.py` | 21 (>=3) |
| min_lines (>=110) | `wc -l src/ml/trainer.py` | 433 (>=110) |
| OOF row count < input (Codex HIGH #2) | test_collect_oof_predictions assertion | PASS (oof_rows < input_rows for 6-race fixture with n_splits=3) |
| feature_columns explicit arg (Codex HIGH #5) | test_collect_oof_predictions_feature_columns_arg | PASS (signature has feature_columns, AST finds no config['data']['feature_columns'] subscript) |
| Stage 2 trains on ALL rows (Codex HIGH #6) | test_train_final_model_two_stage fit spy | PASS (last fit call n_rows == len(df), no early stopping) |
| dates forwarded to splitter (Cycle-2 HIGH #1) | test_collect_oof_passes_dates_to_splitter spy | PASS (every split() call has dates kwarg == df["race_date"].values; missing race_date raises KeyError) |
| post-commit deletion check | `git diff --diff-filter=D --name-only HEAD~2 HEAD` | empty (no accidental file deletions) |

## Known Stubs

None. `train_fold_model` / `collect_oof_predictions` / `train_final_model` は hermetic fixture で完全に動作し、Pitfall #1 callback API で best_iteration_ が populated、OOF 行数 < 入力行数（Codex HIGH #2 leak-free 契約）、二段階全量再学習（Codex HIGH #6）、dates=df["race_date"] 転送（Cycle-2 HIGH #1・splitter の per-fold temporal-order assertion が本番 path で発火）が検証済み。production features_train.parquet (322,510 train rows) に対する gated 実行は 07-07 run_train が担う（本 plan の範囲外）。

## Threat Flags

None. T-07-04-01..06 は全て disposition=mitigate で実装内に反映:
- T-07-04-01 (overfitting): D-13 sensible defaults (num_leaves=31, learning_rate=0.05, min_data_in_leaf=100, feature_fraction=0.9, bagging) + early stopping (stopping_rounds)。
- T-07-04-02 (Pitfall #1 API): callbacks=[lgb.early_stopping(...), lgb.log_evaluation(...)] のみ使用・early_stopping_rounds= kwarg は AST test で禁止・best_iteration_ None-warning が runtime 徴候。
- T-07-04-03 (OOF leakage・Codex HIGH #2): GroupTimeSeriesSplit n_splits+1 chunks 注入で race_id グループ化・時系列順保証・warm-up chunk 0 除外（in-sample 予測で Isotonic キャリブレーションがリークするのを防止）・len(oof_df) < len(df) で検証。
- T-07-04-04 (D-15 契約・Codex HIGH #6): 二段階学習・Stage 2 は全行で best_iteration_val まで再学習・返すモデルは全量学習済み（~80% ではない）。
- T-07-04-05 (Codex HIGH #5 feature_columns): 明示的引数・config 参照廃止・AST test で Subscript chain 検出禁止。
- T-07-04-06 (Cycle-2 HIGH #1 temporal-order dead code): dates=df["race_date"] 明示的転送・splitter の per-fold assertion が常に発火・missing race_date は KeyError で早期検出。

## TDD Gate Compliance

RED gate: commit `a9c932a` (test: add trainer tests (RED) — ModuleNotFoundError until src/ml/trainer.py exists) — tests/ml/test_trainer.py unskipped + 6 tests implemented + conftest extended; src/ml/trainer.py 未作成のため import 時に ModuleNotFoundError で collection error。
GREEN gate: commit `8b0fd3a` (feat: implement trainer — train_fold_model + collect_oof_predictions + train_final_model) — src/ml/trainer.py 実装完了・6 テスト GREEN。
REFACTOR gate: 不要（GREEN 時点でクリーン・補助関数 _build_classifier/_build_callbacks/_resolve_* で関心分離済み）。

## Self-Check: PASSED

- Created/modified files exist:
  - FOUND: src/ml/trainer.py
  - FOUND: tests/ml/test_trainer.py
  - FOUND: tests/ml/conftest.py
- Commits exist:
  - FOUND: a9c932a (RED — trainer tests + conftest extension)
  - FOUND: 8b0fd3a (GREEN — trainer.py implementation)
