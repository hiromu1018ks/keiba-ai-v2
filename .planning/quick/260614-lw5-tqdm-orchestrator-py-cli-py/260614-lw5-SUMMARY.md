---
quick_id: 260614-lw5
description: "スクレイピング進捗表示を追加する（tqdm）。src/scraper/orchestrator.py と src/cli.py を変更。"
commit: 6714f87
commit_message: "feat(04): add tqdm progress bar to run_scrape"
date: 2026-06-14
---

# Quick Task 260614-lw5: tqdm progress bar for run_scrape

Added a tqdm progress bar to the scrape pipeline so an operator running a long
live batch sees live progress (count/%, rate, ETA) on stderr. Output-neutral:
the bar auto-hides under pytest capture, and `--no-progress` / `progress=False`
disable it entirely for log-file / CI use.

## What Changed

- **tqdm added as runtime dependency** (`pyproject.toml`): `"tqdm>=4.66"` placed
  right after `loguru>=0.7` (both observability libs).
- **`run_scrape` + `_fetch_and_parse` gain `progress: bool = True`** param.
  - When `progress=True`: the `refs` loop is wrapped with
    `tqdm(refs, desc="Scraping", unit="race", total=len(race_refs), file=sys.stderr)`.
    When `max_races` truncates, `postfix=f"smoke {max_races}/{len(race_refs)}"`
    is added so the bar explains why it stops short.
  - When `progress=False`: the plain `refs` list is iterated (no tqdm import
    exercised on this path).
  - `run_scrape` forwards `progress=progress` to `_fetch_and_parse` in BOTH the
    live and offline branches.
- **`keiba scrape` CLI gains `--no-progress` flag**: `is_flag=True`, forwards
  `progress=not no_progress` to `run_scrape`. Default (no flag) forwards
  `progress=True`.

## Files Touched

| File | Change |
|------|--------|
| `pyproject.toml` | Added `tqdm>=4.66` to runtime `dependencies` |
| `src/scraper/orchestrator.py` | `import sys` + `from tqdm import tqdm`; `progress: bool = True` on `run_scrape` and `_fetch_and_parse`; tqdm-wrapped loop with smoke postfix; docstring updates |
| `src/cli.py` | `--no-progress` flag on `scrape`; `no_progress: bool` param; `progress=not no_progress` kwarg; docstring note |
| `tests/scraper/test_orchestrator.py` | Added `progress=False` to all 5 existing `run_scrape(...)` calls; new `test_progress_flag_is_output_neutral` |
| `tests/test_cli.py` | Extended `test_scrape_calls_run_scrape_live_true` to assert `progress is True`; extended `test_scrape_help_exits_zero` to assert `--no-progress` in help; new `test_scrape_no_progress_flag_forwards_false` |

## Commit

- **Hash:** `6714f87`
- **Subject (verbatim):** `feat(04): add tqdm progress bar to run_scrape`
- **Files in commit:** exactly 5 (the source + test files only — no `.planning/` docs, no SUMMARY)

## Verification Results

All gates green before commit:

| Gate | Result |
|------|--------|
| `ruff check` (5 files) | All checks passed |
| `mypy src/scraper/orchestrator.py` | Clean (tqdm stubs installed via `types-tqdm`) |
| `mypy src/cli.py` | 1 pre-existing `pandas-stubs` warning at line 29 (out of scope — `import pandas` predates this task at the same line in HEAD) |
| `pytest tests/scraper/test_orchestrator.py tests/test_cli.py tests/scraper/test_end_to_end.py -v` | **27 passed, 1 skipped** (skipped = opt-in live smoke) |

### New / updated tests

- `test_orchestrator.py::test_progress_flag_is_output_neutral` (NEW) — runs the
  pipeline twice with fresh mocks, asserts both `progress=True` and
  `progress=False` produce a parsed list of length `len(two_race_refs) == 2`
  reaching `normalize_to_parquet`. Does NOT assert anything about tqdm's
  rendered text (out of scope).
- `test_cli.py::test_scrape_no_progress_flag_forwards_false` (NEW) — invokes
  `scrape ... --no-progress`, asserts `exit_code == 0`, `captured["progress"]
  is False`, `captured["live"] is True`.
- `test_cli.py::test_scrape_calls_run_scrape_live_true` (EXTENDED) — now asserts
  `captured["progress"] is True` for the default (no flag) invocation.
- `test_cli.py::test_scrape_help_exits_zero` (EXTENDED) — now asserts
  `"--no-progress" in result.output`.

## Deviations from Plan

**1. [Rule 2 - Auto-add missing critical functionality] Installed `types-tqdm`**
- **Found during:** Task 1 mypy gate
- **Issue:** `mypy src/scraper/orchestrator.py` reported
  `Library stubs not installed for "tqdm" [import-untyped]` on the new
  `from tqdm import tqdm` import — this is a new error introduced by this
  task's changes, blocking the plan's "mypy pass clean" success criterion.
- **Fix:** `pip install types-tqdm` (the stub package mypy itself recommends).
  This is the type-checking analogue of the runtime `tqdm` install, not a
  scope expansion. Re-ran mypy: orchestrator.py now clean.
- **Files affected:** none in the commit (dev-dep only, no code change).

**Pre-existing (out of scope, NOT fixed per scope-boundary rule):** mypy also
reports 10 errors in `src/schemas/audit.py`, `src/scraper/normalizer.py`,
`src/scraper/enumeration.py`, `src/scraper/fetcher.py`, and `src/cli.py:29`
(pandas import) — all pre-date this task (verified: `git show HEAD:src/cli.py`
has the identical pandas import at line 29). These are unrelated to tqdm and
were left untouched.

## Environment Notes

- tqdm runtime package installed via `pip install 'tqdm>=4.66'` (no poetry /
  no lockfile in this repo). The `pyproject.toml` change makes the dependency
  declarative regardless of how it lands in the venv.
- `types-tqdm` installed as a dev-side type stub (not committed to
  pyproject.toml's dev extra — that would be a separate scope decision; it
  lives in the env so mypy resolves).

## Self-Check: PASSED

- Commit `6714f87` exists: `git log --oneline | grep 6714f87` OK.
- All 5 files modified in commit (no extras, no deletions).
- tqdm import resolves: `python -c "from tqdm import tqdm"` OK.
- All affected tests green (27 passed, 1 skipped).
