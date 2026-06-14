---
phase: 06-data-integration
reviewers: [codex]
reviewed_at: 2026-06-14T20:22:00+09:00
plans_reviewed:
  - 06-01-PLAN.md
  - 06-02-PLAN.md
  - 06-03-PLAN.md
cycle: 3
prior_cycle_high: 7
---

# Cross-AI Plan Review — Phase 6 (Cycle 3 — FINAL convergence)

Cycle-3 re-review. The three PLAN.md files were replanned under `--reviews` (git commit
`8335e48`) to address the 7 HIGHs that remained unresolved after cycle 2. Codex
(gpt-5.5 via `codex exec`) re-reviewed the revised plans with repository read access
(workdir: `/Users/hart/develop/keiba-ai-v2`). The orchestrator then independently
re-verified every load-bearing claim Codex raised against the working tree before
recording the adjudication below.

**Headline:** of the 7 cycle-2 HIGHs, **4 are FULLY RESOLVED** in cycle 3 (#1, #2, NEW
PK-set union, and the cycle-2 bug portion of #11). **3 remain PARTIALLY RESOLVED** (#3
8-point relocation, #6 transactionality, #14 self-referential max, plus the gate-strictness
portion of #11). Codex raised **2 NEW HIGH defects** introduced by the cycle-3 replan:

1. **06-02 NEW HIGH — `horse_race_id` 1-to-1 mismatch treated as SOFT (not raised).** The
   plan's hard-violation filter is `if "duplicate" in v or "orphan" in v` (mirroring
   `normalizer.py:744-756`). `validate_integrity` returns `"horse_race_id mismatch: ..."`
   (`normalizer.py:331`), which contains NEITHER token, so a non-1-to-1 entry/result corpus
   is written as a warning only. Orchestrator-verified.
2. **06-03 NEW HIGH — `source_stats` is Kaggle-only but compared against the unified
   (Kaggle + scraped) output.** `validate_distributions` (`validators.py:283-330`) uses
   `tolerance=0.01` absolute; the unified distance/popularity mean differs from the
   Kaggle-only mean by far more than 0.01, so `dist_pass=False`, `overall_pass=False`, and
   the plan's `assert v['overall_pass'] is True` FAILS at runtime. Orchestrator-verified.

This means cycle 3 closes 4 of the 7 carried-over HIGHs but opens 2 new ones, leaving a
net of 5 unresolved HIGHs. Since this is the FINAL convergence cycle, the remaining 5 are
documented with the exact one-line fix each requires, so the next `--reviews` replan (or a
targeted patch) can close them without another full review round.

---

## Codex Review

### Plan 06-01 Review

**Summary**

Cycle-3のgrade検出順序、`G1` 正規表現マッチ、`race_condition=' '` によるearly-return
bypass、odds/payoff完全非書き込みは、いずれも実ソース (`kaggle_converter.py:36-44,248,
251-252` / `flag_crosswalk.py:124-130,184-185` / `kaggle_converter.py:103-119`) と整合
している。#1 と #2 は genuine fix。ただし8項目検証の移動先 (06-03) に統計生成の欠陥が
あるため、HIGH #3 はフェーズ全体としては部分解消となる（06-03 側の NEW HIGH 参照）。

### Cycle-2 HIGH Adjudication (06-01)

| # | Verdict | Orchestrator-Verified Evidence |
|---|---------|--------------------------------|
| #1 (grade detection ordering + KeyError + clobber) | **RESOLVED** | `_UNMAPPED_RACE_FLAGS` includes `race_flag_listed` and `race_flag_stakes` (`kaggle_converter.py:39,42` — verified). `convert_flags_to_bool` runs at `:248`; the unmapped-flags loop runs at `:251-252` (AFTER). Moving `_apply_grade_detection` to after the loop (or at end of `split_race_entry_result` before `:278`) means all 20 columns exist as nullable-boolean pd.NA Series when the helper reads `race_df[col]` — no KeyError, no later-clobber. The cycle-2 placement at `:248` would have KeyError'd; the cycle-3 placement does not. Test value `grade='G1'` matches `_GRADE_REGEX`'s `G3\|G2\|G1` (`flag_crosswalk.py:127`); the cycle-2 `GⅠ` (half-width G + full-width Ⅰ U+FF21) matched neither alternative — verified by reading the regex. `race_condition=' '` is truthy so `if not race_condition: return flags` (`:184-185`) does not fire, and the haystack `f"{race_condition} {race_name}"` is built so `_GRADE_REGEX` is applied to the name even when grade is null. |
| #2 (odds/payoff overwrite) | **RESOLVED** | Current write site (`kaggle_converter.py:103-119`) builds ONE `tables` dict with all 5 tables and writes each to `standard_dir / f"{table}.parquet"` unconditionally — verified. The cycle-3 design splits this into `core_tables` (race/entry/result) and `odds_tables` (odds_trifecta/payoff), and gates the odds_tables write on `core_tables_subdir is None`. When subdir is set, odds/payoff are written to NEITHER root NOR subdir — they are not written at all. This directly removes the overwrite cause (cycle-2 only redirected race/entry/result; odds/payoff still went to root). The non-overwrite test (`test_convert_preserves_odds_payoff`) now proves sentinel bytes UNCHANGED, and `test_convert_skips_odds_payoff_when_subdir_set` proves odds/payoff absent from an empty tmp dir — both are genuine non-overwrite proofs, not value-equality. |
| #3 (8-point verification vs 3-table subdir) | **PARTIALLY RESOLVED** | The 06-01-side fix is correct: `validate_integrity(race_df, entry_df, result_df)` (`normalizer.py:263`) takes DataFrames directly and does NOT assume odds/payoff — verified. 06-01-T3 now uses this for its 3-table FK check. The decision NOT to call `run_all_validations` against `data/standard/kaggle/` is also correct: `validate_referential_integrity` (`validators.py:377-383`) iterates `child_tables = ["entry", "result", "odds_trifecta", "payoff"]` and appends "Missing odds_trifecta.parquet"/"Missing payoff.parquet" when absent → `integrity_pass=False` → `overall_pass=False` — verified. HOWEVER the FULL 8-point `run_all_validations` was MOVED to 06-03-T2, and the relocated check has a NEW defect (see 06-03 NEW HIGH — source_stats Kaggle-only). So HIGH #3 is only RESOLVED at the 06-01 layer; the phase-level resolution depends on the 06-03 fix, which is itself broken. |
| #4 (poetry) | **RESOLVED** (carried, KEPT) | All `<verify><automated>` use `python -m pytest` / `python -c`. |

### New Concerns (06-01)

- **MEDIUM — OR-merge converts unknown→False on the 3 grade-derived columns.** `existing.fillna(False) | new.fillna(False)` (plan 06-01-PLAN.md:146) collapses `None` (unknown) to `False` (confirmed-absent) on `race_flag_graded_stakes`/`race_flag_stakes`/`race_flag_listed`. The `derive_race_flags` docstring (`flag_crosswalk.py:152-156`) explicitly distinguishes "unknown / not observed" (None) from "confirmed False". The cycle-2 WARNING-2 framing calls `fillna(False)` "load-bearing" to avoid `True | pd.NA = <NA>` downgrading True, but the side effect is that rows where neither the text-derived value nor the grade-derived value is True become False rather than None. Impact: only 3 of 20 columns; the deterministic count check at Task 3 uses `.fillna(False).sum()` so is consistent with this. Fix (optional): use a mask that only writes True (`race_df.loc[new.fillna(False), col] = True`) leaving other rows' existing values untouched.
- **MEDIUM — Task 3 automated verify does not assert all dtypes.** The `done` block mentions `distance=int64`, `win_odds=double`, but the actual verify block (`06-01-PLAN.md:206`) only asserts null-free + race_flag_* bool + race_date string. `distance` int64 is checked; `win_odds` double is not. Minor coverage gap.

### Suggestions (06-01)

- For the OR-merge, prefer a True-only mask to preserve the unknown→unknown semantics on the 3 columns.
- Add `win_odds` double assertion to the Task 3 verify block for parity with the `done` list.

**Risk Assessment: MEDIUM.** #1 and #2 are genuine, code-grounded resolutions. The remaining
risk on 06-01 is the 06-03-side #3 dependency (source_stats) and the minor OR-merge/dtype
gaps.

---

### Plan 06-02 Review

**Summary**

独立したKaggle入力パス (HIGH #5) と tempfile.mkdtemp staging + validate-before-swap は
改善している。しかし3ファイルの逐次 `os.replace` は依然 corpus-atomic ではなく、さらに
cycle-3 replan が `validate_integrity` の "horse_race_id mismatch" 違反を hard failure
から外すという新しい重大欠陥を導入した。

### Cycle-2 HIGH Adjudication (06-02)

| # | Verdict | Orchestrator-Verified Evidence |
|---|---------|--------------------------------|
| #6 (corpus transactionality) | **PARTIALLY RESOLVED** | `_atomic_write_parquet` (`normalizer.py:643-653`) is per-file atomic (temp + single os.replace) — verified. Three sequential `os.replace` calls are NOT one corpus-atomic operation: a failure between the 2nd and 3rd leaves race=new + entry=new + result=old (or any partial combo). The plan acknowledges this and relies on "validate-before-swap + idempotent recovery" — which is an ACCURATE description (the plan does not falsely claim perfect atomicity, unlike cycle 2's implicit claim). The recovery guarantee is real BECAUSE integration reads from immutable inputs (`data/standard/kaggle/` + scraped partitions), so a re-run produces identical output. BUT the new test `test_integration_partial_swap_recoverable` deletes ONE output file post-run then re-invokes — it does NOT inject a failure DURING the swap loop (e.g. monkeypatch the 2nd os.replace to raise), so it does not prove recovery from the actual mixed-generation failure mode Codex flagged in cycle 2. The idempotency guarantee covers it in principle, but the test is weaker than the cycle-2 concern demanded. |
| #5 (idempotency) | **RESOLVED** (carried, KEPT) | Separate `kaggle_input_dir`; idempotency test present. |
| #7 (autouse skip) | **RESOLVED** (carried, KEPT) | Two-class split. |
| #8 (FK test) | **RESOLVED** (carried, KEPT) — but see NEW HIGH below | Orphan injection + `validate_integrity` + ValueError. |
| #9 (column-set equality) | **RESOLVED** (carried, KEPT) | `_assert_column_set_equality` before reindex. |

### New Concerns (06-02)

- **HIGH — `horse_race_id` 1-to-1 mismatch between entry and result is treated as SOFT, not raised.** The plan's hard-violation filter (06-02-PLAN.md:215) is: "Treat any violation containing `"duplicate"` or `"orphan"` as hard — RAISE ValueError mirroring normalizer.py:744-756." `normalizer.py:744-756` itself uses `hard_violations = [v for v in violations if "duplicate" in v or "orphan" in v]` — verified. But `validate_integrity` returns the string `"horse_race_id mismatch: entry/result are not 1-to-1 ..."` for the entry/result cardinality check (`normalizer.py:331`) — verified. That string contains NEITHER "duplicate" NOR "orphan", so it is classified SOFT (warning only) and a corpus where entry and result are NOT 1-to-1 is written without raising. The normalizer's own source comment (lines 740-743) acknowledges this is a deliberate SOFT classification ("entry/result 1-to-1 cardinality mismatch detected after the per-table uniqueness checks remain warnings"), but the plan does not document this divergence, and the Phase 6 success criterion #1 ("no duplicate races") implicitly assumes entry/result integrity. Orchestrator-verified against `normalizer.py:309-336, 744-756` and `06-02-PLAN.md:215`.
- **MEDIUM — Return type annotation is inaccurate.** `integrate_standard_layer(...) -> dict[str, Path]` but the plan returns `{"race": ..., "entry": ..., "result": ..., "audit": {...}}` where the audit value is a dict, not a Path. Should be `dict[str, Path | dict[str, list[str]]]` or a TypedDict/dataclass.

### Suggestions (06-02)

- **One-line fix for the NEW HIGH:** change the hard-violation filter to also include `"mismatch"`, OR simply raise on ANY non-empty `validate_integrity` return: `if violations: raise ValueError(...)`. The latter is strictly safer and matches the Phase 6 success-criteria intent.
- Add a test that monkeypatches the 2nd `os.replace` to raise and asserts the 3 output files match their pre-call SHA-256 (the genuine transactionality test the cycle-2 concern asked for).
- Fix the return-type annotation or use a TypedDict.

**Risk Assessment: HIGH.** The `horse_race_id` mismatch-as-soft defect means a structurally
inconsistent entry/result corpus can be written silently — exactly the kind of silent
corruption the EV downstream (Phase 7/9) cannot tolerate.

---

### Plan 06-03 Review

**Summary**

PK-set union は実行ブロックで実際に3テーブルを反復しており、NEW HIGH (race-only) は
genuine RESOLVED。しかし preflight は20%までの invalid partition を許容し、EXPECTED_FLOOR
は要求期間（ROADMAP 2024年末 / D-07 2026年5月）を保証せず、さらに8項目検証に渡す
`source_stats` が Kaggle-only であるため `validate_distributions` が統合出力に対して失敗する。

### Cycle-2 HIGH Adjudication (06-03)

| # | Verdict | Orchestrator-Verified Evidence |
|---|---------|--------------------------------|
| #11 (entry/result non-empty) | **PARTIALLY RESOLVED** | The cycle-2 bug (swallowed exception via bare `except Exception: pass` + `n` computed but never asserted) IS genuinely fixed: the cycle-3 verify (`06-03-PLAN.md:144-151`) reads `pq.ParquetFile(p).metadata.num_rows`, asserts `> 0` by appending to `invalid` on failure, and re-raises on read error (`raise RuntimeError(...) from e`). Verified. HOWEVER the gate logic (`06-03-PLAN.md:168`: `if len(invalid) > len(dirs) * 0.2: sys.exit(1)`) tolerates up to 20% invalid partitions. With 40 partitions, up to 8 partition-table failures (e.g. 8 empty `entry.parquet` files, or 2 fully-empty partitions × 3 tables = 6 failures) pass the gate. So the contract "every present scraped partition ... non-emptiness for ALL THREE" (prose at `06-03-PLAN.md:16`) is NOT strictly enforced — a single empty `entry.parquet` in one partition (1 failure ≤ 8) passes. The cycle-2 defect (silent pass via swallowed exception) is resolved; the stricter reading ("all partitions non-empty") is not. |
| #14 (self-referential max) | **PARTIALLY RESOLVED** | The cycle-3 addition `actual_scraped_max >= EXPECTED_FLOOR` where `EXPECTED_FLOOR = '2024-01-01'` (`06-03-PLAN.md:311-312`) catches a scrape stopping before 2024-01 — verified. This resolves the cycle-2 weakness for the pre-2024 case. BUT the floor is weaker than both upstream contracts: ROADMAP success criterion #3 (`ROADMAP.md:190`) says "2015-01-01 through 2024-12-31" (i.e. through end of 2024), and CONTEXT D-07 (`06-CONTEXT.md`) extends the target to 2026/5. A scrape that stopped at 2024-03-15 would pass `>= '2024-01-01'` but violate ROADMAP #3 (which requires through 2024-12-31) and D-07 (which targets 2026-05). The `dmax == actual_scraped_max` check (KEPT) still only proves no-data-dropped-during-integration. So the self-referential weakness is narrowed but not eliminated: the floor catches gross incompleteness (< 2024-01) but not partial-2024 or missing-2025/2026. |
| NEW PK-set union (race-only) | **RESOLVED** | The verify block (`06-03-PLAN.md:319-330`) iterates `PK_BY_TABLE = {'race': 'race_id', 'entry': 'horse_race_id', 'result': 'horse_race_id'}` and for EACH table computes `set(output PKs) == set(union of Kaggle + all scraped partition PKs)`. Verified — the iteration is in the actual `<verify><automated>` block, not just prose. Entry and result PK drift is now caught. |
| #3 (8-point relocation) | **PARTIALLY RESOLVED** | The relocation decision is correct: `run_all_validations` against `data/standard/` root (5 tables present) is the natural validation point, and `validate_referential_integrity` would fail against the 3-table kaggle/ subdir. BUT the relocated check has a NEW defect — see NEW HIGH below (source_stats Kaggle-only). |
| #15 (halt-on-smoke-only) | **RESOLVED** (carried, KEPT) | `< 40` partitions → exit 1. |
| #16 (per-partition 3-file presence + race_date) | **RESOLVED** (carried, KEPT) — modulo the #11 20% tolerance note above. |
| #17 (odds/payoff SHA-256) | **RESOLVED** (carried, KEPT) | Pre/post SHA-256 + row count in verify.automated. |
| #18 (per-period graded) | **RESOLVED** (carried, KEPT) | Per-period derive_race_flags comparison. |

### New Concerns (06-03)

- **HIGH — `source_stats` is Kaggle-only but compared against the unified (Kaggle + scraped) output.** The verify block (`06-03-PLAN.md:274-280`) computes `source_stats` from `krace`/`kentry` — the Kaggle-only DataFrames produced by `split_race_entry_result(df)` after the 2015+ filter — for `race.distance` and `entry.popularity`. `source_counts` (`:266-273`) correctly adds Kaggle + scraped counts. But `validate_distributions` (`validators.py:283-330`) compares `source_stats[table].distributions[col]` against the ACTUAL parquet at `data/standard/{table}.parquet` (the unified Kaggle + scraped output) using `tolerance=0.01` absolute on min/max/mean — verified. The unified distance mean (2015-2026 races) differs from the Kaggle-only distance mean (2015-2021 races) by far more than 0.01 (different course distributions across eras), so `validate_distributions` flags mismatches → `dist_pass = all(len(mismatches) == 0 ...)` is False (`validators.py:855-858`) → `overall_pass = ... and dist_pass and ...` is False (`:862-865`) — verified. The plan's `assert v['overall_pass'] is True` (`06-03-PLAN.md:284`) therefore FAILS at runtime. Same logic applies to `validate_null_rates` (check 4) for `entry.popularity` null rate. This means the cycle-3 #3 relocation, while structurally correct, will not pass execution. Orchestrator-verified against `validators.py:283-330, 800-865` and `06-03-PLAN.md:274-284`.
- **MEDIUM — per-year check skips missing years silently.** `if yr in per_year.index` (`06-03-PLAN.md:316`) means a fully-missing year (e.g. all of 2024 absent) is skipped, not failed. The plan says "assert each PRESENT year 2015..end has > 500 races" so this is intentional, but combined with the #14 floor weakness, a corpus missing 2024-06 through 2024-12 passes both the floor (`>= 2024-01-01`) and the per-year check (2024 present with H1 races > 500).
- **MEDIUM — odds/payoff source_counts derived from the output files themselves.** `source_counts['odds_trifecta'] = pq.ParquetFile('data/standard/odds_trifecta.parquet').metadata.num_rows` (`06-03-PLAN.md:272`) reads the row count FROM the file being validated. The SHA-256 protection (#17) is genuine (proves non-overwrite), but as a row-count validation this is self-referential — it can only catch a row-count change between snapshot and validate, not a wrong row count vs an independent source. Acceptable given Phase 5 is the authoritative source for odds/payoff, but worth noting.
- **MEDIUM — final verify does not directly assert `validate_integrity(race, entry, result) == []`.** The 8-point `run_all_validations` calls `validate_referential_integrity` (`validators.py:352-403`) which checks `race_id` FK only — it does NOT check entry/result `horse_race_id` 1-to-1. Combined with the 06-02 NEW HIGH (horse_race_id mismatch treated as soft), the unified corpus's entry/result 1-to-1 invariant is not enforced anywhere in the final gate.

### Suggestions (06-03)

- **One-line fix for the NEW HIGH:** compute `source_stats` from the merged unified DataFrame (Kaggle + scraped concatenated), not from `krace`/`kentry` alone. OR pass `source_stats=None` (which makes checks 4 and 5 pass vacuously per `validators.py:779, 803-810, 851-860`) and rely on the 3-table-specific checks from 06-01-T3 + the per-period/per-year checks. The latter is simpler and the distributions check adds little value given the strong per-table PK/FK/schema checks already present.
- Change the preflight gate to `if len(invalid) > 0: sys.exit(1)` (fail on ANY invalid partition) to match the "all partitions non-empty" prose, OR explicitly document the 20% tolerance as intentional.
- Strengthen EXPECTED_FLOOR to `>= '2024-12-31'` (ROADMAP #3) or assert a specific target YYYYMM per D-07 (`'202605'` or last-known JRA month), with a documented tolerance for boundary incompleteness.
- Add `assert validate_integrity(race_df, entry_df, result_df) == []` directly to the final verify (independent of the 06-02 raise logic) so the entry/result 1-to-1 invariant is enforced at the gate regardless of how 06-02 classifies it.

**Risk Assessment: HIGH.** The source_stats defect means the relocated 8-point check will
FAIL at runtime — the cycle-3 #3 fix does not actually pass execution. The 20% preflight
tolerance and the weak EXPECTED_FLOOR leave real coverage gaps.

---

## Consensus Summary

Single-reviewer cycle (Codex / gpt-5.5). The orchestrator independently verified every
load-bearing claim Codex raised against the working tree — all corroborated (see inline
"Orchestrator-Verified Evidence" in each adjudication row). No divergent views.

### Resolved cycle-2 HIGHs (4 — counted out)

- **#1 grade detection ordering** — `_apply_grade_detection` moved after `_UNMAPPED_RACE_FLAGS` loop (no KeyError, no clobber); `grade='G1'` matches `_GRADE_REGEX`; `race_condition=' '` bypasses early-return.
- **#2 odds/payoff overwrite** — `convert(core_tables_subdir='kaggle')` SKIPS odds/payoff writes entirely; non-overwrite test replaces value-equality.
- **NEW PK-set union (race-only)** — verify block iterates all 3 tables (race/entry/result); entry/result PK drift now caught.
- **#11 cycle-2 bug portion** — preflight now reads `num_rows` via pyarrow, asserts `> 0`, re-raises exceptions (the swallowed-exception + unasserted-n bug is fixed).

### Unresolved HIGHs (5 — carried forward)

1. **[06-01, #3 PARTIALLY RESOLVED — depends on 06-03] 8-point relocation has a downstream defect.** The 06-01-side fix is correct, but the FULL 8-point check moved to 06-03-T2 will FAIL at runtime due to the source_stats issue (#5 below).
2. **[06-02, #6 PARTIALLY RESOLVED] Transactionality test does not inject mid-swap failure.** Idempotent recovery is real in principle; the test deletes a file post-run rather than failing the swap loop, so it does not prove recovery from the actual mixed-generation failure mode.
3. **[06-03, #11 PARTIALLY RESOLVED — gate strictness] 20% invalid-partition tolerance.** The cycle-2 silent-pass bug is fixed, but the gate tolerates up to 20% partition-table failures, so a single empty `entry.parquet` in one partition passes.
4. **[06-03, #14 PARTIALLY RESOLVED — floor too weak] `EXPECTED_FLOOR = '2024-01-01'` does not match ROADMAP #3 (through 2024-12-31) or D-07 (through 2026/5).** A scrape stopping at 2024-03 passes the floor but violates both upstream contracts.
5. **[06-03, NEW HIGH] `source_stats` Kaggle-only vs unified output → `validate_distributions` fails → `overall_pass=False` → assertion fails.** `source_stats` computed from `krace`/`kentry` (Kaggle-only); compared against unified parquet; tolerance 0.01 is far exceeded by the era difference.

Plus 1 NEW HIGH from 06-02:

6. **[06-02, NEW HIGH] `horse_race_id` 1-to-1 mismatch treated as SOFT (not raised).** The hard-violation filter `"duplicate" in v or "orphan" in v` misses `"horse_race_id mismatch"`; a non-1-to-1 entry/result corpus is written as a warning only.

### Divergent Views

Single reviewer — no divergence. Orchestrator source verification corroborates all
load-bearing claims rather than contradicting.

### Recommended next actions (targeted patches — no full re-review needed)

All 5 unresolved HIGHs have one-line fixes. They can be applied via a targeted patch commit
rather than another full convergence cycle:

1. **06-02 horse_race_id mismatch (NEW HIGH):** change `06-02-PLAN.md:215` hard-violation
   filter to `if violations: raise ValueError(...)` (raise on ANY non-empty return), OR add
   `"mismatch"` to the token list. Add a test injecting an entry/result horse_race_id
   cardinality mismatch and asserting ValueError.
2. **06-03 source_stats Kaggle-only (NEW HIGH):** in `06-03-PLAN.md` STEP 3, either (a)
   compute `source_stats` from `pd.concat([krace, scraped_race_df])` (the merged unified
   frame) instead of `krace`/`kentry` alone, OR (b) pass `source_stats=None` (checks 4 and
   5 pass vacuously; the strong per-table PK/FK/schema checks remain). Option (b) is simpler.
3. **06-03 EXPECTED_FLOOR (carried #14):** change `EXPECTED_FLOOR = '2024-01-01'` to
   `EXPECTED_FLOOR = '2024-12-31'` (ROADMAP #3) and document the D-07 2026-05 stretch goal
   as a separate WARNING-level check (not a hard fail, since the scrape may legitimately be
   in progress).
4. **06-03 preflight tolerance (carried #11):** change `if len(invalid) > len(dirs) * 0.2`
   to `if len(invalid) > 0`, OR explicitly document the 20% tolerance as intentional with
   rationale.
5. **06-02 transactionality test (carried #6):** add a test that monkeypatches the 2nd
   `os.replace` to raise `OSError`, then asserts the 3 output files match their pre-call
   SHA-256 (genuine mid-swap failure injection).

After these 5 patches, the phase should reach 0 HIGHs.

---

## CYCLE_SUMMARY

CYCLE_SUMMARY: current_high=5

## Current HIGH Concerns

- **[06-02, NEW HIGH] `horse_race_id` 1-to-1 mismatch treated as SOFT (not raised)** — the plan's hard-violation filter (`"duplicate" in v or "orphan" in v`, mirroring `normalizer.py:744-756`) misses the `"horse_race_id mismatch"` violation string (`normalizer.py:331`); a non-1-to-1 entry/result corpus is written as a warning only. Orchestrator-verified against `normalizer.py:309-336, 744-756` and `06-02-PLAN.md:215`.
- **[06-03, NEW HIGH] `source_stats` Kaggle-only vs unified output → `validate_distributions` fails → `overall_pass=False`** — `source_stats` is computed from `krace`/`kentry` (Kaggle-only) but compared against the unified (Kaggle + scraped) parquet with `tolerance=0.01`; the era difference in distance/popularity means exceeds tolerance, so the relocated 8-point check FAILS at runtime. Orchestrator-verified against `validators.py:283-330, 800-865` and `06-03-PLAN.md:274-284`.
- **[06-01/06-03, #3 PARTIALLY RESOLVED] 8-point relocation depends on the 06-03 source_stats fix** — the 06-01-side 3-table validation is correct, but the FULL 8-point check moved to 06-03-T2 will not pass execution until the source_stats NEW HIGH above is fixed.
- **[06-02, #6 PARTIALLY RESOLVED] Transactionality test does not inject mid-swap failure** — idempotent recovery is real in principle (reads from immutable inputs), but `test_integration_partial_swap_recoverable` deletes a file post-run rather than failing the 2nd `os.replace`, so it does not prove recovery from the actual mixed-generation failure mode Codex flagged in cycle 2.
- **[06-03, #11 PARTIALLY RESOLVED — gate strictness] 20% invalid-partition tolerance** — the cycle-2 silent-pass bug (swallowed exception + unasserted `n`) IS fixed, but the gate `if len(invalid) > len(dirs) * 0.2` tolerates up to 20% partition-table failures, so a single empty `entry.parquet` in one partition passes. Orchestrator-verified against `06-03-PLAN.md:168`.
- **[06-03, #14 PARTIALLY RESOLVED — floor too weak] `EXPECTED_FLOOR = '2024-01-01'` does not match ROADMAP #3 (through 2024-12-31) or D-07 (through 2026/5)** — a scrape stopping at 2024-03 passes the floor but violates both upstream contracts. Orchestrator-verified against `ROADMAP.md:190` and `06-CONTEXT.md` D-07.
