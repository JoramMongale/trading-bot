"""Tests for src/trading_bot/strategy/levels.py — trailing-window S/R from CONFIRMED swings.

Covers: NaN until the first confirmed swing of a type exists (no lookahead into
unconfirmed swings), persistence while a swing is inside the lookback window,
level updates from newer swings, and window-bounded expiry (a level decays to
NaN the first bar the lookback window holds no confirmed swing of that type —
no forward-fill beyond the window).
"""

import numpy as np
import pandas as pd

from trading_bot.strategy.levels import support_resistance
from trading_bot.strategy.swings import detect_swings


def chain(highs, lows, lookback=60):
    """Full detection pipeline: swings -> levels on a synthetic price series."""
    df = pd.DataFrame({"open": highs, "high": highs, "low": lows, "close": highs})
    return support_resistance(detect_swings(df), lookback=lookback)


def test_resistance_nan_until_first_confirmed_swing():
    out = chain([1.0, 2.0, 3.0, 4.0, 3.0, 2.0, 1.0], [0.5] * 7)
    # the raw swing high sits at index 3, but is only confirmed at index 5 —
    # resistance must not see it before then (no lookahead bias).
    assert out["swing_high_raw"].iloc[3] == 4.0
    assert out["resistance"].iloc[0:5].isna().all()
    assert out["resistance"].iloc[5] == 4.0
    assert out["resistance"].iloc[6] == 4.0


def test_resistance_persists_within_lookback_window():
    # raw swing high at index 2 (5.0) -> confirmed at index 4
    highs = [1.0, 2.0, 5.0, 3.0, 2.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    out = chain(highs, [0.5] * len(highs))
    assert out["swing_high"].iloc[4] == 5.0
    # resistance persists while a confirmed swing is inside the lookback window
    # (default lookback=60: bar 9 is 5 bars after confirmation, well within) — no ffill
    assert out["resistance"].iloc[9] == 5.0


def test_newer_higher_swing_raises_resistance():
    # swings confirmed at index 4 (5.0) and index 8 (6.0)
    highs = [1.0, 2.0, 5.0, 3.0, 2.0, 1.0, 6.0, 4.0, 3.0, 2.0, 1.0]
    out = chain(highs, [0.5] * len(highs))
    assert out["swing_high"].iloc[4] == 5.0
    assert out["swing_high"].iloc[8] == 6.0
    assert out["resistance"].iloc[4] == 5.0
    assert out["resistance"].iloc[7] == 5.0
    assert out["resistance"].iloc[8] == 6.0


def test_lookback_expiry_newer_lower_swing_replaces():
    # lookback=3: the 5.0 swing (confirmed at 4) leaves the trailing window at
    # bar 7, so resistance decays to NaN in the window gap between the expired
    # swing and the next confirmed swing — there is no ffill-forever. The newer,
    # lower 3.5 swing (confirmed at 8) then becomes resistance.
    highs = [1.0, 2.0, 5.0, 3.0, 2.0, 1.0, 3.5, 2.0, 1.0, 2.0]
    out = chain(highs, [0.5] * len(highs), lookback=3)
    assert out["swing_high"].iloc[4] == 5.0
    assert out["swing_high"].iloc[8] == 3.5
    assert pd.isna(out["resistance"].iloc[7])  # 5.0 left the window at bar 7 -> NaN
    assert out["resistance"].iloc[8] == 3.5    # newer swing enters the window


def test_support_uses_min_of_confirmed_swing_lows():
    # swing lows confirmed at index 4 (3.0) and index 8 (4.0)
    lows = [6.0, 5.0, 3.0, 4.0, 5.0, 6.0, 4.0, 5.0, 6.0, 6.0]
    out = chain([7.0] * len(lows), lows)
    assert out["support"].iloc[0:4].isna().all()  # NaN until first confirmed low
    assert out["support"].iloc[4] == 3.0
    # a newer HIGHER swing low (4.0) does not raise support — min stays 3.0
    assert out["swing_low"].iloc[8] == 4.0
    assert out["support"].iloc[8] == 3.0


def test_support_lookback_expiry_newer_lower_swing_replaces():
    # lookback=3: the 3.0 swing (confirmed at 4) leaves the trailing window by
    # bar 9, so support decays to NaN in the window gap between the expired
    # swing and the next confirmed swing — there is no ffill-forever. The newer,
    # lower 2.0 swing (confirmed at 10) then becomes support.
    lows = [6.0, 5.0, 3.0, 4.0, 5.0, 6.0, 4.0, 3.5, 2.0, 3.0, 4.0]
    out = chain([7.0] * len(lows), lows, lookback=3)
    assert out["swing_low"].iloc[4] == 3.0
    assert out["swing_low"].iloc[10] == 2.0
    assert pd.isna(out["support"].iloc[9])    # 3.0 left the window by bar 9 -> NaN
    assert out["support"].iloc[10] == 2.0     # newer swing enters the window


def test_resistance_expires_to_nan_when_swing_leaves_window():
    # lookback=3: the 5.0 swing (raw at 2, confirmed at 4) is still inside the
    # trailing window at bar 6, then leaves it at bar 7. With NO newer swing
    # appearing, resistance must decay to NaN — never ffill forever.
    highs = [1.0, 2.0, 5.0, 3.0, 2.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    out = chain(highs, [0.5] * len(highs), lookback=3)
    assert out["swing_high"].iloc[4] == 5.0
    assert out["resistance"].iloc[4] == 5.0
    assert out["resistance"].iloc[6] == 5.0   # still inside the 3-bar window
    assert out["resistance"].iloc[7:].isna().all()  # expired -> NaN


def test_support_expires_to_nan_when_swing_leaves_window():
    # lookback=3: the 3.0 swing (raw at 2, confirmed at 4) leaves the trailing
    # window at bar 7. With NO newer swing appearing, support must decay to NaN
    # — never ffill forever.
    lows = [6.0, 5.0, 3.0, 4.0, 5.0, 6.0, 4.0, 4.0, 4.0, 4.0, 4.0]
    out = chain([7.0] * len(lows), lows, lookback=3)
    assert out["swing_low"].iloc[4] == 3.0
    assert out["support"].iloc[4] == 3.0
    assert out["support"].iloc[6] == 3.0   # still inside the 3-bar window
    assert out["support"].iloc[7:].isna().all()  # expired -> NaN
