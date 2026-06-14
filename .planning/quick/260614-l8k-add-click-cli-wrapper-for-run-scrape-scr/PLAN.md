---
status: complete
type: quick
quick_id: 260614-l8k
---

# Quick Task: click CLI wrapper for run_scrape (scrape/status subcommands)

**Goal:** Wrap `src/scraper.run_scrape()` with a click 8.x CLI to improve Phase 04
operability. Pure wrapper — no scraper internals touched.

## Scope

1. `src/cli.py` — click group with two subcommands:
   - `scrape`: calls `run_scrape(...)` with `live=True`. Options `--start`,
     `--end` (YYYY-MM-DD → `datetime.date`, required), `--max-races` (int, opt),
     `--raw-dir` / `--standard-dir` (opt, default = orchestrator's
     `DEFAULT_RAW_DIR` / `DEFAULT_STANDARD_DIR`). Echoes `{race, entry, result}`
     output-path counts on completion.
   - `status`: aggregates `data/standard/scraped/**/*.parquet` via pandas.
     Shows race/entry/result total rows, per-YYYYMM file counts, per-YYYYMM race
     row counts, `race_date` min~max. Prints `no scraped data yet` when empty.
2. `pyproject.toml` — add `keiba` console-script entry + `click>=8,<9` dep.
3. `tests/test_cli.py` — `CliRunner` tests, no network, `run_scrape`
   monkeypatched.

## Key facts (verified against code)

- `run_scrape(start_date, end_date, raw_dir=DEFAULT_RAW_DIR,
  standard_dir=DEFAULT_STANDARD_DIR, live=False, max_races=None, fetch_html=None)`
  → `dict[str, list[Path]]` with keys `race`/`entry`/`result`.
- `DEFAULT_RAW_DIR = Path("data/raw/netkeiba")`,
  `DEFAULT_STANDARD_DIR = Path("data/standard")` (orchestrator.py).
- Output layout: `{standard_dir}/scraped/{YYYYMM}/{race,entry,result}.parquet`.
- `race.parquet` has a string `race_date` column; entry/result do not.

## Decisions

- **D1 (deviation from literal spec):** pyproject uses PEP 621 `[project]` +
  setuptools backend (NOT poetry). The spec's `[tool.poetry.scripts]` would be
  inert under this backend and would NOT create the `keiba` command. Use
  `[project.scripts]` (`keiba = "src.cli:main"`) — the only form that makes the
  stated manual command `keiba scrape ...` work. Flagged to user.
- **D2:** `status` reads its root from the imported `DEFAULT_STANDARD_DIR` global
  (`/ "scraped"`). The no-files test monkeypatches `src.cli.DEFAULT_STANDARD_DIR`
  to a tmp_path — no new CLI option needed, honors spec exactly.
- **D3:** loguru INFO inside `run_scrape` already writes to stderr by default; no
  logging config added (spec: "追加のログ設定は不要").

## Constraints

- Do not modify `src/scraper/*.py` (public API or implementation).
- Wrap only. No offline exposure (CLI is live-only; `live=False` test-only).
- Mac / Python 3.12+; existing `tests/scraper/` stays green; ruff + mypy clean.
- No real network in tests (monkeypatch only).

## Commit

Atomic single commit:
`feat(04): add click CLI wrapper for run_scrape (scrape/status subcommands)`
