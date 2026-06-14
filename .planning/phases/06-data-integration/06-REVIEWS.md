---
phase: 06-data-integration
reviewers: [codex]
reviewed_at: 2026-06-14T21:30:00+09:00
plans_reviewed:
  - 06-01-PLAN.md
  - 06-02-PLAN.md
  - 06-03-PLAN.md
cycle: 5
prior_cycle_high: 3
cycle_5_replan_commit: 7a93589
---

# Cross-AI Plan Review — Phase 6 (Cycle 5 — FINAL convergence)

Cycle-5 re-review — the FINAL convergence pass of the plan-review-convergence loop.
The three PLAN.md files were replanned (git commit `7a93589`, touching 06-02 + 06-03)
to address the 3 HIGHs that remained unresolved after cycle 4. Codex (gpt-5.5 via
`codex exec`, codex-cli 0.139.0) re-reviewed the revised plans with repository read
access (workdir: `/Users/hart/develop/keiba-ai-v2`, sandbox granted
`disk-full-read-access` + `git-read-access`). The orchestrator then independently
re-verified every load-bearing claim Codex raised against the working tree before
recording the adjudication below.

**Headline:** of the 3 cycle-4 HIGHs, **2 are FULLY RESOLVED** (HIGH #1 mismatch test
isolation, HIGH #3 D-07 month completeness) and **1 is PARTIALLY RESOLVED** (HIGH #2
`_commit_staging` boundary isolation is correct, but the recovery test still does not
prove what its name claims). Net result: **1 HIGH remains unresolved** (trend
14 → 7 → 5 → 3 → 1, monotonic and decreasing — near convergence, one test-design
patch away from 0).

The cycle-5 replan correctly fixed the structural problem Codex flagged in cycle 4
(monkeypatch firing during staging writes): extracting the swap into a DEDICATED,
PATCHABLE module-level function `_commit_staging(staging_dir, standard_dir)` IS the
right boundary — patching that symbol no longer touches `_atomic_write_parquet`'s
`os.replace`. The cycle-5 mismatch test (DISJOINT unique horse_race_ids `entry=["E1"]`,
`result=["R1"]`) is genuinely load-bearing. The cycle-5 D-07 enforcement
(`EXPECTED_FLOOR='2026-05-01'` + `set(present_months) == set(expected 202201..202605)`)
correctly honors the LOCKED scope.

Codex raised **1 NEW HIGH defect**:

1. **06-02 NEW HIGH — partial-swap recovery test does not prove recovery from a
   mixed-generation state.** The cycle-5 `_commit_staging` test mutates only the
   `entry` and `result` scraped partitions (06-02-PLAN.md:298-317) — NOT the `race`
   scraped partition. The swap order is `race → entry → result` and the failure fires
   on the 2nd call (entry, before any of the mutated tables are swapped). At the
   failure point, the only file swapped is `race`, which produces byte-identical
   output to canonical (race input was unchanged). The mutated entry/result
   new-generation files are staged but NEVER swapped (the failure fired first).
   Therefore at the OSError, all 3 root files are STILL canonical. Worse, the
   `failing_commit_staging` wrapper raises UNCONDITIONALLY (n==2 is always reached),
   so `integrate_standard_layer` always propagates the OSError and the `try`-body
   `post != canonical` assertion is DEAD CODE — never executed. The test effectively
   proves only (a) integration raises OSError on a patched swap failure, and (b) a
   normal re-run after restore is idempotent. It does NOT prove recovery from a
   detectable mid-swap mixed-generation state, which is what its name
   (`test_integration_partial_swap_recoverable`) claims. Orchestrator-verified
   against 06-02-PLAN.md:290-359 and normalizer.py:643-653.

The 06-03 MEDIUM (subdir name not validated against `\d{6}` — a stray `__pycache__`
under `data/standard/scraped/` would be classified as an `extra_month` and halt the
preflight) is legitimate but does not corrupt the corpus; it is a false-positive
robustness gap, not a coverage gap.

This is documented so a targeted cycle-6 patch (or in-execution fix) can close the
last HIGH without another full review.

---

## Codex Review

### Plan 06-01 Review

**Risk Assessment: LOW.** Unchanged in the cycle-5 replan (commit 7a93589 touched
only 06-02 and 06-03). Carries forward the cycle-4 verdict (LOW) — the cycle-3
fixes (grade detection ordering, `_GRADE_REGEX` `G1` match, odds/payoff non-write,
8-point relocation) remain valid. No new concerns in this cycle.

### Plan 06-02 Review

**Summary**

The cycle-5 `_commit_staging` boundary isolation is CORRECT and the mismatch test
is genuinely load-bearing — but the partial-swap recovery test still does not prove
what its name claims.

#### Cycle-4 HIGH Adjudication (06-02)

| # | Verdict | Orchestrator-Verified Evidence |
|---|---------|--------------------------------|
| HIGH #1 (mismatch test isolation) | **FULLY RESOLVED** | With cycle-5 test data `entry=["E1"], result=["R1"]`: check (b) entry dup (normalizer.py:294-299) — `Counter({"E1":1})`, no dup → passes; check (c) result dup (normalizer.py:302-307) — `Counter({"R1":1})`, no dup → passes; check (d) 1-to-1 (normalizer.py:320-336) — `Counter({"E1":1}) != Counter({"R1":1})` → returns EXACTLY ONE violation `"horse_race_id mismatch: entry/result are not 1-to-1 (only-in-entry=1, only-in-result=1, count-mismatch={})"` containing `"mismatch"` and `"1-to-1"`; checks (e)/(f) FK (normalizer.py:338-372) — no orphans IF race_df contains both referenced race_ids (the plan explicitly instructs this at 06-02-PLAN.md:270). So `validate_integrity` returns `len == 1` and `"mismatch" in violations[0]`. The `assert len(violations) == 1` is genuinely load-bearing: removing `"mismatch"` from the hard-violation filter would let this data pass with NO hard violation, and `pytest.raises(ValueError)` would fail. Orchestrator-verified against normalizer.py:293-372 and 06-02-PLAN.md:182,270-282. |
| HIGH #2 (`_commit_staging` boundary) | **PARTIALLY RESOLVED** | The BOUNDARY ISOLATION is correct: `_atomic_write_parquet` (normalizer.py:643-653) calls `os.replace` at line 653 during STAGING writes, but the cycle-5 swap is extracted into a DEDICATED `_commit_staging(staging_dir, standard_dir)` (06-02-PLAN.md:218-231) that performs its own 3 `os.replace` calls. Patching `monkeypatch.setattr(integration_mod, "_commit_staging", failing_swap)` (06-02-PLAN.md:328) does NOT touch `_atomic_write_parquet`'s os.replace — staging writes complete normally, and the monkeypatch fires only during the actual swap. This structurally fixes the cycle-4 defect (monkeypatch firing during staging). HOWEVER the recovery test itself does not prove recovery — see NEW HIGH #1 below. The PRODUCTION-CODE design (validate-before-swap via `tempfile.mkdtemp` + idempotent recovery) remains sound; only the test's observable-claim is flawed. |
| HIGH #6 (transactionality design — carried) | **RESOLVED** (KEPT) | Validate-before-swap via `tempfile.mkdtemp(prefix='.integration_staging_', dir=standard_dir)` (06-02-PLAN.md:261); staged files validated before swap; idempotent recovery via re-run against immutable inputs. The cycle-5 `_commit_staging` extraction does not regress this. |
| HIGH #5 (idempotency — carried) | **RESOLVED** (KEPT) | Separate `kaggle_input_dir`; idempotency test retained. |
| HIGH #7 (autouse skip — carried) | **RESOLVED** (KEPT) | Two-class split. |
| HIGH #8 (FK orphan — carried) | **RESOLVED** (KEPT) | Orphan injection + `validate_integrity` + ValueError. |
| HIGH #8b (mismatch filter — carried, cycle-4 prod fix + cycle-5 test fix) | **RESOLVED** | Filter extended with `"mismatch"`/`"1-to-1"` (matches normalizer.py:330-334 string containing NEITHER `"duplicate"` NOR `"orphan"`); cycle-5 test proves token is load-bearing via DISJOINT unique horse_race_ids. |
| HIGH #9 (column-set equality — carried) | **RESOLVED** (KEPT) | `_assert_column_set_equality` before reindex. |

#### New Concerns (06-02)

- **HIGH — partial-swap recovery test does not prove recovery from a mixed-generation state.** The cycle-5 `_commit_staging` test `test_integration_partial_swap_recoverable` (06-02-PLAN.md:290-359) has two structural flaws that together make it prove only "integration raises OSError on a patched swap" + "normal re-run is idempotent", NOT the claimed "recovery from a mid-swap mixed-generation state":
  1. **Race input is not mutated, but race is the only file swapped before the failure.** The test mutates `entry.parquet` and `result.parquet` scraped partitions (06-02-PLAN.md:302-317) but NOT `race.parquet`. The swap order is `tbls = ("race", "entry", "result")` and `failing_commit_staging` raises when `call_counter["n"] == 2` (06-02-PLAN.md:322-327) — i.e. on the 2nd iteration, which is `entry`. So the sequence is: n=1 → `race` swapped via `real_replace` (race new-gen == canonical because race input unchanged → byte-identical); n=2 → raises OSError on `entry` BEFORE `real_replace`. At the failure point: `race.parquet` root = new-gen = canonical (identical bytes); `entry.parquet` and `result.parquet` root = OLD canonical (never swapped, the mutated new-gen versions are still in staging). So all 3 root files == canonical. The assertion `any(post.get(t) != canonical[t] for t in tbls)` (06-02-PLAN.md:339) would FAIL if reached — but it's never reached because of flaw #2.
  2. **The `failing_commit_staging` raise is unconditional, so the `try`-body `post != canonical` assertion is dead code.** `failing_commit_staging` always reaches `n == 2` (there is no early return or skip), so it always raises OSError. `integrate_standard_layer` propagates the OSError, the `try` body's `post = {...}` and the `assert any(post != canonical)` never execute — control jumps to `except OSError: pass` (06-02-PLAN.md:341-342). The test therefore never observes a post-failure corpus state. The recovery half (06-02-PLAN.md:344-358) then restores `_commit_staging`, re-invokes, and asserts byte-identical re-run — but this proves only standard idempotency (the third invocation matches the second), NOT recovery from an inconsistent state, because there was never an inconsistent state to recover FROM (all 3 files were canonical at the failure point).
  - **Why this matters:** the test's name and docstring claim it proves "idempotent recovery under the REAL mid-swap failure". In reality it proves (a) the OSError propagates, and (b) a clean re-run after a clean (non-mutating) failure is idempotent. A genuine recovery regression (e.g. `_commit_staging` swallowing the OSError, or `integrate_standard_layer` reading its own output on re-run) would NOT be caught by this test.
  - Orchestrator-verified against 06-02-PLAN.md:290-359 and normalizer.py:643-653.
- **MEDIUM — return-type annotation inaccurate (carried).** `integrate_standard_layer(...) -> dict[str, Path]` but the return includes `{"audit": {...}}` (a dict, not a Path). Should be `dict[str, Path | dict]` or a TypedDict. (Carried from cycle 3, not yet fixed; not load-bearing.)

#### Suggestions (06-02)

- **Few-line fix for NEW HIGH #1:** to make the recovery test genuinely prove recovery from a mixed-generation state:
  1. **Mutate the `race` scraped partition too** (append a row, bump a race_id), so the race new-gen differs from canonical. Then the 1st swap (race) DOES replace canonical with a different file — at the failure point (entry, n=2), `race.parquet` root = new-gen != canonical, `entry`/`result` root = old canonical → a REAL mixed-generation state.
  2. **Catch the OSError, then ASSERT the mixed state** before recovery: `assert post["race"] != canonical["race"] and post["entry"] == canonical["entry"]` (race is new-gen, entry/result are old canonical). This is the observable proof of a mid-swap inconsistent corpus.
  3. **Recovery assertion must compare against an INDEPENDENTLY computed expected hash**, not the recovery run's own output. Either (a) run the integration against a SEPARATE temp dir with identical mutated inputs to compute the expected hashes independently, then assert the recovery-run output matches those, or (b) assert that the mutated extra row is now present in the recovered `entry.parquet` (a content check, not a self-referential hash check).
  - The current `fresh_after` is computed from the recovery run's own output (06-02-PLAN.md:351), so the third-run idempotency check (06-02-PLAN.md:355-358) is a tautology — it proves the second and third runs agree, not that either is correct.
- Fix the return-type annotation (carried MEDIUM).

**Risk Assessment: HIGH.** The boundary isolation (cycle-4 HIGH #2 structural fix) is
correct, and the mismatch test (cycle-4 HIGH #1) is genuinely load-bearing. But the
partial-swap recovery test still does not prove recovery from a mixed-generation state
— it proves only OSError propagation + standard idempotency. A genuine recovery
regression would pass this test undetected.

---

### Plan 06-03 Review

**Summary**

The cycle-5 D-07 enforcement (`EXPECTED_FLOOR='2026-05-01'` + `set(present_months) ==
set(expected 202201..202605)` + `202605` partition non-empty) is correct and complete.
One MEDIUM robustness gap remains (subdir name validation).

#### Cycle-4 HIGH Adjudication (06-03)

| # | Verdict | Orchestrator-Verified Evidence |
|---|---------|--------------------------------|
| HIGH #3 / #14 (D-07 floor + missing months) | **FULLY RESOLVED** | (a) Floor: `EXPECTED_FLOOR = '2026-05-01'` (06-03-PLAN.md:356) — a scrape stopping at 2026-04 now FAILS the floor (cycle-4's `'2026-01-01'` was too weak). Honors CONTEXT D-07 line 45 "実データ全部（2015-2026/5）" + Phase 4 D-05 "2022年1月〜2026年5月末". (b) Missing months: `expected_months = set(pd.period_range("2022-01", "2026-05", freq="M").strftime("%Y%m"))` = 53 months (verified: 202201..202605 inclusive); `set(present_months) == set(expected_months)` enforced with `missing_months`/`extra_months` halting on non-empty (06-03-PLAN.md:142-152). A scrape missing any month between 2022-01 and 2026-05 FAILS. (c) Structural May-2026 proof: `202605` partition exists + `pq.ParquetFile('data/standard/scraped/202605/race.parquet').metadata.num_rows > 0` (06-03-PLAN.md:192-194). All per-partition race_date values match their dir name (06-03-PLAN.md:179-183), so a non-empty 202605 cannot have race_date max < 2026-05 — the date floor and partition check are consistent. Orchestrator-verified against 06-CONTEXT.md:45 and 06-03-PLAN.md:130-197. |
| HIGH #11 (zero-tolerance gate — carried) | **RESOLVED** (KEPT) | `if len(invalid) > 0: sys.exit(1)` (06-03-PLAN.md:188-189); exceptions re-raised. |
| HIGH #2 (source_stats unified — carried) | **RESOLVED** (KEPT) | `source_stats` computed from `urace = pd.concat([krace, srace])` / `uentry` (06-03-PLAN.md:302-322); same corpus as output → within tolerance → `overall_pass=True`. |
| HIGH #3 (8-point relocation — carried) | **RESOLVED** (KEPT) | Full 8-point `run_all_validations` against `data/standard/` root (5 tables coexist). |
| HIGH #17 (odds/payoff SHA-256 — carried) | **RESOLVED** (KEPT) | Pre/post SHA-256 + row count in verify.automated (06-03-PLAN.md:271-285). |
| HIGH #18 (per-period graded — carried) | **RESOLVED** (KEPT) | Per-period `derive_race_flags` comparison. |
| NEW PK-set union (race + entry + result — carried) | **RESOLVED** (KEPT) | PK-set union verified for all 3 tables (06-03-PLAN.md:371-381). |
| HIGH #15 (halt-on-smoke-only — carried) | **RESOLVED** (KEPT) | `< 40` partitions → exit 1 (retained as redundant sanity below the set-equality gate). |

#### New Concerns (06-03)

- **MEDIUM — any subdirectory under `data/standard/scraped/` is treated as a month partition.** `dirs = sorted(d for d in root.iterdir() if d.is_dir())` (06-03-PLAN.md:138) collects ALL subdirectories without validating the name matches `\d{6}`. A stray `__pycache__/`, `.tmp/`, `.DS_Store`-adjacent directory, or IDE artifact would be classified as an `extra_month` and halt the preflight (06-03-PLAN.md:145-152). This is a false-positive robustness gap (the corpus is NOT corrupted — the gate fails loudly rather than silently passing a bad corpus), so MEDIUM not HIGH. The fix is to filter partition candidates with `re.fullmatch(r"\d{6}", d.name)` and warn on (not halt for) non-matching directories. Orchestrator-verified against 06-03-PLAN.md:138-152.
- **MEDIUM — `validate_sample_rows` weak coverage for scraped-origin rows (carried).** When a parquet row's race_id is not found in the Kaggle CSV source, `validate_sample_rows` `continue`s and treats it as "filtered out, OK" (validators.py:565-576). Scraped rows have race_ids absent from the Kaggle CSV, so they are skipped rather than validated against a source. Coverage gap, not correctness defect. (Carried from cycle 4.)

#### Suggestions (06-03)

- Filter partition candidates: `dirs = sorted(d for d in root.iterdir() if d.is_dir() and re.fullmatch(r"\d{6}", d.name))`; warn on non-matching directories separately.
- Optional: add a scraped-specific sample validation (compare a sample of scraped rows against the scraped raw HTML partition source) to close the `validate_sample_rows` MEDIUM.

**Risk Assessment: LOW-MEDIUM.** D-07 month-range and missing-month enforcement are
complete. Only the extra-directory false-positive robustness gap remains; it does not
corrupt the corpus.

---

## Consensus Summary

Single-reviewer cycle (Codex / gpt-5.5). The orchestrator independently verified
every load-bearing claim Codex raised against the working tree — all corroborated
(see inline "Orchestrator-Verified Evidence" in each adjudication row). No divergent
views.

### Resolved cycle-4 HIGHs (2 — counted out)

- **HIGH #1 mismatch test isolation** — cycle-5 test data `entry=["E1"], result=["R1"]` (DISJOINT UNIQUE horse_race_ids) makes `validate_integrity` return EXACTLY ONE violation containing `"mismatch"`; the `assert len(violations) == 1` is genuinely load-bearing (removing the token lets the data pass with no hard violation). The token now provably classifies the 1-to-1-only case.
- **HIGH #3 D-07 month-level completeness** — `EXPECTED_FLOOR='2026-05-01'` + `set(present_months) == set(expected 202201..202605)` (53 months) + `202605` partition non-empty. A scrape stopping at 2026-04, or missing any scattered month, now FAILS the gate. Honors CONTEXT D-07 LOCKED scope.

### Unresolved HIGH (1 — carried forward)

1. **[06-02, NEW HIGH] partial-swap recovery test does not prove recovery from a mixed-generation state** — the test mutates only `entry`/`result` scraped partitions, but the swap order (`race → entry → result`) and the unconditional raise on the 2nd call (entry) mean only `race` is swapped before the failure, and `race` was not mutated (so race new-gen == canonical). At the failure point all 3 root files are still canonical; and the `failing_commit_staging` raise is unconditional, so the `try`-body `post != canonical` assertion is dead code (control jumps to `except OSError: pass`). The test proves only OSError propagation + standard idempotency, NOT recovery from a detectable mid-swap mixed-generation state. The `_commit_staging` BOUNDARY ISOLATION (the cycle-4 structural defect) IS correctly fixed; only the test's observable claim is flawed. Orchestrator-verified against 06-02-PLAN.md:290-359 and normalizer.py:643-653.

### Divergent Views

Single reviewer — no divergence. Orchestrator source verification corroborates all
load-bearing claims rather than contradicting.

### Recommended next actions (targeted patch — cycle 6)

The single unresolved HIGH has a few-line fix. It can be applied via a targeted
patch commit rather than another full convergence cycle:

- **06-02 partial-swap recovery test (NEW HIGH #1):** (a) mutate the `race` scraped
  partition too (so the race new-gen differs from canonical — the 1st swap then
  produces a genuinely different file); (b) after catching the OSError, ASSERT the
  mixed state before recovery (`post["race"] != canonical["race"]` AND
  `post["entry"] == canonical["entry"]`); (c) compute the expected recovery hashes
  INDEPENDENTLY (run integration against a separate temp dir with identical mutated
  inputs), then assert the recovery-run output matches those independent hashes
  rather than the recovery run's own output.

After this 1 patch, the phase should reach 0 HIGHs and the loop converges.

---

## CYCLE_SUMMARY

CYCLE_SUMMARY: current_high=1

## Current HIGH Concerns

- **[06-02, NEW HIGH] partial-swap recovery test does not prove recovery from a mixed-generation state** — the test mutates only `entry`/`result` scraped partitions but NOT `race`; the swap order is `race → entry → result` and `failing_commit_staging` raises unconditionally on the 2nd call (entry), so the only file swapped before the failure is `race` (which was not mutated → race new-gen byte-identical to canonical). At the failure point all 3 root files are still canonical. Worse, the unconditional raise means the `try`-body `post != canonical` assertion is dead code (control always jumps to `except OSError: pass`), so the test never observes a post-failure corpus state. The test proves only (a) OSError propagation and (b) standard re-run idempotency — NOT recovery from a detectable mid-swap mixed-generation state, which is what its name claims. NOTE: the cycle-4 structural defect (monkeypatch firing during staging writes) IS genuinely fixed by the `_commit_staging` boundary extraction — only the recovery test's observable claim remains flawed. Orchestrator-verified against 06-02-PLAN.md:290-359 and normalizer.py:643-653.
