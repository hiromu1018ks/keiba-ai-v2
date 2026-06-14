"""Playwright-based HTML fetcher for netkeiba race pages.

Implements D-02 (Playwright fetcher), D-06 (raw dir ``data/raw/netkeiba/{YYYY}/{MM}/``),
D-07 (filename ``{race_id}.html``), D-08 (dedup by race_id), SCRP-02 (fetch + raw
save), and SCRP-05 (dedup: skip non-empty existing files).

Key design invariants (all guarded by tests in ``tests/scraper/test_fetcher.py``):

1. **Cycle-1 HIGH (browser-per-request)** -- ``FetcherSession`` is a context
   manager that launches ONE Chromium browser per BATCH and reuses it across
   every fetch. The browser is closed in ``__exit__`` via try/finally so a crash
   mid-batch still releases the process.
2. **Cycle-1 HIGH #1 (race_date path source)** -- ``fetch_race_html`` accepts a
   ``RaceRef`` and derives ``{YYYY}/{MM}`` from ``race_ref.race_date``, NEVER
   from ``race_ref.race_id[4:6]`` (which is the JRA course code, not a month).
3. **Cycle-1 HIGH (atomic write)** -- HTML is written to a temp file first,
   then ``os.replace``'d to the final path. Interruption cannot leave a
   non-empty partial file that a future run treats as valid.
4. **Cycle-1 HIGH (anti-bot detection)** -- ``detect_block_page`` rejects short
   HTML, CAPTCHA/robot/403 markers, and pages lacking ``race_table_01``. A block
   page is treated as a fetch failure (``None`` returned), never silently saved.
5. **Cycle-1 HIGH (returns-path-on-failure)** -- on terminal failure after
   retries, ``fetch_with_retry`` returns ``None``; ``fetch_race_html`` returns
   ``None``. Neither ever returns a path to a missing/partial file.
6. **Cycle-1 MEDIUM (rate-limit on error)** -- ``FetcherSession.fetch`` applies
   ``time.sleep(rate_limit_seconds)`` on BOTH success and error paths so a
   server error does not trigger unthrottled retries.
7. **Cycle-1 MEDIUM (networkidle unreliable)** -- the default ``wait_until`` is
   ``"domcontentloaded"`` (NOT ``"networkidle"``).
8. **Cycle-1 MEDIUM (12-digit validation)** -- ``race_id`` is validated with
   ``re.fullmatch(r"\\d{12}", race_id)`` and a mismatch raises ``ValueError``.
9. **Cycle-2 HIGH #8 (export contradiction)** -- both a
   ``FetcherSession.fetch_with_retry`` METHOD (used by the batch orchestrator,
   Plan 06) AND a module-level ``fetch_with_retry`` FUNCTION (used by one-off
   CLI/smoke callers) exist. The module-level wrapper constructs a transient
   ``FetcherSession`` and delegates.
10. **Cycle-3 #2 (offline race-fetch path)** -- ``fetch_race_html`` accepts an
    OPTIONAL ``fetch_callable`` param. When ``session is None`` and
    ``fetch_callable`` is provided, the callable is used instead of
    ``session.fetch_with_retry``. When BOTH are ``None`` a loud ``ValueError``
    is raised (not an ``AttributeError`` on a ``None`` session).
"""

import os
import re
import time
from pathlib import Path
from typing import Callable, Optional

from loguru import logger
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from src.scraper.models import RaceRef

# --- Module constants -------------------------------------------------------

MAX_RETRIES = 3
RATE_LIMIT_SECONDS = 2.0

# Validation regex for race_id. Used with re.fullmatch so any non-12-digit
# value (shorter, longer, or non-numeric) is rejected.
_RACE_ID_RE = re.compile(r"\d{12}")


# --- FetcherSession ---------------------------------------------------------


class FetcherSession:
    """Context manager that owns ONE Chromium browser per batch.

    Reusing a single browser/context/page across every fetch in the batch fixes
    the Codex Review Cycle-1 HIGH (browser-per-request overhead). Cleanup is in
    ``__exit__`` via nested try/finally so a crash mid-batch still closes the
    browser process (Cycle-1 MEDIUM finally cleanup).

    Parameters
    ----------
    headless : bool
        Forwarded to ``p.chromium.launch``. Default True (no GUI).
    rate_limit_seconds : float
        Minimum delay between requests. Applied on BOTH success and error paths
        so a server error does not trigger unthrottled retries (Cycle-1 MEDIUM).
    navigation_timeout_ms : int
        Per-navigation timeout forwarded to ``page.goto(timeout=...)``.
    wait_until : str
        ``page.goto(wait_until=...)``. Default ``"domcontentloaded"`` -- NOT
        ``"networkidle"`` which is unreliable on pages with persistent requests
        (Cycle-1 MEDIUM).
    """

    def __init__(
        self,
        headless: bool = True,
        rate_limit_seconds: float = RATE_LIMIT_SECONDS,
        navigation_timeout_ms: int = 30000,
        wait_until: str = "domcontentloaded",
    ) -> None:
        self._headless = headless
        self.rate_limit_seconds = rate_limit_seconds
        self.navigation_timeout_ms = navigation_timeout_ms
        self.wait_until = wait_until
        # Resources populated in __enter__.
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None

    # -- context-manager protocol -------------------------------------------

    def __enter__(self) -> "FetcherSession":
        # Launch ONE Playwright / browser / context / page for the whole batch.
        # Cycle-1 HIGH: this MUST happen here, not per-request.
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self._headless)
        self._context = self._browser.new_context()
        self._page = self._context.new_page()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # Cycle-1 MEDIUM finally cleanup: close page/context/browser and stop
        # playwright even if an exception propagated out of the with block.
        try:
            if self._page is not None:
                try:
                    self._page.close()
                except Exception:
                    pass
            if self._context is not None:
                try:
                    self._context.close()
                except Exception:
                    pass
            if self._browser is not None:
                try:
                    self._browser.close()
                except Exception:
                    pass
        finally:
            if self._pw is not None:
                try:
                    self._pw.stop()
                except Exception:
                    pass
            # Drop references so a second __enter__ would be required.
            self._page = None
            self._context = None
            self._browser = None
            self._pw = None

    # -- fetch primitives ---------------------------------------------------

    @property
    def page(self):
        """The reusable Page object. Raises if used outside a ``with`` block."""
        if self._page is None:
            raise RuntimeError(
                "FetcherSession.page accessed outside of a 'with' block "
                "(browser not launched). Use FetcherSession as a context manager."
            )
        return self._page

    def fetch(self, url: str) -> Optional[str]:
        """Navigate to ``url`` once and return the HTML, or ``None`` on failure.

        Applies ``time.sleep(self.rate_limit_seconds)`` on BOTH success and
        error paths (Cycle-1 MEDIUM rate-limit-on-error): a server error must
        not trigger an unthrottled retry loop.
        """
        try:
            self.page.goto(
                url,
                wait_until=self.wait_until,
                timeout=self.navigation_timeout_ms,
            )
            html = self.page.content()
            return html
        except PlaywrightTimeout as exc:
            logger.warning(f"PlaywrightTimeout fetching {url}: {exc}")
            return None
        except Exception as exc:  # noqa: BLE001 -- any navigation error is a fetch failure
            logger.warning(f"Error fetching {url}: {exc}")
            return None
        finally:
            # Cycle-1 MEDIUM: rate-limit applies on BOTH success and error
            # paths. finally guarantees it runs regardless of which branch
            # returned.
            time.sleep(self.rate_limit_seconds)

    def fetch_with_retry(
        self, url: str, retries: int = MAX_RETRIES
    ) -> Optional[str]:
        """Retry ``self.fetch`` up to ``retries`` times with exponential backoff.

        Returns the HTML string on success, or ``None`` after exhausting retries
        (Cycle-1 HIGH -- do NOT return a path or partial result on failure).
        """
        html: Optional[str] = None
        for attempt in range(retries):
            html = self.fetch(url)
            if html is not None:
                return html
            # Exponential backoff: base RATE_LIMIT_SECONDS * (attempt + 2).
            # attempt 0 -> 2*base, attempt 1 -> 3*base, attempt 2 -> 4*base.
            backoff = RATE_LIMIT_SECONDS * (attempt + 2)
            logger.info(
                f"fetch attempt {attempt + 1}/{retries} failed for {url}; "
                f"backing off {backoff}s"
            )
            # Only sleep between attempts, not after the final failure (fetch()
            # already rate-limited each call).
            if attempt < retries - 1:
                time.sleep(backoff)
        logger.error(f"Exhausted {retries} retries for {url}; returning None")
        return None


# --- Block-page detection ---------------------------------------------------


def detect_block_page(html: str) -> bool:
    """Return True if ``html`` looks like an anti-bot / CAPTCHA / empty page.

    Detection heuristics (any one triggers True):

    - HTML length < 500 bytes (empty / truncated response).
    - Presence of substrings ``アクセス制限``, ``robot``, ``captcha``,
      ``403 Forbidden``.
    - Absence of any result-table indicator (``race_table_01`` not in html AND
      ``result`` not in ``html.lower()``).

    Used by ``fetch_race_html`` to reject block pages as fetch failures rather
    than silently saving junk HTML that a later parse step would have to handle.
    """
    if html is None:
        return True
    if len(html) < 500:
        return True
    lower = html.lower()
    for marker in ("アクセス制限", "robot", "captcha", "403 forbidden"):
        if marker in lower:
            return True
    if "race_table_01" not in html and "result" not in lower:
        return True
    return False


# --- fetch_race_html --------------------------------------------------------


def fetch_race_html(
    race_ref: RaceRef,
    session: Optional[FetcherSession] = None,
    raw_dir: Path = Path("data/raw/netkeiba"),
    fetch_callable: Optional[Callable[[str], Optional[str]]] = None,
) -> Optional[Path]:
    """Fetch one race's HTML and save it atomically under ``raw_dir``.

    Parameters
    ----------
    race_ref : RaceRef
        Cycle-1 HIGH #1 -- ``race_date`` is the source of truth for the
        ``{YYYY}/{MM}`` path; ``race_id[4:6]`` is NEVER used.
    session : Optional[FetcherSession]
        Live-mode default transport. When provided (and ``fetch_callable`` is
        None), ``session.fetch_with_retry(url)`` fetches the HTML. Optional per
        Cycle-3 #2.
    raw_dir : Path
        Root of the raw netkeiba tree (default ``data/raw/netkeiba``).
    fetch_callable : Optional[Callable[[str], Optional[str]]]
        Cycle-3 #2 -- injected transport used when ``session`` is None. Lets
        ``run_scrape(live=False, fetch_html=transport)`` route the transport to
        race fetching so a race NOT pre-saved is fetched via the transport (and
        a transport returning None is handled gracefully) rather than crashing
        with ``AttributeError`` on a None session.

    Returns
    -------
    Optional[Path]
        The final ``out_path`` on success, or ``None`` on fetch failure / block
        page. NEVER a path to a missing or partial file (Cycle-1 HIGH).

    Raises
    ------
    ValueError
        If ``race_ref.race_id`` is not exactly 12 digits, or if BOTH
        ``session`` and ``fetch_callable`` are None.
    """
    # Cycle-1 MEDIUM: strict 12-digit validation. Fail loud, do not proceed.
    if not _RACE_ID_RE.fullmatch(race_ref.race_id):
        raise ValueError(
            f"race_ref.race_id must be exactly 12 digits; got {race_ref.race_id!r}"
        )

    # Cycle-1 HIGH #1: derive {YYYY}/{MM} from race_ref.race_date, NEVER from
    # race_ref.race_id[4:6] (which is the JRA course code YYYYPPCCDDRR).
    year = f"{race_ref.race_date.year:04d}"
    month = f"{race_ref.race_date.month:02d}"
    out_dir = Path(raw_dir) / year / month
    out_path = out_dir / f"{race_ref.race_id}.html"

    # SCRP-05 dedup: skip non-empty existing files. Zero-byte files are
    # treated as missing and re-fetched.
    if out_path.exists() and out_path.stat().st_size > 0:
        logger.info(f"Skipping existing {race_ref.race_id} at {out_path}")
        return out_path

    url = f"https://db.netkeiba.com/race/{race_ref.race_id}/"

    # Cycle-3 #2: choose the transport. fetch_callable wins (offline mode);
    # session is the live-mode default; both-None is a loud ValueError (not
    # AttributeError on None.fetch_with_retry).
    if fetch_callable is not None:
        html = fetch_callable(url)
    elif session is not None:
        html = session.fetch_with_retry(url)
    else:
        raise ValueError(
            "fetch_race_html requires either a session or a fetch_callable "
            "(both are None)"
        )

    if html is None:
        logger.error(f"Fetch returned None for {race_ref.race_id}")
        return None

    if detect_block_page(html):
        logger.warning(
            f"Block/empty page detected for {race_ref.race_id}; not saving"
        )
        return None

    # Cycle-1 HIGH atomic write: temp file -> content already validated ->
    # os.replace rename. Interruption cannot leave a non-empty partial file at
    # out_path (the .tmp may be orphaned, but dedup ignores .tmp).
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(".html.tmp")
    try:
        tmp_path.write_text(html, encoding="utf-8")
        os.replace(tmp_path, out_path)
    except Exception:
        # Clean up the orphaned temp file if os.replace failed.
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise

    logger.info(f"Saved {race_ref.race_id} -> {out_path}")
    return out_path


# --- Module-level fetch_with_retry wrapper (Cycle-2 HIGH #8) -----------------


def fetch_with_retry(
    url: str, retries: int = MAX_RETRIES, headless: bool = True
) -> Optional[str]:
    """Thin convenience wrapper for one-off / CLI / smoke callers.

    Constructs a transient ``FetcherSession``, delegates to its
    ``fetch_with_retry`` method, and closes the browser. Returns the HTML
    string on success or ``None`` on terminal failure (same contract as the
    method).

    Do NOT call this in a loop over many URLs -- use
    ``FetcherSession.fetch_with_retry`` on a single shared session instead.
    Calling this wrapper in a hot loop would regress the Cycle-1 HIGH
    browser-per-request fix: every call launches and tears down its own
    Chromium process.
    """
    with FetcherSession(headless=headless) as session:
        return session.fetch_with_retry(url, retries=retries)


# --- make_fetch_html_callable -----------------------------------------------


def make_fetch_html_callable(
    session: FetcherSession,
) -> Callable[[str], Optional[str]]:
    """Return a closure that delegates to ``session.fetch_with_retry``.

    Lets the enumeration layer (Plan 02) use the SAME session the fetcher owns
    without taking ownership of the browser lifecycle (T-04-04: enumeration
    never launches a browser).
    """
    return lambda url: session.fetch_with_retry(url)
