---
phase: 04-scraping-infrastructure-race-data
plan: 07
subsystem: scraper-flag-derivation
tags: [gap-closure, uat, flag-derivation, graded-stakes, parser]
requires:
  - "04-04-PLAN.md (FLAG_CROSSWALK + Plan-04 Decision D4 context)"
  - "04-UAT.md (UAT-Test-3 root cause)"
provides:
  - "src/scraper/flag_crosswalk.py with ('(国際)', 'race_flag_graded_stakes') REMOVED; GRADE_REGEX is the sole source of true graded detection; Phase 6 reconciliation note in docstring"
  - "src/scraper/parser.py harvests grade-bearing <h1> text into a grade_haystack so GRADE_REGEX fires for true G1 races even when the bare <title> race_name lacks the GI token (Rule 1 deviation)"
  - "tests/scraper/test_parser.py: inverted (国際) test, new ヒヤシンスS listed regression test, filtered coverage-guard parametrize"
affects:
  - "src/pipeline/column_mapping.py line 68 still maps レース記号/(国際) -> race_flag_graded_stakes (Kaggle-side, out of scope; Phase 6 reconciles)"
  - "feature-layer consumers of race_flag_graded_stakes (no longer false-True for Listed/OP-international races)"
tech-stack:
  added: []
  patterns:
    - "Filter parametrize set with inline citing comment instead of xfail for intentional, documented coverage gaps"
    - "Harvest grade-bearing <h1> as a separate haystack distinct from the public race_name field"
key-files:
  created: []
  modified:
    - src/scraper/flag_crosswalk.py
    - src/scraper/parser.py
    - tests/scraper/test_parser.py
decisions:
  - "UAT-Test-3 overrides Plan-04 Decision D4: (国際)->graded mapping is rejected as a semantic error (international designation is NOT graded). Removed from FLAG_CROSSWALK."
  - "GRADE_REGEX (GI/GII/GIII/G1/G2/G3/JG*/重賞/full-width ＧＩ) is the SOLE source of race_flag_graded_stakes=True."
  - "Kaggle-side column_mapping.py (国際)->graded mapping left untouched — Phase 6 (Data Integration) reconciles the divergence before joining the two sources."
  - "Rule 1 deviation: parse_race_html extended to harvest the second <h1> (grade-bearing, e.g. 第64回宝塚記念(GI)) into a grade_haystack fed to derive_race_flags. Required because removing the (国際) mapping exposed a latent bug where the bare <title> race_name lacks the GI token and GRADE_REGEX never fired."
metrics:
  duration: 371s
  completed: 2026-06-14T04:54:09Z
  tasks: 2
  files: 3
---

# Phase 04 Plan 07: UAT-Test-3 Gap Closure (Graded-Stakes Misclassification) Summary

Listed/OP-special races carrying the `(国際)` international-designation marker
no longer get `race_flag_graded_stakes=True`; true graded detection is sourced
solely from `GRADE_REGEX`, and a latent parser bug that would have left the
宝塚記念 G1 fixture graded-less is fixed in the same pass.

## What Was Built

### Task 1 — Remove the `(国際)->graded` mapping (source-side fix)

`src/scraper/flag_crosswalk.py`:

- Deleted `("(国際)", "race_flag_graded_stakes")` from `FLAG_CROSSWALK`
  (was line 66). The list now has 20 entries (was 21; the plan narrative
  said "20 -> 19" but the actual pre-fix count was 21, an off-by-one in
  the plan text — the substantive requirement, "remove the bad row," is
  satisfied).
- Replaced the module docstring's "Compatibility note on
  `(国際)->race_flag_graded_stakes`" section with a **Phase 6
  reconciliation note** that documents: (a) the scraper-side intentionally
  drops the mapping because `(国際)` is an international-designation marker,
  not graded; (b) the Kaggle-side `src/pipeline/column_mapping.py` line 68
  still maps `レース記号/(国際) -> race_flag_graded_stakes` and is out of
  scope for this gap fix; (c) Phase 6 (Data Integration) MUST reconcile
  the divergence — either remove the Kaggle-side mapping too, or introduce
  a new `race_flag_international` column on both sides.
- Left an inline comment where the row was removed
  (`# (国際) intentionally NOT mapped to graded_stakes — see Phase 6 note
  in docstring (UAT-Test-3)`) so future readers do not "fix" the gap by
  re-adding it.
- `GRADE_REGEX`, `_LISTED_REGEX`, `_STAKES_REGEX`, and the grade-detection
  block in `derive_race_flags` are UNCHANGED.

### Task 2 — Lock in the fix with regression tests + parser Rule 1 fix

`tests/scraper/test_parser.py`:

- Renamed `test_international_to_graded_stakes` ->
  `test_international_does_not_set_graded_stakes` and inverted the
  assertion: `derive_race_flags("4歳以上オープン (国際)(特指)(ハンデ)")`
  now asserts `race_flag_graded_stakes is None` (was `is True`). The
  `special_weight` and `handicap` assertions remain unchanged.
- Added `test_listed_international_not_graded` — the exact UAT-Test-3
  failure case locked in as a regression test. Calls
  `derive_race_flags("サラ系4歳以上オープン (国際)(ハンデ)",
  race_name="ヒヤシンスS(L)")` and asserts `graded_stakes is None`,
  `listed is True`, `handicap is True`. Docstring cites UAT-Test-3 and
  race_id `202405010809`.
- `test_grade_g1` and `test_grade_fullwidth` left UNCHANGED (regression
  guards for true graded detection via GRADE_REGEX).
- Updated `test_crosswalk_covers_all_kaggle_flag_targets` parametrize to
  filter `race_flag_graded_stakes` out of the target set with a citing
  comment (intentional Phase 6 deferral, not a coverage regression).
  The plan offered xfail OR filtered-parametrize; filtered-parametrize is
  cleaner and produces a passing test rather than an expected-failure.

`src/scraper/parser.py` (Rule 1 deviation, see below):

- `parse_race_html` now harvests the grade-bearing `<h1>` text on the
  page (netkeiba's SECOND `<h1>` carries `第64回宝塚記念(GI)`; the first
  `<h1>` is the site logo) into a `grade_haystack`. The haystack is fed
  to `derive_race_flags`, the `grade` field extractor, and the
  `grade_revision` extractor. The public `race_name` field stays bare
  (Plan-04 P04 decision unchanged).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Parser dropped the GI token, breaking the G1 fixture after Task 1**

- **Found during:** Task 2 (running `pytest tests/scraper/test_parser.py -x -q`)
- **Issue:** After Task 1 removed the `(国際)->graded` mapping,
  `test_flag_crosswalk_applied_on_graded_fixture` (the 宝塚記念 G1 fixture)
  failed: `race_flag_graded_stakes` came back `None`. Investigation showed
  the parser extracted `race_name='宝塚記念'` from `<title>` (bare, no GI
  token) and `race_condition='3歳以上オープン (国際)(指)(定量)'` (no GI token),
  so `GRADE_REGEX` never matched. The `(国際)` mapping had been setting
  `graded_stakes=True` for the wrong reason — by coincidence on this G1
  fixture (all G1 races are also `(国際)`). The plan's premise that
  "宝塚記念 is G1 so GRADE_REGEX matches" was wrong: GRADE_REGEX only
  matches if it SEES a G1 token, and the parser wasn't feeding it one.
  Netkeiba's actual grade label lives in a SECOND `<h1>` element
  (`<h1>第64回宝塚記念(GI)</h1>`, line 413 of the fixture) — the first
  `<h1>` is the site logo.
- **Fix:** Extended `parse_race_html` to scan all `<h1>` elements, harvest
  any text matching `_GRADE_TOKEN_RE`, and feed it (combined with the bare
  `race_name`) into a new `grade_haystack`. The haystack is used for:
  (a) `grade` field extraction, (b) `grade_revision` extraction, and
  (c) `derive_race_flags`'s `race_name` argument. The public `race_name`
  field stays bare per Plan-04 P04. Bonus: `grade_revision='64'` and
  `grade='GI'` now extract correctly (were `None` on this fixture because
  the bare `<title>` lacks `第64回` and `(GI)`).
- **Why Rule 1 not Rule 4:** The fix is small and surgical (one new
  harvest loop, three call-site updates), localized to a single function
  in `src/scraper/parser.py`, does not change any public field shape, and
  is REQUIRED for the plan's success criterion ("G1/GII/GIII/重賞 races
  still set the flag") to hold. It is a correctness bug directly caused
  by Task 1's change (Task 1 removed the only mechanism that was setting
  graded for this fixture, even if for the wrong reason).
- **Files modified:** `src/scraper/parser.py` (not in plan's declared
  `<files_modified>` — declared as `flag_crosswalk.py` +
  `test_parser.py` only)
- **Commit:** `e5144a2`

### Plan Narrative Inaccuracies (non-blocking, documented for transparency)

**2. [Plan text off-by-one] FLAG_CROSSWALK count was 21, not 20**

- **Found during:** Task 1 verification
- **Issue:** Plan `<action>` said "The FLAG_CROSSWALK list now has 19
  entries (was 20)." Actual pre-fix count was 21 entries (multiple sources
  map to the same target — e.g. two `(見習騎手)` forms, two `(指)`/`[指]`
  forms). Post-fix count is 20.
- **Action:** Followed the substantive requirement ("remove the bad row")
  rather than the narrative count. Did NOT add a `len == 19` assertion to
  the verification (it would have failed spuriously).

## Verification

All five verification commands from the plan pass:

| Check | Command | Result |
|-------|---------|--------|
| Parser test suite green | `pytest tests/scraper/test_parser.py -x -q` | 94 passed |
| Bad row removed | `python -c "from src.scraper.flag_crosswalk import FLAG_CROSSWALK; assert ('(国際)', 'race_flag_graded_stakes') not in FLAG_CROSSWALK"` | UAT-Test-3 row removed |
| Phase 6 reconciliation note present | `grep -c "Phase 6" src/scraper/flag_crosswalk.py` | 5 (>= 1) |
| UAT-Test-3 citations in tests | `grep -c "UAT-Test-3" tests/scraper/test_parser.py` | 5 (>= 2) |
| No regression in broader scraper suite | `pytest tests/scraper/ -q` | 209 passed, 1 skipped (opt-in live smoke), 1 pre-existing non-blocking FutureWarning |

Plus the plan's Task 1 `<verify>` python one-liner passes (all four
behavioral assertions: non-graded `(国際)` returns None; true GI returns
True; listed `(L)` returns listed=True / graded=None; handicap and
special_weight mappings unchanged).

## Success Criteria

- [x] UAT-Test-3 FIXED: non-graded international-designation races no longer set `race_flag_graded_stakes=True`
- [x] True graded detection (GRADE_REGEX) unaffected — G1/GII/GIII/重賞 races still set the flag (verified on 宝塚記念 fixture via the parser Rule 1 fix)
- [x] The ヒヤシンスS case (Listed + `(国際)`) returns `graded_stakes=None` — locked in as `test_listed_international_not_graded`
- [x] Phase 6 reconciliation requirement documented in source (module docstring) and test (parametrize filter comment), not silently deferred
- [x] No regression in the broader scraper test suite (209 passed, 1 skipped)

## Threat Flags

None. The change REDUCES attack surface: a false `True` on
`race_flag_graded_stakes` (which could mislead feature engineering or any
EV calc that conditions on grade) is no longer produced for non-graded
international races. The parser `<h1>` harvest is a read-only DOM scan
with no new network or filesystem surface.

## Commits

| Hash | Type | Message |
|------|------|---------|
| `d7de81a` | fix | `fix(04-07): remove (国際)->graded_stakes mapping (UAT-Test-3)` |
| `e5144a2` | test | `test(04-07): lock in UAT-Test-3 flag fix + parser grade-haystack (Rule 1)` |

## Self-Check: PASSED

All three modified files exist on disk; both per-task commit hashes (`d7de81a`,
`e5144a2`) resolve in `git log --all`. No post-commit file deletions detected.
