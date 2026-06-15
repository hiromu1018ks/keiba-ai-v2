---
phase: 06-data-integration
reviewed: 2026-06-15T00:00:00Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - src/pipeline/column_mapping.py
  - src/pipeline/integration.py
  - src/pipeline/kaggle_converter.py
  - src/pipeline/validators.py
  - tests/pipeline/conftest.py
  - tests/pipeline/test_column_mapping.py
  - tests/pipeline/test_integration.py
  - tests/pipeline/test_kaggle_converter.py
  - tests/pipeline/test_validators.py
findings:
  critical: 4
  warning: 9
  info: 6
  total: 19
status: issues_found
---

# Phase 06: Code Review Report

**Reviewed:** 2026-06-15
**Depth:** standard
**Files Reviewed:** 9 (4 source, 5 test)
**Status:** issues_found

## Summary

Phase 6 adds the Kaggle+scraped corpus integrator (`integration.py`), the D-01 graded-flag regex re-derivation in `kaggle_converter.py`, the D-02 nullable-dtype regen path, and the Rule-1 validator fix in `validators.py`. The transactional design of `integrate_standard_layer` (idempotent transform + separate Kaggle input path + dedicated `_commit_staging` boundary + extended hard-violation filter) is well-motivated and the cycle-5 isolated tests are genuine regression guards, not vacuous assertions.

However, four BLOCKER-tier defects remain:

1. **`_DTYPE_COMPAT['bool']` accepts `"object"` unconditionally** (`validators.py:36`), so any `race_flag_*` or `Optional[bool]` field stored as `object` with arbitrary string/numeric content passes schema conformance. This is the inverse of a validator — it silently endorses corruption.
2. **`validate_sample_rows` has three silent-True escape paths** (`validators.py:525-549`) that report "PASS" when the check was never performed (empty Parquet, missing key, no comparable columns). A real data-integrity regression can hide behind `overall_pass=True`.
3. **`audit_pass` is hardcoded to `True`** (`validators.py:852`) in `run_all_validations`, so post-race column leakage in the standard layer cannot fail the aggregate — contradicting the contract advertised in the module docstring (8 checks).
4. **Stale, contradicting docstring in `flag_crosswalk.py:30-46`** that claims `column_mapping.py line 68 still maps レース記号/(国際) -> race_flag_graded_stakes` and that "that file is out of scope for this gap fix" — directly false after the D-01 removal. Future maintainers will re-introduce the bug.

Additional Warnings cover: `_atomic_write_parquet` imported from outside `__all__` (private-API contract leak), the over-broad Rule-1 `'float' in actual_dtype.lower()` shortcut (accepts `distance=2000.5`), duplicate `_recast_to_canonical` definitions with divergent mutation semantics, the unguarded `df['障害区分'] != '障害'` filter (NaN-safe only because Kaggle CSV stores `""` not NaN), and a few smaller robustness gaps.

テスト自体は網羅的で cycle-5 の isolation は本物だが、validator 系に「チェックしないのに PASS を返す」経路が複数あり、統合後 corpus の品質保証が抜け落ちるリスクがある。フラグ系 bool dtype と audit_pass の hardcode は出荷前に必須修正。

## Critical Issues

### CR-01: `_DTYPE_COMPAT['bool']` accepts `object` dtype unconditionally — schema conformance cannot catch corrupted bool columns

**File:** `src/pipeline/validators.py:36`
**Issue:**
```python
_DTYPE_COMPAT: dict[str, set[str]] = {
    ...
    "bool": {"bool", "boolean", "object"},  # object for nullable bool (True/None)
}
```
The `"object"` entry was added to tolerate nullable booleans stored as object after a Parquet round-trip. But this short-circuits BEFORE all the downstream guards: when `actual_dtype in compatible_dtypes` is `True`, the entire `if actual_dtype not in compatible_dtypes:` block is skipped. A `race_flag_handicap` column with `dtype=object` and content `["yes", "5", pd.NA, "false"]` — i.e. arbitrary strings/ints that are NOT bools — passes `validate_schema_conformance` silently. This is the opposite of a validator.

The nullable `boolean` (capital B) pandas dtype is already in the set and is the correct nullable-bool storage. `object` was added as a fallback but the fallback is unsound: it accepts ANY object content, not just `True/None` triples.

Repro:
```python
import pandas as pd
df = pd.DataFrame({"race_flag_handicap": pd.array(["yes", None, 5], dtype=object)})
# str(df['race_flag_handicap'].dtype) == 'object'
# 'object' in _DTYPE_COMPAT['bool'] -> True -> check passes
```

**Fix:**
Remove `"object"` from `_DTYPE_COMPAT['bool']`. If nullable-bool-round-tripped-to-object is a genuine Parquet artifact (it is not, per `normalizer.py:SCHEMA_DTYPE_MAP` which uses `"boolean"`), handle it explicitly with a content sanity check:
```python
"bool": {"bool", "boolean"},  # nullable bool serializes to Arrow bool, not object
```
If object-round-trip is observed in practice, add a dedicated guard:
```python
if expected_cat == "bool" and actual_dtype == "object":
    sample = df[field_name].dropna()
    if not sample.empty and not sample.isin([True, False]).all():
        errors.append(
            f"Dtype mismatch for {field_name}: object dtype contains "
            f"non-bool values: {sample.unique()[:5].tolist()}"
        )
    continue
```

### CR-02: `validate_sample_rows` reports PASS for tables it could not check (three silent-True paths)

**File:** `src/pipeline/validators.py:525-530, 547-549, 559-566`
**Issue:**
Three branches in `validate_sample_rows` set `results[table_name] = True` and `continue` when the check is genuinely impossible to perform:

- Line 525-527: empty Parquet (`len(pq_df) == 0`) → `True`
- Line 547-549: csv_key not in source columns → `True`
- Line 559-566: no comparable columns → `True`

In `run_all_validations` line 848, `sample_pass = all(sample_result.values())`. These silent `True` values mean the aggregate `overall_pass` reports success even when zero rows were actually sampled and verified. A regression that empties a table or drops the key column produces `overall_pass=True`.

The line 525-527 case is especially insidious: a corrupt convert/integration run that produced a 0-row Parquet (the very scenario `integration.py:380-384` raises about) would be hidden by this validator.

**Fix:**
Distinguish "not checked" from "passed". Either skip the table (do not add to results) or use `None` / a sentinel and adjust the aggregator:
```python
# Option A: skip (omit from results); aggregator uses only tables actually checked.
if len(pq_df) == 0:
    logger.warning(f"sample_rows: {table_name} Parquet is empty -- not checked")
    continue  # do NOT set True
...
if csv_key not in source_df.columns:
    logger.warning(f"sample_rows: {table_name} key {csv_key} missing from source -- not checked")
    continue
...
if not comparable_cols:
    logger.debug(f"sample_rows: {table_name} no comparable columns -- not checked")
    continue
```
Then update `run_all_validations`:
```python
sample_pass = all(sample_result.values()) if sample_result else True
# sample_result is empty dict {} (not {table: True}) when nothing was checked.
```
If "table present but unchecked" must fail loud, set `False` instead and document the contract.

### CR-03: `audit_pass` hardcoded to `True` in `run_all_validations` — leakage audit can never fail the aggregate

**File:** `src/pipeline/validators.py:850-852`
**Issue:**
```python
# Audit: expected behavior -- race should have no leaks, but entry/result/odds/payoff
# are expected to have post-race columns, so we don't fail on those
audit_pass = True  # Audit is informational, not a pass/fail check
```
The module docstring at line 6 advertises "8 validation checks" with `audit_leakage` as check 3. The `result["audit"]` key in the return dict is set to `audit_pass` (always `True`), so callers reading `result["overall_pass"]` cannot detect leakage. The race table specifically is contractually pre-race-only (per `schemas/race.py` and `integration.py:341-348` which RAISES on race leakage) — yet `validate_audit` will not flag it in the aggregate.

The integration module enforces this correctly at write time (it raises), but `run_all_validations` is the post-hoc validator and is supposed to be the independent guard. If a future refactor moves data into `data/standard/race.parquet` outside the integration path, this validator will silently bless the leak.

**Fix:**
Make audit pass conditional on the race table specifically (race must have zero leaks; entry may leak the documented `{popularity, win_odds}` set; result/odds/payoff are post-race by design):
```python
audit_pass = True
if "race" in audit_result:
    race_leaks = audit_result["race"]
    # Filter out non-leak sentinel "Missing: ..." entries or treat them as failures.
    real_race_leaks = [c for c in race_leaks if not c.startswith("Missing:")]
    audit_pass = audit_pass and (len(real_race_leaks) == 0)
if "entry" in audit_result:
    unexpected = set(audit_result["entry"]) - {"popularity", "win_odds"}
    audit_pass = audit_pass and (len(unexpected) == 0)
```
Update the docstring to match (the current comment "Audit is informational, not a pass/fail check" contradicts the docstring's list of 8 checks).

### CR-04: Stale docstring in `flag_crosswalk.py:30-46` contradicts the D-01 fix and will mislead future maintainers

**File:** `src/scraper/flag_crosswalk.py:30-46`
**Issue:**
The module docstring contains an extended "Phase 6 reconciliation note" that says:

> "The Kaggle-side `src/pipeline/column_mapping.py` line 68 still maps `レース記号/(国際)` -> `race_flag_graded_stakes`; that file is out of scope for this gap fix (it is a Kaggle-pipeline file). Phase 6 (Data Integration) MUST reconcile this divergence before joining the two sources: either remove the Kaggle-side mapping too, or introduce a new `race_flag_international` column on both sides. Until Phase 6 ships, scraped 2022-2024 rows with `(国際)` but no GI token will have `race_flag_graded_stakes=None` while equivalent 2015-2021 Kaggle rows have `True` — a known, documented, bounded inconsistency."

This is now FALSE. Phase 6 D-01 DID remove the Kaggle-side mapping (`column_mapping.py:68-73` has only the explanatory comment, no map entry for `(国際)`; `KAGGLE_COLUMN_MAP` has 65 entries, not 66, per `test_kaggle_column_map_has_65_entries`). A maintainer reading this docstring will either (a) re-add the mapping to "complete" what they think is unfinished work, re-introducing UAT-Test-3, or (b) add a `race_flag_international` column that nobody else expects. Either path re-opens the major-severity bug D-01 closed.

**Fix:**
Replace the stale reconciliation note with a one-line "Phase 6 D-01 closed this gap" pointer:
```python
Phase 6 reconciliation note on ``(国際)`` and ``race_flag_graded_stakes``:
``(国際)`` is an INTERNATIONAL-designation marker, NOT a graded-stakes
marker. Phase 6 D-01 REMOVED the corresponding Kaggle-side mapping in
``src/pipeline/column_mapping.py`` (the (国際) CSV column is still listed in
FLAG_COLUMNS but no longer in KAGGLE_COLUMN_MAP); graded detection on both
sides now comes from ``_GRADE_REGEX`` via ``derive_race_flags`` /
``kaggle_converter._apply_grade_detection``. Do NOT re-introduce a
``(国際) -> race_flag_graded_stakes`` mapping on either side.
```

## Warnings

### WR-01: `_atomic_write_parquet` imported from outside `normalizer.__all__` — private-API contract leak

**File:** `src/pipeline/integration.py:70-74`, `src/pipeline/kaggle_converter.py:31`
**Issue:**
Both `integration.py` and `kaggle_converter.py` import `_atomic_write_parquet` from `src.scraper.normalizer`, but `normalizer.py:792-798` explicitly defines `__all__` WITHOUT `_atomic_write_parquet`:
```python
__all__ = [
    "normalize_to_parquet",
    "validate_integrity",
    "write_partitioned_parquet",
    "_build_typed_dataframe",
    "SCHEMA_DTYPE_MAP",
]
```
The leading underscore signals "module-private", yet the function is now a load-bearing cross-module dependency of two production modules. If a future refactor renames or removes it, only a grep (not `__all__`) catches the breakage, and `from src.scraper.normalizer import *` would silently drop it.

**Fix:**
Either (a) promote it to the public surface by adding it to `__all__` and renaming to `atomic_write_parquet` (drop the underscore), or (b) extract it into a shared utility module (`src/pipeline/io_utils.py` or similar) that both consumers import explicitly. Option (a) is the smaller diff:
```python
# src/scraper/normalizer.py
def atomic_write_parquet(df: pd.DataFrame, path: Path) -> None:
    ...

__all__ = [
    "normalize_to_parquet",
    "validate_integrity",
    "write_partitioned_parquet",
    "_build_typed_dataframe",
    "atomic_write_parquet",   # was _atomic_write_parquet
    "SCHEMA_DTYPE_MAP",
]
```

### WR-02: Rule-1 fix is over-broad — `'float' in actual_dtype.lower()` accepts ANY int field stored as float with decimal content

**File:** `src/pipeline/validators.py:172-174`
**Issue:**
```python
if expected_cat == "int" and "float" in actual_dtype.lower():
    # Nullable Int64 columns can become float64 when all NaN
    continue
```
The comment justifies this as accepting "Nullable Int64 columns can become float64 when all NaN" — but the actual predicate accepts `float64`/`Float32`/`Float64` for ANY int field regardless of content. A `distance` column corrupted to `float64` with values like `[2000.5, 1600.25]` passes schema conformance silently. The legitimate case (`SCHEMA_DTYPE_MAP` deliberately uses `Float64` for `corner_1..4`, `horse_weight`, `weight_change`, `popularity` per `normalizer.py:155-167`) is real, but the shortcut conflates "nullable-int-stored-as-float-by-design" with "int-field-corrupted-to-float".

**Fix:**
Constrain the shortcut to the fields that the dtype map actually stores as Float64-by-design, OR check that the float values are integer-valued:
```python
if expected_cat == "int" and "float" in actual_dtype.lower():
    series = df[field_name].dropna()
    if series.empty or (series % 1 == 0).all():
        continue
    # Float column with non-integer values for an int schema field — real mismatch.
    errors.append(
        f"Dtype/value mismatch for {field_name}: stored as {actual_dtype} "
        f"with non-integer values (e.g. {series.head(3).tolist()})"
    )
    continue
```

### WR-03: Duplicate `_recast_to_canonical` definitions with divergent mutation semantics

**File:** `src/pipeline/kaggle_converter.py:142-167` vs `src/pipeline/integration.py:102-124`
**Issue:**
Both modules define a function with the identical name `_recast_to_canonical` and nearly identical docstrings ("Phase 6 D-02: the Kaggle-side Parquet must match the scraped-side dtype contract..."). The semantics diverge:

- `kaggle_converter.py:160` mutates the input DataFrame in place (`df[col] = df[col].astype(target)` with no copy).
- `integration.py:113-118` returns a copy (`out = df.copy()`) — does NOT mutate the caller's frame.

The divergence is load-bearing: `integration.py:283-284` calls `_recast_to_canonical` on `kaggle_df` / `scraped_df` and the callers rely on the original frames being preserved for the audit call later. The `kaggle_converter.py` version is called on DataFrames that are about to be written, so in-place mutation is harmless there — but the inconsistency is a latent footgun for future maintainers who copy one implementation expecting the other's behavior.

**Fix:**
Extract a single implementation into `src/pipeline/io_utils.py` (or `src/scraper/normalizer.py` next to `SCHEMA_DTYPE_MAP`) and import from both:
```python
# src/pipeline/io_utils.py
def recast_to_canonical(df: pd.DataFrame, schema: type[BaseModel]) -> pd.DataFrame:
    """Recast df to SCHEMA_DTYPE_MAP[schema] with strict coercion. Returns a copy."""
    dtype_map = SCHEMA_DTYPE_MAP[schema]
    out = df.copy()
    for col, target in dtype_map.items():
        if col not in out.columns:
            continue
        try:
            out[col] = out[col].astype(target)
        except (TypeError, ValueError) as e:
            raise TypeError(
                f"recast_to_canonical: column {col!r} could not be coerced "
                f"to {target!r} for {schema.__name__}: {e}"
            ) from e
    return out
```

### WR-04: `df['障害区分'] != '障害'` filter is NaN-unsafe (works only because Kaggle stores `""` not NaN)

**File:** `src/pipeline/kaggle_converter.py:222-224`
**Issue:**
```python
df = df[df["レース日付"] >= "2015-01-01"].copy()
df = df[df["障害区分"] != "障害"].copy()
```
The obstacle filter relies on `df['障害区分'] != '障害'` returning `True` for flat races. This works ONLY because the Kaggle CSV stores `""` (empty string) for flat races (per `conftest.py:121-125`), so the comparison `"" != "障害"` is `True`. If a future upstream change (or a mixed input like the scraped corpus which may produce `pd.NA` for missing obstacle fields) introduces NaN, `pd.NA != "障害"` evaluates to `pd.NA`, which drops the row — silently losing flat races.

`normalizer.py:716-719` handles this exact case correctly with `(obstacle_values == "障害") & obstacle_values.notna()`. The Kaggle converter path should match.

**Fix:**
```python
obstacle_series = df["障害区分"]
obstacle_mask = (obstacle_series == "障害") & obstacle_series.notna()
df = df[~obstacle_mask].copy()
```

### WR-05: `integrate_standard_layer` requires `>=1` scraped month but does not enforce the month names are valid `YYYYMM`

**File:** `src/pipeline/integration.py:241-246`
**Issue:**
```python
month_dirs = sorted(p for p in scraped_root.iterdir() if p.is_dir())
if not month_dirs:
    raise ValueError(...)
```
The check only verifies at least one subdirectory exists. A stray non-month directory (e.g. a `.DS_Store` is not a dir, but a `__pycache__`, `.gitignore`-time artifact, or an old `archive/` subdir) would be silently treated as a "month partition" and its `{race,entry,result}.parquet` (if present) merged into the unified corpus. The filename-mismatch guard at line 268-272 raises `FileNotFoundError` only if the `{table}.parquet` is absent, not if the dir name is malformed.

**Fix:**
Validate that each directory name matches `^\d{6}$` (or a narrower `YYYYMM` regex) and skip/log non-matching directories explicitly:
```python
import re
MONTH_RE = re.compile(r"^\d{6}$")
month_dirs = sorted(
    p for p in scraped_root.iterdir() if p.is_dir() and MONTH_RE.match(p.name)
)
skipped = [
    p for p in scraped_root.iterdir() if p.is_dir() and not MONTH_RE.match(p.name)
]
if skipped:
    logger.warning(
        f"integrate_standard_layer: skipping non-YYYYMM dirs in scraped root: "
        f"{[p.name for p in skipped]}"
    )
if not month_dirs:
    raise ValueError(...)
```

### WR-06: `convert_flags_to_bool` uses `.apply(lambda)` instead of vectorized comparison — slow on 472MB CSV and produces `object` dtype (CR-01 vector)

**File:** `src/pipeline/kaggle_converter.py:469-474`
**Issue:**
```python
for col in flag_cols:
    df[col] = df[col].apply(
        lambda x: True if pd.notna(x) and x != "" else pd.NA
    )
```
Per-row `.apply(lambda)` over the full `race_result.csv` (~311K rows × 20 flag columns = ~6.2M cell evaluations) is materially slower than the vectorized form. Worse, the result has `object` dtype (mixed `True`/`pd.NA`), which is exactly the dtype that CR-01's `_DTYPE_COMPAT['bool']` loophole then silently endorses downstream. The Phase 6 D-02 recast at `kaggle_converter.py:449` (`_recast_to_canonical(race_df, RaceSchema)`) does promote these to nullable `boolean` via `astype("boolean")`, so the final Parquet is correct — but the intermediate `object` state is the loophole's enabler.

**Fix:**
```python
for col in flag_cols:
    s = df[col]
    df[col] = (s.notna() & (s != "")).astype("boolean")
```
This is both faster and produces `boolean` dtype directly, removing the intermediate `object` window.

### WR-07: `validate_referential_integrity` does not check `horse_race_id` FK relationship (entry ↔ result 1-to-1)

**File:** `src/pipeline/validators.py:360-411`
**Issue:**
`validate_referential_integrity` checks only `race_id` parent-child relationships across the 5 tables. It does NOT verify the `horse_race_id` 1-to-1 relationship between `entry` and `result` — the very invariant that `integration.py:327-338` extends the hard-violation filter to enforce (HIGH #8b cycle-4: `validate_integrity` returns the mismatch string and the extended filter catches it).

So if a post-hoc editor corrupts `entry` or `result` outside the integration path (e.g. a manual `drop_duplicates` that breaks the 1-to-1), this validator reports `errors == []` and `overall_pass=True`. The integration path catches it at write time, but the standalone validator does not.

**Fix:**
Add a 1-to-1 check that mirrors `normalizer.validate_integrity` check (d):
```python
import pandas as pd
from collections import Counter

entry_path = parquet_dir / "entry.parquet"
result_path = parquet_dir / "result.parquet"
if entry_path.exists() and result_path.exists():
    entry_hids = Counter(
        pd.read_parquet(entry_path, columns=["horse_race_id"])["horse_race_id"]
        .dropna().tolist()
    )
    result_hids = Counter(
        pd.read_parquet(result_path, columns=["horse_race_id"])["horse_race_id"]
        .dropna().tolist()
    )
    if entry_hids != result_hids:
        only_entry = len(entry_hids - result_hids)
        only_result = len(result_hids - entry_hids)
        errors.append(
            f"entry/result horse_race_id not 1-to-1 "
            f"(only-in-entry={only_entry}, only-in-result={only_result})"
        )
```

### WR-08: `_find_csv` fallback double-strips the underscore, breaking the documented fallback

**File:** `src/pipeline/validators.py:432-438`
**Issue:**
```python
if pattern.startswith("*"):
    stripped = pattern[1:]  # e.g., "_race_result.csv"
    exact2 = source_dir / stripped[1:]  # strip leading underscore -> "race_result.csv"
    if exact2.exists():
        return exact2
```
The variable is named `stripped` but already has the asterisk removed (`pattern[1:]` = `"_race_result.csv"`). Then `stripped[1:]` strips the underscore too, yielding `"race_result.csv"`. The inline comment describes this correctly, but the two-step strip is non-obvious and the variable name `stripped` is misleading (it is "asterisk-stripped", not "fully stripped"). More importantly, if the pattern is `"*_race_result.csv"` and the directory contains `"race_result.csv"` (no prefix at all), this fallback returns it — but if the directory contains only the long-named `"19860105-20210731_race_result.csv"`, the earlier `sorted(source_dir.glob(pattern))` at line 429 already returns the long name, so this fallback is dead code for the real Kaggle filename. Confirm it actually fires for any realistic input or remove it.

**Fix:**
Either delete the fallback (if `glob` already handles the real Kaggle names) or make the intent explicit:
```python
if pattern.startswith("*"):
    # "*_race_result.csv" -> look for bare "race_result.csv" as a final fallback.
    bare_name = pattern[1:].lstrip("_")
    candidate = source_dir / bare_name
    if candidate.exists():
        return candidate
```

### WR-09: `_UNMAPPED_RACE_FLAGS` list duplicates information already implied by `RaceSchema.model_fields` — drift risk

**File:** `src/pipeline/kaggle_converter.py:48-57`
**Issue:**
The list `_UNMAPPED_RACE_FLAGS` is hand-maintained: it lists 8 `race_flag_*` fields that have no Kaggle CSV source. If a future schema change renames or removes one of these (or adds a new unmapped flag), this list silently drifts. There is no test that asserts `_UNMAPPED_RACE_FLAGS == (set(RaceSchema.model_fields starting with race_flag_) - set(KAGGLE_COLUMN_MAP race values))`.

**Fix:**
Derive the list mechanically from the schema and the column map:
```python
def _compute_unmapped_race_flags() -> list[str]:
    mapped_race_fields = {
        eng for (tbl, eng) in KAGGLE_COLUMN_MAP.values() if tbl == "race"
    }
    all_race_flags = {
        f for f in RaceSchema.model_fields if f.startswith("race_flag_")
    }
    return sorted(all_race_flags - mapped_race_fields)

_UNMAPPED_RACE_FLAGS = _compute_unmapped_race_flags()
```
Add a test asserting the list equals the computed set.

## Info

### IN-01: `conftest.py:208-209` comment says "Set proper dtypes for flag columns (str)" but uses `object`

**File:** `tests/pipeline/conftest.py:205-209`
**Issue:**
```python
# Set proper dtypes for flag columns (str) to match DTYPE_SPEC behavior
for col in FLAG_COLUMNS:
    df[col] = df[col].astype(object)
```
The comment claims `str` but the code casts to `object`. Pandas' Python `str` dtype is `object`, so the runtime behavior is correct, but the comment is misleading. Also the `conftest.py` module docstring at line 8 claims `DTYPE_SPEC` has "23 entries" (the original count) but the actual count is 25 (20 flags + 3 mixed-type + 2 zero-padded), and the test `test_dtype_spec_has_25_entries` correctly asserts 25. The conftest docstring is stale.

**Fix:**
Update the comment to match the code and update the conftest docstring count.

### IN-02: `integration.py` docstring title says "Phase 6 Plan 06-02" but the file is reused beyond that plan

**File:** `src/pipeline/integration.py:1`
**Issue:**
```python
"""Phase 6 Plan 06-02: unified standard-layer corpus integration.
```
The module is now the production integration entry point, not a plan-specific artifact. The title makes the file look throwaway.

**Fix:**
Drop the "Plan 06-02" prefix: `"""Unified standard-layer corpus integration (Kaggle + scraped)."""`.

### IN-03: `test_integration.py:225` contains a `pass` statement in a loop that does nothing

**File:** `tests/pipeline/test_integration.py:218-225`
**Issue:**
```python
for month_dir in scraped_root.iterdir():
    if month_dir.is_dir():
        # Rewrite each month to be a trivial 1-row per-table extension
        # with horse_race_ids that ALSO mismatch ...
        pass
```
This loop iterates and does nothing. The `pass` body and the explanatory comment are dead code left over from an earlier draft; the actual cleanup is the `shutil.rmtree(scraped_root)` at line 233. The dead loop adds confusion (reader thinks the rewrite happens inside the loop).

**Fix:**
Delete lines 218-225 (the empty loop and its comment).

### IN-04: `validators.py:725` magic number `1-8` for bracket range is undocumented

**File:** `src/pipeline/validators.py:723-729`
**Issue:**
```python
bracket_series = pd.to_numeric(entry_df["bracket_num"], errors="coerce")
invalid_brackets = bracket_series[(bracket_series < 1) | (bracket_series > 8)]
```
The bounds `1` and `8` for bracket_num are JRA-specific (8 brackets max). The `EntrySchema.bracket_num` field at `entry.py:47-52` documents this with `ge=1, le=8`, but the validator hardcodes the numbers without a reference.

**Fix:**
Either import the bounds from a single source of truth or add a constant with a citation:
```python
# JRA bracket numbers are 1-8 (EntrySchema.bracket_num ge/le).
BRACKET_MIN, BRACKET_MAX = 1, 8
invalid_brackets = bracket_series[
    (bracket_series < BRACKET_MIN) | (bracket_series > BRACKET_MAX)
]
```

### IN-05: `tests/pipeline/test_validators.py:643` assertion message claims "5% tolerance" but the check is exact equality

**File:** `tests/pipeline/test_validators.py:625-643`
**Issue:**
```python
def test_row_counts_within_expected_range(self) -> None:
    """Verify row counts are within 5% of expected.
    ...
    """
    ...
    for table, passed in result.items():
        assert passed, f"{table} row count outside 5% tolerance"
```
The docstring and the assertion message reference a 5% tolerance, but `validate_row_counts` does exact equality (`actual_count == expected_count`). The test will fail on any drift from the hardcoded expected counts, not within a 5% band. The integration test is conditional (`_parquet_files_exist`), so this is a test-quality issue, not a runtime one.

**Fix:**
Either implement a 5% tolerance check inline, or fix the docstring/assertion message to say "exact row count match":
```python
"""Verify row counts exactly match the expected unified-corpus counts."""
```

### IN-06: `convert()` writes Parquet files inside a `for` loop without batching; large corpora generate many `_atomic_write_parquet` calls

**File:** `src/pipeline/kaggle_converter.py:261-265`
**Issue:**
```python
for table_name, table_df in core_tables.items():
    output_path = core_out_dir / f"{table_name}.parquet"
    _atomic_write_parquet(table_df, output_path)
```
This is correct but logs one `logger.info` per table. Per MEMORY.md `scraper-logging-no-per-item`, per-table logging is the right granularity here (not per-row). No defect — recorded for completeness; no action needed.

---

_Reviewed: 2026-06-15_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
