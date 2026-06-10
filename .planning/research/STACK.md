# Stack Research

**Domain:** JRA三連複EV判定システム (JRA Trifecta Expected Value Judgment System)
**Researched:** 2026-06-10
**Confidence:** HIGH

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12+ | Runtime | Project constraint. 3.12 for performance improvements, wide library support. LightGBM macOS wheels available. |
| LightGBM | 4.6.0 | ML model for 3着内確率 estimation | Project-fixed choice. Best-in-class for tabular data, native categorical feature support (no one-hot needed), ~8x faster with native categoricals vs OHE. Installed via `pip install lightgbm`; macOS requires `brew install libomp`. |
| pandas | 2.3.x | DataFrame processing, CSV I/O, data pipeline | Dominant tabular data library. Kaggle data is already CSV. 3.0 is too new (breaking changes); use stable 2.3 branch. |
| NumPy | 2.x | Numerical computing, array operations | Required by pandas/LightGBM/scikit-learn. 2.x is now standard; use latest compatible with pandas 2.3. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| scikit-learn | 1.9.0 | Train/test split, metrics, preprocessing, cross-validation | Model evaluation pipeline. Used with LightGBM's scikit-learn API (`LGBMClassifier`). Install via `pip install 'lightgbm[scikit-learn]'`. |
| httpx | 0.28.1 | HTTP client for scraping JRA/netkeiba | Sync and async API, HTTP/2 support. Use for fetching odds pages and race data. Better than `requests` for modern async-capable scraping. |
| BeautifulSoup4 | 4.12+ | HTML parsing for scraped pages | Parse JRA/netkeiba HTML responses. Use with `lxml` parser for speed. |
| lxml | 5.x | Fast HTML/XML parser backend for BS4 | Always use as BS4 parser. Significantly faster than `html.parser`. |
| Pydantic | 2.13.x | Data validation, schema definition for standard/feature layers | Validate data flowing through the 3-layer pipeline (raw -> standard -> feature). Catch data quality issues early. Use `BaseModel` for race entries, odds records, EV results. |
| loguru | 0.7.x | Structured logging | Zero-config logging. Use `logger.add()` with rotation for pipeline execution logs. Far simpler than stdlib `logging`. |
| click | 8.x | CLI interface | Build CLI commands for pipeline execution, backtesting, EV output. Mature, battle-tested, widely used. |
| pyyaml | 6.x | YAML config file parsing | Read pipeline config, model hyperparameters, scraping settings. Standard YAML library. |

### Scraping-Specific Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| playwright | 1.49+ | Browser automation for dynamic JRA pages | Use ONLY when httpx+BS4 fails (JavaScript-rendered odds pages). Heavier dependency; install via `pip install playwright && playwright install chromium`. |

### Development Tools

| Tool | Version | Purpose | Notes |
|------|---------|---------|-------|
| Poetry | 2.x | Dependency management, virtual env, packaging | Use `pyproject.toml` for project config. Handles lockfile (`poetry.lock`) for reproducibility. |
| pytest | 9.0.x | Testing framework | Requires Python 3.10+. Use `conftest.py` for shared fixtures (sample race data, model configs). |
| ruff | 0.15.x | Linter + formatter (replaces black, flake8, isort) | Single tool replacing 5+ dev dependencies. Runs in <1 second. Configure via `[tool.ruff]` in `pyproject.toml`. |
| mypy | 1.14+ | Static type checking | Enforce type safety across pipeline. Essential for data validation layer. |

## Installation

```bash
# Project setup with Poetry
poetry init --python "^3.12"

# Core dependencies
poetry add lightgbm pandas numpy scikit-learn
poetry add httpx beautifulsoup4 lxml
poetry add pydantic loguru click pyyaml

# Optional: for dynamic page scraping
poetry add playwright  # only if needed

# Dev dependencies
poetry add --group dev pytest ruff mypy

# Post-install: LightGBM macOS requirement
brew install libomp

# Post-install: Playwright browsers (only if installed)
playwright install chromium
```

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| ML Framework | LightGBM | XGBoost | Project constraint fixes LightGBM. XGBoost is comparable but LightGBM has faster training on large datasets and native categorical support. |
| ML Framework | LightGBM | CatBoost | CatBoost also handles categoricals natively but is slower to train and less commonly used in horse racing ML literature. |
| Data Processing | pandas 2.3 | Polars | Polars is 3-12x faster but pandas has much better LightGBM/scikit-learn integration, and the Kaggle data is already CSV (not large enough for Polars to matter). Pandas `CategoricalDtype` is auto-detected by LightGBM. Switch to Polars later if data volume grows. |
| Data Processing | pandas 2.3 | pandas 3.0 | 3.0 has breaking changes (new string dtype, removal of deprecated APIs). Too bleeding-edge for a data pipeline that needs reliability. Revisit after 3.0 stabilizes. |
| HTTP Client | httpx | requests | requests is simpler but sync-only. httpx provides both sync and async APIs, HTTP/2 support, and a familiar interface. Same API style as requests. |
| Browser Automation | playwright (fallback) | selenium | Playwright is faster, has better auto-wait, and is the recommended default in 2025+. Selenium is for legacy projects only. Only use either when static scraping fails. |
| CLI Framework | click | typer | Typer is built on top of click and uses type hints. Click is more mature, has better documentation, and is sufficient for this project's CLI needs. |
| Config | pyyaml | Hydra/OmegaConf | Hydra is overkill for this project's config needs. OmegaConf has maintenance concerns (GitHub issue #1200). Simple YAML files with Pydantic validation are sufficient and more maintainable. |
| Logging | loguru | stdlib logging | stdlib logging requires boilerplate configuration. Loguru is zero-config, thread-safe, supports rotation/compression natively, and is 10x faster. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| TensorFlow / PyTorch | Overkill for tabular data EV system. LightGBM is the right tool for structured features. | LightGBM |
| Jupyter Notebooks for production code | Not reproducible, hard to version control, encourages non-modular code. Use for exploration only. | Python modules with pytest |
| SQLite / PostgreSQL | No need for a database. CSV files and Parquet are sufficient for this scale. The 3-layer architecture (raw/standard/feature) works with files. | CSV/Parquet files |
| Scrapy | Overkill for targeted JRA/netkeiba scraping. Scrapy is for large-scale crawling. We need precise data from specific pages. | httpx + BeautifulSoup4 |
| requests-html | Largely unmaintained. Use httpx for fetching and BS4 for parsing. | httpx + BeautifulSoup4 |
| Pandas 1.x | End of life. Missing features like `pyarrow` backend, Copy-on-Write. | pandas 2.3.x |

## Stack Patterns by Variant

**If scraping JRA odds pages that require JavaScript rendering:**
- Use Playwright (headless Chromium) to load the page
- Save raw HTML to `data/raw/` before parsing
- Parse with BeautifulSoup4 + lxml
- This is a fallback; try httpx + BS4 first

**If data volume exceeds ~2GB and pipeline becomes slow:**
- Consider switching from CSV to Parquet for intermediate files (standard/feature layers)
- Consider Polars for heavy data transformations
- Keep pandas for LightGBM compatibility

**If adding more ML models later (Model B/C):**
- scikit-learn provides `Pipeline`, `GridSearchCV`, `cross_val_score`
- LightGBM integrates natively with the scikit-learn API
- Add optuna later for hyperparameter tuning if needed

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| lightgbm 4.6.0 | pandas 2.x, numpy 2.x, scikit-learn 1.9 | Install via `pip install 'lightgbm[scikit-learn]'` for sklearn extras |
| pandas 2.3.x | numpy >=1.23, <2.5 | Check `pyproject.toml` for exact bounds |
| pydantic 2.13.x | Python >=3.9 | No compatibility issues with stack |
| httpx 0.28.x | Python >=3.8 | Stable; 1.0 is in dev (do not use dev versions) |
| pytest 9.0.x | Python >=3.10 | Dropping Python 3.9 support in this version |
| ruff 0.15.x | Python >=3.7 | Standalone Rust binary, no Python version dependency for execution |

## Key Integration Notes

### LightGBM + pandas Categorical Handling
LightGBM handles categorical features natively. Encode categorical columns (競馬場, 騎手, 調教師, 芝ダート) as `pandas.CategoricalDtype` and LightGBM auto-detects them. No one-hot encoding needed. This gives ~8x speed improvement and often better accuracy.

```python
# In feature layer
df["course"] = df["course"].astype("category")
df["jockey"] = df["jockey"].astype("category")
# LightGBM auto-detects pandas CategoricalDtype columns
```

### 3-Layer Data Pipeline
- **raw/**: Original files (Kaggle CSV, scraped HTML)
- **standard/**: Unified schema via Pydantic validation
- **feature/**: Model-ready features (LightGBM Dataset or pandas DataFrame)

### JRA Scraping Architecture
- fetch (httpx/playwright) -> save raw HTML -> parse (BS4) -> normalize -> validate (Pydantic) -> store in standard layer
- Always save raw HTML first to enable re-parsing without re-fetching
- Rate-limit requests (1-2 second delays between page loads)

## Sources

- [PyPI lightgbm](https://pypi.org/project/lightgbm/) — Version 4.6.0 verified (Feb 2025 release)
- [PyPI pandas](https://pypi.org/project/pandas/) — Version 2.3.3 / 3.0.1 verified
- [PyPI numpy](https://pypi.org/project/numpy/) — Version 2.4.0 verified
- [PyPI httpx](https://pypi.org/project/httpx/) — Version 0.28.1 verified (Dec 2024)
- [PyPI pydantic](https://pypi.org/project/pydantic/) — Version 2.13.4 verified (May 2026)
- [PyPI ruff](https://pypi.org/project/ruff/) — Version 0.15.14 verified (May 2026)
- [PyPI loguru](https://pypi.org/project/loguru/) — Current stable verified
- [LightGBM Docs - Categorical Features](https://lightgbm.readthedocs.io/en/latest/Advanced-Topics.html) — Native categorical handling
- [note.com 競馬AI開発シリーズ](https://note.com/dijzpeb/n/n4dc467834532) — JRA odds scraping methodology
- [Zenn 競馬予想で始める機械学習](https://zenn.dev/dijzpeb/books/848d4d8e47001193f3fb/viewer/02_scraping) — netkeiba scraping patterns
- [scikit-learn.org](https://scikit-learn.org/) — Version 1.9.0 verified

---
*Stack research for: JRA三連複EV判定システム*
*Researched: 2026-06-10*
