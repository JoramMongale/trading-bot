"""Tests for src/trading_bot/strategy/liquidity_sweep.py — session ORB detection.

Covers: per-day session range with no-lookahead, breakout sweeps (long on an
up-sweep, short on a down-sweep), and failed-sweep reversal detection. Frames
use a synthetic 2-hour day so ranges and sweeps are hand-checkable.
"""

import numpy as np
import pandas as pd
import pytest

from trading_bot.strategy.liquidity_sweep import detect_sweeps, session_range


def day_frame(day="2025-01-01", n=24):
    """24 consecutive M5 bars (2 hours) starting 00:00 on ``day``, flat price."""
    idx = pd.date_range(f"{day} 00:00", periods=n, freq="5min", name="time")
    return pd.DataFrame(
        {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0}, index=idx
    )


def test_session_range_uses_only_window_bars():
    df = day_frame()
    # push one high spike inside the 00:00-01:00 window and one outside
    df.loc["2025-01-01 00:30", "high"] = 105.0
    df.loc["2025-01-01 01:30", "high"] = 110.0  # outside [0,1): must NOT count
    out = session_range(df, 0, 1)
    # range_high usable only from 01:00 (window end) onward
    assert np.isnan(out.loc["2025-01-01 00:55", "range_high"])
    assert out.loc["2025-01-01 01:00", "range_high"] == pytest.approx(105.0)
    assert out.loc["2025-01-01 01:30", "range_high"] == pytest.approx(105.0)


def test_session_range_gap_day_flagged_not_ok():
    df = day_frame().iloc[6:]  # day starts at 00:30 -> 00:00-01:00 window partial
    # force an empty reference window: bars only after 01:00
    df = df[df.index.hour >= 1]
    out = session_range(df, 0, 1)
    assert not bool(out["range_ok"].any())


def test_breakout_up_sweep_fires_long():
    df = day_frame()
    # range window 00:00-01:00 -> range_high = 100.0
    # at 01:05 a bar pokes above it
    df.loc["2025-01-01 01:05", "high"] = 100.5
    rng = session_range(df, 0, 1)
    det = detect_sweeps(rng, "breakout", sweep_start=1, sweep_end=2)
    setup_bar = det.loc["2025-01-01 01:05"]
    assert bool(setup_bar["setup"])
    assert setup_bar["setup_dir"] == 1


def test_breakout_down_sweep_fires_short():
    df = day_frame()
    df.loc["2025-01-01 01:10", "low"] = 99.5
    rng = session_range(df, 0, 1)
    det = detect_sweeps(rng, "breakout", sweep_start=1, sweep_end=2)
    assert bool(det.loc["2025-01-01 01:10", "setup"])
    assert det.loc["2025-01-01 01:10", "setup_dir"] == -1


def test_no_setup_before_range_window_closes():
    df = day_frame()
    df.loc["2025-01-01 00:40", "high"] = 100.5  # inside the RANGE window
    rng = session_range(df, 0, 1)
    det = detect_sweeps(rng, "breakout", sweep_start=0, sweep_end=2)
    # the poke at 00:40 is inside the range window itself -> not a sweep
    assert not bool(det.loc["2025-01-01 00:40", "setup"])


def test_failed_up_sweep_fires_short_on_close_back():
    df = day_frame()
    # up-sweep at 01:05 (high 100.5 > range_high 100.0)
    df.loc["2025-01-01 01:05", "high"] = 100.5
    # fails at 01:10: closes back below 100.0 -> SHORT
    df.loc["2025-01-01 01:10", "close"] = 99.8
    rng = session_range(df, 0, 1)
    det = detect_sweeps(rng, "failed", sweep_start=1, sweep_end=2)
    assert not bool(det.loc["2025-01-01 01:05", "setup"])  # poke alone = nothing
    assert bool(det.loc["2025-01-01 01:10", "setup"])
    assert det.loc["2025-01-01 01:10", "setup_dir"] == -1


def test_sweep_that_does_not_fail_produces_no_trade():
    df = day_frame()
    df.loc["2025-01-01 01:05", "high"] = 100.5
    df.loc["2025-01-01 01:10", "close"] = 100.3  # stays above range_high
    rng = session_range(df, 0, 1)
    det = detect_sweeps(rng, "failed", sweep_start=1, sweep_end=2)
    assert not bool(det["setup"].any())


def test_pure_functions_do_not_mutate_input():
    df = day_frame()
    df.loc["2025-01-01 01:05", "high"] = 100.5
    rng = session_range(df, 0, 1)
    rng_before = rng.copy()
    detect_sweeps(rng, "breakout", sweep_start=1, sweep_end=2)
    pd.testing.assert_frame_equal(rng, rng_before)
    assert "setup" not in df.columns
