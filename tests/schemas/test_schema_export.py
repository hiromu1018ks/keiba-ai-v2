"""JSON schema export validation tests.

Validates:
- export_schema_documentation() returns dict with 5 table schema keys
- export_schema_documentation(output_path) writes valid JSON file
- Written JSON contains valid schema with all 5 tables
- Each schema has properties with pre_race metadata
"""

import json
from pathlib import Path

from src.schemas.export import export_schema_documentation


class TestSchemaExport:
    """Test export_schema_documentation function."""

    def test_export_returns_all_schemas(self) -> None:
        """export_schema_documentation() returns dict with 5 table keys."""
        result = export_schema_documentation()

        assert isinstance(result, dict)
        expected_keys = {"race", "entry", "result", "odds_trifecta", "payoff"}
        assert set(result.keys()) == expected_keys

    def test_export_writes_json_file(self, tmp_path: Path) -> None:
        """export_schema_documentation(tmp_path) writes valid JSON file."""
        output_file = tmp_path / "schema.json"
        result = export_schema_documentation(output_file)

        # File exists
        assert output_file.exists(), "schema.json was not created"

        # File contains valid JSON
        with open(output_file) as f:
            loaded = json.load(f)

        # JSON has 5 top-level keys
        expected_keys = {"race", "entry", "result", "odds_trifecta", "payoff"}
        assert set(loaded.keys()) == expected_keys

        # Returned dict matches written file content
        assert result == loaded

    def test_export_json_has_pre_race_metadata(self, tmp_path: Path) -> None:
        """Each property in exported JSON has pre_race metadata."""
        output_file = tmp_path / "schema.json"
        export_schema_documentation(output_file)

        with open(output_file) as f:
            loaded = json.load(f)

        for table_name, schema in loaded.items():
            assert "properties" in schema, (
                f"{table_name} schema missing 'properties' key"
            )
            properties = schema["properties"]
            assert len(properties) > 0, (
                f"{table_name} schema has no properties"
            )

            # Check that each property has pre_race metadata
            for prop_name, prop_def in properties.items():
                assert "pre_race" in prop_def, (
                    f"{table_name}.{prop_name} missing 'pre_race' metadata"
                )

    def test_combined_export(self) -> None:
        """All 5 schemas are present and have model-level metadata."""
        result = export_schema_documentation()

        for table_name in ["race", "entry", "result", "odds_trifecta", "payoff"]:
            assert table_name in result, f"Missing table: {table_name}"
            schema = result[table_name]
            assert "properties" in schema
            assert "title" in schema
            assert len(schema["properties"]) > 0
