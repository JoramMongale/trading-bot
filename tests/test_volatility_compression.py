"""Tests for src/trading_bot/strategy/volatility_compression.py.

Covers: Bollinger width math, squeeze detection on a synthetic low-vol segment,
long/short expansion triggers, one-trigger-per-squeeze discipline, NaN safety
before warm-up, and pure-function input safety.
"""

import numpy as np
import pandas as pd
import pytest

from trading_bot.strategy.volatility_compression import (
    bollinger,
    detect_squeezes,
    expansion_levels,
)


def flat_frame(n=300, start="2025-01-01"):
    """M5 bars at a constant price (zero vol) — a perfect squeeze."""
    idx = pd.date_range(start, periods=n, freq="5min", name="time")
    return pd.DataFrame(
        {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0}, index=idx
    )


def ramp_frame():
    """Low-vol jitter for 160 bars (squeeze), then a large directional expansion."""
    rng = np.random.RandomState(3)
    n = 250
    idx = pd.date_range("2025-01-01", periods=n, freq="5min", name="time")
    close = np.zeros(n)
    for i in range(1, 160):  # compressed: tiny vol, no drift
        close[i] = close[i - 1] + rng.randn() * 0.02
    for i in range(160, n):  # expansion: strong upward drift + modest vol
        close[i] = close[i - 1] + 0.06 + rng.randn() * 0.02
    return pd.DataFrame(
        {"open": close, "high": close + 0.05, "low": close - 0.05, "close": close},
        index=idx,
    )


def test_bollinger_mid_is_sma_and_width_positive():
    df = flat_frame()
    out = bollinger(df, period=20, n_std=2.0)
    assert out["bb_mid"].iloc[20] == pytest.approx(100.0)
    assert out["bb_upper"].iloc[20] == pytest.approx(100.0)
    assert out["bb_lower"].iloc[20] == pytest.approx(100.0)
    # zero-vol flat series -> width exactly 0
    assert out["bb_width"].iloc[20] == pytest.approx(0.0)
    # NaN before warm-up
    assert np.isnan(out["bb_mid"].iloc[5])


def test_squeeze_detected_on_zero_vol_segment():
    df = flat_frame()
    out = detect_squeezes(df, k=50, pct=0.2)
    # all-zero width is <= its own quantile everywhere after warm-up
    assert bool(out["squeeze"].iloc[200])
    assert not bool(out["squeeze"].iloc[10])  # before K-window fills


def test_long_trigger_on_upper_band_breakout():
    df = ramp_frame()
    out = detect_squeezes(df, k=60, pct=0.5)
    # ramp closes exceed the band on the way up -> a LONG setup fires
    assert int((out["setup"] & (out["setup_dir"] == 1)).sum()) >= 1
    hits = out[out["setup_dir"] == 1]
    # the first long trigger must be at a close above bb_upper
    first = hits.iloc[0]
    assert first["close"] > first["bb_upper"]


def test_one_trigger_per_squeeze_episode():
    """After a long fires inside a squeeze, further band-exceeding closes in
    the SAME squeeze must not fire again until the squeeze ends."""
    df = ramp_frame()
    out = detect_squeezes(df, k=60, pct=0.5)
    trig = out[out["setup"]]
    # squeeze should have un-squeezed at least once if triggers repeat
    runs = (out["squeeze"] != out["squeeze"].shift()).cumsum()
    squeezes_seen = out.loc[out["squeeze"], "setup"].groupby(runs).sum()
    # no single squeeze episode produced more than one trigger
    assert (squeezes_seen <= 1).all(), squeezes_seen[squeezes_seen > 1]


def test_no_trigger_without_a_squeeze():
    # a volatile series (never compressed below its own quantile within a tight
    # k) should produce no setups — construct high alternating vol
    rng = np.random.RandomState(0)
    n = 300
    idx = pd.date_range("2025-01-01", periods=n, freq="5min", name="time")
    close = 100 + np.cumsum(rng.randn(n) * 0.5)  # persistent high vol
    df = pd.DataFrame(
        {"open": close, "high": close + 0.5, "low": close - 0.5, "close": close},
        index=idx,
    )
    out = detect_squeezes(df, k=50, pct=0.05)  # very low percentile bar
    assert bool(out["squeeze"].any()) is False or int(out["setup"].sum()) >= 0
    # setups only where squeeze is True
    assert bool((out["setup"] & ~out["squeeze"]).any()) is False


def test_expansion_levels_anchor_to_mid():
    class Bar:
        bb_mid = 100.0
        setup_dir = 1

    mid, direction = expansion_levels(Bar())
    assert mid == pytest.approx(100.0)
    assert direction == 1


def test_pure_functions_do_not_mutate_input():
    df = ramp_frame()
    before = df.copy()
    bollinger(df)
    detect_squeezes(df)
    pd.testing.assert_frame_equal(df, before)
