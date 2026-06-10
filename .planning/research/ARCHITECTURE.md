# Architecture Research

**Domain:** Horse Racing EV Betting System (Trifecta / Sanrenpuku)
**Researched:** 2026-06-10
**Confidence:** HIGH

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CLI Interface Layer                         │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ backtest cmd │  │ evaluate cmd │  │ report cmd (CSV/CLI out) │  │
│  └──────┬───────┘  └──────┬───────┘  └───────────┬──────────────┘  │
│         │                 │                       │                 │
├─────────┴─────────────────┴───────────────────────┴─────────────────┤
│                       Decision Engine Layer                         │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ Model A:     │  │ Model B:     │  │ Model C:                 │  │
│  │ Top3 Prob    │→ │ Value Filter │→ │ Trifecta EV Calculator   │  │
│  │ (LightGBM)   │  │ (Edge Det.)  │  │ (Harville + Kelly)       │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
│         │                 │                       │                 │
├─────────┴─────────────────┴───────────────────────┴─────────────────┤
│                       Feature Engineering Layer                     │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ Race Feats   │  │ Horse Feats  │  │ Jockey/Trainer Stats     │  │
│  │ (course,dist)│  │ (form,weight)│  │ (rolling win %)          │  │
│  └──────┬───────┘  └──────┬───────┘  └───────────┬──────────────┘  │
│         │                 │                       │                 │
├─────────┴─────────────────┴───────────────────────┴─────────────────┤
│                       Data Transformation Layer                     │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              Standard Layer (unified schema)                  │   │
│  │   race / entry / result / odds_trifecta / payoff              │   │
│  └──────────────────────────────────────────────────────────────┘   │
│         │                                           │               │
│  ┌──────┴───────┐                          ┌────────┴───────────┐   │
│  │ Kaggle       │                          │ Scraper Pipeline   │   │
│  │ Converter    │                          │ fetch/parse/norm   │   │
│  └──────────────┘                          └────────────────────┘   │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                          Storage Layer                               │
├──────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ raw/kaggle/  │  │ raw/scrape/  │  │ raw/html/                │  │
│  │ (CSV source) │  │ (fetched)    │  │ (preserved pages)        │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| **Raw Layer** | Store source data as close to original form as possible | CSV files (Kaggle), HTML files (scraped), organized by source and date |
| **Kaggle Converter** | Transform 4 Kaggle CSV files into standard schema | Pandas ETL: read CSV, rename columns, fix types, validate, write Parquet |
| **Scraper Pipeline** | Fetch/parse/normalize 2022+ data from netkeiba/JRA | requests + BeautifulSoup for fetch/parse; separate normalize step |
| **Standard Layer** | Unified schema across Kaggle and scraped data | Parquet files: race, entry, result, odds_trifecta, payoff tables |
| **Feature Engineering** | Derive ML-ready features from standard data | Rolling statistics, encoded categoricals, recent form metrics |
| **Model A (Top3 Prob)** | Predict each horse's probability of finishing in top 3 | LightGBM binary classifier (top3 = label), probability calibration via Platt/Isotonic |
| **Model B (Value Filter)** | Identify horses where model probability exceeds market implied probability | Compare p_model vs 1/odds; flag when edge > threshold |
| **Model C (Trifecta EV)** | Calculate EV for trifecta combinations from candidate horses | Harville formula for joint probability, multiply by trifecta odds, apply Kelly sizing |
| **Backtest Engine** | Walk-forward validation of the full pipeline | Time-series split: train on [start, T], predict on [T, T+window], roll forward |
| **CLI** | Command-line interface for all operations | argparse or Click: `backtest`, `evaluate`, `report` subcommands |
| **Report Output** | CSV and terminal output of results and statistics | Pandas DataFrames to CSV, tabulate for CLI tables |

## Recommended Project Structure

```
keiba-ai-v2/
├── data/
│   ├── raw/                        # Immutable source data
│   │   ├── kaggle/                 # Original 4 CSV files (do not modify)
│   │   ├── scrape/                 # Scraped HTML and extracted data
│   │   │   ├── html/               # Preserved HTML pages
│   │   │   ├── race_list/          # Race calendar/index pages
│   │   │   └── odds/               # Odds pages (all trifecta combinations)
│   │   └── jra_official/           # JRA official site data for validation
│   ├── standard/                   # Unified Parquet tables
│   │   ├── race.parquet            # Race-level: date, course, distance, condition
│   │   ├── entry.parquet           # Horse-level per race: horse, jockey, weight, odds
│   │   ├── result.parquet          # Finishing positions
│   │   ├── odds_trifecta.parquet   # All trifecta combination odds (key table)
│   │   └── payoff.parquet          # Actual trifecta payouts for validation
│   └── feature/                    # ML-ready feature matrices
│       ├── training/               # Feature + label pairs for model training
│       └── prediction/             # Features for upcoming races
├── src/
│   ├── __init__.py
│   ├── cli.py                      # CLI entry point (argparse/Click)
│   ├── pipeline/                   # Data transformation pipeline
│   │   ├── __init__.py
│   │   ├── kaggle_converter.py     # Kaggle CSV → standard Parquet
│   │   ├── scraper.py              # fetch/parse/normalize for netkeiba/JRA
│   │   ├── standardizer.py         # Common schema enforcement + validation
│   │   └── combiner.py             # Merge Kaggle + scraped standard data
│   ├── features/                   # Feature engineering
│   │   ├── __init__.py
│   │   ├── race_features.py        # Course, distance, surface, head count
│   │   ├── horse_features.py       # Recent form, weight, speed figures
│   │   ├── jockey_features.py      # Rolling win/place rates
│   │   ├── trainer_features.py     # Rolling win rates
│   │   └── builder.py              # Assemble all features into training matrix
│   ├── models/                     # ML models
│   │   ├── __init__.py
│   │   ├── top3_predictor.py       # Model A: LightGBM top-3 probability
│   │   ├── calibrator.py           # Probability calibration (Platt/Isotonic)
│   │   ├── value_filter.py         # Model B: edge detection
│   │   └── ev_calculator.py        # Model C: trifecta EV via Harville
│   ├── backtest/                   # Backtesting engine
│   │   ├── __init__.py
│   │   ├── engine.py               # Walk-forward backtest orchestrator
│   │   ├── metrics.py              # ROI, hit rate, max drawdown, monthly stats
│   │   └── portfolio.py            # Bet sizing (fractional Kelly)
│   └── output/                     # Reporting
│       ├── __init__.py
│       ├── csv_writer.py           # CSV export
│       └── cli_display.py          # Terminal table output
├── tests/                          # Unit + integration tests
├── notebooks/                      # Exploratory analysis (not production)
├── pyproject.toml                  # Project config, dependencies
└── docs/
    └── specification.md            # Existing specification
```

### Structure Rationale

- **data/raw/**: Immutable source of truth. Never modify raw files. Kaggle originals stay untouched. Scraped HTML preserved for re-parsing without re-fetching.
- **data/standard/**: Parquet format chosen over CSV for type safety, compression (472MB race_result.csv becomes ~80MB Parquet), and fast columnar reads. The unified schema is the contract between data sources and all downstream components.
- **data/feature/**: Separated from standard because features are model-specific. Different model versions may need different feature sets. Standard layer stays stable.
- **src/pipeline/**: All data acquisition and transformation. The `kaggle_converter` and `scraper` are independent -- they never share code because their input formats differ fundamentally. Both output to the same standard schema.
- **src/features/**: Pure feature derivation from standard data. Each feature module owns its domain (race, horse, jockey, trainer). The `builder` assembles the final matrix.
- **src/models/**: The three-model hierarchy (A→B→C) reflects the data flow: probability first, then edge detection, then combination EV. Each model is a separate module because they have different inputs, outputs, and validation needs.
- **src/backtest/**: Isolated from models so the backtest engine can swap strategies without touching model code. The walk-forward logic belongs here, not in model code.
- **src/output/**: Presentation logic only. Keeps CLI and CSV formatting out of business logic.

## Architectural Patterns

### Pattern 1: Three-Layer Data Architecture (raw → standard → feature)

**What:** Separate data into three immutable layers. Raw stores source data unchanged. Standard normalizes all sources into one schema. Feature derives model inputs from standard.
**When to use:** Always. This is the backbone of the entire system.
**Trade-offs:** More storage (3x data), but enables re-processing without re-fetching and decouples data sources from model code.

**Example:**
```python
# raw/kaggle/19860105-20210731_race_result.csv (472MB, original)
# ↓ kaggle_converter.py
# standard/entry.parquet (unified schema)
# ↓ horse_features.py
# feature/training/entry_features.parquet (ML-ready)

# Standard schema contract:
ENTRY_SCHEMA = {
    "race_id": "str",       # YYYYMMDDCCRR (date + course + race#)
    "horse_id": "str",
    "jockey_id": "str",
    "trainer_id": "str",
    "draw": "int8",         # 枠番
    "horse_number": "int8", # 馬番
    "weight_carried": "float32",  # 斤量
    "horse_weight": "float32",
    "horse_weight_delta": "float32",
    "popularity": "int8",   # 人気
    "win_odds": "float32",  # 単勝オッズ
    "finish_position": "int8",  # 着順 (label)
    "top3_flag": "int8",    # 1 if finish_position <= 3
}
```

### Pattern 2: Pipeline-Per-Source with Shared Output Contract

**What:** Each data source (Kaggle, netkeiba scraper, JRA official) has its own pipeline module. All pipelines output to the identical standard schema. Downstream code never knows which source the data came from.
**When to use:** When merging heterogeneous data sources, which is exactly this project's core challenge (Kaggle 1986-2021 + scraped 2022+).
**Trade-offs:** Slightly more upfront work to define the standard schema early. But once defined, adding new data sources is just a new converter module.

**Example:**
```python
# src/pipeline/kaggle_converter.py
def convert_kaggle_to_standard(kaggle_dir: Path, output_dir: Path):
    """Kaggle 4-CSV → standard Parquet. Runs once."""
    results = pd.read_csv(kaggle_dir / "19860105-20210731_race_result.csv")
    entries = parse_kaggle_entries(results)  # source-specific parsing
    entries.to_parquet(output_dir / "entry.parquet")  # standard output

# src/pipeline/scraper.py
def scrape_to_standard(start_date: date, end_date: date, output_dir: Path):
    """netkeiba → standard Parquet. Incremental."""
    for race_date in date_range(start_date, end_date):
        html = fetch_race_page(race_date)  # fetch
        raw_data = parse_race_html(html)    # parse
        entries = normalize_to_standard(raw_data)  # normalize
        append_to_parquet(output_dir / "entry.parquet", entries)  # same standard output
```

### Pattern 3: Harville-Based Trifecta Probability Derivation

**What:** Use individual horse win probabilities (from Model A) to derive joint trifecta probabilities via the Harville formula, rather than trying to predict trifecta outcomes directly.
**When to use:** This is the standard approach established by Benter (1994) and used in all subsequent academic work. It avoids the combinatorial explosion of predicting n*(n-1)*(n-2)/6 trifecta outcomes directly.
**Trade-offs:** Harville assumes conditional independence (once horse A wins, remaining probabilities renormalize proportionally). This is a known simplification -- horses that "place better than they win" are underestimated. For MVP, Harville is the correct choice. The Stern/Henery models can be explored later as refinements.

**Example:**
```python
def harville_trifecta_prob(p_win: dict[str, float], horse_i: str, horse_j: str, horse_k: str) -> float:
    """
    P(i,j,k all in top3, any order) using Harville.
    
    For trifecta (sanrenpuku = any order of 3 horses):
    P(i,j,k in top3) = sum over all permutations of {i,j,k} of:
        p_i * p_j/(1-p_i) * p_k/((1-p_i)*(1-p_j))
    
    Which simplifies to 6 terms (3! permutations).
    """
    prob = 0.0
    for a, b, c in itertools.permutations([horse_i, horse_j, horse_k]):
        prob += p_win[a] * p_win[b] / (1 - p_win[a]) * p_win[c] / ((1 - p_win[a]) * (1 - p_win[b]))
    return prob

def trifecta_ev(p_trifecta: float, odds: float, takeout: float = 0.0) -> float:
    """EV = estimated probability * payout. Positive = value bet."""
    return p_trifecta * odds - 1.0
```

### Pattern 4: Walk-Forward Backtest with Expanding Window

**What:** Train on all data up to time T, predict on [T, T+window]. Then expand training window to include [T, T+window], predict on next window. Never use future data.
**When to use:** All model evaluation. This is mandatory for time-series data to avoid lookahead bias. Standard k-fold cross-validation is invalid for this domain.
**Trade-offs:** More computationally expensive than a single train/test split. But it is the only reliable way to estimate real-world performance for a betting strategy.

**Example:**
```python
def walk_forward_backtest(data, model_fn, start_year=2015, window_months=6):
    """
    Expanding window walk-forward.
    Train on [1986, T), predict on [T, T+6months), roll forward.
    """
    results = []
    for test_start, test_end in generate_windows(start_year, window_months):
        train = data[data["date"] < test_start]
        test  = data[(data["date"] >= test_start) & (data["date"] < test_end)]
        
        model = model_fn(train)  # Train LightGBM on all data before test window
        predictions = model.predict(test)  # Get top3 probabilities
        
        # Run full EV pipeline on predictions
        bets = evaluate_trifecta_ev(predictions, test)
        results.append(calculate_metrics(bets, test))
    
    return aggregate_results(results)
```

## Data Flow

### Primary Data Flow (Kaggle Historical)

```
data/raw/kaggle/*.csv (4 files, 516MB total)
    ↓ [kaggle_converter.py: read, parse, validate]
data/standard/*.parquet (race, entry, result, odds_trifecta, payoff)
    ↓ [builder.py: join tables, derive features]
data/feature/training/*.parquet (ML-ready matrices)
    ↓ [top3_predictor.py: LightGBM train]
trained model (top3 probabilities for each horse per race)
    ↓ [value_filter.py: compare p_model vs market odds]
candidate horses (horses with positive edge)
    ↓ [ev_calculator.py: Harville trifecta probs * odds]
trifecta bet candidates ranked by EV
    ↓ [engine.py: walk-forward simulate]
backtest results (ROI, hit rate, drawdown)
    ↓ [csv_writer.py / cli_display.py]
output/ CSV and CLI tables
```

### Supplementary Data Flow (2022+ Scraping)

```
netkeiba.com / jra.jp
    ↓ [scraper.py: fetch]
data/raw/scrape/html/ (preserved HTML pages)
    ↓ [scraper.py: parse]
data/raw/scrape/extracted/ (structured JSON/CSV from HTML)
    ↓ [standardizer.py: normalize to shared schema]
data/standard/*.parquet (appended to existing files)
    ↓ [same flow as Kaggle path from here]
```

### Key Data Flows

1. **Kaggle Ingestion:** One-time batch. Read 4 CSVs, validate schemas, convert to 5 standard Parquet tables. The odds_trifecta table is critical -- Kaggle only provides top-3 combinations, so the full-combination odds must come from 2022+ scraped data.

2. **Scraping Ingestion:** Incremental. For each race day: fetch HTML pages (race card, odds, results, payoffs), save raw HTML, parse into structured data, normalize to standard schema, append to Parquet tables. The fetch/parse/normalize separation allows re-parsing from saved HTML without re-fetching.

3. **Feature Derivation:** Read standard Parquet tables, compute rolling statistics (jockey win rate last N races, horse recent form, trainer stats), encode categoricals (course, surface), produce a flat feature matrix with one row per horse-per-race. Label is `top3_flag`.

4. **Model Training:** LightGBM binary classifier. Input is feature matrix. Output is calibrated probability of top-3 finish. Calibration via IsotonicRegression or PlattScaling is essential because raw tree-based model probabilities are poorly calibrated and EV calculation demands well-calibrated probabilities.

5. **Trifecta EV Calculation:** For each race, take all horses with top-3 probability estimates, apply Harville formula to get joint probability for every 3-horse combination (C(n,3) combinations), multiply by trifecta odds for each combination, filter for positive EV, rank by EV, apply point cap.

6. **Backtest Validation:** Walk-forward expanding window. Train model on data up to time T, generate trifecta bets for [T, T+window], compare against actual results and payoffs, accumulate metrics. This is the single most important validation step -- it proves or disproves the entire system.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Development (single user, historical data) | Current architecture is ideal. Parquet files on local disk. CLI for everything. No database needed. |
| Weekly operation (1 user, current season) | Add incremental standard/feature updates. No architecture change. |
| Multi-season accumulation (10+ years) | Parquet handles millions of rows efficiently. Partition standard files by year for faster reads. |
| Hypothetical: real-time operation | Would need: SQLite/DuckDB for query flexibility, scheduled scraper, separate prediction service. Out of scope for MVP. |

### Scaling Priorities

1. **First bottleneck: Full trifecta odds availability.** Kaggle data only has top-3 trifecta combinations per race. For 18-horse fields there are C(18,3)*6 = 4896 combinations but Kaggle only stores 3. Solution: scrape 2022+ data with all combinations; for Kaggle era, derive approximate trifecta odds from Harville probabilities applied to win odds.
2. **Second bottleneck: Feature computation for rolling windows.** Computing jockey/horse recent form over 35 years of data can be slow. Solution: pre-compute rolling features incrementally. Standard layer stores per-race snapshots; feature layer computes deltas.

## Anti-Patterns

### Anti-Pattern 1: Predicting Trifecta Outcomes Directly

**What people do:** Try to build a model that directly predicts which 3 horses will finish in the top 3, treating it as a multi-label classification or generating all C(n,3) combinations.
**Why it's wrong:** For an 18-horse field, there are C(18,3)=816 possible trifecta combinations. With ~3000 races/year, most combinations appear fewer than 5 times in the training data. The model cannot learn meaningfully from such sparse labels.
**Do this instead:** Predict individual horse top-3 probability (binary classification, abundant training data), then derive trifecta probabilities via Harville formula. This is the Benter (1994) approach and is universally accepted in the literature.

### Anti-Pattern 2: Using Raw Odds as Features Without Market Intelligence

**What people do:** Feed win odds directly into the model as a feature alongside other variables.
**Why it's wrong:** Win odds already encode the public's collective prediction, including most of the information from your other features. The model will learn to rely on odds and underweight its own signal, producing probabilities that mirror the market rather than finding edges.
**Do this instead:** Use odds as a comparison benchmark, not as a primary feature. The model should learn from intrinsic factors (form, jockey, course conditions) and its output probabilities are compared against market odds to find discrepancies. If you do include odds, use them as a derived feature (e.g., "odds rank" or "deviation from expected odds based on features") to capture residual information the model cannot replicate from other features.

### Anti-Pattern 3: Standard Cross-Validation for Time-Series Data

**What people do:** Use sklearn's KFold or train_test_split with random shuffling.
**Why it's wrong:** Horse racing data is strongly time-dependent. Training on 2020 data to predict 2015 races is lookahead bias. Track conditions, jockey populations, and betting market efficiency change over time.
**Do this instead:** Always use walk-forward (expanding window) validation. Train only on past data, predict on future data. Chronological ordering is mandatory.

### Anti-Pattern 4: Skipping Probability Calibration

**What people do:** Use LightGBM's raw predict_proba output directly for EV calculation.
**Why it's wrong:** Tree-based models produce poorly calibrated probabilities. A raw output of 0.3 does not mean "30% chance." Since EV = probability * odds, miscalibrated probabilities produce systematically wrong EV estimates. The model may appear to find edges where none exist.
**Do this instead:** Apply IsotonicRegression or PlattScaling calibration after LightGBM training. Validate calibration using reliability diagrams. This is especially critical for EV-based betting systems where small probability errors compound into large EV errors.

### Anti-Pattern 5: Mixing Fetch and Parse in Scraping

**What people do:** Fetch a page from netkeiba, immediately parse it, and store only the parsed result.
**Why it's wrong:** When the parsing logic has a bug or when you want to extract additional fields later, you must re-fetch all pages. This wastes time, risks IP blocking, and may find that the source site has changed or removed the pages.
**Do this instead:** Always save the raw HTML first, then parse from the saved file. The specification already mandates this (fetch/parse/normalize separation). This is non-negotiable.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| **Kaggle Dataset** | One-time CSV download, local processing | 4 files in data/raw/kaggle/. Static, never changes. |
| **netkeiba.com** | HTTP fetch with rate limiting, HTML parsing | Primary source for 2022+ data. Note: netkeiba tightened scraping restrictions around 2024. Respect robots.txt, add delays, avoid parallel requests. |
| **JRA Official (jra.jp)** | HTTP fetch for odds validation | Use to cross-check scraped odds, not as primary source. |
| **LightGBM** | Python library via pip | Core ML engine. Deterministic training with fixed seed. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| raw → standard | File-based (CSV/HTML → Parquet) | One-way transformation. Standard never writes back to raw. |
| standard → feature | File-based (Parquet → Parquet) | Feature layer reads standard, writes to feature/. |
| feature → models | In-memory (Pandas DataFrame) | Features loaded into memory for LightGBM training/prediction. |
| models → backtest | In-memory (numpy arrays) | Model outputs passed directly to backtest engine. |
| backtest → output | File-based (CSV) + stdout | Results persisted as CSV, displayed via CLI. |

## Build Order (Component Dependencies)

The build order follows the data flow. Each component depends on the previous one being complete.

```
Phase 1: Data Foundation (no dependencies)
  ├── raw/kaggle/ (exists already)
  └── Kaggle data understanding (explore, document columns, find quirks)

Phase 2: Standard Layer (depends on Phase 1)
  ├── Define standard schema (race, entry, result, odds_trifecta, payoff)
  ├── kaggle_converter.py (Kaggle CSV → standard Parquet)
  └── Validate: can we answer "what was the trifecta payout for race X?"

Phase 3: Scraping Pipeline (parallel with Phase 2, depends on Phase 1)
  ├── scraper.py: fetch HTML → save raw
  ├── scraper.py: parse HTML → structured data
  ├── standardizer.py: structured data → standard Parquet
  └── combiner.py: merge Kaggle + scraped standard data

Phase 4: Feature Engineering (depends on Phase 2)
  ├── race_features.py
  ├── horse_features.py (recent form, weight changes)
  ├── jockey_features.py (rolling win rates)
  ├── trainer_features.py
  └── builder.py (assemble feature matrix)

Phase 5: Model A - Top3 Probability (depends on Phase 4)
  ├── top3_predictor.py (LightGBM training)
  ├── calibrator.py (probability calibration)
  └── Validate: compare model probabilities vs popularity-based baseline

Phase 6: Model B + C - Value Filter and EV Calculator (depends on Phase 5)
  ├── value_filter.py (edge detection: p_model vs 1/odds)
  ├── ev_calculator.py (Harville trifecta probability * odds)
  └── Validate: does the system identify positive-EV trifecta combinations?

Phase 7: Backtest Engine (depends on Phase 6)
  ├── engine.py (walk-forward orchestrator)
  ├── metrics.py (ROI, hit rate, drawdown)
  ├── portfolio.py (Kelly bet sizing)
  └── Validate: walk-forward backtest over full time range

Phase 8: CLI and Reporting (depends on Phase 7)
  ├── cli.py (argparse/Click interface)
  ├── csv_writer.py
  └── cli_display.py
```

### Critical Path Analysis

The critical path is: **Standard Schema → Kaggle Converter → Feature Builder → Model A → EV Calculator → Backtest**.

The scraping pipeline (Phase 3) runs in parallel with Phase 2-4 but must complete before Phase 7 because the backtest needs 2022+ data for meaningful validation.

The most important single decision is the **standard schema definition** in Phase 2. Getting this wrong means rewriting every downstream component. Invest time here.

## Sources

- [Benter (1994) - Computer Based Horse Race Handicapping and Wagering Systems](https://gwern.net/doc/statistics/decision/1994-benter.pdf) - Foundational architecture for probability-based horse racing systems. HIGH confidence.
- [Teddy Koker - Beating the Odds: ML for Horse Racing](https://teddykoker.com/2019/12/beating-the-odds-machine-learning-for-horse-racing/) - Softmax-based probability estimation with shared rating network. HIGH confidence.
- [Harville (1973) - Assigning probabilities to multi-entry competition outcomes](https://math.stackexchange.com/questions/842604/given-every-horses-probability-of-winning-a-race-what-is-the-probability-that) - Trifecta probability derivation from win probabilities. HIGH confidence.
- [Zenn - Expected Value Engine Architecture](https://zenn.dev/mojya/articles/964724219009cc) - Real-world Japanese horse racing EV engine with Python pipeline. MEDIUM confidence (blog post, not peer-reviewed).
- [Enigmo Tech Blog - Rank Learning for Horse Racing](https://tech.enigmo.co.jp/entry/2020/12/09/100000) - Japanese trifecta prediction with ML, ROI evaluation. MEDIUM confidence.
- [Kaggle - Feature Engineering in Horse Racing](https://www.kaggle.com/code/hrosebaby/feature-engineering-in-horse-racing) - Practical feature engineering notebook. MEDIUM confidence.
- [ResearchGate - Ensemble Learning for Horse Racing Predictions](https://www.researchgate.net/publication/385301910_Optimizing_Horse_Racing_Predictions_through_Ensemble_Learning_and_Automated_Betting_Systems) - Academic paper on ensemble methods + automated betting. MEDIUM confidence.
- [SciKit-Learn - Probability Calibration](https://scikit-learn.org/stable/modules/calibration.html) - Official documentation on calibration methods. HIGH confidence.
- [Zenn - Scraping for Horse Racing AI](https://zenn.dev/dijzpeb/books/848d4d8e47001193f3fb/viewer/02_scraping) - netkeiba scraping patterns in Python. MEDIUM confidence.
- [Specification Document](file:///Users/hart/develop/keiba-ai-v2/docs/specification.md) - Project specification v1.1, defining the 3-layer architecture and model hierarchy. HIGH confidence (project source of truth).

---
*Architecture research for: JRA Trifecta EV Betting System*
*Researched: 2026-06-10*
