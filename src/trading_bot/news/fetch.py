"""RSS news fetcher (plan 03-04) — stdlib only: ``urllib`` + ``xml.etree``.

Fetches free, keyless gold/market RSS feeds, dedupes by normalized link, and
stores articles in the DuckDB warehouse's ``raw_news_articles`` table (the
03-03 database). ``MERGE INTO`` on ``link`` makes re-fetches idempotent.

Trust boundary (threat T-04-04-01): the feeds are remote, untrusted XML.
Defenses: ``xml.etree.ElementTree`` does not resolve external entities; we
reject non-200 responses and bodies > 2 MB before parsing; we never fetch
URLs found inside a feed. Every failure is per-feed: log ``news_fetch_failed``
via the SAFE-02 helper and continue — the pipeline is a convenience, never
load-bearing.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import pandas as pd

from trading_bot.config import NewsConfig
from trading_bot.logging_utils import get_logger, log_decision

# Cap on a single feed response — hostile/runaway bodies are rejected before
# parsing (T-04-04-01). Real RSS feeds are tens of KB.
MAX_BODY_BYTES = 2 * 1024 * 1024

_DDL = """
    CREATE TABLE IF NOT EXISTS raw_news_articles (
        published_ts TIMESTAMP,
        title VARCHAR,
        link VARCHAR,
        source_feed VARCHAR,
        description VARCHAR,
        score DOUBLE,
        fetched_at TIMESTAMP,
        PRIMARY KEY (link)
    )
"""


def _http_get(url: str, user_agent: str, timeout: float) -> bytes:
    """GET a feed with the configured UA + timeout; raises on failure.

    Rejects non-200 statuses and bodies over ``MAX_BODY_BYTES`` before they
    reach the parser (T-04-04-01).
    """
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - https(s) feeds only, validated in config
        if resp.status != 200:
            raise urllib.error.HTTPError(url, resp.status, f"status {resp.status}", None, None)
        body = resp.read(MAX_BODY_BYTES + 1)
        if len(body) > MAX_BODY_BYTES:
            raise urllib.error.URLError(f"response too large ({len(body)} bytes)")
        return body


def _parse_rss(data: bytes) -> list[dict]:
    """Extract article dicts (title/link/pubDate/description) from RSS XML."""
    root = ET.fromstring(data)  # ElementTree does not resolve external entities
    items = []
    for item in root.iter("item"):
        def _text(tag: str) -> str:
            node = item.find(tag)
            return (node.text or "").strip() if node is not None and node.text else ""

        title = _text("title")
        link = _text("link")
        if not title or not link:
            continue  # an article without title or link is useless
        published = _text("pubDate")
        try:
            pub_ts = parsedate_to_datetime(published) if published else None
        except (TypeError, ValueError):
            pub_ts = None
        items.append(
            {
                "title": title,
                "link": link,
                "pubDate": pub_ts.isoformat(timespec="seconds") if pub_ts else None,
                "description": _text("description"),
            }
        )
    return items


def _normalize_link(link: str) -> str:
    """Case-insensitive, trailing-slash-stripped canonical link (dedupe key)."""
    return link.strip().lower().rstrip("/")


def _score_article_if_available(article: dict) -> float | None:
    """Score the article when the sentiment module is importable, else None.

    The base bot must never depend on news internals: the score is a
    convenience column, computed best-effort. None keeps the column NULL.
    """
    try:
        from trading_bot.news.sentiment import score_article
    except ImportError:
        return None
    text = " ".join([article.get("title", ""), article.get("description", "")])
    return round(float(score_article(text)), 4)


def _open_db(db_path: str | Path):
    """Connect to the warehouse and ensure raw_news_articles exists."""
    try:
        import duckdb
    except ImportError as exc:
        raise ImportError(
            "news fetch requires the 'analytics' extra: "
            '.venv\\Scripts\\pip install -e ".[analytics]"'
        ) from exc
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    con.execute(_DDL)
    return con


def fetch_news(cfg: NewsConfig, db_path: str | Path | None = None,
               log_path: str | Path = "output/news.log") -> dict[str, int]:
    """Fetch + store articles from every configured feed into DuckDB.

    Returns ``{"fetched": n, "new": m, "skipped": k}`` — total articles
    fetched across feeds, how many were actually new to the table (post
    dedupe), and feeds skipped due to errors. Re-running is idempotent
    (``MERGE`` on link). Network failures never raise: they log
    ``news_fetch_failed`` and move on.
    """
    logger = get_logger("news", str(log_path))
    conn = _open_db(db_path or cfg.db_path)

    # Cross-feed dedupe on the normalized link, newest fetch wins.
    seen: dict[str, dict] = {}
    skipped = 0
    fetched = 0
    try:
        for feed in cfg.feeds:
            try:
                body = _http_get(feed, cfg.user_agent, cfg.fetch_timeout)
                articles = _parse_rss(body)
            except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
                skipped += 1
                log_decision(logger, "news_fetch_failed", feed=feed, error=str(exc))
                continue
            except ET.ParseError as exc:
                skipped += 1
                log_decision(logger, "news_fetch_failed", feed=feed,
                             error=f"parse error: {exc}")
                continue

            for article in articles[: cfg.max_items]:
                fetched += 1
                key = _normalize_link(article["link"])
                seen[key] = {
                    "published_ts": article["pubDate"],
                    "title": article["title"],
                    "link": article["link"],
                    "source_feed": feed,
                    "description": article["description"],
                    "score": _score_article_if_available(article),
                    "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
            log_decision(logger, "news_fetched", feed=feed, articles=len(articles[: cfg.max_items]))

        if not seen:
            return {"fetched": fetched, "new": 0, "skipped": skipped}

        # How many of the fetched links are genuinely new to the table (the
        # rest are updates to already-known articles — dedupe, not novelty).
        before = {
            row[0]
            for row in conn.execute(
                "SELECT lower(rtrim(link, '/')) FROM raw_news_articles"
            ).fetchall()
        }
        new_count = len({_normalize_link(a["link"]) for a in seen.values()} - before)

        df = pd.DataFrame(list(seen.values()))
        cols = ["published_ts", "title", "link", "source_feed", "description",
                "score", "fetched_at"]
        df = df[cols]
        conn.register("__news_src", df)
        try:
            conn.execute(
                "MERGE INTO raw_news_articles AS t USING __news_src AS s "
                "ON t.link = s.link "
                "WHEN MATCHED THEN UPDATE SET "
                "published_ts = s.published_ts, title = s.title, "
                "source_feed = s.source_feed, description = s.description, "
                "score = s.score, fetched_at = s.fetched_at "
                "WHEN NOT MATCHED THEN INSERT (published_ts, title, link, "
                "source_feed, description, score, fetched_at) VALUES ("
                "s.published_ts, s.title, s.link, s.source_feed, s.description, "
                "s.score, s.fetched_at)"
            )
        finally:
            conn.unregister("__news_src")
    finally:
        conn.close()

    return {"fetched": fetched, "new": new_count, "skipped": skipped}
