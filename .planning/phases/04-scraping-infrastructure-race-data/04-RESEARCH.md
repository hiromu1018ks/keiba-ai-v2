# Phase 4: Scraping Infrastructure & Race Data - Research

**Researched:** 2026-06-13
**Domain:** Web scraping / HTML parsing / data normalization (Python)
**Confidence:** MEDIUM

## Summary

Phase 4 builds a fetch/parse/normalize pipeline to scrape 2022-2026 JRA race results from netkeiba (db.netkeiba.com) and convert them to standard-layer Parquet matching the same schema as the existing Kaggle data (Phase 2 output). The pipeline uses Playwright for HTML fetching (confirmed in CONTEXT.md D-02), saves raw HTML to `data/raw/netkeiba/{YYYY}/{MM}/{race_id}.html}`, then parses with BeautifulSoup4 + lxml, and normalizes to the existing RaceSchema/EntrySchema/ResultSchema format.

netkeiba is the original data source for the Kaggle dataset, so schema compatibility is expected. The CONTEXT.md confirms (D-09) that all standard schema fields are obtainable from netkeiba race result pages, verified via Playwright investigation of actual 2022 races. Key technical challenges include: (1) netkeiba's anti-scraping measures (Playwright mitigates this by rendering like a real browser), (2) race condition text parsing to derive 20 race_flag fields, (3) handling edge cases like horse weight format `456(+4)`, scratched/withdrawn entries, and non-standard finish positions.

**Primary recommendation:** Build a three-module pipeline (`fetcher.py`, `parser.py`, `normalizer.py`) under `src/scraper/`, following the specification's fetch/parse/normalize separation pattern. Install Playwright + BS4 + lxml as new dependencies. Reuse existing schemas from `src/schemas/` and follow the Kaggle converter's filter-split-transform-write-audit pattern.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** netkeiba (db.netkeiba.com) center. Race result page provides race/entry/result data in one page.
- **D-02:** Playwright for HTML fetching -> raw file save -> BS4 + lxml for parsing. httpx NOT used. Playwright from the start.
- **D-03:** All standard schema fields obtainable from netkeiba race result page (verified via Playwright investigation).
- **D-04:** Calendar page enumeration strategy: month -> race days -> races (3-level).
- **D-05:** Scraping period: 2022-01 through 2026-05-31 (extended from ROADMAP's "2022-2024").
- **D-06:** Raw HTML directory: `data/raw/netkeiba/{YYYY}/{MM}/`
- **D-07:** Filename: `{race_id}.html` (e.g., `202206010101.html`)
- **D-08:** Dedup by race_id: skip if HTML file already exists (SCRP-05).
- **D-09:** No schema gaps -- all standard fields obtainable from netkeiba.
- **D-10:** Race flags derived from race condition text via regex parsing (e.g., `(ハンデ)` -> race_flag_handicap).
- **D-11:** meeting_num from race header `1回中山` pattern.
- **D-12:** region from trainer column `[東]`/`[西]` prefix.
- **D-13:** prize_money from result table prize column.

### Claude's Discretion
- Race condition text -> race_flag regex patterns (concrete implementation)
- netkeiba HTML DOM-based BS4 parse implementation
- Rate limiting interval (1-2 seconds)
- Error handling details (retry/skip/logging on fetch failure)
- Calendar page URL patterns and parsing
- Scratch/withdrawal/DC special case handling

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SCRP-01 | fetch/parse/normalize/feature separated scraping infrastructure | Three-module pipeline design (fetcher/parser/normalizer), spec section 13 pattern |
| SCRP-02 | Fetch 2022+ JRA race result/entry HTML and save raw | Playwright fetcher with calendar enumeration, raw HTML save to `data/raw/netkeiba/{YYYY}/{MM}/{race_id}.html` |
| SCRP-03 | Parse saved HTML and convert to standard format | BS4+lxml parser extracting race/entry/result data, normalizer producing Parquet matching Phase 1-2 schemas |
| SCRP-05 | Duplicate page fetch prevention | File-existence check on `{race_id}.html` before fetching (D-08) |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Calendar enumeration (fetch) | Local CLI | -- | Playwright runs locally, enumerates netkeiba calendar pages |
| HTML fetch & raw save | Local CLI | -- | Fetches HTML from netkeiba, saves to disk |
| HTML parsing (BS4) | Local CLI | -- | Parses saved HTML into structured dicts |
| Data normalization | Local CLI | -- | Converts parsed dicts to standard-layer DataFrames |
| Parquet output | Local CLI | -- | Writes standard Parquet files to `data/standard/` |
| Rate limiting | Local CLI | -- | Sequential requests with sleep intervals |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| playwright | 1.60.0 | Browser-based HTML fetching | D-02 locks Playwright as fetch method. Handles JS rendering, anti-bot measures. [VERIFIED: PyPI registry] |
| beautifulsoup4 | 4.15.0 | HTML parsing | D-02 locks BS4 + lxml for parsing. Industry standard HTML parser. [VERIFIED: PyPI registry] |
| lxml | 6.1.1 | Fast HTML parser backend for BS4 | D-02 locks lxml. Significantly faster than html.parser. [VERIFIED: PyPI registry] |
| pydantic | 2.13.4 | Schema validation (existing) | Already installed. Used for schema definitions in `src/schemas/`. [VERIFIED: pip show] |
| pandas | 2.3.3 | DataFrame processing (existing) | Already installed. Used for Parquet I/O. [VERIFIED: pip show] |
| pyarrow | 24.0.0 | Parquet read/write (existing) | Already installed. Parquet engine. [VERIFIED: pip show] |
| loguru | 0.7.3 | Structured logging (existing) | Already installed. Project-wide logging standard. [VERIFIED: pip show] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| time (stdlib) | -- | Rate limiting sleep | Between each page fetch |
| re (stdlib) | -- | Race condition text parsing | Extract race_flag values from condition text |
| pathlib (stdlib) | -- | Path handling | File/directory operations for raw HTML |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Playwright | httpx + requests | D-02 locks Playwright. httpx rejected: netkeiba has anti-scraping measures, Playwright renders like real browser |
| BS4 + lxml | direct regex / string parsing | BS4 is more robust against HTML structure variations. lxml parser is fast and tolerant |
| Sequential fetch | async concurrent fetch | Specification prohibits mass parallel fetching. Sequential is simpler and safer |

**Installation:**
```bash
pip install playwright beautifulsoup4 lxml
playwright install chromium
```

**Note:** These must be added to `pyproject.toml` dependencies. Currently they are NOT listed there.

**Version verification:**
```bash
pip index versions playwright    # 1.60.0 (latest)
pip index versions beautifulsoup4  # 4.15.0 (latest)
pip index versions lxml          # 6.1.1 (latest)
```

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| playwright | PyPI | ~5 yrs | ~4M/mo | github.com/microsoft/playwright | OK | Approved |
| beautifulsoup4 | PyPI | ~18 yrs | ~40M/mo | crummy.com/software/BeautifulSoup | OK | Approved |
| lxml | PyPI | ~18 yrs | ~30M/mo | github.com/lxml/lxml | OK | Approved |

**Packages removed due to SLOP verdict:** none
**Packages flagged as suspicious [SUS]:** none (the seam's SUS verdicts were false positives due to missing PyPI metadata -- all three packages are well-established, verified directly on registry)

*All packages verified via `pip index versions` on PyPI. Playwright by Microsoft, BS4 by Leonard Richardson, lxml by Stefan Behnel -- all long-established, widely-used packages.*

## Architecture Patterns

### System Architecture Diagram

```
Calendar Enumerate          Fetch Pipeline           Parse Pipeline           Normalize Pipeline
=================          ==============           ==============           ==================

+------------------+      +------------------+      +------------------+      +------------------+
| Calendar Page    |----->| race_id list     |----->| For each HTML:   |----->| Parsed data      |
| YYYY/MM -> days  |      |                  |      |   Read from disk |      | -> race dict     |
| -> race_ids      |      | Dedup check:     |      |   BS4 + lxml     |      | -> entry list    |
|                  |      | skip if .html    |      |   parse          |      | -> result list   |
+------------------+      | already exists   |      +------------------+      +------------------+
                          +-------+----------+                                        |
                                  |                                                  v
                          +-------+----------+                              +------------------+
                          | Playwright fetch  |                              | DataFrame build  |
                          | page.goto(url)    |                              | Schema alignment |
                          | page.content()    |                              | audit_leakage()  |
                          | save to disk      |                              | Parquet write    |
                          +-------------------+                              +------------------+
                                  |                                                  |
                                  v                                                  v
                          data/raw/netkeiba/                            data/standard/
                          {YYYY}/{MM}/{race_id}.html                    race/entry/result.parquet
```

### Recommended Project Structure
```
src/
├── scraper/                # NEW: Scraping infrastructure
│   ├── __init__.py         # Package exports
│   ├── fetcher.py          # Playwright-based HTML fetcher + calendar enumerator
│   ├── parser.py           # BS4+lxml HTML parser -> structured dicts
│   └── normalizer.py       # Dict -> standard-layer DataFrame + Parquet output
├── pipeline/               # EXISTING: Kaggle data pipeline
├── schemas/                # EXISTING: Standard schema definitions
└── ...
data/
├── raw/
│   └── netkeiba/           # NEW: Scraped HTML files
│       ├── 2022/
│       │   ├── 01/
│       │   │   ├── 202201010101.html
│       │   │   └── ...
│       │   └── ...
│       └── ...
├── standard/               # EXISTING: Standard Parquet output
└── feature/                # EXISTING: Feature Parquet output
tests/
├── scraper/                # NEW: Scraper tests
│   ├── __init__.py
│   ├── conftest.py         # Shared fixtures (sample HTML, sample parsed data)
│   ├── test_fetcher.py     # Fetcher tests (mock Playwright)
│   ├── test_parser.py      # Parser tests (with sample HTML fixtures)
│   └── test_normalizer.py  # Normalizer tests (dict -> DataFrame validation)
```

### Pattern 1: Fetcher with File-Based Dedup (SCRP-01, SCRP-05)
**What:** Playwright fetches HTML only if the target file does not already exist.
**When to use:** Every race page fetch.
**Example:**
```python
# Source: [ASSUMED] based on CONTEXT.md D-08 and spec section 13
from pathlib import Path
from playwright.sync_api import sync_playwright
import time

def fetch_race_html(
    race_id: str,
    raw_dir: Path = Path("data/raw/netkeiba"),
    rate_limit_seconds: float = 2.0,
) -> Path:
    """Fetch race HTML from netkeiba, skip if already downloaded."""
    race_date_part = race_id[:8]  # YYYYPPCC -> need YYYY/MM from race_id
    year = race_id[:4]
    month = race_id[4:6]
    out_dir = raw_dir / year / month
    out_path = out_dir / f"{race_id}.html"

    # SCRP-05: Dedup -- skip if file exists
    if out_path.exists() and out_path.stat().st_size > 0:
        return out_path

    out_dir.mkdir(parents=True, exist_ok=True)
    url = f"https://db.netkeiba.com/race/{race_id}/"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        html = page.content()
        browser.close()

    out_path.write_text(html, encoding="utf-8")
    time.sleep(rate_limit_seconds)
    return out_path
```

### Pattern 2: Calendar-Based Race Enumeration (D-04)
**What:** Enumerate all races by crawling calendar pages month by month.
**When to use:** Before fetching, to build the full list of race_ids to fetch.
**Example:**
```python
# Source: [ASSUMED] based on CONTEXT.md D-04 and canonical refs
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def enumerate_race_ids(
    start_year: int = 2022,
    start_month: int = 1,
    end_year: int = 2026,
    end_month: int = 5,
) -> list[str]:
    """Enumerate all JRA race IDs via calendar pages."""
    race_ids: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        year, month = start_year, start_month
        while (year, month) <= (end_year, end_month):
            ym = f"{year}{month:02d}"
            url = f"https://db.netkeiba.com/race/calendar/{ym}/"
            page.goto(url, wait_until="networkidle")
            html = page.content()
            soup = BeautifulSoup(html, "lxml")

            # Parse calendar page to extract race day links
            # Each day links to a race list page
            # Each race list page has individual race links
            # Extract race_id from links like /race/202206010101/
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if "/race/" in href and href.count("/") >= 3:
                    # Extract race_id from URL
                    rid = href.split("/race/")[-1].strip("/")
                    if len(rid) == 12 and rid.isdigit():
                        race_ids.append(rid)

            # Advance month
            month += 1
            if month > 12:
                month = 1
                year += 1
            time.sleep(1.0)

        browser.close()

    return sorted(set(race_ids))
```

### Pattern 3: Race Flag Derivation from Condition Text (D-10)
**What:** Parse race condition text like `4歳以上オープン (国際)(特指)(ハンデ)` to derive race_flag_* fields.
**When to use:** During normalization of parsed race data.
**Example:**
```python
# Source: [ASSUMED] based on CONTEXT.md D-10 and D-03 investigation
import re

def parse_race_flags(race_condition: str) -> dict[str, bool | None]:
    """Derive race_flag_* fields from race condition text."""
    flags: dict[str, bool | None] = {}

    # Parenthetical modifiers
    flags["race_flag_handicap"] = "(ハンデ)" in race_condition
    flags["race_flag_mare_only"] = "(牝)" in race_condition or "牝" in race_condition.split("(")[0].split()[-1:]
    flags["race_flag_age_restricted"] = "(馬齢)" in race_condition
    flags["race_flag_graded_stakes"] = "(国際)" in race_condition
    flags["race_flag_special_weight"] = "(特指)" in race_condition or "(別定)" in race_condition
    flags["race_flag_bonus_weight"] = "(定量)" in race_condition
    flags["race_flag_apprentice"] = "(見習騎手)" in race_condition
    flags["race_flag_condition_race"] = any(
        x in race_condition for x in ["(指)", "[指]", "(抽)", "[抽]"]
    )
    flags["race_flag_allowance"] = any(
        x in race_condition for x in ["(混)", "(市)", "九州産馬"]
    )

    # Class from text
    flags["race_flag_maiden"] = "未勝利" in race_condition or "新馬" in race_condition
    flags["race_flag_open"] = "オープン" in race_condition
    flags["race_flag_stakes"] = bool(re.search(r"(GI|GII|GIII|重賞)", race_condition))

    # Grade detection from header or condition
    grade_match = re.search(r"(GI|GII|GIII|G1|G2|G3)", race_condition)
    if grade_match:
        flags["race_flag_graded_stakes"] = True

    # Fields not easily derivable from text -- set to None
    for field in [
        "race_flag_colt_only", "race_flag_gelding_only",
        "race_flag_stallion_only", "race_flag_amateur",
        "race_flag_female_jockey", "race_flag_young_horse",
        "race_flag_listed",
    ]:
        if field not in flags:
            flags[field] = None

    return flags
```

### Pattern 4: HTML Parser for netkeiba Race Results
**What:** Parse netkeiba race result page HTML using BS4 + lxml.
**When to use:** The `parse` step of the pipeline.
**Example:**
```python
# Source: [ASSUMED] based on agusblog code + CONTEXT.md canonical refs
from bs4 import BeautifulSoup
from pathlib import Path

def parse_race_html(html_path: Path) -> dict:
    """Parse a saved netkeiba race result HTML into structured data."""
    html = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")

    result = {"race": {}, "entries": [], "results": []}

    # --- Race header ---
    # Race info from <p class="smalltxt">: "2022年01月05日 1回中山1日目 3歳未勝利 (馬齢)"
    smalltxt = soup.find("p", class_="smalltxt")
    if smalltxt:
        text = smalltxt.get_text(strip=True)
        # Parse date, meeting, condition from text
        # ... (regex extraction per D-10/D-11)

    # Race course info from <span> or <div>:
    # "ダ右1200m / 天候 : 晴 / ダート : 良 / 発走 : 09:55"
    # ... parse surface, direction, distance, weather, condition, start_time

    # Race name from <h1>
    h1_tags = soup.find_all("h1")
    # ... extract race_name, grade

    # --- Result table ---
    table = soup.find("table", class_="race_table_01 nk_tb_common")
    if not table:
        table = soup.find("table", class_="race_table_01")

    if table:
        rows = table.find_all("tr")[1:]  # Skip header
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 10:
                continue
            entry = {
                "finish_position": cols[0].get_text(strip=True),
                "bracket_num": cols[1].get_text(strip=True),
                "horse_number": cols[2].get_text(strip=True),
                "horse_name": cols[3].get_text(strip=True),
                "sex_age": cols[4].get_text(strip=True),  # e.g. "牡4"
                "weight_assigned": cols[5].get_text(strip=True),
                "jockey": cols[6].get_text(strip=True),
                "finish_time": cols[7].get_text(strip=True) if len(cols) > 7 else None,
                "margin": cols[8].get_text(strip=True) if len(cols) > 8 else None,
                # ... more columns
            }
            # ... parse further and append

    return result
```

### Anti-Patterns to Avoid
- **Fetching and parsing in one step:** The spec (section 13) requires fetch and parse to be separate. Fetch saves HTML, parse reads from saved HTML. Never parse directly from a live response.
- **Mass parallel fetching:** The spec explicitly prohibits this. Use sequential fetching with rate limiting.
- **Skipping the calendar enumeration:** Guessing race_ids by brute-forcing course/meeting/day/race numbers generates many 404s. Use calendar pages to enumerate real races only.
- **Re-fetching existing HTML:** Always check file existence first (D-08, SCRP-05).
- **Hardcoding HTML structure:** netkeiba's HTML may change. Use flexible selectors (class names, relative positioning) rather than absolute XPath indices.
- **Ignoring encoding:** netkeiba uses EUC-JP in some responses. Playwright handles this automatically, but if reading saved HTML directly, ensure UTF-8 encoding is used.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTML parsing | Custom regex-based HTML parser | BS4 + lxml | HTML is irregular; BS4 handles malformed HTML, nested tables, encoding issues |
| Browser automation | Raw HTTP requests with cookie management | Playwright | netkeiba has anti-scraping measures; Playwright renders JS and looks like a real browser |
| Rate limiting | Custom thread pool + semaphore | Sequential + time.sleep() | Spec prohibits parallel fetching; simple sequential approach is correct |
| Data validation | Manual column checking | Pydantic schemas + audit_leakage() | Existing schemas in `src/schemas/` define the contract; audit function detects data leakage |
| Parquet writing | Custom binary format writer | pandas to_parquet + pyarrow | Follows Phase 2 pattern; handles compression, types, compatibility |

**Key insight:** The normalization step reuses the same schema definitions from Phase 1 and the same Parquet output pattern from Phase 2. The only new code is the fetcher (Playwright) and parser (BS4). The normalizer is structurally similar to `kaggle_converter.py` but with different input parsing.

## Common Pitfalls

### Pitfall 1: netkeiba Anti-Scraping Measures
**What goes wrong:** netkeiba has implemented countermeasures against scraping. Using simple HTTP requests (requests/httpx) may return empty pages, CAPTCHA pages, or rate-limited 403 errors.
**Why it happens:** netkeiba detects automated access patterns.
**How to avoid:** Use Playwright (D-02) which renders pages like a real browser. Use rate limiting (2-3 second delays). Use headless Chromium with realistic viewport. [CITED: agusblog.net states "netkeibaの対策により現在はスクレイピングが禁止"]
**Warning signs:** Empty HTML responses, CAPTCHA pages, consistent 403 errors.

### Pitfall 2: Horse Weight Parsing Edge Cases
**What goes wrong:** Horse weight column shows `456(+4)`, `478(-2)`, `472(0)` but debut horses may have no weight (`計不` text).
**Why it happens:** First-time starters don't have prior weight data.
**How to avoid:** Use regex to extract weight and change: `re.match(r'(\d+)\(([+-]?\d+)\)', text)`. Handle non-numeric values by setting both horse_weight and weight_change to None.
**Warning signs:** ValueError when parsing horse weight column.

### Pitfall 3: Race Condition Text Variation
**What goes wrong:** Race condition text format varies significantly: `3歳未勝利`, `4歳以上オープン (国際)(特指)(ハンデ)`, `メイクデビュー中山`, `障害3歳以上未勝利`. Regex patterns may miss edge cases.
**Why it happens:** JRA has many race classes with different naming conventions.
**How to avoid:** Build regex patterns incrementally. Test against known race conditions from CONTEXT.md D-03 examples. Use defensive parsing that defaults to None for unrecognized patterns rather than crashing.
**Warning signs:** All race_flag values are False/None for known graded stakes races.

### Pitfall 4: Scratched/Withdrawn Entry Handling
**What goes wrong:** Entries with 着順 like `取` (scratched), `中` (withdrawn), `失` (disqualified), `除` (removed) have no finish_time, margin, or corner data.
**Why it happens:** These horses did not complete the race.
**How to avoid:** Follow Phase 2's `process_finish_position` pattern -- detect finish notes, set finish_position to None, record the note. This is already handled in `kaggle_converter.py`.
**Warning signs:** ValueError converting non-numeric finish positions to int.

### Pitfall 5: Missing or Changed HTML Structure
**What goes wrong:** netkeiba may change their HTML structure (different class names, table layout) between years.
**Why it happens:** Websites evolve over time. The 2022 structure may differ from 2024.
**How to avoid:** Use flexible BS4 selectors. Log warnings when expected elements are not found. Include HTML structure validation in tests. Save raw HTML for re-parsing without re-fetching (spec section 13).
**Warning signs:** Parser returns empty results for pages that visually contain data.

### Pitfall 6: Calendar Page Parsing Complexity
**What goes wrong:** Calendar pages link to race list pages, which link to individual races. The intermediate page structure may not be straightforward.
**Why it happens:** netkeiba uses a 3-level navigation: calendar -> race day -> individual races.
**How to avoid:** Parse each level separately. Extract links methodically. Handle edge cases like cancelled race days (empty links).
**Warning signs:** Race count much lower than expected (JRA runs ~3000+ flat races per year).

### Pitfall 7: Encoding Issues with Saved HTML
**What goes wrong:** When using requests directly, netkeiba returns EUC-JP encoded content. Playwright handles encoding automatically but the saved UTF-8 HTML may contain mojibake from the original page.
**Why it happens:** Legacy Japanese encoding on netkeiba.
**How to avoid:** Playwright's `page.content()` returns UTF-8. Save with explicit `encoding="utf-8"`. When parsing, read with UTF-8. Test with Japanese text fixtures.
**Warning signs:** Garbled Japanese characters in parsed data.

### Pitfall 8: Playwright Browser Binary Not Installed
**What goes wrong:** `playwright` pip package installs but Chromium binary is not downloaded. Import works but `chromium.launch()` fails.
**Why it happens:** Playwright requires a separate `playwright install chromium` step after pip install.
**How to avoid:** Document the install step clearly. Include it in pyproject.toml or a setup script. Detect missing binary at startup with a clear error message.
**Warning signs:** `BrowserType.launch: Executable doesn't exist` error.

## Code Examples

### Playwright Fetch with Retry and Rate Limiting
```python
# Source: [ASSUMED] based on Playwright Python API + CONTEXT.md D-02
from pathlib import Path
from loguru import logger
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import time

MAX_RETRIES = 3
RATE_LIMIT_SECONDS = 2.0

def fetch_with_retry(
    url: str,
    output_path: Path,
    retries: int = MAX_RETRIES,
) -> bool:
    """Fetch URL via Playwright with retry logic."""
    for attempt in range(retries):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, wait_until="networkidle", timeout=30000)
                html = page.content()
                browser.close()

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(html, encoding="utf-8")
            logger.info(f"Fetched {url} -> {output_path}")
            time.sleep(RATE_LIMIT_SECONDS)
            return True

        except PlaywrightTimeout:
            logger.warning(f"Timeout on attempt {attempt+1}/{retries}: {url}")
        except Exception as e:
            logger.warning(f"Error on attempt {attempt+1}/{retries}: {url} - {e}")

        if attempt < retries - 1:
            wait = RATE_LIMIT_SECONDS * (attempt + 2)
            logger.info(f"Retrying in {wait}s...")
            time.sleep(wait)

    logger.error(f"Failed after {retries} attempts: {url}")
    return False
```

### BS4 Table Parsing for netkeiba Result Table
```python
# Source: [ASSUMED] based on agusblog code patterns + CONTEXT.md canonical refs
from bs4 import BeautifulSoup
from typing import Optional

def parse_horse_weight(text: str) -> tuple[Optional[int], Optional[int]]:
    """Parse horse weight text like '456(+4)', '478(-2)', '472(0)'."""
    import re
    if not text or text in ("計不", "---"):
        return None, None
    match = re.match(r'(\d+)\(([+-]?\d+)\)', text.strip())
    if match:
        return int(match.group(1)), int(match.group(2))
    # Try weight only without change (debut)
    match = re.match(r'(\d+)', text.strip())
    if match:
        return int(match.group(1)), None
    return None, None

def parse_sex_age(text: str) -> tuple[Optional[str], Optional[int]]:
    """Parse sex/age text like '牡4', '牝3', 'セ5'."""
    if not text or len(text) < 2:
        return None, None
    sex_map = {"牡": "牡", "牝": "牝", "セ": "セ"}
    sex = sex_map.get(text[0])
    try:
        age = int(text[1:])
    except ValueError:
        age = None
    return sex, age
```

### Normalizer Following Kaggle Converter Pattern
```python
# Source: [ASSUMED] following src/pipeline/kaggle_converter.py pattern
import pandas as pd
from pathlib import Path
from loguru import logger
from src.schemas.audit import audit_leakage
from src.schemas.race import RaceSchema
from src.schemas.entry import EntrySchema

def normalize_to_parquet(
    parsed_races: list[dict],
    standard_dir: Path = Path("data/standard"),
) -> dict[str, Path]:
    """Convert parsed race data to standard-layer Parquet.

    Follows kaggle_converter.py pattern: build DataFrames, validate, write, audit.
    """
    race_rows, entry_rows, result_rows = [], [], []
    for parsed in parsed_races:
        race_rows.append(parsed["race"])
        entry_rows.extend(parsed["entries"])
        result_rows.extend(parsed["results"])

    race_df = pd.DataFrame(race_rows)
    entry_df = pd.DataFrame(entry_rows)
    result_df = pd.DataFrame(result_rows)

    # Ensure dtype compatibility with existing Kaggle Parquet
    for str_col in ["race_id", "course_code", "race_date"]:
        if str_col in race_df.columns:
            race_df[str_col] = race_df[str_col].astype(str)

    # Audit for leakage (same as kaggle_converter.py step 6)
    audit_leakage([RaceSchema], race_df, "scraped race table generation")
    audit_leakage([EntrySchema], entry_df, "scraped entry table generation")

    # Write Parquet (same engine/compression as kaggle_converter.py)
    standard_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, df in [("race", race_df), ("entry", entry_df), ("result", result_df)]:
        path = standard_dir / f"{name}_scraped.parquet"  # Separate from Kaggle
        df.to_parquet(path, engine="pyarrow", compression="snappy", index=False)
        paths[name] = path
        logger.info(f"Wrote {name}: {len(df)} rows -> {path}")

    return paths
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| requests + EUC-JP decode | Playwright + UTF-8 | 2023+ (anti-scraping) | Playwright needed for reliable access; requests may return empty/403 |
| html.parser backend | lxml backend for BS4 | Long-standing | 3-10x faster HTML parsing |
| Scrapy framework | Playwright + BS4 | 2023+ | Targeted scraping doesn't need Scrapy's complexity |
| Pandas 1.x nullable types | Pandas 2.x nullable types + pyarrow | 2023 | Better Parquet interop, Copy-on-Write |

**Deprecated/outdated:**
- `requests-html`: Largely unmaintained, use Playwright instead
- `requests` + manual EUC-JP decoding for netkeiba: Anti-scraping measures make this unreliable
- `html.parser` BS4 backend: Use `lxml` for speed and robustness

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | netkeiba race result page HTML table class is `race_table_01 nk_tb_common` with td column order matching agusblog article | Pattern 4 | Parser returns wrong data or empty results -- need to verify with actual Playwright fetch during implementation |
| A2 | Calendar page URL pattern is `https://db.netkeiba.com/race/calendar/{YYYYMM}/` | Pattern 2 | Race enumeration fails -- need to verify actual URL structure |
| A3 | Playwright successfully bypasses netkeiba anti-scraping measures (confirmed by CONTEXT.md D-02/D-03 investigation which used Playwright) | Pitfall 1 | Fetching fails at scale -- may need additional measures (headers, delays) |
| A4 | Scraper output should use separate Parquet files (`race_scraped.parquet`) rather than appending to existing Kaggle Parquet | Pattern 4 | Data integration approach changes for Phase 6 -- planner should confirm |
| A5 | race_id format from netkeiba matches the 12-digit format used in Kaggle data (YYYYPPCCDDRR) | Architecture | ID mismatch would break Phase 6 integration |
| A6 | netkeiba race result page contains all data in a single page load (no pagination) | Architecture | May need additional fetch logic for multi-page results |

## Open Questions (RESOLVED)

All four open questions below have been resolved during planning. The Recommendations are kept as historical context; the RESOLVED line cites the concrete plan-level decision that superseded them.

1. **Should scraped Parquet use separate files or append to existing?**
   - What we know: Kaggle data is in `data/standard/race.parquet` etc. Scraped data covers a different time period (2022-2026 vs 2015-2021).
   - What's unclear: Whether to write to `race_scraped.parquet` (separate) or append to `race.parquet` (merged).
   - Recommendation: Write to separate files (`race_scraped.parquet`) -- Phase 6 handles integration. This avoids corrupting existing validated data.
   - **RESOLVED (per 04-05):** Use a partitioned layout `data/standard/scraped/{YYYYMM}/{race,entry,result}.parquet` keyed by `race_date` year-month, NOT a single `race_scraped.parquet` file. This supersedes the recommendation: a single-file write would overwrite prior batches (Codex Review HIGH #8). One file per month per table enables atomic per-partition writes and preserves all prior months. Phase 6 reads the partition directory.

2. **Exact calendar page HTML structure**
   - What we know: URL pattern `https://db.netkeiba.com/race/calendar/{YYYYMM}/` (D-04). Three-level: month -> day -> races.
   - What's unclear: Exact DOM structure of calendar pages for parsing links to race days and individual races.
   - Recommendation: Investigate with Playwright during implementation. Build parser incrementally.
   - **RESOLVED (per Claude's Discretion):** Deferred to implementation. 04-02 Task 1 implements `parse_calendar_month_html` / `parse_race_day_html` as BS4+lxml parsers against the live DOM, accepting an injected `fetch_html` callable so no real browser is needed in tests. The exact selector logic is implementation-time; the contract (`/race/list/{YYYYMMDD}/` day links, `/race/{12-digit}/` race links) is locked in 04-02.

3. **Obstacle race exclusion**
   - What we know: Phase 2 excludes obstacle races (D-01). CONTEXT.md scope says "JRA中央競馬平地レース".
   - What's unclear: How to detect obstacle races from netkeiba HTML (obstacle tag vs race condition text vs course info field).
   - Recommendation: Detect from race condition text ("障害" keyword) or course info field. Filter during normalization.
   - **RESOLVED (per 04-04 + 04-05):** The parser (04-04) sets `obstacle = "障害"` on the race dict when the course-info / condition text contains the "障害" marker; the normalizer (04-05 `normalize_to_parquet`) applies the filter `race_df["obstacle"] == "障害"` and propagates the drop to entries/results, mirroring `kaggle_converter.py` line 89 (`df = df[df["障害区分"] != "障害"]`).

4. **Playwright installation on CI**
   - What we know: Playwright requires `playwright install chromium` after pip install. Not currently in pyproject.toml.
   - What's unclear: Whether CI/CD will need Chromium installation, or if tests should mock Playwright entirely.
   - Recommendation: Mock Playwright in tests. Use saved HTML fixtures for parser tests. Only real fetch during manual execution.
   - **RESOLVED (per Claude's Discretion):** Deferred to implementation. All unit tests in 04-02/04-03/04-05/04-06 mock Playwright (`unittest.mock.patch("src.scraper.fetcher.sync_playwright")`) or use an injected `fetch_html` callable; parser tests use saved golden HTML fixtures (04-04 Task 3 checkpoint). Chromium installation is performed locally in 04-01 Task 2 and recorded in the SUMMARY. An opt-in live smoke test (04-06 `@pytest.mark.live`, gated on `LIVE_SMOKE=1`) covers real fetch during manual execution only.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Runtime | Yes | 3.12.13 | -- |
| Playwright | HTML fetching | No (pip) | -- | Install required: `pip install playwright && playwright install chromium` |
| beautifulsoup4 | HTML parsing | No (pip) | -- | Install required: `pip install beautifulsoup4` |
| lxml | BS4 parser backend | No (pip) | -- | Install required: `pip install lxml` |
| pandas | DataFrame processing | Yes | 2.3.3 | -- |
| pyarrow | Parquet I/O | Yes | 24.0.0 | -- |
| pydantic | Schema definitions | Yes | 2.13.4 | -- |
| loguru | Logging | Yes | 0.7.3 | -- |
| pytest | Testing | Yes | 9.0.3 | -- |

**Missing dependencies with no fallback:**
- Playwright (pip + chromium binary): Required for HTML fetching per D-02
- beautifulsoup4: Required for HTML parsing per D-02
- lxml: Required as BS4 parser backend per D-02

**Missing dependencies with fallback:**
- None

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` testpaths=["tests"] |
| Quick run command | `pytest tests/scraper/ -x -q` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCRP-01 | Fetch/parse/normalize separation | unit | `pytest tests/scraper/test_fetcher.py tests/scraper/test_parser.py tests/scraper/test_normalizer.py -x` | Wave 0 |
| SCRP-02 | HTML fetch and raw save | unit | `pytest tests/scraper/test_fetcher.py::test_fetch_saves_html -x` | Wave 0 |
| SCRP-03 | Parse HTML to standard Parquet | unit | `pytest tests/scraper/test_parser.py tests/scraper/test_normalizer.py -x` | Wave 0 |
| SCRP-05 | Dedup skip existing HTML | unit | `pytest tests/scraper/test_fetcher.py::test_dedup_skips_existing -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/scraper/ -x -q`
- **Per wave merge:** `pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/scraper/__init__.py` -- package init
- [ ] `tests/scraper/conftest.py` -- shared fixtures (sample HTML from actual race, parsed data)
- [ ] `tests/scraper/test_fetcher.py` -- fetch tests (mock Playwright, dedup check)
- [ ] `tests/scraper/test_parser.py` -- parser tests (with saved HTML fixture)
- [ ] `tests/scraper/test_normalizer.py` -- normalizer tests (dict -> DataFrame -> audit)
- [ ] Scraper package: `src/scraper/__init__.py`

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | -- |
| V3 Session Management | no | -- |
| V4 Access Control | no | -- |
| V5 Input Validation | yes | Pydantic schemas validate parsed data before Parquet write |
| V6 Cryptography | no | -- |
| V9 Communication | yes | Playwright uses HTTPS for all netkeiba connections |
| V11 Error Handling | yes | Retry logic with exponential backoff; failed fetches logged not crashed |

### Known Threat Patterns for Web Scraping

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Rate limiting / IP blocking | Denial of Service | Sequential requests with 2s+ delay; retry with exponential backoff |
| HTML injection / malformed content | Tampering | BS4 sanitizes HTML; Pydantic validates output data |
| Data exfiltration via scraping | Information Disclosure | Raw HTML stored locally only; no external transmission; spec says no public sharing |
| Anti-bot detection | Elevation of Privilege | Playwright renders like real browser; headless Chromium with standard viewport |

## Sources

### Primary (MEDIUM confidence)
- Context7 Playwright Python API -- sync_api patterns, page.goto(), page.content(), browser context management
- CONTEXT.md Phase 4 -- all locked decisions D-01 through D-13, verified via Playwright investigation of actual netkeiba pages
- Codebase: `src/schemas/race.py`, `src/schemas/entry.py`, `src/schemas/result.py` -- schema definitions for normalization target
- Codebase: `src/pipeline/kaggle_converter.py` -- conversion pattern to follow
- Codebase: `src/pipeline/validators.py` -- validation patterns to reuse

### Secondary (MEDIUM confidence)
- PyPI registry -- playwright 1.60.0, beautifulsoup4 4.15.0, lxml 6.1.1 verified
- `pip show` output -- pydantic 2.13.4, pandas 2.3.3, pyarrow 24.0.0, loguru 0.7.3 confirmed installed

### Tertiary (LOW confidence)
- [agusblog.net](https://agusblog.net/keiba-ai-scraping/) -- netkeiba HTML structure, table class `race_table_01 nk_tb_common`, column indices. WARNING: article states netkeiba has anti-scraping measures; uses `requests` not Playwright. Code patterns are reference only.
- [Zenn:競馬予想で始める機械学習](https://zenn.dev/dijzpeb/books/848d4d8e47001193f3fb/viewer/02_scraping) -- scraping methodology reference (content paywalled)
- [Playwright Python API docs](https://playwright.dev/python/docs/api/class-page) -- page.content(), wait strategies

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM - Playwright/BS4/lxml are industry standard; versions verified on PyPI; CONTEXT.md D-02 locks the choices
- Architecture: MEDIUM - follows existing codebase patterns (kaggle_converter.py) and specification section 13; calendar enumeration details need implementation-time verification
- Pitfalls: MEDIUM - based on verified netkeiba anti-scraping reports and existing codebase edge case handling patterns

**Research date:** 2026-06-13
**Valid until:** 2026-07-13 (30 days -- stable libraries, netkeiba HTML structure may change)
