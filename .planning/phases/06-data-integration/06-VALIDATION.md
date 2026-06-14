---
phase: 06
slug: data-integration
status: ready
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-14
revised: 2026-06-14
revision_note: "Cycle-3 — resolve 7 remaining cycle-2 HIGHs. Key changes: (1) convert(core_tables_subdir='kaggle') SKIPS odds/payoff writes entirely (HIGH #2 cycle-3 NON-OVERWRITE); (2) _apply_grade_detection moved AFTER _UNMAPPED_RACE_FLAGS loop (HIGH #1 cycle-3, no KeyError/clobber); grade='G1' test value matches _GRADE_REGEX; race_condition=' ' bypasses early-return; (3) 8-point run_all_validations MOVED from 06-01-T3 to 06-03-T2 (runs against unified root where all 5 tables coexist — HIGH #3 cycle-3); 06-01-T3 does 3-table-specific validation; (4) validate-before-swap via tempfile.mkdtemp + idempotent recovery model (HIGH #6 cycle-3); (5) preflight asserts all 3 files non-empty via pyarrow metadata (HIGH #11 cycle-3); (6) date assert adds EXPECTED_FLOOR '2024-01-01' (HIGH #14 cycle-3); (7) PK-set union extended to entry + result (NEW HIGH cycle-3). Test count 9->10 (adds test_integration_partial_swap_recoverable)."
---

# Phase 06 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Revised under `--reviews` (cycle 3) to address 06-REVIEWS.md (7 remaining cycle-2 HIGHs).

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
| 06-01-T3 | 01 | 1 | DATA-05 | T-06-05 | **CHANGED (cycle-3):** 3-table-specific validation of regenerated kaggle/ subdir (schema column-set, Arrow dtype, grade-regex derivation count, validate_integrity on DataFrames — HIGH #1 follow-up). NO run_all_validations against kaggle/ subdir (HIGH #3 cycle-3 — that moved to 06-03-T2). | integration | `python -c "..."` 3-table checks (column-set, dtype, graded derivation, validate_integrity on DataFrames) + `python -m pytest tests/pipeline/test_validators.py -q` | ✅ existing (validators.py + normalizer.validate_integrity) | ⬜ pending |
| 06-02-T1 | 02 | 2 | DATA-05 | T-06-14 | 10 test stubs collected; 2 classes (TestIntegrationHermetic ungated + TestUnifiedCorpus gated — HIGH #7); tmp_kaggle_input_dir fixture exists (HIGH #5 separate input path) | unit (collection) | `python -m pytest tests/pipeline/test_integration.py --collect-only -q` lists 10 tests; `grep tmp_kaggle_input_dir tests/pipeline/conftest.py` | ❌ W0 (test_integration.py + conftest fixtures) | ⬜ pending |
| 06-02-T2 | 02 | 2 | DATA-05 | T-06-05 / T-06-06 / T-06-07 / T-06-08 / T-06-09 / T-06-11 / T-06-12 / T-06-15 | integrate_standard_layer: reads from kaggle_input_dir (HIGH #5), **validate-before-swap via tempfile.mkdtemp + idempotent recovery (HIGH #6 cycle-3)**, column-set equality assert (HIGH #9), validate_integrity call (HIGH #8 FK), audit_leakage CALLED (MEDIUM #13), explicit missing-input errors (MEDIUM #14); new test_integration_partial_swap_recoverable | unit + integration | `python -m pytest tests/pipeline/test_integration.py -q -k 'not unified_race_date_range and not row_counts_within_expected_bounds'` + grep gates (incl. tempfile.mkdtemp + idempotent) | ❌ W0 (build integration.py) | ⬜ pending |
| 06-03-T1 | 03 | 3 | DATA-05 | T-06-11 / T-06-12 | Per-partition preflight: 3-file presence, **non-empty for ALL THREE via pyarrow metadata num_rows > 0 (HIGH #11 cycle-3 — no swallowing)**, race_date matches dir name; partition count >= 40; halt on smoke-only or > 20% invalid (HIGH #15 gate preserved) | unit (filesystem) | `python -c "..."` per-partition pyarrow-metadata check; exit 1 if < 40 partitions OR > 20% invalid | ✅ (filesystem) | ⬜ pending |
| 06-03-T2 | 03 | 3 | DATA-05 | T-06-13 / T-06-15 / T-06-16 / T-06-17 / T-06-18 / T-06-19 | Real integration: success criteria #1/#2/#3; **FULL 8-point run_all_validations against unified ROOT (HIGH #3 cycle-3 relocation — 5 tables present, source_counts + source_stats supplied)**; odds/payoff SHA-256 in verify.automated (HIGH #17); per-period graded counts (HIGH #18); **robust date range with EXPECTED_FLOOR '2024-01-01' (HIGH #14 cycle-3)** + per-year counts (HIGH #19); **PK-set union for ALL 3 tables (NEW HIGH cycle-3)**; scope=2015-2026/5 (MEDIUM #21) | integration (full suite) | `python -c "..."` snapshot/integrate/8-point-verify/assert + `python -m pytest tests/pipeline/test_integration.py -q` (10 tests incl. slow path) | ✅ (built in 06-02-T2) | ⬜ pending |
| 06-03-T3 | 03 | 3 | DATA-05 | T-06-20 | Human end-of-phase approval gate | human-verify | `python -m pytest tests/ -q` + pyarrow schema inspection + odds/payoff SHA-256 report | n/a (checkpoint) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Nyquist sampling continuity check:** every task has an automated `<verify>` (including the human checkpoint, which runs the full suite as its `<human-check>` precondition). No 3 consecutive tasks lack automated verify. Slow-path tests (date_range, row_counts) are gated by `_require_scraped_data` (on TestUnifiedCorpus only — HIGH #7) until D-06 completes; once cleared in Wave 3 they run automatically.

---

## Wave 0 Requirements

- [ ] `tests/pipeline/test_integration.py` — 10 DATA-05 tests across 2 classes (TestIntegrationHermetic: 8 ungated, incl. new test_integration_partial_swap_recoverable; TestUnifiedCorpus: 2 gated). Stubbed in 06-02-T1, implemented in 06-02-T2.
- [ ] `tests/pipeline/test_kaggle_converter.py` — 6 new tests (test_kaggle_graded_derivation_matches_regex [HIGH #1 cycle-3, grade='G1'], test_grade_detection_preserves_existing_true [WARNING-2], test_apply_grade_detection_runs_after_unmapped_flags [HIGH #1 cycle-3 ordering guard], test_kaggle_parquet_post_d02_has_typed_flags, test_kaggle_race_date_is_string [MEDIUM #5], test_kaggle_race_distance_is_int64, test_recast_raises_on_bad_data, test_convert_preserves_odds_payoff [HIGH #2 cycle-3 NON-OVERWRITE], test_convert_writes_core_tables_to_subdir [BLOCKER-1], test_convert_skips_odds_payoff_when_subdir_set [HIGH #2 cycle-3 explicit SKIP]). File EXISTS; add to it in 06-01-T1/T2.
- [ ] `tests/pipeline/conftest.py` — extend with `tmp_kaggle_input_dir` (HIGH #5) and `tmp_scraped_partitions_dir`. File EXISTS; add fixtures in 06-02-T1.
- [ ] `src/pipeline/integration.py` — built in 06-02-T2 (Wave-2 implementation; tempfile.mkdtemp validate-before-swap + idempotent recovery).
- [ ] `pytest` framework — already installed (no install needed).

*Framework already configured; only new test files + fixtures needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Phase 6 corpus inspection (row counts, date range, schema report, per-period graded counts, EXPECTED_FLOOR + actual_scraped_max, PK-set union for all 3 tables, odds/payoff SHA-256, run_all_validations per-check) — end-of-phase sign-off | DATA-05 | Per `workflow.human_verify_mode=end-of-phase`, the user must confirm the unified corpus matches the ROADMAP success criteria before the phase closes | 06-03-T3 checkpoint: review 06-03-SUMMARY.md verification report; run `python -m pytest tests/ -q`; inspect `pyarrow.parquet.read_schema('data/standard/race.parquet')`; confirm odds/payoff SHA-256 unchanged; confirm EXPECTED_FLOOR + PK-set union for all 3 tables |

---

## Cross-AI Review Concern Coverage (06-REVIEWS.md cycle 3)

| HIGH # | Concern | Cycle 2 Verdict | Cycle 3 Resolution Location |
|--------|---------|-----------------|-----------------------------|
| #1 | D-01 GRADE_REGEX gap | NOT RESOLVED | **06-01-T1 (cycle-3): _apply_grade_detection AFTER _UNMAPPED_RACE_FLAGS loop; grade='G1'; race_condition=' '** |
| #2 | convert() overwrites odds/payoff | NOT RESOLVED | **06-01-T2 (cycle-3): convert(core_tables_subdir='kaggle') SKIPS odds/payoff writes entirely; non-overwrite test** |
| #3 | 8-point verification skips 3-4 | PARTIALLY RESOLVED | **06-01-T3 (cycle-3): removed run_all_validations; does 3-table-specific validation. 06-03-T2 (cycle-3): full 8-point run_all_validations against unified root (5 tables present)** |
| #4 | poetry run commands fail | RESOLVED (cycle 2) | ALL plans — every command is `python -m` / `python -c` (KEPT) |
| #5 | Non-idempotent integration | RESOLVED (cycle 2) | 06-02-T2 (KEPT) |
| #6 | No corpus-level transactionality | PARTIALLY RESOLVED | **06-02-T2 (cycle-3): validate-before-swap via tempfile.mkdtemp + idempotent recovery model; test_integration_partial_swap_recoverable** |
| #7 | autouse skip swallows hermetic | RESOLVED (cycle 2) | 06-02-T1 (KEPT) |
| #8 | FK test is a no-op | RESOLVED (cycle 2) | 06-02-T2 (KEPT) |
| #9 | reindex masks schema drift | RESOLVED (cycle 2) | 06-02-T2 (KEPT) |
| #10/#15 | D-06 pre-task not done | RESOLVED (cycle 2) | 06-03-T1 (KEPT) |
| #11/#16 | Month-count gate weak | NOT RESOLVED | **06-03-T1 (cycle-3): pyarrow metadata num_rows > 0 for ALL THREE files; exceptions re-raised** |
| #12/#17 | odds/payoff snapshot not in verify | RESOLVED (cycle 2) | 06-03-T2 (KEPT) |
| #13/#18 | graded 780-880 post-integration wrong | RESOLVED (cycle 2) | 06-03-T2 (KEPT) |
| #14/#19 | Date-range check too weak | PARTIALLY RESOLVED | **06-03-T2 (cycle-3): dmax == actual_scraped_max AND actual_scraped_max >= '2024-01-01' (EXPECTED_FLOOR)** |
| NEW HIGH (cycle 2) | PK-set union verify race-only | NOT RESOLVED | **06-03-T2 (cycle-3): PK-set union extended to entry + result** |

MEDIUMs: race_date dtype (string, not datetime) — 06-01-T2; test count 10 (adds test_integration_partial_swap_recoverable) — 06-02-T1; audit_leakage called — 06-02-T2; explicit missing-input errors — 06-02-T2; PK-set union per table — 06-03-T2; scope 2015-2026/5 per D-07 — 06-03-T2.

---

## Task Migration Log (cycle 3)

- **run_all_validations MOVED from 06-01-T3 to 06-03-T2 (HIGH #3 cycle-3).** Rationale: run_all_validations iterates 5 tables and validate_referential_integrity appends "Missing odds_trifecta/payoff.parquet" when those files are absent (validators.py:377-383), forcing overall_pass=False against the 3-table kaggle/ subdir. The natural validation point is the unified ROOT in 06-03-T2 where all 5 tables coexist. 06-01-T3 now does 3-table-specific validation (schema column-set, Arrow dtype, grade derivation, validate_integrity on DataFrames) — no run_all_validations call.
- **test_integration_partial_swap_recoverable ADDED (HIGH #6 cycle-3).** Test count 9 → 10. Documents the idempotent recovery model: simulate partial swap by deleting one output file, re-invoke integrate_standard_layer, assert all 3 outputs restored to canonical content.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (test_integration.py + conftest fixtures created in 06-02-T1; 6+ new tests in test_kaggle_converter.py in 06-01-T1/T2)
- [x] No watch-mode flags
- [x] Feedback latency < 60s (quick ~30s, full ~60s)
- [x] `nyquist_compliant: true` set in frontmatter
- [x] Every command uses `python -m` / `python -c` / `keiba` — ZERO `poetry run` (HIGH #4)
- [x] Task migration logged (run_all_validations 06-01-T3 → 06-03-T2; test count 9 → 10)

**Approval:** ready 2026-06-14 (revised under --reviews cycle 3)
