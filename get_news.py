import re
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import requests

FEED_URL = "https://www.bleepingcomputer.com/feed/"
MAX_ITEMS = 40

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
}

_TAGS_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean_text(value: str) -> str:
    text = _TAGS_RE.sub(" ", value)
    text = text.replace("[...]", "").strip()
    return _WS_RE.sub(" ", text)


def _parse_item(item) -> dict | None:
    def txt(path: str, default: str = "") -> str:
        node = item.find(path)
        return (node.text or default) if node is not None else default

    title = _clean_text(txt("title"))
    link = txt("link").strip()
    if not title or not link:
        return None

    published = ""
    raw_date = txt("pubDate")
    if raw_date:
        try:
            published = parsedate_to_datetime(raw_date).isoformat()
        except (TypeError, ValueError):
            published = ""

    description = _clean_text(txt("description"))
    category_nodes = item.findall("category")
    categories = [c.text.strip() for c in category_nodes if c.text and c.text.strip()]

    return {
        "title": title,
        "link": link,
        "published": published,
        "author": _clean_text(txt("{http://purl.org/dc/elements/1.1/}creator")),
        "category": categories[0] if categories else "",
        "summary": description[:300],
    }


def fetch_news() -> dict:
    response = requests.get(FEED_URL, headers=HEADERS, timeout=15)
    response.raise_for_status()

    root = ElementTree.fromstring(response.content)
    channel = root.find("channel")
    if channel is None:
        raise ValueError("feed has no <channel>")

    items = []
    for item in channel.findall("item"):
        parsed = _parse_item(item)
        if parsed:
            items.append(parsed)
        if len(items) >= MAX_ITEMS:
            break

    if not items:
        raise ValueError("feed contained no usable items")

    return {"items": items}
