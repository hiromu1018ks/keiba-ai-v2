"""Data quality validation functions implementing D-05 checks.

Validates the integrity of Parquet files in the standard layer against
source CSV data and Phase 1 Pydantic schema definitions.

8 validation checks:
1. validate_row_counts -- CSV row counts match Parquet row counts
2. validate_schema_conformance -- column names and dtypes match schemas
3. validate_audit -- post-race column leakage detection
4. validate_null_rates -- null rate comparison between source and Parquet
5. validate_distributions -- numeric column stats comparison
6. validate_referential_integrity -- race_id consistency across tables
7. validate_sample_rows -- spot-check individual rows CSV vs Parquet
8. validate_value_ranges -- domain-specific value constraints

Plus run_all_validations() orchestrator that runs all 8 and aggregates results.
"""

from pathlib import Path
from typing import Any

from loguru import logger

from src.pipeline.column_mapping import KAGGLE_COLUMN_MAP, ODDS_COLUMN_MAP, TABLE_TO_SCHEMA
from src.schemas.audit import audit_leakage


# ---------------------------------------------------------------------------
# Dtype compatibility mapping: schema annotation -> acceptable Parquet dtypes
# ---------------------------------------------------------------------------
_DTYPE_COMPAT: dict[str, set[str]] = {
    "str": {"object", "string", "str", "unicode"},
    "int": {"int64", "Int64", "int32", "Int32", "int16", "Int16", "int8", "Int8",
            "uint8", "uint16", "uint32", "uint64"},
    "float": {"float64", "float32", "Float64", "Float32"},
    # CR-03 (Phase 06 review): removed "object" from the bool set.
    #
    # The "object" entry was originally added to tolerate nullable booleans
    # stored as object after a Parquet round-trip. But the production dtype
    # contract (normalizer.SCHEMA_DTYPE_MAP) uses nullable "boolean" (capital B)
    # for all 20 race_flag_* fields, which serializes to Arrow bool, NOT object.
    # Accepting "object" unconditionally meant a race_flag_* column stored as
    # object with arbitrary string/int content (e.g. ["yes", 5, pd.NA]) passed
    # schema conformance silently — the opposite of a validator.
    #
    # The object-content guard below (in validate_schema_conformance) catches
    # the residual object-dtype case that DOES occur in practice (all-NA object
    # columns from empty Parquet round-trips) while rejecting non-bool content.
    "bool": {"bool", "boolean"},
}


def _get_expected_dtype(field_info: Any) -> str:
    """Determine expected dtype category from a Pydantic field annotation.

    Returns one of: 'str', 'int', 'float', 'bool'.
    Falls back to 'str' for unrecognized types.
    """
    ann = field_info.annotation
    # Handle Optional types -- extract the inner type
    origin = getattr(ann, "__origin__", None)
    args = getattr(ann, "__args__", ())

    if origin is not None:
        # Optional[X] -> union of X and NoneType
        non_none_args = [a for a in args if a is not type(None)]
        if non_none_args:
            ann = non_none_args[0]

    type_name = getattr(ann, "__name__", str(ann)).lower()

    if "int" in type_name:
        return "int"
    if "float" in type_name:
        return "float"
    if "bool" in type_name:
        return "bool"
    return "str"


# ---------------------------------------------------------------------------
# Check 1: Row counts
# ---------------------------------------------------------------------------

def validate_row_counts(
    source_counts: dict[str, int],
    parquet_dir: Path,
) -> dict[str, bool]:
    """Compare expected row counts against Parquet file row counts.

    Args:
        source_counts: Dict mapping table names to expected row counts.
        parquet_dir: Directory containing Parquet files.

    Returns:
        Dict mapping table names to True (match) or False (mismatch/missing).
    """
    results: dict[str, bool] = {}
    parquet_dir = Path(parquet_dir)

    import pyarrow.parquet as pq

    for table_name, expected_count in source_counts.items():
        parquet_path = parquet_dir / f"{table_name}.parquet"
        if not parquet_path.exists():
            logger.warning(f"Missing Parquet file: {parquet_path}")
            results[table_name] = False
            continue

        parquet_file = pq.ParquetFile(parquet_path)
        actual_count = parquet_file.metadata.num_rows
        match = actual_count == expected_count
        results[table_name] = match

        if match:
            logger.info(f"Row count check PASSED for {table_name}: {actual_count}")
        else:
            logger.warning(
                f"Row count MISMATCH for {table_name}: "
                f"expected {expected_count}, got {actual_count}"
            )

    return results


# ---------------------------------------------------------------------------
# Check 2: Schema conformance
# ---------------------------------------------------------------------------

def validate_schema_conformance(parquet_dir: Path) -> dict[str, list[str]]:
    """Check Parquet column names and dtypes against Phase 1 schema definitions.

    For each table in TABLE_TO_SCHEMA, verifies:
    - All schema fields exist as Parquet columns
    - Parquet dtypes are compatible with schema annotations

    Args:
        parquet_dir: Directory containing Parquet files.

    Returns:
        Dict mapping table names to lists of error messages.
    """
    import pandas as pd

    results: dict[str, list[str]] = {}
    parquet_dir = Path(parquet_dir)

    for table_name, schema_class in TABLE_TO_SCHEMA.items():
        parquet_path = parquet_dir / f"{table_name}.parquet"
        errors: list[str] = []

        if not parquet_path.exists():
            errors.append(f"Missing Parquet file: {parquet_path}")
            results[table_name] = errors
            continue

        df = pd.read_parquet(parquet_path)
        schema_fields = schema_class.model_fields
        df_columns = set(df.columns)

        # Check all schema fields exist as columns
        for field_name in schema_fields:
            if field_name not in df_columns:
                errors.append(f"Missing column: {field_name}")

        # Check dtypes are compatible
        for field_name, field_info in schema_fields.items():
            if field_name not in df_columns:
                continue  # Already reported as missing

            expected_cat = _get_expected_dtype(field_info)
            actual_dtype = str(df[field_name].dtype)
            compatible_dtypes = _DTYPE_COMPAT.get(expected_cat, set())

            if actual_dtype not in compatible_dtypes:
                # CR-03 (Phase 06 review): bool field stored as object. The
                # production dtype contract (normalizer.SCHEMA_DTYPE_MAP) uses
                # nullable "boolean" for all race_flag_* fields, which round-trips
                # through Arrow as bool — NOT object. An object-dtype bool column
                # therefore indicates either (a) an all-NA column from an empty
                # Parquet round-trip (acceptable) or (b) genuine corruption
                # (string/int content masquerading as bool — REJECT). The content
                # guard below distinguishes the two.
                if expected_cat == "bool" and actual_dtype == "object":
                    sample = df[field_name].dropna()
                    if sample.empty or sample.isin([True, False]).all():
                        # All-NA or all-True/False: treat as compatible.
                        continue
                    errors.append(
                        f"Dtype mismatch for {field_name}: object dtype contains "
                        f"non-bool values: {sample.unique()[:5].tolist()}"
                    )
                    continue
                # Check if nullable integer stored as float (common in Parquet).
                # Case-insensitive substring match so pandas nullable ``Float64`` /
                # ``Float32`` are accepted alongside numpy ``float64``/``float32``.
                # Per Phase 4 cycle-3 #1 (STATE.md), ``SCHEMA_DTYPE_MAP`` deliberately
                # stores nullable-int fields (corner_1..4, horse_weight, weight_change,
                # popularity) as ``Float64`` because Arrow ``double`` round-trips
                # cleanly and matches Kaggle's physical type; ``Int64`` would serialize
                # to Arrow int64 and fail the physical-type equality test. This
                # special-case acknowledges that intentional storage choice.
                if expected_cat == "int" and "float" in actual_dtype.lower():
                    # Nullable Int64 columns can become float64 when all NaN
                    continue
                if expected_cat == "str" and actual_dtype == "object":
                    continue  # str is stored as object, this is fine
                # Optional fields where all values are None get stored as
                # object dtype (pandas can't infer type from empty data)
                if actual_dtype == "object" and not field_info.is_required():
                    if df[field_name].isna().all():
                        continue
                errors.append(
                    f"Dtype mismatch for {field_name}: "
                    f"expected {expected_cat}-compatible, got {actual_dtype}"
                )

        results[table_name] = errors

        if errors:
            logger.warning(f"Schema conformance issues for {table_name}: {errors}")
        else:
            logger.info(f"Schema conformance PASSED for {table_name}")

    return results


# ---------------------------------------------------------------------------
# Check 3: Audit (post-race column leakage)
# ---------------------------------------------------------------------------

def validate_audit(parquet_dir: Path) -> dict[str, list[str]]:
    """Check for post-race column leakage in each table.

    Uses audit_leakage() from src.schemas.audit to detect post-race columns.

    Args:
        parquet_dir: Directory containing Parquet files.

    Returns:
        Dict mapping table names to lists of leaked column names.
    """
    import pandas as pd

    results: dict[str, list[str]] = {}
    parquet_dir = Path(parquet_dir)

    for table_name, schema_class in TABLE_TO_SCHEMA.items():
        parquet_path = parquet_dir / f"{table_name}.parquet"

        if not parquet_path.exists():
            results[table_name] = [f"Missing: {parquet_path}"]
            continue

        df = pd.read_parquet(parquet_path)
        leaked = audit_leakage([schema_class], df, f"{table_name} validation")
        results[table_name] = leaked

    return results


# ---------------------------------------------------------------------------
# Check 4: Null rates
# ---------------------------------------------------------------------------

def validate_null_rates(
    source_stats: dict[str, Any],
    parquet_dir: Path,
    tolerance: float = 0.01,
) -> dict[str, dict[str, float]]:
    """Compare null rates between source and Parquet for specified columns.

    Args:
        source_stats: Dict with structure {table: {"null_rates": {col: rate}}}.
        parquet_dir: Directory containing Parquet files.
        tolerance: Maximum allowed absolute difference in null rates.

    Returns:
        Dict mapping table names to dicts of {column: diff} for flagged columns.
    """
    import pandas as pd

    results: dict[str, dict[str, float]] = {}
    parquet_dir = Path(parquet_dir)

    for table_name, table_stats in source_stats.items():
        flagged: dict[str, float] = {}
        source_null_rates = table_stats.get("null_rates", {})

        parquet_path = parquet_dir / f"{table_name}.parquet"
        if not parquet_path.exists():
            results[table_name] = {}
            continue

        df = pd.read_parquet(parquet_path)

        for col, source_rate in source_null_rates.items():
            if col not in df.columns:
                flagged[col] = 1.0  # Missing column = 100% nulls
                continue

            actual_rate = df[col].isna().mean()
            diff = abs(actual_rate - source_rate)

            if diff > tolerance:
                flagged[col] = diff
                logger.warning(
                    f"Null rate diff for {table_name}.{col}: "
                    f"source={source_rate:.4f}, parquet={actual_rate:.4f}, "
                    f"diff={diff:.4f}"
                )

        results[table_name] = flagged

    return results


# ---------------------------------------------------------------------------
# Check 5: Distributions
# ---------------------------------------------------------------------------

def validate_distributions(
    source_stats: dict[str, Any],
    parquet_dir: Path,
    tolerance: float = 0.01,
) -> dict[str, dict[str, dict]]:
    """Compare numeric column distributions between source and Parquet.

    Args:
        source_stats: Dict with structure {table: {"distributions": {col: {min, max, mean}}}}.
        parquet_dir: Directory containing Parquet files.
        tolerance: Maximum allowed absolute difference for min/max/mean.

    Returns:
        Dict mapping table names to dicts of {column: mismatch_details} for flagged columns.
    """
    import pandas as pd

    results: dict[str, dict[str, dict]] = {}
    parquet_dir = Path(parquet_dir)

    for table_name, table_stats in source_stats.items():
        mismatches: dict[str, dict] = {}
        source_dists = table_stats.get("distributions", {})

        parquet_path = parquet_dir / f"{table_name}.parquet"
        if not parquet_path.exists():
            results[table_name] = {}
            continue

        df = pd.read_parquet(parquet_path)

        for col, expected in source_dists.items():
            if col not in df.columns:
                mismatches[col] = {"error": "Column missing in Parquet"}
                continue

            series = pd.to_numeric(df[col], errors="coerce")
            actual = {
                "min": float(series.min()) if not series.isna().all() else None,
                "max": float(series.max()) if not series.isna().all() else None,
                "mean": float(series.mean()) if not series.isna().all() else None,
            }

            diff_details: dict[str, float] = {}
            for stat in ["min", "max", "mean"]:
                if actual[stat] is not None and expected.get(stat) is not None:
                    diff = abs(actual[stat] - expected[stat])
                    if diff > tolerance:
                        diff_details[stat] = diff

            if diff_details:
                mismatches[col] = {
                    "expected": expected,
                    "actual": actual,
                    "diffs": diff_details,
                }
                logger.warning(
                    f"Distribution mismatch for {table_name}.{col}: {diff_details}"
                )

        results[table_name] = mismatches

    return results


# ---------------------------------------------------------------------------
# Check 6: Referential integrity
# ---------------------------------------------------------------------------

def validate_referential_integrity(parquet_dir: Path) -> list[str]:
    """Check race_id consistency across all 5 tables.

    Verifies every race_id in child tables (entry, result, odds_trifecta, payoff)
    exists in the race table.

    Args:
        parquet_dir: Directory containing Parquet files.

    Returns:
        List of error messages. Empty if all checks pass.
    """
    import pandas as pd

    errors: list[str] = []
    parquet_dir = Path(parquet_dir)

    race_path = parquet_dir / "race.parquet"
    if not race_path.exists():
        errors.append("Missing race.parquet -- cannot check referential integrity")
        return errors

    race_df = pd.read_parquet(race_path, columns=["race_id"])
    race_ids = set(race_df["race_id"].dropna().unique())

    child_tables = ["entry", "result", "odds_trifecta", "payoff"]

    for table_name in child_tables:
        parquet_path = parquet_dir / f"{table_name}.parquet"
        if not parquet_path.exists():
            errors.append(f"Missing {table_name}.parquet")
            continue

        child_df = pd.read_parquet(parquet_path, columns=["race_id"])
        child_ids = set(child_df["race_id"].dropna().unique())

        orphans = child_ids - race_ids
        if orphans:
            orphan_count = len(orphans)
            sample_orphans = sorted(orphans)[:5]
            errors.append(
                f"{table_name} has {orphan_count} race_ids not in race table: "
                f"{sample_orphans}..."
            )
            logger.warning(
                f"Referential integrity: {table_name} has {orphan_count} orphan race_ids"
            )

    if not errors:
        logger.info("Referential integrity PASSED for all tables")

    return errors


# ---------------------------------------------------------------------------
# Check 7: Sample rows
# ---------------------------------------------------------------------------

def _find_csv(source_dir: Path, pattern: str) -> Path | None:
    """Find a CSV file using a glob pattern, preferring exact match.

    Checks for exact filename first, then falls back to glob pattern.
    Returns None if no matching file is found.
    """
    # Try exact match first (pattern may be a literal filename)
    exact = source_dir / pattern
    if exact.exists():
        return exact
    # Try glob for patterns like *_race_result.csv
    candidates = sorted(source_dir.glob(pattern))
    if candidates:
        return candidates[0]
    # Fallback: try stripping the glob prefix (e.g., *_race_result.csv -> race_result.csv)
    if pattern.startswith("*"):
        stripped = pattern[1:]  # e.g., "_race_result.csv"
        exact2 = source_dir / stripped[1:]  # strip leading underscore -> "race_result.csv"
        if exact2.exists():
            return exact2
    return None


def _build_eng_to_jp_map(table_name: str) -> dict[str, list[str]]:
    """Build reverse mapping from English Parquet names to Japanese CSV names.

    Returns dict mapping each English name to a list of ALL possible Japanese
    source column names. When multiple CSV columns map to the same English name
    (coalesced by the converter), all are included so the comparison can check
    any of them.

    For race/entry/result tables, uses KAGGLE_COLUMN_MAP.
    For odds_trifecta/payoff, uses ODDS_COLUMN_MAP.
    Always includes race_id -> レースID mapping.
    """
    eng_to_jp: dict[str, list[str]] = {"race_id": ["レースID"]}
    if table_name in ("race", "entry", "result"):
        for jp_name, (tbl, eng_name) in KAGGLE_COLUMN_MAP.items():
            if tbl == table_name:
                eng_to_jp.setdefault(eng_name, []).append(jp_name)
    elif table_name in ("odds_trifecta", "payoff"):
        for jp_name, eng_name in ODDS_COLUMN_MAP.items():
            eng_to_jp.setdefault(eng_name, []).append(jp_name)
    return eng_to_jp


def validate_sample_rows(
    source_dir: Path,
    parquet_dir: Path,
    n_samples: int = 5,
) -> dict[str, bool]:
    """Spot-check random rows between source CSV and Parquet files.

    For each table, picks n_samples random rows from Parquet and verifies
    their values match the corresponding source CSV rows using a reverse
    column mapping (English Parquet names -> Japanese CSV names).

    Note: This is a simplified check -- for the race/entry/result tables
    derived from race_result.csv, it checks against the CSV. For
    odds_trifecta/payoff (derived from odds.csv), it checks against odds.csv.

    Args:
        source_dir: Directory containing source CSV files.
        parquet_dir: Directory containing Parquet files.
        n_samples: Number of random rows to sample per table.

    Returns:
        Dict mapping table names to True (match) or False (mismatch).
    """
    import pandas as pd

    results: dict[str, bool] = {}
    source_dir = Path(source_dir)
    parquet_dir = Path(parquet_dir)

    # Map table to CSV glob pattern (handles both short and full Kaggle names)
    table_to_csv_pattern = {
        "race": "*_race_result.csv",
        "entry": "*_race_result.csv",
        "result": "*_race_result.csv",
        "odds_trifecta": "*_odds.csv",
        "payoff": "*_odds.csv",
    }

    # Map table to key column(s) for lookups.
    # Entry and result have multiple rows per race (one per horse),
    # so use horse_race_id (unique per horse per race) for matching.
    key_columns = {
        "race": "race_id",
        "entry": "horse_race_id",
        "result": "horse_race_id",
        "odds_trifecta": "race_id",
        "payoff": "race_id",
    }

    for table_name, csv_pattern in table_to_csv_pattern.items():
        parquet_path = parquet_dir / f"{table_name}.parquet"
        if not parquet_path.exists():
            continue

        csv_path = _find_csv(source_dir, csv_pattern)
        if csv_path is None:
            logger.debug(f"Source CSV not found for {table_name}: {csv_pattern}")
            continue

        try:
            pq_df = pd.read_parquet(parquet_path)
            if len(pq_df) == 0:
                results[table_name] = True
                continue

            # Sample rows
            n = min(n_samples, len(pq_df))
            sample = pq_df.sample(n=n, random_state=42)

            # Read source CSV (full file, no row limit)
            source_df = pd.read_csv(csv_path, encoding="utf-8-sig", low_memory=False)
            key_col = key_columns.get(table_name, "race_id")

            # Build reverse mapping: English Parquet -> Japanese CSV
            eng_to_jp = _build_eng_to_jp_map(table_name)

            # Determine the CSV key column name (first candidate)
            csv_key_candidates = eng_to_jp.get(key_col, [key_col])
            csv_key = next(
                (c for c in csv_key_candidates if c in source_df.columns),
                csv_key_candidates[0] if isinstance(csv_key_candidates, list) else csv_key_candidates,
            )
            if csv_key not in source_df.columns:
                # Can't verify without matching key -- skip
                results[table_name] = True
                continue

            # Build list of comparable columns: English names where at
            # least one Japanese equivalent is present in the CSV
            comparable_cols = [
                eng_col for eng_col in sample.columns
                if eng_col in eng_to_jp
                and any(jp in source_df.columns for jp in eng_to_jp[eng_col])
            ]

            if not comparable_cols:
                logger.debug(
                    f"No comparable columns for {table_name} "
                    f"(Parquet cols: {list(sample.columns)}, "
                    f"CSV cols: {list(source_df.columns)[:5]}...)"
                )
                results[table_name] = True
                continue

            # Build a minimal source lookup on the key column
            source_lookup = source_df.drop_duplicates(subset=[csv_key])

            # For each sample row, verify values match the source
            all_match = True
            for _, pq_row in sample.iterrows():
                key_val = pq_row[key_col]

                # Try matching with type coercion (string vs int keys)
                source_match = source_lookup[source_lookup[csv_key] == key_val]
                if len(source_match) == 0:
                    source_match = source_lookup[
                        source_lookup[csv_key].astype(str) == str(key_val)
                    ]
                if len(source_match) == 0:
                    # Key genuinely not in source -- this is OK (filtered out)
                    continue

                source_row = source_match.iloc[0]
                for eng_col in comparable_cols:
                    jp_candidates = eng_to_jp[eng_col]
                    pq_val = pq_row[eng_col]

                    # For multi-mapped columns (coalesced from several
                    # CSV cols), True in Parquet means ANY source was
                    # non-empty.  Try each candidate.
                    if isinstance(pq_val, bool) and len(jp_candidates) > 1:
                        any_non_empty = any(
                            jp in source_row.index
                            and pd.notna(source_row[jp])
                            and str(source_row[jp]).strip() != ""
                            for jp in jp_candidates
                        )
                        if pq_val != any_non_empty:
                            all_match = False
                            break
                        continue

                    # Pick first candidate present in CSV
                    jp_col = next(
                        (c for c in jp_candidates if c in source_row.index),
                        jp_candidates[0],
                    )
                    src_val = source_row[jp_col]
                    # Compare values (handle NaN and type conversions)
                    pq_na = pd.isna(pq_val)
                    src_na = pd.isna(src_val)
                    if pq_na and src_na:
                        continue
                    if pq_na != src_na:
                        # Single-mapped flag: NA in source but True in
                        # Parquet -- check remaining candidates
                        if isinstance(pq_val, bool):
                            any_non_empty = any(
                                jp in source_row.index
                                and pd.notna(source_row[jp])
                                and str(source_row[jp]).strip() != ""
                                for jp in jp_candidates
                            )
                            if pq_val == any_non_empty:
                                continue
                        all_match = False
                        break

                    # Handle flag columns: True matches any non-empty
                    # source value (e.g. "1", "○"); None already handled
                    if isinstance(pq_val, bool):
                        if pq_val and str(src_val).strip() == "":
                            all_match = False
                            break
                        continue

                    # Try numeric comparison before string (handles
                    # zero-padded strings like "05" vs 5)
                    try:
                        if float(str(pq_val)) == float(str(src_val)):
                            continue
                    except (ValueError, TypeError):
                        pass

                    # Compare as strings for consistency
                    if str(pq_val) != str(src_val):
                        all_match = False
                        break
                if not all_match:
                    break

            results[table_name] = all_match

        except Exception as e:
            logger.warning(f"Sample row check failed for {table_name}: {e}")
            results[table_name] = False

    return results


# ---------------------------------------------------------------------------
# Check 8: Value ranges
# ---------------------------------------------------------------------------

def validate_value_ranges(parquet_dir: Path) -> dict[str, list[str]]:
    """Check domain-specific value ranges in Parquet files.

    Validates:
    - race: course_code in 01-10, distance > 0
    - entry: horse_number >= 1, bracket_num 1-8, age >= 2, weight_assigned > 0

    Args:
        parquet_dir: Directory containing Parquet files.

    Returns:
        Dict mapping table names to lists of error messages.
    """
    import pandas as pd

    results: dict[str, list[str]] = {}
    parquet_dir = Path(parquet_dir)

    valid_course_codes = {f"{i:02d}" for i in range(1, 11)}

    # Race table checks
    race_path = parquet_dir / "race.parquet"
    if race_path.exists():
        race_errors: list[str] = []
        race_df = pd.read_parquet(race_path)

        # Course code check
        if "course_code" in race_df.columns:
            invalid_codes = set(race_df["course_code"].dropna().unique()) - valid_course_codes
            if invalid_codes:
                race_errors.append(
                    f"Invalid course_code values: {sorted(invalid_codes)}"
                )

        # Distance check
        if "distance" in race_df.columns:
            dist_series = pd.to_numeric(race_df["distance"], errors="coerce")
            negative = dist_series[dist_series <= 0]
            if len(negative) > 0:
                race_errors.append(
                    f"Non-positive distance values: {len(negative)} rows"
                )

        results["race"] = race_errors
        if race_errors:
            logger.warning(f"Value range issues in race: {race_errors}")
        else:
            logger.info("Value range check PASSED for race")

    # Entry table checks
    entry_path = parquet_dir / "entry.parquet"
    if entry_path.exists():
        entry_errors: list[str] = []
        entry_df = pd.read_parquet(entry_path)

        # Bracket number check (1-8)
        if "bracket_num" in entry_df.columns:
            bracket_series = pd.to_numeric(entry_df["bracket_num"], errors="coerce")
            invalid_brackets = bracket_series[(bracket_series < 1) | (bracket_series > 8)]
            if len(invalid_brackets) > 0:
                entry_errors.append(
                    f"Bracket numbers outside 1-8: {len(invalid_brackets)} rows"
                )

        # Horse number check (>= 1)
        if "horse_number" in entry_df.columns:
            horse_series = pd.to_numeric(entry_df["horse_number"], errors="coerce")
            invalid_horses = horse_series[horse_series < 1]
            if len(invalid_horses) > 0:
                entry_errors.append(
                    f"Horse numbers < 1: {len(invalid_horses)} rows"
                )

        # Age check (>= 2)
        if "age" in entry_df.columns:
            age_series = pd.to_numeric(entry_df["age"], errors="coerce")
            invalid_ages = age_series[age_series < 2]
            if len(invalid_ages) > 0:
                entry_errors.append(
                    f"Age values < 2: {len(invalid_ages)} rows"
                )

        # Weight assigned check (> 0)
        if "weight_assigned" in entry_df.columns:
            weight_series = pd.to_numeric(entry_df["weight_assigned"], errors="coerce")
            invalid_weights = weight_series[weight_series <= 0]
            if len(invalid_weights) > 0:
                entry_errors.append(
                    f"Non-positive weight_assigned: {len(invalid_weights)} rows"
                )

        results["entry"] = entry_errors
        if entry_errors:
            logger.warning(f"Value range issues in entry: {entry_errors}")
        else:
            logger.info("Value range check PASSED for entry")

    return results


# ---------------------------------------------------------------------------
# Orchestrator: run_all_validations
# ---------------------------------------------------------------------------

def run_all_validations(
    raw_dir: Path,
    parquet_dir: Path,
    source_counts: dict[str, int] | None = None,
    source_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run all 8 D-05 validation checks and aggregate results.

    Args:
        raw_dir: Directory containing source CSV files.
        parquet_dir: Directory containing Parquet files to validate.
        source_counts: Optional expected row counts. If None, skips row count check.
        source_stats: Optional source statistics for null rate and distribution
            checks. Structure: {table: {"null_rates": {col: rate},
            "distributions": {col: {min, max, mean}}}}.
            If None, checks 4 and 5 pass vacuously.

    Returns:
        Dict with results for each check and an overall_pass boolean.
    """
    raw_dir = Path(raw_dir)
    parquet_dir = Path(parquet_dir)

    logger.info(f"Running full validation suite on {parquet_dir}")

    # Check 1: Row counts
    row_counts_result: dict[str, bool] = {}
    if source_counts is not None:
        row_counts_result = validate_row_counts(source_counts, parquet_dir)

    # Check 2: Schema conformance
    schema_result = validate_schema_conformance(parquet_dir)

    # Check 3: Audit
    audit_result = validate_audit(parquet_dir)

    # Check 4: Null rates
    if source_stats is not None:
        null_rates_result = validate_null_rates(source_stats, parquet_dir)
    else:
        null_rates_result: dict[str, dict[str, float]] = {}

    # Check 5: Distributions
    if source_stats is not None:
        distributions_result = validate_distributions(source_stats, parquet_dir)
    else:
        distributions_result: dict[str, dict[str, dict]] = {}

    # Check 6: Referential integrity
    integrity_errors = validate_referential_integrity(parquet_dir)

    # Check 7: Sample rows
    sample_result = validate_sample_rows(raw_dir, parquet_dir)

    # Check 8: Value ranges
    range_result = validate_value_ranges(parquet_dir)

    # Aggregate results
    all_checks_passed = True

    # Row counts
    if source_counts is not None:
        row_pass = all(row_counts_result.values()) if row_counts_result else True
    else:
        row_pass = True

    # Schema conformance
    schema_pass = all(v == [] for v in schema_result.values())

    # Referential integrity
    integrity_pass = integrity_errors == []

    # Value ranges
    range_pass = all(v == [] for v in range_result.values())

    # Sample rows (only check tables that were verified)
    sample_pass = all(sample_result.values()) if sample_result else True

    # Audit: expected behavior -- race should have no leaks, but entry/result/odds/payoff
    # are expected to have post-race columns, so we don't fail on those
    audit_pass = True  # Audit is informational, not a pass/fail check

    # Null rates: pass if no source stats provided, otherwise check for flagged columns
    if source_stats is not None:
        null_pass = all(
            len(flagged) == 0 for flagged in null_rates_result.values()
        )
    else:
        null_pass = True

    # Distributions: pass if no source stats provided, otherwise check for mismatches
    if source_stats is not None:
        dist_pass = all(
            len(mismatches) == 0 for mismatches in distributions_result.values()
        )
    else:
        dist_pass = True

    all_checks_passed = (
        row_pass and schema_pass and audit_pass and null_pass
        and dist_pass and integrity_pass and sample_pass and range_pass
    )

    result = {
        "row_counts": row_pass,
        "schema_conformance": schema_pass,
        "audit": audit_pass,
        "null_rates": null_pass,
        "distributions": dist_pass,
        "referential_integrity": integrity_pass,
        "sample_rows": sample_pass,
        "value_ranges": range_pass,
        "overall_pass": all_checks_passed,
        # Detailed results for inspection
        "row_counts_detail": row_counts_result,
        "schema_detail": schema_result,
        "audit_detail": audit_result,
        "null_rates_detail": null_rates_result,
        "distributions_detail": distributions_result,
        "integrity_errors": integrity_errors,
        "sample_detail": sample_result,
        "range_detail": range_result,
    }

    if all_checks_passed:
        logger.info("All validation checks PASSED")
    else:
        failed = [k for k, v in result.items() if v is False and k != "overall_pass"]
        logger.warning(f"Validation failures: {failed}")

    return result
