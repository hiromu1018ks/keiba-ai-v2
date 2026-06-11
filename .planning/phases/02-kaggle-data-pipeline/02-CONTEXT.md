# Phase 2: Kaggle Data Pipeline - Context

**Gathered:** 2026-06-11
**Status:** Ready for planning

<domain>
## Phase Boundary

KaggleのCSVデータ（1986-2021）を、Phase 1で定義したstandard層スキーマに準拠したParquetファイルに変換するraw→standardパイプラインを構築する。JRA中央競馬の平地レース（2015-2021）のみを対象とし、5テーブル（race, entry, result, odds_trifecta, payoff）のParquetファイルを生成・検証する。

**In scope:**
- race_result.csv → race, entry, result の3テーブルへの分割・変換
- odds.csv → odds_trifecta, payoff の2テーブルへの変換（payoffは上位3組のみ部分生成）
- 2015-2021期間フィルタ、障害戦除外、JRA中央平地レースのみ抽出
- 完全データ品質検証（行数・スキーマ・audit・null率・分布・参照整合性・サンプル照合・値域チェック）
- standard層Parquetファイルの出力（テーブル別単一ファイル）

**Out of scope:**
- feature層の特徴量生成（Phase 3）
- 2022年以降のスクレイピングデータ（Phase 4）
- Kaggle/自前データの統合（Phase 6）
- 全通りの三連複オッズ取得（Phase 5）
- ラップタイム・通過順位のstandard化（raw保存のみ、後続フェーズ）

</domain>

<decisions>
## Implementation Decisions

### 対象データ絞り込み
- **D-01:** 障害戦は変換時に除外。RaceSchemaの`obstacle`カラムが"障害"のレースを除外し、平地レースのみをstandard層に保存
- **D-02:** JRA中央競馬の平地レースのみを対象。KaggleデータセットのレースはすべてJRA中央競馬だが、`region`カラム（東/西/外国/地方）は出走馬の所属区分であり、エントリーレベルでの除外は行わない（データ整合性を保つため）

### odds.csv/payoffテーブルの扱い
- **D-03:** odds.csvからodds_trifectaテーブルとpayoffテーブルの両方を生成。payoffは上位3組の組み合わせのみ部分データ（カバレッジ: 54.1% / 0.1% / 0.002%）。Phase 5（スクレイピング）で全通りデータに拡張される
- **D-04:** payoffテーブルは「不完全」状態で存在することを許容。odds_trifectaはOddsTrifectaSchemaに完全マッピング

### データ品質検証
- **D-05:** 完全検証を実装。以下すべてを実行：
  1. CSV行数 vs Parquet行数の一致確認
  2. Pydanticスキーマ適合性検証
  3. Phase 1 audit関数実行（post-raceカラム混入チェック）
  4. null率のCSV/Parquet間比較
  5. 代表カラムの値分布比較（min/max/mean）
  6. race_idをキーにしたテーブル間参照整合性チェック
  7. サンプル行の元CSVとの照合
  8. 競馬場コード・距離などの値域チェック

### Parquet出力構成
- **D-06:** テーブル別単一ファイル構成。各テーブル1つのParquetファイルに2015-2021全データを格納
  - `data/standard/race.parquet`
  - `data/standard/entry.parquet`
  - `data/standard/result.parquet`
  - `data/standard/odds_trifecta.parquet`
  - `data/standard/payoff.parquet`
- **D-07:** ROADMAPの「年別分割」指定を変更。単一ファイル内で`race_date`カラムによる年フィルタが可能。pandasで`pd.read_parquet()`一発で読み込み可能

### Claude's Discretion
- 日本語カラム名→英語カラム名の具体的なマッピングロジック（Phase 1スキーマとCSVヘッダーの対応）
- race_result.csvの1行をrace/entry/resultの3テーブルに分割する具体的なロジック
- レース記号（レース記号/*）の20カラムのスパーステキスト→Optional[bool]変換ロジック
- 472MB CSVの効率的な読み込み方法（chunked reading等）
- BOM付きCSV（﻿レース馬番ID）のエンコーディング処理
- 着順注記（中/取/失/除/再）の具体的な処理方法（finish_position=None, finish_note="中"等）
- 着差（"1.1/4", "大", "ハナ"等の非数値文字列）の処理
- 検証結果の出力形式（ログ、コンソール、レポートファイル等）

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Context
- `.planning/PROJECT.md` — プロジェクト概要、制約、3層アーキテクチャ方針、データ方針
- `.planning/REQUIREMENTS.md` — 要件定義（DATA-02が該当）
- `.planning/ROADMAP.md` — Phase 2定義、成功基準、Phase 1完了状態
- `CLAUDE.md` — 技術スタック詳細（pandas 2.3.x, Pydantic 2.13.x, loguru等）

### Prior Phase Context
- `.planning/phases/01-data-schema-leak-audit/01-CONTEXT.md` — Phase 1の全決定事項。特にD-01〜D-12が下流に直接影響。Pydantic型定義方針、pre/post-race分類、5テーブル分離、audit関数の仕様

### Specification
- `docs/specification.md` — マスター仕様書。3層データ方針、standard層で最初に作るテーブル定義、データ優先度マトリクス

### Schema Definitions (MUST READ for column mapping)
- `src/schemas/race.py` — RaceSchema: レース単位データ、全pre-raceカラム、20個のrace_flagブール値
- `src/schemas/entry.py` — EntrySchema: 出走馬情報、人気/単勝オッズはpost-race扱い
- `src/schemas/result.py` — ResultSchema: 全post-raceカラム、着順注記・着差の特殊フォーマット
- `src/schemas/odds_trifecta.py` — OddsTrifectaSchema: 三連複上位3組、オッズは0.1単位
- `src/schemas/payoff.py` — PayoffSchema: 1行=1組み合わせ設計、オッズはfloat（0.1単位ではない）
- `src/schemas/audit.py` — audit_leakage()関数: standard/feature生成時にpost-raceカラム混入を検出
- `src/schemas/export.py` — export_schema_documentation(): スキーマのJSON出力

### Source Data
- `data/raw/kaggle/19860105-20210731_race_result.csv` — メインデータ（66カラム、472MB、日本語ヘッダー、BOM付き）
- `data/raw/kaggle/19860105-20210731_odds.csv` — オッズデータ（104カラム、22MB、三連複は上位3組のみ）
- `data/raw/kaggle/19860105-20210731_laptime.csv` — ラップタイム（Phase 2ではraw保存のみ）
- `data/raw/kaggle/20020615-20210731_corner_passing_order.csv` — 通過順位（Phase 2ではraw保存のみ）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/schemas/*.py` — Phase 1で実装済みの5テーブルPydanticスキーマ。カラム名、型、pre/post-race分類が全て定義済み。列マッピングの基準として使用
- `src/schemas/audit.py` — audit_leakage()が実装済み。standard生成時に呼び出してpost-raceカラム混入を検出可能
- `src/schemas/export.py` — export_schema_documentation()でスキーマのJSON出力が可能

### Established Patterns
- Pydantic BaseModel は型定義用、DataFrameレベルで一括検証（D-02）。472MB CSVに対して1行ずつのPydantic変換はしない
- `json_schema_extra={"pre_race": True/False, "table": "xxx"}` でカラムのメタデータ駆動分類
- loguruでログ出力（プロジェクト全体で統一）
- pytestでテスト、tests/schemas/に既存テストパターンあり

### Integration Points
- Phase 3（Feature Engineering）が今回生成したstandard Parquetを読み込んで特徴量を生成
- Phase 4（Scraping）が同じstandardスキーマに従ってスクレイピングデータを格納
- Phase 6（Data Integration）がKaggle/自前のstandard Parquetを統合
- Phase 1のaudit関数をstandard生成時（Phase 2）とfeature生成時（Phase 3）の両方で実行（D-11）

### Source Data Structure Notes
- `race_result.csv`: BOM付きUTF-8。ヘッダー行に66カラム（日本語名）。1行=1出走馬。`レース馬番ID`がユニークキー、`レースID`がレース単位キー。`レース日付`で2015-2021フィルタ
- `race_result.csv`の`レース記号/*`カラム（20列）: 値がカラム名自体（例: "レース記号/(ハンデ)" → 値"(ハンデ)"）または空文字。→ Optional[bool]に変換が必要
- `race_result.csv`の着順: 1-18の整数と、特殊値（中=withdrawal, 取=scratched, 失=disqualified, 除=removed, 再=re-run）
- `race_result.csv`の着差: 非数値文字列（"1.1/4", "大", "ハナ", "クビ"等）。ResultSchemaではOptional[str]として保持
- `odds.csv`: 1行=1レース。三連複カラムは15本（3組み合わせ×5カラム）。オッズは0.1単位（990 = 99.0倍）

</code_context>

<specifics>
## Specific Ideas

- **「データは広く保存、モデル利用は狭く始める」**: specification.mdの基本方針。Phase 2では保存段階なので取得可能なデータはすべてstandard層に変換する。ただしD-01で障害戦は除外
- **race_result.csvの3テーブル分割**: 1行のCSV行を「race共通部（重複排除）」「entry事前情報」「result事後情報」に分解。raceは`race_id`でdistinct、entryとresultは`horse_race_id`で1対1結合
- **単一ファイル選択の理由**: pandasで1回の`read_parquet()`で全データを読み込める。2015-2021の7年分（数十万行）は単一ファイルでも十分に扱えるサイズ。年別分割の複雑さを避ける

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.
</deferred>

---

*Phase: 02-Kaggle Data Pipeline*
*Context gathered: 2026-06-11*
