---
phase: quick-260614-mfq
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/scraper/enumeration.py
  - src/scraper/orchestrator.py
  - tests/scraper/test_enumeration.py
autonomous: true
requirements:
  - MFQ-01

must_haves:
  truths:
    - "keiba scrape with a wide date range shows a per-month tqdm progress bar on stderr during the enumerate phase"
    - "enumerate_races(progress=False) produces identical output to enumerate_races(progress=True)"
    - "Existing enumeration/orchestrator/end-to-end tests stay green"
  artifacts:
    - path: "src/scraper/enumeration.py"
      provides: "enumerate_races with a progress: bool = True param wrapping the month loop in tqdm"
      contains: "tqdm"
    - path: "src/scraper/orchestrator.py"
      provides: "run_scrape threads progress into both enumerate_races call sites"
      contains: "enumerate_races(start_date, end_date"
    - path: "tests/scraper/test_enumeration.py"
      provides: "progress=False on every call + one output-neutrality test"
      contains: "progress=True"
  key_links:
    - from: "src/scraper/orchestrator.py (run_scrape)"
      to: "src/scraper/enumeration.py (enumerate_races)"
      via: "progress=progress kwarg at both call sites"
      pattern: "enumerate_races\\([^)]*progress=progress"
    - from: "src/scraper/enumeration.py (enumerate_races month loop)"
      to: "tqdm"
      via: "tqdm(months, desc=\"Enumerating\", unit=\"month\", total=N, file=sys.stderr)"
      pattern: 'tqdm\([^)]*desc="Enumerating"'
---

<objective>
Add a tqdm per-month progress bar to the `enumerate_races` enumeration phase so `keiba scrape` no longer appears "stuck" during the ~18-minute, 53-month calendar walk that precedes the race-fetch bar (already shipped in quick-task 260614-lw5).

Purpose: Surface the previously-silent enumeration phase with the same stderr-stream, auto-hide-under-capture pattern already proven by the race-fetch bar. This is a pure UX/observability change -- output behavior is byte-identical.

Output: Modified `enumerate_races` (new `progress: bool = True` param + precomputed month list + tqdm wrapper), `run_scrape` threading `progress` into both `enumerate_races` call sites, and updated `test_enumeration.py` (7 calls get `progress=False`, 1 new output-neutrality test).
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@.planning/STATE.md
@src/scraper/enumeration.py
@src/scraper/orchestrator.py
@tests/scraper/test_enumeration.py

# Key facts (verified by reading the files in planning)
# - enumerate_races signature: enumerate_races(start_date, end_date, fetch_html). New: add progress: bool = True as LAST param.
# - Month loop is `while cursor <= end_month_anchor:` at enumeration.py:298. Cursor advancement: month==12 -> next year Jan, else month+1, all on day-1.
# - orchestrator.py already imports `tqdm` and `sys` (lines 48, 53); enumerate_races call sites at line 146 (live) and line 159 (offline).
# - test_orchestrator.py and test_end_to_end.py MOCK enumerate_races (patch), so they are unaffected by the real signature change -- but must be re-run to verify.
# - enumerate_races_for_day and enumerate_race_day_urls are SEPARATE functions with NO progress param and must NOT be touched.
# - tqdm is already a runtime dep (added in 260614-lw5). No pyproject.toml change.
# - enumerate_races is publicly exported in src/scraper/__init__.py (lines 19, 36) -- adding a param with a default is backward-compatible; do NOT change the export list.
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add tqdm month-loop progress bar to enumerate_races</name>
  <files>src/scraper/enumeration.py</files>
  <behavior>
    - enumerate_races(progress=True) iterates the SAME set of (year, month) tuples in the SAME order as the current while-loop (behavior-preserving refactor).
    - With progress=True, the month loop is wrapped in tqdm(desc="Enumerating", unit="month", total=<month count>, file=sys.stderr).
    - month count = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month) + 1.
    - enumerate_races(progress=False) iterates the plain months list with NO tqdm wrapper (no tqdm import side-effect on output).
    - The body (per-month enumerate_race_day_urls, boundary date filter, per-day enumerate_races_for_day, dedup) is byte-for-byte unchanged.
    - Boundary filter and dedup logic are NOT modified.
  </behavior>
  <action>Add `import sys` and `from tqdm import tqdm` to the existing imports at the top of src/scraper/enumeration.py (sys is NOT currently imported; tqdm is not imported in this module yet). Then change `enumerate_races` per D-04 (traversal) preserved + progress per task spec:

1. Add `progress: bool = True` as the LAST parameter of the `enumerate_races` signature, after `fetch_html`. Do NOT reorder existing params. Update the docstring's Parameters section to document `progress` (mirror the exact wording already used for run_scrape's progress param: "When True, wrap the month iteration with a tqdm bar on stderr. When False, iterate the plain list (no tqdm) -- use for log-file redirection / CI / tests.").

2. PRECOMPUTE the month list with the IDENTICAL cursor-advancement logic currently in the while-loop (lines 295-313): start `cursor = datetime.date(start_date.year, start_date.month, 1)`, end `end_month_anchor = datetime.date(end_date.year, end_date.month, 1)`, collect `(cursor.year, cursor.month)` into a `months: list[tuple[int, int]]` list while `cursor <= end_month_anchor`, advancing the same way (month==12 -> datetime.date(year+1, 1, 1), else datetime.date(year, month+1, 1)). This is behavior-preserving -- same iteration order, same month set.

3. Compute `total = len(months)` (equivalently `(end_date.year - start_date.year) * 12 + (end_date.month - start_date.month) + 1`). These two MUST agree; use `len(months)` for the tqdm `total` so they cannot diverge.

4. Replace the `while cursor <= end_month_anchor:` outer loop with `for year, month in (tqdm(months, desc="Enumerating", unit="month", total=total, file=sys.stderr) if progress else months):`. The `year, month = cursor.year, cursor.month` line inside the old loop body is now the loop variable binding -- DELETE that single line; keep the rest of the body verbatim.

5. DO NOT wrap the inner `for day_url, race_day_date in enumerate_race_day_urls(...)` or `for ref in enumerate_races_for_day(...)` loops in tqdm. Only the outer month loop is wrapped.

6. DO NOT change parse_calendar_month_html, parse_race_day_html, enumerate_race_day_urls, enumerate_races_for_day, BASE_URL, or either regex constant. DO NOT change the boundary filter condition (`race_day_date < start_date or race_day_date > end_date`) or the dedup `seen_ids` logic.

tqdm MUST write to `file=sys.stderr` (same stream as loguru). tqdm auto-hides under pytest capture / non-TTY, which is what makes the existing tests output-safe once they pass progress=False (Task 3).</action>
  <verify>
    <automated>cd /Users/hart/develop/keiba-ai-v2 && ruff check src/scraper/enumeration.py && mypy src/scraper/enumeration.py && python -c "from src.scraper.enumeration import enumerate_races; import inspect; sig = inspect.signature(enumerate_races); assert 'progress' in sig.parameters; assert sig.parameters['progress'].default is True; print('signature ok')"</automated>
  </verify>
  <done>enumerate_races has a `progress: bool = True` last param; the month loop is precomputed into a list and wrapped in tqdm(desc="Enumerating", unit="month", total=len(months), file=sys.stderr) when progress=True, plain iteration when progress=False; boundary filter and dedup logic are unchanged; ruff + mypy pass on the file.</done>
</task>

<task type="auto">
  <name>Task 2: Thread progress into enumerate_races in run_scrape</name>
  <files>src/scraper/orchestrator.py</files>
  <action>In src/scraper/orchestrator.py, `run_scrape` already has a `progress: bool = True` param (added in 260614-lw5). Thread it into enumerate_races at BOTH call sites:

1. Line ~146 (live branch): change `race_refs = enumerate_races(start_date, end_date, enum_transport)` to `race_refs = enumerate_races(start_date, end_date, enum_transport, progress=progress)`.

2. Line ~159 (offline branch): change `race_refs = enumerate_races(start_date, end_date, fetch_html)` to `race_refs = enumerate_races(start_date, end_date, fetch_html, progress=progress)`.

DO NOT change run_scrape's signature, the docstring's `progress` description (it already documents the race-fetch bar and is still accurate -- the same `progress` flag now also governs the enumeration bar, which is consistent), the `_fetch_and_parse` call sites (they already pass `progress=progress`), or anything else in the file. Add `progress=progress` ONLY to the two enumerate_races calls. No new imports are needed (tqdm and sys are already imported for the race-fetch bar).</action>
  <verify>
    <automated>cd /Users/hart/develop/keiba-ai-v2 && ruff check src/scraper/orchestrator.py && mypy src/scraper/orchestrator.py && grep -c "enumerate_races(start_date, end_date" src/scraper/orchestrator.py | grep -q "2" && echo "both call sites present"</automated>
  </verify>
  <done>Both enumerate_races call sites in run_scrape pass `progress=progress`. The existing race-fetch tqdm bar and `_fetch_and_parse` threading are untouched. ruff + mypy pass.</done>
</task>

<task type="auto">
  <name>Task 3: Update test_enumeration.py -- add progress=False and a new output-neutrality test</name>
  <files>tests/scraper/test_enumeration.py</files>
  <action>In tests/scraper/test_enumeration.py, make two changes:

1. Add `progress=False` as a keyword arg to EVERY existing `enumerate_races(...)` call in the TestEnumerateRaces class. There are exactly 7 such calls (the ones whose first three positional args are a start_date, end_date, and fake fetch). The calls are at approximately lines 250, 269, 288, 304, 323, 336, 382. Do this by appending `, progress=False` before the closing paren of each call. DO NOT add `progress` to:
   - `enumerate_races_for_day(...)` calls (separate function, no progress param -- lines ~352, 364, etc.)
   - `enumerate_race_day_urls(...)` calls (separate function -- lines ~415, 429)
   - `parse_calendar_month_html(...)` or `parse_race_day_html(...)` calls (separate functions)
   This is a mechanical 7-call edit. The fake fetch's `.seen` recording, assertions, and everything else in these 7 tests stay unchanged.

2. Add ONE new test method to the TestEnumerateRaces class, after `test_multi_month_traversal`, named `test_progress_flag_is_output_neutral`. Use `test_multi_month_traversal` as the structural base (same multi-month fake table: a Jan calendar with one day + a Feb calendar with one day, each day listing one race). Build the table ONCE, create TWO separate fake fetch callables from the SAME table (two calls to `_make_fake_fetch(table)` so each records its own `.seen`), then call `enumerate_races(datetime.date(2022, 1, 1), datetime.date(2022, 2, 28), fake_off, progress=False)` and `enumerate_races(datetime.date(2022, 1, 1), datetime.date(2022, 2, 28), fake_on, progress=True)`. Assert:
   - `[(r.race_id, r.race_date) for r in refs_off] == [(r.race_id, r.race_date) for r in refs_on]` (same race_ids, same race_dates, same order).
   - Both result lists are non-empty (sanity: the table actually yields races).
   DO NOT assert anything about tqdm's rendered text (library behavior, out of scope). DO NOT capture stderr. The test proves output neutrality at the RaceRef level, not rendering equality.

Why two fakes: `_make_fake_fetch` returns a closure with its own `.seen` list; calling enumerate_races twice on the same fake would append to the same seen list and the second call's URL pattern would be conflated with the first. Two fakes from the same table keeps each call's fetch log independent (and lets the test optionally assert each saw the same URLs, though that is NOT required -- only the RaceRef output-neutrality is asserted).</action>
  <verify>
    <automated>cd /Users/hart/develop/keiba-ai-v2 && python -m pytest tests/scraper/test_enumeration.py tests/scraper/test_orchestrator.py tests/scraper/test_end_to_end.py -x -q</automated>
  </verify>
  <done>All 7 existing enumerate_races calls in TestEnumerateRaces pass progress=False; the new test_progress_flag_is_output_neutral test passes and asserts identical (race_id, race_date) lists between progress=True and progress=False; the full scraper test suite (test_enumeration.py, test_orchestrator.py, test_end_to_end.py) is green; enumerate_races_for_day and enumerate_race_day_urls calls are untouched.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| (none new) | This change adds a progress bar to an already-trusted code path. No new input crosses a trust boundary; no new network, file, or IPC surface is introduced. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-mfq-01 | Information Disclosure | tqdm stderr output | accept | tqdm writes to stderr (same stream loguru already uses) and auto-hides under non-TTY / pytest capture; no sensitive data is emitted (only month count + unit label). Default progress=True is the user-facing UX the task is adding; tests opt out via progress=False. |
| T-mfq-SC | Tampering | (no package install) | accept | No new packages installed -- tqdm is already a runtime dep added in 260614-lw5 and is a well-established PyPI package. No Package Legitimacy Gate checkpoint needed. |
</threat_model>

<verification>
- `ruff check src/scraper/enumeration.py src/scraper/orchestrator.py tests/scraper/test_enumeration.py` passes.
- `mypy src/scraper/enumeration.py src/scraper/orchestrator.py` passes.
- `python -m pytest tests/scraper/test_enumeration.py tests/scraper/test_orchestrator.py tests/scraper/test_end_to_end.py -q` all green.
- `enumerate_races` has `progress: bool = True` as last param; both run_scrape call sites pass `progress=progress`.
- New `test_progress_flag_is_output_neutral` test passes and asserts identical RaceRef output between the two modes.
</verification>

<success_criteria>
- enumerate_races shows a per-month tqdm bar on stderr when progress=True (visible only on TTY, auto-hidden otherwise).
- enumerate_races(progress=False) is byte-for-byte output-identical to enumerate_races(progress=True) at the RaceRef level.
- run_scrape threads its existing progress flag into enumerate_races at both the live and offline call sites.
- All existing scraper tests stay green; one new output-neutrality test is added and green.
- ruff + mypy pass on all changed files.
- Single atomic commit: `feat(04): add tqdm progress bar to enumerate_races`.
</success_criteria>

<output>
Create `.planning/quick/260614-mfq-tqdm-enumerate-races/260614-mfq-SUMMARY.md` when done
</output>
