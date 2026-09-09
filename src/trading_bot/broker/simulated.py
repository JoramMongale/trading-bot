"""In-memory broker for tests, dry-run, and the E2E replay (SAFE-03).

Implements the :class:`~trading_bot.broker.base.BrokerClient` contract without
the live MT5 package. ``_cursor`` acts as "now": :meth:`fetch_rates` returns
only CLOSED bars ending at the cursor, and :meth:`advance` simulates a new bar
closing so the E2E replay can feed the engine one closed bar at a time.
"""

from __future__ import annotations

import pandas as pd

from trading_bot.broker.base import (
    AccountInfo,
    BrokerClient,
    BrokerUnavailableError,
    OrderRequest,
    OrderResult,
    PendingOrder,
    Position,
    Quote,
    SymbolRisk,
)


class SimulatedBroker(BrokerClient):
    """Fake broker backed by an in-memory OHLC frame and an order ledger."""

    def __init__(
        self,
        rates: pd.DataFrame | None = None,
        trade_mode: int = 0,
        cursor: int | None = None,
        balance: float = 10000.0,
    ):
        self._rates = rates
        self._trade_mode = trade_mode
        self._balance = balance
        # "Now" = one past the last closed bar; defaults to the end of the data.
        # An explicit ``cursor`` rewinds "now" so a caller can replay forward
        # from an earlier bar (the E2E walk and dry-run replay both do this).
        if cursor is not None:
            self._cursor = cursor
        else:
            self._cursor = len(rates) if rates is not None else 0
        self._orders: list[dict] = []
        self._positions: list[Position] = []
        self._spread = 0.0
        self._quote_offset = 0.0
        self._symbol_risk = SymbolRisk(
            tick_size=0.01, tick_value=1.0,
            volume_min=0.01, volume_step=0.01, volume_max=200.0,
        )

    def connect(self) -> None:
        """Always connected — no-op."""

    def disconnect(self) -> None:
        """No-op."""

    def fetch_rates(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        """Return the last ``count`` CLOSED bars ending at the cursor.

        Raises BrokerUnavailableError when no rates were provided (mirrors a
        terminal with no data).
        """
        if self._rates is None:
            raise BrokerUnavailableError(
                "SimulatedBroker has no rates loaded (terminal with no data)"
            )
        # Clamp the window start at 0: a rewound cursor with fewer than
        # ``count`` closed bars behind it must return the bars that DO exist,
        # never wrap around via negative-index slicing.
        start = max(0, self._cursor - count)
        return self._rates.iloc[start : self._cursor].copy()

    def advance(self) -> None:
        """Move "now" forward by one bar (a new bar closes)."""
        self._cursor += 1

    def account_info(self) -> AccountInfo:
        return AccountInfo(
            login=123456,
            server="Simulated",
            currency="USD",
            balance=self._balance,
            trade_mode=self._trade_mode,
        )

    def quote(self, symbol: str) -> Quote:
        """Last closed bar's close, plus an optional spread.

        ``spread`` and ``quote_offset`` let a test put the market somewhere
        other than the last close — which is the realistic case, since the
        setup fires on a close ABOVE resistance and the market keeps moving
        between the bar closing and the order going out.
        """
        if self._rates is None or self._cursor <= 0:
            raise BrokerUnavailableError("SimulatedBroker has no rates loaded")
        mid = float(self._rates["close"].iloc[self._cursor - 1]) + self._quote_offset
        return Quote(bid=mid - self._spread / 2, ask=mid + self._spread / 2)

    def symbol_risk(self, symbol: str) -> SymbolRisk:
        """Defaults mirror standard-account XAUUSD: 0.01 tick worth 1.00 per lot,
        i.e. 100 units of account currency per 1.00 of price on one lot — the
        same economics the old contract_size=100 encoded. Tests override
        ``_symbol_risk`` to model other instruments (a cent account, forex)."""
        return self._symbol_risk

    def place_market_buy(self, request: OrderRequest) -> OrderResult:
        """Fill instantly at the reference entry and open a position.

        A market order does not sit pending, so the ledger entry is recorded
        with ``pending=False`` and a matching position is opened — otherwise
        the engine's one-trade-at-a-time guard would see nothing holding the
        slot and arm a second entry on the next setup.
        """
        ticket = len(self._orders) + 1000
        self._orders.append(
            {
                **request.to_log_fields(),
                "deviation": request.deviation,
                "comment": request.comment,
                "ticket": ticket,
                "pending": False,
            }
        )
        self._positions.append(
            Position(ticket=ticket, symbol=request.symbol, magic=request.magic)
        )
        return OrderResult(
            ticket=ticket,
            placed=True,
            retcode=10009,
            comment="simulated",
            fill_price=self.quote(request.symbol).ask,
        )

    def place_market_sell(self, request: OrderRequest) -> OrderResult:
        """Fill instantly at the BID and open a position (sell mirror).

        A short crosses the bid, so the fill is quoted off the bid — the
        engine's short risk is measured the same way. Same ledger/position
        behaviour as :meth:`place_market_buy`, and the ledger entry records
        the side via ``to_log_fields`` so the decision trail shows which side
        filled.
        """
        ticket = len(self._orders) + 1000
        self._orders.append(
            {
                **request.to_log_fields(),
                "deviation": request.deviation,
                "comment": request.comment,
                "ticket": ticket,
                "pending": False,
            }
        )
        self._positions.append(
            Position(ticket=ticket, symbol=request.symbol, magic=request.magic)
        )
        return OrderResult(
            ticket=ticket,
            placed=True,
            retcode=10009,
            comment="simulated",
            fill_price=self.quote(request.symbol).bid,
        )

    def pending_orders(self, symbol: str, magic: int) -> list[PendingOrder]:
        return [
            PendingOrder(
                ticket=o["ticket"],
                symbol=o["symbol"],
                entry=o["entry"],
                sl=o["sl"],
                tp=o["tp"],
                magic=o["magic"],
            )
            for o in self._orders
            if o["pending"] and o["symbol"] == symbol and o["magic"] == magic
        ]

    def positions(self, symbol: str, magic: int) -> list[Position]:
        return [p for p in self._positions if p.symbol == symbol and p.magic == magic]

    def simulate_pending(
        self, entry: float, symbol: str = "XAUUSD", magic: int = 77001
    ) -> int:
        """Seed an order sitting armed on the server, and return its ticket.

        Nothing the bot places is pending any more — market entries fill
        immediately — but the engine still guards against a leftover order from
        an earlier build or one placed by hand in the terminal, and that guard
        needs a way to be exercised.
        """
        ticket = len(self._orders) + 1000
        self._orders.append(
            {
                "symbol": symbol,
                "volume": 0.01,
                "entry": entry,
                "sl": entry - 1.0,
                "tp": entry + 1.0,
                "magic": magic,
                "deviation": 20,
                "comment": "seeded",
                "ticket": ticket,
                "pending": True,
            }
        )
        return ticket

    def simulate_fill(self, ticket: int) -> None:
        """Mark a ledger order filled (pending=False) — dedup tests."""
        for order in self._orders:
            if order["ticket"] == ticket:
                order["pending"] = False
                return
        raise KeyError(f"no order with ticket {ticket} in ledger")

    def simulate_position(self, ticket: int, symbol: str, magic: int) -> None:
        """Seed an open position (one-trade-at-a-time tests)."""
        self._positions.append(Position(ticket=ticket, symbol=symbol, magic=magic))


class ReplayBroker(SimulatedBroker):
    """SimulatedBroker that walks history forward one bar per fetch.

    ``SimulatedBroker`` holds "now" still, so a polling caller sees the same
    closed bar forever. ``ReplayBroker`` advances the cursor after each
    :meth:`fetch_rates`, which turns a dry-run poll loop into a replay of
    historical bars — one new closed bar per poll, exactly the shape the live
    engine sees against a real terminal.

    Replay stops at the end of the data: once the cursor passes the last bar
    the frame stops growing and the engine reports ``new_bar=False`` from then
    on (the same "no new closed bar" result a quiet market produces).
    """

    def fetch_rates(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        df = super().fetch_rates(symbol, timeframe, count)
        if self._rates is not None and self._cursor < len(self._rates):
            self.advance()
        return df

    @property
    def exhausted(self) -> bool:
        """True once every bar in the frame has been replayed."""
        return self._rates is None or self._cursor >= len(self._rates)
