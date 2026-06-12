---
phase: 03-feature-engineering
plan: 03
subsystem: data-pipeline
tags: [pandas, numpy, feature-engineering, lag-features, rolling-stats, temporal-safety, valid-start-filtering]

# Dependency graph
requires:
  - phase: 03-feature-engineering
    plan: 02
    provides: margin_numeric, finish_time_zscore columns for lag computation
provides:
  - compute_lag_features() with valid-start filtering (45 columns)
  - compute_jockey_trainer_stats() with sum-based race-level aggregation and exact D-08 intersection (6 columns)
  - _compute_person_stats() helper for per-person rolling stat computation
affects: [03-feature-engineering-plans-04-05, 07-model-training]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Valid-start filtering: exclude 取/除 from lag computation, merge back with all-NaN lags"
    - "Sum-based race-level aggregation: sum(top3_count)/sum(valid_start_count) per person-race"
    - "D-08 exact intersection: filter prior valid starts to BOTH (within 365 days AND among most recent 100)"

key-files:
  created: []
  modified:
    - src/pipeline/feature_generator.py
    - tests/pipeline/test_feature_generator.py
    - tests/pipeline/conftest.py

key-decisions:
  - "Lag features computed on valid-start rows only (取/除 excluded before shift), then merged back to full DataFrame with all-NaN lags for non-valid entries"
  - "Sum-based race-level aggregation for jockey/trainer stats: trainer with 2/3 top-3 runners gets 0.667 not 1.0"
  - "D-08 implemented as exact intersection (both conditions simultaneously), not minimum-of-two precomputed stats"
  - "prev3/prev5 rolling stats use min_periods=1 for mean, min_periods=2 for std (D-10)"
  - "Rolling stats iterate per-person with chronological race list, trimming from front for 365-day and from back for 100-start"

patterns-established:
  - "Valid-start mask: ~finish_note.isin(['取', '除']) consistently used across lag features and person stats"
  - "Entity-key-scoped groupby for temporal-safe lag computation"
  - "Left-merge pattern: compute on subset, merge back to full DataFrame preserving original index"

requirements-completed: [DATA-03]

# Metrics
duration: 14min
completed: 2026-06-12
---

# Phase 03 Plan 03: Lag Features and Jockey/Trainer Rolling Stats Summary

**Temporal-safe lag features (45 columns) with valid-start filtering ensuring scratched/removed entries never corrupt lag positions, plus jockey/trainer rolling statistics (6 columns) with sum-based race-level aggregation and exact D-08 intersection -- 3 HIGH root causes fixed**

## Performance

- **Duration:** 14 min
- **Started:** 2026-06-12T06:59:58Z
- **Completed:** 2026-06-12T07:14:05Z
- **Tasks:** 2 (both TDD: RED + GREEN)
- **Files modified:** 3

## Accomplishments

- Lag features with valid-start filtering: 取 (scratched) and 除 (removed) entries excluded from lag computation, preventing lag position corruption. 45 columns total: 25 raw lag (prev_1..5 x 5 metrics) + 20 rolling stats (prev3/5 mean/std).
- Jockey/trainer rolling statistics with sum-based race-level aggregation: trainer with 2 top-3 from 3 runners produces rate 2/3=0.667, not 1.0.
- D-08 exact intersection: stats computed over prior valid starts satisfying BOTH (within 365 days AND among most recent 100), not minimum-of-two.
- DNF (中) counts as valid start in both lag and person stat computations.
- Same-race leakage eliminated: person stats computed at race level, current race not included in current stats.
- 20 new tests (9 lag + 11 jockey/trainer) passing alongside 34 existing tests.

## Task Commits

Each task was committed atomically (TDD):

1. **Task 1 RED: Lag feature tests** - `fa6e77d` (test)
2. **Task 1 GREEN: Lag feature implementation** - `69c5386` (feat)
3. **Task 2 RED: Jockey/trainer stats tests** - `e95b9d2` (test)
4. **Task 2 GREEN: Jockey/trainer stats implementation** - `269b4a5` (feat)

## Files Created/Modified

- `src/pipeline/feature_generator.py` - Added compute_lag_features() (valid-start filtering, 45 columns), _compute_person_stats() (per-person D-08 intersection), compute_jockey_trainer_stats() (6 rolling stat columns). Wired both into generate() orchestrator.
- `tests/pipeline/test_feature_generator.py` - Added TestLagFeatures (9 tests) and TestJockeyTrainerStats (11 tests). Removed stub classes.
- `tests/pipeline/conftest.py` - Added sample_lag_merged_df fixture with scratch-between-valid-starts, DNF, and entity key collision data (16 rows).

## Decisions Made

- Valid-start filtering uses `~finish_note.isin(["取", "除"])` consistently across both lag features and person stat computations. Only these two codes indicate the horse never started.
- Lag features computed on filtered valid-start subset, then merged back to full DataFrame using original index. Non-valid entries get all-NaN lags.
- Rolling stats iterate per-person with a list of (date, top3_count, win_count, valid_start_count) tuples, trimmed from front for 365-day constraint and from back for 100-start constraint. O(n) per person.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test 8 fixture incorrectly placed old races within 365-day window**
- **Found during:** Task 2 (GREEN phase - test execution)
- **Issue:** D-08 intersection test fixture had 70 "old" races at 400-i days ago, meaning 35 of them fell within the 365-day window. Expected all 70 to be outside.
- **Fix:** Changed to 400+i days ago (400 to 469 days), ensuring all 70 old races are outside 365-day window.
- **Files modified:** tests/pipeline/test_feature_generator.py
- **Verification:** All 11 TestJockeyTrainerStats tests pass
- **Committed in:** 269b4a5 (Task 2 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug in test fixture)
**Impact on plan:** Minimal -- test fixture adjustment. No scope creep.

## Issues Encountered

None beyond the test fixture auto-fix above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 51 new feature columns (45 lag + 6 rolling stats) now available for:
  - Plan 04: target_top3 generation
  - Plan 05: categorical conversion, leakage audit, Parquet output
- generate() orchestrator updated with steps 6-7; remaining placeholders for debut flag, target variable, categorical conversion

## Self-Check: PASSED

- All 3 modified files verified on disk
- All 4 TDD commits verified in git log (fa6e77d, 69c5386, e95b9d2, 269b4a5)
- 54 tests passing (34 existing + 20 new), 5 skipped (stubs for Plans 04-05)
- ruff lint clean on feature_generator.py
- Full test suite: 194 passed, 5 skipped

---
*Phase: 03-feature-engineering*
*Completed: 2026-06-12*
