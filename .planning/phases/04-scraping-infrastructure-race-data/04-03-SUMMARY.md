---
phase: 04-scraping-infrastructure-race-data
plan: 03
subsystem: scraper/fetcher
tags: [scraper, fetcher, playwright, atomic-write, anti-bot, dedup, cycle-2-fix, cycle-3-fix, context-manager, dependency-injection]
requires:
  - 04-02 (RaceRef — race_id + race_date; fetch_html callable signature)
  - 04-01 (playwright/beautifulsoup4/lxml runtime deps installed)
provides:
  - "src/scraper/fetcher.py — FetcherSession context manager (one browser per batch), fetch_race_html (Cycle-3 #2: optional fetch_callable), module-level fetch_with_retry wrapper (Cycle-2 #8), detect_block_page, make_fetch_html_callable"
  - "tests/scraper/test_fetcher.py — 29 tests across 9 classes with mocked Playwright (no real browser, no network)"
affects:
  - "04-06 (orchestrator) wires FetcherSession + fetch_race_html + make_fetch_html_callable into run_scrape; uses the METHOD on a shared session, not the module-level wrapper (avoids browser-per-request regression)"
  - "04-06 (orchestrator) passes the injected fetch_html transport as fetch_callable to fetch_race_html in offline mode (Cycle-3 #2 routing)"
tech-stack:
  added: []
  patterns:
    - "Context-manager resource ownership: one Chromium browser per BATCH via __enter__/__exit__ with nested try/finally cleanup (Cycle-1 HIGH browser-per-request fix)"
    - "Atomic file write: temp file + os.replace rename (interruption never leaves a non-empty partial file)"
    - "Dependency-injected transport: fetch_race_html accepts session OR fetch_callable (Cycle-3 #2); both-None raises ValueError (not AttributeError on None)"
    - "Dual-export pattern: module-level fetch_with_retry function + FetcherSession.fetch_with_retry method (Cycle-2 #8 export-contradiction fix)"
    - "Block-page detection: length < 500 / CAPTCHA markers / missing race_table_01 (anti-bot rejection)"
    - "Rate limiting on BOTH success and error paths via finally block (Cycle-1 MEDIUM rate-limit-on-error)"
key-files:
  created:
    - src/scraper/fetcher.py
    - tests/scraper/test_fetcher.py
  modified: []
decisions:
  - "Cycle-2 HIGH #8 resolved: module-level fetch_with_retry function exists alongside FetcherSession.fetch_with_retry method. The verify import `from src.scraper.fetcher import fetch_with_retry` succeeds. The wrapper constructs a transient FetcherSession and delegates; its docstring warns against loop usage (T-04-09b regression guard)."
  - "Cycle-3 #2 resolved: fetch_race_html signature is (race_ref, session=None, raw_dir=..., fetch_callable=None). When session is None and fetch_callable is provided, the callable fetches the HTML (offline mode). When both are None, ValueError is raised (not AttributeError on None.fetch_with_retry). fetch_callable takes precedence when both are provided (offline routing wins)."
  - "FetcherSession.wait_until default is 'domcontentloaded' (NOT 'networkidle') — networkidle is unreliable on pages with persistent requests (Cycle-1 MEDIUM)."
  - "FetcherSession.fetch applies time.sleep(rate_limit_seconds) in a finally block so the rate limit runs on BOTH success and error paths (Cycle-1 MEDIUM — server errors must not trigger unthrottled retries)."
  - "Mock wiring: sync_playwright().start() returns the playwright instance; tests patch src.scraper.fetcher.sync_playwright and set mock.return_value.start.return_value to the playwright mock (the .start() call happens on the object returned by sync_playwright(), not on sync_playwright itself)."
metrics:
  duration: 302s
  completed: 2026-06-14
  tasks: 2
  tests_added: 29
  files_created: 2
  files_modified: 0
---

# Phase 04 Plan 03: netkeiba Playwright Fetcher Summary

PlaywrightベースのHTML fetcherを実装した。1バッチ=1ブラウザを再利用する`FetcherSession`コンテキストマネージャ、atomic write、anti-bot検出、依存性注入型のtransport選択（Cycle-3 #2）を備える。**Cycle-2 HIGH #8（`fetch_with_retry` エクスポート矛盾）**を解決: モジュールレベルの薄いwrapper関数と`FetcherSession`メソッドの両方を提供し、verify block の `from src.scraper.fetcher import fetch_with_retry` が成功する。

## What Was Built

### Task 1: FetcherSession + atomic fetch + block detection + module-level wrapper (`9694540`)

**`src/scraper/fetcher.py`** — Playwright fetcher 基盤。以下のシンボルを提供:

- **`MAX_RETRIES = 3`, `RATE_LIMIT_SECONDS = 2.0`, `_RACE_ID_RE = re.compile(r"\d{12}")`** — モジュール定数。
- **`class FetcherSession`** — コンテキストマネージャ。1バッチにつきChromiumブラウザを1つ起動し、全fetch呼び出しで再利用（Cycle-1 HIGH browser-per-request解決）。
  - `__enter__`: `sync_playwright().start()` → `chromium.launch(headless=...)` → `new_context()` → `new_page()`。1つのreusable pageを作成。
  - `__exit__`: ネストしたtry/finallyでpage/context/browserを閉じ、playwrightを停止（Cycle-1 MEDIUM finally cleanup — クラッシュ時も確実に解放）。
  - `fetch(url)`: `page.goto(wait_until="domcontentloaded", timeout=...)` → `page.content()`。`PlaywrightTimeout`/Exception時は警告して`None`。**finally block**で`time.sleep(rate_limit_seconds)`を成功・エラー両パスに適用（Cycle-1 MEDIUM rate-limit-on-error）。
  - `fetch_with_retry(url, retries=MAX_RETRIES)`: `self.fetch`を`retries`回まで指数バックオフ付きで再試行。HTML文字列を返すか、全retry失敗後は`None`（Cycle-1 HIGH — 失敗時にpathを返さない）。
- **`detect_block_page(html)`** — anti-bot/CAPTCHA/空ページ検出。以下いずれかでTrue: HTML < 500 bytes; `アクセス制限`/`robot`/`captcha`/`403 Forbidden`部分文字列; `race_table_01`不在かつ`result`不在。
- **`fetch_race_html(race_ref, session=None, raw_dir=..., fetch_callable=None)`** (Cycle-3 #2):
  - `race_ref.race_id`を`re.fullmatch(r"\d{12}", ...)`で検証、不正なら`ValueError`（Cycle-1 MEDIUM）。
  - `{YYYY}/{MM}`パスを`race_ref.race_date`から導出（Cycle-1 HIGH #1 — `race_id[4:6]`は不使用）。
  - SCRP-05 dedup: 非空ファイルはskip、0 byteファイルは再取得。
  - **transport選択** (Cycle-3 #2): `fetch_callable`があれば`fetch_callable(url)`（offline mode）、 elif `session`があれば`session.fetch_with_retry(url)`（live mode default）、両方Noneなら`ValueError`（`None.fetch_with_retry`のAttributeErrorではない）。
  - block page検出時は`None`返却（保存しない）。
  - **atomic write**: tempファイル → `os.replace`でリネーム（中断時の部分書き込み防止）。
- **`fetch_with_retry(url, retries=MAX_RETRIES, headless=True)`** (Cycle-2 #8 NEW) — モジュールレベルの薄いwrapper。単発CLI/smokeユース向け。一時的`FetcherSession`を構築し、メソッドに委譲。docstringに「loop内で呼ぶな — browser-per-request regressionを引き起こす」と警告（T-04-09b）。
- **`make_fetch_html_callable(session)`** — `lambda url: session.fetch_with_retry(url)`クロージャ。enumeration (Plan 02)が同じsessionを再利用可能。

### Task 2: fetcherテスト一式 (`aec3d50`)

**`tests/scraper/test_fetcher.py`** — 29テスト / 9クラス。全て`unittest.mock.patch`でPlaywrightをモック、実ブラウザなし・ネットワークなし。「valid HTML」fixtureは意図的に500 bytes以上かつ`race_table_01`を含む（detect_block_pageのfalse-positive回避 — Cycle-1 MEDIUM）。

| クラス | テスト数 | 対象 |
|--------|----------|------|
| `TestDedup` | 2 | SCRP-05: 非空skip、0 byte再取得 |
| `TestPathDerivation` | 2 | Cycle-1 HIGH #1: race_date由来、不正ID ValueError |
| `TestFetcherSessionLifecycle` | 3 + helper | 1 browser/batch、exit後close、例外時もclose |
| `TestRetryAndFailure` | 2 | max retry後None、エラーパスでrate limit |
| `TestBlockPageDetection` | 6 | CAPTCHA/short/robot/アクセス制限/missing-table/valid |
| `TestAtomicWrite` | 1 | .html.tmp残存なし |
| `TestModuleLevelFetchWithRetry` | 5 | **Cycle-2 #8**: import成功、method存在、委譲、None契約、loop警告docstring |
| `TestCycle3FetchCallable` | 5 | **Cycle-3 #2**: session None時callable使用、両None ValueError、callable None正常処理、dedup先行 |
| `TestMakeFetchHtmlCallable` | 2 | クロージャ委譲、callable確認 |

`pytest tests/scraper/ -q` = **150 passed**（121既存 + 29新規）。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Playwright mock chain structure was wrong in lifecycle tests**
- **Found during:** Task 2 `test_launches_browser_once_per_batch` 実行時（`assert mock_p.chromium.launch.call_count == 1` failed, got 0）
- **Issue:** 当初のモック設定 `mock_pw.start.return_value = mock_p` はfetcherの実際の呼び出し連鎖 `sync_playwright().start()` と不一致。fetcherでは `sync_playwright()` がまず呼ばれ（`return_value`）、その戻り値に対して `.start()` が呼ばれる。したがって正しくは `mock_pw.return_value.start.return_value = mock_p`。
- **Fix:** `_wire_mock_playwright` helperメソッドを導入し、3つのlifecycleテストと`test_rate_limit_applied_on_error`で正しい連鎖 `sync_playwright().return_value.start.return_value` を設定。
- **Files modified:** tests/scraper/test_fetcher.py
- **Commit:** `aec3d50`

**2. [Rule 1 - Bug] 未使用import (ruff F401)**
- **Found during:** Task 2 lint check (ruff)
- **Issue:** `datetime`, `Optional`, `MAX_RETRIES` がtest fileでimportされていたが未使用。
- **Fix:** 3つの未使用importを削除。
- **Files modified:** tests/scraper/test_fetcher.py
- **Commit:** `aec3d50`

## Verification Results

plan-level `<verification>` ブロックは全て PASSED:

| Check | Result |
|-------|--------|
| `pytest tests/scraper/test_fetcher.py -x -q` passes | OK (29 passed) |
| `python -c "from src.scraper.fetcher import FetcherSession, fetch_race_html, fetch_with_retry, detect_block_page, make_fetch_html_callable"` exits 0 | OK (Cycle-2 #8) |
| `grep -n "race_id\[4:6\]" src/scraper/fetcher.py` returns nothing executable | OK (docstring/commentのみ — AST Subscriptは全て型アノテーション) |

### Task 1 acceptance criteria（全て PASSED）

- `FetcherSession` is a context manager with `__enter__`/`__exit__` (one browser per batch) — OK
- `__exit__` uses try/finally to close browser/context/page — OK (ネストしたtry/finally)
- `wait_until` default is `"domcontentloaded"` (NOT `"networkidle"`) — OK
- `FetcherSession.fetch` applies `time.sleep(rate_limit_seconds)` on BOTH success and error paths — OK (finally block)
- `FetcherSession.fetch_with_retry` method returns `Optional[str]` — None on terminal failure — OK
- `detect_block_page` returns True for short HTML, CAPTCHA/robot/403 markers, and pages lacking `race_table_01` — OK
- `fetch_race_html` first parameter is `race_ref: RaceRef` — OK
- `fetch_race_html` derives month from `race_ref.race_date.month`, NOT from `race_ref.race_id[4:6]` — OK
- `fetch_race_html` writes via temp file + `os.replace` (atomic) — OK
- `fetch_race_html` validates race_id with `re.fullmatch(r"\d{12}", ...)` and raises ValueError — OK
- `fetch_race_html` returns None when fetch fails or block page detected — OK
- **Cycle-3 #2**: `fetch_callable` param exists; session=None+callable uses callable; both None raises ValueError; dedup runs before transport — OK
- No executable `race_id[4:6]` slice — OK
- No `sync_playwright()` call at module level (only inside `__enter__`) — OK (module wrapperは`FetcherSession`経由)
- **Cycle-2 #8**: `python -c "from src.scraper.fetcher import fetch_with_retry"` exits 0 — OK
- **Cycle-2 #8**: `inspect.isfunction(fetch_with_retry)` True AND `hasattr(FetcherSession, "fetch_with_retry")` True — OK
- **Cycle-2 #8**: module-level wrapper docstring contains loop warning — OK

### Task 2 acceptance criteria（全て PASSED）

- All 9 test classes pass (7 plan-required + Cycle-3 #2 bonus + make_fetch_html_callable bonus) — OK
- Test count >= 17 — OK (29 tests)
- **Cycle-2 #8**: `test_module_level_import_succeeds` passes — OK
- **Cycle-2 #8**: `test_module_level_wrapper_delegates_to_method` passes — OK
- No test reads race_id[4:6] as a month — OK (comment/docstringのみ)
- Dedup, atomic write, block-page detection, browser-once-per-batch all verified — OK
- "valid HTML" test fixture >= 500 bytes — OK (`assert len(_VALID_HTML) >= 500`)
- `pytest tests/scraper/test_fetcher.py -x -q` exits 0 — OK

## Authentication Gates

None occurred.

## Threat Model Verification

| Threat | Disposition | Status |
|--------|-------------|--------|
| T-04-06 (DoS — rate-limit abuse) | mitigate | `FetcherSession.fetch` が finally block で成功・エラー両パスに `time.sleep(rate_limit_seconds)` を適用。1バッチ=1ブラウザ再利用。retryは指数バックオフ (`RATE_LIMIT_SECONDS * (attempt + 2)`)。モジュールレベルwrapperのdocstringがloop使用を警告（T-04-09b regression guard）。 |
| T-04-07 (Tampering — partial HTML file) | mitigate | atomic write（temp + `os.replace`）実装。0 byteファイルは再取得（dedupがsize > 0を要求）。block page検出が空/anti-bot応答を却下。 |
| T-04-08 (Elevation — anti-bot detection) | mitigate | Playwrightが実ブラウザと同じレンダリング。`domcontentloaded` wait が永続接続でのハングを回避。block page検出が失敗を表面化（junkの黙示保存なし）。 |
| T-04-09 (Info Disclosure — raw HTML at rest) | accept | ローカル保存のみ、外部送信なし。spec が公開を禁止。計画通り accept。 |
| T-04-09b (Tampering — browser-per-request regression via wrapper) | mitigate | Cycle-2 #8 wrapper の docstring が明示的に「Do NOT call this in a loop over many URLs — use FetcherSession.fetch_with_retry on a single shared session instead」と警告。`test_wrapper_docstring_contains_loop_warning` が docstring の存在を機械的に検証。 |

## Known Stubs

None — 全関数が実際の実装を持つ。スタブ/プレースホルダなし。

## Threat Flags

None — この plan は新規のtrust boundaryを導入しない（fetcher → netkeiba のoutbound HTTPS、fetcher → filesystem のatomic write は計画の脅威モデル内で処理済み）。

## Commits

- `9694540` — feat(04-03): FetcherSession context manager + atomic fetch + block-page detection + module-level fetch_with_retry
- `aec3d50` — test(04-03): fetcher tests with mocked Playwright (29 tests across 9 classes)

## Self-Check: PASSED

Created files exist:
- FOUND: src/scraper/fetcher.py
- FOUND: tests/scraper/test_fetcher.py

Commits exist:
- FOUND: 9694540 (git log --oneline)
- FOUND: aec3d50 (git log --oneline)

Acceptance grep checks:
- FOUND: no executable `race_id[4:6]` slice in src/scraper/fetcher.py (AST Subscript nodes are all type annotations; grep matches are docstring/comment only)
- FOUND: module-level `fetch_with_retry` is a function (`inspect.isfunction` True)
- FOUND: `FetcherSession.fetch_with_retry` method exists (`hasattr` True)
- FOUND: module-level wrapper docstring contains loop warning
- FOUND: full scraper test suite green (150 passed = 121 baseline + 29 new)
