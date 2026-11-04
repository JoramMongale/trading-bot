"""Does anything in the Sneaky Pivot sweep survive scrutiny?

Three questions, in the order that matters:
  1. spread  -- how much of the raw pattern does the cost of trading eat?
  2. luck    -- is the best config significant once you account for having
                tested hundreds of them (data snooping)?
  3. decay   -- does the config chosen on the first half of the data still
                work on the second half it never saw?
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

def _load(path):
    d = pd.read_csv(path)
    # tz-aware stamps across DST have mixed UTC offsets; normalise to UTC.
    d["entry_time"] = pd.to_datetime(d["entry_time"], format="mixed", utc=True)
    return d

net = _load("output/sneaky_pivot_trades.csv")
gross = _load("output/sp_nospread_trades.csv")
s_net = pd.read_csv("output/sneaky_pivot_summary.csv")
s_gross = pd.read_csv("output/sp_nospread_summary.csv")

print("=" * 78)
print("1. WHAT THE SPREAD COSTS")
print("=" * 78)
for name, s in (("frictionless", s_gross), ("with spread", s_net)):
    print(f"  {name:13s} mean avg_R {s.avg_R.mean():+.4f}   "
          f"positive configs {(s.avg_R > 0).sum():3d}/{len(s)} "
          f"({100 * (s.avg_R > 0).mean():.0f}%)   best {s.avg_R.max():+.3f}")
print(f"\n  spread cost per trade: {s_gross.avg_R.mean() - s_net.avg_R.mean():.4f} R")
print(f"  raw edge before costs: {s_gross.avg_R.mean():+.4f} R")
print(f"  -> costs are {abs(s_gross.avg_R.mean() - s_net.avg_R.mean()) / s_gross.avg_R.mean():.1f}x "
      "the entire edge")

# The anchor grid has duplicates: London 08:00 == Frankfurt 09:00 and
# Tokyo 09:00 == 00:00 UTC are the same instant, so the effective number of
# independent configurations is smaller than the row count.
key = ["symbol", "anchor", "rr"]
n_eff = net.groupby(key).entry_time.apply(lambda s: hash(tuple(s.head(50)))).nunique()
print(f"\n  distinct configs (deduped by identical trade sets): {n_eff} of {len(s_net)}")

print("\n" + "=" * 78)
print("2. IS THE BEST CONFIG REAL? (t-stats vs a data-snooping threshold)")
print("=" * 78)
rows = []
for (sym, anc, rr), g in net.groupby(key):
    r = g.r_net.values
    if len(r) < 40:
        continue
    t, p = stats.ttest_1samp(r, 0.0)
    rows.append(dict(config=f"{sym} {anc} rr={rr}", n=len(r),
                     avg_R=r.mean(), t=t, p=p))
tt = pd.DataFrame(rows).sort_values("t", ascending=False)

bonf = 0.05 / n_eff
print(f"  nominal 5% threshold        p < 0.0500")
print(f"  Bonferroni for {n_eff} configs  p < {bonf:.5f}   (|t| ~ "
      f"{stats.norm.ppf(1 - bonf / 2):.2f})")
print(f"\n  best 5 by t-stat:")
print(tt.head(5).to_string(index=False, float_format=lambda v: f"{v:.4f}"))
# Split by SIGN. A two-sided p-value is just as small for a config that
# loses reliably, and those are the majority here -- counting them as
# "passing" would invert the conclusion.
pos, neg = tt[tt.avg_R > 0], tt[tt.avg_R <= 0]
print(f"\n  significantly POSITIVE  p<0.05: {(pos.p < 0.05).sum():3d}   "
      f"Bonferroni: {(pos.p < bonf).sum()}")
print(f"  significantly NEGATIVE  p<0.05: {(neg.p < 0.05).sum():3d}   "
      f"Bonferroni: {(neg.p < bonf).sum()}")
print(f"  (chance alone predicts ~{0.05 * len(tt):.0f} either way, from {len(tt)} configs)")
print(f"\n  worst 3 by t-stat:")
print(tt.tail(3).to_string(index=False, float_format=lambda v: f"{v:.4f}"))

print("\n" + "=" * 78)
print("3. OUT-OF-SAMPLE: pick the winner in-sample, then trade it forward")
print("=" * 78)
cut = net.entry_time.quantile(0.6)
tr, te = net[net.entry_time <= cut], net[net.entry_time > cut]
print(f"  train {tr.entry_time.min().date()} -> {cut.date()}   "
      f"test {te.entry_time.min().date()} -> {te.entry_time.max().date()}")

a = tr.groupby(key).r_net.agg(["mean", "count"]).query("count >= 25")
b = te.groupby(key).r_net.agg(["mean", "count"]).query("count >= 15")
both = a.join(b, lsuffix="_tr", rsuffix="_te", how="inner").sort_values(
    "mean_tr", ascending=False)

print(f"\n  top 10 in-sample configs, and what they did out-of-sample:")
top = both.head(10).reset_index()
top["config"] = top.symbol + " " + top.anchor + " rr=" + top.rr.astype(str)
print(top[["config", "mean_tr", "count_tr", "mean_te", "count_te"]].to_string(
    index=False, float_format=lambda v: f"{v:.3f}"))

print(f"\n  top-10 in-sample avg_R : {top.mean_tr.mean():+.4f}")
print(f"  their out-of-sample    : {top.mean_te.mean():+.4f}")
print(f"  of the top 10, still positive out-of-sample: {(top.mean_te > 0).sum()}/10")
rho, pv = stats.spearmanr(both.mean_tr, both.mean_te)
print(f"\n  rank correlation train vs test across all {len(both)} configs: "
      f"rho={rho:+.3f} (p={pv:.3f})")
print("  -> a real edge gives strongly positive rho; ~0 means the ranking is noise")

print("\n" + "=" * 78)
print("4. DIRECTIONAL / STRUCTURAL SANITY")
print("=" * 78)
print(net.groupby("direction").r_net.agg(["count", "mean"]).to_string(
    float_format=lambda v: f"{v:.4f}"))
print()
print(net.groupby("exit_reason").agg(n=("r_net", "size"),
                                     avg_R=("r_net", "mean")).to_string(
    float_format=lambda v: f"{v:.4f}"))
print("\n  spread as a fraction of the stop distance (median), per symbol:")
sp = {"EURUSDm": 0.00010, "GBPUSDm": 0.00013, "AUDUSDm": 0.00013, "NZDUSDm": 0.00020,
      "USDCADm": 0.00015, "USDCHFm": 0.00015, "USDJPYm": 0.010, "EURJPYm": 0.015,
      "GBPJPYm": 0.020, "XAUUSDm": 0.15, "XAGUSDm": 0.020, "XAUEURm": 0.20,
      "USTECm": 1.5, "US500m": 0.5, "USOILm": 0.020, "BTCUSDm": 15.0, "ETHUSDm": 1.5}
frac = (net.groupby("symbol").risk.median().to_frame("median_stop"))
frac["spread"] = frac.index.map(sp)
frac["spread_%_of_R"] = 100 * frac.spread / frac.median_stop
print(frac.sort_values("spread_%_of_R", ascending=False).to_string(
    float_format=lambda v: f"{v:.4f}"))
