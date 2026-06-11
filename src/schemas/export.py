"""Schema export function for machine-readable documentation.

Provides export_schema_documentation() which builds a dict of all 5 table
schemas using Pydantic's model_json_schema() and optionally writes the
result as a JSON file. The exported JSON includes pre_race metadata on
every field property, enabling downstream tooling to verify data leakage
classification without importing Python modules.
"""

import json
from pathlib import Path
from typing import Optional

from src.schemas.entry import EntrySchema
from src.schemas.odds_trifecta import OddsTrifectaSchema
from src.schemas.payoff import PayoffSchema
from src.schemas.race import RaceSchema
from src.schemas.result import ResultSchema


def export_schema_documentation(
    output_path: Optional[Path] = None,
) -> dict:
    """Export all table schemas as machine-readable JSON.

    Builds a dict mapping table names to their Pydantic model_json_schema()
    output. Each schema includes field properties with pre_race metadata.

    If output_path is provided, writes the dict as formatted JSON to that path.

    Args:
        output_path: Optional file path to write JSON output.
            If provided, creates parent directories as needed.

    Returns:
        Dict mapping table names to their JSON schema dicts.
        Keys: "race", "entry", "result", "odds_trifecta", "payoff"
    """
    schemas: dict = {
        "race": RaceSchema.model_json_schema(),
        "entry": EntrySchema.model_json_schema(),
        "result": ResultSchema.model_json_schema(),
        "odds_trifecta": OddsTrifectaSchema.model_json_schema(),
        "payoff": PayoffSchema.model_json_schema(),
    }

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(schemas, f, indent=2, ensure_ascii=False)

    return schemas
