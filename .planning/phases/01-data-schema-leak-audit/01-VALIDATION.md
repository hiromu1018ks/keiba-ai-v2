---
phase: 01
slug: data-schema-leak-audit
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-11
---

# Phase 01 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.x |
| **Config file** | pyproject.toml (created in Plan 01-01 Task 1) |
| **Quick run command** | `python -m pytest tests/schemas/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -v --tb=short` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/schemas/ -x -q`
- **After every plan wave:** Run `python -m pytest tests/schemas/ -v --tb=short`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | DATA-01 | T-01-01/02 | N/A | unit | `python -m pytest tests/schemas/test_race.py -x -q` | Wave 0 creates | pending |
| 01-01-02 | 01 | 1 | DATA-01 | — | N/A | unit | `python -m pytest tests/schemas/test_entry.py -x -q` | Wave 0 creates | pending |
| 01-02-01 | 02 | 2 | DATA-01 | — | N/A | unit | `python -m pytest tests/schemas/test_result.py -x -q` | Wave 0 creates | pending |
| 01-02-02 | 02 | 2 | DATA-01 | — | N/A | unit | `python -m pytest tests/schemas/test_odds_trifecta.py tests/schemas/test_payoff.py -x -q` | Wave 0 creates | pending |
| 01-03-01 | 03 | 3 | DATA-04 | T-01-09 | Warning-only (no raise) | unit | `python -m pytest tests/schemas/test_audit.py -x -q` | Wave 0 creates | pending |
| 01-04-01 | 04 | 4 | DATA-01, DATA-04 | T-01-10/11 | N/A | unit | `python -m pytest tests/schemas/test_classification.py tests/schemas/test_schema_export.py -x -q` | Wave 0 creates | pending |
| 01-05-01 | 05 | 5 | DATA-01, DATA-04 | — | N/A | unit | `python -m pytest tests/schemas/ -x -q` | Wave 0 creates | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

All test files are created by the plans themselves (TDD: tests written first). No separate Wave 0 scaffolding needed -- Plan 01-01 Task 1 creates pyproject.toml and the first test file.

- [x] `pyproject.toml` — created in Plan 01-01 Task 1
- [x] `tests/schemas/__init__.py` — created in Plan 01-01 Task 1
- [x] Test files created by each plan's TDD task (test first, implementation second)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|

All phase behaviors have automated verification.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 10s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
