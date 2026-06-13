"""Authoritative JRA course code map (single source of truth).

This module is the SINGLE AUTHORITATIVE source for the 2-digit JRA course
codes used in ``race_id`` (``YYYYPPCCDDRR``, where ``CC`` is the code) and
in the standard-layer ``RaceSchema.course_code`` column. Both the parser
(``src/scraper/parser.py``) and the normalizer (Plan 05) import from here
rather than redefining the mapping.

Codes are corrected per Codex Review Cycle-1 HIGH #5:

    01 札幌   02 函館   03 福島   04 新潟   05 東京
    06 中山   07 中京   08 京都   09 阪神   10 小倉

The previous (buggy) draft had 福島=04 / 新潟=03 swapped; both directions
of the map are exercised by ``tests/scraper/test_course_codes.py`` to guard
against regression.
"""

from typing import Dict

# Forward map: Japanese venue name -> 2-digit JRA code.
# Keyed by the short kanji form netkeiba renders in its race header
# (``1回中山...`` -> COURSE_CODE_MAP["中山"] == "06").
COURSE_CODE_MAP: Dict[str, str] = {
    "札幌": "01",
    "函館": "02",
    "福島": "03",
    "新潟": "04",
    "東京": "05",
    "中山": "06",
    "中京": "07",
    "京都": "08",
    "阪神": "09",
    "小倉": "10",
}

# Reverse map: 2-digit JRA code -> Japanese venue name.
# Built from COURSE_CODE_MAP so the two can never drift apart.
COURSE_CODE_REVERSE: Dict[str, str] = {code: name for name, code in COURSE_CODE_MAP.items()}


__all__ = ["COURSE_CODE_MAP", "COURSE_CODE_REVERSE"]
