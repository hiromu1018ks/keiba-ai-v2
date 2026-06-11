# Phase 1: Data Schema & Leak Audit - Research

**Researched:** 2026-06-11
**Domain:** Pydantic v2 schema definition, data leakage prevention, Kaggle horseracing data structure
**Confidence:** HIGH

## Summary

Phase 1 defines the standard-layer schema contract for 5 tables (race, entry, result, odds_trifecta, payoff) and builds a metadata-driven audit function that prevents post-race information from leaking into feature generation. The implementation uses Pydantic v2 `BaseModel` with `Field(json_schema_extra={...})` to tag each column's pre-race/post-race classification, then introspects `model_fields` at runtime to detect leakage in any DataFrame.

The Kaggle source data has been thoroughly analyzed. `race_result.csv` has 66 columns (1.63M rows), containing race/entry/result data mixed in a single flat file. `odds.csv` has 104 columns (122K rows) with trifecta data limited to top-3 popular combinations. All column names are in Japanese. The `payoff` table has no direct Kaggle source -- it must be derived from the trifecta odds data combined with result data, or deferred to the scraping phase. The `レース記号/` prefix columns (20 columns) are boolean flags that encode race conditions like handicap, age-restricted, filly-only, etc.

**Primary recommendation:** Use `json_schema_extra` in Pydantic `Field()` to carry `pre_race` (bool) and `table` (str) metadata. The audit function reads `Model.model_fields` to build a set of post-race column names, then checks any DataFrame's columns against that set. This approach requires zero external dependencies, is machine-readable via `model_json_schema()`, and integrates naturally with Phase 2 and Phase 3 pipelines.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Pydantic `BaseModel` for each table schema, file-separated (`schemas/race.py`, `schemas/entry.py`, `schemas/result.py`, `schemas/odds_trifecta.py`, `schemas/payoff.py`)
- **D-02:** Pydantic for type definition only, not row-level validation (472MB CSV is too slow for row-by-row Pydantic)
- **D-03:** 人気・単勝オッズ = post-race (not usable in feature layer, EV calculation only)
- **D-04:** 三連複オッズ = post-race (EV calculation only)
- **D-05:** 馬体重・場体重増減 = pre-race (usable in feature layer)
- **D-06:** REQUIREMENTS DATA-03 must remove 人気・単勝オッズ
- **D-07:** 5 tables fully separated: race, entry, result, odds_trifecta, payoff
- **D-08:** 騎手・調教師 = entry table string columns (no master table, Phase 3 uses groupby for rolling stats)
- **D-09:** entry <-> result join key: `horse_race_id` = `{race_id}_{馬番}`, 1-to-1 relationship
- **D-10:** `Field(metadata={"pre_race": True/False})` for per-column metadata-driven classification
- **D-11:** Audit timing: both standard generation (Phase 2) and feature generation (Phase 3)
- **D-12:** Post-race detection = warning log only, do not raise exceptions

### Claude's Discretion
- Exact column name mapping (Kaggle Japanese -> standard English names)
- Pydantic model validation rules (nullable, range checks, etc.)
- Audit function API design (function name, parameters, return value)
- Project structure (`src/` vs flat)

### Deferred Ideas (OUT OF SCOPE)
None
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DATA-01 | raw/standard/feature 3-layer schema definition with documented column names, data types, and storage format | This research defines all 5 standard tables with Pydantic models including column names, Python types, and nullability. See Architecture Patterns for the 3-layer design and Kaggle Column Analysis for the full mapping. |
| DATA-04 | Pre/post column audit mechanism that prevents post-race information from leaking into features | Pydantic `Field(json_schema_extra={"pre_race": bool})` provides machine-readable classification. Audit function introspects `model_fields` to detect post-race columns in any DataFrame. See Code Examples for the verified pattern. |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Schema definition (type contracts) | Python module (no tier) | -- | Pure type definitions consumed by all downstream phases |
| Pre/post-race classification | Python module (no tier) | -- | Metadata embedded in Pydantic Field, read at runtime |
| Audit function | Python module (no tier) | -- | Called from standard generation (Phase 2) and feature generation (Phase 3) |
| JSON schema export | Python module (no tier) | -- | `model_json_schema()` for machine-readable documentation |

Note: This phase produces pure Python library code with no I/O, no database, and no network dependencies. The architectural tiers (raw/standard/feature) are data flow layers, not deployment tiers.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | 2.13.4 | Schema definition with Field metadata for pre/post-race classification | CLAUDE.md fixed choice. `BaseModel` + `Field(json_schema_extra=...)` provides type safety, runtime introspection, and JSON schema generation in one package. Verified working on this machine. [VERIFIED: pip3 index versions] |
| pytest | 9.0.3 | Test framework for schema validation and audit function tests | CLAUDE.md recommended. Verified installed. [VERIFIED: pytest --version] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| ruff | 0.15.16 | Linter + formatter | All Python files. Single tool replacing black/flake8/isort. [VERIFIED: pip3 index versions] |
| mypy | 2.1.0 | Static type checking | Schema definitions benefit from strict type checking. Ensures Pydantic models are type-safe. [VERIFIED: pip3 index versions] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `json_schema_extra` dict | `metadata` parameter with `Annotated` types | `metadata` uses Pydantic constraint objects (Gt, Lt, etc.) not arbitrary dicts. `json_schema_extra` carries arbitrary key-value pairs AND appears in JSON schema output. Clear winner for our use case. |
| Pydantic models | Plain dataclasses + YAML config | Dataclasses lack `model_fields` introspection and `model_json_schema()`. Pydantic gives both for free. |
| Separate YAML classification file | Embedded Field metadata | Embedding avoids sync issues -- the classification lives with the field definition, not in a separate file that can drift. |

**Installation:**
```bash
# Phase 1 requires only pydantic and pytest (both already installed)
pip install pydantic pytest ruff mypy
```

**Version verification:**
```
pydantic 2.13.4 (installed, pip3 index verified)
pytest   9.0.3  (installed, pytest --version verified)
ruff     0.15.16 (pip3 index verified)
mypy     2.1.0  (pip3 index verified)
```

## Package Legitimacy Audit

| Package | Registry | Age | Source Repo | Verdict | Disposition |
|---------|----------|-----|-------------|---------|-------------|
| pydantic | PyPI | ~5 yrs | github.com/pydantic/pydantic | OK | Approved -- SUS flag is "unknown-downloads" only, PyPI API limitation |
| pytest | PyPI | ~10 yrs | github.com/pytest-dev/pytest | OK | Approved -- SUS flag is "unknown-downloads" only |
| ruff | PyPI | ~3 yrs | github.com/astral-sh/ruff | OK | Approved -- SUS flag is "too-new" + "unknown-downloads"; ruff is widely adopted |
| mypy | PyPI | ~10 yrs | github.com/python/mypy | OK | Approved -- SUS flag is "unknown-downloads" only |

**Packages removed due to SLOP verdict:** none
**Packages flagged as suspicious [SUS]:** none (all SUS flags are "unknown-downloads" from PyPI API, not genuine quality concerns)

*All packages are well-known, established Python ecosystem tools with public GitHub repositories and active maintenance. The "unknown-downloads" signal is a PyPI API limitation -- these packages collectively have tens of millions of monthly downloads.*

## Architecture Patterns

### System Architecture Diagram

```
Kaggle race_result.csv (66 cols, 1.63M rows)
    |
    v
[Schema Definition Phase 1] --> Pydantic BaseModels (5 tables)
    |                              |
    |                              +-- model_fields (runtime introspection)
    |                              +-- model_json_schema() (machine-readable doc)
    |                              +-- json_schema_extra.pre_race (classification)
    |
    v
[Audit Function] <-- checks DataFrame columns against post-race set
    |
    +-- Phase 2 (Kaggle Pipeline): validates standard output
    +-- Phase 3 (Feature Engineering): validates feature DataFrame
    +-- Phase 4 (Scraping): validates scraped standard output
```

```
Kaggle odds.csv (104 cols, 122K rows)
    |
    v
[odds_trifecta table] <-- top-3 popular trifecta only (54% of races)
[payoff table]         <-- derived from trifecta odds + results (Phase 2)
```

### Recommended Project Structure
```
src/
├── schemas/              # Phase 1: Pydantic schema definitions
│   ├── __init__.py       # Re-exports all table models + audit function
│   ├── race.py           # RaceSchema model
│   ├── entry.py          # EntrySchema model
│   ├── result.py         # ResultSchema model
│   ├── odds_trifecta.py  # OddsTrifectaSchema model
│   ├── payoff.py         # PayoffSchema model
│   └── audit.py          # audit_leakage() function
tests/
├── schemas/              # Phase 1: Schema and audit tests
│   ├── test_race.py
│   ├── test_entry.py
│   ├── test_result.py
│   ├── test_odds_trifecta.py
│   ├── test_payoff.py
│   └── test_audit.py
pyproject.toml            # Project configuration (Poetry or pip)
```

### Pattern 1: Pydantic Schema with Pre-Race Metadata
**What:** Define table schemas using Pydantic `BaseModel` with `Field(json_schema_extra=...)` for pre/post-race classification.
**When to use:** Every table model in the standard layer.
**Example:**
```python
# Source: Verified working on Python 3.12 + Pydantic 2.13.4
from pydantic import BaseModel, Field
from typing import Optional

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
    course_code: str = Field(
        description="Course code (01-10)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    course_name: str = Field(
        description="Course name in Japanese",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    distance: int = Field(
        description="Distance in meters",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    weather: Optional[str] = Field(
        default=None,
        description="Weather condition",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
    track_condition: Optional[str] = Field(
        default=None,
        description="Track condition (良/稍重/重/不良)",
        json_schema_extra={"pre_race": True, "table": "race"},
    )
```

### Pattern 2: Audit Function via Field Introspection
**What:** Runtime function that checks a DataFrame's columns against post-race column names derived from Pydantic model metadata.
**When to use:** After standard generation (Phase 2) and before feature generation (Phase 3).
**Example:**
```python
# Source: Verified working on Python 3.12 + Pydantic 2.13.4
from pydantic import BaseModel
from loguru import logger

def get_post_race_columns(model_class: type[BaseModel]) -> set[str]:
    """Extract set of post-race column names from a Pydantic model."""
    post_race = set()
    for name, info in model_class.model_fields.items():
        extra = info.json_schema_extra or {}
        if isinstance(extra, dict) and not extra.get("pre_race", True):
            post_race.add(name)
    return post_race

def audit_leakage(
    model_classes: list[type[BaseModel]],
    df_columns: list[str],
    context: str = "",
) -> list[str]:
    """Check DataFrame columns for post-race leakage.
    
    Returns list of post-race column names found in df_columns.
    Logs warnings but does NOT raise exceptions (per D-12).
    """
    all_post_race: set[str] = set()
    for cls in model_classes:
        all_post_race |= get_post_race_columns(cls)
    
    leaked = [col for col in df_columns if col in all_post_race]
    if leaked:
        logger.warning(
            f"Post-race columns detected in {context}: {leaked}"
        )
    return leaked
```

### Pattern 3: Schema Export for Machine-Readable Documentation
**What:** Use `model_json_schema()` to export the complete schema including `pre_race` metadata.
**When to use:** Generating documentation, CI checks, and downstream tooling.
**Example:**
```python
# Source: Verified -- json_schema_extra keys appear in model_json_schema() output
import json
from schemas.race import RaceSchema
from schemas.entry import EntrySchema
from schemas.result import ResultSchema

# Generate combined schema
schemas = {
    "race": RaceSchema.model_json_schema(),
    "entry": EntrySchema.model_json_schema(),
    "result": ResultSchema.model_json_schema(),
}
print(json.dumps(schemas, indent=2, ensure_ascii=False))
# Each property includes "pre_race": true/false in the JSON schema
```

### Anti-Patterns to Avoid
- **Anti-pattern: Row-level Pydantic validation on 472MB CSV.** Per D-02, this is explicitly rejected -- 1.63M rows x BaseModel instantiation = OOM or hours of processing. Use Pydantic for type definition, validate at DataFrame level with pandas `assert` or `dtype` checks.
- **Anti-pattern: Separate YAML file for pre/post classification.** Leads to drift between the schema definition and the classification. Embed classification in the Pydantic Field metadata so it stays synchronized.
- **Anti-pattern: Raising exceptions on post-race detection.** Per D-12, post-race columns in a feature DataFrame should generate a warning log only, not crash the pipeline.
- **Anti-pattern: Including the 20 `レース記号/` columns as individual columns in the race table.** These are sparse boolean flags (most are empty for 90%+ of rows). Consider consolidating into a single `race_conditions` JSON/array field or keeping them as optional boolean fields.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Schema introspection | Custom reflection/metaclass system | `BaseModel.model_fields` | Pydantic v2 provides `FieldInfo` with annotation, default, metadata. Zero code needed. |
| JSON Schema generation | Custom schema serializer | `BaseModel.model_json_schema()` | Handles Optional, nested types, constraints, and custom extras automatically. |
| Nullable type handling | Manual None checks + type dispatch | `Optional[T]` with `Field(default=None)` | Pydantic handles `None` vs missing, generates correct anyOf schema, integrates with mypy. |

**Key insight:** The entire audit mechanism leverages Pydantic's built-in introspection. No custom metadata framework, no separate config files, no metaclass magic. The classification is embedded where the field is defined and read where it's needed.

## Common Pitfalls

### Pitfall 1: BOM in Kaggle CSV First Column
**What goes wrong:** `race_result.csv` has a UTF-8 BOM (`﻿`) on the first column name. Reading with `csv.DictReader` produces a column named `﻿レース馬番ID` instead of `レース馬番ID`.
**Why it happens:** The CSV file was saved with BOM encoding, common in Japanese Excel exports.
**How to avoid:** Always open with `encoding='utf-8-sig'` which strips the BOM automatically:
```python
with open('race_result.csv', 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
```
**Warning signs:** KeyError on first column, or `model_fields` not matching CSV header.

### Pitfall 2: `人気` and `単勝オッズ` are Ambiguous
**What goes wrong:** These are determined at betting close (just before race start), NOT after the race. However, per D-03, they are classified as **post-race** for feature purposes because they encode market information that the model should not use. The model must predict purely from horse/race characteristics, then compare against odds for EV calculation.
**Why it happens:** The temporal boundary of "when data becomes available" (before race) differs from "what data the model should use" (exclude market signals).
**How to avoid:** Explicitly document: `pre_race` in this system means "safe for feature engineering", NOT "available before race start". `人気` and `単勝オッズ` are available before the race but excluded from features by design decision.
**Warning signs:** If someone argues `人気` should be pre-race because it's known at post time, point to D-03/D-06.

### Pitfall 3: `上り` (Last 3F) and `通過順` (Corner Positions) are Context-Dependent
**What goes wrong:** The CURRENT race's `上り` and `1-4コーナー` are post-race (race result). But PAST races' values used as lag features in Phase 3 are pre-race (they're historical data).
**Why it happens:** The pre/post classification depends on temporal context, not the column name alone.
**How to avoid:** The schema classification tags the CURRENT race's values as post-race. Phase 3's lag feature generation creates NEW columns (e.g., `prev_1_last_3f`, `prev_1_corner_4`) that are pre-race by construction. The audit function checks column names, not values -- so lag feature columns won't trigger the audit.
**Warning signs:** If the audit function checks column name substrings (e.g., `contains('上り')`) instead of exact matches, it would false-positive on lag features. Always use exact column name matching.

### Pitfall 4: Payoff Table Has No Direct Kaggle Source
**What goes wrong:** There is no separate payoff/payout CSV in the Kaggle dataset. The `odds.csv` contains trifecta odds for top-3 combinations, and `race_result.csv` has per-horse `賞金(万円)`, but there is no "this trifecta combination paid X yen" data.
**Why it happens:** Kaggle dataset doesn't include full trifecta payout records.
**How to avoid:** For Phase 1, define the `payoff` table schema based on what Phase 5 (scraping) and Phase 8 (EV calculation) will need. The schema can have no data initially -- it's a contract for future phases. For backtesting payoff validation, Phase 2 can derive approximate payouts from `三連複N_オッズ` for the top-3 combinations that have data (54% of races).
**Warning signs:** Don't assume payoff data exists for all races. Only 54% of races have even 1 trifecta odds entry.

### Pitfall 5: `レース記号/` Columns are Sparse Boolean Flags
**What goes wrong:** 20 columns with prefix `レース記号/` where the value is either empty string or the column name itself (e.g., `レース記号/牝` has value `牝` or `""`). Treating them as strings wastes memory and confuses dtype detection.
**Why it happens:** The Kaggle data encodes boolean flags as "value present or empty string".
**How to avoid:** Map these to boolean fields in the race schema. For standard layer, convert to `bool` type: `True` if non-empty, `False` if empty. Alternatively, consolidate into a single `race_conditions: list[str]` field if the individual columns are rarely queried.
**Warning signs:** Pydantic would validate `""` as a valid string, masking the boolean nature.

### Pitfall 6: `着順注記` Indicates Non-Finishers
**What goes wrong:** Rows with `着順注記` values like `中` (mid-race withdrawal), `取` (scratched), `失` (disqualified), `除` (removed), `再` (re-run) have numeric `着順` but represent non-standard results. 1.1% of rows have empty `着順` and some may have special `着順注記` values.
**Why it happens:** These are edge cases in race results that the result table must handle.
**How to avoid:** Make `finish_position` Optional[int] in the result schema. Include `finish_note` as Optional[str]. Phase 3 must filter these out before computing finish-based features.
**Warning signs:** If `finish_position` is non-nullable, data conversion will fail or produce incorrect values.

## Kaggle Column Analysis

### race_result.csv: Complete Column Inventory (66 columns)

**Verified via `head -1` + `csv.DictReader` on actual file.** All column names confirmed.

| # | Japanese Name | English Name (proposed) | Type | Nullable | Pre-race | Table | Notes |
|---|---------------|------------------------|------|----------|----------|-------|-------|
| 1 | レース馬番ID | horse_race_id | str | No | Yes | entry | 14-digit unique key |
| 2 | レースID | race_id | str | No | Yes | race | 12-digit key |
| 3 | レース日付 | race_date | str | No | Yes | race | YYYY-MM-DD |
| 4 | 開催回数 | meeting_num | int | No | Yes | race | |
| 5 | 競馬場コード | course_code | str | No | Yes | race | 01-10 |
| 6 | 競馬場名 | course_name | str | No | Yes | race | Japanese |
| 7 | 開催日数 | meeting_day | int | No | Yes | race | Day within meeting |
| 8 | 競争条件 | race_condition | str | No | Yes | race | e.g. "4歳以上300万下" |
| 9-28 | レース記号/* (20 cols) | race_flags_* | bool | Yes | Yes | race | Sparse boolean flags |
| 29 | レース番号 | race_number | int | No | Yes | race | Race # within day |
| 30 | 重賞回次 | grade_revision | Optional[str] | Yes (96.3%) | Yes | race | e.g. "22" for 22nd running |
| 31 | レース名 | race_name | str | No | Yes | race | |
| 32 | リステッド・重賞競走 | grade | Optional[str] | Yes | Yes | race | G1/G2/G3/G/listed or empty |
| 33 | 障害区分 | obstacle | Optional[str] | Yes | Yes | race | "障害" or empty |
| 34 | 芝・ダート区分 | surface | str | No | Yes | race | "芝"/"ダート" |
| 35 | 芝・ダート区分2 | surface_detail | Optional[str] | Yes | Yes | race | |
| 36 | 右左回り・直線区分 | direction | str | No | Yes | race | "右"/"左" |
| 37 | 内・外・襷区分 | course_detail | Optional[str] | Yes | Yes | race | "外"/"内2周"/"襷"/"外-内" |
| 38 | 距離(m) | distance | int | No | Yes | race | Meters |
| 39 | 天候 | weather | Optional[str] | Yes | Yes | race | 晴/曇/雨/小雨/雪/小雪 |
| 40 | 馬場状態1 | track_condition | Optional[str] | Yes | Yes | race | 良/稍重/重/不良 |
| 41 | 馬場状態2 | track_condition_detail | Optional[str] | Yes | Yes | race | |
| 42 | 発走時刻 | start_time | str | No | Yes | race | HH:MM |
| 43 | 着順 | finish_position | Optional[int] | Yes (1.1%) | **No** | result | 1-24 or empty |
| 44 | 着順注記 | finish_note | Optional[str] | Yes | **No** | result | 中/取/失/除/再 |
| 45 | 枠番 | bracket_num | int | No | Yes | entry | 1-8 |
| 46 | 馬番 | horse_number | int | No | Yes | entry | 1-18+ |
| 47 | 馬名 | horse_name | str | No | Yes | entry | |
| 48 | 性別 | sex | str | No | Yes | entry | 牝/牡/セ |
| 49 | 馬齢 | age | int | No | Yes | entry | |
| 50 | 斤量 | weight_assigned | float | No | Yes | entry | Carried weight in kg |
| 51 | 騎手 | jockey | str | No | Yes | entry | |
| 52 | タイム | finish_time | Optional[str] | Yes (1.0%) | **No** | result | "M:SS.T" format |
| 53 | 着差 | margin | Optional[str] | Yes (10.0%) | **No** | result | e.g. "1.1/4", "大", "ハナ" |
| 54 | 1コーナー | corner_1 | Optional[int] | Yes (52.1%) | **No** | result | Position at 1st corner |
| 55 | 2コーナー | corner_2 | Optional[int] | Yes (44.0%) | **No** | result | |
| 56 | 3コーナー | corner_3 | Optional[int] | Yes (0.7%) | **No** | result | |
| 57 | 4コーナー | corner_4 | Optional[int] | Yes (0.6%) | **No** | result | |
| 58 | 上り | last_3f | Optional[float] | Yes (4.8%) | **No** | result | Final 3 furlong time |
| 59 | 単勝 | win_odds | Optional[float] | Yes (0.4%) | **No** | entry | D-03: post-race for features |
| 60 | 人気 | popularity | Optional[int] | Yes (0.4%) | **No** | entry | D-03: post-race for features |
| 61 | 馬体重 | horse_weight | Optional[int] | Yes (0.3%) | Yes | entry | |
| 62 | 場体重増減 | weight_change | Optional[int] | Yes (0.3%) | Yes | entry | Can be negative |
| 63 | 東西・外国・地方区分 | region | Optional[str] | Yes | Yes | entry | 東/西 |
| 64 | 調教師 | trainer | str | No | Yes | entry | |
| 65 | 馬主 | owner | str | No | Yes | entry | |
| 66 | 賞金(万円) | prize_money | Optional[float] | Yes (55.0%) | **No** | result | In 10K yen |

### odds.csv: Trifecta-Relevant Columns

| # | Japanese Name | English Name | Type | Nullable | Pre-race | Table | Notes |
|---|---------------|-------------|------|----------|----------|-------|-------|
| 1 | レースID | race_id | str | No | Yes | odds_trifecta | 12-digit key |
| 75-77 | 三連複1_組合せ1-3 | trifecta1_combo_1/2/3 | Optional[int] | Yes | **No** | odds_trifecta | Horse numbers |
| 78-80 | 三連複2_組合せ1-3 | trifecta2_combo_1/2/3 | Optional[int] | Yes | **No** | odds_trifecta | |
| 81-83 | 三連複3_組合せ1-3 | trifecta3_combo_1/2/3 | Optional[int] | Yes | **No** | odds_trifecta | |
| 84 | 三連複1_オッズ | trifecta1_odds | Optional[int] | Yes | **No** | odds_trifecta | In 0.1 units (990 = 99.0x) |
| 85 | 三連複2_オッズ | trifecta2_odds | Optional[int] | Yes | **No** | odds_trifecta | Only 0.1% of rows |
| 86 | 三連複3_オッズ | trifecta3_odds | Optional[int] | Yes | **No** | odds_trifecta | Only 0.002% of rows |
| 87-89 | 三連複1-3_人気 | trifecta1-3_popularity | Optional[int] | Yes | **No** | odds_trifecta | |

**Key finding:** Only 54.1% of odds.csv rows have `三連複1_オッズ` data. `三連複2` and `三連複3` are nearly empty (0.1% and 0.002%). Kaggle trifecta data is severely limited.

### Key Data Facts (Verified)
- `race_result.csv`: 1,626,812 rows (including header), 66 columns, 472MB
- `odds.csv`: 121,939 rows (including header), 104 columns, 22MB
- Unique `レースID` in first 100K rows: 8,992
- `レースID` format: `YYYYPPCCDDRR` (12 digits: year 4 + place 2 + meeting 2 + day 2 + race 2)
- `レース馬番ID` format: `YYYYPPCCDDRRHH` (14 digits: race_id + horse_number 2 digits)

## Code Examples

Verified patterns from official Pydantic v2 documentation and local testing:

### Complete Schema Example: Entry Table
```python
# Source: Pydantic v2 docs (pydantic.dev/docs/validation/latest/concepts/fields/)
# Verified working: Python 3.12.13 + pydantic 2.13.4
from pydantic import BaseModel, Field
from typing import Optional

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
    horse_name: str = Field(
        description="Horse name",
        json_schema_extra={"pre_race": True, "table": "entry"},
    )
    sex: str = Field(
        description="Sex: 牝/牡/セ",
        json_schema_extra={"pre_race": True, "table": "entry"},
    )
    age: int = Field(
        description="Horse age",
        ge=2,
        json_schema_extra={"pre_race": True, "table": "entry"},
    )
    weight_assigned: float = Field(
        description="Assigned weight in kg",
        json_schema_extra={"pre_race": True, "table": "entry"},
    )
    jockey: str = Field(
        description="Jockey name",
        json_schema_extra={"pre_race": True, "table": "entry"},
    )
    trainer: str = Field(
        description="Trainer name",
        json_schema_extra={"pre_race": True, "table": "entry"},
    )
    horse_weight: Optional[int] = Field(
        default=None,
        description="Horse weight (kg), measured on race day",
        json_schema_extra={"pre_race": True, "table": "entry"},
    )
    weight_change: Optional[int] = Field(
        default=None,
        description="Weight change from previous race (can be negative)",
        json_schema_extra={"pre_race": True, "table": "entry"},
    )
    # D-03: 人気 and 単勝 are post-race for feature purposes
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

### Complete Audit Function
```python
# Source: Verified working locally
from pydantic import BaseModel
from loguru import logger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

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

### Export Machine-Readable Schema
```python
# Source: Verified -- json_schema_extra appears in model_json_schema() output
import json
from schemas import (
    RaceSchema, EntrySchema, ResultSchema,
    OddsTrifectaSchema, PayoffSchema,
)

def export_schema_documentation() -> dict:
    """Export all table schemas as machine-readable JSON."""
    return {
        "race": RaceSchema.model_json_schema(),
        "entry": EntrySchema.model_json_schema(),
        "result": ResultSchema.model_json_schema(),
        "odds_trifecta": OddsTrifectaSchema.model_json_schema(),
        "payoff": PayoffSchema.model_json_schema(),
    }

# Each property in the JSON schema includes "pre_race": true/false
# This can be written to docs/schema.json for documentation
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Pydantic v1 `__fields__` | Pydantic v2 `model_fields` + `FieldInfo` | Pydantic v2 (2023) | `model_fields` returns `FieldInfo` objects with `json_schema_extra`. `__fields__` is removed. |
| Pydantic v1 `Field(extra=...)` | Pydantic v2 `Field(json_schema_extra=...)` | Pydantic v2 (2023) | `extra` parameter removed. Use `json_schema_extra` for arbitrary metadata. |
| Separate schema config files | Embedded Field metadata | This project | Classification lives with field definition. No sync drift. |
| Exception on leakage | Warning log only (D-12) | This project design | Pipeline continues even with detected leakage. Allows exploration while still alerting. |

**Deprecated/outdated:**
- Pydantic v1 API (`__fields__`, `.Field(extra=...)`, `.dict()`): Removed in v2. Use `model_fields`, `json_schema_extra`, `model_dump()`.
- Python 3.9 `Optional[T]` only: Python 3.10+ supports `T | None` syntax. Either works with Pydantic v2, but `Optional[T]` is clearer for this project's audience.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `json_schema_extra` dict values survive `model_json_schema()` roundtrip | Code Examples | Low -- verified locally with Pydantic 2.13.4 |
| A2 | Payoff table can be defined as schema-only in Phase 1 with no data source until Phase 5 | Architecture | Medium -- Phase 2 may need to derive partial payoff data from trifecta odds for backtesting |
| A3 | `Field(json_schema_extra={"pre_race": True/False})` is the correct metadata mechanism per D-10 (which says `Field(metadata={...})`) | User Constraints | Low -- D-10 mentions `metadata=` but Pydantic v2 `metadata` parameter takes constraint objects, not arbitrary dicts. `json_schema_extra` is the correct mechanism. Planner should confirm this interpretation. |
| A4 | English column names proposed in the Kaggle Column Analysis table are appropriate | Kaggle Column Analysis | Low -- Claude's discretion per CONTEXT.md, but naming affects all downstream phases |
| A5 | `owner` (馬主) column should be in entry table | Kaggle Column Analysis | Low -- rarely used in ML, but storing it doesn't hurt |

**If this table is empty:** N/A -- assumptions present, see above.

## Open Questions

1. **D-10 says `metadata=` but Pydantic v2 `metadata` parameter is for constraint objects, not arbitrary dicts.**
   - What we know: `json_schema_extra` works perfectly for arbitrary key-value metadata. `metadata` is for Pydantic constraint objects like `Gt`, `Lt`, `Interval`.
   - What's unclear: Whether the user specifically wants `metadata=` parameter or just "metadata-driven classification" in general.
   - Recommendation: Use `json_schema_extra={"pre_race": True/False}` and note this satisfies D-10's intent. The planner should confirm.

2. **Payoff table data source:**
   - What we know: No direct Kaggle payoff data. Trifecta odds (top-3 combos, 54% coverage) are the closest data.
   - What's unclear: Whether Phase 1 should define a payoff schema with expected data fields or defer entirely.
   - Recommendation: Define the schema based on what Phase 8 (EV calculation) needs: `race_id`, `combination` (3 horse numbers), `odds`, `payoff_amount`. Leave data population to Phase 2 (partial, from odds.csv) and Phase 5 (full, from scraping).

3. **`レース記号/` columns: 20 individual boolean fields or consolidated?**
   - What we know: 20 sparse boolean columns, most empty for 90%+ rows. Values are the column name itself (e.g., "牝") or empty string.
   - What's unclear: Whether to keep them as individual Optional[bool] fields or consolidate into a single `list[str]` field.
   - Recommendation: Claude's discretion. Individual bool fields are more explicit and schema-friendly. Consolidation is more compact. Suggest individual bool fields for schema clarity.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12+ | Runtime | Yes | 3.12.13 | -- |
| pydantic | Schema definition | Yes | 2.13.4 | -- |
| pytest | Testing | Yes | 9.0.3 | -- |
| ruff | Linting/formatting | Yes | 0.15.16 | -- |
| mypy | Type checking | Yes | 2.1.0 | -- |
| Poetry | Dependency management | No | -- | Use pip + requirements.txt or create pyproject.toml manually |
| pandas | Data inspection (tests only) | Yes (system) | -- | -- |

**Missing dependencies with no fallback:**
- None for Phase 1 (schema definition only)

**Missing dependencies with fallback:**
- Poetry: not installed. Phase 1 can create `pyproject.toml` and `requirements.txt` manually. Poetry installation should happen before Phase 2 when data pipeline code begins.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 |
| Config file | None -- see Wave 0 |
| Quick run command | `pytest tests/schemas/ -x -q` |
| Full suite command | `pytest tests/ -x -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-01 | All 5 table schemas defined with correct field names, types, nullability | unit | `pytest tests/schemas/test_race.py tests/schemas/test_entry.py tests/schemas/test_result.py tests/schemas/test_odds_trifecta.py tests/schemas/test_payoff.py -x` | No -- Wave 0 |
| DATA-01 | model_json_schema() output is valid JSON with all fields | unit | `pytest tests/schemas/test_schema_export.py -x` | No -- Wave 0 |
| DATA-04 | audit_leakage() detects post-race columns in a DataFrame | unit | `pytest tests/schemas/test_audit.py::test_detects_post_race -x` | No -- Wave 0 |
| DATA-04 | audit_leakage() returns empty list for pre-race-only DataFrame | unit | `pytest tests/schemas/test_audit.py::test_no_leakage -x` | No -- Wave 0 |
| DATA-04 | audit_leakage() logs warning, does not raise, on detection | unit | `pytest tests/schemas/test_audit.py::test_warning_no_exception -x` | No -- Wave 0 |
| DATA-04 | All Kaggle columns classified as pre-race or post-race | unit | `pytest tests/schemas/test_classification.py -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/schemas/ -x -q`
- **Per wave merge:** `pytest tests/ -x -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/schemas/__init__.py` -- test package init
- [ ] `tests/schemas/conftest.py` -- shared fixtures (sample DataFrames, model class lists)
- [ ] `tests/schemas/test_race.py` -- covers DATA-01 for race table
- [ ] `tests/schemas/test_entry.py` -- covers DATA-01 for entry table
- [ ] `tests/schemas/test_result.py` -- covers DATA-01 for result table
- [ ] `tests/schemas/test_odds_trifecta.py` -- covers DATA-01 for odds_trifecta table
- [ ] `tests/schemas/test_payoff.py` -- covers DATA-01 for payoff table
- [ ] `tests/schemas/test_audit.py` -- covers DATA-04 audit function
- [ ] `tests/schemas/test_classification.py` -- covers DATA-04 complete classification
- [ ] `tests/schemas/test_schema_export.py` -- covers DATA-01 JSON schema export
- [ ] `src/schemas/__init__.py` -- source package init
- [ ] `pyproject.toml` -- project configuration

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | N/A -- no user authentication in this phase |
| V3 Session Management | No | N/A -- no sessions |
| V4 Access Control | No | N/A -- no access control |
| V5 Input Validation | Yes | Pydantic BaseModel Field constraints (ge, le, max_length) |
| V6 Cryptography | No | N/A -- no cryptographic operations |

### Known Threat Patterns for Python Schema Definition

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| None relevant | -- | This phase produces only type definitions and a pure function. No network, no file I/O, no user input, no database. Security surface is negligible. |

## Sources

### Primary (HIGH confidence)
- Actual Kaggle CSV file analysis (`race_result.csv` 66 columns, `odds.csv` 104 columns) -- all column names, data types, and nullability patterns verified via direct file inspection
- Pydantic v2 `Field(json_schema_extra=...)` pattern verified working on local Python 3.12.13 + pydantic 2.13.4

### Secondary (MEDIUM confidence)
- [Pydantic Fields documentation](https://docs.pydantic.dev/latest/concepts/fields/) -- Field introspection, json_schema_extra, model_fields
- [Pydantic Models documentation](https://pydantic.dev/docs/validation/latest/concepts/models/) -- BaseModel concepts

### Tertiary (LOW confidence)
- None -- all findings verified or cited from official sources

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - pydantic 2.13.4 verified installed and tested locally
- Architecture: HIGH - audit function pattern verified with working code
- Kaggle column analysis: HIGH - all 66+104 columns examined directly from source files
- Pitfalls: HIGH - BOM issue, sparsity patterns, and edge cases verified empirically
- Column classification: HIGH - based on CONTEXT.md decisions D-03 through D-06

**Research date:** 2026-06-11
**Valid until:** 2026-07-11 (stable domain -- Pydantic API and Kaggle data are static)
