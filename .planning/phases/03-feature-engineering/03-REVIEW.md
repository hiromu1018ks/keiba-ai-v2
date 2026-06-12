---
phase: 03-feature-engineering
reviewed: 2026-06-12T18:15:00Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - src/pipeline/feature_generator.py
  - tests/pipeline/conftest.py
  - tests/pipeline/test_feature_generator.py
findings:
  critical: 1
  warning: 3
  info: 3
  total: 7
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-06-12T18:15:00Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Reviewed the feature generator pipeline (`feature_generator.py`) and its supporting test fixtures (`conftest.py`, `test_feature_generator.py`). The codebase is well-structured with thorough test coverage (95 tests, all passing). However, one critical data leakage bug was found in the `compute_finish_time_zscore` function where `.shift(1)` operates globally across groupby boundaries, causing normalization parameters from one (course, distance, surface) group to leak into the first valid row of the next group. All existing tests use a single group and therefore do not catch this bug.

## Critical Issues

### CR-01: Cross-group data leakage in finish_time_zscore via global shift(1)

**File:** `src/pipeline/feature_generator.py:304-309`
**Issue:** In `compute_finish_time_zscore`, the code computes an expanding mean/std per (course_name, distance, surface) group, then applies `.shift(1)` to exclude the current race. However, `.shift(1)` operates on the flat Series returned by the groupby-expanding operation, shifting across group boundaries. This causes the last row's expanding mean from group A (e.g., Nakayama 1600 turf) to be assigned as the normalization mean for the first valid row of group B (e.g., Tokyo 2000 turf).

Concretely, with `race_means` sorted by (course_name, distance, surface, race_date):
```python
grp = race_means.groupby(["course_name", "distance", "surface"])
race_means["norm_mean"] = (
    grp["race_ft_mean"].expanding(min_periods=5).mean().shift(1).values
)
```

The `.shift(1)` on the grouped Series shifts the entire concatenated result by one position globally. The first row of each group (after the first group) receives the shifted value from the last row of the previous group, which is a completely different (course, distance, surface) combination.

Verified with a minimal reproduction: two groups with 6 rows each. Row 6 (first Tokyo 2000 race) received `norm_mean=95.67` from the Nakayama 1600 group, when it should be NaN (no prior races for its own group).

All 95 existing tests pass because every z-score test uses `_make_many_race_fixture` or `_make_two_race_fixture` which creates all races in a single group (Tokyo 2000 turf), so the cross-group boundary is never exercised.

**Fix:**
Replace the global `.shift(1)` with a per-group shift using `groupby.transform`:
```python
grp = race_means.groupby(["course_name", "distance", "surface"])

# CORRECT: shift within each group using transform
race_means["norm_mean"] = grp["race_ft_mean"].transform(
    lambda s: s.expanding(min_periods=5).mean().shift(1)
)
race_means["norm_std"] = grp["race_ft_mean"].transform(
    lambda s: s.expanding(min_periods=5).std().shift(1)
)
```

Alternatively, use `groupby().shift(1)` on the expanding result:
```python
exp_mean = grp["race_ft_mean"].expanding(min_periods=5).mean()
exp_std = grp["race_ft_mean"].expanding(min_periods=5).std()
race_means["norm_mean"] = grp[exp_mean.name].shift(1) if exp_mean.name else exp_mean.groupby(level=[0,1,2]).shift(1).values
```

A new test should be added that creates races across two different (course, distance, surface) groups and verifies that the first valid z-score row in each group uses only its own group's normalization history.

## Warnings

### WR-01: COMPONENT_MAP is entirely redundant with MARGIN_MAP

**File:** `src/pipeline/feature_generator.py:143-147`
**Issue:** `COMPONENT_MAP` contains three entries (`"ハナ": 0.02`, `"クビ": 0.10`, `"1/2": 0.50`) that are all already present in `MARGIN_MAP` with identical values. The compound parsing logic at line 184 checks `MARGIN_MAP` first via `elif part in COMPONENT_MAP`, so `COMPONENT_MAP` is never reached. This is dead code that adds confusion -- a reader might expect `COMPONENT_MAP` to have unique additive-only components.

**Fix:** Either remove `COMPONENT_MAP` entirely (since all its entries are already in `MARGIN_MAP`), or add a doc comment explaining it exists for future additive-only margin parts not in the main map.

### WR-02: Z-score temporal invariance test excluded from real-data check without justification for the actual bug

**File:** `tests/pipeline/test_feature_generator.py:1847-1853`
**Issue:** The `test_temporal_invariance_real_data` test explicitly excludes `finish_time_zscore` and its lag derivatives from temporal invariance verification, commenting that "z-score normalization uses expanding-window stats that depend on the full group history." While truncating the dataset can change which rows have valid z-scores (due to `min_periods=5`), for rows where z-scores ARE valid in both the truncated and full datasets, they should be identical (the expanding window is inherently backward-looking). The test's blanket exclusion masks the cross-group shift bug (CR-01) and should be tightened to compare only rows where z-scores are valid in both datasets.

**Fix:** Refine the temporal invariance test to compare z-score values only for rows where both the full and truncated datasets produce valid (non-NaN) z-scores, rather than excluding z-score columns entirely.

### WR-03: compute_lag_features assumes contiguous RangeIndex for merge-back

**File:** `src/pipeline/feature_generator.py:370-426`
**Issue:** The function saves the original DataFrame index as `_orig_idx` before filtering to valid-start rows, then uses `df_indexed.loc[lag_only["_orig_idx"].values, col]` to write lag values back. This pattern assumes `df` has a contiguous RangeIndex (0..N-1). If `df` had a non-contiguous index (e.g., after filtering), `_orig_idx` values would reference positions that no longer exist in `df_indexed = df.reset_index(drop=True)`, causing a `KeyError`. In the `generate()` pipeline this is safe because `load_and_merge()` produces a clean RangeIndex and subsequent steps preserve it. However, as a standalone function, it is not robust.

**Fix:** At the start of the function, explicitly reset the index:
```python
df = df.reset_index(drop=True)
```
Or add a guard assertion:
```python
assert df.index.equals(pd.RangeIndex(len(df))), "compute_lag_features requires contiguous RangeIndex"
```

## Info

### IN-01: Unused import -- ResultSchema

**File:** `src/pipeline/feature_generator.py:34`
**Issue:** `from src.schemas.result import ResultSchema  # noqa: F401` is imported but never referenced anywhere in the module. The leakage audit at line 997 intentionally uses only `[RaceSchema, EntrySchema]`, excluding `ResultSchema` because all its fields are marked post-race. The import is dead code.

**Fix:** Remove the unused import or add a comment explaining it is kept for future use.

### IN-02: Unregistered pytest.mark.integration

**File:** `tests/pipeline/test_feature_generator.py:1789` (and 8 other locations)
**Issue:** The `@pytest.mark.integration` decorator is used on 9 test methods but the mark is not registered in `pytest.ini`, `pyproject.toml`, or a `conftest.py` file. This produces `PytestUnknownMarkWarning` for every such test. The tests still run (not skipped), but the warnings clutter output.

**Fix:** Register the mark in `pyproject.toml`:
```toml
[tool.pytest.ini_options]
markers = ["integration: requires real data/standard/*.parquet files"]
```

### IN-03: extract_race/horse_features return values used only for logging

**File:** `src/pipeline/feature_generator.py:932-935`
**Issue:** In `generate()`, `extract_race_context_features(df)` and `extract_horse_basic_features(df)` are called and their return values are only used to log column counts. The actual feature data remains in `df` (these functions return copies). This works correctly but is misleading -- a reader might think these function calls modify `df` or that their return values are used downstream.

**Fix:** Either remove these calls (the logging adds minimal value since the column lists are static and known) or rename the variables to clarify intent (e.g., `race_features_for_logging`).

---

_Reviewed: 2026-06-12T18:15:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
