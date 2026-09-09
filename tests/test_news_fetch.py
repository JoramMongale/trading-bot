"""Tests for the RSS news fetcher (plan 03-04, NEWS-01).

Offline: ``urllib.request.urlopen`` is monkeypatched with a fixture server,
so no network ever happens. Covers cross-feed dedupe + idempotency, per-feed
failure isolation (HTTPError / non-XML body), the stored columns incl. the
lexicon score, and [news] config validation.
"""

import urllib.error

import duckdb
import pytest

from trading_bot.config import NewsConfig, load_config
from trading_bot.news import fetch as fetch_module
from trading_bot.news.fetch import fetch_news

_RSS_A = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item>
  <title>Gold surges to record high on safe-haven demand</title>
  <link>https://feed-a.example/a1</link>
  <pubDate>Wed, 26 Aug 2026 12:00:00 GMT</pubDate>
  <description>Gold surges as rate-cut bets boost demand.</description>
</item>
<item>
  <title>Gold slumps as dollar strengthens</title>
  <link>https://feed-a.example/a2</link>
  <pubDate>Wed, 26 Aug 2026 13:00:00 GMT</pubDate>
  <description>Gold crashes on rate-hike fears.</description>
</item>
</channel></rss>
"""

_RSS_B = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item>
  <title>Gold surges to record high on safe-haven demand</title>
  <link>https://feed-a.example/a1/</link>
  <pubDate>Wed, 26 Aug 2026 14:00:00 GMT</pubDate>
  <description>Duplicate of feed A's headline.</description>
</item>
<item>
  <title>Breakout: gold breaks resistance</title>
  <link>https://feed-b.example/b1</link>
  <pubDate>Wed, 26 Aug 2026 15:00:00 GMT</pubDate>
  <description>Gold rallies on a weak dollar.</description>
</item>
</channel></rss>
"""


class _FakeResp:
    def __init__(self, body: bytes, status: int = 200):
        self.body = body
        self.status = status

    def read(self, n: int = -1):
        return self.body[:n] if n >= 0 else self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _news_config(tmp_path, feeds) -> NewsConfig:
    return NewsConfig(
        enabled=True,
        feeds=list(feeds),
        db_path=str(tmp_path / "news.duckdb"),
        snapshot_file=str(tmp_path / "news_sentiment.json"),
    )


def _patch_feeds(monkeypatch, responses: dict[str, object]):
    """Point urlopen at a fixture map url -> FakeResp / Exception."""

    def _urlopen(req, timeout=None):
        url = req.full_url
        if url not in responses:
            raise urllib.error.HTTPError(url, 404, "not found", None, None)
        resp = responses[url]
        if isinstance(resp, Exception):
            raise resp
        return resp

    monkeypatch.setattr(fetch_module.urllib.request, "urlopen", _urlopen)


def _row_count(db_path: str) -> int:
    con = duckdb.connect(db_path, read_only=True)
    try:
        return con.execute("SELECT COUNT(*) FROM raw_news_articles").fetchone()[0]
    finally:
        con.close()


def test_fetch_dedupes_across_feeds_and_is_idempotent(tmp_path, monkeypatch):
    """A link shared across two feeds lands once; re-running adds nothing."""
    cfg = _news_config(
        tmp_path,
        ["https://feed-a.example/rss", "https://feed-b.example/rss"],
    )
    _patch_feeds(
        monkeypatch,
        {
            "https://feed-a.example/rss": _FakeResp(_RSS_A.encode()),
            "https://feed-b.example/rss": _FakeResp(_RSS_B.encode()),
        },
    )

    first = fetch_news(cfg, log_path=tmp_path / "news.log")
    second = fetch_news(cfg, log_path=tmp_path / "news.log")

    # 3 unique articles (a2, b1, and a1 deduped across feeds).
    assert first == {"fetched": 4, "new": 3, "skipped": 0}
    assert second == {"fetched": 4, "new": 0, "skipped": 0}
    assert _row_count(cfg.db_path) == 3

    con = duckdb.connect(str(cfg.db_path), read_only=True)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info('raw_news_articles')").fetchall()}
        assert {"title", "link", "source_feed", "description", "published_ts",
                "score", "fetched_at"} <= cols
        # The lexicon score was populated at ingest (sentiment importable).
        scores = con.execute("SELECT count(*) FROM raw_news_articles WHERE score IS NOT NULL").fetchone()[0]
        assert scores == 3
    finally:
        con.close()


def test_feed_http_error_is_isolated_to_that_feed(tmp_path, monkeypatch):
    """A dead feed logs news_fetch_failed and the live feed still ingests."""
    cfg = _news_config(
        tmp_path,
        ["https://dead.example/rss", "https://alive.example/rss"],
    )
    _patch_feeds(
        monkeypatch,
        {
            "https://dead.example/rss": urllib.error.HTTPError(
                "https://dead.example/rss", 503, "gone", None, None
            ),
            "https://alive.example/rss": _FakeResp(_RSS_B.encode()),
        },
    )

    result = fetch_news(cfg, log_path=tmp_path / "news.log")

    assert result["skipped"] == 1
    assert _row_count(cfg.db_path) == 2  # b1 + a1(dup) — feed B's two items

    log_text = (tmp_path / "news.log").read_text(encoding="utf-8")
    assert "event=news_fetch_failed " in log_text
    assert "https://dead.example/rss" in log_text


def test_non_xml_body_is_skipped_with_notice(tmp_path, monkeypatch):
    cfg = _news_config(tmp_path, ["https://junk.example/rss"])
    _patch_feeds(
        monkeypatch,
        {"https://junk.example/rss": _FakeResp(b"this is not xml at all <<<")},
    )

    result = fetch_news(cfg, log_path=tmp_path / "news.log")

    assert result["skipped"] == 1
    assert result["fetched"] == 0
    log_text = (tmp_path / "news.log").read_text(encoding="utf-8")
    assert "event=news_fetch_failed " in log_text


def _write_config(tmp_path, news_table: str) -> str:
    p = tmp_path / "config.toml"
    p.write_text(
        f"""[data]
source = "histdata"
raw_dir = "data/raw"
symbol = "XAUUSD"
timeframe = "M5"
start = "2024-01-01"
end = "2026-07-31"

[strategy]
fractal_left = 2
fractal_right = 2
sr_lookback = 60
rr_multiple = 1.0
sl_buffer = 0.01

[trading]
lot = 0.01
contract_size = 100
spread_assumption = 0.0

[backtest]
output_dir = "output"

[live]
enabled = false
mode = "dry-run"
magic_number = 77100
deviation = 20
poll_interval = 5.0
comment = "x"

{news_table}
""",
        encoding="utf-8",
    )
    return str(p)


def test_news_config_validation_raises_naming_bad_key(tmp_path):
    """[news] feeds must be a non-empty list of http(s) URLs (NEWS-01)."""
    for bad in ('feeds = ["ftp://not-http.example/rss"]', "feeds = []"):
        cfg = _write_config(tmp_path, f"[news]\nenabled = true\n{bad}\n")
        with pytest.raises(ValueError, match="news.feeds"):
            load_config(cfg)


def test_news_config_loads_valid(tmp_path):
    cfg = _write_config(
        tmp_path,
        '[news]\nenabled = true\n'
        'feeds = ["https://kitco.example/rss"]\nmax_items = 25\n',
    )
    loaded = load_config(cfg)
    assert loaded.news.enabled is True
    assert loaded.news.feeds == ["https://kitco.example/rss"]
    assert loaded.news.max_items == 25


def test_missing_news_table_defaults_to_off(tmp_path):
    """Legacy configs without [news] load with the pipeline off (NEWS-01)."""
    cfg = _write_config(tmp_path, "")
    loaded = load_config(cfg)
    assert loaded.news.enabled is False
    assert isinstance(loaded.news, NewsConfig)
