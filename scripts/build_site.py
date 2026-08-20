"""data/items.json と content/trends/*.md から docs/ に静的サイトを生成する."""

from __future__ import annotations

import json
import re
import shutil
from html import unescape
from pathlib import Path

import frontmatter
import markdown as md
from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

_TAG_RE = re.compile(r"<[^>]+>")
# 一部フィード（FASHIONSNAP等）はdescriptionが閉じ`>`の無いまま途中で切れた
# `<img src="...`のような不完全なタグを含むことがある。通常の_TAG_REは`>`を
# 要求するため除去できず、タグ風の文字列がそのまま読者に見えてしまう。
# 属性値（URL等）は空白を含まない前提で、`<タグ名 属性="値`の形だけを
# 狭く対象にして除去する（本文中の通常の"<"はこの形に一致しないため誤爆しない）。
_UNCLOSED_TAG_RE = re.compile(r'<[a-zA-Z][a-zA-Z0-9]*\s+[a-zA-Z:-]+="[^"\s]*')

# WordPress系フィード（HOUYHNHNM等）のdescriptionの末尾に必ず付く
# 「The post <a>記事タイトル</a> first appeared on <a>サイト名</a>.」という定型フッターの
# 除去用。タグ除去後は記事タイトル・サイト名がリンクテキストとして地の文に残るため、
# 変動する部分（タイトル・サイト名）ではなく前後の固定の英語フレーズだけに一致させる。
# `.+?`は非貪欲マッチ: 通常このフッターは文字列の末尾に1つだけ出現するため、貪欲/非貪欲の
# 結果は変わらないが、万一本文中に同じ英語フレーズが偶然含まれる場合でも、最も手前の
# 一致から末尾までの最小範囲だけを削るようにするため非貪欲を選ぶ。
_WORDPRESS_BOILERPLATE_RE = re.compile(r"\s*The post .+? first appeared on .+?\.\s*$")


def excerpt(raw_html: str, limit: int = 200) -> str:
    """RSSのdescription（HTMLタグを含みうる）からタグを除去し、抜粋のプレーンテキストを返す.

    - HTMLタグを除去する（閉じ`>`の無い不完全なタグも狭い条件で除去する）
    - HTMLエンティティをアンエスケープする（Jinja2に渡す前のソーステキストをクリーンにするだけで、
      Jinja2の自動エスケープ自体はそのまま有効に働く）
    - WordPress系フィードの「The post ... first appeared on ....」という定型フッター
      （本文ではなくサイトのリンク案内文）を除去する
    - 空白・改行を1つのスペースに畳む
    - limit文字を超える場合は切り詰めて「…」を付与する
    """
    text = _TAG_RE.sub("", raw_html or "")
    text = _UNCLOSED_TAG_RE.sub("", text)
    text = unescape(text)
    text = " ".join(text.split())
    text = _WORDPRESS_BOILERPLATE_RE.sub("", text)
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


FEED_ITEM_LIMIT = 200


def _pick_hero(items: list[dict]) -> tuple[dict | None, list[dict]]:
    """画像のある最新アイテムをヒーローとして選ぶ。無ければ先頭にフォールバックする.

    itemsは公開日時降順にソート済みであることを前提とする。Highsnobietyのように
    フィードに画像データを一切含まないソースの記事がたまたま最新（先頭）になると、
    ヒーロー（トップページの大きな目立つ枠）が画像の無い黒い枠のまま表示され、
    壊れて見える問題があった。これを避けるため、先頭から順に見て画像URLを持つ
    最初のアイテムをヒーローとして選び、グリッド（それ以降のカード一覧）からは
    そのアイテムを除外して重複表示を防ぐ。
    どのアイテムにも画像が無い場合（空リストを含む）は、従来通りitems[0]に
    フォールバックする（空リストならヒーロー無し＝Noneを返す）。
    """
    for i, item in enumerate(items):
        if item.get("image_url"):
            return item, items[:i] + items[i + 1:]
    if items:
        return items[0], items[1:]
    return None, []


def build(output_dir: Path, items: list[dict], trends: list[dict]) -> None:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["excerpt"] = excerpt
    output_dir.mkdir(parents=True, exist_ok=True)
    trends_dir = output_dir / "trends"
    trends_dir.mkdir(parents=True, exist_ok=True)

    # リネーム・削除済みトレンド記事の古い生成物を掃除する（index.htmlは常に再生成するため対象外）
    current_slugs = {post["slug"] for post in trends}
    for existing_html in trends_dir.glob("*.html"):
        if existing_html.stem != "index" and existing_html.stem not in current_slugs:
            existing_html.unlink()

    # GitHub PagesのJekyll処理を無効化する
    (output_dir / ".nojekyll").write_text("", encoding="utf-8")

    # 静的アセット（CSS等）をdocs/配下にコピーする
    static_out = output_dir / "static"
    if STATIC_DIR.exists():
        static_out.mkdir(parents=True, exist_ok=True)
        for asset in STATIC_DIR.iterdir():
            if asset.is_file():
                shutil.copy2(asset, static_out / asset.name)

    hero, grid_items = _pick_hero(items[:10])
    (output_dir / "index.html").write_text(
        env.get_template("index.html").render(hero=hero, items=grid_items[:9], trends=trends[:3]),
        encoding="utf-8",
    )
    (output_dir / "feed.html").write_text(
        env.get_template("feed.html").render(items=items[:FEED_ITEM_LIMIT]),
        encoding="utf-8",
    )
    (trends_dir / "index.html").write_text(
        env.get_template("trends.html").render(trends=trends, asset_prefix="../"),
        encoding="utf-8",
    )
    detail_tpl = env.get_template("trend_detail.html")
    for post in trends:
        (trends_dir / f"{post['slug']}.html").write_text(
            detail_tpl.render(post=post, asset_prefix="../"), encoding="utf-8"
        )


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    items = load_items(root / "data" / "items.json")
    trends = load_trend_posts(root / "content" / "trends")
    build(root / "docs", items, trends)


if __name__ == "__main__":
    main()
