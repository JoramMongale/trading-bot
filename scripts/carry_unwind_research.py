"""Carry-trade unwind research (quick task 20261106-carry-unwind-research).

Research only: the live bots never use this. Run from the repo root:

    python scripts/carry_unwind_research.py fetch     # -> data/processed/carry/
    python scripts/carry_unwind_research.py analyse

Question: do "carry unwind" warning signs (sharp yen strength, VIX stress,
hedge funds covering yen shorts, US 2y yield falling) predict that JPY crosses
fall over the next 5/20 days, and does "calm carry" predict they rise?

The rules below were fixed BEFORE the first run. Do not tune them to the
results: that is how a noise pattern gets traded with real money.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "data" / "processed" / "carry"

YAHOO = ["JPY=X", "EURJPY=X", "CHFJPY=X", "AUDJPY=X", "GBPJPY=X", "^VIX"]
CROSSES = ["EURJPY=X", "CHFJPY=X", "AUDJPY=X", "GBPJPY=X"]
FRED_DGS2 = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS2"
# CFTC Traders in Financial Futures, futures only; 097741 = Japanese yen (CME).
CFTC_JPY = ("https://publicreporting.cftc.gov/resource/gpe5-46if.json?$limit=50000"
            "&$where=cftc_contract_market_code=%27097741%27"
            "&$select=report_date_as_yyyy_mm_dd,lev_money_positions_long,"
            "lev_money_positions_short")


def _get(url: str, timeout: float = 120.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "trading-bot research"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read()


def fetch() -> None:
    from trading_bot.news import macro

    OUT.mkdir(parents=True, exist_ok=True)
    cols = {s: macro._parse_chart(macro._http_get_json(macro._chart_url(s)), s) for s in YAHOO}
    pd.DataFrame(cols).to_csv(OUT / "px.csv")
    (OUT / "dgs2.csv").write_bytes(_get(FRED_DGS2))
    (OUT / "cot_jpy.json").write_bytes(_get(CFTC_JPY))
    print("fetched into", OUT)


def _signals():
    px = pd.read_csv(OUT / "px.csv", index_col=0)
    px.index = pd.to_datetime(px.index, utc=True).tz_convert(None).normalize()
    px = px[~px.index.duplicated(keep="last")].ffill(limit=3)
    px = px[px.index >= "2003-01-01"]

    d2 = pd.read_csv(OUT / "dgs2.csv")
    d2.columns = ["d", "y"]
    us2 = (pd.Series(pd.to_numeric(d2["y"], errors="coerce").values,
                     index=pd.to_datetime(d2["d"])).reindex(px.index).ffill())

    cot = pd.DataFrame(json.loads((OUT / "cot_jpy.json").read_text()))
    # Positions are as of Tuesday, published Friday: usable from +3 days.
    cot.index = pd.to_datetime(cot["report_date_as_yyyy_mm_dd"]) + pd.Timedelta(days=3)
    cot = cot.sort_index()
    net_short = (cot["lev_money_positions_short"].astype(float)
                 - cot["lev_money_positions_long"].astype(float))
    cover = (net_short.shift(4) > 0) & (net_short <= 0.75 * net_short.shift(4))
    cover = cover.reindex(px.index, method="ffill").fillna(False).astype(bool)

    uj, vix = px["JPY=X"], px["^VIX"]
    surge = uj.pct_change(5) <= -0.02                 # yen up 2%+ in a week
    stress = vix >= 1.2 * vix.rolling(50).mean()      # VIX 20%+ above its 50d MA
    narrow = us2.diff(20) <= -0.25                    # US 2y down 25bp+ in a month
    unwind = surge & (stress | cover)
    calm = (vix < vix.rolling(50).mean()) & (uj > uj.rolling(50).mean()) & ~unwind
    sig = {"UNWIND": unwind, "yen surge": surge, "vix stress": stress,
           "cot cover": cover, "2y narrowing": narrow, "CALM": calm}
    return px, sig, net_short


def _stat(px, mask, h, lo, hi):
    lr = np.log(px[CROSSES])
    fwd = (lr.shift(-h) - lr).mean(axis=1) * 100   # basket, entered at signal-day close
    inside = (fwd.index >= lo) & (fwd.index < hi)
    base = fwd[inside].dropna().mean()
    days, nxt = [], None                            # non-overlapping samples
    for t in fwd.index[(mask & inside).fillna(False).values]:
        if np.isnan(fwd[t]):
            continue
        if nxt is None or t >= nxt:
            days.append(t)
            nxt = fwd.index[min(fwd.index.get_loc(t) + h, len(fwd) - 1)]
    x = fwd.loc[days]
    if len(x) < 3:
        return f"n={len(x):3d}"
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    return (f"n={len(x):3d} mean={x.mean():+.2f}% (base {base:+.2f}%) "
            f"t={t:+.2f} down={(x < 0).mean() * 100:.0f}%")


def analyse() -> None:
    px, sig, net_short = _signals()
    for h in (5, 20):
        print(f"\n=== forward {h} days, JPY-cross basket (EUR/CHF/AUD/GBP vs JPY) ===")
        for name, m in sig.items():
            print(f"{name:13s} 2003-14: {_stat(px, m, h, '2003', '2015')}")
            print(f"{'':13s} 2015-26: {_stat(px, m, h, '2015', '2027')}")
    last = px.index[-1]
    print(f"\nlatest {last.date()}: USDJPY {px['JPY=X'].iloc[-1]:.2f}  VIX {px['^VIX'].iloc[-1]:.2f}  "
          + "  ".join(f"{k}={bool(v.iloc[-1])}" for k, v in sig.items()))
    print("hedge-fund net short yen (contracts):",
          {d.date().isoformat(): int(v) for d, v in net_short.tail(4).items()})


if __name__ == "__main__":
    (fetch if (sys.argv[1:] or ["analyse"])[0] == "fetch" else analyse)()
