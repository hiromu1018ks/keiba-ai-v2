---
phase: 07
reviewers: [codex]
reviewed_at: 2026-06-15T12:30:23Z
cycle: 3
previous_cycle_high_count: 4
current_cycle_high_count: 1
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

# Cross-AI Plan Review — Phase 07 (Model A: Top-3 Probability) — CYCLE 3 (FINAL)

> **Convergence loop — Cycle 3 of 3.** The second replan targeted the 4 HIGHs that Cycle 2 left open. This cycle verifies resolution of those 4 HIGHs and surfaces any NEW HIGH-severity concerns introduced by the revisions.
>
> **Reviewers invoked:** Codex (Claude skipped — this review was orchestrated from inside the Claude Code runtime, so an independent Claude session would not be truly independent).
>
> **Scope:** All 8 revised plans for Phase 7. Review focus: (a) verify each Cycle-2 HIGH is actually implemented in the revised plan text (not just mentioned), (b) detect new structural problems introduced by the revisions (temporal-assertion vs chunk-boundary interaction, sentinel branches, `oof_rows` contract, ROADMAP alignment).
>
> **Orchestrator data verification:** The orchestrator independently confirmed against `data/feature/features_train.parquet` that JRA has **multiple races per `race_date` without exception** — 23,288 training races across only 1,236 unique dates (10-36 races/date, mean 30.75, **zero single-race dates**). This is load-bearing evidence for the one remaining HIGH and was cross-checked rather than taken on faith.

---

## Cycle-2 HIGH Resolution Verdicts (Codex + orchestrator cross-check)

| # | Cycle-2 HIGH concern | Verdict | Evidence in revised plan text |
|---|---|---|---|
| **#1** | Temporal-order assertion was dead code on the execution path | **PARTIALLY RESOLVED** | The dead-code defect itself is fixed: `07-02` Task 1 `sort_values(["race_date","race_id","horse_number"]).reset_index(drop=True)` + `is_monotonic_increasing` assert + retains the `race_date` column; `07-03` Task 1 `split(X, y, groups, dates=None)` takes `dates` as an explicit arg and asserts `max(dates[train_idx]) < min(dates[val_idx])` whenever `dates` is passed (independent of `X` columns); `07-04` Task 1 `collect_oof_predictions` calls `splitter.split(X, y, groups=race_ids, dates=df["race_date"])`, with `test_collect_oof_passes_dates_to_splitter` spy-verifying the forwarding. The assertion is now live on the real path. **BUT the strict `<` assertion conflicts with race-count-based chunking** (see NEW HIGH below) and will halt the production 5-fold run. The fix solved the dead-code problem and introduced a real halt defect; net verdict PARTIALLY RESOLVED. |
| **#2** | `expected_counts` bypass sentinel inconsistent (`{}` spec vs `[]` call sites) | **FULLY RESOLVED** | `07-02` Task 1: unified sentinel `None`=production assert / `[]` (empty list)=bypass / non-empty dict=custom / `{}` (empty dict) rejected with TypeError; branch logic `if expected_counts is None: …; elif isinstance(expected_counts, list) and len==0: bypass; elif isinstance(expected_counts, dict): custom; else: TypeError`; acceptance criterion `grep -cE "expected_counts == \{\}" … == 0`. `07-07` run_train signature `expected_counts: dict | list | None = None` forwards identically; hermetic E2E calls `expected_counts=[]`; T-07-07-10 threat entry documents the contract. Consistent across spec/signature/tests/run_train/E2E. |
| **#3** | `oof_rows` never written to `metrics.json` by run_train | **FULLY RESOLVED** | `07-07` Task 2 **Step 9b** explicitly writes `metrics["oof_rows"] = int(len(oof_df))` before serialization; acceptance `grep -cE "metrics\[.oof_rows.\]" … >= 1`; `test_oof_parquet_schema_and_row_count` asserts `metrics.json` `oof_rows` exists, is int, and equals the OOF parquet row count. `07-08` Task 1 verify asserts `'oof_rows' in m` and `m['oof_rows'] < 322510`. Producer (`07-07`)/consumer (`07-08`) contract identical: key=`oof_rows`, type=`int`, computation=`len(oof_df)`. |
| **#4** | ROADMAP success criteria diverged from LOCKED decisions (D-05/D-07/D-08) | **FULLY RESOLVED** | `ROADMAP.md` Phase 7 section verified updated: criterion #1 = "trained on **2018-2024 data** with temporal splits (D-05/D-01)"; criterion #3 = baseline on **holdout** as **reference information**, explicitly "beating the baseline is NOT a required success gate"; criterion #2 references temporal-order enforcement (Cycle-2 HIGH #1); criterion #4 references `oof_rows` recording (Cycle-2 HIGH #3). Stale "2015-2023" / "beat baseline on OOF" wording is gone. ROADMAP text now literally matches the plans' LOCKED decisions. |

**Cycle-2 tally: 3 of 4 HIGHs FULLY RESOLVED; 1 PARTIALLY RESOLVED (#1 — the fix introduced a new halt defect).**

---

## Codex Review

### 1. Cycle-2 HIGH Resolution Verdicts

| # | concern | verdict | plan-text evidence |
|---|---|---|---|
| 1 | Temporal-order assertion was dead code | **PARTIALLY RESOLVED** | `07-02 Task 1`: `sort_values(["race_date", "race_id", "horse_number"])` and retaining `race_date`. `07-03 Task 1`: `split(..., dates=None)` and `assert max(dates[train_idx]) < min(dates[val_idx])`. `07-04 Task 1`: `splitter.split(..., dates=df["race_date"])`. The assertion is now live, but chunk boundaries are still computed by race count and may split races from the same `race_date`, causing the strict `<` assertion to halt execution. |
| 2 | `expected_counts` sentinel inconsistency | **FULLY RESOLVED** | `07-02 Task 1`: "`None`=production assert / `[]`=bypass / non-empty dict=custom" and "`{}`（空 dict）は受け付けない". `07-07 run_train`: identical signature and forwarding, with hermetic E2E calling `expected_counts=[]`. |
| 3 | `oof_rows` missing from `metrics.json` | **FULLY RESOLVED** | `07-07 Task 2, Step 9b`: `metrics["oof_rows"] = int(len(oof_df))`. `07-07 Task 3`: test compares the JSON value with the actual OOF parquet row count. `07-08 Task 1`: verifies `'oof_rows' in m` and OOF rows `< 322510`. |
| 4 | ROADMAP criteria diverged from LOCKED decisions | **FULLY RESOLVED** | `ROADMAP Phase 7 Success Criteria #1`: "trained on **2018-2024 data**". Criterion #3: baseline comparison on **holdout as reference information**, explicitly not a required gate. Criteria #2 and #4 also mention temporal enforcement and `oof_rows`. |

### 2. Summary

Three carry-over HIGHs are fully resolved. The temporal assertion is correctly connected to the real trainer path, but its strict date comparison conflicts with race-count chunking: a fold boundary falling inside one race day will cause an assertion failure. This leaves one unresolved HIGH and blocks implementation approval until date-block boundaries are specified.

### 3. Strengths

- Producer/consumer contracts are explicit across `07-02`, `07-04`, `07-07`, and `07-08`.
- OOF warm-up exclusion is consistently reflected in training, calibration, artifacts, and verification.
- Final-model training correctly uses two stages and refits on all 2018–2024 rows.
- Holdout calibration and retuning restrictions preserve the calibration guarantee.
- ROADMAP criteria now match D-05, D-07, and D-08.

### 4. Concerns

- **[HIGH|new] Same-day fold boundaries can halt CV.**
  `07-03` creates chunks from ordered `race_id` counts, not unique `race_date` blocks, while asserting `max(train_dates) < min(val_dates)`. JRA has multiple races per date, so a boundary can place races from the same date on both sides and fail the strict assertion.

- **[MEDIUM|new] Empty-dict rejection should be made algorithmically explicit.**
  `07-02 Task 1` shows `elif isinstance(expected_counts, dict): <custom assert>`, while separately requiring `{}` to raise `TypeError`. Add a non-empty condition to remove implementation ambiguity.

- **[MEDIUM|new] Gated-test invocation is inconsistent.**
  Plans register a `gated` marker and mention `RUN_GATED=1`, but verification commands use `--run-gated`; no pytest option registration is planned.

- **[MEDIUM|new] Early-stopping tests may be nondeterministic.**
  Requiring `best_iteration_ < 50` on a tiny synthetic dataset does not guarantee early stopping will fire.

- **[LOW] Artifact counts are described as six although seven files are individually verified.**

### 5. Suggestions

1. In `07-03`, construct chunks from complete `race_date` blocks, then map those date blocks back to race IDs. Never split one date across train and validation.
2. Add a regression test with multiple races on the boundary date and verify strict temporal order without an assertion failure.
3. Specify the sentinel branch as:
   ```python
   elif isinstance(expected_counts, dict) and expected_counts:
       ...
   else:
       raise TypeError(...)
   ```
4. Either implement a `--run-gated` pytest option or consistently use `RUN_GATED=1`.
5. Test callback configuration and `best_iteration_` validity without requiring early stopping to occur on every synthetic fixture.

### 6. Risk Assessment

**HIGH.** Calibration and artifact contracts are otherwise strong, but the current splitter can halt the real five-fold training run whenever a chunk boundary falls within a racing date.

### 7. Per-Plan Notes

- **07-01:** Sound environment and test scaffolding; gated execution convention needs alignment.
- **07-02:** Correct sorting, date retention, leakage audit, and sentinel contract.
- **07-03:** Live temporal assertion added, but chunking must preserve whole `race_date` blocks.
- **07-04:** Correctly forwards `dates` and excludes warm-up rows from OOF.
- **07-05:** OOF-only isotonic calibration contract is coherent.
- **07-06:** Evaluation and reference-only popularity baseline match locked decisions.
- **07-07:** Integration contracts, `oof_rows`, and hermetic bypass are well specified.
- **07-08:** Phase gate is comprehensive and correctly prohibits holdout retuning.

### 8. Convergence Status

**UNRESOLVED HIGHs: 1**

**Recommendation: NO-GO** until `07-03` defines date-block-aware fold boundaries and adds a same-date boundary regression test.

---

## Orchestrator Cross-Check (Claude Code)

The orchestrator independently verified Codex's single HIGH against the plan text and the real data, because the HIGH blocks the production run and must not be inflated or under-reported.

### Why Codex's HIGH is valid (not a misreading)

1. **Plan text (`07-03` Task 1, action step (2)):** `_compute_fold_sizes(n_groups)` computes chunk sizes by **race count** — `base = n_groups // (n_splits + 1), rem = n_groups % (n_splits + 1), return [base + (1 if i < rem else 0) for i in range(n_splits + 1)]`. Boundaries are `np.cumsum(fold_sizes)` on the ordered `unique_groups` array. Nothing in the algorithm references `race_date` when drawing boundaries. The Cycle-1 Codex *suggestion* "Optionally block same-race_date into the same time block" (quoted in `07-03` `read_first`) was **not implemented**.

2. **Plan text (assertion):** `assert max(dates[train_idx]) < min(dates[val_idx])` is **strict `<`**. It fires per fold whenever `dates` is passed, and `07-04` always passes `dates=df["race_date"]` on the real path.

3. **Real data (`data/feature/features_train.parquet`, verified by the orchestrator):** 23,288 training races span only **1,236 unique `race_date`s**. Every date has **10-36 races** (mean 30.75). **There are zero single-race dates in JRA.** Multiple races per date is not an edge case — it is the universal case.

4. **Consequence:** With 6 chunks over 1,236 dates (~206 dates/chunk) and 5 internal boundaries drawn at arbitrary race indices, the probability that all 5 boundaries land exactly on a date boundary is effectively zero. On the real 5-fold run, at least one fold will split races from a shared date, `max(train_dates) == min(val_dates)`, and the strict `<` assertion raises `AssertionError`, halting `python -m src.ml.run_train` in `07-08` Task 1. This is an **execution-halt defect on the production pipeline** — a genuine HIGH by the severity bar (execution halt).

5. **Was this flagged before?** Yes. Cycle 2 Codex raised it as a **MEDIUM** ("Same-`race_date` races can straddle a chunk boundary … makes the date assertion unachievable"). It was **not addressed** in the second replan. The Cycle-2 HIGH #1 fix (making the assertion live on the real path) **promoted** this latent issue: in Cycle 2 the assertion was dead code so the straddle was theoretical; in Cycle 3 the assertion is live, so the straddle halts execution. This is a legitimate escalation **introduced by the HIGH #1 fix**, correctly classified `[HIGH|new]`.

### Minimal fix (small, localized — does not invalidate the design)

In `07-03`, change `_compute_fold_sizes` and the boundary loop to be **date-block-aware**: group `unique_groups` by their `race_date`, draw chunk boundaries on the ordered list of unique `race_date`s (so each `race_date` block is atomic), then expand each date block to its constituent `race_id`s. Add a regression test (`test_same_date_not_split_across_boundary`) that constructs a fixture with multiple races on a candidate boundary date and asserts the strict `max(train_dates) < min(val_dates)` passes. The `n_splits+1` warm-up contract, OOF-excludes-warm-up contract, and all other Cycle-1/Cycle-2 fixes are unaffected.

### Verdict on the other 3 carry-over HIGHs

Cross-checked independently by reading the plan text — all three are FULLY RESOLVED as Codex states. Evidence summarized in the verdict table above.

### MEDIUMs (carry-over, fair, below the HIGH bar)

- **`--run-gated` not registered as a pytest option** (carry-over from Cycle 2 MEDIUM). `07-01` Task 2 adds the `gated` *marker* to `[tool.pytest.ini_options] markers` and references `RUN_GATED=1`, but no `pytest_addoption` / skip-hook for the `--run-gated` *flag* is planned. The gated verify commands use `--run-gated 2>/dev/null || echo "gated tests require RUN_GATED=1"`, so the env-var path still works and the phase is not blocked, but a stray `--run-gated` without the option registered would error. Test-runner friction only; no execution halt of the production path, no leakage.
- **D-09 race-level Top-3 recall** still listed in `07-06` `read_first` but not returned by `evaluate()` (carry-over from Cycle 1/2 MEDIUM). No regression vs Cycle 2.
- **Empty-dict branch ambiguity** (Codex MEDIUM #2) and **early-stopping test nondeterminism** (Codex MEDIUM #4) — fair, small edits, below HIGH.

---

## Consensus Summary

> Single reviewer (Codex) plus orchestrator cross-check. The single HIGH was independently validated by the orchestrator against the real feature parquet (1,236 unique dates, mean 30.75 races/date, zero single-race dates) and the `07-03` plan text.

### Agreed Strengths (plan text + reviewer + orchestrator)

- 3 of 4 Cycle-2 HIGHs are fully implemented in the revised plan text (`expected_counts` sentinel unification, `oof_rows` producer/consumer contract, ROADMAP alignment with D-05/D-07/D-08).
- The temporal-order assertion is genuinely live on the real execution path (sort + `dates` explicit arg + forwarding) — the dead-code defect from Cycle 2 is solved.
- OOF warm-up exclusion is consistent end-to-end (07-03 chunks → 07-04 collect → 07-05 calibrate → 07-07/08 assert `< 322510`).
- Two-stage full retrain (Stage 1 best_iteration → Stage 2 refit on all rows) and holdout retune prohibition are intact.

### Agreed Concerns (highest priority — Cycle 3)

1. **[HIGH, new — introduced by the Cycle-2 HIGH #1 fix] Same-day fold boundaries will halt the production 5-fold run.** `07-03` chunks by race count while asserting strict `max(train) < min(val)` on `race_date`; JRA has multiple races per date without exception, so a boundary lands inside a date and the assertion fires. *Fix: date-block-aware chunking + same-date boundary regression test.*
2. **[MEDIUM, new] Empty-dict sentinel branch is ambiguous** — `elif isinstance(expected_counts, dict)` should be `and expected_counts`.
3. **[MEDIUM, carry-over] `--run-gated` flag not registered** as a pytest option (only the `gated` marker + `RUN_GATED=1` env var exist).
4. **[MEDIUM, new] Early-stopping test (`best_iteration_ < n_estimators`) may be nondeterministic** on tiny fixtures.
5. **[MEDIUM, carry-over] D-09 race-level Top-3 recall** still not returned by `evaluate()`.
6. **[LOW] Artifact count described as "6" but 7 files verified individually.**

### Divergent Views

- None material. The orchestrator's independent data verification reinforces rather than contradicts Codex's single HIGH.

### Convergence Status

- **Cycle-2 HIGHs:** 3 FULLY RESOLVED, 1 PARTIALLY RESOLVED (#1 — the dead-code fix is correct but introduced a date-boundary halt defect).
- **Cycle-3 NEW HIGHs:** 1 (same-date fold boundary; introduced by the Cycle-2 HIGH #1 fix).
- **Remaining unresolved HIGH count: 1.**
- **Recommendation:** One small, localized edit to `07-03` (date-block-aware chunking + regression test) closes the final HIGH. The fix does not disturb any other Cycle-1/Cycle-2 resolution. After that edit, Phase 7 is GO for implementation.
