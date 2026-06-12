# Phase 4: Scraping Infrastructure & Race Data - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-13
**Phase:** 04-Scraping Infrastructure & Race Data
**Areas discussed:** スクレイピング先, レース一覧取得, HTML保存設計, スキーマギャップ対応

---

## スクレイピング先

### スクレイピング先サイト

| Option | Description | Selected |
|--------|-------------|----------|
| netkeiba中心 | 競馬ML界隈で最も使われるデータソース。HTML構造が比較的安定。Zenn/note記事で実績多数 | ✓ |
| JRA公式中心 | 公式ソースで信頼性が高いが、JavaScript重いページが多くPlaywright必須。データ制限あり | |
| 両方併用 | メインはnetkeiba、取得不能フィールドはJRA公式で補完。完全性は最も高いが実装複雑 | |

**User's choice:** netkeiba中心
**Notes:** specification.md §3 に「netkeiba等」と記載あり。Kaggleデータの元ソースであることを確認。

### 取得ページタイプ

| Option | Description | Selected |
|--------|-------------|----------|
| 結果ページのみ | /race/result/ のみ。着順・タイム・上がり・通過順・オッズ等が揃う | |
| 結果＋出馬表 | 結果＋/race/shutuba/。事前情報がより詳しい | |
| 広く取得 | 結果＋出馬表＋馬プロフィール等。raw保存は広くする方針に合う | |

**User's choice:** 「特徴量で利用する情報はすべて取得できるように」（自由入力）
**Notes:** Phase 3の全特徴量が結果ページのみでカバー可能であることを確認。ただし将来の拡張（血統等）も視野に入れる。

### ページ取得方法

| Option | Description | Selected |
|--------|-------------|----------|
| httpx + BS4 | 静的HTMLとして取得。CLAUDE.md推奨パターン | |
| Playwright | JavaScript レンダリング込みで確実に取得 | ✓ |
| httpx + Playwright fallback | まずhttpxで試し、失敗時Playwright | |

**User's choice:** Playwrightで取得
**Notes:** httpxではなく最初からPlaywrightを使用。

### データ抽出方法

| Option | Description | Selected |
|--------|-------------|----------|
| BS4+lxml で parse | Playwright取得→HTML保存→BS4+lxmlでparse。specification.md §13の分離方針に合う | ✓ |
| Playwright内で直接抽出 | Playwright上でDOM操作してデータ抽出。速いが分離が弱まる | |

**User's choice:** BS4+lxml で parse
**Notes:** specification.md §13「取得と解析を分ける」方針を遵守。

---

## レース一覧取得

### レース列挙方法

| Option | Description | Selected |
|--------|-------------|----------|
| カレンダー/開催一覧から | netkeibaのカレンダーページから月ごとの開催日を取得→各レースのURL。確実に実在レースのみ取得 | ✓ |
| race_id推測生成 | Kaggleと同じrace_id形式でID生成し存在チェック。実装単純だが大量の無効アクセス発生 | |
| 年→開催回→レースの階層走査 | より確実だがnetkeibaの階層構造に依存 | |

**User's choice:** カレンダー/開催一覧から
**Notes:** 「1で確実に」。データ期間は2022年1月〜2026年5月31日まで（ROADMAPの2022-2024から拡張）。

### カレンダーベースの具体的アプローチ

| Option | Description | Selected |
|--------|-------------|----------|
| 月→開催日→レース | カレンダーページ→月ごとの開催日→各レース結果URL。3段階で確実 | ✓ |
| JRA公式のスケジュール | JRA開催スケジュールから直接。Playwright必須の場合が多い | |
| 土日＋祝日の日付生成 | 決め打ちで日付生成。場外発売日の見落としリスク | |

**User's choice:** 月→開催日→レース
**Notes:** netkeibaのURLパターン `https://db.netkeiba.com/race/calendar/{YYYYMM}/` を使用。

---

## HTML保存設計

### ディレクトリ構造

| Option | Description | Selected |
|--------|-------------|----------|
| 年/月階層 | data/raw/netkeiba/2022/01/race_result_XXX.html。探しやすく重複判定も直感的 | ✓ |
| フラット構造 | 同一ディレクトリに全ファイル。シンプルだが数千ファイルで探しにくい | |
| 競馬場別階層 | 競馬場ごとに分ける。分析には便利だが日付検索性が低下 | |

**User's choice:** 年/月階層

### ファイル名規約

| Option | Description | Selected |
|--------|-------------|----------|
| race_idベース | 202206010101.html。standard層との対応が明確。重複判定も確実 | ✓ |
| URLパスベース | URLのパス部分をそのままファイル名に。URL変更時にリスク | |
| URLハッシュベース | URLのハッシュ値。確実だがファイル名から内容が分からない | |

**User's choice:** race_idベース

---

## スキーマギャップ対応

### ギャップの有無（初期前提の修正）

初期分析では「20個のrace_flag等が取得困難」と判断したが、ユーザーの指摘「Kaggleはnetkeiba由来データだぞ？」を受けてPlaywrightで実調査を実施。

**Playwright調査結果:**
- レース `202206010101`（3歳未勝利）と `202206010111`（中山金杯GIII）を確認
- レース条件テキスト: `4歳以上オープン (国際)(特指)(ハンデ)` からrace_flag導出可能
- meeting_num: `1回中山` から取得可能
- region: 調教師列 `[東] 相沢郁` から取得可能
- prize_money: 賞金列 `520.0` から取得可能
- **結論: ギャップなし、全フィールド取得可能**

| Option | Description | Selected |
|--------|-------------|----------|
| ギャップなし、全取得可能 | Playwright実調査で全フィールドの取得可能性を確認 | ✓ |
| さらに確認 | 追加調査が必要 | |

**User's choice:** ギャップなし、全取得可能
**Notes:** ユーザーの指摘が正しかった。Kaggleデータはnetkeiba由来であるため、当然全フィールドが揃う。

---

## Claude's Discretion

以下はClaudeの裁量で実装方針を決定:
- レース条件テキストからrace_flagへの正規表現パターン定義
- netkeiba HTMLのDOM構造に基づくBS4パースロジック
- レート制限の具体的な間隔（1-2秒）
- エラーハンドリングの詳細（リトライ・スキップ・ログ）
- 出走取消・競走中止等の特殊ケース対応

## Deferred Ideas

None — discussion stayed within phase scope.
