"""Standard-layer odds_trifecta table schema definition.

Defines the Pydantic model for trifecta (三連複) odds data from Kaggle odds.csv.
ALL columns in this table are post-race (pre_race=False) per D-04 -- reserved
for EV calculation only, not usable in feature layer.

Per D-07: odds_trifecta table is fully separate from other tables.
Per RESEARCH.md Pitfall #4: Kaggle odds.csv provides only top-3 popular
trifecta combinations. Full odds will come from Phase 5 (scraping).

Per D-02: Pydantic is for TYPE DEFINITION ONLY.
"""

from typing import Optional

from pydantic import BaseModel, Field


class OddsTrifectaSchema(BaseModel):
    """Standard-layer odds_trifecta table schema.

    Trifecta odds for top-3 popular combinations per race.
    One row per race. Primary key: race_id.

    Maps Kaggle odds.csv trifecta columns (RESEARCH.md "odds.csv: Trifecta-Relevant Columns").

    Key design decisions:
    - ALL fields pre_race=False per D-04 (EV calculation only)
    - Only race_id is non-Optional; all trifecta fields are sparse
    - Coverage: trifecta1 54.1%, trifecta2 0.1%, trifecta3 0.002%
    - Odds values are in 0.1 units (e.g. 990 = 99.0x) per Kaggle format
    """

    # Identification
    race_id: str = Field(
        description="12-digit race identifier (レースID) -- primary key",
        json_schema_extra={"pre_race": False, "table": "odds_trifecta"},
    )

    # Trifecta 1: top popular combination (54.1% coverage)
    trifecta1_combo_1: Optional[int] = Field(
        default=None,
        description="1st horse number in top trifecta combination (三連複1_組合せ1)",
        json_schema_extra={"pre_race": False, "table": "odds_trifecta"},
    )
    trifecta1_combo_2: Optional[int] = Field(
        default=None,
        description="2nd horse number in top trifecta combination (三連複1_組合せ2)",
        json_schema_extra={"pre_race": False, "table": "odds_trifecta"},
    )
    trifecta1_combo_3: Optional[int] = Field(
        default=None,
        description="3rd horse number in top trifecta combination (三連複1_組合せ3)",
        json_schema_extra={"pre_race": False, "table": "odds_trifecta"},
    )
    trifecta1_odds: Optional[int] = Field(
        default=None,
        description="Top trifecta odds in 0.1 units, e.g. 990 = 99.0x (三連複1_オッズ). 54.1% coverage.",
        json_schema_extra={"pre_race": False, "table": "odds_trifecta"},
    )
    trifecta1_popularity: Optional[int] = Field(
        default=None,
        description="Top trifecta popularity rank (三連複1_人気)",
        json_schema_extra={"pre_race": False, "table": "odds_trifecta"},
    )

    # Trifecta 2: second popular combination (0.1% coverage, near-empty)
    trifecta2_combo_1: Optional[int] = Field(
        default=None,
        description="1st horse number in 2nd trifecta combination (三連複2_組合せ1)",
        json_schema_extra={"pre_race": False, "table": "odds_trifecta"},
    )
    trifecta2_combo_2: Optional[int] = Field(
        default=None,
        description="2nd horse number in 2nd trifecta combination (三連複2_組合せ2)",
        json_schema_extra={"pre_race": False, "table": "odds_trifecta"},
    )
    trifecta2_combo_3: Optional[int] = Field(
        default=None,
        description="3rd horse number in 2nd trifecta combination (三連複2_組合せ3)",
        json_schema_extra={"pre_race": False, "table": "odds_trifecta"},
    )
    trifecta2_odds: Optional[int] = Field(
        default=None,
        description="2nd trifecta odds in 0.1 units (三連複2_オッズ). 0.1% coverage.",
        json_schema_extra={"pre_race": False, "table": "odds_trifecta"},
    )
    trifecta2_popularity: Optional[int] = Field(
        default=None,
        description="2nd trifecta popularity rank (三連複2_人気)",
        json_schema_extra={"pre_race": False, "table": "odds_trifecta"},
    )

    # Trifecta 3: third popular combination (0.002% coverage, near-empty)
    trifecta3_combo_1: Optional[int] = Field(
        default=None,
        description="1st horse number in 3rd trifecta combination (三連複3_組合せ1)",
        json_schema_extra={"pre_race": False, "table": "odds_trifecta"},
    )
    trifecta3_combo_2: Optional[int] = Field(
        default=None,
        description="2nd horse number in 3rd trifecta combination (三連複3_組合せ2)",
        json_schema_extra={"pre_race": False, "table": "odds_trifecta"},
    )
    trifecta3_combo_3: Optional[int] = Field(
        default=None,
        description="3rd horse number in 3rd trifecta combination (三連複3_組合せ3)",
        json_schema_extra={"pre_race": False, "table": "odds_trifecta"},
    )
    trifecta3_odds: Optional[int] = Field(
        default=None,
        description="3rd trifecta odds in 0.1 units (三連複3_オッズ). 0.002% coverage.",
        json_schema_extra={"pre_race": False, "table": "odds_trifecta"},
    )
    trifecta3_popularity: Optional[int] = Field(
        default=None,
        description="3rd trifecta popularity rank (三連複3_人気)",
        json_schema_extra={"pre_race": False, "table": "odds_trifecta"},
    )
