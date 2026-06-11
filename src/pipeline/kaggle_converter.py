"""Kaggle CSV-to-Parquet converter for the standard-layer data pipeline.

Reads race_result.csv and odds.csv from the raw Kaggle directory, applies
filtering (2015+ dates, obstacle exclusion per D-01), splits into 5 tables
(race, entry, result, odds_trifecta, payoff), and writes Parquet files to
the standard layer.

Key design decisions:
- encoding="utf-8-sig" handles BOM in Kaggle CSV files (T-02-05)
- DTYPE_SPEC prevents DtypeWarning for 23 mixed-type columns (T-02-04)
- Flag columns converted from sparse text to Optional[bool] after rename
- Finish position notes: 降 keeps position, others (中/取/失/除/再) get None
- payoff table: unpivoted from trifecta1/2/3 columns, odds divided by 10

Per D-06: single Parquet file per table.
Per D-04: payoff is "incomplete" (top-3 combos only, no full payoff_amount).
"""

from pathlib import Path

import pandas as pd
from loguru import logger

from src.pipeline.column_mapping import (
    DTYPE_SPEC,
    ODDS_COLUMN_MAP,
    get_columns_for_table,
)
from src.schemas.audit import audit_leakage
from src.schemas.entry import EntrySchema
from src.schemas.race import RaceSchema


# Flag fields defined in RaceSchema but not present in Kaggle CSV.
# These will be added as None columns in the race table.
_UNMAPPED_RACE_FLAGS = [
    "race_flag_amateur",
    "race_flag_female_jockey",
    "race_flag_listed",
    "race_flag_maiden",
    "race_flag_mare_only",
    "race_flag_stakes",
    "race_flag_young_horse",
]


def convert(
    raw_dir: Path = Path("data/raw/kaggle"),
    standard_dir: Path = Path("data/standard"),
) -> dict[str, Path]:
    """Main entry point: CSV -> filter -> split -> transform -> write -> audit.

    Orchestrates the full conversion pipeline:
    1. Read race_result.csv and odds.csv
    2. Filter to 2015+ flat races (D-01 obstacle exclusion)
    3. Split race_result into race/entry/result tables
    4. Extract odds_trifecta and payoff from odds.csv
    5. Write 5 Parquet files to standard_dir
    6. Run audit_leakage() on race and entry tables

    Args:
        raw_dir: Directory containing Kaggle CSV files.
        standard_dir: Directory to write Parquet output files.

    Returns:
        Dict mapping table names to output Parquet file paths.
    """
    raw_dir = Path(raw_dir)
    standard_dir = Path(standard_dir)

    # Step 1: Read raw CSV files
    race_result_path = raw_dir / "19860105-20210731_race_result.csv"
    odds_path = raw_dir / "19860105-20210731_odds.csv"

    logger.info(f"Reading race_result.csv from {race_result_path}")
    df = read_race_result_csv(race_result_path)

    logger.info(f"Reading odds.csv from {odds_path}")
    odds_df = read_odds_csv(odds_path)

    # Step 2: Filter to 2015+ flat races
    logger.info("Filtering to 2015+ flat races")
    df["レース日付"] = pd.to_datetime(df["レース日付"])
    df = df[df["レース日付"] >= "2015-01-01"].copy()
    df = df[df["障害区分"] != "障害"].copy()
    logger.info(f"After filtering: {len(df)} rows")

    # Step 3: Split into race/entry/result
    logger.info("Splitting into race/entry/result tables")
    race_df, entry_df, result_df = split_race_entry_result(df)

    # Step 4: Extract odds tables
    logger.info("Extracting odds tables")
    valid_race_ids = set(entry_df["race_id"].unique())
    # Ensure odds レースID is string for matching against valid_race_ids
    odds_df["レースID"] = odds_df["レースID"].astype(str)
    odds_trifecta_df, payoff_df = extract_odds_tables(odds_df, valid_race_ids)

    # Step 5: Write Parquet files
    standard_dir.mkdir(parents=True, exist_ok=True)

    output_paths: dict[str, Path] = {}
    tables = {
        "race": race_df,
        "entry": entry_df,
        "result": result_df,
        "odds_trifecta": odds_trifecta_df,
        "payoff": payoff_df,
    }

    for table_name, table_df in tables.items():
        output_path = standard_dir / f"{table_name}.parquet"
        table_df.to_parquet(output_path, engine="pyarrow", compression="snappy", index=False)
        output_paths[table_name] = output_path
        logger.info(f"Wrote {table_name}: {len(table_df)} rows -> {output_path}")

    # Step 6: Audit for data leakage
    logger.info("Running data leakage audit")
    race_leaked = audit_leakage([RaceSchema], race_df, "race table generation")
    entry_leaked = audit_leakage([EntrySchema], entry_df, "entry table generation")

    if race_leaked:
        logger.warning(f"Race table post-race columns: {race_leaked}")
    if entry_leaked:
        logger.warning(f"Entry table post-race columns: {entry_leaked}")

    return output_paths


def read_race_result_csv(csv_path: Path) -> "pd.DataFrame":
    """Read race_result.csv with BOM handling and dtype specification.

    Args:
        csv_path: Path to the race_result.csv file.

    Returns:
        DataFrame with all 66 columns, dtypes as specified in DTYPE_SPEC.
    """
    return pd.read_csv(
        csv_path,
        encoding="utf-8-sig",
        dtype=DTYPE_SPEC,
        low_memory=False,
    )


def read_odds_csv(csv_path: Path) -> "pd.DataFrame":
    """Read odds.csv with BOM handling.

    No dtype spec needed for odds (smaller file, no DtypeWarning issues).

    Args:
        csv_path: Path to the odds.csv file.

    Returns:
        DataFrame with all odds columns.
    """
    return pd.read_csv(csv_path, encoding="utf-8-sig")


def _select_and_rename(
    df: pd.DataFrame, rename_map: dict[str, str]
) -> pd.DataFrame:
    """Select and rename columns, handling multi-to-single mappings.

    When multiple Japanese columns map to the same English name (e.g., flag
    columns), they are coalesced: if any source column has a non-empty/non-NaN
    value, the result is that value. This implements OR logic for flag columns.

    Args:
        df: Source DataFrame with Japanese column names.
        rename_map: Dict mapping Japanese column names to English field names.

    Returns:
        DataFrame with renamed columns. Multi-mapped columns are coalesced.
    """
    cols_available = [c for c in rename_map.keys() if c in df.columns]
    subset = df[cols_available].copy()

    # Group columns by their target English name
    eng_to_jp: dict[str, list[str]] = {}
    for jp_name, eng_name in rename_map.items():
        if jp_name in cols_available:
            eng_to_jp.setdefault(eng_name, []).append(jp_name)

    result = pd.DataFrame()
    for eng_name, jp_names in eng_to_jp.items():
        if len(jp_names) == 1:
            # Simple rename
            result[eng_name] = subset[jp_names[0]].values
        else:
            # Multi-mapping: coalesce (take first non-empty/non-NaN value)
            # This handles flag columns where multiple CSV cols map to same field
            coalesced = subset[jp_names[0]].copy()
            for jp_name in jp_names[1:]:
                mask = coalesced.isna() | (coalesced == "")
                coalesced[mask] = subset.loc[mask, jp_name]
            result[eng_name] = coalesced.values

    return result


def split_race_entry_result(
    df: "pd.DataFrame",
) -> tuple["pd.DataFrame", "pd.DataFrame", "pd.DataFrame"]:
    """Split a filtered race_result DataFrame into race, entry, and result tables.

    Uses KAGGLE_COLUMN_MAP to select and rename columns for each table.
    Race table is deduplicated by race_id. Flag columns are converted to
    Optional[bool]. Finish positions are processed for note handling.

    Args:
        df: Filtered DataFrame with Japanese column names.

    Returns:
        Tuple of (race_df, entry_df, result_df) with English column names.
    """
    # Build rename dicts for each table
    race_rename = get_columns_for_table("race")
    entry_rename = get_columns_for_table("entry")
    result_rename = get_columns_for_table("result")

    # Entry and result tables also need race_id as a foreign key,
    # even though レースID is mapped to the "race" table in KAGGLE_COLUMN_MAP.
    entry_rename["レースID"] = "race_id"
    result_rename["レースID"] = "race_id"

    # Result table also needs horse_race_id (same as entry, 1:1 relationship)
    result_rename["レース馬番ID"] = "horse_race_id"

    # Process finish position: renames 着順->finish_position, 着順注記->finish_note
    df = process_finish_position(df)

    # Remove already-renamed columns from result_rename dict
    # (process_finish_position already renamed these)
    for already_renamed in ["着順", "着順注記"]:
        result_rename.pop(already_renamed, None)

    # Race table: select race columns, rename, deduplicate
    race_df = _select_and_rename(df, race_rename)
    race_df = race_df.drop_duplicates(subset=["race_id"])

    # Convert flag columns to Optional[bool]
    race_df = convert_flags_to_bool(race_df)

    # Add unmapped race flag columns as None (not present in Kaggle CSV)
    for flag_col in _UNMAPPED_RACE_FLAGS:
        race_df[flag_col] = pd.NA

    # Ensure string columns have string dtype
    for str_col in ["race_id", "course_code", "race_date"]:
        if str_col in race_df.columns:
            race_df[str_col] = race_df[str_col].astype(str)

    # Entry table: select entry columns, rename
    entry_df = _select_and_rename(df, entry_rename)

    # Ensure string columns in entry table
    for str_col in ["horse_race_id", "race_id"]:
        if str_col in entry_df.columns:
            entry_df[str_col] = entry_df[str_col].astype(str)

    # Result table: select remaining result columns, rename, then add
    # the pre-processed finish_position and finish_note columns
    result_df = _select_and_rename(df, result_rename)
    result_df["finish_position"] = df["finish_position"].values
    result_df["finish_note"] = df["finish_note"].values

    # Ensure string columns in result table
    for str_col in ["horse_race_id", "race_id"]:
        if str_col in result_df.columns:
            result_df[str_col] = result_df[str_col].astype(str)

    return race_df, entry_df, result_df


def convert_flags_to_bool(df: "pd.DataFrame") -> "pd.DataFrame":
    """Convert race flag columns from sparse text to Optional[bool].

    For each column starting with 'race_flag_':
    - Non-empty and not NaN -> True
    - Empty string or NaN -> None (pd.NA)

    Args:
        df: DataFrame with race_flag_* columns (after rename to English names).

    Returns:
        DataFrame with flag columns converted to boolean/NA.
    """
    flag_cols = [col for col in df.columns if col.startswith("race_flag_")]
    for col in flag_cols:
        # True where value is non-empty and not NaN, else None
        df[col] = df[col].apply(
            lambda x: True if pd.notna(x) and x != "" else pd.NA
        )
    return df


def process_finish_position(df: "pd.DataFrame") -> "pd.DataFrame":
    """Handle finish position notes and rename to English.

    Operates on the Japanese column names '着順' (finish position) and
    '着順注記' (finish note). Processes the notes, then renames the columns
    to their English equivalents 'finish_position' and 'finish_note':
    - 降 (demoted): keeps original finish_position, note recorded
    - 中/取/失/除/再: finish_position set to pd.NA, note recorded
    - No note: finish_position stays as-is, finish_note is pd.NA

    Args:
        df: DataFrame with Japanese column names (before rename).

    Returns:
        DataFrame with '着順注記' replaced by 'finish_note' and
        '着順' replaced by 'finish_position' (Int64 nullable).
    """
    df = df.copy()

    # Create finish_note from 着順注記
    df["finish_note"] = df["着順注記"].where(df["着順注記"].notna())

    # Notes that null the finish position (withdrawal, scratched, etc.)
    null_notes = {"中", "取", "失", "除", "再"}

    # For rows with null_notes: set 着順 to NA
    mask_null = df["finish_note"].isin(null_notes)
    df.loc[mask_null, "着順"] = pd.NA

    # For 降 (demoted): keep 着順 as-is, just record the note
    # (no action needed - finish_position preserved)

    # Convert 着順 to nullable Int64 and rename to finish_position
    df["着順"] = pd.to_numeric(df["着順"], errors="coerce").astype("Int64")
    df = df.rename(columns={"着順": "finish_position"})

    # Drop the original 着順注記 column (replaced by finish_note)
    if "着順注記" in df.columns:
        df = df.drop(columns=["着順注記"])

    return df


def extract_odds_tables(
    odds_df: "pd.DataFrame",
    valid_race_ids: set[str],
) -> tuple["pd.DataFrame", "pd.DataFrame"]:
    """Extract odds_trifecta and payoff tables from odds.csv DataFrame.

    Filters odds to only valid flat race_ids, then:
    - odds_trifecta: renames trifecta columns using ODDS_COLUMN_MAP
    - payoff: unpivots trifecta1/2/3 into up to 3 rows per race,
      with combo_1/2/3, odds (divided by 10), payoff_amount=None

    Args:
        odds_df: Raw odds.csv DataFrame with Japanese column names.
        valid_race_ids: Set of race_ids from filtered flat race_result.

    Returns:
        Tuple of (odds_trifecta_df, payoff_df).
    """
    # Filter to valid flat race_ids only (Pitfall 5: obstacle exclusion)
    odds_df = odds_df[odds_df["レースID"].isin(valid_race_ids)].copy()

    # --- OddsTrifecta table ---
    # Select race_id + all trifecta columns
    trifecta_cols = ["レースID"] + list(ODDS_COLUMN_MAP.keys())
    odds_trifecta_df = odds_df[trifecta_cols].copy()
    odds_trifecta_df = odds_trifecta_df.rename(
        columns={**ODDS_COLUMN_MAP, "レースID": "race_id"}
    )
    # Ensure race_id is string
    odds_trifecta_df["race_id"] = odds_trifecta_df["race_id"].astype(str)

    # --- Payoff table ---
    # Unpivot trifecta1/2/3 into rows
    payoff_rows: list[dict] = []
    for i in range(1, 4):
        combo1_col = f"三連複{i}_組合せ1"
        combo2_col = f"三連複{i}_組合せ2"
        combo3_col = f"三連複{i}_組合せ3"
        odds_col = f"三連複{i}_オッズ"

        if combo1_col not in odds_df.columns:
            continue

        subset = odds_df[["レースID", combo1_col, combo2_col, combo3_col, odds_col]].copy()

        # Only keep rows where ALL combo values are present (PayoffSchema requires
        # combo_1/2/3 as non-Optional int fields -- skip incomplete rows)
        subset = subset.dropna(subset=[combo1_col, combo2_col, combo3_col])

        for _, row in subset.iterrows():
            payoff_rows.append({
                "race_id": str(row["レースID"]),
                "combo_1": int(row[combo1_col]),
                "combo_2": int(row[combo2_col]),
                "combo_3": int(row[combo3_col]),
                "odds": row[odds_col] / 10.0 if pd.notna(row[odds_col]) else None,
                "payoff_amount": None,  # D-04: incomplete state
            })

    if payoff_rows:
        payoff_df = pd.DataFrame(payoff_rows)
    else:
        payoff_df = pd.DataFrame(
            columns=["race_id", "combo_1", "combo_2", "combo_3", "odds", "payoff_amount"]
        )

    return odds_trifecta_df, payoff_df
