---
phase: 04-scraping-infrastructure-race-data
fixed_at: 2026-06-14T12:00:00Z
review_path: .planning/phases/04-scraping-infrastructure-race-data/04-REVIEW.md
iteration: 1
findings_in_scope: 9
fixed: 9
skipped: 0
status: all_fixed
---

# Phase 04: Code Review Fix Report

**Fixed at:** 2026-06-14T12:00:00Z
**Source review:** `.planning/phases/04-scraping-infrastructure-race-data/04-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 9 (2 Critical + 7 Warning; Info findings IN-01..IN-04 excluded per `fix_scope: critical_warning`)
- Fixed: 9
- Skipped: 0

All 9 in-scope findings were applied as targeted, minimal edits matching the
surrounding code style. Each fix was committed atomically (one commit per
finding) with the regression tests the REVIEW.md "Fix" sections called for.
The fixes collectively add 11 new tests. No source files were left in a broken
state; no deferred lint items (see `deferred-items.md`) were touched.

## Fixed Issues

### CR-01: Calendar regex silently truncates malformed race-day hrefs

**Files modified:** `src/scraper/enumeration.py`, `tests/scraper/test_enumeration.py`
**Commit:** `8bc81d0`
**Applied fix:** Anchored `_RACE_DAY_HREF_RE` with a trailing `(?:/|$)` so the
captured 8-digit run must be followed by `/` or end-of-string. A malformed
`>8`-digit href (`/race/list/2022010512/`) is now REJECTED rather than
prefix-truncated to `20220105`. Added `test_rejects_long_digit_run_in_day_href`
covering 10-digit, 11-digit, and 8-digits-plus-suffix rejection vectors plus
sanity checks that valid 8-digit hrefs (with and without trailing slash) still
match.

### CR-02: Merge-dedup dtype contract silently broken by `_recast_for_storage`

**Files modified:** `src/scraper/normalizer.py`, `tests/scraper/test_normalizer.py`
**Commit:** `8b639e9`
**Applied fix:** `_recast_for_storage` now re-raises `(TypeError, ValueError)`
as `TypeError` instead of swallowing with `pass`. The caller in
`write_partitioned_parquet` already wraps this in `try/except Exception` and
falls back to writing only the new (correctly-typed) partition -- that becomes
the safety net, and the strict-dtype contract is no longer silently broken.
Added `test_merge_dedup_falls_back_when_existing_column_not_coercible` that
pre-seeds a non-coercible `finish_position` and verifies the fallback drops the
bad row while preserving the strict `Int64` dtype on the surviving new row.

### WR-01: `parse_race_html` trusts filename stem as `race_id` without validation

**Files modified:** `src/scraper/parser.py`, `tests/scraper/test_parser.py`
**Commit:** `2547736`
**Applied fix:** `parse_race_html` now validates the filename stem with
`re.fullmatch(r"\d{12}", race_id)` at entry; a non-12-digit stem raises
`ValueError` with a debuggable message. This mirrors `fetcher.py:290`'s
validation-on-write and closes the direct-caller gap. Added
`TestParseRaceHtmlFilenameValidation` (4 tests) covering non-numeric,
too-short, too-long, and valid 12-digit stems.

### WR-02: Merge-dedup has no column-set equality check

**Files modified:** `src/scraper/normalizer.py`, `tests/scraper/test_normalizer.py`
**Commit:** `2637e6c`
**Applied fix:** `write_partitioned_parquet` now compares
`list(existing_df.columns)` vs `list(new_partition_df.columns)` before the
merge. On mismatch (schema drift from a prior run), it logs a warning and
writes ONLY the new (correctly-typed) partition. This prevents a stale column
from surviving the recast and polluting the standard layer. Added
`test_merge_dedup_rejects_column_drift` that pre-seeds a race partition with
an extra `stale_col` and verifies the stale column does NOT survive.

### WR-03: `validate_integrity` check "d" is set-equality, not true 1-to-1 cardinality

**Files modified:** `src/scraper/normalizer.py`, `tests/scraper/test_normalizer.py`
**Commit:** `46ec3e6`
**Applied fix:** Replaced the set-equality comparison in check (d) with a
`Counter` (multiset) comparison, which naturally subsumes set equality AND
per-table uniqueness. The diagnostic now also surfaces `count-mismatch` for
keys present in both tables but with different counts. Added
`test_detects_entry_result_cardinality_mismatch` covering the case the
pre-existing set-equality would have missed (1 row in entry vs 100 rows in
result, all the same id).

### WR-04: `_parse_finish_position_cell` surfaces horse-weight sentinels as `finish_note`

**Files modified:** `src/scraper/parser.py`
**Commit:** `0ae0df6`
**Applied fix:** The primary mitigation (warning log on unparseable cells)
already existed. Added a `_KNOWN_FINISH_NOTES` frozenset (`_NULL_FINISH_NOTES`
union `{"降"}`) and a defense-in-depth check: if the surfaced `finish_note` is
NOT in this set, emit an additional warning naming the suspicious value and
pointing at column-header resolution (so a horse-weight sentinel like `計不` /
`---` fed in by a header-resolution bug is visible). Known finish notes do not
trigger the secondary warning. Verified manually that `計不` triggers the
warning and `中`/`取`/`降` do not.

### WR-05: Calendar URL dedup misses trailing-slash variance

**Files modified:** `src/scraper/enumeration.py`, `tests/scraper/test_enumeration.py`
**Commit:** `78f0cfb`
**Applied fix:** `parse_calendar_month_html` now normalizes the trailing slash
via `.rstrip("/") + "/"` before dedup, so the same calendar day emitted in
both forms (`/race/list/20220105/` and `/race/list/20220105`) collapses to a
single canonical URL. Both forms resolve to the same netkeiba page, so
canonicalizing on the trailing-slash form is safe. Added
`test_deduplicates_trailing_slash_variance`.

### WR-06: `EntrySchema.popularity` annotation drifts from its normalizer dtype

**Files modified:** `src/schemas/entry.py`
**Commit:** `40e17af`
**Applied fix:** Documentation-only. Added a `NOTE (WR-06)` to the
descriptions of `popularity`, `horse_weight`, and `weight_change` flagging
that the standard-layer Parquet stores these as `Float64` (Kaggle double) per
`SCHEMA_DTYPE_MAP[EntrySchema]`, and that the `int` annotation is
documentation only and does NOT change the runtime dtype. Per the REVIEW.md
guidance, the runtime dtype map was NOT changed (it is correct for the join
contract). No behavior change.

### WR-07: `validate_integrity` violations never raise even when they indicate corruption

**Files modified:** `src/scraper/normalizer.py`, `tests/scraper/test_normalizer.py`
**Commit:** `62443b0`
**Applied fix:** `normalize_to_parquet` now classifies violations as HARD
(`"duplicate" in v or "orphan" in v` per the REVIEW.md fix sketch) vs SOFT.
HARD violations raise `ValueError` (refusing to write corrupt Parquet); SOFT
violations remain warnings. Added `TestHardIntegrityViolationsRaise` (2 tests)
asserting `normalize_to_parquet` raises on a duplicate `race_id` and on an
orphan entry `race_id`. This is flagged as `requires human verification` for
logic correctness -- the classification criteria (the `"duplicate"`/`"orphan"`
substring match) follow the REVIEW.md sketch literally; confirm the soft/hard
boundary matches intent.

## Skipped Issues

None.

## Verification

All verification ran inside the isolated worktree `/tmp/sv-04-reviewfix-pdqUI3`
on branch `gsd-reviewfix/04-32806`. Commands and results:

### Test suite (full scraper suite, final run after all 9 fixes)

```
python3 -m pytest tests/scraper/ -q
  => 205 passed, 4 skipped, 1 failed in 9.71s
```

The single failure is `TestCycle2RegressionGuards::test_kaggle_physical_type_equality_for_corners`,
which is a PRE-EXISTING environment failure: it requires
`data/standard/result.parquet` (a Kaggle-derived file) that does not exist in
this worktree. This failure was present in the BASELINE (before any fix) and
is NOT caused by any of the 9 fixes. Confirmed baseline:
`194 passed, 4 skipped, 1 failed` before fixes; `205 passed, 4 skipped, 1
failed` after (the +11 passed are the new regression tests; the same 1
pre-existing failure and 4 skips remain unchanged).

Per-finding test runs (all green):

- CR-01: `pytest tests/scraper/test_enumeration.py -q` => 20 passed (was 19; +1 new)
- CR-02: `pytest tests/scraper/test_normalizer.py::TestPartitionedOutput::test_merge_dedup_falls_back_when_existing_column_not_coercible` => 1 passed
- WR-01: `pytest tests/scraper/test_parser.py::TestParseRaceHtmlFilenameValidation -q` => 4 passed
- WR-02: `pytest tests/scraper/test_normalizer.py::TestPartitionedOutput::test_merge_dedup_rejects_column_drift -q` => 1 passed
- WR-03: `pytest tests/scraper/test_normalizer.py::TestIntegrityValidation -q` => 6 passed (was 5; +1 new)
- WR-04: `pytest tests/scraper/test_parser.py -q` => 94 passed (unchanged count; WR-04 adds a defense-in-depth warning, not a new test)
- WR-05: `pytest tests/scraper/test_enumeration.py -q` => 20 passed (was 19; +1 new)
- WR-06: `pytest tests/schemas/ -q` => 77 passed (documentation-only; no new tests)
- WR-07: `pytest tests/scraper/test_normalizer.py::TestHardIntegrityViolationsRaise -q` => 2 passed

Downstream-consumer check (WR-05 changed the yielded URL form):
`pytest tests/scraper/test_end_to_end.py tests/scraper/test_orchestrator.py -q`
=> 15 passed, 4 skipped (no regression).

### Lint (ruff)

```
python3 -m ruff check src/scraper/enumeration.py src/scraper/normalizer.py src/scraper/parser.py src/schemas/entry.py
  => All checks passed!

python3 -m ruff check tests/scraper/test_enumeration.py tests/scraper/test_normalizer.py tests/scraper/test_parser.py
  => Found 4 errors.
```

The 4 test-file errors are ALL pre-existing deferred items documented in
`deferred-items.md` (F401 `pytest`, F821 `Callable`, F401 `typing.Callable`,
F841 `bad_day_url` in `test_enumeration.py`). None are in code added by these
fixes. Per the SCOPE BOUNDARY rule, these deferred items were NOT touched. The
9 fixes introduced ZERO new ruff errors.

### Manual verification (WR-04)

Manually verified the defense-in-depth warning fires when a horse-weight
sentinel (`計不`) is fed into `_parse_finish_position_cell`, and does NOT fire
for known finish notes (`中`/`取`/`失`/`除`/`再`/`降`).

### Notes on logic-class fixes (per verification_strategy)

- **CR-02, WR-02, WR-07** involve control-flow / logic decisions (re-raise vs
  swallow, drift detection, hard-vs-soft classification). Tier 1 + Tier 2
  verification (re-read + ruff + targeted regression tests) passed. Flagged
  for human verification of the soft/hard boundary and the fallback semantics
  per the `logic bug limitation` rule.
- **WR-03** (multiset comparison) and **CR-01** (regex anchor) have
  comprehensive regression tests covering both the previously-undetected
  failure modes and the valid-input sanity checks.

---

_Fixed: 2026-06-14T12:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
