"""Tests for PayoffSchema - standard-layer payoff table contract schema.

PayoffSchema defines the contract for future phases (Phase 5 scraping, Phase 8
EV calculation). No direct Kaggle source exists for full trifecta payoff data.
All fields are post-race (pre_race=False).
"""

import json

from src.schemas.payoff import PayoffSchema


class TestPayoffSchemaFields:
    """Verify PayoffSchema has all expected fields for the payoff contract."""

    EXPECTED_FIELDS = {
        "race_id",
        "combo_1",
        "combo_2",
        "combo_3",
        "odds",
        "payoff_amount",
    }

    def test_payoff_schema_has_all_fields(self):
        """PayoffSchema.model_fields contains all expected field names."""
        actual_fields = set(PayoffSchema.model_fields.keys())
        missing = self.EXPECTED_FIELDS - actual_fields
        extra = actual_fields - self.EXPECTED_FIELDS
        assert not missing, f"Missing fields: {missing}"
        assert not extra, f"Unexpected extra fields: {extra}"

    def test_all_fields_are_post_race(self):
        """ALL PayoffSchema fields have pre_race=False."""
        for name, info in PayoffSchema.model_fields.items():
            extra = info.json_schema_extra
            assert isinstance(extra, dict), (
                f"Field '{name}' json_schema_extra is not a dict: {type(extra)}"
            )
            assert extra.get("pre_race") is False, (
                f"Field '{name}' has pre_race={extra.get('pre_race')}, expected False"
            )
            assert extra.get("table") == "payoff", (
                f"Field '{name}' has table={extra.get('table')}, expected 'payoff'"
            )


class TestPayoffSchemaFieldTypes:
    """Verify PayoffSchema fields have correct Python types."""

    def test_non_nullable_fields(self):
        """Non-nullable fields have correct base types."""
        non_nullable = {
            "race_id": str,
            "combo_1": int,
            "combo_2": int,
            "combo_3": int,
        }
        for name, expected_type in non_nullable.items():
            info = PayoffSchema.model_fields[name]
            assert info.annotation is expected_type, (
                f"Field '{name}' type is {info.annotation}, expected {expected_type}"
            )

    def test_nullable_fields_are_optional(self):
        """Nullable fields are Optional[T] with correct inner types."""
        nullable = {
            "odds": float,
            "payoff_amount": int,
        }
        from typing import get_args

        for name, base_type in nullable.items():
            info = PayoffSchema.model_fields[name]
            args = get_args(info.annotation)
            assert base_type in args, (
                f"Field '{name}' Optional args should include {base_type.__name__}, "
                f"got {args}"
            )


class TestPayoffSchemaJsonSchema:
    """Verify model_json_schema() output for payoff table."""

    def test_model_json_schema_valid(self):
        """model_json_schema() produces valid JSON with all field properties."""
        schema = PayoffSchema.model_json_schema()
        assert "properties" in schema
        assert len(schema["properties"]) >= 6

        # Check representative fields
        assert "race_id" in schema["properties"]
        assert "combo_1" in schema["properties"]
        assert "odds" in schema["properties"]
        assert "payoff_amount" in schema["properties"]

    def test_json_schema_all_post_race(self):
        """JSON schema shows all fields have pre_race=false."""
        schema = PayoffSchema.model_json_schema()
        props = schema["properties"]

        for name, prop in props.items():
            assert prop.get("pre_race") is False, (
                f"Field '{name}' in JSON schema has pre_race={prop.get('pre_race')}, "
                f"expected False"
            )
            assert prop.get("table") == "payoff", (
                f"Field '{name}' in JSON schema has table={prop.get('table')}, "
                f"expected 'payoff'"
            )

    def test_model_json_schema_roundtrip(self):
        """model_json_schema() output serializes to valid JSON string."""
        schema = PayoffSchema.model_json_schema()
        json_str = json.dumps(schema, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert "properties" in parsed
        assert len(parsed["properties"]) == len(schema["properties"])
