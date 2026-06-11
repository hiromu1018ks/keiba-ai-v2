---
phase: 01-data-schema-leak-audit
plan: 03
subsystem: data
tags: [pydantic, audit, data-leakage, tdd]

# Dependency graph
requires:
  - phase: 01-01
    provides: "RaceSchema, EntrySchema Pydantic models with json_schema_extra metadata"
  - phase: 01-02
    provides: "ResultSchema Pydantic model with all post-race fields"
provides:
  - "get_post_race_columns() function: extracts post-race column names from any BaseModel"
  - "audit_leakage() function: detects post-race columns in DataFrames, logs warning (D-12)"
  - "tests/schemas/conftest.py with shared fixtures for audit tests"
affects: [02-kaggle-pipeline, 03-feature-engineering, 04-scraping]

# Tech tracking
tech-stack:
  added: [loguru>=0.7]
  patterns:
    - "TYPE_CHECKING guard for pandas import -- no hard dependency at module level"
    - "Exact column name matching for leakage detection (no substring checks)"
    - "loguru logger.warning() for leakage, logger.info() for clean pass"

key-files:
  created:
    - src/schemas/audit.py
    - tests/schemas/conftest.py
    - tests/schemas/test_audit.py
  modified: []

key-decisions:
  - "audit_leakage returns list[str] of leaked columns for caller inspection, never raises (D-12)"
  - "Exact column name matching prevents false positives on lag features like prev_1_last_3f (Pitfall #3)"
  - "pandas import behind TYPE_CHECKING guard -- audit module usable without pandas installed"

patterns-established:
  - "Pattern: Pydantic model_fields introspection for metadata-driven column classification"
  - "Pattern: Warning-only audit functions that return diagnostic data without halting pipelines"

requirements-completed: [DATA-04]

# Metrics
duration: 3min
completed: 2026-06-11
---

# Phase 1 Plan 03: Audit Function Summary

**get_post_race_columns() and audit_leakage() functions using Pydantic model_fields introspection with exact column name matching and TYPE_CHECKING guard -- 11 TDD tests covering EntrySchema, ResultSchema, and RaceSchema**

## Performance

- **Duration:** 3 min
- **Started:** 2026-06-11T04:14:33Z
- **Completed:** 2026-06-11T04:17:14Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments
- get_post_race_columns() extracts post-race column names from any BaseModel subclass by reading json_schema_extra metadata
- audit_leakage() detects post-race columns in DataFrames with exact name matching, logs warning without raising (D-12)
- 11 tests covering all behaviors: EntrySchema (2 post-race), RaceSchema (0 post-race), ResultSchema (all 12 post-race)
- Lag feature columns (prev_1_last_3f) correctly do NOT trigger false positives (Pitfall #3)

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Add failing tests for audit functions** - `f455715` (test)
2. **Task 1 GREEN: Implement get_post_race_columns and audit_leakage** - `c2116b0` (feat)

_Note: TDD tasks have separate RED (test) and GREEN (implementation) commits_

## Files Created/Modified
- `src/schemas/audit.py` - get_post_race_columns() and audit_leakage() functions with TYPE_CHECKING guard
- `tests/schemas/conftest.py` - Shared pytest fixtures: sample_pre_race_df, sample_entry_post_race_df, sample_result_post_race_df, sample_mixed_df, sample_lag_feature_df, entry_model_classes, full_model_classes
- `tests/schemas/test_audit.py` - 11 tests in 2 test classes: TestGetPostRaceColumns (3), TestAuditLeakage (8)

## Decisions Made
- audit_leakage returns list[str] (not set) to preserve column order as they appear in DataFrame -- more useful for caller diagnostics
- Warning-only behavior per D-12: function logs and returns diagnostic data, caller decides how to proceed
- pandas import behind TYPE_CHECKING guard: audit module can be imported without pandas installed (only needed at runtime when actually checking DataFrames)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed unused pytest import**
- **Found during:** Task 1 GREEN (ruff lint check)
- **Issue:** `import pytest` was present but unused in test_audit.py
- **Fix:** Removed the unused import
- **Files modified:** tests/schemas/test_audit.py
- **Verification:** ruff check passes clean
- **Committed in:** c2116b0 (Task 1 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 lint bug)
**Impact on plan:** Trivial lint fix, no scope creep or architectural changes.

## Issues Encountered
None beyond the auto-fix documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- audit_leakage() ready for Phase 2 (Kaggle Pipeline) and Phase 3 (Feature Engineering)
- get_post_race_columns() works with any BaseModel subclass including future schema additions
- All 56 schema tests pass across 6 test files (19 from Plan 01 + 26 from Plan 02 + 11 from Plan 03)
- Remaining Phase 1 plans: column classification map (Plan 04), schema export (Plan 05)

## Self-Check: PASSED

All 3 files verified present. Both commits verified in git log.

---
*Phase: 01-data-schema-leak-audit*
*Completed: 2026-06-11*
