"""Typed broker contract shared by every live-execution component.

Phase 2 programs against this interface (:class:`BrokerClient`) instead of raw
MT5 calls. The live MT5 pip package is Windows-only (RESEARCH.md) and must
never be imported anywhere in this package — the :class:`SimulatedBroker` in
``simulated.py`` is the test/dry-run implementation, and the MT5 adapter lands
in a later plan.

Dataclasses mirror the MT5 request/order vocabulary so the eventual adapter is
a thin translation layer with no strategy knowledge.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class AccountInfo:
    login: int
    server: str
    currency: str
    balance: float
    trade_mode: int  # 0=demo, 1=contest, 2=real (MT5 ACCOUNT_TRADE_MODE_*)


@dataclass(frozen=True)
class OrderRequest:
    """One entry the strategy wants taken, in strategy vocabulary.

    ``entry`` is the REFERENCE level the strategy signalled on (the broken
    resistance), NOT a price the order is placed at. The setup fires on a close
    ABOVE resistance, so by the time this request exists the market is already
    past ``entry`` — a Buy Stop there sits below market and every broker
    rejects it (retcode 10015). The backtest never actually traded that level
    either: it armed the level and filled at ``max(entry, open)`` on the next
    bar, which is the bar's open in 339 of 340 recorded trades. Live execution
    is therefore a MARKET buy, and ``entry`` survives only so the fill can be
    logged against the level that triggered it.
    """

    symbol: str
    volume: float
    entry: float  # reference level (resistance) — see class docstring
    sl: float
    tp: float
    magic: int
    deviation: int
    comment: str

    @property
    def risk_per_unit(self) -> float:
        """Distance from the reference entry down to the stop, in quote units."""
        return self.entry - self.sl

    def to_log_fields(self) -> dict[str, object]:
        """SAFE-02 structured-log fields for this order request."""
        return {
            "symbol": self.symbol,
            "volume": self.volume,
            "entry": self.entry,
            "sl": self.sl,
            "tp": self.tp,
            "magic": self.magic,
        }


@dataclass(frozen=True)
class OrderResult:
    """Outcome of a placement.

    ``fill_price`` is what the market actually gave us. It is a separate field
    from the request's reference ``entry`` because a market order fills at the
    prevailing ask, and the gap between the two is the live-vs-backtest
    slippage the decision log has to keep visible. ``0.0`` means "no fill price
    available" (dry-run no-send, or a broker that omits it).
    """

    ticket: int
    placed: bool
    retcode: int
    comment: str
    fill_price: float = 0.0


@dataclass(frozen=True)
class Quote:
    """Current two-sided price for a symbol.

    Exists because risk cannot be measured from the strategy's reference entry.
    The setup fires on a close above resistance, so by the time an order is
    built the market is already past that level — sizing and the risk cap read
    off the reference therefore both understate what the trade actually risks,
    and understate it MOST when the stop is tight. A live M1 trade on
    2026-08-20 was sized for $49.10 against a $50.42 budget and actually
    risked $56.97, 13% over its own cap.
    """

    bid: float
    ask: float


@dataclass(frozen=True)
class SymbolRisk:
    """What price movement is worth, in the ACCOUNT's currency.

    This exists so the engine never has to know an instrument's contract size
    or do its own currency conversion — two things it got wrong in different
    directions at once. ``[trading] contract_size`` was 100, correct only for
    standard-account gold; on a cent account the same instrument is 1. And a
    symbol can settle its profit in a currency the account is not denominated
    in (XAUUSDc pays USD into a USC account), so a loss computed in quote
    terms is off by the FX rate.

    ``tick_value`` is the broker's own answer to both: the account-currency
    value of one ``tick_size`` move on one full lot. Risk is then

        (stop_distance / tick_size) * tick_value * lots

    with no contract size and no conversion anywhere in it.
    """

    tick_size: float
    tick_value: float
    volume_min: float
    volume_step: float
    volume_max: float

    def money_risk(self, stop_distance: float, lots: float) -> float:
        """Account-currency loss if a position of ``lots`` moves ``stop_distance``."""
        if self.tick_size <= 0:
            return float("nan")
        return (stop_distance / self.tick_size) * self.tick_value * lots

    def notional(self, price: float, lots: float) -> float:
        """Position value in the ACCOUNT's currency — for exposure, not risk.

        Note there is no contract size here, and that is the point. The obvious
        implementation, ``price * contract_size * lots``, yields the symbol's
        QUOTE currency: $4,600 of gold. Comparing that against a balance held in
        USC is wrong by the FX factor — 100x on a cent account — which is
        precisely the class of bug this whole class exists to prevent.

        ``tick_value / tick_size`` is already the account-currency value of a
        one-unit price move on one lot, so multiplying by price gives notional
        directly in account currency with no contract size and no conversion:

            460,000 USC per lot of XAUUSDc at 4600  (= $4,600, correct)
             77,658 USC per lot of BTCUSDc at 77658 (=   $776.58, correct)

        Returns NaN when tick economics are missing, so callers must handle the
        unknown explicitly rather than read it as zero exposure.
        """
        if self.tick_size <= 0 or self.tick_value <= 0:
            return float("nan")
        return price * (self.tick_value / self.tick_size) * lots


@dataclass(frozen=True)
class PendingOrder:
    ticket: int
    symbol: str
    entry: float
    sl: float
    tp: float
    magic: int

    def equivalent_to(self, other: OrderRequest) -> bool:
        """True when ``other`` duplicates this pending order (re-trigger dedup).

        Matches on symbol + magic and on entry within XAUUSD's 2-dp quoting
        tolerance (0.01).
        """
        return (
            self.symbol == other.symbol
            and self.magic == other.magic
            and abs(self.entry - other.entry) <= 0.01
        )


@dataclass(frozen=True)
class Position:
    ticket: int
    symbol: str
    magic: int


class BrokerError(Exception):
    """Base class for broker failures."""


class BrokerUnavailableError(BrokerError):
    """MT5 package/terminal not available, or no data to serve."""


class BrokerRejectedError(BrokerError):
    """order_send returned a failure retcode."""


class BrokerClient(ABC):
    """Interface every broker adapter implements (live MT5, simulated, ...)."""

    @abstractmethod
    def connect(self) -> None:
        """Establish the connection; raise BrokerUnavailableError if unusable."""

    @abstractmethod
    def disconnect(self) -> None:
        """Tear down the connection."""

    def reconnect(self) -> None:
        """Re-establish the connection after a failure (04-01).

        Default: a clean disconnect + connect. A wrapped broker (dry-run)
        delegates; MT5Broker overrides to also drop its cached transport so a
        dead socket is rebuilt rather than re-initialised in place.
        """
        self.disconnect()
        self.connect()

    @abstractmethod
    def fetch_rates(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        """Return ``count`` CLOSED bars: OHLC columns, datetime index named
        ``"time"`` (the exact shape strategy.swings/levels/signals expect)."""

    @abstractmethod
    def account_info(self) -> AccountInfo:
        """Current account snapshot."""

    @abstractmethod
    def quote(self, symbol: str) -> Quote:
        """Current bid/ask. A BUY crosses the ASK, so that is the price risk
        must be measured against — never the strategy's reference level."""

    @abstractmethod
    def symbol_risk(self, symbol: str) -> SymbolRisk:
        """Tick economics and the lot grid, for sizing in account currency."""

    @abstractmethod
    def place_market_buy(self, request: OrderRequest) -> OrderResult:
        """Buy at market with SL/TP attached; raise BrokerRejectedError on a
        failure retcode."""

    @abstractmethod
    def pending_orders(self, symbol: str, magic: int) -> list[PendingOrder]:
        """Live pending orders for symbol+magic (re-trigger dedup).

        Market entries leave nothing pending, so against a real terminal this
        is normally empty and :meth:`positions` is what actually enforces
        one-trade-at-a-time. It stays in the contract because the guard must
        still catch anything left armed by an earlier build or placed by hand.
        """

    @abstractmethod
    def positions(self, symbol: str, magic: int) -> list[Position]:
        """Open positions for symbol+magic (one-trade-at-a-time guard)."""
