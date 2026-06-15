"""MODA-01 data_loader tests (Wave 0 skeleton).

RESEARCH.md Test Map lines 786-787, 795. PATTERNS.md analog:
tests/pipeline/test_feature_generator.py::TestLoadMerge.

Wave 1 will implement src/ml/data_loader.py; until then every case skips.
"""

import pytest


class TestFeatureLoad:
    """Tests for src/ml/data_loader.load_feature_matrix.

    Covers MODA-01 (categorical conversion, horse_race_id derive), T-data-leak
    (post-race column audit), D-01/D-02 train/holdout window splits, and
    Pitfall #3 (categorical dtype) / #2 (horse_race_id authority) / #4
    (grade NaN preservation) / #7 (train/holdout time gap).
    """

    def test_categorical_conversion(
        self, sample_feature_df: "pytest.fixture"  # type: ignore[name-defined]
    ) -> None:
        """MODA-01 / Pitfall #3: jockey/trainer arrive as pandas CategoricalDtype.

        Wave 1 expectation: after load_feature_matrix, every column in
        feature_generator.CATEGORICAL_COLUMNS is either category dtype
        (jockey/trainer) or stays string-with-NaN (grade). LightGBM should
        see the categoricals natively (no one-hot, D-16).
        """
        pytest.skip("Wave 1 implements src/ml/data_loader first")

    def test_horse_race_id_derive(
        self, sample_entry_df: "pytest.fixture"  # type: ignore[name-defined]
    ) -> None:
        """MODA-01 / Pitfall #2: horse_race_id = f"{race_id}{horse_number:02d}".

        Wave 1 expectation: derived horse_race_id is globally unique per row
        and round-trips 1:1 against (race_id, horse_number) for joins.
        """
        pytest.skip("Wave 1 implements src/ml/data_loader first")

    def test_leakage_audit(
        self, sample_feature_df: "pytest.fixture"  # type: ignore[name-defined]
    ) -> None:
        """T-data-leak: post-race columns absent from feature matrix.

        Wave 1 expectation: audit_leakage([RaceSchema, EntrySchema], df, ...)
        returns empty when run against sample_feature_df (no popularity/
        win_odds/finish_position columns present by construction).
        """
        pytest.skip("Wave 1 implements src/ml/data_loader first")

    def test_train_holdout_window_counts(
        self,
        sample_feature_df: "pytest.fixture",  # type: ignore[name-defined]
        ml_config: "pytest.fixture",  # type: ignore[name-defined]
    ) -> None:
        """MODA-01 / D-01 / D-02 / Pitfall #7: train and holdout split cleanly.

        Wave 1 expectation: with ml_config data.train_end=2023-12-31 and
        holdout_start=2024-01-01, all 2024 race rows land in holdout and
        2018-2023 rows land in train. No race_id straddles both windows.
        """
        pytest.skip("Wave 1 implements src/ml/data_loader first")

    def test_grade_nan_preserved(
        self, sample_feature_df: "pytest.fixture"  # type: ignore[name-defined]
    ) -> None:
        """Pitfall #4: grade column keeps NaN for non-graded races.

        Wave 1 expectation: grade is object/string dtype, NaNs survive
        (not silently filled with '' or '未勝利'), and the column can be
        coerced to category with NaN as a category.
        """
        pytest.skip("Wave 1 implements src/ml/data_loader first")
