"""Tests for src/trading_bot/ai/schema.py — strict JSON parsing of model output."""

import pytest

from trading_bot.ai.schema import (
    AIProposal,
    AIResponseError,
    RegimeAssessment,
    parse_proposal,
    parse_regime,
)

VALID_PROPOSAL = (
    '{"ticker": "XAUUSD", "bias": "LONG", "confidence": 84, '
    '"invalidation_level": 101.0, "reasoning": "breakout holds above support"}'
)


def test_parse_proposal_happy_path():
    p = parse_proposal(VALID_PROPOSAL)
    assert isinstance(p, AIProposal)
    assert p.bias == "LONG"
    assert p.confidence == 84
    assert p.invalidation == 101.0
    assert p.is_long and not p.is_short and not p.is_none


def test_parse_proposal_accepts_markdown_fence():
    p = parse_proposal(f"```json\n{VALID_PROPOSAL}\n```")
    assert p.bias == "LONG"


def test_parse_proposal_invalidation_null_and_omitted():
    assert parse_proposal(
        '{"bias": "NONE", "confidence": 50, "invalidation_level": null, '
        '"reasoning": "pass"}'
    ).invalidation is None
    assert parse_proposal(
        '{"bias": "NONE", "confidence": 50, "reasoning": "pass"}'
    ).invalidation is None


@pytest.mark.parametrize(
    "raw",
    [
        "not json at all",
        '{"bias": "LONG"}',  # missing confidence + reasoning
        '{"confidence": 84, "reasoning": "x"}',  # missing bias
        '{"bias": "LONG", "confidence": 84, "reasoning": 3}',  # reasoning not str
        '{"bias": "LONG", "confidence": "84", "reasoning": "x"}',  # conf not int
        '{"bias": "LONG", "confidence": True, "reasoning": "x"}',  # bool not int
        '{"bias": "SIDEWAYS", "confidence": 84, "reasoning": "x"}',  # bad bias
        '{"bias": "LONG", "confidence": 150, "reasoning": "x"}',  # conf out of range
        '{"bias": "LONG", "confidence": -1, "reasoning": "x"}',  # conf out of range
        '{"bias": "LONG", "confidence": 84, "reasoning": "x", '
        '"invalidation_level": "101"}',  # invalidation not a number
        "[1, 2, 3]",  # not an object
        "42",
    ],
)
def test_parse_proposal_rejects_malformed(raw):
    with pytest.raises(AIResponseError):
        parse_proposal(raw)


def test_parse_proposal_rejects_bool_invalidation():
    with pytest.raises(AIResponseError):
        parse_proposal(
            '{"bias": "LONG", "confidence": 84, "reasoning": "x", '
            '"invalidation_level": true}'
        )


def test_parse_regime_happy_path():
    r = parse_regime(
        '{"regime": "TRENDING", "bias": "BULLISH", "confidence": 78, '
        '"tradeable": true, "notes": "clean trend"}'
    )
    assert isinstance(r, RegimeAssessment)
    assert r.regime == "TRENDING"
    assert r.bias == "BULLISH"
    assert r.tradeable is True
    assert not r.is_choppy


@pytest.mark.parametrize(
    "raw",
    [
        '{"regime": "SIDEWAYS", "bias": "BULLISH", "confidence": 78, '
        '"tradeable": true, "notes": "x"}',  # bad regime
        '{"regime": "TRENDING", "bias": "BULL", "confidence": 78, '
        '"tradeable": true, "notes": "x"}',  # bad bias
        '{"regime": "TRENDING", "bias": "BULLISH", "confidence": 78, '
        '"tradeable": "yes", "notes": "x"}',  # tradeable not bool
        '{"regime": "TRENDING", "bias": "BULLISH", "confidence": 78, '
        '"notes": "x"}',  # missing tradeable
        '{"regime": "TRENDING", "bias": "BULLISH", "confidence": "78", '
        '"tradeable": true, "notes": "x"}',  # conf not int
    ],
)
def test_parse_regime_rejects_malformed(raw):
    with pytest.raises(AIResponseError):
        parse_regime(raw)


def test_parse_regime_choppy_flag():
    r = parse_regime(
        '{"regime": "CHOPPY", "bias": "NEUTRAL", "confidence": 60, '
        '"tradeable": false, "notes": "whipsaw"}'
    )
    assert r.is_choppy and not r.tradeable
