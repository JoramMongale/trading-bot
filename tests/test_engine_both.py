"""direction="both" single-slot semantics in the shared backtest engine.

Five properties are pinned here:

1. Byte-identity of the long path: after the per-trade-sign refactor the
   default direction="long" run must equal an explicit direction="long" run
   record-for-record (the refactor must not touch the single-direction path).
2. Mirror symmetry of a both-book on reflected data: longs on a series and
   shorts on its reflection must match trade-for-trade (the same guarantee
   test_short_and_filters.py demands of the single-direction runs).
3. Per-trade labels and geometry: every trade in a both-book carries its own
   "long"/"short" direction and is armed from the correct side's levels.
4. Single-slot no-overlap: with max_concurrent=1 trades in a both-book never
   overlap in time.
5. Invalid combinations raise: direction="both" with the direction-scoped
   options (candle_reversal variant, require_body, htf_sma, setup_override)
   is refused with a ValueError naming the combination; an unknown direction
   still raises.
"""

import numpy as np
import pandas as pd
import pytest

from trading_bot.backtest.engine import run_backtest
from trading_bot.backtest.stats import trade_stats


def _frame(rows, start="2026-01-01", freq="5min"):
    idx = pd.date_range(start, periods=len(rows), freq=freq)
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


def _mirror(df):
    """Reflect a price series about zero: highs become lows and vice versa."""
    out = pd.DataFrame(
        {
            "open": -df["open"],
            "high": -df["low"],
            "low": -df["high"],
            "close": -df["close"],
        },
        index=df.index,
    )
    return out


def _random_walk(n=6000, seed=7):
    rng = np.random.default_rng(seed)
    close = 1000 + np.cumsum(rng.normal(0, 1.0, n))
    spread = np.abs(rng.normal(0, 0.6, n)) + 0.1
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    return _frame(np.c_[open_, high, low, close])


def _book_on_mirror(df, n=12000):
    up = run_backtest(df, direction="both")
    down = run_backtest(_mirror(df), direction="both")
    return up, down


# --- 1. byte-identity of the long path after the refactor ------------------


def test_long_default_is_byte_identical_to_explicit_long():
    """direction="long" (the default) must equal the pre-refactor record
    stream exactly -- the byte-identity proof the golden tests rely on."""
    df = _random_walk(n=12000)
    assert run_backtest(df) == run_backtest(df, direction="long")


# --- 2. mirror symmetry -----------------------------------------------------


def test_both_book_on_mirrored_data_flips_every_trade():
    """A both-book on a series and a both-book on its reflection must trade
    the same times with every direction flipped and every price negated."""
    df = _random_walk(n=12000)
    up, down = _book_on_mirror(df)

    assert len(up) == len(down) > 20, (len(up), len(down))
    assert {"long", "short"} <= {t["direction"] for t in up}
    assert {"long", "short"} <= {t["direction"] for t in down}

    trade_stats(up)
    trade_stats(down)
    by_time = {t["entry_time"]: t for t in down}
    assert len(by_time) == len(down)  # one trade per fill bar: keys unique
    for a in up:
        b = by_time[a["entry_time"]]
        assert a["direction"] != b["direction"], a["entry_time"]
        assert a["entry_idx"] == b["entry_idx"]
        assert a["exit_idx"] == b["exit_idx"]
        assert a["exit_reason"] == b["exit_reason"]
        assert a["entry"] == pytest.approx(-b["entry"])
        assert a["sl"] == pytest.approx(-b["sl"])
        assert a["tp"] == pytest.approx(-b["tp"])
        assert a["exit_price"] == pytest.approx(-b["exit_price"])
        assert a["r_multiple"] == pytest.approx(b["r_multiple"])
        assert a["pnl_points"] == pytest.approx(b["pnl_points"])

    for key in ("total_trades", "wins", "losses", "avg_r", "net_pnl_points"):
        assert trade_stats(up)[key] == pytest.approx(trade_stats(down)[key]), key


# --- 3. labels and geometry ------------------------------------------------


def test_both_book_carries_both_sides_with_correct_geometry():
    """A both-book on a random walk must contain at least one long and one
    short, and each trade must be armed from its own side's levels."""
    trades = run_backtest(_random_walk(n=12000), direction="both")
    sides = {t["direction"] for t in trades}
    assert sides == {"long", "short"}, sides
    for t in trades:
        if t["direction"] == "long":
            assert t["sl"] < t["entry"] < t["tp"], t
        else:
            assert t["sl"] > t["entry"] > t["tp"], t


# --- 4. single slot, no overlap --------------------------------------------


def test_both_book_single_slot_trades_never_overlap():
    """With max_concurrent=1 the both-book is one slot: sorted by entry_idx,
    each next entry is strictly after the previous exit."""
    trades = run_backtest(_random_walk(n=12000), direction="both",
                          max_concurrent=1)
    assert len(trades) > 20, len(trades)
    ordered = sorted(trades, key=lambda t: t["entry_idx"])
    for prev, cur in zip(ordered, ordered[1:]):
        assert cur["entry_idx"] > prev["exit_idx"], (prev, cur)


# --- 5. invalid combinations raise -----------------------------------------


def test_both_rejects_direction_scoped_options():
    df = _random_walk(n=6000)
    with pytest.raises(ValueError, match="both"):
        run_backtest(df, direction="both", require_body=True)
    with pytest.raises(ValueError, match="both"):
        run_backtest(df, direction="both", htf_sma=20)
    with pytest.raises(ValueError, match="both"):
        run_backtest(df, direction="both",
                     setup_override=pd.Series(False, index=df.index))
    # candle_reversal describes the BUY side only; the existing guard's
    # message already names direction="both".
    with pytest.raises(ValueError, match="both"):
        run_backtest(df, direction="both", variant="candle_reversal")


def test_unknown_direction_still_raises():
    df = _random_walk(n=300)
    with pytest.raises(ValueError, match="direction"):
        run_backtest(df, direction="sideways")
