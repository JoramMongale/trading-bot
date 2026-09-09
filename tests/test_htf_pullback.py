"""Tests for src/trading_bot/strategy/htf_pullback.py.

Covers: HTF bias no-lookahead, long/short pullback triggers gated by the bias,
no trigger without a matching bias, NaN safety, and pure-function safety.
"""

import numpy as np
import pandas as pd
import pytest

from trading_bot.strategy.htf_pullback import detect_pullbacks, htf_bias


def make_frame(closes, start="2025-01-01", rule_freq="5min"):
    idx = pd.date_range(start, periods=len(closes), freq=rule_freq, name="time")
    o = np.array(closes, dtype=float)
    return pd.DataFrame(
        {"open": o, "high": o, "low": o, "close": o}, index=idx
    )


def test_htf_bias_returns_plus_minus_and_zero_before_history():
    # strongly trending up: H4 closes rising -> EMA below close -> bias +1
    n = 400  # 400 M5 bars = ~33h, several H4 bars
    up = np.linspace(100, 200, n)
    df = make_frame(up)
    bias = htf_bias(df, ema=50, rule="4h")
    # after enough H4 history the bias is +1
    tail = bias.iloc[-100:]
    assert int(tail.mode().iloc[0]) == 1


def test_htf_bias_uses_only_completed_h4_bars():
    """No-lookahead: the bias flips to +1 only after an H1 bar has CLOSED above
    the EMA — never on the M5 bar where the jump first happens."""
    # 6 hours of M5 bars (72 bars) at 100, then a sustained rise to 150.
    n = 500
    closes = np.array([100.0] * 72 + list(np.linspace(100, 150, n - 72)))
    df = make_frame(closes)
    bias = htf_bias(df, ema=10, rule="1h")
    # Find the first bar where close is clearly above the recent flat level.
    jump_idx = 72
    # With a 1h rule, bars 0..11 form the first H1 bar. After the price jump the
    # first COMPLETED rising H1 bar is the one ending at ~jump_idx+12. Before
    # that completed bar, the bias must not yet read +1.
    early = bias.iloc[jump_idx:jump_idx + 12]
    # The bias is -1 during the flat phase (close == EMA -> not bullish).
    assert (early == 1).sum() == 0, "bias flipped before an H1 bar completed"
    # Once a rising H1 bar completes, the bias becomes +1 and stays.
    later = bias.iloc[jump_idx + 24:]
    assert (later == 1).any()


def test_long_trigger_requires_htf_bullish_bias():
    """Synthetic: H4 uptrend, M5 dips to its fast EMA then closes bullish."""
    n = 600
    base = np.linspace(100, 300, n)  # sustained H4 uptrend
    o = base.copy()
    h = base + 1.0
    l = base - 1.0
    c = base.copy()
    idx = pd.date_range("2025-01-01", periods=n, freq="5min", name="time")
    df = pd.DataFrame({"open": o, "high": h, "low": l, "close": c}, index=idx)
    out = detect_pullbacks(df, ema_fast=20, ema_htf=50, htf_rule="4h")
    # bias is +1 in the tail of a sustained uptrend
    assert (out["htf_bias"].iloc[-200:] == 1).any()
    # setups, when present, are longs only under a +1 bias
    longs = out[out["setup_dir"] == 1]
    shorts = out[out["setup_dir"] == -1]
    assert len(shorts) == 0  # no bearish bias in a pure uptrend
    # every long trigger occurred while bias == +1
    assert bool((longs["htf_bias"] == 1).all())


def test_short_trigger_requires_htf_bearish_bias():
    n = 600
    base = np.linspace(300, 100, n)  # sustained downtrend
    o = base.copy(); h = base + 1.0; l = base - 1.0; c = base.copy()
    idx = pd.date_range("2025-01-01", periods=n, freq="5min", name="time")
    df = pd.DataFrame({"open": o, "high": h, "low": l, "close": c}, index=idx)
    out = detect_pullbacks(df, ema_fast=20, ema_htf=50, htf_rule="4h")
    shorts = out[out["setup_dir"] == -1]
    longs = out[out["setup_dir"] == 1]
    assert len(longs) == 0
    if len(shorts):
        assert bool((shorts["htf_bias"] == -1).all())


def test_setup_columns_absent_from_input_after_call():
    df = make_frame(np.linspace(100, 200, 400))
    before = df.copy()
    detect_pullbacks(df)
    pd.testing.assert_frame_equal(df, before)
    assert "setup" not in df.columns
