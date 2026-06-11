---
phase: 02-kaggle-data-pipeline
plan: 02
subsystem: data-pipeline
tags: [converter, parquet, csv-to-standard, tdd]
dependency_graph:
  requires: [src/pipeline/column_mapping.py (02-01), src/schemas/*.py (Phase 1)]
  provides: [src/pipeline/kaggle_converter.py, tests/pipeline/conftest.py, tests/pipeline/test_kaggle_converter.py]
  affects: [plans 02-03 (feature engineering)]
tech_stack:
  added: []
  patterns: [multi-column coalescing, CSV-to-Parquet pipeline, TDD red-green]
key_files:
  created:
    - src/pipeline/kaggle_converter.py
    - tests/pipeline/conftest.py
    - tests/pipeline/test_kaggle_converter.py
  modified: []
decisions:
  - "Multi-mapped flag columns coalesced via OR logic: 20 CSV flag columns become 13 unique schema fields"
  - "process_finish_position() renames Japanese columns to English directly, simplifying the split pipeline"
  - "Entry and result tables receive race_id via explicit foreign key addition (not from KAGGLE_COLUMN_MAP)"
  - "Payoff table odds divided by 10 to convert from 0.1-unit Kaggle format to decimal"
metrics:
  duration: 11m
  completed: "2026-06-11"
  tasks: 2
  tests_added: 21
  files_created: 3
  files_modified: 0
---

# Phase 2 Plan 2: CSV-to-Parquet Converter Summary

Kaggle CSV-to-Parquet converter with BOM handling, dtype specification, obstacle exclusion, flag coalescing, finish position note processing, odds filtering, and payoff unpivoting -- all validated by 21 unit tests.

## What Was Built

- **convert()**: Main entry point orchestrating the full pipeline: read CSV -> filter 2015+ flat races -> split into 3 tables -> extract odds tables -> write 5 Parquet files -> audit for data leakage
- **read_race_result_csv()**: Reads 472MB race_result.csv with encoding="utf-8-sig" (BOM handling), dtype=DTYPE_SPEC (23 mixed-type columns as str), low_memory=False (prevents DtypeWarning)
- **read_odds_csv()**: Reads odds.csv with BOM handling
- **_select_and_rename()**: Internal helper that handles multi-to-single column mappings by coalescing (OR logic for flag columns)
- **split_race_entry_result()**: Splits filtered DataFrame into race (deduplicated by race_id), entry (all rows), and result (all rows) tables with English column names
- **convert_flags_to_bool()**: Converts 13 unique race_flag_* columns from sparse text to Optional[bool] (True for non-empty, pd.NA for empty/NaN)
- **process_finish_position()**: Handles finish position notes: converts to nullable Int64, records finish_note, nulls position for 中/取/失/除/再, preserves position for 降
- **extract_odds_tables()**: Filters odds to flat race_ids only (Pitfall 5), generates odds_trifecta (1 row/race) and payoff (up to 3 rows/race from trifecta1/2/3, odds/10 conversion)
- **Test fixtures**: sample_race_result_df (10 rows, 66 cols with mixed flags/finish notes), sample_odds_df (5 rows, 104 cols with trifecta data), tmp_standard_dir

## Key Decisions

1. **Multi-mapped flag columns coalesced**: The 20 CSV flag columns (レース記号/*) map to 13 unique schema fields via coalescing. When multiple CSV columns map to the same field (e.g., both レース記号/[抽] and レース記号/(抽) map to race_flag_condition_race), the first non-empty value is used. This implements OR logic correctly -- if any source flag is set, the target is set.

2. **process_finish_position renames to English directly**: Instead of operating on Japanese column names and then renaming separately, process_finish_position() renames 着順 to finish_position and 着順注記 to finish_note directly. This simplifies the split pipeline and makes the function testable in isolation.

3. **Foreign key race_id added explicitly**: KAGGLE_COLUMN_MAP maps レースID to the "race" table only. Entry and result tables need race_id as a foreign key, so it's added explicitly to their rename maps before the split.

4. **Payoff odds/10 conversion**: Kaggle stores trifecta odds in 0.1-unit format (e.g., 990 = 99.0x). The payoff table converts these to decimal by dividing by 10.

## TDD Gate Compliance

- **RED gate**: `c1dd22f` - test(02-02): add failing tests for kaggle converter module
- **GREEN gate**: `eaddb14` - feat(02-02): implement kaggle converter module with CSV-to-Parquet pipeline
- **REFACTOR**: Minor -- removed redundant local import during GREEN phase

## Test Results

All 21 new tests pass:
- TestDateFilter (2 tests): 2014 exclusion, 2015/2016 inclusion
- TestObstacleExclusion (2 tests): obstacle filtered, count correct (7 rows)
- TestRaceEntryResultSplit (4 tests): deduplication, all rows, correct columns
- TestFlagConversion (4 tests): non-empty->True, empty->None, NaN->None, all 13 flags
- TestFinishPosition (4 tests): normal, withdrawal (中), demoted (降), other notes
- TestOddsConversion (3 tests): obstacle filter, payoff unpivot, NaN exclusion
- TestParquetOutput (2 tests): 5 files exist, audit_leakage called

Full suite: 115 passed (21 new + 94 existing), 0 failed, 0 regressions.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Multi-column rename collision**
- **Found during:** Task 2 GREEN phase
- **Issue:** pd.DataFrame.rename() silently creates a DataFrame when multiple columns map to the same name, causing truth-value ambiguity in subsequent operations
- **Fix:** Created _select_and_rename() helper with coalesce logic for multi-mapped columns
- **Files modified:** src/pipeline/kaggle_converter.py
- **Commit:** eaddb14

**2. [Rule 2 - Critical] Entry/result tables missing race_id foreign key**
- **Found during:** Task 2 GREEN phase
- **Issue:** KAGGLE_COLUMN_MAP maps レースID only to the "race" table, but entry and result schemas require race_id as a foreign key
- **Fix:** Explicitly added レースID -> race_id to entry and result rename maps
- **Files modified:** src/pipeline/kaggle_converter.py
- **Commit:** eaddb14

**3. [Rule 1 - Bug] Flag count assertion mismatch**
- **Found during:** Task 2 GREEN phase
- **Issue:** Test expected 20 flag columns but multi-mapping coalesces them to 13 unique schema fields
- **Fix:** Updated test assertion to expect 13 unique flag fields
- **Files modified:** tests/pipeline/test_kaggle_converter.py
- **Commit:** eaddb14

## Verification

- `pytest tests/pipeline/test_kaggle_converter.py -x -v --tb=short` -- 21 passed
- `pytest tests/ -x -v` -- 115 passed, 0 failed, 0 regressions
- `ruff check src/pipeline/kaggle_converter.py tests/pipeline/conftest.py tests/pipeline/test_kaggle_converter.py` -- All checks passed

## Threat Flags

No new threat surface introduced beyond what the plan's threat model covers. All mitigations from T-02-01 through T-02-05 are implemented (utf-8-sig encoding, DTYPE_SPEC, pathlib.Path for output).

## Self-Check: PASSED

- All 3 created files verified on disk
- Both TDD commits (RED c1dd22f, GREEN eaddb14) found in git log
- SUMMARY.md exists at expected path
