"""Tests for src/trading_bot/ai/engine.py — AIEngine, the AI-gated live engine."""

import pandas as pd
import pytest

from trading_bot.ai.base import AIClientUnavailableError
from trading_bot.ai.engine import AIEngine
from trading_bot.ai.mock import MockAIClient
from trading_bot.ai.schema import AIProposal, RegimeAssessment
from trading_bot.broker.simulated import SimulatedBroker
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
from trading_bot.logging_utils import get_logger

_OPENS = [100.00, 100.10, 100.60, 100.90, 100.50, 100.15, 100.80,
          101.10, 101.60, 101.90, 101.80, 101.20]
_HIGHS = [100.00, 100.50, 101.00, 100.90, 100.50, 100.70, 101.05,
          101.50, 101.85, 102.05, 101.80, 101.20]
_LOWS = [100.00, 100.10, 100.60, 100.50, 100.10, 100.15, 100.80,
         101.10, 101.60, 101.90, 101.60, 100.90]
_CLOSES = [100.00, 100.50, 101.00, 100.50, 100.10, 100.70, 101.05,
           101.50, 101.85, 102.05, 101.60, 100.90]

ENTRY, SL, TP = 101.00, 100.09, 101.91


def _golden_df() -> pd.DataFrame:
    index = pd.date_range("2021-02-01 00:00", periods=12, freq="5min", name="time")
    return pd.DataFrame(
        {"open": _OPENS, "high": _HIGHS, "low": _LOWS, "close": _CLOSES},
        index=index,
    )


def _config(ai: AIConfig) -> Config:
    return Config(
        data=DataConfig(source="histdata", raw_dir="data/raw", symbol="XAUUSD",
                        timeframe="M5", start="2024-01-01", end="2026-07-31"),
        strategy=StrategyConfig(fractal_left=2, fractal_right=2, sr_lookback=60,
                                rr_multiple=1.0, sl_buffer=0.01),
        trading=TradingConfig(lot=0.01, contract_size=100),
        backtest=BacktestConfig(output_dir="output"),
        live=LiveConfig(enabled=False, mode="demo"),
        risk=RiskConfig(),
        ai=ai,
    )


def _make_engine(broker, tmp_path, ai_client, ai: AIConfig | None = None):
    cfg = _config(ai if ai is not None else AIConfig(enabled=True))
    logger = get_logger(f"ai-engine-{tmp_path.name}", str(tmp_path / "live.log"))
    return AIEngine(cfg, broker, logger, ai_client)


def _walk_to_setup(broker, engine, warm_cursor: int = 5) -> list[dict]:
    events = []
    broker._cursor = warm_cursor
    while broker._cursor <= 7:
        events.append(engine.poll_once())
        broker.advance()
    return events


def test_approved_proposal_proceeds_to_placement(tmp_path):
    broker = SimulatedBroker(rates=_golden_df())
    engine = _make_engine(broker, tmp_path, MockAIClient())
    events = _walk_to_setup(broker, engine)

    assert events[-1]["event"] == "order_placed"
    assert events[-1]["entry"] == pytest.approx(ENTRY)
    assert events[-1]["sl"] == pytest.approx(SL)
    assert events[-1]["tp"] == pytest.approx(TP)

    log_text = (tmp_path / "live.log").read_text()
    assert "event=ai_proposal" in log_text
    assert "verdict=APPROVED" in log_text


def test_rejected_proposal_skips_placement(tmp_path):
    client = MockAIClient(
        proposal_fn=lambda ctx: AIProposal(bias="NONE", confidence=40,
                                           reasoning="pass")
    )
    broker = SimulatedBroker(rates=_golden_df())
    engine = _make_engine(broker, tmp_path, client)
    events = _walk_to_setup(broker, engine)

    assert events[-1]["event"] == "order_skipped"
    assert events[-1]["reason"] == "ai_rejected"
    log_text = (tmp_path / "live.log").read_text()
    assert "verdict=REJECTED" in log_text and "reason=no_idea" in log_text


def test_low_confidence_blocks(tmp_path):
    client = MockAIClient(
        proposal_fn=lambda ctx: AIProposal(bias="LONG", confidence=30,
                                           reasoning="weak")
    )
    broker = SimulatedBroker(rates=_golden_df())
    engine = _make_engine(broker, tmp_path, client)
    events = _walk_to_setup(broker, engine)
    assert events[-1] == {"event": "order_skipped", "reason": "ai_rejected",
                          "detail": "low_confidence"}


def test_choppy_regime_blocks_the_day(tmp_path):
    client = MockAIClient(
        regime=RegimeAssessment(regime="CHOPPY", bias="NEUTRAL", confidence=80,
                                tradeable=False, notes="whipsaw")
    )
    broker = SimulatedBroker(rates=_golden_df())
    engine = _make_engine(broker, tmp_path, client)
    events = _walk_to_setup(broker, engine)

    assert events[-1]["event"] == "order_skipped"
    assert events[-1]["reason"] == "ai_regime_block"
    log_text = (tmp_path / "live.log").read_text()
    assert "event=ai_regime" in log_text and "regime=CHOPPY" in log_text
    # The regime was assessed once for the day, not per setup.
    assert log_text.count("event=ai_regime ") == 1


def test_block_when_choppy_off_allows_setup(tmp_path):
    ai = AIConfig(enabled=True, block_when_choppy=False)
    client = MockAIClient(
        regime=RegimeAssessment(regime="CHOPPY", bias="NEUTRAL", confidence=80,
                                tradeable=False, notes="whipsaw")
    )
    broker = SimulatedBroker(rates=_golden_df())
    engine = _make_engine(broker, tmp_path, client, ai)
    events = _walk_to_setup(broker, engine)
    assert events[-1]["event"] == "order_placed"


def test_regime_check_runs_once_per_day(tmp_path):
    """A second poll on the same UTC day must NOT re-assess the regime."""
    client = MockAIClient()
    broker = SimulatedBroker(rates=_golden_df())
    engine = _make_engine(broker, tmp_path, client)
    _walk_to_setup(broker, engine)
    # Walk a few more bars on the same day (cursor 8..10).
    for _ in range(3):
        engine.poll_once()
        broker.advance()
    log_text = (tmp_path / "live.log").read_text()
    assert log_text.count("event=ai_regime ") == 1


def test_proposal_transport_failure_fails_closed(tmp_path):
    class _Broken(MockAIClient):
        def propose_trade(self, ctx):
            raise AIClientUnavailableError("provider down")

    broker = SimulatedBroker(rates=_golden_df())
    engine = _make_engine(broker, tmp_path, _Broken())
    events = _walk_to_setup(broker, engine)
    assert events[-1]["event"] == "order_skipped"
    assert events[-1]["reason"] == "ai_unavailable"


def test_regime_transport_failure_fails_open(tmp_path):
    """A broken regime read must not stop the day (a filter, not a safety gate)."""

    class _RegimeDown(MockAIClient):
        def assess_regime(self, ctx):
            raise AIClientUnavailableError("provider down")

    broker = SimulatedBroker(rates=_golden_df())
    engine = _make_engine(broker, tmp_path, _RegimeDown())
    events = _walk_to_setup(broker, engine)
    assert events[-1]["event"] == "order_placed"
    log_text = (tmp_path / "live.log").read_text()
    assert "event=ai_regime_failed" in log_text


def test_ai_engine_gates_regardless_of_enabled_flag(tmp_path):
    """``[ai] enabled`` is the CLI build-level opt-in (choose AIEngine vs plain
    LiveEngine). Once you ARE running an AIEngine it gates every setup; the
    ``regime_check_daily`` flag is the only in-engine switch, and it only
    controls the daily regime call."""
    ai = AIConfig(enabled=False, regime_check_daily=False)
    client = MockAIClient()
    broker = SimulatedBroker(rates=_golden_df())
    engine = _make_engine(broker, tmp_path, client, ai)
    events = _walk_to_setup(broker, engine)
    assert events[-1]["event"] == "order_placed"
    log_text = (tmp_path / "live.log").read_text()
    assert "event=ai_proposal" in log_text  # gate still runs for AIEngine
    assert "event=ai_regime" not in log_text  # regime check switched off


# ---------------------------------------------------------------------------
# News sentiment snapshot -> regime context (plan 03-04) — fail-open.
# ---------------------------------------------------------------------------

def _regime_capturing_engine(tmp_path, ai, news=None):
    """Engine whose regime read records the RegimeContext the model received."""
    from dataclasses import replace

    cfg = _config(ai)
    if news is not None:
        cfg = replace(cfg, news=news)
    seen = {}

    class _Capture(MockAIClient):
        def assess_regime(self, ctx):
            seen["ctx"] = ctx
            return RegimeAssessment(
                regime="TRENDING", bias="BULLISH", confidence=70,
                tradeable=True, notes="captured",
            )

    broker = SimulatedBroker(rates=_golden_df())
    logger = get_logger(f"ai-sent-{tmp_path.name}", str(tmp_path / "live.log"))
    engine = AIEngine(cfg, broker, logger, _Capture())
    broker._cursor = 6
    engine.poll_once()  # fires the once-per-day regime read
    return seen, broker, engine


def test_regime_check_feeds_sentiment_snapshot(tmp_path):
    from dataclasses import replace

    from trading_bot.config import NewsConfig

    snapshot = tmp_path / "news_sentiment.json"
    snapshot.write_text(
        '{"date": "2026-08-27", "score": -0.1, "articles": 10, '
        '"top_titles": ["Gold slumps", "Gold surges"]}',
        encoding="utf-8",
    )
    news = replace(
        NewsConfig(), enabled=True, snapshot_file=str(snapshot)
    )
    seen, _, _ = _regime_capturing_engine(tmp_path, AIConfig(enabled=True), news)

    assert seen["ctx"].sentiment == {
        "date": "2026-08-27",
        "score": -0.1,
        "articles": 10,
        "top_titles": ["Gold slumps", "Gold surges"],
    }


def test_regime_check_missing_snapshot_fails_open(tmp_path):
    from dataclasses import replace

    from trading_bot.config import NewsConfig

    news = replace(
        NewsConfig(), enabled=True, snapshot_file=str(tmp_path / "missing.json")
    )
    seen, _, engine = _regime_capturing_engine(tmp_path, AIConfig(enabled=True), news)

    # No snapshot on disk -> sentiment None, regime still assessed.
    assert seen["ctx"].sentiment is None


def test_regime_check_corrupt_snapshot_fails_open(tmp_path):
    from dataclasses import replace

    from trading_bot.config import NewsConfig

    snapshot = tmp_path / "news_sentiment.json"
    snapshot.write_text("{not valid json !!!", encoding="utf-8")
    news = replace(NewsConfig(), enabled=True, snapshot_file=str(snapshot))
    seen, _, engine = _regime_capturing_engine(tmp_path, AIConfig(enabled=True), news)

    assert seen["ctx"].sentiment is None  # day proceeds without news
    log_text = (tmp_path / "live.log").read_text()
    assert "event=ai_regime_sentiment_unreadable" in log_text
    assert "event=ai_regime " in log_text  # the regime read itself still ran
