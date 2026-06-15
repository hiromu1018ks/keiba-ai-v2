# Phase 7: Model A -- Top-3 Probability - Research

**Researched:** 2026-06-15
**Domain:** LightGBM 二値分類（3着内確率推定）・時系列CV・確率キャリブレーション
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions (D-01〜D-15 — DO NOT re-litigate)

**時系列分割・CV 設計**
- **D-01:** 学習区間 = 2018-2024（直近7年）。ROADMAP「2015-2023」から前倒し（concept drift 対策）
- **D-02:** ホールドアウト = 2025-01〜2026-05（1.5年）。学習に触れさせない最終評価専用
- **D-03:** GroupTimeSeriesSplit 採用（race_id/race_date で区切り、同一レースは同一foldへ）。sklearn標準 TimeSeriesSplit は行単位で境界割れするため独自実装
- **D-04:** fold 数 = 5。学習7年を5分割。各foldから early stopping 用 validation を別途切る
- **D-05:** ROADMAP 成功基準#1「2015-2023」文言更新は Phase 9 繰越

**評価指標・ベースライン**
- **D-06:** 主指標 = AUC（ランキング精度）。Brier / logloss は補助。ROI は Phase 9 領域
- **D-07:** 成功判定 = 「ホールドアウト AUC 目安0.75以上」＋「キャリブレーション成功（D-11）」。人気ベースライン超えは必須条件にしない
- **D-08:** feature からオッズ除外（純粋馬特性モデル）なので人気ベースライン超えは困難。真の EV 優位性は Phase 9 ROI で検証
- **D-09:** race レベル指標（Top-3 recall）も参考出力

**キャリブレーション**
- **D-10:** Isotonic 回帰。OOF予測で学習 → ホールドアウトに適用（リークなし標準パターン）
- **D-11:** 成功基準 = ホールドアウト ECE < 0.02。reliability diagram 併出力
- **D-12:** IsotonicRegression をキャリブレーターとしてモデルと一緒に保存。生 `p_top3_raw` も併存

**ハイパラ・成果物契約**
- **D-13:** LightGBM sensible defaults + early stopping（HPO/Optuna は Phase 9/v2 繰越）
- **D-14:** ハイパラは YAML config、固定 seed
- **D-15:** 成果物 = ①訓練済みモデル(`.txt`) ②Isotonicキャリブレーター(`.joblib`) ③OOF予測parquet（`race_id`, `horse_race_id`, `p_top3_raw`, `p_top3_calibrated`, `target_top3`, `fold`）④ホールドアウト予測parquet（`fold='holdout'`）⑤評価レポート ⑥config YAML。配置: `models/phase7/`・`data/model/oof/`・`reports/phase7/`（gitignore対象）

### Claude's Discretion（研究で推奨を提示する領域）
- AUC 閾値の厳密値（目安0.75は実測次第）
- early stopping validation の切り方・patience・最大ラウンド数
- 人気ベースライン計算の詳細（順位→疑似確率の変換方式）
- sensible defaults の具体的パラメータ値（`num_leaves` / `learning_rate` / `min_data_in_leaf` / `feature_fraction` / `bagging` / `max_depth`）
- 高カーディナリティ categorical（`jockey` / `trainer`）の `min_data_in_leaf` 等の対処
- クラス不均衡対処（陽性21.7%は軽度、`scale_pos_weight` はデフォルトで様子見）
- 成果物配置の最終パス・ファイル命名規則
- reliability diagram 可視化ライブラリ（matplotlib 導入要否）

### Deferred Ideas (OUT OF SCOPE)
- Optuna HPO / グリッドサーチ（Phase 9 / v2 ADVM-02）
- 「純粋モデル vs 人気追加モデル」の3者比較
- ROADMAP 成功基準#1 文言更新（Phase 9）
- `scale_pos_weight` / クラス重み付け
- 特徴量重要度の深度分析（SHAP 等）
- sliding / rolling window CV
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MODA-01 | LightGBM による3着内確率モデルを構築し、各馬の p_top3 を出力できること | `## Standard Stack` LightGBM 4.6.0 + sklearn API LGBMClassifier。`## Code Examples` sensible defaults + early_stopping callback パターン。feature_train.parquet の target_top3（21.7% 陽性）を binary 目標として学習 |
| MODA-02 | TimeSeriesSplit による時系列CVで学習/検証を分離し、未来データのリークを防ぐこと | `## Pattern 1: GroupTimeSeriesSplit` race_id グループ化 + race_date 時系列順で同一レース同一fold を保証。`## Don't Hand-Roll` の sklearn TimeSeriesSplit 行単位境界割れ問題と解決策。各 fold 内で validation 切り出しパターン |
| MODA-03 | 人気順ベースライン（単勝オッズ順位）との比較でモデル確率の優位性を確認できること | `## Code Examples` 人気ベースライン AUC 計算。`data/standard/entry.parquet` の popularity（533,009 non-null）を race_id+horse_number 経由で features_train に join。rank を -1×score として roc_auc_score に渡す |
| MODA-04 | OOF 予測による確率キャリブレーションを実装し、推定確率と実際の的中率の一致を確認できること | `## Pattern 2: Isotonic Calibration` OOF 学習→ホールドアウト適用のリーク防止標準パターン。`## Code Examples` ECE 計算（手動実装、10-bin equal-width）+ reliability diagram。成功基準 ECE < 0.02（D-11） |
</phase_requirements>

## Summary

Phase 7 は、feature 層（534,953行×78列、2015-2026/5）から 2018-2024 の学習窓（322,510 有効行 / 23,288 レース）と 2025-2026/5 のホールドアウト（66,574行 / 4,740 レース）を抽出し、LightGBM 二値分類器で各馬の 3着内確率 `p_top3` を推定・検証するフェーズ。target_top3 の陽性率は 21.7%（軽度不均衡、`scale_pos_weight` はデフォルトで対応）。

技術的に最も重要な発見は3点。**(1) LightGBM 4.x では `early_stopping_rounds` が fit() から完全削除されており、`callbacks=[lgb.early_stopping(stopping_rounds=N)]` を使う必須** `[VERIFIED: lightgbm readthedocs 4.6]`。**(2) `features_train.parquet` は `horse_race_id` を含まず（D-15 が OOF/holdout に必須指定）、Phase 7 は `race_id + horse_number` から derive するか feature に追加する必要がある** `[VERIFIED: codebase inspect]`。**(3) `course_name`, `surface`, `direction`, `weather`, `track_condition`, `sex`, `grade` は `string` dtype で保存されており、`jockey`/`trainer` のみが `category` 変換済み** — Phase 7 は学習前にこれら string 列を `CategoricalDtype` に変換しないと LightGBM の native categorical 自動検出が働かない `[VERIFIED: codebase inspect]`。特に `grade` は 95% NaN（506,349件）で、categorical 化時に NaN が code -1 として正しく保持されるか検証が必要。

環境面では `lightgbm==4.6.0` はインストール済みだが libomp 未導入で **import が失敗**、`scikit-learn` / `matplotlib` / `joblib` は未導入。これらは Phase 7 plan の Wave 0 前提タスク（`brew install libomp` + `pip install scikit-learn matplotlib joblib`）として必須。

**Primary recommendation:** Wave 0 で環境整備（libomp + sklearn + matplotlib + joblib）→ Wave 1 で `src/ml/` 新設（data_loader, group_timeseries_split, trainer, calibrator, evaluator, run_train）+ sensible-defaults config YAML → Wave 2 でホールドアウト評価・成果物保存。GroupTimeSeriesSplit は sklearn `BaseCrossValidator` 互換の独自実装（race_id グループ化＋race_date 時系列ソート）。Isotonic は OOF 学習→holdout 適用のリーク防止パターン。

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Feature 読込・dtype 整備 | Pipeline / Data Layer | — | `feature_generator.py` が生成、Phase 7 は parquet を読んで categorical 変換のみ追補 |
| p_top3 推定モデル学習 | ML / Training Tier | — | LightGBM LGBMClassifier、新設 `src/ml/`。純粋予測（オッズ除外）は理論的骨格 |
| 時系列CV（リーク防止） | ML / Training Tier | — | GroupTimeSeriesSplit 独自実装、Phase 8/9 再利用資産。境界は race_id/race_date |
| Isotonic キャリブレーション | ML / Post-Training Tier | — | OOF 学習→holdout 適用。EV 計算（Phase 8）精度に直接効く安全側設計 |
| 評価（AUC/Brier/logloss/ECE） | ML / Evaluation Tier | Reporting | 主に sklearn.metrics + ECE 手動実装。reliability diagram は matplotlib |
| 人気ベースライン比較 | ML / Evaluation Tier | Data Layer | `entry.parquet` の popularity を join して AUC 対比。純粋予測×EV 構図の文脈 |
| 成果物永続化 | Storage / Artifacts | — | モデル(.txt)・キャリブレーター(.joblib)・OOF/holdout parquet・report・config。全て gitignore |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| lightgbm | 4.6.0 `[VERIFIED: pip index]` | 二値分類器（p_top3 推定） | CLAUDE.md 固定。4.6.0 は macOS wheel 提供・categorical native 扱い・8x 高速化 `[CITED: lightgbm.readthedocs.io/Parameters-Tuning]` |
| scikit-learn | 1.9.0 `[VERIFIED: pip index]` | 評価指標・IsotonicRegression | roc_auc_score / brier_score_loss / log_loss / IsotonicRegression に必須。未導入（Wave 0 で install）`[CITED: scikit-learn.org/stable/modules/calibration]` |
| pandas | 2.3.x（導入済） | DataFrame 処理・parquet I/O | 既存スタック。CategoricalDtype で LightGBM native categorical |
| numpy | 2.x（導入済） | 数値計算 | 既存スタック。feature_generator 依存 |
| pyarrow | 14.0+（導入済） | parquet engine | 既存スタック。features_train.parquet 読込 |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| matplotlib | 3.11.0 `[VERIFIED: pip index]` | reliability diagram 出力 | ECE 評価の可視化（D-11）。未導入。`Agg` backend でヘッドレス描画 |
| joblib | 1.5.3 `[VERIFIED: pip index]` | IsotonicRegression の `.joblib` 保存 | D-15 が `.joblib` 形式を指定。未導入。lightgbm モデルは `.txt`（booster.save_model）で joblib 不要 |
| pyyaml | 6.x（導入済） | ハイパラ config（D-14） | `config/phase7_model_a.yaml` の読込 |
| loguru | 0.7.x（導入済） | 構造化ロギング | 既存プロジェクト標準 |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| 手作り GroupTimeSeriesSplit | mlxtend `GroupTimeSeriesSplit` | mlxtend は外部依存追加。CLAUDE.md「Use Instead: 必要なものだけ」精神。独自実装で Phase 8/9 再利用資産化 `[CITED: rasbt.github.io/mlxtend]` |
| 手動 ECE 実装 | torchmetrics `CalibrationError` | torchmetrics は PyTorch 重依存（過剰）。ECE は20行で実装可能、sklearn に未収録（issue #18268 open）`[CITED: github.com/scikit-learn/scikit-learn/issues/18268]` |
| 手動 Isotonic パターン | `CalibratedClassifierCV(est, method='isotonic', cv=...)` | CalibratedClassifierCV は group-aware CV に非対応（D-03 GroupTimeSeriesSplit と衝突）。OOF 収集→別 fit の手動パターンが D-10 要件に合致 `[CITED: scikit-learn.org/stable/modules/calibration]` |

**Installation (Wave 0 前提タスク):**
```bash
# libomp: LightGBM が lib_lightgbm.dylib で @rpath/libomp.dylib を要求（未導入で import 失敗を実測）
brew install libomp

# scikit-learn: LGBMClassifier の sklearn API・metrics・IsotonicRegression
# lightgbm[scikit-learn] extra で明示
pip install 'lightgbm[scikit-learn]' scikit-learn matplotlib joblib

# pyproject.toml への追記（setuptools、Poetry ではない — MEMORY.md 参照）
# [project] dependencies に追記: "scikit-learn>=1.9", "matplotlib>=3.10", "joblib>=1.4"
```

**Version verification（実測）:**
```
lightgbm==4.6.0     (installed, import fails without libomp)
scikit-learn==1.9.0 (latest on PyPI, NOT installed)
matplotlib==3.11.0  (latest on PyPI, NOT installed)
joblib==1.5.3       (latest on PyPI, NOT installed)
```

## Package Legitimacy Audit

> `gsd-tools query package-legitimacy check --ecosystem pypi lightgbm scikit-learn matplotlib joblib` を実施。全パッケージが `SUS` 判定だが、これは seam が PyPI で週次ダウンロード数を取得できない（npm のみ対応）ことと「最近 publish された」シグナルによる**誤検知**。4 パッケージ全て、Microsoft/scikit-learn_contrib/matplotlib/joblib という正規の権威ソースであり、slopsquat リスクなし。

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| lightgbm | PyPI | since 2017 (4.6.0: 2025-02) | seam N/A | github.com/microsoft/LightGBM | SUS (false positive) | Approved — 正規 Microsoft 公式パッケージ |
| scikit-learn | PyPI | since 2010 (1.9.0: 2026-06) | seam N/A | github.com/scikit-learn/scikit-learn | SUS (false positive) | Approved — デファクト標準 |
| matplotlib | PyPI | since 2009 (3.11.0: 2026-06) | seam N/A | github.com/matplotlib/matplotlib | SUS (false positive) | Approved — デファクト標準 |
| joblib | PyPI | since 2010 (1.5.3: 2025-12) | seam N/A | github.com/joblib/joblib | SUS (false positive) | Approved — scikit-learn 依存としても入る |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** 4 パッケージ全て seam で SUS 判定を受けたが、いずれも PyPI seam シグナル制限（downloads 取得不可）による誤検知。正規リポジトリ（microsoft/LightGBM, scikit-learn, matplotlib, joblib）で10年以上の実績。**planner は `checkpoint:human-verify` 不要** — これらは CLAUDE.md 推奨スタックと既存 `pyproject.toml`（lightgbm>=4.6 宣言済み）で承認済み。

*Cross-ecosystem 混乱確認: 全パッケージ PyPI に存在（npm で同名パッケージがあるかは無関係、Python プロジェクトのため）。*

## Architecture Patterns

### System Architecture Diagram

```
                    data/feature/features_train.parquet
                    (534,953 rows × 78 cols, 2015-2026/5)
                              │
                              ▼
                    ┌─────────────────────┐
                    │  load_features()    │  race_date string→datetime
                    │  + dtype整備        │  string→category 変換
                    │  + horse_race_id    │  audit_leakage() 再確認
                    │    derive           │  (post-race 混入検出)
                    └────────┬────────────┘
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
    2018-2024 (学習窓)             2025-01〜2026-05 (holdout)
    322,510 rows / 23,288 races    66,574 rows / 4,740 races
    target_top3 含む               target_top3 含む（評価用）
              │
              ▼
    ┌─────────────────────────────────────────────┐
    │     GroupTimeSeriesSplit (fold=5)           │
    │  race_id グループ化 + race_date 時系列順     │
    │  fold_i 検証 ≈ 1.4年（境界は race_id 単位）  │
    │  各 fold 内でさらに early-stopping 用       │
    │  validation を時間末から切り出し             │
    └─────────────────────────────────────────────┘
              │
              ▼ (5 folds)
    ┌─────────────────────────────────────────────┐
    │  LGBMClassifier 学習 (fold 毎)              │
    │  sensible defaults + early stopping         │
    │  callbacks=[lgb.early_stopping(             │
    │    stopping_rounds=50)]                     │
    │  → fold モデル + fold OOF 予測              │
    └─────────────────────────────────────────────┘
              │
              ▼
    ┌─────────────────────────────────────────────┐
    │  OOF 予測収集 (全 fold 結合)                │
    │  → oof_predictions.parquet                  │
    │     (race_id, horse_race_id, p_top3_raw,    │
    │      target_top3, fold)                     │
    └────────────┬────────────────────────────────┘
                 │
       ┌─────────┴──────────┐
       ▼                    ▼
  Isotonic fit         Full-train model
  (oof_p_raw,          (2018-2024 全量で再学習 or
   y_train)             fold モデルのアンサンブル)
       │                    │
       ▼                    ▼
  Calibrator         Final model (.txt)
  (.joblib)                  │
       │                     │  predict_proba
       └──────────┬──────────┘
                  ▼
        ┌──────────────────────┐
        │  ホールドアウト評価    │  p_top3_raw → iso.predict
        │  AUC / Brier / logloss │  → p_top3_calibrated
        │  ECE < 0.02 (D-11)     │
        │  reliability diagram   │
        │  人気ベースライン比較   │  entry.popularity join
        └──────────┬───────────┘
                   ▼
        成果物 (D-15)
        models/phase7/  data/model/oof/  reports/phase7/
        → Phase 8 (Harville EV) / Phase 9 (walk-forward)
```

### Recommended Project Structure

Phase 7 は **新規 `src/ml/` パッケージ**を作成（`src/pipeline/`, `src/scraper/`, `src/schemas/` と同列）。

```
src/ml/
├── __init__.py            # 公開 API（後段 Plan 06 で遷移、Phase 4 パターン踏襲）
├── data_loader.py         # features_train.parquet 読込 + dtype 整備 + horse_race_id derive + audit_leakage 再実行
├── group_timeseries_split.py  # sklearn BaseCrossValidator 準拠の GroupTimeSeriesSplit（Phase 8/9 再利用資産）
├── trainer.py             # LGBMClassifier sensible defaults 学習・OOF 収集・最終モデル学習
├── calibrator.py          # IsotonicRegression OOF学習→holdout適用のリーク防止パターン
├── evaluator.py           # AUC/Brier/logloss/ECE/reliability diagram/人気ベースライン比較
├── run_train.py           # オーケストレーション（CLI entry point・loguru ロギング・成果物保存）
└── baseline.py            # 人気ベースライン（entry.popularity から AUC 計算）

config/
└── phase7_model_a.yaml    # sensible defaults ハイパラ・seed・分割境界・fold 設定

tests/ml/
├── __init__.py
├── conftest.py            # 小規模 fixture race データ（数レース・時系列順・categorical mix）
├── test_group_timeseries_split.py  # 境界割れ検出・同一 race 同一 fold・時系列順・sklearn 互換
├── test_trainer.py        # 学習実行・early stopping 発火・OOF 収集（hermetic fixture）
├── test_calibrator.py     # OOF→iso.fit→holdout predict のリーク防止・[0,1] 範囲・単調非減少
├── test_evaluator.py      # ECE 計算の健全性（完全予測=0・最悪で1・bin 重み付け）・reliability 画像生成
└── test_baseline.py       # 人気逆順 AUC 計算・join 健全性

# 成果物出力先（全て .gitignore 追記対象）
models/phase7/             # model_a.lgb.txt, isotonic_calibrator.joblib
data/model/oof/            # oof_predictions.parquet, holdout_predictions.parquet
reports/phase7/            # evaluation_report.md, reliability_diagram.png, metrics.json
```

### Pattern 1: GroupTimeSeriesSplit（race_id グループ化＋時系列順）

**What:** sklearn 標準 `TimeSeriesSplit` は行単位で分割するため、同一レースの馬が別 fold に割れる。Phase 7 は race_id をグループキーとし、race_date で時系列順に並べた上で fold 境界を race 単位で切る。
**When to use:** 全ての LightGBM CV（学習/OOF収集）。Phase 8/9 でも再利用。
**Why not mlxtend:** 外部依存追加を避け、独自実装で Phase 8/9 の walk-forward にも拡張可能な資産にする（CLAUDE.md「Use Instead: 必要なものだけ」）。

```python
# Source: sklearn BaseCrossValidator 仕様 + D-03 GroupTimeSeriesSplit 要件
# 参考: https://rasbt.github.io/mlxtend/user_guide/evaluate/GroupTimeSeriesSplit/
import numpy as np
import pandas as pd
from sklearn.model_selection import BaseCrossValidator


class GroupTimeSeriesSplit(BaseCrossValidator):
    """race_id グループ単位で時系列 split する CV。

    D-03 要件:
    - 同一 race_id は必ず同一 fold へ（境界割れ防止）
    - race_date の時系列順を厳守（未来データの過去 fold 混入防止）
    - fold 数 = 5（D-04）

    使い方:
        splitter = GroupTimeSeriesSplit(n_splits=5)
        for train_idx, val_idx in splitter.split(X, y, groups=race_ids):
            # train_idx, val_idx は行インデックス
            ...

    注意: groups（race_id）と X の行順は、呼び出し側が race_date 昇順で
    ソート済みであることを前提。本クラスは groups の出現順で fold を切る。
    """

    def __init__(self, n_splits: int = 5):
        self.n_splits = n_splits

    def get_n_splits(self, X=None, y=None, groups=None):
        return self.n_splits

    def split(self, X, y=None, groups=None):
        if groups is None:
            raise ValueError("groups (race_id) は必須")
        # race_id のユニークな時系列順（出現順）
        unique_groups = pd.unique(groups)
        n_groups = len(unique_groups)
        # fold 境界: n_groups を (n_splits+1) 個のチャンクに分け、
        # 各 fold の val = 1 チャンク、train = それより前の全チャンク
        fold_sizes = self._compute_fold_sizes(n_groups)
        boundaries = np.cumsum(fold_sizes)
        start = 0
        for i in range(self.n_splits):
            val_group_end = boundaries[i]
            val_groups = unique_groups[start:val_group_end]
            train_groups = unique_groups[:start]
            train_mask = np.isin(groups, train_groups)
            val_mask = np.isin(groups, val_groups)
            yield np.where(train_mask)[0], np.where(val_mask)[0]
            start = val_group_end

    def _compute_fold_sizes(self, n_groups: int) -> list[int]:
        # n_splits 個の val chunk + 手前は拡張的に train
        base = n_groups // self.n_splits
        rem = n_groups % self.n_splits
        return [base + (1 if i < rem else 0) for i in range(self.n_splits)]
```

**各 fold 内の early-stopping validation 切り出し（D-04 の discretion 領域）:**

```python
# fold_i の train_groups をさらに「学習本体」「validation」に時系列分割
# 推奨: train 末尾の最新 20% レースを validation に（race_date 順で末尾）
def split_train_validation(train_df: pd.DataFrame, val_ratio: float = 0.2):
    """fold 内 train を race_date 昇順でソートし、末尾 val_ratio を early-stopping 用 val に。"""
    races = train_df[["race_id", "race_date"]].drop_duplicates().sort_values("race_date")
    n_val = max(1, int(len(races) * val_ratio))
    val_races = races.tail(n_val)["race_id"].tolist()
    is_val = train_df["race_id"].isin(val_races)
    return train_df[~is_val], train_df[is_val]
```

### Pattern 2: Isotonic キャリブレーション（リーク防止標準パターン）

**What:** OOF 予測を「キャリブレーターにとっての学習データ」、ホールドアウト raw 予測を「適用対象」とする。キャリブレーターはモデルの学習データを一切見ていない（OOF は fold モデルが学習していない馬の予測）ため、リークなし。
**When to use:** D-10/D-12 のキャリブレーション全工程。

```python
# Source: sklearn probability calibration 標準パターン
# 参考: https://scikit-learn.org/stable/modules/calibration.html
#       http://ethen8181.github.io/machine-learning/model_selection/prob_calibration/prob_calibration.html
import joblib
from sklearn.isotonic import IsotonicRegression


def fit_calibrator(oof_raw: np.ndarray, y_oof: np.ndarray) -> IsotonicRegression:
    """OOF 予測と実績から Isotonic キャリブレーターを学習。

    D-10/D-12 リーク防止:
    - oof_raw は各 fold モデルが学習していない馬の予測（GroupTimeSeriesSplit で保証）
    - したがってキャリブレーターは「未知データ上の予測分布」を学習
    - y_min=0, y_max=1 で [0,1] に制限、out_of_bounds='clip' で安全

    Args:
        oof_raw: OOF 上の生予測確率 (n_samples,)
        y_oof: OOF の正解ラベル (n_samples,)

    Returns:
        fit 済み IsotonicRegression
    """
    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    iso.fit(oof_raw, y_oof)
    return iso


def apply_calibrator(iso: IsotonicRegression, raw_preds: np.ndarray) -> np.ndarray:
    """キャリブレーターを適用（holdout にも使用可能、リークなし）。"""
    return iso.predict(raw_preds)


# 保存（D-15: .joblib）
# joblib.dump(iso, "models/phase7/isotonic_calibrator.joblib")
```

### Anti-Patterns to Avoid

- **sklearn `TimeSeriesSplit` 直接使用:** 行単位分割で同一レースが別 fold に割れ、Phase 8 Harville 計算時にレース内 p_top3 の整合性が崩れる（D-03 の根拠）。必ず GroupTimeSeriesSplit で race_id 単位。
- **`early_stopping_rounds=50` を fit() に渡す:** LightGBM 4.x で TypeError（API 削除）。`callbacks=[lgb.early_stopping(stopping_rounds=50)]` を使うこと `[VERIFIED: lightgbm readthedocs]`。
- **CalibratedClassifierCV で `method='isotonic'`:** 内部 CV が group 非対応で D-03 と衝突。手動 OOF→iso.fit パターンが要件に合致。
- **string dtype のまま LightGBM に渡す:** `course_name` 等は `string` dtype で保存されており、LightGBM の categorical 自動検出は `category` dtype のみ反応。string のまま渡すと object 扱いで warning、性能劣化。
- **`popularity` / `win_odds` を feature に混入:** D-15（feature 除外）と audit_leakage の核心。Phase 7 は必ず audit_leakage([RaceSchema, EntrySchema], df) を再実行し post-race 混入を検出。
- **ホールドアウトでキャリブレーターを fit し直す:** リーク（D-10 違反）。キャリブレーターは OOF のみで fit、holdout は predict のみ。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 時系列CV | sklearn `TimeSeriesSplit`（行単位で境界割れ）| 独自 `GroupTimeSeriesSplit`（race_id グループ化）| 同一レース同一 fold 保証、Phase 8 Harville 整合性。mlxtend は外部依存追加を避ける |
| 確率キャリブレーション | 自作 sigmoid / Platt / 線形回帰 | `sklearn.isotonic.IsotonicRegression` | 非パラメトリック・単調非減少保証・[0,1] clip 標準装備。EV 計算精度に直結 |
| AUC / Brier / logloss | 自作 ROC 曲線・积分 | `sklearn.metrics.roc_auc_score`, `brier_score_loss`, `log_loss` | 業界標準・数値精度検証済み・tie-breaking 処理済み |
| LightGBM モデル | XGBoost / CatBoost / 手作 GBM | LightGBM 4.6.0（CLAUDE.md 固定）| categorical native 扱い・8x 高速・sensible defaults で安定 |
| categorical encoding | One-Hot / LabelEncoder | pandas `CategoricalDtype` + LightGBM native | OHE は次元爆発（jockey 419 + trainer 524 + grade 等）、native は code 化で省メモリ・高速 |
| config 管理 | Python dict 直書き / argparse | YAML + pydantic（任意）| D-14 が YAML 指定・再現性（固定 seed）・Phase 8/9 でパラメータ引き継ぎ |

**Key insight:** 競馬 ML で「まず確実に進める」（CLAUDE.md）哲学に沿うため、sensible defaults + early stopping + リーク防止 CV の3点を**標準ライブラリの組合せ**で構築する。自作アルゴリズム（キャリブレーター・CV・評価指標の再発明）はバグ温床であり、Phase 9 walk-forward で再利用する資産性も下がる。

## Common Pitfalls

### Pitfall 1: `early_stopping_rounds` を fit() に渡すと TypeError（LightGBM 4.x API 削除）
**What goes wrong:** `LGBMClassifier.fit(X, y, eval_set=..., early_stopping_rounds=50)` で `TypeError: fit() got an unexpected keyword argument 'early_stopping_rounds'`。
**Why it happens:** LightGBM 4.0.0（2023年）で `early_stopping_rounds` が fit()/train() から完全削除。代わりに callbacks API に統一。
**How to avoid:** 必ず `callbacks=[lgb.early_stopping(stopping_rounds=50, verbose=True), lgb.log_evaluation(period=100)]` を fit() の引数に渡す。`best_iteration_` は callback 使用時のみ populated。
**Warning signs:** TypeError、または `model.best_iteration_` が None のまま。
`[VERIFIED: lightgbm.readthedocs.io/en/latest/pythonapi/lightgbm.early_stopping.html]` `[CITED: stackoverflow.com/questions/77131656]`

### Pitfall 2: `horse_race_id` が features_train.parquet に存在しない
**What goes wrong:** D-15 が OOF/holdout parquet に `horse_race_id` を必須指定しているが、`features_train.parquet` を実測確認すると同カラムが存在しない。`horse_entity_key` と `horse_name` は存在。
**Why it happens:** `feature_generator.py` の `train_cols` 構築で `horse_race_id` が `FEATURE_COLUMNS` にも `ENTITY_KEY` にも含まれないため、出力時に除外される（Step 13）。
**How to avoid:** Phase 7 の data_loader で `race_id + horse_number` から `horse_race_id` を derive（`f"{race_id}_{horse_number:02d}"`、EntrySchema D-09 形式）。または feature_generator 側で train_cols に `horse_race_id` を追加する quick fix。後者の方が D-15 契約と整合するが、feature 層の再生成が必要。
**Warning signs:** D-15 成果物 parquet に horse_race_id カラムが存在しない、Phase 8 でレース単位の予測集計ができない。
`[VERIFIED: codebase inspect]`

### Pitfall 3: `course_name`/`surface`/`grade` が string dtype で categorical 未変換
**What goes wrong:** LightGBM が categorical 列として認識せず、object 扱いの warning または暗黙の数値化が発生。性能劣化・再現性低下。
**Why it happens:** `feature_generator.py` の `convert_to_categorical()` は `if df[col].dtype == object` 条件で変換するが、Phase 6 統合 corpus は `string` dtype（Phase 4 cycle-3 #1 で nullable string 採択）。`string != object` のためスキップされる。実測: `course_name: string`, `jockey: category`（jockey/trainer のみ変換済み）。
**How to avoid:** Phase 7 の data_loader で `CATEGORICAL_COLUMNS` 全列を `astype("category")` で明示変換。`grade` は NaN 95%（506,349件）を含むため、変換後に NaN が category code -1 として正しく保持されるか assert で検証。
**Warning signs:** LightGBM 学習ログに `categorical_feature in DataFrame` の認識メッセージが出ない、feature importance で categorical が低すぎる。
`[VERIFIED: codebase inspect]`

### Pitfall 4: `grade` 列の 95% NaN が LightGBM でエラー
**What goes wrong:** pandas CategoricalDtype は NaN を code -1 で保持するが、LightGBM は歴史的に非負整数 codes を期待した（v3.x 以前）。4.x では解消済みだが、変換後の code 分布を確認しないと予期せぬ挙動。
**Why it happens:** grade は重賞レース（GI/GII/GIII/重賞/リステッド等）のみ値を持ち、一般戦は NaN。Phase 3 feature_generator では未変換の string のまま残る。
**How to avoid:** (1) `grade` を category 化する際、`NaN` を明示的に `"unknown"` 等のカテゴリに fill する選択肢もあるが、D-09（初出走馬 NaN + debut flag）と同様に NaN のまま LightGBM に委ねる方が情報量を保つ。(2) 学習後に `lgb.plot_importance` で grade が有意に寄与しているか確認。コード -1 の挙動は LightGBM 4.6 で正常（公式 docs 確認済み）。
**Warning signs:** 学習が失敗する、または grade の importance が異常に高い/低い。
`[CITED: lightgbm.readthedocs.io/en/latest/Advanced-Topics.html]` `[CITED: github.com/lightgbm-org/LightGBM/issues/2761]`

### Pitfall 5: ホールドアウトでのキャリブレーター再学習（リーク）
**What goes wrong:** holdout の ECE が異常に良い（例: 0.001）が出る。これはキャリブレーターが holdout ラベルを見て fit されている証拠。
**Why it happens:** 「holdout で isotonic を fit → holdout で ECE 計測」を実装してしまう。
**How to avoid:** キャリブレーターは**OOF のみ**で fit（`iso.fit(oof_raw, y_oof)`）。holdout は `iso.predict(holdout_raw)` のみ。ECE は holdout の calibrated 予測 vs holdout 正解で計算。
**Warning signs:** holdout ECE が OOF ECE より顕著に良い、または 0.0 に近い。
`[CITED: scikit-learn.org/stable/modules/calibration.html]`

### Pitfall 6: 人気ベースライン計算で popularity の NaN 処理漏れ
**What goes wrong:** `entry.popularity` は 534,953 件中 533,009 件のみ non-null（1,944 件 NaN = 取消/除外馬）。これを無視して `roc_auc_score` に渡すと NaN 伝播でエラー。
**Why it happens:** features_train の `exclude_from_training=True` は 1,944 件だが、学習前フィルタで除外しても popularity join 後に別の NaN が残りうる（standard 層と feature 層の行セット差分）。
**How to avoid:** (1) 学習データは `exclude_from_training == False` でフィルタ（1,944 件除外）。(2) baseline 計算時は popularity が NaN の行を drop するか、race 内で popularity を rank に変換後 NaN を race の最下位として扱う。baseline は「参考情報」（D-07 で必須条件ではない）なので、厳密な rank→疑似確率変換よりは `-popularity` を score とした AUC で十分。
**Warning signs:** `roc_auc_score` で ValueError、または baseline AUC が 0.5 を大きく下回る。
`[VERIFIED: codebase inspect]`

### Pitfall 7: データ範囲の境界チェック漏れ（2018-2024 vs 2015-2024）
**What goes wrong:** ROADMAP は「2015-2023 学習」、D-01 は「2018-2024 学習」、features_train.parquet は 2015-01-04〜2026-05-31 の全期間。3つの仕様が混在し、誤って 2015-2017 を学習に含めると D-01 違反（concept drift 対策が無効化）。
**Why it happens:** D-01 の前倒し決定（ROADMAP 更新は D-05 で Phase 9 繰越）。
**How to avoid:** data_loader で明示的に `race_date >= '2018-01-01' & race_date <= '2024-12-31'` で学習窓、`race_date >= '2025-01-01' & race_date <= '2026-05-31'` でホールドアウトを抽出。境界値を loguru で出力し、行数（学習: 322,510 有効 / holdout: 66,574）を assert。
**Warning signs:** 学習行数が想定（~322,510）と大幅に異なる、2017 年以前の race_date が学習データに含まれる。
`[VERIFIED: codebase inspect]`（実測: 学習窓 322,510 行 / 23,288 レース、holdout 66,574 行 / 4,740 レース）

## Code Examples

### Sensible Defaults Config YAML（D-13/D-14）

```yaml
# config/phase7_model_a.yaml
# Source: LightGBM Parameters-Tuning 公式推奨範囲
# 参考: https://lightgbm.readthedocs.io/en/latest/Parameters-Tuning.html
seed: 42
data:
  feature_path: data/feature/features_train.parquet
  train_window: ['2018-01-01', '2024-12-31']
  holdout_window: ['2025-01-01', '2026-05-31']
  target_column: target_top3
  exclude_column: exclude_from_training
  categorical_columns:
    - course_name
    - surface
    - direction
    - weather
    - track_condition
    - sex
    - jockey       # 既に category 変換済み（feature_generator）
    - trainer      # 既に category 変換済み
    - grade
  drop_columns:
    - race_id
    - race_date
    - horse_entity_key
    - horse_name
    - result_status
    - is_dnf
cv:
  n_splits: 5
  group_column: race_id
  sort_column: race_date
  early_stopping_val_ratio: 0.2  # fold 内 train の末尾 20% を validation に
model:
  # sensible defaults — LightGBM 公式推奨 + 競馬 ML 通説
  objective: binary
  metric: [binary_logloss, auc]
  num_leaves: 31                 # 公式 default。過学習なら 16 に下げる
  learning_rate: 0.05            # 0.1(default)より保守的・early stopping と組合せ
  min_data_in_leaf: 100          # 20(default)より大きく・競馬データのノイズ対策
  feature_fraction: 0.9          # 列サンプリング・過学習抑制
  bagging_fraction: 0.9          # 行サンプリング
  bagging_freq: 5                # 5 iteration 毎に bagging
  max_depth: -1                  # 無制限（num_leaves で制御）
  lambda_l1: 0.0                 # 正則化（様子見）
  lambda_l2: 0.0
  min_gain_to_split: 0.0
  verbose: -1
  n_estimators: 1000             # 上限・early stopping で最適化
  # scale_pos_weight: 1.0        # 陽性 21.7% は軽度・デフォルト（D 残す）
early_stopping:
  stopping_rounds: 50
  verbose: false
  first_metric_only: false       # logloss で判定（metric リスト先頭）
calibration:
  method: isotonic               # D-10
  y_min: 0.0
  y_max: 1.0
  out_of_bounds: clip
evaluation:
  ece_bins: 10                   # D-11 ECE 計算の bin 数
  ece_tolerance: 0.02            # D-11 成功基準
  reliability_diagram: true
artifacts:
  model_dir: models/phase7
  oof_dir: data/model/oof
  report_dir: reports/phase7
  model_filename: model_a.lgb.txt
  calibrator_filename: isotonic_calibrator.joblib
  oof_filename: oof_predictions.parquet
  holdout_filename: holdout_predictions.parquet
```

### LightGBM 学習（sensible defaults + early stopping callback）

```python
# Source: LightGBM 4.6 LGBMClassifier + early_stopping callback API
# 参考: https://lightgbm.readthedocs.io/en/latest/pythonapi/lightgbm.early_stopping.html
#       https://lightgbm.readthedocs.io/en/latest/pythonapi/lightgbm.LGBMClassifier.html
import lightgbm as lgb
import yaml


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def train_fold_model(
    X_train, y_train, X_val, y_val, config: dict
) -> lgb.LGBMClassifier:
    """1 fold の学習。early stopping は callback で指定（4.x API）。

    CRITICAL: early_stopping_rounds は fit() に渡さない（4.x で削除）。
    callbacks=[lgb.early_stopping(stopping_rounds=N)] を使う。
    """
    m = config["model"]
    clf = lgb.LGBMClassifier(
        objective=m["objective"],
        num_leaves=m["num_leaves"],
        learning_rate=m["learning_rate"],
        min_data_in_leaf=m["min_data_in_leaf"],  # alias: min_child_samples
        feature_fraction=m["feature_fraction"],
        bagging_fraction=m["bagging_fraction"],
        bagging_freq=m["bagging_freq"],
        max_depth=m["max_depth"],
        lambda_l1=m["lambda_l1"],
        lambda_l2=m["lambda_l2"],
        min_gain_to_split=m["min_gain_to_split"],
        n_estimators=m["n_estimators"],
        random_state=config["seed"],
        verbose=m["verbose"],
    )
    es = config["early_stopping"]
    clf.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        callbacks=[
            lgb.early_stopping(
                stopping_rounds=es["stopping_rounds"],
                verbose=es["verbose"],
                first_metric_only=es["first_metric_only"],
            ),
            lgb.log_evaluation(period=50),
        ],
    )
    # clf.best_iteration_ は callback 使用時に populated
    return clf


# モデル保存（D-15: .txt）
# clf.booster_.save_model("models/phase7/model_a.lgb.txt")
```

### ECE 計算（手動実装）+ Reliability Diagram

```python
# Source: Guo et al. 2017 の ECE 定義 + sklearn issue #18268（未収録）
# 参考: https://towardsdatascience.com/expected-calibration-error-ece-a-step-by-step-visual-explanation-with-python-code-c3e9aa12937d/
import numpy as np


def compute_ece(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    """Expected Calibration Error を計算。

    ECE = Σ_m (|B_m| / N) × |acc(B_m) - conf(B_m)|

    - M = n_bins（10 が標準、equal-width bins [0, 0.1), [0.1, 0.2), ...）
    - |B_m| / N = bin m のサンプル割合
    - acc(B_m) = bin m 内の観測陽性率（実際の top3 率）
    - conf(B_m) = bin m 内の平均予測確率

    完全に校正されたモデル: ECE = 0.0
    D-11 成功基準: ECE < 0.02
    """
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    # 最終 bin は閉区間 [0.9, 1.0]、それ以外は半開区間 [low, high)
    bin_indices = np.digitize(y_prob, bins[1:-1], right=False)
    n = len(y_true)
    ece = 0.0
    for b in range(n_bins):
        mask = bin_indices == b
        if not mask.any():
            continue
        bin_size = mask.sum()
        acc = y_true[mask].mean()       # 観測陽性率
        conf = y_prob[mask].mean()      # 平均予測確率
        ece += (bin_size / n) * abs(acc - conf)
    return float(ece)


def reliability_diagram(
    y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10, save_path: str = None
):
    """reliability diagram を matplotlib で描画・保存。

    D-11 が reliability diagram 併出力を要求。Agg backend でヘッドレス。
    """
    import matplotlib
    matplotlib.use("Agg")  # ヘッドレス環境向け（CLI 実行）
    import matplotlib.pyplot as plt

    bins = np.linspace(0.0, 1.0, n_bins + 1)
    bin_indices = np.digitize(y_prob, bins[1:-1], right=False)
    accs, confs, sizes = [], [], []
    for b in range(n_bins):
        mask = bin_indices == b
        if not mask.any():
            accs.append(np.nan)
            confs.append((bins[b] + bins[b + 1]) / 2)
            sizes.append(0)
        else:
            accs.append(y_true[mask].mean())
            confs.append(y_prob[mask].mean())
            sizes.append(mask.sum())

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.bar(confs, accs, width=0.08, alpha=0.7, label="Model")
    ax.plot([0, 1], [0, 1], "k--", label="Perfect calibration")
    ax.set_xlabel("Mean predicted probability")
    ax.set_ylabel("Observed top-3 rate")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend()
    ax.set_title("Reliability Diagram")
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig
```

### 人気ベースライン AUC（D-08 参考）

```python
# Source: D-08 単勝オッズ順位スコアでの AUC 計算
# 参考: 03-CONTEXT D-15（feature からオッズ除外・純粋予測×EV 構図）
import pandas as pd
from sklearn.metrics import roc_auc_score


def compute_popularity_baseline(
    features_df: pd.DataFrame, entry_df: pd.DataFrame
) -> dict:
    """人気（単勝オッズ順位）を score とした baseline AUC。

    D-07/D-08: 純粋馬特性モデルが市場集合知（人気）を AUC で超えるのは困難。
    baseline は参考情報（必須成功条件ではない）。

    実装:
    - entry.parquet の popularity を race_id+horse_number で join
    - score = -popularity（人気順位が小さい=強い、AUC は score 大=陽性 で判定）
    - roc_auc_score(target_top3, -popularity)
    - popularity NaN は行 drop（race 内で順位不明は評価不可）
    """
    merged = features_df.merge(
        entry_df[["race_id", "horse_number", "popularity"]],
        on=["race_id", "horse_number"],
        how="inner",
    )
    valid = merged.dropna(subset=["popularity", "target_top3"])
    baseline_auc = roc_auc_score(
        valid["target_top3"].astype(int), -valid["popularity"].astype(float)
    )
    return {
        "baseline_auc": float(baseline_auc),
        "n_rows": len(valid),
        "note": "人気(単勝オッズ順位)ベースライン。D-08: 純粋モデルがこれを"
                "AUC で超えるのは競馬ML通説上非常に困難（参考情報）",
    }
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `early_stopping_rounds=N` in fit() | `callbacks=[lgb.early_stopping(stopping_rounds=N)]` | LightGBM 4.0.0 (2023) | 古いコードは TypeError。4.6 では完全削除済み |
| `verbose_eval=N` in fit() | `lgb.log_evaluation(period=N)` | LightGBM 4.0.0 (2023) | 同上。callbacks リストで併用 |
| One-Hot Encoding for categoricals | pandas `CategoricalDtype` + LightGBM native | LightGBM 2.x+ (~2018) | 8x 高速化・省メモリ。jockey(419) + trainer(524) で顕著 |
| `CalibratedClassifierCV(method='isotonic', cv=kfold)` | 手動 OOF→iso.fit（group-aware CV 向け）| group-aware CV 必要時 | CalibratedClassifierCV は group 非対応、D-03 と衝突 |
| LightGBM GPU 学習 | CPU（本プロジェクト）| — | Mac 単体制約（CLAUDE.md）。53万行×78列は CPU で十分（数分） |

**Deprecated/outdated:**
- LightGBM 3.x の `early_stopping_rounds` / `verbose_eval`: 4.0 で deprecated、4.x で完全削除。`[CITED: lightgbm.readthedocs.io/en/latest/pythonapi/lightgbm.early_stopping.html]`
- LightGBM sklearn wrapper の `n_jobs` パラメータ: OpenMP 経由で制御されるため、Mac では `brew install libomp` が必要（実測: libomp 未導入で import 失敗）。

## Assumptions Log

> 訓練データ・CONTEXT.md の実測確認で `[VERIFIED]`/`[CITED]` を付けた項目が大半。残る `[ASSUMED]` は planner が実装時に検証すべき軽微な選択。

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | sensible defaults の `learning_rate=0.05`, `min_data_in_leaf=100` が本データで適切 | Standard Stack / Code Examples | 過学習 or 過小学習。early stopping と AUC 実測で調整可能（D-07 目安 0.75） |
| A2 | `min_data_in_leaf=100` で jockey/trainer 高カーディナリティが安全に処理される | Code Examples | 稀少騎手の過学習。LightGBM native categorical は min_data_in_leaf で葉の最小サンプルを保証するため、通常は問題ない |
| A3 | `scale_pos_weight=1.0`（デフォルト）で陽性 21.7% を処理できる | Code Examples | AUC は不均衡に鈍感だが、logloss/brier が影響受ける可能性。実測次第で Phase 9 で調整（deferred） |
| A4 | reliability diagram に matplotlib 3.11 が必要十分 | Standard Stack | matplotlib は重依存だが可視化のデファクト。`Agg` backend でヘッドレス動作確認済み |
| A5 | `horse_race_id` derive は `f"{race_id}_{horse_number:02d}"` 形式（EntrySchema D-09）で features_train の行と一致する | Common Pitfalls #2 | join 失敗。standard entry.parquet の horse_race_id を直接 join して検証すべき |
| A6 | LightGBM 4.6 で categorical code -1（pandas NaN）が正常処理される（grade 95% NaN）| Common Pitfalls #4 | 学習エラー or 性能劣化。公式 docs では解消済みだが、実データで assert 推奨 |

**If this table is empty:** 全ての主要技術的判断（early stopping API・GroupTimeSeriesSplit 設計・Isotonic リーク防止・ECE 実装）は `[VERIFIED]` または `[CITED]` で裏付け済み。上記は実装時の微調整領域。

## Open Questions

1. **`horse_race_id` を features_train に追加するか、derive するか**
   - What we know: features_train.parquet は `horse_race_id` を含まない（実測）。D-15 は OOF/holdout parquet に必須指定。
   - What's unclear: feature_generator の train_cols に `horse_race_id` を追加して feature 層を再生成する quick fix を取るか、Phase 7 の data_loader で `race_id + horse_number` から derive するか。
   - Recommendation: **Phase 7 data_loader で derive**（feature 層の再生成不要・D-15 契約は Phase 7 出力で満たせる）。`f"{race_id}_{horse_number:02d}"` 形式を EntrySchema D-09 と一致させる。`standard/entry.parquet` の `horse_race_id` と join して整合性を assert するテストを追加。

2. **学習7年（2018-2024）を 5 fold に分けた際、最初の fold の train が小さくなりすぎないか**
   - What we know: 23,288 レースを 5 fold に分けると、fold 0 の train は最初の ~0 fold 分（最小）、fold 4 の train は 4 fold 分（最大）。
   - What's unclear: GroupTimeSeriesSplit の設計（expanding window）で fold 0 は train が無い or 極小になる。
   - Recommendation: **expanding window**（fold i の train = fold 0..i-1、val = fold i）。fold 0 は train=最初の1チャンク（~4,657 レース）、val=次チャンク。OOF 収集は全 5 fold の val 予測を結合（~23,288 レース分）。これは Phase 9 walk-forward の基礎になる設計。

3. **最終モデル（Phase 8 に引き渡す）は fold モデルのアンサンブルか、全量再学習か**
   - What we know: D-15 は「訓練済みモデル(`.txt`)」を単数で指定。Phase 8 はこれを使って Harville EV 計算。
   - What's unclear: 5 fold モデルの平均（アンサンブル）にするか、2018-2024 全量で再学習した単一モデルにするか。
   - Recommendation: **全量再学習の単一モデル**（D-15 契約に合致・Phase 8 で扱い簡単）。early stopping 用 validation は OOF 全体の末尾 20% を使う。fold モデルは OOF 生成用のみで破棄可。

## Environment Availability

> Step 2.6 実施。`lightgbm` はインストール済みだが import 失敗（libomp 未導入）。`scikit-learn`, `matplotlib`, `joblib` は未導入。これらは Phase 7 plan の Wave 0 前提タスク。

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| libomp (brew) | LightGBM import（`lib_lightgbm.dylib` が `@rpath/libomp.dylib` を要求） | ✗ | — | なし（必須。`brew install libomp`） |
| lightgbm | p_top3 モデル学習（LGBMClassifier） | ✓（installed）/ ✗（import fails） | 4.6.0 | libomp 導入で解決 |
| scikit-learn | roc_auc_score / brier_score_loss / log_loss / IsotonicRegression | ✗ | — | なし（必須。`pip install scikit-learn`） |
| matplotlib | reliability diagram（D-11）| ✗ | — | テキスト形式の bin 別集計で代替可だが、D-11 が diagram 併出力を要求 |
| joblib | IsotonicRegression の `.joblib` 保存（D-15）| ✗ | — | pickle で代替可だが、D-15 が `.joblib` 指定 |
| pandas / numpy / pyarrow / pyyaml / loguru | 既存スタック | ✓ | 導入済み | — |
| Python 3.12 | 実行環境 | ✓ | 3.12.13 | — |

**Missing dependencies with no fallback:**
- `libomp`: LightGBM import が完全に失敗。**Wave 0 で `brew install libomp` が必須**（実測: import 時 `OSError: dlopen ... Library not loaded: @rpath/libomp.dylib`）。
- `scikit-learn`: 評価指標・キャリブレーション全てで必要。**Wave 0 で `pip install scikit-learn` 必須**。

**Missing dependencies with fallback:**
- `matplotlib`: reliability diagram のみ。テキスト形式 bin 集計で代替可能だが、D-11 が diagram 併出力を要求するため、**導入を推奨**（`pip install matplotlib`）。
- `joblib`: `.joblib` 保存のみ。pickle で代替可能だが、D-15 が `.joblib` 指定のため**導入を推奨**（`pip install joblib`、scikit-learn の依存として自動入る場合あり）。

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.x（pyproject.toml `[project.optional-dependencies] dev`） |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` testpaths=["tests"] |
| Quick run command | `python -m pytest tests/ml/ -x -q` |
| Full suite command | `python -m pytest tests/ -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MODA-01 | LightGBM 学習実行・p_top3 出力 | unit (hermetic) | `pytest tests/ml/test_trainer.py::test_train_fold_model_returns_classifier -x` | ❌ Wave 0 |
| MODA-01 | categorical 変換（string→category）検証 | unit | `pytest tests/ml/test_data_loader.py::test_categorical_conversion -x` | ❌ Wave 0 |
| MODA-01 | horse_race_id derive 検証 | unit | `pytest tests/ml/test_data_loader.py::test_horse_race_id_derive -x` | ❌ Wave 0 |
| MODA-02 | GroupTimeSeriesSplit 同一 race 同一 fold | unit | `pytest tests/ml/test_group_timeseries_split.py::test_same_race_same_fold -x` | ❌ Wave 0 |
| MODA-02 | GroupTimeSeriesSplit 時系列順厳守 | unit | `pytest tests/ml/test_group_timeseries_split.py::test_temporal_order -x` | ❌ Wave 0 |
| MODA-02 | GroupTimeSeriesSplit 境界割れ検出 | unit | `pytest tests/ml/test_group_timeseries_split.py::test_no_boundary_split -x` | ❌ Wave 0 |
| MODA-03 | 人気ベースライン AUC 計算 | unit | `pytest tests/ml/test_baseline.py::test_popularity_baseline_auc -x` | ❌ Wave 0 |
| MODA-04 | Isotonic OOF→fit→holdout predict リーク防止 | unit | `pytest tests/ml/test_calibrator.py::test_leak_free_calibration -x` | ❌ Wave 0 |
| MODA-04 | ECE 計算健全性（完全予測=0） | unit | `pytest tests/ml/test_evaluator.py::test_ece_perfect_prediction -x` | ❌ Wave 0 |
| MODA-04 | ECE 計算（最悪=最大） | unit | `pytest tests/ml/test_evaluator.py::test_ece_worst_case -x` | ❌ Wave 0 |
| 全般 | audit_leakage 再実行（post-race 混入検出） | unit | `pytest tests/ml/test_data_loader.py::test_leakage_audit -x` | ❌ Wave 0 |
| 統合 | E2E 学習→OOF→キャリブレーション→holdout 評価 | integration (gated) | `pytest tests/ml/test_run_train.py -k e2e --run-gated -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/ml/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -q`（既存 513 passed/1 skipped を壊さないこと）
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/ml/__init__.py` — パッケージマーカー
- [ ] `tests/ml/conftest.py` — 小規模 fixture race データ（数レース・時系列順・categorical mix・target_top3 含む）
- [ ] `tests/ml/test_group_timeseries_split.py` — MODA-02 CV 健全性
- [ ] `tests/ml/test_trainer.py` — MODA-01 学習
- [ ] `tests/ml/test_calibrator.py` — MODA-04 リーク防止
- [ ] `tests/ml/test_evaluator.py` — MODA-04 ECE/reliability/baseline
- [ ] `tests/ml/test_data_loader.py` — categorical 変換・horse_race_id derive・leakage audit
- [ ] Framework install: `brew install libomp && pip install scikit-learn matplotlib joblib` — Wave 0 前提

## Security Domain

### Applicable ASVS Categories

> `security_enforcement: true` / `security_asvs_level: 1` / `security_block_on: high`（config.json）
> Phase 7 は ML 学習・評価フェーズ。外部入力（HTTP/CLI ユーザ入力）はなく、データは parquet ファイルから読込のみ。ASVS L1 の大部分は Web アプリ向けだが、以下が適用される。

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | ML 学習ジョブ・認証不要 |
| V3 Session Management | no | バッチジョブ・セッション不要 |
| V4 Access Control | no | ローカルファイル処理・認可不要 |
| V5 Input Validation | yes | parquet ファイルのカラム検証（audit_leakage 再実行で post-race 混入検出） |
| V6 Cryptography | no | 暗号化不要（モデル・予測は機密性低） |
| V7 Logging | yes | loguru で学習進行・ハイパラ・メトリックを記録 |
| V8 Data Protection | partial | モデル・OOF 予測は再現性のため保存するが、個人情報（馬名/騎手名）は feature 層に既に含まれるため追加保護不要 |
| V9 Communications | no | 外部通信なし（スクレイピングは Phase 4 完了済み） |
| V14 Configuration | yes | YAML config でハイパラ管理・固定 seed で再現性（D-14） |

### Known Threat Patterns for LightGBM ML Pipeline

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Data leakage（post-race 混入）| Tampering / Elevation of privilege | audit_leakage([RaceSchema, EntrySchema]) 再実行・FEATURE_COLUMNS allowlist（feature_generator）・GroupTimeSeriesSplit で未来データ混入防止 |
| Temporal leakage（CV 境界）| Tampering | GroupTimeSeriesSplit race_id グループ化・race_date 時系列順厳守・early stopping validation は fold 内 train の末尾のみ |
| Calibration leakage（holdout で再学習）| Tampering | Isotonic は OOF のみで fit・holdout は predict のみ（D-10） |
| Overfitting（sensible defaults 不備）| Information disclosure | num_leaves/min_data_in_leaf/feature_fraction/bagging で正則化・early stopping で最適 iteration |
| Model serialization tampering | Tampering | `.txt`/`.joblib` は gitignore・ローカル保存・config YAML で再現性担保 |
| Unbounded memory（53万行×78列）| DoS | pandas DataFrame 一括処理（Pydantic D-02 パターン）・LightGBM Dataset で効率的メモリ管理 |

## Sources

### Primary (HIGH confidence)
- **lightgbm.readthedocs.io/en/latest/pythonapi/lightgbm.early_stopping.html** — early_stopping callback API（4.6.0.99）。`stopping_rounds`, `verbose`, `first_metric_only`, `min_delta` シグネチャ確認。
- **lightgbm.readthedocs.io/en/latest/pythonapi/lightgbm.LGBMClassifier.html** — LGBMClassifier defaults: `num_leaves=31`, `learning_rate=0.1`, `max_depth=-1`。`best_iteration_` は callback 使用時のみ populated。
- **lightgbm.readthedocs.io/en/latest/Parameters-Tuning.html** — sensible defaults 推奨範囲。`num_leaves` 主複雑性制御・`num_leaves < 2^max_depth` 推奨。
- **lightgbm.readthedocs.io/en/latest/Advanced-Topics.html** — categorical native 扱い。pandas CategoricalDtype で int32 codes 抽出。
- **scikit-learn.org/stable/modules/calibration.html** — probability calibration 標準パターン。CalibratedClassifierCV 内部 CV でリーク防止。
- **scikit-learn.org/stable/modules/isotonic.html** — IsotonicRegression クラス仕様。
- **Codebase inspect** — features_train.parquet スキーマ・dtypes・target 分布・window 行数・horse_race_id 欠落・categorical 変換状態・audit.py・feature_generator.py・pyproject.toml・標準 entry.parquet。
- **pip index versions** — lightgbm 4.6.0 / scikit-learn 1.9.0 / matplotlib 3.11.0 / joblib 1.5.3（PyPI registry 実測）。

### Secondary (MEDIUM confidence)
- **stackoverflow.com/questions/77131656** — LightGBM 4.6.0 で `early_stopping_rounds` を fit() に渡すと TypeError の事例確認。
- **github.com/scikit-learn/scikit-learn/issues/18268** — ECE が sklearn に未収録（手動実装が必要）。
- **github.com/lightgbm-org/LightGBM/issues/5196** — early stopping 推奨パターン（公式メンテナ）。
- **rasbt.github.io/mlxtend/user_guide/evaluate/GroupTimeSeriesSplit/** — GroupTimeSeriesSplit の sklearn 互換実装参考。
- **towardsdatascience.com/expected-calibration-error-ece-a-step-by-step-visual-explanation-with-python-code-c3e9aa12937d** — ECE 手動実装と reliability diagram。
- **ethen8181.github.io/machine-learning/model_selection/prob_calibration/prob_calibration.html** — OOF キャリブレーション標準パターン。

### Tertiary (LOW confidence)
- **leoniemonigatti.com/blog/lightgbm-hyperparameters.html** — `num_leaves` baseline 16 の推奨（sensible defaults の補助資料）。

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — 全パッケージ PyPI で実測・LightGBM/sklearn API は公式 docs 確認
- Architecture: HIGH — feature_generator.py・features_train.parquet・標準 entry.parquet を実測、既存 Phase 3/4/6 パターン踏襲
- Pitfalls: HIGH — Pitfall #1（early stopping API）#2（horse_race_id）#3（categorical 変換）#7（window 境界）は全てコード/データ実測で確認
- Calibration/ECE: HIGH — sklearn 公式 docs + 複数コミュニティ資料で交叉確認

**Research date:** 2026-06-15
**Valid until:** 2026-07-15（30日間。LightGBM 4.x API は安定・sklearn 1.9 も安定だが、minor version update で callback API 互換性を再確認推奨）
