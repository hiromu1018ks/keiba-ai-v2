---
phase: 02-kaggle-data-pipeline
reviewed: 2026-06-11T13:43:59Z
depth: deep
files_reviewed: 10
files_reviewed_list:
  - pyproject.toml
  - src/pipeline/__init__.py
  - src/pipeline/column_mapping.py
  - src/pipeline/kaggle_converter.py
  - src/pipeline/validators.py
  - tests/pipeline/__init__.py
  - tests/pipeline/conftest.py
  - tests/pipeline/test_column_mapping.py
  - tests/pipeline/test_kaggle_converter.py
  - tests/pipeline/test_validators.py
findings:
  critical: 2
  warning: 5
  info: 4
  total: 11
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-06-11T13:43:59Z
**Depth:** deep
**Files Reviewed:** 10
**Status:** issues_found

## Summary

Deep review of the Kaggle data pipeline covering column mapping, CSV-to-Parquet conversion, and data quality validators. Cross-file analysis traced the full data flow from CSV read through column rename/split to Parquet write and validation. Schema conformance was verified against Phase 1 Pydantic models. Import graph is clean; all module boundaries resolve correctly. All 66 KAGGLE_COLUMN_MAP entries resolve to valid schema fields. Multi-mapping (20 CSV flags coalesced into 13 schema fields + 7 unmapped) is handled correctly by `_select_and_rename`.

Two critical bugs found in `validate_sample_rows` (check 7) that compound to make it a complete no-op against real data. A second critical issue found in the payoff table where non-Optional schema fields receive None values. The remaining validators (checks 1-6, 8) are functionally correct. The converter pipeline produces well-structured output but lacks error handling for malformed input.

Previous standard-review findings re-verified: CR-01 confirmed and expanded (dual compounding bug), WR-01 confirmed, WR-02 confirmed, WR-03 confirmed, IN-01 confirmed, IN-02 confirmed, IN-03 confirmed and linked to CR-01. Two new findings added: CR-02 (payoff schema violation) and WR-04 (unhandled date parse errors).

## Critical Issues

### CR-01: validate_sample_rows is a complete no-op against real data (dual compounding bugs)

**File:** `src/pipeline/validators.py:434-532`
**Issue:** Two independent bugs in `validate_sample_rows` combine to make the function never actually validate any data:

1. **Filename mismatch (line 434-439):** The `table_to_csv` dict maps tables to `race_result.csv` and `odds.csv`, but the actual Kaggle files are `19860105-20210731_race_result.csv` and `19860105-20210731_odds.csv`. The CSV lookup always hits the "Source CSV not found" branch at line 457-458, logging a debug message and skipping the table entirely.

2. **Column name mismatch (line 488):** Even if filenames were fixed, `common_cols` is computed as the intersection of Parquet column names (English: `race_id`, `distance`, etc.) and CSV column names (Japanese: `レースID`, `距離(m)`, etc.). These sets are disjoint, so `common_cols` is always empty, and the value comparison loop at lines 508-522 never executes.

Verified by tracing the actual execution: `common_cols` returns `[]` for all race/entry/result tables. The function always returns `True` for every table without performing any comparison. The test `TestValidateSampleRows` passes because it uses hand-crafted CSV/Parquet pairs with matching English column names, masking both bugs.

**Fix:**
```python
# 1. Fix filename mapping to accept actual Kaggle filenames, or use a glob
import glob
csv_candidates = list(source_dir.glob("*_race_result.csv"))
if csv_candidates:
    csv_path = csv_candidates[0]

# 2. Build a reverse mapping from English Parquet names to Japanese CSV names
from src.pipeline.column_mapping import KAGGLE_COLUMN_MAP

eng_to_jp_map = {}
for jp_name, (tbl, eng_name) in KAGGLE_COLUMN_MAP.items():
    if tbl == table_name:
        eng_to_jp_map[eng_name] = jp_name
eng_to_jp_map["race_id"] = "レースID"

# Then compare pq_row[eng_col] against source_row[eng_to_jp_map[eng_col]]
```

### CR-02: Payoff table violates PayoffSchema by storing None in required int fields

**File:** `src/pipeline/kaggle_converter.py:393-395`
**Issue:** `extract_odds_tables` creates payoff rows with `combo_1/2/3` set to `None` when any combo value is NaN:

```python
"combo_1": int(row[combo1_col]) if pd.notna(row[combo1_col]) else None,
"combo_2": int(row[combo2_col]) if pd.notna(row[combo2_col]) else None,
"combo_3": int(row[combo3_col]) if pd.notna(row[combo3_col]) else None,
```

`PayoffSchema` defines `combo_1`, `combo_2`, `combo_3` as non-Optional `int` fields (required=True, no default). While `combo_1` is guarded by the earlier `dropna(subset=[combo1_col])`, `combo_2` and `combo_3` can still be NaN even when `combo_1` is present. For example, in the sample test data, race `201502020202` has `trifecta1_combo_3 = NaN`, which would produce a payoff row with `combo_3 = None`. This produces Parquet rows that violate the schema contract. `validate_schema_conformance` will not catch this because nullable int columns become float64 in Parquet, and the validator's int-as-float exception silently passes them.

**Fix:** Either make `PayoffSchema.combo_2/3` Optional[int] to match actual data, or skip rows where any combo value is missing:
```python
# Option A: Skip incomplete rows (in extract_odds_tables)
subset = subset.dropna(subset=[combo1_col, combo2_col, combo3_col])

# Option B: Update schema (in schemas/payoff.py)
combo_2: Optional[int] = Field(default=None, ...)
combo_3: Optional[int] = Field(default=None, ...)
```

## Warnings

### WR-01: _DTYPE_COMPAT allows object dtype for int and bool categories

**File:** `src/pipeline/validators.py:31-37`
**Issue:** The `_DTYPE_COMPAT` dict includes `"object"` in both the `"int"` and `"bool"` compatible dtype sets. This means a column defined as `int` in the schema but stored as `object` dtype (mixed strings, NaN, integers) will pass validation without any warning. This could mask genuine data corruption where numeric columns contain unexpected string values. Verified: `validate_schema_conformance` at line 161 checks `actual_dtype not in compatible_dtypes`, and `"object"` is in the set, so any object-dtype int column passes.

**Fix:**
```python
"int": {"int64", "Int64", "int32", "Int32", "int16", "Int16", "int8", "Int8",
        "uint8", "uint16", "uint32", "uint64"},  # removed "object"
```

### WR-02: validate_sample_rows reads only first 1000 CSV rows

**File:** `src/pipeline/validators.py:472`
**Issue:** `pd.read_csv(csv_path, encoding="utf-8-sig", nrows=1000)` loads only the first 1000 rows of the source CSV. The real race_result.csv has hundreds of thousands of rows. If any sampled Parquet row has a race_id beyond the first 1000 CSV rows, the lookup fails and the row is silently skipped (treated as "filtered out" at line 504-505). This severely limits the validator's ability to catch data corruption, even after CR-01 is fixed.

**Fix:** Remove the `nrows` limit and read the full CSV, or use a targeted approach:
```python
source_df = pd.read_csv(csv_path, encoding="utf-8-sig")  # read full file
```

### WR-03: pyarrow.parquet imported inside loop body

**File:** `src/pipeline/validators.py:95`
**Issue:** `import pyarrow.parquet as pq` is inside the `for table_name` loop in `validate_row_counts`. While Python caches imports so this does not re-execute the module load each iteration, it is misleading and against convention. Other validator functions correctly import pandas at the top of the function body rather than inside loops.

**Fix:** Move the import to the top of the function, outside the loop:
```python
def validate_row_counts(source_counts, parquet_dir):
    import pyarrow.parquet as pq  # moved outside loop
    results = {}
    for table_name, expected_count in source_counts.items():
        # ... loop body without import
```

### WR-04: convert() uses pd.to_datetime without errors='coerce'

**File:** `src/pipeline/kaggle_converter.py:83`
**Issue:** `df["レース日付"] = pd.to_datetime(df["レース日付"])` uses the default `errors="raise"`. A single malformed date string in the 472MB CSV (e.g., a corrupted row, encoding artifact, or unexpected format) will crash the entire pipeline with an unhandled `ValueError`. There is no try/except anywhere in `convert()` or its callees. For a production pipeline processing large files, this is fragile.

**Fix:** Use `errors="coerce"` and handle NaT values:
```python
df["レース日付"] = pd.to_datetime(df["レース日付"], errors="coerce")
nat_count = df["レース日付"].isna().sum()
if nat_count > 0:
    logger.warning(f"Dropped {nat_count} rows with unparseable dates")
    df = df[df["レース日付"].notna()].copy()
```

### WR-05: run_all_validations never populates null_rates or distributions checks

**File:** `src/pipeline/validators.py:675-678`
**Issue:** Checks 4 (`validate_null_rates`) and 5 (`validate_distributions`) are initialized as empty dicts and never populated because `run_all_validations` does not accept a `source_stats` parameter. The orchestrator always reports `null_rates: True` and `distributions: True` regardless of actual data quality. These two checks are effectively dead code in the orchestrator path, giving a false sense of validation coverage. The individual functions work correctly when called directly with source_stats, but the main entry point never exercises them.

**Fix:** Add a `source_stats` parameter and pass it through:
```python
def run_all_validations(
    raw_dir: Path,
    parquet_dir: Path,
    source_counts: dict[str, int] | None = None,
    source_stats: dict[str, Any] | None = None,  # ADD THIS
) -> dict[str, Any]:
    # ...
    if source_stats is not None:
        null_rates_result = validate_null_rates(source_stats, parquet_dir)
        distributions_result = validate_distributions(source_stats, parquet_dir)
```

## Info

### IN-01: Non-existent dtype names in _DTYPE_COMPAT

**File:** `src/pipeline/validators.py:32`
**Issue:** The `"str"` compat set contains `"str"` and `"unicode"` which are not actual pandas dtype names. Verified: `str(df[col].dtype)` never returns `"str"` or `"unicode"` -- it returns `"object"` or `"string"`. These entries are dead code that can never match.

**Fix:** Remove the non-existent names: `"str": {"object", "string"}`.

### IN-02: convert_flags_to_bool mutates DataFrame in-place and returns it

**File:** `src/pipeline/kaggle_converter.py:277-296`
**Issue:** The function modifies `df[col]` in-place via direct column assignment and also returns `df`. The caller `split_race_entry_result` uses the return value (`race_df = convert_flags_to_bool(race_df)`) which works but is confusing since `race_df` was already mutated. This dual pattern (mutate + return) can mislead future callers into thinking the function is pure.

**Fix:** Document the in-place mutation in the docstring, or operate on a copy for a pure function.

### IN-03: CSV filenames hardcoded in convert()

**File:** `src/pipeline/kaggle_converter.py:72-73`
**Issue:** The filenames `19860105-20210731_race_result.csv` and `19860105-20210731_odds.csv` are hardcoded string literals. This is also linked to CR-01 bug 1: the validator uses different hardcoded names (`race_result.csv`, `odds.csv`), creating a naming inconsistency between the converter and the validator.

**Fix:** Make filenames configurable via parameters or use a glob pattern. Also coordinate with `validate_sample_rows` to use consistent naming.

### IN-04: Missing end-to-end test combining convert() and validators

**File:** `tests/pipeline/` (directory-level observation)
**Issue:** Converter tests verify output shape (row counts, column names, Parquet existence) and validator tests verify against hand-crafted Parquet fixtures. But no test runs the full pipeline: convert sample CSV data to Parquet, then run all validators on the converter's output. This is why CR-01 (validators cannot read converter output) went undetected by the test suite. The converter and validators are tested in isolation with incompatible assumptions about data format.

**Fix:** Add an integration test that runs `convert()` on sample data, then runs `run_all_validations()` on the output:
```python
def test_convert_then_validate(sample_race_result_df, sample_odds_df, tmp_standard_dir):
    """Convert sample data then run validators on the output."""
    raw_dir = tmp_standard_dir.parent / "raw" / "kaggle"
    raw_dir.mkdir(parents=True)
    sample_race_result_df.to_csv(raw_dir / "19860105-20210731_race_result.csv", ...)
    sample_odds_df.to_csv(raw_dir / "19860105-20210731_odds.csv", ...)
    result = convert(raw_dir=raw_dir, standard_dir=tmp_standard_dir)
    validation = run_all_validations(raw_dir=raw_dir, parquet_dir=tmp_standard_dir)
    assert validation["overall_pass"] is True
```

---

_Reviewed: 2026-06-11T13:43:59Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
