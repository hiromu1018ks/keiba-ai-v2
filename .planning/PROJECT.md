# 競馬AI 三連複EVシステム

## What This Is

JRA中央競馬を対象に、三連複で期待値の高い買い目を抽出するEV判定システム。各馬の3着内確率を推定し、市場オッズとのズレから割安な三連複組み合わせを見つけ出す。Mac環境・Pythonで構築するCLI/CSVベースのシステム。

## Core Value

推定的中確率に対してオッズが高い三連複を特定し、バックテストで回収率を検証できること。当たる馬券を探すのではなく、割安な馬券を探す。

## Requirements

### Validated

- [x] Kaggleデータの5テーブル（race/entry/result/odds_trifecta/payoff）のPydanticスキーマが定義済み（91フィールド、pre/post-raceメタデータ付き） — Validated in Phase 1: Data Schema & Leak Audit
- [x] データリーク監査関数が実装済み（post-raceカラムの自動検出、DataFrameとの照合） — Validated in Phase 1: Data Schema & Leak Audit
- [x] 66カラムのKaggle分類網羅性が機械的に検証済み — Validated in Phase 1: Data Schema & Leak Audit
- [x] Kaggleデータ（2015〜2021年）を5テーブル（race/entry/result/odds_trifecta/payoff）のParquetに変換、140テスト全通過 — Validated in Phase 2: Kaggle Data Pipeline
- [x] 8項目のデータ品質バリデーションが実装済み（行数・スキーマ・日付範囲・障害除外・参照整合性等） — Validated in Phase 2: Kaggle Data Pipeline
- [x] 2022年以降のJRAレース・出走データをスクレイピングで収集しstandard Parquetに変換（2022-2024、Kaggleと同一スキーマ） — Validated in Phase 4: Scraping Infrastructure & Race Data
- [x] スクレイピングパイプライン（fetch/parse/normalize分離、raw HTML先保存、重複取得回避、レートリミット強制）実装 — Validated in Phase 4 (SCRP-01/02/03/05、8 plans、UAT gap-closure + ライブ検証完了)
- [x] Kaggle（2015-2021）とスクレイプ（2021-08..2026-05、58ヶ月）を統合した単一 corpus（race 38,009 / entry=result 534,953 行、2015-01-04..2026-05-31、重複0・スキーマ同一・PK-set union 3テーブル・odds/payoff 不変）— Validated in Phase 6: Data Integration (DATA-05; 独立直接検証で3/3 success criteria PASS。feature_generator 再生成は Phase 3 繰越、ROADMAP 2015-2024→2015-2026/5 表記は Phase 9 繰越 per D-07)
- [x] LightGBM Model A（3着内確率）が構築済み（GroupTimeSeriesSplit race-grouped時系列CV + Isotonicキャリブレーション、holdout AUC=0.7669 / ECE=0.0062、2018-2024 train・2025-01〜2026-05 holdout、164 trees/69 features、リーク防止構造的保証）— Validated in Phase 7: Model A Top-3 Probability (MODA-01/02/04; 4/4 success criteria PASS・verify passed)
- [x] 人気順ベースラインとの比較で確率の妥当性を確認（baseline AUC=0.8100 vs 純粋特性モデル 0.7669、D-08想定通り・参考情報・ベースライン超えは非必須ゲート）— Validated in Phase 7 (MODA-03)

### Active

- [ ] Kaggleデータ（1986〜2014年）のstandard層変換（現状は2015年以降のみ対応）
- [ ] raw・standard・featureの3層データパイプラインが構築されていること
- [ ] 全通りの三連複オッズを取得できること
- [ ] 候補馬から三連複の組み合わせを生成しEVを計算できること
- [ ] EVが高い買い目だけを抽出し、点数上限をかけられること
- [ ] 時系列バックテストで回収率・的中率・ドローダウン等を検証できること
- [ ] バックテスト結果をCLI・CSVで出力できること

### Out of Scope

- 自動投票 — 初期は分析・検証のみ
- Web UI — CLI/CSV出力で十分
- リアルタイム運用 — まずはバックテスト完走が目標
- 血統・ラップ・調教コメントの初期モデル投入 — raw保存はするがモデル利用は後段
- JRA以外の競馬（地方・海外）— JRA中央競馬のみ対象

## Context

- **既存データ**: `data/raw/kaggle/` に4ファイル存在
  - `19860105-20210731_race_result.csv` (472MB) — レース結果・出走馬情報・着順・人気・単勝オッズ・騎手・調教師・馬体重・上がり・通過順 等
  - `19860105-20210731_odds.csv` (22MB) — 各券種オッズ（三連複上位3組のオッズ・組み合わせ含む）
  - `19860105-20210731_laptime.csv` (14MB) — ラップタイム
  - `20020615-20210731_corner_passing_order.csv` (8.6MB) — 通過順位
- **データ方針**: 「データは広く保存し、モデル利用は狭く始める」— 取得できるものはrawに保存、standard化とfeature化は三連複EV検証に必要なものから段階的に
- **3層アーキテクチャ**: raw層（取得元に近い形で保存）→ standard層（Kaggle/自前を共通形式に統一）→ feature層（モデル投入用特徴量）
- **モデル3段階**: Model A（3着内確率）→ Model B（割安馬判定）→ Model C（三連複EV判定）
- **初期モデル特徴量**: 競馬場・距離・芝ダート・馬場状態・頭数・枠番・馬番・斤量・騎手・調教師・人気・単勝オッズ・近走成績・上がり3F・通過順
- **買い目方針**: EVが高い組み合わせのみ抽出。AI上位BOX・全レース購入・人気馬のみの低配当は避ける。期待値がないレースは見送り
- **スクレイピング方針**: fetch/parse/normalize/featureを分離。HTML保存必須。重複取得回避。大量並列なし。外部公開なし

## Constraints

- **環境**: Mac単体で完結するシステム
- **言語**: Python
- **ML**: LightGBM固定で開始（まず確実に進める）
- **データ期間**: 1986年〜2021年7月（Kaggle）、2022年以降（自前スクレイピング）
- **対象券種**: 三連複のみ
- **三連複オッズ**: 全通りのオッズが必要（Kaggleは上位3組のみ）。2022年以降のスクレイピングで全通り取得する方針

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| LightGBM固定で開始 | 表形式データに強く、学習速度も速い。最初は確実に進めるため | — Pending |
| 全通り三連オッズ取得 | 正確なEV計算には全通りのオッズが必要。上位3組だけでは不十分 | — Pending |
| CLI/CSV出力 | バックテスト検証がMVP。UIは不要 | — Pending |
| 3層データ分離 (raw/standard/feature) | 取得・保存・利用を明確に分離。段階的にモデル精度を上げる基盤 | — Pending |
| MVP = バックテスト完走 | 「この買い目を買っていたらどうなったか」を検証できる状態が最初の目標 | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-16 after Phase 7 completion (Model A top-3 probability, MODA-01/02/03/04, holdout AUC 0.7669 / ECE 0.0062)*
