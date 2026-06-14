"""BS4+lxml parser for netkeiba race result HTML.

Transforms a raw netkeiba race page (``data/raw/netkeiba/{YYYY}/{MM}/{race_id}.html``)
into a structured dict ``{"race": ..., "entries": [...], "results": [...]}``
whose keys mirror ``RaceSchema`` / ``EntrySchema`` / ``ResultSchema`` so the
Plan 05 normalizer can reindex against the schemas without renaming.

Load-bearing design decisions (all guarded by ``tests/scraper/test_parser.py``):

1. **HIGH #2** -- ``horse_race_id`` is the 14-digit concatenation
   ``f"{race_id}{horse_number:02d}"`` (``YYYYPPCCDDRRHH``), matching Kaggle's
   existing keys. NO underscore (the schema docstring ``{race_id}_{horse_number:02d}``
   is a doc error; the actual Kaggle data is 14-digit per Phase 1 RESEARCH.md
   lines 333/401).
2. **HIGH #5** -- ``COURSE_CODE_MAP`` is consumed from the single authoritative
   source ``src/scraper/course_codes.py`` (not redefined here).
3. **HIGH #6 / Cycle-2 #2** -- race flags come from
   ``src.scraper.flag_crosswalk.derive_race_flags`` which is an EXHAUSTIVE
   superset of ``column_mapping.py``'s 13 ``race_flag_*`` targets.
4. **HIGH #10** -- result-table columns are resolved by normalized ``<th>``
   header text via ``resolve_columns_by_header``. No hardcoded ``cols[N]``
   index survives a column reordering.
5. **MEDIUM** -- the runner-count pseudo-field is NOT emitted (it does not
   exist on ``RaceSchema``). ``surface_detail`` / ``course_detail`` /
   ``track_condition_detail`` ARE emitted (None when absent) so the
   normalizer can reindex against ``RaceSchema`` without missing-key errors.
6. **None vs False** -- missing/unknown values are emitted as ``None``
   (never ``False`` based on absence) per Codex Review MEDIUM. ``None`` =
   unknown; the normalizer/feature layer decides how to interpret it.

Trust boundary (T-04-10): untrusted raw HTML crosses into this module.
Every column resolution is header-driven so a layout shift cannot
misattribute data; missing headers are logged and the field is left None.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup
from bs4.element import Tag
from loguru import logger

from src.scraper.course_codes import COURSE_CODE_MAP
from src.scraper.flag_crosswalk import derive_race_flags

# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------

# Race header date: ``2022年01月05日`` -> ISO 2022-01-05.
_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")

# Meeting line: ``1回中山1日目`` -> meeting_num=1, course_name=中山, meeting_day=1.
# Course name is non-greedy up to the trailing day segment. Netkeiba uses
# 2-3 kanji venue names; ``\S+?`` keeps the match bounded.
_MEETING_RE = re.compile(r"(\d+)回(\S+?)(\d+)日目")

# Course info line from the netkeiba header <span>. Real-world forms observed
# across the 5 golden fixtures (Plan 04-04 Task 3):
#   * ``芝右1800m``      (turf, right-handed inner loop)
#   * ``芝右 外1600m``   (turf, right-handed OUTER loop -- space + 外)
#   * ``芝右2200m``      (turf G1)
#   * ``ダ左1600m``      (dirt; ダ is the netkeiba shorthand for ダート)
#   * ``ダ右1200m``      (dirt)
#   * ``障芝 ダート3110m`` (obstacle mixed turf->dirt; 障 = shorthand for 障害)
#
# Captures (surface_primary, surface_secondary, direction, outer_loop, distance).
# The leading group matches 芝|ダ|ダート|障|障害 and obstacle markers so we can
# post-process for obstacle detection. ``\s*外?`` accepts the optional 外
# (outer-loop) marker between direction and distance.
# Course info line from the netkeiba header <span>. Real-world forms observed
# across the 5 golden fixtures (Plan 04-04 Task 3):
#   * ``芝右1800m``      (turf, right-handed inner loop)
#   * ``芝右 外1600m``   (turf, right-handed OUTER loop -- space + 外)
#   * ``芝右2200m``      (turf G1)
#   * ``ダ左1600m``      (dirt; ダ is the netkeiba shorthand for ダート)
#   * ``ダ右1200m``      (dirt)
#   * ``障芝 ダート3110m`` (obstacle mixed turf->dirt; 障 = shorthand for 障害)
#
# We use TWO regexes:
#  * ``_COURSE_INFO_RE`` for the common turf/dirt forms (surface, direction,
#    optional outer-loop marker, distance). It captures the four structured
#    fields the race dict needs.
#  * ``_DISTANCE_RE`` for the obstacle mixed-surface form, where there is no
#    direction token between surfaces and the surface composition is encoded
#    as ``障芝 ダート``. We treat obstacle as an override below.
_COURSE_INFO_RE = re.compile(
    r"(芝|ダート|ダ)"                    # surface (primary; netkeiba shorthand)
    r"\s*(右|左|直線|直)"                # direction
    r"(?:\s*(外))?"                     # optional outer-loop marker
    r"\s*(\d+)m"
)
_DISTANCE_RE = re.compile(r"(\d{3,5})m")

# Weather / track condition / start time captured from the inline summary line
# (e.g. ``天候 : 晴 / 芝 : 良 / 発走 : 09:55``).
_WEATHER_RE = re.compile(r"天候\s*[:：]\s*(\S+)")
_TRACK_CONDITION_RE = re.compile(r"(?:芝|ダート)\s*[:：]\s*(\S+)")
_START_TIME_RE = re.compile(r"発走\s*[:：]\s*(\d{1,2}:\d{2})")
_GRADE_REVISION_RE = re.compile(r"第(\d+)回")

# Grade token extraction from race name (``東京優駿(GI)``, ``フェブラリーS(G1)``
# etc.). Delegates full classification to flag_crosswalk._GRADE_REGEX.
# IMPORTANT: longer alternatives MUST precede shorter ones (GIII before GII
# before GI) -- Python regex alternation returns the first match at a
# position, not the longest, so ``ＧＩＩ`` would otherwise match as ``ＧＩ``.
_GRADE_TOKEN_RE = re.compile(
    r"("
    r"GIII|GII|GI|"            # half-width: long -> short
    r"JGIII|JGII|JGI|"
    r"G3|G2|G1|"
    r"JG3|JG2|JG1|"
    r"ＧＩＩＩ|ＧＩＩ|ＧＩ|"    # full-width: long -> short
    r"\(L\)|（L）|リステッド"
    r")"
)

# horse_race_id validation: exactly 14 digits (HIGH #2). race_id (12) + 2-digit
# horse number. Anything else is logged and the row skipped.
_HORSE_RACE_ID_RE = re.compile(r"\d{14}")

# Region prefix on the trainer cell: ``[東] 相沢郁`` -> region=東, trainer=相沢郁.
_TRAINER_REGION_RE = re.compile(r"^\[([東西])\]\s*(.+)$")

# horse_weight / weight_change parsing.
_HORSE_WEIGHT_RE = re.compile(r"^(\d{1,4})(?:\(([+-]?\d{1,3})\))?$")

# sex+age column: ``牡4``, ``牝3``, ``セ5``.
_SEX_AGE_RE = re.compile(r"^(牡|牝|セ)(\d{1,2})$")

# Passing (通過) cell positions separated by ``-``: ``4-6-7-7`` -> [4,6,7,7].
_PASSING_SPLIT_RE = re.compile(r"[-－―]")

# Notes that null the finish position (mirror kaggle_converter.process_finish_position).
# 降 (demoted) is NOT in this set -- it keeps the position and just records the note.
_NULL_FINISH_NOTES = {"中", "取", "失", "除", "再"}

# WR-04: the complete set of legitimately-expected finish notes. Used by the
# unknown-format branch of _parse_finish_position_cell as a defense-in-depth
# sanity check: if a surfaced finish_note is NOT in this set, it likely
# indicates a column-header resolution error feeding a non-着順 cell (e.g. a
# horse-weight sentinel like 計不 / ---) into the finish-position parser.
_KNOWN_FINISH_NOTES: frozenset[str] = frozenset(_NULL_FINISH_NOTES | {"降"})


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def parse_horse_weight(text: str) -> Tuple[Optional[int], Optional[int]]:
    """Parse the ``馬体重`` cell into ``(weight, change)``.

    Formats handled:
      * ``"456(+4)"``  -> ``(456, 4)``
      * ``"478(-2)"``  -> ``(478, -2)``
      * ``"472(0)"``   -> ``(472, 0)``
      * ``"456"``      -> ``(456, None)``  (no change recorded)
      * ``"計不"`` / ``"---"`` / ``""`` -> ``(None, None)``

    Returns ``(None, None)`` for any unparseable input rather than raising.
    """
    if not text:
        return (None, None)
    cleaned = text.strip()
    if not cleaned or cleaned in {"計不", "---"}:
        return (None, None)
    match = _HORSE_WEIGHT_RE.match(cleaned)
    if match is None:
        return (None, None)
    weight = int(match.group(1))
    change_str = match.group(2)
    change = int(change_str) if change_str is not None else None
    return (weight, change)


def parse_sex_age(text: str) -> Tuple[Optional[str], Optional[int]]:
    """Parse the ``性齢`` cell into ``(sex, age)``.

    Formats: ``"牡4"`` -> ``("牡", 4)``; ``"牝3"`` -> ``("牝", 3)``;
    ``"セ5"`` -> ``("セ", 5)``. Empty/short input -> ``(None, None)``.
    """
    if not text:
        return (None, None)
    cleaned = text.strip()
    if not cleaned:
        return (None, None)
    match = _SEX_AGE_RE.match(cleaned)
    if match is None:
        return (None, None)
    sex = match.group(1)
    age = int(match.group(2))
    return (sex, age)


# Default header aliases used by ``resolve_columns_by_header`` for the netkeiba
# result table. Caller may override (e.g. for a future table layout change).
DEFAULT_HEADER_ALIASES: Dict[str, List[str]] = {
    "finish_position": ["着順"],
    "bracket_num": ["枠番"],
    "horse_number": ["馬番"],
    "horse_name": ["馬名"],
    "sex_age": ["性齢"],
    "weight_assigned": ["斤量"],
    "jockey": ["騎手"],
    "finish_time": ["タイム"],
    "margin": ["着差"],
    "passing": ["通過"],
    "last_3f": ["上り", "上がり"],
    "win_odds": ["単勝"],
    "popularity": ["人気"],
    "horse_weight": ["馬体重"],
    "trainer": ["調教師"],
    "owner": ["馬主"],
    "prize_money": ["賞金"],
}


def _normalize_th_text(th: Tag) -> str:
    """Normalize a ``<th>`` cell's text for header matching.

    Strips whitespace and converts full-width alphanumerics to half-width so
    e.g. ``'馬　名'`` and ``'馬名'`` compare equal.
    """
    raw = th.get_text()
    # Translate full-width digits/letters to half-width.
    normalized = raw.translate(str.maketrans(
        "０１２３４５６７８９"
        "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
        "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ",
        "0123456789"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "abcdefghijklmnopqrstuvwxyz",
    ))
    return normalized.strip()


def resolve_columns_by_header(
    table: Tag,
    header_aliases: Dict[str, List[str]],
) -> Dict[str, int]:
    """Map field names to ``<td>`` column indices by reading ``<th>`` text.

    Per Codex Review HIGH #10 -- replaces fixed ``cols[N]`` indexing. Finds
    the header row (the ``<tr>`` containing ``<th>`` cells), normalizes each
    ``<th>`` text, and matches it against the alias lists.

    Parameters
    ----------
    table : bs4.element.Tag
        A ``<table>`` element (typically ``class="race_table_01"``).
    header_aliases : dict[str, list[str]]
        Field name -> list of acceptable header strings (post-normalization).

    Returns
    -------
    dict[str, int]
        Field name -> ``<td>`` index within a data ``<tr>``. Fields whose
        headers are absent are omitted from the dict (caller treats them as
        None). A warning is logged for each expected-but-missing header.
    """
    # Locate the header row: the first <tr> that contains <th> children.
    header_cells: List[Tag] = []
    all_rows = table.find_all("tr")
    for row in all_rows:
        ths = row.find_all("th")
        if ths:
            header_cells = ths
            break

    if not header_cells:
        logger.warning("resolve_columns_by_header: no <th> cells found in table")
        return {}

    # Build a list of (index, normalized_text) for each header cell.
    header_texts: List[str] = [_normalize_th_text(th) for th in header_cells]

    resolved: Dict[str, int] = {}
    for field_name, aliases in header_aliases.items():
        normalized_aliases = [a.strip() for a in aliases]
        for idx, text in enumerate(header_texts):
            if text in normalized_aliases:
                resolved[field_name] = idx
                break
        # If not found, simply omit (caller treats as None). Do NOT spam logs
        # for every missing optional field -- only warn for fields we consider
        # structurally expected. The caller decides.
    return resolved


# ---------------------------------------------------------------------------
# Race header parsing
# ---------------------------------------------------------------------------


def _parse_race_header(soup: BeautifulSoup, race_id: str) -> Dict:
    """Extract the race-level fields from the page header.

    Returns a dict with all RaceSchema field names (the runner-count column
    from the Kaggle pseudo-schema is NOT among them). Missing values are
    None; confirmed-absent optionals are also None (not False).
    """
    # ----- date + meeting + condition from the ``smalltxt`` paragraph -----
    race_date: Optional[str] = None
    meeting_num: Optional[int] = None
    course_name: Optional[str] = None
    meeting_day: Optional[int] = None
    race_condition: Optional[str] = None

    smalltxt = soup.find("p", class_="smalltxt")
    header_text = smalltxt.get_text() if smalltxt else ""

    date_match = _DATE_RE.search(header_text)
    if date_match:
        y, m, d = (int(x) for x in date_match.groups())
        race_date = f"{y:04d}-{m:02d}-{d:02d}"

    meeting_match = _MEETING_RE.search(header_text)
    if meeting_match:
        meeting_num = int(meeting_match.group(1))
        course_name = meeting_match.group(2)
        meeting_day = int(meeting_match.group(3))

    # race_condition: the portion of the header AFTER the meeting segment.
    # e.g. ``"3歳未勝利 (馬齢)"`` or ``"4歳以上オープン (国際)(特指)(ハンデ)"``.
    if meeting_match is not None:
        after_meeting = header_text[meeting_match.end():].strip()
        # Trim leading whitespace and any stray separators.
        race_condition = after_meeting or None

    # ----- course info from the diary_snap_cut span / main <p> -----
    surface: Optional[str] = None
    direction: Optional[str] = None
    distance: Optional[int] = None
    obstacle: Optional[str] = None
    weather: Optional[str] = None
    track_condition: Optional[str] = None
    start_time: Optional[str] = None

    # netkeiba renders the course/condition line inside a <p> or <span> with
    # a structure like ``ダ右1200m / 天候 : 晴 / ダート : 良 / 発走 : 09:55``.
    # Search the whole document for these tokens; we use the first occurrence.
    full_text = soup.get_text(separator=" ")

    # Obstacle detection takes precedence over the structured course regex,
    # because netkeiba renders obstacle races as ``障芝 ダート3110m`` (no
    # direction token between surfaces) and the ``障害`` substring is reliably
    # present in the race-condition text. Condition-derived obstacle detection
    # is required regardless of the regex match below.
    is_obstacle = bool(race_condition and "障害" in race_condition)
    if is_obstacle:
        obstacle = "障害"
        # Obstacle mixed-surface: netkeiba renders ``障芝 ダート3110m`` -- we
        # take the secondary surface (ダート for the 障芝 -> ダート sequence)
        # and the distance. Direction is not encoded for obstacle races.
        if "ダート" in full_text or "ダ" in full_text:
            surface = "ダート"
        # Distance: use the trailing ``<digits>m`` near the course-info span.
        # _DISTANCE_RE.search on the full text would also match any other
        # ``<digits>m`` on the page (rare but possible); to stay precise we
        # search within 40 chars of the first ``障`` marker.
        obs_match = re.search(r"障.{0,40}?(\d{3,5})m", full_text)
        if obs_match:
            distance = int(obs_match.group(1))

    course_match = _COURSE_INFO_RE.search(full_text)
    if course_match:
        s1, dirn, _outer, dist = course_match.groups()
        if not is_obstacle:
            # Surface: normalize netkeiba shorthand (ダ -> ダート).
            if s1 == "ダ":
                surface = "ダート"
            elif s1 in {"芝", "ダート"}:
                surface = s1
            if dirn:
                # ``直`` -> ``直線`` for schema consistency.
                direction = "直線" if dirn == "直" else dirn
            if dist:
                distance = int(dist)

    weather_match = _WEATHER_RE.search(full_text)
    if weather_match:
        weather = weather_match.group(1)

    track_match = _TRACK_CONDITION_RE.search(full_text)
    if track_match:
        track_condition = track_match.group(1)

    start_match = _START_TIME_RE.search(full_text)
    if start_match:
        start_time = start_match.group(1)

    # ----- race name + grade -----
    #
    # Race-name extraction (Rule 1 deviation fix verified against the 5 golden
    # fixtures): netkeiba's <h1> contains the SITE LOGO, not the race name.
    # The race name is reliably in <title> as
    # ``"ひいらぎ賞｜2022年12月17日 | 競馬データベース - netkeiba"`` where the
    # FIRST pipe-separated segment is the race name (full-width ``｜``).
    # We fall back to <h1> text only if <title> is missing/empty.
    race_name: Optional[str] = None
    title_tag = soup.find("title")
    if title_tag:
        title_text = title_tag.get_text(strip=True)
        if title_text:
            # Split on the first full-width or half-width pipe.
            for sep in ("｜", "|"):
                if sep in title_text:
                    race_name = title_text.split(sep, 1)[0].strip() or None
                    break
            if race_name is None:
                race_name = title_text or None
    if race_name is None:
        h1 = soup.find("h1")
        if h1:
            race_name = h1.get_text(strip=True) or None

    # Grade token from the race name (``東京優駿(GI)``). Use the same regex
    # as flag_crosswalk so classification is consistent.
    grade: Optional[str] = None
    if race_name:
        grade_token = _GRADE_TOKEN_RE.search(race_name)
        if grade_token:
            grade = grade_token.group(1)

    # grade_revision: ``第N回`` in the race name (e.g. ``第89回東京優駿``).
    grade_revision: Optional[str] = None
    if race_name:
        rev_match = _GRADE_REVISION_RE.search(race_name)
        if rev_match:
            grade_revision = rev_match.group(1)

    # ----- course code from the authoritative map -----
    course_code: Optional[str] = None
    if course_name is not None:
        if course_name in COURSE_CODE_MAP:
            course_code = COURSE_CODE_MAP[course_name]
        else:
            logger.warning(
                f"Unknown course_name {course_name!r} for race_id {race_id}; "
                f"course_code left None"
            )

    # ----- race flags -----
    flags = derive_race_flags(race_condition or "", race_name or "")

    # ----- race_number from race_id suffix -----
    race_number: Optional[int] = None
    if race_id and len(race_id) >= 12 and race_id[-2:].isdigit():
        race_number = int(race_id[-2:])

    # Assemble the race dict with EVERY RaceSchema field (runner-count excluded).
    race: Dict = {
        "race_id": race_id,
        "race_date": race_date,
        "meeting_num": meeting_num,
        "course_code": course_code,
        "course_name": course_name,
        "meeting_day": meeting_day,
        "race_condition": race_condition,
        "race_number": race_number,
        "grade_revision": grade_revision,
        "race_name": race_name,
        "grade": grade,
        "obstacle": obstacle,
        "surface": surface,
        # Codex Review MEDIUM: surface_detail / course_detail /
        # track_condition_detail are not directly present in the standard
        # netkeiba race header. Emit None so the normalizer can reindex
        # against RaceSchema without a missing-key error.
        "surface_detail": None,
        "direction": direction,
        "course_detail": None,
        "distance": distance,
        "weather": weather,
        "track_condition": track_condition,
        "track_condition_detail": None,
        "start_time": start_time,
        # 20 race_flag_* fields (HIGH #6 / Cycle-2 #2 -- exhaustive).
        **flags,
    }
    return race


# ---------------------------------------------------------------------------
# Result table parsing
# ---------------------------------------------------------------------------


def _safe_int(text: Optional[str]) -> Optional[int]:
    if text is None:
        return None
    cleaned = text.strip()
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def _safe_float(text: Optional[str]) -> Optional[float]:
    if text is None:
        return None
    cleaned = text.strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_passing_cell(text: Optional[str]) -> List[Optional[int]]:
    """Parse the 通過 cell into a list of corner positions (1..N).

    ``"4-6-7-7"`` -> ``[4, 6, 7, 7]``. Empty / missing -> ``[]``. Non-numeric
    segments become None within the list.
    """
    if not text:
        return []
    parts = _PASSING_SPLIT_RE.split(text.strip())
    out: List[Optional[int]] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            out.append(None)
    return out


def _parse_finish_position_cell(
    text: Optional[str],
) -> Tuple[Optional[int], Optional[str]]:
    """Parse the 着順 cell into ``(finish_position, finish_note)``.

    Mirrors ``kaggle_converter.process_finish_position``:
      * numeric (``"1"``, ``"12"``) -> ``(int, None)``
      * numeric + 降 (``"5降"``) -> ``(5, "降")``  (position kept)
      * null-notes 中/取/失/除/再 -> ``(None, note)``  (position dropped)

    Returns ``(None, None)`` for any unparseable input.
    """
    if text is None:
        return (None, None)
    cleaned = text.strip()
    if not cleaned:
        return (None, None)

    # Pure null-note case (``"取"``, ``"中"``...).
    if cleaned in _NULL_FINISH_NOTES:
        return (None, cleaned)

    # Demotion: ``"5降"`` -> keep position, set note to 降.
    if cleaned.endswith("降"):
        prefix = cleaned[:-1].strip()
        pos = _safe_int(prefix)
        if pos is not None:
            return (pos, "降")
        return (None, "降")

    # Plain numeric.
    pos = _safe_int(cleaned)
    if pos is not None:
        return (pos, None)

    # Unknown format -- surface as a note, drop position.
    logger.warning(f"Unparseable 着順 cell: {cleaned!r}; dropping finish_position")
    # WR-04 defense-in-depth: if the surfaced note is NOT a known finish note,
    # it likely indicates a column-header resolution error feeding a non-着順
    # cell (e.g. a horse-weight sentinel like 計不 / ---) into this parser.
    # Surface it explicitly so a header-resolution bug is visible.
    if cleaned not in _KNOWN_FINISH_NOTES:
        logger.warning(
            f"Surfaced finish_note {cleaned!r} is not a known finish note "
            f"({_KNOWN_FINISH_NOTES}); if this looks like a horse-weight "
            f"sentinel (計不/---), check column-header resolution."
        )
    return (None, cleaned)


def _cell_text(row_cells: List[Tag], idx: Optional[int]) -> Optional[str]:
    """Return stripped text of the cell at ``idx``, or None if out of range."""
    if idx is None:
        return None
    if idx < 0 or idx >= len(row_cells):
        return None
    return row_cells[idx].get_text(strip=True)


def _split_trainer_region(text: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Split ``"[東] 相沢郁"`` into ``("東", "相沢郁")``.

    Returns ``(None, text)`` when no region prefix is present.
    """
    if text is None:
        return (None, None)
    match = _TRAINER_REGION_RE.match(text.strip())
    if match is None:
        return (None, text.strip() or None)
    region = match.group(1)
    trainer = match.group(2).strip() or None
    return (region, trainer)


def _parse_result_table(
    soup: BeautifulSoup,
    race_id: str,
) -> Tuple[List[Dict], List[Dict]]:
    """Parse the result table into ``(entries, results)``.

    Uses ``resolve_columns_by_header`` to map fields to column indices. For
    each data row, builds an entry dict (EntrySchema keys) and a result dict
    (ResultSchema keys). ``horse_race_id`` is the 14-digit concatenation.
    """
    entries: List[Dict] = []
    results: List[Dict] = []

    # netkeiba renders the result table with class ``race_table_01`` (sometimes
    # with an additional ``nk_tb_common`` class).
    table = soup.find("table", class_="race_table_01")
    if table is None:
        # Some pages use a different table class; fall back to the first table
        # that has <th> cells (header-driven detection).
        for candidate in soup.find_all("table"):
            if candidate.find("th"):
                table = candidate
                break
    if table is None:
        logger.warning(f"No result table found for race_id {race_id}")
        return (entries, results)

    col_map = resolve_columns_by_header(table, DEFAULT_HEADER_ALIASES)

    # Iterate data rows: any <tr> with <td> children (skip header rows).
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if not cells:
            continue  # header row

        # horse_number is the structural key -- skip the row if absent.
        horse_number_text = _cell_text(cells, col_map.get("horse_number"))
        horse_number = _safe_int(horse_number_text)
        if horse_number is None:
            # Could be a summary row or a malformed entry; skip silently.
            continue

        # HIGH #2: 14-digit horse_race_id (NO underscore).
        horse_race_id = f"{race_id}{horse_number:02d}"
        if not _HORSE_RACE_ID_RE.fullmatch(horse_race_id):
            logger.warning(
                f"horse_race_id {horse_race_id!r} is not 14 digits "
                f"(race_id={race_id!r}, horse_number={horse_number}); skipping row"
            )
            continue

        # ----- entry fields -----
        bracket_num = _safe_int(_cell_text(cells, col_map.get("bracket_num")))
        horse_name = _cell_text(cells, col_map.get("horse_name"))
        sex_text = _cell_text(cells, col_map.get("sex_age"))
        sex, age = parse_sex_age(sex_text or "")
        weight_assigned = _safe_float(_cell_text(cells, col_map.get("weight_assigned")))
        jockey = _cell_text(cells, col_map.get("jockey"))

        # trainer cell carries the region prefix (D-12): ``[東] 相沢郁``.
        trainer_raw = _cell_text(cells, col_map.get("trainer"))
        region, trainer = _split_trainer_region(trainer_raw)

        owner = _cell_text(cells, col_map.get("owner"))

        # horse weight cell: ``456(+4)`` / ``計不``.
        hw_text = _cell_text(cells, col_map.get("horse_weight"))
        horse_weight, weight_change = parse_horse_weight(hw_text or "")

        # Market signals (post-race per D-03): win_odds / popularity.
        win_odds = _safe_float(_cell_text(cells, col_map.get("win_odds")))
        popularity = _safe_int(_cell_text(cells, col_map.get("popularity")))

        entry: Dict = {
            "horse_race_id": horse_race_id,
            "race_id": race_id,
            "bracket_num": bracket_num,
            "horse_number": horse_number,
            "horse_name": horse_name,
            "sex": sex,
            "age": age,
            "weight_assigned": weight_assigned,
            "jockey": jockey,
            "trainer": trainer,
            "owner": owner,
            "horse_weight": horse_weight,
            "weight_change": weight_change,
            "region": region,
            "popularity": popularity,
            "win_odds": win_odds,
        }
        entries.append(entry)

        # ----- result fields -----
        finish_text = _cell_text(cells, col_map.get("finish_position"))
        finish_position, finish_note = _parse_finish_position_cell(finish_text)

        finish_time = _cell_text(cells, col_map.get("finish_time"))
        margin = _cell_text(cells, col_map.get("margin"))

        passing_text = _cell_text(cells, col_map.get("passing"))
        corners = _parse_passing_cell(passing_text)
        # Codex Review MEDIUM: races may have 2/3 passing points. Pad to 4
        # corners with None; if MORE than 4, keep first 4 and warn.
        corner_1: Optional[int] = None
        corner_2: Optional[int] = None
        corner_3: Optional[int] = None
        corner_4: Optional[int] = None
        if len(corners) > 4:
            logger.warning(
                f"horse_race_id {horse_race_id}: {len(corners)} corner positions "
                f"(expected <=4); keeping first 4"
            )
        for i, value in enumerate(corners[:4]):
            if i == 0:
                corner_1 = value
            elif i == 1:
                corner_2 = value
            elif i == 2:
                corner_3 = value
            elif i == 3:
                corner_4 = value

        last_3f = _safe_float(_cell_text(cells, col_map.get("last_3f")))
        prize_money = _safe_float(_cell_text(cells, col_map.get("prize_money")))

        result: Dict = {
            "horse_race_id": horse_race_id,
            "race_id": race_id,
            "finish_position": finish_position,
            "finish_note": finish_note,
            "finish_time": finish_time,
            "margin": margin,
            "corner_1": corner_1,
            "corner_2": corner_2,
            "corner_3": corner_3,
            "corner_4": corner_4,
            "last_3f": last_3f,
            "prize_money": prize_money,
        }
        results.append(result)

    return (entries, results)


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


def parse_race_html(html_path: Path) -> Dict:
    """Parse a saved netkeiba race HTML file into a structured dict.

    Parameters
    ----------
    html_path : pathlib.Path
        Path to the raw HTML file (UTF-8). The ``race_id`` is taken from the
        filename stem (``202206010101.html`` -> ``"202206010101"``).

    Returns
    -------
    dict
        ``{"race": {...}, "entries": [...], "results": [...]}`` where ``race``
        has all ``RaceSchema`` field names (runner-count excluded), each entry has
        all ``EntrySchema`` field names, and each result has all
        ``ResultSchema`` field names. Missing values are ``None``.

    Raises
    ------
    ValueError
        WR-01: if the filename stem is not a 12-digit race_id. Without this
        guard, a misnamed fixture (e.g. ``foo.html``) would inject
        ``race_id="foo"`` and silently produce a corrupt race row whose
        entries/results all fail the 14-digit ``horse_race_id`` validation and
        get dropped -- an empty entries list with a corrupt race row.
    """
    html_path = Path(html_path)
    race_id = html_path.stem
    # WR-01: validate the stem is a 12-digit race_id before it propagates into
    # race["race_id"] and horse_race_id. fetcher.py:290 validates on write; this
    # validates on parse entry so direct callers (tests, manual use) are
    # protected equivalently.
    if not re.fullmatch(r"\d{12}", race_id):
        raise ValueError(
            f"parse_race_html: filename stem {race_id!r} is not a 12-digit "
            f"race_id (file={html_path})"
        )

    html = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, features="lxml")

    race = _parse_race_header(soup, race_id)
    entries, results = _parse_result_table(soup, race_id)

    return {"race": race, "entries": entries, "results": results}


__all__ = [
    "parse_race_html",
    "parse_horse_weight",
    "parse_sex_age",
    "resolve_columns_by_header",
    "DEFAULT_HEADER_ALIASES",
]
