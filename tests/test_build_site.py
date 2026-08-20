from pathlib import Path

from scripts.build_site import build, excerpt, load_items, load_trend_posts


def test_excerpt_strips_html_tags_and_entities_and_truncates():
    raw = (
        '<div><img src="https://example.com/a.jpg" /><p>' +
        "とても&amp;素敵な新作スニーカーが登場しました。" * 10 +
        "</p></div>"
    )
    result = excerpt(raw)
    assert "<img" not in result
    assert "<p>" not in result
    assert "&amp;" not in result
    assert "&" in result  # アンエスケープされて素の文字になっている
    assert len(result) == 201  # 200文字 + "…"
    assert result.endswith("…")


def test_excerpt_short_plain_text_passes_through_unchanged():
    assert excerpt("短い紹介文です") == "短い紹介文です"


def test_excerpt_strips_unclosed_img_tag_missing_closing_bracket():
    # FASHIONSNAPのフィードで実際に観測された、閉じ`>`の無い不完全なimgタグ
    raw = '<img src="https://example.com/photo.jpg 東京で撮影しました。'
    result = excerpt(raw)
    assert "<img" not in result
    assert "src=" not in result
    assert "東京で撮影しました。" in result


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


def test_build_caps_feed_html_at_200_items(tmp_path):
    items = [
        {
            "title": f"記事{i}",
            "url": f"https://example.com/{i}",
            "source": "Hypebeast",
            "published": f"2026-08-{(i % 28) + 1:02d}T00:00:00+00:00",
            "summary": "紹介文",
            "image_url": None,
        }
        for i in range(250)
    ]

    build(tmp_path, items, [])

    feed_html = (tmp_path / "feed.html").read_text(encoding="utf-8")
    assert feed_html.count('<li>') == 200
    assert "記事0" in feed_html
    assert "記事199" in feed_html
    assert "記事200" not in feed_html
    assert "記事249" not in feed_html


def test_build_removes_stale_trend_detail_pages(tmp_path):
    trends_dir = tmp_path / "trends"
    trends_dir.mkdir(parents=True)
    # リネーム・削除済みの古い生成物を模擬する
    (trends_dir / "old-slug.html").write_text("<p>古い記事</p>", encoding="utf-8")
    (trends_dir / "index.html").write_text("stale index", encoding="utf-8")

    trends = [{"title": "現行記事", "date": "2026-08-20", "slug": "current-slug", "html": "<p>本文</p>"}]

    build(tmp_path, [], trends)

    assert not (trends_dir / "old-slug.html").exists()
    assert (trends_dir / "current-slug.html").exists()
    assert (trends_dir / "index.html").exists()


def test_build_creates_nojekyll_file(tmp_path):
    build(tmp_path, [], [])
    nojekyll = tmp_path / ".nojekyll"
    assert nojekyll.exists()
    assert nojekyll.read_text(encoding="utf-8") == ""
