---
phase: 07
reviewers: [codex]
reviewed_at: 2026-06-15T00:00:00
cycle: 2
previous_cycle_high_count: 7
current_cycle_high_count: 4
plans_reviewed:
  - 07-01-PLAN.md
  - 07-02-PLAN.md
  - 07-03-PLAN.md
  - 07-04-PLAN.md
  - 07-05-PLAN.md
  - 07-06-PLAN.md
  - 07-07-PLAN.md
  - 07-08-PLAN.md
---

# Cross-AI Plan Review — Phase 07 (Model A: Top-3 Probability) — CYCLE 2

> **Convergence loop — Cycle 2 of N.** Plans were replanned in commit `aed9d89` to address the 7 HIGH concerns Codex raised in Cycle 1. This cycle verifies resolution of those 7 HIGHs and surfaces any NEW concerns introduced by the revisions.
>
> **Reviewers invoked:** Codex (Claude skipped — this review was orchestrated from inside the Claude Code runtime, so an independent Claude session would not be truly independent).
>
> **Scope:** All 8 revised plans for Phase 7. Review focus: (a) verify each Cycle-1 HIGH is actually implemented in the revised plan text (not just mentioned), (b) detect new structural problems introduced by the revisions (two-stage retrain, expected_counts semantics, n_splits+1 chunk math, dependency graph, cross-plan metric contracts).

---

## Cycle-1 HIGH Resolution Verdicts (Codex + orchestrator cross-check)

| # | Cycle-1 HIGH concern | Verdict | Evidence in revised plan text |
|---|---|---|---|
| **#1** | `GroupTimeSeriesSplit` fold 0 had empty training set (07-03) | **FULLY RESOLVED** | 07-03 truth + Task 1 implement `n_splits+1` chunk scheme: chunk 0 = warm-up train, chunks 1..n_splits = validation. `test_fold0_train_non_empty` regression guard asserts fold 0 train_idx non-empty. `_compute_fold_sizes` returns `n_splits+1` sizes. |
| **#2** | All-rows OOF contract (322,510) incompatible with temporal CV | **FULLY RESOLVED** | 07-04 `collect_oof_predictions` truth: "OOF 行数 = validation chunks のみ（warm-up chunk 0 除外）". 07-08 acceptance: `OOF parquet 行数 < 322,510`. 07-07 hermetic test `test_oof_parquet_schema_and_row_count` asserts `len(oof) < len(train_fixture)`. |
| **#3** | 07-04 runtime-depends on 07-03 but labeled Wave-1-parallel | **FULLY RESOLVED** | 07-04 frontmatter: `wave: 2`, `depends_on: ["07-01", "07-03"]`. Module-level import `from src.ml.group_timeseries_split import split_train_validation` (lazy import removed). |
| **#4** | 07-02 fixed-count assert breaks 07-07 hermetic E2E | **PARTIALLY RESOLVED** | Bypass mechanism added (`expected_counts` param), BUT contract is internally inconsistent: 07-02 spec lines 98/108 gate bypass on `expected_counts == {}` (empty dict) with type `dict \| None`, while tests (07-02 lines 89/143) and run_train (07-07 line 219) call `expected_counts=[]` (empty list). See HIGH below. |
| **#5** | `config["data"]["feature_columns"]` referenced by 07-04 but absent from YAML | **FULLY RESOLVED** | `feature_columns` made an explicit argument of `collect_oof_predictions` / `train_final_model`. Config key `data.feature_columns` added in 07-07 Task 1. run_train resolves from config and passes as arg. `test_feature_columns_config_consistency` asserts config == FEATURE_COLUMNS. |
| **#6** | `train_final_model` saves model trained on ~80%, not all data | **FULLY RESOLVED** | 07-04 `train_final_model` truth: two-stage — Stage 1 determines `best_iteration` on validation split, Stage 2 refits on ALL rows at that iteration count. `test_train_final_model_two_stage` asserts Stage 2 trains on full df row count. |
| **#7** | 07-08 permits hyperparameter retuning after holdout inspection | **FULLY RESOLVED** | 07-08 Task 2 resume-signal explicitly forbids retune; fixed-failure flow documented (record → adjust within CV only → fresh unused period or Phase 9). evaluation_report.md must include the prohibition note. |

**Cycle-1 tally: 6 of 7 HIGHs FULLY RESOLVED; 1 PARTIALLY RESOLVED (#4 — sentinel inconsistency).**

---

## Codex Review

### Summary

Cycle 1's 7 HIGH concerns are mostly converged: 6 are fully resolved and the CV/OOF/final-retrain/feature_columns/holdout-envelope design is now internally coherent. However, the revisions introduced or exposed four HIGH-severity issues that would cause execution halt or silent integrity loss if implemented as written: (1) the runtime temporal-order safety net is dead code on the actual execution path because `load_features()` never sorts and the splitter's date assertion only fires when `X` carries `race_date`, which trainer excludes; (2) the `expected_counts` bypass sentinel is inconsistent between spec (`{}`) and call sites (`[]`); (3) `run_train` never writes `oof_rows` into `metrics.json` despite 07-08 requiring it; (4) ROADMAP success criteria #1/#3 diverge from the plans' locked windows and reference-only baseline stance without ROADMAP.md being updated. The design has materially improved, but implementation should not start until these are fixed.

### Strengths

- Warm-up-inclusive expanding-window CV contract is now explicit and testable (07-03 n_splits+1 chunks).
- OOF excludes warm-up, preventing in-sample contamination of the Isotonic calibrator (07-04/07-07/07-08 consistent).
- Final-model two-stage full retrain is concrete and tested (07-04 Stage 1 → Stage 2 on all rows).
- `feature_columns` ownership and argument routing are unambiguous (07-07 resolves from config, passes as explicit arg; config == FEATURE_COLUMNS consistency test).
- Holdout single-use "envelope" statistical contract is now written down with a fixed-failure flow (07-08 resume-signal).
- Hermetic E2E and real-data phase gate are cleanly separated (expected_counts bypass vs production assert).

### Concerns

- **HIGH — Runtime temporal-order assertion is dead code on the execution path (new).** `load_features()` (07-02 line 101) converts `race_date` to datetime but performs no `sort_values`. The feature parquet's row order is not guaranteed chronological. The GroupTimeSeriesSplit runtime assertion (07-03 line 97) only fires when "X が DataFrame で race_date 列を持つ場合", but the trainer passes `X = df[feature_columns]` (07-04 line 103) and `race_date` is in `drop_columns` (07-07 line 111). Therefore the temporal-leakage safety net is guaranteed to be skipped on every real run, and MODA-02 / ROADMAP success criterion #2 ("no future data in any training fold") rests entirely on an unsorted-row assumption. *Minimal fix:* (a) add `sort_values(["race_date","race_id","horse_number"])` + `reset_index(drop=True)` in `load_features()`; (b) pass `dates`/`df` to the splitter so the assertion always runs, or make `race_date` available to the splitter independently of `feature_columns`.

- **HIGH — `expected_counts` bypass sentinel inconsistent: `{}` vs `[]` (carry-over from Cycle 1, HIGH #4).** The 07-02 implementation spec gates bypass on `expected_counts == {}` (empty dict) with declared type `dict | None` (07-02 lines 98/108, 07-07 line 161), but the tests (07-02 lines 89/143) and `run_train` (07-07 line 219) invoke `expected_counts=[]` (empty list). An empty list is not `None` and is not `== {}`; depending on the branch logic it will either fall into the custom-dict path and fail on key access, or silently not bypass. *Minimal fix:* pick one sentinel (`expected_counts=[]` or `expected_counts={}`) and use it identically across spec, signature, tests, and run_train; or replace with `skip_count_assert: bool = False`.

- **HIGH — `oof_rows` never added to `metrics.json` by run_train (new).** 07-07 Step 9 (line 173) only adds `baseline_auc` to the metrics dict; the `oof_rows` write that 07-08's own Codex HIGH #2 fix depends on is absent from 07-07's metrics construction. 07-08's automated verify (line 127) asserts `'oof_rows' in m` and will fail with "oof_rows missing from metrics.json (Codex HIGH #2)". This is a cross-plan contract hole introduced by the Cycle-1 #2 fix landing in 07-08 but not propagating to 07-07's metrics writer. *Minimal fix:* in run_train, `metrics["oof_rows"] = len(oof_df)` before serializing metrics.json.

- **HIGH — ROADMAP success criteria not satisfied as written (carry-over from Cycle 1 MEDIUM, escalated).** ROADMAP.md Phase 7 still requires (1) training on **2015-2023** data (plans use 2018-2024 per D-05 LOCKED window) and (3) beating the popularity baseline on **OOF** predictions (plans compute baseline on **holdout** and demote "beat baseline" to reference-only per D-07/D-08). The underlying technical decisions are sound and documented in the plans (D-05/D-07/D-08), but ROADMAP.md itself has not been updated, so declaring Phase 7 done would not satisfy the 4 success criteria as recorded. *Minimal fix:* formally update ROADMAP.md Phase 7 success criteria (or record a divergence ADR) before the 07-08 phase gate.

- **MEDIUM — Same-`race_date` races can straddle a chunk boundary (new).** Chunks are race-grouped, not date-blocked. Two races sharing a `race_date` that land on opposite sides of a fold boundary violate the `max(train_date) < min(val_date)` assertion even though no leakage occurs. *Fix:* block same-`race_date` races into the same chunk (Cycle-1 Codex suggestion already flagged this).

- **MEDIUM — `--run-gated` pytest option is not registered (new).** 07-02/07-07 reference `--run-gated` / `RUN_GATED=1` and `@pytest.mark.gated`, but no `pytest_addoption` or marker registration exists in the repo or in Wave 0. The verify commands will fail with "unrecognized arguments: --run-gated". *Fix:* add `pytest_addoption` + `conftest` skip hook in 07-01.

- **MEDIUM — D-09 race-level Top-3 recall still not implemented (carry-over from Cycle 1).** 07-06 lists D-09 in `read_first` but `evaluate()` returns and the tests assert no race-level Top-3 recall. ROADMAP/MODA imply it.

- **LOW — evaluation_report.md retune-prohibition note is required by 07-08 but not in 07-07's report-generation spec (new).** 07-07 Step 10 ⑥ only specifies the D-08 純粋予測×EV note; 07-08 requires the holdout-retune-prohibition note. Cross-plan gap.

### Suggestions

1. Sort in `load_features()`: `df.sort_values(["race_date","race_id","horse_number"]).reset_index(drop=True)` and assert monotonicity; make the splitter's date assertion always run by passing `dates` explicitly.
2. Block same-`race_date` races into one chunk to make the date-boundary assertion achievable.
3. Unify the `expected_counts` bypass sentinel (`[]` or `{}`) across spec/signature/tests/run_train, or switch to a boolean flag.
4. Add `metrics["oof_rows"] = len(oof_df)` to run_train before metrics.json serialization.
5. Update ROADMAP.md Phase 7 success criteria (window + baseline comparison scope) or file a divergence note before 07-08.
6. Register `--run-gated` and the `gated` marker in Wave 0 conftest.
7. Add D-09 race-level Top-3 recall to 07-06's `evaluate()`.
8. Add the holdout-retune-prohibition note to 07-07's evaluation_report.md generation spec.

### Risk Assessment

**Overall Risk: HIGH.** The Cycle-1 structural problems (CV fold-0, OOF-vs-temporal, dependency graph, fixed-count assert, feature_columns, partial retrain, holdout retune) are largely converged. However, three of the four remaining HIGHs are concrete execution-path or cross-plan contract failures that would halt implementation or silently void the leakage guarantee if built as specified: the temporal assertion is dead code, the `expected_counts` sentinel mismatches, and `oof_rows` is required but never written. These are fixable with small, localized plan edits; they do not invalidate the overall design.

### Per-Plan Notes

- **07-02:** Add the sort step and unify the `expected_counts` sentinel. Most urgent for the leakage guarantee.
- **07-03:** Make the temporal assertion always run (do not gate on `race_date` being a column of `X`).
- **07-04:** Confirmed two-stage retrain + feature_columns arg + OOF=val-chunks are correctly specified. Pass dates to splitter.
- **07-07:** Add `metrics["oof_rows"] = len(oof_df)`; specify the retune-prohibition note in the report; forward `expected_counts` to `load_features` with the unified sentinel.
- **07-08:** Sound as a phase gate; blocked only by upstream 07-07 `oof_rows` gap and the ROADMAP update.

---

## Consensus Summary

> Single reviewer (Codex). "Agreed" items reflect Codex's findings cross-checked against the revised plan text and ROADMAP/CONTEXT contracts by the orchestrator. All Cycle-1 HIGH verdicts were independently verified against the plan text by reading the relevant sections.

### Agreed Strengths (plan text + reviewer)

- 6 of 7 Cycle-1 HIGHs are fully implemented in the revised plan text (CV fold-0, OOF-warm-up exclusion, dependency graph, feature_columns routing, two-stage retrain, holdout retune prohibition).
- Expanding-window CV with warm-up chunk is now a coherent, tested contract spanning 07-03/04/07/08.
- Two-stage final retrain genuinely trains on all 2018-2024 rows (Stage 1 best_iteration → Stage 2 full refit).
- `feature_columns` has a single owner (run_train resolves from config, passes explicitly); config/FEATURE_COLUMNS consistency is tested.

### Agreed Concerns (highest priority — Cycle 2)

1. **[HIGH, new] Runtime temporal-order assertion is dead code on the execution path** — `load_features` doesn't sort; splitter date-assertion gated on `race_date` being a column of `X`, which trainer excludes. Undermines MODA-02 / ROADMAP #2.
2. **[HIGH, carry-over from Cycle 1 #4] `expected_counts` bypass sentinel inconsistent (`{}` spec vs `[]` call sites)** — hermetic E2E will fail as written.
3. **[HIGH, new] `oof_rows` never written to metrics.json by run_train** — 07-08 verify asserts its presence and will fail.
4. **[HIGH, carry-over from Cycle 1 MEDIUM, escalated] ROADMAP success criteria #1/#3 diverge from plans and ROADMAP.md is not updated** — declaring Phase 7 done would not satisfy the recorded 4 criteria.
5. **[MEDIUM, new] Same-`race_date` races can straddle chunk boundaries** — makes the date assertion unachievable.
6. **[MEDIUM, new] `--run-gated` pytest option/marker not registered** — verify commands fail.
7. **[MEDIUM, carry-over from Cycle 1] D-09 race-level Top-3 recall not implemented** in 07-06.
8. **[LOW, new] evaluation_report.md retune-prohibition note required by 07-08 but absent from 07-07 report spec.**

### Divergent Views

- None — single reviewer. The ROADMAP-divergence HIGH is partly a traceability/process concern (the underlying D-05/D-07/D-08 decisions are deliberate and statistically grounded), so a planner may choose to treat it as a documentation task rather than a design defect; it is listed HIGH here because the recorded success criteria are not literally met without a ROADMAP update.

### Convergence Status

- **Cycle 1 HIGHs:** 6 FULLY RESOLVED, 1 PARTIALLY RESOLVED (#4 sentinel inconsistency).
- **Cycle 2 NEW HIGHs:** 3 (temporal assertion dead code; `oof_rows` missing in run_train; plus #4 escalated to its own remaining HIGH).
- **Remaining unresolved HIGH count: 4.**
- **Recommendation:** One more replan cycle to close the 4 HIGHs (all are small, localized edits) before implementation.
