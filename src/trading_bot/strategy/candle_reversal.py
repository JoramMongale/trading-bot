"""STRAT candle-reversal setup detection — a selectable TEST strategy.

Pure pandas/numpy — shared by the backtester and (optionally, behind an
explicit config) the live bot (SAFE-01). This is a research variant of the
original breakout setup, kept as a first-class module so it can be measured
and compared, NOT wired in as the default.

Signal (user spec, 2026-08-28):
  A bullish candle that follows a bearish candle:
      setup[t] = (close[t] > open[t]) AND (close[t-1] < open[t-1])

Trade geometry for a LONG (the buy side of the spec):
  Entry = high[t]              (Buy Stop at the very top of the upper wick)
  SL    = low[t]               (below the bottom wick)
  TP    = entry + rr_multiple * (entry - sl)
         = high[t] + rr_multiple * (high[t] - low[t])

Because entry == high and sl == low, (entry - sl) equals the full candle range,
so ``rr_multiple`` scales the target in exactly the way the caller wants: 1.0
gives TP = high + 1x range, 2.5 gives TP = high + 2.5x range. The engine's arm
formula (``tp = entry + rr_multiple * (entry - sl)``) therefore needs no change
for this variant — only the level SOURCE differs (candle high/low instead of
swing-based resistance/support).

All comparisons use data up to and including bar t only (no lookahead): the
pattern is known at the close of bar t, exactly when the live engine acts.

Adds: setup (bool). The input frame is never mutated.
"""

import pandas as pd


def detect_candle_reversal(df: pd.DataFrame) -> pd.DataFrame:
    """STRAT candle-reversal: a bullish candle directly after a bearish one.

    long setup[t] = (close[t] > open[t]) AND (close[t-1] < open[t-1])

    This variant does NOT use swing points or S/R levels. It is the pure
    two-candle reversal pattern; the engine supplies entry/SL/TP from the
    signal candle's own high/low (see ``candle_levels``).

    A doji (close == open) is never the bullish candle, and the prior bar must
    be strictly bearish — a flat prior close (doji) does not count as "red".
    """
    out = df.copy()  # CoW-friendly; pure function
    close = out["close"]
    open_ = out["open"]
    out["setup"] = (close > open_) & (close.shift(1) < open_.shift(1))
    return out


def candle_levels(bar) -> tuple[float, float]:
    """(entry, sl) for a LONG on a confirmed candle-reversal bar.

    Entry is the top of the upper wick (the bar's high); the stop sits below
    the bottom wick (the bar's low). This replaces the breakout variant's
    ``levels_at`` — the entry/stop come from the candle itself, not from
    swing-derived resistance/support. The buffer that the breakout variant
    applies to its structural stop does not exist here: the wick low IS the
    stop, and adding one would only push it further away.
    """
    return float(bar.high), float(bar.low)
