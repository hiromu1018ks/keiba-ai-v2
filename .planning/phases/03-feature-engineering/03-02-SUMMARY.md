---
phase: 03-feature-engineering
plan: 02
subsystem: data-pipeline
tags: [pandas, numpy, feature-engineering, z-score, margin, temporal-safety]

# Dependency graph
requires:
  - phase: 03-feature-engineering
    plan: 01
    provides: feature_generator module skeleton with generate() orchestrator
provides:
  - parse_margin() text-to-numeric margin conversion with compound form support
  - convert_margin_to_numeric() DataFrame-level margin column transformation
  - parse_finish_time_to_seconds() M:SS.T time format parser
  - compute_finish_time_zscore() race-boundary z-score normalization with temporal safety
affects: [03-feature-engineering-plans-03-05, 07-model-training]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Race-boundary z-score: aggregate to race-level means, then expanding window with shift(1) at race level"
    - "Compound margin parsing: split on '+' and sum MARGIN_MAP + COMPONENT_MAP lookups"

key-files:
  created: []
  modified:
    - src/pipeline/feature_generator.py
    - tests/pipeline/test_feature_generator.py

key-decisions:
  - "Z-score normalization operates at RACE BOUNDARY level: each race's norm params come from prior races only, not from any runner in the current race"
  - "Expanding window min_periods=5: groups with fewer than 5 prior races produce NaN z-score"
  - "MARGIN_MAP contains 22 entries covering all unique margin values; COMPONENT_MAP handles additive parts in compound margins"
  - "parse_margin handles full-width spaces and trailing whitespace via str().strip()"
  - "Empty string margin treated as None (graceful degradation)"

patterns-established:
  - "Race-level aggregation for temporal-safe normalization: groupby race_id -> race-level means -> expanding with shift(1) -> join back"
  - "Compound text parsing: direct lookup first, then split-and-sum for '+' delimited forms"

requirements-completed: [DATA-03]

# Metrics
duration: 8min
completed: 2026-06-12
---

# Phase 03 Plan 02: Margin Conversion and Finish Time Z-Score Summary

**Margin text-to-numeric conversion (22-value MARGIN_MAP + compound parsing) and finish_time z-score normalization with race-boundary temporal safety -- no same-race leakage, temporal invariance verified**

## Performance

- **Duration:** 8 min
- **Started:** 2026-06-12T06:47:14Z
- **Completed:** 2026-06-12T06:56:13Z
- **Tasks:** 2 (both TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments

- Margin text-to-numeric conversion covering 22 unique margin values plus compound forms (e.g. "1.1/4+クビ" -> 1.35)
- Finish time string parsing (M:SS.T) to seconds
- Race-boundary z-score normalization: expanding window operates on race-level means, not individual rows, preventing same-race leakage
- Temporal invariance verified: adding future races does not change historical z-scores
- Sparse group guard: fewer than 5 prior races produce NaN z-score
- Std==0 guard: identical times produce NaN z-score, not inf
- 23 new tests (12 margin + 11 z-score) passing alongside 11 existing tests

## Task Commits

Each task was committed atomically (TDD):

1. **Task 1 RED: Margin conversion tests** - `9ea26bf` (test)
2. **Task 1 GREEN: Margin conversion implementation** - `7cf337e` (feat)
3. **Task 2 RED: Z-score tests** - `a5e3005` (test)
4. **Task 2 GREEN: Z-score implementation** - `6f12052` (feat)

## Files Created/Modified

- `src/pipeline/feature_generator.py` - Added MARGIN_MAP (22 entries), COMPONENT_MAP (3 entries), parse_margin(), convert_margin_to_numeric(), parse_finish_time_to_seconds(), compute_finish_time_zscore(). Wired both transformations into generate() orchestrator.
- `tests/pipeline/test_feature_generator.py` - Added TestMarginConversion (12 tests) and TestFinishTimeZscore (11 tests including race-boundary leakage and temporal invariance tests). Replaced stub classes.

## Decisions Made

- Z-score normalization uses race-boundary approach: aggregate to race-level means first, then apply expanding window with shift(1) at the race level. This is the fundamental fix for same-race leakage identified in Cycle 3 review.
- min_periods=5 for expanding window: requires at least 5 prior races before producing a valid z-score, preventing unreliable normalization from sparse data.
- parse_margin strips whitespace including full-width Japanese spaces (common in data) before lookup.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test 6 expectation used insufficient prior races**
- **Found during:** Task 2 (GREEN phase - test execution)
- **Issue:** test_later_race_sees_prior_race_stats used 2-race fixture but min_periods=5 requires 5+ prior races for non-NaN z-scores
- **Fix:** Changed test to use 7-race fixture, verifying race 6 has non-NaN z-scores (5 prior races meet min_periods)
- **Files modified:** tests/pipeline/test_feature_generator.py
- **Verification:** All 34 tests pass
- **Committed in:** 6f12052 (Task 2 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug in test expectation)
**Impact on plan:** Minimal -- test fixture adjustment. No scope creep.

## Issues Encountered

None beyond the test fixture auto-fix above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- margin_numeric and finish_time_seconds/finish_time_zscore columns now available for:
  - Plan 03: lag feature assembly (prev_1_margin_numeric, prev_1_finish_time_zscore, etc.)
  - Plan 03: debut flag and lag feature computation
- generate() orchestrator updated with steps 4-5; remaining placeholders for Plans 03-05
- Test fixtures include race-boundary test data for future plan verification

## Self-Check: PASSED

- Both modified files verified on disk
- All 4 TDD commits verified in git log (9ea26bf, 7cf337e, a5e3005, 6f12052)
- 34 tests passing (11 existing + 12 margin + 11 z-score), 7 skipped (stubs for Plans 03-05)
- ruff lint clean on all modified files
- Full test suite: 174 passed, 7 skipped

---
*Phase: 03-feature-engineering*
*Completed: 2026-06-12*
