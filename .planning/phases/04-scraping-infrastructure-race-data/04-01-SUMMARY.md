---
phase: 04-scraping-infrastructure-race-data
plan: 01
subsystem: scraper
tags: [scaffold, dependencies, package-init]
requires:
  - SCRP-01
  - D-02 (Playwright + BS4 + lxml)
provides:
  - "src/scraper import-safe empty package marker (Plans 02-06 add submodules here)"
  - "tests/scraper test package with shared conftest fixtures (tmp_raw_dir, tmp_standard_dir, golden_html_dir)"
  - "pyproject.toml runtime deps: playwright>=1.49, beautifulsoup4>=4.12, lxml>=5.0"
affects:
  - "Plans 02-06 import src.scraper and consume tests/scraper/conftest.py fixtures"
  - "Phase 5 (Trifecta Odds) will reuse the same scraping infrastructure"
tech-stack:
  added:
    - "playwright>=1.49 (1.60.0 installed) — HTML fetching for netkeiba"
    - "beautifulsoup4>=4.12 (4.15.0 installed) — HTML parsing"
    - "lxml>=5.0 (6.1.1 installed) — fast parser backend for BS4"
  patterns:
    - "Import-safe empty package __init__ (HIGH #3): __init__.py has no submodule imports and no __all__ until Plan 06 wires re-exports"
    - "tmp_path-based conftest fixtures (no real data/ paths): hermetic test isolation"
key-files:
  created:
    - src/scraper/__init__.py
    - tests/scraper/__init__.py
    - tests/scraper/conftest.py
  modified:
    - pyproject.toml
decisions:
  - "src/scraper/__init__.py ships as an import-safe EMPTY marker for 4 waves (Plans 02-05); public re-exports are added only in Plan 06 (final integration). This fixes Codex Review HIGH #3: eager submodule imports would block Plans 02/03 from importing their own not-yet-created submodules."
  - "playwright/beautifulsoup4/lxml declared as runtime deps in the main dependencies list (NOT a dev extra) per D-02."
  - "Task 2 install is recorded as machine state (per threat model T-04-02), not a tracked code change. Versions: playwright 1.60.0, beautifulsoup4 4.15.0, lxml 6.1.1."
metrics:
  duration: ~78s
  completed: 2026-06-13
  tasks: 2
  files: 4
---

# Phase 04 Plan 01: Scraper Package Skeleton & Dependency Setup Summary

`src/scraper` パッケージを import-safe 空マーカーとして作成し、Playwright/BS4/lxml を runtime dependency として `pyproject.toml` に宣言した。Codex Review HIGH #3（eager import が後続 plan をブロック）を解決。

## What Was Built

### Task 1: パッケージスケルトン + 依存関係宣言 (`13496ab`)

**`src/scraper/__init__.py`** — import-safe 空パッケージマーカー。モジュール docstring とサブモジュール予定地のコメントのみ。`__all__` なし、submodule import なし。Plan 06 で公開 API の re-export を追加するまでこの状態を維持する。

**`tests/scraper/__init__.py`** — 空のテストパッケージマーカー（`tests/pipeline/__init__.py` と同じ形式）。

**`tests/scraper/conftest.py`** — Plan 02-06 が消費する3つの共有 fixture を定義。全て `tmp_path` 由来（`golden_html_dir` だけ repo-relative）で hermetic:
- `tmp_raw_dir` → `(tmp_path / "data" / "raw" / "netkeiba")`。Fetcher が `{YYYY}/{MM}/{race_id}.html` に合成するルート。
- `tmp_standard_dir` → `(tmp_path / "data" / "standard")`。
- `golden_html_dir` → repo-relative `tests/scraper/fixtures/html/`。Plan 04 Task 3 のヒューマン checkpoint で HTML を保存し、Plan 04/06 のテストが読み込む。

**`pyproject.toml`** — `dependencies` リストに `"playwright>=1.49"`, `"beautifulsoup4>=4.12"`, `"lxml>=5.0"` を追加（`pyarrow>=14.0` の直後）。これらは runtime dep（D-02）であり dev extra には入れない。

### Task 2: 依存関係インストール + Chromium バイナリ検証

`pip install -e .` で3つの新しい runtime dep をインストール。バージョン:
- `playwright` 1.60.0
- `beautifulsoup4` 4.15.0（`soupsieve` 2.8.4 も自動導入）
- `lxml` 6.1.1

`python -m playwright install chromium` を実行し Chromium バイナリを取得。以下がダウンロード完了済み:
- `chromium-1223`（フル Chromium）
- `chromium_headless_shell-1223`（ヘッドレスシェル — fetcher が使用）
- `ffmpeg-1011`

キャッシュパス: `~/Library/Caches/ms-playwright/`

`python -c "from playwright.sync_api import sync_playwright; from bs4 import BeautifulSoup; import lxml"` が exit 0 で全依存関係インポート成功。

## Deviations from Plan

None — 計画通りに実行。Codex Review HIGH #3（import-safe `__init__.py`）と MEDIUM（`pyproject.toml` 経由でインストール、bare `pip install` なし）の両方を計画通りに対応した。

## Verification Results

全ての plan-level verification（`<verification>` ブロック）が PASSED:

| Check | Result |
|-------|--------|
| `python -c "import src.scraper"` exits 0 | OK |
| `grep -E "from src\.scraper\.(fetcher\|parser\|normalizer)" src/scraper/__init__.py` returns nothing | OK (no matches) |
| `grep -c "playwright" pyproject.toml` >= 1 | OK (count=1) |
| `python -c "from playwright.sync_api import sync_playwright; from bs4 import BeautifulSoup; import lxml"` exits 0 | OK |

### Task 1 acceptance criteria（全て PASSED）

- `python -c "import src.scraper"` exits 0 — OK
- `grep -E "from src\.scraper\.(fetcher|parser|normalizer)" src/scraper/__init__.py` returns no matches — OK
- `grep -c "__all__" src/scraper/__init__.py` returns 0 — OK
- pyproject.toml contains `"playwright>=1.49"`, `"beautifulsoup4>=4.12"`, `"lxml>=5.0"` — OK
- `python -c "from tests.scraper.conftest import tmp_raw_dir, tmp_standard_dir, golden_html_dir"` does not raise — OK
- `ls tests/scraper/__init__.py tests/scraper/conftest.py` exits 0 — OK

### Task 2 acceptance criteria（全て PASSED）

- `python -c "from playwright.sync_api import sync_playwright"` exits 0 — OK
- `python -c "from bs4 import BeautifulSoup"` exits 0 — OK
- `python -c "import lxml"` exits 0 — OK
- `pip show playwright beautifulsoup4 lxml` lists all three installed — OK (versions recorded above)
- `python -m playwright install chromium` succeeded — OK

## Authentication Gates

None occurred.

## Threat Model Verification

| Threat | Disposition | Status |
|--------|-------------|--------|
| T-04-01 (pip install playwright/bs4/lxml tampering) | mitigate | Pre-verified [OK] in RESEARCH.md Package Legitimacy Audit. Microsoft publishes playwright (~4M/mo DLs); bs4/lxml are 18-year-old projects. All installed from declared pyproject versions via `pip install -e .` (no bare `pip install <pkg>`). |
| T-04-SC (pip supply chain) | mitigate | All three packages pre-verified [OK]; no [ASSUMED]/[SUS]/[SLOP] packages. |
| T-04-02 (Chromium binary tampering) | mitigate | Microsoft-published Chromium build from playwright CDN; verified by Playwright at launch. Downloaded successfully to `~/Library/Caches/ms-playwright/`. |

## Reproducibility Notes (machine state — T-04-02)

Next-machine setup:
```bash
pip install -e .                          # installs playwright, beautifulsoup4, lxml
python -m playwright install chromium     # downloads Chromium + headless shell + ffmpeg
```

Versions at this machine (2026-06-13):
- playwright 1.60.0
- beautifulsoup4 4.15.0
- lxml 6.1.1
- Chromium 148.0.7778.96 (playwright build chromium-1223)

## Commits

- `13496ab` — chore(04-01): scaffold import-safe src/scraper package and declare deps
- Task 2 produces machine state only (no tracked files modified); no separate commit per the plan's threat model T-04-02 ("machine state, not reproducible config").

## Self-Check: PASSED

Created files exist:
- FOUND: src/scraper/__init__.py
- FOUND: tests/scraper/__init__.py
- FOUND: tests/scraper/conftest.py

Modified file contains expected deps:
- FOUND: "playwright>=1.49", "beautifulsoup4>=4.12", "lxml>=5.0" in pyproject.toml

Commit exists:
- FOUND: 13496ab (git log --oneline)
