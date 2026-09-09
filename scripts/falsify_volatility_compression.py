"""Falsification battery for the volatility compression/expansion strategy.

Runs the REAL session driver through:
1. Bar/slot coverage — confirm trades span the whole series.
2. Train/test 70/30 split.
3. Random-squeeze control — trigger on band breaks WITHOUT the squeeze
   requirement (plain Bollinger breakout), to test whether the COMPRESSION
   state adds anything over a band-breakout that makes no regime claim.
4. Monthly R breakdown.
"""

import random
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from backtest_volatility_compression import backtest_vol, load_m5, summarize
from trading_bot.strategy.volatility_compression import bollinger, detect_squeezes


def run_split(csv, name):
    full = load_m5(csv)
    cut = int(len(full) * 0.7)
    train, test = full.iloc[:cut], full.iloc[cut:]
    print(f"\n== {name} train/test 70/30 ==")
    for pct in (0.1, 0.2):
        for rr in (1.0, 2.5):
            summarize(backtest_vol(train, pct=pct, rr=rr), f"pct{pct} rr{rr} train")
            summarize(backtest_vol(test, pct=pct, rr=rr), f"pct{pct} rr{rr} TEST ")

    trades = backtest_vol(full, pct=0.2, rr=1.0)
    if trades:
        first = trades[0]["entry_time"]
        last_e = max(x["exit_time"] for x in trades)
        frac = len(full.index[:full.index.get_loc(last_e) + 1]) / len(full)
        print(f"\ncoverage pct0.2 rr1.0: first {first}, last exit {last_e} "
              f"-> {100*frac:.0f}% of data")


def run_random_control(csv, name):
    """Squeeze vs no-squeeze: run a plain Bollinger band-breakout (no squeeze
    filter) with the same SL/TP. If the no-squeeze version matches or beats the
    squeezed one, the compression state adds nothing."""
    full = load_m5(csv)
    print(f"\n== {name} squeeze vs plain band-breakout control ==")
    summarize(backtest_vol(full, pct=0.2, rr=1.0), "SQUEEZED  pct0.2 rr1.0")

    # plain band breakout: replace squeeze filter with "always squeezed"
    def no_squeeze(df, k=100, pct=0.2, period=20, n_std=2.0, rr=1.0, **kw):
        from trading_bot.strategy.volatility_compression import bollinger
        bb = bollinger(df, period, n_std)
        out = bb.copy()
        out["squeeze"] = True
        out["setup"] = False
        out["setup_dir"] = 0
        close = out["close"]
        up = close > out["bb_upper"]
        dn = close < out["bb_lower"]
        # first break after warm-up only, long/short
        for ts in out.index:
            if up.loc[ts] and pd.notna(out["bb_upper"].loc[ts]):
                out.loc[ts, "setup"] = True; out.loc[ts, "setup_dir"] = 1
            elif dn.loc[ts] and pd.notna(out["bb_lower"].loc[ts]):
                out.loc[ts, "setup"] = True; out.loc[ts, "setup_dir"] = -1
        return out

    # replicate the driver's fill/exit on the no_squeeze detection
    import backtest_volatility_compression as bvc
    import numpy as np
    df = full
    det = no_squeeze(df)
    closes = df["close"].values; opens = df["open"].values
    highs = df["high"].values; lows = df["low"].values
    idx = df.index; last = len(df) - 1
    setup = det["setup"].values; sdir = det["setup_dir"].values
    mid = det["bb_mid"].values
    trades = []; open_pos = None
    for t in range(len(df)):
        if open_pos is not None:
            d = open_pos["dir"]
            if (d > 0 and lows[t] <= open_pos["sl"]) or (d < 0 and highs[t] >= open_pos["sl"]):
                open_pos.update(exit_price=open_pos["sl"], exit_reason="SL"); trades.append(open_pos); open_pos = None
            elif (d > 0 and highs[t] >= open_pos["tp"]) or (d < 0 and lows[t] <= open_pos["tp"]):
                open_pos.update(exit_price=open_pos["tp"], exit_reason="TP"); trades.append(open_pos); open_pos = None
            if open_pos is not None:
                continue
        if not bool(setup[t]) or t + 1 >= len(df):
            continue
        side = int(sdir[t]); entry = float(opens[t + 1])
        anchor = float(mid[t])
        sl = anchor * 0.999 if side > 0 else anchor * 1.001
        risk = (entry - sl) if side > 0 else (sl - entry)
        if risk <= 0: continue
        tp = entry + risk if side > 0 else entry - risk
        open_pos = {"entry_time": idx[t+1], "entry_idx": t+1, "entry": entry,
                    "sl": sl, "tp": tp, "dir": side, "exit_time": None,
                    "exit_price": None, "exit_reason": None}
    if open_pos is not None:
        open_pos.update(exit_time=idx[last], exit_price=closes[last], exit_reason="OPEN")
        trades.append(open_pos)
    summarize(trades, "PLAIN breakout (no squeeze)")


def run_monthly(csv, name):
    full = load_m5(csv)
    print(f"\n== {name} monthly R (pct0.2 rr1.0) ==")
    trades = backtest_vol(full, pct=0.2, rr=1.0)
    from backtest_volatility_compression import tstat
    by_month = {}
    for x in trades:
        if x["exit_reason"] == "OPEN": continue
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
        run_random_control(csv, name)
        run_monthly(csv, name)


if __name__ == "__main__":
    main()
