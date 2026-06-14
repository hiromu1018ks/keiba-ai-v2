# Phase 5: Trifecta Odds Scraping - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-14
**Phase:** 05-Trifecta Odds Scraping
**Areas discussed:** オッズ取得元, 出力スキーマ, オッズ種別, 対象範囲

---

## オッズ取得元

### Q1: 全816通りの三連複オッズの取得元はどの方針か

| Option | Description | Selected |
|--------|-------------|----------|
| netkeibaオッズページ優先 | Phase 4と同じ基盤で完結、race_id紐付け自明。研究エージェントが実際の構造・履歴保持範囲を検証 | ✓ |
| JRA公式サイト優先 | 公式データで信頼性高いが形式が異なり別パーサ・別フェッチが必要 | |
| 外部プロバイダも検討 | netkeiba履歴がない場合の代替として全通り履歴を提供する外部/有料サービスも調査 | |
| 取得元を知っている(Other) | ユーザーが特定ソースを心当たりとして指定 | |

**User's choice:** netkeibaオッズページ優先（推奨）
**Notes:** Phase 4 基盤との一貫性が最大の理由。結果ページには的中組1件しかないことはコードベース精査（実際の `data/raw/netkeiba/2023/06/*.html` の払戻欄確認）で発見済み。

### Q2: 全通りオッズが完全に取れない場合の扱い

| Option | Description | Selected |
|--------|-------------|----------|
| 部分網羅でも進める | 上位人気のみ/近年のみでも取れた分を保存、Phase 8で使える範囲を最大化 | ✓ |
| 完全網羅が必須 | 全816通りが必須、足りなければJRA/外部も含めて継続調査 | |
| netkeiba前提で計画 | netkeibaが全通り履歴を持つ前提、研究でダメなら計画修正 | |

**User's choice:** 部分網羅でも進める（推奨）
**Notes:** Phase 5 の完了をブロックしない現実的妥協点。

---

## 出力スキーマ

### Q1: 全通りの三連複オッズの保存先スキーマは

| Option | Description | Selected |
|--------|-------------|----------|
| PayoffSchema使用 | 既存long形式(race_id+combo1/2/3+odds+payoff_amount)、Phase 1契約スキーマ | ✓ |
| odds/payoff別テーブル分離 | オッズと払戻を別テーブルに、意味的には綺麗だが新スキーマ定義が必要 | |
| OddsTrifectaSchema拡張 | wide/top-3を816列に拡張、Parquet効率・クエリ性が著しく悪化 | |

**User's choice:** PayoffSchema使用（推奨）
**Notes:** Phase 1 で "Phase 5: Full payoff data" として契約定義済み。Kaggle top-3 は Phase 6 で long 化して部分集合として統合（D-04）。

### Q2: 各組合せの三連複人気順位を取得するか

| Option | Description | Selected |
|--------|-------------|----------|
| PayoffSchemaにpopularity追加 | 人気も取得・保存、EV検証・バイアス分析に有用 | |
| スキーマ現状維持 | odds+payoff_amountのみ、人気はoddsソートで導出可能 | |
| Claude/研究に委ねる | 実構造確認後に取得可能なら追加・不可なら省略 | ✓ |

**User's choice:** Claude/研究に委ねる
**Notes:** netkeibaオッズページが各組合せの人気を表示するか次第。post-race なので追加してもリーク問題なし。

---

## オッズ種別（確定/発走時）

### Q1: 歴史データとして取得するオッズのタイミングは

| Option | Description | Selected |
|--------|-------------|----------|
| 確定オッズのみ | 払戻基準の最終オッズ、歴史的に取得可能なのは実質これのみ | |
| 確定+発走時の併存 | 発走時スナップショットも別列/別テーブルで保存、BKTS-04差異分析向け | |
| Claude/研究に委ねる | 実データでどちらが取得可能か確認後に判断 | ✓ |

**User's choice:** Claude/研究に委ねる
**Notes:** デフォルト推奨は確定オッズ。発走時は全通りスナップショット履歴が稀。Phase 9 BKTS-04 で前提をドキュメント化。

---

## 対象範囲

### Q1: Phase 5のオッズ取得範囲は

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 4と同じ2022-2026 | 結果データと同範囲、全スクレイプ済みレースにオッズが紐づく | ✓ |
| ROADMAP通り2022-2024 | 厳密に絞る、ただし2025-2026レースにオッズが付かずEV対象から漏れる | |
| Phase 4実績に追従 | Phase 4がどこまで取ったか確定次第で同期 | |

**User's choice:** Phase 4と同じ2022-2026（推奨）

### Q2: 障害レースの三連複オッズの扱いは

| Option | Description | Selected |
|--------|-------------|----------|
| 障害は除外（平地のみ） | Phase 4（平地中心）と一貫、障害は頭数・オッズ構造が異なる | ✓ |
| 障害も含める | 障害の三連複も取得、ただしrace/entry/resultに障害がない場合オッズが孤立 | |

**User's choice:** 障害は除外（平地のみ）（推奨）

---

## Claude's Discretion

- **人気列（popularity）**: netkeibaオッズページ構造確認後、取得可能なら PayoffSchema に popularity 列追加、不可なら省略
- **オッズ種別（確定/発走時）**: デフォルト確定オッズ。発走時が取得可能なら併存検討、稀なら確定のみで Phase 9 で前提ドキュメント化

## Deferred Ideas

- 三連単・他券種のオッズ取得（三連複特化、将来フェーズ）
- 発走時オッズのリアルタイム追跡（RTOP-02、v2要件）
- 外部/有料オッズプロバイダ導入（netkeiba不十分時の最終手段、Phase 6以降で検討）
- Kaggle odds_trifecta と scraped payoff のスキーマ統合（Phase 6 の作業、方針のみ D-04 に記録）

---

*Discussion log for Phase 05-Trifecta Odds Scraping*
*Generated: 2026-06-14*
