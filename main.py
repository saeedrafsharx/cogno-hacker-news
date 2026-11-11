import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

import anyio
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from get_news import fetch_news

REFRESH_INTERVAL = timedelta(hours=12)
RETRY_INTERVAL = timedelta(minutes=5)
NO_DATA_INTERVAL = timedelta(seconds=30)
CACHE_FILE = Path(os.environ.get("CACHE_FILE", "news_cache.json"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("nitel")

cache: dict = {"updated_at": None, "items": []}


def _load_cache() -> None:
    try:
        raw = json.loads(CACHE_FILE.read_text())
        if raw.get("items"):
            cache.update(updated_at=raw["updated_at"], items=raw["items"])
            logger.info("loaded %d cached items as fallback", len(cache["items"]))
    except (OSError, ValueError, KeyError, TypeError):
        pass


def _save_cache() -> None:
    try:
        CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False))
    except OSError as exc:
        logger.warning("could not persist cache: %s", exc)


def _refresh_sync() -> int:
    data = fetch_news()
    cache.update(
        updated_at=datetime.now(timezone.utc).isoformat(),
        items=data["items"],
    )
    _save_cache()
    return len(cache["items"])


async def _refresh() -> bool:
    try:
        count = await anyio.to_thread.run_sync(_refresh_sync)
        logger.info("news refreshed: %d items", count)
        return True
    except Exception as exc:
        logger.error("news refresh failed: %s", exc)
        return False


async def _scheduler(initial_ok: bool) -> None:
    if initial_ok:
        await asyncio.sleep(REFRESH_INTERVAL.total_seconds())
    while True:
        if await _refresh():
            await asyncio.sleep(REFRESH_INTERVAL.total_seconds())
        else:
            wait = NO_DATA_INTERVAL if not cache["items"] else RETRY_INTERVAL
            await asyncio.sleep(wait.total_seconds())


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_cache()
    initial_ok = await _refresh()
    if not initial_ok and cache["items"]:
        logger.warning("startup fetch failed; serving stale cache")
    task = asyncio.create_task(_scheduler(initial_ok))
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="nitel", lifespan=lifespan)


@app.get("/health")
def health_check():
    return {"health": "ok"}


@app.get("/api/news")
def news():
    if not cache["items"]:
        return JSONResponse({"error": "no news yet"}, status_code=503)
    return cache


TEMPLATE = Path(__file__).resolve().parent / "static" / "index.html"


def _ago(iso: str) -> str:
    try:
        seconds = (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds()
    except (ValueError, TypeError):
        return ""
    if seconds < 0:
        return "just now"
    for span, label in ((31536000, "y"), (2592000, "mo"), (604800, "w"), (86400, "d"), (3600, "h"), (60, "m")):
        if seconds >= span:
            return f"{int(seconds // span)}{label} ago"
    return "just now"


def _article_html(item: dict) -> str:
    parts = ['<article><div class="meta">']
    ago = _ago(item.get("published", ""))
    if ago:
        parts.append(f"<span>{escape(ago)}</span>")
    if item.get("author"):
        parts.append(f"<span>{escape(item['author'])}</span>")
    if item.get("category"):
        parts.append(f'<span class="cat">{escape(item["category"])}</span>')
    parts.append("</div>")
    parts.append(
        f'<h2><a href="{escape(item["link"])}" target="_blank" rel="noopener noreferrer">'
        f'{escape(item["title"])}</a></h2>'
    )
    if item.get("summary"):
        parts.append(f"<p>{escape(item['summary'])}</p>")
    parts.append("</article>")
    return "".join(parts)


@app.get("/")
def index():
    html = TEMPLATE.read_text(encoding="utf-8")
    if cache["items"]:
        html = html.replace('"__NEWS__"', json.dumps(
            {"updated_at": cache["updated_at"], "items": cache["items"]},
            ensure_ascii=False,
        ).replace("</", "<\\/"))
        html = html.replace("<!--NEWS-->", "".join(_article_html(i) for i in cache["items"]))
    else:
        html = html.replace('"__NEWS__"', "null")
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})
