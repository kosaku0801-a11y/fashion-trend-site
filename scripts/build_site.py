"""data/items.json と content/trends/*.md から docs/ に静的サイトを生成する."""

from __future__ import annotations

import json
from pathlib import Path

import frontmatter
import markdown as md


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
            "date": post.get("date", ""),
            "slug": p.stem,
            "html": md.markdown(post.content),
        })
    posts.sort(key=lambda x: str(x["date"]), reverse=True)
    return posts
