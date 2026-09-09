"""Measure the SHORT-side / fade mirrors of the candle-reversal signal.

Signal (unchanged): bar t green (close>open) after bar t-1 red (close<open).
The long breakout of the candle high was measured strongly negative on gold
and BTC (mean reversion). These variants test whether fading it has edge.

Variant A — Direct Reversal short:
    Entry  = pending SELL STOP at candle LOW[t]
    SL     = candle HIGH[t]
    TP     = entry - tp_mult * (high - low)

Variant B — Fade the High (sell LIMIT into the breakout):
    Entry  = pending SELL LIMIT at candle HIGH[t]
    SL     = high + 0.5 * range
    TP     = entry - 0.5 * range   (midpoint target)

Research-only. Not wired into the live engine.
"""

import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def load_m5(csv: Path) -> pd.DataFrame:
    df = pd.read_csv(csv, parse_dates=["time"]).set_index("time")
    return df[["open", "high", "low", "close"]]


def run(csv: Path, variant: str, tp_mult: float = 1.0):
    """variant: 'A_stop' (sell stop at low) or 'B_limit' (sell limit at high)."""
    df = load_m5(csv)
    closes = df["close"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    idx = df.index
    last = len(df) - 1

    open_pos = None
    trades = []

    for t in range(1, len(df)):
        if open_pos is not None:
            # short: adverse = high (>= sl), favourable = low (<= tp)
            if highs[t] >= open_pos["sl"]:
                trades.append({**open_pos, "exit_time": idx[t], "exit_price": open_pos["sl"],
                               "exit_reason": "SL"})
                open_pos = None
            elif lows[t] <= open_pos["tp"]:
                trades.append({**open_pos, "exit_time": idx[t], "exit_price": open_pos["tp"],
                               "exit_reason": "TP"})
                open_pos = None

        if open_pos is not None:
            continue

        if not (closes[t] > opens[t] and closes[t - 1] < opens[t - 1]):
            continue

        rng = float(highs[t] - lows[t])
        if rng <= 0:
            continue

        if variant == "A_stop":
            entry = float(lows[t])
            sl = float(highs[t])
            tp = entry - tp_mult * rng
        else:  # B_limit fade the high
            entry = float(highs[t])
            sl = float(highs[t]) + 0.5 * rng
            tp = float(highs[t]) - 0.5 * rng
        if not (math.isfinite(entry) and sl > entry and entry > tp):
            continue

        # fill scan: SELL STOP fills when price falls to entry; SELL LIMIT when
        # it rises to entry. Stop -> worse fill is the OPEN if it gapped below.
        for f in range(t + 1, len(df)):
            hit = lows[f] <= entry if variant == "A_stop" else highs[f] >= entry
            if hit:
                fill = min(entry, opens[f]) if variant == "A_stop" else max(entry, opens[f])
                open_pos = {"entry_time": idx[t], "entry_idx": t, "entry": fill,
                            "sl": sl, "tp": tp}
                break

    if open_pos is not None:
        trades.append({**open_pos, "exit_time": idx[last], "exit_price": closes[last],
                       "exit_reason": "OPEN"})
    return trades


def tstat(rs):
    n = len(rs)
    if n < 2:
        return None, None, n
    mean = sum(rs) / n
    var = sum((r - mean) ** 2 for r in rs) / (n - 1)
    return mean, mean / math.sqrt(var / n), n


def report(trades, label):
    closed = [t for t in trades if t["exit_reason"] != "OPEN"]
    if not closed:
        print(f"{label}: 0 closed")
        return
    wins = sum(1 for t in closed if t["exit_reason"] == "TP")
    rs = [(t["entry"] - t["exit_price"]) / (t["sl"] - t["entry"]) for t in closed]
    m, t, n = tstat(rs)
    print(f"{label}: n={n:>5}  win={100*wins/n:5.1f}%  R {m:+.4f}  t={t:+.2f}")


def main():
    for csv, name in [
        (ROOT / "data/processed/XAUUSDc_M5_broker.csv", "GOLD"),
        (ROOT / "data/processed/BTCUSDc_M5_broker.csv", "BTC "),
    ]:
        if not csv.exists():
            print(f"{name}: missing, skipping")
            continue
        print(f"\n== {name} ==")
        for variant, tag in [("A_stop", "sell-stop@low "), ("B_limit", "fade-limit@high")]:
            for mult in (1.0, 2.5):
                report(run(csv, variant, mult), f"{tag} TP={mult}x")


if __name__ == "__main__":
    main()
