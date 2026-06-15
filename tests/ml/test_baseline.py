"""MODA-03 baseline tests (Wave 0 skeleton).

RESEARCH.md Test Map line 791. PATTERNS.md analog:
tests/pipeline/test_feature_generator.py::TestJockeyTrainerStats
(groupby aggregation correctness against hand-built fixtures).
"""

import pytest


class TestBaseline:
    """Tests for src/ml/baseline.popularity_baseline_auc.

    Covers MODA-03 (popularity-based baseline AUC), Pitfall #6 (NaN
    popularity rows must be dropped, not silently coerced), and join
    integrity between the feature matrix and entry table.
    """

    def test_popularity_baseline_auc(
        self,
        sample_feature_df: "pytest.fixture",  # type: ignore[name-defined]
        sample_entry_df: "pytest.fixture",  # type: ignore[name-defined]
    ) -> None:
        """MODA-03: with popularity perfectly inversely correlated to target_top3,
        AUC is high (>= 0.9 on the hand-built fixture).

        Wave 1 expectation: after joining feature_df to entry_df on
        (race_id, horse_number), popularity_baseline_auc(df) returns a float
        in [0.5, 1.0]; on the deterministic fixture the value is >= 0.9.
        """
        pytest.skip("Wave 1 implements src/ml/baseline first")

    def test_popularity_nan_dropped(
        self,
        sample_feature_df: "pytest.fixture",  # type: ignore[name-defined]
        sample_entry_df: "pytest.fixture",  # type: ignore[name-defined]
    ) -> None:
        """Pitfall #6: NaN popularity rows are dropped, not coerced to 0.

        Wave 1 expectation: popularity_baseline_auc drops rows where
        popularity is NaN (no implicit 0-fill), and the returned AUC is
        computed only on rows with finite popularity. No silent warning.
        """
        pytest.skip("Wave 1 implements src/ml/baseline first")

    def test_join_integrity(
        self,
        sample_feature_df: "pytest.fixture",  # type: ignore[name-defined]
        sample_entry_df: "pytest.fixture",  # type: ignore[name-defined]
    ) -> None:
        """Feature-entry join preserves row count (no fan-out / no drops).

        Wave 1 expectation: the joined DataFrame has exactly
        len(sample_feature_df) rows (1:1 on race_id+horse_number); no race_id
        from feature_df is lost; no duplicate horse_race_id appears.
        """
        pytest.skip("Wave 1 implements src/ml/baseline first")
