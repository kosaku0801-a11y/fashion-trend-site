from pathlib import Path

from scripts.build_site import load_items, load_trend_posts


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


def test_load_trend_posts_empty_dir_returns_empty_list(tmp_path):
    assert load_trend_posts(tmp_path / "does-not-exist") == []
