# Phase 4: Scraping Infrastructure & Race Data - Pattern Map

**Mapped:** 2026-06-13 (regenerated for the 6-plan structure 04-01..04-06)
**Files analyzed:** 17 new/modified files across 6 plans
**Analogs found:** 17 / 17

> Regenerated after the cycle-2 reviews revision of the 6-plan layout.
> Cycle-1 fixes preserved: `__init__.py` is import-safe/empty until 04-06 (NOT
> eager re-exports — Cycle-1 HIGH #3); output layout is partitioned
> `data/standard/scraped/{YYYYMM}/{table}.parquet` (NOT single
> `race_scraped.parquet` — Cycle-1 HIGH #8); the enumerator is `enumerate_races`
> returning `RaceRef(race_id, race_date)` (NOT `enumerate_race_ids` returning
> bare strings — Cycle-1 HIGH #1/#4).
>
> **Cycle-2 additions:** enumeration absolutizes day URLs via `urljoin(BASE_URL, href)` (Cycle-2 #1);
> `fetcher.py` exports a module-level `fetch_with_retry` wrapper alongside the method (Cycle-2 #8);
> `FLAG_CROSSWALK` is an exhaustive superset of `column_mapping.py`'s 13 race_flag_* targets — adds 牡 and bare 見習騎手 (Cycle-2 #2);
> `normalizer._build_typed_dataframe` uses STRICT coercion (no `errors="ignore"`) with nullable Int64/Float64 (Cycle-2 #3);
> `write_partitioned_parquet` does same-month read-merge-dedup on primary_key and accepts `partition_map` for entry/result (Cycle-2 #4/#6 — entry/result have NO race_date column);
> `run_scrape` accepts an injectable `fetch_html` boundary for full-chain e2e (Cycle-2 #5);
> TestSchemaCompatibility asserts equality for non-null Kaggle columns + promotion for null Kaggle columns (Cycle-2 #7).

## File Classification

| New/Modified File | Role | Data Flow | Owning Plan | Closest Analog | Match Quality |
|-------------------|------|-----------|-------------|----------------|---------------|
| `src/scraper/__init__.py` | config | -- | 04-01 (empty) → 04-06 (re-exports) | `src/schemas/__init__.py` | exact |
| `src/scraper/models.py` | model | -- | 04-02 | `src/schemas/race.py` (Pydantic model pattern) / `dataclasses` | role-match |
| `src/scraper/enumeration.py` | service | transform | 04-02 | `src/pipeline/kaggle_converter.py` (split/transform step) | role-match |
| `src/scraper/fetcher.py` | service | file-I/O | 04-03 | `src/pipeline/kaggle_converter.py` (orchestrator + file I/O) | role-match |
| `src/scraper/course_codes.py` | config | -- | 04-04 | `src/pipeline/column_mapping.py` (constant lookup table) | exact |
| `src/scraper/flag_crosswalk.py` | service | transform | 04-04 | `src/pipeline/column_mapping.py` (KAGGLE_COLUMN_MAP + flag conversion) | exact |
| `src/scraper/parser.py` | service | transform | 04-04 | `src/pipeline/kaggle_converter.py` (split_race_entry_result) | role-match |
| `src/scraper/normalizer.py` | service | CRUD | 04-05 | `src/pipeline/kaggle_converter.py` (convert() orchestrator) | exact |
| `src/scraper/orchestrator.py` | service | file-I/O | 04-06 | `src/pipeline/kaggle_converter.py` (convert() top-level entry) | exact |
| `pyproject.toml` | config | -- | 04-01 | `pyproject.toml` (existing) | exact |
| `tests/scraper/__init__.py` | config | -- | 04-01 | `tests/pipeline/__init__.py` (empty) | exact |
| `tests/scraper/conftest.py` | config | -- | 04-01 | `tests/pipeline/conftest.py` | exact |
| `tests/scraper/test_enumeration.py` | test | request-response (mocked) | 04-02 | `tests/pipeline/test_kaggle_converter.py` | role-match |
| `tests/scraper/test_fetcher.py` | test | request-response (mocked) | 04-03 | `tests/pipeline/test_kaggle_converter.py` | role-match |
| `tests/scraper/test_course_codes.py` | test | unit (constant lookup) | 04-04 | `tests/pipeline/test_kaggle_converter.py` (parametrized assertions) | role-match |
| `tests/scraper/test_parser.py` | test | transform | 04-04 | `tests/pipeline/test_kaggle_converter.py` | role-match |
| `tests/scraper/test_normalizer.py` | test | CRUD | 04-05 | `tests/pipeline/test_kaggle_converter.py` (TestParquetOutput) | role-match |
| `tests/scraper/test_end_to_end.py` | test | integration (fixture-based) | 04-06 | `tests/pipeline/test_kaggle_converter.py` (full convert round-trip) | role-match |
| `tests/scraper/test_orchestrator.py` | test | integration (mocked) | 04-06 | `tests/pipeline/test_kaggle_converter.py` | role-match |
| `tests/scraper/fixtures/html/*.html` | storage | file-I/O | 04-04 (Task 3 checkpoint) | `data/raw/kaggle/` (saved source data) | exact |
| `data/raw/netkeiba/{YYYY}/{MM}/{race_id}.html` | storage | file-I/O | 04-03 (writes), 04-04 (reads) | `data/raw/kaggle/` | exact |
| `data/standard/scraped/{YYYYMM}/{race,entry,result}.parquet` | storage | CRUD | 04-05 | `data/standard/race.parquet` (partitioned equivalent) | exact |

## Pattern Assignments

### `src/scraper/__init__.py` (config) — TWO-PHASE LIFECYCLE

**Analog:** `src/schemas/__init__.py` (existing package marker pattern).

**CRITICAL — Codex Review HIGH #3 fix:** This file has a TWO-PHASE lifecycle.
The original pattern map documented eager re-exports (`from src.scraper.fetcher
import ...`); that is WRONG and would block Plans 02/03 from importing their
own not-yet-created submodules (Python executes `__init__.py` before any
submodule import).

- **Phase A (created by 04-01 Task 1, waves 1-4):** IMPORT-SAFE EMPTY package
  marker. Module docstring only, NO submodule imports, NO `__all__`. The
  docstring explicitly notes re-exports are deferred to Plan 06.
- **Phase B (updated by 04-06 Task 1, wave 5):** public re-exports added NOW
  THAT all submodules exist. This is the ONLY plan that adds re-exports.

**04-01 Task 1 shape (Phase A — the file ships like this for 4 waves):**
```python
"""Scraping infrastructure package for netkeiba race data collection.

Public re-exports are added in Plan 06 (final integration) once all
submodules exist. Importing this package MUST NOT trigger any submodule
import (Codex Review HIGH #3).
"""
# Submodules: models.py, enumeration.py (Plan 02); fetcher.py (Plan 03);
# parser.py, course_codes.py, flag_crosswalk.py (Plan 04);
# normalizer.py (Plan 05); orchestrator.py (Plan 06). Re-exports wired in 06.
```

**04-06 Task 1 shape (Phase B — final re-export state):**
```python
"""Scraping infrastructure for netkeiba race data. Public API re-exports."""
from src.scraper.fetcher import FetcherSession, fetch_race_html
from src.scraper.enumeration import (
    enumerate_races,
    enumerate_race_day_urls,
    enumerate_races_for_day,
)
from src.scraper.parser import parse_race_html
from src.scraper.normalizer import normalize_to_parquet
from src.scraper.models import RaceRef
from src.scraper.orchestrator import run_scrape

__all__ = [
    "FetcherSession", "fetch_race_html",
    "enumerate_races", "enumerate_race_day_urls", "enumerate_races_for_day",
    "parse_race_html", "normalize_to_parquet", "RaceRef", "run_scrape",
]
```

**Key conventions:**
- The empty Phase-A marker matches `src/schemas/__init__.py`'s minimal style.
- Phase-B re-exports are added LAST, after every submodule is importable.

---

### `src/scraper/models.py` (model)

**Analog:** `src/schemas/race.py` (Pydantic `BaseModel` for type definitions),
plus stdlib `dataclasses` for the frozen-record shape. The scraper needs a
lightweight immutable value type (not a Pydantic model) because `RaceRef`
carries no validation logic — it is just a typed pair.

**Pattern — frozen dataclass (stdlib, no Pydantic overhead):**
```python
# Source: stdlib dataclasses; mirrors the immutability intent of Pydantic frozen models
from dataclasses import dataclass
import datetime

@dataclass(frozen=True)
class RaceRef:
    """A reference to a race discovered during calendar enumeration.

    race_date is the source of truth for the raw HTML path {YYYY}/{MM}.
    race_id[4:6] is the JRA course code (YYYYPPCCDDRR), NOT a calendar month,
    and MUST NOT be used to derive a path (Codex Review HIGH #1).
    """
    race_id: str          # 12-digit YYYYPPCCDDRR
    race_date: datetime.date
```

**Key conventions from `src/schemas/race.py`:**
- Type annotations on every field (project-wide mypy enforcement).
- Module docstring explaining the load-bearing invariant (race_date vs race_id).

---

### `src/scraper/enumeration.py` (service, transform)

**Analog:** `src/pipeline/kaggle_converter.py` — the `split_race_entry_result`
function (lines 207-278) is the closest structural match: it transforms one
input shape into structured sub-records. Enumeration transforms one calendar
HTML into a list of `RaceRef` records.

**Imports pattern** (mirrors kaggle_converter.py + adds BS4):
```python
import re
import datetime
from typing import Callable, Optional

from bs4 import BeautifulSoup
from loguru import logger

from src.scraper.models import RaceRef
```

**Dependency-injection pattern (NEW vs kaggle_converter.py):** enumeration
functions accept a `fetch_html: Callable[[str], Optional[str]]` callable so
they NEVER launch a browser. The browser lifecycle is owned by the Plan 03
`FetcherSession`. This is the key inversion vs the original Pattern 2 sketch
(which called `sync_playwright()` inline):
```python
def enumerate_races(
    start_date: datetime.date,
    end_date: datetime.date,
    fetch_html: Callable[[str], Optional[str]],
) -> list[RaceRef]:
    """3-level traversal: month -> race day -> race. Returns RaceRef, NOT bare strings."""
    ...
```

**Three-level traversal** (Codex Review HIGH #4 — the locked D-04 strategy):
`enumerate_races` → `enumerate_race_day_urls(year, month, fetch_html)` →
`enumerate_races_for_day(day_url, race_day_date, fetch_html)`. Each level
delegates parsing to `parse_calendar_month_html` / `parse_race_day_html`.

**race_id validation pattern** (Codex Review MEDIUM):
```python
_RACE_ID_RE = re.compile(r"\d{12}")
# In parse_race_day_html:
if not re.fullmatch(r"\d{12}", race_id):
    logger.warning(f"Dropping malformed race_id: {race_id!r}")
    continue
refs.append(RaceRef(race_id=race_id, race_date=race_day_date))  # date from day, NOT race_id
```

---

### `src/scraper/fetcher.py` (service, file-I/O)

**Analog:** `src/pipeline/kaggle_converter.py` — the `convert()` function
(lines 47-131) is the structural template: orchestrator function with error
handling, logging, file I/O, and a clear return type.

**Imports pattern** (Playwright replaces pandas):
```python
import os
import re
import time
from pathlib import Path
from typing import Callable, Optional

from loguru import logger
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from src.scraper.models import RaceRef
```

**Context-manager resource pattern** (Codex Review HIGH — one browser per
batch, NOT one per request). kaggle_converter.py opens files per-call; the
fetcher opens ONE browser per BATCH via `__enter__`/`__exit__`:
```python
class FetcherSession:
    def __init__(self, headless=True, rate_limit_seconds=2.0,
                 navigation_timeout_ms=30000, wait_until="domcontentloaded"):
        ...
    def __enter__(self):
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self._headless)
        self._context = self._browser.new_context()
        self._page = self._context.new_page()
        return self
    def __exit__(self, *exc):
        try: self._page.close()
        finally:
            try: self._browser.close()
            finally: self._pw.stop()
```

**Atomic-write pattern** (NEW — kaggle_converter.py writes in place; the
fetcher writes via temp + `os.replace` so an interruption never leaves a
non-empty partial file that future dedup runs treat as valid):
```python
tmp = out_path.with_suffix(".html.tmp")
tmp.write_text(html, encoding="utf-8")
os.replace(tmp, out_path)  # atomic on the same filesystem
```

**Dedup pattern** (D-08, SCRP-05) — mirrors the existence-check style:
```python
if out_path.exists() and out_path.stat().st_size > 0:
    logger.info(f"Skipping existing {race_ref.race_id}")
    return out_path
```

**CYCLE-3 #2 — `fetch_race_html` optional `fetch_callable` param (NEW):** the
signature is now `fetch_race_html(race_ref, session=None, raw_dir=...,
fetch_callable=None)`. `session` is now Optional. When `session is None` and
`fetch_callable is provided`, the injected transport is used to fetch the HTML
(`fetch_callable(url)`) instead of `session.fetch_with_retry(url)`. This lets
`run_scrape(live=False, fetch_html=transport)` route the transport to race
fetching (not only enumeration), so a race NOT pre-saved to the raw path is
fetched via the transport — and a transport returning None is handled gracefully
(race skipped) rather than crashing with `AttributeError` on a None session. The
live-mode session path remains the default when a session is supplied. The dedup
short-circuit above runs BEFORE either transport is consulted:
```python
def fetch_race_html(race_ref, session=None, raw_dir=Path("data/raw/netkeiba"),
                    fetch_callable=None) -> Optional[Path]:
    # ... path derivation from race_ref.race_date (HIGH #1) ...
    # SCRP-05 dedup short-circuit (runs before any transport)
    if out_path.exists() and out_path.stat().st_size > 0:
        return out_path
    url = f"https://db.netkeiba.com/race/{race_ref.race_id}/"
    # CYCLE-3 #2: choose the transport
    if fetch_callable is not None:
        html = fetch_callable(url)          # injected transport (offline mode)
    elif session is not None:
        html = session.fetch_with_retry(url) # live-mode default
    else:
        raise ValueError("fetch_race_html requires either a session or a fetch_callable")
    if html is None or detect_block_page(html):
        return None                          # graceful skip, NOT AttributeError
    # ... atomic write + return out_path ...
```

**Path derivation from `RaceRef.race_date`** (Codex Review HIGH #1 — the
month comes from the race_date, NEVER from `race_id[4:6]`):
```python
year = f"{race_ref.race_date.year:04d}"
month = f"{race_ref.race_date.month:02d}"
out_path = raw_dir / year / month / f"{race_ref.race_id}.html"
```

**wait_until default** is `"domcontentloaded"` (NOT `"networkidle"` — Codex
Review MEDIUM, networkidle is unreliable on pages with persistent requests).

**CYCLE-2 #8 — module-level `fetch_with_retry` wrapper (NEW):** the verify
block imports `fetch_with_retry` at module level, so a thin wrapper exists
alongside the `FetcherSession.fetch_with_retry` method:
```python
def fetch_with_retry(url: str, retries: int = MAX_RETRIES, headless: bool = True) -> Optional[str]:
    """Thin convenience wrapper for one-off/CLI/smoke callers.

    Constructs a transient FetcherSession and delegates. Do NOT call this in a
    loop over many URLs — use FetcherSession.fetch_with_retry on a single shared
    session instead (avoids the browser-per-request regression, Cycle-1 HIGH).
    """
    with FetcherSession(headless=headless) as session:
        return session.fetch_with_retry(url, retries=retries)
```
The orchestrator (Plan 06) uses the METHOD on a shared session; the wrapper is
for single-shot CLI/smoke use only.

---

### `src/scraper/course_codes.py` (config, constant lookup)

**Analog:** `src/pipeline/column_mapping.py` — the `KAGGLE_COLUMN_MAP` (lines
9-28) is the exact pattern: a module-level constant dict that other modules
import as the single source of truth, plus a reverse map.

**Pattern — authoritative constant table:**
```python
"""Single authoritative source for JRA course codes.

Corrected per Codex Review HIGH #5: 札幌=01, 函館=02, 福島=03, 新潟=04,
東京=05, 中山=06, 中京=07, 京都=08, 阪神=09, 小倉=10.
The parser, normalizer, and any future module import from here.
"""
COURSE_CODE_MAP: dict[str, str] = {
    "札幌": "01", "函館": "02", "福島": "03", "新潟": "04", "東京": "05",
    "中山": "06", "中京": "07", "京都": "08", "阪神": "09", "小倉": "10",
}
COURSE_CODE_REVERSE: dict[str, str] = {v: k for k, v in COURSE_CODE_MAP.items()}
```

**Key conventions from `column_mapping.py`:**
- Module docstring cites the source-of-truth cross-reference.
- Public constant in UPPER_SNAKE; reverse map derived in-place.

---

### `src/scraper/flag_crosswalk.py` (service, transform)

**Analog:** `src/pipeline/column_mapping.py` — the flag-conversion rows in
`KAGGLE_COLUMN_MAP` (レース記号/牝 -> race_flag_filly_only, etc.) and the
`convert_flags_to_bool` helper are the direct template. The crosswalk is the
netkeiba-text-side equivalent of that Kaggle-side mapping.

**Pattern — ordered pattern list + derivation function:**
```python
"""netkeibia-text -> race_flag_* crosswalk.

Validated against src/pipeline/column_mapping.py (the Kaggle-side authority)
so scraped flags join cleanly with Kaggle flags in Phase 6. (国際) maps to
race_flag_graded_stakes for Kaggle join compatibility even though it is
strictly an international designation (documented compatibility decision).
"""
from typing import Optional

FLAG_CROSSWALK: list[tuple[str, str]] = [
    ("(ハンデ)", "race_flag_handicap"),
    ("(馬齢)", "race_flag_age_restricted"),
    ("(牝)", "race_flag_filly_only"),       # NOT race_flag_mare_only (HIGH #6)
    ("(国際)", "race_flag_graded_stakes"),  # Kaggle join compatibility (HIGH #6)
    ("(特指)", "race_flag_special_weight"),
    # ... full list in 04-04 Task 1
]

def derive_race_flags(race_condition: str, race_name: str = "") -> dict[str, Optional[bool]]:
    """Return EXACTLY the 20 race_flag_* keys from RaceSchema.

    All keys default to None (unknown). Matched patterns set the field to
    True. NEVER set False based on absence (None = unknown, per Codex Review MEDIUM).
    """
    flags: dict[str, Optional[bool]] = {name: None for name in _ALL_FLAG_FIELDS}
    for pattern, field_name in FLAG_CROSSWALK:
        if pattern in race_condition:
            flags[field_name] = True
    # ... class patterns, grade patterns
    return flags
```

**Key conventions from `column_mapping.py`:**
- Order matters (more-specific patterns first for greedy matches).
- Public `list[tuple]` constant + a derivation function that returns the
  full field set (so downstream reindex against `RaceSchema.model_fields` is
  guaranteed to find every key).
- Compatibility decisions documented inline, not buried.

---

### `src/scraper/parser.py` (service, transform)

**Analog:** `src/pipeline/kaggle_converter.py` — `split_race_entry_result`
(lines 207-278) transforms a flat DataFrame into race/entry/result structures;
the parser does the same transformation but from BS4 DOM nodes.

**Imports pattern:**
```python
import re
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup
from loguru import logger

from src.scraper.course_codes import COURSE_CODE_MAP
from src.scraper.flag_crosswalk import derive_race_flags
```

**Header-driven column resolution** (Codex Review HIGH #10 — replaces fixed
`cols[N]` indexing with `<th>`-name resolution):
```python
def resolve_columns_by_header(table, header_aliases: dict[str, list[str]]) -> dict[str, int]:
    """Map field names to column indices by reading <th> text, not by hardcoding indices."""
    ...
```

**horse_race_id 14-digit pattern** (Codex Review HIGH #2 — matches Kaggle's
existing keys, NO underscore despite the schema docstring):
```python
horse_race_id = f"{race_id}{horse_number:02d}"   # 14-digit YYYYPPCCDDRRHH
```

**Finish-position note handling** (mirrors kaggle_converter.py
`process_finish_position`, lines 303-343):
```python
null_notes = {"中", "取", "失", "除", "再"}  # -> finish_position None, note set
# "降" (demoted) keeps the position, records the note
```

**horse_weight / sex_age parsing** — same regex style as the original
Pattern 4 sketch (unchanged by the revision).

---

### `src/scraper/normalizer.py` (service, CRUD)

**Analog:** `src/pipeline/kaggle_converter.py` — the `convert()` function
(lines 47-131) is the closest analog: build DataFrames, ensure dtypes, write
Parquet, run audit. The normalizer follows the same shape but with three
load-bearing differences driven by Codex Review HIGH #7/#8:

1. **Schema-conformance via `model_fields` reindex** (HIGH #7) — replaces the
   audit-only check. Every DataFrame is reindexed against
   `Schema.model_fields.keys()` so all expected columns exist in stable order
   even for empty input.
2. **Partitioned atomic output** (HIGH #8) — see the storage section below.
3. **No `audit_leakage` on standard-layer generation** (MEDIUM) —
   `audit_leakage` is post-race-leakage detection (feature-layer concern);
   the standard entry table legitimately contains popularity/win_odds, so
   calling audit would false-positive. Schema conformance is enforced via
   reindex + dtype map instead.

**Imports pattern** (mirrors kaggle_converter.py lines 19-29):
```python
import os
from pathlib import Path

import pandas as pd
from loguru import logger
from pydantic import BaseModel

from src.schemas.race import RaceSchema
from src.schemas.entry import EntrySchema
from src.schemas.result import ResultSchema
# NOTE: audit_leakage is deliberately NOT imported here (Codex Review MEDIUM)
```

**Typed-DataFrame builder** (Cycle-1 HIGH #7 + **Cycle-2 HIGH #3 strict coercion**):
```python
def _build_typed_dataframe(rows: list[dict], schema: type[BaseModel]) -> pd.DataFrame:
    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    df = df.reindex(columns=list(schema.model_fields.keys()))  # all columns, stable order
    for col, target in SCHEMA_DTYPE_MAP[schema].items():
        if col not in df.columns:
            continue
        # CYCLE-2 #3: STRICT coercion. No errors="ignore" (it silently skipped
        # failed conversions, leaving None-containing int columns as float64).
        # Nullable Int64/Float64/boolean succeed on mixed None+value input;
        # genuine conversion failures (non-numeric text in a numeric column) RAISE.
        try:
            df[col] = df[col].astype(target)  # nullable dtype handles None as NA
        except (TypeError, ValueError) as e:
            raise TypeError(
                f"Column {col} could not be coerced to {target} for "
                f"{schema.__name__}: {e}"
            ) from e
    return df
```
`SCHEMA_DTYPE_MAP[ResultSchema]["finish_position"] == "Int64"` (nullable) —
matches Kaggle's `int64 nullable=True` Arrow type exactly; the Cycle-1 plan's
non-nullable `"int64"` was unreachable for None-containing input.

**Integrity validation** (Codex Review MEDIUM — unique, FK, 1-to-1):
```python
def validate_integrity(race_df, entry_df, result_df) -> list[str]:
    """Return human-readable violation strings (empty = clean). Does NOT raise."""
    ...
```

**Obstacle filter** (mirrors kaggle_converter.py line 89):
```python
race_df = race_df[race_df["obstacle"] != "障害"].copy()
# propagate to entries/results by race_id
```

**SCHEMA_DTYPE_MAP** — concrete dtypes matching Kaggle Parquet exactly (see
04-05 Task 1 for the authoritative field-by-field list). **Cycle-2 #3: nullable
`Int64`/`Float64`/`boolean` are used throughout** because Kaggle's int/double
columns are themselves `nullable=True` in Arrow (verified via
`pq.read_schema('data/standard/result.parquet')` — finish_position is
`int64 nullable=True`). Nullable pandas dtypes serialize to the same Arrow
physical type, so equality holds in 04-06 TestSchemaCompatibility. For the 20
race_flag_* fields, nullable `boolean` is used because Kaggle mixes non-null
`bool` and Arrow `null` flag columns; 04-06 TestSchemaCompatibility treats the
null-only Kaggle columns as deliberate promotions (Cycle-2 #7).

**CYCLE-3 #1 (corner dtype Float64, NOT Int64):** `corner_1..corner_4` are
mapped to nullable `Float64`, NOT `Int64`. Kaggle stores them as NON-NULL Arrow
`double` (verified via `pq.read_schema('data/standard/result.parquet')`:
`corner_1..corner_4 -> double nullable=True`). Nullable pandas `Float64`
serializes to Arrow `double` (`str(double) == str(double)`), so it passes 04-06's
`test_physical_type_equality_for_non_null_kaggle_columns` (which compares
`str(field.type)`). The Cycle-2 revision's `Int64` assignment was wrong — `Int64`
serializes to Arrow `int64` (`str(int64) != str(double)`) and would FAIL that
equality test for all 4 corner columns. (Corners are integer-valued passing
positions but Kaggle stores them as `double`; `Float64` preserves them exactly.)

---

### `src/scraper/orchestrator.py` (service, file-I/O)

**Analog:** `src/pipeline/kaggle_converter.py` — the `convert()` function is
the top-level entry point that wires the sub-steps together. The orchestrator
is the scraping-pipeline equivalent.

**Pattern — top-level entry that wires sub-steps:**
```python
import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from src.scraper.fetcher import FetcherSession, fetch_race_html, make_fetch_html_callable
from src.scraper.enumeration import enumerate_races
from src.scraper.parser import parse_race_html
from src.scraper.normalizer import normalize_to_parquet


def run_scrape(
    start_date: datetime.date,
    end_date: datetime.date,
    raw_dir: Path = Path("data/raw/netkeiba"),
    standard_dir: Path = Path("data/standard"),
    live: bool = False,
    max_races: Optional[int] = None,
    fetch_html: Optional[Callable[[str], Optional[str]]] = None,  # CYCLE-2 #5
) -> dict[str, list[Path]]:
    """Wire enumeration -> fetch -> parse -> normalize.

    CYCLE-2 #5: fetch_html is the injectable network boundary. If provided,
    enumeration uses it and NO real browser is launched (deterministic test
    path). If None AND live=True, a real FetcherSession is opened. If None AND
    live=False, raise ValueError — `live=False` MUST forbid network (Cycle-1
    MEDIUM: `live` is not a dead parameter).
    """
    parsed_races = []
    if fetch_html is None and not live:
        raise ValueError("run_scrape requires either live=True or an injected fetch_html callable")
    session_cm = FetcherSession() if (live and fetch_html is None) else None
    with session_cm as session if session_cm else _NullContext():
        if fetch_html is None:
            fetch_html = make_fetch_html_callable(session)
        refs = enumerate_races(start_date, end_date, fetch_html)
        if max_races:
            refs = refs[:max_races]
        for ref in refs:
            # When fetch_html is injected and live=False, tests pre-save golden
            # HTML to the expected raw path so fetch_race_html's SCRP-05 dedup
            # returns the path without calling the transport.
            # CYCLE-3 #2: route the injected transport to race fetching in offline mode.
            # When fetch_html is injected and live=False, pass it as fetch_callable so a race
            # NOT pre-saved is fetched via the transport (transport-None -> race skipped),
            # not by dereferencing a None session.
            path = fetch_race_html(ref, session=session, raw_dir=raw_dir,
                                   fetch_callable=fetch_html if (not live and fetch_html is not None) else None)
            if path is None:
                logger.warning(f"fetch failed for {ref.race_id}, skipping")
                continue
            parsed_races.append(parse_race_html(path))
    return normalize_to_parquet(parsed_races, standard_dir)
```

**Key conventions from `kaggle_converter.py` `convert()`:**
- Single public entry function with Path-typed defaults.
- `with` block guarantees resource cleanup (browser here; file handles in
  kaggle_converter).
- Returns a structured result (`dict[str, list[Path]]` here; `dict[str, Path]`
  in kaggle_converter — the scraper returns lists because output is
  partitioned across months).

**CYCLE-2 #5 — injectable fetch boundary (NEW vs kaggle_converter):** the
`fetch_html: Optional[Callable[[str], Optional[str]]] = None` parameter is the
network seam. It lets the full-chain e2e test (04-06 TestFullChainE2E) pass a
transport backed by saved golden HTML and exercise the REAL enumerate → parse →
normalize without a browser. `live=False` WITHOUT `fetch_html` raises — this
fixes the Codex cycle-1 MEDIUM that `live` was a dead parameter that still
permitted network.

---

### `pyproject.toml` (config)

**Analog:** `pyproject.toml` (existing dependencies section).

**Modification pattern** — append to the existing `dependencies` list (NOT a
dev/optional extra; these are runtime deps per D-02):
```toml
dependencies = [
    "pydantic>=2.13,<3",
    # ... existing entries ...
    "pyarrow>=14.0",
    "playwright>=1.49",        # NEW (04-01 Task 1)
    "beautifulsoup4>=4.12",    # NEW (04-01 Task 1)
    "lxml>=5.0",               # NEW (04-01 Task 1)
]
```

---

### `tests/scraper/__init__.py` (config)

**Analog:** `tests/pipeline/__init__.py` (empty file). Created empty by 04-01
Task 1.

---

### `tests/scraper/conftest.py` (config)

**Analog:** `tests/pipeline/conftest.py` (lines 1-33) — `tmp_path`-based
directory fixtures. Created by 04-01 Task 1 (the only plan that creates
conftest; later plans consume its fixtures).

```python
"""Shared pytest fixtures for scraper tests."""
from pathlib import Path
import pytest


@pytest.fixture
def tmp_raw_dir(tmp_path: Path) -> Path:
    raw_dir = tmp_path / "data" / "raw" / "netkeiba"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


@pytest.fixture
def tmp_standard_dir(tmp_path: Path) -> Path:
    standard_dir = tmp_path / "data" / "standard"
    standard_dir.mkdir(parents=True, exist_ok=True)
    return standard_dir


@pytest.fixture
def golden_html_dir() -> Path:
    fixtures = Path("tests/scraper/fixtures/html")
    fixtures.mkdir(parents=True, exist_ok=True)
    return fixtures
```

**Key conventions from the analog:**
- `tmp_path` from pytest for isolated temp directories (no real `data/` paths).
- `@pytest.fixture` decorator, Path return types.

---

### `tests/scraper/test_enumeration.py` (test, request-response mocked)

**Analog:** `tests/pipeline/test_kaggle_converter.py` (class-based test
pattern). Created by 04-02 Task 2.

Uses a fake `fetch_html` callable (a dict mapping URL -> HTML string, None for
unknown URLs) — NO real Playwright. Classes: `TestParseCalendarMonthHtml`,
`TestParseRaceDayHtml`, `TestEnumerateRaces`, `TestRaceIdValidation`.

**Critical assertion (HIGH #1 regression guard):** no test derives a month
from `race_id[4:6]`; every `RaceRef.race_date` comes from the day argument.

---

### `tests/scraper/test_fetcher.py` (test, request-response mocked)

**Analog:** `tests/pipeline/test_kaggle_converter.py`. Created by 04-03 Task 2.

Mocks Playwright via `unittest.mock.patch("src.scraper.fetcher.sync_playwright")`
— NO real browser. Classes: `TestDedup`, `TestPathDerivation`,
`TestFetcherSessionLifecycle`, `TestRetryAndFailure`, `TestBlockPageDetection`,
`TestAtomicWrite`.

**Mock pattern (NEW — kaggle_converter tests mock pandas, not a browser):**
```python
def fake_session():
    session = MagicMock()
    session.fetch_with_retry.return_value = "<html><table class='race_table_01'></table></html>"
    return session
```

---

### `tests/scraper/test_course_codes.py` (test, unit constant lookup)

**Analog:** `tests/pipeline/test_kaggle_converter.py` (parametrized
assertions on a constant table). Created by 04-04 Task 4.

Class `TestCourseCodes` with a parametrized test covering all 10 venues
(`札幌=01` .. `小倉=10`) — the HIGH #5 regression guard.

---

### `tests/scraper/test_parser.py` (test, transform)

**Analog:** `tests/pipeline/test_kaggle_converter.py`. Created by 04-04 Task 4.

Classes: `TestHorseWeightParsing`, `TestSexAgeParsing`, `TestFlagCrosswalk`,
`TestResolveColumnsByHeader`, `TestParseRaceHtmlGolden`. The golden-fixture
class loads real HTML from `tests/scraper/fixtures/html/` (captured in 04-04
Task 3).

---

### `tests/scraper/test_normalizer.py` (test, CRUD)

**Analog:** `tests/pipeline/test_kaggle_converter.py` (`TestParquetOutput`
class, lines 382-429). Created by 04-05 Task 2.

Classes: `TestTypedDataframe`, `TestObstacleFiltering`,
`TestIntegrityValidation`, `TestPartitionedOutput`. The
`TestDtypesApplied`/`TestDtypeFidelity` assertions verify pyarrow physical
type equality against the Kaggle Parquet schema (the load-bearing check for
04-06 `TestSchemaCompatibility`).

---

### `tests/scraper/test_end_to_end.py` (test, integration fixture-based)

**Analog:** `tests/pipeline/test_kaggle_converter.py` (full `convert()`
round-trip test). Created by 04-06 Task 2.

Classes: `TestEndToEndFixture` (parametrized over every golden fixture),
`TestSchemaCompatibility`, `TestOptInLiveSmoke` (`@pytest.mark.live`, skipped
by default — NO network in CI).

---

### `tests/scraper/test_orchestrator.py` (test, integration mocked)

**Analog:** `tests/pipeline/test_kaggle_converter.py`. Created by 04-06 Task 2.

Class `TestRunScrape` with all sub-steps mocked (`FetcherSession`,
`enumerate_races`, `fetch_race_html`, `parse_race_html`,
`normalize_to_parquet`).

---

### `tests/scraper/fixtures/html/*.html` (storage, file-I/O)

**Analog:** `data/raw/kaggle/` (saved source data that tests read back).
Captured by the human checkpoint in 04-04 Task 3.

Target diversity axes: base flat race (2022 中山), graded stakes (2023 阪神
G1/G2/G3), dirt race (2024 東京/中京), cancelled/scratched runner (取/中),
optional obstacle race. Each fixture is valid HTML loadable by BS4+lxml.

---

### `data/raw/netkeiba/{YYYY}/{MM}/{race_id}.html` (storage, file-I/O)

**Analog:** `data/raw/kaggle/` (existing raw data directory).

**Directory structure (D-06, D-07):** the `{YYYY}/{MM}` segments come from
`RaceRef.race_date` (HIGH #1), NOT from `race_id[4:6]`. Filename is
`{race_id}.html` where race_id is the 12-digit `YYYYPPCCDDRR`.

---

### `data/standard/scraped/{YYYYMM}/{race,entry,result}.parquet` (storage, CRUD) — PARTITIONED

**Analog:** `data/standard/race.parquet` (existing standard-layer Parquet).
Written by 04-05 Task 1, read back by 04-06 Task 2.

**CRITICAL — Cycle-1 HIGH #8 fix:** The original pattern map documented
`data/standard/race_scraped.parquet` (a single file per table). That is WRONG
— a single-file write would overwrite prior batches on every run. The revised
layout is **date-partitioned**: one file per `{YYYYMM}` per table, keyed by
`race_date`. Each partition is written atomically (temp + `os.replace`), so
interruption never corrupts a prior month.

```
data/standard/scraped/
    202201/
        race.parquet
        entry.parquet
        result.parquet
    202202/
        race.parquet
        ...
```

**CYCLE-2 #4 — same-month merge-dedup (NEW):** re-running the SAME month
(e.g. `max_races=1` smoke then a full run) does NOT overwrite the prior
partition. `write_partitioned_parquet` now accepts `primary_key` and performs
read-merge-dedup before the atomic replace:
```python
def write_partitioned_parquet(
    table_name: str,
    df: pd.DataFrame,
    standard_dir: Path,
    partition_map: Optional[dict[str, datetime.date]] = None,  # CYCLE-2 #6
    primary_key: str = "race_id",                              # CYCLE-2 #4
) -> list[Path]:
    # if target file exists: read -> concat -> drop_duplicates(subset=[primary_key], keep="last")
    # then atomic temp + os.replace
```
A sentinel primary-key row from a prior smoke run SURVIVES a same-month full
re-run, and duplicate primary keys within the merged frame collapse to one.

**CYCLE-2 #6 — entry/result have NO race_date column (NEW):** `EntrySchema` and
`ResultSchema` (verified against `data/standard/{entry,result}.parquet`) lack a
`race_date` field, so partitioning them by `df["race_date"]` raises KeyError.
The `partition_map: dict[str, datetime.date]` (race_id -> race_date) is built
in `normalize_to_parquet` from the race DataFrame and passed to the entry/result
writes. For entry/result the partition YYYYMM is looked up via
`partition_map[row["race_id"]]`. Omitting the map for entry/result raises a
loud KeyError (fail-fast, not silent mis-partition).

**Parquet write parameters** (same as kaggle_converter.py line 117):
```python
df.to_parquet(path, engine="pyarrow", compression="snappy", index=False)
```

**Naming convention:** `scraped/` subdirectory separates scraped data from
Kaggle-sourced `data/standard/race.parquet`. Phase 6 reads the partition
directory and handles integration/merging.

## Shared Patterns

### Logging
**Source:** `src/pipeline/kaggle_converter.py` (used throughout)
**Apply to:** All scraper modules (enumeration, fetcher, parser, normalizer, orchestrator)
```python
from loguru import logger

logger.info(f"Reading race_result.csv from {race_result_path}")
logger.warning(f"Dropped {nat_count} rows with unparseable dates")
logger.error(f"Failed after {retries} attempts: {url}")
```

### Schema Reuse
**Source:** `src/schemas/race.py`, `src/schemas/entry.py`, `src/schemas/result.py`
**Apply to:** normalizer.py (output must match these schemas exactly), parser.py
(emits dict keys matching schema field names)
```python
from src.schemas.race import RaceSchema      # 20 race_flag_* fields, NO head_count
from src.schemas.entry import EntrySchema    # horse_race_id (14-digit), sex, age, etc.
from src.schemas.result import ResultSchema  # finish_position, finish_note, etc.
```

### Schema-Conformance Reindex (HIGH #7)
**Source:** NEW (this phase); supersedes the audit-only check
**Apply to:** normalizer.py `_build_typed_dataframe`
```python
df = df.reindex(columns=list(schema.model_fields.keys()))
```
This replaces the original `audit_leakage`-only validation. `audit_leakage`
remains in scope for the feature layer only (post-race leakage detection).

### Finish Position Note Handling
**Source:** `src/pipeline/kaggle_converter.py` (lines 303-343)
**Apply to:** parser.py (when parsing 着順 from netkeiba result table)
```python
null_notes = {"中", "取", "失", "除", "再"}   # -> finish_position None, note set
# "降" (demoted): keep position, record note
```

### Obstacle Race Exclusion
**Source:** `src/pipeline/kaggle_converter.py` (line 89)
**Apply to:** parser.py emits `obstacle = "障害"` marker; normalizer.py applies the filter
```python
# parser.py: detect "障害" in course info / condition text -> race["obstacle"] = "障害"
# normalizer.py:
race_df = race_df[race_df["obstacle"] != "障害"].copy()
# propagate drop to entries/results by race_id
```

### Parquet Output
**Source:** `src/pipeline/kaggle_converter.py` (line 117)
**Apply to:** normalizer.py `write_partitioned_parquet`
```python
df.to_parquet(path, engine="pyarrow", compression="snappy", index=False)
```

### Path Handling
**Source:** All pipeline modules
**Apply to:** All scraper modules
```python
from pathlib import Path

raw_dir = Path(raw_dir)
standard_dir = Path(standard_dir)
standard_dir.mkdir(parents=True, exist_ok=True)
```

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| (none) | -- | -- | All files have sufficient analogs in the existing codebase |

**Notes:**
- The Playwright usage in `fetcher.py` is new to the codebase (no existing
  Playwright code), but its STRUCTURAL pattern (orchestrator + context-manager
  resource + atomic file I/O) matches `kaggle_converter.py`. Use RESEARCH.md
  Pattern 1 / Code Examples for the Playwright API specifics.
- The BS4 usage in `parser.py` / `enumeration.py` is new but follows the same
  transform-pattern as `split_race_entry_result`.
- The frozen-dataclass `RaceRef` in `models.py` is new but matches the
  immutability intent of the Pydantic schemas in `src/schemas/`.

## Metadata

**Analog search scope:** `src/`, `tests/`, `pyproject.toml`, `data/`
**Files scanned:** 18 Python files + 1 TOML + 3 Parquet schemas (via `pyarrow.parquet.read_schema`)
**Pattern extraction date:** 2026-06-13 (regenerated for the cycle-2 reviews revision)
