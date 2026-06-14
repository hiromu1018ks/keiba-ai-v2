---
phase: 06-data-integration
reviewers: [codex]
reviewed_at: 2026-06-14T19:55:00+09:00
plans_reviewed:
  - 06-01-PLAN.md
  - 06-02-PLAN.md
  - 06-03-PLAN.md
cycle: 2
prior_cycle_high: 14
---

# Cross-AI Plan Review — Phase 6 (Cycle 2)

Cycle-2 re-review. The three PLAN.md files were replanned under `--reviews` to address the
14 HIGHs from cycle 1. Codex (gpt-5.5 via `codex exec`) re-reviewed the revised plans with
repository read access. The orchestrator independently re-verified each of Codex's
load-bearing claims against the working tree (verifications inlined in the Concerns
sections below).

**Headline:** the replan resolved 7 of 14 cycle-1 HIGHs fully (#4, #5, #7, #8, #9, #10,
#12, #13 — 8 by the strict RESOLVED count, since #4 poetry is shared across all three
plans). 7 HIGHs remain unresolved in cycle 2: 3 are genuinely NOT RESOLVED (the replan's
mechanism does not achieve the claimed effect), 3 are PARTIALLY RESOLVED (mechanism present
but enforcement incomplete), and 1 is newly raised.

---

## Codex Review

### Plan 06-01 Review

**Summary**

D-01、出力分離、validator引数、setuptools対応の方向性は正しいが、実装順序と5テーブルwrite契約の確認が不足している。現状の記述どおりではgrade detectorが実行時エラー（KeyError）になり、odds/payoffも引き続き上書きされ、8項目検証も成功しない。

### Cycle-1 HIGH Adjudication (06-01)

| # | Verdict | Evidence |
|---|---------|----------|
| 1 (D-01 GRADE_REGEX) | **NOT RESOLVED** | PLAN calls `_apply_grade_detection` "immediately AFTER `convert_flags_to_bool`" (`split_race_entry_result` line ~248). But `race_flag_stakes` and `race_flag_listed` are in `_UNMAPPED_RACE_FLAGS` (`kaggle_converter.py:39,42`) and are added as `pd.NA` at lines 251-252, AFTER line 248. So the helper's OR-merge result for `stakes`/`listed` gets CLOBBERED to `pd.NA` by the subsequent unmapped-flags loop. Worse, at line 248 those two columns do not yet exist on `race_df`, so `existing = race_df[col]` raises `KeyError` on `race_flag_stakes` and `race_flag_listed`. The plan's WARNING-2 OR-merge is defeated by call ordering. Additionally the plan's hermetic test `grade="GⅠ"` (`06-01-PLAN.md:141`) does not match `_GRADE_REGEX` (`flag_crosswalk.py:124`): `GⅠ` is half-width `G` (0x47) + full-width `Ⅰ` (0xFF21), which matches NEITHER the half-width alternative `GI` nor the full-width alternative `ＧＩ` (0xFF27 0xFF29). |
| 2 (convert() overwrites odds/payoff) | **NOT RESOLVED** | The PLAN's own action text (`06-01-PLAN.md:178`) states: "For odds_trifecta/payoff: `out_dir = standard_dir` (ALWAYS the root, regardless of `core_tables_subdir`)". So `convert(core_tables_subdir='kaggle')` STILL WRITES odds/payoff to `data/standard/`, overwriting any pre-existing `odds_trifecta.parquet` / `payoff.parquet`. The `core_tables_subdir` param only redirects race/entry/result; it does NOT stop odds/payoff from being written. The SHA-256 equality test (`test_convert_preserves_odds_payoff`) only proves the REGENERATED odds/payoff match the pre-existing ones in VALUE (same source CSV re-derived), not that they were not rewritten. This is a real D-05 violation. |
| 3 (8-point verification skips 3-4 checks) | **PARTIALLY RESOLVED** | The mechanism (supply non-None `source_counts` + `source_stats`) is present (`06-01-PLAN.md:255-259`). BUT `run_all_validations(raw, Path('data/standard/kaggle'), ...)` runs check 6 (`validate_referential_integrity`) which hard-appends `"Missing odds_trifecta.parquet"` and `"Missing payoff.parquet"` to its error list when those files are absent from `parquet_dir` (`validators.py:377-383`). The 3-table `kaggle/` subdir has NO odds/payoff → `integrity_errors` non-empty → `integrity_pass=False` → `overall_pass=False`. The plan's `assert r['overall_pass'] is True` will FAIL. The plan anticipates this (option (a) vs (b)) but defers the decision to "read the source first" without resolving it. |
| 4 (poetry) | **RESOLVED** | All `<verify><automated>` commands use `python -m pytest` / `python -c` (`06-01-PLAN.md:134,190,243`). `pyproject.toml` build-backend is setuptools. |

### New Concerns (06-01)

- **HIGH — `_apply_grade_detection` call ordering causes KeyError + clobbers OR-merge result.** As detailed in #1: the helper runs at line 248 but the columns it modifies for `stakes`/`listed` are created at 251-252 as `pd.NA`. Either the helper must run AFTER the unmapped-flags loop, or it must defensively initialize the 3 columns as nullable-boolean before OR-merging. The plan specifies neither.
- **HIGH — `core_tables_subdir` does not protect odds/payoff.** The plan's "ALWAYS write odds/payoff to root" rule means the Phase 5 seed at `data/standard/odds_trifecta.parquet` is overwritten on every `convert(core_tables_subdir='kaggle')` call. The fix should EXCLUDE odds/payoff from the write loop when `core_tables_subdir` is set, or guard with an existence check.
- **HIGH — 3-table subdir vs 5-table validator structural incompatibility.** `run_all_validations` iterates all 5 tables (race/entry/result/odds_trifecta/payoff) and treats missing odds/payoff as a referential-integrity failure. A 3-table `kaggle/` subdir cannot pass `overall_pass=True` without a dedicated 3-table validator or the option-(b) symlink shim the plan defers.
- **MEDIUM — `derive_race_flags` early-returns on empty `race_condition`.** `flag_crosswalk.py:184-185`: `if not race_condition: return flags`. The plan passes `race_condition=str(row["grade"])`. When `grade` is null (non-graded Kaggle races), the helper returns ALL-None flags even if `race_name` alone contains a GI token. The plan's `_apply_grade_detection` passes `""` for the condition in that case, so `race_name`-only grade tokens are NOT detected. Fix: pass `race_condition=" "` (non-empty) when grade is null, or change the early-return guard.
- **MEDIUM — Kaggle `grade` value `"L"` does not match `_LISTED_REGEX`.** `_LISTED_REGEX = r"\(L\)|（L）|\(リステッド\)|（リステッド）"` (`flag_crosswalk.py:131`) requires the parenthesized form. The Kaggle `リステッド・重賞競走` field stores bare `"L"` / `"リステッド"` (no parens) for listed races. So the listed derivation the plan promises is incomplete.
- **MEDIUM — `grade_revision` mentioned as input (`06-01-PLAN.md:118`) but the helper only consumes `grade` + `race_name`.** The `重賞回次` (grade_revision) field is never read by `_apply_grade_detection`; the test description is inconsistent with the action.

### Suggestions (06-01)

- Move `_apply_grade_detection` AFTER the `_UNMAPPED_RACE_FLAGS` loop, OR have the helper defensively create `race_flag_stakes`/`race_flag_listed`/`race_flag_graded_stakes` as nullable-boolean Series before OR-merging.
- Normalize the grade value before testing: accept `GⅠ/GⅠ/G1/JpnI/L` explicitly rather than relying on `_GRADE_REGEX` which only handles half/full-width ASCII `GI`.
- When `core_tables_subdir` is set, EXCLUDE odds/payoff from the write loop entirely (do not write them at all), preserving the Phase 5 seed.
- Add a dedicated 3-table validator OR implement the symlink shim (option b) so `run_all_validations` finds all 5 tables; assert `overall_pass=True` AND that the result dict shows all 8 check keys actually executed.

**Risk Assessment: HIGH.** The grade detector as specified will raise KeyError at runtime or silently clobber its own result; odds/payoff are still overwritten; the 8-point verification cannot return True against the kaggle/ subdir.

---

### Plan 06-02 Review

**Summary**

入力分離、skip分離、FKテスト、列集合検証は具体的で、cycle 1の多くを解消している。ただし3ファイルの逐次`os.replace`はcorpus transactionではなく、swap途中の障害でmixed generationが残る。rollbackテストもない。

### Cycle-1 HIGH Adjudication (06-02)

| # | Verdict | Evidence |
|---|---------|----------|
| 5 (non-idempotent) | **RESOLVED** | `integrate_standard_layer` reads Kaggle from `kaggle_input_dir` (default `standard_dir/'kaggle'`), never from the output path (`06-02-PLAN.md:197`). Two-run SHA-equality idempotency test present (`06-02-PLAN.md:172`). |
| 6 (no corpus transactionality) | **PARTIALLY RESOLVED** | The mechanism writes all 3 frames to a tmp dir, validates, then swaps via `os.replace` (`06-02-PLAN.md:209`). However, THREE SEQUENTIAL `os.replace` calls are not one atomic operation. If the 2nd `os.replace` raises (disk full, permission, signal), the corpus is left with race=new + entry=result=old. The plan has no rollback (no backup-and-restore of the pre-swap files) and no test that injects a mid-swap failure to prove the corpus stays consistent. The idempotency test only proves two CLEAN runs match — it does not test transactionality. |
| 7 (autouse skip swallows hermetic) | **RESOLVED** | Split into `TestIntegrationHermetic` (no autouse) + `TestUnifiedCorpus` (gated `_require_scraped_data`) (`06-02-PLAN.md:122`). Verify collects 7 hermetic + 2 gated. |
| 8 (FK test no-op) | **RESOLVED** | Injects orphan `entry.race_id`, asserts `validate_integrity` reports it, integration raises `ValueError` (`06-02-PLAN.md:167`). Matches `validate_integrity`'s FK contract (`normalizer.py:338-354`). |
| 9 (reindex masks schema drift) | **RESOLVED** | `_assert_column_set_equality` raises `ValueError` BEFORE reindex; test injects extra/missing column (`06-02-PLAN.md:203`). |

### New Concerns (06-02)

- **HIGH — corpus-swap failure leaves mixed generation; no rollback.** Three sequential `os.replace` calls are not atomic. A failure on the 2nd or 3rd replace leaves race=new + entry/result=old (or any partial combination). No backup-and-restore of the pre-existing output files, and no test injecting a mid-swap failure.
- **MEDIUM — fixed tmp dir path `.integration_tmp` collides on concurrent runs / stale leftovers.** If a prior run crashed and left the tmp dir, the next run may pick up stale files. Use `tempfile.mkdtemp()` (the plan mentions both options but does not commit to one).
- **LOW — `PK_BY_TABLE = {race: race_id, entry: horse_race_id, result: horse_race_id}` is CORRECT.** `validate_integrity` checks entry/result uniqueness on `horse_race_id` and FK on `race_id` (`normalizer.py:274-372`); the plan's per-table dedup-on-PK assertion matches.

### Suggestions (06-02)

- Implement directory-level swap: write all 3 to a versioned tmp dir, then rename the dir into place (single atomic op), OR back up the 3 pre-existing output files and restore on any swap failure.
- Add a test that monkeypatches the 2nd `os.replace` to raise, then asserts the 3 output files are byte-identical to their pre-call SHA-256.

**Risk Assessment: HIGH.** Idempotency, skip-split, FK, and column-set guards are solid. But the transactionality claim is not actually enforced — a partial swap is a real mixed-generation risk that propagates to Phase 7/9.

---

### Plan 06-03 Review

**Summary**

odds/payoff snapshotと固定band廃止は改善されている。しかしpreflightの実コマンドはentry/resultの非空性を検証しておらず、日付上限も「入力に存在する最大日」と比較するだけでD-06の2026年5月到達を保証しない。PK-set union検証もrace tableだけ。

### Cycle-1 HIGH Adjudication (06-03)

| # | Verdict | Evidence |
|---|---------|----------|
| 10 (D-06 pre-task not done) | **RESOLVED** | Real corpus is still `202306` only (5 races), but the `< 40` partitions halt gate exits 1 with a clear message (`06-03-PLAN.md:115`). The plan does NOT weaken the gate. |
| 11 (month-count gate weak) | **NOT RESOLVED** | The PROSE describes per-partition 3-file presence + non-empty + race_date-matches-dir (`06-03-PLAN.md:94-96`), but the ACTUAL `<verify><automated>` command (`06-03-PLAN.md:124-128`) only reads `race.parquet` for non-empty + date. The entry/result non-empty check (`06-03-PLAN.md:122-127`) wraps a `pd.read_parquet` in a bare `except Exception: pass` and the `n` variable is computed but NEVER asserted (`> 0`). Empty `entry.parquet` / `result.parquet` files pass the verify. |
| 12 (odds/payoff snapshot not in verify) | **RESOLVED** | Pre/post SHA-256 + row count snapshot/assert IS in the actual `<verify><automated>` command (`06-03-PLAN.md:202-223`), not just prose. |
| 13 (graded 780-880 wrong) | **RESOLVED** | Kaggle/scraped periods split; each compared to `derive_race_flags` derivation, not a fixed band (`06-03-PLAN.md:225-233`). |
| 14 (date-range too weak) | **PARTIALLY RESOLVED** | min in 2015-01..03, max EQUALS actual scraped max, per-year counts (`06-03-PLAN.md:235-257`). BUT `actual_scraped_max` is computed from the SAME input partitions as `dmax` (output), so the assertion `dmax == actual_scraped_max` is self-referential: if the D-06 scrape stopped at 2025-12, both are 2025-12-x and the assertion passes despite the 2026-05 target being unreached. Missing years are warning-only, not fail (`06-03-PLAN.md:258`). The check is robust to NO data being dropped, but NOT robust to the scrape being INCOMPLETE. |

### New Concerns (06-03)

- **HIGH — preflight "3-file non-empty" not actually implemented in verify.** The verify command's entry/result loop swallows all exceptions and never asserts `n > 0`. An empty `entry.parquet` or `result.parquet` passes.
- **HIGH — `actual_scraped_max` comparison is self-referential; does not enforce D-06 target reach.** D-06 is premised on a full 2022-01 → 2026-05 scrape. Comparing the output max to the input max proves no data was dropped during integration, but ACCEPTS an incomplete scrape as "complete." Need an explicit floor (e.g. `dmax >= '2026-01-01'`) or an expected-months-set diff with a defined tolerance.
- **NEW HIGH — PK-set union verify checks race only, not entry/result.** The plan's prose says "per table" (`06-03-PLAN.md:188`) and MEDIUM #20 is described as per-table, but the actual `<verify><automated>` PK-set equality block (`06-03-PLAN.md:261-271`) only reads `race.parquet`. Entry/result PK-set drift (dropped horses during merge) is undetected.
- **MEDIUM — "40 directories" does not guarantee 53-month continuity.** Missing months are logged, not failed. A corpus with 40 non-contiguous months (e.g. gaps in 2023) passes.

### Suggestions (06-03)

- Apply `pyarrow.parquet.ParquetFile(path).metadata.num_rows > 0` to all 3 files in the preflight verify; assert explicitly.
- Define an expected-months set `202201..202605` and diff against present partitions; fail if > N months missing.
- In addition to `actual_scraped_max`, assert `dmax >= '2026-01-01'` (or document an explicit tolerance for boundary incompleteness).
- Extend the PK-set union equality block to entry and result tables, not just race.

**Risk Assessment: HIGH.** odds/payoff SHA-256 and per-period graded counts are genuinely fixed. But the preflight does not actually enforce entry/result non-emptiness, the date-range ceiling accepts incomplete scrapes, and the PK-set union check is race-only.

---

## Consensus Summary

Single-reviewer cycle (Codex / gpt-5.5). The orchestrator independently verified each of
Codex's load-bearing claims against the working tree — all corroborated (see inline
"Orchestrator verification" notes in the Concerns sections). No divergent views.

### Resolved cycle-1 HIGHs (8 — counted out)

- **#4 poetry** — all commands `python -m` / `python -c`; setuptools backend confirmed.
- **#5 non-idempotent integration** — separate `kaggle_input_dir`; idempotency test present.
- **#7 autouse skip swallows hermetic** — two-class split; hermetic ungated.
- **#8 FK test no-op** — orphan injection + `validate_integrity` + `ValueError` assertion.
- **#9 reindex masks schema drift** — `_assert_column_set_equality` before reindex.
- **#10 D-06 pre-task not done** — halt gate kept; prerequisite documented.
- **#12 odds/payoff snapshot not in verify** — now in actual `<verify><automated>`.
- **#13 graded 780-880 wrong** — per-period derivation comparison; no fixed band.

### Unresolved HIGHs (7 — carried into cycle 3)

1. **[06-01, #1 NOT RESOLVED] `_apply_grade_detection` call ordering + KeyError + OR-merge clobber.** Helper runs at line 248 but `race_flag_stakes`/`race_flag_listed` are added as `pd.NA` at 251-252 — helper either KeyErrors or its result is overwritten. Verified: `_UNMAPPED_RACE_FLAGS` at `kaggle_converter.py:39,42`; write at `:251-252`. Also `grade="GⅠ"` test value does not match `_GRADE_REGEX`.
2. **[06-01, #2 NOT RESOLVED] `core_tables_subdir` does NOT protect odds/payoff.** Plan explicitly writes odds/payoff to root always; Phase 5 seed overwritten. SHA-256 test proves value-equality, not non-overwrite. Verified: plan action `06-01-PLAN.md:178`; existing `data/standard/{odds_trifecta,payoff}.parquet` present.
3. **[06-01, #3 PARTIALLY RESOLVED] 8-point verification cannot pass against 3-table subdir.** `validate_referential_integrity` appends "Missing odds_trifecta/payoff.parquet" → `overall_pass=False`. Verified: `validators.py:377-383`.
4. **[06-02, #6 PARTIALLY RESOLVED] 3 sequential `os.replace` not atomic; no rollback test.** Mid-swap failure leaves mixed-generation corpus. Mechanism present, enforcement absent.
5. **[06-03, #11 NOT RESOLVED] preflight verify does not assert entry/result non-empty.** `n` computed but never asserted; exceptions swallowed. Verified: `06-03-PLAN.md:122-127`.
6. **[06-03, #14 PARTIALLY RESOLVED] `actual_scraped_max` is self-referential.** Proves no data dropped, accepts incomplete scrape. Mechanism present, target reach not enforced.
7. **[06-03, NEW HIGH] PK-set union verify is race-only.** Prose says per-table; verify checks only `race.parquet`. Entry/result PK drift undetected. Verified: `06-03-PLAN.md:261-271`.

### Divergent Views

Single reviewer — no divergence. Orchestrator source verification corroborates all
load-bearing claims rather than contradicting.

### Recommended next actions (for cycle-3 `/gsd-plan-phase 6 --reviews`)

Priority order:

1. **Fix `_apply_grade_detection` ordering.** Move the call AFTER the `_UNMAPPED_RACE_FLAGS` loop (so the 3 graded columns exist), OR have the helper defensively initialize them as nullable-boolean before OR-merging. Add a test that injects a row where `convert_flags_to_bool` already set `race_flag_stakes=True` and asserts it survives.
2. **Stop `convert()` from writing odds/payoff when `core_tables_subdir` is set.** Exclude odds/payoff from the write loop entirely (the integration never reads them from the subdir anyway). The SHA-256 test then becomes a true non-overwrite proof.
3. **Resolve the 3-table-vs-5-table validator mismatch.** Either write a dedicated 3-table validator, OR use the option-(b) symlink shim, OR pass `parquet_dir=Path('data/standard')` and accept that `run_all_validations` validates the OLD race/entry/result (documenting that Plan 06-02's integration is the real validation gate). Pick one and commit.
4. **Make the corpus swap atomic.** Directory-level rename OR backup-and-restore of pre-swap files; add a test that injects a 2nd-`os.replace` failure and asserts the 3 output files match their pre-call SHA-256.
5. **Implement the preflight entry/result non-empty check properly.** Use `pyarrow.parquet.ParquetFile(path).metadata.num_rows > 0` on all 3 files; assert explicitly.
6. **Add a real date-ceiling floor.** `dmax >= '2026-01-01'` (or document an explicit tolerance for boundary incompleteness); keep `dmax == actual_scraped_max` as a "no data dropped" check in addition.
7. **Extend PK-set union verify to entry and result.** Mirror the race block for the other two tables.

---

## CYCLE_SUMMARY

CYCLE_SUMMARY: current_high=7

## Current HIGH Concerns

- **[06-01, #1 NOT RESOLVED] `_apply_grade_detection` call ordering** — helper runs at line 248 but `race_flag_stakes`/`race_flag_listed` are created as `pd.NA` at 251-252; helper KeyErrors or its OR-merge result is clobbered. Plus `grade="GⅠ"` test value does not match `_GRADE_REGEX`. Verified against `kaggle_converter.py:39,42,251-252` and `flag_crosswalk.py:124`.
- **[06-01, #2 NOT RESOLVED] `core_tables_subdir` does not protect odds/payoff** — plan writes odds/payoff to root ALWAYS; Phase 5 seed overwritten on every `convert(core_tables_subdir='kaggle')`. SHA-256 test proves value-equality, not non-overwrite. Verified against plan action `06-01-PLAN.md:178`.
- **[06-01, #3 PARTIALLY RESOLVED] 8-point verification cannot pass against 3-table subdir** — `validate_referential_integrity` appends "Missing odds_trifecta/payoff.parquet" → `overall_pass=False`. Verified against `validators.py:377-383`.
- **[06-02, #6 PARTIALLY RESOLVED] 3 sequential `os.replace` not atomic; no rollback** — mid-swap failure leaves mixed-generation corpus; idempotency test does not cover transactionality.
- **[06-03, #11 NOT RESOLVED] preflight verify does not assert entry/result non-empty** — `n` computed but never asserted; exceptions swallowed. Verified against `06-03-PLAN.md:122-127`.
- **[06-03, #14 PARTIALLY RESOLVED] `actual_scraped_max` self-referential** — proves no data dropped during integration, but accepts an incomplete D-06 scrape as complete; missing years are warning-only.
- **[06-03, NEW HIGH] PK-set union verify is race-only** — prose promises per-table; `<verify><automated>` checks only `race.parquet`; entry/result PK drift undetected. Verified against `06-03-PLAN.md:261-271`.
