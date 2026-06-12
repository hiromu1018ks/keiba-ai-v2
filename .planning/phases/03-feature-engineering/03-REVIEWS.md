---
phase: 3
reviewers: [codex]
reviewed_at: "2026-06-12T15:30:00+09:00"
cycle: 2
previous_cycle_highs: 7
plans_reviewed:
  - 03-01-PLAN.md
  - 03-02-PLAN.md
  - 03-03-PLAN.md
  - 03-04-PLAN.md
  - 03-05-PLAN.md
---

# Cross-AI Plan Review — Phase 3 (Cycle 2)

## Codex Review (Cycle 2 — Re-review of Revised Plans)

### Summary

The revisions improve merge preservation, current-row feature exclusion, and test intent, but they do not fully resolve the identity and temporal-leakage risks. The proposed `horse_key` cannot distinguish same-name horses, finish-time normalization leaks same-race results, and jockey/trainer rolling statistics are neither an exact nor scalable implementation of D-08. The Plan 05 "allowlist" is still dynamically derived by exclusion. Overall, substantial correction is required before implementation.

---

### HIGH Resolution Status

| # | Original Concern | Status | Assessment |
|---|------------------|--------|------------|
| 1 | horse_name entity key instability | **UNRESOLVED** | `groupby("horse_name").transform("min")` assigns the same first date to every row sharing that name. Two different same-name horses therefore receive the same key. The claimed different-first-date test cannot pass against this implementation. |
| 2 | Non-deterministic race ordering | **PARTIALLY RESOLVED** | race_number improves same-day ordering, but is not globally unique across courses/meetings. Use race_date, start_time, and race_id as deterministic tie-breakers. More importantly, feature calculations must honor race boundaries, not merely row order. |
| 3 | Global z-score temporal leakage | **PARTIALLY RESOLVED** | Global future leakage is removed, but row-level expanding statistics leak results from earlier rows in the same race into later runners. Sorting only by race_date also leaves same-date ordering ambiguous. |
| 4 | Jockey/trainer same-race leakage | **PARTIALLY RESOLVED** | Race-level computation prevents runners in the current race influencing each other. However, reducing trainer outcomes to `any(top3)`/`any(win)` and counting one record per race changes the requested runner/start-level rates and ride counts. |
| 5 | D-08 "100 rides or 1 year" ambiguity | **UNRESOLVED** | Choosing whichever precomputed statistic has fewer observations is not equivalent to calculating statistics over the exact intersection. The last-100 constraint concerns valid starts, while the proposed structure is one row per person-race. |
| 6 | Merge drops resultless entries | **RESOLVED** | A validated left join preserves entry rows and prevents result absence from reducing row count. |
| 7 | Column-name audit insufficient | **PARTIALLY RESOLVED** | Current-row derivatives are explicitly excluded and temporal tests are added. However, `FEATURE_COLUMNS = all columns minus EXCLUDE_FROM_FEATURES` is a denylist, not an explicit allowlist, so newly introduced columns can still leak automatically. |

---

### New Concerns

#### HIGH Severity

1. **Same-race leakage in finish_time_zscore** — Each horse is a separate row. A shifted expanding calculation lets earlier runners from the current race influence later runners. Normalization parameters must be frozen at the race boundary and calculated only from earlier races. (Plan 03-02)

2. **Resultless rows cannot be classified as scratched versus removed** — After the left join, both finish_position and finish_note are null. Plan 04 maps these rows to `no_result`, not `scratched` or `removed`. The pipeline needs an entry-side status field or another authoritative source for distinguishing these. (Plan 03-04)

3. **Scratched entries corrupt horse lag positions** — `groupby(...).shift(n)` runs over all entry rows. A scratched entry therefore consumes a lag position and can replace the most recent valid result with NaN. Lags must be based on prior valid starts and then joined back to all current entries. (Plan 03-03)

4. **Trainer statistics have incorrect semantics** — For three trainer runners in one race, `any(top3)` produces one binary race outcome and `race_n_runners` is not incorporated into the proposed rates. Correct statistics require sums of wins/top-three finishes and counts of valid starts. (Plan 03-03)

#### MEDIUM Severity

5. **D-08 performance assumptions are weak** — Person-race data is not necessarily "much fewer" than 311K rows, especially for jockeys. Per-row 365-day filtering can become quadratic for high-volume people. Benchmarking and an indexed sliding-window algorithm are needed.

6. **FEATURE_COLUMNS is internally inconsistent** — The plan describes it as a constant, but also computes it dynamically inside generate(). A real allowlist should be statically constructed from named feature groups and validated for missing/unexpected columns.

7. **Debut specification contradicts itself** — Plan 04 behavior says an all-scratched horse has is_debut=True for all entries. The implementation and acceptance criteria say scratched rows have is_debut=False. One definition must be selected; the implementation's behavior is more coherent.

8. **field_size includes scratched/removed entries** — That may mean declared field size rather than actual starters. The intended model meaning should be explicit; potentially expose both declared_field_size and starter_count.

9. **Race-level ordering needs stronger keys** — Use parsed timestamps and race_id as the final tie-breaker. Relying on input stability or race_number alone is insufficient for reproducibility.

10. **Training output retains excluded rows** — features_train.parquet contains exclude_from_training, but the plan does not actually filter those rows. This is acceptable only if every downstream trainer is contractually required to filter them and tests enforce that contract.

---

### Suggestions

1. Use a source-provided horse ID. If unavailable, create a persisted entity-resolution table with a generated ID and collision handling. Do not claim `name + grouped minimum date` distinguishes collisions.

2. Define canonical race order as: `race_date, start_time, race_id`. Use race-level computations so all runners in one race receive statistics based on the identical prior-race snapshot.

3. For finish-time normalization, aggregate historical observations by race or batch by race: compute prior-group moments -> assign to every runner in current race -> update moments.

4. For person statistics, retain per-race aggregates as: valid_start_count, top3_count, win_count. Window sums of these quantities produce correct runner-level rates.

5. Implement D-08 with a per-person deque/two-pointer window that removes starts older than 365 days, retains at most the latest 100 valid starts, and maintains running sums and counts.

6. Build FEATURE_COLUMNS explicitly from named lists such as race, horse, lag, and person features. Assert every allowed column exists, no unexpected column is selected, and no allowlisted column overlaps the exclusion set.

7. Add tests for: two same-name horses with overlapping observation periods; multiple runners in one race receiving identical z-score parameters; scratches not consuming horse lag positions; trainer rate denominators with multiple same-race runners; exact D-08 expected values, not just expected counts; runtime/memory on the full 311K-row dataset.

---

### Risk Assessment

**HIGH.** Three core correctness problems remain: horse identity collisions, same-race finish-time leakage, and incorrect/non-exact person rolling windows. These can materially contaminate validation results or produce features with different semantics from the documented decisions. The plans should be revised again before execution.

---

## Consensus Summary

Review conducted by 1 AI system (Codex). Claude was skipped (same runtime).

### Cycle Comparison

| Metric | Cycle 1 | Cycle 2 |
|--------|---------|---------|
| Total HIGHs | 7 | 8 (1 resolved + 4 new) |
| Resolved | 0 | 1 (#6 merge strategy) |
| Partially Resolved | 0 | 4 (#2, #3, #4, #7) |
| Unresolved | 7 | 2 (#1, #5) |
| New HIGHs raised | N/A | 4 |

### Agreed Strengths (Carried Forward + New)

- Comprehensive test coverage planned across all 5 plans (~57 tests total)
- Clear separation of concerns: each plan handles a distinct feature group
- Explicit exclusion of popularity/win_odds per D-15
- Phase 1 audit_leakage() integration planned as final gate
- Well-structured wave-based execution with proper dependencies
- LEFT join merge strategy now correctly preserves scratched/removed entries (resolved #6)

### Agreed Concerns (Cycle 2 — Codex)

**HIGH severity (8 concerns: 2 unresolved + 2 partially resolved from cycle 1 + 4 new):**

1. **horse_name entity key still insufficient** — The horse_key = horse_name + first_race_date surrogate uses groupby("horse_name").transform("min"), which assigns the same first date to ALL rows sharing that name. Two same-name horses would get the same key. The data shows zero collisions in 2015-2021, but the defense-in-depth implementation is logically flawed. (UNRESOLVED from cycle 1 #1)

2. **D-08 exact intersection not implemented** — "Choose whichever precomputed stat has fewer observations" is not the same as computing stats over the exact intersection of (within 365 days AND among last 100 valid starts). Need a proper sliding-window or deque implementation. (UNRESOLVED from cycle 1 #5)

3. **Same-race leakage in finish_time_zscore** — Expanding-window with shift(1) operates row-by-row. Earlier runners in the same race contribute to normalization stats seen by later runners. Must compute at race boundary level: all runners in race N see stats from races 1..N-1 only. (NEW)

4. **Scratched entries consume lag positions** — groupby("horse_key").shift(n) operates on all rows including scratched entries. A scratched horse's row gets a lag position filled with NaN, pushing valid past results to later positions. Lags must filter to valid starts only before shift. (NEW)

5. **Trainer statistics have incorrect rate semantics** — Using `any(top3)`/`any(win)` at race level produces binary outcomes, not proper rate denominators. For 3 runners: 2 top-3 finishes should count as 2/3 rate, not 1/1. Need sum-based aggregation: sum(top3_count)/sum(valid_starts). (NEW)

6. **Resultless rows cannot distinguish scratched from removed** — Left-join preserved entries with no result row get result_status="no_result" in Plan 04, losing the scratched/removed distinction that exists in entry data. Need entry-side status field. (NEW)

7. **Race ordering not globally unique** — (horse_key, race_date, race_number) is not globally unique across courses. Need start_time and race_id as additional tie-breakers. (PARTIALLY RESOLVED from cycle 1 #2)

8. **FEATURE_COLUMNS is a denylist, not an allowlist** — `all columns minus EXCLUDE_FROM_FEATURES` means new columns auto-include. Need a static, explicitly enumerated allowlist. (PARTIALLY RESOLVED from cycle 1 #7)

### Divergent Views

Single reviewer -- no divergent views to report.

### Planner Action Items (Priority Order)

1. **Fix horse entity key**: Either (a) verify that the standard data contains a horse_id field and use it, or (b) accept the current horse_key with a documented caveat that 2015-2021 data has zero name collisions (verified by data analysis) and add a runtime assertion checking for key collisions. If collisions exist, the system must fail loudly rather than silently.

2. **Fix finish_time_zscore same-race leakage**: Change the grouping to operate at race level -- compute expanding-window stats per (course_name, distance, surface) using one representative observation per race (e.g., mean finish_time), then assign the same normalization parameters to all runners in that race. This ensures no same-race runner influences another.

3. **Fix lag position corruption by scratched entries**: Before computing shift(n), filter the DataFrame to only valid-start rows (where result_status is not scratched/removed/no_result). Compute lags on this filtered set, then merge back to the full entry DataFrame. Scratched entries get all-NaN lags, which is correct.

4. **Fix trainer stat semantics**: Replace `any(top3)`/`any(win)` with sum-based aggregation: for each person-race, compute sum of top3 finishes and count of valid starts. Rolling rates = rolling_sum(top3_count) / rolling_sum(valid_starts). This produces correct runner-level rates.

5. **Implement D-08 as exact intersection**: Use a two-pointer or deque approach per person: maintain a sorted list of prior valid starts, filter to last 365 days, take the most recent 100, compute stats over exactly those records. This is O(n) per person with sorted data.

6. **Make FEATURE_COLUMNS a true allowlist**: Define it as a static list constructed from named feature groups (RACE_FEATURES, HORSE_FEATURES, LAG_FEATURES, PERSON_FEATURES). Assert at generation time that all expected columns exist and no unexpected columns are present.

7. **Strengthen race ordering key**: Add start_time and race_id as additional sort components for full global uniqueness across courses and meetings.

8. **Resolve result_status for resultless rows**: Check if entry-side data distinguishes scratched from removed. If so, use that field. If not, document "no_result" as a catch-all and note the downstream impact.
