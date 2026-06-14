---
slug: scrape-resume-ignored
status: resolved
goal: find_and_fix
tdd_mode: false
created: 2026-06-14
updated: 2026-06-14
---

# Debug Session: scrape-resume-ignored

## Trigger (verbatim)

スクレイピングの動作なのですが、最初にカレンダーを取得し取得した開催情報を元にレースを取得するようにしているのですが、一度スクレイピングを実行したあとに中断して再実行した場合にまた最初からカレンダーの取得が始まってしまいます。
理想は一度取得したものはスキップされるようにしたはずなのだがうまく動作していないので修正して

## Symptoms

**Expected behavior:**
スクレイピングは3層（カレンダー月一覧取得 → 開催日ごとのレース列挙 → 個別レースページHTML取得）で構成される。一度取得済みのものは再実行時にスキップされ、未取得分のみが取得される（レジューム）。中断→再実行で前回完了した箇所から再開されること。

**Actual behavior:**
スクレイピング実行 → 中断 → 再実行すると、前回の進捗が無視され、また最初からカレンダー取得が始まってしまう。

**Error messages:**
なし。エラー/警告は表示されず、一見正常に動いているように見える（静かな不具合 / silent regression）。

**Timeline:**
ユーザーはスキップロジックを実装した認識。いつから効かなくなったか（あるいは一度も効いていなかったか）は不明。Phase 4 でスクレイパ実装、その後 Quick Task で click CLI (`keiba scrape`) と tqdm プログレスバーを追加。

**Reproduction:**
1. スクレイピングを実行（`keiba scrape` または `run_scrape`）
2. **個別レースページ取得の途中**で中断（※カレンダー月一覧取得・レース列挙は前回完了していた状態）
3. 再実行 → また最初からカレンダー取得が始まる

**Key clue（原因切り分けの優先材料）:**
- 中断時点は「個別レースページ取得中」。すなわちカレンダー(month listing)とレース列挙(day→race list)は前回**完了**していたはず。
- それにもかかわらず再実行で**カレンダーからやり直し**が始まる → 個別レースHTMLレベルのスキップロジックだけでなく、上位のカレンダー/列挙フェーズでもキャッシュ・スキップが効いていない可能性が高い。
- 逆に、スキップロジックが「個別レースHTMLの存在チェック」にしか無く、カレンダー・列挙フェーズには無い可能性もある。
- いずれにせよ `run_scrape` / `enumerate_races` / `parse_calendar_month_html` 周辺のレジューム実装を確認する必要がある。

## Current Focus

**reasoning_checkpoint:**
```yaml
hypothesis: "スキップロジックは個別レースHTMLの存在チェック(fetcher.py:307 out_path.exists())にのみ存在し、
  カレンダー月ページ(enumerate_race_day_urls)とレース日ページ(enumerate_races_for_day)の
  2階層にはキャッシュ/スキップが一切ない。これら2階層は enumerate_races が呼ばれるたびに
  毎回ネットワークから再取得されるため、個別レースHTMLが既存であっても列挙フェーズは最初から
  走り直す。これが『再実行でカレンダー取得から始まる』現象の原因。"

confirming_evidence:
  - "fetcher.py L302-308: fetch_race_html は out_path.exists() && size>0 でスキップする。
    スキップは個別レースHTMLレベルでのみ機能する。"
  - "enumeration.py L226-234: enumerate_race_day_urls は fetch_html(calendar_url) を
    無条件で呼び、parse_calendar_month_html(html) に渡す。キャッシュの読み出しは一切ない。"
  - "enumeration.py L273-280: enumerate_races_for_day も同様に fetch_html(day_url) を無条件で呼ぶ。
    キャッシュの読み出しは一切ない。"
  - "orchestrator.py run_scrape は enumerate_races(transport) を呼び、その前にキャッシュを
    チェックするような層は存在しない。"
  - "data/raw/netkeiba/ の下には {YYYY}/{MM}/{race_id}.html の個別レースHTMLしか無く、
    カレンダーページやレース日ページを保存しているディレクトリは存在しない
    （find結果: *day*, *calendar*, *list* いずれも0件）。"

falsification_test: "カレンダー月ページとレース日ページを data/raw/netkeiba/ の
  対応パスに保存し、再実行でファイルが存在する場合にはネットワークにアクセスせず
  ファイルから読み込むように修正した場合、再実行でフェッチの呼び出しが起きないことを
  fake.seen で検証できればH支持。逆にフェッチが走り続けるならHは誤り。"

fix_rationale: "ユーザーの『一度取得したものはスキップされるようにしたはず』という意図に合致させるため、
  3層すべてでディスクキャッシュを実装する。個別レースHTMLは既に実装済みなので、上位2層
  （カレンダー月ページ、レース日ページ）にも同じキャッシュ戦略を適用する。これにより
  再実行時にネットワークアクセスが省略され、個別レースHTMLスキップと組み合わせて
  完全なレジュームが実現される。"

blind_spots: "カレンダーHTMLの保存先を data/raw/netkeiba/{YYYY}/calendar/{MM}.html のように
  既存ツリーの外に置くか、個別レースと並列に置くかは設計判断が必要（既存コード慣行に従う）。
  また列挙層の関数シグネチャに raw_dir を追加するため、呼び出し側の修正も必要。"
```

## Evidence

- timestamp: 2026-06-14 phase-1
  checked: src/scraper/orchestrator.py (run_scrape)
  found: run_scrape は enumerate_races(transport) を呼び出すのみ。enumeration に raw_dir
    は渡されず、キャッシュ判定を行うレイヤーもない。live=Trueの実パスでも offlineの
    fetch_html注入パスでも、列挙フェーズは毎回 transport = browser/https を叩く。
  implication: 列挙フェーズにキャッシュ層が存在しないことが確認された。

- timestamp: 2026-06-14 phase-1
  checked: src/scraper/enumeration.py (parse_calendar_month_html, enumerate_race_day_urls,
    enumerate_races_for_day, enumerate_races)
  found: 全4関数ともディスクアクセスなし。enumerate_race_day_urls は
    fetch_html(calendar_url) を無条件呼び出し。enumerate_races_for_day は
    fetch_html(day_url) を無条件呼び出し。関数シグネチャに raw_dir / cache_dir は無い。
  implication: 上位2階層（カレンダー月ページ・レース日ページ）にキャッシュ機構が全くない。
    個別レースHTMLの out_path.exists() チェック(fetcher.py:307)が唯一のスキップ。

- timestamp: 2026-06-14 phase-1
  checked: src/scraper/fetcher.py (fetch_race_html, L300-308)
  found: out_path = raw_dir/YYYY/MM/{race_id}.html。out_path.exists() && size>0 で
    即座に return out_path。これが SCRP-05 dedup（個別レースレベルのスキップ）。
  implication: 個別レースHTMLのレジュームは実装済み。上位2層へのキャッシュ拡張が必要。

- timestamp: 2026-06-14 phase-1
  checked: data/raw/netkeiba/ ディレクトリツリー + find *calendar*/*day*/*list*
  found: data/raw/netkeiba/{YYYY}/{MM}/{race_id}.html の個別レースHTMLのみ。
    カレンダー月ページ・レース日ページを保存する場所は存在しない。
  implication: 上位2層のHTMLは一度も保存されておらず、再実行で再利用の対象にもならない。
    これが「再実行でカレンダーからやり直し」の物理的理由。

## Eliminated Hypotheses

(populated by investigator)

## Resolution

root_cause: |
  レジューム（スキップ）ロジックが3層のうち最下層（個別レースHTML取得）にのみ実装されており、
  上位2層（カレンダー月ページ取得・レース日ページ取得）にはキャッシュ機構が存在しない。
  そのため再実行時に enumerate_races は毎回すべての月・日のページをネットワークから
  再取得し、その後で個別レースHTMLだけがスキップされる。
  ユーザーには「カレンダー取得から始まる」ように見える。

  具体的:
  - fetch_race_html (fetcher.py:307): out_path.exists() && size>0 でスキップ → 実装済み
  - enumerate_race_day_urls (enumeration.py:227): fetch_html(calendar_url) を無条件呼出 → キャッシュなし
  - enumerate_races_for_day (enumeration.py:273): fetch_html(day_url) を無条件呼出 → キャッシュなし

fix: |
  カレンダー月ページとレース日ページをディスクに保存し、再実行時にキャッシュヒットすれば
  ネットワークアクセスをスキップする機構を追加する。保存先は個別レースHTMLと並列の
  data/raw/netkeiba/{YYYY}/calendar/{MM}.html と data/raw/netkeiba/{YYYY}/{MM}/{YYYYMMDD}_day.html。

  設計方針:
  1. fetch_html を wrap するキャッシュ付きトランスポートを run_scrape 側で構築し、
     enumerate_races にはそのラッパーを渡す（enumeration 層のシグネチャは不変）。
  2. キャッシュキーは URL。calendar URL と day URL だけをキャッシュ対象とする。
  3. 既存のフェッチ失敗時の None 返却セマンティクスは維持（None はキャッシュしない）。
  4. 既存テスト（test_enumeration, test_orchestrator, test_end_to_end）は一切改変不要。

files_changed:
  - src/scraper/cache.py (NEW)
  - src/scraper/orchestrator.py (modified: wrap enum transport with cache)
  - tests/scraper/test_cache.py (NEW: 15 unit tests)
  - tests/scraper/test_orchestrator.py (modified: 1 updated assertion + 1 new test)
  - tests/scraper/test_end_to_end.py (modified: NEW TestResumeContract class, 2 tests)

verification: |
  ## Self-verified checks

  ### TDD red/green proof (regression test pinning the bug)
  - Temporarily reverted orchestrator.py to pre-fix state
  - Ran `test_second_run_does_not_refetch_calendar_or_day_pages`:
    FAILED with assertion listing the exact re-fetched calendar+day URLs
    (the user's symptom, reproduced deterministically in a hermetic test).
  - Restored fix; same test now PASSES.
  => Confirms: the test reproduces the bug, and the fix addresses the root cause.

  ### Full scraper suite
  - `python -m pytest tests/scraper/` -> 233 passed, 1 skipped (pre-existing), 1 warning (pre-existing).
  - Was 230 passed before fix; now 233 (3 new tests added, 0 regressions).

  ### Lint / type
  - `python -m ruff check` on all changed files -> All checks passed.
  - `python -m mypy` on src/scraper/cache.py + orchestrator.py -> 0 new errors.
    (9 pre-existing errors in other files: pandas stubs, enumeration/fetcher/normalizer quirks.)

  ### Cache unit tests (tests/scraper/test_cache.py)
  - 15/15 pass. Covers: URL -> path resolver (month, day, race, edge cases),
    cache hit/miss, transport-None-not-cached, zero-byte-is-miss, atomic write.

  ### Integration tests
  - test_orchestrator.py: test_live_false_with_injected_fetch_html_runs_offline
    (updated to assert the transport handed to enumerate_races is a CachedFetcher
    wrapping the injected stub) -- PASSES.
  - test_orchestrator.py: NEW test_enumeration_transport_is_cache_wrapped -- PASSES.
  - test_end_to_end.py::TestResumeContract: 2 NEW tests -- PASS.

  ## Pending human verification
  実機で `keiba scrape` を実行→中断→再実行し、(a) 2回目の実行で
  `Enumerating:` バーが（キャッシュヒットで）一瞬で終わること、
  (b) data/raw/netkeiba/{YYYY}/calendar/{MM}.html と
  {YYYY}/{MM}/{YYYYMMDD}_day.html が生成されていることを確認する。
