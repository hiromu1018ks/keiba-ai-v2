# Phase 1: Data Schema & Leak Audit - Pattern Map

**Mapped:** 2026-06-11
**Files analyzed:** 17 (new creation only)
**Analogs found:** 0 / 17

## Greenfield Note

This is the first implementation phase of a greenfield project. There is **zero existing Python code** in the repository -- no `src/`, no `tests/`, no `pyproject.toml`, no `requirements.txt`. All patterns must be established from scratch.

The pattern source for this phase is the **RESEARCH.md code examples**, which contain verified Pydantic v2 patterns tested on the local Python 3.12.13 + pydantic 2.13.4 environment. These code excerpts should be treated as the canonical starting point for implementation.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `pyproject.toml` | config | N/A | None (greenfield) | no-analog |
| `src/__init__.py` | config | N/A | None (greenfield) | no-analog |
| `src/schemas/__init__.py` | config | N/A | None (greenfield) | no-analog |
| `src/schemas/race.py` | model | transform | None (greenfield) | no-analog |
| `src/schemas/entry.py` | model | transform | None (greenfield) | no-analog |
| `src/schemas/result.py` | model | transform | None (greenfield) | no-analog |
| `src/schemas/odds_trifecta.py` | model | transform | None (greenfield) | no-analog |
| `src/schemas/payoff.py` | model | transform | None (greenfield) | no-analog |
| `src/schemas/audit.py` | utility | request-response | None (greenfield) | no-analog |
| `tests/__init__.py` | config | N/A | None (greenfield) | no-analog |
| `tests/schemas/__init__.py` | config | N/A | None (greenfield) | no-analog |
| `tests/schemas/conftest.py` | test | N/A | None (greenfield) | no-analog |
| `tests/schemas/test_race.py` | test | N/A | None (greenfield) | no-analog |
| `tests/schemas/test_entry.py` | test | N/A | None (greenfield) | no-analog |
| `tests/schemas/test_result.py` | test | N/A | None (greenfield) | no-analog |
| `tests/schemas/test_odds_trifecta.py` | test | N/A | None (greenfield) | no-analog |
| `tests/schemas/test_payoff.py` | test | N/A | None (greenfield) | no-analog |
| `tests/schemas/test_audit.py` | test | N/A | None (greenfield) | no-analog |
| `tests/schemas/test_schema_export.py` | test | N/A | None (greenfield) | no-analog |
| `tests/schemas/test_classification.py` | test | N/A | None (greenfield) | no-analog |

## Pattern Assignments

Since no codebase analogs exist, each pattern assignment references the **RESEARCH.md verified code examples** as the pattern source. These were verified to work on Python 3.12.13 + Pydantic 2.13.4.

---

### `pyproject.toml` (config, N/A)

**Analog:** None (greenfield)
**Pattern source:** CLAUDE.md Technology Stack recommendations

**Required configuration:**
```toml
[project]
name = "keiba-ai-v2"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.13,<3",
    "pandas>=2.3,<3",
    "numpy>=2,<3",
    "lightgbm>=4.6",
    "loguru>=0.7",
]

[project.optional-dependencies]
dev = [
    "pytest>=9.0",
    "ruff>=0.15",
    "mypy>=1.14",
]

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.pytest.ini_options]
testpaths = ["tests"]
```

**Notes for planner:**
- Poetry is not installed per RESEARCH.md. Use standard `[project]` table in pyproject.toml (PEP 621) with `pip install -e ".[dev]"`.
- Only pydantic and pytest are needed for Phase 1. Other dependencies listed for future phases.

---

### `src/__init__.py` (config, N/A)

**Analog:** None (greenfield)
**Pattern:** Empty file for package initialization.

---

### `src/schemas/__init__.py` (config, N/A)

**Analog:** None (greenfield)
**Pattern source:** RESEARCH.md Architecture Patterns -- "Re-exports all table models + audit function"

**Re-export pattern:**
```python
"""Standard-layer schema definitions for the 3-layer data pipeline."""

from src.schemas.race import RaceSchema
from src.schemas.entry import EntrySchema
from src.schemas.result import ResultSchema
from src.schemas.odds_trifecta import OddsTrifectaSchema
from src.schemas.payoff import PayoffSchema
from src.schemas.audit import get_post_race_columns, audit_leakage

__all__ = [
    "RaceSchema",
    "EntrySchema",
    "ResultSchema",
    "OddsTrifectaSchema",
    "PayoffSchema",
    "get_post_race_columns",
    "audit_leakage",
]
```

---

### `src/schemas/race.py` (model, transform)

**Analog:** None (greenfield)
**Pattern source:** RESEARCH.md Pattern 1 -- "Pydantic Schema with Pre-Race Metadata"

**Imports pattern:**
```python
from pydantic import BaseModel, Field
from typing import Optional
```

**Core pattern (from RESEARCH.md verified example):**
```python
class RaceSchema(BaseModel):
    """Standard-layer race table schema."""
    race_id: str = Field(
        description="Unique race identifier (12-digit: YYYYPPCCDDRR)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    race_date: str = Field(
        description="Race date (YYYY-MM-DD)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    # ... all race-level columns per RESEARCH.md Kaggle Column Analysis table
```

**Critical pattern rules for ALL schema files:**
1. Every `Field` must include `json_schema_extra={"pre_race": bool, "table": str}` (per D-10, using `json_schema_extra` instead of `metadata=` per RESEARCH.md Open Question #1 resolution)
2. All columns in this table are pre-race (`pre_race: True`) -- race table has no post-race columns
3. The 20 `レース記号/*` columns become individual `Optional[bool]` fields (per RESEARCH.md recommendation)
4. Use `Optional[T] = Field(default=None, ...)` for nullable columns

**Column inventory:** See RESEARCH.md "race_result.csv: Complete Column Inventory" rows 1-42 (the race-level subset). Planner must map these to English names.

---

### `src/schemas/entry.py` (model, transform)

**Analog:** None (greenfield)
**Pattern source:** RESEARCH.md Code Examples -- "Complete Schema Example: Entry Table"

**Imports pattern:**
```python
from pydantic import BaseModel, Field
from typing import Optional
```

**Core pattern (from RESEARCH.md verified example -- this is the most complete example):**
```python
class EntrySchema(BaseModel):
    """Standard-layer entry table schema.

    Pre-race information about each horse in a race.
    One row per horse per race. Join key: horse_race_id.
    """
    horse_race_id: str = Field(
        description="Unique key: {race_id}_{horse_number:02d}",
        json_schema_extra={"pre_race": True, "table": "entry"},
    )
    race_id: str = Field(
        description="12-digit race identifier",
        json_schema_extra={"pre_race": True, "table": "entry"},
    )
    bracket_num: int = Field(
        description="Bracket number (1-8)",
        ge=1, le=8,
        json_schema_extra={"pre_race": True, "table": "entry"},
    )
    horse_number: int = Field(
        description="Horse number (1-18+)",
        ge=1,
        json_schema_extra={"pre_race": True, "table": "entry"},
    )
    # ... pre-race columns ...
    # D-03: popularity and win_odds are post-race for feature purposes
    popularity: Optional[int] = Field(
        default=None,
        description="Betting popularity rank",
        json_schema_extra={"pre_race": False, "table": "entry"},
    )
    win_odds: Optional[float] = Field(
        default=None,
        description="Win odds",
        json_schema_extra={"pre_race": False, "table": "entry"},
    )
```

**Key design note:** This table has MIXED pre_race/post_race columns. `popularity` and `win_odds` are `pre_race: False` per D-03/D-06. All other entry columns are `pre_race: True`.

---

### `src/schemas/result.py` (model, transform)

**Analog:** None (greenfield)
**Pattern source:** Same pattern as `entry.py` but ALL columns are post-race

**Core pattern rule:** Every Field in this table has `json_schema_extra={"pre_race": False, "table": "result"}`. Result columns include finish_position, finish_note, finish_time, margin, corner_1-4, last_3f, prize_money (per RESEARCH.md Column Inventory rows 43-44, 52-58, 66).

**Critical:**
- `finish_position: Optional[int]` -- must be nullable because 1.1% of rows have empty values and `着順注記` indicates non-finishers (RESEARCH.md Pitfall #6)
- `finish_note: Optional[str]` -- values like `中`, `取`, `失`, `除`, `再`
- `last_3f: Optional[float]` -- 4.8% null rate

---

### `src/schemas/odds_trifecta.py` (model, transform)

**Analog:** None (greenfield)
**Pattern source:** Same Pydantic pattern; all columns are post-race

**Column inventory:** See RESEARCH.md "odds.csv: Trifecta-Relevant Columns" (rows 75-89). All `pre_race: False`. Includes:
- `race_id` (join key)
- `trifecta1_combo_1/2/3`, `trifecta1_odds`, `trifecta1_popularity`
- `trifecta2_*`, `trifecta3_*` (sparse, 0.1% and 0.002% coverage)

**Note:** Only 54.1% of rows have `trifecta1_odds` data. All trifecta fields must be `Optional`.

---

### `src/schemas/payoff.py` (model, transform)

**Analog:** None (greenfield)
**Pattern source:** Same Pydantic pattern

**Special note (RESEARCH.md Pitfall #4):** There is **no direct Kaggle source** for payoff data. This schema is a **contract for future phases** (Phase 5 scraping, Phase 8 EV calculation). All fields are post-race.

**Expected fields:**
- `race_id: str`
- `combination: str` or `combo_1/2/3: int` (3 horse numbers)
- `odds: Optional[float]` (in 0.1 units or as float)
- `payoff_amount: Optional[int]` (in yen)

---

### `src/schemas/audit.py` (utility, request-response)

**Analog:** None (greenfield)
**Pattern source:** RESEARCH.md Code Examples -- "Complete Audit Function"

**Imports pattern:**
```python
from pydantic import BaseModel
from loguru import logger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd
```

**Core pattern -- `get_post_race_columns()` (from RESEARCH.md verified example):**
```python
def get_post_race_columns(model_class: type[BaseModel]) -> set[str]:
    """Extract post-race column names from a Pydantic model class.

    Reads json_schema_extra["pre_race"] from each FieldInfo.
    """
    post_race = set()
    for name, info in model_class.model_fields.items():
        extra = info.json_schema_extra
        if isinstance(extra, dict) and not extra.get("pre_race", True):
            post_race.add(name)
    return post_race
```

**Core pattern -- `audit_leakage()` (from RESEARCH.md verified example):**
```python
def audit_leakage(
    model_classes: list[type[BaseModel]],
    df: "pd.DataFrame",
    context: str = "feature generation",
) -> list[str]:
    """Check DataFrame for post-race column leakage.

    Per D-12: logs warning only, does NOT raise.
    Returns list of leaked column names for caller inspection.
    """
    all_post_race: set[str] = set()
    for cls in model_classes:
        all_post_race |= get_post_race_columns(cls)

    leaked = [col for col in df.columns if col in all_post_race]
    if leaked:
        logger.warning(
            f"Data leakage detected during {context}: "
            f"post-race columns found: {leaked}"
        )
    else:
        logger.info(f"No data leakage detected during {context}")
    return leaked
```

**Critical constraints:**
- Uses `loguru` for logging (CLAUDE.md fixed choice)
- `TYPE_CHECKING` guard for pandas import (audit function accepts DataFrame but doesn't import pandas at module level -- avoids hard dependency for pure schema modules)
- **Exact column name matching only** -- no substring checks (RESEARCH.md Pitfall #3: prevents false positives on lag feature columns like `prev_1_last_3f`)
- Returns `list[str]` (leaked column names) for caller inspection, never raises (D-12)

---

### `tests/schemas/conftest.py` (test, N/A)

**Analog:** None (greenfield)
**Pattern source:** RESEARCH.md Validation Architecture -- Wave 0 Gaps

**Pattern:** pytest shared fixtures for schema tests.

**Expected fixtures:**
- Sample DataFrames with known pre-race and post-race columns for audit tests
- Model class lists (all 5 schema classes)
- Sample valid field dicts for each schema

---

### `tests/schemas/test_race.py` (test, N/A)

**Pattern source:** pytest conventions

**Tests to implement (per RESEARCH.md Test Map):**
- `test_race_schema_has_all_fields` -- verify all expected columns present
- `test_race_schema_field_types` -- verify correct Python types
- `test_race_schema_all_pre_race` -- verify ALL fields are pre_race=True
- `test_race_schema_optional_fields_accept_none` -- verify nullable fields
- `test_race_schema_model_json_schema_valid` -- verify JSON schema export

---

### `tests/schemas/test_entry.py` (test, N/A)

**Tests to implement:**
- Same structural tests as test_race.py
- **Additional:** `test_entry_has_post_race_columns` -- verify `popularity` and `win_odds` are `pre_race=False`
- `test_entry_mixed_classification` -- verify some fields pre_race=True, some False

---

### `tests/schemas/test_result.py` (test, N/A)

**Tests to implement:**
- Same structural tests
- `test_result_all_post_race` -- verify ALL fields are pre_race=False
- `test_finish_position_nullable` -- verify Optional[int] accepts None

---

### `tests/schemas/test_odds_trifecta.py` (test, N/A)

**Tests to implement:**
- Same structural tests
- `test_odds_all_post_race` -- verify all fields are pre_race=False
- `test_sparse_optional_fields` -- verify trifecta2/3 fields accept None

---

### `tests/schemas/test_payoff.py` (test, N/A)

**Tests to implement:**
- Same structural tests
- `test_payoff_all_post_race` -- verify all fields are pre_race=False

---

### `tests/schemas/test_audit.py` (test, N/A)

**Pattern source:** RESEARCH.md Validation Architecture -- Test Map

**Tests to implement (per RESEARCH.md):**
- `test_detects_post_race` -- audit_leakage detects post-race columns in a DataFrame
- `test_no_leakage` -- audit_leakage returns empty list for pre-race-only DataFrame
- `test_warning_no_exception` -- audit_leakage logs warning, does not raise, on detection
- `test_get_post_race_columns_entry` -- verify mixed pre/post model returns correct set
- `test_get_post_race_columns_all_pre` -- verify all-pre-race model returns empty set
- `test_exact_column_matching` -- verify "last_3f" does not match "prev_1_last_3f"

---

### `tests/schemas/test_schema_export.py` (test, N/A)

**Tests to implement:**
- `test_model_json_schema_valid_json` -- verify all 5 models produce valid JSON schema
- `test_json_schema_contains_pre_race_metadata` -- verify `pre_race` key appears in schema properties
- `test_combined_export` -- verify RESEARCH.md Pattern 3 export produces complete dict

---

### `tests/schemas/test_classification.py` (test, N/A)

**Tests to implement:**
- `test_all_kaggle_columns_classified` -- verify every Kaggle column has a pre_race classification
- `test_classification_consistency` -- verify no column is both pre_race True and False across tables
- `test_post_race_columns_match_decisions` -- verify D-03/D-04/D-06 classifications

---

## Shared Patterns

### Pattern A: Pydantic BaseModel with Field metadata
**Source:** RESEARCH.md Pattern 1 (verified on local environment)
**Apply to:** `src/schemas/race.py`, `src/schemas/entry.py`, `src/schemas/result.py`, `src/schemas/odds_trifecta.py`, `src/schemas/payoff.py`

**Canonical import block for every schema file:**
```python
from pydantic import BaseModel, Field
from typing import Optional
```

**Canonical Field pattern:**
```python
field_name: type = Field(
    description="Human-readable description",
    json_schema_extra={"pre_race": bool, "table": "table_name"},
)
```

**Nullable field pattern:**
```python
field_name: Optional[type] = Field(
    default=None,
    description="Human-readable description",
    json_schema_extra={"pre_race": bool, "table": "table_name"},
)
```

**Key rules:**
- Use `json_schema_extra` NOT `metadata` (per RESEARCH.md Open Question #1)
- Every field must have both `pre_race` (bool) and `table` (str) in `json_schema_extra`
- Use `Optional[T]` with `Field(default=None, ...)` for nullable columns
- Pydantic is for TYPE DEFINITION ONLY, not row-level validation (D-02)

### Pattern B: Logging with loguru
**Source:** CLAUDE.md Technology Stack
**Apply to:** `src/schemas/audit.py`

```python
from loguru import logger
```

Zero-config logging. Use `logger.warning()` for leak detection, `logger.info()` for clean passes.

### Pattern C: pytest test structure
**Source:** RESEARCH.md Validation Architecture
**Apply to:** All test files

```python
import pytest
from src.schemas.race import RaceSchema  # or relevant module
```

**Test naming:** `test_<what>_<condition>_<expected>`
**Config:** No pytest config file needed initially. `testpaths = ["tests"]` in pyproject.toml suffices.
**Run command:** `pytest tests/schemas/ -x -q`

### Pattern D: TYPE_CHECKING guard for pandas
**Source:** RESEARCH.md Code Examples
**Apply to:** `src/schemas/audit.py`

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd
```

This keeps pandas as a type-hint-only dependency in the schema module, avoiding a hard import when the module is loaded for schema introspection without DataFrames.

## No Analog Found

All 20 files have no analog in the codebase. This is expected -- the project has zero Python code. The pattern assignments above use **RESEARCH.md verified code examples** as the pattern source, which were tested and confirmed working on this machine's Python 3.12.13 + Pydantic 2.13.4 environment.

| File Group | Count | Pattern Source |
|------------|-------|----------------|
| Schema models (5 files) | 5 | RESEARCH.md Pattern 1 + Code Examples |
| Audit utility (1 file) | 1 | RESEARCH.md Pattern 2 + Code Examples |
| Test files (8 files) | 8 | RESEARCH.md Validation Architecture Test Map |
| Config/init files (5 files) | 5 | Standard Python package conventions |
| pyproject.toml (1 file) | 1 | CLAUDE.md Technology Stack |

## Implementation Order Guidance for Planner

Based on dependencies:

1. **Wave 0 (Infrastructure):** `pyproject.toml`, `src/__init__.py`, `src/schemas/__init__.py`, `tests/__init__.py`, `tests/schemas/__init__.py`
2. **Wave 1 (Core schema - race):** `src/schemas/race.py` + `tests/schemas/test_race.py` -- simplest table, all pre-race, establishes the pattern
3. **Wave 2 (Mixed schema - entry):** `src/schemas/entry.py` + `tests/schemas/test_entry.py` -- mixed pre/post, the most complete RESEARCH.md example
4. **Wave 3 (Post-race schemas):** `src/schemas/result.py` + `test_result.py`, `src/schemas/odds_trifecta.py` + `test_odds_trifecta.py`, `src/schemas/payoff.py` + `test_payoff.py`
5. **Wave 4 (Audit function):** `src/schemas/audit.py` + `tests/schemas/test_audit.py` + `tests/schemas/conftest.py`
6. **Wave 5 (Cross-cutting tests):** `tests/schemas/test_classification.py`, `tests/schemas/test_schema_export.py`
7. **Wave 6 (Final):** Update `src/schemas/__init__.py` with complete re-exports

## Metadata

**Analog search scope:** `/Users/hart/develop/keiba-ai-v2/` (full project root)
**Python files found:** 0
**Directories scanned:** 8 (root, .planning/, .planning/phases/, .planning/research/, data/, data/raw/, data/raw/kaggle/, docs/)
**Pattern extraction date:** 2026-06-11
