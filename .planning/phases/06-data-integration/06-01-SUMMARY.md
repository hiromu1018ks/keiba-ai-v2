---
phase: 06-data-integration
plan: 01
subsystem: data-pipeline
tags: [kaggle, parquet, pyarrow, dtype-discipline, grade-detection, schema-alignment]

# Dependency graph
requires:
  - phase: 02-kaggle-data-pipeline
    provides: kaggle_converter.py + column_mapping.py (the D-01/D-02 modification targets)
  - phase: 04-scraping-infrastructure-race-data
    provides: SCHEMA_DTYPE_MAP (dtype authority) + derive_race_flags (grade detector) + _atomic_write_parquet
provides:
  - "data/standard/kaggle/{race,entry,result}.parquet — STABLE separate input path for 06-02 integration (BLOCKER-1)"
  - "Kaggle-side grade detection via _GRADE_REGEX (matches scraper side); (国際) no longer misclassified as graded (D-01)"
  - "Kaggle Parquet regenerated with nullable dtypes matching SCHEMA_DTYPE_MAP (D-02): zero Arrow-null columns, race_date=string, distance=int64, race_flag_*=bool"
  - "convert(core_tables_subdir='kaggle') API that SKIPS odds/payoff writes entirely (HIGH #2 cycle-3 — Phase 5 seed protected)"
affects: [06-data-integration/06-02 (integration reads kaggle/ subdir), 06-03 (8-point run_all_validations runs against unified root), feature-regen, backtest]

# Tech tracking
tech-stack:
  added: []  # no new deps; reused src.scraper.normalizer.SCHEMA_DTYPE_MAP + _atomic_write_parquet
  patterns:
    - "Kaggle-side grade detection reuses scraper's derive_race_flags (single GRADE_REGEX authority across both corpora)"
    - "OR-merge with fillna(False) on both sides (pandas treats True | pd.NA as NA, not True)"
    - "core_tables_subdir param redirects core-table writes + SKIPS odds/payoff writes (strongest seed protection)"
    - "_recast_to_canonical mirrors _build_typed_dataframe but operates on existing DataFrame (D-02 dtype unification)"

key-files:
  created:
    - data/standard/kaggle/race.parquet  # gitignored; regenerated from data/raw/kaggle/
    - data/standard/kaggle/entry.parquet
    - data/standard/kaggle/result.parquet
  modified:
    - src/pipeline/kaggle_converter.py
    - src/pipeline/column_mapping.py
    - tests/pipeline/test_kaggle_converter.py
    - tests/pipeline/test_column_mapping.py

key-decisions:
  - "D-01: removed レース記号/(国際) -> race_flag_graded_stakes from KAGGLE_COLUMN_MAP; graded detection now comes from _GRADE_REGEX via _apply_grade_detection (matches Phase 4 P07 scraper-side decision)"
  - "D-02: regenerated Kaggle Parquet to data/standard/kaggle/ subdir with SCHEMA_DTYPE_MAP nullable dtypes; race_date stays string (MEDIUM #5 — code-authoritative contract supersedes CONTEXT.md datetime note)"
  - "HIGH #2 cycle-3: convert(core_tables_subdir='kaggle') SKIPS odds/payoff writes entirely — Phase 5 seed at data/standard/{odds_trifecta,payoff}.parquet protected (SHA-256 verified unchanged)"
  - "HIGH #3 cycle-3: 06-01-T3 does NOT call run_all_validations against kaggle/ subdir (it cannot pass — 5-table contract); 3-table-specific validation runs here; full 8-point deferred to 06-03-T2 against unified root"
  - "BLOCKER-1: regenerated Kaggle race/entry/result written to data/standard/kaggle/ as a STABLE separate input path for 06-02 idempotent integration"

patterns-established:
  - "OR-merge idiom: existing.fillna(False) | new.fillna(False) then .astype('boolean') — preserves True, never downgrades"
  - "race_condition=' ' (single space) bypass of derive_race_flags early-return guard when grade is null"
  - "core_tables_subdir param pattern: truthy subdir => redirect core tables + SKIP odds/payoff; None => all 5 tables to root (backwards-compat)"

requirements-completed: [DATA-05]

# Metrics
duration: 14min
completed: 2026-06-14
---

# Phase 6 Plan 01: Kaggle-side D-01/D-02 Reconciliation Summary

**Kaggle Parquet regenerated to data/standard/kaggle/ with (国際)->graded mapping removed (D-01), nullable SCHEMA_DTYPE_MAP dtypes applied (D-02), and convert(core_tables_subdir='kaggle') now SKIPS odds/payoff writes entirely — Phase 5 seed SHA-256-proven unchanged**

## Performance

- **Duration:** ~14 min (846s)
- **Started:** 2026-06-14T13:26:02Z
- **Completed:** 2026-06-14T13:40:08Z
- **Tasks:** 3/3
- **Files modified:** 4 source + 3 regenerated Parquet (gitignored)

## Accomplishments

- **D-01 applied:** removed the `(国際) -> race_flag_graded_stakes` semantic-error mapping from KAGGLE_COLUMN_MAP; added `_apply_grade_detection` helper that OR-merges `_GRADE_REGEX`-derived True values onto graded_stakes/stakes/listed (single authority shared with scraper side). Regenerated graded_stakes=True count is **838** (deterministic — matches a per-row derive_race_flags recompute exactly).
- **D-02 applied:** regenerated Kaggle race/entry/result Parquet under `data/standard/kaggle/` with `SCHEMA_DTYPE_MAP` nullable dtypes. Arrow schema: zero `null` columns; every `race_flag_*` is `bool`; `distance` is `int64`; `race_date` is `string` (MEDIUM #5 — code contract wins over CONTEXT.md datetime note); `win_odds`/`horse_weight` are `double`.
- **HIGH #2 cycle-3 resolved:** `convert(core_tables_subdir='kaggle')` SKIPS odds/payoff writes entirely — not written to root, subdir, or anywhere. `data/standard/odds_trifecta.parquet` and `payoff.parquet` SHA-256 verified **identical pre/post regen** (NON-OVERWRITE proven).
- **BLOCKER-1 resolved:** regenerated Kaggle corpus lives at the STABLE separate input path `data/standard/kaggle/` that Plan 06-02's idempotent integration reads as its default `kaggle_input_dir`.
- **HIGH #3 cycle-3 resolved:** 06-01-T3 does NOT call `run_all_validations` against the 3-table kaggle/ subdir (it cannot pass — 5-table contract). Instead, a 3-table-specific validation runs here (schema column-set, Arrow dtype, grade-derivation determinism, `validate_integrity` on DataFrames). The full 8-point `run_all_validations` is deferred to 06-03-T2 against the unified root where all 5 tables coexist.
- **Full test suite green:** 470 passed, 1 skipped (308s).

## Task Commits

1. **Task 1: D-01 grade detection** — `b068b3a` (feat)
2. **Task 2: D-02 dtype regen + core_tables_subdir** — `0095412` (feat)
3. **Task 3: 3-table-specific validation** — no commit (validation-only; regenerated Parquet is gitignored)

## Files Created/Modified

- `src/pipeline/column_mapping.py` — removed line 68 `(国際)->graded_stakes`; FLAG_COLUMNS entry at ~197 preserved; added Phase 6 D-01 comment citing Phase 4 P07 + flag_crosswalk.py.
- `src/pipeline/kaggle_converter.py` — added `derive_race_flags` + `SCHEMA_DTYPE_MAP` + `_atomic_write_parquet` + `ResultSchema` imports; new `_apply_grade_detection` helper (runs AFTER `_UNMAPPED_RACE_FLAGS` loop); new `_recast_to_canonical` helper; `convert()` gained `core_tables_subdir` param with HIGH #2 cycle-3 SKIP; `_UNMAPPED_RACE_FLAGS` expanded to include `race_flag_graded_stakes`.
- `tests/pipeline/test_column_mapping.py` — count 66->65 with `INTENTIONALLY_UNMAPPED` allowlist; relaxed JP-name-set check to permit documented unmapped columns.
- `tests/pipeline/test_kaggle_converter.py` — new `TestGradeDetection` (3 tests: regex-match G1, OR-merge preserves True, ordering regression guard), `TestRecastAndDtypes` (4 tests: recast-raises, dtype checks post-regen), `TestCoreTablesSubdir` (4 tests: subdir redirect, SKIP, NON-OVERWRITE, default-5-table backwards-compat).
- `data/standard/kaggle/{race,entry,result}.parquet` — regenerated (gitignored).

## Grade Derivation Result

Regenerated `race.parquet` graded_stakes=True count: **838** (out of 21,929 races).

Determinism proof: a per-row recompute via `derive_race_flags(race_condition=grade_or_space, race_name)` where `grade_or_space` is the `grade` value when non-null else `' '` (single space, bypassing the early-return guard) yields exactly 838 — identical to `int(race_df['race_flag_graded_stakes'].fillna(False).sum())`. The grade detector is deterministic and the OR-merge dropped no True values.

This count is lower than the pre-D-01 `graded_stakes=True` count because the previous mapping misclassified `(国際)`-carrying Listed/OP-special races as graded. Only true GI/GII/GIII/G1/G2/G3/JG*/重賞/ＧＩ races now set the flag.

## Odds/Payoff NON-OVERWRITE Proof (HIGH #2 cycle-3)

`data/standard/odds_trifecta.parquet` and `payoff.parquet` SHA-256, verified **identical** across the regen invocation:

| File | SHA-256 (pre-regen = post-regen) |
|------|----------------------------------|
| `data/standard/odds_trifecta.parquet` | `7473133c8a2c971a2f4ae26e33b9c2043801d006b6f53df9bf6244c80e740013` |
| `data/standard/payoff.parquet`        | `899987a8d66c91c172f9fd00c4c60c3e7b3dfa428a357ed862aa2cfbb8c8351a` |

Regenerated kaggle/ subdir SHA-256 (for traceability):

| File | SHA-256 |
|------|---------|
| `data/standard/kaggle/race.parquet`   | `8faa071e2fe14ef9e020091034b84742a6cdd4b6794c352f374a38075024b5a9` |
| `data/standard/kaggle/entry.parquet`  | `4b9dec2c6a5f4a9f6fcc10400fbc36e334d735435ef46a8347d4599d214952a9` |
| `data/standard/kaggle/result.parquet` | `f5e7548ef5dfa13fcc5297a83fc4799b2578e0e1d71f0adcdddab9304459634d` |

odds/payoff are correctly **absent** from `data/standard/kaggle/` subdir (proven by both `test_convert_skips_odds_payoff_when_subdir_set` on an empty tmp dir AND the production regen).

## race_date dtype Resolution Note (MEDIUM #5)

`race_date` stays Arrow `string` per `SCHEMA_DTYPE_MAP[RaceSchema]["race_date"] = "string"` (verified `src/scraper/normalizer.py:99`) and `src/schemas/race.py:31` declares `race_date: str`. CONTEXT.md D-02's `datetime` wording is superseded by the existing Phase 4 dtype discipline. This plan does NOT change race_date to datetime.

## Decisions Made

- **_UNMAPPED_RACE_FLAGS expanded to 8 entries** (added `race_flag_graded_stakes`). After removing the `(国際)` mapping, graded_stakes has no text source — it must be in the unmapped list so it exists as a pd.NA column BEFORE `_apply_grade_detection` runs. The plan's must_have truth said "the loop creates all 20 race_flag_* columns" — this Rule 1 fix makes that literally true (8 unmapped + 12 text-derived = 20).
- **OR-merge coerces existing to boolean first** (`existing.astype("boolean")` before `.fillna(False)`) to avoid pandas' object->bool downcasting FutureWarning on columns materialized via `pd.NA` writes.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_column_mapping count assertion 66 -> 65**
- **Found during:** Task 1 (after removing the `(国際)` line)
- **Issue:** Plan Test 7 claimed "existing test_column_mapping.py still passes" after removing the mapping, but `test_kaggle_column_map_has_66_entries` asserts exactly 66 and `test_all_jp_names_match_expected_set` checks both missing AND extra directions, so removing one key fails both.
- **Fix:** Changed count to 65; added `INTENTIONALLY_UNMAPPED` allowlist `{"レース記号/(国際)"}`; relaxed the JP-name-set check to permit documented unmapped columns while still catching unexpected regressions. EXPECTED_JP_NAMES stays at 66 (documents the CSV header, which still has `(国際)`).
- **Files modified:** tests/pipeline/test_column_mapping.py
- **Verification:** `python -m pytest tests/pipeline/test_column_mapping.py -q` — 17 passed.
- **Committed in:** b068b3a (Task 1 commit)

**2. [Rule 1 - Bug] _UNMAPPED_RACE_FLAGS must include race_flag_graded_stakes**
- **Found during:** Task 1 (test_apply_grade_detection_runs_after_unmapped_flags KeyError)
- **Issue:** With the `(国際)` mapping removed, `race_flag_graded_stakes` had no source column. `_select_and_rename` no longer produced it, and it was not in `_UNMAPPED_RACE_FLAGS`, so `_apply_grade_detection`'s "all 3 target columns must exist" guard raised KeyError.
- **Fix:** Added `race_flag_graded_stakes` to `_UNMAPPED_RACE_FLAGS` (now 8 entries). This makes the plan's "loop creates all 20 race_flag_* columns" literally true.
- **Files modified:** src/pipeline/kaggle_converter.py
- **Verification:** `test_apply_grade_detection_runs_after_unmapped_flags` passes; full converter suite 41 passed.
- **Committed in:** b068b3a (Task 1 commit)

**3. [Rule 1 - Bug] test_all_flags_converted assertion too strict for grade-derived columns**
- **Found during:** Task 1 (full suite run)
- **Issue:** After `_apply_grade_detection` runs `fillna(False) | new.fillna(False)`, non-graded rows now have concrete `False` (numpy bool) on graded_stakes/stakes/listed, but the test asserted only `True` or `NA`. Also `val is True` is too strict for numpy bools.
- **Fix:** Whitelisted the 3 grade-derived columns to accept `True/False/NA`; used `bool(val)` coercion throughout.
- **Files modified:** tests/pipeline/test_kaggle_converter.py
- **Verification:** `test_all_flags_converted` passes.
- **Committed in:** b068b3a (Task 1 commit)

**4. [Rule 1 - Bug] numpy bool identity in test_kaggle_graded_derivation_matches_regex**
- **Found during:** Task 1 (first test run)
- **Issue:** `v1 is False` failed because `astype('boolean')` produces `numpy.bool_(False)`, not Python `False`.
- **Fix:** Changed to `bool(v1) is False`.
- **Files modified:** tests/pipeline/test_kaggle_converter.py
- **Verification:** test passes.
- **Committed in:** b068b3a (Task 1 commit)

**5. [Rule 1 - Bug] OR-merge FutureWarning on object-dtype fillna**
- **Found during:** Task 1 (test run warnings)
- **Issue:** `existing.fillna(False)` on object-dtype columns (from `pd.NA` writes) triggered pandas' object->bool downcasting FutureWarning.
- **Fix:** Cast `existing = race_df[col].astype("boolean")` before fillna.
- **Files modified:** src/pipeline/kaggle_converter.py
- **Verification:** Test run no longer emits the FutureWarning.
- **Committed in:** b068b3a (Task 1 commit)

**6. [Rule 1 - Bug] Plan verification grep matched docstring mention of errors='ignore'**
- **Found during:** Task 2 (automated verification)
- **Issue:** The plan's `! grep -q 'errors=.ignore.'` check matched `_recast_to_canonical`'s docstring ("NEVER uses `errors='ignore'`"), a false positive — the actual code uses `errors="coerce"` legitimately.
- **Fix:** Reworded the docstring to say "silent `ignore` error mode" instead of the literal `errors='ignore'` token.
- **Files modified:** src/pipeline/kaggle_converter.py
- **Verification:** `! grep -q 'errors=.ignore.'` now returns success.
- **Committed in:** 0095412 (Task 2 commit)

---

**Total deviations:** 6 auto-fixed (6 Rule 1 bugs — test/count adjustments and a dtype-coercion cleanup forced by the D-01 mapping removal; no scope creep, no architectural changes).
**Impact on plan:** All auto-fixes necessary for the D-01 mapping removal to actually work end-to-end. The plan's must_have truths assumed "the loop creates all 20 race_flag_* columns" without noting graded_stakes needed to join the unmapped list after losing its source mapping; these fixes realize that assumption.

## Issues Encountered

None beyond the auto-fixed issues above.

## User Setup Required

None — no external service configuration required. The regenerated Parquet files live under the gitignored `data/standard/kaggle/` and are reproducible via `python -c "from pathlib import Path; from src.pipeline.kaggle_converter import convert; convert(standard_dir=Path('data/standard'), core_tables_subdir='kaggle')"`.

## Next Phase Readiness

- **Ready for 06-02 (integration):** `data/standard/kaggle/{race,entry,result}.parquet` is the STABLE separate input path; `integrate_standard_layer` can default `kaggle_input_dir = standard_dir / 'kaggle'`. The two corpora (Kaggle kaggle/ subdir + scraped scraped/{YYYYMM}/) are now schema-indistinguishable (same SCHEMA_DTYPE_MAP dtypes, same grade-detection authority).
- **Ready for 06-03-T2:** The full 8-point `run_all_validations` runs there against `data/standard/` ROOT after integration, where all 5 tables (unified race/entry/result + Phase 5 odds/payoff) coexist. The 5-table contract is honored at the natural validation point.
- **Phase 5 seed protected:** odds/payoff at `data/standard/{odds_trifecta,payoff}.parquet` are byte-identical to their pre-regen state and will persist untouched through the Wave 2 merge.

## Self-Check: PASSED

- `data/standard/kaggle/race.parquet` — FOUND
- `data/standard/kaggle/entry.parquet` — FOUND
- `data/standard/kaggle/result.parquet` — FOUND
- `.planning/phases/06-data-integration/06-01-SUMMARY.md` — FOUND
- `data/standard/kaggle/odds_trifecta.parquet` — correctly ABSENT
- `data/standard/kaggle/payoff.parquet` — correctly ABSENT
- Commit `b068b3a` (Task 1) — FOUND in git log
- Commit `0095412` (Task 2) — FOUND in git log

---
*Phase: 06-data-integration*
*Completed: 2026-06-14*
