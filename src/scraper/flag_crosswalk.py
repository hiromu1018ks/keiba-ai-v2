"""netkeiba race-condition text -> ``race_flag_*`` crosswalk.

This module converts the free-text race-condition string scraped from the
netkeiba race header (e.g. ``"4歳以上オープン (国際)(特指)(ハンデ)"``) into
the 20 ``race_flag_*`` boolean fields defined on ``src.schemas.race.RaceSchema``.

Source-of-truth cross-reference: ``src/pipeline/column_mapping.py``. Its
``KAGGLE_COLUMN_MAP`` rows 9-28 are the AUTHORITATIVE definition of which
CSV flag columns exist on the Kaggle side and which ``race_flag_*`` field
each one maps to. ``FLAG_CROSSWALK`` here is intentionally an EXHAUSTIVE
SUPERSET of those 13 unique targets so that, when Phase 6 joins scraped
rows against Kaggle rows, no flag column silently collapses to ``None``.

Coverage regression guard: ``tests/scraper/test_parser.py`` parameterizes
``test_crosswalk_covers_all_kaggle_flag_targets`` over the 13 targets
extracted from ``KAGGLE_COLUMN_MAP`` and asserts each one has >=1 pattern
in ``FLAG_CROSSWALK``. This is the mechanical diff guard Codex recommended
(Cycle-2 HIGH #2).

Compatibility note on ``(国際)`` -> ``race_flag_graded_stakes``:
Kaggle's existing ``column_mapping.py`` maps ``レース記号/(国際)`` to
``race_flag_graded_stakes``. Strictly speaking ``(国際)`` is an
international-designation flag, not a graded-stakes flag. We follow the
Kaggle mapping here for JOIN COMPATIBILITY so Phase 6 does not introduce
a semantic split between the two data sources. A Phase 6 cleanup pass may
revisit this classification if desired.

Semantics (per Codex Review MEDIUM):
  * ``None``  = unknown / not observed in the source text. The normalizer
               preserves ``None`` so downstream code can distinguish
               "absent from HTML" from "confirmed False".
  * ``True``  = the pattern matched the race condition text.
  * ``False`` = NEVER assigned based on absence. Only the parser/normalizer
               may set ``False`` when it has positive evidence the flag does
               not apply (not implemented in this module).
"""

import re
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# FLAG_CROSSWALK: ordered list of (substring_pattern, race_flag_field_name).
#
# Order matters only when one pattern is a substring of another (e.g. the
# bare ``見習騎手`` form is a substring of the parenthesized ``(見習騎手)``
# form). We list the parenthesized forms first where relevant; since both
# map to the same field, order between them does not change the result, but
# listing them adjacent makes the intent obvious.
#
# Cycle-2 HIGH #2: this list MUST cover every ``race_flag_*`` target that
# ``src/pipeline/column_mapping.py`` defines. The parametrized test
# ``test_crosswalk_covers_all_kaggle_flag_targets`` enforces this.
# ---------------------------------------------------------------------------
FLAG_CROSSWALK: List[Tuple[str, str]] = [
    ("(ハンデ)", "race_flag_handicap"),
    ("(馬齢)", "race_flag_age_restricted"),
    ("(牝)", "race_flag_filly_only"),   # Cycle-1 HIGH #6: 牝 -> filly_only (NOT mare_only)
    ("(牡)", "race_flag_colt_only"),    # Cycle-2 #2: was missing (column_mapping.py:61)
    ("(父)", "race_flag_stallion_only"),
    ("(別定)", "race_flag_special_weight"),
    ("(特指)", "race_flag_special_weight"),  # Kaggle: レース記号/(特指) -> special_weight
    ("(混)", "race_flag_allowance"),
    ("(市)", "race_flag_allowance"),
    ("九州産馬", "race_flag_allowance"),
    ("(定量)", "race_flag_bonus_weight"),
    ("(国際)", "race_flag_graded_stakes"),  # Kaggle-compat (see module docstring)
    ("(見習騎手)", "race_flag_apprentice"),  # parenthesized netkeiba form
    ("見習騎手", "race_flag_apprentice"),    # Cycle-2 #2 BARE form (column_mapping.py:66)
    ("(指)", "race_flag_condition_race"),
    ("[指]", "race_flag_condition_race"),
    ("(抽)", "race_flag_condition_race"),
    ("[抽]", "race_flag_condition_race"),
    ("関東配布馬", "race_flag_open"),
    ("関西配布馬", "race_flag_open"),
    ("せん", "race_flag_gelding_only"),
]

# ---------------------------------------------------------------------------
# CLASS_PATTERNS: regex -> race_flag_field for class-level detection.
# Used to derive maiden / open from the class portion of the condition text.
# ---------------------------------------------------------------------------
CLASS_PATTERNS: List[Tuple["re.Pattern[str]", str]] = [
    (re.compile(r"未勝利"), "race_flag_maiden"),
    (re.compile(r"新馬"), "race_flag_maiden"),  # maiden-compat: 新馬 is a debut maiden race
    (re.compile(r"オープン"), "race_flag_open"),
]

# ---------------------------------------------------------------------------
# GRADE_PATTERNS: regex matching grade designations.
#
# Matches half-width (GI/GII/GIII/G1/G2/G3, JRA jump JG*) and full-width
# (ＧＩ/ＧＩＩ/ＧＩＩＩ) forms. A match sets BOTH race_flag_graded_stakes
# and race_flag_stakes to True (a graded stakes is by definition a stakes).
#
# ``重賞`` substring alone (no GI/...) sets race_flag_stakes only.
# ``(L)`` / ``(リステッド)`` sets race_flag_listed only.
# ---------------------------------------------------------------------------
_GRADE_REGEX = re.compile(
    r"(?:GI|GII|GIII|G1|G2|G3|JGI|JGII|JGIII|JG1|JG2|JG3"
    r"|ＧＩ|ＧＩＩ|ＧＩＩＩ)"
)
_LISTED_REGEX = re.compile(r"\(L\)|（L）|\(リステッド\)|（リステッド）")
_STAKES_REGEX = re.compile(r"重賞")


def derive_race_flags(
    race_condition: str,
    race_name: str = "",
) -> Dict[str, Optional[bool]]:
    """Derive the 20 ``race_flag_*`` fields from race-condition text.

    Parameters
    ----------
    race_condition : str
        The condition/class text from the netkeiba race header, e.g.
        ``"4歳以上オープン (国際)(特指)(ハンデ)"`` or ``"3歳未勝利 (馬齢)"``.
    race_name : str
        Optional race-name text (e.g. ``"東京優駿(GI)"``). Grade patterns are
        also matched against the name so that named graded stakes set the
        graded flag even if the condition string omits the grade token.

    Returns
    -------
    dict[str, Optional[bool]]
        A dict with EXACTLY the 20 keys from ``RaceSchema`` whose names start
        with ``race_flag_``. All values default to ``None`` (unknown). Each
        pattern that matches sets its field to ``True``. No field is ever
        set to ``False`` by this function (absence => unknown).
    """
    # Initialize all 20 keys to None. The exact key set mirrors RaceSchema
    # (kept in sync by test_exactly_20_keys which diffs against the schema).
    flags: Dict[str, Optional[bool]] = {
        "race_flag_handicap": None,
        "race_flag_age_restricted": None,
        "race_flag_filly_only": None,
        "race_flag_colt_only": None,
        "race_flag_gelding_only": None,
        "race_flag_mare_only": None,
        "race_flag_stallion_only": None,
        "race_flag_apprentice": None,
        "race_flag_amateur": None,
        "race_flag_female_jockey": None,
        "race_flag_young_horse": None,
        "race_flag_condition_race": None,
        "race_flag_special_weight": None,
        "race_flag_bonus_weight": None,
        "race_flag_stakes": None,
        "race_flag_graded_stakes": None,
        "race_flag_listed": None,
        "race_flag_open": None,
        "race_flag_maiden": None,
        "race_flag_allowance": None,
    }

    if not race_condition:
        return flags

    # Substring crosswalk: each match sets its target field to True.
    for pattern, field_name in FLAG_CROSSWALK:
        if pattern in race_condition:
            flags[field_name] = True

    # Class-level patterns (maiden / open). Run after the crosswalk so that,
    # for example, ``関東配布馬`` does not get overridden by the ``オープン``
    # substring inside another word -- but since each only sets True (never
    # False), order between class patterns and the crosswalk is safe.
    for regex, field_name in CLASS_PATTERNS:
        if regex.search(race_condition):
            flags[field_name] = True

    # Grade / stakes / listed detection. Search both the condition and the
    # race name so that a named graded race (``"東京優駿(GI)"``) sets the
    # graded flag even when the condition text is just ``"3歳オープン"``.
    haystack = f"{race_condition} {race_name}" if race_name else race_condition

    if _GRADE_REGEX.search(haystack):
        flags["race_flag_graded_stakes"] = True
        flags["race_flag_stakes"] = True
    elif _STAKES_REGEX.search(haystack):
        # ``重賞`` without an explicit grade token: stakes but not graded.
        flags["race_flag_stakes"] = True

    if _LISTED_REGEX.search(haystack):
        flags["race_flag_listed"] = True

    return flags


__all__ = ["FLAG_CROSSWALK", "CLASS_PATTERNS", "GRADE_PATTERNS", "derive_race_flags"]
