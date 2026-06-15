"""MODA-01 trainer tests (07-04 GREEN).

Covers MODA-01 (LightGBM fold training + OOF collection + two-stage final
retrain), Pitfall #1 (early_stopping callback API in LightGBM 4.x, NOT the
legacy ``early_stopping_rounds`` kwarg), D-15 (final model = single full
retrain on ALL train-window rows), and the four Codex HIGH fixes (#2 OOF =
val chunks only, #3 module-level import, #5 feature_columns explicit arg,
#6 two-stage full retrain) plus Cycle-2 HIGH #1 (dates=df["race_date"]
forwarded to splitter).

Hermetic: builds a small (~20 rows, 6 races, 2018-2024) feature frame from
the shared ``sample_feature_df`` fixture (derives horse_race_id locally), and
shrinks the model config via the ``ml_config`` fixture so each LightGBM fit
finishes in <1s.
"""

from __future__ import annotations

import ast
import inspect

import lightgbm as lgb
import numpy as np
import pandas as pd
import pytest
from sklearn.model_selection import BaseCrossValidator

from src.ml.group_timeseries_split import GroupTimeSeriesSplit
from src.ml.trainer import (
    collect_oof_predictions,
    train_final_model,
    train_fold_model,
)

# Feature columns the trainer should consume (numeric + categorical subset
# that exists on sample_feature_df). Must EXCLUDE race_id / race_date /
# horse_number / target_top3 / exclude_from_training (identifiers + targets).
_TRAINER_FEATURE_COLUMNS = [
    "distance",
    "race_number",
    "field_size",
    "bracket_num",
    "horse_number",
    "age",
    "weight_assigned",
    "horse_weight",
    "weight_change",
    "prev_1_finish_position",
    "prev_1_last_3f",
    "prev_1_corner_4",
    "prev_1_finish_time_zscore",
    "prev_1_margin_numeric",
    "prev3_finish_position_mean",
    "prev5_last_3f_mean",
    "jockey_rolling_top3_rate",
    "jockey_rolling_win_rate",
    "jockey_rolling_rides",
    "trainer_rolling_top3_rate",
    "trainer_rolling_win_rate",
    "trainer_rolling_rides",
    "is_debut",
    # Categoricals (LightGBM native, D-16) — MUST be category dtype on the df
    "jockey",
    "trainer",
]


def _derive_horse_race_id(df: pd.DataFrame) -> pd.DataFrame:
    """Add the D-15 horse_race_id column (no underscore, Pitfall #2 authority)."""
    out = df.copy()
    out["horse_race_id"] = (
        out["race_id"].astype(str)
        + out["horse_number"].astype(int).astype(str).str.zfill(2)
    )
    return out


def _const_str(node) -> str | None:
    """Return the string literal value of an AST Constant/Str node, else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _ensure_race_date_datetime(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce race_date to datetime (GroupTimeSeriesSplit requires it)."""
    out = df.copy()
    out["race_date"] = pd.to_datetime(out["race_date"])
    return out


class _SpySplitter(BaseCrossValidator):
    """Records every split() call's kwargs so the test can assert that
    ``dates=df["race_date"]`` was forwarded (Cycle-2 HIGH #1)."""

    def __init__(self, n_splits: int = 3) -> None:
        self.n_splits = n_splits
        self.split_calls: list[dict] = []
        self._inner = GroupTimeSeriesSplit(n_splits=n_splits)

    def get_n_splits(self, X=None, y=None, groups=None) -> int:  # noqa: D401, ANN001
        return self.n_splits

    def split(self, X, y=None, groups=None, dates=None):  # noqa: ANN001
        # Record the call signature verbatim.
        self.split_calls.append(
            {"X_shape": getattr(X, "shape", None), "groups": groups, "dates": dates}
        )
        # Delegate to the real splitter so the OOF pipeline still runs.
        yield from self._inner.split(X, y, groups=groups, dates=dates)


class TestTrainer:
    """Tests for src/ml/trainer.py (MODA-01 / Pitfall #1 / Codex HIGH #2/#5/#6
    / Cycle-2 HIGH #1)."""

    def test_train_fold_model_returns_classifier(
        self,
        sample_feature_df: pd.DataFrame,
        ml_config: dict,
    ) -> None:
        """Test 1: MODA-01 — train_fold_model returns a fitted LGBMClassifier
        with best_iteration_ populated (callback API evidence, Pitfall #1).

        D-13 sensible defaults + early stopping. clf.best_iteration_ is None
        iff the early stopping callback did NOT run (Pitfall #1 signature).
        """
        df = _ensure_race_date_datetime(_derive_horse_race_id(sample_feature_df))
        X = df[_TRAINER_FEATURE_COLUMNS]
        y = df["target_top3"]
        # naive 50/50 row split (NOT time-safe; this test only checks the
        # return type + best_iteration_, time-safety is tested via OOF path).
        mid = len(df) // 2
        clf = train_fold_model(
            X.iloc[:mid], y.iloc[:mid], X.iloc[mid:], y.iloc[mid:], ml_config
        )
        assert isinstance(clf, lgb.LGBMClassifier)
        assert clf.best_iteration_ is not None
        assert isinstance(clf.best_iteration_, (int, np.integer))
        # predict_proba returns (n, 2) binary shape
        proba = clf.predict_proba(X)
        assert proba.shape == (len(df), 2)

    def test_early_stopping_fires(
        self,
        sample_feature_df: pd.DataFrame,
        ml_config: dict,
    ) -> None:
        """Test 2: Pitfall #1 — early_stopping callback triggers before
        n_estimators.

        Determinism hardened per Codex Cycle-5 carry-over + the in-suite
        observation that sample_feature_df's target_top3 is trivially
        separable (it is derived from horse_number, producing a near-zero
        val logloss that monotonically decreases and never triggers
        stopping). We build a NOISY synthetic frame where the label is a
        random coin flip uncorrelated with the single feature, so the val
        logloss is non-monotonic and early stopping fires well before
        n_estimators. ``random_state`` is seeded for reproducibility.

        Meta-check: the source of train_fold_model MUST NOT pass the legacy
        ``early_stopping_rounds`` kwarg to fit() (Pitfall #1 grep guard).
        """
        rng = np.random.RandomState(42)
        n = 300
        # Single noise feature; label is pure noise (coin flip) so the model
        # cannot reduce val logloss monotonically — early stopping fires.
        X = pd.DataFrame({"noise": rng.randn(n)})
        y = pd.Series(rng.randint(0, 2, n), name="target_top3")
        mid = n // 2
        # Use a config that should reliably trigger early stopping:
        # n_estimators=200, stopping_rounds=10, num_leaves=31, lr=0.1.
        config = {
            "seed": 42,
            "model": {
                "objective": "binary",
                "num_leaves": 31,
                "learning_rate": 0.1,
                "min_data_in_leaf": 5,
                "n_estimators": 200,
                "feature_fraction": 1.0,
                "bagging_fraction": 1.0,
                "bagging_freq": 0,
                "max_depth": -1,
                "verbose": -1,
            },
            "early_stopping": {
                "stopping_rounds": 10,
                "verbose": False,
                "first_metric_only": True,
            },
        }
        clf = train_fold_model(
            X.iloc[:mid], y.iloc[:mid], X.iloc[mid:], y.iloc[mid:], config
        )
        n_estimators = config["model"]["n_estimators"]
        assert clf.best_iteration_ is not None
        assert clf.best_iteration_ < n_estimators, (
            f"early stopping did not fire: best_iteration_="
            f"{clf.best_iteration_} >= n_estimators={n_estimators} (Pitfall #1)"
        )
        # Pitfall #1 meta-guard: no `early_stopping_rounds=` KEYWORD ARGUMENT
        # is passed in any executable call inside train_fold_model. We
        # inspect the AST (not raw source) so that docstrings / comments that
        # merely mention the legacy kwarg name do not false-positive.
        tree = ast.parse(inspect.getsource(train_fold_model))
        offending = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "early_stopping_rounds":
                        offending.append(node.lineno)
        assert not offending, (
            f"Pitfall #1 violation: train_fold_model passes "
            f"early_stopping_rounds= as a kwarg at line(s) {offending} "
            "(LightGBM 4.x removed it from fit())"
        )
        # And MUST use the callback API (string check is fine — the callback
        # call is executable code, not a docstring phrase).
        src = inspect.getsource(train_fold_model)
        assert "lgb.early_stopping" in src, (
            "train_fold_model must use lgb.early_stopping(...) callback "
            "(Pitfall #1 — only 4.x path)"
        )

    def test_collect_oof_predictions(
        self,
        sample_feature_df: pd.DataFrame,
        ml_config: dict,
    ) -> None:
        """Test 3: MODA-01 + Codex HIGH #2 — OOF predictions cover validation
        chunks ONLY (warm-up chunk 0 excluded). Returns a DataFrame with
        columns {race_id, horse_race_id, p_top3_raw, target_top3, fold} and
        ``len(oof) < len(df)`` (load-bearing invariant, NOT a bug).

        sample_feature_df has 6 unique race_dates. With n_splits=3 the
        splitter builds 4 date-block chunks (chunk 0 warm-up + 3 val chunks),
        so OOF rows = sum of chunks 1..3 < total rows.
        """
        df = _ensure_race_date_datetime(_derive_horse_race_id(sample_feature_df))
        # Use n_splits=3 so we have 6 unique dates / 4 chunks (base=1, rem=2).
        # Override config cv.n_splits to match the injected splitter.
        config = dict(ml_config)
        config["cv"] = dict(ml_config["cv"])
        config["cv"]["n_splits"] = 3
        splitter = GroupTimeSeriesSplit(n_splits=3)

        oof_df = collect_oof_predictions(
            df, splitter, config, feature_columns=_TRAINER_FEATURE_COLUMNS
        )

        # Schema contract (D-15 OOF parquet).
        expected_cols = {"race_id", "horse_race_id", "p_top3_raw", "target_top3", "fold"}
        assert set(oof_df.columns) == expected_cols, (
            f"OOF columns mismatch: got {set(oof_df.columns)}, want {expected_cols}"
        )
        # Codex HIGH #2: OOF rows = val chunks only (warm-up chunk 0 excluded).
        assert len(oof_df) < len(df), (
            f"Codex HIGH #2 violation: oof_rows={len(oof_df)} >= "
            f"input_rows={len(df)} (warm-up chunk 0 must be excluded from OOF)"
        )
        # fold values in {0, 1, 2} (n_splits=3).
        assert set(oof_df["fold"].unique()).issubset({0, 1, 2})
        # p_top3_raw in [0, 1].
        assert oof_df["p_top3_raw"].between(0.0, 1.0).all()
        # No NaN in OOF predictions.
        assert not oof_df["p_top3_raw"].isna().any()

    def test_collect_oof_predictions_feature_columns_arg(
        self,
        sample_feature_df: pd.DataFrame,
        ml_config: dict,
    ) -> None:
        """Test 4: Codex HIGH #5 — feature_columns is an EXPLICIT argument.

        (a) ``inspect.signature(collect_oof_predictions)`` has a
            ``feature_columns`` parameter.
        (b) ``inspect.getsource(collect_oof_predictions)`` does NOT reference
            ``config["data"]["feature_columns"]`` (KeyError avoidance).
        """
        sig = inspect.signature(collect_oof_predictions)
        assert "feature_columns" in sig.parameters, (
            "collect_oof_predictions must accept feature_columns as an explicit "
            "argument (Codex HIGH #5)"
        )
        # AST check (not raw-source) so docstring mentions don't false-positive.
        # We look for any executable subscript chain: config["data"]["feature_columns"]
        tree = ast.parse(inspect.getsource(collect_oof_predictions))
        offending_lines = []
        for node in ast.walk(tree):
            # Match config["data"]["feature_columns"]: a Subscript whose value
            # is Subscript whose value is Name "config", inner keys "data" then
            # "feature_columns".
            if isinstance(node, ast.Subscript):
                outer = node
                if isinstance(outer.value, ast.Subscript):
                    inner = outer.value
                    if (
                        isinstance(inner.value, ast.Name)
                        and inner.value.id == "config"
                    ):
                        outer_key = _const_str(outer.slice)
                        inner_key = _const_str(inner.slice)
                        if (
                            outer_key == "feature_columns"
                            and inner_key == "data"
                        ):
                            offending_lines.append(getattr(node, "lineno", -1))
        assert not offending_lines, (
            f"Codex HIGH #5 violation: collect_oof_predictions references "
            f"config['data']['feature_columns'] at line(s) {offending_lines} "
            "(must take feature_columns as an explicit arg instead)"
        )
        # Sanity: actually run the function with the explicit arg.
        df = _ensure_race_date_datetime(_derive_horse_race_id(sample_feature_df))
        config = dict(ml_config)
        config["cv"] = dict(ml_config["cv"])
        config["cv"]["n_splits"] = 3
        splitter = GroupTimeSeriesSplit(n_splits=3)
        oof_df = collect_oof_predictions(
            df, splitter, config, feature_columns=_TRAINER_FEATURE_COLUMNS
        )
        assert len(oof_df) > 0

    def test_train_final_model_two_stage(
        self,
        sample_feature_df: pd.DataFrame,
        ml_config: dict,
    ) -> None:
        """Test 5: Codex HIGH #6 — train_final_model is a TWO-STAGE full
        retrain. The returned model is trained on ALL input rows (Stage 2),
        not on the ~80% inner-train subset.

        We verify the full-retrain contract by spying on LightGBM's fit row
        count. The test patches ``lgb.LGBMClassifier.fit`` to record the
        length of the X passed to the LAST fit call (which must be Stage 2 =
        full input frame). We cannot simply check ``best_iteration_`` because
        Stage 2 has no early-stopping callback (so best_iteration_ stays
        None by design).
        """
        df = _ensure_race_date_datetime(_derive_horse_race_id(sample_feature_df))
        # Shrink n_splits semantics aren't used here (train_final_model does
        # not run CV), but we keep the config consistent.
        config = dict(ml_config)

        # Spy: wrap LGBMClassifier.fit to record (n_rows, has_callbacks) per call.
        original_fit = lgb.LGBMClassifier.fit
        fit_calls: list[dict] = []

        def _spy_fit(self, X, y=None, **kwargs):  # noqa: ANN001, ANN202
            n_rows = len(X) if hasattr(X, "__len__") else None
            cbs = kwargs.get("callbacks")
            has_es = any("early" in type(cb).__name__.lower() for cb in (cbs or []))
            fit_calls.append({"n_rows": n_rows, "has_early_stopping": has_es})
            return original_fit(self, X, y=y, **kwargs)

        lgb.LGBMClassifier.fit = _spy_fit  # type: ignore[assignment]
        try:
            final_clf = train_final_model(
                df, config, feature_columns=_TRAINER_FEATURE_COLUMNS
            )
        finally:
            lgb.LGBMClassifier.fit = original_fit  # type: ignore[assignment]

        assert isinstance(final_clf, lgb.LGBMClassifier)
        # At least 2 fit calls (Stage 1 + Stage 2).
        assert len(fit_calls) >= 2, (
            f"two-stage contract: expected >=2 fit calls, got {len(fit_calls)}"
        )
        # Stage 1 had early stopping; Stage 2 did NOT (iteration count fixed).
        assert fit_calls[0]["has_early_stopping"], (
            "Stage 1 must use early stopping to decide best_iteration_val"
        )
        last_call = fit_calls[-1]
        assert not last_call["has_early_stopping"], (
            "Stage 2 must NOT use early stopping (iteration count is fixed at "
            "best_iteration_val — Codex HIGH #6)"
        )
        # Codex HIGH #6: Stage 2 trained on ALL input rows.
        assert last_call["n_rows"] == len(df), (
            f"Codex HIGH #6 violation: Stage 2 trained on {last_call['n_rows']} "
            f"rows, expected ALL {len(df)} input rows (true full retrain)"
        )
        # best_iteration_val exposed as custom attr (Stage 2 best_iteration_
        # is None because there was no early stopping).
        assert hasattr(final_clf, "_best_iteration_val")
        assert isinstance(final_clf._best_iteration_val, (int, np.integer))

    def test_collect_oof_passes_dates_to_splitter(
        self,
        sample_feature_df: pd.DataFrame,
        ml_config: dict,
    ) -> None:
        """Test 6: Cycle-2 HIGH #1 — collect_oof_predictions forwards
        ``dates=df["race_date"]`` to ``splitter.split`` so the per-fold
        temporal-order assertion ALWAYS fires (X-column-presence independent).

        (a) Spy splitter records that ``dates`` kwarg was passed on EVERY
            fold call and that its value equals ``df["race_date"]``.
        (b) If df lacks ``race_date``, collect_oof_predictions raises
            KeyError (precondition violation — early detection).
        """
        df = _ensure_race_date_datetime(_derive_horse_race_id(sample_feature_df))
        config = dict(ml_config)
        config["cv"] = dict(ml_config["cv"])
        config["cv"]["n_splits"] = 3

        spy = _SpySplitter(n_splits=3)
        collect_oof_predictions(
            df, spy, config, feature_columns=_TRAINER_FEATURE_COLUMNS
        )

        # (a) at least one split() call recorded.
        assert len(spy.split_calls) >= 1, (
            "collect_oof_predictions did not call splitter.split — spy empty"
        )
        for call in spy.split_calls:
            assert "dates" in call, (
                "Cycle-2 HIGH #1: splitter.split was called WITHOUT the dates "
                "kwarg — temporal-order assertion cannot fire"
            )
            # dates value matches df["race_date"]
            np.testing.assert_array_equal(
                np.asarray(call["dates"]),
                np.asarray(df["race_date"].values),
            )

        # (b) missing race_date -> KeyError (Cycle-2 HIGH #1 contract).
        df_no_date = df.drop(columns=["race_date"])
        with pytest.raises(KeyError):
            collect_oof_predictions(
                df_no_date, spy, config, feature_columns=_TRAINER_FEATURE_COLUMNS
            )
