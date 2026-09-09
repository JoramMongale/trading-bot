"""Tests for src/trading_bot/strategy/candle_reversal.py — the two-candle
reversal TEST strategy.

Covers: the exact bullish-after-bearish condition (close[t] > open[t] AND
close[t-1] < open[t-1]), doji exclusion on both candles, pure-function safety,
and the entry/SL geometry from the signal candle's own wicks.
"""

import pandas as pd
import pytest

from trading_bot.strategy.candle_reversal import candle_levels, detect_candle_reversal


def frame(opens, highs, lows, closes):
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes}
    )


def test_fires_on_bullish_after_bearish():
    # idx1 red (close < open), idx2 green (close > open) -> setup at idx2
    df = frame(
        opens=[10.0, 10.0, 10.0, 10.0],
        highs=[10.2, 10.1, 10.6, 10.3],
        lows=[9.8, 9.8, 10.0, 9.9],
        closes=[10.0, 9.9, 10.5, 10.1],  # idx1 red, idx2 green
    )
    out = detect_candle_reversal(df)
    assert out["setup"].tolist() == [False, False, True, False]


def test_no_fire_when_prior_bar_is_green():
    # two greens in a row: the second is NOT a reversal of a bearish bar
    df = frame(
        opens=[10.0, 9.8, 10.0],
        highs=[10.2, 10.4, 10.5],
        lows=[9.8, 9.7, 9.9],
        closes=[10.0, 10.3, 10.4],  # idx1 green, idx2 green
    )
    out = detect_candle_reversal(df)
    assert out["setup"].tolist() == [False, False, False]


def test_doji_signal_bar_never_fires():
    # idx2 close == open (doji) -> not a bullish candle even though prior is red
    df = frame(
        opens=[10.0, 10.0, 10.3],
        highs=[10.2, 10.1, 10.4],
        lows=[9.8, 9.8, 10.2],
        closes=[10.0, 9.9, 10.3],  # idx2 doji (open == close)
    )
    out = detect_candle_reversal(df)
    assert out["setup"].tolist() == [False, False, False]


def test_doji_prior_bar_does_not_count_as_red():
    # idx1 doji is not bearish, so idx2 green is not a reversal of a red bar
    df = frame(
        opens=[10.0, 10.0, 10.0],
        highs=[10.2, 10.1, 10.6],
        lows=[9.8, 9.9, 10.0],
        closes=[10.0, 10.0, 10.5],  # idx1 doji, idx2 green
    )
    out = detect_candle_reversal(df)
    assert out["setup"].tolist() == [False, False, False]


def test_pure_function_input_never_mutated():
    df = frame(
        opens=[10.0, 10.0, 10.0],
        highs=[10.2, 10.1, 10.6],
        lows=[9.8, 9.8, 10.0],
        closes=[10.0, 9.9, 10.5],
    )
    detect_candle_reversal(df)
    assert "setup" not in df.columns


def test_candle_levels_entry_is_high_sl_is_low():
    class Bar:
        high = 100.50
        low = 99.80

    entry, sl = candle_levels(Bar())
    assert entry == pytest.approx(100.50)  # top of the upper wick
    assert sl == pytest.approx(99.80)      # below the bottom wick
