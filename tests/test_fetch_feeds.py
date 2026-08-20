import json
from unittest.mock import patch

from scripts.fetch_feeds import fetch_source, parse_feed, load_existing_items, merge_items, save_items

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


def test_parse_feed_rejects_javascript_url_scheme():
    malicious_rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Malicious Feed</title>
<item>
<title>危険なリンク</title>
<link>javascript:alert(1)</link>
<description>説明文</description>
<pubDate>Thu, 20 Aug 2026 03:00:00 GMT</pubDate>
</item>
</channel>
</rss>"""
    items = parse_feed(malicious_rss, "SampleMedia")
    assert len(items) == 1
    assert items[0]["url"] == ""


def test_parse_feed_rejects_javascript_image_url_scheme():
    malicious_rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
<channel>
<title>Malicious Feed</title>
<item>
<title>危険な画像リンク</title>
<link>https://example.com/a</link>
<description>説明文</description>
<media:thumbnail url="javascript:alert(1)" />
<pubDate>Thu, 20 Aug 2026 03:00:00 GMT</pubDate>
</item>
</channel>
</rss>"""
    items = parse_feed(malicious_rss, "SampleMedia")
    assert len(items) == 1
    assert items[0]["url"] == "https://example.com/a"
    assert items[0]["image_url"] is None


def test_parse_feed_extracts_image_from_description_img_tag():
    # Fashionsnap/Hypebeast両方の実データはmedia:thumbnail/media:content拡張要素を使わず、
    # descriptionの先頭に<img src="...">を埋め込み、その後ろに本文が続く形式で画像を提供する。
    rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Sample Feed</title>
<item>
<title>サンプル記事</title>
<link>https://example.com/item-with-image</link>
<description>&lt;img src="https://example.com/photo.jpg" /&gt; お笑いトリオの記事本文がここに続きます。</description>
<pubDate>Thu, 20 Aug 2026 03:00:00 GMT</pubDate>
</item>
</channel>
</rss>"""
    items = parse_feed(rss, "SampleMedia")
    assert len(items) == 1
    assert items[0]["image_url"] == "https://example.com/photo.jpg"


def test_parse_feed_unescapes_query_string_ampersands_in_description_image():
    # Hypebeastの実データはクエリ文字列付きの画像URLを持ち、XML上は`&amp;amp;`と
    # 二重エスケープされているため、feedparserが1段階デコードした後のsummaryには
    # `&amp;`が残る。html.unescape()でさらに1段階デコードして実URLに戻す必要がある。
    rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Sample Feed</title>
<item>
<title>サンプル記事2</title>
<link>https://example.com/item-with-query-image</link>
<description>&lt;img src="https://example.com/photo.jpg?w=800&amp;amp;q=90" /&gt; 本文です。</description>
<pubDate>Thu, 20 Aug 2026 03:00:00 GMT</pubDate>
</item>
</channel>
</rss>"""
    items = parse_feed(rss, "SampleMedia")
    assert items[0]["image_url"] == "https://example.com/photo.jpg?w=800&q=90"


def test_parse_feed_rejects_unsafe_scheme_in_description_image():
    rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Sample Feed</title>
<item>
<title>危険な画像リンク（description内）</title>
<link>https://example.com/item-unsafe-image</link>
<description>&lt;img src="javascript:alert(1)" /&gt; 本文です。</description>
<pubDate>Thu, 20 Aug 2026 03:00:00 GMT</pubDate>
</item>
</channel>
</rss>"""
    items = parse_feed(rss, "SampleMedia")
    assert items[0]["image_url"] is None


def test_parse_feed_still_prefers_media_thumbnail_when_present():
    # media:thumbnail/media:content経由の既存の抽出パスが、description内img
    # フォールバックの追加によって壊れていないことを確認する回帰テスト。
    rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
<channel>
<title>Sample Feed</title>
<item>
<title>media:thumbnail付き記事</title>
<link>https://example.com/item-media-thumbnail</link>
<description>&lt;img src="https://example.com/should-not-be-used.jpg" /&gt; 本文です。</description>
<media:thumbnail url="https://example.com/thumbnail.jpg" />
<pubDate>Thu, 20 Aug 2026 03:00:00 GMT</pubDate>
</item>
</channel>
</rss>"""
    items = parse_feed(rss, "SampleMedia")
    assert items[0]["image_url"] == "https://example.com/thumbnail.jpg"


def test_parse_feed_no_image_anywhere_returns_none_without_crashing():
    rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Sample Feed</title>
<item>
<title>画像の無い記事</title>
<link>https://example.com/item-no-image</link>
<description>画像を含まない普通の説明文です。</description>
<pubDate>Thu, 20 Aug 2026 03:00:00 GMT</pubDate>
</item>
</channel>
</rss>"""
    items = parse_feed(rss, "SampleMedia")
    assert items[0]["image_url"] is None


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


def test_merge_items_ignores_missing_url_without_raising():
    existing = [{"url": "https://example.com/a", "published": "2026-08-19T00:00:00+00:00"}]
    new_items = [
        {"title": "urlが無いアイテム", "published": "2026-08-20T00:00:00+00:00"},
        {"url": "https://example.com/b", "published": "2026-08-18T00:00:00+00:00"},
    ]
    merged = merge_items(existing, new_items)
    # urlの無いアイテムも消えずに残る（重複判定の対象外として扱われる）
    assert len(merged) == 3
    urls = [item.get("url") for item in merged]
    assert "https://example.com/a" in urls
    assert "https://example.com/b" in urls


def test_merge_items_sorts_missing_published_last():
    existing = []
    new_items = [
        {"url": "https://example.com/no-date"},  # publishedキーが無い
        {"url": "https://example.com/a", "published": "2026-08-20T00:00:00+00:00"},
    ]
    merged = merge_items(existing, new_items)
    assert [item["url"] for item in merged] == [
        "https://example.com/a",
        "https://example.com/no-date",
    ]


def test_merge_items_existing_missing_url_does_not_raise():
    existing = [{"title": "既存だがurlが無い", "published": "2026-08-19T00:00:00+00:00"}]
    new_items = [{"url": "https://example.com/b", "published": "2026-08-20T00:00:00+00:00"}]
    merged = merge_items(existing, new_items)
    assert len(merged) == 2


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


def test_fetch_source_returns_empty_list_on_parse_error():
    source = {"name": "BrokenMedia", "url": "https://example.com/broken.xml"}
    with patch("scripts.fetch_feeds.parse_feed", side_effect=ValueError("boom")):
        result = fetch_source(source)
    assert result == []


def test_fetch_source_returns_items_on_success():
    source = {"name": "SampleMedia", "url": "https://example.com/feed.xml"}
    fake_items = [{"url": "https://example.com/a", "title": "a", "published": "2026-08-20T00:00:00+00:00"}]
    with patch("scripts.fetch_feeds.parse_feed", return_value=fake_items):
        result = fetch_source(source)
    assert result == fake_items
