"""The Sneaky Pivot premise, measured on US equities at daily resolution.

The strategy buys at the prior-day low (or the swing low beneath it) and targets
the prior-day HIGH, so what decides it is purely geometric: how often does one
session traverse the whole previous day's range?

Daily bars answer that. For a long setup, "did the target print" is
    today.high >= yesterday.high
given today also visited the low zone.

UPPER BOUND, deliberately. Daily OHLC does not record whether the high or the
low came first, so a day that engulfs the prior range counts as a success here
even if the high printed before the low and no entry could have triggered. The
real rules also demand the low arrive in the first 30 minutes and an entry
trigger to fire after it. Buy and sell setups are evaluated independently -- a
wide day can qualify as both -- because excluding two-sided days would remove
precisely the ones that reach the target.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TOL = 0.10        # "close enough" band, as a fraction of the prior day's range
LOOKBACK = 60     # days to scan back for the swing levels
FWD = 5           # sessions for the multi-day variant

df = pd.read_csv("data/equities/daily.csv", parse_dates=["date"])
rows = []

for (tkr, bucket), g in df.groupby(["ticker", "bucket"]):
    g = g.sort_values("date").reset_index(drop=True)
    hi, lo, cl = g.high.values, g.low.values, g.close.values
    for i in range(2, len(g) - FWD):
        rh, rl = hi[i - 1], lo[i - 1]
        rng = rh - rl
        if rng <= 0:
            continue
        sh = next((hi[j] for j in range(i - 2, max(-1, i - 2 - LOOKBACK), -1)
                   if hi[j] > rh), np.nan)
        sl = next((lo[j] for j in range(i - 2, max(-1, i - 2 - LOOKBACK), -1)
                   if lo[j] < rl), np.nan)
        band = TOL * rng
        fwd_hi, fwd_lo = hi[i:i + FWD + 1].max(), lo[i:i + FWD + 1].min()
        rangeiness = rng / cl[i]

        if lo[i] <= rl + band:                      # buy zone visited
            rows.append((tkr, bucket, "buy",
                         lo[i] <= sl if np.isfinite(sl) else np.nan,
                         hi[i] >= rh,
                         hi[i] >= sh if np.isfinite(sh) else np.nan,
                         fwd_hi >= rh, rangeiness))
        if hi[i] >= rh - band:                      # sell zone visited
            rows.append((tkr, bucket, "sell",
                         hi[i] >= sh if np.isfinite(sh) else np.nan,
                         lo[i] <= rl,
                         lo[i] <= sl if np.isfinite(sl) else np.nan,
                         fwd_lo <= rl, rangeiness))

d = pd.DataFrame(rows, columns=["ticker", "bucket", "side", "ext",
                                "tgt_same", "tgt_swing_same", "tgt_5d", "rangeiness"])
f = lambda s: 100 * s.astype(float).mean()

print(f"setups: {len(d):,}   tickers: {d.ticker.nunique()}   "
      f"(TOL={TOL}; upper bound -- intraday ordering not required)\n")
print("=" * 70)
print("CLAIM 1  'visits the swing almost every single time' (07:48)")
print("=" * 70)
print(f"  measured: {f(d.ext):.1f}%\n")
print("=" * 70)
print("CLAIM 2  price travels back to the opposite line (the TARGET)")
print("=" * 70)
print(f"  opposite RANGE line, same session : {f(d.tgt_same):.1f}%")
print(f"  opposite SWING line, same session : {f(d.tgt_swing_same):.1f}%")
print(f"  opposite RANGE line, within {FWD} days: {f(d.tgt_5d):.1f}%")
print("\n  breakeven needed at the ~4.8R geometry the target implies: 17.3%")

print("\n" + "=" * 70)
print("BY BUCKET  (better on the rangy names he actually trades?)")
print("=" * 70)
b = d.groupby("bucket").agg(setups=("side", "size"),
                            daily_range_pct=("rangeiness", lambda s: 100 * s.mean()),
                            claim1_ext=("ext", f), tgt_same=("tgt_same", f),
                            tgt_5d=("tgt_5d", f))
print(b.to_string(float_format=lambda v: f"{v:.1f}"))

t = d.groupby(["ticker", "bucket"]).agg(n=("side", "size"), tgt_same=("tgt_same", f),
                                        rangey=("rangeiness", lambda s: 100 * s.mean()))
print("\ntop 10 tickers by same-session target rate:")
print(t.sort_values("tgt_same", ascending=False).head(10).to_string(
    float_format=lambda v: f"{v:.1f}"))
print(f"\nbest {t.tgt_same.max():.1f}%   median {t.tgt_same.median():.1f}%   "
      f"worst {t.tgt_same.min():.1f}%")
print(f"tickers clearing the 17.3% breakeven (upper bound): "
      f"{(t.tgt_same >= 17.3).sum()} of {len(t)}")
print(f"\ncorrelation between rangeiness and target rate: "
      f"{t.rangey.corr(t.tgt_same, method='spearman'):+.3f}")
