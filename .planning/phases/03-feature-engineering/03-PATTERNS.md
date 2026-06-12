# Phase 3: Feature Engineering - Pattern Map

**Mapped:** 2026-06-12
**Files analyzed:** 3 (2 new, 1 modified)
**Analogs found:** 3 / 3

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/pipeline/feature_generator.py` | service (pipeline) | transform (batch) | `src/pipeline/kaggle_converter.py` | exact |
| `tests/pipeline/test_feature_generator.py` | test | transform (batch) | `tests/pipeline/test_kaggle_converter.py` | exact |
| `tests/pipeline/conftest.py` | test fixture | n/a | `tests/pipeline/conftest.py` (modify) | self |

## Pattern Assignments

### `src/pipeline/feature_generator.py` (service/pipeline, batch transform)

**Analog:** `src/pipeline/kaggle_converter.py`

The feature generator follows the exact same structural pattern as the converter: a top-level `generate()` orchestrator function that calls discrete transformation functions, runs the leakage audit, and writes Parquet output.

**Module docstring pattern** (`kaggle_converter.py` lines 1-17):
```python
"""Feature generator for the feature-layer data pipeline.

Reads standard-layer Parquet files (race, entry, result), generates ML-ready
features for Model A (3着内確率), and writes feature Parquet files.

Key design decisions:
- D-01/D-02: 3-race and 5-race lag features for 5 metrics
- D-03: finish_time z-score normalized per course-distance combo
- D-06: jockey/trainer as native categorical + rolling stats
- D-09: debut flag for first-time starters (NaN lag features)
- D-11/D-15: target_top3 for training only; no popularity/win_odds

Output: features_train.parquet (with target_top3) and features_pred.parquet
(without target_top3).
"""
```

**Imports pattern** (`kaggle_converter.py` lines 19-31):
```python
from pathlib import Path

import pandas as pd
from loguru import logger

from src.schemas.audit import audit_leakage
from src.schemas.entry import EntrySchema
from src.schemas.race import RaceSchema
from src.schemas.result import ResultSchema
```
Feature generator should add `import numpy as np` and import the same schema classes plus the `get_post_race_columns` helper from audit.py.

**Top-level orchestrator pattern** (`kaggle_converter.py` lines 47-131):
```python
def convert(
    raw_dir: Path = Path("data/raw/kaggle"),
    standard_dir: Path = Path("data/standard"),
) -> dict[str, Path]:
    """Main entry point: CSV -> filter -> split -> transform -> write -> audit."""
    # Step 1: Read inputs
    # Step 2: Filter / transform
    # Step 3-N: Discrete transformation functions
    # Step N+1: Write Parquet
    # Step N+2: Run audit_leakage()
    # Return output paths
```
Feature generator `generate()` should follow: `load() -> merge() -> race_context_features() -> horse_basic_features() -> margin_numeric() -> finish_time_zscore() -> lag_features() -> jockey_trainer_stats() -> debut_flag() -> target_top3() -> categorical_conversion() -> audit() -> write_parquet()`.

**Parquet I/O pattern** (`kaggle_converter.py` lines 104-119):
```python
standard_dir.mkdir(parents=True, exist_ok=True)

output_paths: dict[str, Path] = {}
tables = {
    "race": race_df,
    "entry": entry_df,
    # ...
}

for table_name, table_df in tables.items():
    output_path = standard_dir / f"{table_name}.parquet"
    table_df.to_parquet(output_path, engine="pyarrow", compression="snappy", index=False)
    output_paths[table_name] = output_path
    logger.info(f"Wrote {table_name}: {len(table_df)} rows -> {output_path}")
```
Feature generator writes two files: `features_train.parquet` (with target_top3 + result_status + is_dnf + exclude_from_training) and `features_pred.parquet` (all features except target columns).

**Leakage audit integration** (`kaggle_converter.py` lines 122-131):
```python
# Step 6: Audit for data leakage
logger.info("Running data leakage audit")
race_leaked = audit_leakage([RaceSchema], race_df, "race table generation")
entry_leaked = audit_leakage([EntrySchema], entry_df, "entry table generation")

if race_leaked:
    logger.warning(f"Race table post-race columns: {race_leaked}")
if entry_leaked:
    logger.warning(f"Entry table post-race columns: {entry_leaked}")
```
Feature generator must call `audit_leakage([RaceSchema, EntrySchema, ResultSchema], feature_df, "feature generation")` on the output DataFrame to verify no post-race columns leaked into features. This is critical per CONTEXT.md requirement.

**Helper function pattern** (`kaggle_converter.py` lines 165-204):
Each transformation is a standalone function taking a DataFrame and returning a DataFrame. The `_select_and_rename()` helper shows the pattern: focused, single-responsibility, docstring with Args/Returns. Feature generator should follow this pattern for each feature group (e.g., `generate_target()`, `compute_lag_features()`, `compute_rolling_stats()`, `convert_to_categorical()`, `normalize_finish_time()`, `parse_margin()`).

**Error handling pattern** (`kaggle_converter.py` throughout):
- Uses `logger.info()` for progress, `logger.warning()` for issues
- No try/except wrapping -- lets errors propagate to caller
- Returns structured data (dict of paths, tuple of DataFrames)

---

### `tests/pipeline/test_feature_generator.py` (test, batch transform)

**Analog:** `tests/pipeline/test_kaggle_converter.py`

**Test structure pattern** (`test_kaggle_converter.py` lines 1-13):
```python
"""Unit tests for the feature generator pipeline.

Tests cover:
- Race context features extraction
- Horse basic features presence
- Lag feature temporal safety (shift correctness)
- Jockey/trainer rolling statistics
- Target variable generation (top3, edge cases)
- Margin numeric conversion (simple + compound)
- Finish time z-score normalization
- Categorical dtype conversion
- Debut flag for first-time starters
- Leakage audit integration
- End-to-end feature generation
"""
```

**Import pattern** (`test_kaggle_converter.py` lines 15-19):
```python
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
```

**Class-based test organization** (`test_kaggle_converter.py` lines 22-23):
```python
class TestDateFilter:
    """Test that convert() filters to races on or after 2015-01-01."""

    def test_excludes_2014_race(self, sample_race_result_df, sample_odds_df, tmp_standard_dir):
```
Feature generator tests should organize into classes: `TestRaceContextFeatures`, `TestHorseBasicFeatures`, `TestLagFeatures`, `TestJockeyTrainerStats`, `TestTargetVariable`, `TestMarginConversion`, `TestFinishTimeZscore`, `TestCategoricalConversion`, `TestDebutFlag`, `TestLeakageAudit`, `TestEndToEnd`.

**Fixture usage pattern** (`test_kaggle_converter.py` throughout):
Tests use conftest fixtures for sample data and tmp directories. The pattern is: build sample DataFrames in conftest, import the function under test, call it, assert on the result.

**Key temporal safety test pattern** (new, no direct analog):
The lag feature tests need a specific pattern to verify temporal safety:
```python
def test_lag_uses_only_past_races(self, sample_feature_df):
    """Verify prev_1_finish_position for race N equals finish_position for race N-1."""
    # Sort by horse then date, shift and compare
    for horse in df['horse_name'].unique():
        horse_df = df[df['horse_name'] == horse].sort_values('race_date')
        for i in range(1, len(horse_df)):
            assert horse_df.iloc[i]['prev_1_finish_position'] == horse_df.iloc[i-1]['finish_position']
```

---

### `tests/pipeline/conftest.py` (test fixture, modify)

**Analog:** `tests/pipeline/conftest.py` (self - modification)

Add feature-specific fixtures to the existing conftest. The existing fixtures (`sample_race_result_df`, `sample_odds_df`, `tmp_standard_dir`) remain unchanged.

**Existing fixture pattern** (`conftest.py` lines 18-28):
```python
@pytest.fixture
def sample_race_result_df() -> pd.DataFrame:
    """DataFrame mimicking race_result.csv with 10 rows and all 66 columns."""
    data: dict[str, list] = {}
    # ... build dict of lists ...
    df = pd.DataFrame(data)
    return df
```

New fixtures to add:
- `sample_standard_race_df`: Small race table DataFrame (English columns from RaceSchema)
- `sample_standard_entry_df`: Small entry table DataFrame (English columns from EntrySchema)
- `sample_standard_result_df`: Small result table DataFrame (English columns from ResultSchema)
- `sample_feature_merged_df`: Pre-merged race+entry+result DataFrame ready for feature generation
- `tmp_feature_dir`: Temporary `data/feature/` output directory

These should use English schema column names (not Japanese) since they represent the standard-layer output that feature_generator reads.

---

## Shared Patterns

### Parquet I/O (Read/Write)
**Source:** `src/pipeline/kaggle_converter.py` lines 104-119
**Apply to:** `src/pipeline/feature_generator.py` (both reading standard-layer and writing feature-layer)
```python
# Reading standard layer
race_df = pd.read_parquet(standard_dir / "race.parquet", engine="pyarrow")
entry_df = pd.read_parquet(standard_dir / "entry.parquet", engine="pyarrow")
result_df = pd.read_parquet(standard_dir / "result.parquet", engine="pyarrow")

# Writing feature layer
feature_dir.mkdir(parents=True, exist_ok=True)
df.to_parquet(feature_dir / "features_train.parquet", engine="pyarrow", compression="snappy", index=False)
```

### Leakage Audit
**Source:** `src/schemas/audit.py` lines 45-84
**Apply to:** `src/pipeline/feature_generator.py` -- must be called after feature generation, before writing Parquet
```python
from src.schemas.audit import audit_leakage
from src.schemas.race import RaceSchema
from src.schemas.entry import EntrySchema
from src.schemas.result import ResultSchema

# After generating features, before writing:
leaked = audit_leakage([RaceSchema, EntrySchema, ResultSchema], feature_df, "feature generation")
if leaked:
    raise ValueError(f"Post-race columns leaked into features: {leaked}")
```
Note: The converter only logs warnings (D-12: audit does NOT raise). The feature generator should follow the same pattern -- log warning but do not raise. The test should verify the audit was called.

### Logging
**Source:** `src/pipeline/kaggle_converter.py` throughout
**Apply to:** All pipeline modules
```python
from loguru import logger

logger.info(f"Reading race_result.csv from {race_result_path}")
logger.info(f"After filtering: {len(df)} rows")
logger.warning(f"Race table post-race columns: {race_leaked}")
```

### DataFrame Transformation Functions
**Source:** `src/pipeline/kaggle_converter.py` lines 165-204, 280-300, 303-343
**Apply to:** All feature transformation functions in `feature_generator.py`
Pattern: standalone function, takes DataFrame, returns DataFrame, single responsibility:
```python
def process_finish_position(df: pd.DataFrame) -> pd.DataFrame:
    """Handle finish position notes and rename to English.

    Args:
        df: DataFrame with Japanese column names.

    Returns:
        DataFrame with processed columns.
    """
    df = df.copy()
    # ... transformation logic ...
    return df
```

### Test Organization
**Source:** `tests/pipeline/test_kaggle_converter.py`
**Apply to:** `tests/pipeline/test_feature_generator.py`
- Class-based grouping by feature area
- Each test method uses fixtures from conftest.py
- Assertions use pandas operations (`.iloc[]`, `.unique()`, `set()`)
- End-to-end test writes to tmp directory and reads back

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| (none) | -- | -- | All files have strong analogs in the existing codebase |

All three files have close analogs. The feature generator's lag computation (`groupby().shift()`), expanding window statistics, and z-score normalization are new logic but follow the same structural patterns as `kaggle_converter.py`'s transformation functions. Concrete implementations for these algorithms come from RESEARCH.md Patterns 1-3 rather than existing codebase.

## Metadata

**Analog search scope:** `src/pipeline/`, `src/schemas/`, `tests/pipeline/`
**Files scanned:** 7
**Pattern extraction date:** 2026-06-12
