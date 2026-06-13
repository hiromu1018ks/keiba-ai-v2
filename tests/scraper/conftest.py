"""Shared pytest fixtures for scraper tests.

Provides tmp_path-based directory fixtures used across the scraper test
suite (Plans 02-06 consume these). No fixture references real ``data/``
paths — every path is derived from pytest's per-test ``tmp_path`` so tests
are hermetic. The one exception is ``golden_html_dir``, which points at the
repo-relative ``tests/scraper/fixtures/html/`` directory that holds golden
HTML fixtures captured in Plan 04 Task 3.
"""

from pathlib import Path

import pytest


@pytest.fixture
def tmp_raw_dir(tmp_path: Path) -> Path:
    """Temporary ``data/raw/netkeiba`` root for fetcher tests.

    Fetchers compose this into ``{YYYY}/{MM}/{race_id}.html`` using
    ``RaceRef.race_date`` (Plan 03, HIGH #1 path derivation).
    """
    raw_dir = tmp_path / "data" / "raw" / "netkeiba"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


@pytest.fixture
def tmp_standard_dir(tmp_path: Path) -> Path:
    """Temporary ``data/standard`` root for normalizer tests."""
    standard_dir = tmp_path / "data" / "standard"
    standard_dir.mkdir(parents=True, exist_ok=True)
    return standard_dir


@pytest.fixture
def golden_html_dir() -> Path:
    """Repo-relative directory holding golden netkeiba HTML fixtures.

    The actual HTML files are captured in Plan 04 Task 3 (human checkpoint)
    and consumed by Plan 04 parser tests and the Plan 06 end-to-end suite.
    This fixture only guarantees the directory exists so writers do not
    need to ``mkdir`` defensively.
    """
    fixtures = Path("tests/scraper/fixtures/html")
    fixtures.mkdir(parents=True, exist_ok=True)
    return fixtures
