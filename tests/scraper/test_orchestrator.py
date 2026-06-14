"""Unit tests for ``src.scraper.orchestrator.run_scrape``.

All sub-steps are mocked so these tests verify ONLY the orchestrator's wiring:
  * Cycle-1 MEDIUM: ``live=False`` without ``fetch_html`` raises ``ValueError``
    (the ``live`` parameter is no longer dead).
  * Cycle-2 #5: ``live=False`` WITH injected ``fetch_html`` runs offline (no
    real browser, no real network).
  * One ``FetcherSession`` is opened per live run.
  * A race whose ``fetch_race_html`` returns ``None`` is skipped, others proceed.

The REAL full-chain e2e (REAL enumerate -> REAL parse -> REAL normalize with
only the network boundary mocked) lives in ``tests/scraper/test_end_to_end.py``
(Cycle-2 HIGH #5). These orchestrator unit tests are intentionally fully
mocked to verify wiring without depending on the parser / normalizer behavior.
"""

import datetime
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from src.scraper.models import RaceRef
from src.scraper.orchestrator import run_scrape

# Repo-relative golden fixture path used by the mocked fetch_race_html to
# return a real Path (parse_race_html is mocked here too, so the file content
# is not actually consumed -- but a real path makes the mock realistic).
_FIXTURES = Path(__file__).parent / "fixtures" / "html"


@pytest.fixture
def two_race_refs() -> list[RaceRef]:
    """Two RaceRefs spanning distinct fixture race_ids."""
    return [
        RaceRef(race_id="202206050509", race_date=datetime.date(2022, 12, 17)),
        RaceRef(race_id="202309030811", race_date=datetime.date(2023, 6, 25)),
    ]


class TestRunScrape:
    """Orchestrator wiring tests with all sub-steps mocked."""

    def test_processes_racerefs_end_to_end_mocked(
        self, two_race_refs: list[RaceRef], tmp_standard_dir: Path
    ) -> None:
        """A normal run: 2 RaceRefs -> 2 parsed dicts -> normalize_to_parquet called once."""
        with (
            patch("src.scraper.orchestrator.FetcherSession") as mock_session_cls,
            patch("src.scraper.orchestrator.enumerate_races") as mock_enum,
            patch("src.scraper.orchestrator.fetch_race_html") as mock_fetch,
            patch("src.scraper.orchestrator.parse_race_html") as mock_parse,
            patch("src.scraper.orchestrator.normalize_to_parquet") as mock_norm,
        ):
            mock_session = MagicMock()
            mock_session.__enter__.return_value = mock_session
            mock_session_cls.return_value = mock_session
            mock_enum.return_value = two_race_refs
            mock_fetch.side_effect = [
                _FIXTURES / "202206050509.html",
                _FIXTURES / "202309030811.html",
            ]
            mock_parse.side_effect = [
                {"race": {"race_id": "202206050509"}, "entries": [], "results": []},
                {"race": {"race_id": "202309030811"}, "entries": [], "results": []},
            ]
            expected = {"race": [Path("a.parquet")], "entry": [], "result": []}
            mock_norm.return_value = expected

            result = run_scrape(
                start_date=datetime.date(2022, 12, 17),
                end_date=datetime.date(2023, 6, 25),
                standard_dir=tmp_standard_dir,
                live=True,
                progress=False,
            )

            assert result == expected
            # enumerate_races was called once with the shared session transport.
            mock_enum.assert_called_once()
            _args, kwargs = mock_enum.call_args
            # The third positional arg or the fetch_html kwarg is the transport.
            # In live mode, make_fetch_html_callable(session) builds the transport.
            assert mock_session_cls.call_count == 1
            # fetch_race_html called once per RaceRef (live mode: session passed).
            assert mock_fetch.call_count == 2
            for call in mock_fetch.call_args_list:
                # live path: session=<MagicMock>, fetch_callable=None
                assert "session" in call.kwargs
                assert call.kwargs.get("fetch_callable") is None
            # parse_race_html called once per fetched path.
            assert mock_parse.call_count == 2
            # normalize_to_parquet called ONCE with a list of 2 parsed dicts.
            mock_norm.assert_called_once()
            norm_args = mock_norm.call_args
            passed_list = norm_args.args[0] if norm_args.args else norm_args.kwargs["parsed_races"]
            assert len(passed_list) == 2

    def test_skips_failed_fetch(self, two_race_refs: list[RaceRef]) -> None:
        """fetch_race_html returning None for the first race -> it is skipped, others proceed."""
        with (
            patch("src.scraper.orchestrator.FetcherSession") as mock_session_cls,
            patch("src.scraper.orchestrator.enumerate_races") as mock_enum,
            patch("src.scraper.orchestrator.fetch_race_html") as mock_fetch,
            patch("src.scraper.orchestrator.parse_race_html") as mock_parse,
            patch("src.scraper.orchestrator.normalize_to_parquet") as mock_norm,
        ):
            mock_session = MagicMock()
            mock_session.__enter__.return_value = mock_session
            mock_session_cls.return_value = mock_session
            mock_enum.return_value = two_race_refs
            # First fetch returns None (skip), second returns a real path.
            mock_fetch.side_effect = [
                None,
                _FIXTURES / "202309030811.html",
            ]
            mock_parse.return_value = {
                "race": {"race_id": "202309030811"},
                "entries": [],
                "results": [],
            }
            mock_norm.return_value = {"race": [], "entry": [], "result": []}

            run_scrape(
                start_date=datetime.date(2022, 12, 17),
                end_date=datetime.date(2023, 6, 25),
                live=True,
                progress=False,
            )

            # Only the second race reaches parse + normalize.
            assert mock_parse.call_count == 1
            mock_norm.assert_called_once()
            norm_args = mock_norm.call_args
            passed_list = norm_args.args[0] if norm_args.args else norm_args.kwargs["parsed_races"]
            assert len(passed_list) == 1

    def test_single_session_per_run(self, two_race_refs: list[RaceRef]) -> None:
        """Live mode opens exactly ONE FetcherSession (Cycle-1 HIGH browser-per-request)."""
        with (
            patch("src.scraper.orchestrator.FetcherSession") as mock_session_cls,
            patch("src.scraper.orchestrator.enumerate_races") as mock_enum,
            patch("src.scraper.orchestrator.fetch_race_html") as mock_fetch,
            patch("src.scraper.orchestrator.parse_race_html"),
            patch("src.scraper.orchestrator.normalize_to_parquet"),
        ):
            mock_session = MagicMock()
            mock_session.__enter__.return_value = mock_session
            mock_session_cls.return_value = mock_session
            mock_enum.return_value = two_race_refs
            mock_fetch.return_value = _FIXTURES / "202206050509.html"

            run_scrape(
                start_date=datetime.date(2022, 12, 17),
                end_date=datetime.date(2023, 6, 25),
                live=True,
                progress=False,
            )

            # Exactly ONE FetcherSession context-manager open (the with block).
            assert mock_session_cls.call_count == 1

    def test_live_false_without_fetch_html_raises(self) -> None:
        """Cycle-1 MEDIUM: live=False without fetch_html raises ValueError (live not dead)."""
        with pytest.raises(ValueError, match="fetch_html"):
            run_scrape(
                start_date=datetime.date(2022, 1, 1),
                end_date=datetime.date(2022, 1, 5),
                live=False,
                fetch_html=None,
                progress=False,
            )

    def test_live_false_with_injected_fetch_html_runs_offline(
        self, two_race_refs: list[RaceRef]
    ) -> None:
        """Cycle-2 #5: live=False WITH injected fetch_html runs offline (no real browser)."""
        captured_transport: dict[str, object] = {}

        def _stub_transport(url: str) -> Optional[str]:
            # In offline mode this transport is what enumerate_races AND
            # fetch_race_html use. Return minimal HTML.
            return "<html><body>stub</body></html>"

        with (
            patch("src.scraper.orchestrator.FetcherSession") as mock_session_cls,
            patch("src.scraper.orchestrator.enumerate_races") as mock_enum,
            patch("src.scraper.orchestrator.fetch_race_html") as mock_fetch,
            patch("src.scraper.orchestrator.parse_race_html"),
            patch("src.scraper.orchestrator.normalize_to_parquet"),
        ):
            mock_enum.return_value = two_race_refs
            mock_fetch.return_value = _FIXTURES / "202206050509.html"

            # Capture the transport enumerate_races was called with.
            # **kwargs absorbs the progress kwarg run_scrape now threads
            # through to enumerate_races (quick-task 260614-mfq).
            def _capture_transport(start, end, transport, **kwargs):
                captured_transport["transport"] = transport
                return two_race_refs

            mock_enum.side_effect = _capture_transport

            run_scrape(
                start_date=datetime.date(2022, 12, 17),
                end_date=datetime.date(2023, 6, 25),
                live=False,
                fetch_html=_stub_transport,
                progress=False,
            )

            # FetcherSession was NEVER entered in offline mode (no real browser).
            mock_session_cls.assert_not_called()
            # enumerate_races was called with the injected transport (not a
            # make_fetch_html_callable wrapper).
            assert captured_transport["transport"] is _stub_transport
            # fetch_race_html was called with fetch_callable=transport
            # (Cycle-3 #2 offline race-fetch routing).
            assert mock_fetch.call_count == len(two_race_refs)
            for call in mock_fetch.call_args_list:
                assert call.kwargs.get("session") is None
                assert call.kwargs.get("fetch_callable") is _stub_transport

    def test_progress_flag_is_output_neutral(
        self, two_race_refs: list[RaceRef], tmp_standard_dir: Path
    ) -> None:
        """progress=True vs progress=False must produce the SAME parsed list reaching
        normalize_to_parquet (tqdm is a display-only layer; it does not change data)."""

        def _run_and_capture(progress: bool) -> int:
            with (
                patch("src.scraper.orchestrator.FetcherSession") as mock_session_cls,
                patch("src.scraper.orchestrator.enumerate_races") as mock_enum,
                patch("src.scraper.orchestrator.fetch_race_html") as mock_fetch,
                patch("src.scraper.orchestrator.parse_race_html") as mock_parse,
                patch("src.scraper.orchestrator.normalize_to_parquet") as mock_norm,
            ):
                mock_session = MagicMock()
                mock_session.__enter__.return_value = mock_session
                mock_session_cls.return_value = mock_session
                mock_enum.return_value = two_race_refs
                mock_fetch.side_effect = [
                    _FIXTURES / "202206050509.html",
                    _FIXTURES / "202309030811.html",
                ]
                mock_parse.side_effect = [
                    {"race": {"race_id": "202206050509"}, "entries": [], "results": []},
                    {"race": {"race_id": "202309030811"}, "entries": [], "results": []},
                ]
                mock_norm.return_value = {"race": [], "entry": [], "result": []}

                run_scrape(
                    start_date=datetime.date(2022, 12, 17),
                    end_date=datetime.date(2023, 6, 25),
                    standard_dir=tmp_standard_dir,
                    live=True,
                    progress=progress,
                )

                mock_norm.assert_called_once()
                norm_args = mock_norm.call_args
                passed_list = (
                    norm_args.args[0] if norm_args.args else norm_args.kwargs["parsed_races"]
                )
                return len(passed_list)

        assert _run_and_capture(True) == _run_and_capture(False) == len(two_race_refs)
