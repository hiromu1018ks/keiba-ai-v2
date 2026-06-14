---
phase: quick-260614-mfq
plan: 01
subsystem: scraper
tags: [scraper, observability, tqdm, ux, enumeration]
requires:
  - quick-260614-lw5 (run_scrape race-fetch tqdm bar + tqdm runtime dep)
provides:
  - enumerate_races(progress) per-month tqdm bar on stderr
  - run_scrape threading progress into enumerate_races at both call sites
affects:
  - src/scraper/enumeration.py
  - src/scraper/orchestrator.py
  - tests/scraper/test_enumeration.py
  - tests/scraper/test_orchestrator.py
tech-stack:
  added: []
  patterns:
    - "stderr-streamed tqdm bar with auto-hide under non-TTY (same pattern as the race-fetch bar)"
key-files:
  created: []
  modified:
    - src/scraper/enumeration.py
    - src/scraper/orchestrator.py
    - tests/scraper/test_enumeration.py
    - tests/scraper/test_orchestrator.py
decisions:
  - "Precompute the (year, month) list up front (behavior-preserving refactor of the while-loop) so tqdm gets a real total and the iteration order is identical"
  - "tqdm writes to sys.stderr (same stream loguru uses) and auto-hides under pytest capture / non-TTY, keeping tests output-neutral"
  - "Default progress=True is the user-facing UX; tests opt out via progress=False"
metrics:
  duration: ~12m
  completed: 2026-06-14
---

# Phase quick-260614-mfq Plan 01: tqdm enumerate_races progress bar Summary

Surfaced the previously-silent ~18-minute, 53-month calendar enumeration phase with a per-month tqdm bar on stderr -- a pure UX/observability change that is byte-for-byte output-identical at the RaceRef level.

## What Changed

### `src/scraper/enumeration.py`
- Added `import sys` and `from tqdm import tqdm` to the module imports.
- `enumerate_races` gained a `progress: bool = True` parameter (last position, backward-compatible).
- The outer month loop was refactored: the previous `while cursor <= end_month_anchor:` loop is now a PRECOMPUTED `months: list[tuple[int, int]]` built with IDENTICAL cursor-advancement logic (start at `datetime.date(start_date.year, start_date.month, 1)`, advance month-by-month, stop past end_date's month). `total = len(months)`.
- The loop is now `for year, month in (tqdm(months, desc="Enumerating", unit="month", total=total, file=sys.stderr) if progress else months):`. The `year, month = cursor.year, cursor.month` line was deleted (loop var binding replaces it).
- The loop body (per-month `enumerate_race_day_urls`, boundary date filter, per-day `enumerate_races_for_day`, dedup via `seen_ids`) is byte-for-byte unchanged.
- Docstring updated to document the `progress` parameter (mirrors run_scrape's wording).

### `src/scraper/orchestrator.py`
- `run_scrape` already had `progress: bool = True` (from quick-task 260614-lw5) and already imported `tqdm` + `sys`.
- Both `enumerate_races` call sites now pass `progress=progress`:
  - Live branch (~line 146): `enumerate_races(start_date, end_date, enum_transport, progress=progress)`.
  - Offline branch (~line 159): `enumerate_races(start_date, end_date, fetch_html, progress=progress)`.
- The existing race-fetch tqdm bar and `_fetch_and_parse` threading are untouched.

### `tests/scraper/test_enumeration.py`
- Added `progress=False` to all 7 `enumerate_races(...)` calls in `TestEnumerateRaces` (test_traverses_three_levels, test_deduplicates_across_days, test_filters_by_date_range, test_boundary_end_date_inclusive, test_handles_fetch_none_gracefully, test_returns_race_refs_not_strings, test_multi_month_traversal).
- Added `test_progress_flag_is_output_neutral`: builds the same multi-month table as test_multi_month_traversal, creates TWO independent fakes from it (so each call records its own `.seen`), calls `enumerate_races(..., progress=False)` and `enumerate_races(..., progress=True)`, asserts identical `(race_id, race_date)` output lists. Does NOT capture stderr or assert on tqdm rendering.

### `tests/scraper/test_orchestrator.py` (Rule 1 deviation — see below)
- `_capture_transport` mock side-effect gained `**kwargs` to absorb the new `progress` kwarg that `run_scrape` now passes to `enumerate_races`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed enumerate_races mock side-effect signature in test_orchestrator.py**
- **Found during:** Task 2 verification (full pytest gate)
- **Issue:** The plan's context claimed "test_orchestrator.py and test_end_to_end.py MOCK enumerate_races (patch), so they are unaffected by the real signature change." This was incorrect for ONE mock: `TestRunScrape.test_live_false_with_injected_fetch_html_runs_offline` uses `mock_enum.side_effect = _capture_transport` where `_capture_transport(start, end, transport)` had a positional-only signature. After Task 2 added `progress=progress` to the offline enumerate_races call site, the mock received an unexpected `progress` kwarg and raised `TypeError: _capture_transport() got an unexpected keyword argument 'progress'`.
- **Fix:** Added `**kwargs` to `_capture_transport`'s signature so it absorbs the new kwarg. Behavior-preserving: the test still asserts the captured transport identity and the fetch_callable routing, none of which depend on the `progress` kwarg.
- **Files modified:** tests/scraper/test_orchestrator.py (1-line change)
- **Commit:** 6960111 (included in the same atomic commit per "do not commit red")

Note: The execution_notes said to stage only 3 files, but the verification gate required tests/scraper/test_orchestrator.py to be green, and my Task 2 change broke it. Rule 1 (auto-fix bugs directly caused by the current task's changes) took precedence over the file-count constraint. The 4th file is a 1-line `**kwargs` fix directly necessitated by my orchestrator change.

## Verification Results

All gates green:

- `ruff check src/scraper/enumeration.py src/scraper/orchestrator.py tests/scraper/test_orchestrator.py` -> All checks passed! (test_enumeration.py has 4 PRE-EXISTING ruff errors on lines not touched by this task: unused `pytest` import, `Callable` undefined name, unused `typing.Callable` import, unused `bad_day_url` -- all confirmed present on the unmodified baseline.)
- `mypy src/scraper/enumeration.py src/scraper/orchestrator.py` -> 2 errors on enumeration.py lines 106 & 160, both PRE-EXISTING BS4 typing issues (`anchor["href"]` returns `str | AttributeValueList`), confirmed present on the unmodified baseline at lines 104 & 158. No NEW mypy errors introduced.
- `python -m pytest tests/scraper/test_enumeration.py tests/scraper/test_orchestrator.py tests/scraper/test_end_to_end.py -q` -> 43 passed, 1 skipped.

Pre-existing error baselines (verified via `git stash` + re-run on clean main): ruff=4 errors (all in test_enumeration.py, untouched lines), mypy=2 errors (enumeration.py BS4 typing, untouched lines). This commit introduces ZERO new ruff or mypy errors.

## Commits

- `6960111`: feat(04): add tqdm progress bar to enumerate_races

## TDD Gate Compliance

This task was marked `tdd="true"` in the plan. The plan's `<action>` blocks did not prescribe a strict RED/GREEN commit split (the behavior is a pure UX refactor with a new flag, and the verification gate is a single green test suite run). The output-neutrality test (`test_progress_flag_is_output_neutral`) was written as part of Task 3 and passes in the same commit. A warning is logged here for transparency: there is no separate `test(...)` RED commit preceding the `feat(...)` GREEN commit -- implementation and test landed atomically. This matches the pattern of the predecessor quick-task 260614-lw5 (same author, same repo convention for small UX refactor quick-tasks).

## Self-Check: PASSED

- [x] `src/scraper/enumeration.py` exists and has `progress: bool = True` param + tqdm wrapper.
- [x] `src/scraper/orchestrator.py` passes `progress=progress` at both enumerate_races call sites.
- [x] `tests/scraper/test_enumeration.py` has `progress=False` on all 7 calls + new neutrality test.
- [x] Commit `6960111` exists in git log.
- [x] All verification gates green (ruff clean on new code, mypy no new errors, pytest 43 passed/1 skipped).
