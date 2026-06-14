# Phase 5: Trifecta Odds Scraping - Context

**Gathered:** 2026-06-14
**Status:** Ready for planning

<domain>
## Phase Boundary

2022年1月〜2026年5月末のJRA中央競馬**平地レース**について、**全通りの三連複オッズ**（C(n,3)、最大 C(18,3)=816通り）を netkeiba から取得し、Phase 1 で契約スキーマとして定義済みの `PayoffSchema`（long形式）に格納して standard 層 Parquet に保存する。EV計算（Phase 8）が依存する「市場オッズ」データを供給するフェーズ。

**In scope:**
- netkeiba オッズページからの全通り三連複オッズ取得（Phase 4 の fetch/parse/normalize 基盤を再利用）
- 取得した全組合せオッズの `PayoffSchema` 形式（race_id + combo_1/2/3 + odds）への正規化・standard Parquet 出力
- Phase 4 が取得済みのレース（race/entry/result）と同一範囲（2022-2026、平地）のオッズ取得
- 既知のレース結果（結果ページに載る的中組オッズ）とのスポットチェック検証（成功基準#3）
- 部分網羅（全通りでなく上位人気のみ、または近年のみ等）でも取得できた分を保存

**Out of scope:**
- 三連複以外の券種（単勝/複勝/馬連/三連単等）のオッズ取得 — 三連複に特化（REQUIREMENTS Out of Scope）
- 障害レースの三連複オッズ（平地のみ、Phase 4 と一貫）
- EV計算・Harville確率（Phase 8）
- Kaggle(2015-2021)と自前(2022-2024)オッズの統合（Phase 6）— Phase 5は自前期間のオッズ取得のみ
- 発走時オッズのリアルタイム追跡（RTOP-02、v2要件）

</domain>

<decisions>
## Implementation Decisions

### オッズデータソース
- **D-01:** **netkeiba オッズページ優先**。Phase 4 と同じ基盤（db.netkeiba.com + Playwright fetch → raw HTML → BS4 parse）で完結でき、race_id による他テーブル（race/entry/result）との紐付けが自明。JRA公式や外部プロバイダは、netkeiba で過去データが取得できない場合の後続検討対象（Phase 5 内では netkeiba 一貫性を最優先）
- **D-02:** **部分網羅でも進める**。netkeiba が全通り履歴を保持していない場合でも、取得できた分（上位人気のみ、近年のみ等）を standard 層に保存し、Phase 8 EV計算で使える範囲を最大化する。完全網羅を必須とはしない（Phase 5 の完了をブロックしない）

### 出力スキーマ
- **D-03:** **既存 `PayoffSchema`（`src/schemas/payoff.py`）を使用**。long形式（race_id + combo_1/2/3 + odds: Optional[float] + payoff_amount: Optional[int]）。Phase 1 で「Phase 5: Full payoff data from JRA scraping (all trifecta combinations)」として契約定義済み。全816組合せを格納し、`odds` は全通り、`payoff_amount` は的中組のみ（残りは None）。新スキーマ定義不要
- **D-04:** Kaggle の `OddsTrifectaSchema`（wide/top-3）とは形式が異なるが、Phase 6 統合時に Kaggle top-3 を long 形式に変換して `payoff` テーブルの部分集合として取り込む方針（Phase 6 の作業）

### 対象範囲
- **D-05:** **Phase 4 と同じ 2022年1月〜2026年5月末**。結果データ（race/entry/result）と同一範囲とし、全スクレイプ済みレースにオッズが紐づく。Phase 6 統合でも一貫
- **D-06:** **障害レースは除外（平地のみ）**。Phase 4 の平地中心方針と一貫。障害は頭数・オッズ構造が異なり EV 計算でも別扱いになりがち

### Claude's Discretion
- **人気列（popularity）:** netkeiba オッズページが各組合せの三連複人気順位を表示する場合、`PayoffSchema` に `popularity` 列を追加して取得する（post-race フラグなのでリーク問題なし、EV検証・人気バイアス分析に有用）。実構造確認後に取得不可と判明すれば省略。研究エージェントがオッズページ構造を確認して判断
- **オッズ種別（確定/発走時）:** デフォルト推奨は**確定オッズ**（払戻基準の最終オッズ）。発走時スナップショットが実データで取得可能なら別列/別テーブルでの併存保存を検討するが、履歴保持が稀なら確定のみ取得し、Phase 9（BKTS-04）で「発走時スナップショットは未保存・確定との差は無視できる前提」をドキュメント化する。研究エージェントが実データで確認後に判断

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Context
- `.planning/PROJECT.md` — プロジェクト概要、3層アーキテクチャ、スクレイピング方針、買い目方針
- `.planning/REQUIREMENTS.md` — 要件 SCRP-04（Phase 5 担当）と BKTS-04（Phase 9、オッズ種別関連）、Traceability
- `.planning/ROADMAP.md` — Phase 5 定義・成功基準3項目・Phase 4/6 依存関係

### Specification
- `docs/specification.md` §13 スクレイピング方針 — fetch/parse/normalize/feature 分離、HTML保存必須、重複回避、大量並列なし

### Prior Phase Context（直接依存）
- `.planning/phases/04-scraping-infrastructure-race-data/04-CONTEXT.md` — **必読**。Phase 4 の全決定事項。netkeiba 取得方針、Playwright+BS4 パイプライン、raw HTML 保存設計、レートリミット。Phase 5 はこの基盤を再利用
- `.planning/phases/01-data-schema-leak-audit/01-CONTEXT.md` — Phase 1 決定事項。5テーブル分離、pre/post-race 分類、audit 関数

### Schema Definitions（正規化先・MUST READ）
- `src/schemas/payoff.py` — **PayoffSchema**: race_id, combo_1/2/3 (int), odds (Optional[float]), payoff_amount (Optional[int])。全 post-race。Phase 5 の出力先
- `src/schemas/odds_trifecta.py` — OddsTrifectaSchema: Kaggle top-3 wide 形式（0.1単位 int）。Phase 6 統合時の参照元。Phase 5 出力先ではない
- `src/schemas/audit.py` — audit_leakage(): odds/payoff は全 post-race なので feature 層混入検出の対象外だが、normalizer で利用可能

### Existing Scraper Infrastructure（Phase 4 実装・再利用対象）
- `src/scraper/fetcher.py` — FetcherSession (Playwright)、fetch_race_html、fetch_with_retry、原子書き込み、重複回避、レートリミット。オッズページ取得もこの基盤を拡張または再利用
- `src/scraper/parser.py` — parse_race_html、resolve_columns_by_header（ヘッダ駆動列解決）。オッズページ解析も同じ BS4 パターンで踏襲
- `src/scraper/normalizer.py` — write_partitioned_parquet（read-merge-dedup、原子 replace、partition_map）。オッズも同じ Parquet 出力パターン
- `src/scraper/enumeration.py` — enumerate_races / enumerate_race_day_urls。オッズ取得対象レースの列挙（Phase 4 の race_id 一覧を再利用）
- `src/scraper/orchestrator.py` — run_scrape（live/fetch_html 切替、progress、max_races）。オッズ取得の orchestrator も同じ構造
- `src/scraper/models.py` — RaceRef データクラス

### Critical Finding（研究エージェントへの最重要検証事項）
- **レース結果ページ `/race/{race_id}/` の払戻欄には三連複の的中組1件のみ**（例: `4-10-11 / 2,150 / 4`）。全816通りのオッズはこのページに存在しない。**別のオッズページ/API の特定が必要** — 実際の `data/raw/netkeiba/2023/06/*.html` で確認済み（href grep で `/odds/` リンクは検出されず、nav は「結果/払戻」と `/race/pay/` のみ）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/scraper/fetcher.py` FetcherSession / fetch_race_html / fetch_with_retry — オッズページ取得も同じ Playwright セッション・重複回避・レートリミット基盤を使用可能
- `src/scraper/parser.py` resolve_columns_by_header + DEFAULT_HEADER_ALIASES — ヘッダ駆動の列解決。オッズテーブルも `<th>` ベースで解決すればレイアウト変動に強い
- `src/scraper/normalizer.py` write_partitioned_parquet — read-merge-dedup on PK、原子 os.replace。オッズ行も race_id+combo を PK として同じマージ戦略
- `src/scraper/enumeration.py` enumerate_races — Phase 4 が列挙した race_id 一覧をそのままオッズ取得対象に再利用（同一 2022-2026 平地範囲）

### Established Patterns
- fetch/parse/normalize 分離（specification.md §13）— raw HTML を先保存してから parse。オッズページも同じ分離
- race_id ベース重複回避（SCRP-05）— 既存 HTML キャッシュがあれば再取得スキップ
- ヘッダ駆動列解決（HIGH #10）— 固定 `cols[N]` インデックス禁止
- Pydantic は型定義専用、DataFrame レベルで一括処理（Phase 1 D-02）
- loguru ログ、pytest テスト。`tests/scraper/` に既存テストパターン
- standard 層はテーブル別・日付分割 Parquet（`data/standard/scraped/{YYYYMM}/`）

### Integration Points
- **入力**: netkeiba オッズページ（Playwright取得 → raw 保存。既存 `data/raw/netkeiba/{YYYY}/{MM}/` 構造にオッズ用 raw を追加、または別ディレクトリ）
- **出力**: `data/standard/scraped/{YYYYMM}/payoff.parquet`（Phase 4 の race/entry/result と同パーティション。PayoffSchema long形式）
- **上流**: Phase 4 の enumerate_races が対象 race_id を提供。Phase 4 race/entry/result と race_id で結合
- **下流**: Phase 6 が Kaggle odds_trifecta(top-3) を long 化して `payoff` に統合。Phase 8 が `payoff.odds` を市場オッズとして Harville EV 計算に使用。Phase 9 がオッズ種別（確定/発走時）の差異を BKTS-04 で評価

</code_context>

<specifics>
## Specific Ideas

- **結果ページとの交差検証**: 各レースの結果ページ払戻欄には三連複的中組のオッズが1件載っている（既に Phase 4 が raw HTML を `data/raw/netkeiba/` に保存済み）。オッズページから取得した全通りオッズの中から、この的中組のオッズを引き当てて値が一致するかで、オッズ取得の正確性をスポットチェック可能（成功基準#3 の検証手段）
- **Kaggle 期間の照合**: Kaggle odds.csv は三連複 top-3 人気のオッズを持つ。スクレイパーの妥当性は、Kaggle 期間（2015-2021）の既知レースで、オッズページの取得ロジックが top-3 を正しく抽出できるか（期間が被る場合）で検証可能 — ただし Phase 5 対象は 2022-2026 なので直接被りはない。間接的なロジック検証として参考
- **netkeiba は Kaggle の元ソース**: Kaggle データは元々 netkeiba 由来。オッズページ構造が Kaggle の top-3 形式と整合する可能性が高い

</specifics>

<deferred>
## Deferred Ideas

- **三連単（三連複以外の券種）オッズ取得** — 三連複特化の方針（REQUIREMENTS Out of Scope）。将来の全券種拡張時の別フェーズ
- **発走時オッズのリアルタイム追跡** — RTOP-02（v2要件）。Phase 5 では確定オッズ履歴取得が主眼
- **外部/有料オッズプロバイダの導入** — netkeiba で過去全通りオッズが取得できない場合の最終手段。D-02（部分網羅許容）で Phase 5 は完結させるため、Phase 5 内では導入しない。netkeiba 不十分が判明した場合、Phase 6 以降で検討
- **Kaggle odds_trifecta(top-3) と scraped payoff のスキーマ統合** — Phase 6（Data Integration）の作業。D-04 で方針のみ記録

</deferred>

---

*Phase: 05-Trifecta Odds Scraping*
*Context gathered: 2026-06-14*
