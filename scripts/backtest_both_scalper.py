"""Measure the both-direction single-slot "scalper" variant of the swing S/R
breakout through the REAL shared engine (run_backtest, direction="both").

Grid (pre-registered, quick task 20260909-gold-both-scalper, all on the real
broker-native XAUUSDc M5 file, max_concurrent=1 -- the single slot):
  controls  long / short / both at rr=1.0   (the anchors the scalp rows beat)
  scalp     both rr0.5, both rr0.75, tp_from_fill at rr0.5/rr1.0,
            max_hold_bars 12/36 (1h/3h on M5) at rr1.0 and rr0.5
            (8 configs -- the search whose best |t| the falsification battery
            judges against best-of-8 noise)
  legs      long/short decomposition under the both rr1.0 and both rr0.5 rows
            (quantifies the drift asymmetry)
  BTC       secondary machinery cross-check when the BTC file is present

Research only; nothing here is a live candidate and live/engine.py is
untouched. The printed tables ARE the deliverable.
"""

import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from trading_bot.backtest.engine import run_backtest


def load_m5(csv: Path) -> pd.DataFrame:
    df = pd.read_csv(csv, parse_dates=["time"]).set_index("time")
    return df[["open", "high", "low", "close"]]


def run_config(df, direction, rr=1.0, tp_from_fill=False, max_hold_bars=None):
    """One engine run at the given direction and exit knobs. The engine's
    defaults (fractal_left=2, fractal_right=2, sr_lookback=60, sl_buffer=0.01,
    max_concurrent=1) match config-cent.toml's [strategy], so only the exit
    knobs are passed explicitly."""
    return run_backtest(
        df,
        direction=direction,
        rr_multiple=rr,
        tp_from_fill=tp_from_fill,
        max_hold_bars=max_hold_bars,
    )


def tstat(rs):
    n = len(rs)
    if n < 2:
        return None, None, n
    mean = sum(rs) / n
    var = sum((r - mean) ** 2 for r in rs) / (n - 1)
    return mean, mean / math.sqrt(var / n), n


def _r(t):
    """Per-trade r_multiple, sign-corrected per the record's own direction."""
    if t["direction"] == "long":
        risk = t["entry"] - t["sl"]
        return (t["exit_price"] - t["entry"]) / risk if risk else 0.0
    risk = t["sl"] - t["entry"]
    return (t["entry"] - t["exit_price"]) / risk if risk else 0.0


def summarize(trades, label):
    closed = [t for t in trades if t["exit_reason"] != "OPEN"]
    n = len(closed)
    if n < 2:
        print(f"{label:<24} n={n} (insufficient)")
        return None
    wins = sum(1 for t in closed if t["exit_reason"] == "TP")
    rs = []; gross_win = gross_loss = 0.0
    for t in closed:
        r = _r(t)
        rs.append(r)
        if r > 0:
            gross_win += r
        else:
            gross_loss += -r
    m, t, n = tstat(rs)
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
    holds = [t["exit_idx"] - t["entry_idx"] for t in trades]
    avg_hold = sum(holds) / len(holds) if holds else 0.0
    print(f"{label:<24} n={n:>5} win={100*wins/n:5.1f}%  R {m:+.4f}  "
          f"t={t:+.2f}  PF {pf:.2f}  avg_hold {avg_hold:.1f}")
    return m


def summarize_leg(trades, side, label):
    closed = [t for t in trades if t["exit_reason"] != "OPEN"
              and t["direction"] == side]
    n = len(closed)
    if n < 2:
        print(f"{label:<24} n={n} (insufficient)")
        return
    wins = sum(1 for t in closed if t["exit_reason"] == "TP")
    rs = [_r(t) for t in closed]
    m, t, _ = tstat(rs)
    print(f"{label:<24} n={n:>5} win={100*wins/n:5.1f}%  R {m:+.4f}  "
          f"t={t:+.2f}")


def print_grid(df):
    header = (f"{'label':<24} {'n':>5}  {'win%':>7}  {'R':>8}  {'t':>6}  "
              f"{'PF':>6}  avg_hold")
    print(header)
    rows = [
        ("long   rr1.0",         dict(direction="long",  rr=1.0)),
        ("short  rr1.0",         dict(direction="short", rr=1.0)),
        ("both   rr1.0",         dict(direction="both",  rr=1.0)),
        ("both   rr0.5",         dict(direction="both",  rr=0.5)),
        ("both   rr0.75",        dict(direction="both",  rr=0.75)),
        ("both   rr0.5 tpffill", dict(direction="both",  rr=0.5, tp_from_fill=True)),
        ("both   rr1.0 tpffill", dict(direction="both",  rr=1.0, tp_from_fill=True)),
        ("both   rr1.0 hold12",  dict(direction="both",  rr=1.0, max_hold_bars=12)),
        ("both   rr1.0 hold36",  dict(direction="both",  rr=1.0, max_hold_bars=36)),
        ("both   rr0.5 hold12",  dict(direction="both",  rr=0.5, max_hold_bars=12)),
        ("both   rr0.5 hold36",  dict(direction="both",  rr=0.5, max_hold_bars=36)),
    ]
    for label, kw in rows:
        trades = run_config(df, **kw)
        summarize(trades, label)
        if label in ("both   rr1.0", "both   rr0.5"):
            summarize_leg(trades, "long", f"  leg long  ({label})")
            summarize_leg(trades, "short", f"  leg short ({label})")


def main():
    gold = ROOT / "data/processed/XAUUSDc_M5_broker.csv"
    if not gold.exists():
        raise SystemExit(
            f"missing gold data file: {gold}\n"
            "cannot measure the pre-registered grid without the real broker "
            "bars")

    df = load_m5(gold)
    print("== GOLD grid (XAUUSDc_M5_broker.csv) ==")
    print(f"bars={len(df)}  {df.index[0]} -> {df.index[-1]}  "
          f"(100k broker-native bars)")
    print("engine params: fractal_left=2 fractal_right=2 sr_lookback=60 "
          "sl_buffer=0.01 max_concurrent=1 (engine defaults = "
          "config-cent.toml [strategy]); exit knobs per row")
    print("grid: controls long/short/both rr1.0 ; scalp both rr0.5, rr0.75, "
          "rr0.5+tp_from_fill, rr1.0+tp_from_fill, rr1.0+hold12/36, "
          "rr0.5+hold12/36 (N=8 scalp configs)")
    print_grid(df)

    btc = ROOT / "data/processed/BTCUSDc_M5_broker.csv"
    if not btc.exists():
        print("\n(BTCUSDc_M5_broker.csv not present - skipping cross-check)")
        return
    dfb = load_m5(btc)
    print(f"\n== BTC cross-check == ({btc.name})")
    print(f"bars={len(dfb)}  {dfb.index[0]} -> {dfb.index[-1]}")
    print(f"{'label':<24} {'n':>5}  {'win%':>7}  {'R':>8}  {'t':>6}  "
          f"{'PF':>6}  avg_hold")
    for label, kw in [
        ("long   rr1.0",        dict(direction="long",  rr=1.0)),
        ("short  rr1.0",        dict(direction="short", rr=1.0)),
        ("both   rr1.0",        dict(direction="both",  rr=1.0)),
        ("both   rr0.5",        dict(direction="both",  rr=0.5)),
        ("both   rr1.0 hold12", dict(direction="both",  rr=1.0, max_hold_bars=12)),
    ]:
        summarize(run_config(dfb, **kw), label)


if __name__ == "__main__":
    main()
