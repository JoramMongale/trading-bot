"""Volatility compression/expansion backtest driver (research).

Entry at the NEXT M5 bar open after an expansion trigger (the execution model
retained from the ORB round — 100% bar coverage, no slot starvation). SL =
bb_mid at trigger time; TP = rr x risk. One trade at a time; a trigger does not
re-arm within the same squeeze (pure detection enforces this).

Research only. Falsification battery in falsify_volatility_compression.py.
"""

import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from trading_bot.strategy.volatility_compression import detect_squeezes


def load_m5(csv: Path) -> pd.DataFrame:
    df = pd.read_csv(csv, parse_dates=["time"]).set_index("time")
    return df[["open", "high", "low", "close"]]


def backtest_vol(
    df,
    k=100,
    pct=0.20,
    period=20,
    n_std=2.0,
    rr=2.5,
    sl_from_mid=True,
    max_hold=None,
    direction="both",
):
    """Run the squeeze-expansion strategy over ``df``.

    A setup (first close outside the band while squeezed) enters at the next
    bar open. SL = bb_mid of the trigger bar (a real expansion should not
    collapse back through the mean); when sl_from_mid is False the SL is the
    opposite band instead.
    """
    det = detect_squeezes(df, k=k, pct=pct, period=period, n_std=n_std)

    closes = df["close"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    idx = df.index
    last = len(df) - 1

    setup = det["setup"].values
    sdir = det["setup_dir"].values
    mid = det["bb_mid"].values
    upper = det["bb_upper"].values
    lower = det["bb_lower"].values

    trades = []
    open_pos = None

    for t in range(len(df)):
        if open_pos is not None:
            d = open_pos["dir"]
            if d > 0:
                if lows[t] <= open_pos["sl"]:
                    open_pos.update(exit_time=idx[t], exit_price=open_pos["sl"], exit_reason="SL")
                    trades.append(open_pos); open_pos = None
                elif highs[t] >= open_pos["tp"]:
                    open_pos.update(exit_time=idx[t], exit_price=open_pos["tp"], exit_reason="TP")
                    trades.append(open_pos); open_pos = None
            else:
                if highs[t] >= open_pos["sl"]:
                    open_pos.update(exit_time=idx[t], exit_price=open_pos["sl"], exit_reason="SL")
                    trades.append(open_pos); open_pos = None
                elif lows[t] <= open_pos["tp"]:
                    open_pos.update(exit_time=idx[t], exit_price=open_pos["tp"], exit_reason="TP")
                    trades.append(open_pos); open_pos = None
            if open_pos is not None and max_hold and t - open_pos["entry_idx"] >= max_hold:
                open_pos.update(exit_time=idx[t], exit_price=closes[t], exit_reason="TIME")
                trades.append(open_pos); open_pos = None
            if open_pos is not None:
                continue

        if not bool(setup[t]):
            continue
        if direction == "long" and sdir[t] < 0:
            continue
        if direction == "short" and sdir[t] > 0:
            continue
        if t + 1 >= len(df):
            break

        side = int(sdir[t])
        entry = float(opens[t + 1])
        # SL anchor: mean (default) or opposite band.
        anchor = float(mid[t]) if sl_from_mid else (
            float(upper[t]) if side < 0 else float(lower[t]))
        # Long: SL below anchor; short: SL above anchor.
        sl = anchor * 0.999 if side > 0 else anchor * 1.001
        if side > 0:
            risk = entry - sl
        else:
            risk = sl - entry
        if risk <= 0 or not math.isfinite(risk):
            continue
        tp = entry + rr * risk if side > 0 else entry - rr * risk
        open_pos = {
            "entry_time": idx[t + 1], "entry_idx": t + 1,
            "entry": entry, "sl": sl, "tp": tp, "dir": side,
            "exit_time": None, "exit_price": None, "exit_reason": None,
        }

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
        for pct in (0.1, 0.2, 0.3):
            for rr in (1.0, 2.5):
                trades = backtest_vol(df, pct=pct, rr=rr)
                summarize(trades, f"pct{pct} rr{rr}")


if __name__ == "__main__":
    main()
