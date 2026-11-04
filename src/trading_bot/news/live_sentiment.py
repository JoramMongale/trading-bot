"""Live sentiment -> trade direction, for the poll loop.

One entry point, :func:`resolve`, turns a sentiment source into "long",
"short" or None (no override: the engine falls back to ``[strategy]
direction``). Three sources, each a daily series mapped onto a 0-100
"bullishness for THIS symbol" scale:

- ``dxy`` (gold): US dollar index vs its own trailing MA. Weak dollar ->
  bullish gold. Same mapping the 20260928-dxy backtest measured.
- ``fng`` (BTC): Crypto Fear & Greed index, used as-is (0-100). Greed ->
  bullish. Same mapping the 20260928-btc-fear-greed backtest measured.
- ``vix`` (JPY crosses, e.g. EURJPY): VIX vs its own trailing MA. Calm
  markets (VIX below its MA, "risk-on") -> yen weakens -> bullish for
  XXX/JPY. NOT yet backtested.

What this adds over the backtest loaders, which read a cache once and never
refetch (fine for a backtest, wrong for a bot that runs for weeks):

- The cache is refetched once it is older than ``cache_max_age_hours``. If
  the refetch fails, the stale cache is still used.
- Only COMPLETED days count: a row dated today (UTC) is dropped, matching the
  backtest's one-day no-lookahead shift.
- If the newest completed day is older than ``max_stale_days``, the signal is
  treated as unavailable (None) rather than trading on old data.

Every failure returns None with a reason: sentiment picks a side, it is not a
safety device, and an outage must not stop the bot.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

SOURCES = ("dxy", "fng", "vix")

VIX_SYMBOL = "^VIX"
# VIX swings far more than DXY (a 20% move vs its MA is ordinary), so its
# deviation is scaled 4x wider than gold's 0.05 before the tanh squash.
VIX_RISK_SCALE = 0.20

DEFAULT_CACHE = {
    "dxy": "data/processed/dxy.json",
    "fng": "data/processed/fear_greed.json",
    "vix": "data/processed/vix.json",
}


@dataclass(frozen=True)
class Reading:
    """One resolved sentiment reading (everything the decision log needs)."""

    direction: str | None       # "long" | "short" | None
    bullishness: float | None   # 0-100, None when unavailable
    as_of: str | None           # ISO date of the completed day used
    reason: str                 # "ok" | "neutral" | why it is unavailable


def _cache_is_stale(path: Path, max_age_hours: float, now: float) -> bool:
    if not path.exists():
        return True
    return (now - path.stat().st_mtime) > max_age_hours * 3600.0


def _load(source: str, cache_path: str, refresh: bool) -> pd.Series:
    """Load the raw daily series for ``source`` (raises on failure)."""
    if source == "dxy":
        from trading_bot.news.macro import load_dxy

        return load_dxy(cache_path=cache_path, refresh=refresh)
    if source == "fng":
        from trading_bot.news.fear_greed import load_fear_greed

        return load_fear_greed(cache_path=cache_path, refresh=refresh)
    if source == "vix":
        from trading_bot.news.macro import _chart_url, _load_series

        return _load_series(cache_path, _chart_url(VIX_SYMBOL), VIX_SYMBOL,
                            15.0, refresh)
    if source == "tnx":  # US 10-year yield, used by the veto_longs mode only
        from trading_bot.news.macro import load_tnx

        return load_tnx(cache_path=cache_path, refresh=refresh)
    raise ValueError(f"unknown sentiment source {source!r}")


def load_fresh(source: str, cache_path: str, cache_max_age_hours: float,
               now: float | None = None) -> pd.Series:
    """Daily series, refetched when the cache is old; stale cache on failure."""
    now = time.time() if now is None else now
    path = Path(cache_path)
    if _cache_is_stale(path, cache_max_age_hours, now):
        try:
            return _load(source, cache_path, refresh=True)
        except Exception:  # noqa: BLE001 — fall back to whatever is cached
            if not path.exists():
                raise
    return _load(source, cache_path, refresh=False)


def to_bullishness(source: str, daily: pd.Series, window: int) -> pd.Series:
    """Map a raw daily series onto 0-100 bullishness for the traded symbol."""
    if source == "fng":
        return daily.astype("float64")
    if source == "dxy":
        from trading_bot.news.macro import to_gold_bullishness

        return to_gold_bullishness(daily, window)
    if source == "vix":
        ma = daily.rolling(window=window, min_periods=window).mean()
        dev = daily / ma - 1.0
        out = 50.0 * (1.0 - np.tanh(dev / VIX_RISK_SCALE))
        out.name = "vix_risk_on"
        return out
    raise ValueError(f"unknown sentiment source {source!r}")


def _completed_days(series: pd.Series, today: pd.Timestamp) -> pd.Series:
    """Drop rows dated today or later (UTC): today's value is not final."""
    idx = pd.DatetimeIndex(series.index)
    if idx.tz is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    days = idx.normalize()
    return series[days < today]


def direction_for(bullishness: float | None, band: float) -> str | None:
    """>= 50+band -> long, <= 50-band -> short, otherwise None."""
    from trading_bot.news.macro import dxy_direction

    return dxy_direction(bullishness, band=band)


def resolve(
    source: str,
    *,
    cache_path: str,
    window: int,
    band: float,
    cache_max_age_hours: float = 12.0,
    max_stale_days: float = 5.0,
    now: float | None = None,
) -> Reading:
    """Resolve ``source`` to a trade direction. Never raises."""
    now = time.time() if now is None else now
    today = pd.Timestamp(now, unit="s").normalize()
    try:
        daily = load_fresh(source, cache_path, cache_max_age_hours, now=now)
        bull = _completed_days(to_bullishness(source, daily, window), today).dropna()
    except Exception as exc:  # noqa: BLE001 — fail-open
        return Reading(None, None, None, f"load_failed: {type(exc).__name__}: {exc}")
    if bull.empty:
        return Reading(None, None, None, "no_completed_data")
    last_day = pd.Timestamp(bull.index[-1])
    if last_day.tz is not None:
        last_day = last_day.tz_convert("UTC").tz_localize(None)
    last_day = last_day.normalize()
    value = float(bull.iloc[-1])
    age_days = (today - last_day).days
    if age_days > max_stale_days:
        return Reading(None, value, last_day.date().isoformat(),
                       f"stale: newest completed day is {age_days} days old")
    direction = direction_for(value, band)
    return Reading(direction, value, last_day.date().isoformat(),
                   "ok" if direction else "neutral")


@dataclass(frozen=True)
class Veto:
    """Gold macro-headwind reading (``[sentiment] mode = "veto_longs"``)."""

    veto_longs: bool            # True -> skip LONG setups
    dxy_bullishness: float | None
    yield_rising: bool | None
    as_of: str | None
    reason: str                 # "ok" | why it is unavailable (-> no veto)


def macro_headwind(
    *,
    dxy_cache_path: str,
    tnx_cache_path: str,
    window: int,
    yield_window: int,
    band: float,
    cache_max_age_hours: float = 12.0,
    max_stale_days: float = 5.0,
    now: float | None = None,
) -> Veto:
    """Is the macro against gold? DXY strong AND 10-year yield rising.

    The composite from quick 260928-dxy: veto longs when DXY bullishness is
    <= 50 - band (vs its ``window``-day MA) AND ^TNX is above its
    ``yield_window``-day MA, both on the last COMPLETED day. Either series
    unavailable or stale -> no veto (fail-open, like the direction mode).
    Never raises.
    """
    dxy = resolve("dxy", cache_path=dxy_cache_path, window=window, band=band,
                  cache_max_age_hours=cache_max_age_hours,
                  max_stale_days=max_stale_days, now=now)
    if dxy.bullishness is None or dxy.reason.startswith(("stale", "load_failed")):
        return Veto(False, dxy.bullishness, None, dxy.as_of, f"dxy {dxy.reason}")
    now = time.time() if now is None else now
    today = pd.Timestamp(now, unit="s").normalize()
    try:
        tnx = load_fresh("tnx", tnx_cache_path, cache_max_age_hours, now=now)
        tnx = _completed_days(tnx, today).dropna()
        ma = tnx.rolling(window=yield_window, min_periods=yield_window).mean()
        rising = (tnx > ma).where(ma.notna()).dropna()
    except Exception as exc:  # noqa: BLE001 — fail-open
        return Veto(False, dxy.bullishness, None, dxy.as_of,
                    f"tnx load_failed: {type(exc).__name__}: {exc}")
    if rising.empty:
        return Veto(False, dxy.bullishness, None, dxy.as_of, "tnx no_completed_data")
    last_day = pd.Timestamp(rising.index[-1])
    if last_day.tz is not None:
        last_day = last_day.tz_convert("UTC").tz_localize(None)
    if (today - last_day.normalize()).days > max_stale_days:
        return Veto(False, dxy.bullishness, None, dxy.as_of, "tnx stale")
    yield_rising = bool(rising.iloc[-1])
    dxy_strong = dxy.bullishness <= 50.0 - band
    return Veto(dxy_strong and yield_rising, dxy.bullishness, yield_rising,
                dxy.as_of, "ok")
