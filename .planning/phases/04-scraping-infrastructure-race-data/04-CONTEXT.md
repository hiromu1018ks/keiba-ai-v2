# Phase 4: Scraping Infrastructure & Race Data - Context

**Gathered:** 2026-06-13
**Status:** Ready for planning

<domain>
## Phase Boundary

2022-2026年のJRAレース結果・出走情報をnetkeibaからスクレイピングし、Phase 1-2で定義・実績化したstandard層Parquetと同じスキーマに変換するfetch/parse/normalizeパイプラインを構築する。

**In scope:**
- Playwrightベースのfetch/parse/normalizeパイプライン構築
- netkeibaカレンダーページからのレース一覧列挙（月→開催日→レース）
- レース結果HTMLの取得・raw保存・BS4+lxmlでのパース
- パース済みデータのstandard層Parquet（race/entry/result）への変換
- 重複取得回避（race_idベースのHTMLキャッシュ）
- レート制限の実装
- 2022年1月〜2026年5月31日の全JRA中央競馬平地レースが対象

**Out of scope:**
- 全通りの三連複オッズ取得（Phase 5）
- Kaggle/自前データの統合（Phase 6）
- feature層の特徴量生成（Phase 3で完了済み）
- 血統・ラップ詳細・調教コメント等の拡張データ取得（v2要件）
- 自動投票・リアルタイム運用

</domain>

<decisions>
## Implementation Decisions

### スクレイピング先と取得方法
- **D-01:** **netkeiba（db.netkeiba.com）中心**。Kaggleデータの元ソースであり、HTML構造が安定している。レース結果ページ1ページでrace/entry/resultの全情報が揃う
- **D-02:** **Playwright**でHTML取得 → rawファイルに保存 → **BS4 + lxml**でparse。specification.md §13の「取得と解析を分ける」方針に合致。httpxは使用せず、最初からPlaywrightで確実に取得
- **D-03:** netkeibaのレース結果ページから**Phase 3の全特徴量情報を取得可能**。以下を確認済み:
  - レースヘッダー: 競馬場・距離・芝ダート・馬場状態・天候・発走時刻・meeting_num・grade・race_name
  - 出走馬テーブル: 枠番・馬番・馬名・性齢・斤量・騎手・馬体重・体重増減・単勝オッズ・人気
  - 結果テーブル: 着順・タイム・着差・通過順・上がり3F・調教師・賞金
  - 払戻テーブル: 三連複オッズ・組み合わせ（Phase 5で活用）
  - コーナー通過順位・ラップタイム

### レース一覧取得戦略
- **D-04:** netkeibaの**カレンダーページ**から**月→開催日→レース**の3段階で全レースを列挙。確実に実在するレースのみを取得
- **D-05:** スクレイピング対象期間は**2022年1月〜2026年5月31日**。ROADMAPの「2022-2024」から拡張（実データの最新まで取得）

### HTML保存設計
- **D-06:** raw HTMLのディレクトリ構造は**年/月階層**: `data/raw/netkeiba/{YYYY}/{MM}/`
- **D-07:** ファイル名は**race_idベース**: `{race_id}.html`（例: `202206010101.html`）。standard層との対応が明確
- **D-08:** 重複判定は**race_idベース**。既存HTMLファイルがあれば再取得をスキップ（SCRP-05要件）

### スキーマギャップ対応
- **D-09:** **スキーマギャップなし** — Playwrightでの実調査（2022年中山1R・11Rを確認）により、standardスキーマの全フィールドがnetkeibaから取得可能
- **D-10:** 20個のrace_flagフィールドはレース条件テキストから**パース導出**:
  - `(ハンデ)` → race_flag_handicap
  - `(牝)` → race_flag_mare_only
  - `3歳未勝利` → race_flag_maiden + 年齢制限
  - `(国際)` → 国際競走
  - `(特指)` → 特別指定
  - `(馬齢)` → 馬齢定量（ハンデではない）
  - `GIII`等 → grade/stakes系フラグ
- **D-11:** meeting_numはレースヘッダー `1回中山` から取得可能
- **D-12:** region（所属）は調教師列の `[東]` `[西]` プレフィックスから取得可能
- **D-13:** prize_money（賞金）は結果テーブルの賞金列から取得可能

### Claude's Discretion
- レース条件テキストからrace_flagへの具体的パースロジック（正規表現パターンの定義）
- netkeiba HTMLの具体的なDOM構造に基づくBS4パース実装
- レート制限の具体的な間隔（1-2秒程度）
- エラーハンドリングの詳細（取得失敗時のリトライ・スキップ・ログ等）
- カレンダーページの具体的なURLパターンとパース方法
- 出走取消・競走中止等の特殊ケースのパース対応

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Context
- `.planning/PROJECT.md` — プロジェクト概要、3層アーキテクチャ、スクレイピング方針
- `.planning/REQUIREMENTS.md` — 要件定義（SCRP-01〜SCRP-05が該当）
- `.planning/ROADMAP.md` — Phase 4定義、成功基準4項目

### Prior Phase Context
- `.planning/phases/01-data-schema-leak-audit/01-CONTEXT.md` — Phase 1の全決定事項。standardスキーマ定義、pre/post-race分類、5テーブル分離、audit関数
- `.planning/phases/02-kaggle-data-pipeline/02-CONTEXT.md` — Phase 2の全決定事項。CSV→Parquet変換パターン、DTYPE_SPEC、flag変換、着順注記処理
- `.planning/phases/03-feature-engineering/03-CONTEXT.md` — Phase 3の全決定事項。feature columns、lag feature設計、target定義

### Specification
- `docs/specification.md` §13 スクレイピング方針 — fetch/parse/normalize/feature分離、HTML保存必須、重複回避、大量並列なし

### Schema Definitions (MUST READ for normalization)
- `src/schemas/race.py` — RaceSchema: race_id, race_date, meeting_num, course_code, distance, surface, direction, weather, condition, head_count, start_time, 20個のrace_flag_*
- `src/schemas/entry.py` — EntrySchema: horse_race_id, bracket_number, horse_number, horse_name, horse_sex, horse_age, jockey_name, trainer_name, horse_weight, weight_change, carried_weight, popularity, win_odds, region
- `src/schemas/result.py` — ResultSchema: finish_position, finish_note, finish_time, margin, corner_1-4, last_3f, prize_money
- `src/schemas/audit.py` — audit_leakage()関数: standard生成時にpost-raceカラム混入を検出

### Existing Pipeline (patterns to follow)
- `src/pipeline/kaggle_converter.py` — raw→standard変換のコードパターン。filtering、table splitting、transform、write、audit
- `src/pipeline/column_mapping.py` — カラムマッピング、DTYPE_SPEC

### netkeiba Page Structure (verified via Playwright investigation)
- Race result URL pattern: `https://db.netkeiba.com/race/{race_id}/`
- Race header: `ダ右1200m / 天候 : 晴 / ダート : 良 / 発走 : 09:55`
- Race conditions: `2022年01月05日 1回中山1日目 3歳未勝利 (馬齢)` or `4歳以上オープン (国際)(特指)(ハンデ)`
- Result table columns: 着順/枠番/馬番/馬名/性齢/斤量/騎手/タイム/着差/通過/上り/単勝/人気/馬体重/調教師/馬主/賞金
- Trainer column: `[東] 相沢郁` or `[西] ...` — prefix encodes region
- Payoff section: 三連複/三連単 odds and combinations
- Calendar URL pattern: `https://db.netkeiba.com/race/calendar/{YYYYMM}/`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/schemas/*.py` — Phase 1で実装済みのstandardスキーマ。スクレイピングデータのnormalization先として直接使用
- `src/schemas/audit.py` — audit_leakage()でstandard生成後のpost-raceカラム混入を検出可能
- `src/pipeline/kaggle_converter.py` — raw→standard変換のパターン。filter→split→transform→write→auditのフローを踏襲
- `src/pipeline/column_mapping.py` — DTYPE_SPEC、flag変換等のパターン

### Established Patterns
- Pydantic BaseModelは型定義用、DataFrameレベルで一括処理（Phase 1 D-02）
- `json_schema_extra={"pre_race": True/False}` でカラムのメタデータ駆動分類
- loguruでログ出力（プロジェクト全体で統一）
- pytestでテスト。tests/に既存テストパターンあり
- standard層はテーブル別単一ファイルParquet（Phase 2 D-06）

### Integration Points
- **入力**: netkeibaのHTML（Playwright取得 → `data/raw/netkeiba/{YYYY}/{MM}/{race_id}.html` に保存）
- **出力**: standard層Parquet（`data/standard/race.parquet`, `entry.parquet`, `result.parquet` に追記または新規生成）
- **Phase 5**（Trifecta Odds）が同じスクレイピング基盤を使って三連複オッズを取得
- **Phase 6**（Data Integration）がKaggle + スクレイピングのstandard Parquetを統合
- **Phase 3**（Feature Engineering）が統合データに対して再実行される

</code_context>

<specifics>
## Specific Ideas

- **netkeibaはKaggleの元データソース**: Kaggleデータは元々netkeibaから収集されたもの。したがってstandardスキーマとの完全な互換性が期待できる。パースロジックの妥当性は、Kaggle期間（2015-2021）の既知レースとの照合で検証可能
- **レース条件テキストのパース**: `4歳以上オープン (国際)(特指)(ハンデ)` のような形式からrace_flagを導出する正規表現パターンを定義する。括弧内のキーワードと年齢/クラス表記の組み合わせで20個のフラグを網羅
- **Playwright選択の理由**: netkeibaのページは静的HTMLとしても取得可能だが、ユーザー判断でPlaywrightをプライマリに採用。将来のJavaScript レンダリングページ対応も視野に入る
- **データ範囲の拡張**: ROADMAPでは「2022-2024」としていたが、実際のデータ取得は2026年5月31日まで実施。Phase 6以降でこのデータを活用
- **馬体重のパース**: `456(+4)`, `478(-2)`, `472(0)` の形式から horse_weight と weight_change を抽出。初出走等で馬体重がない場合のNaN対応が必要

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.
</deferred>

---

*Phase: 04-Scraping Infrastructure & Race Data*
*Context gathered: 2026-06-13*
