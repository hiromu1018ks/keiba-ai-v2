---
status: complete
type: quick
quick_id: 260614-l8k
slug: add-click-cli-wrapper-for-run-scrape-scr
date: 2026-06-14
---

# Summary: click CLI wrapper for run_scrape

## Outcome

Added a thin click 8.x CLI (`src/cli.py`) wrapping `run_scrape()`, plus a
`status` aggregator and a `keiba` console-script entry point. Scraper internals
untouched.

## Deliverables

- `src/cli.py` — click group `main` with two subcommands:
  - `scrape --start --end [--max-races] [--raw-dir] [--standard-dir]` →
    `run_scrape(..., live=True, ...)`; echoes per-table output-path counts.
  - `status` → pandas aggregation of `data/standard/scraped/**/*.parquet`
    (per-table totals, per-YYYYMM file + race-row counts, race_date min~max);
    prints `no scraped data yet` when empty.
- `pyproject.toml` — added `click>=8,<9` dep + `keiba` console-script entry.
- `tests/test_cli.py` — 7 tests via `CliRunner`, no network, `run_scrape`
  monkeypatched.

## Verification (all green)

- `ruff check` / `ruff format --check` — clean.
- `pytest tests/test_cli.py` — 7 passed.
- `pytest` (full suite) — 455 passed, 1 skipped (was 448+1 before; +7 new).
- `mypy` — no new type errors. Only noise is the repo-wide `pandas` stub gap
  (`Library stubs not installed for "pandas"`), identical to pre-existing
  `src/scraper/normalizer.py:72` and `src/schemas/audit.py:21`. CLI logic is
  type-clean.
- Manual smoke: `python -m src.cli status` reads real `202306` data
  (race=3 entry=37 result=37, race_date 2023-06-25~2023-06-25).

## Decision: D1 (deviation from literal spec) — IMPORTANT

Spec said add to `[tool.poetry.scripts]`. The repo's `pyproject.toml` uses
**PEP 621 `[project]` + setuptools** backend (no `[tool.poetry.*]` section at
all). A `[tool.poetry.scripts]` entry would be **inert under setuptools** and
would NOT register the `keiba` command — defeating the stated goal of running
`keiba scrape --start ... --end ...`. Used the correct standard form:

```toml
[project.scripts]
keiba = "src.cli:main"
```

This is the only deviation; flagged to user for awareness.

## Constraints honored

- `src/scraper/*.py` public API and implementation: unchanged (import-only).
- Wrap-only; CLI is live-only (offline/test path not exposed).
- Loguru INFO inside `run_scrape` flows to stderr unchanged (no log config added).
- Mac / Python 3.12.13; click 8.4.1.
- No real network in tests (monkeypatch only).

## Next (manual, out of scope)

After install (`pip install -e .`), run:
`keiba scrape --start 2022-01-01 --end 2024-12-31`
