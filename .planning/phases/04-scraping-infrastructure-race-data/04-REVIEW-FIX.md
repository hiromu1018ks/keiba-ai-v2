---
phase: 04-scraping-infrastructure-race-data
fixed_at: 2026-06-14T14:30:00Z
review_path: .planning/phases/04-scraping-infrastructure-race-data/04-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 04: Code Review Fix Report (Gap-Closure — Plans 04-07 / 04-08)

**Fixed at:** 2026-06-14T14:30:00Z
**Source review:** `.planning/phases/04-scraping-infrastructure-race-data/04-REVIEW.md`
**Iteration:** 1
**Fix scope:** `critical_warning` (Critical + Warning only; Info findings IN-01..IN-03 excluded)

## Summary

- Findings in scope: 6 (2 Critical + 4 Warning)
- Fixed: 6
- Skipped: 0
- Status: all_fixed

REVIEW.md の指摘事項 6 件（Critical 2 件 + Warning 4 件）をすべて適用・検証した。
各修正は原子的にコミット（finding ごとに 1 コミット、関連するものは同ファイルで束ねて整理）。
ソースファイルは壊れた状態を残さず、既存の回帰テストはすべて緑を維持。

### Verification

- `tests/scraper/test_parser.py`: 94 passed（ベースライン同等）。WR-03 で追加した `assert race["grade"] == "GI"` 表明も含めて緑。
- `tests/scraper/` 全体: 212 passed, 1 skipped。
- 全フェーズ回帰（fix 後）: 448 passed, 1 skipped。Phase 03 (feature-engineering) 等、他フェーズへの回帰なし。

## Commits

| Commit | Findings | Files |
|--------|----------|-------|
| `1aaf36b` | CR-01, WR-01 | `src/scraper/flag_crosswalk.py` |
| `f1d3477` | CR-02 | `src/scraper/parser.py` |
| `05e1d1f` | WR-02, WR-03 | `tests/scraper/test_parser.py` |
| `e9d9cf2` | WR-04 | `src/scraper/parser.py` |

## Fixed Issues

### CR-01: `GRADE_PATTERNS` declared in `__all__` but never defined (ImportError)

**Severity:** Critical
**File:** `src/scraper/flag_crosswalk.py:210`
**Commit:** `1aaf36b`

実証された `ImportError`。`__all__` に `GRADE_PATTERNS` が宣言されていたが、実際の正規表現は private な `_GRADE_REGEX`（line 119）であり、`GRADE_PATTERNS` は未定義だった。`from src.scraper.flag_crosswalk import GRADE_PATTERNS` が `ImportError`、`from ... import *` が `AttributeError` になる。テストが両 import path を叩かないため潜在化していた。Plan 04-04（commit `87539b0`）からの既存バグで、gap-closure では触れていなかったが実証済みのため今回修正。

**Applied fix:** リポジトリ全体を `grep` し `GRADE_PATTERNS` の利用箇所がないことを確認した上で、`__all__` から `GRADE_PATTERNS` を削除（alias 追加ではなく export 削除を選択）。併せてセクションコメントの見出しを `GRADE_PATTERNS:` から `_GRADE_REGEX:` に修正し、将来の混同を防止。

### CR-02: Listed レースの `grade` がリテラル `'(L)'`（カッコ付き）になり RaceSchema 仕様違反

**Severity:** Critical
**File:** `src/scraper/parser.py:439-443`
**Commit:** `f1d3477`

ヒヤシンスS（L 馬券、race_id `202405010809`）の `grade` フィールドが `'(L)'`（カッコ付き）になった。`RaceSchema.grade` の docstring は `"G1/G2/G3/G/listed or empty"`（bare トークン）を要求し、Kaggle 側の `リステッド・重賞競走` ソース列も bare トークンを保持する。カッコ付きのままだと Phase 6 の Kaggle 結合でサイレントに NaN 化する恐れがあった。実証済み。

**Applied fix:** キャプチャトークンからカッコを剥がし、`リステッド` を `'L'` に正規化。5 つのゴールデンフィクスチャで検証：`202405010809` の `grade` が `'(L)'` → `'L'`、`202309030811`（宝塚記念 GI）は `'GI'` のまま維持。

### WR-01: `_GRADE_REGEX` alternation order reversed (longest-match footgun)

**Severity:** Warning
**File:** `src/scraper/flag_crosswalk.py:119`
**Commit:** `1aaf36b`

`_GRADE_REGEX` の選択肢順序が `GI|GII|GIII` になっており、左most-match で `GII`/`GIII` が `GI` に誤判定される可能性があった。`parser.py:108` の `_GRADE_TOKEN_RE`（正しく長い順）と非対称。現在は真偽値の test 結果しか使わないため潜在していたが、`parser.py` 側のコメントが明示的にこの footgun を警告していた。

**Applied fix:** 選択肢を `GIII|GII|GI`（長い順）に並び替え、`_GRADE_TOKEN_RE` と対称化。

### WR-02: `test_parser.py` module docstring still documents the removed `(国際)` → `graded_stakes` mapping

**Severity:** Warning
**File:** `tests/scraper/test_parser.py:10-11`
**Commit:** `05e1d1f`

モジュール docstring が、Plan 04-07 で削除された `(国際)` → `race_flag_graded_stakes` マッピングを未だ HIGH #6 不変条件として説明していた。コードと乖離。

**Applied fix:** docstring を Plan 04-07 の新契約（`(国際)` は国際指定マーカーであり graded ではない；真の重賞検出は GRADE_REGEX のみ）に更新。

### WR-03: Misleading comment attributes `graded_stakes=True` to `(国際)` (now comes from `<h1>` GI token)

**Severity:** Warning
**File:** `tests/scraper/test_parser.py:430`
**Commit:** `05e1d1f`

`test_flag_crosswalk_applied_on_graded_fixture` のコメントが、`graded_stakes` を `(国際)` 由来と説明していた。実際は（Plan 04-07 の Rule-1 deviation で）`<h1>` の GI トークン由来。実証：`race_name` を空にして `derive_race_flags` を呼ぶと確認できる。

**Applied fix:** コメントを GI トークン由来に修正。併せてレビュー提案通り `assert race["grade"] == "GI"` を追加（CR-02 を捕捉できたはずの表明。今後の回帰ガード）。

### WR-04: `grade_haystack` passed as the `race_name` parameter to `derive_race_flags` (conflation)

**Severity:** Warning
**File:** `src/scraper/parser.py:467`
**Commit:** `e9d9cf2`

`grade_haystack`（`race_name` + `<h1>` テキストの結合）が `derive_race_flags` の `race_name` 仮引数に渡されており、2 つの関心が混在している。潜在的な結合：`<h1>` テキスト内の flag-marker トークンが `FLAG_CROSSWALK` の部分文字列マッチングに拾われる可能性。

**Applied fix:** レビュー Option (a)（素の `race_name` を渡す）は UAT-Test-3 回帰テストを壊すことを実証（`derive_race_flags('... (国際)(指)(定量)', '宝塚記念')` → `graded_stakes=None`）。レビューの「UAT-Test-3 を壊さない最小変更」ガイダンスに従い、呼び出し箇所のコメントを拡充し、結合が意図的かつ負荷のかかる選択であること（GRADE_REGEX が haystack 全体を走査するため GI トークン検出に必要）を文書化（Option (b) フォールバック）。動作変更なし。

## Out of Scope (Info findings, not addressed this round)

以下 3 件の Info finding は `fix_scope: critical_warning` のため対象外。必要に応じて別途対応。

- **IN-01** `src/scraper/flag_crosswalk.py:195` — haystack が `race_condition` 空の場合に `race_name` を除外する。
- **IN-02** `src/scraper/parser.py:115` — `リステッド` 代替が bare CJK 文字列を `grade` に運ぶ（CR-02 の正規化で緩和済み）。
- **IN-03** `tests/scraper/test_parser.py` — いずれのフィクスチャでも `grade` フィールド値を表明するテストがなかった（WR-03 で `assert race["grade"] == "GI"` を追加し緩和）。
