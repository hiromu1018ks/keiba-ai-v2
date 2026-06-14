"""Tests for the click CLI wrapper (``src.cli``).

No real network. The ``scrape`` subcommand monkeypatches ``run_scrape`` so the
real live pipeline never executes; only the wiring (argument parsing, ``live=True``
enforcement, path-count echo) is verified. ``status`` is pointed at a tmp dir via
monkeypatching ``src.cli.DEFAULT_STANDARD_DIR``.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from click.testing import CliRunner

import src.cli as cli_mod
from src.cli import main


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# --help exits
# ---------------------------------------------------------------------------


def test_scrape_help_exits_zero(runner: CliRunner) -> None:
    result = runner.invoke(main, ["scrape", "--help"])
    assert result.exit_code == 0
    assert "--start" in result.output
    assert "--end" in result.output
    assert "--max-races" in result.output
    assert "--no-progress" in result.output


def test_status_help_exits_zero(runner: CliRunner) -> None:
    result = runner.invoke(main, ["status", "--help"])
    assert result.exit_code == 0
    assert "scraped" in result.output


# ---------------------------------------------------------------------------
# status: empty / missing data does not crash
# ---------------------------------------------------------------------------


def test_status_no_files_does_not_crash(
    runner: CliRunner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Redirect the status root to an empty tmp dir (no scraped/ subdir at all).
    monkeypatch.setattr(cli_mod, "DEFAULT_STANDARD_DIR", tmp_path)
    result = runner.invoke(main, ["status"])
    assert result.exit_code == 0
    assert "no scraped data yet" in result.output


def test_status_aggregates_files(
    runner: CliRunner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scraped = tmp_path / "scraped"
    (scraped / "202301").mkdir(parents=True)
    (scraped / "202302").mkdir(parents=True)
    pd.DataFrame({"race_id": ["r1", "r2"], "race_date": ["2023-01-05", "2023-01-20"]}).to_parquet(
        scraped / "202301" / "race.parquet"
    )
    pd.DataFrame({"race_id": ["r3"], "race_date": ["2023-02-10"]}).to_parquet(
        scraped / "202302" / "race.parquet"
    )
    pd.DataFrame({"horse_race_id": ["r1h1", "r1h2", "r2h1"]}).to_parquet(
        scraped / "202301" / "entry.parquet"
    )

    monkeypatch.setattr(cli_mod, "DEFAULT_STANDARD_DIR", tmp_path)
    result = runner.invoke(main, ["status"])
    assert result.exit_code == 0
    # Total rows: race 3 (2 + 1), entry 3, result 0.
    assert "race=3" in result.output
    assert "entry=3" in result.output
    assert "result=0" in result.output
    # Per-month breakdown.
    assert "202301" in result.output
    assert "202302" in result.output
    # race_date min~max span.
    assert "2023-01-05" in result.output
    assert "2023-02-10" in result.output


# ---------------------------------------------------------------------------
# scrape: run_scrape is called with live=True and parsed dates
# ---------------------------------------------------------------------------


def test_scrape_calls_run_scrape_live_true(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run_scrape(**kwargs: Any) -> dict[str, list[Path]]:
        captured.update(kwargs)
        return {
            "race": [Path("a/race.parquet"), Path("b/race.parquet")],
            "entry": [Path("a/entry.parquet")],
            "result": [Path("a/result.parquet"), Path("b/result.parquet")],
        }

    monkeypatch.setattr(cli_mod, "run_scrape", fake_run_scrape)

    result = runner.invoke(main, ["scrape", "--start", "2022-01-01", "--end", "2022-01-02"])

    assert result.exit_code == 0, result.output
    # Dates parsed to datetime.date, live forced True.
    assert captured["start_date"] == datetime.date(2022, 1, 1)
    assert captured["end_date"] == datetime.date(2022, 1, 2)
    assert captured["live"] is True
    assert captured["max_races"] is None
    # Defaults come from the orchestrator's constants.
    assert captured["raw_dir"] == cli_mod.DEFAULT_RAW_DIR == Path("data/raw/netkeiba")
    assert captured["standard_dir"] == cli_mod.DEFAULT_STANDARD_DIR
    # Default (no --no-progress) forwards progress=True.
    assert captured["progress"] is True
    # Path-count echo per table.
    assert "race=2" in result.output
    assert "entry=1" in result.output
    assert "result=2" in result.output


def test_scrape_no_progress_flag_forwards_false(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run_scrape(**kwargs: Any) -> dict[str, list[Path]]:
        captured.update(kwargs)
        return {"race": [], "entry": [], "result": []}

    monkeypatch.setattr(cli_mod, "run_scrape", fake_run_scrape)

    result = runner.invoke(
        main,
        ["scrape", "--start", "2022-01-01", "--end", "2022-01-02", "--no-progress"],
    )

    assert result.exit_code == 0, result.output
    assert captured["progress"] is False
    assert captured["live"] is True


def test_scrape_passes_max_races_and_dirs(
    runner: CliRunner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run_scrape(**kwargs: Any) -> dict[str, list[Path]]:
        captured.update(kwargs)
        return {"race": [], "entry": [], "result": []}

    monkeypatch.setattr(cli_mod, "run_scrape", fake_run_scrape)

    result = runner.invoke(
        main,
        [
            "scrape",
            "--start",
            "2022-03-01",
            "--end",
            "2022-03-31",
            "--max-races",
            "5",
            "--raw-dir",
            str(tmp_path / "raw"),
            "--standard-dir",
            str(tmp_path / "standard"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["max_races"] == 5
    assert captured["raw_dir"] == tmp_path / "raw"
    assert captured["standard_dir"] == tmp_path / "standard"
    assert captured["live"] is True
    # Zero-length path lists still echo cleanly.
    assert "race=0" in result.output


def test_scrape_rejects_bad_date(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # run_scrape must never be reached on a bad date.
    def boom(**_kwargs: Any) -> dict[str, list[Path]]:
        raise AssertionError("run_scrape should not be called for a bad date")

    monkeypatch.setattr(cli_mod, "run_scrape", boom)

    result = runner.invoke(main, ["scrape", "--start", "not-a-date", "--end", "2022-01-02"])

    assert result.exit_code != 0
    assert "not-a-date" in result.output
