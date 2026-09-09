"""HTF-aligned M5 pullback backtest driver + falsification battery (research).

Primary target: the gold account instrument (XAUUSDc). Entry at the next M5 bar
open (100% coverage, no slot starvation). SL = trigger bar low/high, TP = rr x
risk.

Falsification battery:
1. Full-sample + bar-coverage check.
2. HTF ablation control — identical M5 pullback WITHOUT the HTF gate.
3. Random-bias control — coin-flip HTF bias instead of the H4 EMA(50).
4. Train/test 70/30 split.
5. Monthly breakdown.

Research only. Nothing is a live candidate without passing this.
"""

import math
import random
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from trading_bot.strategy.htf_pullback import detect_pullbacks, htf_bias


def load_m5(csv: Path) -> pd.DataFrame:
    df = pd.read_csv(csv, parse_dates=["time"]).set_index("time")
    return df[["open", "high", "low", "close"]]


def _run_detection(df, ema_fast, ema_htf, htf_rule, use_htf, random_bias_seed=None):
    """Return a frame with setup/setup_dir columns."""
    if use_htf and random_bias_seed is None:
        return detect_pullbacks(df, ema_fast, ema_htf, htf_rule)
    out = df.copy()
    ema = out["close"].ewm(span=ema_fast, adjust=False).mean()
    out["m5_ema"] = ema
    if random_bias_seed is not None:
        # coin flip per HTF bar: +1 or -1
        rng = random.Random(random_bias_seed)
        htf_close = out["close"].resample(htf_rule).last()
        flips = pd.Series([rng.choice([-1, 1]) for _ in htf_close.index],
                          index=htf_close.index)
        flips = flips.shift(1).reindex(out.index, method="ffill")
        out["htf_bias"] = flips.fillna(0).astype(int)
    elif use_htf:
        out["htf_bias"] = htf_bias(out, ema_htf, htf_rule)
    else:  # ablation: no HTF gate -> bias always agrees
        out["htf_bias"] = 1  # placeholder; triggers derived below without gate
    close = out["close"]; open_ = out["open"]
    high = out["high"]; low = out["low"]
    ema20 = ema
    if random_bias_seed is not None or use_htf:
        long_ok = (out["htf_bias"] == 1) & (close > open_) & (low <= ema20) & ema20.notna()
        short_ok = (out["htf_bias"] == -1) & (close < open_) & (high >= ema20) & ema20.notna()
    else:  # ablation: both directions, no bias gate
        long_ok = (close > open_) & (low <= ema20) & ema20.notna()
        short_ok = (close < open_) & (high >= ema20) & ema20.notna()
    out["setup"] = long_ok | short_ok
    out["setup_dir"] = 0
    out.loc[long_ok, "setup_dir"] = 1
    out.loc[short_ok, "setup_dir"] = -1
    return out


def backtest_pullback(
    df,
    ema_fast=20,
    ema_htf=50,
    htf_rule="4h",
    rr=1.0,
    use_htf=True,
    random_bias_seed=None,
    direction="both",
):
    det = _run_detection(df, ema_fast, ema_htf, htf_rule, use_htf, random_bias_seed)
    closes = df["close"].values; opens = df["open"].values
    highs = df["high"].values; lows = df["low"].values
    idx = df.index; last = len(df) - 1
    setup = det["setup"].values; sdir = det["setup_dir"].values
    # SL anchors come from the trigger bar's own high/low (trigger_levels)
    setup_low = lows.copy(); setup_high = highs.copy()
    trades = []; open_pos = None

    for t in range(len(df)):
        if open_pos is not None:
            d = open_pos["dir"]
            if (d > 0 and lows[t] <= open_pos["sl"]) or (d < 0 and highs[t] >= open_pos["sl"]):
                open_pos.update(exit_time=idx[t], exit_price=open_pos["sl"], exit_reason="SL")
                trades.append(open_pos); open_pos = None
            elif (d > 0 and highs[t] >= open_pos["tp"]) or (d < 0 and lows[t] <= open_pos["tp"]):
                open_pos.update(exit_time=idx[t], exit_price=open_pos["tp"], exit_reason="TP")
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
        sl = float(setup_low[t]) * 0.999 if side > 0 else float(setup_high[t]) * 1.001
        risk = (entry - sl) if side > 0 else (sl - entry)
        if risk <= 0 or not math.isfinite(risk):
            continue
        tp = entry + rr * risk if side > 0 else entry - rr * risk
        open_pos = {"entry_time": idx[t+1], "entry_idx": t+1, "entry": entry,
                    "sl": sl, "tp": tp, "dir": side, "exit_time": None,
                    "exit_price": None, "exit_reason": None}

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
        print(f"{label:<34} n=0")
        return None
    wins = sum(1 for t in closed if t["exit_reason"] == "TP")
    rs = []; gw = gl = 0.0
    for t in closed:
        r = (t["exit_price"] - t["entry"]) / (t["entry"] - t["sl"]) if t["dir"] > 0 \
            else (t["entry"] - t["exit_price"]) / (t["sl"] - t["entry"])
        rs.append(r)
        if r > 0: gw += r
        else: gl += -r
    m, t, n = tstat(rs)
    pf = gw / gl if gl > 0 else float("inf")
    print(f"{label:<34} n={n:>4} win={100*wins/n:5.1f}%  R {m:+.4f}  t={t:+.2f}  PF {pf:.2f}")
    return m


def run_full(csv, name):
    full = load_m5(csv)
    cut = int(len(full) * 0.7)
    train, test = full.iloc[:cut], full.iloc[cut:]
    print(f"\n{'='*78}\n== {name} ({csv.name}) ==\n{'='*78}")

    print("-- full sample --")
    for rr in (1.0, 2.5):
        summarize(backtest_pullback(full, rr=rr, use_htf=True), f"HTF-gated  rr{rr}")
        summarize(backtest_pullback(full, rr=rr, use_htf=False), f"NO-HTF(abl) rr{rr}")

    print("-- HTF ablation control (rr1.0) --")
    summarize(backtest_pullback(full, rr=1.0, use_htf=True), "HTF EMA(50) gated  ")
    summarize(backtest_pullback(full, rr=1.0, use_htf=False), "UNFILTERED (no HTF)")

    print("-- random-bias control (rr1.0) --")
    for seed in (1, 2, 3):
        summarize(backtest_pullback(full, rr=1.0, random_bias_seed=seed), f"RANDOM HTF bias seed={seed}")

    print("-- bar coverage (HTF-gated rr1.0) --")
    trades = backtest_pullback(full, rr=1.0, use_htf=True)
    if trades:
        frac = len(full.index[:full.index.get_loc(max(x['exit_time'] for x in trades)) + 1]) / len(full)
        print(f"  {len(full)} bars; first {trades[0]['entry_time']}, last exit "
              f"{max(x['exit_time'] for x in trades)} -> {100*frac:.0f}% coverage")

    print("-- train/test 70/30 --")
    for rr in (1.0, 2.5):
        summarize(backtest_pullback(train, rr=rr), f"HTF rr{rr} TRAIN")
        summarize(backtest_pullback(test, rr=rr), f"HTF rr{rr} TEST ")

    print("-- monthly R (HTF-gated rr1.0) --")
    trades = backtest_pullback(full, rr=1.0, use_htf=True)
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
    # Primary target: the gold account instrument (XAUUSDc).
    gold = ROOT / "data/processed/XAUUSDc_M5_broker.csv"
    btc = ROOT / "data/processed/BTCUSDc_M5_broker.csv"
    if gold.exists():
        run_full(gold, "GOLD (account 161693049 XAUUSDc)")
    if btc.exists():
        run_full(btc, "BTC (for contrast)")


if __name__ == "__main__":
    main()
