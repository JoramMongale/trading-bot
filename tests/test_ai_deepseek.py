"""Tests for src/trading_bot/ai/deepseek.py — DeepSeek client, no network.

The transport seam is ``trading_bot.ai.deepseek._post_json``; tests fake it
with monkeypatch, so nothing here opens a socket. This also pins the request
shape (endpoint, auth header, JSON mode, temperature, model) against the
OpenAI-compatible contract.
"""

import os

import pytest

import trading_bot.ai.deepseek as ds
from trading_bot.ai.base import AIClientUnavailableError
from trading_bot.ai.context import RegimeContext, TradeContext
from trading_bot.ai.schema import AIResponseError
from trading_bot.config import AIConfig


class _FakeCfg:
    ai = AIConfig()


def _trade_ctx():
    return TradeContext(
        symbol="XAUUSD", timeframe="M5", bar_time="2021-02-01 00:30:00",
        last_bars=[], resistance=101.00, support=100.10,
        entry=101.00, sl=100.09, tp=101.91,
        stop_distance=0.91, reward_risk=1.0, change_pct=1.2,
        atr_estimate=0.4, session_hour=0, balance=5000.0, max_loss_pct=1.0,
    )


def _regime_ctx():
    return RegimeContext(
        symbol="XAUUSD", as_of="2021-02-01", days=[], n_days=5,
        up_days_frac=0.8, avg_daily_range_pct=0.5, price_change_pct=2.0,
        recent_avg_r=0.1, recent_trades=20,
    )


def _response(content):
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def test_propose_trade_round_trip(monkeypatch, tmp_path):
    captured = {}

    def fake_post(url, headers, payload, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = payload
        captured["timeout"] = timeout
        return _response(
            '{"ticker": "XAUUSD", "bias": "LONG", "confidence": 80, '
            '"invalidation_level": 100.50, "reasoning": "ok"}'
        )

    monkeypatch.setattr(ds, "_post_json", fake_post)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-123")
    client = ds.DeepSeekClient(_FakeCfg())

    p = client.propose_trade(_trade_ctx())
    assert p.bias == "LONG" and p.confidence == 80 and p.invalidation == 100.5

    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key-123"
    assert captured["payload"]["model"] == "deepseek-chat"
    assert captured["payload"]["temperature"] == 0.2
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert captured["payload"]["messages"][1]["role"] == "user"
    assert "resistance 101.00" in captured["payload"]["messages"][1]["content"].lower()
    assert captured["timeout"] == 30.0


def test_assess_regime_round_trip(monkeypatch):
    def fake_post(url, headers, payload, timeout):
        return _response(
            '{"regime": "RANGING", "bias": "NEUTRAL", "confidence": 60, '
            '"tradeable": true, "notes": "quiet"}'
        )

    monkeypatch.setattr(ds, "_post_json", fake_post)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    r = ds.DeepSeekClient(_FakeCfg()).assess_regime(_regime_ctx())
    assert r.regime == "RANGING" and r.tradeable


def test_missing_key_fails_closed(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    client = ds.DeepSeekClient(_FakeCfg())
    with pytest.raises(AIClientUnavailableError, match="DEEPSEEK_API_KEY"):
        client.propose_trade(_trade_ctx())


def test_http_error_raises_unavailable(monkeypatch):
    def boom(*a, **k):
        raise ds.urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)

    monkeypatch.setattr(ds, "_post_json", boom)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    with pytest.raises(AIClientUnavailableError, match="HTTP 401"):
        ds.DeepSeekClient(_FakeCfg()).propose_trade(_trade_ctx())


def test_urlerror_raises_unavailable(monkeypatch):
    def boom(*a, **k):
        raise ds.urllib.error.URLError("connection refused")

    monkeypatch.setattr(ds, "_post_json", boom)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    with pytest.raises(AIClientUnavailableError, match="unreachable"):
        ds.DeepSeekClient(_FakeCfg()).propose_trade(_trade_ctx())


def test_response_missing_choices_raises_unavailable(monkeypatch):
    monkeypatch.setattr(ds, "_post_json", lambda *a, **k: {"unexpected": True})
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    with pytest.raises(AIClientUnavailableError, match="missing choices"):
        ds.DeepSeekClient(_FakeCfg()).propose_trade(_trade_ctx())


def test_malformed_model_json_raises_response_error(monkeypatch):
    monkeypatch.setattr(ds, "_post_json", lambda *a, **k: _response("not json"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    with pytest.raises(AIResponseError):
        ds.DeepSeekClient(_FakeCfg()).propose_trade(_trade_ctx())
