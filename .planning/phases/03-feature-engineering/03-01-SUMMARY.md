---
phase: 03-feature-engineering
plan: 01
subsystem: data-pipeline
tags: [pandas, parquet, feature-engineering, lightgbm, entity-key]

# Dependency graph
requires:
  - phase: 02-kaggle-data-pipeline
    provides: standard-layer Parquet files (race, entry, result)
provides:
  - feature_generator module with generate() orchestrator skeleton
  - derive_horse_entity_key() collision-safe horse identification
  - load_and_merge() safe inner-join merge with deterministic sort
  - extract_race_context_features() race-level context + field_size
  - extract_horse_basic_features() horse pre-race characteristics
  - Test fixtures with collision-horse data for downstream plans
affects: [03-feature-engineering-plans-02-05, 07-model-training]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "horse_entity_key = horse_name + birth_year_proxy (race_year - age) for collision disambiguation"
    - "SORT_KEY = [horse_entity_key, race_date, race_id] globally unique total order"
    - "Inner join on result (1:1 entry-result verified at 311,806 rows)"

key-files:
  created:
    - src/pipeline/feature_generator.py
    - tests/pipeline/test_feature_generator.py
  modified:
    - tests/pipeline/conftest.py

key-decisions:
  - "horse_entity_key uses birth_year_proxy (race_year - age) instead of first_race_date, disambiguating all 14 same-name collisions"
  - "Inner join on result correct because entry/result are 1:1 (311,806 rows each)"
  - "race_id (format YYYYPPCCDDRR) provides globally unique ordering across courses on same date"
  - "Result's race_id dropped before merge to avoid column name collision with entry's race_id"

patterns-established:
  - "Entity key derivation: horse_name + birth_year_proxy as collision-safe horse identifier"
  - "Sort ordering: [horse_entity_key, race_date, race_id] for deterministic globally-unique total order"
  - "Merge strategy: entry+race left join, then +result inner join with duplicate column handling"

requirements-completed: [DATA-03]

# Metrics
duration: 12min
completed: 2026-06-12
---

# Phase 03 Plan 01: Feature Generator Skeleton Summary

**Feature generator skeleton with collision-safe horse_entity_key (horse_name + birth_year_proxy), inner-join merge, deterministic race ordering via race_id, and race context + horse basic feature extraction**

## Performance

- **Duration:** 12 min
- **Started:** 2026-06-12T06:30:39Z
- **Completed:** 2026-06-12T06:42:35Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 3

## Accomplishments
- Horse entity key derivation that disambiguates all 14 same-name horse collisions in 2015-2021 data via birth_year_proxy
- Safe merge pipeline: entry+race left join, then +result inner join (1:1 relationship verified)
- Deterministic globally-unique sort order via [horse_entity_key, race_date, race_id]
- Race context features with field_size computation, excluding post-race columns (per D-15)
- Horse basic features excluding popularity/win_odds (per D-15)
- Comprehensive test fixtures with collision-horse test data for all downstream plans
- 11 tests passing, 9 stub tests for Plans 02-05

## Task Commits

Each task was committed atomically (TDD):

1. **Task 1 RED: Module skeleton + test fixtures** - `687e231` (test)
2. **Task 1 GREEN: Implementation** - `fef18ce` (feat)

## Files Created/Modified
- `src/pipeline/feature_generator.py` - Feature generation module with generate(), load_and_merge(), derive_horse_entity_key(), extract_race_context_features(), extract_horse_basic_features(); constants CATEGORICAL_COLUMNS, SORT_KEY (280 lines)
- `tests/pipeline/test_feature_generator.py` - Unit tests for entity key, merge, race context, horse basic features + 9 stub test classes
- `tests/pipeline/conftest.py` - Added 5 feature-specific fixtures: sample_standard_race_df, sample_standard_entry_df, sample_standard_result_df, sample_feature_merged_df, tmp_feature_dir

## Decisions Made
- Result DataFrame's race_id column dropped before merge to avoid race_id_x/race_id_y suffix collision (entry already has race_id from first merge)
- Schema imports (audit_leakage, EntrySchema, RaceSchema, ResultSchema) kept as forward imports for Plans 02-05 with noqa comments

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] race_id column collision in merge**
- **Found during:** Task 1 (GREEN phase - test execution)
- **Issue:** entry+race merge produces race_id, then result merge also has race_id, creating race_id_x/race_id_y suffixes. derive_horse_entity_key() then fails to find race_id column.
- **Fix:** Drop result's race_id before merging since it's redundant (entry already has it from the first merge)
- **Files modified:** src/pipeline/feature_generator.py
- **Verification:** All 11 tests pass, merge produces correct 14-row output
- **Committed in:** fef18ce (Task 1 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Minimal -- standard merge column handling. No scope creep.

## Issues Encountered
None beyond the race_id collision auto-fix above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Feature generator skeleton ready for Plans 02-05 to fill in:
  - Plan 02: margin numeric conversion, finish_time z-score, lag features computation
  - Plan 03: debut flag, lag feature assembly
  - Plan 04: target_top3 generation
  - Plan 05: categorical conversion, leakage audit, Parquet output
- Test fixtures include all required edge cases (collision horses, finish notes, same-date different-course)
- SORT_KEY and horse_entity_key patterns established for all downstream feature generation

## Self-Check: PASSED

- All 3 created/modified files verified on disk
- Both TDD commits verified in git log (687e231 RED, fef18ce GREEN)
- 11 tests passing, 9 skipped (stubs for Plans 02-05)
- ruff lint clean on all modified files

---
*Phase: 03-feature-engineering*
*Completed: 2026-06-12*
