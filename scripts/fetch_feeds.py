"""RSSフィードを取得して data/items.json を更新するスクリプト."""

from __future__ import annotations

import calendar
import json
import logging
import re
import socket
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

import feedparser

from scripts.feed_sources import FEED_SOURCES

logger = logging.getLogger(__name__)

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "items.json"


def parse_feed(source: str, source_name: str) -> list[dict]:
    """RSS/AtomのURLまたはXML文字列をパースしてアイテムのリストを返す."""
    parsed = feedparser.parse(source)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"feed parse error: {parsed.bozo_exception}")

    items = []
    for entry in parsed.entries:
        url = entry.get("link", "").strip()
        image_url = _extract_image(entry)
        items.append({
            "title": entry.get("title", "").strip(),
            "url": url if _is_safe_url(url) else "",
            "source": source_name,
            "published": _to_iso(entry.get("published_parsed")),
            "summary": entry.get("summary", "").strip(),
            "image_url": image_url if _is_safe_url(image_url) else None,
        })
    return items


def _is_safe_url(url: str | None) -> bool:
    """http/https のURLのみを安全とみなす（javascript: 等の危険なスキームを拒否する）."""
    return bool(url) and url.startswith(("http://", "https://"))


def _to_iso(struct_time) -> str:
    if struct_time is None:
        return ""
    dt = datetime.fromtimestamp(calendar.timegm(struct_time), tz=timezone.utc)
    return dt.isoformat()


# description(summary)内の最初の<img src="...">からURLを取り出す正規表現。
# 属性値はダブルクオート・シングルクオートどちらの場合にも対応する。
_IMG_SRC_RE = re.compile(r'<img[^>]*\ssrc=["\']([^"\']+)["\']', re.IGNORECASE)


def _extract_image_from_html(html_text: str | None) -> str | None:
    """HTML断片（RSSのdescription/summary）内の最初の<img src="...">からURLを抽出する.

    Fashionsnap・Hypebeastとも、画像はmedia:thumbnail/media:contentのような
    RSS拡張要素ではなく、description内に埋め込まれた<img>タグとしてのみ提供される
    （実際のRSSを取得して確認済み）。抽出したURLはXMLの二重エンティティエスケープ
    （例: Hypebeastのクエリ文字列中の`&amp;`）を`unescape()`で解いたうえで、
    `_is_safe_url()`でスキームを検証する。安全でなければNoneを返す。
    """
    match = _IMG_SRC_RE.search(html_text or "")
    if not match:
        return None
    url = unescape(match.group(1))
    return url if _is_safe_url(url) else None


def _extract_image(entry) -> str | None:
    if entry.get("media_thumbnail"):
        url = entry["media_thumbnail"][0].get("url")
        return url if _is_safe_url(url) else None
    if entry.get("media_content"):
        url = entry["media_content"][0].get("url")
        return url if _is_safe_url(url) else None
    # フォールバック: media拡張要素が無い場合、description内のimgタグから抽出する
    return _extract_image_from_html(entry.get("summary", ""))


def load_existing_items(path: Path) -> list[dict]:
    """Loads existing items from a JSON file. Returns empty list if file doesn't exist."""
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def merge_items(existing: list[dict], new_items: list[dict]) -> list[dict]:
    """Merges existing and new items, removing duplicates by URL and sorting by published date (descending).

    data/items.jsonは手編集される可能性があるため、urlやpublishedを欠いた
    不正な形式のアイテムがあってもKeyErrorで落ちないよう.get()で防御する。
    urlが無い（または空の）アイテムはどの既存URLとも一致しないものとして扱い、
    重複判定によってサイレントに除外されることはない（毎回そのまま残る）。
    publishedが無いアイテムは空文字列扱いとなり、降順ソートで末尾に来る。
    """
    seen_urls = {item.get("url") for item in existing if item.get("url")}
    merged = list(existing)
    for item in new_items:
        url = item.get("url")
        if not url or url not in seen_urls:
            merged.append(item)
            if url:
                seen_urls.add(url)
    merged.sort(key=lambda x: x.get("published", ""), reverse=True)
    return merged


def save_items(items: list[dict], path: Path) -> None:
    """Saves items to a JSON file, creating parent directories if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def fetch_source(source: dict) -> list[dict]:
    try:
        return parse_feed(source["url"], source["name"])
    except Exception as exc:  # noqa: BLE001 - 1メディアの失敗で全体を止めない
        logger.warning("failed to fetch %s: %s", source["name"], exc)
        return []


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    socket.setdefaulttimeout(30)
    existing = load_existing_items(DATA_PATH)
    new_items: list[dict] = []
    for source in FEED_SOURCES:
        new_items.extend(fetch_source(source))
    merged = merge_items(existing, new_items)
    save_items(merged, DATA_PATH)
    logger.info("saved %d items (was %d)", len(merged), len(existing))


if __name__ == "__main__":
    main()
