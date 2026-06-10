# Project Research Summary

**Project:** JRA三連複EV判定システム (JRA Trifecta Expected Value Judgment System)
**Domain:** Horse racing ML prediction + expected value betting system
**Researched:** 2026-06-10/11
**Confidence:** HIGH

## Executive Summary

This project is a personal, CLI-based horse racing expected value system focused exclusively on JRA trifecta (三連複) betting. The domain is well-established in both academic literature (Benter 1994, Harville 1973) and practical Japanese development communities (note.com, Zenn). The recommended approach follows a proven three-model pipeline: Model A predicts each horse's top-3 finish probability via LightGBM, Model B identifies horses where the model probability exceeds market-implied probability (edge detection), and Model C combines candidate horses into trifecta combinations with EV calculated via the Harville conditional probability formula. The entire system is validated through walk-forward backtesting with expanding windows -- the single most important quality gate.

The critical architectural decision is the three-layer data architecture (raw/standard/feature) that separates immutable source data from a unified schema from model-ready features. This pattern, combined with the pipeline-per-source approach, cleanly handles the core data challenge: merging 35 years of Kaggle historical data (1986-2021) with incrementally scraped 2022+ data into a single training corpus. Python with LightGBM, pandas, and Pydantic is the right stack -- LightGBM's native categorical feature support is a significant advantage for this domain's many categorical variables (course, jockey, trainer, surface).

The primary risks are not technical but methodological. The most dangerous pitfall is data leakage: including post-race information (final odds, finishing position, running times) in training features, which produces unrealistically high AUC scores that collapse in production. A secondary risk is the "accuracy-ROI inversion" where improving AUC actually degrades betting returns because the model optimizes for the 96% of samples with EV < 1 rather than the critical 4% that drive actual bets. Both are preventable with strict feature auditing (pre-race vs. post-race column classification), temporal cross-validation, and ROI-first evaluation metrics.

## Key Findings

### Recommended Stack

The stack is Python-centric with LightGBM as the ML engine and file-based storage (CSV/Parquet). No database is needed at this scale. Poetry manages dependencies. The stack is constrained by the project specification (Python 3.12+, LightGBM) and validated by community practice.

**Core technologies:**
- **LightGBM 4.6.0:** ML model for top-3 probability prediction -- native categorical support (~8x faster than one-hot encoding), dominant in tabular data ML
- **pandas 2.3.x:** Data processing and CSV/Parquet I/O -- best LightGBM integration, `CategoricalDtype` auto-detected by LightGBM
- **Pydantic 2.13.x:** Data validation across the 3-layer pipeline -- catch data quality issues at standard layer boundaries
- **httpx + BeautifulSoup4 + lxml:** Scraping for 2022+ odds data -- httpx for async-capable HTTP, BS4+lxml for fast HTML parsing
- **scikit-learn 1.9.0:** Train/test splitting (TimeSeriesSplit), metrics, probability calibration -- integrates natively with LightGBM
- **Poetry 2.x + ruff + pytest + mypy:** Development toolchain -- single dependency manager, fast linting, type safety

**Critical version note:** pandas 3.0 should be avoided (breaking changes); stick with 2.3.x. Playwright is a fallback-only dependency for JavaScript-rendered pages; try httpx+BS4 first.

### Expected Features

The feature set is clearly tiered. MVP goal is "backtest completion" -- proving whether the system generates positive ROI over historical data.

**Must have (table stakes -- P1):**
- 3着内確率予測モデル (Model A) -- the core ML model; LightGBM binary classifier predicting top-3 finish
- 全通り三連複オッズ取得 -- C(18,3)=816 combinations per race; scraping required for full odds
- 期待値(EV)計算・足切り -- EV = probability * odds; filter for EV > threshold
- 時系列バックテスト -- walk-forward expanding window validation; the MVP's proof of concept
- 回収率・的中率・ドローダウン出力 -- quantitative evaluation of backtest results
- 人気順ベースライン比較 -- model must beat naive popularity-based predictions
- 3層データパイプライン (raw/standard/feature) -- data foundation for everything
- CLI/CSV出力 -- primary interface per project specification

**Should have (competitive -- P2):**
- 確率キャリブレーション -- Platt scaling or isotonic regression; critical for EV accuracy but can be added after initial backtest
- 2022年以降データスクレイピング -- extend data beyond Kaggle's 2021 cutoff
- 「見送り」判定の閾値最適化 -- data-driven EV threshold for skipping races
- Model B (割安馬判定) -- explicit edge detection between model and market

**Defer (v2+ -- P3):**
- 血統・ラップ・調教コメント特徴量 -- save to raw layer now, use in models later
- Henery/Stern確率モデル -- improved trifecta probability over Harville
- リアルタイム直前オッズ取得 -- requires browser automation and monitoring
- ケリー基準による資金管理 -- optimal bet sizing
- 自動投票, Web UI, 全券種対応 -- explicitly out of scope per PROJECT.md

### Architecture Approach

The system follows a layered pipeline architecture with strict one-way data flow: raw files (immutable) are converted to a unified standard schema (Parquet), which feeds feature engineering, which feeds the three-model hierarchy (A: probability, B: edge detection, C: trifecta EV), validated by a walk-forward backtest engine. Each data source (Kaggle, scraper) has its own converter but outputs to the identical standard schema contract.

**Major components:**
1. **Data Transformation Layer** (raw/standard/feature) -- three-layer separation; raw is immutable, standard is the unified schema contract, feature is model-specific
2. **Feature Engineering Layer** -- race features, horse form, jockey/trainer rolling statistics; categorical encoding via pandas CategoricalDtype
3. **Decision Engine Layer** -- Model A (LightGBM top-3 probability) -> Model B (value filter) -> Model C (Harville trifecta EV)
4. **Backtest Engine** -- walk-forward expanding window; ROI, hit rate, max drawdown metrics
5. **CLI/Output Layer** -- Click-based CLI, CSV export, terminal display

**Key architectural decision:** The standard schema (race, entry, result, odds_trifecta, payoff) is the most important single design choice. Getting it wrong means rewriting every downstream component.

### Critical Pitfalls

1. **データリーク (data leakage via future information)** -- Post-race columns (final odds, finishing position, running time) in training features produce fake AUC > 0.80. Prevent with explicit DROP_COLS list and audit every feature: "could I compute this 10 minutes before race start?"
2. **精度向上とROI低下のパラドックス (accuracy-ROI inversion)** -- Improving AUC can decrease betting ROI because LightGBM optimizes the 96% bulk, not the 4% high-EV tail. Prevent with EV-weighted sample training (sigmoid-based weights from OOF predictions) and ROI as the primary metric.
3. **時系列無視のランダムCV (temporal leakage in cross-validation)** -- Standard KFold trains on future data. Always use TimeSeriesSplit or year-based walk-forward splits. Recovery cost: medium (re-partition + retrain).
4. **オッズ特徴量による人気追従 (odds as feature causing popularity echo)** -- Including odds as a model feature makes predictions mirror the market, finding zero edge. Use odds ONLY in the post-model EV calculation step, never as input features.
5. **三連複確率の独立仮定 (naive independence for trifecta probability)** -- P(A)*P(B)*P(C) is wrong. Use the Harville conditional probability formula: P(i,j,k) = p_i * p_j/(1-p_i) * p_k/(1-p_i-p_j), summed over all 6 permutations for 三連複.

## Implications for Roadmap

Based on the combined research, the following phase structure is recommended. The ordering follows strict data dependencies: you cannot train a model without features, you cannot build features without a standard schema, and you cannot validate the system without a backtest engine.

### Phase 1: Data Foundation
**Rationale:** Everything depends on understanding and standardizing the Kaggle data. This is the most important phase to get right -- the standard schema contract shapes all downstream work.
**Delivers:** Raw data documented, standard schema defined, Kaggle data converted to standard Parquet, pre-race vs. post-race columns classified.
**Addresses:** 3層データパイプライン, Kaggleデータ理解・standard変換 (from FEATURES.md P1)
**Avoids:** データリーク (PITFALLS #3) -- column classification prevents leakage at the source
**Key decisions:** Standard schema (race, entry, result, odds_trifecta, payoff), column naming convention, Parquet partitioning strategy

### Phase 2: Feature Engineering
**Rationale:** Model A needs ML-ready features derived from the standard layer. Feature quality determines model quality. This phase must implement temporal-aware rolling statistics.
**Delivers:** Feature builder producing training matrices with race, horse, jockey, and trainer features. Categorical encoding via pandas CategoricalDtype. `.shift(1)` enforced on all rolling calculations.
**Uses:** pandas 2.3.x (categorical support), Pydantic (feature schema validation)
**Implements:** Feature Engineering Layer from architecture
**Avoids:** データリーク via .shift(1) enforcement (PITFALLS #3), オッズ特徴量 by excluding odds from features (PITFALLS #7)

### Phase 3: Model A -- Top-3 Probability
**Rationale:** The core ML model. Must beat popularity baseline. Requires temporal CV from day one.
**Delivers:** LightGBM binary classifier predicting top-3 finish probability, trained with TimeSeriesSplit, evaluated against popularity baseline. Probability calibration via Platt scaling or isotonic regression.
**Uses:** LightGBM 4.6.0 (native categoricals), scikit-learn 1.9.0 (TimeSeriesSplit, metrics)
**Avoids:** 時系列CV漏れ (PITFALLS #6), 精度ROI逆転 (PITFALLS #1) via ROI evaluation alongside AUC, OOF忘れ (PITFALLS #2) via OOF infrastructure built into training pipeline

### Phase 4: Trifecta EV Calculation
**Rationale:** Combines Model A probabilities with odds data to compute trifecta combination EV. This is where the system generates its value proposition.
**Delivers:** Harville-based trifecta probability calculation, EV computation for all C(n,3) combinations per race, EV threshold filtering, point cap enforcement.
**Uses:** Model A probabilities, odds data from standard layer
**Avoids:** 三連複独立仮定 (PITFALLS #4) via correct Harville implementation, validates against historical trifecta hit rates

### Phase 5: Scraping Pipeline
**Rationale:** Extends data coverage beyond Kaggle's 2021 cutoff. Can be developed in parallel with Phases 2-4 but must complete before Phase 6 (backtest needs 2022+ data for meaningful validation). For MVP, the backtest can run on Kaggle data alone; scraping enriches later.
**Delivers:** Scraper for JRA/netkeiba odds pages, fetch/parse/normalize separation with raw HTML preservation, standard schema output matching Kaggle converter.
**Uses:** httpx + BeautifulSoup4 + lxml (primary), Playwright (fallback only)
**Avoids:** Aggressive scraping causing IP ban (rate limiting, polite delays), fetch-parse mixing (PITFALLS anti-pattern #5)

### Phase 6: Walk-Forward Backtest Engine
**Rationale:** The MVP proof. Validates the entire pipeline end-to-end. Only meaningful once Model A and EV calculation are complete.
**Delivers:** Walk-forward expanding window backtest over full time range. ROI, hit rate, max drawdown, bet count statistics. CSV/CLI output of results. Popularity baseline comparison.
**Uses:** All prior components, scikit-learn metrics
**Avoids:** 確定オッズ罠 (PITFALLS #5) by documenting which odds version is used, applies conservative discount if only final odds available

### Phase 7: CLI and Reporting
**Rationale:** Polish the interface. Not critical path but necessary for usability.
**Delivers:** Click-based CLI with backtest, evaluate, report subcommands. CSV output. Terminal table display.
**Uses:** Click 8.x, pandas to_csv

### Phase Ordering Rationale

- Phases 1-4 are strictly sequential due to data dependencies (schema -> features -> model -> EV)
- Phase 5 (scraping) can be developed in parallel with Phases 2-4; it feeds into Phase 6 when 2022+ validation data is needed
- Phase 6 depends on everything above it -- it is the integration test of the entire system
- Phase 7 is a polish phase that can be interleaved with earlier phases for incremental usability
- The critical path is: Standard Schema -> Kaggle Converter -> Feature Builder -> Model A -> EV Calculator -> Backtest

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3 (Model A):** EV-weighted sample training is a niche technique; the sigmoid-based weight formula needs tuning. OOF prediction infrastructure is non-trivial. Consider `/gsd-plan-phase --research-phase 3`.
- **Phase 4 (Trifecta EV):** Harville model implementation for 三連複 specifically requires summing over 6 permutations. Validation against historical trifecta frequencies needs careful design. Consider `/gsd-plan-phase --research-phase 4`.
- **Phase 5 (Scraping):** netkeiba has tightened anti-scraping measures. JRA official site structure may have changed. Scraping patterns need current verification. Consider `/gsd-plan-phase --research-phase 5`.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Data Foundation):** Well-documented pandas ETL patterns. Kaggle CSV structure is static.
- **Phase 2 (Feature Engineering):** Standard rolling statistics, categorical encoding. Well-established LightGBM patterns.
- **Phase 6 (Backtest Engine):** Walk-forward validation is well-documented. Metrics computation is straightforward.
- **Phase 7 (CLI/Reporting):** Click CLI and pandas CSV output are trivially standard.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Technologies verified against PyPI versions. LightGBM + pandas categorical integration confirmed in official docs. Stack is constrained by project specification. |
| Features | HIGH | Feature tiers derived from competitor analysis (ROBOTIP, SPAIA, VUMA) and Japanese horse racing AI development community. MVP scope clearly bounded. |
| Architecture | HIGH | Three-layer data architecture is established best practice. Three-model hierarchy (A->B->C) follows Benter (1994) and is standard in academic literature. |
| Pitfalls | HIGH | Seven critical pitfalls documented with specific Japanese domain sources (note.com, Zenn). Warning signs and recovery strategies provided for each. |

**Overall confidence:** HIGH

The research is unusually well-supported for a personal project. The Japanese horse racing ML community has produced extensive practical documentation, and the academic literature (Benter, Harville, Stern, Henery) provides rigorous foundations. The main uncertainty is not "how to build this" but "will it generate positive ROI" -- which is the correct uncertainty to have, since answering it is the project's purpose.

### Gaps to Address

- **Kaggle odds column semantics:** The exact meaning of "odds" columns in the Kaggle dataset (発走時 vs 確定 vs 最終) must be verified during Phase 1 by cross-referencing against known race results. This cannot be resolved by research alone.
- **Harville bias magnitude:** The systematic bias of the Harville model (overestimates favorites, underestimates longshots) is documented but its impact on EV accuracy for this specific dataset is unknown. Phase 4 should include validation against actual trifecta hit rates to quantify the bias.
- **Optimal EV threshold:** The cutoff for "positive EV" bets is a key parameter that cannot be determined by research. It must be calibrated during Phase 6 (backtesting) using the walk-forward results.
- **netkeiba scraping viability:** netkeiba has reportedly tightened anti-scraping measures. The feasibility of large-scale scraping for 2022+ data may need to pivot to JRA official pages or JRA-VAN Data Lab during Phase 5.

## Sources

### Primary (HIGH confidence)
- Benter (1994) -- Computer Based Horse Race Handicapping and Wagering Systems -- foundational architecture for probability-based horse racing systems
- Harville (1973) -- Assigning probabilities to multi-entry competition outcomes -- trifecta probability derivation from win probabilities
- LightGBM Official Docs -- Native categorical feature handling, scikit-learn API integration
- scikit-learn.org -- Probability calibration (IsotonicRegression, CalibratedClassifierCV), TimeSeriesSplit
- PyPI package registries -- Version verification for LightGBM 4.6.0, pandas 2.3.x, NumPy 2.x, Pydantic 2.13.x
- PROJECT.md / specification.md -- Project constraints and architectural requirements

### Secondary (MEDIUM confidence)
- note.com/dijzpeb -- JRA odds scraping methodology, EV-weighted training, OOF prediction methodology
- Zenn 競馬予想で始める機械学習 -- netkeiba scraping patterns, feature engineering, data leakage prevention
- note.com/ra_lab_keiba -- Evaluation pitfalls in horse racing AI
- ウマニティ ROBOTIPスーパー -- Commercial competitor feature analysis
- SPAIA競馬, VUMA -- Commercial competitor feature analysis
- Zenn Expected Value Engine Architecture -- Real-world Japanese horse racing EV engine with Python pipeline

### Tertiary (LOW confidence)
- YouTube 予測精度を上げたのに回収率が下がる -- AUC-ROI inversion phenomenon (video source, not verifiable text)
- note.com 競馬AIで「回収率150%」はなぜ嘘なのか -- Backtest high-ROI trap (opinion piece)
- Kaggle Feature Engineering in Horse Racing -- Practical notebook (community quality, not peer-reviewed)

---
*Research completed: 2026-06-10/11*
*Ready for roadmap: yes*
