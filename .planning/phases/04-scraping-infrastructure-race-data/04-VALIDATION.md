---
phase: 04
slug: scraping-infrastructure-race-data
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-13
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` testpaths=["tests"] |
| **Quick run command** | `pytest tests/scraper/ -x -q` |
| **Full suite command** | `pytest tests/ -x` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/scraper/ -x -q`
- **After every plan wave:** Run `pytest tests/ -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | SCRP-01 | — | N/A | unit | `pytest tests/scraper/test_fetcher.py -x` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 1 | SCRP-01, SCRP-02 | T-04-01 | Rate limiting enforced | unit | `pytest tests/scraper/test_fetcher.py -x` | ❌ W0 | ⬜ pending |
| 04-03-01 | 03 | 1 | SCRP-01 | — | N/A | unit | `pytest tests/scraper/test_parser.py -x` | ❌ W0 | ⬜ pending |
| 04-04-01 | 04 | 1 | SCRP-03 | — | N/A | unit | `pytest tests/scraper/test_normalizer.py -x` | ❌ W0 | ⬜ pending |
| 04-05-01 | 05 | 2 | SCRP-05 | — | N/A | unit | `pytest tests/scraper/test_normalizer.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/scraper/__init__.py` — package init
- [ ] `tests/scraper/conftest.py` — shared fixtures (sample HTML from actual race, parsed data)
- [ ] `tests/scraper/test_fetcher.py` — fetch tests (mock Playwright, dedup check)
- [ ] `tests/scraper/test_parser.py` — parser tests (with saved HTML fixture)
- [ ] `tests/scraper/test_normalizer.py` — normalizer tests (dict -> DataFrame -> audit)
- [ ] `src/scraper/__init__.py` — scraper package

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Actual netkeiba page fetch | SCRP-02 | Requires network access + rate limiting; not safe for CI | Run `python -m src.scraper.fetcher --dry-run 2022 01` and verify HTML saved |
| Calendar enumeration end-to-end | SCRP-02 | Requires network access; long-running | Run `python -m src.scraper.fetcher --enumerate 2022 01` and verify race_id list |
| Parquet output schema match | SCRP-03 | Visual comparison with Kaggle Parquet schema | Compare scraped Parquet dtypes with Kaggle Parquet dtypes |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
