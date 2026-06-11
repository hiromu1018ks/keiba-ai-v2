---
phase: 01-data-schema-leak-audit
plan: 02
subsystem: data
tags: [pydantic, schema, validation, tdd]

# Dependency graph
requires:
  - phase: 01-01
    provides: "RaceSchema, EntrySchema Pydantic models, json_schema_extra pattern, project infrastructure"
provides:
  - "ResultSchema Pydantic model with 12 post-race fields"
  - "OddsTrifectaSchema Pydantic model with 16 post-race fields (Kaggle odds.csv)"
  - "PayoffSchema Pydantic model with 6 fields as contract for future phases"
affects: [02-kaggle-pipeline, 03-feature-engineering, 05-scraping, 08-ev-calculation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "All-post-race schema pattern: table where every field has pre_race=False"

key-files:
  created:
    - src/schemas/result.py
    - src/schemas/odds_trifecta.py
    - src/schemas/payoff.py
    - tests/schemas/test_result.py
    - tests/schemas/test_odds_trifecta.py
    - tests/schemas/test_payoff.py
  modified: []

key-decisions:
  - "ResultSchema: all 12 fields pre_race=False, finish_position Optional[int] for non-finishers per Pitfall #6"
  - "OddsTrifectaSchema: only race_id non-Optional, all trifecta data sparse (54.1%/0.1%/0.002% coverage)"
  - "PayoffSchema: contract schema for Phase 5/8, combo_1/2/3 non-Optional, odds as float not 0.1 units"

patterns-established:
  - "Pattern: Contract schema without data source -- PayoffSchema defines the interface for future phases"
  - "Pattern: Sparse Optional fields documented with coverage percentages in description"

requirements-completed: [DATA-01]

# Metrics
duration: 3min
completed: 2026-06-11
---

# Phase 1 Plan 02: Result, OddsTrifecta & Payoff Schema Summary

**ResultSchema (12 post-race fields), OddsTrifectaSchema (16 sparse trifecta odds fields from Kaggle odds.csv), and PayoffSchema (6-field contract for Phase 5/8) -- all fields pre_race=False, TDD-verified with 26 new tests**

## Performance

- **Duration:** 3 min
- **Started:** 2026-06-11T04:08:38Z
- **Completed:** 2026-06-11T04:12:26Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- ResultSchema defines 12 result-level columns: all post-race, finish_position Optional[int] for non-finishers (Pitfall #6)
- OddsTrifectaSchema defines 16 trifecta odds columns from odds.csv: only race_id non-Optional, documented sparse coverage rates
- PayoffSchema defines 6-field contract for Phase 5 (scraping) and Phase 8 (EV calculation): no direct Kaggle source
- Full TDD cycle (RED -> GREEN) for both tasks, all 45 schema tests pass across 5 test files
- 3 of 5 standard-layer table schemas now complete (race/entry from Plan 01, result/odds_trifecta/payoff from Plan 02)

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Add failing tests for ResultSchema** - `1c19735` (test)
2. **Task 1 GREEN: Implement ResultSchema with 12 post-race fields** - `802bb14` (feat)
3. **Task 2 RED: Add failing tests for OddsTrifectaSchema and PayoffSchema** - `3c70d7c` (test)
4. **Task 2 GREEN: Implement OddsTrifectaSchema and PayoffSchema** - `b1f8371` (feat)

_Note: TDD tasks have separate RED (test) and GREEN (implementation) commits_

## Files Created/Modified
- `src/schemas/result.py` - ResultSchema model with 12 post-race fields (finish_position, finish_note, finish_time, margin, corner_1-4, last_3f, prize_money)
- `src/schemas/odds_trifecta.py` - OddsTrifectaSchema model with 16 fields from Kaggle odds.csv (trifecta1/2/3 combos, odds, popularity)
- `src/schemas/payoff.py` - PayoffSchema contract model with 6 fields (race_id, combo_1/2/3, odds, payoff_amount)
- `tests/schemas/test_result.py` - 11 tests for ResultSchema
- `tests/schemas/test_odds_trifecta.py` - 8 tests for OddsTrifectaSchema
- `tests/schemas/test_payoff.py` - 7 tests for PayoffSchema

## Decisions Made
- ResultSchema: finish_position as Optional[int] to handle 1.1% null rate and non-finishers with special finish_note values (中/取/失/除/再) per Pitfall #6
- OddsTrifectaSchema: odds values kept as Optional[int] in 0.1-unit Kaggle format (not float) to match source data exactly
- PayoffSchema: odds stored as float (not 0.1 units) since this table will receive processed data from scraping, not raw Kaggle data
- PayoffSchema: combo_1/2/3 are non-Optional since every row represents a specific combination; odds/payoff_amount are Optional since not all combinations have payoff data

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- ResultSchema, OddsTrifectaSchema, PayoffSchema are complete and tested
- 3 of 5 standard-layer tables complete (race, entry, result, odds_trifecta, payoff)
- Remaining Phase 1 plans: audit function (Plan 03), column classification map (Plan 04), schema export (Plan 05)
- Phase 2 (Kaggle Pipeline) can use ResultSchema and OddsTrifectaSchema for CSV-to-Parquet conversion

## Self-Check: PASSED

All 6 files verified present. All 4 commits verified in git log.

---
*Phase: 01-data-schema-leak-audit*
*Completed: 2026-06-11*
