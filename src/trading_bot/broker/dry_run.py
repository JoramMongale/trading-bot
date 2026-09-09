"""Safety-critical no-send wrapper (phase success criterion 4).

:class:`DryRunBroker` wraps any :class:`~trading_bot.broker.base.BrokerClient`
and intercepts order placement: instead of reaching the inner broker, an entry
request becomes an ``order_plan`` structured decision line (SAFE-02) and
a ``placed=False``/``ticket=0`` result. Nothing inside
:meth:`DryRunBroker.place_market_buy` references the inner broker, so a dry-run
run can never touch a real account by construction — and it never leaves a
phantom pending order behind either.
"""

from __future__ import annotations

import logging

import pandas as pd

from trading_bot.broker.base import (
    AccountInfo,
    BrokerClient,
    OrderRequest,
    OrderResult,
    PendingOrder,
    Position,
    Quote,
    SymbolRisk,
)
from trading_bot.logging_utils import log_decision


class DryRunBroker(BrokerClient):
    """Wraps a broker and guarantees no order reaches it."""

    def __init__(self, inner: BrokerClient, logger: logging.Logger | None = None):
        self._inner = inner
        self._logger = logger

    # Read-only / introspection methods delegate unchanged.
    def connect(self) -> None:
        self._inner.connect()

    def disconnect(self) -> None:
        self._inner.disconnect()

    def reconnect(self) -> None:
        # The dry-run wrapper carries no connection state of its own; delegate
        # so a reconnecting CLI loop behaves identically in dry-run.
        self._inner.reconnect()

    def fetch_rates(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        return self._inner.fetch_rates(symbol, timeframe, count)

    def account_info(self) -> AccountInfo:
        return self._inner.account_info()

    def quote(self, symbol: str) -> Quote:
        return self._inner.quote(symbol)

    def symbol_risk(self, symbol: str) -> SymbolRisk:
        return self._inner.symbol_risk(symbol)

    def pending_orders(self, symbol: str, magic: int) -> list[PendingOrder]:
        return self._inner.pending_orders(symbol, magic)

    def positions(self, symbol: str, magic: int) -> list[Position]:
        return self._inner.positions(symbol, magic)

    def place_market_buy(self, request: OrderRequest) -> OrderResult:
        """NEVER sends. Logs the would-be order and returns a no-op result.

        Deliberately contains zero references to ``self._inner`` — structurally
        impossible for a dry-run call to leak a real order, and the inner
        broker's state (pending orders, positions) is never touched.
        """
        logger = self._logger or logging.getLogger("dry_run")
        log_decision(logger, "order_plan", **request.to_log_fields(), mode="dry-run")
        return OrderResult(
            ticket=0, placed=False, retcode=0, comment="dry-run: no order sent"
        )

    def place_market_sell(self, request: OrderRequest) -> OrderResult:
        """NEVER sends (sell mirror of :meth:`place_market_buy`).

        Structurally identical no-send: logs the would-be short as an
        ``order_plan`` decision (SAFE-02, carrying ``side=short`` via
        ``to_log_fields``) and returns a no-op result. Zero references to
        ``self._inner`` — a dry-run short can never leak a real sell.
        """
        logger = self._logger or logging.getLogger("dry_run")
        log_decision(logger, "order_plan", **request.to_log_fields(), mode="dry-run")
        return OrderResult(
            ticket=0, placed=False, retcode=0, comment="dry-run: no order sent"
        )
