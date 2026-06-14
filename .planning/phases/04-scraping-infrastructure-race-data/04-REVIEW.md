---
phase: 04-scraping-infrastructure-race-data
reviewed: 2026-06-14T11:30:00Z
depth: deep
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

# Phase 04: Code Review Report (DEEP)

**Reviewed:** 2026-06-14T11:30:00Z
**Depth:** deep
**Files Reviewed:** 9 production source files + 8 test files + 5 HTML fixtures + 4 cross-reference schemas
**Status:** issues_found

## Summary

Deep cross-file review of the netkeiba scraping infrastructure (9 `src/scraper/*.py` files, ~2.7k LOC), tracing the full pipeline `enumerate_races -> fetch_race_html -> parse_race_html -> normalize_to_parquet` and the `run_scrape` orchestration. Cross-referenced against `src/pipeline/column_mapping.py`, `src/schemas/{race,entry,result}.py`, and 5 golden HTML fixtures to verify the standard-layer dtype/schema contract and the Phase-6 Kaggle join compatibility.

**Prior standard-depth review re-verification:** Both Critical findings (CR-01 calendar regex truncation, CR-02 merge-dedup dtype swallow) **still hold** against current code. All 7 Warnings and 4 Infos re-verified and carried forward. No prior finding was resolved.

**Deep value-add:** Confirmed the dtype-contract leak path end-to-end (CR-02 traces from `_recast_for_storage` through `write_partitioned_parquet` to the written Parquet that Phase 6 joins against Kaggle). Verified the partition-key derivation chain (`race_ref.race_date` -> `{YYYY}/{MM}` raw path -> `partition_map` -> `{YYYYMM}` standard partition) is internally consistent and has no path-traversal surface. Confirmed no post-race field (finish_position, finish_time, margin, corners, last_3f, prize_money) can reach RaceSchema/EntrySchema pre-race fields. Confirmed `popularity`/`win_odds` are correctly tagged `pre_race=False` (reserved for EV, never features).

**Leakage posture is sound.** RaceSchema/EntrySchema carry only pre-race fields; ResultSchema cleanly isolates all post-race data. The obstacle filter (`normalize_to_parquet` lines 676-693) correctly propagates from race to entry/result tables with a `notna()` guard against the `pd.NA == "障害"` propagation trap.

**Flag crosswalk is exhaustive.** Programmatically verified all 13 unique `race_flag_*` targets in `KAGGLE_COLUMN_MAP` have >=1 pattern in `FLAG_CROSSWALK` and each pattern sets its target to `True`. The Cycle-2 HIGH #2 regression guard holds (also enforced by `test_crosswalk_covers_all_kaggle_flag_targets`).

**Two BLOCKER findings** (both carried from prior review, still unresolved):
1. `parse_calendar_month_html` regex `_RACE_DAY_HREF_RE` truncates >8-digit `/race/list/{N}/` hrefs via unanchored `.search()`, silently emitting a wrong `race_day_date` (verified by direct regex test).
2. `_recast_for_storage` swallows `(TypeError, ValueError)` on the merge-dedup path, silently breaking the strict-dtype contract (Cycle-2 HIGH #3) when a same-month re-run hits a non-coercible existing column.

**Test-suite assessment:** The test suite is thorough on happy paths (5 golden fixtures, full-chain e2e, dtype-fidelity checks). However, three test-quality gaps were identified: the merge-dedup test does not exercise the dtype-swallow path (CR-02 is uncaught); the integrity-validation tests never assert that violations RAISE (WR-07 is uncaught); and the full-chain e2e pre-saves all fixture HTML, bypassing the real transport-based race fetch for the happy path (the `test_full_chain_handles_failed_fetch` test covers the None path but not a successful transport fetch without pre-save).

## Critical Issues

### CR-01: Calendar regex silently truncates malformed race-day hrefs (carried from standard review, STILL UNRESOLVED)

**File:** `src/scraper/enumeration.py:45, 87-90`
**Status:** Carried from prior standard review. Verified still present in current code. No regression test added.
**Issue:** `_RACE_DAY_HREF_RE = re.compile(r"/race/list/(\d{8})/?")` is applied with `.search()` on the raw href (line 87). Because the regex is not anchored to require the 8-digit segment to be the FULL digit run, a malformed href with MORE than 8 digits matches the leading 8 digits. Verified by direct regex test:

```
/race/list/2022010512/   -> match group '20220105'  (10-digit href truncated)
/race/list/20220105123/  -> match group '20220105'  (11-digit href truncated)
/race/list/20220105xyz/  -> match group '20220105'  (8 digits + suffix)
```

The trailing `/?` matches an OPTIONAL slash but does NOT require end-of-segment, so any >8-digit numeric prefix is silently matched. The resulting `race_day_date` (e.g., `2022-01-05` for a `2022010512` href) does not correspond to the actual segment. This corrupts `RaceRef.race_date`, which is the authoritative source for:
- The raw HTML path `{YYYY}/{MM}` (fetcher.py:297-300) -> HTML written to the wrong month directory.
- The standard-layer partition key `{YYYYMM}` (normalizer.py:392-396) -> Parquet written to the wrong partition.
- The Phase-6 join contract -> races silently land in a partition that does not match their calendar date.

This is a data-corruption defect: the corruption is silent (no warning logged) and propagates to both the raw and standard layers.

**Fix:** Anchor the regex so the captured 8-digit segment is the FULL digit run. The fix uses a trailing `(?:/|$)` to require the 8 digits be followed by a slash or end-of-string:
```python
# Reject any href where the digit run is not exactly 8 chars.
_RACE_DAY_HREF_RE = re.compile(r"/race/list/(\d{8})(?:/|$)")
```
Verified against the test vectors:
```
/race/list/2022010512/   -> None  (correctly rejected)
/race/list/20220105123/  -> None  (correctly rejected)
/race/list/20220105/     -> '20220105'  (valid)
/race/list/20220105      -> '20220105'  (valid, no trailing slash)
/race/list/20220105xyz/  -> None  (correctly rejected)
```
Add a regression test in `tests/scraper/test_enumeration.py`:
```python
def test_rejects_long_digit_run_in_day_href(self) -> None:
    """A >8-digit /race/list/ segment is dropped, NOT prefix-truncated."""
    html = '<a href="/race/list/2022010512/">bad</a>'
    result = parse_calendar_month_html(html)
    assert result == [], f"expected empty, got {result}"
```

### CR-02: Merge-dedup dtype contract silently broken by `_recast_for_storage` (carried from standard review, STILL UNRESOLVED)

**File:** `src/scraper/normalizer.py:571-598`
**Status:** Carried from prior standard review. Verified still present. No test exercises this failure path.
**Issue:** The module docstring (lines 22-27, 222-234) and `_build_typed_dataframe` enforce strict dtypes with hard `TypeError` on coercion failure (Cycle-2 HIGH #3). But the merge-dedup path in `write_partitioned_parquet` reads an existing parquet, concats with new rows, then calls `_recast_for_storage` -- which **catches `(TypeError, ValueError)` and `pass`es** (lines 591-597):

```python
try:
    out[col] = out[col].astype(target)
except (TypeError, ValueError):
    # Best-effort recast: leave as-is if the column cannot be coerced
    pass
```

Deep-traced failure path: if a stale column from a prior run survives a schema change (e.g., an `object`-dtype column from an older writer, or a column where stored values are genuinely non-coercible like a `finish_position` accidentally written as `"DNF"` strings), `_recast_for_storage` silently leaves the column as-is. The merged frame is then written with whatever dtype it landed on, and the strict-dtype guarantee is violated. The written Parquet then fails to physically match the Kaggle schema that Cycle-2 #3 and Cycle-3 #1 were designed to enforce.

This is the SAME class of failure the strict path (`_build_typed_dataframe`) raises on. The merge path MUST raise equivalently -- silent best-effort here defeats the entire dtype-contract test surface. Concrete demonstration:
```python
df_bad = pd.DataFrame({"finish_position": ["abc", "def"]})
df_bad["finish_position"].astype("Int64")  # raises ValueError
# _recast_for_storage catches this -> column stays object/string
# written parquet has finish_position as string, not Int64
```

**Fix:** Propagate the exception so the existing `except Exception` wrapper at lines 551-557 catches it and falls back to writing only the new partition (which IS correctly typed):
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
The caller at lines 551-557 already wraps this in `try/except Exception` and falls back to `write_df = new_partition_df` -- that branch becomes the safety net, and the dtype contract is no longer silently broken.

Add a regression test:
```python
def test_merge_dedup_raises_on_non_coercible_existing(self, tmp_standard_dir):
    """CR-02: a non-coercible existing column triggers fallback to new-only write."""
    target_dir = tmp_standard_dir / "scraped" / "202201"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / "result.parquet"
    # Write a bad existing parquet with string finish_position.
    bad_df = pd.DataFrame({
        "horse_race_id": ["20220105010101"], "race_id": ["202201050101"],
        "finish_position": ["not_a_number"], "finish_note": [None],
        "finish_time": [None], "margin": [None],
        "corner_1": [None], "corner_2": [None], "corner_3": [None], "corner_4": [None],
        "last_3f": [None], "prize_money": [None],
    })
    bad_df.to_parquet(target_path, engine="pyarrow", index=False)
    # A subsequent write should NOT silently merge the bad dtype.
    # It should fall back to writing the new (correctly-typed) partition only.
    new_rows = [/* valid result row */]
    new_df = _build_typed_dataframe(new_rows, ResultSchema)
    written = write_partitioned_parquet("result", new_df, tmp_standard_dir,
                                        partition_map={"202201050101": datetime.date(2022,1,5)},
                                        primary_key="horse_race_id")
    back = pd.read_parquet(target_path, engine="pyarrow")
    # The bad row was dropped; only the new row survives with correct dtype.
    assert "not_a_number" not in back["finish_position"].tolist()
    assert str(back["finish_position"].dtype) in {"Int64", "int64"}
```

## Warnings

### WR-01: `parse_race_html` trusts filename stem as `race_id` without validation (carried, STILL UNRESOLVED)

**File:** `src/scraper/parser.py:743, 761`
**Status:** Carried from prior review. Verified still present.
**Issue:** `race_id = html_path.stem` (line 761) is used directly as the race dict's `race_id`, joined into every entry/result as `horse_race_id = f"{race_id}{horse_number:02d}"`. There is NO validation that this string is a 12-digit race ID. `fetcher.py:290` validates on write, but the parser is reachable directly (tests, manual use). A misnamed fixture (e.g., `foo.html`) would inject `race_id="foo"`, then `horse_race_id="foo01"` which fails `_HORSE_RACE_ID_RE.fullmatch` (line 637) and skips every row -- silently producing an empty entries/results list while still emitting a corrupt race row with `race_id="foo"`.

**Fix:** Validate at parse entry point:
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

### WR-02: Merge-dedup has no column-set equality check between existing and new partition (carried, STILL UNRESOLVED)

**File:** `src/scraper/normalizer.py:537-557`
**Status:** Carried from prior review. Verified still present. Concrete demonstration confirms the issue.
**Issue:** When `target_path.exists()`, the code does `pd.concat([existing_df, new_partition_df])` without checking `set(existing_df.columns) == set(new_partition_df.columns)`. Concrete demonstration:
```
existing: race_id, race_date, stale_col (3 columns)
new:      race_id, race_date (2 columns)
concat -> union: race_id, race_date, stale_col (3 columns, stale_col=NaN for new rows)
drop_duplicates(keep="last") -> keeps new rows, stale_col=NaN survives
```
If a prior run wrote with an older schema (extra/dropped/renamed column), concat takes the UNION of columns; the merged frame inherits stale columns with NaN for new rows. `_recast_for_storage` only iterates `SCHEMA_DTYPE_MAP` (which excludes stale columns), so the stale column survives the recast and is written to the output Parquet. The schema drift then persists across every subsequent same-month re-run, polluting the standard-layer output that Phase 6 joins against Kaggle.

**Fix:** Assert column-set equality before concat, or restrict the merge to the schema columns:
```python
if target_path.exists():
    existing_df = pd.read_parquet(target_path, engine="pyarrow")
    schema_cols = list(SCHEMA_DTYPE_MAP[
        {"race": RaceSchema, "entry": EntrySchema, "result": ResultSchema}[table_name]
    ].keys())
    if list(existing_df.columns) != schema_cols:
        logger.warning(
            f"write_partitioned_parquet({table_name!r}): existing parquet columns "
            f"{list(existing_df.columns)} != schema columns {schema_cols}; "
            f"writing new partition only (schema drift detected)"
        )
        write_df = new_partition_df
        _atomic_write_parquet(write_df, target_path)
        written.append(target_path)
        continue
    # ... existing merge logic
```

### WR-03: `validate_integrity` check "d" is set-equality, not true 1-to-1 cardinality (carried, STILL UNRESOLVED)

**File:** `src/scraper/normalizer.py:308-323`
**Status:** Carried from prior review. Verified still present.
**Issue:** The docstring claims "entry/result `horse_race_id` are 1-to-1 (set equality)". Set equality is NOT 1-to-1 cardinality. If `entry` has 1 row with `horse_race_id="X"` and `result` has 100 rows all `"X"`, the sets are equal (`{"X"} == {"X"}`) and the check passes. The per-table uniqueness checks (b/c at lines 293-306) partially cover this, but if those checks are skipped (e.g., column missing), set-equality alone is insufficient.

**Fix:** Compare multisets (Counter), which naturally subsumes set equality and uniqueness:
```python
from collections import Counter
entry_hids = Counter(entry_df["horse_race_id"].dropna().tolist())
result_hids = Counter(result_df["horse_race_id"].dropna().tolist())
if entry_hids != result_hids:
    msg = "horse_race_id mismatch: entry/result are not 1-to-1 (cardinality differs)"
    violations.append(msg)
    logger.warning(msg)
```

### WR-04: `_parse_finish_position_cell` surfaces horse-weight sentinels as `finish_note` (carried, STILL UNRESOLVED)

**File:** `src/scraper/parser.py:564-566`
**Status:** Carried from prior review. Verified still present. Note: a `logger.warning` WAS added at line 565 (the prior report said it was missing; it now exists), so this is partially mitigated but the defense-in-depth gap remains.
**Issue:** The unknown-format branch returns `(None, cleaned)` -- preserving ANY unparseable text as the finish note. `計不` and `---` are horse-weight sentinels (see `parse_horse_weight` lines 156-162) that would never legitimately appear in a 着順 cell. If a column-header resolution error in `resolve_columns_by_header` feeds a horse-weight cell into `_parse_finish_position_cell`, the parser silently treats it as a finish note rather than failing loudly.

**Fix:** Add a sanity check that warns when the surfaced note is not in a known finish-note set:
```python
KNOWN_FINISH_NOTES = _NULL_FINISH_NOTES | {"降"}
if cleaned not in KNOWN_FINISH_NOTES:
    logger.warning(
        f"Unparseable 着順 cell {cleaned!r} is not a known finish note; "
        f"if this looks like a horse-weight sentinel (計不/---), "
        f"check column-header resolution."
    )
return (None, cleaned)
```

### WR-05: Calendar URL dedup misses trailing-slash variance (carried, STILL UNRESOLVED)

**File:** `src/scraper/enumeration.py:96-101`
**Status:** Carried from prior review. Verified still present.
**Issue:** `parse_calendar_month_html` dedupes by `urljoin(BASE_URL, href)`. `urljoin` is href-form-preserving: `/race/list/20220105/` and `/race/list/20220105` produce DIFFERENT URLs. If the calendar page emits both forms for the same day, the day is fetched twice. Not a correctness bug (races dedup later by `race_id`), but a wasteful double-fetch on a rate-limited scraper.

**Fix:** Normalize trailing slash before dedup:
```python
day_url = urljoin(BASE_URL, href).rstrip("/") + "/"
if day_url in seen_urls:
    continue
seen_urls.add(day_url)
```

### WR-06: `EntrySchema.popularity` annotation drifts from its normalizer dtype (carried, STILL UNRESOLVED)

**File:** `src/schemas/entry.py:116-120` vs `src/scraper/normalizer.py:166`
**Status:** Carried from prior review. Verified still present.
**Issue:** `EntrySchema.popularity` is annotated `Optional[int]`, but `SCHEMA_DTYPE_MAP[EntrySchema]["popularity"] = "Float64"` writes nullable float. Kaggle stores popularity as Arrow `double`, so the normalizer is correct for the join contract. But the Pydantic annotation lies about the runtime type. Same drift exists for `horse_weight` and `weight_change` (Pydantic `Optional[int]`, dtype map `Float64`).

**Fix:** Update the Pydantic annotations to `Optional[float]`, or add a docstring note flagging the standard-layer dtype override. Given the schemas are explicitly "type definition only" per D-02, the cheaper fix is documentation:
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

### WR-07: `validate_integrity` violations never raise even when they indicate corruption (carried, STILL UNRESOLVED)

**File:** `src/scraper/normalizer.py:695-701`
**Status:** Carried from prior review. Verified still present. Test suite confirms violations are never asserted to raise (`test_detects_duplicate_race_id` etc. only check the return value).
**Issue:** Integrity violations (duplicate `race_id`, duplicate `horse_race_id`, orphan FKs) are logged as warnings and the output is written anyway. A duplicate `race_id` in the race table means the Phase-6 join produces ambiguous matches against Kaggle. The current behavior writes silently-corrupt Parquet and returns successfully.

**Fix:** For HIGH-severity violations (duplicate primary keys, FK orphans), raise:
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

### IN-01: `_GRADE_REGEX` in `flag_crosswalk.py` has redundant alternatives (carried, STILL PRESENT)

**File:** `src/scraper/flag_crosswalk.py:98-101`
**Status:** Carried. Verified still present.
**Issue:** The regex includes both `JGI|JGII|JGIII` AND `JG1|JG2|JG3` AND full-width forms. Because it's used only for boolean flag derivation (any match -> `graded_stakes=True`), and `GI` alone matches as a substring of `JGI`, the explicit `JG*` alternatives are redundant for the boolean purpose. Verified: `'JGIII' -> matched: 'JGI'` (substring match), but the boolean result is correct either way. Not harmful, but adds maintenance noise.

**Fix:** Add a comment clarifying `_GRADE_REGEX` is for boolean detection only, or simplify to `GI|GII|GIII|ＧＩ|ＧＩＩ|ＧＩＩＩ` since the JG variants are subsumed.

### IN-02: `FetcherSession.__exit__` swallows all cleanup exceptions silently (carried, STILL PRESENT)

**File:** `src/scraper/fetcher.py:120-149`
**Status:** Carried. Verified still present.
**Issue:** Every cleanup step (`page.close()`, `context.close()`, `browser.close()`, `_pw.stop()`) is wrapped in bare `except Exception: pass`. Intentional (cleanup-must-not-throw), but a Playwright/Chromium process leak during teardown is invisible. On macOS, an orphaned Chromium process is recoverable, but in a long-running batch it could exhaust resources.

**Fix:** Log at DEBUG level:
```python
try:
    self._browser.close()
except Exception as e:
    logger.debug(f"FetcherSession.__exit__: browser.close() failed: {e!r}")
```

### IN-03: `fetch_with_retry` comment says "Exponential backoff" but the formula is linear (carried, STILL PRESENT)

**File:** `src/scraper/fetcher.py:203-205`
**Status:** Carried. Verified still present.
**Issue:** The comment says "Exponential backoff: base RATE_LIMIT_SECONDS * (attempt + 2)". This is LINEAR backoff (constant additive increase: 2*base, 3*base, 4*base), not exponential (which would be base * 2^attempt). Not a bug -- the behavior is intentional and benign -- but the comment misnames it.

**Fix:** Rename to "linear backoff":
```python
# Linear backoff: base * (attempt + 2).
# attempt 0 -> 2*base, attempt 1 -> 3*base, attempt 2 -> 4*base.
```

### IN-04: `_RACE_HREF_RE` matches any-digit race IDs by design (carried, DOCUMENTATION ONLY)

**File:** `src/scraper/enumeration.py:54`
**Status:** Carried. Verified still present and intentional.
**Issue:** `_RACE_HREF_RE = re.compile(r"/race/(\d+)/?")` deliberately captures any-length digit run so malformed IDs "enter the validation branch" (per comment lines 47-53). This is by design -- `_RACE_ID_RE.fullmatch` at line 138 then rejects non-12-digit values. The regex is greedy: for a href like `/race/123456789012/results/`, the trailing `/?` allows either a slash or end-of-string, so it matches `123456789012`. Not a bug.

**Fix:** No code change needed. Add a test fixture for the `/race/{12digit}/results/` href shape if defensive coverage is desired.

---

## Deep Cross-File Analysis (NEW context not in prior review)

### Data-flow tracing: `race_id` / `horse_race_id` / partition keys

Traced the full key-derivation chain across all 9 files:

1. **`race_id` (12-digit):** `parse_race_day_html` (enumeration.py:137) -> `RaceRef.race_id` -> `fetch_race_html` (fetcher.py:290, validated) -> filename stem -> `parse_race_html` (parser.py:761, NOT validated -- see WR-01) -> `race["race_id"]` -> `_build_typed_dataframe` (normalizer.py:235) -> `race_df["race_id"]` (string dtype) -> `partition_map` key. **Gap:** WR-01 (parser does not validate stem).

2. **`horse_race_id` (14-digit):** `parse_race_html` -> `f"{race_id}{horse_number:02d}"` (parser.py:636) -> `_HORSE_RACE_ID_RE.fullmatch` (parser.py:637, validated) -> `entry["horse_race_id"]` / `result["horse_race_id"]`. **Sound:** validation present at construction.

3. **`race_day_date` -> raw path `{YYYY}/{MM}`:** `parse_calendar_month_html` (enumeration.py:92) -> `RaceRef.race_date` -> `fetch_race_html` (fetcher.py:297-298) -> `out_dir = raw_dir / year / month`. **Gap:** CR-01 (date can be corrupted by regex truncation upstream).

4. **`race_date` -> partition key `{YYYYMM}`:** `normalize_to_parquet` -> `partition_map[race_id] = parsed_date` (normalizer.py:713) -> `write_partitioned_parquet` -> `_partition_key_from_date` (normalizer.py:396). **Sound** (given CR-01 is fixed upstream).

**Path-traversal analysis:** `race_id` is validated as `\d{12}` (fetcher.py:290) before path construction, so no `../` injection is possible. `race_date` is a `datetime.date` (typed dataclass field), so `year`/`month` are bounded ints. No SSRF/path-traversal surface found in the filesystem path derivation. The outbound HTTPS URL `f"https://db.netkeiba.com/race/{race_ref.race_id}/"` (fetcher.py:308) is also bounded by the 12-digit validation. **No security vulnerability found.**

### Schema/dtype contract verification

Verified `SCHEMA_DTYPE_MAP` (normalizer.py:94-191) against `RaceSchema`/`EntrySchema`/`ResultSchema` field sets:
- All 3 schemas' `model_fields` keys exactly match their `SCHEMA_DTYPE_MAP` entries (also enforced by `test_dtype_map_covers_all_schema_fields`).
- `finish_position` -> `Int64` (Cycle-2 #3). Corner columns -> `Float64` (Cycle-3 #1). `popularity` -> `Float64` (matches Kaggle double). All correct.
- **Leakage check:** No post-race field (`finish_position`, `finish_time`, `margin`, `corner_1..4`, `last_3f`, `prize_money`) appears in `RaceSchema` or `EntrySchema`. `popularity`/`win_odds` are in `EntrySchema` with `pre_race=False` (correctly reserved for EV). **No leakage.**

### Concurrency/lifecycle

- `FetcherSession` is a context manager with nested try/finally in `__exit__` (fetcher.py:120-149). A partial `__enter__` failure (e.g., `new_page()` raises after `sync_playwright().start()`) is handled: `self._page` is None -> skip `page.close()`; `self._pw` is not None -> `_pw.stop()` runs. **Sound.**
- `run_scrape` live mode opens exactly ONE `FetcherSession` per run (orchestrator.py:133), shared across enumeration and race fetching via `make_fetch_html_callable`. Verified by `test_single_session_per_run`. **Sound.**
- Exception flow when `fetch_race_html` returns None: `_fetch_and_parse` logs and continues (orchestrator.py:208-213). Other races proceed. Verified by `test_skips_failed_fetch` and `test_full_chain_handles_failed_fetch`. **Sound.**

### Test-suite gaps (NEW deep observations)

1. **CR-02 uncaught:** `test_same_month_merge_dedup_preserves_sentinel` (test_normalizer.py:586-620) pre-seeds a CORRECTLY-TYPED sentinel. No test seeds a non-coercible existing column to exercise the `_recast_for_storage` swallow path. The dtype contract can be silently broken without any test failing.

2. **WR-07 uncaught:** Integrity tests (`test_detects_duplicate_race_id` etc.) only assert that violations appear in the return value. No test asserts that `normalize_to_parquet` RAISES on hard violations. The "caller decides" contract has no caller that decides.

3. **Full-chain e2e happy path bypasses transport:** `test_full_chain_end_to_end` (test_end_to_end.py:275-369) pre-saves all fixture HTML via `_presave_fixture_raw_html`, so `fetch_race_html`'s SCRP-05 dedup short-circuits BEFORE the transport is consulted. The only test that exercises the transport for race fetching is `test_full_chain_handles_failed_fetch` (None path). A successful transport-based race fetch (without pre-save) is untested. This means a bug in the `fetch_callable` success path (e.g., `detect_block_page` rejecting valid transport HTML) could go undetected.

---

_Reviewed: 2026-06-14T11:30:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
