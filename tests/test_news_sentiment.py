"""Tests for the lexicon sentiment scorer + snapshot writer (plan 03-04, NEWS-02).

score_article is a pure deterministic function — no DB, no network. The
snapshot test seeds a tiny raw_news_articles table and asserts the atomic
write produces the expected JSON.
"""

import json

import duckdb
import pytest

from trading_bot.config import NewsConfig
from trading_bot.news.sentiment import LEXICON, score_article, write_snapshot

_BULLISH = "Gold surges to a record high on safe-haven demand and rate-cut bets."
_BEARISH = "Gold slumps and crashes as rate-hike fears spark a sell-off."
_NEUTRAL = "Gold traded inside a narrow range today."


def test_score_article_bullish_positive():
    assert score_article(_BULLISH) > 0


def test_score_article_bearish_negative():
    assert score_article(_BEARISH) < 0


def test_score_article_neutral_is_zero():
    assert score_article(_NEUTRAL) == 0.0


def test_score_article_empty_and_mixed():
    assert score_article("") == 0.0
    mixed = "Gold surges but the dollar also strengthens"
    pos = _count(mixed, LEXICON["bullish"])
    neg = _count(mixed, LEXICON["bearish"])
    assert score_article(mixed) == (pos - neg) / max(1, pos + neg)


def test_custom_lexicon_override():
    lexicons = {
        "bullish": frozenset({"rocket"}),
        "bearish": frozenset({"sink"}),
    }
    assert score_article("rocket rocket", lexicons) > 0
    assert score_article("sink", lexicons) < 0
    # The default lexicon no longer applies.
    assert score_article("surge", lexicons) == 0.0


def _count(text: str, terms) -> int:
    lower = text.lower()
    return sum(lower.count(t) for t in terms)


def _seed_articles(conn) -> None:
    conn.execute("""
        CREATE TABLE raw_news_articles (
            published_ts TIMESTAMP, title VARCHAR, link VARCHAR,
            source_feed VARCHAR, description VARCHAR, score DOUBLE,
            fetched_at TIMESTAMP, PRIMARY KEY (link)
        )
    """)
    conn.execute(
        """
        INSERT INTO raw_news_articles VALUES
        ('2026-08-26 12:00:00', 'Gold surges to record high', 'https://x/a', 'feed',
         'Gold surges on safe-haven demand', 0.8, '2026-08-26T12:05:00Z'),
        ('2026-08-26 13:00:00', 'Gold slumps on rate-hike fears', 'https://x/b', 'feed',
         'Gold crashes on a stronger dollar', -0.75, '2026-08-26T13:05:00Z'),
        ('2026-08-26 14:00:00', 'Gold traded in a narrow range', 'https://x/c', 'feed',
         'Ranging session', 0.0, '2026-08-26T14:05:00Z')
        """
    )


def test_write_snapshot_writes_atomic_json(tmp_path):
    db = tmp_path / "news.duckdb"
    con = duckdb.connect(str(db))
    _seed_articles(con)
    con.close()

    cfg = NewsConfig(
        enabled=True,
        db_path=str(db),
        snapshot_file=str(tmp_path / "news_sentiment.json"),
    )
    payload = write_snapshot(cfg)

    assert payload is not None
    assert payload["articles"] == 3
    assert payload["score"] != 0  # bullish + bearish mix nets somewhere near 0
    assert len(payload["top_titles"]) == 3

    on_disk = json.loads((tmp_path / "news_sentiment.json").read_text(encoding="utf-8"))
    assert on_disk == payload
    # No stray temp files left behind by the atomic write.
    leftovers = [p.name for p in tmp_path.glob(".news_sentiment.*.tmp")]
    assert leftovers == []


def test_write_snapshot_returns_none_with_no_articles(tmp_path):
    db = tmp_path / "empty.duckdb"
    con = duckdb.connect(str(db))
    con.execute("""
        CREATE TABLE raw_news_articles (
            published_ts TIMESTAMP, title VARCHAR, link VARCHAR,
            source_feed VARCHAR, description VARCHAR, score DOUBLE,
            fetched_at TIMESTAMP, PRIMARY KEY (link)
        )
    """)
    con.close()

    cfg = NewsConfig(
        enabled=True,
        db_path=str(db),
        snapshot_file=str(tmp_path / "news_sentiment.json"),
    )
    assert write_snapshot(cfg) is None
    assert not (tmp_path / "news_sentiment.json").exists()
