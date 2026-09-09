"""Robustness verification of the fade-the-high SHORT edge (Option 1 protocol).

Signal bar t: green candle (close>open) after a red candle (close<open).
Trade: SELL LIMIT placed around the green candle's high, targeting a drop.

Entry   = high[t] + entry_off * range        (entry_off ~ 0.0..0.2)
SL      = entry + sl_mult * range
TP      = entry - tp_mult * range
range   = high[t] - low[t]

Fill: a sell LIMIT triggers when price RISES to entry on a later bar (price must
come back up to our limit). Gap-above fills at the open (worse for a short).

Research-only. Train/test split reported per (sl_mult, tp_mult, entry_off).
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


def run(df, sl_mult=0.5, tp_mult=0.5, entry_off=0.0, max_hold=None):
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
            if highs[t] >= open_pos["sl"]:
                trades.append({**open_pos, "exit_time": idx[t], "exit_price": open_pos["sl"],
                               "exit_reason": "SL"})
                open_pos = None
            elif lows[t] <= open_pos["tp"]:
                trades.append({**open_pos, "exit_time": idx[t], "exit_price": open_pos["tp"],
                               "exit_reason": "TP"})
                open_pos = None
            elif max_hold and t - open_pos["entry_idx"] >= max_hold:
                trades.append({**open_pos, "exit_time": idx[t], "exit_price": closes[t],
                               "exit_reason": "TIME"})
                open_pos = None

        if open_pos is not None:
            continue

        if not (closes[t] > opens[t] and closes[t - 1] < opens[t - 1]):
            continue
        rng = float(highs[t] - lows[t])
        if rng <= 0:
            continue

        entry = float(highs[t]) + entry_off * rng
        sl = entry + sl_mult * rng
        tp = entry - tp_mult * rng
        if not (math.isfinite(entry) and sl > entry and entry > tp):
            continue

        for f in range(t + 1, len(df)):
            if highs[f] >= entry:  # price must rise back to the limit
                fill = max(entry, opens[f])  # gap-up fills at the open (worse)
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


def metrics(trades):
    closed = [x for x in trades if x["exit_reason"] != "OPEN"]
    if not closed:
        return 0.0, 0.0, 0, 0.0
    wins = sum(1 for x in closed if x["exit_reason"] == "TP")
    rs = [(x["entry"] - x["exit_price"]) / (x["sl"] - x["entry"]) for x in closed]
    m, t, n = tstat(rs)
    return (m or 0.0), (t or 0.0), n, 100.0 * wins / len(closed)


def main():
    for csv, name in [
        (ROOT / "data/processed/XAUUSDc_M5_broker.csv", "GOLD"),
        (ROOT / "data/processed/BTCUSDc_M5_broker.csv", "BTC "),
    ]:
        if not csv.exists():
            continue
        full = load_m5(csv)
        cut = int(len(full) * 0.7)
        train, test = full.iloc[:cut], full.iloc[cut:]

        # 1) plateau map on TRAIN for the default entry_off=0
        print(f"\n=== {name} TRAIN plateau (entry at high, R / win% / n) ===")
        print("       tp0.5       tp1.0       tp1.5       tp2.0")
        for sl in (0.25, 0.5, 1.0):
            cells = []
            for tp in (0.5, 1.0, 1.5, 2.0):
                m, _, n, w = metrics(run(train, sl_mult=sl, tp_mult=tp))
                cells.append(f"{m:+.3f}/{w:.0f}%/{n}")
            print(f"sl{sl:<4} " + "  ".join(f"{c:<22}" for c in cells))

        # 2) best train geometry, report OOS
        best = None
        for sl in (0.25, 0.5, 1.0):
            for tp in (0.5, 1.0, 1.5, 2.0):
                for off in (0.0, 0.1, 0.2):
                    m, t, n, _ = metrics(run(train, sl, tp, off))
                    if n >= 100 and (best is None or t > best[0]):
                        best = (t, sl, tp, off, m, n)
        t, sl, tp, off, m, n = best
        tm, tt, tn, tw = metrics(run(test, sl, tp, off))
        print(f"\n  best on TRAIN: sl{sl} tp{tp} off{off} -> R {m:+.3f} t={t:+.2f} n={n}")
        print(f"  OUT-OF-SAMPLE:                R {tm:+.3f} t={tt:+.2f} n={tn} win {tw:.1f}%")
        # fixed geometry 0.5/0.5/0 for reference
        gm, gt, gn, gw = metrics(run(train, 0.5, 0.5, 0.0))
        gm2, gt2, gn2, gw2 = metrics(run(test, 0.5, 0.5, 0.0))
        print(f"  REF sl0.5 tp0.5 off0 TRAIN: R {gm:+.3f} t={gt:+.2f} n={gn} | TEST: R {gm2:+.3f} t={gt2:+.2f} n={gn2}")


if __name__ == "__main__":
    main()
