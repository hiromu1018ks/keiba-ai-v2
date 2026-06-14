---
phase: 04-scraping-infrastructure-race-data
verified: 2026-06-14T14:45:00Z
status: human_needed
score: 7/8 must-haves verified
overrides_applied: 0
human_verification:
  - test: "run_scrape(live=True) で実際の netkeiba から小範囲（例: 2023-06-25 宝塚記念開催日、max_races=3）をスクレイプし、data/standard/scraped/{YYYYMM}/{race,entry,result}.parquet が非零ロードで生成されることを確認する"
    expected: "race/entry/result の3 Parquet が data/standard/scraped/202306/ に生成され、race 行数 >0、entry/result 行数 >0。raw HTML も data/raw/netkeiba/2023/06/ に保存される。UAT-Test-6 修正後の /race/list/{YYYYMM}/ URL 形式が実際のサイトで開催日リンクを返すことを実証する。"
    why_human: "実ネットワークアクセスとライブ netkeiba サイト構造が必要。フィクスチャベースのテストと合成 golden calendar (calendar_202306.html) はパーサ形状を検証するが、実際のURL形式 /race/list/{YYYYMM}/ が開催日リンクを返すことは実証済み（プラン04-08調査プローブ）のものの、本環境では再確認できない。"
---

# Phase 4: Scraping Infrastructure & Race Data — Verification Report

**Phase Goal:** 2022-2024 JRA race results and entry information are scraped and available in standard Parquet, extending the dataset beyond Kaggle's 2021 cutoff
**Verified:** 2026-06-14T14:45:00Z
**Status:** human_needed
**Re-verification:** No — initial verification (gap-closure plans 04-07/04-08 已適用済み、04-REVIEW.md / 04-REVIEW-FIX.md 已処理済みの状態で実施)

## Goal Achievement

### Observable Truths

ROADMAP の 4 成功基準 + UAT-Test-3/UAT-Test-6 ギャップ解消 + フェーズ目標の達成可能性、を合成した 8 truth で評価した。

| #   | Truth | Status     | Evidence |
| --- | ----- | ---------- | -------- |
| 1   | SC-1: fetch/parse/normalize が分離され、raw HTML がパース前に保存される | ✓ VERIFIED | `src/scraper/fetcher.py` が raw HTML を `data/raw/netkeiba/{YYYY}/{MM}/{race_id}.html` へ atomic 書き込み (`os.replace`, line 340) した後に `src/scraper/parser.py:parse_race_html` がファイルパスから読み取る。orchestrator は enumerate→fetch→parse→normalize の4段階を明示的に接続 (`src/scraper/orchestrator.py:130-160`)。モジュール分離はディレクトリ構造と `__init__.py` の再エクスポートで確認。 |
| 2   | SC-2: 2022-2024 レース・出走データが Kaggle と同一スキーマの standard Parquet に変換される | ⚠ VERIFIED (pipeline) / HUMAN (live data) | パイプライン機能は VERIFIED: `tests/scraper/test_end_to_end.py::TestSchemaCompatibility` (13 passed) が Arrow 物理型一致性を検証。5 つの golden fixture が正しくパースされることを行動的に確認（宝塚記念=GI/17頭、ヒヤシンスS=L/11頭、他3件 None）。一方「実際の2022-2024データが Parquet に存在すること」は LIVE RUN が必要なため human にルーティング。 |
| 3   | SC-3: 重複ページ取得が防止される（既存HTML再利用） | ✓ VERIFIED | `src/scraper/fetcher.py:302-306` で `out_path.exists() and out_path.stat().st_size > 0` を満たす既存ファイルを再フェッチせずリターン（SCRP-05）。`tests/scraper/test_fetcher.py` でdedupの単体テストあり。 |
| 4   | SC-4: レートリミットが強制されアンチボット回避 | ✓ VERIFIED | `src/scraper/fetcher.py:59` `RATE_LIMIT_SECONDS = 2.0`、`FetcherSession.fetch` の `finally:` ブロック (line 184-188) で成功・エラー両パスに `time.sleep` 適用。`fetch_with_retry` は指数バックオフ (line 203-213)。 |
| 5   | UAT-Test-3 FIXED: `(国際)` 国際指定マーカーで非重賞レースが `race_flag_graded_stakes=True` にならない | ✓ VERIFIED | `src/scraper/flag_crosswalk.py` の `FLAG_CROSSWALK` から `("(国際)", "race_flag_graded_stakes")` 行が削除済み（line 86-87 コメントで意図的削除を明記）。行動確認: `derive_race_flags('4歳以上オープン (国際)(特指)(ハンデ)')['race_flag_graded_stakes'] == None`、`derive_race_flags('3歳オープン', race_name='宝塚記念(GI)')['race_flag_graded_stakes'] == True`（GRADE_REGEX は健在）。回帰テスト `test_international_does_not_set_graded_stakes` + `test_flag_crosswalk_applied_on_graded_fixture` が PASS。 |
| 6   | UAT-Test-6 FIXED: `run_scrape(live=True)` が実netkeibaから2022-2024レースを列挙できる（月カレンダーURLが開催日リンクを返す） | ✓ VERIFIED (URL form) / HUMAN (live enumeration) | URL形式は VERIFIED: `src/scraper/enumeration.py:206` が `urljoin(BASE_URL, f'/race/list/{year}{month:02d}/')` を生成（旧 `/race/calendar/` から変更）。行動確認: `enumerate_race_day_urls(2023, 6, fake)` が `https://db.netkeiba.com/race/list/202306/` をキャプチャ。回帰テスト `TestEnumerateRaceDayUrlsUrlContract` + golden fixture テスト `TestParseCalendarMonthHtmlGolden` が PASS。ただし `tests/scraper/fixtures/html/calendar_202306.html` は **SYNTHETIC**（冒頭コメント明記: "constructed from verified live probe data"）。実際のライブサイトで `/race/list/{YYYYMM}/` が開催日リンクを返すことは本環境では再確認不可 → human。 |
| 7   | CR-01 FIXED: `GRADE_PATTERNS` が `__all__` に存在するが未定義（ImportError） | ✓ VERIFIED | `src/scraper/flag_crosswalk.py:223` の `__all__` が `["FLAG_CROSSWALK", "CLASS_PATTERNS", "derive_race_flags"]` のみ（`GRADE_PATTERNS` 削除）。行動確認: `'GRADE_PATTERNS' in __all__` == False。`ruff check src/scraper` が F822 エラーゼロ（旧 deferred-items.md line 14 の F822 が解消）。`from src.scraper.flag_crosswalk import *` 成功。 |
| 8   | CR-02 FIXED: ヒヤシンスS(Listed) の `grade` が `'(L)'`（カッコ付き）で RaceSchema 仕様違反 | ✓ VERIFIED | `src/scraper/parser.py:457-459` で `grade = raw.strip("()（）")` + `if grade == "リステッド": grade = "L"`。行動確認: ヒヤシンスS (202405010809) `grade == 'L'`（カッコなし）、宝塚記念 (202309030811) `grade == 'GI'`（維持）。 |

**Score:** 7/8 truths verified (1 truth — UAT-Test-6 live enumeration — splits between URL-form VERIFIED and live-data HUMAN)

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `src/scraper/__init__.py` | Public re-exports (10 symbols) | ✓ VERIFIED | `run_scrape, fetch_race_html, fetch_with_retry, enumerate_races(+day_urls,for_day), parse_race_html, normalize_to_parquet, FetcherSession, RaceRef` すべて import 成功 |
| `src/scraper/enumeration.py` | 3-level calendar traversal + `/race/list/{YYYYMM}/` | ✓ VERIFIED | 3関数分離 + URL 形式修正済み + race_id 12桁バリデーション |
| `src/scraper/fetcher.py` | FetcherSession + dedup + rate-limit + atomic write | ✓ VERIFIED | すべて実装済み、`detect_block_page` でCAPTCHA/403検出 |
| `src/scraper/parser.py` | Header-driven BS4 parser + flag crosswalk + CR-02 grade normalize | ✓ VERIFIED | 5 golden fixtures が正しくパース、grade='L'/'GI'/None |
| `src/scraper/flag_crosswalk.py` | FLAG_CROSSWALK (国際削除) + derive_race_flags + CR-01 __all__ | ✓ VERIFIED | UAT-Test-3 + CR-01 修正確認済み、Phase 6 調整注記あり |
| `src/scraper/normalizer.py` | Strict typed + partition_map + atomic Parquet | ✓ VERIFIED | SCHEMA_DTYPE_MAP (Float64 for corners), merge-dedup 実装 |
| `src/scraper/orchestrator.py` | run_scrape wiring 4 stages | ✓ VERIFIED | live/offline 両モード、ValueError ガード |
| `tests/scraper/fixtures/html/calendar_202306.html` | Golden /race/list/ snapshot | ⚠ SYNTHETIC | 実ページではなく "constructed from verified live probe data"。パーサ形状検証には有効だが、ライブURL形式の実証ではない |
| `tests/scraper/fixtures/html/{5 race IDs}.html` | Authentic netkeiba HTML | ✓ VERIFIED | 215-318KB、実サイト構造。ヒヤシンスSには `<h1>ヒヤシンスステークス(L)</h1>` が含まれ CR-02 検出可能 |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `orchestrator.py` | `enumeration.py` | `enumerate_races` | ✓ WIRED | line 139/151 |
| `orchestrator.py` | `fetcher.py` | `FetcherSession` + `fetch_race_html(fetch_callable=...)` | ✓ WIRED | line 133/202-207 |
| `orchestrator.py` | `parser.py` | `parse_race_html(path)` | ✓ WIRED | line 215 |
| `orchestrator.py` | `normalizer.py` | `normalize_to_parquet` | ✓ WIRED | line 160 |
| `parser.py` | `flag_crosswalk.py` | `derive_race_flags(race_condition, grade_haystack)` | ✓ WIRED | line 511 (WR-04: grade_haystack を race_name として渡すことは意図的とコメント文書化) |
| `parser.py` | `course_codes.py` | `COURSE_CODE_MAP[course_name]` | ✓ WIRED | line 472-473 |
| `flag_crosswalk.py` | `src/pipeline/column_mapping.py` | Phase 6 調整注記 | ✓ DOCUMENTED | line 20-46 で (国際) の Kaggle 側マッピング残存と Phase 6 での調整を明記 |
| `__init__.py` | 全サブモジュール | re-exports | ✓ WIRED | 10 シンボルすべて解決 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `parse_race_html` 戻り値 | `race`/`entries`/`results` dicts | 実 HTML ファイル (5 fixtures) | ✓ Yes (17頭/16頭/13頭/11頭/11頭) | ✓ FLOWING |
| `normalize_to_parquet` 出力 | Parquet files | parsed dicts | ✓ Yes (e2e テストで Parquet 生成確認) | ✓ FLOWING |
| `enumerate_races` 出力 | `list[RaceRef]` | calendar HTML → day HTML | ✓ Yes (golden calendar で8日分) | ✓ FLOWING (fixture) / HUMAN (live) |
| live `run_scrape` 出力 | standard Parquet | 実 netkeiba | ✗ 実行されていない | ⚠ LIVE RUN REQUIRED |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Public API import | `python -c "from src.scraper import run_scrape, ..."` | OK: all 8 symbols import | ✓ PASS |
| UAT-Test-3 (国際) graded | `derive_race_flags('...(国際)(特指)(ハンデ)')['race_flag_graded_stakes']` | None | ✓ PASS |
| GRADE_REGEX は健在 | `derive_race_flags('3歳オープン', race_name='宝塚記念(GI)')['race_flag_graded_stakes']` | True | ✓ PASS |
| CR-01 GRADE_PATTERNS | `'GRADE_PATTERNS' in __all__` | False | ✓ PASS |
| CR-02 grade normalize | `parse_race_html(ヒヤシンスS)['race']['grade']` | 'L' (not '(L)') | ✓ PASS |
| CR-02 G1 grade 保続 | `parse_race_html(宝塚記念)['race']['grade']` | 'GI' | ✓ PASS |
| UAT-Test-6 URL form | `enumerate_race_day_urls(2023, 6, fake)` captured URL | https://db.netkeiba.com/race/list/202306/ | ✓ PASS |
| 5 fixtures パース | 5 race HTML を parse_race_html | 全成功、行動的に正しい grade/頭数 | ✓ PASS |
| Scraper test suite | `pytest tests/scraper/ -q` | 212 passed, 1 skipped | ✓ PASS |
| E2E test suite | `pytest tests/scraper/test_end_to_end.py` | 13 passed, 1 skipped | ✓ PASS |
| ruff src/scraper | `ruff check src/scraper` | All checks passed | ✓ PASS |
| ruff tests (既知の遅延) | `ruff check tests/scraper/test_enumeration.py` | 4 cosmetic (F401/F821/F841) | ℹ INFO (pre-existing, documented) |

### Probe Execution

該当なし（本フェーズは `scripts/*/tests/probe-*.sh` を宣言しておらず、 conventional probe も存在しない）。代わりに pytest を用いた行動的スポットチェックで検証。

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| SCRP-01 | 04-01..08 | fetch/parse/normalize/feature分離基盤 | ✓ SATISFIED | 8つのソースモジュールが明確に分離、`__init__.py` が10シンボルを再エクスポート、orchestrator が4段階を明示接続 |
| SCRP-02 | 04-02,03,06,08 | 2022以降のJRAレースHTMLを取得しraw保存 | ✓ SATISFIED | fetcher が `data/raw/netkeiba/{YYYY}/{MM}/{race_id}.html` へ atomic 書き込み、dedup・rate-limit・block検出実装、URL 形式修正済み |
| SCRP-03 | 04-04,05,06,07 | 保存済みHTMLからstandard形式変換 | ✓ SATISFIED | parser が header-driven で5 fixtures を正しくパース、normalizer が strict typed で Kaggle スキーマ互換 Parquet 生成、CR-02 grade 正規化済み |
| SCRP-05 | 04-03,06 | 重複取得回避・既存HTMLキャッシュ活用 | ✓ SATISFIED | `fetch_race_html` line 302-306 で非零既存ファイルを再利用、`write_partitioned_parquet` で同月 re-run 時の merge-dedup 実装 |

**要件トレーサビリティ:** REQUIREMENTS.md の Phase 4 マッピング (SCRP-01/02/03/05 = Complete) と一致。SCRP-04（三連複オッズ）は正しく Phase 5 に振り分けられており本フェーズのスコープ外。孤児要件なし。

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `tests/scraper/test_enumeration.py` | 16, 29, 37, 315 | ruff F401/F821/F841 (unused imports, unused var) | ℹ INFO | 機能影響なし。`deferred-items.md` に pre-existing として文書化済み（Plan 04-02 由来）。本フェーズの動作成果物ではない |
| `src/scraper/normalizer.py` | 458, 470, 505-516, 680 | "placeholder" キーワード | ℹ INFO | empty-input の zero-row typed Parquet センチネルを指す（STUB ではない）。Plan 04-05 の明示的設計、テストで担保 |
| `tests/scraper/fixtures/html/calendar_202306.html` | 1-6 | SYNTHETIC marker | ⚠ WARNING | 実 HTML ではなく "constructed from verified live probe data"。パーサ回帰テストには有効、ライブURL実証には不十分 → human にルーティング |

**Debt marker gate:** TBD/FIXME/XXX は src/ にも tests/ にも存在しない（grep 結果ゼロ）。TODO/HACK/PLACEHOLDER もソースコードには存在しない。

### Human Verification Required

### 1. ライブスクレイプによる 2022-2024 データ取得の実証

**Test:** `run_scrape(live=True, start_date=datetime.date(2023,6,25), end_date=datetime.date(2023,6,25), max_races=3)` を実行する。必要に応じて `fetch_html=None` (デフォルト) で実際の FetcherSession を使用。実行後、`data/raw/netkeiba/2023/06/*.html` と `data/standard/scraped/202306/{race,entry,result}.parquet` を確認。

**Expected:**
- `data/raw/netkeiba/2023/06/` に少なくとも1つの非零 `.html` ファイルが保存される
- `data/standard/scraped/202306/race.parquet` に行数 >0 のレース行が存在する
- `data/standard/scraped/202306/entry.parquet` と `result.parquet` に行数 >0 の出走・結果行が存在する
- race_id `202309030811`（宝塚記念）が含まれ、`grade == 'GI'`、`race_flag_graded_stakes == True` であることをスポットチェック
- カレンダーURL `/race/list/202306/` が実際に8開催日（6/3,4,10,11,17,18,24,25）のリンクを返すことを確認（合成 golden fixture の検証を実データで再確認）

**Why human:** 実ネットワークアクセスと実 netkeiba サイト構造が必要。本環境ではライブスクレイプが実行されておらず、`calendar_202306.html` は SYNTHETIC（冒頭コメントに "constructed from verified live probe data because live fetch was unavailable" と明記）。UAT-Test-6 で実証されたURL形式 `/race/list/{YYYYMM}/` がPlan 04-08 調査時にプローブ済みであることは文書化されているが、本環境での再実証は不可。

### Gaps Summary

**機械的パイプライン能力:** すべて VERIFIED。fetch/parse/normalize の分離、raw HTML の atomic 保存、dedup、rate-limit、Kaggle スキーマ互換 Parquet 出力、UAT-Test-3 と UAT-Test-6 の URL/flag 修正、CR-01 と CR-02 の review fix — すべて実ソースコードとテストで確認済み。212 テスト + 13 e2e テストが緑。

**実際の2022-2024データ入手:** NOT YET — `run_scrape(live=True)` が本環境で実行されておらず、`data/standard/scraped/` に実際の標準 Parquet が存在しない。フェーズ目標「2022-2024 JRA race results ... are scraped and available in standard Parquet」の字義解釈では、実際のデータが Parquet に存在することが求められる。パイプラインは準備完了だが、実データ生成は human 検証ステップとして残っている。

**判定:** 自動検証可能なすべての truth は VERIFIED。残る1項目（ライブ列挙 + 実データ Parquet 生成）は人間による実ネットワーク検証が必要なため、ステータスは `human_needed` とする。ライブ実行後にスキーマ互換性・行数・grade 正確性を確認できれば `passed` に昇格可能。

---

_Verified: 2026-06-14T14:45:00Z_
_Verifier: Claude (gsd-verifier)_
