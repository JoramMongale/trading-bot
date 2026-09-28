"""Tests for the keyless Crypto Fear & Greed fetcher (quick 20260928-btc-fear-greed).

Offline: ``urllib.request.urlopen`` is monkeypatched with a fixture server, so
no network ever happens. Covers parse (ascending daily Series, float values,
normalized UTC midnight, dedupe keep-last), cache write/read (zero network on
the second call, refresh refetches), map_to_bars shift(1) no-lookahead, and the
fail-closed fetch (a fetch failure with no cache raises).
"""

import json
import urllib.error

import pandas as pd
import pytest

from trading_bot.news import fear_greed
from trading_bot.news.fear_greed import load_fear_greed, map_to_bars, _parse


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


# Deliberately reverse-chronological (the API returns most-recent-first), with
# `value` as STRING ints and `timestamp` as STRING unix-seconds (UTC midnight).
_FIXTURE_DATA = [
    {"value": "72", "value_classification": "greed", "timestamp": "1782864000"},   # 2026-07-01
    {"value": "25", "value_classification": "fear", "timestamp": "1782777600"},    # 2026-06-30
    {"value": "50", "value_classification": "neutral", "timestamp": "1782691200"},  # 2026-06-29
]
_FIXTURE_PAYLOAD = {"name": "Fear and Greed Index", "data": _FIXTURE_DATA}


def _patch_urlopen(monkeypatch, responses):
    """Point urlopen at a fixture map url -> _FakeResp / Exception."""

    def _urlopen(req, timeout=None):
        resp = responses[req.full_url]
        if isinstance(resp, Exception):
            raise resp
        return resp

    monkeypatch.setattr(fear_greed.urllib.request, "urlopen", _urlopen)


def test_parse_returns_ascending_daily_series():
    s = _parse(_FIXTURE_PAYLOAD)
    expected = pd.DatetimeIndex(
        ["2026-06-29", "2026-06-30", "2026-07-01"], tz="UTC"
    )
    assert list(s.index) == list(expected)
    # normalized UTC midnight (no hour/minute component)
    assert (s.index.hour == 0).all() and (s.index.minute == 0).all()
    assert list(s.values) == [50.0, 25.0, 72.0]
    assert all(isinstance(v, float) for v in s.values)
    assert s.name == "fng"


def test_parse_drops_duplicate_dates_keep_last():
    dup = _FIXTURE_DATA + [
        {"value": "99", "value_classification": "greed", "timestamp": "1782691200"}
    ]
    s = _parse({"data": dup})
    assert len(s) == 3
    assert s.loc[pd.Timestamp("2026-06-29", tz="UTC")] == 99.0


def test_load_fear_greed_caches_and_reads_without_network(tmp_path, monkeypatch):
    cache = tmp_path / "fear_greed.json"
    calls = {"n": 0}

    def _urlopen(req, timeout=None):
        calls["n"] += 1
        return _FakeResp(json.dumps(_FIXTURE_PAYLOAD).encode())

    monkeypatch.setattr(fear_greed.urllib.request, "urlopen", _urlopen)

    first = load_fear_greed(cache_path=cache)
    assert calls["n"] == 1
    assert cache.exists()
    assert json.loads(cache.read_text(encoding="utf-8")) == _FIXTURE_DATA

    second = load_fear_greed(cache_path=cache)
    assert calls["n"] == 1  # zero network on the second call
    assert second.equals(first)

    third = load_fear_greed(cache_path=cache, refresh=True)
    assert calls["n"] == 2  # refresh refetches
    assert third.equals(first)


def test_map_to_bars_shifts_one_day_no_lookahead():
    days = pd.date_range("2026-06-01", periods=4, freq="D", tz="UTC")
    daily = pd.Series([10.0, 20.0, 30.0, 40.0], index=days, name="fng")
    bars = pd.date_range("2026-06-01 12:00", periods=4, freq="D", tz="UTC")
    mapped = map_to_bars(daily, bars)
    # leading bar sees NaN (before the first shifted day)
    assert pd.isna(mapped.iloc[0])
    # a bar on day D sees day D-1's value
    assert mapped.iloc[1] == 10.0
    assert mapped.iloc[2] == 20.0
    assert mapped.iloc[3] == 30.0


def test_fetch_failure_with_no_cache_raises(tmp_path, monkeypatch):
    cache = tmp_path / "fear_greed.json"
    _patch_urlopen(
        monkeypatch,
        {fear_greed.FNG_URL: urllib.error.HTTPError(
            fear_greed.FNG_URL, 503, "unavailable", None, None)},
    )
    with pytest.raises(urllib.error.HTTPError):
        load_fear_greed(cache_path=cache)
