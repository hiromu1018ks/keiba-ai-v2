# Phase 6: Data Integration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-14
**Phase:** 06-Data Integration
**Areas discussed:** スキーマ調停方針, 統合corpus出力構成, オッズテーブルの扱い, 範囲・本格スクレイプ

---

## スキーマ調停方針

### Q1: `(国際)→graded_stakes` の乖離をどう調停するか

| Option | Description | Selected |
|--------|-------------|----------|
| Kaggle側マッピング削除（推奨） | column_mapping.py:68 の (国際)→graded_stakes を削除。両側とも GRADE_REGEX のみで判定。スキーマ変更不要 | ✓ |
| 両側にinternational列追加 | race_flag_international 列を RaceSchema に新設し両側で取得。スキーマ変更 + Phase 1 audit メタデータ更新が必要 | |
| You decide | Claude に判断委譲 | |

**User's choice:** Kaggle側マッピング削除（A）
**Notes:** 最初の提示で「説明が足りなさすぎてよくわからん」とフィードバック。`graded_stakes`（重賞フラグ）、`(国際)`（国際競走指定）、なぜ Kaggle/スクレイプ間で定義不整合が起きるかを平易に再説明した上で選択。Phase 4 P07 の判断と整合、STATE.md の Phase 6 必須調停事項を解決。

### Q2: dtype（int64↔Int64, object↔boolean, object↔datetime）をどこで統一するか

| Option | Description | Selected |
|--------|-------------|----------|
| 統合時に正規化（推奨） | 統合 corpus 出力時に両側を nullable 型に揃える。元の Kaggle/scraped Parquet は保持。Phase 6 が唯一の正規化ポイント | |
| Kaggle再生成 | Phase 2 を nullable 型で再実行して Kaggle Parquet 自体を差し替え → 統合。元ファイル変更、Phase 2 成果物の再検証が必要 | ✓ |
| You decide | Claude に判断委譲 | |

**User's choice:** Kaggle再生成（B）
**Notes:** 推奨（統合時正規化）ではなく Kaggle 側 Parquet 自体を再生成する方を選択。Phase 2 相当の再検証（D-05 の8項目）を Phase 6 で実施する責務を伴う。

---

## 統合corpus出力構成

### Q1: 統合 corpus の出力場所はどこにするか

| Option | Description | Selected |
|--------|-------------|----------|
| data/standard/unified/（推奨） | 新規ディレクトリ出力。元の Kaggle/scraped Parquet は保持。統合成果物が独立 | |
| data/standard/ 既存上書き | {table}.parquet に2022-分を結合して上書き。Phase 3 はそのまま読めるが区別が消える | ✓ |
| You decide | Claude に判断委譲 | |

**User's choice:** data/standard/ 既存上書き（B）
**Notes:** 推奨（unified/）ではなく既存上書きを選択。Phase 3 のパス変更不要を優先。`data/standard/scraped/`（月分割元データ）と `data/raw/kaggle/`（CSV）が再生成可能な追跡源として残る。

### Q2: 統合 corpus のファイル粒度はどうするか

| Option | Description | Selected |
|--------|-------------|----------|
| テーブル別単一ファイル（推奨） | Phase 2 D-06 と一致。Phase 3 読み込みロジック不変 | ✓ |
| 年別分割 | 大容量化に強いが Phase 3 読み込みロジック変更が必要 | |
| You decide | Claude に判断委譲 | |

**User's choice:** テーブル別単一ファイル（A）

---

## オッズテーブルの扱い

### Q1: 統合 corpus に odds_trifecta/payoff を含めるか

| Option | Description | Selected |
|--------|-------------|----------|
| race/entry/result のみ統合（推奨） | odds_trifecta/payoff は data/standard/ に現状維持。Phase 8 は entry.win_odds から Harville プロキシ。Kaggle オッズは失われない | ✓ |
| Kaggleオッズも部分統合 | odds_trifecta/payoff(2015-2021のみ) を統合。2022-2024は欠損の非対称。Phase 8では未使用 | |
| You decide | Claude に判断委譲 | |

**User's choice:** race/entry/result のみ統合（A）
**Notes:** Phase 5 DEFERRED により 2022-2024 の三連複オッズは取得不可。Phase 8 は単勝 Harville プロキシを使用するため、三連複オッズ corpus は必須でない。

---

## 範囲・本格スクレイプ

### Q1: 本格スクレイプ（未実行）を Phase 6 でどう扱うか

| Option | Description | Selected |
|--------|-------------|----------|
| 別実行してから統合 | Phase 6 開始前に別タスクで全期間スクレイプ実行 → 完了後 Phase 6 は統合ロジックのみ | ✓ |
| Phase 6に含める | Phase 6 に本格スクレイプ実行を含める（スコープ拡大） | |
| テストで検証・本格は別（推奨） | テストデータで統合ロジックを構築・検証。本格スクレイプは別途/並行実行し完了後に最終 corpus 再生成 | |

**User's choice:** 別実行してから統合（A）
**Notes:** 推奨（テスト検証・本格は別）ではなく、本格スクレイプを Phase 6 の**前に**完了させる方を選択。Phase 6 は「スクレイプ済みデータ前提」の統合ロジックに集中。本格スクレイプ実行を STATE.md の前提タスクとして明記。

### Q2: 統合 corpus のデータ範囲はどうするか

| Option | Description | Selected |
|--------|-------------|----------|
| ROADMAP準拠 2015-2024（推奨） | 取得は2026/5まで実施するが統合 corpus は 2015-2024 にフィルタ。ROADMAP/Phase 9 バックテストと整合 | |
| 実データ全部 2015-2026/5 | 取得した分（2026/5まで）を全部統合。バックテスト対象期間が延長。ROADMAP成功基準#3から逸脱 | ✓ |
| You decide | Claude に判断委譲 | |

**User's choice:** 実データ全部 2015-2026/5（B）
**Notes:** 推奨（ROADMAP準拠）ではなく実データ全部を選択。ROADMAP 成功基準#3（2015-2024）からの拡張として CONTEXT.md に明記。Phase 9 バックテストは 2015-2026/5 で実行可能。

---

## Claude's Discretion

- 重複排除の具体的検証ロジック（race_id で dedup、境界年の衝突確認）
- 統合 corpus 検証の深度（Phase 2 D-05 の8項目の再適用範囲、audit 再実行タイミング）
- Kaggle converter 修正の影響範囲調査（他のフラグマッピング・既存テストへの波及）
- feature 再生成のタイミング判断（Phase 6 スコープ内外、基本は Phase 3 再実行 = 別タスク）

## Deferred Ideas

- feature 層の再生成（Phase 3 再実行）— Phase 6 完了後、Phase 7 前
- odds_trifecta/payoff の統合 — Phase 5 再開時（Phase 5 D-04 方針）
- ROADMAP 成功基準#3 の範囲更新（2015-2024 → 2015-2026/5）— Phase 9 計画時に再調整
