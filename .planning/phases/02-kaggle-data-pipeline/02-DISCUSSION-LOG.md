# Phase 2: Kaggle Data Pipeline - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-11
**Phase:** 02-Kaggle Data Pipeline
**Areas discussed:** 障害戦・除外条件, odds.csv/payoffの扱い, データ品質検証の深度, Parquet出力構成

---

## 障害戦・除外条件

### Q1: 障害戦データをどう扱うか

| Option | Description | Selected |
|--------|-------------|----------|
| 変換して保存（推奨） | standard層には全データを変換保存。Phase 3/7で除外。obstacleカラムで後からフィルタ可能 | |
| 変換時に除外 | 2015-2021の変換時点で障害戦を除外。standard層は平地のみ。後で必要なら再変換 | ✓ |
| 平地・障害で別ファイル | 平地用と障害戦用で別ファイルに分けて保存。テーブルが2倍に増えパイプラインが複雑化 | |

**User's choice:** 変換時に除外
**Notes:** ユーザーが「地方のデータもある場合はそれも取り除いたほうがいい」と追加指摘。これにより除外条件の議論が拡大。

### Q2: 除外条件の確定（地方・外国馬の扱い）

| Option | Description | Selected |
|--------|-------------|----------|
| 平地＋JRA中央のみ（推奨） | 障害戦除外 + regionが「地方」「外国」の出走を除外 | ✓ |
| 平地＋JRA中央＋外国馬は含める | 障害戦除外 + region「地方」のみ除外。外国馬はJRAレースに出走しているので含める | |
| 障害のみ除外 | 障害戦のみ除外。regionフィルタはかけない | |

**User's choice:** 平地＋JRA中央のみ
**Notes:** Kaggleデータセットのレース自体は全てJRA中央競馬。regionは出走馬の所属区分（東/西/外国/地方）であり、エントリーレベルの除外はデータ整合性上の注意が必要（1レースの結果が欠損する可能性）。この点はplannerが詳細を詰める。

---

## odds.csv/payoffの扱い

### Q1: Phase 2でodds.csvをどう扱うか

| Option | Description | Selected |
|--------|-------------|----------|
| odds_trifectaのみ生成（推奨） | odds_trifectaテーブルのみ生成。payoffはPhase 5までスキップ | |
| odds_trifecta + payoff部分生成 | odds_trifectaを生成し、payoffも上位3組のみ部分生成。Phase 5で全通りに拡張 | ✓ |
| odds.csvはスキップ | odds.csvはPhase 2では一切変換しない。全通りデータをPhase 5で待つ | |

**User's choice:** odds_trifecta + payoff部分生成
**Notes:** payoffテーブルは「不完全」状態で存在することを許容。Phase 5で全通りデータに拡張される。

---

## データ品質検証の深度

### Q1: 変換後のデータ品質検証をどの程度の深さにするか

| Option | Description | Selected |
|--------|-------------|----------|
| 基本検証（推奨） | 行数確認 + スキーマ適合性 + audit関数実行。最低限の安心保証 | |
| 詳細検証 | 基本検証 + null率比較 + 値分布比較 + 参照整合性チェック | |
| 完全検証 | 詳細検証 + サンプル行照合 + 値域チェック。最も確実 | ✓ |

**User's choice:** 完全検証
**Notes:** 472MBのCSVを扱う初回パイプラインなので、変換ミスの早期発見は後のフェーズの信頼性に直結。

---

## Parquet出力構成

### Q1: standard層のParquetファイルをどう構成するか

| Option | Description | Selected |
|--------|-------------|----------|
| テーブル別ディレクトリ＋年別ファイル（推奨） | `data/standard/race/2015.parquet` 等。pd.read_parquet()で全年一括読み込み可能 | |
| テーブル別単一ファイル | `data/standard/race.parquet` 等。最もシンプル | ✓ |
| Hive-styleパーティション | `data/standard/race/year=2015/` 等。将来的な拡張性は高いが現時点では過剰 | |

**User's choice:** テーブル別単一ファイル
**Notes:** ROADMAPの「年別分割で出力」指定を変更。2015-2021の7年分は単一ファイルでも十分扱えるサイズ。race_dateカラムで年フィルタ可能。

---

## Claude's Discretion

- 日本語カラム名→英語カラム名の具体的なマッピングロジック
- race_result.csvの1行→3テーブル分割ロジック
- レース記号カラム（20列）のテキスト→bool変換
- 472MB CSVの効率的読み込み方法
- BOM付きCSVのエンコーディング処理
- 着順注記・着差の特殊フォーマット処理
- 検証結果の出力形式

## Deferred Ideas

None — discussion stayed within phase scope.
