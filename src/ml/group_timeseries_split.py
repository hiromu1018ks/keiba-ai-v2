"""Group-aware time-series cross-validator for Phase 7 Model A (MODA-02).

Provides ``GroupTimeSeriesSplit`` — a bespoke ``sklearn``-compatible cross
validator that splits rows by ``race_id`` group AND respects ``race_date``
chronology. The standard ``sklearn.model_selection.TimeSeriesSplit`` splits
row-wise, so two horses from the SAME race can land in different folds. That
breaks Phase 8 Harville computation (in-race p_top3 integrity) and creates
within-race leakage. This class solves the problem structurally (D-03).

Why bespoke instead of mlxtend ``GroupTimeSeriesSplit``: CLAUDE.md "Use
Instead: 必要なものだけ" — avoid the external dependency and produce an asset
that Phase 8 (Harville EV) and Phase 9 (walk-forward backtest) can reuse.

============================================================================
CV CONTRACT (Codex Suggestions + Codex HIGH #1 fix)
============================================================================
n_splits + 1 date-block chunks:
    * chunk 0            = warm-up TRAIN (always included in EVERY fold's
                           training set; non-empty because base >= 1 dates)
    * chunks 1..n_splits = one validation chunk per fold

For fold i in 0..n_splits-1:
    train = unique_dates[: val_start]    # date-block chunks 0..i (cumulative,
                                         #   expanding window; warm-up always
                                         #   included)
    val   = unique_dates[val_start:val_end]   # date-block chunk i+1

OOF target = chunks 1..n_splits ONLY (warm-up chunk 0 is excluded from OOF —
it is never a validation chunk). This guarantees fold 0's train = chunk 0
(non-empty), fixing the legacy structural bug where fold 0 train = chunks[:0]
= empty (Codex HIGH #1).

============================================================================
Cycle-3 HIGH fix — date-block-aware chunking
============================================================================
Chunks are built from ORDERED UNIQUE ``race_date`` blocks, NOT race counts.
All race_ids that share a race_date form an ATOMIC block and are placed inside
a single chunk. A race_date can therefore NEVER straddle a train/val boundary.

Under this construction ``max(train_dates) < min(val_dates)`` is a GENUINE
INVARIANT — it holds by construction, not by luck. The strict per-fold assertion
(see ``split``) therefore never raises on JRA's real data, where every
race_date carries multiple races (orchestrator cross-check on the production
corpus: 23,288 training races / 1,236 unique dates = mean 30.75 races/date,
minimum 10, maximum 36, ZERO single-race dates). The legacy race-count-based
chunking placed at least one of the 5 inner boundaries inside a date for any
6-chunk split of that data, halting the production 5-fold run via AssertionError.

============================================================================
Cycle-2 HIGH #1 fix — temporal-order assertion is NOT dead code
============================================================================
``split(X, y, groups, dates=None)`` takes ``dates`` as an EXPLICIT argument.
When dates are provided (trainer passes ``dates=df["race_date"]`` in 07-04),
the per-fold ``assert max(dates[train_idx]) < min(dates[val_idx])`` ALWAYS
fires, regardless of whether X happens to carry a ``race_date`` column. The
legacy gate ('X is DataFrame with race_date column') never fired in practice
because the trainer passes ``X=df[feature_columns]`` which excludes race_date.

Edge handling (Cycle-5 MEDIUM):
    * dates provided                                    -> assertion runs
    * dates=None + X has race_date column               -> resolve & assert
    * dates=None + X lacks race_date column             -> ValueError (NOT a
                                                          silent skip; the old
                                                          behavior fell through
                                                          to pd.unique(None) and
                                                          raised a confusing
                                                          TypeError)

Defensive validation (Cycle-5 LOW): after building the race_id -> race_date
map, we assert each race_id maps to exactly one race_date. JRA race_ids encode
the date so this is normally satisfied, but data corruption (e.g. a duplicated
race_id on two dates) would otherwise silently produce wrong folds.
============================================================================
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger
from sklearn.model_selection import BaseCrossValidator


class GroupTimeSeriesSplit(BaseCrossValidator):
    """Race-aware time-series cross-validator (MODA-02 / D-03).

    Splits rows such that:
      1. All rows sharing a ``race_id`` (groups) land in the SAME partition
         (no within-race leakage; Phase 8 Harville integrity preserved).
      2. Fold boundaries respect ``race_date`` chronology
         (``max(train_dates) < min(val_dates)`` per fold).
      3. fold count = ``n_splits`` (default 5 per D-04).
      4. n_splits+1 date-block chunks (chunk 0 = warm-up train, always
         included) so fold 0's train is non-empty (Codex HIGH #1).

    The caller MUST supply rows pre-sorted by ``race_date`` ascending
    (``load_features`` enforces this at the read boundary; Cycle-2 HIGH #1).
    This class cuts fold boundaries on the ORDERED UNIQUE ``race_date`` array,
    so chronological order of ``dates`` is the contract.

    Usage (Cycle-2 HIGH #1 — pass ``dates`` explicitly so the temporal-order
    assertion always fires regardless of X columns)::

        splitter = GroupTimeSeriesSplit(n_splits=5)
        for train_idx, val_idx in splitter.split(
            X, y, groups=df["race_id"], dates=df["race_date"]
        ):
            ...

    Legacy compatibility: if ``dates`` is omitted but ``X`` is a DataFrame
    carrying a ``race_date`` column, dates are resolved from X. If neither is
    available, ``ValueError`` is raised (Cycle-5 MEDIUM).
    """

    def __init__(self, n_splits: int = 5) -> None:
        self.n_splits = n_splits

    def get_n_splits(
        self,
        X: Any = None,  # noqa: N803 -- sklearn BaseCrossValidator signature
        y: Any = None,
        groups: Any = None,
    ) -> int:
        """Return the configured number of folds (sklearn signature)."""
        return self.n_splits

    def split(
        self,
        X: Any,  # noqa: N803 -- sklearn BaseCrossValidator signature
        y: Any = None,
        groups: Any = None,
        dates: Any = None,
    ) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        """Generate (train_idx, val_idx) index pairs for each fold.

        Args:
            X: feature matrix (DataFrame or array). Used for row count and,
                if ``dates`` is None, as a fallback source of race_date.
            y: ignored (sklearn signature compatibility).
            groups: 1-d array-like of ``race_id`` per row. REQUIRED.
            dates: 1-d array-like of ``race_date`` per row, ascending. When
                provided, the per-fold temporal-order assertion ALWAYS runs
                (Cycle-2 HIGH #1). When None, falls back to X["race_date"]
                if available, else raises ValueError (Cycle-5 MEDIUM).

        Yields:
            (train_idx, val_idx) as int numpy arrays of row positions.

        Raises:
            ValueError: groups is None; dates unavailable (neither passed nor
                in X); n_dates < n_splits + 1 (insufficient date-blocks for
                the n_splits+1 chunk scheme).
            AssertionError: a race_id maps to more than one race_date
                (Cycle-5 LOW); or per-fold ``max(train_dates) >=
                min(val_dates)`` (Cycle-2 HIGH #1 / Cycle-3 HIGH).
        """
        if groups is None:
            raise ValueError(
                "groups (race_id) is required by GroupTimeSeriesSplit"
            )

        # --- Cycle-2 HIGH #1 / Cycle-5 MEDIUM: resolve dates ---
        if dates is None:
            if isinstance(X, pd.DataFrame) and "race_date" in X.columns:
                dates = X["race_date"]
                logger.debug(
                    "dates resolved from X['race_date'] (legacy compat path)"
                )
            else:
                # Cycle-5 MEDIUM: explicit error, NOT silent skip
                raise ValueError(
                    "dates must be provided (or X must contain a race_date "
                    "column) — temporal-order assertion cannot run without "
                    "dates (Cycle-5 MEDIUM: dates=None + X-lacks-race_date "
                    "is an explicit error, not a silent skip)"
                )

        n_rows = len(groups)
        groups_arr = np.asarray(groups)
        dates_arr = (
            dates.values if isinstance(dates, pd.Series) else np.asarray(dates)
        )
        assert len(groups_arr) == n_rows == len(dates_arr), (
            f"length mismatch: groups={len(groups_arr)} dates={len(dates_arr)} "
            f"rows={n_rows}"
        )

        # --- Cycle-5 LOW: race_id -> exactly one race_date (defensive) ---
        # JRA race_ids encode the date so normally each race_id maps to one
        # date, but corrupted data (race_id duplicated on two dates) would
        # silently produce wrong folds. Detect loudly.
        race_id_to_dates = pd.DataFrame(
            {"race_id": groups_arr, "race_date": dates_arr}
        ).groupby("race_id", observed=True)["race_date"].nunique()
        max_dates_per_race = int(race_id_to_dates.max())
        assert max_dates_per_race == 1, (
            f"race_id must map to exactly one race_date, but found max "
            f"{max_dates_per_race} dates for a single race_id "
            "(Cycle-5 LOW: defensive validation against data corruption)"
        )

        # --- Cycle-3 HIGH: ordered unique race_date blocks ---
        # pd.unique preserves order of appearance. Caller is responsible for
        # pre-sorting by race_date ascending (load_features enforces it).
        unique_dates = pd.unique(dates_arr)
        n_dates = len(unique_dates)

        if n_dates < self.n_splits + 1:
            raise ValueError(
                f"Need at least n_splits+1={self.n_splits + 1} unique "
                f"race_dates for the date-block chunk scheme, got "
                f"{n_dates}. Reduce n_splits or widen the train window."
            )

        # --- Codex HIGH #1: n_splits+1 date-block chunk sizes ---
        date_block_sizes = self._compute_date_block_sizes(n_dates)
        date_boundaries = np.cumsum(date_block_sizes)
        # date_boundaries[i] = end index (exclusive) of date-block chunk i on
        # the ordered unique_dates array. chunk 0 spans [0, date_boundaries[0]),
        # chunk i spans [date_boundaries[i-1], date_boundaries[i]).

        # Precompute date -> row indices for O(chunk_size) mask building.
        # Each row belongs to exactly one date; build a dict date -> list(rows).
        date_to_rows: dict[Any, list[int]] = {}
        for row_idx in range(n_rows):
            d = dates_arr[row_idx]
            # numpy datetime64 hashing: use a python-friendly key
            key = (
                pd.Timestamp(d)
                if not isinstance(d, pd.Timestamp)
                else d
            )
            date_to_rows.setdefault(key, []).append(row_idx)

        logger.info(
            f"GroupTimeSeriesSplit: n_splits={self.n_splits} "
            f"n_dates={n_dates} date_block_sizes={date_block_sizes.tolist()} "
            f"n_rows={n_rows}"
        )

        # --- Yield one (train_idx, val_idx) per fold ---
        for i in range(self.n_splits):
            # date-block chunk i+1 is the validation chunk for fold i.
            # date-block chunks 0..i (cumulative, includes warm-up) are train.
            val_start = date_boundaries[i]
            val_end = date_boundaries[i + 1]
            val_dates_block = unique_dates[val_start:val_end]
            train_dates_block = unique_dates[:val_start]

            train_row_idxs: list[int] = []
            val_row_idxs: list[int] = []
            for d in train_dates_block:
                key = (
                    pd.Timestamp(d)
                    if not isinstance(d, pd.Timestamp)
                    else d
                )
                train_row_idxs.extend(date_to_rows[key])
            for d in val_dates_block:
                key = (
                    pd.Timestamp(d)
                    if not isinstance(d, pd.Timestamp)
                    else d
                )
                val_row_idxs.extend(date_to_rows[key])

            train_idx = np.array(sorted(train_row_idxs), dtype=np.int64)
            val_idx = np.array(sorted(val_row_idxs), dtype=np.int64)

            # --- Runtime temporal-order assertion ---
            # Cycle-2 HIGH #1: ALWAYS fires when dates are available (which is
            # always — we either received them or resolved from X).
            # Cycle-3 HIGH: holds by construction because chunks are date-block
            # units — train_dates and val_dates are disjoint complete date
            # blocks, and val chunk i+1 comes strictly after chunks 0..i.
            train_dates_values = dates_arr[train_idx]
            val_dates_values = dates_arr[val_idx]
            max_train_date = pd.Timestamp(train_dates_values.max())
            min_val_date = pd.Timestamp(val_dates_values.min())
            assert max_train_date < min_val_date, (
                f"fold {i}: temporal-order violation "
                f"max(train_date)={max_train_date} >= "
                f"min(val_date)={min_val_date} (Cycle-3 HIGH should make this "
                "a genuine invariant — investigate date-block chunking)"
            )

            logger.debug(
                f"fold {i}: train_rows={len(train_idx)} "
                f"val_rows={len(val_idx)} "
                f"train_date_blocks={len(train_dates_block)} "
                f"val_date_blocks={len(val_dates_block)} "
                f"warmup_included={val_start > 0} "
                f"max_train_date={max_train_date.date()} "
                f"min_val_date={min_val_date.date()}"
            )

            yield train_idx, val_idx

    def _compute_date_block_sizes(self, n_dates: int) -> np.ndarray:
        """Return the n_splits+1 date-block chunk sizes (Codex HIGH #1 +
        Cycle-3 HIGH).

        Each chunk gets at least ``base = n_dates // (n_splits + 1)`` dates
        (>= 1 because ``n_dates >= n_splits + 1`` is enforced upstream), and
        the first ``rem`` chunks get one extra date to distribute the
        remainder. This guarantees chunk 0 (warm-up train) is non-trivial.

        Args:
            n_dates: number of ordered unique race_dates.

        Returns:
            int numpy array of length n_splits + 1, summing to n_dates.
        """
        n_chunks = self.n_splits + 1
        base = n_dates // n_chunks
        rem = n_dates % n_chunks
        # base >= 1 is guaranteed because split() raises ValueError when
        # n_dates < n_splits + 1.
        sizes = np.array(
            [base + (1 if i < rem else 0) for i in range(n_chunks)],
            dtype=np.int64,
        )
        assert sizes.sum() == n_dates
        return sizes


def split_train_validation(
    train_df: pd.DataFrame,
    val_ratio: float = 0.2,
    sort_column: str = "race_date",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Carve an early-stopping validation set out of a fold's training frame.

    Within a single CV fold's training partition, take the LATEST
    ``val_ratio`` fraction of races (by ``sort_column``) as the early-stopping
    validation set. The remainder is the inner training set passed to
    LightGBM. This is the D-04 "discretion" region: the fold-level CV split
    is already time-safe (GroupTimeSeriesSplit guarantees max(train_dates) <
    min(val_dates)), and this inner carve keeps the inner train/val pair
    time-safe too.

    Args:
        train_df: a fold's training DataFrame; must contain ``race_id`` and
            ``sort_column`` columns.
        val_ratio: fraction of races (NOT rows) in the tail to use as inner
            validation. Must be in (0, 1).
        sort_column: chronological column to order races by (default race_date).

    Returns:
        (inner_train_df, inner_val_df) — both DataFrames, row-wise disjoint,
        together covering all rows of ``train_df``.

    Raises:
        ValueError: ``val_ratio`` out of (0, 1); required columns missing.
    """
    if not 0.0 < val_ratio < 1.0:
        raise ValueError(f"val_ratio must be in (0, 1), got {val_ratio}")
    for col in ("race_id", sort_column):
        if col not in train_df.columns:
            raise ValueError(
                f"train_df must contain '{col}' column for inner split"
            )

    races = (
        train_df[["race_id", sort_column]]
        .drop_duplicates(subset=["race_id"])
        .sort_values(sort_column)
        .reset_index(drop=True)
    )
    n_val = max(1, int(len(races) * val_ratio))
    val_race_ids = set(races.tail(n_val)["race_id"].tolist())

    is_val = train_df["race_id"].isin(val_race_ids)
    inner_train_df = train_df.loc[~is_val].copy()
    inner_val_df = train_df.loc[is_val].copy()

    # WR-01: guard empty inner_train. With n_val=max(1, ...) the val chunk is
    # always >=1 race, but inner_train can still be empty when total races <=
    # n_val (e.g. a single-race fold, or val_ratio=0.2 with <5 races). Feeding
    # an empty frame to LightGBM's clf.fit raises a confusing ValueError deep
    # inside the booster; fail loudly here with an actionable message instead.
    if len(inner_train_df) == 0:
        raise ValueError(
            f"split_train_validation: inner_train is empty "
            f"(total_races={len(races)}, n_val={n_val}, "
            f"val_ratio={val_ratio}). Need at least {n_val + 1} races in "
            f"train_df to leave a non-empty inner_train. Widening the train "
            f"window or reducing val_ratio / n_splits will fix this."
        )

    logger.debug(
        f"split_train_validation: total_races={len(races)} "
        f"inner_train_races={len(races) - n_val} inner_val_races={n_val} "
        f"inner_train_rows={len(inner_train_df)} "
        f"inner_val_rows={len(inner_val_df)}"
    )
    return inner_train_df, inner_val_df
