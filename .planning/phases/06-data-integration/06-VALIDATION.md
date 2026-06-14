---
phase: 06
slug: data-integration
status: ready
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-14
---

# Phase 06 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x — already installed per CLAUDE.md and pyproject.toml |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]` — `testpaths=["tests"]` |
| **Quick run command** | `poetry run pytest tests/pipeline/test_integration.py tests/pipeline/test_kaggle_converter.py -q` |
| **Full suite command** | `poetry run pytest -q` |
| **Estimated runtime** | ~30 seconds (quick); ~60 seconds (full) |

---

## Sampling Rate

- **After every task commit:** Run `poetry run pytest tests/pipeline/test_integration.py tests/pipeline/test_kaggle_converter.py -q` (~30s)
- **After every plan wave:** Run `poetry run pytest -q` (~60s — all existing tests must still pass after Kaggle-side dtype changes)
- **Before `/gsd-verify-work`:** Full suite must be green + `pyarrow.parquet.read_schema` physical-type check on `data/standard/race.parquet`
- **Max feedback latency:** ~30 seconds (quick) / ~60 seconds (full)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 06-01-T1 | 01 | 1 | DATA-05 | T-06-01 / T-06-04 | `(国際)` mapping removed from KAGGLE_COLUMN_MAP but FLAG_COLUMNS entry preserved (no orphan column) | unit + grep | `pytest tests/pipeline/test_column_mapping.py -q && grep -c '"レース記号/(国際)": ("race", "race_flag_graded_stakes")' src/pipeline/column_mapping.py == 0 && grep -c 'レース記号/(国際)' src/pipeline/column_mapping.py >= 1` | ✅ existing (test_column_mapping) | ⬜ pending |
| 06-01-T2 | 01 | 1 | DATA-05 | T-06-02 | `_recast_to_canonical` raises TypeError on uncoercible values; NEVER uses `errors='ignore'`; regen race.parquet has zero Arrow-null columns | unit + integration | `pytest tests/pipeline/test_kaggle_converter.py -q && pyarrow.parquet.read_schema('data/standard/race.parquet') has 0 cols with str(type)=='null'` | ❌ W0 (3 new tests in test_kaggle_converter.py) | ⬜ pending |
| 06-01-T3 | 01 | 1 | DATA-05 | T-06-01 | Phase 2 D-05 8-point validators green on regenerated Parquet; graded_stakes count in 780-880 range | integration | `poetry run python -c "from src.pipeline.validators import run_all_validations; ..."` + graded_stakes count assertion | ✅ existing (validators.py) | ⬜ pending |
| 06-02-T1 | 02 | 2 | DATA-05 | T-06-09 / T-06-10 | Wave-0 stubs collect without import errors; conftest has hermetic fixtures | unit (collection) | `pytest tests/pipeline/test_integration.py --collect-only -q` lists 8 tests | ❌ W0 (test_integration.py + conftest fixtures) | ⬜ pending |
| 06-02-T2 | 02 | 2 | DATA-05 | T-06-05 / T-06-06 / T-06-07 / T-06-08 / T-06-10 | integrate_standard_layer FAIL-LOUD on duplicate PK; no `errors='ignore'`; no `source` column; no odds_trifecta/payoff in module; atomic write reused | unit + integration | `pytest tests/pipeline/test_integration.py -q -k 'not unified_race_date_range and not row_counts_within_expected_bounds'` | ❌ W0 (build integration.py) | ⬜ pending |
| 06-03-T1 | 03 | 3 | DATA-05 | T-06-11 | D-06 pre-task status check (smoke-only HALTs) | unit (ls + grep) | `ls data/standard/scraped/ | wc -l` | ✅ (filesystem) | ⬜ pending |
| 06-03-T2 | 03 | 3 | DATA-05 | T-06-12 / T-06-13 / T-06-14 | Real integration: success criteria #1 (no dups), #2 (schema identical), #3 (date range); odds/payoff preserved | integration (full suite) | `pytest tests/pipeline/test_integration.py -q` (8 tests incl. slow path) + `pytest tests/ -q` | ✅ (built in 06-02-T2) | ⬜ pending |
| 06-03-T3 | 03 | 3 | DATA-05 | T-06-15 | Human end-of-phase approval gate | human-verify | `pytest tests/ -q` + pyarrow schema inspection | n/a (checkpoint) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Nyquist sampling continuity check:** every task has an automated `<verify>` (including the human checkpoint, which runs the full suite as its `<human-check>` precondition). No 3 consecutive tasks lack automated verify. Slow-path tests (date_range, row_counts) are gated by `_require_scraped_data` until D-06 completes; once cleared in Wave 3 they run automatically.

---

## Wave 0 Requirements

- [ ] `tests/pipeline/test_integration.py` — 8 DATA-05 tests (stubbed in 06-02-T1, implemented in 06-02-T2). File does NOT exist yet.
- [ ] `tests/pipeline/test_kaggle_converter.py` — 3 new tests (test_kaggle_parquet_post_d02_has_typed_flags, test_kaggle_race_distance_is_int64, test_kaggle_recast_raises_on_bad_data). File EXISTS; add to it in 06-01-T2.
- [ ] `tests/pipeline/conftest.py` — extend with `tmp_scraped_partitions_dir` and a Kaggle-side synthetic-file fixture. File EXISTS; add fixtures in 06-02-T1.
- [ ] `src/pipeline/integration.py` — built in 06-02-T2 (not Wave 0 — this is a Wave-2 implementation task, but its tests are the Wave 0 deliverable that gates execution).
- [ ] `pytest` framework — already installed per CLAUDE.md stack (no install needed).

*Framework already configured; only new test files + fixtures needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Phase 6 corpus inspection (row counts, date range, schema report) — end-of-phase sign-off | DATA-05 | Per `workflow.human_verify_mode=end-of-phase`, the user must confirm the unified corpus matches the ROADMAP success criteria before the phase closes | 06-03-T3 checkpoint: review 06-03-SUMMARY.md verification report; run `poetry run pytest tests/ -q`; inspect `pyarrow.parquet.read_schema('data/standard/race.parquet')`; confirm odds/payoff row counts unchanged |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (every task has automated verify)
- [x] Wave 0 covers all MISSING references (test_integration.py + conftest fixtures created in 06-02-T1)
- [x] No watch-mode flags
- [x] Feedback latency < 60s (quick ~30s, full ~60s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** ready 2026-06-14
