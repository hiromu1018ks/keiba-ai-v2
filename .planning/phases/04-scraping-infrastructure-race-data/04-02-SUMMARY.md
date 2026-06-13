---
phase: 04-scraping-infrastructure-race-data
plan: 02
subsystem: scraper
tags: [enumeration, calendar, url-absolutization, race-validation]
requires:
  - SCRP-01
  - SCRP-02
  - 04-01 (src/scraper/__init__.py import-safe marker)
provides:
  - "src/scraper/models.RaceRef — frozen dataclass (race_id, race_date)"
  - "src/scraper/enumeration — 3-level calendar traversal (month -> day -> race), race_id validation, Cycle-2 #1 URL absolutization"
  - "tests/scraper/test_enumeration.py — 18 tests across 4 classes covering traversal, validation, dedup, None-fetch, date-range filtering, URL absolutization"
affects:
  - "Plan 03 (fetcher) consumes RaceRef.race_date for raw HTML {YYYY}/{MM} path derivation"
  - "Plan 03 (fetcher) implements the fetch_html: Callable[[str], Optional[str]] contract that enumeration depends on"
  - "Plan 04 (parser) reads the same race-day HTML pages that enumerate_races_for_day discovers"
  - "Plan 06 (orchestrator) wires enumerate_races into run_scrape with the injected fetch boundary"
tech-stack:
  added: []
  patterns:
    - "Frozen dataclass for immutable value records (RaceRef) — lightweight alternative to Pydantic BaseModel"
    - "Dependency-injected fetch_html callable — enumeration never launches a browser (lifecycle owned by Plan 03 FetcherSession)"
    - "urllib.parse.urljoin(BASE_URL, href) for relative->absolute URL absolutization (Cycle-2 #1)"
    - "re.fullmatch(r'\\d{12}', race_id) for strict 12-digit validation before RaceRef construction (T-04-03)"
key-files:
  created:
    - src/scraper/models.py
    - src/scraper/enumeration.py
    - tests/scraper/test_enumeration.py
  modified: []
decisions:
  - "RaceRef is a stdlib frozen dataclass (NOT Pydantic) — it is a plain typed pair with no validation logic; Pydantic overhead is reserved for the standard-layer schemas in src/schemas/."
  - "Extraction regex _RACE_HREF_RE is \\d+ (variable-length numeric), NOT \\d{12}. This lets the malformed-ID warning branch fire for 10/13-digit IDs; the strict 12-digit check is delegated to _RACE_ID_RE.fullmatch. Non-numeric segments (/race/list/, /race/result/) are intentionally NOT matched because they are legitimate non-race links, not malformed race IDs."
  - "loguru warnings are captured in tests via a local loguru sink (logger.add(sink, level='WARNING')); loguru does not route through stdlib logging by default so pytest caplog cannot see it without an interceptor."
metrics:
  duration: 197s
  completed: 2026-06-14
  tasks: 2
  files: 3
---

# Phase 04 Plan 02: Race Enumeration & URL Absolutization Summary

netkeibaカレンダーページから3段階（月→開催日→レース）でレースを列挙するパイプラインを実装した。各レースは `RaceRef(race_id, race_date)` として返され、race_date が raw HTML パス `{YYYY}/{MM}` の唯一の真実源。Cycle-2 HIGH #1（相対URL絶対化）を `urljoin(BASE_URL, href)` で解決し、Playwright が受け取る全URLが絶対であることを保証した。

## What Was Built

### Task 1: RaceRef model + 3-level calendar enumeration (`e463061`)

**`src/scraper/models.py`** — `@dataclass(frozen=True)` の `RaceRef(race_id: str, race_date: datetime.date)`。race_date が raw HTML パス `{YYYY}/{MM}` の唯一の真実源であり、`race_id[4:6]` は JRA のコースコード（YYYYPPCCDDRR）であって月ではないという不変量を docstring で明文化。Pydantic ではなく stdlib dataclass を採用（バリデーションロジックを持たない軽量な値型のため）。

**`src/scraper/enumeration.py`** — 依存性注入設計の3段階走査モジュール。`fetch_html: Callable[[str], Optional[str]]` を注入可能で、enumeration 自身はブラウザを起動しない（ライフサイクルは Plan 03 FetcherSession が所有、T-04-04）。

公開シンボル:
- `BASE_URL = "https://db.netkeiba.com"` — urljoin の絶対オリジン
- `parse_calendar_month_html(html)` — 月カレンダー → 絶対化された `(day_url, race_day_date)` リスト。`urljoin(BASE_URL, href)` で相対パス `/race/list/{8d}/` を絶対化（Cycle-2 #1）
- `parse_race_day_html(html, race_day_date)` — 開催日ページ → `list[RaceRef]`。`re.fullmatch(r"\d{12}", race_id)` で検証、不正IDは警告してドロップ（T-04-03）。race_date は day 引数から取得（race_id からではない）
- `enumerate_race_day_urls(year, month, fetch_html)` — 1月分のカレンダー取得・パース。fetch_html=None は空リスト（例外なし）
- `enumerate_races_for_day(day_url, race_day_date, fetch_html)` — 1開催日のレース取得。相対URLの防御的修復付き（`not day_url.startswith("http")` → `urljoin(BASE_URL, day_url)`）
- `enumerate_races(start_date, end_date, fetch_html)` — 全期間走査。境界フィルタ付き（D-05 の 2026-05-31 カットオーネ対応）、race_id で重複排除

### Task 2: 包括的テストスイート (`3fe5dd2`)

**`tests/scraper/test_enumeration.py`** — 18テスト / 4クラス。全てダミー `fetch_html`（絶対URL→HTMLの dict）を使用、実Playwrightなし。fake のキーが絶対URLなので、enumeration が相対URLを要求すると fake が None を返してテストが失敗する — これが Cycle-2 #1 を暗黙に強制する。

- `TestParseCalendarMonthHtml` (4 tests): day link 抽出、**Cycle-2 #1 絶対化検証**（`test_day_urls_are_absolute`）、空カレンダー→[]、重複リンク排除
- `TestParseRaceDayHtml` (3 tests): RaceRef 抽出、**Cycle-1 HIGH #1**（race_date は day 引数由来、race_id[0:8] と意図的に異なる日付で検証）、不正ID ドロップ＆警告確認
- `TestEnumerateRaces` (10 tests): 3段階走査、重複排除、日付範囲フィルタ、**境界 2026-05-31 包含**、None-fetch 耐性、RaceRef 型確認、**Cycle-2 #1 防御的修復**（`test_repair_relative_day_url`）、カレンダー None、複数月走査
- `TestRaceIdValidation` (2 tests): fullmatch 直接検証、parse 内ドロップ

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `_RACE_HREF_RE` が厳密すぎて不正ID警告がデッドコードだった**
- **Found during:** Task 2 テスト実行時（`test_drops_malformed_race_ids` 失敗）
- **Issue:** 当初の抽出 regex `/race/(\d{12})/` は12桁のみ一致。そのため `/race/2022010501/`（10桁）や `/race/2022010501011/`（13桁）が regex に一致せず、`_RACE_ID_RE.fullmatch()` の検証・警告ブランチに到達しなかった（到達不能なデッドコード）。T-04-03 の「不正ID を警告してドロップ」が実質機能していなかった。
- **Fix:** regex を `/race/(\d+)/?` に緩和（可変長数値セグメント）。10/13桁の数値IDが検証ブランチに入り警告される。非数値セグメント（`/race/list/`, `/race/result/` 等）は正規の非レースリンクなので意図的に非一致とする。
- **Files modified:** src/scraper/enumeration.py
- **Commit:** `3fe5dd2`

**2. [Rule 3 - Blocking] loguru 警告が pytest caplog で捕捉できない**
- **Found during:** Task 2 `test_drops_malformed_race_ids` のアサーション失敗
- **Issue:** loguru は独自のシンクシステムを使用し stdlib logging を経由しないため、pytest 標準 `caplog` fixture で `logger.warning` を捕捉できない。当初 stdlib `_InterceptHandler` で橋渡しを試みたが loguru のレコード形式が stdlib と非互換で失敗。
- **Fix:** テスト内で `loguru_logger.add(sink, level="WARNING")` で直接リスト収集シンクを取り付け、finally で `remove(handler_id)`。stdlib logging 経由を完全に回避。
- **Files modified:** tests/scraper/test_enumeration.py（実装側の変更は不要）
- **Commit:** `3fe5dd2`

## Verification Results

plan-level `<verification>` ブロックは全て PASSED:

| Check | Result |
|-------|--------|
| `pytest tests/scraper/test_enumeration.py -x -q` passes | OK (18 passed) |
| `python -c "from src.scraper.models import RaceRef; ..."` exits 0 | OK |
| `grep -n "race_id\[4:6\]" src/scraper/` returns nothing executable | OK (docstring/comment のみ — 実行可能なスライス演算なし) |
| `grep -n "urljoin" src/scraper/enumeration.py` returns >= 2 matches | OK (12 matches) |

### Task 1 acceptance criteria（全て PASSED）

- `RaceRef` は frozen dataclass、フィールドは `race_id: str`, `race_date: datetime.date` のみ — OK
- `BASE_URL` は `https://db.netkeiba.com` で開始 — OK
- `enumerate_races` シグネチャ `(start_date, end_date, fetch_html) -> list[RaceRef]` — OK
- `enumerate_race_day_urls` と `enumerate_races_for_day` は別関数 — OK
- `race_id` 検証は `re.fullmatch(r"\d{12}", race_id)` — OK
- 実行可能な `race_id[4:6]` スライスなし — OK
- `urljoin` が2箇所以上 — OK（12箇所）
- Cycle-2 #1: `parse_calendar_month_html` の全 day_url が `https://` で開始 — OK
- `enumeration.py` に `sync_playwright` import なし — OK
- `enumerate_races` が `[start_date, end_date]` で day を包含フィルタ — OK
- `parse_calendar_month_html` が空入力で `[]` を返す — OK

### Task 2 acceptance criteria（全て PASSED）

- 全テストクラス合格（TestParseCalendarMonthHtml, TestParseRaceDayHtml, TestEnumerateRaces, TestRaceIdValidation） — OK
- テスト数 >= 12 — OK（18テスト、Cycle-2 #1 の +2 を含む）
- Cycle-2 #1: `test_day_urls_are_absolute` と `test_repair_relative_day_url` が合格 — OK
- race_id[4:6] から月を導出するテストなし — OK
- 境界テストが 2026-05-31 含包含を確認 — OK
- `pytest tests/scraper/test_enumeration.py -x -q` exit 0 — OK

## Authentication Gates

None occurred.

## Threat Model Verification

| Threat | Disposition | Status |
|--------|-------------|--------|
| T-04-03 (HTML tampering — forged race_id) | mitigate | 全 race_id を `re.fullmatch(r"\d{12}", ...)` で検証し、不正ID を logger.warning で記録後ドロップ。Rule 1 fix により10/13桁IDも警告されるようになった（元はデッドコード）。 |
| T-04-04 (DoS — calendar flooding) | mitigate | enumeration は `fetch_html` callable を注入されて初めてリクエストを発行する。ブラウザライフサイクルとレート制限は Plan 03 FetcherSession が所有 — このモジュール自身は単独ではリクエストしない。 |
| T-04-05 (Tampering — wrong raw-path month from race_id) | mitigate | Cycle-1 HIGH #1 維持解決済み。raw パス月は `RaceRef.race_date` から導出され、`race_id[4:6]` からは絶対に導出しない（docstring/comment のみ言及、実行可能なスライス演算なし）。 |
| T-04-05b (Tampering — relative-URL injection breaking Playwright) | mitigate | Cycle-2 HIGH #1 解決。`parse_calendar_month_html` は `urljoin(BASE_URL, href)` で全 day URL を絶対化。`enumerate_races_for_day` は防御的に非-http 入力を修復。2つの専用テスト（`test_day_urls_are_absolute`, `test_repair_relative_day_url`）でガード。 |

## Known Stubs

None — 全関数が実際の実装を持つ。スタブ/プレースホルダなし。

## Threat Flags

None — この plan は新規のネットワークエンドポイント、認証パス、ファイルアクセスパターン、または信頼境界でのスキーマ変更を導入しない（`fetch_html` callable は全ての境界横断を抽象化）。

## Commits

- `e463061` — feat(04-02): RaceRef model と3段階カレンダー列挙 + URL絶対化を実装
- `3fe5dd2` — test(04-02): URL絶対化と検証をカバーする列挙テストを追加（Rule 1 fix 含む）

## Self-Check: PASSED

Created files exist:
- FOUND: src/scraper/models.py
- FOUND: src/scraper/enumeration.py
- FOUND: tests/scraper/test_enumeration.py

Commits exist:
- FOUND: e463061 (git log --oneline)
- FOUND: 3fe5dd2 (git log --oneline)

Acceptance grep checks:
- FOUND: no executable `race_id[4:6]` slice in src/scraper/*.py (docstring/comment mentions only)
- FOUND: 12 `urljoin` matches in src/scraper/enumeration.py (>=2 required)
- FOUND: no `sync_playwright` import in enumeration.py
