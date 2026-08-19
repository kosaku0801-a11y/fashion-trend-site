from scripts.fetch_feeds import parse_feed

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
