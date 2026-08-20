"""data/items.json と content/trends/*.md から docs/ に静的サイトを生成する."""

from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path

import frontmatter
import markdown as md
from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

_TAG_RE = re.compile(r"<[^>]+>")


def excerpt(raw_html: str, limit: int = 200) -> str:
    """RSSのdescription（HTMLタグを含みうる）からタグを除去し、抜粋のプレーンテキストを返す.

    - HTMLタグを除去する
    - HTMLエンティティをアンエスケープする（Jinja2に渡す前のソーステキストをクリーンにするだけで、
      Jinja2の自動エスケープ自体はそのまま有効に働く）
    - 空白・改行を1つのスペースに畳む
    - limit文字を超える場合は切り詰めて「…」を付与する
    """
    text = _TAG_RE.sub("", raw_html or "")
    text = unescape(text)
    text = " ".join(text.split())
    if len(text) > limit:
        return text[:limit] + "…"
    return text


def load_items(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_trend_posts(content_dir: Path) -> list[dict]:
    if not content_dir.exists():
        return []
    posts = []
    for p in sorted(content_dir.glob("*.md")):
        post = frontmatter.load(p)
        posts.append({
            "title": post.get("title", p.stem),
            "date": str(post.get("date", "")),
            "slug": p.stem,
            "html": md.markdown(post.content),
        })
    posts.sort(key=lambda x: str(x["date"]), reverse=True)
    return posts


def build(output_dir: Path, items: list[dict], trends: list[dict]) -> None:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["excerpt"] = excerpt
    output_dir.mkdir(parents=True, exist_ok=True)
    trends_dir = output_dir / "trends"
    trends_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "index.html").write_text(
        env.get_template("index.html").render(items=items[:10], trends=trends[:3]),
        encoding="utf-8",
    )
    (output_dir / "feed.html").write_text(
        env.get_template("feed.html").render(items=items),
        encoding="utf-8",
    )
    (trends_dir / "index.html").write_text(
        env.get_template("trends.html").render(trends=trends),
        encoding="utf-8",
    )
    detail_tpl = env.get_template("trend_detail.html")
    for post in trends:
        (trends_dir / f"{post['slug']}.html").write_text(
            detail_tpl.render(post=post), encoding="utf-8"
        )


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    items = load_items(root / "data" / "items.json")
    trends = load_trend_posts(root / "content" / "trends")
    build(root / "docs", items, trends)


if __name__ == "__main__":
    main()
