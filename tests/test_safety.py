"""SAFE-03 demo-only execution guard tests (plan 02-03).

Verifies ``verify_execution_allowed`` across all 8 mode × account
combinations: dry-run never blocks (orders never sent anyway), a REAL
account requires the explicit ``[live] enabled=true`` opt-in, and
mode='demo' must never trade a REAL account. Also guards the purity
contract — safety.py must never import the Windows-only MetaTrader5
package (RESEARCH.md).

Config and account fixtures are constructed directly via the dataclasses
(config.py / broker.base.py) — faster than tmp TOML and keeps the tests
focused on the guard's decision matrix.
"""

from pathlib import Path

import pytest

from trading_bot.broker.base import AccountInfo
from trading_bot.config import (
    BacktestConfig,
    Config,
    DataConfig,
    LiveConfig,
    StrategyConfig,
    TradingConfig,
)
from trading_bot.live.safety import (
    ACCOUNT_TRADE_MODE_DEMO,
    ACCOUNT_TRADE_MODE_REAL,
    SafetyError,
    verify_execution_allowed,
)

_MODE_DEMO = ACCOUNT_TRADE_MODE_DEMO
_MODE_REAL = ACCOUNT_TRADE_MODE_REAL


def _config(live: LiveConfig) -> Config:
    """Minimal valid Config with the given [live] settings."""
    return Config(
        data=DataConfig(
            source="histdata",
            raw_dir="data/raw",
            symbol="XAUUSD",
            timeframe="M5",
            start="2024-01-01",
            end="2026-07-31",
        ),
        strategy=StrategyConfig(
            fractal_left=2,
            fractal_right=2,
            sr_lookback=60,
            rr_multiple=1.0,
            sl_buffer=0.01,
        ),
        trading=TradingConfig(lot=0.01, contract_size=100),
        backtest=BacktestConfig(output_dir="out/backtest"),
        live=live,
    )


def _account(trade_mode: int) -> AccountInfo:
    return AccountInfo(
        login=12345,
        server="demo-server",
        currency="USD",
        balance=10000.0,
        trade_mode=trade_mode,
    )


@pytest.mark.parametrize(
    ("mode", "enabled", "trade_mode", "expect_raise", "message_fragment"),
    [
        # Rule 1 (dry-run): never blocks — orders are never sent anyway.
        ("dry-run", False, _MODE_REAL, False, None),
        ("dry-run", False, _MODE_DEMO, False, None),
        # Happy path: demo account in demo mode.
        ("demo", False, _MODE_DEMO, False, None),
        # Rule 3 (demo mode + REAL account): refused, message names REAL.
        ("demo", False, _MODE_REAL, True, "REAL"),
        # Rule 2 (real-account opt-in): refused unless [live] enabled=true.
        ("live", False, _MODE_REAL, True, "live.enabled"),
        ("live", True, _MODE_REAL, False, None),
        # Demo accounts are always fine in live mode.
        ("live", False, _MODE_DEMO, False, None),
        ("live", True, _MODE_DEMO, False, None),
    ],
)
def test_verify_execution_allowed(mode, enabled, trade_mode, expect_raise, message_fragment):
    cfg = _config(LiveConfig(enabled=enabled, mode=mode))
    account = _account(trade_mode)
    if expect_raise:
        with pytest.raises(SafetyError) as excinfo:
            verify_execution_allowed(cfg, account)
        assert message_fragment in str(excinfo.value)
    else:
        assert verify_execution_allowed(cfg, account) is None


def test_safety_module_does_not_import_metatrader5():
    """Purity contract: safety.py never imports the Windows-only MT5 package."""
    source = Path("src/trading_bot/live/safety.py").read_text(encoding="utf-8")
    assert "import MetaTrader5" not in source
    assert "from MetaTrader5" not in source
