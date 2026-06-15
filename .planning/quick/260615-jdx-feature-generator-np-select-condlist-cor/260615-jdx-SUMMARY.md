---
phase: 03-feature-engineering
plan: 260615-jdx
subsystem: data-pipeline
tags: [numpy, pandas, nullable-dtype, np.select, feature-engineering, regression-fix]

# Dependency graph
requires:
  - phase: 06-data-integration
    provides: "Unified standard-layer corpus (race=38009 / entry=result=534953, 2015-01-04..2026-05-31) as the LOCKED feature input"
  - phase: 03-feature-engineering
    provides: "Original feature_generator.generate_target authored against Kaggle-only (object-dtype) corpus"
provides:
  - "feature_generator.generate_target dtype-safe against pandas nullable string finish_note (np.select condlist coerced to native bool ndarray)"
  - "Regenerated data/feature/features_train.parquet (534,953 rows) + features_pred.parquet (534,953 rows) on the unified corpus"
  - "Real-data integration test expectations aligned to unified-corpus scale ([530000, 540000])"
  - "Regression test test_generate_target_handles_nullable_string_finish_note guards the dtype edge case"
affects: [phase-07-model-training, phase-08-ev-calculation, phase-09-backtesting]

# Tech tracking
tech-stack:
  added: []  # No new libraries
  patterns:
    - "Nullable-boolean to native-bool coercion via Series.to_numpy(dtype=bool, na_value=False) before passing to np.select"
    - "Regression tests must construct the exact dtype that exposes the bug (pd.array(..., dtype='string')) — cannot rely on object dtype silently masking the failure"

key-files:
  created:
    - ".planning/quick/260615-jdx-feature-generator-np-select-condlist-cor/260615-jdx-SUMMARY.md"
  modified:
    - "src/pipeline/feature_generator.py"
    - "tests/pipeline/test_feature_generator.py"
    - "data/feature/features_train.parquet (on-disk, gitignored — regenerated, not committed)"
    - "data/feature/features_pred.parquet (on-disk, gitignored — regenerated, not committed)"

key-decisions:
  - "Root cause is dtype, NOT empty condlist. np.select rejects pandas nullable boolean Series carrying pd.NA; the fix is native-bool coercion of each condlist entry, not a defensive empty-list guard."
  - "pd.NA -> False coercion preserves the existing 'finished' default branch semantics verbatim: an unknown finish_note is a finished race with no special note. No behavioral change vs the Kaggle-only (object dtype) corpus."
  - "Parquet artifacts under data/feature/ are NOT git-tracked (.gitignore line 22: data/). The Task 2 git commit contains only the tracked test-expectation edits; the regenerated 534,953-row parquet files are verified ON DISK via the plan's verify commands and constitute the deliverable."
  - "Did NOT add a defensive 'if conditions is empty' guard — condlist always has 5 well-formed entries, so such a guard would be dead code and would mask the real dtype root cause."

patterns-established:
  - "Nullable-dtype coercion pattern: when feeding pandas nullable boolean Series to numpy primitives that require native bool ndarrays (np.select, np.where, np.logical_and, etc.), coerce via .to_numpy(dtype=bool, na_value=<explicit>) with an explicit NA policy. Never rely on object dtype to paper over the contract."

requirements-completed: [DEFERRED-1]

# Metrics
duration: ~15min (verification + audit + SUMMARY; Tasks 1-2 code work already committed in this session)
completed: 2026-06-15
---

# Quick Task 260615-jdx: feature_generator np.select fix + unified-corpus feature regen Summary

**Root-cause dtype fix for np.select TypeError blocking feature generation on the Phase 6 unified corpus — each condlist entry coerced to native bool ndarray, 534,953-row feature layer regenerated, real-data test expectations aligned.**

## Performance

- **Duration:** ~15 min (verification + full-suite audit + SUMMARY authoring)
- **Tasks:** 3 (Task 1 root-cause fix, Task 2 regen + test-alignment, Task 3 verify + audit + SUMMARY)
- **Files modified (git-tracked):** 2 (`src/pipeline/feature_generator.py`, `tests/pipeline/test_feature_generator.py`)
- **Files regenerated (gitignored, on-disk):** 2 (`data/feature/features_train.parquet`, `data/feature/features_pred.parquet`)

## Accomplishments

- np.select TypeError in `generate_target` resolved at the root: each of the 5 condlist entries is now coerced to a native bool ndarray via `.to_numpy(dtype=bool, na_value=False)` before passing to `np.select`. pd.NA maps to False → default "finished" branch (unchanged semantics).
- All 11 `TestTargetVariable` non-degradation tests pass unchanged — the 6-way `result_status` classification (finished/dnf/disqualified/scratched/removed/demoted) and D-12/D-13/D-14 behavior are byte-identical to the Kaggle-only baseline.
- New regression test `test_generate_target_handles_nullable_string_finish_note` explicitly constructs `pd.array([...], dtype="string")` with `<NA>` + each of 中/失/取/除/降 and asserts the 6-way classification row-for-row. Guards against silent regression to object dtype.
- Feature layer regenerated against the unified corpus: `features_train.parquet` = 534,953 rows / 78 cols; `features_pred.parquet` = 534,953 rows / 74 cols. Row counts match the unified corpus entry count exactly.
- Real-data integration test expectations aligned: `test_real_data_row_counts` band widened from `[310000, 320000]` to `[530000, 540000]` with corrected docstring; `test_real_data_target_distribution` band `[0.16, 0.26]` held unchanged (actual regenerated rate = 0.2141, comfortably inside).
- Stale `data/feature/tmp_full/` scratch directory (from a prior failed test run) removed during this execution pass (gitignored, disk cleanup only).
- Full test suite: **513 passed, 1 skipped, 0 failed** — zero feature_generator-attributed failures (was 2 failed pre-fix).

## Task Commits

Each task committed atomically on `main` (code + test only; parquet is gitignored):

1. **Task 1: Fix np.select condlist dtype in generate_target (root-cause)** — `516fa46` (fix)
2. **Task 2: Regenerate features on unified corpus + align real-data test expectations** — `bcb0716` (feat)
3. **Task 3: Verify + audit + SUMMARY** — (this SUMMARY; orchestrator handles the docs commit per execution constraints)

## Files Created/Modified

- `src/pipeline/feature_generator.py` — `generate_target` lines 616-619: condlist now built with `.to_numpy(dtype=bool, na_value=False)` coercion. Inline docstring (lines 605-615) documents the dtype root cause and the pd.NA→False→default-branch semantics.
- `tests/pipeline/test_feature_generator.py` — Added `TestTargetVariableNullableDtype` regression test class; updated `TestRealDataIntegration::test_real_data_row_counts` band + docstring to unified-corpus scale.
- `data/feature/features_train.parquet` — Regenerated on unified corpus (534,953 rows × 78 cols). Gitignored; verified on disk.
- `data/feature/features_pred.parquet` — Regenerated on unified corpus (534,953 rows × 74 cols). Gitignored; verified on disk.

## What Was Broken

`data/standard/result.parquet` ships `finish_note` as pandas nullable `string` dtype (Phase 4 cycle-3 #1: nullable dtypes preserved end-to-end). After `load_and_merge()`, `finish_note` stays `string` with `<NA>` (pd.NA) for the 531,320 finished entries.

`generate_target` built the condlist as a list of comparisons:
- `df["finish_note"] == "中"` → pandas nullable `boolean` Series (carries `pd.NA`, NOT native bool)
- Likewise for 失/取/除/降

`np.select(condlist, choicelist, default)` requires each condlist entry to be a **native bool ndarray**. A pandas nullable `boolean` Series with `pd.NA` is rejected:

```
TypeError: invalid entry 0 in condlist: should be boolean ndarray
```

at `feature_generator.py:614` (the `np.select` call).

**Why the Kaggle-only corpus did not trip it:** the original Phase 3 Kaggle-only corpus carried `finish_note` as plain `object` dtype with Python `None`, so `== "中"` produced a native bool ndarray (None == "中" is already False). The Phase 6 unified corpus preserves the nullable `string` dtype, exposing the latent bug.

**NOT the cause (disproven hypotheses):** The initial task brief hypothesized "empty condlist" / "value-range outside Kaggle" / "NaN not hitting conditions". Reproduction disproves all three — condlist has 5 well-formed entries, and there are zero `finish_note` values outside {中, 失, 取, 除, 降, NA}. The cause is purely dtype.

## How It Was Fixed

One-line conceptual change at `src/pipeline/feature_generator.py:generate_target`:

```python
conditions = [
    (df["finish_note"] == note).to_numpy(dtype=bool, na_value=False)
    for note in ["中", "失", "取", "除", "降"]
]
```

`choices` and `default="finished"` are unchanged. The downstream `is_dnf`, `target_top3`, and `exclude_from_training` logic is untouched.

**Why `na_value=False`:** `pd.NA == "中"` is `pd.NA` (unknown). For classification, an unknown note must NOT match any special-status branch, so it must be coerced to `False` → falls through to default `"finished"`. This is exactly the intended semantics: a finished race with no special note. It preserves the D-12/D-13/D-14 contract and the Kaggle-only (object dtype) behavior byte-for-byte.

## Non-Degradation Evidence

All 11 `TestTargetVariable` tests pass unchanged:
- `test_position_1_target_top3`, `test_position_2_target_top3`, `test_position_3_target_top3`, `test_position_4_target_top3`
- `test_dnf_middle_note`, `test_scratched_tori_note`, `test_removed_jo_note`, `test_disqualified_shitsu_note`, `test_demoted_kou_note_keeps_position`
- `test_normal_finish_result_status`, `test_scratched_vs_removed_distinct_status`

The new regression test `test_generate_target_handles_nullable_string_finish_note` explicitly constructs the nullable `string` dtype and asserts all 6 classification rows. Full `tests/pipeline/test_feature_generator.py`: **97 passed**.

## Feature Output Scale

| Artifact | Rows | Cols | Notes |
|----------|------|------|-------|
| `data/feature/features_train.parquet` | 534,953 | 78 | FEATURE_COLUMNS + ENTITY_KEY + target/auxiliary |
| `data/feature/features_pred.parquet` | 534,953 | 74 | FEATURE_COLUMNS + ENTITY_KEY only |

**Corpus:** race = 38,009 / entry = result = 534,953, span 2015-01-04..2026-05-31 (Phase 6 unified corpus, LOCKED, 8-point validation green).

**target_top3 positive rate (valid starts, excl 取/除):** **0.2141** — matches the proxy estimate and sits comfortably inside the test band `[0.16, 0.26]` (unchanged).

**result_status distribution (regenerated train):**

| status | count |
|--------|-------|
| finished | 531,320 |
| dnf | 1,668 |
| removed | 1,090 |
| scratched | 854 |
| demoted | 20 |
| disqualified | 1 |

Total valid starts (excl scratched/removed) = 533,009.

## Full-Suite Status

```
513 passed, 1 skipped, 0 failed, 11 warnings in 444.25s
```

Zero feature_generator-attributed failures. No other unrelated failures to report (the pre-fix baseline per `deferred-items.md` was "497 passed, 2 failed, 1 skipped"; the suite has since grown and is now fully green).

## Scope Respected

`git diff --stat 18e0ae0..HEAD` touches ONLY:
- `src/pipeline/feature_generator.py` (+21 / -... lines)
- `tests/pipeline/test_feature_generator.py` (+91 lines)

NO changes under:
- `data/standard/` (Phase 6 corpus — LOCKED)
- Any Phase 6 source: `src/pipeline/integration*`, `src/pipeline/validators.py`, `src/pipeline/kaggle_converter.py`, `src/pipeline/column_mapping.py`
- `src/schemas/*`

Parquet regeneration is gitignored (`.gitignore` line 22: `data/`); the on-disk 534,953-row files are the deliverable but are intentionally not git-tracked.

## Decisions Made

- **Root cause = dtype, fix = coercion.** Rejected the "empty condlist" hypothesis (disproven by reproduction). Rejected adding a defensive empty-list guard (would be dead code — condlist always has 5 entries — and would mask the real cause).
- **`pd.NA -> False` preserves semantics.** The default branch is "finished"; an unknown finish_note is definitionally a finished race with no special note. Non-degradation verified by all 11 `TestTargetVariable` tests passing unchanged.
- **Parquet is on-disk deliverable, not a git artifact.** Per the execution constraints, `data/` is gitignored. Task 2's commit contains only the tracked test-expectation edits; the regenerated parquet files are verified via the plan's `<verify>` commands (read-back + row-count assertions).

## Deviations from Plan

None — plan executed exactly as written. The execution environment note (no worktree isolation; parquet gitignored) clarified the Task 2 commit boundary but did not change the plan's intent.

## Issues Encountered

None beyond the bug the plan was created to fix.

## User Setup Required

None — no external service configuration, no new dependencies, no environment variables.

## Next Phase Readiness

- **Phase 7 (model training) is unblocked.** The feature layer is regenerated at unified-corpus scale (534,953 rows), `target_top3` is populated with the correct positive rate (0.2141), and all 97 feature_generator tests are green.
- The nullable-dtype contract is now explicitly guarded by `TestTargetVariableNullableDtype` — future corpus changes that preserve or alter the `finish_note` dtype will surface immediately.
- No blockers or concerns carried forward.

## Self-Check: PASSED

- `src/pipeline/feature_generator.py` — FOUND
- `tests/pipeline/test_feature_generator.py` — FOUND
- `data/feature/features_train.parquet` — FOUND (534,953 rows, verified via read-back)
- `data/feature/features_pred.parquet` — FOUND (534,953 rows, verified via read-back)
- `.planning/quick/260615-jdx-...-SUMMARY.md` — FOUND (this file)
- Commit `516fa46` (Task 1) — FOUND in git log
- Commit `bcb0716` (Task 2) — FOUND in git log
- Scope guard — PASS: only `src/pipeline/feature_generator.py` and `tests/pipeline/test_feature_generator.py` changed since `18e0ae0`; no `data/standard/`, Phase 6 source, or `src/schemas/` files touched.
- Stale `data/feature/tmp_full/` — removed (regenerated by the full-suite audit run via `test_temporal_invariance_real_data`, which uses it as test scratch; cleaned post-audit).

---
*Quick task: 260615-jdx-feature-generator-np-select-condlist-cor*
*Completed: 2026-06-15*
