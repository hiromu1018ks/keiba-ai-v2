"""Tests for ``src/scraper/parser`` and ``src/scraper/flag_crosswalk``.

Covers the Cycle-1 / Cycle-2 review HIGH items and the Plan 04-04 acceptance
criteria:

  * HIGH #2  -- ``horse_race_id`` is the 14-digit concatenation
    ``f"{race_id}{horse_number:02d}"`` (no underscore), matching Kaggle.
  * HIGH #5  -- COURSE_CODE_MAP consumed from the single authoritative source
    (parametrized test lives in ``test_course_codes.py``).
  * HIGH #6  -- flag crosswalk semantics: ``(牝)`` -> ``race_flag_filly_only``
    (NOT ``race_flag_mare_only``); ``(国際)`` -> ``race_flag_graded_stakes``.
  * HIGH #10 -- ``resolve_columns_by_header`` maps ``<th>`` text to indices
    instead of relying on hardcoded ``cols[N]`` positions.
  * HIGH #9  -- ``TestParseRaceHtmlGolden`` runs ``parse_race_html`` against
    the 5 authentic fixtures captured in Task 3 and asserts the parser
    extracts the correct surface / course / distance / horse_race_id etc.
  * MEDIUM  -- ``head_count`` is NOT emitted; ``surface_detail`` etc. ARE
    emitted (None allowed).
  * CYCLE-2 #2 -- ``FLAG_CROSSWALK`` is an EXHAUSTIVE superset of
    ``column_mapping.py``'s 13 ``race_flag_*`` targets. A parametrized
    coverage guard asserts every target has >= 1 source pattern.
"""

import re
from pathlib import Path
from typing import List

import pytest
from bs4 import BeautifulSoup

from src.pipeline.column_mapping import KAGGLE_COLUMN_MAP
from src.scraper.course_codes import COURSE_CODE_MAP
from src.scraper.flag_crosswalk import FLAG_CROSSWALK, derive_race_flags
from src.scraper.parser import (
    DEFAULT_HEADER_ALIASES,
    parse_horse_weight,
    parse_race_html,
    parse_sex_age,
    resolve_columns_by_header,
)
from src.schemas.race import RaceSchema


# ---------------------------------------------------------------------------
# Helper: authoritative list of golden fixtures (Task 3 outputs).
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "html"

# (race_id, expected_diversity_axis_summary) for parametrized golden tests.
GOLDEN_FIXTURES: List[tuple] = [
    ("202206050509", "turf base (1勝クラス)"),
    ("202309030811", "graded stakes (宝塚記念 G1)"),
    ("202405010809", "dirt (ヒヤシンスS L)"),
    ("202206050508", "dirt (3歳以上1勝クラス)"),
    ("202209060504", "obstacle (障害3歳以上OP)"),
]


# ---------------------------------------------------------------------------
# TestHorseWeightParsing
# ---------------------------------------------------------------------------


class TestHorseWeightParsing:
    """parse_horse_weight: ``456(+4)`` -> ``(456, 4)`` etc."""

    @pytest.mark.parametrize(
        "text, expected",
        [
            ("456(+4)", (456, 4)),
            ("478(-2)", (478, -2)),
            ("472(0)", (472, 0)),
            ("456", (456, None)),  # no change recorded
            ("計不", (None, None)),
            ("---", (None, None)),
            ("", (None, None)),
        ],
    )
    def test_formats(self, text: str, expected: tuple) -> None:
        assert parse_horse_weight(text) == expected


# ---------------------------------------------------------------------------
# TestSexAgeParsing
# ---------------------------------------------------------------------------


class TestSexAgeParsing:
    """parse_sex_age: ``牡4`` -> ``("牡", 4)`` etc."""

    @pytest.mark.parametrize(
        "text, expected",
        [
            ("牡4", ("牡", 4)),
            ("牝3", ("牝", 3)),
            ("セ5", ("セ", 5)),
            ("", (None, None)),
        ],
    )
    def test_formats(self, text: str, expected: tuple) -> None:
        assert parse_sex_age(text) == expected


# ---------------------------------------------------------------------------
# TestFlagCrosswalk
# ---------------------------------------------------------------------------


class TestFlagCrosswalk:
    """derive_race_flags: Cycle-1 HIGH #6 + Cycle-2 HIGH #2 coverage."""

    def test_handicap(self) -> None:
        flags = derive_race_flags("4歳以上オープン (ハンデ)")
        assert flags["race_flag_handicap"] is True

    def test_filly_only(self) -> None:
        """HIGH #6: ``(牝)`` -> ``race_flag_filly_only`` (NOT ``race_flag_mare_only``)."""
        flags = derive_race_flags("牝馬オープン (牝)")
        assert flags["race_flag_filly_only"] is True
        # mare_only is never set by the crosswalk (Kaggle-side compat).
        assert flags["race_flag_mare_only"] is None

    def test_international_to_graded_stakes(self) -> None:
        """HIGH #6 Kaggle-compat: ``(国際)`` -> ``race_flag_graded_stakes``."""
        flags = derive_race_flags("4歳以上オープン (国際)(特指)(ハンデ)")
        assert flags["race_flag_graded_stakes"] is True
        assert flags["race_flag_special_weight"] is True
        assert flags["race_flag_handicap"] is True

    def test_grade_g1(self) -> None:
        """``東京優駿(GI)`` -> graded + stakes."""
        flags = derive_race_flags("3歳オープン", race_name="東京優駿(GI)")
        assert flags["race_flag_graded_stakes"] is True
        assert flags["race_flag_stakes"] is True

    def test_grade_fullwidth(self) -> None:
        """Full-width ``ＧＩ`` form is also recognized."""
        flags = derive_race_flags("3歳オープン", race_name="東京優駿（ＧＩ）")
        assert flags["race_flag_graded_stakes"] is True
        assert flags["race_flag_stakes"] is True

    def test_maiden(self) -> None:
        """``3歳未勝利`` -> ``race_flag_maiden`` True."""
        flags = derive_race_flags("3歳未勝利")
        assert flags["race_flag_maiden"] is True

    def test_exactly_20_keys(self) -> None:
        """The flag dict carries EXACTLY the 20 ``race_flag_*`` fields from RaceSchema."""
        flags = derive_race_flags("3歳未勝利")
        schema_flag_names = {
            name for name in RaceSchema.model_fields if name.startswith("race_flag_")
        }
        assert len(flags) == 20
        assert set(flags.keys()) == schema_flag_names

    def test_unknown_flags_none(self) -> None:
        """Unmatched flags stay ``None`` (not ``False``)."""
        flags = derive_race_flags("4歳以上1000万下")
        assert flags["race_flag_amateur"] is None
        assert flags["race_flag_female_jockey"] is None

    def test_colt_only_derivable(self) -> None:
        """CYCLE-2 #2: ``(牡)`` -> ``race_flag_colt_only`` (was missing in Cycle-1)."""
        flags = derive_race_flags("サラ系4歳以上1000万下 (牡)")
        assert flags["race_flag_colt_only"] is True

    def test_apprentice_bare_form_derivable(self) -> None:
        """CYCLE-2 #2: bare ``見習騎手`` (no parens) -> ``race_flag_apprentice``.

        ``column_mapping.py:66`` maps ``レース記号/見習騎手`` WITHOUT parens; the
        bare form must match so the field is never silently None.
        """
        flags = derive_race_flags("3歳未勝利 見習騎手")
        assert flags["race_flag_apprentice"] is True

    def test_apprentice_paren_form_derivable(self) -> None:
        """CYCLE-2 #2: parenthesized ``(見習騎手)`` (netkeiba-rendered) also matches."""
        flags = derive_race_flags("3歳未勝利 (見習騎手)")
        assert flags["race_flag_apprentice"] is True

    @pytest.mark.parametrize(
        "target",
        sorted(
            {
                v[1]
                for k, v in KAGGLE_COLUMN_MAP.items()
                if k.startswith("レース記号/")
            }
        ),
    )
    def test_crosswalk_covers_all_kaggle_flag_targets(self, target: str) -> None:
        """CYCLE-2 #2 parametrized coverage guard.

        For each of the 13 unique ``race_flag_*`` targets that
        ``KAGGLE_COLUMN_MAP`` defines, assert that AT LEAST ONE entry in
        ``FLAG_CROSSWALK`` produces that target. A missing target yields a
        named failure (e.g. ``target='race_flag_colt_only'[FAIL]``) so the
        gap is impossible to overlook.
        """
        covered = {field_name for _pattern, field_name in FLAG_CROSSWALK}
        assert target in covered, (
            f"CYCLE-2 #2 regression: KAGGLE target {target!r} has no pattern "
            f"in FLAG_CROSSWALK (covered={sorted(covered)})"
        )


# ---------------------------------------------------------------------------
# TestResolveColumnsByHeader
# ---------------------------------------------------------------------------


class TestResolveColumnsByHeader:
    """HIGH #10: header-driven column resolution (no hardcoded indices)."""

    def test_maps_headers_to_indices(self) -> None:
        html = (
            "<table>"
            "<tr><th>着順</th><th>馬名</th></tr>"
            "<tr><td>1</td><td>馬A</td></tr>"
            "</table>"
        )
        table = BeautifulSoup(html, "lxml").find("table")
        assert table is not None  # narrow type for mypy
        aliases = {"finish_position": ["着順"], "horse_name": ["馬名"]}
        resolved = resolve_columns_by_header(table, aliases)
        assert resolved == {"finish_position": 0, "horse_name": 1}

    def test_missing_header_skipped(self) -> None:
        """A table lacking ``馬番`` does NOT include ``horse_number``."""
        html = (
            "<table>"
            "<tr><th>着順</th><th>馬名</th></tr>"
            "<tr><td>1</td><td>馬A</td></tr>"
            "</table>"
        )
        table = BeautifulSoup(html, "lxml").find("table")
        assert table is not None
        resolved = resolve_columns_by_header(table, DEFAULT_HEADER_ALIASES)
        assert "horse_number" not in resolved
        # Other matched headers ARE present.
        assert "finish_position" in resolved
        assert "horse_name" in resolved

    def test_no_th_returns_empty(self) -> None:
        """A header-less table returns an empty dict (does not raise)."""
        html = "<table><tr><td>1</td><td>x</td></tr></table>"
        table = BeautifulSoup(html, "lxml").find("table")
        assert table is not None
        resolved = resolve_columns_by_header(table, DEFAULT_HEADER_ALIASES)
        assert resolved == {}


# ---------------------------------------------------------------------------
# TestParseRaceHtmlGolden — fixture-driven end-to-end (HIGH #9 parser side)
# ---------------------------------------------------------------------------


class TestParseRaceHtmlGolden:
    """End-to-end ``parse_race_html`` against the 5 authentic fixtures."""

    @pytest.mark.parametrize("race_id, axis", GOLDEN_FIXTURES)
    def test_returns_three_keys(self, race_id: str, axis: str) -> None:
        """Parser returns ``{race, entries, results}`` for each fixture."""
        path = FIXTURES_DIR / f"{race_id}.html"
        assert path.exists(), f"fixture missing: {path}"
        out = parse_race_html(path)
        assert set(out.keys()) >= {"race", "entries", "results"}

    @pytest.mark.parametrize("race_id, axis", GOLDEN_FIXTURES)
    def test_horse_race_id_is_14_digits(self, race_id: str, axis: str) -> None:
        """HIGH #2: every horse_race_id is the 14-digit concat (no underscore)."""
        out = parse_race_html(FIXTURES_DIR / f"{race_id}.html")
        assert out["entries"], f"no entries parsed for {race_id}"
        for entry in out["entries"]:
            assert re.fullmatch(r"\d{14}", entry["horse_race_id"]), (
                f"horse_race_id {entry['horse_race_id']!r} is not 14 digits"
            )
            assert "_" not in entry["horse_race_id"]
        # Same for results.
        for result in out["results"]:
            assert re.fullmatch(r"\d{14}", result["horse_race_id"])

    @pytest.mark.parametrize("race_id, axis", GOLDEN_FIXTURES)
    def test_no_head_count_field(self, race_id: str, axis: str) -> None:
        """MEDIUM: race dict does NOT carry the runner-count pseudo-field."""
        out = parse_race_html(FIXTURES_DIR / f"{race_id}.html")
        assert "head_count" not in out["race"]

    @pytest.mark.parametrize("race_id, axis", GOLDEN_FIXTURES)
    def test_surface_detail_emitted(self, race_id: str, axis: str) -> None:
        """MEDIUM: surface_detail / course_detail / track_condition_detail emitted (None ok)."""
        out = parse_race_html(FIXTURES_DIR / f"{race_id}.html")
        race = out["race"]
        assert "surface_detail" in race
        assert "course_detail" in race
        assert "track_condition_detail" in race

    @pytest.mark.parametrize("race_id, axis", GOLDEN_FIXTURES)
    def test_race_dict_has_all_flag_keys(self, race_id: str, axis: str) -> None:
        """Race dict carries all 20 ``race_flag_*`` keys (CYCLE-2 #2 application)."""
        race = parse_race_html(FIXTURES_DIR / f"{race_id}.html")["race"]
        schema_flag_names = {
            name for name in RaceSchema.model_fields if name.startswith("race_flag_")
        }
        assert set(name for name in race if name.startswith("race_flag_")) == schema_flag_names

    @pytest.mark.parametrize(
        "race_id, axis, expected_surface",
        [
            ("202206050509", "turf base", "芝"),
            ("202309030811", "graded G1", "芝"),
            ("202405010809", "dirt", "ダート"),
            ("202206050508", "dirt", "ダート"),
            ("202209060504", "obstacle", "ダート"),
        ],
    )
    def test_surface_extracted(
        self, race_id: str, axis: str, expected_surface: str
    ) -> None:
        """Surface (芝 / ダート) extracted correctly across diversity axes."""
        race = parse_race_html(FIXTURES_DIR / f"{race_id}.html")["race"]
        assert race["surface"] == expected_surface, (
            f"{race_id} ({axis}): expected surface {expected_surface!r}, "
            f"got {race['surface']!r}"
        )

    @pytest.mark.parametrize(
        "race_id, axis, expected_course, expected_code",
        [
            ("202206050509", "中山 turf base", "中山", "06"),
            ("202309030811", "阪神 G1", "阪神", "09"),
            ("202405010809", "東京 dirt", "東京", "05"),
            ("202206050508", "中山 dirt", "中山", "06"),
            ("202209060504", "阪神 obstacle", "阪神", "09"),
        ],
    )
    def test_course_code_extracted(
        self,
        race_id: str,
        axis: str,
        expected_course: str,
        expected_code: str,
    ) -> None:
        """HIGH #5 application: course_name and code resolved from authoritative map."""
        race = parse_race_html(FIXTURES_DIR / f"{race_id}.html")["race"]
        assert race["course_name"] == expected_course
        assert race["course_code"] == expected_code
        # Cross-check against the single source of truth.
        assert COURSE_CODE_MAP[expected_course] == expected_code

    @pytest.mark.parametrize(
        "race_id, axis, expected_distance",
        [
            ("202206050509", "turf base", 1600),
            ("202309030811", "G1 turf", 2200),
            ("202405010809", "dirt", 1600),
            ("202206050508", "dirt short", 1200),
            ("202209060504", "obstacle", 3110),
        ],
    )
    def test_distance_extracted(
        self, race_id: str, axis: str, expected_distance: int
    ) -> None:
        """Distance (m) extracted correctly for turf, dirt, and obstacle."""
        race = parse_race_html(FIXTURES_DIR / f"{race_id}.html")["race"]
        assert race["distance"] == expected_distance, (
            f"{race_id} ({axis}): expected distance {expected_distance}, "
            f"got {race['distance']!r}"
        )

    @pytest.mark.parametrize(
        "race_id, axis, expected_count",
        [
            ("202206050509", "turf base", 13),
            ("202309030811", "G1 large field", 17),
            ("202405010809", "dirt", 11),
            ("202206050508", "dirt", 16),
            ("202209060504", "obstacle", 11),
        ],
    )
    def test_horse_count(self, race_id: str, axis: str, expected_count: int) -> None:
        """Number of entries/results matches the actual field size."""
        out = parse_race_html(FIXTURES_DIR / f"{race_id}.html")
        assert len(out["entries"]) == expected_count
        assert len(out["results"]) == expected_count

    def test_obstacle_detected(self) -> None:
        """Obstacle race fixture (axis #5) sets ``obstacle='障害'``."""
        race = parse_race_html(FIXTURES_DIR / "202209060504.html")["race"]
        assert race["obstacle"] == "障害"

    def test_flag_crosswalk_applied_on_graded_fixture(self) -> None:
        """The G1 fixture sets ``race_flag_graded_stakes`` (Kaggle compat)."""
        race = parse_race_html(FIXTURES_DIR / "202309030811.html")["race"]
        # 宝塚記念 smalltxt: ``(国際)(指)(定量)`` -> graded_stakes / condition_race / bonus_weight
        assert race["race_flag_graded_stakes"] is True
        assert race["race_flag_condition_race"] is True  # from (指)
        assert race["race_flag_bonus_weight"] is True  # from (定量)

    def test_race_name_extracted_from_title(self) -> None:
        """Rule 1 deviation fix: race_name comes from ``<title>`` not ``<h1>``."""
        # The G1 fixture: <title>宝塚記念｜2023年6月25日 | ...</title>
        race = parse_race_html(FIXTURES_DIR / "202309030811.html")["race"]
        assert race["race_name"] == "宝塚記念"
        # Turf base fixture: ひいらぎ賞
        race2 = parse_race_html(FIXTURES_DIR / "202206050509.html")["race"]
        assert race2["race_name"] == "ひいらぎ賞"

    def test_finish_position_first_row_is_one(self) -> None:
        """First result row's finish_position is 1 (winner) for each fixture."""
        for race_id, _axis in GOLDEN_FIXTURES:
            out = parse_race_html(FIXTURES_DIR / f"{race_id}.html")
            assert out["results"], f"no results for {race_id}"
            assert out["results"][0]["finish_position"] == 1, (
                f"{race_id}: expected first finish_position=1, "
                f"got {out['results'][0]['finish_position']!r}"
            )

    def test_finish_note_handling_constructed(self) -> None:
        """Finish-note handling: 中/取/失/除/再 -> position None; 降 keeps position.

        None of the 5 fixtures contain a 取/中 scratched runner (axis #4 was
        optional per Plan 04-04 Task 3), so we verify the contract on
        constructed ``_parse_finish_position_cell`` inputs. The parser's
        private helper mirrors kaggle_converter.process_finish_position.
        """
        from src.scraper.parser import _parse_finish_position_cell

        # Null-notes: position dropped, note preserved.
        for note in ("中", "取", "失", "除", "再"):
            pos, finish_note = _parse_finish_position_cell(note)
            assert pos is None, f"note {note!r}: expected pos None, got {pos!r}"
            assert finish_note == note

        # Demotion: 5降 keeps position 5 and records 降 as the note.
        pos, finish_note = _parse_finish_position_cell("5降")
        assert pos == 5
        assert finish_note == "降"

        # Plain numeric.
        pos, finish_note = _parse_finish_position_cell("3")
        assert pos == 3
        assert finish_note is None

    def test_corner_parsing_variability(self) -> None:
        """MEDIUM: corner_1..4 keys exist (None ok); 2, 3, 4 positions do not crash.

        The dirt short-track fixture (202206050508) has 2-corner 通過 cells;
        the turf base fixture (202206050509) has 3-corner cells; the G1
        fixture (202309030811) has 4-corner cells. All parse without error.
        """
        for race_id, _axis in GOLDEN_FIXTURES:
            out = parse_race_html(FIXTURES_DIR / f"{race_id}.html")
            for result in out["results"]:
                # All four corner_N keys are always present (None when absent).
                for n in (1, 2, 3, 4):
                    assert f"corner_{n}" in result

    def test_horse_race_id_matches_race_id_plus_number(self) -> None:
        """HIGH #2 cross-check: horse_race_id == f'{race_id}{horse_number:02d}'."""
        for race_id, _axis in GOLDEN_FIXTURES:
            out = parse_race_html(FIXTURES_DIR / f"{race_id}.html")
            for entry in out["entries"]:
                expected = f"{race_id}{entry['horse_number']:02d}"
                assert entry["horse_race_id"] == expected


class TestParseRaceHtmlFilenameValidation:
    """WR-01: parse_race_html validates the filename stem is a 12-digit race_id.

    Without this guard a misnamed fixture (e.g. ``foo.html``) would inject
    ``race_id="foo"``, silently producing a corrupt race row whose
    entries/results all fail the 14-digit horse_race_id validation and get
    dropped -- an empty entries list with a corrupt race row.
    """

    def test_non_numeric_stem_raises(self, tmp_path: Path) -> None:
        """A non-numeric filename stem is rejected at parse entry."""
        bad_path = tmp_path / "foo.html"
        bad_path.write_text("<html></html>", encoding="utf-8")
        with pytest.raises(ValueError) as excinfo:
            parse_race_html(bad_path)
        msg = str(excinfo.value)
        assert "foo" in msg
        assert "12-digit" in msg

    def test_short_numeric_stem_raises(self, tmp_path: Path) -> None:
        """A too-short numeric stem (e.g. 10 digits) is rejected."""
        bad_path = tmp_path / "2022010501.html"
        bad_path.write_text("<html></html>", encoding="utf-8")
        with pytest.raises(ValueError):
            parse_race_html(bad_path)

    def test_long_numeric_stem_raises(self, tmp_path: Path) -> None:
        """A too-long numeric stem (e.g. 13 digits) is rejected."""
        bad_path = tmp_path / "2022010501013.html"
        bad_path.write_text("<html></html>", encoding="utf-8")
        with pytest.raises(ValueError):
            parse_race_html(bad_path)

    def test_valid_12_digit_stem_accepted(self) -> None:
        """Sanity: a valid 12-digit-stemmed golden fixture parses normally."""
        out = parse_race_html(FIXTURES_DIR / "202206050509.html")
        assert set(out.keys()) >= {"race", "entries", "results"}
        assert out["race"]["race_id"] == "202206050509"
