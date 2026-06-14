# Phase 04 Deferred Items

Out-of-scope discoveries logged during plan execution. These are pre-existing
issues in prior-wave files (Plans 04-01 through 04-05), NOT caused by the
current plan's changes. Per the executor's SCOPE BOUNDARY rule, they are logged
here rather than fixed.

## Discovered during Plan 04-06

### ruff (pre-existing, in prior-wave files)

| File | Code | Detail |
|------|------|--------|
| `src/scraper/flag_crosswalk.py:189` | F822 | `__all__` lists `GRADE_PATTERNS` but the name is undefined. Plan 04-01 (Task 1, commit 87539b0). |
| `tests/scraper/test_enumeration.py:16` | F401 | `pytest` imported but unused. Plan 04-02 (commit 3fe5dd2). |
| `tests/scraper/test_enumeration.py:29` | F821 | Undefined name `Callable` (import is `typing.Callable`, used unqualified). Plan 04-02. |
| `tests/scraper/test_enumeration.py:37` | F401 | `typing.Callable` imported but unused. Plan 04-02. |
| `tests/scraper/test_enumeration.py:265` | F841 | Local variable `bad_day_url` assigned but never used. Plan 04-02. |

These were emitted by `ruff check src/scraper tests/scraper` on the main branch
BEFORE Plan 04-06's changes (verified via `git stash` + mypy/ruff re-run).
None are caused by Plan 04-06's new files (`src/scraper/orchestrator.py`,
`src/scraper/__init__.py`, `tests/scraper/test_end_to_end.py`,
`tests/scraper/test_orchestrator.py`) -- all of which pass ruff cleanly.

The Plan 04-06 Task 3 acceptance criterion "`ruff check src/scraper tests/scraper`
exits 0" is therefore unachievable without modifying prior-wave code, which the
SCOPE BOUNDARY forbids. Recommended follow-up: a small lint-only cleanup PR
that fixes the 5 prior-wave ruff errors. These are trivial (unused imports /
__all__ typo / unused local var) and carry no behavioral risk.

### mypy (pre-existing, in prior-wave files)

`mypy src/scraper` reports 9 errors in 4 prior-wave files
(`normalizer.py`, `enumeration.py`, `fetcher.py`, plus 1 import-untyped stub
note). Verified pre-existing via `git stash` + `mypy` re-run. None caused by
Plan 04-06's new files (both of which mypy-clean).

| File | Line | Code | Detail |
|------|------|------|--------|
| `src/schemas/audit.py` | 21 | import-untyped | pandas stubs not installed (affects the whole project, not scraper-specific) |
| `src/scraper/normalizer.py` | 71 | import-untyped | pandas stubs (same as above) |
| `src/scraper/normalizer.py` | 586 | index | `_recast_for_storage` indexes SCHEMA_DTYPE_MAP with a `ModelMetaclass` (Plan 04-05) |
| `src/scraper/enumeration.py` | 86, 133 | assignment | `anchor["href"]` typed as `str | AttributeValueList` (Plan 04-02) |
| `src/scraper/fetcher.py` | 114-117 | attr-defined | `self._pw = sync_playwright().start()` -- mypy sees `self._pw` as None (Plan 04-03) |

The pandas-stubs note is global (would touch pyproject optional-dependencies
to install pandas-stubs). The remaining 5 errors are pre-existing type
narrowing gaps. Plan 04-06's `mypy src/scraper` acceptance criterion "exits 0"
is similarly unachievable without touching prior-wave files or the global
type-stubs config. Recommended follow-up: either install `pandas-stubs` and
fix the 5 type gaps in a small PR, or relax the acceptance criterion in
future plans to "no NEW mypy errors introduced by this plan's files" (which
Plan 04-06 satisfies).
