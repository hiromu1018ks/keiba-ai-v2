---
phase: 03-feature-engineering
fixed_at: 2026-06-12T10:15:00Z
review_path: .planning/phases/03-feature-engineering/03-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 3: Code Review Fix Report

**Fixed at:** 2026-06-12T10:15:00Z
**Source review:** .planning/phases/03-feature-engineering/03-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 6
- Fixed: 6
- Skipped: 0

## Fixed Issues

### CR-01: Cross-group data leakage in finish_time_zscore via global shift(1)

**Files modified:** `src/pipeline/feature_generator.py`, `tests/pipeline/test_feature_generator.py`
**Commit:** 5a6c0c3
**Applied fix:** Replaced global `.shift(1)` with per-group shift using `groupby.transform(lambda s: s.expanding(min_periods=5).mean().shift(1))`. The transform applies shift within each group independently, preventing cross-group contamination. Added `test_cross_group_no_leakage` test that creates races across two different (course, distance, surface) groups, shuffles the input, and verifies z-scores match standalone computation for each group.

### CR-02: compute_lag_features crashes on non-contiguous DataFrame index

**Files modified:** `src/pipeline/feature_generator.py`
**Commit:** cb1f617
**Applied fix:** Added `df = df.reset_index(drop=True)` at the start of `compute_lag_features`, before `df = df.copy()`. This ensures the `_orig_idx` merge-back pattern always aligns with `df_indexed`'s index regardless of the input's index state.

### WR-01: COMPONENT_MAP is entirely redundant with MARGIN_MAP

**Files modified:** `src/pipeline/feature_generator.py`, `tests/pipeline/test_feature_generator.py`
**Commit:** 2eb2f99
**Applied fix:** Removed the `COMPONENT_MAP` dictionary entirely. Updated compound parsing in `parse_margin` to only check `MARGIN_MAP`. Updated test docstring reference from "COMPONENT_MAP" to "MARGIN_MAP". All 3 entries in COMPONENT_MAP were already in MARGIN_MAP with identical values, making COMPONENT_MAP unreachable dead code.

### WR-02: compute_debut_flag silently produces incorrect results if input is not sorted

**Files modified:** `src/pipeline/feature_generator.py`
**Commit:** f23aa38
**Applied fix:** Added `df = df.sort_values(SORT_KEY).reset_index(drop=True)` at function start, before `df = df.copy()`. Updated docstring to document that sorting is enforced internally rather than requiring callers to pre-sort.

### WR-03: Z-score temporal invariance test excluded from real-data check

**Files modified:** `tests/pipeline/test_feature_generator.py`
**Commit:** b16c6e1
**Applied fix:** Replaced blanket exclusion of `finish_time_zscore` columns with intersection-based comparison. The refined test now includes `prev_1_finish_time_zscore` in the check columns and skips rows where either the full or truncated dataset produces NaN (due to min_periods=5). On the intersection of valid rows, z-scores must match -- catching cross-group leakage bugs that the previous exclusion masked.

### WR-04: D-08 intersection caps at 100 race-level entries, not 100 valid starts

**Files modified:** `src/pipeline/feature_generator.py`
**Commit:** 257ad2f
**Applied fix:** Updated docstring in `_compute_person_stats` to accurately describe the race-level capping behavior: "Among the most recent 100 prior race entries (each entry may contain multiple valid starts for trainers with multiple runners per race)."

---

_Fixed: 2026-06-12T10:15:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
