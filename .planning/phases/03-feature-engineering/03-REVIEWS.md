---
phase: 3
reviewers: [codex]
reviewed_at: "2026-06-12T17:45:00+09:00"
cycle: 3
previous_cycle_highs: 8
plans_reviewed:
  - 03-01-PLAN.md
  - 03-02-PLAN.md
  - 03-03-PLAN.md
  - 03-04-PLAN.md
  - 05-05-PLAN.md
---

# Cross-AI Plan Review -- Phase 3 (Cycle 3)

## Codex Review (Cycle 3 -- Re-review of Root-Cause-Revised Plans)

### Summary

The Cycle 3 revisions make substantial progress on all eight Cycle 2 HIGH concerns. Four concerns are now fully resolved (scratch lag filtering, sum-based trainer rates, scratched/removed classification via finish_note, and race_id ordering). However, several concerns have implementation-level defects that prevent full resolution: the finish-time z-score grouped expanding shift crosses group boundaries (verified via pandas behavior test), the leakage audit will flag `race_id` and `horse_race_id` as leaked (verified via `get_post_race_columns()` on all schemas), and D-08's 100-start cap operates on race records not individual starts for multi-runner trainers. Additionally, 8 new HIGH concerns were raised including merge key suffix collision, contradictory min_periods=5 in z-score tests, and the semantic difference between race-level standard deviation and runner-level standard deviation.

### Cycle 2 HIGH Resolution Assessment

| # | Concern | Assessment | Justification |
|---|---------|------------|---------------|
| 1 | horse_name entity key insufficient | **RESOLVED** | `horse_name + birth_year_proxy` where `birth_year_proxy = race_year - age` correctly disambiguates all 14 name collisions in 2015-2021 data (36,816 entities vs 36,802 names). Stable within the 2015-2021 training window. Codex raised a concern about 2001 horse-age notation change affecting historical data -- valid for Phase 6 (1986-2014) but NOT relevant to Phase 3's 2015-2021 scope. Tests cover the collision case. |
| 2 | D-08 exact intersection | **PARTIALLY RESOLVED** | The intersection semantics (BOTH conditions simultaneously) are correctly described. However, the implementation aggregates to person-race rows and caps at 100 race records, not 100 individual valid starts. A trainer with 3 runners per race would have 300 starts in 100 race records. For jockeys (1 runner per race), this is equivalent and correct. For trainers, the constraint is weaker than intended. |
| 3 | Same-race finish-time leakage | **PARTIALLY RESOLVED** | Race-level aggregation architecture is correct. However, `grp["race_ft_mean"].expanding().mean().shift(1).values` applies shift(1) AFTER groupby expanding, which crosses group boundaries. Verified via pandas test: Group B's first row inherits Group A's last mean. The shift must be applied per-group using `.groupby().transform()` or explicit per-group computation. |
| 4 | Scratches consume lag positions | **RESOLVED** | Valid-start filtering before shift computation, then merge back with NaN lags for invalid entries, is the correct pattern. The planned valid-scratch-valid test explicitly verifies the behavior. |
| 5 | Trainer rate semantics | **RESOLVED** | Sum-based aggregation with `top3_count=sum(is_top3)`, `valid_start_count=count`, rolling rate = rolling_sum(top3_count)/rolling_sum(valid_start_count) produces correct runner-level rates (2/3, not 1/1). |
| 6 | Scratched versus removed classification | **RESOLVED** | The 1:1 entry-result relationship (311,806 rows each) is data-verified. `finish_note` column directly provides the distinction: `取`=scratched (520), `除`=removed (604), `中`=DNF (966), etc. Inner join is correct. No catch-all needed. |
| 7 | Non-unique race ordering | **RESOLVED** | `race_id` encodes YYYYPPCCDDRR and is globally unique. SORT_KEY = [horse_entity_key, race_date, race_id] provides deterministic total order. |
| 8 | Denylist instead of allowlist | **PARTIALLY RESOLVED** | FEATURE_COLUMNS is now a static concatenation of named feature groups, independent of df.columns. This prevents silent auto-inclusion. However, the plan warns about unexpected columns rather than raising an error, and metadata columns (race_id, race_date, horse_entity_key, horse_name) are mixed with model features. |

### New Concerns

#### HIGH Severity

1. **`load_and_merge()` creates suffixed `race_id` columns** -- Both entry and result DataFrames contain `race_id`. Merging on `horse_race_id` alone produces `race_id_x` and `race_id_y`, breaking downstream code that expects a single `race_id` column. The merge must either use `on=["horse_race_id", "race_id"]` or explicitly drop the duplicate before merging. (Plan 03-01)

2. **`audit_leakage()` will flag `race_id` and `horse_race_id` as leaked** -- Verified: `get_post_race_columns(ResultSchema)` returns `{'race_id', 'horse_race_id', ...}`. The feature output includes `race_id` in FEATURE_COLUMNS. When `audit_leakage([RaceSchema, EntrySchema, ResultSchema])` is called on the feature DataFrame, it will report `race_id` and `horse_race_id` as leaked columns. The audit semantics need adjustment: either exclude identifier columns from the audit check, or pass only RaceSchema + EntrySchema (where `race_id` is pre-race) and audit result-derived columns separately. (Plan 03-05)

3. **`expanding().shift(1)` crosses group boundaries in z-score computation** -- Verified via pandas test: `df.groupby('group')['value'].expanding().mean().shift(1).values` allows Group A's last expanding mean to shift into Group B's first row. The `.shift(1)` must be applied per-group, not on the concatenated series. Use `groupby().apply(lambda x: x.expanding().mean().shift(1))` or compute cumulative count/sum/sum-of-squares explicitly per group. (Plan 03-02)

4. **Z-score test expectations contradict `min_periods=5`** -- Plan 03-02 tests 5-7 construct 2 races and expect valid z-scores for race 2. But `min_periods=5` in the expanding window requires 5 prior race-level observations. With only 1 prior race, the z-score should be NaN. Tests must either use 6+ races or lower min_periods for the test fixture. (Plan 03-02)

5. **Z-score standard deviation uses race means, not runner times** -- The expanding std is computed across race-level means (one value per race), not across individual runner finish times. This changes the distributional meaning: a std across 5 race means is not the same as a std across 70 runner times. The resulting z-scores may be more extreme or compressed than intended. Consider cumulative count/sum/sum-of-squares over individual runner times, frozen at race boundaries. (Plan 03-02)

6. **D-08 caps race records, not individual starts for trainers** -- The person-race aggregation creates one row per person per race. Keeping the "most recent 100" rows means 100 races, not 100 starts. A trainer with 3 runners per race would contribute up to 300 valid starts. For jockeys (1 runner per race) this is equivalent, but for trainers the constraint is weaker than D-08 specifies. (Plan 03-03)

7. **Orchestrator data flow ambiguity** -- `extract_race_context_features()` and `extract_horse_basic_features()` are described as extracting column subsets but operate sequentially on one DataFrame. The documentation says they "return df" but it is unclear whether they subset columns or merely ensure columns exist. If they subset, the second call loses columns from the first. If they don't subset, they are identity functions. The intent should be clarified. (Plan 03-01)

8. **Person-stat per-row slicing is O(n^2) and may be slow on 311K rows** -- The "practical approach" described for D-08 iterates each person-race row and slices all prior rows. With 311,806 entries and ~700 unique persons, total iterations are O(311K * avg_history_length). For jockeys with long careers (500+ races), this becomes expensive. A deque-based running-sum approach would be O(n) total. (Plan 03-03)

#### MEDIUM Severity

9. **`再` (re-run) omitted from target-status handling** -- `ResultSchema` documents `再` as a possible `finish_note` value, but the six-category result_status mapping has no defined behavior for it. Need an explicit handling rule. (Plan 03-04)

10. **Merge cardinality not enforced** -- The inner join on result assumes 1:1, but there is no `validate="one_to_one"` parameter. Adding merge validation with explicit anti-join checks would prevent silent row loss if data assumptions change. (Plan 03-01)

11. **Fixture race IDs have inconsistent lengths** -- `"20150101010101"` is 14 digits while the documented `YYYYPPCCDDRR` format is 12 digits. Fixtures should match the actual data format. (Plan 03-01)

12. **Unexpected column handling should be a hard error** -- Plan 03-05 says `logger.warning()` for unexpected columns but `raise ValueError` for missing columns. Both should be hard errors to maintain allowlist integrity. (Plan 03-05)

13. **Identifier columns in FEATURE_COLUMNS** -- `race_id` and `race_date` are metadata identifiers, not model features. They should be separated from `FEATURE_COLUMNS` into a `METADATA_COLUMNS` list to avoid confusion and prevent accidental use as LightGBM inputs. (Plan 03-05)

14. **Trainer test wording implies current-race leakage** -- The test description says "all 3 runners see trainer_rolling_top3_rate reflecting 2/3" but this is the rate AFTER the race. The test must verify the rate for the trainer's NEXT race, not the race itself, to prove temporal safety. (Plan 03-03)

#### LOW Severity

15. **Output column counts are inconsistent** -- Plan 05 success criteria says "72 features + 4 auxiliary = ~76 columns" but the actual count is 72 features + 2 entity keys + 4 auxiliary = 78. Minor documentation issue.

16. **2001 horse-age notation change** -- Codex flagged that Japan changed horse-age notation in 2001. This affects 1986-2000 data in Phase 6 scope but not the 2015-2021 data used in Phase 3. Not a blocking concern for this phase.

### Suggestions

1. **Fix the merge to handle race_id correctly**: Merge result using `on=["horse_race_id", "race_id"]` or drop the result's `race_id` column before merging. Add `validate="one_to_one"` for the result merge and `validate="many_to_one"` for the race merge.

2. **Fix the z-score expanding shift to be group-local**: Replace `grp["race_ft_mean"].expanding().mean().shift(1).values` with either:
   - `grp["race_ft_mean"].transform(lambda x: x.expanding(min_periods=5).mean().shift(1))`
   - Or explicit per-group computation: `for name, group in grp: ...`

3. **Fix the audit to handle identifier columns**: Either:
   - Pass only `[RaceSchema, EntrySchema]` to `audit_leakage()` and separately verify that no result-derived columns appear (except via `prev_*` lag prefix)
   - Or exclude identifier columns (`race_id`, `horse_race_id`) from the audit's post-race set before checking

4. **Fix D-08 to count individual starts**: Track `valid_start_count` per person-race row. When trimming to 100 starts, iterate person-race rows in reverse chronological order and accumulate `valid_start_count` until the sum exceeds 100, then trim at that boundary. This handles multi-runner trainers correctly.

5. **Align z-score tests with min_periods=5**: Either construct fixtures with 6+ races or use a separate `min_periods` parameter for test fixtures. Document why 5 is the chosen threshold.

6. **Clarify extract functions**: Document that `extract_race_context_features()` and `extract_horse_basic_features()` are validation/annotation functions that ensure expected columns exist and compute derived columns (like `field_size`), not column-subsetting functions.

7. **Make unexpected columns a hard error**: Change `logger.warning()` to `raise ValueError()` for unexpected columns in the allowlist validation.

8. **Handle `再` finish_note**: Add `result_status = "re_run"` for `finish_note == "再"` with `exclude_from_training = True` (re-run entries should not be training data).

### Risk Assessment

**HIGH.** Three implementation-level defects will prevent the pipeline from producing correct output as planned: (1) the merge creates suffixed race_id columns breaking all downstream code, (2) the z-score expanding shift crosses group boundaries producing incorrect normalization, and (3) the audit will always flag race_id as leaked. These are code-level issues that can be fixed during implementation without re-planning, but they must be addressed. The D-08 race-vs-starts issue is a semantic concern that affects trainer features specifically.

---

## Consensus Summary

Review conducted by 1 AI system (Codex). Claude was skipped (same runtime).

### Cycle Comparison

| Metric | Cycle 1 | Cycle 2 | Cycle 3 |
|--------|---------|---------|---------|
| Total HIGHs | 7 | 8 | 8 (4 resolved + 3 partially resolved + 8 new) |
| Resolved | 0 | 1 | 4 (#1, #4, #5, #6 from Cycle 2) |
| Partially Resolved | 0 | 4 | 3 (#2, #3, #8 from Cycle 2) |
| Unresolved | 7 | 2 | 0 (from Cycle 2) |
| New HIGHs raised | N/A | 4 | 8 |

### Agreed Strengths

- **4 of 8 Cycle 2 HIGHs now fully resolved**: valid-start lag filtering, sum-based trainer rates, finish_note-based status classification, race_id ordering
- Collision-safe horse entity key using birth_year_proxy (verified on 2015-2021 data)
- Race-level z-score architecture is fundamentally correct (implementation detail needs fix)
- Static FEATURE_COLUMNS allowlist prevents silent column inclusion
- Comprehensive test coverage (~62 tests planned across 5 plans)
- Clear wave-based dependency structure with proper blocking
- Phase 1 audit_leakage() integration as final gate

### Agreed Concerns (Cycle 3 -- Codex)

**HIGH severity (8 new + 3 partially resolved):**

1. **Merge creates suffixed race_id columns** -- entry.merge(result, on="horse_race_id") produces race_id_x/race_id_y. Fix merge key. (NEW)

2. **audit_leakage() flags race_id as leaked** -- ResultSchema marks race_id as post-race. Feature output includes race_id. Audit will always fail. Fix audit semantics. (NEW, verified via code)

3. **expanding().shift(1) crosses group boundaries** -- Pandas applies shift to the concatenated series, not per-group. Group B inherits Group A's last value. Must use group-local shift. (NEW, verified via pandas test)

4. **Z-score test expectations contradict min_periods=5** -- Tests use 2 races but implementation requires 5 prior races for valid z-score. Fix tests or min_periods. (NEW)

5. **Z-score std across race means differs from runner-level std** -- Standard deviation of race-level means has different distributional properties than std across individual runner times. Consider cumulative sum-of-squares approach. (NEW)

6. **D-08 caps race records not starts for trainers** -- 100 race records can contain more than 100 valid starts when trainers have multiple runners per race. (PARTIALLY RESOLVED from Cycle 2 #2)

7. **Orchestrator data flow unclear for extract functions** -- Sequential calls on one DF with unclear column subsetting semantics. (NEW)

8. **Person-stat O(n^2) performance on 311K rows** -- Per-row slicing approach may be slow. Use deque-based running sums. (NEW)

### Divergent Views

Single reviewer -- no divergent views to report.

### Planner Action Items (Priority Order)

1. **Fix merge key handling** (HIGH, trivial): Merge result on `["horse_race_id", "race_id"]` or drop result's race_id before merge. Add merge cardinality validation.

2. **Fix z-score group-local shift** (HIGH, moderate): Replace `expanding().mean().shift(1).values` with group-local transform or explicit per-group computation.

3. **Fix audit_leakage() for identifier columns** (HIGH, moderate): Either exclude race_id/horse_race_id from the audit, or pass only [RaceSchema, EntrySchema] and verify result-derived columns separately.

4. **Fix D-08 start-level counting** (HIGH, moderate): Track valid_start_count per person-race and trim based on accumulated starts, not race count.

5. **Align z-score tests with min_periods** (HIGH, trivial): Construct fixtures with sufficient races or lower min_periods for test scope.

6. **Make unexpected columns a hard error** (MEDIUM, trivial): Change warning to ValueError.

7. **Handle `再` finish_note** (MEDIUM, trivial): Add re_run status and exclude from training.

8. **Clarify extract function semantics** (MEDIUM, documentation): Document that they ensure/compute columns, not subset them.
