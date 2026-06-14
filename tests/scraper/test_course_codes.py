"""Tests for ``src/scraper/course_codes``.

Guards the Cycle-1 HIGH #5 course-code correction (福島=03, 新潟=04 — the
previous draft had them swapped) by parametrizing over ALL 10 JRA venues
and asserting both directions of the map.
"""

import pytest

from src.scraper.course_codes import COURSE_CODE_MAP, COURSE_CODE_REVERSE


class TestCourseCodes:
    """Course-code regression guard (HIGH #5)."""

    def test_all_10_venues_present(self) -> None:
        """All 10 JRA venues are keyed in COURSE_CODE_MAP."""
        expected = {"札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"}
        assert set(COURSE_CODE_MAP.keys()) == expected

    @pytest.mark.parametrize(
        "name, code",
        [
            ("札幌", "01"),
            ("函館", "02"),
            ("福島", "03"),  # HIGH #5: was 04 in the buggy draft
            ("新潟", "04"),  # HIGH #5: was 03 in the buggy draft
            ("東京", "05"),
            ("中山", "06"),
            ("中京", "07"),
            ("京都", "08"),
            ("阪神", "09"),
            ("小倉", "10"),
        ],
    )
    def test_specific_codes(self, name: str, code: str) -> None:
        """Each venue maps to its authoritative 2-digit code."""
        assert COURSE_CODE_MAP[name] == code

    def test_reverse_map(self) -> None:
        """Reverse map inverts COURSE_CODE_MAP exactly."""
        # Spot-check the previously-buggy pair.
        assert COURSE_CODE_REVERSE["03"] == "福島"
        assert COURSE_CODE_REVERSE["04"] == "新潟"
        # Full inversion invariant.
        for name, code in COURSE_CODE_MAP.items():
            assert COURSE_CODE_REVERSE[code] == name

    def test_map_size(self) -> None:
        """Map size is exactly 10 (no extra or missing venues)."""
        assert len(COURSE_CODE_MAP) == 10
        assert len(COURSE_CODE_REVERSE) == 10
