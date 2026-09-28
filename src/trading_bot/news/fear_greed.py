"""Keyless Crypto Fear & Greed Index fetcher (quick task 20260928-btc-fear-greed).

stdlib only: ``urllib`` + ``json``. Fetches the free, keyless alternative.me
Fear & Greed Index (0 = extreme fear, 100 = extreme greed) as a daily series,
caches it locally to a JSON file so the backtest is reproducible offline, and
maps it onto M5 bars with a one-day no-lookahead shift.

Trust boundary (threat T-fng-01): the remote JSON is untrusted input. Defenses:
stdlib ``json.loads`` only (no code execution); non-200 statuses and bodies >
``MAX_BODY_BYTES`` rejected before parsing; a missing/empty ``data`` key raises
(loud, not silent). Unlike the RSS news pipeline (which is fail-open because it
is a convenience), this series is a backtest INPUT: a fetch failure with no
cache RAISES, because a silent miss would corrupt the measurement.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

FNG_URL = "https://api.alternative.me/fng/?limit=0&format=json"
MAX_BODY_BYTES = 2 * 1024 * 1024
USER_AGENT = "trading-bot/0.1 (+personal research)"


def _http_get_json(url: str, timeout: float = 15.0) -> dict:
    """GET a JSON document with the configured UA + timeout; raises on failure.

    Rejects non-200 statuses and bodies over ``MAX_BODY_BYTES`` before they
    reach the parser (T-fng-01 / T-fng-02).
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


def _parse(data: dict) -> pd.Series:
    """Parse the F&G payload into an ascending daily 0-100 Series.

    ``value`` is a STRING int 0-100; ``timestamp`` is a STRING unix-seconds
    (UTC midnight of the day it describes). Dates are normalized to UTC
    midnight, sorted ascending, and duplicate dates keep the last value.
    Raises ValueError if ``data`` is missing/empty (loud, not silent).
    """
    entries = data.get("data")
    if not entries:
        raise ValueError("Fear & Greed payload missing/empty 'data' key")
    idx = []
    vals = []
    for entry in entries:
        day = pd.to_datetime(int(entry["timestamp"]), unit="s", utc=True).normalize()
        idx.append(day)
        vals.append(float(entry["value"]))
    s = pd.Series(vals, index=pd.DatetimeIndex(idx), name="fng", dtype="float64")
    s = s.sort_index()
    return s[~s.index.duplicated(keep="last")]


def fetch_fear_greed(url: str = FNG_URL, timeout: float = 15.0) -> pd.Series:
    """Fetch and parse the daily F&G series (no caching)."""
    return _parse(_http_get_json(url, timeout))


def load_fear_greed(
    cache_path: str | Path = "data/processed/fear_greed.json",
    url: str = FNG_URL,
    timeout: float = 15.0,
    refresh: bool = False,
) -> pd.Series:
    """Load the daily F&G series, fetching once and caching to JSON.

    On a cache miss (or ``refresh=True``) the network is hit exactly once and
    the raw ``data`` list is written to ``cache_path``; every later call reads
    the cache with ZERO network. A fetch failure with no cache RAISES -- the
    series is a backtest INPUT, not a convenience.
    """
    cache = Path(cache_path)
    if cache.exists() and not refresh:
        raw = json.loads(cache.read_text(encoding="utf-8"))
        return _parse({"data": raw})
    payload = _http_get_json(url, timeout)
    raw = payload.get("data")
    if not raw:
        raise ValueError("Fear & Greed payload missing/empty 'data' key")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(raw), encoding="utf-8")
    return _parse(payload)


def map_to_bars(daily: pd.Series, index: pd.Index) -> pd.Series:
    """Map a daily series onto a bar index with one-day no-lookahead.

    A Fear & Greed value for day D is only known from day D+1 onward, so the
    daily series is shifted by one day (``daily.shift(1)``) before being
    forward-filled onto the bar index: a bar at time T sees only the most
    recent COMPLETED daily value. The leading bar (before the first shifted
    day) stays NaN, which the engine's gate treats as neutral/fail-open.
    """
    return daily.shift(1).reindex(index, method="ffill")
