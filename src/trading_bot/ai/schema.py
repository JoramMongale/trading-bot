"""Typed model output + strict JSON parsing (plan 03-01).

The model REASONS; deterministic code DISPOSES. Everything the model can say
about the market is shaped by the two dataclasses in this module and validated
at the parse boundary, so a malformed or hallucinated response fails loudly and
deterministically here — never reaching the gate with wrong-shaped fields.

Nothing in this module touches the network. It is pure stdlib, so the schema
and its parsing are testable on any platform without a key, exactly like the
rest of the deterministic core.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

BIASES = ("LONG", "SHORT", "NONE")
REGIMES = ("TRENDING", "RANGING", "CHOPPY")
REGIME_BIASES = ("BULLISH", "BEARISH", "NEUTRAL")


class AIResponseError(ValueError):
    """The model returned text that is not a valid, parseable response."""


def _strip_fences(raw: str) -> str:
    """Remove a ```json ... ``` wrapper some models add around the payload."""
    text = raw.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    return m.group(1) if m else text


def _require(payload: dict[str, Any], key: str, hint: str) -> Any:
    if key not in payload:
        raise AIResponseError(
            f"model response is missing required field {key!r} ({hint})"
        )
    return payload[key]


@dataclass(frozen=True)
class AIProposal:
    """The model's verdict on one deterministic setup.

    Fields:
        bias:             LONG / SHORT / NONE — the directional read on the
                          setup. NONE means "no trade idea".
        confidence:       0..100.
        reasoning:        Free text the operator can read in the decision log.
        invalidation:     A price at/below which the idea is dead for a LONG,
                          at/above which it is dead for a SHORT. Optional; when
                          present the gate requires it NOT to widen the
                          deterministic stop (see ``ai/gate.py``).

    The deterministic system owns entry/sl/tp. The model never supplies order
    prices — it supplies a directional verdict, a conviction, and an invalidation
    the gate checks for stop-integrity. That keeps the measured strategy
    arithmetic (SAFE-01) as the only source of order geometry.
    """

    bias: str
    confidence: int
    reasoning: str
    invalidation: float | None = None

    @property
    def is_long(self) -> bool:
        return self.bias == "LONG"

    @property
    def is_short(self) -> bool:
        return self.bias == "SHORT"

    @property
    def is_none(self) -> bool:
        return self.bias == "NONE"


def parse_proposal(raw: str) -> AIProposal:
    """Parse strict model JSON into an :class:`AIProposal`.

    Raises:
        AIResponseError: the payload is not valid JSON, or a field is missing
            or has the wrong type/range. The deterministic caller treats this
            as a fail-CLOSED skip of the setup, never as a pass.
    """
    try:
        payload = json.loads(_strip_fences(raw))
    except json.JSONDecodeError as exc:
        raise AIResponseError(f"model response is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise AIResponseError(
            f"model response must be a JSON object, got {type(payload).__name__}"
        )

    bias = _require(payload, "bias", "one of LONG/SHORT/NONE")
    if bias not in BIASES:
        raise AIResponseError(f"bias={bias!r} is invalid: must be one of {BIASES}")
    confidence = _require(payload, "confidence", "integer 0..100")
    if not isinstance(confidence, int) or isinstance(confidence, bool):
        raise AIResponseError(
            f"confidence={confidence!r} is invalid: must be an integer 0..100"
        )
    if not 0 <= confidence <= 100:
        raise AIResponseError(f"confidence={confidence} is out of range 0..100")
    reasoning = _require(payload, "reasoning", "short text explaining the call")
    if not isinstance(reasoning, str):
        raise AIResponseError(f"reasoning={reasoning!r} is invalid: must be a string")

    invalidation = payload.get("invalidation_level", None)
    if invalidation is not None:
        if isinstance(invalidation, bool) or not isinstance(invalidation, (int, float)):
            raise AIResponseError(
                f"invalidation_level={invalidation!r} is invalid: must be a number or null"
            )
        invalidation = float(invalidation)

    return AIProposal(
        bias=bias,
        confidence=confidence,
        reasoning=reasoning,
        invalidation=invalidation,
    )


@dataclass(frozen=True)
class RegimeAssessment:
    """The model's daily read of the market regime.

    Fields:
        regime:     TRENDING / RANGING / CHOPPY.
        bias:       BULLISH / BEARISH / NEUTRAL.
        confidence: 0..100.
        tradeable:  Whether the model thinks today is a day to trade at all.
        notes:      Free text for the operator.
    """

    regime: str
    bias: str
    confidence: int
    tradeable: bool
    notes: str

    @property
    def is_choppy(self) -> bool:
        return self.regime == "CHOPPY"


def parse_regime(raw: str) -> RegimeAssessment:
    """Parse strict model JSON into a :class:`RegimeAssessment`.

    Raises:
        AIResponseError: the payload is not valid JSON, or a field is missing
            or has the wrong type/range.
    """
    try:
        payload = json.loads(_strip_fences(raw))
    except json.JSONDecodeError as exc:
        raise AIResponseError(f"model response is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise AIResponseError(
            f"model response must be a JSON object, got {type(payload).__name__}"
        )

    regime = _require(payload, "regime", "one of TRENDING/RANGING/CHOPPY")
    if regime not in REGIMES:
        raise AIResponseError(f"regime={regime!r} is invalid: must be one of {REGIMES}")
    bias = _require(payload, "bias", "one of BULLISH/BEARISH/NEUTRAL")
    if bias not in REGIME_BIASES:
        raise AIResponseError(
            f"bias={bias!r} is invalid: must be one of {REGIME_BIASES}"
        )
    confidence = _require(payload, "confidence", "integer 0..100")
    if not isinstance(confidence, int) or isinstance(confidence, bool):
        raise AIResponseError(
            f"confidence={confidence!r} is invalid: must be an integer 0..100"
        )
    if not 0 <= confidence <= 100:
        raise AIResponseError(f"confidence={confidence} is out of range 0..100")
    tradeable = _require(payload, "tradeable", "true or false")
    if not isinstance(tradeable, bool):
        raise AIResponseError(
            f"tradeable={tradeable!r} is invalid: must be true or false"
        )
    notes = _require(payload, "notes", "short text")
    if not isinstance(notes, str):
        raise AIResponseError(f"notes={notes!r} is invalid: must be a string")

    return RegimeAssessment(
        regime=regime,
        bias=bias,
        confidence=confidence,
        tradeable=tradeable,
        notes=notes,
    )
