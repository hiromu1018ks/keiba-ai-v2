---
quick_id: 260615-jdx
slug: feature-generator-np-select-condlist-cor
type: execute
mode: quick
created: 2026-06-15
files_modified:
  - src/pipeline/feature_generator.py
  - tests/pipeline/test_feature_generator.py
  - data/feature/features_train.parquet
  - data/feature/features_pred.parquet
autonomous: true
requirements:
  - DEFERRED-1
must_haves:
  truths:
    - "generate() runs to completion on the unified corpus (race=38009 / entry=result=534953) without TypeError"
    - "result_status classification (finished/dnf/disqualified/scratched/removed/demoted) is unchanged for every finish_note category; 取→scratched, 除→removed, 中→dnf, 失→disqualified, 降→demoted, NA→finished"
    - "features_train.parquet + features_pred.parquet are regenerated against the unified corpus and row counts align with 534,953 entries"
    - "All tests in tests/pipeline/test_feature_generator.py pass; full suite has zero feature-generator-attributed failures"
  artifacts:
    - path: "src/pipeline/feature_generator.py"
      provides: "np.select condlist forced to native bool ndarray (root-cause fix at line 614)"
      contains: "generate_target"
    - path: "tests/pipeline/test_feature_generator.py"
      provides: "Updated real-data expected row counts for the unified corpus"
    - path: "data/feature/features_train.parquet"
      provides: "Regenerated training features for the unified 2015-2026/5 corpus"
    - path: "data/feature/features_pred.parquet"
      provides: "Regenerated prediction features for the unified 2015-2026/5 corpus"
  key_links:
    - from: "src/pipeline/feature_generator.py:generate_target"
      to: "numpy.select"
      via: "condlist entries converted via to_numpy(dtype=bool, na_value=False) before np.select"
      pattern: "to_numpy\\(dtype=bool"
    - from: "data/feature/features_train.parquet"
      to: "data/standard/{race,entry,result}.parquet"
      via: "generate(standard_dir=Path('data/standard'), feature_dir=Path('data/feature'))"
      pattern: "534953"
---

<objective>
Fix the `np.select` TypeError in `src/pipeline/feature_generator.py:generate_target` (line 614) that blocks feature generation on the Phase 6 unified corpus, then regenerate `data/feature/*.parquet` against the unified corpus and align the real-data test expectations.

Purpose: Unblock Phase 7 (model training). The unified corpus (race=38,009 / entry=result=534,953, 2015-01-04..2026-05-31) is LOCKED and correct (Phase 6 8-point validation green). The bug is a Phase 3 data-handling defect, explicitly deferred per `06-CONTEXT.md` Deferred Ideas and tracked as DEFERRED-1. The Phase 3 feature_generator was authored against the Kaggle-only corpus (311,806 rows) where `finish_note` was object dtype; the unified corpus preserves pandas nullable `string` dtype (Phase 4 cycle-3 #1 authority), which exposes the latent np.select edge case.

Output: Patched `feature_generator.py`, updated real-data test expectations, regenerated `features_train.parquet` + `features_pred.parquet`, and a SUMMARY documenting root cause + fix + output scale.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/STATE.md
@.planning/phases/06-data-integration/deferred-items.md
@.planning/phases/03-feature-engineering/03-CONTEXT.md
@src/pipeline/feature_generator.py
@tests/pipeline/test_feature_generator.py
@CLAUDE.md
</context>

<root_cause>
**Confirmed by reproduction (2026-06-15):**

`data/standard/result.parquet` ships `finish_note` as pandas nullable `string` dtype (Phase 4 cycle-3 #1: nullable dtypes preserved end-to-end). After `load_and_merge()`, `finish_note` stays `string` with `<NA>` (pd.NA) for the 531,320 finished entries.

`generate_target` builds the condlist as:
- `df["finish_note"] == "中"` → pandas nullable `boolean` Series (contains `pd.NA`, NOT native bool)
- Likewise for 失/取/除/降

`np.select(condlist, choicelist, default)` requires each condlist entry to be a **native bool ndarray**. A pandas nullable `boolean` Series with `pd.NA` is rejected: `TypeError: invalid entry 0 in condlist: should be boolean ndarray` at `feature_generator.py:614`.

**Why Kaggle-only corpus did not trip it:** the Phase 3 Kaggle-only corpus carried `finish_note` as plain `object` dtype with Python `None`, so `== "中"` produced a native bool ndarray. The Phase 6 unified corpus preserves the nullable `string` dtype, exposing the latent bug.

**NOT the cause (do NOT chase):** the task brief hypothesized "empty condlist" / "value-range outside Kaggle / NaN not hitting conditions". Reproduction disproves this — condlist has 5 well-formed entries, and there are zero `finish_note` values outside {中,失,取,除,降,NA}. The cause is purely dtype.
</root_cause>

<scope_boundary>
- TOUCH: `src/pipeline/feature_generator.py`, `tests/pipeline/test_feature_generator.py`, `data/feature/*.parquet`.
- DO NOT TOUCH: `data/standard/` (Phase 6 corpus — LOCKED, verified), any Phase 6 code (`src/pipeline/integration*`, `validators.py`, `kaggle_converter.py`, `column_mapping.py`), `src/schemas/*`.
- No new dependencies. Use `python -m pytest` (setuptools env, NOT `poetry run`).
- Do NOT change `result_status` classification semantics. The 6-way mapping (finished/dnf/disqualified/scratched/removed/demoted) and D-12/D-13/D-14 behavior must be non-degenerate vs the Kaggle-only behavior verified by `TestTargetVariable`.
</scope_boundary>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Fix np.select condlist dtype in generate_target (root-cause)</name>
  <files>src/pipeline/feature_generator.py</files>
  <behavior>
    - Existing TestTargetVariable tests (test_position_1..4_target_top3, test_dnf_middle_note, test_scratched_tori_note, test_removed_jo_note, test_disqualified_shitsu_note, test_demoted_kou_note_keeps_position, test_normal_finish_result_status, test_scratched_vs_removed_distinct_status) MUST still pass unchanged — they encode the non-degradation contract.
    - New regression: `generate_target` must not raise when `finish_note` is pandas nullable `string` dtype with `<NA>` values (the unified-corpus condition). Add a unit test `test_generate_target_handles_nullable_string_finish_note` that constructs a DataFrame whose `finish_note` column is explicitly `pd.array([...], dtype="string")` containing `<NA>` plus each of 中/失/取/除/降, then asserts the existing 6-way classification row-for-row.
    - `pd.NA` finish_note → result_status == "finished" (default branch), is_dnf False, exclude_from_training False (unchanged semantics).
  </behavior>
  <action>
    Root-cause fix at `src/pipeline/feature_generator.py` inside `generate_target` (the `np.select` call at line 614). Convert each nullable-boolean condition to a native bool ndarray BEFORE passing to `np.select`, treating `pd.NA` as `False` so NA finish_note rows fall through to the `default="finished"` branch — which is exactly the intended semantics (a finished race with no special note).

    Implementation: replace the bare `conditions` list construction so each comparison is coerced, e.g.
    `conditions = [(df["finish_note"] == note).to_numpy(dtype=bool, na_value=False) for note in ["中","失","取","除","降"]]`.
    Keep `choices` and `default="finished"` unchanged. Do NOT alter the downstream is_dnf / target_top3 / exclude_from_training logic.

    Why `na_value=False`: `pd.NA == "中"` is `pd.NA` (unknown). For classification, an unknown note must NOT match any special-status branch, so it must be `False` → falls through to default "finished". This preserves the D-12/D-13/D-14 contract. Verify non-degradation by running the full `TestTargetVariable` class — all 11 tests must pass unchanged.

    Do NOT add a defensive "if conditions is empty" guard — that is not the root cause and would be dead code (condlist always has 5 entries). The fix is dtype coercion, full stop.

    Add the regression unit test described in `<behavior>` to `tests/pipeline/test_feature_generator.py` inside `TestTargetVariable` (or a new `TestTargetVariableNullableDtype` class directly below it). The test must explicitly construct the nullable string dtype so it cannot silently regress to object dtype.
  </action>
  <verify>
    <automated>python -m pytest tests/pipeline/test_feature_generator.py::TestTargetVariable tests/pipeline/test_feature_generator.py -k "target or Target or nullable" -q</automated>
  </verify>
  <done>
    - `np.select` call no longer receives nullable-boolean Series; each condlist entry is a native bool ndarray.
    - All 11 existing `TestTargetVariable` tests pass unchanged (non-degradation).
    - New nullable-dtype regression test passes.
    - Commit: `fix(03): coerce np.select condlist to native bool for nullable finish_note`
  </done>
</task>

<task type="auto">
  <name>Task 2: Regenerate features on unified corpus + align real-data test expectations</name>
  <files>data/feature/features_train.parquet, data/feature/features_pred.parquet, tests/pipeline/test_feature_generator.py</files>
  <action>
    1. Regenerate features by running the generate() entrypoint against the unified corpus. From the repo root, invoke the pipeline so it reads `data/standard/{race,entry,result}.parquet` (38,009 / 534,953 / 534,953 rows) and writes `data/feature/features_train.parquet` + `data/feature/features_pred.parquet`. Use a direct Python invocation of `src.pipeline.feature_generator.generate(standard_dir=Path("data/standard"), feature_dir=Path("data/feature"))` (the time-series split logic at lines 885-1013 writes both train and pred from the single merged DataFrame — there is no separate split call). Do NOT modify `data/standard/`.

    2. Update real-data test expectations in `tests/pipeline/test_feature_generator.py` to match the unified corpus reality:
       - `TestRealDataIntegration::test_real_data_row_counts` (line ~1987-1996): the assertion `310000 <= len(df) <= 320000` is Kaggle-only. Change the band to `530000 <= len(df) <= 540000` (actual = 534,953). Update the docstring "Test 4: features_train.parquet has ~311,806 rows." to "~534,953 rows (unified corpus)".
       - `TestRealDataIntegration::test_real_data_target_distribution` (line ~2029-2041): the band `0.16 <= rate <= 0.26` — verify against the regenerated file. Proxy from the unified corpus is 0.2141 (target_top3 over valid = excl 取/除), so the existing band is expected to still hold; if the regenerated rate falls outside, widen symmetrically to `[0.16, 0.27]` at most and document the actual value in the docstring. Do NOT narrow the band.
       - `TestRealDataIntegration::test_real_data_column_counts` (line ~1999-2011): unchanged — column count derives from `len(FEATURE_COLUMNS) + 2`, which is source-code-driven, not corpus-driven. Leave as-is.
       - `TestRealDataIntegration::test_real_data_generation` and `TestTemporalInvariance::test_temporal_invariance_real_data`: NO expectation edits — they assert behavior, not specific numbers. They pass once Task 1's fix is in. The temporal-invariance test's pre-2020 cutoff produces 16,634 races / 237,685 entries — the test's own row-count assertion is self-consistent (full vs truncated), so no edit.

    3. Clean up the stale `data/feature/tmp_full/` directory created by the prior failing run of `test_temporal_invariance_real_data` (it is test scratch, not a deliverable) — delete it so it is not committed. Do NOT delete `data/standard/`.

    Do NOT change any assertion in the fixture-based tests (TestEndToEnd, TestTemporalInvariance::test_temporal_invariance_fixture) — they use tmp_path fixtures with fixed 14-row / synthetic data and are corpus-independent.
  </action>
  <verify>
    <automated>python -m pytest tests/pipeline/test_feature_generator.py -q && python -c "import pandas as pd; tr=pd.read_parquet('data/feature/features_train.parquet'); pr=pd.read_parquet('data/feature/features_pred.parquet'); assert 530000 <= len(tr) <= 540000, len(tr); assert len(tr)==len(pr), (len(tr),len(pr)); print('train/pred rows:', len(tr), len(pr))"</automated>
  </verify>
  <done>
    - `data/feature/features_train.parquet` and `features_pred.parquet` regenerated with 534,953 rows each (unified corpus).
    - `test_real_data_row_counts` band updated to [530000, 540000] with corrected docstring.
    - `test_real_data_target_distribution` passes against the regenerated file (band kept or widened only if needed, with actual rate documented).
    - Stale `data/feature/tmp_full/` removed.
    - Commit: `feat(03): regenerate feature layer on unified corpus + align real-data expectations`
  </done>
</task>

<task type="auto">
  <name>Task 3: Verify feature_generator green + audit full suite + write SUMMARY</name>
  <files>.planning/quick/260615-jdx-feature-generator-np-select-condlist-cor/260615-jdx-SUMMARY.md</files>
  <action>
    1. Run the full `tests/pipeline/test_feature_generator.py` module — must be all green (the 2 previously-failing integration tests now pass, the new nullable-dtype test passes, and no existing test regresses).

    2. Run the full test suite `python -m pytest tests/ -q` and confirm the count of failures attributable to feature_generator is ZERO. The pre-fix baseline was "497 passed, 2 failed (the 2 feature_generator integration tests), 1 skipped" per deferred-items.md. Post-fix must be "499 passed, 0 failed, 1 skipped" (or better). If OTHER unrelated failures exist (not feature_generator-attributed), report them verbatim in the SUMMARY but do NOT fix them — they are out of scope for this quick task.

    3. Write `.planning/quick/260615-jdx-feature-generator-np-select-condlist-cor/260615-jdx-SUMMARY.md` using the standard SUMMARY template. Content must cover:
       - **What was broken:** np.select in generate_target rejected pandas nullable boolean Series; root cause is dtype (finish_note is nullable `string` in the unified corpus), NOT "empty condlist" as initially hypothesized.
       - **How it was fixed:** coerce each condlist entry to native bool ndarray via `.to_numpy(dtype=bool, na_value=False)` so pd.NA → False → default "finished" branch (unchanged semantics). 1-line conceptual change.
       - **Non-degradation evidence:** all 11 TestTargetVariable tests pass unchanged.
       - **Feature output scale:** features_train/pred each = 534,953 rows; target_top3 positive rate (valid, excl 取/除) = <actual value from regenerated file, ~0.214>; corpus = race 38,009 / entry=result 534,953, 2015-01-04..2026-05-31.
       - **Full-suite status:** <passed/failed/skipped counts>; list any non-feature_generator failures verbatim with "out of scope — reported only".
       - **Scope respected:** data/standard/ and Phase 6 code untouched.
  </action>
  <verify>
    <automated>python -m pytest tests/pipeline/test_feature_generator.py -q && python -m pytest tests/ -q 2>&1 | tail -5</automated>
  </verify>
  <done>
    - tests/pipeline/test_feature_generator.py: 100% green.
    - Full suite: zero feature_generator-attributed failures (other failures only reported, not fixed).
    - 260615-jdx-SUMMARY.md exists with root cause, fix, output scale, full-suite status.
    - Commit: `docs(260615-jdx): add SUMMARY for feature_generator np.select fix`
  </done>
</task>

</tasks>

<verification>
Phase-level checks for this quick task:
1. `python -m pytest tests/pipeline/test_feature_generator.py -q` → all green (was 2 failed before).
2. `python -c "import pandas as pd; df=pd.read_parquet('data/feature/features_train.parquet'); print(len(df))"` → prints 534,953 (±1).
3. `python -c "import pandas as pd; df=pd.read_parquet('data/feature/features_pred.parquet'); print(len(df))"` → prints 534,953 (±1).
4. `python -m pytest tests/ -q` → feature_generator-attributed failures == 0.
5. `git diff --stat` touches ONLY: `src/pipeline/feature_generator.py`, `tests/pipeline/test_feature_generator.py`, `data/feature/features_train.parquet`, `data/feature/features_pred.parquet`, the SUMMARY file. NO changes under `data/standard/` or any Phase 6 source.
</verification>

<success_criteria>
- np.select TypeError resolved at root (dtype coercion, not surface guard).
- result_status 6-way classification non-degenerate vs Kaggle-only behavior (TestTargetVariable green unchanged).
- features_train.parquet + features_pred.parquet regenerated on unified corpus (534,953 rows each).
- Real-data test expectations aligned to unified-corpus scale.
- feature_generator tests 100% green; full suite has zero feature_generator-attributed failures.
- data/standard/ and Phase 6 code untouched (verified via git diff --stat).
- SUMMARY documents root cause (dtype, not empty condlist), fix, and output scale.
</success_criteria>

<output>
Create `.planning/quick/260615-jdx-feature-generator-np-select-condlist-cor/260615-jdx-SUMMARY.md` when done (Task 3).
</output>
