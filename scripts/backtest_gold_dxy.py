"""Measure whether a DXY macro-regime sentiment gate improves gold's
both-direction single-slot breakout edge, through the REAL shared engine
(run_backtest, direction="both", sentiment=...).

Grid (pre-registered, quick task 20260928-gold-dxy-sentiment-gate, all on the
real broker-native XAUUSDc M5 file, max_concurrent=1 -- the single slot):
  controls  long / short / both at rr=1.0, NO gate   (the anchors the gated
            rows must beat; expected to reproduce the scalper numbers
            long +0.0925 / short +0.0009 / both +0.0810)
  gated     both rr1.0 DXY-gated, MA window {50,200} x neutral band {0,5,10}
            (N=6 -- the search whose best |t| the falsification battery judges
            against best-of-6 noise)
  legs      long/short decomposition under the both (no dxy) row and every
            gated both row (quantifies the direction-split effect of the gate)

Regime normalization (locked pitfall): the gate operates on the FRACTIONAL
DEVIATION of DXY from its own trailing MA (never the raw index level), mapped
through to_gold_bullishness to a 0-100 scale where 50 = neutral. Weak dollar
(DXY below its MA) -> >50 -> "bullish" -> long-only; strong dollar -> <50 ->
"bearish" -> short-only; the neutral band -> both. No-lookahead: map_to_bars
shifts the daily series by one day then forward-fills onto the M5 index, so a
bar only ever sees the most recent COMPLETED daily regime.

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
from trading_bot.news.fear_greed import map_to_bars
from trading_bot.news.macro import load_dxy, to_gold_bullishness


def load_m5(csv: Path) -> pd.DataFrame:
    df = pd.read_csv(csv, parse_dates=["time"]).set_index("time")
    return df[["open", "high", "low", "close"]]


def run_config(df, direction, rr=1.0, sentiment=None, band=10.0):
    """One engine run at the given direction, exit knob and sentiment gate.

    The engine's defaults (fractal_left=2, fractal_right=2, sr_lookback=60,
    sl_buffer=0.01, max_concurrent=1) match config-cent.toml's [strategy], so
    only the direction, rr and sentiment gate are passed explicitly."""
    return run_backtest(
        df,
        direction=direction,
        rr_multiple=rr,
        sentiment=sentiment,
        sentiment_band=band,
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


def bar_mix(mapped, band=10.0):
    """(bull, bear, neutral) bar counts at the given neutral half-band.

    NaN (no completed daily regime yet) counts as neutral -- the engine's
    fail-open semantics."""
    bull = int((mapped >= 50.0 + band).sum())
    bear = int((mapped <= 50.0 - band).sum())
    neutral = int(len(mapped) - bull - bear)
    return bull, bear, neutral


def print_grid(df, dxy50, dxy200):
    header = (f"{'label':<24} {'n':>5}  {'win%':>7}  {'R':>8}  {'t':>6}  "
              f"{'PF':>6}  avg_hold")
    print(header)
    rows = [
        ("long   rr1.0 (no dxy) ", dict(direction="long",  rr=1.0, sentiment=None)),
        ("short  rr1.0 (no dxy) ", dict(direction="short", rr=1.0, sentiment=None)),
        ("both   rr1.0 (no dxy) ", dict(direction="both",  rr=1.0, sentiment=None)),
        ("both   rr1.0 dxy w50 b0 ", dict(direction="both",  rr=1.0, sentiment=dxy50,  band=0.0)),
        ("both   rr1.0 dxy w50 b5 ", dict(direction="both",  rr=1.0, sentiment=dxy50,  band=5.0)),
        ("both   rr1.0 dxy w50 b10", dict(direction="both",  rr=1.0, sentiment=dxy50,  band=10.0)),
        ("both   rr1.0 dxy w200 b0 ", dict(direction="both",  rr=1.0, sentiment=dxy200, band=0.0)),
        ("both   rr1.0 dxy w200 b5 ", dict(direction="both",  rr=1.0, sentiment=dxy200, band=5.0)),
        ("both   rr1.0 dxy w200 b10", dict(direction="both",  rr=1.0, sentiment=dxy200, band=10.0)),
    ]
    for label, kw in rows:
        trades = run_config(df, **kw)
        summarize(trades, label)
        if label.startswith("both"):
            summarize_leg(trades, "long", f"  leg long  ({label.strip()})")
            summarize_leg(trades, "short", f"  leg short ({label.strip()})")


def main():
    gold = ROOT / "data/processed/XAUUSDc_M5_broker.csv"
    if not gold.exists():
        raise SystemExit(
            f"missing gold data file: {gold}\n"
            "cannot measure the pre-registered grid without the real broker "
            "bars")

    df = load_m5(gold)
    dxy = load_dxy(cache_path=ROOT / "data/processed/dxy.json")
    dxy50 = to_gold_bullishness(dxy, 50)
    dxy200 = to_gold_bullishness(dxy, 200)
    dxy50_mapped = map_to_bars(dxy50, df.index)
    dxy200_mapped = map_to_bars(dxy200, df.index)

    b50_bull, b50_bear, b50_neu = bar_mix(dxy50_mapped, band=10.0)
    b200_bull, b200_bear, b200_neu = bar_mix(dxy200_mapped, band=10.0)

    print("== GOLD DXY regime gate grid (XAUUSDc_M5_broker.csv) ==")
    print(f"bars={len(df)}  {df.index[0]} -> {df.index[-1]}  "
          f"(~100k broker-native bars)")
    print(f"DXY daily series: {len(dxy)} days, "
          f"{dxy.index[0].date()} -> {dxy.index[-1].date()} "
          f"(mapped onto M5 with shift(1) no-lookahead)")
    print("engine params: fractal_left=2 fractal_right=2 sr_lookback=60 "
          "sl_buffer=0.01 max_concurrent=1 (engine defaults = "
          "config-cent.toml [strategy]); sentiment gate per row")
    print(f"bar mix at band=10 (bull/bear/neutral): dxy w50 = "
          f"{b50_bull}/{b50_bear}/{b50_neu} ; dxy w200 = "
          f"{b200_bull}/{b200_bear}/{b200_neu}")
    print("grid: controls long/short/both rr1.0 (no dxy) ; gated both rr1.0 "
          "dxy MA window {50,200} x neutral band {0,5,10} (N=6 gated configs)")
    print_grid(df, dxy50_mapped, dxy200_mapped)


if __name__ == "__main__":
    main()
