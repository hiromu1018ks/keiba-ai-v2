"""MODA-02 GroupTimeSeriesSplit tests (Wave 0 skeleton).

RESEARCH.md Test Map lines 788-790. PATTERNS.md analog:
tests/pipeline/test_feature_generator.py::TestLoadMerge (property-based
sort-order verification). Also "No Analog Found" entry: this CV is a
sklearn BaseCrossValidator-compatible bespoke implementation.
"""

import pytest


class TestGroupTimeSeriesSplit:
    """Tests for src/ml/group_timeseries_split.GroupTimeSeriesSplit.

    D-03 race-aware CV: all rows from the same race_id MUST land in the same
    fold (no within-race leakage), folds advance strictly forward in
    race_date, and a race never straddles a train/test boundary.
    """

    def test_same_race_same_fold(
        self, sample_feature_df: "pytest.fixture"  # type: ignore[name-defined]
    ) -> None:
        """T-temporal-leak: all rows of one race_id end up in one fold's test set.

        Wave 1 expectation: for each split, the set of race_ids in train and
        test are disjoint; no race_id appears in both partitions of a fold.
        """
        pytest.skip("Wave 1 implements src/ml/group_timeseries_split first")

    def test_temporal_order(
        self, sample_feature_df: "pytest.fixture"  # type: ignore[name-defined]
    ) -> None:
        """MODA-02: fold test sets advance strictly forward in race_date.

        Wave 1 expectation: max(train_date) < min(test_date) for every fold,
        and the sequence of fold test_start_dates is monotonically increasing.
        """
        pytest.skip("Wave 1 implements src/ml/group_timeseries_split first")

    def test_no_boundary_split(
        self, sample_feature_df: "pytest.fixture"  # type: ignore[name-defined]
    ) -> None:
        """MODA-02: no race straddles the train/test boundary.

        Wave 1 expectation: every fold's max(train_date) belongs to a race
        whose ENTIRE row set is in train; same race is never split across
        the boundary.
        """
        pytest.skip("Wave 1 implements src/ml/group_timeseries_split first")

    def test_get_n_splits(
        self, sample_feature_df: "pytest.fixture"  # type: ignore[name-defined]
    ) -> None:
        """sklearn BaseCrossValidator compatibility: get_n_splits returns config.

        Wave 1 expectation: GroupTimeSeriesSplit(n_splits=N).get_n_splits(
        X, y, groups) returns N (no off-by-one; sklearn signature honored).
        """
        pytest.skip("Wave 1 implements src/ml/group_timeseries_split first")
