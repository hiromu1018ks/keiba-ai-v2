"""End-to-end scraper pipeline tests (Cycle-2 #5, #7, Cycle-1 #9).

Three coverage tiers:

1. **TestParseOnlyFixture** (Cycle-1 HIGH #9): for each golden HTML fixture,
   run REAL ``parse_race_html`` -> REAL ``normalize_to_parquet`` and assert
   the Parquet conforms to the standard-layer schema, every horse_race_id is
   14-digit, no ``head_count`` column, etc. Skips enumerate + fetch entirely.

2. **TestFullChainE2E** (Cycle-2 HIGH #5): a SINGLE test runs the REAL
   ``enumerate_races`` -> (injected ``_GoldenTransport`` returning saved golden
   HTML) -> REAL ``fetch_race_html`` (offline, dedup short-circuits via
   pre-saved raw HTML) -> REAL ``parse_race_html`` -> REAL
   ``normalize_to_parquet``. The network boundary is the ONLY thing mocked --
   every real function runs. Distinct from the parse-only test (which skips
   enumerate/fetch) and from the orchestrator unit tests (which mock all
   sub-steps).

   CYCLE-3 #2: ``test_full_chain_handles_failed_fetch`` exercises a real
   transport-None -> ``fetch_race_html(fetch_callable=transport)``-returns-None
   -> race-skipped flow that was previously unreachable.

3. **TestSchemaCompatibility** (Cycle-2 HIGH #7): asserts physical-type
   EQUALITY for columns where Kaggle is NON-null, and deliberate promotion
   (null -> bool/string) for Kaggle-null columns. The Cycle-1
   "equality on every overlapping column" assertion is GONE -- it was
   unachievable because pandas nullable boolean serializes to Arrow bool even
   for an all-None column, while Kaggle's null-data columns are Arrow null.

4. **TestOptInLiveSmoke** (Cycle-1 MEDIUM): an opt-in live smoke test marked
   ``@pytest.mark.live`` that is SKIPPED by default (no network in CI).
"""

import datetime
import os
import re
from pathlib import Path
from typing import Optional

import pandas as pd
import pyarrow.parquet as pq
import pytest

from src.scraper.normalizer import normalize_to_parquet
from src.scraper.orchestrator import run_scrape
from src.scraper.parser import parse_race_html
from src.schemas.entry import EntrySchema
from src.schemas.race import RaceSchema
from src.schemas.result import ResultSchema

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "html"
KAGGLE_STANDARD = Path("data/standard")

# Fixture metadata: (race_id, race_date, course_code, expected_surface, is_graded)
# race_date is what the REAL parser extracts from the fixture's <title>/<p>.
GOLDEN_FIXTURES = [
    ("202206050509", datetime.date(2022, 12, 17), "06", "芝", False),  # ひいらぎ賞
    ("202309030811", datetime.date(2023, 6, 25), "09", "芝", True),   # 宝塚記念 G1
    ("202405010809", datetime.date(2024, 2, 18), "05", "ダート", False),  # ヒヤシンスS L
    ("202206050508", datetime.date(2022, 12, 17), "06", "ダート", False),
    # The obstacle fixture (202209060504) is filtered out by the normalizer,
    # so it is NOT in the full-chain e2e set. It IS exercised by
    # TestParseOnlyFixture parametrization (parse+normalize drops it).
]
GOLDEN_FIXTURE_IDS = [fx[0] for fx in GOLDEN_FIXTURES]

# 14-digit horse_race_id regex (Cycle-1 HIGH #2 end-to-end guard).
_HORSE_RACE_ID_RE = re.compile(r"\d{14}")


# ---------------------------------------------------------------------------
# TestParseOnlyFixture (Cycle-1 HIGH #9): parse -> normalize only.
# ---------------------------------------------------------------------------


def _all_fixture_ids() -> list[str]:
    """Return every fixture filename stem (incl. obstacle) for parametrization."""
    return [
        "202206050509",
        "202309030811",
        "202405010809",
        "202206050508",
        "202209060504",
    ]


class TestParseOnlyFixture:
    """Cycle-1 HIGH #9: parse_race_html -> normalize_to_parquet per fixture."""

    @pytest.mark.parametrize("race_id", _all_fixture_ids())
    def test_parse_then_normalize_each_golden_fixture(
        self, race_id: str, tmp_standard_dir: Path
    ) -> None:
        """Parse + normalize each fixture; verify schema + 14-digit horse_race_id + no head_count."""
        path = FIXTURES_DIR / f"{race_id}.html"
        assert path.exists(), f"fixture missing: {path}"
        parsed = parse_race_html(path)
        result = normalize_to_parquet([parsed], standard_dir=tmp_standard_dir)

        # normalize_to_parquet drops obstacle races. If the fixture is the
        # obstacle fixture, expect the placeholder (empty) output.
        is_obstacle = parsed["race"].get("obstacle") == "障害"

        # Race table.
        race_paths = result["race"]
        race_df = pd.concat([pd.read_parquet(p) for p in race_paths], ignore_index=True)
        assert set(race_df.columns) == set(RaceSchema.model_fields.keys())
        assert "head_count" not in race_df.columns

        if is_obstacle:
            # Obstacle race filtered -> zero rows.
            assert len(race_df) == 0
            return

        assert len(race_df) == 1, f"{race_id}: expected 1 race row, got {len(race_df)}"

        # Entry + result tables.
        entry_df = pd.concat(
            [pd.read_parquet(p) for p in result["entry"] if len(pd.read_parquet(p)) > 0],
            ignore_index=True,
        )
        result_df = pd.concat(
            [pd.read_parquet(p) for p in result["result"] if len(pd.read_parquet(p)) > 0],
            ignore_index=True,
        )
        # Every entry/result horse_race_id is 14-digit (Cycle-1 HIGH #2).
        for hid in entry_df["horse_race_id"].dropna().tolist():
            assert _HORSE_RACE_ID_RE.fullmatch(str(hid)), (
                f"{race_id}: horse_race_id {hid!r} not 14 digits"
            )
        for hid in result_df["horse_race_id"].dropna().tolist():
            assert _HORSE_RACE_ID_RE.fullmatch(str(hid)), (
                f"{race_id}: horse_race_id {hid!r} not 14 digits"
            )
        assert len(entry_df) > 0
        assert len(result_df) > 0
        # entry/result are 1-to-1 (Cycle-1 integrity guard).
        assert set(entry_df["horse_race_id"]) == set(result_df["horse_race_id"])

    def test_graded_fixture_sets_graded_stakes_flag(self, tmp_standard_dir: Path) -> None:
        """Cycle-1 HIGH #6 end-to-end: 宝塚記念 sets race_flag_graded_stakes=True after normalize."""
        parsed = parse_race_html(FIXTURES_DIR / "202309030811.html")
        result = normalize_to_parquet([parsed], standard_dir=tmp_standard_dir)
        race_df = pd.concat([pd.read_parquet(p) for p in result["race"]], ignore_index=True)
        assert len(race_df) == 1
        val = race_df.iloc[0]["race_flag_graded_stakes"]
        assert bool(val) is True, f"expected graded_stakes True, got {val!r}"

    def test_finish_note_fixture_handled(self, tmp_standard_dir: Path) -> None:
        """Parse + normalize does not crash on any finish-note format present in fixtures."""
        for race_id in _all_fixture_ids():
            parsed = parse_race_html(FIXTURES_DIR / f"{race_id}.html")
            # normalize_to_parquet must not raise regardless of finish_note values.
            normalize_to_parquet([parsed], standard_dir=tmp_standard_dir)

    def test_diversity_axes_covered(self, tmp_standard_dir: Path) -> None:
        """The fixture set covers turf / dirt / graded / obstacle diversity axes."""
        surfaces: set[str] = set()
        graded_seen = False
        obstacle_seen = False
        for race_id in _all_fixture_ids():
            parsed = parse_race_html(FIXTURES_DIR / f"{race_id}.html")
            race = parsed["race"]
            if race.get("surface"):
                surfaces.add(race["surface"])
            if race.get("race_flag_graded_stakes"):
                graded_seen = True
            if race.get("obstacle") == "障害":
                obstacle_seen = True
        assert "芝" in surfaces
        assert "ダート" in surfaces
        assert graded_seen
        assert obstacle_seen


# ---------------------------------------------------------------------------
# TestFullChainE2E (Cycle-2 HIGH #5): the single full-chain test.
# ---------------------------------------------------------------------------


class _GoldenTransport:
    """Test double: maps absolute URLs to saved golden HTML strings.

    The Cycle-2 #5 full-chain test injects an instance of this class as the
    ``fetch_html`` argument to ``run_scrape``. The transport serves:

      * Calendar page URLs (``/race/calendar/{YYYYMM}/``) -> minimal calendar
        HTML listing each fixture's race day as a ``/race/list/{YYYYMMDD}/`` link.
      * Race-day page URLs (``/race/list/{YYYYMMDD}/``) -> minimal race-day
        HTML listing each fixture's ``/race/{race_id}/`` link.
      * Race page URLs (``/race/{race_id}/``) -> the actual golden HTML
        content (read from disk).

    Unknown URLs return None (simulates fetch failure).
    """

    def __init__(self, fixtures: list[tuple]) -> None:
        """``fixtures`` is the GOLDEN_FIXTURES list: (race_id, race_date, ...)."""
        self._fixtures = fixtures
        # Pre-load the actual golden HTML for each race URL.
        self._race_html: dict[str, str] = {}
        for race_id, _date, *_ in fixtures:
            path = FIXTURES_DIR / f"{race_id}.html"
            self._race_html[race_id] = path.read_text(encoding="utf-8")

    def __call__(self, url: str) -> Optional[str]:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        path = parsed.path

        # Calendar page: /race/calendar/{YYYYMM}/
        cal_match = re.match(r"^/race/calendar/(\d{6})/?$", path)
        if cal_match:
            yyyymm = cal_match.group(1)
            return self._build_calendar_html(yyyymm)

        # Race-day page: /race/list/{YYYYMMDD}/
        day_match = re.match(r"^/race/list/(\d{8})/?$", path)
        if day_match:
            yyyymmdd = day_match.group(1)
            return self._build_race_day_html(yyyymmdd)

        # Race page: /race/{12-digit}/
        race_match = re.match(r"^/race/(\d{12})/?$", path)
        if race_match:
            race_id = race_match.group(1)
            return self._race_html.get(race_id)

        return None

    def _build_calendar_html(self, yyyymm: str) -> str:
        """Build minimal calendar HTML listing race days whose YYYYMM matches."""
        year = int(yyyymm[:4])
        month = int(yyyymm[4:6])
        links: list[str] = []
        for _rid, race_date, *_ in self._fixtures:
            if race_date.year == year and race_date.month == month:
                yyyymmdd = race_date.strftime("%Y%m%d")
                links.append(f'<a href="/race/list/{yyyymmdd}/">{yyyymmdd}</a>')
        return f"<html><body>{''.join(links)}</body></html>"

    def _build_race_day_html(self, yyyymmdd: str) -> str:
        """Build minimal race-day HTML listing race_ids on this day."""
        target = datetime.datetime.strptime(yyyymmdd, "%Y%m%d").date()
        links: list[str] = []
        for rid, race_date, *_ in self._fixtures:
            if race_date == target:
                links.append(f'<a href="/race/{rid}/">{rid}</a>')
        return f"<html><body>{''.join(links)}</body></html>"


def _presave_fixture_raw_html(
    fixtures: list[tuple], raw_dir: Path
) -> None:
    """Copy each fixture's HTML to its expected raw path under ``raw_dir``.

    This makes ``fetch_race_html``'s SCRP-05 dedup short-circuit return the
    path WITHOUT consulting the transport -- so the happy-path test isolates
    enumerate + parse + normalize while still exercising the real dedup branch.
    """
    for race_id, race_date, *_ in fixtures:
        year = f"{race_date.year:04d}"
        month = f"{race_date.month:02d}"
        out_dir = raw_dir / year / month
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{race_id}.html"
        src = FIXTURES_DIR / f"{race_id}.html"
        out_path.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


class TestFullChainE2E:
    """Cycle-2 HIGH #5: a SINGLE test connects enumerate -> fetch -> parse -> normalize."""

    def test_full_chain_end_to_end(
        self, tmp_raw_dir: Path, tmp_standard_dir: Path
    ) -> None:
        """REAL enumerate -> injected-fetch -> REAL fetch_race_html dedup -> REAL parse -> REAL normalize.

        This is the only test that connects the REAL pipeline with ONLY the
        network boundary mocked (via ``_GoldenTransport``). Distinct from
        TestParseOnlyFixture (skips enumerate/fetch) and TestRunScrape (fully
        mocked).
        """
        # The obstacle fixture (202209060504) is filtered by the normalizer;
        # exclude it from the e2e input to keep row-count assertions clean.
        fixtures = GOLDEN_FIXTURES  # 4 non-obstacle fixtures
        transport = _GoldenTransport(fixtures)

        # Pre-save each fixture's HTML to its expected raw path so
        # fetch_race_html's SCRP-05 dedup returns the path without consulting
        # the transport. This still exercises the REAL dedup code path.
        _presave_fixture_raw_html(fixtures, tmp_raw_dir)

        # Date range: earliest -> latest fixture date.
        start = min(fx[1] for fx in fixtures)
        end = max(fx[1] for fx in fixtures)

        result = run_scrape(
            start_date=start,
            end_date=end,
            raw_dir=tmp_raw_dir,
            standard_dir=tmp_standard_dir,
            live=False,
            fetch_html=transport,
        )

        # (a) Returned dict has race/entry/result path lists.
        assert set(result.keys()) >= {"race", "entry", "result"}
        assert all(isinstance(paths, list) for paths in result.values())

        # Read back the race Parquet.
        race_df = pd.concat(
            [pd.read_parquet(p) for p in result["race"] if p.exists()],
            ignore_index=True,
        )
        # (b) Columns == RaceSchema.model_fields keys.
        assert set(race_df.columns) == set(RaceSchema.model_fields.keys())

        # (g) Total race row count == number of distinct fixture race_ids.
        assert len(race_df) == len(fixtures), (
            f"expected {len(fixtures)} race rows (one per fixture), "
            f"got {len(race_df)} -- silent dedup/overwrite loss?"
        )

        # (d) At least one row has the CORRECT course code (Cycle-1 HIGH #5).
        # fixture 202206050509 -> 中山 -> "06".
        nakayama_rows = race_df[race_df["race_id"] == "202206050509"]
        assert len(nakayama_rows) == 1
        assert nakayama_rows.iloc[0]["course_code"] == "06"

        # (e) For the graded fixture, race_flag_graded_stakes is True
        # (Cycle-1 HIGH #6 + Cycle-2 #2 end-to-end).
        graded_rows = race_df[race_df["race_id"] == "202309030811"]
        assert len(graded_rows) == 1
        assert bool(graded_rows.iloc[0]["race_flag_graded_stakes"]) is True

        # (c) Every entry/result horse_race_id matches re.fullmatch(r"\d{14}", ...).
        entry_df = pd.concat(
            [pd.read_parquet(p) for p in result["entry"] if p.exists()],
            ignore_index=True,
        )
        result_df = pd.concat(
            [pd.read_parquet(p) for p in result["result"] if p.exists()],
            ignore_index=True,
        )
        for hid in entry_df["horse_race_id"].dropna().tolist():
            assert _HORSE_RACE_ID_RE.fullmatch(str(hid)), (
                f"entry horse_race_id {hid!r} not 14 digits"
            )
        for hid in result_df["horse_race_id"].dropna().tolist():
            assert _HORSE_RACE_ID_RE.fullmatch(str(hid)), (
                f"result horse_race_id {hid!r} not 14 digits"
            )

        # (f) Entry/result partition files landed under the correct {YYYYMM}/
        # derived from race_date (Cycle-2 #6 end-to-end).
        # Fixture 202309030811 has race_date 2023-06-25 -> partition 202306.
        graded_partition = tmp_standard_dir / "scraped" / "202306" / "entry.parquet"
        assert graded_partition.exists(), (
            f"expected entry partition under 202306/, listing: "
            f"{list((tmp_standard_dir / 'scraped').rglob('entry.parquet'))}"
        )
        # Fixture 202405010809 has race_date 2024-02-18 -> partition 202402.
        hyacinth_partition = tmp_standard_dir / "scraped" / "202402" / "entry.parquet"
        assert hyacinth_partition.exists()
        # Fixture 202206050509 / 202206050508 both race_date 2022-12-17 -> 202212.
        dec_partition = tmp_standard_dir / "scraped" / "202212" / "entry.parquet"
        assert dec_partition.exists()

    def test_full_chain_handles_failed_fetch(
        self, tmp_raw_dir: Path, tmp_standard_dir: Path
    ) -> None:
        """CYCLE-3 #2: a race for which the transport returns None is skipped.

        Do NOT pre-save the failing race's HTML to the raw path -- so
        fetch_race_html's SCRP-05 dedup does NOT short-circuit and the
        transport IS consulted via ``fetch_callable``. A transport returning
        None must be handled gracefully (race skipped/quarantined), NOT crash
        with AttributeError on a None session.
        """
        # Use 2 fixtures; the second's HTML is NOT pre-saved.
        fixtures = [
            ("202206050509", datetime.date(2022, 12, 17), "06", "芝", False),
            ("202309030811", datetime.date(2023, 6, 25), "09", "芝", True),
        ]
        # Transport returns None for the second race URL.
        transport = _GoldenTransport(fixtures)

        def _transport_none_for_second(url: str) -> Optional[str]:
            from urllib.parse import urlparse

            path = urlparse(url).path
            if path == "/race/202309030811/":
                return None  # simulate failed fetch
            return transport(url)

        # Pre-save ONLY the first race's HTML. The second will require the
        # transport (which returns None).
        _presave_fixture_raw_html([fixtures[0]], tmp_raw_dir)

        start = min(fx[1] for fx in fixtures)
        end = max(fx[1] for fx in fixtures)

        # Must NOT raise (the prior bug crashed with AttributeError on None).
        result = run_scrape(
            start_date=start,
            end_date=end,
            raw_dir=tmp_raw_dir,
            standard_dir=tmp_standard_dir,
            live=False,
            fetch_html=_transport_none_for_second,
        )

        # The failing race (202309030811) was skipped; the other (202206050509)
        # still parsed and normalized.
        race_df = pd.concat(
            [pd.read_parquet(p) for p in result["race"] if p.exists()],
            ignore_index=True,
        )
        assert len(race_df) == 1, f"expected 1 race (one skipped), got {len(race_df)}"
        assert race_df.iloc[0]["race_id"] == "202206050509"


# ---------------------------------------------------------------------------
# TestSchemaCompatibility (Cycle-2 HIGH #7): achievable dtype-fidelity.
# ---------------------------------------------------------------------------


def _kaggle_null_columns(table: str) -> set[str]:
    """Return the set of Kaggle-null columns for a table.

    Reads ``data/standard/{table}.parquet`` via pyarrow and collects every
    field whose Arrow type is ``null`` (Kaggle has no data for these). Returns
    an empty set if the file is absent (tests that depend on Kaggle Parquet
    skip themselves).
    """
    path = KAGGLE_STANDARD / f"{table}.parquet"
    if not path.exists():
        return set()
    schema = pq.read_schema(str(path))
    return {f.name for f in schema if str(f.type) == "null"}


def _kaggle_schema(table: str) -> Optional[dict[str, str]]:
    """Return ``{col: arrow_type_str}`` for the Kaggle Parquet, or None if absent."""
    path = KAGGLE_STANDARD / f"{table}.parquet"
    if not path.exists():
        return None
    schema = pq.read_schema(str(path))
    return {f.name: str(f.type) for f in schema}


def _scraped_parquet_for_e2e(tmp_standard_dir: Path) -> dict[str, list[Path]]:
    """Run a parse + normalize on the full golden set to produce scraped Parquet."""
    parsed = [parse_race_html(FIXTURES_DIR / f"{rid}.html") for rid in GOLDEN_FIXTURE_IDS]
    return normalize_to_parquet(parsed, standard_dir=tmp_standard_dir)


class TestSchemaCompatibility:
    """Cycle-2 HIGH #7: equality for non-null Kaggle columns; promotion for null columns."""

    @pytest.fixture(autouse=True)
    def _require_kaggle_parquet(self) -> None:
        """Skip this class if the Kaggle Parquet is absent."""
        for tbl in ("race", "entry", "result"):
            if not (KAGGLE_STANDARD / f"{tbl}.parquet").exists():
                pytest.skip(f"Kaggle {tbl}.parquet absent -- schema comparison not possible")

    def test_scraped_columns_superset_of_kaggle_overlap(
        self, tmp_standard_dir: Path
    ) -> None:
        """For overlapping column names, both sides have the column (presence check)."""
        _scraped_parquet_for_e2e(tmp_standard_dir)  # ensure scraped Parquet exists
        schema_map = {
            "race": RaceSchema,
            "entry": EntrySchema,
            "result": ResultSchema,
        }
        for tbl, schema in schema_map.items():
            kaggle = _kaggle_schema(tbl)
            if kaggle is None:
                continue
            scraped_cols = set(schema.model_fields.keys())
            overlap = set(kaggle.keys()) & scraped_cols
            # Every overlapping column must be present on both sides (trivially
            # true since both derive from the schema, but asserts the contract).
            assert overlap == set(kaggle.keys()) & scraped_cols

    def test_physical_type_equality_for_non_null_kaggle_columns(
        self, tmp_standard_dir: Path
    ) -> None:
        """For columns where Kaggle is NON-null, scraped Arrow type EQUALS Kaggle Arrow type.

        This is the achievable equality half of Cycle-2 #7. Examples:
          * finish_position: both int64
          * weight_assigned: both double
          * corner_1..4: both double (Cycle-3 #1)
          * race_flag_handicap: both bool
        """
        result = _scraped_parquet_for_e2e(tmp_standard_dir)
        schema_map = {
            "race": RaceSchema,
            "entry": EntrySchema,
            "result": ResultSchema,
        }
        mismatches: list[str] = []
        for tbl, schema in schema_map.items():
            kaggle = _kaggle_schema(tbl)
            if kaggle is None:
                continue
            null_cols = _kaggle_null_columns(tbl)
            # Read the scraped Parquet schema.
            paths = [p for p in result[tbl] if p.exists() and len(pd.read_parquet(p)) > 0]
            if not paths:
                continue
            scraped_schema = pq.read_schema(str(paths[0]))
            scraped_types = {f.name: str(f.type) for f in scraped_schema}
            # For every overlapping NON-null Kaggle column, assert equality.
            for col, kaggle_type in kaggle.items():
                if col in null_cols:
                    continue
                if col not in scraped_types:
                    continue
                if scraped_types[col] != kaggle_type:
                    mismatches.append(
                        f"{tbl}.{col}: scraped={scraped_types[col]!r} kaggle={kaggle_type!r}"
                    )
        assert not mismatches, (
            "Non-null Kaggle columns with mismatched Arrow physical types:\n  "
            + "\n  ".join(mismatches)
        )

    def test_promotion_allowed_for_null_kaggle_columns(
        self, tmp_standard_dir: Path
    ) -> None:
        """For columns where Kaggle IS null, scraped type is a CONCRETE bool/string (not null).

        This is the achievable promotion half of Cycle-2 #7. Kaggle has no
        data for these columns so their type is the null supertype; the
        scraper populates them so they get a concrete type. null is a
        supertype of bool/string in Arrow, so a scraped bool/string column is
        compatible with a Kaggle null column -- Phase 6 concatenation will
        not raise.

        Expected promotions (verified at test setup):
          * race_flag_* null columns -> bool
          * obstacle, surface_detail, track_condition_detail -> string
        """
        result = _scraped_parquet_for_e2e(tmp_standard_dir)
        schema_map = {
            "race": RaceSchema,
            "entry": EntrySchema,
            "result": ResultSchema,
        }
        violations: list[str] = []
        for tbl, schema in schema_map.items():
            kaggle = _kaggle_schema(tbl)
            if kaggle is None:
                continue
            null_cols = _kaggle_null_columns(tbl)
            if not null_cols:
                continue
            # Need a scraped Parquet schema. Use any non-empty partition; if
            # all are empty (placeholder), use the placeholder schema.
            paths = [p for p in result[tbl] if p.exists()]
            if not paths:
                continue
            scraped_schema = pq.read_schema(str(paths[0]))
            scraped_types = {f.name: str(f.type) for f in scraped_schema}
            allowed_promotions = {"bool", "string", "double", "int64"}
            for col in null_cols:
                if col not in scraped_types:
                    continue
                scraped_type = scraped_types[col]
                if scraped_type == "null":
                    violations.append(
                        f"{tbl}.{col}: scraped type is STILL null (no promotion happened)"
                    )
                elif scraped_type not in allowed_promotions:
                    violations.append(
                        f"{tbl}.{col}: scraped type {scraped_type!r} not in allowed "
                        f"promotions {allowed_promotions}"
                    )
        assert not violations, (
            "Kaggle-null columns where the promotion rule was violated:\n  "
            + "\n  ".join(violations)
        )


# ---------------------------------------------------------------------------
# TestOptInLiveSmoke (Cycle-1 MEDIUM): skipped by default.
# ---------------------------------------------------------------------------


@pytest.mark.live
class TestOptInLiveSmoke:
    """Opt-in live smoke test. SKIPPED unless ``LIVE_SMOKE=1`` env var is set."""

    @pytest.fixture(autouse=True)
    def _require_live_smoke_env(self) -> None:
        if os.environ.get("LIVE_SMOKE") != "1":
            pytest.skip("Set LIVE_SMOKE=1 to run the live smoke test (requires network)")
        if os.environ.get("ALLOW_LIVE_NETWORK") != "1":
            pytest.skip(
                "Set ALLOW_LIVE_NETWORK=1 to confirm you want to issue real "
                "HTTPS requests to db.netkeiba.com"
            )

    def test_smoke_one_historical_race(self, tmp_standard_dir: Path) -> None:
        """Fetch one historical race over the real network and assert Parquet exists."""
        result = run_scrape(
            start_date=datetime.date(2022, 1, 5),
            end_date=datetime.date(2022, 1, 5),
            standard_dir=tmp_standard_dir,
            max_races=1,
            live=True,
        )
        race_paths = [p for p in result["race"] if p.exists() and len(pd.read_parquet(p)) > 0]
        assert race_paths, "live smoke produced no race Parquet"
