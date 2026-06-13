---
phase: 04
slug: scraping-infrastructure-race-data
status: ready
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-13
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

Regenerated for the cycle-2 reviews revision of the 6-plan structure (04-01 ..
04-06). Every `<task>` in the phase plans maps to exactly one row in the
Per-Task Verification Map below. Cycle-2 changes: 04-02 adds URL-absolutization
verify; 04-03 adds the module-level `fetch_with_retry` wrapper test; 04-04 adds
the parametrized FLAG_CROSSWALK coverage test; 04-05 adds the strict-dtype,
same-month merge-dedup, and entry/result partition_map tests; 04-06 adds the
single full-chain e2e test (Cycle-2 #5) and the revised dtype-fidelity test
(Cycle-2 #7 — equality for non-null Kaggle columns, promotion for null).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` testpaths=["tests"] |
| **Quick run command** | `pytest tests/scraper/ -x -q` |
| **Full suite command** | `pytest tests/ -q` (no `-x` for the final gate per Codex Review MEDIUM) |
| **Estimated runtime** | ~10 seconds (scraper unit tests; Playwright fully mocked) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/scraper/ -x -q`
- **After every plan wave:** Run `pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite + `ruff check src/scraper tests/scraper` + `mypy src/scraper` all clean (per 04-06 Task 3)
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

One row per `<task>` across the 6 plans. The Automated Verification column is
the exact command from the task's `<automated>` block (or the closest scoped
subset, where the plan already scopes it). "File Exists" reflects whether the
test file is created by an earlier Wave-0 task in this phase.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | SCRP-01 | T-04-01, T-04-SC | Import-safe `src/scraper/__init__.py` (no eager submodule imports — HIGH #3); pyproject declares playwright/bs4/lxml | unit + import | `python -c "import src.scraper; print('package import OK')"; grep -c "playwright" pyproject.toml` | ✅ W0 (conftest) | ⬜ pending |
| 04-01-02 | 01 | 1 | SCRP-01 | T-04-01, T-04-02 | Runtime deps installed via pyproject (not bare pip); Chromium binary recorded | unit + import | `python -c "from playwright.sync_api import sync_playwright; from bs4 import BeautifulSoup; import lxml; print('All deps OK')"` | ✅ W0 | ⬜ pending |
| 04-02-01 | 02 | 2 | SCRP-01, SCRP-02 | T-04-03, T-04-04, T-04-05, T-04-05b | 3-level calendar traversal; race_id 12-digit validation; RaceRef.race_date (NOT race_id[4:6]) — Cycle-1 #1/#4; **CYCLE-2 #1: every URL handed to fetch_html is ABSOLUTE via urljoin(BASE_URL, href)** | unit + import | `python -c "from src.scraper.enumeration import enumerate_races, BASE_URL; from src.scraper.models import RaceRef; assert all(u.startswith('https://') for u,_ in __import__('src.scraper.enumeration', fromlist=['parse_calendar_month_html']).parse_calendar_month_html('<a href=\"/race/list/20220105/\">x</a>')); print('Enumeration + Cycle-2 #1 OK')"` | ✅ W0 | ⬜ pending |
| 04-02-02 | 02 | 2 | SCRP-02 | T-04-03, T-04-05, T-04-05b | Cancelled days, malformed IDs, dedup, date-range filter verified; **CYCLE-2 #1: test_day_urls_are_absolute + test_repair_relative_day_url (>=12 tests)** | unit | `pytest tests/scraper/test_enumeration.py -x -q` | ❌ W0 → created by this task | ⬜ pending |
| 04-03-01 | 03 | 3 | SCRP-01, SCRP-02, SCRP-05 | T-04-06, T-04-07, T-04-08, T-04-09, T-04-09b | One browser per batch; atomic write; block-page detection; None on failure; rate-limit on error path — Cycle-1 HIGH browser/atomic/anti-bot/returns-path; **CYCLE-2 #8: module-level `fetch_with_retry` wrapper exists alongside the method** | unit + import | `python -c "from src.scraper.fetcher import FetcherSession, fetch_race_html, fetch_with_retry, detect_block_page, make_fetch_html_callable; import inspect; assert inspect.isfunction(fetch_with_retry); print('Fetcher + Cycle-2 #8 OK')"` | ✅ W0 | ⬜ pending |
| 04-03-02 | 03 | 3 | SCRP-02, SCRP-05 | T-04-06, T-04-07, T-04-09b | SCRP-05 dedup; race_date path; browser-once; None-after-retries; block-page; atomic; rate-limit-on-error; **CYCLE-2 #8: TestModuleLevelFetchWithRetry (3 tests — import/delegation/docstring); >=500-byte valid-HTML fixture (Cycle-1 MEDIUM)** | unit | `pytest tests/scraper/test_fetcher.py -x -q` | ❌ W0 → created by this task | ⬜ pending |
| 04-04-01 | 04 | 3 | SCRP-03 | T-04-11, T-04-13 | COURSE_CODE_MAP corrected (Cycle-1 #5); FLAG_CROSSWALK vs column_mapping.py (Cycle-1 #6); exactly 20 flag keys; **CYCLE-2 #2: FLAG_CROSSWALK exhaustively covers all 13 race_flag_* targets (牡 + bare 見習騎手 added)** | unit + import | `python -c "from src.scraper.course_codes import COURSE_CODE_MAP; assert COURSE_CODE_MAP['福島']=='03' and COURSE_CODE_MAP['新潟']=='04'; from src.scraper.flag_crosswalk import derive_race_flags; assert derive_race_flags('4歳以上1000万下 (牡)')['race_flag_colt_only'] is True; assert derive_race_flags('3歳未勝利 見習騎手')['race_flag_apprentice'] is True; print('Crosswalk + Cycle-2 #2 OK')"` | ✅ W0 | ⬜ pending |
| 04-04-02 | 04 | 3 | SCRP-01, SCRP-03 | T-04-10, T-04-12 | Header-driven parse (HIGH #10); 14-digit horse_race_id (HIGH #2); no head_count; surface_detail emitted | unit + import | `python -c "from src.scraper.parser import parse_race_html, parse_horse_weight, parse_sex_age, resolve_columns_by_header; print('Parser imports OK')"` | ✅ W0 | ⬜ pending |
| 04-04-03 | 04 | 3 | SCRP-03 | — | Golden HTML fixtures captured across years/venues/grades/surfaces/cancellations (HIGH #9 setup) | checkpoint:human-verify | `test -d tests/scraper/fixtures/html && ls tests/scraper/fixtures/html/*.html \| wc -l` | ❌ → created by this checkpoint | ⬜ pending |
| 04-04-04 | 04 | 3 | SCRP-03 | T-04-10, T-04-11, T-04-12, T-04-13 | Course-code parametrized; flag crosswalk; header-driven; 14-digit horse_race_id on golden fixtures; **CYCLE-2 #2: parametrized test_crosswalk_covers_all_kaggle_flag_targets + 牝/牡/apprentice tests (>=24 tests)** | unit | `pytest tests/scraper/test_course_codes.py tests/scraper/test_parser.py -x -q` | ❌ W0 → created by this task | ⬜ pending |
| 04-05-01 | 05 | 4 | SCRP-01, SCRP-03 | T-04-15, T-04-16, T-04-16b, T-04-17, T-04-18 | Schema-conformance reindex (Cycle-1 #7); partitioned atomic output (Cycle-1 #8); **CYCLE-2 #3: strict dtype (no errors=ignore; nullable Int64 for finish_position); CYCLE-2 #4: write_partitioned_parquet merge-dedup on primary key; CYCLE-2 #6: partition_map param for entry/result (no race_date column); CYCLE-3 #1: corner_1..corner_4 -> Float64 (Kaggle double, NOT Int64)**; no audit_leakage on standard | unit + import | `python -c "from src.scraper.normalizer import normalize_to_parquet, validate_integrity, SCHEMA_DTYPE_MAP, write_partitioned_parquet; import inspect; assert 'partition_map' in inspect.signature(write_partitioned_parquet).parameters; assert 'primary_key' in inspect.signature(write_partitioned_parquet).parameters; from src.schemas.result import ResultSchema; assert SCHEMA_DTYPE_MAP[ResultSchema]['finish_position']=='Int64'; assert all(SCHEMA_DTYPE_MAP[ResultSchema][c]=='Float64' for c in ('corner_1','corner_2','corner_3','corner_4')), 'Cycle-3 #1: corners must be Float64'; print('Normalizer + Cycle-2 #3/#4/#6 + Cycle-3 #1 OK')"` | ✅ W0 | ⬜ pending |
| 04-05-02 | 05 | 4 | SCRP-03 | T-04-15, T-04-16, T-04-16b, T-04-18 | Empty-input typed DataFrame; obstacle filtering; integrity (unique/FK/1-to-1); partitioned output; **CYCLE-2 #3: test_finish_position_none_preserves_int64_nullable + test_genuine_coercion_failure_raises + test_no_errors_ignore_in_source; CYCLE-2 #4: test_same_month_merge_dedup_preserves_sentinel; CYCLE-2 #6: test_entry_result_partitioned_via_partition_map + test_entry_write_without_partition_map_raises (>=18 tests)** | unit | `pytest tests/scraper/test_normalizer.py -x -q` | ❌ W0 → created by this task | ⬜ pending |
| 04-06-01 | 06 | 5 | SCRP-01, SCRP-02, SCRP-03, SCRP-05 | T-04-20, T-04-21 | Orchestrator wires all 4 stages through ONE FetcherSession; `__init__.py` re-exports added (Cycle-1 #3 final step); **CYCLE-2 #5: run_scrape accepts injectable fetch_html for full-chain e2e; CYCLE-1 MEDIUM: live=False without fetch_html raises (network forbidden); CYCLE-3 #2: run_scrape(live=False, fetch_html=transport) routes the transport to race fetching via fetch_race_html(fetch_callable=transport); a transport-None race is skipped, not an AttributeError** | unit + import | `python -c "from src.scraper import run_scrape, fetch_race_html, fetch_with_retry, enumerate_races, parse_race_html, normalize_to_parquet, FetcherSession, RaceRef; import inspect; assert 'fetch_html' in inspect.signature(run_scrape).parameters; from src.scraper.fetcher import fetch_race_html as _f; assert 'fetch_callable' in inspect.signature(_f).parameters, 'Cycle-3 #2: fetch_race_html needs fetch_callable param'; print('Package API + Cycle-2 #5 + Cycle-3 #2 OK')"` | ✅ W0 | ⬜ pending |
| 04-06-02 | 06 | 5 | SCRP-01, SCRP-02, SCRP-03, SCRP-05 | T-04-22, T-04-23 | Parse-only fixture e2e across diversity axes (Cycle-1 #9); **CYCLE-2 #5: TestFullChainE2E — single test connects REAL enumerate→injected-fetch→parse→normalize, asserts schema/14-digit-horse_race_id/course-code/graded-flag/partition-YYYYMM/row-count; CYCLE-2 #7: TestSchemaCompatibility revised — equality for non-null Kaggle columns + promotion for null Kaggle columns (unachievable all-columns equality removed)**; live-not-dead orchestrator tests; opt-in live smoke skipped in CI | unit | `pytest tests/scraper/test_end_to_end.py tests/scraper/test_orchestrator.py -x -q` | ❌ → created by this task | ⬜ pending |
| 04-06-03 | 06 | 5 | SCRP-01, SCRP-02, SCRP-03, SCRP-05 | T-04-21 | Full scraper suite green; full project suite green (no regressions); ruff + mypy clean; SCRP mapping documented | suite + lint + type | `pytest tests/scraper/ -q && ruff check src/scraper tests/scraper && mypy src/scraper` | ✅ (depends on all earlier) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Sampling continuity check:** every task has an automated `<verify>` step. No
3 consecutive tasks lack automated verification. The single checkpoint
(04-04-03) is flanked by automated tasks (04-04-02 and 04-04-04).

---

## Wave 0 Requirements

The phase creates its own test scaffold in Wave 1 (04-01 Task 1) so all later
waves have a working `tests/scraper/` package. Each test file below is created
by the plan that owns its tests; the file name is listed with its owning plan.

- [x] `tests/scraper/__init__.py` — empty test package marker (created by **04-01** Task 1)
- [x] `tests/scraper/conftest.py` — shared fixtures `tmp_raw_dir`, `tmp_standard_dir`, `golden_html_dir` (created by **04-01** Task 1; consumed by 04-02/03/04/05/06)
- [ ] `tests/scraper/test_enumeration.py` — created by **04-02** Task 2
- [ ] `tests/scraper/test_fetcher.py` — created by **04-03** Task 2
- [ ] `tests/scraper/test_course_codes.py` — created by **04-04** Task 4
- [ ] `tests/scraper/test_parser.py` — created by **04-04** Task 4
- [ ] `tests/scraper/fixtures/html/*.html` — golden real-HTML fixtures captured by **04-04** Task 3 (human checkpoint)
- [ ] `tests/scraper/test_normalizer.py` — created by **04-05** Task 2
- [ ] `tests/scraper/test_end_to_end.py` — created by **04-06** Task 2; contains TestParseOnlyFixture (Cycle-1 #9), **TestFullChainE2E (Cycle-2 #5 — single full-chain test)**, **TestSchemaCompatibility (Cycle-2 #7 — equality + promotion rule)**, TestOptInLiveSmoke
- [ ] `tests/scraper/test_orchestrator.py` — created by **04-06** Task 2
- [x] `src/scraper/__init__.py` — import-safe empty package marker (created by **04-01** Task 1; re-exports added by 04-06 Task 1)

The two checked items are created in Wave 1 and exist before any later-wave
test runs. All unchecked items are created by the same task that writes the
tests they contain (each task lists its test file in `<files>` and the file is
written in the same commit as the production code it tests), so there is no
standalone "Wave 0 must scaffold test files first" step for them.

---

## Manual-Only Verifications

Replaces the pre-revision CLI-flag commands (the fetcher exposes no
`--dry-run` / `--enumerate` flags; the only Python entry point is the
orchestrator function `run_scrape`).

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Public entry point importable | SCRP-01 | Confirms the integrated API surface exists without launching a browser | `python -c "from src.scraper.orchestrator import run_scrape; print(callable(run_scrape))"` — must print `True` |
| Live opt-in smoke test (one historical race) | SCRP-02 | Requires real network access to db.netkeiba.com with rate limiting; not safe for CI | Set `LIVE_SMOKE=1` and run `pytest tests/scraper/test_end_to_end.py::TestOptInLiveSmoke -x` (skipped by default — no network in CI) |
| Golden HTML fixture capture | SCRP-03 | Requires a real Playwright session against db.netkeiba.com to capture authentic pages; Claude cannot fabricate netkeiba HTML without risking silent structural mismatches | Per **04-04** Task 3 (checkpoint:human-verify): navigate to `https://db.netkeiba.com/race/{race_id}/` for ≥3 races spanning (base flat, graded stakes, dirt surface) and save Page Source (UTF-8) to `tests/scraper/fixtures/html/{race_id}.html`. Resume signal: "approved" + fixture count. |
| Scraped vs Kaggle schema overlap | SCRP-03 | Automated only on synthetic input; the live overlap is best eyeballed once real scraped data exists | After a live smoke run, compare `pyarrow.parquet.read_schema('data/standard/scraped/{YYYYMM}/race.parquet')` against `pyarrow.parquet.read_schema('data/standard/race.parquet')` on overlapping fields (documented in the 04-06 SUMMARY) |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (15/15 implementation tasks have automated verify; the 1 checkpoint 04-04-03 has an automated existence check + human-verify gate)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (checkpoint 04-04-03 is flanked by 04-04-02 and 04-04-04)
- [x] Wave 0 covers all MISSING references (test scaffold created in Wave 1 by 04-01 Task 1; each later test file is created by the task that writes it)
- [x] No watch-mode flags (`pytest -q` final gate uses no `--watch`/`--ff`)
- [x] Feedback latency < 15s (scraper unit tests are mocked-Playwright; ~10s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** ready (regenerated 2026-06-13 for the cycle-2 reviews revision — 8 Cycle-2 HIGHs addressed: 04-02 #1 URL absolutization, 04-03 #8 fetch_with_retry wrapper, 04-04 #2 FLAG_CROSSWALK exhaustive, 04-05 #3 strict dtype / #4 merge-dedup / #6 partition_map, 04-06 #5 full-chain e2e / #7 dtype-fidelity promotion rule)
