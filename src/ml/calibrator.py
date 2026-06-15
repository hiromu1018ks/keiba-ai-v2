"""Isotonic probability calibration for the Model A top-3 probability model.

This module encodes RESEARCH.md Pattern 2 (leak-free isotonic calibration) and
Pitfall #5 (NEVER re-fit the calibrator on holdout labels).

Contract (D-10 / D-12 / D-15):
    fit_calibrator(oof_raw, y_oof)   -> IsotonicRegression
    apply_calibrator(iso, raw_preds)  -> np.ndarray   (holdout / live, predict only)
    save_calibrator(iso, path)        -> Path          (.joblib, D-15)
    load_calibrator(path)             -> IsotonicRegression

Leak-prevention boundary (analog: src/pipeline/feature_generator.py
``compute_finish_time_zscore`` race-boundary safety docstring):

    The IsotonicRegression is fit on OOF predictions ONLY. OOF predictions are
    produced by each fold's model on the validation chunk that fold did NOT
    train on (guaranteed by GroupTimeSeriesSplit). Therefore the calibrator
    learns the prediction distribution on data it has effectively never seen,
    and applying it to the holdout is leak-free (Pitfall #5).

    Codex HIGH #2 (OOF = validation chunks only, warm-up excluded):
    The ``oof_raw`` array passed to ``fit_calibrator`` MUST consist of the
    validation-chunk predictions only (chunks 1..n_splits in the
    ``n_splits + 1`` date-block scheme of GroupTimeSeriesSplit). The warm-up
    chunk 0 is part of every fold's expanding-window training set, so a
    prediction for chunk-0 rows would be an in-sample prediction; forcing such
    predictions into the OOF array would leak the training labels into
    calibration. Consequence: ``len(oof_raw)`` is strictly less than the total
    number of rows in the training window (warm-up chunk 0 + all train-body
    rows are excluded from OOF/calibration). This is the correct, leak-free
    state and is asserted by the caller (07-04 ``collect_oof_predictions``),
    not re-checked here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

import joblib
import numpy as np
from loguru import logger
from sklearn.isotonic import IsotonicRegression

__all__ = [
    "fit_calibrator",
    "apply_calibrator",
    "save_calibrator",
    "load_calibrator",
]


def fit_calibrator(oof_raw: np.ndarray, y_oof: np.ndarray) -> IsotonicRegression:
    """Fit an Isotonic calibrator on OOF predictions and labels.

    Leak-prevention boundary (D-10 / D-12, Pitfall #5):

        ``oof_raw`` are out-of-fold predictions: each row's prediction comes
        from the fold model that did NOT train on that row's race
        (GroupTimeSeriesSplit guarantee). The calibrator therefore learns the
        prediction-vs-truth mapping on data that is, from its perspective,
        genuinely unseen. Applying the returned calibrator to the holdout raw
        predictions is leak-free.

        NEVER call this function with holdout labels (Pitfall #5). Re-fitting
        on holdout makes the holdout ECE look suspiciously close to zero and
        destroys the integrity of the final evaluation.

        Codex HIGH #2 — OOF = validation chunks only:
        ``oof_raw`` must contain predictions for the validation chunks
        (chunks 1..n_splits) only. The warm-up chunk 0 of the
        ``n_splits + 1`` date-block scheme is part of every fold's
        expanding-window training set, so it has no OOF prediction; injecting
        chunk-0 rows here would introduce in-sample predictions and leak.
        ``len(oof_raw)`` is therefore strictly less than the training-window
        row count — this is the expected, leak-free state.

    Parameters
    ----------
    oof_raw : numpy.ndarray, shape (n_oof,)
        Raw (pre-calibration) top-3 probability predictions for the
        validation-chunk rows of the training window. Values need not be
        bounded; ``IsotonicRegression`` with ``out_of_bounds="clip"`` handles
        extrapolation safely.
    y_oof : numpy.ndarray, shape (n_oof,)
        Binary top-3 labels (0/1) aligned with ``oof_raw``.

    Returns
    -------
    sklearn.isotonic.IsotonicRegression
        Fit calibrator. ``y_min=0.0``, ``y_max=1.0`` guarantee calibrated
        outputs are bounded in [0, 1]; ``out_of_bounds="clip"`` guarantees
        extrapolation beyond the observed input range stays in range.
    """
    oof_raw = np.asarray(oof_raw, dtype=float)
    y_oof = np.asarray(y_oof)
    if oof_raw.shape[0] != y_oof.shape[0]:
        raise ValueError(
            f"fit_calibrator: oof_raw and y_oof length mismatch "
            f"({oof_raw.shape[0]} vs {y_oof.shape[0]})"
        )
    if oof_raw.ndim != 1:
        raise ValueError(
            f"fit_calibrator: oof_raw must be 1-D, got shape {oof_raw.shape}"
        )

    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    iso.fit(oof_raw, y_oof)

    logger.info(
        "fit_calibrator: fitted IsotonicRegression on "
        f"{oof_raw.shape[0]} OOF rows "
        f"(raw range [{float(np.min(oof_raw)):.4f}, {float(np.max(oof_raw)):.4f}]; "
        f"iso X_min_={float(iso.X_min_):.4f}, X_max_={float(iso.X_max_):.4f}; "
        f"len(oof_raw) < training-window row count is expected — "
        f"warm-up chunk 0 is excluded from OOF, Codex HIGH #2)"
    )
    return iso


def apply_calibrator(
    iso: IsotonicRegression, raw_preds: np.ndarray
) -> np.ndarray:
    """Apply a fit Isotonic calibrator to raw predictions.

    Safe for holdout / live data (D-10): the calibrator is only ever fit on
    OOF (validation chunks only, warm-up excluded — Codex HIGH #2). This
    function performs ``predict`` only; it accepts no labels, so Pitfall #5
    (holdout recalibration leakage) is structurally impossible.

    Parameters
    ----------
    iso : sklearn.isotonic.IsotonicRegression
        Calibrator returned by ``fit_calibrator``.
    raw_preds : numpy.ndarray, shape (n,)
        Raw (pre-calibration) top-3 probability predictions.

    Returns
    -------
    numpy.ndarray, shape (n,)
        Calibrated probabilities in [0.0, 1.0], monotonic non-decreasing in
        ``raw_preds``. Extrapolation beyond the fit input range is clipped to
        the boundary calibrated values. An empty input returns an empty
        output (WR-02).

    Raises
    ------
    Nothing — empty input is handled gracefully (WR-02) to stay consistent
    with the trainer's OOF contract (``collect_oof_predictions`` may return
    an empty DataFrame on degenerate input, and run_train applies the
    calibrator to OOF rows at line ~294).
    """
    raw_preds = np.asarray(raw_preds, dtype=float)
    if raw_preds.size == 0:
        # WR-02: sklearn's check_array raises "Found array with 0 sample(s)"
        # on empty input. Mirror the trainer's empty-OOF contract (return
        # empty) so run_train Step 7 / OOF parquet write do not crash on
        # degenerate folds or empty hermetic fixtures.
        return raw_preds
    return iso.predict(raw_preds)


def save_calibrator(
    iso: IsotonicRegression, path: Union[str, Path]
) -> Path:
    """Persist a fit calibrator to a ``.joblib`` file (D-15).

    D-15 specifies the ``.joblib`` format (NOT pickle) for the Isotonic
    calibrator. ``joblib.dump`` is the canonical scikit-learn model
    serialization route and preserves the fit ``IsotonicRegression`` state
    for Phase 8/9 consumption.

    Parameters
    ----------
    iso : sklearn.isotonic.IsotonicRegression
        Calibrator returned by ``fit_calibrator``.
    path : str | pathlib.Path
        Destination path. Parent directories are created if missing. The
        ``.joblib`` extension is conventional (D-15) but not enforced here.

    Returns
    -------
    pathlib.Path
        Resolved destination path.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(iso, path)
    logger.info(f"save_calibrator: wrote calibrator to {path}")
    return path


def load_calibrator(path: Union[str, Path]) -> IsotonicRegression:
    """Load a fit calibrator from a ``.joblib`` file (D-15).

    Parameters
    ----------
    path : str | pathlib.Path
        Source path previously written by ``save_calibrator``.

    Returns
    -------
    sklearn.isotonic.IsotonicRegression
        Fit calibrator ready for use with ``apply_calibrator``.

    Raises
    ------
    FileNotFoundError
        If ``path`` does not exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"load_calibrator: calibrator not found at {path}")
    iso: IsotonicRegression = joblib.load(path)
    logger.info(f"load_calibrator: loaded calibrator from {path}")
    return iso
