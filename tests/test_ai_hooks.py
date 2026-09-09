"""Tests for the two additive AI-layer hooks (plan 03-01).

Both must be strict no-ops by default so the existing deterministic behavior is
byte-identical (pinned here), and both must do their job when given a value:
``setup_veto`` on the backtester and ``_ai_gate`` on the live engine.
"""

import pandas as pd
import pytest

from trading_bot.backtest.engine import run_backtest
from trading_bot.broker.base import OrderRequest
from trading_bot.broker.simulated import SimulatedBroker
from trading_bot.config import (
    BacktestConfig,
    Config,
    DataConfig,
    LiveConfig,
    RiskConfig,
    StrategyConfig,
    TradingConfig,
)
from trading_bot.live.engine import LiveEngine
from trading_bot.logging_utils import get_logger

_OPENS = [100.00, 100.10, 100.60, 100.90, 100.50, 100.15, 100.80,
          101.10, 101.60, 101.90, 101.80, 101.20]
_HIGHS = [100.00, 100.50, 101.00, 100.90, 100.50, 100.70, 101.05,
          101.50, 101.85, 102.05, 101.80, 101.20]
_LOWS = [100.00, 100.10, 100.60, 100.50, 100.10, 100.15, 100.80,
         101.10, 101.60, 101.90, 101.60, 100.90]
_CLOSES = [100.00, 100.50, 101.00, 100.50, 100.10, 100.70, 101.05,
           101.50, 101.85, 102.05, 101.60, 100.90]


def _golden_df() -> pd.DataFrame:
    index = pd.date_range("2021-02-01 00:00", periods=12, freq="5min", name="time")
    return pd.DataFrame(
        {"open": _OPENS, "high": _HIGHS, "low": _LOWS, "close": _CLOSES},
        index=index,
    )


def test_setup_veto_default_is_byte_identical():
    df = _golden_df()
    base = run_backtest(df)
    noop = run_backtest(df, setup_veto=lambda bar, e, s, t: None)
    assert base == noop
    assert len(base) == 1  # the golden setup arms, fills, closes


def test_setup_veto_reason_skips_the_arm():
    df = _golden_df()
    events = []

    def on_event(event):
        events.append(event)

    trades = run_backtest(
        df, on_event=on_event, setup_veto=lambda bar, e, s, t: "ai_low_confidence"
    )
    assert trades == []
    skipped = [e for e in events if e["event"] == "setup_skipped"]
    assert skipped and skipped[0]["reason"] == "ai_low_confidence"
    assert skipped[0]["entry"] == 101.00


def test_setup_veto_receives_bar_levels():
    df = _golden_df()
    seen = {}

    def veto(bar, entry, sl, tp):
        seen.update(bar=bar.name, entry=entry, sl=sl, tp=tp)
        return None

    run_backtest(df, setup_veto=veto)
    assert str(seen["bar"]) == "2021-02-01 00:30:00"
    assert seen["entry"] == pytest.approx(101.00)
    assert seen["sl"] == pytest.approx(100.09)
    assert seen["tp"] == pytest.approx(101.91)


def test_live_default_ai_gate_is_noop(tmp_path):
    """The default LiveEngine._ai_gate returns None, so on_setup proceeds to
    place — the pre-AI behavior, pinned."""
    df = _golden_df()
    broker = SimulatedBroker(rates=df, cursor=7)
    cfg = Config(
        data=DataConfig(source="histdata", raw_dir="data/raw", symbol="XAUUSD",
                        timeframe="M5", start="2024-01-01", end="2026-07-31"),
        strategy=StrategyConfig(fractal_left=2, fractal_right=2, sr_lookback=60,
                                rr_multiple=1.0, sl_buffer=0.01),
        trading=TradingConfig(lot=0.01, contract_size=100),
        backtest=BacktestConfig(output_dir="output"),
        live=LiveConfig(enabled=False, mode="demo"),
        risk=RiskConfig(),
    )
    logger = get_logger(f"hook-{tmp_path.name}", str(tmp_path / "live.log"))
    engine = LiveEngine(cfg, broker, logger)
    assert engine._ai_gate(101.00, 100.09, 101.91, df.index[6]) is None

    result = engine.on_setup(101.00, 100.09, 101.91, df.index[6])
    assert result["event"] == "order_placed"
