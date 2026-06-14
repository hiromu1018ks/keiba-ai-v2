"""Disk cache for enumeration-layer HTML (calendar + race-day pages).

Resumes (scrape-resume-ignored): a re-run of ``run_scrape`` must NOT re-fetch
calendar month pages and race-day list pages that were already fetched in a
previous run. The individual-race HTML layer already has its own dedup
(``fetch_race_html`` SCRP-05: ``out_path.exists() and size>0`` -> skip), but
the two upper enumeration layers (``enumerate_race_day_urls`` ->
``parse_calendar_month_html`` and ``enumerate_races_for_day``) had no such
cache. On every re-run they re-fetched every month and every day page, which
is exactly the symptom the user reported: "中断して再実行した場合にまた最初
からカレンダーの取得が始まってしまう" (resume re-runs from the calendar layer).

This module provides ``CachedFetcher``, a transparent wrapper around any
``fetch_html: Callable[[str], Optional[str]]`` transport that:

1. Intercepts the **calendar page** (``/race/list/{YYYYMM}/``) and the
   **race-day page** (``/race/list/{YYYYMMDD}/``) URLs.
2. On a cache hit (file exists, non-empty), returns the cached HTML without
   calling the underlying transport.
3. On a cache miss, delegates to the underlying transport. A ``None`` result
   (transport failure) is NOT cached -- consistent with ``fetch_race_html``'s
   zero-byte-is-missing semantics so a transient failure is retried next run.
4. A non-``None`` result is written atomically (temp file + ``os.replace``)
   so an interruption mid-write cannot leave a corrupt cache entry that a
   future run would treat as valid.

URLs that match NEITHER pattern (e.g. ``/race/{race_id}/`` individual race
pages, ad-hoc probes) are passed straight through to the underlying transport
WITHOUT touching the cache. Individual race HTML dedup stays the job of
``fetch_race_html`` -- layering two caches on top of each other would be
redundant.

Cache layout (sits alongside the existing raw tree, ``raw_dir``):

* ``{raw_dir}/{YYYY}/calendar/{MM}.html``         <- month page
* ``{raw_dir}/{YYYY}/{MM}/{YYYYMMDD}_day.html``   <- race-day page

The ``_day.html`` suffix distinguishes a race-day list page from an individual
race page (``{race_id}.html``) co-located in the same ``{YYYY}/{MM}/`` dir.

Load-bearing invariants (guarded by ``tests/scraper/test_cache.py``):

1. **Pattern-scoped** -- only ``/race/list/{YYYYMM}/`` (6 digits) and
   ``/race/list/{YYYYMMDD}/`` (8 digits) are cached. Anything else is a
   pass-through.
2. **None not cached** -- a transport failure is retried next run instead of
   being remembered as an empty file.
3. **Atomic write** -- temp file then ``os.replace`` (same discipline as
   ``fetch_race_html``).
4. **Callable protocol preserved** -- ``CachedFetcher(transport)`` returns a
   plain ``Callable[[str], Optional[str]]`` via ``__call__``, so it can be
   dropped in anywhere ``fetch_html`` is accepted (e.g. ``enumerate_races``).
"""

import os
import re
from pathlib import Path
from typing import Callable, Optional

# /race/list/{YYYYMM}/  -> 6-digit month segment.
# /race/list/{YYYYMMDD}/ -> 8-digit day segment.
# Both forms share the same ``/race/list/`` prefix (UAT-Test-6 verified the
# month form). The alternation captures whichever runs; ``re.match`` anchors
# at the start so a deeper path segment cannot accidentally match.
_LIST_PAGE_RE = re.compile(
    r"^https?://[^/]+/race/list/(?P<digits>\d{6,8})/?$"
)


def _cache_path_for_url(url: str, raw_dir: Path) -> Optional[Path]:
    """Return the on-disk cache path for a calendar/day URL, or ``None``.

    ``None`` means "this URL is not a cacheable list page" -- the caller should
    pass it straight through to the underlying transport. The two cacheable
    shapes are:

    * 6 digits -> calendar month page -> ``{raw_dir}/{YYYY}/calendar/{MM}.html``
    * 8 digits -> race-day page      -> ``{raw_dir}/{YYYY}/{MM}/{YYYYMMDD}_day.html``

    Any other URL (including individual ``/race/{race_id}/`` pages and non-
    netkeiba URLs) returns ``None``.
    """
    match = _LIST_PAGE_RE.match(url)
    if match is None:
        return None
    digits = match.group("digits")
    if len(digits) == 6:
        # {YYYY}{MM} calendar month page.
        year, month = digits[:4], digits[4:6]
        return Path(raw_dir) / year / "calendar" / f"{month}.html"
    if len(digits) == 8:
        # {YYYY}{MM}{DD} race-day page.
        year, month = digits[:4], digits[4:6]
        return Path(raw_dir) / year / month / f"{digits}_day.html"
    # 7-digit or 9+ digit runs do not correspond to a netkeiba list page and
    # are treated as non-cacheable pass-through.
    return None


class CachedFetcher:
    """Wrap a ``fetch_html`` callable with a disk cache for list-page HTML.

    Callable protocol: ``__call__(url)`` mirrors ``fetch_html(url)`` so this
    can be passed wherever ``fetch_html`` is expected (notably
    ``enumerate_races(start, end, fetch_html, ...)``).

    Parameters
    ----------
    transport : Callable[[str], Optional[str]]
        The underlying fetch (real ``FetcherSession`` closure in live mode,
        injected transport in offline mode). Called ONLY on a cache miss.
    raw_dir : Path
        Root of the raw HTML tree. Same ``raw_dir`` ``fetch_race_html`` uses,
        so calendar/day cache files sit alongside individual race HTMLs.

    Notes
    -----
    * A non-empty existing cache file is returned verbatim -- the transport is
      NOT consulted. This is the resume win.
    * A zero-byte or missing cache file is a miss -> transport is called. A
      ``None`` transport result is NOT cached (consistent with
      ``fetch_race_html`` zero-byte-is-missing semantics).
    * Non-cacheable URLs (individual race pages, anything not matching
      ``/race/list/{6 or 8 digits}/``) are forwarded to the transport
      untouched -- no read, no write.
    """

    def __init__(
        self,
        transport: Callable[[str], Optional[str]],
        raw_dir: Path,
    ) -> None:
        self._transport = transport
        self._raw_dir = Path(raw_dir)

    def __call__(self, url: str) -> Optional[str]:
        cache_path = _cache_path_for_url(url, self._raw_dir)
        if cache_path is None:
            # Not a list page -> defer entirely to the transport.
            return self._transport(url)

        # Cache hit: non-empty existing file. Avoid stat'ing again after read.
        if cache_path.is_file() and cache_path.stat().st_size > 0:
            return cache_path.read_text(encoding="utf-8")

        # Cache miss -> consult the transport.
        html = self._transport(url)
        if html is None:
            # Transport failure. Do NOT cache -- a future run should retry.
            return None

        # Atomic write (same discipline as fetch_race_html): temp file then
        # os.replace so an interruption cannot leave a partial cache entry.
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
        try:
            tmp_path.write_text(html, encoding="utf-8")
            os.replace(tmp_path, cache_path)
        except Exception:
            # Clean up the orphaned temp file if os.replace failed; the cache
            # simply misses next time.
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise

        return html


def make_cached_fetcher(
    transport: Callable[[str], Optional[str]],
    raw_dir: Path,
) -> Callable[[str], Optional[str]]:
    """Return a cache-wrapped callable usable as ``fetch_html``.

    Thin convenience wrapper around ``CachedFetcher`` -- lets ``run_scrape``
    hand ``enumerate_races`` a plain ``Callable`` (matching the existing
    transport contract) without exposing the wrapper class at call sites.
    """
    return CachedFetcher(transport, raw_dir)


__all__ = ["CachedFetcher", "make_cached_fetcher"]
