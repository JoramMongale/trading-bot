"""Sneaky Pivot, as actually described in the video (transcript-verified).

Rules, with the timecode each one comes from:

  levels (02:50-04:47)
    range high/low = the PREVIOUS DAY's high and low
    swing high/low = scanning back through history, the first prior day whose
                     high exceeds the range high (resp. low below the range low)

  location filter (06:07) -- the core of the strategy
    "we are only, I mean only going to buy or sell ... if, and only if it is at
     one of those lines. Anywhere else, leave it alone."
    upper two lines are sell-only, lower two are buy-only. This makes the
    system MEAN REVERTING, not a breakout.

  three-candle framework (08:37-09:18)
    c1  opening range candle, the first M15 candle of the session (09:30 ET)
    c2  the "sneaky" candle, which confirms c1
    c3+ entry, "in most cases at the 45 minute mark"

  entry (13:09)   price crossing the sneaky candle's high (long) / low (short)
  stop  (13:25)   "underneath the big buyer" -- beyond the tested level, taken
                  here as the lowest low of c1/c2 plus a buffer
  target (14:19)  the OPPOSITE level -- range high or swing high. Not a fixed
                  R multiple; the R:R is whatever the geometry gives.

  tolerance (18:05, 22:00) "technical analysis is not literal ... that's close
                  enough" -- so touching a level is a zone, swept via --tol.

Deliberately NOT modelled: he trades US single stocks and ETFs live (AAOI,
GGLL); this repo has no equity data, so the nearest proxies are US500m/USTECm
(he demos on YM Dow futures). Read the FX/metals/crypto rows as "does the level
logic generalise", not as a replication of his actual book.
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

DATA_DIR = "data/processed/multi"
SESSION_TZ = "America/New_York"

SPREADS = {
    "EURUSDm": 0.00010, "GBPUSDm": 0.00013, "AUDUSDm": 0.00013,
    "NZDUSDm": 0.00020, "USDCADm": 0.00015, "USDCHFm": 0.00015,
    "USDJPYm": 0.010,   "EURJPYm": 0.015,   "GBPJPYm": 0.020,
    "XAUUSDm": 0.15,    "XAGUSDm": 0.020,   "XAUEURm": 0.20,
    "USTECm": 1.5,      "US500m": 0.5,      "USOILm": 0.020,
    "BTCUSDm": 15.0,    "ETHUSDm": 1.5,
}


def load_m15(symbol: str) -> pd.DataFrame:
    df = pd.read_csv(f"{DATA_DIR}/{symbol}.csv", parse_dates=["time"], index_col="time")
    m15 = df.tz_localize("UTC").resample("15min", label="left", closed="left").agg(
        open=("open", "first"), high=("high", "max"),
        low=("low", "min"), close=("close", "last"), n=("close", "size"),
    ).dropna(subset=["close"])
    return m15[m15["n"] >= 2].tz_convert(SESSION_TZ)


def build_levels(m15: pd.DataFrame, lookback: int = 60) -> dict:
    """Per session date: the four magic lines, from prior days only."""
    daily = m15.groupby(m15.index.date).agg(high=("high", "max"), low=("low", "min"))
    dates = list(daily.index)
    hi, lo = daily.high.values, daily.low.values
    out = {}
    for i in range(1, len(dates)):
        rh, rl = hi[i - 1], lo[i - 1]
        # "go back to the left as far as you can until you find the next price
        # that was higher than the range high" -- the FIRST one encountered
        # scanning backwards, not the global maximum.
        sh = next((hi[j] for j in range(i - 2, max(-1, i - 2 - lookback), -1)
                   if hi[j] > rh), np.nan)
        sl = next((lo[j] for j in range(i - 2, max(-1, i - 2 - lookback), -1)
                   if lo[j] < rl), np.nan)
        out[dates[i]] = dict(range_high=rh, range_low=rl,
                             swing_high=sh, swing_low=sl)
    return out


def backtest(m15: pd.DataFrame, levels: dict, tol: float, target: str,
             buf: float, spread: float, require_confirm: bool,
             open_time: str = "09:30", close_time: str = "16:00",
             hold_days: int = 0) -> list[dict]:
    trades = []
    t_open, t_close = pd.Timestamp(open_time).time(), pd.Timestamp(close_time).time()
    # hold_days > 0 is a steelman, not his rule: he is explicitly a day trader
    # ("15 minutes a day") and both live trades in the video close same-session.
    # It exists because the level target is a daily-range-scale move, which the
    # premise test shows is rarely covered in one session.
    by_day = {d: g for d, g in m15.groupby(m15.index.date)}
    day_list = sorted(by_day)
    day_pos = {d: i for i, d in enumerate(day_list)}

    for day, g in m15.groupby(m15.index.date):
        lv = levels.get(day)
        if lv is None or not np.isfinite(lv["range_high"]):
            continue
        rh, rl = lv["range_high"], lv["range_low"]
        prev_range = rh - rl
        if prev_range <= 0:
            continue

        sess = g[(g.index.time >= t_open) & (g.index.time < t_close)]
        if len(sess) < 4 or sess.index[0].time() != t_open:
            continue
        c1, c2 = sess.iloc[0], sess.iloc[1]

        # --- location filter: did the open reach a buy zone or a sell zone? ---
        band = tol * prev_range
        low2, high2 = min(c1.low, c2.low), max(c1.high, c2.high)
        at_buy = low2 <= rl + band
        at_sell = high2 >= rh - band
        if at_buy == at_sell:      # neither, or both -> no clean read
            continue
        side = 1 if at_buy else -1

        # --- sneaky candle confirms: green under a low, red under a high ---
        if require_confirm and side * (c2.close - c2.open) <= 0:
            continue

        # --- target: the opposite magic line ---
        if side > 0:
            tp = rh if target == "range" else lv["swing_high"]
        else:
            tp = rl if target == "range" else lv["swing_low"]
        if not np.isfinite(tp):
            continue

        entry_level = c2.high if side > 0 else c2.low
        sl = (low2 - buf * prev_range) if side > 0 else (high2 + buf * prev_range)
        risk = side * (entry_level - sl)
        # Target must sit beyond the entry, and the stop beneath it; when the
        # open has already run past the opposite line there is no trade left.
        if risk <= 0 or side * (tp - entry_level) <= 0:
            continue

        win = sess.iloc[2:]
        if hold_days:
            i = day_pos[day]
            extra = [by_day[d] for d in day_list[i + 1:i + 1 + hold_days]]
            if extra:
                win = pd.concat([win] + extra)
        tr = _walk(win, side, entry_level, sl, tp)
        if tr is None:
            continue
        tr.update(date=day, risk=risk, rr=side * (tp - entry_level) / risk,
                  level="swing" if (low2 <= lv["swing_low"] if side > 0
                                    else high2 >= lv["swing_high"]) else "range",
                  r_gross=tr["pnl_gross"] / risk,
                  r_net=(tr["pnl_gross"] - spread) / risk)
        trades.append(tr)
    return trades


def _walk(win: pd.DataFrame, side: int, entry: float, sl: float, tp: float):
    """Arm a stop order; fill from the next bar; resolve SL before TP."""
    for t in range(len(win)):
        bar = win.iloc[t]
        if side * (bar.high if side > 0 else bar.low) < side * entry:
            continue
        fill = max(entry, bar.open) if side > 0 else min(entry, bar.open)
        if side * (tp - fill) <= 0:
            return None                      # gapped past the target
        for u in range(t, len(win)):
            b = win.iloc[u]
            if side * (b.low if side > 0 else b.high) <= side * sl:
                return _rec(win, t, u, side, fill, sl, tp, sl, "SL")
            if side * (b.high if side > 0 else b.low) >= side * tp:
                return _rec(win, t, u, side, fill, sl, tp, tp, "TP")
        last = win.iloc[-1]
        return _rec(win, t, len(win) - 1, side, fill, sl, tp,
                    float(last.close), "EOD")
    return None


def _rec(win, t0, t, side, entry, sl, tp, exit_price, reason) -> dict:
    return {"entry_time": win.index[t0], "exit_time": win.index[t],
            "direction": "long" if side > 0 else "short",
            "entry": entry, "sl": sl, "tp": tp, "exit_price": exit_price,
            "exit_reason": reason, "bars_held": t - t0,
            "pnl_gross": side * (exit_price - entry)}


def summarise(tr: list[dict], label: str) -> dict:
    if not tr:
        return {"config": label, "n": 0}
    r = np.array([t["r_net"] for t in tr])
    w, l = r[r > 0], r[r <= 0]
    eq = r.cumsum()
    return {"config": label, "n": len(r), "win%": 100 * len(w) / len(r),
            "avg_R": r.mean(), "tot_R": r.sum(),
            "gross_R": float(np.mean([t["r_gross"] for t in tr])),
            "med_RR": float(np.median([t["rr"] for t in tr])),
            "PF": float(w.sum() / -l.sum()) if l.sum() < 0 else float("inf"),
            "maxDD_R": float((np.maximum.accumulate(eq) - eq).max()),
            "tp%": 100 * sum(t["exit_reason"] == "TP" for t in tr) / len(r),
            "sl%": 100 * sum(t["exit_reason"] == "SL" for t in tr) / len(r)}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbols", default="all")
    p.add_argument("--tol", default="0.05,0.10,0.20",
                   help="level proximity, as a fraction of the previous day's range")
    p.add_argument("--target", default="range,swing")
    p.add_argument("--buf", type=float, default=0.02, help="stop buffer, same units")
    p.add_argument("--spread-mult", type=float, default=1.0)
    p.add_argument("--no-confirm", action="store_true",
                   help="drop the sneaky-candle colour confirmation")
    p.add_argument("--out", default="output/sp2")
    p.add_argument("--min-n", type=int, default=25)
    p.add_argument("--hold-days", type=int, default=0,
                   help="extra sessions to hold past the entry day (steelman)")
    a = p.parse_args()

    symbols = list(SPREADS) if a.symbols == "all" else a.symbols.split(",")
    rows, all_tr = [], []
    for sym in symbols:
        try:
            m15 = load_m15(sym)
        except FileNotFoundError:
            print(f"skip {sym}", file=sys.stderr)
            continue
        levels = build_levels(m15)
        for tol in [float(x) for x in a.tol.split(",")]:
            for tgt in a.target.split(","):
                tr = backtest(m15, levels, tol, tgt, a.buf,
                              SPREADS[sym] * a.spread_mult, not a.no_confirm,
                              hold_days=a.hold_days)
                for t in tr:
                    t.update(symbol=sym, tol=tol, target=tgt)
                all_tr += tr
                s = summarise(tr, f"{sym:9s} tol={tol:<5} tgt={tgt}")
                s.update(symbol=sym, tol=tol, target=tgt)
                rows.append(s)

    res = pd.DataFrame(rows)
    res = res[res["n"] >= a.min_n].sort_values("avg_R", ascending=False)
    pd.set_option("display.width", 220)
    cols = ["config", "n", "win%", "tp%", "sl%", "med_RR", "avg_R", "gross_R",
            "tot_R", "PF", "maxDD_R"]
    print(f"\n=== Sneaky Pivot v2 (transcript rules) | spread x{a.spread_mult} "
          f"| confirm={not a.no_confirm} ===")
    print(res[cols].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    if len(res):
        print(f"\nconfigs {len(res)}   trades {len(all_tr)}   "
              f"mean avg_R {res.avg_R.mean():+.4f}   "
              f"positive {(res.avg_R > 0).sum()}/{len(res)}")
    res.to_csv(f"{a.out}_summary.csv", index=False)
    pd.DataFrame(all_tr).to_csv(f"{a.out}_trades.csv", index=False)
    print(f"wrote {a.out}_summary.csv / _trades.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
