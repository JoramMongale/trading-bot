"""Proper-engine falsification of the candle_reversal variant (2026-08-28).

Runs the REAL backtest engine (run_backtest) — not the research approximation —
through both protocols:

1. RANDOM-SIGNAL CONTROL: engine runs identically with a coin-flip setup column
   (via run_backtest's setup_override seam). If random triggers match or beat
   the pattern's result, the apparent edge is the engine's fill/slot mechanics,
   not predictive alpha.

2. TRAIN/TEST SPLIT: 70/30 in-sample vs out-of-sample, so a regime-localised
   result is exposed rather than accepted.

Report: R, t, win rate, PF per configuration. Research only.
"""

import math
import random
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from trading_bot.backtest.engine import run_backtest
from trading_bot.strategy.candle_reversal import detect_candle_reversal


def load_m5(csv: Path) -> pd.DataFrame:
    df = pd.read_csv(csv, parse_dates=["time"]).set_index("time")
    return df[["open", "high", "low", "close"]]


def tstat(rs):
    n = len(rs)
    if n < 2:
        return None, None, n
    mean = sum(rs) / n
    var = sum((r - mean) ** 2 for r in rs) / (n - 1)
    return mean, mean / math.sqrt(var / n), n


def summarize(trades, label):
    closed = [t for t in trades if t["exit_reason"] != "OPEN"]
    if not closed:
        print(f"{label:<26} n=0")
        return None
    wins = sum(1 for t in closed if t["exit_reason"] == "TP")
    rs = []
    gross_win = gross_loss = 0.0
    for t in closed:
        r = (t["exit_price"] - t["entry"]) / (t["entry"] - t["sl"]) if t["entry"] != t["sl"] else 0.0
        rs.append(r)
        if r > 0:
            gross_win += r
        else:
            gross_loss += -r
    m, t, n = tstat(rs)
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
    print(f"{label:<26} n={n:>6} win={100*wins/n:5.1f}%  R {m:+.4f}  t={t:+.2f}  PF {pf:.2f}")
    return m


def real_signal(df, **kw):
    return run_backtest(df, variant="candle_reversal", **kw)


def random_signal(df, seed, **kw):
    rng = random.Random(seed)
    r = df.copy()
    # naive candle_reversal detection just to learn its natural firing rate
    det = detect_candle_reversal(df)
    rate = float(det["setup"].mean())
    flips = pd.Series(
        [rng.random() < rate for _ in range(len(df))], index=df.index
    )
    return run_backtest(df, variant="candle_reversal", setup_override=flips, **kw)


def run_instrument(csv, name):
    full = load_m5(csv)
    cut = int(len(full) * 0.7)
    train, test = full.iloc[:cut], full.iloc[cut:]
    print(f"\n== {name} ({csv.name}) ==")
    print("-- pattern through the REAL engine --")
    summarize(real_signal(full), "pattern full")
    summarize(real_signal(train), "pattern train(70%)")
    summarize(real_signal(test), "pattern test(30%)")

    print("-- RANDOM-SIGNAL CONTROL (coin flips, same engine) --")
    for seed in (1, 2, 3, 4, 5):
        summarize(random_signal(full, seed), f"random seed={seed}")


def main():
    for csv, name in [
        (ROOT / "data/processed/XAUUSDc_M5_broker.csv", "GOLD"),
        (ROOT / "data/processed/BTCUSDc_M5_broker.csv", "BTC "),
    ]:
        if csv.exists():
            run_instrument(csv, name)


if __name__ == "__main__":
    main()
