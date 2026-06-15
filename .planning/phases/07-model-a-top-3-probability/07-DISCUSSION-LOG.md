# Phase 7: Model A -- Top-3 Probability - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-15
**Phase:** 7-Model A -- Top-3 Probability
**Areas discussed:** 時系列分割・CV設計, 評価指標・ベースライン, キャリブレーション手法, ハイパラ・成果物契約

---

## 時系列分割・CV 設計

### Q1. TimeSeriesSplit 全体戦略（学習区間 vs OOF vs ホールドアウト）

| Option | Description | Selected |
|--------|-------------|----------|
| ROADMAP準拠+直近HOLDOUT | 2015-2023 を TimeSeriesSplit OOF、2024-2026/5 を最終ホールドアウト | |
| 全期間CV+最終1年HOLDOUT | 2015-2025/5 を CV、直近1年のみホールドアウト | |
| CVのみ（HOLDOUTなし） | 全期間 CV のみ、最終モデルは全データで再学習 | |

**User's choice:** （まず）「よくわからない。何がどう違うのか」→ 平易な図解で再説明後に検討継続

**Notes:** 用語（学習 / OOF / ホールドアウト）と「データが2026/5まで延びたが ROADMAP は2015-2023」というズレの核心を図解タイムラインで説明。その上で学習窓の長さについて追加質問へ。

### Q1'. 学習窓の長さ（11年半は長すぎないか）

| Option | Description | Selected |
|--------|-------------|----------|
| 中窓 2018-2024（推奨） | 直近7年学習、2025-2026/5 ホールドアウト(1.5年)。drift 低減・ROADMAP から前倒し | ✓ |
| 長窓 2015-2023 | 9年学習、ROADMAP criterion#1 に忠実。2015-2017 ノイズ混入 | |
| 短窓 2020-2024 | 直近5年・drift クリーンだがコロナ期含む。約23万行 | |

**User's choice:** 中窓 2018-2024

**Notes:** ユーザー「Aでいいとは思うんだけど11年半分って長すぎない？一般的にどう？」→ 競馬 ML では 5-7年窓が定石（concept drift：騎手世代交代・レース体系改編・馬場改良・コロナ期）。ただし「最適窓の発見は Phase 9 walk-forward の仕事」と役割分担を説明した上で、競馬常識範囲・drift 低減・ホールドアウト1.5年安定の中窓を推奨し採用。ROADMAP「2015-2023」からの前倒しは CONTEXT 記録・文言更新は Phase 9 繰越（D-05、Phase 6 D-07 と同パターン）。

### Q2. CV grouping

| Option | Description | Selected |
|--------|-------------|----------|
| レース単位（推奨） | GroupTimeSeriesSplit: race_id で区切り同一レースは同一fold。Phase8 Harville 整合性・race レベル評価・間接リーク防止。fold=5 | ✓ |
| 行単位（標準） | scikit-learn 標準 TimeSeriesSplit。実装最小だが境界で同一レース分割の恐れ | |

**User's choice:** レース単位（推奨）

---

## 評価指標・ベースライン

### Q. MODA-03「人気ベースライン超え」の扱い

| Option | Description | Selected |
|--------|-------------|----------|
| 複合判定（推奨） | 成功=妥当AUC(0.75+)＋キャリブレーション成功。人気ベースライン比較は参考情報・超えは必須でない。真の優位性は Phase9 ROI | ✓ |
| 厳密超え要求 | モデル AUC > 人気ベースライン AUC を成功必須。D-15 と整合せず成功リスク大 | |
| 3者比較モデル | 純粋モデル＋人気追加モデルを副次訓練し3者比較。スコープ・工数増 | |

**User's choice:** 複合判定（推奨）

**Notes:** ROADMAP 成功基準#3「人気ベースライン超え」と 03-CONTEXT D-15「feature オッズ除外」の矛盾を提示。純粋馬特性モデルが市場の集合知（人気）を AUC で超えるのは競馬 ML 通説上非常に困難。「超え」は必須成功条件にせず、真の EV 優位性は Phase 9 ROI で検証する方針（D-07/D-08）。主指標は AUC、Brier/logloss は補助、ROI は Phase 9 領域（D-06）。

---

## キャリブレーション手法

### Q. キャリブレーション手法と許容誤差

| Option | Description | Selected |
|--------|-------------|----------|
| Isotonic + ECE<0.02（推奨） | Isotonic 回帰（OOF 学習→ホールドアウト適用）。ECE<0.02 基準・reliability diagram 出力。EV 精度に直結し安全側 | ✓ |
| Beta + ECE<0.02 | Beta キャリブレーション（2パラメータ）。堅牢だが表現力劣る | |
| 生確率（省略） | LightGBM 生確率・ECE 報告のみ。極端域ズレ未補正で EV 計算へ | |

**User's choice:** Isotonic + ECE<0.02（推奨）

**Notes:** LightGBM の logloss 学習で概ね校準されるが極端域でズレる。Phase 8 Harville の EV 計算精度に直接効くため、OOF サンプル十分（数十万行）で過学習リスク低の Isotonic を採用（D-10〜D-12）。

---

## ハイパラ・成果物契約

### Q. ハイパラ戦略

| Option | Description | Selected |
|--------|-------------|----------|
| defaults+early stopping（推奨） | LightGBM sensible defaults + early stopping。YAML config・固定 seed。CLAUDE.md「Optuna 後で」準拠 | ✓ |
| Optuna HPO | CV ベース最適化（数十分〜数時間）。AUC 2-3pt 向上の可能性だが工数増 | |
| defaults+軽グリッド | 数点のグリッドサーチ。Optuna 未満・工数小 | |

**User's choice:** defaults+early stopping（推奨）

**Notes:** 成果物契約は標準セット（モデル .txt / Isotonic .joblib / OOF・ホールドアウト予測 parquet / 評価レポート / config YAML）で合意（D-13〜D-15）。配置は models/phase7/・data/model/oof/・reports/phase7/（詳細 planner）。

---

## Claude's Discretion

- AUC 閾値の厳密値（0.75 目安の最終確定はホールドアウト実測次第）
- early stopping 用 validation の切り方・patience・最大ラウンド
- 人気ベースライン計算の詳細（順位→疑似確率変換方式）
- sensible defaults の具体的パラメータ値
- 高カーディナリティ categorical（jockey/trainer）の min_data_in_leaf 調整
- クラス不均衡対処（陽性21%は軽度・scale_pos_weight はデフォルトで様子見）
- 成果物配置の最終パス・命名規則
- reliability diagram 可視化ライブラリ（matplotlib 導入要否）

## Deferred Ideas

- Optuna HPO / グリッドサーチ → Phase 9 / v2 ADVM-02
- 「純粋モデル vs 人気追加モデル」3者比較 → v2 拡張時の比較ベース
- ROADMAP 成功基準#1 文言更新（2015-2023 → 2018-2024）→ Phase 9
- scale_pos_weight / クラス重み付け → Phase 9 で再考
- 特徴量重要度の深度分析（SHAP 等）→ v2
- sliding / rolling window CV → Phase 9 walk-forward

## 申し送り（researcher/planner 向け）

- **環境前提タスク**: `brew install libomp`（lightgbm import 解消）+ scikit-learn 導入（TimeSeriesSplit / metrics / IsotonicRegression）。Phase 7 plan の Wave 1 等で前提タスク化。
