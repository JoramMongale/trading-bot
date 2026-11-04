"""Fetch daily US equity bars for the Sneaky Pivot premise test.

Universe is chosen to match what the video's author actually trades, not a
generic large-cap list. In the live section he trades AAOI (a small-cap optical
name) and GGLL (a 2x leveraged Google ETF), and he describes the ideal
instrument as "rangy" -- wide daily range relative to price. A test on SPY and
MSFT would be a different question, so the universe is split into three
deliberate buckets and reported separately.
"""

from __future__ import annotations

import sys
import time

import pandas as pd
import yfinance as yf

UNIVERSE = {
    # 2x leveraged single-stock ETFs -- GGLL is his own live example. These are
    # the most "rangy" instruments retail can trade.
    "leveraged": [
        "GGLL", "TSLL", "NVDL", "AAPU", "MSFU", "AMZU", "METU", "CONL",
        "TSLQ", "NVDQ", "MSTU", "PLTU", "AMDL", "SMCX", "TSMX", "AVL",
    ],
    # High-volatility movers, the AAOI profile: small/mid-cap, headline-driven,
    # wide daily ranges.
    "volatile": [
        "AAOI", "SOFI", "MARA", "RIOT", "COIN", "SMCI", "PLTR", "LUNR",
        "IONQ", "RGTI", "BBAI", "SOUN", "ACHR", "JOBY", "CLSK", "HUT",
        "AFRM", "UPST", "HOOD", "RKLB", "NNE", "OKLO", "TEM", "CRWV",
    ],
    # Liquid controls -- if the effect is real it should at least be visible
    # here too, and DIA is the ETF twin of the YM Dow futures he demos on.
    "liquid": [
        "SPY", "QQQ", "DIA", "IWM", "AAPL", "MSFT", "NVDA", "TSLA",
        "AMD", "META", "AMZN", "GOOGL", "NFLX", "JPM", "XOM", "BA",
    ],
}

START, END = "2023-08-01", "2026-08-28"


def main() -> int:
    frames = []
    for bucket, tickers in UNIVERSE.items():
        for i in range(0, len(tickers), 8):          # small chunks: Yahoo 429s
            chunk = tickers[i:i + 8]
            for attempt in range(4):
                try:
                    d = yf.download(chunk, start=START, end=END, interval="1d",
                                    auto_adjust=False, progress=False,
                                    threads=False, group_by="ticker")
                    break
                except Exception as e:               # transient throttling
                    print(f"  retry {chunk}: {e}", file=sys.stderr)
                    time.sleep(5 * (attempt + 1))
            else:
                continue
            for t in chunk:
                try:
                    sub = d[t] if len(chunk) > 1 else d
                except KeyError:
                    continue
                sub = sub.dropna(subset=["High", "Low", "Close"])
                if len(sub) < 200:
                    print(f"  skip {t}: only {len(sub)} rows", file=sys.stderr)
                    continue
                sub = sub.reset_index()[["Date", "Open", "High", "Low", "Close", "Volume"]]
                sub.columns = ["date", "open", "high", "low", "close", "volume"]
                sub["ticker"], sub["bucket"] = t, bucket
                frames.append(sub)
            print(f"{bucket}: {chunk} ok", flush=True)
            time.sleep(1.5)

    out = pd.concat(frames, ignore_index=True)
    out.to_csv("data/equities/daily.csv", index=False)
    print(f"\nwrote data/equities/daily.csv  {len(out):,} rows, "
          f"{out.ticker.nunique()} tickers")
    print(out.groupby("bucket").agg(tickers=("ticker", "nunique"),
                                    rows=("date", "size")).to_string())
    print(f"range: {out.date.min().date()} -> {out.date.max().date()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
