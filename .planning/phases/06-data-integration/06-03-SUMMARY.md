---
phase: 06-data-integration
plan: 03
subsystem: data-pipeline
tags: [integration, unified-corpus, validation, d-07, month-set-equality, expected-floor, pk-set-union, odds-payoff-sha256]

# Dependency graph
requires:
  - phase: 06-data-integration
    provides: "06-01 regenerated Kaggle race/entry/result at data/standard/kaggle/ (D-01 grade detection + D-02 nullable dtypes); 06-02 integrate_standard_layer + DEDICATED _commit_staging + extended hard-violation filter"
  - phase: 04-scraping-infrastructure-race-data
    provides: "D-06 full scrape output: 58 month partitions data/standard/scraped/{202108..202605}/ (cycle-6 widened from 2022-01 to 2021-08 — actual scrape filled Kaggle gap, clean boundary no overlap)"
  - phase: 02-kaggle-data-pipeline
    provides: "run_all_validations 8-point validator + validate_schema_conformance + validate_referential_integrity"
provides:
  - "data/standard/{race,entry,result}.parquet — UNIFIED 2015-2026/5 corpus (Kaggle 2015-2021 + scraped 2021-08..2026-05), integration executed against real data"
  - "Verified unified corpus: 8-point run_all_validations overall_pass=True with UNIFIED source_stats; odds/payoff SHA-256 unchanged; per-period graded counts match; EXPECTED_FLOOR '2026-05-01' + 202605 partition non-empty; PK-set union equality for all 3 tables"
  - "Rule 1 fix in validate_schema_conformance: case-insensitive 'float' substring so pandas nullable Float64 (Phase 4 cycle-3 #1 authority) is accepted for Optional[int] fields"
affects: [feature-regen (Phase 3 re-run — deferred), Phase 7 model training, Phase 9 backtest]

# Tech tracking
tech-stack:
  added: []  # no new deps; reused integrate_standard_layer (06-02) + run_all_validations (02)
  patterns:
    - "UNIFIED source_stats computation: source_stats computed from Kaggle+scraped COMBINED per table (NOT Kaggle-only) so validate_distributions/validate_null_rates compare identical data -> tolerance satisfied (cycle-4 fix verified)"
    - "Case-insensitive dtype substring: 'float' in actual_dtype.lower() accepts both numpy float64 AND pandas nullable Float64/Float32 — aligns validator with SCHEMA_DTYPE_MAP's deliberate Float64 storage for nullable-int fields (Phase 4 cycle-3 #1)"

key-files:
  created:
    - .planning/phases/06-data-integration/deferred-items.md  # feature_generator out-of-scope failures logged
  modified:
    - src/pipeline/validators.py  # Rule 1: case-insensitive float substring in schema_conformance
    - tests/pipeline/test_validators.py  # Rule 1: update stale Kaggle-only expected counts to unified
    - data/standard/race.parquet  # gitignored; unified 2015-2026/5
    - data/standard/entry.parquet  # gitignored; unified 2015-2026/5
    - data/standard/result.parquet  # gitignored; unified 2015-2026/5

key-decisions:
  - "D-07 scope LOCKED: unified corpus = 2015-2026/5 (actual_scraped_max=2026-05-31). ROADMAP text still says 2024-12-31 (success criterion #3) — text update DEFERRED to Phase 9 per 06-CONTEXT.md Deferred Ideas. D-07 takes precedence as the LOCKED contract."
  - "Cycle-6 gate widening KEPT (commit 3c5b233, pre-execution): preflight month-set expected start widened from 2022-01 to 2021-08 because the actual D-06 scrape began 2021-08 (fills Kaggle gap; Kaggle ends 2021-07-31, clean boundary, no overlap). 58 months total. Preflight PASSED against the real corpus (set equality, 0 missing, 0 extra, 0 invalid)."
  - "Rule 1 fix (validators.py): validate_schema_conformance's nullable-int special-case was case-sensitive ('float' in actual_dtype) and rejected pandas nullable Float64 — which SCHEMA_DTYPE_MAP deliberately uses for corner_1..4/horse_weight/weight_change/popularity per Phase 4 cycle-3 #1 (Int64 would serialize to Arrow int64 and FAIL the physical-type equality test against Kaggle's double). Fix: 'float' in actual_dtype.lower(). This made schema_conformance pass for all 5 tables; the quirk was pre-existing (Kaggle subdir produces identical warnings) but only surfaced as a blocking failure when this plan's overall_pass assertion ran."
  - "Rule 1 fix (test_validators.py): test_row_counts_within_expected_range had stale Kaggle-only expected counts (21929/311806/311806) with a 5% tolerance; the unified corpus is 38009/534953/534953 (~73% larger). Updated to unified counts."
  - "Out-of-scope DEFERRED: feature_generator TypeError (np.select empty condlist) on the larger unified corpus — 2 tests fail in tests/pipeline/test_feature_generator.py. Owning phase = Phase 3 re-run (explicitly deferred per 06-CONTEXT.md). The corpus itself is correct (8-point validation green); feature layer is a downstream consumer."

requirements-completed: [DATA-05]

# Metrics
duration: 35min
completed: 2026-06-15
---

# Phase 6 Plan 03: Unified Corpus Integration & Verification Summary

**integrate_standard_layer executed against the real 58-partition scraped corpus (202108..202605) + Kaggle kaggle/ subdir, producing the unified 2015-2026/5 data/standard/{race,entry,result}.parquet that passes the full 8-point run_all_validations (overall_pass=True) with UNIFIED source_stats, odds/payoff SHA-256 unchanged, per-period graded counts matching grade-regex derivation, EXPECTED_FLOOR '2026-05-01' satisfied, and PK-set union equality for all 3 tables**

## Performance

- **Duration:** ~35 min (2100s)
- **Started:** 2026-06-14T23:54:34Z
- **Completed:** 2026-06-15T00:29:34Z
- **Tasks:** 2/3 complete (Task 3 is the blocking human-verify checkpoint, returned to orchestrator NOT self-approved)
- **Files modified:** 2 source/test (Rule 1 fixes) + 1 new (deferred-items.md) + 3 gitignored Parquet (unified corpus)

## Task 1: Per-partition preflight — PASSED

Preflight ran against all 58 scraped partitions with the cycle-6 widened expected month-set (202108..202605).

**Cycle-5 D-07 month-set EQUALITY (primary gate):**
- expected months: 58 (202108..202605 per D-07 + cycle-6 actual-scrape floor)
- present months: 58
- missing months: 0
- extra months: 0
- `set(present_months) == set(expected_months)` → PASS (no gaps, no extras)

**Cycle-4 ZERO-TOLERANCE per-partition validity:**
- partition count: 58 (>= 40 redundant sanity: PASS)
- invalid partitions: 0
- Each partition's race/entry/result asserted NON-EMPTY via `pyarrow.parquet.ParquetFile(path).metadata.num_rows > 0` for ALL THREE files
- race_date validity: every race_date parses and its YYYYMM matches the partition dir name

**Cycle-5 STRUCTURAL MAY-2026 PROOF:**
- `202605` partition present: YES
- `202605/race.parquet` rows: 322 (> 0) → D-07 May-2026 reach satisfied

Preflight is a verification gate (no source files); the partition report is captured here. Task 1 produces no commit.

## Task 2: Integration + full verification — PASSED (with 2 Rule 1 fixes)

### Integration output

`integrate_standard_layer(Path('data/standard'))` merged the Kaggle kaggle/ subdir + all 58 scraped partitions via validate-before-swap (DEDICATED `_commit_staging`):

| Table | Kaggle rows | Scraped rows | Unified rows |
|-------|-------------|--------------|--------------|
| race  | 21,929      | 16,080       | 38,009       |
| entry | 311,806     | 223,147      | 534,953      |
| result| 311,806     | 223,147      | 534,953      |

### HIGH #17 — odds/payoff SHA-256 UNCHANGED (D-05 honored)

| File | SHA-256 | Rows | Pre == Post |
|------|---------|------|-------------|
| data/standard/odds_trifecta.parquet | `7473133c8a2c971a2f4ae26e33b9c2043801d006b6f53df9bf6244c80e740013` | 21,929 | YES (byte-identical) |
| data/standard/payoff.parquet        | `899987a8d66c91c172f9fd00c4c60c3e7b3dfa428a357ed862aa2cfbb8c8351a` | 21,987 | YES (byte-identical) |

The Phase 5 seed is preserved. `integrate_standard_layer`'s hardcoded `{race, entry, result}` allowlist (SCHEMA_BY_TABLE) is the structural guarantee — it never reads or writes the Phase 5 tables.

### HIGH #3 cycle-3 + cycle-4 — FULL 8-point run_all_validations (overall_pass=True)

`run_all_validations(raw_dir=data/raw/kaggle, parquet_dir=data/standard, source_counts, source_stats)` where source_counts + source_stats computed from UNIFIED Kaggle+scraped combined inputs (cycle-4 fix):

| Check | Result |
|-------|--------|
| row_counts | True (race=38009, entry=534953, result=534953, odds_trifecta=21929, payoff=21987) |
| schema_conformance | True (all 5 tables — see Rule 1 fix note below) |
| null_rates | True (UNIFIED source_stats — same corpus compared against itself, within tolerance=0.01) |
| distributions | True (UNIFIED source_stats — distance mean/popularity mean match within tolerance) |
| referential_integrity | True (FK integrity errors: []) |
| sample_rows | True |
| value_ranges | True |
| audit | True (informational — race leaks [], entry leaks {popularity, win_odds} per Phase 1 D-03) |
| **overall_pass** | **True** |

### HIGH #18 — per-period graded counts (match grade-regex derivation)

Split by period (race_date < '2022-01-01' = kaggle; >= '2022-01-01' = scraped):

| Period | graded_stakes actual | derive_race_flags expected | Match |
|--------|----------------------|----------------------------|-------|
| kaggle | 893 | 893 | YES |
| scraped | 578 | 578 | YES |

Unified total = 1,471 (NOT a fixed band — each period independently matches its grade-regex recompute).

### HIGH #14 cycle-5 — robust date range (EXPECTED_FLOOR '2026-05-01' + 202605 partition)

- race_date min: `2015-01-04` (in 2015-Q1: `'2015-01-01' <= '2015-01-04' <= '2015-03-31'`) ✓
- race_date max (dmax): `2026-05-31`
- actual_scraped_max: `2026-05-31`
- `dmax == actual_scraped_max` → YES (no data dropped/added during integration)
- `actual_scraped_max >= EXPECTED_FLOOR ('2026-05-01')` → YES (D-07 LOCKED scope 2015-2026/5 honored; Phase 4 D-05 '2022年1月〜2026年5月末' honored)
- `202605/race.parquet` exists + non-empty (322 rows) → YES (structural May-2026 proof)

**Per-year race counts** (each present year > 500 races):

| Year | Races |
|------|-------|
| 2015 | 3,326 |
| 2016 | 3,326 |
| 2017 | 3,329 |
| 2018 | 3,328 |
| 2019 | 3,325 |
| 2020 | 3,331 |
| 2021 | 3,329 |
| 2022 | 3,331 |
| 2023 | 3,329 |
| 2024 | 3,315 |
| 2025 | 3,335 |
| 2026 | 1,405 (Jan-May partial) |

### NEW HIGH cycle-3 — PK-set union equality (all 3 tables)

`set(output PKs) == set(union of input partition PKs)` per table:

| Table | PK | Input PK count | Output PK count | Set equality |
|-------|----|----------------|-----------------|--------------|
| race | race_id | 38,009 | 38,009 | YES |
| entry | horse_race_id | 534,953 | 534,953 | YES |
| result | horse_race_id | 534,953 | 534,953 | YES |

No silent dedup, no row loss during merge. (race_id unique: nunique==len==38009; entry horse_race_id unique: nunique==len==534953.)

### audit_leakage results

- race audit: `[]` (race is pre-race only — no post-race column leakage) ✓
- entry audit: `['popularity', 'win_odds']` (intentional per Phase 1 D-03 — these are the Harville EV proxy inputs; any OTHER leak would raise ValueError) ✓

### Schema invariant (race.parquet)

- Zero Arrow-null columns ✓
- Every `race_flag_*` column is Arrow `bool` (20 columns) ✓
- `race_date` is Arrow `string` ✓
- `distance` is Arrow `int64` ✓

### pytest integration suite

`python -m pytest tests/pipeline/test_integration.py -q` → **11 passed** (including cycle-5 isolated `test_horse_race_id_mismatch_raises` + `test_integration_partial_swap_recoverable` patching `_commit_staging`).

## Scope Resolution (MEDIUM #21)

Per CONTEXT D-07, the unified corpus covers **all real data (2015-2026/5)**. NO period filter was applied. The expected `race_date.max()` equals `actual_scraped_max` AND must be `>= EXPECTED_FLOOR '2026-05-01'`.

**ROADMAP-text-vs-actual divergence:** ROADMAP success criterion #3 still reads "2015-2024"; the actual unified corpus reaches 2026-05-31. Per CONTEXT.md Deferred Ideas, the ROADMAP text update is DEFERRED to Phase 9 backtest planning. D-07 is the LOCKED contract that takes precedence.

## Task Commits

1. **Task 1 (preflight):** no commit (verification-only gate; `<files></files>` empty; partition report captured in this SUMMARY)
2. **Task 2 (integration + Rule 1 fixes):** `08f1b35` (feat) — includes validators.py case-insensitive float fix, test_validators expected-count update, deferred-items.md

## Files Created/Modified

- `src/pipeline/validators.py` — MODIFIED. Rule 1 fix: `validate_schema_conformance` nullable-int special-case now uses `"float" in actual_dtype.lower()` so pandas nullable `Float64`/`Float32` (SCHEMA_DTYPE_MAP's deliberate storage for nullable-int fields per Phase 4 cycle-3 #1) are accepted alongside numpy `float64`/`float32`. Expanded comment documents the Phase 4 cycle-3 #1 rationale.
- `tests/pipeline/test_validators.py` — MODIFIED. Rule 1 fix: `test_row_counts_within_expected_range` expected counts updated from stale Kaggle-only (21929/311806/311806) to unified corpus (38009/534953/534953). Added docstring noting the Phase 6 corpus growth.
- `.planning/phases/06-data-integration/deferred-items.md` — NEW. Logs the 2 feature_generator test failures (out-of-scope per 06-CONTEXT.md Deferred Ideas — Phase 3 re-run owns the fix).
- `data/standard/race.parquet` — regenerated (gitignored; unified 2015-2026/5, 38,009 rows).
- `data/standard/entry.parquet` — regenerated (gitignored; unified, 534,953 rows).
- `data/standard/result.parquet` — regenerated (gitignored; unified, 534,953 rows).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] validate_schema_conformance rejected correct Float64 dtypes**
- **Found during:** Task 2 (first full 8-point run)
- **Issue:** `validate_schema_conformance` returned False for entry (horse_weight/weight_change/popularity) and result (corner_1..4) because these Optional[int] fields are stored as pandas nullable `Float64` per `SCHEMA_DTYPE_MAP` (Phase 4 cycle-3 #1 authority — Int64 would serialize to Arrow int64 and FAIL the physical-type equality test against Kaggle's double). The validator's nullable-int special-case (`if expected_cat == "int" and "float" in actual_dtype: continue`) was case-sensitive: `"float" not in "Float64"`, so the deliberate Float64 storage was flagged as a mismatch. This made `schema_conformance=False` → `overall_pass=False` → the Task 2 assertion failed. The same warnings appeared against the Kaggle kaggle/ subdir in isolation (pre-existing quirk), but only became a blocking failure when this plan's overall_pass assertion ran.
- **Fix:** Changed the substring check to `"float" in actual_dtype.lower()`. This accepts both numpy `float64`/`float32` AND pandas nullable `Float64`/`Float32`, while still rejecting genuinely-incompatible dtypes (`object`, `string`, `bool`). Added an expanded comment documenting the Phase 4 cycle-3 #1 rationale.
- **Files modified:** src/pipeline/validators.py
- **Verification:** `validate_schema_conformance(Path('data/standard'))` now returns 0 errors for all 5 tables; full 8-point `run_all_validations` overall_pass=True.
- **Committed in:** 08f1b35 (Task 2 commit)

**2. [Rule 1 - Bug] test_row_counts_within_expected_range had stale Kaggle-only expected counts**
- **Found during:** Task 2 (full suite regression check after the validator fix)
- **Issue:** `test_row_counts_within_expected_range` in `tests/pipeline/test_validators.py` asserted row counts within 5% of `{race: 21929, entry: 311806, result: 311806}` — the Kaggle-only pre-integration counts. Phase 6 integration grew the corpus to 38009/534953/534953 (~73% larger, far outside 5% tolerance), so the test failed. This is a direct consequence of this plan's integration work (the whole purpose was to grow the corpus).
- **Fix:** Updated expected counts to `{race: 38009, entry: 534953, result: 534953}` (the unified corpus values). Added a docstring noting the Phase 6 corpus growth.
- **Files modified:** tests/pipeline/test_validators.py
- **Verification:** `python -m pytest tests/pipeline/test_validators.py -q` → 25 passed.
- **Committed in:** 08f1b35 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 Rule 1 bugs — both directly caused by the Phase 6 corpus growth; the validator quirk was latent and surfaced by the overall_pass assertion, the test counts were stale post-integration). No scope creep, no architectural changes.

### Out-of-scope (logged to deferred-items.md, NOT fixed)

**feature_generator TypeError on unified corpus** — 2 tests fail in `tests/pipeline/test_feature_generator.py`:
- `TestTemporalInvariance::test_temporal_invariance_real_data`
- `TestRealDataIntegration::test_real_data_generation`
- Both raise `TypeError: invalid entry 0 in condlist: should be boolean ndarray` from `np.select` inside the feature generator's lag/rolling computation.
- **Owning phase:** Phase 3 (feature-engineering) re-run — explicitly deferred per 06-CONTEXT.md Deferred Ideas ("feature 層の再生成（Phase 3 再実行）— Phase 6 完了後、Phase 7 前に統合 corpus で feature 層を再生成。別タスク。Phase 6 スコープ外。").
- **Scope rationale:** Phase 6's deliverable is the unified standard-layer corpus (DATA-05). The corpus itself is correct (8-point validation green, PK-set union equality, FK integrity clean). Feature-layer regeneration is a separate downstream task. Fixing the feature generator here would conflate Phase 6 (data integration) with Phase 3 (feature engineering).
- **Suite health:** Full suite WITHOUT feature_generator tests → 403 passed, 1 skipped. All Phase 6 tests pass on the unified corpus.
- **Resolution path:** Re-run Phase 3 feature generation against the unified corpus before Phase 7. See `.planning/phases/06-data-integration/deferred-items.md` for full details.

## Issues Encountered

The 2 Rule 1 fixes above (validator dtype heuristic + stale test counts) and the deferred feature_generator failures. No other issues.

## User Setup Required

None — no external service configuration required. The unified Parquet files live under the gitignored `data/standard/` and are reproducible via `python -c "from pathlib import Path; from src.pipeline.integration import integrate_standard_layer; integrate_standard_layer(Path('data/standard'))"`.

## Next Phase Readiness

- **DATA-05 DELIVERED:** the unified `data/standard/{race,entry,result}.parquet` corpus covers 2015-2026/5 (Kaggle 2015-2021 + scraped 2021-08..2026-05), all 3 ROADMAP success criteria verified TRUE (no dups/entry-result 1-to-1; schema identical across full date range; 2015-2026/5 coverage).
- **Phase 3 feature regen:** required before Phase 7 (deferred per CONTEXT.md — feature_generator needs the np.select condlist edge case fixed for the larger corpus).
- **Phase 7/9 downstream:** the unified corpus is the single input for model training + backtesting. Phase 8 (EV) uses `entry.win_odds` → Harville proxy (三連複 corpus not mandatory).
- **Phase 5 seed protected:** odds/payoff byte-identical pre/post integration.

## Task 3: Human-verify checkpoint (RETURNED to orchestrator, NOT self-approved)

Per plan `autonomous: false` and `<task type="checkpoint:human-verify" gate="blocking">`, Task 3 is a blocking end-of-phase gate. The user reviews the unified corpus + this verification report, runs the full suite, and types "approved" or describes issues. This plan does NOT self-approve; the checkpoint state is returned to the orchestrator for routing to the user.

## Self-Check: PASSED

- `src/pipeline/validators.py` — FOUND (Rule 1 fix applied)
- `tests/pipeline/test_validators.py` — FOUND (Rule 1 fix applied)
- `.planning/phases/06-data-integration/deferred-items.md` — FOUND
- `data/standard/race.parquet` — FOUND (38,009 rows, unified)
- `data/standard/entry.parquet` — FOUND (534,953 rows, unified)
- `data/standard/result.parquet` — FOUND (534,953 rows, unified)
- `data/standard/odds_trifecta.parquet` — FOUND (SHA-256 unchanged)
- `data/standard/payoff.parquet` — FOUND (SHA-256 unchanged)
- Commit `08f1b35` (Task 2) — FOUND in git log
- 8-point run_all_validations overall_pass=True — VERIFIED
- 11 integration tests green — VERIFIED
- Preflight month-set equality (58==58, 0 missing, 0 extra) — VERIFIED

## Task 3 — human-verify approved

**Approved on:** 2026-06-15
**Gate:** `checkpoint:human-verify` (`gate="blocking"`) — end-of-phase blocking checkpoint per `autonomous: false`.

The user reviewed the orchestrator's spot-checked verification summary (8-point run_all_validations overall_pass=True, 11 integration tests green, odds/payoff SHA-256 byte-identical, PK-set union equality, date-floor satisfied) and typed **approved**.

Two noted items were accepted by the user:

- **(a) Rule 1 fix in `validators.py`** (commit `08f1b35`) — accepted as a narrow corpus-growth fix: case-insensitive `'float'` substring so pandas nullable `Float64` dtype (Phase 4 cycle-3 #1 authority for nullable-int fields) passes schema conformance on the larger unified corpus. Not a scope expansion; the corpus itself is verified correct.
- **(b) feature_generator 2-test failure DEFERRED** — `np.select empty condlist` TypeError on the unified corpus. Owning phase = Phase 3; explicitly deferred per `06-CONTEXT.md` Deferred Ideas. Re-run is a pre-Phase-7 carryover. Corpus correctness is independent of this (8-point validation green).

The unified corpus is verified CORRECT via the 8-point run_all_validations + spot checks. Task 3 satisfies its resume-signal; no code change was required (`<files></files>` empty).

---
*Phase: 06-data-integration*
*Completed: 2026-06-15*
