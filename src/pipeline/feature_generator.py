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

import numpy as np
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

# Margin text-to-numeric mapping (Plan 03-02)
# Source: JRA official margin definitions, RESEARCH.md Code Examples
# Values in 馬身 (horse length) units
MARGIN_MAP: dict[str, float] = {
    # Text margins (body parts)
    "ハナ": 0.02,      # nose ~20cm
    "アタマ": 0.05,    # head ~40cm
    "クビ": 0.10,      # neck ~60-80cm
    # Fractional margins (in 馬身/horse lengths)
    "3/4": 0.75,
    "1/2": 0.50,
    "1.1/4": 1.25,
    "1.1/2": 1.50,
    "1.3/4": 1.75,
    "2.1/2": 2.50,
    "3.1/2": 3.50,
    # Integer margins (in 馬身)
    "1": 1.0,
    "2": 2.0,
    "3": 3.0,
    "4": 4.0,
    "5": 5.0,
    "6": 6.0,
    "7": 7.0,
    "8": 8.0,
    "9": 9.0,
    "10": 10.0,
    # Special
    "大": 15.0,        # 大差 (large margin, >10 lengths)
    "同着": 0.0,       # dead heat
}

# Compound margin components: used for parsing "1.1/4+クビ" style values
# These are the additive parts that appear after "+"
COMPONENT_MAP: dict[str, float] = {
    "ハナ": 0.02,
    "クビ": 0.10,
    "1/2": 0.50,
}


def parse_margin(margin_str: str | None) -> float | None:
    """Convert margin text to numeric value in 馬身 (horse length) units.

    Handles:
    - Direct MARGIN_MAP lookup (e.g. "クビ" -> 0.10)
    - Compound margins split on "+" (e.g. "1.1/4+クビ" -> 1.35)
    - None/NaN/empty string -> None (graceful degradation)

    Args:
        margin_str: Margin text from result table, or None.

    Returns:
        Numeric margin value in 馬身 units, or None if input is
        None/NaN/empty/unrecognized.
    """
    if margin_str is None or (isinstance(margin_str, float) and np.isnan(margin_str)):
        return None

    # Strip whitespace (including full-width spaces common in Japanese data)
    margin_str = str(margin_str).strip()

    if margin_str == "":
        return None

    # Direct lookup first (most common case)
    if margin_str in MARGIN_MAP:
        return MARGIN_MAP[margin_str]

    # Compound parsing: split on "+" and sum components
    if "+" in margin_str:
        parts = margin_str.split("+")
        total = 0.0
        for part in parts:
            part = part.strip()
            if part in MARGIN_MAP:
                total += MARGIN_MAP[part]
            elif part in COMPONENT_MAP:
                total += COMPONENT_MAP[part]
            else:
                return None  # Unknown component -> graceful degradation
        return total

    return None  # Unknown format -> graceful degradation


def convert_margin_to_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """Add margin_numeric column to DataFrame by parsing margin text values.

    Applies parse_margin() to the "margin" column. Empty strings are treated
    as None. The original "margin" column is preserved.

    Args:
        df: Merged DataFrame with a "margin" column containing text values.

    Returns:
        DataFrame with "margin_numeric" column added.
    """
    df = df.copy()

    # Treat empty string as None before parsing
    margin_col = df["margin"].replace("", None)

    df["margin_numeric"] = margin_col.apply(parse_margin)

    return df


def parse_finish_time_to_seconds(time_str: str | None) -> float:
    """Convert finish time string (M:SS.T) to seconds.

    Args:
        time_str: Finish time in M:SS.T format (e.g. "1:29.5", "0:59.3"),
            or None/NaN.

    Returns:
        Time in seconds as float, or np.nan if input is None/NaN or
        malformed (missing ":").
    """
    if time_str is None or (isinstance(time_str, float) and np.isnan(time_str)):
        return np.nan

    time_str = str(time_str).strip()
    if ":" not in time_str:
        return np.nan

    parts = time_str.split(":")
    if len(parts) != 2:
        return np.nan

    try:
        minutes = float(parts[0])
        seconds = float(parts[1])
        return minutes * 60 + seconds
    except (ValueError, IndexError):
        return np.nan


def compute_finish_time_zscore(df: pd.DataFrame) -> pd.DataFrame:
    """Compute finish_time z-score with race-boundary temporal safety.

    The z-score normalization operates at RACE BOUNDARY level to prevent
    same-race leakage. Each race's normalization parameters (mean, std)
    come from all prior races in the same (course_name, distance, surface)
    group, with no contribution from any runner in the current race.

    Algorithm:
    1. Parse finish_time to seconds for each runner.
    2. Aggregate to race-level means (one row per race).
    3. Within each (course, distance, surface) group, compute expanding
       mean/std with shift(1) on the race-level series.
       shift(1) at race level skips the current RACE, not just the current row.
    4. Join normalization parameters back to every runner in that race.
       ALL runners in the same race get identical norm_mean and norm_std.
    5. Compute z-score: (finish_time_seconds - norm_mean) / norm_std.
    6. When std is NaN or 0, z-score is NaN (not inf).
    7. Groups with fewer than 5 prior races produce NaN z-score.

    This guarantees:
    - No runner from race N influences normalization stats for any runner in race N.
    - Adding future races to the dataset does NOT change z-scores for historical rows.
    - All runners in the same race receive identical normalization parameters.

    Args:
        df: DataFrame with columns: finish_time, race_id, race_date,
            course_name, distance, surface.

    Returns:
        DataFrame with finish_time_seconds and finish_time_zscore columns added.
        Intermediate columns (norm_mean, norm_std) are dropped.
    """
    df = df.copy()

    # Step 1: Parse finish_time to seconds
    df["finish_time_seconds"] = df["finish_time"].apply(parse_finish_time_to_seconds)

    # Step 2: Aggregate to race-level means
    race_means = (
        df.groupby("race_id")
        .agg(
            race_ft_mean=("finish_time_seconds", "mean"),
            race_date=("race_date", "first"),
            course_name=("course_name", "first"),
            distance=("distance", "first"),
            surface=("surface", "first"),
        )
        .reset_index()
    )

    # Step 3: Compute expanding-window stats on the race-level series
    race_means = race_means.sort_values(
        ["course_name", "distance", "surface", "race_date"]
    ).reset_index(drop=True)

    grp = race_means.groupby(["course_name", "distance", "surface"])
    race_means["norm_mean"] = (
        grp["race_ft_mean"].expanding(min_periods=5).mean().shift(1).values
    )
    race_means["norm_std"] = (
        grp["race_ft_mean"].expanding(min_periods=5).std().shift(1).values
    )

    # Step 4: Join normalization parameters back to entry-level DataFrame
    df = df.merge(
        race_means[["race_id", "norm_mean", "norm_std"]],
        on="race_id",
        how="left",
    )

    # Step 5: Compute z-score
    mask = df["norm_std"].notna() & (df["norm_std"] > 0)
    df["finish_time_zscore"] = np.nan
    df.loc[mask, "finish_time_zscore"] = (
        df.loc[mask, "finish_time_seconds"] - df.loc[mask, "norm_mean"]
    ) / df.loc[mask, "norm_std"]

    # Step 6: Clean up intermediate columns
    df = df.drop(columns=["norm_mean", "norm_std"])

    return df


def compute_lag_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute lag features for recent runs with valid-start filtering.

    Generates lag features encoding each horse's recent performance history.
    Only VALID-START rows are used for lag computation -- scratched (取) and
    removed (除) entries are excluded before shifting, then merged back with
    all-NaN lags.

    A "valid start" is any entry where the horse actually ran:
    - Normal finishes (finish_position is not NA, finish_note is None)
    - DNF: 中 (did not finish -- started but didn't complete)
    - Disqualified: 失 (started, disqualified)
    - Demoted: 降 (started, demoted)
    Excluded: 取 (scratched -- never started), 除 (removed -- never started)

    Lag features computed:
    - 25 raw lag columns: prev_{1..5}_{metric} for metrics:
      finish_position, last_3f, corner_4, finish_time_zscore, margin_numeric
    - 10 prev3 stat columns: prev3_{metric}_mean, prev3_{metric}_std
    - 10 prev5 stat columns: prev5_{metric}_mean, prev5_{metric}_std

    Total: 45 lag feature columns.

    Args:
        df: DataFrame with columns: horse_entity_key, race_date, race_id,
            finish_position, finish_note, last_3f, corner_4,
            finish_time_zscore, margin_numeric.

    Returns:
        DataFrame with 45 lag feature columns added.
    """
    df = df.copy()

    # Step 1: Identify valid starts (取 and 除 excluded)
    is_valid_start = ~df["finish_note"].isin(["取", "除"])

    # Step 2: Filter to valid-start rows for lag computation
    valid_df = df[is_valid_start].copy()

    # Sort deterministically
    valid_df = valid_df.sort_values(SORT_KEY).reset_index(drop=False)
    # Preserve original index for merge-back
    valid_df = valid_df.rename(columns={"index": "_orig_idx"})

    # Step 3: Compute lag features on valid-start rows
    lag_metrics = ["finish_position", "last_3f", "corner_4", "finish_time_zscore", "margin_numeric"]

    for metric in lag_metrics:
        for lag in range(1, 6):
            col_name = f"prev_{lag}_{metric}"
            valid_df[col_name] = valid_df.groupby("horse_entity_key")[metric].shift(lag)

    # Step 3b: Compute rolling statistics on prev_1 values
    for metric in lag_metrics:
        prev1_col = f"prev_1_{metric}"
        grouped = valid_df.groupby("horse_entity_key")[prev1_col]

        # prev3: rolling window of 3, min_periods=1 for mean, min_periods=2 for std
        valid_df[f"prev3_{metric}_mean"] = grouped.transform(
            lambda s: s.rolling(3, min_periods=1).mean()
        )
        valid_df[f"prev3_{metric}_std"] = grouped.transform(
            lambda s: s.rolling(3, min_periods=2).std()
        )

        # prev5: rolling window of 5, min_periods=1 for mean, min_periods=2 for std
        valid_df[f"prev5_{metric}_mean"] = grouped.transform(
            lambda s: s.rolling(5, min_periods=1).mean()
        )
        valid_df[f"prev5_{metric}_std"] = grouped.transform(
            lambda s: s.rolling(5, min_periods=2).std()
        )

    # Step 4: Select only the lag+stat columns plus merge key
    lag_cols = []
    for metric in lag_metrics:
        for lag in range(1, 6):
            lag_cols.append(f"prev_{lag}_{metric}")
        lag_cols.append(f"prev3_{metric}_mean")
        lag_cols.append(f"prev3_{metric}_std")
        lag_cols.append(f"prev5_{metric}_mean")
        lag_cols.append(f"prev5_{metric}_std")

    merge_cols = lag_cols + ["_orig_idx"]
    lag_only = valid_df[merge_cols].copy()

    # Step 5: Left-merge back to the full df using original index
    # Initialize all lag columns as NaN on the full df
    for col in lag_cols:
        df[col] = np.nan

    # Set values from valid-start rows
    df_indexed = df.reset_index(drop=True)
    for col in lag_cols:
        df_indexed.loc[lag_only["_orig_idx"].values, col] = lag_only[col].values

    return df_indexed


def _compute_person_stats(
    df: pd.DataFrame, person_col: str, prefix: str
) -> pd.DataFrame:
    """Compute rolling stats for a person (jockey or trainer) with exact D-08 intersection.

    Implements sum-based race-level aggregation: for each (person, race_id),
    counts top-3 finishes, wins, and valid starts across all runners.
    Then computes rolling rates using only prior valid starts that satisfy
    BOTH:
    - Within 365 days of current race date
    - Among the most recent 100 prior valid starts

    Args:
        df: DataFrame with person_col, race_id, race_date, finish_position,
            finish_note columns.
        person_col: Column name for the person ('jockey' or 'trainer').
        prefix: Prefix for output columns ('jockey_rolling_' or 'trainer_rolling_').

    Returns:
        DataFrame with columns: person_col, race_id, {prefix}top3_rate,
        {prefix}win_rate, {prefix}rides. One row per (person, race_id).
    """
    # Step 1: Create entry-level boolean columns
    is_top3 = df["finish_position"].notna() & (df["finish_position"] <= 3)
    is_win = df["finish_position"].notna() & (df["finish_position"] == 1)
    is_valid_start = ~df["finish_note"].isin(["取", "除"])

    work = df.copy()
    work["_is_top3"] = is_top3.astype(float)
    work["_is_win"] = is_win.astype(float)
    work["_is_valid_start"] = is_valid_start.astype(float)

    # Step 2: Aggregate to person-race level
    person_race = (
        work.groupby([person_col, "race_id"])
        .agg(
            top3_count=("_is_top3", "sum"),
            win_count=("_is_win", "sum"),
            valid_start_count=("_is_valid_start", "sum"),
            race_date=("race_date", "first"),
        )
        .reset_index()
    )

    # Ensure race_date is datetime for comparison
    person_race["race_date"] = pd.to_datetime(person_race["race_date"])

    # Sort chronologically per person
    person_race = person_race.sort_values(
        [person_col, "race_date", "race_id"]
    ).reset_index(drop=True)

    # Step 3: For each person, compute rolling stats with exact D-08 intersection
    results: list[dict] = []

    for person, group in person_race.groupby(person_col):
        group = group.reset_index(drop=True)
        n = len(group)

        # Pre-extract arrays for performance
        dates = group["race_date"].values
        top3s = group["top3_count"].values
        wins = group["win_count"].values
        valids = group["valid_start_count"].values
        race_ids = group["race_id"].values

        # Maintain a list of prior valid-start indices (as person-race rows)
        # Each entry: (race_date, top3_count, win_count, valid_start_count)
        prior_starts: list[tuple] = []

        for i in range(n):
            current_date = dates[i]

            # Filter prior_starts to D-08 exact intersection:
            # Keep only those within 365 days AND among most recent 100
            # First: remove entries older than 365 days
            cutoff_date = current_date - pd.Timedelta(days=365)
            prior_starts = [
                (d, t, w, v)
                for d, t, w, v in prior_starts
                if d >= cutoff_date
            ]
            # Then: keep at most the most recent 100 (they're already sorted by date)
            prior_starts = prior_starts[-100:]

            # Compute stats over the filtered set
            if prior_starts and sum(v for _, _, _, v in prior_starts) > 0:
                total_top3 = sum(t for _, t, _, _ in prior_starts)
                total_win = sum(w for _, _, w, _ in prior_starts)
                total_valid = sum(v for _, _, _, v in prior_starts)

                top3_rate = total_top3 / total_valid if total_valid > 0 else np.nan
                win_rate = total_win / total_valid if total_valid > 0 else np.nan
                rides = float(total_valid)
            else:
                top3_rate = np.nan
                win_rate = np.nan
                rides = 0.0

            results.append({
                person_col: person,
                "race_id": race_ids[i],
                f"{prefix}top3_rate": top3_rate,
                f"{prefix}win_rate": win_rate,
                f"{prefix}rides": rides,
            })

            # Add current race to prior_starts for next iteration (if it had valid starts)
            if valids[i] > 0:
                prior_starts.append(
                    (dates[i], top3s[i], wins[i], valids[i])
                )

    return pd.DataFrame(results)


def compute_jockey_trainer_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Compute jockey and trainer rolling statistics.

    Generates 6 rolling stat columns with sum-based race-level aggregation
    and exact D-08 intersection (both 365-day AND 100-start constraints
    applied simultaneously).

    Columns produced:
    - jockey_rolling_top3_rate, jockey_rolling_win_rate, jockey_rolling_rides
    - trainer_rolling_top3_rate, trainer_rolling_win_rate, trainer_rolling_rides

    Key design:
    - Sum-based aggregation: trainer with 2 top-3 from 3 runners gets
      top3_rate=2/3, not 1.0 (any-based would give 1.0).
    - Race-level: all runners of same person in same race get identical stats.
    - Temporal safety: current race results do not influence current stats
      (prior_starts appended AFTER computing stats for current row).
    - D-08 exact intersection: stats computed over prior valid starts that
      satisfy BOTH (within 365 days AND among most recent 100).

    Args:
        df: DataFrame with columns: jockey, trainer, race_id, race_date,
            finish_position, finish_note.

    Returns:
        DataFrame with 6 rolling stat columns added.
    """
    df = df.copy()

    # Compute jockey stats
    jockey_stats = _compute_person_stats(df, "jockey", "jockey_rolling_")
    df = df.merge(jockey_stats, on=["jockey", "race_id"], how="left")

    # Compute trainer stats
    trainer_stats = _compute_person_stats(df, "trainer", "trainer_rolling_")
    df = df.merge(trainer_stats, on=["trainer", "race_id"], how="left")

    return df


def generate_target(df: pd.DataFrame) -> pd.DataFrame:
    """Generate target variable and auxiliary columns for Model A training.

    Creates four columns from finish_position and finish_note:
    - target_top3 (Int64): 1 for finish_position 1-3, 0 otherwise (per D-12)
    - result_status (str): one of {finished, dnf, disqualified, scratched,
      removed, demoted} based on finish_note (per D-14)
    - is_dnf (bool): True for dnf and disqualified statuses
    - exclude_from_training (bool): True for scratched and removed (per D-13)

    Implementation note: every entry has a result row (1:1 relationship confirmed
    at 311,806 rows). finish_note distinguishes all non-finish categories:
    取 (scratched, 520), 除 (removed, 604), 中 (DNF, 966),
    降 (demoted, 18), 失 (disqualified, 1).

    Args:
        df: DataFrame with finish_position and finish_note columns.

    Returns:
        DataFrame with target_top3, result_status, is_dnf, exclude_from_training
        columns added.
    """
    df = df.copy()

    # Step 1: Create result_status from finish_note
    # Check finish_note first (specific notes), then default to "finished"
    conditions = [
        df["finish_note"] == "中",
        df["finish_note"] == "失",
        df["finish_note"] == "取",
        df["finish_note"] == "除",
        df["finish_note"] == "降",
    ]
    choices = ["dnf", "disqualified", "scratched", "removed", "demoted"]
    default = "finished"

    df["result_status"] = np.select(conditions, choices, default=default)

    # Step 2: Create is_dnf column (True for dnf/disqualified)
    df["is_dnf"] = df["result_status"].isin(["dnf", "disqualified"]).astype(bool)

    # Step 3: Create target_top3 (Int64 nullable)
    # finish_position <= 3 and not NaN -> 1
    # finish_position > 3 or NaN -> 0
    # Note: 降 (demoted) keeps finish_position per D-12
    is_top3 = df["finish_position"].notna() & (df["finish_position"] <= 3)
    df["target_top3"] = is_top3.astype("Int64")
    # Ensure NaN positions get 0
    df.loc[df["finish_position"].isna(), "target_top3"] = pd.array([0], dtype="Int64")[0]

    # Step 4: Create exclude_from_training (True for scratched/removed only, per D-13)
    df["exclude_from_training"] = df["result_status"].isin(["scratched", "removed"]).astype(bool)

    return df


def compute_debut_flag(df: pd.DataFrame) -> pd.DataFrame:
    """Compute debut flag (is_debut) identifying first valid start per horse.

    A horse's "debut" is their first VALID start, where valid start means
    result_status is NOT in ["scratched", "removed"]. 取 (scratched) and
    除 (removed) entries do not consume the debut position.

    This must be called after generate_target() which creates result_status.

    Implementation:
    1. Define is_valid_start: result_status NOT in ["scratched", "removed"]
    2. For each horse_entity_key, count cumulative valid starts BEFORE current row
    3. is_debut = (valid_before == 0) AND is_valid_start

    This correctly handles:
    - Horse whose first entry is 取: is_valid_start=False, is_debut=False
    - Same horse's second entry (first valid start): is_debut=True
    - Horse with all 取 entries: is_debut=False for all

    Args:
        df: DataFrame sorted by SORT_KEY with result_status column
            (requires generate_target() called first).

    Returns:
        DataFrame with is_debut and is_valid_start columns added.
    """
    df = df.copy()

    # Define valid start: anything except scratched/removed
    df["is_valid_start"] = ~df["result_status"].isin(["scratched", "removed"])

    # For each horse, count cumulative valid starts BEFORE current row
    # cumsum() includes current row, so subtract current row's contribution
    valid_before = (
        df.groupby("horse_entity_key")["is_valid_start"]
        .cumsum()
        - df["is_valid_start"].astype(int)
    )

    # is_debut: first valid start for this horse
    df["is_debut"] = (valid_before == 0) & df["is_valid_start"]

    return df


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

    # Step 4: Margin numeric conversion (Plan 03-02)
    df = convert_margin_to_numeric(df)
    logger.info("Margin numeric conversion complete")

    # Step 5: Finish time z-score normalization (Plan 03-02)
    df = compute_finish_time_zscore(df)
    logger.info("Finish time z-score normalization complete")

    # Step 6: Lag features for recent runs (Plan 03-03)
    df = compute_lag_features(df)
    logger.info("Lag feature computation complete")

    # Step 7: Jockey/trainer rolling statistics (Plan 03-03)
    df = compute_jockey_trainer_stats(df)
    logger.info("Jockey/trainer rolling statistics complete")

    # Step 8: Target variable generation (Plan 03-04)
    df = generate_target(df)
    logger.info("Target variable generation complete")

    # Step 9: Debut flag for first-time starters (Plan 03-04)
    df = compute_debut_flag(df)
    logger.info("Debut flag computation complete")

    # Steps 10: Placeholders for Plan 03-05
    # Plan 03-05: categorical CategoricalDtype conversion

    # Step 11: Parquet writing (Plan 03-05)
    # feature_dir.mkdir(parents=True, exist_ok=True)
    # ... write output files ...

    logger.info("Feature generation pipeline completed (skeleton)")
    return {}
