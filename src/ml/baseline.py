"""Popularity-based baseline AUC for the Model A top-3 probability model.

This module encodes RESEARCH.md "人気ベースライン AUC（D-08 参考）"
(lines 664-702, VERIFIED code) and Pitfall #6 (popularity NaN handling).

Contract (D-08 参考情報 / Pitfall #6):
    compute_popularity_baseline(features_df, entry_df) -> dict

Theoretical framing (D-08 — MUST be read alongside 03-CONTEXT D-15):
    The Model A feature layer deliberately EXCLUDES odds/popularity (post-race
    market signals) so that p_top3 is a *pure horse-characteristics* estimate
    (PROJECT.md / 03-CONTEXT D-15). This is the "純粋予測×EV" backbone of the
    system: the gap between the pure prediction and the market-implied
    probability is exactly what Phase 8 Harville EV measures.

    Consequence (D-08): a pure horse-characteristics model beating the market
    consensus (popularity = win-odds rank) on AUC is, by horse-racing ML
    consensus, *very hard (rare)*. The popularity baseline is therefore
    REFERENCE INFORMATION ONLY — it is NOT a Phase 7 success criterion
    (D-07 explicitly does not require out-performing it). The genuine EV edge
    is validated in Phase 9 ROI, where a model that is slightly worse on AUC
    but better calibrated in the odds-rich regions can still be profitable.

Pitfall #6 mitigation (T-07-06-01):
    ``entry.popularity`` is non-null for 533,009 of 534,953 rows in the unified
    corpus — 1,944 rows are NaN (取消/除外馬). Passing NaN into
    ``roc_auc_score`` raises ``ValueError``. This module drops NaN rows
    explicitly (``dropna(subset=['popularity', 'target_top3'])``) BEFORE the
    AUC call, so the baseline never crashes on scratched/withdrawn horses.
"""

from __future__ import annotations

import pandas as pd
from loguru import logger
from sklearn.metrics import roc_auc_score

__all__ = ["compute_popularity_baseline"]


def compute_popularity_baseline(
    features_df: pd.DataFrame, entry_df: pd.DataFrame
) -> dict:
    """人気（単勝オッズ順位）を score とした baseline AUC.

    D-07/D-08: 純粋馬特性モデルが市場集合知（人気）を AUC で超えるのは困難.
    baseline は参考情報（D-07 で必須成功条件ではない）.

    実装:
    - ``entry_df`` の ``popularity`` を ``race_id`` + ``horse_number`` で
      inner-join して ``features_df`` に付与.
    - ``score = -popularity``（人気順位が小さい = 強い. ``roc_auc_score`` は
      score 大 = 陽性で判定するためマイナス符号で反転）.
    - ``popularity`` / ``target_top3`` の NaN 行は ``dropna`` で除外
      （Pitfall #6 — 取消/除外馬 1,944件相当. ``roc_auc_score`` の
      ``ValueError`` を防止）.

    Args:
        features_df: feature-layer DataFrame with ``race_id``, ``horse_number``,
            ``target_top3`` (the 0/1 top-3 label). Must NOT itself contain
            ``popularity`` (that would be a D-15 leakage — caller's invariant).
        entry_df: entry-layer DataFrame with at minimum ``race_id``,
            ``horse_number``, ``popularity``.

    Returns:
        ``{"baseline_auc": float, "n_rows": int, "note": str}``. ``n_rows``
        is the post-``dropna`` row count actually scored.
    """
    merged = features_df.merge(
        entry_df[["race_id", "horse_number", "popularity"]],
        on=["race_id", "horse_number"],
        how="inner",
    )
    pre_drop = len(merged)
    # Pitfall #6 — drop NaN popularity (取消/除外馬) and NaN target before AUC.
    valid = merged.dropna(subset=["popularity", "target_top3"]).reset_index(
        drop=True
    )
    n_dropped = pre_drop - len(valid)
    if n_dropped > 0:
        logger.info(
            "compute_popularity_baseline: dropped {} rows with NaN "
            "popularity/target_top3 (Pitfall #6)".format(n_dropped)
        )

    if len(valid) == 0:
        logger.warning(
            "compute_popularity_baseline: no valid rows after dropna — "
            "returning baseline_auc=0.5 (uninformative)"
        )
        return {
            "baseline_auc": 0.5,
            "n_rows": 0,
            "note": (
                "人気(単勝オッズ順位)ベースライン。D-08: 純粋モデルがこれをAUCで"
                "超えるのは競馬ML通説上非常に困難（参考情報）。"
                "※有効行0件のため0.5（無情報）を返却"
            ),
        }

    # score = -popularity (lower popularity rank = stronger = higher score).
    baseline_auc = float(
        roc_auc_score(
            valid["target_top3"].astype(int),
            -valid["popularity"].astype(float),
        )
    )

    logger.info(
        "compute_popularity_baseline: baseline_auc={:.4f} n_rows={} "
        "(dropped {} NaN rows)".format(baseline_auc, len(valid), n_dropped)
    )

    return {
        "baseline_auc": baseline_auc,
        "n_rows": int(len(valid)),
        "note": (
            "人気(単勝オッズ順位)ベースライン。D-08: 純粋モデルがこれをAUCで"
            "超えるのは競馬ML通説上非常に困難（参考情報）"
        ),
    }
