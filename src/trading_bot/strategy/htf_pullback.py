"""HTF-aligned M5 pullback detection — pure, research strategy.

Pure pandas/numpy — no I/O, no config, no broker imports (SAFE-01). Tests the
pervasive retail paradigm: only take M5 pullback entries in the direction of a
higher-timeframe (H4) trend.

Spec (2026-08-28, see .planning/quick/20260828-htf-pullback/SPEC.md):
  HTF bias:  Bullish when H4 close > H4 EMA(50)
             Bearish when H4 close < H4 EMA(50)
  M5 trigger (while the bias is in force):
     Long:  M5 pulled back below M5 EMA(20) and prints a bullish bar (close>open)
     Short: M5 rallied above M5 EMA(20) and prints a bearish bar (close<open)
  Entry at the NEXT M5 bar open (100% coverage, no slot starvation).
  SL = low (long) / high (short) of the M5 trigger bar. TP = rr x risk.

No-lookahead contract (mirrors filters.htf_trend, the project's existing HTF
seam):
  - the H4 EMA verdict for an M5 bar at time t uses only H4 bars that have
    COMPLETED before t (shift by one H4 bar, then forward-fill)
  - the M5 trigger is confirmed at the close of bar t; entry is the next open
"""

import pandas as pd


def htf_bias(
    df: pd.DataFrame, ema: int = 50, rule: str = "4h"
) -> pd.Series:
    """+1 where H4 close > H4 EMA(ema), -1 below, 0 before enough H4 history.

    The no-lookahead step is the shift(1) on the H4 verdict (see filters.htf_trend
    for the full rationale): an M5 bar at 10:05 may only see H4 bars that had
    finished by then.
    """
    htf_close = df["close"].resample(rule).last()
    htf_ema = htf_close.ewm(span=ema, adjust=False).mean()
    bullish = htf_close > htf_ema
    verdict = pd.Series(0, index=htf_close.index)
    verdict[bullish] = 1
    verdict[~bullish] = -1
    verdict = verdict.shift(1)  # only COMPLETED H4 bars
    aligned = verdict.reindex(df.index, method="ffill")
    return aligned.fillna(0).astype(int)


def detect_pullbacks(
    df: pd.DataFrame,
    ema_fast: int = 20,
    ema_htf: int = 50,
    htf_rule: str = "4h",
) -> pd.DataFrame:
    """Mark HTF-aligned M5 pullback triggers.

    Long trigger at bar t:  htf_bias[t] == +1 AND m5_ema20 exists AND
        close[t] > open[t] (bullish bar) AND low[t] <= ema20[t]
        (the bar pulled back to/touched the fast EMA).
    Short trigger at bar t: htf_bias[t] == -1 AND close[t] < open[t] AND
        high[t] >= ema20[t].

    The "pullback to the fast EMA" reading is used (rather than "closed below
    the EMA then bounced") because it is the clean, single-bar, testable form
    of a pullback continuation and is what the spec's diagram implies. The
    direction is fully gated by the HTF bias.

    Adds: htf_bias, m5_ema, setup (bool), setup_dir (+1/-1/0).
    The input frame is never mutated.
    """
    out = df.copy()
    out["htf_bias"] = htf_bias(out, ema_htf, htf_rule)
    ema = out["close"].ewm(span=ema_fast, adjust=False).mean()
    out["m5_ema"] = ema

    close = out["close"]
    open_ = out["open"]
    high = out["high"]
    low = out["low"]
    bias = out["htf_bias"]

    long_ok = (bias == 1) & (close > open_) & (low <= ema) & ema.notna()
    short_ok = (bias == -1) & (close < open_) & (high >= ema) & ema.notna()
    out["setup"] = long_ok | short_ok
    out["setup_dir"] = 0
    out.loc[long_ok, "setup_dir"] = 1
    out.loc[short_ok, "setup_dir"] = -1
    return out


def trigger_levels(bar) -> tuple[float, int]:
    """(sl_anchor, direction) for a trigger bar.

    Long: SL anchor is the bar's LOW; Short: the bar's HIGH. The actual SL/entry
    are computed at fill time (entry = next open, SL = anchor +/- tiny buffer).
    """
    if bar.setup_dir > 0:
        return float(bar.low), 1
    return float(bar.high), -1
