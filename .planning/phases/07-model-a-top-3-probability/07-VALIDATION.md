---
phase: 7
slug: model-a-top-3-probability
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-15
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Task IDs are finalized by the planner; the Requirement / Test / Command columns
> below are locked by `07-RESEARCH.md` (Validation Architecture). Planner must map
> each task to one or more rows so that no requirement lacks automated verification.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.x (`pyproject.toml` `[project.optional-dependencies] dev`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` testpaths=["tests"] |
| **Quick run command** | `python -m pytest tests/ml/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -q` |
| **Estimated runtime** | ~45 seconds (unit); ~3–5 min (gated E2E on real feature corpus) |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ml/ -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -q` (must not break the existing 513 passed / 1 skipped baseline)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds (unit tier)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | — | W0 | MODA-01 | T-data-leak | LightGBM fold 学習が正常終了し p_top3 を出力 | unit (hermetic) | `pytest tests/ml/test_trainer.py::test_train_fold_model_returns_classifier -x` | ❌ W0 | ⬜ pending |
| TBD | — | W0 | MODA-01 | T-data-leak | 7 つの categorical 列(string)が category dtype に変換される | unit | `pytest tests/ml/test_data_loader.py::test_categorical_conversion -x` | ❌ W0 | ⬜ pending |
| TBD | — | W0 | MODA-01 | — | `horse_race_id` を `race_id + horse_number` から derive し standard/entry と整合 | unit | `pytest tests/ml/test_data_loader.py::test_horse_race_id_derive -x` | ❌ W0 | ⬜ pending |
| TBD | — | W0 | MODA-02 | T-temporal-leak | 同一 race_id は常に同一 fold に配置される | unit | `pytest tests/ml/test_group_timeseries_split.py::test_same_race_same_fold -x` | ❌ W0 | ⬜ pending |
| TBD | — | W0 | MODA-02 | T-temporal-leak | fold 境界が race_date の時系列順を厳守する | unit | `pytest tests/ml/test_group_timeseries_split.py::test_temporal_order -x` | ❌ W0 | ⬜ pending |
| TBD | — | W0 | MODA-02 | T-temporal-leak | 境界で同一レースが割れない（行単位境界割れなし） | unit | `pytest tests/ml/test_group_timeseries_split.py::test_no_boundary_split -x` | ❌ W0 | ⬜ pending |
| TBD | — | W1 | MODA-03 | — | 人気(単勝オッズ順位)ベースライン AUC を NaN 安全に計算 | unit | `pytest tests/ml/test_baseline.py::test_popularity_baseline_auc -x` | ❌ W0 | ⬜ pending |
| TBD | — | W1 | MODA-04 | T-cali-leak | キャリブレーターは OOF のみで fit・holdout は predict のみ（リーク防止） | unit | `pytest tests/ml/test_calibrator.py::test_leak_free_calibration -x` | ❌ W0 | ⬜ pending |
| TBD | — | W1 | MODA-04 | — | ECE が完全予測で 0.0・[0,1] bin 重み付きで計算される | unit | `pytest tests/ml/test_evaluator.py::test_ece_perfect_prediction -x` | ❌ W0 | ⬜ pending |
| TBD | — | W1 | MODA-04 | — | ECE が最悪ケースで最大値を取り範囲 [0,1] に収まる | unit | `pytest tests/ml/test_evaluator.py::test_ece_worst_case -x` | ❌ W0 | ⬜ pending |
| TBD | — | W0 | 全般 | T-data-leak | `audit_leakage([RaceSchema, EntrySchema])` で post-race 混入を検出 | unit | `pytest tests/ml/test_data_loader.py::test_leakage_audit -x` | ❌ W0 | ⬜ pending |
| TBD | — | W2 | 全般 | — | E2E: 学習→OOF→キャリブレーション→holdout 評価が完走 | integration (gated) | `pytest tests/ml/test_run_train.py -k e2e --run-gated -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*
*Threat refs: T-data-leak (post-race leakage), T-temporal-leak (CV boundary), T-cali-leak (holdout recalibration). See `07-RESEARCH.md` § Security Domain.*

---

## Wave 0 Requirements

- [ ] `tests/ml/__init__.py` — package marker
- [ ] `tests/ml/conftest.py` — small fixture race data (a few races, time-ordered, categorical mix, includes `target_top3`)
- [ ] `tests/ml/test_data_loader.py` — categorical conversion / `horse_race_id` derive / leakage audit
- [ ] `tests/ml/test_group_timeseries_split.py` — MODA-02 CV integrity (same-race / temporal order / no boundary split)
- [ ] `tests/ml/test_trainer.py` — MODA-01 training (early-stopping callback API)
- [ ] `tests/ml/test_baseline.py` — MODA-03 popularity baseline AUC
- [ ] `tests/ml/test_calibrator.py` — MODA-04 leak-free isotonic calibration
- [ ] `tests/ml/test_evaluator.py` — MODA-04 ECE / reliability / baseline
- [ ] Framework install: `brew install libomp && pip install scikit-learn matplotlib joblib` (lightgbm import fails without libomp; sklearn/matplotlib/joblib not installed — see `07-RESEARCH.md` § Environment Availability)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| ホールドアウト AUC ≥ 目安0.75（D-07 成功判定） | MODA-01/MODA-03 | 実データ実行結果の数値評価（phase gate） | `reports/phase7/metrics.json` の `holdout_auc` を確認 |
| ホールドアウト ECE < 0.02（D-11 成功判定） | MODA-04 | 実データ実行結果の数値評価（phase gate） | `reports/phase7/metrics.json` の `holdout_ece` を確認・`reports/phase7/reliability_diagram.png` を目視 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
