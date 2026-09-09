"""Tests for src/trading_bot/ai/mock.py — offline provider + audit wrapper."""

import json

from trading_bot.ai.context import RegimeContext, TradeContext
from trading_bot.ai.mock import MockAIClient, RecordingAIClient
from trading_bot.ai.schema import AIProposal, RegimeAssessment


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


def test_heuristic_proposal_agrees_with_valid_setup():
    p = MockAIClient().propose_trade(_trade_ctx())
    assert p.bias == "LONG" and p.confidence == 90
    assert p.invalidation == 100.09


def test_heuristic_proposal_passes_on_invalid_setup():
    ctx = _trade_ctx()
    bad = TradeContext(**{**ctx.__dict__, "entry": 100.0, "sl": 100.09,
                          "reward_risk": 0.1})
    p = MockAIClient().propose_trade(bad)
    assert p.is_none


def test_fixed_proposal_and_regime():
    fixed_p = AIProposal(bias="SHORT", confidence=55, reasoning="fixed",
                         invalidation=None)
    fixed_r = RegimeAssessment(regime="CHOPPY", bias="NEUTRAL", confidence=50,
                               tradeable=False, notes="fixed")
    client = MockAIClient(proposal=fixed_p, regime=fixed_r)
    assert client.propose_trade(_trade_ctx()) == fixed_p
    assert client.assess_regime(_regime_ctx()) == fixed_r


def test_scripted_functions():
    client = MockAIClient(
        proposal_fn=lambda ctx: AIProposal(bias="LONG", confidence=42,
                                           reasoning="scripted"),
        regime_fn=lambda ctx: RegimeAssessment(
            regime="TRENDING", bias="BULLISH", confidence=80,
            tradeable=True, notes="scripted"),
    )
    assert client.propose_trade(_trade_ctx()).confidence == 42
    assert client.assess_regime(_regime_ctx()).regime == "TRENDING"


def test_heuristic_regime_chooses_trending(tmp_path):
    r = MockAIClient().assess_regime(_regime_ctx())
    assert r.regime == "TRENDING" and r.tradeable


def test_recording_client_audits_in_memory_and_to_file(tmp_path):
    inner = MockAIClient()
    path = tmp_path / "calls.jsonl"
    client = RecordingAIClient(inner, path)
    client.propose_trade(_trade_ctx())
    client.assess_regime(_regime_ctx())

    assert len(client.calls) == 2
    assert client.calls[0]["kind"] == "propose_trade"
    assert client.calls[0]["result"]["bias"] == "LONG"
    assert client.calls[1]["kind"] == "assess_regime"

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["kind"] == "propose_trade"
    assert first["context"]["entry"] == 101.00
