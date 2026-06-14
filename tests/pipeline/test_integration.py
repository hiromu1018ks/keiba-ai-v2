"""Phase 6 Plan 06-02: integration.py test suite.

Test class layout (HIGH #7 -- autouse skip gate):

- ``TestIntegrationHermetic`` (9 tests, NO autouse skip) -- runs unconditionally
  against synthetic ``tmp_path`` data. These tests do NOT depend on the real
  scraped corpus being present.
- ``TestUnifiedCorpus`` (2 tests, autouse ``_require_scraped_data`` skip) --
  the slow-path tests that read ``data/standard/`` and only run when the full
  D-06 scraped corpus is present.

Task 1 (RED) leaves every test as a ``pytest.skip`` stub. Task 2 (GREEN)
replaces each stub with the real assertion.
"""

from __future__ import annotations

import pytest

# Try to import the entry point; the module does not exist yet during Task 1
# (RED). Collection must still succeed so --collect-only can enumerate the
# 11 expected test items.
try:  # pragma: no cover - import guard
    from src.pipeline.integration import integrate_standard_layer  # type: ignore

    INTEGRATION_AVAILABLE = True
except ImportError:  # pragma: no cover - import guard
    integrate_standard_layer = None  # type: ignore[assignment]
    INTEGRATION_AVAILABLE = False


_STUB_REASON = "integration.py not yet implemented -- Wave 0 stub"


class TestIntegrationHermetic:
    """Hermetic integration tests (no autouse skip -- run unconditionally).

    Each test constructs synthetic Kaggle + scraped Parquet under ``tmp_path``
    via the conftest fixtures and exercises ``integrate_standard_layer``. The
    cycle-5 ISOLATED regression tests (``test_horse_race_id_mismatch_raises``,
    ``test_integration_partial_swap_recoverable``) live here.
    """

    def test_no_duplicate_race_ids_fail_loud(
        self,
        tmp_kaggle_input_dir,
        tmp_scraped_partitions_dir,
    ) -> None:
        pytest.skip(_STUB_REASON)

    def test_referential_integrity_orphan_raises(
        self,
        tmp_kaggle_input_dir,
        tmp_scraped_partitions_dir,
    ) -> None:
        pytest.skip(_STUB_REASON)

    def test_horse_race_id_mismatch_raises(
        self,
        tmp_kaggle_input_dir,
        tmp_scraped_partitions_dir,
    ) -> None:
        """HIGH #8b cycle-5 ISOLATED: DISJOINT unique horse_race_ids in entry/result."""
        pytest.skip(_STUB_REASON)

    def test_column_set_mismatch_raises_before_reindex(
        self,
        tmp_kaggle_input_dir,
        tmp_scraped_partitions_dir,
    ) -> None:
        pytest.skip(_STUB_REASON)

    def test_schema_invariant_post_integration(
        self,
        tmp_kaggle_input_dir,
        tmp_scraped_partitions_dir,
    ) -> None:
        pytest.skip(_STUB_REASON)

    def test_no_post_race_leakage_audit_called(
        self,
        tmp_kaggle_input_dir,
        tmp_scraped_partitions_dir,
    ) -> None:
        pytest.skip(_STUB_REASON)

    def test_odds_payoff_not_overwritten(
        self,
        tmp_kaggle_input_dir,
        tmp_scraped_partitions_dir,
        tmp_path,
    ) -> None:
        pytest.skip(_STUB_REASON)

    def test_integration_is_idempotent(
        self,
        tmp_kaggle_input_dir,
        tmp_scraped_partitions_dir,
    ) -> None:
        pytest.skip(_STUB_REASON)

    def test_integration_partial_swap_recoverable(
        self,
        tmp_kaggle_input_dir,
        tmp_scraped_partitions_dir,
        monkeypatch,
    ) -> None:
        """HIGH #6 cycle-5 ISOLATED: patch ``_commit_staging`` (NOT global os.replace)."""
        pytest.skip(_STUB_REASON)


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
        from pathlib import Path

        scraped_root = Path("data/standard/scraped")
        if not scraped_root.exists():
            pytest.skip("data/standard/scraped/ absent -- real corpus not present")
        month_dirs = [p for p in scraped_root.iterdir() if p.is_dir()]
        # Smoke corpus is a single month with only 5 races. Treat <2 months OR
        # the known smoke-only month as "not yet the full corpus".
        if len(month_dirs) < 2:
            pytest.skip(
                f"scraped corpus is smoke-only ({len(month_dirs)} month dir(s)); "
                f"D-06 full scrape required for TestUnifiedCorpus"
            )

    def test_unified_race_date_range(self) -> None:
        pytest.skip(_STUB_REASON)

    def test_row_counts_within_expected_bounds(self) -> None:
        pytest.skip(_STUB_REASON)
