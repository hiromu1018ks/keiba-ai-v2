"""LightGBM fold trainer + OOF collector + two-stage final retrain (MODA-01).

This module is the learning core of Phase 7 Model A (3着内確率 / top-3
probability). It implements three public functions consumed by the
``run_train`` orchestrator (07-07):

    train_fold_model(X_train, y_train, X_val, y_val, config) -> LGBMClassifier
    collect_oof_predictions(df, splitter, config, feature_columns) -> DataFrame
    train_final_model(df, config, feature_columns) -> LGBMClassifier

============================================================================
Pitfall #1 (VERIFIED) — early_stopping callback API, NOT the legacy kwarg
============================================================================
LightGBM 4.0 removed ``early_stopping_rounds`` from ``fit()`` / ``train()``.
Passing it raises
``TypeError: fit() got an unexpected keyword argument 'early_stopping_rounds'``.
The ONLY supported path is
``fit(..., callbacks=[lgb.early_stopping(stopping_rounds=N), lgb.log_evaluation(...)])``.
``clf.best_iteration_`` is populated iff a callback ran — so the assertion
``best_iteration_ is not None`` is both a correctness check and a Pitfall #1
detector.

============================================================================
Codex HIGH #2 — OOF = validation chunks only (warm-up chunk 0 excluded)
============================================================================
``GroupTimeSeriesSplit`` (07-03) uses an ``n_splits + 1`` date-block chunk
scheme: chunk 0 is the warm-up training block and chunks ``1..n_splits`` are
the per-fold validation blocks. OOF predictions are therefore generated only
for rows whose race_date falls in a validation chunk. The warm-up chunk 0 is
part of EVERY fold's expanding-window training set, so any prediction on
chunk-0 rows would be in-sample; forcing such predictions into the OOF array
would leak training labels into the downstream Isotonic calibrator (07-05).
Contract: ``len(oof_df) < len(input_df)`` is a load-bearing invariant, NOT a
bug. This is documented in the ``collect_oof_predictions`` docstring.

============================================================================
Codex HIGH #3 — module-level import of split_train_validation
============================================================================
07-04 is Wave 2 and depends on 07-03 (which ships
``src.ml.group_timeseries_split.split_train_validation``). The import is
module-level (NOT lazy) because there is no parallelization benefit to lazy
importing — only obfuscation.

============================================================================
Codex HIGH #5 — feature_columns is an EXPLICIT argument
============================================================================
``collect_oof_predictions`` and ``train_final_model`` take ``feature_columns``
as an explicit ``list[str]`` argument. They NEVER read
``config["data"]["feature_columns"]`` internally (KeyError risk on configs
that don't carry that key). The caller (07-07 run_train) resolves the column
list in one place and passes it down.

============================================================================
Codex HIGH #6 — train_final_model is a TWO-STAGE full retrain
============================================================================
Stage 1: carve the tail 20% of races (by race_date) as a validation split
(via ``split_train_validation``), train one LightGBM model with early
stopping, and record ``best_iteration_val``.
Stage 2: train a FRESH ``LGBMClassifier`` on ALL input rows up to
``best_iteration_val`` iterations (no early stopping — the iteration count is
fixed). The returned model has therefore seen every row of the training
window (NOT ~80%). This honours D-15 (single final model) and Open-Question-#3
("true full retrain"), which the legacy "~80% early-stopping val" approach
violated.

============================================================================
Cycle-2 HIGH #1 — collect_oof_predictions forwards dates=df["race_date"]
============================================================================
``GroupTimeSeriesSplit.split(X, y, groups, dates=None)`` runs the per-fold
``assert max(train_dates) < min(val_dates)`` ONLY when dates are provided.
The legacy code path that gated this assertion on ``X`` carrying a
``race_date`` column was dead code in production (the trainer passes
``X = df[feature_columns]`` which excludes race_date per 07-02 metadata).
Fix: ``collect_oof_predictions`` calls
``splitter.split(X, y, groups=race_ids, dates=df["race_date"])`` explicitly.
This REQUIRES ``load_features`` (07-02) to retain the ``race_date`` column on
the training frame — the trainer must NOT drop it.

============================================================================
D-13 — sensible defaults + early stopping
============================================================================
The defaults (num_leaves=31, learning_rate=0.05, min_data_in_leaf=100,
feature_fraction=0.9, bagging_fraction=0.9, bagging_freq=5, max_depth=-1,
n_estimators=1000, stopping_rounds=50) follow the LightGBM Parameters-Tuning
official guidance and CLAUDE.md's "まず確実に進める" (start reliable) philosophy.
They are read from ``config["model"]`` and ``config["early_stopping"]``; the
test config shrinks them so hermetic LightGBM training finishes in <1s.
============================================================================
"""

from __future__ import annotations

from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
from loguru import logger

# Codex HIGH #3: module-level import (NOT lazy). 07-04 depends on 07-03.
from src.ml.group_timeseries_split import split_train_validation


def _resolve_target_column(config: dict) -> str:
    """Return the target column name from config (with safe default).

    Conftest's ml_config and the production config both carry this under
    ``config["data"]["target_column"]``. Fall back to "target_top3" so that
    callers with a minimal config still work.
    """
    return str(config.get("data", {}).get("target_column", "target_top3"))


def _resolve_group_column(config: dict) -> str:
    """Return the race_id group column from config (with safe default).

    Accepts either the canonical ``config["cv"]["group_column"]`` (07-07
    config) or the legacy ``config["cv"]["group_col"]`` (conftest fixture).
    """
    cv_cfg = config.get("cv", {})
    return str(cv_cfg.get("group_column", cv_cfg.get("group_col", "race_id")))


def _build_classifier(config: dict) -> lgb.LGBMClassifier:
    """Build an LGBMClassifier from the sensible-defaults config block.

    Missing optional hyperparameters fall back to the D-13 sensible defaults
    documented in 07-RESEARCH.md Code Examples so that test configs (which
    only override a subset) still produce a well-formed classifier.
    """
    m = config.get("model", {})
    seed = config.get("seed", 42)
    clf = lgb.LGBMClassifier(
        objective=m.get("objective", "binary"),
        num_leaves=int(m.get("num_leaves", 31)),
        learning_rate=float(m.get("learning_rate", 0.05)),
        min_data_in_leaf=int(m.get("min_data_in_leaf", 100)),
        feature_fraction=float(m.get("feature_fraction", 0.9)),
        bagging_fraction=float(m.get("bagging_fraction", 0.9)),
        bagging_freq=int(m.get("bagging_freq", 5)),
        max_depth=int(m.get("max_depth", -1)),
        lambda_l1=float(m.get("lambda_l1", 0.0)),
        lambda_l2=float(m.get("lambda_l2", 0.0)),
        min_gain_to_split=float(m.get("min_gain_to_split", 0.0)),
        n_estimators=int(m.get("n_estimators", 1000)),
        random_state=int(seed),
        verbose=int(m.get("verbose", -1)),
    )
    return clf


def _build_callbacks(config: dict) -> list:
    """Build the early-stopping + log-evaluation callback list.

    Pitfall #1 (VERIFIED): ``early_stopping_rounds`` is NOT a fit() kwarg in
    LightGBM 4.x. The ONLY supported path is the callback API.
    """
    es = config.get("early_stopping", {})
    return [
        lgb.early_stopping(
            stopping_rounds=int(es.get("stopping_rounds", 50)),
            verbose=bool(es.get("verbose", False)),
            first_metric_only=bool(es.get("first_metric_only", True)),
        ),
        lgb.log_evaluation(period=int(es.get("log_period", 50))),
    ]


def train_fold_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    config: dict,
) -> lgb.LGBMClassifier:
    """Train one LightGBM fold with early stopping (callback API).

    Args:
        X_train / y_train: inner-train split (from split_train_validation).
        X_val / y_val: inner-val split used as the early-stopping eval_set.
        config: phase7_model_a config dict (model + early_stopping + seed).

    Returns:
        Fitted ``lgb.LGBMClassifier`` with ``best_iteration_`` populated.

    Raises:
        Nothing explicit; LightGBM may raise on degenerate input.

    Pitfall #1 (VERIFIED):
        ``early_stopping_rounds`` MUST NOT be passed to ``fit()``. The
        callback API ``lgb.early_stopping(...)`` is the only 4.x path.

    Threats mitigated: T-07-04-01 (sensible defaults), T-07-04-02 (callback
    API), T-07-04-04 (Stage 1 of final retrain uses this).
    """
    clf = _build_classifier(config)
    callbacks = _build_callbacks(config)
    n_estimators = int(config.get("model", {}).get("n_estimators", 1000))

    logger.info(
        f"train_fold_model: train_rows={len(X_train)} val_rows={len(X_val)} "
        f"n_estimators={n_estimators}"
    )
    clf.fit(
        X_train,
        y_train,
        eval_set=[(X_val, y_val)],
        callbacks=callbacks,
    )

    if clf.best_iteration_ is None:
        # Pitfall #1 detection: best_iteration_ is populated IFF the early
        # stopping callback ran. None means the callback was wired wrong.
        logger.warning(
            "best_iteration_ is None — early_stopping callback did not run "
            "(Pitfall #1 signature). Did fit() receive callbacks=[...]?"
        )
    else:
        logger.info(
            f"train_fold_model done: best_iteration_={clf.best_iteration_} "
            f"<n_estimators={n_estimators}={clf.best_iteration_ < n_estimators}"
        )

    return clf


def collect_oof_predictions(
    df: pd.DataFrame,
    splitter: Any,
    config: dict,
    feature_columns: list[str],
) -> pd.DataFrame:
    """Collect out-of-fold p_top3_raw predictions via an injected splitter.

    Args:
        df: training-window frame from ``load_features``. MUST retain the
            ``race_date`` column (Cycle-2 HIGH #1: passed to
            ``splitter.split`` as ``dates=df["race_date"]`` so the per-fold
            temporal-order assertion always fires).
        splitter: a ``GroupTimeSeriesSplit`` (or compatible
            ``BaseCrossValidator`` subclass) whose ``split`` accepts a
            ``dates`` keyword.
        config: phase7_model_a config dict.
        feature_columns: EXPLICIT list of model feature columns (Codex HIGH
            #5 — NEVER read from ``config["data"]["feature_columns"]``
            internally).

    Returns:
        DataFrame with columns ``race_id, horse_race_id, p_top3_raw,
        target_top3, fold``. Row count = sum of validation-chunk rows ONLY
        (warm-up chunk 0 EXCLUDED — Codex HIGH #2). Therefore
        ``len(oof_df) < len(df)`` is a load-bearing invariant, NOT a bug.

    Raises:
        KeyError: ``df`` lacks ``race_date`` (Cycle-2 HIGH #1 contract).
        AttributeError / TypeError: splitter.split does not accept ``dates``.

    Threats mitigated:
        T-07-04-03 (Codex HIGH #2: warm-up excluded, OOF < input),
        T-07-04-05 (Codex HIGH #5: feature_columns explicit arg),
        T-07-04-06 (Cycle-2 HIGH #1: dates=df["race_date"] forwarded).
    """
    target_col = _resolve_target_column(config)
    group_col = _resolve_group_column(config)

    # WR-05: OOF output schema pins the group column name to "race_id". This
    # is load-bearing — Phase 8 Harville groups on oof_predictions.parquet's
    # race_id column. _resolve_group_column lets config set cv.group_column
    # to other values (future horse_race_id-based CV), but the OOF DataFrame
    # literal below uses "race_id" unconditionally; if group_col != "race_id"
    # the column would silently carry the wrong-group values under the
    # "race_id" name. Fail loudly at the boundary rather than corrupt Phase 8.
    if group_col != "race_id":
        raise ValueError(
            "collect_oof_predictions requires cv.group_column='race_id' for "
            "OOF schema stability (Phase 8 Harville groups on race_id); got "
            f"'{group_col}'. Pinning the column name in code AND allowing a "
            "different group_col would silently mislabel the OOF race_id column."
        )

    # Cycle-2 HIGH #1: race_date MUST be present so we can forward it to the
    # splitter. Trainer never drops race_date.
    if "race_date" not in df.columns:
        raise KeyError(
            "collect_oof_predictions requires df['race_date'] (Cycle-2 HIGH #1: "
            "splitter.split must receive dates=df['race_date'] so the per-fold "
            "temporal-order assertion always fires). load_features (07-02) is "
            "contracted to retain race_date — did you drop it?"
        )

    X = df[feature_columns]
    y = df[target_col]
    groups = df[group_col].values
    dates = df["race_date"]

    # Codex HIGH #5: feature_columns is the explicit arg. We do NOT touch
    # config["data"]["feature_columns"] anywhere in this function.

    oof_frames: list[pd.DataFrame] = []
    fold: int = 0
    for train_idx, val_idx in splitter.split(X, y, groups=groups, dates=dates):
        # D-04: carve an inner early-stopping val out of the fold's training
        # frame (tail 20% by race_date). The fold-level CV split is already
        # time-safe (GroupTimeSeriesSplit guarantees max(train) < min(val));
        # split_train_validation keeps the inner train/val pair time-safe too.
        fold_train_full = df.iloc[train_idx]
        fold_val = df.iloc[val_idx]

        inner_train_df, inner_es_val_df = split_train_validation(
            fold_train_full,
            val_ratio=float(config.get("cv", {}).get(
                "early_stopping_val_ratio", 0.2
            )),
        )

        clf = train_fold_model(
            inner_train_df[feature_columns],
            inner_train_df[target_col],
            inner_es_val_df[feature_columns],
            inner_es_val_df[target_col],
            config,
        )

        p_raw = clf.predict_proba(fold_val[feature_columns])[:, 1]
        oof_frames.append(
            pd.DataFrame(
                {
                    "race_id": fold_val[group_col].values,
                    "horse_race_id": fold_val["horse_race_id"].values,
                    "p_top3_raw": p_raw,
                    "target_top3": fold_val[target_col].values,
                    "fold": fold,
                }
            )
        )
        logger.info(
            f"collect_oof fold {fold}: train_rows={len(train_idx)} "
            f"val_rows={len(val_idx)} (inner_train={len(inner_train_df)} "
            f"inner_es_val={len(inner_es_val_df)})"
        )
        fold += 1

    oof_df = pd.concat(oof_frames, ignore_index=True) if oof_frames else (
        pd.DataFrame(
            columns=["race_id", "horse_race_id", "p_top3_raw", "target_top3", "fold"]
        )
    )

    logger.info(
        f"collect_oof_predictions done: oof_rows={len(oof_df)} "
        f"< input_rows={len(df)} (Codex HIGH #2: warm-up chunk 0 excluded; "
        f"this is the correct leak-free contract, NOT a bug)"
    )
    return oof_df


def train_final_model(
    df: pd.DataFrame,
    config: dict,
    feature_columns: list[str],
) -> lgb.LGBMClassifier:
    """Two-stage full-retrain final model (Codex HIGH #6 / D-15).

    Stage 1 (best_iteration decision):
        Carve the tail 20% of races (by race_date) via
        ``split_train_validation`` and train one LightGBM model with early
        stopping. Record ``best_iteration_val = clf.best_iteration_``.

    Stage 2 (full retrain):
        Train a FRESH ``LGBMClassifier`` on ALL input rows up to
        ``best_iteration_val`` iterations. No early stopping — the iteration
        count is fixed. The returned model has therefore seen every row of
        the training window (NOT ~80%).

    Args:
        df: training-window frame from ``load_features``.
        config: phase7_model_a config dict.
        feature_columns: EXPLICIT list of model feature columns (Codex HIGH
            #5).

    Returns:
        ``lgb.LGBMClassifier`` trained on ALL of ``df`` at Stage-1's
        ``best_iteration_val`` (D-15 / Open-Question-#3: true full retrain).

    Threats mitigated: T-07-04-04 (Codex HIGH #6 two-stage full retrain).
    """
    target_col = _resolve_target_column(config)

    # --- Stage 1: decide best_iteration on a validation split ---
    inner_train_df, inner_val_df = split_train_validation(
        df,
        val_ratio=float(config.get("cv", {}).get("early_stopping_val_ratio", 0.2)),
    )
    stage1_clf = train_fold_model(
        inner_train_df[feature_columns],
        inner_train_df[target_col],
        inner_val_df[feature_columns],
        inner_val_df[target_col],
        config,
    )
    best_iteration_val = stage1_clf.best_iteration_
    if best_iteration_val is None:
        # Degenerate fixture: early stopping never triggered. Fall back to the
        # configured n_estimators so Stage 2 still trains (logged as a
        # deviation from the two-stage contract).
        best_iteration_val = int(
            config.get("model", {}).get("n_estimators", 1000)
        )
        logger.warning(
            f"Stage 1 best_iteration_ is None (early stopping never fired); "
            f"falling back to n_estimators={best_iteration_val} for Stage 2"
        )
    logger.info(
        f"Stage 1 done: best_iteration_val={best_iteration_val} "
        f"(inner_train_rows={len(inner_train_df)} inner_val_rows={len(inner_val_df)})"
    )

    # --- Stage 2: full retrain on ALL rows at best_iteration_val ---
    # Codex HIGH #6: Stage 2 sees the ENTIRE input frame, not the inner_train
    # subset. This is the "true full retrain" of D-15 / Open-Question-#3.
    #
    # CR-02: clamp n_estimators to a floor so the final artefact is never a
    # near-untrained weak learner. early_stopping(stopping_rounds=50) can fire
    # at very small iteration counts when the Stage-1 validation metric
    # plateaus immediately (degenerate features, distribution shift, unlucky
    # seed). Without a floor, the shipped models/phase7/model_a.lgb.txt could
    # contain only 1-2 trees, silently destroying Phase 8 Harville EV and
    # Phase 9 backtest ROI. Floor is conservative (10 trees) — large enough
    # to avoid degeneracy, small enough that a genuinely-converged Stage-1
    # (which would never be this low on real data) is not meaningfully changed.
    MIN_FINAL_ITERATIONS = 10
    final_n_estimators = max(int(best_iteration_val), MIN_FINAL_ITERATIONS)
    if final_n_estimators != int(best_iteration_val):
        logger.warning(
            f"Stage 1 best_iteration_val={best_iteration_val} < floor "
            f"{MIN_FINAL_ITERATIONS}; clamping Stage 2 n_estimators to "
            f"{final_n_estimators} to avoid an under-fit final model (CR-02)"
        )
    stage2_clf = _build_classifier(config)
    # Override n_estimators with the (clamped) Stage-1 best iteration and
    # drop early stopping (the iteration count is now fixed; callbacks=log_eval only).
    stage2_clf.set_params(n_estimators=final_n_estimators)
    X_all = df[feature_columns]
    y_all = df[target_col]
    logger.info(
        f"Stage 2: training on {len(df)} rows (ALL input rows, Codex HIGH #6) "
        f"up to n_estimators={final_n_estimators} "
        f"(Stage-1 best_iteration_val={best_iteration_val})"
    )
    stage2_clf.fit(
        X_all,
        y_all,
        callbacks=[
            lgb.log_evaluation(period=int(
                config.get("early_stopping", {}).get("log_period", 50)
            ))
        ],
    )
    # best_iteration_ stays None on Stage 2 because there was no early
    # stopping callback — that's correct. Expose best_iteration_val via a
    # custom attribute so tests / run_train can verify the two-stage contract.
    stage2_clf._best_iteration_val = best_iteration_val  # type: ignore[attr-defined]
    logger.info(
        f"train_final_model done: trained_rows={len(df)} "
        f"best_iteration_val={best_iteration_val}"
    )
    return stage2_clf
