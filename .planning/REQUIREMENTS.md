# Requirements: 競馬AI 三連複EVシステム

**Defined:** 2026-06-10
**Core Value:** 推定的中確率に対してオッズが高い三連複を特定し、バックテストで回収率を検証できること

## v1 Requirements

### Data Pipeline

- [x] **DATA-01**: raw/standard/featureの3層スキーマを定義し、保存形式・カラム名・データ型を文書化できること
- [x] **DATA-02**: Kaggleデータ（1986-2021）をstandard形式に変換し、Parquetで出力できること
- [x] **DATA-03**: standardデータからfeature層の基本特徴量（競馬場・距離・芝ダート・馬場状態・頭数・枠番・馬番・斤量・騎手・調教師・人気・単勝オッズ・近走成績・上がり3F・通過順）を生成できること
- [x] **DATA-04**: データリーク防止のため、事前/事後カラムの監査機構があり、レース後に確定する情報が特徴量に混入しないことを検証できること
- [x] **DATA-05**: 2015-2024年のデータ（Kaggle + 自前収集）を共通standard形式でParquet出力し、統合して扱えること

### Scraping

- [x] **SCRP-01**: fetch/parse/normalize/featureの処理を分離したスクレイピング基盤を構築できること
- [x] **SCRP-02**: 2022年以降のJRAレース結果・出走馬情報のHTMLを取得しraw保存できること
- [x] **SCRP-03**: 保存済みHTMLから必要情報を抽出し、standard形式に変換できること
- [ ] **SCRP-04**: 全通りの三連複オッズ（最大816通り）を取得し、レースID・組み合わせ・オッズの形式で保存できること
- [x] **SCRP-05**: 同一ページの重複取得を回避し、既存HTMLキャッシュを活用できること

### Model A — 3着内確率

- [x] **MODA-01**: LightGBMによる3着内確率モデルを構築し、各馬のp_top3を出力できること
- [x] **MODA-02**: TimeSeriesSplitによる時系列CVで学習/検証を分離し、未来データのリークを防ぐこと
- [x] **MODA-03**: 人気順ベースライン（単勝オッズ順位）との比較でモデル確率の優位性を確認できること
- [x] **MODA-04**: OOF（Out-of-Fold）予測による確率キャリブレーションを実装し、推定確率と実際の的中率の一致を確認できること

### EV Calculation — 三連複EV判定

- [ ] **EVCALC-01**: Harville条件付き確率により、各馬のp_top3から三連複組み合わせ確率を計算できること
- [ ] **EVCALC-02**: EV = 推定的中確率 × 三連複オッズを全組み合わせについて計算できること
- [ ] **EVCALC-03**: EV閾値による足切りで、割安な買い目のみを抽出できること
- [ ] **EVCALC-04**: EV基準を満たさないレースを「見送り」と判定できること
- [ ] **EVCALC-05**: 点数上限を設定し、買い目数を制御できること

### Backtesting

- [ ] **BKTS-01**: ウォークフォワードバックテストエンジンにより、時系列を厳守した過去検証を実行できること
- [ ] **BKTS-02**: 回収率・的中率・総投資額・総払戻額・純利益・最大ドローダウンを計算・出力できること
- [ ] **BKTS-03**: 月別・オッズ帯別・EV帯別・レース条件別の成績を詳細分析できること
- [ ] **BKTS-04**: 確定オッズと発走時オッズの差異を考慮した現実的な検証ができること

### Output

- [ ] **OUTP-01**: ClickベースのCLIインターフェースで各操作（データ変換・学習・予測・バックテスト）を実行できること
- [ ] **OUTP-02**: バックテスト結果をCSVで出力できること
- [ ] **OUTP-03**: 買い目候補をCSVで出力できること

## v2 Requirements

### Extended Features

- **EXTF-01**: 血統適性特徴量の生成とモデルへの追加
- **EXTF-02**: ラップ適性特徴量の生成とモデルへの追加
- **EXTF-03**: 馬場含水率・クッション値特徴量の追加
- **EXTF-04**: 直前オッズ推移のログ保存と特徴量化
- **EXTF-05**: 調教評価・厩舎コメント解析特徴量の追加

### Advanced Models

- **ADVM-01**: Stern/Heneryモデルによる三連複確率の高精度計算
- **ADVM-02**: EV重み付け学習（ROI直接最適化）
- **ADVM-03**: 複数モデル比較（XGBoost・CatBoost等）

### Real-time Operation

- **RTOP-01**: 当週出馬表の取り込みと買い目候補出力
- **RTOP-02**: 当週オッズのリアルタイム反映
- **RTOP-03**: レース後の結果自動保存と成績更新

## Out of Scope

| Feature | Reason |
|---------|--------|
| 自動投票（IPAT連携） | 分析・検証フェーズが未完了。バグによる誤購入リスク。回収率安定後に検討 |
| Web UI / ダッシュボード | CLI/CSVで検証段階は十分。UI開発は工期を消費するだけ |
| 全券種対応（単勝・複勝・馬連・三連単等） | 三連複に特化することで確率モデル精度に集中。全券種は複雑さを倍増 |
| SNS・コミュニティ機能 | 個人分析ツールに不要。外部公開はスクレイピング規約違反リスク |
| JRA以外の競馬（地方・海外） | データ形式・ルールが異なり、対応コストが高い |
| 1986-2014年のデータ統合 | 直近10年（2015-2024）に絞り込むことで精度確保とデータ品質管理を両立 |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DATA-01 | Phase 1 | Complete |
| DATA-02 | Phase 2 | Complete |
| DATA-03 | Phase 3 | Complete |
| DATA-04 | Phase 1 | Complete |
| DATA-05 | Phase 6 | Complete |
| SCRP-01 | Phase 4 | Complete |
| SCRP-02 | Phase 4 | Complete |
| SCRP-03 | Phase 4 | Complete |
| SCRP-04 | Phase 5 | Pending |
| SCRP-05 | Phase 4 | Complete |
| MODA-01 | Phase 7 | Complete |
| MODA-02 | Phase 7 | Complete |
| MODA-03 | Phase 7 | Complete |
| MODA-04 | Phase 7 | Complete |
| EVCALC-01 | Phase 8 | Pending |
| EVCALC-02 | Phase 8 | Pending |
| EVCALC-03 | Phase 8 | Pending |
| EVCALC-04 | Phase 8 | Pending |
| EVCALC-05 | Phase 8 | Pending |
| BKTS-01 | Phase 9 | Pending |
| BKTS-02 | Phase 9 | Pending |
| BKTS-03 | Phase 9 | Pending |
| BKTS-04 | Phase 9 | Pending |
| OUTP-01 | Phase 10 | Pending |
| OUTP-02 | Phase 10 | Pending |
| OUTP-03 | Phase 10 | Pending |

**Coverage:**

- v1 requirements: 26 total
- Mapped to phases: 26
- Unmapped: 0

---
*Requirements defined: 2026-06-10*
*Last updated: 2026-06-11 after roadmap creation*
