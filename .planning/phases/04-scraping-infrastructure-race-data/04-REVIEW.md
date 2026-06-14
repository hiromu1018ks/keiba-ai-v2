---
phase: 04-scraping-infrastructure-race-data
reviewed: 2026-06-14T14:15:00Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - src/scraper/enumeration.py
  - src/scraper/flag_crosswalk.py
  - src/scraper/parser.py
  - tests/scraper/fixtures/html/calendar_202306.html
  - tests/scraper/test_end_to_end.py
  - tests/scraper/test_enumeration.py
  - tests/scraper/test_parser.py
findings:
  critical: 2
  warning: 4
  info: 3
  total: 9
status: issues_found
---

# Phase 04: Code Review Report (Gap-Closure — Plans 04-07 / 04-08)

**Reviewed:** 2026-06-14T14:15:00Z
**Depth:** standard
**Files Reviewed:** 7
**Status:** issues_found

## Summary

This review covers the two UAT-driven fixes shipped after `f01afda`:
Plan 04-07 (UAT-Test-3, `(国際)` -> graded mapping removed; parser `grade_haystack`
harvesting from second `<h1>`) and Plan 04-08 (UAT-Test-6, calendar URL form changed
from `/race/calendar/{YYYYMM}/` to `/race/list/{YYYYMM}/`).

The headline changes are directionally correct: the URL form change is
live-verified and well-guarded by the new URL-contract test class, and removing
the `(国際)` -> graded mapping is semantically right. However, the gap-closure
introduces two new BLOCKER-tier issues that the planning notes did not surface
and that the current test suite does not catch:

1. `src/scraper/flag_crosswalk.py` exports `GRADE_PATTERNS` in `__all__` but
   never defines the symbol. `from src.scraper.flag_crosswalk import *` and
   any direct `import GRADE_PATTERNS` raise `ImportError`/`AttributeError`. The
   pre-existing `_GRADE_REGEX` is what the module actually uses internally.
2. `src/scraper/parser.py` sets the `grade` field to the raw captured token,
   which for Listed races yields `'(L)'` (parentheses included). The
   `RaceSchema.grade` docstring expects `'G1/G2/G3/G/listed'`; Kaggle's
   `リステッド・重賞競走` source column carries bare tokens. This is a
   schema-consistency defect that will corrupt Phase 6 joins and
   downstream feature columns.

Additional WARNING-level defects: `_GRADE_REGEX` in `flag_crosswalk.py` has the
alternation order reversed relative to `parser._GRADE_TOKEN_RE`, so `GII`/`GIII`
tokens are leftmost-matched as `GI` (currently harmless because `derive_race_flags`
only tests for a match, but it is a latent footgun and asymmetric with the parser);
a stale docstring in `test_parser.py:10-11` still documents the removed mapping as
an invariant; and a misleading test comment in `test_parser.py:430` attributes
the G1 fixture's graded_stakes=True to `(国際)` when it now comes from the
`<h1>`-harvested GI token.

## Critical Issues

### CR-01: `GRADE_PATTERNS` exported in `__all__` but never defined — `ImportError` on star-import

**File:** `src/scraper/flag_crosswalk.py:210`
**Issue:** The module's `__all__` list declares `"GRADE_PATTERNS"`, but no
symbol of that name is defined anywhere in the file. The module's actual
grade-detection regex is the private `_GRADE_REGEX` (line 119), and there is
no `GRADE_PATTERNS` list (unlike `CLASS_PATTERNS` which is real).

Verified empirically:
```
>>> from src.scraper.flag_crosswalk import GRADE_PATTERNS
ImportError: cannot import name 'GRADE_PATTERNS' from 'src.scraper.flag_crosswalk'
>>> from src.scraper.flag_crosswalk import *
AttributeError: module 'src.scraper.flag_crosswalk' has no attribute 'GRADE_PATTERNS'
```

The existing test suite passes only because no test performs either import —
but this is a latent landmine: the moment any consumer (Phase 5/6 normalizer,
downstream feature code, or an IDE auto-completion that follows `__all__`)
attempts to use `GRADE_PATTERNS`, the module becomes un-importable. This is
also a broken public contract: `__all__` is the documented surface, and
advertising a non-existent symbol is a defect regardless of whether any
current caller trips it.

**Fix:** Pick one of two consistent resolutions. Either (a) remove
`GRADE_PATTERNS` from `__all__` since the actual grade logic lives in the
private `_GRADE_REGEX` and `derive_race_flags`, or (b) add a real public
export that aliases the private regex (e.g. `GRADE_PATTERNS = _GRADE_REGEX`).

```python
# Option (a) — recommended; the module has no need to expose the regex
# directly because derive_race_flags is the public API.
__all__ = ["FLAG_CROSSWALK", "CLASS_PATTERNS", "derive_race_flags"]
```

### CR-02: `grade` field captures parenthesized token `'(L)'` for Listed races — schema inconsistency

**File:** `src/scraper/parser.py:439-443`
**Issue:** The parser extracts the `grade` field via
`_GRADE_TOKEN_RE.search(grade_haystack)`, and `_GRADE_TOKEN_RE` includes
`\(L\)|（L）|リステッド` as alternatives (line 116). For the Listed fixture
`202405010809.html` (`ヒヤシンスS(L)`), the harvested grade is the literal
string `'(L)'` — including the parentheses:

Verified empirically:
```
>>> race = parse_race_html(Path('tests/scraper/fixtures/html/202405010809.html'))['race']
>>> race['grade']
'(L)'
```

This contradicts:
- `src/schemas/race.py:68` — `grade` field documented as
  `"G1/G2/G3/G/listed or empty"` (bare tokens, no parens).
- `src/pipeline/column_mapping.py:78` — Kaggle's source column for `grade` is
  `リステッド・重賞競走`, which carries bare graded/listed tokens on the
  Kaggle side, not parenthesized forms.

Phase 6 will join scraped 2022+ rows against Kaggle rows on (among other
keys) the `grade` column. A scraped `'(L)'` will never equal a Kaggle `'L'`
or `'リステッド'`, silently producing `None`/NaN on the join and corrupting
any feature column that keys off `grade`. The Plan 04-07 docstring claims
Phase 6 "MUST reconcile" divergences, but this one is introduced by the
parser itself, not by a Kaggle-side mapping choice, and should be fixed at
the source.

The bug is also somewhat hidden by the G1 fixture test
(`test_flag_crosswalk_applied_on_graded_fixture`), which only asserts the
boolean flag and never inspects `race['grade']`. The graded-token path
returns `'GI'` (bare, no parens), so it does not surface this issue.

**Fix:** Strip surrounding parentheses from the captured token, and do not
use the bare `リステッド` string as a grade value — normalize to `'L'` to
match the schema's expected form. Alternatively, exclude the Listed
alternatives from `_GRADE_TOKEN_RE` entirely (since Listed is already
classified by `_LISTED_REGEX` inside `derive_race_flags`) and leave
`grade=None` for non-graded races.

```python
# Option A: normalize the captured token.
if grade_haystack:
    grade_token = _GRADE_TOKEN_RE.search(grade_haystack)
    if grade_token:
        raw = grade_token.group(1)
        # Strip parentheses and normalize Listed variants to bare 'L'.
        grade = raw.strip("()（）")
        if grade in {"L", "リステッド"}:
            grade = "L"
        # else keep the bare graded token (GI/GII/GIII/G1/...).
```

## Warnings

### WR-01: `_GRADE_REGEX` alternation order is wrong — `GII`/`GIII` leftmost-match as `GI`

**File:** `src/scraper/flag_crosswalk.py:119-122`
**Issue:** `_GRADE_REGEX` lists alternatives in the order
`GI|GII|GIII|G1|G2|G3|JGI|JGII|JGIII|JG1|JG2|JG3|ＧＩ|ＧＩＩ|ＧＩＩＩ`.
Python `re` alternation returns the **first** matching alternative at a
position, not the longest, so on the string `'GII'` it matches `'GI'`
(verified empirically). The same applies to `'J.GII'` -> `'GI'` and
`'GIII'` -> `'GI'`.

By contrast, `parser._GRADE_TOKEN_RE` (line 108) correctly orders the
alternatives longest-first (`GIII|GII|GI|...`), which is why the comment at
`parser.py:104-107` explicitly warns about this ordering.

For `derive_race_flags` this is currently harmless because the code only tests
`if _GRADE_REGEX.search(haystack):` (any match sets graded_stakes=True) and
never inspects the captured group. But:

1. It is an inconsistency between two regexes that the comment in
   `parser.py:104` claims are coordinated ("Delegates full classification to
   flag_crosswalk._GRADE_REGEX").
2. Any future caller that reads `_GRADE_REGEX.search(s).group(0)` to extract
   a grade token will get a silently wrong result.
3. It is the exact footgun the parser's own comment warns against.

**Fix:** Reorder `_GRADE_REGEX` to longest-first, mirroring `_GRADE_TOKEN_RE`:

```python
_GRADE_REGEX = re.compile(
    r"(?:GIII|GII|GI|"             # half-width: long -> short
    r"JGIII|JGII|JGI|"
    r"G3|G2|G1|"
    r"JG3|JG2|JG1|"
    r"ＧＩＩＩ|ＧＩＩ|ＧＩ)"
)
```

### WR-02: Stale docstring in `test_parser.py:10-11` documents the removed mapping as an invariant

**File:** `tests/scraper/test_parser.py:10-11`
**Issue:** The module docstring still lists the removed mapping under HIGH #6:

```
* HIGH #6  -- flag crosswalk semantics: ``(牝)`` -> ``race_flag_filly_only``
  (NOT ``race_flag_mare_only``); ``(国際)`` -> ``race_flag_graded_stakes``.
```

Plan 04-07 explicitly removed the `(国際)` -> `race_flag_graded_stakes`
mapping (it is the entire point of the fix). The docstring now contradicts
both the production code and the regression test
`test_international_does_not_set_graded_stakes` (line 124) which asserts
the opposite. This is a documentation defect that will mislead future
maintainers into thinking the mapping still exists.

**Fix:** Update the docstring to reflect the post-Plan-04-07 contract:

```python
# tests/scraper/test_parser.py:10-11
  * HIGH #6  -- flag crosswalk semantics: ``(牝)`` -> ``race_flag_filly_only``
    (NOT ``race_flag_mare_only``); ``(国際)`` is intentionally NOT mapped to
    ``race_flag_graded_stakes`` (UAT-Test-3 — see Plan 04-07).
```

### WR-03: Misleading comment in `test_parser.py:430` attributes graded_stakes to the wrong source

**File:** `tests/scraper/test_parser.py:427-433`
**Issue:** The test `test_flag_crosswalk_applied_on_graded_fixture` still carries
the pre-Plan-04-07 comment:

```python
# 宝塚記念 smalltxt: ``(国際)(指)(定量)`` -> graded_stakes / condition_race / bonus_weight
assert race["race_flag_graded_stakes"] is True
```

Under the new code path, `graded_stakes=True` comes from the GI token harvested
from the second `<h1>` (`第64回宝塚記念(GI)`), NOT from `(国際)`. The
`(国際)(指)(定量)` substring only contributes `condition_race` (via `(指)`) and
`bonus_weight` (via `(定量)`); the comment's claim that it contributes
`graded_stakes` is now wrong. Worse, the comment implicitly documents that
`(国際)` still drives the graded flag, which is precisely the bug Plan 04-07
fixed.

Verified empirically: `derive_race_flags('3歳以上オープン  (国際)(指)(定量)', '')`
returns `graded_stakes=None` — proving the GI token, not `(国際)`, is what
sets the flag.

**Fix:** Update the comment to reflect the actual source, and add a direct
`grade` field assertion (which would have caught CR-02):

```python
def test_flag_crosswalk_applied_on_graded_fixture(self) -> None:
    """The G1 fixture sets graded_stakes via the GI token in <h1> (Plan 04-07)."""
    race = parse_race_html(FIXTURES_DIR / "202309030811.html")["race"]
    # graded_stakes=True comes from the harvested <h1> GI token
    # (第64回宝塚記念(GI)), NOT from (国際) per Plan 04-07.
    assert race["grade"] == "GI"
    assert race["race_flag_graded_stakes"] is True
    assert race["race_flag_condition_race"] is True  # from (指)
    assert race["race_flag_bonus_weight"] is True    # from (定量)
```

### WR-04: `grade_haystack` overloads the `race_name` parameter to `derive_race_flags`, leaking h1 text into flag crosswalk matching

**File:** `src/scraper/parser.py:431-467`
**Issue:** The grade-haystack harvesting logic concatenates `race_name` with
the grade-bearing `<h1>` text:

```python
grade_haystack = race_name or ""
for h1 in soup.find_all("h1"):
    h1_text = h1.get_text(strip=True)
    if h1_text and _GRADE_TOKEN_RE.search(h1_text):
        if h1_text not in grade_haystack:
            grade_haystack = f"{grade_haystack} {h1_text}".strip()
        break
...
flags = derive_race_flags(race_condition or "", grade_haystack or "")
```

This is functionally correct for the happy path, but two concerns:

1. The loop breaks on the FIRST `<h1>` containing a grade token. If the page
   layout ever includes a third `<h1>` carrying a DIFFERENT grade token (e.g.
   a sidebar "next race" preview), the wrong one is harvested. The 5 golden
   fixtures happen to have exactly two `<h1>` elements (logo + race title),
   so this does not trigger today, but it is fragile to layout drift.
2. `grade_haystack` is passed to `derive_race_flags` as the `race_name`
   argument (line 467), but it is actually a *concatenation* of `race_name`
   and the h1 text. If the h1 text contains e.g. `(定量)` or other
   flag-markers (unlikely for netkeiba's h1, but not contractually
   impossible), those would be picked up by `FLAG_CROSSWALK` substring
   matching and incorrectly set race flags. The current fixtures don't
   exhibit this, but it is a latent coupling.

**Fix:** Either (a) pass `race_name` (not `grade_haystack`) to
`derive_race_flags` as the `race_name` parameter, and harvest the grade token
from `grade_haystack` only for the `grade`/`grade_revision` fields; or (b)
restrict the `<h1>` search to the page's main content area
(e.g. `soup.select_one("main h1")` or `soup.find("div", class_="race_main")`)
to avoid accidentally harvesting sidebar/header tokens.

```python
# Option (a) — cleaner separation of concerns.
flags = derive_race_flags(race_condition or "", race_name or "")
# grade / grade_revision use grade_haystack (which includes the h1 text).
```

## Info

### IN-01: `derive_race_flags` haystack excludes `race_name` when `race_condition` is empty

**File:** `src/scraper/flag_crosswalk.py:195`
**Issue:** The haystack is built as:
```python
haystack = f"{race_condition} {race_name}" if race_name else race_condition
```
This is correct, but note that if `race_condition` is empty (e.g. a misparsed
page where `smalltxt` is missing), `haystack` becomes `""` even when
`race_name` is set. In that case `重賞` in the race name would not be detected.
Not a current bug (condition is non-empty on all fixtures), but a latent edge
case worth a guard.

**Fix:** Build the haystack unconditionally:
```python
haystack = f"{race_condition or ''} {race_name or ''}".strip()
if not haystack:
    return flags
```

### IN-02: `_GRADE_TOKEN_RE` matching `リステッド` would carry the bare CJK string into `grade`

**File:** `src/scraper/parser.py:115`
**Issue:** The regex alternative `リステッド` would, if matched, set
`grade='リステッド'` — a CJK string inconsistent with the schema's
`'G1/G2/G3/G/listed'` documented form. This compounds CR-02: even after
stripping parentheses, `リステッド` would need normalization to `'L'`.

**Fix:** See CR-02 fix (normalize Listed variants to bare `'L'`).

### IN-03: `test_parser.py` does not assert the `grade` field value on any fixture

**File:** `tests/scraper/test_parser.py` (whole file)
**Issue:** No test currently asserts the `grade` field's value for any fixture.
The boolean `race_flag_graded_stakes` is asserted (line 431), but `grade`
itself is unverified. This is why CR-02 (`'(L)'`) and the half-width pipe
title-split edge cases go undetected.

**Fix:** Add parametrized assertions over the 5 golden fixtures for the
expected `grade` value (`'GI'` for 宝塚記念, `'L'`-normalized for
ヒヤシンスS, `None` for the ungraded fixtures).

```python
@pytest.mark.parametrize(
    "race_id, expected_grade",
    [
        ("202206050509", None),   # ひいらぎ賞
        ("202309030811", "GI"),   # 宝塚記念
        ("202405010809", "L"),    # ヒヤシンスS (after CR-02 fix)
        ("202206050508", None),
        ("202209060504", None),
    ],
)
def test_grade_field_extracted(self, race_id: str, expected_grade) -> None:
    race = parse_race_html(FIXTURES_DIR / f"{race_id}.html")["race"]
    assert race["grade"] == expected_grade, (
        f"{race_id}: expected grade {expected_grade!r}, got {race['grade']!r}"
    )
```

---

_Reviewed: 2026-06-14T14:15:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
