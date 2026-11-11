# nitel

Lightweight security-news page: scrapes the [BleepingComputer](https://www.bleepingcomputer.com/feed/) RSS feed, serves a static dark-terminal page, and re-syncs every 12 hours.

## Run locally

```bash
source .venv/bin/activate
uvicorn main:app --reload
```

Then open http://127.0.0.1:8000

## Run with Docker

```bash
docker build -t nitel .
docker run -p 8000:8000 nitel
```

Set a different port with `-e PORT=9000`. To keep the cache across container restarts, mount a volume for the cache file:

```bash
docker run -p 8000:8000 -v nitel-data:/app/data -e CACHE_FILE=/app/data/news_cache.json nitel
```

## Endpoints

| Path        | Description                          |
| ----------- | ------------------------------------ |
| `/`         | static news page (dark terminal UI)  |
| `/api/news` | cached feed as JSON                  |
| `/health`   | liveness check                       |

## How updates work

- On startup: loads `news_cache.json` as a fallback, then fetches the feed immediately (fresh data wins; stale cache is served if the fetch fails).
- Background task re-fetches every 12 h. On failure it retries every 5 min — or every 30 s until the first successful fetch.
- `/api/news` never 503s once any data has been fetched — stale news is served until a fresh sync succeeds.
- The browser page retries every 30 s until data arrives, then silently re-pulls every 5 min.

## Deploying on Chabokan

Build and push the image (or use the Dockerfile directly in a container instance), map the container port (`8000` by default) to your public port, and point your domain at it. No database, no volumes required — the cache file is optional and rebuilt automatically.
