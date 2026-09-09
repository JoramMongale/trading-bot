"""Tests for src/trading_bot/ai/context.py + prompts.py — what the model sees."""

import pandas as pd
import pytest

from trading_bot.ai.context import (
    atr_estimate,
    build_regime_context,
    build_trade_context,
)
from trading_bot.ai.prompts import (
    render_regime_prompt,
    render_trade_prompt,
)
from trading_bot.config import (
    BacktestConfig,
    Config,
    DataConfig,
    LiveConfig,
    RiskConfig,
    StrategyConfig,
    TradingConfig,
)
from trading_bot.strategy.levels import support_resistance
from trading_bot.strategy.swings import detect_swings

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
    df = pd.DataFrame(
        {"open": _OPENS, "high": _HIGHS, "low": _LOWS, "close": _CLOSES},
        index=index,
    )
    return support_resistance(detect_swings(df, 2, 2), 60)


def _config() -> Config:
    return Config(
        data=DataConfig(source="histdata", raw_dir="data/raw", symbol="XAUUSD",
                        timeframe="M5", start="2024-01-01", end="2026-07-31"),
        strategy=StrategyConfig(fractal_left=2, fractal_right=2, sr_lookback=60,
                                rr_multiple=1.0, sl_buffer=0.01),
        trading=TradingConfig(lot=0.01, contract_size=100),
        backtest=BacktestConfig(output_dir="output"),
        live=LiveConfig(enabled=False, mode="dry-run"),
        risk=RiskConfig(max_loss_pct_per_trade=1.0),
    )


def test_build_trade_context_fields():
    df = _golden_df()
    bar_time = df.index[6]
    # The context contract: the LAST bar of the frame is the setup bar.
    ctx = build_trade_context(df.iloc[:7], _config(), 101.00, 100.09, 101.91,
                              bar_time, balance=5000.0)
    assert ctx.entry == 101.00 and ctx.sl == 100.09 and ctx.tp == 101.91
    assert ctx.resistance == 101.00 and ctx.support == 100.10
    assert ctx.stop_distance == pytest.approx(0.91)
    assert ctx.reward_risk == pytest.approx(1.0)
    assert ctx.balance == 5000.0 and ctx.max_loss_pct == 1.0
    assert ctx.session_hour == 0
    assert ctx.bar_time == "2021-02-01 00:30:00"
    assert len(ctx.last_bars) == 7


def test_build_trade_context_empty_frame_raises():
    df = _golden_df()
    empty = df.iloc[:0]
    with pytest.raises(ValueError, match="empty frame"):
        build_trade_context(empty, _config(), 1.0, 0.9, 1.1, df.index[0])


def test_atr_estimate_is_positive_finite():
    assert 0 < atr_estimate(_golden_df()) < 100


def test_build_regime_context_resamples_to_daily():
    df = _golden_df()
    ctx = build_regime_context(df, _config(), recent_avg_r=0.1, recent_trades=5)
    assert ctx.symbol == "XAUUSD"
    assert ctx.n_days >= 1
    assert ctx.recent_avg_r == 0.1 and ctx.recent_trades == 5
    assert ctx.days and "date" in ctx.days[0]
    # A single daily bar cannot produce an up-day fraction — reported as None
    # (unknown), never NaN, so the model does not read "nan" as a number.
    assert ctx.up_days_frac is None


def test_render_trade_prompt_carries_levels_and_schema():
    df = _golden_df()
    bar_time = df.index[6]
    ctx = build_trade_context(df.iloc[:7], _config(), 101.00, 100.09, 101.91,
                              bar_time)
    text = render_trade_prompt(ctx)
    assert "resistance 101.00" in text.lower()
    assert "100.09" in text
    assert "bias" in text and "confidence" in text and "invalidation_level" in text
    assert "LONG|SHORT|NONE" in text
    # The model must be told it cannot claim live data.
    assert "Do NOT claim access to live market data" in text


def test_render_regime_prompt_carries_daily_snapshot():
    df = _golden_df()
    ctx = build_regime_context(df, _config(), recent_avg_r=-0.05, recent_trades=10)
    text = render_regime_prompt(ctx)
    assert "TRENDING|RANGING|CHOPPY" in text
    assert "tradeable" in text
    assert "recent_avg_r" not in text  # rendered value, not placeholder
    # The single daily bar leaves the up-day fraction unknown, and the prompt
    # must say so plainly rather than print "nan".
    assert "-0.050 R per trade" in text
    assert "unknown" in text


def test_prompt_template_file_overrides_builtin(tmp_path):
    (tmp_path / "trade_idea.txt").write_text("CUSTOM {symbol}", encoding="utf-8")
    df = _golden_df()
    ctx = build_trade_context(df, _config(), 101.00, 100.09, 101.91, df.index[6])
    assert render_trade_prompt(ctx, str(tmp_path)) == "CUSTOM XAUUSD"


def test_unknown_template_raises(tmp_path):
    from trading_bot.ai.prompts import load_template

    with pytest.raises(FileNotFoundError):
        load_template("missing.txt", str(tmp_path))


# ---------------------------------------------------------------------------
# News sentiment in the regime context (plan 03-04, NEWS-02) — fail-open.
# ---------------------------------------------------------------------------

def test_regime_context_sentiment_defaults_to_none():
    """No snapshot -> RegimeContext.sentiment is None (no regression)."""
    df = _golden_df()
    ctx = build_regime_context(df, _config())
    assert ctx.sentiment is None


def test_regime_context_sentiment_populated():
    df = _golden_df()
    sentiment = {
        "date": "2026-08-27 09:15:00",
        "score": -0.1,
        "articles": 10,
        "top_titles": ["Gold surges", "Gold slumps"],
    }
    ctx = build_regime_context(df, _config(), sentiment=sentiment)
    assert ctx.sentiment == sentiment


def test_render_regime_prompt_with_sentiment_shows_block():
    df = _golden_df()
    ctx = build_regime_context(
        df, _config(),
        sentiment={
            "date": "2026-08-27",
            "score": -0.1,
            "articles": 10,
            "top_titles": ["Gold slumps", "Gold surges"],
        },
    )
    text = render_regime_prompt(ctx)
    assert "NEWS SENTIMENT" in text
    assert "-0.1" in text
    assert "Articles scored 10" in text
    assert "Gold slumps; Gold surges" in text


def test_render_regime_prompt_without_sentiment_is_clean():
    """Absent snapshot renders no SENTIMENT block and never 'None'/'nan'."""
    df = _golden_df()
    ctx = build_regime_context(df, _config())
    text = render_regime_prompt(ctx)
    assert "NEWS SENTIMENT" not in text
    assert "None" not in text
    assert "nan" not in text
    assert "TRENDING|RANGING|CHOPPY" in text  # rest of the prompt intact
