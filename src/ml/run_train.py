"""Phase 7 Model A orchestrator: ``run_train`` single-entry pipeline.

Waves 1+2 module integration point for Phase 7 (MODA-01..04). The function
``run_train`` orchestrates the full pipeline:

    load_features  (07-02)
        -> GroupTimeSeriesSplit.split       (07-03)
        -> collect_oof_predictions          (07-04, OOF = val chunks only)
        -> fit_calibrator on OOF            (07-05, leak-free Isotonic)
        -> train_final_model two-stage      (07-04, Codex HIGH #6)
        -> apply_calibrator on holdout      (07-05, Pitfall #5 structural)
        -> evaluate + reliability_diagram   (07-06)
        -> compute_popularity_baseline      (07-06)
        -> persist 6 D-15 artifacts

CLI entry point: ``python -m src.ml.run_train`` (setuptools project, NOT
``poetry run`` — per CLAUDE.md the repo uses setuptools).

Design analog: ``src/pipeline/integration.py::integrate_standard_layer``
(numpy-style docstring, per-step ``logger.info``, dict return value,
``Path.mkdir(parents=True, exist_ok=True)`` pattern).

Codex HIGH concerns resolved here:
    * HIGH #2 — OOF row count < train-window row count is logged at runtime
      and asserted by the hermetic test (warm-up chunk 0 excluded).
    * HIGH #4 — ``expected_counts`` parameter forwarded to ``load_features``;
      the UNIFIED sentinel (None=production assert / []=hermetic bypass /
      non-empty dict=custom) is identical to 07-02. Empty dict ``{}`` is NOT
      used (07-02 raises TypeError on it).
    * HIGH #5 — ``feature_columns`` is resolved ONCE from
      ``config["data"]["feature_columns"]`` (minus ``data.drop_columns``) and
      passed as an explicit argument to ``collect_oof_predictions`` and
      ``train_final_model``. The trainer modules NEVER read the config key
      themselves.
    * HIGH #6 — ``train_final_model`` (07-04) is the two-stage full retrain;
      ``run_train`` simply calls it.

Cycle-2 HIGH fixes:
    * #1 — ``run_train`` does NOT drop ``race_date``; ``load_features`` (07-02)
      returns frames that retain it and ``collect_oof_predictions`` (07-04)
      forwards ``dates=df["race_date"]`` to ``splitter.split``.
    * #2 — UNIFIED expected_counts sentinel (see above).
    * #3 — ``metrics["oof_rows"] = int(len(oof_df))`` is written into the
      metrics dict before ``metrics.json`` is persisted. Producer/consumer
      contract with 07-08 phase-gate verify: key="oof_rows", type=int,
      value=len(oof_df) where oof_df = collect_oof_predictions return value.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd
import yaml
from loguru import logger

from src.ml.baseline import compute_popularity_baseline
from src.ml.calibrator import (
    apply_calibrator,
    fit_calibrator,
    save_calibrator,
)
from src.ml.data_loader import load_features
from src.ml.evaluator import evaluate, reliability_diagram
from src.ml.group_timeseries_split import GroupTimeSeriesSplit
from src.ml.trainer import collect_oof_predictions, train_final_model


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------


def run_train(
    config_path: Union[str, Path] = "config/phase7_model_a.yaml",
    expected_counts: Optional[Union[dict, list]] = None,
) -> Dict[str, Any]:
    """Run the full Phase 7 Model A training + evaluation pipeline.

    Parameters
    ----------
    config_path : str | pathlib.Path, default ``"config/phase7_model_a.yaml"``
        Path to the YAML config (D-14). All hyperparameters, window
        boundaries, fold settings, feature columns and artifact paths are
        read from here.
    expected_counts : dict | list | None, default ``None``
        UNIFIED sentinel forwarded to ``load_features`` (Cycle-2 HIGH #2):

            * ``None`` (default) — assert production row counts
              (PRODUCTION_COUNTS 322510/23288/66343/4740). Used by the 07-08
              phase-gate run against the real corpus.
            * ``[]`` (empty LIST) — bypass the row-count assert. Used by the
              07-07 hermetic E2E test on a small tmp_path fixture
              (Codex HIGH #4).
            * non-empty ``dict`` — assert the given custom counts.
            * ``{}`` (empty dict) is NOT accepted; 07-02 raises TypeError on
              it (Cycle-2 HIGH #2 + Cycle-5 MEDIUM tightening).

    Returns
    -------
    dict
        Paths to the persisted D-15 artifacts::

            {
                "model":      Path,  # models/phase7/model_a.lgb.txt
                "calibrator": Path,  # models/phase7/isotonic_calibrator.joblib
                "oof":        Path,  # data/model/oof/oof_predictions.parquet
                "holdout":    Path,  # data/model/oof/holdout_predictions.parquet
                "report":     Path,  # reports/phase7/evaluation_report.md
                "metrics":    Path,  # reports/phase7/metrics.json
                "diagram":    Path,  # reports/phase7/reliability_diagram.png
                "config":     Path,  # the input config_path (referenced, not copied)
            }

    Raises
    ------
    FileNotFoundError
        If ``config_path`` does not exist or (in production mode) the feature
        Parquet is missing.
    AssertionError
        If production row counts diverge from PRODUCTION_COUNTS (only when
        ``expected_counts is None``).
    TypeError
        If ``expected_counts`` is an empty dict ``{}`` (Cycle-2 HIGH #2).

    Notes
    -----
    The pipeline is reproducible from the fixed seed in the config (D-14,
    ``seed: 42``). The config YAML is referenced (NOT copied) — re-running
    ``run_train(config_path=...)`` with the same config reproduces the
    artifacts. Holdout predictions are NEVER used to refit the calibrator
    (Pitfall #5 structural guard in ``apply_calibrator``).
    """
    config_path = Path(config_path)
    logger.info(f"run_train: starting (config_path={config_path})")

    # ----- Step 1: load_config -----
    if not config_path.is_file():
        raise FileNotFoundError(f"run_train: config not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # WR-06: validate required config keys up front with an actionable message.
    # Many keys were accessed via bracket notation (config["data"]["..."]) deep
    # inside the function, producing a low-level KeyError ('train_window') with
    # no indication of what to fix. Optional keys (drop_columns, ece_tolerance,
    # diagram_filename, etc.) stay on .get() with defaults; required keys are
    # checked once here so a malformed config fails fast at the boundary.
    _REQUIRED_CONFIG_KEYS = [
        ("data",),
        ("data", "feature_path"),
        ("data", "train_window"),
        ("data", "holdout_window"),
        ("data", "entry_path"),
        ("data", "target_column"),
        ("data", "feature_columns"),
        ("cv",),
        ("cv", "n_splits"),
        ("evaluation",),
        ("evaluation", "ece_bins"),
        ("artifacts",),
    ]
    for key_path in _REQUIRED_CONFIG_KEYS:
        node = config
        for k in key_path:
            if not isinstance(node, dict) or k not in node:
                dotted = ".".join(key_path)
                raise KeyError(
                    f"run_train: required config key '{dotted}' is missing or "
                    f"not a mapping in {config_path}. Check the YAML against "
                    f"config/phase7_model_a.yaml (D-14 config schema)."
                )
            node = node[k]

    seed = config.get("seed", 42)
    train_window = config["data"]["train_window"]
    holdout_window = config["data"]["holdout_window"]
    n_splits = config["cv"]["n_splits"]
    logger.info(
        f"run_train: config loaded seed={seed} "
        f"train_window={train_window} holdout_window={holdout_window} "
        f"n_splits={n_splits}"
    )

    # ----- Step 2: load_features (Codex HIGH #4: forward expected_counts) -----
    data = load_features(
        feature_path=config["data"]["feature_path"],
        train_window=tuple(train_window),
        holdout_window=tuple(holdout_window),
        entry_path=config["data"]["entry_path"],
        expected_counts=expected_counts,
    )
    train_df: pd.DataFrame = data["train"]
    holdout_df: pd.DataFrame = data["holdout"]
    logger.info(
        f"run_train: features loaded train_rows={len(train_df)} "
        f"holdout_rows={len(holdout_df)}"
    )

    # ----- Step 3: resolve feature_columns (Codex HIGH #5 fix) -----
    # config["data"]["feature_columns"] is the static allowlist (must equal
    # src.pipeline.feature_generator.FEATURE_COLUMNS). drop_columns are the
    # identifiers / targets / post-race status columns that are present in
    # FEATURE_COLUMNS for schema completeness but must NOT enter the LightGBM
    # feature matrix (race_id leaks as a near-unique key; race_date leaks the
    # temporal position; horse_number is not a model feature).
    raw_feature_columns: List[str] = list(config["data"]["feature_columns"])
    drop_columns: List[str] = list(config["data"].get("drop_columns", []))
    feature_columns = [c for c in raw_feature_columns if c not in drop_columns]
    missing_in_df = [c for c in feature_columns if c not in train_df.columns]
    if missing_in_df:
        raise KeyError(
            f"run_train: feature_columns missing from train_df: {missing_in_df}. "
            "Check config.data.feature_columns / drop_columns vs the feature "
            "parquet schema."
        )
    logger.info(
        f"run_train: feature_columns resolved count={len(feature_columns)} "
        f"(raw={len(raw_feature_columns)} dropped={len(drop_columns)})"
    )

    # ----- Step 4: collect OOF predictions (Codex HIGH #2 + #5) -----
    splitter = GroupTimeSeriesSplit(n_splits=n_splits)
    oof_df = collect_oof_predictions(
        train_df, splitter, config, feature_columns=feature_columns
    )
    # Codex HIGH #2: OOF rows = validation chunks ONLY (warm-up chunk 0
    # excluded by the n_splits+1 date-block scheme). len(oof_df) < len(train_df)
    # is the leak-free contract, NOT a bug.
    logger.info(
        f"run_train: OOF collected oof_rows={len(oof_df)} "
        f"< train_rows={len(train_df)} (Codex HIGH #2: warm-up chunk 0 excluded)"
    )

    # ----- Step 5: fit calibrator on OOF (Pitfall #5 leak-free) -----
    iso = fit_calibrator(
        oof_df["p_top3_raw"].values,
        oof_df["target_top3"].values,
    )
    logger.info(f"run_train: calibrator fit on {len(oof_df)} OOF rows")

    # ----- Step 6: train final model (Codex HIGH #6 two-stage) -----
    final_clf = train_final_model(
        train_df, config, feature_columns=feature_columns
    )
    best_iter_val = getattr(final_clf, "_best_iteration_val", None)
    logger.info(
        f"run_train: final model trained on {len(train_df)} rows "
        f"(Codex HIGH #6: two-stage full retrain, "
        f"best_iteration_val={best_iter_val})"
    )

    # ----- Step 7: holdout predictions (raw + calibrated) -----
    holdout_pred_raw = final_clf.predict_proba(
        holdout_df[feature_columns]
    )[:, 1]
    holdout_pred_calibrated = apply_calibrator(iso, holdout_pred_raw)
    logger.info(
        f"run_train: holdout predicted holdout_rows={len(holdout_df)} "
        f"raw_mean={float(holdout_pred_raw.mean()):.4f} "
        f"cal_mean={float(holdout_pred_calibrated.mean()):.4f}"
    )

    # ----- Step 8: evaluate (D-06 main metric AUC; D-11 ECE) -----
    target_col = config["data"]["target_column"]
    metrics = evaluate(
        holdout_df[target_col].values,
        holdout_pred_raw,
        holdout_pred_calibrated,
        n_bins=config["evaluation"]["ece_bins"],
    )
    logger.info(
        "run_train: evaluation auc_calibrated={} "
        "ece_calibrated={:.4f} n_samples={}".format(
            (
                f"{metrics['auc_calibrated']:.4f}"
                if metrics['auc_calibrated'] is not None
                else "n/a (single-class)"
            ),
            metrics['ece_calibrated'],
            metrics['n_samples'],
        )
    )
    ece_tolerance = float(config["evaluation"].get("ece_tolerance", 0.02))
    if metrics["ece_calibrated"] >= ece_tolerance:
        logger.warning(
            f"run_train: ece_calibrated={metrics['ece_calibrated']:.4f} "
            f">= D-11 tolerance {ece_tolerance} — calibration goal unmet "
            "(inspect calibrator fit / Pitfall #5 leak)"
        )

    # ----- Step 9: popularity baseline (D-08 reference) -----
    entry_df = pd.read_parquet(config["data"]["entry_path"])
    baseline = compute_popularity_baseline(holdout_df, entry_df)
    metrics["baseline_auc"] = float(baseline["baseline_auc"])
    metrics["baseline_n_rows"] = int(baseline["n_rows"])
    logger.info(
        f"run_train: popularity baseline_auc={metrics['baseline_auc']:.4f} "
        f"n_rows={metrics['baseline_n_rows']} (D-08 reference only)"
    )

    # ----- Step 9b: record oof_rows (Cycle-2 HIGH #3 producer/consumer contract) -----
    # 07-08 phase-gate verify asserts `oof_rows in m` and `m[oof_rows] < 322510`.
    # Producer/consumer contract: key="oof_rows", type=int,
    # value=len(oof_df) where oof_df = collect_oof_predictions return value
    # (validation chunks only, warm-up excluded — Codex HIGH #2).
    metrics["oof_rows"] = int(len(oof_df))
    logger.info(
        f"run_train: metrics['oof_rows']={metrics['oof_rows']} "
        "(Cycle-2 HIGH #3 producer/consumer contract with 07-08)"
    )

    # ----- Step 10: persist D-15 artifacts -----
    art = config["artifacts"]
    model_dir = Path(art["model_dir"])
    oof_dir = Path(art["oof_dir"])
    report_dir = Path(art["report_dir"])
    for d in (model_dir, oof_dir, report_dir):
        d.mkdir(parents=True, exist_ok=True)

    # (1) LightGBM model .txt
    model_path = model_dir / art["model_filename"]
    final_clf.booster_.save_model(str(model_path))
    logger.info(f"run_train: saved model -> {model_path}")

    # (2) Calibrator .joblib
    calibrator_path = model_dir / art["calibrator_filename"]
    save_calibrator(iso, calibrator_path)

    # (3) OOF parquet (D-12: p_top3_raw AND p_top3_calibrated coexist)
    oof_df = oof_df.copy()
    oof_df["p_top3_calibrated"] = apply_calibrator(
        iso, oof_df["p_top3_raw"].values
    )
    oof_path = oof_dir / art["oof_filename"]
    oof_df.to_parquet(oof_path, engine="pyarrow", index=False)
    logger.info(f"run_train: saved OOF parquet -> {oof_path} rows={len(oof_df)}")

    # (4) Holdout parquet (same schema, fold="holdout")
    holdout_out = pd.DataFrame(
        {
            "race_id": holdout_df["race_id"].values,
            "horse_race_id": holdout_df["horse_race_id"].values,
            "p_top3_raw": holdout_pred_raw,
            "p_top3_calibrated": holdout_pred_calibrated,
            "target_top3": holdout_df[target_col].values,
            "fold": "holdout",
        }
    )
    holdout_path = oof_dir / art["holdout_filename"]
    holdout_out.to_parquet(holdout_path, engine="pyarrow", index=False)
    logger.info(
        f"run_train: saved holdout parquet -> {holdout_path} "
        f"rows={len(holdout_out)}"
    )

    # (5) Reliability diagram PNG (D-11)
    diagram_path = report_dir / art.get(
        "diagram_filename", "reliability_diagram.png"
    )
    _ = reliability_diagram(
        holdout_df[target_col].values,
        holdout_pred_calibrated,
        n_bins=config["evaluation"]["ece_bins"],
        save_path=diagram_path,
    )
    logger.info(f"run_train: saved reliability diagram -> {diagram_path}")

    # (6) metrics.json (includes oof_rows — Cycle-2 HIGH #3) + evaluation_report.md
    #
    # CR-01: ensure the file is STRICT JSON (RFC 8259). ``evaluate`` returns
    # ``None`` (not ``nan``) for single-class AUC, but other floats may still
    # be ``nan`` from degenerate inputs. ``allow_nan=False`` makes
    # ``json.dump`` raise ``ValueError`` on any ``NaN``/``Infinity`` so a bug
    # can never silently produce a non-standard literal (which breaks jq /
    # Node ``JSON.parse`` / pyarrow ``read_json`` / Phase 8/9 consumers). We
    # first normalise any residual nan/inf to ``None`` (-> JSON ``null``) so
    # the file is always parseable while still flagging the metric as missing.
    metrics_path = report_dir / art.get("metrics_filename", "metrics.json")
    metrics_for_json = {
        k: (
            None
            if (isinstance(v, float) and (math.isnan(v) or math.isinf(v)))
            else v
        )
        for k, v in metrics.items()
    }
    with metrics_path.open("w", encoding="utf-8") as f:
        json.dump(
            metrics_for_json, f, indent=2, ensure_ascii=False,
            allow_nan=False,
        )
    logger.info(f"run_train: saved metrics.json -> {metrics_path}")

    report_path = report_dir / art.get(
        "report_filename", "evaluation_report.md"
    )
    _write_evaluation_report(
        report_path,
        metrics=metrics,
        oof_rows=int(len(oof_df)),
        train_rows=int(len(train_df)),
        holdout_rows=int(len(holdout_df)),
        seed=seed,
        config_path=config_path,
    )
    logger.info(f"run_train: saved evaluation report -> {report_path}")

    logger.info("run_train: complete")
    return {
        "model": model_path,
        "calibrator": calibrator_path,
        "oof": oof_path,
        "holdout": holdout_path,
        "report": report_path,
        "metrics": metrics_path,
        "diagram": diagram_path,
        "config": config_path,
    }


def _write_evaluation_report(
    path: Path,
    *,
    metrics: Dict[str, Any],
    oof_rows: int,
    train_rows: int,
    holdout_rows: int,
    seed: int,
    config_path: Path,
) -> None:
    """Render the markdown evaluation report (D-08 framing + holdout-retune
    prohibition note — Cycle-2 LOW fix)."""
    lines: List[str] = []
    lines.append("# Phase 7 Model A — Evaluation Report\n")
    lines.append(f"Config: `{config_path}` (seed={seed})\n")
    lines.append(
        f"Train window rows: **{train_rows}** / Holdout rows: **{holdout_rows}** "
        f"/ OOF rows: **{oof_rows}** (validation chunks only, warm-up excluded — "
        "Codex HIGH #2)\n"
    )

    lines.append("## Metrics (holdout)\n")
    lines.append("| Metric | Raw | Calibrated |")
    lines.append("|---|---|---|")
    lines.append(
        f"| AUC (D-06 main) | {metrics.get('auc_raw', float('nan')):.4f} "
        f"| {metrics.get('auc_calibrated', float('nan')):.4f} |"
    )
    lines.append(
        f"| Brier | {metrics.get('brier_raw', float('nan')):.4f} "
        f"| {metrics.get('brier_calibrated', float('nan')):.4f} |"
    )
    lines.append(
        f"| Logloss | {metrics.get('logloss_raw', float('nan')):.4f} "
        f"| {metrics.get('logloss_calibrated', float('nan')):.4f} |"
    )
    lines.append(
        f"| ECE (D-11 < 0.02) | {metrics.get('ece_raw', float('nan')):.4f} "
        f"| {metrics.get('ece_calibrated', float('nan')):.4f} |"
    )
    lines.append(f"| n_samples | {metrics.get('n_samples', 0)} | |")
    lines.append(
        f"| Popularity baseline (D-08 ref) | "
        f"{metrics.get('baseline_auc', float('nan')):.4f} "
        f"(n={metrics.get('baseline_n_rows', 0)}) | |"
    )
    lines.append(f"| oof_rows (Cycle-2 HIGH #3) | {metrics.get('oof_rows', 0)} | |")
    lines.append("")

    lines.append("## Notes\n")
    lines.append(
        "- **D-08 純粋予測×EV 構図**: 本モデルは feature からオッズ/popularity "
        "を除外した純粋馬特性モデル (03-CONTEXT D-15). 人気 (単勝オッズ順位) "
        "ベースラインは市場集合知の参照値であり、純粋モデルがこれを AUC で超える"
        "のは競馬 ML 通説上非常に困難 (参考情報・D-07 で必須成功条件ではない). "
        "真の EV 優位性は Phase 9 ROI で検証."
    )
    lines.append(
        "- **Holdout retune prohibition (Cycle-2 LOW fix)**: holdout 予測は "
        "評価のみに使用し、calibrator / model の再学習に絶対に使用しないこと. "
        "Pitfall #5 (holdout recalibration leak) は calibrator.apply_calibrator "
        "のシグネチャ (labels 受け取らず) で構造防止済み."
    )
    lines.append(
        "- **Reproducibility (D-14)**: 同一 config で ``python -m src.ml.run_train`` "
        "を再実行すると同一の artifact set が再現される (固定 seed)."
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover
    run_train()
