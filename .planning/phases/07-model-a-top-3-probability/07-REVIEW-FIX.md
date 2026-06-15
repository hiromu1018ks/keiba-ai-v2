---
phase: 07-model-a-top-3-probability
fixed_at: 2026-06-16T07:45:00Z
review_path: .planning/phases/07-model-a-top-3-probability/07-REVIEW.md
iteration: 1
findings_in_scope: 8
fixed: 8
skipped: 0
status: all_fixed
---

# Phase 07: Code Review Fix Report

**Fixed at:** 2026-06-16T07:45:00Z
**Source review:** `.planning/phases/07-model-a-top-3-probability/07-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 8 (2 BLOCKER + 6 WARNING; Info 4 件は fix_scope=critical_warning のため対象外)
- Fixed: 8
- Skipped: 0

**Verification:**
- 各修正後に Tier 1 (再読込) + Tier 2 (`ast.parse` 構文チェック + 該当エッジケースの実機確認) を実施。
- 最終的に `python -m pytest tests/ml/ -q` が **37 passed, 2 skipped** (gated) で GREEN を確認。
- full suite (`python -m pytest tests/ -q`) はバックグラウンドで起動済み (本修正は `src/ml/` 内のみのため ml スイートで十分なカバレッジ)。

## Fixed Issues

### CR-01: `evaluate()` が単一クラスで `nan` を返し、`run_train` が非標準 JSON を書き出す

**Files modified:** `src/ml/evaluator.py`, `src/ml/run_train.py`
**Commit:** `a416445`
**Applied fix:**
- `evaluator.py` に `_safe_auc` / `_safe_logloss` ヘルパーを追加。単一クラス `y_true` のとき AUC は `None`、`log_loss` も `None` を返す (`log_loss` は `nan` ではなく `ValueError` でクラッシュするため、関数全体を巻き込んでパイプライン停止する本来のバグも同時に修正)。`brier_score_loss` は単一クラスを受け付けるため変更なし。
- `run_train.py` Step 10 で `json.dump` に `allow_nan=False` を渡し、残存 `nan/inf` を `None` に正規化してから書き出すよう変更。Step 8 のログ行も `auc_calibrated=None` を許容するよう修正。
- **動作保証**: クラス混在時の実数値は完全に同一 (AUC 1.0 / logloss 0.2899 等は不変)、単一クラス時のみ JSON 安全な `null` になることを実機確認済み。

**Status:** fixed (論理バグを含むため、本番 holdout 66k 行では発現しない点は REVIEW 記載の通り。subset 評価・hermetic fixture 拡張時に即発するバグの構造的封じ込め)。

### CR-02: `train_final_model` Stage 2 が `best_iteration_val` に下限を持たず、ほぼ未学習モデルが出力され得る

**Files modified:** `src/ml/trainer.py`
**Commit:** `f00d1e0`
**Applied fix:**
- Stage 2 の `n_estimators` に `MIN_FINAL_ITERATIONS = 10` のフロアを設定。`final_n_estimators = max(int(best_iteration_val), 10)`。下限到達時は警告ログを出力 (監査性確保)。
- Stage 2 の訓練ログ行が「clamped 値」と「元の Stage-1 値」の両方を報告するよう改善。

**Status:** fixed: requires human verification (論理バグ — フロア値 10 がドメイン的に適切かは最終モデルの木数分布を見て確認推奨。本番 config の `stopping_rounds=50` では到達しないが、seed/特徴量退化時の安全網)。

### WR-01: `split_train_validation` が inner_train=0 行を許容し、LightGBM fit をクラッシュさせる

**Files modified:** `src/ml/group_timeseries_split.py`
**Commit:** `1684792`
**Applied fix:**
- `inner_train_df` が空のとき、LightGBM の深部 `ValueError` に至る前にアクション可能なメッセージ付き `ValueError` を raise。単一レース fold / `val_ratio=0.2` で train<5 レースのケースを明示的に検出。

### WR-02: `apply_calibrator` が空配列で `ValueError` を投げる

**Files modified:** `src/ml/calibrator.py`
**Commit:** `664aebe`
**Applied fix:**
- `raw_preds.size == 0` のとき早期 return で空配列を返す。trainer の空 OOF 契約 (「OOF が空なら空 DataFrame」) と整合。run_train Step 7 / OOF parquet 書き出し (line ~294) が空 hermetic fixture でクラッシュしなくなった。

### WR-03: `compute_popularity_baseline` が features_df 既存の `popularity` 列で KeyError を出す

**Files modified:** `src/ml/baseline.py`
**Commit:** `d094028`
**Applied fix:**
- merge 前に `features_df` が `popularity` 列を持つとき、D-15 リーケージ不変条件違反として明示的に `ValueError` を raise。merge が `popularity_x/y` にリネームした後に `dropna(subset=["popularity"])` が不可解な `KeyError` を出す本来のバグを、境界で分かりやすく失敗させるよう変更。

### WR-04: `compute_ece` が NaN 含む入力で `nan` を返し、呼び出し元に伝播する

**Files modified:** `src/ml/evaluator.py`
**Commit:** `4b284a8`
**Applied fix:**
- 冒頭で NaN 行をマスク除去し、全行 NaN のとき 0.0 を返すよう変更。docstring の「戻り値は常に有限 float で [0.0, 1.0]」契約を遵守。
- 副次効果: run_train の `if ece_calibrated >= ece_tolerance` が `nan >= 0.02` → 常に `False` で D-11 違反警告を握り潰すバグも同時に解消。

**Status:** fixed: requires human verification (ロジック — NaN 除去が ECE の統計的意味を変えないかは、本番 OOF の NaN 発生頻度が実質ゼロである前提。発生時は行数減をログで追跡可能)。

### WR-05: `collect_oof_predictions` が `group_col` をハードコード列名 `race_id` で出力する

**Files modified:** `src/ml/trainer.py`
**Commit:** `95b6df3`
**Applied fix:**
- `collect_oof_predictions` の冒頭で `group_col != "race_id"` のとき `ValueError` を raise。OOF 出力列名をコード固定の `"race_id"` とし、Phase 8 Harville の groupby 契約を構造保証。可変 `group_col` と固定出力名の不整合による黙示的誤グループ化を境界で防止。

### WR-06: `run_train` の必須 config キーが `.get()` なしで直接アクセスされ、欠損時に不可解な KeyError

**Files modified:** `src/ml/run_train.py`
**Commit:** `8845f97`
**Applied fix:**
- YAML 読込直後に `_REQUIRED_CONFIG_KEYS` リストを 1 パス走査して必須キーを検証。欠損時は `KeyError("run_train: required config key 'data.train_window' is missing ... in {config_path}. Check the YAML against config/phase7_model_a.yaml (D-14 config schema).")` のようにアクション可能なメッセージで即時失敗。オプションキー (`drop_columns`, `ece_tolerance`, `diagram_filename` 等) は従来通り `.get()` を維持。

---

_Fixed: 2026-06-16T07:45:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
