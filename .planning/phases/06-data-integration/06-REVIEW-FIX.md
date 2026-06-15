---
phase: 06-data-integration
fixed_at: 2026-06-15T03:40:00Z
review_path: .planning/phases/06-data-integration/06-REVIEW.md
iteration: 1
findings_in_scope: 13
fixed: 13
skipped: 0
status: all_fixed
---

# Phase 06: Code Review Fix Report

**Fixed at:** 2026-06-15T03:40:00Z
**Source review:** `.planning/phases/06-data-integration/06-REVIEW.md`
**Iteration:** 1
**Scope:** critical_warning (4 Critical + 9 Warning; 6 Info out of scope)

**Summary:**
- Findings in scope: 13
- Fixed: 13
- Skipped: 0

## Verification

- All 13 in-scope findings fixed, each in its own atomic commit.
- `python -m pytest tests/pipeline/` after all fixes: **177 passed, 17 skipped, 0 failures** (feature_generator: 87 passed, 9 skipped — no pre-existing failures observed).
- `python -m pytest tests/scraper/` after all fixes: all pass except one pre-existing failure (`test_kaggle_physical_type_equality_for_corners`) that fails because the Kaggle data CSV is gitignored and absent from the worktree; it is unrelated to any fix here and fails identically on the pre-fix baseline.
- **8-point validation on the unified corpus** (`run_all_validations` against `data/standard/`): **overall_pass = True**, all 8 checks pass. This confirms CR-03 (tightened bool dtype), CR-04 (conditional audit_pass), WR-02 (int-as-float content check), and WR-08 (1-to-1 check) do NOT make the validator too strict for the current (correct) unified corpus.

## Data Regeneration Decision (CR-01 / CR-02)

CR-01 and CR-02 are regex/classification bugs that misclassified rows. The **code fix is necessary but not sufficient** on its own: the already-generated `data/standard/kaggle/*.parquet` (and the unified `data/standard/*.parquet`) still contain the wrong grade flags for the affected races. Verified staleness in `data/standard/kaggle/race.parquet` (race-table rows, deduplicated):

- `grade='L'`: **165 races** with `race_flag_listed=False` and `race_flag_stakes=False` (should both be `True`). Entry-row impact: 2,232 rows (per REVIEW.md).
- `grade='G'`: **7 races** with `race_flag_graded_stakes=False` and `race_flag_stakes=False` (should both be `True`). Entry-row impact: 110 rows (per REVIEW.md).

**Decision: regeneration is DEFERRED to the next pipeline run.** Rationale:
1. The fix is in the converter code (`_apply_grade_detection`); the next `python -m src.pipeline.kaggle_converter convert` invocation will regenerate `data/standard/kaggle/*.parquet` with correct flags, and the next `integrate_standard_layer` run will propagate the corrections into the unified corpus.
2. Regenerating the 472MB Kaggle CSV -> ~22K race rows + ~311K entry/result rows is a heavy data-pipeline operation properly owned by the pipeline-execution phase, not the code-review-fix phase.
3. The validator (post-CR-03/CR-04 fixes) does NOT catch the stale data as a failure because the stale `False` values are valid booleans (just semantically wrong) — this is expected; the validator checks structural integrity, not semantic correctness of every flag value.

Action required before the next EV-feature training run: re-run `convert()` + `integrate_standard_layer()` so the unified corpus reflects the corrected grade detection.

## Fixed Issues

### CR-01: Listed races (grade="L") are silently misclassified

**Files modified:** `src/pipeline/kaggle_converter.py`, `tests/pipeline/test_kaggle_converter.py`
**Commit:** `9796f48`
**Severity:** Critical (data integrity)
**Applied fix:** Added a bare-token classification pass in `_apply_grade_detection` that runs after the `derive_race_flags` per-row loop and mutates `per_row_results` in place before the OR-merge. A bare `grade="L"` sets `race_flag_listed=True` and `race_flag_stakes=True`. The fix lives in the converter (where `grade` is known to be the structured リステッド・重賞競走 column) rather than in `flag_crosswalk._LISTED_REGEX`, because a bare `L` is only unambiguous as a top-level grade token — matching it inside `_LISTED_REGEX` would also match the letter `L` inside arbitrary race names.
**Regression test:** `test_kaggle_bare_grade_L_detected_as_listed_and_stakes` (grade='L' -> listed=True, stakes=True, graded stays False/NA).
**Logic-bug flag:** fixed: requires human verification (the OR-merge fillna(False) semantics mean grade=None rows get concrete False, not NA — test assertions adapted accordingly).
**Notes:** Code fix complete; data regeneration deferred (see Data Regeneration Decision above).

### CR-02: Bare grade="G" rows (110 entry-rows) are not detected as graded/stakes

**Files modified:** `src/pipeline/kaggle_converter.py`, `tests/pipeline/test_kaggle_converter.py`
**Commit:** `9796f48` (same commit as CR-01 — tightly coupled, same bare-token pass)
**Severity:** Critical (data integrity)
**Applied fix:** Same bare-token pass as CR-01. A bare `grade="G"` (or full-width `Ｇ`) sets `race_flag_graded_stakes=True` and `race_flag_stakes=True`. The actual G1/G2/G3 level, if any, is encoded in `race_name` and already detected by `_GRADE_REGEX`.
**Regression test:** `test_kaggle_bare_grade_G_detected_as_graded_and_stakes` (grade='G' -> graded=True, stakes=True).
**Notes:** Code fix complete; data regeneration deferred.

### CR-03: _DTYPE_COMPAT['bool'] accepts object dtype unconditionally

**Files modified:** `src/pipeline/validators.py`, `tests/pipeline/test_validators.py`
**Commit:** `ef3e79c`
**Severity:** Critical (validator blind spot)
**Applied fix:** Removed `"object"` from `_DTYPE_COMPAT['bool']` (the production dtype contract uses nullable `boolean` for all 20 race_flag_* fields, which serializes to Arrow bool, NOT object). Added an object-content guard in `validate_schema_conformance`: a bool field stored as object is accepted only if all non-null values are `True`/`False` (the residual all-NA Parquet artifact case); mixed string/int content is rejected with a `non-bool values` error.
**Regression tests:** `test_corrupt_bool_object_column_rejected` (string content -> flagged), `test_all_na_object_bool_column_accepted` (all-NA -> accepted).

### CR-04: validate_sample_rows silent-True paths + audit_pass hardcoded True

**Files modified:** `src/pipeline/validators.py`, `tests/pipeline/test_validators.py`
**Commit:** `224e229`
**Severity:** Critical (validator blind spot)
**Applied fix:** Two independent defects:
- **(a)** `validate_sample_rows` silent-True paths: empty Parquet (0 rows) now returns `False` (fail loud — this is the signature of a corrupt convert/integration run); missing csv_key / no comparable columns now omit from results (distinguish "not checked" from "passed"); the aggregator `all(sample_result.values()) if sample_result else True` correctly returns True only when at least one table WAS checked AND all passed.
- **(b)** `audit_pass` no longer hardcoded `True`; derived from `audit_result`: race table ANY leak fails (race is pre-race only); entry table `popularity`/`win_odds` are documented expected leaks (Phase 1 D-03), any OTHER leak fails; result/odds/payoff are post-race by design (informational).
**Regression tests:** `test_empty_parquet_flagged_not_silent_pass` (CR-04a), `test_audit_pass_false_on_race_table_leak` (CR-04b race, via monkeypatch since validate_audit's per-schema design cannot detect cross-schema race leaks), `test_audit_pass_false_on_unexpected_entry_leak` (CR-04b entry).
**Notes:** The deeper design gap (validate_audit uses per-schema `audit_leakage`, and RaceSchema has no post-race fields, so a real race-table leak of a result-schema column cannot be detected by the current audit design) is documented in the test; cross-schema audit checking is out of scope for this fix.

### WR-01: _GRADE_REGEX missing the GⅠ/GⅡ/GⅢ (Roman-numeral U+2160..2162) form

**Files modified:** `src/scraper/flag_crosswalk.py`, `tests/pipeline/test_kaggle_converter.py`
**Commit:** `79e15e8`
**Severity:** Warning
**Applied fix:** Added `GⅠ|GⅡ|GⅢ` (half-width G U+0047 + ROMAN NUMERAL ONE/TWO/THREE) alternatives to `_GRADE_REGEX`, ordered longest-first. Also corrected the stale `U+FF21` annotation in `test_kaggle_graded_derivation_matches_regex` docstring (U+FF21 is full-width Latin A, not the Roman numeral Ⅰ which is U+2160).
**Regression test:** `test_grade_regex_matches_roman_numeral_form` (GⅠ/GⅡ/GⅢ, realistic 優駿牝(GⅠ) name, existing forms still match, bare 'G' still does NOT match).

### WR-02: Rule-1 int-as-float shortcut over-broad

**Files modified:** `src/pipeline/validators.py`, `tests/pipeline/test_validators.py`
**Commit:** `1f38f1e`
**Severity:** Warning
**Applied fix:** Added `_INT_AS_FLOAT_ALLOWLIST` constant (`corner_1..4`, `horse_weight`, `weight_change`, `popularity` — the SCHEMA_DTYPE_MAP intentional Float64 fields). These short-circuit as before. All other int fields stored as float must contain integer-valued content (`series % 1 == 0`) or be all-NaN; non-integer values (e.g. `distance=[2000.5, 1600.25]`) are rejected.
**Regression tests:** `test_int_field_corrupted_to_non_integer_float_rejected` (distance=2000.5 -> flagged), `test_int_field_integer_valued_float_accepted` (distance=2000.0 -> accepted).

### WR-03: integrate_standard_layer audit does not detect missing expected entry leaks

**Files modified:** `src/pipeline/integration.py`
**Commit:** `90dc00e`
**Severity:** Warning
**Applied fix:** After the unexpected-leak check, added a `missing_expected` check that raises `ValueError` if `popularity` or `win_odds` is absent from the merged entry columns. This makes the audit a true last-line-of-defense check. The primary guard (`_assert_column_set_equality`) still catches missing columns first; WR-03 is defense-in-depth for the documented post-hoc audit role.
**Regression test:** Not added as a separate test — the primary `_assert_column_set_equality` guard already enforces full column-set equality and would catch the missing-column case first; the value of this fix is as a last-line-of-defense guard that only fires if a future refactor weakens the primary guard.

### WR-04: Duplicate _recast_to_canonical definitions with divergent mutation semantics

**Files modified:** `src/scraper/normalizer.py`, `src/pipeline/kaggle_converter.py`, `src/pipeline/integration.py`
**Commit:** `8504ec2`
**Severity:** Warning
**Applied fix:** Extracted a single `recast_to_canonical` (public) into `src/scraper/normalizer.py` with copy-semantics (returns a new frame, never mutates the caller's frame — the load-bearing behavior the integration caller relies on). Both consumers import it and keep a `_recast_to_canonical = recast_to_canonical` back-compat alias so existing imports (`test_kaggle_converter.test_recast_raises_on_bad_data`, `integration.__all__`) keep working. Added `recast_to_canonical` to `normalizer.__all__`. Removed now-unused `SCHEMA_DTYPE_MAP`/`BaseModel` imports.
**Semantic change:** the kaggle_converter path now uses copy-semantics; all call sites reassign the result (`race_df = _recast_to_canonical(...)`) so behavior is preserved for every caller.

### WR-05: df['障害区分'] != '障害' filter is NaN-unsafe

**Files modified:** `src/pipeline/kaggle_converter.py`
**Commit:** `e771e39`
**Severity:** Warning
**Applied fix:** Replaced with the `normalizer.py:716-719` NaN-safe pattern: `obstacle_mask = (s == '障害') & s.notna(); df = df[~obstacle_mask]`. This keeps NaN flat-race rows instead of dropping them (which the previous form would do if a future upstream change introduced NaN, since `pd.NA != '障害'` evaluates to `pd.NA`).

### WR-06: integrate_standard_layer does not validate scraped month dir names

**Files modified:** `src/pipeline/integration.py`, `tests/pipeline/test_integration.py`
**Commit:** `15f2c93`
**Severity:** Warning
**Applied fix:** Added `_MONTH_RE = re.compile(r"^\d{6}$")`; the `month_dirs` filter now requires the directory name to match. Non-matching directories are collected and logged as a warning ("skipping non-YYYYMM dirs"). The empty-month check now reports "zero YYYYMM month directories" to distinguish from "zero directories".
**Regression test:** `test_stray_non_yyyymm_directory_skipped` (creates a `__pycache__` dir with a bogus race.parquet inside scraped/; verifies the stray race_id does NOT appear in the merged race table).

### WR-07: _atomic_write_parquet imported from outside normalizer.__all__

**Files modified:** `src/scraper/normalizer.py`, `src/pipeline/kaggle_converter.py`, `src/pipeline/integration.py`
**Commit:** `8532e8b`
**Severity:** Warning
**Applied fix:** Renamed the definition to `atomic_write_parquet` (public), added it to `normalizer.__all__`, kept `_atomic_write_parquet` as a deprecated back-compat alias. Updated the cross-module imports and call sites in `kaggle_converter` and `integration` to use the public name. The transactionality test patches `_commit_staging` (NOT `atomic_write_parquet`), so it is unaffected.

### WR-08: validate_referential_integrity does not check horse_race_id FK (entry ↔ result 1-to-1)

**Files modified:** `src/pipeline/validators.py`, `tests/pipeline/test_validators.py`
**Commit:** `6730384`
**Severity:** Warning
**Applied fix:** Added an explicit entry/result `horse_race_id` 1-to-1 check using `Counter` multiset comparison (catches both set-difference and count-mismatch cases). The check requires both tables to have a `horse_race_id` column; minimal fixtures that omit it skip the check (no KeyError).
**Regression tests:** `test_horse_race_id_1to1_mismatch_detected` (entry has 3 hids, result has 2 -> flagged), `test_horse_race_id_1to1_consistent_no_error` (matching multisets -> no 1-to-1 error).

### WR-09: Stale docstring in flag_crosswalk.py contradicts the D-01 fix

**Files modified:** `src/scraper/flag_crosswalk.py`
**Commit:** `ffb5b1a`
**Severity:** Warning
**Applied fix:** Replaced the stale "Phase 6 MUST reconcile this divergence" note (which claimed the Kaggle-side `(国際)` mapping was still present) with a "Phase 6 D-01 closed this gap" pointer that documents the current state: D-01 REMOVED the Kaggle-side mapping (KAGGLE_COLUMN_MAP has 65 entries), graded detection on both sides comes from `_GRADE_REGEX`, and explicitly warns against re-introducing the mapping (which would re-open UAT-Test-3). Also references the WR-01 Roman-numeral forms and CR-01/CR-02 bare-token classification for completeness.

---

_Fixed: 2026-06-15T03:40:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
