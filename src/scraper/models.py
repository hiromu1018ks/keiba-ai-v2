"""Scraper value-object models.

This module holds lightweight immutable value types for the scraping pipeline.
Unlike the Pydantic ``BaseModel`` schemas in ``src/schemas/`` (which define the
standard-layer table shapes and carry validation), these dataclasses are plain
typed records passed between enumeration / fetcher / parser stages.
"""

import datetime
from dataclasses import dataclass


@dataclass(frozen=True)
class RaceRef:
    """A reference to a race discovered during calendar enumeration.

    ``race_date`` is the source of truth for the raw HTML path ``{YYYY}/{MM}``.
    ``race_id[4:6]`` is the JRA course code (the ``YYYYPPCCDDRR`` layout, where
    ``PP`` is the meeting/course pair), NOT a calendar month, and MUST NOT be
    used to derive a path. This invariant is the Codex Review HIGH #1 fix: a
    forged or off-by-one course code would otherwise write the HTML into the
    wrong month directory.

    Fields
    ------
    race_id : str
        12-digit identifier (``YYYYPPCCDDRR``).
    race_date : datetime.date
        Calendar date parsed from the netkeiba race-day page. The fetcher
        (Plan 03) derives ``{YYYY}/{MM}`` from this field exclusively.
    """

    race_id: str
    race_date: datetime.date
