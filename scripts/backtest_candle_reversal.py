"""Measure the user's candle-reversal strategy before any live wiring.

Spec (from user, 2026-08-28):
  Signal bar t: bullish candle after a bearish candle
      green[t] = close[t] > open[t]
      red[t-1] = close[t-1] < open[t-1]
  Entry   = high[t]                 (pending Buy Stop at the top of the top wick)
  SL      = low[t]                  (below the bottom wick)
  TP      = entry + TP_MULT * (high[t] - low[t])     # TP_MULT = 2.5 per user 2026-08-28
  Execution: Buy Stop armed at close of bar t, fills on a later bar whose
      high >= entry (gap-open fills at the open, the worse price). SL before TP
      on the same bar. One position at a time.

Research-only measurement. Not wired into the live engine or run_backtest.
"""

TP_MULT = 2.5

import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def load_m5(csv: Path) -> pd.DataFrame:
    df = pd.read_csv(csv, parse_dates=["time"]).set_index("time")
    return df[["open", "high", "low", "close"]]


def run(csv: Path, min_pullback: int = 0, at_support: bool = False,
        tp_mult: float = TP_MULT):
    """Backtest the candle reversal. min_pullback>0 requires that many prior
    red candles; at_support requires the signal low within 0.1% of the trailing
    60-bar swing support."""
    df = load_m5(csv)

    # Optional swing-support context (confirmed, no lookahead) reusing the
    # project's pure swing/level machinery.
    if at_support:
        from trading_bot.strategy.levels import support_resistance
        from trading_bot.strategy.swings import detect_swings
        lev = support_resistance(detect_swings(df, 2, 2), 60)
        support = lev["support"]
    else:
        support = pd.Series(float("nan"), index=df.index)

    open_pos = None  # dict entry_idx, entry, sl, tp
    trades = []

    closes = df["close"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    idx = df.index
    last = len(df) - 1

    # Consecutive-red count ENDING at each bar (0 if that bar is green).
    red_ending = [0] * len(df)
    for t in range(1, len(df)):
        red_ending[t] = red_ending[t - 1] + 1 if closes[t] < opens[t] else 0

    for t in range(1, len(df)):
        # manage open position first (SL before TP, same-bar)
        if open_pos is not None:
            if lows[t] <= open_pos["sl"]:
                trades.append({**open_pos, "exit_time": idx[t], "exit_price": open_pos["sl"],
                               "exit_reason": "SL"})
                open_pos = None
            elif highs[t] >= open_pos["tp"]:
                trades.append({**open_pos, "exit_time": idx[t], "exit_price": open_pos["tp"],
                               "exit_reason": "TP"})
                open_pos = None

        if open_pos is not None:
            continue  # one position at a time

        # signal: green today, red yesterday
        if not (closes[t] > opens[t] and closes[t - 1] < opens[t - 1]):
            continue
        # N-bar pullback: require (min_pullback) consecutive reds ENDING at t-1
        if min_pullback > 1 and red_ending[t - 1] < min_pullback:
            continue

        entry = float(highs[t])
        sl = float(lows[t])
        tp = entry + tp_mult * (entry - sl)
        if not (math.isfinite(sl) and sl > 0 and tp > entry):
            continue

        # at_support filter: signal low near confirmed swing support
        if at_support and not (math.isfinite(support.iloc[t])
                               and lows[t] <= support.iloc[t] * 1.001):
            continue

        # armed at close of t; fill on t+1 onward when high >= entry
        for f in range(t + 1, len(df)):
            if highs[f] >= entry:
                fill = max(entry, opens[f])  # gap-open worst price
                open_pos = {"entry_time": idx[t], "entry_idx": t, "entry": fill,
                            "sl": sl, "tp": tp}
                break

    # close any position still open at end
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
    if not trades:
        print(f"{label}: 0 closed trades")
        return
    closed = [t for t in trades if t["exit_reason"] != "OPEN"]
    wins = sum(1 for t in closed if t["exit_reason"] == "TP")
    rs = []
    for t in closed:
        risk = t["entry"] - t["sl"]
        rs.append((t["exit_price"] - t["entry"]) / risk if risk else 0.0)
    m, t, n = tstat(rs)
    print(f"{label}: n={len(closed):>4}  win={100*wins/max(1,len(closed)):5.1f}%  "
          f"R {m:+.4f}  t={t:+.2f}" if m is not None else f"{label}: n={len(closed)}")


def main():
    for csv, name in [
        (ROOT / "data/processed/XAUUSDc_M5_broker.csv", "GOLD"),
        (ROOT / "data/processed/BTCUSDc_M5_broker.csv", "BTC "),
    ]:
        if not csv.exists():
            print(f"{name}: {csv.name} missing, skipping")
            continue
        print(f"\n== {name} {csv.name} ==")
        for mult, tag in [(2.5, "TP=2.5x"), (1.0, "TP=1.0x")]:
            report(run(csv, tp_mult=mult), f"pure {tag}        ")
            report(run(csv, at_support=True, tp_mult=mult), f"support {tag}    ")
            report(run(csv, min_pullback=2, tp_mult=mult), f"pullback {tag}   ")


if __name__ == "__main__":
    main()
