---
phase: 07
reviewers: [codex]
reviewed_at: 2026-06-15T12:51:55Z
cycle: 4
previous_cycle_high_count: 1
current_cycle_high_count: 0
plans_reviewed:
  - 07-03-PLAN.md
---

# Cross-AI Plan Review — Phase 07 (Model A: Top-3 Probability) — CYCLE 4 (CONVERGENCE)

> **Convergence loop — Cycle 4 of 4.** Cycles 1-3 resolved 10 of 11 HIGHs. Cycle 3 left exactly 1 HIGH: same-day fold boundaries would halt the production 5-fold CV run because `07-03` chunked by race count while asserting strict `max(train_dates) < min(val_dates)`, and JRA has multiple races per `race_date` without exception (mean 30.75 races/date, zero single-race dates over 23,288 training races / 1,236 unique dates).
>
> The Cycle 4 replan made a **TARGETED edit to `07-03-PLAN.md` ONLY** (commit `d75ae06`, +49/-29 lines, single file). No other plan was touched. Chunking is now **date-block-aware** — boundaries are drawn on an ordered unique `race_date` array so no `race_date` is ever split across a train/val boundary, making `max(train_dates) < min(val_dates)` hold by construction. A regression test `test_same_date_not_split_across_fold_boundary` was added.
>
> **Reviewers invoked:** Codex (Claude skipped — orchestrated from inside the Claude Code runtime, so an independent Claude session would not be truly independent).
>
> **Scope:** Verification that the single Cycle-3 HIGH is now FULLY RESOLVED, and that the date-block fix introduced no NEW HIGH-severity concern (execution-halt or calibration-leakage). The other 7 plans passed Cycle 3 and are not re-litigated.

---

## Cycle-3 HIGH Resolution Verdict (Codex + orchestrator cross-check)

| Cycle-3 HIGH concern | Verdict | Plan-text evidence |
|---|---|---|
| **Same-day fold boundaries will halt the production 5-fold run** (`07-03` chunked by race count while asserting strict `max(train_dates) < min(val_dates)`; JRA has multiple races per date without exception) | **FULLY RESOLVED** | `07-03` Task 1, action (2): `unique_dates = pd.unique(dates)` obtained in occurrence order (caller sorts by `race_date` ascending, guaranteed by `07-02` `sort_values([...])` + `is_monotonic_increasing` assert). `_compute_date_block_sizes(n_dates)` divides the ordered unique-date array into `n_splits+1` date-block chunks (each chunk is a complete block of dates; no date is split). `date_boundaries = np.cumsum(date_block_sizes)` indexes the ordered-date array, NOT race counts. Per fold `i`: `val_dates_block = unique_dates[val_start:val_end]` is a complete date block; `train_dates_block = unique_dates[:val_start]` is the cumulative/expanding-window set of earlier date blocks (warm-up chunk 0 always included, non-empty since base >= 1). Same `race_date` → same chunk by construction → `set(train_dates) & set(val_dates) == empty` for every fold → since dates are ordered ascending, `max(train_dates) < min(val_dates)` is a genuine invariant. Strict assertion never raises on the production path. Regression test `test_same_date_not_split_across_fold_boundary` (Task 2) uses a fixture where **every date has multiple races** (JRA's universal case) and asserts both (a) no date appears in both train and val of any fold, and (b) the strict assertion never raises. Threat register T-07-03-05 documents the mitigation. |

**Cycle-3 tally: 1 of 1 HIGH FULLY RESOLVED.**

### Orchestrator independent cross-check (why the fix is correct, not just present)

1. **Boundary indexing — no off-by-one.** `date_block_sizes` has `n_splits+1` elements; `date_boundaries = np.cumsum(...)` has `n_splits+1` cumulative sums, the last equal to `n_dates`. For folds `i = 0..n_splits-1`, both `date_boundaries[i]` and `date_boundaries[i+1]` are valid. `val_start = date_boundaries[i]`, `val_end = date_boundaries[i+1]`. Correct.

2. **Expanding-window / cumulative train preserved.** `train_dates_block = unique_dates[:val_start]` = chunks 0..i (warm-up + all earlier val chunks). Fold 0 train = chunk 0 = `unique_dates[:date_boundaries[0]]`, non-empty. Codex HIGH #1 (fold-0 empty train) regression intact.

3. **Same-race invariant preserved.** date-block → race_id expansion is atomic; `np.isin(groups, ...)` keeps every row of a `race_id` together. test_same_race_same_fold and test_no_boundary_split still apply.

4. **`n_dates < n_splits+1` ValueError cannot fire on production data.** 1,236 unique dates ≫ 6 chunks.

5. **Strict `<` holds by construction.** train dates and val dates are disjoint slices of an ascending-ordered unique-date array; `max(train_dates) < min(val_dates)` necessarily.

6. **Scope confirmed** via `git show d75ae06 --stat`: only `07-03-PLAN.md` changed (+49/-29). The other 7 plans' Cycle-1/2/3 resolutions are untouched.

---

## Codex Review

### 1. Cycle-3 HIGH Resolution Verdict

| Verdict | Plan-text evidence |
|---|---|
| **FULLY RESOLVED** | Chunks are explicitly computed from ordered `unique_dates`, not race counts (`07-03-PLAN.md:101`). Boundaries use cumulative date-block sizes, with train=`unique_dates[:date_boundaries[i]]` and validation=`unique_dates[date_boundaries[i]:date_boundaries[i+1]]` (`07-03-PLAN.md:103`). Therefore dates cannot straddle a boundary and strict `<` holds for sorted input. |

### 2. Summary

The targeted Cycle-3 HIGH is fully resolved in the plan. The boundary indexing is correct, expanding-window training remains cumulative, race IDs are expanded atomically from date blocks, and the real dataset's 1,236 dates safely exceeds the required six chunks. No new HIGH-severity execution-halt or calibration-leakage issue was introduced.

### 3. Strengths

- `val_start=date_boundaries[i]` and `val_end=date_boundaries[i+1]` correctly select chunk `i+1`.
- Fold 0 trains on complete chunk 0; subsequent folds accumulate all earlier chunks.
- `np.isin(groups, ...)` keeps every row of a `race_id` together.
- The regression test explicitly checks date-set disjointness and successful strict ordering (`07-03-PLAN.md:153`).
- `n_dates < n_splits+1` cannot trigger on the verified production data.

### 4. Concerns

- **[MEDIUM|new]** The legacy `dates=None` path is underspecified. When `X` lacks `race_date`, the plan says assertion is skipped, but the algorithm still immediately calls `pd.unique(dates)` (`07-03-PLAN.md:100`). This conflicts with the claimed backward compatibility, although production always supplies `dates`.
- **[LOW|new]** The regression fixture's "4-5 races per date" is not deterministic enough to guarantee that the old race-count algorithm would split a date. Equal counts could accidentally align boundaries.
- **[LOW|new]** The race ID to date mapping assumes, but does not explicitly validate, that one `race_id` never maps to multiple dates.

### 5. Suggestions

1. Require `dates` when `X` lacks `race_date`, raising a clear `ValueError`; remove the ambiguous "assertion only is skipped" behavior.
2. Use deliberately uneven race counts per date (e.g. `[4, 5, 4, 5, 4, 5]`) so the old race-count splitter necessarily fails the regression test.
3. Validate that each `race_id` maps to exactly one `race_date`.

### 6. Risk Assessment

**LOW.** The production path and targeted date-boundary invariant are correctly specified. Remaining issues concern legacy behavior and test robustness, not production execution or calibration leakage.

### 7. Convergence Status

**Unresolved HIGHs: 0**

**Recommendation: GO** for implementation.

---

## Orchestrator Cross-Check (Claude Code)

The orchestrator independently verified Codex's FULLY-RESOLVED verdict by reading the `07-03` plan text line-by-line (action steps, assertions, test, threat model, acceptance criteria) and confirming the boundary/indexing/expanding-window logic is not only present but correct. Findings reinforce rather than contradict Codex.

### Why the 3 new concerns are correctly below the HIGH bar

- **MEDIUM — legacy `dates=None` path underspecified (Codex).** Real plan-text inconsistency: `07-03` line 100-101 says "if `dates` is None and X has `race_date`, use it" but then line 101 unconditionally calls `pd.unique(dates)` which would raise `TypeError` on `None`. This lives entirely on the **legacy/unused** code path — the production trainer (`07-04` `collect_oof_predictions`) always passes `dates=df["race_date"]`, and the hermetic E2E (`07-07`) passes it too. No execution-halt of the production pipeline, no calibration leakage. Fair MEDIUM; the executor should tighten this (Codex suggestion #1: require `dates` when X lacks `race_date`, raise ValueError instead of silently skipping the assertion).
- **LOW — regression fixture race-count determinism (Codex).** A robustness nit on the test fixture, not a defect in the fix. The test still validates the invariant (date-set disjointness + assertion-never-raises) regardless of whether it would *also* catch a hypothetical race-count regression. Below HIGH.
- **LOW — race_id → single-date assumption not explicitly validated (Codex).** The mapping is built by `zip(groups, dates)` into a dict; if a `race_id` appeared under two dates, the dict would silently keep the last. In JRA data `race_id` is globally unique to one date (it encodes the date), so this is a data invariant rather than a plan defect. A defensive assert in the executor would be nice-to-have.

### Carry-over MEDIUMs from earlier cycles (unchanged, below HIGH)

- `--run-gated` flag not registered as a pytest option (only the `gated` marker + `RUN_GATED=1` env var exist) — test-runner friction, not a production halt.
- D-09 race-level Top-3 recall still listed in `07-06` `read_first` but not returned by `evaluate()`.
- Empty-dict sentinel branch ambiguity (`elif isinstance(expected_counts, dict)` should be `and expected_counts`).
- Early-stopping test (`best_iteration_ < n_estimators`) may be nondeterministic on tiny fixtures.

None of these are execution-halt or calibration-leakage. They are not counted.

---

## Consensus Summary

> Single reviewer (Codex) plus orchestrator cross-check. The single Cycle-3 HIGH was independently validated by the orchestrator against the `07-03` plan text and the real feature parquet (1,236 unique dates, mean 30.75 races/date, zero single-race dates). The Cycle 4 targeted edit fully closes it.

### Agreed Strengths

- The date-block-aware chunking is genuinely present and correct in the plan text: boundaries index an ordered unique-date array, each date block is atomic, and `max(train_dates) < min(val_dates)` is a genuine invariant.
- Boundary indexing (`val_start=date_boundaries[i]`, `val_end=date_boundaries[i+1]`) has no off-by-one; cumulative/expanding-window train including warm-up chunk 0 is preserved.
- The regression test fixture (all-multi-race dates) directly exercises the universal JRA case and asserts both the invariant and assertion-non-raising.
- The Cycle 4 edit was correctly scoped — only `07-03-PLAN.md` changed; the other 7 plans' prior resolutions are untouched.

### Agreed Concerns (all below HIGH)

1. **[MEDIUM|new] Legacy `dates=None` path is underspecified** — line 100-101 inconsistency; production path unaffected.
2. **[LOW|new] Regression fixture race counts could accidentally align** — test-robustness nit.
3. **[LOW|new] `race_id`→single-date assumption not explicitly validated** — data invariant, not a plan defect.
4. **[MEDIUM|carry-over] `--run-gated` not a registered pytest option.**
5. **[MEDIUM|carry-over] D-09 race-level Top-3 recall not returned by `evaluate()`.**
6. **[MEDIUM|carry-over] Empty-dict sentinel branch ambiguity.**
7. **[MEDIUM|carry-over] Early-stopping test nondeterminism.**
8. **[LOW|carry-over] Artifact count "6" vs 7 files verified.**

### Divergent Views

- None. The orchestrator's independent verification reinforces rather than contradicts Codex's FULLY-RESOLVED verdict and GO recommendation.

### Convergence Status

- **Cycle-3 HIGH:** 1 FULLY RESOLVED (date-block-aware chunking).
- **Cycle-4 NEW HIGHs:** 0.
- **Remaining unresolved HIGH count: 0.**
- **Recommendation:** Phase 7 is **GO** for implementation. All 11 HIGHs raised across Cycles 1-3 are now FULLY RESOLVED in the plan text. The remaining items are MEDIUM/LOW and are the executor's responsibility to tighten during implementation.
