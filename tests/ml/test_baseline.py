"""MODA-03 baseline tests.

RESEARCH.md Test Map line 791. PATTERNS.md analog:
tests/pipeline/test_feature_generator.py::TestJockeyTrainerStats
(groupby aggregation correctness against hand-built fixtures).

Covers MODA-03 (popularity-based baseline AUC), Pitfall #6 (NaN
popularity rows must be dropped, not silently coerced), and join
integrity between the feature matrix and entry table.
"""

import numpy as np
import pandas as pd
import pytest

from src.ml.baseline import compute_popularity_baseline


class TestBaseline:
    """Tests for src/ml/baseline.compute_popularity_baseline.

    Covers MODA-03 (popularity-based baseline AUC), Pitfall #6 (NaN
    popularity rows must be dropped, not silently coerced), and join
    integrity between the feature matrix and entry table.
    """

    @staticmethod
    def _perfect_fixture() -> tuple[pd.DataFrame, pd.DataFrame]:
        """Build a fixture where popularity perfectly predicts target_top3.

        2 races × 4 horses each. In each race, popularity 1/2/3 are top-3
        (target=1), popularity 4 is out (target=0). AUC against
        -popularity must be exactly 1.0.
        """
        features = pd.DataFrame(
            {
                "race_id": ["R1"] * 4 + ["R2"] * 4,
                "horse_number": [1, 2, 3, 4, 1, 2, 3, 4],
                "target_top3": [1, 1, 1, 0, 1, 1, 1, 0],
            }
        )
        entry = pd.DataFrame(
            {
                "race_id": ["R1"] * 4 + ["R2"] * 4,
                "horse_number": [1, 2, 3, 4, 1, 2, 3, 4],
                "popularity": [1.0, 2.0, 3.0, 4.0, 1.0, 2.0, 3.0, 4.0],
            }
        )
        return features, entry

    def test_popularity_baseline_auc(
        self,
        sample_feature_df: "pytest.fixture",  # type: ignore[name-defined]
        sample_entry_df: "pytest.fixture",  # type: ignore[name-defined]
    ) -> None:
        """MODA-03: with popularity perfectly inversely correlated to target_top3,
        AUC is high (>= 0.9 on the hand-built fixture).

        On the deterministic perfect fixture, baseline AUC is exactly 1.0
        (popularity rank fully separates top-3 from the rest).
        """
        features, entry = self._perfect_fixture()
        result = compute_popularity_baseline(features, entry)
        assert "baseline_auc" in result
        assert result["baseline_auc"] == pytest.approx(1.0, abs=1e-9)
        assert result["n_rows"] == len(features)

    def test_popularity_baseline_random(
        self,
        sample_feature_df: "pytest.fixture",  # type: ignore[name-defined]
        sample_entry_df: "pytest.fixture",  # type: ignore[name-defined]
    ) -> None:
        """MODA-03: with random popularity (no signal), AUC ≈ 0.5.

        A fixture where popularity is random w.r.t. target_top3 yields a
        baseline AUC close to 0.5 (chance-level ranking). Validates the
        baseline is measuring actual popularity-target correlation, not a
        trivially-high artifact of the metric.
        """
        rng = np.random.default_rng(seed=42)
        n = 200
        features = pd.DataFrame(
            {
                "race_id": [f"R{i // 4}" for i in range(n)],
                "horse_number": [(i % 4) + 1 for i in range(n)],
                "target_top3": rng.integers(0, 2, size=n).astype(int),
            }
        )
        entry = pd.DataFrame(
            {
                "race_id": features["race_id"].values,
                "horse_number": features["horse_number"].values,
                "popularity": rng.integers(1, 18, size=n).astype(float),
            }
        )
        result = compute_popularity_baseline(features, entry)
        assert result["baseline_auc"] == pytest.approx(0.5, abs=0.1)

    def test_popularity_nan_dropped(
        self,
        sample_feature_df: "pytest.fixture",  # type: ignore[name-defined]
        sample_entry_df: "pytest.fixture",  # type: ignore[name-defined]
    ) -> None:
        """Pitfall #6: NaN popularity rows are dropped, not coerced to 0.

        ``compute_popularity_baseline`` drops rows where popularity is NaN
        (no implicit 0-fill), and the returned AUC is computed only on rows
        with finite popularity. Crucially, passing popularity NaN into
        ``roc_auc_score`` would raise ``ValueError`` — this test verifies
        the NaN-drop path prevents that crash.
        """
        features, entry = self._perfect_fixture()
        # Inject 2 NaN popularity rows (cancel/scratch reproduction).
        entry.loc[0, "popularity"] = np.nan
        entry.loc[4, "popularity"] = np.nan
        result = compute_popularity_baseline(features, entry)
        # 2 NaN rows dropped from the 8-row fixture -> 6 valid rows.
        assert result["n_rows"] == 6
        # AUC still computable (no ValueError raised) and high (perfect
        # correlation preserved on the surviving rows).
        assert result["baseline_auc"] == pytest.approx(1.0, abs=1e-9)

    def test_join_integrity(
        self,
        sample_feature_df: "pytest.fixture",  # type: ignore[name-defined]
        sample_entry_df: "pytest.fixture",  # type: ignore[name-defined]
    ) -> None:
        """Feature-entry join preserves row count (no fan-out / no drops).

        On the hermetic ``sample_feature_df`` + ``sample_entry_df`` fixtures
        (1:1 on race_id+horse_number), the joined DataFrame inside
        ``compute_popularity_baseline`` has exactly as many rows as the
        feature fixture, minus only the explicit NaN-popularity rows
        (Pitfall #6). No race_id from the feature fixture is silently lost
        to a join miss; no duplicate horse_race_id appears from fan-out.
        """
        n_feature = len(sample_feature_df)
        result = compute_popularity_baseline(sample_feature_df, sample_entry_df)
        # sample_entry_df has popularity NaN on rows where i % 5 == 0.
        # Count those NaN rows for the expected n_rows assertion.
        n_nan_pop = int(sample_entry_df["popularity"].isna().sum())
        # Also account for any target_top3 NaN (none in this fixture by design).
        expected_n = n_feature - n_nan_pop
        assert result["n_rows"] == expected_n
        # baseline AUC is in [0,1] (no ValueError on the joined set).
        assert 0.0 <= result["baseline_auc"] <= 1.0
