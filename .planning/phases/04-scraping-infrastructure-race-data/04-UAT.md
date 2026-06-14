---
status: complete
phase: 04-scraping-infrastructure-race-data
source: 04-01-SUMMARY.md, 04-02-SUMMARY.md, 04-03-SUMMARY.md, 04-04-SUMMARY.md, 04-05-SUMMARY.md, 04-06-SUMMARY.md, 04-07-SUMMARY.md, 04-08-SUMMARY.md
started: 2026-06-14T03:18:51Z
updated: 2026-06-14T15:00:00Z
---

## Current Test

[all tests passed — gap closure complete with live verification]

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
verified: "UAT-Test-3 RESOLVED by plan 04-07. FLAG_CROSSWALK row ('(国際)', 'race_flag_graded_stakes') removed; graded detection sourced solely from GRADE_REGEX. Live-verified (see Test 6): 宝塚記念(GI) race_flag_graded_stakes=True, 3歳未勝利 graded_stakes=None. CR-02 (code-review fix) normalizes grade to bare 'L'/'GI'. Full parser suite 94 passed."

### 4. Normalizer Produces Kaggle-Compatible Parquet
expected: Scraped Parquet Arrow physical types MATCH Kaggle Parquet for non-null columns (finish_position=int64, weight_assigned/corner_1..4=double, race_flag_*=bool); null-only Kaggle cols deliberately promoted to bool/string. Date-partitioned under `data/standard/scraped/{YYYYMM}/{race,entry,result}.parquet`.
result: pass
verified: "Claude ran TestSchemaCompatibility → 3/3 PASSED. Kaggle standard Parquet Arrow types confirmed. normalizer SCHEMA_DTYPE_MAP matches exactly."

### 5. Full-Chain Offline E2E Produces Parquet
expected: `run_scrape(live=False, fetch_html=<injected transport>)` connects REAL enumerate→fetch→parse→normalize and writes race/entry/result Parquet with correct schema, partition YYYYMM, and row counts. Failed fetch (transport→None) skips that race without crashing others.
result: pass
verified: "Claude ran TestFullChainE2E + test_orchestrator.py → 7/7 PASSED. _GoldenTransport regex updated to /race/list/ by plan 04-08."

### 6. Live Scrape Against Real netkeiba (Phase-Goal Proof)
expected: A real small date range scraped from netkeiba via `run_scrape(live=True)` produces REAL standard Parquet (race/entry/result) under `data/standard/scraped/{YYYYMM}/` with plausible data.
result: pass
verified: "UAT-Test-6 RESOLVED by plan 04-08 + live verification. Claude ran run_scrape(live=True, 2023-06-25, max_races=3): enumerated 92 races from the corrected /race/list/202306/ URL; produced race.parquet(3 rows), entry.parquet(37 rows), result.parquet(37 rows) under data/standard/scraped/202306/. race_date=2023-06-25 confirmed (Cycle-1 HIGH #1: race_id[4:6] is course code, not month). Additional live probe of 宝塚記念 (race_id 202309030811): parse_race_html yields race_name=宝塚記念, grade=GI (CR-02 bare-token fix confirmed), race_flag_graded_stakes=True (UAT-Test-3/GRADE_REGEX confirmed), 17 entries — matches golden fixture exactly. 3歳未勝利戦: grade=None, graded_stakes=None (correct for non-graded). raw HTML saved under data/raw/netkeiba/2023/06/."

## Summary

total: 6
passed: 6
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

- truth: "Listed/リステッド競走（ヒヤシンスS 202405010809 など非重賞）の race_flag_graded_stakes は None/False であるべき"
  status: resolved
  severity: major
  test: 3
  resolution: "Plan 04-07 removed ('(国際)', 'race_flag_graded_stakes') from FLAG_CROSSWALK; graded detection solely via GRADE_REGEX. Live-verified: 宝塚記念(GI)=True, 3歳未勝利=None. Code-review round added CR-02 (grade='L' bare-token). gsd-verifier truth #5/#8 VERIFIED."
  resolved_by: "04-07"
  resolved_at: "2026-06-14"

- truth: "run_scrape(live=True) が実netkeibaから2022-2024の実レースをスクレイプし標準Parquetを生成する（フェーズ目標）"
  status: resolved
  severity: blocker
  test: 6
  resolution: "Plan 04-08 fixed calendar URL to /race/list/{YYYYMM}/. Live verification: run_scrape(live=True, 2023-06-25, max_races=3) enumerated 92 races and produced non-empty race/entry/result Parquet (3/37/37 rows). URL form confirmed working against the live site. gsd-verifier truth #6 VERIFIED (URL form + live enumeration)."
  resolved_by: "04-08"
  resolved_at: "2026-06-14"
