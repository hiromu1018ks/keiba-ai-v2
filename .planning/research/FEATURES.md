# Feature Research

**Domain:** JRA三連複EV判定システム (Horse Racing Expected Value Betting System)
**Researched:** 2026-06-10
**Confidence:** HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist in any credible競馬AI/EV system. Missing these = product feels incomplete or untrustworthy.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| 3着内確率予測モデル | 競馬AIの基本機能。LightGBM等で各馬の上位入着確率を出力するのが前提 | MEDIUM | LightGBM二値分類(3着内/外)が主流。特徴量: 競馬場・距離・馬場状態・頭数・枠番・騎手・人気・近走成績・上がり3F等。ROBOTIP、SPAIA、VUMA全てが確率出力を持つ |
| 全通りの三連複オッズ取得 | EV計算にはオッズが不可欠。JRA公式の上位3組だけでは不十分 | MEDIUM | 18頭立て最大C(18,3)=816通り。JRA公式サイトからスクレイピング(robots.txt Disallow空)。note記事でPython実装が公開されている |
| 期待値(EV)計算・足切り | EV=確率xオッズ。これがないと「割安な馬券」が分からない | LOW | 計算自体は単純。重要なのは確率モデルの精度。ROBOTIPは「期待値100未満足切り」設定が標準 |
| 時系列バックテスト | 「この買い目で買っていたらどうなったか」の検証。回収率の信頼性の根拠 | HIGH | ウォークフォワード検証が必須(静的バックテストは過学習の温床)。多くの競馬AI開発者が「バックテスト高ROIの罠」を経験している |
| 回収率・的中率・ドローダウン出力 | バックテスト結果の定量評価。投資判断の基準 | LOW | CSV/CLI出力で十分。回収率100%超え、最大DD、的中率、シャープレシオ等の標準指標 |
| 人気順ベースライン比較 | モデル確率の妥当性確認。「人気通りに買った場合」との比較で改善を測る | LOW | 人気(単勝オッズ順位)は最もシンプルな予測モデル。これに勝てなければMLモデルの価値がない |
| CLI/CSV出力 | 分析ツールとして最低限のI/O | LOW | PROJECT.mdで明示的に指定。pandas DataFrameのto_csvで対応可能 |

### Differentiators (Competitive Advantage)

Features that set this product apart from existing競馬AI services. Most commercial services (SPAIA, VUMA, ROBOTIP) do NOT provide these for三連複 specifically.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| 三連複に特化した確率モデル | 市場の三連複オッズとモデル確率のズレを正確に捉える。単勝確率から三連複確率を独立仮定で計算する簡易手法(Harville)ではなく、3着内確率モデルから直接組み合わせ確率を導出 | HIGH | Harville模型の限界: 高確率馬の順位確率を過大推定する系統的バイアス。Stern(1990)やHenery(1981)の代替モデルも検討可能。本プロジェクトのModel A→Model B→Model Cの3段階アプローチが独自性 |
| 全通り三連複EV計算と点数上限制御 | 18頭立て816通りの全てのEVを計算し、点数上限をかけた上でEV上位のみ抽出する機能 | MEDIUM | ROBOTIPは「期待値100未満足切り」を実装済みだが三連複全通りに特化は稀。本システムの「EVが高い組み合わせのみ抽出」+「点数上限」の組み合わせが独自 |
| ウォークフォワードバックテスト | 時系列を厳密に扱い、未来データのリークを防ぐバックテスト。多くの個人開発者がこれを怠り過学習に陥る | HIGH | 「AUCがある水準を超えるとROIが下がり始める」現象の検出に必須。SimulationEngineとして標準化する開発者が増えている |
| 35年超の長期データパイプライン | 1986年〜のKaggleデータ + 2022年以降の自前収集を共通standard形式で統合 | HIGH | ROBOTIP・SPAIAは独自DB。本システムはKaggle公開データ(472MB)をベースにする点が再現性・検証性で優位。3層(raw/standard/feature)の明確な分離も独自性 |
| 「見送り」判定機能 | EVが基準を満たさないレースは「買わない」ことをシステムが判定する | MEDIUM | PROJECT.mdで「期待値がないレースは見送り」と明記。多くの競馬AIは全レース購入前提だが、本システムは「買わない」ことを積極的な判断とする |
| 確率キャリブレーション | モデル出力確率と実際の的中率の一致を確認・補正する機能 | MEDIUM | LightGBMの生出力は確率として校準されていない場合がある。Platt scalingやIsotonic regression等で補正。商業サービスでは公開されていない内部機能 |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| 自動投票(IPAT連携) | 「完全自動化」の魅力。note記事の競馬AI開発シリーズでも最終ゴールとして扱われる | 自動投票は「分析・検証」のフェーズを飛ばす危険性。バグで誤購入のリスク。JRA IPATの仕様変更リスク。PROJECT.mdでも明示的にOut of Scope | バックテスト完走をMVPとする。自動投票は回収率が安定して100%超を確認してから検討 |
| Web UI / ダッシュボード | 「見やすい画面」への欲求。SPAIA・netkeiba等はリッチなUIを持つ | CLI/CSVで十分な検証フェーズにUI開発は工期を消費するだけ。UI保守コストが発生 | CLI + CSV出力に徹する。matplotlib/pandasによる簡易可視化のみ。UIが必要になった段階で検討 |
| リアルタイム運用 | 「発走直前のオッズ変動に対応したい」という欲求 | 直前オッズの安定取得(スクレイピング)にはSelenium等のブラウザ操作が必要。運用監視体制も必要。MVPの段階で複雑さが桁違いに上がる | バックテストでの確定オッズ使用を優先。リアルタイム運用は「バックテスト完走」後の課題 |
| 全券種対応(単勝・複勝・馬連・三連単...) | 「より多くの馬券で儲けたい」という欲求。note記事のAI開発者も全券種対応を目指す | 三連複に特化することで確率モデルの精度に集中できる。全券種対応は確率計算・オッズ取得の複雑さを倍増させる | 三連複のみに特化。MODEL A(3着内確率)→MODEL C(三連複EV)のパイプラインに集中する |
| 全レースBOX購入 | 「AI上位馬をBOXで買えばいい」という安易な発想 | BOXは点数が爆発し、回収率を圧迫する。三連複3頭BOXでも1点=100円で、18頭から3頭のBOX=816点=81,600円 | EV計算で「割安な組み合わせのみ」を抽出。BOXではなくフォーメーションや流しで点数を絞る |
| 高精度な予測(AUC最大化) | 「予測が当たれば儲かる」という直感 | AUCがある水準を超えるとROIが下がり始める現象が確認されている(YouTube競馬AI#52)。的中率と回収率はトレードオフ | 回収率(ROI)を直接最適化する。的中率ではなく「割安さ」を基準にする |
| 血統・ラップ・調教コメントの初期投入 | 「データが多いほど精度が上がる」という期待 | 特徴量の品質管理・欠損対応・カテゴリ変数の処理が複雑化。初期モデルの収束を遅らせる | raw層には保存するがモデル利用は後段(PROJECT.mdのデータ方針通り)。まずは実績ある基本特徴量で確実に進める |
| SNS・コミュニティ機能 | 「予想を共有したい」という欲求。netkeibaにはコミュニティ要素がある | 個人分析ツールに不要。外部公開はスクレイピング規約違反リスクも | 個人利用のCLIツールに徹する。結果はCSV出力で十分 |

## Feature Dependencies

```
[データパイプライン(raw→standard→feature)]
    └──requires──> [Kaggleデータの理解・変換]
                        └──requires──> [raw・standard・featureの3層定義]

[3着内確率モデル(Model A)]
    └──requires──> [特徴量エンジニアリング]
    └──requires──> [データパイプライン]
    └──requires──> [人気順ベースライン比較]

[全通り三連複オッズ取得]
    └──requires──> [スクレイピング基盤(fetch/parse/normalize)]
                        └──requires──> [2022年以降データ収集]

[三連複EV計算(Model C)]
    └──requires──> [3着内確率モデル(Model A)]
    └──requires──> [全通り三連複オッズ取得]
    └──requires──> [確率→組み合わせ確率変換]

[EV足切り・買い目抽出]
    └──requires──> [三連複EV計算(Model C)]
    └──requires──> [点数上限設定]

[ウォークフォワードバックテスト]
    └──requires──> [EV足切り・買い目抽出]
    └──requires──> [時系列データ全体]
    └──requires──> [回収率・的中率・ドローダウン計算]

[確率キャリブレーション]
    └──enhances──> [3着内確率モデル(Model A)]
    └──enhances──> [三連複EV計算(Model C)]

[「見送り」判定]
    └──enhances──> [EV足切り・買い目抽出]

[全券種対応] ──conflicts──> [三連複特化の確率モデル精度]
[自動投票] ──conflicts──> [バックテスト検証フェーズ]
[リアルタイム運用] ──conflicts──> [CLI/CSVベースのシンプル設計]
```

### Dependency Notes

- **3着内確率モデル requires データパイプライン:** Model Aはfeature層のデータに依存する。feature層はstandard層から生成され、standard層はraw層から変換される。この3層が揃わないとモデル学習が始まらない
- **三連複EV計算 requires 3着内確率モデル AND 全通りオッズ:** EV = P(組み合わせ的中) x Odds。P(組み合わせ的中)は各馬の3着内確率から導出し、Oddsは全通り取得した三連複オッズを使用。この2つが揃って初めてEV計算が可能
- **ウォークフォワードバックテスト requires EV足切り:** バックテストは「EVが高い買い目だけを買ったらどうなったか」を検証するもの。買い目抽出ロジック(EV足切り)が確定していないとバックテストの意味がない
- **確率キャリブレーション enhances Model A/C:** キャリブレーションは確率の信頼性を高め、EV計算の精度を向上させる。MVPには不要だが、回収率安定化に直結する
- **全券種対応 conflicts 三連複特化:** 三連複に特化することで、3着内確率という明確な目的変数に集中できる。単勝(1着確率)や複勝(3着内確率と同じ)など券種ごとに最適なモデルが異なり、対応券種を増やすと各券種の精度が分散する
- **自動投票 conflicts バックテスト検証フェーズ:** バックテストで回収率100%超えを確認する前に自動投票を実装すると、「検証されていないロジックで実際の金を動かす」危険状態になる

## MVP Definition

### Launch With (v1)

Minimum viable product -- バックテスト完走が目標。「この買い目を買っていたらどうなったか」を検証できる状態。

- [ ] **Kaggleデータ(raw)の理解・standard形式変換** -- 全ての基盤。データが読めないと何も始まらない
- [ ] **3層データパイプライン(raw/standard/feature)** -- 学習・予測のデータ基盤
- [ ] **LightGBM 3着内確率モデル(Model A)** -- EV計算の核心。人気順ベースラインに勝つことが最初の目標
- [ ] **全通り三連複オッズ取得(確定オッズ)** -- バックテスト用。スクレイピング基盤の最初の成果物
- [ ] **三連複組み合わせ生成 + EV計算** -- Model Aの確率とオッズからEVを算出
- [ ] **EV足切り + 点数上限** -- 「割安な買い目」の抽出
- [ ] **時系列バックテスト(回収率・的中率・ドローダウン)** -- MVPのゴール。CLI/CSV出力

### Add After Validation (v1.x)

バックテストで回収率100%超えを確認した後に追加検討する機能。

- [ ] **確率キャリブレーション** -- Model Aの確率と実際の的中率のズレを補正。バックテスト結果を見てから判断
- [ ] **2022年以降データのスクレイピング収集** -- Kaggle期間(〜2021年7月)以降のデータ拡充。Kaggleデータだけでバックテストが完走すれば追加
- [ ] **Kaggle期間と自前収集期間の結合** -- standard形式での共通化。データ期間延長でモデル精度向上を狙う
- [ ] **「見送り」判定の閾値最適化** -- バックテスト結果に基づき、どのEV閾値で見送るかをデータ駆動で決定
- [ ] **Model B(割安馬判定)の導入** -- Model Aだけでは捉えきれない「市場の過小評価」パターンの抽出

### Future Consideration (v2+)

プロダクトマーケットフィット確認後の検討事項。

- [ ] **血統・ラップ・調教コメントの特徴量追加** -- raw保存はv1で実施。モデル投入は精度頭打ち後に検討
- [ ] **Henery/Sternモデルによる組み合わせ確率の改善** -- Harville模型の系統的バイアス(高確率馬の順位過大推定)への対応
- [ ] **リアルタイム直前オッズ取得** -- バックテスト完走後、発走前のオッズ変動対応
- [ ] **ケリー基準による資金管理** -- 最適ベットサイズの算出。ハーフケリーでDD抑制
- [ ] **他券種への展開検討** -- 三連複で安定回収を確認後の拡張

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Kaggleデータ理解・standard変換 | HIGH | MEDIUM | P1 |
| 3層データパイプライン | HIGH | HIGH | P1 |
| LightGBM 3着内確率モデル | HIGH | HIGH | P1 |
| 全通り三連複オッズ取得 | HIGH | MEDIUM | P1 |
| 三連複EV計算 | HIGH | MEDIUM | P1 |
| EV足切り + 点数上限 | HIGH | LOW | P1 |
| 時系列バックテスト | HIGH | HIGH | P1 |
| 人気順ベースライン比較 | HIGH | LOW | P1 |
| CLI/CSV出力 | HIGH | LOW | P1 |
| 確率キャリブレーション | MEDIUM | MEDIUM | P2 |
| 2022年以降スクレイピング | MEDIUM | MEDIUM | P2 |
| 「見送り」判定閾値最適化 | MEDIUM | LOW | P2 |
| Model B(割安馬判定) | MEDIUM | MEDIUM | P2 |
| 血統・ラップ特徴量追加 | LOW | HIGH | P3 |
| Henery/Stern確率モデル | MEDIUM | HIGH | P3 |
| リアルタイムオッズ取得 | MEDIUM | HIGH | P3 |
| ケリー基準資金管理 | LOW | MEDIUM | P3 |
| 自動投票 | LOW | HIGH | P3 |
| Web UI | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have for launch (バックテスト完走 = MVP)
- P2: Should have, add when possible (精度改善・データ拡充)
- P3: Nice to have, future consideration (運用自動化・UI)

## Competitor Feature Analysis

| Feature | ROBOTIP Super (ウマニティ) | SPAIA競馬 | VUMA | netkeiba UMAI | 本プロジェクト |
|---------|--------------------------|-----------|------|---------------|---------------|
| 確率モデル | U指数ベース(6能力指数x5適性) | KAIBAエンジン(18種AI) | Heneryモデル順位確率 | ユーザー選択特徴量で即時生成 | LightGBM 3着内確率 |
| 期待値計算 | あり(期待値100未満足切り) | あり(期待値順位表示) | 不明(的中率重視) | 不明 | 全通り三連複EV計算 |
| 三連複対応 | あり(予算3000円/レース) | あり | 主軸(ワイド3点+三連複10点) | あり | 三連複のみに特化 |
| 全通りオッズ | 不明(内部計算) | 不明 | 不明 | 不明 | 全通りスクレイピング取得 |
| バックテスト | シミュレーション機能あり | 実績公開のみ | 実績公開のみ | ROIランキング公開 | ウォークフォワード時系列検証 |
| 自動投票 | あり(IPAT連携) | なし | なし | なし | なし(Out of Scope) |
| 料金 | 有料(月額) | 有料(月額) | 有料(月額) | 一部無料/マスターコース有料 | 個人開発(無料) |
| データ期間 | 不明(独自DB) | 過去数十年 | 不明 | 不明 | 1986年〜(Kaggle+自前) |
| UI | Web+アプリ | Web+アプリ | Web+アプリ(スポーツナビ) | Web+アプリ | CLI/CSV |

## Sources

- [note: 競馬AIがついに完成！機械学習による予測から自動投票まで](https://note.com/dijzpeb/n/n4b1dca201cc9) -- 競馬AI開発シリーズ。特徴量作成→確率予測→EV計算→自動投票の全体構成を解説。信頼性: HIGH
- [ウマニティ ROBOTIPスーパー](https://umanity.jp/robotip_super/about.php) -- 期待値100未満足切り、三連複買い目プラン、U指数ベース予想エンジン。信頼性: HIGH
- [SPAIA競馬 料金プラン](https://info.spaia-keiba.com/) -- AI予想家18種、回収率実績公開。信頼性: HIGH
- [VUMA AI競馬とは](https://vuma.ai/about) -- 的中率重視型、ワイド3点+三連複10点。信頼性: HIGH
- [note: 競馬AI指数の裏側―国内主要6サービス徹底比較](https://note.com/gaisenmontaro/n/n493992f5611a) -- netkeiba UMAI、JRA-VAN、競馬ブック、シュウ等の比較。信頼性: HIGH
- [Zenn: 機械学習による競馬予想で安定して勝てるのか](https://zenn.dev/nyanyanyanyanya/articles/ff16a824566376) -- 三連複BOXでの回収率検証。信頼性: MEDIUM
- [YouTube: 予測精度を上げたのに回収率が下がる…競馬AIの落とし穴](https://www.youtube.com/watch?v=hD0zdd8eL1U) -- AUC向上がROI低下を招く現象。ウォークフォワード検証の重要性。信頼性: MEDIUM
- [Zenn: 競馬AI開発記録#15 バックテストの異常な高ROIを疑う](https://zenn.dev/ricotiler/articles/keiba-ai-15-pit-generation-leak-prevention) -- ウォークフォワードシミュレーション標準化。データリーク防止。信頼性: MEDIUM
- [Sazanami-AI](https://astroripple.com/) -- 回収率重視の競馬予想AI。勝率・期待値リアルタイム予測。信頼性: MEDIUM
- [netkeiba AI機能](https://support.keiba.netkeiba.com/hc/ja/sections/42138938502809) -- AIアドバイザー・AI展開予想・AIレース相性度。信頼性: HIGH
- [法政大学: 機械学習による競馬予想](https://syslab.k.hosei.ac.jp/abst/2023-MN-RM.pdf) -- LightGBM 3着内予測。学術論文。信頼性: HIGH
- [Ali et al.: Probability Models on Horse-Race Outcomes](https://www.stat.berkeley.edu/~aldous/157/Papers/ali.pdf) -- Harvilleモデルの限界と代替モデルの学術的検討。信頼性: HIGH
- [Benter: Computer Based Horse Race Handicapping](https://datagolf.com/static/blogs/benter_paper.pdf) -- 競馬予測システムの古典的参考文献。信頼性: HIGH
- [競馬AI開発にありがちな間違い](https://keibasys.seesaa.net/article/493406221.html) -- データリーク・過学習の警告。信頼性: MEDIUM
- [note: 競馬AIで「回収率150%」はなぜ嘘なのか](https://note.com/project_sei/n/n419115d82214) -- バックテスト高ROIの罠。信頼性: MEDIUM

---
*Feature research for: JRA三連複EV判定システム*
*Researched: 2026-06-10*
