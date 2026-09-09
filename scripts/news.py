"""News/sentiment pipeline CLI (plan 03-04).

    python scripts/news.py fetch [--config PATH]       # RSS -> raw_news_articles
    python scripts/news.py sentiment [--config PATH]   # score -> output/news_sentiment.json

Free and keyless; network failures degrade to log-and-continue (fetch) and
the snapshot is never required by the trading path. The AI regime check reads
the snapshot fail-open. Requires the ``analytics`` extra (duckdb); without it
exits 2 with an install hint.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python scripts/news.py")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("fetch", "sentiment"):
        cmd = sub.add_parser(name, help=f"{name} the news pipeline")
        cmd.add_argument(
            "--config", default="config/config-ai-live.toml",
            help="path to the TOML config (default: config/config-ai-live.toml)",
        )

    args = parser.parse_args(argv)

    from trading_bot.config import load_config

    try:
        cfg = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        if args.command == "fetch":
            from trading_bot.news.fetch import fetch_news

            result = fetch_news(cfg.news)
            print(f"articles: {result['fetched']} (new: {result['new']}, "
                  f"feeds skipped: {result['skipped']})")
        elif args.command == "sentiment":
            from trading_bot.news.sentiment import write_snapshot

            payload = write_snapshot(cfg.news)
            if payload is None:
                print("no articles to score — snapshot not written")
            else:
                print(
                    f"sentiment: {payload['score']:+.3f} over "
                    f"{payload['articles']} articles (as of {payload['date']}) "
                    f"-> {cfg.news.snapshot_file}"
                )
    except ImportError as exc:
        if "duckdb" in str(exc) or "analytics" in str(exc):
            print(
                "news pipeline requires the 'analytics' extra: "
                '.venv\\Scripts\\pip install -e ".[analytics]"',
                file=sys.stderr,
            )
            return 2
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
