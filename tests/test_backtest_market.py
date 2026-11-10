"""Tests for scripts/backtest_market.py and the fetcher's spec sidecar."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


bm = _load("backtest_market_under_test", "backtest_market.py")
fb = _load("fetch_broker_history_under_test", "fetch_broker_history.py")


def _trade(direction, entry, sl, exit_price, day):
    return {"direction": direction, "entry": entry, "sl": sl, "exit_price": exit_price,
            "exit_reason": "TP" if exit_price != sl else "SL",
            "entry_time": pd.Timestamp("2026-01-01") + pd.Timedelta(days=day)}


def test_net_r_charges_spread_both_sides():
    assert bm.net_r(_trade("long", 100.0, 99.0, 101.0, 0), 0.1) == 0.9
    assert bm.net_r(_trade("short", 100.0, 101.0, 101.0, 0), 0.1) == -1.1


def test_pass_needs_t_and_both_halves_positive():
    good = [_trade("long", 100, 99, 101 if i % 3 else 99, i) for i in range(90)]
    s = bm.row_stats(good, 0.0)
    assert s["pass"] and s["avg1"] > 0 and s["avg2"] > 0
    # Same overall edge, but all the losses in the second half -> fail.
    lopsided = ([_trade("long", 100, 99, 101, i) for i in range(45)]
                + [_trade("long", 100, 99, 101 if i % 2 else 99, 45 + i) for i in range(45)]
                + [_trade("long", 100, 99, 99, 90 + i) for i in range(25)])
    s2 = bm.row_stats(lopsided, 0.0)
    assert s2["avg2"] < 0 and not s2["pass"]


def test_too_few_trades_is_none():
    assert bm.row_stats([_trade("long", 100, 99, 101, i) for i in range(5)], 0.0) is None


def test_spec_from_terminal_writes_loadable_sidecar(tmp_path):
    info = SimpleNamespace(name="EURJPYc", digits=3, point=0.001, trade_tick_size=0.001,
                           trade_tick_value=0.65, trade_contract_size=1000.0,
                           volume_min=0.01, volume_step=0.01, spread=22)
    mt5 = SimpleNamespace(symbol_info=lambda s: info,
                          account_info=lambda: SimpleNamespace(currency="USC"),
                          last_error=lambda: (0, ""))
    spec = fb.spec_from_terminal(mt5, "EURJPYc", pd.Series([18, 20, 0, 24]))
    assert spec["spread_points_median"] == 20.0 and spec["account_currency"] == "USC"
    p = tmp_path / "EURJPYc_M5_broker.spec.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    from trading_bot.data.loader import load_instrument_spec
    loaded = load_instrument_spec(p)
    assert loaded.symbol == "EURJPYc" and abs(loaded.spread_price - 0.02) < 1e-12
