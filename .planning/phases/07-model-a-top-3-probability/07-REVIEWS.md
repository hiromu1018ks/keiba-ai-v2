---
phase: 07
reviewers: [codex]
reviewed_at: 2026-06-15T00:00:00
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

# Cross-AI Plan Review — Phase 07 (Model A: Top-3 Probability)

> **Reviewers invoked:** Codex (Claude skipped — this review was orchestrated from inside the Claude Code runtime, so an independent Claude session would not be truly independent).
>
> **Scope:** All 8 plans for Phase 7 (Wave 0 env/test scaffolding → Wave 1 parallel ML modules → Wave 2 run_train orchestrator → Wave 3 real-data phase gate). Review focus: temporal/data leakage, LightGBM 4.x API correctness, calibration correctness, statistical validity, dependency ordering, and whether the plans achieve MODA-01..04 + the 4 ROADMAP success criteria.

---

## Codex Review

### Summary

The plan set has clear separation of concerns, correct LightGBM 4.x callback handling, leak-free OOF calibration design, and a well-specified artifact contract (D-15). It covers the Phase 7 implementation scope comprehensively. **However, the temporal CV design contains a fatal contradiction.** The current `GroupTimeSeriesSplit` produces an empty training set for fold 0, and an expanding-window CV by definition cannot emit an OOF prediction for *every* training row — which makes the row-count contracts in 07-04, 07-07, and 07-08 simultaneously impossible. Plan 07-04 also has a hard runtime dependency on 07-03's `split_train_validation`, so the "Wave 1 is fully parallel" claim does not hold. Without fixing these, the phase may be unable to reach real-data training.

### Strengths

- 07-02 explicitly handles `exclude_from_training`, categorical dtype conversion, `grade` NaN, and `horse_race_id` derivation.
- 07-04 correctly specifies the LightGBM 4.x callback API (`callbacks=[lgb.early_stopping(...)]`) and avoids the removed `early_stopping_rounds` fit kwarg (Pitfall #1).
- 07-05 "fit Isotonic on OOF only, predict-only on holdout" satisfies D-10 / MODA-04.
- 07-06 reports raw-vs-calibrated AUC/Brier/logloss/ECE separately.
- Popularity baseline is kept out of the feature set and isolated for evaluation only (D-08).
- Reproducibility and artifact contract (seed, YAML, model, calibrator, prediction parquets, report) are explicit.
- Hermetic tests are separated from the real-data phase gate.
- D-07's decision to NOT make "beat popularity baseline" a hard requirement is statistically sound.

### Concerns

- **HIGH — 07-03 Task 1 splitter yields an empty `train_groups` for fold 0.** The first model cannot train, so 07-04 OOF generation fails.
  *Minimal fix:* split races into `n_splits + 1` chunks; chunk 0 = initial train, chunks 1..5 = validation for folds 0..4.

- **HIGH — Expanding-window CV cannot produce OOF predictions for the initial train-only chunk.** Therefore 07-04's "OOF rows == input rows" and 07-08's "OOF == 322,510 rows" are impossible. Forcing predictions there injects in-sample predictions and leaks Isotonic calibration.
  *Minimal fix:* define OOF row count as the sum of validation-chunk rows; warm-up rows are excluded from OOF/calibration.

- **HIGH — 07-04 has a hard runtime dependency on 07-03's `split_train_validation`.** Lazy import avoids file-write conflicts but does not resolve the dependency. If 07-04 completes/tests first, import error or hollowed-out test conditions result.
  *Minimal fix:* add `"07-03"` to 07-04's `depends_on`, or move the shared split helper to Wave 0.

- **HIGH — 07-02 `load_features()` unconditionally asserts the production fixed row counts**, so 07-07's small-scale hermetic E2E will fail.
  *Minimal fix:* make `expected_counts` optional, or only verify fixed counts under the production config.

- **HIGH — 07-04 references `config["data"]["feature_columns"]` but 07-07's YAML has no such key.**
  *Failure mode:* `collect_oof_predictions()` raises `KeyError: feature_columns`.
  *Minimal fix:* make feature columns an explicit function argument, or persist a confirmed list in the config.

- **HIGH — `train_final_model()` carves off the trailing 20% as early-stopping validation and returns the model trained on the remainder — this is NOT "train on all 2018-2024 data".** The saved single model is trained on ~80% of the window.
  *Minimal fix:* two-stage final training — determine `best_iteration` on the validation split, then refit on ALL 2018-2024 rows using that iteration count.

- **HIGH — 07-08 leaves room to retune hyperparameters after inspecting holdout results.** Repeating this turns the D-02 "envelope" into model-selection data.
  *Minimal fix:* on holdout failure, record results as fixed-failure and adjust only within CV; any re-evaluation requires a fresh unused period.

- **MEDIUM — splitter assumes caller pre-sorts by `race_date`, but 07-02/07-07 have no explicit stable sort + verification.**
- **MEDIUM — `audit_leakage()` is warning-only (D-12); in an ML phase this is a weak safety boundary — a detected post-race column still proceeds to produce a contaminated model.**
- **MEDIUM — OOF enters a single Isotonic with non-uniform prediction distributions across folds (different training horizons).** Standard practice, but fold-wise and period-wise ECE should also be reported.
- **MEDIUM — ECE `<0.02` is sensitive to the 10-bin equal-width definition;** low-probability bins can be sparsely populated and look deceptively good.
- **MEDIUM — 07-05's "holdout ECE should not be better than OOF" is not a sufficient leak detector;** a legitimate well-calibrated model can also improve.
- **MEDIUM — Gating primarily on `auc_calibrated` can be lower than `auc_raw` due to Isotonic ties;** discrimination should be judged on `auc_raw`.
- **MEDIUM — D-09 race-level Top-3 recall is not implemented in 07-06/07-07.**
- **MEDIUM — ROADMAP success criterion #2 explicitly says "TimeSeriesSplit";** the divergence with the custom `GroupTimeSeriesSplit` should be recorded in formal traceability.
- **LOW — Skipping all Wave 0 tests early makes test-spec errors hard to detect early.**
- **LOW — Fixed real-data row-count asserts are fragile against legitimate data regeneration / future corpus updates.**
- **LOW — 8 plans is slightly granular, but the env/CV/train/calibrate/evaluate/integrate/real-data-gate split is not excessive.**

### Suggestions

- Lock the CV contract: 6 chunks; chunk 0 = warm-up train; folds 0..4 validate on chunks 1..5; OOF target = chunks 1..5 only; OOF row count computed at runtime and stored in metadata.
- Add `race_date` to the OOF parquet to ease temporal audit and Phase 9 reuse.
- Assert `max(train_date) < min(validation_date)` at runtime for each fold.
- Optionally block same-`race_date` into the same time block to remove date-boundary ambiguity.
- Keep `audit_leakage()` warning-only, but have `run_train` abort if any leakage column is detected.
- Split final training into "decide best_iteration" and "refit on all rows".
- Resolve `feature_columns` in one place; use identical column order across config/trainer/holdout inference.
- Alongside ECE, report bin counts, max bin error, equal-frequency ECE, and period-wise ECE.
- Phase gate should judge `auc_raw`, `ece_calibrated`, and Brier improvement separately.
- Treat AUC ~0.75 as an expectation, not a hard pass/fail; MODA requirements can be met if leak-free + artifacts generated + calibration evaluated, even if AUC falls short.
- Add D-09 race-level Top-3 recall to 07-06.
- Add a formal `ruff check . && mypy src && pytest` gate before 07-08.

### Risk Assessment

**HIGH.** The CV design yields an untrainable fold 0, the all-rows OOF contract is incompatible with temporal CV, the Wave dependency graph is incorrect, the hermetic E2E collides with the fixed-count assert, and the `feature_columns` config key is missing. These are not precision concerns — they are structural problems that lead to execution halt or calibration leakage.

### Per-Plan Notes

- **07-01:** Rather than mass-producing skip skeletons first, lock the CV contract and the fixture's period structure first. The current fixture may not represent the expanding-CV warm-up problem.
- **07-02:** Fixed-count assert and hermetic fixture are mutually incompatible. Leakage detection that only warns is too weak a safety boundary for an ML phase.
- **07-03:** Highest-priority fix target. The current algorithm gives fold 0 an empty train. Move to an `n_splits + 1` chunk scheme and validate temporal order inside the class.
- **07-04:** Has a real dependency on 07-03, so it is not Wave-1-parallel. It also advertises "full retrain" while saving a model trained with the trailing 20% withheld.
- **07-05:** OOF-only fit is correct. But drop the false premise that OOF = all rows, and exclude warm-up from calibration.
- **07-06:** D-09 race-level Top-3 recall is missing. Gating `<0.02` ECE on 10-bin alone is fragile.
- **07-07:** `feature_columns` config mismatch and likely hermetic-E2E failure from the production fixed-count assert. The "6 artifacts" vs 7 actual files should be reconciled in the contract.
- **07-08:** The "OOF == 322,510 rows" acceptance criterion is incompatible with temporal OOF. Re-tuning after inspecting holdout results must be forbidden to preserve D-02 envelope integrity.

---

## Consensus Summary

> Note: Only one independent reviewer (Codex) was invoked in this cycle (Claude skipped due to runtime-independence constraint). "Agreed" items below reflect Codex's findings cross-checked against the plan text and ROADMAP/CONTEXT contracts by the orchestrator.

### Agreed Strengths (plan text + reviewer)

- Clean module separation (data_loader / splitter / trainer / calibrator / evaluator / baseline / orchestrator) with explicit per-plan `exports` and artifact contracts.
- Correct LightGBM 4.x early-stopping callback API (Pitfall #1) — not the removed fit kwarg.
- Leak-free calibration pattern (fit on OOF, predict-only on holdout) at the API surface.
- Deliberate, statistically-grounded decision (D-07/D-08) not to require beating the popularity baseline with an odds-free "pure prediction" model.
- D-15 artifact contract (6 logical artifacts) and D-14 fixed-seed YAML config for reproducibility.

### Agreed Concerns (highest priority — all newly raised this cycle, none resolved)

1. **[HIGH] `GroupTimeSeriesSplit` fold 0 has an empty training set** — structural CV bug in 07-03. Must switch to `n_splits + 1` chunk scheme.
2. **[HIGH] All-rows OOF contract (322,510) incompatible with expanding-window temporal CV** — warm-up chunk gets no OOF; forcing it leaks Isotonic calibration. Affects 07-03/07-04/07-05/07-07/07-08.
3. **[HIGH] 07-04 runtime-depends on 07-03's `split_train_validation`** — lazy import does not make them parallel; Wave 1 graph is mislabeled.
4. **[HIGH] 07-02 production fixed-count assert breaks 07-07 hermetic E2E** — must be opt-in / config-gated.
5. **[HIGH] `config["data"]["feature_columns"]` referenced by 07-04 but absent from 07-07 YAML** — will raise `KeyError` at runtime.
6. **[HIGH] `train_final_model` saves a model trained on ~80% of the window, not "all 2018-2024 data"** — violates the D-15 / Open-Question-#3 single-full-retrain contract.
7. **[HIGH] 07-08 permits hyperparameter retuning after holdout inspection** — degrades the D-02 envelope to model-selection data.

### Divergent Views

- None — single reviewer. The MEDIUM/LOW items (ECE-bin sensitivity, `audit_leakage` warning-only behavior, D-09 recall omission, AUC-gate-on-raw-vs-calibrated, ROADMAP #2 "TimeSeriesSplit" naming divergence) are noted for planner consideration but are not blocking.
