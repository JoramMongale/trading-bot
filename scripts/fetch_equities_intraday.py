"""Fetch 15-minute US equity bars (Yahoo caps this at ~60 days).

Short window, but free and immediate, and it is the only thing that can settle
the question the daily premise test leaves open: daily bars cannot tell whether
the high or the low printed first, so they only bound the target rate from
above. Intraday bars resolve the ordering and let the real entry rules run.
"""

from __future__ import annotations

import sys
import time

import pandas as pd
import yfinance as yf

sys.path.insert(0, "scripts")
from fetch_equities import UNIVERSE

frames = []
for bucket, tickers in UNIVERSE.items():
    for i in range(0, len(tickers), 8):
        chunk = tickers[i:i + 8]
        for attempt in range(4):
            try:
                d = yf.download(chunk, period="60d", interval="15m",
                                auto_adjust=False, progress=False,
                                threads=False, group_by="ticker")
                break
            except Exception as e:
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
            if len(sub) < 300:
                print(f"  skip {t}: {len(sub)} bars", file=sys.stderr)
                continue
            sub = sub.reset_index()
            sub.columns = [c.lower() for c in sub.columns]
            tcol = "datetime" if "datetime" in sub.columns else "index"
            sub = sub.rename(columns={tcol: "time"})[
                ["time", "open", "high", "low", "close", "volume"]]
            sub["ticker"], sub["bucket"] = t, bucket
            frames.append(sub)
        print(f"{bucket}: {chunk} ok", flush=True)
        time.sleep(1.5)

out = pd.concat(frames, ignore_index=True)
out.to_csv("data/equities/m15.csv", index=False)
et = pd.to_datetime(out.time, utc=True).dt.tz_convert("America/New_York")
print(f"\nwrote data/equities/m15.csv  {len(out):,} bars, {out.ticker.nunique()} tickers")
print(f"sessions: {et.dt.normalize().nunique()}   "
      f"range: {et.min().date()} -> {et.max().date()}")
