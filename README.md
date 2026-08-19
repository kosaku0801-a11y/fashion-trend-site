# ファッショントレンドサイト

ストリート・カジュアル系ブランドの新着情報とトレンド分析を専門メディアのRSSから自動収集して公開する静的サイト。

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

## 手動実行

```bash
python scripts/fetch_feeds.py
python scripts/build_site.py
```

## テスト

```bash
pytest
```
