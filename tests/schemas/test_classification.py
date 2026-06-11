"""Cross-table classification verification tests.

Validates:
- All 66 Kaggle columns from race_result.csv are mapped 1-to-1 to schema fields
- No orphan schema fields exist (except PayoffSchema which is a contract table)
- Post-race column classification matches D-03/D-04/D-05 decisions
- horse_weight/weight_change are pre-race per D-05
- No field name collisions across tables except race_id and horse_race_id
- Total field count across all 5 schemas >= 80

Per DATA-01 SC2: Machine-verifiable 1-to-1 mapping of all Kaggle columns.
"""

from src.schemas.audit import get_post_race_columns
from src.schemas.entry import EntrySchema
from src.schemas.odds_trifecta import OddsTrifectaSchema
from src.schemas.payoff import PayoffSchema
from src.schemas.race import RaceSchema
from src.schemas.result import ResultSchema

# ---------------------------------------------------------------------------
# KAGGLE_COLUMN_MAP: Authoritative 1-to-1 mapping of all 66 Japanese column
# names from race_result.csv to (table_name, english_field_name) tuples.
#
# Source: RESEARCH.md "Kaggle Column Analysis" table (rows 1-66).
# This dict is the single source of truth for the Kaggle -> standard mapping.
# ---------------------------------------------------------------------------
KAGGLE_COLUMN_MAP: dict[str, tuple[str, str]] = {
    # Row 1: Identification
    "レース馬番ID": ("entry", "horse_race_id"),
    # Row 2: Race identification
    "レースID": ("race", "race_id"),
    # Row 3: Race date
    "レース日付": ("race", "race_date"),
    # Row 4: Meeting number
    "開催回数": ("race", "meeting_num"),
    # Row 5: Course code
    "競馬場コード": ("race", "course_code"),
    # Row 6: Course name
    "競馬場名": ("race", "course_name"),
    # Row 7: Meeting day
    "開催日数": ("race", "meeting_day"),
    # Row 8: Race condition
    "競争条件": ("race", "race_condition"),
    # Rows 9-28: 20 race flag columns (レース記号/* prefix)
    "レース記号/ハンデ": ("race", "race_flag_handicap"),
    "レース記号/年齢": ("race", "race_flag_age_restricted"),
    "レース記号/牝": ("race", "race_flag_filly_only"),
    "レース記号/牡": ("race", "race_flag_colt_only"),
    "レース記号/セ": ("race", "race_flag_gelding_only"),
    "レース記号/牝馬": ("race", "race_flag_mare_only"),
    "レース記号/種牡馬": ("race", "race_flag_stallion_only"),
    "レース記号/見習": ("race", "race_flag_apprentice"),
    "レース記号/アマ": ("race", "race_flag_amateur"),
    "レース記号/女性": ("race", "race_flag_female_jockey"),
    "レース記号/若駒": ("race", "race_flag_young_horse"),
    "レース記号/条件": ("race", "race_flag_condition_race"),
    "レース記号/別定": ("race", "race_flag_special_weight"),
    "レース記号/定量": ("race", "race_flag_bonus_weight"),
    "レース記号/特別": ("race", "race_flag_stakes"),
    "レース記号/重賞": ("race", "race_flag_graded_stakes"),
    "レース記号/リステッド": ("race", "race_flag_listed"),
    "レース記号/オープン": ("race", "race_flag_open"),
    "レース記号/未勝利": ("race", "race_flag_maiden"),
    "レース記号/認定": ("race", "race_flag_allowance"),
    # Row 29: Race number
    "レース番号": ("race", "race_number"),
    # Row 30: Grade revision
    "重賞回次": ("race", "grade_revision"),
    # Row 31: Race name
    "レース名": ("race", "race_name"),
    # Row 32: Grade
    "リステッド・重賞競走": ("race", "grade"),
    # Row 33: Obstacle
    "障害区分": ("race", "obstacle"),
    # Row 34: Surface
    "芝・ダート区分": ("race", "surface"),
    # Row 35: Surface detail
    "芝・ダート区分2": ("race", "surface_detail"),
    # Row 36: Direction
    "右左回り・直線区分": ("race", "direction"),
    # Row 37: Course detail
    "内・外・襷区分": ("race", "course_detail"),
    # Row 38: Distance
    "距離(m)": ("race", "distance"),
    # Row 39: Weather
    "天候": ("race", "weather"),
    # Row 40: Track condition
    "馬場状態1": ("race", "track_condition"),
    # Row 41: Track condition detail
    "馬場状態2": ("race", "track_condition_detail"),
    # Row 42: Start time
    "発走時刻": ("race", "start_time"),
    # Row 43: Finish position (result)
    "着順": ("result", "finish_position"),
    # Row 44: Finish note (result)
    "着順注記": ("result", "finish_note"),
    # Row 45: Bracket number (entry)
    "枠番": ("entry", "bracket_num"),
    # Row 46: Horse number (entry)
    "馬番": ("entry", "horse_number"),
    # Row 47: Horse name (entry)
    "馬名": ("entry", "horse_name"),
    # Row 48: Sex (entry)
    "性別": ("entry", "sex"),
    # Row 49: Age (entry)
    "馬齢": ("entry", "age"),
    # Row 50: Weight assigned (entry)
    "斤量": ("entry", "weight_assigned"),
    # Row 51: Jockey (entry)
    "騎手": ("entry", "jockey"),
    # Row 52: Finish time (result)
    "タイム": ("result", "finish_time"),
    # Row 53: Margin (result)
    "着差": ("result", "margin"),
    # Row 54: Corner 1 (result)
    "1コーナー": ("result", "corner_1"),
    # Row 55: Corner 2 (result)
    "2コーナー": ("result", "corner_2"),
    # Row 56: Corner 3 (result)
    "3コーナー": ("result", "corner_3"),
    # Row 57: Corner 4 (result)
    "4コーナー": ("result", "corner_4"),
    # Row 58: Last 3f (result)
    "上り": ("result", "last_3f"),
    # Row 59: Win odds (entry, post-race per D-03)
    "単勝": ("entry", "win_odds"),
    # Row 60: Popularity (entry, post-race per D-03)
    "人気": ("entry", "popularity"),
    # Row 61: Horse weight (entry, pre-race per D-05)
    "馬体重": ("entry", "horse_weight"),
    # Row 62: Weight change (entry, pre-race per D-05)
    "場体重増減": ("entry", "weight_change"),
    # Row 63: Region (entry)
    "東西・外国・地方区分": ("entry", "region"),
    # Row 64: Trainer (entry)
    "調教師": ("entry", "trainer"),
    # Row 65: Owner (entry)
    "馬主": ("entry", "owner"),
    # Row 66: Prize money (result)
    "賞金(万円)": ("result", "prize_money"),
}

# Table name -> schema class mapping for dynamic lookup
TABLE_TO_SCHEMA: dict[str, type] = {
    "race": RaceSchema,
    "entry": EntrySchema,
    "result": ResultSchema,
    "odds_trifecta": OddsTrifectaSchema,
    "payoff": PayoffSchema,
}


class TestKaggleColumnMapping:
    """Verify 1-to-1 mapping of all 66 Kaggle columns to schema fields."""

    def test_kaggle_column_1to1_mapping(self) -> None:
        """Every Kaggle column maps to exactly one field in exactly one table.

        For each (jp_name, (table, eng_name)) in KAGGLE_COLUMN_MAP, verify that
        eng_name is a valid field name in the corresponding schema class.
        This ensures all 66 race_result.csv columns are accounted for.
        """
        assert len(KAGGLE_COLUMN_MAP) == 66, (
            f"Expected 66 Kaggle columns, got {len(KAGGLE_COLUMN_MAP)}"
        )

        errors: list[str] = []
        for jp_name, (table_name, eng_name) in KAGGLE_COLUMN_MAP.items():
            schema_class = TABLE_TO_SCHEMA[table_name]
            if eng_name not in schema_class.model_fields:
                errors.append(
                    f"{jp_name} -> ({table_name}, {eng_name}): "
                    f"'{eng_name}' not in {schema_class.__name__}.model_fields"
                )

        assert errors == [], (
            f"{len(errors)} unmapped Kaggle columns:\n" + "\n".join(errors)
        )

    def test_no_unmapped_schema_fields(self) -> None:
        """No schema field exists without a Kaggle source (except expected exceptions).

        KAGGLE_COLUMN_MAP covers the 66 columns from race_result.csv. Some fields
        are legitimately not in the map:
        - PayoffSchema: contract table, no Kaggle source at all
        - OddsTrifectaSchema: sourced from odds.csv, not race_result.csv
        - Foreign keys (race_id, horse_race_id) appear in multiple tables but
          are mapped only once in KAGGLE_COLUMN_MAP (to their canonical table)
        """
        # Collect all English field names from KAGGLE_COLUMN_MAP, grouped by table
        mapped_fields: dict[str, set[str]] = {}
        for _jp_name, (table_name, eng_name) in KAGGLE_COLUMN_MAP.items():
            mapped_fields.setdefault(table_name, set()).add(eng_name)

        # Foreign keys that appear in multiple tables but mapped once
        foreign_keys = {"race_id", "horse_race_id"}

        # Tables with non-race_result.csv sources (excluded from reverse check)
        non_race_result_tables = {"payoff", "odds_trifecta"}

        errors: list[str] = []
        for table_name, schema_class in TABLE_TO_SCHEMA.items():
            if table_name in non_race_result_tables:
                continue

            actual_fields = set()
            for field_name, info in schema_class.model_fields.items():
                extra = info.json_schema_extra
                if isinstance(extra, dict) and extra.get("table") == table_name:
                    actual_fields.add(field_name)

            expected_fields = mapped_fields.get(table_name, set())

            # Fields in schema but not in KAGGLE_COLUMN_MAP
            # Foreign keys in non-canonical tables are expected to be unmapped
            unmapped = actual_fields - expected_fields - foreign_keys
            if unmapped:
                errors.append(
                    f"{schema_class.__name__} has unmapped fields: {sorted(unmapped)}"
                )

            # Fields in KAGGLE_COLUMN_MAP but not in schema
            missing = expected_fields - actual_fields
            if missing:
                errors.append(
                    f"{schema_class.__name__} missing mapped fields: {sorted(missing)}"
                )

        assert errors == [], (
            f"{len(errors)} schema/field mismatches:\n" + "\n".join(errors)
        )

    def test_post_race_columns_match_decisions(self) -> None:
        """Post-race columns match D-03, D-04, D-05 exactly.

        D-03: EntrySchema popularity and win_odds are post-race.
        D-04: All OddsTrifectaSchema fields (except race_id FK) are post-race.
        D-05: horse_weight and weight_change are pre-race (NOT post-race).
        """
        # D-03: EntrySchema post-race columns = {popularity, win_odds}
        entry_post_race = get_post_race_columns(EntrySchema)
        assert entry_post_race == {"popularity", "win_odds"}, (
            f"D-03 violation: EntrySchema post-race columns = {entry_post_race}, "
            f"expected {{'popularity', 'win_odds'}}"
        )

        # D-04: All OddsTrifectaSchema fields are post-race (pre_race=False).
        # The schema consistently marks ALL fields including race_id as post-race
        # since the entire odds table captures post-race information.
        odds_post_race = get_post_race_columns(OddsTrifectaSchema)
        assert len(odds_post_race) == 16, (
            f"D-04 violation: OddsTrifectaSchema has {len(odds_post_race)} post-race fields, "
            f"expected 16 (all fields)"
        )
        assert odds_post_race == set(OddsTrifectaSchema.model_fields.keys()), (
            "D-04 violation: Not all OddsTrifectaSchema fields are post-race"
        )

        # ResultSchema: all fields are post-race
        result_post_race = get_post_race_columns(ResultSchema)
        assert len(result_post_race) == 12, (
            f"ResultSchema has {len(result_post_race)} post-race fields, expected 12"
        )

    def test_horse_weight_is_pre_race(self) -> None:
        """horse_weight and weight_change are pre-race per D-05."""
        entry_post_race = get_post_race_columns(EntrySchema)
        assert "horse_weight" not in entry_post_race, (
            "D-05 violation: horse_weight is post-race, should be pre-race"
        )
        assert "weight_change" not in entry_post_race, (
            "D-05 violation: weight_change is post-race, should be pre-race"
        )

        # Explicitly check pre_race metadata
        for field_name in ("horse_weight", "weight_change"):
            info = EntrySchema.model_fields[field_name]
            extra = info.json_schema_extra
            assert isinstance(extra, dict) and extra.get("pre_race") is True, (
                f"D-05 violation: {field_name} pre_race={extra}, expected True"
            )

    def test_no_field_name_collision(self) -> None:
        """No field name appears in multiple tables except race_id and horse_race_id.

        race_id appears in race, entry, result, odds_trifecta, payoff (foreign key).
        horse_race_id appears in entry and result (1-to-1 join key per D-09).
        All other field names must be unique to a single table.
        """
        # Collect field_name -> [table_names] mapping
        field_tables: dict[str, list[str]] = {}
        for table_name, schema_class in TABLE_TO_SCHEMA.items():
            for field_name, info in schema_class.model_fields.items():
                extra = info.json_schema_extra
                if isinstance(extra, dict) and extra.get("table") == table_name:
                    field_tables.setdefault(field_name, []).append(table_name)

        # Allowed duplicates (foreign keys)
        allowed_duplicates = {"race_id", "horse_race_id"}

        collisions = {
            name: tables
            for name, tables in field_tables.items()
            if len(tables) > 1 and name not in allowed_duplicates
        }

        assert collisions == {}, (
            f"Field name collisions found: {collisions}"
        )

    def test_total_field_coverage(self) -> None:
        """Total field count across all 5 schemas >= 80.

        66 Kaggle columns from race_result.csv + 16 OddsTrifectaSchema fields
        from odds.csv + 6 PayoffSchema contract fields = 91 fields total.
        The threshold of 80 ensures comprehensive coverage.
        """
        total = sum(
            len(schema_class.model_fields)
            for schema_class in TABLE_TO_SCHEMA.values()
        )
        assert total >= 80, (
            f"Total field count = {total}, expected >= 80 "
            f"(66 Kaggle + 16 odds_trifecta + 6 payoff = 88 minimum)"
        )
