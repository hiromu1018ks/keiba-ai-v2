---
phase: 06-data-integration
reviewers: [codex]
reviewed_at: 2026-06-14T20:55:00+09:00
plans_reviewed:
  - 06-01-PLAN.md
  - 06-02-PLAN.md
  - 06-03-PLAN.md
cycle: 4
prior_cycle_high: 5
---

# Cross-AI Plan Review — Phase 6 (Cycle 4 — FINAL convergence)

Cycle-4 re-review. The three PLAN.md files were replanned (git commits `c818eda` +
`c1e26b9`) to address the 5 HIGHs that remained unresolved after cycle 3. Codex
(gpt-5.5 via `codex exec`, codex-cli 0.139.0) re-reviewed the revised plans with
repository read access (workdir: `/Users/hart/develop/keiba-ai-v2`, sandbox granted
`disk-full-read-access` + `git-read-access`). The orchestrator then independently
re-verified every load-bearing claim Codex raised against the working tree before
recording the adjudication below.

**Headline:** of the 5 cycle-3 HIGHs, **2 are FULLY RESOLVED** (#2 source_stats unified,
#11 zero-tolerance gate), **1 is PARTIALLY RESOLVED** (#14 floor — improved to
`'2026-01-01'` but does not honor D-07's month-level contract through 2026-05), and the
2 cycle-3 NEW HIGHs (#06-02 mismatch-as-soft, #06-02 transactionality) have **correct
mitigations but flawed regression tests** — the production code fix is sound, but the
tests do not isolate the failure path they claim to prove. Net result: **3 HIGH remain
unresolved** (trend 14 → 7 → 5 → 3, still decreasing).

Codex raised **3 NEW HIGH defects**:

1. **06-02 NEW HIGH — `mismatch` regression test passes via the `duplicate` path.** The
   proposed test data (entry 1 row "X", result 2 rows "X") triggers BOTH a `duplicate
   horse_race_id` violation (`normalizer.py:301-307`) AND the `mismatch` violation
   (`normalizer.py:320-336`). Because the hard-violation filter checks `"duplicate"`
   first, removing `"mismatch"` from the token set would leave the test still passing
   via `duplicate`. The mitigation itself (adding `"mismatch"` to the filter) is
   CORRECT and will protect production — but the regression test does not prove the
   `mismatch` token is what catches the 1-to-1-only case. Orchestrator-verified against
   `normalizer.py:301-336`.
2. **06-02 NEW HIGH — mid-swap monkeypatch fires during staging write, not swap.**
   `_atomic_write_parquet` (`normalizer.py:643-653`) also calls `os.replace`, and
   `normalizer.os` is the SAME module object as `integration.os` (both do `import os`).
   The plan writes 3 staging files via `_atomic_write_parquet` BEFORE the 3-call swap
   loop, so the 2nd `os.replace` call fires during the 2nd staging write — the test
   never reaches the swap loop it claims to test. Orchestrator-verified against
   `normalizer.py:643-653` and `06-02-PLAN.md:246-248`.
3. **06-03 NEW HIGH — D-07 month-level completeness not guaranteed.** `EXPECTED_FLOOR =
   '2026-01-01'` only proves the scrape reached into 2026, not that it reached 2026-05
   per D-07's LOCKED scope "2022年1月〜2026年5月末" (`06-CONTEXT.md:45`). Separately,
   the preflight gate `>= 40` partitions does not detect missing months between
   2022-01 and 2026-05 (53 months expected; JRA runs year-round so there are no
   legitimate off-months). Orchestrator-verified against `06-CONTEXT.md:45` and
   `06-03-PLAN.md:100-172`.

All 3 new HIGHs have one-line (or few-line) fixes. The convergence trend is monotonic
(14 → 7 → 5 → 3), and the production-code mitigations are correct on the 2 cycle-3 NEW
HIGHs — only the tests and the floor-strictness need patching. This is documented so a
targeted cycle-5 patch (or in-execution fix) can close them without another full review.

---

## Codex Review

### Plan 06-01 Review

**Summary**

Cycle-4のgrade検出順序、`G1` 正規表現マッチ、`race_condition=' '` によるearly-return
bypass、odds/payoff完全非書き込み、core_tables_subdirリダイレクトは、いずれも実ソース
(`kaggle_converter.py:36-44,82-90,244-278` / `flag_crosswalk.py:124-130,184-185` /
`normalizer.py:95-192,643-653`) と整合している。06-01はcycle-3の5件HIGHを直接解決する
計画ではないが、06-02/06-03の前提としては十分。

### Cycle-3 HIGH Adjudication (06-01)

06-01はcycle-3の5件HIGHを直接解決を主張していない（それらは06-02/06-03側）。関連する前提は妥当:

- `_UNMAPPED_RACE_FLAGS` に `race_flag_listed`/`race_flag_stakes` が含まれ、後から `pd.NA` で追加される (`kaggle_converter.py:36-44,250-252`)
- `derive_race_flags()` は空文字で早期returnする (`flag_crosswalk.py:184-185`)
- `G1` (半角) は `_GRADE_REGEX` の `G3|G2|G1` にマッチする (`flag_crosswalk.py:124-130`)
- `race_date` の正規dtypeは `string` (`normalizer.py:99`)

### New Concerns (06-01)

- **MEDIUM — Task 3のdtype検証が記述どおりではない。** 計画本文 (`06-01-PLAN.md:236`) は `win_odds` が `double` であることも検証すると記述しているが、提示されたPython検証コード (`06-01-PLAN.md:266-276`) は `race` テーブルの `race_flag_*`/`race_date`/`distance` だけを確認し、`entry.win_odds`/`entry.horse_weight` を検証していない。Orchestrator-verified: verify.automatedブロックに `win_odds` assertionなし。
- **LOW — subdir指定時もodds CSVを読み、変換する。** 現在の `convert()` 処理順ではodds抽出 (`kaggle_converter.py:96-101`) が書込み判定より前。非書込み要件には違反しないが、22MB CSVの不要な読込みと変換が発生する。

### Suggestions (06-01)

- Task 3 verifyブロックに `entry.win_odds` (double), `entry.horse_weight` (double), `result.last_3f` のArrow dtype assertionを追加する。
- `core_tables_subdir is not None` の場合はodds CSVの読込み・抽出自体をスキップする（性能改善、任意）。

**Risk Assessment: LOW.** 実装の主要方針はコードに適合している。残件は検証範囲の拡充と
性能上の最適化のみ。

---

### Plan 06-02 Review

**Summary**

`mismatch` をハード違反へ追加する実装方針自体は正しい（`normalizer.py:330-334` の違反文字列に
`mismatch`/`1-to-1` があり、`duplicate`/`orphan` はない）。validate-before-swap +
idempotent recoveryモデルも妥当。しかし、その2つの回帰テストはどちらも意図した経路を証明
できない。

### Cycle-3 HIGH Adjudication (06-02)

| # | Verdict | Orchestrator-Verified Evidence |
|---|---------|--------------------------------|
| #6 (corpus transactionality) | **PARTIALLY RESOLVED** | Mitigation design (validate-before-swap via `tempfile.mkdtemp` staging + idempotent recovery) is CORRECT and the model is accurately described as NOT perfect atomicity. The 3 staging writes (`_atomic_write_parquet`, normalizer.py:643-653) + 3 swap `os.replace` calls is a real validate-before-swap flow. The recovery guarantee (reads only from immutable inputs `data/standard/kaggle/` + scraped partitions) is genuine. BUT the cycle-4 strengthened test does not prove recovery from a mid-SWAP failure — see NEW HIGH #2 below. |
| #5 (idempotency) | **RESOLVED** (carried, KEPT) | Separate `kaggle_input_dir`; idempotency test present. |
| #7 (autouse skip) | **RESOLVED** (carried, KEPT) | Two-class split. |
| #8 (FK orphan raises) | **RESOLVED** (carried, KEPT) | Orphan injection + `validate_integrity` + ValueError. |
| #8b (horse_race_id mismatch RAISES) | **PARTIALLY RESOLVED** | The PRODUCTION-CODE mitigation is CORRECT: extending the hard-violation filter to `"duplicate" in v or "orphan" in v or "mismatch" in v or "1-to-1" in v` (`06-02-PLAN.md:230-240`) genuinely catches the `"horse_race_id mismatch: entry/result are not 1-to-1"` violation string (`normalizer.py:330-334`), because that string contains `"mismatch"` and `"1-to-1"` but NEITHER `"duplicate"` NOR `"orphan"`. Verified at `normalizer.py:330-336`. A structurally inconsistent entry/result corpus will now RAISE in production. HOWEVER the regression test `test_horse_race_id_mismatch_raises` does not isolate the `mismatch` path — see NEW HIGH #1 below. |
| #9 (column-set equality) | **RESOLVED** (carried, KEPT) | `_assert_column_set_equality` before reindex. |

### New Concerns (06-02)

- **HIGH — `mismatch` regression test passes via the `duplicate` path.** The proposed test data (`06-02-PLAN.md:182,254`) is entry 1 row with horse_race_id "X", result 2 rows BOTH with horse_race_id "X". With this data, `validate_integrity` returns violations containing BOTH: (a) `"duplicate horse_race_id: 1 duplicated rows in result table"` (from check (c) at `normalizer.py:301-307` — result has 2 rows with the same id, so `duplicated().sum() == 1`); AND (b) `"horse_race_id mismatch: entry/result are not 1-to-1 (..., count-mismatch={'X': (1, 2)})"` (from check (d) at `normalizer.py:320-336` — `Counter({"X":1}) != Counter({"X":2})`). Because the hard-violation filter iterates the violations list and checks `"duplicate"` first, the test PASSES even if `"mismatch"` were removed from the token set. The test does not prove the `"mismatch"` token is load-bearing for the 1-to-1-only case (where entry and result have DIFFERENT keys, not duplicates). Orchestrator-verified against `normalizer.py:293-336` and `06-02-PLAN.md:182,230-240`.
- **HIGH — mid-swap monkeypatch fires during staging write, not swap.** The plan's swap design (`06-02-PLAN.md:246-248`) is: (1) write all 3 merged frames to staging via `_atomic_write_parquet(merged, staging_dir / f"{table}.parquet")` — 3 calls to `os.replace` (one per file, inside `_atomic_write_parquet` at `normalizer.py:653`); (2) validate staged files; (3) swap each into root via `os.replace(staging_dir / f"{table}.parquet", standard_dir / f"{table}.parquet")` — 3 more `os.replace` calls. `normalizer.py` does `import os` (`normalizer.py:67`) and the plan instructs `integration.py` to also `import os` — so `normalizer.os` and `integration.os` reference the SAME module object. The test's `monkeypatch.setattr(integration_mod.os, "replace", failing_replace)` (`06-02-PLAN.md:276`) patches that shared module, so the "2nd call" counter increments during the 2nd STAGING write (which happens before the swap loop). The test fires during staging, never reaches the swap loop, and does not prove recovery from a mid-SWAP failure — exactly the failure mode Codex flagged in cycle 2. Additionally, because a clean re-run from identical inputs produces byte-identical output, the assertion `post != canonical` is vacuously misleading (if the integration raised during staging, the canonical files were never overwritten, so `post == canonical`). Orchestrator-verified against `normalizer.py:67,643-653` and `06-02-PLAN.md:246-248,268-297`.
- **MEDIUM — Return-type annotation inaccurate.** `integrate_standard_layer(...) -> dict[str, Path]` but the return includes `{"audit": {...}}` (a dict, not a Path). Should be `dict[str, Path | dict]` or a TypedDict. (Carried from cycle 3, not yet fixed.)

### Suggestions (06-02)

- **One-line fix for NEW HIGH #1:** change the `test_horse_race_id_mismatch_raises` test data so entry and result have DIFFERENT keys (no duplicates in either table) — e.g. entry has 1 row with horse_race_id "X", result has 1 row with horse_race_id "Y". Then `Counter(entry)={"X":1}` and `Counter(result)={"Y":1}`, so check (c) finds NO duplicates (passes), and check (d) returns ONLY the `"horse_race_id mismatch: entry/result are not 1-to-1 (only-in-entry=1, only-in-result=1, count-mismatch={})"` violation. BEFORE asserting `integrate_standard_layer` raises, assert `validate_integrity(...)` returns a list whose ONLY entry contains `"mismatch"` (proving the `mismatch` token is the load-bearing classifier).
- **Few-line fix for NEW HIGH #2:** extract the swap loop into a dedicated function `_swap_staged_files(staging_dir, standard_dir)` that calls `os.replace` directly (not via `_atomic_write_parquet`), and patch ONLY that function (e.g. `monkeypatch.setattr("src.pipeline.integration._swap_staged_files", failing_swap)`), OR use a counter that skips the first N calls (where N = number of staging writes). Additionally, to make the mixed-generation observable, mutate an input between the clean run and the failing run (e.g. add a row to a scraped partition) so the "new generation" produces a different SHA-256 than the canonical — then the assertion `post != canonical` is meaningful.
- Fix the return-type annotation (carried MEDIUM).

**Risk Assessment: HIGH.** Production-code mitigations are correct on both cycle-3 NEW HIGHs, but
the two load-bearing regression tests do not prove what they claim. A structurally inconsistent
entry/result corpus WILL now raise in production (the filter extension is genuine), but the test
suite would pass even if the `"mismatch"` token were accidentally removed — a false sense of
regression coverage. The mid-swap test fires at the wrong stage.

---

### Plan 06-03 Review

**Summary**

unified source_stats (cycle-4) と ゼロ許容preflightは妥当で実行可能。一方、
`EXPECTED_FLOOR='2026-01-01'` はD-07の「2026年5月末まで」を保証せず、preflightも
月次完全性（欠落月検出）を行わない。結果として、完全でないD-06 corpusを受理できる。

### Cycle-3 HIGH Adjudication (06-03)

| # | Verdict | Orchestrator-Verified Evidence |
|---|---------|--------------------------------|
| #11 (preflight gate strictness) | **RESOLVED** | The cycle-4 gate `if len(invalid) > 0: sys.exit(1)` (`06-03-PLAN.md:168-170`) fails on ANY invalid partition (missing file, `num_rows == 0` in any of the 3 tables, or race_date mismatch). This correctly honors the prose contract "non-emptiness for ALL THREE". A single empty `entry.parquet` no longer passes. The cycle-3 silent-pass bug (swallowed exception + unasserted `n`) remains fixed (exceptions re-raised at `06-03-PLAN.md:148-149,157-158`). Verified at `06-03-PLAN.md:124-172`. NOTE: the gate validates PRESENT partitions only — it does not detect MISSING months (see NEW HIGH #3 below); that is a separate concern from the #11 gate-strictness defect, which is genuinely resolved. |
| #14 (EXPECTED_FLOOR) | **PARTIALLY RESOLVED** | The cycle-4 floor `EXPECTED_FLOOR = '2026-01-01'` (`06-03-PLAN.md:332`) is a genuine improvement over cycle-3's `'2024-01-01'` — a scrape stopping at 2025-12 now FAILS. The triple assertion (`dmax == actual_scraped_max` AND `actual_scraped_max >= '2026-01-01'` AND `dmin in 2015-Q1`) is structurally correct. HOWEVER the floor does not honor the full D-07 contract (`06-CONTEXT.md:45`: "実データ全部（2015-2026/5）" / Phase 4 D-05 design "2022年1月〜2026年5月末"). A scrape reaching 2026-02 passes `>= '2026-01-01'` but violates D-07's "through 2026年5月末". Combined with the per-year `> 500 races` check (which passes if 2026 has > 500 races from Jan+Feb alone), a scrape stopping at 2026-02 can pass all gates. See NEW HIGH #3. |
| #2 (source_stats Kaggle-only) | **RESOLVED** | The cycle-4 fix (`06-03-PLAN.md:200-207,268-298`) computes `source_stats` AND `source_counts` from the UNIFIED frames `urace = pd.concat([krace, srace])` / `uentry = pd.concat([kentry, sentry])` — the SAME Kaggle + scraped inputs that integration writes. Because `validate_distributions` (`validators.py:283-345`) reads `parquet_dir / f"{table}.parquet"` (the unified output) and compares min/max/mean with `tolerance=0.01` absolute, comparing identical-corpus stats passes within tolerance. Same for `validate_null_rates` (`validators.py:227-276`). `dist_pass = True`, `null_pass = True`, `overall_pass = True`. The cycle-3 runtime-FAIL defect is genuinely fixed. Orchestrator-verified against `validators.py:227-345,800-865` and `06-03-PLAN.md:268-298`. |
| NEW PK-set union (race-only) | **RESOLVED** (carried, KEPT) | Verify block iterates all 3 tables; entry/result PK drift caught. |
| #3 (8-point relocation) | **RESOLVED** | The FULL 8-point `run_all_validations` now runs here against `data/standard/` root (5 tables coexist) AND passes execution because source_stats is unified (cycle-4 fix to #2). The phase-level #3 resolution (which depended on #2 in cycle 3) is now complete. |
| #15 (halt-on-smoke-only) | **RESOLVED** (carried, KEPT) | `< 40` partitions → exit 1. |
| #16 (per-partition 3-file presence + race_date) | **RESOLVED** (carried, KEPT) | modulo the NEW HIGH #3 missing-month gap. |
| #17 (odds/payoff SHA-256) | **RESOLVED** (carried, KEPT) | Pre/post SHA-256 + row count in verify.automated. |
| #18 (per-period graded) | **RESOLVED** (carried, KEPT) | Per-period derive_race_flags comparison. |

### New Concerns (06-03)

- **HIGH — D-07 month-level completeness not guaranteed (two sub-defects).** (a) Floor too weak: `EXPECTED_FLOOR = '2026-01-01'` (`06-03-PLAN.md:332`) only proves the scrape reached into calendar year 2026, not that it reached May 2026 per D-07's LOCKED scope (`06-CONTEXT.md:45`: "2022年1月〜2026年5月末"). A scrape stopping at 2026-02-28 passes the floor (`2026-02-28 >= 2026-01-01`) and the per-year `> 500 races` check (Jan+Feb 2026 JRA races easily exceed 500), yet violates D-07. (b) No missing-month detection: the preflight gate `if len(dirs) < 40` (`06-03-PLAN.md:134`) counts PRESENT partitions but does not verify WHICH months are present. From 2022-01 to 2026-05 is 53 months; if 13 months are entirely missing (e.g. all of 2024-Q3 + scattered months) but 40+ remain, the gate passes. JRA runs year-round (中央競馬 has meetings every month), so there are no legitimate off-months to tolerate. Orchestrator-verified against `06-CONTEXT.md:45`, `06-03-PLAN.md:100-172,314-339`, and the ROADMAP (Phase 4 D-05 design target 2022-01〜2026-05).
- **MEDIUM — `validate_sample_rows` provides weak coverage for scraped-origin rows.** When a parquet row's key (race_id) is not found in the Kaggle CSV source, `validate_sample_rows` `continue`s and treats it as "filtered out, OK" (`validators.py:570-576`). Since scraped rows have race_ids absent from the Kaggle CSV, they are skipped rather than validated against a source. The 8-point `sample_rows` check therefore effectively validates only Kaggle-origin rows in the unified corpus. This is a coverage gap, not a correctness defect — the per-table PK-set union check (NEW HIGH cycle-3, RESOLVED) and the per-partition preflight already cover scraped integrity. Orchestrator-verified against `validators.py:565-576`.

### Suggestions (06-03)

- **One-line fix for NEW HIGH #3 (floor):** strengthen `EXPECTED_FLOOR` to require reaching at least May 2026: `EXPECTED_FLOOR = '2026-05-01'` (honors D-07's "2026年5月末" — a scrape stopping at 2026-04 fails). Optionally also assert the `202605` partition exists: `assert (Path('data/standard/scraped/202605') / 'race.parquet').exists()`. Document that D-07's exact last-race-day (e.g. last JRA meeting before 2026-06) is verified in Phase 9 backtest planning.
- **Few-line fix for NEW HIGH #3 (missing months):** add an expected-months set check to the preflight:
  ```python
  expected = pd.period_range("2022-01", "2026-05", freq="M").strftime("%Y%m")
  present = {d.name for d in dirs}
  missing = sorted(set(expected) - present)
  if missing:
      print(f"BLOCKING: missing scraped months per D-07: {missing}"); sys.exit(1)
  ```
  (Drop the `>= 40` count gate, or keep it as a redundant sanity check below the strict set check.)
- Optional: add a scraped-specific sample validation (compare a sample of scraped rows against the scraped raw HTML partition source) to close the `validate_sample_rows` MEDIUM.

**Risk Assessment: HIGH.** source_stats unified and zero-tolerance gate are genuine resolutions,
but the D-07 month-level completeness is not enforced — an incomplete scrape (stopping at 2026-02, or
missing 13 scattered months) can pass all gates and produce a corpus that silently violates the
LOCKED scope. Since D-07 is the contract that takes precedence over ROADMAP text, this is a real
coverage gap the EV downstream (Phase 9 backtest over 2015-2026/5) depends on.

---

## Consensus Summary

Single-reviewer cycle (Codex / gpt-5.5). The orchestrator independently verified every
load-bearing claim Codex raised against the working tree — all corroborated (see inline
"Orchestrator-Verified Evidence" in each adjudication row). No divergent views.

### Resolved cycle-3 HIGHs (2 — counted out)

- **#2 source_stats Kaggle-only** — `source_stats` AND `source_counts` now computed from UNIFIED `urace`/`uentry` (Kaggle + scraped combined); `validate_distributions`/`validate_null_rates` compare identical-corpus data → within tolerance → `overall_pass=True`. The cycle-3 runtime-FAIL is genuinely fixed.
- **#11 preflight gate strictness** — `if len(invalid) > 0: sys.exit(1)` (zero-tolerance); exceptions re-raised; the cycle-2 silent-pass bug remains fixed.

### Unresolved HIGHs (3 — carried forward)

1. **[06-02, NEW HIGH] `mismatch` regression test passes via the `duplicate` path.** The proposed test data (entry 1 row "X", result 2 rows "X") triggers BOTH a `duplicate horse_race_id` violation (`normalizer.py:301-307`) AND the `mismatch` violation (`normalizer.py:320-336`). The hard-violation filter checks `"duplicate"` first, so the test passes even if `"mismatch"` were removed. The PRODUCTION-CODE mitigation (extending the filter with `"mismatch"`/`"1-to-1"`) is CORRECT and will protect the unified corpus — but the regression test does not prove the `"mismatch"` token is load-bearing. Orchestrator-verified against `normalizer.py:293-336` and `06-02-PLAN.md:182,230-240`.
2. **[06-02, NEW HIGH] Mid-swap monkeypatch fires during staging write, not swap.** `_atomic_write_parquet` (`normalizer.py:643-653`) also calls `os.replace`, and `normalizer.os` == `integration.os` (same module object via `import os`). The plan writes 3 staging files via `_atomic_write_parquet` BEFORE the 3-call swap loop (`06-02-PLAN.md:246-248`), so the 2nd `os.replace` call fires during the 2nd staging write — the test never reaches the swap loop. Additionally, a clean re-run from identical inputs produces byte-identical output, so `post != canonical` is vacuously misleading. The validate-before-swap + idempotent recovery DESIGN is sound; the TEST does not prove it. Orchestrator-verified against `normalizer.py:67,643-653` and `06-02-PLAN.md:246-297`.
3. **[06-03, NEW HIGH] D-07 month-level completeness not guaranteed (floor too weak + no missing-month detection).** (a) `EXPECTED_FLOOR = '2026-01-01'` (`06-03-PLAN.md:332`) only proves the scrape reached into 2026, not May 2026 per D-07 (`06-CONTEXT.md:45`: "2022年1月〜2026年5月末"). A scrape stopping at 2026-02 passes. (b) The preflight `>= 40` partitions (`06-03-PLAN.md:134`) counts PRESENT partitions but does not detect missing months between 2022-01 and 2026-05 (53 expected; JRA runs year-round so no legitimate off-months). Orchestrator-verified against `06-CONTEXT.md:45` and `06-03-PLAN.md:100-172,314-339`.

### Divergent Views

Single reviewer — no divergence. Orchestrator source verification corroborates all
load-bearing claims rather than contradicting.

### Recommended next actions (targeted patches — cycle 5)

All 3 unresolved HIGHs have one-line or few-line fixes. They can be applied via a targeted
patch commit rather than another full convergence cycle:

1. **06-02 `mismatch` test isolation (NEW HIGH #1):** change `test_horse_race_id_mismatch_raises`
   test data to entry 1 row "X", result 1 row "Y" (different keys, no duplicates in either
   table). Then `validate_integrity` returns ONLY the `mismatch` violation (check (c) finds no
   duplicates). BEFORE asserting `integrate_standard_layer` raises, assert `validate_integrity(...)`
   returns a list whose ONLY entry contains `"mismatch"` (proving the token is load-bearing).
2. **06-02 mid-swap test isolation (NEW HIGH #2):** extract the swap loop into a dedicated
   function `_swap_staged_files(staging_dir, standard_dir)` and patch ONLY that function (so the
   counter applies to swap calls, not staging writes). Alternatively, skip the first N calls where
   N = number of staging writes. To make the mixed-generation observable, mutate an input between
   the clean run and the failing run (add a row to a scraped partition) so the new generation
   produces a different SHA-256 than canonical — then `post != canonical` is meaningful.
3. **06-03 D-07 floor + missing months (NEW HIGH #3):** (a) change `EXPECTED_FLOOR = '2026-01-01'`
   to `EXPECTED_FLOOR = '2026-05-01'` and optionally assert the `202605` partition exists; (b) add
   an expected-months set check to the preflight: `expected = pd.period_range("2022-01", "2026-05",
   freq="M").strftime("%Y%m"); missing = sorted(set(expected) - {d.name for d in dirs}); assert not
   missing`.

After these 3 patches, the phase should reach 0 HIGHs.

---

## CYCLE_SUMMARY

CYCLE_SUMMARY: current_high=3

## Current HIGH Concerns

- **[06-02, NEW HIGH] `mismatch` regression test passes via the `duplicate` path** — the proposed test data (entry 1 row "X", result 2 rows "X") triggers BOTH a `duplicate horse_race_id` violation (`normalizer.py:301-307`) AND the `mismatch` violation (`normalizer.py:320-336`); the hard-violation filter checks `"duplicate"` first, so the test passes even if `"mismatch"` were removed from the token set. The PRODUCTION-CODE mitigation (filter extension with `"mismatch"`/`"1-to-1"`) is CORRECT — but the regression test does not prove the `"mismatch"` token is load-bearing for the 1-to-1-only case. Orchestrator-verified against `normalizer.py:293-336` and `06-02-PLAN.md:182,230-240`.
- **[06-02, NEW HIGH] Mid-swap monkeypatch fires during staging write, not swap** — `_atomic_write_parquet` (`normalizer.py:643-653`) also calls `os.replace`, and `normalizer.os` == `integration.os` (same module object via `import os`); the plan writes 3 staging files via `_atomic_write_parquet` BEFORE the 3-call swap loop (`06-02-PLAN.md:246-248`), so the 2nd `os.replace` call fires during the 2nd staging write — the test never reaches the swap loop it claims to test. The validate-before-swap + idempotent recovery DESIGN is sound; the TEST does not prove it. Orchestrator-verified against `normalizer.py:67,643-653` and `06-02-PLAN.md:246-297`.
- **[06-03, NEW HIGH] D-07 month-level completeness not guaranteed (floor too weak + no missing-month detection)** — (a) `EXPECTED_FLOOR = '2026-01-01'` (`06-03-PLAN.md:332`) only proves the scrape reached into 2026, not May 2026 per D-07 (`06-CONTEXT.md:45`: "2022年1月〜2026年5月末"); a scrape stopping at 2026-02 passes. (b) The preflight `>= 40` partitions (`06-03-PLAN.md:134`) counts PRESENT partitions but does not detect missing months between 2022-01 and 2026-05 (53 expected; JRA runs year-round so no legitimate off-months). Orchestrator-verified against `06-CONTEXT.md:45` and `06-03-PLAN.md:100-172,314-339`.
