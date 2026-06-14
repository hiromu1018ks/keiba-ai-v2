"""Shared pytest fixtures for converter tests.

Provides sample DataFrames that mimic the actual Kaggle CSV structure:
- sample_race_result_df: 10 rows with 66 columns using ACTUAL Japanese column names
- sample_odds_df: 5 rows with actual odds.csv column names
- tmp_standard_dir: temporary output directory for Parquet files
- sample_standard_race_df: 6 rows with English schema column names (feature generator tests)
- sample_standard_entry_df: 14 rows with English schema column names (feature generator tests)
- sample_standard_result_df: 14 rows with English schema column names (feature generator tests)
- sample_feature_merged_df: Pre-merged DataFrame via load_and_merge (feature generator tests)
- tmp_feature_dir: temporary data/feature/ output directory
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.pipeline.column_mapping import FLAG_COLUMNS


@pytest.fixture
def sample_race_result_df() -> pd.DataFrame:
    """DataFrame mimicking race_result.csv with 10 rows and all 66 columns.

    Row breakdown:
    - 5 rows: 2015 flat races (2 unique race_ids: 2015A, 2015B, 2+3 horses each)
    - 2 rows: 2016 flat race (1 unique race_id: 2016A)
    - 2 rows: 2015 obstacle race (obstacle="障害") -> should be filtered out
    - 1 row: 2014 flat race -> should be filtered out by date

    Total unique flat race_ids after filtering: 3 (2015A, 2015B, 2016A)
    Total rows after filtering: 7 (5 from 2015 flat + 2 from 2016 flat)
    """
    data: dict[str, list] = {}

    # Row 1: Identification
    data["レース馬番ID"] = [
        "2015A01", "2015A02", "2015A03",  # race 2015A, 3 horses
        "2015B04", "2015B05",              # race 2015B, 2 horses
        "2016A01", "2016A02",              # race 2016A, 2 horses
        "2015O01", "2015O02",              # 2015 obstacle race (filtered)
        # 2014 row
    ]
    data["レース馬番ID"].append("2014C01")

    # Row 2-8: Race identification
    data["レースID"] = [
        "201501010101", "201501010101", "201501010101",
        "201502020202", "201502020202",
        "201603030303", "201603030303",
        "201504040404", "201504040404",
        "201405050505",
    ]
    data["レース日付"] = [
        "2015-01-05", "2015-01-05", "2015-01-05",
        "2015-02-10", "2015-02-10",
        "2016-03-15", "2016-03-15",
        "2015-04-20", "2015-04-20",
        "2014-05-25",
    ]
    data["開催回数"] = [1, 1, 1, 2, 2, 3, 3, 4, 4, 1]
    data["競馬場コード"] = ["01", "01", "01", "02", "02", "03", "03", "04", "04", "05"]
    data["競馬場名"] = ["東京", "東京", "東京", "中山", "中山", "京都", "京都", "障害場", "障害場", "阪神"]
    data["開催日数"] = [1, 1, 1, 2, 2, 1, 1, 1, 1, 3]
    data["競争条件"] = [
        "4歳以上100万下", "4歳以上100万下", "4歳以上100万下",
        "3歳500万下", "3歳500万下",
        "4歳以上1600万下", "4歳以上1600万下",
        "障害4歳以上未勝利", "障害4歳以上未勝利",
        "4歳以上500万下",
    ]

    # Rows 9-28: 20 race flag columns (sparse text flags)
    # Pattern: some rows have text (non-empty), some empty string, some NaN
    flag_values = {
        "レース記号/[抽]": ["", "", "", "", "", "", "", "", "", ""],
        "レース記号/(馬齢)": ["", "(馬齢)", "", "", "", "", "", "", "", ""],
        "レース記号/牝": ["", "", "牝", "", "", "", "", "", "", ""],
        "レース記号/(父)": ["", "", "", "", "", "", "", "", "", ""],
        "レース記号/(別定)": ["", "", "", "(別定)", "", "", "", "", "", ""],
        "レース記号/(混)": ["(混)", "", "", "", "", "", "", "", "", ""],
        "レース記号/(ハンデ)": ["", "", "", "", "(ハンデ)", "", "", "", "", ""],
        "レース記号/(抽)": ["", "", "", "", "", "", "", "", "", ""],
        "レース記号/(市)": ["", "", "", "", "", "", "", "", "", ""],
        "レース記号/(定量)": ["", "", "", "", "", "", "", "", "", ""],
        "レース記号/牡": ["", "", "", "", "", "牡", "", "", "", ""],
        "レース記号/関東配布馬": ["", "", "", "", "", "", "", "", "", ""],
        "レース記号/(指)": ["", "", "", "", "", "", "", "", "", ""],
        "レース記号/関西配布馬": ["", "", "", "", "", "", "", "", "", ""],
        "レース記号/九州産馬": ["", "", "", "", "", "", "", "", "", ""],
        "レース記号/見習騎手": ["", "", "", "", "", "", "見習騎手", "", "", ""],
        "レース記号/せん": ["", "", "", "", "", "", "", "", "", ""],
        "レース記号/(国際)": ["", "", "", "(国際)", "", "", "", "", "", ""],
        "レース記号/[指]": ["", "", "", "", "", "", "", "", "", ""],
        "レース記号/(特指)": ["", "", "", "", "", "", "", "", "", ""],
    }
    for flag_col in FLAG_COLUMNS:
        data[flag_col] = flag_values[flag_col]

    # Add NaN to some flag columns for variety
    data["レース記号/[抽]"][2] = np.nan  # NaN for one row
    data["レース記号/(父)"][5] = np.nan

    # Row 29: Race number
    data["レース番号"] = [1, 1, 1, 5, 5, 11, 11, 3, 3, 7]
    # Row 30: Grade revision (mostly empty)
    data["重賞回次"] = [np.nan] * 10
    # Row 31: Race name
    data["レース名"] = [
        "サンプル1", "サンプル1", "サンプル1",
        "サンプル2", "サンプル2",
        "サンプル3", "サンプル3",
        "障害サンプル", "障害サンプル",
        "2014レース",
    ]
    # Row 32: Grade (mostly empty)
    data["リステッド・重賞競走"] = [np.nan] * 10
    # Row 33: Obstacle
    data["障害区分"] = [
        "", "", "", "", "", "", "",
        "障害", "障害",  # obstacle rows
        "",
    ]
    # Row 34-42: Race details
    data["芝・ダート区分"] = ["芝", "芝", "芝", "ダート", "ダート", "芝", "芝", "芝", "芝", "芝"]
    data["芝・ダート区分2"] = [np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan]
    data["右左回り・直線区分"] = ["右", "右", "右", "左", "左", "右", "右", "右", "右", "右"]
    data["内・外・襷区分"] = [np.nan] * 10
    data["距離(m)"] = [2000, 2000, 2000, 1400, 1400, 1600, 1600, 3000, 3000, 1200]
    data["天候"] = ["晴", "晴", "晴", "曇", "曇", "雨", "雨", "晴", "晴", "晴"]
    data["馬場状態1"] = ["良", "良", "良", "稍重", "稍重", "重", "重", "良", "良", "良"]
    data["馬場状態2"] = [np.nan] * 10
    data["発走時刻"] = ["10:00", "10:00", "10:00", "11:30", "11:30", "14:00", "14:00", "09:30", "09:30", "15:30"]

    # Row 43-44: Result columns
    data["着順"] = [1, 2, 3, 1, 2, 1, 2, 1, 2, 1]
    data["着順注記"] = [np.nan, np.nan, np.nan, np.nan, "降", np.nan, "中", np.nan, np.nan, np.nan]

    # Row 45-46: Entry identifiers
    data["枠番"] = [1, 2, 3, 1, 4, 2, 5, 1, 3, 1]
    data["馬番"] = [1, 2, 3, 4, 5, 1, 2, 1, 2, 1]

    # Row 47-51: Entry details
    data["馬名"] = [
        "馬A", "馬B", "馬C", "馬D", "馬E",
        "馬F", "馬G", "馬H", "馬I", "馬J",
    ]
    data["性別"] = ["牡", "牝", "牡", "セ", "牡", "牝", "牡", "牡", "牝", "牡"]
    data["馬齢"] = [4, 3, 5, 4, 3, 4, 5, 4, 3, 4]
    data["斤量"] = [57.0, 55.0, 57.0, 57.0, 54.0, 55.0, 57.0, 60.0, 58.0, 56.0]
    data["騎手"] = [
        "騎手A", "騎手B", "騎手C", "騎手D", "騎手E",
        "騎手F", "騎手G", "騎手H", "騎手I", "騎手J",
    ]

    # Row 52-58: Result details
    data["タイム"] = [
        "1:58.5", "1:58.8", "1:59.1",
        "1:23.4", "1:23.7",
        "1:35.2", np.nan,  # withdrawal -> no time
        "3:25.0", "3:25.8",
        "1:10.5",
    ]
    data["着差"] = [
        "", "3/4", "1.1/2",
        "", "1.3/4",
        "", np.nan,
        "", "5",
        "",
    ]
    data["1コーナー"] = [1, 3, 2, 2, 1, 1, np.nan, 1, 2, 1]
    data["2コーナー"] = [1, 3, 2, 2, 1, 1, np.nan, 1, 2, 1]
    data["3コーナー"] = [1, 2, 3, 1, 2, 1, np.nan, 1, 2, 1]
    data["4コーナー"] = [1, 2, 3, 1, 2, 1, np.nan, 1, 2, 1]
    data["上り"] = [34.5, 34.8, 35.0, 33.2, 33.5, 36.1, np.nan, 38.5, 38.8, 33.0]

    # Row 59-60: Market signals (post-race per D-03)
    data["単勝"] = [2.1, 3.5, 5.0, 4.2, 6.8, 3.0, 8.5, 10.0, 15.0, 1.8]
    data["人気"] = [1, 2, 3, 2, 4, 1, 5, 3, 6, 1]

    # Row 61-66: Physical + people
    data["馬体重"] = [480, 460, 500, 510, 470, 490, 505, 520, 480, 495]
    data["場体重増減"] = [2, -3, 0, 5, -1, 3, -2, 0, 4, 1]
    data["東西・外国・地方区分"] = ["東", "東", "東", "西", "西", "西", "西", "東", "東", "西"]
    data["調教師"] = [
        "調教師A", "調教師B", "調教師C", "調教師D", "調教師E",
        "調教師F", "調教師G", "調教師H", "調教師I", "調教師J",
    ]
    data["馬主"] = [
        "馬主A", "馬主B", "馬主C", "馬主D", "馬主E",
        "馬主F", "馬主G", "馬主H", "馬主I", "馬主J",
    ]
    data["賞金(万円)"] = [
        750.0, 300.0, 190.0,
        500.0, 200.0,
        900.0, np.nan,  # withdrawal -> no prize
        600.0, 240.0,
        400.0,
    ]

    df = pd.DataFrame(data)

    # Set proper dtypes for flag columns (str) to match DTYPE_SPEC behavior
    for col in FLAG_COLUMNS:
        df[col] = df[col].astype(object)

    return df


@pytest.fixture
def sample_odds_df() -> pd.DataFrame:
    """DataFrame mimicking odds.csv with 5 rows using actual column names.

    Uses race_ids that overlap with sample_race_result_df flat races:
    - 201501010101 (2015A)
    - 201502020202 (2015B)
    - 201603030303 (2016A)
    - 201504040404 (2015 obstacle - should be filtered)
    - 999999999999 (race not in race_result - should be filtered)

    After filtering to flat race_ids from race_result: 3 rows.
    """
    data: dict[str, list] = {}

    data["レースID"] = [
        "201501010101", "201502020202", "201603030303",
        "201504040404", "999999999999",
    ]

    # Fill non-trifecta columns with placeholder values (we only need trifecta cols)
    # All columns from odds.csv header except the trifecta columns and レースID
    non_trifecta_cols = [
        "単勝1_馬番", "単勝2_馬番", "単勝1_オッズ", "単勝2_オッズ", "単勝1_人気", "単勝2_人気",
        "複勝1_馬番", "複勝2_馬番", "複勝3_馬番", "複勝4_馬番", "複勝5_馬番",
        "複勝1_オッズ", "複勝2_オッズ", "複勝3_オッズ", "複勝4_オッズ", "複勝5_オッズ",
        "複勝1_人気", "複勝2_人気", "複勝3_人気", "複勝4_人気", "複勝5_人気",
        "枠連1_組合せ1", "枠連1_組合せ2", "枠連2_組合せ1", "枠連2_組合せ2",
        "枠連1_オッズ", "枠連2_オッズ", "枠連1_人気", "枠連2_人気",
        "馬連1_組合せ1", "馬連1_組合せ2", "馬連2_組合せ1", "馬連2_組合せ2",
        "馬連1_オッズ", "馬連2_オッズ", "馬連1_人気", "馬連2_人気",
        "ワイド1_組合せ1", "ワイド1_組合せ2", "ワイド2_組合せ1", "ワイド2_組合せ2",
        "ワイド3_組合せ1", "ワイド3_組合せ2", "ワイド4_組合せ1", "ワイド4_組合せ2",
        "ワイド5_組合せ1", "ワイド5_組合せ2", "ワイド6_組合せ1", "ワイド6_組合せ2",
        "ワイド7_組合せ1", "ワイド7_組合せ2",
        "ワイド1_オッズ", "ワイド2_オッズ", "ワイド3_オッズ", "ワイド4_オッズ",
        "ワイド5_オッズ", "ワイド6_オッズ", "ワイド7_オッズ",
        "ワイド1_人気", "ワイド2_人気", "ワイド3_人気", "ワイド4_人気",
        "ワイド5_人気", "ワイド6_人気", "ワイド7_人気",
        "馬単1_組合せ1", "馬単1_組合せ2", "馬単2_組合せ1", "馬単2_組合せ2",
        "馬単1_オッズ", "馬単2_オッズ", "馬単1_人気", "馬単2_人気",
    ]
    for col in non_trifecta_cols:
        data[col] = [np.nan] * 5

    # Trifecta columns (the ones we care about)
    data["三連複1_組合せ1"] = [1, 4, 1, np.nan, 2]
    data["三連複1_組合せ2"] = [2, 5, 2, np.nan, 3]
    data["三連複1_組合せ3"] = [3, np.nan, np.nan, np.nan, 4]
    data["三連複1_オッズ"] = [990, 1500, 800, np.nan, 2000]
    data["三連複1_人気"] = [1, 1, 1, np.nan, 1]

    data["三連複2_組合せ1"] = [np.nan, np.nan, np.nan, np.nan, np.nan]
    data["三連複2_組合せ2"] = [np.nan, np.nan, np.nan, np.nan, np.nan]
    data["三連複2_組合せ3"] = [np.nan, np.nan, np.nan, np.nan, np.nan]
    data["三連複2_オッズ"] = [np.nan, np.nan, np.nan, np.nan, np.nan]
    data["三連複2_人気"] = [np.nan, np.nan, np.nan, np.nan, np.nan]

    data["三連複3_組合せ1"] = [np.nan, np.nan, np.nan, np.nan, np.nan]
    data["三連複3_組合せ2"] = [np.nan, np.nan, np.nan, np.nan, np.nan]
    data["三連複3_組合せ3"] = [np.nan, np.nan, np.nan, np.nan, np.nan]
    data["三連複3_オッズ"] = [np.nan, np.nan, np.nan, np.nan, np.nan]
    data["三連複3_人気"] = [np.nan, np.nan, np.nan, np.nan, np.nan]

    # Also add the 三連単 columns to complete the 104-column structure
    trifecta_single_cols = [
        "三連単1_組合せ1", "三連単1_組合せ2", "三連単1_組合せ3",
        "三連単2_組合せ1", "三連単2_組合せ2", "三連単2_組合せ3",
        "三連単3_組合せ1", "三連単3_組合せ2", "三連単3_組合せ3",
        "三連単1_オッズ", "三連単2_オッズ", "三連単3_オッズ",
        "三連単1_人気", "三連単2_人気", "三連単3_人気",
    ]
    for col in trifecta_single_cols:
        data[col] = [np.nan] * 5

    return pd.DataFrame(data)


@pytest.fixture
def tmp_standard_dir(tmp_path: Path) -> Path:
    """Create and return a temporary data/standard/ directory for Parquet output."""
    standard_dir = tmp_path / "data" / "standard"
    standard_dir.mkdir(parents=True, exist_ok=True)
    return standard_dir


# ---------------------------------------------------------------------------
# Feature generator fixtures (Phase 3)
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_standard_race_df() -> pd.DataFrame:
    """Standard-layer race table with 6 rows (English column names).

    Key design:
    - 3 distinct course_names: 東京, 中山, 京都
    - 2 different dates: 2015-01-01 (東京, 中山), 2015-03-03 (京都)
    - Same-date different-course races for ordering tests
    - race_id format YYYYPPCCDDRR encodes course+date+number (globally unique)
    """
    return pd.DataFrame({
        "race_id": [
            "201501010101",  # 東京 R1 on 2015-01-01
            "201501010102",  # 東京 R2 on 2015-01-01
            "201501010201",  # 中山 R1 on 2015-01-01 (same date, different course)
            "201502020201",  # 中山 R1 on 2015-02-02
            "201503030101",  # 京都 R1 on 2015-03-03
            "201503030102",  # 京都 R2 on 2015-03-03
        ],
        "race_date": [
            "2015-01-01", "2015-01-01", "2015-01-01",
            "2015-02-02", "2015-03-03", "2015-03-03",
        ],
        "meeting_num": [1, 1, 1, 1, 1, 1],
        "course_code": ["01", "01", "02", "02", "03", "03"],
        "course_name": ["東京", "東京", "中山", "中山", "京都", "京都"],
        "meeting_day": [1, 1, 1, 1, 1, 1],
        "race_condition": [
            "4歳以上100万下", "3歳未勝利", "4歳以上500万下",
            "3歳新馬", "4歳以上1600万下", "3歳500万下",
        ],
        "race_number": [1, 2, 1, 1, 1, 2],
        "grade_revision": [None, None, None, None, None, None],
        "race_name": [
            "サンプルR1", "サンプルR2", "サンプルR3",
            "サンプルR4", "サンプルR5", "サンプルR6",
        ],
        "grade": [None, None, None, None, None, None],
        "obstacle": [None, None, None, None, None, None],
        "surface": ["芝", "芝", "芝", "ダート", "芝", "芝"],
        "surface_detail": [None, None, None, None, None, None],
        "direction": ["左", "左", "右", "右", "右", "右"],
        "course_detail": [None, None, None, None, None, None],
        "distance": [2000, 1600, 1200, 1400, 2200, 1800],
        "weather": ["晴", "晴", "晴", "曇", "雨", "雨"],
        "track_condition": ["良", "良", "良", "稍重", "重", "重"],
        "track_condition_detail": [None, None, None, None, None, None],
        "start_time": ["10:00", "10:30", "10:00", "11:00", "14:00", "14:30"],
    })


@pytest.fixture
def sample_standard_entry_df() -> pd.DataFrame:
    """Standard-layer entry table with 14 rows (English column names).

    Key design:
    - Horse "アームストロング" age 4 in 2015 (born 2011) and age 7 in 2025 (born 2018)
      -- tests same-name collision disambiguation via birth_year_proxy
    - Horse "馬A" appearing in 3 races on different dates -- tests lag ordering
    - Two races on same date at different courses -- tests race_id ordering
    - A finish_note "取" entry -- tests scratch detection
    - A finish_note "中" entry -- tests DNF detection
    - Jockey "騎手A" appearing in 3+ races across dates -- tests rolling stats
    - Trainer "調教師A" with 2 runners in same race -- tests race-level stat safety
    """
    return pd.DataFrame({
        "horse_race_id": [
            "20150101010101",  # アームストロング (born 2011) in 東京R1
            "20150101010102",  # 馬A in 東京R1
            "20150101010103",  # 馬C in 東京R1
            "20150101010201",  # 馬A in 東京R2 (2nd race for 馬A)
            "20150101010202",  # 馬D in 東京R2
            "20150101020101",  # 馬A in 中山R1 (3rd race for 馬A, same date as 東京R2)
            "20150101020102",  # アームストロング (born 2018) in 中山R1
            "20150101020103",  # 馬F in 中山R1 (finish_note=取)
            "20150202020101",  # 馬G in 中山R1 on 2015-02-02
            "20150202020102",  # 馬H in 中山R1 (finish_note=中)
            "20150303010101",  # 馬I in 京都R1 (same trainer as 馬J)
            "20150303010102",  # 馬J in 京都R1 (same trainer 調教師A)
            "20150303010201",  # 馬K in 京都R2
            "20150303010202",  # 馬L in 京都R2
        ],
        "race_id": [
            "201501010101", "201501010101", "201501010101",
            "201501010102", "201501010102",
            "201501010201", "201501010201", "201501010201",
            "201502020201", "201502020201",
            "201503030101", "201503030101",
            "201503030102", "201503030102",
        ],
        "bracket_num": [1, 2, 3, 1, 2, 1, 2, 3, 1, 4, 1, 2, 1, 3],
        "horse_number": [1, 2, 3, 1, 2, 1, 2, 3, 1, 4, 1, 2, 1, 3],
        "horse_name": [
            "アームストロング", "馬A", "馬C",
            "馬A", "馬D",
            "馬A", "アームストロング", "馬F",
            "馬G", "馬H",
            "馬I", "馬J",
            "馬K", "馬L",
        ],
        "sex": ["牡", "牡", "牝", "牡", "セ", "牡", "牡", "牝", "牡", "牝", "牡", "牡", "牝", "牡"],
        "age": [4, 5, 3, 5, 4, 5, 7, 3, 4, 5, 6, 4, 3, 5],
        "weight_assigned": [57.0, 57.0, 54.0, 57.0, 57.0, 57.0, 56.0, 52.0, 57.0, 55.0, 58.0, 57.0, 54.0, 57.0],
        "jockey": [
            "騎手A", "騎手B", "騎手C",
            "騎手D", "騎手A",
            "騎手A", "騎手E", "騎手F",
            "騎手G", "騎手H",
            "騎手I", "騎手J",
            "騎手A", "騎手K",
        ],
        "trainer": [
            "調教師X", "調教師Y", "調教師Z",
            "調教師X", "調教師W",
            "調教師X", "調教師V", "調教師U",
            "調教師T", "調教師S",
            "調教師A", "調教師A",
            "調教師R", "調教師Q",
        ],
        "owner": [
            "馬主A", "馬主B", "馬主C", "馬主A", "馬主D",
            "馬主A", "馬主E", "馬主F", "馬主G", "馬主H",
            "馬主I", "馬主J", "馬主K", "馬主L",
        ],
        "horse_weight": [480, 460, 420, 462, 510, 465, 490, 430, 500, 475, 520, 505, 415, 488],
        "weight_change": [2, -3, 0, 2, 5, 3, -1, -2, 4, 0, -3, 2, 0, -5],
        "region": ["東", "東", "東", "東", "東", "西", "西", "西", "西", "西", "西", "西", "西", "西"],
        "popularity": [1, 3, 8, 2, 5, 1, 4, 7, 3, 6, 2, 4, 1, 5],
        "win_odds": [2.1, 5.5, 25.0, 3.8, 12.0, 2.5, 8.0, 18.0, 4.5, 15.0, 3.2, 7.5, 2.8, 10.0],
    })


@pytest.fixture
def sample_standard_result_df() -> pd.DataFrame:
    """Standard-layer result table with 14 rows (1:1 with entry, English column names).

    Key design:
    - finish_position variety: 1-8, and None for 取/中 entries
    - finish_note: one "取", one "中", rest None (normal finishes)
    - margin values: "3/4", "1.1/2", None, "ハナ" (tests Plan 02 margin conversion)
    - finish_time: "1:58.5", "1:59.1", etc.
    - last_3f: 34.5-36.0 range, corner_4: 1-5
    """
    return pd.DataFrame({
        "horse_race_id": [
            "20150101010101", "20150101010102", "20150101010103",
            "20150101010201", "20150101010202",
            "20150101020101", "20150101020102", "20150101020103",
            "20150202020101", "20150202020102",
            "20150303010101", "20150303010102",
            "20150303010201", "20150303010202",
        ],
        "race_id": [
            "201501010101", "201501010101", "201501010101",
            "201501010102", "201501010102",
            "201501010201", "201501010201", "201501010201",
            "201502020201", "201502020201",
            "201503030101", "201503030101",
            "201503030102", "201503030102",
        ],
        "finish_position": [1, 2, 3, 1, 4, 2, 5, None, 1, None, 3, 6, 1, 2],
        "finish_note": [None, None, None, None, None, None, None, "取", None, "中", None, None, None, None],
        "finish_time": [
            "1:58.5", "1:58.8", "1:59.1",
            "1:35.2", "1:36.0",
            "1:10.5", "1:11.2", None,  # 取 -> no time
            "1:23.4", None,  # 中 -> no time
            "2:15.3", "2:15.8",
            "1:48.2", "1:48.6",
        ],
        "margin": [
            None, "3/4", "1.1/2",
            None, "2",
            "ハナ", "3", None,
            None, None,
            "1.1/4", "5",
            None, "アタマ",
        ],
        "corner_1": [1, 3, 2, 1, 4, 1, 3, None, 2, None, 1, 5, 1, 3],
        "corner_2": [1, 3, 2, 1, 4, 1, 3, None, 2, None, 1, 5, 1, 3],
        "corner_3": [1, 2, 3, 1, 3, 1, 4, None, 1, None, 2, 5, 1, 2],
        "corner_4": [1, 2, 3, 1, 3, 1, 4, None, 1, None, 2, 5, 1, 2],
        "last_3f": [34.5, 34.8, 35.0, 36.0, 35.5, 33.2, 35.8, None, 33.5, None, 35.1, 36.0, 34.0, 34.2],
        "prize_money": [750.0, 300.0, 190.0, 500.0, None, 200.0, None, None, 400.0, None, 150.0, None, 600.0, 240.0],
    })


@pytest.fixture
def sample_feature_merged_df(
    sample_standard_race_df: pd.DataFrame,
    sample_standard_entry_df: pd.DataFrame,
    sample_standard_result_df: pd.DataFrame,
    tmp_path: Path,
) -> pd.DataFrame:
    """Pre-merged DataFrame via load_and_merge using test Parquet files.

    Writes the three standard DataFrames as temporary Parquet files,
    then calls load_and_merge() to produce the merged output.
    """
    from src.pipeline.feature_generator import load_and_merge

    standard_dir = tmp_path / "data" / "standard"
    standard_dir.mkdir(parents=True, exist_ok=True)

    sample_standard_race_df.to_parquet(standard_dir / "race.parquet", engine="pyarrow", index=False)
    sample_standard_entry_df.to_parquet(standard_dir / "entry.parquet", engine="pyarrow", index=False)
    sample_standard_result_df.to_parquet(standard_dir / "result.parquet", engine="pyarrow", index=False)

    return load_and_merge(standard_dir)


@pytest.fixture
def tmp_feature_dir(tmp_path: Path) -> Path:
    """Create and return a temporary data/feature/ output directory."""
    feature_dir = tmp_path / "data" / "feature"
    feature_dir.mkdir(parents=True, exist_ok=True)
    return feature_dir


# ---------------------------------------------------------------------------
# Phase 6 Plan 06-02 integration fixtures (HIGH #5 separate input path)
# ---------------------------------------------------------------------------


def _reindex_to_schema(df: pd.DataFrame, schema: type) -> pd.DataFrame:
    """Reindex a sample DataFrame to ``list(schema.model_fields.keys())``.

    Sample fixtures (sample_standard_*) carry only the human-readable subset of
    schema columns; integration needs ALL schema columns in canonical order so
    the reindex-then-concat pipeline works the same way against synthetic test
    data as it does against the real corpora.
    """
    cols = list(schema.model_fields.keys())
    return df.reindex(columns=cols)


@pytest.fixture
def tmp_kaggle_input_dir(
    tmp_path: Path,
    sample_standard_race_df: pd.DataFrame,
    sample_standard_entry_df: pd.DataFrame,
    sample_standard_result_df: pd.DataFrame,
) -> Path:
    """Create the SEPARATE Kaggle input path (HIGH #5).

    Writes one tiny synthetic Parquet per table at::

        tmp_path/data/standard/kaggle/{race,entry,result}.parquet

    This path is DISTINCT from the integration output path
    (``tmp_path/data/standard/{race,entry,result}.parquet``) and is never read
    by ``integrate_standard_layer`` as its own output -- it is the stable,
    idempotent Kaggle input that survives repeated invocations.
    """
    from src.schemas.entry import EntrySchema
    from src.schemas.race import RaceSchema
    from src.schemas.result import ResultSchema

    kaggle_dir = tmp_path / "data" / "standard" / "kaggle"
    kaggle_dir.mkdir(parents=True, exist_ok=True)

    for df, schema, name in (
        (sample_standard_race_df, RaceSchema, "race"),
        (sample_standard_entry_df, EntrySchema, "entry"),
        (sample_standard_result_df, ResultSchema, "result"),
    ):
        reindexed = _reindex_to_schema(df, schema)
        reindexed.to_parquet(
            kaggle_dir / f"{name}.parquet", engine="pyarrow", index=False
        )

    return kaggle_dir


@pytest.fixture
def tmp_scraped_partitions_dir(
    tmp_path: Path,
    sample_standard_race_df: pd.DataFrame,
    sample_standard_entry_df: pd.DataFrame,
    sample_standard_result_df: pd.DataFrame,
) -> Path:
    """Create synthetic scraped month-partitioned Parquet (mirrors Phase 4 layout).

    Writes two partitions (202301, 202302) under::

        tmp_path/data/standard/scraped/{YYYYMM}/{race,entry,result}.parquet

    The races in the sample fixtures use 2015-era race_ids, so these scraped
    partitions are NON-OVERLAPPING with Kaggle by race_id (HIGH #5 idempotency
    boundary). Each per-table Parquet is reindexed to canonical schema order so
    the integration read+reindex+concat pipeline is exercised end-to-end.
    """
    from src.schemas.entry import EntrySchema
    from src.schemas.race import RaceSchema
    from src.schemas.result import ResultSchema

    standard_dir = tmp_path / "data" / "standard"
    scraped_root = standard_dir / "scraped"

    # Build two distinct synthetic scraped months. Each month has 1 race with
    # 2 entries/results so PKs are globally unique across months and the
    # union of partition PK-sets == output unique PK count (MEDIUM #20).
    month_blocks = [
        (
            "202301",
            {
                "race_id": "202301030101",
                "horse_race_ids": ["20230103010101", "20230103010102"],
            },
        ),
        (
            "202302",
            {
                "race_id": "202302040101",
                "horse_race_ids": ["20230204010101", "20230204010102"],
            },
        ),
    ]

    for month, spec in month_blocks:
        month_dir = scraped_root / month
        month_dir.mkdir(parents=True, exist_ok=True)

        race_id = spec["race_id"]
        hids = spec["horse_race_ids"]

        # Race: 1 row (template off sample, override keys).
        race_row = sample_standard_race_df.iloc[[0]].copy()
        race_row["race_id"] = race_id
        race_row["race_date"] = f"{month[:4]}-{month[4:6]}-03" if month == "202301" else f"{month[:4]}-{month[4:6]}-04"
        race_reindexed = _reindex_to_schema(race_row, RaceSchema)
        race_reindexed.to_parquet(
            month_dir / "race.parquet", engine="pyarrow", index=False
        )

        # Entry: 2 rows.
        entry_rows = sample_standard_entry_df.iloc[[0, 1]].copy()
        entry_rows["horse_race_id"] = hids
        entry_rows["race_id"] = race_id
        entry_reindexed = _reindex_to_schema(entry_rows, EntrySchema)
        entry_reindexed.to_parquet(
            month_dir / "entry.parquet", engine="pyarrow", index=False
        )

        # Result: 2 rows, same horse_race_ids (1-to-1).
        result_rows = sample_standard_result_df.iloc[[0, 1]].copy()
        result_rows["horse_race_id"] = hids
        result_rows["race_id"] = race_id
        result_reindexed = _reindex_to_schema(result_rows, ResultSchema)
        result_reindexed.to_parquet(
            month_dir / "result.parquet", engine="pyarrow", index=False
        )

    return scraped_root


# ---------------------------------------------------------------------------
# Lag feature fixtures (Plan 03-03)
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_lag_merged_df() -> pd.DataFrame:
    """Pre-built DataFrame for lag feature tests with scratch-between-valid-starts.

    Contains ~16 rows with:
    - Horse "馬A" with 3 valid starts on different dates (tests basic lag correctness)
    - Horse "馬B" with valid_start, SCRATCHED (取), valid_start (tests scratch filtering)
    - Horse "アームストロング" (born 2011) with 2 valid starts (tests entity key isolation)
    - Horse "アームストロング" (born 2008) with 1 valid start (same name, different entity)
    - Same-day races at different courses for "馬A" (tests race_id ordering in lag chain)

    All columns needed by compute_lag_features are included.
    """
    rows = [
        # Horse 馬A: race 1 at 東京 on 2015-01-01 (R1) -- finish_position=3
        {
            "race_id": "201501010101", "race_date": "2015-01-01",
            "horse_entity_key": "馬A_2010", "horse_name": "馬A",
            "finish_position": 3, "finish_note": None,
            "last_3f": 35.0, "corner_4": 3,
            "finish_time_zscore": 0.5, "margin_numeric": 1.5,
            "jockey": "騎手A", "trainer": "調教師X",
        },
        # Horse 馬A: race 2 at 東京 on 2015-01-01 (R2) -- same day, different race_id
        # race_id 201501010102 > 201501010101 so this comes after R1
        {
            "race_id": "201501010102", "race_date": "2015-01-01",
            "horse_entity_key": "馬A_2010", "horse_name": "馬A",
            "finish_position": 1, "finish_note": None,
            "last_3f": 34.0, "corner_4": 1,
            "finish_time_zscore": -1.2, "margin_numeric": None,
            "jockey": "騎手A", "trainer": "調教師X",
        },
        # Horse 馬A: race 3 at 中山 on 2015-02-02 -- tests cross-course lag
        {
            "race_id": "201502020201", "race_date": "2015-02-02",
            "horse_entity_key": "馬A_2010", "horse_name": "馬A",
            "finish_position": 2, "finish_note": None,
            "last_3f": 34.5, "corner_4": 2,
            "finish_time_zscore": 0.3, "margin_numeric": 0.75,
            "jockey": "騎手A", "trainer": "調教師X",
        },
        # Horse 馬B: race 1 at 東京 on 2015-01-01 (R1) -- valid start, pos=5
        {
            "race_id": "201501010101", "race_date": "2015-01-01",
            "horse_entity_key": "馬B_2011", "horse_name": "馬B",
            "finish_position": 5, "finish_note": None,
            "last_3f": 36.0, "corner_4": 5,
            "finish_time_zscore": 1.5, "margin_numeric": 3.0,
            "jockey": "騎手B", "trainer": "調教師Y",
        },
        # Horse 馬B: SCRATCHED at 東京 on 2015-01-01 (R2) -- 取, does NOT run
        {
            "race_id": "201501010102", "race_date": "2015-01-01",
            "horse_entity_key": "馬B_2011", "horse_name": "馬B",
            "finish_position": None, "finish_note": "取",
            "last_3f": None, "corner_4": None,
            "finish_time_zscore": None, "margin_numeric": None,
            "jockey": "騎手B", "trainer": "調教師Y",
        },
        # Horse 馬B: race 2 at 中山 on 2015-02-02 -- valid start, pos=3
        # prev_1 should point to the R1 result (pos=5), NOT the scratched row
        {
            "race_id": "201502020201", "race_date": "2015-02-02",
            "horse_entity_key": "馬B_2011", "horse_name": "馬B",
            "finish_position": 3, "finish_note": None,
            "last_3f": 34.8, "corner_4": 2,
            "finish_time_zscore": -0.5, "margin_numeric": 1.25,
            "jockey": "騎手B", "trainer": "調教師Y",
        },
        # Horse 馬B: race 3 at 京都 on 2015-03-03 (R1) -- valid start, pos=1
        {
            "race_id": "201503030101", "race_date": "2015-03-03",
            "horse_entity_key": "馬B_2011", "horse_name": "馬B",
            "finish_position": 1, "finish_note": None,
            "last_3f": 33.5, "corner_4": 1,
            "finish_time_zscore": -2.0, "margin_numeric": None,
            "jockey": "騎手B", "trainer": "調教師Y",
        },
        # Horse アームストロング_2011: race 1 at 東京 on 2015-01-01 (R1) -- pos=1
        {
            "race_id": "201501010101", "race_date": "2015-01-01",
            "horse_entity_key": "アームストロング_2011", "horse_name": "アームストロング",
            "finish_position": 1, "finish_note": None,
            "last_3f": 34.5, "corner_4": 1,
            "finish_time_zscore": -1.0, "margin_numeric": None,
            "jockey": "騎手C", "trainer": "調教師Z",
        },
        # Horse アームストロング_2011: race 2 at 中山 on 2015-01-01 (R1) -- same day, different course
        {
            "race_id": "201501010201", "race_date": "2015-01-01",
            "horse_entity_key": "アームストロング_2011", "horse_name": "アームストロング",
            "finish_position": 4, "finish_note": None,
            "last_3f": 35.5, "corner_4": 3,
            "finish_time_zscore": 0.8, "margin_numeric": 2.0,
            "jockey": "騎手C", "trainer": "調教師Z",
        },
        # Horse アームストロング_2008: race 1 at 中山 on 2015-01-01 (R1) -- pos=2
        # Different entity key from the other アームストロング
        {
            "race_id": "201501010201", "race_date": "2015-01-01",
            "horse_entity_key": "アームストロング_2008", "horse_name": "アームストロング",
            "finish_position": 2, "finish_note": None,
            "last_3f": 34.2, "corner_4": 2,
            "finish_time_zscore": -0.3, "margin_numeric": 0.5,
            "jockey": "騎手D", "trainer": "調教師W",
        },
        # Horse 馬C: DNF at 中山 on 2015-01-01 (R1) -- finish_note=中 (valid start)
        {
            "race_id": "201501010201", "race_date": "2015-01-01",
            "horse_entity_key": "馬C_2012", "horse_name": "馬C",
            "finish_position": None, "finish_note": "中",
            "last_3f": None, "corner_4": None,
            "finish_time_zscore": None, "margin_numeric": None,
            "jockey": "騎手E", "trainer": "調教師V",
        },
        # Horse 馬C: race 2 at 中山 on 2015-02-02 (R1) -- valid start
        # prev_1 should point to DNF row (中 is valid start)
        {
            "race_id": "201502020201", "race_date": "2015-02-02",
            "horse_entity_key": "馬C_2012", "horse_name": "馬C",
            "finish_position": 6, "finish_note": None,
            "last_3f": 36.5, "corner_4": 4,
            "finish_time_zscore": 1.8, "margin_numeric": 4.0,
            "jockey": "騎手E", "trainer": "調教師V",
        },
        # Horse 馬D: REMOVED (除) at 中山 on 2015-02-02 (R1) -- NOT a valid start
        {
            "race_id": "201502020201", "race_date": "2015-02-02",
            "horse_entity_key": "馬D_2013", "horse_name": "馬D",
            "finish_position": None, "finish_note": "除",
            "last_3f": None, "corner_4": None,
            "finish_time_zscore": None, "margin_numeric": None,
            "jockey": "騎手F", "trainer": "調教師U",
        },
        # Horse 馬E: extra horse at 京都 on 2015-03-03 (R1) -- pos=4
        {
            "race_id": "201503030101", "race_date": "2015-03-03",
            "horse_entity_key": "馬E_2014", "horse_name": "馬E",
            "finish_position": 4, "finish_note": None,
            "last_3f": 35.0, "corner_4": 3,
            "finish_time_zscore": 0.2, "margin_numeric": 1.0,
            "jockey": "騎手G", "trainer": "調教師A",
        },
        # Horse 馬F: extra horse at 京都 on 2015-03-03 (R2) -- pos=1
        {
            "race_id": "201503030102", "race_date": "2015-03-03",
            "horse_entity_key": "馬F_2015", "horse_name": "馬F",
            "finish_position": 1, "finish_note": None,
            "last_3f": 33.8, "corner_4": 1,
            "finish_time_zscore": -1.5, "margin_numeric": None,
            "jockey": "騎手H", "trainer": "調教師A",
        },
    ]
    df = pd.DataFrame(rows)
    return df.sort_values(["horse_entity_key", "race_date", "race_id"]).reset_index(drop=True)
