"""ML training/evaluation package for Model A (top-3 probability).

Public API re-exports are added in Plan 07-07 (run_train orchestrator). Until
then this package ships as an import-safe EMPTY marker (Phase 4 P01 pattern:
src/scraper/__init__.py started empty in P01 and gained re-exports in P06).

Submodules will be added by Wave 1 (Plans 07-02..07-06):
  * data_loader             -- feature Parquet loading + categorical conversion
  * group_timeseries_split  -- race-aware time-series cross-validator
  * trainer                 -- LightGBM fold training + OOF collection
  * calibrator              -- isotonic regression, leak-free
  * evaluator               -- ECE + reliability diagram
  * baseline                -- popularity-based baseline AUC
"""
