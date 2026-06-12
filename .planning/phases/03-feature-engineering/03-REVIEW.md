---
phase: 03-feature-engineering
reviewed: 2026-06-12T20:30:00Z
depth: deep
files_reviewed: 3
files_reviewed_list:
  - src/pipeline/feature_generator.py
  - tests/pipeline/test_feature_generator.py
  - tests/pipeline/conftest.py
findings:
  critical: 2
  warning: 4
  info: 4
  total: 10
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-06-12T20:30:00Z
**Depth:** deep
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Deep review of the feature engineering pipeline (`feature_generator.py`, 1023 lines) and its test suite (`test_feature_generator.py`, 2028 lines + `conftest.py`, 683 lines). Cross-file analysis was performed tracing the full `generate()` orchestration path, import graph to `src/schemas/audit.py`, `entry.py`, `race.py`, `result.py`, and call chains across all 15 public functions. All 85 non-integration tests pass.

Two critical data leakage bugs were found. The most severe is in `compute_finish_time_zscore`: the `.shift(1)` at lines 305/308 operates globally across `groupby` boundaries, causing normalization parameters from one `(course_name, distance, surface)` group to leak into the first valid row of the next group. This was confirmed by reproduction and is invisible to tests because every z-score test uses a single group. The second critical issue is that `compute_lag_features` assumes a contiguous `RangeIndex` and crashes with `KeyError` when called standalone on a sliced DataFrame.

Four warnings cover test coverage gaps, an implicit sort-order dependency in `compute_debut_flag`, and dead code in `COMPONENT_MAP`.

## Critical Issues

### CR-01: Cross-group data leakage in finish_time_zscore via global shift(1)

**File:** `src/pipeline/feature_generator.py:304-309`
**Issue:** In `compute_finish_time_zscore`, the code computes expanding-window mean/std per `(course_name, distance, surface)` group, then applies `.shift(1)` to exclude the current race from its own normalization. However, `.shift(1)` operates on the flat MultiIndex Series returned by the groupby-expanding operation, shifting across group boundaries. This causes the last row's expanding mean from group A (e.g., Nakayama 1600 turf) to be assigned as the normalization mean for the first valid row of group B (e.g., Tokyo 2000 turf).

The code at lines 304-308:
```python
grp = race_means.groupby(["course_name", "distance", "surface"])
race_means["norm_mean"] = (
    grp["race_ft_mean"].expanding(min_periods=5).mean().shift(1).values
)
race_means["norm_std"] = (
    grp["race_ft_mean"].expanding(min_periods=5).std().shift(1).values
)
```

The `.shift(1)` on the grouped Series shifts the entire concatenated result by one position globally. Verified reproduction: two groups with 6 rows each. Row index 6 (first Tokyo 2000 race) received `norm_mean=71.25` from the Nakayama 1600 group, when it should be NaN. Row index 3 (second Tokyo race) received NaN when it should have been 118.5 (the shifted expanding mean from its own group's first race).

This bug affects the `finish_time_zscore` column AND all 5 lag features derived from it (`prev_{1..5}_finish_time_zscore`, `prev3_finish_time_zscore_*`, `prev5_finish_time_zscore_*`). On real data with many distinct `(course, distance, surface)` groups, every group boundary (after the first) will have contaminated z-scores for its first few races. The z-score column is also listed in `EXCLUDE_FROM_FEATURES` (line 103) but its lag versions (`prev_*_finish_time_zscore`) ARE in `FEATURE_COLUMNS` and will be fed to LightGBM with incorrect values.

All 85 existing tests pass because every z-score test fixture (`_make_two_race_fixture`, `_make_many_race_fixture`) creates all races in a single group (Tokyo 2000 turf), so the cross-group boundary is never exercised. The real-data temporal invariance test at line 1847 explicitly excludes `finish_time_zscore` columns from comparison, masking the issue.

**Fix:**
Replace the global `.shift(1)` with a per-group shift using `groupby.transform`:
```python
grp = race_means.groupby(["course_name", "distance", "surface"])

race_means["norm_mean"] = grp["race_ft_mean"].transform(
    lambda s: s.expanding(min_periods=5).mean().shift(1)
)
race_means["norm_std"] = grp["race_ft_mean"].transform(
    lambda s: s.expanding(min_periods=5).std().shift(1)
)
```

A new test must be added that creates races across at least two different `(course_name, distance, surface)` groups and verifies:
1. The first valid z-score row in each group uses only its own group's history.
2. No z-score value in group B depends on any race in group A.

### CR-02: compute_lag_features crashes on non-contiguous DataFrame index

**File:** `src/pipeline/feature_generator.py:370-426`
**Issue:** The function saves the original DataFrame index as `_orig_idx` (line 372-373), then writes lag values back using `df_indexed.loc[lag_only["_orig_idx"].values, col]` (line 425). This pattern assumes the input `df` has a contiguous `RangeIndex(0, N-1)`. When called on a DataFrame with a non-contiguous index (e.g., after `df.iloc[1:]` producing index `[1, 2, 3, ...]`), the `_orig_idx` values will reference positions that do not exist in `df_indexed = df.reset_index(drop=True)`, causing a `KeyError`.

Verified reproduction: calling `compute_lag_features(df.iloc[[1, 2]])` on a 3-row DataFrame raises `KeyError: '[2] not in index'`.

In the `generate()` pipeline this is safe because `load_and_merge()` produces a clean `RangeIndex` (line 815: `.reset_index(drop=True)`) and all intermediate steps preserve it. However, the function is public and exported in `__init__` imports -- any standalone usage with a filtered/sliced DataFrame will crash.

**Fix:**
Add an explicit index normalization at the function start:
```python
def compute_lag_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reset_index(drop=True)  # Ensure contiguous RangeIndex for merge-back
    df = df.copy()
    # ... rest of function
```

This ensures the `_orig_idx` values always align with `df_indexed`'s index regardless of the input's index state.

## Warnings

### WR-01: COMPONENT_MAP is entirely redundant with MARGIN_MAP

**File:** `src/pipeline/feature_generator.py:143-147`
**Issue:** `COMPONENT_MAP` contains three entries (`"ハナ": 0.02`, `"クビ": 0.10`, `"1/2": 0.50`) that are all already present in `MARGIN_MAP` with identical values. In the compound parsing logic (line 183-188), `MARGIN_MAP` is checked first at line 184, so `COMPONENT_MAP` is only reached if a part is NOT in `MARGIN_MAP` but IS in `COMPONENT_MAP` -- which is impossible given current entries. This is dead code that adds maintenance burden and confusion. A reader might expect `COMPONENT_MAP` to have unique additive-only components not in the main map, but it does not.

**Fix:** Remove `COMPONENT_MAP` entirely and change line 186-187 to just check `MARGIN_MAP`:
```python
for part in parts:
    part = part.strip()
    if part in MARGIN_MAP:
        total += MARGIN_MAP[part]
    else:
        return None  # Unknown component -> graceful degradation
```
Or, if `COMPONENT_MAP` is kept for future expansion, add a doc comment explaining its purpose and add at least one entry that is NOT in `MARGIN_MAP`.

### WR-02: compute_debut_flag silently produces incorrect results if input is not sorted

**File:** `src/pipeline/feature_generator.py:642-684`
**Issue:** `compute_debut_flag` uses `df.groupby("horse_entity_key")["is_valid_start"].cumsum()` (line 676) which operates in row order. If the input DataFrame is not sorted by `SORT_KEY`, the cumulative sum and debut flag will be computed in the wrong chronological order. The docstring states the precondition ("DataFrame sorted by SORT_KEY") but the function does not enforce it. Unlike `compute_lag_features` which sorts internally, `compute_debut_flag` trusts the caller entirely.

In the `generate()` pipeline this is safe (sort order is preserved from step 1 through step 9). But as a standalone public function, silent incorrect output is more dangerous than a crash -- it would produce plausible-looking debut flags that are chronologically wrong.

**Fix:** Add a sort assertion or sort internally at function start:
```python
df = df.sort_values(SORT_KEY).reset_index(drop=True)
df = df.copy()
```

### WR-03: Z-score temporal invariance test excluded from real-data check, masking the cross-group bug

**File:** `tests/pipeline/test_feature_generator.py:1847-1853`
**Issue:** `test_temporal_invariance_real_data` explicitly excludes `finish_time_zscore` and its lag derivatives from temporal invariance verification, with a comment that "z-score normalization uses expanding-window stats that depend on the full group history." While truncating the dataset can change which rows have valid z-scores (due to `min_periods=5`), for rows where z-scores ARE valid in both the truncated and full datasets, they should be identical because the expanding window is inherently backward-looking. The blanket exclusion masks the cross-group shift bug (CR-01) -- had the z-score columns been checked, the test would likely have caught the group-boundary leakage.

**Fix:** Refine the temporal invariance test to compare z-score values only for rows where both the full and truncated datasets produce valid (non-NaN) z-scores, rather than excluding z-score columns entirely. This requires computing the intersection of valid z-score rows across both datasets.

### WR-04: D-08 intersection caps at 100 race-level entries, not 100 valid starts

**File:** `src/pipeline/feature_generator.py:513`
**Issue:** The `_compute_person_stats` function caps `prior_starts` at 100 entries (`prior_starts = prior_starts[-100:]`), but `prior_starts` stores race-level tuples where each tuple can represent multiple valid starts (e.g., a trainer with 3 runners in one race has `valid_start_count=3`). The D-08 spec says "most recent 100 prior valid starts" but the code implements "most recent 100 prior race entries." For trainers with multi-runner entries (common in JRA), this could retain significantly more than 100 valid starts. For jockeys who ride at most one horse per race, there is no difference. The docstring at line 439-440 says "Among the most recent 100 prior valid starts" which does not match the implementation.

**Fix:** Either update the docstring to accurately describe the race-level capping behavior, or change the implementation to cap based on cumulative valid_start_count rather than number of race entries. The race-level capping is arguably more correct (it prevents old multi-runner races from dominating), so updating the documentation is the simpler fix.

## Info

### IN-01: Unused import -- ResultSchema

**File:** `src/pipeline/feature_generator.py:34`
**Issue:** `from src.schemas.result import ResultSchema  # noqa: F401` is imported but never referenced in the module. The leakage audit at line 997 intentionally uses only `[RaceSchema, EntrySchema]`, excluding `ResultSchema` because all its fields are marked post-race. The `noqa: F401` suppresses the linter warning but the import is dead code.

**Fix:** Remove the import or add a comment explaining it is kept for documentation/future use.

### IN-02: Unregistered pytest.mark.integration

**File:** `tests/pipeline/test_feature_generator.py:1789` (and 8 other locations)
**Issue:** The `@pytest.mark.integration` decorator is used on 9 test methods but the mark is not registered in `pytest.ini`, `pyproject.toml`, or a `conftest.py` file. This produces `PytestUnknownMarkWarning` for each decorated test. The tests still run (not skipped), but the warnings clutter output and the marks cannot be used for test selection (e.g., `pytest -m "not integration"`).

**Fix:** Register the mark in `pyproject.toml`:
```toml
[tool.pytest.ini_options]
markers = ["integration: requires real data/standard/*.parquet files"]
```

### IN-03: extract_race/horse_features return values used only for logging

**File:** `src/pipeline/feature_generator.py:932-935`
**Issue:** In `generate()`, `extract_race_context_features(df)` and `extract_horse_basic_features(df)` are called and their return values are only used to log column counts. The actual feature data remains in `df` (these functions return copies). The `field_size` column computed inside `extract_race_context_features` is also computed redundantly at line 928. This works correctly but is misleading -- a reader might think these calls modify `df` or that their return values are used downstream.

**Fix:** Remove these calls (the column counts are static and known from `RACE_FEATURES`/`HORSE_FEATURES`), or rename variables to clarify logging-only intent (e.g., `_race_features_for_logging`).

### IN-04: race_id in FEATURE_COLUMNS but not in CATEGORICAL_COLUMNS

**File:** `src/pipeline/feature_generator.py:56-57`
**Issue:** `RACE_FEATURES` includes `race_id`, which propagates into `FEATURE_COLUMNS` and thus into `features_pred.parquet`. However, `race_id` is not in `CATEGORICAL_COLUMNS`, so it remains as a string/object column in the Parquet output. When this file is loaded for LightGBM training, `race_id` would need to be explicitly excluded from the feature matrix (it is an identifier, not a predictive feature). This is likely intentional (race_id is needed for identification/joining in downstream steps) but could cause a runtime error if the Parquet is naively fed to LightGBM without column selection.

**Fix:** Document this explicitly in the `FEATURE_COLUMNS` definition or add a `IDENTIFIER_COLUMNS` list that downstream consumers know to exclude from the model feature matrix.

---

_Reviewed: 2026-06-12T20:30:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
