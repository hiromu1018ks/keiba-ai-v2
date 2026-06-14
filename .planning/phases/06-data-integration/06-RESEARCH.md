# Phase 6: Data Integration - Research

**Researched:** 2026-06-14
**Domain:** Data integration / Parquet schema reconciliation / Cross-source deduplication
**Confidence:** HIGH

## Summary

Phase 6 unifies two independently-produced standard-layer corpora — Kaggle (2015-2021, single-file `data/standard/{table}.parquet`) and netkeiba-scraped (2022-2026/5, date-partitioned `data/standard/scraped/{YYYYMM}/{table}.parquet`) — into a single 2015-2026/5 corpus written back to `data/standard/{table}.parquet` for race/entry/result only. The two corpora already share the same column SET (41 race, 16 entry, 12 result columns; both deriving from `RaceSchema`/`EntrySchema`/`ResultSchema`) and the same `race_id` 12-digit format (`YYYYMMDDRRCC`). What they do NOT share is (a) **column order** (Kaggle places flags between `race_condition` and `race_number`; scraped places flags after `start_time`), (b) **physical Arrow type** for 11 columns Kaggle stores as `null` (no data) that scraped stores as concrete `bool`/`string` (e.g. `obstacle`, `surface_detail`, `race_flag_maiden`, `race_flag_open`), and (c) the **`(国際)→race_flag_graded_stakes` mapping** which still exists on the Kaggle side (`src/pipeline/column_mapping.py:68`) but was intentionally removed from the scraper (`src/scraper/flag_crosswalk.py` per Phase 4 P07 UAT-Test-3).

The integration recipe is small and was **verified end-to-end locally** during research: **reindex both DataFrames to canonical schema column order + recast both via `SCHEMA_DTYPE_MAP` (already authoritative in `src/scraper/normalizer.py`) + `pd.concat` + `drop_duplicates(subset=[race_id/horse_race_id], keep="last")` + atomic Parquet write**. With this recipe, mixed `null`-vs-`bool` columns concat cleanly to `bool nullable=True`, FutureWarnings disappear (both sides already typed), and the merged schema is byte-identical across all rows. D-01 and D-02 (CONTEXT.md) are the prerequisites: D-02 regenerates the Kaggle Parquet with the same nullable dtypes the scraper already uses (this is the unification work), and D-01 removes the `(国際)` misclassification from the Kaggle side (510 rows currently misclassified as graded — confirmed by counting `graded_stakes=True ∧ grade ∉ {G1,G2,G3}` in `data/standard/race.parquet`).

**Primary recommendation:** Build a `src/pipeline/integration.py` module with `integrate_standard_layer()` that (1) edits `src/pipeline/column_mapping.py:68` to delete the `(国際)→graded_stakes` line, (2) adds nullable-dtype application to `kaggle_converter.py` mirroring `SCHEMA_DTYPE_MAP`, (3) reads Kaggle + all scraped `{YYYYMM}` partitions, (4) reindex+recast+concat+dedup, (5) writes single-file Parquet for race/entry/result with `compression="snappy"`. Re-run `validators.run_all_validations()` (Phase 2 D-05 8-point) on the integrated corpus and add a Phase-4-style `TestSchemaCompatibility` (physical-type equality on every column) for the integrated output.

**Primary recommendation (one-liner):** Reindex+recast both corpora to the canonical `SCHEMA_DTYPE_MAP` then concat+dedup on `race_id` — verified locally to produce a byte-stable unified Parquet with zero schema divergence.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Schema reconciliation (column order + dtype unification) | API / Backend (`src/pipeline/integration.py`) | Database / Storage (Parquet) | Pure transformation step on file-backed DataFrames; no DB tier in this project |
| Duplicate race detection (Kaggle/scraped overlap) | API / Backend (`integration.py`) | — | Same backend; uses `race_id` PK on concatenated DataFrame |
| Kaggle Parquet regeneration with nullable types | API / Backend (`src/pipeline/kaggle_converter.py`) | Database / Storage | D-02 — re-runs the Phase 2 converter with stricter dtypes |
| `(国際)` mapping removal | API / Backend (`src/pipeline/column_mapping.py:68`) | — | One-line code edit; both sources converge on `GRADE_REGEX`-only detection |
| Volume verification (date range 2015-2026/5) | API / Backend (`validators.py` reuse + new integrated-corp asserts) | — | Phase 2 D-05 8-point + Phase 4 schema-equality pattern reused |
| Output Parquet write | Database / Storage (`data/standard/{race,entry,result}.parquet`) | — | D-03/D-04 — single-file overwrite, table-per-file (Phase 2 D-06) |

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** `(国際)→race_flag_graded_stakes` Kaggle-side mapping **deleted** (`src/pipeline/column_mapping.py:68`). Both sources use `GRADE_REGEX` (GI/GII/GIII/G1/G2/G3/JG*/重賞/full-width ＧＩ etc.) as the sole `race_flag_graded_stakes=True` source. **No schema change needed**. Resolves STATE.md Phase 6 必須調停.
- **D-02:** dtype unification via **Kaggle-side Parquet regeneration**. Re-run Phase 2 converter with nullable types (`Int64`/`Float64`/`boolean`/`datetime`) matching `src/scraper/normalizer.py:SCHEMA_DTYPE_MAP`. **Phase 2 D-05 8-point re-verification runs in Phase 6**. `race_date=datetime`, `distance=Int64`, `race_flag_*=boolean`.
- **D-03:** Unified corpus output: **overwrite `data/standard/{table}.parquet`** (scraped 2022- portions merged in). Phase 3 `feature_generator.py` reads unchanged. `data/standard/scraped/{YYYYMM}/` and `data/raw/kaggle/` retained as traceable sources. **No new `unified/` directory**.
- **D-04:** File granularity: **table-per-file** (`race.parquet`/`entry.parquet`/`result.parquet`, matches Phase 2 D-06). 2015-2026/5 (数十万行) is fine for single files.
- **D-05:** Unified corpus is **`race`/`entry`/`result` only**. `odds_trifecta`/`payoff` excluded from corpus, remain in `data/standard/` (Kaggle 2015-2021 only, NOT overwritten). Phase 8 uses `entry.win_odds` → Harville implied-odds proxy (三連複 corpus not mandatory).
- **D-06:** Full scrape (2022-2026/5, not yet run) executes as a **separate task before Phase 6** (`/gsd-quick` or Phase 4 extension) using `run_scrape(live=True)`. **Phase 6 takes scraped data as input and only does integration logic.**
- **D-07:** Unified corpus covers **all real data (2015-2026/5)**. Extension of ROADMAP success criterion #3 (originally 2015-2024).

### Claude's Discretion
- **Duplicate detection verification logic** — Verify "no duplicate races" by `race_id` dedup. Kaggle (2015-2021) and scraped (2022-) should not overlap by construction, but boundary-year (`race_id` format `YYYYMMDDRRCC`) collision check is required.
- **Unified corpus verification depth** — Which of Phase 2 D-05's 8 checks to re-apply (row counts, schema identity, audit, referential integrity, value ranges) and when to re-run Phase 1 `audit_leakage()` is planner's call.
- **Kaggle converter modification blast radius** — Whether `(国際)` removal + dtype regeneration impacts other flag mappings (FLAG_CROSSWALK 13 flags) or existing Phase 2 tests is research agent's call.
- **Feature regeneration timing** — Whether to regenerate feature layer (Phase 3) on the unified corpus before Phase 7 is planner's call (out of Phase 6 scope by default).

### Deferred Ideas (OUT OF SCOPE)
- **Feature layer regeneration (Phase 3 re-run)** — After Phase 6 completes, regenerate feature layer on unified corpus before Phase 7. Separate task.
- **`odds_trifecta`/`payoff` integration** — When Phase 5 resumes (forward odds collection or paid provider), un-Kaggle top-3 to long format and integrate into `payoff` table (Phase 5 D-04). Currently excluded per D-05.
- **ROADMAP success criterion #3 range update (2015-2024 → 2015-2026/5)** — Adjust ROADMAP text per D-07 at Phase 9 backtest planning time.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DATA-05 | 2015-2024年のデータ（Kaggle + 自前収集）を共通standard形式でParquet出力し、統合して扱えること | This entire phase. D-03 (single-file output, overwritten), D-04 (table-per-file), D-07 (extended to 2015-2026/5). Schema-reconciliation recipe (reindex+recast+concat+dedup) is verified end-to-end locally. Phase 2 D-05 8-point verification reused. Phase 4 `TestSchemaCompatibility` pattern reused for physical-type equality. Output: `data/standard/{race,entry,result}.parquet` covering 2015-2026/5. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | 2.3.3 (installed) | DataFrame concat, reindex, recast, dedup, Parquet I/O | Already the project's tabular engine. Stable 2.3 branch. `[VERIFIED: pip show pandas]` |
| pyarrow | 24.0.0 (installed) | Parquet engine, Arrow schema introspection (`pq.read_schema`) | Required by pandas for Parquet I/O. Used in Phase 4 `TestSchemaCompatibility` for physical-type equality (`str(field.type)`). `[VERIFIED: pip show pyarrow]` |
| numpy | 2.4.6 (installed) | Backing array library for pandas | Transitive dependency; no direct calls needed in Phase 6. `[VERIFIED: pip show numpy]` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic | 2.13.4 (installed) | `RaceSchema`/`EntrySchema`/`ResultSchema` `model_fields` as canonical column-order source | Reindex to `list(Schema.model_fields.keys())` to normalize column order before concat. `[VERIFIED: pip show pydantic]` |
| loguru | 0.7.x | Structured logging (project-wide) | Phase-6 module logging; reuse the existing `loguru` pattern. `[VERIFIED: pyproject.toml]` |
| pytest | 9.0.x | Test framework (project-wide) | Tests for integration correctness. `[VERIFIED: pyproject.toml]` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `pd.concat` + `drop_duplicates` | DuckDB SQL `UNION ALL ... QUALIFY ROW_NUMBER()` | Adds a new runtime dependency; for ~500K rows pandas is plenty fast and the project is pandas-only |
| Parquet single-file overwrite | Partitioned directory by year (`hive` partitioning) | D-04 explicitly keeps table-per-file for Phase 3 read simplicity; ~500K rows fit fine |
| Snappy compression | Zstd | Snappy already used by `kaggle_converter.py` and `normalizer.py`; consistency wins. Zstd ~20% smaller but decompression-slower; not worth the divergence. |

**Installation:**
```bash
# No new packages. All dependencies already in pyproject.toml + installed.
pip show pandas pyarrow numpy pydantic | grep -E '^(Name|Version)'
```

**Version verification (all already installed):**
```bash
$ python3 -c "import pandas, pyarrow, numpy, pydantic; print(f'pandas={pandas.__version__} pyarrow={pyarrow.__version__} numpy={numpy.__version__} pydantic={pydantic.__version__}')"
pandas=2.3.3 pyarrow=24.0.0 numpy=2.4.6 pydantic=2.13.4
```

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| pandas | PyPI | ~17 yrs | ~250M/mo | github.com/pandas-dev/pandas | OK | Approved (already installed) |
| pyarrow | PyPI | ~11 yrs | ~90M/mo | github.com/apache/arrow | OK | Approved (already installed) |
| numpy | PyPI | ~17 yrs | ~500M/mo | github.com/numpy/numpy | OK | Approved (already installed) |
| pydantic | PyPI | ~8 yrs | ~150M/mo | github.com/pydantic/pydantic | OK | Approved (already installed) |
| loguru | PyPI | ~7 yrs | ~30M/mo | github.com/Delgan/loguru | OK | Approved (already installed) |
| pytest | PyPI | ~19 yrs | ~70M/mo | github.com/pytest-dev/pytest | OK | Approved (already installed) |

**Packages removed due to [SLOP] verdict:** none — no new packages are introduced by this phase.

**Packages flagged as suspicious [SUS]:** none.

## Architecture Patterns

### System Architecture Diagram

```
                  +-------------------+              +-------------------------------+
                  |  Kaggle CSVs      |              |  netkeiba live site            |
                  |  data/raw/kaggle/ |              |  (already scraped via Phase 4) |
                  |  race_result.csv  |              +---------------+---------------+
                  |  odds.csv         |                              |
                  +---------+---------+                              |
                            |                                        |
                            v                                        v
            +---------------+----------------+          +-------------+--------------+
            | src/pipeline/kaggle_converter  |          | data/standard/scraped/      |
            |   D-02: regenerate with        |          |   {YYYYMM}/                 |
            |   nullable dtypes              |          |   {race,entry,result}.parq  |
            |   D-01: drop (国際)->graded    |          |   (already typed: SCHEMA_   |
            |     mapping (column_mapping:68)|          |    DTYPE_MAP applied)       |
            +---------------+----------------+          +-------------+----------------+
                            |                                        |
                            v                                        |
              +-------------+----------+                             |
              | data/standard/         |                             |
              |   {race,entry,result}  |                             |
              |   .parquet (regen'd,   |                             |
              |   Kaggle 2015-2021)    |                             |
              +-------------+----------+                             |
                            |                                        |
                            |       +--------------------------------+
                            |       |
                            v       v
                +-----------+-------+--------+
                | src/pipeline/integration.py|  <-- NEW Phase 6 module
                |   1. reindex -> Schema cols|
                |   2. recast -> SCHEMA_     |
                |      DTYPE_MAP             |
                |   3. concat                |
                |   4. drop_duplicates(PK,   |
                |      keep="last")          |
                |   5. atomic Parquet write  |
                +-----------+----------------+
                            |
                            v
                +-----------+----------------+
                | data/standard/             |
                |   {race,entry,result}      |
                |   .parquet                 |
                |   (UNIFIED 2015-2026/5)    |
                +-----------+----------------+
                            |
                            v
                +-----------+----------------+
                | validators.run_all_        |  <-- Phase 2 D-05 reuse
                | validations() +             |
                | TestSchemaCompatibility     |  <-- Phase 4 pattern reuse
                | (physical-type equality)    |
                +----------------------------+
```

Trace the primary use case: input is Kaggle CSVs + scraped Parquet partitions; output is single unified Parquet per table with verified schema equality and zero duplicate `race_id`.

### Recommended Project Structure
```
src/pipeline/
├── integration.py        # NEW: integrate_standard_layer() entry point
├── kaggle_converter.py   # EDITED: D-02 nullable-dtype application; reads SCHEMA_DTYPE_MAP
├── column_mapping.py     # EDITED: D-01 line 68 (国際) entry removed
└── validators.py         # REUSED: run_all_validations() for integrated corpus
tests/pipeline/
├── test_integration.py   # NEW: merge correctness, dedup, schema equality, date-range assertion
└── test_kaggle_converter.py  # EDITED: dtype tests updated for nullable output
```

### Pattern 1: Canonical Column Order via Schema.model_fields
**What:** Both Kaggle and scraped DataFrames are `reindex(columns=list(Schema.model_fields.keys()))` BEFORE concat.
**When to use:** Any time you concat DataFrames produced by different code paths.
**Why:** `pd.concat` preserves column UNION; if orders differ it produces column-name-set union which silently inflates the schema. Reindexing both to the canonical Pydantic `model_fields` order guarantees byte-identical column sets.
**Verified locally:**
```python
from src.schemas.race import RaceSchema
canonical = list(RaceSchema.model_fields.keys())
k_df = pd.read_parquet('data/standard/race.parquet').reindex(columns=canonical)
s_df = pd.read_parquet('data/standard/scraped/202306/race.parquet').reindex(columns=canonical)
assert list(k_df.columns) == list(s_df.columns)  # PASS
```

### Pattern 2: Strict dtype recast via SCHEMA_DTYPE_MAP (Phase 4 reuse)
**What:** After reindex, cast every column through `src/scraper/normalizer.py:SCHEMA_DTYPE_MAP[Schema]` — this is the AUTHORITY that Phase 4 P05/P06/P07 already converged on.
**When to use:** Whenever unifying corpora that may have drifted dtypes.
**Why:** `pd.read_parquet` does not round-trip nullable `Int64`/`Float64`/`boolean` reliably (it downgrades to `int64`/`float64`/`object`). Phase 4 already invented `_recast_for_storage` for this exact case — Phase 6 reuses the same dtype map.
**Example:**
```python
from src.scraper.normalizer import SCHEMA_DTYPE_MAP
from src.schemas.race import RaceSchema

def _recast_to_canonical(df, schema):
    dtype_map = SCHEMA_DTYPE_MAP[schema]
    for col, target in dtype_map.items():
        if col in df.columns:
            df[col] = df[col].astype(target)
    return df
```

### Pattern 3: PK-based dedup with keep="last" (Phase 4 reuse)
**What:** `merged.drop_duplicates(subset=[pk], keep="last")` where `pk` is `race_id` (race) or `horse_race_id` (entry/result).
**When to use:** Concatenating corpora that might overlap on primary key.
**Why:** Phase 4 `write_partitioned_parquet` uses `keep="last"` for same-month re-runs (newer wins). Phase 6 mirrors this on the cross-source merge. If scraped 2022-2026/5 data ever reproduces a Kaggle 2015-2021 race_id, scraped wins (newer, more authoritative for current race conditions). Verified locally: with current data, 0 collisions (Kaggle ends 2021-07-31, scraped starts 2023-06-25).
**Example:**
```python
merged = pd.concat([kaggle_df, scraped_df], ignore_index=True)
deduped = merged.drop_duplicates(subset=["race_id"], keep="last").reset_index(drop=True)
```

### Pattern 4: Atomic Parquet write via temp + os.replace (Phase 4 reuse)
**What:** Write to `{path}.tmp`, then `os.replace(tmp, final)`.
**When to use:** Overwriting `data/standard/{table}.parquet` (D-03 — destructive overwrite).
**Why:** Phase 4 `_atomic_write_parquet` already does this. Failure mid-write does not corrupt the existing file. `engine="pyarrow"`, `compression="snappy"`, `index=False` (same as `kaggle_converter.py`).

### Pattern 5: Physical-type equality assertion (Phase 4 reuse)
**What:** After writing unified Parquet, read its schema with `pyarrow.parquet.read_schema` and compare `str(field.type)` for every column to the authoritative type from `SCHEMA_DTYPE_MAP` (or to the scraped schema).
**When to use:** As the **success criterion #2 verification** ("schema identical across full date range").
**Why:** This is the exact pattern Phase 4 `TestSchemaCompatibility` uses (`tests/scraper/test_end_to_end.py:464`). Phase 6 reuses the technique for the integrated output.

### Anti-Patterns to Avoid
- **Concatenating without reindex first:** `pd.concat` takes the column-union, silently inflating the schema if the two frames have different column orders. Always reindex both to canonical first.
- **Comparing column SET instead of column ORDER+TYPE:** Two DataFrames can have the same column set with different orders and different Arrow types. Success criterion #2 ("schema identical") requires both. Use `pq.read_schema` and compare `(name, str(type))` tuples in order.
- **Adding a `source` column to track origin:** Violates CONTEXT.md D-05 "rows are indistinguishable" (success criterion #2). The integration must be schema-only — no provenance leak. (Phase 6 does NOT add `source`.)
- **Trusting `pd.concat` FutureWarning to be benign:** It is benign today (pandas 2.3 still downcasts empty/all-NA columns correctly) but the warning is real and signals that the dtype contract is unenforced. D-02 (regenerate Kaggle with nullable types) eliminates it.
- **Re-scraping during integration:** Phase 6 is integration-only. Scraping is a separate pre-task (D-06).
- **Writing `unified/` directory:** D-03 explicitly forbids this. Output overwrites `data/standard/{table}.parquet`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Canonical column order | Manual hardcoded column lists | `list(Schema.model_fields.keys())` | Pydantic model is the source of truth; hardcoding drifts from schema edits |
| Nullable dtype map | Re-derive acceptable dtypes per column | `src/scraper/normalizer.py:SCHEMA_DTYPE_MAP` | Phase 4 P05/P06/P07 already converged on this after 3 review cycles; copying the map duplicates authority |
| Duplicate detection | Custom hash-based dedup | `pd.DataFrame.drop_duplicates(subset=[pk], keep="last") | Phase 4 `write_partitioned_parquet` uses the same primitive; Phase 6 mirrors the contract |
| Atomic file write | `try/except` around `to_parquet` | Temp file + `os.replace` (Phase 4 `_atomic_write_parquet`) | `os.replace` is atomic on POSIX/Windows; no half-written files |
| Schema equality assertion | Comparing pandas `.dtypes` strings | `pyarrow.parquet.read_schema` then `str(field.type)` comparison | pandas dtypes (`Int64Dtype()`) do not round-trip to Arrow types cleanly; Phase 4 P06 found this and switched to Arrow introspection |
| Parquet writing | Custom file format | `to_parquet(engine="pyarrow", compression="snappy", index=False)` | Same params as Phase 2/4 outputs — guaranteed byte-compatible downstream readers |

**Key insight:** Phase 6 introduces **no new infrastructure**. Every primitive (typed reindex, strict recast, PK dedup, atomic write, physical-type equality) already exists in Phase 2 or Phase 4 code and is reusable. Phase 6 is a **wiring phase** that combines existing primitives in a new order. This dramatically reduces risk.

## Runtime State Inventory

> This phase **overwrites** `data/standard/{race,entry,result}.parquet` — a destructive operation on persisted runtime state. The Runtime State Inventory is required.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `data/standard/race.parquet` (Kaggle 2015-2021, 21,929 rows) — **will be overwritten** with unified 2015-2026/5 data | Code edit: `integration.py` writes unified corpus; Kaggle-only file is **regenerable** from `data/raw/kaggle/*.csv` + `kaggle_converter.py` (now D-02 updated). **No data migration** — overwrite is destructive but regenerable. |
| Stored data | `data/standard/entry.parquet` (311,806 rows) — **will be overwritten** | Same as race.parquet — regenerable from Kaggle CSV |
| Stored data | `data/standard/result.parquet` (311,806 rows) — **will be overwritten** | Same as race.parquet — regenerable from Kaggle CSV |
| Stored data | `data/standard/odds_trifecta.parquet` (21,929 rows, Kaggle top-3) — **NOT overwritten** (D-05) | None — preserved as Phase 5 resume seed |
| Stored data | `data/standard/payoff.parquet` (21,987 rows, Kaggle partial) — **NOT overwritten** (D-05) | None — preserved |
| Stored data | `data/standard/scraped/{YYYYMM}/*.parquet` (Phase 4 source partitions) — **NOT overwritten** | None — retained as traceable source per D-03 |
| Live service config | None | No external services in this project (no DB, no daemon) |
| OS-registered state | None | No cron jobs, launchd plists, pm2 processes registered |
| Secrets/env vars | None | No SOPS keys, no `.env` references in the integration path |
| Build artifacts | None | No compiled binaries, no egg-info. `pyproject.toml` already declares `pyarrow>=14.0` (satisfied by 24.0.0). |

**Nothing found in category:** Live service config (none — verified by project structure); OS-registered state (none); Secrets/env vars (none); Build artifacts (none). **Verified by inspecting** `pyproject.toml`, project file layout (`src/`, `tests/`, `data/`), and the absence of `Dockerfile`/`docker-compose.yml`/systemd units.

**The canonical question — "After every file in the repo is updated, what runtime systems still have the old string cached, stored, or registered?"** — answer: **nothing outside `data/standard/`**. The destructive overwrites are regenerable from raw sources. Phase 3 (`feature_generator.py`) reads `data/standard/*.parquet` and is the only downstream consumer; it will see the new corpus on next run (out of Phase 6 scope per CONTEXT.md).

## Common Pitfalls

### Pitfall 1: Concat without reindex silently inflates schema
**What goes wrong:** If Kaggle `entry.parquet` has columns in order `[horse_race_id, bracket_num, ..., win_odds, popularity, ..., race_id]` and scraped has `[horse_race_id, race_id, bracket_num, ..., popularity, win_odds]`, a naive `pd.concat` produces the column UNION — which is the same set in this case, but if any column name differs subtly the union grows silently.
**Why it happens:** `pd.concat` aligns on column names, not positions, but does not enforce that both frames have identical column SETS before concat.
**How to avoid:** Always `reindex(columns=list(Schema.model_fields.keys()))` both sides BEFORE concat. This is Pattern 1 above.
**Warning signs:** Post-concat `len(merged.columns) > len(Schema.model_fields)` — a hard assertion should fire.

### Pitfall 2: pandas nullable dtype round-trip via Parquet downgrades types
**What goes wrong:** `pd.read_parquet` of a file written with `Int64` may return `int64` (numpy); `Float64` may return `float64`; `boolean` may return `object` (if all-NA was preserved).
**Why it happens:** pyarrow <-> pandas nullable dtype bridge is not symmetric. Phase 4 P05 discovered this and invented `_recast_for_storage`.
**How to avoid:** Always recast AFTER read and BEFORE concat using `SCHEMA_DTYPE_MAP`. Pattern 2 above.
**Warning signs:** `str(df.dtypes)` showing `int64` instead of `Int64`; `pd.NA` becoming `np.nan` silently.

### Pitfall 3: FutureWarning "concatenation with empty or all-NA entries is deprecated"
**What goes wrong:** When concatenating two frames where one has an all-NA object column (Kaggle's null-typed columns) and the other has a typed column, pandas 2.3 emits a FutureWarning. Today the result is correct (`boolean` dtype, `<NA>` for missing values), but pandas 3.0 changes this behavior.
**Why it happens:** The Kaggle Parquet stores 11 columns as Arrow `null` because Kaggle has no data — pandas reads them as all-NA `object`. Concatenating with scraped `boolean`/`string` triggers the warning.
**How to avoid:** D-02 (regenerate Kaggle Parquet with nullable types) eliminates this entirely — both sides have typed dtypes pre-concat, no all-NA `object` columns.
**Warning signs:** FutureWarning in CI logs after `pd.concat`.
**Verified locally:** With reindex+recast on both sides, the warning disappears (verified during this research).

### Pitfall 4: `(国際)` misclassification scope is larger than expected
**What goes wrong:** Removing `column_mapping.py:68` (D-01) changes the Kaggle `race_flag_graded_stakes=True` count from 1,348 to ~838 (510 rows were misclassified as graded via `(国際)` substring without an actual GI/GII/GIII token).
**Why it happens:** The Kaggle CSV's `レース記号/(国際)` column is set on international-designation races, many of which are Listed/OP-special races that are NOT graded stakes. The original Phase 2 mapping conflated the two concepts.
**How to avoid:** Phase 6 explicitly verifies the post-fix `graded_stakes=True` count drops to ~838 (matches `grade in {G1,G2,G3}` count). This is the verification step.
**Warning signs:** If `graded_stakes=True` count stays at 1,348 after the fix, the mapping removal did not propagate (e.g., `_UNMAPPED_RACE_FLAGS` interaction or stale converter cache).
**Verified locally:** `data/standard/race.parquet` currently has 1,348 `graded_stakes=True`; of those, 510 have `grade NOT IN {G1,G2,G3}` — these are the misclassified rows. After D-01, they should all be `None` or `False`.

### Pitfall 5: Overwriting data/standard/*.parquet destroys the Phase 5 seed
**What goes wrong:** `odds_trifecta.parquet` and `payoff.parquet` are Kaggle 2015-2021 partial data that Phase 5 (DEFERRED) needs as resume seed.
**Why it happens:** `integration.py` could naively loop over all 5 tables and overwrite them.
**How to avoid:** D-05 explicitly excludes `odds_trifecta`/`payoff` from the unified corpus. The integration module MUST only write `race`/`entry`/`result` — hardcode the table allowlist. Do not iterate `TABLE_TO_SCHEMA.keys()` (which includes odds tables).
**Warning signs:** After Phase 6 run, `odds_trifecta.parquet` row count changed.

### Pitfall 6: Boundary-year race_id collision goes undetected
**What goes wrong:** Kaggle ends 2021-07-31; scraped starts 2022+ (currently 2023-06-25 smoke). If a real boundary-overlap exists (e.g., re-scrape accidentally captures a late-2021 race), `pd.concat` produces a duplicate `race_id` row.
**Why it happens:** Date ranges are non-overlapping by design but not enforced by code.
**How to avoid:** After concat, assert `merged["race_id"].duplicated().sum() == 0` BEFORE `drop_duplicates`. If > 0, log the overlapping IDs and FAIL the integration (refuse to silently dedup away the overlap). Pattern 3 + assertion.
**Warning signs:** `race_id.duplicated().sum() > 0` post-concat pre-dedup.

### Pitfall 7: Schema-equality assertion compares the wrong thing
**What goes wrong:** Comparing `df.dtypes` strings (`Int64Dtype()`) across the two corpora fails because pandas stringifies nullable dtypes inconsistently.
**Why it happens:** `str(df.dtypes)` produces different output depending on pandas version and column state.
**How to avoid:** Use `pyarrow.parquet.read_schema(path)` and compare `str(field.type)` tuples in order. This is the Phase 4 P06 invention. Pattern 5.

## Code Examples

### Verified end-to-end integration recipe (run locally during research)
```python
# Source: this research session — executed against actual project Parquet files
import pandas as pd
import warnings
from src.schemas.race import RaceSchema
from src.schemas.entry import EntrySchema
from src.schemas.result import ResultSchema
from src.scraper.normalizer import SCHEMA_DTYPE_MAP
from pathlib import Path
import pyarrow.parquet as pq

SCHEMA_BY_TABLE = {
    "race": RaceSchema,
    "entry": EntrySchema,
    "result": ResultSchema,
}
PK_BY_TABLE = {"race": "race_id", "entry": "horse_race_id", "result": "horse_race_id"}

def integrate_table(table: str, standard_dir: Path = Path("data/standard")) -> pd.DataFrame:
    schema = SCHEMA_BY_TABLE[table]
    pk = PK_BY_TABLE[table]
    canonical_cols = list(schema.model_fields.keys())
    dtype_map = SCHEMA_DTYPE_MAP[schema]

    # 1. Read Kaggle (post D-02: will already be nullable-typed)
    kaggle_path = standard_dir / f"{table}.parquet"
    kaggle_df = pd.read_parquet(kaggle_path).reindex(columns=canonical_cols)

    # 2. Read ALL scraped partitions
    scraped_root = standard_dir / "scraped"
    scraped_dfs = []
    for month_dir in sorted(scraped_root.glob("*")):
        path = month_dir / f"{table}.parquet"
        if path.exists():
            scraped_dfs.append(pd.read_parquet(path).reindex(columns=canonical_cols))
    scraped_df = pd.concat(scraped_dfs, ignore_index=True) if scraped_dfs else pd.DataFrame(columns=canonical_cols)

    # 3. Recast both via SCHEMA_DTYPE_MAP
    for df in (kaggle_df, scraped_df):
        for col, target in dtype_map.items():
            if col in df.columns:
                df[col] = df[col].astype(target)

    # 4. Concat + dedup
    merged = pd.concat([kaggle_df, scraped_df], ignore_index=True)
    dup_count = int(merged[pk].duplicated().sum())
    if dup_count > 0:
        # FAIL LOUD — overlap is unexpected; investigate before silently dedup'ing
        raise ValueError(f"{table}: {dup_count} duplicate {pk} values post-concat — investigate overlap")
    return merged

# Verified output: race 21,934 rows (Kaggle 21,929 + scraped 5), no duplicates
```

### Phase 4 TestSchemaCompatibility pattern (reuse for Phase 6)
```python
# Source: tests/scraper/test_end_to_end.py:464 (Phase 4 P06) — adapted for Phase 6
import pyarrow.parquet as pq
from src.schemas.race import RaceSchema

def test_unified_corpus_schema_invariant():
    """After Phase 6 integration, every column in race.parquet has the SAME
    Arrow physical type as defined by SCHEMA_DTYPE_MAP. This is success
    criterion #2 (rows indistinguishable across date range)."""
    schema = pq.read_schema("data/standard/race.parquet")
    # Authoritative expected types from SCHEMA_DTYPE_MAP
    expected = {
        "race_id": "string", "race_date": "string", "meeting_num": "int64",
        # ... (all 41 columns from SCHEMA_DTYPE_MAP[RaceSchema])
    }
    mismatches = []
    for f in schema:
        actual = str(f.type)
        exp = expected.get(f.name)
        if exp and actual != exp:
            mismatches.append(f"{f.name}: got {actual!r}, want {exp!r}")
    assert not mismatches, f"Schema divergence: {mismatches}"
```

### Phase 1 audit_leakage reuse for integrated corpus
```python
# Source: src/schemas/audit.py — reused verbatim
from src.schemas.audit import audit_leakage
from src.schemas.race import RaceSchema
from src.schemas.entry import EntrySchema
import pandas as pd

race_df = pd.read_parquet("data/standard/race.parquet")
entry_df = pd.read_parquet("data/standard/entry.parquet")

# Verify post-race columns did not leak into pre-race tables during integration
assert audit_leakage([RaceSchema], race_df, "post-integration race audit") == []
assert audit_leakage([EntrySchema], entry_df, "post-integration entry audit") == []
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Per-table Parquet with nullable `object` for missing flags (Phase 2) | Per-table Parquet with explicit `boolean` for all 20 flags (Phase 4) | Phase 4 P05 (Cycle-2 #3) | Phase 6 must bring Kaggle side up to Phase 4 dtype discipline |
| `errors="ignore"` in dtype coercion (early Phase 2 sketch) | Strict coercion that raises `TypeError` (Phase 4 P05 `_build_typed_dataframe`) | Phase 4 P05 | Phase 6 Kaggle regen MUST follow the strict path, not re-introduce `errors="ignore"` |
| `(国際)→graded_stakes` substring mapping | `GRADE_REGEX` (GI/GII/GIII/重賞/full-width) only | Phase 4 P07 (UAT-Test-3) | Phase 6 must propagate this fix to the Kaggle side (D-01) |
| Separate `data/standard/*.parquet` (Kaggle) and `data/standard/scraped/{YYYYMM}/*.parquet` (scraped) | Single unified `data/standard/*.parquet` covering 2015-2026/5 (Phase 6 D-03) | This phase | Phase 3 reads unchanged; `scraped/` retained as source |

**Deprecated/outdated:**
- `(国際)→graded_stakes` Kaggle mapping (`column_mapping.py:68`): semantic error, removed by D-01.
- `errors="ignore"` dtype coercion pattern: not in current codebase but research warns against re-introducing.

## Assumptions Log

> All claims in this research were verified against the codebase, Parquet files, or executed locally during this session. The only assumptions are scope/timing.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Full scrape (2022-2026/5) will produce scraped Parquet under `data/standard/scraped/{YYYYMM}/` using the existing Phase 4 pipeline; integration logic is the same regardless of scraped volume | Architectural Responsibility Map, Code Examples | LOW — Phase 4 P06 live-verified the pipeline shape; only volume differs. If scrape produces data outside `scraped/{YYYYMM}/`, `glob("*")` in integration needs adjustment. |
| A2 | The full scrape will not produce `race_id` collisions with Kaggle (2015-2021) by construction | Common Pitfalls #6 | LOW — `race_id` is `YYYYMMDDRRCC`; date ranges are non-overlapping (Kaggle ≤ 2021-07-31, scraped ≥ 2022-01-01). A duplicate would indicate a parser bug surfacing a Kaggle-era race as scraped-era. |
| A3 | Phase 3 `feature_generator.py` is the only downstream consumer of `data/standard/{race,entry,result}.parquet` | Runtime State Inventory | LOW — verified by `grep -rn "data/standard" src/` during research. The Phase 6 overwrite will not affect any other module. |
| A4 | ROADMAP success criterion #3 expansion to 2015-2026/5 is acceptable (D-07); no ROADMAP text update needed in Phase 6 | User Constraints | LOW — D-07 explicitly defers ROADMAP text update to Phase 9 planning. |

**If this table is empty:** N/A — 4 assumed claims documented. All LOW risk; planner should confirm A1/A2 with a quick scrape-volume sanity check before Phase 6 execution (the pre-task in D-06 handles this).

## Open Questions

1. **Does the full scrape produce all months 2022-01 through 2026-05, or are there gaps?**
   - What we know: Phase 4 enumerated via `/race/list/{YYYYMM}/` and is designed for the full range. Smoke run produced only 202306 (5 races).
   - What's unclear: Whether the actual full run covers every month cleanly or has gaps (e.g., holiday months, network errors).
   - Recommendation: D-06 pre-task should run the full scrape with `tqdm` (already integrated) and log a per-month coverage report. Phase 6 integration should assert every expected `{YYYYMM}/` directory exists before merge — but tolerate missing months (just log a warning, since JRA does have off months).

2. **Should `audit_leakage()` run on the integrated race/entry tables?**
   - What we know: Phase 2 ran it on Kaggle-only output. Phase 4 P05 Cycle-1 MEDIUM intentionally skipped it for scraped (because `popularity`/`win_odds` are intentionally in entry per D-03).
   - What's unclear: Phase 6 CONTEXT.md (Claude's Discretion) leaves the timing open.
   - Recommendation: Run it for race table (should always return `[]` — race is pre-race only). For entry table, expect `['popularity', 'win_odds']` in the leaked list (these are correctly post-race per Phase 1 D-03); assert that and only that, no other leaks.

3. **Does D-02 (Kaggle regen with nullable types) need a new converter flag, or edit the existing converter?**
   - What we know: `kaggle_converter.py` currently writes whatever dtype pandas infers after the column-mapping transform. Phase 4 invented `SCHEMA_DTYPE_MAP` separately.
   - What's unclear: Whether to add a `_recast_to_canonical(df, schema)` call at the end of `split_race_entry_result`, or add it to `convert()` before write.
   - Recommendation: Add it at the end of `split_race_entry_result` (per-table, before returning) — this is the natural chokepoint where each DataFrame has its final shape. Reuse the `_recast_to_canonical` helper shown in Pattern 2.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | All code | ✓ | 3.12+ | — |
| pandas | DataFrame ops, Parquet I/O | ✓ | 2.3.3 | — |
| pyarrow | Parquet engine + schema introspection | ✓ | 24.0.0 | — |
| numpy | Backing arrays (via pandas) | ✓ | 2.4.6 | — |
| pydantic | Schema model_fields for column order | ✓ | 2.13.4 | — |
| pytest | Tests | ✓ | 9.0.x | — |
| Kaggle CSVs (`data/raw/kaggle/*.csv`) | D-02 Kaggle regen input | ✓ | 19860105-20210731 | — |
| Kaggle Parquet (`data/standard/*.parquet`) | Integration input (post-D-02 regen) | ✓ | 21,929 / 311,806 rows | — |
| Scraped Parquet (`data/standard/scraped/{YYYYMM}/`) | Integration input | ⚠ SMOKE ONLY (202306, 5 races) | — | **D-06 pre-task: full scrape** |
| LightGBM | NOT used in Phase 6 | n/a | — | — |
| playwright | NOT used in Phase 6 (D-06 pre-task only) | ✓ | 1.60.0 | — |

**Missing dependencies with no fallback:**
- **Full scraped corpus (2022-2026/5)** — currently only smoke 5 races. **D-06 pre-task MUST complete before Phase 6 plan/execute starts.** Without it, success criteria #1 (no duplicates between Kaggle and scraped) and #3 (date coverage 2015-2026/5) cannot be verified.

**Missing dependencies with fallback:**
- None.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.x (already configured) |
| Config file | `pyproject.toml [tool.pytest.ini_options]` — `testpaths=["tests"]` |
| Quick run command | `python -m pytest tests/pipeline/test_integration.py -x -q` |
| Full suite command | `python -m pytest tests/ -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-05 (coverage) | Unified `race.parquet` covers 2015-01-01 through 2026-05-31 | integration | `python -m pytest tests/pipeline/test_integration.py::test_unified_race_date_range -x` | ❌ Wave 0 |
| DATA-05 (no dups) | No duplicate `race_id` between Kaggle and scraped post-concat (pre-dedup assertion fires if any) | unit | `python -m pytest tests/pipeline/test_integration.py::test_no_duplicate_race_ids -x` | ❌ Wave 0 |
| DATA-05 (schema identical) | Every column in unified `race.parquet` has identical Arrow physical type across the corpus (success criterion #2) | integration | `python -m pytest tests/pipeline/test_integration.py::test_schema_invariant_post_integration -x` | ❌ Wave 0 |
| DATA-05 (volume) | Row counts: race ~21,929+scraped_races, entry ~311,806+scraped_entries, result ~311,806+scraped_results | integration | `python -m pytest tests/pipeline/test_integration.py::test_row_counts_within_expected_bounds -x` | ❌ Wave 0 |
| DATA-05 (FK integrity) | Every `entry.race_id` and `result.race_id` exists in `race.race_id` | integration | `python -m pytest tests/pipeline/test_integration.py::test_referential_integrity -x` | ❌ Wave 0 |
| DATA-05 (audit) | `audit_leakage()` on unified race table returns `[]`; on entry table returns exactly `{popularity, win_odds}` | integration | `python -m pytest tests/pipeline/test_integration.py::test_no_post_race_leakage -x` | ❌ Wave 0 |
| DATA-05 (D-01 fix) | After Kaggle regen with D-01 fix, `race_flag_graded_stakes=True` count drops from 1,348 to ~838 | unit | `python -m pytest tests/pipeline/test_integration.py::test_graded_stakes_count_post_d01_fix -x` | ❌ Wave 0 |
| DATA-05 (D-02 dtypes) | Kaggle Parquet after D-02 regen has all 20 `race_flag_*` as Arrow `bool` (not `null`) | unit | `python -m pytest tests/pipeline/test_integration.py::test_kaggle_parquet_post_d02_has_typed_flags -x` | ❌ Wave 0 |
| DATA-05 (odds preserved) | `odds_trifecta.parquet` and `payoff.parquet` are NOT modified by Phase 6 (D-05 exclusion) | integration | `python -m pytest tests/pipeline/test_integration.py::test_odds_payoff_not_overwritten -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/pipeline/test_integration.py -x -q` (~5s)
- **Per wave merge:** `python -m pytest tests/ -q` (~30s, all existing tests must still pass)
- **Phase gate:** Full suite green + manual inspection of `data/standard/race.parquet` row count + date range + schema before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/pipeline/test_integration.py` — covers DATA-05 (9 tests above)
- [ ] `src/pipeline/integration.py` — new module with `integrate_standard_layer()` entry point
- [ ] No new conftest fixtures needed — `tests/pipeline/conftest.py` already has `tmp_standard_dir` and `sample_race_result_df`. May need a `tmp_kaggle_raw_dir` and `tmp_scraped_partitions_dir` for integration tests.
- [ ] Framework install: none (pytest already installed)

*(Framework already configured; only new test files needed.)*

## Security Domain

> `security_enforcement` is enabled in `.planning/config.json` (level 1). Phase 6 is a pure data-pipeline phase with no network, no auth, no user input. ASVS categories mostly N/A; only V5 (input validation) and V6 (cryptography — N/A) might nominally apply.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No authentication in this phase |
| V3 Session Management | no | No sessions |
| V4 Access Control | no | No access control decisions |
| V5 Input Validation | yes | Pydantic schemas (`RaceSchema`/`EntrySchema`/`ResultSchema`) define the canonical column contract. Integration MUST reindex to `Schema.model_fields` — any column outside the schema is dropped (input validation at the schema layer). |
| V6 Cryptography | no | No cryptographic operations |
| V7 Errors & Logging | yes | loguru structured logging; integrity violations (duplicate PKs, FK orphans) RAISE per Phase 4 P05 WR-07 pattern (no silent corruption) |
| V8 Data Protection | yes | Atomic Parquet write (temp + `os.replace`) prevents half-written/corrupt files during the destructive overwrite of `data/standard/*.parquet` (D-03). |

### Known Threat Patterns for Python data pipeline

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Silent schema drift between corpora | Tampering | Pattern 5 (physical-type equality assertion via `pq.read_schema`); Phase 4 P06 `TestSchemaCompatibility` reuse |
| Duplicate race_id collision masking data loss | Tampering | Pattern 3 + Pitfall 6 (FAIL LOUD on pre-dedup duplicates) |
| Half-written Parquet from interrupted overwrite | Denial of Service | Pattern 4 (atomic write via `os.replace`) |
| Provenance leak via `source` column | Information Disclosure | Pitfall "Adding source column" — D-05 forbids; rows MUST be indistinguishable |
| Misclassification via loose substring match | Tampering | D-01 (`(国際)` removal); GRADE_REGEX strict match only |

## Sources

### Primary (HIGH confidence)
- Local execution: `python3` introspection of `data/standard/{race,entry,result}.parquet` and `data/standard/scraped/202306/*.parquet` via `pyarrow.parquet.read_schema` — physical-type comparison, row counts, date ranges, duplicate-detection simulation. **All verified in this session.**
- `src/scraper/normalizer.py` — authoritative `SCHEMA_DTYPE_MAP`, `_build_typed_dataframe`, `write_partitioned_parquet`, `_recast_for_storage`, `_atomic_write_parquet`. Phase 4 P05/P06/P07 converged code.
- `src/pipeline/column_mapping.py` — `KAGGLE_COLUMN_MAP`, `FLAG_CROSSWALK`, `DTYPE_SPEC`. Line 68 confirmed to contain `(国際)→race_flag_graded_stakes`.
- `src/pipeline/kaggle_converter.py` — Phase 2 converter, the D-02 modification target.
- `src/pipeline/validators.py` — Phase 2 D-05 8-point verification functions.
- `src/schemas/{race,entry,result,audit}.py` — Phase 1 contract definitions.
- `tests/scraper/test_end_to_end.py:464` — Phase 4 `TestSchemaCompatibility` pattern (the schema-equality test technique).
- `pyproject.toml` — installed package versions.

### Secondary (MEDIUM confidence)
- `.planning/phases/02-kaggle-data-pipeline/02-CONTEXT.md` — Phase 2 D-05 8-point verification definition (the reused validation protocol).
- `.planning/phases/04-scraping-infrastructure-race-data/04-CONTEXT.md` and `04-VERIFICATION.md` — Phase 4 P05/P06/P07 decisions, UAT-Test-3 `(国際)` finding.
- `.planning/phases/05-trifecta-odds-scraping/05-CONTEXT.md` — Phase 5 DEFERRED reasoning (D-05 odds-exclusion rationale).
- `.planning/STATE.md` — Blockers/Concerns (Phase 6 必須調停事項).

### Tertiary (LOW confidence)
- None. All claims verified against codebase or executed locally.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages already installed and verified; no new dependencies.
- Architecture: HIGH — integration recipe executed end-to-end locally against real project Parquet files; patterns reused verbatim from Phase 2/4.
- Pitfalls: HIGH — 7 pitfalls identified; 5 verified empirically (FutureWarning behavior, concat-without-reindex, dtype round-trip, `(国際)` count, odds-preservation risk).
- Validation: HIGH — test map derived from success criteria + DATA-05; all 9 tests are mechanically derivable.

**Research date:** 2026-06-14
**Valid until:** 2026-07-14 (30 days) — stable; no external dependencies that drift. The D-06 pre-task (full scrape) outcome may affect A1/A2 assumptions but not the integration recipe.
