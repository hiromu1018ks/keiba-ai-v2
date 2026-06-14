# Phase 6: Data Integration - Context

**Gathered:** 2026-06-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Kaggle (2015-2021) とスクレイピング (2022-2026/5) の standard Parquet を、2015-2026/5 にまたがる**単一の統合 corpus** にマージし、Phase 3 (feature)・Phase 7 (model) が「出所を意識せず1つのデータセット」として扱えるようにする。スキーマ定義の不整合（`(国際)` 誤マッピング・dtype 乖離）を調停し、Kaggle/スクレイプ両起源の行が standard 層で区別できない状態にする。

**In scope:**
- Kaggle converter 修正: `(国際)→graded_stakes` マッピング削除 + nullable 型(`Int64`/`Float64`/`boolean`/`datetime`)での Kaggle Parquet 再生成（Phase 2 相当の再検証含む）
- 統合ロジック: Kaggle + scraped の `race`/`entry`/`result` をマージ、dtype 統一、重複排除
- 統合 corpus 出力: `data/standard/{table}.parquet`（既存上書き、テーブル別単一ファイル）
- 統合 corpus の検証: 行数・スキーマ同一性・重複なし・日付範囲(2015-2026/5)・Phase 1 audit
- 統合範囲: 2015-2026/5（実データ全部、ROADMAP成功基準#3 の 2015-2024 から拡張）

**Out of scope:**
- 本格スクレイプの実行（**Phase 6 の前提タスク**、別実行）— Phase 4 基盤（`run_scrape(live=True)`）で `/gsd-quick` または Phase 4 拡張として別途実施
- `odds_trifecta`/`payoff` テーブルの統合（`race`/`entry`/`result` のみ統合）
- feature 層の再生成（Phase 3 の再実行、Phase 7 前に別途）
- Phase 5（DEFERRED）の三連複オッズ全通り取得

**⚠ 実行前提条件（Phase 6 plan/execute 開始前に満たす必要あり）:**
本格スクレイプ（2022-2026/5 全期間）が未実行。現状 `data/standard/scraped/202306/` はテスト5レースのみ、`data/raw/netkeiba/` も空。Phase 6 開始前に本格スクレイプを別タスクで完了させること（D-06）。完了しないと統合対象データが存在せず、成功基準#1/#3 を検証できない。

</domain>

<decisions>
## Implementation Decisions

### スキーマ調停方針
- **D-01:** `(国際)→race_flag_graded_stakes` の Kaggle 側マッピングを**削除**（`src/pipeline/column_mapping.py:68`）。両側とも `GRADE_REGEX`（GI/GII/GIII/G1/G2/G3/JG*/重賞/full-width ＧＩ 等）でのみ `race_flag_graded_stakes=True` を決定。**スキーマ変更不要**。Phase 4 P07 の判断（`src/scraper/flag_crosswalk.py` で既に削除済み）と整合。STATE.md の Phase 6 必須調停事項（Blockers/Concerns）を解決する。Kaggle `race.parquet` の `graded_stakes=True` 1,348件のうち `(国際)` 由来の誤分類（Listed/OP特別戦）が是正される。
- **D-02:** dtype 統一は **Kaggle 側 Parquet の再生成**で実施。Phase 2 を nullable 型（`Int64`/`Float64`/`boolean`/`datetime`）で再実行し、`data/standard/{table}.parquet` 自体を差し替える。`src/scraper/normalizer.py` の `SCHEMA_DTYPE_MAP`（Phase 4 P05 で定義）と同じ物理型になるよう Kaggle converter（`src/pipeline/kaggle_converter.py`）を調整。**Phase 2 相当の再検証（D-05 の8項目）を Phase 6 で実施**し、行数・値域・参照整合性が崩れていないことを確認。`race_date` は `datetime`、`distance` は `Int64`、`race_flag_*` は `boolean` に統一。

### 統合 corpus 出力構成
- **D-03:** 統合 corpus の出力場所は **`data/standard/{table}.parquet` を既存上書き**（2022-分を結合）。Phase 3 (`feature_generator.py`) はパス変更不要でそのまま統合 corpus を読める。`data/standard/scraped/{YYYYMM}/`（Phase 4 の月分割元データ）と `data/raw/kaggle/`（CSV）は再生成可能な追跡源として保持。`unified/` 等の新規ディレクトリは作らない。
- **D-04:** ファイル粒度は**テーブル別単一ファイル**（`race.parquet`/`entry.parquet`/`result.parquet`、Phase 2 D-06 と一致）。Phase 3 読み込みロジック不変。2015-2026/5（約10年強、数十万行）は単一ファイルで十分に扱えるサイズ。

### オッズテーブルの扱い
- **D-05:** 統合 corpus は **`race`/`entry`/`result` のみ**。`odds_trifecta`/`payoff` は統合 corpus から除外し、`data/standard/` に現状維持（Kaggle 2015-2021 のみ、上書きしない）。Phase 8 (EV) は `entry.win_odds`（単勝オッズ）から Harville 展開した三連複含意オッズを市場プロキシに使用するため、三連複オッズ corpus は必須でない。Kaggle オッズデータは Phase 5 再開時の検証用として失われない。

### 範囲・本格スクレイプ
- **D-06:** 本格スクレイプ（2022-2026/5 全期間、未実行）は **Phase 6 の前に別タスクで実行**（`/gsd-quick` または Phase 4 拡張）。Phase 4 基盤（`run_scrape(live=True)`、`enumerate_races`、`FetcherSession`、レートリミット）をそのまま使用。**Phase 6 は統合ロジックのみを担い、スクレイプ済みデータを入力とする**。Phase 6 の plan は「スクレイプ済みデータ前提」で組む。本格スクレイプ実行を STATE.md の前提タスクとして明記。
- **D-07:** 統合 corpus のデータ範囲は **実データ全部（2015-2026/5）**。Phase 4 D-05 が「2022年1月〜2026年5月末」まで取得する設計なので、取得した分を全部統合。ROADMAP 成功基準#3（2015-2024）からの**拡張**として CONTEXT.md に明記。Phase 9 バックテストは 2015-2026/5 で実行可能（より多くのデータで検証）。2025-2026/5 分の追加は features/backtest のサンプル増として有益。

### Claude's Discretion
- **重複排除の具体的検証ロジック** — 成功基準#1「重複レースなし」を `race_id` で dedup。Kaggle（2015-2021）とスクレイプ（2022-）は元々重複しないはずだが、境界年（2021末↔2022初）での `race_id` 衝突確認。研究・計画エージェントが `race_id` 形式（12桁: YYYYMMDDRRCC）の衝突可能性を精査。
- **統合 corpus 検証の深度** — Phase 2 D-05 の8項目検証のうち統合 corpus に再適用すべきもの（行数・スキーマ同一性・audit・参照整合性・値域 等）と、Phase 1 `audit_leakage()` の再実行タイミングは計画エージェントが決定。
- **Kaggle converter 修正の影響範囲調査** — `(国際)` マッピング削除・dtype 再生成が他のフラグマッピング（FLAG_CROSSWALK の13フラグ）や既存 Phase 2 テストに波及しなか、研究エージェントが精査。
- **feature 再生成のタイミング** — Phase 6 完了後、Phase 7 前に feature 層（Phase 3）を統合 corpus で再生成するかは、Phase 6 スコープ内外を含め計画エージェントが判断（基本は Phase 3 再実行 = 別タスク）。

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Context
- `.planning/PROJECT.md` — プロジェクト概要、3層アーキテクチャ（raw/standard/feature）、データ方針、Key Decisions
- `.planning/REQUIREMENTS.md` — 要件 DATA-05（Phase 6 担当）、Traceability
- `.planning/ROADMAP.md` — Phase 6 定義・成功基準3項目・Phase 2/4 依存関係
- `.planning/STATE.md` — Blockers/Concerns の `(国際)` 乖離調停事項（Phase 6 必須）、Phase 5 DEFERRED ピボット（単勝 Harville プロキシ）

### Specification
- `docs/specification.md` — マスター仕様書。3層データ方針、standard 層テーブル定義、データ優先度マトリクス

### Prior Phase Context（直接依存）
- `.planning/phases/02-kaggle-data-pipeline/02-CONTEXT.md` — **必読**。Kaggle 変換パターン、DTYPE_SPEC、flag 変換、D-05 の8項目検証。D-02 の再生成はこのフェーズの成果物を更新
- `.planning/phases/04-scraping-infrastructure-race-data/04-CONTEXT.md` — **必読**。スクレイプ standard Parquet（`data/standard/scraped/{YYYYMM}/`）、SCHEMA_DTYPE_MAP、`(国際)` 削除済み状態
- `.planning/phases/05-trifecta-odds-scraping/05-CONTEXT.md` — Phase 5 DEFERRED の理由と単勝 Harville プロキシ方針。D-05（オッズ除外）の根拠
- `.planning/phases/01-data-schema-leak-audit/01-CONTEXT.md` — 5テーブルスキーマ定義、pre/post-race 分類、audit 関数
- `.planning/phases/03-feature-engineering/03-CONTEXT.md` — feature 層が `data/standard/{table}.parquet` を読む統合ポイント

### Schema Definitions（正規化先・MUST READ）
- `src/schemas/race.py` — RaceSchema: race_id, race_date, meeting_num, course_code, distance, 20個の race_flag_*。D-01/D-02 の調停対象
- `src/schemas/entry.py` — EntrySchema: horse_race_id, popularity, win_odds（Phase 8 Harville プロキシの入力）
- `src/schemas/result.py` — ResultSchema: finish_position, finish_time, margin 等
- `src/schemas/audit.py` — `audit_leakage()`: 統合 corpus 生成時に post-race カラム混入を検出

### Existing Pipeline（修正・再利用対象）
- `src/pipeline/column_mapping.py` — **D-01 修正対象**: `:68` の `(国際)→graded_stakes` マッピング、`:197` の FLAG_CROSSWALK。D-02 の dtype 調整もここ
- `src/pipeline/kaggle_converter.py` — raw→standard 変換。D-02 の nullable 型再生成で更新。filter→split→transform→write→audit フロー
- `src/pipeline/validators.py` — Phase 2 D-05 の8項目検証。D-02 再検証で再利用
- `src/scraper/normalizer.py` — `SCHEMA_DTYPE_MAP`（nullable 型の参照元）、`write_partitioned_parquet`（read-merge-dedup パターン）。統合マージロジックの参考
- `src/scraper/flag_crosswalk.py` — `(国際)` 削除済み、Phase 6 調停ノート（docstring）が記載。D-01 の参考

### Data Layout（入力・出力）
- `data/standard/race.parquet` / `entry.parquet` / `result.parquet` — Kaggle（2015-2021）。D-02/D-03 の入力かつ出力（上書き）
- `data/standard/scraped/{YYYYMM}/` — スクレイプ（2022-2026/5）。D-03 の入力
- `data/standard/odds_trifecta.parquet` / `payoff.parquet` — D-05 で統合除外（現状維持）
- `data/raw/kaggle/*.csv` — 再生成可能な追跡源

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/pipeline/kaggle_converter.py` — raw→standard 変換の既存フロー。D-02 の再生成で直接更新。filter→split→transform→write→audit パターン
- `src/pipeline/validators.py` — Phase 2 D-05 の8項目検証が実装済み。D-02 再検証と統合 corpus 検証で再利用
- `src/scraper/normalizer.py` `write_partitioned_parquet` — read-merge-dedup on PK（`race_id`/`horse_race_id`）→ 原子 `os.replace`。統合マージ（Kaggle + scraped）の dedup 戦略の直接参考
- `src/schemas/audit.py` `audit_leakage()` — 統合 corpus 生成後に post-race カラム混入を検出
- `src/scraper/normalizer.py` `SCHEMA_DTYPE_MAP` — nullable 型の権威ある定義。D-02 は Kaggle 側をこれに合わせる

### Established Patterns
- Pydantic BaseModel は型定義用、DataFrame レベルで一括処理（Phase 1 D-02）— 数十万行の一括処理
- standard 層はテーブル別単一ファイル Parquet（Phase 2 D-06）— D-04 と一致
- `json_schema_extra={"pre_race": True/False}` でカラムメタデータ駆動分類 — audit で活用
- loguru ログ、pytest テスト。`tests/schemas/`・`tests/pipeline/` に既存テストパターン
- physical-type EQUALITY 検証（Phase 4 P06 `TestSchemaCompatibility`）— D-02 の dtype 統一検証パターン

### Integration Points
- **入力（前提）**: 本格スクレイプ済みの `data/standard/scraped/{YYYYMM}/{race,entry,result}.parquet`（D-06 前提タスク完了後）+ Kaggle `data/standard/{race,entry,result}.parquet`
- **出力**: `data/standard/{race,entry,result}.parquet`（2015-2026/5 統合、D-03 上書き）
- **上流（前提タスク）**: Phase 4 基盤による本格スクレイプ（D-06）
- **下流**: Phase 3 (feature) が統合 corpus を読んで再生成 → Phase 7 (model) → Phase 9 (backtest)。Phase 8 (EV) は `entry.win_odds` から Harville（三連複 corpus 非依存）

</code_context>

<specifics>
## Specific Ideas

- **「Kaggle/スクレイプ起源が区別できない」の検証**: 成功基準#2 の実質的検証は、統合 corpus に `source` 列を**持たない**こと（起源非依存）。dtype・スキーマ・値域が全行で同一であることを物理型比較で確認（Phase 4 P06 の `str(field.type)` 比較パターンを再利用）。
- **`(国際)` 誤分類の規模**: Kaggle `race.parquet` で `graded_stakes=True` 1,348件のうち `(国際)` 由来の誤分類（国際指定だが非重賞の Listed/OP特別戦）が含まれる。D-01 適用後に `graded_stakes=True` 件数が減少し、GI/GII/GIII のみになることを検証で確認。
- **本格スクレイプの時間**: 2022-2026/5（約4.5年、年間約3,000レース ≈ 13,000-14,000レース）× レートリミット1-2秒 = 数時間〜半日規模。Phase 6 前提タスクとして `/gsd-quick` で実行するのが現実的。tqdm 進捗バー（`enumerate_races`・`run_scrape` に実装済み）で進捗可視化。

</specifics>

<deferred>
## Deferred Ideas

- **feature 層の再生成（Phase 3 再実行）** — Phase 6 完了後、Phase 7 前に統合 corpus（2015-2026/5）で feature 層を再生成。別タスク（Phase 3 再実行）。Phase 6 スコープ外。
- **odds_trifecta/payoff の統合** — Phase 5 再開時（前方オッズ収集 or 有料プロバイダ導入）に、Kaggle top-3 を long 化して `payoff` テーブルに統合する作業（Phase 5 D-04 方針）。現状は D-05 で除外。
- **ROADMAP 成功基準#3 の範囲更新（2015-2024 → 2015-2026/5）** — D-07 の決定に合わせ ROADMAP 記載を更新するかは、Phase 9 バックテスト計画時に再調整。CONTEXT.md に拡張の事実を記録。

</deferred>

---

*Phase: 06-Data Integration*
*Context gathered: 2026-06-14*
