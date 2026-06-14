"""Pipeline orchestrator: wire enumerate -> fetch -> parse -> normalize.

``run_scrape`` is the single public entry point that connects every stage of
the scraping pipeline:

  1. ``enumerate_races`` (Plan 02) walks the netkeiba calendar over a date range.
  2. ``fetch_race_html`` (Plan 03) saves each race's raw HTML under
     ``data/raw/netkeiba/{YYYY}/{MM}/{race_id}.html``.
  3. ``parse_race_html`` (Plan 04) turns each raw HTML file into a dict.
  4. ``normalize_to_parquet`` (Plan 05) writes strict-typed, date-partitioned
     Parquet under ``{standard_dir}/scraped/{YYYYMM}/``.

Load-bearing design decisions (all guarded by ``tests/scraper/test_orchestrator.py``
and ``tests/scraper/test_end_to_end.py``):

1. **Cycle-2 #5 (injectable fetch boundary)** -- ``run_scrape`` accepts an
   optional ``fetch_html: Callable[[str], Optional[str]]``. When provided,
   the injected callable is used BOTH by ``enumerate_races`` AND (in offline
   mode) by ``fetch_race_html`` as the transport, so the Cycle-2 #5 full-chain
   e2e test can drive the REAL pipeline with ONLY the network boundary mocked
   (no monkeypatching of Playwright internals, no real browser, no real
   network). This is what lets ``tests/scraper/test_end_to_end.py`` exercise
   REAL ``enumerate_races`` -> REAL ``parse_race_html`` -> REAL
   ``normalize_to_parquet`` end-to-end against saved golden HTML.
2. **Cycle-1 MEDIUM (live is not dead)** -- in the Cycle-1 plan,
   ``live=False`` was the DEFAULT but still permitted network access (the
   branch fell through to a real ``FetcherSession``), making it a dead
   parameter. Now ``run_scrape(live=False)`` WITHOUT an injected
   ``fetch_html`` RAISES ``ValueError``: network access is forbidden in this
   mode. There are exactly two valid modes:

       * ``live=True``                       -> real browser, real network
       * ``live=False, fetch_html=transport`` -> offline, transport-backed

3. **Cycle-3 #2 (offline race-fetch routing)** -- in the offline injected
   mode, ``fetch_race_html`` is called with ``fetch_callable=transport`` so a
   race NOT already pre-saved under ``raw_dir`` is fetched via the transport.
   A race for which the transport returns ``None`` is skipped/quarantined
   (logged, dropped, others proceed) rather than crashing with
   ``AttributeError: 'NoneType' object has no attribute 'fetch_with_retry'``
   -- the exact crash Codex flagged as HIGH #2.
4. **One FetcherSession per live run** (Cycle-1 HIGH browser-per-request) --
   live mode opens exactly one ``FetcherSession`` for the whole batch and
   shares it across both enumeration and race fetching.
"""

import datetime
from pathlib import Path
from typing import Callable, Optional

from loguru import logger

from src.scraper.enumeration import enumerate_races
from src.scraper.fetcher import FetcherSession, fetch_race_html, make_fetch_html_callable
from src.scraper.models import RaceRef
from src.scraper.normalizer import normalize_to_parquet
from src.scraper.parser import parse_race_html

DEFAULT_RAW_DIR = Path("data/raw/netkeiba")
DEFAULT_STANDARD_DIR = Path("data/standard")


def run_scrape(
    start_date: datetime.date,
    end_date: datetime.date,
    raw_dir: Path = DEFAULT_RAW_DIR,
    standard_dir: Path = DEFAULT_STANDARD_DIR,
    live: bool = False,
    max_races: Optional[int] = None,
    fetch_html: Optional[Callable[[str], Optional[str]]] = None,
) -> dict[str, list[Path]]:
    """Run the full scraping pipeline over ``[start_date, end_date]``.

    Two valid modes (Cycle-1 MEDIUM: ``live`` is no longer a dead parameter):

    * **Live** (``live=True``): open a real ``FetcherSession``, share it across
      enumeration and race fetching. Issues real HTTPS requests to netkeiba.
      Rate-limited per the FetcherSession defaults.
    * **Offline** (``live=False, fetch_html=transport``): use the injected
      ``transport`` callable as the fetch boundary for BOTH enumeration and
      race fetching. No real browser, no real network. This is the path the
      Cycle-2 #5 full-chain e2e test exercises.

    Parameters
    ----------
    start_date, end_date : datetime.date
        Inclusive date range passed to ``enumerate_races``.
    raw_dir : pathlib.Path, default ``data/raw/netkeiba``
        Root of the raw HTML tree. ``fetch_race_html`` composes
        ``{raw_dir}/{YYYY}/{MM}/{race_id}.html`` from ``RaceRef.race_date``.
    standard_dir : pathlib.Path, default ``data/standard``
        Root of the standard-layer tree. Output goes under
        ``{standard_dir}/scraped/{YYYYMM}/{race,entry,result}.parquet``.
    live : bool, default False
        If True, open a real ``FetcherSession``. If False, MUST be paired
        with an injected ``fetch_html`` -- otherwise raises ``ValueError``
        (Cycle-1 MEDIUM: ``live=False`` without an injected transport forbids
        network access).
    max_races : Optional[int]
        If set, truncate the enumerated race list to this many races. Used
        for smoke runs.
    fetch_html : Optional[Callable[[str], Optional[str]]]
        Cycle-2 #5 injectable fetch boundary. When provided AND ``live=False``,
        drives both ``enumerate_races`` and ``fetch_race_html`` (as
        ``fetch_callable``). When provided AND ``live=True``, drives
        ``enumerate_races`` but race fetching uses the real session. When
        ``None``, a real ``FetcherSession`` is opened in live mode and
        ``make_fetch_html_callable`` builds the enumeration transport.

    Returns
    -------
    dict[str, list[pathlib.Path]]
        ``{"race": [...], "entry": [...], "result": [...]}`` -- the
        ``normalize_to_parquet`` return value.

    Raises
    ------
    ValueError
        If ``live=False`` and ``fetch_html is None`` (network forbidden).
    """
    # --- Cycle-1 MEDIUM: live=False WITHOUT injected transport is a hard error.
    if not live and fetch_html is None:
        raise ValueError(
            "run_scrape requires either live=True or an injected fetch_html "
            "callable (live=False without fetch_html forbids network access)."
        )

    parsed_races: list[dict] = []

    if live:
        # Live mode: open ONE FetcherSession and share it across enumeration
        # and race fetching (Cycle-1 HIGH browser-per-request).
        with FetcherSession() as session:
            enum_transport = (
                fetch_html
                if fetch_html is not None
                else make_fetch_html_callable(session)
            )
            race_refs = enumerate_races(start_date, end_date, enum_transport)
            parsed_races = _fetch_and_parse(
                race_refs=race_refs,
                raw_dir=raw_dir,
                session=session,
                fetch_callable=None,  # live path uses the real session
                max_races=max_races,
            )
    else:
        # Offline mode: the injected transport drives BOTH enumeration and
        # (as fetch_callable) race fetching (Cycle-3 #2 routing).
        assert fetch_html is not None  # guarded by the ValueError branch above
        race_refs = enumerate_races(start_date, end_date, fetch_html)
        parsed_races = _fetch_and_parse(
            race_refs=race_refs,
            raw_dir=raw_dir,
            session=None,
            fetch_callable=fetch_html,  # Cycle-3 #2: transport -> race fetch
            max_races=max_races,
        )

    return normalize_to_parquet(parsed_races, standard_dir)


def _fetch_and_parse(
    race_refs: list[RaceRef],
    raw_dir: Path,
    session: Optional[FetcherSession],
    fetch_callable: Optional[Callable[[str], Optional[str]]],
    max_races: Optional[int],
) -> list[dict]:
    """Fetch + parse each race. ``fetch_race_html`` None is skipped, others proceed.

    Parameters
    ----------
    race_refs : list[RaceRef]
        Enumerated races.
    raw_dir : pathlib.Path
        Root of the raw HTML tree.
    session : Optional[FetcherSession]
        Live-mode session. When None, ``fetch_callable`` MUST be provided
        (the caller guarantees this -- the orchestrator ValueError path
        already enforced it for the offline branch).
    fetch_callable : Optional[Callable[[str], Optional[str]]]
        Offline-mode transport (Cycle-3 #2). When None, the live session is
        used.
    max_races : Optional[int]
        If set, truncate to this many races (smoke runs).
    """
    refs = race_refs if max_races is None else race_refs[:max_races]
    if max_races is not None and len(race_refs) > max_races:
        logger.info(
            f"run_scrape: max_races={max_races} truncating from "
            f"{len(race_refs)} enumerated races"
        )

    parsed: list[dict] = []
    for ref in refs:
        # Cycle-3 #2: in the offline injected-transport branch, fetch_callable
        # is passed through to fetch_race_html so a race NOT already pre-saved
        # under raw_dir is fetched via the transport. A transport returning
        # None is handled gracefully (race skipped) rather than crashing with
        # AttributeError on None.fetch_with_retry.
        path = fetch_race_html(
            ref,
            session=session,
            raw_dir=raw_dir,
            fetch_callable=fetch_callable,
        )
        if path is None:
            logger.warning(
                f"run_scrape: fetch_race_html returned None for {ref.race_id}; "
                f"skipping (other races will proceed)"
            )
            continue
        try:
            parsed.append(parse_race_html(path))
        except Exception as exc:  # noqa: BLE001 -- parse errors drop one race, not the batch
            logger.error(
                f"run_scrape: parse_race_html failed for {ref.race_id} "
                f"({path}): {exc!r}; skipping"
            )
            continue
    return parsed


__all__ = ["run_scrape"]
