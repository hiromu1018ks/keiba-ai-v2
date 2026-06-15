# Phase 7: Model A -- Top-3 Probability - Context

**Gathered:** 2026-06-15
**Status:** Ready for planning

<domain>
## Phase Boundary

feature 層（2015-2026/5、534,953行×78列）を読み込み、LightGBM 二値分類器（target_top3）を学習して各馬の **3着内確率 `p_top3`** を出力する **Model A** を構築・検証する。時系列CV（GroupTimeSeriesSplit）でリークを防ぎ、OOF予測で Isotonic キャリブレーションを実施、ホールドアウト（2025-01〜2026-05）で最終評価する。訓練済みモデル + キャリブレーター + OOF/ホールドアウト予測 + 評価レポート + config を成果物とし、Phase 8（Harville EV）/ Phase 9（walk-forward backtest）に引き渡す。

**In scope:**
- LightGBM 二値分類器の学習・推論コード（sensible defaults + early stopping）
- GroupTimeSeriesSplit（race_id グループ化、fold=5）の実装
- OOF 予測生成 + Isotonic キャリブレーション（OOF学習→ホールドアウト適用）
- ホールドアウト評価（AUC / Brier / logloss / ECE / reliability diagram）
- 人気ベースライン（単勝オッズ順位スコア）との比較
- 成果物保存（モデル / calibrator / OOF / holdout / report / config）
- 環境整備（`brew install libomp` + scikit-learn 導入＝Phase 7 plan の前提タスク）

**Out of scope:**
- Harville 三連複確率・EV 計算（Phase 8）
- walk-forward バックテスト・ROI 検証（Phase 9）
- feature 再生成（Phase 3 完了済み、本フェーズは feature を読むだけ）
- 三連複オッズ全通り取得（Phase 5 DEFERRED）
- Optuna HPO（Phase 9 / v2 ADVM-02 へ）
- 血統・ラップ・調教コメント特徴量（v2 EXTF-01〜05）

</domain>

<decisions>
## Implementation Decisions

### 時系列分割・CV 設計
- **D-01:** 学習区間 = **2018-2024（直近7年）**。ROADMAP 成功基準#1「2015-2023」からの前倒し。理由は concept drift（騎手・調教師の世代交代、レース体系改編、馬場・コース改良、コロナ期2020-2021）。競馬 ML の通説（5-7年窓）に沿う。データ量は十分（1年≈46,000行、7年≈32万行で LightGBM 学習に問題ない）。
- **D-02:** ホールドアウト = **2025-01〜2026-05（1.5年）**。学習に一切触らず最終評価専用の「封筒」。誠実な「未知データでの成績」の証拠。
- **D-03:** **GroupTimeSeriesSplit** 採用（race_id / race_date で区切り、同一レースは必ず同一foldへ）。Phase 8 Harville 整合性（p_top3 をレース内で処理）・race レベル評価・間接リーク防止の3点を構造的に担保。scikit-learn 標準 TimeSeriesSplit は行単位で境界割れが起きるため独自実装（Phase 8/9 再利用可能な資産にする）。
- **D-04:** **fold 数 = 5**。学習7年を5分割（各foldの検証≈1.4年）。各foldから early stopping 用 validation を別途切る設計（切り方の詳細は planner）。
- **D-05:** ROADMAP 成功基準#1「trained on 2015-2023」の文言更新（→ 2018-2024 学習）は **Phase 9 繰越**。D-01 前倒しの事実を本 CONTEXT に記録し、成功判定は D-01/D-02 で行う。Phase 6 D-07（2015-2024→2015-2026/5）と同じパターン。

### 評価指標・ベースライン
- **D-06:** 主指標 = **AUC**（ランキング精度）。Brier / logloss は補助指標。**ROI は Phase 9 領域**（Phase 7 単体ではオッズ・買い目戦略不足で計算不可＝Phase 8/9 の仕事）。
- **D-07:** **Phase 7 成功判定 = 「ホールドアウト AUC 目安0.75以上」＋「キャリブレーション成功（D-11）」**。人気ベースラインとの AUC 比較は参考情報として報告するが、「超え」は**必須成功条件にしない**。
- **D-08:** **ROADMAP 成功基準#3「人気ベースライン超え」と 03-CONTEXT D-15「feature オッズ除外」の矛盾を明記**。純粋馬特性モデルが市場の集合知（人気＝単勝オッズ順位）を AUC で超えるのは、競馬 ML の通説上**非常に困難（稀）**。人気ベースライン計算 = 単勝オッズ順位をスコアとした AUC（ランキング精度は順序のみ感度なので順位そのものでも可）。真の EV 優位性は Phase 9 ROI で検証する。
- **D-09:** race レベル指標（1レースの上位3頭を何頭再現したか＝Top-3 recall）も参考出力。詳細は planner。

### キャリブレーション
- **D-10:** **Isotonic 回帰**でキャリブレーション。**OOF 予測で学習 → ホールドアウトに適用**し、ホールドアウント ECE で検証（リークなし標準パターン）。OOF サンプル十分（数十万行）で過学習リスク低。EV 計算（Phase 8）精度に直接効くため安全側の選択。
- **D-11:** 成功基準 = **ホールドアウト ECE < 0.02**。reliability diagram を併出力（ビン別 予測 vs 実績の可視化）。
- **D-12:** IsotonicRegression（scikit-learn）をキャリブレーターとして**モデルと一緒に保存**。Phase 8/9 は `p_top3_calibrated` を利用。生の `p_top3_raw` も OOF/ホールドアウト予渓に併存（比較・分析用）。

### ハイパラ・成果物契約
- **D-13:** ハイパラ戦略 = **LightGBM sensible defaults + early stopping**（検証 logloss 改善停止で打切り）。CLAUDE.md「Add optuna later」準拠。HPO は Phase 9 / v2 ADVM-02（ROI 直接最適化）へ。
- **D-14:** ハイパラは **YAML config** で管理（CLAUDE.md pyyaml）、**固定 seed** で再現性担保。
- **D-15:** 成果物 = ①訓練済み LightGBM モデル(`.txt`) ②Isotonic キャリブレーター(`.joblib`) ③OOF 予測 parquet（`race_id`, `horse_race_id`, `p_top3_raw`, `p_top3_calibrated`, `target_top3`, `fold`）④ホールドアウト予測 parquet（同構造、`fold='holdout'`）⑤評価レポート（AUC / Brier / logloss / ECE / reliability diagram / 人気ベースライン比較）⑥config YAML（ハイパラ / seed / 分割境界 / fold 設定）。配置目安: `models/phase7/`（モデル類）・`data/model/oof/`（予渓）・`reports/phase7/`（評価）。詳細は planner、いずれも gitignore 対象。

### Claude's Discretion
- AUC 閾値の厳密値（目安0.75の最終確定はホールドアウト実測 AUC 次第で planner/verify が判断）
- early stopping 用 validation の切り方・patience・最大ラウンド数
- 人気ベースライン計算の詳細（順位→疑似確率の変換方式）
- sensible defaults の具体的パラメータ値（LightGBM 推奨範囲: `num_leaves` / `learning_rate` / `min_data_in_leaf` / `feature_fraction` / `bagging` / `max_depth`）
- 高カーディナリティ categorical（`jockey` / `trainer`）の `min_data_in_leaf` 等の対処（03-CONTEXT D-06 で native categorical + rolling 統計量は既決定）
- クラス不均衡対処（陽性21%は軽度なので `scale_pos_weight` はデフォルトで様子見可）
- 成果物配置の最終パス・ファイル命名規則
- reliability diagram 可視化ライブラリ（matplotlib 導入要否）

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Context
- `.planning/PROJECT.md` — プロジェクト概要、3層アーキテクチャ、純粋予測×EV 構図、Key Decisions（LightGBM 固定・Optuna 後で）
- `.planning/REQUIREMENTS.md` — MODA-01〜04（Phase 7 担当要件）、Traceability
- `.planning/ROADMAP.md` — Phase 7 定義・成功基準4項目・Phase 3/6 依存関係
- `.planning/STATE.md` — Phase 5 DEFERRED（単勝 Harville プロキシ方針）、Blockers/Concerns

### Prior Phase Context（直接依存・必読）
- `.planning/phases/03-feature-engineering/03-CONTEXT.md` — **必読**。feature 層の完全契約。D-01〜D-05（lag/rolling 設計・45列）、D-06〜D-08（jockey/trainer native categorical + rolling 統計量）、D-09〜D-10（初出走馬 NaN + debut flag）、**D-11〜D-14（target_top3 定義・取消/除外除外ルール・DNF=0 含む）**、**D-15（人気/単勝オッズ除外=post-race）**。Phase 7 が読む feature の全仕様
- `.planning/phases/06-data-integration/06-CONTEXT.md` — **必読**。統合 corpus（2015-2026/5、race=38009/entry=result=534953）、**D-07（データ範囲 LOCKED）**、Phase 5 DEFERRED の単勝 Harville プロキシ方針
- `.planning/phases/01-data-schema-leak-audit/01-CONTEXT.md` — pre/post-race 分類、audit 関数

### Specification
- `docs/specification.md` §10 — モデル方針。§10「Model A：3着内確率モデル」p_top3 定義、LightGBM 指定
- `docs/specification.md` §7.2 — 最初に使う特徴量リスト（feature 層の根拠）

### Feature Layer（Phase 7 の入力・MUST READ）
- `src/pipeline/feature_generator.py` — feature 層生成ロジック。`FEATURE_COLUMNS` allowlist、target_top3 生成、categorical 変換。Phase 7 はこれを import してカラム整合性を担保
- `data/feature/features_train.parquet` — 学習用（534,953行×78列、target_top3 含む、2015-01-04〜2026-05-31）。Phase 7 はここから 2018-2024（学習）と 2025-2026/5（ホールドアウト）を抽出
- `data/feature/features_pred.parquet` — 予測用（target_top3 なし）。Phase 7 の検証は features_train の時系列分割で完結；features_pred は Phase 8/10 の運用予測用

### Schema Definitions（target・除外ルールの参照元）
- `src/schemas/result.py` — ResultSchema: `finish_position`, `finish_note`（target_top3 生成元）、`result_status` / `is_dnf` 補助列
- `src/schemas/entry.py` — EntrySchema: `popularity`, `win_odds`（人気ベースラインのソース・feature には含まれない）
- `src/schemas/audit.py` — `audit_leakage()`: feature 読込後に呼び出し post-race 混入を再確認

### Dependencies（環境）
- `pyproject.toml` — `lightgbm>=4.6` 宣言済みだが **libomp 未導入で import 失敗**（`brew install libomp` 必要）、**scikit-learn 未導入**（TimeSeriesSplit / metrics / IsotonicRegression に必要）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/pipeline/feature_generator.py` — feature 層の構造・カラム順・categorical 定義。Phase 7 は `FEATURE_COLUMNS` を import して feature と整合する学習カラムを取得
- `src/schemas/audit.py` `audit_leakage()` — feature DataFrame 読込後に呼び出し、post-race（`popularity` / `win_odds` 等）混入を検出。Phase 1 D-11/D-12 パターン
- `src/pipeline/validators.py` — データ品質検証パターン（行数・スキーマ・参照整合性）
- `loguru` — プロジェクト全体ロギング
- `pytest` / `tests/pipeline/` — 既存テストパターン（hermetic + gated の2層テスト構成が定番）

### Established Patterns
- Pydantic BaseModel は型定義用、DataFrame レベルで一括処理（Phase 1 D-02）— 53万行の一括処理
- standard / feature 層はテーブル別単一ファイル Parquet（Phase 2 D-06 / Phase 3）
- config は YAML（pyyaml）、再現性は固定 seed
- loguru ログ、pytest テスト
- **新規 `src/ml/`（または `src/model/`）ディレクトリ** — 現在 ml/model ディレクトリなし。Phase 7 で作成。`src/pipeline/` に feature Generator があるので、学習・推論・CV・評価モジュールを新設

### Integration Points
- **入力**: `data/feature/features_train.parquet`（2018-2024 抽出→学習、2025-2026/5 抽出→ホールドアウト）
- **出力**: `models/phase7/`（モデル+キャリブレーター）、`data/model/oof/`（OOF/ホールドアウト予測 parquet）、`reports/phase7/`（評価レポート・reliability diagram）
- **下流**: Phase 8 が `p_top3_calibrated` + `entry.win_odds` で Harville 三連複 EV 計算。Phase 9 が walk-forward で本格検証（モデル・推論コード・キャリブレーター・GroupTimeSeriesSplit を再利用）
- **⚠ 環境前提タスク**: `brew install libomp`（lightgbm import 解消）+ `pip install 'lightgbm[scikit-learn]'`（scikit-95 導入）。researcher / planner が Phase 7 plan の前提タスク（Wave 1 等）として扱う

</code_context>

<specifics>
## Specific Ideas

- **「純粋予測×EV」構図の堅持**（PROJECT.md / 03-CONTEXT D-15）: feature から人気・単勝オッズを除外し、純粋に馬・レース特性だけで `p_top3` を推定。オッズとの比較は Phase 8 EV 計算で初めて行う。これが本システムの理論的骨格であり、「人気ベースライン超え」が困難という D-08 の矛盾もこの構図に由来する（オッズを入れたら人気に勝てないのは自明なので、あえて外して EV でズレを測る）。
- **「まず確実に進める」哲学**（CLAUDE.md）: LightGBM 固定・defaults + early stopping・Optuna は後で。Phase 7 は手法確立フェーズとして、過学習を抑えた安定モデルを作ることが優先。
- **Phase 6 D-07 との一貫性**: データ範囲・学習窓の ROADMAP 文言更新は次フェーズ繰越の確立パターン。Phase 7 も学習窓「2015-2023 → 2018-2024」を同パターン（D-05）で処理する。
- **ホールドアウト1.5年（2025-2026/5）の意義**: 直近の実データで「未来で通用するか」を検証。Phase 9 walk-forward とは役割分担（Phase 7 = 手法確立、Phase 9 = 運用検証）。

</specifics>

<deferred>
## Deferred Ideas

- **Optuna HPO / グリッドサーチ** — Phase 9 walk-forward 本検証 または v2 ADVM-02（ROI 直接最適化）で対応。Phase 7 は defaults + early stopping（D-13）。
- **「純粋モデル vs 人気追加モデル」の3者比較** — Area 2 選択肢Cとして検討したが見送り（複合判定 D-07 で十分）。将来 feature にオッズを追加する v2 拡張の比較ベースとして再利用可。
- **ROADMAP 成功基準#1 文言更新（2015-2023 → 2018-2024）** — Phase 9 バックテスト計画時に ROADMAP 記載を調整（D-05 / Phase 6 D-07 と同パターン）。
- **`scale_pos_weight` / クラス重み付け** — 軽度不均衡（陽性21%）なので Phase 7 はデフォルト。AUC / logloss 次第で Phase 9 で再考。
- **特徴量重要度の深度分析（SHAP 等）** — Phase 7 は LightGBM 標準 feature importance まで。詳細分析は v2。
- **sliding / rolling window CV** — Phase 7 は expanding（GroupTimeSeriesSplit）で手法確立。窓の最適化は Phase 9 walk-forward の仕事。

</deferred>

---

*Phase: 07-Model A -- Top-3 Probability*
*Context gathered: 2026-06-15*
