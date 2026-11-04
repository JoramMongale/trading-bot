"""Tests for news.live_sentiment — the live sentiment -> direction resolver.

No network: the per-source loader is monkeypatched. Covers the mappings for
all three sources, cache refresh, the stale-data refusal and the
completed-day (no-lookahead) rule.
"""

import os

import numpy as np
import pandas as pd
import pytest

from trading_bot.config import load_config
from trading_bot.news import live_sentiment as ls

# 2026-11-04 12:00 UTC (a Wednesday)
NOW = pd.Timestamp("2026-11-04 12:00", tz="UTC").timestamp()


def _daily(values, end="2026-11-04"):
    idx = pd.date_range(end=end, periods=len(values), freq="D", tz="UTC")
    return pd.Series(values, index=idx, dtype="float64")


def _fake_loader(series, calls=None):
    def _load(source, cache_path, refresh):
        if calls is not None:
            calls.append(refresh)
        return series
    return _load


def _resolve(source, monkeypatch, tmp_path, series, **kw):
    monkeypatch.setattr(ls, "_load", _fake_loader(series))
    cache = tmp_path / f"{source}.json"
    cache.write_text("{}")
    return ls.resolve(source, cache_path=str(cache), window=kw.pop("window", 5),
                      band=kw.pop("band", 10.0), now=NOW, **kw)


# --- mappings -----------------------------------------------------------------


def test_fng_greed_is_long_and_fear_is_short(monkeypatch, tmp_path):
    # last row (today) is dropped; yesterday's value decides
    greed = _resolve("fng", monkeypatch, tmp_path, _daily([50, 75, 5]))
    fear = _resolve("fng", monkeypatch, tmp_path, _daily([50, 20, 95]))
    neutral = _resolve("fng", monkeypatch, tmp_path, _daily([50, 55, 5]))
    assert (greed.direction, greed.bullishness, greed.as_of) == ("long", 75.0, "2026-11-03")
    assert fear.direction == "short"
    assert neutral.direction is None and neutral.reason == "neutral"


def test_dxy_weak_dollar_is_long_for_gold(monkeypatch, tmp_path):
    weak = _daily([100.0] * 10 + [95.0, 0.0])      # today's 0.0 must be ignored
    strong = _daily([100.0] * 10 + [105.0, 0.0])
    assert _resolve("dxy", monkeypatch, tmp_path, weak).direction == "long"
    assert _resolve("dxy", monkeypatch, tmp_path, strong).direction == "short"


def test_vix_calm_is_long_and_spike_is_short(monkeypatch, tmp_path):
    calm = _daily([20.0] * 10 + [15.0, 99.0])
    spike = _daily([20.0] * 10 + [28.0, 1.0])
    flat = _daily([20.0] * 12)
    assert _resolve("vix", monkeypatch, tmp_path, calm).direction == "long"
    assert _resolve("vix", monkeypatch, tmp_path, spike).direction == "short"
    assert _resolve("vix", monkeypatch, tmp_path, flat).direction is None


def test_vix_bullishness_is_bounded_and_decreasing():
    s = _daily([20.0] * 5 + [10.0, 20.0, 40.0])
    b = ls.to_bullishness("vix", s, window=5).dropna()
    assert ((b > 0) & (b < 100)).all()
    assert np.all(np.diff(b.to_numpy()[-3:]) < 0)


# --- freshness ----------------------------------------------------------------


def test_stale_data_gives_no_direction(monkeypatch, tmp_path):
    old = _daily([90.0] * 3, end="2026-10-20")
    r = _resolve("fng", monkeypatch, tmp_path, old, max_stale_days=5.0)
    assert r.direction is None
    assert r.reason.startswith("stale")
    assert r.as_of == "2026-10-20"


def test_weekend_gap_is_not_stale(monkeypatch, tmp_path):
    # DXY has no weekend rows: Friday's close read on Monday is 3 days old.
    monday = pd.Timestamp("2026-11-09 08:00", tz="UTC").timestamp()
    s = _daily([100.0] * 10 + [95.0], end="2026-11-06")
    monkeypatch.setattr(ls, "_load", _fake_loader(s))
    (tmp_path / "d.json").write_text("{}")
    r = ls.resolve("dxy", cache_path=str(tmp_path / "d.json"), window=5,
                   band=10.0, now=monday)
    assert r.direction == "long" and r.reason == "ok"


def test_old_cache_is_refetched(monkeypatch, tmp_path):
    cache = tmp_path / "fng.json"
    cache.write_text("{}")
    os.utime(cache, (NOW - 13 * 3600, NOW - 13 * 3600))
    calls = []
    monkeypatch.setattr(ls, "_load", _fake_loader(_daily([80, 80, 80]), calls))
    ls.resolve("fng", cache_path=str(cache), window=5, band=10.0,
               cache_max_age_hours=12.0, now=NOW)
    assert calls == [True]


def test_fresh_cache_is_not_refetched(monkeypatch, tmp_path):
    cache = tmp_path / "fng.json"
    cache.write_text("{}")
    os.utime(cache, (NOW - 3600, NOW - 3600))
    calls = []
    monkeypatch.setattr(ls, "_load", _fake_loader(_daily([80, 80, 80]), calls))
    ls.resolve("fng", cache_path=str(cache), window=5, band=10.0,
               cache_max_age_hours=12.0, now=NOW)
    assert calls == [False]


def test_failed_refetch_falls_back_to_cache(monkeypatch, tmp_path):
    cache = tmp_path / "fng.json"
    cache.write_text("{}")
    os.utime(cache, (NOW - 48 * 3600, NOW - 48 * 3600))

    def _load(source, cache_path, refresh):
        if refresh:
            raise OSError("network down")
        return _daily([80, 80, 80])

    monkeypatch.setattr(ls, "_load", _load)
    r = ls.resolve("fng", cache_path=str(cache), window=5, band=10.0, now=NOW)
    assert r.direction == "long"


def test_failure_without_cache_is_unavailable_not_raised(monkeypatch, tmp_path):
    def _load(source, cache_path, refresh):
        raise OSError("network down")

    monkeypatch.setattr(ls, "_load", _load)
    r = ls.resolve("fng", cache_path=str(tmp_path / "missing.json"), window=5,
                   band=10.0, now=NOW)
    assert r.direction is None
    assert r.reason.startswith("load_failed")


def test_only_today_row_means_no_data(monkeypatch, tmp_path):
    r = _resolve("fng", monkeypatch, tmp_path, _daily([90.0]))
    assert r.direction is None and r.reason == "no_completed_data"


# --- config -------------------------------------------------------------------


def test_each_source_gets_its_own_cache_file(tmp_path):
    base = open("config/config.toml", encoding="utf-8").read()
    for source, expected in ls.DEFAULT_CACHE.items():
        p = tmp_path / f"{source}.toml"
        p.write_text(base + f'\n[sentiment]\nsource = "{source}"\n', encoding="utf-8")
        assert load_config(p).sentiment.cache_path == expected


@pytest.mark.parametrize(
    ("path", "enabled", "source"),
    [
        ("config/config-cent.toml", True, "dxy"),  # mode veto_longs, below
        ("config/config-btc.toml", True, "fng"),
        ("config/config-eurjpy.toml", False, "vix"),
    ],
)
def test_committed_bot_configs_sentiment(path, enabled, source):
    s = load_config(path).sentiment
    assert (s.enabled, s.source) == (enabled, source)


# --- veto_longs: macro headwind (DXY strong AND 10y yield rising) ------------


def _two_loaders(monkeypatch, dxy, tnx):
    def _load(source, cache_path, refresh):
        return {"dxy": dxy, "tnx": tnx}[source]
    monkeypatch.setattr(ls, "_load", _load)


def _headwind(tmp_path, **kw):
    for n in ("d.json", "t.json"):
        (tmp_path / n).write_text("{}")
    return ls.macro_headwind(dxy_cache_path=str(tmp_path / "d.json"),
                             tnx_cache_path=str(tmp_path / "t.json"),
                             window=5, yield_window=5, band=10.0, now=NOW, **kw)


STRONG_DXY = _daily([100.0] * 10 + [105.0, 0.0])
WEAK_DXY = _daily([100.0] * 10 + [95.0, 999.0])
RISING_TNX = _daily([4.0] * 10 + [4.5, 0.0])
FALLING_TNX = _daily([4.0] * 10 + [3.5, 99.0])


@pytest.mark.parametrize(
    ("dxy", "tnx", "veto"),
    [
        (STRONG_DXY, RISING_TNX, True),
        (STRONG_DXY, FALLING_TNX, False),
        (WEAK_DXY, RISING_TNX, False),
        (WEAK_DXY, FALLING_TNX, False),
    ],
)
def test_veto_needs_both_dxy_strong_and_yield_rising(monkeypatch, tmp_path, dxy, tnx, veto):
    _two_loaders(monkeypatch, dxy, tnx)
    v = _headwind(tmp_path)
    assert v.reason == "ok"
    assert v.veto_longs is veto


def test_veto_tnx_failure_means_no_veto(monkeypatch, tmp_path):
    def _load(source, cache_path, refresh):
        if source == "tnx":
            raise OSError("down")
        return STRONG_DXY
    monkeypatch.setattr(ls, "_load", _load)
    v = _headwind(tmp_path)
    assert v.veto_longs is False and v.reason.startswith("tnx load_failed")


def test_veto_stale_tnx_means_no_veto(monkeypatch, tmp_path):
    _two_loaders(monkeypatch, STRONG_DXY, _daily([4.0] * 10 + [4.5], end="2026-10-01"))
    v = _headwind(tmp_path)
    assert v.veto_longs is False and v.reason == "tnx stale"


def test_committed_bot_configs_risk_and_accounts():
    cent = load_config("config/config-cent.toml")
    btc = load_config("config/config-btc.toml")
    assert (cent.strategy.direction, cent.sentiment.mode) == ("long", "veto_longs")
    assert cent.risk.max_loss_pct_per_trade == 10.0 and cent.risk.sizing == "percent"
    assert (btc.risk.sizing, btc.trading.lot) == ("fixed", 0.01)
    assert btc.live.expected_login == 161700182
    assert cent.live.expected_login == 161693049
