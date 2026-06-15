"""ML training/evaluation package for Model A (top-3 probability).

Public API re-exports (Plan 07-07 — Phase 4 P06 analog). Phase 8/9 may
access every Wave 1+2 symbol via ``from src.ml import ...``:

    from src.ml import (
        run_train,                       # orchestrator (07-07)
        GroupTimeSeriesSplit,            # race-aware time-series CV (07-03)
        train_fold_model,                # single LightGBM fold (07-04)
        collect_oof_predictions,         # OOF = val chunks only (07-04)
        train_final_model,               # two-stage full retrain (07-04)
        fit_calibrator,                  # Isotonic OOF fit (07-05)
        apply_calibrator,                # predict-only (Pitfall #5) (07-05)
        save_calibrator,                 # .joblib persist (07-05)
        load_calibrator,                 # .joblib load (07-05)
        compute_ece,                     # Guo et al. 2017 ECE (07-06)
        evaluate,                        # AUC/Brier/logloss/ECE dict (07-06)
        reliability_diagram,             # matplotlib Agg PNG (07-06)
        compute_popularity_baseline,     # D-08 reference AUC (07-06)
        load_features,                   # feature parquet loader (07-02)
    )

Plan 07-01 shipped this file as an import-safe EMPTY marker (Phase 4 P01
pattern); the transition to public re-exports happens HERE, mirroring how
``src/scraper/__init__.py`` went from empty (P01) to re-exports (P06).
"""

from src.ml.baseline import compute_popularity_baseline
from src.ml.calibrator import (
    apply_calibrator,
    fit_calibrator,
    load_calibrator,
    save_calibrator,
)
from src.ml.data_loader import load_features
from src.ml.evaluator import compute_ece, evaluate, reliability_diagram
from src.ml.group_timeseries_split import GroupTimeSeriesSplit
from src.ml.run_train import run_train
from src.ml.trainer import (
    collect_oof_predictions,
    train_final_model,
    train_fold_model,
)

__all__ = [
    # 07-07 orchestrator
    "run_train",
    # 07-03 cross-validator
    "GroupTimeSeriesSplit",
    # 07-04 trainer
    "train_fold_model",
    "collect_oof_predictions",
    "train_final_model",
    # 07-05 calibrator
    "fit_calibrator",
    "apply_calibrator",
    "save_calibrator",
    "load_calibrator",
    # 07-06 evaluator
    "compute_ece",
    "evaluate",
    "reliability_diagram",
    # 07-06 baseline
    "compute_popularity_baseline",
    # 07-02 data loader
    "load_features",
]
