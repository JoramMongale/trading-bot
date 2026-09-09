"""Deterministic lexicon sentiment scorer (plan 03-04, NEWS-02).

No model calls, no API — a fixed lexicon of bullish/bearish gold & market
terms is applied to each article's title+description, producing a score in
[-1.0, 1.0]. The score is computed at ingest time and stored on
``raw_news_articles``; a daily snapshot is offered to the AI regime check.

The lexicon is a module-level dict of frozensets (``bullish``/``bearish``),
overridable via the ``lexicons`` parameter so tests can inject tiny custom
vocabularies.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pandas as pd

LEXICON = {
    "bullish": frozenset(
        {
            "surge", "rally", "record high", "record-high", "breakout", "break out",
            "safe haven", "haven demand", "rate cut", "rate-cut", "cuts rates",
            "dollar weak", "weaker dollar", "weak dollar", "buy", "buys", "buying",
            "gains", "gain", "higher", "up", "jump", "jumps", "soar", "soars",
            "strong", "strength", "bullish", "bullion", "lift", "lifts", "rising",
            "outperform", "outperformance", "tightening supply", "physical demand",
            "central bank buying", "inflation hedge", "crisis", "uncertainty",
            "geopolitical", "trade war", "recession", "stimulus",
        }
    ),
    "bearish": frozenset(
        {
            "slump", "plunge", "plunges", "crash", "crashes", "fear", "fears",
            "sell-off", "selloff", "sell off", "rate hike", "rate-hike", "hikes rates",
            "dollar strong", "stronger dollar", "strong dollar", "sell", "sells",
            "selling", "losses", "loss", "lower", "down", "drop", "drops", "falls",
            "fall", "weak", "weakness", "bearish", "decline", "declines", "dips",
            "pressure", "pressured", "correction", "worst", "retreat", "retreats",
            "tumble", "tumbles", "losing", "retreating", "glut", "overhang",
            "yields rise", "higher yields", "dollar rally", "risk-on",
        }
    ),
}


def score_article(text: str, lexicons: dict | None = None) -> float:
    """Deterministic lexicon score of ``text`` in [-1.0, 1.0].

    Score = (pos - neg) / max(1, pos + neg): 0.0 for no/no matching terms,
    +1.0 all-bullish, -1.0 all-bearish. The count is of TERM occurrences, so
    a headline mentioning "surge" twice leans further positive.
    """
    if not text:
        return 0.0
    lexicons = lexicons or LEXICON
    lower = text.lower()
    pos = sum(lower.count(term) for term in lexicons["bullish"])
    neg = sum(lower.count(term) for term in lexicons["bearish"])
    return (pos - neg) / max(1, pos + neg)


def score_recent(cfg, conn, days: int = 3) -> dict | None:
    """Aggregate the last ``days`` of raw_news_articles.

    ``cfg`` is the ``[news]`` NewsConfig (used only for context; the query
    runs on ``conn``). Returns ``{"date", "score", "articles",
    "top_titles", "bottom_titles"}`` or None when there are no scored
    articles in the window.
    """
    latest = conn.execute(
        "SELECT max(fetched_at) FROM raw_news_articles"
    ).fetchone()[0]
    if latest is None:
        return None
    cutoff = latest - pd.Timedelta(days=days)
    rows = conn.execute(
        """
        SELECT title, score
        FROM raw_news_articles
        WHERE score IS NOT NULL
          AND fetched_at >= ?
        ORDER BY abs(score) DESC
        """,
        [cutoff],
    ).fetchall()
    if not rows:
        return None
    scores = [float(s) for _, s in rows]
    top = [t for t, _ in rows[:5]]
    bottom = [t for t, _ in rows[-5:]]
    return {
        "date": str(conn.execute("SELECT max(published_ts) FROM raw_news_articles").fetchone()[0] or ""),
        "score": round(sum(scores) / len(scores), 4),
        "articles": len(scores),
        "top_titles": top,
        "bottom_titles": bottom,
    }


def write_snapshot(cfg, conn=None) -> dict | None:
    """Compute the recent sentiment and atomically write it to snapshot_file.

    ``cfg`` is the ``[news]`` NewsConfig. Writes
    ``{"date", "score", "articles", "top_titles", ...}`` to
    ``cfg.snapshot_file`` via temp-file + ``os.replace`` (atomic — a reader
    never sees a half-written file). Returns the dict, or None when there is
    nothing to snapshot.
    """
    if conn is None:
        try:
            import duckdb
        except ImportError as exc:
            raise ImportError(
                "news sentiment requires the 'analytics' extra: "
                '.venv\\Scripts\\pip install -e ".[analytics]"'
            ) from exc
        conn = duckdb.connect(str(cfg.db_path), read_only=True)
        close_after = True
    else:
        close_after = False

    try:
        payload = score_recent(cfg, conn)
        if payload is None:
            return None
        payload["score"] = float(payload["score"])
        payload["articles"] = int(payload["articles"])
        payload["top_titles"] = [str(t) for t in payload["top_titles"]]
        payload["bottom_titles"] = [str(t) for t in payload["bottom_titles"]]
    finally:
        if close_after:
            conn.close()

    target = Path(cfg.snapshot_file)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".news_sentiment.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return payload
