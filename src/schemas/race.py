"""Standard-layer race table schema definition.

Defines the Pydantic model for race-level data from Kaggle race_result.csv.
All columns in this table are pre-race -- known before or at race start.

Per D-02: Pydantic is for TYPE DEFINITION ONLY. Row-level validation against
the 472MB CSV uses DataFrame operations, not per-row Pydantic parsing.
"""

from typing import Optional

from pydantic import BaseModel, Field


class RaceSchema(BaseModel):
    """Standard-layer race table schema.

    Maps Kaggle race_result.csv race-level columns (rows 2-42 in RESEARCH.md).
    One row per unique race. Join key: race_id.

    The 20 race_flag_* fields correspond to the レース記号/* prefix columns
    (rows 9-28), which are sparse boolean flags encoding race conditions like
    handicap, age-restricted, filly-only, etc.
    """

    # Race identification (rows 2-3, 7-8, 29, 31-32, 42)
    race_id: str = Field(
        description="Unique race identifier (12-digit: YYYYPPCCDDRR)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    race_date: str = Field(
        description="Race date (YYYY-MM-DD format)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    meeting_num: int = Field(
        description="Meeting number within the year (開催回数)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    course_code: str = Field(
        description="Course code (01-10)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    course_name: str = Field(
        description="Course name in Japanese (競馬場名)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    meeting_day: int = Field(
        description="Day within the meeting (開催日数)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    race_condition: str = Field(
        description="Race condition/class (競争条件, e.g. '4歳以上300万下')",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    race_number: int = Field(
        description="Race number within the day (レース番号)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    grade_revision: Optional[str] = Field(
        default=None,
        description="Grade revision number (重賞回次, 96.3% null)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    race_name: str = Field(
        description="Race name (レース名)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    grade: Optional[str] = Field(
        default=None,
        description="Grade classification (G1/G2/G3/G/listed or empty)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    obstacle: Optional[str] = Field(
        default=None,
        description="Obstacle classification ('障害' or empty)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )

    # Course and surface details (rows 34-38)
    surface: str = Field(
        description="Surface type: 芝/ダート (芝・ダート区分)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    surface_detail: Optional[str] = Field(
        default=None,
        description="Surface detail (芝・ダート区分2)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    direction: str = Field(
        description="Direction: 右/左 (右左回り・直線区分)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    course_detail: Optional[str] = Field(
        default=None,
        description="Course detail: 外/内2周/襷 (内・外・襷区分)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    distance: int = Field(
        description="Distance in meters (距離(m))",
        json_schema_extra={"pre_race": True, "table": "race"},
    )

    # Weather and track conditions (rows 39-41)
    weather: Optional[str] = Field(
        default=None,
        description="Weather: 晴/曇/雨/小雨/雪/小雪 (天候)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    track_condition: Optional[str] = Field(
        default=None,
        description="Track condition: 良/稍重/重/不良 (馬場状態1)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    track_condition_detail: Optional[str] = Field(
        default=None,
        description="Track condition detail (馬場状態2)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )

    # Start time (row 42)
    start_time: str = Field(
        description="Start time in HH:MM format (発走時刻)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )

    # 20 boolean race flags (rows 9-28: レース記号/* prefix columns)
    # These are sparse flags where value is the flag name itself or empty string.
    # Converted to Optional[bool] in the standard layer.
    race_flag_handicap: Optional[bool] = Field(
        default=None,
        description="Handicap race flag (レース記号/ハンデ)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    race_flag_age_restricted: Optional[bool] = Field(
        default=None,
        description="Age-restricted race flag",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    race_flag_filly_only: Optional[bool] = Field(
        default=None,
        description="Filly-only race flag (レース記号/牝)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    race_flag_colt_only: Optional[bool] = Field(
        default=None,
        description="Colt-only race flag",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    race_flag_gelding_only: Optional[bool] = Field(
        default=None,
        description="Gelding-only race flag",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    race_flag_mare_only: Optional[bool] = Field(
        default=None,
        description="Mare-only race flag",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    race_flag_stallion_only: Optional[bool] = Field(
        default=None,
        description="Stallion book race flag",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    race_flag_apprentice: Optional[bool] = Field(
        default=None,
        description="Apprentice jockey race flag (見習騎手)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    race_flag_amateur: Optional[bool] = Field(
        default=None,
        description="Amateur jockey race flag",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    race_flag_female_jockey: Optional[bool] = Field(
        default=None,
        description="Female jockey race flag",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    race_flag_young_horse: Optional[bool] = Field(
        default=None,
        description="Young horse race flag",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    race_flag_condition_race: Optional[bool] = Field(
        default=None,
        description="Condition race flag",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    race_flag_special_weight: Optional[bool] = Field(
        default=None,
        description="Special weight race flag (別定)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    race_flag_bonus_weight: Optional[bool] = Field(
        default=None,
        description="Bonus weight race flag (定量)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    race_flag_stakes: Optional[bool] = Field(
        default=None,
        description="Stakes race flag",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    race_flag_graded_stakes: Optional[bool] = Field(
        default=None,
        description="Graded stakes race flag",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    race_flag_listed: Optional[bool] = Field(
        default=None,
        description="Listed race flag",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    race_flag_open: Optional[bool] = Field(
        default=None,
        description="Open class race flag",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    race_flag_maiden: Optional[bool] = Field(
        default=None,
        description="Maiden race flag (未勝利)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    race_flag_allowance: Optional[bool] = Field(
        default=None,
        description="Allowance/conditional race flag",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
