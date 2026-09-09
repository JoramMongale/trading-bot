"""Williams-style fractal swing point detection (STRAT-01).

Pure pandas/numpy — no logging, config, data, or broker imports, so the live
bot can call these exact functions on its own bars (SAFE-01).
"""

import numpy as np
import pandas as pd


def detect_swings(df: pd.DataFrame, left: int = 2, right: int = 2) -> pd.DataFrame:
    """Fractal swing points with a no-lookahead confirmation shift.

    Raw swing high at i:  high[i] >= max(high[i-left .. i-1])  AND  high[i] > max(high[i+1 .. i+right])
    Raw swing low at i:   low[i]  <= min(low[i-left .. i-1])   AND  low[i]  < min(low[i+1 .. i+right])

    '>='/'<=' on the LEFT makes the LAST bar of an equal-high/low plateau the
    swing point. Strict '>'/'<' on the RIGHT keeps the swing unconfirmed until
    the right window closes.

    The confirmed columns are the raw markers shifted by `right` bars: a swing
    at bar i becomes usable only at bar i+right — exactly when it would be known
    in live trading. Levels and setups must read ONLY these confirmed columns.

    Adds: swing_high_raw, swing_low_raw, swing_high, swing_low.
    The input frame is never mutated (CoW-safe copy).
    """
    high = df["high"]
    low = df["low"]

    # Max/min over the LEFT window ending at i-1 ('.shift(1)'), and over the
    # RIGHT window [i+1 .. i+right] ('.shift(-right)' pulls the rolling value
    # computed at i+right back onto row i).
    left_high_max = high.rolling(left, min_periods=left).max().shift(1)
    right_high_max = high.rolling(right, min_periods=right).max().shift(-right)
    left_low_min = low.rolling(left, min_periods=left).min().shift(1)
    right_low_min = low.rolling(right, min_periods=right).min().shift(-right)

    is_swing_high = (high >= left_high_max) & (high > right_high_max)
    is_swing_low = (low <= left_low_min) & (low < right_low_min)

    out = df.copy()  # CoW-friendly; pure function, caller's frame untouched
    out["swing_high_raw"] = np.where(is_swing_high, high, np.nan)
    out["swing_low_raw"] = np.where(is_swing_low, low, np.nan)
    out["swing_high"] = out["swing_high_raw"].shift(right)  # confirmed, no lookahead
    out["swing_low"] = out["swing_low_raw"].shift(right)
    return out
