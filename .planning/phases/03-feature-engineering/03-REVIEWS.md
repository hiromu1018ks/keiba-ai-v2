---
phase: 3
reviewers: [codex]
reviewed_at: "2026-06-12T13:45:00+09:00"
plans_reviewed:
  - 03-01-PLAN.md
  - 03-02-PLAN.md
  - 03-03-PLAN.md
  - 03-04-PLAN.md
  - 03-05-PLAN.md
---

# Cross-AI Plan Review — Phase 3

## Codex Review

### Overall Summary

The plans cover the required feature categories and include substantial testing, but several temporal leakage and data identity issues could invalidate backtest results. The most serious risks are globally fitted finish-time normalization, same-race leakage in jockey/trainer statistics, ambiguous implementation of the 100-rides/one-year window, and grouping horses by name rather than a stable identifier. These should be resolved before implementation proceeds.

---

### PLAN 03-01 Review

#### Summary

The module decomposition is reasonable and establishes a testable foundation. However, merge cardinality, missing-result handling, entity identity, and deterministic chronological ordering need stronger definitions because every downstream lag and target feature depends on them.

#### Strengths

- Clear separation between loading, race context, and horse-level features.
- Explicit exclusion of popularity and win odds.
- `field_size` is derived rather than trusted from potentially inconsistent source data.
- Sorting before lag generation is recognized as necessary.
- Test fixtures are introduced early.

#### Concerns

- **HIGH:** `horse_name` is not a reliable entity key. Different horses can share names, and formatting changes can split one horse into multiple histories.
- **HIGH:** Sorting only by `[horse_name, race_date]` is ambiguous when a horse has multiple records on one date or dates are missing. Stable race ordering is required.
- **HIGH:** An inner merge with results may remove scratched/removed entries before Plan 03-04 can classify them.
- **HIGH:** Merge cardinality is unspecified. Duplicate keys could silently multiply rows and corrupt all features.
- **MEDIUM:** `field_size` needs a defined policy for scratched and removed horses: declared runners versus actual starters.
- **MEDIUM:** Required-column validation and dtype/date parsing behavior are not specified.
- **MEDIUM:** Direct column selection may unintentionally retain duplicate columns or inconsistent suffixes after merging.
- **LOW:** Defining an empty `MARGIN_MAP` in this plan creates cross-plan ownership ambiguity.

#### Suggestions

- Use `horse_id` as the grouping key. If unavailable, define and validate a documented surrogate key.
- Sort by a deterministic key such as `race_datetime`, `race_id`, and `horse_number`.
- Use explicit merge validation, such as `validate="many_to_one"` and `validate="one_to_one"`.
- Assert row counts and uniqueness after each merge.
- Preserve entries without results using a left join.
- Define both `declared_field_size` and `starter_count` if both concepts are needed.
- Add tests for duplicate keys, missing result rows, same-day races, and malformed dates.

#### Risk Assessment

**HIGH.** Identity or merge errors here silently contaminate every downstream feature and are difficult to detect after feature generation.

---

### PLAN 03-02 Review

#### Summary

Margin parsing is appropriately isolated and well tested, but the proposed global z-score computation introduces temporal leakage. Parsing and normalization also require stronger handling for malformed values and low-variance groups.

#### Strengths

- Compound margin forms are explicitly considered.
- Finish-time parsing is separated from normalization.
- Sparse course-distance combinations receive special handling.
- The planned test count is appropriate for parsing-heavy logic.

#### Concerns

- **HIGH:** Computing mean and standard deviation from the full dataset leaks future race results into historical rows.
- **HIGH:** The current row contributes to its own normalization. Shifting the normalized value later does not remove future-distribution leakage.
- **MEDIUM:** Grouping only by course and distance may mix turf/dirt, course layouts, or materially different conditions.
- **MEDIUM:** `<30` samples does not handle `std == 0`, invalid times, or groups containing many missing values.
- **MEDIUM:** A fixed mapping of all observed margin strings may fail on whitespace, full-width characters, alternate separators, or unseen values.
- **LOW:** The exact physical interpretation of textual margins is heuristic and should be documented.

#### Suggestions

- Compute normalization statistics using prior races only, with an expanding calculation followed by `shift(1)`.
- Alternatively, fit normalization parameters on each training fold and apply them to validation/test data.
- Include surface and other justified course configuration fields in the grouping key.
- Normalize Unicode and whitespace before parsing.
- Return `NaN` plus a parse-status indicator for unknown values rather than raising or silently coercing.
- Add tests proving that adding future rows does not change earlier z-scores.

#### Risk Assessment

**HIGH.** The proposed global normalization violates the phase's temporal leakage requirement and can inflate backtest performance.

---

### PLAN 03-03 Review

#### Summary

The intended lag coverage matches the decisions, but this is the highest-risk plan. Temporal ordering, group isolation, same-race outcomes, and the one-year/100-rides window must be specified more precisely.

#### Strengths

- Produces the required 25 raw lag and 20 aggregate columns.
- Uses lagged values as the source for horse-history aggregates.
- Supports partial history through `min_periods=1`.
- Includes explicit testing for repeated horses and participants.
- Recognizes that jockey/trainer statistics must exclude the current observation.

#### Concerns

- **HIGH:** Grouping by `horse_name` can combine unrelated horses.
- **HIGH:** Row-level `shift(1)` can leak outcomes from an earlier row in the same race or date into another runner's jockey/trainer statistics, especially for trainers with multiple runners.
- **HIGH:** "Compute both and select smaller" does not clearly implement the intersection of "last 100 rides" and "last one year."
- **HIGH:** Rolling operations on `prev_1_*` must be grouped by horse again; otherwise histories can cross group boundaries.
- **HIGH:** Date-only ordering is insufficient for multiple races on one day.
- **MEDIUM:** `rides` should represent prior valid starts, not all rows, and needs rules for scratches, removals, and missing results.
- **MEDIUM:** Jockey/trainer names may change formatting or collide; stable IDs are preferable.
- **MEDIUM:** Python-level rolling implementations could be expensive over 311K rows.
- **MEDIUM:** Whether DNF/disqualified results count in denominators is unspecified.
- **LOW:** Column naming and output ordering should be deterministic.

#### Suggestions

- Group histories using stable horse, jockey, and trainer IDs.
- Establish a total ordering using race datetime or date plus race sequence.
- Compute jockey/trainer outcomes at race boundaries so no participant can see any result from the same race.
- Define D-08 as records satisfying both `date > current_date - 1 year` and membership among the most recent 100 prior valid starts.
- Add invariance tests: changing current or future outcomes must not alter the row's features.
- Add tests for trainers with multiple runners in one race and multiple races on one day.
- Benchmark the implementation on full data and avoid per-row Python callbacks.

#### Risk Assessment

**HIGH.** Incorrect implementation would create direct target leakage while still appearing to use `shift(1)` correctly.

---

### PLAN 03-04 Review

#### Summary

The target and auxiliary-column plan covers important result-status cases, but target semantics and debut logic require tighter definitions. It also depends on Plan 03-01 preserving entries without result rows.

#### Strengths

- Uses nullable integer type for the target.
- Separates result status, DNF state, and training exclusion.
- Explicitly addresses scratched, removed, disqualified, and demoted records.
- Includes edge-case fixtures.
- Keeps debut state separate from missing lag values.

#### Concerns

- **HIGH:** Scratched/removed rows cannot be classified if the earlier merge dropped resultless entries.
- **HIGH:** `is_debut = cumcount() == 0` means "first row in this dataset," not necessarily career debut.
- **HIGH:** Scratched entries may incorrectly consume the first-history position and make the next actual start non-debut.
- **MEDIUM:** Future prediction rows and missing official results need `target_top3 = NA`, not `0`.
- **MEDIUM:** Demotion handling is underspecified. "Keep finish position" must identify whether that is the official revised position.
- **MEDIUM:** Dead heats and non-numeric position values need explicit parsing rules.
- **MEDIUM:** `is_dnf` including disqualified runners may conflate "did not finish" with "finished but disqualified."
- **LOW:** `exclude_from_training` overlaps with status and could become inconsistent unless derived centrally.

#### Suggestions

- Derive all target fields from one normalized result-status function.
- Define target eligibility before assigning `0` or `1`.
- Use official finalized placing for demotions and dead heats.
- Distinguish `is_first_observed_start` from a verified `is_debut`.
- Exclude cancelled entries from history counts.
- Add tests for missing results, prediction rows, first observed records, and revised official placings.

#### Risk Assessment

**MEDIUM-HIGH.** The logic is manageable, but incorrect eligibility or debut handling will introduce label noise and misleading missing-history signals.

---

### PLAN 03-05 Review

#### Summary

The final integration plan addresses categoricals, auditing, persistence, and real-data validation. Its main weakness is reliance on a column-name leakage audit, which cannot detect temporal leakage or unsafe derived columns.

#### Strengths

- Includes end-to-end generation and real-data validation.
- Uses native pandas categoricals for LightGBM.
- Explicitly defines excluded result columns.
- Provides separate training and prediction artifacts.
- Includes a direct previous-race spot check.
- Validates against the Phase 1 audit function.

#### Concerns

- **HIGH:** A schema or column-name audit cannot detect global z-score leakage or same-race rolling-stat leakage.
- **HIGH:** `margin_numeric` and current-row `finish_time_zscore` are not listed in `EXCLUDE_FROM_FEATURES`; both are post-race values unless retained solely as internal lag sources.
- **HIGH:** Auxiliary post-race columns must not enter `features_pred.parquet`.
- **MEDIUM:** Sampling 100 horses may miss systematic ordering and identity defects.
- **MEDIUM:** Writing all historical rows as `features_pred.parquet` is semantically unclear; prediction data normally has no results or targets.
- **MEDIUM:** Category domains may differ between training and inference unless category vocabularies are persisted or aligned.
- **MEDIUM:** Full-data integration tests may be too slow for the default unit-test suite.
- **MEDIUM:** Output schema, uniqueness constraints, atomic writes, and overwrite behavior are unspecified.
- **LOW:** Expected row and column counts should tolerate legitimate exclusions rather than rely only on approximate values.

#### Suggestions

- Separate internal calculation columns, model features, targets, and metadata through explicit allowlists.
- Ensure current `margin_numeric` and `finish_time_zscore` are never model inputs.
- Add temporal invariance tests that recompute a historical prefix with and without future data and compare outputs.
- Validate uniqueness of `horse_race_id`, row counts, dtypes, and categorical columns before writing.
- Persist categorical vocabularies or define inference-time unknown-category behavior.
- Put the 311K-row validation in a separate integration-test marker.
- Write outputs atomically and include generation metadata or schema version.

#### Risk Assessment

**HIGH.** This plan can pass the stated audit while retaining serious temporal leakage, so the verification strategy is not sufficient yet.

---

### Final Assessment

**Overall risk: HIGH.**

The plans broadly satisfy DATA-03 at the feature-list level, but they do not yet guarantee leakage-safe ML inputs. Before implementation, the plan set should explicitly resolve:

1. Stable entity identifiers and deterministic race ordering.
2. Prefix-only or fold-fitted finish-time normalization.
3. Race-boundary-safe jockey/trainer calculations.
4. Exact intersection semantics for the 100-rides/one-year window.
5. Preservation and classification of entries without results.
6. Explicit model-feature allowlists excluding all current-race result derivatives.
7. Automated temporal invariance tests rather than sampled value checks alone.

---

## Consensus Summary

Review conducted by 1 AI system (Codex). Claude was skipped (same runtime).

### Agreed Strengths

- Comprehensive test coverage planned across all 5 plans (~57 tests total)
- Clear separation of concerns: each plan handles a distinct feature group
- Explicit exclusion of popularity/win_odds per D-15
- Phase 1 audit_leakage() integration planned as final gate
- Well-structured wave-based execution with proper dependencies

### Agreed Concerns (from Codex review)

**HIGH severity (7 unresolved):**

1. **horse_name entity key instability** — Different horses can share names; formatting changes can split one horse into multiple histories. Lag features may reference wrong past races. (Plan 03-01, 03-03)
2. **Non-deterministic race ordering** — Sorting by [horse_name, race_date] is ambiguous for same-day races or missing dates. (Plan 03-01, 03-03)
3. **Global z-score temporal leakage** — Using all-data mean/std for finish_time normalization leaks future distribution into historical rows. (Plan 03-02, 03-05)
4. **Jockey/trainer same-race leakage risk** — Row-level shift(1) within groupby can leak outcomes from an earlier row in the same race (trainers with multiple runners). (Plan 03-03)
5. **D-08 "100 rides or 1 year" ambiguity** — "Compute both and select smaller" does not clearly implement the intersection constraint. (Plan 03-03)
6. **Merge drops resultless entries** — Inner merge with results may remove scratched/removed entries before Plan 03-04 can classify them. (Plan 03-01, 03-04)
7. **Column-name audit insufficient** — audit_leakage() only checks column names, not temporal leakage from global z-score or same-race rolling stats. Current-row margin_numeric and finish_time_zscore not in EXCLUDE_FROM_FEATURES. (Plan 03-05)

**MEDIUM severity (10 raised):**

- field_size policy for scratched/removed horses undefined
- Z-score grouping only by course+distance may mix surface types
- std==0 edge case for sparse course-distance groups
- Whether DNF/disqualified count in rolling stat denominators unspecified
- is_debut means "first observed row" not career debut
- features_pred.parquet semantics unclear (historical rows with no results)
- Category vocabulary alignment between train/inference unspecified
- Performance concern with per-row Python operations on 311K rows
- Output schema uniqueness constraints and atomic writes unspecified
- Demotion dead-heat official position handling underspecified

### Divergent Views

Single reviewer -- no divergent views to report.

### Planner Action Items

1. **Resolve horse_name entity key**: Evaluate whether the standard data contains a horse_id field. If not, document the collision risk and consider a composite key (horse_name + first_race_date). Update Plan 03-01.
2. **Fix merge strategy**: Change result merge to left join. Preserve scratched/removed rows for Plan 03-04 classification. Update Plan 03-01.
3. **Address z-score leakage**: Either (a) use expanding-window mean/std per course-distance with shift(1), or (b) accept global stats as a documented known assumption (per RESEARCH.md A2) and add a temporal invariance test. Update Plan 03-02.
4. **Fix jockey/trainer race-boundary safety**: Compute stats at race level, not row level. A trainer/jockey should see all results from completed prior races, not from an earlier row in the same race. Update Plan 03-03.
5. **Clarify D-08 constraint**: Define exact semantics: filter prior records to those within 365 days AND among the most recent 100 valid starts. Update Plan 03-03.
6. **Expand EXCLUDE_FROM_FEATURES**: Add current-row margin_numeric, finish_time_zscore, and finish_time_seconds to the exclusion list. Ensure only lag-derived versions (prev_*_finish_time_zscore, prev_*_margin_numeric) appear in features. Update Plan 03-05.
7. **Add temporal invariance tests**: Add tests verifying that adding future data does not change historical feature values. Update Plan 03-05.
