"""AIClient contract (plan 03-01).

Every AI provider (DeepSeek, the offline mock, a future recorder wrapper)
implements this interface. The deterministic engine and the AI backtester
program against it and never touch a specific provider — the same pattern as
``BrokerClient`` for brokers: one interface, one seam to swap, everything else
testable offline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from trading_bot.ai.context import RegimeContext, TradeContext
from trading_bot.ai.schema import AIProposal, RegimeAssessment


class AIClientError(Exception):
    """Base class for AI provider failures."""


class AIClientUnavailableError(AIClientError):
    """The provider could not be reached, or refused the call (auth/rate/5xx).

    Distinct from a malformed RESPONSE (``AIResponseError``, which is the
    model saying something unparseable): this is the transport failing. Callers
    decide per-call whether a transport failure fails OPEN or CLOSED — the AI
    proposal gate fails CLOSED (skip the trade), the daily regime check does
    not (a filter failing must not stop the day).
    """


class AIClient(ABC):
    """Interface every AI provider implements.

    Implementations MUST be constructible without a network call and MUST NOT
    import provider SDKs at module import time (the repo's stdlib-only,
    Windows-portable ethos; the DeepSeek client uses ``urllib``).
    """

    @abstractmethod
    def propose_trade(self, context: TradeContext) -> AIProposal:
        """Verdict on the deterministic setup described by ``context``.

        Raises AIClientUnavailableError on transport failure and
        AIResponseError on an unparseable model reply.
        """

    @abstractmethod
    def assess_regime(self, context: RegimeContext) -> RegimeAssessment:
        """Daily read of the market regime from ``context``.

        Same error contract as :meth:`propose_trade`.
        """
