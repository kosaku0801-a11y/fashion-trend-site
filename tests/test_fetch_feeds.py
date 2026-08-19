import json

from scripts.fetch_feeds import parse_feed, load_existing_items, merge_items, save_items

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Sample Feed</title>
<item>
<title>サンプル記事1</title>
<link>https://example.com/item1</link>
<description>サンプルの説明文です</description>
<pubDate>Thu, 20 Aug 2026 03:00:00 GMT</pubDate>
</item>
</channel>
</rss>"""


def test_parse_feed_extracts_fields():
    items = parse_feed(SAMPLE_RSS, "SampleMedia")
    assert len(items) == 1
    item = items[0]
    assert item["title"] == "サンプル記事1"
    assert item["url"] == "https://example.com/item1"
    assert item["source"] == "SampleMedia"
    assert item["summary"] == "サンプルの説明文です"
    assert item["published"] == "2026-08-20T03:00:00+00:00"
    assert item["image_url"] is None


def test_parse_feed_empty_feed_returns_empty_list():
    empty_rss = """<?xml version="1.0"?><rss version="2.0"><channel><title>Empty</title></channel></rss>"""
    assert parse_feed(empty_rss, "SampleMedia") == []


def test_merge_items_removes_duplicates_by_url():
    existing = [{"url": "https://example.com/a", "published": "2026-08-19T00:00:00+00:00"}]
    new_items = [
        {"url": "https://example.com/a", "published": "2026-08-19T00:00:00+00:00"},
        {"url": "https://example.com/b", "published": "2026-08-20T00:00:00+00:00"},
    ]
    merged = merge_items(existing, new_items)
    assert [item["url"] for item in merged] == [
        "https://example.com/b",
        "https://example.com/a",
    ]


def test_load_existing_items_returns_empty_list_when_missing(tmp_path):
    missing_path = tmp_path / "items.json"
    assert load_existing_items(missing_path) == []


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "items.json"
    items = [{"url": "https://example.com/a", "title": "テスト記事", "published": "2026-08-20T00:00:00+00:00"}]
    save_items(items, path)
    loaded = load_existing_items(path)
    assert loaded == items
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    assert raw == items
