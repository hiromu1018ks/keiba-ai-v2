# Phase 6 Deferred Items

Out-of-scope issues discovered during Phase 6 execution. Per executor SCOPE
BOUNDARY: pre-existing warnings/failures in unrelated files are NOT auto-fixed;
they are logged here for the owning phase to pick up.

## [DEFERRED-1] feature_generator TypeError on unified corpus

- **Discovered during:** Plan 06-03, Task 2 (full suite run after integration)
- **Owning phase:** Phase 3 (feature-engineering) re-run — explicitly deferred
  per `06-CONTEXT.md` Deferred Ideas: "feature 層の再生成（Phase 3 再実行）—
  Phase 6 完了後、Phase 7 前に統合 corpus で feature 層を再生成。別タスク。
  Phase 6 スコープ外。"
- **Symptom:** 2 tests fail with the same root cause:
  - `tests/pipeline/test_feature_generator.py::TestTemporalInvariance::test_temporal_invariance_real_data`
  - `tests/pipeline/test_feature_generator.py::TestRealDataIntegration::test_real_data_generation`
  - Both raise `TypeError: invalid entry 0 in condlist: should be boolean ndarray`
    from `numpy.lib._function_base_impl:898` (an `np.select` call inside the
    feature generator's lag/rolling computation path).
- **Root cause:** Phase 6 integration grew `data/standard/{race,entry,result}.parquet`
  from Kaggle-only (311,806 entry/result rows, race_date 2015-2021) to the unified
  corpus (534,953 entry/result rows, race_date 2015-01-04..2026-05-31). The feature
  generator's `np.select`-based result_status / margin classification path hits an
  empty-condlist edge case on a subset of scraped-era rows that the Kaggle corpus
  did not exercise. This is a Phase 3 data-handling issue, NOT a Phase 6 corpus
  defect — the unified corpus itself passes the full 8-point `run_all_validations`
  (overall_pass=True), PK-set union equality for all 3 tables, referential
  integrity, and per-period graded counts.
- **Scope rationale:** Phase 6's deliverable is the unified standard-layer corpus
  (DATA-05). Feature-layer regeneration is a separate downstream task (Phase 3
  re-run) that CONTEXT.md explicitly places out of Phase 6 scope. Fixing the
  feature generator here would violate the scope boundary and conflate Phase 6
  (data integration) with Phase 3 (feature engineering).
- **Verification that corpus is correct:** `run_all_validations(raw_dir,
  parquet_dir=Path('data/standard'), source_counts, source_stats)` returns
  `overall_pass=True` with all 8 checks True against the unified root (Plan
  06-03 Task 2, commit pending). The feature generator is a downstream consumer,
  not a corpus validator.
- **Resolution path:** Re-run Phase 3 feature generation against the unified
  corpus before Phase 7 (model training). Investigate the `np.select` condlist
  edge case in `src/pipeline/feature_generator.py` at that time. The 2 failing
  tests will need their expected outputs updated for the larger corpus regardless.
- **Status:** OPEN — awaiting Phase 3 re-run (pre-Phase-7).

## Reference: suite health

- Full suite WITHOUT feature_generator tests: **403 passed, 1 skipped** (green).
- Full suite WITH feature_generator tests: 497 passed, 2 failed (the 2
  feature_generator tests above), 1 skipped.
- All Phase 6 tests (`tests/pipeline/test_integration.py`, `test_validators.py`,
  `test_kaggle_converter.py`, `test_column_mapping.py`) pass on the unified corpus.
