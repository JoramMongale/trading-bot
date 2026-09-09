"""M1 -> M5 OHLCV resampler.

Aggregates a 1-minute bar DataFrame into 5-minute bars with exact
OHLCV semantics: open=first, high=max, low=min, close=last, volume=sum.
Empty 5-minute buckets (e.g. the daily trading break gap) are dropped.
"""

from __future__ import annotations

import pandas as pd


def resample_to_m5(m1: pd.DataFrame) -> pd.DataFrame:
    """Resample 1-minute bars to 5-minute OHLCV bars (left-labeled).

    Partial buckets (fewer than 5 bars, e.g. around the daily break) are
    aggregated over whatever bars are present; empty buckets are dropped.
    """
    return (
        m1.resample("5min", label="left", closed="left")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna()
    )
