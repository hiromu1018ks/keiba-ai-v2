"""Strict-typed normalizer: parser dict output -> standard-layer Parquet.

Converts the list of ``parse_race_html`` outputs (``{"race": ..., "entries":
..., "results": ...}``) into partitioned Parquet files under
``data/standard/scraped/{YYYYMM}/{race,entry,result}.parquet`` that conform to
the standard-layer schemas established in Phases 1-2
(``src.schemas.{race,entry,result}``) and are physically Arrow-compatible with
the Kaggle-derived ``data/standard/{race,entry,result}.parquet``.

Load-bearing design decisions (all guarded by ``tests/scraper/test_normalizer.py``):

1. **Cycle-1 HIGH #7** -- every output DataFrame is reindexed against
   ``Schema.model_fields`` so all expected columns exist in stable order,
   even for empty input (a zero-row TYPED DataFrame, not a zero-column one).
2. **Cycle-1 HIGH #8 / Cycle-2 #4** -- output is partitioned by ``YYYYMM`` and
   a same-month re-run performs **read-merge-dedup on the primary key**
   (``race_id`` for race, ``horse_race_id`` for entry/result) BEFORE the
   atomic replace. A sentinel row from a prior smoke run survives a full
   same-month re-run, and duplicate primary keys collapse to one.
3. **Cycle-2 #3 (strict dtypes)** -- ``_build_typed_dataframe`` does NOT use
   ``astype(..., errors="ignore")`` anywhere. ``Optional[int]`` fields
   (notably ``finish_position``) use nullable pandas ``Int64`` so that a
   ``None`` value does not silently downgrade the column to ``float64``
   (Kaggle stores ``finish_position`` as Arrow ``int64 nullable=True`` and
   the Cycle-1 ``errors="ignore"`` fallback left it as float64 undetected).
   Genuine conversion failures (e.g. non-numeric text in a numeric column)
   RAISE ``TypeError`` -- the type guarantee is enforced, not aspirational.
4. **Cycle-3 #1 (corner dtype)** -- ``corner_1..corner_4`` are mapped to
   nullable pandas ``Float64`` (NOT ``Int64``). Kaggle's
   ``data/standard/result.parquet`` stores them as NON-NULL Arrow ``double``
   (verified via ``pyarrow.parquet.read_schema``). Nullable ``Float64``
   serializes to Arrow ``double`` (``str(double) == str(double)``) so the
   04-06 ``test_physical_type_equality_for_non_null_kaggle_columns`` check
   (which compares ``str(field.type)``) passes. The Cycle-2 ``Int64`` choice
   was wrong: ``Int64`` serializes to Arrow ``int64`` and would FAIL that
   equality test for all 4 corner columns.
5. **Cycle-2 #6 (entry/result partition)** -- ``EntrySchema`` and
   ``ResultSchema`` have NO ``race_date`` column. ``write_partitioned_parquet``
   accepts ``partition_map: dict[str, datetime.date]`` (``race_id`` ->
   ``race_date``) for entry/result tables. Omitting the map for entry/result
   raises a loud ``KeyError`` (fail-fast, not silent mis-partition).
6. **audit_leakage scoping** -- standard-layer generation does NOT call
   ``audit_leakage`` (Cycle-1 MEDIUM). ``popularity``/``win_odds`` are
   intentionally part of the entry table per D-06/D-03; the leakage audit
   is reserved for feature-layer generation where it actually matters.

Kaggle null-only columns (deliberate promotion to a concrete dtype):

The Kaggle Parquet stores several columns as Arrow ``null`` because Kaggle
has no data for them. In our scraped output we PROMOTE them to a concrete
dtype so they can be populated:

  * ``race_flag_stallion_only``, ``race_flag_colt_only``, ``race_flag_open``,
    ``race_flag_gelding_only``, ``race_flag_amateur``,
    ``race_flag_female_jockey``, ``race_flag_listed``, ``race_flag_maiden``,
    ``race_flag_mare_only``, ``race_flag_stakes``, ``race_flag_young_horse``
    -- promoted to nullable ``boolean`` (bool is a subtype of null).
  * ``obstacle``, ``surface_detail``, ``track_condition_detail`` -- promoted
    to ``string`` (text classification).

The 04-06 ``TestSchemaCompatibility`` checks physical-type EQUALITY only for
columns where Kaggle is NON-null; for null-only Kaggle columns it asserts the
promotion lands on a concrete type (bool/string), which is compatible.
"""

import datetime
import os
from pathlib import Path
from typing import Optional

import pandas as pd
from loguru import logger
from pydantic import BaseModel

from src.schemas.entry import EntrySchema
from src.schemas.race import RaceSchema
from src.schemas.result import ResultSchema

# ---------------------------------------------------------------------------
# SCHEMA_DTYPE_MAP: concrete pandas dtype per field per schema.
#
# Authoritative source for each target: the Kaggle Parquet schema
# (``data/standard/{race,entry,result}.parquet`` via
# ``pyarrow.parquet.read_schema``). Where Kaggle is ``int64 nullable=True`` we
# use nullable pandas ``Int64``; where Kaggle is ``double nullable=True`` we
# use nullable pandas ``Float64``; where Kaggle is ``string`` we use ``string``;
# where Kaggle is a MIX of ``bool`` and ``null`` flag columns we use nullable
# ``boolean``; where Kaggle is ``null`` we promote to a concrete dtype (bool /
# string) per the module docstring.
#
# CYCLE-2 #3 / CYCLE-3 #1 are enforced here. Do NOT use ``errors="ignore"``
# downstream -- this map is the contract.
# ---------------------------------------------------------------------------
SCHEMA_DTYPE_MAP: dict[type[BaseModel], dict[str, str]] = {
    RaceSchema: {
        # Identification (Kaggle: string / int64 nullable)
        "race_id": "string",
        "race_date": "string",
        "meeting_num": "Int64",
        "course_code": "string",
        "course_name": "string",
        "meeting_day": "Int64",
        "race_condition": "string",
        "race_number": "Int64",
        "grade_revision": "string",
        "race_name": "string",
        "grade": "string",
        "obstacle": "string",  # Kaggle null -> string promotion
        # Course / surface (Kaggle: string / int64 nullable)
        "surface": "string",
        "surface_detail": "string",  # Kaggle null -> string promotion
        "direction": "string",
        "course_detail": "string",
        "distance": "Int64",
        # Weather / track (Kaggle: string / null)
        "weather": "string",
        "track_condition": "string",
        "track_condition_detail": "string",  # Kaggle null -> string promotion
        "start_time": "string",
        # 20 race_flag_* -- Kaggle mix of bool / null; nullable boolean
        # serializes to Arrow bool nullable=True in all cases (Cycle-2 #7).
        "race_flag_handicap": "boolean",
        "race_flag_age_restricted": "boolean",
        "race_flag_filly_only": "boolean",
        "race_flag_colt_only": "boolean",
        "race_flag_gelding_only": "boolean",
        "race_flag_mare_only": "boolean",
        "race_flag_stallion_only": "boolean",
        "race_flag_apprentice": "boolean",
        "race_flag_amateur": "boolean",
        "race_flag_female_jockey": "boolean",
        "race_flag_young_horse": "boolean",
        "race_flag_condition_race": "boolean",
        "race_flag_special_weight": "boolean",
        "race_flag_bonus_weight": "boolean",
        "race_flag_stakes": "boolean",
        "race_flag_graded_stakes": "boolean",
        "race_flag_listed": "boolean",
        "race_flag_open": "boolean",
        "race_flag_maiden": "boolean",
        "race_flag_allowance": "boolean",
    },
    EntrySchema: {
        # Identification (Kaggle: string / int64)
        "horse_race_id": "string",
        "race_id": "string",
        "bracket_num": "Int64",
        "horse_number": "Int64",
        # Horse details (string / int64)
        "horse_name": "string",
        "sex": "string",
        "age": "Int64",
        # Race assignment (Kaggle: double nullable)
        "weight_assigned": "Float64",
        # People (string)
        "jockey": "string",
        "trainer": "string",
        "owner": "string",
        # Physical measurements (Kaggle: double nullable -- horse_weight and
        # weight_change are double in Kaggle, NOT int; nullable Float64 matches)
        "horse_weight": "Float64",
        "weight_change": "Float64",
        # Region (string nullable)
        "region": "string",
        # Market signals (Kaggle: double nullable; popularity is double, NOT int)
        "popularity": "Float64",
        "win_odds": "Float64",
    },
    ResultSchema: {
        # Identification (string)
        "horse_race_id": "string",
        "race_id": "string",
        # Finish (int64 nullable / string nullable)
        # Cycle-2 #3: nullable Int64 so None does not become float64.
        "finish_position": "Int64",
        "finish_note": "string",
        # Time / margin (string nullable)
        "finish_time": "string",
        "margin": "string",
        # Corner positions (CYCLE-3 #1: Kaggle double nullable=True -> Float64,
        # NOT Int64; verified via pyarrow.parquet.read_schema on
        # data/standard/result.parquet: corner_1..corner_4 -> double).
        "corner_1": "Float64",
        "corner_2": "Float64",
        "corner_3": "Float64",
        "corner_4": "Float64",
        # Performance (Kaggle: double nullable)
        "last_3f": "Float64",
        "prize_money": "Float64",
    },
}


# ---------------------------------------------------------------------------
# Typed DataFrame construction (Cycle-2 #3 strict path)
# ---------------------------------------------------------------------------


def _build_typed_dataframe(
    rows: list[dict],
    schema: type[BaseModel],
) -> pd.DataFrame:
    """Build a DataFrame reindexed to ``schema.model_fields`` with strict dtypes.

    Parameters
    ----------
    rows : list[dict]
        Row dicts. Keys not in the schema are dropped; missing keys become NA.
    schema : type[BaseModel]
        ``RaceSchema`` / ``EntrySchema`` / ``ResultSchema``. Column order and
        presence come from ``schema.model_fields``.

    Returns
    -------
    pandas.DataFrame
        Columns exactly match ``list(schema.model_fields.keys())`` in that
        order. Empty input produces a zero-row TYPED DataFrame (all columns
        present). Numeric dtypes are the nullable pandas variants (``Int64`` /
        ``Float64`` / ``boolean``) where the Kaggle Parquet is nullable.

    Raises
    ------
    TypeError
        If a column cannot be coerced to its target dtype (e.g. non-numeric
        text in ``finish_position``). The error message names the column and
        schema. This is the opposite of ``errors="ignore"`` -- a contract
        violation is loud.

    Notes
    -----
    Cycle-2 #3: this function does NOT use ``astype(..., errors="ignore")``
    anywhere. Genuine conversion failures raise; nullable dtypes succeed on
    mixed None + int input.
    """
    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    # Reindex to schema fields -- guarantees EVERY expected column exists in
    # stable order, even for empty input (Cycle-1 HIGH #7).
    columns = list(schema.model_fields.keys())
    df = df.reindex(columns=columns)

    dtype_map = SCHEMA_DTYPE_MAP[schema]
    for col, target in dtype_map.items():
        if col not in df.columns:
            # Reindex already inserted the column as all-NA; set its dtype via
            # an empty cast below (the cast succeeds on NA-only data).
            continue
        try:
            df[col] = df[col].astype(target)
        except (TypeError, ValueError) as e:
            raise TypeError(
                f"Column {col!r} could not be coerced to {target!r} for "
                f"{schema.__name__}: {e}"
            ) from e
    return df


# ---------------------------------------------------------------------------
# Integrity validation
# ---------------------------------------------------------------------------


def validate_integrity(
    race_df: pd.DataFrame,
    entry_df: pd.DataFrame,
    result_df: pd.DataFrame,
) -> list[str]:
    """Return a list of human-readable integrity-violation strings.

    Returns an empty list when all checks pass. Each violation is logged at
    WARNING level. The caller decides whether to raise; this function never
    raises.

    Checks
    -------
    a. ``race_id`` unique in the race table.
    b. ``horse_race_id`` unique in the entry table.
    c. ``horse_race_id`` unique in the result table.
    d. entry/result ``horse_race_id`` are 1-to-1 (set equality).
    e. entry ``race_id`` is a subset of race ``race_id`` (FK).
    f. result ``race_id`` is a subset of race ``race_id`` (FK).
    """
    violations: list[str] = []

    # a. unique race_id
    if "race_id" in race_df.columns and not race_df.empty:
        dup_count = int(race_df["race_id"].duplicated().sum())
        if dup_count > 0:
            msg = f"duplicate race_id: {dup_count} duplicated rows in race table"
            violations.append(msg)
            logger.warning(msg)

    # b. unique entry horse_race_id
    if "horse_race_id" in entry_df.columns and not entry_df.empty:
        dup_count = int(entry_df["horse_race_id"].duplicated().sum())
        if dup_count > 0:
            msg = f"duplicate horse_race_id: {dup_count} duplicated rows in entry table"
            violations.append(msg)
            logger.warning(msg)

    # c. unique result horse_race_id
    if "horse_race_id" in result_df.columns and not result_df.empty:
        dup_count = int(result_df["horse_race_id"].duplicated().sum())
        if dup_count > 0:
            msg = f"duplicate horse_race_id: {dup_count} duplicated rows in result table"
            violations.append(msg)
            logger.warning(msg)

    # d. entry/result horse_race_id 1-to-1 (set equality)
    entry_hids = set()
    result_hids = set()
    if "horse_race_id" in entry_df.columns:
        entry_hids = set(entry_df["horse_race_id"].dropna().tolist())
    if "horse_race_id" in result_df.columns:
        result_hids = set(result_df["horse_race_id"].dropna().tolist())
    if entry_hids != result_hids:
        only_entry = entry_hids - result_hids
        only_result = result_hids - entry_hids
        msg = (
            "horse_race_id mismatch: entry/result are not 1-to-1 "
            f"(only-in-entry={len(only_entry)}, only-in-result={len(only_result)})"
        )
        violations.append(msg)
        logger.warning(msg)

    # e. entry race_id FK -> race table
    if (
        "race_id" in entry_df.columns
        and "race_id" in race_df.columns
        and not entry_df.empty
    ):
        race_ids = set(race_df["race_id"].dropna().tolist())
        entry_race_ids = set(entry_df["race_id"].dropna().tolist())
        orphans = entry_race_ids - race_ids
        if orphans:
            sample = sorted(orphans)[:5]
            msg = (
                f"orphan entry race_id: {len(orphans)} entry race_ids not in race "
                f"table; sample={sample}"
            )
            violations.append(msg)
            logger.warning(msg)

    # f. result race_id FK -> race table
    if (
        "race_id" in result_df.columns
        and "race_id" in race_df.columns
        and not result_df.empty
    ):
        race_ids = set(race_df["race_id"].dropna().tolist())
        result_race_ids = set(result_df["race_id"].dropna().tolist())
        orphans = result_race_ids - race_ids
        if orphans:
            sample = sorted(orphans)[:5]
            msg = (
                f"orphan result race_id: {len(orphans)} result race_ids not in race "
                f"table; sample={sample}"
            )
            violations.append(msg)
            logger.warning(msg)

    return violations


# ---------------------------------------------------------------------------
# Partitioned atomic Parquet writes (Cycle-2 #4 merge-dedup + Cycle-2 #6
# partition_map for entry/result)
# ---------------------------------------------------------------------------


def _parse_race_date(value: object) -> Optional[datetime.date]:
    """Parse a RaceSchema race_date (string ``YYYY-MM-DD``) into a ``date``.

    Returns ``None`` for None / empty / unparseable input. Used to build the
    ``partition_map`` for entry/result tables.
    """
    if value is None:
        return None
    if isinstance(value, datetime.date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        # Defensive: race_date malformed in source. Log + return None so the
        # caller's downstream code can detect (entry partition will skip it).
        logger.warning(f"Unparseable race_date {value!r}; partition lookup may fail")
        return None


def _partition_key_from_date(d: Optional[datetime.date]) -> Optional[str]:
    """Format a date as ``YYYYMM`` partition key. Returns None for None."""
    if d is None:
        return None
    return f"{d.year:04d}{d.month:02d}"


def write_partitioned_parquet(
    table_name: str,
    df: pd.DataFrame,
    standard_dir: Path,
    partition_map: Optional[dict[str, datetime.date]] = None,
    primary_key: str = "race_id",
) -> list[Path]:
    """Write ``df`` to date-partitioned Parquet with merge-dedup + atomic rename.

    Output layout: ``standard_dir/scraped/{YYYYMM}/{table_name}.parquet``.
    Each (year, month) present in the data is written as one file. If the
    target file already exists, it is READ and concatenated with the new
    partition, then ``drop_duplicates(subset=[primary_key], keep="last")``
    collapses duplicates (Cycle-2 #4: a sentinel row from a prior run survives
    a same-month re-run; duplicate primary keys collapse to one).

    Cycle-2 #6 (entry/result partition via race_date join): for ``entry`` /
    ``result`` tables, ``df`` has NO ``race_date`` column. The caller must
    supply ``partition_map`` (``race_id`` -> ``race_date``) so each row can be
    routed to the correct ``YYYYMM`` partition. Omitting ``partition_map`` for
    entry/result raises a ``KeyError`` whose message mentions
    ``partition_map`` (fail loud, not silent mis-partition).

    Atomic write per partition: write to ``{path}.tmp`` then ``os.replace``
    (Cycle-1 MEDIUM). Parent dirs are created on demand.

    Parameters
    ----------
    table_name : str
        One of ``"race"``, ``"entry"``, ``"result"``.
    df : pandas.DataFrame
        Already typed via ``_build_typed_dataframe``.
    standard_dir : pathlib.Path
        Root standard directory (e.g. ``data/standard``).
    partition_map : dict[str, datetime.date], optional
        ``race_id`` -> ``race_date`` mapping. Required for ``entry`` /
        ``result`` (they lack a ``race_date`` column). Ignored for ``race``
        (which reads ``df["race_date"]`` directly).
    primary_key : str, default ``"race_id"``
        Column used for ``drop_duplicates``. Use ``"horse_race_id"`` for
        entry/result.

    Returns
    -------
    list[pathlib.Path]
        Paths of the files written, in partition order. For empty input,
        returns a single placeholder path with a zero-row typed schema.
    """
    standard_dir = Path(standard_dir)
    scraped_root = standard_dir / "scraped"

    # Cycle-2 #6: determine partition key (YYYYMM) for each row WITHOUT
    # reading df["race_date"] for entry/result (they have no such column).
    partition_keys: list[Optional[str]] = []
    if table_name == "race":
        # RaceSchema HAS race_date. Read it directly.
        if "race_date" not in df.columns:
            # Defensive: typed DataFrame should always have race_date. Treat
            # empty/missing as a single unpartitioned placeholder.
            partition_keys = [None] * len(df)
        else:
            partition_keys = [
                _partition_key_from_date(_parse_race_date(v))
                for v in df["race_date"].tolist()
            ]
    elif table_name in ("entry", "result"):
        # EntrySchema / ResultSchema have NO race_date. Must use partition_map.
        if partition_map is None:
            raise KeyError(
                "partition_map required for entry/result tables (no race_date column); "
                f"caller must build it from the race table (table={table_name!r})"
            )
        if "race_id" not in df.columns:
            # Empty/typed DataFrame still has race_id as a typed column.
            partition_keys = []
        else:
            partition_keys = []
            for rid in df["race_id"].tolist():
                rd = partition_map.get(rid)
                if rd is None:
                    logger.warning(
                        f"{table_name} race_id {rid!r} not in partition_map; "
                        f"row will be skipped"
                    )
                    partition_keys.append(None)
                else:
                    partition_keys.append(_partition_key_from_date(rd))
    else:
        raise ValueError(
            f"write_partitioned_parquet: unknown table_name {table_name!r} "
            f"(expected one of 'race'/'entry'/'result')"
        )

    # Empty input: produce a single placeholder file with the typed zero-row
    # schema so downstream readers always find a file with the right columns.
    if df.empty:
        placeholder_dir = scraped_root
        placeholder_dir.mkdir(parents=True, exist_ok=True)
        placeholder_path = placeholder_dir / f"{table_name}.parquet"
        _atomic_write_parquet(df, placeholder_path)
        logger.info(
            f"write_partitioned_parquet({table_name!r}): empty input -> "
            f"typed zero-row placeholder at {placeholder_path}"
        )
        return [placeholder_path]

    # Group rows by partition key. Use a temporary key column then groupby so
    # all rows sharing a YYYYMM land in the same partition DataFrame (a naive
    # setdefault loop would overwrite each group with a single-row frame).
    # Rule 1 bug fix: the original setdefault version kept only the LAST row
    # of each partition.
    key_series = pd.Series(partition_keys, index=df.index, dtype="object")
    skipped = int(key_series.isna().sum())
    if skipped > 0:
        logger.warning(
            f"write_partitioned_parquet({table_name!r}): skipped {skipped} rows "
            f"with no partition key"
        )
    non_na_mask = key_series.notna()
    if not non_na_mask.any():
        # All rows had no partition key -- nothing to write (already logged).
        return []
    df_keyed = df.loc[non_na_mask].copy()
    df_keyed["__partition_key__"] = key_series.loc[non_na_mask].values
    groups: dict[str, pd.DataFrame] = {}
    for key, group_df in df_keyed.groupby("__partition_key__", sort=False):
        groups[str(key)] = group_df.drop(columns=["__partition_key__"])

    written: list[Path] = []
    for key in sorted(groups.keys()):
        partition_dir = scraped_root / key
        partition_dir.mkdir(parents=True, exist_ok=True)
        target_path = partition_dir / f"{table_name}.parquet"

        new_partition_df = groups[key]

        # Cycle-2 #4: read-merge-dedup on primary key BEFORE atomic replace.
        # keep="last" so the newer re-run wins on conflict.
        if target_path.exists():
            try:
                existing_df = pd.read_parquet(target_path, engine="pyarrow")
                merged = pd.concat(
                    [existing_df, new_partition_df], ignore_index=True
                )
                merged = merged.drop_duplicates(
                    subset=[primary_key], keep="last"
                )
                merged = merged.reset_index(drop=True)
                # Re-cast to the same dtype map to preserve nullable dtypes
                # (read_parquet may down-cast nullable types).
                merged = _recast_for_storage(merged, table_name)
                write_df = merged
            except Exception as e:
                logger.warning(
                    f"write_partitioned_parquet({table_name!r}): failed to "
                    f"read/merge existing {target_path} ({e!r}); writing new "
                    f"partition only"
                )
                write_df = new_partition_df
        else:
            write_df = new_partition_df

        _atomic_write_parquet(write_df, target_path)
        written.append(target_path)
        logger.info(
            f"write_partitioned_parquet({table_name!r}): wrote {len(write_df)} "
            f"rows -> {target_path}"
        )

    return written


def _recast_for_storage(df: pd.DataFrame, table_name: str) -> pd.DataFrame:
    """Re-apply nullable dtypes after a read_parquet round-trip.

    ``pd.read_parquet`` can convert nullable ``Int64`` / ``Float64`` /
    ``boolean`` back to ``int64`` / ``float64`` / ``object``. We re-cast so
    the merge-dedup output preserves the strict dtype contract.
    """
    schema_map = {
        "race": RaceSchema,
        "entry": EntrySchema,
        "result": ResultSchema,
    }
    schema = schema_map.get(table_name)
    if schema is None:
        return df
    dtype_map = SCHEMA_DTYPE_MAP[schema]
    out = df.copy()
    for col, target in dtype_map.items():
        if col not in out.columns:
            continue
        try:
            out[col] = out[col].astype(target)
        except (TypeError, ValueError):
            # Best-effort recast: leave as-is if the column cannot be coerced
            # (e.g. mixed object that survived an earlier write). The strict
            # path in _build_typed_dataframe enforces dtype on fresh data.
            pass
    return out


def _atomic_write_parquet(df: pd.DataFrame, path: Path) -> None:
    """Write ``df`` to ``path`` atomically via a temp file + ``os.replace``.

    Parent directories are created on demand. Uses ``engine="pyarrow"``,
    ``compression="snappy"``, ``index=False`` (same as kaggle_converter.py).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp_path, engine="pyarrow", compression="snappy", index=False)
    os.replace(tmp_path, path)


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


def normalize_to_parquet(
    parsed_races: list[dict],
    standard_dir: Path = Path("data/standard"),
) -> dict[str, list[Path]]:
    """Normalize parser output dicts to date-partitioned Parquet files.

    Parameters
    ----------
    parsed_races : list[dict]
        Each item is the output of ``parse_race_html``:
        ``{"race": {...}, "entries": [...], "results": [...]}``.
    standard_dir : pathlib.Path, default ``Path("data/standard")``
        Root standard directory. Output goes under
        ``{standard_dir}/scraped/{YYYYMM}/{race,entry,result}.parquet``.

    Returns
    -------
    dict[str, list[pathlib.Path]]
        ``{"race": [paths], "entry": [paths], "result": [paths]}`` -- one path
        per (table, month-partition). Empty input yields a single placeholder
        path per table.

    Notes
    -----
    * Obstacle races (``race["obstacle"] == "障害"``) are dropped from all 3
      tables, mirroring ``kaggle_converter.convert``'s obstacle filter.
    * Cycle-2 #6: the entry/result ``partition_map`` is built from the
      filtered race DataFrame so entry/result rows land under the YYYYMM
      matching their parent race's ``race_date``.
    * Cycle-1 MEDIUM: ``audit_leakage`` is NOT called (standard-layer
      generation; popularity/win_odds belong in the entry table by design).
    * Integrity violations (duplicate keys, FK, 1-to-1) are logged via
      ``validate_integrity`` but do NOT raise unless they would corrupt the
      output (they are warnings; the caller may inspect the return value).
    """
    standard_dir = Path(standard_dir)

    # Accumulate raw rows from parsed_races.
    race_rows: list[dict] = []
    entry_rows: list[dict] = []
    result_rows: list[dict] = []
    for parsed in parsed_races:
        race_rows.append(parsed["race"])
        entry_rows.extend(parsed.get("entries", []))
        result_rows.extend(parsed.get("results", []))

    # Build typed DataFrames (Cycle-2 #3 strict dtypes).
    race_df = _build_typed_dataframe(race_rows, RaceSchema)
    entry_df = _build_typed_dataframe(entry_rows, EntrySchema)
    result_df = _build_typed_dataframe(result_rows, ResultSchema)

    # Obstacle filter: drop obstacle races; propagate to entries/results.
    # Mirrors kaggle_converter.convert line 89 (df = df[df["障害区分"] != "障害"]).
    # IMPORTANT: race_df["obstacle"] is now a nullable string column (per the
    # SCHEMA_DTYPE_MAP cast). ``pd.NA == "障害"`` returns ``pd.NA`` (not False),
    # so a naive ``== "障害"`` mask would propagate NA and drop flat races too.
    # Force NA -> False by combining the equality with a notna guard.
    obstacle_values = race_df["obstacle"]
    obstacle_mask = (obstacle_values == "障害") & obstacle_values.notna()
    dropped_count = int(obstacle_mask.sum())
    if dropped_count > 0:
        logger.info(
            f"normalize_to_parquet: filtering {dropped_count} obstacle race(s) "
            f"from all 3 tables"
        )
        dropped_race_ids = set(race_df.loc[obstacle_mask, "race_id"].dropna().tolist())
        race_df = race_df.loc[~obstacle_mask].reset_index(drop=True)
        if not entry_df.empty:
            entry_df = entry_df.loc[
                ~entry_df["race_id"].isin(dropped_race_ids)
            ].reset_index(drop=True)
        if not result_df.empty:
            result_df = result_df.loc[
                ~result_df["race_id"].isin(dropped_race_ids)
            ].reset_index(drop=True)

    # Integrity validation (warnings only; caller decides).
    violations = validate_integrity(race_df, entry_df, result_df)
    if violations:
        logger.warning(
            f"normalize_to_parquet: {len(violations)} integrity violation(s) "
            f"detected (logged as warnings; output still written)"
        )

    # Cycle-2 #6: build partition_map from the FILTERED race DataFrame so
    # entry/result rows route to the YYYYMM of their parent race.
    partition_map: dict[str, datetime.date] = {}
    for record in race_df.to_dict("records"):
        rid = record.get("race_id")
        rd = record.get("race_date")
        if rid is None:
            continue
        parsed_date = _parse_race_date(rd)
        if parsed_date is not None:
            partition_map[str(rid)] = parsed_date

    # Write partitioned Parquet files.
    race_paths = write_partitioned_parquet(
        "race", race_df, standard_dir, partition_map=None, primary_key="race_id"
    )
    entry_paths = write_partitioned_parquet(
        "entry",
        entry_df,
        standard_dir,
        partition_map=partition_map,
        primary_key="horse_race_id",
    )
    result_paths = write_partitioned_parquet(
        "result",
        result_df,
        standard_dir,
        partition_map=partition_map,
        primary_key="horse_race_id",
    )

    return {"race": race_paths, "entry": entry_paths, "result": result_paths}


__all__ = [
    "normalize_to_parquet",
    "validate_integrity",
    "write_partitioned_parquet",
    "_build_typed_dataframe",
    "SCHEMA_DTYPE_MAP",
]
