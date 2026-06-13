---
phase: 4
reviewers: [codex]
reviewed_at: 2026-06-14T00:00:00Z
cycle: 4
plans_reviewed:
  - 04-01-PLAN.md
  - 04-02-PLAN.md
  - 04-03-PLAN.md
  - 04-04-PLAN.md
  - 04-05-PLAN.md
  - 04-06-PLAN.md
---

# Cross-AI Plan Review — Phase 4 (Cycle 4 / Final Convergence-Confirmation)

> **This is cycle 4 — the final convergence-confirmation review.** The cycle-3
> review confirmed all 8 cycle-2 HIGHs and all 5 cycle-1 HIGHs were FULLY
> RESOLVED, but flagged 2 NEW narrow defects. Both were just fixed in a narrow
> revision:
>
> 1. `corner_1..corner_4` dtype `Int64` → `Float64` (in 04-05), so it matches
>    Kaggle `double nullable=True` and passes 04-06's dtype-equality test.
> 2. `fetch_race_html` gained an optional `fetch_callable` param (in 04-03), and
>    `run_scrape(live=False)` threads the injected transport to race fetching
>    (in 04-06), so the offline full-chain path no longer crashes on
>    non-pre-saved races.
>
> This cycle reviews the CURRENT plans freshly and independently: are the 2
> cycle-3 NEW HIGHs now genuinely fully resolved, and does any other correctness
> issue (new or persisting) remain? Prior HIGHs are recorded as history and are
> NOT counted as current HIGHs.

## Cycle 4 Summary

- **Cycle-3 NEW HIGHs:** 2 raised; **2 FULLY RESOLVED** in this cycle's plan text.
- **Cycle-4 verdict:** **CONVERGED — PROCEED TO IMPLEMENTATION.**
- **Cycle-4 HIGHs remaining:** **0**.

| # | Cycle-3 NEW HIGH | Cycle-4 verdict | Evidence in current plan text |
|---|---|---|---|
| 1 | `corner_1..corner_4` dtype `Int64` contradicts 04-06 equality test (Kaggle `double`) | **FULLY RESOLVED** | 04-05 SCHEMA_DTYPE_MAP maps `corner_1..corner_4` to `"Float64"` (plan line 117), with explicit `CYCLE-3 #1` rationale. Verification import asserts all 4 corners are `Float64` (line 159). `test_dtypes_applied` asserts each corner dtype is `Float64` AND serializes to Arrow `double` via `pyarrow.Table.from_pandas(df).schema.field("corner_1").type` (line 231). This matches Kaggle `double nullable=True` and passes 04-06's `test_physical_type_equality_for_non_null_kaggle_columns` (line 215). |
| 2 | Offline injected-fetch path crashes on non-pre-saved races (`AttributeError: 'NoneType'`) | **FULLY RESOLVED** | 04-03 `fetch_race_html` signature is `(race_ref, session=None, raw_dir=..., fetch_callable=None)` (line 106). Two-transport dispatch (line 111): `fetch_callable` used if provided, `session` used if provided, `ValueError` if both None (fail-loud, not `AttributeError`). 04-06 `run_scrape(live=False, fetch_html=transport)` passes `fetch_callable=transport` to `fetch_race_html` for each RaceRef (line 130). `test_full_chain_handles_failed_fetch` exercises the real transport-None → `fetch_race_html`-returns-None → race-skipped flow without pre-saving the failing race (line 210). Acceptance criteria lock it in (04-03 line 141; 04-06 line 154). |

**Both cycle-3 NEW HIGHs are FULLY RESOLVED.** No prior HIGH persists. The cycle-2
revision's 8 HIGHs and cycle-1's 5 HIGHs remain resolved (verified: their
acceptance criteria — `urljoin` for #1, FLAG_CROSSWALK completeness for #2,
`errors="ignore"` removal for #3, `partition_map` for #6, `primary_key` merge-dedup
for #4, module-level `fetch_with_retry` for #8 — are all still present in the
current plan text; the narrow cycle-4 revision touched only the corner dtype and
the fetch_callable wiring).

## Codex Review (Cycle 4)

> Codex (cycle 4) was given the current plan text and asked to verify the 2
> cycle-3 NEW HIGHs and surface any new issue. Codex confirmed both are FULLY
> RESOLVED and raised no new HIGH.

### Verdict for HIGH-1 (corner dtype): FULLY RESOLVED

- `corner_1..corner_4` は `Float64` に指定されています。 (04-05-PLAN.md:117)
- `finish_position` は `Int64` のままです。 (04-05-PLAN.md:116)
- 検証コマンドでも4列すべての `Float64` を確認します。 (04-05-PLAN.md:159)
- `test_dtypes_applied` は4列の pandas dtype と Arrow `double` への変換を検証します。 (04-05-PLAN.md:231)
- これにより04-06の非null型完全一致テストと整合します。 (04-06-PLAN.md:215)

### Verdict for HIGH-2 (offline fetch path): FULLY RESOLVED

- `fetch_race_html` に optionalな `session` と `fetch_callable` が定義されています。 (04-03-PLAN.md:106)
- `fetch_callable` があればそれを使用し、両方が `None` なら `ValueError` を送出します。 (04-03-PLAN.md:111)
- offlineモードでは各RaceRefに `fetch_callable=fetch_html` が渡されます。 (04-06-PLAN.md:130)
- `test_full_chain_handles_failed_fetch` は未保存レースに対するtransportの `None` を実際に通し、スキップして他レースを継続する流れを検証します。 (04-06-PLAN.md:210)

### Any NEW HIGH concerns

None.

### Final CYCLE_SUMMARY

`CYCLE_SUMMARY: current_high=0`

## Orchestrator Independent Verification (Cycle 4)

The orchestrator (this review's author) independently re-verified both fixes
against the current plan text before recording Codex's verdict. Findings agree
with Codex:

**HIGH-1 (corner dtype) — FULLY RESOLVED.** The fix is present in three
reinforcing layers in 04-05: (a) the dtype map assignment (`Float64`, line 117),
(b) a verification import that asserts all 4 corners are `Float64` and would fail
at plan-execution if the map regressed (line 159), and (c) `test_dtypes_applied`
asserting both the pandas dtype and the Arrow `double` serialization (line 231).
The cycle-3 rationale ("high null rates" justified `Int64`) is explicitly refuted
in the plan text with the authoritative `pyarrow.parquet.read_schema` evidence.
04-06's `test_physical_type_equality_for_non_null_kaggle_columns` (line 215)
compares `str(field.type)`; `str(double) == str(double)` now holds for all 4
corner columns. The equality branch of cycle-2 #7 is now achievable for every
non-null Kaggle column. No collateral damage: `finish_position` remains `Int64`
(line 116), and the strict-coercion / no-`errors="ignore"` guarantees from
cycle-2 #3 are untouched.

**HIGH-2 (offline fetch path) — FULLY RESOLVED.** The fix threads through both
plans cleanly: (a) 04-03 `fetch_race_html` gains `fetch_callable` with
fail-loud `ValueError` when both transports are None (lines 106, 111) — this
converts the exact `AttributeError: 'NoneType' object has no attribute
'fetch_with_retry'` crash Codex flagged into a deliberate, diagnosable error;
(b) 04-06 `run_scrape(live=False, fetch_html=transport)` passes
`fetch_callable=transport` to `fetch_race_html` per RaceRef (line 130), so a race
not pre-saved is fetched via the transport and a transport-None is handled
gracefully (race skipped, others proceed); (c) `test_full_chain_handles_failed_fetch`
(line 210) now reaches the previously-unreachable transport-None → skip path by
NOT pre-saving the failing race. The happy-path e2e (`test_full_chain_end_to_end`,
line 204) still pre-saves golden HTML so its SCRP-05 dedup short-circuits before
the transport is consulted — preserving the cycle-2 #5 design. Acceptance
criteria in both plans lock the wiring in (04-03 line 141; 04-06 line 154).

**No regression in prior resolutions.** A grep for the load-bearing tokens of
each prior HIGH confirms they survive the narrow revision: `urljoin` (cycle-2 #1),
FLAG_CROSSWALK completeness (cycle-2 #2), absence of `errors="ignore"` in any
enabling position (cycle-2 #3), `primary_key` merge-dedup (cycle-2 #4),
full-chain e2e (cycle-2 #5), `partition_map` (cycle-2 #6), dtype-fidelity split
(cycle-2 #7), and module-level `fetch_with_retry` (cycle-2 #8). The cycle-4
revision touched only corner dtype and the fetch_callable wiring — both are
additive and do not disturb any prior fix.

## Consensus Summary (Cycle 4)

Both reviewers (Codex + orchestrator) agree:

### Agreed Verdict

- **HIGH-1 (corner dtype):** FULLY RESOLVED (both reviewers).
- **HIGH-2 (offline fetch path):** FULLY RESOLVED (both reviewers).
- **New HIGHs this cycle:** None (both reviewers).
- **Persisting prior HIGHs:** None.

### Agreed Strengths (carried forward)

- The fixes are narrow, additive, and each is locked in by an automated
  verification (import assertion / dtype test / e2e test) that would fail at
  plan-execution if the fix regressed.
- The corner dtype fix cites the authoritative `pyarrow.parquet.read_schema`
  evidence directly in the plan text, making the rationale auditable.
- The fetch_callable fix converts a cryptic `AttributeError` into a deliberate,
  documented `ValueError` — improving diagnosability, not just silencing the crash.

### Divergent Views

None. Both reviewers reached identical verdicts with identical evidence.

## Cycle 4 Conclusion

**CYCLE 4 VERDICT: CONVERGED — PROCEED TO IMPLEMENTATION.**

The 2 cycle-3 NEW HIGHs are FULLY RESOLVED in the current plan text. No new HIGH
was raised. No prior HIGH persists. The plans are ready for execution.

`CYCLE_SUMMARY: current_high=0`

---

## Prior-Cycle History (reference only — NOT counted as current HIGHs)

The sections below are preserved from cycle 3 for traceability. Per the cycle
contract, HIGHs recorded in prior cycles that are now resolved are NOT counted
in the cycle-4 `current_high` total.

### Cycle 3 outcome (reference)

- Cycle-3 raised 2 NEW HIGHs (corner dtype; offline fetch path).
- Both are FULLY RESOLVED in cycle 4 (see table above).
- All 8 cycle-2 HIGHs were FULLY RESOLVED as of cycle 3 and remain resolved.
- All 5 cycle-1 HIGHs were FULLY RESOLVED as of cycle 3 and remain resolved.

### Cycle-2 HIGH resolution status (verified against current plan text, re-confirmed in cycle 4)

| # | Cycle-2 HIGH | Status | Evidence |
|---|---|---|---|
| 1 | Relative day URLs not absolutized | FULLY RESOLVED | 04-02 `urljoin(BASE_URL, href)` + `enumerate_races_for_day` repair + tests |
| 2 | FLAG_CROSSWALK incomplete (牡, bare 見習騎手) | FULLY RESOLVED | 04-04 FLAG_CROSSWALK rows + parametrized test over all 13 targets |
| 3 | dtype coercion not enforced (`errors="ignore"`) | FULLY RESOLVED | 04-05 strict coercion, nullable Int64, no `errors="ignore"` |
| 4 | Same-month partition overwrite | FULLY RESOLVED | 04-05 `drop_duplicates(subset=[primary_key], keep="last")` |
| 5 | No full-chain e2e | FULLY RESOLVED | 04-06 `test_full_chain_end_to_end` (real enumerate→injected fetch→real parse→real normalize) |
| 6 | entry/result partition by race_date is KeyError | FULLY RESOLVED | 04-05 `partition_map` param + tests |
| 7 | dtype-fidelity assertion unachievable (null Kaggle cols) | FULLY RESOLVED | 04-06 equality branch + promotion branch; now achievable for corners after cycle-4 dtype fix |
| 8 | `fetch_with_retry` export contradiction | FULLY RESOLVED | 04-03 method + module-level wrapper + import test |
