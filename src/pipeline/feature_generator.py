"""Feature generator for the feature-layer data pipeline.

Reads standard-layer Parquet files (race, entry, result), generates ML-ready
features for Model A (3着内確率), and prepares feature Parquet files.

Key design decisions:
- D-15: popularity/win_odds excluded from features (post-race per D-03/D-06)
- Review fix #1: horse_entity_key uses (horse_name, birth_year_proxy) to
  disambiguate all 14 confirmed same-name collisions in 2015-2021 data.
  birth_year_proxy = race_year - age, producing keys like "アームストロング_2011"
  vs "アームストロング_2018". Verified: 36,816 unique entities vs 36,802 unique
  names.
- Review fix #6: entry and result are 1:1 at 311,806 rows each. Inner join
  on result is correct. finish_note column distinguishes 取 (scratched, 520),
  除 (removed, 604), 中 (DNF, 966), 降 (demoted, 18), 失 (disqualified, 1).
- Review fix #7: SORT_KEY = [horse_entity_key, race_date, race_id] provides
  globally unique total order. race_id format YYYYPPCCDDRR encodes
  course+date+number, making it globally unique.

Threat model mitigations:
- T-03-01: pathlib.Path used throughout; directory existence validated before
  reading Parquet files.
"""

from pathlib import Path

import pandas as pd
from loguru import logger

from src.schemas.audit import audit_leakage  # noqa: F401 -- used by Plans 02-05
from src.schemas.entry import EntrySchema  # noqa: F401
from src.schemas.race import RaceSchema  # noqa: F401
from src.schemas.result import ResultSchema  # noqa: F401


CATEGORICAL_COLUMNS = [
    "course_name",
    "surface",
    "direction",
    "weather",
    "track_condition",
    "sex",
    "jockey",
    "trainer",
    "grade",
]

SORT_KEY = ["horse_entity_key", "race_date", "race_id"]


def derive_horse_entity_key(df: pd.DataFrame) -> pd.DataFrame:
    """Derive a collision-safe horse entity key from horse_name and birth_year_proxy.

    Computes birth_year_proxy = race_year - age, where race_year is extracted
    from race_id (first 4 digits). Then creates horse_entity_key as
    "{horse_name}_{birth_year_proxy}".

    This correctly disambiguates all 14 same-name horse collisions in 2015-2021
    data (109 rows). Two horses sharing the name "アームストロング" but born in
    2011 vs 2018 produce keys "アームストロング_2011" and "アームストロング_2018".

    The birth_year_proxy column is dropped after key creation (not needed
    downstream). race_year is retained for potential downstream use.

    Args:
        df: Merged DataFrame with horse_name, age, and race_id columns.

    Returns:
        DataFrame with horse_entity_key column added and birth_year_proxy dropped.
    """
    df = df.copy()

    # Extract race_year from race_id (format YYYYPPCCDDRR)
    df["race_year"] = df["race_id"].str[:4].astype(int)

    # Compute birth_year_proxy: race_year - age
    df["birth_year_proxy"] = df["race_year"] - df["age"]

    # Create horse_entity_key: horse_name + birth_year_proxy
    df["horse_entity_key"] = df["horse_name"] + "_" + df["birth_year_proxy"].astype(str)

    # Drop intermediate birth_year_proxy (not needed downstream)
    df = df.drop(columns=["birth_year_proxy"])

    return df


def load_and_merge(standard_dir: Path) -> pd.DataFrame:
    """Read standard-layer Parquet files and merge into a single DataFrame.

    Reads race.parquet, entry.parquet, result.parquet from standard_dir,
    performs inner joins (1:1 entry-result relationship verified at 311,806
    rows each), adds horse_entity_key, and sorts by SORT_KEY.

    Inner join on result is correct: data analysis confirms EVERY entry has
    a corresponding result row. finish_note distinguishes non-finishers:
    取 (scratched, 520 rows), 除 (removed, 604), 中 (DNF, 966),
    降 (demoted, 18), 失 (disqualified, 1).

    Args:
        standard_dir: Directory containing standard-layer Parquet files.

    Returns:
        Merged DataFrame sorted by [horse_entity_key, race_date, race_id].

    Raises:
        FileNotFoundError: If standard_dir or required Parquet files don't exist.
    """
    standard_dir = Path(standard_dir)

    # T-03-01: Validate directory exists
    if not standard_dir.is_dir():
        raise FileNotFoundError(f"Standard directory not found: {standard_dir}")

    # Read Parquet files
    race_path = standard_dir / "race.parquet"
    entry_path = standard_dir / "entry.parquet"
    result_path = standard_dir / "result.parquet"

    for p in [race_path, entry_path, result_path]:
        if not p.exists():
            raise FileNotFoundError(f"Required file not found: {p}")

    logger.info(f"Reading race.parquet from {race_path}")
    race_df = pd.read_parquet(race_path, engine="pyarrow")

    logger.info(f"Reading entry.parquet from {entry_path}")
    entry_df = pd.read_parquet(entry_path, engine="pyarrow")

    logger.info(f"Reading result.parquet from {result_path}")
    result_df = pd.read_parquet(result_path, engine="pyarrow")

    logger.info(f"Loaded: race={len(race_df)} rows, entry={len(entry_df)} rows, result={len(result_df)} rows")

    # Merge: entry + race (left join, race is the dimension table)
    df = entry_df.merge(race_df, on="race_id", how="left")
    logger.info(f"After entry+race merge: {len(df)} rows")

    # Merge: + result (inner join -- 1:1 relationship verified)
    # Drop result's race_id to avoid column name collision (already in entry)
    result_cols = result_df.drop(columns=["race_id"])
    df = df.merge(result_cols, on="horse_race_id", how="inner")
    logger.info(f"After +result merge (inner): {len(df)} rows")

    # Add horse_entity_key
    df = derive_horse_entity_key(df)

    # Sort by SORT_KEY for deterministic globally-unique total order
    df = df.sort_values(by=SORT_KEY).reset_index(drop=True)

    return df


def extract_race_context_features(df: pd.DataFrame) -> pd.DataFrame:
    """Extract race-level context features from the merged DataFrame.

    Computes field_size as the count of entries per race_id.
    Returns only pre-race context columns. Does NOT include popularity,
    win_odds, or any post-race result columns (per D-15).

    Args:
        df: Merged DataFrame with race context columns.

    Returns:
        DataFrame with race context features: race_id, race_date, course_name,
        distance, surface, direction, weather, track_condition, race_number,
        grade, field_size, horse_entity_key.
    """
    df = df.copy()

    # Compute field_size: count of entries per race_id
    df["field_size"] = df.groupby("race_id")["horse_number"].transform("count")

    # Select race context columns (all pre-race, no post-race)
    race_context_cols = [
        "race_id",
        "race_date",
        "course_name",
        "distance",
        "surface",
        "direction",
        "weather",
        "track_condition",
        "race_number",
        "grade",
        "field_size",
        "horse_entity_key",
    ]

    return df[race_context_cols]


def extract_horse_basic_features(df: pd.DataFrame) -> pd.DataFrame:
    """Extract horse-level basic features from the merged DataFrame.

    Returns pre-race horse characteristics. Explicitly does NOT include
    popularity or win_odds (post-race per D-15, reserved for EV calculation
    only).

    Args:
        df: Merged DataFrame with horse feature columns.

    Returns:
        DataFrame with horse basic features: bracket_num, horse_number, sex,
        age, weight_assigned, horse_weight, weight_change, horse_name,
        horse_entity_key, jockey, trainer.
    """
    horse_basic_cols = [
        "bracket_num",
        "horse_number",
        "sex",
        "age",
        "weight_assigned",
        "horse_weight",
        "weight_change",
        "horse_name",
        "horse_entity_key",
        "jockey",
        "trainer",
    ]

    return df[horse_basic_cols].copy()


def generate(
    standard_dir: Path = Path("data/standard"),
    feature_dir: Path = Path("data/feature"),
) -> dict[str, Path]:
    """Generate feature-layer Parquet from standard-layer data.

    Orchestrates the full feature generation pipeline:
    1. load_and_merge() -- read standard Parquet, merge, sort
    2. extract_race_context_features() -- race-level context + field_size
    3. extract_horse_basic_features() -- horse-level pre-race features
    4. Placeholder: margin numeric conversion (Plan 03-02)
    5. Placeholder: finish_time z-score normalization (Plan 03-02)
    6. Placeholder: lag features for recent runs (Plan 03-03)
    7. Placeholder: jockey/trainer rolling statistics (Plan 03-02)
    8. Placeholder: debut flag for first-time starters (Plan 03-03)
    9. Placeholder: target_top3 generation (Plan 03-04)
    10. Placeholder: categorical CategoricalDtype conversion (Plan 03-05)
    11. Placeholder: write Parquet output (Plan 03-05)

    Args:
        standard_dir: Directory containing standard-layer Parquet files.
        feature_dir: Directory to write feature Parquet output files.

    Returns:
        Dict mapping feature file names to output paths.
        Currently returns empty dict (Parquet writing comes in Plan 05).
    """
    logger.info("Starting feature generation pipeline")

    # Step 1: Load and merge
    df = load_and_merge(standard_dir)
    logger.info(f"Loaded and merged: {len(df)} rows")

    # Step 2: Extract race context features
    race_features = extract_race_context_features(df)
    logger.info(f"Race context features: {len(race_features.columns)} columns")

    # Step 3: Extract horse basic features
    horse_features = extract_horse_basic_features(df)
    logger.info(f"Horse basic features: {len(horse_features.columns)} columns")

    # Steps 4-10: Placeholders for Plans 02-05
    # Plan 03-02: margin numeric conversion
    # Plan 03-02: finish_time z-score normalization
    # Plan 03-03: lag features for recent runs (3-race, 5-race)
    # Plan 03-02: jockey/trainer rolling statistics
    # Plan 03-03: debut flag for first-time starters
    # Plan 03-04: target_top3 generation
    # Plan 03-05: categorical CategoricalDtype conversion

    # Step 11: Parquet writing (Plan 03-05)
    # feature_dir.mkdir(parents=True, exist_ok=True)
    # ... write output files ...

    logger.info("Feature generation pipeline completed (skeleton)")
    return {}
