"""Tests for RaceSchema - standard-layer race table schema definition."""

import json

import pytest

from src.schemas.race import RaceSchema


class TestRaceSchemaFields:
    """Verify RaceSchema has all expected fields from Kaggle race_result.csv race-level columns."""

    # All expected field names based on RESEARCH.md Kaggle Column Analysis rows 2-42
    EXPECTED_FIELDS = {
        # Race identification and timing (rows 2-3, 7-8, 29, 31-32, 42)
        "race_id",
        "race_date",
        "meeting_num",
        "course_code",
        "course_name",
        "meeting_day",
        "race_condition",
        "race_number",
        "grade_revision",
        "race_name",
        "grade",
        "obstacle",
        # Course and surface details (rows 34-38)
        "surface",
        "surface_detail",
        "direction",
        "course_detail",
        "distance",
        # Conditions (rows 39-41)
        "weather",
        "track_condition",
        "track_condition_detail",
        # Timing
        "start_time",
        # 20 race flag columns (rows 9-28: レース記号/* prefix columns)
        "race_flag_handicap",
        "race_flag_age_restricted",
        "race_flag_filly_only",
        "race_flag_colt_only",
        "race_flag_gelding_only",
        "race_flag_mare_only",
        "race_flag_stallion_only",
        "race_flag_apprentice",
        "race_flag_amateur",
        "race_flag_female_jockey",
        "race_flag_young_horse",
        "race_flag_condition_race",
        "race_flag_special_weight",
        "race_flag_bonus_weight",
        "race_flag_stakes",
        "race_flag_graded_stakes",
        "race_flag_listed",
        "race_flag_open",
        "race_flag_maiden",
        "race_flag_allowance",
    }

    def test_race_schema_has_all_fields(self):
        """RaceSchema.model_fields contains all expected field names."""
        actual_fields = set(RaceSchema.model_fields.keys())
        missing = self.EXPECTED_FIELDS - actual_fields
        extra = actual_fields - self.EXPECTED_FIELDS
        assert not missing, f"Missing fields: {missing}"
        assert not extra, f"Unexpected extra fields: {extra}"

    def test_race_schema_all_pre_race(self):
        """Every field in RaceSchema has json_schema_extra with pre_race=True and table='race'."""
        for name, info in RaceSchema.model_fields.items():
            extra = info.json_schema_extra
            assert isinstance(extra, dict), (
                f"Field '{name}' json_schema_extra is not a dict: {type(extra)}"
            )
            assert extra.get("pre_race") is True, (
                f"Field '{name}' has pre_race={extra.get('pre_race')}, expected True"
            )
            assert extra.get("table") == "race", (
                f"Field '{name}' has table={extra.get('table')}, expected 'race'"
            )

    def test_race_schema_field_types(self):
        """RaceSchema fields have correct Python types."""
        from typing import Optional, get_args, get_origin

        # Non-nullable fields with expected base types
        non_nullable_str_fields = {
            "race_id",
            "race_date",
            "course_code",
            "course_name",
            "race_condition",
            "race_name",
            "surface",
            "direction",
            "start_time",
        }
        non_nullable_int_fields = {
            "meeting_num",
            "meeting_day",
            "race_number",
            "distance",
        }

        for name, info in RaceSchema.model_fields.items():
            annotation = info.annotation
            # Check if Optional
            origin = get_origin(annotation)
            is_optional = origin is Optional or (
                origin is type(None) | type(...) and type(None) in get_args(annotation)
            )
            # Simpler check: is Optional if Union with NoneType
            if origin is type(int | str | float | bool):  # skip for non-Union
                pass

            if name in non_nullable_str_fields:
                assert annotation is str, (
                    f"Field '{name}' type is {annotation}, expected str"
                )
            elif name in non_nullable_int_fields:
                assert annotation is int, (
                    f"Field '{name}' type is {annotation}, expected int"
                )

        # Nullable Optional fields
        nullable_fields = {
            "grade_revision": str,
            "grade": str,
            "obstacle": str,
            "surface_detail": str,
            "course_detail": str,
            "weather": str,
            "track_condition": str,
            "track_condition_detail": str,
        }

        for name, base_type in nullable_fields.items():
            info = RaceSchema.model_fields[name]
            annotation = info.annotation
            origin = get_origin(annotation)
            args = get_args(annotation)
            # Should be Optional[base_type] i.e. Union[base_type, None]
            assert origin is not None or annotation is not type(None), (
                f"Field '{name}' should be Optional[{base_type.__name__}]"
            )
            assert base_type in args, (
                f"Field '{name}' Optional args should include {base_type.__name__}, got {args}"
            )

        # Boolean flag fields should be Optional[bool]
        flag_fields = {f for f in self.EXPECTED_FIELDS if f.startswith("race_flag_")}
        for name in flag_fields:
            info = RaceSchema.model_fields[name]
            annotation = info.annotation
            origin = get_origin(annotation)
            args = get_args(annotation)
            assert origin is not None, (
                f"Field '{name}' should be Optional[bool], got {annotation}"
            )
            assert bool in args, (
                f"Field '{name}' Optional args should include bool, got {args}"
            )


class TestRaceSchemaOptionalFields:
    """Verify nullable fields accept None and non-nullable reject None."""

    def test_nullable_fields_accept_none(self):
        """Nullable Optional fields accept None without error."""
        nullable_fields = [
            "grade_revision",
            "grade",
            "obstacle",
            "surface_detail",
            "course_detail",
            "weather",
            "track_condition",
            "track_condition_detail",
            "race_flag_handicap",
            "race_flag_age_restricted",
        ]
        for name in nullable_fields:
            field_info = RaceSchema.model_fields[name]
            assert field_info.default is not None or field_info.is_required() is False, (
                f"Nullable field '{name}' should have default or not be required"
            )

    def test_non_nullable_fields_required(self):
        """Non-nullable fields are required (no default)."""
        required_fields = [
            "race_id",
            "race_date",
            "meeting_num",
            "course_code",
            "course_name",
            "surface",
            "direction",
            "distance",
            "start_time",
        ]
        for name in required_fields:
            field_info = RaceSchema.model_fields[name]
            assert field_info.is_required(), (
                f"Non-nullable field '{name}' should be required"
            )


class TestRaceSchemaJsonSchema:
    """Verify model_json_schema() output."""

    def test_model_json_schema_valid(self):
        """model_json_schema() produces valid JSON with all field properties."""
        schema = RaceSchema.model_json_schema()
        assert "properties" in schema
        assert len(schema["properties"]) >= 34

        # Check a few representative fields
        assert "race_id" in schema["properties"]
        assert "distance" in schema["properties"]
        assert "weather" in schema["properties"]
        assert "race_flag_handicap" in schema["properties"]

        # Check pre_race metadata appears in JSON schema
        race_id_prop = schema["properties"]["race_id"]
        # json_schema_extra keys should be present
        assert race_id_prop.get("pre_race") is True
        assert race_id_prop.get("table") == "race"

    def test_model_json_schema_roundtrip(self):
        """model_json_schema() output serializes to valid JSON string."""
        schema = RaceSchema.model_json_schema()
        json_str = json.dumps(schema, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert "properties" in parsed
        assert len(parsed["properties"]) == len(schema["properties"])
