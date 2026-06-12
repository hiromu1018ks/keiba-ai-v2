---
phase: 3
slug: feature-engineering
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-12
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 |
| **Config file** | pyproject.toml [tool.pytest.ini_options] testpaths=["tests"] |
| **Quick run command** | `python3 -m pytest tests/pipeline/test_feature_generator.py -x -q` |
| **Full suite command** | `python3 -m pytest tests/ -x` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest tests/pipeline/test_feature_generator.py -x -q`
- **After every plan wave:** Run `python3 -m pytest tests/ -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | DATA-03 | — | N/A | unit | `python3 -m pytest tests/pipeline/test_feature_generator.py::test_race_context_features -x` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 1 | DATA-03 | — | N/A | unit | `python3 -m pytest tests/pipeline/test_feature_generator.py::test_horse_basic_features -x` | ❌ W0 | ⬜ pending |
| 03-02-01 | 02 | 1 | DATA-03 | — | N/A | unit | `python3 -m pytest tests/pipeline/test_feature_generator.py::test_margin_conversion -x` | ❌ W0 | ⬜ pending |
| 03-02-02 | 02 | 1 | DATA-03 | — | N/A | unit | `python3 -m pytest tests/pipeline/test_feature_generator.py::test_finish_time_zscore -x` | ❌ W0 | ⬜ pending |
| 03-03-01 | 03 | 2 | DATA-03 | — | N/A | unit | `python3 -m pytest tests/pipeline/test_feature_generator.py::test_lag_features_temporal_safety -x` | ❌ W0 | ⬜ pending |
| 03-03-02 | 03 | 2 | DATA-03 | — | N/A | unit | `python3 -m pytest tests/pipeline/test_feature_generator.py::test_jockey_trainer_stats -x` | ❌ W0 | ⬜ pending |
| 03-04-01 | 04 | 2 | DATA-03 | — | N/A | unit | `python3 -m pytest tests/pipeline/test_feature_generator.py::test_target_top3_generation -x` | ❌ W0 | ⬜ pending |
| 03-04-02 | 04 | 2 | DATA-03 | — | N/A | unit | `python3 -m pytest tests/pipeline/test_feature_generator.py::test_debut_flag -x` | ❌ W0 | ⬜ pending |
| 03-05-01 | 05 | 3 | DATA-03 | T-03-01 | Path validated within project root | unit | `python3 -m pytest tests/pipeline/test_feature_generator.py::test_categorical_conversion -x` | ❌ W0 | ⬜ pending |
| 03-05-02 | 05 | 3 | DATA-03 | T-03-02 | Parquet uses pyarrow engine | unit | `python3 -m pytest tests/pipeline/test_feature_generator.py::test_leakage_audit -x` | ❌ W0 | ⬜ pending |
| 03-05-03 | 05 | 3 | DATA-03 | — | N/A | integration | `python3 -m pytest tests/pipeline/test_feature_generator.py::test_e2e_feature_generation -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/pipeline/test_feature_generator.py` — stubs for DATA-03
- [ ] `tests/pipeline/conftest.py` — feature-specific fixtures (sample race+entry+result data)
- [ ] `src/pipeline/feature_generator.py` — implementation module

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Feature Parquet output inspection (row counts, column types) | DATA-03 | Visual verification of output quality | Load output Parquet in Python, verify ~311K rows, ~71 feature columns, correct dtypes |
| ROADMAP success criterion #1 discrepancy (popularity/win odds vs D-15) | DATA-03 | Design decision confirmation needed | Confirm D-15 precedence before finalizing |

*All automated verifications are covered by test suite above.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
