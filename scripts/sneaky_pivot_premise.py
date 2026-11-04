"""Test the claim the whole strategy rests on.

At 07:48 the video says that after the first 15 minutes, "either the range low
gets broken and it immediately visits the swing low or the range high gets
broken and it visits the swing high almost every single time."

And the trade premise at 08:09: buy at the range/swing low and "trade it back to
either the swing high or the range high".

Both are measurable. This script measures them, with no trading logic in the
way -- it asks only how often price actually travels those distances.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import sys

sys.path.insert(0, "scripts")
from sneaky_pivot_v2 import load_m15, build_levels, SPREADS, SESSION_TZ

t_open, t_close = pd.Timestamp("09:30").time(), pd.Timestamp("16:00").time()
rows = []

for sym in SPREADS:
    m15 = load_m15(sym)
    levels = build_levels(m15)
    by_day = {d: g for d, g in m15.groupby(m15.index.date)}
    dates = sorted(by_day)

    for i, day in enumerate(dates):
        lv = levels.get(day)
        if lv is None or not np.isfinite(lv["range_high"]):
            continue
        rh, rl = lv["range_high"], lv["range_low"]
        if rh - rl <= 0:
            continue
        g = by_day[day]
        sess = g[(g.index.time >= t_open) & (g.index.time < t_close)]
        if len(sess) < 4 or sess.index[0].time() != t_open:
            continue

        c12 = sess.iloc[:2]
        band = 0.10 * (rh - rl)
        at_buy = c12.low.min() <= rl + band
        at_sell = c12.high.max() >= rh - band
        if at_buy == at_sell:
            continue
        rest = sess.iloc[2:]
        if rest.empty:
            continue

        # forward window for the multi-day steelman
        fwd = pd.concat([by_day[d] for d in dates[i:i + 6]])
        fwd = fwd[fwd.index > sess.index[1]]

        if at_buy:
            hit_ext = rest.low.min() <= lv["swing_low"] if np.isfinite(lv["swing_low"]) else np.nan
            tgt_r, tgt_s = rh, lv["swing_high"]
            same = rest.high.max() >= tgt_r
            multi = fwd.high.max() >= tgt_r if len(fwd) else np.nan
            multi_s = (fwd.high.max() >= tgt_s) if (len(fwd) and np.isfinite(tgt_s)) else np.nan
        else:
            hit_ext = rest.high.max() >= lv["swing_high"] if np.isfinite(lv["swing_high"]) else np.nan
            tgt_r, tgt_s = rl, lv["swing_low"]
            same = rest.low.min() <= tgt_r
            multi = fwd.low.min() <= tgt_r if len(fwd) else np.nan
            multi_s = (fwd.low.min() <= tgt_s) if (len(fwd) and np.isfinite(tgt_s)) else np.nan

        rows.append(dict(symbol=sym, side="buy" if at_buy else "sell",
                         ext_same_session=hit_ext, opp_range_same_session=same,
                         opp_range_5day=multi, opp_swing_5day=multi_s))

d = pd.DataFrame(rows)
print(f"setups examined: {len(d):,} across {d.symbol.nunique()} symbols\n")
print("CLAIM 1 -- after the open reaches a level, price 'visits the swing'")
print("           (the next level BEYOND) in the same session:")
print(f"           {100 * d.ext_same_session.mean(nan_policy if False else slice(None)).mean() if False else 100 * d.ext_same_session.astype(float).mean():.1f}%   "
      f'(video: "almost every single time")\n')

print("CLAIM 2 -- the TARGET: price travels back to the opposite level")
print(f"           opposite RANGE line, same session : {100 * d.opp_range_same_session.astype(float).mean():.1f}%")
print(f"           opposite RANGE line, within 5 days: {100 * d.opp_range_5day.astype(float).mean():.1f}%")
print(f"           opposite SWING line, within 5 days: {100 * d.opp_swing_5day.astype(float).mean():.1f}%")

print("\nby symbol (same-session target hit rate):")
t = d.groupby("symbol").agg(setups=("side", "size"),
                            ext=("ext_same_session", lambda s: 100 * s.astype(float).mean()),
                            tgt_same=("opp_range_same_session", lambda s: 100 * s.astype(float).mean()),
                            tgt_5d=("opp_range_5day", lambda s: 100 * s.astype(float).mean()))
print(t.sort_values("tgt_same", ascending=False).to_string(float_format=lambda v: f"{v:.1f}"))
