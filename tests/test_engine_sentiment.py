"""Sentiment direction-gate semantics in the shared backtest engine.

Properties pinned here (quick task 20260928-btc-fear-greed):

1. Byte-identity: ``run_backtest(df)`` == ``run_backtest(df, sentiment=None)``
   record-for-record (the seam must not touch the default path).
2. Direction gate in a both-book: all-bullish -> zero shorts, all-bearish ->
   zero longs, neutral -> both sides, all-NaN -> same as sentiment=None
   (fail-open = no mask).
3. Single-direction gate: direction="long" + all-bearish -> zero trades;
   direction="short" + all-bullish -> zero trades.
4. Validation: a sentiment Series of the wrong length raises ValueError naming
   "sentiment".
"""

import numpy as np
import pandas as pd
import pytest

from trading_bot.backtest.engine import run_backtest


def _frame(rows, start="2026-01-01", freq="5min"):
    idx = pd.date_range(start, periods=len(rows), freq=freq)
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


def _random_walk(n=12000, seed=7):
    rng = np.random.default_rng(seed)
    close = 1000 + np.cumsum(rng.normal(0, 1.0, n))
    spread = np.abs(rng.normal(0, 0.6, n)) + 0.1
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    return _frame(np.c_[open_, high, low, close])


def _sent(df, value):
    """Broadcast a constant F&G value (or np.nan) aligned to df.index."""
    return pd.Series(value, index=df.index, dtype="float64")


# --- 1. byte-identity of the default path -----------------------------------


def test_sentiment_none_is_byte_identical():
    df = _random_walk(n=12000)
    assert run_backtest(df) == run_backtest(df, sentiment=None)


# --- 2. both-book direction gate --------------------------------------------


def test_all_bullish_both_has_no_shorts():
    df = _random_walk(n=12000)
    trades = run_backtest(df, direction="both", sentiment=_sent(df, 90.0))
    assert len(trades) > 0
    assert {t["direction"] for t in trades} == {"long"}


def test_all_bearish_both_has_no_longs():
    df = _random_walk(n=12000)
    trades = run_backtest(df, direction="both", sentiment=_sent(df, 10.0))
    assert len(trades) > 0
    assert {t["direction"] for t in trades} == {"short"}


def test_neutral_both_has_both_sides():
    df = _random_walk(n=12000)
    trades = run_backtest(df, direction="both", sentiment=_sent(df, 50.0))
    assert {"long", "short"} <= {t["direction"] for t in trades}


def test_all_nan_fail_open_same_count():
    df = _random_walk(n=12000)
    base = run_backtest(df, direction="both")
    gated = run_backtest(df, direction="both", sentiment=_sent(df, np.nan))
    assert len(base) == len(gated)


# --- 3. single-direction gate -----------------------------------------------


def test_long_all_bearish_zero_trades():
    df = _random_walk(n=12000)
    assert run_backtest(df, direction="long", sentiment=_sent(df, 10.0)) == []


def test_short_all_bullish_zero_trades():
    df = _random_walk(n=12000)
    assert run_backtest(df, direction="short", sentiment=_sent(df, 90.0)) == []


# --- 4. validation ----------------------------------------------------------


def test_length_mismatch_raises():
    df = _random_walk(n=6000)
    bad = pd.Series(50.0, index=range(len(df) + 1))
    with pytest.raises(ValueError, match="sentiment"):
        run_backtest(df, direction="both", sentiment=bad)


def test_negative_band_raises():
    df = _random_walk(n=6000)
    with pytest.raises(ValueError, match="sentiment_band"):
        run_backtest(df, direction="both", sentiment=_sent(df, 50.0),
                     sentiment_band=-1.0)
