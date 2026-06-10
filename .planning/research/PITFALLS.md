# Pitfalls Research

**Domain:** JRA三連複EV判定システム (Horse Racing Trifecta Expected Value System)
**Researched:** 2026-06-11
**Confidence:** HIGH

## Critical Pitfalls

### Pitfall 1: Prediction Accuracy Improves But ROI Declines (精度向上と回収率低下のパラドックス)

**What goes wrong:**
Model AUC and logloss metrics improve during development, but the actual ROI (回収率) from backtesting decreases. The model gets better at classifying all horses, but this improvement concentrates on the 96% of data where EV < 1 -- the region that never drives bet selection. The critical 4% of data where EV >= 1 does not improve or even degrades.

**Why it happens:**
LightGBM optimizes logloss uniformly across all samples. Since 96% of horses have EV < 1, the model naturally focuses on getting the bulk of predictions right. The optimizer has no incentive to specialize in the high-EV tail where actual betting decisions are made. This is a structural mismatch between the loss function and the business objective.

**How to avoid:**
- Use sample weighting (LightGBM `weight=` parameter) to emphasize high-EV regions during training
- Implement sigmoid-based EV-to-weight conversion: `w(ev) = 1 + sigmoid((ev - center) / tau)` with parameters like center=0.9, tau=0.02
- Use OOF (Out-of-Fold) predictions to compute weights -- never use in-sample predictions for weight calculation, as they are overfitted
- Evaluate with ROI as the primary metric, not AUC
- Plot ROI vs. model confidence thresholds to find the optimal operating point

**Warning signs:**
- AUC improves from 0.65 to 0.70 but backtest ROI drops from 95% to 85%
- Model predicts favorites accurately but misses longshots that drive EV
- Training loss keeps decreasing while validation ROI plateaus or declines

**Phase to address:**
Phase where Model A (3着内確率) is built and evaluated -- the evaluation framework must include ROI from the start, not just classification metrics.

---

### Pitfall 2: Using Training-Data Predictions for Weight Calculation (OOF忘れによる自己過学習)

**What goes wrong:**
When implementing sample weighting by EV, the developer trains a model without weights, then uses that model's predictions on the training data itself to compute EV and derive weights for a second training pass. The resulting model appears to work but performs poorly on truly unseen data.

**Why it happens:**
LightGBM memorizes training patterns. A horse that won with true probability 5% at odds of 15x might get an in-sample predicted probability of 20%, inflating its EV from 0.75 to 7.5. This horse incorrectly receives high weight, distorting the entire weighting scheme. The model ends up optimizing for "samples I happened to overfit on" rather than "samples that truly have high EV in production."

**How to avoid:**
- Use Out-of-Fold (OOF) prediction exclusively for weight calculation
- For each time period, train on all prior data and predict on the held-out period
- Combine OOF predictions across all folds to compute weights for the final model
- Never pass the same data through both training and weight-computation paths

**Warning signs:**
- Training-set predictions are systematically more confident than validation-set predictions
- The weight distribution is heavily skewed toward known winners
- A "weighted retrain" shows dramatic improvement that vanishes on new data

**Phase to address:**
Phase where Model A training pipeline is established -- OOF infrastructure must be built into the training architecture from day one.

---

### Pitfall 3: Data Leakage via Future Information in Features (未来情報リーク)

**What goes wrong:**
Features that are only available after race completion (final odds, finishing position, running time, race-level aggregate statistics) are included in training data. The model appears extremely accurate during backtesting but is completely useless in production because the same features are unavailable at prediction time.

**Why it happens:**
The Kaggle dataset contains both pre-race and post-race information in the same rows. When computing rolling averages or group statistics, it is easy to accidentally include the current race's result. For example, `df.groupby('horse_id')['rank'].expanding().mean()` without `.shift(1)` includes the current race outcome.

Specific leakage vectors in this project:
- **最終オッズ (final odds):** Only available after betting closes, not at prediction time
- **着順 (finishing position):** The literal answer -- must never be a feature
- **走破タイム (finish time):** Only known after the race
- **上がり3F:** Post-race measurement
- **通過順 (passing order):** Known only after race completion
- **レース内平均タイム:** Uses all horses' times from the current race

**How to avoid:**
- Maintain a strict `DROP_COLS` list in configuration that enforces feature exclusion
- Use `.shift(1)` for all rolling/expanding window calculations on per-horse time series
- For race-level features, only use information from prior races at the same meeting
- Audit every feature by asking: "Could I compute this 10 minutes before the race starts?"
- Implement a "fingerprint" system that records which columns the model expects, preventing column drift between training and prediction

**Warning signs:**
- AUC above 0.80 (unrealistically high for horse racing -- typical good range is 0.65-0.70)
- Training AUC significantly above 0.75
- Backtest ROI consistently above 150% without a clear explanation
- The same model that shows 120% ROI in backtesting predicts poorly on the most recent weekend's races

**Phase to address:**
Phase 1 (data pipeline / feature engineering) -- this must be addressed at the raw-to-feature transformation layer. Recovery from leakage at later phases requires full retraining.

---

### Pitfall 4: Naive Independence Assumption for Trifecta Probability (三連複確率の独立仮定ミス)

**What goes wrong:**
The system computes trifecta (三連複) probability by simply multiplying three individual "top-3 finish" probabilities: P(A, B, C) = P(A) * P(B) * P(C). This assumes finishing positions are independent, which they are not. The resulting EV calculations are systematically biased.

**Why it happens:**
The Harville model provides a simple conditional probability formula:
`P(i,j,k) = p_i * [p_j / (1 - p_i)] * [p_k / (1 - p_i - p_j)]`

Many developers either do not know this formula or implement it incorrectly. Even the Harville model itself has known systematic biases:
- It **overestimates** probabilities for favorite combinations
- It **underestimates** probabilities for longshot combinations
- It assumes that conditional probabilities scale proportionally after removing a horse

For 三連複 (order-independent), you must sum over all 6 permutations of the 3 horses, not just pick one ordering.

**How to avoid:**
- Implement the Harville formula correctly, including the conditional probability chain
- For 三連複, sum P(i,j,k) over all 6 permutations of the 3 selected horses
- Validate against historical trifecta frequencies -- if your model says a combination has 1% probability but historically it hits 0.3%, the model is biased
- Consider the Henery model or Stern model as alternatives if Harville shows systematic bias
- Use Platt scaling or isotonic regression on the combined probability output

**Warning signs:**
- Model EV is systematically higher for favorite-heavy combinations than actual payout data suggests
- Backtested hit rate for longshot trifectas is much lower than predicted probability
- The sum of all predicted trifecta probabilities across all combinations does not equal 1.0
- EV calculations produce many "attractive" bets that all cluster around similar combinations

**Phase to address:**
Phase where Model C (三連複EV判定) is built -- the probability combination logic is the core of this phase.

---

### Pitfall 5: Using Final Odds (確定オッズ) in Backtesting Instead of Real-Time Odds (直前オッズ)

**What goes wrong:**
The backtest uses the final confirmed odds from the Kaggle dataset (確定オッズ) as the denominator in EV calculations. In reality, when a bettor places a wager, they face the odds at that moment -- typically 1-2 minutes before race start. The final odds often differ significantly, especially due to computer-assisted betting in the last minute.

**Why it happens:**
The Kaggle odds CSV likely contains only the final (confirmed) odds. These are the most readily available numbers. But professional computer bettors systematically move odds in the final minutes, concentrating action on likely winners. A horse showing 15x odds when you bet might close at 6x after late money pours in.

**How to avoid:**
- Clearly distinguish between "確定オッズ" (final odds) and "直前オッズ" (pre-race odds) in your data model
- For backtesting, if only final odds are available, apply a conservative discount (e.g., reduce predicted EV by 10-20%) to account for adverse odds movement
- For the 2022+ scraping pipeline, capture odds at multiple time points (e.g., 10 min before, 5 min before, 1 min before)
- Document which odds version each data source provides
- When reporting backtest results, always note "based on final odds" as a caveat

**Warning signs:**
- Backtest ROI looks excellent (130%+) but paper-trading with live odds loses money
- The system's "best bets" consistently see odds compression in the final minutes
- You are using odds from the same Kaggle CSV column without checking what point-in-time they represent

**Phase to address:**
Phase 1 (data understanding) -- document what odds the Kaggle dataset provides. Phase 2 (scraping) -- design the scraper to capture odds at multiple timepoints.

---

### Pitfall 6: Temporal Data Leakage in Cross-Validation (時系列無視のランダムCV)

**What goes wrong:**
The developer uses standard KFold cross-validation with `shuffle=True` or random train/test splits. This means 2024 data might appear in training while 2023 data appears in testing. The model learns patterns from the future and applies them to the past.

**Why it happens:**
sklearn's `KFold` and `train_test_split` default to random splitting. This is standard practice for i.i.d. data but catastrophically wrong for time-series data like horse racing. Horse racing has temporal dynamics: jockey form, track bias, training methods, and even the betting population's behavior evolve over years.

**How to avoid:**
- Use `TimeSeriesSplit` from sklearn or manual year-based splits (train: before year X, test: year X)
- Implement walk-forward validation: train on all data up to year Y, predict year Y+1, slide forward
- Never use data from the future to predict the past
- Add a time gap (embargo period) between training and test windows to prevent information bleeding at boundaries

**Warning signs:**
- Cross-validation scores are suspiciously high but a simple "train on 2020, test on 2021" evaluation is much lower
- The model appears to predict longshots well in CV but not in forward testing
- Feature importance shows suspicious reliance on features that might encode temporal patterns

**Phase to address:**
Phase where Model A is trained and evaluated -- the evaluation framework must use temporal splitting from the start.

---

### Pitfall 7: Odds-as-Feature Leading to "Popularity Echo" (オッズ特徴量による人気追従)

**What goes wrong:**
Including odds (単勝オッズ) or popularity rank (人気) as features causes the model to simply echo the market's assessment. The model learns "low odds = likely winner" and produces predictions that mirror the odds board. This yields high AUC but zero edge -- the model cannot find undervalued horses because it has learned to trust the market.

**Why it happens:**
Odds are the strongest single predictor of race outcomes. LightGBM will heavily weight this feature and use it as the primary splitting criterion. The model effectively becomes a noisy version of the odds board.

**How to avoid:**
- **Do NOT include odds or popularity as model features** during training
- Use odds exclusively in the post-model EV calculation step: `EV = predicted_probability * odds`
- If you must include market information, use derived features (e.g., "deviation from expected odds based on form") rather than raw odds
- Validate that the model can identify horses where its prediction diverges from the market -- this divergence IS the edge

**Warning signs:**
- Model predictions are almost perfectly correlated with popularity ranking (Spearman rho > 0.95)
- Feature importance shows odds/popularity as the top feature by a large margin
- Removing odds from features causes a large AUC drop but improves ROI
- The model never predicts that a 10th-favorite horse has higher win probability than the 3rd-favorite

**Phase to address:**
Phase where features are defined for Model A -- feature selection must explicitly exclude odds. The PROJECT.md already notes this correctly, but enforcement during implementation is critical.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Using 確定オッズ for EV in backtest | Quick first backtest result | Overestimated ROI; false confidence in the model | First prototype only -- must flag as "approximate" |
| Random KFold split for fast validation | Faster iteration, higher CV scores | Temporal leakage; model fails in production | Never -- use TimeSeriesSplit even in early prototyping |
| Skipping calibration (Platt scaling) | Simpler pipeline | EV calculations based on uncalibrated probabilities are unreliable | Only if model output is used for ranking, not EV calculation |
| Hardcoding feature columns | Quick to implement | Column drift between training and prediction; One-Hot mismatch errors | Never -- use a schema/fingerprint system |
| Storing only final odds, not time-series odds | Smaller data, simpler scraping | Cannot study or adjust for odds movement | MVP only -- plan to capture multi-timepoint odds |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Kaggle race_result.csv | Assuming all columns are pre-race data; 着順・走破タイム・上がり・通過順 are post-race | Audit each column; label as pre-race or post-race; build explicit exclusion lists |
| Kaggle odds.csv | Using the top-3 三連複 odds as representative of all combinations | Recognize that only 3 combinations are provided; 2022+ scraping must capture all combinations |
| JRA scraping (2022+) | Aggressive parallel requests causing IP ban; scraping netkeiba which is now heavily protected | Rate-limit requests; save raw HTML; respect robots.txt; consider JRA-VAN Data Lab as an alternative for stable access |
| netkeiba scraping | Using netkeiba at all for current data | netkeiba has strengthened anti-scraping measures; JRA official odds pages or JRA-VAN are more sustainable sources |
| JRA IPAT odds | Assuming IPAT odds match final odds | IPAT scraping has reported anomalous "過剰オッズ" (excess odds) issues; validate data quality carefully |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| 三連複全通りオッズ computation | 18 horses = C(18,3) = 816 combinations per race; slow EV calculation | Pre-filter by Model A probability threshold; only compute EV for horses above top-3 probability threshold | When computing EV for every possible trifecta combination in a full field |
| Feature computation with expanding windows | Slow re-computation for each horse's rolling stats | Cache feature tables; use incremental computation; pre-compute per-horse features before race-day | Beyond ~50,000 rows with complex rolling features |
| Backtesting with daily retraining | Full retrain per race day is extremely slow | Use warm-start or incremental learning; only retrain weekly/monthly | When attempting walk-forward with daily model updates |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Hardcoding scraping credentials or session tokens | Exposure if code is shared; session hijacking | Use environment variables; store in .env files excluded from git |
| Aggressive scraping without rate limiting | IP ban from JRA/netkeiba; legal risk | Implement polite delays (2-5 seconds between requests); respect rate limits; use session management |
| Storing scraped HTML with personal session data | Accidental leak of cookies/tokens | Strip HTTP headers before saving; store only the body content |

## UX Pitfalls (CLI/CSV Output)

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Outputting only EV without confidence | User cannot distinguish between "EV 1.2 with high certainty" and "EV 1.2 with wild uncertainty" | Include prediction confidence interval or probability alongside EV |
| Too many recommended bets per race | User buys 20+ combinations, bankroll diluted, variance high | Apply strict EV threshold; cap at 3-5 combinations per race; show "skip race" when no combination meets threshold |
| No aggregate backtest summary | User cannot judge whether the system works | Output summary statistics: total ROI, hit rate, max drawdown, Sharpe-like ratio, number of bets |
| Showing only recent results | Survivorship bias in evaluation | Always show full-period backtest results including losing streaks |

## "Looks Done But Isn't" Checklist

- [ ] **Data Pipeline:** Raw data loaded -- Often missing column-level documentation of which fields are pre-race vs. post-race. Verify by checking if each column existed before race start time.
- [ ] **Feature Engineering:** Features computed -- Often missing `.shift(1)` in rolling calculations. Verify by checking that no feature for race N uses data from race N's outcome.
- [ ] **Model Training:** Model trained with good AUC -- Often trained with random CV split instead of temporal split. Verify by confirming `TimeSeriesSplit` or year-based splits were used.
- [ ] **Probability Calibration:** Predictions look reasonable -- Often the raw LightGBM output is not calibrated. Verify calibration with reliability diagrams or ECE metric.
- [ ] **EV Calculation:** EV formula implemented -- Often uses naive P(A)*P(B)*P(C) instead of Harville conditional probabilities. Verify against actual trifecta hit rates.
- [ ] **Backtesting:** ROI positive -- Often uses 確定オッズ instead of realistic purchasable odds. Verify by noting which odds version is used.
- [ ] **三連複オッズ全通り:** All combinations fetched -- Kaggle only provides top 3 combinations. Verify that the scraping pipeline captures all C(n,3) combinations, not just the popular ones.
- [ ] **Odds column meaning:** "Odds" column in dataset -- Verify whether it is 発走時オッズ (at race start), 確定オッズ (final confirmed), or 最終オッズ (final before confirmation). These are different.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Data leakage in features | HIGH | Rebuild entire feature pipeline; retrain all models; redo all backtests |
| Random CV instead of temporal | MEDIUM | Re-partition data; retrain model; redo evaluation (feature engineering may be reusable) |
| Odds as feature (popularity echo) | MEDIUM | Remove odds from feature list; retrain model; verify predictions diverge from market |
| Naive trifecta probability | LOW-MEDIUM | Replace probability combination function with Harville model; recompute EV; redo backtest |
| Using 確定オッズ in backtest | LOW | Add discount factor to EV threshold; or recompute with realistic odds if multi-timepoint data is available |
| Missing calibration | LOW | Add Platt scaling or isotonic regression as post-processing step; recompute EV |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 未来情報リーク (data leakage) | Phase 1: Data Pipeline | Audit every column as pre-race or post-race; implement DROP_COLS |
| 時系列CV (temporal CV) | Phase 2: Model A Training | Confirm TimeSeriesSplit used; compare temporal CV vs. random CV scores |
| オッズ特徴量 (odds as feature) | Phase 2: Model A Feature Selection | Check feature importance does not show odds/popularity at top |
| 精度と回収率の逆転 (accuracy-ROI divergence) | Phase 2: Model A Evaluation | Plot ROI alongside AUC; implement EV-weighted loss if needed |
| OOF忘れ (in-sample weighting) | Phase 2: Model A Training (advanced) | Verify weights come from OOF predictions, not in-sample predictions |
| 直前オッズ vs 確定オッズ | Phase 1: Data Understanding + Phase 3: Scraping | Document odds type; design scraper for multi-timepoint capture |
| 三連複確率の独立仮定 | Phase 3: Model C (三連複EV) | Validate Harville probabilities against historical trifecta hit rates |
| 三連複オッズ全通り不足 | Phase 3: Scraping Pipeline | Verify scraper captures all C(n,3) combinations, not just top 3 |
| キャリブレーション不足 | Phase 2: Model A Post-Processing | Check reliability diagram; measure ECE; apply Platt scaling |
| バックテスト設計 (backtest design) | Phase 4: Backtesting | Walk-forward validation; realistic odds; report drawdown and bet count |

## Sources

- [note.com/dijzpeb - 競馬AIで本当に重視すべきデータは、全体の4%しかなかった](https://note.com/dijzpeb/n/n3b149e2b896f) -- Detailed analysis of EV-weighted training and OOF prediction methodology
- [zenn.dev/ricotiler - 未来の情報を漏らすな：特徴量エンジニアリングとデータリーク](https://zenn.dev/ricotiler/articles/keiba-ai-04-feature-engineering-leakage) -- Comprehensive guide to leakage prevention in horse racing AI
- [note.com/ra_lab_keiba - 精度評価の正しい方法](https://note.com/ra_lab_keiba/n/nc40f71d4c079) -- Three critical evaluation pitfalls in horse racing AI
- [keibasys.seesaa.net - 競馬AI開発 特徴量再考](https://keibasys.seesaa.net/article/482086231.html) -- Feature reconsideration and odds leakage
- [zenn.dev/ricotiler - 競馬AI開発記録 #16](https://zenn.dev/ricotiler/articles/keiba-ai-16-dynamic-features-and-negative-signs) -- Edge discovery after leakage removal
- [yokokenkeiba.com - AIは楽をしたがる](https://yokokenkeiba.com/ainowana/) -- AI's tendency to over-rely on market signals
- [Griffith University - Trifecta probability approximation](https://research-repository.griffith.edu.au/server/api/core/bitstreams/b8664df1-fe5c-550a-991f-77495a155574/content) -- Academic paper on discount model for trifecta probability
- [Harville (1973) - Conditional probability model](https://scispace.com/pdf/logistic-analyses-for-complicated-bets-263isxszp7.pdf) -- Foundational Harville model for exotic bet probability
- [京都アカデメイア - 競馬の数理モデル](https://kyoto-academeia.sakura.ne.jp/blog/wp-content/uploads/2022/04/%E7%AB%B6%E9%A6%AC%E3%81%AE%E6%95%B0%E7%90%86%E3%83%A2%E3%83%87%E3%83%AB.pdf) -- Harville model and discount model explanation
- [wilico.co.jp - netkeibaスクレイピングの規約と制限](https://wilico.co.jp/ja/blog/netkeiba-scraping-terms-and-realistic-ways-to-get-horse-racing-data) -- Scraping legal and technical constraints
- [note.com/dijzpeb - 全馬券種の直前オッズ取得](https://note.com/dijzpeb/n/n4dc467834532) -- JRA odds scraping implementation
- [medium.com/@kyle-t-jones - Data Leakage and Lookahead Bias in Time Series](https://medium.com/@kyle-t-jones/data-leakage-lookahead-bias-and-causality-in-time-series-analytics-76e271ba2f6b) -- General time-series leakage prevention
- [JRA公式 - 馬券のルール](https://www.jra.go.jp/kouza/baken/) -- 三連複控除率25%の確認

---
*Pitfalls research for: JRA三連複EV判定システム*
*Researched: 2026-06-11*
