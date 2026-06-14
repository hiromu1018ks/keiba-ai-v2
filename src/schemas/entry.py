"""Standard-layer entry table schema definition.

Defines the Pydantic model for entry-level data from Kaggle race_result.csv.
This table has MIXED pre_race/post_race columns:
- Most fields are pre-race (known before or at race start)
- popularity and win_odds are post-race per D-03 (not usable in feature layer,
  reserved for EV calculation only)

Per D-06: EntrySchema includes popularity and win_odds fields classified as
post-race (pre_race=False). Phase 3 (Feature Engineering) must exclude these
from model features -- this schema design enables that separation.

Per D-02: Pydantic is for TYPE DEFINITION ONLY. Row-level validation against
the 472MB CSV uses DataFrame operations, not per-row Pydantic parsing.
"""

from typing import Optional

from pydantic import BaseModel, Field


class EntrySchema(BaseModel):
    """Standard-layer entry table schema.

    Pre-race information about each horse in a race.
    One row per horse per race. Primary key: horse_race_id.

    Maps Kaggle race_result.csv entry-level columns (rows 1, 45-51, 59-65
    in RESEARCH.md Kaggle Column Analysis).

    Key design decisions:
    - horse_race_id: unique key per D-09 ({race_id}_{horse_number:02d})
    - jockey/trainer: string columns per D-08 (no master table)
    - popularity/win_odds: pre_race=False per D-03 (market signals excluded from features)
    - horse_weight/weight_change: pre_race=True per D-05 (measured before race)
    """

    # Identification (rows 1, 45-46)
    horse_race_id: str = Field(
        description="Unique key: {race_id}_{horse_number:02d} (レース馬番ID)",
        json_schema_extra={"pre_race": True, "table": "entry"},
    )
    race_id: str = Field(
        description="12-digit race identifier (foreign key to race table)",
        json_schema_extra={"pre_race": True, "table": "entry"},
    )
    bracket_num: int = Field(
        description="Bracket number 1-8 (枠番)",
        ge=1,
        le=8,
        json_schema_extra={"pre_race": True, "table": "entry"},
    )
    horse_number: int = Field(
        description="Horse number 1-18+ (馬番)",
        ge=1,
        json_schema_extra={"pre_race": True, "table": "entry"},
    )

    # Horse details (rows 47-49)
    horse_name: str = Field(
        description="Horse name (馬名)",
        json_schema_extra={"pre_race": True, "table": "entry"},
    )
    sex: str = Field(
        description="Sex: 牝/牡/セ (性別)",
        json_schema_extra={"pre_race": True, "table": "entry"},
    )
    age: int = Field(
        description="Horse age (馬齢, ge=2)",
        ge=2,
        json_schema_extra={"pre_race": True, "table": "entry"},
    )

    # Race assignment (row 50)
    weight_assigned: float = Field(
        description="Assigned weight in kg (斤量)",
        json_schema_extra={"pre_race": True, "table": "entry"},
    )

    # People (rows 51, 64-65) -- per D-08: string columns, no master table
    jockey: str = Field(
        description="Jockey name (騎手)",
        json_schema_extra={"pre_race": True, "table": "entry"},
    )
    trainer: str = Field(
        description="Trainer name (調教師)",
        json_schema_extra={"pre_race": True, "table": "entry"},
    )
    owner: str = Field(
        description="Horse owner name (馬主)",
        json_schema_extra={"pre_race": True, "table": "entry"},
    )

    # Physical measurements (rows 61-62) -- per D-05: pre_race=True
    horse_weight: Optional[int] = Field(
        default=None,
        description=(
            "Horse weight in kg, measured on race day (馬体重). "
            "NOTE (WR-06): the standard-layer Parquet stores this as Float64 "
            "(Kaggle double); the int annotation is documentation only and "
            "does NOT change the runtime dtype. See "
            "src/scraper/normalizer.py:SCHEMA_DTYPE_MAP[EntrySchema]."
        ),
        json_schema_extra={"pre_race": True, "table": "entry"},
    )
    weight_change: Optional[int] = Field(
        default=None,
        description=(
            "Weight change from previous race, can be negative (場体重増減). "
            "NOTE (WR-06): the standard-layer Parquet stores this as Float64 "
            "(Kaggle double); the int annotation is documentation only and "
            "does NOT change the runtime dtype. See "
            "src/scraper/normalizer.py:SCHEMA_DTYPE_MAP[EntrySchema]."
        ),
        json_schema_extra={"pre_race": True, "table": "entry"},
    )

    # Region (row 63)
    region: Optional[str] = Field(
        default=None,
        description="Region classification: 東/西/外国/地方 (東西・外国・地方区分)",
        json_schema_extra={"pre_race": True, "table": "entry"},
    )

    # Market signals (rows 59-60) -- per D-03: pre_race=False
    # These encode market information; model must predict purely from
    # horse/race characteristics, then compare against odds for EV calculation.
    popularity: Optional[int] = Field(
        default=None,
        description=(
            "Betting popularity rank (人気) -- post-race for feature purposes. "
            "NOTE (WR-06): the standard-layer Parquet stores this as Float64 "
            "(Kaggle double); the int annotation is documentation only and "
            "does NOT change the runtime dtype. See "
            "src/scraper/normalizer.py:SCHEMA_DTYPE_MAP[EntrySchema]."
        ),
        json_schema_extra={"pre_race": False, "table": "entry"},
    )
    win_odds: Optional[float] = Field(
        default=None,
        description="Win odds (単勝) -- post-race for feature purposes",
        json_schema_extra={"pre_race": False, "table": "entry"},
    )
