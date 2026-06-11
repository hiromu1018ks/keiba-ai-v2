---
phase: 02-kaggle-data-pipeline
plan: 01
subsystem: data-pipeline
tags: [column-mapping, pyarrow, tdd]
dependency_graph:
  requires: [src/schemas/*.py (Phase 1)]
  provides: [src/pipeline/column_mapping.py, src/pipeline/__init__.py]
  affects: [plans 02-02, 02-03]
tech_stack:
  added: [pyarrow>=14.0]
  patterns: [dict-based column mapping, dtype specification, TDD red-green]
key_files:
  created:
    - src/pipeline/__init__.py
    - src/pipeline/column_mapping.py
    - tests/pipeline/__init__.py
    - tests/pipeline/test_column_mapping.py
  modified:
    - pyproject.toml
decisions:
  - "Flag columns use actual CSV header names with parentheses/brackets (not shortened test names)"
  - "Multiple CSV flags can map to the same schema field (e.g., (混), (市), 九州産馬 all -> race_flag_allowance)"
metrics:
  duration: 4m
  completed: "2026-06-11"
  tasks: 1
  tests_added: 17
  files_created: 4
  files_modified: 1
---

# Phase 2 Plan 1: Column Mapping + pyarrow Summary

Authoritative column mapping from Kaggle Japanese CSV headers to Phase 1 English schema fields, with pyarrow installed and all mappings validated via unit tests.

## What Was Built

- **KAGGLE_COLUMN_MAP**: 66 entries mapping all race_result.csv Japanese column names to (table, field) tuples, verified against Phase 1 Pydantic schemas
- **ODDS_COLUMN_MAP**: 15 entries mapping odds.csv trifecta columns to OddsTrifectaSchema fields
- **FLAG_COLUMNS**: 20 actual CSV flag column names (with parentheses/brackets) for dtype specification
- **DTYPE_SPEC**: 23 dtype=str entries (20 flags + 3 mixed-type optional columns) to prevent DtypeWarning
- **TABLE_TO_SCHEMA**: 5-entry mapping from table names to Pydantic schema classes
- **get_columns_for_table()**: Helper function returning Japanese-to-English column mapping for a specific table
- **Pipeline package**: `src/pipeline/__init__.py` with re-exports of all key symbols

## Key Decisions

1. **Actual CSV header names for flags**: The 20 flag columns use the real CSV header text (e.g., `"レース記号/(ハンデ)"`) instead of the shortened names in `test_classification.py` (e.g., `"レース記号/ハンデ"`). This matches what pandas sees when reading the CSV.

2. **Multi-to-single flag mapping**: Multiple CSV flag columns map to the same schema field where semantically equivalent:
   - `(混)`, `(市)`, `九州産馬` all map to `race_flag_allowance`
   - `[抽]`, `(抽)`, `(指)`, `[指]` all map to `race_flag_condition_race`
   - `(別定)`, `(特指)` both map to `race_flag_special_weight`
   - `関東配布馬`, `関西配布馬` both map to `race_flag_open`
   This means some RaceSchema flag fields will be set from multiple CSV columns.

## TDD Gate Compliance

- **RED gate**: `c4f1baf` - test(02-01): add failing tests for column mapping module
- **GREEN gate**: `bad361b` - feat(02-01): implement column mapping module with all mapping dicts
- **REFACTOR**: Not needed - code is clean, ruff passes with no issues

## Test Results

All 17 new tests pass:
- TestKaggleColumnMapping (3 tests): 66 entries, all resolve to schema fields, all match expected set
- TestOddsColumnMapping (3 tests): 15 entries, all match expected set, all resolve to OddsTrifectaSchema
- TestDtypeSpec (5 tests): 20 flag columns with correct prefix, 23 dtype entries, covers all flags + 3 mixed-type
- TestHelperFunctions (6 tests): 5 tables mapped correctly, get_columns_for_table works for race/entry/result

Full suite: 94 passed (17 new + 77 existing), 0 failed, 0 regressions.

## Verification

- `pytest tests/pipeline/ -x -v --tb=short` -- 17 passed
- `ruff check src/pipeline/ tests/pipeline/` -- All checks passed
- `pyarrow>=14.0` installed (v24.0.0) and listed in pyproject.toml

## Deviations from Plan

None - plan executed exactly as written.

## Threat Flags

No new threat surface introduced. Column mapping is a static dict module with no network or file I/O.

## Self-Check: PASSED

- All 5 created/modified files verified on disk
- Both TDD commits (RED c4f1baf, GREEN bad361b) found in git log
- SUMMARY.md exists at expected path
