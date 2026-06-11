"""Shared pytest fixtures for audit tests."""

import pandas as pd
import pytest

from src.schemas.entry import EntrySchema
from src.schemas.race import RaceSchema
from src.schemas.result import ResultSchema


@pytest.fixture
def sample_pre_race_df() -> pd.DataFrame:
    """DataFrame with only pre-race column names."""
    return pd.DataFrame(
        {
            "race_id": ["202101010101"],
            "horse_number": [1],
            "distance": [2000],
        }
    )


@pytest.fixture
def sample_entry_post_race_df() -> pd.DataFrame:
    """DataFrame with entry post-race column names (popularity, win_odds)."""
    return pd.DataFrame(
        {
            "popularity": [1],
            "win_odds": [2.5],
        }
    )


@pytest.fixture
def sample_result_post_race_df() -> pd.DataFrame:
    """DataFrame with result post-race column names."""
    return pd.DataFrame(
        {
            "finish_position": [1],
            "finish_time": ["1:32.5"],
            "last_3f": [34.5],
            "prize_money": [5000.0],
        }
    )


@pytest.fixture
def sample_mixed_df() -> pd.DataFrame:
    """DataFrame with both pre-race and post-race columns from entry and result."""
    return pd.DataFrame(
        {
            "race_id": ["202101010101"],
            "horse_number": [1],
            "popularity": [3],
            "win_odds": [5.0],
            "finish_position": [2],
            "last_3f": [35.1],
        }
    )


@pytest.fixture
def sample_lag_feature_df() -> pd.DataFrame:
    """DataFrame with lag feature column names like prev_1_last_3f."""
    return pd.DataFrame(
        {
            "prev_1_last_3f": [34.5],
            "prev_1_corner_4": [3],
            "prev_2_last_3f": [35.0],
        }
    )


@pytest.fixture
def entry_model_classes() -> list[type]:
    """Model classes for entry context: EntrySchema and RaceSchema."""
    return [EntrySchema, RaceSchema]


@pytest.fixture
def full_model_classes() -> list[type]:
    """Full model classes: EntrySchema, ResultSchema, and RaceSchema."""
    return [EntrySchema, ResultSchema, RaceSchema]
