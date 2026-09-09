"""Deterministic gate over AI proposals (plan 03-01).

The AI PROPOSES; this gate DISPOSES. A pure function with no I/O, no provider,
no logging — the same design as ``live/safety.py``: the decision is separable,
testable on any platform, and the ENGINE decides what to do with the verdict.
This gate is the only thing standing between a model's idea and an order, so it
fails CLOSED: anything it cannot evaluate with certainty blocks the trade.

An invalidation level, when the model supplies one, must satisfy two sanity
conditions or the proposal is BLOCKED:

- it must not WIDEN the deterministic stop (a LONG must not be invalidated
  below its stop — the deterministic stop already caps the loss, and a level
  past it would silently widen the risk if a future version ever wired the
  invalidation into the exit); and
- it must sit on the RISK side of the trade (a LONG cannot be "invalidated" at
  a price above its entry — the trade is working there).

For a LONG that means ``sl <= invalidation <= entry``; for a SHORT
``entry <= invalidation <= sl``. ``None`` always passes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from trading_bot.ai.schema import AIProposal

APPROVED = "APPROVED"
BLOCKED = "BLOCKED"
REJECTED = "REJECTED"


@dataclass(frozen=True)
class GateVerdict:
    verdict: str  # APPROVED | BLOCKED | REJECTED
    reason: str   # machine-readable reason for the decision log


def evaluate_proposal(
    proposal: AIProposal,
    *,
    entry: float,
    sl: float,
    tp: float,
    direction: str = "long",
    min_confidence: int = 70,
    require_agreement: bool = True,
) -> GateVerdict:
    """Gate one proposal against the deterministic setup it is judging.

    Args:
        proposal:          parsed model output (already schema-validated).
        entry/sl/tp:       the DETERMINISTIC levels (the gate never trusts the
                           model to price anything — it only judges).
        direction:         "long" or "short" — the setup's direction.
        min_confidence:    confidence floor from ``[ai] min_confidence``.
        require_agreement: ``[ai] require_agreement`` — bias must match the
                           setup direction.

    Returns an APPROVED/BLOCKED/REJECTED :class:`GateVerdict`.
    """
    if proposal.is_none:
        return GateVerdict(REJECTED, "no_idea")

    if proposal.confidence < min_confidence:
        return GateVerdict(BLOCKED, "low_confidence")

    if require_agreement:
        if direction == "long" and not proposal.is_long:
            return GateVerdict(BLOCKED, "bias_mismatch")
        if direction == "short" and not proposal.is_short:
            return GateVerdict(BLOCKED, "bias_mismatch")

    if proposal.invalidation is not None:
        # Fail CLOSED on a level we cannot judge: an unknown or degenerate
        # stop geometry means the integrity check is meaningless.
        if not (math.isfinite(entry) and math.isfinite(sl)):
            return GateVerdict(BLOCKED, "invalid_invalidation")
        if direction == "long" and not (sl <= proposal.invalidation <= entry):
            return GateVerdict(BLOCKED, "invalid_invalidation")
        if direction == "short" and not (entry <= proposal.invalidation <= sl):
            return GateVerdict(BLOCKED, "invalid_invalidation")

    return GateVerdict(APPROVED, "ok")
