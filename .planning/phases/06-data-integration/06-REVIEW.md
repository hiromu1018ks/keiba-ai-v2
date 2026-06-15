---
phase: 06-data-integration
reviewed: 2026-06-15T00:00:00Z
depth: deep
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
**Depth:** deep
**Files Reviewed:** 9 (4 source, 5 test)
**Status:** issues_found

## Summary

Deep cross-file review of the phase-06 data-integration layer. Traced the full data flow `kaggle_converter -> integration -> validators` against `src/schemas/{race,entry,result,audit}.py`, `src/scraper/normalizer.py`, and `src/scraper/flag_crosswalk.py`, and validated the grade-detection regex against the actual Kaggle CSV (`data/raw/kaggle/19860105-20210731_race_result.csv`).

The transactional design of `integrate_standard_layer` (idempotent transform + separate Kaggle input path + dedicated `_commit_staging` boundary + extended hard-violation filter) is sound and the cycle-5 isolated tests genuinely prove the `_commit_staging` swap boundary and the `'mismatch'` hard-violation token. The D-01 grade-detection rewrite has the right shape but TWO data-correctness gaps that silently corrupt real races.

Four BLOCKER-tier defects:

1. **Listed races (`grade="L"`) are silently misclassified** — `_LISTED_REGEX` requires parentheses, so 2,232 entry-rows with `grade="L"` get `race_flag_listed=False` and `race_flag_stakes=False` instead of `True` (CR-01).
2. **Bare `grade="G"` rows are missed** — `_GRADE_REGEX` needs 2+ chars, so 110 entry-rows (e.g. ターコイズステークス, 葵ステークス) get `race_flag_graded_stakes=False` (CR-02).
3. **`_DTYPE_COMPAT['bool']` accepts `object` unconditionally** — any `race_flag_*` column stored as `object` with arbitrary string/numeric content passes schema conformance (CR-03).
4. **`validate_sample_rows` reports PASS for tables it could not check** (three silent-True paths) + `audit_pass` hardcoded `True` — the aggregate `overall_pass` cannot detect empty Parquet, missing keys, or race-table leakage (CR-04).

Additional Warnings cover: `_GRADE_REGEX` missing the `GⅠ` (Roman-numeral U+2160) form, NaN-unsafe obstacle filter, over-broad Rule-1 float shortcut, duplicate `_recast_to_canonical` definitions, and more. テストは網羅的で cycle-5 isolation は本物だが、grade-detection の実データ検証と validator の silent-PASS 経路が出荷前に必須修正。

## Critical Issues

### CR-01: Listed races (grade="L") are silently misclassified — `race_flag_listed` and `race_flag_stakes` both become `False`

**File:** `src/pipeline/kaggle_converter.py:60-139` (via `src/scraper/flag_crosswalk.py:124-213`)
**Issue:** D-01 removed the Kaggle-side `レース記号/(国際) -> race_flag_graded_stakes` mapping and made `_apply_grade_detection` the sole source of graded/stakes/listed detection on the Kaggle side. That helper calls `derive_race_flags(race_condition=cond, race_name=name)`. When the Kaggle `リステッド・重賞競走` column is `"L"` (the value Kaggle actually stores for Listed races — verified against the real CSV), `_apply_grade_detection` sets `cond = "L"` and `derive_race_flags("L", race_name)` is invoked.

Inside `derive_race_flags`, `_LISTED_REGEX = re.compile(r"\(L\)|（L）|\(リステッド\)|（リステッド）")` **requires parentheses** around the `L`. A bare `L` (which is exactly what Kaggle stores) matches NEITHER `_LISTED_REGEX` NOR `_STAKES_REGEX` (`重賞`), so the function returns `listed=None, stakes=None, graded=None`. The subsequent OR-merge with `fillna(False)` then writes `race_flag_listed = False` and `race_flag_stakes = False` for every Listed race in the unified corpus.

Verified end-to-end:
```
grade='L': race_flag_listed=False (should be True)
            race_flag_stakes=False (should be True — a Listed race is a stakes)
grade='G1': race_flag_graded_stakes=True (works — G1 is in the regex)
```

Data impact (counted from `data/raw/kaggle/19860105-20210731_race_result.csv`, 2015+ flat races):
- `grade='L'`: **2,232 entry-rows** misclassified
- `grade='G'`: **110 entry-rows** misclassified (see CR-02)
- `grade='G3'`: 6,692 / `grade='G2'`: 3,234 / `grade='G1'`: 2,584 (correctly detected)

This corrupts any downstream EV feature that keys off `race_flag_listed` or `race_flag_stakes` (race-class strength priors, class-level features). With 2,232 affected entry-rows this is systemic mislabel, not an edge case. The phase-06 test `TestGradeDetection.test_kaggle_graded_derivation_matches_regex` only exercises `G1`/`None` cases and does NOT cover `grade="L"`, so the suite is green while the data is corrupt.

**Fix:** `_LISTED_REGEX` in `flag_crosswalk.py` cannot safely accept bare `L` (too ambiguous inside race_name). The Kaggle converter must classify the raw grade token directly. In `kaggle_converter._apply_grade_detection`, after building `per_row_results`, add a bare-token classification pass:

```python
# Bare-grade-token classification for Kaggle forms derive_race_flags misses.
# Kaggle stores 'L' for Listed (no parentheses) and bare 'G' for some graded
# races; _LISTED_REGEX requires (L) and _GRADE_REGEX requires GI/G1/etc (2+ chars).
listed_tokens = {"L"}  # bare Listed marker
for i, row in enumerate(race_df.itertuples(index=False)):
    grade_val = getattr(row, "grade", None) if has_grade else None
    if pd.isna(grade_val):
        continue
    g = str(grade_val).strip()
    if g in listed_tokens:
        per_row_results[i]["race_flag_listed"] = True
        per_row_results[i]["race_flag_stakes"] = True
```

Add regression tests:
```python
def test_kaggle_listed_grade_L_detected(self) -> None:
    """grade='L' (bare) sets race_flag_listed=True and race_flag_stakes=True."""
    # ... build race_df with grade=['L', None], call _apply_grade_detection,
    # assert race_flag_listed.iloc[0] is True and race_flag_stakes.iloc[0] is True
```

### CR-02: Bare `grade="G"` rows (110 entry-rows) are not detected as graded/stakes

**File:** `src/pipeline/kaggle_converter.py:60-139` (via `src/scraper/flag_crosswalk.py:124-130`)
**Issue:** The Kaggle `リステッド・重賞競走` column contains a bare `"G"` for 110 flat-race entry-rows (verified: races like `サウジアラビアRC`, `ターコイズステークス`, `葵ステークス` — all graded/stakes races in reality). `_GRADE_REGEX` requires `GI|GII|GIII|G1|G2|G3|JG*` (two+ chars), so a bare `G` matches neither `_GRADE_REGEX` nor `_STAKES_REGEX`. `_apply_grade_detection` therefore writes `race_flag_graded_stakes=False, race_flag_stakes=False` for these graded races.

Verified:
```
_GRADE_REGEX.search('G') -> False
_STAKES_REGEX.search('G') -> False
```

Same failure mode as CR-01 (bare-grade token the regexes don't expect) and same impact (graded/class features trained on mislabeled rows).

**Fix:** In `kaggle_converter._apply_grade_detection`, treat a bare `grade="G"` as a stakes/graded marker. Extend the bare-token classification pass from CR-01:

```python
import re as _re
_GRADE_PREFIX_RE = _re.compile(r"^(?:G|Ｇ)$")  # bare 'G' or full-width 'Ｇ' alone
for i, row in enumerate(race_df.itertuples(index=False)):
    grade_val = getattr(row, "grade", None) if has_grade else None
    if pd.isna(grade_val):
        continue
    g = str(grade_val).strip()
    if g == "L":
        per_row_results[i]["race_flag_listed"] = True
        per_row_results[i]["race_flag_stakes"] = True
    elif _GRADE_PREFIX_RE.match(g):
        # Bare 'G' is a Kaggle shorthand for graded — real race_name determines
        # the actual grade level, but the bare marker is evidence of graded/stakes.
        per_row_results[i]["race_flag_graded_stakes"] = True
        per_row_results[i]["race_flag_stakes"] = True
```

Add a regression test using `リステッド・重賞競走="G"`.

### CR-03: `_DTYPE_COMPAT['bool']` accepts `object` dtype unconditionally — schema conformance cannot catch corrupted bool columns

**File:** `src/pipeline/validators.py:36`
**Issue:**
```python
_DTYPE_COMPAT: dict[str, set[str]] = {
    ...
    "bool": {"bool", "boolean", "object"},  # object for nullable bool (True/None)
}
```
The `"object"` entry was added to tolerate nullable booleans stored as object after a Parquet round-trip. But when `actual_dtype in compatible_dtypes` is `True`, the entire downstream content-sanity block is skipped. A `race_flag_handicap` column with `dtype=object` and content `["yes", 5, pd.NA, "false"]` — arbitrary strings/ints that are NOT bools — passes `validate_schema_conformance` silently. This is the opposite of a validator.

The nullable `boolean` (capital B) pandas dtype is already in the set and is the correct nullable-bool storage per `SCHEMA_DTYPE_MAP`. The `object` fallback is unsound: it accepts ANY object content, not just `True/False/None` triples.

Repro:
```python
import pandas as pd
df = pd.DataFrame({"race_flag_handicap": pd.array(["yes", None, 5], dtype=object)})
# str(df['race_flag_handicap'].dtype) == 'object'
# 'object' in _DTYPE_COMPAT['bool'] -> True -> check passes
```

This affects ALL 20 `race_flag_*` fields plus any future `Optional[bool]` schema field. In a betting-EV system, a corrupt `race_flag_graded_stakes` column with mixed string/int content would silently pass validation, then contaminate the graded-stakes feature.

**Fix:**
Remove `"object"` from `_DTYPE_COMPAT['bool']`. Nullable `boolean` serializes to Arrow `bool` (verified per `normalizer.py` SCHEMA_DTYPE_MAP which uses `"boolean"` for all 20 flags), so the `object` fallback is not needed for the production pipeline. If a Parquet-round-trip-to-object artifact is ever observed, handle it with a content check:

```python
"bool": {"bool", "boolean"},  # nullable bool serializes to Arrow bool, NOT object
```

And add an explicit object-content guard in the dtype-check block:
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

### CR-04: `validate_sample_rows` reports PASS for unchecked tables AND `audit_pass` is hardcoded `True` — aggregate `overall_pass` cannot detect multiple regression classes

**File:** `src/pipeline/validators.py:525-530, 547-549, 559-566, 850-852`
**Issue:**
Two independent silent-PASS defects combine to make `run_all_validations`'s `overall_pass` unreliable:

**(a) `validate_sample_rows` silent-True paths** (lines 525-527, 547-549, 559-566):
Three branches set `results[table_name] = True` and `continue` when the check is genuinely impossible to perform:
- Line 525-527: empty Parquet (`len(pq_df) == 0`) → `True`
- Line 547-549: csv_key not in source columns → `True`
- Line 559-566: no comparable columns → `True`

In `run_all_validations` line 848, `sample_pass = all(sample_result.values())`. These silent `True` values mean the aggregate reports success even when zero rows were sampled. A regression that empties a table or drops the key column produces `overall_pass=True`. The line 525-527 case is especially insidious: a corrupt convert/integration run that produced a 0-row Parquet (the very scenario `integration.py:380-384` raises about at write time) would be hidden by this validator.

**(b) `audit_pass` hardcoded `True`** (lines 850-852):
```python
# Audit: expected behavior -- race should have no leaks, but entry/result/odds/payoff
# are expected to have post-race columns, so we don't fail on those
audit_pass = True  # Audit is informational, not a pass/fail check
```
The module docstring advertises "8 validation checks" with `audit_leakage` as check 3, and `result["audit"]` is set to `audit_pass` (always `True`). Callers reading `result["overall_pass"]` cannot detect race-table leakage. The race table is contractually pre-race-only (`integration.py:341-348` RAISES on race leakage at write time), but `run_all_validations` is the post-hoc independent validator. If data lands in `data/standard/race.parquet` outside the integration path (manual edit, future refactor), this validator silently blesses the leak.

**Fix:**

For (a), distinguish "not checked" from "passed":
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
Then the aggregator `sample_pass = all(sample_result.values()) if sample_result else True` correctly returns True only when at least one table was checked AND all checked tables passed. If "table present but unchecked" must fail loud, set `False` instead.

For (b), make audit pass conditional on the race table specifically (race must have zero leaks; entry may leak the documented `{popularity, win_odds}` set; result/odds/payoff are post-race by design):
```python
audit_pass = True
if "race" in audit_result:
    real_race_leaks = [c for c in audit_result["race"] if not c.startswith("Missing:")]
    audit_pass = audit_pass and (len(real_race_leaks) == 0)
if "entry" in audit_result:
    unexpected = set(audit_result["entry"]) - {"popularity", "win_odds"}
    audit_pass = audit_pass and (len(unexpected) == 0)
```
Update the docstring to match (the current comment "Audit is informational, not a pass/fail check" contradicts the docstring's list of 8 checks).

## Warnings

### WR-01: `_GRADE_REGEX` does not match half-width `G` + Roman-numeral `Ⅰ` (U+2160) form used in JRA publications

**File:** `src/scraper/flag_crosswalk.py:124-130`
**Issue:** The regex handles half-width-digit (`G1`), full-width-both (`ＧＩ`), and half-width-both (`GI`) forms but NOT the mixed `GⅠ`/`GⅡ`/`GⅢ` form (half-width `G` U+0047 + ROMAN NUMERAL ONE U+2160 / TWO U+2161 / THREE U+2162). That mixed form appears in JRA official materials and in some scraped race names; the scraper-side path feeds `race_name` into the same regex. Verified:
```
_GRADE_REGEX.search('GⅠ')   -> False  (Ⅰ is U+2160 ROMAN NUMERAL ONE)
_GRADE_REGEX.search('ＧＩ')  -> True   (full-width both — covered)
```
Kaggle itself uses `G1`/`G2`/`G3` (verified against the CSV), so the Kaggle path is safe today. But a scraped race named `優駿牝(GⅠ)` would be missed on the scraper side, producing the same Kaggle-vs-scraped flag divergence D-01 was designed to eliminate. The phase-06 test `test_kaggle_graded_derivation_matches_regex` docstring claims the cycle-2 failure was `GⅠ` with codepoint `U+FF21`, but `U+FF21` is full-width `Ａ`, not the Roman numeral — the docstring's codepoint annotation is wrong and the actual `Ⅰ` (U+2160) case remains uncovered.

**Fix:** Add the Roman-numeral alternatives to `_GRADE_REGEX`:
```python
_GRADE_REGEX = re.compile(
    r"(?:GⅢ|GⅡ|GⅠ|"            # half-width G + Roman numeral (U+2160..2162)
    r"GIII|GII|GI|"
    r"JGIII|JGII|JGI|"
    r"G3|G2|G1|JG3|JG2|JG1|"
    r"ＧＩＩＩ|ＧＩＩ|ＧＩ)"
)
```
And correct the misleading `U+FF21` annotation in the test docstring to `U+2160`.

### WR-02: Rule-1 fix is over-broad — `'float' in actual_dtype.lower()` accepts ANY int field stored as float with decimal content

**File:** `src/pipeline/validators.py:172-174`
**Issue:**
```python
if expected_cat == "int" and "float" in actual_dtype.lower():
    # Nullable Int64 columns can become float64 when all NaN
    continue
```
The comment justifies this as accepting "Nullable Int64 columns can become float64 when all NaN" — but the actual predicate accepts `float64`/`Float32`/`Float64` for ANY int field regardless of content. A `distance` column corrupted to `float64` with values like `[2000.5, 1600.25]` passes schema conformance silently. The legitimate case (`SCHEMA_DTYPE_MAP` deliberately uses `Float64` for `corner_1..4`, `horse_weight`, `weight_change`, `popularity`) is real, but the shortcut conflates "nullable-int-stored-as-float-by-design" with "int-field-corrupted-to-float".

**Fix:** Either constrain the shortcut to a known allowlist OR check that the float values are integer-valued:
```python
_INT_AS_FLOAT_ALLOWLIST = {
    "corner_1", "corner_2", "corner_3", "corner_4",
    "horse_weight", "weight_change", "popularity",
}
if expected_cat == "int" and "float" in actual_dtype.lower():
    if field_name in _INT_AS_FLOAT_ALLOWLIST:
        continue
    series = df[field_name].dropna()
    if series.empty or (series % 1 == 0).all():
        continue
    errors.append(
        f"Dtype/value mismatch for {field_name}: stored as {actual_dtype} "
        f"with non-integer values (e.g. {series.head(3).tolist()})"
    )
```

### WR-03: `integrate_standard_layer` audit does NOT raise when `popularity`/`win_odds` are absent from the merged entry table

**File:** `src/pipeline/integration.py:349-361`
**Issue:** The audit block computes `unexpected_entry_leak = set(entry_leaked) - expected_entry_leak` and raises only on UNEXPECTED leaks. But if `entry_leaked` is missing `popularity` or `win_odds` (because they were silently dropped from one input source), `unexpected_entry_leak` is empty and no raise occurs. The safety net is `_assert_column_set_equality` (line 279-280) which checks the FULL schema column set before reindex — so a missing column IS caught earlier. However, the audit itself is documented as a defense-in-depth check and its current logic cannot detect the "expected leak is missing" case. If a future refactor weakened the column-set equality check, this audit would be the last line of defense and it would fail silently.

**Fix:** Either document explicitly that `_assert_column_set_equality` is the sole guard for column presence (and remove the audit's pretense of being a defense-in-depth check), or strengthen the audit:
```python
# After confirming unexpected_entry_leak is empty, also confirm the expected
# leaks ARE present (popularity/win_odds must be in the merged entry columns).
missing_expected = expected_entry_leak - set(merged_entry.columns)
if missing_expected:
    raise ValueError(
        f"integrate_standard_layer: entry table is MISSING expected post-race "
        f"columns {sorted(missing_expected)!r} (silent column drop)"
    )
```

### WR-04: Duplicate `_recast_to_canonical` definitions with divergent mutation semantics

**File:** `src/pipeline/kaggle_converter.py:142-167` vs `src/pipeline/integration.py:102-124`
**Issue:** Both modules define a function with the identical name `_recast_to_canonical` and nearly identical docstrings ("Phase 6 D-02: the Kaggle-side Parquet must match the scraped-side dtype contract..."). The semantics diverge:

- `kaggle_converter.py:160` mutates the input DataFrame in place (`df[col] = df[col].astype(target)` with no copy).
- `integration.py:113-118` returns a copy (`out = df.copy()`) — does NOT mutate the caller's frame.

The divergence is load-bearing: `integration.py:283-284` calls `_recast_to_canonical` on `kaggle_df` / `scraped_df` and the caller relies on the original frames being preserved for the audit call later. The `kaggle_converter.py` version is called on DataFrames that are about to be written, so in-place mutation is harmless there — but the inconsistency is a latent footgun for future maintainers who copy one implementation expecting the other's behavior. There are now THREE near-identical strict-recast loops (`normalizer._build_typed_dataframe`, `normalizer._recast_for_storage`, and these two `_recast_to_canonical`).

**Fix:** Extract a single implementation into a shared module and import from both:
```python
# src/pipeline/_dtypes.py (or extend src/scraper/normalizer.py)
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
            raise TypeError(...) from e
    return out
```

### WR-05: `df['障害区分'] != '障害'` filter is NaN-unsafe (works only because Kaggle stores `""` not NaN)

**File:** `src/pipeline/kaggle_converter.py:222-224`
**Issue:**
```python
df = df[df["レース日付"] >= "2015-01-01"].copy()
df = df[df["障害区分"] != "障害"].copy()
```
The obstacle filter relies on `df['障害区分'] != '障害'` returning `True` for flat races. This works ONLY because the Kaggle CSV stores `""` (empty string) for flat races, so the comparison `"" != "障害"` is `True`. If a future upstream change introduces NaN (which `pd.read_csv` produces for truly-empty cells when `dtype` is not `str`), `pd.NA != "障害"` evaluates to `pd.NA`, which drops the row — silently losing flat races.

`normalizer.py:716-719` handles this exact case correctly with `(obstacle_values == "障害") & obstacle_values.notna()`. The Kaggle converter path should match.

**Fix:**
```python
obstacle_series = df["障害区分"]
obstacle_mask = (obstacle_series == "障害") & obstacle_series.notna()
df = df[~obstacle_mask].copy()
```

### WR-06: `integrate_standard_layer` does not validate scraped month directory names are `YYYYMM`

**File:** `src/pipeline/integration.py:241-246`
**Issue:**
```python
month_dirs = sorted(p for p in scraped_root.iterdir() if p.is_dir())
if not month_dirs:
    raise ValueError(...)
```
The check only verifies at least one subdirectory exists. A stray non-month directory (e.g. `__pycache__`, an `archive/` subdir, a `.DS_Store`-adjacent artifact) would be silently treated as a "month partition" and its `{race,entry,result}.parquet` (if present) merged into the unified corpus. The filename-mismatch guard at line 268-272 raises `FileNotFoundError` only if `{table}.parquet` is absent, not if the dir name is malformed — so a stray dir containing well-named Parquet would silently pollute the corpus.

**Fix:** Validate that each directory name matches `^\d{6}$` and skip/log non-matching directories explicitly:
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

### WR-07: `_atomic_write_parquet` imported from outside `normalizer.__all__` — private-API contract leak

**File:** `src/pipeline/integration.py:70-74`, `src/pipeline/kaggle_converter.py:31`
**Issue:** Both `integration.py` and `kaggle_converter.py` import `_atomic_write_parquet` from `src.scraper.normalizer`, but `normalizer.py:792-798` explicitly defines `__all__` WITHOUT `_atomic_write_parquet`. The leading underscore signals "module-private", yet the function is now a load-bearing cross-module dependency of two production modules. If a future refactor renames or removes it, only a grep (not `__all__`) catches the breakage, and `from src.scraper.normalizer import *` would silently drop it.

**Fix:** Either (a) promote it to the public surface by adding it to `__all__` and renaming to `atomic_write_parquet` (drop the underscore), or (b) extract it into a shared utility module (`src/pipeline/io_utils.py`) that both consumers import explicitly.

### WR-08: `validate_referential_integrity` does not check `horse_race_id` FK (entry ↔ result 1-to-1)

**File:** `src/pipeline/validators.py:360-411`
**Issue:** `validate_referential_integrity` checks only `race_id` parent-child relationships across the 5 tables. It does NOT verify the `horse_race_id` 1-to-1 relationship between `entry` and `result` — the very invariant that `integration.py:327-338` extends the hard-violation filter to enforce (HIGH #8b cycle-4). So if a post-hoc editor corrupts `entry` or `result` outside the integration path (e.g. a manual `drop_duplicates` that breaks the 1-to-1), this validator reports `errors == []` and `overall_pass=True`. The integration path catches it at write time, but the standalone validator does not.

**Fix:** Add a 1-to-1 check that mirrors `normalizer.validate_integrity` check (d):
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

### WR-09: Stale docstring in `flag_crosswalk.py:30-46` contradicts the D-01 fix and will mislead future maintainers

**File:** `src/scraper/flag_crosswalk.py:30-46`
**Issue:** The module docstring contains an extended "Phase 6 reconciliation note" that says:

> "The Kaggle-side `src/pipeline/column_mapping.py` line 68 still maps `レース記号/(国際)` -> `race_flag_graded_stakes`; that file is out of scope for this gap fix (it is a Kaggle-pipeline file). Phase 6 (Data Integration) MUST reconcile this divergence before joining the two sources ... Until Phase 6 ships, scraped 2022-2024 rows with `(国際)` but no GI token will have `race_flag_graded_stakes=None` while equivalent 2015-2021 Kaggle rows have `True` — a known, documented, bounded inconsistency."

This is now FALSE. Phase 6 D-01 DID remove the Kaggle-side mapping (`column_mapping.py:68-73` has only the explanatory comment, no map entry for `(国際)`; `KAGGLE_COLUMN_MAP` has 65 entries, not 66, per `test_kaggle_column_map_has_65_entries`). A maintainer reading this docstring will either (a) re-add the mapping to "complete" what they think is unfinished work, re-introducing UAT-Test-3, or (b) add a `race_flag_international` column that nobody else expects. Either path re-opens the major-severity bug D-01 closed.

**Fix:** Replace the stale reconciliation note with a "Phase 6 D-01 closed this gap" pointer:
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

## Info

### IN-01: `convert_flags_to_bool` uses `.apply(lambda)` — slow on 472MB CSV and produces intermediate `object` dtype

**File:** `src/pipeline/kaggle_converter.py:469-474`
**Issue:** The flag conversion uses a Python-level `.apply(lambda)` on every flag column. For the full Kaggle corpus this is materially slower than a vectorized form. Worse, the result has `object` dtype (mixed `True`/`pd.NA`), which is exactly the dtype that CR-03's `_DTYPE_COMPAT['bool']` loophole then silently endorses downstream. The Phase 6 D-02 recast at `kaggle_converter.py:449` does promote these to nullable `boolean` via `astype("boolean")`, so the final Parquet is correct — but the intermediate `object` state is the loophole's enabler.

**Fix:**
```python
for col in flag_cols:
    s = df[col]
    df[col] = (s.notna() & (s.astype(str).str.strip() != "")).astype("boolean")
```
This is both faster and produces `boolean` dtype directly, removing the intermediate `object` window. (Low priority — current output is correct.)

### IN-02: `_apply_grade_detection` per-row `itertuples` + `derive_race_flags` is ~22K Python function calls

**File:** `src/pipeline/kaggle_converter.py:113-126`
**Issue:** The helper iterates every race row and calls `derive_race_flags` (which compiles and runs 3 regex searches) per row. On the full Kaggle race table (~22K rows post-filter) this is ~66K regex searches in a Python loop. Correctness is fine; the `race_condition=' '` bypass logic (lines 119-122) is also hard to follow — a comment explaining WHY a single space (not empty string) is used would help future maintainers.

**Fix:** Consider vectorizing with `df['grade'].str.extract` + a single `derive_race_flags` invocation on the concatenated haystack, or at minimum add a clearer comment on the `' '` vs `''` distinction. (Performance is out of scope per review rules; noted for completeness.)

### IN-03: `test_integration.py:218-225` contains a dead `for ... pass` loop with a misleading comment

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

**Fix:** Delete lines 218-225 (the empty loop and its comment).

### IN-04: `_UNMAPPED_RACE_FLAGS` is hand-maintained — drift risk vs `RaceSchema.model_fields`

**File:** `src/pipeline/kaggle_converter.py:48-57`
**Issue:** The list `_UNMAPPED_RACE_FLAGS` is hand-maintained: it lists 8 `race_flag_*` fields that have no Kaggle CSV source. If a future schema change renames or removes one of these (or adds a new unmapped flag), this list silently drifts. There is no test that asserts `_UNMAPPED_RACE_FLAGS == (set(race_flag_* schema fields) - set(race_flag_* mapped fields))`.

**Fix:** Derive the list mechanically from the schema and the column map:
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

### IN-05: `validators.py:725` magic numbers for bracket range are undocumented

**File:** `src/pipeline/validators.py:723-729`
**Issue:**
```python
bracket_series = pd.to_numeric(entry_df["bracket_num"], errors="coerce")
invalid_brackets = bracket_series[(bracket_series < 1) | (bracket_series > 8)]
```
The bounds `1` and `8` are JRA-specific (8 brackets max). `EntrySchema.bracket_num` at `entry.py:47-52` documents this with `ge=1, le=8`, but the validator hardcodes the numbers without a reference.

**Fix:** Add a citation constant:
```python
# JRA bracket numbers are 1-8 (EntrySchema.bracket_num ge/le).
BRACKET_MIN, BRACKET_MAX = 1, 8
invalid_brackets = bracket_series[
    (bracket_series < BRACKET_MIN) | (bracket_series > BRACKET_MAX)
]
```

### IN-06: `test_validators.py:625-643` docstring claims "5% tolerance" but the check is exact equality

**File:** `tests/pipeline/test_validators.py:625-643`
**Issue:**
```python
def test_row_counts_within_expected_range(self) -> None:
    """Verify row counts are within 5% of expected. ..."""
    ...
    for table, passed in result.items():
        assert passed, f"{table} row count outside 5% tolerance"
```
The docstring and the assertion message reference a 5% tolerance, but `validate_row_counts` does exact equality (`actual_count == expected_count`). The test will fail on any drift from the hardcoded expected counts, not within a 5% band. Conditional (`_parquet_files_exist`), so test-quality issue, not runtime.

**Fix:** Either implement a 5% tolerance check inline, or fix the docstring/assertion message:
```python
"""Verify row counts exactly match the expected unified-corpus counts."""
```

---

_Reviewed: 2026-06-15_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
