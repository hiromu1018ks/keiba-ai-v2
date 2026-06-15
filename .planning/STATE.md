---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: "Completed 07-04-PLAN.md (trainer: train_fold_model + collect_oof_predictions + train_final_model)"
last_updated: "2026-06-15T15:27:31.281Z"
last_activity: 2026-06-15 -- Phase 07 execution started
progress:
  total_phases: 10
  completed_phases: 5
  total_plans: 32
  completed_plans: 30
  percent: 50
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-10)

**Core value:** 推定的中確率に対してオッズが高い三連複を特定し、バックテストで回収率を検証できること
**Current focus:** Phase 07 — model-a-top-3-probability

## Current Position

Phase: 07 (model-a-top-3-probability) — EXECUTING
Plan: 7 of 8
Status: Ready to execute
Last activity: 2026-06-15 -- Phase 07 execution started

Progress: [████░░░░░░] 42%

## Performance Metrics

**Velocity:**

- Total plans completed: 27
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 5 | - | - |
| 02 | 3 | - | - |
| 03 | 5 | - | - |
| 04 | 8 | - | - |
| 06 | 3 | - | - |

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
| Phase 06 P01 | 846 | 3 tasks | 4 files |
| Phase 06 P02 | 777 | 2 tasks | 3 files |
| Phase 06 P03 | 2100 | 2 tasks | 3 files |
| Phase 07 P01 | 967 | 3 tasks | 10 files |
| Phase 07 P02 | 955 | 2 tasks | 2 files |
| Phase 07 P03 | 688 | 2 tasks | 2 files |
| Phase 07 P05 | 792 | 2 tasks | 2 files |
| Phase 07 P06 | 533 | 2 tasks | 4 files |
| Phase 07 P04 | 895 | 2 tasks | 3 files |

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
- [Phase 06 P01]: D-01 applied — removed レース記号/(国際) -> race_flag_graded_stakes from KAGGLE_COLUMN_MAP (Kaggle side now matches Phase 4 P07 scraper-side decision). Graded detection on both corpora now comes from the single _GRADE_REGEX authority via derive_race_flags. Regenerated graded_stakes=True count = 838 (deterministic).
- [Phase 06 P01]: D-02 applied — regenerated Kaggle race/entry/result Parquet to data/standard/kaggle/ subdir with SCHEMA_DTYPE_MAP nullable dtypes. Zero Arrow-null columns; race_flag_*=bool; distance=int64; win_odds/horse_weight=double. race_date stays string (MEDIUM #5 — code-authoritative contract supersedes CONTEXT.md datetime note).
- [Phase 06 P01]: HIGH #2 cycle-3 resolved — convert(core_tables_subdir='kaggle') SKIPS odds/payoff writes entirely (not to root, subdir, or anywhere). Phase 5 seed at data/standard/{odds_trifecta,payoff}.parquet SHA-256 verified identical pre/post regen.
- [Phase 06 P01]: HIGH #3 cycle-3 resolved — 06-01-T3 does NOT call run_all_validations against the 3-table kaggle/ subdir (it cannot pass — 5-table contract). 3-table-specific validation (schema column-set, Arrow dtype, grade-derivation determinism, validate_integrity on DataFrames) runs here. Full 8-point run_all_validations deferred to 06-03-T2 against unified root.
- [Phase 06 P01]: BLOCKER-1 resolved — regenerated Kaggle race/entry/result written to data/standard/kaggle/ as a STABLE separate input path for 06-02 idempotent integration. _UNMAPPED_RACE_FLAGS expanded from 7 to 8 entries (graded_stakes added — its only text source mapping is now gone).
- [Phase ?]: [Phase 06 P02]: HIGH #5 idempotency via kaggle_input_dir separate path (default standard_dir/kaggle) -- integration reads Kaggle from a STABLE separate input, never its own output; byte-identical re-run proven by test_integration_is_idempotent.
- [Phase ?]: [Phase 06 P02]: HIGH #6 cycle-3 + cycle-5 -- validate-before-swap via tempfile.mkdtemp staging + DEDICATED _commit_staging swap function. Transactionality model ACCURATELY described as 'validate-before-swap with idempotent recovery' (NOT perfectly atomic; mid-swap crash recoverable via re-run since integration reads only from immutable inputs). Cycle-5 isolated test patches _commit_staging directly (NOT global os.replace) and mutates the race input to make the mixed-generation state observable.
- [Phase ?]: [Phase 06 P02]: HIGH #8b cycle-4 production fix + cycle-5 TEST ISOLATION -- hard-violation filter extended to 'duplicate' OR 'orphan' OR 'mismatch' OR '1-to-1'. The latter two tokens are load-bearing: 'horse_race_id mismatch: entry/result are not 1-to-1' at normalizer.py:330-334 contains NEITHER 'duplicate' NOR 'orphan'. Cycle-5 test uses DISJOINT unique horse_race_ids (entry=E1/S_E, result=R1/S_R); validate_integrity returns EXACTLY ONE violation containing 'mismatch' -- proving the token is the sole classifier.
- [Phase 06 P03]: CYCLE-6 gate widening (commit 3c5b233, applied pre-execution) -- preflight month-set expected start widened from 2022-01 to 2021-08 because the actual D-06 scrape began 2021-08, filling the Kaggle gap (Kaggle ends 2021-07-31; boundary clean, no overlap). D-07 '実データ全部（2015-2026/5）' embraces the extra 2021-Q3/Q4 real data. 58 expected months. Preflight PASSED against real corpus (set equality, 0 missing, 0 extra, 0 invalid).
- [Phase 06 P03]: UNIFIED CORPUS DELIVERED (DATA-05) -- integrate_standard_layer wrote race=38009 / entry=534953 / result=534953 rows (Kaggle 21929/311806/311806 + scraped 16080/223147/223147). Full 8-point run_all_validations overall_pass=True with UNIFIED source_stats. odds/payoff SHA-256 byte-identical pre/post (D-05). per-period graded: kaggle=893, scraped=578 (both match grade-regex). EXPECTED_FLOOR '2026-05-01' satisfied (actual_scraped_max=2026-05-31); 202605 partition non-empty (322 rows). PK-set union equality for all 3 tables. RULE 1 fix in validate_schema_conformance: case-insensitive 'float' substring so pandas nullable Float64 (Phase 4 cycle-3 #1 authority for nullable-int fields) is accepted.
- [Phase 06 P03]: D-07 scope LOCKED at 2015-2026/5 (actual_scraped_max=2026-05-31). ROADMAP success criterion #3 still reads '2015-2024' -- text update DEFERRED to Phase 9 per 06-CONTEXT.md Deferred Ideas. D-07 takes precedence as the LOCKED contract.
- [Phase 06 P03]: DEFERRED to Phase 3 re-run -- feature_generator TypeError (np.select empty condlist) on the larger unified corpus; 2 tests fail in tests/pipeline/test_feature_generator.py. Owning phase = Phase 3 (explicitly deferred per 06-CONTEXT.md). Corpus itself is correct (8-point validation green). See .planning/phases/06-data-integration/deferred-items.md.
- [Phase ?]: [Phase 07 P01]: src.ml/__init__.py ships as import-safe empty marker (Phase 4 P01 analog); public re-exports deferred to Plan 07-07. Wave 0 scaffold only — no production src/ml/* symbols created.
- [Phase ?]: [Phase 07 P01]: tests/ml/conftest.py hermetic fixtures — sample_feature_df keeps jockey/trainer as pandas CategoricalDtype (D-16 native categoricals, no one-hot), grade stays object/string with NaN preserved (Pitfall #4); popularity/win_odds live in sample_entry_df (separate) so leakage audit on feature df is empty by construction. 24 skip-state test cases named per RESEARCH Test Map + PATTERNS planner directives.
- [Phase ?]: test
- [Phase ?]: [Phase 07 P02]: horse_race_id format is NO underscore f'{race_id}{horse_number:02d}' — verified against data/standard/entry.parquet (534,953/534,953 = 100% match). EntrySchema docstring '{race_id}_{horse_number:02d}' is WRONG; real data wins (Pitfall #2 VERIFIED).
- [Phase ?]: [Phase 07 P02]: UNIFIED empty-list [] is the sole expected_counts bypass sentinel. Empty dict {} raises TypeError (Cycle-2 HIGH #2 + Cycle-5 MEDIUM truthy guard: isinstance(dict) and expected_counts).
- [Phase ?]: [Phase 07 P02]: load_features performs read-boundary sort_values(['race_date','race_id','horse_number']) + reset_index + is_monotonic_increasing assert. On-disk features_train.parquet is NOT chronologically ordered (verified False pre-sort); GroupTimeSeriesSplit (07-03) requires ascending input. train/holdout DataFrames RETAIN race_date column so trainer passes dates=df['race_date'] to splitter.split (Cycle-2 HIGH #1).
- [Phase ?]: [Phase 07 P02]: Rule 2 fix — gated inline skip (os.environ RUN_GATED != '1' -> pytest.skip) added to both gated tests, mirroring tests/scraper/test_end_to_end.py:713-720 live pattern. pyproject.toml gated marker only suppresses PytestUnknownMarkWarning and does NOT auto-skip; without inline skip gated tests would run in CI against the real corpus.
- [Phase 07 P03]: [Phase 07 P03]: GroupTimeSeriesSplit is bespoke (NOT mlxtend) per CLAUDE.md 'Use Instead' — Phase 8/9 reusable asset, no external dep. n_splits+1 date-block chunk scheme (Codex HIGH #1 fix): chunk 0 = warm-up train always in every fold's training set, so fold 0 train is non-empty. Legacy n_splits-chunk had fold 0 train = chunks[:0] = empty (structural bug).
- [Phase 07 P03]: [Phase 07 P03]: Cycle-3 HIGH fix — chunking is date-block-aware (race_count -> unique race_date blocks). All race_ids sharing a date are an atomic block inside one chunk; a race_date can never straddle a train/val boundary. max(train_dates) < min(val_dates) is now a GENUINE INVARIANT (holds by construction), so the strict per-fold assertion NEVER raises on JRA real data (mean 30.75 races/date, zero single-race dates). Legacy race-count chunking placed >=1 of 5 inner boundaries inside a date for any 6-chunk split, halting the production 5-fold run via AssertionError.
- [Phase 07 P03]: [Phase 07 P03]: Cycle-2 HIGH #1 fix — split(X, y, groups, dates=None) takes dates as an explicit arg so the per-fold temporal-order assertion ALWAYS fires when dates are provided (X column-presence independent). Legacy gate ('X is DataFrame with race_date column') was dead code because trainer passes X=df[feature_columns] (race_date in drop_columns). trainer.collect_oof_predictions (07-04) will pass dates=df['race_date']. Cycle-5 MEDIUM: dates=None + X-lacks-race_date raises explicit ValueError (not silent skip). Cycle-5 LOW: defensive assert each race_id maps to exactly one race_date.
- [Phase ?]: [Phase 07 P05]: apply_calibrator signature is (iso, raw_preds) ONLY — Pitfall #5 enforced structurally (no labels parameter exists), not just by convention. test_leak_free_calibration uses inspect.signature to lock this for forward compatibility.
- [Phase ?]: [Phase 07 P05]: load_calibrator raises FileNotFoundError (not silent None) on missing path — at Phase 8 Harville EV time, a missing calibrator must fail loud rather than return an unfitted estimator (Rule 2 missing-critical-functionality fix).
- [Phase ?]: [Phase 07 P05]: Codex HIGH #2 (OOF = validation chunks only, warm-up excluded) is a fit_calibrator docstring CONTRACT, not a runtime assertion — len(oof_raw) < training-window check is the caller's (07-04 collect_oof_predictions) responsibility because calibrator.py cannot know the training-window row count.
- [Phase ?]: [Phase 07 P05]: Wave 0 skeleton shipped 3 TestCalibrator tests; plan requires 4. test_save_load_roundtrip ADDED in Task 2 (not just unskipped) — covers D-15 .joblib round-trip + FileNotFoundError. _manual_ece helper kept local; canonical ECE belongs to 07-06 evaluator (no duplication).
- [Phase 07]: [Phase 07 P06]: D-09 race-level Top-3 recall deferred to 07-07 run_train (Cycle-5 MEDIUM option b). evaluate() is array-only (no race grouping); D-09 needs race_id which 07-07 retains.
- [Phase 07]: [Phase 07 P06]: compute_ece returns 0.0+warning on empty input; compute_popularity_baseline returns auc=0.5+n_rows=0 on all-NaN fixture (defensive, not crash).
- [Phase 07]: [Phase 07 P06]: evaluate() emits logger.warning when ece_calibrated>=0.02 (D-11 smell, T-07-06-02). Pitfall #5 leak prevention lives in calibrator.apply_calibrator (structural, no labels).
- [Phase 07]: [Phase 07 P06]: reliability_diagram uses function-local matplotlib.use('Agg')+import so compute_ece/evaluate never pay matplotlib cost. Headless-safe (T-07-06-03).
- [Phase ?]: [Phase 07 P04]: Pitfall #1 VERIFIED — train_fold_model uses callbacks=[lgb.early_stopping(...), lgb.log_evaluation(...)] ONLY; early_stopping_rounds= fit() kwarg AST-forbidden (LightGBM 4.x removed it).
- [Phase ?]: [Phase 07 P04]: Codex HIGH #2 — len(oof_df) < len(df) is a CONTRACT (warm-up chunk 0 excluded from OOF); forcing warm-up predictions would leak into Isotonic calibration.
- [Phase ?]: [Phase 07 P04]: Codex HIGH #5/#6 — feature_columns explicit arg + two-stage full retrain (Stage 1 best_iteration decision, Stage 2 fresh classifier on ALL rows at fixed iteration).
- [Phase ?]: [Phase 07 P04]: Cycle-2 HIGH #1 — collect_oof_predictions forwards dates=df['race_date'] to splitter.split so per-fold temporal-order assertion always fires.

### Pending Todos

None yet.

### Blockers/Concerns

yet.

- Phase 5 (Trifecta Odds Scraping) DEFERRED — 過去レースの全通り三連複オッズが無料ソースから取得不可。netkeiba結果ページは的中組1件のみアーカイブ(実データ確認済み)、ライブオッズページは過去分を保持しない、JRA公式も全通り履歴を無料スクレープ可能な形では保持しない。PIVOT: Phase 7-9(EV/backtest)はPhase 4取得済みの単勝オッズからHarville展開した三連複含意オッズを市場プロキシとして進める(実三連複市場特有の非効率性は検出不可)。RESUME条件: 2026年以降の前方オッズ収集、または有料プロバイダ(JV-Data等)導入時。Phase 5 CONTEXT.mdは保留状態で保持・再開時に再利用可。

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Quick Tasks Completed

| Date | Slug | Summary |
|------|------|---------|
| 2026-06-14 | add-click-cli-wrapper-for-run-scrape-scr | click 8.x CLI (`keiba` console-script) wrapping `run_scrape` — `scrape` (live) + `status` (parquet aggregation) subcommands. Note: used `[project.scripts]` (PEP621/setuptools) not spec's `[tool.poetry.scripts]`. |
| 2026-06-14 | tqdm-orchestrator-py-cli-py | tqdm 進捗バーを `run_scrape` に追加（`progress: bool = True`、`total=len(race_refs)` 切り詰め前、max_races truncate 時に `smoke N/total` postfix、`file=sys.stderr`）。`scrape` CLI に `--no-progress` フラグ追加（`progress=not no_progress` を伝達）。テスト: 既存呼び出しに `progress=False`、出力非依存テスト + フラグテスト追加。Commit 6714f87. |
| 2026-06-14 | tqdm-enumerate-races | `enumerate_races` の月ループに tqdm 進捗バーを追加（`desc='Enumerating'`, `unit='month'`, `total=len(months)`, `file=sys.stderr`）。広範囲スクレイプ時の列挙フェーズ無出力（「止まったように見える」問題）を解消。月ループを `(year,month)` リスト化（振る舞い保存）。`run_scrape` から `progress=progress` を両呼び出しに伝達。テスト7件に `progress=False` + 出力非依存テスト追加。test_orchestrator のモックも `**kwargs` 化（Rule 1）。Commit 6960111. |
| 2026-06-15 | 260615-jdx feature-generator-np-select-condlist-cor | feature_generator の np.select TypeError を根本修正。真因は「空 condlist」ではなく**dtype**：統一 corpus では `finish_note` が pandas nullable `string`（Phase 4 cycle-3 #1）で `==` が nullable boolean Series を生み、np.select が native bool を要求して TypeError。各 condlist を `to_numpy(dtype=bool, na_value=False)` で強制（pd.NA→False→default "finished" 枝で分類論理は非退化、TestTargetVariable 11テスト不変 + 新規 nullable 回帰テスト追加）。統一 corpus(534,953行)向けに features_train/pred を再生成（各534,953行）。feature_generator テスト全 green、フルスイート 513 passed/1 skipped/0 failed。DEFERRED-1 解消。Commits 516fa46, bcb0716. |

## Session Continuity

Last session: 2026-06-15T15:27:31.275Z
Stopped at: Completed 07-04-PLAN.md (trainer: train_fold_model + collect_oof_predictions + train_final_model)
Resume file: .planning/phases/07-model-a-top-3-probability/07-07-PLAN.md
