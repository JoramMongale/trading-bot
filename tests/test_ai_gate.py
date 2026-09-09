"""Tests for src/trading_bot/ai/gate.py — the pure deterministic proposal gate.

The gate is the only thing standing between a model's idea and an order, so it
fails CLOSED: anything it cannot evaluate with certainty blocks the trade.
Golden setup for reference: entry=101.00, sl=100.09, tp=101.91 (exact 1:1).
"""

import pytest

from trading_bot.ai.gate import APPROVED, BLOCKED, REJECTED, evaluate_proposal
from trading_bot.ai.schema import AIProposal

ENTRY, SL, TP = 101.00, 100.09, 101.91


def _proposal(bias="LONG", confidence=80, invalidation=None):
    return AIProposal(bias=bias, confidence=confidence,
                      reasoning="t", invalidation=invalidation)


def test_approves_agreeing_high_confidence_long():
    v = evaluate_proposal(_proposal(invalidation=SL), entry=ENTRY, sl=SL, tp=TP)
    assert v.verdict == APPROVED and v.reason == "ok"


def test_invalidation_none_passes():
    assert evaluate_proposal(_proposal(), entry=ENTRY, sl=SL, tp=TP).verdict == APPROVED


def test_rejects_no_idea():
    v = evaluate_proposal(_proposal(bias="NONE"), entry=ENTRY, sl=SL, tp=TP)
    assert v.verdict == REJECTED and v.reason == "no_idea"


def test_blocks_low_confidence():
    v = evaluate_proposal(_proposal(confidence=60), entry=ENTRY, sl=SL, tp=TP,
                          min_confidence=70)
    assert v.verdict == BLOCKED and v.reason == "low_confidence"


def test_confidence_exactly_at_threshold_passes():
    v = evaluate_proposal(_proposal(confidence=70), entry=ENTRY, sl=SL, tp=TP,
                          min_confidence=70)
    assert v.verdict == APPROVED


def test_blocks_bias_mismatch_on_long_setup():
    v = evaluate_proposal(_proposal(bias="SHORT"), entry=ENTRY, sl=SL, tp=TP)
    assert v.verdict == BLOCKED and v.reason == "bias_mismatch"


def test_require_agreement_off_allows_any_bias():
    v = evaluate_proposal(_proposal(bias="SHORT"), entry=ENTRY, sl=SL, tp=TP,
                          require_agreement=False)
    assert v.verdict == APPROVED


def test_blocks_invalidation_above_entry_long():
    # A LONG cannot be "invalidated" above its entry — the trade is working there.
    v = evaluate_proposal(_proposal(invalidation=ENTRY + 0.5),
                          entry=ENTRY, sl=SL, tp=TP)
    assert v.verdict == BLOCKED and v.reason == "invalid_invalidation"


def test_blocks_invalidation_below_stop_long():
    # An invalidation below the stop would WIDEN the stop if ever used as an exit.
    v = evaluate_proposal(_proposal(invalidation=SL - 0.5), entry=ENTRY, sl=SL, tp=TP)
    assert v.verdict == BLOCKED and v.reason == "invalid_invalidation"


def test_invalidation_between_stop_and_entry_passes_long():
    v = evaluate_proposal(_proposal(invalidation=(SL + ENTRY) / 2),
                          entry=ENTRY, sl=SL, tp=TP)
    assert v.verdict == APPROVED


def test_short_direction_mirror():
    # Short mirror of the golden long: entry below, stop above.
    s_entry, s_sl = 100.00, 100.91
    assert evaluate_proposal(_proposal(bias="SHORT", invalidation=s_sl),
                             entry=s_entry, sl=s_sl, tp=99.09,
                             direction="short").verdict == APPROVED
    # SHORT bias on a SHORT setup with a wrong-side invalidation (below entry).
    v = evaluate_proposal(_proposal(bias="SHORT", invalidation=s_entry - 0.5),
                          entry=s_entry, sl=s_sl, tp=99.09, direction="short")
    assert v.verdict == BLOCKED and v.reason == "invalid_invalidation"
    # LONG bias on a SHORT setup is a mismatch.
    v = evaluate_proposal(_proposal(bias="LONG"), entry=s_entry, sl=s_sl, tp=99.09,
                          direction="short")
    assert v.verdict == BLOCKED and v.reason == "bias_mismatch"


def test_blocks_on_unknown_stop_geometry():
    v = evaluate_proposal(_proposal(invalidation=100.5), entry=float("nan"),
                          sl=float("nan"), tp=float("nan"))
    assert v.verdict == BLOCKED and v.reason == "invalid_invalidation"
