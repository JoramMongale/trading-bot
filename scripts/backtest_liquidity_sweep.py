"""Session ORB / liquidity-sweep backtest driver (research).

This strategy enters at the NEXT BAR OPEN after a confirmed sweep — an entry
price not known at arm time, so it does NOT fit run_backtest's pending-order
model. It has its own session loop built on the pure detection in
trading_bot/strategy/liquidity_sweep.py, honouring the engine's conventions
where they apply (SL before TP on the same bar; OPEN exit at the last close).

Research only. Falsification battery (random-time control, train/test split,
monthly breakdown) is appended in falsify_liquidity_sweep.py.
"""

import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from trading_bot.strategy.liquidity_sweep import detect_sweeps, session_range


def load_m5(csv: Path) -> pd.DataFrame:
    df = pd.read_csv(csv, parse_dates=["time"]).set_index("time")
    return df[["open", "high", "low", "close"]]


def backtest_sweep(
    df,
    range_win=(0, 6),
    sweep_win=(7, 9),
    kind="breakout",
    rr=1.5,
    sl_pct=0.001,
    max_hold=None,
    direction="both",
):
    """Session strategy over ``df``.

    A confirmed sweep enters at the NEXT bar open. SL sits beyond the swept
    reference level on the far side of the trade; TP = entry +/- rr*(sl gap),
    i.e. rr_multiple scales reward over the same risk distance used everywhere
    else in this project.

    kind="breakout":  up-sweep -> long (SL below range_low), down-sweep -> short.
    kind="failed":    the reversal direction is in setup_dir already (long after
                      a failed down-sweep etc.); SL beyond the FAILED level on
                      the far side.

    direction restricts which sweep side is taken ("long"/"short"/"both").
    """
    rng = session_range(df, *range_win)
    det = detect_sweeps(rng, kind, *sweep_win)

    closes = df["close"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    idx = df.index
    last = len(df) - 1

    setup = det["setup"].values
    sdir = det["setup_dir"].values
    r_high = det["range_high"].values
    r_low = det["range_low"].values

    trades = []
    open_pos = None
    traded_day = None

    for t in range(len(df)):
        day = idx[t].normalize()
        # manage open position first (SL before TP on the same bar)
        if open_pos is not None:
            d = open_pos["dir"]
            adverse = lows[t] if d > 0 else highs[t]
            favourable = highs[t] if d > 0 else lows[t]
            if d > 0 and adverse <= open_pos["sl"]:
                open_pos.update(exit_time=idx[t], exit_price=open_pos["sl"], exit_reason="SL")
                trades.append(open_pos); open_pos = None
            elif d < 0 and adverse >= open_pos["sl"]:
                open_pos.update(exit_time=idx[t], exit_price=open_pos["sl"], exit_reason="SL")
                trades.append(open_pos); open_pos = None
            elif d > 0 and favourable >= open_pos["tp"]:
                open_pos.update(exit_time=idx[t], exit_price=open_pos["tp"], exit_reason="TP")
                trades.append(open_pos); open_pos = None
            elif d < 0 and favourable <= open_pos["tp"]:
                open_pos.update(exit_time=idx[t], exit_price=open_pos["tp"], exit_reason="TP")
                trades.append(open_pos); open_pos = None
            elif max_hold and t - open_pos["entry_idx"] >= max_hold:
                open_pos.update(exit_time=idx[t], exit_price=closes[t], exit_reason="TIME")
                trades.append(open_pos); open_pos = None
            if open_pos is not None:
                continue

        if not bool(setup[t]):
            continue
        if day == traded_day:
            continue  # one trade per day
        if direction == "long" and sdir[t] < 0:
            continue
        if direction == "short" and sdir[t] > 0:
            continue
        if t + 1 >= len(df):
            break  # no next bar to open at

        side = int(sdir[t])  # +1 long, -1 short
        # Entry at next bar open. SL anchors to the level THIS trade is defined
        # against — the boundary the move actually swept:
        #   breakout  long after UP-sweep of range_high   -> SL below range_high
        #             short after DN-sweep of range_low   -> SL above range_low
        #   failed    long after failed DN-sweep of range_low -> SL below range_low
        #             short after failed UP-sweep of range_high-> SL above range_high
        # i.e. a long's SL is below the swept level; a short's is above it. The
        # swept level for a long breakout is range_high; for a long failed
        # reversal it is range_low (the level the down-move bounced off).
        entry = float(opens[t + 1])
        swept_high = (side > 0 and kind == "breakout") or (side < 0 and kind == "failed")
        anchor = r_high[t] if swept_high else r_low[t]
        if side > 0:
            sl = float(anchor) * (1 - sl_pct)
        else:
            sl = float(anchor) * (1 + sl_pct)
        risk = (entry - sl) if side > 0 else (sl - entry)
        if risk <= 0 or not math.isfinite(risk):
            continue
        tp = entry + rr * risk if side > 0 else entry - rr * risk
        open_pos = {
            "entry_time": idx[t + 1], "entry_idx": t + 1,
            "entry": entry, "sl": sl, "tp": tp, "dir": side,
            "exit_time": None, "exit_price": None, "exit_reason": None,
        }
        traded_day = day

    if open_pos is not None:
        open_pos.update(exit_time=idx[last], exit_price=closes[last], exit_reason="OPEN")
        trades.append(open_pos)
    return trades


def tstat(rs):
    n = len(rs)
    if n < 2:
        return None, None, n
    m = sum(rs) / n
    var = sum((r - m) ** 2 for r in rs) / (n - 1)
    return m, m / math.sqrt(var / n), n


def summarize(trades, label):
    closed = [t for t in trades if t["exit_reason"] != "OPEN"]
    if not closed:
        print(f"{label:<26} n=0")
        return None
    wins = sum(1 for t in closed if t["exit_reason"] == "TP")
    rs = []
    gw = gl = 0.0
    for t in closed:
        if t["dir"] > 0:
            r = (t["exit_price"] - t["entry"]) / (t["entry"] - t["sl"])
        else:
            r = (t["entry"] - t["exit_price"]) / (t["sl"] - t["entry"])
        rs.append(r)
        if r > 0:
            gw += r
        else:
            gl += -r
    m, t, n = tstat(rs)
    pf = gw / gl if gl > 0 else float("inf")
    print(f"{label:<26} n={n:>4} win={100*wins/n:5.1f}%  R {m:+.4f}  t={t:+.2f}  PF {pf:.2f}")
    return m


def main():
    for csv, name in [
        (ROOT / "data/processed/XAUUSDc_M5_broker.csv", "GOLD"),
        (ROOT / "data/processed/BTCUSDc_M5_broker.csv", "BTC "),
    ]:
        if not csv.exists():
            continue
        df = load_m5(csv)
        print(f"\n== {name} ==")
        for kind in ("breakout", "failed"):
            for rr in (1.0, 1.5, 2.0):
                trades = backtest_sweep(df, kind=kind, rr=rr)
                summarize(trades, f"{kind} rr{rr}")
        # London opening-range (07:00-07:30) as the reference instead of Asian
        trades = backtest_sweep(df, range_win=(7, 8), sweep_win=(8, 10), kind="breakout", rr=1.5)
        summarize(trades, "LonOR 7-8/8-10 brk")
        # NY-window sweep on the Asian range
        trades = backtest_sweep(df, range_win=(0, 6), sweep_win=(12, 14), kind="breakout", rr=1.5)
        summarize(trades, "AsiaR/NYsweep brk")


if __name__ == "__main__":
    main()
