---
status: complete
phase: 03-feature-engineering
source: 03-01-SUMMARY.md, 03-02-SUMMARY.md, 03-03-SUMMARY.md, 03-04-SUMMARY.md, 03-05-SUMMARY.md
started: 2026-06-12T15:03:39Z
updated: 2026-06-12T15:13:30Z
---

## Current Test

[testing complete]

## Tests

### 1. End-to-end feature pipeline run on real data
expected: `generate()` runs over real `data/standard/*.parquet` and writes both Parquet files (features_train + features_pred) with no error.
result: pass
verified: TestRealDataIntegration 8 passed (86s) — incl. "generate() runs successfully on real data/standard"; pipeline runs end-to-end on 311K rows without error.

### 2. Output shapes & prediction-file safety
expected: features_train.parquet = 311,806 rows × 78 cols (72 features + 2 entity keys + 4 auxiliary); features_pred.parquet = 311,806 rows × 74 cols (72 features + 2 entity keys only). pred file must contain NO target_top3 / result_status / auxiliary columns (no leakage into prediction input).
result: pass
verified: Direct parquet inspection — train (311806, 78), pred (311806, 74); rows match; pred has NONE of [target_top3, result_status, is_dnf, exclude_from_training]; train-only cols = exactly the 4 auxiliary; target_top3 positive rate 21.12%.

### 3. Horse collision disambiguation
expected: All 14 same-name horse collisions in 2015-2021 data disambiguated by birth_year_proxy (horse_entity_key = horse_name + birth_year_proxy). "アームストロング" correctly splits into 2 distinct horse_entity_key values.
result: pass
verified: TestHorseEntityKey passed + real-data collision test in TestRealDataIntegration passed; horse_entity_key = horse_name + birth_year_proxy confirmed in module.

### 4. Margin conversion & finish-time z-score temporal safety
expected: Compound margin text parses correctly (e.g. "1.1/4+クビ" → 1.35; 22-value MARGIN_MAP + COMPONENT_MAP for '+'-delimited forms). finish_time_zscore uses race-boundary normalization (no same-race leakage), and is temporally invariant (adding future races does not change historical z-scores).
result: pass
verified: TestMarginConversion (12) + TestFinishTimeZscore (11, incl. race-boundary leakage + temporal invariance) passed.

### 5. Lag features with valid-start filtering
expected: 取 (scratched) and 除 (removed) entries excluded from lag computation so they never corrupt lag slots; non-valid entries get all-NaN lags. 45 lag columns present (prev_1..5 × 5 metrics + prev3/5 mean/std).
result: pass
verified: TestLagFeatures (9) passed; 45 lag columns (25 raw + 20 stat) confirmed via FEATURE_COLUMNS structure.

### 6. Jockey/trainer rolling stats (sum-based, D-08 intersection)
expected: Sum-based race-level aggregation — trainer/jockey with 2 top-3 from 3 runners produces rate 0.667, not 1.0. D-08 exact intersection (within 365 days AND among most recent 100). Current race not included in its own stats. 6 rolling-stat columns.
result: pass
verified: TestJockeyTrainerStats (11) + test_real_data_trainer_rate passed; PERSON_FEATURES = 6 columns confirmed.

### 7. Target variable & result_status classification
expected: target_top3 ~21% positive rate. result_status distinguishes 取 (scratched) vs 除 (removed) as distinct categories. 降 (demoted) horses keep finish_position and target_top3 based on actual position. exclude_from_training excludes only 取/除.
result: pass
verified: TestTargetVariable (11) passed; target_top3 21.12% confirmed on real data; result_status 6-category (finished/dnf/disqualified/scratched/removed/demoted).

### 8. Debut flag correctness
expected: is_debut True only at a horse's first valid start per horse_entity_key. A horse whose first entry is 取 does NOT consume the debut slot (debut happens at next valid start). A horse with only 取 entries has is_debut=False throughout.
result: pass
verified: TestDebutFlag (6) passed; cumsum-based debut with valid-start exclusion.

### 9. Static feature allowlist & leakage audit
expected: FEATURE_COLUMNS is a static 72-column allowlist built from 6 named feature-group lists — no column can silently appear in model features. `audit_leakage()` on features_pred output is clean (zero pre-race-feature contamination from post-race ResultSchema fields).
result: pass
verified: FEATURE_COLUMNS = 72 (module constant); train cols == FEATURE_COLUMNS + ENTITY_KEY + aux exactly; pred cols == FEATURE_COLUMNS + ENTITY_KEY exactly; TestLeakageAudit (2) + TestEndToEnd (9) passed; real-data pred has zero leak columns.

## Summary

total: 9
passed: 9
issues: 0
pending: 0
skipped: 0
blocked: 0

## Observations (non-blocking)

- `pytest.mark.integration` is used but NOT registered in `[tool.pytest.ini_options]` markers → emits PytestUnknownMarkWarning on every integration test. Register the marker to silence.
- A `FutureWarning: observed=False` fires from a test helper groupby at `test_feature_generator.py:2101` (`test_real_data_trainer_rate`). Cosmetic now (test helper, not production code), but will need `observed=True` before a future pandas release.
- Both are cosmetic/maintenance items — no impact on feature correctness or pipeline output. Not UAT gaps.

## Gaps

[none — all 9 tests passed]
