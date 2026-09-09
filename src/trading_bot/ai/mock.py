"""Offline providers: a deterministic mock and an audit-recording wrapper.

``MockAIClient`` is the offline-first default (``[ai] provider = "mock"``): no
API key, no network, deterministic output. It is what makes every AI feature —
gating, AI backtest, live dry-run — runnable and testable before a single paid
call, mirroring the reference repo's "offline is the default" rule.

``RecordingAIClient`` wraps any client and writes every prompt+response to a
JSONL audit file (SAFE-02 for the AI half), so model output quality can be
reviewed offline regardless of provider.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from trading_bot.ai.base import AIClient
from trading_bot.ai.context import RegimeContext, TradeContext
from trading_bot.ai.schema import AIProposal, RegimeAssessment


class MockAIClient(AIClient):
    """Deterministic offline provider.

    Behavior is chosen by which constructor argument is given (first match wins):

    - ``proposal_fn`` / ``regime_fn``: callables (context) -> result. The
      scripted hooks tests use to simulate the model passing/rejecting at
      specific bars.
    - ``proposal`` / ``regime``: a fixed result returned for every call.
    - otherwise: the heuristic below, which derives a plausible verdict from
      the context itself.
    """

    def __init__(
        self,
        *,
        proposal: AIProposal | None = None,
        regime: RegimeAssessment | None = None,
        proposal_fn: Callable[[TradeContext], AIProposal] | None = None,
        regime_fn: Callable[[RegimeContext], RegimeAssessment] | None = None,
    ):
        self._proposal = proposal
        self._regime = regime
        self._proposal_fn = proposal_fn
        self._regime_fn = regime_fn

    def propose_trade(self, context: TradeContext) -> AIProposal:
        if self._proposal_fn is not None:
            return self._proposal_fn(context)
        if self._proposal is not None:
            return self._proposal
        return self._heuristic_proposal(context)

    def assess_regime(self, context: RegimeContext) -> RegimeAssessment:
        if self._regime_fn is not None:
            return self._regime_fn(context)
        if self._regime is not None:
            return self._regime
        return self._heuristic_regime(context)

    @staticmethod
    def _heuristic_proposal(context: TradeContext) -> AIProposal:
        """A sane LONG with high conviction when the setup is valid, else NONE.

        The point is not that this predicts anything — it is a plumbing test.
        It exercises the same schema the real model uses so the whole gate and
        execution path runs offline.
        """
        if context.entry > context.sl and context.reward_risk >= 0.5:
            return AIProposal(
                bias="LONG",
                confidence=90,
                reasoning="mock heuristic: valid setup, agree with breakout",
                invalidation=context.sl,
            )
        return AIProposal(
            bias="NONE",
            confidence=50,
            reasoning="mock heuristic: no clearly tradeable setup",
        )

    @staticmethod
    def _heuristic_regime(context: RegimeContext) -> RegimeAssessment:
        if context.up_days_frac is not None and context.up_days_frac >= 0.5:
            return RegimeAssessment(
                regime="TRENDING",
                bias="BULLISH",
                confidence=70,
                tradeable=True,
                notes="mock heuristic: up days dominate",
            )
        return RegimeAssessment(
            regime="RANGING",
            bias="NEUTRAL",
            confidence=60,
            tradeable=True,
            notes="mock heuristic: no clear daily direction",
        )


class RecordingAIClient(AIClient):
    """Wrap any client and audit every call to a JSONL file + in-memory list.

    Each recorded line: ``{"kind", "as_of", "context", "result"}`` where
    ``context``/``result`` are the dataclass ``asdict`` dumps. The in-memory
    ``calls`` list is what tests assert on; the file is the durable audit trail
    operators review offline (SAFE-02 for the AI half).
    """

    def __init__(self, inner: AIClient, record_path: str | Path | None = None):
        self._inner = inner
        self._record_path = Path(record_path) if record_path else None
        self.calls: list[dict] = []

    def propose_trade(self, context: TradeContext) -> AIProposal:
        result = self._inner.propose_trade(context)
        self._record("propose_trade", context, result)
        return result

    def assess_regime(self, context: RegimeContext) -> RegimeAssessment:
        result = self._inner.assess_regime(context)
        self._record("assess_regime", context, result)
        return result

    def _record(self, kind: str, context, result) -> None:
        entry = {
            "kind": kind,
            "as_of": str(getattr(context, "as_of", getattr(context, "bar_time", ""))),
            "context": asdict(context),
            "result": asdict(result),
        }
        self.calls.append(entry)
        if self._record_path is not None:
            self._record_path.parent.mkdir(parents=True, exist_ok=True)
            with self._record_path.open("a", encoding="utf-8") as fh:
                fh.write(
                    json.dumps(
                        {"ts": datetime.now(timezone.utc).isoformat(), **entry},
                        default=str,
                    )
                    + "\n"
                )
