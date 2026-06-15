"""MODA-01 trainer tests (Wave 0 skeleton).

RESEARCH.md Test Map line 785. PATTERNS.md analog:
tests/pipeline/test_feature_generator.py::TestEndToEnd (hermetic E2E with
small fixture, ML training must finish in ~1s).
"""

import pytest


class TestTrainer:
    """Tests for src/ml/trainer.train_fold_model and train_final_model.

    Covers MODA-01 (LightGBM fold training + OOF collection), Pitfall #1
    (early_stopping callback API in LightGBM 4.6, NOT the legacy
    early_stopping_rounds kwarg), and D-15 (final model trained on full
    train window for holdout evaluation).
    """

    def test_train_fold_model_returns_classifier(
        self,
        sample_feature_df: "pytest.fixture",  # type: ignore[name-defined]
        ml_config: "pytest.fixture",  # type: ignore[name-defined]
    ) -> None:
        """MODA-01: train_fold_model returns a fitted LGBMClassifier.

        Wave 1 expectation: clf is lightgbm.LGBMClassifier, has best_iteration_
        attribute set, and predict_proba returns a (n, 2) array.
        """
        pytest.skip("Wave 1 implements src/ml/trainer first")

    def test_early_stopping_fires(
        self,
        sample_feature_df: "pytest.fixture",  # type: ignore[name-defined]
        ml_config: "pytest.fixture",  # type: ignore[name-defined]
    ) -> None:
        """Pitfall #1: early_stopping callback triggers before n_estimators.

        Wave 1 expectation: with stopping_rounds=10 and n_estimators=50,
        best_iteration_ < 50 (callback API from lightgbm.early_stopping,
        NOT the deprecated early_stopping_rounds constructor kwarg).
        """
        pytest.skip("Wave 1 implements src/ml/trainer first")

    def test_collect_oof_predictions(
        self,
        sample_feature_df: "pytest.fixture",  # type: ignore[name-defined]
        ml_config: "pytest.fixture",  # type: ignore[name-defined]
    ) -> None:
        """MODA-01: OOF predictions cover every training row exactly once.

        Wave 1 expectation: oof DataFrame has len == len(train_df), and a
        'fold' column whose values are in {0..n_splits-1} with each fold
        contributing roughly balanced rows.
        """
        pytest.skip("Wave 1 implements src/ml/trainer first")

    def test_train_final_model(
        self,
        sample_feature_df: "pytest.fixture",  # type: ignore[name-defined]
        ml_config: "pytest.fixture",  # type: ignore[name-defined]
    ) -> None:
        """D-15: train_final_model fits on the FULL train window for holdout.

        Wave 1 expectation: final_model is trained on all rows with
        race_date in [train_start, train_end] (no CV holdout), and can
        predict_proba on the holdout rows without re-fitting.
        """
        pytest.skip("Wave 1 implements src/ml/trainer first")
