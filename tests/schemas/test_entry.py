"""Tests for EntrySchema - standard-layer entry table with mixed pre/post-race classification."""

import json
from typing import get_args

from src.schemas.entry import EntrySchema


class TestEntrySchemaFields:
    """Verify EntrySchema has all expected fields from Kaggle race_result.csv entry-level columns."""

    # All expected field names based on RESEARCH.md rows 1, 45-51, 59-65
    EXPECTED_FIELDS = {
        "horse_race_id",
        "race_id",
        "bracket_num",
        "horse_number",
        "horse_name",
        "sex",
        "age",
        "weight_assigned",
        "jockey",
        "trainer",
        "horse_weight",
        "weight_change",
        "region",
        "owner",
        "popularity",
        "win_odds",
    }

    # Fields that are post-race per D-03 (not usable in feature layer)
    POST_RACE_FIELDS = {"popularity", "win_odds"}

    def test_entry_schema_has_all_fields(self):
        """EntrySchema.model_fields contains all expected field names."""
        actual_fields = set(EntrySchema.model_fields.keys())
        missing = self.EXPECTED_FIELDS - actual_fields
        extra = actual_fields - self.EXPECTED_FIELDS
        assert not missing, f"Missing fields: {missing}"
        assert not extra, f"Unexpected extra fields: {extra}"

    def test_popularity_is_post_race(self):
        """popularity field has json_schema_extra pre_race=False per D-03."""
        info = EntrySchema.model_fields["popularity"]
        extra = info.json_schema_extra
        assert isinstance(extra, dict)
        assert extra.get("pre_race") is False, (
            f"popularity should be pre_race=False, got {extra.get('pre_race')}"
        )

    def test_win_odds_is_post_race(self):
        """win_odds field has json_schema_extra pre_race=False per D-03."""
        info = EntrySchema.model_fields["win_odds"]
        extra = info.json_schema_extra
        assert isinstance(extra, dict)
        assert extra.get("pre_race") is False, (
            f"win_odds should be pre_race=False, got {extra.get('pre_race')}"
        )

    def test_other_fields_are_pre_race(self):
        """All fields except popularity and win_odds have pre_race=True."""
        pre_race_fields = self.EXPECTED_FIELDS - self.POST_RACE_FIELDS
        for name in pre_race_fields:
            info = EntrySchema.model_fields[name]
            extra = info.json_schema_extra
            assert isinstance(extra, dict), (
                f"Field '{name}' json_schema_extra is not a dict"
            )
            assert extra.get("pre_race") is True, (
                f"Field '{name}' has pre_race={extra.get('pre_race')}, expected True"
            )
            assert extra.get("table") == "entry", (
                f"Field '{name}' has table={extra.get('table')}, expected 'entry'"
            )

    def test_horse_weight_is_pre_race(self):
        """horse_weight has pre_race=True per D-05 (measured on race day before start)."""
        info = EntrySchema.model_fields["horse_weight"]
        extra = info.json_schema_extra
        assert isinstance(extra, dict)
        assert extra.get("pre_race") is True, (
            f"horse_weight should be pre_race=True per D-05, got {extra.get('pre_race')}"
        )

    def test_weight_change_is_pre_race(self):
        """weight_change has pre_race=True per D-05 (measured on race day before start)."""
        info = EntrySchema.model_fields["weight_change"]
        extra = info.json_schema_extra
        assert isinstance(extra, dict)
        assert extra.get("pre_race") is True, (
            f"weight_change should be pre_race=True per D-05, got {extra.get('pre_race')}"
        )


class TestEntrySchemaFieldTypes:
    """Verify EntrySchema fields have correct Python types."""

    def test_non_nullable_fields(self):
        """Non-nullable fields have correct base types."""
        non_nullable = {
            "horse_race_id": str,
            "race_id": str,
            "bracket_num": int,
            "horse_number": int,
            "horse_name": str,
            "sex": str,
            "age": int,
            "weight_assigned": float,
            "jockey": str,
            "trainer": str,
            "owner": str,
        }
        for name, expected_type in non_nullable.items():
            info = EntrySchema.model_fields[name]
            assert info.annotation is expected_type, (
                f"Field '{name}' type is {info.annotation}, expected {expected_type}"
            )

    def test_nullable_fields_are_optional(self):
        """Nullable fields are Optional[T] with correct inner types."""
        nullable = {
            "horse_weight": int,
            "weight_change": int,
            "region": str,
            "popularity": int,
            "win_odds": float,
        }
        for name, base_type in nullable.items():
            info = EntrySchema.model_fields[name]
            args = get_args(info.annotation)
            assert base_type in args, (
                f"Field '{name}' Optional args should include {base_type.__name__}, "
                f"got {args}"
            )


class TestEntrySchemaOptionalFields:
    """Verify nullable fields accept None."""

    def test_nullable_fields_accept_none(self):
        """Nullable Optional fields have defaults allowing None."""
        nullable_fields = [
            "horse_weight",
            "weight_change",
            "region",
            "popularity",
            "win_odds",
        ]
        for name in nullable_fields:
            field_info = EntrySchema.model_fields[name]
            assert field_info.default is None, (
                f"Nullable field '{name}' default should be None, "
                f"got {field_info.default}"
            )
            assert not field_info.is_required(), (
                f"Nullable field '{name}' should not be required"
            )


class TestEntrySchemaJsonSchema:
    """Verify model_json_schema() output for entry table."""

    def test_model_json_schema_valid(self):
        """model_json_schema() produces valid JSON with all field properties."""
        schema = EntrySchema.model_json_schema()
        assert "properties" in schema
        assert len(schema["properties"]) >= 16

        # Check representative fields
        assert "horse_race_id" in schema["properties"]
        assert "popularity" in schema["properties"]
        assert "win_odds" in schema["properties"]

    def test_json_schema_has_mixed_pre_race(self):
        """JSON schema contains both pre_race=True and pre_race=False fields."""
        schema = EntrySchema.model_json_schema()
        props = schema["properties"]

        # popularity and win_odds should be pre_race=False
        assert props["popularity"].get("pre_race") is False
        assert props["win_odds"].get("pre_race") is False

        # horse_name should be pre_race=True
        assert props["horse_name"].get("pre_race") is True

        # horse_weight should be pre_race=True (D-05)
        assert props["horse_weight"].get("pre_race") is True

    def test_model_json_schema_roundtrip(self):
        """model_json_schema() output serializes to valid JSON string."""
        schema = EntrySchema.model_json_schema()
        json_str = json.dumps(schema, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert "properties" in parsed
        assert len(parsed["properties"]) == len(schema["properties"])
