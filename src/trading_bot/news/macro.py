"""Keyless Yahoo chart fetcher for DXY + US10Y and macro-regime helpers (quick
task 20260928-gold-dxy-sentiment-gate).

stdlib only: ``urllib`` + ``json`` (+ ``numpy``). Fetches the free, keyless
Yahoo Finance chart API daily closes for the US Dollar Index (``DX-Y.NYB``) and
the 10-year Treasury yield (``^TNX``), caches each locally to a JSON file so the
backtest is reproducible offline, and exposes the DXY-regime normalization that
turns "DXY vs its own moving average" into a 0-100 gold-bullishness scale.

Trust boundary (threat T-dxy-01): the remote Yahoo JSON is untrusted input.
Defenses: stdlib ``json.loads`` only (no code execution); non-200 statuses and
bodies > ``MAX_BODY_BYTES`` rejected before parsing; a missing/empty
``chart.result[0].indicators.quote[0].close`` raises (loud, not silent).
Unlike the RSS news pipeline (which is fail-open because it is a convenience),
these series are backtest INPUTS: a fetch failure with no cache RAISES, because
a silent miss would corrupt the measurement.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

DX_SYMBOL = "DX-Y.NYB"
TNX_SYMBOL = "^TNX"

MAX_BODY_BYTES = 2 * 1024 * 1024
USER_AGENT = "trading-bot/0.1 (+personal research)"
# Fractional DXY deviation that maps to tanh(1) in the gold-bullishness scale.
# Documented a-priori: DXY rarely deviates more than ~5% from a 50/200d MA, so
# this keeps the output well inside (0, 100) in practice.
GOLD_BULLISH_SCALE = 0.05

# Deterministic period2 (2100-01-01 UTC); Yahoo clamps it to "now". We use
# explicit period1/period2 instead of ``range=max`` because ``range=max``
# downsamples a multi-decade index to 3-month granularity (``dataGranularity:
# "3mo"``), which is useless for a 50/200-day MA regime gate -- the 200-day MA
# would be all-NaN and the 50-day MA a degenerate single-value fill.
_CHART_PERIOD2 = 4102444800  # 2100-01-01


def _chart_url(symbol: str) -> str:
    """The Yahoo chart API URL for ``symbol`` (``^TNX`` -> ``%5ETNX``).

    ``period1=0`` fetches from the symbol's first trade date, giving the full
    daily close history (DXY: 17k+ bars back to 1971; ^TNX: 14k+ bars back to
    1970) at daily granularity.
    """
    quoted = urllib.parse.quote(symbol, safe="")
    return (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{quoted}?period1=0&period2={_CHART_PERIOD2}&interval=1d"
    )


def _http_get_json(url: str, timeout: float = 15.0) -> dict:
    """GET a JSON document with the configured UA + timeout; raises on failure.

    Rejects non-200 statuses and bodies over ``MAX_BODY_BYTES`` before they
    reach the parser (T-dxy-01 / T-dxy-02).
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        if resp.status != 200:
            raise urllib.error.HTTPError(url, resp.status, f"status {resp.status}",
                                         None, None)
        body = resp.read(MAX_BODY_BYTES + 1)
        if len(body) > MAX_BODY_BYTES:
            raise urllib.error.URLError(f"response too large ({len(body)} bytes)")
        return json.loads(body)


def _parse_chart(payload: dict, symbol: str) -> pd.Series:
    """Parse a Yahoo chart payload into an ascending daily close Series.

    Takes ``chart.result[0]``, zips ``timestamp`` (unix-seconds, UTC midnight)
    with ``indicators.quote[0].close``, drops null closes (market holidays),
    sorts ascending, and dedupes duplicate dates keep-last. Raises ValueError
    if ``result`` / ``quote[0]`` / ``close`` is missing or empty (loud).
    """
    try:
        result = payload["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError):
        raise ValueError(f"{symbol} chart payload missing result/quote/close")
    if not timestamps or not closes:
        raise ValueError(f"{symbol} chart payload has empty timestamp/close")
    idx = [pd.to_datetime(int(ts), unit="s", utc=True).normalize() for ts in timestamps]
    s = pd.Series(closes, index=pd.DatetimeIndex(idx), name=symbol, dtype="float64")
    s = s.dropna()
    s = s.sort_index()
    return s[~s.index.duplicated(keep="last")]


def fetch_dxy(url: str | None = None, timeout: float = 15.0) -> pd.Series:
    """Fetch and parse the daily DXY series (no caching)."""
    return _parse_chart(
        _http_get_json(url or _chart_url(DX_SYMBOL), timeout), DX_SYMBOL)


def fetch_tnx(url: str | None = None, timeout: float = 15.0) -> pd.Series:
    """Fetch and parse the daily ^TNX series (no caching)."""
    return _parse_chart(
        _http_get_json(url or _chart_url(TNX_SYMBOL), timeout), TNX_SYMBOL)


def _load_series(
    cache_path: str | Path,
    url: str,
    symbol: str,
    timeout: float,
    refresh: bool,
) -> pd.Series:
    """Shared fetch-once + JSON-cache + fail-closed loader for a daily series."""
    cache = Path(cache_path)
    if cache.exists() and not refresh:
        raw = json.loads(cache.read_text(encoding="utf-8"))
        return _parse_chart({"chart": {"result": [raw]}}, symbol)
    payload = _http_get_json(url, timeout)
    result = payload.get("chart", {}).get("result")
    if not result:
        raise ValueError(f"{symbol} chart payload missing/empty 'chart.result'")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(result[0]), encoding="utf-8")
    return _parse_chart(payload, symbol)


def load_dxy(
    cache_path: str | Path = "data/processed/dxy.json",
    url: str | None = None,
    timeout: float = 15.0,
    refresh: bool = False,
) -> pd.Series:
    """Load the daily DXY series, fetching once and caching to JSON.

    On a cache miss (or ``refresh=True``) the network is hit exactly once and
    the raw ``chart.result[0]`` object (timestamp + quote close) is written to
    ``cache_path``; every later call reads the cache with ZERO network. A fetch
    failure with no cache RAISES -- the series is a backtest INPUT.
    """
    return _load_series(cache_path, url or _chart_url(DX_SYMBOL), DX_SYMBOL,
                        timeout, refresh)


def load_tnx(
    cache_path: str | Path = "data/processed/tnx.json",
    url: str | None = None,
    timeout: float = 15.0,
    refresh: bool = False,
) -> pd.Series:
    """Load the daily ^TNX series, fetching once and caching to JSON."""
    return _load_series(cache_path, url or _chart_url(TNX_SYMBOL), TNX_SYMBOL,
                        timeout, refresh)


def to_gold_bullishness(dxy: pd.Series, window: int) -> pd.Series:
    """Map DXY-vs-its-own-MA deviation to a 0-100 gold-bullishness scale.

    The non-negotiable pitfall this exists to avoid: the raw DXY *level* is not
    stationary across decades, so gating on it would let the long-run dollar
    trend dominate the 0-100 normalization. Instead we gate on the FRACTIONAL
    DEVIATION of DXY from its own trailing MA (regime, not level)::

        ma  = dxy.rolling(window).mean()
        dev = dxy / ma - 1.0
        return 50.0 * (1.0 - tanh(dev / GOLD_BULLISH_SCALE))

    So: weak dollar (DXY below its MA, dev < 0) -> value > 50 (bullish gold);
    strong dollar (dev > 0) -> value < 50 (bearish gold); dev == 0 -> exactly
    50 (neutral). Output is bounded in (0, 100), monotonic decreasing in dev,
    and NaN before the window is full.
    """
    ma = dxy.rolling(window=window, min_periods=window).mean()
    dev = dxy / ma - 1.0
    out = 50.0 * (1.0 - np.tanh(dev / GOLD_BULLISH_SCALE))
    out.name = "dxy_bullishness"
    return out


def is_yield_rising(tnx: pd.Series, window: int) -> pd.Series:
    """Yield regime: True where TNX is above its own trailing MA.

    ``tnx > tnx.rolling(window).mean()``, NaN before the window is full (a NaN
    regime is treated fail-open downstream, like the news fail-open convention).
    """
    ma = tnx.rolling(window=window, min_periods=window).mean()
    return (tnx > ma).where(ma.notna())
