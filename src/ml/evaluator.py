"""Evaluation metrics + reliability diagram for the Model A top-3 probability model.

This module encodes RESEARCH.md "ECE 計算（手動実装）+ Reliability Diagram"
(lines 590-662, VERIFIED code) and the evaluator-side decisions D-06 / D-11.

Contract (D-06 主指標 AUC / D-11 ECE<0.02 + reliability diagram):
    compute_ece(y_true, y_prob, n_bins=10)            -> float
    evaluate(y_true, y_prob_raw, y_prob_calibrated,
             n_bins=10)                               -> dict
    reliability_diagram(y_true, y_prob, n_bins=10,
                        save_path=None)               -> matplotlib.figure.Figure

Why ECE is hand-rolled (not sklearn):
    scikit-learn has NOT incorporated ECE as of 1.9.0 — upstream issue #18268
    (https://github.com/scikit-learn/scikit-learn/issues/18268) remains open.
    This module implements the Guo et al. 2017 definition of ECE directly.
    (RESEARCH.md "Don't Hand-Roll" — ECE is the documented exception.)

Leak / sanity boundary (Pitfall #5 — T-07-06-02, accept mitigation here):
    This module is READ-ONLY over its inputs; it never fits anything. The
    Pitfall #5 holdout-recalibration risk lives in ``calibrator.py``
    (``apply_calibrator`` accepts no labels). ``evaluate`` merely *reports*
    ECE; if ``ece_calibrated`` is suspiciously good (e.g. near 0.0 or
    materially better than ``ece_raw`` without a real calibration step),
    that is a leak signal originating upstream, not here. ``evaluate`` emits
    ``logger.warning`` whenever ``ece_calibrated >= 0.02`` (D-11 violation
    smell) so Phase 7/8 logs surface the regression immediately.

D-09 scope note (Cycle-5 MEDIUM carry-over resolution — option (b)):
    ``evaluate`` operates purely on (y_true, y_prob_raw, y_prob_calibrated)
    arrays with no race grouping, so race-level Top-3 recall (D-09 "参考出力")
    CANNOT be computed inside this function. D-09 belongs to the orchestrator
    (07-07 ``run_train``), which retains ``race_id`` and can group
    predictions per race. Keeping ``evaluate`` array-only preserves its
    unit-testability with small hermetic numpy fixtures (PATTERNS.md analog
    ``tests/schemas/test_audit.py``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import numpy as np
from loguru import logger
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

__all__ = ["compute_ece", "evaluate", "reliability_diagram"]


def compute_ece(
    y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10
) -> float:
    """Expected Calibration Error (Guo et al. 2017), hand-rolled.

    ECE = Σ_m (|B_m| / N) × |acc(B_m) - conf(B_m)|

    - M = ``n_bins`` (10 が標準). equal-width bins over [0, 1]:
      [0.0, 0.1), [0.1, 0.2), ..., [0.9, 1.0]. 最終 bin のみ閉区間
      (``np.digitize`` with ``bins[1:-1]`` boundaries produces this).
    - ``|B_m| / N`` = bin m のサンプル割合
    - ``acc(B_m)`` = bin m 内の観測陽性率（実際の top-3 率）
    - ``conf(B_m)`` = bin m 内の平均予測確率

    完全に校正されたモデル: ECE = 0.0. D-11 成功基準: ECE < 0.02.
    戻り値は常に有限 float で [0.0, 1.0] に収まる（完全予測で 0.0・
    最悪ケースで高々 1.0）。NaN 含む入力は NaN 行を除外して計算し、
    全行 NaN の場合は 0.0 を返す（WR-04: 呼び出し元への nan 伝播防止）。

    Why not sklearn: ECE は scikit-learn 未収録（issue #18268 open）。
    RESEARCH.md "Don't Hand-Roll" で ECE は手動実装の例外として明記済み。
    """
    y_true_arr = np.asarray(y_true, dtype=float)
    y_prob_arr = np.asarray(y_prob, dtype=float)
    # WR-04: drop NaN rows explicitly. Without this, y_true_arr.mean() over a
    # bin containing NaN labels returns nan, propagating into ece_calibrated
    # and thence into metrics.json as the non-standard 'NaN' literal (CR-01).
    # It also breaks the run_train check 'if ece_calibrated >= ece_tolerance'
    # — nan >= 0.02 is always False, so a D-11 violation would be silently
    # swallowed. Masking NaN upholds the docstring contract that the return
    # is always a finite float in [0.0, 1.0].
    if y_true_arr.shape[0] != y_prob_arr.shape[0]:
        raise ValueError(
            f"compute_ece: y_true and y_prob length mismatch "
            f"({y_true_arr.shape[0]} vs {y_prob_arr.shape[0]})"
        )
    mask = ~(np.isnan(y_true_arr) | np.isnan(y_prob_arr))
    y_true_arr = y_true_arr[mask]
    y_prob_arr = y_prob_arr[mask]
    n = len(y_true_arr)
    if n == 0:
        logger.warning(
            "compute_ece: empty or all-NaN input after NaN drop, returning 0.0"
        )
        return 0.0

    bins = np.linspace(0.0, 1.0, n_bins + 1)
    # 最終 bin は閉区間 [0.9, 1.0]、それ以外は半開区間 [low, high).
    # np.digitize with internal boundaries bins[1:-1] maps [0, bins[1]) -> 0,
    # ..., [bins[-2], 1.0] -> n_bins-1 (final bin closed by construction).
    bin_indices = np.digitize(y_prob_arr, bins[1:-1], right=False)

    ece = 0.0
    for b in range(n_bins):
        mask = bin_indices == b
        if not mask.any():
            continue
        bin_size = int(mask.sum())
        acc = float(y_true_arr[mask].mean())
        conf = float(y_prob_arr[mask].mean())
        ece += (bin_size / n) * abs(acc - conf)
    return float(ece)


def _safe_auc(y_true: np.ndarray, y_prob: np.ndarray) -> Optional[float]:
    """AUC guard for single-class ``y_true`` (CR-01).

    ``roc_auc_score`` returns ``nan`` (with ``UndefinedMetricWarning``) when
    ``y_true`` contains only one class. That ``nan`` would propagate into the
    metrics dict and be serialised as the non-standard JSON literal ``NaN``
    by ``run_train``'s ``json.dump``, breaking strict JSON consumers (jq,
    Node.js ``JSON.parse``, pyarrow ``read_json``, Phase 8/9 / 07-08 verify).

    Returns ``None`` on single-class input (the JSON-serialisable sentinel
    for "AUC undefined"); otherwise the finite float AUC.

    Single-class holdout is rare but reachable via subset evaluation
    (e.g. grade-only race slices) and via degenerate hermetic fixtures.
    Behaviour is UNCHANGED when both classes are present.
    """
    if len(np.unique(y_true)) < 2:
        logger.warning(
            "evaluate: single-class y_true "
            f"(unique={np.unique(y_true).tolist()}, n={len(y_true)}) — "
            "AUC undefined, returning None (CR-01: avoid nan -> non-standard JSON)"
        )
        return None
    return float(roc_auc_score(y_true, y_prob))


def _safe_logloss(
    y_true: np.ndarray, y_prob: np.ndarray, label: str
) -> Optional[float]:
    """``log_loss`` guard for single-class ``y_true`` (CR-01 companion).

    Unlike AUC, ``sklearn.log_loss`` does NOT return nan on single-class
    input — it raises ``ValueError`` outright ("y_true contains only one
    label"). That crash would propagate up through ``run_train`` and halt
    the pipeline. Guard it the same way as AUC: return ``None`` (JSON
    ``null``) on single-class input.
    """
    if len(np.unique(y_true)) < 2:
        logger.warning(
            f"evaluate: single-class y_true ({label}) — log_loss undefined, "
            "returning None (CR-01)"
        )
        return None
    return float(log_loss(y_true, y_prob))


def _format_metric(value: Optional[float]) -> str:
    """Format a metric for logging, tolerating ``None`` (CR-01)."""
    return "n/a" if value is None else f"{value:.4f}"


def evaluate(
    y_true: np.ndarray,
    y_prob_raw: np.ndarray,
    y_prob_calibrated: np.ndarray,
    n_bins: int = 10,
) -> dict:
    """Compute AUC / Brier / logloss / ECE for raw vs calibrated predictions.

    D-06: 主指標 = AUC (ranking accuracy). Brier / logloss は補助指標.
    Both raw and calibrated AUC are computed — calibration is monotonic-preserving
    under IsotonicRegression so AUC is normally unchanged, but reporting both
    guards against a future Platt/sigmoid calibrator that *would* re-rank.

    D-11: ``ece_calibrated`` is the success-criterion metric (< 0.02).
    ``ece_raw`` is reported for reference. When ``ece_calibrated >= 0.02`` a
    ``logger.warning`` is emitted (D-11 violation smell, T-07-06-02).

    Returns a dict with documented keys (analog: ``run_all_validations``
    dict-aggregation pattern in src/pipeline/validators.py). Phase 8/9
    consumes this dict directly.

    CR-01 single-class safety: when ``y_true`` contains only one class,
    ``auc_*`` and ``logloss_*`` are returned as ``None`` (NOT ``nan`` and
    NOT a crash). ``roc_auc_score`` would otherwise return ``nan`` (which
    ``json.dump`` emits as the non-standard ``NaN`` literal); ``log_loss``
    would otherwise raise ``ValueError`` outright. ``brier_score_loss``
    accepts single-class input and returns a finite float, so it is left
    unchanged. ``ece_*`` are already guarded by ``compute_ece``. Behaviour
    is UNCHANGED when both classes are present.
    """
    y_true_arr = np.asarray(y_true, dtype=float)
    y_prob_raw_arr = np.asarray(y_prob_raw, dtype=float)
    y_prob_cal_arr = np.asarray(y_prob_calibrated, dtype=float)
    n_samples = int(len(y_true_arr))

    auc_raw = _safe_auc(y_true_arr, y_prob_raw_arr)
    auc_calibrated = _safe_auc(y_true_arr, y_prob_cal_arr)
    brier_raw = float(brier_score_loss(y_true_arr, y_prob_raw_arr))
    brier_calibrated = float(brier_score_loss(y_true_arr, y_prob_cal_arr))
    logloss_raw = _safe_logloss(y_true_arr, y_prob_raw_arr, "raw")
    logloss_calibrated = _safe_logloss(y_true_arr, y_prob_cal_arr, "calibrated")
    ece_raw = compute_ece(y_true_arr, y_prob_raw_arr, n_bins=n_bins)
    ece_calibrated = compute_ece(y_true_arr, y_prob_cal_arr, n_bins=n_bins)

    result = {
        "auc_raw": auc_raw,
        "auc_calibrated": auc_calibrated,
        "brier_raw": brier_raw,
        "brier_calibrated": brier_calibrated,
        "logloss_raw": logloss_raw,
        "logloss_calibrated": logloss_calibrated,
        "ece_raw": ece_raw,
        "ece_calibrated": ece_calibrated,
        "n_samples": n_samples,
    }

    logger.info(
        "evaluate: n_samples={} auc(raw={} cal={}) "
        "brier(raw={:.4f} cal={:.4f}) logloss(raw={} cal={}) "
        "ece(raw={:.4f} cal={:.4f})".format(
            n_samples,
            _format_metric(auc_raw), _format_metric(auc_calibrated),
            brier_raw, brier_calibrated,
            _format_metric(logloss_raw), _format_metric(logloss_calibrated),
            ece_raw, ece_calibrated,
        )
    )
    if ece_calibrated >= 0.02:
        logger.warning(
            "evaluate: ece_calibrated={:.4f} >= D-11 threshold 0.02 "
            "(calibration goal not met — check calibrator fit / Pitfall #5 leak)".format(
                ece_calibrated
            )
        )
    return result


def reliability_diagram(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    n_bins: int = 10,
    save_path: Optional[Union[str, Path]] = None,
):
    """Render a reliability diagram (D-11) and optionally save as PNG.

    Uses the matplotlib ``Agg`` backend (forced inside the function so the
    module import is headless-safe — no Tkinter / display required for CLI
    runs, Pitfall noted in RESEARCH.md Code Examples lines 625-661).

    Each bin shows observed top-3 rate (``acc``) vs mean predicted probability
    (``conf``). A perfectly calibrated model traces the diagonal ``y = x``
    (plotted as ``'k--'``). Empty bins are plotted at their bin centre with
    NaN height (transparent bar) so the x-axis coverage is always complete.

    Args:
        y_true: observed binary labels (1 = top-3 hit).
        y_prob: predicted probabilities in [0, 1].
        n_bins: number of equal-width bins over [0, 1] (default 10).
        save_path: if given, ``fig.savefig(save_path, dpi=150,
            bbox_inches='tight')`` is called. Parent dirs are NOT created
            here (caller's responsibility; tmp_ml_output_dir is pre-made in
            tests).

    Returns:
        ``matplotlib.figure.Figure`` (caller may ``plt.close(fig)`` or
        further customize).
    """
    # Function-local import + Agg backend (headless-safe; module-level import
    # would pull matplotlib into every evaluator call even when no plotting).
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    y_true_arr = np.asarray(y_true, dtype=float)
    y_prob_arr = np.asarray(y_prob, dtype=float)

    bins = np.linspace(0.0, 1.0, n_bins + 1)
    bin_indices = np.digitize(y_prob_arr, bins[1:-1], right=False)
    accs, confs, sizes = [], [], []
    for b in range(n_bins):
        mask = bin_indices == b
        if not mask.any():
            accs.append(np.nan)
            confs.append((bins[b] + bins[b + 1]) / 2.0)
            sizes.append(0)
        else:
            accs.append(float(y_true_arr[mask].mean()))
            confs.append(float(y_prob_arr[mask].mean()))
            sizes.append(int(mask.sum()))

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.bar(confs, accs, width=0.08, alpha=0.7, label="Model")
    ax.plot([0, 1], [0, 1], "k--", label="Perfect calibration")
    ax.set_xlabel("Mean predicted probability")
    ax.set_ylabel("Observed top-3 rate")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend()
    ax.set_title("Reliability Diagram")

    if save_path is not None:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        logger.info(f"reliability_diagram: saved to {save_path}")
    return fig
