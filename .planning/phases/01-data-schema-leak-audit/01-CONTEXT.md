# Phase 1: Data Schema & Leak Audit - Context

**Gathered:** 2026-06-11
**Status:** Ready for planning

<domain>
## Phase Boundary

standard層のスキーマ契約（5テーブルの定義）と、データリーク防止のための監査機構を定義・実装する。全下流フェーズ（Phase 2〜10）が依存するデータ基盤の土台。

**In scope:**
- standard層の5テーブル（race, entry, result, odds_trifecta, payoff）のPydanticモデル定義
- Kaggle全カラムのpre-race/post-race分類
- メタデータ駆動のリーク監査関数
- 監査関数のstandard生成時・feature生成時での実行

**Out of scope:**
- Kaggle CSVからstandard Parquetへの実際の変換（Phase 2）
- feature層の特徴量生成（Phase 3）
- スクレイピングデータのstandard化（Phase 4）

</domain>

<decisions>
## Implementation Decisions

### Schema Definition Form
- **D-01:** Pydantic `BaseModel` で各テーブルのスキーマを定義。テーブルごとにファイル分割（`schemas/race.py`, `schemas/entry.py`, `schemas/result.py`, `schemas/odds_trifecta.py`, `schemas/payoff.py`）
- **D-02:** Pydanticは型定義用。実際のデータ検証はDataFrameレベルで実行（1行ずつのPydantic変換は避ける — 472MB CSVに対しては遅すぎる）

### Pre-race / Post-race Classification
- **D-03:** 人気・単勝オッズ → **post-race**（feature層では使用不可。EV計算のみで使用）
- **D-04:** 三連複オッズ → **post-race**（EV計算のみで使用）
- **D-05:** 馬体重・場体重増減 → **pre-race**（feature層で使用可能）
- **D-06:** ⚠️ REQUIREMENTS `DATA-03` から人気・単勝オッズを削除する必要あり。これにより、モデルは純粋に馬・レース特性のみで3着内確率を予測し、オッズとの比較でEVを計算する構図になる

**分類の全体像:**

| カラム群 | 分類 | 備考 |
|----------|------|------|
| 枠番、馬番、斤量、性別、馬齢 | pre-race | 出走確定時に判明 |
| 騎手、調教師 | pre-race | 出走確定時に判明（文字列カラム） |
| 競馬場、距離、芝ダート、右左回り | pre-race | レース条件 |
| 天候、馬場状態、頭数 | pre-race | 発走時に確定 |
| 馬体重、場体重増減 | pre-race | 当日計量・発走前公表 |
| レース名、重賞回次、発走時刻 | pre-race | レース情報 |
| 人気、単勝オッズ | post-race | 発走時確定だがfeature不可扱い |
| 三連複オッズ（全券種オッズ） | post-race | EV計算のみ |
| 着順、着差、タイム | post-race | レース結果 |
| 上り（3F） | post-race | レース結果 |
| 通過順位（1-4コーナー） | post-race | レース結果 |
| 賞金 | post-race | レース結果 |

**注意:** Phase 3（Feature Engineering）では「過去レースの上り3F・通過順位」をlag featureとして使用する。これらは過去データからの参照なのでpre-race扱い。現在レースの上り3F・通過順位はpost-race。

### Table Separation
- **D-07:** 5テーブル完全分離: `race`, `entry`, `result`, `odds_trifecta`, `payoff`
- **D-08:** 騎手・調教師はentryテーブルの文字列カラム（マスターテーブルは作らない）。Phase 3のrolling stats計算では`groupby`で集計
- **D-09:** entry ↔ result の結合キー: `horse_race_id` = `{race_id}_{馬番}`。1対1関係

**Kaggle CSV → 5テーブルのマッピング方針:**
- `race_result.csv` → race（レース単位に重複排除） + entry（事前情報カラム） + result（事後情報カラム）
- `odds.csv` → odds_trifecta（三連複上位3組） + payoff（払戻情報）
- `laptime.csv`, `corner_passing_order.csv` → Phase 1では未対応（raw保存のみ）

### Audit Mechanism
- **D-10:** Pydantic `Field(metadata={"pre_race": True/False})` でカラムごとにメタデータ駆動の分類を定義。audit関数はメタデータを参照してpost-raceカラムを検出
- **D-11:** 監査タイミング: standard生成時（Phase 2）とfeature生成時（Phase 3）の両方で監査を実行
- **D-12:** post-raceカラム検出時の動作: **警告ログのみ、処理は継続**。例外で停止はしない

### Claude's Discretion
- 各テーブルの具体的なカラム名マッピング（Kaggleの日本語カラム → standard層の英名）
- Pydanticモデルの具体的なバリデーションルール（nullable、range check等）
- audit関数の具体的なAPI設計（関数名、引数、戻り値）
- プロジェクト構成（`src/` vs flat等）

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Context
- `.planning/PROJECT.md` — プロジェクト概要、制約、3層アーキテクチャ方針、データ方針
- `.planning/REQUIREMENTS.md` — 要件定義（DATA-01, DATA-04 が該当）。⚠️ DATA-03から人気・単勝オッズを削除する必要あり（D-06）
- `.planning/ROADMAP.md` — Phase定義、依存関係、success criteria
- `CLAUDE.md` — 技術スタック詳細、Pydantic 2.13.x推奨、LightGBM/pandas設定

### Specification
- `docs/specification.md` — マスター仕様書。3層データ方針、standard層の最初に作るテーブル、feature層の最初に使う特徴量を定義

### Source Data
- `data/raw/kaggle/19860105-20210731_race_result.csv` — メインデータ（65カラム、race/entry/result混在）
- `data/raw/kaggle/19860105-20210731_odds.csv` — オッズデータ（三連複は上位3組のみ）
- `data/raw/kaggle/19860105-20210731_laptime.csv` — ラップタイム（Phase 1ではraw保存のみ）
- `data/raw/kaggle/20020615-20210731_corner_passing_order.csv` — 通過順位（Phase 1ではraw保存のみ）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- なし — greenfieldプロジェクト。Pythonコード・pyproject.toml未作成

### Established Patterns
- 3層アーキテクチャ: raw → standard → feature（PROJECT.md / specification.mdで定義済み）
- Pydantic BaseModel によるデータ検証（CLAUDE.md推奨）
- pandas CategoricalDtype でLightGBMのnative categorical対応（Phase 3以降）

### Integration Points
- Phase 2（Kaggle Pipeline）が今回のスキーマ定義を使ってCSV→Parquet変換を行う
- Phase 3（Feature Engineering）がaudit関数を使ってfeature生成時のリークを検出する
- Phase 4（Scraping）が同じstandardスキーマに従ってスクレイピングデータを格納する
- Phase 6（Data Integration）がKaggle/自前のstandard Parquetを統合する

### Source Data Structure Notes
- `race_result.csv`: ヘッダー行に約65カラム（日本語名）。1レースの出走馬が別々の行。`レース馬番ID`がユニークキー、`レースID`がレース単位キー
- `odds.csv`: ヘッダー行に各券種のオッズ・人気・組み合わせ。三連複は上位3組のみ（`三連複1_組合せ1-3`、`三連複1_オッズ`等）
- `odds.csv`の三連複は「人気上位3組」のオッズのみ。全通りのオッズはPhase 5でスクレイピング取得

</code_context>

<specifics>
## Specific Ideas

- **純粋予測×EV構図:** モデルは人気・オッズを使わず純粋に馬・レース特性のみで予測 → 予測確率とオッズの比較でEVを計算。この設計により「市場評価とAI評価のズレ」を直接的に捉える
- **過去データのlag feature:** Phase 3で「過去レースの上り3F・通過順位」を`.shift(1)`でlag feature化する際、これらはpast dataからの参照なのでpre-race扱い。現在レースの値はpost-race。この区別をaudit関数で表現できる必要がある
- **Kaggle→standard変換のロジック:** `race_result.csv`の1行をrace情報（重複排除）・entry情報（pre-raceカラム）・result情報（post-raceカラム）に分解するマッピングロジックがPhase 2で必要

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.
</deferred>

---

*Phase: 01-Data Schema & Leak Audit*
*Context gathered: 2026-06-11*
