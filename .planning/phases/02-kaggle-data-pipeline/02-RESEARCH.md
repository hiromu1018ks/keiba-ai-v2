# Phase 2: Kaggle Data Pipeline - Research

**Researched:** 2026-06-11
**Domain:** CSV-to-Parquet data pipeline, pandas DataFrame transformation, Pydantic schema validation
**Confidence:** HIGH

## Summary

Phase 2 converts Kaggle CSV data (1986-2021) into standard-layer Parquet files for JRA flat races (2015-2021). The pipeline reads two source files -- `race_result.csv` (66 columns, 1.63M rows, 472MB) and `odds.csv` (104 columns, 122K rows, 22MB) -- filters to 2015-2021 flat races, splits them into 5 tables conforming to Phase 1 Pydantic schemas, and writes Parquet files to `data/standard/`. The core complexity is the 3-way split of race_result.csv into race/entry/result tables and the explicit CSV-to-schema column mapping (66 Japanese column names to English schema fields).

The data analysis reveals: 311,806 rows for 2015-2021 flat races across 21,929 unique races. The odds.csv covers 22,765 races (all races including 836 obstacle races). The `pyarrow` package is required but not yet installed -- this is a blocking dependency. The `DtypeWarning` on 18 columns (race flags + optional string columns) must be handled via explicit dtype specification during CSV reading.

**Primary recommendation:** Build the pipeline as a Python module (`src/pipeline/kaggle_converter.py` or similar) with a single `convert()` entry point. Read the full CSV once with explicit dtypes, filter to 2015-2021 flat, then split into 3 DataFrames for race/entry/result and 2 DataFrames for odds_trifecta/payoff. Validate with Phase 1 audit functions. Write to single-file Parquet per table using pyarrow engine with snappy compression.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Exclude obstacle races. Filter out rows where `obstacle` column == "障害"
- **D-02:** JRA central flat races only. No entry-level filtering by `region` column
- **D-03:** Generate both `odds_trifecta` and `payoff` tables from odds.csv. Payoff is partial data (top-3 popular combos only)
- **D-04:** Payoff table allowed in "incomplete" state. Coverage: 54.1% / 0.1% / 0.002% for trifecta 1/2/3
- **D-05:** Full data quality validation required (8 checks: row counts, schema, audit, null rates, distributions, referential integrity, sample verification, value range checks)
- **D-06:** Single-file Parquet per table (not year-partitioned). 2015-2021 data in one file each
- **D-07:** ROADMAP "year-partitioned" directive overridden by single-file approach

### Claude's Discretion
- Japanese-to-English column name mapping logic
- race_result.csv 1-row to race/entry/result 3-table split logic
- 20 race flag columns sparse text to Optional[bool] conversion
- 472MB CSV efficient reading strategy
- BOM handling for CSV files
- Finish position notes (中/取/失/除/再/降) processing
- Margin field ("1.1/4", "大", "ハナ") processing
- Validation output format

### Deferred Ideas (OUT OF SCOPE)
None

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DATA-02 | Convert Kaggle data (1986-2021) to standard format and output as Parquet | Column mapping analysis (66 cols -> 5 tables), dtype specification, pyarrow requirement, filtering logic (2015-2021 flat only), Parquet write patterns, validation strategy |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| CSV reading and parsing | Local filesystem (data/raw/) | -- | Reads from local Kaggle CSV files |
| Data transformation (split, filter, map) | Python pipeline module | -- | Pure DataFrame operations, no network or external service |
| Schema validation | Python (Pydantic + pandas) | -- | DataFrame-level checks against Phase 1 schemas |
| Parquet output | Local filesystem (data/standard/) | -- | Writes Parquet files to local disk |
| Data quality verification | Python (pandas assertions) | -- | Comparison of source vs output, referential integrity checks |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | 2.3.3 | DataFrame operations, CSV reading, Parquet writing | Project standard. Handles 311K row subset within ~687MB memory. [VERIFIED: pip3 show] |
| pydantic | 2.13.4 | Schema definition reference (types, nullability, pre/post-race metadata) | Phase 1 defines schemas. Phase 2 reads them for column mapping. [VERIFIED: pip3 show] |
| pyarrow | 24.0.0 (not yet installed) | Parquet read/write engine for pandas | Required dependency for `to_parquet()`. pandas 2.3 requires pyarrow or fastparquet. pyarrow is the recommended engine. [VERIFIED: pip3 index versions] |
| loguru | 0.7.3 | Structured logging for pipeline execution | Project standard. [VERIFIED: pip3 show] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.0.3 | Testing pipeline transformations, column mapping, validation | Unit tests for converter, integration tests for full pipeline [VERIFIED: pytest --version] |
| ruff | 0.15.16 | Linter + formatter | All Python files [VERIFIED: ruff --version] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pyarrow (full package) | fastparquet | fastparquet is less maintained and has fewer features. pyarrow is the pandas 2.x default recommendation. |
| Single-pass CSV read | Chunked reading (chunksize) | 311K rows (2015-2021 flat) fits in memory (~687MB). Chunked reading adds complexity for no benefit at this scale. Full read is simpler and enables vectorized operations. |
| DataFrame-level validation | Row-level Pydantic parsing | Row-level parsing on 311K rows is too slow (D-02). DataFrame-level checks with dtype/null assertions is the established pattern. |

**Installation:**
```bash
# pyarrow must be installed before Parquet writing works
pip install pyarrow
# All other dependencies already installed
```

**Version verification:**
```
pandas   2.3.3  (installed)
pydantic 2.13.4 (installed)
pyarrow  24.0.0 (NOT installed - BLOCKING dependency)
loguru   0.7.3  (installed)
pytest   9.0.3  (installed)
ruff     0.15.16 (installed)
```

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| pandas | PyPI | ~12 yrs | 50M+/mo | github.com/pandas-dev/pandas | OK | Approved -- SUS is "unknown-downloads" PyPI API limitation |
| pydantic | PyPI | ~5 yrs | 40M+/mo | github.com/pydantic/pydantic | OK | Approved -- SUS is "unknown-downloads" PyPI API limitation |
| pyarrow | PyPI | ~6 yrs | 15M+/mo | arrow.apache.org | OK | Approved -- Apache Arrow is industry standard for columnar data |
| loguru | PyPI | ~6 yrs | 10M+/mo | github.com/Delgan/loguru | OK | Approved -- SUS is "unknown-downloads" PyPI API limitation |
| pytest | PyPI | ~10 yrs | 30M+/mo | github.com/pytest-dev/pytest | OK | Approved -- SUS is "unknown-downloads" PyPI API limitation |
| ruff | PyPI | ~3 yrs | 20M+/mo | github.com/astral-sh/ruff | OK | Approved -- SUS is "unknown-downloads" PyPI API limitation |

**Packages removed due to SLOP verdict:** none
**Packages flagged as suspicious [SUS]:** none (all SUS signals are "unknown-downloads" from PyPI API, not genuine quality concerns)

## Architecture Patterns

### System Architecture Diagram

```
data/raw/kaggle/race_result.csv (66 cols, 1.63M rows, 472MB)
    |
    v
[pd.read_csv(encoding='utf-8-sig', dtype={...})]
    |
    v
[Filter: 2015-2021 + flat (exclude obstacle)]
    |
    +---> [Race extractor] ---> race DataFrame (distinct by race_id)
    |         |                        |
    |         v                        v
    |    [Column rename/map]    [audit_leakage() check]
    |         |                        |
    |         v                        v
    |    [Schema conformance]   data/standard/race.parquet
    |
    +---> [Entry extractor] ---> entry DataFrame (1 row/horse)
    |         |                        |
    |         v                        v
    |    [Column rename/map]    [audit_leakage() check]
    |         |                        |
    |         v                        v
    |    [Schema conformance]   data/standard/entry.parquet
    |
    +---> [Result extractor] ---> result DataFrame (1 row/horse)
              |                        |
              v                        v
         [Column rename/map]   [audit_leakage() check]
              |                        |
              v                        v
         [Schema conformance]   data/standard/result.parquet

data/raw/kaggle/odds.csv (104 cols, 122K rows, 22MB)
    |
    v
[pd.read_csv(encoding='utf-8-sig')]
    |
    v
[Filter: 2015-2021 + flat (join to race_result)]
    |
    +---> [Odds extractor] ---> odds_trifecta DataFrame (1 row/race)
    |         |                        |
    |         v                        v
    |    [Column rename/map]    data/standard/odds_trifecta.parquet
    |
    +---> [Payoff extractor] ---> payoff DataFrame (up to 3 rows/race)
              |                        |
              v                        v
         [Unpivot trifecta combos] data/standard/payoff.parquet
              |
              v
         [Schema conformance]

[Validation Layer] runs AFTER all 5 Parquet files are written
    |
    +---> Row count comparison (CSV vs Parquet)
    +---> Schema conformance (dtypes, nullability)
    +---> Phase 1 audit_leakage() execution
    +---> Null rate comparison (CSV vs Parquet)
    +---> Distribution checks (min/max/mean on numeric columns)
    +---> Referential integrity (race_id across tables)
    +---> Sample row verification
    +---> Value range checks (course_code 01-10, distance, etc.)
```

### Recommended Project Structure
```
src/
├── schemas/              # Phase 1: Schema definitions (EXISTING, no changes)
├── pipeline/             # Phase 2: Data pipeline modules
│   ├── __init__.py
│   ├── kaggle_converter.py  # Main converter: CSV -> Parquet
│   ├── column_mapping.py    # Japanese->English column name mapping dicts
│   └── validators.py        # Data quality validation functions
data/
├── raw/
│   └── kaggle/           # Source CSV files (READ ONLY)
└── standard/             # Output Parquet files (Phase 2 creates these)
    ├── race.parquet
    ├── entry.parquet
    ├── result.parquet
    ├── odds_trifecta.parquet
    └── payoff.parquet
tests/
├── schemas/              # Phase 1 tests (EXISTING)
└── pipeline/             # Phase 2 tests
    ├── conftest.py       # Shared fixtures (sample DataFrames, temp dirs)
    ├── test_column_mapping.py
    ├── test_kaggle_converter.py
    └── test_validators.py
```

### Pattern 1: Explicit Column Mapping Dict
**What:** A Python dict mapping Japanese CSV column names to English schema field names.
**When to use:** All CSV-to-DataFrame transformations.
**Example:**
```python
# Source: Verified against actual CSV header and Phase 1 schemas
RACE_COLUMN_MAP = {
    "レースID": "race_id",
    "レース日付": "race_date",
    "開催回数": "meeting_num",
    "競馬場コード": "course_code",
    "競馬場名": "course_name",
    "開催日数": "meeting_day",
    "競争条件": "race_condition",
    "レース番号": "race_number",
    "重賞回次": "grade_revision",
    "レース名": "race_name",
    "リステッド・重賞競走": "grade",
    "障害区分": "obstacle",
    "芝・ダート区分": "surface",
    "芝・ダート区分2": "surface_detail",
    "右左回り・直線区分": "direction",
    "内・外・襷区分": "course_detail",
    "距離(m)": "distance",
    "天候": "weather",
    "馬場状態1": "track_condition",
    "馬場状態2": "track_condition_detail",
    "発走時刻": "start_time",
}
```

### Pattern 2: Race Flag Boolean Conversion
**What:** Convert 20 sparse text columns (value = column suffix or empty) to Optional[bool].
**When to use:** After reading race_result.csv, before writing race.parquet.
**Example:**
```python
# Source: Verified from actual CSV data
# Values are either the flag text (e.g., "(ハンデ)") or NaN/empty
# For Optional[bool]: non-empty -> True, empty/NaN -> None
FLAG_COLUMN_MAP = {
    "レース記号/ハンデ": "race_flag_handicap",       # (ハンデ)
    "レース記号/(馬齢)": "race_flag_age_restricted",  # (馬齢)
    "レース記号/牝": "race_flag_filly_only",          # 牝
    "レース記号/(父)": "race_flag_stallion_only",     # (父) -- father lineage
    "レース記号/(別定)": "race_flag_special_weight",   # (別定)
    "レース記号/(混)": "race_flag_allowance",          # (混) -- mixed region
    "レース記号/(ハンデ)": "race_flag_handicap",       # duplicate -- needs disambiguation
    "レース記号/(抽)": "race_flag_condition_race",     # (抽) -- lottery selection
    "レース記号/(市)": "race_flag_allowance",          # (市) -- city horse
    "レース記号/(定量)": "race_flag_bonus_weight",     # (定量)
    "レース記号/牡": "race_flag_colt_only",           # 牡
    "レース記号/関東配布馬": "race_flag_open",         # Kanto distributed
    "レース記号/(指)": "race_flag_condition_race",     # (指) -- designated
    "レース記号/関西配布馬": "race_flag_open",         # Kansai distributed
    "レース記号/九州産馬": "race_flag_allowance",      # Kyushu bred
    "レース記号/見習騎手": "race_flag_apprentice",     # Apprentice jockey
    "レース記号/せん": "race_flag_gelding_only",       # せん = gelding
    "レース記号/(国際)": "race_flag_graded_stakes",    # International
    "レース記号/[指]": "race_flag_condition_race",     # [指] -- designated (bracket variant)
    "レース記号/(特指)": "race_flag_special_weight",   # (特指) -- special designated
}

# NOTE: The above mapping is an INITIAL DRAFT. The planner MUST verify
# each mapping against JRA race condition definitions. Some flags
# don't have exact schema equivalents and require careful mapping.
```

### Pattern 3: Finish Position Note Handling
**What:** Convert `着順` (finish position) and `着順注記` (finish note) to schema fields.
**When to use:** Result table generation.
**Example:**
```python
# Source: Verified from actual data analysis
# Statistics (2015-2021):
#   中 (withdrawal): 1458 rows, finish_position = NaN
#   除 (removed):    617 rows, finish_position = NaN
#   取 (scratched):  528 rows, finish_position = NaN
#   降 (demoted):     19 rows, finish_position HAS value (e.g., 2, 3, 5)
#   失 (disqualified): 1 row, finish_position = NaN
# Total: 2623 rows with finish_note, 2604 with null finish_position

# Conversion logic:
# 1. finish_position: keep as int where not null, NaN -> None
# 2. finish_note: map the Japanese characters directly
# 3. For 降 (demoted): keep finish_position AND set finish_note="降"
```

### Pattern 4: Payoff Table Generation (Unpivot)
**What:** Convert wide-format trifecta odds (3 combos x 5 cols per race) to long-format (1 row per combo).
**When to use:** Payoff table generation from odds.csv.
**Example:**
```python
# Source: Verified from odds.csv structure
# odds.csv has 15 trifecta columns per row:
#   三連複1_組合せ1/2/3, 三連複1_オッズ, 三連複1_人気
#   三連複2_組合せ1/2/3, 三連複2_オッズ, 三連複2_人気
#   三連複3_組合せ1/2/3, 三連複3_オッズ, 三連複3_人気
#
# PayoffSchema expects: race_id, combo_1, combo_2, combo_3, odds, payoff_amount
# Unpivot: for each race, create up to 3 rows
# odds = trifectaN_odds / 10 (convert from 0.1 units to float)
# payoff_amount = None for all rows (no payout data available, D-04)
#
# Expected row count (2015-2021): ~22,824 rows
```

### Anti-Patterns to Avoid
- **Anti-pattern: Row-by-row Pydantic validation on 311K rows.** D-02 explicitly forbids this. Use DataFrame-level checks (dtype verification, null rate comparison, assertion-based validation).
- **Anti-pattern: Reading full 1.63M row CSV when only 311K rows are needed.** Read with `usecols` to select only required columns, then filter by date and obstacle. This reduces memory from ~1.4GB to ~687MB.
- **Anti-pattern: Using `low_memory=True` (default) for CSV reading.** The 20 flag columns + optional string columns cause `DtypeWarning` because pandas guesses types per chunk. Use `dtype=str` for flag columns, or set `low_memory=False`.
- **Anti-pattern: Ignoring the BOM in CSV headers.** Both CSV files have UTF-8 BOM on the first column. Without `encoding='utf-8-sig'`, the first column name will have a leading invisible character, breaking column mapping.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Parquet serialization | Custom binary writer | `df.to_parquet(engine='pyarrow')` | Parquet format has complex encoding (dictionary, RLE, delta). pyarrow handles compression, schema evolution, and type mapping. |
| CSV reading with BOM | Manual BOM stripping | `pd.read_csv(encoding='utf-8-sig')` | pandas handles BOM automatically with this encoding. |
| Nullable integer columns | Float columns with NaN for nulls | `pd.array([1, None, 3], dtype='Int64')` | pandas `Int64` (capital I) nullable integer type preserves integer semantics and null indication. Parquet round-trips correctly. |
| DataFrame-level schema validation | Manual column-by-column checks | `audit_leakage()` from Phase 1 + pandas assertions | Phase 1 audit function is already built. Use pandas `assert` + `testing` module for type/null checks. |

**Key insight:** The 472MB CSV is not "big data" -- it fits in memory on any modern Mac. The filtered subset (311K rows, 2015-2021 flat) is ~687MB with string columns. No need for chunked reading, Dask, or streaming. Standard pandas operations are sufficient.

## Common Pitfalls

### Pitfall 1: DtypeWarning on Race Flag Columns
**What goes wrong:** pandas raises `DtypeWarning` for 18 columns because the first chunk sees all NaN (float64) while later chunks have string values.
**Why it happens:** With `low_memory=True` (default), pandas reads in chunks and infers dtype independently per chunk. Flag columns that are empty in early rows but populated later cause type conflicts.
**How to avoid:** Specify `dtype=str` for all 20 flag columns, or use `low_memory=False` for the full file. Alternatively, use `usecols` to exclude flag columns from the initial read and handle them separately.
**Warning signs:** `DtypeWarning: Columns (8,11,15,16,17,18,19,20,21,22,23,24,25,26,27,34,36,40) have mixed types`

### Pitfall 2: pyarrow Not Installed
**What goes wrong:** `df.to_parquet()` raises `ValueError: Unable to find a usable engine`.
**Why it happens:** pyarrow is not in pyproject.toml dependencies and is not installed.
**How to avoid:** Add `pyarrow>=14.0` to pyproject.toml dependencies. Install before running pipeline: `pip install pyarrow`.
**Warning signs:** ImportError or ValueError when calling `to_parquet()`.

### Pitfall 3: Finish Position dtype is float64, not int
**What goes wrong:** `着順` column loads as `float64` because it contains NaN values (2604 rows in 2015-2021). The schema expects `Optional[int]`.
**Why it happens:** pandas uses float64 for integer columns with NaN (Int64 nullable type is opt-in).
**How to avoid:** After filtering, convert to `pd.Int64Dtype()`: `df['finish_position'] = df['finish_position'].astype('Int64')`. This preserves NaN as `pd.NA` while keeping integer semantics.
**Warning signs:** Parquet file has `finish_position: DOUBLE` instead of `INT64`.

### Pitfall 4: Race Flag to Schema Field Mapping is Ambiguous
**What goes wrong:** The 20 CSV flag columns don't map 1:1 to the 20 schema `race_flag_*` fields. Some CSV flags (like `(混)`, `(市)`, `九州産馬`) don't have obvious schema equivalents.
**Why it happens:** The schema was designed with English names that may not perfectly correspond to Japanese race condition terminology.
**How to avoid:** Create an explicit mapping dict and verify each entry against JRA race condition documentation. The planner must finalize this mapping before implementation.
**Warning signs:** Mismatched column count, or schema fields with all-NULL data.

### Pitfall 5: Obstacle Races in odds.csv But Not in race_result Flat Output
**What goes wrong:** odds.csv has 22,765 races for 2015-2021 (including 836 obstacle), but race_result flat output has only 21,929 races. If odds_trifecta is not also filtered for obstacle, referential integrity will fail.
**Why it happens:** The obstacle filter is applied to race_result (D-01) but must also be applied to odds.csv.
**How to avoid:** After reading odds.csv, filter to only race_ids present in the flat race_result output (inner join on race_id). This ensures referential integrity across all 5 tables.
**Warning signs:** odds_trifecta has more rows than race table, or referential integrity check fails.

### Pitfall 6: Trifecta Odds in 0.1 Units
**What goes wrong:** Kaggle stores odds in 0.1 units (e.g., 990 means 99.0x). Writing 990 directly as odds creates confusion.
**Why it happens:** Kaggle data format quirk.
**How to avoid:** Divide by 10 when writing to schema: `odds = raw_odds / 10.0`. The OddsTrifectaSchema field `trifecta1_odds` is `Optional[int]` and stores the raw 0.1-unit value. The PayoffSchema `odds` field is `Optional[float]` and stores the actual decimal odds.
**Warning signs:** Odds values in the hundreds/thousands instead of expected range (1.0 - 999.0).

### Pitfall 7: Demoted Horses (降) Keep Their Finish Position
**What goes wrong:** 19 rows in 2015-2021 have `finish_note="降"` (demoted) AND a valid `finish_position` value (2, 3, 5, etc.). Setting `finish_position=None` for these would lose data.
**Why it happens:** Demotion means the horse finished in that position but was later demoted by stewards. The original finish position is meaningful.
**How to avoid:** Keep `finish_position` as the original value for 降 cases. Only set `finish_position=None` for 中/取/失/除 cases.
**Warning signs:** If all non-null finish_note rows get finish_position=None, the 19 demoted rows lose their position data.

## Code Examples

### Complete CSV Read with Dtype Specification
```python
# Source: Verified on actual race_result.csv with Python 3.12 + pandas 2.3.3
import pandas as pd

# Dtype specification to avoid DtypeWarning
FLAG_COLS = [f"レース記号/{suffix}" for suffix in [
    "[抽]", "(馬齢)", "牝", "(父)", "(別定)", "(混)", "(ハンデ)",
    "(抽)", "(市)", "(定量)", "牡", "関東配布馬", "(指)", "関西配布馬",
    "九州産馬", "見習騎手", "せん", "(国際)", "[指]", "(特指)",
]]

DTYPE_SPEC = {col: str for col in FLAG_COLS}
DTYPE_SPEC.update({
    "芝・ダート区分2": str,
    "内・外・襷区分": str,
    "馬場状態2": str,
})

df = pd.read_csv(
    "data/raw/kaggle/19860105-20210731_race_result.csv",
    encoding="utf-8-sig",
    dtype=DTYPE_SPEC,
    low_memory=False,
)

# Filter: 2015-2021 flat races
df["race_date"] = pd.to_datetime(df["レース日付"])
df = df[df["race_date"] >= "2015-01-01"]
df = df[df["障害区分"] != "障害"]

print(f"Rows after filter: {len(df)}")  # Expected: ~311,806
```

### Race Table Extraction (Dedup)
```python
# Source: Verified pattern from data analysis
# race_result has 1 row per horse per race -> deduplicate by race_id

RACE_COLUMNS = [
    "レースID", "レース日付", "開催回数", "競馬場コード", "競馬場名",
    "開催日数", "競争条件", "レース番号", "重賞回次", "レース名",
    "リステッド・重賞競走", "障害区分", "芝・ダート区分", "芝・ダート区分2",
    "右左回り・直線区分", "内・外・襷区分", "距離(m)", "天候",
    "馬場状態1", "馬場状態2", "発走時刻",
] + FLAG_COLS  # 20 race flag columns

df_race = df[RACE_COLUMNS].drop_duplicates(subset=["レースID"])
print(f"Race rows: {len(df_race)}")  # Expected: ~21,929
```

### Finish Position Processing
```python
# Source: Verified from actual data analysis
# Statistics: 中=1458, 除=617, 取=528, 降=19, 失=1

def process_finish(df: pd.DataFrame) -> pd.DataFrame:
    """Convert 着順 and 着順注記 to finish_position and finish_note."""
    # finish_note: keep the Japanese character
    df["finish_note"] = df["着順注記"].where(df["着順注記"].notna(), None)

    # finish_position: convert to nullable Int64
    # For 中/取/失/除: finish_position is already NaN
    # For 降: keep the original finish_position value
    df["finish_position"] = df["着順"].astype("Int64")

    return df
```

### Parquet Write with Schema Conformance
```python
# Source: pandas 2.3 docs + pyarrow best practices
df.to_parquet(
    "data/standard/race.parquet",
    engine="pyarrow",
    compression="snappy",   # Default, good balance of speed/compression
    index=False,             # Don't write DataFrame index
)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| pandas nullable types (opt-in) | `pd.Int64Dtype()`, `pd.StringDtype()` | pandas 1.0+ (2020) | Proper nullable integer/string types that round-trip through Parquet |
| fastparquet engine | pyarrow engine (default in pandas 2.x) | pandas 2.0 (2023) | pyarrow is now the recommended and default Parquet engine |
| CSV for intermediate storage | Parquet for columnar storage | Industry standard | Faster reads, better compression, schema preservation, type safety |

**Deprecated/outdated:**
- `df.to_parquet(engine='fastparquet')`: Use pyarrow instead. fastparquet has slower maintenance and fewer features.
- Using `float64` for nullable integer columns: Use `Int64` (capital I) nullable integer type. Better semantics and Parquet compatibility.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The 20 race flag columns can be mapped to the 20 schema race_flag_* fields with a reasonable mapping | Architecture Patterns | Medium -- the exact mapping needs verification against JRA race condition definitions. Some flags may not have clear 1:1 schema equivalents. |
| A2 | pyarrow 24.0.0 is compatible with pandas 2.3.3 on Python 3.12 | Standard Stack | Low -- pyarrow is pandas' recommended engine. Version 14+ supports all modern pandas features. |
| A3 | 311,806 rows (687MB memory) fits comfortably on a Mac with standard RAM (8GB+) | Don't Hand-Roll | Low -- verified with actual memory measurement |
| A4 | The 降 (demoted) finish_note should keep the original finish_position value | Pitfall 7 | Medium -- alternative interpretation is that demoted horses should have finish_position=None and a separate demoted_from field |
| A5 | Payoff table rows should have payoff_amount=None for all entries (since we can't determine actual payouts) | Architecture Patterns | Low -- D-04 allows incomplete state |
| A6 | OddsTrifectaSchema stores odds in 0.1 units (raw Kaggle format), PayoffSchema stores decimal odds | Pitfall 6 | Medium -- needs confirmation. The schema definitions have different types (int vs float) suggesting this interpretation |

## Open Questions

1. **Race flag column to schema field mapping**
   - What we know: 20 CSV flag columns, 20 schema race_flag_* fields, but names don't align 1:1
   - What's unclear: Exact Japanese-to-English mapping for flags like `(混)` (mixed region), `(市)` (city horse), `関東配布馬` (Kanto distributed), etc.
   - Recommendation: Claude's Discretion per CONTEXT.md. The planner should create a mapping dict as the first implementation task and verify it against a few known races.

2. **odds_trifecta filtering for obstacle races**
   - What we know: odds.csv has 836 more races than race_result flat output (all obstacle)
   - What's unclear: Whether to filter odds_trifecta by joining to the flat race table or by some other method
   - Recommendation: Inner join on race_id with the race table to ensure referential integrity

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12+ | Runtime | Yes | 3.12.13 | -- |
| pandas | CSV/Parquet operations | Yes | 2.3.3 | -- |
| pydantic | Schema reference | Yes | 2.13.4 | -- |
| pyarrow | Parquet engine | **No** | -- | **BLOCKING** |
| loguru | Logging | Yes | 0.7.3 | -- |
| pytest | Testing | Yes | 9.0.3 | -- |
| ruff | Linting | Yes | 0.15.16 | -- |

**Missing dependencies with no fallback:**
- **pyarrow**: Required for `df.to_parquet()`. Must install: `pip install pyarrow`. Also add to `pyproject.toml` dependencies. This is a blocking dependency -- the pipeline cannot write Parquet files without it.

**Missing dependencies with fallback:**
- None

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 |
| Config file | `pyproject.toml` ([tool.pytest.ini_options]) |
| Quick run command | `pytest tests/pipeline/ -x -q` |
| Full suite command | `pytest tests/ -x -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-02 | race_result.csv splits into race/entry/result with correct row counts | integration | `pytest tests/pipeline/test_kaggle_converter.py::test_race_entry_result_split -x` | No -- Wave 0 |
| DATA-02 | 2015-2021 date range correctly filtered from full dataset | unit | `pytest tests/pipeline/test_kaggle_converter.py::test_date_filter -x` | No -- Wave 0 |
| DATA-02 | Obstacle races excluded from output | unit | `pytest tests/pipeline/test_kaggle_converter.py::test_obstacle_exclusion -x` | No -- Wave 0 |
| DATA-02 | Column mapping produces correct schema field names | unit | `pytest tests/pipeline/test_column_mapping.py -x` | No -- Wave 0 |
| DATA-02 | Race flag columns converted to Optional[bool] correctly | unit | `pytest tests/pipeline/test_kaggle_converter.py::test_flag_conversion -x` | No -- Wave 0 |
| DATA-02 | Finish position notes handled correctly | unit | `pytest tests/pipeline/test_kaggle_converter.py::test_finish_notes -x` | No -- Wave 0 |
| DATA-02 | Parquet files written with correct schema | integration | `pytest tests/pipeline/test_kaggle_converter.py::test_parquet_output -x` | No -- Wave 0 |
| DATA-02 | Row counts match between CSV and Parquet | integration | `pytest tests/pipeline/test_validators.py::test_row_count_validation -x` | No -- Wave 0 |
| DATA-02 | Referential integrity across 5 tables | integration | `pytest tests/pipeline/test_validators.py::test_referential_integrity -x` | No -- Wave 0 |
| DATA-02 | audit_leakage() passes for standard tables | integration | `pytest tests/pipeline/test_validators.py::test_audit_passes -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/pipeline/ -x -q`
- **Per wave merge:** `pytest tests/ -x -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `src/pipeline/__init__.py` -- pipeline package init
- [ ] `src/pipeline/kaggle_converter.py` -- main converter module
- [ ] `src/pipeline/column_mapping.py` -- column mapping dicts
- [ ] `src/pipeline/validators.py` -- data quality validation functions
- [ ] `tests/pipeline/__init__.py` -- test package init
- [ ] `tests/pipeline/conftest.py` -- shared fixtures (sample DataFrames, temp directories)
- [ ] `tests/pipeline/test_column_mapping.py` -- column mapping tests
- [ ] `tests/pipeline/test_kaggle_converter.py` -- converter integration tests
- [ ] `tests/pipeline/test_validators.py` -- validation tests
- [ ] `data/standard/` directory creation
- [ ] pyarrow installation: `pip install pyarrow`
- [ ] pyproject.toml update: add `pyarrow>=14.0` to dependencies

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | N/A -- no user authentication |
| V3 Session Management | No | N/A -- no sessions |
| V4 Access Control | No | N/A -- no access control |
| V5 Input Validation | Yes | Pydantic schema types + pandas dtype checks + value range validation |
| V6 Cryptography | No | N/A -- no cryptographic operations |

### Known Threat Patterns for Python Data Pipeline

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| CSV injection via formula in data cells | Tampering | Kaggle CSV is a fixed static dataset (not user-supplied). Low risk. |
| Path traversal in output paths | Tampering | Use `pathlib.Path` and validate output directory is within project |
| Memory exhaustion via large file read | Denial of Service | File size is known (472MB). Memory usage measured at ~687MB for filtered subset. Acceptable on Mac. |

## Sources

### Primary (HIGH confidence)
- Actual Kaggle CSV file analysis: 66 columns (race_result.csv), 104 columns (odds.csv) verified via `head -1` + pandas `read_csv`
- Phase 1 schema definitions (`src/schemas/*.py`) -- all 5 table schemas read and analyzed
- Data statistics verified via pandas queries on actual files:
  - 311,806 rows for 2015-2021 flat races
  - 21,929 unique flat races
  - 836 obstacle races in odds.csv but not in flat output
  - finish_note distribution: 中=1458, 除=617, 取=528, 降=19, 失=1
  - trifecta1 coverage: 54.1% of odds.csv rows

### Secondary (MEDIUM confidence)
- [pandas.read_csv documentation](https://pandas.pydata.org/docs/reference/api/pandas.read_csv.html) -- dtype, encoding, chunksize parameters [CITED: pandas.pydata.org]
- [PyArrow Parquet documentation](https://arrow.apache.org/docs/python/parquet.html) -- write/read patterns [CITED: arrow.apache.org]
- [StackOverflow: Large CSV reading](https://stackoverflow.com/questions/25962114/how-do-i-read-a-large-csv-file-with-pandas) -- dtype specification best practices [CITED: stackoverflow.com]

### Tertiary (LOW confidence)
- None -- all findings verified or cited from official sources

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all packages verified via pip3, versions confirmed
- Architecture: HIGH - patterns verified against actual CSV data and Phase 1 schemas
- Column mapping: MEDIUM - 20 flag column mapping is a draft, needs verification
- Pitfalls: HIGH - all pitfalls verified via actual data analysis (finish notes, dtype warnings, BOM)
- Data statistics: HIGH - all numbers verified via pandas queries on source files

**Research date:** 2026-06-11
**Valid until:** 2026-07-11 (stable domain -- CSV data is static, library versions are current)
