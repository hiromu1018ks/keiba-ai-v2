---
phase: 06
slug: data-integration
status: ready
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-14
revised: 2026-06-14
revision_note: "Cycle-2 — address 14 HIGH cross-AI review concerns. Test count 8->9, add per-partition preflight (06-03-T1), odds/payoff SHA-256 in verify.automated (06-03-T2), per-period graded counts (06-03-T2), python -m (no poetry)."
---

# Phase 06 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Revised under `--reviews` to address 06-REVIEWS.md (14 HIGH concerns).

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
| 06-01-T1 | 01 | 1 | DATA-05 | T-06-01 | `(国際)` mapping removed from KAGGLE_COLUMN_MAP; FLAG_COLUMNS preserved; Kaggle-side grade detector wired via derive_race_flags (HIGH #1) | unit + grep | `python -m pytest tests/pipeline/test_column_mapping.py tests/pipeline/test_kaggle_converter.py -q -k 'grade or column_mapping'` + grep gates | ✅ existing (test_column_mapping, test_kaggle_converter) + 1 new test | ⬜ pending |
| 06-01-T2 | 01 | 1 | DATA-05 | T-06-02 / T-06-04 | `_recast_to_canonical` raises TypeError (no errors='ignore'); regen race.parquet has zero Arrow-null cols; race_date=string (MEDIUM #5); odds/payoff snapshot-protected (HIGH #2); _atomic_write_parquet reused | unit + integration | `python -m pytest tests/pipeline/test_kaggle_converter.py -q` + pyarrow schema check + odds/payoff preservation test | ❌ W0 (5 new tests in test_kaggle_converter.py) | ⬜ pending |
| 06-01-T3 | 01 | 1 | DATA-05 | T-06-05 | All 8 D-05 checks actually RUN (source_counts + source_stats supplied — HIGH #3); graded count == grade-regex derivation (deterministic, no fixed band — HIGH #1) | integration | `python -c "from src.pipeline.validators import run_all_validations; ... source_counts=... source_stats=..."` + graded derivation equality | ✅ existing (validators.py) | ⬜ pending |
| 06-02-T1 | 02 | 2 | DATA-05 | T-06-14 | 9 test stubs collected; 2 classes (TestIntegrationHermetic ungated + TestUnifiedCorpus gated — HIGH #7); tmp_kaggle_input_dir fixture exists (HIGH #5 separate input path) | unit (collection) | `python -m pytest tests/pipeline/test_integration.py --collect-only -q` lists 9 tests; `grep tmp_kaggle_input_dir tests/pipeline/conftest.py` | ❌ W0 (test_integration.py + conftest fixtures) | ⬜ pending |
| 06-02-T2 | 02 | 2 | DATA-05 | T-06-05 / T-06-06 / T-06-07 / T-06-08 / T-06-09 / T-06-11 / T-06-12 | integrate_standard_layer: reads from kaggle_input_dir (HIGH #5 idempotency), tmp-swap transactionality (HIGH #6), column-set equality assert (HIGH #9), validate_integrity call (HIGH #8 FK), audit_leakage CALLED (MEDIUM #13), explicit missing-input errors (MEDIUM #14) | unit + integration | `python -m pytest tests/pipeline/test_integration.py -q -k 'not unified_race_date_range and not row_counts_within_expected_bounds'` + grep gates | ❌ W0 (build integration.py) | ⬜ pending |
| 06-03-T1 | 03 | 3 | DATA-05 | T-06-11 / T-06-12 | Per-partition preflight: 3-file presence, non-empty, race_date matches dir name (HIGH #16); halt on smoke-only or > 20% invalid (HIGH #15 gate preserved) | unit (filesystem) | `python -c "..."` per-partition check; exit 1 if < 40 valid partitions OR > 20% invalid | ✅ (filesystem) | ⬜ pending |
| 06-03-T2 | 03 | 3 | DATA-05 | T-06-13 / T-06-15 / T-06-16 / T-06-17 / T-06-18 | Real integration: success criteria #1/#2/#3; odds/payoff SHA-256 in verify.automated (HIGH #17); per-period graded counts (HIGH #18); robust date range + per-year counts (HIGH #19); PK-set union (MEDIUM #20); scope=2015-2026/5 (MEDIUM #21) | integration (full suite) | `python -c "..."` snapshot/integrate/assert + `python -m pytest tests/pipeline/test_integration.py -q` (9 tests incl. slow path) | ✅ (built in 06-02-T2) | ⬜ pending |
| 06-03-T3 | 03 | 3 | DATA-05 | T-06-19 | Human end-of-phase approval gate | human-verify | `python -m pytest tests/ -q` + pyarrow schema inspection + odds/payoff SHA-256 report | n/a (checkpoint) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Nyquist sampling continuity check:** every task has an automated `<verify>` (including the human checkpoint, which runs the full suite as its `<human-check>` precondition). No 3 consecutive tasks lack automated verify. Slow-path tests (date_range, row_counts) are gated by `_require_scraped_data` (on TestUnifiedCorpus only — HIGH #7) until D-06 completes; once cleared in Wave 3 they run automatically.

---

## Wave 0 Requirements

- [ ] `tests/pipeline/test_integration.py` — 9 DATA-05 tests across 2 classes (TestIntegrationHermetic: 7 ungated; TestUnifiedCorpus: 2 gated). Stubbed in 06-02-T1, implemented in 06-02-T2.
- [ ] `tests/pipeline/test_kaggle_converter.py` — 5 new tests (test_kaggle_graded_derivation_matches_regex [HIGH #1], test_kaggle_parquet_post_d02_has_typed_flags, test_kaggle_race_date_is_string [MEDIUM #5], test_kaggle_race_distance_is_int64, test_recast_raises_on_bad_data, test_convert_preserves_odds_payoff [HIGH #2]). File EXISTS; add to it in 06-01-T1/T2.
- [ ] `tests/pipeline/conftest.py` — extend with `tmp_kaggle_input_dir` (HIGH #5 separate input path) and `tmp_scraped_partitions_dir`. File EXISTS; add fixtures in 06-02-T1.
- [ ] `src/pipeline/integration.py` — built in 06-02-T2 (Wave-2 implementation; its tests are the Wave 0 deliverable that gates execution).
- [ ] `pytest` framework — already installed (no install needed).

*Framework already configured; only new test files + fixtures needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Phase 6 corpus inspection (row counts, date range, schema report, per-period graded counts, odds/payoff SHA-256) — end-of-phase sign-off | DATA-05 | Per `workflow.human_verify_mode=end-of-phase`, the user must confirm the unified corpus matches the ROADMAP success criteria before the phase closes | 06-03-T3 checkpoint: review 06-03-SUMMARY.md verification report; run `python -m pytest tests/ -q`; inspect `pyarrow.parquet.read_schema('data/standard/race.parquet')`; confirm odds/payoff SHA-256 unchanged |

---

## Cross-AI Review Concern Coverage (06-REVIEWS.md)

| HIGH # | Concern | Resolution Location |
|--------|---------|---------------------|
| #1 | D-01 GRADE_REGEX gap | 06-01-T1 (derive_race_flags wired on Kaggle side); 06-01-T3 (deterministic count check) |
| #2 | D-05 violation via convert() | 06-01-T2 (snapshot/restore odds/payoff + test_convert_preserves_odds_payoff) |
| #3 | 8-point verification skips 3-4 | 06-01-T3 (source_counts + source_stats supplied) |
| #4 | poetry run commands fail | ALL plans — every command is `python -m` / `python -c` |
| #5 | Non-idempotent integration | 06-02-T2 (kaggle_input_dir separate path) + test_integration_is_idempotent |
| #6 | No corpus-level transactionality | 06-02-T2 (tmp-swap via os.replace) |
| #7 | autouse skip swallows hermetic tests | 06-02-T1 (TestIntegrationHermetic ungated + TestUnifiedCorpus gated) |
| #8 | FK test is a no-op | 06-02-T2 (validate_integrity called; orphan-injection test) |
| #9 | reindex masks schema drift | 06-02-T2 (_assert_column_set_equality before reindex) |
| #10 (15) | D-06 pre-task not done | 06-03-T1 (halt-on-smoke-only gate preserved + documented prerequisite) |
| #11 (16) | Month-count gate weak | 06-03-T1 (per-partition 3-file/non-empty/date preflight) |
| #12 (17) | odds/payoff snapshot not in verify | 06-03-T2 (SHA-256 + row count in actual verify.automated) |
| #13 (18) | graded 780-880 post-integration wrong | 06-03-T2 (per-period graded counts, no fixed band) |
| #14 (19) | Date-range check too weak | 06-03-T2 (min/max racedays + per-year counts) |

MEDIUMs: race_date dtype (string, not datetime) — 06-01-T2; test count 9 — 06-02-T1; audit_leakage called — 06-02-T2; explicit missing-input errors — 06-02-T2; PK-set union — 06-03-T2; scope 2015-2026/5 per D-07 — 06-03-T2.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (every task has automated verify)
- [x] Wave 0 covers all MISSING references (test_integration.py + conftest fixtures created in 06-02-T1; 5 new tests in test_kaggle_converter.py in 06-01-T1/T2)
- [x] No watch-mode flags
- [x] Feedback latency < 60s (quick ~30s, full ~60s)
- [x] `nyquist_compliant: true` set in frontmatter
- [x] Every command uses `python -m` / `python -c` / `keiba` — ZERO `poetry run` (HIGH #4)

**Approval:** ready 2026-06-14 (revised under --reviews)
