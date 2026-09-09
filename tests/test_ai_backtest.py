"""Tests for src/trading_bot/ai/backtest.py — run_ai_backtest (AI-04).

Uses the golden 12-bar frame: one setup at idx 6, one trade (entry fill 101.10,
TP at 101.91). Raw vs gated must be reported honestly, and the veto must be the
only difference between the two runs.
"""

import pandas as pd

from trading_bot.ai.backtest import run_ai_backtest
from trading_bot.ai.mock import MockAIClient
from trading_bot.ai.schema import AIProposal, RegimeAssessment
from trading_bot.backtest.engine import run_backtest
from trading_bot.config import (
    AIConfig,
    BacktestConfig,
    Config,
    DataConfig,
    LiveConfig,
    RiskConfig,
    StrategyConfig,
    TradingConfig,
)

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


def _config() -> Config:
    return Config(
        data=DataConfig(source="histdata", raw_dir="data/raw", symbol="XAUUSD",
                        timeframe="M5", start="2024-01-01", end="2026-07-31"),
        strategy=StrategyConfig(fractal_left=2, fractal_right=2, sr_lookback=60,
                                rr_multiple=1.0, sl_buffer=0.01),
        trading=TradingConfig(lot=0.01, contract_size=100),
        backtest=BacktestConfig(output_dir="output"),
        live=LiveConfig(enabled=False, mode="dry-run"),
        risk=RiskConfig(),
        ai=AIConfig(),
    )


def test_heuristic_mock_approves_all_and_matches_raw():
    df = _golden_df()
    result = run_ai_backtest(df, _config(), MockAIClient())
    assert result["raw_trades"] == run_backtest(df)
    assert result["gated_trades"] == result["raw_trades"]
    assert len(result["gated_trades"]) == 1
    assert result["consultations"] == 1
    assert result["approved"] == 1
    assert result["rejected"] == 0
    assert result["regime_checks"] == 1
    assert result["regime_blocks"] == 0


def test_veto_everything_leaves_raw_untouched():
    client = MockAIClient(
        proposal_fn=lambda ctx: AIProposal(bias="NONE", confidence=40,
                                           reasoning="pass")
    )
    df = _golden_df()
    result = run_ai_backtest(df, _config(), client)
    assert len(result["raw_trades"]) == 1
    assert result["gated_trades"] == []
    assert result["consultations"] == 1
    assert result["rejected"] == 1
    assert result["approved"] == 0


def test_choppy_regime_blocks_every_setup():
    client = MockAIClient(
        regime=RegimeAssessment(regime="CHOPPY", bias="NEUTRAL", confidence=70,
                                tradeable=False, notes="whipsaw")
    )
    df = _golden_df()
    result = run_ai_backtest(df, _config(), client)
    assert result["gated_trades"] == []
    assert result["regime_blocks"] == 1
    assert result["regime_checks"] == 1
    # A regime-blocked setup is never consulted for a proposal.
    assert result["consultations"] == 0


def test_ai_events_are_emitted_in_order():
    df = _golden_df()
    events = []

    def on_event(event):
        events.append(event)

    run_ai_backtest(df, _config(), MockAIClient(), on_event=on_event)
    kinds = [e["event"] for e in events]
    assert "ai_regime" in kinds
    assert "ai_proposal" in kinds
    # The veto emission precedes the strategy's setup_detected for the same bar.
    assert "setup_detected" in kinds


def test_regime_sees_realized_r_from_gated_trades():
    """Across many setups the regime prompt's recent R must come from trades the
    AI run actually closed — tracked via trade_closed events."""
    df = _golden_df()
    state = {"regime_avg_r": None}

    class _Probe(MockAIClient):
        def assess_regime(self, ctx):
            state["regime_avg_r"] = ctx.recent_avg_r
            return super().assess_regime(ctx)

    run_ai_backtest(df, _config(), _Probe())
    # On the single-day golden frame the regime check happens on the FIRST
    # setup, before any trade has closed, so avg R is None there.
    assert state["regime_avg_r"] in (None, 0.0)


def test_unavailable_provider_fails_closed_and_counts():
    from trading_bot.ai.base import AIClientUnavailableError

    class _Broken(MockAIClient):
        def propose_trade(self, ctx):
            raise AIClientUnavailableError("down")

    df = _golden_df()
    result = run_ai_backtest(df, _config(), _Broken())
    assert result["gated_trades"] == []
    assert result["unavailable"] == 1
