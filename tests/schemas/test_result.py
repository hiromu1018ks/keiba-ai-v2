"""Tests for ResultSchema - standard-layer result table schema definition.

All fields in ResultSchema are post-race (pre_race=False) per CONTEXT.md
classification table. The result table captures race outcome data including
finish position, times, margins, corner positions, and prize money.
"""

import json

from src.schemas.result import ResultSchema


class TestResultSchemaFields:
    """Verify ResultSchema has all expected fields from Kaggle race_result.csv result-level columns."""

    # All expected field names based on RESEARCH.md Kaggle Column Analysis rows 43-44, 52-58, 66
    EXPECTED_FIELDS = {
        "horse_race_id",
        "race_id",
        "finish_position",
        "finish_note",
        "finish_time",
        "margin",
        "corner_1",
        "corner_2",
        "corner_3",
        "corner_4",
        "last_3f",
        "prize_money",
    }

    def test_result_schema_has_all_fields(self):
        """ResultSchema.model_fields contains all expected field names."""
        actual_fields = set(ResultSchema.model_fields.keys())
        missing = self.EXPECTED_FIELDS - actual_fields
        extra = actual_fields - self.EXPECTED_FIELDS
        assert not missing, f"Missing fields: {missing}"
        assert not extra, f"Unexpected extra fields: {extra}"

    def test_all_fields_are_post_race(self):
        """Every field in ResultSchema has json_schema_extra with pre_race=False and table='result'."""
        for name, info in ResultSchema.model_fields.items():
            extra = info.json_schema_extra
            assert isinstance(extra, dict), (
                f"Field '{name}' json_schema_extra is not a dict: {type(extra)}"
            )
            assert extra.get("pre_race") is False, (
                f"Field '{name}' has pre_race={extra.get('pre_race')}, expected False"
            )
            assert extra.get("table") == "result", (
                f"Field '{name}' has table={extra.get('table')}, expected 'result'"
            )


class TestResultSchemaFieldTypes:
    """Verify ResultSchema fields have correct Python types."""

    def test_finish_position_is_optional_int(self):
        """finish_position is Optional[int] -- handles 1.1% null rate and non-finishers per Pitfall #6."""
        info = ResultSchema.model_fields["finish_position"]
        from typing import get_args, get_origin

        origin = get_origin(info.annotation)
        args = get_args(info.annotation)
        assert origin is not None, (
            f"finish_position should be Optional[int], got {info.annotation}"
        )
        assert int in args, f"finish_position Optional args should include int, got {args}"

    def test_finish_note_is_optional_str(self):
        """finish_note is Optional[str] -- non-standard result indicators (中/取/失/除/再)."""
        info = ResultSchema.model_fields["finish_note"]
        from typing import get_args, get_origin

        origin = get_origin(info.annotation)
        args = get_args(info.annotation)
        assert origin is not None, (
            f"finish_note should be Optional[str], got {info.annotation}"
        )
        assert str in args, f"finish_note Optional args should include str, got {args}"

    def test_last_3f_is_optional_float(self):
        """last_3f is Optional[float] -- handles 4.8% null rate."""
        info = ResultSchema.model_fields["last_3f"]
        from typing import get_args, get_origin

        origin = get_origin(info.annotation)
        args = get_args(info.annotation)
        assert origin is not None, (
            f"last_3f should be Optional[float], got {info.annotation}"
        )
        assert float in args, f"last_3f Optional args should include float, got {args}"

    def test_non_nullable_fields(self):
        """Non-nullable fields have correct base types."""
        non_nullable = {
            "horse_race_id": str,
            "race_id": str,
        }
        for name, expected_type in non_nullable.items():
            info = ResultSchema.model_fields[name]
            assert info.annotation is expected_type, (
                f"Field '{name}' type is {info.annotation}, expected {expected_type}"
            )

    def test_nullable_fields_are_optional(self):
        """Nullable fields are Optional[T] with correct inner types."""
        nullable = {
            "finish_position": int,
            "finish_note": str,
            "finish_time": str,
            "margin": str,
            "corner_1": int,
            "corner_2": int,
            "corner_3": int,
            "corner_4": int,
            "last_3f": float,
            "prize_money": float,
        }
        from typing import get_args

        for name, base_type in nullable.items():
            info = ResultSchema.model_fields[name]
            args = get_args(info.annotation)
            assert base_type in args, (
                f"Field '{name}' Optional args should include {base_type.__name__}, "
                f"got {args}"
            )


class TestResultSchemaOptionalFields:
    """Verify nullable fields accept None."""

    def test_nullable_fields_accept_none(self):
        """Nullable Optional fields have defaults allowing None."""
        nullable_fields = [
            "finish_position",
            "finish_note",
            "finish_time",
            "margin",
            "corner_1",
            "corner_2",
            "corner_3",
            "corner_4",
            "last_3f",
            "prize_money",
        ]
        for name in nullable_fields:
            field_info = ResultSchema.model_fields[name]
            assert field_info.default is None, (
                f"Nullable field '{name}' default should be None, "
                f"got {field_info.default}"
            )
            assert not field_info.is_required(), (
                f"Nullable field '{name}' should not be required"
            )


class TestResultSchemaJsonSchema:
    """Verify model_json_schema() output for result table."""

    def test_model_json_schema_valid(self):
        """model_json_schema() produces valid JSON with all field properties."""
        schema = ResultSchema.model_json_schema()
        assert "properties" in schema
        assert len(schema["properties"]) >= 12

        # Check representative fields
        assert "horse_race_id" in schema["properties"]
        assert "finish_position" in schema["properties"]
        assert "last_3f" in schema["properties"]
        assert "prize_money" in schema["properties"]

    def test_json_schema_all_post_race(self):
        """JSON schema shows all fields have pre_race=false."""
        schema = ResultSchema.model_json_schema()
        props = schema["properties"]

        for name, prop in props.items():
            assert prop.get("pre_race") is False, (
                f"Field '{name}' in JSON schema has pre_race={prop.get('pre_race')}, "
                f"expected False"
            )
            assert prop.get("table") == "result", (
                f"Field '{name}' in JSON schema has table={prop.get('table')}, "
                f"expected 'result'"
            )

    def test_model_json_schema_roundtrip(self):
        """model_json_schema() output serializes to valid JSON string."""
        schema = ResultSchema.model_json_schema()
        json_str = json.dumps(schema, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert "properties" in parsed
        assert len(parsed["properties"]) == len(schema["properties"])
