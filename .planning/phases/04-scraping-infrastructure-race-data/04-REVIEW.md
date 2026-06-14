---
phase: 04-scraping-infrastructure-race-data
reviewed: 2026-06-14T10:55:00Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - src/scraper/__init__.py
  - src/scraper/course_codes.py
  - src/scraper/enumeration.py
  - src/scraper/fetcher.py
  - src/scraper/flag_crosswalk.py
  - src/scraper/models.py
  - src/scraper/normalizer.py
  - src/scraper/orchestrator.py
  - src/scraper/parser.py
findings:
  critical: 2
  warning: 7
  info: 4
  total: 13
status: issues_found
---

# Phase 04: Code Review Report

**Reviewed:** 2026-06-14T10:55:00Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Reviewed the netkeiba scraping infrastructure (9 files, ~2.0k LOC) at standard depth, tracing parser/normalizer output into the standard-layer `RaceSchema` / `EntrySchema` / `ResultSchema` and cross-referencing `src/pipeline/column_mapping.py` for the Kaggle join contract.

**Leakage posture is sound:** `RaceSchema`/`EntrySchema` carry only pre-race fields (mod note: `popularity`/`win_odds` are tagged `pre_race=False` and belong in EntrySchema by design — they are reserved for EV calculation, never features). `ResultSchema` cleanly isolates all post-race data (finish_position, finish_time, margin, corners, last_3f, prize_money). No leak was found.

**Flag crosswalk is exhaustive:** programmatically verified all 13 unique `race_flag_*` targets in `KAGGLE_COLUMN_MAP` have ≥1 pattern in `FLAG_CROSSWALK` and each pattern sets its target to `True`. The Cycle-2 HIGH #2 regression guard holds.

**Two BLOCKER findings** target correctness defects:
1. `parse_calendar_month_html` truncates >8-digit `/race/list/{N}/` IDs to 8 digits via `re.search`, silently emitting a wrong `race_day_date`.
2. `_recast_for_storage` swallows `TypeError`/`ValueError` on the merge-dedup path, re-opening the exact dtype-contract failure Cycle-2 HIGH #3 was designed to prevent whenever a same-month re-run hits a non-coercible existing column.

**Warning findings** cover: parser trusts filename as `race_id` without validation; merge-dedup has no column-set equality check (schema drift persists across re-runs); the 1-to-1 integrity check is set-equality rather than cardinality; `_NULL_FINISH_NOTES` surfaces horse-weight sentinels as `finish_note`; URL dedup misses trailing-slash variance; `EntrySchema.popularity` annotation drifts from its normalizer dtype; and `validate_integrity` violations never raise even when they indicate data corruption.

## Critical Issues

### CR-01: Calendar regex silently truncates malformed race-day hrefs

**File:** `src/scraper/enumeration.py:45, 87-102`
**Issue:** `_RACE_DAY_HREF_RE = re.compile(r"/race/list/(\d{8})/?")` is applied with `.search()` on the raw href. Because the regex is not anchored, a malformed href such as `/race/list/2022010512/` (10 digits) matches the leading 8 digits and produces `race_day_date = datetime(2022,1,5)` — a date that does not correspond to the actual segment. Verified by direct regex test:
```
/race/list/2022010512/  -> match '/race/list/20220105', race_day_date = 2022-01-05
```
The trailing `/?` does NOT require end-of-segment, so any >8-digit numeric segment is silently prefix-matched. This corrupts `RaceRef.race_date`, which is the authoritative source for the raw HTML path `{YYYY}/{MM}` and the standard-layer partition key — downstream writes go to the wrong month directory and the wrong YYYYMM partition.

**Fix:** Anchor the regex so the captured 8-digit segment is the FULL digit run. Use a word boundary or reject segments with trailing digits:
```python
# Reject any href where the digit run is not exactly 8 chars.
_RACE_DAY_HREF_RE = re.compile(r"/race/list/(\d{8})(?:/|$)")
# Then in parse_calendar_month_html, _RACE_DAY_HREF_RE.search still works;
# the trailing (?:/|$) ensures \d{8} is followed by / or end-of-string,
# so /race/list/2022010512/ no longer matches.
```
Add a regression test in `tests/scraper/test_enumeration.py` covering `/race/list/2022010512/` → not matched (dropped, with warning).

### CR-02: Merge-dedup dtype contract is silently broken by `_recast_for_storage`

**File:** `src/scraper/normalizer.py:571-598`
**Issue:** The module docstring (Cycle-2 HIGH #3) promises strict dtypes with hard `TypeError` on coercion failure (lines 22-27, 222-227, 232-234). `_build_typed_dataframe` honors this. But the merge-dedup path in `write_partitioned_parquet` reads an existing parquet, concats with new rows, then calls `_recast_for_storage` — which **catches `(TypeError, ValueError)` and `pass`es** (lines 591-597). If a stale column from a prior run (e.g. an `object`-dtype column surviving a previous schema change, or a column where the stored values are genuinely non-coercible) is loaded, the merged frame is written with whatever dtype it landed on, and the strict-dtype guarantee is silently violated. The written parquet then fails to physically match the Kaggle schema that Cycle-2 #3 and Cycle-3 #1 were designed to enforce.

This is the same class of failure the strict path raises on. The merge path MUST raise equivalently — silent best-effort here defeats the entire dtype-contract test surface.

**Fix:** Propagate the exception, or fail the merge and fall back to writing only the new partition (already the existing exception branch's behavior) WITHOUT mixing dtypes:
```python
def _recast_for_storage(df: pd.DataFrame, table_name: str) -> pd.DataFrame:
    schema_map = {"race": RaceSchema, "entry": EntrySchema, "result": ResultSchema}
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
        except (TypeError, ValueError) as e:
            raise TypeError(
                f"_recast_for_storage: column {col!r} in {table_name!r} existing "
                f"parquet cannot be coerced to {target!r} during merge-dedup: {e}"
            ) from e
    return out
```
Callers in `write_partitioned_parquet` already wrap this in a try/except (line 551-557) that falls back to writing the new partition only — that branch becomes the safety net, and the dtype contract is no longer silently broken.

## Warnings

### WR-01: `parse_race_html` trusts filename stem as `race_id` without validation

**File:** `src/scraper/parser.py:743-769`
**Issue:** `race_id = html_path.stem` is used directly as the race dict's `race_id`, joined into every entry/result as `horse_race_id = f"{race_id}{horse_number:02d}"`, and emitted into the race table. There is NO validation that this string is a 12-digit race ID. `fetcher.py:290` validates on write, but the parser is also reachable directly (and from tests using arbitrary fixture filenames like `foo.html`). A misnamed fixture would inject `race_id="foo"` into the race table, then `horse_race_id="foo01"` which fails `_HORSE_RACE_ID_RE.fullmatch` and skips every row — silently producing an empty entries/results list while still emitting a corrupt race row.

**Fix:** Validate at parse entry point and either fail loud or skip:
```python
def parse_race_html(html_path: Path) -> Dict:
    html_path = Path(html_path)
    race_id = html_path.stem
    if not re.fullmatch(r"\d{12}", race_id):
        raise ValueError(
            f"parse_race_html: filename stem {race_id!r} is not a 12-digit race_id "
            f"(file={html_path})"
        )
    ...
```

### WR-02: Merge-dedup has no column-set equality check between existing and new partition

**File:** `src/scraper/normalizer.py:537-557`
**Issue:** When `target_path.exists()`, the code does `pd.concat([existing_df, new_partition_df])` without checking that `set(existing_df.columns) == set(new_partition_df.columns)`. If a prior run wrote with an older schema (extra column, renamed column, dropped column), concat takes the UNION of columns; the merged frame inherits stale columns with NaN for new rows, and `drop_duplicates(keep="last")` may keep a new row whose stale column is NaN. The schema drift then persists across every subsequent same-month re-run, polluting the standard-layer output that Phase 6 joins against Kaggle.

**Fix:** Assert column-set equality before concat, or restrict the merge to the new partition's columns:
```python
if target_path.exists():
    existing_df = pd.read_parquet(target_path, engine="pyarrow")
    if list(existing_df.columns) != list(new_partition_df.columns):
        logger.warning(
            f"write_partitioned_parquet({table_name!r}): existing parquet columns "
            f"{list(existing_df.columns)} != new columns {list(new_partition_df.columns)}; "
            f"writing new partition only (schema drift detected)"
        )
        write_df = new_partition_df
        _atomic_write_parquet(write_df, target_path)
        written.append(target_path)
        continue
    # ... existing merge logic
```

### WR-03: `validate_integrity` check "d" is set-equality, not true 1-to-1 cardinality

**File:** `src/scraper/normalizer.py:308-323`
**Issue:** The docstring claims "entry/result `horse_race_id` are 1-to-1 (set equality)". Set equality is NOT 1-to-1 cardinality. If `entry` has 1 row with `horse_race_id="X"` and `result` has 100 rows all `"X"`, the sets are equal (`{"X"} == {"X"}`) and the check passes — but the tables are wildly unbalanced. The check is partially covered by checks b/c (per-table uniqueness), which would flag the 100 duplicates in result. But if check b/c are skipped (e.g. columns missing) the set-equality check is insufficient.

**Fix:** Compare multisets (Counter), or assert equal length alongside set equality:
```python
from collections import Counter
if Counter(entry_df["horse_race_id"].dropna().tolist()) != Counter(result_df["horse_race_id"].dropna().tolist()):
    msg = "horse_race_id mismatch: entry/result are not 1-to-1 (cardinality differs)"
    violations.append(msg)
    logger.warning(msg)
```
This naturally subsumes set equality and uniqueness in one check.

### WR-04: `_parse_finish_position_cell` surfaces horse-weight sentinels as `finish_note`

**File:** `src/scraper/parser.py:529-566`
**Issue:** The unknown-format branch (line 564-566) returns `(None, cleaned)` — preserving ANY unparseable text as the finish note. This is correct for genuine finish codes, but `計不` and `---` are horse-weight sentinels (see `parse_horse_weight` lines 156-162) that would never legitimately appear in a 着順 cell. If a column-misalignment bug ever feeds a horse-weight cell into `_parse_finish_position_cell`, the parser silently treats it as a finish note rather than failing loudly. This is a defense-in-depth gap — a column-header resolution error in `resolve_columns_by_header` would propagate undetected.

**Fix:** Either narrow the unknown-format branch to known-finish-note characters, or add a sanity check that warns when the surfaced note is not in a known set. At minimum, log loudly:
```python
# Unknown format -- surface as a note, drop position.
logger.warning(
    f"Unparseable 着順 cell: {cleaned!r}; dropping finish_position. "
    f"If this looks like a horse-weight sentinel (計不/---), "
    f"check column-header resolution."
)
return (None, cleaned)
```

### WR-05: Calendar URL dedup misses trailing-slash variance

**File:** `src/scraper/enumeration.py:96-101`
**Issue:** `parse_calendar_month_html` dedupes by the absolutized URL via `urljoin(BASE_URL, href)`. But `urljoin` is href-form-preserving: `/race/list/20220105/` and `/race/list/20220105` (one with trailing slash, one without) produce DIFFERENT URLs:
```
https://db.netkeiba.com/race/list/20220105/
https://db.netkeiba.com/race/list/20220105
```
If the calendar page ever emits both forms for the same day, the day is fetched twice and the underlying races are deduped later by `race_id` (which works) but at the cost of a redundant network round-trip per affected day. Not a correctness bug, but a wasteful double-fetch on a rate-limited scraper.

**Fix:** Normalize trailing slash before dedup:
```python
day_url = urljoin(BASE_URL, href).rstrip("/") + "/"
if day_url in seen_urls:
    continue
seen_urls.add(day_url)
```

### WR-06: `EntrySchema.popularity` annotation drifts from its normalizer dtype

**File:** `src/schemas/entry.py:116-120` vs `src/scraper/normalizer.py:166`
**Issue:** `EntrySchema.popularity` is annotated `Optional[int]` with description "Betting popularity rank (人気)". `SCHEMA_DTYPE_MAP[EntrySchema]["popularity"] = "Float64"` writes nullable float. Kaggle stores popularity as Arrow `double` so the normalizer is correct for the join contract. But the Pydantic annotation lies about the runtime type — any code that calls `EntrySchema(**row).popularity` and expects an int will get a float. The same drift exists for `horse_weight` and `weight_change` (Pydantic says `Optional[int]`, dtype map says `Float64`).

**Fix:** Either update the Pydantic annotations to `Optional[float]` to match the dtype map, or add a comment in the schema flagging the standard-layer dtype override. Given that the schemas are explicitly "type definition only" per D-02 (not used for row validation), the cheaper fix is documentation:
```python
popularity: Optional[int] = Field(
    default=None,
    description=(
        "Betting popularity rank (人気) -- post-race for feature purposes. "
        "NOTE: standard-layer Parquet stores this as Float64 (Kaggle double); "
        "the int annotation is for documentation only."
    ),
    json_schema_extra={"pre_race": False, "table": "entry"},
)
```

### WR-07: `validate_integrity` violations never raise even when they indicate corruption

**File:** `src/scraper/normalizer.py:695-701`
**Issue:** Integrity violations (duplicate `race_id`, duplicate `horse_race_id`, orphan FKs) are logged as warnings and the output is written anyway. The docstring says "the caller decides" — but the only caller is `normalize_to_parquet`, which never decides anything; it just logs. A duplicate `race_id` in the race table means the Phase-6 join produces ambiguous matches against Kaggle. A duplicate `horse_race_id` corrupts the entry/result 1-to-1 join. The current behavior writes silently-corrupt parquet and returns successfully.

**Fix:** For HIGH-severity violations (duplicate primary keys, FK orphans), raise; for soft violations (1-to-1 cardinality mismatch), keep warning. Minimum viable fix:
```python
violations = validate_integrity(race_df, entry_df, result_df)
hard_violations = [v for v in violations if "duplicate" in v or "orphan" in v]
if hard_violations:
    raise ValueError(
        f"normalize_to_parquet: {len(hard_violations)} hard integrity violation(s): "
        f"{hard_violations[:3]}"
    )
```

## Info

### IN-01: `_GRADE_REGEX` in `flag_crosswalk.py` has redundant/unused alternatives

**File:** `src/scraper/flag_crosswalk.py:98-101`
**Issue:** The regex includes both `JGI|JGII|JGIII` AND `JG1|JG2|JG3` AND full-width forms. Because the regex is used only for boolean flag derivation (any match → `graded_stakes=True`), and because `GI` alone already matches as a substring of `JGI`, the explicit `JG*` alternatives are redundant for the boolean purpose. They're not harmful (the boolean result is correct either way), but they add maintenance noise. The parser's `_GRADE_TOKEN_RE` correctly needs them (for token capture). Consider a comment clarifying that `_GRADE_REGEX` is for boolean detection only.

**Fix:** Add a comment, or simplify the regex to `GI|GII|GIII|ＧＩ|ＧＩＩ|ＧＩＩＩ` since the JG variants are subsumed.

### IN-02: `FetcherSession.__exit__` swallows all cleanup exceptions silently

**File:** `src/scraper/fetcher.py:120-149`
**Issue:** Every cleanup step (`page.close()`, `context.close()`, `browser.close()`, `_pw.stop()`) is wrapped in bare `except Exception: pass`. This is intentional (cleanup-must-not-throw) but means a Playwright/Chromium process leak during teardown is invisible. On macOS, an orphaned Chromium process is recoverable, but in a long-running batch it could exhaust resources.

**Fix:** Log at DEBUG level so the leak is at least traceable:
```python
try:
    self._browser.close()
except Exception as e:
    logger.debug(f"FetcherSession.__exit__: browser.close() failed: {e!r}")
```

### IN-03: `fetch_with_retry` method backoff comment is misleading

**File:** `src/scraper/fetcher.py:202-213`
**Issue:** The comment says "Exponential backoff: base RATE_LIMIT_SECONDS * (attempt + 2)" and "attempt 0 -> 2*base, attempt 1 -> 3*base, attempt 2 -> 4*base". This is LINEAR backoff (constant additive increase), not exponential. Not a bug — the behavior is intentional and benign — but the comment misnames it.

**Fix:** Rename to "linear backoff" or "increasing backoff":
```python
# Linear backoff: base * (attempt + 2).
# attempt 0 -> 2*base, attempt 1 -> 3*base, attempt 2 -> 4*base.
```

### IN-04: `_RACE_HREF_RE` in `enumeration.py` matches any-digit race IDs but tests only 12-digit path

**File:** `src/scraper/enumeration.py:54`
**Issue:** `_RACE_HREF_RE = re.compile(r"/race/(\d+)/?")` deliberately captures any-length digit run so malformed IDs (10-digit, 13-digit) "enter the validation branch" (per the comment on line 47-53). This is by design. However, the regex is greedy: for a href like `/race/123456789012/results/` (note the `/results/` suffix), the trailing `/?` allows either a slash or end-of-string, so this matches as `123456789012` (12 digits). Then `_RACE_ID_RE.fullmatch` accepts it. Not a bug per se, but worth a test fixture. The current design is sound; flagging only as documentation.

**Fix:** No code change needed. Add a test fixture for the `/race/{12digit}/results/` href shape if defensive coverage is desired.

---

_Reviewed: 2026-06-14T10:55:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
