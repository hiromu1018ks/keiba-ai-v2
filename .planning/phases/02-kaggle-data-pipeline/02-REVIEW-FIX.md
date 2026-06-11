---
phase: 02-kaggle-data-pipeline
reviewed: 2026-06-11T00:00:00Z
depth: deep
findings_in_scope: 7
fixed: 7
skipped: 0
iteration: 1
status: all_fixed
---

# Phase 2: Code Review Fix Report

**Review Date:** 2026-06-11
**Fix Date:** 2026-06-11
**Depth:** deep
**Status:** all_fixed

## Summary

All 7 in-scope findings (2 Critical, 5 Warning) were fixed and verified. 140 tests pass (0 failures).

## Fixes Applied

### CR-01: validate_sample_rows was a complete no-op ✅ Fixed

**Files:** `src/pipeline/validators.py`, `tests/pipeline/test_validators.py`

Two compounding bugs fixed:
1. **CSV filename mismatch**: Used glob pattern (`*race_result*.csv`, `*_odds.csv`) instead of hardcoded names
2. **Column name mismatch**: Built reverse mapping from English→Japanese using `KAGGLE_COLUMN_MAP`/`ODDS_COLUMN_MAP`

Additional refinements during verification:
- Changed `_build_eng_to_jp_map` to return `dict[str, list[str]]` for multi-mapped columns (e.g., `race_flag_allowance` coalesced from 3 CSV columns)
- Used `horse_race_id` as composite key for entry/result tables (not `race_id`) since multiple rows exist per race
- Added numeric comparison fallback (`float()` equality) to handle zero-padded values like `course_code "05"` vs `5`
- Added type-aware boolean comparison for flag columns

### CR-02: extract_odds_tables could produce None in combo_2/combo_3 ✅ Fixed

**File:** `src/pipeline/kaggle_converter.py`

Extended `dropna` guard to include `combo_2` and `combo_3` alongside `combo_1`.

### WR-01: _DTYPE_COMPAT allowed object dtype for int schema validation ✅ Fixed

**File:** `src/pipeline/validators.py`

Removed `"object"` from the `"int"` compat set. Kept `"object"` in `"bool"` compat set since pandas nullable booleans (True/None) are legitimately stored as `object` dtype.

Added special handling: Optional fields where all values are None are accepted with `object` dtype (pandas can't infer type from empty data).

### WR-02: validate_sample_rows read only first 1000 CSV rows ✅ Fixed

**File:** `src/pipeline/validators.py`

Removed `nrows=1000` limit. Full CSV is now read for comprehensive comparison.

### WR-03: pyarrow.parquet imported inside loop ✅ Fixed

**File:** `src/pipeline/validators.py`

Moved `import pyarrow.parquet as pq` outside the loop in `validate_row_counts`.

### WR-04: Unhandled date parse errors ✅ Fixed

**File:** `src/pipeline/kaggle_converter.py`

Added `errors="coerce"` to `pd.to_datetime` calls with NaT warning logging for failed parses.

### WR-05: Dead validation checks 4/5 ✅ Fixed

**File:** `src/pipeline/validators.py`

Added `source_stats` parameter to `run_all_validations` to properly pass source counts to `validate_null_rates` and `validate_distributions`.

## Commits

| Hash | Finding | Description |
|------|---------|-------------|
| `5c0d10f` | CR-01 + WR-02 | Fix validate_sample_rows no-op via glob filenames, reverse column mapping, remove nrows limit |
| `21225e8` | CR-02 | Extend dropna guard to combo_2/combo_3 in extract_odds_tables |
| `f52b131` | WR-01 | Remove object dtype from int compat set in _DTYPE_COMPAT |
| `16c29f9` | WR-03 | Move pyarrow.parquet import outside loop |
| `6890f89` | WR-04 | Add errors=coerce to pd.to_datetime with NaT warning |
| `73e0f85` | WR-05 | Add source_stats parameter to run_all_validations |
| `94dbb25` | Refinement | Multi-map columns, composite keys, nullable dtype handling, low_memory fix |

## Verification

- **Tests:** 140 passed, 0 failed, 0 warnings
- **Schema conformance:** All 5 tables pass (race, entry, result, odds_trifecta, payoff)
- **Sample rows:** All 5 tables pass value comparison against source CSVs

---

_Reviewer: Claude (gsd-code-reviewer)_
_Fixer: Claude (gsd-code-fixer) + orchestrator refinements_
_Depth: deep_
