---
phase: 04-scraping-infrastructure-race-data
plan: 04
subsystem: scraper/parser
tags: [scraper, parser, netkeiba, course-codes, flag-crosswalk, golden-fixtures, header-driven, tdd]
requires:
  - 04-01 (KAGGLE_COLUMN_MAP as authoritative flag source via src/pipeline/column_mapping.py)
  - 04-02 (RaceRef for fixture race_id semantics)
provides:
  - src/scraper/parser.py (parse_race_html, parse_horse_weight, parse_sex_age, resolve_columns_by_header)
  - src/scraper/course_codes.py (COURSE_CODE_MAP single source of truth)
  - src/scraper/flag_crosswalk.py (FLAG_CROSSWALK + derive_race_flags, exhaustive over KAGGLE_COLUMN_MAP)
  - tests/scraper/fixtures/html/ (5 golden HTML fixtures — contract for Plan 06 end-to-end)
affects:
  - 04-05 (normalizer consumes parser output dicts)
  - 04-06 (end-to-end test loads golden fixtures through parser + normalizer)
tech-stack:
  added: []
  patterns:
    - "BS4+lxml header-driven column resolution (no hardcoded td indices)"
    - "Golden-fixture-driven parser tests (real netkeiba DOM, not fabricated HTML)"
    - "Parametrized coverage guard: FLAG_CROSSWALK diffed against KAGGLE_COLUMN_MAP"
key-files:
  created:
    - tests/scraper/test_course_codes.py
    - tests/scraper/test_parser.py
    - tests/scraper/fixtures/html/202206050509.html
    - tests/scraper/fixtures/html/202309030811.html
    - tests/scraper/fixtures/html/202405010809.html
    - tests/scraper/fixtures/html/202206050508.html
    - tests/scraper/fixtures/html/202209060504.html
  modified:
    - src/scraper/parser.py
decisions:
  - "D1: race_name extracted from <title> not <h1> — netkeiba's <h1> holds the site logo. Format: '<race_name>｜YYYY年MM月DD日 | ...'. (Rule 1 deviation fix verified against 5 fixtures.)"
  - "D2: obstacle detection keyed off '障害' substring in race_condition (not the course-info line, which lacks a direction token for obstacle races)."
  - "D3: course-info regex accepts 'ダ' shorthand for ダート, '外' outer-loop marker, and optional direction (obstacle races have no direction)."
  - "D4: race_flag_graded_stakes set via (国際) substring for Kaggle join compatibility; race_flag_stakes remains None when the race name has no explicit GI/G1 token (宝塚記念 smalltxt has no grade token). Plan accepts this — Phase 6 may revisit."
metrics:
  duration: ~25min
  completed: 2026-06-14
  tasks: 4
  tests_added: 103
  files_created: 7
  files_modified: 1
---

# Phase 4 Plan 04: netkeiba Race Parser Summary

ヘッダ駆動BS4+lxml parserを実装し、5個の本物netkeiba HTMLゴールデンフィクスチャに対してend-to-end検証を行った。Cycle-1 HIGH #2/#5/#6/#10、Cycle-2 HIGH #2（FLAG_CROSSWALK完全カバー）、HIGH #9（ゴールデンフィクスチャ）をすべて解決。

## What Was Built

### 1. 単一権威COURSE_CODE_MAP (Task 1, commit 87539b0)
`src/scraper/course_codes.py` — JRA 10会場の2桁コードマップ。Cycle-1 HIGH #5修正済み（福島=03, 新潟=04）。parser・normalizer両方がここからimport。

### 2. FLAG_CROSSWALK完全カバー (Task 1, commit 87539b0)
`src/scraper/flag_crosswalk.py` — netkeibaテキスト -> `race_flag_*` 変換。Cycle-2 HIGH #2で`column_mapping.py`が定義する13個の`race_flag_*`ターゲットを網羅:
- `("牡", "race_flag_colt_only")` 追加 (column_mapping.py:61)
- bare `("見習騎手", "race_flag_apprentice")` 追加 (column_mapping.py:66)
- 両形式 `(見習騎手)` と bare `見習騎手` をマッチ

`derive_race_flags()`はRaceSchemaの20キーを返す（未知は`None`、`False`は未観察を意味しない）。

### 3. ヘッダ駆動parser (Task 2, commit 7f6d82e + Task 4修正)
`src/scraper/parser.py`:
- `parse_race_html(html_path) -> {race, entries, results}` — RaceSchema/EntrySchema/ResultSchemaキーと互換
- `parse_horse_weight("456(+4)") -> (456, 4)` / `("計不") -> (None, None)`
- `parse_sex_age("牡4") -> ("牡", 4)`
- `resolve_columns_by_header(table, aliases)` — `<th>`テキストから列インデックス解決（HIGH #10、固定`cols[N]`排除）
- 14桁`horse_race_id = f"{race_id}{horse_number:02d}"`（HIGH #2、アンダースコアなし）
- `head_count`フィールドはemitしない（RaceSchemaに存在しない、MEDIUM）
- `surface_detail`/`course_detail`/`track_condition_detail`は`None`でemit（MEDIUM、normalizerがreindex可能）

### 4. ゴールデンHTMLフィクスチャ (Task 3, commit 97b1dc2)
5個の本物netkeiba HTML（ユーザーがPlaywrightで取得）:

| race_id | レース | コース | 距離 | クラス | 多様性軸 |
|---------|--------|--------|------|--------|----------|
| 202206050509 | ひいらぎ賞 | 中山(06) 芝 | 1600m | 1勝クラス | #1 base turf |
| 202309030811 | 宝塚記念 | 阪神(09) 芝 | 2200m | G1 | #2 graded stakes |
| 202405010809 | ヒヤシンスS | 東京(05) ダート | 1600m | L(Listed) | #3 dirt |
| 202206050508 | 3歳以上1勝クラス | 中山(06) ダート | 1200m | 1勝クラス | extra dirt |
| 202209060504 | 障害3歳以上OP | 阪神(09) 障害 | 3110m | OP | #5 obstacle |

面=芝×2 (base+G1), ダート×2, 障害×1。年=2022/2023/2024。コース=中山(06)/阪神(09)/東京(05)。

### 5. テストスイート (Task 4, commit 3c686bc)
103新規テスト:

| クラス | テスト数 | 対象 |
|--------|----------|------|
| `TestCourseCodes` | 13 (10 parametrized) | HIGH #5 course-code regression guard |
| `TestHorseWeightParsing` | 7 | parse_horse_weight 全形式 |
| `TestSexAgeParsing` | 4 | parse_sex_age 全形式 |
| `TestFlagCrosswalk` | 16 (13 parametrized) | HIGH #6 + Cycle-2 #2 |
| `TestResolveColumnsByHeader` | 3 | HIGH #10 header-driven |
| `TestParseRaceHtmlGolden` | 59 (5×parametrized) | HIGH #9 end-to-end |

**Cycle-2 HIGH #2 coverage guard:** `test_crosswalk_covers_all_kaggle_flag_targets`は`KAGGLE_COLUMN_MAP`から抽出した13個の`race_flag_*`ターゲットでパラメータ化し、各々がFLAG_CROSSWALKでカバーされることを機械的に検証。ターゲット欠落は名前付き失敗（例: `race_flag_colt_only[FAIL]`）。

`pytest tests/scraper/ -q` = **121 passed**（103新規 + 18既存enumeration）。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] race_name extraction source wrong**
- **Found during:** Task 4 (verifying parser against golden fixtures)
- **Issue:** プランのTask 2指示「race_name from `<h1>`」は実DOMと不一致。netkeibaの`<h1>`は**サイトロゴ**を含み、race_nameは空。5個すべてのフィクスチャで`race_name=None`になった。
- **Fix:** `<title>`から抽出。`<title>`形式は`"<race_name>｜YYYY年MM月DD日 | 競馬データベース - netkeiba"`（full-width `｜`区切り）。最初のパイプ区切りセグメントをrace_nameとする。`<h1>`はfallback。
- **Files modified:** `src/scraper/parser.py` (_parse_race_header)
- **Commit:** 3c686bc

**2. [Rule 1 - Bug] _COURSE_INFO_RE real-world forms not handled**
- **Found during:** Task 4 (verifying parser against golden fixtures)
- **Issue:** プランのTask 2指示の正規表現 `(芝|ダート|障害)?\s*(芝|ダート)?\s*(右|左|直線)?\s*(\d+)m` は実DOM形式を処理できず:
  - `芝右 外1600m` (turf外回り、スペース+外) — スペースと「外」でマッチ失敗
  - `ダ左1600m` / `ダ右1200m` — netkeiba略記の`ダ`（ダートの省略形）未対応
  - `障芝 ダート3110m` — 障害混合面、方向トークンなし — 完全にマッチせず`obstacle=None`, `distance=None`
- **Fix:** 正規表現を`(芝|ダート|ダ)\s*(右|左|直線|直)(?:\s*(外))?\s*(\d+)m`に書き直し、`ダ`->`ダート`正規化、`外`アウタループマーカー、方向オプション化。障害検出は`race_condition`中の`障害`部分文字列に移動（course-info行に方向トークンがないため）。距離は`_DISTANCE_RE = r"(\d{3,5})m"`で別途抽出。
- **Files modified:** `src/scraper/parser.py` (_COURSE_INFO_RE, _parse_race_header)
- **Commit:** 3c686bc

**3. [Rule 1 - Bug] Unused _GRADE_REGEX import**
- **Found during:** Task 4 lint check (ruff F401)
- **Issue:** `parser.py`が`_GRADE_REGEX`をimportしていたが、コメント内でのみ言及し実際のコードでは未使用。
- **Fix:** importから`_GRADE_REGEX`を削除。
- **Files modified:** `src/scraper/parser.py`
- **Commit:** 3c686bc

## Test Counts by Class (full breakdown)

- `TestCourseCodes`: 13 (3 unit + 10 parametrized venue codes)
- `TestHorseWeightParsing`: 7 (parametrized formats)
- `TestSexAgeParsing`: 4 (parametrized formats)
- `TestFlagCrosswalk`: 16 (8 unit + 3 Cycle-2 tests + 13 parametrized coverage guard, dedup-aware)
- `TestResolveColumnsByHeader`: 3
- `TestParseRaceHtmlGolden`: 59 (parametrized ×5 fixtures across multiple assertions)

合計103新規テスト、最小要件24を大きく上回る。

## Authentication Gates

None.

## Known Stubs

None — すべてのparser出力は5個のゴールデンフィクスチャでend-to-end検証済み。race_flag_stakesがG1フィクスチャで`None`になるのは既知の意味論的挙動（Kaggle互換性のため`(国際)`→`race_flag_graded_stakes`のみ設定、レース名に明示的なGIトークンがない場合`race_flag_stakes`は設定されない）。プランが明示的にaccept（Decision D4）。

## Threat Flags

None — 脅威モデル T-04-10/11/12/13/14 はすべてプラン内で処理済み。新規のtrust boundaryは導入されていない。

## Self-Check: PASSED

**Files verified:**
- [x] FOUND: tests/scraper/test_course_codes.py
- [x] FOUND: tests/scraper/test_parser.py
- [x] FOUND: tests/scraper/fixtures/html/202206050509.html
- [x] FOUND: tests/scraper/fixtures/html/202309030811.html
- [x] FOUND: tests/scraper/fixtures/html/202405010809.html
- [x] FOUND: tests/scraper/fixtures/html/202206050508.html
- [x] FOUND: tests/scraper/fixtures/html/202209060504.html
- [x] FOUND: src/scraper/parser.py (modified)

**Commits verified:**
- [x] FOUND: 87539b0 (Task 1: COURSE_CODE_MAP + FLAG_CROSSWALK)
- [x] FOUND: 7f6d82e (Task 2: parser implementation)
- [x] FOUND: bdb92e5 (Task 3 placeholder: fixtures dir + README)
- [x] FOUND: 97b1dc2 (Task 3: 5 golden fixtures)
- [x] FOUND: 3c686bc (Task 4: tests + parser deviation fixes)

**Test suite:** `pytest tests/scraper/ -q` = 121 passed (0 failed).
