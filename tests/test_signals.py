"""Tests for src/trading_bot/strategy/signals.py — STRAT-02 breakout setup detection.

Covers: the exact bullish-close-above-resistance crossover condition (close[t] >
resistance[t] AND close[t-1] <= resistance[t-1]), re-trigger suppression after a
breakout, NaN-level safety, extra-column preservation, and a full pipeline chain
(swings -> levels -> setups) proving the wiring used by the backtester.
"""

import numpy as np
import pandas as pd

from trading_bot.strategy.signals import detect_setups


def frame(closes, resistance, **extra):
    data = {"close": closes, "resistance": resistance}
    data.update(extra)
    return pd.DataFrame(data)


def test_fires_exactly_on_bullish_close_above_resistance():
    # resistance level 10.0 forms at index 2; close crosses above it only at index 4
    df = frame(
        closes=[10.0, 10.0, 9.0, 9.5, 10.5],
        resistance=[np.nan, np.nan, 10.0, 10.0, 10.0],
    )
    out = detect_setups(df)
    assert out["setup"].iloc[:4].tolist() == [False, False, False, False]
    assert bool(out["setup"].iloc[4])


def test_retrigger_disabled_after_breakout():
    # breakout fires at index 3 (prior close 9 <= 10); index 4 stays below
    # resistance (prior close 11 > 10) so the signal does NOT re-fire.
    df = frame(
        closes=[10.0, 10.0, 9.0, 11.0, 11.5],
        resistance=[10.0, 10.0, 10.0, 10.0, 10.0],
    )
    out = detect_setups(df)
    assert bool(out["setup"].iloc[3])
    assert not bool(out["setup"].iloc[4])


def test_nan_resistance_never_fires():
    # NaN comparisons are False — a missing level can never produce a setup
    df = frame(closes=[10.0, 11.0, 12.0], resistance=[np.nan, np.nan, np.nan])
    out = detect_setups(df)
    assert out["setup"].tolist() == [False, False, False]


def test_extra_columns_pass_through_unchanged():
    df = frame(
        closes=[10.0, 10.0, 9.0, 9.5, 10.5],
        resistance=[np.nan, np.nan, 10.0, 10.0, 10.0],
        volume=[100, 120, 90, 110, 130],
    )
    out = detect_setups(df)
    assert "volume" in out.columns
    assert out["volume"].tolist() == [100, 120, 90, 110, 130]
    # pure function: input frame is never mutated
    assert "setup" not in df.columns


def test_full_pipeline_fires_on_breakout_after_confirmation():
    from trading_bot.strategy.levels import support_resistance
    from trading_bot.strategy.swings import detect_swings

    # Raw swing high at index 3 (4.0) confirms at index 5 -> resistance 4.0.
    # Close at index 5 is 3.8 (<= 4.0); close at index 6 is 4.1 (> 4.0) -> setup fires.
    highs = [1.0, 2.0, 3.0, 4.0, 3.0, 2.0, 4.2]
    lows = [0.5, 0.8, 1.2, 2.0, 2.2, 2.8, 3.5]
    closes = [0.9, 1.9, 2.9, 3.9, 3.5, 3.8, 4.1]
    df = pd.DataFrame({"open": closes, "high": highs, "low": lows, "close": closes})
    out = detect_setups(support_resistance(detect_swings(df), lookback=60))
    assert out["setup"].iloc[:6].tolist() == [False] * 6
    assert bool(out["setup"].iloc[6])
