---
phase: 03-feature-engineering
plan: 04
subsystem: data-pipeline
tags: [pandas, numpy, feature-engineering, target-variable, debut-flag, finish-note-classification]

# Dependency graph
requires:
  - phase: 03-feature-engineering
    plan: 03
    provides: lag features and jockey/trainer stats columns in generate() orchestrator
provides:
  - generate_target() with target_top3, result_status, is_dnf, exclude_from_training columns
  - compute_debut_flag() with is_debut and is_valid_start columns
affects: [03-feature-engineering-plan-05, 07-model-training]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "np.select() for multi-condition finish_note mapping to result_status"
    - "cumsum-based debut flag with valid-start exclusion"

key-files:
  created: []
  modified:
    - src/pipeline/feature_generator.py
    - tests/pipeline/test_feature_generator.py

key-decisions:
  - "result_status uses np.select() with 5 finish_note conditions and 'finished' default, no 'no_result' category needed"
  - "is_debut computed via cumsum minus current row's contribution, avoiding explicit loops"
  - "Boolean columns use .astype(bool) to ensure Python bool compatibility with pandas"

requirements-completed: [DATA-03]

# Metrics
duration: 8min
completed: 2026-06-12
---

# Phase 03 Plan 04: Target Variable and Debut Flag Summary

**Target variable generation (target_top3) with 6-category result_status classification and debut flag (is_debut) that correctly excludes 取/除 from history count -- 17 tests passing across 2 TDD task pairs**

## Performance

- **Duration:** 8 min
- **Started:** 2026-06-12T07:19:46Z
- **Completed:** 2026-06-12T07:27:31Z
- **Tasks:** 2 (both TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments

- generate_target() creates 4 columns: target_top3 (Int64), result_status (string), is_dnf (bool), exclude_from_training (bool)
- result_status maps all 6 finish_note categories without any catch-all: finished, dnf, disqualified, scratched, removed, demoted
- 取 (scratched) and 除 (removed) produce distinct result_status values, resolving the HIGH review concern about distinguishing them
- 降 (demoted) horses keep finish_position, target_top3 based on actual position per D-12
- exclude_from_training correctly excludes only 取/除 per D-13
- compute_debut_flag() identifies first valid start per horse_entity_key, excluding 取/除 from history count
- A horse whose first entry is 取 does not consume the debut position; debut happens at the next valid start
- A horse with only 取 entries has is_debut=False for all entries
- Both functions wired into generate() orchestrator (steps 8 and 9)

## Task Commits

Each task was committed atomically (TDD):

1. **Task 1 RED: Target variable tests** - `b123a46` (test)
2. **Task 1 GREEN: generate_target() implementation** - `f16c7bb` (feat)
3. **Task 2 RED: Debut flag tests** - `9175a11` (test)
4. **Task 2 GREEN: compute_debut_flag() implementation** - `c717e88` (feat)

## Files Created/Modified

- `src/pipeline/feature_generator.py` - Added generate_target() (4 columns: target_top3, result_status, is_dnf, exclude_from_training), compute_debut_flag() (2 columns: is_debut, is_valid_start). Wired both into generate() orchestrator steps 8-9.
- `tests/pipeline/test_feature_generator.py` - Added TestTargetVariable (11 tests) and TestDebutFlag (6 tests). Removed stub classes. Updated imports.

## Decisions Made

- np.select() used for finish_note mapping: 5 conditions checked in order (中, 失, 取, 除, 降), default to "finished". Clean, no if-else chain needed.
- Boolean columns (.isin() result) explicitly cast with .astype(bool) to avoid np.True_/np.False_ vs Python True/False identity issues in test assertions.
- Debut flag uses cumsum-based approach: groupby horse_entity_key, cumsum of is_valid_start, subtract current row's contribution. O(n) vectorized, no loops.
- is_valid_start column created in compute_debut_flag() using result_status (consistent definition with Plan 03-03's valid-start mask).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Boolean identity comparison with numpy types**
- **Found during:** Task 1 (GREEN phase - test execution)
- **Issue:** Tests using `is True` / `is False` for boolean assertions failed because pandas .isin() returns np.True_/np.False_ which are not identical to Python True/False.
- **Fix:** Changed test assertions from `is True`/`is False` to `== True`/`== False` for pandas boolean compatibility.
- **Files modified:** tests/pipeline/test_feature_generator.py
- **Verification:** All 11 TestTargetVariable tests pass
- **Committed in:** f16c7bb (Task 1 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug in test assertions)
**Impact on plan:** Minimal -- test assertion style adjustment. No scope creep.

## Issues Encountered

None beyond the boolean identity auto-fix above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Target variable and debut flag complete. generate() orchestrator now has steps 1-9 implemented.
- Remaining for Plan 05: categorical CategoricalDtype conversion, leakage audit, Parquet output, end-to-end test.
- 71 total tests passing (11 target + 6 debut + 54 prior), 3 stubs remaining for Plan 05.

## Self-Check: PASSED

- Both modified files verified on disk
- All 4 TDD commits verified in git log (b123a46, f16c7bb, 9175a11, c717e88)
- 71 tests passing, 3 skipped (stubs for Plan 05)
- ruff lint clean on feature_generator.py
- Full test suite: 211 passed, 3 skipped

---
*Phase: 03-feature-engineering*
*Completed: 2026-06-12*
