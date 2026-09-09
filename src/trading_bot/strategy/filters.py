"""Optional entry filters — volatility, higher-timeframe trend, candle body.

Pure pandas/numpy, no I/O, same contract as the rest of ``strategy``. Every
function returns a boolean Series aligned to ``df.index``, True where a trade
would be PERMITTED.

None of these are wired into the live engine. They exist so their effect can be
MEASURED, and the measurement bar here is high: ~39 configurations have already
been searched on this data and the best |t| anywhere was 2.46, which noise beats
42% of the time. Every filter slices the sample thinner, which makes a good
backtest easier to produce and a real edge harder to demonstrate. Treat a filter
that "helps" as unproven until it survives out-of-sample.

Filters are computed from data up to and including bar t only — never later.
The higher-timeframe filter is where that is easy to get wrong; see ``htf_trend``.
"""

import pandas as pd


def true_range(df: pd.DataFrame) -> pd.Series:
    """Wilder's True Range: max of the three classic ranges."""
    prev_close = df["close"].shift(1)
    ranges = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder-smoothed ATR (EMA with alpha = 1/period)."""
    return true_range(df).ewm(alpha=1.0 / period, adjust=False).mean()


def atr_below_median(
    df: pd.DataFrame, period: int = 14, median_bars: int = 120
) -> pd.Series:
    """True where ATR is at or below its own trailing median — "controlled" vol.

    The median window is trailing and CLOSED at bar t, so the comparison uses
    only history. Bars before the window fills are False: with no basis for the
    comparison, refusing is the honest answer rather than assuming permission.

    Worth stating plainly what this does to the strategy: the stop is structural
    (support to resistance), so low volatility means a TIGHTER stop and a nearer
    target, not a safer trade. This filter does not reduce risk per trade — risk
    per trade is already fixed by the sizing cap. It only changes WHICH trades
    are taken, which is a bet that breakouts in quiet conditions behave
    differently from breakouts in busy ones. That is an empirical claim, and it
    is the thing being measured.
    """
    a = atr(df, period)
    med = a.rolling(median_bars, min_periods=median_bars).median()
    return (a <= med).fillna(False)


def htf_trend(
    df: pd.DataFrame, sma: int = 20, rule: str = "1h", direction: str = "long"
) -> pd.Series:
    """True where the higher-timeframe trend agrees with ``direction``.

    Resamples to ``rule``, takes the SMA of the higher-timeframe closes, and
    compares close to SMA. Bullish = HTF close above its SMA.

    **The no-lookahead step is the ``shift(1)``.** A resampled H1 bar carries the
    timestamp of its OPEN, but its close is not known until the hour has ended.
    Reindexing it straight back onto M5 would let a 10:05 decision read the
    10:00-11:00 candle's close — fifty-five minutes of the future. Shifting by
    one HTF bar first means an M5 bar at 10:05 sees the 09:00-10:00 bar, the
    most recent one that had actually finished. This is the same rule the M5
    signal itself obeys (``copy_rates_from_pos(start_pos=1)`` in the live
    adapter): never act on a bar that is still forming.

    Bars before the HTF SMA has enough history are False.
    """
    if direction not in ("long", "short"):
        raise ValueError(f"direction={direction!r} must be 'long' or 'short'")

    htf_close = df["close"].resample(rule).last()
    htf_sma = htf_close.rolling(sma, min_periods=sma).mean()
    bullish = htf_close > htf_sma
    # Shift by one HTF bar: only COMPLETED higher-timeframe bars are visible.
    bullish = bullish.shift(1)
    # Carry each completed HTF verdict forward across the M5 bars it governs.
    aligned = bullish.reindex(df.index, method="ffill")
    ok = aligned if direction == "long" else ~aligned.astype("boolean")
    return ok.fillna(False).astype(bool)


def body_confirms(df: pd.DataFrame, direction: str = "long") -> pd.Series:
    """True where the bar closed in the direction of the trade.

    long: close > open (bullish body). short: close < open (bearish body).

    A doji (close == open) is False for both — it confirms nothing, and the
    honest reading of "the candle must close bullish" excludes it.
    """
    if direction not in ("long", "short"):
        raise ValueError(f"direction={direction!r} must be 'long' or 'short'")
    return (
        df["close"] > df["open"] if direction == "long" else df["close"] < df["open"]
    )
