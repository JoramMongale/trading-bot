"""Measure whether a Crypto Fear & Greed sentiment DIRECTION filter improves
Bitcoin's both-direction single-slot edge, through the REAL shared engine
(run_backtest, direction="both", sentiment=...).

Grid (pre-registered, quick task 20260928-btc-fear-greed, all on the real
broker-native BTCUSDc M5 file, max_concurrent=1 -- the single slot):
  controls  long / short / both at rr=1.0, NO filter   (the anchors the gated
            rows must beat; expected to reproduce the scalper cross-check)
  gated     both rr1.0 with sentiment band sweep {5,10,15,20,25}  (N=5 -- the
            search whose best |t| the falsification battery judges against
            best-of-5 noise)
  legs      long/short decomposition under the both (no fng) row and every
            gated both row (quantifies the direction-split effect of the gate)

Sentiment semantics: the F&G index is 0 = extreme fear, 100 = extreme greed.
"Bullish" (>= 50+band) permits ONLY longs, "bearish" (<= 50-band) permits ONLY
shorts, neutral permits both. No-lookahead: map_to_bars shifts the daily series
by one day then forward-fills onto the M5 index, so a bar only ever sees the
most recent COMPLETED daily value.

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
from trading_bot.news.fear_greed import load_fear_greed, map_to_bars


def load_m5(csv: Path) -> pd.DataFrame:
    df = pd.read_csv(csv, parse_dates=["time"]).set_index("time")
    return df[["open", "high", "low", "close"]]


def run_config(df, direction, rr=1.0, sentiment=None, band=10.0):
    """One engine run at the given direction, exit knob and sentiment gate.

    The engine's defaults (fractal_left=2, fractal_right=2, sr_lookback=60,
    sl_buffer=0.01, max_concurrent=1) match config-btc.toml's [strategy], so
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


def print_grid(df, sent):
    header = (f"{'label':<24} {'n':>5}  {'win%':>7}  {'R':>8}  {'t':>6}  "
              f"{'PF':>6}  avg_hold")
    print(header)
    rows = [
        ("long   rr1.0 (no fng) ", dict(direction="long",  rr=1.0, sentiment=None)),
        ("short  rr1.0 (no fng) ", dict(direction="short", rr=1.0, sentiment=None)),
        ("both   rr1.0 (no fng) ", dict(direction="both",  rr=1.0, sentiment=None)),
        ("both   rr1.0 fng b5   ", dict(direction="both",  rr=1.0, sentiment=sent, band=5.0)),
        ("both   rr1.0 fng b10  ", dict(direction="both",  rr=1.0, sentiment=sent, band=10.0)),
        ("both   rr1.0 fng b15  ", dict(direction="both",  rr=1.0, sentiment=sent, band=15.0)),
        ("both   rr1.0 fng b20  ", dict(direction="both",  rr=1.0, sentiment=sent, band=20.0)),
        ("both   rr1.0 fng b25  ", dict(direction="both",  rr=1.0, sentiment=sent, band=25.0)),
    ]
    for label, kw in rows:
        trades = run_config(df, **kw)
        summarize(trades, label)
        if label.startswith("both"):
            summarize_leg(trades, "long", f"  leg long  ({label.strip()})")
            summarize_leg(trades, "short", f"  leg short ({label.strip()})")


def main():
    btc = ROOT / "data/processed/BTCUSDc_M5_broker.csv"
    if not btc.exists():
        raise SystemExit(
            f"missing BTC data file: {btc}\n"
            "cannot measure the pre-registered grid without the real broker "
            "bars")

    df = load_m5(btc)
    daily = load_fear_greed(cache_path=ROOT / "data/processed/fear_greed.json")
    sent = map_to_bars(daily, df.index)

    print("== BTC F&G sentiment direction-filter grid "
          "(BTCUSDc_M5_broker.csv) ==")
    print(f"bars={len(df)}  {df.index[0]} -> {df.index[-1]}  "
          f"(~100k broker-native bars)")
    print(f"F&G daily series: {len(daily)} days, "
          f"{daily.index[0].date()} -> {daily.index[-1].date()} "
          f"(mapped onto M5 with shift(1) no-lookahead)")
    print("engine params: fractal_left=2 fractal_right=2 sr_lookback=60 "
          "sl_buffer=0.01 max_concurrent=1 (engine defaults = "
          "config-btc.toml [strategy]); sentiment gate per row")
    print("grid: controls long/short/both rr1.0 (no fng) ; gated both rr1.0 "
          "with band sweep {5,10,15,20,25} (N=5 gated configs)")
    print_grid(df, sent)


if __name__ == "__main__":
    main()
