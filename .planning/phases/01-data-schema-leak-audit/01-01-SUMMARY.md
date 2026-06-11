---
phase: 01-data-schema-leak-audit
plan: 01
subsystem: data
tags: [pydantic, schema, validation, tdd]

# Dependency graph
requires:
  - phase: none
    provides: "Greenfield - first implementation plan"
provides:
  - "RaceSchema Pydantic model with 41 pre-race fields"
  - "EntrySchema Pydantic model with 16 fields (14 pre-race, 2 post-race)"
  - "Project infrastructure (pyproject.toml, package structure)"
  - "json_schema_extra pattern for pre_race metadata on every field"
affects: [02-kaggle-pipeline, 03-feature-engineering, 04-scraping]

# Tech tracking
tech-stack:
  added: [pydantic>=2.13, pytest>=9.0, ruff>=0.15, mypy>=1.14]
  patterns:
    - "Pydantic BaseModel with Field(json_schema_extra={pre_race, table}) for schema metadata"
    - "TDD RED/GREEN cycle for schema definitions"
    - "Optional[T] with Field(default=None) for nullable columns"

key-files:
  created:
    - pyproject.toml
    - src/__init__.py
    - src/schemas/__init__.py
    - src/schemas/race.py
    - src/schemas/entry.py
    - tests/__init__.py
    - tests/schemas/__init__.py
    - tests/schemas/test_race.py
    - tests/schemas/test_entry.py
    - .gitignore
  modified: []

key-decisions:
  - "Used json_schema_extra (not metadata=) for pre_race classification per Pydantic v2 API"
  - "20 レース記号/* columns mapped to individual Optional[bool] race_flag_* fields"
  - "build-backend set to setuptools.build_meta (pip install -e '.[dev]' workflow, Poetry not installed)"

patterns-established:
  - "Pattern: Every schema field has json_schema_extra={pre_race: bool, table: str}"
  - "Pattern: Nullable columns use Optional[T] = Field(default=None, ...)"
  - "Pattern: TDD cycle with test-only commit then implementation commit"

requirements-completed: [DATA-01]

# Metrics
duration: 7min
completed: 2026-06-11
---

# Phase 1 Plan 01: Race & Entry Schema Foundation Summary

**RaceSchema (41 fields, all pre-race) and EntrySchema (16 fields, mixed pre/post-race) with TDD-verified Pydantic models using json_schema_extra metadata**

## Performance

- **Duration:** 7 min
- **Started:** 2026-06-11T03:56:46Z
- **Completed:** 2026-06-11T04:04:44Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments
- RaceSchema defines 41 race-level columns: 21 named fields + 20 boolean race_flag_* fields, all pre_race=True
- EntrySchema defines 16 entry-level columns with mixed classification: 14 pre_race=True, popularity/win_odds pre_race=False per D-03
- horse_weight and weight_change correctly classified as pre_race=True per D-05
- model_json_schema() exports machine-readable JSON with pre_race metadata for downstream audit
- Full TDD cycle: RED (failing test) -> GREEN (implementation passes) for both schemas
- All 19 tests pass, ruff check clean

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Add failing tests for RaceSchema** - `e7c49b4` (test)
2. **Task 1 GREEN: Implement RaceSchema with 41 pre-race fields** - `f375b6f` (feat)
3. **Task 2 RED: Add failing tests for EntrySchema** - `c928c7b` (test)
4. **Task 2 GREEN: Implement EntrySchema with 16 mixed pre/post-race fields** - `9231d8d` (feat)

**Supporting commits:**
- `4a5a67e` (chore): add .gitignore for Python project

_Note: TDD tasks have separate RED (test) and GREEN (implementation) commits_

## Files Created/Modified
- `pyproject.toml` - Project configuration with PEP 621, pydantic/pytest/ruff/mypy deps
- `src/__init__.py` - Package initialization
- `src/schemas/__init__.py` - Schemas package stub (updated in Plan 05)
- `src/schemas/race.py` - RaceSchema model with 41 fields
- `src/schemas/entry.py` - EntrySchema model with 16 fields (mixed pre/post-race)
- `tests/__init__.py` - Tests package initialization
- `tests/schemas/__init__.py` - Test schemas package initialization
- `tests/schemas/test_race.py` - 7 tests for RaceSchema
- `tests/schemas/test_entry.py` - 12 tests for EntrySchema
- `.gitignore` - Python project gitignore

## Decisions Made
- Used `json_schema_extra` (not `metadata=`) for pre_race classification -- Pydantic v2 `metadata` parameter accepts constraint objects, not arbitrary dicts
- Mapped 20 レース記号/* columns to individual `Optional[bool]` race_flag_* fields for explicit schema clarity
- Set build-backend to `setuptools.build_meta` since Poetry is not installed (RESEARCH.md confirmed)
- Added `.gitignore` to exclude `__pycache__`, `.egg-info`, and `data/` (Rule 2: auto-add missing critical)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed pyproject.toml build-backend**
- **Found during:** Task 1 (project installation)
- **Issue:** Initial build-backend `setuptools.backends._legacy:_Backend` does not exist in installed setuptools version
- **Fix:** Changed to `setuptools.build_meta` (standard setuptools backend)
- **Files modified:** pyproject.toml
- **Verification:** `pip install -e ".[dev]"` succeeded
- **Committed in:** f375b6f (Task 1 commit)

**2. [Rule 1 - Bug] Fixed ruff lint errors in test files**
- **Found during:** Task 1 and Task 2 (lint verification)
- **Issue:** Unused imports (pytest, Optional, get_origin) and unused variable (is_optional)
- **Fix:** Removed unused imports and simplified type checking logic
- **Files modified:** tests/schemas/test_race.py, tests/schemas/test_entry.py
- **Verification:** `ruff check` passes clean
- **Committed in:** f375b6f, 9231d8d (task commits)

**3. [Rule 2 - Missing Critical] Added .gitignore**
- **Found during:** Post-task git status check
- **Issue:** Generated files (__pycache__, .egg-info, .DS_Store) were untracked
- **Fix:** Created .gitignore with Python-standard exclusions
- **Files modified:** .gitignore (new)
- **Verification:** `git status` clean of generated files
- **Committed in:** 4a5a67e

---

**Total deviations:** 3 auto-fixed (1 blocking, 1 bug, 1 missing critical)
**Impact on plan:** All auto-fixes were infrastructure/tooling adjustments. No scope creep or architectural changes.

## Issues Encountered
None beyond the auto-fixes documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- RaceSchema and EntrySchema are complete and tested
- json_schema_extra pattern established for all downstream schemas (result, odds_trifecta, payoff)
- pyproject.toml ready for additional dependencies in Plan 02-05
- Tests provide template for writing schema tests in subsequent plans

## Self-Check: PASSED

All 11 files verified present. All 5 commits verified in git log.

---
*Phase: 01-data-schema-leak-audit*
*Completed: 2026-06-11*
