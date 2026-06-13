# Golden netkeiba HTML fixtures

This directory holds authentic netkeiba race-result HTML pages captured by
the user via Playwright (Plan 04-04 Task 3 checkpoint). These fixtures are
the contract for the parser tests in `tests/scraper/test_parser.py`
(`TestParseRaceHtmlGolden`) and the Plan 06 end-to-end suite.

## How to capture (user action)

For each target race below:

1. Open `https://db.netkeiba.com/race/{race_id}/` in a browser (or run the
   Plan 03 Playwright session script).
2. Save Page Source (UTF-8) as `{race_id}.html` in THIS directory.
3. Commit with a message naming the diversity axis covered.

Rate-limit yourself to 1-2 seconds between page loads.

## Target diversity axes (HIGH #9)

1. A 2022 中山 flat race (maiden or allowance) — base case.
2. A 2023 阪神 graded stakes (G1/G2/G3) — grade + `(国際)(特指)(ハンデ)` flags.
3. A 2024 東京 or 中京 dirt race — `ダート` surface branch.
4. A race with a cancelled/scratched runner (着順 = 取 or 中) — finish_note.
5. (Optional) An obstacle race — obstacle detection (parser emits it;
   normalizer filters).

Minimum: 3 fixtures covering (base flat, graded, dirt). Capture 5 if
possible.

## Status

Placeholder. No `.html` files committed yet — awaiting the Task 3 checkpoint
resolution.
