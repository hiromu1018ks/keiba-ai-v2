---
status: testing
phase: 04-scraping-infrastructure-race-data
source: 04-01-SUMMARY.md, 04-02-SUMMARY.md, 04-03-SUMMARY.md, 04-04-SUMMARY.md, 04-05-SUMMARY.md, 04-06-SUMMARY.md, 04-07-SUMMARY.md, 04-08-SUMMARY.md
started: 2026-06-14T03:18:51Z
updated: 2026-06-14T14:50:00Z
---

## Current Test

number: 6
name: Live Scrape Against Real netkeiba (Phase-Goal Proof) — gap-closure re-verification
expected: |
  After gap-closure plans 04-07 (UAT-Test-3 flag fix) and 04-08 (UAT-Test-6 URL fix),
  a real small date range scraped via `run_scrape(live=True)` produces non-empty
  race/entry/result Parquet under `data/standard/scraped/{YYYYMM}/`, proving the
  corrected `/race/list/{YYYYMM}/` URL form returns racing-day links on the live site.
awaiting: user live verification (or explicit skip)

## Tests

### 1. Scraper Public API Importable
expected: `python -c "from src.scraper import run_scrape, fetch_race_html, fetch_with_retry, enumerate_races, parse_race_html, normalize_to_parquet, FetcherSession, RaceRef"` exits 0 — all 10 public symbols resolve (Cycle-1 HIGH #3 final re-export wiring from Plan 06).
result: pass
verified: "Claude ran import command; all 10 symbols resolved, __all__ lists all 10."

### 2. Scraper Test Suite Green
expected: `pytest tests/scraper/ -q` reports ~198 passed, 1 skipped (the opt-in live smoke). No failures.
result: pass
verified: "Claude ran pytest tests/scraper/ -q → 212 passed, 1 skipped, 1 warning in 10.21s. Skipped = opt-in live smoke. Warning = non-blocking pandas FutureWarning at normalizer.py:570."

### 3. Parser Accuracy on Real netkeiba HTML
expected: The 5 golden fixtures parse to correct race/entry/result dicts — 14-digit horse_race_id, course codes (06/09/05), graded flag True for 宝塚記念, 障害 fixture obstacle flag set.
result: pass
verified: "UAT-Test-3 RESOLVED by plan 04-07. FLAG_CROSSWALK row ('(国際)', 'race_flag_graded_stakes') removed (src/scraper/flag_crosswalk.py); graded detection sourced solely from GRADE_REGEX. Verified: derive_race_flags('4歳以上オープン (国際)(特指)(ハンデ)')['race_flag_graded_stakes'] == None; ヒヤシンスS (Listed) graded_stakes=None; 宝塚記念(GI) graded_stakes=True (GRADE_REGEX intact). CR-02 fix (plan 04-08 code-review round) also normalizes grade to bare 'L' for Listed (was '(L)'). Full parser suite 94 passed."

### 4. Normalizer Produces Kaggle-Compatible Parquet
expected: Scraped Parquet Arrow physical types MATCH Kaggle Parquet for non-null columns (finish_position=int64, weight_assigned/corner_1..4=double, race_flag_*=bool); null-only Kaggle cols deliberately promoted to bool/string. Date-partitioned under `data/standard/scraped/{YYYYMM}/{race,entry,result}.parquet`.
result: pass
verified: "Claude ran TestSchemaCompatibility → 3/3 PASSED. Kaggle standard Parquet Arrow types confirmed: finish_position=int64, corner_1..4=double, weight_assigned/win_odds/popularity/horse_weight=double, race_flag_*=bool. normalizer SCHEMA_DTYPE_MAP matches exactly."

### 5. Full-Chain Offline E2E Produces Parquet
expected: `run_scrape(live=False, fetch_html=<injected transport>)` connects REAL enumerate→fetch→parse→normalize and writes race/entry/result Parquet with correct schema, partition YYYYMM, and row counts. Failed fetch (transport→None) skips that race without crashing others.
result: pass
verified: "Claude ran TestFullChainE2E + test_orchestrator.py → 7/7 PASSED. test_full_chain_end_to_end generates race/entry/result Parquet through REAL enumerate→fetch→parse→normalize. _GoldenTransport regex updated to /race/list/ by plan 04-08."

### 6. Live Scrape Against Real netkeiba (Phase-Goal Proof)
expected: A real small date range scraped from netkeiba via `run_scrape(live=True)` produces REAL standard Parquet (race/entry/result) under `data/standard/scraped/{YYYYMM}/` with plausible data.
result: issue
reported: "UAT-Test-6 PARTIALLY RESOLVED by plan 04-08. URL construction fixed: enumerate_race_day_urls now builds /race/list/{YYYYMM}/ (live-verified working form, verified via URL-capture test). Golden-fixture + URL-contract regression guards added. HOWEVER: actual live run_scrape(live=True) has NOT been re-executed in this environment — the calendar_202306.html fixture is SYNTHETIC (Option B fallback, no live network access during gap closure). The URL form was live-verified during planning, but the live enumeration + end-to-end Parquet generation against the real site remains to be confirmed by a human-driven live run."
severity: blocker
awaiting: human live verification (run_scrape(live=True, 2023-06-25, max_races=3) → non-empty Parquet under data/standard/scraped/202306/)

## Summary

total: 6
passed: 5
issues: 1
pending: 0
skipped: 0
blocked: 0

## Gaps

- truth: "Listed/リステッド競走（ヒヤシンスS 202405010809 など非重賞）の race_flag_graded_stakes は None/False であるべき — 重賞でないレースが重賞としてフラグ立てられてはならない"
  status: resolved
  severity: major
  test: 3
  resolution: "Plan 04-07 removed the ('(国際)', 'race_flag_graded_stakes') row from FLAG_CROSSWALK (src/scraper/flag_crosswalk.py). Graded detection now sourced solely from GRADE_REGEX (GI/GII/GIII/重賞). Module docstring documents the Phase 6 reconciliation requirement (Kaggle-side column_mapping.py still maps (国際)->graded). Regression tests test_international_does_not_set_graded_stakes + test_listed_international_not_graded lock in the fix. Code-review round added CR-02 fix normalizing grade field to bare 'L' for Listed. Verified by gsd-verifier (04-VERIFICATION.md truth #5, #8)."
  resolved_by: "04-07"
  resolved_at: "2026-06-14"

- truth: "run_scrape(live=True) が実netkeibaから2022-2024の実レースをスクレイプし標準Parquetを生成する（フェーズ目標）"
  status: partial
  severity: blocker
  test: 6
  resolution: "Plan 04-08 fixed the URL construction: enumerate_race_day_urls now builds /race/list/{YYYYMM}/ (src/scraper/enumeration.py:206), the live-verified working form. URL-contract test (TestEnumerateRaceDayUrlsUrlContract) + golden-calendar parse test (TestParseCalendarMonthHtmlGolden) prevent silent regression. parse_calendar_month_html logic unchanged (identical relative href shape). _GoldenTransport regex updated for e2e. URL form VERIFIED by gsd-verifier (04-VERIFICATION.md truth #6)."
  awaiting: "Live run_scrape(live=True) re-execution against real netkeiba to confirm the corrected URL returns racing-day links and produces non-empty race/entry/result Parquet. The calendar_202306.html fixture is synthetic (Option B); the URL form was live-verified during planning but not re-confirmed in the execution environment. This is the single remaining human-verification item (04-VERIFICATION.md human_verification)."
  resolved_by: "04-08 (URL form); live run pending"
