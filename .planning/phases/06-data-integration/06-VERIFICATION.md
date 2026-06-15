---
phase: 06-data-integration
verified: 2026-06-15T09:35:00Z
status: passed
score: 3/3 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: N/A
  gaps_closed: []
  gaps_remaining: []
  regressions: []
---

# Phase 6: Data Integration — Verification Report

**Phase Goal (ROADMAP):** Kaggle (2015-2021) and scraped datasets are merged into a single unified corpus in standard Parquet, ready for feature engineering and model training.
**Verified:** 2026-06-15T09:35:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

The Phase 6 goal is **achieved**. The three ROADMAP success criteria are independently verified as TRUE by direct inspection of `data/standard/{race,entry,result}.parquet` — NOT by trusting the SUMMARY claims or the `run_all_validations` aggregate (which 06-REVIEW.md flagged as containing lenient PASS-by-default shortcuts in `validators.py`).

All checks below were performed with direct pandas/pyarrow queries that bypass the flagged lenient validator paths (CR-01/CR-02/CR-03), so the corpus-correctness verdict does not depend on those shortcuts.

### ROADMAP Success Criteria (roadmap_truths)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC-1 | A single unified Parquet dataset covers the date range with no duplicate races between Kaggle and scraped sources | VERIFIED | race.parquet: race_id unique (nunique=38,009 == len=38,009, dup=0). horse_race_id 1-to-1 entry↔result (534,953 nunique each, 0 only-in-entry, 0 only-in-result). Kaggle/scraped race_id overlap=0 (kaggle=21,929, scraped=16,080). |
| SC-2 | Schema is identical across the full date range (Kaggle-origin and scraped-origin rows indistinguishable in the standard layer) | VERIFIED | 0 dtype mismatches when race table split by source period (race_date < 2022-01-01 vs >= 2022-01-01). Arrow schema: 0 null columns; 20 race_flag_* all Arrow `bool`; race_date Arrow `string`; distance Arrow `int64`. Column-set matches Pydantic schema for all 3 tables (race/entry/result). No `source` column in any of the 3 unified tables (D-05 honor). |
| SC-3 | Date-range coverage / readiness for downstream phases | VERIFIED | race_date 2015-01-04 .. 2026-05-31 (D-07 LOCKED scope 2015-2026/5 honored — divergence from ROADMAP text "2015-2024" is documented and DEFERRED to Phase 9 per CONTEXT D-07). 12 years present, each year >500 races (min 2026 partial: 1,405). 202605 partition exists + non-empty (322 races). |

**Score:** 3/3 truths verified

### PLAN Must-Have Truths (cross-checked, not load-bearing for the goal verdict)

The three PLANs declare many cycle-resolved HIGHs (HIGH #5/6/7/8/8b/9/11/14/15/16/17/18/19 + cycle-3 NEW PK-set union). All were spot-checked directly:

| Must-have | Status | Evidence |
|-----------|--------|----------|
| HIGH #17 odds/payoff SHA-256 unchanged (D-05) | VERIFIED | odds_trifecta `7473133c...740013` (21,929 rows) and payoff `899987a8...351a` (21,987 rows) — byte-identical to the SUMMARY-claimed pre/post SHA values. Confirmed by independent re-hash on disk. |
| HIGH #18 per-period graded counts | VERIFIED | kaggle period: actual=893 expected=893 (derive_race_flags recompute); scraped period: actual=578 expected=578. Unified total 1,471. |
| NEW HIGH cycle-3 PK-set union (all 3 tables) | VERIFIED | race: input 38,009 == output 38,009; entry: input 534,953 == output 534,953; result: input 534,953 == output 534,953. Set equality per table. |
| HIGH #19 robust date range + EXPECTED_FLOOR + 202605 partition | VERIFIED | dmax (2026-05-31) == actual_scraped_max (2026-05-31); EXPECTED_FLOOR 2026-05-01 satisfied; 202605 partition exists + non-empty. |
| D-01 `(国際)` mapping removed; FLAG_COLUMNS preserved | VERIFIED | `grep -E '国際.*graded_stakes' src/pipeline/column_mapping.py` returns no map entry (only an explanatory comment + FLAG_COLUMNS listing). |
| D-02 dtype contract on regenerated Kaggle kaggle/ subdir | VERIFIED | data/standard/kaggle/{race,entry,result}.parquet exist; serve as integration's separate input path. |
| HIGH #5 idempotent separate Kaggle input path | VERIFIED (code) | `kaggle_input_dir` defaults to `standard_dir / 'kaggle'` (integration.py:225-226); SCHEMA_BY_TABLE hardcoded 3-table allowlist. |
| HIGH #6 validate-before-swap via DEDICATED `_commit_staging` | VERIFIED (code) | `_commit_staging(staging_dir, standard_dir)` defined at integration.py:149-168 (3 os.replace inside); tempfile.mkdtemp staging at line 365. |
| HIGH #8b cycle-4 hard-violation filter includes 'mismatch'/'1-to-1' | VERIFIED (code) | integration.py:330 `if "duplicate" in v or "orphan" in v or "mismatch" in v or "1-to-1" in v`. |
| HIGH #9 column-set equality assert before reindex | VERIFIED (code) | `_assert_column_set_equality` defined at integration.py:127; called on both kaggle_df and scraped_df at lines 279-280. |
| MEDIUM #13 audit_leakage CALLED inside integrate_standard_layer | VERIFIED (code) | audit_leakage called on merged race_df (line 341) and entry_df (line 349). |
| HIGH #2/D-05 convert(core_tables_subdir='kaggle') SKIPS odds/payoff writes | VERIFIED (code) | kaggle_converter.py:267 odds_tables write gated on `core_tables_subdir is None`. data/standard/kaggle/ contains only race/entry/result (odds/payoff absent). |
| HIGH #1 grade detection ordering + OR-merge | VERIFIED (code) | kaggle_converter.py:445 `_apply_grade_detection(race_df)` called AFTER `_UNMAPPED_RACE_FLAGS` loop; OR-merge with `.fillna(False)` at line 136. |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `data/standard/race.parquet` | Unified race 2015-2026/5, no dups, schema-typed | VERIFIED | 38,009 rows; Arrow schema clean; race_id unique; byte-identical to SUMMARY claim |
| `data/standard/entry.parquet` | Unified entry 2015-2026/5 | VERIFIED | 534,953 rows; PK unique; column-set matches EntrySchema |
| `data/standard/result.parquet` | Unified result 2015-2026/5 | VERIFIED | 534,953 rows; PK unique; column-set matches ResultSchema |
| `data/standard/kaggle/{race,entry,result}.parquet` | Regenerated Kaggle corpus as separate input path | VERIFIED | 3 files present; odds/payoff correctly absent |
| `data/standard/odds_trifecta.parquet` | Phase 5 seed, byte-identical pre/post integration | VERIFIED | SHA-256 matches SUMMARY claim; 21,929 rows |
| `data/standard/payoff.parquet` | Phase 5 seed, byte-identical pre/post integration | VERIFIED | SHA-256 matches SUMMARY claim; 21,987 rows |
| `src/pipeline/integration.py` | `integrate_standard_layer` entry point + transactionality + hard-violation filter | VERIFIED | 435 lines; all load-bearing symbols present (SCHEMA_BY_TABLE, _commit_staging, _assert_column_set_equality, kaggle_input_dir, tempfile.mkdtemp, validate_integrity, audit_leakage, mismatch/1-to-1 filter) |
| `src/pipeline/kaggle_converter.py` | `_apply_grade_detection` + `_recast_to_canonical` + `core_tables_subdir` SKIP | VERIFIED | 587 lines; derive_race_flags import + call; odds_tables write gated on `core_tables_subdir is None` |
| `src/pipeline/column_mapping.py` | `(国際)→graded_stakes` mapping removed; FLAG_COLUMNS preserved | VERIFIED | grep confirms no map entry; FLAG_COLUMNS list intact |
| `tests/pipeline/test_integration.py` | 11 tests across 2 classes (hermetic ungated + corpus gated) | VERIFIED | 626 lines; 11 tests collected; all 11 pass (6.69s) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `integrate_standard_layer` | data/standard/{race,entry,result}.parquet | tempfile.mkdtemp staging + `_commit_staging` | WIRED | integration.py:149-168 (`_commit_staging`); line 365 (tempfile.mkdtemp); line 404 (`_commit_staging(staging_dir, standard_dir)`) |
| `integrate_standard_layer` | `validate_integrity` + `audit_leakage` | direct import + call | WIRED | integration.py:73 (import); lines 318 + 341/349 (calls) |
| `kaggle_converter.split_race_entry_result` | `derive_race_flags` | import + `_apply_grade_detection` | WIRED | kaggle_converter.py:30 (import); line 445 (`_apply_grade_detection`) call after `_UNMAPPED_RACE_FLAGS` loop |
| `convert(core_tables_subdir='kaggle')` | data/standard/kaggle/{race,entry,result}.parquet | `core_tables_subdir` param + odds/payoff SKIP | WIRED | kaggle_converter.py:173 (param); line 256 (out_dir redirect); line 267 (odds_tables gated on `core_tables_subdir is None`) |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|----|
| data/standard/race.parquet | race_id, race_date, race_flag_* | Kaggle kaggle/ + scraped/* partitions via integrate_standard_layer | Yes (38,009 rows, real JRA race IDs 2015-2026/5) | FLOWING |
| data/standard/entry.parquet | horse_race_id, win_odds, popularity | Kaggle kaggle/ + scraped/* partitions | Yes (534,953 rows; graded counts match derive_race_flags per period) | FLOWING |
| data/standard/result.parquet | horse_race_id, finish_position, corner_1..4 | Kaggle kaggle/ + scraped/* partitions | Yes (534,953 rows; 1-to-1 with entry) | FLOWING |

No hardcoded empty arrays or static returns in the data path. Integration reads real Kaggle Parquet + 58 real scraped month partitions and writes the merge.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| race_id uniqueness in unified race | `python -c "import pandas as pd; r=pd.read_parquet('data/standard/race.parquet'); assert r['race_id'].nunique()==len(r)==38009"` | passed | PASS |
| horse_race_id 1-to-1 entry↔result | `python -c "...e=set(pd.read_parquet('data/standard/entry.parquet',columns=['horse_race_id'])['horse_race_id']); r=set(pd.read_parquet('data/standard/result.parquet',columns=['horse_race_id'])['horse_race_id']); assert e==r and len(e)==534953"` | passed | PASS |
| Zero Kaggle/scraped race_id overlap | direct set intersection computation | overlap == 0 | PASS |
| 11 integration tests green | `python -m pytest tests/pipeline/test_integration.py -q` | 11 passed in 6.69s | PASS |
| Full suite health | `python -m pytest tests/ -q` | 497 passed, 2 failed (deferred feature_generator), 1 skipped | PASS (the 2 failures are scoped to Phase 3 re-run — see Deferred) |
| odds/payoff SHA-256 unchanged | `python -c "import hashlib; ..."` | byte-identical to SUMMARY claim | PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` conventions declared for this phase. The verification was performed via direct pandas/pyarrow queries and the integration test suite (which itself contains cycle-5 isolated regression tests for the load-bearing properties — `_commit_staging` mid-swap recovery, horse_race_id mismatch hard-classification).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| DATA-05 | 06-01, 06-02, 06-03 | 2015-2024年のデータ（Kaggle + 自前収集）を共通standard形式でParquet出力し、統合して扱えること | SATISFIED | Unified `data/standard/{race,entry,result}.parquet` covers 2015-2026/5 (D-07 LOCKED scope supersedes ROADMAP text "2015-2024"; divergence documented + DEFERRED to Phase 9). All 3 ROADMAP success criteria verified TRUE. REQUIREMENTS.md line 14 marks DATA-05 as `[x]` complete; traceability table line 95 maps DATA-05 → Phase 6 → Complete. No orphaned requirement IDs. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/pipeline/validators.py` | 36 | `_DTYPE_COMPAT['bool']` accepts `"object"` (06-REVIEW CR-01) | Warning | Validator-lenient path — does NOT affect corpus correctness (verified independently of this validator). Should be tightened in a follow-up. |
| `src/pipeline/validators.py` | 525-566 | `validate_sample_rows` silent-True escape paths (06-REVIEW CR-02) | Warning | Validator-lenient path — corpus integrity verified independently (PK-set union, FK, row counts all check out directly). |
| `src/pipeline/validators.py` | 852 | `audit_pass` hardcoded `True` (06-REVIEW CR-03) | Warning | Validator-lenient path — `audit_leakage` is still CALLED inside `integrate_standard_layer` (integration.py:341/349) and RAISES on unexpected leaks. The post-hoc `run_all_validations` shortcut does not undermine the corpus. |
| `src/scraper/flag_crosswalk.py` | 30-46 | Stale "out of scope" docstring contradicting D-01 removal (06-REVIEW CR-04) | Warning | Maintainability risk — future maintainer could re-introduce the bug. Not a corpus defect. |
| `src/pipeline/integration.py`, `src/pipeline/kaggle_converter.py`, `src/pipeline/column_mapping.py` | — | No TBD/FIXME/XXX/TODO/HACK markers found | Info | Clean of debt markers in Phase 6 source modules. |

**BLOCKER scan:** No unresolved TBD/FIXME/XXX debt markers in any Phase 6-modified file. The 06-REVIEW.md findings are tracked separately as a code-review artifact (4 critical / 9 warning / 6 info). They are real defects in `validators.py` and `flag_crosswalk.py` documentation, but they do not block the Phase 6 GOAL because the corpus was verified correct via independent paths.

### 06-REVIEW.md BLOCKERs — Independent Impact Assessment

The verification brief specifically asked: do CR-01/CR-02/CR-03/CR-04 undermine the `run_all_validations overall_pass=True` claim that underpins the corpus-correctness verdict?

**Answer: No.** The `run_all_validations overall_pass=True` claim is corroborated by independent direct checks that do NOT route through the flagged lenient paths:

- CR-01 (bool accepts object): I verified `every race_flag_* Arrow type == 'bool'` directly via `pyarrow.parquet.read_schema` (not via `_DTYPE_COMPAT`). Result: 20/20 bool, 0 mismatches.
- CR-02 (validate_sample_rows silent True): I verified row counts, PK uniqueness, and PK-set union directly via pandas — not via `validate_sample_rows`.
- CR-03 (audit_pass hardcoded True): I verified the integration module itself RAISES on race leakage (`audit_leakage` called at integration.py:341 and the hard-violation filter at line 330 catches unexpected entry leaks). The post-hoc validator shortcut does not create a corpus defect.
- CR-04 (stale docstring): Maintainability risk only.

These BLOCKERs are real and should be scheduled for a validator-hardening follow-up (not a Phase 6 gap — Phase 6's goal is the unified corpus, which is verified correct). The 06-REVIEW.md itself classifies Phase 6's transactional design as "well-motivated" and the cycle-5 isolated tests as "genuine regression guards."

### Deferred Items

Per Step 9b, two items are explicitly addressed in later phases — NOT Phase 6 gaps:

| # | Item | Addressed In | Evidence |
|---|------|--------------|----------|
| 1 | feature_generator 2-test failure (`np.select` empty condlist TypeError on larger unified corpus) | Phase 3 (feature-engineering) re-run, scheduled before Phase 7 | 06-CONTEXT.md Deferred Ideas: "feature 層の再生成（Phase 3 再実行）— Phase 6 完了後、Phase 7 前に統合 corpus で feature 層を再生成。別タスク。Phase 6 スコープ外。" Logged in `.planning/phases/06-data-integration/deferred-items.md`. Suite health: 497 passed / 2 failed (these 2) / 1 skipped. The corpus itself is correct (8-point validation green, PK-set union equality, FK clean). |
| 2 | ROADMAP success criterion #3 text "2015-2024" → "2015-2026/5" update | Phase 9 (backtest planning) | 06-CONTEXT.md Deferred Ideas: "ROADMAP 成功基準#3 の範囲更新（2015-2024 → 2015-2026/5）— D-07 の決定に合わせ ROADMAP 記載を更新するかは、Phase 9 バックテスト計画時に再調整。" D-07 LOCKED scope takes precedence; verification honors D-07, not the stale ROADMAP text. |

### Human Verification Required

None required beyond the existing `checkpoint:human-verify` already approved in 06-03-SUMMARY.md (line 280: "Approved on: 2026-06-15"). All automated checks pass and the corpus was inspected directly.

### Gaps Summary

No gaps blocking the Phase 6 goal. All three ROADMAP success criteria are independently verified as TRUE via direct pandas/pyarrow inspection that bypasses the lenient validator paths flagged by 06-REVIEW.md.

The 06-REVIEW.md BLOCKERs (CR-01/CR-02/CR-03 in `validators.py` + CR-04 stale docstring in `flag_crosswalk.py`) are real defects but they affect the `run_all_validations` aggregate's defense-in-depth, not the corpus itself. The corpus is correct. These should be scheduled as a validator-hardening task (separate from Phase 6's goal) — recommended target: before Phase 9 backtest, so the post-hoc validator can be trusted as an independent guard rather than corroborated by hand.

The two deferred items (feature_generator failure → Phase 3 re-run; ROADMAP text update → Phase 9) are explicitly out of Phase 6 scope per CONTEXT.md and do not block the goal.

---

_Verified: 2026-06-15T09:35:00Z_
_Verifier: Claude (gsd-verifier)_
