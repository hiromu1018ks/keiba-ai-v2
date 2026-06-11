"""Data leakage audit functions for pre/post-race column classification.

Provides get_post_race_columns() and audit_leakage() for detecting post-race
information in DataFrames. Designed for use at both standard-layer generation
(Phase 2) and feature-layer generation (Phase 3).

Per D-11: audit_leakage() accepts any BaseModel subclass and any pandas
DataFrame, enabling invocation at multiple pipeline stages.

Per D-12: audit_leakage() logs warnings only -- it does NOT raise exceptions.
The caller receives the list of leaked columns for inspection and can decide
how to proceed.
"""

from typing import TYPE_CHECKING

from loguru import logger
from pydantic import BaseModel

if TYPE_CHECKING:
    import pandas as pd


def get_post_race_columns(model_class: type[BaseModel]) -> set[str]:
    """Extract post-race column names from a Pydantic model class.

    Reads json_schema_extra["pre_race"] from each FieldInfo in model_fields.
    A field is classified as post-race when pre_race is explicitly False.

    Args:
        model_class: A Pydantic BaseModel subclass with json_schema_extra
            metadata containing {"pre_race": bool, "table": str}.

    Returns:
        Set of field names where pre_race=False (post-race columns).
    """
    post_race: set[str] = set()
    for name, info in model_class.model_fields.items():
        extra = info.json_schema_extra
        if isinstance(extra, dict) and not extra.get("pre_race", True):
            post_race.add(name)
    return post_race


def audit_leakage(
    model_classes: list[type[BaseModel]],
    df: "pd.DataFrame",
    context: str = "feature generation",
) -> list[str]:
    """Check DataFrame for post-race column leakage.

    Collects all post-race column names from the given model classes, then
    checks each column in the DataFrame against the post-race set using
    EXACT column name matching (no substring checks).

    Per D-12: logs a warning when leakage is detected but does NOT raise.
    Per Pitfall #3: uses exact name matching so lag feature columns like
    "prev_1_last_3f" will NOT trigger for the post-race column "last_3f".

    Args:
        model_classes: List of Pydantic BaseModel subclasses to check against.
        df: pandas DataFrame whose columns are checked for post-race leakage.
        context: Description of the pipeline stage (for log messages).

    Returns:
        List of DataFrame column names that are classified as post-race.
        Empty list if no leakage detected.
    """
    all_post_race: set[str] = set()
    for cls in model_classes:
        all_post_race |= get_post_race_columns(cls)

    # Exact column name matching only -- no substring checks
    leaked = [col for col in df.columns if col in all_post_race]

    if leaked:
        logger.warning(
            f"Data leakage detected during {context}: "
            f"post-race columns found: {leaked}"
        )
    else:
        logger.info(f"No data leakage detected during {context}")

    return leaked
