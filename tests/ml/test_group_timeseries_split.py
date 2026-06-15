"""MODA-02 GroupTimeSeriesSplit tests.

D-03 race-aware CV: all rows from the same race_id MUST land in the same
fold (no within-race leakage), folds advance strictly forward in race_date,
and a race never straddles a train/test boundary.

Fixes verified by this suite:
- Codex HIGH #1 (fold-0 empty train): n_splits+1 chunk scheme; chunk 0 is the
  warm-up train and is ALWAYS included in every fold's training set.
- Cycle-2 HIGH #1 (temporal-order assertion dead code): ``dates`` is an explicit
  ``split(X, y, groups, dates=None)`` argument so the per-fold
  ``max(train_dates) < min(val_dates)`` assertion always fires when dates are
  provided (X column-presence independent).
- Cycle-3 HIGH (same-date fold boundary halts production 5-fold run):
  date-block-aware chunking. Chunks are built from ordered unique ``race_date``
  blocks, so all race_ids sharing a date are an atomic block inside a single
  chunk and never straddle a train/val boundary. ``max(train_dates) <
  min(val_dates)`` is a genuine invariant (holds by construction).
- Cycle-5 MEDIUM (dates=None fall-through): ``dates=None`` with X lacking a
  ``race_date`` column raises ValueError (explicit error, not silent skip).
- Cycle-5 LOW (race_id→multi-date corruption): defensive validation that each
  race_id maps to exactly one race_date.

PATTERNS.md analog: tests/pipeline/test_feature_generator.py::TestLoadMerge
(property-based sort-order verification). This CV is a sklearn
BaseCrossValidator-compatible bespoke implementation (No Analog Found entry in
07-PATTERNS.md).
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from src.ml.group_timeseries_split import GroupTimeSeriesSplit


def _make_fixture(
    n_dates: int,
    races_per_date: list[int],
    horses_per_race: int = 3,
    start_date: str = "2020-01-01",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, np.ndarray, pd.Series]:
    """Build a hermetic time-sorted feature fixture for CV tests.

    Returns (df, X_no_race_date, y, race_ids, date_series) where:
      * df has columns [race_id, race_date, horse_number, feat_a, feat_b]
        sorted ascending by [race_date, race_id, horse_number].
      * X_no_race_date is df WITHOUT race_date (mimics trainer passing
        df[feature_columns] with race_date in drop_columns).
      * y is a dummy target.
      * race_ids = df["race_id"].values (the groups arg).
      * date_series = df["race_date"] (the explicit dates arg).

    Args:
        n_dates: number of unique race_dates (must equal len(races_per_date)).
        races_per_date: number of races on each date. Deliberately non-uniform
            for the Cycle-3 regression (e.g. [4,5,4,5,4,5]) so that legacy
            race-count chunking would not accidentally align boundaries.
        horses_per_race: rows per race (3 horses default).
        start_date: first race_date; subsequent dates are +1 day each.
    """
    assert len(races_per_date) == n_dates, (
        "races_per_date length must equal n_dates"
    )
    base = pd.Timestamp(start_date)
    rows: list[dict] = []
    for d_idx in range(n_dates):
        rdate = base + pd.Timedelta(days=d_idx)
        for r_idx in range(races_per_date[d_idx]):
            # race_id encodes date + race-in-day so it is unique and sortable
            race_id = f"R{rdate.strftime('%Y%m%d')}{r_idx + 1:02d}"
            for h in range(1, horses_per_race + 1):
                rows.append({
                    "race_id": race_id,
                    "race_date": rdate,
                    "horse_number": h,
                    "feat_a": float(d_idx * 100 + r_idx * 10 + h),
                    "feat_b": float(h),
                })
    df = pd.DataFrame(rows).sort_values(
        ["race_date", "race_id", "horse_number"]
    ).reset_index(drop=True)
    assert df["race_date"].is_monotonic_increasing
    X_no_race_date = df[["feat_a", "feat_b"]]
    y = pd.Series(
        [1 if (i % 3 == 0) else 0 for i in range(len(df))], name="target_top3"
    )
    race_ids = df["race_id"].values
    date_series = df["race_date"]
    return df, X_no_race_date, y, race_ids, date_series


class TestGroupTimeSeriesSplit:
    """MODA-02: temporal CV with race_id grouping — prevents boundary split
    and temporal leakage.

    n_splits+1 date-block chunk scheme ensures fold 0 has non-empty training
    set and no race_date straddles a train/val boundary (Cycle-3 HIGH fix).
    """

    # ------------------------------------------------------------------ #
    # Test 1: sklearn BaseCrossValidator compatibility (get_n_splits)
    # ------------------------------------------------------------------ #
    def test_get_n_splits(self) -> None:
        """Test 1: MODA-02 sklearn compatibility — GroupTimeSeriesSplit
        (n_splits=N).get_n_splits(X, y, groups) returns N.

        D-04 fold count = 5. Works with X=None, y=None, groups=None (sklearn
        BaseCrossValidator signature).
        """
        splitter = GroupTimeSeriesSplit(n_splits=5)
        assert splitter.get_n_splits() == 5
        # sklearn calls get_n_splits(X, y, groups) — all-None must work
        assert splitter.get_n_splits(None, None, None) == 5
        # Different n_splits value sanity check
        assert GroupTimeSeriesSplit(n_splits=3).get_n_splits() == 3

    # ------------------------------------------------------------------ #
    # Test 2: same race_id lands in exactly one partition per fold
    # ------------------------------------------------------------------ #
    def test_same_race_same_fold(self) -> None:
        """Test 2: T-temporal-leak — for each fold, the set of race_ids in
        train and val are disjoint; no race_id appears in both partitions.

        D-03 race-aware CV: all rows of one race_id end up in one fold's
        val set, and none of those rows leak into that fold's train.
        """
        # 6 dates × 5 races × 3 horses (uniform is fine here — Cycle-3 fix is
        # verified separately in test_same_date_not_split_across_fold_boundary)
        df, X, y, race_ids, dates = _make_fixture(6, [5, 5, 5, 5, 5, 5])
        splitter = GroupTimeSeriesSplit(n_splits=5)
        for train_idx, val_idx in splitter.split(X, y, groups=race_ids, dates=dates):
            train_races = set(race_ids[train_idx])
            val_races = set(race_ids[val_idx])
            # D-03: train and val race_id sets must be disjoint
            assert train_races & val_races == set(), (
                "race_id leakage: train/val share race_ids "
                f"{train_races & val_races}"
            )

    # ------------------------------------------------------------------ #
    # Test 3: folds advance strictly forward in race_date
    # ------------------------------------------------------------------ #
    def test_temporal_order(self) -> None:
        """Test 3: MODA-02 — fold val sets advance strictly forward in
        race_date. fold i's train race_dates are all strictly before fold i's
        val race_dates (max(train_dates) < min(val_dates)).
        """
        df, X, y, race_ids, dates = _make_fixture(6, [5, 5, 5, 5, 5, 5])
        splitter = GroupTimeSeriesSplit(n_splits=5)
        prev_val_min_date = None
        for train_idx, val_idx in splitter.split(X, y, groups=race_ids, dates=dates):
            train_dates = dates.iloc[train_idx]
            val_dates = dates.iloc[val_idx]
            # Per-fold temporal order (Cycle-2 HIGH #1 invariant)
            assert train_dates.max() < val_dates.min(), (
                "temporal leakage: max(train_date) >= min(val_date) within fold"
            )
            # Fold-to-fold advance: each fold's val_min > previous fold's val_min
            if prev_val_min_date is not None:
                assert val_dates.min() > prev_val_min_date, (
                    "fold val sets are not strictly advancing in race_date"
                )
            prev_val_min_date = val_dates.min()

    # ------------------------------------------------------------------ #
    # Test 4: no race straddles the train/val boundary
    # ------------------------------------------------------------------ #
    def test_no_boundary_split(self) -> None:
        """Test 4: MODA-02 — no race straddles the train/test boundary.

        Every fold's max(train_date) belongs to a race whose ENTIRE row set
        is in train; same race is never split across the boundary.
        """
        df, X, y, race_ids, dates = _make_fixture(6, [5, 5, 5, 5, 5, 5])
        splitter = GroupTimeSeriesSplit(n_splits=5)
        for train_idx, val_idx in splitter.split(X, y, groups=race_ids, dates=dates):
            train_races = set(race_ids[train_idx])
            val_races = set(race_ids[val_idx])
            # For each race_id, ALL its rows must be on the same side
            for rid in train_races | val_races:
                in_train = rid in train_races
                in_val = rid in val_races
                assert not (in_train and in_val), (
                    f"race_id {rid} straddles boundary (in both train and val)"
                )

    # ------------------------------------------------------------------ #
    # Test 5: Codex HIGH #1 — fold 0 train is non-empty (n_splits+1 chunks)
    # ------------------------------------------------------------------ #
    def test_fold0_train_non_empty(self) -> None:
        """Test 5: Codex HIGH #1 regression guard — fold 0's train_idx is
        non-empty. Under the n_splits+1 chunk scheme, chunk 0 is the warm-up
        train and is ALWAYS included in every fold's training set.

        The legacy n_splits-chunk algorithm had fold 0 train = chunks[:0] =
        empty (structural bug). The new scheme guarantees fold 0 train = chunk
        0 (warm-up, contains >= 1 date-block).
        """
        df, X, y, race_ids, dates = _make_fixture(6, [5, 5, 5, 5, 5, 5])
        splitter = GroupTimeSeriesSplit(n_splits=5)
        folds = list(splitter.split(X, y, groups=race_ids, dates=dates))
        assert len(folds) == 5
        # Fold 0 explicitly
        train_idx_0, _ = folds[0]
        assert len(train_idx_0) > 0, (
            "fold 0 train is empty — n_splits+1 chunk scheme broken "
            "(Codex HIGH #1 regression)"
        )
        # ALL folds must have non-empty train (warm-up chunk always included)
        for i, (train_idx, _) in enumerate(folds):
            assert len(train_idx) > 0, (
                f"fold {i} train is empty — expanding window broken"
            )

    # ------------------------------------------------------------------ #
    # Test 6: Cycle-2 HIGH #1 — dates explicit arg fires assertion always
    # ------------------------------------------------------------------ #
    def test_dates_arg_assertion_always_fires(self) -> None:
        """Test 6: Cycle-2 HIGH #1 — the per-fold temporal-order assertion
        runs whenever dates is provided, EVEN IF X does not contain a
        race_date column. Proves the assertion is not dead code (the legacy
        gate on 'X is DataFrame with race_date column' never fired because
        the trainer passes X=df[feature_columns] which excludes race_date).

        Three sub-checks:
        (a) X without race_date + dates=sorted → assertion passes (no error).
        (b) dates reversed (fold 0 val BEFORE fold 0 train) → AssertionError.
        (c) Cycle-5 MEDIUM: dates=None + X without race_date → ValueError.
        """
        df, X, y, race_ids, dates = _make_fixture(6, [5, 5, 5, 5, 5, 5])
        splitter = GroupTimeSeriesSplit(n_splits=5)

        # (a) Normal order with dates explicit → assertion passes
        for _train_idx, _val_idx in splitter.split(
            X, y, groups=race_ids, dates=dates
        ):
            pass  # no AssertionError

        # (b) Reversed dates → fold 0 val dates < train dates → AssertionError
        reversed_dates = dates.iloc[::-1].reset_index(drop=True)
        with pytest.raises(AssertionError):
            list(splitter.split(X, y, groups=race_ids, dates=reversed_dates))

        # (c) Cycle-5 MEDIUM: dates=None + X without race_date → ValueError
        with pytest.raises(ValueError, match="dates must be provided"):
            list(splitter.split(X, y, groups=race_ids, dates=None))

    # ------------------------------------------------------------------ #
    # Test 7: Cycle-3 HIGH — same date NOT split across fold boundary
    # ------------------------------------------------------------------ #
    def test_same_date_not_split_across_fold_boundary(self) -> None:
        """Test 7: Cycle-3 HIGH fix regression — under a fixture where EVERY
        race_date has MULTIPLE races (JRA real-data universal case: mean 30.75
        races/date, zero single-race dates), the date-block-aware chunking
        must:

        (a) Never split a race_date across train and val for ANY fold
            (set(train_dates) & set(val_dates) == empty).
        (b) Never raise the strict ``max(train_dates) < min(val_dates)``
            assertion — it is a genuine invariant under date-block chunking,
            NOT a latent landmine.

        Cycle-5 LOW: races-per-date deliberately NON-UNIFORM [4,5,4,5,4,5]
        so that legacy race-count chunking would not accidentally produce
        boundary-aligned splits (Codex Cycle-4 suggestion #2). With uniform
        counts the old algorithm could coincidentally pass and the regression
        would be vacuous.
        """
        # 6 unique dates × non-uniform races [4,5,4,5,4,5] × 3 horses
        # Every date has >=4 races (multi-race universal case, no single-race day)
        df, X, y, race_ids, dates = _make_fixture(6, [4, 5, 4, 5, 4, 5])
        splitter = GroupTimeSeriesSplit(n_splits=5)

        # (b) Split call must not raise (Cycle-3 HIGH regression guard —
        # the production 5-fold run must NOT halt under multi-race-per-date data)
        folds = list(splitter.split(X, y, groups=race_ids, dates=dates))
        assert len(folds) == 5

        for i, (train_idx, val_idx) in enumerate(folds):
            train_dates_set = set(dates.iloc[train_idx])
            val_dates_set = set(dates.iloc[val_idx])
            # (a) No race_date straddles the boundary
            assert train_dates_set & val_dates_set == set(), (
                f"fold {i}: race_date straddles train/val boundary — "
                f"shared dates={train_dates_set & val_dates_set} "
                "(Cycle-3 HIGH regression)"
            )

    # ------------------------------------------------------------------ #
    # Test 8: Cycle-5 LOW — race_id maps to exactly one race_date
    # ------------------------------------------------------------------ #
    def test_race_id_maps_to_single_date(self) -> None:
        """Test 8: Cycle-5 LOW fix (Codex Cycle-4 suggestion #3) — defensive
        validation that each race_id maps to exactly one race_date.

        (a) Clean fixture (each race_id on one date) → split succeeds.
        (b) Corrupted fixture (one race_id duplicated onto two different
            dates) → splitter raises AssertionError or ValueError.
        """
        # (a) Clean fixture
        df, X, y, race_ids, dates = _make_fixture(6, [5, 5, 5, 5, 5, 5])
        splitter = GroupTimeSeriesSplit(n_splits=5)
        folds = list(splitter.split(X, y, groups=race_ids, dates=dates))
        assert len(folds) == 5

        # (b) Corrupt: copy rows of the first race_id but change their race_date
        # to the LAST date, producing a race_id that spans 2 dates.
        first_rid = df["race_id"].iloc[0]
        last_date = df["race_date"].iloc[-1]
        corrupted = df.copy()
        dup = df[df["race_id"] == first_rid].copy()
        dup["race_date"] = last_date
        corrupted = pd.concat([corrupted, dup], ignore_index=True)
        corrupted = corrupted.sort_values(
            ["race_date", "race_id", "horse_number"]
        ).reset_index(drop=True)
        X_c = corrupted[["feat_a", "feat_b"]]
        y_c = pd.Series([0] * len(corrupted))
        race_ids_c = corrupted["race_id"].values
        dates_c = corrupted["race_date"]
        with pytest.raises((AssertionError, ValueError)):
            list(splitter.split(X_c, y_c, groups=race_ids_c, dates=dates_c))
