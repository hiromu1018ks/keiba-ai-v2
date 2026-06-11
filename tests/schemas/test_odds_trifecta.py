"""Tests for OddsTrifectaSchema - standard-layer odds_trifecta table schema definition.

All fields in OddsTrifectaSchema are post-race (pre_race=False) per D-04.
Maps the trifecta odds columns from Kaggle odds.csv (top-3 popular combinations).
"""

import json

from src.schemas.odds_trifecta import OddsTrifectaSchema


class TestOddsTrifectaSchemaFields:
    """Verify OddsTrifectaSchema has all expected fields from Kaggle odds.csv trifecta columns."""

    # All expected field names based on RESEARCH.md "odds.csv: Trifecta-Relevant Columns"
    EXPECTED_FIELDS = {
        "race_id",
        # Trifecta 1 (top combination)
        "trifecta1_combo_1",
        "trifecta1_combo_2",
        "trifecta1_combo_3",
        "trifecta1_odds",
        "trifecta1_popularity",
        # Trifecta 2 (second combination)
        "trifecta2_combo_1",
        "trifecta2_combo_2",
        "trifecta2_combo_3",
        "trifecta2_odds",
        "trifecta2_popularity",
        # Trifecta 3 (third combination)
        "trifecta3_combo_1",
        "trifecta3_combo_2",
        "trifecta3_combo_3",
        "trifecta3_odds",
        "trifecta3_popularity",
    }

    def test_odds_trifecta_schema_has_all_fields(self):
        """OddsTrifectaSchema.model_fields contains all expected field names."""
        actual_fields = set(OddsTrifectaSchema.model_fields.keys())
        missing = self.EXPECTED_FIELDS - actual_fields
        extra = actual_fields - self.EXPECTED_FIELDS
        assert not missing, f"Missing fields: {missing}"
        assert not extra, f"Unexpected extra fields: {extra}"

    def test_all_fields_are_post_race(self):
        """ALL OddsTrifectaSchema fields have pre_race=False per D-04."""
        for name, info in OddsTrifectaSchema.model_fields.items():
            extra = info.json_schema_extra
            assert isinstance(extra, dict), (
                f"Field '{name}' json_schema_extra is not a dict: {type(extra)}"
            )
            assert extra.get("pre_race") is False, (
                f"Field '{name}' has pre_race={extra.get('pre_race')}, expected False"
            )
            assert extra.get("table") == "odds_trifecta", (
                f"Field '{name}' has table={extra.get('table')}, expected 'odds_trifecta'"
            )


class TestOddsTrifectaSchemaFieldTypes:
    """Verify OddsTrifectaSchema fields have correct Python types."""

    def test_race_id_is_non_optional_str(self):
        """race_id is the only non-Optional field."""
        info = OddsTrifectaSchema.model_fields["race_id"]
        assert info.annotation is str, (
            f"race_id should be str, got {info.annotation}"
        )
        assert info.is_required(), "race_id should be required"

    def test_all_trifecta_fields_are_optional(self):
        """All trifecta fields (except race_id) are Optional -- sparse coverage data."""
        optional_fields = self.EXPECTED_FIELDS - {"race_id"} if hasattr(self, 'EXPECTED_FIELDS') else set()
        # Use the class-level constant
        optional_fields = TestOddsTrifectaSchemaFields.EXPECTED_FIELDS - {"race_id"}
        from typing import get_args, get_origin

        for name in optional_fields:
            info = OddsTrifectaSchema.model_fields[name]
            origin = get_origin(info.annotation)
            args = get_args(info.annotation)
            assert origin is not None, (
                f"Field '{name}' should be Optional, got {info.annotation}"
            )
            assert int in args, (
                f"Field '{name}' Optional args should include int, got {args}"
            )


class TestOddsTrifectaSchemaOptionalFields:
    """Verify nullable fields accept None."""

    def test_trifecta_fields_accept_none(self):
        """All trifecta fields have defaults allowing None (sparse data coverage)."""
        optional_fields = TestOddsTrifectaSchemaFields.EXPECTED_FIELDS - {"race_id"}
        for name in optional_fields:
            field_info = OddsTrifectaSchema.model_fields[name]
            assert field_info.default is None, (
                f"Nullable field '{name}' default should be None, "
                f"got {field_info.default}"
            )
            assert not field_info.is_required(), (
                f"Nullable field '{name}' should not be required"
            )


class TestOddsTrifectaSchemaJsonSchema:
    """Verify model_json_schema() output for odds_trifecta table."""

    def test_model_json_schema_valid(self):
        """model_json_schema() produces valid JSON with all field properties."""
        schema = OddsTrifectaSchema.model_json_schema()
        assert "properties" in schema
        assert len(schema["properties"]) >= 16

        # Check representative fields
        assert "race_id" in schema["properties"]
        assert "trifecta1_odds" in schema["properties"]
        assert "trifecta3_popularity" in schema["properties"]

    def test_json_schema_all_post_race(self):
        """JSON schema shows all fields have pre_race=false."""
        schema = OddsTrifectaSchema.model_json_schema()
        props = schema["properties"]

        for name, prop in props.items():
            assert prop.get("pre_race") is False, (
                f"Field '{name}' in JSON schema has pre_race={prop.get('pre_race')}, "
                f"expected False"
            )
            assert prop.get("table") == "odds_trifecta", (
                f"Field '{name}' in JSON schema has table={prop.get('table')}, "
                f"expected 'odds_trifecta'"
            )

    def test_model_json_schema_roundtrip(self):
        """model_json_schema() output serializes to valid JSON string."""
        schema = OddsTrifectaSchema.model_json_schema()
        json_str = json.dumps(schema, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert "properties" in parsed
        assert len(parsed["properties"]) == len(schema["properties"])
