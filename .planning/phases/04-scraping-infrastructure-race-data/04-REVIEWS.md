---
phase: 4
reviewers: [codex]
reviewed_at: 2026-06-12T23:15:25Z
plans_reviewed:
  - 04-01-PLAN.md
  - 04-02-PLAN.md
  - 04-03-PLAN.md
  - 04-04-PLAN.md
  - 04-05-PLAN.md
---

# Cross-AI Plan Review — Phase 4

## Codex Review

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

---

## Consensus Summary

### Agreed Strengths

- Fetch/parse/normalize separation is architecturally sound and follows specification section 13
- Dependency selection matches locked decision D-02 (Playwright, BS4, lxml)
- SCRP-05 dedup via file-existence check is correctly designed
- Retry logic with exponential backoff is appropriate
- Separate Parquet output files (race_scraped.parquet) avoid corrupting validated Kaggle data
- Obstacle filtering propagates to all three tables
- Snappy/pyarrow settings match the existing converter

### Agreed Concerns

The following concerns are identified as blocking correctness issues that would cause silent data corruption:

1. **race_id month derivation is wrong** (HIGH) -- `race_id[4:6]` is the course code, not a month. Raw files will be stored in wrong directories. The enumeration must return `race_date` alongside `race_id` to build correct paths.

2. **horse_race_id format incompatibility** (HIGH) -- `f"{race_id}_{horse_number:02d}"` produces `"202206010101_01"` while Kaggle uses 14-digit concatenation `"20220601010101"`. Phase 6 integration would fail silently.

3. **Eager imports in __init__.py** (HIGH) -- Importing `src.scraper.fetcher` triggers `src.scraper.__init__` which imports nonexistent parser/normalizer, blocking all subsequent plans.

4. **Calendar enumeration does not implement D-04** (HIGH) -- The plan extracts race links directly from monthly pages, but D-04 specifies a 3-level traversal: month -> race day -> individual races. This will likely miss races.

5. **COURSE_CODE_MAP has wrong codes** (HIGH) -- 福島 maps to `02` (should be `03`) and 新潟 maps to `03` (should be `04`). This silently corrupts course identification.

6. **Race flag semantics are incorrect** (HIGH) -- `(国際)` mapped to `race_flag_graded_stakes` is wrong (international designation, not grade). `(牝)` maps to `race_flag_mare_only` but Kaggle uses `race_flag_filly_only`. No crosswalk against `column_mapping.py` is defined.

7. **No schema validation in normalizer** (HIGH) -- `audit_leakage()` checks for post-race column leakage, not column completeness, types, or value ranges. Empty input produces zero-column DataFrames.

8. **Normalizer overwrites on each invocation** (HIGH) -- Each call to `normalize_to_parquet` writes `*_scraped.parquet`, erasing any prior batch. No append/merge semantics defined.

9. **No end-to-end test** (HIGH) -- All Playwright tests are mocked. No test validates the full enumeration -> fetch -> parse -> normalize pipeline, even with saved HTML fixtures.

10. **Fixed td index parsing** (HIGH) -- Column extraction uses hardcoded `<td>` indices, which will break if netkeiba changes table layout. Header-driven parsing is more robust.

### Divergent Views

Not applicable -- single reviewer.

### Recommended Actions Before Implementation

1. Fix `race_id` path derivation: enumeration must return `(race_id, race_date)` tuples; use `race_date` for `{YYYY}/{MM}` paths
2. Fix `horse_race_id` to use 14-digit format matching Kaggle: `f"{race_id}{horse_number:02d}"`
3. Make `__init__.py` import-safe (empty or lazy) until Plan 05 integration
4. Implement 3-level calendar traversal per D-04 with separate functions for each level
5. Correct `COURSE_CODE_MAP`: 福島=03, 新潟=04 (derive from authoritative source or existing Kaggle data)
6. Build a flag crosswalk table mapping netkeiba text patterns to exact `race_flag_*` field names, validated against `column_mapping.py`
7. Add schema-conformance validation (column completeness, dtype enforcement) to normalizer using `Schema.model_fields`
8. Define normalizer output semantics (append vs overwrite vs date-partitioned)
9. Add a fixture-based end-to-end test using saved real HTML
10. Add `race_id` format validation (`re.fullmatch(r"\d{12}", race_id)`)
