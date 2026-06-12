# Phase 3: Feature Engineering - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-12
**Phase:** 03-Feature Engineering
**Areas discussed:** 近走成績の定義, 騎手・調教師の特徴量化, 初出走馬の扱い, Target変数と評価設計

---

## 近走成績の定義

### Q1: 何レース分遡ってlag featureを作るか

| Option | Description | Selected |
|--------|-------------|----------|
| 3レース分 | 直近3レース分。データ欠損リスク低、コンパクト | |
| 5レース分 | 直近5レース分。より長い傾向を捉える | |
| 3 + 5レースの両方 | 両方生成。モデルが重要な方を使う。特微量数は増える | ✓ |

**User's choice:** 3 + 5レースの両方
**Notes:** モデルに選ばせる方針

### Q2: lag featureとしてどの指標を含めるか

| Option | Description | Selected |
|--------|-------------|----------|
| 基本3指標 | finish_position, last_3f, corner_4 | |
| 5指標（拡張） | 基本3 + finish_time + margin。ただし正規化/変換が必要 | ✓ |
| 基本3 + 通過順全4角 | 基本3 + corner_1-4。corner_1/2はnull率高（44-52%） | |

**User's choice:** 5指標（拡張）
**Notes:** finish_timeは正規化が必要、marginは数値変換が必要

### Q3: finish_timeの正規化方法

| Option | Description | Selected |
|--------|-------------|----------|
| コース×距離のz-score | 各コース×距離の平均からの偏差。競馬分析で一般的 | ✓ |
| 勝馬との差（秒） | シンプルだがレースペースの影響を受ける | |
| finish_timeを除外 | 正規化の複雑さを避ける | |

**User's choice:** コース×距離のz-score

### Q4: lag featureの形式

| Option | Description | Selected |
|--------|-------------|----------|
| lag生値 + 統計量 | 生値 + 3走/5走の平均・標準偏差。モデルが傾向を捉えやすい | ✓ |
| lag生値のみ | 特微量数を抑える。LightGBMなら非線形変換可能 | |

**User's choice:** lag生値 + 統計量

---

## 騎手・調教師の特徴量化

### Q1: 騎手・調教師をどう特微量化するか

| Option | Description | Selected |
|--------|-------------|----------|
| Categorical直接 | LightGBM native categorical。最もシンプル | |
| 統計量のみ | 勝率等を計算。初騎乗時の欠損が発生 | |
| Categorical + 統計量の両方 | 最大の表現力。騎手名と数値統計量の両方 | ✓ |

**User's choice:** Categorical + 統計量の両方

### Q2: 統計量として何を計算するか

| Option | Description | Selected |
|--------|-------------|----------|
| 基本3指標 | 3着内率、勝率（1着率）、騎乗数 | ✓ |
| 6指標（詳細） | 基本3 + 連対率 + 複勝率 + 賞金総額 | |

**User's choice:** 基本3指標

### Q3: 統計量の計算期間

| Option | Description | Selected |
|--------|-------------|----------|
| 100戦 / 1年 | 直近100戦または1年の短い方。十分なサンプル確保 | ✓ |
| 50戦のみ | 最近の調子に特化。長期休養後はサンプル不足 | |
| 1年間のみ | 季節性をキャッチ。新米騎手はサンプル不足 | |

**User's choice:** 100戦 / 1年（短い方）

---

## 初出走馬の扱い

### Q1: 初出走馬のlag featureの扱い

| Option | Description | Selected |
|--------|-------------|----------|
| NaNのまま | LightGBMがNaNをnative処理。「データがない」信号として働く | |
| 平均値で補完 | 「データがない」信号が失われる | |
| NaN + デビューフラグ | NaNのまま + is_debut列。明示的な信号 + NaN処理 | ✓ |

**User's choice:** NaN + デビューフラグ
**Notes:** データ分析の結果、11.8%のエントリーが初出走（36,802件/311,806件）。7.7%の馬は1走のみ。

### Q2: 出走数が3走未満の統計量

| Option | Description | Selected |
|--------|-------------|----------|
| 可能な分だけ計算 | 2走なら2走で平均を出す。情報の損失なし | ✓ |
| 最低レース数未満は全てNaN | 一貫性あるが、1走の情報が完全に失われる | |

**User's choice:** 可能な分だけ計算

---

## Target変数と評価設計

### Q1: targetをfeature層に含めるか

| Option | Description | Selected |
|--------|-------------|----------|
| 一緒に入れる | 学習用Parquetにtarget_top3列。Phase 7で即学習可能 | ✓ |
| 別にする | targetは別ステップ。Phase 7で結合が必要 | |

**User's choice:** 一緒に入れる方針。ユーザーから詳細な指定あり：

**ユーザー指定事項（全文）:**
- 学習用feature Parquetに `target_top3` 列を含める
- 将来の予測用データにはtargetは存在しないため、学習用と予測用で区別できる設計
- target_top3の定義:
  - 正式着順 1〜3着 → target_top3 = 1
  - 正式着順 4着以下 → target_top3 = 0
- 未完走馬:
  - 取消・除外・発走除外 → 学習対象から除外
  - 競走中止・落馬・失格等（出走したが完走せず）→ target_top3 = 0
  - 同着で3着以内 → target_top3 = 1
  - 降着・失格は最終確定後の公式着順を基準
- 補助列: result_status / is_dnf を残して後から分析可能にする

---

## Claude's Discretion

- finish_timeのz-score正規化の具体的実装（コース×距離の平均・標準偏差計算方法）
- marginの数値変換マッピングテーブル定義
- lag feature生成のpandas実装（.shift(1), groupby等の具体的操作）
- feature Parquetのファイル構成
- rolling統計量の実装詳細
- result_status/is_dnf補助列の値定義
- CategoricalDtype変換の実装

## Deferred Ideas

None — discussion stayed within phase scope.
