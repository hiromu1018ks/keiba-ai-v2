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
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urljoin

from src.scraper.enumeration import (
    BASE_URL,
    enumerate_race_day_urls,
    enumerate_races,
    enumerate_races_for_day,
    parse_calendar_month_html,
    parse_race_day_html,
)
from src.scraper.models import RaceRef


def _make_fake_fetch(table: dict[str, str]) -> Callable[[str], Optional[str]]:
    """Return a fetch_html callable backed by an absolute-URL -> HTML dict.

    Unknown URLs return None (mirrors the real fetcher's failure contract).
    Recording every URL seen lets tests assert which absolute URL was hit.
    """
    seen: list[str] = []

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

    def test_drops_nar_races_keeps_jra_only(self) -> None:
        """JRA-only filter (CLAUDE.md): NAR place codes (e.g. 35=盛岡) are dropped.

        race_id PP is digits 5-6; JRA central is 01-10. A NAR race_id must NOT
        become a RaceRef -- otherwise it is fetched (wasting a rate-limited
        request on a race the project does not model) and pollutes course_code
        with None at parse time.
        """
        html = (
            '<a href="/race/202205010401/">JRA 東京</a>'   # PP=05 JRA
            '<a href="/race/202135080801/">NAR 盛岡</a>'   # PP=35 NAR
            '<a href="/race/202209020601/">JRA 阪神</a>'   # PP=09 JRA
        )
        refs = parse_race_day_html(html, datetime.date(2022, 5, 1))
        assert {r.race_id for r in refs} == {"202205010401", "202209020601"}
        # No NAR race leaked through.
        jra_codes = {f"{n:02d}" for n in range(1, 11)}
        assert all(r.race_id[4:6] in jra_codes for r in refs), refs


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
        calendar_url = urljoin(BASE_URL, "/race/list/202201/")
        calendar_html = self._calendar_html("20220105")
        day_races = {"20220105": ["202201050101", "202201050102"]}
        day_table = self._build_table(day_races, "20220105")
        table = {calendar_url: calendar_html, **day_table}
        fake = _make_fake_fetch(table)

        refs = enumerate_races(
            datetime.date(2022, 1, 1), datetime.date(2022, 1, 31), fake,
            progress=False,
        )
        assert len(refs) == 2
        assert {r.race_id for r in refs} == {"202201050101", "202201050102"}
        # Every fetch was against an absolute URL.
        assert all(u.startswith("https://") for u in fake.seen), fake.seen

    def test_deduplicates_across_days(self) -> None:
        """Two days both list the same race_id -> result has it exactly once."""
        calendar_url = urljoin(BASE_URL, "/race/list/202201/")
        calendar_html = self._calendar_html("20220105", "20220106")
        day_table = self._build_table(
            {"20220105": ["202201050101"], "20220106": ["202201050101"]},
            "20220105", "20220106",
        )
        table = {calendar_url: calendar_html, **day_table}
        fake = _make_fake_fetch(table)

        refs = enumerate_races(
            datetime.date(2022, 1, 1), datetime.date(2022, 1, 31), fake,
            progress=False,
        )
        assert len(refs) == 1
        assert refs[0].race_id == "202201050101"

    def test_filters_by_date_range(self) -> None:
        """A day at 2022-02-01 in the calendar is excluded when end is 2022-01-31."""
        calendar_url = urljoin(BASE_URL, "/race/list/202201/")
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
            datetime.date(2022, 1, 1), datetime.date(2022, 1, 31), fake,
            progress=False,
        )
        assert {r.race_id for r in refs} == {"202201050101"}
        # The out-of-range day was NOT fetched (filter applies before fetch).
        feb_day_url = urljoin(BASE_URL, "/race/list/20220201/")
        assert feb_day_url not in fake.seen, fake.seen

    def test_boundary_end_date_inclusive(self) -> None:
        """D-05 cutoff 2026-05-31: a day exactly on end_date IS included."""
        calendar_url = urljoin(BASE_URL, "/race/list/202605/")
        calendar_html = self._calendar_html("20260531")
        day_table = self._build_table({"20260531": ["202605310101"]}, "20260531")
        table = {calendar_url: calendar_html, **day_table}
        fake = _make_fake_fetch(table)

        refs = enumerate_races(
            datetime.date(2026, 5, 1), datetime.date(2026, 5, 31), fake,
            progress=False,
        )
        assert len(refs) == 1
        assert refs[0].race_id == "202605310101"

    def test_handles_fetch_none_gracefully(self) -> None:
        """One day URL returns None -> enumerate_races still returns others."""
        calendar_url = urljoin(BASE_URL, "/race/list/202201/")
        calendar_html = self._calendar_html("20220105", "20220109")
        ok_day_url = urljoin(BASE_URL, "/race/list/20220105/")
        table = {
            calendar_url: calendar_html,
            ok_day_url: self._race_day_html("202201050101"),
            # /race/list/20220109/ intentionally absent -> fake returns None
        }
        fake = _make_fake_fetch(table)

        refs = enumerate_races(
            datetime.date(2022, 1, 1), datetime.date(2022, 1, 31), fake,
            progress=False,
        )
        assert len(refs) == 1
        assert refs[0].race_id == "202201050101"

    def test_returns_race_refs_not_strings(self) -> None:
        calendar_url = urljoin(BASE_URL, "/race/list/202201/")
        calendar_html = self._calendar_html("20220105")
        day_table = self._build_table({"20220105": ["202201050101"]}, "20220105")
        table = {calendar_url: calendar_html, **day_table}
        fake = _make_fake_fetch(table)

        refs = enumerate_races(
            datetime.date(2022, 1, 1), datetime.date(2022, 1, 31), fake,
            progress=False,
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
        jan_cal = urljoin(BASE_URL, "/race/list/202201/")
        feb_cal = urljoin(BASE_URL, "/race/list/202202/")
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
            datetime.date(2022, 1, 1), datetime.date(2022, 2, 28), fake,
            progress=False,
        )
        assert {r.race_id for r in refs} == {"202201050101", "202202010101"}
        # Both month calendars were fetched.
        assert jan_cal in fake.seen and feb_cal in fake.seen, fake.seen

    def test_progress_flag_is_output_neutral(self) -> None:
        """enumerate_races(progress=False) and enumerate_races(progress=True)
        produce identical (race_id, race_date) output for the same input.

        Builds the SAME multi-month table as test_multi_month_traversal, then
        creates TWO independent fakes from it (each records its own ``.seen``
        so the two calls don't conflate their fetch logs) and asserts the
        RaceRef output is identical between the two progress modes. Does NOT
        capture stderr or assert anything about tqdm's rendered text -- the
        neutrality claim is at the RaceRef level, not the rendering level.
        """
        jan_cal = urljoin(BASE_URL, "/race/list/202201/")
        feb_cal = urljoin(BASE_URL, "/race/list/202202/")
        jan_cal_html = self._calendar_html("20220105")
        feb_cal_html = self._calendar_html("20220201")
        day_table = self._build_table(
            {"20220105": ["202201050101"], "20220201": ["202202010101"]},
            "20220105", "20220201",
        )
        table = {
            jan_cal: jan_cal_html, feb_cal: feb_cal_html, **day_table,
        }
        fake_off = _make_fake_fetch(table)
        fake_on = _make_fake_fetch(table)

        refs_off = enumerate_races(
            datetime.date(2022, 1, 1), datetime.date(2022, 2, 28), fake_off,
            progress=False,
        )
        refs_on = enumerate_races(
            datetime.date(2022, 1, 1), datetime.date(2022, 2, 28), fake_on,
            progress=True,
        )

        # Sanity: the table actually yields races in both modes.
        assert len(refs_off) > 0, refs_off
        assert len(refs_on) > 0, refs_on
        # Output neutrality: same race_ids, same race_dates, same order.
        assert [(r.race_id, r.race_date) for r in refs_off] == [
            (r.race_id, r.race_date) for r in refs_on
        ]


class TestEnumerateRaceDayUrlsUrlContract:
    """UAT-Test-6 regression guard: the calendar URL form contract.

    The previous ``race/calendar/{YYYYMM}/`` form returns ~40-52KB of
    navigation HTML with ZERO day links on the live netkeiba site (verified by
    UAT-Test-6 live probing during planning). ``/race/list/{YYYYMM}/`` is the
    verified working form. These tests capture the URL passed to ``fetch_html``
    and assert the form, so any silent reversion to the broken form is caught
    immediately.
    """

    def test_enumerate_race_day_urls_constructs_correct_live_url(self) -> None:
        """UAT-Test-6 regression guard: the calendar URL MUST be /race/list/{YYYYMM}/.

        The previous ``race/calendar/{YYYYMM}/`` form returns 0 day links on
        the live site (verified by UAT-Test-6 live probing). This test captures
        the URL passed to fetch_html and asserts it matches the verified
        working form.
        """
        captured: list[str] = []

        def fake(url: str) -> Optional[str]:
            captured.append(url)
            return None

        enumerate_race_day_urls(2023, 6, fake)
        assert captured == ["https://db.netkeiba.com/race/list/202306/"], captured
        assert "/race/calendar/" not in captured[0], (
            "UAT-Test-6 regression: calendar URL reverted to broken form"
        )

    def test_month_is_zero_padded(self) -> None:
        """A single-digit month is zero-padded to two digits in the URL."""
        captured: list[str] = []

        def fake(url: str) -> Optional[str]:
            captured.append(url)
            return None

        enumerate_race_day_urls(2023, 1, fake)
        assert captured == ["https://db.netkeiba.com/race/list/202301/"], captured


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


class TestParseCalendarMonthHtmlGolden:
    """UAT-Test-6 golden-fixture regression guard.

    Parses a real (or synthetic-fallback) ``/race/list/{YYYYMM}/`` calendar
    page and asserts it yields the verified racing days for 2023-06. This
    locks the URL contract: if anyone reverts enumerate_race_day_urls to
    ``race/calendar/``, this test still passes (it tests the parser in
    isolation), but test_enumerate_race_day_urls_constructs_correct_live_url
    will catch the URL revert. Together they form a two-layer guard.
    """

    def test_yields_eight_racing_days_for_202306(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "html" / "calendar_202306.html"
        assert fixture.exists(), f"golden calendar fixture missing: {fixture}"
        html = fixture.read_text(encoding="utf-8")
        results = parse_calendar_month_html(html)
        # The 8 verified racing days for 2023-06 (live-probed 2026-06-14).
        expected_days = {
            datetime.date(2023, 6, 3), datetime.date(2023, 6, 4),
            datetime.date(2023, 6, 10), datetime.date(2023, 6, 11),
            datetime.date(2023, 6, 17), datetime.date(2023, 6, 18),
            datetime.date(2023, 6, 24), datetime.date(2023, 6, 25),
        }
        actual_days = {d for _url, d in results}
        assert actual_days == expected_days, (
            f"UAT-Test-6 golden mismatch: expected {len(expected_days)} days, "
            f"got {len(actual_days)}: {sorted(actual_days)}"
        )
        # Every returned URL is absolute (Cycle-2 #1 still holds).
        assert all(u.startswith("https://") for u, _ in results), results
