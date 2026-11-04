"""Significance, out-of-sample and a beta check for the transcript-rule version."""
from __future__ import annotations
import numpy as np, pandas as pd
from scipy import stats

def load(p):
    d = pd.read_csv(p)
    d["entry_time"] = pd.to_datetime(d["entry_time"], format="mixed", utc=True)
    return d

net, gross = load("output/sp2_trades.csv"), load("output/sp2_nospread_trades.csv")
hold = load("output/sp2_hold5_trades.csv")
sn, sg = pd.read_csv("output/sp2_summary.csv"), pd.read_csv("output/sp2_nospread_summary.csv")
key = ["symbol", "tol", "target"]

print("=" * 76); print("1. COST vs EDGE (transcript rules, same-session)"); print("=" * 76)
for nm, s in (("frictionless", sg), ("with spread", sn)):
    print(f"  {nm:13s} mean avg_R {s.avg_R.mean():+.4f}   "
          f"positive {(s.avg_R > 0).sum():3d}/{len(s)}   best {s.avg_R.max():+.3f}")
print(f"\n  Unlike the reconstructed version, this is negative BEFORE costs too.")

print("\n" + "=" * 76); print("2. SIGNIFICANCE (data-snooping aware)"); print("=" * 76)
rows = []
for (sym, tol, tgt), g in net.groupby(key):
    r = g.r_net.values
    if len(r) < 40: continue
    t, p = stats.ttest_1samp(r, 0.0)
    rows.append(dict(config=f"{sym} tol={tol} {tgt}", n=len(r), avg_R=r.mean(), t=t, p=p))
tt = pd.DataFrame(rows).sort_values("t", ascending=False)
bonf = 0.05 / len(tt)
pos, neg = tt[tt.avg_R > 0], tt[tt.avg_R <= 0]
print(f"  configs tested {len(tt)}   Bonferroni p < {bonf:.5f} (|t| ~ {stats.norm.ppf(1-bonf/2):.2f})")
print(f"  significantly POSITIVE p<0.05: {(pos.p<0.05).sum():3d}   Bonferroni: {(pos.p<bonf).sum()}")
print(f"  significantly NEGATIVE p<0.05: {(neg.p<0.05).sum():3d}   Bonferroni: {(neg.p<bonf).sum()}")
print("\n  best 3:"); print(tt.head(3).to_string(index=False, float_format=lambda v: f"{v:.4f}"))

print("\n" + "=" * 76); print("3. OUT-OF-SAMPLE"); print("=" * 76)
cut = net.entry_time.quantile(0.6)
a = net[net.entry_time <= cut].groupby(key).r_net.agg(["mean","count"]).query("count>=20")
b = net[net.entry_time >  cut].groupby(key).r_net.agg(["mean","count"]).query("count>=12")
j = a.join(b, lsuffix="_tr", rsuffix="_te", how="inner").sort_values("mean_tr", ascending=False)
top = j.head(8).reset_index()
top["config"] = top.symbol + " tol=" + top.tol.astype(str) + " " + top.target
print(top[["config","mean_tr","count_tr","mean_te","count_te"]].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
print(f"\n  top-8 in-sample {top.mean_tr.mean():+.4f} -> out-of-sample {top.mean_te.mean():+.4f}"
      f"   still positive: {(top.mean_te>0).sum()}/8")
rho, pv = stats.spearmanr(j.mean_tr, j.mean_te)
print(f"  rank correlation train vs test: rho={rho:+.3f} (p={pv:.3f})")

print("\n" + "=" * 76); print("4. IS THE 5-DAY STEELMAN EDGE, OR LONG-SIDE DRIFT?"); print("=" * 76)
print(hold.groupby("direction").r_net.agg(["size","mean"]).to_string(float_format=lambda v: f"{v:.4f}"))
c = hold[hold.symbol.isin(["BTCUSDm","ETHUSDm"])]
print(f"\n  crypto only:  long {c[c.direction=='long'].r_net.mean():+.3f} "
      f"(n={(c.direction=='long').sum()})   "
      f"short {c[c.direction=='short'].r_net.mean():+.3f} (n={(c.direction=='short').sum()})")
oth = hold[~hold.symbol.isin(["BTCUSDm","ETHUSDm"])]
print(f"  everything else: {oth.r_net.mean():+.4f} (n={len(oth)})")
for s in ("BTCUSDm","ETHUSDm","USTECm"):
    px = pd.read_csv(f"data/processed/multi/{s}.csv", parse_dates=["time"])
    r = 100*(px.close.iloc[-1]/px.close.iloc[0]-1)
    print(f"  {s} buy-and-hold over the sample: {r:+.0f}%")
