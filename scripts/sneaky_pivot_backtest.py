"""Sneaky Pivot backtest (opening-range three-candle breakout).

Rules as reconstructed from the video summary (the transcript itself was not
retrievable -- see the caveats printed by --explain):

  candle 1  "Opening Range"  the first M15 candle of the session
  candle 2  "Sneaky"         the second M15 candle; its range is the bracket
  candle 3+ "Entry"          a stop order on each side of the Sneaky candle

  long  : entry = sneaky.high, stop = sneaky.low
  short : entry = sneaky.low,  stop = sneaky.high
  target: rr * risk, where risk = sneaky.high - sneaky.low
  OCO   : the first side to trigger cancels the other; one trade per day

Fill/exit conventions match src/trading_bot/backtest/engine.py:
  - the order is armed at the Sneaky candle's close and can fill from candle 3
  - a gap past the level fills at the open (the worse price, both directions)
  - intrabar exits are pessimistic: SL is checked before TP, including on the
    fill bar itself
  - unresolved at the end of the entry window -> close at that bar's close

Costs: one full spread per round trip is deducted from every trade. That is the
first-order model, and it is not optional here -- the stop is a single M15
candle, so the spread is a far larger fraction of R than it is for the
structural-stop strategy this repo already trades.
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

DATA_DIR = "data/processed/multi"

# Typical Exness Standard-account spreads, in PRICE units for each symbol.
# Deliberately on the pessimistic side of typical; override with --spread-mult.
SPREADS = {
    "EURUSDm": 0.00010, "GBPUSDm": 0.00013, "AUDUSDm": 0.00013,
    "NZDUSDm": 0.00020, "USDCADm": 0.00015, "USDCHFm": 0.00015,
    "USDJPYm": 0.010,   "EURJPYm": 0.015,   "GBPJPYm": 0.020,
    "XAUUSDm": 0.15,    "XAGUSDm": 0.020,   "XAUEURm": 0.20,
    "USTECm": 1.5,      "US500m": 0.5,      "USOILm": 0.020,
    "BTCUSDm": 15.0,    "ETHUSDm": 1.5,
}

# Candidate "first candle of the day" anchors. The video says "the first 15
# minute candle of the day" without saying whose day, and that choice is
# load-bearing, so it is swept rather than assumed.
ANCHORS = {
    "ny930":    ("America/New_York", "09:30"),  # US equity open
    "ny800":    ("America/New_York", "08:00"),  # US pre-market / futures push
    "london":   ("Europe/London",    "08:00"),  # London open
    "frankfurt":("Europe/Berlin",    "09:00"),  # Frankfurt open
    "utc0":     ("UTC",              "00:00"),  # broker day open
    "tokyo":    ("Asia/Tokyo",       "09:00"),  # Tokyo open
}


def load_m15(symbol: str) -> pd.DataFrame:
    """Load the M5 broker CSV and aggregate to M15, keeping the bar count."""
    df = pd.read_csv(f"{DATA_DIR}/{symbol}.csv", parse_dates=["time"], index_col="time")
    df = df.tz_localize("UTC")
    m15 = df.resample("15min", label="left", closed="left").agg(
        open=("open", "first"), high=("high", "max"),
        low=("low", "min"), close=("close", "last"), n=("close", "size"),
    ).dropna(subset=["close"])
    # A bucket built from one M5 bar is a stub around a gap; its high/low do not
    # describe a real 15 minutes, and the whole strategy is a bet on one
    # candle's range. Require at least 2 of the 3 constituent bars.
    return m15[m15["n"] >= 2]


def backtest(m15: pd.DataFrame, tz: str, anchor: str, rr: float,
             entry_bars: int, spread: float) -> list[dict]:
    """Run one (anchor, rr) configuration over all days. Returns trade dicts."""
    local = m15.tz_convert(tz)
    anchor_t = pd.Timestamp(anchor).time()
    trades: list[dict] = []

    for _, g in local.groupby(local.index.date):
        hit = np.flatnonzero(g.index.time == anchor_t)
        if not len(hit):
            continue
        i0 = int(hit[0])
        # Opening Range, Sneaky and the first Entry candle must be contiguous.
        if i0 + 2 >= len(g):
            continue
        if (g.index[i0 + 1] - g.index[i0]) != pd.Timedelta("15min"):
            continue

        sneaky = g.iloc[i0 + 1]
        hi, lo = float(sneaky.high), float(sneaky.low)
        risk = hi - lo
        if risk <= 0:
            continue

        window = g.iloc[i0 + 2: i0 + 2 + entry_bars]
        if window.empty:
            continue

        trade = _walk(window, hi, lo, risk, rr)
        if trade is None:
            continue
        trade.update(
            date=g.index[i0].date(), risk=risk,
            sneaky_time=g.index[i0 + 1],
            r_gross=trade["pnl_gross"] / risk,
            r_net=(trade["pnl_gross"] - spread) / risk,
        )
        trades.append(trade)

    return trades


def _walk(window: pd.DataFrame, hi: float, lo: float,
          risk: float, rr: float) -> dict | None:
    """Find the first side to trigger, then resolve that trade to an exit."""
    for t in range(len(window)):
        bar = window.iloc[t]
        o, h, l = float(bar.open), float(bar.high), float(bar.low)

        long_hit, short_hit = h >= hi, l <= lo
        if not (long_hit or short_hit):
            continue

        if long_hit and short_hit:
            # Both levels touched in one bar. Resolve by which side the bar
            # opened nearer to -- and if it opened outside the bracket, that is
            # the side that filled first, at the open.
            if o >= hi:
                side = 1
            elif o <= lo:
                side = -1
            else:
                side = 1 if (hi - o) <= (o - lo) else -1
        else:
            side = 1 if long_hit else -1

        if side > 0:
            entry, sl = max(hi, o), lo
        else:
            entry, sl = min(lo, o), hi
        tp = entry + side * rr * abs(entry - sl)

        return _resolve(window, t, side, entry, sl, tp, risk)

    return None


def _resolve(window: pd.DataFrame, t0: int, side: int, entry: float,
             sl: float, tp: float, risk: float) -> dict:
    """Walk forward from the fill bar. SL is checked before TP, always."""
    for t in range(t0, len(window)):
        bar = window.iloc[t]
        h, l = float(bar.high), float(bar.low)
        adverse = l if side > 0 else h
        favourable = h if side > 0 else l

        if side * adverse <= side * sl:
            return _rec(window, t0, t, side, entry, sl, tp, sl, "SL")
        if side * favourable >= side * tp:
            return _rec(window, t0, t, side, entry, sl, tp, tp, "TP")

    last = window.iloc[-1]
    return _rec(window, t0, len(window) - 1, side, entry, sl, tp,
                float(last.close), "TIME")


def _rec(window, t0, t, side, entry, sl, tp, exit_price, reason) -> dict:
    return {
        "entry_time": window.index[t0], "exit_time": window.index[t],
        "direction": "long" if side > 0 else "short",
        "entry": entry, "sl": sl, "tp": tp,
        "exit_price": exit_price, "exit_reason": reason,
        "bars_held": t - t0,
        "pnl_gross": side * (exit_price - entry),
    }


def summarise(trades: list[dict], label: str) -> dict:
    """Aggregate in R units. Net R already carries the spread deduction."""
    if not trades:
        return {"config": label, "n": 0}
    r = np.array([t["r_net"] for t in trades])
    wins, losses = r[r > 0], r[r <= 0]
    eq = r.cumsum()
    dd = float((np.maximum.accumulate(eq) - eq).max()) if len(eq) else 0.0
    return {
        "config": label,
        "n": len(r),
        "win%": 100.0 * len(wins) / len(r),
        "avg_R": float(r.mean()),
        "tot_R": float(r.sum()),
        "gross_R": float(np.mean([t["r_gross"] for t in trades])),
        "PF": float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf"),
        "maxDD_R": dd,
        "tp%": 100.0 * sum(t["exit_reason"] == "TP" for t in trades) / len(r),
        "sl%": 100.0 * sum(t["exit_reason"] == "SL" for t in trades) / len(r),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbols", default="all")
    p.add_argument("--anchors", default="all")
    p.add_argument("--rr", default="1,1.5,2,3")
    p.add_argument("--entry-bars", type=int, default=24,
                   help="M15 bars the bracket stays live (24 = 6 hours)")
    p.add_argument("--spread-mult", type=float, default=1.0,
                   help="0 for a frictionless run, 1 for modelled spread")
    p.add_argument("--out", default="output/sneaky_pivot")
    p.add_argument("--top", type=int, default=25)
    a = p.parse_args()

    symbols = list(SPREADS) if a.symbols == "all" else a.symbols.split(",")
    anchors = list(ANCHORS) if a.anchors == "all" else a.anchors.split(",")
    rrs = [float(x) for x in a.rr.split(",")]

    rows, all_trades = [], []
    for sym in symbols:
        try:
            m15 = load_m15(sym)
        except FileNotFoundError:
            print(f"skip {sym}: no data", file=sys.stderr)
            continue
        spread = SPREADS[sym] * a.spread_mult
        for aname in anchors:
            tz, at = ANCHORS[aname]
            for rr in rrs:
                tr = backtest(m15, tz, at, rr, a.entry_bars, spread)
                for t in tr:
                    t.update(symbol=sym, anchor=aname, rr=rr)
                all_trades += tr
                s = summarise(tr, f"{sym:9s} {aname:9s} rr={rr}")
                s.update(symbol=sym, anchor=aname, rr=rr)
                rows.append(s)

    res = pd.DataFrame(rows)
    res = res[res["n"] >= 40].sort_values("avg_R", ascending=False)
    pd.set_option("display.width", 200, "display.max_rows", 400)
    cols = ["config", "n", "win%", "tp%", "sl%", "avg_R", "gross_R", "tot_R", "PF", "maxDD_R"]
    print(f"\n=== Sneaky Pivot | spread x{a.spread_mult} | entry window {a.entry_bars} bars ===")
    print(res[cols].head(a.top).to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(f"\nconfigs tested: {len(rows)}   trades: {len(all_trades)}")
    print(f"avg_R across ALL configs: {res['avg_R'].mean():+.4f}   "
          f"configs with avg_R>0: {(res['avg_R'] > 0).sum()}/{len(res)}")

    res.to_csv(f"{a.out}_summary.csv", index=False)
    pd.DataFrame(all_trades).to_csv(f"{a.out}_trades.csv", index=False)
    print(f"\nwrote {a.out}_summary.csv and {a.out}_trades.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
