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
    # フォールバック1: media拡張要素が無い場合、description内のimgタグから抽出する
    # （Fashionsnap・Hypebeastはここで見つかる）
    image = _extract_image_from_html(entry.get("summary", ""))
    if image:
        return image
    # フォールバック2: descriptionに画像が無い場合、content:encoded
    # （entry.content[0].value、feedparserがlistで公開する）内のimgタグから抽出する。
    # HOUYHNHNMの実データはdescriptionに画像を一切含まず、content:encodedにのみ
    # <img>タグとして埋め込まれている（実際のフィードで確認済み）。
    content_list = entry.get("content") or [{}]
    return _extract_image_from_html(content_list[0].get("value", ""))


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


# 非ファッション記事を弾くための、簡易かつ不完全なブロックリスト。
#
# 経緯: 過去に実名入りの刑事事件報道記事が1件、Fashionsnapの一般フィード経由で
# 混入し、そのときは手動除外のみで対応した（恒久フィルタは別タスクと決定）。
# その後QAレビューで、同一の構造的原因（情報源のフィルタ不在）による混入が
# 教育イベント・法人向けサービス・アニメ関連announcementで複数件再発している
# ことが確認されたため、最低限のガードとして導入する。
#
# 明らかに非ファッションと分かるキーワードのみを対象にした簡易な文字列一致
# であり、頑健な分類器ではない。今後の精度向上（許可リスト化・分類器の導入等）
# は別タスクとする。
#
# 「アニメ」という単語自体は含めていない: 実データを確認した結果、
# 「コンバース トウキョウがまどマギと初コラボ」「グラニフが『呪術廻戦』とコラボ」
# のような正当なファッション×アニメコラボ記事の本文に
# 「アニメ『〜』とのコラボレーション」という言い回しで頻出することが分かり、
# 誤除外のリスクが高いと判断したため。英語の"Animation"はTOHO Animationの
# ようなアニメ制作会社名・アニメ発表記事にのみ出現し、確認した実データの
# コラボ記事タイトル・本文には出現しなかったため採用している。
#
# 2回目の追加（オーナー要望「服・スニーカーを軸にする」への対応、2026-08-21）:
# 犯罪報道等とは別の切り口で、オーナーから「サイトのコアコンセプトを服・スニーカーに
# 絞り、それ以外のジャンルが目立つのを避けたい」との要望があった。本番データ
# （data/items.json、当時139件）を全件確認し、既存フィルタでは弾けていない
# 非ファッション記事を新たに以下のジャンル別に追加した。いずれも実データで
# 実際に混入していたタイトルに基づく（各キーワード脇にコメントで実例を記載）。
#
# 一方で、バッグ・ジュエリー／アクセサリー・アイウェアはキーワードに追加していない。
# これらは「服」「シューズ」そのものではないが、ファッションの核となる周辺アイテム
# であり、オーナーからも「グッチの新作バッグ」のような記事はファッションニュースとして
# 残すべきと明示的な指示があったため、意図的に対象外としている。同様にストリート
# スナップ（実在の人物のコーディネート紹介）や通常のコラボ・コレクション発表も対象外。
EXCLUDE_KEYWORDS = [
    # 犯罪・司法関連の報道（芸能人等の事件報道がフィードに混入することがある）
    "逮捕",
    "書類送検",
    "送検",
    "容疑",
    "起訴",
    "有罪",
    "訴訟",
    "迷惑防止条例",
    # ファッション商品と無関係な教育・法人向けサービス等のお知らせ
    "教育イベント",
    "法人向けサービス",
    # アニメ・エンタメの発表記事（ファッション商品とのコラボは対象に含めない。上記コメント参照）
    "Animation",
    # コスメ・スキンケア・メイクアップ（服・シューズではなく美容ジャンルのため対象外とする）
    # 実例: 「弾むようなハリのある肌に　SUQQU「アクフォンス」から新スキンケアが登場」
    #       「【2026年クリスマスコフレ】キールズ」
    #       「「バイユア」から毛穴汚れを吸着して落とす新ライン誕生」
    #       「【2026年秋コスメ】シャネル：ココ マドモアゼルの精神を宿すメイクアップなどが登場」
    #       「無印良品「着るスキンケア」が一時販売停止」
    #       「【2026年秋コスメ】NARS：重ねてニュアンスを楽しむアイシャドウやリップライナーが登場」
    #       「「アンレーベル ラボ」集中美容液ヘアケアがリニューアル」
    "コスメ",
    "スキンケア",
    "メイクアップ",
    "アイシャドウ",
    "コフレ",
    "美容液",
    "ヘアケア",
    # フレグランス・香水・ボディケア（美容ジャンルの一種として上記と同様の理由で対象外とする）
    # 実例: 「より贅沢な濃度に　「ディオール」がジャスミンの香りを再解釈したフレグランス発売」
    #       「「ジバンシイ」が新フレグランスを伊勢丹新宿店で限定発売」
    #       「ディプティックから古代ギリシャの入浴文化に着想したボディケアコレクションが登場」
    "フレグランス",
    "香水",
    "ボディケア",
    # 金融（クレジットカード等）のお知らせ。服・シューズと無関係なため対象外とする
    # 実例: 「アメックスとANAの提携カードがリニューアル　旅行ニーズの変化に対応」
    "提携カード",
    # 法人のM&A・株式取得等のコーポレートニュース。商品情報ではないため対象外とする
    # 実例: 「旧マックハウスが「クラネ」運営会社の株式取得　持株比率は19％」
    "株式取得",
    "持株比率",
    # 消費者トラブル・行政注意喚起のニュース。服・シューズの商品情報ではないため対象外とする
    # 実例: 「ファッションサブスク「アールカワイイ」で解約トラブル多数　国民生活センターが注意喚起」
    "解約トラブル",
    "国民生活センター",
    # ウェルネス系ライフスタイルコミュニティのお知らせ。服・シューズと無関係なため対象外とする
    # 実例: 「東京・高輪発のウェルネスコミュニティ「TOKYO BLANK CLUB」が始動」
    "ウェルネスコミュニティ",
    # 書店ビジネス・読書文化を扱うコラム。ファッションに触れてはいるが主題は書店業界のため対象外とする
    # 実例: 「「本を売る」だけではない書店ビジネス　ファッション業界にも通じるリアル店舗の生存戦略」
    #       「三宅香帆が語る、ブッククラブの可能性とファッションが心に与える体温」
    "書店ビジネス",
    "ブッククラブ",
    # 異業種ビジネスコラム（服・飲食の複合施設だが主題はゴルフ練習場のビジネスモデル）
    # 実例: 「【異業種に学ぶ】服や飲食など複合型ゴルフ練習場「ロイヤルグリーン水戸」」
    "ゴルフ練習場",
    # 純粋な音楽ニュース。「音楽」「ライブ」単体はファッション記事の本文にも頻出するため
    # キーワードにせず、実際に混入した1件のみを狭く狙う固有のフレーズを採用する
    # 実例: 「KID FRESINOがワンマンライブ『21』のライブ・アルバムを配信リリース。」
    # （注意: 「G-DRAGON、BIGBANG‎の新曲MVでタナカダイスケの衣装を着用」のような
    # 　衣装が主題の記事は引き続き除外しない。下のテストで回帰確認している）
    "ライブ・アルバム",
    # 地方都市計画をテーマにしたコラム。ファッションと無関係なため対象外とする
    # 実例: 「人口減少と向き合った新しい地方の街づくりとは？」
    "人口減少",
]


def _is_excluded(item: dict) -> bool:
    """簡易・不完全な非ファッション記事フィルタ.

    タイトル・概要のいずれかにEXCLUDE_KEYWORDSのキーワードが含まれる場合、
    非ファッション記事とみなして除外する。頑健な分類器ではなく、明らかな
    ケースのみを弾くための最低限のガードである（EXCLUDE_KEYWORDSのコメント参照）。
    """
    text = f"{item.get('title', '')} {item.get('summary', '')}"
    return any(keyword in text for keyword in EXCLUDE_KEYWORDS)


def fetch_source(source: dict) -> list[dict]:
    try:
        items = parse_feed(source["url"], source["name"])
    except Exception as exc:  # noqa: BLE001 - 1メディアの失敗で全体を止めない
        logger.warning("failed to fetch %s: %s", source["name"], exc)
        return []

    kept = []
    for item in items:
        if _is_excluded(item):
            logger.info("excluded non-fashion item (%s): %s", source["name"], item.get("title"))
        else:
            kept.append(item)
    return kept


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
