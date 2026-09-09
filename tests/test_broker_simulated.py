"""Tests for src/trading_bot/broker/ — BrokerClient contract + SimulatedBroker.

Covers:
  - fetch_rates closed-bar shape (OHLC columns, index named "time") and
    cursor-relative windowing that shifts on advance()
  - BrokerUnavailableError when the broker has no rates loaded
  - place_market_buy ledger behavior (ticket sequence, retcode 10009)
  - pending_orders symbol+magic filtering and simulate_fill expiry
  - PendingOrder.equivalent_to re-trigger dedup semantics (0.01 tolerance)
  - OrderRequest.to_log_fields SAFE-02 logging keys
  - BrokerClient stays abstract while SimulatedBroker is concrete
"""

import inspect

import pandas as pd
import pytest

from trading_bot.broker.base import BrokerClient, BrokerUnavailableError, OrderRequest, PendingOrder
from trading_bot.broker.simulated import SimulatedBroker


def _rates(n=10):
    idx = pd.date_range("2025-01-01 00:00", periods=n, freq="5min", name="time")
    return pd.DataFrame(
        {
            "open": [100.0] * n,
            "high": [101.0] * n,
            "low": [99.0] * n,
            "close": [100.5] * n,
        },
        index=idx,
    )


def _request(**overrides):
    base = dict(
        symbol="XAUUSD",
        volume=0.01,
        entry=101.0,
        sl=100.0,
        tp=102.0,
        magic=77001,
        deviation=20,
        comment="gold-breakout-bot",
    )
    base.update(overrides)
    return OrderRequest(**base)


def test_fetch_rates_returns_closed_bars_ending_at_cursor():
    rates = _rates(10)
    broker = SimulatedBroker(rates=rates)

    df = broker.fetch_rates("XAUUSD", "M5", 3)

    assert list(df.columns) == ["open", "high", "low", "close"]
    assert df.index.name == "time"
    assert df.index.tolist() == rates.index[7:].tolist()


def test_fetch_rates_window_shifts_with_advance():
    rates = _rates(10)
    broker = SimulatedBroker(rates=rates)

    assert broker.fetch_rates("XAUUSD", "M5", 3).index.tolist() == rates.index[7:].tolist()

    broker.advance()

    assert broker.fetch_rates("XAUUSD", "M5", 3).index.tolist() == rates.index[8:].tolist()


def test_fetch_rates_on_no_rates_raises_broker_unavailable():
    broker = SimulatedBroker(rates=None)

    with pytest.raises(BrokerUnavailableError):
        broker.fetch_rates("XAUUSD", "M5", 5)


def test_place_market_buy_appends_ledger_and_returns_ticket():
    broker = SimulatedBroker(rates=_rates())

    res = broker.place_market_buy(_request())

    assert res.placed is True
    assert res.retcode == 10009
    assert res.ticket == 1000
    assert broker.place_market_buy(_request()).ticket == 1001


def test_place_market_buy_opens_a_position_and_leaves_nothing_pending():
    """A market order fills on the spot. If the fake left the entry pending
    instead, the engine's one-trade-at-a-time guard would find an empty
    position list and happily arm a second entry on the next setup."""
    broker = SimulatedBroker(rates=_rates())

    res = broker.place_market_buy(_request(entry=101.0))

    assert broker.pending_orders("XAUUSD", 77001) == []
    assert [p.ticket for p in broker.positions("XAUUSD", 77001)] == [res.ticket]
    # Fills at the ask, not the reference entry — that gap is the slippage.
    assert res.fill_price == pytest.approx(broker.quote("XAUUSD").ask)


def test_pending_orders_filters_by_symbol_and_magic():
    broker = SimulatedBroker(rates=_rates())
    broker.simulate_pending(101.0)
    broker.simulate_pending(102.0, magic=999)
    broker.simulate_pending(103.0, symbol="XAGUSD")

    pending = broker.pending_orders("XAUUSD", 77001)

    assert [p.entry for p in pending] == [101.0]


def test_positions_filter_by_symbol_and_magic():
    broker = SimulatedBroker(rates=_rates())
    broker.place_market_buy(_request(entry=101.0))
    broker.place_market_buy(_request(entry=102.0, magic=999))
    broker.place_market_buy(_request(entry=103.0, symbol="XAGUSD"))

    assert [p.ticket for p in broker.positions("XAUUSD", 77001)] == [1000]


def test_simulate_fill_expires_pending_order():
    broker = SimulatedBroker(rates=_rates())
    broker.simulate_pending(101.0)
    broker.simulate_pending(102.0)
    assert len(broker.pending_orders("XAUUSD", 77001)) == 2

    broker.simulate_fill(1000)

    pending = broker.pending_orders("XAUUSD", 77001)
    assert [p.ticket for p in pending] == [1001]


def test_equivalent_to_matches_on_symbol_magic_entry_tolerance():
    order = PendingOrder(ticket=1, symbol="XAUUSD", entry=101.00, sl=100.0, tp=102.0, magic=77001)

    assert order.equivalent_to(_request(entry=101.005))  # within 0.01
    assert not order.equivalent_to(_request(entry=101.02))  # outside 0.01
    assert not order.equivalent_to(_request(entry=101.00, magic=999))
    assert not order.equivalent_to(_request(entry=101.00, symbol="XAGUSD"))


def test_to_log_fields_contains_safe02_keys():
    assert set(_request().to_log_fields()) == {"symbol", "volume", "entry", "sl", "tp", "magic", "side"}


def test_broker_client_abstract_simulated_concrete():
    assert inspect.isabstract(BrokerClient)
    assert not inspect.isabstract(SimulatedBroker)
