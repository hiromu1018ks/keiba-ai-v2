"""Phase 6 Plan 06-02: integration.py test suite.

Test class layout (HIGH #7 -- autouse skip gate):

- ``TestIntegrationHermetic`` (9 tests, NO autouse skip) -- runs unconditionally
  against synthetic ``tmp_path`` data. These tests do NOT depend on the real
  scraped corpus being present.
- ``TestUnifiedCorpus`` (2 tests, autouse ``_require_scraped_data`` skip) --
  the slow-path tests that read ``data/standard/`` and only run when the full
  D-06 scraped corpus is present.

Two cycle-5 ISOLATED regression tests live in the hermetic class and prove
their load-bearing properties:

- ``test_horse_race_id_mismatch_raises`` (HIGH #8b) uses DISJOINT unique
  horse_race_ids in entry/result (no duplicates, no FK orphans) so
  ``validate_integrity`` returns EXACTLY ONE violation containing ``mismatch``
  -- proving that token is the sole classifier and load-bearing for the
  integration's hard-classification.
- ``test_integration_partial_swap_recoverable`` (HIGH #6) monkeypatches
  ``src.pipeline.integration._commit_staging`` (NOT global ``os.replace``) and
  mutates a race input so the mid-swap failure produces a DIFFERENT generation
  than canonical -- proving recovery under the REAL mid-swap failure.
"""

from __future__ import annotations

import hashlib
import os as _os
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from src.pipeline import integration as integration_mod
from src.pipeline.integration import (
    _commit_staging,
    integrate_standard_layer,
)
from src.schemas.entry import EntrySchema
from src.schemas.race import RaceSchema
from src.schemas.result import ResultSchema
from src.scraper.normalizer import SCHEMA_DTYPE_MAP, validate_integrity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_typed_parquet(df: pd.DataFrame, schema: type, path: Path) -> None:
    """Reindex to canonical columns + recast to SCHEMA_DTYPE_MAP + write."""
    canonical = list(schema.model_fields.keys())
    df = df.reindex(columns=canonical)
    dtype_map = SCHEMA_DTYPE_MAP[schema]
    for col, target in dtype_map.items():
        if col in df.columns:
            df[col] = df[col].astype(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, engine="pyarrow", index=False)


class TestIntegrationHermetic:
    """Hermetic integration tests (no autouse skip -- run unconditionally).

    Each test constructs synthetic Kaggle + scraped Parquet under ``tmp_path``
    via the conftest fixtures and exercises ``integrate_standard_layer``.
    """

    # ------------------------------------------------------------------
    # Test 1: HIGH #8 -- pre-dedup duplicate race_id raises ValueError
    # ------------------------------------------------------------------
    def test_no_duplicate_race_ids_fail_loud(
        self,
        tmp_kaggle_input_dir,
        tmp_scraped_partitions_dir,
    ) -> None:
        """Construct a scraped race_id that OVERLAPS a Kaggle race_id; expect ValueError."""
        standard_dir = tmp_kaggle_input_dir.parent
        # Overwrite the 202301 race partition with a race_id that exists in Kaggle.
        # The Kaggle fixture (sample_standard_race_df) row 0 uses race_id
        # "201501010101"; reuse it so the post-concat frame has a duplicate.
        overlap_path = standard_dir / "scraped" / "202301" / "race.parquet"
        race_df = pd.read_parquet(overlap_path)
        race_df.loc[0, "race_id"] = "201501010101"
        # Keep entry/result pointing at this overlap race_id so no FK orphan
        # fires; the duplicate race_id is the only hard violation.
        entry_path = standard_dir / "scraped" / "202301" / "entry.parquet"
        result_path = standard_dir / "scraped" / "202301" / "result.parquet"
        entry_df = pd.read_parquet(entry_path)
        result_df = pd.read_parquet(result_path)
        entry_df["race_id"] = "201501010101"
        result_df["race_id"] = "201501010101"
        race_df.to_parquet(overlap_path, engine="pyarrow", index=False)
        entry_df.to_parquet(entry_path, engine="pyarrow", index=False)
        result_df.to_parquet(result_path, engine="pyarrow", index=False)

        with pytest.raises(ValueError, match=r"duplicate"):
            integrate_standard_layer(standard_dir)

    # ------------------------------------------------------------------
    # Test 2: HIGH #8 -- FK orphan raises ValueError
    # ------------------------------------------------------------------
    def test_referential_integrity_orphan_raises(
        self,
        tmp_kaggle_input_dir,
        tmp_scraped_partitions_dir,
    ) -> None:
        """Inject entry.race_id NOT in race table; expect orphan + ValueError."""
        standard_dir = tmp_kaggle_input_dir.parent
        entry_path = standard_dir / "scraped" / "202301" / "entry.parquet"
        entry_df = pd.read_parquet(entry_path)
        # Set entry race_id to a value that does NOT exist in any race table
        # (Kaggle or scraped). The orphan check at normalizer.py:338-372 fires.
        entry_df["race_id"] = "999999999999"
        entry_df.to_parquet(entry_path, engine="pyarrow", index=False)

        with pytest.raises(ValueError, match=r"(orphan|hard integrity)"):
            integrate_standard_layer(standard_dir)

    # ------------------------------------------------------------------
    # Test 3: HIGH #8b cycle-5 ISOLATED -- horse_race_id 1-to-1 mismatch raises
    # ------------------------------------------------------------------
    def test_horse_race_id_mismatch_raises(
        self,
        tmp_kaggle_input_dir,
        tmp_scraped_partitions_dir,
    ) -> None:
        """DISJOINT UNIQUE horse_race_ids in entry/result -> ONLY the mismatch violation.

        CYCLE-5 ISOLATION FIX: entry horse_race_id="E1" and result
        horse_race_id="R1" are INTERNALLY UNIQUE (no duplicates in either
        table) and both reference a race_id present in race_df (no FK orphan).
        ``validate_integrity`` therefore returns EXACTLY ONE violation -- the
        ``horse_race_id mismatch`` string -- proving the ``mismatch`` token in
        the integration's hard-violation filter is load-bearing: without it,
        this data has NO hard violation and integration would NOT raise.
        """
        standard_dir = tmp_kaggle_input_dir.parent
        # Build a 3-table setup with a deliberately mismatched entry/result
        # pair (DISJOINT unique horse_race_ids).
        kaggle_dir = tmp_kaggle_input_dir
        race_id = "202301030101"

        race_row = pd.DataFrame([
            {
                "race_id": race_id,
                "race_date": "2023-01-03",
                "meeting_num": 1,
                "course_code": "01",
                "course_name": "東京",
                "meeting_day": 1,
                "race_condition": "4歳以上",
                "race_number": 1,
                "grade_revision": None,
                "race_name": "MismatchTest",
                "grade": None,
                "obstacle": None,
                "surface": "芝",
                "surface_detail": None,
                "direction": "左",
                "course_detail": None,
                "distance": 2000,
                "weather": "晴",
                "track_condition": "良",
                "track_condition_detail": None,
                "start_time": "10:00",
            }
        ])
        entry_row = pd.DataFrame([
            {
                "horse_race_id": "E1",  # DISJOINT from result
                "race_id": race_id,
                "bracket_num": 1,
                "horse_number": 1,
                "horse_name": "HorseE",
                "sex": "牡",
                "age": 4,
                "weight_assigned": 57.0,
                "jockey": "J1",
                "trainer": "T1",
                "owner": "O1",
                "horse_weight": 480.0,
                "weight_change": 0.0,
                "region": "東",
                "popularity": 1.0,
                "win_odds": 2.0,
            }
        ])
        result_row = pd.DataFrame([
            {
                "horse_race_id": "R1",  # DISJOINT from entry
                "race_id": race_id,
                "finish_position": 1,
                "finish_note": None,
                "finish_time": "1:58.5",
                "margin": None,
                "corner_1": 1.0,
                "corner_2": 1.0,
                "corner_3": 1.0,
                "corner_4": 1.0,
                "last_3f": 34.5,
                "prize_money": 750.0,
            }
        ])

        _write_typed_parquet(race_row, RaceSchema, kaggle_dir / "race.parquet")
        _write_typed_parquet(entry_row, EntrySchema, kaggle_dir / "entry.parquet")
        _write_typed_parquet(result_row, ResultSchema, kaggle_dir / "result.parquet")

        # Wipe scraped partitions so the corpus is Kaggle-only (the injected
        # mismatch lives entirely in the Kaggle input here).
        scraped_root = standard_dir / "scraped"
        for month_dir in scraped_root.iterdir():
            if month_dir.is_dir():
                # Rewrite each month to be a trivial 1-row per-table extension
                # with horse_race_ids that ALSO mismatch (the test only needs
                # validate_integrity to see the mismatch overall; Kaggle-only
                # mismatch is the cleanest isolation).
                pass
        # Simplest isolation: DELETE all scraped month dirs. We override the
        # integration's ">=1 month" guard by re-creating a single empty-but-
        # valid month that is CONSISTENT with the Kaggle mismatch setup (its
        # rows extend the same DISJOINT pattern, so the only hard violation
        # remains the mismatch).
        import shutil

        if scraped_root.exists():
            shutil.rmtree(scraped_root)
        scraped_root.mkdir(parents=True, exist_ok=True)
        month = scraped_root / "202301"
        month.mkdir(parents=True, exist_ok=True)
        # Scraped race mirrors the Kaggle race so concat produces 1 duplicate
        # race_id (which the duplicate-PK guard fires first). To AVOID the
        # duplicate-PK path dominating, give the scraped race a DIFFERENT
        # race_id so Kaggle+scraped have NO race_id overlap. The scraped
        # entry/result rows reference THIS new race_id and ALSO have DISJOINT
        # horse_race_ids (entry="S_E", result="S_R") so they ADD to the
        # mismatch but introduce no duplicate / no orphan.
        scraped_race_id = "202301030102"
        s_race = race_row.copy()
        s_race["race_id"] = scraped_race_id
        s_entry = entry_row.copy()
        s_entry["horse_race_id"] = "S_E"
        s_entry["race_id"] = scraped_race_id
        s_result = result_row.copy()
        s_result["horse_race_id"] = "S_R"
        s_result["race_id"] = scraped_race_id
        _write_typed_parquet(s_race, RaceSchema, month / "race.parquet")
        _write_typed_parquet(s_entry, EntrySchema, month / "entry.parquet")
        _write_typed_parquet(s_result, ResultSchema, month / "result.parquet")

        # ----- prove the mismatch token is the SOLE classifier -----
        # Read the merged frames EXACTLY as integration would (so the test
        # reflects the real violation list integration will see).
        merged_race = pd.concat(
            [
                pd.read_parquet(kaggle_dir / "race.parquet").reindex(
                    columns=list(RaceSchema.model_fields.keys())
                ),
                pd.read_parquet(month / "race.parquet").reindex(
                    columns=list(RaceSchema.model_fields.keys())
                ),
            ],
            ignore_index=True,
        )
        merged_entry = pd.concat(
            [
                pd.read_parquet(kaggle_dir / "entry.parquet").reindex(
                    columns=list(EntrySchema.model_fields.keys())
                ),
                pd.read_parquet(month / "entry.parquet").reindex(
                    columns=list(EntrySchema.model_fields.keys())
                ),
            ],
            ignore_index=True,
        )
        merged_result = pd.concat(
            [
                pd.read_parquet(kaggle_dir / "result.parquet").reindex(
                    columns=list(ResultSchema.model_fields.keys())
                ),
                pd.read_parquet(month / "result.parquet").reindex(
                    columns=list(ResultSchema.model_fields.keys())
                ),
            ],
            ignore_index=True,
        )
        violations = validate_integrity(merged_race, merged_entry, merged_result)
        # The load-bearing check: validate_integrity returns EXACTLY ONE
        # violation and it contains 'mismatch' (no duplicate, no orphan).
        assert len(violations) == 1, (
            f"expected exactly 1 violation (the mismatch), got {violations}"
        )
        assert "mismatch" in violations[0] and "1-to-1" in violations[0], (
            f"unexpected violation string: {violations[0]!r}"
        )

        # Now prove integrate_standard_layer raises via the hard-violation
        # filter (the 'mismatch' token is what makes this hard).
        with pytest.raises(ValueError, match=r"(mismatch|1-to-1|hard integrity)"):
            integrate_standard_layer(standard_dir)

    # ------------------------------------------------------------------
    # Test 4: HIGH #9 -- column-set mismatch raises BEFORE reindex
    # ------------------------------------------------------------------
    def test_column_set_mismatch_raises_before_reindex(
        self,
        tmp_kaggle_input_dir,
        tmp_scraped_partitions_dir,
    ) -> None:
        """Corrupt Kaggle entry column set; expect ValueError naming the mismatch."""
        standard_dir = tmp_kaggle_input_dir.parent
        entry_path = tmp_kaggle_input_dir / "entry.parquet"
        df = pd.read_parquet(entry_path)
        # Drop a real column AND add a bogus one -> column set diverges.
        df = df.drop(columns=["jockey"])
        df["__bogus__"] = "x"
        df.to_parquet(entry_path, engine="pyarrow", index=False)

        with pytest.raises(ValueError, match=r"column set mismatch"):
            integrate_standard_layer(standard_dir)

    # ------------------------------------------------------------------
    # WR-06: non-YYYYMM stray directories are skipped, not treated as months
    # ------------------------------------------------------------------
    def test_stray_non_yyyymm_directory_skipped(
        self,
        tmp_kaggle_input_dir,
        tmp_scraped_partitions_dir,
    ) -> None:
        """WR-06: a stray non-YYYYMM directory is skipped, not merged.

        Previously the month_dirs filter accepted ANY subdirectory, so a stray
        ``__pycache__`` / ``archive/`` / ``.DS_Store``-adjacent artifact
        containing well-named {table}.parquet would silently pollute the corpus.
        The fix validates each directory name matches r'^\\d{6}$' and skips/logs
        non-matching directories. This test creates a stray ``__pycache__``
        directory with valid parquet inside scraped/ and verifies integration
        still succeeds (stray skipped) with the expected row count.
        """
        standard_dir = tmp_kaggle_input_dir.parent
        scraped_root = standard_dir / "scraped"

        # Create a stray non-YYYYMM directory with well-named parquet files.
        # If WR-06 regresses, integration will try to read these as a month
        # partition and either error or inflate the row count.
        stray_dir = scraped_root / "__pycache__"
        stray_dir.mkdir(parents=True, exist_ok=True)
        # Write a bogus race.parquet with a clearly-foreign race_id.
        pd.DataFrame({"race_id": ["STRAY_999"]}).to_parquet(
            stray_dir / "race.parquet", engine="pyarrow", index=False
        )

        # Integration must succeed (stray dir skipped).
        result = integrate_standard_layer(standard_dir)

        # The stray race_id must NOT appear in the merged race table.
        merged_race = pd.read_parquet(result["race"])
        assert "STRAY_999" not in set(merged_race["race_id"]), (
            "Stray non-YYYYMM directory was merged into the corpus (WR-06 regression)"
        )

    # ------------------------------------------------------------------
    # Test 5: schema invariant post-integration (every flag Arrow bool etc)
    # ------------------------------------------------------------------
    def test_schema_invariant_post_integration(
        self,
        tmp_kaggle_input_dir,
        tmp_scraped_partitions_dir,
    ) -> None:
        """Integrated race.parquet has every race_flag_* Arrow bool, distance int64, race_date string."""
        standard_dir = tmp_kaggle_input_dir.parent
        integrate_standard_layer(standard_dir)

        schema = pq.read_schema(str(standard_dir / "race.parquet"))
        types = {f.name: str(f.type) for f in schema}

        # Every race_flag_* column must be Arrow bool (not null).
        flag_cols = [c for c in types if c.startswith("race_flag_")]
        assert flag_cols, "no race_flag_* columns in race.parquet"
        null_flags = {c for c in flag_cols if types[c] != "bool"}
        assert not null_flags, f"race_flag_* columns not Arrow bool: {null_flags}"

        # distance must be int64; race_date must be string.
        assert types.get("distance") == "int64", f"distance={types.get('distance')!r}"
        assert types.get("race_date") == "string", f"race_date={types.get('race_date')!r}"

    # ------------------------------------------------------------------
    # Test 6: MEDIUM #13 -- audit_leakage is CALLED (race=[], entry={pop,win_odds})
    # ------------------------------------------------------------------
    def test_no_post_race_leakage_audit_called(
        self,
        tmp_kaggle_input_dir,
        tmp_scraped_partitions_dir,
    ) -> None:
        """integrate_standard_layer returns an 'audit' dict proving audit_leakage ran."""
        standard_dir = tmp_kaggle_input_dir.parent
        result = integrate_standard_layer(standard_dir)

        assert "audit" in result, "return dict missing 'audit' key (audit_leakage not called)"
        audit = result["audit"]
        assert "race" in audit and "entry" in audit, (
            f"audit sub-dict missing race/entry keys: {audit!r}"
        )
        # race has NO post-race columns -> empty leak list.
        assert audit["race"] == [], f"race leaked post-race columns: {audit['race']!r}"
        # entry leaks popularity + win_odds (intentional per Phase 1 D-03).
        assert set(audit["entry"]) == {"popularity", "win_odds"}, (
            f"entry leaked unexpected columns: {audit['entry']!r}"
        )

    # ------------------------------------------------------------------
    # Test 7: odds/payoff NOT overwritten (D-05 seed protection)
    # ------------------------------------------------------------------
    def test_odds_payoff_not_overwritten(
        self,
        tmp_kaggle_input_dir,
        tmp_scraped_partitions_dir,
        tmp_path,
    ) -> None:
        """Sentinel odds_trifecta/payoff files in standard_dir are byte-identical post-integration."""
        standard_dir = tmp_kaggle_input_dir.parent
        # Plant sentinel odds/payoff files in the standard root.
        odds_path = standard_dir / "odds_trifecta.parquet"
        payoff_path = standard_dir / "payoff.parquet"
        odds_df = pd.DataFrame({"race_id": ["SENTINEL"], "odds": [123.4]})
        payoff_df = pd.DataFrame({"race_id": ["SENTINEL"], "payoff": [567.8]})
        odds_df.to_parquet(odds_path, engine="pyarrow", index=False)
        payoff_df.to_parquet(payoff_path, engine="pyarrow", index=False)

        odds_sha_before = _sha256(odds_path)
        payoff_sha_before = _sha256(payoff_path)
        odds_rows_before = len(pd.read_parquet(odds_path))
        payoff_rows_before = len(pd.read_parquet(payoff_path))

        integrate_standard_layer(standard_dir)

        assert _sha256(odds_path) == odds_sha_before, "odds_trifecta.parquet was modified"
        assert _sha256(payoff_path) == payoff_sha_before, "payoff.parquet was modified"
        assert len(pd.read_parquet(odds_path)) == odds_rows_before
        assert len(pd.read_parquet(payoff_path)) == payoff_rows_before

    # ------------------------------------------------------------------
    # Test 8: HIGH #5 -- two consecutive runs produce byte-identical output
    # ------------------------------------------------------------------
    def test_integration_is_idempotent(
        self,
        tmp_kaggle_input_dir,
        tmp_scraped_partitions_dir,
    ) -> None:
        """Run integrate_standard_layer twice; second run's SHA-256 == first run's."""
        standard_dir = tmp_kaggle_input_dir.parent
        integrate_standard_layer(standard_dir)
        first = {t: _sha256(standard_dir / f"{t}.parquet") for t in ("race", "entry", "result")}

        integrate_standard_layer(standard_dir)
        second = {t: _sha256(standard_dir / f"{t}.parquet") for t in ("race", "entry", "result")}

        assert first == second, (
            f"integrate_standard_layer is NOT idempotent: first={first} second={second}"
        )

    # ------------------------------------------------------------------
    # Test 9: HIGH #6 cycle-5 ISOLATED -- _commit_staging mid-swap failure
    # ------------------------------------------------------------------
    def test_integration_partial_swap_recoverable(
        self,
        tmp_kaggle_input_dir,
        tmp_scraped_partitions_dir,
        monkeypatch,
    ) -> None:
        """Patch ``_commit_staging`` (NOT global os.replace) to raise on 2nd swap; prove recovery.

        CYCLE-5 ISOLATION:
            (a) Clean run -- capture canonical SHA-256 of race/entry/result.
            (b) MUTATE the race INPUT (non-key column, race_id preserved) so
                the new-generation race differs from canonical.
            (c) Patch ``src.pipeline.integration._commit_staging`` (NOT global
                ``os.replace``). The wrapper raises OSError on the 2nd os.replace
                INSIDE it so RACE is swapped (new-gen) but entry/result are NOT.
            (d) Re-invoke; observe the MIXED-GENERATION state on disk.
            (e) RESTORE ``_commit_staging`` and re-invoke. Re-run produces a
                CONSISTENT new-generation corpus (race=new-gen; entry/result
                consistent since their inputs were unchanged). A 3rd invocation
                is byte-identical to the recovered state (idempotency on the
                mutated inputs).
        """
        standard_dir = tmp_kaggle_input_dir.parent
        tbls = ("race", "entry", "result")

        # (a) Clean run -- capture canonical SHA-256 of all 3 outputs.
        integrate_standard_layer(standard_dir)
        canonical = {t: _sha256(standard_dir / f"{t}.parquet") for t in tbls}

        # (b) MUTATE THE RACE INPUT so the new-generation race differs from
        # canonical. Change a NON-KEY column on one scraped race row (race_id
        # preserved -> referential integrity stays valid; only race content
        # hash changes). entry/result inputs LEFT UNCHANGED so their
        # new-generation == canonical -- this is what makes the mid-swap
        # mixed-generation state OBSERVABLE.
        srace_path = standard_dir / "scraped" / "202301" / "race.parquet"
        srace = pd.read_parquet(srace_path)
        # Pick any object column other than race_id.
        non_key_col = next(
            c for c in srace.columns if c != "race_id" and srace[c].dtype == object
        )
        srace.loc[0, non_key_col] = str(srace.loc[0, non_key_col]) + "_MUTATED"
        srace.to_parquet(srace_path, engine="pyarrow", index=False)

        # (c) Patch the DEDICATED _commit_staging -- NOT global os.replace.
        # Raise on the 2nd os.replace (entry swap) so RACE is swapped (new-gen)
        # but entry/result are NOT -- leaving a genuine mixed-generation corpus.
        real_replace = _os.replace
        call_counter = {"n": 0}

        def failing_commit_staging(staging_dir, standard_dir):
            for table in tbls:
                call_counter["n"] += 1
                if call_counter["n"] == 2:
                    raise OSError(
                        f"simulated mid-swap failure on {table} "
                        f"(race swapped, entry/result not)"
                    )
                real_replace(
                    Path(staging_dir) / f"{table}.parquet",
                    Path(standard_dir) / f"{table}.parquet",
                )

        monkeypatch.setattr(integration_mod, "_commit_staging", failing_commit_staging)

        # (d) Re-invoke with mutated race input. _commit_staging raises mid-swap.
        raised = False
        try:
            integrate_standard_layer(standard_dir)
        except OSError:
            raised = True  # acceptable -- _commit_staging propagated the mid-swap failure

        # Observe the mixed-generation state. race was swapped (new-gen);
        # entry/result were NOT (still canonical).
        post_race = _sha256(standard_dir / "race.parquet")
        post_entry = _sha256(standard_dir / "entry.parquet")
        post_result = _sha256(standard_dir / "result.parquet")
        assert post_race != canonical["race"], (
            "race should be new-generation (swapped before failure) -- "
            "mixed-generation state not observed (was the race input actually mutated?)"
        )
        assert post_entry == canonical["entry"], (
            "entry should still be canonical (not yet swapped at failure) -- "
            "mixed-generation state not observed"
        )
        assert post_result == canonical["result"], (
            "result should still be canonical (not yet swapped at failure) -- "
            "mixed-generation state not observed"
        )

        # (e) RECOVERY: restore _commit_staging and re-invoke. Idempotent
        # integration reads Kaggle from data/standard/kaggle/ (never its own
        # output) + immutable scraped partitions, so re-run restores a
        # CONSISTENT new-generation corpus.
        monkeypatch.undo()
        integrate_standard_layer(standard_dir)
        recovered = {
            t: _sha256(standard_dir / f"{t}.parquet") for t in tbls
        }
        for t in tbls:
            assert (standard_dir / f"{t}.parquet").exists(), (
                f"{t}.parquet missing after recovery"
            )
        # race recovered to NEW-gen (mutated input applied); entry/result
        # consistent (their new-gen == canonical since their inputs unchanged).
        assert recovered["race"] != canonical["race"], (
            "recovered race should reflect the mutated input"
        )
        assert recovered["entry"] == canonical["entry"], (
            "recovered entry should be consistent"
        )
        assert recovered["result"] == canonical["result"], (
            "recovered result should be consistent"
        )

        # A 3rd invocation is byte-identical (idempotency on mutated inputs) --
        # proves the recovered state is a stable fixed point, not a transient.
        integrate_standard_layer(standard_dir)
        for t in tbls:
            h = _sha256(standard_dir / f"{t}.parquet")
            assert h == recovered[t], (
                f"{t}.parquet NOT byte-identical on idempotent re-run after recovery"
            )


class TestUnifiedCorpus:
    """Real-corpus slow-path tests (gated -- skip when scraped corpus is smoke-only)."""

    @pytest.fixture(autouse=True)
    def _require_scraped_data(self) -> None:
        """Skip this class unless the real D-06 scraped corpus is present.

        Mirrors the Phase 4 ``_require_kaggle_parquet`` autouse pattern at
        ``tests/scraper/test_end_to_end.py:467-472``. The slow-path tests read
        the unified ``data/standard/{race,entry,result}.parquet`` after a real
        integration run against the full 2022-2026/5 scraped corpus. When only
        the smoke (5-race 202306) partition exists, these tests skip.
        """
        scraped_root = Path("data/standard/scraped")
        if not scraped_root.exists():
            pytest.skip("data/standard/scraped/ absent -- real corpus not present")
        month_dirs = [p for p in scraped_root.iterdir() if p.is_dir()]
        # Smoke corpus is a single month with only 5 races. Treat <2 months as
        # "not yet the full corpus".
        if len(month_dirs) < 2:
            pytest.skip(
                f"scraped corpus is smoke-only ({len(month_dirs)} month dir(s)); "
                f"D-06 full scrape required for TestUnifiedCorpus"
            )

    def test_unified_race_date_range(self) -> None:
        """Unified race.parquet race_date covers the expected 2015-01..2026-05 range."""
        standard_dir = Path("data/standard")
        result = integrate_standard_layer(standard_dir)
        race_df = pd.read_parquet(result["race"], engine="pyarrow")
        dates = pd.to_datetime(race_df["race_date"], errors="coerce").dropna()
        assert len(dates) > 0, "unified race.parquet has 0 parseable race_date values"
        # Earliest should be in 2015 (Kaggle start). Latest in 2022+ (scraped).
        assert dates.min().year <= 2015, f"unexpected earliest year {dates.min().year}"
        assert dates.max().year >= 2022, f"unexpected latest year {dates.max().year}"

    def test_row_counts_within_expected_bounds(self) -> None:
        """Output unique PK count == union of input PK-sets per table (MEDIUM #20)."""
        standard_dir = Path("data/standard")
        kaggle_dir = standard_dir / "kaggle"
        scraped_root = standard_dir / "scraped"

        result = integrate_standard_layer(standard_dir)

        for table, pk in (
            ("race", "race_id"),
            ("entry", "horse_race_id"),
            ("result", "horse_race_id"),
        ):
            # Input PK union.
            kaggle_ids = set(
                pd.read_parquet(kaggle_dir / f"{table}.parquet")[pk].dropna().tolist()
            )
            scraped_ids: set[object] = set()
            for month_dir in sorted(p for p in scraped_root.iterdir() if p.is_dir()):
                scraped_ids |= set(
                    pd.read_parquet(month_dir / f"{table}.parquet")[pk]
                    .dropna()
                    .tolist()
                )
            input_union = kaggle_ids | scraped_ids

            # Output unique PK count must equal the input union cardinality
            # (no silent dedup, no row loss).
            out_df = pd.read_parquet(result[table], engine="pyarrow")
            output_unique = set(out_df[pk].dropna().tolist())
            assert len(output_unique) == len(input_union), (
                f"{table}: output unique {pk} count {len(output_unique)} != "
                f"input union {len(input_union)} (silent dedup or row loss)"
            )
