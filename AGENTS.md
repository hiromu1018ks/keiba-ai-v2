# AGENTS.md

JRA中央競馬の三連複EV判定システム。各馬の3着内確率を推定し、市場オッズとのズレから割安な三連複を抽出する。

## Commands

パッケージ管理は **pip + setuptools (editable install)** で運用中。CLAUDE.md / STACK.md に Poetry と書かれているが、実際の `pyproject.toml` は setuptools バックエンドで、`poetry.lock` は存在しない。

```bash
# 初回セットアップ (Python 3.12, mise/rtx 経由を想定)
pip install -e ".[dev]"

# テスト
python -m pytest                    # 全テスト
python -m pytest tests/schemas/test_race.py        # 単一ファイル
python -m pytest tests/schemas/test_race.py::test_name  # 単一テスト

# Lint / Format
ruff check .                        # リント
ruff format .                       # フォーマット (line-length=100, target=py312)

# Typecheck (mypy設定は pyproject.toml に未定義 → パスを明示指定)
mypy src
```

## Architecture

3層データパイプライン。すべて `data/` 配下（gitignore対象）。

- **raw/**: Kaggle CSV、スクレイピングHTML等の取得元そのまま
- **standard/**: 5テーブルのParquet（race, entry, result, odds_trifecta, payoff）。`race_id` が全テーブルの結合キー
- **feature/**: LightGBM投入用特徴量

パッケージ構成:
- `src/schemas/` — Pydanticスキーマ定義（型定義専用。行単位バリデーションには使わない）
- `src/pipeline/` — CSV→Parquet変換、特徴量生成、バリデーション
- `src.pipeline` / `src.schemas` の `__init__.py` で主要シンボルを再エクスポート

## Critical Conventions

### データリーク監査（最重要）

スキーマフィールドの `json_schema_extra` に `{"pre_race": bool, "table": str}` を付与し、`audit_leakage()` がpost-race列の混入を検出する。

- **厳密名一致のみ**。部分一致は使わない。`prev_1_last_3f` は `last_3f` のリークとして誤検出されない（`src/schemas/audit.py`）
- `popularity` / `win_odds` は post-race 扱い（D-03）。特徴量からは除外（D-15）

### CSV読み込みの癖

- Kaggle CSVはBOM付き → `encoding="utf-8-sig"` 必須
- `DTYPE_SPEC`（`src/pipeline/column_mapping.py`）で23列を `dtype=str` 指定しないと DtypeWarning 発生。`競馬場コード` はゼロ埋め（"01"-"10"）を保持するため str 必須
- フラグ列（`レース記号/*` の20列）は複数CSV列が1スキーマフィールドにマージされる

### データスコープ

2015年以降の平地競走のみ。障害（`障害区分="障害"`）は除外（D-01）。

### インポート

`from src.schemas import ...`, `from src.pipeline import ...` の絶対インポート。パッケージルートは `src/`。

## Decision Labels

コード内で `D-01`〜`D-15` 等のラベルが参照される。各ラベルの意味は `.planning/phases/` 配下の各フェーズ成果物に記載。主なもの:
- **D-01**: 障害除外
- **D-03**: popularity/win_odds は post-race
- **D-06**: テーブルごとに1つのParquetファイル
- **D-12**: `audit_leakage()` は警告のみで例外を投げない

## Notes

- `@pytest.mark.integration` マーカーが一部のテストに付与されているが、`pyproject.toml` に未登録のため警告が出る
- CI / pre-commit / Makefile は未設定。ローカルで `ruff check . && mypy src && pytest` を実行すること
- GSDワークフローを使用（`.planning/` 配下でフェーズ管理）。編集前に `/gsd-quick` 等でコンテキストを同期することが CLAUDE.md で指示されている

## Communication

ユーザーへの回答は **日本語** で行うこと。
