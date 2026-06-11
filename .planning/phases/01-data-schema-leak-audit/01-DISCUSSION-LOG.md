# Phase 1: Data Schema & Leak Audit - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-11
**Phase:** 01-Data Schema & Leak Audit
**Areas discussed:** スキーマ定義の形式, オッズの事前/事後分類, Kaggle1行のテーブル分離方針, 監査機構の設計粒度

---

## スキーマ定義の形式

### Q1: standard層のテーブルスキーマをどう定義するか

| Option | Description | Selected |
|--------|-------------|----------|
| Pydanticモデル主体 | BaseModelで各テーブル定義。型・nullable・validationが集約 | ✓ |
| YAML定義 + Pydantic検証 | YAMLで宣言的定義、Pydanticは別レイヤー | |
| dict/dataclass軽量定義 | 最軽量だが型安全性は自前実装 | |

**User's choice:** Pydanticモデル主体
**Notes:** CLAUDE.mdでPydantic 2.13.x推奨と整合

### Q2: Pydanticモデルの役割（大量データでの性能）

| Option | Description | Selected |
|--------|-------------|----------|
| Pydanticで型定義 + DataFrame検証 | DataFrameのdtypesと照合。大量データでも高速 | ✓ |
| 1行ずつPydantic検証 | 最高の型安全性だが472MB CSVには遅い | |
| Pydanticは文書用、実検証はpandasのみ | 実行速度優先 | |

**User's choice:** Pydanticで型定義 + DataFrame検証

### Q3: ファイル構成

| Option | Description | Selected |
|--------|-------------|----------|
| テーブルごとにファイル分割 | schemas/race.py, schemas/entry.py 等 | ✓ |
| 1ファイルに全定義 | 管理可能だがPhase 3-4で肥大化の懸念 | |

**User's choice:** テーブルごとにファイル分割

---

## オッズの事前/事後分類

### Q1: Kaggleの人気・単勝オッズの分類

| Option | Description | Selected |
|--------|-------------|----------|
| pre-race扱い（確定オッズ前提） | バックテストは確定オッズ前提 | |
| 「at-post」カテゴリを新設 | 厳密な分類だが複雑度増 | |
| post-race扱い（featureで使用不可） | モデルは純粋に馬・レース特性のみ | ✓ |

**User's choice:** post-race扱い（featureで使用不可）

### Q2: 要件との矛盾への対応

| Option | Description | Selected |
|--------|-------------|----------|
| post-race確定（要件更新する） | DATA-03から人気・単勝オッズを削除 | ✓ |
| pre-raceに戻す（要件との整合優先） | 既存要件を維持 | |
| 2軸分類（タイミング + 利用可否） | 柔軟だが複雑 | |

**User's choice:** post-race確定（要件更新する）
**Notes:** これによりREQUIREMENTS DATA-03の更新が必要。モデルは「純粋予測 × オッズ = EV」の構図になる

### Q3: 馬体重・場体重増減の分類

| Option | Description | Selected |
|--------|-------------|----------|
| pre-race扱い | 当日計量・発走前公表 | ✓ |
| post-race扱い | 直前情報として使用不可 | |

**User's choice:** pre-race扱い

### Q4: 三連複オッズの分類

| Option | Description | Selected |
|--------|-------------|----------|
| post-race（EV計算のみ） | featureでは使わない。オッズを特徴量に使うとEV矛盾の懸念 | ✓ |
| pre-race（feature利用可能） | 利用可能だが「割安」発見と矛盾する可能性 | |

**User's choice:** post-race（EV計算のみ）

---

## Kaggle1行のテーブル分離方針

### Q1: テーブル構成

| Option | Description | Selected |
|--------|-------------|----------|
| 5テーブル完全分離 | race/entry/result/odds_trifecta/payoff。リーク監査しやすい | ✓ |
| 4テーブル（entry+結果結合） | entry_result結合。変換シンプル | |
| 2テーブル（最小構成） | race/horse_race。Phase 4で再考の可能性 | |

**User's choice:** 5テーブル完全分離

### Q2: 騎手・調教師のデータの扱い

| Option | Description | Selected |
|--------|-------------|----------|
| entryテーブルの文字列カラム | IDなし、名前のみ。groupbyでrolling stats計算 | ✓ |
| マスターテーブル（jockey/trainer） | 正規化は完全だが名前ベースマッチングが必要 | |

**User's choice:** entryテーブルの文字列カラム

### Q3: entry/resultの結合キー

| Option | Description | Selected |
|--------|-------------|----------|
| horse_race_id共通（1:1結合） | {レースID}_{馬番}。共通キーで結合 | ✓ |
| 各テーブル独立PK（同値） | 独立PKだが同じ値 | |

**User's choice:** horse_race_id共通（1:1結合）

---

## 監査機構の設計粒度

### Q1: リーク監査の実装方式

| Option | Description | Selected |
|--------|-------------|----------|
| Pydanticメタデータ駆動 | Field(metadata={"pre_race": True/False})。拡張性高 | ✓ |
| allowlist方式（YAML/JSON） | pre-race許可リスト。シンプル | |
| denylist方式 | post-race禁止リスト。漏れリスク | |

**User's choice:** Pydanticメタデータ駆動

### Q2: 監査タイミング

| Option | Description | Selected |
|--------|-------------|----------|
| feature生成時のみ | Phase 3のみ。standardでは分類記録のみ | |
| standard生成時も監査 | Phase 2のentry/result分離も検証 | ✓ |

**User's choice:** standard生成時も監査

### Q3: 検出時の動作

| Option | Description | Selected |
|--------|-------------|----------|
| 例外で即停止 | テストで即キャッチ。長時間実行で中断リスク | |
| 警告ログ＋問題カラム除外 | バックテスト完走優先 | |
| 警告ログのみ（継続） | 処理継続 | ✓ |

**User's choice:** 警告ログのみ（継続）

---

## Claude's Discretion

- 各テーブルの具体的カラム名マッピング（日本語→英名）
- Pydanticモデルのバリデーションルール詳細（nullable、range check等）
- audit関数のAPI設計（関数名、引数、戻り値）
- プロジェクトディレクトリ構成

## Deferred Ideas

なし — 全議論がフェーズスコープ内
