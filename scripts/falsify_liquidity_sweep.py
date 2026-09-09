"""Falsification battery for the session ORB / liquidity-sweep strategy.

Runs the REAL session driver (scripts/backtest_liquidity_sweep.py) through:
1. Bar/slot coverage — confirm trades span the whole series (no stall).
2. Train/test 70/30 split — OOS must stay positive with t > 2.0.
3. Random-time control — the same sweep mechanics at random windows instead of
   the session windows, to test whether time-of-day is the source of any edge.
4. Monthly R breakdown — expose front-loading.

Research only. Nothing here is a candidate for live without passing this.
"""

import random
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from backtest_liquidity_sweep import backtest_sweep, load_m5, summarize, tstat


def run_split(csv, name):
    full = load_m5(csv)
    cut = int(len(full) * 0.7)
    train, test = full.iloc[:cut], full.iloc[cut:]
    print(f"\n== {name} train/test 70/30 ==")
    # configs with any pulse in the full run
    for kind, rr in [("breakout", 1.0), ("breakout", 2.0), ("failed", 1.0), ("failed", 2.0)]:
        summarize(backtest_sweep(train, kind=kind, rr=rr), f"{kind} rr{rr} train")
        summarize(backtest_sweep(test, kind=kind, rr=rr), f"{kind} rr{rr} TEST ")

    # bar coverage check on the best-looking full config
    trades = backtest_sweep(full, kind="failed", rr=1.0)
    if trades:
        first = trades[0]["entry_time"]
        last_e = max(x["exit_time"] for x in trades)
        print(f"\ncoverage (failed rr1.0): {len(full)} bars, first trade {first}, "
              f"last exit {last_e} -> spans to {100*len(full.index[:full.index.get_loc(last_e)+1])/len(full):.0f}% of data")


def run_random_time_control(csv, name):
    """Random-window control: pick random range/sweep hour windows and compare
    their R distribution against the real session windows (Asian range 0-6,
    London sweep 7-9). If random windows match or beat the real ones, the
    session timing carries no alpha."""
    full = load_m5(csv)
    print(f"\n== {name} random-time control (failed kind, rr=1.0) ==")
    # reference: the real session windows
    summarize(backtest_sweep(full, range_win=(0, 6), sweep_win=(7, 9), kind="failed", rr=1.0),
              "REAL Asian0-6/Lon7-9")

    rng = random.Random(42)
    real_results = []
    for i in range(8):
        rs = rng.sample(range(0, 18), 2)
        rs.sort()
        range_h = rs[0]
        sweep_h = (range_h + rng.randint(1, 4)) % 20
        trades = backtest_sweep(full, range_win=(range_h, min(range_h + 1, 23)),
                                sweep_win=(sweep_h, min(sweep_h + 2, 24)),
                                kind="failed", rr=1.0)
        closed = [t for t in trades if t["exit_reason"] != "OPEN"]
        if closed:
            rs_ = [(t["exit_price"] - t["entry"]) / (t["entry"] - t["sl"]) if t["dir"] > 0
                   else (t["entry"] - t["exit_price"]) / (t["sl"] - t["entry"]) for t in closed]
            m, t, n = tstat(rs_)
            print(f"random window r{range_h} s{sweep_h}: n={n:>3} R {m:+.3f} t={t:+.2f}")


def run_monthly(csv, name):
    full = load_m5(csv)
    print(f"\n== {name} monthly R (failed kind, rr=1.0) ==")
    trades = backtest_sweep(full, kind="failed", rr=1.0)
    by_month = {}
    for x in trades:
        if x["exit_reason"] == "OPEN":
            continue
        ym = str(x["entry_time"])[:7]
        r = (x["exit_price"] - x["entry"]) / (x["entry"] - x["sl"]) if x["dir"] > 0 \
            else (x["entry"] - x["exit_price"]) / (x["sl"] - x["entry"])
        by_month.setdefault(ym, []).append(r)
    for ym in sorted(by_month):
        m, t, n = tstat(by_month[ym])
        print(f"  {ym}  n={n:>3}  R {m:+.3f}  t={t:+.2f}")


def main():
    for csv, name in [
        (ROOT / "data/processed/XAUUSDc_M5_broker.csv", "GOLD"),
        (ROOT / "data/processed/BTCUSDc_M5_broker.csv", "BTC "),
    ]:
        if not csv.exists():
            continue
        run_split(csv, name)
        run_random_time_control(csv, name)
        run_monthly(csv, name)


if __name__ == "__main__":
    main()
