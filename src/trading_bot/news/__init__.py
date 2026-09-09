"""News/sentiment pipeline (plan 03-04, NEWS-01/NEWS-02).

A free, keyless, offline-first feed of gold/market headlines into the DuckDB
warehouse (03-03), a deterministic lexicon score per article, and a daily
sentiment snapshot offered to the AI regime check (fail-open).

The pipeline never runs automatically: ``[news] enabled`` is the opt-in and
``scripts/news.py fetch`` is the manual trigger. The trading path has no new
dependency — this package is stdlib + the (optional) analytics extra.
"""

from trading_bot.news.fetch import fetch_news
from trading_bot.news.sentiment import score_article, score_recent, write_snapshot

__all__ = ["fetch_news", "score_article", "score_recent", "write_snapshot"]
