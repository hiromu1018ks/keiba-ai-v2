---
phase: 04-scraping-infrastructure-race-data
plan: 06
subsystem: scraper/orchestrator
tags: [scraper, orchestrator, integration, public-api, full-chain-e2e, dtype-fidelity, cycle-2, cycle-3, final-plan]
requires:
  - 04-02 (enumerate_races + RaceRef)
  - 04-03 (FetcherSession + fetch_race_html + make_fetch_html_callable)
  - 04-04 (parse_race_html + golden fixtures)
  - 04-05 (normalize_to_parquet + write_partitioned_parquet partition_map)
  - 04-01 (src/scraper/__init__.py import-safe marker — now transitioned)
provides:
  - "src/scraper/orchestrator.py — run_scrape (Cycle-2 #5 injectable fetch_html; live=False raises without transport; Cycle-3 #2 offline race-fetch routing)"
  - "src/scraper/__init__.py — public re-exports (Cycle-1 HIGH #3 final step): FetcherSession, fetch_race_html, fetch_with_retry, enumerate_races, enumerate_race_day_urls, enumerate_races_for_day, parse_race_html, normalize_to_parquet, RaceRef, run_scrape"
  - "tests/scraper/test_end_to_end.py — TestParseOnlyFixture (Cycle-1 #9), TestFullChainE2E (Cycle-2 #5 incl. Cycle-3 #2 failed-fetch path), TestSchemaCompatibility (Cycle-2 #7 equality+promotion), TestOptInLiveSmoke (skipped by default)"
  - "tests/scraper/test_orchestrator.py — TestRunScrape (5 tests incl. live=False ValueError, offline path)"
affects:
  - "Phase 6 (Data Integration): scraped Parquet schema verified Arrow-compatible with Kaggle Parquet (Cycle-2 #7)"
  - "Future phases import the public API from src.scraper (run_scrape, normalize_to_parquet, etc.)"
tech-stack:
  added: []
  patterns:
    - "Injectable fetch boundary (Cycle-2 #5): run_scrape accepts fetch_html: Callable[[str], Optional[str]]; offline mode routes the transport to BOTH enumeration and fetch_race_html(fetch_callable=...)"
    - "Two-mode guard (Cycle-1 MEDIUM): live=False without fetch_html raises ValueError -- live is no longer a dead parameter"
    - "One FetcherSession per live run (Cycle-1 HIGH browser-per-request preserved)"
    - "Test double _GoldenTransport: minimal calendar/race-day HTML generated inline so REAL parse_calendar_month_html + parse_race_day_html execute in e2e"
    - "Pre-save golden HTML to raw paths so fetch_race_html dedup short-circuits -- isolates e2e to enumerate+parse+normalize while still exercising the real dedup code path"
key-files:
  created:
    - src/scraper/orchestrator.py
    - tests/scraper/test_end_to_end.py
    - tests/scraper/test_orchestrator.py
    - .planning/phases/04-scraping-infrastructure-race-data/deferred-items.md
  modified:
    - src/scraper/__init__.py
    - pyproject.toml
decisions:
  - "CYCLE-2 #5: run_scrape(live=False, fetch_html=transport) is the ONLY mode the full-chain e2e test exercises. The transport serves calendar HTML (inline-constructed with /race/list/{8d}/ links), race-day HTML (inline-constructed with /race/{12d}/ links), and the actual golden race HTML (read from disk). REAL parse_calendar_month_html + parse_race_day_html + enumerate_races + fetch_race_html (dedup branch) + parse_race_html + normalize_to_parquet all run. No real browser, no real network."
  - "CYCLE-1 MEDIUM: live=False without fetch_html raises ValueError (network forbidden). There are exactly two valid modes: live=True (real browser+network) OR live=False + fetch_html (offline). The Cycle-1 plan's live=False default that still permitted network is now a hard error."
  - "CYCLE-3 #2: the offline path passes fetch_callable=transport to fetch_race_html so a race NOT already pre-saved is fetched via the transport (and a transport returning None is handled gracefully -> race skipped, others proceed). The test test_full_chain_handles_failed_fetch exercises this real transport-None -> fetch_race_html-returns-None -> race-skipped flow."
  - "CYCLE-2 #7: TestSchemaCompatibility asserts physical-type EQUALITY only for Kaggle-NON-null columns (int64/double/bool/string) and deliberate promotion (null -> bool/string) for Kaggle-null columns. The unachievable Cycle-1 'equality on every overlapping column' assertion is GONE (pandas nullable boolean serializes to Arrow bool even for all-None columns, while Kaggle's null-data columns are Arrow null)."
  - "TestParseOnlyFixture parametrizes over all 5 fixtures (including the obstacle fixture 202209060504) and verifies the obstacle fixture produces a zero-row race table (normalizer filter). The full-chain e2e set (GOLDEN_FIXTURES) excludes the obstacle fixture so row-count assertions stay clean."
  - "5 pre-existing ruff errors and 9 pre-existing mypy errors found in prior-wave files (flag_crosswalk.py F822, test_enumeration.py F401/F821/F841, fetcher/normalizer/enumeration mypy gaps) are logged in deferred-items.md per SCOPE BOUNDARY (not caused by this plan's changes; verified via git stash). All 4 new files in this plan pass ruff and mypy cleanly."
  - "Registered pytest.mark.live in pyproject.toml [tool.pytest.ini_options] markers to silence the PytestUnknownMarkWarning for TestOptInLiveSmoke."
metrics:
  duration: ~840s (~14min)
  completed: 2026-06-14
  tasks: 3
  tests_added: 18 (5 classes; 1 skipped by default)
  files_created: 4
  files_modified: 2
---

# Phase 04 Plan 06: Pipeline Orchestrator + Full-Chain E2E + Public API Summary

スクレイピングパイプライン全体を統合するorchestratorを実装し、Cycle-2の残存HIGH 2件（#5 full-chain e2e不在、#7 dtype-fidelity達成不可能）とCycle-3 #2（offline race-fetch routing）を解決。Plan 01で意図的に空だった`src/scraper/__init__.py`に公開APIのre-exportを追加し（Cycle-1 HIGH #3 最終ステップ）、Phase 04の全6 planを完遂した。

## What Was Built

### Task 1: Orchestrator + 公開re-export (`8605f17`)

**`src/scraper/orchestrator.py`** — `run_scrape(start_date, end_date, raw_dir, standard_dir, live=False, max_races=None, fetch_html=None) -> dict[str, list[Path]]`。全4段階（enumerate → fetch → parse → normalize）を接続。

- **Cycle-2 #5 injectable fetch boundary**: `fetch_html: Callable[[str], Optional[str]]` パラメータ。提供時は REAL `enumerate_races` と offline `fetch_race_html` の両方で注入transportを使用。
- **Cycle-1 MEDIUM (live-not-dead)**: `live=False` かつ `fetch_html is None` は `ValueError` をraise（ネットワーク禁止）。有効モードは2つのみ: `live=True`（実ブラウザ+実NW）または `live=False, fetch_html=transport`（offline）。
- **Cycle-3 #2 offline race-fetch routing**: offline pathで `fetch_race_html(fetch_callable=transport)` を呼び出し、pre-saveされていないraceもtransport経由で取得。transportがNone返却時はraceをskip（AttributeErrorでcrashしない）。
- **Cycle-1 HIGH browser-per-request**: live modeは `with FetcherSession()` 1回のみ（enumeration + race fetch で共有）。

**`src/scraper/__init__.py`** — Plan 01のimport-safe空マーカーから公開re-exportに移行。`FetcherSession`, `fetch_race_html`, `fetch_with_retry`, `enumerate_races`, `enumerate_race_day_urls`, `enumerate_races_for_day`, `parse_race_html`, `normalize_to_parquet`, `RaceRef`, `run_scrape` をexport。`__all__` リスト付き（Cycle-1 HIGH #3 最終ステップ）。

### Task 2: テストスイート (`a82b14d`)

**`tests/scraper/test_end_to_end.py`** — 4クラス / 14テスト + 1 skipped:

| クラス | テスト数 | 対象 |
|--------|----------|------|
| `TestParseOnlyFixture` | 8 | Cycle-1 #9: parse → normalize per golden fixture (5 fixture parametrized + graded flag + finish note + diversity axes) |
| `TestFullChainE2E` | 2 | **Cycle-2 #5** + **Cycle-3 #2**: REAL enumerate → injected-fetch → REAL parse → REAL normalize |
| `TestSchemaCompatibility` | 3 | **Cycle-2 #7**: equality for non-null Kaggle cols + promotion for null cols |
| `TestOptInLiveSmoke` | 1 (skipped) | Cycle-1 MEDIUM: opt-in live smoke, `LIVE_SMOKE=1` env required |

主要テスト:
- `test_full_chain_end_to_end`: 単一テストが REAL `enumerate_races` → `_GoldenTransport` → REAL `fetch_race_html` (dedup) → REAL `parse_race_html` → REAL `normalize_to_parquet` を接続。race/entry/result Parquet の schema、14-digit horse_race_id、course code "06"、graded flag True、partition YYYYMM (202212/202302/202306)、row count 4 を検証。
- `test_full_chain_handles_failed_fetch`: transportが1raceでNone返却 → `fetch_race_html(fetch_callable=transport)`-returns-None → race skipped（他は継続）。crashしない。
- `test_physical_type_equality_for_non_null_kaggle_columns`: Kaggle非null列（finish_position=int64, weight_assigned=double, corner_1..4=double, race_flag_handicap=bool等）でArrow物理型EQUALITYを検証。
- `test_promotion_allowed_for_null_kaggle_columns`: Kaggle null列（race_flag_stallion_only等14個 + obstacle/surface_detail/track_condition_detail）で具体型（bool/string）への意図的promotionを検証。

**`tests/scraper/test_orchestrator.py`** — 1クラス / 5テスト（`TestRunScrape`）:
- `test_processes_racerefs_end_to_end_mocked`: 2 RaceRefs → normalize_to_parquet が2要素リストで呼ばれる
- `test_skips_failed_fetch`: fetch_race_html None → skip、他は継続
- `test_single_session_per_run`: live mode で FetcherSession 1回のみ
- `test_live_false_without_fetch_html_raises`: **Cycle-1 MEDIUM** ValueError
- `test_live_false_with_injected_fetch_html_runs_offline`: **Cycle-2 #5** offline path（FetcherSession未使用、transport直接注入、fetch_callable=transport）

**`pyproject.toml`** — `[tool.pytest.ini_options]` に `markers = ["live: ..."]` を追加（PytestUnknownMarkWarning解消）。

### Task 3: 検証 + SCRP coverage (`3c86947`)

- `pytest tests/scraper/ -q`: **198 passed, 1 skipped**（180 baseline + 18 new）
- `pytest tests/ -q`: **434 passed, 1 skipped**（full project, no regressions）
- ruff/mypy on new files: **clean**（5 pre-existing errors in prior-wave files logged to deferred-items.md per SCOPE BOUNDARY）
- Public API importable: `from src.scraper import run_scrape, fetch_race_html, fetch_with_retry, enumerate_races, parse_race_html, normalize_to_parquet` ✓

## SCRP Coverage Mapping

| Requirement | Tests |
|-------------|-------|
| SCRP-01 (fetch/parse/normalize separation) | test_fetcher, test_parser, test_normalizer, test_end_to_end (TestParseOnlyFixture, **TestFullChainE2E** per Cycle-2 #5) |
| SCRP-02 (fetch HTML raw save) | test_fetcher::TestPathDerivation, test_orchestrator::TestRunScrape, test_end_to_end::TestFullChainE2E (pre-save raw path) |
| SCRP-03 (parse to standard format) | test_parser, test_normalizer, test_end_to_end (**TestSchemaCompatibility** per Cycle-2 #7) |
| SCRP-05 (dedup) | test_fetcher::TestDedup, test_normalizer::TestPartitionedOutput::test_same_month_merge_dedup_preserves_sentinel, test_end_to_end::TestFullChainE2E (pre-save dedup short-circuit) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Lint] ruff F401/F841 in new test files**
- **Found during:** Task 2 lint check (ruff)
- **Issue:** `test_end_to_end.py` が `BASE_URL`, `RaceRef` をimportしていたが未使用。`test_scraped_columns_superset_of_kaggle_overlap` で `result = _scraped_parquet_for_e2e(...)` の戻り値を使用していなかった（F841）。
- **Fix:** 未使用import削除、未使用変数を `_scraped_parquet_for_e2e(tmp_standard_dir)` の呼出のみに変更。
- **Files modified:** tests/scraper/test_end_to_end.py
- **Commit:** `a82b14d`

**2. [Rule 2 - Missing config] pytest.mark.live 未登録**
- **Found during:** Task 2 テスト実行時（PytestUnknownMarkWarning）
- **Issue:** `TestOptInLiveSmoke` に `@pytest.mark.live` を付けたが、pyproject.toml にmark登録がなく警告。
- **Fix:** `pyproject.toml [tool.pytest.ini_options]` に `markers = ["live: tests that issue real HTTPS requests..."]` を追加。
- **Files modified:** pyproject.toml
- **Commit:** `a82b14d`

### Out-of-Scope Discoveries (logged to deferred-items.md)

- **5 pre-existing ruff errors** in prior-wave files (`flag_crosswalk.py` F822 from 04-01, `test_enumeration.py` F401/F821/F841 from 04-02). Verified pre-existing via `git stash`. Not caused by this plan's changes.
- **9 pre-existing mypy errors** in prior-wave files (`normalizer.py`, `enumeration.py`, `fetcher.py` + `schemas/audit.py` pandas-stubs note). Verified pre-existing via `git stash`. All new files in this plan are mypy-clean.
- Plan 04-06 Task 3 acceptance criteria "ruff check / mypy exits 0" is unachievable without modifying prior-wave files. Per SCOPE BOUNDARY, logged to deferred-items.md for a follow-up lint cleanup PR. The relaxed criterion "no NEW ruff/mypy errors introduced by this plan's files" IS satisfied (all 4 new files clean).

## Verification Results

plan-level `<verification>` ブロック:

| Check | Result |
|-------|--------|
| `pytest tests/scraper/ -q` passes (no -x) | OK (198 passed, 1 skipped) |
| `pytest tests/ -q` passes (no regressions) | OK (434 passed, 1 skipped, 284s) |
| `ruff check src/scraper tests/scraper` on NEW files | OK (All checks passed) |
| `mypy src/scraper` on NEW files | OK (0 new errors; 9 pre-existing logged) |
| `python -c "from src.scraper import run_scrape, ..."` exits 0 | OK |
| `python -c "... assert 'fetch_html' in inspect.signature(run_scrape).parameters"` (Cycle-2 #5) | OK |

### Task 1 acceptance criteria（全て PASSED）

- `from src.scraper import run_scrape, fetch_race_html, fetch_with_retry, enumerate_races, parse_race_html, normalize_to_parquet, FetcherSession, RaceRef` — OK
- `run_scrape` signature includes `fetch_html: Optional[Callable[[str], Optional[str]]] = None` — OK (Cycle-2 #5)
- `run_scrape(live=False)` without fetch_html raises ValueError — OK (Cycle-1 MEDIUM)
- `run_scrape(live=False, fetch_html=stub)` runs using ONLY the injected stub — OK (test_live_false_with_injected_fetch_html_runs_offline)
- CYCLE-3 #2: offline path passes `fetch_callable=transport` to `fetch_race_html` — OK (verified in test_live_false_with_injected_fetch_html_runs_offline + test_full_chain_handles_failed_fetch)
- `run_scrape` in live mode opens exactly ONE FetcherSession — OK (test_single_session_per_run)
- `src/scraper/__init__.py` `__all__` lists all 10 public symbols — OK
- Only this plan modified `__init__.py` re-exports — OK (Cycle-1 HIGH #3 sequencing)

### Task 2 acceptance criteria（全て PASSED）

- All 5 classes pass: TestParseOnlyFixture, TestFullChainE2E, TestSchemaCompatibility, TestOptInLiveSmoke, TestRunScrape — OK
- CYCLE-2 #5: `TestFullChainE2E.test_full_chain_end_to_end` passes — OK (single test connects REAL enumerate → injected-fetch → REAL parse → REAL normalize; asserts schema/14-digit/course-code/graded-flag/partition-YYYYMM/row-count)
- CYCLE-2 #7: `test_physical_type_equality_for_non_null_kaggle_columns` AND `test_promotion_allowed_for_null_kaggle_columns` pass — OK (unachievable all-columns equality replaced)
- Opt-in live smoke skipped by default — OK (1 skipped)
- TestParseOnlyFixture exercises every golden fixture (5 incl. obstacle) — OK
- horse_race_id 14-digit assertion passes for all parsed entries — OK
- race_flag_graded_stakes True for graded fixture end-to-end — OK (asserted in test_full_chain_end_to_end + test_graded_fixture_sets_graded_stakes_flag)
- Orchestrator unit test confirms single FetcherSession — OK
- Orchestrator unit test confirms failed fetch is skipped — OK
- CYCLE-1 MEDIUM: `test_live_false_without_fetch_html_raises` passes — OK
- `pytest tests/scraper/test_end_to_end.py tests/scraper/test_orchestrator.py -x -q` exits 0 — OK (18 passed, 1 skipped)

### Task 3 acceptance criteria（全て PASSED, with deferred-items note）

- `pytest tests/scraper/ -q` exits 0 — OK (198 passed, 1 skipped)
- `pytest tests/ -q` exits 0 — OK (434 passed, 1 skipped, no regressions)
- `ruff check src/scraper tests/scraper` on new files exits 0 — OK (5 pre-existing in prior-wave files logged to deferred-items.md)
- `mypy src/scraper` on new files introduces 0 errors — OK (9 pre-existing in prior-wave files logged)
- SUMMARY documents test → SCRP mapping — OK (all 4 IDs covered, table above)
- `python -c "from src.scraper import run_scrape, ..."` exits 0 — OK

## Authentication Gates

None occurred.

## Threat Model Verification

| Threat | Disposition | Status |
|--------|-------------|--------|
| T-04-20 (DoS — orchestrator unbounded requests) | mitigate | live mode uses sequential FetcherSession with 2s rate limiting; max_races caps smoke runs; live mode opt-in only. **Cycle-1 MEDIUM resolved: live=False without fetch_html now raises ValueError (network forbidden).** |
| T-04-21 (Tampering — integration regression breaking import chain) | mitigate | Full test suite (198 scraper + 434 project) green; public API import test asserts all 10 symbols resolve. ruff/mypy clean on new files. |
| T-04-22 (Tampering — silent e2e breakage) | mitigate | **Cycle-2 HIGH #5 resolved: TestFullChainE2E.test_full_chain_end_to_end connects REAL enumerate→fetch→parse→normalize with only network mocked; asserts schema/14-digit/course-code/graded/partition-YYYYMM/row-count.** Plus TestParseOnlyFixture (Cycle-1 #9) for parse+normalize per fixture. |
| T-04-23 (Tampering — schema incompatibility blocking Phase 6) | mitigate | **Cycle-2 HIGH #7 resolved: TestSchemaCompatibility asserts physical-type EQUALITY for non-null Kaggle cols + deliberate promotion for null Kaggle cols. Unachievable all-columns equality replaced with 2 precise passing assertions.** |

## Known Stubs

None — 全関数が実際の実装を持つ。`run_scrape` は4段階すべてを実際の関数呼出で接続。`_GoldenTransport` はテストダブル（test double）だが、これは本番コードではなくテストコードの一部であり、本番のネットワーク境界を置換するために設計されている。

## Threat Flags

None — この plan は新規のtrust boundaryを導入しない。orchestrator → netkeiba のoutbound HTTPS は fetcher (Plan 03) の FetcherSession が所有（rate limit + block-page detection がPlan 03で処理済み）。offline mode は fetch_html callable が全ての境界横断を抽象化。

## Commits

- `8605f17` — feat(04-06): orchestrator wires enumerate->fetch->parse->normalize + public re-exports
- `a82b14d` — test(04-06): full-chain e2e + dtype-fidelity + orchestrator unit tests
- `3c86947` — docs(04-06): log pre-existing ruff/mypy issues in prior-wave files as deferred

## Self-Check: PASSED

Created files exist:
- FOUND: src/scraper/orchestrator.py
- FOUND: tests/scraper/test_end_to_end.py
- FOUND: tests/scraper/test_orchestrator.py
- FOUND: .planning/phases/04-scraping-infrastructure-race-data/deferred-items.md

Modified files contain expected content:
- FOUND: __all__ with 10 symbols in src/scraper/__init__.py
- FOUND: run_scrape signature with fetch_html param
- FOUND: markers = ["live: ..."] in pyproject.toml [tool.pytest.ini_options]

Commits exist:
- FOUND: 8605f17 (git log --oneline)
- FOUND: a82b14d (git log --oneline)
- FOUND: 3c86947 (git log --oneline)

Test suite:
- FOUND: pytest tests/scraper/ -q = 198 passed, 1 skipped
- FOUND: pytest tests/ -q = 434 passed, 1 skipped (no regressions)

Acceptance grep checks:
- FOUND: 'fetch_html' in inspect.signature(run_scrape).parameters (Cycle-2 #5)
- FOUND: ValueError raised by run_scrape(live=False) without fetch_html (Cycle-1 MEDIUM)
- FOUND: TestFullChainE2E.test_full_chain_end_to_end passes (Cycle-2 #5)
- FOUND: TestSchemaCompatibility 3 tests pass (Cycle-2 #7)
- FOUND: no executable ruff/mypy errors in new files (5+9 pre-existing logged)
