"""Tests for the broker SELL path — place_market_sell on every adapter.

Mirrors tests/test_mt5_broker.py conventions (copied locally — the tests dir
is not a package): a minimal FakeMT5 module is injected into sys.modules and
the real adapter's lazy ``_load_mt5`` import picks it up.

The sell path is the strict mirror of the buy path (Task 1 of the live
both-direction build): ORDER_TYPE_SELL at the BID (a sell crosses the bid, so
that is the price the SL/TP distance checks and the fill must reference), with
``_check_stop_distance(..., sell=True)`` refusing stops that sit inside the
broker's minimum distance ABOVE (sl) / BELOW (tp) the bid.

Covers the six behaviours:
  1. sell translation: the exact order_send request dict (type SELL at the bid)
  2. bid not ask: fills at the bid and reports the bid as fill_price
  3. mirrored stop-distance guard on both sl (above) and tp (below)
  4. DryRunBroker.place_market_sell never sends and logs side=short
  5. SimulatedBroker.place_market_sell fills at the bid and opens a position
  6. OrderRequest.risk_per_unit is side-agnostic (abs stop distance)
"""

import sys
from collections import namedtuple

import pandas as pd
import pytest

import trading_bot.broker.mt5 as mt5_mod
from trading_bot.broker.base import BrokerRejectedError, OrderRequest
from trading_bot.broker.dry_run import DryRunBroker
from trading_bot.broker.mt5 import MT5Broker
from trading_bot.broker.simulated import SimulatedBroker

# --- MT5 result/order objects (namedtuple stand-ins for the real API) ------
# Minimal local copy of the test_mt5_broker.py block — only what the sell
# path touches.

_SymbolInfo = namedtuple(
    "_SymbolInfo",
    "filling_mode digits point trade_stops_level volume_min volume_max volume_step",
)
_Tick = namedtuple("_Tick", "bid ask")
_OrderSendResult = namedtuple("_OrderSendResult", "retcode order comment price")


class FakeMT5:
    """Minimal stand-in for the ``MetaTrader5`` module (sell-path surface)."""

    # Constants mirroring the real module (buy + sell families).
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2
    TRADE_RETCODE_INVALID_FILL = 10030
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_PLACED = 10008

    # Mutable state — defaults (market sits ABOVE the long reference entry
    # and below the short reference entry; bid 101.30 / ask 101.50).
    digits = 2
    point = 0.01
    trade_stops_level = 0
    volume_min = 0.01
    volume_max = 200.0
    volume_step = 0.01
    filling_mode = 3  # SYMBOL_FILLING_FOK | SYMBOL_FILLING_IOC
    tick = _Tick(bid=101.30, ask=101.50)
    order_send_result = None
    order_send_results = []
    last_err = (0, "ok")
    calls: list[tuple[str, tuple]] = []

    # --- callable API -------------------------------------------------------

    @classmethod
    def initialize(cls, **kwargs):
        cls.calls.append(("initialize", ()))
        return True

    @classmethod
    def terminal_info(cls):
        cls.calls.append(("terminal_info", ()))
        return None

    @classmethod
    def symbol_select(cls, symbol, enable):
        cls.calls.append(("symbol_select", (symbol, enable)))
        return True

    @classmethod
    def last_error(cls):
        return cls.last_err

    @classmethod
    def symbol_info(cls, symbol):
        cls.calls.append(("symbol_info", (symbol,)))
        return _SymbolInfo(
            filling_mode=cls.filling_mode,
            digits=cls.digits,
            point=cls.point,
            trade_stops_level=cls.trade_stops_level,
            volume_min=cls.volume_min,
            volume_max=cls.volume_max,
            volume_step=cls.volume_step,
        )

    @classmethod
    def symbol_info_tick(cls, symbol):
        cls.calls.append(("symbol_info_tick", (symbol,)))
        return cls.tick

    @classmethod
    def order_send(cls, request):
        cls.calls.append(("order_send", (dict(request),)))
        if cls.order_send_results:
            return cls.order_send_results.pop(0)
        return cls.order_send_result

    # --- test helpers --------------------------------------------------------

    @classmethod
    def reset(cls):
        cls.digits = 2
        cls.point = 0.01
        cls.trade_stops_level = 0
        cls.volume_min = 0.01
        cls.volume_max = 200.0
        cls.volume_step = 0.01
        cls.filling_mode = 3
        cls.tick = _Tick(bid=101.30, ask=101.50)
        cls.order_send_result = None
        cls.order_send_results = []
        cls.last_err = (0, "ok")
        cls.calls = []

    @classmethod
    def call(cls, name):
        """Args of the first recorded call to ``name``."""
        return next(args for n, args in cls.calls if n == name)

    @classmethod
    def calls_to(cls, name):
        """Args of EVERY recorded call to ``name``, in order."""
        return [args for n, args in cls.calls if n == name]


@pytest.fixture(autouse=True)
def fake_mt5(monkeypatch):
    """Inject FakeMT5 as the ``MetaTrader5`` module and reset per test."""
    FakeMT5.reset()
    monkeypatch.setitem(sys.modules, "MetaTrader5", FakeMT5)
    return FakeMT5


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


def _broker(**kwargs):
    kwargs.setdefault("symbol", "XAUUSD")
    return MT5Broker(**kwargs)


def _request(**overrides):
    """Short-geometry request: entry is the broken SUPPORT (reference), the
    stop sits ABOVE it and the target BELOW (sl > entry > tp)."""
    base = dict(
        symbol="XAUUSD",
        volume=0.01,
        entry=101.0,
        sl=102.0,
        tp=100.0,
        magic=77001,
        deviation=20,
        comment="gold-breakout-bot",
        side="short",
    )
    base.update(overrides)
    return OrderRequest(**base)


# --- 1. sell translation ----------------------------------------------------


def test_place_market_sell_sends_a_deal_at_the_bid():
    """A short is a MARKET SELL: a DEAL (not pending) at the BID, with sl ABOVE
    and tp BELOW that price, volume floored, identity passed through, and IOC
    filling first — the exact mirror of the buy request dict."""
    FakeMT5.order_send_result = _OrderSendResult(
        retcode=10009, order=77002, comment="done", price=101.30
    )
    res = _broker().place_market_sell(_request())

    req = FakeMT5.call("order_send")[0]
    assert req == {
        "action": 1,  # TRADE_ACTION_DEAL
        "symbol": "XAUUSD",
        "volume": 0.01,
        "type": 1,  # ORDER_TYPE_SELL — not ORDER_TYPE_BUY
        "price": 101.30,  # the live BID — not the ask, not the reference entry
        "sl": 102.0,  # resistance + buffer, ABOVE the bid
        "tp": 100.0,  # entry - stop distance, BELOW the bid
        "deviation": 20,
        "magic": 77001,
        "comment": "gold-breakout-bot",
        "type_time": 0,
        "type_filling": 1,  # ORDER_FILLING_IOC
    }
    assert req["price"] == FakeMT5.tick.bid  # the sell crosses the bid
    assert res.placed is True
    assert res.ticket == 77002


def test_place_market_sell_buy_path_request_is_untouched():
    """The long request dict (test_place_market_buy_...) is byte-identical:
    ORDER_TYPE_BUY at the ASK. Adding the sell method must not move the buy."""
    FakeMT5.order_send_result = _OrderSendResult(
        retcode=10009, order=77001, comment="done", price=101.50
    )
    _broker().place_market_buy(_request(side="long"))

    req = FakeMT5.call("order_send")[0]
    assert req["type"] == 0  # ORDER_TYPE_BUY
    assert req["price"] == 101.50  # the ask
    assert req["sl"] == 102.0
    assert req["tp"] == 100.0


# --- 2. bid not ask ---------------------------------------------------------


def test_place_market_sell_fills_at_the_bid_not_the_ask():
    """With bid 101.30 / ask 101.50 a sell must go out at 101.30 and report
    fill_price 101.30 — a sell that crossed the ask would be a gift to the
    market (the mirror of the buy path's ask discipline)."""
    FakeMT5.tick = _Tick(bid=101.30, ask=101.50)
    FakeMT5.order_send_result = _OrderSendResult(
        retcode=10009, order=77002, comment="done", price=101.30
    )
    res = _broker().place_market_sell(_request())

    req = FakeMT5.call("order_send")[0]
    assert req["price"] == 101.30
    assert req["price"] != FakeMT5.tick.ask
    assert res.fill_price == 101.30


# --- 3. mirrored stop-distance guard -----------------------------------------


def test_place_market_sell_refuses_a_stop_inside_the_minimum_above_the_bid():
    """Sell mirror of the buy guard: a stop loss sitting inside
    trade_stops_level ABOVE the bid would be bounced by the server (10016).
    Widening it would change the trade the risk gate approved, so refuse."""
    FakeMT5.trade_stops_level = 500  # 500 * 0.01 = $5.00 minimum distance
    FakeMT5.order_send_result = _OrderSendResult(
        retcode=10009, order=77002, comment="done", price=101.30
    )
    with pytest.raises(BrokerRejectedError) as excinfo:
        # sl 106.00 is 4.70 above bid 101.30 — inside the 5.00 minimum.
        _broker().place_market_sell(_request(entry=101.0, sl=106.0, tp=96.0))
    assert "minimum stop distance" in str(excinfo.value)
    assert FakeMT5.calls_to("order_send") == []


def test_place_market_sell_refuses_a_tp_inside_the_minimum_below_the_bid():
    FakeMT5.trade_stops_level = 500  # $5.00 minimum distance
    FakeMT5.order_send_result = _OrderSendResult(
        retcode=10009, order=77002, comment="done", price=101.30
    )
    with pytest.raises(BrokerRejectedError) as excinfo:
        # tp 96.50 is 4.80 below bid 101.30 — inside the 5.00 minimum.
        _broker().place_market_sell(_request(entry=101.0, sl=106.5, tp=96.5))
    assert "minimum stop distance" in str(excinfo.value)
    assert FakeMT5.calls_to("order_send") == []


def test_place_market_sell_allows_stops_outside_the_minimum_distance():
    FakeMT5.trade_stops_level = 500  # $5.00 minimum distance
    FakeMT5.order_send_result = _OrderSendResult(
        retcode=10009, order=77002, comment="done", price=101.30
    )
    # sl 106.40 is 5.10 above the bid and tp 96.20 is 5.10 below — both clear.
    res = _broker().place_market_sell(_request(entry=101.0, sl=106.4, tp=96.2))
    assert res.placed is True


def test_place_market_sell_buy_guard_is_unchanged():
    """The BUY-side distance guard still compares ask-sl and tp-ask (the sell
    flag must default to False so the existing buy checks stay byte-identical)."""
    FakeMT5.trade_stops_level = 500
    FakeMT5.order_send_result = _OrderSendResult(
        retcode=10009, order=77001, comment="done", price=101.50
    )
    with pytest.raises(BrokerRejectedError) as excinfo:
        _broker().place_market_buy(
            OrderRequest(
                symbol="XAUUSD", volume=0.01, entry=101.0, sl=101.0, tp=102.0,
                magic=77001, deviation=20, comment="c",
            )
        )
    assert "minimum stop distance" in str(excinfo.value)


# --- 4. dry-run sell --------------------------------------------------------


def _capture_logger():
    import io
    import logging

    logger = logging.getLogger(f"test-dry-run-sell-{id(object())}")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.INFO)
    stream = io.StringIO()
    logger.addHandler(logging.StreamHandler(stream))
    return logger, stream


def test_dry_run_place_market_sell_never_sends_and_logs_side_short():
    inner = SimulatedBroker(rates=_rates())
    logger, stream = _capture_logger()
    dry = DryRunBroker(inner, logger=logger)

    res = dry.place_market_sell(_request())

    assert res.placed is False
    assert res.ticket == 0
    assert res.retcode == 0
    assert "no order sent" in res.comment
    # Structural no-send: the inner ledger and position list stay untouched.
    assert inner.pending_orders("XAUUSD", 77001) == []
    assert inner.positions("XAUUSD", 77001) == []
    # SAFE-02: the would-be order is logged with its side.
    line = stream.getvalue()
    assert "event=order_plan" in line
    assert "side=short" in line
    assert "mode=dry-run" in line


# --- 5. simulated sell ------------------------------------------------------


def test_simulated_sell_fills_at_the_bid_and_opens_a_position():
    """The simulated sell mirrors the simulated buy: ledger entry carrying the
    side, an open position (the single-slot guard sees it), and a fill at the
    BID — with a spread set the bid and ask differ, and a sell must get the
    bid."""
    broker = SimulatedBroker(rates=_rates())
    broker._spread = 0.20  # bid != ask: mid 100.50 -> bid 100.40 / ask 100.60

    res = broker.place_market_sell(_request())

    assert res.placed is True
    assert res.retcode == 10009
    assert res.fill_price == pytest.approx(broker.quote("XAUUSD").bid)
    assert res.fill_price != pytest.approx(broker.quote("XAUUSD").ask)
    # The ledger entry records the side (to_log_fields now carries it).
    assert broker._orders[-1]["side"] == "short"
    # A market sell opens a position immediately (one-trade-at-a-time guard).
    assert [p.ticket for p in broker.positions("XAUUSD", 77001)] == [res.ticket]


# --- 6. side-agnostic risk_per_unit -----------------------------------------


def test_risk_per_unit_is_the_stop_distance_regardless_of_side():
    long_req = _request(side="long", entry=101.0, sl=100.09, tp=101.91)
    short_req = _request(side="short", entry=100.10, sl=101.01, tp=99.19)

    assert long_req.risk_per_unit == pytest.approx(101.0 - 100.09)
    assert short_req.risk_per_unit == pytest.approx(101.01 - 100.10)
    assert long_req.risk_per_unit == pytest.approx(abs(long_req.entry - long_req.sl))
    assert short_req.risk_per_unit == pytest.approx(abs(short_req.entry - short_req.sl))
    assert short_req.risk_per_unit > 0
