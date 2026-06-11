"""Tests for audit functions: get_post_race_columns and audit_leakage.

Covers DATA-04: pre/post column audit mechanism that prevents post-race
information from leaking into features.
"""

import pandas as pd
import pytest
from loguru import logger

from src.schemas.audit import audit_leakage, get_post_race_columns
from src.schemas.entry import EntrySchema
from src.schemas.race import RaceSchema
from src.schemas.result import ResultSchema


class TestGetPostRaceColumns:
    """Tests for get_post_race_columns function."""

    def test_entry_schema_returns_popularity_and_win_odds(self) -> None:
        """Test 1: get_post_race_columns(EntrySchema) returns popularity and win_odds."""
        result = get_post_race_columns(EntrySchema)
        assert result == {"popularity", "win_odds"}

    def test_race_schema_returns_empty_set(self) -> None:
        """Test 2: get_post_race_columns(RaceSchema) returns empty set."""
        result = get_post_race_columns(RaceSchema)
        assert result == set()

    def test_result_schema_returns_all_field_names(self) -> None:
        """Test 3: get_post_race_columns(ResultSchema) returns ALL ResultSchema field names."""
        result = get_post_race_columns(ResultSchema)
        expected = set(ResultSchema.model_fields.keys())
        assert result == expected


class TestAuditLeakage:
    """Tests for audit_leakage function."""

    def test_detects_entry_post_race_columns(
        self, sample_entry_post_race_df: pd.DataFrame
    ) -> None:
        """Test 4: audit_leakage detects popularity column from EntrySchema."""
        result = audit_leakage([EntrySchema], sample_entry_post_race_df, "test")
        assert "popularity" in result

    def test_detects_result_post_race_columns(
        self, sample_result_post_race_df: pd.DataFrame
    ) -> None:
        """Test 5: audit_leakage detects finish_position from ResultSchema."""
        result = audit_leakage(
            [ResultSchema], sample_result_post_race_df, "test"
        )
        assert "finish_position" in result

    def test_no_leakage_for_pre_race_only(
        self, sample_pre_race_df: pd.DataFrame
    ) -> None:
        """Test 6: audit_leakage returns empty list for pre-race-only DataFrame."""
        result = audit_leakage(
            [RaceSchema], sample_pre_race_df, "test"
        )
        assert result == []

    def test_logs_warning_on_leakage(
        self, sample_entry_post_race_df: pd.DataFrame
    ) -> None:
        """Test 7: audit_leakage logs warning when post-race columns detected."""
        import io
        import sys

        # Capture loguru output
        output = io.StringIO()
        logger.remove()  # Remove default handler
        logger.add(output, format="{message}")

        try:
            audit_leakage([EntrySchema], sample_entry_post_race_df, "test")
            log_output = output.getvalue()
            assert "leakage" in log_output.lower() or "post-race" in log_output.lower()
        finally:
            logger.remove()
            logger.add(sys.stderr)  # Restore default handler

        # Verify no exception was raised (D-12)

    def test_logs_info_when_no_leakage(
        self, sample_pre_race_df: pd.DataFrame
    ) -> None:
        """Test 8: audit_leakage logs info when no leakage detected."""
        import io
        import sys

        output = io.StringIO()
        logger.remove()
        logger.add(output, format="{message}")

        try:
            audit_leakage([RaceSchema], sample_pre_race_df, "test")
            log_output = output.getvalue()
            assert "no" in log_output.lower() or "clean" in log_output.lower()
        finally:
            logger.remove()
            logger.add(sys.stderr)

    def test_exact_name_matching_no_false_positive_on_lag_features(
        self, sample_lag_feature_df: pd.DataFrame
    ) -> None:
        """Test 9: 'last_3f' triggers audit but 'prev_1_last_3f' does NOT."""
        # ResultSchema has last_3f as post-race, but prev_1_last_3f is a lag feature
        result = audit_leakage(
            [ResultSchema], sample_lag_feature_df, "test"
        )
        # prev_1_last_3f should NOT be detected -- exact matching only
        assert "prev_1_last_3f" not in result
        # None of the lag feature columns match exact post-race names
        assert result == []

    def test_accepts_multiple_model_classes(
        self, sample_mixed_df: pd.DataFrame
    ) -> None:
        """Test 10: audit_leakage combines post-race sets from multiple model classes."""
        result = audit_leakage(
            [EntrySchema, ResultSchema], sample_mixed_df, "test"
        )
        # Should detect both entry post-race (popularity, win_odds)
        # and result post-race (finish_position, last_3f) columns
        assert "popularity" in result
        assert "win_odds" in result
        assert "finish_position" in result
        assert "last_3f" in result

    def test_all_result_columns_detected_as_leaked(self) -> None:
        """Test 11: audit_leakage detects all ResultSchema fields as leaked."""
        all_result_cols = list(ResultSchema.model_fields.keys())
        df = pd.DataFrame({col: [0] for col in all_result_cols})
        result = audit_leakage([ResultSchema], df, "test")
        assert set(result) == set(all_result_cols)
