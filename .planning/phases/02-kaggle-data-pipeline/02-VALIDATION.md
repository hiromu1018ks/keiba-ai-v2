---
phase: 02
slug: kaggle-data-pipeline
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-11
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.x |
| **Config file** | `pyproject.toml` ([tool.pytest.ini_options]) |
| **Quick run command** | `pytest tests/pipeline/ -x -q` |
| **Full suite command** | `pytest tests/ -x -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/pipeline/ -x -q`
- **After every plan wave:** Run `pytest tests/ -x -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | DATA-02 | — | N/A | unit | `pytest tests/pipeline/test_column_mapping.py -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | DATA-02 | — | N/A | unit | `pytest tests/pipeline/test_kaggle_converter.py::test_date_filter -x` | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 1 | DATA-02 | — | N/A | unit | `pytest tests/pipeline/test_kaggle_converter.py::test_obstacle_exclusion -x` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 2 | DATA-02 | T-02-01 | pathlib.Path for output paths | integration | `pytest tests/pipeline/test_kaggle_converter.py::test_race_entry_result_split -x` | ❌ W0 | ⬜ pending |
| 02-02-02 | 02 | 2 | DATA-02 | — | N/A | unit | `pytest tests/pipeline/test_kaggle_converter.py::test_flag_conversion -x` | ❌ W0 | ⬜ pending |
| 02-02-03 | 02 | 2 | DATA-02 | — | N/A | unit | `pytest tests/pipeline/test_kaggle_converter.py::test_finish_notes -x` | ❌ W0 | ⬜ pending |
| 02-03-01 | 03 | 3 | DATA-02 | — | N/A | integration | `pytest tests/pipeline/test_validators.py::test_row_count_validation -x` | ❌ W0 | ⬜ pending |
| 02-03-02 | 03 | 3 | DATA-02 | — | N/A | integration | `pytest tests/pipeline/test_validators.py::test_referential_integrity -x` | ❌ W0 | ⬜ pending |
| 02-03-03 | 03 | 3 | DATA-02 | — | N/A | integration | `pytest tests/pipeline/test_validators.py::test_audit_passes -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `src/pipeline/__init__.py` — pipeline package init
- [ ] `src/pipeline/kaggle_converter.py` — main converter module stubs
- [ ] `src/pipeline/column_mapping.py` — column mapping dicts stubs
- [ ] `src/pipeline/validators.py` — data quality validation function stubs
- [ ] `tests/pipeline/__init__.py` — test package init
- [ ] `tests/pipeline/conftest.py` — shared fixtures (sample DataFrames, temp directories)
- [ ] `tests/pipeline/test_column_mapping.py` — column mapping test stubs
- [ ] `tests/pipeline/test_kaggle_converter.py` — converter test stubs
- [ ] `tests/pipeline/test_validators.py` — validation test stubs
- [ ] `data/standard/` directory creation
- [ ] pyarrow installation: add `pyarrow>=14.0` to pyproject.toml dependencies

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Visual inspection of Parquet file sizes | DATA-02 | Size expectations require human judgment | `ls -lh data/standard/*.parquet` — verify sizes are reasonable (~50-200MB total) |
| Spot-check sample rows in Parquet against CSV | DATA-02 | Requires domain knowledge to validate | `pd.read_parquet('data/standard/race.parquet').head()` — compare with source CSV |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
