---
phase: 03-feature-engineering
verified: 2026-06-15T16:00:00Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
re_verification: true
initial_verification: 2026-06-12T18:10:00Z
re_verification_reason: "Phase 6 unified corpus (534,953 rows, 2015-2026/5); feature_generator np.select dtype bug fixed (quick 260615-jdx); feature layer regenerated + directly re-inspected"
---

# Phase 3: Feature Engineering Verification Report

**Phase Goal:** ML-ready feature vectors are generated from standard-layer data, providing the training inputs that Model A requires
**Verified:** 2026-06-15T16:00:00Z (re-verification on unified corpus)
**Status:** passed
**Re-verification:** Yes — 2026-06-15 (unified corpus, post Phase 6). Initial verification 2026-06-12 (Kaggle-only) preserved below.

## Re-verification (2026-06-15): Unified Corpus

Phase 6 (data-integration, completed 2026-06-15) merged Kaggle (2015-2021) + scraped (2021-08..2026-05) into a unified standard corpus (race 38,009 / entry=result 534,953 rows, 2015-01-04..2026-05-31). The feature layer — originally verified 2026-06-12 against the Kaggle-only corpus (311,806 rows) — required regeneration against the unified corpus. This section records the re-verification (direct inspection of the regenerated Parquet + suite).

### Trigger & fix
- `feature_generator.generate_target()` line 614 raised `TypeError: invalid entry 0 in condlist` on the unified corpus. Root cause: the unified corpus's `finish_note` is pandas nullable `string` dtype (Phase 4 cycle-3 #1), so `df["finish_note"] == "中"` produced a nullable-boolean Series that `np.select` rejects (requires native bool ndarray). **Not** an empty-condlist / out-of-range issue. The Kaggle-only corpus had `finish_note` as object dtype, so the latent bug did not surface.
- Fix (quick task 260615-jdx, commits `516fa46` + `bcb0716`): each condlist entry coerced via `.to_numpy(dtype=bool, na_value=False)` (pd.NA → False → default "finished" branch). 6-way classification logic unchanged and non-degenerate (TestTargetVariable 11 tests invariant + new nullable-dtype regression test added).

### 4 must-haves re-verified against the unified corpus

| # | Truth | Re-verified | Evidence (2026-06-15 direct inspection) |
|---|-------|-------------|------------------------------------------|
| 1 | All specified features present; popularity/win_odds excluded | ✓ | features_train 78 cols / features_pred 74 cols; train-only 4 cols = target/auxiliary (target_top3, result_status, is_dnf, exclude_from_training); FEATURE_COLUMNS unchanged |
| 2 | Temporal shift — no future leakage | ✓ | lag-feature NaN signature monotonic: prev_1 13.0% → prev_5 47.4% (correct "no prior start" pattern); rolling stats ~0% NaN; TestTemporalInvariance green |
| 3 | Categorical CategoricalDtype | ✓ | category dtype columns present in Parquet output |
| 4 | pred passes audit_leakage (zero post-race) | ✓ | features_pred has no target/auxiliary columns (only FEATURE_COLUMNS + ENTITY_KEY); audit runs in generate() step 12 |

### Direct inspection of regenerated Parquet (features_train/pred.parquet)
- **Rows:** 534,953 each (full unified corpus — both files cover all rows; train has target cols, pred does not; temporal train/test split is deferred to Phase 7 training time, not feature-gen time, per `generate()` design Step 13/14).
- **race_id:** 38,009 unique = full unified corpus; race_date 2015-01-04 → 2026-05-31.
- **target_top3:** 21.3% positive (114,123 / 534,953) — consistent with Kaggle-only baseline (21.12%).
- **result_status** (np.select fix site): finished=531,320, dnf=1,668, removed=1,090, scratched=854, demoted=20, disqualified=1 — 6 categories healthy; fix confirmed correct.
- **Schema:** 0 Arrow-null columns; race_date/race_id string; dtype mix float64/string-nullable/Int64/Float64/bool/category.
- **Minor observation:** 15 non-finished rows have target_top3=1 (0.003%; demoted/降着 horses physically finishing top-3 — target-definition nuance, same as Kaggle-only behavior, covered by TestTargetVariable; not a defect).

### Suite
- `tests/pipeline/test_feature_generator.py`: 97 passed (was 95 + 2 new incl. nullable-dtype regression).
- Full suite: 513 passed / 1 skipped / 0 failed.

### References
- Quick task PLAN/SUMMARY: `.planning/quick/260615-jdx-*/`
- Phase 6 DEFERRED-1: `.planning/phases/06-data-integration/deferred-items.md`
- Commits: `516fa46` (fix), `bcb0716` (regen)

**Re-verification verdict:** passed — 4/4 must-haves hold against the unified corpus; feature layer regenerated and directly inspected; Phase 7 unblocked.

---

_Note: the sections below ("## Goal Achievement" onward) are the **initial verification record** (2026-06-12, Kaggle-only 311,806-row corpus), preserved as methodology evidence. Numeric values there (311,806 rows, 21.12% target rate, 95 tests) reflect the Kaggle-only baseline; the unified-corpus current values are in the re-verification section above._

## Goal Achievement

## Goal Achievement

### Observable Truths (from ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Feature layer generates all specified features: race context, horse identifiers, jockey/trainer categoricals + rolling stats, recent form (lag features), last-3F time, running position, debut flag; popularity/win_odds excluded per D-15 | VERIFIED | `FEATURE_COLUMNS` has 72 columns; all DATA-03 features verified present; `popularity` and `win_odds` confirmed absent from FEATURE_COLUMNS; 9 categorical columns verified in Parquet |
| 2 | All rolling/lag features use temporal shift so no future information leaks into any row | VERIFIED | `shift(1..5)` in `compute_lag_features()` line 381; race-boundary `shift(1)` in z-score lines 305/308; jockey/trainer stats compute current row BEFORE appending to prior_starts (lines 529-541); temporal invariance tests pass on fixture and real data |
| 3 | Categorical columns use pandas CategoricalDtype for native LightGBM integration | VERIFIED | `convert_to_categorical()` converts 9 CATEGORICAL_COLUMNS to category dtype (line 712); verified in Parquet output: all 9 columns are `category` dtype |
| 4 | Feature output passes the Phase 1 audit function (zero post-race columns detected) | VERIFIED | `audit_leakage([RaceSchema, EntrySchema], pred_df, ...)` returns empty list `[]`; `features_pred.parquet` contains zero forbidden columns (target_top3, result_status, is_dnf, exclude_from_training, margin_numeric, finish_time_zscore, finish_time_seconds all absent) |

**Score:** 4/4 truths verified

### DATA-03 Requirement Coverage

| DATA-03 Feature | Column | Present |
|-----------------|--------|---------|
| 競馬場 (course) | course_name | VERIFIED |
| 距離 (distance) | distance | VERIFIED |
| 芝ダート (surface) | surface | VERIFIED |
| 馬場状態 (condition) | track_condition | VERIFIED |
| 頭数 (field size) | field_size | VERIFIED |
| 枠番 (bracket) | bracket_num | VERIFIED |
| 馬番 (horse number) | horse_number | VERIFIED |
| 斤量 (weight) | weight_assigned | VERIFIED |
| 騎手 (jockey) | jockey + jockey_rolling_* | VERIFIED |
| 調教師 (trainer) | trainer + trainer_rolling_* | VERIFIED |
| 近走成績 (recent form) | prev_1..5_finish_position + prev3/5 stats | VERIFIED |
| 上がり3F (last 3f) | prev_1..5_last_3f + prev3/5 stats | VERIFIED |
| 通過順 (running position) | prev_1..5_corner_4 + prev3/5 stats | VERIFIED |
| 人気 (popularity) | -- excluded per D-15 | CORRECTLY EXCLUDED |
| 単勝オッズ (win odds) | -- excluded per D-15 | CORRECTLY EXCLUDED |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/pipeline/feature_generator.py` | Module with generate() orchestrator and all helper functions (120+ lines) | VERIFIED | 1022 lines; 15 functions including generate(), load_and_merge(), derive_horse_entity_key(), extract_race_context_features(), extract_horse_basic_features(), parse_margin(), convert_margin_to_numeric(), parse_finish_time_to_seconds(), compute_finish_time_zscore(), compute_lag_features(), compute_jockey_trainer_stats(), _compute_person_stats(), generate_target(), compute_debut_flag(), convert_to_categorical() |
| `tests/pipeline/test_feature_generator.py` | Unit + integration tests | VERIFIED | 2027 lines; 16 test classes; 95 test methods; all passing |
| `tests/pipeline/conftest.py` | Test fixtures with collision-horse data | VERIFIED | 682 lines; includes sample_standard_race_df, sample_standard_entry_df, sample_standard_result_df, sample_feature_merged_df, sample_lag_merged_df, tmp_feature_dir |
| `data/feature/features_train.parquet` | Training features with target_top3 (~311K rows) | VERIFIED | 311,806 rows, 78 columns (72 features + 2 entity keys + 4 auxiliary) |
| `data/feature/features_pred.parquet` | Prediction features without target (~311K rows) | VERIFIED | 311,806 rows, 74 columns (72 features + 2 entity keys) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| generate() | load_and_merge() | Step 1 call | WIRED | Line 924 |
| generate() | audit_leakage() | Step 12 call | WIRED | Line 996; imports from src.schemas.audit |
| compute_lag_features() | finish_time_zscore, margin_numeric | Reads columns from Plans 01-02 | WIRED | Line 376: lag_metrics includes finish_time_zscore, margin_numeric |
| compute_jockey_trainer_stats() | _compute_person_stats() | Delegates per person type | WIRED | Lines 576-581: calls for jockey then trainer |
| generate() | Parquet output | Steps 13-14 | WIRED | Lines 1012, 1019: writes both Parquet files |
| derive_horse_entity_key() | horse_name, race_id, age | birth_year_proxy computation | WIRED | Lines 740-746 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| features_train.parquet | target_top3 | generate_target() from finish_position | Real: 21.12% positive rate, 65845/311806 | FLOWING |
| features_train.parquet | result_status | generate_target() from finish_note | Real: 6 categories (finished=309697, dnf=966, removed=604, scratched=520, demoted=18, disqualified=1) | FLOWING |
| features_pred.parquet | prev_1_finish_position | compute_lag_features() from valid-start rows | Real: NaN for debut, numeric for experienced horses | FLOWING |
| features_pred.parquet | jockey_rolling_top3_rate | _compute_person_stats() from prior valid starts | Real: varied rates (e.g., 0.1524 for sampled trainer) | FLOWING |
| features_pred.parquet | is_debut | compute_debut_flag() from result_status | Real: True for first valid start, skips scratches | FLOWING |
| features_train.parquet | finish_time_zscore | compute_finish_time_zscore() from race-level expanding window | Real: race-boundary normalization from prior races | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Feature generator tests pass | `python3 -m pytest tests/pipeline/test_feature_generator.py -x -q` | 95 passed, 10 warnings in 247s | PASS |
| Full test suite passes | `python3 -m pytest tests/ -x -q` | 235 passed, 10 warnings in 273s | PASS |
| Ruff lint clean | `ruff check src/pipeline/feature_generator.py` | All checks passed | PASS |
| Ruff lint clean (tests) | `ruff check tests/pipeline/test_feature_generator.py` | All checks passed | PASS |
| Train Parquet readable with correct row count | Python: `len(pd.read_parquet('data/feature/features_train.parquet'))` | 311806 rows, 78 columns | PASS |
| Pred Parquet readable with correct row count | Python: `len(pd.read_parquet('data/feature/features_pred.parquet'))` | 311806 rows, 74 columns | PASS |
| Leakage audit returns empty | Python: `audit_leakage([RaceSchema, EntrySchema], pred_df, 'test')` | `[]` (zero leaked columns) | PASS |
| Entity key collision disambiguation | Python: filter horse_name "アームストロング" | 2 distinct keys: `アームストロング_2011`, `アームストロング_2018` | PASS |

### Probe Execution

Step 7c: SKIPPED (no probe scripts defined for this phase)

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| DATA-03 | 03-01 through 03-05 | Generate feature-layer basic features from standard data | SATISFIED | All 13 feature groups present in FEATURE_COLUMNS; 2 D-15 exclusions correctly applied; 72 feature columns, 311K rows generated |

No orphaned requirements found. REQUIREMENTS.md maps only DATA-03 to Phase 3, and all 5 plans declare DATA-03.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| (none) | -- | -- | -- | No debt markers, stubs, or empty implementations found |

No TBD, FIXME, XXX, TODO, HACK, or PLACEHOLDER markers found in `src/pipeline/feature_generator.py` or `tests/pipeline/test_feature_generator.py`. No empty implementations. No stub returns.

### Human Verification Required

None required. All success criteria are programmatically verified:

- Feature column counts, data types, and content verified via Parquet inspection
- Temporal safety verified via dedicated test classes (TestTemporalInvariance, race-boundary z-score tests)
- Leakage verified via audit_leakage() returning empty list
- Entity key collision verified via real data query
- Scratch filtering verified via real data query showing correct prev_1 references
- Trainer rate semantics verified via real data showing sum-based rates (not binary)

### Gaps Summary

No gaps found. All 4 ROADMAP success criteria verified against the actual codebase. Phase goal achieved.

Key verifications performed:
- 311,806 rows in both Parquet files (matching entry count from Phase 2)
- 72 feature columns in static FEATURE_COLUMNS allowlist (matching sum of 6 named feature groups)
- 9 categorical columns with CategoricalDtype confirmed in Parquet
- Zero post-race leakage in features_pred.parquet
- 95 tests passing (86 unit + 9 integration)
- Horse "アームストロング" correctly split into 2 entity keys
- target_top3 distribution: 21.12% positive rate
- result_status covers all 6 categories (finished, dnf, disqualified, scratched, removed, demoted)
- exclude_from_training: all 1,124 scratched/removed rows correctly flagged

---

_Verified: 2026-06-12T18:10:00Z_
_Verifier: Claude (gsd-verifier)_
