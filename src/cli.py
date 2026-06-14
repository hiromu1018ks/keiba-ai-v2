"""Click-based CLI entry point for the keiba scraping pipeline.

Thin wrapper over :func:`src.scraper.orchestrator.run_scrape`. This module does
NOT modify any scraper internals; it only translates CLI arguments into a
``run_scrape(...)`` call and reports the result.

Two subcommands:

* ``scrape`` -- runs the full pipeline in live mode (``live=True``). Real browser,
  real network. Offline mode is test-only and is intentionally NOT exposed here.
* ``status`` -- aggregates the scraped standard-layer Parquet files under
  ``data/standard/scraped/`` so an operator can eyeball coverage before/after a
  scrape run.

Logging: ``run_scrape`` emits progress via ``loguru`` INFO records, which by
default flow to stderr unchanged. No additional logging configuration is added
here (Phase 04 operability wrapper -- we keep the existing log surface).
"""

from __future__ import annotations

import datetime
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

import click
import pandas as pd

from src.scraper.orchestrator import (
    DEFAULT_RAW_DIR,
    DEFAULT_STANDARD_DIR,
    run_scrape,
)

# A scraped month partition directory looks like ``YYYYMM`` (e.g. ``202306``).
_MONTH_RE = re.compile(r"^\d{6}$")
_TABLES = ("race", "entry", "result")


def _parse_date(ctx: click.Context, param: click.Parameter, value: str) -> datetime.date:
    """Click callback: parse a ``YYYY-MM-DD`` string into a ``datetime.date``.

    Raises :class:`click.BadParameter` (a clean, non-zero-exit CLI error) on a
    malformed value rather than letting ``date.fromisoformat``'s ``ValueError``
    surface as an unhandled traceback.
    """
    try:
        return datetime.date.fromisoformat(value)
    except ValueError as e:
        raise click.BadParameter(
            f"{value!r} is not a valid date (expected YYYY-MM-DD)",
            ctx=ctx,
            param=param,
        ) from e


@click.group()
def main() -> None:
    """Keiba AI v2 -- JRA trifecta EV system CLI."""


@main.command()
@click.option(
    "--start",
    required=True,
    callback=_parse_date,
    help="Range start date (inclusive), YYYY-MM-DD.",
)
@click.option(
    "--end",
    required=True,
    callback=_parse_date,
    help="Range end date (inclusive), YYYY-MM-DD.",
)
@click.option(
    "--max-races",
    type=int,
    default=None,
    help="Truncate to this many races (smoke runs). Default: no limit.",
)
@click.option(
    "--raw-dir",
    "raw_dir",
    type=click.Path(path_type=Path),
    default=DEFAULT_RAW_DIR,
    show_default=True,
    help="Raw HTML tree root.",
)
@click.option(
    "--standard-dir",
    "standard_dir",
    type=click.Path(path_type=Path),
    default=DEFAULT_STANDARD_DIR,
    show_default=True,
    help="Standard-layer output root.",
)
@click.option(
    "--no-progress",
    "no_progress",
    is_flag=True,
    default=False,
    help="Disable the tqdm progress bar (for log-file redirection / CI).",
)
def scrape(
    start: datetime.date,
    end: datetime.date,
    max_races: Optional[int],
    raw_dir: Path,
    standard_dir: Path,
    no_progress: bool,
) -> None:
    """Run the LIVE scraping pipeline over [start, end].

    Issues real HTTPS requests to netkeiba via Playwright. Progress logs stream
    to stderr. On completion the number of output Parquet paths written per
    table (race/entry/result) is printed. Pass --no-progress to suppress the
    tqdm bar for log files / CI.
    """
    result = run_scrape(
        start_date=start,
        end_date=end,
        raw_dir=raw_dir,
        standard_dir=standard_dir,
        live=True,
        max_races=max_races,
        progress=not no_progress,
    )
    click.echo(
        "scrape complete -- written output path(s): "
        f"race={len(result['race'])} entry={len(result['entry'])} "
        f"result={len(result['result'])}"
    )


@main.command()
def status() -> None:
    """Summarize scraped standard-layer Parquet under data/standard/scraped/.

    Prints per-table (race/entry/result) total row counts, per-month (YYYYMM)
    file counts, per-month race row counts, and the race_date min~max span.
    Prints ``no scraped data yet`` when no Parquet files are present.
    """
    scraped_dir = DEFAULT_STANDARD_DIR / "scraped"
    # Discover partitioned files ({YYYYMM}/{table}.parquet) and any root-level
    # placeholder files ({table}.parquet). ``Path.glob`` yields nothing (does not
    # raise) when the directory is absent, so a fresh checkout never crashes.
    files = sorted({*scraped_dir.glob("*.parquet"), *scraped_dir.glob("*/*.parquet")})
    if not files:
        click.echo("no scraped data yet")
        return

    table_totals: dict[str, int] = dict.fromkeys(_TABLES, 0)
    month_file_counts: dict[str, int] = defaultdict(int)
    month_race_rows: dict[str, int] = defaultdict(int)
    race_dates: list[str] = []

    for path in files:
        table = path.stem
        month = path.parent.name if _MONTH_RE.match(path.parent.name) else "unpartitioned"
        # Read with pandas (spec requirement). pyarrow is the installed engine.
        df = pd.read_parquet(path)
        nrows = len(df)
        if table in table_totals:
            table_totals[table] += nrows
        month_file_counts[month] += 1
        if table == "race":
            month_race_rows[month] += nrows
            if "race_date" in df.columns:
                race_dates.extend(df["race_date"].dropna().astype(str).tolist())

    click.echo(f"Scraped data summary ({scraped_dir})")
    click.echo("-" * 60)
    click.echo(
        f"Rows: race={table_totals['race']} "
        f"entry={table_totals['entry']} result={table_totals['result']}"
    )
    click.echo("")
    click.echo("Month    files  race_rows")
    for month in sorted(month_file_counts):
        click.echo(f"{month:<8} {month_file_counts[month]:<6} {month_race_rows.get(month, 0)}")
    if race_dates:
        click.echo(f"race_date: {min(race_dates)} ~ {max(race_dates)}")


if __name__ == "__main__":  # pragma: no cover - manual invocation only
    main()
