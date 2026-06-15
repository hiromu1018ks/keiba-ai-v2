---
phase: 07-model-a-top-3-probability
reviewed: 2026-06-15T16:01:42Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - src/ml/__init__.py
  - src/ml/data_loader.py
  - src/ml/group_timeseries_split.py
  - src/ml/trainer.py
  - src/ml/calibrator.py
  - src/ml/evaluator.py
  - src/ml/baseline.py
  - src/ml/run_train.py
  - config/phase7_model_a.yaml
  - pyproject.toml
findings:
  critical: 2
  warning: 6
  info: 4
  total: 12
status: issues_found
---

# Phase 07: Code Review Report

**Reviewed:** 2026-06-15T16:01:42Z
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

Phase 7 Model A (top-3 probability) の実装 10 ファイルを標準深度でレビューした。
LightGBM 4.x callback API、GroupTimeSeriesSplit の時間不変性、Isotonic 校正の leak 防止、ECE 実装といった主要なドメイン不変条件は実データ検証付きで正しく実装されている。

一方で、以下の実装バグ・堅牢性欠陥を実機検証で確認した:

- **BLOCKER 級**: `evaluate()` が `roc_auc_score` の単一クラス入力で `nan` を返し、`run_train` がそれを `json.dump` で `NaN`（非標準 JSON リテラル）として metrics.json に書き出す。strict JSON パーサ（JS / jq / 多くの BI ツール）がファイルを解析できず、Phase 8/9 のダウンストリーム消費と 07-08 phase-gate verify を破る可能性がある。
- **BLOCKER 級**: `train_final_model` の Stage 2 が `best_iteration_val` に下限を持たず、`stopping_rounds` で 1〜数イテレーションで早止めした場合、ほぼ未学習のモデルが最終成果物として出力される。本番相性の悪いデータで静かに破綻する。
- そのほか `split_train_validation` の inner_train 空時の LightGBM クラッシュ、`apply_calibrator` の空配列クラッシュ、`compute_popularity_baseline` の merge 衝突時 KeyError など、エッジケースでのみ発現する堅牢性欠陥が多数存在する。

leakage prevention 不変条件（`target_top3` / `popularity` / `win_odds` / `race_id` / `race_date` / `horse_number` / `horse_race_id` が effective feature_columns に入らない）、temporal integrity（race 完全性・日付ブロック境界・warm-up 非空）、LightGBM 4.x callback API 使用、Isotonic `[0,1]` クリッピング、ECE の bin 重み付け（Guo et al. 2017）は検証で全て満たされることを確認した。

## Critical Issues

### CR-01: `evaluate()` が単一クラスで `nan` を返し、`run_train` が非標準 JSON を書き出す

**File:** `src/ml/evaluator.py:123-128`, `src/ml/run_train.py:333-334`
**Issue:**
`evaluate()` は `roc_auc_score` を直接呼び出す。holdout の `target_top3` が極端な偏り（全 0 または全 1）を持つ場合、sklearn は `UndefinedMetricWarning` を出して `nan` を返す（実機確認済み）。その `nan` を含む `metrics` dict を `run_train` が `json.dump(metrics, f, ..., default=float)` で直列化すると、ファイルには `NaN`（引用符なし）という **strict JSON として不正なリテラル** が書き出される（実機確認: `{"auc": NaN}`）。

Python の `json.loads` はデフォルトでこれを許容するが、標準 JSON（RFC 8259）は `NaN` / `Infinity` を認めない。jq、Node.js の `JSON.parse`、多くの BI ツール / Pandas の `read_json(engine="pyarrow")` / Spark はパースエラーを起こす。Phase 8/9 および 07-08 phase-gate verify が metrics.json を消費する設計上、このファイルが読めなくなるとパイプライン全体が止まる。

補足: 単一クラスの holdout 自体はレアだが、本番データのリサンプリングや特定条件下の race サブセット（例: grade レース限定の部分評価）では発生し得る。現在の holdout（66,343 行）では起きないが、コードはジェネリックに `evaluate()` を再利用可能にしているため、利用範囲が広がると即発する。

**Fix:**
`evaluate()` で単一クラスを検出したら `auc_*` を明示的に `None`（または `0.5` の無情報値）にし、`run_train` で `json.dump` に `allow_nan=False` を渡して非標準リテラルを構造的に禁止する。

```python
# evaluator.py — evaluate() 内
def _safe_auc(y_true, y_prob):
    if len(np.unique(y_true)) < 2:
        logger.warning("evaluate: single-class y_true — AUC undefined, returning None")
        return None
    return float(roc_auc_score(y_true, y_prob))

auc_raw = _safe_auc(y_true_arr, y_prob_raw_arr)
auc_calibrated = _safe_auc(y_true_arr, y_prob_cal_arr)
```

```python
# run_train.py Step 10
metrics_for_json = {
    k: (v if v is not None and not (isinstance(v, float) and math.isnan(v)) else None)
    for k, v in metrics.items()
}
with metrics_path.open("w", encoding="utf-8") as f:
    json.dump(metrics_for_json, f, indent=2, ensure_ascii=False, allow_nan=False)
```

### CR-02: `train_final_model` Stage 2 が `best_iteration_val` に下限を持たず、ほぼ未学習モデルが出力され得る

**File:** `src/ml/trainer.py:386-409`
**Issue:**
Stage 1 の `clf.best_iteration_` は `stopping_rounds=50` の early stopping で小さな値（極端な場合は 1〜10）になり得る。本番 config (`stopping_rounds: 50`, `n_estimators: 1000`) では通常数拾〜数百になるが、データ分布のシフト・特徴量の退化・seed の変更で 1 桁になる可能性がある。Stage 2 は `stage2_clf.set_params(n_estimators=int(best_iteration_val))` でこれをそのまま使い、一切の下限チェックを行わない。

結果として、最終成果物（`models/phase7/model_a.lgb.txt`）が実質的に 1〜数本の木しか持たない弱学習器になり得る。これは Phase 8 Harville EV / Phase 9 backtest の根幹をなすモデルであり、静かに回収率を破壊する。docstring にはこの危険性の記述も、ログでの警告も、下限のフロアもない。

`best_iteration_ is None` のフォールバック（`n_estimators` に戻す）は実装されているが、`best_iteration_` が極端に小さい正の整数の場合の保護がない。

**Fix:**
Stage 2 の `n_estimators` に明示的な下限（例: 10 または `min(50, n_estimators // 2)`）を設け、下限に達したら警告ログを出す。

```python
# trainer.py train_final_model — Stage 2 の前
MIN_FINAL_ITERATIONS = 10  # 弱学習器化を防ぐフロア
final_n_estimators = max(int(best_iteration_val), MIN_FINAL_ITERATIONS)
if final_n_estimators != int(best_iteration_val):
    logger.warning(
        f"Stage 1 best_iteration_val={best_iteration_val} < floor "
        f"{MIN_FINAL_ITERATIONS}; clamping Stage 2 n_estimators to "
        f"{final_n_estimators} to avoid under-fit final model"
    )
stage2_clf.set_params(n_estimators=final_n_estimators)
```

## Warnings

### WR-01: `split_train_validation` が inner_train=0 行を許容し、LightGBM fit をクラッシュさせる

**File:** `src/ml/group_timeseries_split.py:367-378`
**Issue:**
`n_val = max(1, int(len(races) * val_ratio))` は常に `>= 1` を保証するが、`inner_train` が空になるケースを防がない。実機確認: `train_df` が 1 レースのみの場合、`inner_train_rows=0` / `inner_val_rows=1` となる。この `inner_train_df` を `train_fold_model` → `clf.fit(X_train=[], y_train=[])` に渡すと LightGBM が `ValueError` でクラッシュする。

本番 holdout（66k 行）では起きないが、fold 0 の train chunk（warm-up）が極端に小さい hermetic fixture や、CV fold の train partition の race 数が `1 / val_ratio` 未満の場合に発現する。`val_ratio=0.2` なら train が 5 レース未満の fold で空になる可能性がある。

**Fix:**
`inner_train` が空、または LightGBM が学習可能な最小行数を下回る場合に `ValueError` を raise する。

```python
# group_timeseries_split.py split_train_validation の末尾
if len(inner_train_df) == 0:
    raise ValueError(
        f"split_train_validation: inner_train is empty "
        f"(total_races={len(races)}, n_val={n_val}, val_ratio={val_ratio}). "
        f"Need at least {n_val + 1} races in train_df."
    )
return inner_train_df, inner_val_df
```

### WR-02: `apply_calibrator` が空配列で `ValueError` を投げる

**File:** `src/ml/calibrator.py:145-146`
**Issue:**
実機確認: `apply_calibrator(iso, np.array([]))` は sklearn 内部の `check_array` が `Found array with 0 sample(s)` で `ValueError` を投げる。`run_train` Step 7（holdout 予測の校正）と Step 10 OOF parquet 保存時の OOF 校正（line 294）で呼ばれる。holdout や OOF が空（例: 全 fold の val chunk が空、または hermetic fixture で holdout が空）の場合、`run_train` 全体がクラッシュする。

`run_train` の OOF path は「OOF が空なら空 DataFrame を返す」仕様（trainer.py:328-332）なので、それと整合しない。

**Fix:**
空配列は early return する。

```python
# calibrator.py apply_calibrator
def apply_calibrator(iso: IsotonicRegression, raw_preds: np.ndarray) -> np.ndarray:
    raw_preds = np.asarray(raw_preds, dtype=float)
    if raw_preds.size == 0:
        return raw_preds  # 空入力は空出力
    return iso.predict(raw_preds)
```

### WR-03: `compute_popularity_baseline` が features_df 既存の `popularity` 列で KeyError を出す

**File:** `src/ml/baseline.py:69-78`
**Issue:**
実機確認: `features_df` が既に `popularity` 列を持つ場合、`merge` が `popularity_x` / `popularity_y` にサフィックス変更し、その後 `dropna(subset=["popularity"])` が `KeyError: ['popularity']` でクラッシュする。docstring に「features_df must NOT contain popularity — caller's invariant」と書かれているが、実行時検証がない。

本番パスでは features layer に popularity はない（設計通り）ため発現しないが、Phase 8/9 で誤って popularity を含む df を渡した場合、不可解な KeyError になる。invariant はコードで保証すべき。

**Fix:**
マージ前に invariant を assert するか、サフィックスを明示して冲突を検出する。

```python
# baseline.py
def compute_popularity_baseline(features_df, entry_df):
    if "popularity" in features_df.columns:
        raise ValueError(
            "compute_popularity_baseline: features_df must NOT contain 'popularity' "
            "(D-15 leakage invariant). Caller passed a frame with the column present."
        )
    merged = features_df.merge(...)
```

### WR-04: `compute_ece` が NaN 含む入力で `nan` を返し、呼び出し元に伝播する

**File:** `src/ml/evaluator.py:72-94`
**Issue:**
実機確認: `compute_ece([0, 1, None], [0.1, 0.5, 0.9])` は例外を投げず `nan` を返す。`[0,1,1]` / `[0.1, nan, 0.9]` も同様。`evaluate()` の `ece_raw` / `ece_calibrated` が `nan` になると、CR-01 と同じく metrics.json の非標準 JSON 化を引き起こすほか、`run_train` の `if metrics["ece_calibrated"] >= ece_tolerance` が `nan >= 0.02` → `False` となり、D-11 違反の警告が正しく発火しない（`nan` 比較は常に `False`）。

ECE の docstring は「戻り値は常に有限 float で [0.0, 1.0] に収まる」と明記しているが、これは NaN 入力について虚偽になる。

**Fix:**
入力の NaN を明示的にチェックするか、`dropna` してから計算する。

```python
# evaluator.py compute_ece の冒頭
y_true_arr = np.asarray(y_true, dtype=float)
y_prob_arr = np.asarray(y_prob, dtype=float)
mask = ~(np.isnan(y_true_arr) | np.isnan(y_prob_arr))
y_true_arr = y_true_arr[mask]
y_prob_arr = y_prob_arr[mask]
n = len(y_true_arr)
if n == 0:
    logger.warning("compute_ece: empty or all-NaN input, returning 0.0")
    return 0.0
```

### WR-05: `collect_oof_predictions` が `group_col` をハードコード列名 `race_id` で出力する

**File:** `src/ml/trainer.py:264, 313`
**Issue:**
`group_col = _resolve_group_column(config)` で `race_id` 以外のグループ列（例: 将来の `horse_race_id` ベース CV）を許可するが、OOF 出力 DataFrame は常に列名 `"race_id"` を使う。`group_col != "race_id"` の場合、`oof_df["race_id"]` に `group_col` の値が入り、列名と意味が不一致になる。Phase 8 Harville が `oof_predictions.parquet` を `race_id` で groupby すると、誤ったグルーピングになる。

本番 config では `group_column: race_id` なので発現しないが、コードの意図（`group_col` を可変にする）と出力（`race_id` 固定）が矛盾しており、潜在的なバグ。

**Fix:**
出力列名を `group_col` に合わせるか、ドキュメントで `group_col == "race_id"` を契約化して assert する。

```python
# trainer.py collect_oof_predictions
if group_col != "race_id":
    raise ValueError(
        f"collect_oof_predictions requires cv.group_column='race_id' for OOF schema "
        f"stability (Phase 8 Harville groups on race_id); got '{group_col}'"
    )
```

### WR-06: `run_train` の必須 config キーが `.get()` なしで直接アクセスされ、欠損時に不可解な KeyError

**File:** `src/ml/run_train.py:145-147, 176, 234, 239, 276, 326`
**Issue:**
`config["data"]["train_window"]`, `config["data"]["target_column"]`, `config["evaluation"]["ece_bins"]`, `config["artifacts"]` など多数の必須キーがブラケットアクセスで直接参照されている。キー欠損時、`KeyError: 'train_window'` のような低レベルエラーになり、ユーザー（または Phase 8/9 の再利用者）がどこを直せばいいか分からない。

`data.drop_columns`, `ece_tolerance`, `diagram_filename` などは `.get(..., default)` で安全に読まれているのに、より重要な必須キーが unsafe になっているのは一貫性がない。

**Fix:**
必須キーを冒頭で一度だけ検証するか、専用の `_load_config` ヘルパで Pydantic / dataclass にパースする。最小限の修正:

```python
REQUIRED_KEYS = [
    ("data", "feature_path"), ("data", "train_window"), ("data", "holdout_window"),
    ("data", "target_column"), ("data", "feature_columns"), ("data", "entry_path"),
    ("cv", "n_splits"), ("evaluation", "ece_bins"), ("artifacts",),
]
for path in REQUIRED_KEYS:
    node = config
    for k in path:
        if not isinstance(node, dict) or k not in node:
            raise KeyError(f"run_train: required config key '{'.'.join(path)}' missing in {config_path}")
        node = node[k]
```

## Info

### IN-01: `config.model.metric` / `force_col_wise` が `_build_classifier` で無視される

**File:** `config/phase7_model_a.yaml:156-168`, `src/ml/trainer.py:124-149`
**Issue:**
config の `model.metric: [binary_logloss, auc]` と `model.force_col_wise: true` は `_build_classifier` で一度も読まれず、`LGBMClassifier` に渡されない（実機確認: `LGBMClassifier.__init__` はこれらの引数を受け取るが、呼び出し側が渡していない）。特に `metric` は early stopping callback の `first_metric_only` と連動するはずで、callback は objective のデフォルト metric（`binary_logloss`）を見る。config で `auc` を第2 metric に指定しても効果がない。ドキュメント上のミスリード。

**Fix:**
未使用キーを削除するか、`_build_classifier` で `metric` / `force_col_wise` を明示的に渡す。

```python
clf = lgb.LGBMClassifier(
    ...
    metric=m.get("metric"),  # None なら LightGBM デフォルト
    force_col_wise=bool(m.get("force_col_wise", False)),
)
```

### IN-02: `config.data.categorical_columns` が trainer で明示的に渡されない（pandas category 自動検出に依存）

**File:** `config/phase7_model_a.yaml:121-130`, `src/ml/trainer.py:124-149`
**Issue:**
config に 9 列の `categorical_columns` を定義しているが、`_build_classifier` は `categorical_feature=` を渡さない。`load_features` が `astype("category")` で pandas CategoricalDtype に変換しており、LightGBM が pandas category を自動検出するため機能的には動作する（CLAUDE.md「LightGBM auto-detects pandas CategoricalDtype columns」記載通り）。しかし config とコードの二重管理で、片方だけ更新すると不整合が起きる。D-16「native categoricals」の意図は達成されるが、明示性に欠ける。

**Fix:**
`load_features` の category 変換を single source of truth とし、config の `categorical_columns` をドキュメント専用にする（コメントで明記）、または trainer で `categorical_feature=config["data"]["categorical_columns"]` を明示渡しして二重保証にする。

### IN-03: `_best_iteration_val` が private 属性として LightGBM オブジェクトに monkey-patch される

**File:** `src/ml/trainer.py:428`
**Issue:**
`stage2_clf._best_iteration_val = best_iteration_val` は LightGBM の公開 API 外の属性追加で、`type: ignore[attr-defined]` で黙殱されている。LightGBM のバージョンアップで `_` 始まり属性の扱いが変わるリスク、および `__slots__` 化された場合の `AttributeError` リスクがある。`run_train` はこれを `getattr(final_clf, "_best_iteration_val", None)` で読むので、属性が消えても静かに `None` になり、ログの監査性が落ちる。

**Fix:**
ラッパークラスか tuple で返す方が堅牢。最小修正なら dict で返す。

```python
# trainer.py
@dataclass
class FinalModel:
    clf: lgb.LGBMClassifier
    best_iteration_val: int

# train_final_model の return
return FinalModel(stage2_clf, best_iteration_val)
```
ただし Phase 8/9 と既存テストが `final_clf` を直接 LightGBM として扱っているため、影響範囲を要確認。

### IN-04: `reliability_diagram` の空 bin プロットが `np.nan` height を使うが、matplotlib が警告を出す場合がある

**File:** `src/ml/evaluator.py:208-217`
**Issue:**
空 bin に対して `accs.append(np.nan)` し、`ax.bar(confs, accs, ...)` でプロットする。matplotlib は `NaN` の bar を描画しない（透明）が、バージョンによって `UserWarning: invalid value encountered in greater` 系の警告を出すことがある。機能的には正しいが、CI ログにノイズが出る可能性。

**Fix:**
空 bin の `confs` / `accs` をプロット対象から除外する（`sizes > 0` でマスク）か、`ax.bar` 呼び出し前に `np.errstate(invalid='ignore')` で包む。

```python
non_empty = [s > 0 for s in sizes]
ax.bar(
    [c for c, ok in zip(confs, non_empty) if ok],
    [a for a, ok in zip(accs, non_empty) if ok],
    width=0.08, alpha=0.7, label="Model",
)
```

---

_Reviewed: 2026-06-15T16:01:42Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
