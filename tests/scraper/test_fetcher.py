"""Tests for ``src/scraper/fetcher``.

Covers SCRP-01 (separation), SCRP-02 (fetch + raw save), SCRP-05 (dedup),
the Cycle-1 HIGHs (browser-per-request, atomic write, anti-bot detection,
returns-path-on-failure), Cycle-1 MEDIUMs (12-digit validation, networkidle,
rate-limit-on-error, finally cleanup), **Cycle-2 HIGH #8** (module-level
``fetch_with_retry`` export contradiction regression guard), and **Cycle-3 #2**
(injected ``fetch_callable`` transport routing).

Playwright is mocked throughout via ``unittest.mock.patch`` -- NO real browser
is launched and NO network calls are made. The "valid HTML" fixture strings
are intentionally >= 500 bytes AND contain ``race_table_01`` so
``detect_block_page``'s length heuristic and result-table check do not
false-positive (Cycle-1 MEDIUM).
"""

import inspect
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.scraper.fetcher import (
    FetcherSession,
    detect_block_page,
    fetch_race_html,
    fetch_with_retry,
    make_fetch_html_callable,
)
from src.scraper.models import RaceRef

# --- Shared constants -------------------------------------------------------
#
# A "valid" HTML fixture used across dedup / path / atomic-write tests. It is
# intentionally >= 500 bytes AND contains the ``race_table_01`` marker so
# detect_block_page's length and result-table heuristics do not flag it
# (Cycle-1 MEDIUM: detect_block_page must not false-positive on valid HTML).

_VALID_HTML = (
    "<html><head><title>2022年6月15日 | test race</title></head>"
    "<body><h1>Race</h1>"
    "<table class='race_table_01'>"
    "<tr><th>着順</th><th>馬番</th><th>馬名</th></tr>"
    "<tr><td>1</td><td>01</td><td>Test Horse A</td></tr>"
    "<tr><td>2</td><td>02</td><td>Test Horse B</td></tr>"
    "<tr><td>3</td><td>03</td><td>Test Horse C</td></tr>"
    "</table>"
    + ("<!-- " + "x" * 300 + " -->")  # padding to exceed 500 bytes comfortably
    + "</body></html>"
)
assert len(_VALID_HTML) >= 500, "valid HTML fixture must be >= 500 bytes"

# A short block-page fixture (< 500 bytes).
_SHORT_HTML = "<html></html>"

# A CAPTCHA marker fixture.
_CAPTCHA_HTML = "<html><body>please complete captcha to continue</body></html>"


# --- Fixtures ---------------------------------------------------------------


@pytest.fixture
def fake_session() -> MagicMock:
    """Return a MagicMock standing in for a ``FetcherSession``.

    Its ``fetch_with_retry`` returns ``_VALID_HTML`` by default. Individual
    tests override ``return_value`` or ``side_effect`` as needed.
    """
    session = MagicMock(name="fake_session")
    session.fetch_with_retry.return_value = _VALID_HTML
    return session


@pytest.fixture
def fake_fetch_callable() -> MagicMock:
    """Return a MagicMock standing in for an injected fetch_callable transport.

    Cycle-3 #2: this is the offline-mode transport that ``fetch_race_html``
    uses when ``session is None``.
    """
    fn = MagicMock(name="fake_fetch_callable")
    fn.return_value = _VALID_HTML
    return fn


# ===========================================================================
# 1. TestDedup -- SCRP-05
# ===========================================================================


class TestDedup:
    """SCRP-05: existing non-empty files are skipped; zero-byte files re-fetch."""

    def test_skips_existing_nonempty_html(
        self, tmp_raw_dir: Path, fake_session: MagicMock
    ) -> None:
        race_id = "202201050101"
        # race_date is 2022-06-15; path is {raw}/2022/06/{race_id}.html
        # NOTE: month comes from race_date (06), NOT race_id (which starts 202201).
        out_dir = tmp_raw_dir / "2022" / "06"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{race_id}.html"
        out_path.write_text("existing content", encoding="utf-8")

        ref = RaceRef(race_id=race_id, race_date=date(2022, 6, 15))
        result = fetch_race_html(ref, session=fake_session, raw_dir=tmp_raw_dir)

        assert result == out_path
        # fetch_with_retry MUST NOT have been called (dedup short-circuit).
        fake_session.fetch_with_retry.assert_not_called()
        # Original content preserved (not overwritten).
        assert out_path.read_text(encoding="utf-8") == "existing content"

    def test_refetches_zero_byte_file(
        self, tmp_raw_dir: Path, fake_session: MagicMock
    ) -> None:
        race_id = "202201050101"
        out_dir = tmp_raw_dir / "2022" / "06"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{race_id}.html"
        # Zero-byte file -> treated as missing.
        out_path.write_bytes(b"")

        ref = RaceRef(race_id=race_id, race_date=date(2022, 6, 15))
        result = fetch_race_html(ref, session=fake_session, raw_dir=tmp_raw_dir)

        # fetch_with_retry IS called (file is zero-byte, treated as missing).
        fake_session.fetch_with_retry.assert_called_once()
        assert result == out_path
        # File now has the fetched content (atomic replace happened).
        assert out_path.stat().st_size > 0


# ===========================================================================
# 2. TestPathDerivation -- Cycle-1 HIGH #1 (application side)
# ===========================================================================


class TestPathDerivation:
    """Cycle-1 HIGH #1: path derived from race_ref.race_date, NOT race_id[4:6]."""

    def test_path_from_race_date(
        self, tmp_raw_dir: Path, fake_session: MagicMock
    ) -> None:
        # race_id starts with "202201" (would be month 01 if read from [4:6]),
        # but race_date is 2022-06-15 -> path MUST use month 06.
        race_id = "202201050101"
        ref = RaceRef(race_id=race_id, race_date=date(2022, 6, 15))

        result = fetch_race_html(ref, session=fake_session, raw_dir=tmp_raw_dir)

        expected = tmp_raw_dir / "2022" / "06" / f"{race_id}.html"
        assert result == expected
        # The month-01 path (derived from race_id[4:6]) must NOT exist.
        bad_path = tmp_raw_dir / "2022" / "01" / f"{race_id}.html"
        assert not bad_path.exists()
        # The month-06 path MUST exist (the file was written there).
        assert expected.exists()

    def test_invalid_race_id_raises(
        self, tmp_raw_dir: Path, fake_session: MagicMock
    ) -> None:
        ref = RaceRef(race_id="abc", race_date=date(2022, 1, 1))
        with pytest.raises(ValueError, match="12 digits"):
            fetch_race_html(ref, session=fake_session, raw_dir=tmp_raw_dir)
        # The transport must not have been invoked.
        fake_session.fetch_with_retry.assert_not_called()


# ===========================================================================
# 3. TestFetcherSessionLifecycle -- Cycle-1 HIGH (one browser per batch)
# ===========================================================================


class TestFetcherSessionLifecycle:
    """Cycle-1 HIGH: one Chromium launch per batch; try/finally cleanup."""

    def _wire_mock_playwright(self, mock_pw: MagicMock) -> MagicMock:
        """Set up the mock chain: sync_playwright().start().chromium.launch().

        ``sync_playwright()`` returns a context-manager-like object whose
        ``.start()`` returns the playwright instance (``self._pw`` in the
        fetcher). The instance's ``.chromium.launch()`` returns the browser.
        """
        mock_p = MagicMock()
        # sync_playwright() returns an object; .start() on it returns mock_p.
        mock_pw.return_value.start.return_value = mock_p
        mock_browser = MagicMock()
        mock_p.chromium.launch.return_value = mock_browser
        mock_context = MagicMock()
        mock_browser.new_context.return_value = mock_context
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page
        # page.content returns a valid-length string.
        mock_page.content.return_value = _VALID_HTML
        return mock_p

    def test_launches_browser_once_per_batch(self) -> None:
        """3 fetch calls inside one ``with`` -> exactly 1 chromium.launch."""
        with patch("src.scraper.fetcher.sync_playwright") as mock_pw:
            mock_p = self._wire_mock_playwright(mock_pw)

            with FetcherSession() as session:
                # Perform 3 fetch calls; all share the single browser.
                session.fetch("https://example.com/1")
                session.fetch("https://example.com/2")
                session.fetch("https://example.com/3")

            # Exactly ONE chromium.launch call across the whole batch.
            assert mock_p.chromium.launch.call_count == 1

    def test_closes_browser_on_exit(self) -> None:
        with patch("src.scraper.fetcher.sync_playwright") as mock_pw:
            mock_p = self._wire_mock_playwright(mock_pw)
            mock_browser = mock_p.chromium.launch.return_value

            with FetcherSession():
                pass

            # browser.close called during __exit__.
            mock_browser.close.assert_called_once()

    def test_closes_browser_even_on_exception(self) -> None:
        """Cycle-1 MEDIUM finally cleanup: exception in the with still closes."""
        with patch("src.scraper.fetcher.sync_playwright") as mock_pw:
            mock_p = self._wire_mock_playwright(mock_pw)
            mock_browser = mock_p.chromium.launch.return_value

            with pytest.raises(RuntimeError, match="boom"):
                with FetcherSession():
                    raise RuntimeError("boom")

            # browser.close STILL called even though an exception propagated.
            mock_browser.close.assert_called_once()


# ===========================================================================
# 4. TestRetryAndFailure -- Cycle-1 HIGH (None on terminal failure)
# ===========================================================================


class TestRetryAndFailure:
    """Cycle-1 HIGH: returns None after max retries, never a path."""

    def test_returns_none_after_max_retries(
        self, tmp_raw_dir: Path, fake_session: MagicMock
    ) -> None:
        fake_session.fetch_with_retry.return_value = None
        ref = RaceRef(race_id="202201050101", race_date=date(2022, 6, 15))

        result = fetch_race_html(ref, session=fake_session, raw_dir=tmp_raw_dir)

        # fetch_race_html returns None when the session exhausted retries.
        assert result is None
        # No file written on failure.
        assert not (tmp_raw_dir / "2022" / "06" / "202201050101.html").exists()

    def test_rate_limit_applied_on_error(self) -> None:
        """Cycle-1 MEDIUM: time.sleep called even when fetch raises."""
        with patch("src.scraper.fetcher.sync_playwright") as mock_pw, patch(
            "src.scraper.fetcher.time.sleep"
        ) as mock_sleep:
            # Wire the mock chain so __enter__ succeeds.
            mock_p = MagicMock()
            mock_pw.return_value.start.return_value = mock_p
            mock_browser = MagicMock()
            mock_p.chromium.launch.return_value = mock_browser
            mock_context = MagicMock()
            mock_browser.new_context.return_value = mock_context
            mock_page = MagicMock()
            mock_context.new_page.return_value = mock_page
            # page.goto raises -> fetch() error path.
            mock_page.goto.side_effect = Exception("network error")

            with FetcherSession() as session:
                result = session.fetch("https://example.com/timeout")

            # fetch returns None on error.
            assert result is None
            # time.sleep WAS called on the error path (rate-limit-on-error).
            # The finally block in fetch() applies the rate limit.
            assert mock_sleep.called


# ===========================================================================
# 5. TestBlockPageDetection -- Cycle-1 HIGH (anti-bot)
# ===========================================================================


class TestBlockPageDetection:
    """Cycle-1 HIGH: block/empty/anti-bot pages detected and rejected."""

    def test_detects_captcha(self) -> None:
        assert detect_block_page(_CAPTCHA_HTML) is True

    def test_detects_short_html(self) -> None:
        assert detect_block_page(_SHORT_HTML) is True

    def test_detects_missing_result_table(self) -> None:
        # >= 500 bytes but lacks race_table_01 AND 'result'.
        html = "<html><body>" + ("some nav here " * 50) + "</body></html>"
        assert len(html) >= 500
        assert "race_table_01" not in html
        assert detect_block_page(html) is True

    def test_detects_robot_marker(self) -> None:
        html = "<html><body>access denied, robot detected " + ("x" * 500) + "</body></html>"
        assert detect_block_page(html) is True

    def test_detects_access_restriction_japanese(self) -> None:
        html = "<html><body>アクセス制限 " + ("y" * 500) + "</body></html>"
        assert detect_block_page(html) is True

    def test_accepts_valid_result_html(self) -> None:
        assert detect_block_page(_VALID_HTML) is False

    def test_block_page_never_saved(
        self, tmp_raw_dir: Path, fake_session: MagicMock
    ) -> None:
        fake_session.fetch_with_retry.return_value = _CAPTCHA_HTML
        ref = RaceRef(race_id="202201050101", race_date=date(2022, 6, 15))

        result = fetch_race_html(ref, session=fake_session, raw_dir=tmp_raw_dir)

        # Returns None when a block page is detected.
        assert result is None
        # NO file exists at the target path (block page never saved).
        out_path = tmp_raw_dir / "2022" / "06" / "202201050101.html"
        assert not out_path.exists()
        # No temp file left behind either.
        assert not out_path.with_suffix(".html.tmp").exists()


# ===========================================================================
# 6. TestAtomicWrite -- Cycle-1 HIGH (temp + os.replace)
# ===========================================================================


class TestAtomicWrite:
    """Cycle-1 HIGH: atomic write leaves only the final .html, no .tmp."""

    def test_no_tmp_file_remains(
        self, tmp_raw_dir: Path, fake_session: MagicMock
    ) -> None:
        ref = RaceRef(race_id="202201050101", race_date=date(2022, 6, 15))
        result = fetch_race_html(ref, session=fake_session, raw_dir=tmp_raw_dir)

        out_path = tmp_raw_dir / "2022" / "06" / "202201050101.html"
        assert result == out_path
        assert out_path.exists()
        # The .html.tmp file MUST NOT remain after a successful atomic write.
        assert not out_path.with_suffix(".html.tmp").exists()
        # The content is the fetched HTML.
        assert out_path.read_text(encoding="utf-8") == _VALID_HTML


# ===========================================================================
# 7. TestModuleLevelFetchWithRetry -- Cycle-2 HIGH #8
# ===========================================================================


class TestModuleLevelFetchWithRetry:
    """Cycle-2 HIGH #8: module-level ``fetch_with_retry`` wrapper regression guard.

    The plan's verify block imports ``fetch_with_retry`` at module level. The
    Cycle-1 revision only defined it as a ``FetcherSession`` method, so the
    import would have raised ``ImportError``. These tests guard against that
    regression.
    """

    def test_module_level_import_succeeds(self) -> None:
        """The exact verify import must succeed and yield a callable."""
        # Imported at module top, but re-import here to mirror the verify
        # command literally.
        from src.scraper.fetcher import fetch_with_retry as imported

        assert inspect.isfunction(imported), (
            "module-level fetch_with_retry must be a function (Cycle-2 #8), "
            f"got {type(imported)}"
        )
        assert callable(imported)

    def test_method_also_exists(self) -> None:
        """The FetcherSession.fetch_with_retry method must also exist."""
        assert hasattr(FetcherSession, "fetch_with_retry")
        method = getattr(FetcherSession, "fetch_with_retry")
        assert callable(method)

    def test_module_level_wrapper_delegates_to_method(self) -> None:
        """Wrapper constructs a transient session and calls the method once."""
        url = "https://db.netkeiba.com/race/202201050101/"
        with patch("src.scraper.fetcher.FetcherSession") as MockSession:
            mock_instance = MagicMock()
            MockSession.return_value.__enter__.return_value = mock_instance
            mock_instance.fetch_with_retry.return_value = _VALID_HTML

            result = fetch_with_retry(url)

            # The wrapper delegated to the session's fetch_with_retry method.
            mock_instance.fetch_with_retry.assert_called_once()
            called_args = mock_instance.fetch_with_retry.call_args
            assert called_args.args == (url,)
            # Returns the same HTML the method returned.
            assert result == _VALID_HTML

    def test_wrapper_returns_none_on_terminal_failure(self) -> None:
        """Wrapper shares the method's None-on-failure contract."""
        url = "https://db.netkeiba.com/race/202201050101/"
        with patch("src.scraper.fetcher.FetcherSession") as MockSession:
            mock_instance = MagicMock()
            MockSession.return_value.__enter__.return_value = mock_instance
            mock_instance.fetch_with_retry.return_value = None

            result = fetch_with_retry(url)

            assert result is None

    def test_wrapper_docstring_contains_loop_warning(self) -> None:
        """Cycle-2 #8 / T-04-09b: docstring warns against loop usage."""
        assert fetch_with_retry.__doc__ is not None
        doc = fetch_with_retry.__doc__
        # The warning must mention NOT calling in a loop + shared session.
        assert "loop" in doc.lower(), (
            "module-level fetch_with_retry docstring must warn against loop usage"
        )
        assert "FetcherSession.fetch_with_retry" in doc, (
            "docstring must point readers to the shared-session method"
        )


# ===========================================================================
# 8. TestCycle3FetchCallable -- Cycle-3 #2 (offline race-fetch path)
# ===========================================================================


class TestCycle3FetchCallable:
    """Cycle-3 #2: ``fetch_callable`` param routes injected transport to races.

    When ``session is None`` and ``fetch_callable`` is provided, the callable
    fetches the HTML instead of dereferencing a None session. When BOTH are
    None, a loud ``ValueError`` is raised (not ``AttributeError``).
    """

    def test_uses_fetch_callable_when_session_none(
        self, tmp_raw_dir: Path, fake_fetch_callable: MagicMock
    ) -> None:
        ref = RaceRef(race_id="202201050101", race_date=date(2022, 6, 15))

        result = fetch_race_html(
            ref,
            session=None,
            raw_dir=tmp_raw_dir,
            fetch_callable=fake_fetch_callable,
        )

        # The callable was used, not a session.
        fake_fetch_callable.assert_called_once()
        called_url = fake_fetch_callable.call_args.args[0]
        assert called_url == "https://db.netkeiba.com/race/202201050101/"
        out_path = tmp_raw_dir / "2022" / "06" / "202201050101.html"
        assert result == out_path
        assert out_path.exists()

    def test_session_takes_precedence_when_both_provided(
        self, tmp_raw_dir: Path, fake_session: MagicMock, fake_fetch_callable: MagicMock
    ) -> None:
        """When both are provided, fetch_callable wins (offline routing)."""
        ref = RaceRef(race_id="202201050101", race_date=date(2022, 6, 15))

        fetch_race_html(
            ref,
            session=fake_session,
            raw_dir=tmp_raw_dir,
            fetch_callable=fake_fetch_callable,
        )

        # fetch_callable is consulted (offline-mode routing wins per the
        # implementation's `if fetch_callable is not None` first branch).
        fake_fetch_callable.assert_called_once()
        # The session is NOT consulted when fetch_callable is provided.
        fake_session.fetch_with_retry.assert_not_called()

    def test_raises_when_both_none(self, tmp_raw_dir: Path) -> None:
        ref = RaceRef(race_id="202201050101", race_date=date(2022, 6, 15))
        with pytest.raises(ValueError, match="session or a fetch_callable"):
            fetch_race_html(ref, session=None, raw_dir=tmp_raw_dir, fetch_callable=None)

    def test_fetch_callable_returning_none_handled_gracefully(
        self, tmp_raw_dir: Path, fake_fetch_callable: MagicMock
    ) -> None:
        fake_fetch_callable.return_value = None
        ref = RaceRef(race_id="202201050101", race_date=date(2022, 6, 15))

        result = fetch_race_html(
            ref,
            session=None,
            raw_dir=tmp_raw_dir,
            fetch_callable=fake_fetch_callable,
        )

        # Returns None gracefully (NOT an AttributeError on None session).
        assert result is None
        out_path = tmp_raw_dir / "2022" / "06" / "202201050101.html"
        assert not out_path.exists()

    def test_dedup_short_circuits_before_fetch_callable(
        self, tmp_raw_dir: Path, fake_fetch_callable: MagicMock
    ) -> None:
        """SCRP-05 dedup runs BEFORE either transport is consulted."""
        race_id = "202201050101"
        out_dir = tmp_raw_dir / "2022" / "06"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{race_id}.html"
        out_path.write_text("preexisting", encoding="utf-8")

        ref = RaceRef(race_id=race_id, race_date=date(2022, 6, 15))
        result = fetch_race_html(
            ref,
            session=None,
            raw_dir=tmp_raw_dir,
            fetch_callable=fake_fetch_callable,
        )

        assert result == out_path
        # Dedup short-circuited: the callable was NOT called.
        fake_fetch_callable.assert_not_called()


# ===========================================================================
# 9. TestMakeFetchHtmlCallable -- shared-session closure
# ===========================================================================


class TestMakeFetchHtmlCallable:
    """The closure lets enumeration reuse the fetcher's session."""

    def test_closure_delegates_to_session(self) -> None:
        session = MagicMock()
        session.fetch_with_retry.return_value = _VALID_HTML

        closure = make_fetch_html_callable(session)
        url = "https://db.netkeiba.com/race/list/20220615/"
        result = closure(url)

        session.fetch_with_retry.assert_called_once_with(url)
        assert result == _VALID_HTML

    def test_closure_is_callable(self) -> None:
        session = MagicMock()
        closure = make_fetch_html_callable(session)
        assert callable(closure)
