---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Phase 04 plan 04-08 complete (UAT-Test-6 URL blocker closed; phase 04 fully complete)
last_updated: "2026-06-14T06:03:58.835Z"
last_activity: 2026-06-14
progress:
  total_phases: 10
  completed_phases: 4
  total_plans: 21
  completed_plans: 21
  percent: 40
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-10)

**Core value:** 推定的中確率に対してオッズが高い三連複を特定し、バックテストで回収率を検証できること
**Current focus:** Phase 04 — scraping-infrastructure-race-data

## Current Position

Phase: 5
Plan: Not started
Status: Ready to execute
Last activity: 2026-06-14

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**

- Total plans completed: 24
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 5 | - | - |
| 02 | 3 | - | - |
| 03 | 5 | - | - |
| 04 | 8 | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 02 P01 | 240s | 1 tasks | 4 files |
| Phase 02 P02 | 649 | 2 tasks | 3 files |
| Phase 02 P03 | 2253 | 2 tasks | 7 files |
| Phase 03 P01 | 716 | 1 tasks | 3 files |
| Phase 03 P02 | 539 | 2 tasks | 2 files |
| Phase 03 P03 | 847 | 2 tasks | 3 files |
| Phase 03 P04 | 465 | 2 tasks | 2 files |
| Phase 03 P05 | 2015 | 2 tasks | 2 files |
| Phase 04 P01 | 78 | 2 tasks | 4 files |
| Phase 04 P02 | 197 | 2 tasks | 3 files |
| Phase 04 P04 | 1500 | 4 tasks | 8 files |
| Phase 04 P03 | 302 | 2 tasks | 2 files |
| Phase 04 P05 | 352 | 2 tasks | 2 files |
| Phase 04 P06 | 840 | 3 tasks | 6 files |
| Phase 04 P07 | 371 | 2 tasks | 3 files |
| Phase 04 P08 | 223 | 3 tasks | 4 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Roadmap created with 10 phases at fine granularity
- Data scope limited to 2015-2024 (not full 1986-2021 Kaggle range)
- Phase 4 (Scraping) has dependency only on Phase 1, enabling parallel work with Phases 2-3
- [Phase 02]: Flag columns use actual CSV header names with parentheses/brackets for multi-to-single flag mapping
- [Phase ?]: Multi-mapped flag columns coalesced: 20 CSV flags become 13 unique schema fields
- [Phase ?]: Optional[bool] and Optional[int] stored as object dtype in Parquet; dtype compatibility accepts object for both
- [Phase ?]: 7 unmapped race flag fields added as None columns; Kaggle CSV lacks corresponding flag columns
- [Phase ?]: horse_entity_key uses birth_year_proxy (race_year - age) for collision-safe horse identification, disambiguating 14 same-name collisions
- [Phase ?]: Inner join on result correct (entry-result 1:1 at 311,806 rows); race_id provides globally unique ordering across courses
- [Phase ?]: Race-boundary z-score: normalization operates on race-level means with expanding shift(1), preventing same-race leakage
- [Phase ?]: MARGIN_MAP (22 entries) + COMPONENT_MAP handles all margin text formats including compound '+' forms
- [Phase ?]: result_status uses np.select() for finish_note mapping with 6 categories, no catch-all needed
- [Phase ?]: is_debut uses cumsum-based approach excluding 取/除 from history count (D-09)
- [Phase 03]: FEATURE_COLUMNS is a static allowlist from named feature groups -- no column can silently appear in model features
- [Phase 03]: Leakage audit uses RaceSchema + EntrySchema only; ResultSchema marks race_id as post-race
- [Phase 03]: finish_time_zscore not temporally invariant under dataset truncation (expanding-window normalization)
- [Phase 04 P01]: src/scraper/__init__.py ships as import-safe EMPTY marker for Plans 02-05; public re-exports added only in Plan 06 (fixes Codex Review HIGH #3)
- [Phase 04 P01]: playwright/beautifulsoup4/lxml declared as runtime deps (not dev extra) per D-02; versions installed: playwright 1.60.0, bs4 4.15.0, lxml 6.1.1
- [Phase 04 P01]: Chromium binary (chromium-1223 + headless shell + ffmpeg-1011) installed at ~/Library/Caches/ms-playwright/ — recorded as machine state per threat T-04-02
- [Phase 04 P02]: RaceRef is a stdlib frozen dataclass (NOT Pydantic) — lightweight typed pair; Pydantic overhead reserved for src/schemas/ standard-layer schemas
- [Phase 04 P02]: _RACE_HREF_RE extraction regex is \d+ (variable-length numeric), NOT \d{12}; strict 12-digit check delegated to _RACE_ID_RE.fullmatch so malformed (10/13-digit) IDs actually reach the warning branch (was dead code — Rule 1 fix)
- [Phase 04 P02]: Cycle-2 HIGH #1 resolved — every URL handed to fetch_html is absolute via urljoin(BASE_URL, href); parse_calendar_month_html yields absolute day URLs, enumerate_races_for_day defensively repairs non-http inputs
- [Phase 04 P04]: race_name extracted from <title> not <h1> — netkeiba's <h1> holds the site logo, not the race name (Rule 1 deviation fix verified against 5 real fixtures)
- [Phase 04 P04]: obstacle detection keyed off '障害' substring in race_condition (course-info line has no direction token for obstacle races); _COURSE_INFO_RE rewritten for ダ shorthand + 外 outer-loop + optional direction
- [Phase 04 P04]: race_flag_graded_stakes set via (国際) substring for Kaggle join compatibility; race_flag_stakes stays None when race name has no explicit GI token (Plan accepts — Phase 6 may revisit)
- [Phase 04 P04]: Cycle-2 HIGH #2 resolved — FLAG_CROSSWALK is exhaustive superset of KAGGLE_COLUMN_MAP's 13 race_flag_* targets (牡 + bare 見習騎手 added); parametrized coverage guard test_crosswalk_covers_all_kaggle_flag_targets
- [Phase 04]: Cycle-2 HIGH #8 resolved — module-level fetch_with_retry function exists alongside FetcherSession.fetch_with_retry method; verify import succeeds; wrapper docstring warns against loop usage (T-04-09b regression guard) — Plan 04-03 implements the Playwright fetcher. Decisions resolve Cycle-2 HIGH #8 (export contradiction), Cycle-3 #2 (offline transport routing), and confirm Cycle-1 MEDIUM mitigations (rate-limit-on-error, networkidle avoidance, finally cleanup, 12-digit validation).
- [Phase 04]: Cycle-3 #2 resolved — fetch_race_html(race_ref, session=None, raw_dir, fetch_callable=None); when session None + fetch_callable provided, callable fetches HTML (offline mode); both None raises ValueError (not AttributeError); fetch_callable wins when both provided — Plan 04-03 implements the Playwright fetcher. Decisions resolve Cycle-2 HIGH #8 (export contradiction), Cycle-3 #2 (offline transport routing), and confirm Cycle-1 MEDIUM mitigations (rate-limit-on-error, networkidle avoidance, finally cleanup, 12-digit validation).
- [Phase 04]: FetcherSession.wait_until default 'domcontentloaded' (NOT 'networkidle'); fetch() applies time.sleep(rate_limit_seconds) in finally block on BOTH success and error paths (Cycle-1 MEDIUM rate-limit-on-error); atomic write via temp + os.replace; mock chain for tests is sync_playwright().return_value.start.return_value — Plan 04-03 implements the Playwright fetcher. Decisions resolve Cycle-2 HIGH #8 (export contradiction), Cycle-3 #2 (offline transport routing), and confirm Cycle-1 MEDIUM mitigations (rate-limit-on-error, networkidle avoidance, finally cleanup, 12-digit validation).
- [Phase 04 P05]: CYCLE-2 #3 resolved — SCHEMA_DTYPE_MAP uses nullable pandas Int64/Float64/boolean wherever Kaggle Parquet is nullable; _build_typed_dataframe does NOT use astype(errors=ignore) anywhere (genuine failures raise TypeError); finish_position is Int64 so None does not silently become float64.
- [Phase 04 P05]: CYCLE-3 #1 resolved — corner_1..corner_4 -> Float64 (Kaggle double nullable=True; verified via pyarrow.parquet.read_schema). Cycle-2 Int64 choice was wrong: Int64 serializes to Arrow int64 (str(int64)!=str(double)) and would FAIL 04-06 physical-type equality test. Float64 serializes to Arrow double (str matches).
- [Phase 04 P05]: CYCLE-2 #4 resolved — write_partitioned_parquet performs read-merge-dedup on primary_key (race_id/horse_race_id) BEFORE atomic replace; keep="last" so newer re-run wins; sentinel survives same-month re-run; duplicate PKs collapse to one.
- [Phase 04 P05]: CYCLE-2 #6 resolved — EntrySchema/ResultSchema have NO race_date column; write_partitioned_parquet accepts partition_map (race_id->race_date) for entry/result tables; calling without partition_map raises KeyError mentioning "partition_map" (fail loud, not silent mis-partition); normalize_to_parquet builds partition_map from filtered race_df.
- [Phase 04 P05]: CYCLE-1 MEDIUM — normalize_to_parquet does NOT call audit_leakage; popularity/win_odds are intentionally in entry table per D-06/D-03; leakage audit reserved for feature-layer generation.
- [Phase 04 P05]: CYCLE-1 HIGH #7/#8 stay resolved — _build_typed_dataframe reindexes to Schema.model_fields (empty input -> typed zero-row DF with ALL columns); output is date-partitioned under data/standard/scraped/{YYYYMM}/ (no single-file overwrite pattern _scraped.parquet).
- [Phase 04 P06]: CYCLE-2 #5 resolved — run_scrape(live=False, fetch_html=transport) provides the injectable fetch boundary that the full-chain e2e test uses; REAL enumerate_races + parse_race_html + normalize_to_parquet run with only the network boundary mocked.
- [Phase 04 P06]: CYCLE-1 MEDIUM resolved — live=False without fetch_html now RAISES ValueError (network forbidden); live is no longer a dead parameter. Two valid modes: live=True (real browser+NW) OR live=False + fetch_html (offline).
- [Phase 04 P06]: CYCLE-3 #2 resolved — offline path passes fetch_callable=transport to fetch_race_html so a race NOT pre-saved is fetched via the transport; transport returning None is handled gracefully (race skipped, others proceed), not AttributeError.
- [Phase 04 P06]: CYCLE-2 #7 resolved — TestSchemaCompatibility asserts physical-type EQUALITY for Kaggle-NON-null columns + deliberate promotion (null->bool/string) for Kaggle-null columns. Unachievable Cycle-1 'equality on every overlapping column' replaced (pandas nullable boolean serializes to Arrow bool even for all-None cols).
- [Phase 04 P06]: Cycle-1 HIGH #3 final step — src/scraper/__init__.py transitions from import-safe empty marker to public re-exports (10 symbols: FetcherSession, fetch_race_html, fetch_with_retry, enumerate_races, enumerate_race_day_urls, enumerate_races_for_day, parse_race_html, normalize_to_parquet, RaceRef, run_scrape).
- [Phase ?]: [Phase 04 P07]: UAT-Test-3 overrides Plan-04 Decision D4 — (国際)->graded_stakes mapping is a semantic error (international designation is NOT graded); removed from FLAG_CROSSWALK. GRADE_REGEX (GI/GII/GIII/重賞/ＧＩ) is the SOLE source of race_flag_graded_stakes=True.
- [Phase ?]: [Phase 04 P07]: Kaggle-side column_mapping.py (国際)->graded mapping left untouched (out of scope). Phase 6 (Data Integration) MUST reconcile the divergence before joining scraped 2022-2024 rows with 2015-2021 Kaggle rows — either drop the Kaggle mapping too, or add a race_flag_international column on both sides.
- [Phase ?]: [Phase 04 P07]: Rule 1 deviation — parse_race_html extended to harvest the second <h1> (grade-bearing, e.g. 第64回宝塚記念(GI)) into a grade_haystack fed to derive_race_flags + grade/grade_revision extraction. Required because removing the (国際) mapping exposed a latent bug: the bare <title> race_name lacks the GI token so GRADE_REGEX never fired, leaving the G1 fixture graded-less. Public race_name stays bare per Plan-04 P04.
- [Phase ?]: [Phase 04 P08]: UAT-Test-6 FIX -- enumerate_race_day_urls now builds /race/list/{YYYYMM}/ (live-verified). Prior /race/calendar/ form returns 0 racing-day links. Two-layer regression guard: URL-contract test + golden calendar fixture parse test.
- [Phase ?]: [Phase 04 P08]: Per-day blind-URL construction deliberately NOT adopted -- non-racing day's /race/list/{YYYYMMDD}/ page silently returns prior racing day's race links. Month-listing strategy avoids false attribution (T-04-18).

### Pending Todos

None yet.

### Blockers/Concerns

None yet.

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-06-14T05:03:25.215Z
Stopped at: Phase 04 plan 04-08 complete (UAT-Test-6 URL blocker closed; phase 04 fully complete)
Resume file: .planning/phases/04-scraping-infrastructure-race-data/04-08-SUMMARY.md
