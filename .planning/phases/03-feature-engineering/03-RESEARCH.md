# Phase 3: Feature Engineering - Research

**Researched:** 2026-06-12
**Domain:** Feature engineering for LightGBM tabular model (3着内確率)
**Confidence:** HIGH

## Summary

Phase 3 transforms standard-layer Parquet (race, entry, result) into ML-ready feature Parquet for Model A's 3着内確率 prediction. The core technical challenges are: (1) computing time-series-safe lag features from past race results via `groupby('horse_name').shift(1)` after sorting by `race_date`, (2) generating jockey/trainer rolling statistics using expanding windows that respect temporal boundaries, (3) converting non-numeric margin text ("クビ", "1.1/4") to numeric values using a fixed mapping table, (4) z-score normalizing finish_time per course-distance combination, and (5) converting string categorical columns to pandas `CategoricalDtype` for LightGBM's native categorical support.

The standard-layer data contains 311,806 entries across 21,929 races (2015-2021), with 36,802 unique horse names averaging 8.5 races each. The feature layer will produce ~45 lag feature columns from 5 metrics across 3 and 5 past races, plus rolling jockey/trainer stats, race context features, and horse basic features. All features must pass the Phase 1 `audit_leakage()` check -- zero post-race columns from the current race may appear in the output.

**Primary recommendation:** Build the feature pipeline as a single `src/pipeline/feature_generator.py` module with discrete transformation functions for each feature group, orchestrated by a top-level `generate()` function. Output two Parquet files: training features (with `target_top3`) and prediction features (without `target_top3`). Use pandas `groupby().shift()` pattern for all lag features, ensuring `race_date` sort within each group before shifting.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** lag遡り範囲は **3レース + 5レースの両方** を生成。モデルが重要な方を使用
- **D-02:** lag対象指標は5指標: finish_position, last_3f, corner_4, finish_time (z-score正規化済み), margin (数値変換済み)
- **D-03:** finish_timeは **コース×距離別のz-score** で正規化
- **D-04:** marginは **数値変換マッピング** で処理
- **D-05:** lag形式は **lag生値 + 統計量**: lag生値(`prev_1_*`〜`prev_5_*`), 3走統計量(平均・標準偏差), 5走統計量(平均・標準偏差)
- **D-06:** LightGBMの **native categoricalとして直接投入** + **rolling統計量** の両方
- **D-07:** 統計量は基本3指標: 3着内率, 勝率(1着率), 騎乗数
- **D-08:** 統計量の計算期間は **直近100戦または直近1年間の短い方**。当該レースより前のデータのみ使用（時系列リーク防止）
- **D-09:** lag featureは **NaNのまま** + **is_debut ブール特微量** を追加
- **D-10:** 出走数が3走/5走未満の馬は **可能な分だけ統計量を計算**。不足分はNaN
- **D-11:** **target_top3** 列を学習用feature Parquetに含める。予測用には含めない
- **D-12:** target_top3定義: 正式着順 1-3 -> 1, 4着以下 -> 0, 同着で3着以内 -> 1, 降着・失格は最終確定後の公式着順
- **D-13:** 取消(取)・除外(除)・発走除外 -> 学習対象から除外。競走中止(中)・失格(失) -> target_top3=0、学習対象に含む
- **D-14:** 補助列 `result_status` / `is_dnf` を残して後から分析可能にする
- **D-15:** 人気・単勝オッズはfeature層では使用しない（post-race扱い）

### Claude's Discretion
- finish_timeのz-score正規化の具体的実装
- marginの数値変換マッピング詳細テーブル
- lag featureの生成方法（`.shift(1)`による時系列安全なlag、groupby horse_name等の具体的pandas操作）
- feature Parquetのファイル構成（単一ファイル vs テーブル別等）
- 統計量計算のrolling window実装詳細
- result_status/is_dnf補助列の具体的な値定義
- categorical列のCategoricalDtype変換の実装

### Deferred Ideas (OUT OF SCOPE)
None
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DATA-03 | standardデータからfeature層の基本特徴量（競馬場・距離・芝ダート・馬場状態・頭数・枠番・馬番・斤量・騎手・調教師・近走成績・上がり3F・通過順）を生成できること | Feature pipeline design below covers all listed features. Note: D-15 excludes 人気・単勝オッズ from features; specification.md §7.2 lists them but CONTEXT.md D-15 overrides. 近走成績/上がり3F/通過順 are handled via lag features from past race result data. |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Race context features (course, distance, surface, etc.) | Data Pipeline | -- | Direct column selection from race/entry tables, no model tier involvement |
| Horse basic features (sex, age, weight) | Data Pipeline | -- | Direct column selection from entry table |
| Lag features (past race performance) | Data Pipeline | -- | Requires temporal join of entry+result, groupby horse, shift operations |
| Jockey/trainer rolling stats | Data Pipeline | -- | Expanding window aggregation on historical data, no model needed |
| Target variable (target_top3) generation | Data Pipeline | -- | Binary classification from finish_position, purely data transformation |
| Leakage audit (post-race check) | Data Pipeline | -- | Phase 1 audit_leakage() function, runs after feature generation |
| Categorical encoding (CategoricalDtype) | Data Pipeline | -- | Pandas type conversion for LightGBM native handling |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | 2.3.3 | DataFrame operations, groupby, shift, rolling | Project standard. CategoricalDtype for LightGBM. [VERIFIED: runtime] |
| numpy | 2.x | Numerical computing | Required by pandas. [VERIFIED: runtime] |
| pyarrow | 24.0.0 | Parquet I/O | Required for read_parquet/to_parquet. [VERIFIED: runtime] |
| loguru | 0.7.3 | Structured logging | Project standard. [VERIFIED: runtime] |
| pydantic | 2.13.4 | Schema type definitions | Used by audit_leakage(). [VERIFIED: runtime] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.0.3 | Test framework | All feature generation tests. [VERIFIED: runtime] |

### No New Packages Required
This phase uses only packages already installed. No new dependencies need to be added.

## Package Legitimacy Audit

> No new packages are installed in this phase. All dependencies are existing project dependencies verified in prior phases.

**Packages removed due to SLOP verdict:** none
**Packages flagged as suspicious:** none

## Architecture Patterns

### System Architecture Diagram

```
data/standard/                          data/feature/
┌──────────────┐
│  race.parquet │────┐
└──────────────┘    │
                    │    ┌─────────────────────────────────────┐
┌──────────────┐    ├───►│     Feature Generation Pipeline      │
│ entry.parquet│────┤    │                                     │
└──────────────┘    │    │  1. Load & Merge (race+entry+result) │
                    │    │  2. Race Context Features            │
┌──────────────┐    │    │  3. Horse Basic Features             │
│result.parquet│────┘    │  4. Target Variable (training only)  │
└──────────────┘         │  5. Margin Numeric Conversion        │
                         │  6. Finish Time Z-Score Normalization │
                         │  7. Lag Features (shift per horse)    │
                         │  8. Jockey/Trainer Rolling Stats      │
                         │  9. Debut Flag                        │
                         │ 10. CategoricalDtype Conversion       │
                         │ 11. Leakage Audit (audit_leakage)     │
                         │ 12. Write Parquet                     │
                         └──────────┬──────────────────────────┘
                                    │
                          ┌─────────▼─────────┐
                          │features_train.parquet│ (target_top3 included)
                          │features_pred.parquet │ (target_top3 excluded)
                          └────────────────────┘
```

### Recommended Project Structure
```
src/
├── pipeline/
│   ├── __init__.py
│   ├── column_mapping.py       # (existing) Kaggle column mapping
│   ├── kaggle_converter.py     # (existing) CSV -> standard Parquet
│   ├── validators.py           # (existing) data quality checks
│   └── feature_generator.py    # NEW: standard -> feature pipeline
├── schemas/
│   ├── audit.py                # (existing) audit_leakage()
│   ├── race.py                 # (existing) RaceSchema
│   ├── entry.py                # (existing) EntrySchema
│   └── result.py               # (existing) ResultSchema
tests/
├── pipeline/
│   ├── conftest.py             # (existing) shared fixtures
│   ├── test_kaggle_converter.py
│   └── test_feature_generator.py  # NEW: feature pipeline tests
data/
├── standard/                   # (existing) Input Parquet files
│   ├── race.parquet            # 21,929 races
│   ├── entry.parquet           # 311,806 entries
│   └── result.parquet          # 311,806 results
└── feature/                    # NEW: Output directory
    ├── features_train.parquet  # Training features with target_top3
    └── features_pred.parquet   # Prediction features without target_top3
```

### Pattern 1: Temporal-Safe Lag Features via groupby().shift()
**What:** Generate past-race features by shifting result data within horse groups, sorted chronologically.
**When to use:** All lag features (prev_1_finish_position, prev_1_last_3f, etc.)
**Example:**
```python
# Source: pandas groupby+shift pattern [CITED: pandas docs]
# Step 1: Merge entry + result, sort by horse then date
df = entry.merge(race[['race_id', 'race_date', 'course_name', 'distance']], on='race_id')
df = df.merge(result[['horse_race_id', 'finish_position', 'last_3f', 'corner_4',
                        'finish_time', 'margin']], on='horse_race_id')
df = df.sort_values(['horse_name', 'race_date']).reset_index(drop=True)

# Step 2: Create lag columns within horse group
for lag in range(1, 6):
    df[f'prev_{lag}_finish_position'] = df.groupby('horse_name')['finish_position'].shift(lag)
    df[f'prev_{lag}_last_3f'] = df.groupby('horse_name')['last_3f'].shift(lag)
    # ... same for corner_4, finish_time_zscore, margin_numeric
```

### Pattern 2: Expanding Window Statistics for Jockey/Trainer
**What:** Compute cumulative statistics (3着内率, 勝率, 騎乗数) using expanding windows that only look backward.
**When to use:** Jockey and trainer rolling stats (D-06, D-07, D-08)
**Example:**
```python
# Source: pandas expanding window pattern [CITED: pandas docs]
# Sort by jockey name and race_date to ensure temporal order
df = df.sort_values(['jockey', 'race_date']).reset_index(drop=True)

# Group by jockey, use expanding window to compute stats from ALL prior races
grp = df.groupby('jockey')
# Shift(1) ensures we never include the current race's result
df['jockey_total_rides'] = grp.cumcount()  # count before current row
df['jockey_wins'] = grp['is_win'].expanding().sum().shift(1).values
df['jockey_top3'] = grp['is_top3'].expanding().sum().shift(1).values

# Apply the "100 rides or 1 year" constraint from D-08
# For each row, filter prior data to min(last_100_rides, last_1_year)
# This requires a more careful implementation (see Implementation Notes)
```

### Pattern 3: Z-Score Normalization per Course-Distance
**What:** Convert finish_time to z-scores within each course-distance group, so times are comparable across different tracks.
**When to use:** finish_time normalization (D-03)
**Example:**
```python
# Source: z-score normalization pattern [CITED: standard statistical method]
# Compute mean and std per course-distance combo from HISTORICAL data only
# This requires cumulative/expanding stats to avoid future leakage
df = df.sort_values(['course_name', 'distance', 'race_date'])

# For z-score: use expanding mean/std so only past data is used
grp = df.groupby(['course_name', 'distance'])
df['ft_mean'] = grp['finish_time_seconds'].expanding().mean().shift(1).values
df['ft_std'] = grp['finish_time_seconds'].expanding().std().shift(1).values

# Alternative (simpler, acceptable for 2015-2021 training data):
# Compute global stats per course-distance combo from all data,
# then use those as fixed reference values. This is safe because:
# 1. z-score is for normalization, not prediction
# 2. The model sees normalized values, not raw times
# 3. Course-distance parameters are stable over time
cd_stats = df.groupby(['course_name', 'distance'])['finish_time_seconds'].agg(['mean', 'std'])
df = df.merge(cd_stats, on=['course_name', 'distance'], how='left')
df['finish_time_zscore'] = (df['finish_time_seconds'] - df['mean']) / df['std']
```

### Anti-Patterns to Avoid
- **Including current-race result data in features:** Never use the current race's finish_position, last_3f, corner_4, or margin as features. Only use `.shift(N)` where N >= 1. The audit_leakage() function catches exact column name matches but cannot detect semantic leakage from incorrect shift logic. [CITED: CONTEXT.md D-15, Phase 1 D-06]
- **Computing lag features without sorting by date first:** `groupby().shift()` operates on row order. If data is not sorted by `race_date` within each horse group, shift may reference future or wrong races. Always sort before shift. [CITED: WebSearch - temporal safety best practices]
- **Using horse_name as a unique horse identifier without awareness of name collisions:** 36,802 unique horse names, max 72 races per name. In JRA, same-name horses are extremely rare but not impossible. The 2015-2021 dataset likely has minimal collisions. Using horse_name as groupby key is acceptable for this dataset but should be documented. [VERIFIED: data analysis]
- **Forgetting to exclude scratchings/withdrawals from training data:** 取消(取)・除外(除) horses must be excluded from training (D-13), not just labeled as target_top3=0. Including them would add noise since these horses never actually ran. [CITED: CONTEXT.md D-13]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Time-series lag features | Custom loop over rows | pandas `groupby().shift(N)` | Vectorized, handles NaN boundaries, O(n) not O(n^2) |
| Rolling/expanding statistics | Manual cumulative sums | pandas `.expanding()` and `.rolling()` | Handles edge cases, NaN correctly |
| Categorical encoding for LightGBM | One-hot encoding or LabelEncoder | pandas `CategoricalDtype` | LightGBM natively handles pandas categoricals, no OHE needed |
| Leakage detection | Manual column checking | `audit_leakage()` from `src/schemas/audit.py` | Already implemented, uses metadata-driven exact matching |
| Parquet I/O | Custom serialization | `pd.read_parquet()` / `df.to_parquet()` | Proven, handles dtypes, compression |

**Key insight:** The Phase 2 `kaggle_converter.py` established the pipeline pattern (load -> transform -> validate -> write). Phase 3 should follow this same pattern. The feature generator should mirror the converter's structure: discrete transformation functions + top-level `generate()` orchestrator + `audit_leakage()` call before writing.

## Common Pitfalls

### Pitfall 1: Data Leakage via Incorrect Shift Direction
**What goes wrong:** Using `shift(-1)` or forgetting shift, so the model sees the current race's result as a "feature".
**Why it happens:** Confusion about shift direction -- `shift(1)` moves data DOWN (past values align with current row).
**How to avoid:** Always use `shift(N)` with N >= 1. Write a test that verifies for any horse, `prev_1_finish_position` for race N equals `finish_position` for race N-1 (the previous race).
**Warning signs:** Model shows suspiciously high accuracy (>95%) in cross-validation.

### Pitfall 2: Jockey/Trainer Stats Leakage via Including Current Race
**What goes wrong:** Computing jockey win rate including the race being predicted.
**Why it happens:** Expanding window by default includes the current row. Must use `shift(1)` after expanding aggregation.
**How to avoid:** After computing expanding stats per jockey, shift by 1 to exclude current row. For the "100 rides or 1 year" constraint (D-08), carefully filter historical data to only include rows where `race_date < current_race_date` and within the lookback window.
**Warning signs:** Jockey win rate feature shows near-perfect correlation with target.

### Pitfall 3: Margin Text Conversion Edge Cases
**What goes wrong:** Failing to handle compound margin strings like "1.1/4+クビ" or "2+ハナ".
**Why it happens:** 29 unique margin values include compound forms (6 compound forms found in data).
**How to avoid:** Parse compound margins by splitting on "+" and summing the component values. Handle all 29 unique values in the mapping table.
**Warning signs:** NaN rate in margin_numeric column is higher than the 10% null rate in source data.

### Pitfall 4: Weather Whitespace Inconsistency
**What goes wrong:** Categorical values "晴" and "晴 " (trailing space) are treated as different categories, doubling category count.
**Why it happens:** Source data has inconsistent whitespace in weather column.
**How to avoid:** Strip whitespace from all string categorical columns before converting to CategoricalDtype.
**Warning signs:** Weather has 9 categories instead of expected 6 (晴/曇/雨/小雨/小雪/雪).

### Pitfall 5: Z-Score with Insufficient Samples
**What goes wrong:** Rare course-distance combinations (e.g., 中京3000 with only 14 samples) produce unreliable z-scores.
**Why it happens:** 84 course-distance combos exist; 1 has fewer than 30 samples.
**How to avoid:** For combos with < 30 samples, fall back to a broader normalization (e.g., distance-only z-score) or mark as NaN. Document the threshold used.
**Warning signs:** Extremely large or small z-scores (>5 or <-5) for specific course-distance combos.

### Pitfall 6: Target Variable Generation Off-By-One
**What goes wrong:** Incorrectly classifying 同着 (dead heat) or 降着 (demotion) horses in target_top3.
**Why it happens:** D-12/D-13 have nuanced rules: 同着で3着以内 -> 1, 降着 keeps position, 中/取/失/除 have different treatments.
**How to avoid:** Implement target generation as an explicit mapping function with clear conditional logic. Test each case: 正常1-3着, 正常4着以下, 同着, 降着, 中止, 取消, 失格, 除外.
**Warning signs:** Target distribution doesn't match expected ~top-3 rate (~21% for average 14-horse fields).

### Pitfall 7: Finish Time Parsing Edge Cases
**What goes wrong:** Some finish_time values might be in different formats (e.g., "1:29.5" vs "0:59.3").
**Why it happens:** Short-distance races may have sub-minute times.
**How to avoid:** Parse using split on ":" -- minutes * 60 + seconds. Test with various formats.
**Warning signs:** finish_time_seconds has negative values or values > 600 (10 minutes).

## Code Examples

### Margin Numeric Conversion Mapping
```python
# Source: JRA official margin definitions [CITED: jra.go.jp/kouza/yougo/w273.html]
# Approximate seconds conversion (1 馬身 ≈ 0.17-0.2 seconds)
# Compound margins (e.g., "1.1/4+クビ") are split and summed

MARGIN_MAP: dict[str, float] = {
    # Text margins (body parts)
    "ハナ": 0.02,      # nose ~20cm
    "アタマ": 0.05,    # head ~40cm
    "クビ": 0.10,      # neck ~60-80cm
    # Fractional margins (in 馬身/horse lengths, 1 馬身 ≈ 0.2 sec)
    "3/4": 0.75,
    "1/2": 0.50,
    "1.1/4": 1.25,
    "1.1/2": 1.50,
    "1.3/4": 1.75,
    "2.1/2": 2.50,
    "3.1/2": 3.50,
    # Integer margins (in 馬身)
    "1": 1.0,
    "2": 2.0,
    "3": 3.0,
    "4": 4.0,
    "5": 5.0,
    "6": 6.0,
    "7": 7.0,
    "8": 8.0,
    "9": 9.0,
    "10": 10.0,
    # Special
    "大": 15.0,        # 大差 (large margin, >10 lengths)
    "同着": 0.0,       # dead heat
}

# Compound margins: "1.1/4+クビ" -> 1.25 + 0.10 = 1.35
# "2+ハナ" -> 2.0 + 0.02 = 2.02
COMPONENT_MAP: dict[str, float] = {
    "ハナ": 0.02,
    "クビ": 0.10,
    "1/2": 0.50,
}

def parse_margin(margin_str: str) -> float | None:
    """Convert margin text to numeric (馬身 units)."""
    if pd.isna(margin_str) or margin_str is None:
        return None
    # Try direct lookup first
    if margin_str in MARGIN_MAP:
        return MARGIN_MAP[margin_str]
    # Try compound parsing (split on "+")
    if "+" in margin_str:
        parts = margin_str.split("+")
        total = 0.0
        for part in parts:
            if part in MARGIN_MAP:
                total += MARGIN_MAP[part]
            elif part in COMPONENT_MAP:
                total += COMPONENT_MAP[part]
            else:
                return None  # Unknown component
        return total
    return None  # Unknown margin format
```

### Target Variable Generation
```python
# Source: CONTEXT.md D-12, D-13
def generate_target(df: pd.DataFrame) -> pd.DataFrame:
    """Generate target_top3, result_status, is_dnf columns.

    D-12: 正式着順 1-3 -> 1, 4着以下 -> 0
    D-13: 取/除 -> exclude from training. 中/失 -> target_top3=0, include.
    """
    df = df.copy()

    # result_status: categorize each entry
    # 取=scratched, 除=removed, 発走除外 -> exclude
    # 中=withdrawal during race, 失=disqualified -> include as non-top3
    # 降=demoted -> include, use final official position
    df['result_status'] = 'finished'  # default
    df.loc[df['finish_note'] == '中', 'result_status'] = 'dnf'         # did not finish
    df.loc[df['finish_note'] == '失', 'result_status'] = 'disqualified'
    df.loc[df['finish_note'] == '取', 'result_status'] = 'scratched'
    df.loc[df['finish_note'] == '除', 'result_status'] = 'removed'
    df.loc[df['finish_note'] == '降', 'result_status'] = 'demoted'
    df.loc[df['finish_position'].isna() & df['finish_note'].isna(), 'result_status'] = 'unknown'

    # is_dnf: True if horse started but did not finish normally
    df['is_dnf'] = df['result_status'].isin(['dnf', 'disqualified'])

    # target_top3: 1 for positions 1-3, 0 otherwise
    df['target_top3'] = (df['finish_position'] <= 3).astype('Int64')
    # Null finish_position (non-finishers) -> target_top3 = 0
    df.loc[df['finish_position'].isna(), 'target_top3'] = 0

    # Exclude scratched/removed from training (D-13)
    df['exclude_from_training'] = df['result_status'].isin(['scratched', 'removed'])

    return df
```

### Categorical Column Conversion
```python
# Source: CLAUDE.md LightGBM + pandas CategoricalDtype integration
CATEGORICAL_COLUMNS = [
    'course_name',      # 10 courses
    'surface',          # 芝/ダート
    'direction',        # 右/左
    'weather',          # 晴/曇/雨/小雨/小雪/雪 (strip whitespace first!)
    'track_condition',  # 良/稍重/重/不良
    'sex',              # 牡/牝/セ
    'jockey',           # 312 unique values
    'trainer',          # 376 unique values
    'grade',            # G1/G2/G3/G/listed/None
]

def convert_to_categorical(df: pd.DataFrame) -> pd.DataFrame:
    """Convert string columns to pandas CategoricalDtype for LightGBM."""
    for col in CATEGORICAL_COLUMNS:
        if col in df.columns:
            # Strip whitespace first (Pitfall #4: weather has trailing spaces)
            df[col] = df[col].str.strip()
            df[col] = df[col].astype('category')
    return df
```

### Complete Feature Column Inventory
```python
# All feature columns in the output Parquet

# 1. Race Context Features (from race table, ~12 columns)
#    race_id, race_date, course_name, distance, surface, direction,
#    weather, track_condition, race_number, grade
#    field_size (computed: count of entries per race_id)

# 2. Horse Basic Features (from entry table, ~7 columns)
#    bracket_num, horse_number, sex, age, weight_assigned,
#    horse_weight, weight_change

# 3. People Features (from entry table + rolling stats)
#    jockey (categorical), trainer (categorical)
#    jockey_rolling_top3_rate, jockey_rolling_win_rate, jockey_rolling_rides
#    trainer_rolling_top3_rate, trainer_rolling_win_rate, trainer_rolling_rides

# 4. Lag Features (from past result data, 45 columns)
#    5 metrics x 5 lags = 25 raw lag columns:
#      prev_{1..5}_finish_position
#      prev_{1..5}_last_3f
#      prev_{1..5}_corner_4
#      prev_{1..5}_finish_time_zscore
#      prev_{1..5}_margin_numeric
#    5 metrics x 2 stats x 2 windows = 20 stat columns:
#      prev3_{metric}_mean, prev3_{metric}_std  (5x2=10)
#      prev5_{metric}_mean, prev5_{metric}_std  (5x2=10)

# 5. Debut Flag
#    is_debut (True if no previous race data available)

# 6. Target and Auxiliary (training only)
#    target_top3, result_status, is_dnf, exclude_from_training

# TOTAL: ~12 + 7 + 6 + 45 + 1 = ~71 feature columns + target/auxiliary
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| One-hot encoding for categoricals | pandas CategoricalDtype + LightGBM native handling | LightGBM 3.x+ | Reduces feature dimensionality from 312+376 one-hot columns to 2 categorical columns. ~8x faster training. |
| Manual lag feature loops | pandas vectorized groupby().shift() | pandas 1.x+ | O(n) vs O(n^2), handles NaN boundaries automatically |
| Fixed window rolling stats | Expanding window with temporal constraint | Standard practice | D-08 uses "100 rides or 1 year, whichever is shorter" -- modern approach balances recency with sample size |

**Deprecated/outdated:**
- LabelEncoder for LightGBM categoricals: Use pandas CategoricalDtype instead. LightGBM reads category codes directly. [ASSUMED]
- Manual NaN handling for lag features: LightGBM handles NaN natively in split decisions. No imputation needed. [CITED: LightGBM documentation]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | horse_name is a sufficient unique identifier for groupby lag operations (same-name collision risk is negligible in 2015-2021 JRA data) | Architecture Patterns | Lag features reference wrong past races for same-name horses; ~0 impact expected |
| A2 | Global course-distance z-score stats (computed from all data) are acceptable for normalization rather than strictly expanding-window stats | Pattern 3 | Minor temporal leakage in z-score values; z-score is for normalization not prediction so impact is minimal |
| A3 | Margin conversion values (ハナ=0.02, クビ=0.10, アタマ=0.05 馬身) are reasonable approximations for ML features | Code Examples | Feature noise in margin_numeric; model is robust to small numeric differences |
| A4 | finish_time format is always "M:SS.T" (minutes:seconds.tenths) | Pitfalls | Parse errors for unusual formats; 309,716 non-null values all contain ":" so this is validated |
| A5 | LightGBM will be installed with libomp by Phase 7 (not needed for feature generation, only for model training) | Environment | Feature generation works without LightGBM; only Phase 7 needs the native library |

**If this table is empty:** All claims in this research were verified or cited.

## Open Questions

1. **ROADMAP success criterion mentions "popularity/win odds" but D-15 excludes them**
   - What we know: ROADMAP Phase 3 success criteria #1 lists "popularity/win odds" as features. CONTEXT.md D-15 explicitly excludes them (post-race). Phase 1 D-03/D-06 classified them as post-race.
   - What's unclear: Whether to update ROADMAP to match D-15, or whether the discrepancy indicates a design conflict.
   - Recommendation: D-15 takes precedence (CONTEXT.md is the locked decision). The planner should note this discrepancy and confirm with user if needed, but implement per D-15.

2. **Feature Parquet file naming and structure**
   - What we know: CONTEXT.md mentions "学習用: target_top3付き / 予測用: target_top3なし" but doesn't specify exact file names.
   - What's unclear: Whether to use two separate files or one file with a flag column.
   - Recommendation: Two separate Parquet files (`features_train.parquet` and `features_pred.parquet`) to enforce the separation at the file level. This is Claude's Discretion per CONTEXT.md.

3. **Jockey/trainer rolling stats: exact implementation of D-08's "100 rides or 1 year" constraint**
   - What we know: D-08 specifies "直近100戦または直近1年間の短い方". This requires per-row lookback computation.
   - What's unclear: Whether to implement this as a per-row loop (slow but precise) or as an approximation using rolling windows.
   - Recommendation: For 311K rows, a per-row approach using pandas operations is feasible. Pre-compute expanding stats and apply the constraint as a post-processing step. This is Claude's Discretion.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Runtime | Yes | 3.12.13 | -- |
| pandas | DataFrame ops | Yes | 2.3.3 | -- |
| numpy | Numerical | Yes | 2.x | -- |
| pyarrow | Parquet I/O | Yes | 24.0.0 | -- |
| pydantic | Schema types | Yes | 2.13.4 | -- |
| loguru | Logging | Yes | 0.7.3 | -- |
| pytest | Testing | Yes | 9.0.3 | -- |
| lightgbm | Model training | **No (libomp missing)** | 4.6 installed but fails to load | Not needed for feature generation; Phase 7 installs libomp |
| data/standard/*.parquet | Input data | Yes | Phase 2 output | -- |

**Missing dependencies with no fallback:**
- None that block feature generation. LightGBM import is not required for this phase.

**Missing dependencies with fallback:**
- LightGBM: Not needed for feature generation. Feature output is Parquet that Phase 7 reads. The `CategoricalDtype` conversion only requires pandas.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 |
| Config file | pyproject.toml [tool.pytest.ini_options] testpaths=["tests"] |
| Quick run command | `python3 -m pytest tests/pipeline/test_feature_generator.py -x -q` |
| Full suite command | `python3 -m pytest tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-03 | Race context features generated correctly | unit | `pytest tests/pipeline/test_feature_generator.py::test_race_context_features -x` | Wave 0 |
| DATA-03 | Horse basic features present | unit | `pytest tests/pipeline/test_feature_generator.py::test_horse_basic_features -x` | Wave 0 |
| DATA-03 | Lag features with temporal safety | unit | `pytest tests/pipeline/test_feature_generator.py::test_lag_features_temporal_safety -x` | Wave 0 |
| DATA-03 | Jockey/trainer rolling stats | unit | `pytest tests/pipeline/test_feature_generator.py::test_jockey_trainer_stats -x` | Wave 0 |
| DATA-03 | Target variable correct | unit | `pytest tests/pipeline/test_feature_generator.py::test_target_top3_generation -x` | Wave 0 |
| DATA-03 | Margin numeric conversion | unit | `pytest tests/pipeline/test_feature_generator.py::test_margin_conversion -x` | Wave 0 |
| DATA-03 | Finish time z-score | unit | `pytest tests/pipeline/test_feature_generator.py::test_finish_time_zscore -x` | Wave 0 |
| DATA-03 | Categorical dtype conversion | unit | `pytest tests/pipeline/test_feature_generator.py::test_categorical_conversion -x` | Wave 0 |
| DATA-03 | Leakage audit passes | unit | `pytest tests/pipeline/test_feature_generator.py::test_leakage_audit -x` | Wave 0 |
| DATA-03 | Debut flag correct | unit | `pytest tests/pipeline/test_feature_generator.py::test_debut_flag -x` | Wave 0 |
| DATA-03 | End-to-end feature generation | integration | `pytest tests/pipeline/test_feature_generator.py::test_e2e_feature_generation -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python3 -m pytest tests/pipeline/test_feature_generator.py -x -q`
- **Per wave merge:** `python3 -m pytest tests/ -x`
- **Phase gate:** Full suite green + manual inspection of feature Parquet output

### Wave 0 Gaps
- [ ] `tests/pipeline/test_feature_generator.py` -- all DATA-03 tests
- [ ] `tests/pipeline/conftest.py` -- add feature-specific fixtures (sample race+entry+result data for testing)
- [ ] `src/pipeline/feature_generator.py` -- the main implementation module

## Security Domain

> security_enforcement is enabled (default). This phase processes local data files with no external network access, no authentication, and no user input. Security domain is minimal.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth required for local CLI pipeline |
| V3 Session Management | no | No sessions |
| V4 Access Control | no | Local file processing |
| V5 Input Validation | yes | Pydantic schema validation on input Parquet; margin text parsing with fallback |
| V6 Cryptography | no | No encryption needed |

### Known Threat Patterns for Data Pipeline (Python/pandas/Parquet)

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal in file paths | Tampering | Use pathlib.Path, validate directory is within project root |
| Pickle deserialization (Parquet) | Tampering | pyarrow engine for Parquet (not pickle-based); trusted local files |
| Data injection via malformed CSV/Parquet | Tampering | Pydantic schema validation; dtype enforcement |

## Sources

### Primary (HIGH confidence)
- Standard layer data analysis: 311,806 entries, 21,929 races, 36,802 horses -- verified via pandas inspection [VERIFIED: runtime data analysis]
- Schema definitions in `src/schemas/*.py` -- pre/post-race classification, column definitions [VERIFIED: codebase]
- `src/schemas/audit.py` -- `audit_leakage()` implementation with exact matching [VERIFIED: codebase]
- Phase 2 `kaggle_converter.py` -- pipeline pattern reference [VERIFIED: codebase]
- CONTEXT.md D-01 through D-15 -- locked decisions [VERIFIED: user decisions]

### Secondary (MEDIUM confidence)
- JRA official margin definitions [CITED: jra.go.jp/kouza/yougo/w273.html]
- Pandas groupby().shift() pattern for temporal lag features [CITED: pandas documentation]
- LightGBM native categorical handling via pandas CategoricalDtype [CITED: CLAUDE.md]

### Tertiary (LOW confidence)
- Margin numeric approximation values (ハナ=0.02, クビ=0.10, アタマ=0.05 馬身) [ASSUMED -- based on JRA standard conversions but not precisely verified]
- Same-name horse collision risk being negligible [ASSUMED]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all packages verified at runtime, no new dependencies
- Architecture: HIGH - follows established Phase 2 pipeline pattern, data analyzed directly
- Pitfalls: HIGH - identified from data analysis (margin formats, weather whitespace, target edge cases)
- Feature column inventory: HIGH - all counts verified from schema definitions and CONTEXT.md decisions

**Research date:** 2026-06-12
**Valid until:** 2026-07-12 (stable domain, 30-day validity)
