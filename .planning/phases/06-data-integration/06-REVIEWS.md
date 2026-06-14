---
phase: 06-data-integration
reviewers: [codex]
reviewed_at: 2026-06-14T19:30:00+09:00
plans_reviewed:
  - 06-01-PLAN.md
  - 06-02-PLAN.md
  - 06-03-PLAN.md
cycle: 1
---

# Cross-AI Plan Review — Phase 6

Single-reviewer cycle (Codex / gpt-5.5 via `codex exec`). Reviewer had read access to the repository and verified code references live; the orchestrator independently re-verified the four load-bearing HIGH claims against the working tree (see "Orchestrator verification" block at the end of each plan's Concerns).

---

## Codex Review

### Plan 06-01 Review

**Summary**

D-01/D-02を統合前に解消する順序は適切ですが、現状の計画には実行を阻害する重大な誤認があります。特にKaggle変換側には`GRADE_REGEX`による重賞判定が存在しないため、`(国際)`マッピングを削除するだけでは約838件にはならず、`race_flag_graded_stakes`がほぼ全消失します。また「8項目検証」は実際には3項目を省略しています。

**Strengths**

- dtype調停を統合処理ではなく生成元で直す方針は妥当。
- `SCHEMA_DTYPE_MAP`を単一の型契約として再利用している。
- 不正値を`errors="ignore"`で隠さず、`TypeError`にする方針は適切。
- Parquet書き込みの原子化は破損リスクを軽減する。
- `FLAG_COLUMNS`から`(国際)`を削除しない判断は正しい。
- 実コード上、以下の参照は確認できた。
  - `KAGGLE_COLUMN_MAP`の`(国際)`マッピング
  - `SCHEMA_DTYPE_MAP`
  - `_atomic_write_parquet(df, path)`
  - `run_all_validations(raw_dir, parquet_dir, source_counts=None, source_stats=None)`

**Concerns**

- **HIGH — Task 1 / D-01:** Kaggle変換側には`GRADE_REGEX`がない。`GRADE_REGEX`は`src/scraper/flag_crosswalk.py`だけにあり、`kaggle_converter.py`からは呼ばれていない。マッピング削除だけでは「GI/GII/GIIIのみ約838件」という結果にならない。
- **HIGH — Task 3:** `source_counts=None`と`source_stats=None`では、行数・null率・分布の3検証が空で成功扱いになる。「Phase 2 D-05 8-point verification passes」という表現は不正確。
- **HIGH — 全Task:** コマンドが`poetry run`になっているが、このリポジトリはpip/setuptools運用でPoetry未使用。実行環境によって計画が即座に失敗する。
- **MEDIUM — D-02:** CONTEXTでは`race_date`をdatetimeにするとあるが、実際の`SCHEMA_DTYPE_MAP[RaceSchema]["race_date"]`は`"string"`。計画と型契約が矛盾している。
- **MEDIUM — Task 2:** `convert()`はrace/entry/resultだけでなく、`odds_trifecta`と`payoff`も上書きする。`files_modified`および後続計画の「odds/payoff unchanged」と整合しない。
- **MEDIUM — Task 2:** 別パッケージのprivate関数`_atomic_write_parquet`へ依存する。共有ユーティリティへ移す方が所有境界として明確。
- **LOW — コード参照:** 行番号は現在おおむね近いが、編集後にずれるため、行番号を受入条件に使うのは脆い。

**Suggestions**

- Kaggle側にも`grade`や`race_name`を入力とする共通の重賞判定関数を適用し、個別テストを追加する。
- 約838件の範囲チェックではなく、`grade`から導出した期待値との行単位比較にする。
- 再検証時は変換前に`source_counts`と`source_stats`を取得し、8項目すべてを実際に実行する。
- 全コマンドを`python -m pytest`、`python -c`へ変更する。
- `race_date`はstringかdatetimeのどちらを標準契約とするか決定し、CONTEXTとコードを統一する。
- odds/payoffを保存するか、変換前後のchecksum一致を検証する。

**Risk Assessment**

**HIGH**。D-01の実装案では重賞フラグの正解値を生成できず、Wave 2へ誤ったデータを渡す可能性があります。

> **Orchestrator verification (06-01 HIGHs):**
> - **GRADE_REGEX:** Confirmed. `grep GRADE_REGEX src/pipeline/kaggle_converter.py` → no match. The regex lives only in `src/scraper/flag_crosswalk.py:124` (`_GRADE_REGEX`). The Kaggle converter has no grade-detection path; deleting the `(国際)` mapping would make `race_flag_graded_stakes` False for *all* Kaggle rows, not ~838. The plan's 780–880 acceptance band is therefore unreachable as written.
> - **8-point skip:** Confirmed. `src/pipeline/validators.py` gates `validate_row_counts` (line 791), `validate_null_rates` (801), `validate_distributions` (807), and a 4th block (825) all behind `if source_counts is not None` / `if source_stats is not None`. The plan invokes `run_all_validations(Path('data/raw/kaggle'), Path('data/standard'))` with both optional args omitted, so ~3-4 of the 8 checks are skipped rather than passing.
> - **poetry:** Confirmed. `which poetry` → not found. `pyproject.toml` uses `[build-system] requires = ["setuptools>=68.0"]` / `build-backend = setuptools.build_meta`. Every `poetry run …` command in all three plans will fail. Use `python -m pytest` / `python -c …` (or `python3 -m …`).
> - **convert() overwrites odds/payoff:** Confirmed. `src/pipeline/kaggle_converter.py:107-117` builds `tables = {…, "odds_trifecta": …, "payoff": …}` and writes all five. Plan 06-01 Task 2 invokes `convert()` (defaults) which will overwrite `data/standard/odds_trifecta.parquet` and `payoff.parquet`, violating D-05 and invalidating Plan 06-03's "odds/payoff unchanged" assertion.

---

### Plan 06-02 Review

**Summary**

統合処理の基本構造は小さく理解しやすい一方、入力と出力が同じパスであるため再実行不能で、3テーブルを一括更新するトランザクション性もありません。またテストのskip設計、参照整合性検証、スキーマ検証が計画内で矛盾しています。

**Strengths**

- `SCHEMA_BY_TABLE`による3テーブル限定はodds/payoff保護に有効。
- PK重複を黙って除去せず停止する方針は適切。
- canonical column orderへの統一とnullable dtype再適用は必要。
- per-rowログを避けた設計は性能面で妥当。
- 一時ディレクトリを使うhermeticテストの方針は良い。
- `source`列をstandard層に追加しない決定と整合する。

**Concerns**

- **HIGH — `integrate_standard_layer`:** 入力`standard/{table}.parquet`を同じパスへ上書きするため、2回目は「統合済みデータ + scraped」を結合し、全scraped PKが重複して失敗する。再実行可能性がない。
- **HIGH — 書き込み処理:** raceを書いた後にentry/resultで失敗すると、異なる世代の3ファイルが残る。ファイル単位のatomic writeだけではcorpus全体の整合性を保証できない。
- **HIGH — Task 1:** `TestUnifiedCorpus`のautouse `_require_scraped_data`はクラス内のhermeticテストもskipする。計画中の「fast-pathはskip gateを持たない」と矛盾する。
- **HIGH — Task 2:** 「referential integrity」を実装していない。正常データで「例外が出ない」テストは、FK検証が存在しなくても通るため無効。
- **HIGH — Task 2:** `reindex()`は余分な列を黙って捨て、不足列をNAで追加する。入力側のスキーマドリフトを隠し、成功基準#2を誤って通す可能性がある。
- **MEDIUM — テスト数:** 「8 tests」と記載されているが、列挙されたメソッドは9件。
- **MEDIUM — audit:** `audit_leakage`をimportするとしているが、実装手順には実際のaudit呼び出しがない。
- **MEDIUM — 入力エラー:** Kaggleファイル欠落、scraped partitionなし、月内の特定テーブル欠落に対する明示的なエラー処理がない。
- **MEDIUM — 成功基準#2:** `source`列がないことは「起源を区別できない」の十分条件ではない。列型・null表現・値域の検証が必要。
- **LOW — private API:** Plan 06-01と同様に`_atomic_write_parquet`へ直接依存している。

**Suggestions**

- Kaggle-only入力を`data/standard/kaggle/`などに固定するか、統合前に一時入力スナップショットを作り、再実行可能にする。
- 3ファイルを一時ディレクトリへすべて生成・検証した後、一括切替する。
- `reindex()`前に列集合の完全一致をassertする。
- `validate_integrity()`を再利用し、FK欠損を実際に`ValueError`へする。
- hermeticテストとreal-corpusテストを別クラスまたはmarkerで分離する。
- テスト件数を9件へ修正するか、重複するD-01/D-02テストをPlan 06-01へ残して8件にする。
- 欠落ファイル、空partition、壊れたParquetのテストを追加する。

**Risk Assessment**

**HIGH**。初回統合は動く可能性がありますが、再実行不能と部分更新リスクはstandard corpusの信頼性を損なう重大な設計欠陥です。

---

### Plan 06-03 Review

**Summary**

実データでROADMAP基準を確認する最終waveとしての位置付けは正しいですが、現在のリポジトリは`data/standard/scraped/202306`の5レースのみで、既知の前提未達です。また、年月ディレクトリ数だけのゲート、弱い日付検証、統合後の重賞件数期待値などに問題があります。

**Strengths**

- smoke-onlyデータで本番統合しない停止条件を設けている。
- 行数、日付、PK、FK、型、leak auditをまとめて確認する方針は適切。
- human verificationを自動検証後に置いている。
- odds/payoffを統合対象外として確認する考え方は妥当。
- 現在の実データ状態は計画の記述どおり、202306の1partitionのみであることを確認できた。

**Concerns**

- **HIGH — 前提条件:** 現在は1か月・5レースのみであり、Plan 06-03は現状のままでは完了できない。
- **HIGH — Task 1:** 「40ディレクトリ以上」は完全性を保証しない。空ファイル、欠落テーブル、不正な日付範囲、途中月だけでも通過し得る。
- **HIGH — Task 2:** odds/payoffの「事前snapshot」は実行コマンドに含まれていない。統合後に行数を見るだけでは上書きされなかった証明にならない。
- **HIGH — Task 3:** 統合後の`graded_stakes=True`を780–880とする期待値は誤り。2022–2026の重賞レースが追加されるため、統合全体の件数はKaggleのみの約838より増える。
- **HIGH — 日付検証:** `max().startswith("2024") or startswith("2026")`は弱すぎる。2024年1月だけ、または2026年1月までしかなくても通る。
- **HIGH — 再実行:** Plan 06-02の設計のままでは、失敗後やhuman-check時の再統合が重複エラーになる。
- **MEDIUM — 行数検証:** 単なる下限値では、partition欠落や一部行損失を検出できない。入力partitionのPK集合との一致が必要。
- **MEDIUM — スコープ整合性:** ROADMAP/REQUIREMENTSは2015–2024のままだが、計画は2015–2026/5へ拡張している。下流のPhase 9は2015–2024前提であり、正式な仕様更新か明示的な期間フィルタが必要。
- **MEDIUM — 日付表現:** `race_date`がstringである現行契約を前提にした検証になっており、CONTEXTのdatetime方針と矛盾する。
- **LOW — 実行コマンド:** ここでも`poetry run`はリポジトリの実際の運用と一致しない。

**Suggestions**

- 月ディレクトリ数ではなく、各partitionのrace日付、3ファイル存在、非空性、PK/FK整合性を検証するpreflightを実装する。
- 統合前にodds/payoffのSHA-256、行数、Arrow schemaを保存し、統合後に完全一致を確認する。
- 期待行数を各入力partitionの一意PK集合から算出し、統合出力と集合一致させる。
- 日付範囲は期待する最初・最後の実開催日、または少なくとも年ごとのレース数で検証する。
- 重賞件数はKaggle期間とscraped期間を分けて検証する。
- 2015–2026/5への拡張を採用するならROADMAP/REQUIREMENTSもこのphaseで更新する。
- full suiteは`python -m pytest`で実行する。

**Risk Assessment**

**HIGH**。前提データが未取得で現在は実行不能です。さらに、現状の完了判定では不完全なcorpusをDATA-05達成済みと誤認する余地があります。

> **Orchestrator verification (06-03):** The "graded_stakes 780–880 post-integration" claim is internally inconsistent with Plan 06-01's Kaggle-only ~838 target: scraping adds 2022–2026 graded races, so the unified count must exceed 838. This compounds the Plan 06-01 GRADE_REGEX defect (if graded flags are near-zero on the Kaggle side after D-01, the unified count is dominated by scraped graded races and could be anywhere).

---

## Consensus Summary

Single-reviewer cycle — consensus is Codex's view, with orchestrator-side code verification backing the four load-bearing HIGH claims.

### Agreed Strengths (Codex)

- Correct sequencing: dtype/flag reconciliation at the producer (Kaggle) before the consumer (merge).
- `SCHEMA_DTYPE_MAP` reused as the single dtype authority.
- `_recast_to_canonical` raises on bad data instead of `errors='ignore'`.
- Atomic write for Parquet reduces corruption risk.
- `FLAG_COLUMNS` entry for `(国際)` correctly preserved (models CSV header, not the mapping).
- `SCHEMA_BY_TABLE` 3-table allowlist protects the Phase 5 odds/payoff seed at the integration boundary.
- Pre-dedup PK overlap raises loudly rather than silently dropping.
- Per-row logging avoided (honors `scraper-logging-no-per-item.md`).
- Hermetic tmp_path test fixtures for the fast-path tests.
- Smoke-only corpus halt gate (Plan 06-03 Task 1) prevents a misleadingly tiny corpus.

### Agreed Concerns (highest priority — all HIGH)

1. **[HIGH, 06-01] D-01 GRADE_REGEX gap.** The Kaggle converter has no `GRADE_REGEX`; deleting the `(国際)` mapping alone makes `race_flag_graded_stakes` False for nearly all Kaggle rows. The "~838 (780–880)" acceptance band is unreachable as written. A grade-detection function must be introduced on the Kaggle side or the target recomputed. *(Verified: `GRADE_REGEX` only in `src/scraper/flag_crosswalk.py:124`.)*
2. **[HIGH, 06-01] D-05 violation via `convert()`.** `convert()` writes all 5 tables including `odds_trifecta`/`payoff`; Plan 06-01 Task 2 invoking it will overwrite the Phase 5 seed, contradicting D-05 and Plan 06-03's "unchanged" assertion. *(Verified: `kaggle_converter.py:107-117` `tables` dict.)*
3. **[HIGH, 06-01] 8-point verification is not actually 8.** `run_all_validations` skips row-count / null-rate / distribution checks when `source_counts`/`source_stats` are None. The plan omits both, so ~3-4 of 8 checks are skipped, not passed. *(Verified: `validators.py:791,801,807,825`.)*
4. **[HIGH, all] `poetry run` commands fail.** Repo uses setuptools; `poetry` is not installed. Every test/verification command in all three plans will fail at invocation. *(Verified: `which poetry` → not found; `pyproject.toml build-backend = setuptools.build_meta`.)*
5. **[HIGH, 06-02] Non-idempotent integration.** `integrate_standard_layer` reads `standard/{table}.parquet` and writes the same path, so a second run re-merges already-merged Kaggle rows + scraped → all scraped PKs become duplicates → FAIL-LOUD aborts. Re-run after a partial failure or human-check is impossible.
6. **[HIGH, 06-02] No corpus-level transactionality.** Per-file atomic write does not prevent a mixed-generation corpus if entry/result writes fail after race succeeds.
7. **[HIGH, 06-02] autouse skip gate swallows hermetic tests.** The class-level autouse `_require_scraped_data` fixture will skip the hermetic fast-path tests too, contradicting the plan's "fast-path tests do not have the skip gate."
8. **[HIGH, 06-02] Referential-integrity test is a no-op.** "Does not raise" on well-formed data passes even if FK validation is absent. The integration module also does not call any FK validator.
9. **[HIGH, 06-02] `reindex()` silently masks schema drift.** `reindex` drops extra columns and adds missing ones as NA; success criterion #2 (schema identical) can pass spuriously. Needs an explicit column-set equality assert before reindex.
10. **[HIGH, 06-03] D-06 pre-task not done.** Real corpus is `data/standard/scraped/202306` only (5 races). Plan 06-03 cannot complete until the full 2022–2026/5 scrape runs. *(Verified by Codex reading the tree.)*
11. **[HIGH, 06-03] Month-count gate is weak.** ≥40 month dirs does not validate per-partition non-emptiness, 3-file presence, or correct date range. Empty/partial partitions pass.
12. **[HIGH, 06-03] odds/payoff snapshot not in the run command.** The pre-integration snapshot step is described but not in the `verify.automated` command, so the "unchanged" proof is unenforceable.
13. **[HIGH, 06-03] graded_stakes 780–880 post-integration is wrong.** Scraped 2022–2026 graded races must push the unified count above the Kaggle-only ~838; the band is internally inconsistent.
14. **[HIGH, 06-03] Date-range check too weak.** `startswith("2024") or startswith("2026")` passes for a single-month corpus.

### Divergent Views

Single reviewer — no divergence. The orchestrator's independent code verification corroborates Codex on all four load-bearing HIGH claims (GRADE_REGEX, convert() overwrite, 8-point skip, poetry) rather than contradicting.

### Orchestrator note on cycle contract

Of the 14 HIGH concerns above, all are newly raised in this cycle (cycle 1, no prior HIGHs). None are partially or fully resolved. The internal plan-checker's prior 3-blocker fixes (run_all_validations signature, atomic write, grep-gated verify) addressed *command-level* correctness but did not surface the four producer-side correctness defects above; the Codex review's repository access caught them.

### Recommended next actions (for `/gsd-plan-phase 6 --reviews`)

Priority order for the replanner:

1. **Introduce a Kaggle-side grade detector** (reuse `flag_crosswalk`'s `_GRADE_REGEX` against the race-symbol / race-name field) so D-01 actually yields a graded count near the claimed ~838, and recompute the unified-target band (Kaggle-graded + scraped-graded, not a fixed 780–880).
2. **Prevent `convert()` from clobbering odds/payoff.** Either restrict the Kaggle regen to race/entry/result only, or snapshot+restore odds/payoff around the call (checksum assertion).
3. **Make `run_all_validations` actually run 8 checks** by supplying `source_counts` and `source_stats` computed from the source CSVs before regeneration.
4. **Replace every `poetry run …`** with `python -m pytest …` / `python -c …` (repo is setuptools).
5. **Make `integrate_standard_layer` idempotent** by reading Kaggle rows from a stable, separate path (e.g. `data/standard/kaggle/{table}.parquet`) or a pre-merge snapshot dir, never from the output path.
6. **Add corpus-level transactionality** (write all three to a tmp dir, validate, then swap).
7. **Split test classes / use markers** so hermetic tests are not gated by the scraped-data autouse skip; replace the "does-not-raise" FK test with an actual `validate_integrity`-backed assertion that raises on orphan FKs.
8. **Add column-set equality assert before `reindex`** to catch schema drift loudly.
9. **Strengthen Plan 06-03 preflight**: per-partition 3-file presence, non-empty, valid date; PK-set union == output unique PK count; odds/payoff checksum pre+post in the actual `verify.automated` command.
10. **Resolve the 2015–2024 vs 2015–2026/5 scope**: update ROADMAP/REQUIREMENTS or add an explicit period filter.
11. **Resolve `race_date` dtype contract**: CONTEXT says datetime, code says string — pick one and align.

---

## CYCLE_SUMMARY

CYCLE_SUMMARY: current_high=14

## Current HIGH Concerns

- **[06-01] D-01 GRADE_REGEX gap** — Kaggle converter has no grade-detection path; deleting `(国際)` mapping collapses `graded_stakes` to near-zero, the 780–880 acceptance band is unreachable. Verified.
- **[06-01] D-05 violation via `convert()`** — regenerating via `convert()` overwrites `odds_trifecta.parquet` and `payoff.parquet`, destroying the Phase 5 seed. Verified.
- **[06-01] 8-point verification is ~4-5 checks** — `run_all_validations` skips row-count/null-rate/distribution when `source_counts`/`source_stats` are None; the plan omits both. Verified.
- **[all] `poetry run` commands fail** — repo uses setuptools, `poetry` not installed; every test/verify command in all 3 plans will error at invocation. Verified.
- **[06-02] Non-idempotent integration** — `integrate_standard_layer` reads and writes `standard/{table}.parquet`; second run double-merges Kaggle rows → all-scraped-PK-duplicate abort.
- **[06-02] No corpus-level transactionality** — per-file atomic write leaves a mixed-generation corpus if entry/result fail after race succeeds.
- **[06-02] autouse skip gate swallows hermetic tests** — class-level `_require_scraped_data` skips the fast-path tests the plan says should not be gated.
- **[06-02] Referential-integrity test is a no-op** — "does not raise" on valid data passes without any FK validation in the integration module.
- **[06-02] `reindex()` silently masks schema drift** — extra columns dropped, missing columns filled with NA; success criterion #2 can pass spuriously.
- **[06-03] D-06 pre-task not done** — real corpus is `data/standard/scraped/202306` only (5 races); plan cannot complete until the full scrape runs. Verified by reviewer.
- **[06-03] Month-count gate is weak** — ≥40 month dirs does not validate per-partition non-emptiness, 3-file presence, or date correctness.
- **[06-03] odds/payoff snapshot not in run command** — the pre-integration snapshot is described but absent from `verify.automated`, so the "unchanged" proof is unenforceable.
- **[06-03] graded_stakes 780–880 post-integration is wrong** — scraped 2022–2026 graded races push the unified count above the Kaggle-only ~838; internally inconsistent.
- **[06-03] Date-range check too weak** — `startswith("2024") or startswith("2026")` passes for a single-month corpus.
