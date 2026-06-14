---
phase: 06
slug: data-integration
status: ready
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-14
revised: 2026-06-14
revision_note: "Cycle-4 — resolve 5 remaining cycle-3 HIGHs (2 NEW + 3 PARTIAL). Targeted fixes (do NOT regress prior-resolved HIGHs). Key changes: (1) HIGH #8b cycle-4 [06-02 NEW HIGH FIX]: hard-violation filter in integrate_standard_layer EXTENDED with 'mismatch'/'1-to-1' tokens so the 'horse_race_id mismatch: entry/result are not 1-to-1' violation string at normalizer.py:330-334 (contains NEITHER 'duplicate' NOR 'orphan') is classified HARD and RAISES; new regression test test_horse_race_id_mismatch_raises (entry 1 row X, result 2 rows X → ValueError); (2) HIGH #6 cycle-4 [06-02 PARTIAL→RESOLVED]: test_integration_partial_swap_recoverable STRENGTHENED to monkeypatch os.replace to raise OSError on the 2nd call during the swap, assert inconsistent state OR raise, then RESTORE os.replace + re-invoke + assert byte-identical recovery — proves idempotent recovery under the REAL mid-swap failure (replaces the cycle-3 file-delete test); (3) HIGH #3 cycle-4 [06-03 NEW HIGH FIX]: source_stats + source_counts computed from UNIFIED inputs (Kaggle + scraped combined per table), NOT Kaggle-only — so validate_distributions/validate_null_rates compare identical data → within tolerance → overall_pass=True (was False at runtime in cycle 3); (4) HIGH #11 cycle-4 [06-03 PARTIAL→RESOLVED]: preflight gate changed from 20% tolerance to ZERO-TOLERANCE (`if len(invalid) > 0: sys.exit(1)`) — any invalid partition fails; (5) HIGH #14 cycle-4 [06-03 PARTIAL→RESOLVED]: EXPECTED_FLOOR strengthened from '2024-01-01' to '2026-01-01' reflecting CONTEXT D-07 LOCKED scope 2015-2026/5 (ROADMAP text update deferred to Phase 9). Test count 10→11 (adds test_horse_race_id_mismatch_raises; strengthens test_integration_partial_swap_recoverable)."
---

# Phase 06 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Revised under `--reviews` cycle 4 to address 06-REVIEWS.md cycle-3 residuals (2 NEW + 3 PARTIAL = 5 HIGHs).
> Cycle 4 = extra, user-approved convergence cycle beyond max-cycles=3.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x — already installed per CLAUDE.md and pyproject.toml |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]` — `testpaths=["tests"]` |
| **Quick run command** | `python -m pytest tests/pipeline/test_integration.py tests/pipeline/test_kaggle_converter.py -q` |
| **Full suite command** | `python -m pytest -q` |
| **Estimated runtime** | ~30 seconds (quick); ~60 seconds (full) |
| **Repo runtime** | setuptools (build-backend = setuptools.build_meta); `poetry` NOT installed — every command uses `python -m` / `python -c` / `keiba` entry point |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/pipeline/test_integration.py tests/pipeline/test_kaggle_converter.py -q` (~30s)
- **After every plan wave:** Run `python -m pytest -q` (~60s — all existing tests must still pass after Kaggle-side dtype + grade-detector changes)
- **Before `/gsd-verify-work`:** Full suite green + `pyarrow.parquet.read_schema` physical-type check on `data/standard/race.parquet` + odds/payoff SHA-256 snapshot/restore report
- **Max feedback latency:** ~30 seconds (quick) / ~60 seconds (full)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 06-01-T1 | 01 | 1 | DATA-05 | T-06-01 / T-06-01b | `(国際)` mapping removed; Kaggle-side grade detector wired via derive_race_flags called AFTER _UNMAPPED_RACE_FLAGS loop (HIGH #1 cycle-3); grade='G1' matches _GRADE_REGEX; race_condition=' ' bypasses early-return; OR-merge preserves True (WARNING-2) | unit + grep | `python -m pytest tests/pipeline/test_column_mapping.py tests/pipeline/test_kaggle_converter.py -q -k 'grade or column_mapping or preserves_existing_true or apply_grade_detection'` + grep gates | ✅ existing + 3 new tests | ⬜ pending |
| 06-01-T2 | 01 | 1 | DATA-05 | T-06-02 / T-06-03 / T-06-04 | `_recast_to_canonical` raises TypeError; regen race.parquet has zero Arrow-null cols; race_date=string (MEDIUM #5); convert(core_tables_subdir='kaggle') SKIPS odds/payoff writes entirely (HIGH #2 cycle-3 NON-OVERWRITE); _atomic_write_parquet reused; test_convert_skips_odds_payoff_when_subdir_set | unit + integration | `python -m pytest tests/pipeline/test_kaggle_converter.py -q` + pyarrow schema check + non-overwrite test + absence-of-odds/payoff-in-subdir check | ❌ W0 (6 new tests in test_kaggle_converter.py) | ⬜ pending |
| 06-01-T3 | 01 | 1 | DATA-05 | T-06-05 | 3-table-specific validation of regenerated kaggle/ subdir (schema column-set, Arrow dtype, grade-regex derivation count, validate_integrity on DataFrames — HIGH #1 follow-up). NO run_all_validations against kaggle/ subdir (HIGH #3 cycle-3 — that moved to 06-03-T2). | integration | `python -c "..."` 3-table checks (column-set, dtype, graded derivation, validate_integrity on DataFrames) + `python -m pytest tests/pipeline/test_validators.py -q` | ✅ existing (validators.py + normalizer.validate_integrity) | ⬜ pending |
| 06-02-T1 | 02 | 2 | DATA-05 | T-06-14 | 11 test stubs collected; 2 classes (TestIntegrationHermetic ungated + TestUnifiedCorpus gated — HIGH #7); tmp_kaggle_input_dir fixture exists (HIGH #5 separate input path); NEW cycle-4 stub test_horse_race_id_mismatch_raises (HIGH #8b) + cycle-4 strengthened stub test_integration_partial_swap_recoverable (HIGH #6 mid-swap injection) | unit (collection) | `python -m pytest tests/pipeline/test_integration.py --collect-only -q` lists 11 tests; `grep tmp_kaggle_input_dir tests/pipeline/conftest.py` | ❌ W0 (test_integration.py + conftest fixtures) | ⬜ pending |
| 06-02-T2 | 02 | 2 | DATA-05 | T-06-05 / T-06-06 / T-06-07 / T-06-08 / T-06-08b / T-06-09 / T-06-11 / T-06-12 / T-06-15 | integrate_standard_layer: reads from kaggle_input_dir (HIGH #5), **validate-before-swap via tempfile.mkdtemp + idempotent recovery (HIGH #6 cycle-3 + cycle-4 monkeypatch mid-swap test)**, **hard-violation filter including 'mismatch'/'1-to-1' (HIGH #8b cycle-4)**, column-set equality assert (HIGH #9), validate_integrity call (HIGH #8 FK), audit_leakage CALLED (MEDIUM #13), explicit missing-input errors (MEDIUM #14); NEW test_horse_race_id_mismatch_raises + cycle-4 strengthened test_integration_partial_swap_recoverable | unit + integration | `python -m pytest tests/pipeline/test_integration.py -q -k 'not unified_race_date_range and not row_counts_within_expected_bounds'` + grep gates (incl. tempfile.mkdtemp + idempotent + mismatch/1-to-1 + test_horse_race_id_mismatch_raises) | ❌ W0 (build integration.py) | ⬜ pending |
| 06-03-T1 | 03 | 3 | DATA-05 | T-06-11 / T-06-12 | Per-partition preflight: 3-file presence, **non-empty for ALL THREE via pyarrow metadata num_rows > 0 (HIGH #11 cycle-3 — no swallowing)**, race_date matches dir name; partition count >= 40; **cycle-4 ZERO-TOLERANCE gate — halt if ANY partition invalid (`if len(invalid) > 0: sys.exit(1)`), replacing the cycle-3 20% tolerance** (HIGH #15 gate preserved) | unit (filesystem) | `python -c "..."` per-partition pyarrow-metadata check; exit 1 if < 40 partitions OR ANY invalid (cycle-4 zero-tolerance) | ✅ (filesystem) | ⬜ pending |
| 06-03-T2 | 03 | 3 | DATA-05 | T-06-13 / T-06-15 / T-06-16 / T-06-17 / T-06-18 / T-06-19 | Real integration: success criteria #1/#2/#3; **FULL 8-point run_all_validations against unified ROOT with UNIFIED source_stats (HIGH #3 cycle-3 relocation + cycle-4 source_stats FIX — source_stats + source_counts computed from Kaggle+scraped combined per table, NOT Kaggle-only)**; odds/payoff SHA-256 in verify.automated (HIGH #17); per-period graded counts (HIGH #18); **robust date range with EXPECTED_FLOOR '2026-01-01' (HIGH #14 cycle-4 D-07 LOCKED scope 2015-2026/5 — ROADMAP text update deferred to Phase 9)** + per-year counts (HIGH #19); **PK-set union for ALL 3 tables (NEW HIGH cycle-3)**; scope=2015-2026/5 (MEDIUM #21) | integration (full suite) | `python -c "..."` snapshot/integrate/8-point-verify-with-UNIFIED-source_stats/assert + `python -m pytest tests/pipeline/test_integration.py -q` (11 tests incl. slow path) | ✅ (built in 06-02-T2) | ⬜ pending |
| 06-03-T3 | 03 | 3 | DATA-05 | T-06-20 | Human end-of-phase approval gate | human-verify | `python -m pytest tests/ -q` + pyarrow schema inspection + odds/payoff SHA-256 report | n/a (checkpoint) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Nyquist sampling continuity check:** every task has an automated `<verify>` (including the human checkpoint, which runs the full suite as its `<human-check>` precondition). No 3 consecutive tasks lack automated verify. Slow-path tests (date_range, row_counts) are gated by `_require_scraped_data` (on TestUnifiedCorpus only — HIGH #7) until D-06 completes; once cleared in Wave 3 they run automatically.

---

## Wave 0 Requirements

- [ ] `tests/pipeline/test_integration.py` — 11 DATA-05 tests across 2 classes (TestIntegrationHermetic: 9 ungated, incl. NEW cycle-4 test_horse_race_id_mismatch_raises + cycle-4 strengthened test_integration_partial_swap_recoverable with monkeypatch mid-swap injection; TestUnifiedCorpus: 2 gated). Stubbed in 06-02-T1, implemented in 06-02-T2.
- [ ] `tests/pipeline/test_kaggle_converter.py` — 6 new tests (test_kaggle_graded_derivation_matches_regex [HIGH #1 cycle-3, grade='G1'], test_grade_detection_preserves_existing_true [WARNING-2], test_apply_grade_detection_runs_after_unmapped_flags [HIGH #1 cycle-3 ordering guard], test_kaggle_parquet_post_d02_has_typed_flags, test_kaggle_race_date_is_string [MEDIUM #5], test_kaggle_race_distance_is_int64, test_recast_raises_on_bad_data, test_convert_preserves_odds_payoff [HIGH #2 cycle-3 NON-OVERWRITE], test_convert_writes_core_tables_to_subdir [BLOCKER-1], test_convert_skips_odds_payoff_when_subdir_set [HIGH #2 cycle-3 explicit SKIP]). File EXISTS; add to it in 06-01-T1/T2.
- [ ] `tests/pipeline/conftest.py` — extend with `tmp_kaggle_input_dir` (HIGH #5) and `tmp_scraped_partitions_dir`. File EXISTS; add fixtures in 06-02-T1.
- [ ] `src/pipeline/integration.py` — built in 06-02-T2 (Wave-2 implementation; tempfile.mkdtemp validate-before-swap + idempotent recovery + cycle-4 hard-violation filter with 'mismatch'/'1-to-1').
- [ ] `pytest` framework — already installed (no install needed).

*Framework already configured; only new test files + fixtures needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Phase 6 corpus inspection (row counts, date range, schema report, per-period graded counts, EXPECTED_FLOOR='2026-01-01' + D-07 rationale + actual_scraped_max, UNIFIED source_stats, PK-set union for all 3 tables, odds/payoff SHA-256, run_all_validations per-check) — end-of-phase sign-off | DATA-05 | Per `workflow.human_verify_mode=end-of-phase`, the user must confirm the unified corpus matches the ROADMAP success criteria before the phase closes | 06-03-T3 checkpoint: review 06-03-SUMMARY.md verification report; run `python -m pytest tests/ -q`; inspect `pyarrow.parquet.read_schema('data/standard/race.parquet')`; confirm odds/payoff SHA-256 unchanged; confirm EXPECTED_FLOOR + PK-set union for all 3 tables |

---

## Cross-AI Review Concern Coverage (06-REVIEWS.md cycle 3 + cycle 4 patches)

| HIGH # | Concern | Cycle 3 Verdict | Cycle 4 Resolution Location |
|--------|---------|-----------------|------------------------------|
| #1 | D-01 GRADE_REGEX gap | RESOLVED (cycle 3) | 06-01-T1 (KEPT) |
| #2 | convert() overwrites odds/payoff | RESOLVED (cycle 3) | 06-01-T2 (KEPT) |
| #3 | 8-point verification — source_stats | PARTIALLY RESOLVED | **06-03-T2 (cycle-4 FIX): source_stats + source_counts computed from UNIFIED inputs (Kaggle + scraped combined per table), NOT Kaggle-only — so validate_distributions/validate_null_rates compare identical data → within tolerance → overall_pass=True** |
| #4 | poetry run commands fail | RESOLVED (cycle 2) | ALL plans (KEPT) |
| #5 | Non-idempotent integration | RESOLVED (cycle 2) | 06-02-T2 (KEPT) |
| #6 | No corpus-level transactionality — test injection | PARTIALLY RESOLVED | **06-02-T2 (cycle-4 FIX): test_integration_partial_swap_recoverable STRENGTHENED to monkeypatch os.replace to raise OSError on 2nd call, assert inconsistent state OR raise, then RESTORE + re-invoke + byte-identical recovery — proves idempotent recovery under the REAL mid-swap failure** |
| #7 | autouse skip swallows hermetic | RESOLVED (cycle 2) | 06-02-T1 (KEPT) |
| #8 | FK test is a no-op | RESOLVED (cycle 2) | 06-02-T2 (KEPT) |
| #8b (cycle 4 NEW) | horse_race_id 1-to-1 mismatch treated as SOFT | NEW HIGH (cycle 3) | **06-02-T2 (cycle-4 FIX): hard-violation filter EXTENDED with 'mismatch'/'1-to-1' tokens; regression test test_horse_race_id_mismatch_raises (entry 1 row X, result 2 rows X → ValueError)** |
| #9 | reindex masks schema drift | RESOLVED (cycle 2) | 06-02-T2 (KEPT) |
| #10/#15 | D-06 pre-task not done | RESOLVED (cycle 2) | 06-03-T1 (KEPT) |
| #11/#16 | Month-count gate — 20% tolerance | PARTIALLY RESOLVED | **06-03-T1 (cycle-4 FIX): preflight gate changed to ZERO-TOLERANCE (`if len(invalid) > 0: sys.exit(1)`) — any invalid partition fails** |
| #12/#17 | odds/payoff snapshot not in verify | RESOLVED (cycle 2) | 06-03-T2 (KEPT) |
| #13/#18 | graded 780-880 post-integration wrong | RESOLVED (cycle 2) | 06-03-T2 (KEPT) |
| #14/#19 | Date-range check too weak — EXPECTED_FLOOR | PARTIALLY RESOLVED | **06-03-T2 (cycle-4 FIX): EXPECTED_FLOOR strengthened from '2024-01-01' to '2026-01-01' reflecting CONTEXT D-07 LOCKED scope 2015-2026/5 (ROADMAP text update deferred to Phase 9)** |
| NEW HIGH (cycle 2) | PK-set union verify race-only | RESOLVED (cycle 3) | 06-03-T2 (KEPT) |

MEDIUMs: race_date dtype (string, not datetime) — 06-01-T2; test count 11 (cycle-4 adds test_horse_race_id_mismatch_raises; strengthens test_integration_partial_swap_recoverable) — 06-02-T1; audit_leakage called — 06-02-T2; explicit missing-input errors — 06-02-T2; PK-set union per table — 06-03-T2; scope 2015-2026/5 per D-07 — 06-03-T2.

---

## Task Migration Log (cycle 3 + cycle 4)

- **run_all_validations MOVED from 06-01-T3 to 06-03-T2 (HIGH #3 cycle-3).** Rationale: run_all_validations iterates 5 tables and validate_referential_integrity appends "Missing odds_trifecta/payoff.parquet" when those files are absent (validators.py:377-383), forcing overall_pass=False against the 3-table kaggle/ subdir. The natural validation point is the unified ROOT in 06-03-T2 where all 5 tables coexist. 06-01-T3 now does 3-table-specific validation (schema column-set, Arrow dtype, grade derivation, validate_integrity on DataFrames) — no run_all_validations call.
- **test_integration_partial_swap_recoverable ADDED (HIGH #6 cycle-3).** Test count 9 → 10. Documents the idempotent recovery model.
- **test_integration_partial_swap_recoverable STRENGTHENED (HIGH #6 cycle-4).** Now monkeypatches os.replace to raise OSError on the 2nd call, asserts the integration surfaces/raises OR leaves an inconsistent state, then RESTORES os.replace and re-invokes — proves idempotent recovery under the REAL mid-swap failure (replaces the cycle-3 file-delete test).
- **test_horse_race_id_mismatch_raises ADDED (HIGH #8b cycle-4 NEW HIGH FIX).** Test count 10 → 11. Injects entry/result horse_race_id cardinality mismatch (entry 1 row "X", result 2 rows "X") and asserts integrate_standard_layer RAISES ValueError. The hard-violation filter in integration.py is EXTENDED with 'mismatch'/'1-to-1' tokens to match the 'horse_race_id mismatch: entry/result are not 1-to-1' violation string at normalizer.py:330-334 (contains NEITHER 'duplicate' NOR 'orphan').

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (test_integration.py + conftest fixtures created in 06-02-T1; 6+ new tests in test_kaggle_converter.py in 06-01-T1/T2)
- [x] No watch-mode flags
- [x] Feedback latency < 60s (quick ~30s, full ~60s)
- [x] `nyquist_compliant: true` set in frontmatter
- [x] Every command uses `python -m` / `python -c` / `keiba` — ZERO `poetry run` (HIGH #4)
- [x] Task migration logged (run_all_validations 06-01-T3 → 06-03-T2; test count 9 → 10 → 11 across cycle 3 + cycle 4)

**Approval:** ready 2026-06-14 (revised under --reviews cycle 4 — extra user-approved convergence cycle)
