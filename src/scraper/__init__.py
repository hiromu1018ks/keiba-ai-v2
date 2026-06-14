"""Scraping infrastructure for netkeiba race data. Public API re-exports.

This package is built across Plans 02-06 of Phase 04. Plan 06 (this commit)
adds the public re-exports now that every submodule exists, transitioning away
from the Plan-01 import-safe empty marker.

Submodules (import directly for advanced use):
  * ``models``        -- ``RaceRef`` value object (Plan 02)
  * ``enumeration``   -- 3-level calendar traversal (Plan 02)
  * ``fetcher``       -- ``FetcherSession`` + ``fetch_race_html`` (Plan 03)
  * ``parser``        -- ``parse_race_html`` (Plan 04)
  * ``course_codes``  -- ``COURSE_CODE_MAP`` (Plan 04)
  * ``flag_crosswalk``-- ``FLAG_CROSSWALK`` (Plan 04)
  * ``normalizer``    -- ``normalize_to_parquet`` (Plan 05)
  * ``orchestrator``  -- ``run_scrape`` (Plan 06)
"""
from src.scraper.enumeration import (
    enumerate_race_day_urls,
    enumerate_races,
    enumerate_races_for_day,
)
from src.scraper.fetcher import (
    FetcherSession,
    fetch_race_html,
    fetch_with_retry,
)
from src.scraper.models import RaceRef
from src.scraper.normalizer import normalize_to_parquet
from src.scraper.orchestrator import run_scrape
from src.scraper.parser import parse_race_html

__all__ = [
    "FetcherSession",
    "RaceRef",
    "enumerate_race_day_urls",
    "enumerate_races",
    "enumerate_races_for_day",
    "fetch_race_html",
    "fetch_with_retry",
    "normalize_to_parquet",
    "parse_race_html",
    "run_scrape",
]
