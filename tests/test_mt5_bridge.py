"""MT5Broker transport selection (quick task 260819-nhq).

macOS has no ``MetaTrader5`` wheel on any architecture, so the adapter also
speaks to a containerised terminal through the ``siliconmetatrader5`` RPC
bridge. These tests lock which transport each ``bridge`` setting resolves to,
and — critically — that the default still routes through the module-level
``_load_mt5`` import site the 30 fake-MT5 tests inject into.
"""

from __future__ import annotations

import sys
import types

import pytest

from trading_bot.broker.base import BrokerUnavailableError
from trading_bot.broker.mt5 import MT5Broker


class _FakeBridge:
    """Stand-in for ``siliconmetatrader5.MetaTrader5`` (an instance, not a module)."""

    instances = 0

    def __init__(self, host, port, keepalive=False):
        _FakeBridge.instances += 1
        self.host = host
        self.port = port
        self.keepalive = keepalive


@pytest.fixture
def fake_silicon(monkeypatch):
    _FakeBridge.instances = 0
    mod = types.ModuleType("siliconmetatrader5")
    mod.MetaTrader5 = _FakeBridge
    monkeypatch.setitem(sys.modules, "siliconmetatrader5", mod)
    return mod


@pytest.fixture
def fake_native(monkeypatch):
    mod = types.ModuleType("MetaTrader5")
    mod.marker = "native"
    monkeypatch.setitem(sys.modules, "MetaTrader5", mod)
    return mod


def test_default_bridge_is_native(fake_native):
    """No bridge argument -> the Windows package via _load_mt5, unchanged.

    This is what keeps the existing fake-MT5 suite (sys.modules injection)
    working against the same adapter.
    """
    assert MT5Broker(symbol="XAUUSD")._mt5() is fake_native


def test_native_is_not_cached(fake_native, monkeypatch):
    """The native path must re-import per call so tests can swap sys.modules
    between calls — caching it would freeze the first-injected fake."""
    broker = MT5Broker(symbol="XAUUSD", bridge="native")
    assert broker._mt5() is fake_native
    other = __import__("types").ModuleType("MetaTrader5")
    monkeypatch.setitem(sys.modules, "MetaTrader5", other)
    assert broker._mt5() is other


def test_silicon_bridge_builds_with_configured_host_and_port(fake_silicon):
    b = MT5Broker(
        symbol="XAUUSD", bridge="silicon", bridge_host="127.0.0.1", bridge_port=9001
    )
    mt5 = b._mt5()
    assert isinstance(mt5, _FakeBridge)
    assert (mt5.host, mt5.port, mt5.keepalive) == ("127.0.0.1", 9001, True)


def test_silicon_bridge_is_cached(fake_silicon):
    """The bridge holds an RPC socket — it must be built once, not per call."""
    b = MT5Broker(symbol="XAUUSD", bridge="silicon")
    assert b._mt5() is b._mt5()
    assert _FakeBridge.instances == 1


def test_auto_prefers_native_when_available(fake_native, fake_silicon):
    assert MT5Broker(symbol="XAUUSD", bridge="auto")._mt5() is fake_native
    assert _FakeBridge.instances == 0


def test_auto_falls_back_to_bridge_without_native(monkeypatch, fake_silicon):
    monkeypatch.delitem(sys.modules, "MetaTrader5", raising=False)
    monkeypatch.setattr(
        "trading_bot.broker.mt5._load_mt5",
        lambda: (_ for _ in ()).throw(BrokerUnavailableError("no native")),
    )
    assert isinstance(MT5Broker(symbol="XAUUSD", bridge="auto")._mt5(), _FakeBridge)


def test_missing_silicon_package_is_actionable(monkeypatch):
    """A None entry in sys.modules makes ``import`` raise ImportError, so this
    holds whether or not the package is actually installed."""
    monkeypatch.setitem(sys.modules, "siliconmetatrader5", None)
    with pytest.raises(BrokerUnavailableError, match="pip install siliconmetatrader5"):
        MT5Broker(symbol="XAUUSD", bridge="silicon")._mt5()


def test_unreachable_bridge_is_actionable(monkeypatch):
    """A refused RPC connection names the port and points at the container."""
    mod = types.ModuleType("siliconmetatrader5")

    def _boom(host, port, keepalive=False):
        raise ConnectionRefusedError("connection refused")

    mod.MetaTrader5 = _boom
    monkeypatch.setitem(sys.modules, "siliconmetatrader5", mod)
    with pytest.raises(BrokerUnavailableError, match="container running"):
        MT5Broker(symbol="XAUUSD", bridge="silicon")._mt5()
