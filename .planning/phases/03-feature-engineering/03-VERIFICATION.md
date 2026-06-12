---
phase: 03-feature-engineering
verified: 2026-06-12T18:10:00Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
re_verification: false
---

# Phase 3: Feature Engineering Verification Report

**Phase Goal:** ML-ready feature vectors are generated from standard-layer data, providing the training inputs that Model A requires
**Verified:** 2026-06-12T18:10:00Z
**Status:** passed
**Re-verification:** No -- initial verification

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
