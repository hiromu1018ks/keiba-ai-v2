"""Tests for src/schemas/__init__.py re-exports.

Verifies that all 8 symbols (5 schema classes, 2 audit functions, 1 export
function) are accessible via `from src.schemas import ...` and that __all__
is correctly defined.
"""

import src.schemas


class TestSchemaClassReexports:
    """Test that all 5 schema classes are re-exported."""

    def test_import_race_schema(self):
        from src.schemas import RaceSchema

        assert RaceSchema.__name__ == "RaceSchema"

    def test_import_entry_schema(self):
        from src.schemas import EntrySchema

        assert EntrySchema.__name__ == "EntrySchema"

    def test_import_result_schema(self):
        from src.schemas import ResultSchema

        assert ResultSchema.__name__ == "ResultSchema"

    def test_import_odds_trifecta_schema(self):
        from src.schemas import OddsTrifectaSchema

        assert OddsTrifectaSchema.__name__ == "OddsTrifectaSchema"

    def test_import_payoff_schema(self):
        from src.schemas import PayoffSchema

        assert PayoffSchema.__name__ == "PayoffSchema"

    def test_all_five_classes_importable_in_one_statement(self):
        from src.schemas import (
            EntrySchema,
            OddsTrifectaSchema,
            PayoffSchema,
            RaceSchema,
            ResultSchema,
        )

        assert {RaceSchema, EntrySchema, ResultSchema, OddsTrifectaSchema, PayoffSchema}


class TestAuditFunctionReexports:
    """Test that audit functions are re-exported."""

    def test_import_get_post_race_columns(self):
        from src.schemas import get_post_race_columns

        assert callable(get_post_race_columns)

    def test_import_audit_leakage(self):
        from src.schemas import audit_leakage

        assert callable(audit_leakage)


class TestExportFunctionReexports:
    """Test that export function is re-exported."""

    def test_import_export_schema_documentation(self):
        from src.schemas import export_schema_documentation

        assert callable(export_schema_documentation)


class TestAllDunder:
    """Test __all__ list correctness."""

    def test_all_contains_exactly_8_symbols(self):
        expected = {
            "RaceSchema",
            "EntrySchema",
            "ResultSchema",
            "OddsTrifectaSchema",
            "PayoffSchema",
            "get_post_race_columns",
            "audit_leakage",
            "export_schema_documentation",
        }
        assert hasattr(src.schemas, "__all__"), "__all__ not defined in src.schemas"
        assert set(src.schemas.__all__) == expected
        assert len(src.schemas.__all__) == 8

    def test_star_import_matches_all(self):
        """Verify that import * brings in exactly __all__ symbols."""
        expected = set(src.schemas.__all__)
        imported = {
            name
            for name in dir(src.schemas)
            if not name.startswith("_") and name in expected
        }
        assert imported == expected
