"""RSSフィードを取得して data/items.json を更新するスクリプト."""

from __future__ import annotations

import calendar
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import feedparser

logger = logging.getLogger(__name__)

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "items.json"


def parse_feed(source: str, source_name: str) -> list[dict]:
    """RSS/AtomのURLまたはXML文字列をパースしてアイテムのリストを返す."""
    parsed = feedparser.parse(source)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"feed parse error: {parsed.bozo_exception}")

    items = []
    for entry in parsed.entries:
        items.append({
            "title": entry.get("title", "").strip(),
            "url": entry.get("link", "").strip(),
            "source": source_name,
            "published": _to_iso(entry.get("published_parsed")),
            "summary": entry.get("summary", "").strip(),
            "image_url": _extract_image(entry),
        })
    return items


def _to_iso(struct_time) -> str:
    if struct_time is None:
        return ""
    dt = datetime.fromtimestamp(calendar.timegm(struct_time), tz=timezone.utc)
    return dt.isoformat()


def _extract_image(entry) -> str | None:
    if entry.get("media_thumbnail"):
        return entry["media_thumbnail"][0].get("url")
    if entry.get("media_content"):
        return entry["media_content"][0].get("url")
    return None


def load_existing_items(path: Path) -> list[dict]:
    """Loads existing items from a JSON file. Returns empty list if file doesn't exist."""
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def merge_items(existing: list[dict], new_items: list[dict]) -> list[dict]:
    """Merges existing and new items, removing duplicates by URL and sorting by published date (descending)."""
    seen_urls = {item["url"] for item in existing}
    merged = list(existing)
    for item in new_items:
        if item["url"] and item["url"] not in seen_urls:
            merged.append(item)
            seen_urls.add(item["url"])
    merged.sort(key=lambda x: x["published"], reverse=True)
    return merged


def save_items(items: list[dict], path: Path) -> None:
    """Saves items to a JSON file, creating parent directories if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
