---
phase: 4
reviewers: [codex]
reviewed_at: 2026-06-13T09:29:51Z
cycle: 2
plans_reviewed:
  - 04-01-PLAN.md
  - 04-02-PLAN.md
  - 04-03-PLAN.md
  - 04-04-PLAN.md
  - 04-05-PLAN.md
  - 04-06-PLAN.md
---

# Cross-AI Plan Review — Phase 4 (Cycle 2)

> **This cycle (2) is a fresh review of the revised 6-plan structure.**
> The 10 HIGHs from cycle 1 are verified below against the *current* plan text
> and the authoritative schema/source files. Prior HIGHs that are now fully
> fixed are marked RESOLVED and are NOT recounted in the cycle-2 HIGH total.
> The cycle-1 review is preserved verbatim in the **Cycle 1 History** section
> at the bottom of this document for reference only.

---

## Cycle 2 Summary

- **Reviewer:** Codex (gpt-5.5, codex exec)
- **Cycle-1 HIGHs:** 10 raised
- **Cycle-2 verdict from Codex:** REVIEW AGAIN
- **Cycle-2 HIGHs remaining:** 8 (5 prior partially-resolved/still-open + 3 newly raised)
- **Reviewer-side verification:** Every Codex HIGH claim was independently
  re-verified against the actual schemas (`src/schemas/*.py`), the actual Kaggle
  Parquet dtypes (`pyarrow.parquet.read_schema`), and `column_mapping.py` before
  being recorded here. All 8 HIGHs reproduce on inspection.

### Prior HIGH resolution status (cycle 1 → cycle 2)

| # | Prior HIGH | Status | Evidence |
|---|------------|--------|----------|
| 1 | `race_id[4:6]` used as month | **RESOLVED** | 04-02 `RaceRef(race_id, race_date)`; 04-03 derives path from `race_ref.race_date`. Verified: `race_id` is `YYYYPPCCDDRR` (12-digit, positions 4-5 = course code). No `race_id[4:6]` slice in any plan. |
| 2 | `horse_race_id` underscore format | **RESOLVED** | 04-04 emits `f"{race_id}{horse_number:02d}"` (14-digit). Verified: actual Kaggle values are 14-digit (`20150101010102`); schema docstring `{race_id}_{horse_number:02d}` is a confirmed doc error. |
| 3 | Eager `__init__.py` imports | **RESOLVED** | 04-01 keeps `__init__.py` empty (no submodule imports, no `__all__`); re-exports deferred to 04-06 Task 1 only. |
| 4 | 3-level calendar traversal missing | **PARTIALLY RESOLVED** | Functions split per level exist, BUT day URLs extracted by `parse_calendar_month_html` are relative paths (`/race/list/{8d}/`); `enumerate_races_for_day` passes `day_url` straight to `fetch_html`, which Playwright requires as an absolute URL. No `urljoin` step. → HIGH |
| 5 | Wrong COURSE_CODE_MAP codes | **RESOLVED** | 04-04 defines all 10 venues correctly (福島=03, 新潟=04); parametrized test guards all 10. |
| 6 | Race-flag semantics | **PARTIALLY RESOLVED** | `(牝)→filly_only`, `(国際)→graded_stakes`, `(特指)→special_weight` now match `column_mapping.py`. BUT the authoritative map has `レース記号/牡 → race_flag_colt_only` (line 61) and bare `見習騎手 → race_flag_apprentice` (line 66); the plan's crosswalk OMITS `牡` and only matches `(見習騎手)` (with parens). `race_flag_colt_only` is silently always None. → HIGH |
| 7 | No schema validation in normalizer | **PARTIALLY RESOLVED** | Reindex + dtype map + integrity checks added. BUT the dtype coercion uses `errors="ignore"`, which silently leaves failed conversions unchanged (e.g. `[1, None]` stays `float64`, never `int64`). The claimed dtype guarantee is therefore unenforced. → HIGH |
| 8 | Normalizer overwrites prior batches | **PARTIALLY RESOLVED** | Date-partitioned output protects *different* months. BUT re-running the *same* month (e.g. `max_races=1` smoke then a full run) atomically replaces the partition file with no read-merge-dedup of the existing rows. Same-month prior data is lost. → HIGH |
| 9 | No end-to-end test | **STILL OPEN** | 04-06 `TestEndToEndFixture` only exercises parse→normalize on golden fixtures. The full enumerate→fetch→parse→normalize chain is split across separate, independently-mocked tests; no single test connects all four stages even with a fake fetch callable + golden HTML. → HIGH |
| 10 | Fixed `<td>` index parsing | **RESOLVED** | 04-04 `resolve_columns_by_header` resolves columns by normalized `<th>` text; missing-header-skip test present. |

---

## Codex Review (Cycle 2)

### 10 Prior HIGH Verification

| # | Verdict | Verification result |
|---|---------|---------------------|
| 1 | FULLY RESOLVED | Contract + tests keep `race_date` on `RaceRef` and derive the save path from it. 04-02:82, 04-03:100 |
| 2 | FULLY RESOLVED | `f"{race_id}{horse_number:02d}"` and the 14-digit regex test are explicit. 04-04:210 |
| 3 | FULLY RESOLVED | 04-01 keeps `__init__.py` empty; re-exports deferred to 04-06. |
| 4 | PARTIALLY RESOLVED | Month→day→race functions are split, but the month page returns a *relative* path and `enumerate_races_for_day()` passes it straight to `fetch_html(day_url)` — Playwright needs an absolute URL. 04-02:87, 04-02:104 |
| 5 | FULLY RESOLVED | All 10 venue codes correct; regression test for all venues. |
| 6 | PARTIALLY RESOLVED | `(牝)`, `(国際)` etc. are Kaggle-compatible now, but the authoritative mapping `牡 → race_flag_colt_only` is absent from `FLAG_CROSSWALK`. column_mapping.py:61, 04-04:113 |
| 7 | PARTIALLY RESOLVED | `model_fields` reindex, empty-DataFrame handling, and integrity checks were added. However nullable `finish_position` is coerced to non-nullable `int64`; on failure `errors="ignore"` leaves the column unconverted, so the type guarantee is not enforced. ResultSchema:48, 04-05:107 |
| 8 | PARTIALLY RESOLVED | Partitioning protects other months, but a partial run of the *same* month overwrites the existing month file. No merge/dedup with the existing partition. 04-05:130 |
| 9 | STILL OPEN | The e2e body is parse→normalize only. Enumeration and fetch live in separate, fully-mocked tests; nothing connects enumerate→fetch→parse→normalize in a single test. 04-06:183, 04-06:197 |
| 10 | FULLY RESOLVED | `<th>`-name column resolution and a column-order-change test are explicit. 04-04:188 |

### New Blockers (raised this cycle)

- **HIGH: entry/result cannot be partitioned by `race_date`.** `write_partitioned_parquet` reads `df["race_date"]` to partition, but `EntrySchema` and `ResultSchema` have no `race_date` field (verified: only `RaceSchema` has it). The entry/result DataFrames raise `KeyError` on `df["race_date"]`. 04-05:130
- **HIGH: dtype-fidelity assertion is unachievable.** pandas nullable `boolean` always serializes to Arrow `bool`, even for an all-None column (verified: `pd.array([None,None], dtype="boolean")` → arrow `bool`). Kaggle's null-only flag columns are Arrow `null`, not `bool`. The plan's mandated "physical-type equality on every overlapping column" cannot hold for those columns. 04-05:109
- **HIGH: 04-03 public API is self-contradictory.** The artifacts/exports/verify blocks import `fetch_with_retry` as a top-level module function, but Task 1 only defines it as a `FetcherSession.fetch_with_retry()` method. The verify command `from src.scraper.fetcher import ... fetch_with_retry` would fail at import. 04-03:30, 04-03:91
- **HIGH: same-month re-run data loss.** `max_races=1` or a day-scoped run followed by a same-month run atomically replaces that month's partition file; no merge/dedup against existing rows. (Root cause shared with prior #8.)
- **MEDIUM: schema-compatibility test does not assert physical-type equality.** 04-06 `TestSchemaCompatibility` uses `_DTYPE_COMPAT` category compatibility (int↔int64/Int64, bool↔bool/boolean), which contradicts 04-05's stricter Arrow-physical-type claim. 04-06:189
- **MEDIUM: golden-fixture requirement is weak.** The cancellation fixture is optional and its test allows `pytest.skip`, so the must-have cancellation axis is not guaranteed.
- **MEDIUM: `live` is a dead parameter.** `live=False` still permits network access, so it provides no safety. 04-06:124

### Per-Plan Review

#### 04-01 — Package Skeleton and Dependencies
**Summary:** Import-safe handling is appropriate and resolves prior HIGH #3.
**Strengths:** runtime dependency placement, shared fixtures, deferred re-exports.
**Concerns:**
- **MEDIUM:** Task 1 verify imports `src.scraper.fetcher`, which does not exist until 04-03; combined with a pipe the failure is not reliably reflected in exit code.
**Suggestions:** In Task 1 verify only `import src.scraper`; move submodule import verification to 04-03.
**Risk Assessment:** LOW-MEDIUM

#### 04-02 — Fetcher and Calendar Enumeration
**Summary:** `RaceRef` and the 3-level structure are correct, but day-URL passing breaks in real use.
**Strengths:** date-range filtering, dedup, 12-digit validation, session injection.
**Concerns:**
- **HIGH:** Relative day URLs are never absolutized.
- **MEDIUM:** "malformed link" fixtures won't match the extraction regex, so the warning-logging assertion can't trigger as written.
**Suggestions:** Apply `urllib.parse.urljoin("https://db.netkeiba.com", href)` at parse time.
**Risk Assessment:** HIGH

#### 04-03 — HTML Parser and Race Flags (fetcher)
**Summary:** Session reuse, atomic write, and None-on-failure are solid, but the API/test contract is inconsistent.
**Strengths:** race_date-based save, dedup, rate limit, block-page detection.
**Concerns:**
- **HIGH:** Standalone `fetch_with_retry` is undefined (method only).
- **MEDIUM:** The "valid HTML" test string is under 500 bytes, so `detect_block_page` flags it as a block page.
**Suggestions:** Unify exports to methods only; gate block detection on required DOM elements rather than byte length.
**Risk Assessment:** HIGH

#### 04-04 — HTML Parser and Race Flags (parser)
**Summary:** IDs, course codes, and header-driven parsing are improved, but the flag crosswalk is incomplete.
**Strengths:** Correct `EntrySchema` field names (`bracket_num/sex/age/weight_assigned`); no drift.
**Concerns:**
- **HIGH:** `牡` omitted from the crosswalk.
- **MEDIUM:** `見習騎手` is bare in the authoritative map but the plan only matches `(見習騎手)`.
**Suggestions:** Add a test that mechanically diff's the crosswalk against all 20 `KAGGLE_COLUMN_MAP` rows; include `牡` and bare `見習騎手`.
**Risk Assessment:** HIGH

#### 04-05 — Normalizer and Parquet Output
**Summary:** The largest unresolved area. Partition scheme and dtype guarantee do not satisfy the real data contract.
**Strengths:** full-column reindex, atomic write, uniqueness/FK/1-to-1 checks.
**Concerns:**
- **HIGH:** entry/result have no `race_date`.
- **HIGH:** same-month overwrite.
- **HIGH:** nullable `finish_position` forced to `int64`.
- **HIGH:** null-typed flag columns can't achieve physical-type equality.
**Suggestions:** Join race_id→race_date from the race table to partition entry/result; read-merge-dedup existing partition then atomic replace; document an explicit rule for promoting null-only columns to a concrete type.
**Risk Assessment:** HIGH

#### 04-06 — Integration and Quality Gate
**Summary:** The orchestrator wires together on paper, but the required e2e verification is not actually performed.
**Strengths:** Function signatures align; single-session and failed-race-skip are tested.
**Concerns:**
- **HIGH:** No full-chain e2e.
- **MEDIUM:** `live` is inert.
- **MEDIUM:** How Phase 6 integrates partitioned output into a single standard table is unspecified.
**Suggestions:** Use a fake fetch callable + golden HTML to actually run calendar-fixture → day-fixture → raw save → parse → partition output; delete `live` or make `False` forbid network.
**Risk Assessment:** HIGH

### Required Fixes (Codex)

1. Add `牡` and bare `見習騎手` to the crosswalk.
2. Absolutize the day URL.
3. Partition entry/result by race_date joined from the race table.
4. Merge+dedup same-month partitions before atomic replace.
5. Fix the dtype design so nullable values are preserved.
6. Document the compatibility rule for Arrow `null` vs `bool`/`string`.
7. Add a true full-chain e2e using a calendar fixture.
8. Resolve the `fetch_with_retry` export contradiction.

**CYCLE 2 VERDICT: REVIEW AGAIN**

---

## Consensus Summary (Cycle 2)

> Single reviewer (Codex); all findings independently re-verified by the
> reviewing orchestrator against schemas, Kaggle Parquet, and column_mapping.py.

### Agreed Strengths (carried + new)

- Fetch/parse/normalize separation remains architecturally sound
- Import-safe `__init__.py` sequencing (prior #3) is correctly resolved
- `RaceRef` + `race_date`-based raw paths (prior #1) correctly resolved
- 14-digit `horse_race_id` (prior #2) correctly resolved and matches real Kaggle data
- Corrected `COURSE_CODE_MAP` with all-10-venue parametrized regression guard (prior #5)
- Header-driven column resolution (prior #10) correctly resolved
- Normalizer reindex against `Schema.model_fields`, integrity checks, and atomic write are real improvements

### Agreed Concerns (HIGHs remaining in cycle 2)

The following 8 HIGH-severity concerns remain unresolved. They break down as
5 prior HIGHs that are only PARTIALLY RESOLVED / STILL OPEN and 3 newly raised
HIGHs introduced or exposed by the revision.

1. **(PARTIALLY RESOLVED, prior #4) Relative day URLs not absolutized.** `parse_calendar_month_html` yields `/race/list/{8d}/`; `enumerate_races_for_day` forwards it to Playwright, which needs an absolute URL. Enumeration will fail at fetch time.

2. **(PARTIALLY RESOLVED, prior #6) Flag crosswalk missing `牡` and paren-variant `見習騎手`.** `column_mapping.py:61` maps `牡 → race_flag_colt_only`; the plan's `FLAG_CROSSWALK` omits it, so `race_flag_colt_only` is silently always None. `見習騎手` appears without parens in the authoritative map but the plan matches only `(見習騎手)`.

3. **(PARTIALLY RESOLVED, prior #7) Dtype coercion not enforced.** `_build_typed_dataframe` uses `astype(target, errors="ignore")`, which silently skips failed conversions. `finish_position` is `Optional[int]` but assigned non-nullable `int64`; a None value leaves the column as `float64` undetected. The dtype guarantee is stated but not actually enforced.

4. **(PARTIALLY RESOLVED, prior #8) Same-month partition overwrite.** Date-partitioning protects other months, but re-running the same month (smoke then full run) atomically replaces that month's file with no read-merge-dedup of existing rows.

5. **(STILL OPEN, prior #9) No single full-chain end-to-end test.** The e2e fixture test covers parse→normalize only. Enumeration and fetch are exercised in separate, fully-mocked tests. No test connects enumerate→fetch→parse→normalize in one flow.

6. **(NEW) entry/result partition by `race_date` is a KeyError.** `write_partitioned_parquet` reads `df["race_date"]`, but `EntrySchema` and `ResultSchema` have no `race_date` field. The entry/result DataFrames raise `KeyError`. Partition key must be joined from the race table.

7. **(NEW) dtype-fidelity assertion is unachievable for null-typed Kaggle columns.** pandas nullable `boolean` always serializes to Arrow `bool` (verified empirically), but several Kaggle flag columns are Arrow `null`. The mandated "physical-type equality on every overlapping column" cannot hold. An explicit null→concrete-type promotion rule is needed.

8. **(NEW) `fetch_with_retry` export contradiction.** 04-03's exports/verify treat `fetch_with_retry` as a top-level module function, but Task 1 defines it only as a `FetcherSession` method. The verify import `from src.scraper.fetcher import fetch_with_retry` would fail.

### Divergent Views

Not applicable — single reviewer. All HIGHs were re-verified against source.

### Recommended Actions Before Implementation (Cycle 3)

1. Absolutize calendar/day URLs via `urljoin` in 04-02 before passing to `fetch_html`.
2. Make `FLAG_CROSSWALK` a mechanical superset of `KAGGLE_COLUMN_MAP` flag rows; add `牡 → race_flag_colt_only` and bare `見習騎手 → race_flag_apprentice`; add a test that diffs the crosswalk against the authoritative map.
3. In 04-05, partition entry/result by joining `race_id → race_date` from the race table (or carry `race_date` into the parsed dicts).
4. In 04-05, read-merge-dedup an existing same-month partition before atomic replace (upsert on primary key).
5. Replace `astype(..., errors="ignore")` with explicit nullable-dtype handling; for `finish_position` use nullable `Int64` OR coerce nulls and document, but enforce the result with an assertion.
6. Document an explicit rule: null-only Kaggle columns are promoted to the concrete dtype the scraper writes (`bool`/`string`), and the schema-compatibility test asserts Arrow compatibility (not null-type identity) for those columns. Relax the "physical-type equality" claim accordingly.
7. In 04-06, add a true full-chain test: calendar fixture → day fixture → raw save → parse → partition output, using a fake fetch callable backed by golden HTML.
8. Resolve the `fetch_with_retry` API: either remove it from the standalone exports/verify (keep method only) or add a thin module-level wrapper.

---

## Cycle 1 History

> The section below is the cycle-1 review, preserved verbatim for reference.
> Per the cycle-2 contract, HIGHs recorded here are **NOT** recounted in the
> cycle-2 total unless explicitly carried forward above as PARTIALLY RESOLVED
> or STILL OPEN.

---

## Codex Review (Cycle 1)

# Cross-AI Plan Review

## Overall Assessment

The fetch/parse/normalize separation is sound, but the plans contain several blocking correctness issues. Most importantly, the raw path derives a month from the wrong part of `race_id`, calendar enumeration does not implement the locked three-level traversal, course codes are incorrect, and scraped identifiers will not match existing Kaggle identifiers. The normalizer also checks column presence rather than real schema compatibility. Overall implementation risk is **HIGH** until these contracts are corrected.

## Cross-Plan Blockers

- **HIGH:** `race_id[4:6]` is the course code, not the calendar month. A race ID is `YYYYPPCCDDRR`; its month cannot be derived from the ID.
- **HIGH:** `horse_race_id = f"{race_id}_{horse_number:02d}"` conflicts with the existing Kaggle value format, which is a 14-digit concatenation such as `20150101010101`.
- **HIGH:** Plan 01 creates eager imports for modules that do not yet exist. Importing `src.scraper.fetcher` in Wave 2 first executes `src.scraper.__init__` and fails on the missing parser/normalizer.
- **HIGH:** Calendar enumeration describes direct race-link extraction from the monthly page, contradicting D-04's month -> race day -> race traversal.
- **HIGH:** `COURSE_CODE_MAP` assigns incorrect codes to 福島 and 新潟.
- **HIGH:** The proposed race flag mapping is neither semantically correct nor demonstrably compatible with the Kaggle mapping.
- **HIGH:** No real HTML or overlap-period compatibility test validates the assumptions behind parsing.
- **MEDIUM:** There is no orchestrator/CLI that connects enumeration, fetching, parsing, and normalization for a date range.

---

# Plan 04-01: Package Skeleton and Dependencies

## Summary

The dependency selection and package separation are appropriate, but the package skeleton is internally inconsistent. It claims the package is importable while deliberately creating imports that fail until later waves. Because Python executes package `__init__.py` before importing a submodule, this can block Plans 04-02 and 04-03 themselves.

## Strengths

- Dependencies match locked decision D-02.
- Runtime dependencies are correctly placed outside the development extra.
- Chromium availability is explicitly considered.
- Package exports are clearly defined.

## Concerns

- **HIGH:** Eager imports of nonexistent modules make `src.scraper` and potentially `src.scraper.fetcher` unimportable.
- **MEDIUM:** The verification command hides import failure using `|| echo`, so it cannot serve as a quality gate.
- **MEDIUM:** `pip install playwright beautifulsoup4 lxml` does not install the project from `pyproject.toml` and can diverge from declared versions.
- **MEDIUM:** Chromium installation is machine state, not reproducible project configuration.
- **LOW:** `min_lines: 15` encourages unnecessary content in a simple `__init__.py`.
- **LOW:** Dependencies have minimum versions but no upper bounds, unlike existing core dependencies.

## Suggestions

- Keep `src/scraper/__init__.py` minimal until all modules exist, or use lazy exports.
- Move public re-exports entirely to Plan 04-05.
- Replace direct pip installation with the repository's standard environment installation command, such as `pip install -e .`.
- Add a documented setup command/script for `python -m playwright install chromium`.
- Make verification fail when package imports fail.

## Risk Assessment

**HIGH** because the package initialization strategy can prevent subsequent plans from importing their own modules.

---

# Plan 04-02: Fetcher and Calendar Enumeration

## Summary

The plan covers caching, retry, rate limiting, and raw persistence, but its date/path model and enumeration algorithm are incorrect. It also uses an expensive browser-per-request lifecycle that is unsuitable for several years of data.

## Strengths

- Fetching and parsing are cleanly separated.
- Non-empty file caching directly addresses SCRP-05.
- Sequential access and rate limiting are appropriate.
- Retry behavior and mocked unit tests are included.
- Monthly browser reuse is considered for enumeration.

## Concerns

- **HIGH:** `race_id[4:6]` is a JRA course code, not a month. Files will be placed under course-code directories such as `2022/06`, regardless of race month.
- **HIGH:** The monthly page is treated as though it directly contains all 12-digit race links. This does not implement D-04's three-level traversal.
- **HIGH:** `fetch_with_retry()` launches and closes Chromium for every attempt and race. This adds substantial overhead across thousands of races.
- **HIGH:** `fetch_race_html()` returns an output path even when all retries fail.
- **MEDIUM:** No validation restricts `race_id` to exactly 12 digits before using it in a path and URL.
- **MEDIUM:** HTML is written directly to the final file. Interruption can leave a non-empty partial file that future runs treat as valid.
- **MEDIUM:** No detection exists for CAPTCHA, block pages, login redirects, empty result tables, or unexpected final URLs.
- **MEDIUM:** `wait_until="networkidle"` can be unreliable on pages with persistent requests.
- **MEDIUM:** Rate limiting is applied only after success, while server errors can trigger repeated navigation.
- **MEDIUM:** No explicit browser/context cleanup using `finally` is specified.
- **MEDIUM:** The end date is represented only as `end_month`, so the API cannot precisely enforce May 31 for arbitrary ranges.
- **LOW:** `sorted(set(race_ids))` loses source/date metadata needed to determine the correct raw month.

## Suggestions

- Return structured enumeration records such as:
  ```python
  RaceRef(race_id="...", race_date=date(...))
  ```
  Use `race_date` to build `{YYYY}/{MM}` paths.
- Implement separate functions for:
  - `enumerate_race_day_urls(month)`
  - `enumerate_races_for_day(day_url)`
  - date-range filtering
- Introduce a fetch session/context manager that launches one browser and reuses a context/page across a batch.
- Validate `race_id` with `re.fullmatch(r"\d{12}", race_id)`.
- Write to a temporary file, validate content, then atomically rename it.
- Raise a typed exception or return `None` on terminal failure.
- Add content validation for result table presence and anti-bot pages.
- Add tests for two-level links, cancelled days, no races, malformed IDs, failure paths, and browser closure.
- Include a small controlled live smoke test outside CI.

## Risk Assessment

**HIGH** because raw files will be stored in incorrect month directories and race enumeration is likely incomplete.

---

# Plan 04-03: HTML Parser and Race Flags

## Summary

The helper-oriented parser design is reasonable, but the proposed field mapping has several correctness defects. Fixed table indices, incorrect course codes, incompatible identifiers, and speculative flag semantics make this the highest-risk plan.

## Strengths

- Parsing operates only on saved HTML.
- Horse weight and non-finisher edge cases are identified.
- Entries and results are separated according to existing schemas.
- Region and prize-money extraction are explicitly covered.
- All 20 flag keys are intended to be emitted.

## Concerns

- **HIGH:** Correct JRA codes are:
  - `01` 札幌
  - `02` 函館
  - `03` 福島
  - `04` 新潟
  - `05` 東京
  - `06` 中山
  - `07` 中京
  - `08` 京都
  - `09` 阪神
  - `10` 小倉

  The plan incorrectly maps 福島 to `02` and 新潟 to `03`.

- **HIGH:** The underscore in `horse_race_id` makes scraped keys incompatible with existing 14-digit Kaggle keys.
- **HIGH:** `head_count` is required by the plan but does not exist in RaceSchema.
- **HIGH:** `(牝)` is mapped to `race_flag_mare_only`, while the existing Kaggle mapping sends `牝` to `race_flag_filly_only`.
- **HIGH:** `(国際)` is not a graded-stakes indicator. Mapping it to `race_flag_graded_stakes` creates false graded races.
- **HIGH:** The fixed `td` index mapping assumes one exact table layout and does not verify headers.
- **MEDIUM:** D-10 expects age restrictions from conditions such as `3歳未勝利`, but the plan only sets `maiden`.
- **MEDIUM:** `新馬 == maiden` needs an explicit compatibility decision rather than assumption.
- **MEDIUM:** `race_flag_listed` is marked underivable even though listed grade information should be available.
- **MEDIUM:** The plan does not populate or explicitly default all RaceSchema fields, including `surface_detail`, `course_detail`, and `track_condition_detail`.
- **MEDIUM:** Grade parsing only mentions `G1/G2/G3` and may miss `GI/GII/GIII`, full-width forms, icons, and `L`.
- **MEDIUM:** Corner parsing assumes four positions, but races may provide two, three, or irregular passing points.
- **MEDIUM:** Demotion formats such as numeric position plus `降` are not precisely specified.
- **MEDIUM:** Required entry values may be missing for cancelled/scratched horses, conflicting with non-optional schema fields.
- **LOW:** "BS4 sanitizes HTML" is not meaningful data validation; parsing tolerance does not establish correctness.

## Suggestions

- Derive `COURSE_CODE_MAP` from one authoritative shared constant and test all ten venues.
- Match Kaggle's actual 14-digit `horse_race_id` format.
- Remove `head_count` or formally add it to the schema in a separate schema decision.
- Define a documented flag crosswalk based on `column_mapping.py`, including whether compatibility or semantic cleanup takes priority.
- Parse table columns by normalized `<th>` header names rather than fixed indices.
- Add golden HTML fixtures from multiple years, venues, grades, surfaces, and cancellation cases.
- Run the parser against several 2015-2021 pages and compare its output to known Kaggle rows.
- Distinguish missing/unknown (`None`) from confirmed absence (`False`) consistently.
- Fail or quarantine a race when required header/table elements are missing rather than emitting a partially valid record.

## Risk Assessment

**HIGH** because incorrect course and flag values would silently contaminate training data.

---

# Plan 04-04: Normalizer and Parquet Output

## Summary

The overall DataFrame-to-Parquet flow follows existing project patterns, but it does not actually guarantee schema compatibility. It also risks overwriting previously normalized batches and cannot correctly handle empty input under the stated tests.

## Strengths

- Scraped outputs remain separate from Kaggle outputs.
- Obstacle filtering propagates to all three tables.
- String identifier preservation is considered.
- Snappy/pyarrow settings match the existing converter.
- Audit integration and tests are planned.

## Concerns

- **HIGH:** No actual schema validation occurs. `audit_leakage()` checks feature leakage, not column completeness, types, uniqueness, or value ranges.
- **HIGH:** Creating DataFrames directly from dictionaries does not guarantee every schema column exists or appears in a stable order.
- **HIGH:** Empty input produces zero-column DataFrames, contradicting the requirement that output columns match all schema fields.
- **HIGH:** Each invocation overwrites `*_scraped.parquet`; normalizing one month after another can erase prior months.
- **MEDIUM:** Only string dtypes are enforced. Nullable integers, floats, and 20 nullable booleans may differ from Kaggle Parquet.
- **MEDIUM:** `audit_leakage([EntrySchema], entry_df)` will always flag `popularity` and `win_odds`, even though they intentionally belong in the standard entry table.
- **MEDIUM:** No duplicate-key checks exist for `race_id` or `horse_race_id`.
- **MEDIUM:** No referential-integrity checks ensure every entry/result race exists or entry/result keys match one-to-one.
- **MEDIUM:** Writes are not atomic, so a failed write can damage a prior valid dataset.
- **MEDIUM:** Loading all parsed races into one list may be unnecessary for a multi-year run.
- **LOW:** Tests checking only `object or string` are weaker than comparing pyarrow schemas.

## Suggestions

- Reindex every DataFrame using `Schema.model_fields` before dtype conversion.
- Add an explicit dtype map for every schema field.
- Reuse or extend schema-conformance and value-range validation from `validators.py`.
- Validate:
  - unique `race_id`
  - unique `horse_race_id`
  - entry/result one-to-one keys
  - foreign keys to race
  - entry/result row-count expectations
- Define output semantics explicitly: full rebuild, merge-and-deduplicate, or date-partitioned files.
- Write temporary Parquet files and atomically replace the final files only after validation succeeds.
- Treat empty input as a typed zero-row output with all expected columns.
- Compare the resulting pyarrow schema directly against Kaggle Parquet.
- Replace the standard-layer entry leakage warning with an audit appropriate to the feature boundary.

## Risk Assessment

**HIGH** because apparently successful Parquet files may be incompatible, incomplete, or overwrite prior data.

---

# Plan 04-05: Integration and Quality Gate

## Summary

Running both focused and full test suites is appropriate, but this plan validates only mocked components and imports. It does not prove that the pipeline can enumerate real races, fetch valid HTML, parse actual pages, or produce Kaggle-compatible output.

## Strengths

- Includes package-level import verification.
- Runs both scraper-specific and regression suites.
- Provides a single final quality gate.
- Allows root-cause fixes rather than merely recording failures.

## Concerns

- **HIGH:** All Playwright tests are mocked; SCRP-02 is not demonstrated against an actual page.
- **HIGH:** No end-to-end test connects enumeration -> fetch -> parse -> normalize.
- **MEDIUM:** The validation document mentions CLI commands that no plan implements.
- **MEDIUM:** No sample comparison against known Kaggle rows is required.
- **MEDIUM:** `pytest -x` stops after one failure and is less useful as the final comprehensive report.
- **MEDIUM:** No Ruff or mypy checks are included despite both being configured dependencies.
- **MEDIUM:** No completeness metric checks expected race counts by year/month.
- **LOW:** Updating `__init__.py` should not require a separate wave if it was kept valid from Plan 01.

## Suggestions

- Add a deterministic end-to-end test using a saved real HTML fixture.
- Add an opt-in live smoke test for one historical race and one calendar month.
- Implement the CLI/orchestrator referenced by validation or remove those manual commands.
- Compare overlap-period parsed records against Kaggle values.
- Add count-based sanity checks per month/year to detect incomplete enumeration.
- Run:
  ```bash
  pytest tests/
  ruff check src tests
  mypy src
  ```
- Validate that no real network request occurs in the normal unit suite.

## Risk Assessment

**MEDIUM-HIGH** because unit tests may all pass while the real site traversal and schema integration remain broken.

---

# Recommended Dependency Revision

1. **04-01:** Dependencies and import-safe empty package only.
2. **04-02A:** Calendar/day/race enumeration returning `race_id + race_date`.
3. **04-02B:** Shared Playwright session, atomic fetch, cache validation.
4. **04-03:** Header-driven parser with corrected IDs, course map, and flag crosswalk.
5. **04-04:** Strict typed normalization, integrity validation, atomic/partitioned output.
6. **04-05:** Orchestrator plus fixture-based end-to-end and opt-in live smoke validation.
7. **04-06:** Final exports, full tests, lint, type checks, and overlap compatibility report.

# Final Risk Assessment

**Overall risk: HIGH.**

The architecture is directionally correct, but the current plans can produce incomplete enumeration, incorrectly located raw files, wrong course and race-flag values, and identifiers that cannot join to Kaggle data. These are silent data-quality failures that would propagate into model training and EV evaluation, so they should be corrected before implementation begins.
