"""MODA-04 evaluator tests (Wave 0 skeleton).

RESEARCH.md Test Map lines 793-794. PATTERNS.md analog:
tests/schemas/test_audit.py (sanity tests for computed metrics).
"""

import pytest


class TestEvaluator:
    """Tests for src/ml/evaluator.compute_ece and reliability diagram output.

    Covers MODA-04 (ECE computation sanity), D-11 (reliability diagram file
    generation), D-06 (evaluate returns a metrics dict with documented keys).
    """

    def test_ece_perfect_prediction(
        self, ml_config: "pytest.fixture"  # type: ignore[name-defined]
    ) -> None:
        """MODA-04: a perfect predictor has ECE = 0.

        Wave 1 expectation: with y_true == y_prob (e.g. y_true=[0,1,0,1],
        y_prob=[0.0,1.0,0.0,1.0]), compute_ece returns exactly 0.0.
        """
        pytest.skip("Wave 1 implements src/ml/evaluator first")

    def test_ece_worst_case(
        self, ml_config: "pytest.fixture"  # type: ignore[name-defined]
    ) -> None:
        """MODA-04: ECE is bounded in [0, 1] for the worst-case predictor.

        Wave 1 expectation: with a maximally wrong predictor
        (y_true=[0,0,1,1], y_prob=[1,1,0,0]), compute_ece returns a value in
        [0, 1] (typically 1.0 but never NaN/inf).
        """
        pytest.skip("Wave 1 implements src/ml/evaluator first")

    def test_ece_bin_weighting(
        self, ml_config: "pytest.fixture"  # type: ignore[name-defined]
    ) -> None:
        """ECE bins are weighted by sample proportion.

        Wave 1 expectation: with n_bins=10 and a custom y_prob distribution
        that clusters in 2 bins only, the ECE equals the weighted average
        of per-bin gaps (not the unweighted mean).
        """
        pytest.skip("Wave 1 implements src/ml/evaluator first")

    def test_reliability_diagram_generates_file(
        self,
        ml_config: "pytest.fixture",  # type: ignore[name-defined]
        tmp_ml_output_dir: "pytest.fixture",  # type: ignore[name-defined]
    ) -> None:
        """D-11: reliability diagram writes a PNG to the output directory.

        Wave 1 expectation: plot_reliability_diagram(y_true, y_prob, out_path)
        writes a file at out_path that exists and is non-empty (>1KB PNG).
        matplotlib backend forced to Agg (no display required).
        """
        pytest.skip("Wave 1 implements src/ml/evaluator first")

    def test_evaluate_returns_metrics_dict(
        self, ml_config: "pytest.fixture"  # type: ignore[name-defined]
    ) -> None:
        """D-06: evaluate returns a metrics dict with documented keys.

        Wave 1 expectation: keys include at minimum {'ece', 'auc', 'logloss',
        'brier_score'}; AUC computed via sklearn.metrics.roc_auc_score;
        values are floats in expected ranges.
        """
        pytest.skip("Wave 1 implements src/ml/evaluator first")
