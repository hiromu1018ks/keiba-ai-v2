# Phase 2: Kaggle Data Pipeline - Pattern Map

**Mapped:** 2026-06-11
**Files analyzed:** 11 (9 new, 2 modified)
**Analogs found:** 9 / 11

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/pipeline/__init__.py` | config | N/A | `src/schemas/__init__.py` | exact |
| `src/pipeline/column_mapping.py` | model | transform | `tests/schemas/test_classification.py` (KAGGLE_COLUMN_MAP dict) | exact |
| `src/pipeline/kaggle_converter.py` | service | batch | `src/schemas/export.py` | role-match |
| `src/pipeline/validators.py` | utility | batch | `src/schemas/audit.py` | role-match |
| `tests/pipeline/__init__.py` | config | N/A | `tests/schemas/__init__.py` | exact |
| `tests/pipeline/conftest.py` | test | N/A | `tests/schemas/conftest.py` | exact |
| `tests/pipeline/test_column_mapping.py` | test | N/A | `tests/schemas/test_classification.py` | exact |
| `tests/pipeline/test_kaggle_converter.py` | test | N/A | `tests/schemas/test_race.py` | role-match |
| `tests/pipeline/test_validators.py` | test | N/A | `tests/schemas/test_audit.py` | role-match |
| `pyproject.toml` | config | N/A | `pyproject.toml` (modify existing) | self |
| `data/standard/*.parquet` | output | file-I/O | N/A (data files, no code analog) | N/A |

## Pattern Assignments

### `src/pipeline/__init__.py` (config, N/A)

**Analog:** `src/schemas/__init__.py`

**Imports pattern** (lines 1-24 of analog):
```python
"""Standard-layer schema definitions for the 3-layer data pipeline.

Re-exports all table schema models, audit functions, and export function
so downstream phases can access them via ``from src.schemas import ...``.
"""

from src.schemas.audit import audit_leakage, get_post_race_columns
from src.schemas.entry import EntrySchema
from src.schemas.export import export_schema_documentation
from src.schemas.odds_trifecta import OddsTrifectaSchema
from src.schemas.payoff import PayoffSchema
from src.schemas.race import RaceSchema
from src.schemas.result import ResultSchema

__all__ = [
    "RaceSchema",
    "EntrySchema",
    "ResultSchema",
    "OddsTrifectaSchema",
    "PayoffSchema",
    "get_post_race_columns",
    "audit_leakage",
    "export_schema_documentation",
]
```

**Pattern to follow:** Docstring describing the package, re-export key symbols, define `__all__`. The pipeline `__init__.py` should re-export the converter entry point, column mapping dicts, and validator functions.

---

### `src/pipeline/column_mapping.py` (model, transform)

**Analog:** `tests/schemas/test_classification.py` (lines 28-142: KAGGLE_COLUMN_MAP dict)

This is the primary reference for the column mapping. The test file already contains the authoritative `KAGGLE_COLUMN_MAP` dict mapping all 66 Japanese column names to `(table_name, english_field_name)` tuples. The new `column_mapping.py` should extract this into production code.

**Core pattern** (lines 28-142 of analog):
```python
KAGGLE_COLUMN_MAP: dict[str, tuple[str, str]] = {
    # Row 1: Identification
    "レース馬番ID": ("entry", "horse_race_id"),
    # Row 2: Race identification
    "レースID": ("race", "race_id"),
    # Row 3: Race date
    "レース日付": ("race", "race_date"),
    # ... (all 66 entries)
    # Row 66: Prize money (result)
    "賞金(万円)": ("result", "prize_money"),
}

# Table name -> schema class mapping for dynamic lookup
TABLE_TO_SCHEMA: dict[str, type] = {
    "race": RaceSchema,
    "entry": EntrySchema,
    "result": ResultSchema,
    "odds_trifecta": OddsTrifectaSchema,
    "payoff": PayoffSchema,
}
```

**Additional content needed (not in existing code):**
- `ODDS_COLUMN_MAP` dict mapping odds.csv Japanese column names to `OddsTrifectaSchema` and `PayoffSchema` fields
- `FLAG_COLUMNS` list of the 20 `レース記号/*` column names for dtype specification
- `DTYPE_SPEC` dict for `pd.read_csv()` dtype parameter (flag columns as `str`, plus other mixed-type columns)
- `FINISH_NOTE_MAP` dict mapping Japanese finish note characters to their meanings
- Reverse mapping functions: `get_columns_for_table(table_name) -> dict[str, str]`

**Imports pattern:**
```python
from src.schemas.entry import EntrySchema
from src.schemas.odds_trifecta import OddsTrifectaSchema
from src.schemas.payoff import PayoffSchema
from src.schemas.race import RaceSchema
from src.schemas.result import ResultSchema
```

---

### `src/pipeline/kaggle_converter.py` (service, batch)

**Analog:** `src/schemas/export.py` (function-based module, path I/O, logging)

**Imports pattern** (lines 1-19 of analog):
```python
"""Schema export function for machine-readable documentation.

Provides export_schema_documentation() which builds a dict of all 5 table
schemas using Pydantic's model_json_schema() and optionally writes the
result as a JSON file.
"""

import json
from pathlib import Path
from typing import Optional

from src.schemas.entry import EntrySchema
from src.schemas.race import RaceSchema
from src.schemas.result import ResultSchema
```

**Core pattern -- function with path I/O** (lines 22-53 of analog):
```python
def export_schema_documentation(
    output_path: Optional[Path] = None,
) -> dict:
    """Export all table schemas as machine-readable JSON.

    If output_path is provided, writes the dict as formatted JSON to that path.

    Args:
        output_path: Optional file path to write JSON output.
            If provided, creates parent directories as needed.

    Returns:
        Dict mapping table names to their JSON schema dicts.
    """
    schemas: dict = {
        "race": RaceSchema.model_json_schema(),
        "entry": EntrySchema.model_json_schema(),
        # ...
    }

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(schemas, f, indent=2, ensure_ascii=False)

    return schemas
```

**Pattern to follow for kaggle_converter.py:**
- Module-level docstring explaining purpose
- Function-based API (not class-based)
- `pathlib.Path` for file paths
- `output_path.parent.mkdir(parents=True, exist_ok=True)` for directory creation
- `loguru.logger` for logging (see `src/schemas/audit.py` lines 17, 77-82)
- `pandas` for DataFrame operations
- Import schemas from `src.schemas` for column mapping reference
- Call `audit_leakage()` from `src.schemas.audit` after generating each table

**Error handling pattern** (from `src/schemas/audit.py` lines 76-83):
```python
if leaked:
    logger.warning(
        f"Data leakage detected during {context}: "
        f"post-race columns found: {leaked}"
    )
else:
    logger.info(f"No data leakage detected during {context}")
```

**Expected function signatures:**
```python
def convert(
    raw_dir: Path = Path("data/raw/kaggle"),
    standard_dir: Path = Path("data/standard"),
) -> dict[str, Path]:
    """Main entry point: read CSV -> filter -> split -> write Parquet.

    Returns dict mapping table names to output Parquet file paths.
    """
```

---

### `src/pipeline/validators.py` (utility, batch)

**Analog:** `src/schemas/audit.py`

**Imports pattern** (lines 15-21 of analog):
```python
from typing import TYPE_CHECKING

from loguru import logger
from pydantic import BaseModel

if TYPE_CHECKING:
    import pandas as pd
```

**Core pattern** (lines 24-42, 45-84 of analog):
```python
def get_post_race_columns(model_class: type[BaseModel]) -> set[str]:
    """Extract post-race column names from a Pydantic model class.

    Args:
        model_class: A Pydantic BaseModel subclass with json_schema_extra
            metadata containing {"pre_race": bool, "table": str}.

    Returns:
        Set of field names where pre_race=False (post-race columns).
    """
    post_race: set[str] = set()
    for name, info in model_class.model_fields.items():
        extra = info.json_schema_extra
        if isinstance(extra, dict) and not extra.get("pre_race", True):
            post_race.add(name)
    return post_race
```

**Pattern to follow for validators.py:**
- `TYPE_CHECKING` guard for pandas import (keeps module importable without pandas at type-check time)
- `loguru.logger` for all logging
- Functions accept `pd.DataFrame` parameters with docstrings describing args/returns
- Logger.warning for issues found, logger.info for clean results
- Return structured results (e.g., dict or list) rather than raising exceptions for validation failures
- Each validator function focuses on one check type (D-05 lists 8 checks)

**Expected function signatures:**
```python
def validate_row_counts(
    source_counts: dict[str, int],
    parquet_dir: Path,
) -> dict[str, bool]:
    """Check 1: CSV row counts vs Parquet row counts."""

def validate_schema_conformance(
    parquet_dir: Path,
) -> dict[str, list[str]]:
    """Check 2: Pydantic schema dtype/nullability conformance."""

def validate_audit(
    parquet_dir: Path,
) -> dict[str, list[str]]:
    """Check 3: Phase 1 audit_leakage() execution."""

def validate_null_rates(
    source_stats: dict,
    parquet_dir: Path,
) -> dict[str, dict[str, float]]:
    """Check 4: Null rate comparison CSV vs Parquet."""

def validate_distributions(
    source_stats: dict,
    parquet_dir: Path,
) -> dict[str, dict]:
    """Check 5: Min/max/mean comparison on numeric columns."""

def validate_referential_integrity(
    parquet_dir: Path,
) -> list[str]:
    """Check 6: race_id consistency across all 5 tables."""

def validate_sample_rows(
    source_dir: Path,
    parquet_dir: Path,
) -> dict[str, bool]:
    """Check 7: Sample row spot-check against original CSV."""

def validate_value_ranges(
    parquet_dir: Path,
) -> dict[str, list[str]]:
    """Check 8: Value range checks (course_code, distance, etc.)."""
```

---

### `tests/pipeline/__init__.py` (config, N/A)

**Analog:** `tests/schemas/__init__.py`

**Pattern:** Empty file (content is just a single blank line). Used as a Python package marker.

---

### `tests/pipeline/conftest.py` (test, N/A)

**Analog:** `tests/schemas/conftest.py`

**Imports pattern** (lines 1-8 of analog):
```python
"""Shared pytest fixtures for audit tests."""

import pandas as pd
import pytest

from src.schemas.entry import EntrySchema
from src.schemas.race import RaceSchema
from src.schemas.result import ResultSchema
```

**Fixture pattern** (lines 11-20 of analog):
```python
@pytest.fixture
def sample_pre_race_df() -> pd.DataFrame:
    """DataFrame with only pre-race column names."""
    return pd.DataFrame(
        {
            "race_id": ["202101010101"],
            "horse_number": [1],
            "distance": [2000],
        }
    )
```

**Pattern to follow for pipeline conftest.py:**
- Module docstring describing purpose
- `import pandas as pd` and `import pytest` at top
- Import schema classes from `src.schemas`
- Import mapping dicts from `src.pipeline.column_mapping`
- Fixtures return small DataFrames representing realistic data shapes
- `tmp_path` (pytest builtin) for temp directory fixtures
- Fixtures for:
  - Small sample race_result DataFrame (5-10 rows, 2015 data, flat races)
  - Small sample odds DataFrame (5-10 rows)
  - Expected column mapping dicts
  - Temp output directory for Parquet writes

---

### `tests/pipeline/test_column_mapping.py` (test, N/A)

**Analog:** `tests/schemas/test_classification.py`

**Imports pattern** (lines 1-19 of analog):
```python
"""Cross-table classification verification tests.

Validates:
- All 66 Kaggle columns from race_result.csv are mapped 1-to-1 to schema fields
- No orphan schema fields exist (except PayoffSchema which is a contract table)
- Post-race column classification matches D-03/D-04/D-05 decisions
"""

from src.schemas.audit import get_post_race_columns
from src.schemas.entry import EntrySchema
from src.schemas.odds_trifecta import OddsTrifectaSchema
from src.schemas.payoff import PayoffSchema
from src.schemas.race import RaceSchema
from src.schemas.result import ResultSchema
```

**Core test pattern -- class-based with descriptive method names** (lines 154-179 of analog):
```python
class TestKaggleColumnMapping:
    """Verify 1-to-1 mapping of all 66 Kaggle columns to schema fields."""

    def test_kaggle_column_1to1_mapping(self) -> None:
        """Every Kaggle column maps to exactly one field in exactly one table."""
        assert len(KAGGLE_COLUMN_MAP) == 66, (
            f"Expected 66 Kaggle columns, got {len(KAGGLE_COLUMN_MAP)}"
        )

        errors: list[str] = []
        for jp_name, (table_name, eng_name) in KAGGLE_COLUMN_MAP.items():
            schema_class = TABLE_TO_SCHEMA[table_name]
            if eng_name not in schema_class.model_fields:
                errors.append(
                    f"{jp_name} -> ({table_name}, {eng_name}): "
                    f"'{eng_name}' not in {schema_class.__name__}.model_fields"
                )

        assert errors == [], (
            f"{len(errors)} unmapped Kaggle columns:\n" + "\n".join(errors)
        )
```

**Pattern to follow:**
- Class-based test organization: `TestColumnMappingRaceResult`, `TestColumnMappingOdds`, `TestDtypeSpec`
- Descriptive docstring per test method (explains what and why)
- Collect errors into a list, then assert with formatted message
- Import the production mapping from `src.pipeline.column_mapping`
- Verify mapping completeness (66 race_result columns + odds.csv columns)
- Verify each mapped field exists in the corresponding schema class
- Test reverse mapping functions

---

### `tests/pipeline/test_kaggle_converter.py` (test, N/A)

**Analog:** `tests/schemas/test_race.py` and `tests/schemas/test_schema_export.py`

**Test class pattern** (from `tests/schemas/test_race.py` lines 8-67):
```python
"""Tests for RaceSchema - standard-layer race table schema definition."""

import json

from src.schemas.race import RaceSchema


class TestRaceSchemaFields:
    """Verify RaceSchema has all expected fields."""

    EXPECTED_FIELDS = {
        "race_id",
        "race_date",
        # ...
    }

    def test_race_schema_has_all_fields(self):
        """RaceSchema.model_fields contains all expected field names."""
        actual_fields = set(RaceSchema.model_fields.keys())
        missing = self.EXPECTED_FIELDS - actual_fields
        extra = actual_fields - self.EXPECTED_FIELDS
        assert not missing, f"Missing fields: {missing}"
        assert not extra, f"Unexpected extra fields: {extra}"
```

**tmp_path pattern** (from `tests/schemas/test_schema_export.py` lines 27-44):
```python
def test_export_writes_json_file(self, tmp_path: Path) -> None:
    """export_schema_documentation(tmp_path) writes valid JSON file."""
    output_file = tmp_path / "schema.json"
    result = export_schema_documentation(output_file)

    # File exists
    assert output_file.exists(), "schema.json was not created"

    # File contains valid JSON
    with open(output_file) as f:
        loaded = json.load(f)
```

**Pattern to follow for converter tests:**
- Use `tmp_path` pytest fixture for Parquet output directories
- Use conftest fixtures for sample DataFrames
- Test the 3-way split (race_result -> race/entry/result)
- Test 2-way split (odds -> odds_trifecta/payoff)
- Test date filter (2015+ only)
- Test obstacle exclusion
- Test flag boolean conversion
- Test finish position note handling
- Test Parquet output schema conformance
- Integration test with actual CSV data (marked with `@pytest.mark.integration` or conditional on file existence)

---

### `tests/pipeline/test_validators.py` (test, N/A)

**Analog:** `tests/schemas/test_audit.py`

**Test class pattern** (lines 16-46 of analog):
```python
class TestGetPostRaceColumns:
    """Tests for get_post_race_columns function."""

    def test_entry_schema_returns_popularity_and_win_odds(self) -> None:
        """Test 1: get_post_race_columns(EntrySchema) returns popularity and win_odds."""
        result = get_post_race_columns(EntrySchema)
        assert result == {"popularity", "win_odds"}
```

**Logger capture pattern** (lines 66-83 of analog):
```python
def test_logs_warning_on_leakage(
    self, sample_entry_post_race_df: pd.DataFrame
) -> None:
    """Test 7: audit_leakage logs warning when post-race columns detected."""
    import io
    import sys

    # Capture loguru output
    output = io.StringIO()
    logger.remove()  # Remove default handler
    logger.add(output, format="{message}")

    try:
        audit_leakage([EntrySchema], sample_entry_post_race_df, "test")
        log_output = output.getvalue()
        assert "leakage" in log_output.lower()
    finally:
        logger.remove()
        logger.add(sys.stderr)  # Restore default handler
```

**Pattern to follow for validator tests:**
- One test class per validator function (8 classes for 8 checks)
- Each test has a descriptive docstring explaining the check
- Use conftest fixtures for sample DataFrames
- Use `tmp_path` for test Parquet files
- For logger capture: `io.StringIO()` + `logger.add()` + `try/finally` to restore
- Test both pass and fail cases for each validator

---

### `pyproject.toml` (config, modify existing)

**Analog:** `pyproject.toml` (self-modification)

**Current dependencies** (lines 6-12):
```toml
dependencies = [
    "pydantic>=2.13,<3",
    "pandas>=2.3,<3",
    "numpy>=2,<3",
    "lightgbm>=4.6",
    "loguru>=0.7",
]
```

**Required change:** Add `pyarrow>=14.0` to dependencies. This is the blocking dependency identified in RESEARCH.md.

**Pattern to follow:** Add `"pyarrow>=14.0"` to the existing `dependencies` list, maintaining alphabetical or logical ordering.

---

### `data/standard/*.parquet` (output, file-I/O)

No code analog -- these are data output files. The write pattern comes from RESEARCH.md:

```python
df.to_parquet(
    "data/standard/race.parquet",
    engine="pyarrow",
    compression="snappy",
    index=False,
)
```

---

## Shared Patterns

### Logging
**Source:** `src/schemas/audit.py` (lines 17, 76-82)
**Apply to:** `src/pipeline/kaggle_converter.py`, `src/pipeline/validators.py`
```python
from loguru import logger

# In functions:
logger.info(f"No data leakage detected during {context}")
logger.warning(f"Data leakage detected during {context}: post-race columns found: {leaked}")
```

### Module Docstring Convention
**Source:** All `src/schemas/*.py` files
**Apply to:** All new `src/pipeline/*.py` files
```python
"""One-line summary of the module's purpose.

Detailed description of what the module provides, referencing design decisions
(e.g., "Per D-02: Pydantic is for TYPE DEFINITION ONLY") and the data source
it works with.

Key design decisions:
- Bullet point 1
- Bullet point 2
"""
```

### Import Path Convention
**Source:** All `src/schemas/*.py` and `tests/schemas/*.py` files
**Apply to:** All new files
```python
# Production code uses absolute imports from src.*
from src.schemas.race import RaceSchema
from src.schemas.audit import audit_leakage

# Test code imports both production code and test fixtures
import pandas as pd
import pytest
from src.pipeline.kaggle_converter import convert
from src.pipeline.column_mapping import KAGGLE_COLUMN_MAP
```

### Path Handling
**Source:** `src/schemas/export.py` (lines 48-49)
**Apply to:** `src/pipeline/kaggle_converter.py`, `src/pipeline/validators.py`
```python
from pathlib import Path

# Always use pathlib.Path, create directories as needed
output_path = Path(output_path)
output_path.parent.mkdir(parents=True, exist_ok=True)
```

### DataFrame-Level Validation (NOT Row-Level Pydantic)
**Source:** `src/schemas/race.py` docstring (line 7), `tests/schemas/conftest.py`
**Apply to:** `src/pipeline/kaggle_converter.py`, `src/pipeline/validators.py`

**Established pattern:** Per D-02, Pydantic is for type definition only. The 472MB CSV is validated at the DataFrame level using dtype checks, null rate assertions, and schema conformance checks. Never iterate over 311K rows calling `RaceSchema(**row)`.

### Pydantic Schema Field Metadata
**Source:** `src/schemas/race.py` (all fields), `src/schemas/audit.py` (consumes this metadata)
**Apply to:** Column mapping validation in `src/pipeline/validators.py`

Every schema field has `json_schema_extra={"pre_race": bool, "table": str}`. The `audit_leakage()` function reads this metadata. Validators should use `model_fields` to extract expected column names, types, and nullability for conformance checks.

```python
# Extracting field metadata from schema
for name, info in RaceSchema.model_fields.items():
    extra = info.json_schema_extra
    is_pre_race = extra.get("pre_race", True)
    table_name = extra.get("table")
```

### pytest Fixture Pattern
**Source:** `tests/schemas/conftest.py`
**Apply to:** `tests/pipeline/conftest.py`
```python
import pandas as pd
import pytest

from src.schemas.race import RaceSchema  # Import what fixtures reference

@pytest.fixture
def sample_pre_race_df() -> pd.DataFrame:
    """DataFrame with only pre-race column names."""
    return pd.DataFrame({
        "race_id": ["202101010101"],
        "distance": [2000],
    })
```

### KAGGLE_COLUMN_MAP (Authoritative Mapping)
**Source:** `tests/schemas/test_classification.py` (lines 28-142)
**Apply to:** `src/pipeline/column_mapping.py`

The test file already contains the complete 66-entry mapping dict. The production `column_mapping.py` should move this dict from the test file into `src/pipeline/`, keeping the exact same structure. The test file should then import from the production module instead of defining its own copy.

## No Analog Found

Files with no close match in the codebase (planner should use RESEARCH.md patterns instead):

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `src/pipeline/kaggle_converter.py` | service | batch | No batch CSV-to-Parquet pipeline exists yet. RESEARCH.md provides code examples for CSV reading with dtype spec (lines 381-411), race table extraction (lines 414-428), and Parquet writing (lines 449-457). |
| `src/pipeline/validators.py` | utility | batch | No data quality validation functions exist. RESEARCH.md Section "Validation Architecture" (lines 513-554) defines the 8 required checks and test map. |

**Note:** While these files have no exact analog, the `src/schemas/export.py` and `src/schemas/audit.py` files establish the coding conventions (function-based API, loguru logging, pathlib for paths, TYPE_CHECKING guards) that should be followed.

## Metadata

**Analog search scope:** `src/`, `tests/`, project root
**Files scanned:** 22 (9 source, 12 test, 1 config)
**Pattern extraction date:** 2026-06-11
