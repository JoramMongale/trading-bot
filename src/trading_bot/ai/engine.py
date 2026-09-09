"""AIEngine — the deterministic LiveEngine plus the AI layer (plan 03-01).

The parent owns everything that costs money: detection, dedup, safety, risk and
placement. This subclass adds exactly two model consultations (the cadence the
user chose):

- **Once per UTC day** a regime assessment. If the model says CHOPPY or
  ``tradeable=false`` and ``[ai] block_when_choppy`` is set, that day's setups
  are suppressed.
- **On every setup** that reaches the ``_ai_gate`` hook, a trade proposal that
  must pass the pure gate (``ai/gate.py``) or the setup is skipped.

Failure policy (documented in plan 03-01):
- transport/parse failure on the PROPOSAL gate fails CLOSED — the setup is
  skipped, because the gate cannot judge it;
- a failure on the DAILY REGIME check fails OPEN — the regime is a filter, not
  a safety device, and one model outage must not stop the day.
"""

from __future__ import annotations

import pandas as pd

from trading_bot.ai.base import AIClient, AIClientError
from trading_bot.ai.context import build_regime_context, build_trade_context
from trading_bot.ai.gate import APPROVED, evaluate_proposal
from trading_bot.ai.schema import AIResponseError
from trading_bot.broker.base import BrokerUnavailableError
from trading_bot.live.engine import LiveEngine, _round2
from trading_bot.logging_utils import log_decision


class AIEngine(LiveEngine):
    """LiveEngine + AI regime gate + AI proposal gate.

    Args:
        cfg:       project Config with the ``[ai]`` table set up.
        broker:    any BrokerClient (same contract the parent programs against).
        logger:    logging.Logger (SAFE-02).
        ai_client: any AIClient (DeepSeek, mock, recording wrapper).
    """

    def __init__(self, cfg, broker, logger, ai_client: AIClient):
        super().__init__(cfg, broker, logger)
        self._ai = ai_client
        self._last_bars_frame: pd.DataFrame | None = None
        self._regime = None
        self._regime_day: object | None = None

    # -- parent wiring ------------------------------------------------------

    def poll_once(self) -> dict:
        """Run the parent's poll, then the once-per-day regime check."""
        result = super().poll_once()
        self._maybe_regime_check()
        return result

    def _ai_gate(self, entry: float, sl: float, tp: float, bar_time, side: str = "long") -> dict | None:
        """Consult the model on this setup; gate it; skip or proceed.

        Runs between the parent's dedup/slot guards and its safety gate. Returns
        an ``order_skipped`` event (logged) when the proposal does not clear the
        gate or the model cannot be reached; returns ``None`` to let the parent
        proceed to safety/risk/placement.
        """
        cfg = self._cfg
        frame = self._last_bars_frame
        if frame is None or frame.empty:
            # Cannot build a context -> cannot judge -> fail CLOSED.
            log_decision(
                self._logger, "order_skipped", reason="ai_no_context",
                bar=str(bar_time), detail="no bars available to build context",
            )
            return {"event": "order_skipped", "reason": "ai_no_context"}

        if self._regime_blocked():
            log_decision(
                self._logger, "order_skipped", reason="ai_regime_block",
                bar=str(bar_time), entry=_round2(entry),
                regime=self._regime.regime, tradeable=self._regime.tradeable,
            )
            return {"event": "order_skipped", "reason": "ai_regime_block"}

        ctx = build_trade_context(
            frame, cfg, entry, sl, tp, bar_time, balance=self._account_balance()
        )
        try:
            proposal = self._ai.propose_trade(ctx)
        except (AIClientError, AIResponseError) as exc:
            # Fail CLOSED: the gate cannot judge the trade, so it blocks it.
            log_decision(
                self._logger, "order_skipped", reason="ai_unavailable",
                bar=str(bar_time), detail=f"{type(exc).__name__}: {exc}",
            )
            return {"event": "order_skipped", "reason": "ai_unavailable",
                    "detail": str(exc)}

        verdict = evaluate_proposal(
            proposal,
            entry=entry,
            sl=sl,
            tp=tp,
            direction=side,
            min_confidence=cfg.ai.min_confidence,
            require_agreement=cfg.ai.require_agreement,
        )
        log_decision(
            self._logger, "ai_proposal", bar=str(bar_time),
            bias=proposal.bias, confidence=proposal.confidence,
            invalidation=proposal.invalidation, verdict=verdict.verdict,
            reason=verdict.reason,
        )
        if verdict.verdict != APPROVED:
            log_decision(
                self._logger, "order_skipped", reason="ai_rejected",
                bar=str(bar_time), entry=_round2(entry),
                detail=verdict.reason, bias=proposal.bias,
                confidence=proposal.confidence,
            )
            return {"event": "order_skipped", "reason": "ai_rejected",
                    "detail": verdict.reason}
        return None

    # -- internals ----------------------------------------------------------

    def _account_balance(self) -> float | None:
        """Best-effort account balance for the prompt context (never blocks)."""
        try:
            return self._broker.account_info().balance
        except BrokerUnavailableError:
            return None

    def _maybe_regime_check(self) -> None:
        """Once per UTC day, ask the model about the regime (fail OPEN)."""
        cfg = self._cfg
        if not cfg.ai.regime_check_daily:
            return
        frame = self._last_bars_frame
        if frame is None or frame.empty:
            return
        today = frame.index[-1].date()
        if self._regime_day == today:
            return
        self._regime_day = today

        sentiment = self._load_sentiment_snapshot()
        ctx = build_regime_context(frame, cfg, sentiment=sentiment)
        try:
            self._regime = self._ai.assess_regime(ctx)
        except (AIClientError, AIResponseError) as exc:
            # Fail OPEN: a filter outage must not stop the day.
            self._regime = None
            log_decision(
                self._logger, "ai_regime_failed", day=str(today),
                detail=f"{type(exc).__name__}: {exc}",
            )
            return
        log_decision(
            self._logger, "ai_regime", day=str(today),
            regime=self._regime.regime, bias=self._regime.bias,
            confidence=self._regime.confidence, tradeable=self._regime.tradeable,
            notes=self._regime.notes,
        )

    def _load_sentiment_snapshot(self) -> dict | None:
        """Read the [news] daily sentiment snapshot, fail-open (plan 03-04).

        Returns a coerced primitive dict (or None) so the prompt renders
        cleanly. Any error -> None + a log line, and the regime read proceeds
        exactly as before this plan — no news must never stop the day
        (T-04-04-03).
        """
        news = getattr(self._cfg, "news", None)
        if news is None or not news.enabled or not news.snapshot_file:
            return None
        try:
            import json

            from pathlib import Path

            path = Path(news.snapshot_file)
            if not path.exists():
                return None
            raw = json.loads(path.read_text(encoding="utf-8"))
            return {
                "date": str(raw.get("date", "")),
                "score": float(raw.get("score", 0.0)),
                "articles": int(raw.get("articles", 0)),
                "top_titles": [str(t) for t in (raw.get("top_titles") or [])],
            }
        except (OSError, ValueError, TypeError) as exc:
            log_decision(
                self._logger, "ai_regime_sentiment_unreadable",
                detail="news_sentiment snapshot unreadable, continuing without it",
                error=f"{type(exc).__name__}: {exc}",
            )
            return None

    def _regime_blocked(self) -> bool:
        return (
            self._cfg.ai.block_when_choppy
            and self._regime is not None
            and (self._regime.is_choppy or not self._regime.tradeable)
        )
