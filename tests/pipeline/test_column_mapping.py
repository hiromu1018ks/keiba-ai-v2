"""Unit tests for column mapping dicts and helper functions.

Validates:
- KAGGLE_COLUMN_MAP has exactly 66 entries, all (table, field) resolve to schema fields
- ODDS_COLUMN_MAP has exactly 15 entries for trifecta columns from odds.csv
- FLAG_COLUMNS has exactly 20 entries matching actual CSV headers
- DTYPE_SPEC has exactly 23 entries (20 flags + 3 mixed-type columns)
- TABLE_TO_SCHEMA maps each table name to the correct schema class
- get_columns_for_table() returns correct subsets
- Every KAGGLE_COLUMN_MAP Japanese column name is in the expected set of 66 names
"""

from src.schemas.entry import EntrySchema
from src.schemas.odds_trifecta import OddsTrifectaSchema
from src.schemas.payoff import PayoffSchema
from src.schemas.race import RaceSchema
from src.schemas.result import ResultSchema

from src.pipeline.column_mapping import (
    DTYPE_SPEC,
    FLAG_COLUMNS,
    KAGGLE_COLUMN_MAP,
    ODDS_COLUMN_MAP,
    TABLE_TO_SCHEMA,
    get_columns_for_table,
)


class TestKaggleColumnMapping:
    """Verify all 66 Kaggle race_result.csv column mappings."""

    # The expected set of 66 Japanese column names from the actual CSV header.
    # Rows 1-8 are standard columns, rows 9-28 are flag columns, rows 29-66 are
    # the remaining standard columns. The 20 flag columns use the ACTUAL CSV
    # header names (with parentheses/brackets), not the shortened test names.
    EXPECTED_JP_NAMES: set[str] = {
        # Row 1: Identification
        "レース馬番ID",
        # Row 2-8: Race identification columns
        "レースID",
        "レース日付",
        "開催回数",
        "競馬場コード",
        "競馬場名",
        "開催日数",
        "競争条件",
        # Rows 9-28: 20 race flag columns (actual CSV headers)
        "レース記号/[抽]",
        "レース記号/(馬齢)",
        "レース記号/牝",
        "レース記号/(父)",
        "レース記号/(別定)",
        "レース記号/(混)",
        "レース記号/(ハンデ)",
        "レース記号/(抽)",
        "レース記号/(市)",
        "レース記号/(定量)",
        "レース記号/牡",
        "レース記号/関東配布馬",
        "レース記号/(指)",
        "レース記号/関西配布馬",
        "レース記号/九州産馬",
        "レース記号/見習騎手",
        "レース記号/せん",
        "レース記号/(国際)",
        "レース記号/[指]",
        "レース記号/(特指)",
        # Rows 29-42: Remaining race columns
        "レース番号",
        "重賞回次",
        "レース名",
        "リステッド・重賞競走",
        "障害区分",
        "芝・ダート区分",
        "芝・ダート区分2",
        "右左回り・直線区分",
        "内・外・襷区分",
        "距離(m)",
        "天候",
        "馬場状態1",
        "馬場状態2",
        "発走時刻",
        # Rows 43-44: Result columns
        "着順",
        "着順注記",
        # Rows 45-51: Entry columns
        "枠番",
        "馬番",
        "馬名",
        "性別",
        "馬齢",
        "斤量",
        "騎手",
        # Rows 52-58: Result columns
        "タイム",
        "着差",
        "1コーナー",
        "2コーナー",
        "3コーナー",
        "4コーナー",
        "上り",
        # Rows 59-60: Entry (post-race) columns
        "単勝",
        "人気",
        # Rows 61-66: Entry/Result columns
        "馬体重",
        "場体重増減",
        "東西・外国・地方区分",
        "調教師",
        "馬主",
        "賞金(万円)",
    }

    def test_kaggle_column_map_has_66_entries(self) -> None:
        """KAGGLE_COLUMN_MAP contains exactly 66 entries (one per CSV column)."""
        assert len(KAGGLE_COLUMN_MAP) == 66, (
            f"Expected 66 entries in KAGGLE_COLUMN_MAP, got {len(KAGGLE_COLUMN_MAP)}"
        )

    def test_every_mapping_resolves_to_schema_field(self) -> None:
        """Every (table, field) in KAGGLE_COLUMN_MAP exists in the schema class."""
        errors: list[str] = []
        for jp_name, (table_name, eng_name) in KAGGLE_COLUMN_MAP.items():
            schema_class = TABLE_TO_SCHEMA[table_name]
            if eng_name not in schema_class.model_fields:
                errors.append(
                    f"{jp_name} -> ({table_name}, {eng_name}): "
                    f"'{eng_name}' not in {schema_class.__name__}.model_fields"
                )

        assert errors == [], (
            f"{len(errors)} unmapped columns:\n" + "\n".join(errors)
        )

    def test_all_jp_names_match_expected_set(self) -> None:
        """Every Japanese column name in KAGGLE_COLUMN_MAP is in the expected 66-name set."""
        actual_names = set(KAGGLE_COLUMN_MAP.keys())
        missing = self.EXPECTED_JP_NAMES - actual_names
        extra = actual_names - self.EXPECTED_JP_NAMES

        errors: list[str] = []
        if missing:
            errors.append(f"Missing from KAGGLE_COLUMN_MAP: {sorted(missing)}")
        if extra:
            errors.append(f"Unexpected in KAGGLE_COLUMN_MAP: {sorted(extra)}")

        assert errors == [], "\n".join(errors)


class TestOddsColumnMapping:
    """Verify the 15 trifecta column mappings from odds.csv."""

    EXPECTED_ODDS_JP_NAMES: set[str] = {
        "三連複1_組合せ1", "三連複1_組合せ2", "三連複1_組合せ3",
        "三連複1_オッズ", "三連複1_人気",
        "三連複2_組合せ1", "三連複2_組合せ2", "三連複2_組合せ3",
        "三連複2_オッズ", "三連複2_人気",
        "三連複3_組合せ1", "三連複3_組合せ2", "三連複3_組合せ3",
        "三連複3_オッズ", "三連複3_人気",
    }

    def test_odds_column_map_has_15_entries(self) -> None:
        """ODDS_COLUMN_MAP contains exactly 15 entries."""
        assert len(ODDS_COLUMN_MAP) == 15, (
            f"Expected 15 entries in ODDS_COLUMN_MAP, got {len(ODDS_COLUMN_MAP)}"
        )

    def test_odds_jp_names_match_expected(self) -> None:
        """Every key in ODDS_COLUMN_MAP matches the expected 15 Japanese names."""
        actual_keys = set(ODDS_COLUMN_MAP.keys())
        missing = self.EXPECTED_ODDS_JP_NAMES - actual_keys
        extra = actual_keys - self.EXPECTED_ODDS_JP_NAMES

        errors: list[str] = []
        if missing:
            errors.append(f"Missing from ODDS_COLUMN_MAP: {sorted(missing)}")
        if extra:
            errors.append(f"Unexpected in ODDS_COLUMN_MAP: {sorted(extra)}")

        assert errors == [], "\n".join(errors)

    def test_every_odds_mapping_resolves_to_schema_field(self) -> None:
        """Every value in ODDS_COLUMN_MAP exists in OddsTrifectaSchema.model_fields."""
        errors: list[str] = []
        for jp_name, eng_name in ODDS_COLUMN_MAP.items():
            if eng_name not in OddsTrifectaSchema.model_fields:
                errors.append(
                    f"{jp_name} -> {eng_name}: "
                    f"'{eng_name}' not in OddsTrifectaSchema.model_fields"
                )

        assert errors == [], (
            f"{len(errors)} unmapped odds columns:\n" + "\n".join(errors)
        )


class TestDtypeSpec:
    """Verify FLAG_COLUMNS and DTYPE_SPEC for CSV dtype handling."""

    EXPECTED_FLAG_PREFIX = "レース記号/"

    def test_flag_columns_has_20_entries(self) -> None:
        """FLAG_COLUMNS list has exactly 20 entries."""
        assert len(FLAG_COLUMNS) == 20, (
            f"Expected 20 FLAG_COLUMNS, got {len(FLAG_COLUMNS)}"
        )

    def test_every_flag_column_starts_with_prefix(self) -> None:
        """Every flag column name starts with 'レース記号/'."""
        errors: list[str] = []
        for col_name in FLAG_COLUMNS:
            if not col_name.startswith(self.EXPECTED_FLAG_PREFIX):
                errors.append(
                    f"Flag column '{col_name}' does not start with "
                    f"'{self.EXPECTED_FLAG_PREFIX}'"
                )

        assert errors == [], (
            f"{len(errors)} flag columns without expected prefix:\n"
            + "\n".join(errors)
        )

    def test_dtype_spec_has_23_entries(self) -> None:
        """DTYPE_SPEC has exactly 23 entries (20 flags + 3 mixed-type optional)."""
        assert len(DTYPE_SPEC) == 23, (
            f"Expected 23 entries in DTYPE_SPEC, got {len(DTYPE_SPEC)}"
        )

    def test_dtype_spec_covers_all_flag_columns(self) -> None:
        """DTYPE_SPEC contains all 20 FLAG_COLUMNS with dtype=str."""
        errors: list[str] = []
        for flag_col in FLAG_COLUMNS:
            if flag_col not in DTYPE_SPEC:
                errors.append(f"FLAG_COLUMN '{flag_col}' not in DTYPE_SPEC")
            elif DTYPE_SPEC[flag_col] is not str:
                errors.append(
                    f"DTYPE_SPEC['{flag_col}'] = {DTYPE_SPEC[flag_col]}, expected str"
                )

        assert errors == [], (
            f"{len(errors)} flag columns missing or wrong dtype:\n"
            + "\n".join(errors)
        )

    def test_dtype_spec_includes_mixed_type_columns(self) -> None:
        """DTYPE_SPEC includes the 3 mixed-type optional columns as str."""
        mixed_type_cols = {"芝・ダート区分2", "内・外・襷区分", "馬場状態2"}
        for col in mixed_type_cols:
            assert col in DTYPE_SPEC, f"'{col}' not in DTYPE_SPEC"
            assert DTYPE_SPEC[col] is str, (
                f"DTYPE_SPEC['{col}'] = {DTYPE_SPEC[col]}, expected str"
            )


class TestHelperFunctions:
    """Verify TABLE_TO_SCHEMA and get_columns_for_table()."""

    def test_table_to_schema_maps_5_tables(self) -> None:
        """TABLE_TO_SCHEMA maps exactly 5 table names to schema classes."""
        assert len(TABLE_TO_SCHEMA) == 5, (
            f"Expected 5 entries in TABLE_TO_SCHEMA, got {len(TABLE_TO_SCHEMA)}"
        )

    def test_table_to_schema_maps_correctly(self) -> None:
        """TABLE_TO_SCHEMA maps each table name to the correct schema class."""
        expected = {
            "race": RaceSchema,
            "entry": EntrySchema,
            "result": ResultSchema,
            "odds_trifecta": OddsTrifectaSchema,
            "payoff": PayoffSchema,
        }
        errors: list[str] = []
        for table_name, expected_class in expected.items():
            actual = TABLE_TO_SCHEMA.get(table_name)
            if actual is not expected_class:
                errors.append(
                    f"TABLE_TO_SCHEMA['{table_name}'] = {actual}, "
                    f"expected {expected_class}"
                )

        assert errors == [], "\n".join(errors)

    def test_get_columns_for_table_race(self) -> None:
        """get_columns_for_table('race') returns only race table columns."""
        race_cols = get_columns_for_table("race")
        assert isinstance(race_cols, dict), "Should return dict[str, str]"

        # All values should be valid race schema fields
        for jp_name, eng_name in race_cols.items():
            assert eng_name in RaceSchema.model_fields, (
                f"race column '{jp_name}' -> '{eng_name}' not in RaceSchema"
            )

        # Should include the race-level columns (rows 2-8, 9-28, 29-42)
        # At minimum: race_id, race_date, surface, distance, and 20 flags
        assert "race_id" in race_cols.values()
        assert "distance" in race_cols.values()

    def test_get_columns_for_table_entry(self) -> None:
        """get_columns_for_table('entry') returns only entry table columns."""
        entry_cols = get_columns_for_table("entry")
        assert isinstance(entry_cols, dict)
        assert len(entry_cols) > 0

        for jp_name, eng_name in entry_cols.items():
            assert eng_name in EntrySchema.model_fields, (
                f"entry column '{jp_name}' -> '{eng_name}' not in EntrySchema"
            )

    def test_get_columns_for_table_result(self) -> None:
        """get_columns_for_table('result') returns only result table columns."""
        result_cols = get_columns_for_table("result")
        assert isinstance(result_cols, dict)
        assert len(result_cols) > 0

        for jp_name, eng_name in result_cols.items():
            assert eng_name in ResultSchema.model_fields, (
                f"result column '{jp_name}' -> '{eng_name}' not in ResultSchema"
            )

    def test_get_columns_for_table_unknown_returns_empty(self) -> None:
        """get_columns_for_table with unknown table name returns empty dict."""
        unknown_cols = get_columns_for_table("nonexistent")
        assert unknown_cols == {}, (
            f"Expected empty dict for unknown table, got {unknown_cols}"
        )
