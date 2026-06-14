"""Unit tests for ``src.scraper.cache`` (resume layer for enumeration HTML).

These tests verify the resume contract that fixes scrape-resume-ignored:

* The cache wraps any ``fetch_html`` callable transparently.
* Calendar month URLs (``/race/list/{YYYYMM}/``) and race-day URLs
  (``/race/list/{YYYYMMDD}/``) are read from disk on a second call -- the
  underlying transport is NOT consulted.
* Individual race URLs (``/race/{race_id}/``) and any other URL are passed
  straight through to the transport (no cache read, no cache write).
* A transport ``None`` result is NOT cached -- a future run retries instead
  of remembering the failure.
* Writes are atomic (the temp file is gone on success).

Style matches ``tests/scraper/test_enumeration.py`` (real fake transport,
no monkeypatching of internals).
"""

from pathlib import Path
from typing import Optional

from src.scraper.cache import (
    CachedFetcher,
    _cache_path_for_url,
    make_cached_fetcher,
)

BASE = "https://db.netkeiba.com"


def _make_recording_transport(
    table: dict[str, Optional[str]]
) -> tuple[list[str], object]:
    """Return (seen-urls-list, callable) -- the callable records every URL it
    is asked for and looks the answer up in ``table``."""
    seen: list[str] = []

    def _transport(url: str) -> Optional[str]:
        seen.append(url)
        return table.get(url)

    return seen, _transport


class TestCachePathForUrl:
    """``_cache_path_for_url`` -- the URL -> on-disk-path resolver."""

    def test_month_url_maps_to_calendar_dir(self, tmp_raw_dir: Path) -> None:
        url = f"{BASE}/race/list/202201/"
        path = _cache_path_for_url(url, tmp_raw_dir)
        assert path == tmp_raw_dir / "2022" / "calendar" / "01.html"

    def test_month_url_without_trailing_slash(self, tmp_raw_dir: Path) -> None:
        url = f"{BASE}/race/list/202201"
        path = _cache_path_for_url(url, tmp_raw_dir)
        assert path == tmp_raw_dir / "2022" / "calendar" / "01.html"

    def test_day_url_maps_to_year_month_dir(self, tmp_raw_dir: Path) -> None:
        url = f"{BASE}/race/list/20220105/"
        path = _cache_path_for_url(url, tmp_raw_dir)
        assert path == tmp_raw_dir / "2022" / "01" / "20220105_day.html"

    def test_day_url_without_trailing_slash(self, tmp_raw_dir: Path) -> None:
        url = f"{BASE}/race/list/20220105"
        path = _cache_path_for_url(url, tmp_raw_dir)
        assert path == tmp_raw_dir / "2022" / "01" / "20220105_day.html"

    def test_individual_race_url_is_not_cached(self, tmp_raw_dir: Path) -> None:
        # Individual race pages are handled by fetch_race_html SCRP-05 dedup;
        # the cache layer must NOT interfere.
        url = f"{BASE}/race/202201050101/"
        assert _cache_path_for_url(url, tmp_raw_dir) is None

    def test_seven_digit_list_url_is_not_cached(self, tmp_raw_dir: Path) -> None:
        # 7 digits is neither a valid YYYYMM nor YYYYMMDD -- not cacheable.
        url = f"{BASE}/race/list/2022010/"
        assert _cache_path_for_url(url, tmp_raw_dir) is None

    def test_non_netkeiba_url_shape_still_matches(self, tmp_raw_dir: Path) -> None:
        """The resolver is shape-based, NOT host-based: any absolute URL of the
        form ``http(s)://host/race/list/{6 or 8 digits}/`` resolves. This is
        intentional -- the cache layer cares about the path shape, not the
        host (which is locked at the enumeration layer via BASE_URL)."""
        url = "https://example.com/race/list/202201/"
        path = _cache_path_for_url(url, tmp_raw_dir)
        assert path == tmp_raw_dir / "2022" / "calendar" / "01.html"

    def test_relative_url_is_not_cached(self, tmp_raw_dir: Path) -> None:
        """Relative URLs (no scheme) do not match the resolver -- pass-through."""
        assert _cache_path_for_url("/race/list/202201/", tmp_raw_dir) is None


class TestCachedFetcher:
    """End-to-end behaviour of the cache wrapper around a transport."""

    def test_month_page_cached_after_first_fetch(self, tmp_raw_dir: Path) -> None:
        """Second call for the same calendar month URL skips the transport."""
        url = f"{BASE}/race/list/202201/"
        seen, transport = _make_recording_transport({url: "<html>month</html>"})
        fetcher = CachedFetcher(transport, tmp_raw_dir)

        first = fetcher(url)
        assert first == "<html>month</html>"
        assert seen == [url]

        # Second call: cache hit, transport NOT consulted.
        second = fetcher(url)
        assert second == "<html>month</html>"
        assert seen == [url], "transport should not be called on a cache hit"
        # File landed at the expected path.
        assert (tmp_raw_dir / "2022" / "calendar" / "01.html").read_text(
            encoding="utf-8"
        ) == "<html>month</html>"

    def test_day_page_cached_after_first_fetch(self, tmp_raw_dir: Path) -> None:
        url = f"{BASE}/race/list/20220105/"
        seen, transport = _make_recording_transport({url: "<html>day</html>"})
        fetcher = CachedFetcher(transport, tmp_raw_dir)

        first = fetcher(url)
        assert first == "<html>day</html>"
        second = fetcher(url)
        assert second == "<html>day</html>"
        assert seen == [url]
        assert (tmp_raw_dir / "2022" / "01" / "20220105_day.html").is_file()

    def test_individual_race_url_passes_through(self, tmp_raw_dir: Path) -> None:
        """``/race/{race_id}/`` URLs go straight to the transport -- no cache."""
        url = f"{BASE}/race/202201050101/"
        seen, transport = _make_recording_transport({url: "<html>race</html>"})
        fetcher = CachedFetcher(transport, tmp_raw_dir)

        # First call: transport consulted (pass-through).
        assert fetcher(url) == "<html>race</html>"
        # Second call: transport consulted AGAIN -- no cache for race pages.
        assert fetcher(url) == "<html>race</html>"
        assert seen == [url, url], "race URLs must not be cached"
        # No file written anywhere for a race URL.
        assert not list((tmp_raw_dir).rglob("*.html"))

    def test_transport_none_is_not_cached(self, tmp_raw_dir: Path) -> None:
        """A transport failure (None) is NOT cached -- next run retries.

        Sequence:
          call 1 -> transport returns None (simulated transient failure)
          call 2 -> transport returns real HTML

        After call 1 the cache file MUST NOT exist (no zero-byte placeholder
        remembering the failure). After call 2 the cache file holds the
        recovered HTML.
        """
        url = f"{BASE}/race/list/202201/"
        call_count = [0]

        def _failing_then_ok(url_: str) -> Optional[str]:
            call_count[0] += 1
            return None if call_count[0] == 1 else "<html>recovered</html>"

        fetcher = CachedFetcher(_failing_then_ok, tmp_raw_dir)
        cache_file = tmp_raw_dir / "2022" / "calendar" / "01.html"

        # Call 1: failure. No cache file written.
        assert fetcher(url) is None
        assert not cache_file.exists(), "None result must not be cached"

        # Call 2: success. Cache file now holds the recovered HTML.
        assert fetcher(url) == "<html>recovered</html>"
        assert cache_file.read_text(encoding="utf-8") == "<html>recovered</html>"
        assert call_count[0] == 2, "transport should have been called twice"

    def test_zero_byte_cache_file_treated_as_miss(self, tmp_raw_dir: Path) -> None:
        """A pre-existing zero-byte cache file is a miss (consistent with
        fetch_race_html's zero-byte-is-missing semantics)."""
        url = f"{BASE}/race/list/202201/"
        cache_file = tmp_raw_dir / "2022" / "calendar" / "01.html"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.touch()  # zero-byte file
        assert cache_file.stat().st_size == 0

        seen, transport = _make_recording_transport({url: "<html>real</html>"})
        fetcher = CachedFetcher(transport, tmp_raw_dir)

        result = fetcher(url)
        assert result == "<html>real</html>"
        assert seen == [url], "zero-byte cache file should be treated as a miss"
        # File is now populated.
        assert cache_file.read_text(encoding="utf-8") == "<html>real</html>"

    def test_no_temp_file_left_after_write(self, tmp_raw_dir: Path) -> None:
        """Atomic write discipline: the .tmp file is gone after a successful write."""
        url = f"{BASE}/race/list/202201/"
        seen, transport = _make_recording_transport({url: "<html>x</html>"})
        fetcher = CachedFetcher(transport, tmp_raw_dir)

        fetcher(url)
        cache_file = tmp_raw_dir / "2022" / "calendar" / "01.html"
        assert cache_file.is_file()
        # No .tmp sibling lingering.
        assert not cache_file.with_suffix(".html.tmp").exists()
        assert not list(tmp_raw_dir.rglob("*.tmp"))


class TestMakeCachedFetcher:
    """The convenience factory returns a plain Callable matching the transport contract."""

    def test_factory_returns_callable(self, tmp_raw_dir: Path) -> None:
        url = f"{BASE}/race/list/202201/"
        seen, transport = _make_recording_transport({url: "<html>y</html>"})
        wrapped = make_cached_fetcher(transport, tmp_raw_dir)

        # Callable -- not a class instance exposed at the call site.
        assert callable(wrapped)
        assert wrapped(url) == "<html>y</html>"
        assert wrapped(url) == "<html>y</html>"  # second call hits the cache
        assert seen == [url]
