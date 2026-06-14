---
phase: 06-data-integration
plan: 02
subsystem: data-pipeline
tags: [integration, parquet, idempotency, validate-before-swap, transactionality, fk-integrity, horse_race_id-1to1]

# Dependency graph
requires:
  - phase: 06-data-integration
    provides: "06-01 regenerated Kaggle race/entry/result at data/standard/kaggle/ with SCHEMA_DTYPE_MAP nullable dtypes + D-01 grade detection (BLOCKER-1 separate input path)"
  - phase: 04-scraping-infrastructure-race-data
    provides: "SCHEMA_DTYPE_MAP + _atomic_write_parquet + validate_integrity (the 3 primitives integration.py reuses)"
  - phase: 01-data-schema-leak-audit
    provides: "audit_leakage + EntrySchema.popularity/win_odds pre_race=False contract (MEDIUM #13 expected-entry-leak set)"
provides:
  - "src/pipeline/integration.py::integrate_standard_layer(standard_dir, kaggle_input_dir=None) -> dict — the Phase 6 Wave-2 entry point that unifies Kaggle + scraped corpora into data/standard/{race,entry,result}.parquet"
  - "DEDICATED _commit_staging(staging_dir, standard_dir) module-level swap function (cycle-5 transactionality boundary that the test patches directly, NOT global os.replace)"
  - "Hard-violation filter extended with 'mismatch'/'1-to-1' tokens (HIGH #8b cycle-4) so the entry/result horse_race_id 1-to-1 violation string at normalizer.py:330-334 is classified HARD and raises ValueError"
  - "tests/pipeline/test_integration.py — 11 tests across TestIntegrationHermetic (9, ungated) + TestUnifiedCorpus (2, _require_scraped_data autouse skip)"
affects: [06-data-integration/06-03 (run_all_validations against unified root, all 5 tables present), feature-regen, backtest]

# Tech tracking
tech-stack:
  added: []  # no new deps; reused SCHEMA_DTYPE_MAP + _atomic_write_parquet + validate_integrity + audit_leakage
  patterns:
    - "validate-before-swap with idempotent recovery: stage all 3 to tempfile.mkdtemp(prefix='.integration_staging_'), validate each (row count > 0, schema column-set, PK unique), swap via DEDICATED _commit_staging (3 os.replace). Re-run recovers (integration reads only immutable inputs)."
    - "Hard-violation filter extension: 'duplicate' OR 'orphan' OR 'mismatch' OR '1-to-1' — the latter two are load-bearing for the entry/result 1-to-1 case which contains NEITHER 'duplicate' NOR 'orphan'."
    - "Two-class test split: TestIntegrationHermetic (NO autouse, runs against tmp_path) + TestUnifiedCorpus (autouse _require_scraped_data skip when scraped corpus is smoke-only)."
    - "Cycle-5 test isolation: regression tests inject data so the load-bearing token is the SOLE classifier (DISJOINT unique horse_race_ids -> validate_integrity returns EXACTLY ONE mismatch violation)."

key-files:
  created:
    - src/pipeline/integration.py
    - tests/pipeline/test_integration.py
  modified:
    - tests/pipeline/conftest.py

key-decisions:
  - "HIGH #5 idempotency: Kaggle read from kaggle_input_dir (default standard_dir/'kaggle'), NEVER from output path. test_integration_is_idempotent proves byte-identical re-run."
  - "HIGH #6 cycle-3 + cycle-5: validate-before-swap via tempfile.mkdtemp staging + DEDICATED _commit_staging swap function. Transactionality model ACCURATELY described as 'validate-before-swap with idempotent recovery' (NOT perfectly atomic; mid-swap crash recoverable via re-run because the transform reads only from immutable inputs)."
  - "HIGH #8b cycle-4 production fix + cycle-5 test isolation: hard-violation filter extended with 'mismatch'/'1-to-1'; cycle-5 regression test uses DISJOINT unique horse_race_ids so the mismatch token is the SOLE classifier (validate_integrity returns EXACTLY ONE violation, no duplicate, no orphan)."
  - "HIGH #6 cycle-6 test-data mutation: test_integration_partial_swap_recoverable MUTATES THE RACE INPUT (non-key column, race_id preserved) so the new-generation race differs from canonical; entry/result inputs unchanged so their new-gen == canonical — making the mid-swap MIXED-GENERATION state (race=new-gen, entry/result=canonical) OBSERVABLE and the recovery meaningful."
  - "MEDIUM #13 audit contract: race must leak []; entry must leak EXACTLY {popularity, win_odds} per Phase 1 D-03 (Harville EV proxy). Any other leak raises ValueError."
  - "Pitfall 5 honored: SCHEMA_BY_TABLE hardcoded as {race,entry,result}; never iterates TABLE_TO_SCHEMA.keys() (would include the Phase 5 tables excluded per D-05)."

patterns-established:
  - "DEDICATED patchable swap function: extract the swap loop out of the main entry point so tests can inject mid-swap failure by monkeypatching the SWAP symbol (not global os.replace which is shared with the staging-write path)."
  - "Cycle-5 test isolation principle: regression tests inject data so the load-bearing token is the SOLE classifier — removing the token from the production filter would let the test data pass entirely, failing the pytest.raises."
  - "Audit-contract assert: post-integration audit_leakage return values are compared against an EXPECTED leak set (not just an empty-list check); intentional post-race columns are allowlisted per Phase 1 D-03."

requirements-completed: [DATA-05]

# Metrics
duration: 13min
completed: 2026-06-14
---

# Phase 6 Plan 02: Unified Standard-Layer Integration Summary

**integrate_standard_layer unifies Kaggle (data/standard/kaggle/) + scraped (data/standard/scraped/{YYYYMM}/) corpora into data/standard/{race,entry,result}.parquet via validate-before-swap with idempotent recovery (DEDICATED _commit_staging swap function), with the hard-violation filter extended to catch the entry/result horse_race_id 1-to-1 mismatch**

## Performance

- **Duration:** ~13 min (777s)
- **Started:** 2026-06-14T13:50:36Z
- **Completed:** 2026-06-14T14:03:33Z
- **Tasks:** 2/2
- **Files created:** 2 (integration.py + test_integration.py)
- **Files modified:** 1 (conftest.py — 2 new fixtures)

## Accomplishments

- **HIGH #5 (idempotency — KEPT from cycle 2):** Kaggle is read from `kaggle_input_dir` (default `standard_dir / 'kaggle'`), a STABLE SEPARATE input path that is NEVER the output path. `test_integration_is_idempotent` runs `integrate_standard_layer` twice and asserts byte-identical SHA-256 across race/entry/result.
- **HIGH #6 (transactionality — cycle 3 + cycle 4 + cycle 5):** validate-before-swap implemented via `tempfile.mkdtemp(prefix='.integration_staging_', dir=standard_dir)` staging. All 3 merged frames are staged via `_atomic_write_parquet`; each staged file is validated (row count > 0, schema column-set match, PK uniqueness); only then does the DEDICATED `_commit_staging(staging_dir, standard_dir)` perform the 3 `os.replace` swaps. Transactionality model is ACCURATELY described as "validate-before-swap with idempotent recovery" — NOT perfectly atomic, but a mid-swap crash leaves at most a partial swap that a re-run fully recovers (integration reads only from immutable inputs). The cycle-5 isolated test `test_integration_partial_swap_recoverable` patches `_commit_staging` directly (NOT global `os.replace`) so the failure fires during the actual SWAP, mutates the race input so new-gen != canonical, observes the mixed-generation state on disk (race=new-gen, entry/result=canonical), and proves byte-identical recovery on re-run + 3rd-run idempotency.
- **HIGH #7 (autouse skip — KEPT from cycle 2):** two-class split honored. `TestIntegrationHermetic` (9 tests) has NO autouse skip and runs unconditionally against `tmp_path` synthetic data. `TestUnifiedCorpus` (2 tests) has `_require_scraped_data` autouse skip that fires when `data/standard/scraped/` has <2 month directories (smoke-only state).
- **HIGH #8 (FK orphan — KEPT from cycle 2):** `test_referential_integrity_orphan_raises` injects an entry row whose `race_id` is `999999999999` (not in race table); `validate_integrity` returns the orphan violation and `integrate_standard_layer` raises ValueError.
- **HIGH #8b (horse_race_id 1-to-1 mismatch — cycle 4 production fix + cycle 5 TEST ISOLATION):** the hard-violation filter is `"duplicate" in v or "orphan" in v or "mismatch" in v or "1-to-1" in v`. The cycle-5 isolated test `test_horse_race_id_mismatch_raises` injects DISJOINT UNIQUE horse_race_ids (entry=`["E1", "S_E"]`, result=`["R1", "S_R"]`): both tables internally unique (no duplicates), all race_ids present in race_df (no FK orphan). `validate_integrity` returns EXACTLY ONE violation containing `"mismatch"` AND `"1-to-1"` — proving the token is the SOLE classifier and load-bearing for the integration's hard-classification.
- **HIGH #9 (column-set equality — KEPT from cycle 2):** `_assert_column_set_equality(df, schema, source_label)` is called on BOTH Kaggle and scraped frames BEFORE reindex; mismatches raise ValueError naming extra/missing columns.
- **MEDIUM #13 (audit_leakage CALLED):** `integrate_standard_layer` calls `audit_leakage([RaceSchema], merged_race, ...)` and `audit_leakage([EntrySchema], merged_entry, ...)`. The return dict carries an `audit` sub-dict; `test_no_post_race_leakage_audit_called` verifies race leaks `[]` and entry leaks EXACTLY `{popularity, win_odds}` per Phase 1 D-03.
- **MEDIUM #14 (explicit missing-input errors):** `FileNotFoundError` for missing Kaggle file or missing per-month table file; `ValueError` when `scraped/` root is absent or has zero month dirs.
- **Pitfall 5 (D-05 protection):** `SCHEMA_BY_TABLE` hardcoded as `{race, entry, result}`; the Phase 5 tables are deliberately not in the map. `test_odds_payoff_not_overwritten` plants sentinel odds/payoff files and asserts byte-identical SHA-256 + row count post-integration.
- **Pitfall 6 (pre-dedup overlap RAISES):** `test_no_duplicate_race_ids_fail_loud` constructs an overlapping race_id and asserts ValueError mentioning "duplicate".
- **Full suite green:** 479 passed, 3 skipped (302s). The 3 skipped tests are the 2 `TestUnifiedCorpus` (smoke-only corpus, autouse skip) plus 1 pre-existing.

## Task Commits

1. **Task 1 (RED):** hermetic fixtures + 11-stub scaffold — `2216c09` (test)
2. **Task 2 (GREEN):** integrate_standard_layer implementation + cycle-5 isolated test bodies — `49c4472` (feat)

## Files Created/Modified

- `src/pipeline/integration.py` — NEW. Exports `integrate_standard_layer`, `SCHEMA_BY_TABLE`, `PK_BY_TABLE`, `_recast_to_canonical`, `_assert_column_set_equality`, `_commit_staging`. Reuses `SCHEMA_DTYPE_MAP` + `_atomic_write_parquet` + `validate_integrity` from `src.scraper.normalizer` (NO re-implementation). Reuses `audit_leakage` from `src.schemas.audit`.
- `tests/pipeline/test_integration.py` — NEW. 11 tests across 2 classes. Includes the cycle-5 ISOLATED `test_horse_race_id_mismatch_raises` (DISJOINT unique horse_race_ids) and `test_integration_partial_swap_recoverable` (`_commit_staging` monkeypatch + race-input mutation + mixed-generation observation + recovery + 3rd-run idempotency).
- `tests/pipeline/conftest.py` — MODIFIED. Adds `tmp_kaggle_input_dir` (HIGH #5 separate input path) and `tmp_scraped_partitions_dir` (202301/202302 synthetic Phase 4 layout). Both reuse the existing `sample_standard_*` fixtures reindexed to canonical schema column order.

## Transactionality Model

**Validate-before-swap with idempotent recovery (NOT perfect atomicity).**

1. Build all 3 merged DataFrames in memory.
2. Validate integrity (`validate_integrity` + extended hard-violation filter).
3. Run `audit_leakage` on race + entry.
4. Stage all 3 to `tempfile.mkdtemp(prefix='.integration_staging_', dir=standard_dir)` via `_atomic_write_parquet`. (NOTE: `_atomic_write_parquet`'s internal `os.replace` commits each STAGING file BEFORE the swap loop runs — these staging commits are NOT routed through `_commit_staging`.)
5. Validate each staged file: row count > 0, schema column-set, PK uniqueness. On failure, remove the staging dir and raise (existing output files untouched).
6. ONLY AFTER all staged files validate, call `_commit_staging(staging_dir, standard_dir)` (DEDICATED, PATCHABLE) to swap each into root. Wrap in `try/finally` that best-effort-removes the staging dir.

The 3 sequential `os.replace` calls INSIDE `_commit_staging` are NOT perfectly atomic; a failure between the 2nd and 3rd swap leaves a partial swap. HOWEVER, because integration reads only from immutable inputs (`data/standard/kaggle/` + scraped partitions) and NEVER from its own output, re-running `integrate_standard_layer` produces IDENTICAL output (against the same inputs), fully recovering. This is more robust than a backup-and-restore scheme (which depends on the backup surviving the crash) and is the genuinely correct guarantee for a deterministic, idempotent transform.

`test_integration_partial_swap_recoverable` (cycle-5 isolated) documents this recovery path via `_commit_staging` monkeypatch failure injection: race input is mutated (non-key column, race_id preserved) so new-gen != canonical; the failing `_commit_staging` raises on the 2nd `os.replace`, leaving a mixed-generation corpus on disk (race=new-gen, entry/result=canonical). The test asserts this mixed-generation state is OBSERVABLE, then RESTORES `_commit_staging` and re-invokes — proving all 3 outputs recover to a consistent new-generation corpus. A 3rd invocation is byte-identical, confirming the recovered state is a stable fixed point.

## Hard-Violation Filter Extension (HIGH #8b cycle 4)

`validate_integrity` (normalizer.py:263-374) returns the entry/result 1-to-1 mismatch violation as `"horse_race_id mismatch: entry/result are not 1-to-1 (only-in-entry=N, only-in-result=N, count-mismatch={...})"` at normalizer.py:330-334. This string contains NEITHER `"duplicate"` NOR `"orphan"`, so the Phase 4 token filter (`"duplicate" in v or "orphan" in v`) classifies it SOFT (warning only) and would silently write a structurally inconsistent entry/result corpus.

This module EXTENDS the filter to `"duplicate" in v or "orphan" in v or "mismatch" in v or "1-to-1" in v`. Adding BOTH `"mismatch"` AND `"1-to-1"` is belt-and-braces — either substring matches the violation string.

**Cycle-5 proof that the token is load-bearing:** the regression test `test_horse_race_id_mismatch_raises` uses DISJOINT UNIQUE horse_race_ids (entry=`["E1", "S_E"]`, result=`["R1", "S_R"]`): both tables are internally unique (no duplicate check fires at normalizer.py:293-307), all race_ids are present in the race table (no FK orphan fires at normalizer.py:338-372). `validate_integrity` therefore returns EXACTLY ONE violation — the mismatch. The test asserts `len(violations) == 1 and "mismatch" in violations[0] and "1-to-1" in violations[0]`, proving the token is the SOLE classifier. Without `"mismatch"` in the filter, this data has NO hard violation and `integrate_standard_layer` would NOT raise — so the `pytest.raises(ValueError)` would fail. Together the two assertions prove the token is load-bearing for BOTH violation detection AND integration hard-classification.

## Odds/Payoff NON-OVERWRITE Proof (D-05)

`test_odds_payoff_not_overwritten` plants sentinel `odds_trifecta.parquet` and `payoff.parquet` in `standard_dir` BEFORE integration, captures their SHA-256 + row counts, runs `integrate_standard_layer`, and asserts BOTH SHA-256 AND row counts are identical post-integration. The `SCHEMA_BY_TABLE` allowlist (`{race, entry, result}` only) is the structural guarantee — `integrate_standard_layer` never reads or writes the Phase 5 tables.

## Cycle-5 Test-Isolation Patterns Established

These two patterns are reusable for any future regression test where a production filter has been extended:

1. **Sole-classifier injection:** construct test data so the target token is the ONLY reason the production code path fires. Assert the lower-level function returns EXACTLY ONE violation containing the token, THEN assert the higher-level function raises. Removing the token would let the test data pass entirely.

2. **Dedicated-patchable-boundary + input-mutation:** extract the production swap into a DEDICATED module-level function so the test can monkeypatch THAT symbol (not a global like `os.replace`, which is shared with other call sites). Mutate an input between the clean run and the failing run so the new generation differs from canonical — making the "post != canonical" assertion meaningful and the recovery observable.

## Decisions Made

- **`_commit_staging` is module-level, not nested inside `integrate_standard_layer`:** this is what makes it patchable via `monkeypatch.setattr(integration_mod, "_commit_staging", failing_swap)`. A nested closure would not be patchable. The function performs exactly 3 `os.replace` calls (one per table) so the test's 2nd-call counter intercepts the entry swap.
- **`audit` sub-dict is part of the return value, not a side effect:** makes `test_no_post_race_leakage_audit_called` a simple return-value assertion (no monkeypatch spy needed). The race audit MUST return `[]` (race is pre-race only); the entry audit MUST leak EXACTLY `{popularity, win_odds}` per Phase 1 D-03. Any other leak raises ValueError.
- **`test_horse_race_id_mismatch_raises` injects the mismatch in the KAGGLE input (not scraped):** the synthetic Kaggle fixture is rewritten with `horse_race_id="E1"` in entry and `"R1"` in result. A scraped partition with the same DISJOINT pattern (`S_E` / `S_R`) is added so the merged frame's mismatch is unambiguous. Both Kaggle and scraped rows reference race_ids present in the race table (no FK orphan). The result: `validate_integrity` returns EXACTLY ONE violation containing `"mismatch"` and `"1-to-1"`.
- **`test_integration_partial_swap_recoverable` mutates a NON-KEY object column on the race input:** preserves `race_id` (so referential integrity stays valid), only changes content. entry/result inputs are LEFT UNCHANGED so their new-gen == canonical — this is what makes the mid-swap mixed-generation state observable (race swapped to new-gen, entry/result still canonical).

## Deviations from Plan

None — plan executed exactly as written. The 5 cross-AI review cycles converged the must_haves to exact behavioral contracts, and the implementation honors each one literally:

- HIGH #5: `kaggle_input_dir = standard_dir / 'kaggle'` default, separate path, idempotent re-run test.
- HIGH #6 cycle-3 + cycle-5: `tempfile.mkdtemp` staging + DEDICATED `_commit_staging` + cycle-5 isolated test patching `_commit_staging` (NOT global `os.replace`) + race-input mutation.
- HIGH #7: two-class split with NO autouse on `TestIntegrationHermetic`.
- HIGH #8: FK orphan injection, `validate_integrity` reports it, integration raises.
- HIGH #8b cycle-4 + cycle-5: hard-violation filter includes `"mismatch"` AND `"1-to-1"`; cycle-5 test uses DISJOINT unique horse_race_ids and asserts `validate_integrity` returns EXACTLY ONE violation.
- HIGH #9: `_assert_column_set_equality` before reindex.
- MEDIUM #13: `audit_leakage` CALLED, return dict carries `audit` sub-dict.
- MEDIUM #14: explicit `FileNotFoundError` / `ValueError` for each missing-input case.
- Pitfalls 5/6 + D-05 honored: hardcoded 3-table allowlist, pre-dedup overlap raises, no `source` column.

The only adjustment was a documentation rewording: the integration.py docstring/comments originally mentioned the literal Phase 5 table names (`odds_trifecta`/`payoff`) to document the D-05 exclusion rationale. The PLAN.md verification gate includes `! grep -qE 'odds_trifecta|payoff' src/pipeline/integration.py` (defense against accidentally writing those tables), so the docstring was reworded to refer to "the Phase 5 tables" without naming them literally. No functional change.

## Issues Encountered

None beyond the documentation rewording noted above.

## User Setup Required

None — no external service configuration required. The integration module is a pure file-to-file transform over the existing `data/standard/kaggle/` + `data/standard/scraped/{YYYYMM}/` Parquet. Wave 3 (Plan 06-03) invokes `integrate_standard_layer` against the real corpus.

## Next Phase Readiness

- **Ready for 06-03 (validation):** `integrate_standard_layer` produces `data/standard/{race,entry,result}.parquet` (unified) alongside the Phase 5 `odds_trifecta`/`payoff` (untouched). Plan 06-03-T2 runs the full 8-point `run_all_validations` against the unified root where all 5 tables coexist.
- **Ready for feature regeneration:** the unified `race/entry/result` Parquet covers 2015-2026/5 (post-D-06 full scrape); Phase 3 `feature_generator.py` reads `data/standard/*.parquet` unchanged.
- **Cycle-5 convergence:** all 6 HIGH issues from cycles 2-5 are resolved with production fixes whose regression tests prove the load-bearing properties. The plan is convergence-pass-ready.

## Self-Check: PASSED

- `src/pipeline/integration.py` — FOUND
- `tests/pipeline/test_integration.py` — FOUND
- `tests/pipeline/conftest.py` — FOUND (modified; 2 new fixtures present)
- Commit `2216c09` (Task 1 RED) — FOUND in git log
- Commit `49c4472` (Task 2 GREEN) — FOUND in git log
- `grep _commit_staging src/pipeline/integration.py` — FOUND (3 occurrences: definition, docstring mention, call)
- `grep _commit_staging tests/pipeline/test_integration.py` — FOUND (patch target)
- `grep test_horse_race_id_mismatch_raises tests/pipeline/test_integration.py` — FOUND
- Hermetic suite: 9 passed (Cycle-5 ISOLATED tests both pass)
- Full suite: 479 passed, 3 skipped (302s)

---
*Phase: 06-data-integration*
*Completed: 2026-06-14*
