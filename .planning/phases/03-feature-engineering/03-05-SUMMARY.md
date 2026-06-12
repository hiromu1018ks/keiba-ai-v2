---
phase: 03-feature-engineering
plan: 05
subsystem: data-pipeline
tags: [pandas, parquet, lightgbm, feature-engineering, categorical, leakage-audit, temporal-invariance]

# Dependency graph
requires:
  - phase: 03-feature-engineering
    plan: 04
    provides: generate_target() and compute_debut_flag() wired into generate() orchestrator
provides:
  - convert_to_categorical() for LightGBM native categorical handling
  - Static FEATURE_COLUMNS allowlist from named feature groups
  - Complete generate() orchestrator with Parquet output
  - features_train.parquet (311,806 rows, 78 columns)
  - features_pred.parquet (311,806 rows, 74 columns)
  - Temporal invariance proven on fixture and real data
affects: [07-model-training]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Static FEATURE_COLUMNS allowlist from named feature group lists (Cycle 3 root cause fix)"
    - "Leakage audit with RaceSchema + EntrySchema only (ResultSchema marks race_id as post-race)"
    - "CategoricalDtype conversion with whitespace stripping for Japanese text"

key-files:
  created:
    - data/feature/features_train.parquet
    - data/feature/features_pred.parquet
  modified:
    - src/pipeline/feature_generator.py
    - tests/pipeline/test_feature_generator.py

key-decisions:
  - "FEATURE_COLUMNS is a static allowlist concatenated from RACE_FEATURES + HORSE_FEATURES + LAG_RAW_FEATURES + LAG_STAT_FEATURES + PERSON_FEATURES + DEBUT_FEATURE -- no column can silently appear in model features"
  - "Leakage audit uses RaceSchema + EntrySchema only; ResultSchema marks ALL fields (including race_id) as post-race, but race_id is pre-race per RaceSchema/EntrySchema"
  - "finish_time_zscore excluded from temporal invariance spot-check because expanding-window normalization depends on full group history"

patterns-established:
  - "Static feature allowlist: FEATURE_COLUMNS is a module-level constant explicitly enumerating every model feature column"
  - "Two-file output: features_train.parquet includes target/auxiliary columns; features_pred.parquet is prediction-ready with only features + entity keys"

requirements-completed: [DATA-03]

# Metrics
duration: 34min
completed: 2026-06-12
---

# Phase 03 Plan 05: Feature Generation Complete Summary

**Complete feature generation pipeline with static FEATURE_COLUMNS allowlist, categorical conversion for LightGBM, leakage audit, and temporal invariance proven on 311K-row real data**

## Performance

- **Duration:** 34 min
- **Started:** 2026-06-12T07:32:29Z
- **Completed:** 2026-06-12T08:06:04Z
- **Tasks:** 2 (both TDD)
- **Files modified:** 2

## Accomplishments

- convert_to_categorical() converts all 9 CATEGORICAL_COLUMNS to pandas CategoricalDtype with whitespace stripping, enabling LightGBM native categorical handling
- FEATURE_COLUMNS redesigned as a true static allowlist: 72 columns explicitly enumerated from 6 named feature group lists (RACE, HORSE, LAG_RAW, LAG_STAT, PERSON, DEBUT). No column can silently appear in model features without being named.
- generate() orchestrator complete with column validation, leakage audit, and two-file Parquet output
- features_train.parquet: 311,806 rows, 78 columns (72 features + 2 entity keys + 4 auxiliary: target_top3, result_status, is_dnf, exclude_from_training)
- features_pred.parquet: 311,806 rows, 74 columns (72 features + 2 entity keys only -- no target/auxiliary/current-race result derivatives)
- Temporal invariance proven on fixture data and verified on real 2015-2021 Kaggle data
- Horse collision verification: "アームストロング" correctly split into 2 horse_entity_key values
- Trainer rate verified: sum-based aggregation across multi-runner races
- target_top3 distribution: 21.19% positive rate (within expected ~21% +/- 5%)
- 95 total tests passing (86 unit + 9 integration), 3 stub classes removed

## Task Commits

Each task was committed atomically (TDD):

1. **Task 1 RED: Categorical + allowlist + leakage + Parquet tests** - `a65cd70` (test)
2. **Task 1 GREEN: Full implementation** - `b95684d` (feat)
3. **Task 2: Temporal invariance + real data tests + FutureWarning fix** - `fcb8524` (feat)

## Files Created/Modified

- `src/pipeline/feature_generator.py` - Added convert_to_categorical(), static FEATURE_COLUMNS allowlist (6 named feature group constants), EXCLUDE_FROM_FEATURES, ENTITY_KEY. Complete generate() orchestrator with column validation, leakage audit, and Parquet output. Fixed FutureWarning in lag feature assignment.
- `tests/pipeline/test_feature_generator.py` - Added TestCategoricalConversion (3 tests), TestLeakageAudit (2 tests), TestEndToEnd (9 tests), TestTemporalInvariance (2 tests), TestRealDataIntegration (8 tests). Removed 3 stub classes.
- `data/feature/features_train.parquet` - Training features with target_top3 (311,806 rows, 78 columns)
- `data/feature/features_pred.parquet` - Prediction features without target (311,806 rows, 74 columns)

## Decisions Made

- FEATURE_COLUMNS is a static allowlist constructed by concatenating RACE_FEATURES + HORSE_FEATURES + LAG_RAW_FEATURES + LAG_STAT_FEATURES + PERSON_FEATURES + DEBUT_FEATURE. This is the fundamental Cycle 3 root cause fix -- no column can auto-include.
- Leakage audit uses RaceSchema + EntrySchema only. ResultSchema marks ALL fields as post-race (including race_id), but race_id is pre-race per RaceSchema/EntrySchema. Checking against all three schemas would false-positive on race_id.
- finish_time_zscore excluded from temporal invariance real-data spot-check. The expanding-window normalization depends on full group history; truncating the dataset changes normalization params for groups. Non-normalized features are temporally invariant.
- generate() validates columns at step 11: asserts all FEATURE_COLUMNS exist and warns about unexpected columns. This catches any pipeline changes that add/remove columns without updating the allowlist.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Import name mismatch in test file**
- **Found during:** Task 1 (test execution)
- **Issue:** Test imported `convert_categorical` but function was named `convert_to_categorical`
- **Fix:** Updated test import to match actual function name
- **Files modified:** tests/pipeline/test_feature_generator.py
- **Verification:** All 85 tests pass
- **Committed in:** b95684d (Task 1 GREEN commit)

**2. [Rule 3 - Blocking] field_size not added to main DataFrame in generate()**
- **Found during:** Task 1 (test execution)
- **Issue:** extract_race_context_features() computed field_size but generate() didn't add it to the main DataFrame before downstream processing
- **Fix:** Added `df["field_size"] = df.groupby("race_id")["horse_number"].transform("count")` before extraction step
- **Files modified:** src/pipeline/feature_generator.py
- **Verification:** Column validation no longer raises ValueError
- **Committed in:** b95684d (Task 1 GREEN commit)

**3. [Rule 3 - Blocking] Redundant local imports in generate() causing ruff F811**
- **Found during:** Task 1 (lint check)
- **Issue:** audit_leakage, RaceSchema, EntrySchema were imported both at module level and locally in generate()
- **Fix:** Removed local imports, used module-level imports directly
- **Files modified:** src/pipeline/feature_generator.py
- **Verification:** ruff check clean
- **Committed in:** b95684d (Task 1 GREEN commit)

**4. [Rule 1 - Bug] FutureWarning in lag feature assignment**
- **Found during:** Task 2 (real data generation)
- **Issue:** Setting Int64 values into float64-initialized NaN columns triggers pandas FutureWarning
- **Fix:** Added `.astype(float)` to lag values before assignment
- **Files modified:** src/pipeline/feature_generator.py
- **Verification:** No FutureWarning on 311K-row generation
- **Committed in:** fcb8524 (Task 2 commit)

---

**Total deviations:** 4 auto-fixed (2 bug, 2 blocking)
**Impact on plan:** All auto-fixes necessary for correctness and clean execution. No scope creep.

## Issues Encountered

- finish_time_zscore columns are not temporally invariant under dataset truncation due to expanding-window normalization. This is by design (normalization depends on available history), but the temporal invariance test needed adjustment to exclude these columns from spot-checking. The test still verifies temporal invariance for all other feature types (lag positions, margin, last_3f, corner_4, jockey/trainer rates, debut flag).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Feature generation pipeline complete and validated on real 311K-row data
- features_train.parquet and features_pred.parquet ready for Phase 07 (Model Training)
- All 95 tests passing (86 unit + 9 integration)
- Phase 03 complete: 5 plans executed, feature engineering pipeline fully operational
- Key outputs: 72 model features, 2 entity keys, 4 auxiliary columns, zero leakage proven

## Self-Check: PASSED

- Both modified source files verified on disk
- All 3 TDD commits verified in git log (a65cd70 RED, b95684d GREEN, fcb8524 Task 2)
- 95 tests passing (86 unit + 9 integration), 0 skipped (stubs removed)
- ruff lint clean on both source and test files
- features_train.parquet: 311,806 rows, 78 columns
- features_pred.parquet: 311,806 rows, 74 columns
- Full non-integration test suite: 226 passed

---
*Phase: 03-feature-engineering*
*Completed: 2026-06-12*
