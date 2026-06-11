---
phase: 02-kaggle-data-pipeline
reviewed: 2026-06-11T00:00:00Z
depth: standard
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
  critical: 1
  warning: 3
  info: 3
  total: 7
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-06-11T00:00:00Z
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

Reviewed the Kaggle CSV-to-Parquet data pipeline (column mapping, converter, validators) and associated tests. The core conversion logic (split, rename, coalesce, flag conversion) is well-structured and correct. However, one critical defect was found in `validate_sample_rows` where the column name comparison is fundamentally broken for production data -- Parquet columns are English but source CSV columns are Japanese, so the comparison set is always empty and the check vacuously passes. The tests for this function only pass because they use English CSV column names in test fixtures, masking the defect.

Three warnings concern: the `int` dtype compat set allowing `object` dtype to pass for integer schema fields, the `nrows=1000` limit in sample validation making it unable to verify most Parquet rows, and `pyarrow.parquet` being re-imported inside a loop on each iteration.

## Critical Issues

### CR-01: validate_sample_rows never actually compares Parquet values against CSV

**File:** `src/pipeline/validators.py:488-523`
**Issue:** After the converter renames all columns from Japanese to English, the Parquet files have English column names (`race_id`, `course_code`, etc.) while the source CSV files retain Japanese column names (`レースID`, `競馬場コード`, etc.). The function computes `common_cols` as the intersection of Parquet columns (English) and CSV columns (Japanese) at line 488. This intersection is always empty because no column names are shared between the two sets.

As a result, the inner comparison loop (lines 508-523) that checks individual cell values never executes. `all_match` remains `True` by default, and the function returns `True` for every table regardless of actual data correctness.

The unit tests pass because they create test CSV files with English column headers (`race_id`, `course_code`, `distance`) that match the English Parquet column names, masking the defect.

**Fix:**
```python
# In validate_sample_rows, after reading the source CSV, build a reverse
# mapping from English Parquet column names back to Japanese CSV column names
# using KAGGLE_COLUMN_MAP, then use that mapping for the comparison.

from src.pipeline.column_mapping import KAGGLE_COLUMN_MAP, ODDS_COLUMN_MAP

# Build reverse map: english_name -> japanese_name
reverse_map: dict[str, str] = {}
if table_name in ("race", "entry", "result"):
    for jp_name, (_, eng_name) in KAGGLE_COLUMN_MAP.items():
        reverse_map[eng_name] = jp_name
    # Add foreign keys added by converter
    reverse_map["race_id"] = "レースID"
elif table_name in ("odds_trifecta", "payoff"):
    for jp_name, eng_name in ODDS_COLUMN_MAP.items():
        reverse_map[eng_name] = jp_name
    reverse_map["race_id"] = "レースID"

# Map Parquet column names to CSV column names for comparison
common_cols = {
    eng: jp for eng, jp in reverse_map.items()
    if eng in sample.columns and jp in source_df.columns
}
```

## Warnings

### WR-01: _DTYPE_COMPAT allows object dtype to pass int schema validation

**File:** `src/pipeline/validators.py:31-37`
**Issue:** The `_DTYPE_COMPAT` dictionary maps the `"int"` expected category to a set that includes `"object"`. This means if an integer schema field has `dtype=object` (which happens when string data is stored in the column), the schema conformance check passes without flagging it. Integer columns in pandas with NaN values become `float64`, not `object`, so the `object` entry in the `int` compat set does not serve a legitimate NaN-handling purpose. It can only mask genuine type corruption where string data replaces integer data.

**Fix:**
```python
# Remove 'object' from the 'int' compat set
_DTYPE_COMPAT: dict[str, set[str]] = {
    "str": {"object", "string"},
    "int": {"int64", "Int64", "int32", "Int32", "int16", "Int16",
            "int8", "Int8", "uint8", "uint16", "uint32", "uint64"},
    "float": {"float64", "float32", "Float64", "Float32"},
    "bool": {"bool", "boolean", "object"},
}
```

### WR-02: validate_sample_rows reads only first 1000 CSV rows

**File:** `src/pipeline/validators.py:472`
**Issue:** `pd.read_csv(csv_path, encoding="utf-8-sig", nrows=1000)` loads only the first 1000 rows of the source CSV. The real Kaggle CSV has hundreds of thousands of rows. When sample Parquet rows have `race_id` values not present in the first 1000 CSV rows, the match falls through to the `continue` branch at line 505, silently skipping the comparison. Combined with CR-01, the function currently never compares any rows at all; but even after CR-01 is fixed, this `nrows=1000` limit would still prevent verification of most Parquet rows.

**Fix:** Remove `nrows=1000` and read the full CSV, or at minimum read enough rows to cover all sampled race_ids. Alternatively, use a more targeted approach that reads only the rows matching the sampled keys.

### WR-03: pyarrow.parquet imported inside a loop

**File:** `src/pipeline/validators.py:96`
**Issue:** `import pyarrow.parquet as pq` is inside the `for table_name, expected_count in source_counts.items()` loop in `validate_row_counts`. This causes the module to be re-imported (or at minimum the import statement re-executed) on every iteration. While Python caches module imports so this is not a performance disaster, it is a code quality issue that should be fixed by moving the import to the top of the function or module.

**Fix:**
```python
def validate_row_counts(
    source_counts: dict[str, int],
    parquet_dir: Path,
) -> dict[str, bool]:
    import pyarrow.parquet as pq  # Move import here, outside the loop
    results: dict[str, bool] = {}
    parquet_dir = Path(parquet_dir)

    for table_name, expected_count in source_counts.items():
        parquet_path = parquet_dir / f"{table_name}.parquet"
        if not parquet_path.exists():
            logger.warning(f"Missing Parquet file: {parquet_path}")
            results[table_name] = False
            continue
        parquet_file = pq.ParquetFile(parquet_path)
        ...
```

## Info

### IN-01: _DTYPE_COMPAT contains non-existent pandas dtype names

**File:** `src/pipeline/validators.py:32`
**Issue:** The `"str"` compat set contains `"str"` and `"unicode"` which are not actual pandas dtype names. The real dtypes are `"object"` (default for strings) and `"string"` (for the StringDtype). These dead entries are harmless but misleading.

**Fix:** Remove `"str"` and `"unicode"` from the `"str"` compat set: `{"object", "string"}`.

### IN-02: convert_flags_to_bool mutates DataFrame in-place and also returns it

**File:** `src/pipeline/kaggle_converter.py:277-296`
**Issue:** `convert_flags_to_bool` modifies the input DataFrame in-place via `df[col] = ...` and also returns it. The caller (`split_race_entry_result`) uses the return value (`race_df = convert_flags_to_bool(race_df)`), so the mutation is not lost, but the dual pattern (mutate + return) is a code smell that can cause confusion about whether the function is pure or mutating.

**Fix:** Either document the in-place mutation clearly in the docstring, or operate on a copy internally for a pure function.

### IN-03: CSV filenames hardcoded in convert()

**File:** `src/pipeline/kaggle_converter.py:72-73`
**Issue:** The filenames `19860105-20210731_race_result.csv` and `19860105-20210731_odds.csv` are hardcoded. If the filenames change for new data drops, the converter will raise `FileNotFoundError` with no guidance. Consider making these configurable or using a glob pattern.

**Fix:** Accept filenames as parameters with these as defaults, or document the naming convention clearly.

---

_Reviewed: 2026-06-11T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
