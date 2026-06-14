---
phase: 06-data-integration
reviewers: [codex]
reviewed_at: 2026-06-14T22:05:00+09:00
plans_reviewed:
  - 06-01-PLAN.md
  - 06-02-PLAN.md
  - 06-03-PLAN.md
cycle: 6
prior_cycle_high: 1
cycle_6_fix_commit: c7c5e55
converged: true
---

# Cross-AI Plan Review — Phase 6 (Cycle 6 — FINAL convergence, CONVERGED)

Cycle-6 re-review — the FINAL convergence pass of the plan-review-convergence loop.
The single cycle-5 HIGH (partial-swap recovery test did not observe a mixed-generation
state) was addressed by a surgical fix to ONE test in **06-02-PLAN.md**
(`test_integration_partial_swap_recoverable`, git commit `c7c5e55`, +49/-42 lines —
touched no other file). Codex (gpt-5.5 via `codex exec`, codex-cli 0.139.0) re-reviewed
the revised plans with repository read access (workdir:
`/Users/hart/develop/keiba-ai-v2`). The orchestrator independently re-verified every
load-bearing claim against the working tree before recording the adjudication below.

**Headline:** the cycle-5 HIGH is **FULLY RESOLVED**. **0 HIGH concerns remain.**
Trend: 14 → 7 → 5 → 3 → 1 → **0** (monotonic, decreasing, converged). The plan-review-
convergence loop has converged; Phase 6 may proceed to execution.

The cycle-6 fix is exactly what the cycle-5 reviewer's "Recommended next actions"
prescribed, applied surgically:
1. **Mutate the `race` scraped input** (non-key object column, `race_id` preserved) so the
   new-generation race hash ≠ canonical (06-02-PLAN.md:298-309). Entry/result inputs are
   left UNCHANGED so their new-generation == canonical.
2. **Observe the mixed-generation state after the failure** (06-02-PLAN.md:332-345):
   `post_race != canonical["race"]` (new-gen, swapped), `post_entry == canonical["entry"]`
   (not swapped), `post_result == canonical["result"]` (not swapped). This is the
   observable proof of a detectable mid-swap inconsistent corpus — the missing piece in
   cycle 5.
3. **Recover and prove consistency** (06-02-PLAN.md:347-365): restore `_commit_staging`,
   re-invoke, assert `recovered["race"] != canonical["race"]` (mutated input applied) and
   `recovered["entry"] == canonical["entry"]`, `recovered["result"] == canonical["result"]`.
   A 3rd run is byte-identical (idempotent fixed point).

Codex raised **0 NEW HIGH concerns** and **0 NEW MEDIUM concerns** — only 3 LOW
observations (style/clarity nits that do not affect correctness or test validity).

---

## Codex Review

### Plan 06-01 Review

**Summary**

Unchanged since cycle 5 (commit `c7c5e55` touched only 06-02-PLAN.md). The D-01 grade
detection, nullable-dtype regeneration, Kaggle-input-path separation, odds/payoff
non-overwrite, and 3-table-specific validation design remain consistent. No new HIGH
defects.

**New Concerns**

- None.

**Suggestions**

- At implementation time, record the graded count and the odds/payoff pre/post SHA-256
  values in the SUMMARY (already required by the plan's `<output>` block).

**Risk Assessment: LOW.** The main boundary conditions are covered by tests and
verification commands.

---

### Plan 06-02 Review

**Summary**

The cycle-6 fix ensures the failure fires during the actual swap, that `race` alone is
swapped to the new generation before the failure, and that this mixed-generation state is
observable in the exception-handling's wake. The cycle-5 single HIGH is resolved. The
input-mutation method has a minor robustness-improvement opportunity, but it does not
prevent the test from running against the current fixture.

#### Cycle-5 HIGH Adjudication (06-02)

| # | Verdict | Orchestrator-Verified Evidence |
|---|---------|--------------------------------|
| HIGH (cycle 5: partial-swap recovery test does not observe a mixed-generation state) | **FULLY RESOLVED** | The cycle-6 fix addresses BOTH structural flaws the cycle-5 reviewer identified: (1) the race input is now MUTATED (06-02-PLAN.md:298-309 — `non_key_col = next(c for c in srace.columns if c != "race_id" and srace[c].dtype == object); srace.loc[0, non_key_col] = str(srace.loc[0, non_key_col]) + "_MUTATED"`, race_id preserved), so the race new-gen hash differs from canonical; (2) the post-failure corpus state is now OBSERVED via three explicit assertions (06-02-PLAN.md:336-344: `post_race != canonical["race"]`, `post_entry == canonical["entry"]`, `post_result == canonical["result"]`). **Logic trace of `failing_commit_staging`** (06-02-PLAN.md:316-321): `call_counter["n"]` starts at 0; iteration 1 (`table="race"`) → n=1, `if n==2` False → `real_replace` executes → **race IS swapped**; iteration 2 (`table="entry"`) → n=2, `if n==2` True → raises OSError BEFORE `real_replace` → **entry NOT swapped, result NOT swapped**. So at the OSError the on-disk state is genuinely mixed-generation: race=new-gen, entry=result=canonical. The cycle-5 "dead code" defect (the `try`-body `post != canonical` assertion never executed because the raise was unconditional) is gone — the post-failure state is now observed unconditionally AFTER the `try/except OSError` block (06-02-PLAN.md:326-345), so it executes whether or not the OSError propagated. Recovery (06-02-PLAN.md:347-365) restores `_commit_staging`, re-invokes, and asserts a consistent new-generation corpus + a 3rd-run byte-identical fixed point. **Orchestrator-verified against** 06-02-PLAN.md:298-365, normalizer.py:643-653, normalizer.py:330-334. **FK preservation confirmed**: the mutation changes a non-key object column (`race_id` is explicitly excluded by `c != "race_id"`), so referential integrity stays valid. |
| HIGH #8b (mismatch filter — carried, cycle-4 prod fix + cycle-5 test fix) | **RESOLVED** (KEPT) | Filter extended with `"mismatch"`/`"1-to-1"`; cycle-5 test proves token is load-bearing via DISJOINT unique horse_race_ids. The mismatch violation string at normalizer.py:330-334 contains NEITHER `"duplicate"` NOR `"orphan"` — orchestrator-verified (the string is `"horse_race_id mismatch: entry/result are not 1-to-1 (only-in-entry=..., only-in-result=..., count-mismatch={...})"`). |
| HIGH #6 (transactionality design — carried) | **RESOLVED** (KEPT) | Validate-before-swap via `tempfile.mkdtemp(prefix='.integration_staging_', dir=standard_dir)`; staged files validated before swap; idempotent recovery via re-run against immutable inputs. The cycle-6 test now proves the recovery half against a real mixed-generation state. |
| HIGH #5 (idempotency — carried) | **RESOLVED** (KEPT) | Separate `kaggle_input_dir`; idempotency test retained. |
| HIGH #7 (autouse skip — carried) | **RESOLVED** (KEPT) | Two-class split. |
| HIGH #8 (FK orphan — carried) | **RESOLVED** (KEPT) | Orphan injection + `validate_integrity` + ValueError. |
| HIGH #9 (column-set equality — carried) | **RESOLVED** (KEPT) | `_assert_column_set_equality` before reindex. |
| MEDIUM (return-type annotation — carried) | **KEPT** (MEDIUM, not load-bearing) | `integrate_standard_layer(...) -> dict` but return includes `{"audit": {...}}`. Plan already documents the return type as `dict` (loose) to accommodate the audit sub-dict (06-02-PLAN.md:266). |

#### New Concerns (06-02)

- **LOW — `raised` flag assigned but never asserted.** The `raised = True` on OSError
  capture (06-02-PLAN.md:326-330) is dead state: no `assert raised` or
  `assert not raised` follows. The test accepts EITHER outcome (OSError propagated OR
  swallowed), so `raised` records which happened but never gates an assertion. Does not
  affect correctness — the mixed-generation state assertions (06-02-PLAN.md:336-344)
  execute unconditionally and are the load-bearing checks.
- **LOW — `non_key_col` object-dtype discovery is fragile to fixture changes.**
  `non_key_col = next(c for c in srace.columns if c != "race_id" and srace[c].dtype == object)`
  (06-02-PLAN.md:307) raises `StopIteration` if the synthetic scraped race fixture has no
  object-dtype non-key column. **Orchestrator-verified**: the current fixture
  (`tests/pipeline/conftest.py:322-336` `sample_standard_race_df`) has multiple object
  columns (`race_date`, `course_name`, `race_name`), so `next(...)` succeeds. Not a
  current defect; a future fixture refactor that drops all object columns would surface
  this.
- **LOW — recovered race is not compared to the post-failure `post_race` directly.** The
  recovery assertions (06-02-PLAN.md:352-359) compare `recovered["race"]` to
  `canonical["race"]` (proving the mutated input was applied) and the 3rd-run idempotency
  check (06-02-PLAN.md:360-365) proves a stable fixed point — but `recovered["race"]` is
  not directly compared to `post_race` (the new-gen race that was swapped in during the
  failure). Adding `assert recovered["race"] == post_race` would more directly prove the
  recovery restored the SAME new-generation file that the mid-swap failure had already
  swapped in. Not a correctness gap — the current chain transitively proves consistency —
  but a clarity improvement.

**Non-key-column mutation preserves FK (orchestrator-verified):** the mutation changes a
string column value (`str(existing) + "_MUTATED"`), `race_id` is explicitly excluded by
`c != "race_id"`, so `validate_integrity`'s FK checks (normalizer.py:338-372) still pass.
The string-column mutation is recast-safe (the canonical dtype for object columns is
string; appending a suffix does not trigger a `TypeError` in `_recast_to_canonical`).

#### Suggestions (06-02)

- Replace the dynamic `non_key_col` discovery with an explicit mutation of `race_name`
  (a column whose presence is contractually guaranteed by `RaceSchema.model_fields`).
- Add `assert recovered["race"] == post_race` to directly prove the recovery restored the
  same new-generation race that the mid-swap failure had already swapped in.
- Either delete `raised` (unused state) or, if OSError propagation is a hard contract,
  simplify to `with pytest.raises(OSError): integrate_standard_layer(standard_dir)`.

**Risk Assessment: LOW.** All three causes of the cycle-5 HIGH (failure firing before the
swap; post-failure state unobserved; all-3-files-still-canonical) have been removed. The
test now genuinely proves recovery from a detectable mid-swap mixed-generation state.

---

### Plan 06-03 Review

**Summary**

Unchanged since cycle 5 (commit `c7c5e55` touched only 06-02-PLAN.md). The 53-month
set-equality gate, the per-partition zero-tolerance non-emptiness gate, the May-2026
reach proof (date floor + 202605 partition existence), the 3-table PK-set union, the
unified-input source statistics, and the odds/payoff SHA-256 protection are all in place.
No new HIGH defects.

**New Concerns**

- None.

**Suggestions**

- When the full-scrape prerequisite (D-06 pre-task) is not yet complete, the plan must
  halt at Task 1 as designed — do not proceed to the integration step against a
  smoke-only corpus.
- Record the execution results (counts, date range, SHA-256 values, month set) in the
  SUMMARY as raw machine output.

**Risk Assessment: MEDIUM.** The plan itself is sound, but it is the operational phase
that overwrites real data; it depends on the external data quality of the 53-month scrape
and on the prerequisite task being complete.

---

## Consensus Summary

Single-reviewer cycle (Codex / gpt-5.5). The orchestrator independently verified every
load-bearing claim Codex raised against the working tree — all corroborated (see inline
"Orchestrator-Verified Evidence" in each adjudication row). No divergent views.

### Resolved cycle-5 HIGH (1 — counted out)

- **[06-02, cycle-5 HIGH] partial-swap recovery test did not observe a mixed-generation
  state** — the cycle-6 fix mutates the race scraped input (non-key column, race_id
  preserved) so the race new-gen hash ≠ canonical; the `failing_commit_staging` counter
  logic raises on the 2nd call (entry) AFTER the race swap completes via `real_replace`;
  the post-failure on-disk state is now observed unconditionally (outside the
  `try/except OSError`) and asserted to be mixed-generation (race=new-gen, entry=result=
  canonical); recovery then restores a consistent new-generation corpus and a 3rd run is
  byte-identical. The cycle-5 "dead code" defect (unconditional raise → `try`-body
  assertion never executed) is gone — the post-failure state observation is no longer
  gated on whether the OSError propagated. Orchestrator-verified against
  06-02-PLAN.md:298-365 and normalizer.py:643-653, normalizer.py:330-334.

### Unresolved HIGH (0 — converged)

None. The loop has converged.

### Carried MEDIUM (1 — not load-bearing, deferred)

- **[06-02, MEDIUM] `integrate_standard_layer` return-type annotation** — `-> dict` but
  return includes `{"audit": {...}}`. Plan documents the return type as `dict` (loose) to
  accommodate the audit sub-dict. Not a HIGH; does not block convergence or execution.

### New LOW observations (3 — optional clarity improvements, do not block convergence)

- `raised` flag unused (06-02 test) — delete or convert to `pytest.raises`.
- `non_key_col` dynamic discovery is fixture-fragile — replace with explicit `race_name`
  mutation (contractually guaranteed by RaceSchema).
- `recovered["race"]` not directly compared to `post_race` — add the assertion for
  clearer transitive proof.

These are test-clarity nits. None affects the validity of the cycle-6 fix or the
correctness of the production code design.

### Divergent Views

Single reviewer — no divergence. Orchestrator source verification corroborates all
load-bearing claims rather than contradicting.

### Convergence status

**CONVERGED.** The plan-review-convergence loop reached 0 HIGH at cycle 6. Phase 6 plans
(06-01, 06-02, 06-03) are approved for execution. The 3 LOW observations can be applied
in-execution as optional test-clarity improvements (no replan required).

---

## CYCLE_SUMMARY

CYCLE_SUMMARY: current_high=0

## Current HIGH Concerns

None.
