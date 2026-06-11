"""Standard-layer result table schema definition.

Defines the Pydantic model for result-level data from Kaggle race_result.csv.
ALL columns in this table are post-race -- they capture race outcome information
that becomes available only after the race has finished.

Per D-07: result table is fully separate from entry table.
Per D-09: join key to entry table is horse_race_id (1-to-1 relationship).

Per D-02: Pydantic is for TYPE DEFINITION ONLY. Row-level validation against
the 472MB CSV uses DataFrame operations, not per-row Pydantic parsing.
"""

from typing import Optional

from pydantic import BaseModel, Field


class ResultSchema(BaseModel):
    """Standard-layer result table schema.

    Post-race outcome data for each horse in a race.
    One row per horse per race. Join key: horse_race_id (1-to-1 with entry).

    Maps Kaggle race_result.csv result-level columns (rows 43-44, 52-58, 66
    in RESEARCH.md Kaggle Column Analysis).

    Key design decisions:
    - ALL fields are pre_race=False (post-race outcomes)
    - finish_position is Optional[int]: handles 1.1% null rate and non-finishers
      (中=withdrawal, 取=scratched, 失=disqualified, 除=removed, 再=re-run)
      per Pitfall #6
    - margin is Optional[str]: non-numeric format (e.g. "1.1/4", "大", "ハナ")
    - corner fields have high null rates (corner_1: 52.1%, corner_2: 44.0%)
    """

    # Identification
    horse_race_id: str = Field(
        description="Unique key: {race_id}_{horse_number:02d} (レース馬番ID). Join key to entry table per D-09.",
        json_schema_extra={"pre_race": False, "table": "result"},
    )
    race_id: str = Field(
        description="12-digit race identifier (foreign key to race table)",
        json_schema_extra={"pre_race": False, "table": "result"},
    )

    # Finish information (rows 43-44)
    finish_position: Optional[int] = Field(
        default=None,
        description="Finishing position 1-24, or None for non-finishers (着順). 1.1% null rate.",
        json_schema_extra={"pre_race": False, "table": "result"},
    )
    finish_note: Optional[str] = Field(
        default=None,
        description="Non-standard result indicator (着順注記): 中/取/失/除/再",
        json_schema_extra={"pre_race": False, "table": "result"},
    )

    # Time and margin (rows 52-53)
    finish_time: Optional[str] = Field(
        default=None,
        description="Finish time in M:SS.T format (タイム). 1.0% null rate.",
        json_schema_extra={"pre_race": False, "table": "result"},
    )
    margin: Optional[str] = Field(
        default=None,
        description="Margin to winner (着差): e.g. '1.1/4', '大', 'ハナ'. 10.0% null rate. String format is non-numeric.",
        json_schema_extra={"pre_race": False, "table": "result"},
    )

    # Corner positions (rows 54-57) -- high null rates
    corner_1: Optional[int] = Field(
        default=None,
        description="Position at 1st corner (1コーナー). 52.1% null rate.",
        json_schema_extra={"pre_race": False, "table": "result"},
    )
    corner_2: Optional[int] = Field(
        default=None,
        description="Position at 2nd corner (2コーナー). 44.0% null rate.",
        json_schema_extra={"pre_race": False, "table": "result"},
    )
    corner_3: Optional[int] = Field(
        default=None,
        description="Position at 3rd corner (3コーナー). 0.7% null rate.",
        json_schema_extra={"pre_race": False, "table": "result"},
    )
    corner_4: Optional[int] = Field(
        default=None,
        description="Position at 4th corner (4コーナー). 0.6% null rate.",
        json_schema_extra={"pre_race": False, "table": "result"},
    )

    # Performance metrics (rows 58, 66)
    last_3f: Optional[float] = Field(
        default=None,
        description="Final 3 furlong time in seconds (上り). 4.8% null rate.",
        json_schema_extra={"pre_race": False, "table": "result"},
    )
    prize_money: Optional[float] = Field(
        default=None,
        description="Prize money in 10K yen units (賞金(万円)). 55.0% null rate.",
        json_schema_extra={"pre_race": False, "table": "result"},
    )
