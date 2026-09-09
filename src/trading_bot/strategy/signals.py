"""STRAT-02 breakout setup detection, long and short.

Pure pandas/numpy — shared by the backtester and the Phase 2 live bot (SAFE-01).
Consumes the confirmed level columns from ``strategy.levels.support_resistance``.
"""

import pandas as pd


def detect_setups(df: pd.DataFrame, direction: str = "long") -> pd.DataFrame:
    """STRAT-02: a close through a level, with the prior close on the far side.

    long   setup[t] = (close[t] >  resistance[t]) AND (close[t-1] <= resistance[t-1])
    short  setup[t] = (close[t] <  support[t])    AND (close[t-1] >= support[t-1])

    All comparisons are made against levels valid at each bar (already confirmed
    and shifted), so a decision at the close of bar t uses data up to and
    including bar t only. The prior-close condition self-disables re-triggers:
    after a breakout, the prior close is already through the level, so no new
    signal fires until a fresh swing forms on the other side of price and price
    retraces past it.

    ``direction`` defaults to ``"long"``, which reproduces the original
    behaviour exactly — the live engine depends on that and must not change.

    The short branch is a strict mirror: no extra confirmation is layered onto
    it. That is the point. It exists to measure whether the setup's measured
    negative edge is SYMMETRIC, and any condition present on one side but not
    the other would make the two sides incomparable. Candle-body confirmation
    is available separately in ``strategy.filters`` and applies to both sides
    or neither.

    Adds: setup (bool). The input frame is never mutated.
    """
    if direction not in ("long", "short"):
        raise ValueError(f"direction={direction!r} must be 'long' or 'short'")

    out = df.copy()  # CoW-friendly; pure function
    close = out["close"]
    if direction == "long":
        level = out["resistance"]
        out["setup"] = (close > level) & (close.shift(1) <= level.shift(1))
    else:
        level = out["support"]
        out["setup"] = (close < level) & (close.shift(1) >= level.shift(1))
    return out
