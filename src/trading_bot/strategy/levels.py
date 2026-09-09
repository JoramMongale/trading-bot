"""Support/resistance levels from CONFIRMED swing points.

Pure pandas/numpy — shared by the backtester and the Phase 2 live bot (SAFE-01).
Reads only the confirmed swing_high/swing_low columns produced by
``strategy.swings.detect_swings``, so unconfirmed swings can never leak into levels.

A level is the trailing-lookback max/min of the CONFIRMED swings of that type:
a swing stops contributing the first bar it leaves the ``lookback`` window, and
the level decays to NaN the moment no confirmed swing of that type is inside the
window — expiry is a pure function of the trailing window, never carried forward
past it (no stale-level contamination across data gaps).
"""

import pandas as pd


def support_resistance(df: pd.DataFrame, lookback: int = 60) -> pd.DataFrame:
    """Trailing-window S/R from confirmed swings (window-bounded expiry).

    resistance = max of swing_high over the trailing ``lookback`` bars,
    support    = min of swing_low over the trailing ``lookback`` bars.

    Both stay NaN until the first CONFIRMED swing of that type enters the window
    (rolling max/min of an all-NaN window is NaN), so a level is never built
    from a swing that live trading could not yet see. A level persists across
    quiet bars while a confirmed swing is inside the window, and decays to NaN
    the first bar the window no longer contains any confirmed swing of that
    type — a newer swing entering the window updates the level immediately.
    Expiry is a pure function of the lookback window: no lookahead, no data-gap
    knowledge, no forward-fill beyond the window.

    Adds: resistance, support. The input frame is never mutated.
    """
    out = df.copy()  # CoW-friendly; pure function
    out["resistance"] = out["swing_high"].rolling(lookback, min_periods=1).max()
    out["support"] = out["swing_low"].rolling(lookback, min_periods=1).min()
    return out
