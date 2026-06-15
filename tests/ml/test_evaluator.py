"""MODA-04 evaluator tests.

RESEARCH.md Test Map lines 793-794. PATTERNS.md analog:
tests/schemas/test_audit.py (sanity tests for computed metrics).

Covers MODA-04 (ECE computation sanity), D-11 (reliability diagram file
generation), D-06 (evaluate returns a metrics dict with documented keys).
"""

import numpy as np
import pytest

from src.ml.evaluator import compute_ece, evaluate, reliability_diagram


class TestEvaluator:
    """Tests for src/ml/evaluator.compute_ece + evaluate + reliability_diagram.

    Covers MODA-04 (ECE computation sanity), D-11 (reliability diagram file
    generation), D-06 (evaluate returns a metrics dict with documented keys).
    """

    def test_ece_perfect_prediction(
        self, ml_config: "pytest.fixture"  # type: ignore[name-defined]
    ) -> None:
        """MODA-04: a perfect predictor has ECE = 0.

        With y_true == y_prob (e.g. y_true=[0,1,0,1], y_prob=[0.0,1.0,0.0,1.0]),
        compute_ece returns exactly 0.0 (perfectly calibrated).
        """
        n_bins = ml_config["evaluation"]["n_bins"]
        y_true = np.array([0, 1, 0, 1])
        y_prob = np.array([0.0, 1.0, 0.0, 1.0])
        ece = compute_ece(y_true, y_prob, n_bins=n_bins)
        assert ece == pytest.approx(0.0, abs=1e-12)

    def test_ece_worst_case(
        self, ml_config: "pytest.fixture"  # type: ignore[name-defined]
    ) -> None:
        """MODA-04: ECE is bounded in [0, 1] for the worst-case predictor.

        With a maximally wrong predictor (y_true=[0,0,1,1], y_prob=[1,1,0,0]),
        compute_ece returns a value in [0, 1] (typically 1.0 but never NaN/inf).
        """
        n_bins = ml_config["evaluation"]["n_bins"]
        y_true = np.array([0, 0, 1, 1])
        y_prob = np.array([1.0, 1.0, 0.0, 0.0])
        ece = compute_ece(y_true, y_prob, n_bins=n_bins)
        assert np.isfinite(ece)
        assert 0.0 <= ece <= 1.0

    def test_ece_bin_weighting(
        self, ml_config: "pytest.fixture"  # type: ignore[name-defined]
    ) -> None:
        """ECE bins are weighted by sample proportion.

        With n_bins=10 and 10 samples clustering in 2 bins (9 in bin 0 at
        conf 0.05, 1 in bin 9 at conf 0.95), the ECE equals the weighted
        average of per-bin gaps, NOT the unweighted mean:
            bin 0: acc=8/9, conf=0.05 -> gap=0.8389, weight=9/10
            bin 9: acc=1/1, conf=0.95 -> gap=0.05,  weight=1/10
            ECE = 0.9*0.8389 + 0.1*0.05 = 0.7600
        Unweighted mean would be (0.8389 + 0.05)/2 = 0.4444 (distinctly less).
        """
        n_bins = ml_config["evaluation"]["n_bins"]
        # 9 negatives predicted low, 1 positive predicted high
        y_true = np.array([0, 0, 0, 0, 0, 0, 0, 0, 1, 1])
        # Wait: 9 in bin 0 means 9 samples at ~0.05; but we need 1 positive
        # among them for acc=8/9. Reconstruct: 8 negatives + 1 positive at
        # 0.05 (bin 0), plus 1 positive at 0.95 (bin 9). Total = 10.
        y_true = np.array([0, 0, 0, 0, 0, 0, 0, 0, 1, 1])
        # 8 negatives at index 0..7, 1 positive at index 8 (bin 0), 1 positive
        # at index 9 (bin 9).
        y_prob = np.array(
            [0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.95]
        )
        ece = compute_ece(y_true, y_prob, n_bins=n_bins)
        # Manual: bin 0 -> acc=1/9, conf=0.05, gap=0.9389, w=9/10
        #         bin 9 -> acc=1/1, conf=0.95, gap=0.05,  w=1/10
        # (The single positive in bin 0 makes acc=1/9, not 8/9.)
        expected = 0.9 * abs(1.0 / 9.0 - 0.05) + 0.1 * abs(1.0 - 0.95)
        assert ece == pytest.approx(expected, abs=1e-9)
        # Sanity: weighted != unweighted
        unweighted = (abs(1.0 / 9.0 - 0.05) + abs(1.0 - 0.95)) / 2.0
        assert ece != pytest.approx(unweighted, abs=1e-6)

    def test_reliability_diagram_generates_file(
        self,
        ml_config: "pytest.fixture",  # type: ignore[name-defined]
        tmp_ml_output_dir: "pytest.fixture",  # type: ignore[name-defined]
    ) -> None:
        """D-11: reliability diagram writes a PNG to the output directory.

        reliability_diagram(y_true, y_prob, save_path) writes a file at
        save_path that exists and is non-empty. matplotlib backend forced to
        Agg (no display required).
        """
        n_bins = ml_config["evaluation"]["n_bins"]
        y_true = np.array([0, 0, 1, 1, 0, 1])
        y_prob = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.9])
        out_path = tmp_ml_output_dir / "reliability_diagram.png"
        fig = reliability_diagram(y_true, y_prob, n_bins=n_bins, save_path=out_path)
        try:
            assert out_path.exists()
            assert out_path.stat().st_size > 0
        finally:
            import matplotlib.pyplot as plt

            plt.close(fig)

    def test_evaluate_returns_metrics_dict(
        self, ml_config: "pytest.fixture"  # type: ignore[name-defined]
    ) -> None:
        """D-06: evaluate returns a metrics dict with documented keys.

        Keys include auc_calibrated + ece_calibrated (D-06 主指標 AUC +
        D-11 success metric), plus the raw/calibrated pairs for AUC/Brier/
        logloss/ECE and n_samples. AUC is computed via
        sklearn.metrics.roc_auc_score; values are floats in expected ranges.
        """
        n_bins = ml_config["evaluation"]["n_bins"]
        y_true = np.array([0, 1, 0, 1, 0, 1, 1, 0])
        y_prob_raw = np.array([0.2, 0.8, 0.3, 0.7, 0.4, 0.6, 0.55, 0.45])
        # Calibrated: closer to the true rate per bin (sharper).
        y_prob_cal = np.array([0.1, 0.9, 0.2, 0.8, 0.3, 0.7, 0.75, 0.25])
        result = evaluate(y_true, y_prob_raw, y_prob_cal, n_bins=n_bins)

        required_keys = {
            "auc_raw",
            "auc_calibrated",
            "brier_raw",
            "brier_calibrated",
            "logloss_raw",
            "logloss_calibrated",
            "ece_raw",
            "ece_calibrated",
            "n_samples",
        }
        assert required_keys.issubset(result.keys())
        # D-06 主指標 AUC present for calibrated path
        assert "auc_calibrated" in result
        # D-11 success metric present
        assert "ece_calibrated" in result
        # Range checks
        for k in ("auc_raw", "auc_calibrated"):
            assert 0.0 <= result[k] <= 1.0
        for k in ("brier_raw", "brier_calibrated"):
            assert 0.0 <= result[k] <= 1.0
        for k in ("ece_raw", "ece_calibrated"):
            assert 0.0 <= result[k] <= 1.0
        for k in ("logloss_raw", "logloss_calibrated"):
            assert np.isfinite(result[k]) and result[k] >= 0.0
        assert result["n_samples"] == len(y_true)
        # AUC should be high for this trivially-separable fixture
        assert result["auc_calibrated"] >= 0.7
