"""MODA-04 calibrator tests (Wave 0 skeleton).

RESEARCH.md Test Map line 792. PATTERNS.md analog:
tests/pipeline/test_feature_generator.py::TestFinishTimeZscore (leak-free
normalization with hand-built expected values).
"""

import pytest


class TestCalibrator:
    """Tests for src/ml/calibrator.IsotonicCalibrator.

    Covers MODA-04 (leak-free isotonic calibration), T-cali-leak (OOF fit ->
    holdout predict boundary), Pitfall #5 (calibrator NEVER fit on holdout),
    and output shape invariants ([0,1] range, monotonic non-decreasing).
    """

    def test_leak_free_calibration(
        self, ml_config: "pytest.fixture"  # type: ignore[name-defined]
    ) -> None:
        """MODA-04 / T-cali-leak / Pitfall #5: calibrator fits on OOF only.

        Wave 1 expectation: with OOF predictions + OOF labels, the calibrator
        fits; then predicting on a disjoint holdout set returns transformed
        probabilities that are NOT identical to the raw holdout logits
        (the iso transform was learned from OOF, not holdout).
        """
        pytest.skip("Wave 1 implements src/ml/calibrator first")

    def test_isotonic_output_in_01_range(
        self, ml_config: "pytest.fixture"  # type: ignore[name-defined]
    ) -> None:
        """Calibrated predictions are bounded in [0, 1].

        Wave 1 expectation: with adversarial inputs (e.g. raw p = -10, +10),
        the isotonic transform clips outputs into [0, 1] (IsotonicRegression
        boundary behavior). No NaN, no inf.
        """
        pytest.skip("Wave 1 implements src/ml/calibrator first")

    def test_isotonic_monotonic_non_decreasing(
        self, ml_config: "pytest.fixture"  # type: ignore[name-defined]
    ) -> None:
        """Calibrated predictions are monotonic non-decreasing in raw input.

        Wave 1 expectation: sort raw predictions ascending; the calibrated
        output is also ascending (np.diff >= 0 everywhere). Isotonic
        regression is the guarantee.
        """
        pytest.skip("Wave 1 implements src/ml/calibrator first")
