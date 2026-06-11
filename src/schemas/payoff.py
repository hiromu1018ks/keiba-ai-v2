"""Standard-layer payoff table schema definition.

Defines the Pydantic model for trifecta payoff data. This is a CONTRACT schema
for future phases -- no direct Kaggle source exists for full trifecta payoff
records (per RESEARCH.md Pitfall #4).

ALL columns in this table are post-race (pre_race=False).

Expected data sources:
- Phase 2: Partial data derivable from odds.csv trifecta odds (top-3 combos)
- Phase 5: Full payoff data from JRA scraping (all trifecta combinations)
- Phase 8: EV calculation using payoff data

Per D-02: Pydantic is for TYPE DEFINITION ONLY.
"""

from typing import Optional

from pydantic import BaseModel, Field


class PayoffSchema(BaseModel):
    """Standard-layer payoff table schema.

    Payoff (payout) data for trifecta combinations.
    One row per trifecta combination per race.

    This is a contract schema -- the actual data population happens in
    Phase 2 (partial, from odds.csv) and Phase 5 (full, from scraping).

    Key design decisions:
    - ALL fields pre_race=False (post-race result data)
    - combo_1/2/3 are non-Optional (define the trifecta combination)
    - odds and payoff_amount are Optional (may not be available for all combos)
    - odds is float (not int like OddsTrifectaSchema) -- this table stores
      the actual odds value, not the 0.1-unit Kaggle format
    """

    # Identification
    race_id: str = Field(
        description="12-digit race identifier (join key to race table)",
        json_schema_extra={"pre_race": False, "table": "payoff"},
    )

    # Trifecta combination (horse numbers)
    combo_1: int = Field(
        description="1st horse number in trifecta combination",
        json_schema_extra={"pre_race": False, "table": "payoff"},
    )
    combo_2: int = Field(
        description="2nd horse number in trifecta combination",
        json_schema_extra={"pre_race": False, "table": "payoff"},
    )
    combo_3: int = Field(
        description="3rd horse number in trifecta combination",
        json_schema_extra={"pre_race": False, "table": "payoff"},
    )

    # Payoff data
    odds: Optional[float] = Field(
        default=None,
        description="Odds value as float (not 0.1 units)",
        json_schema_extra={"pre_race": False, "table": "payoff"},
    )
    payoff_amount: Optional[int] = Field(
        default=None,
        description="Payout amount in yen",
        json_schema_extra={"pre_race": False, "table": "payoff"},
    )
