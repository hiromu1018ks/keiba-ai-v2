---
phase: 07-model-a-top-3-probability
plan: 03
subsystem: ml-cv-splitter
tags: [wave-1, time-series-cv, race-grouping, sklearn-compat, leakage-prevention, expanding-window, date-block-chunking, temporal-invariant]
requires:
  - "07-01 (tests/ml/ scaffold + conftest fixtures + pyproject deps)"
  - "07-02 (data_loader.load_features returns race_date-ascending frames, trainer passes dates=df['race_date'])"
  - "phase-06 (unified corpus features_train.parquet; orchestrator cross-check 23,288 training races / 1,236 unique dates)"
provides:
  - "src.ml.group_timeseries_split.GroupTimeSeriesSplit(BaseCrossValidator) — race_id-grouped + race_date-chronology time-series CV with n_splits+1 date-block chunk scheme"
  - "src.ml.group_timeseries_split.split_train_validation(train_df, val_ratio=0.2, sort_column='race_date') -> (inner_train_df, inner_val_df) — fold-inner early-stopping val carve-out"
  - "TestGroupTimeSeriesSplit with 8 GREEN tests (6 hermetic + 2 hermetic regression guards)"
affects:
  - "07-04 trainer.collect_oof_predictions calls splitter.split(X, y, groups=race_ids, dates=df['race_date']) — Cycle-2 HIGH #1 assertion fires in production path"
  - "07-07 run_train orchestrator reuses GroupTimeSeriesSplit for OOF collection + final model train/val carve"
  - "Phase 8 Harville EV reuses GroupTimeSeriesSplit to guarantee in-race p_top3 integrity"
  - "Phase 9 walk-forward backtest reuses GroupTimeSeriesSplit as the race-aware CV asset"
tech_stack:
  added: []
  patterns:
    - "n_splits+1 date-block chunk scheme (Codex HIGH #1): chunk 0 = warm-up train (always non-empty), chunks 1..n_splits = per-fold validation; expanding window — fold i train = chunks 0..i cumulative"
    - "date-block-aware chunking (Cycle-3 HIGH): chunks built from ordered unique race_date blocks, so all race_ids sharing a date are an atomic block inside a single chunk; max(train_dates) < min(val_dates) is a genuine invariant"
    - "dates explicit arg on split(X, y, groups, dates=None) (Cycle-2 HIGH #1): per-fold temporal-order assertion always fires when dates are provided (X column-presence independent)"
    - "explicit ValueError when dates=None + X lacks race_date (Cycle-5 MEDIUM: no silent skip / pd.unique(None) fall-through)"
    - "defensive race_id→single-date validation via groupby(race_id)[race_date].nunique().max()==1 (Cycle-5 LOW)"
    - "date_to_rows precomputed dict for O(chunk_size) mask building (avoids O(n_rows*n_dates) np.isin)"
    - "non-uniform races-per-date [4,5,4,5,4,5] in Cycle-3 regression fixture so legacy race-count chunking cannot accidentally align boundaries (Codex Cycle-4 suggestion #2)"
key_files:
  created:
    - src/ml/group_timeseries_split.py
  modified:
    - tests/ml/test_group_timeseries_split.py
decisions:
  - "GroupTimeSeriesSplit is bespoke (NOT mlxtend) per CLAUDE.md 'Use Instead: 必要なものだけ' — produces a Phase 8/9-reusable asset and avoids an external dependency."
  - "n_splits+1 date-block chunk scheme adopted (Codex HIGH #1 fix): chunk 0 = warm-up train is ALWAYS in every fold's training set, so fold 0 train is non-empty. Legacy n_splits-chunk algorithm had fold 0 train = chunks[:0] = empty (structural bug)."
  - "Cycle-3 HIGH fix: chunking is date-block-aware (race_count -> unique race_date). All race_ids sharing a date are an atomic block inside one chunk; a race_date can never straddle a train/val boundary. max(train_dates) < min(val_dates) is now a GENUINE INVARIANT (holds by construction), so the strict per-fold assertion NEVER raises on JRA's real data (mean 30.75 races/date, zero single-race dates). Legacy race-count chunking placed >=1 of 5 inner boundaries inside a date for any 6-chunk split of the 23,288-race / 1,236-date corpus, halting the production 5-fold run via AssertionError."
  - "Cycle-2 HIGH #1 fix: split(X, y, groups, dates=None) — dates is an explicit arg so the per-fold temporal-order assertion ALWAYS fires when dates are provided, regardless of whether X carries race_date. The legacy gate ('X is DataFrame with race_date column') was dead code in production because the trainer passes X=df[feature_columns] (race_date ∈ drop_columns). trainer.collect_oof_predictions (07-04) will pass dates=df['race_date'] explicitly."
  - "Cycle-5 MEDIUM: dates=None + X-lacks-race_date raises explicit ValueError (not silent skip). The old behavior fell through to pd.unique(None) and raised a confusing TypeError."
  - "Cycle-5 LOW: defensive validation that each race_id maps to exactly one race_date (groupby(race_id)[race_date].nunique().max()==1). JRA race_ids encode the date so normally satisfied, but data corruption (race_id duplicated on two dates) would otherwise silently produce wrong folds."
  - "split_train_validation carves the inner early-stopping val from the TAIL of each fold's training frame (by race_date), keeping the inner train/val pair time-safe. This is the D-04 'discretion' region."
metrics:
  duration: 688s
  completed: 2026-06-15
  tasks: 2
  files: 2
---

# Phase 7 Plan 03: GroupTimeSeriesSplit Summary

race_id グループ化 + race_date 時系列順で fold 境界を切る `GroupTimeSeriesSplit`（sklearn BaseCrossValidator 準拠）を実装。Codex HIGH #1（fold-0 empty train → n_splits+1 chunk scheme）・Cycle-2 HIGH #1（temporal-order assertion dead code → dates 明示的引数）・Cycle-3 HIGH（same-date fold boundary が本番 5-fold run を halt → date-block-aware chunking）・Cycle-5 MEDIUM（dates=None fall-through → 明示的 ValueError）・Cycle-5 LOW（race_id→multi-date corruption → defensive validation）の全修正を実装・検証。

## What Was Built

### Task 1 — src/ml/group_timeseries_split.py (RED 831182e → GREEN a64c34c, 386 行 min_lines=80 充足)
- **`GroupTimeSeriesSplit(BaseCrossValidator)`** を実装。`__init__(n_splits=5)`, `get_n_splits(X, y, groups) -> int`, `split(X, y, groups, dates=None) -> Iterator[(train_idx, val_idx)]` の sklearn 互換 API。
- **CV contract（docstring 明記）**: n_splits+1 date-block chunks。chunk 0 = warm-up train（常に全 fold の train に含まれる・非空）・chunks 1..n_splits = 各 fold の validation。fold i の train = unique_dates[:val_start]（date-block chunks 0..i = cumulative expanding window・warm-up 常時含入）・val = unique_dates[val_start:val_end]（date-block chunk i+1）。OOF target = chunks 1..n_splits のみ（warm-up chunk 0 は OOF 対象外）。
- **Cycle-3 HIGH fix の中核**: `pd.unique(dates_arr)` で ordered unique dates 配列を作り（呼び出し側が race_date 昇順ソート済み前提・07-02 load_features が保証）、`_compute_date_block_sizes(n_dates)` で n_splits+1 個の date-block chunk サイズを計算（base = n_dates // (n_splits+1) >= 1・rem 分配）。各 date-block chunk は dates の完全なブロック（日付をまたがない）。同一 race_date の全 race_id は単一 chunk に収まる。
- **`_compute_date_block_sizes(n_dates) -> np.ndarray`**: n_splits+1 サイズの int 配列を返す。base = n_dates // (n_splits+1)、rem = n_dates % (n_splits+1)、最初の rem 個の chunk に +1。base == 0 は split() の ValueError（n_dates < n_splits+1）で排除済み。
- **Cycle-2 HIGH #1 fix**: `split(X, y, groups, dates=None)` の明示的 dates 引数。dates が渡された場合、per-fold で `assert max(dates[train_idx]) < min(dates[val_idx])` を常に実行（X 列の有無に依存しない）。dates=None + X が race_date 列を持つ DataFrame なら解決して assertion 実行（レガシー互換）。
- **Cycle-5 MEDIUM fix**: dates is None かつ X が race_date 列を持たない場合 `ValueError("dates must be provided ...")` を raise（pd.unique(None) への fall through を防止）。
- **Cycle-5 LOW fix**: `pd.DataFrame({"race_id": groups, "race_date": dates}).groupby("race_id")["race_date"].nunique().max()` で各 race_id が exactly 1 date に属すことを防御的に assert（race_id が複数 date に跨るデータ不整合を早期検出・JRA では通常1 date だが defensive に検証）。
- **Runtime temporal-order assertion**: 各 fold で `max(train_dates_values) < min(val_dates_values)` を必ず実行。date-block chunking により construction 上常に真（genuine invariant）なので本番 5-fold run で決して raise しない。
- **`split_train_validation(train_df, val_ratio=0.2, sort_column="race_date") -> (inner_train_df, inner_val_df)`**: fold 内 train を race_date 昇順でソートし、末尾 val_ratio のレースを early-stopping 用 inner val に切り出す。trainer.py (07-04) が各 fold 内で使用。

### Task 2 — tests/ml/test_group_timeseries_split.py (RED 831182e で実装、GREEN a64c34c で通過)
- 07-01 skip skeleton を完全実装に置換。8 テスト GREEN。
- **hermetic fixture builder `_make_fixture(n_dates, races_per_date, horses_per_race=3)`**: 指定した unique date 数 × 各 date のレース数 × 各レースの頭数で、race_date 昇順ソート済みの feature DataFrame を構築。X_no_race_date（feature_columns のみ・trainer の X=df[feature_columns] を模倣）・y・race_ids・date_series を返す。
- **test_get_n_splits** (Test 1): sklearn 互換。`GroupTimeSeriesSplit(n_splits=5).get_n_splits() == 5`。X=None, y=None, groups=None でも動作。
- **test_same_race_same_fold** (Test 2): D-03 同一 race 同一 fold。各 fold で `set(train_race_ids) & set(val_race_ids) == set()`（disjoint）を明示 assert。
- **test_temporal_order** (Test 3): race_date 昇順厳守。per-fold `max(train_dates) < min(val_dates)` + fold-to-fold `val_dates.min()` 単調増加を assert。
- **test_no_boundary_split** (Test 4): 同一 race_id の全行が同一 fold に揃うことを assert。
- **test_fold0_train_non_empty** (Test 5, Codex HIGH #1 regression guard): fold 0 の train_idx len > 0 を明示 assert。全 fold (0..4) の train_idx が非空であることも assert（warm-up chunk 常時含入 expanding window の検証）。
- **test_dates_arg_assertion_always_fires** (Test 6, Cycle-2 HIGH #1・hermetic): (a) X が race_date 列を持たなくても dates を渡せば assertion が通過。(b) dates を逆順にすると AssertionError が raise（assertion が実際に実行されている証拠・dead code でないことの証明）。(c) [Cycle-5 MEDIUM] dates=None + X が race_date 列を持たない場合は ValueError が raise。
- **test_same_date_not_split_across_fold_boundary** (Test 7, Cycle-3 HIGH fix・regression・hermetic): **[Cycle-5 LOW fix]** 全 race_date が複数レースを持つ fixture（races-per-date = [4, 5, 4, 5, 4, 5] のように意図的に非均一・Codex Cycle-4 suggestion #2）を構築。(a) 全 fold で `set(train_dates) & set(val_dates) == empty` を assert。(b) strict `<` assertion が一度も raise しないことを assert（split 呼び出しが正常に完了 = 本番 halt 欠陥が construction 上起きないことの証明・Cycle-3 HIGH regression guard）。
- **test_race_id_maps_to_single_date** (Test 8, Cycle-5 LOW fix・Codex Cycle-4 suggestion #3・hermetic): (a) 正常 fixture（各 race_id が1 date のみ）で split 成功。(b) 1 つの race_id を2つの異なる race_date 行に複製して fixture を汚染し、AssertionError/ValueError が raise されることを assert。
- クラス docstring に「MODA-02: temporal CV with race_id grouping — prevents boundary split and temporal leakage. n_splits+1 date-block chunk scheme ensures fold 0 has non-empty training set and no race_date straddles a train/val boundary (Cycle-3 HIGH fix)」を記載。各テスト docstring に「Test N: MODA-02 ...」を明記。

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written. 両 task とも TDD RED→GREEN サイクルで完了（Task 1 の `tdd="true"` 指示に従い、Task 2 の skip 解除・GREEN 化は Task 1 の GREEN ステップで同時に達成）。

### Task 2達成経緯の明記

Task 2（skip 解除 + 7 テスト GREEN 化）は、Task 1 の TDD サイクル内で完了している。本 plan の Task 1 は `tdd="true"` であり、RED commit（831182e・全テスト実装・ModuleNotFoundError で失敗）→ GREEN commit（a64c34c・実装完了・8 テスト通過）の順で実行した。Task 2 の `<action>` が要求する作業（skip skeleton の完全実装への置換・各テストの docstring「Test N: MODA-02 ...」明記・クラス docstring 記載・hermetic fixture 構築・各 assertion の明示的検証）は Task 1 の実装で全て満たされている。したがって Task 2 単独の code commit は作成せず、Task 1 と Task 2 の成果は RED (831182e) + GREEN (a64c34c) の 2 commit に集約される。

## Verification

| Check | Command | Result |
|-------|---------|--------|
| Task 1 GREEN | `python -m pytest tests/ml/test_group_timeseries_split.py -x -q` | 8 passed in 0.62s |
| Task 2 default tests/ml/ | `python -m pytest tests/ml/ -q` | 13 passed, 17 skipped, 0 failed (07-01 skeleton + 07-02 gated skipped) |
| Full suite regression | `python -m pytest tests/ -q` | 526 passed, 18 skipped, 0 failed (07-02 baseline 518/22 -> +8 unskipped, -4 skipped) |
| sklearn BaseCrossValidator subclass | `python -c "from src.ml.group_timeseries_split import GroupTimeSeriesSplit; from sklearn.model_selection import BaseCrossValidator; assert issubclass(GroupTimeSeriesSplit, BaseCrossValidator); print('ok')"` | ok |
| grep BaseCrossValidator (>=1) | `grep -c "BaseCrossValidator" src/ml/group_timeseries_split.py` | 4 |
| grep n_splits+1 chunks (>=1) | `grep -cE "n_splits \+ 1\|n_splits\+1"` | 13 |
| grep date_block (>=2) | `grep -cE "_compute_date_block_sizes\|date_block"` | 6 |
| grep unique_dates (>=1) | `grep -cE "unique_dates\|pd.unique(dates)"` | 7 |
| grep split_train_validation (>=1) | `grep -c "split_train_validation"` | 2 |
| grep dates (>=2) | `grep -c "dates"` | 74 |
| grep dates=None in split signature | `grep -nE 'dates: Any = None'` | line 135 (matches `def split(` multi-line signature) |
| grep 'dates must be provided\|ValueError' (>=1) | `grep -cE "dates must be provided\|ValueError"` | 12 |
| min_lines (>=80) | `wc -l src/ml/group_timeseries_split.py` | 386 |

## Known Stubs

None. `GroupTimeSeriesSplit` は hermetic fixture で完全に動作し、production corpus（23,288 races / 1,236 unique dates / mean 30.75 races per date）の条件下で strict `<` assertion が決して raise しないことが date-block chunking により construction 上保証される。trainer.collect_oof_predictions (07-04) が dates=df["race_date"] を渡すことで本番 path で assertion が発火することが 07-04 acceptance_criteria で検証予定。

## Threat Flags

None. T-07-03-01..07 は全て disposition=mitigate で実装内に反映:
- T-07-03-01 (Temporal leakage): race_id グループ化 + n_splits+1 chunk scheme の expanding window + runtime `max(train_dates) < min(val_dates)` assertion（Cycle-2 HIGH #1・date-block chunking で construction 上常に真・Cycle-3 HIGH）。
- T-07-03-02 (Harville 整合性): 同一 race_id 同一 fold により Phase 8 Harville 計算時にレース内 p_top3 の整合性が保たれる（D-03 根拠）。
- T-07-03-03 (Codex HIGH #1 fold-0 empty train): n_splits+1 chunks（chunk 0 = warm-up train・非空）+ test_fold0_train_non_empty regression guard。
- T-07-03-04 (Cycle-2 HIGH #1 temporal-order dead code): split(X, y, groups, dates=None) 明示的引数 + test_dates_arg_assertion_always_fires で dead code でないことを証明。
- T-07-03-05 (Cycle-3 HIGH same-date fold boundary halts production): date-block-aware chunking（race_count -> unique race_date ブロック）+ test_same_date_not_split_across_fold_boundary regression guard。
- T-07-03-06 (Cycle-5 MEDIUM dates=None fall-through): 明示的 ValueError + test_dates_arg_assertion_always_fires (c)。
- T-07-03-07 (Cycle-5 LOW race_id→multi-date corruption): groupby(race_id)[race_date].nunique().max()==1 defensive assertion + test_race_id_maps_to_single_date。

## TDD Gate Compliance

RED gate: commit `831182e` (test: add failing tests for GroupTimeSeriesSplit (RED)) — ModuleNotFoundError で全テスト collection error（source 未作成）。
GREEN gate: commit `a64c34c` (feat: implement GroupTimeSeriesSplit (GREEN)) — 8 テスト GREEN。
REFACTOR gate: 不要（GREEN 時点でクリーン・early return も可読性重視）。

## Self-Check: PASSED

- Created/modified files exist:
  - FOUND: src/ml/group_timeseries_split.py
  - FOUND: tests/ml/test_group_timeseries_split.py
- Commits exist:
  - FOUND: 831182e (RED — failing tests for GroupTimeSeriesSplit)
  - FOUND: a64c34c (GREEN — GroupTimeSeriesSplit implementation)
