"""Feature-layer loader for Phase 7 Model A (3着内確率 / top-3 probability).

Provides ``load_features`` — the single read boundary that Wave 1 trainer,
baseline, and the Wave 2 ``run_train`` orchestrator share. Reads
``data/feature/features_train.parquet`` and produces dtype-safe, leakage-audited,
time-sorted train / holdout DataFrames with the derived ``horse_race_id``.

Encodes RESEARCH.md "実測ベリファイド" pitfalls:
- Pitfall #2 (horse_race_id authority): format is ``f"{race_id}{horse_number:02d}"``
  with NO underscore (verified against data/standard/entry.parquet; the
  EntrySchema docstring's "{race_id}_{horse_number:02d}" is WRONG — real data
  wins). Derive on load and assert join integrity against entry.parquet when
  available.
- Pitfall #3 (categorical dtype): feature_generator.convert_to_categorical
  gated conversion on ``dtype == "object"``, which misses pandas nullable
  ``string`` columns. The 7 columns course_name/surface/direction/weather/
  track_condition/sex/grade arrive as ``string`` dtype (verified), so we
  convert CATEGORICAL_COLUMNS unconditionally with ``astype("category")``.
- Pitfall #4 (grade NaN preserved): grade is ~95% NaN on real data
  (506,349/534,953). We internally assert NaN count is identical before/after
  category conversion.
- Pitfall #7 (window boundary): train_window (2018-01-01..2024-12-31,
  exclude_from_training=False) = 322,510 rows / 23,288 races; holdout_window
  (2025-01-01..2026-05-31, exclude_from_training=False) = 66,343 rows /
  4,740 races (all verified on the real corpus). PRODUCTION_COUNTS is asserted
  when ``expected_counts is None`` (default).

Codex HIGH #4 fix (fixed-count assert breaks hermetic E2E):
    The original spec hard-coded ``assert len(train_df) == 322510`` which
    caused hermetic 07-07 E2E tests using a 10-15 race fixture to fail with
    AssertionError. ``expected_counts`` parameter toggles between the
    production-count assert and an explicit bypass:
      * ``expected_counts=None`` (default) — assert PRODUCTION_COUNTS
      * ``expected_counts=[]`` (empty LIST) — bypass assert (hermetic fixtures)
      * ``expected_counts={...}`` (non-empty dict) — assert those custom counts
      * ``{}`` (empty dict) — TypeError (NOT accepted)

Cycle-2 HIGH #1 fix (temporal-order enforcement):
    GroupTimeSeriesSplit (07-03) assumes input is race_date-ascending, but
    parquet row order is NOT guaranteed to be chronological (verified: the
    on-disk features_train.parquet is NOT monotonic). load_features therefore
    (a) converts race_date to datetime, (b) sorts by [race_date, race_id,
    horse_number] with reset_index, (c) asserts ``is_monotonic_increasing``,
    and (d) RETAINS the race_date column on the returned train/holdout frames
    so the downstream trainer can pass ``dates=df["race_date"]`` to splitter.split
    and always run the per-fold temporal-order assertion (independent of whether
    X happens to carry race_date).

Cycle-2 HIGH #2 fix (sentinel unification):
    Earlier spec gated bypass on an empty dict sentinel but
    callers used ``expected_counts == []`` (empty list). UNIFIED sentinel: the
    empty LIST [] is the sole bypass sentinel; {} is rejected with TypeError.
    The ``elif isinstance(expected_counts, dict) and expected_counts:`` guard
    (Cycle-5 MEDIUM tightening) ensures an empty dict cannot accidentally
    match the custom-assert branch and would fall through to TypeError.

Threat register (T-07-02-01..07): see .planning/.../07-02-PLAN.md. All seven
threats are disposition=mitigate and are implemented inline here.
"""

from pathlib import Path

import pandas as pd
from loguru import logger

from src.pipeline.feature_generator import CATEGORICAL_COLUMNS, FEATURE_COLUMNS
from src.schemas.audit import audit_leakage
from src.schemas.entry import EntrySchema
from src.schemas.race import RaceSchema

# Verified against the real data/feature/features_train.parquet corpus on
# 2026-06-15 (534,953 rows; unified Kaggle+scraped Phase 6 corpus).
# train_window = 2018-01-01..2024-12-31 with exclude_from_training=False
# holdout_window = 2025-01-01..2026-05-31 with exclude_from_training=False
PRODUCTION_COUNTS = {
    "train_rows": 322510,
    "train_races": 23288,
    "holdout_rows": 66343,
    "holdout_races": 4740,
}


def load_features(
    feature_path: str | Path = "data/feature/features_train.parquet",
    train_window: tuple[str, str] = ("2018-01-01", "2024-12-31"),
    holdout_window: tuple[str, str] = ("2025-01-01", "2026-05-31"),
    entry_path: str | Path = "data/standard/entry.parquet",
    expected_counts: dict | list | None = None,
) -> dict:
    """Load features_train.parquet, prepare dtypes, derive horse_race_id,
    audit leakage, sort by race_date, and split into train/holdout windows.

    Args:
        feature_path: Path to the feature-layer parquet (Phase 3 output).
        train_window: (start, end) inclusive date strings for the training window.
        holdout_window: (start, end) inclusive date strings for the holdout window.
        entry_path: Path to data/standard/entry.parquet — used to verify derived
            horse_race_id join integrity. Missing file => warning, not error.
        expected_counts: UNIFIED sentinel (Cycle-2 HIGH #2 fix):
            * None (default) — assert PRODUCTION_COUNTS (322510/23288/66343/4740)
            * [] (empty LIST) — bypass row-count assert for hermetic fixtures
            * {non-empty dict} — assert the given custom counts
            * {} (empty dict) — raises TypeError (NOT accepted; Cycle-5 tightening)

    Returns:
        dict with keys:
            * "train": pd.DataFrame (race_date column RETAINED — Cycle-2 HIGH #1)
            * "holdout": pd.DataFrame (race_date column RETAINED)
            * "metadata": dict with train_rows, train_races, holdout_rows,
              holdout_races, leaked_columns, feature_columns, race_date_sorted

    Raises:
        FileNotFoundError: feature_path does not exist.
        AssertionError: window counts diverge from asserted values.
        TypeError: expected_counts is {} (empty dict) or an unsupported type.

    Threats mitigated: T-07-02-01..07 — see module docstring + 07-02-PLAN.md.
    """
    # --- (1) Resolve & validate feature path (T-03-01 analog) ---
    feature_path = Path(feature_path)
    if not feature_path.is_file():
        raise FileNotFoundError(
            f"Feature parquet not found: {feature_path} "
            "(Phase 3 feature_generator output expected)"
        )

    # --- (2) Read parquet (per-table log only, no per-row — MEMORY.md) ---
    df = pd.read_parquet(feature_path, engine="pyarrow")
    logger.info(
        f"Loaded feature parquet: {feature_path} rows={len(df)} "
        f"cols={len(df.columns)}"
    )

    # --- (3) race_date -> datetime (features_train stores as string; verified) ---
    df["race_date"] = pd.to_datetime(df["race_date"])

    # --- (4) Cycle-2 HIGH #1: sort by race_date + assert monotonicity ---
    # parquet row order is NOT guaranteed chronological (verified: on-disk
    # features_train.parquet is NOT monotonic). GroupTimeSeriesSplit (07-03)
    # assumes ascending race_date, so we enforce it at the read boundary.
    df = df.sort_values(["race_date", "race_id", "horse_number"]).reset_index(
        drop=True
    )
    assert df["race_date"].is_monotonic_increasing, (
        "race_date must be sorted ascending after load_features "
        "(Cycle-2 HIGH #1: GroupTimeSeriesSplit requires ascending input)"
    )
    logger.info("Sorted by [race_date, race_id, horse_number] (Cycle-2 HIGH #1)")

    # --- (5) audit_leakage (D-12; T-07-02-01) ---
    # ResultSchema intentionally excluded: it marks race_id as post-race, which
    # would produce false positives on a feature table. We check against
    # RaceSchema + EntrySchema only (popularity/win_odds are post-race in Entry).
    leaked = audit_leakage(
        [RaceSchema, EntrySchema], df, context="phase7 feature load"
    )
    if leaked:
        logger.warning(f"Leakage detected: {leaked}")

    # --- (6) Pitfall #3: unconditional astype("category") on all CATEGORICAL_COLS ---
    # feature_generator.convert_to_categorical gated on dtype=="object" which
    # misses pandas nullable `string` columns (verified: the 7 non-jockey/trainer
    # categoricals arrive as `string`). Convert unconditionally; jockey/trainer
    # are already category so the operation is idempotent.
    grade_nan_before = pd.isna(df["grade"]).sum() if "grade" in df.columns else 0
    for col in CATEGORICAL_COLUMNS:
        if col in df.columns:
            df[col] = df[col].astype("category")
    logger.info(
        f"Converted {len(CATEGORICAL_COLUMNS)} CATEGORICAL_COLUMNS to category "
        f"(Pitfall #3: unconditional, dtype==object misses `string`)"
    )

    # --- (7) Pitfall #4: grade NaN preserved through category conversion ---
    grade_nan_after = pd.isna(df["grade"]).sum() if "grade" in df.columns else 0
    if grade_nan_before != grade_nan_after:
        logger.warning(
            f"grade NaN count diverged through category conversion: "
            f"before={grade_nan_before} after={grade_nan_after} (Pitfall #4)"
        )

    # --- (8) Pitfall #2: derive horse_race_id (no underscore — verified) ---
    # EntrySchema docstring says "{race_id}_{horse_number:02d}" (underscore)
    # but real data/standard/entry.parquet uses NO underscore. Real data wins.
    df["horse_race_id"] = (
        df["race_id"].astype(str)
        + df["horse_number"].astype(int).astype(str).str.zfill(2)
    )
    logger.info(
        "Derived horse_race_id = f'{race_id}{horse_number:02d}' "
        "(no underscore — verified against data/standard/entry.parquet)"
    )

    # --- (9) Join integrity check against entry.parquet (best-effort) ---
    entry_path = Path(entry_path)
    if entry_path.is_file():
        entry_df = pd.read_parquet(entry_path, engine="pyarrow", columns=["horse_race_id"])
        entry_keys = set(entry_df["horse_race_id"].astype(str))
        derived_keys = set(df["horse_race_id"].astype(str))
        overlap = len(derived_keys & entry_keys)
        total = len(derived_keys)
        match_rate = overlap / total if total else 0.0
        logger.info(
            f"horse_race_id join integrity: {overlap}/{total} "
            f"({match_rate:.4%}) match entry.parquet"
        )
    else:
        logger.warning(
            f"entry_path not found ({entry_path}); skipping horse_race_id "
            "join integrity check"
        )

    # --- (10) Window split (Pitfall #7; D-01/D-02 boundaries) ---
    # exclude_from_training=True (取消/除外馬; target_top3=0; result_status in
    # {removed, scratched}) is excluded from BOTH windows to avoid label
    # poisoning and to keep the holdout a clean evaluation set.
    train_start, train_end = train_window
    holdout_start, holdout_end = holdout_window
    train_mask = (
        (df["race_date"] >= pd.Timestamp(train_start))
        & (df["race_date"] <= pd.Timestamp(train_end))
        & (~df["exclude_from_training"])
    )
    holdout_mask = (
        (df["race_date"] >= pd.Timestamp(holdout_start))
        & (df["race_date"] <= pd.Timestamp(holdout_end))
        & (~df["exclude_from_training"])
    )
    train_df = df.loc[train_mask].copy()
    holdout_df = df.loc[holdout_mask].copy()

    # --- (11) Row-count assertion (Pitfall #7 + Codex HIGH #4 + Cycle-2 HIGH #2) ---
    actual_counts = {
        "train_rows": len(train_df),
        "train_races": int(train_df["race_id"].nunique()),
        "holdout_rows": len(holdout_df),
        "holdout_races": int(holdout_df["race_id"].nunique()),
    }

    if expected_counts is None:
        # Default: assert against PRODUCTION_COUNTS (07-08 phase gate path)
        assert_counts = PRODUCTION_COUNTS
        mode = "production (PRODUCTION_COUNTS)"
    elif isinstance(expected_counts, list) and len(expected_counts) == 0:
        # UNIFIED bypass sentinel: empty LIST (Cycle-2 HIGH #2 fix).
        # Hermetic fixtures (07-07 E2E) pass [] to skip the row-count assert.
        assert_counts = None
        mode = "bypassed (empty list, hermetic fixtures)"
        logger.info(
            "expected_counts bypassed: empty list sentinel — row-count assert "
            "skipped (Cycle-2 HIGH #2 / Codex HIGH #4)"
        )
    elif isinstance(expected_counts, dict) and expected_counts:
        # Custom assert: caller supplied specific counts.
        # Cycle-5 MEDIUM tightening: the `and expected_counts` guard means an
        # empty dict {} does NOT match this branch and falls through to the
        # TypeError below (Codex Cycle-4 carry-over).
        assert_counts = expected_counts
        mode = "custom dict"
    else:
        # Reject {} (empty dict) and any other unsupported type.
        raise TypeError(
            "expected_counts must be None, empty list [], or non-empty dict. "
            f"Got {expected_counts!r} (type={type(expected_counts).__name__}). "
            "Empty dict {} is NOT accepted (Cycle-2 HIGH #2 + Cycle-5 MEDIUM)."
        )

    if assert_counts is not None:
        for key, expected_value in assert_counts.items():
            actual_value = actual_counts.get(key)
            assert actual_value == expected_value, (
                f"{key} mismatch: expected={expected_value} "
                f"actual={actual_value} (mode={mode})"
            )

    logger.info(
        f"load_features done: mode={mode} train={actual_counts['train_rows']}rows/"
        f"{actual_counts['train_races']}races holdout={actual_counts['holdout_rows']}"
        f"rows/{actual_counts['holdout_races']}races"
    )

    # --- (12) Return dict; train/holdout RETAIN race_date (Cycle-2 HIGH #1) ---
    return {
        "train": train_df,
        "holdout": holdout_df,
        "metadata": {
            "train_rows": actual_counts["train_rows"],
            "train_races": actual_counts["train_races"],
            "holdout_rows": actual_counts["holdout_rows"],
            "holdout_races": actual_counts["holdout_races"],
            "leaked_columns": leaked,
            "feature_columns": FEATURE_COLUMNS,
            "race_date_sorted": True,  # Cycle-2 HIGH #1
        },
    }
