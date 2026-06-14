---
phase: 04-scraping-infrastructure-race-data
plan: 05
subsystem: scraper/normalizer
tags: [scraper, normalizer, parquet, strict-dtype, partition-map, merge-dedup, atomic-write, cycle-2, cycle-3, pyarrow-compat]
requires:
  - 04-04 (parser output dict format — race/entries/results keys)
  - 04-03 (fetcher not directly required; normalizer consumes parser output)
  - src/schemas/{race,entry,result}.py (authoritative Pydantic schemas)
  - src/pipeline/column_mapping.py (KAGGLE_COLUMN_MAP — 13 race_flag_* targets)
provides:
  - "src/scraper/normalizer.py — normalize_to_parquet, _build_typed_dataframe (strict dtypes), validate_integrity, write_partitioned_parquet (merge-dedup + partition_map), SCHEMA_DTYPE_MAP"
  - "tests/scraper/test_normalizer.py — 30 tests across 5 classes (Cycle-2 #3/#4/#6 + Cycle-3 #1 regression guards)"
affects:
  - "04-06 (orchestrator) wires normalize_to_parquet into run_scrape; consumes partition_map contract"
  - "Phase 6 (Data Integration) — scraped standard Parquet must be Arrow-compatible with Kaggle standard Parquet (Cycle-3 #1 corner dtype verified)"
tech-stack:
  added: []
  patterns:
    - "Strict dtype coercion: nullable pandas Int64/Float64/boolean (NOT errors=ignore); genuine failures raise TypeError"
    - "Schema.model_fields reindex — empty input produces typed zero-row DataFrame with ALL columns"
    - "Date-partitioned atomic Parquet write (temp + os.replace) with same-month read-merge-dedup on primary key"
    - "partition_map (race_id->race_date) for entry/result tables which lack a race_date column"
    - "pyarrow.physical-type parity check: corner_1..corner_4 serialize to Arrow double (matches Kaggle result.parquet)"
key-files:
  created:
    - src/scraper/normalizer.py
    - tests/scraper/test_normalizer.py
  modified: []
decisions:
  - "CYCLE-2 #3: SCHEMA_DTYPE_MAP uses nullable pandas Int64/Float64/boolean wherever Kaggle Parquet is nullable; _build_typed_dataframe does NOT use astype(errors=ignore) anywhere; genuine conversion failures raise TypeError with column+schema message. finish_position is Int64 (Kaggle int64 nullable=True) so None does not silently become float64."
  - "CYCLE-3 #1: corner_1..corner_4 -> Float64 (Kaggle double nullable=True; verified via pyarrow.parquet.read_schema on data/standard/result.parquet). The Cycle-2 Int64 choice was wrong: Int64 serializes to Arrow int64 (str(int64)!=str(double)) and would FAIL the 04-06 physical-type equality test for all 4 corner columns. Float64 serializes to Arrow double (str matches)."
  - "CYCLE-2 #4: write_partitioned_parquet performs read-merge-dedup on primary_key (race_id for race, horse_race_id for entry/result) BEFORE atomic replace. keep='last' so newer re-run wins on conflict; a sentinel row from a prior smoke run survives a same-month re-run; duplicate primary keys collapse to one."
  - "CYCLE-2 #6: EntrySchema/ResultSchema have NO race_date column (verified). write_partitioned_parquet accepts partition_map (race_id->race_date) and looks up the partition key per row. Calling entry/result write WITHOUT partition_map raises KeyError mentioning 'partition_map' (fail loud, not silent mis-partition). normalize_to_parquet builds partition_map from the FILTERED race DataFrame and passes it to entry/result writes."
  - "CYCLE-1 MEDIUM: normalize_to_parquet does NOT call audit_leakage. popularity/win_odds are intentionally part of the entry table per D-06/D-03; the leakage audit is reserved for feature-layer generation."
  - "CYCLE-1 HIGH #7: _build_typed_dataframe reindexes to list(Schema.model_fields.keys()) so empty input produces a typed zero-row DataFrame with ALL columns in stable order, not a zero-column DataFrame."
  - "CYCLE-1 HIGH #8: output is date-partitioned under data/standard/scraped/{YYYYMM}/{race,entry,result}.parquet. No single-file overwrite pattern (_scraped.parquet absent)."
metrics:
  duration: ~6min (352s)
  completed: 2026-06-14
  tasks: 2
  tests_added: 30
  files_created: 2
  files_modified: 0
---

# Phase 4 Plan 05: netkeiba Race Normalizer Summary

パース済みdictデータをstrict-typed standard層Parquetに変換するnormalizerを実装した。Cycle-1 HIGH #7/#8（前回部分的に解決済み）に加え、**Cycle-2の3つのHIGH（#3 strict dtype、#4 same-month overwrite、#6 entry/result race_date不在）とCycle-3のHIGH #1（corner dtype Float64）**をすべて解決。30個のテストがCycle-2/Cycle-3回帰ガードを機械的に検証する。

## What Was Built

### 1. SCHEMA_DTYPE_MAP (Task 1, commit e623e93)

`src/scraper/normalizer.py` — RaceSchema/EntrySchema/ResultSchemaの全フィールドに対するpandas dtypeマップ。権威ソースは `pyarrow.parquet.read_schema` で読んだKaggle Parquetスキーマ。

| 型カテゴリ | フィールド例 | Kaggle Arrow型 | pandas dtype | 根拠 |
|-----------|-------------|---------------|--------------|------|
| string | race_id, race_date, horse_race_id, sex, finish_time, margin | string | `string` | 直接一致 |
| Int64 (nullable) | meeting_num, distance, bracket_num, finish_position | int64 nullable=True | `Int64` | Noneを保持; Cycle-2 #3 |
| Float64 (nullable) | weight_assigned, win_odds, popularity, horse_weight, weight_change, last_3f, prize_money | double nullable=True | `Float64` | Noneを保持 |
| **Float64 (Cycle-3 #1)** | **corner_1..corner_4** | **double nullable=True** | **Float64** | **Int64はArrow int64にserializeされ不等; Float64はArrow doubleと一致** |
| boolean (nullable) | 全20個のrace_flag_* | bool/null混在 | `boolean` | null-only Kaggle列はboolへのdeliberate promotion |

null-only Kaggle列（`race_flag_stallion_only`, `race_flag_colt_only`, `obstacle`, `surface_detail`, `track_condition_detail` 等計14個）はモジュールdocstringに明記し、`boolean` または `string` への意図的promotionとして文書化。04-06 `TestSchemaCompatibility`は物理型EQUALITYをKaggle non-null列にのみ要求し、null-only列は具体型へのpromotionのみを検証する。

### 2. _build_typed_dataframe — STRICT dtype path (Cycle-2 #3)

Cycle-1 planの `astype(target, errors="ignore")` を完全に廃止。新実装:

- `df.reindex(columns=list(schema.model_fields.keys()))` — empty inputでも全列のtyped zero-row DataFrameを保証 (Cycle-1 HIGH #7)
- 各列を `df[col].astype(target)` でcast — nullable dtype (Int64/Float64/boolean) は None + int 混在入力で成功
- genuine conversion failure（例: finish_position="abc"）は `TypeError` をraise。メッセージに列名とスキーマ名を含める（`errors="ignore"` の対極：loud failure）
- ソースコードに実行可能な `.astype(..., errors="ignore")` は存在しない（grep回帰ガード `test_no_errors_ignore_in_source` が検証）

### 3. write_partitioned_parquet — partition_map + merge-dedup + atomic (Cycle-2 #4 + #6)

出力レイアウト: `data/standard/scraped/{YYYYMM}/{race,entry,result}.parquet`

- **Cycle-2 #6 partition_map**: `table_name="race"` は `df["race_date"]` を直接読む。`table_name in ("entry","result")` は `partition_map[row["race_id"]]` でrace_dateをlookup。`partition_map=None` でentry/result呼ぶと `KeyError("partition_map required...")` でfail loud。
- **Cycle-2 #4 same-month merge-dedup**: 既存パーティションファイルがあれば読み込み、`pd.concat([existing, new])` → `drop_duplicates(subset=[primary_key], keep="last")` → atomic replace。sentinel行は同一月再実行で生き残り、重複PKは1つにcollapse。
- **Atomic write**: `to_parquet("{path}.tmp")` → `os.replace(tmp, path)`。中断時の部分書き込み防止。
- empty input: typed zero-rowプレースホルダファイル `{standard_dir}/scraped/{table_name}.parquet` を生成（出力が常に存在することを保証）。

### 4. validate_integrity — 警告専用（raiseしない）

- duplicate race_id / horse_race_id検出
- entry/result horse_race_id 1対1セット等価性
- entry/result race_id FK → race表のsubset検証
- 戻り値: `list[str]`（空=clean）。各違反はWARNING log。呼び出し元がraise判断。

### 5. normalize_to_parquet — orchestrator

1. parsed_racesからrace/entry/result行を蓄積
2. `_build_typed_dataframe` で3表をstrict typed化
3. obstacle filter: `race_df["obstacle"] == "障害"` かつnotnaの行をdrop、該当race_idのentry/resultも伝播削除（kaggle_converter line 89と同じパターン）
4. `validate_integrity` 実行（警告のみ）
5. **filtered race_dfからpartition_mapをbuild**（race_id→date; Cycle-2 #6 wiring）
6. `write_partitioned_parquet` を各表に呼出。entry/resultにはpartition_mapを渡す。
7. `audit_leakage` は呼ばない（Cycle-1 MEDIUM; popularity/win_oddsはentry表に意図的に所属）

### 6. テストスイート (Task 2, commit 102b6fb)

**30新規テスト / 5クラス**:

| クラス | テスト数 | 対象 |
|--------|----------|------|
| `TestTypedDataframe` | 7 | Cycle-1 HIGH #7 + Cycle-2 #3 + Cycle-3 #1 |
| `TestObstacleFiltering` | 2 | 障害フィルタ伝播 |
| `TestIntegrityValidation` | 5 | duplicate/FK/1-to-1検出 |
| `TestPartitionedOutput` | 8 | Cycle-1 HIGH #8 + Cycle-2 #4 + Cycle-2 #6 |
| `TestCycle2RegressionGuards` | 8 | dtype map完全性 + signature + Arrow physical type equality |

**主要回帰ガード**（Codex Cycle-2 HIGH指摘を機械的検証）:
- `test_finish_position_none_preserves_int64_nullable`: `[1, None]` → Int64（NOT float64）
- `test_genuine_coercion_failure_raises`: `["not_a_number"]` → TypeError
- `test_no_errors_ignore_in_source`: AST grepで `astype(..., errors="ignore")` を拒否
- `test_same_month_merge_dedup_preserves_sentinel`: sentinel + duplicate + new → 全生存・重複collapse
- `test_entry_result_partitioned_via_partition_map`: entry/resultがrace_date列なしで202201/に配置（KeyErrorなし）
- `test_entry_write_without_partition_map_raises`: partition_map=None → KeyError("partition_map required...")
- `test_kaggle_physical_type_equality_for_corners`: 当方のcorner_1..4 Arrow型 == Kaggle result.parquet Arrow型（両方 `double`）

`pytest tests/scraper/ -q` = **180 passed**（150 baseline + 30 new）。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] obstacle_mask pd.NA propagation**
- **Found during:** Task 2 `test_obstacle_race_dropped` 実行時（race_dfがemptyになり、flat raceまでフィルタされた）
- **Issue:** `race_df["obstacle"]` はnullable string dtype（`SCHEMA_DTYPE_MAP` で `"string"` 指定）。`pd.NA == "障害"` は `False` ではなく `pd.NA` を返す。`race_df[mask]` はNA行をフィルタインデックスから除外するため、**flat race（obstacle=None -> pd.NA）までフィルタされてrace_dfが空になった**。
- **Fix:** `obstacle_mask = (race_df["obstacle"] == "障害") & race_df["obstacle"].notna()` でNAを明示的にFalse化。
- **Files modified:** `src/scraper/normalizer.py` (normalize_to_parquet obstacle filter)
- **Commit:** 102b6fb

**2. [Rule 1 - Bug] write_partitioned_parquet groupby overwrote single-row groups**
- **Found during:** Task 2 `test_obstacle_entries_propagate` 実行時（flat raceの2頭エントリのうち1頭しか書き込まれなかった）
- **Issue:** 当初の `for idx, key in zip(df.index, partition_keys): groups.setdefault(key, df.loc[[idx]])` は、同一partition_keyを持つ複数行があると各 `setdefault` が **そのキーの値を単一行DataFrameで上書き** していた。結果、各月パーティションの**最後の1行のみ**が書き込まれていた。
- **Fix:** 一時キー列 `__partition_key__` を追加して `df.groupby("__partition_key__")` でグループ化し、各グループ全体をDataFrameとして保持する方式に書き直し。
- **Files modified:** `src/scraper/normalizer.py` (write_partitioned_parquet grouping block)
- **Commit:** 102b6fb

## Verification Results

plan-level `<verification>` ブロックは全て PASSED:

| Check | Result |
|-------|--------|
| `pytest tests/scraper/test_normalizer.py -x -q` passes | OK (30 passed) |
| `python -c "from src.scraper.normalizer import normalize_to_parquet, validate_integrity, SCHEMA_DTYPE_MAP, write_partitioned_parquet"` exits 0 | OK |
| `python -c "... assert 'partition_map' in inspect.signature(write_partitioned_parquet).parameters"` exits 0 (Cycle-2 #6) | OK |
| `grep -c 'errors="ignore"' src/scraper/normalizer.py` returns 0 *executable* matches | OK (5 docstring matches only; no `.astype(..., errors="ignore")` calls) |
| No `_scraped.parquet` single-file overwrite pattern in normalizer.py | OK |

### Task 1 acceptance criteria（全て PASSED）

- SCHEMA_DTYPE_MAP covers RaceSchema/EntrySchema/ResultSchema with every field — OK
- Cycle-2 #3: `SCHEMA_DTYPE_MAP[ResultSchema]["finish_position"] == "Int64"` — OK
- Cycle-2 #3: no executable `errors="ignore"` (grep regression guard) — OK
- Cycle-2 #3: `_build_typed_dataframe([{"finish_position": 1}, {"finish_position": None}], ResultSchema)` produces Int64 column (not float64) — OK
- Cycle-3 #1: `SCHEMA_DTYPE_MAP[ResultSchema]["corner_1..4"] == "Float64"` AND Arrow physical type == "double" — OK (verified against `data/standard/result.parquet`)
- Cycle-1 HIGH #7: `_build_typed_dataframe([], RaceSchema)` returns 0-row DF with ALL schema columns — OK
- Cycle-2 #6: `partition_map` + `primary_key` in signature; entry/result use map, no KeyError on df["race_date"] — OK
- Cycle-2 #6: entry/result write without partition_map raises KeyError mentioning "partition_map" — OK
- Cycle-2 #4: same-month merge-dedup preserves sentinel + collapses duplicates — OK
- Cycle-2 #4: duplicate PKs within single batch also collapse — OK
- Partitioned output under `standard_dir/scraped/{YYYYMM}/`; single-file overwrite absent — OK
- Atomic write via temp + os.replace — OK
- normalize_to_parquet filters obstacle + propagates to entry/result — OK (after Rule 1 fix)
- normalize_to_parquet builds partition_map from filtered race_df and passes to entry/result — OK
- normalize_to_parquet does NOT call audit_leakage — OK

### Task 2 acceptance criteria（全て PASSED）

- All 5 classes pass (4 plan-required + bonus regression guard class) — OK
- Test count >= 18 — OK (30 tests)
- Cycle-2 #3: `test_finish_position_none_preserves_int64_nullable` passes — OK
- Cycle-2 #3: `test_genuine_coercion_failure_raises` passes — OK
- Cycle-2 #3: `test_no_errors_ignore_in_source` passes — OK
- Cycle-2 #4: `test_same_month_merge_dedup_preserves_sentinel` passes — OK
- Cycle-2 #6: `test_entry_result_partitioned_via_partition_map` passes — OK
- Cycle-2 #6: `test_entry_write_without_partition_map_raises` passes — OK
- Empty-input test verifies ALL schema columns present — OK
- Partitioned-output test verifies no single-file overwrite — OK
- Atomic-write test verifies no .tmp files remain — OK
- FK / uniqueness / 1-to-1 violations all detected — OK
- popularity/win_odds do NOT cause failures — OK
- `pytest tests/scraper/test_normalizer.py -x -q` exits 0 — OK

## TDD Gate Compliance

本planは `tdd="true"` Task 2 を含む。実装順序: Task 1 (feat commit e623e93) → Task 2 (test commit 102b6fb, GREEN with 2 Rule 1 fixes during RED→GREEN iteration)。

Gate commits:
- `feat(04-05)`: e623e93 (Task 1 implementation)
- `test(04-05)`: 102b6fb (Task 2 tests + bug fixes found during GREEN)

Note: Task 1とTask 2の順序は実装→テスト（test-after、aka GREEN-first）。Planは両taskを `auto` + Task 2に `tdd="true"` をマークしていたが、Task 1が既にimplementationを含むため、RED→GREEN→REFACTORの完全サイクルではなく実装先行→テスト検証のパターンとなった。これは plan の task 分割（Task 1=impl, Task 2=test）と整合。両gate commit（feat + test）がgit logに存在し、CYCLE-2/CYCLE-3回帰ガードが30テストで機械的に検証されている。

## Authentication Gates

None.

## Threat Model Verification

| Threat | Disposition | Status |
|--------|-------------|--------|
| T-04-15 (Tampering — silent schema drift) | mitigate | Cycle-1 HIGH #7: reindex against `Schema.model_fields`. Cycle-2 HIGH #3: STRICT coercion raising TypeError on genuine failure (no `errors="ignore"`); nullable Int64/Float64/boolean for Optional fields so None does not silently become float64. |
| T-04-16 (Tampering — prior-month data erased) | mitigate | Cycle-1 HIGH #8: date-partitioned output keyed by race_date YYYYMM. Cycle-2 HIGH #4: same-month re-runs read-merge-dedup on primary key before atomic replace (sentinel survives; duplicates collapse). |
| T-04-16b (Tampering — entry/result mis-partitioned) | mitigate | Cycle-2 HIGH #6: `write_partitioned_parquet` accepts `partition_map` (race_id->race_date) for entry/result; omitting the map -> loud KeyError, not silent mis-partition. |
| T-04-17 (Denial of Service — partial write) | mitigate | Atomic write (temp + `os.replace`); zero-row typed placeholder ensures output always present. |
| T-04-18 (Tampering — broken Kaggle join key) | mitigate | `validate_integrity` checks 1-to-1 entry/result on horse_race_id; FK to race_id; parser-side 14-digit format guard (Plan 04). |
| T-04-19 (Info Disclosure — Parquet at rest) | accept | Local-only; no external transmission; standard format. |

## Known Stubs

None — 全関数が実際の実装を持つ。`normalize_to_parquet`、`_build_typed_dataframe`、`validate_integrity`、`write_partitioned_parquet` はすべて実データを処理し、5個のゴールデンparser出力フォーマットと互換。placeholderファイル（`tmp_standard_dir/scraped/{table}.parquet`）は空入力時のtyped zero-rowスキーマファイルであり、これはPlanが明示的に要求する挙動（"Empty input still produces a single placeholder file with the typed zero-row schema, so the output is always present"）でstubではない。

## Threat Flags

None — このplanは新規のtrust boundaryを導入しない。filesystem atomic write（`to_parquet` + `os.replace`）は計画の脅威モデル T-04-17 内で処理済み。

## Self-Check: PASSED

**Files verified:**
- [x] FOUND: src/scraper/normalizer.py
- [x] FOUND: tests/scraper/test_normalizer.py

**Commits verified:**
- [x] FOUND: e623e93 (Task 1: strict-typed normalizer implementation)
- [x] FOUND: 102b6fb (Task 2: 30 tests + 2 Rule 1 bug fixes)

**Test suite:** `pytest tests/scraper/ -q` = **180 passed** (150 baseline + 30 new, 0 failed).

**Acceptance grep checks:**
- [x] FOUND: no executable `.astype(..., errors="ignore")` in src/scraper/normalizer.py (5 matches are all docstring/comment text)
- [x] FOUND: no `_scraped.parquet` single-file overwrite pattern
- [x] FOUND: `partition_map` and `primary_key` in `write_partitioned_parquet` signature
- [x] FOUND: corner_1..corner_4 dtype Float64 with Arrow physical type "double" matching Kaggle result.parquet
- [x] FOUND: full scraper test suite green (180 passed)
