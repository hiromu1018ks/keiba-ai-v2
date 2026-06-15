# Roadmap: 競馬AI 三連複EVシステム

## Overview

Build a CLI-based system that identifies undervalued trifecta (三連複) combinations in JRA horse racing by estimating each horse's top-3 finish probability via LightGBM, then comparing against market odds to find positive expected value bets. The roadmap progresses from data foundation (schema, Kaggle conversion, feature engineering) through data expansion (scraping 2022-2024 race results and full trifecta odds), then into the ML pipeline (probability model, EV calculation), and concludes with walk-forward backtesting and CLI reporting to validate whether the system generates positive ROI.

**Data scope:** 2015-2024 (10 years). Kaggle covers 1986-2021, but only the 2015-2021 window is used. Scraping covers 2022-2024. Output format is Parquet.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Data Schema & Leak Audit** - Define the 3-layer schema (raw/standard/feature) with column types, and build a pre-race/post-race audit mechanism to prevent data leakage (completed 2026-06-11)
- [x] **Phase 2: Kaggle Data Pipeline** - Convert Kaggle race result CSVs (2015-2021) to standard-layer Parquet with validated schema conformance (completed 2026-06-11)
- [x] **Phase 3: Feature Engineering** - Generate ML-ready features (race, horse form, jockey/trainer stats, recent performance) from standard data with temporal safety (completed 2026-06-12)
- [x] **Phase 4: Scraping Infrastructure & Race Data** - Build fetch/parse/normalize pipeline and scrape 2022-2024 JRA race results into standard Parquet
- [ ] **Phase 5: Trifecta Odds Scraping** - Scrape all-combination trifecta odds (up to 816 per race) for 2022-2024 and save in standard format
- [x] **Phase 6: Data Integration** - Merge Kaggle (2015-2021) and scraped (2022-2024) datasets into a unified 2015-2024 standard Parquet corpus (completed 2026-06-15)
- [ ] **Phase 7: Model A -- Top-3 Probability** - Build LightGBM top-3 probability model (2018-2024 train, 2025-2026/5 holdout per D-05) with race-grouped temporal CV (GroupTimeSeriesSplit), Isotonic calibration, and popularity-baseline comparison on holdout (reference-only per D-07/D-08)
- [ ] **Phase 8: EV Calculation Engine** - Compute Harville trifecta probabilities, calculate EV for all combinations, filter by threshold, enforce point caps, and mark skip races
- [ ] **Phase 9: Walk-Forward Backtest** - Run walk-forward expanding-window backtest over 2015-2024, compute ROI/hit rate/drawdown, and produce detailed breakdowns
- [ ] **Phase 10: CLI & Reporting** - Build Click-based CLI for all operations and CSV output for backtest results and bet candidates

## Phase Details

### Phase 1: Data Schema & Leak Audit

**Goal**: The standard schema contract and data leakage prevention mechanism are defined and documented, forming the foundation all downstream data work depends on
**Depends on**: Nothing (first phase)
**Requirements**: DATA-01, DATA-04
**Success Criteria** (what must be TRUE):

  1. Standard schema defines all tables (race, entry, result, odds_trifecta, payoff) with column names, data types, and nullability documented
  2. Every column in the Kaggle dataset is classified as pre-race or post-race, and the classification is persisted in a machine-readable format
  3. An audit function can validate that a feature DataFrame contains only pre-race columns, flagging any post-race leakage

**Plans**: 5 plans
Plans:
**Wave 1**

- [x] 01-01: Project infrastructure + race/entry schema (DATA-01)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02: result/odds_trifecta/payoff schema (DATA-01)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-03: Audit function + tests with EntrySchema and ResultSchema coverage (DATA-04)

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 01-04: Kaggle 1-to-1 column mapping verification + JSON schema export function (DATA-01, DATA-04)

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 01-05: Package integration + __init__.py re-exports (DATA-01, DATA-04)

### Phase 2: Kaggle Data Pipeline

**Goal**: Kaggle race data from 2015-2021 is converted to standard-layer Parquet files, giving the project a working raw-to-standard data pipeline
**Depends on**: Phase 1
**Requirements**: DATA-02
**Success Criteria** (what must be TRUE):

  1. Kaggle CSV files are read and converted to standard-layer Parquet with correct schema conformance (validated by Pydantic or schema checks)
  2. The 2015-20221 date range is correctly filtered from the full Kaggle dataset (1986-2021), and output is single-file Parquet per table (per D-07)
  3. Row counts and key distributions in the output Parquet match expectations from the source CSV (no silent data loss)

**Plans**: 3 plans
Plans:
**Wave 1**

- [x] 02-01: Column mapping + pyarrow + package structure (DATA-02)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-02: CSV-to-Parquet converter + test fixtures + integration tests (DATA-02)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 02-03: Data quality validators (8 D-05 checks) + end-to-end pipeline validation (DATA-02)

### Phase 3: Feature Engineering

**Goal**: ML-ready feature vectors are generated from standard-layer data, providing the training inputs that Model A requires
**Depends on**: Phase 2
**Requirements**: DATA-03
**Success Criteria** (what must be TRUE):

  1. Feature layer generates all specified features: race context (course, distance, surface, condition, field size, post position), horse identifiers, jockey/trainer categorical features, recent form (past performance metrics), last-3F time, and running position. Note: popularity/win odds are excluded per D-15 (post-race) -- ROADMAP criterion #1 lists them but CONTEXT.md D-15 takes precedence.
  2. All rolling/lag features use temporal shift (`.shift(1)`) so no future information leaks into any row
  3. Categorical columns use pandas CategoricalDtype for native LightGBM integration
  4. Feature output passes the Phase 1 audit function (zero post-race columns detected)

**Plans**: 5 plans (Cycle 3 revision -- root cause fixes for all 8 HIGH review concerns)
Plans:
**Wave 1**

- [x] 03-01: Module skeleton + collision-safe horse_entity_key + inner-join merge + race context + horse basic features (DATA-03)

**Wave 2** *(blocked on 03-01)*

- [x] 03-02: Margin conversion + race-boundary finish_time z-score (DATA-03)

**Wave 3** *(blocked on 03-02)*

- [x] 03-03: Valid-start-filtered lag features (45 cols) + sum-based race-level jockey/trainer stats with exact D-08 intersection (DATA-03)

**Wave 4** *(blocked on 03-03)*

- [x] 03-04: Target variable (6 result_status categories) + debut flag (DATA-03)

**Wave 5** *(blocked on 03-04)*

- [x] 03-05: Static feature allowlist + categorical conversion + temporal invariance tests + leakage audit + Parquet output (DATA-03)

### Phase 4: Scraping Infrastructure & Race Data

**Goal**: 2022-2024 JRA race results and entry information are scraped and available in standard Parquet, extending the dataset beyond Kaggle's 2021 cutoff
**Depends on**: Phase 1
**Requirements**: SCRP-01, SCRP-02, SCRP-03, SCRP-05
**Success Criteria** (what must be TRUE):

  1. Scraper follows fetch/parse/normalize separation: raw HTML is saved before parsing, and parsing reads from saved HTML (not live requests)
  2. 2022-2024 race results and entry data are scraped and converted to standard-layer Parquet matching the same schema as Kaggle data
  3. Duplicate page fetches are prevented: already-downloaded HTML is reused without re-requesting
  4. Rate limiting is enforced so the scraper does not trigger anti-bot blocks

**Plans**: 8 plans (6 baseline + 2 gap-closure for UAT-Test-3 flag misclassification and UAT-Test-6 broken calendar URL)
Plans:
**Wave 1**

- [x] 04-01: Import-safe package skeleton + dependency install (SCRP-01)

**Wave 2** *(blocked on 04-01)*

- [x] 04-02: 3-level calendar enumeration returning RaceRef(race_id, race_date) + race_id validation (SCRP-01, SCRP-02)

**Wave 3** *(04-03 and 04-04 run in parallel)*

- [x] 04-03: Shared Playwright FetcherSession + atomic fetch + dedup + block-page detection (SCRP-01, SCRP-02, SCRP-05)
- [x] 04-04: Header-driven BS4 parser + corrected COURSE_CODE_MAP + flag crosswalk + golden HTML fixtures (SCRP-01, SCRP-03)

**Wave 4** *(blocked on 04-03 and 04-04)*

- [x] 04-05: Strict typed normalizer + schema reindex + integrity validation + atomic partitioned Parquet (SCRP-01, SCRP-03)

**Wave 5** *(blocked on 04-02, 04-03, 04-04, 04-05)*

- [x] 04-06: Orchestrator + fixture-based end-to-end test + __init__ re-exports + ruff/mypy gate (SCRP-01, SCRP-02, SCRP-03, SCRP-05)

**Wave 6 — Gap Closure** *(04-07 and 04-08 run in parallel; fix UAT-Test-3 and UAT-Test-6)*

- [x] 04-07: Remove (国際)->graded_stakes mapping (UAT-Test-3 flag misclassification fix) (SCRP-01, SCRP-03)
- [x] 04-08: Fix calendar URL from /race/calendar/ to /race/list/ + golden regression fixture (UAT-Test-6 blocker fix) (SCRP-01, SCRP-02)

### Phase 5: Trifecta Odds Scraping

**Goal**: All-combination trifecta odds (up to 816 combinations per race) for 2022-2024 are scraped and stored, providing the odds data needed for accurate EV calculation
**Depends on**: Phase 4
**Requirements**: SCRP-04
**Success Criteria** (what must be TRUE):

  1. For each 2022-2024 race, all trifecta combinations (C(n,3) where n = field size) are scraped with their odds values
  2. Output is stored as race ID, combination tuple, and odds in a standard-format Parquet file
  3. Odds data spot-checks against known race results match (no systematic scraping or parsing errors)

**Plans**: TBD

Plans:

- [ ] 05-01: TBD
- [ ] 05-02: TBD

### Phase 6: Data Integration

**Goal**: Kaggle (2015-2021) and scraped (2022-2024) datasets are merged into a single unified 2015-2024 corpus in standard Parquet, ready for feature engineering and model training
**Depends on**: Phase 2, Phase 4
**Requirements**: DATA-05
**Success Criteria** (what must be TRUE):

  1. A single unified Parquet dataset covers 2015-2024 with no duplicate races between Kaggle and scraped sources
  2. Schema is identical across the full date range (Kaggle-origin and scraped-origin rows are indistinguishable in the standard layer)
  3. Row counts and date coverage can be verified: the combined dataset spans 2015-01-01 through 2024-12-31 with expected volume

**Plans**: 3 plans (revised under --reviews to address 14 HIGH cross-AI concerns — Kaggle-side grade detector, idempotent transactional integration, per-partition preflight, SHA-256 odds/payoff protection)

Plans:
**Wave 1**

- [x] 06-01: D-01 `(国際)` removal + Kaggle-side grade detector (derive_race_flags) + D-02 nullable-dtype regen + odds/payoff snapshot-protected + 8-point verification with source_counts/stats (DATA-05)

**Wave 2** *(blocked on 06-01)*

- [x] 06-02: src/pipeline/integration.py (idempotent via separate kaggle_input_dir, corpus-level tmp-swap, column-set equality assert, validate_integrity-backed FK test, audit_leakage called) + tests/pipeline/test_integration.py (9 tests across TestIntegrationHermetic ungated + TestUnifiedCorpus gated) (DATA-05)

**Wave 3** *(blocked on 06-01, 06-02)*

- [x] 06-03: Per-partition preflight (PASSED: 58 partitions 202108..202605, month-set equality, zero-tolerance gate) + invoke integrate_standard_layer() (DONE: race=38009/entry=result=534953 unified) + odds/payoff SHA-256 byte-identical pre/post + 8-point run_all_validations overall_pass=True (UNIFIED source_stats) + per-period graded counts (kaggle=893, scraped=578) + robust date-range (dmin=2015-01-04, dmax=actual_scraped_max=2026-05-31 >= EXPECTED_FLOOR '2026-05-01'; 202605 partition non-empty) + PK-set union for all 3 tables + human inspection gate (DATA-05) — **Task 3 human-verify APPROVED 2026-06-15; plan COMPLETE**

> **Note (D-07 scope extension):** The unified corpus covers 2015-2026/5 (actual_scraped_max=2026-05-31), exceeding the original success-criterion #3 text "2015-2024". Per CONTEXT.md D-07 ("実データ全部（2015-2026/5）") and 06-CONTEXT.md Deferred Ideas, the ROADMAP success-criterion text update is DEFERRED to Phase 9 backtest planning. D-07 is the LOCKED contract that takes precedence; the actual coverage (2015-2026/5) is verified TRUE in 06-03-SUMMARY.md.

### Phase 7: Model A -- Top-3 Probability

**Goal**: A LightGBM model predicts each horse's probability of finishing in the top 3, trained on 2018-2024 data (D-05), validated with race-grouped temporal cross-validation (GroupTimeSeriesSplit), calibrated via Isotonic regression (holdout ECE < 0.02 per D-11), and compared against a popularity-rank baseline on holdout as reference information (D-07/D-08 — beating the baseline is not a required gate because the pure-properties model excludes odds per 03-CONTEXT D-15)
**Depends on**: Phase 3, Phase 6
**Requirements**: MODA-01, MODA-02, MODA-03, MODA-04
**Success Criteria** (what must be TRUE — updated Cycle-2 HIGH #4 fix to match LOCKED decisions D-05/D-07/D-08; stale "2015-2023" / "beat baseline on OOF" wording replaced):

  1. LightGBM binary classifier outputs p_top3 for each horse in a race, trained on **2018-2024 data** with temporal splits (D-05/D-01 — window pulled forward from "2015-2023" to mitigate concept drift; holdout = 2025-01〜2026-05 per D-02)
  2. GroupTimeSeriesSplit (race_id-grouped, n_splits+1 expanding-window chunks) is used for all cross-validation; no future data appears in any training fold (temporal-order assertion enforced on the real execution path — Cycle-2 HIGH #1)
  3. Model AUC on **holdout** is compared against the popularity-rank baseline (horses ranked by win odds) as **reference information**; beating the baseline is NOT a required success gate because the pure-horse-properties model (odds excluded per 03-CONTEXT D-15) is expected to rarely beat market wisdom on AUC alone (D-07/D-08 — true EV edge is validated in Phase 9 ROI). Baseline is reported in evaluation_report.md.
  4. OOF predictions are calibrated via Isotonic regression (fit on OOF validation chunks only — warm-up excluded per Codex HIGH #2) and applied to holdout: holdout ECE < 0.02 (D-11), verified via reliability diagram. **oof_rows is recorded in metrics.json** (Cycle-2 HIGH #3 — producer/consumer contract between 07-07 run_train and 07-08 verify).

**Plans**: 8 plans

Plans:
**Wave 0**

- [x] 07-01: Environment install (libomp + scikit-learn + matplotlib + joblib) + tests/ml/ scaffolding (conftest + 6 test skeletons + gated marker)

**Wave 1** *(07-02, 07-03, 07-05, 07-06 run in parallel — no file overlap; Codex HIGH #3 fix: 07-04 moved to Wave 2 because it runtime-depends on 07-03's split_train_validation)*

- [x] 07-02: data_loader.py — features_train 読込 + dtype 整備 + horse_race_id derive + window 分割 + audit_leakage + expected_counts bypass (MODA-01, Codex HIGH #4 fix)
- [x] 07-03: group_timeseries_split.py — sklearn BaseCrossValidator 準拠の race_id グループ化時系列CV・n_splits+1 chunk scheme (MODA-02, Codex HIGH #1 fix)
- [x] 07-05: calibrator.py — Isotonic OOF(val chunks only)→holdout リーク防止パターン (MODA-04, Codex HIGH #2 fix)
- [x] 07-06: evaluator.py + baseline.py — ECE/metrics/reliability diagram + 人気ベースライン AUC (MODA-04, MODA-03)

**Wave 2** *(blocked on Wave 1 completion; 07-04 depends on 07-03 per Codex HIGH #3 fix)*

- [x] 07-04: trainer.py — LightGBM sensible defaults + early stopping callback API + OOF 収集(val chunks only) + 二段階全量再学習 + feature_columns 明示的引数 (MODA-01, Codex HIGH #2/#5/#6 fixes)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 07-07: run_train.py orchestrator + config/phase7_model_a.yaml (feature_columns キー追加) + src/ml/__init__.py re-exports + hermetic E2E (expected_counts bypass) (MODA-01..04, Codex HIGH #2/#4/#5 fixes)

**Wave 4** *(blocked on Wave 3 completion)*

- [ ] 07-08: 実データ phase gate — python -m src.ml.run_train で6成果物生成 + 人間 verify（D-07 AUC目安0.75 + D-11 ECE<0.02 + holdout retune 禁止）(MODA-01..04, Codex HIGH #2/#7 fixes)

### Phase 8: EV Calculation Engine

**Goal**: The system computes expected value for every trifecta combination in a race using Harville probabilities and market odds, then filters to only high-EV bets within a point cap
**Depends on**: Phase 7
**Requirements**: EVCALC-01, EVCALC-02, EVCALC-03, EVCALC-04, EVCALC-05
**Success Criteria** (what must be TRUE):

  1. Harville conditional probability is correctly computed for all C(n,3) trifecta combinations from individual p_top3 values, summed over 6 permutations for 三連複
  2. EV (estimated probability x trifecta odds) is calculated for every combination and the results are rankable
  3. An EV threshold filters combinations: only bets above the threshold are selected, and races with no qualifying bets are marked as "skip"
  4. A configurable point cap limits the maximum number of bet combinations per race

**Plans**: TBD

Plans:

- [ ] 08-01: TBD
- [ ] 08-02: TBD
- [ ] 08-03: TBD

### Phase 9: Walk-Forward Backtest

**Goal**: A walk-forward backtest over 2015-2024 validates whether the EV-based betting strategy produces positive ROI, with detailed performance breakdowns
**Depends on**: Phase 8
**Requirements**: BKTS-01, BKTS-02, BKTS-03, BKTS-04
**Success Criteria** (what must be TRUE):

  1. Walk-forward backtest with expanding windows trains on past data, predicts on future races, and never uses future information (strict temporal integrity)
  2. Core metrics are computed: ROI (recovery rate), hit rate, total investment, total payout, net profit, and maximum drawdown
  3. Detailed breakdowns are available by month, odds band, EV band, and race condition (course, distance, surface)
  4. Final-odds vs. at-post odds difference is documented and its impact on results is quantified

**Plans**: TBD

Plans:

- [ ] 09-01: TBD
- [ ] 09-02: TBD
- [ ] 09-03: TBD

### Phase 10: CLI & Reporting

**Goal**: All system operations are accessible via a Click-based CLI, and backtest results and bet candidates are exportable as CSV files
**Depends on**: Phase 9
**Requirements**: OUTP-01, OUTP-02, OUTP-03
**Success Criteria** (what must be TRUE):

  1. CLI provides subcommands for data conversion, model training, prediction, and backtesting (e.g. `keiba convert`, `keiba train`, `keiba predict`, `keiba backtest`)
  2. Backtest results are output as CSV with all metrics (ROI, hit rate, drawdown) and per-race bet details
  3. Bet candidate predictions are output as CSV with race ID, combination, estimated probability, odds, and EV

**Plans**: TBD

Plans:

- [ ] 10-01: TBD
- [ ] 10-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10
Note: Phase 4 (Scraping) depends only on Phase 1, so it can execute in parallel with Phases 2-3 if desired.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Data Schema & Leak Audit | 5/5 | Complete    | 2026-06-11 |
| 2. Kaggle Data Pipeline | 3/3 | Complete    | 2026-06-11 |
| 3. Feature Engineering | 5/5 | Complete | 2026-06-12 |
| 4. Scraping Infrastructure & Race Data | 8/8 | Complete    | 2026-06-14 |
| 5. Trifecta Odds Scraping | 0/? | Not started | - |
| 6. Data Integration | 3/3 | Complete    | 2026-06-15 |
| 7. Model A -- Top-3 Probability | 7/8 | In Progress|  |
| 8. EV Calculation Engine | 0/? | Not started | - |
| 9. Walk-Forward Backtest | 0/? | Not started | - |
| 10. CLI & Reporting | 0/? | Not started | - |
