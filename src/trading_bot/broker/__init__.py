"""Broker abstraction for live execution (phase 2).

Re-exports the BrokerClient contract, its dataclasses/errors, and the broker
implementations: SimulatedBroker (in-memory), MT5Broker (real adapter), and
DryRunBroker (no-send safety wrapper). MT5Broker never imports the
Windows-only ``MetaTrader5`` package at module level — it loads lazily inside
its methods (broker/mt5.py), so this package imports cleanly on macOS.
"""

from trading_bot.broker.base import (
    AccountInfo,
    BrokerClient,
    BrokerError,
    BrokerRejectedError,
    BrokerUnavailableError,
    OrderRequest,
    OrderResult,
    PendingOrder,
    Position,
    Quote,
    SymbolRisk,
)
from trading_bot.broker.dry_run import DryRunBroker
from trading_bot.broker.mt5 import MT5Broker
from trading_bot.broker.simulated import ReplayBroker, SimulatedBroker

__all__ = [
    "AccountInfo",
    "BrokerClient",
    "BrokerError",
    "BrokerRejectedError",
    "BrokerUnavailableError",
    "OrderRequest",
    "OrderResult",
    "PendingOrder",
    "Position",
    "Quote",
    "SymbolRisk",
    "DryRunBroker",
    "MT5Broker",
    "ReplayBroker",
    "SimulatedBroker",
]
