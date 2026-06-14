# Phase 6: Data Integration - Pattern Map

**Mapped:** 2026-06-14
**Files analyzed:** 4 (2 new + 2 modified)
**Analogs found:** 4 / 4

Phase 6 is a **wiring phase** that introduces NO new primitives. Every pattern (typed reindex, strict recast, PK dedup, atomic write, physical-type equality) already exists in Phase 2 (`src/pipeline/kaggle_converter.py`, `src/pipeline/validators.py`) or Phase 4 (`src/scraper/normalizer.py`, `tests/scraper/test_end_to_end.py`). The planner's job is to assemble these into the new `integration.py` module and to apply two small edits (`column_mapping.py:68` removal + `kaggle_converter.py` nullable-dtype application).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/pipeline/integration.py` (NEW) | service / pipeline | transform (read-merge-dedup-write) | `src/scraper/normalizer.py` (`write_partitioned_parquet`, `_recast_for_storage`, `_atomic_write_parquet`) | exact (same primitives, single-file target) |
| `tests/pipeline/test_integration.py` (NEW) | test | pytest integration/unit | `tests/scraper/test_end_to_end.py` (`TestSchemaCompatibility`) + `tests/pipeline/test_kaggle_converter.py` | exact (Phase 4 schema-equality pattern + Phase 2 converter test style) |
| `src/pipeline/column_mapping.py:68` (MODIFY) | config (data dict) | declarative | `src/scraper/flag_crosswalk.py` (`FLAG_CROSSWALK`, intentional `(国際)` omission docstring) | exact (the same edit was already applied on the scraper side in Phase 4 P07) |
| `src/pipeline/kaggle_converter.py` (MODIFY) | service / pipeline | transform (CSV→Parquet) | `src/scraper/normalizer.py` (`_build_typed_dataframe`, `SCHEMA_DTYPE_MAP`, `_recast_for_storage`) | exact (Phase 6 must bring Kaggle side up to the Phase 4 dtype discipline already proven there) |

> **Note:** `tests/pipeline/test_kaggle_converter.py` is touched indirectly (existing dtype assertions may need updates once D-02 regenerates with nullable types). The closest analog for those edits is the file itself; see the relevant pattern assignment below.

## Pattern Assignments

### `src/pipeline/integration.py` (service / pipeline, transform)

**Analog:** `src/scraper/normalizer.py` — this module already implements every primitive Phase 6 needs (typed reindex, strict recast, PK dedup, atomic write). `integration.py` reuses the helpers, not the partitioned-month logic.

**Imports pattern** — mirror `normalizer.py` lines 66-78 and `kaggle_converter.py` lines 19-31:

```python
# Analog: src/scraper/normalizer.py:66-78
import os
from pathlib import Path

import pandas as pd
from loguru import logger
from pydantic import BaseModel

from src.schemas.entry import EntrySchema
from src.schemas.race import RaceSchema
from src.schemas.result import ResultSchema
```

For the integration module also import the dtype authority and atomic-write helper:

```python
# Analog: src/scraper/normalizer.py imports SCHEMA_DTYPE_MAP / _atomic_write_parquet
# (same module — import directly, no duplication)
from src.scraper.normalizer import SCHEMA_DTYPE_MAP, _atomic_write_parquet
from src.schemas.audit import audit_leakage
```

**Canonical column order (Pattern 1)** — analog `src/scraper/normalizer.py:239` (`_build_typed_dataframe`):

```python
# Analog: src/scraper/normalizer.py:239
columns = list(schema.model_fields.keys())
df = df.reindex(columns=columns)
```

For integration, reindex BOTH Kaggle and scraped frames to the same canonical order BEFORE concat:

```python
canonical = list(schema.model_fields.keys())
kaggle_df = pd.read_parquet(kaggle_path).reindex(columns=canonical)
scraped_df = pd.read_parquet(scraped_path).reindex(columns=canonical)
```

**Strict dtype recast (Pattern 2)** — analog `src/scraper/normalizer.py:200-255` (`_build_typed_dataframe`) and `_recast_for_storage:601-640`. The integration module MUST NOT use `errors="ignore"`; the analog raises `TypeError` on genuine coercion failure:

```python
# Analog: src/scraper/normalizer.py:242-254 (_build_typed_dataframe)
dtype_map = SCHEMA_DTYPE_MAP[schema]
for col, target in dtype_map.items():
    if col not in df.columns:
        continue
    try:
        df[col] = df[col].astype(target)
    except (TypeError, ValueError) as e:
        raise TypeError(
            f"Column {col!r} could not be coerced to {target!r} for "
            f"{schema.__name__}: {e}"
        ) from e
```

`integration.py` should reuse this verbatim as a `_recast_to_canonical(df, schema)` helper (the body is 5 lines; copying the docstring/try-except shape is intentional — see RESEARCH.md Open Question 3).

**PK-based dedup with FAIL LOUD on unexpected overlap (Pattern 3 + Pitfall 6)** — analog `src/scraper/normalizer.py:570-580` (`write_partitioned_parquet` read-merge-dedup) and `validate_integrity:286-308` (duplicate-key detection):

```python
# Analog: src/scraper/normalizer.py:570-580
merged = pd.concat([existing_df, new_partition_df], ignore_index=True)
merged = merged.drop_duplicates(subset=[primary_key], keep="last")
merged = merged.reset_index(drop=True)
```

Phase 6 MUST add a pre-dedup assertion that RAISES on unexpected Kaggle/scraped overlap (Pitfall 6):

```python
# Pattern from normalizer.py:744-756 (hard_violations raise ValueError)
merged = pd.concat([kaggle_df, scraped_df], ignore_index=True)
dup_count = int(merged[pk].duplicated().sum())
if dup_count > 0:
    overlapping = merged.loc[merged[pk].duplicated(keep=False), pk].unique()[:5]
    raise ValueError(
        f"{table}: {dup_count} duplicate {pk} values post-concat — "
        f"unexpected Kaggle/scraped overlap; sample={list(overlapping)}"
    )
```

**Atomic Parquet write (Pattern 4)** — analog `src/scraper/normalizer.py:643-653` (`_atomic_write_parquet`). REUSE this function; do NOT re-implement:

```python
# Analog: src/scraper/normalizer.py:643-653
def _atomic_write_parquet(df: pd.DataFrame, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp_path, engine="pyarrow", compression="snappy", index=False)
    os.replace(tmp_path, path)
```

Note: `to_parquet` parameters (`engine="pyarrow"`, `compression="snappy"`, `index=False`) match `kaggle_converter.py:117` and `normalizer.py:652` — same params for byte-compatible downstream readers.

**Table allowlist (Pitfall 5 — D-05 odds/payoff preservation)** — hardcode the 3-table allowlist; do NOT iterate `TABLE_TO_SCHEMA.keys()` (which includes `odds_trifecta`/`payoff`):

```python
# PHASE-6-SPECIFIC (D-05). Borrow the {table: schema} shape from
# normalizer.py _recast_for_storage:614-619 but RESTRICT to the 3 unified tables.
SCHEMA_BY_TABLE = {
    "race": RaceSchema,
    "entry": EntrySchema,
    "result": ResultSchema,
}
PK_BY_TABLE = {"race": "race_id", "entry": "horse_race_id", "result": "horse_race_id"}
```

**Entry point signature** — follow `normalize_to_parquet` (`src/scraper/normalizer.py:661-664`) shape (Path defaults, returns path mapping):

```python
# Analog: src/scraper/normalizer.py:661-664
def integrate_standard_layer(
    standard_dir: Path = Path("data/standard"),
) -> dict[str, Path]:
    """... returns {'race': Path, 'entry': Path, 'result': Path}"""
```

**Error handling pattern** — loguru structured logging + RAISE on hard violations. Mirror `normalizer.py:744-756` (hard violations raise `ValueError`); never swallow a dtype/overlap failure silently.

**CLI integration (optional)** — if a CLI subcommand is added, follow `src/cli.py` (`@click.group()`, subcommand calls the entry point, `click.BadParameter` for malformed input). Phase 6 tests in RESEARCH.md do not require a CLI; only add if the planner wants one.

---

### `tests/pipeline/test_integration.py` (test, pytest integration/unit)

**Analogs:** `tests/scraper/test_end_to_end.py` (`TestSchemaCompatibility` for physical-type equality) + `tests/pipeline/test_kaggle_converter.py` (converter test style, fixture-driven).

**Imports + module header pattern** — analog `tests/scraper/test_end_to_end.py:34-49`:

```python
# Analog: tests/scraper/test_end_to_end.py:34-49
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from src.schemas.entry import EntrySchema
from src.schemas.race import RaceSchema
from src.schemas.result import ResultSchema
```

**Fixture-driven hermetic test pattern** — analog `tests/pipeline/test_kaggle_converter.py:25-39` (writes CSVs to tmp_path, calls convert(), reads back Parquet). For integration tests, write both Kaggle Parquet + scraped Parquet partitions to `tmp_path`, then call `integrate_standard_layer(standard_dir=tmp_path / "data" / "standard")`.

Reuse the existing `tests/pipeline/conftest.py:291-295` `tmp_standard_dir` fixture and extend with a scraped-partitions fixture:

```python
# Analog: tests/pipeline/conftest.py:291-295 (tmp_standard_dir)
@pytest.fixture
def tmp_standard_dir(tmp_path: Path) -> Path:
    standard_dir = tmp_path / "data" / "standard"
    standard_dir.mkdir(parents=True, exist_ok=True)
    return standard_dir
```

Planner action: add a new `tmp_kaggle_raw_dir` fixture and a `tmp_scraped_partitions_dir` fixture (or a combined helper) to `tests/pipeline/conftest.py` per RESEARCH.md Wave 0 Gaps note. Mirror the `tmp_raw_dir` / `tmp_standard_dir` shape from `tests/scraper/conftest.py:17-33`.

**Physical-type equality assertion (Pattern 5 — success criterion #2)** — analog `tests/scraper/test_end_to_end.py:464-536` (`TestSchemaCompatibility`). Use `pyarrow.parquet.read_schema` and compare `str(field.type)`:

```python
# Analog: tests/scraper/test_end_to_end.py:494-536
def test_physical_type_equality_for_non_null_kaggle_columns(...):
    ...
    schema = pq.read_schema(str(path))
    scraped_types = {f.name: str(f.type) for f in schema}
    for col, kaggle_type in kaggle.items():
        if col in null_cols:
            continue
        if scraped_types[col] != kaggle_type:
            mismatches.append(f"{tbl}.{col}: ...")
    assert not mismatches, ...
```

For Phase 6, simplify to comparing the unified output against `SCHEMA_DTYPE_MAP` (Phase 4 already proved these are byte-compatible with Kaggle). RESEARCH.md "Phase 4 TestSchemaCompatibility pattern (reuse for Phase 6)" has the exact body.

**Audit leakage assertion (Open Question 2)** — analog `src/schemas/audit.py:45-84` (`audit_leakage`). For the unified race table: expect `[]`; for the unified entry table: expect EXACTLY `{'popularity', 'win_odds'}` (intentionally post-race per Phase 1 D-03):

```python
# Analog: src/pipeline/kaggle_converter.py:123-129 (audit call site)
from src.schemas.audit import audit_leakage

race_leaked = audit_leakage([RaceSchema], race_df, "post-integration race audit")
assert race_leaked == []
entry_leaked = audit_leakage([EntrySchema], entry_df, "post-integration entry audit")
assert set(entry_leaked) == {"popularity", "win_odds"}
```

**D-01 graded_stakes count drop assertion** — no analog (new test). RESEARCH.md Pitfall 4 specifies: assert post-fix `race_flag_graded_stakes=True` count drops from 1,348 to ~838. Pattern: read the regenerated `data/standard/race.parquet`, count True rows, assert approximately 838 (use a tolerance bound, e.g. `780 <= count <= 880`).

**D-05 odds/payoff preserved assertion** — analog `tests/pipeline/test_kaggle_converter.py` (file-hash or row-count preservation). Compute mtime or row count of `odds_trifecta.parquet`/`payoff.parquet` BEFORE integration, assert UNCHANGED after. RESEARCH.md Validation Architecture row 9.

**Test class structure** — mirror `tests/scraper/test_end_to_end.py:464` class-based grouping (`class TestSchemaCompatibility:`). Consider grouping Phase 6 tests into `class TestUnifiedCorpus:` with `_require_scraped_data` autouse fixture (analog `_require_kaggle_parquet` at `test_end_to_end.py:467-472`) to skip when the D-06 pre-task scraped data is absent.

---

### `src/pipeline/column_mapping.py:68` (config / declarative dict, MODIFY)

**Analog:** `src/scraper/flag_crosswalk.py` — the scraper side ALREADY made this exact edit in Phase 4 P07. The docstring at `flag_crosswalk.py:20-46` is the canonical reasoning and should be cross-referenced in the Phase 6 commit message.

**Exact change** — delete line 68:

```python
# src/pipeline/column_mapping.py:68 — DELETE this line:
"レース記号/(国際)": ("race", "race_flag_graded_stakes"),
```

The FLAG_COLUMNS list at `column_mapping.py:179-200` ALSO contains `"レース記号/(国際)"` (line 197) and `DTYPE_SPEC` at `column_mapping.py:207` is derived from FLAG_COLUMNS. **Do NOT remove from FLAG_COLUMNS** — that list models the CSV header (the column still EXISTS in the CSV, it just should not map to `race_flag_graded_stakes`). Removing only line 68 from `KAGGLE_COLUMN_MAP` is the correct, surgical fix.

**Post-edit verification** — the analog test guard is `tests/scraper/test_parser.py::test_crosswalk_covers_all_kaggle_flag_targets` (per `flag_crosswalk.py:42-46` docstring). Phase 6 must verify the Kaggle-side equivalent still passes (the flag will simply no longer be set on Kaggle rows where the only signal is `(国際)`). RESEARCH.md Pitfall 4: `race_flag_graded_stakes=True` count drops from 1,348 → ~838 (510 misclassified rows fixed).

**Blast radius** — per CONTEXT.md Claude's Discretion: research agent confirmed this edit does NOT cascade into the other 13 FLAG_CROSSWALK mappings or break existing Phase 2 tests (the `(国際)` column simply stops contributing to `race_flag_graded_stakes`; rows with an actual GI/GII/GIII token in the grade column are unaffected). The planner should still run the full `tests/pipeline/test_column_mapping.py` suite post-edit.

---

### `src/pipeline/kaggle_converter.py` (service / pipeline, MODIFY)

**Analog:** `src/scraper/normalizer.py` (`_build_typed_dataframe`, `SCHEMA_DTYPE_MAP`, `_recast_for_storage`). The Phase 4 dtype discipline is the target state; Phase 6 brings Kaggle up to it.

**Imports pattern** — add `SCHEMA_DTYPE_MAP` import to existing imports at `kaggle_converter.py:19-31`:

```python
# ADD to src/pipeline/kaggle_converter.py imports:
from src.scraper.normalizer import SCHEMA_DTYPE_MAP
```

(Modify the existing import block; do not duplicate the `from pathlib import Path` / `import pandas` lines.)

**Core modification — apply nullable dtypes before write (D-02)** — per RESEARCH.md Open Question 3, the natural chokepoint is the END of `split_race_entry_result` (`kaggle_converter.py:207-278`). Each returned DataFrame has its final shape there. Add a recast pass using the EXACT same loop as `_build_typed_dataframe:242-255`:

```python
# Analog: src/scraper/normalizer.py:242-255 (_build_typed_dataframe)
def _recast_to_canonical(df: pd.DataFrame, schema: type) -> pd.DataFrame:
    """Apply SCHEMA_DTYPE_MAP to a Kaggle-derived DataFrame post-transform."""
    dtype_map = SCHEMA_DTYPE_MAP[schema]
    for col, target in dtype_map.items():
        if col not in df.columns:
            continue
        try:
            df[col] = df[col].astype(target)
        except (TypeError, ValueError) as e:
            raise TypeError(
                f"Column {col!r} could not be coerced to {target!r} for "
                f"{schema.__name__}: {e}"
            ) from e
    return df
```

Call it before returning from `split_race_entry_result`:

```python
# At the END of split_race_entry_result (kaggle_converter.py:278), before return:
race_df = _recast_to_canonical(race_df, RaceSchema)
entry_df = _recast_to_canonical(entry_df, EntrySchema)
result_df = _recast_to_canonical(result_df, ResultSchema)
return race_df, entry_df, result_df
```

Add the imports for the schema classes (already present at `kaggle_converter.py:30-31` for `EntrySchema`/`RaceSchema`; add `ResultSchema`).

**Anti-pattern guard** — do NOT use `errors="ignore"` anywhere in this recast. Per RESEARCH.md "State of the Art" table, the Cycle-2/P05 invention specifically removed `errors="ignore"`; Phase 6 must not reintroduce it. The analog `_build_typed_dataframe` docstring at `normalizer.py:226-234` documents this contract.

**Existing write call — NO change needed.** `kaggle_converter.py:115-119` already uses the correct `to_parquet(engine="pyarrow", compression="snappy", index=False)`. After the recast, the dtypes flow through unchanged.

**Atomic write (optional hardening)** — `kaggle_converter.py:115-119` currently writes non-atomically (`to_parquet` directly). RESEARCH.md does not mandate changing this (the Kaggle regen is reproducible from CSV; not a destructive overwrite in the same sense as the integration write). If the planner wants consistency, swap for `_atomic_write_parquet` from `normalizer.py:643-653` — same params, adds the temp+`os.replace` safety.

**Audit call site** — `kaggle_converter.py:121-129` already calls `audit_leakage` correctly. No change needed for D-02; the regenerated tables will pass the same audit.

---

### `tests/pipeline/test_kaggle_converter.py` (test, MODIFY — indirect via D-02)

**Analog:** itself. Phase 2 tests already assert converter behavior; D-02 changes output dtypes from `object`/`float64` to nullable `Int64`/`Float64`/`boolean`. The planner must:

1. Run the existing suite after the `kaggle_converter.py` edit; any dtype-string assertion that breaks is a candidate for update.
2. Add new assertions mirroring `tests/scraper/test_normalizer.py::TestStrictDtypeEnforcement` (Cycle-2 #3) — read the regenerated `data/standard/race.parquet` via `pyarrow.parquet.read_schema` and assert every `race_flag_*` column is Arrow `bool` (not `null`), per RESEARCH.md Validation Architecture row 8 (`test_kaggle_parquet_post_d02_has_typed_flags`).

**Physical-type assertion pattern** — analog `tests/scraper/test_end_to_end.py:494-536` (`test_physical_type_equality_for_non_null_kaggle_columns`):

```python
# Analog: tests/scraper/test_end_to_end.py:494-536 — adapt for Kaggle regen output
import pyarrow.parquet as pq

def test_kaggle_parquet_post_d02_has_typed_flags(tmp_standard_dir, sample_race_result_df, sample_odds_df):
    # ... write CSVs, call convert() ...
    schema = pq.read_schema(str(tmp_standard_dir / "race.parquet"))
    flag_cols = {f.name: str(f.type) for f in schema if f.name.startswith("race_flag_")}
    null_flags = {name for name, t in flag_cols.items() if t == "null"}
    assert not null_flags, f"Post-D-02 Kaggle flags still Arrow null: {null_flags}"
```

## Shared Patterns

### Strict dtype contract (SCHEMA_DTYPE_MAP authority)
**Source:** `src/scraper/normalizer.py:95-192` (full map for RaceSchema/EntrySchema/ResultSchema)
**Apply to:** `src/pipeline/integration.py` (recast both corpora before concat) AND `src/pipeline/kaggle_converter.py` (apply during D-02 regen)
**Key invariant:** NEVER use `astype(..., errors="ignore")` — failures MUST raise `TypeError`. This contract is documented in `_build_typed_dataframe:226-234` and enforced by the Cycle-2 #3 / Cycle-3 #1 tests in `tests/scraper/test_normalizer.py`. Phase 6 inherits it unchanged.

```python
# THE canonical nullable dtype map — src/scraper/normalizer.py:95-192
# RaceSchema excerpt:
"race_id": "string", "race_date": "string", "meeting_num": "Int64",
"distance": "Int64", "race_flag_graded_stakes": "boolean", ...
# EntrySchema excerpt:
"horse_race_id": "string", "popularity": "Float64", "win_odds": "Float64", ...
# ResultSchema excerpt:
"finish_position": "Int64", "corner_1": "Float64", "corner_2": "Float64", ...
```

### Atomic Parquet write (temp + os.replace)
**Source:** `src/scraper/normalizer.py:643-653` (`_atomic_write_parquet`)
**Apply to:** `src/pipeline/integration.py` (destructive overwrite of `data/standard/{race,entry,result}.parquet` per D-03); OPTIONAL for `src/pipeline/kaggle_converter.py` (Kaggle regen is reproducible, lower stakes)
**Why:** POSIX-atomic; no half-written file if the process is interrupted mid-write. Same `engine="pyarrow"`, `compression="snappy"`, `index=False` params as Phase 2/4 outputs.

```python
# src/scraper/normalizer.py:643-653 — REUSE, do not re-implement
def _atomic_write_parquet(df: pd.DataFrame, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp_path, engine="pyarrow", compression="snappy", index=False)
    os.replace(tmp_path, path)
```

### FAIL LOUD on integrity violations
**Source:** `src/scraper/normalizer.py:744-756` (hard violations raise `ValueError`)
**Apply to:** `src/pipeline/integration.py` — duplicate `race_id`/`horse_race_id` post-concat MUST raise (Pitfall 6), never silently dedup away data loss.
**Pattern:** compute violations → log warning → if any "duplicate"/"orphan" in the message, `raise ValueError(...)` with first-3 sample.

```python
# Analog: src/scraper/normalizer.py:744-756
hard_violations = [v for v in violations if "duplicate" in v or "orphan" in v]
if hard_violations:
    raise ValueError(
        f"integrate_standard_layer: {len(hard_violations)} hard integrity "
        f"violation(s) detected; refusing to write corrupt Parquet. "
        f"First 3: {hard_violations[:3]}"
    )
```

### loguru structured logging (project-wide)
**Source:** every `src/pipeline/*.py` and `src/scraper/*.py` module
**Apply to:** `src/pipeline/integration.py` (info-level progress per table; warning on schema drift; error on overlap)
**Per MEMORY.md (`scraper-logging-no-per-item.md`):** NEVER log per-item in watched loops (e.g. per-row, per-race). Log per-table or per-partition only. The analog is `normalizer.py:593-596` (one info line per partition written).

```python
# Analog: src/scraper/normalizer.py:593-596
logger.info(
    f"integrate_standard_layer({table!r}): wrote {len(df)} rows -> {path}"
)
```

### pytest hermetic fixtures (tmp_path-derived, no real data/ paths)
**Source:** `tests/scraper/conftest.py:17-47` and `tests/pipeline/conftest.py:291-295`
**Apply to:** `tests/pipeline/test_integration.py` and any new fixtures added to `tests/pipeline/conftest.py`
**Pattern:** every directory fixture derives from pytest's `tmp_path`; the ONE exception in the scraper suite is `golden_html_dir` (repo-relative golden fixtures). Integration tests should follow the same discipline — write synthetic Kaggle + scraped Parquet to `tmp_path`, never touch real `data/standard/`.

```python
# Analog: tests/scraper/conftest.py:29-33
@pytest.fixture
def tmp_standard_dir(tmp_path: Path) -> Path:
    standard_dir = tmp_path / "data" / "standard"
    standard_dir.mkdir(parents=True, exist_ok=True)
    return standard_dir
```

### Physical-type equality via pyarrow.parquet.read_schema
**Source:** `tests/scraper/test_end_to_end.py:449-455` (`_kaggle_schema`) + `:494-536` (`TestSchemaCompatibility`)
**Apply to:** `tests/pipeline/test_integration.py` (success criterion #2 verification)
**Why:** pandas `.dtypes` strings (`Int64Dtype()`) do not round-trip cleanly to Arrow types; Phase 4 P06 discovered this and switched to Arrow introspection. Compare `str(field.type)` tuples in order.

```python
# Analog: tests/scraper/test_end_to_end.py:449-455
import pyarrow.parquet as pq

schema = pq.read_schema(str(path))
types = {f.name: str(f.type) for f in schema}
```

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| (none) | — | — | Every Phase 6 primitive has an exact analog in Phase 2 or Phase 4 code. RESEARCH.md explicitly notes: "Phase 6 introduces no new infrastructure." |

The closest thing to "novel" in this phase is the combination order (reindex → recast → concat → FAIL-LOUD pre-dedup check → atomic write), but each step is a verbatim reuse. Where RESEARCH.md provides reference code (the verified integration recipe at lines 324-376, the TestSchemaCompatibility adaptation at 380-401, the audit_leakage reuse at 404-417), the planner should treat those as the spec and the analogs above as the source of truth for code style/imports/error-handling shape.

## Metadata

**Analog search scope:**
- `/Users/hart/develop/keiba-ai-v2/src/pipeline/` (4 modules: `column_mapping.py`, `kaggle_converter.py`, `validators.py`, `feature_generator.py`)
- `/Users/hart/develop/keiba-ai-v2/src/scraper/` (8 modules; `normalizer.py` is the primary analog)
- `/Users/hart/develop/keiba-ai-v2/src/schemas/` (8 modules; `race.py`, `entry.py`, `result.py`, `audit.py` referenced)
- `/Users/hart/develop/keiba-ai-v2/tests/pipeline/` (conftest.py + 4 test files)
- `/Users/hart/develop/keiba-ai-v2/tests/scraper/` (conftest.py + `test_end_to_end.py` for `TestSchemaCompatibility`)

**Files scanned:** 14 source/test files read in full or in targeted ranges
**Pattern extraction date:** 2026-06-14
