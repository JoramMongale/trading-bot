"""Market context builders (plan 03-01).

The deterministic system builds a compact, honest snapshot of the market and
hands it to the model — the model reasons ONLY on this, never on its training
memory of "current" prices, which is months stale by definition. This mirrors
the reference book's rule: no live market data through a prompt; the prompt
carries what the deterministic code already fetched.

Everything here is pure pandas/stdlib: bars + the deterministic levels in,
two frozen context dataclasses out. Testable offline with the same golden
frames the rest of the suite uses.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


def _last_bars(df: pd.DataFrame, n: int = 20) -> list[dict]:
    """Compact OHLC of the last ``n`` rows: [{time, open, high, low, close}]."""
    tail = df.tail(n)
    return [
        {
            "time": str(idx),
            "open": float(row.open),
            "high": float(row.high),
            "low": float(row.low),
            "close": float(row.close),
        }
        for idx, row in tail.iterrows()
    ]


def atr_estimate(df: pd.DataFrame, n: int = 20) -> float:
    """Simple average true range over the last ``n`` bars (pure pandas).

    ATR = mean(max(high-low, |high-prev_close|, |low-prev_close|)). The same
    shape the project's ``strategy/filters.py`` uses for its ATR filter, so the
    model and the deterministic filters read the same volatility number.
    """
    if len(df) < 2:
        return float("nan")
    tail = df.tail(n)
    prev_close = tail["close"].shift(1)
    tr = pd.concat(
        [
            tail["high"] - tail["low"],
            (tail["high"] - prev_close).abs(),
            (tail["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return float(tr.mean())


@dataclass(frozen=True)
class TradeContext:
    """Everything the model sees when judging ONE deterministic setup."""

    symbol: str
    timeframe: str
    bar_time: str
    last_bars: list[dict]
    resistance: float
    support: float
    entry: float
    sl: float
    tp: float
    stop_distance: float
    reward_risk: float
    change_pct: float
    atr_estimate: float
    session_hour: int
    balance: float | None
    max_loss_pct: float


def build_trade_context(
    df: pd.DataFrame,
    cfg,
    entry: float,
    sl: float,
    tp: float,
    bar_time,
    balance: float | None = None,
    n_bars: int = 20,
) -> TradeContext:
    """Snapshot one deterministic setup for the model.

    ``df`` must already carry ``resistance``/``support`` (the output of
    ``strategy.levels.support_resistance``). ``entry``/``sl``/``tp`` are the
    deterministic trade levels (resistance, support-buffer, target) — the model
    sees them but does not set them.
    """
    if df.empty:
        raise ValueError("cannot build a trade context from an empty frame")
    last = df.iloc[-1]
    stop_distance = entry - sl
    reward_risk = (tp - entry) / stop_distance if stop_distance > 0 else float("nan")
    change_pct = (
        (float(last.close) / float(df["close"].iloc[-n_bars]) - 1.0) * 100.0
        if len(df) >= n_bars and float(df["close"].iloc[-n_bars]) != 0
        else float("nan")
    )
    return TradeContext(
        symbol=cfg.data.symbol,
        timeframe=cfg.data.timeframe,
        bar_time=str(bar_time),
        last_bars=_last_bars(df, n_bars),
        resistance=float(last["resistance"]),
        support=float(last["support"]),
        entry=float(entry),
        sl=float(sl),
        tp=float(tp),
        stop_distance=float(stop_distance),
        reward_risk=float(reward_risk),
        change_pct=float(change_pct),
        atr_estimate=atr_estimate(df, n_bars),
        session_hour=int(bar_time.hour),
        balance=balance,
        max_loss_pct=cfg.risk.max_loss_pct_per_trade,
    )


@dataclass(frozen=True)
class RegimeContext:
    """Everything the model sees for the once-per-day regime read."""

    symbol: str
    as_of: str
    days: list[dict]
    n_days: int
    up_days_frac: float | None
    avg_daily_range_pct: float | None
    price_change_pct: float
    recent_avg_r: float | None
    recent_trades: int
    # Optional news-sentiment snapshot (plan 03-04): {date, score, articles,
    # top_titles}. None = no news today (the regime read proceeds unchanged,
    # fail-open).
    sentiment: dict | None = None


def build_regime_context(
    df: pd.DataFrame,
    cfg,
    recent_avg_r: float | None = None,
    recent_trades: int = 0,
    window_days: int = 20,
    sentiment: dict | None = None,
) -> RegimeContext:
    """Resample the bars to daily closes and describe the recent regime.

    ``recent_avg_r``/``recent_trades`` let the caller (live engine or
    backtester) tell the model how the strategy has actually been doing in R
    multiples — the honest, size-independent performance number this project
    tracks. Pure pandas; never touches the network.
    """
    if df.empty:
        raise ValueError("cannot build a regime context from an empty frame")
    daily = df.resample("1D").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()
    daily = daily.tail(window_days)
    if daily.empty:
        raise ValueError("no daily bars in the frame for the regime context")

    prev_close = daily["close"].shift(1)
    change = daily["close"].pct_change() * 100.0
    range_pct = (daily["high"] - daily["low"]) / prev_close * 100.0

    days = [
        {
            "date": str(idx.date()),
            "open": float(row.open),
            "high": float(row.high),
            "low": float(row.low),
            "close": float(row.close),
            "change_pct": float(c) if c == c else None,  # NaN -> None
        }
        for (idx, row), c in zip(daily.iterrows(), change)
    ]
    up = (change.dropna() > 0).mean()
    price_change = (
        (float(daily["close"].iloc[-1]) / float(daily["close"].iloc[0]) - 1.0) * 100.0
        if float(daily["close"].iloc[0]) != 0
        else float("nan")
    )
    range_series = range_pct.dropna()
    return RegimeContext(
        symbol=cfg.data.symbol,
        as_of=str(df.index[-1]),
        days=days,
        n_days=len(daily),
        # None (not NaN) when a metric cannot be computed — a single daily bar
        # has no up-day fraction or mean range. None renders as "unknown" in the
        # prompt; NaN would render as "nan", which a model may read as a number.
        up_days_frac=float(up) if up == up and not pd.isna(up) else None,
        avg_daily_range_pct=float(range_series.mean()) if not range_series.empty else None,
        price_change_pct=float(price_change) if price_change == price_change else float("nan"),
        recent_avg_r=recent_avg_r,
        recent_trades=recent_trades,
        sentiment=sentiment,
    )
