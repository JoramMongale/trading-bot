"""Sneaky Pivot on US equities -- the instruments the video's author trades.

Levels come from the 3-year DAILY file (so the swing scan has real history);
entries and exits run on the 60-day 15-minute file, which resolves the intraday
ordering that daily bars cannot. Reuses the transcript-verified rule engine in
sneaky_pivot_v2 unchanged.

Sample sizes per ticker are small (60 sessions), so results are POOLED by
bucket. Per-ticker configs would be noise.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, "scripts")
from sneaky_pivot_v2 import backtest, summarise

LOOKBACK = 60
# Round-trip cost in cents-per-share terms: a floor of one penny (the tick) or a
# few bps of price, whichever is larger. Retail equity commissions are zero, so
# spread plus slippage is the whole cost.
BPS = {"liquid": 0.0001, "leveraged": 0.0003, "volatile": 0.0005}


def levels_from_daily(g: pd.DataFrame) -> dict:
    g = g.sort_values("date").reset_index(drop=True)
    hi, lo, dates = g.high.values, g.low.values, g.date.dt.date.values
    out = {}
    for i in range(1, len(g)):
        rh, rl = hi[i - 1], lo[i - 1]
        sh = next((hi[j] for j in range(i - 2, max(-1, i - 2 - LOOKBACK), -1)
                   if hi[j] > rh), np.nan)
        sl = next((lo[j] for j in range(i - 2, max(-1, i - 2 - LOOKBACK), -1)
                   if lo[j] < rl), np.nan)
        out[dates[i]] = dict(range_high=rh, range_low=rl,
                             swing_high=sh, swing_low=sl)
    return out


daily = pd.read_csv("data/equities/daily.csv", parse_dates=["date"])
m15 = pd.read_csv("data/equities/m15.csv")
m15["time"] = pd.to_datetime(m15["time"], utc=True).dt.tz_convert("America/New_York")

all_tr = []
for tkr, g15 in m15.groupby("ticker"):
    dg = daily[daily.ticker == tkr]
    if dg.empty:
        continue
    bucket = g15.bucket.iloc[0]
    lv = levels_from_daily(dg)
    bars = g15.set_index("time")[["open", "high", "low", "close"]].sort_index()
    spread = max(0.01, BPS[bucket] * float(bars.close.median()))
    for tol in (0.05, 0.10, 0.20):
        for tgt in ("range", "swing"):
            tr = backtest(bars, lv, tol, tgt, 0.02, spread, True)
            for t in tr:
                t.update(ticker=tkr, bucket=bucket, tol=tol, target=tgt)
            all_tr += tr

d = pd.DataFrame(all_tr)
d.to_csv("output/sp_equity_trades.csv", index=False)
print(f"trades: {len(d):,}   tickers: {d.ticker.nunique()}   "
      f"sessions: {d.date.nunique()}\n")

print("=" * 88)
print("POOLED BY BUCKET  (60 sessions, Jun-Aug 2026 -- one regime, a pilot)")
print("=" * 88)
rows = []
for (b, tol, tgt), g in d.groupby(["bucket", "tol", "target"]):
    s = summarise(g.to_dict("records"), f"{b:10s} tol={tol:<5} {tgt}")
    r = g.r_net.values
    s["t"] = stats.ttest_1samp(r, 0.0)[0] if len(r) > 2 else np.nan
    rows.append(s)
res = pd.DataFrame(rows).sort_values("avg_R", ascending=False)
cols = ["config", "n", "win%", "tp%", "sl%", "med_RR", "avg_R", "gross_R", "PF", "t"]
print(res[cols].to_string(index=False, float_format=lambda v: f"{v:.3f}"))

print("\n" + "=" * 88)
print("ALL TICKERS POOLED, by config")
print("=" * 88)
rows = []
for (tol, tgt), g in d.groupby(["tol", "target"]):
    s = summarise(g.to_dict("records"), f"ALL tol={tol:<5} {tgt}")
    r = g.r_net.values
    s["t"], s["p"] = stats.ttest_1samp(r, 0.0)
    rows.append(s)
a = pd.DataFrame(rows).sort_values("avg_R", ascending=False)
print(a[["config", "n", "win%", "tp%", "sl%", "med_RR", "avg_R", "gross_R", "PF", "t", "p"]]
      .to_string(index=False, float_format=lambda v: f"{v:.3f}"))

print("\n" + "=" * 88)
print("EXIT MIX + the decisive comparison")
print("=" * 88)
print(d.exit_reason.value_counts(normalize=True).mul(100).round(1).to_string())
be = 100 / (1 + d.rr.median())
print(f"\n  median R:R {d.rr.median():.2f}  ->  breakeven win rate {be:.1f}%")
print(f"  actual TP rate                        {100 * (d.exit_reason == 'TP').mean():.1f}%")
print(f"  daily-data UPPER BOUND was            21.6%")
print(f"\n  overall avg_R (net) {d.r_net.mean():+.4f}   gross {d.r_gross.mean():+.4f}")
print(d.groupby("direction").r_net.agg(["size", "mean"]).to_string(
    float_format=lambda v: f"{v:.4f}"))
