---
phase: 07-model-a-top-3-probability
plan: 02
subsystem: ml-data-loader
tags: [wave-1, data-loading, lightgbm-input, dtype-safety, leakage-audit, horse-race-id, temporal-sort]
requires:
  - "07-01 (tests/ml/ scaffold + conftest fixtures + pyproject deps)"
  - "phase-06 (data/feature/features_train.parquet unified corpus, 534,953 rows)"
provides:
  - "src.ml.data_loader.load_features(feature_path, train_window, holdout_window, entry_path, expected_counts) -> dict[train, holdout, metadata]"
  - "src.ml.data_loader.PRODUCTION_COUNTS = {train_rows: 322510, train_races: 23288, holdout_rows: 66343, holdout_races: 4740}"
  - "TestFeatureLoad with 7 GREEN tests (5 hermetic + 2 gated RUN_GATED=1)"
affects:
  - "07-03 GroupTimeSeriesSplit consumes ascending-sorted train frame with race_date retained"
  - "07-04 trainer consumes train/holdout + passes dates=df[race_date] to splitter.split"
  - "07-06 baseline consumes holdout for popularity AUC"
  - "07-07 run_train forwards expected_counts (UNIFIED [] bypass sentinel) to hermetic E2E"
tech_stack:
  added: []
  patterns:
    - "UNIFIED expected_counts sentinel (None=production assert / []=bypass / dict=custom / {}=TypeError)"
    - "read-boundary temporal sort + is_monotonic_increasing assert (Cycle-2 HIGH #1)"
    - "race_date column RETAINED on returned frames (downstream trainer passes to splitter)"
    - "unconditional astype('category') on CATEGORICAL_COLUMNS (Pitfall #3: dtype==object misses string)"
    - "no-underscore horse_race_id format f'{race_id}{horse_number:02d}' (real-data authority over EntrySchema docstring)"
    - "inline-skip gated pattern mirroring tests/scraper/test_end_to_end.py live pattern"
key_files:
  created:
    - src/ml/data_loader.py
  modified:
    - tests/ml/test_data_loader.py
decisions:
  - "horse_race_id format is NO underscore f'{race_id}{horse_number:02d}' — verified against data/standard/entry.parquet (534,953/534,953 100% match). EntrySchema docstring '{race_id}_{horse_number:02d}' is WRONG; real data wins (Pitfall #2 VERIFIED)."
  - "UNIFIED empty-list [] is the sole expected_counts bypass sentinel. Empty dict {} raises TypeError (Cycle-2 HIGH #2 fix + Cycle-5 MEDIUM tightening via `isinstance(dict) and expected_counts` truthy guard so {} falls through to TypeError)."
  - "load_features performs df.sort_values(['race_date','race_id','horse_number']) + reset_index + is_monotonic_increasing assert at the read boundary because the on-disk features_train.parquet is NOT chronologically ordered (verified False pre-sort). GroupTimeSeriesSplit (07-03) requires ascending input."
  - "train/holdout DataFrames RETAIN the race_date column (not dropped) so the downstream trainer can pass dates=df['race_date'] to splitter.split and the per-fold temporal-order assertion always runs (X column-presence independent)."
  - "exclude_from_training=True rows removed from BOTH windows (train 1,240 + holdout 231 = 1,451 of 1,944 total; the remainder fall outside both windows)."
  - "audit_leakage uses [RaceSchema, EntrySchema] only (ResultSchema excluded — race_id is post-race in ResultSchema and would false-positive on the feature table)."
  - "[Rule 2 - missing critical functionality] gated inline skip added to both gated tests: os.environ RUN_GATED != '1' -> pytest.skip. The pyproject.toml gated marker only suppresses PytestUnknownMarkWarning and does NOT auto-skip; without the inline skip the gated tests would run in CI against the real corpus. Mirrors tests/scraper/test_end_to_end.py:713-720 live pattern."
metrics:
  duration: 955s
  completed: 2026-06-15
  tasks: 2
  files: 2
---

# Phase 7 Plan 02: data_loader / load_features Summary

features_train.parquet (534,953 行) を読み込む `load_features` を実装。Cycle-2 HIGH #1 (read-boundary race_date sort + monotonicity + race_date 列保持)・Cycle-2 HIGH #2 (UNIFIED expected_counts sentinel)・Codex HIGH #4 (hermetic E2E bypass)・Pitfall #2/#3/#4/#7 を全て実データ検証付きで解決。

## What Was Built

### Task 1 — src/ml/data_loader.py (commit 4348168)
- **`load_features(feature_path, train_window, holdout_window, entry_path, expected_counts)`** を実装 (295 行、min_lines=85 を充足)。
- 戻り値: `{"train": pd.DataFrame, "holdout": pd.DataFrame, "metadata": {...}}`。train/holdout は **race_date 列を保持** (Cycle-2 HIGH #1)。
- **PRODUCTION_COUNTS** 定数: `{train_rows: 322510, train_races: 23288, holdout_rows: 66343, holdout_races: 4740}` (実データ検証済み)。
- 処理フロー:
  1. Path 検証 + `pd.read_parquet(engine="pyarrow")` 読込 (per-table log のみ、per-row 禁止・MEMORY.md 準拠)。
  2. `race_date` → datetime 変換。
  3. **Cycle-2 HIGH #1**: `df.sort_values(["race_date","race_id","horse_number"]).reset_index(drop=True)` + `assert is_monotonic_increasing`。実測: on-disk parquet は時系列順ではない (verified False pre-sort)。
  4. `audit_leakage([RaceSchema, EntrySchema])` — ResultSchema は除外 (race_id post-race 誤検出回避)。warning のみ・D-12 準拠。
  5. **Pitfall #3**: `CATEGORICAL_COLUMNS` 全列を無条件 `astype("category")` (feature_generator の `dtype=="object"` 条件は `string` を見逃すため・実測: 7 列は string・jockey/trainer のみ既に category)。
  6. **Pitfall #4**: grade NaN カウントが category 変換前後で一致することを内部 assert (不一致は logger.warning)。
  7. **Pitfall #2**: `horse_race_id = race_id.astype(str) + horse_number.astype(int).str.zfill(2)` (**アンダースコアなし**・EntrySchema docstring は誤り・実データ優先)。entry.parquet と join 整合性を logger.info (実測: 534,953/534,953 = 100%)。
  8. window 分割: `exclude_from_training=True` は両窓から除外 (取消/除外馬・target=0・poisoning 回避)。
  9. **Codex HIGH #4 + Cycle-2 HIGH #2**: `expected_counts` sentinel で assert 制御。None=本番 / `[]`=bypass / 非空 dict=カスタム / `{}`=TypeError。`isinstance(expected_counts, dict) and expected_counts` の truthy ガードで空 dict を custom-assert 分岐に誤マッチさせない (Cycle-5 MEDIUM)。

### Task 2 — tests/ml/test_data_loader.py (commit dfa3c72)
- 07-01 skip skeleton を外し、7 テストを GREEN に。
- **hermetic 5 テスト** (sample_feature_df → tmp parquet → `load_features(expected_counts=[])`):
  - `test_categorical_conversion`: course_name/surface/direction/weather/track_condition/sex/grade/jockey/trainer 全列が category dtype (Pitfall #3)。
  - `test_horse_race_id_derive`: アンダースコアなし形式検証 + `sample_entry_df` と 1:1 set equality (Pitfall #2)。
  - `test_leakage_audit`: clean feature → `[]`、`popularity` 混入 → `["popularity"]` 検出 (D-12)。
  - `test_expected_counts_bypass`: `[]` 成功 / `None` AssertionError / `{}` TypeError の 3 パス全検証 (Codex HIGH #4 + Cycle-2 HIGH #2)。
  - `test_race_date_sorted_monotonic`: 降順入力 → 昇順出力、race_date 列保持、`metadata.race_date_sorted == True` (Cycle-2 HIGH #1)。
- **gated 2 テスト** (`@pytest.mark.gated` + inline skip `os.environ RUN_GATED != "1"`):
  - `test_train_holdout_window_counts`: 本番 322510/23288/66343/4740 (Pitfall #7)。
  - `test_grade_nan_preserved`: grade category dtype + ~95% NaN 比維持 (Pitfall #4)。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] gated inline skip wiring absent**
- **Found during:** Task 2 (gated テストが default 実行で走ってしまった)
- **Issue:** `pyproject.toml` の `gated` marker は `PytestUnknownMarkWarning` 抑制のみで、default skip を実装する `pytest_collection_modifyitems` hook が存在しなかった。07-01 SUMMARY は「gated marker pattern (RUN_GATED=1 env var) mirrors existing live marker pattern at tests/scraper/test_end_to_end.py:713」と宣言していたが、実 live pattern は marker ではなく **inline skip** (`os.environ.get("LIVE_SMOKE") != "1"` → `pytest.skip`)。marker 宣言だけでは CI で gated テストが本番 corpus に対して走ってしまう。
- **Fix:** 両 gated テストに `if os.environ.get("RUN_GATED") != "1": pytest.skip(...)` の inline skip を追加。tests/scraper/test_end_to_end.py:713-720 の live pattern と同一形式。
- **Files modified:** tests/ml/test_data_loader.py (test_train_holdout_window_counts, test_grade_nan_preserved)
- **Commit:** dfa3c72

**2. [Rule 1 - Bug] test_grade_nan_preserved threshold too strict**
- **Found during:** Task 2 (gated 実行で nan_count > 500000 が 366,117 で失敗)
- **Issue:** plan 案の `assert nan_count > 500000` は train+holdout window 内の grade NaN (366,117) に対して失敗する。元の 506,349 は全 parquet (534,953 行・両 window 外 + exclude_from_training=True 含む) の grade NaN であり、train+holdout 有効行 (388,853) の grade NaN は 366,117 (~94%)。Pitfall #4 の本質は「NaN が category 化で保持されること」であって固定数ではない。
- **Fix:** `assert nan_count / total > 0.80` (~95% 実測に対して robust) + `dtype.name == "category"` に変更。load_features 内部の before==after assertion が正確な保持チェックを担う。
- **Files modified:** tests/ml/test_data_loader.py (test_grade_nan_preserved)
- **Commit:** dfa3c72

## Verification

| Check | Command | Result |
|-------|---------|--------|
| Task 1 hermetic production load | `python -c "from src.ml.data_loader import load_features; r=load_features(); print(r['metadata'])"` | train=322510/23288 holdout=66343/4740 race_date_sorted=True leaked=[] |
| Task 1 default tests/ml/ | `python -m pytest tests/ml/test_data_loader.py -q` | 5 passed, 2 skipped (gated inline-skip) |
| Task 1 gated tests | `RUN_GATED=1 python -m pytest tests/ml/test_data_loader.py -q` | 7 passed |
| Task 1 tests/ml/ full | `python -m pytest tests/ml/ -q` | 5 passed, 21 skipped (他の tests/ml/ は still skip) |
| Task 1 full suite regression | `python -m pytest tests/ -q` | 518 passed, 22 skipped, 0 failed (07-01 baseline 513/25 → +5 unskipped, -3 skipped) |
| horse_race_id join integrity | load_features log | 534,953/534,953 (100.0000%) match entry.parquet |
| parquet monotonicity pre-sort | `df['race_date'].is_monotonic_increasing` | False (sort が必須の根拠・Cycle-2 HIGH #1) |
| grep astype category | `grep -c 'astype("category")' src/ml/data_loader.py` | 3 (>=1) |
| grep horse_race_id | `grep -c horse_race_id src/ml/data_loader.py` | 12 (>=2) |
| grep audit_leakage | `grep -c audit_leakage src/ml/data_loader.py` | 3 (>=1) |
| grep expected_counts | `grep -c expected_counts src/ml/data_loader.py` | 18 (>=2) |
| grep PRODUCTION_COUNTS literals | `grep -cE "322510\|23288\|66343\|4740"` | 6 (>=1) |
| grep sort_values | `grep -c sort_values src/ml/data_loader.py` | 1 (>=1) |
| grep is_monotonic_increasing | `grep -c is_monotonic_increasing src/ml/data_loader.py` | 2 (>=1) |
| grep forbidden {} sentinel | `grep -cE 'expected_counts == \{\}' src/ml/data_loader.py` | 0 (==0) |
| grep Cycle-5 dict-and-nonempty | `grep -cE 'isinstance\(expected_counts, dict\) and expected_counts'` | 2 (>=1) |
| min_lines | `wc -l src/ml/data_loader.py` | 295 (>=85) |
| TDD 07-04 dates forward (deferred) | `grep -c "dates" src/ml/trainer.py` | trainer は 07-04 で実装 (本 plan の範囲外・07-04 acceptance_criteria で検証) |

## Known Stubs

None. `load_features` は本番 features_train.parquet に対して完全に動作し、実測行数 (322510/23288/66343/4740) が PRODUCTION_COUNTS と一致、horse_race_id join 整合性 100%、リーク列空。Codex HIGH #4 / Cycle-2 HIGH #1 / Cycle-2 HIGH #2 は全て実測ベリファイドで解決済み。

## Threat Flags

None. T-07-02-01..07 は全て disposition=mitigate で実装内に反映:
- T-07-02-01 (post-race 混入): audit_leakage([RaceSchema, EntrySchema]) で popularity/win_odds 検出 (実測: leaked=[])。
- T-07-02-02 (horse_race_id derive): 実データのアンダースコアなし形式を採用、100% join 整合性。
- T-07-02-03 (categorical 変換): 無条件 astype("category") で string dtype を見逃さない。
- T-07-02-04 (window): PRODUCTION_COUNTS assert + exclude_from_training=True 両窓除外。
- T-07-02-05 (Codex HIGH #4): expected_counts sentinel で hermetic bypass 切替。
- T-07-02-06 (Cycle-2 HIGH #1): read-boundary sort + monotonicity assert + race_date 列保持。
- T-07-02-07 (Cycle-2 HIGH #2): UNIFIED 空 list [] sentinel + {} TypeError 拒否。

## Self-Check: PASSED

- Created/modified files exist:
  - FOUND: src/ml/data_loader.py
  - FOUND: tests/ml/test_data_loader.py
- Commits exist:
  - FOUND: 4348168 (Task 1 data_loader implementation)
  - FOUND: dfa3c72 (Task 2 tests unskipped + Rule 2 gated inline-skip + Rule 1 grade NaN threshold)
