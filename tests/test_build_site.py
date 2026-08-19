from pathlib import Path

from scripts.build_site import build, load_items, load_trend_posts


def test_load_items_returns_empty_list_when_missing(tmp_path):
    assert load_items(tmp_path / "items.json") == []


def test_load_items_reads_json(tmp_path):
    path = tmp_path / "items.json"
    path.write_text('[{"title": "a", "url": "https://example.com/a"}]', encoding="utf-8")
    assert load_items(path) == [{"title": "a", "url": "https://example.com/a"}]


def test_load_trend_posts_parses_frontmatter_and_sorts_desc(tmp_path):
    (tmp_path / "old.md").write_text(
        "---\ntitle: 古い記事\ndate: 2026-08-01\n---\n本文A\n", encoding="utf-8"
    )
    (tmp_path / "new.md").write_text(
        "---\ntitle: 新しい記事\ndate: 2026-08-15\n---\n本文B\n", encoding="utf-8"
    )
    posts = load_trend_posts(tmp_path)
    assert [p["title"] for p in posts] == ["新しい記事", "古い記事"]
    assert posts[0]["slug"] == "new"
    assert "本文B" in posts[0]["html"]
    assert posts[0]["date"] == "2026-08-15"
    assert posts[1]["date"] == "2026-08-01"


def test_load_trend_posts_empty_dir_returns_empty_list(tmp_path):
    assert load_trend_posts(tmp_path / "does-not-exist") == []


def test_build_writes_expected_files(tmp_path):
    items = [{
        "title": "新作スニーカー登場",
        "url": "https://example.com/a",
        "source": "Hypebeast",
        "published": "2026-08-20T00:00:00+00:00",
        "summary": "新作の紹介文",
        "image_url": None,
    }]
    trends = [{"title": "今週のトレンド", "date": "2026-08-20", "slug": "week-1", "html": "<p>本文</p>"}]

    build(tmp_path, items, trends)

    assert (tmp_path / "index.html").exists()
    assert "新作スニーカー登場" in (tmp_path / "index.html").read_text(encoding="utf-8")

    feed_html = (tmp_path / "feed.html").read_text(encoding="utf-8")
    assert "新作スニーカー登場" in feed_html
    assert "Hypebeast" in feed_html

    trends_index = (tmp_path / "trends" / "index.html").read_text(encoding="utf-8")
    assert "今週のトレンド" in trends_index

    detail = (tmp_path / "trends" / "week-1.html").read_text(encoding="utf-8")
    assert "本文" in detail
