"""Data pipeline package for the 3-layer data architecture.

Re-exports key column mapping dicts and helper functions for downstream
phases to access via ``from src.pipeline import ...``.
"""

from src.pipeline.column_mapping import (
    DTYPE_SPEC,
    FLAG_COLUMNS,
    KAGGLE_COLUMN_MAP,
    ODDS_COLUMN_MAP,
    TABLE_TO_SCHEMA,
    get_columns_for_table,
)
from src.pipeline.validators import run_all_validations

__all__ = [
    "KAGGLE_COLUMN_MAP",
    "ODDS_COLUMN_MAP",
    "FLAG_COLUMNS",
    "DTYPE_SPEC",
    "TABLE_TO_SCHEMA",
    "get_columns_for_table",
    "run_all_validations",
]
