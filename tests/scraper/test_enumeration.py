"""Tests for ``src/scraper/enumeration``.

Covers the D-04 three-level traversal, race_id validation, date-range
filtering, None-fetch tolerance, deduplication, and the Cycle-2 #1 URL
absolutization invariants. Every test uses a FAKE ``fetch_html`` backed by a
dict mapping absolute URL -> HTML string. If enumeration ever asked for a
relative URL the fake would return None and the test would fail -- this
implicitly enforces Cycle-2 #1 across the whole suite.
"""

import datetime
import re
from typing import Optional
from urllib.parse import urljoin

import pytest

from src.scraper.enumeration import (
    BASE_URL,
    enumerate_race_day_urls,
    enumerate_races,
    enumerate_races_for_day,
    parse_calendar_month_html,
    parse_race_day_html,
)
from src.scraper.models import RaceRef


def _make_fake_fetch(table: dict[str, str]) -> "Callable[[str], Optional[str]]":
    """Return a fetch_html callable backed by an absolute-URL -> HTML dict.

    Unknown URLs return None (mirrors the real fetcher's failure contract).
    Recording every URL seen lets tests assert which absolute URL was hit.
    """
    seen: list[str] = []

    from typing import Callable

    def fake(url: str) -> Optional[str]:
        seen.append(url)
        return table.get(url)

    fake.seen = seen  # type: ignore[attr-defined]
    return fake


class TestParseCalendarMonthHtml:
    """parse_calendar_month_html: extracts day links and absolutizes them."""

    def test_extracts_day_links(self) -> None:
        html = (
            '<html><body>'
            '<a href="/race/list/20220105/">5</a>'
            '<a href="/race/list/20220109/">9</a>'
            '</body></html>'
        )
        result = parse_calendar_month_html(html)
        assert len(result) == 2
        dates = [d for _, d in result]
        assert dates == [datetime.date(2022, 1, 5), datetime.date(2022, 1, 9)]

    def test_day_urls_are_absolute(self) -> None:
        """Cycle-2 #1 regression guard: every day_url must be absolute.

        Without urljoin, the URL would be the raw relative string
        ``/race/list/20220105/`` and Playwright's goto would fail.
        """
        html = '<a href="/race/list/20220105/">5</a>'
        result = parse_calendar_month_html(html)
        assert len(result) == 1
        day_url, _ = result[0]
        assert day_url.startswith("https://"), day_url
        expected = urljoin(BASE_URL, "/race/list/20220105/")
        assert day_url == expected, (day_url, expected)
        assert day_url == "https://db.netkeiba.com/race/list/20220105/"

    def test_empty_calendar_returns_empty_list(self) -> None:
        html = "<html><body><p>no racing this month</p></body></html>"
        result = parse_calendar_month_html(html)
        assert result == []
        # Specifically NOT None and does not raise.
        assert isinstance(result, list)

    def test_deduplicates_repeated_day_links(self) -> None:
        html = (
            '<a href="/race/list/20220105/">5</a>'
            '<a href="/race/list/20220105/">5 again</a>'
        )
        result = parse_calendar_month_html(html)
        assert len(result) == 1

    def test_deduplicates_trailing_slash_variance(self) -> None:
        """WR-05: the same day emitted in both forms (``/race/list/20220105/``
        and ``/race/list/20220105``) collapses to a single URL. Without
        trailing-slash normalization the day would be fetched twice -- a
        wasteful double-fetch on a rate-limited scraper."""
        html = (
            '<a href="/race/list/20220105/">with slash</a>'
            '<a href="/race/list/20220105">without slash</a>'
        )
        result = parse_calendar_month_html(html)
        assert len(result) == 1, f"expected 1 (deduped), got {len(result)}"
        # The canonical form carries a trailing slash.
        day_url, _ = result[0]
        assert day_url == "https://db.netkeiba.com/race/list/20220105/", day_url

    def test_rejects_long_digit_run_in_day_href(self) -> None:
        """CR-01: a >8-digit ``/race/list/{N}/`` href is DROPPED, not
        prefix-truncated. Previously ``_RACE_DAY_HREF_RE`` was unanchored and
        ``.search()`` would match the leading 8 digits of a longer run,
        silently emitting a wrong ``race_day_date`` (e.g. ``2022010512`` ->
        ``2022-01-05``) that corrupts the partition key."""
        # 10-digit run -> must be rejected entirely.
        html = '<a href="/race/list/2022010512/">bad</a>'
        result = parse_calendar_month_html(html)
        assert result == [], f"expected empty, got {result}"

        # 11-digit run -> also rejected.
        html = '<a href="/race/list/20220105123/">bad</a>'
        result = parse_calendar_month_html(html)
        assert result == [], f"expected empty, got {result}"

        # 8 digits + non-slash suffix -> also rejected (the 8-digit run must
        # be followed by '/' or end-of-string).
        html = '<a href="/race/list/20220105xyz/">bad</a>'
        result = parse_calendar_month_html(html)
        assert result == [], f"expected empty, got {result}"

        # Sanity: a valid 8-digit href WITH a trailing slash still matches.
        html = '<a href="/race/list/20220105/">ok</a>'
        result = parse_calendar_month_html(html)
        assert len(result) == 1
        assert result[0][1] == datetime.date(2022, 1, 5)

        # Sanity: a valid 8-digit href WITHOUT a trailing slash also matches.
        html = '<a href="/race/list/20220105">ok</a>'
        result = parse_calendar_month_html(html)
        assert len(result) == 1
        assert result[0][1] == datetime.date(2022, 1, 5)


class TestParseRaceDayHtml:
    """parse_race_day_html: builds RaceRef with date from the day argument."""

    def test_extracts_race_refs(self) -> None:
        html = (
            '<html><body>'
            '<a href="/race/202201050101/">R1</a>'
            '<a href="/race/202201050102/">R2</a>'
            '<a href="/race/202201050103/">R3</a>'
            '</body></html>'
        )
        refs = parse_race_day_html(html, datetime.date(2022, 1, 5))
        assert len(refs) == 3
        assert {r.race_id for r in refs} == {
            "202201050101", "202201050102", "202201050103",
        }

    def test_race_date_comes_from_day_not_race_id(self) -> None:
        """Cycle-1 HIGH #1 regression guard.

        race_id starts with ``20220105`` but the authoritative race_date is
        the day argument. No code path reads race_id[4:6] as a month.
        """
        html = '<a href="/race/202201050101/">R1</a>'
        # Pass a deliberately DIFFERENT date than what race_id[0:8] encodes
        # to prove race_date is the day argument, not the race_id prefix.
        day = datetime.date(2022, 1, 10)
        refs = parse_race_day_html(html, day)
        assert len(refs) == 1
        assert refs[0].race_date == day
        # And specifically NOT the date encoded in race_id[0:8].
        assert refs[0].race_date != datetime.date(2022, 1, 5)

    def test_drops_malformed_race_ids(self) -> None:
        """T-04-03 mitigation: malformed race_ids are skipped with a warning.

        loguru does not route through stdlib logging by default, so install a
        capture sink that collects rendered messages into a list for the
        duration of the call.
        """
        from loguru import logger as loguru_logger

        captured: list[str] = []

        def _sink(message: "loguru_logger._loguru_message_record") -> None:  # type: ignore[name-defined]
            # message.record carries the structured payload.
            captured.append(str(message).rstrip("\n"))

        handler_id = loguru_logger.add(_sink, level="WARNING")

        html = (
            '<a href="/race/202201050101/">valid</a>'
            '<a href="/race/2022010501/">too-short-10-digit</a>'
            '<a href="/race/2022010501011/">too-long-13-digit</a>'
            # Note: /race/abc123/ is intentionally NOT a race link in netkeiba's
            # URL scheme (word-based paths like /race/list/ are separate routes),
            # so the extractor regex is numeric-only and does not flag it.
        )
        try:
            refs = parse_race_day_html(html, datetime.date(2022, 1, 5))
        finally:
            loguru_logger.remove(handler_id)

        assert len(refs) == 1
        assert refs[0].race_id == "202201050101"
        # A warning was emitted for the malformed IDs.
        assert any("malformed" in m.lower() or "race_id" in m.lower() for m in captured), \
            captured


class TestEnumerateRaces:
    """enumerate_races + enumerate_races_for_day: 3-level traversal."""

    @staticmethod
    def _calendar_html(*yyyymmdd: str) -> str:
        return "".join(f'<a href="/race/list/{d}/">{d}</a>' for d in yyyymmdd)

    @staticmethod
    def _race_day_html(*race_ids: str) -> str:
        return "".join(f'<a href="/race/{rid}/">{rid}</a>' for rid in race_ids)

    def _build_table(
        self,
        day_to_races: dict[str, list[str]],
        *calendar_days: str,
    ) -> dict[str, str]:
        """Build an absolute-URL -> HTML table for the fake fetch."""
        table: dict[str, str] = {}
        for d in calendar_days:
            day_url = urljoin(BASE_URL, f"/race/list/{d}/")
            table[day_url] = self._race_day_html(*day_to_races.get(d, []))
        return table

    def test_traverses_three_levels(self) -> None:
        """Calendar returns 1 day, day returns 2 races -> 2 RaceRef.

        The fake's keys are ABSOLUTE URLs. If enumeration asked for a relative
        URL the fake would return None and the test would fail -- implicitly
        enforcing Cycle-2 #1.
        """
        calendar_url = urljoin(BASE_URL, "/race/calendar/202201/")
        calendar_html = self._calendar_html("20220105")
        day_races = {"20220105": ["202201050101", "202201050102"]}
        day_table = self._build_table(day_races, "20220105")
        table = {calendar_url: calendar_html, **day_table}
        fake = _make_fake_fetch(table)

        refs = enumerate_races(
            datetime.date(2022, 1, 1), datetime.date(2022, 1, 31), fake
        )
        assert len(refs) == 2
        assert {r.race_id for r in refs} == {"202201050101", "202201050102"}
        # Every fetch was against an absolute URL.
        assert all(u.startswith("https://") for u in fake.seen), fake.seen

    def test_deduplicates_across_days(self) -> None:
        """Two days both list the same race_id -> result has it exactly once."""
        calendar_url = urljoin(BASE_URL, "/race/calendar/202201/")
        calendar_html = self._calendar_html("20220105", "20220106")
        day_table = self._build_table(
            {"20220105": ["202201050101"], "20220106": ["202201050101"]},
            "20220105", "20220106",
        )
        table = {calendar_url: calendar_html, **day_table}
        fake = _make_fake_fetch(table)

        refs = enumerate_races(
            datetime.date(2022, 1, 1), datetime.date(2022, 1, 31), fake
        )
        assert len(refs) == 1
        assert refs[0].race_id == "202201050101"

    def test_filters_by_date_range(self) -> None:
        """A day at 2022-02-01 in the calendar is excluded when end is 2022-01-31."""
        calendar_url = urljoin(BASE_URL, "/race/calendar/202201/")
        calendar_html = self._calendar_html("20220105", "20220201")
        # Note: in real life Feb 1 wouldn't appear in the Jan calendar, but
        # the filter must defend against any date the page emits.
        day_table = self._build_table(
            {"20220105": ["202201050101"], "20220201": ["202202010101"]},
            "20220105", "20220201",
        )
        table = {calendar_url: calendar_html, **day_table}
        fake = _make_fake_fetch(table)

        refs = enumerate_races(
            datetime.date(2022, 1, 1), datetime.date(2022, 1, 31), fake
        )
        assert {r.race_id for r in refs} == {"202201050101"}
        # The out-of-range day was NOT fetched (filter applies before fetch).
        feb_day_url = urljoin(BASE_URL, "/race/list/20220201/")
        assert feb_day_url not in fake.seen, fake.seen

    def test_boundary_end_date_inclusive(self) -> None:
        """D-05 cutoff 2026-05-31: a day exactly on end_date IS included."""
        calendar_url = urljoin(BASE_URL, "/race/calendar/202605/")
        calendar_html = self._calendar_html("20260531")
        day_table = self._build_table({"20260531": ["202605310101"]}, "20260531")
        table = {calendar_url: calendar_html, **day_table}
        fake = _make_fake_fetch(table)

        refs = enumerate_races(
            datetime.date(2026, 5, 1), datetime.date(2026, 5, 31), fake
        )
        assert len(refs) == 1
        assert refs[0].race_id == "202605310101"

    def test_handles_fetch_none_gracefully(self) -> None:
        """One day URL returns None -> enumerate_races still returns others."""
        calendar_url = urljoin(BASE_URL, "/race/calendar/202201/")
        calendar_html = self._calendar_html("20220105", "20220109")
        ok_day_url = urljoin(BASE_URL, "/race/list/20220105/")
        bad_day_url = urljoin(BASE_URL, "/race/list/20220109/")
        table = {
            calendar_url: calendar_html,
            ok_day_url: self._race_day_html("202201050101"),
            # bad_day_url intentionally absent -> fake returns None
        }
        fake = _make_fake_fetch(table)

        refs = enumerate_races(
            datetime.date(2022, 1, 1), datetime.date(2022, 1, 31), fake
        )
        assert len(refs) == 1
        assert refs[0].race_id == "202201050101"

    def test_returns_race_refs_not_strings(self) -> None:
        calendar_url = urljoin(BASE_URL, "/race/calendar/202201/")
        calendar_html = self._calendar_html("20220105")
        day_table = self._build_table({"20220105": ["202201050101"]}, "20220105")
        table = {calendar_url: calendar_html, **day_table}
        fake = _make_fake_fetch(table)

        refs = enumerate_races(
            datetime.date(2022, 1, 1), datetime.date(2022, 1, 31), fake
        )
        assert len(refs) >= 1
        assert all(isinstance(x, RaceRef) for x in refs)

    def test_repair_relative_day_url(self) -> None:
        """Cycle-2 #1 defensive guard: a relative day_url is repaired via urljoin.

        Call enumerate_races_for_day directly with a RELATIVE url and verify
        the fake is still hit at the ABSOLUTE URL.
        """
        absolute = urljoin(BASE_URL, "/race/list/20220105/")
        table = {absolute: self._race_day_html("202201050101")}
        fake = _make_fake_fetch(table)

        refs = enumerate_races_for_day(
            "/race/list/20220105/", datetime.date(2022, 1, 5), fake
        )
        assert len(refs) == 1
        assert refs[0].race_id == "202201050101"
        # The repaired (absolute) URL is what the fake actually received.
        assert absolute in fake.seen, fake.seen
        assert "/race/list/20220105/" not in fake.seen or absolute in fake.seen

    def test_calendar_fetch_none_returns_empty(self) -> None:
        """Calendar fetch returns None -> enumerate_race_day_urls returns []."""
        fake = _make_fake_fetch({})  # no entries -> all return None
        result = enumerate_race_day_urls(2022, 1, fake)
        assert result == []

    def test_multi_month_traversal(self) -> None:
        """enumerate_races walks multiple months in the range."""
        jan_cal = urljoin(BASE_URL, "/race/calendar/202201/")
        feb_cal = urljoin(BASE_URL, "/race/calendar/202202/")
        jan_cal_html = self._calendar_html("20220105")
        feb_cal_html = self._calendar_html("20220201")
        day_table = self._build_table(
            {"20220105": ["202201050101"], "20220201": ["202202010101"]},
            "20220105", "20220201",
        )
        table = {
            jan_cal: jan_cal_html, feb_cal: feb_cal_html, **day_table,
        }
        fake = _make_fake_fetch(table)

        refs = enumerate_races(
            datetime.date(2022, 1, 1), datetime.date(2022, 2, 28), fake
        )
        assert {r.race_id for r in refs} == {"202201050101", "202202010101"}
        # Both month calendars were fetched.
        assert jan_cal in fake.seen and feb_cal in fake.seen, fake.seen


class TestRaceIdValidation:
    """Direct validation of the 12-digit race_id contract."""

    def test_fullmatch_12_digits(self) -> None:
        pattern = re.compile(r"\d{12}")
        # Valid 12-digit ID matches.
        assert pattern.fullmatch("202201050101") is not None
        # 11-digit ID does NOT match.
        assert pattern.fullmatch("20220105010") is None
        # 13-digit ID does NOT match.
        assert pattern.fullmatch("2022010501011") is None
        # Non-numeric ID does NOT match.
        assert pattern.fullmatch("20220abc0101") is None

    def test_malformed_ids_dropped_in_parse(self) -> None:
        """End-to-end: malformed IDs never become RaceRef."""
        html = (
            '<a href="/race/202201050101/">valid</a>'
            '<a href="/race/123/">too-short</a>'
            '<a href="/race/2022010501019999/">too-long</a>'
        )
        refs = parse_race_day_html(html, datetime.date(2022, 1, 5))
        assert len(refs) == 1
        assert refs[0].race_id == "202201050101"
