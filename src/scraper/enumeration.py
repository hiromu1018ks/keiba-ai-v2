"""Three-level netkeiba calendar enumeration.

Implements D-04's locked traversal strategy: month -> race day -> race. The
calendar page for a given ``(year, month)`` lists race-day links; each race-day
page lists the individual races held that day. The result is a deduplicated
``list[RaceRef]`` carrying both ``race_id`` and the authoritative
``race_date`` (parsed from the calendar/day page).

Key invariants (all guarded by tests in ``tests/scraper/test_enumeration.py``):

1. **Cycle-1 HIGH #1** -- ``race_date`` comes from the enclosing day, NEVER
   from ``race_id[4:6]`` (which is the JRA course code ``YYYYPPCCDDRR``, not a
   calendar month).
2. **Cycle-1 HIGH #4** -- D-04's three-level traversal is implemented as
   distinct functions, not collapsed into one.
3. **Cycle-2 HIGH #1** -- every URL handed to ``fetch_html`` is ABSOLUTE. The
   netkeiba calendar emits relative ``/race/list/{8d}/`` hrefs; Playwright's
   ``page.goto()`` requires an absolute URL, so these are absolutized via
   ``urllib.parse.urljoin(BASE_URL, href)`` before being forwarded.
4. **T-04-03 (tampering)** -- every ``race_id`` is validated with
   ``re.fullmatch(r"\\d{12}", race_id)``; malformed IDs are logged and dropped.

The browser lifecycle is NOT owned here. Enumeration accepts an injected
``fetch_html: Callable[[str], Optional[str]]`` callable so it never launches
Playwright itself (the Plan 03 ``FetcherSession`` owns the browser and enforces
rate limiting, T-04-04).
"""

import datetime
import re
from typing import Callable, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from loguru import logger

from src.scraper.models import RaceRef

# netkeiba absolute origin. Every urljoin call resolves relative hrefs against
# this constant (Cycle-2 #1).
BASE_URL: str = "https://db.netkeiba.com"

# Regex used to locate race-day links in the monthly calendar HTML. The 8-digit
# segment encodes YYYYMMDD.
_RACE_DAY_HREF_RE = re.compile(r"/race/list/(\d{8})/?")

# Regex used to locate individual race links on a race-day page. Captures any
# numeric segment (not just 12 digits) so malformed hrefs like
# ``/race/2022010501/`` (10 digits) or ``/race/2022010501011/`` (13 digits)
# still enter the validation branch and emit a warning via the
# _RACE_ID_RE.fullmatch check below (T-04-03). Non-numeric segments
# (``/race/list/``, ``/race/result/``, etc.) are intentionally NOT matched --
# they are legitimate non-race links, not malformed race IDs.
_RACE_HREF_RE = re.compile(r"/race/(\d+)/?")

# Validation regex for race_id. Used with re.fullmatch so any non-12-digit
# value (shorter, longer, or non-numeric) is rejected.
_RACE_ID_RE = re.compile(r"\d{12}")


def parse_calendar_month_html(html: str) -> list[tuple[str, datetime.date]]:
    """Parse a monthly netkeiba calendar page into absolute day URLs.

    The calendar page lists one link per racing day, with hrefs shaped like
    ``/race/list/{YYYYMMDD}/``. Each href is ABSOLUTIZED via ``urljoin`` so the
    caller can hand the result directly to ``fetch_html`` (Playwright cannot
    navigate relative URLs -- Cycle-2 #1).

    Parameters
    ----------
    html : str
        Raw HTML of ``https://db.netkeiba.com/race/calendar/{YYYYMM}/``.

    Returns
    -------
    list[tuple[str, datetime.date]]
        Ordered list of ``(absolute_day_url, race_day_date)``. Empty list (NOT
        ``None``) when the page has no day links (e.g. a cancelled month or a
        month with no JRA flat racing).
    """
    soup = BeautifulSoup(html, features="lxml")
    results: list[tuple[str, datetime.date]] = []
    seen_urls: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href: str = anchor["href"]
        match = _RACE_DAY_HREF_RE.search(href)
        if match is None:
            continue
        yyyymmdd = match.group(1)
        try:
            race_day_date = datetime.datetime.strptime(yyyymmdd, "%Y%m%d").date()
        except ValueError:
            logger.warning(f"Skipping unparseable race-day date segment: {yyyymmdd!r}")
            continue
        # Cycle-2 #1: absolutize the relative href before yielding. urljoin
        # resolves /race/list/... against BASE_URL -> https://db.netkeiba.com/...
        day_url = urljoin(BASE_URL, href)
        if day_url in seen_urls:
            continue
        seen_urls.add(day_url)
        results.append((day_url, race_day_date))

    return results


def parse_race_day_html(html: str, race_day_date: datetime.date) -> list[RaceRef]:
    """Parse a race-day (race list) page into ``RaceRef`` records.

    Individual race links are shaped like ``/race/{12-digit race_id}/``. The
    href itself is NOT returned -- the fetcher reconstructs the URL from
    ``race_id`` -- so no second ``urljoin`` is needed here.

    Parameters
    ----------
    html : str
        Raw HTML of a race-day page (the target of an absolute day URL).
    race_day_date : datetime.date
        Calendar date of the enclosing race day. This is the AUTHORITATIVE
        source for every emitted ``RaceRef.race_date`` -- NOT ``race_id[4:6]``
        (Cycle-1 HIGH #1).

    Returns
    -------
    list[RaceRef]
        Possibly empty. Malformed race_ids are logged and dropped (T-04-03).
    """
    soup = BeautifulSoup(html, features="lxml")
    refs: list[RaceRef] = []
    seen_ids: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href: str = anchor["href"]
        match = _RACE_HREF_RE.search(href)
        if match is None:
            continue
        race_id = match.group(1)
        if not _RACE_ID_RE.fullmatch(race_id):
            logger.warning(f"Dropping malformed race_id: {race_id!r}")
            continue
        if race_id in seen_ids:
            continue
        seen_ids.add(race_id)
        # race_date comes from the enclosing day, NEVER from race_id[4:6].
        refs.append(RaceRef(race_id=race_id, race_date=race_day_date))

    return refs


def enumerate_race_day_urls(
    year: int,
    month: int,
    fetch_html: Callable[[str], Optional[str]],
) -> list[tuple[str, datetime.date]]:
    """Fetch and parse one month of the netkeiba calendar.

    Builds the calendar URL ``https://db.netkeiba.com/race/calendar/{YYYYMM}/``
    (absolute via ``urljoin``), calls ``fetch_html``, and delegates parsing to
    ``parse_calendar_month_html`` (which yields already-absolutized day URLs).

    Parameters
    ----------
    year, month : int
        Calendar month to enumerate.
    fetch_html : Callable[[str], Optional[str]]
        Injected transport. Returns the page HTML or ``None`` on failure.

    Returns
    -------
    list[tuple[str, datetime.date]]
        Absolutized day URLs and their dates. Empty list (NOT raised) when
        ``fetch_html`` returns ``None`` for the calendar page -- the caller
        (``enumerate_races``) decides whether to retry.
    """
    calendar_url = urljoin(BASE_URL, f"/race/calendar/{year}{month:02d}/")
    html = fetch_html(calendar_url)
    if html is None:
        logger.warning(
            f"fetch_html returned None for calendar page {calendar_url}; "
            f"returning empty day list for {year}-{month:02d}"
        )
        return []
    return parse_calendar_month_html(html)


def enumerate_races_for_day(
    day_url: str,
    race_day_date: datetime.date,
    fetch_html: Callable[[str], Optional[str]],
) -> list[RaceRef]:
    """Fetch and parse one race-day page.

    ``day_url`` is EXPECTED to be absolute (the caller ``enumerate_races``
    receives absolute URLs from ``enumerate_race_day_urls`` ->
    ``parse_calendar_month_html``). As a defensive guard against a caller that
    forgets to absolutize (Cycle-2 #1), a non-``http`` input is repaired via
    ``urljoin(BASE_URL, day_url)``.

    Parameters
    ----------
    day_url : str
        Absolute URL of the race-day page.
    race_day_date : datetime.date
        Calendar date of the day (authoritative source for ``RaceRef.race_date``).
    fetch_html : Callable[[str], Optional[str]]
        Injected transport.

    Returns
    -------
    list[RaceRef]
        Possibly empty. ``None`` from ``fetch_html`` is logged and returns
        ``[]`` rather than raising.
    """
    # Cycle-2 #1 defensive: repair a relative day_url if a caller forgot.
    if not day_url.startswith("http"):
        logger.warning(
            f"enumerate_races_for_day received a relative day_url {day_url!r}; "
            f"absolutizing via urljoin(BASE_URL, ...)"
        )
        day_url = urljoin(BASE_URL, day_url)

    html = fetch_html(day_url)
    if html is None:
        logger.warning(
            f"fetch_html returned None for race-day page {day_url}; "
            f"returning empty race list"
        )
        return []
    return parse_race_day_html(html, race_day_date)


def enumerate_races(
    start_date: datetime.date,
    end_date: datetime.date,
    fetch_html: Callable[[str], Optional[str]],
) -> list[RaceRef]:
    """Enumerate every race in ``[start_date, end_date]`` inclusive.

    Implements D-04's locked three-level traversal:
    ``enumerate_races`` -> ``enumerate_race_day_urls`` (per month) ->
    ``enumerate_races_for_day`` (per racing day). Day dates are filtered to
    ``[start_date, end_date]`` so partial months at the boundaries respect
    D-05's 2026-05-31 cutoff. Results are deduplicated by ``race_id`` (first
    occurrence wins, preserving stable order).

    Parameters
    ----------
    start_date, end_date : datetime.date
        Inclusive date range. ``start_date <= end_date`` is assumed.
    fetch_html : Callable[[str], Optional[str]]
        Injected transport shared across the whole batch (the Plan 03 session
        owns the browser and rate-limiting, T-04-04).

    Returns
    -------
    list[RaceRef]
        Deduplicated ``RaceRef`` records. NEVER bare strings.
    """
    refs: list[RaceRef] = []
    seen_ids: set[str] = set()

    # Iterate every (year, month) touched by the range, inclusive. Using a
    # cursor date advanced month-by-month avoids constructing a giant date list.
    cursor = datetime.date(start_date.year, start_date.month, 1)
    end_month_anchor = datetime.date(end_date.year, end_date.month, 1)

    while cursor <= end_month_anchor:
        year, month = cursor.year, cursor.month
        for day_url, race_day_date in enumerate_race_day_urls(year, month, fetch_html):
            # Boundary filter: skip days outside [start_date, end_date].
            if race_day_date < start_date or race_day_date > end_date:
                continue
            for ref in enumerate_races_for_day(day_url, race_day_date, fetch_html):
                if ref.race_id in seen_ids:
                    continue
                seen_ids.add(ref.race_id)
                refs.append(ref)
        # Advance to the first day of the next month.
        if month == 12:
            cursor = datetime.date(year + 1, 1, 1)
        else:
            cursor = datetime.date(year, month + 1, 1)

    return refs
