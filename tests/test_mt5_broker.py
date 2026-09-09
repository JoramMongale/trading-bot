"""Tests for the real MT5 adapter via an injected fake ``MetaTrader5`` module.

The ``MetaTrader5`` pip package is Windows-only, so the adapter's lazy
:func:`~trading_bot.broker.mt5._load_mt5` import is the seam: tests inject a
FakeMT5 into ``sys.modules["MetaTrader5"]`` and every method call resolves to
it. The no-package error path is covered by popping the fake so the real
(absent) package is attempted — and fails with a Windows hint.
"""

import os
import sys
from collections import namedtuple

import numpy as np
import pandas as pd
import pytest

import trading_bot.broker.mt5 as mt5_mod
from trading_bot.broker.base import BrokerRejectedError, BrokerUnavailableError, OrderRequest
from trading_bot.broker.dry_run import DryRunBroker
from trading_bot.broker.mt5 import MT5Broker, _load_mt5
from trading_bot.broker.simulated import SimulatedBroker

# --- MT5 result/order objects (namedtuple stand-ins for the real API) ------

_TerminalInfo = namedtuple("_TerminalInfo", "connected trade_allowed")
# The real TerminalInfo also carries `path` (the INSTALL folder). The RPC
# bridge's does not, which is why the adapter treats a missing path as "nothing
# to check" rather than as a failure.
_TerminalInfoWithPath = namedtuple("_TerminalInfoWithPath", "connected trade_allowed path")
_SymbolInfo = namedtuple(
    "_SymbolInfo",
    "filling_mode digits point trade_stops_level volume_min volume_max volume_step",
)
_Tick = namedtuple("_Tick", "bid ask")
_AccountInfo = namedtuple("_AccountInfo", "login server currency balance trade_mode")
_OrderSendResult = namedtuple("_OrderSendResult", "retcode order comment price")
_Order = namedtuple("_Order", "ticket symbol price sl tp volume magic")
_Position = namedtuple("_Position", "ticket symbol magic")


class FakeMT5:
    """Stand-in for the ``MetaTrader5`` module, injected into ``sys.modules``.

    All state is class-level so tests flip flags before calling into the
    adapter; :meth:`reset` restores defaults between tests. Every API call is
    recorded in ``calls`` as ``(name, args)`` so tests can assert exact
    invocation parameters (e.g. ``start_pos == 1``).
    """

    # Constants mirroring the real module.
    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_PENDING = 5
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_BUY_STOP = 4
    ORDER_TIME_GTC = 0
    # Real MT5 values. type_filling takes ORDER_FILLING_*; symbol_info().
    # filling_mode is a bitmask of SYMBOL_FILLING_* — a DIFFERENT family, and
    # there is no SYMBOL_FILLING_RETURN flag at all. The old fake invented one
    # (=4) and mirrored the production code's confusion, so 30 tests passed
    # over an implementation that raised AttributeError on a real terminal.
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2
    SYMBOL_FILLING_FOK = 1
    SYMBOL_FILLING_IOC = 2
    TRADE_RETCODE_INVALID_FILL = 10030
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_PLACED = 10008
    TRADE_RETCODE_REJECT = 10016  # arbitrary failure retcode for tests

    # Mutable state — defaults.
    initialize_ok = True
    terminal_connected = True
    trade_allowed = True
    symbol_select_ok = True
    last_err = (0, "ok")
    rates = None
    account = None
    filling_mode = SYMBOL_FILLING_FOK | SYMBOL_FILLING_IOC  # 3, as Exness XAUUSDm reports
    # Symbol contract details, defaulted to Exness XAUUSDm's real values.
    symbol_info_none = False
    digits = 2
    point = 0.01
    trade_stops_level = 0
    volume_min = 0.01
    volume_max = 200.0
    volume_step = 0.01
    tick = None
    order_send_result = None
    orders = []
    positions = []
    calls: list[tuple[str, tuple]] = []

    # --- callable API -------------------------------------------------------

    @classmethod
    def initialize(cls, **kwargs):
        # The real initialize() takes path=/portable= for selecting one install
        # among several. Recorded rather than ignored so a test can assert the
        # adapter passes them ONLY when configured to.
        cls.calls.append(("initialize", ()))
        cls.initialize_kwargs = kwargs
        return cls.initialize_ok

    @classmethod
    def shutdown(cls):
        cls.calls.append(("shutdown", ()))

    @classmethod
    def last_error(cls):
        return cls.last_err

    @classmethod
    def terminal_info(cls):
        cls.calls.append(("terminal_info", ()))
        if cls.terminal_path_reported is not None:
            return _TerminalInfoWithPath(
                connected=cls.terminal_connected,
                trade_allowed=cls.trade_allowed,
                path=cls.terminal_path_reported,
            )
        return _TerminalInfo(connected=cls.terminal_connected, trade_allowed=cls.trade_allowed)

    @classmethod
    def symbol_select(cls, symbol, enable):
        cls.calls.append(("symbol_select", (symbol, enable)))
        return cls.symbol_select_ok

    @classmethod
    def copy_rates_from_pos(cls, symbol, timeframe, start_pos, count):
        cls.calls.append(("copy_rates_from_pos", (symbol, timeframe, start_pos, count)))
        return cls.rates

    @classmethod
    def account_info(cls):
        cls.calls.append(("account_info", ()))
        return cls.account

    @classmethod
    def symbol_info(cls, symbol):
        cls.calls.append(("symbol_info", (symbol,)))
        if cls.symbol_info_none:
            return None
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
        # dict is reused and mutated across filling-mode retries, so snapshot it
        cls.calls.append(("order_send", (dict(request),)))
        if cls.order_send_results:
            return cls.order_send_results.pop(0)
        return cls.order_send_result

    @classmethod
    def orders_get(cls, symbol=None):
        cls.calls.append(("orders_get", (symbol,)))
        # Real MT5 scopes by symbol server-side; mirror that so the adapter's
        # magic-only filter is exercised against symbol-scoped input.
        if symbol is None:
            return cls.orders or None
        return [o for o in cls.orders if o.symbol == symbol] or None

    @classmethod
    def positions_get(cls, symbol=None):
        cls.calls.append(("positions_get", (symbol,)))
        if symbol is None:
            return cls.positions or None
        return [p for p in cls.positions if p.symbol == symbol] or None

    # --- test helpers --------------------------------------------------------

    @classmethod
    def reset(cls):
        cls.initialize_kwargs = {}
        cls.terminal_path_reported = None
        cls.initialize_ok = True
        cls.terminal_connected = True
        cls.trade_allowed = True
        cls.symbol_select_ok = True
        cls.last_err = (0, "ok")
        cls.rates = None
        cls.account = None
        cls.filling_mode = cls.SYMBOL_FILLING_FOK | cls.SYMBOL_FILLING_IOC
        cls.symbol_info_none = False
        cls.digits = 2
        cls.point = 0.01
        cls.trade_stops_level = 0
        cls.volume_min = 0.01
        cls.volume_max = 200.0
        cls.volume_step = 0.01
        # Market ask sits ABOVE the reference entry (101.0) used by _request():
        # that is the whole point — the setup fires on a close above
        # resistance, so the level is already behind the market.
        cls.tick = _Tick(bid=101.30, ask=101.50)
        cls.order_send_result = None
        cls.order_send_results = []  # queue; consumed before order_send_result
        cls.orders = []
        cls.positions = []
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
    """Inject FakeMT5 as the ``MetaTrader5`` module and reset per test.

    ``_load_mt5()`` performs the import at call time, so no module reload is
    needed: the injected sys.modules entry is picked up by the very next call.
    """
    FakeMT5.reset()
    FakeMT5.rates = _rates_recarray()
    FakeMT5.account = _AccountInfo(
        login=999, server="DemoServer", currency="USD", balance=10000.0, trade_mode=0
    )
    monkeypatch.setitem(sys.modules, "MetaTrader5", FakeMT5)
    return FakeMT5


def _rates_recarray(n=10, start=1609459200):
    """numpy recarray with the documented MT5 ``copy_rates_from_pos`` dtype."""
    arr = np.zeros(
        n,
        dtype=[
            ("time", "i8"),
            ("open", "f8"),
            ("high", "f8"),
            ("low", "f8"),
            ("close", "f8"),
            ("tick_volume", "i8"),
            ("spread", "i8"),
            ("real_volume", "i8"),
        ],
    )
    for i in range(n):
        arr[i] = (start + i * 300, 100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i, 10, 5, 10)
    return arr.view(np.recarray)


def _rates(n=10):
    """In-memory OHLC frame for the SimulatedBroker wrapped by DryRunBroker."""
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


# --- lazy import / unavailability ------------------------------------------


def test_module_imports_without_meta_trader5_package():
    """The module must import cleanly — MetaTrader5 is never top-level.

    ``_load_mt5()`` is the only import site; the AST must not contain a
    module-level ``import MetaTrader5`` (that is what breaks on macOS).
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(mt5_mod))
    for node in tree.body:  # module-top-level statements only
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                assert not alias.name.startswith("MetaTrader5"), (
                    f"top-level import of MetaTrader5 found: {ast.dump(node)}"
                )
    # The sanctioned lazy import site must exist.
    assert "_load_mt5" in inspect.getsource(mt5_mod)


def test_load_mt5_without_package_raises_windows_hint(monkeypatch):
    """Without the package, the error is actionable and names Windows."""
    monkeypatch.setitem(sys.modules, "MetaTrader5", None)
    with pytest.raises(BrokerUnavailableError) as excinfo:
        _load_mt5()
    assert "Windows" in str(excinfo.value)
    assert "SimulatedBroker" in str(excinfo.value)


# --- connect / disconnect ----------------------------------------------------


def test_connect_succeeds_against_healthy_terminal():
    _broker().connect()
    assert FakeMT5.call("initialize") == ()
    assert FakeMT5.call("terminal_info") == ()
    assert FakeMT5.call("symbol_select") == ("XAUUSD", True)


def test_connect_initialize_failure_raises():
    FakeMT5.initialize_ok = False
    FakeMT5.last_err = (1001, "init boom")
    with pytest.raises(BrokerUnavailableError) as excinfo:
        _broker().connect()
    assert "initialize() failed: 1001 init boom" in str(excinfo.value)


def test_connect_terminal_not_connected_raises():
    FakeMT5.terminal_connected = False
    with pytest.raises(BrokerUnavailableError) as excinfo:
        _broker().connect()
    assert "terminal not connected" in str(excinfo.value)


def test_connect_trade_not_allowed_raises():
    FakeMT5.trade_allowed = False
    with pytest.raises(BrokerUnavailableError) as excinfo:
        _broker().connect()
    assert "trade_allowed=False" in str(excinfo.value)


def test_connect_symbol_select_failure_raises():
    FakeMT5.symbol_select_ok = False
    FakeMT5.last_err = (1002, "not in market watch")
    with pytest.raises(BrokerUnavailableError) as excinfo:
        _broker().connect()
    assert "symbol_select(XAUUSD) failed: 1002 not in market watch" in str(excinfo.value)


# --- terminal selection: three accounts, three installs, one machine --------
#
# Paths here are POSIX because the tests run on macOS and the adapter uses
# os.path, which is platform-native on both sides. In production these are
# Windows paths (C:\MT5-Gold\terminal64.exe) resolved by the same code.


def test_connect_without_terminal_path_passes_no_kwargs():
    """The macOS/bridge route must keep calling initialize() bare.

    The siliconmetatrader5 bridge's initialize() takes no path/portable, so
    passing them unconditionally would break every existing deployment.
    """
    _broker().connect()
    assert FakeMT5.initialize_kwargs == {}


def test_connect_with_terminal_path_passes_path_and_portable():
    _broker(
        terminal_path="/opt/mt5-gold/terminal64.exe", terminal_portable=True
    ).connect()
    assert FakeMT5.initialize_kwargs == {
        "path": "/opt/mt5-gold/terminal64.exe",
        "portable": True,
    }


def test_connect_accepts_terminal_whose_install_matches():
    FakeMT5.terminal_path_reported = "/opt/mt5-gold"
    _broker(terminal_path="/opt/mt5-gold/terminal64.exe").connect()
    assert FakeMT5.call("symbol_select") == ("XAUUSD", True)


def test_connect_refuses_when_attached_to_a_different_install():
    """The failure this whole feature exists to prevent.

    Asking for the gold install and being handed the bitcoin one must abort,
    not trade. Silently proceeding would place gold's orders, sized off gold's
    risk percentage, against bitcoin's balance — and every log line would look
    healthy while it happened.
    """
    FakeMT5.terminal_path_reported = "/opt/mt5-btc"
    with pytest.raises(BrokerUnavailableError) as excinfo:
        _broker(terminal_path="/opt/mt5-gold/terminal64.exe").connect()
    msg = str(excinfo.value)
    assert "WRONG terminal" in msg
    want_dir = os.path.normcase(os.path.dirname(os.path.abspath("/opt/mt5-gold/terminal64.exe")))
    got_dir = os.path.normcase(os.path.abspath("/opt/mt5-btc"))
    assert want_dir in msg and got_dir in msg
    # Aborted BEFORE touching Market Watch — nothing was set up to trade.
    assert not any(c[0] == "symbol_select" for c in FakeMT5.calls)


def test_connect_skips_install_check_when_terminal_reports_no_path():
    """The RPC bridge reports no path; that must not be read as a mismatch."""
    FakeMT5.terminal_path_reported = None
    _broker(terminal_path="/opt/mt5-gold/terminal64.exe").connect()
    assert FakeMT5.call("symbol_select") == ("XAUUSD", True)


def test_connect_initialize_failure_names_the_path_it_asked_for():
    FakeMT5.initialize_ok = False
    FakeMT5.last_err = (1001, "init boom")
    with pytest.raises(BrokerUnavailableError) as excinfo:
        _broker(terminal_path="/opt/mt5-gold/terminal64.exe").connect()
    assert "path=/opt/mt5-gold/terminal64.exe" in str(excinfo.value)


def test_disconnect_calls_shutdown():
    _broker().disconnect()
    assert FakeMT5.call("shutdown") == ()


def test_fetch_rates_none_with_disconnected_terminal_raises():
    """04-01: a dead terminal must surface as BrokerUnavailableError, not an
    empty frame — otherwise the reconnect path in the CLI never fires."""
    FakeMT5.rates = None
    FakeMT5.terminal_connected = False
    with pytest.raises(BrokerUnavailableError) as excinfo:
        _broker().fetch_rates("XAUUSD", "M5", 5)
    assert "disconnected" in str(excinfo.value)


def test_reconnect_reinitialises_and_reconnects():
    """04-01: reconnect() drops any cached transport and runs the full
    connect() verification again (reachable, trade_allowed, correct install)."""
    broker = _broker(terminal_path="/opt/mt5-gold/terminal64.exe")
    broker._mt5_cached = object()  # simulate a cached (dead) silicon bridge
    FakeMT5.calls.clear()
    FakeMT5.terminal_path_reported = "/opt/mt5-gold"
    broker.reconnect()
    # initialize() was called again (re-attach), and the expected-terminal
    # check ran against the reconnected info.
    assert FakeMT5.call("initialize") == ()
    assert FakeMT5.call("terminal_info") == ()


def test_reconnect_shutdown_failure_does_not_block_reattach():
    """A dead bridge socket may not answer shutdown(); that must not prevent
    the reconnect from proceeding to initialize()."""
    broker = _broker()
    broker._mt5_cached = object()
    original = FakeMT5.shutdown
    FakeMT5.shutdown = classmethod(lambda cls: (_ for _ in ()).throw(RuntimeError("dead socket")))
    try:
        broker.reconnect()
    finally:
        FakeMT5.shutdown = original
    assert FakeMT5.call("initialize") == ()


# --- fetch_rates -------------------------------------------------------------


def test_fetch_rates_uses_start_pos_1_and_returns_closed_bars():
    df = _broker().fetch_rates("XAUUSD", "M5", 5)

    assert FakeMT5.call("copy_rates_from_pos")[2] == 1  # skip forming bar
    assert list(df.columns) == ["open", "high", "low", "close"]
    assert df.index.name == "time"
    assert df.index.tolist()[0] == pd.Timestamp("2021-01-01 00:00:00")
    assert len(df) == 10  # whole fake sample is returned
    assert df["close"].iloc[-1] == 100.5 + 9
    assert str(df.index.dtype).startswith("datetime64")


def test_fetch_rates_m1_uses_m1_constant():
    _broker().fetch_rates("XAUUSD", "M1", 3)
    assert FakeMT5.call("copy_rates_from_pos")[1] == FakeMT5.TIMEFRAME_M1


def test_fetch_rates_m5_uses_m5_constant():
    _broker().fetch_rates("XAUUSD", "M5", 3)
    assert FakeMT5.call("copy_rates_from_pos")[1] == FakeMT5.TIMEFRAME_M5


def test_fetch_rates_unknown_timeframe_raises_value_error():
    with pytest.raises(ValueError):
        _broker().fetch_rates("XAUUSD", "H4", 5)


def test_fetch_rates_none_returns_empty_frame_not_error():
    """A no-data poll is normal for a fresh start — empty frame, no raise."""
    FakeMT5.rates = None
    df = _broker().fetch_rates("XAUUSD", "M5", 5)
    assert list(df.columns) == ["open", "high", "low", "close"]
    assert df.index.name == "time"
    assert df.empty


# --- account_info -------------------------------------------------------------


def test_account_info_maps_fields_and_trade_mode():
    ai = _broker().account_info()
    assert ai.login == 999
    assert ai.server == "DemoServer"
    assert ai.currency == "USD"
    assert ai.balance == 10000.0
    assert ai.trade_mode == 0  # demo


def test_account_info_none_raises():
    FakeMT5.account = None
    FakeMT5.last_err = (1003, "no account")
    with pytest.raises(BrokerUnavailableError) as excinfo:
        _broker().account_info()
    assert "1003 no account" in str(excinfo.value)


# --- place_market_buy --------------------------------------------------------


def _ok(order=77001, price=101.50):
    return _OrderSendResult(retcode=10009, order=order, comment="done", price=price)


def test_place_market_buy_sends_a_deal_at_the_ask_not_a_stop_at_the_level():
    """The bug this whole change exists for.

    ``detect_setups`` fires on a close ABOVE resistance, so ``entry`` (101.0)
    is always behind the market (ask 101.50). A Buy Stop there is below market
    and the server answers 10015 Invalid price, every time, forever. The order
    must be a DEAL at the ask instead."""
    FakeMT5.order_send_result = _ok()
    res = _broker().place_market_buy(_request())

    req = FakeMT5.call("order_send")[0]
    assert req == {
        "action": 1,  # TRADE_ACTION_DEAL, not TRADE_ACTION_PENDING
        "symbol": "XAUUSD",
        "volume": 0.01,
        "type": 0,  # ORDER_TYPE_BUY, not ORDER_TYPE_BUY_STOP
        "price": 101.50,  # the live ask — NOT entry=101.0, which is below market
        "sl": 100.0,
        "tp": 102.0,
        "deviation": 20,
        "magic": 77001,
        "comment": "gold-breakout-bot",
        "type_time": 0,
        "type_filling": 1,  # ORDER_FILLING_IOC
    }
    assert req["price"] > _request().entry
    assert res.placed is True
    assert res.ticket == 77001


def test_place_market_buy_reports_the_realised_fill_price():
    """The fill is what the account actually paid; the backtest booked the
    reference level. Both have to survive to the caller or there is no way to
    tell which numbers the equity curve belongs to."""
    FakeMT5.order_send_result = _ok(price=101.62)
    res = _broker().place_market_buy(_request())
    assert res.fill_price == 101.62
    assert res.fill_price != _request().entry


def test_place_market_buy_rounds_prices_to_symbol_digits():
    """Full-precision strategy arithmetic (2621.4599999...) is an invalid price
    on a 2-digit symbol (10015)."""
    FakeMT5.tick = _Tick(bid=101.3, ask=101.5049999)
    FakeMT5.order_send_result = _ok()
    _broker().place_market_buy(_request(entry=101.0, sl=100.00499, tp=101.99501))

    req = FakeMT5.call("order_send")[0]
    assert req["price"] == 101.50
    assert req["sl"] == 100.00
    assert req["tp"] == 102.00


def test_place_market_buy_prefers_ioc_then_fok_for_market_execution():
    """Market orders take ORDER_FILLING_IOC/FOK. RETURN is the pending-order
    mode and most brokers reject it on a DEAL, so it must not lead."""
    FakeMT5.filling_mode = FakeMT5.SYMBOL_FILLING_FOK | FakeMT5.SYMBOL_FILLING_IOC
    FakeMT5.order_send_result = _ok()
    _broker().place_market_buy(_request())
    assert FakeMT5.call("order_send")[0]["type_filling"] == FakeMT5.ORDER_FILLING_IOC


def test_place_market_buy_retries_next_filling_on_invalid_fill():
    """retcode 10030 means the broker rejected that filling mode: retry the
    next candidate instead of surfacing a rejection the user cannot act on."""
    FakeMT5.filling_mode = FakeMT5.SYMBOL_FILLING_FOK
    FakeMT5.order_send_results = [
        _OrderSendResult(retcode=10030, order=0, comment="invalid fill", price=0.0),
        _ok(order=55),
    ]
    res = _broker().place_market_buy(_request())
    sent = [c[0]["type_filling"] for c in FakeMT5.calls_to("order_send")]
    assert sent == [FakeMT5.ORDER_FILLING_FOK, FakeMT5.ORDER_FILLING_IOC]
    assert res.ticket == 55


def test_filling_candidates_work_without_symbol_filling_constants():
    """The siliconmetatrader5 bridge exposes ORDER_FILLING_* but NOT
    SYMBOL_FILLING_*. Reading the mask numerically keeps the adapter working
    against it — this is the exact AttributeError that killed the live bot
    mid-order on 2026-08-19."""
    from trading_bot.broker.mt5 import _filling_candidates

    class _BridgeLike:
        ORDER_FILLING_FOK = 0
        ORDER_FILLING_IOC = 1
        ORDER_FILLING_RETURN = 2

    class _SI:
        filling_mode = 3  # FOK | IOC

    # IOC, FOK, then RETURN last — RETURN is for pending orders.
    assert _filling_candidates(_BridgeLike, _SI) == [1, 0, 2]


def test_place_market_buy_refuses_volume_below_the_symbol_minimum():
    """Silently bumping size up to volume_min would place a bigger position
    than the config asked for — size is risk, so this refuses instead."""
    FakeMT5.volume_min = 0.10
    FakeMT5.order_send_result = _ok()
    with pytest.raises(BrokerRejectedError) as excinfo:
        _broker().place_market_buy(_request())
    assert "below the symbol minimum" in str(excinfo.value)
    assert FakeMT5.calls_to("order_send") == []


def test_place_market_buy_floors_volume_onto_the_lot_grid_never_rounds_up():
    FakeMT5.volume_step = 0.01
    FakeMT5.order_send_result = _ok()
    req = _request()
    _broker().place_market_buy(
        OrderRequest(
            symbol=req.symbol, volume=0.038, entry=req.entry, sl=req.sl, tp=req.tp,
            magic=req.magic, deviation=req.deviation, comment=req.comment,
        )
    )
    assert FakeMT5.call("order_send")[0]["volume"] == 0.03  # not 0.04


def test_place_market_buy_refuses_volume_above_the_symbol_maximum():
    FakeMT5.volume_max = 0.02
    with pytest.raises(BrokerRejectedError) as excinfo:
        _broker().place_market_buy(
            OrderRequest(
                symbol="XAUUSD", volume=5.0, entry=101.0, sl=100.0, tp=102.0,
                magic=77001, deviation=20, comment="c",
            )
        )
    assert "exceeds the symbol maximum" in str(excinfo.value)


def test_place_market_buy_refuses_stops_inside_the_brokers_minimum_distance():
    """Inside trade_stops_level the server answers 10016. Widening the stop to
    comply would make the loss bigger than the one the risk gate approved, so
    the trade is refused instead of quietly altered."""
    FakeMT5.trade_stops_level = 500  # 500 * 0.01 = $5.00 minimum distance
    FakeMT5.order_send_result = _ok()
    with pytest.raises(BrokerRejectedError) as excinfo:
        _broker().place_market_buy(
            _request(entry=101.0, sl=101.0, tp=102.0)  # sl 0.50 from ask 101.50
        )
    assert "minimum stop distance" in str(excinfo.value)
    assert FakeMT5.calls_to("order_send") == []


def test_place_market_buy_allows_stops_outside_the_minimum_distance():
    FakeMT5.trade_stops_level = 10  # $0.10
    FakeMT5.order_send_result = _ok()
    assert _broker().place_market_buy(_request()).placed is True


def test_place_market_buy_without_a_live_ask_is_rejected_not_sent_at_zero():
    """Market closed / no quote. Sending price=0 would be an invalid price at
    best and an unpriced market order at worst."""
    FakeMT5.tick = None
    FakeMT5.last_err = (4106, "market closed")
    with pytest.raises(BrokerRejectedError) as excinfo:
        _broker().place_market_buy(_request())
    assert "no live ask" in str(excinfo.value)
    assert FakeMT5.calls_to("order_send") == []


def test_place_market_buy_unknown_symbol_raises_broker_unavailable():
    FakeMT5.symbol_info_none = True
    FakeMT5.last_err = (4301, "unknown symbol")
    with pytest.raises(BrokerUnavailableError) as excinfo:
        _broker().place_market_buy(_request())
    assert "symbol_info" in str(excinfo.value)


def test_place_market_buy_retcode_placed_also_counts_as_placed():
    FakeMT5.order_send_result = _OrderSendResult(
        retcode=10008, order=42, comment="placed", price=101.5
    )
    res = _broker().place_market_buy(_request())
    assert res.placed is True
    assert res.ticket == 42
    assert res.retcode == 10008


def test_place_market_buy_failure_retcode_raises_broker_rejected():
    FakeMT5.order_send_result = _OrderSendResult(
        retcode=10016, order=0, comment="invalid stops", price=0.0
    )
    with pytest.raises(BrokerRejectedError) as excinfo:
        _broker().place_market_buy(_request())
    assert "10016" in str(excinfo.value)


def test_place_market_buy_none_result_raises_broker_rejected():
    FakeMT5.order_send_result = None
    FakeMT5.last_err = (1004, "no response")
    with pytest.raises(BrokerRejectedError) as excinfo:
        _broker().place_market_buy(_request())
    assert "order_send returned None" in str(excinfo.value)
    assert "1004 no response" in str(excinfo.value)


def _capture_logger():
    import io
    import logging

    logger = logging.getLogger(f"test-dry-run-{id(object())}")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.INFO)
    stream = io.StringIO()
    logger.addHandler(logging.StreamHandler(stream))
    return logger, stream


def test_dry_run_place_market_buy_never_touches_inner_broker():
    inner = SimulatedBroker(rates=_rates())
    dry = DryRunBroker(inner)

    res = dry.place_market_buy(_request())

    assert res.placed is False
    assert res.ticket == 0
    assert res.retcode == 0
    assert "no order sent" in res.comment
    # The inner broker must not report a phantom order OR a phantom position:
    # a market entry opens a position immediately, so a leaked dry-run order
    # would show up there rather than in the pending list.
    assert inner.pending_orders("XAUUSD", 77001) == []
    assert inner.positions("XAUUSD", 77001) == []


def test_dry_run_place_market_buy_logs_order_plan_decision():
    inner = SimulatedBroker(rates=_rates())
    logger, stream = _capture_logger()
    dry = DryRunBroker(inner, logger=logger)

    dry.place_market_buy(_request())

    line = stream.getvalue()
    assert "event=order_plan" in line
    assert "mode=dry-run" in line
    assert "symbol=XAUUSD" in line
    assert "entry=101.0" in line
    assert "sl=100.0" in line
    assert "tp=102.0" in line
    assert "magic=77001" in line


def test_dry_run_delegates_read_only_methods():
    inner = SimulatedBroker(rates=_rates())
    dry = DryRunBroker(inner)

    assert dry.fetch_rates("XAUUSD", "M5", 3).index.tolist() == _rates().index[7:].tolist()
    assert dry.account_info() == inner.account_info()
    dry.connect()  # no-op on SimulatedBroker; must not raise
    dry.disconnect()


def test_dry_run_pending_and_positions_pass_through():
    """Read-only introspection is delegated, unlike placement.

    A market entry opens a position and leaves nothing pending, so the
    pass-through is checked on both lists — the position side is what actually
    holds the one-trade-at-a-time slot now.
    """
    inner = SimulatedBroker(rates=_rates())
    inner.place_market_buy(_request(entry=101.0))
    dry = DryRunBroker(inner)

    assert dry.pending_orders("XAUUSD", 77001) == []
    assert [p.ticket for p in dry.positions("XAUUSD", 77001)] == [1000]

    inner.simulate_position(2000, "XAUUSD", 77001)
    assert [p.ticket for p in dry.positions("XAUUSD", 77001)] == [1000, 2000]
