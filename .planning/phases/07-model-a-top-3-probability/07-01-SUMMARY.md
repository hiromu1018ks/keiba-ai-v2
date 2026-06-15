---
phase: 07-model-a-top-3-probability
plan: 01
subsystem: ml-test-scaffold
tags: [wave-0, environment, pytest-scaffold, lightgbm, sklearn]
requires:
  - phase-06-unified-corpus (DATA-05; feature corpus upstream consumer in Wave 1+)
provides:
  - "src.ml package marker (import-safe empty; re-exports land in 07-07)"
  - "tests.ml package + conftest hermetic fixtures (sample_feature_df, sample_entry_df, tmp_ml_output_dir, ml_config)"
  - "6 skip-state test skeletons (24 cases) ready for Wave 1 RED→GREEN"
  - "pyproject.toml deps: scikit-learn>=1.9, matplotlib>=3.10, joblib>=1.4, pyyaml>=6"
  - "pyproject.toml gated pytest marker (RUN_GATED=1, mirrors live pattern)"
affects:
  - pyproject.toml (deps + markers)
  - "Wave 1 plans 07-02..07-06 implement src/ml/* and unskip matching tests"
tech_stack:
  added:
    - scikit-learn 1.9.0 (ECE/ROC/AUC + sklearn-API compatibility)
    - matplotlib 3.11.0 (reliability diagram, Agg backend)
    - joblib 1.5.3 (calibrator persistence)
    - pyyaml 6.x (config/phase7_model_a.yaml reader)
    - lightgbm 4.6.0 (already installed in venv; libomp prereq verified)
  patterns:
    - "import-safe empty package marker (Phase 4 P01 analog; re-exports deferred to final plan)"
    - "hermetic pytest fixtures via tmp_path (no data/feature corpus dependency)"
    - "pandas CategoricalDtype for jockey/trainer (D-16 native categoricals, no one-hot)"
    - "skip-state test skeletons (Wave 1 removes skips as src/ml/* modules land)"
key_files:
  created:
    - src/ml/__init__.py
    - tests/ml/__init__.py
    - tests/ml/conftest.py
    - tests/ml/test_data_loader.py
    - tests/ml/test_group_timeseries_split.py
    - tests/ml/test_trainer.py
    - tests/ml/test_calibrator.py
    - tests/ml/test_evaluator.py
    - tests/ml/test_baseline.py
  modified:
    - pyproject.toml
decisions:
  - "src.ml/__init__.py ships empty (Phase 4 P01 pattern); public re-exports deferred to 07-07"
  - "sample_feature_df keeps jockey/trainer as pandas CategoricalDtype so LightGBM native categorical path is exercised (D-16); grade stays object/string with NaN preserved (Pitfall #4)"
  - "popularity/win_odds live in sample_entry_df (separate), not sample_feature_df, so the leakage audit on the feature DataFrame is empty by construction"
  - "gated marker pattern (RUN_GATED=1 env var) mirrors existing live marker; --run-gated CLI flag NOT registered (Cycle-5 MEDIUM carry-over: 07-02 verify/AC use env var)"
  - "24 test cases named per RESEARCH.md Test Map lines 785-795 and PATTERNS.md planner directives; each carries MODA-XX / Pitfall #N citation in docstring"
metrics:
  duration: 967s
  completed: 2026-06-15
  tasks: 3
  files: 10
---

# Phase 7 Plan 01: Wave 0 Environment + tests/ml Scaffold Summary

LightGBM (libomp)・scikit-learn・matplotlib・joblib を導入し、tests/ml/ に hermetic fixture + 6テストファイル（24ケース・全skip）を整えた Wave 0。Wave 1 の src/ml/* 実装が TDD サイクルで着手できる前提を完成させた。

## What Was Built

### Task 1 — brew install libomp (verify-only precondition)
- Pre-verified by orchestrator dispatch; libomp 22.1.7 already installed.
- Confirmed in this run: `import lightgbm` → 4.6.0, `from lightgbm import early_stopping` succeeds (Pitfall #1 callback API available).
- No code change.

### Task 2 — pip install + pyproject.toml deps + gated marker (commit f518ea8)
- Installed into venv: scikit-learn 1.9.0, matplotlib 3.11.0, joblib 1.5.3, pyyaml 6.x.
- pyproject.toml `[project] dependencies` += `scikit-learn>=1.9`, `matplotlib>=3.10`, `joblib>=1.4`, `pyyaml>=6` (setuptools, not Poetry — MEMORY.md).
- pyproject.toml `[tool.pytest.ini_options] markers` += `gated` (RUN_GATED=1 env var; mirrors existing `live` marker pattern at tests/scraper/test_end_to_end.py:713).
- Existing test suite unaffected (collection 514 → 514, then +24 after Task 3).

### Task 3 — tests/ml/ scaffold (commit 8c7dabb)
- **src/ml/__init__.py**: import-safe empty marker (Phase 4 P01 analog; re-exports deferred to Plan 07-07). Module docstring lists the 6 Wave 1 submodules that will populate it.
- **tests/ml/conftest.py** (hermetic fixtures, no `data/feature/*.parquet` dependency):
  - `sample_feature_df` — 20 rows / 6 races / 2018-2024 window; jockey/trainer coerced to `pandas.CategoricalDtype` (D-16 native categoricals, no one-hot), grade preserved as object/string with NaN (Pitfall #4), target_top3 + exclude_from_training present, no popularity/win_odds (post-race columns live in entry table).
  - `sample_entry_df` — 1:1 joinable to sample_feature_df on (race_id, horse_number); horse_race_id derived per Pitfall #2; 2 NaN popularity rows for cancel/scratch reproduction (Pitfall #6).
  - `tmp_ml_output_dir` — tmp_path dir for OOF/model/diagram artifacts.
  - `ml_config` — test-shrunk mirror of config/phase7_model_a.yaml (num_leaves=31, n_estimators=50, stopping_rounds=10, n_splits=5, n_bins=10).
- **6 test files / 24 skip-state cases** (each carries MODA-XX / D-XX / Pitfall #N citation in docstring):
  - `TestFeatureLoad` (5): MODA-01 categorical/horse_race_id/leakage/window/grade-NaN
  - `TestGroupTimeSeriesSplit` (4): MODA-02 same-fold/temporal/boundary/get_n_splits
  - `TestTrainer` (4): MODA-01 fold model + early-stopping (Pitfall #1 callback API) + OOF + final (D-15)
  - `TestCalibrator` (3): MODA-04 leak-free (Pitfall #5) + [0,1] range + monotonic non-decreasing
  - `TestEvaluator` (5): MODA-04 ECE perfect/worst/bin-weight + reliability diagram (D-11) + metrics dict (D-06)
  - `TestBaseline` (3): MODA-03 popularity AUC + NaN drop (Pitfall #6) + join integrity

## Deviations from Plan

None — plan executed exactly as written. All 3 tasks met their acceptance_criteria on first run:
- Task 1: imports succeed (libomp already installed pre-dispatch)
- Task 2: imports succeed + 4 deps declared + gated marker present + collection 514 unaffected
- Task 3: 24 cases collected with 0 errors, all skip, full suite still 513 passed / 25 skipped (24 new ml skips + 1 pre-existing integration skip), src.ml imports, no leakage of post-race columns into sample_feature_df by construction

## Verification

| Check | Command | Result |
|-------|---------|--------|
| libomp import | `python -c "import lightgbm"` | lightgbm 4.6.0 OK |
| callback API | `python -c "from lightgbm import early_stopping"` | ok |
| Task 2 deps import | `python -c "import sklearn, matplotlib, joblib, yaml"` | sklearn 1.9.0 / matplotlib 3.11.0 / joblib 1.5.3 |
| pyproject deps declared | `grep -c {dep} pyproject.toml` | scikit-learn=1, matplotlib=1, joblib=1, pyyaml=1, gated=1 |
| tests/ml collection | `python -m pytest tests/ml/ -q --co` | 24 collected, 0 errors |
| tests/ml skip path | `python -m pytest tests/ml/ -q` | 24 skipped, 0 failed, 0 errors |
| Full suite baseline | `python -m pytest tests/ -q` | 513 passed, 25 skipped (run twice, identical) |
| src.ml empty marker | `python -c "import src.ml"` | ok |
| Post-commit deletion check | `git diff --diff-filter=D --name-only HEAD~2 HEAD` | (none) |

## Known Stubs

None. Plan 07-01 is Wave 0 scaffolding by design — all `src/ml/` production symbols are explicitly deferred to Wave 1 (Plans 07-02..07-06), and every test in tests/ml/ is in intentional skip state. The skip messages cite "Wave 1 implements src/ml/{module} first" so unskipping is mechanically tied to module landing.

## Threat Flags

None. The only trust boundary this plan touches (PyPI/pip → local env for scikit-learn/matplotlib/joblib) is disposition-mitigated by T-07-01-SC: all three packages are 10+ year authoritative sources pre-verified in RESEARCH § Package Legitimacy Audit (github.com/scikit-learn, matplotlib, joblib). seam's "SUS" verdict is a known false-positive from PyPI download-count retrieval failure and is overridden by CLAUDE.md recommended-stack + existing lightgbm>=4.6 declaration. No blocking-human gate needed.

## Self-Check: PASSED

- Created files exist:
  - FOUND: src/ml/__init__.py
  - FOUND: tests/ml/__init__.py
  - FOUND: tests/ml/conftest.py
  - FOUND: tests/ml/test_data_loader.py
  - FOUND: tests/ml/test_group_timeseries_split.py
  - FOUND: tests/ml/test_trainer.py
  - FOUND: tests/ml/test_calibrator.py
  - FOUND: tests/ml/test_evaluator.py
  - FOUND: tests/ml/test_baseline.py
- Commits exist:
  - FOUND: f518ea8 (Task 2 deps + gated marker)
  - FOUND: 8c7dabb (Task 3 tests/ml scaffold)
