"""Backtest the live breakout strategy on a new market before it trades.

    python scripts/backtest_market.py --config config/config-eurjpy-backtest.toml \\
        --csv data/processed/EURJPYc_M5_broker.csv [--report output/eurjpy_backtest.txt]

Uses broker data from fetch_broker_history.py --spec (prices + spec sidecar)
and the SAME engine and [strategy] settings the live bot would run. Every
result is net of the broker's median spread.

Pre-registered rows (fixed before the data was fetched, quick task
20261110-scorecard-eurjpy). Do not add rows after seeing results:
  1. long  rr1.0
  2. short rr1.0
  3. both  rr1.0
  4. both  rr1.0 + VIX direction (band 10, 50-day MA), the setting
     config-eurjpy.toml would use; skipped if VIX cannot be fetched

PASS needs all of: net average R > 0, t >= 2.0 over the full span, AND a
positive average in both the first and the second half of the period. With 4
rows tried, luck alone clears t >= 2 somewhere roughly 1 time in 6, so a pass
is "worth a demo-sized live trial", not "proven".

Read-only research: places nothing, changes no config.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from trading_bot.backtest.engine import run_backtest  # noqa: E402
from trading_bot.config import load_config  # noqa: E402
from trading_bot.data.loader import base_symbol, load_instrument_spec  # noqa: E402

MIN_T = 2.0


def load_m5(csv: Path) -> pd.DataFrame:
    df = pd.read_csv(csv, parse_dates=["time"]).set_index("time")
    return df[["open", "high", "low", "close"]].astype(float)


def net_r(t: dict, spread_price: float) -> float:
    """R of one closed trade after one spread payment, sign-correct by side."""
    if t["direction"] == "long":
        risk = t["entry"] - t["sl"]
        gross = t["exit_price"] - t["entry"]
    else:
        risk = t["sl"] - t["entry"]
        gross = t["entry"] - t["exit_price"]
    if risk <= 0:
        return 0.0
    return (gross - spread_price) / risk


def tstat(rs) -> float | None:
    n = len(rs)
    if n < 2:
        return None
    sd = float(np.std(rs, ddof=1))
    return float(np.mean(rs)) / (sd / math.sqrt(n)) if sd > 0 else None


def row_stats(trades: list[dict], spread_price: float) -> dict | None:
    closed = [t for t in trades if t["exit_reason"] != "OPEN"]
    if len(closed) < 10:
        return None
    rs = np.array([net_r(t, spread_price) for t in closed])
    times = pd.to_datetime([t["entry_time"] for t in closed])
    mid = times.min() + (times.max() - times.min()) / 2
    first, second = rs[times < mid], rs[times >= mid]
    cum = np.cumsum(rs)
    dd = float((np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum).max())
    streak = worst = 0
    for r in rs:
        streak = streak + 1 if r < 0 else 0
        worst = max(worst, streak)
    gw, gl = rs[rs > 0].sum(), -rs[rs < 0].sum()
    w30 = np.convolve(rs, np.ones(30) / 30, "valid") if len(rs) >= 30 else np.array([])
    out = {
        "n": len(rs), "win": float((rs > 0).mean() * 100), "avg": float(rs.mean()),
        "t": tstat(rs), "pf": float(gw / gl) if gl > 0 else float("inf"),
        "avg1": float(first.mean()) if len(first) else float("nan"),
        "avg2": float(second.mean()) if len(second) else float("nan"),
        "dd": dd, "streak": worst,
        "p5_30": float(np.percentile(w30, 5)) if len(w30) else float("nan"),
        "risk_med": float(np.median([abs(t["entry"] - t["sl"]) for t in closed])),
    }
    out["pass"] = bool(out["avg"] > 0 and (out["t"] or 0) >= MIN_T
                       and out["avg1"] > 0 and out["avg2"] > 0)
    return out


def vix_bullishness(index: pd.DatetimeIndex, window: int = 50) -> pd.Series | None:
    """Daily VIX risk-on reading (0-100) mapped onto the bars, one-day lag."""
    try:
        from trading_bot.news import live_sentiment
        from trading_bot.news.fear_greed import map_to_bars

        daily = live_sentiment._load("vix", str(ROOT / "data/processed/vix.json"), refresh=True)
        bull = live_sentiment.to_bullishness("vix", daily, window).dropna()
        return map_to_bars(bull, index)
    except Exception as exc:  # noqa: BLE001
        print(f"(VIX unavailable, row 4 skipped: {type(exc).__name__}: {exc})")
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--spec", default=None, help="default: <csv>.spec.json")
    ap.add_argument("--report", default=None, help="also write the output here")
    a = ap.parse_args(argv)

    cfg = load_config(a.config)
    csv = Path(a.csv)
    spec = load_instrument_spec(a.spec or csv.with_suffix(".spec.json"))
    if base_symbol(cfg.data.symbol) != base_symbol(spec.symbol):
        print(f"error: config symbol {cfg.data.symbol} != spec symbol {spec.symbol}")
        return 1
    st = cfg.strategy
    sl_buffer = st.sl_buffer_points * spec.point if st.sl_buffer_points > 0 else st.sl_buffer
    df = load_m5(csv)

    lines: list[str] = []
    say = lines.append
    say(f"== {spec.symbol} backtest ({csv.name}) ==")
    say(f"bars={len(df):,}  {df.index[0]} -> {df.index[-1]}  "
        f"({(df.index[-1] - df.index[0]).days} days)")
    say(f"strategy: fractal {st.fractal_left}/{st.fractal_right}  lookback {st.sr_lookback}  "
        f"rr {st.rr_multiple}  sl_buffer {sl_buffer:g}  one slot")
    say(f"spread: median {spec.spread_points:g} points = {spec.spread_price:g} price, "
        f"charged once per trade  | digits {spec.digits}  account {spec.account_currency}")
    say("")
    say(f"{'row':<26}{'n':>5}{'win%':>7}{'avgR':>8}{'t':>7}{'PF':>6}"
        f"{'1st half':>10}{'2nd half':>10}{'maxDD':>7}{'streak':>7}  verdict")

    common = dict(fractal_left=st.fractal_left, fractal_right=st.fractal_right,
                  sr_lookback=st.sr_lookback, sl_buffer=sl_buffer,
                  rr_multiple=st.rr_multiple, max_concurrent=1)
    rows = [("1 long  rr1.0", dict(direction="long")),
            ("2 short rr1.0", dict(direction="short")),
            ("3 both  rr1.0", dict(direction="both"))]
    vix = vix_bullishness(df.index)
    if vix is not None:
        rows.append(("4 both  rr1.0 + VIX b10", dict(direction="both", sentiment=vix,
                                                     sentiment_band=10.0)))
    results = {}
    for label, kw in rows:
        s = row_stats(run_backtest(df, **common, **kw), spec.spread_price)
        results[label] = s
        if s is None:
            say(f"{label:<26}  fewer than 10 closed trades")
            continue
        t = f"{s['t']:+.2f}" if s["t"] is not None else "  n/a"
        say(f"{label:<26}{s['n']:>5}{s['win']:>7.1f}{s['avg']:>+8.3f}{t:>7}{s['pf']:>6.2f}"
            f"{s['avg1']:>+10.3f}{s['avg2']:>+10.3f}{s['dd']:>6.1f}R{s['streak']:>7}  "
            f"{'PASS' if s['pass'] else 'fail'}")

    passed = [k for k, s in results.items() if s and s["pass"]]
    say("")
    if passed:
        best = max(passed, key=lambda k: results[k]["t"])
        s = results[best]
        say(f"RESULT: {best.strip()} passes. Worth a minimum-lot live trial, not proven.")
        say(f"scorecard reference: win {s['win']:.1f}%  avg {s['avg']:+.3f}R  "
            f"maxDD {s['dd']:.1f}R  streak {s['streak']}  30-trade p5 {s['p5_30']:+.3f}")
    else:
        say("RESULT: no row passes. Do not trade this market with real money.")
    med = next((s["risk_med"] for s in results.values() if s), None)
    if med:
        say(f"(median stop distance {med:g} price; spread is {spec.spread_price / med * 100:.1f}% "
            f"of a typical stop)")

    text = "\n".join(lines)
    print(text)
    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(text + "\n", encoding="utf-8")
        print(f"\nsaved -> {a.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
