# Phase 4: Scraping Infrastructure & Race Data - Pattern Map

**Mapped:** 2026-06-13
**Files analyzed:** 12 new/modified files
**Analogs found:** 12 / 12

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/scraper/__init__.py` | config | -- | `src/pipeline/__init__.py` | exact |
| `src/scraper/fetcher.py` | service | file-I/O | `src/pipeline/kaggle_converter.py` | role-match |
| `src/scraper/parser.py` | service | transform | `src/pipeline/kaggle_converter.py` | role-match |
| `src/scraper/normalizer.py` | service | CRUD | `src/pipeline/kaggle_converter.py` | exact |
| `pyproject.toml` | config | -- | `pyproject.toml` (existing) | exact |
| `tests/scraper/__init__.py` | config | -- | `tests/pipeline/__init__.py` | exact |
| `tests/scraper/conftest.py` | config | -- | `tests/pipeline/conftest.py` | exact |
| `tests/scraper/test_fetcher.py` | test | request-response | `tests/pipeline/test_kaggle_converter.py` | role-match |
| `tests/scraper/test_parser.py` | test | transform | `tests/pipeline/test_kaggle_converter.py` | role-match |
| `tests/scraper/test_normalizer.py` | test | CRUD | `tests/pipeline/test_kaggle_converter.py` | role-match |
| `data/raw/netkeiba/{YYYY}/{MM}/{race_id}.html` | storage | file-I/O | `data/raw/kaggle/` (existing) | exact |
| `data/standard/race_scraped.parquet` (+entry, result) | storage | CRUD | `data/standard/race.parquet` (existing) | exact |

## Pattern Assignments

### `src/scraper/__init__.py` (config)

**Analog:** `src/pipeline/__init__.py` (lines 1-25)

**Package init pattern** -- re-exports key public symbols with `__all__`:

```python
"""Scraping infrastructure package for netkeiba data collection.

Re-exports key fetcher, parser, and normalizer functions for downstream
phases to access via ``from src.scraper import ...``.
"""

from src.scraper.fetcher import fetch_race_html, enumerate_race_ids
from src.scraper.parser import parse_race_html
from src.scraper.normalizer import normalize_to_parquet

__all__ = [
    "fetch_race_html",
    "enumerate_race_ids",
    "parse_race_html",
    "normalize_to_parquet",
]
```

**Key conventions from analog:**
- Triple-quoted module docstring with single-line summary + re-export description
- Explicit `__all__` list
- Import only public functions, not internal helpers

---

### `src/scraper/fetcher.py` (service, file-I/O)

**Analog:** `src/pipeline/kaggle_converter.py` (convert function, lines 47-131)

**Imports pattern** (from kaggle_converter.py lines 19-23):
```python
from pathlib import Path

import pandas as pd
from loguru import logger
```

Fetch module uses same base imports but replaces pandas with playwright:
```python
from pathlib import Path
import time

from loguru import logger
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
```

**Core pattern -- orchestrator function** (from kaggle_converter.py lines 47-131):
```python
def convert(
    raw_dir: Path = Path("data/raw/kaggle"),
    standard_dir: Path = Path("data/standard"),
) -> dict[str, Path]:
    """Main entry point: CSV -> filter -> split -> transform -> write -> audit."""
    raw_dir = Path(raw_dir)
    standard_dir = Path(standard_dir)

    # Step 1: Read input
    logger.info(f"Reading race_result.csv from {race_result_path}")
    # ...

    # Step 2: Process
    logger.info("Filtering to 2015+ flat races")
    # ...

    # Step 3: Write output
    standard_dir.mkdir(parents=True, exist_ok=True)
    # ...

    return output_paths
```

**Error handling + logging pattern** (from kaggle_converter.py):
```python
if nat_count > 0:
    logger.warning(f"Dropped {nat_count} rows with unparseable dates")
```

**File existence + mkdir pattern** (kaggle_converter.py line 104):
```python
standard_dir.mkdir(parents=True, exist_ok=True)
```

**Dedup pattern** (D-08, SCRP-05) -- check file existence before fetching:
```python
# SCRP-05: Dedup -- skip if file exists
if out_path.exists() and out_path.stat().st_size > 0:
    return out_path
```

**Playwright usage pattern** (from RESEARCH.md Pattern 1):
```python
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(url, wait_until="networkidle", timeout=30000)
    html = page.content()
    browser.close()
```

**Rate limiting pattern**:
```python
time.sleep(RATE_LIMIT_SECONDS)
```

---

### `src/scraper/parser.py` (service, transform)

**Analog:** `src/pipeline/kaggle_converter.py` (split_race_entry_result, lines 207-278)

**Imports pattern**:
```python
from pathlib import Path
import re

from bs4 import BeautifulSoup
from loguru import logger
```

**Core parse pattern** -- transforms raw input to structured dicts:

The parser mirrors how `split_race_entry_result` transforms a flat DataFrame into race/entry/result structures. Instead of pandas column operations, it uses BS4 DOM traversal:

```python
def parse_race_html(html_path: Path) -> dict:
    """Parse a saved netkeiba race result HTML into structured data."""
    html = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")

    result = {"race": {}, "entries": [], "results": []}
    # Parse race header, result table, payoff section
    # ...
    return result
```

**Finish position handling** -- follow kaggle_converter.py pattern (lines 303-343):
```python
# Notes that null the finish position (withdrawal, scratched, etc.)
null_notes = {"中", "取", "失", "除", "再"}
```

**Flag parsing** -- from race condition text (D-10):
The parser must derive race_flag_* fields from text, using regex patterns. This is analogous to how `convert_flags_to_bool` (lines 281-300) converts sparse text to Optional[bool], but the INPUT is different (regex from text instead of column values).

**Horse weight parsing** (from RESEARCH.md):
```python
def parse_horse_weight(text: str) -> tuple[Optional[int], Optional[int]]:
    """Parse horse weight text like '456(+4)', '478(-2)', '472(0)'."""
    if not text or text in ("計不", "---"):
        return None, None
    match = re.match(r'(\d+)\(([+-]?\d+)\)', text.strip())
    if match:
        return int(match.group(1)), int(match.group(2))
    return None, None
```

**Sex/age parsing**:
```python
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

---

### `src/scraper/normalizer.py` (service, CRUD)

**Analog:** `src/pipeline/kaggle_converter.py` (convert function, lines 47-131)

This is the closest analog. The normalizer follows the EXACT same pattern as kaggle_converter.py's `convert()`: build DataFrames, validate with schemas, write Parquet, run audit.

**Imports pattern** (from kaggle_converter.py lines 19-29):
```python
from pathlib import Path

import pandas as pd
from loguru import logger

from src.schemas.audit import audit_leakage
from src.schemas.entry import EntrySchema
from src.schemas.race import RaceSchema
from src.schemas.result import ResultSchema
```

**Core normalizer pattern** (mirrors kaggle_converter.py convert() step 5-6):

```python
def normalize_to_parquet(
    parsed_races: list[dict],
    standard_dir: Path = Path("data/standard"),
) -> dict[str, Path]:
    """Convert parsed race data to standard-layer Parquet."""
    race_rows, entry_rows, result_rows = [], [], []
    for parsed in parsed_races:
        race_rows.append(parsed["race"])
        entry_rows.extend(parsed["entries"])
        result_rows.extend(parsed["results"])

    race_df = pd.DataFrame(race_rows)
    entry_df = pd.DataFrame(entry_rows)
    result_df = pd.DataFrame(result_rows)

    # Ensure string dtypes for key columns (same as kaggle_converter.py line 255-257)
    for str_col in ["race_id", "course_code", "race_date"]:
        if str_col in race_df.columns:
            race_df[str_col] = race_df[str_col].astype(str)

    # Audit for leakage (same as kaggle_converter.py step 6)
    audit_leakage([RaceSchema], race_df, "scraped race table generation")
    audit_leakage([EntrySchema], entry_df, "scraped entry table generation")

    # Write Parquet (same engine/compression as kaggle_converter.py line 117)
    standard_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, df in [("race", race_df), ("entry", entry_df), ("result", result_df)]:
        path = standard_dir / f"{name}_scraped.parquet"
        df.to_parquet(path, engine="pyarrow", compression="snappy", index=False)
        paths[name] = path
        logger.info(f"Wrote {name}: {len(df)} rows -> {path}")

    return paths
```

**Parquet write pattern** (kaggle_converter.py line 117):
```python
table_df.to_parquet(output_path, engine="pyarrow", compression="snappy", index=False)
```

**audit_leakage call pattern** (kaggle_converter.py lines 123-129):
```python
race_leaked = audit_leakage([RaceSchema], race_df, "race table generation")
entry_leaked = audit_leakage([EntrySchema], entry_df, "entry table generation")

if race_leaked:
    logger.warning(f"Race table post-race columns: {race_leaked}")
```

---

### `pyproject.toml` (config)

**Analog:** `pyproject.toml` (existing, lines 1-9 dependencies section)

**Modification pattern** -- add new dependencies to existing list:

Current dependencies (line 5-12):
```toml
dependencies = [
    "pydantic>=2.13,<3",
    "pandas>=2.3,<3",
    "numpy>=2,<3",
    "lightgbm>=4.6",
    "loguru>=0.7",
    "pyarrow>=14.0",
]
```

Add after existing entries:
```toml
    "playwright>=1.49",
    "beautifulsoup4>=4.12",
    "lxml>=5.0",
```

---

### `tests/scraper/__init__.py` (config)

**Analog:** `tests/pipeline/__init__.py` (empty file)

Empty file to make the directory a Python package.

---

### `tests/scraper/conftest.py` (config)

**Analog:** `tests/pipeline/conftest.py` (lines 1-33)

**Fixture pattern** -- sample data as pytest fixtures:

```python
"""Shared pytest fixtures for scraper tests.

Provides:
- sample_race_html: Saved HTML from a netkeiba race result page
- sample_parsed_race: Dict output from parse_race_html()
- tmp_raw_dir: Temporary data/raw/netkeiba/ directory
- tmp_standard_dir: Temporary data/standard/ directory (reuse from pipeline)
"""
from pathlib import Path
import pytest
```

**Key fixture design principles from analog:**
1. Fixtures use realistic data structures matching actual input/output formats
2. `tmp_path` from pytest for temporary directories
3. `@pytest.fixture` with return type annotations in docstrings
4. Fixtures build data inline (no external file dependencies for unit tests)

**Scraper-specific fixtures needed:**
```python
@pytest.fixture
def sample_race_html(tmp_path: Path) -> Path:
    """Saved netkeiba race result HTML for testing parser."""

@pytest.fixture
def sample_parsed_race() -> dict:
    """Parsed race dict output matching parse_race_html() return format."""

@pytest.fixture
def tmp_raw_dir(tmp_path: Path) -> Path:
    """Temporary data/raw/netkeiba/ directory."""
    raw_dir = tmp_path / "data" / "raw" / "netkeiba"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir

@pytest.fixture
def tmp_standard_dir(tmp_path: Path) -> Path:
    """Temporary data/standard/ directory."""
    standard_dir = tmp_path / "data" / "standard"
    standard_dir.mkdir(parents=True, exist_ok=True)
    return standard_dir
```

---

### `tests/scraper/test_fetcher.py` (test, request-response)

**Analog:** `tests/pipeline/test_kaggle_converter.py` (class-based test pattern)

**Test structure pattern** (from test_kaggle_converter.py):
```python
"""Unit tests for the netkeiba HTML fetcher.

Tests cover:
- Race ID enumeration from calendar pages
- HTML fetch and raw file save
- Dedup skip for existing files (SCRP-05)
- Rate limiting behavior
- Retry on failure
"""
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
```

**Class-based test organization** (from test_kaggle_converter.py):
```python
class TestDedupSkip:
    """Test that existing HTML files are not re-fetched (SCRP-05)."""

    def test_skips_existing_html(self, tmp_raw_dir):
        """Existing race_id.html file is not re-fetched."""
        # ...

    def test_fetches_missing_html(self, tmp_raw_dir):
        """Missing race_id.html file is fetched and saved."""
        # ...
```

**Mocking pattern for Playwright** (tests must mock Playwright, not use real browser):
```python
def test_fetch_calls_playwright(self, tmp_raw_dir):
    """Fetcher calls Playwright to fetch HTML."""
    with patch("src.scraper.fetcher.sync_playwright") as mock_pw:
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_page.content.return_value = "<html>test</html>"
        mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        # ...
```

---

### `tests/scraper/test_parser.py` (test, transform)

**Analog:** `tests/pipeline/test_kaggle_converter.py` (class-based test pattern)

**Test structure pattern:**
```python
"""Unit tests for the netkeiba HTML parser.

Tests cover:
- Race header extraction (date, course, distance, surface, etc.)
- Entry table parsing (horse name, sex/age, weight, jockey, etc.)
- Result table parsing (finish position, time, margin, etc.)
- Race flag derivation from condition text (D-10)
- Horse weight parsing ('456(+4)' format)
- Sex/age parsing ('牡4' format)
- Edge cases: scratched, withdrawn, no-weight entries
"""
```

**Test class organization** (following test_kaggle_converter.py pattern):
```python
class TestRaceHeaderParsing:
    """Test race header extraction from netkeiba HTML."""

    def test_extracts_race_date(self, sample_race_html):
        """Race date extracted from <p class='smalltxt'>."""
        from src.scraper.parser import parse_race_html
        result = parse_race_html(sample_race_html)
        assert result["race"]["race_date"] == "2022-01-05"

class TestHorseWeightParsing:
    """Test horse weight string parsing."""

    def test_weight_with_positive_change(self):
        """'456(+4)' -> (456, 4)"""
        from src.scraper.parser import parse_horse_weight
        weight, change = parse_horse_weight("456(+4)")
        assert weight == 456
        assert change == 4

    def test_weight_no_data(self):
        """'計不' -> (None, None)"""
        from src.scraper.parser import parse_horse_weight
        weight, change = parse_horse_weight("計不")
        assert weight is None
        assert change is None
```

---

### `tests/scraper/test_normalizer.py` (test, CRUD)

**Analog:** `tests/pipeline/test_kaggle_converter.py` (TestParquetOutput class, lines 382-429)

**Test pattern for Parquet output:**
```python
class TestNormalization:
    """Test dict -> DataFrame -> Parquet normalization."""

    def test_produces_three_parquet_files(self, sample_parsed_race, tmp_standard_dir):
        """normalize_to_parquet creates race/entry/result Scraped Parquet."""
        from src.scraper.normalizer import normalize_to_parquet
        result = normalize_to_parquet([sample_parsed_race], standard_dir=tmp_standard_dir)
        assert "race" in result
        assert "entry" in result
        assert "result" in result
        assert result["race"].exists()

    def test_audit_leakage_called(self, sample_parsed_race, tmp_standard_dir):
        """audit_leakage() is called for race and entry tables."""
        from unittest.mock import patch
        with patch("src.scraper.normalizer.audit_leakage") as mock_audit:
            mock_audit.return_value = []
            # ... call normalize_to_parquet
            assert mock_audit.call_count >= 2
```

---

### `data/raw/netkeiba/{YYYY}/{MM}/{race_id}.html` (storage, file-I/O)

**Analog:** `data/raw/kaggle/` (existing raw data directory)

**Directory structure pattern:**
```
data/raw/kaggle/          # Existing: Kaggle CSV files
data/raw/netkeiba/        # New: Scraped HTML files
    2022/
        01/
            202201010101.html
            202201010102.html
        02/
            ...
    2023/
        ...
```

**File naming convention:** `{race_id}.html` where race_id is 12-digit (YYYYPPCCDDRR)

---

### `data/standard/race_scraped.parquet` (+entry_scraped, result_scraped) (storage, CRUD)

**Analog:** `data/standard/race.parquet` (existing standard-layer Parquet)

**Naming convention:** `{table}_scraped.parquet` to separate from Kaggle-sourced data.
Phase 6 handles integration/merging.

**Parquet write parameters** (from kaggle_converter.py line 117):
```python
df.to_parquet(path, engine="pyarrow", compression="snappy", index=False)
```

## Shared Patterns

### Logging
**Source:** `src/pipeline/kaggle_converter.py` (used throughout)
**Apply to:** All scraper modules (fetcher, parser, normalizer)
```python
from loguru import logger

logger.info(f"Reading race_result.csv from {race_result_path}")
logger.warning(f"Dropped {nat_count} rows with unparseable dates")
logger.error(f"Failed after {retries} attempts: {url}")
```

### Schema Reuse
**Source:** `src/schemas/race.py`, `src/schemas/entry.py`, `src/schemas/result.py`
**Apply to:** normalizer.py (output must match these schemas exactly)
```python
from src.schemas.race import RaceSchema      # 20 race_flag_* fields
from src.schemas.entry import EntrySchema    # horse_race_id, sex, age, etc.
from src.schemas.result import ResultSchema  # finish_position, finish_note, etc.
```

### Audit Leakage Check
**Source:** `src/schemas/audit.py` (lines 45-84)
**Apply to:** normalizer.py (after building DataFrames, before writing Parquet)
```python
from src.schemas.audit import audit_leakage

leaked = audit_leakage([RaceSchema], race_df, "scraped race table generation")
if leaked:
    logger.warning(f"Post-race columns found: {leaked}")
```

### Finish Position Note Handling
**Source:** `src/pipeline/kaggle_converter.py` (lines 303-343)
**Apply to:** parser.py (when parsing 着順 from netkeiba result table)
```python
# Notes that null the finish position
null_notes = {"中", "取", "失", "除", "再"}
# For 降 (demoted): keep position, just record the note
```

### Obstacle Race Exclusion
**Source:** `src/pipeline/kaggle_converter.py` (line 89)
**Apply to:** normalizer.py or fetcher.py (filter out 障害 races)
```python
df = df[df["障害区分"] != "障害"].copy()
# Or from netkeiba: detect "障害" keyword in race condition text
```

### Parquet Output
**Source:** `src/pipeline/kaggle_converter.py` (line 117)
**Apply to:** normalizer.py
```python
table_df.to_parquet(output_path, engine="pyarrow", compression="snappy", index=False)
```

### Path Handling
**Source:** All pipeline modules
**Apply to:** All scraper modules
```python
from pathlib import Path

raw_dir = Path(raw_dir)    # Ensure Path type
standard_dir = Path(standard_dir)
standard_dir.mkdir(parents=True, exist_ok=True)
```

### String Column Dtype Safety
**Source:** `src/pipeline/kaggle_converter.py` (lines 255-257, 263-265)
**Apply to:** normalizer.py (after building DataFrames)
```python
for str_col in ["race_id", "course_code", "race_date"]:
    if str_col in race_df.columns:
        race_df[str_col] = race_df[str_col].astype(str)

for str_col in ["horse_race_id", "race_id"]:
    if str_col in entry_df.columns:
        entry_df[str_col] = entry_df[str_col].astype(str)
```

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| (none) | -- | -- | All files have sufficient analogs in the existing codebase |

**Notes:** The fetcher.py Playwright usage is new to the codebase (no existing Playwright code), but its STRUCTURAL pattern (orchestrator function with error handling, logging, file I/O) matches kaggle_converter.py exactly. The parser.py BS4 usage is new but follows the same transform-pattern as split_race_entry_result. Use RESEARCH.md code examples for Playwright/BS4 API specifics.

## Metadata

**Analog search scope:** `src/`, `tests/`, `pyproject.toml`, `data/`
**Files scanned:** 18 Python files + 1 TOML
**Pattern extraction date:** 2026-06-13
