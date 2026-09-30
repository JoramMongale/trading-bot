"""Tests for the keyless Yahoo macro fetcher (quick 20260928-gold-dxy-sentiment-gate).

Offline: ``urllib.request.urlopen`` is monkeypatched with a fixture server, so
no network ever happens. Covers parse (ascending daily Series, float closes,
normalized UTC midnight, null-close holiday drop, dedupe keep-last), cache
write/read (zero network on the second call, refresh refetches), the Yahoo
chart URL encoding for ``^TNX``, the DXY-vs-own-MA gold-bullishness
normalization, the yield-rising regime helper, and the fail-closed fetch (a
fetch failure with no cache raises).
"""

import json
import urllib.error

import numpy as np
import pandas as pd
import pytest

from trading_bot.news import macro
from trading_bot.news.macro import (
    _chart_url,
    _parse_chart,
    is_yield_rising,
    load_dxy,
    to_gold_bullishness,
)


class _FakeResp:
    def __init__(self, body: bytes, status: int = 200):
        self.body = body
        self.status = status

    def read(self, n: int = -1):
        return self.body[:n] if n >= 0 else self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# Deliberately reverse-chronological (Yahoo returns most-recent-first), with
# timestamps as unix-seconds STRINGS (UTC midnight) and one null close (market
# holiday) to exercise the holiday drop. Dates: 07-01, 06-30, 06-29.
_FIXTURE_RESULT = {
    "timestamp": ["1782864000", "1782777600", "1782691200"],
    "indicators": {"quote": [{"close": [103.5, None, 102.0]}]},
}
_FIXTURE_PAYLOAD = {"chart": {"result": [_FIXTURE_RESULT], "error": None}}


def _patch_urlopen(monkeypatch, responses):
    """Point urlopen at a fixture map url -> _FakeResp / Exception."""

    def _urlopen(req, timeout=None):
        resp = responses[req.full_url]
        if isinstance(resp, Exception):
            raise resp
        return resp

    monkeypatch.setattr(macro.urllib.request, "urlopen", _urlopen)


def test_parse_chart_returns_ascending_daily_series():
    s = _parse_chart(_FIXTURE_PAYLOAD, macro.DX_SYMBOL)
    # 06-30 had a null close -> dropped; remaining ascending.
    expected = pd.DatetimeIndex(["2026-06-29", "2026-07-01"], tz="UTC")
    assert list(s.index) == list(expected)
    # normalized UTC midnight (no hour/minute component)
    assert (s.index.hour == 0).all() and (s.index.minute == 0).all()
    assert list(s.values) == [102.0, 103.5]
    assert all(isinstance(v, float) for v in s.values)
    assert s.name == macro.DX_SYMBOL


def test_parse_chart_drops_duplicate_dates_keep_last():
    dup_result = {
        "timestamp": ["1782864000", "1782691200", "1782691200"],
        "indicators": {"quote": [{"close": [103.5, 102.0, 102.9]}]},
    }
    s = _parse_chart({"chart": {"result": [dup_result], "error": None}},
                     macro.DX_SYMBOL)
    assert len(s) == 2
    assert s.loc[pd.Timestamp("2026-06-29", tz="UTC")] == 102.9


def test_parse_chart_raises_on_missing_result():
    with pytest.raises(ValueError):
        _parse_chart({"chart": {"result": [], "error": None}}, macro.DX_SYMBOL)
    with pytest.raises(ValueError):
        _parse_chart({"chart": {"result": [{"timestamp": [], "indicators": {
            "quote": [{"close": []}]}}], "error": None}}, macro.DX_SYMBOL)


def test_load_dxy_caches_and_reads_without_network(tmp_path, monkeypatch):
    cache = tmp_path / "dxy.json"
    calls = {"n": 0}

    def _urlopen(req, timeout=None):
        calls["n"] += 1
        return _FakeResp(json.dumps(_FIXTURE_PAYLOAD).encode())

    monkeypatch.setattr(macro.urllib.request, "urlopen", _urlopen)

    first = load_dxy(cache_path=cache)
    assert calls["n"] == 1
    assert cache.exists()
    # the raw chart.result[0] object (timestamp + quote close) is cached
    assert json.loads(cache.read_text(encoding="utf-8")) == _FIXTURE_RESULT

    second = load_dxy(cache_path=cache)
    assert calls["n"] == 1  # zero network on the second call
    assert second.equals(first)

    third = load_dxy(cache_path=cache, refresh=True)
    assert calls["n"] == 2  # refresh refetches
    assert third.equals(first)


def test_chart_url_quotes_tnx_symbol():
    url = _chart_url(macro.TNX_SYMBOL)
    assert "%5ETNX" in url
    assert "^" not in url
    # DXY symbol needs no escaping and is preserved
    assert macro.DX_SYMBOL in _chart_url(macro.DX_SYMBOL)


def test_to_gold_bullishness_direction_and_bounds():
    days = pd.date_range("2026-01-01", periods=12, freq="D", tz="UTC")
    # strictly DECREASING DXY -> below its own MA -> weak dollar -> value > 50
    falling = pd.Series(np.linspace(110.0, 100.0, 12), index=days)
    bull = to_gold_bullishness(falling, window=5)
    # warm-up rows (first window-1) are NaN
    assert bull.iloc[:4].isna().all()
    assert (bull.iloc[4:] > 50.0).all()

    # strictly INCREASING DXY -> above its own MA -> strong dollar -> value < 50
    rising = pd.Series(np.linspace(100.0, 110.0, 12), index=days)
    bear = to_gold_bullishness(rising, window=5)
    assert (bear.iloc[4:] < 50.0).all()

    # constant DXY -> dev == 0 -> exactly 50 after warm-up
    flat = pd.Series(105.0, index=days)
    neutral = to_gold_bullishness(flat, window=5)
    assert (neutral.iloc[4:] == 50.0).all()

    # bounded in (0, 100) everywhere a value exists
    for s in (bull, bear, neutral):
        finite = s.dropna()
        assert (finite > 0.0).all() and (finite < 100.0).all()
    assert bull.name == "dxy_bullishness"


def test_is_yield_rising():
    days = pd.date_range("2026-01-01", periods=8, freq="D", tz="UTC")
    tnx = pd.Series([4.0, 4.1, 4.2, 4.3, 4.4, 4.5, 4.4, 4.3], index=days)
    out = is_yield_rising(tnx, window=3)
    # warm-up rows are NaN (before a full window exists)
    assert out.iloc[:2].isna().all()
    # a value above its trailing mean is True, below is False
    assert out.iloc[5] is True    # 4.5 > mean(4.3,4.4,4.5)
    assert out.iloc[7] is False   # 4.3 < mean(4.4,4.5,4.4)


def test_fetch_failure_with_no_cache_raises(tmp_path, monkeypatch):
    cache = tmp_path / "dxy.json"
    _patch_urlopen(
        monkeypatch,
        {macro._chart_url(macro.DX_SYMBOL): urllib.error.HTTPError(
            macro._chart_url(macro.DX_SYMBOL), 503, "unavailable", None, None)},
    )
    with pytest.raises(urllib.error.HTTPError):
        load_dxy(cache_path=cache)
