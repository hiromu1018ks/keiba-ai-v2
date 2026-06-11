"""Column mapping dicts for Kaggle CSV-to-standard-layer conversion.

Defines the authoritative mapping from Japanese CSV column headers to
English schema field names. These mappings are the foundation of the
entire conversion pipeline (Plans 02-03).

Key design decisions:
- KAGGLE_COLUMN_MAP uses the ACTUAL CSV header names for flag columns
  (with parentheses/brackets), not shortened names.
- The 20 flag columns (レース記号/*) may map multiple CSV columns to the
  same schema field (e.g., both "(混)" and "(市)" map to race_flag_allowance).
- ODDS_COLUMN_MAP maps only the 15 trifecta-relevant columns from odds.csv.
- DTYPE_SPEC specifies dtype=str for columns that cause DtypeWarning.

Per D-01: obstacle exclusion. Per D-02: no entry-level region filtering.
Per D-03/D-04: both odds_trifecta and payoff from odds.csv.
"""

from src.schemas.entry import EntrySchema
from src.schemas.odds_trifecta import OddsTrifectaSchema
from src.schemas.payoff import PayoffSchema
from src.schemas.race import RaceSchema
from src.schemas.result import ResultSchema

# ---------------------------------------------------------------------------
# KAGGLE_COLUMN_MAP: Authoritative mapping of all 66 Japanese column names
# from race_result.csv to (table_name, english_field_name) tuples.
#
# The 20 flag columns (rows 9-28) use the ACTUAL CSV header names with
# parentheses/brackets. Multiple CSV columns may map to the same schema field.
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
    # Rows 9-28: 20 race flag columns (actual CSV header names)
    # Note: Some CSV flags map to the same schema field.
    "レース記号/[抽]": ("race", "race_flag_condition_race"),
    "レース記号/(馬齢)": ("race", "race_flag_age_restricted"),
    "レース記号/牝": ("race", "race_flag_filly_only"),
    "レース記号/(父)": ("race", "race_flag_stallion_only"),
    "レース記号/(別定)": ("race", "race_flag_special_weight"),
    "レース記号/(混)": ("race", "race_flag_allowance"),
    "レース記号/(ハンデ)": ("race", "race_flag_handicap"),
    "レース記号/(抽)": ("race", "race_flag_condition_race"),
    "レース記号/(市)": ("race", "race_flag_allowance"),
    "レース記号/(定量)": ("race", "race_flag_bonus_weight"),
    "レース記号/牡": ("race", "race_flag_colt_only"),
    "レース記号/関東配布馬": ("race", "race_flag_open"),
    "レース記号/(指)": ("race", "race_flag_condition_race"),
    "レース記号/関西配布馬": ("race", "race_flag_open"),
    "レース記号/九州産馬": ("race", "race_flag_allowance"),
    "レース記号/見習騎手": ("race", "race_flag_apprentice"),
    "レース記号/せん": ("race", "race_flag_gelding_only"),
    "レース記号/(国際)": ("race", "race_flag_graded_stakes"),
    "レース記号/[指]": ("race", "race_flag_condition_race"),
    "レース記号/(特指)": ("race", "race_flag_special_weight"),
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

# ---------------------------------------------------------------------------
# ODDS_COLUMN_MAP: Mapping of 15 trifecta-relevant Japanese column names
# from odds.csv to OddsTrifectaSchema field names.
# ---------------------------------------------------------------------------
ODDS_COLUMN_MAP: dict[str, str] = {
    # Trifecta 1: top popular combination
    "三連複1_組合せ1": "trifecta1_combo_1",
    "三連複1_組合せ2": "trifecta1_combo_2",
    "三連複1_組合せ3": "trifecta1_combo_3",
    "三連複1_オッズ": "trifecta1_odds",
    "三連複1_人気": "trifecta1_popularity",
    # Trifecta 2: second popular combination
    "三連複2_組合せ1": "trifecta2_combo_1",
    "三連複2_組合せ2": "trifecta2_combo_2",
    "三連複2_組合せ3": "trifecta2_combo_3",
    "三連複2_オッズ": "trifecta2_odds",
    "三連複2_人気": "trifecta2_popularity",
    # Trifecta 3: third popular combination
    "三連複3_組合せ1": "trifecta3_combo_1",
    "三連複3_組合せ2": "trifecta3_combo_2",
    "三連複3_組合せ3": "trifecta3_combo_3",
    "三連複3_オッズ": "trifecta3_odds",
    "三連複3_人気": "trifecta3_popularity",
}

# ---------------------------------------------------------------------------
# FLAG_COLUMNS: The 20 actual CSV column names for race flag columns.
# These are the rows 9-28 in the CSV header, with the exact text including
# parentheses and brackets.
# ---------------------------------------------------------------------------
FLAG_COLUMNS: list[str] = [
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
]

# ---------------------------------------------------------------------------
# DTYPE_SPEC: dtype specification for pd.read_csv() to avoid DtypeWarning.
# All 20 flag columns plus 3 mixed-type optional columns are read as str.
# Total: 23 entries.
# ---------------------------------------------------------------------------
DTYPE_SPEC: dict[str, type] = {col: str for col in FLAG_COLUMNS}
DTYPE_SPEC.update({
    "芝・ダート区分2": str,
    "内・外・襷区分": str,
    "馬場状態2": str,
    "競馬場コード": str,  # Preserve zero-padded format (01-10)
    "重賞回次": str,  # Read as string to avoid float64 when NaN
})

# ---------------------------------------------------------------------------
# TABLE_TO_SCHEMA: Maps each table name to its Pydantic schema class.
# Used for dynamic schema lookup in validation.
# ---------------------------------------------------------------------------
TABLE_TO_SCHEMA: dict[str, type] = {
    "race": RaceSchema,
    "entry": EntrySchema,
    "result": ResultSchema,
    "odds_trifecta": OddsTrifectaSchema,
    "payoff": PayoffSchema,
}


def get_columns_for_table(table_name: str) -> dict[str, str]:
    """Return Japanese-to-English column mapping for a specific table.

    Filters KAGGLE_COLUMN_MAP to return only columns that belong to the
    specified table.

    Args:
        table_name: One of 'race', 'entry', 'result', 'odds_trifecta', 'payoff'.

    Returns:
        Dict mapping Japanese column names to English field names for the
        specified table. Empty dict if table_name is not found.
    """
    return {
        jp_name: eng_name
        for jp_name, (tbl, eng_name) in KAGGLE_COLUMN_MAP.items()
        if tbl == table_name
    }
