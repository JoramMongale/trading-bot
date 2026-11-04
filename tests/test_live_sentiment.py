"""Live-engine DXY sentiment direction override (auto-flip long/short).

Pins the [sentiment] seam in the LIVE engine: when enabled, the DXY macro
regime OVERRIDES [strategy] direction — bullish -> long only, bearish -> short
only, neutral/unavailable -> the configured direction (fail-open). Tests
monkeypatch ``news.macro.current_dxy_bullishness`` (no network) and drive the
REAL detection chain through the golden/mirrored/mixed frames from
test_live_engine_both.py. DryRunBroker is used so neither side starves the
single slot (nothing actually opens).

Properties pinned:
  1. disabled (default) -> [strategy] direction unchanged (byte-identity).
  2. bullish -> the mirrored (short-setup) frame no longer trades; the golden
     (long-setup) frame still fires long.
  3. bearish -> the golden (long-setup) frame no longer trades; the mirrored
     frame fires short.
  4. neutral -> falls back to "both" (both sides fire on the mixed frame).
  5. unavailable (None) / fetch error -> fail-open, configured direction holds.
  6. the resolution is cached for [sentiment] refresh_seconds.
"""

from dataclasses import replace

import pandas as pd
import pytest

from trading_bot.broker.dry_run import DryRunBroker
from trading_bot.broker.simulated import SimulatedBroker
from trading_bot.config import (
    BacktestConfig,
    Config,
    DataConfig,
    LiveConfig,
    SentimentConfig,
    StrategyConfig,
    TradingConfig,
)
from trading_bot.live.engine import LiveEngine
from trading_bot.logging_utils import get_logger
from trading_bot.news import macro

# Golden 12-bar 5-minute OHLC (identical to test_live_engine_both.py — copied
# locally because the tests dir is not a package).
_OPENS = [
    100.00, 100.10, 100.60, 100.90, 100.50, 100.15, 100.80, 101.10, 101.60,
    101.90, 101.80, 101.20,
]
_HIGHS = [
    100.00, 100.50, 101.00, 100.90, 100.50, 100.70, 101.05, 101.50, 101.85,
    102.05, 101.80, 101.20,
]
_LOWS = [
    100.00, 100.10, 100.60, 100.50, 100.10, 100.15, 100.80, 101.10, 101.60,
    101.90, 101.60, 100.90,
]
_CLOSES = [
    100.00, 100.50, 101.00, 100.50, 100.10, 100.70, 101.05, 101.50, 101.85,
    102.05, 101.60, 100.90,
]

LONG_ENTRY = 101.00
LONG_SL = 100.09
LONG_TP = 101.91

# Mixed long+short frame (long setup at idx 6, short setup at idx 11).
_M_OPENS = [100.00, 100.10, 100.60, 100.90, 100.50, 100.15, 100.80, 101.10,
            101.60, 101.90, 101.50, 100.60]
_M_HIGHS = [100.00, 100.50, 101.00, 100.90, 100.50, 100.70, 101.05, 101.50,
            101.85, 102.00, 101.60, 100.90]
_M_LOWS = [100.00, 100.10, 100.60, 100.50, 100.10, 100.15, 100.80, 101.10,
           101.60, 101.20, 99.50, 99.60]
_M_CLOSES = [100.00, 100.50, 101.00, 100.50, 100.10, 100.70, 101.05, 101.50,
             101.85, 101.30, 100.20, 99.95]

_DRY = LiveConfig(enabled=False, mode="dry-run")


def _golden_df() -> pd.DataFrame:
    index = pd.date_range(
        "2021-02-01 00:00", periods=len(_OPENS), freq="5min", name="time"
    )
    return pd.DataFrame(
        {"open": _OPENS, "high": _HIGHS, "low": _LOWS, "close": _CLOSES},
        index=index,
    )


def _mirror(df: pd.DataFrame, m: float = 150.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": 2 * m - df["open"],
            "high": 2 * m - df["low"],
            "low": 2 * m - df["high"],
            "close": 2 * m - df["close"],
        },
        index=df.index,
    )


def _mixed_df() -> pd.DataFrame:
    index = pd.date_range(
        "2021-02-01 00:00", periods=len(_M_OPENS), freq="5min", name="time"
    )
    return pd.DataFrame(
        {"open": _M_OPENS, "high": _M_HIGHS, "low": _M_LOWS, "close": _M_CLOSES},
        index=index,
    )


def _config(direction: str = "long", sentiment: SentimentConfig | None = None) -> Config:
    cfg = Config(
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
        backtest=BacktestConfig(output_dir="output"),
        live=_DRY,
        sentiment=sentiment if sentiment is not None else SentimentConfig(),
    )
    return replace(cfg, strategy=replace(cfg.strategy, direction=direction))


def _engine(tmp_path, name, direction="long", sentiment=None,
            refresh_seconds=3600.0):
    """Build a LiveEngine wired to a DryRunBroker over SimulatedBroker."""
    sent = sentiment if sentiment is not None else SentimentConfig()
    sent = replace(sent, refresh_seconds=refresh_seconds)
    cfg = _config(direction=direction, sentiment=sent)
    inner = SimulatedBroker(trade_mode=0)
    logger = get_logger(name, str(tmp_path / f"{name}.log"))
    dry = DryRunBroker(inner, logger=logger)
    return LiveEngine(cfg, dry, logger), dry, inner


def _placed(engine, inner, frame, n_bars):
    """Replay ``n_bars`` closed bars and return the order_placed events."""
    inner._rates = frame
    inner._cursor = 0
    events = []
    for _ in range(n_bars):
        events.append(engine.poll_once())
        inner.advance()
    return [e for e in events if e["event"] == "order_placed"]


def _bullishness(value):
    """Monkeypatch current_dxy_bullishness to return ``value`` (float or None)."""
    def _fake(cache_path=None, window=None, refresh=False):
        return value
    return _fake


# --- 1. disabled = byte-identity --------------------------------------------


def test_sentiment_disabled_keeps_config_direction(tmp_path):
    """[sentiment] disabled (the default) never overrides: a direction="both"
    engine on the golden frame still fires the long setup (side=long)."""
    engine, _, inner = _engine(tmp_path, f"sent_off_{tmp_path.name}",
                               direction="both")
    placed = _placed(engine, inner, _golden_df(), len(_OPENS))
    assert [p["side"] for p in placed] == ["long"]


# --- 2. bullish -> long only -------------------------------------------------


def test_bullish_sentiment_suppresses_the_short_mirror(tmp_path, monkeypatch):
    """A bullish regime flips direction to long: the mirrored (short-setup)
    frame now finds no long breakout and places NOTHING."""
    monkeypatch.setattr(macro, "current_dxy_bullishness", _bullishness(90.0))
    engine, _, inner = _engine(tmp_path, f"sent_bull_{tmp_path.name}",
                               direction="both",
                               sentiment=SentimentConfig(enabled=True))
    placed = _placed(engine, inner, _mirror(_golden_df()), len(_OPENS))
    assert placed == []


def test_bullish_sentiment_still_fires_long(tmp_path, monkeypatch):
    """A bullish regime on the golden (long-setup) frame fires the long with
    the golden geometry unchanged."""
    monkeypatch.setattr(macro, "current_dxy_bullishness", _bullishness(90.0))
    engine, _, inner = _engine(tmp_path, f"sent_bull2_{tmp_path.name}",
                               direction="both",
                               sentiment=SentimentConfig(enabled=True))
    placed = _placed(engine, inner, _golden_df(), len(_OPENS))
    assert [p["side"] for p in placed] == ["long"]
    assert placed[0]["entry"] == pytest.approx(LONG_ENTRY)
    assert placed[0]["sl"] == pytest.approx(LONG_SL)
    assert placed[0]["tp"] == pytest.approx(LONG_TP)


# --- 3. bearish -> short only ------------------------------------------------


def test_bearish_sentiment_suppresses_the_long(tmp_path, monkeypatch):
    """A bearish regime flips direction to short: the golden (long-setup)
    frame now finds no short breakout and places NOTHING."""
    monkeypatch.setattr(macro, "current_dxy_bullishness", _bullishness(10.0))
    engine, _, inner = _engine(tmp_path, f"sent_bear_{tmp_path.name}",
                               direction="both",
                               sentiment=SentimentConfig(enabled=True))
    placed = _placed(engine, inner, _golden_df(), len(_OPENS))
    assert placed == []


def test_bearish_sentiment_fires_the_short_mirror(tmp_path, monkeypatch):
    """A bearish regime on the mirrored frame fires the short."""
    monkeypatch.setattr(macro, "current_dxy_bullishness", _bullishness(10.0))
    engine, _, inner = _engine(tmp_path, f"sent_bear2_{tmp_path.name}",
                               direction="both",
                               sentiment=SentimentConfig(enabled=True))
    placed = _placed(engine, inner, _mirror(_golden_df()), len(_OPENS))
    assert [p["side"] for p in placed] == ["short"]
    assert placed[0]["sl"] > placed[0]["entry"] > placed[0]["tp"]


# --- 4. neutral -> fall back to "both" ---------------------------------------


def test_neutral_sentiment_falls_back_to_both(tmp_path, monkeypatch):
    """A neutral regime (50) returns no override, so direction="both" fires
    both sides on the mixed frame."""
    monkeypatch.setattr(macro, "current_dxy_bullishness", _bullishness(50.0))
    engine, _, inner = _engine(tmp_path, f"sent_neutral_{tmp_path.name}",
                               direction="both",
                               sentiment=SentimentConfig(enabled=True))
    placed = _placed(engine, inner, _mixed_df(), len(_M_OPENS) + 1)
    assert {p["side"] for p in placed} == {"long", "short"}


# --- 5. unavailable / error -> fail-open ------------------------------------


def test_unavailable_sentiment_fails_open(tmp_path, monkeypatch):
    """current_dxy_bullishness -> None leaves the configured direction
    untouched (the golden long still fires under direction="both")."""
    monkeypatch.setattr(macro, "current_dxy_bullishness", _bullishness(None))
    engine, _, inner = _engine(tmp_path, f"sent_none_{tmp_path.name}",
                               direction="both",
                               sentiment=SentimentConfig(enabled=True))
    placed = _placed(engine, inner, _golden_df(), len(_OPENS))
    assert [p["side"] for p in placed] == ["long"]


def test_sentiment_fetch_error_fails_open(tmp_path, monkeypatch):
    """A fetch exception logs sentiment_unavailable and falls back — the trade
    still proceeds (sentiment is a hint, not a safety device)."""
    def _raise(cache_path=None, window=None, refresh=False):
        raise RuntimeError("yahoo down")

    monkeypatch.setattr(macro, "current_dxy_bullishness", _raise)
    engine, _, inner = _engine(tmp_path, f"sent_err_{tmp_path.name}",
                               direction="both",
                               sentiment=SentimentConfig(enabled=True))
    placed = _placed(engine, inner, _golden_df(), len(_OPENS))
    assert [p["side"] for p in placed] == ["long"]
    log_text = (tmp_path / f"sent_err_{tmp_path.name}.log").read_text()
    assert "event=sentiment_unavailable" in log_text


# --- 6. caching --------------------------------------------------------------


def test_sentiment_resolution_is_cached(tmp_path, monkeypatch):
    """Two resolutions within refresh_seconds hit current_dxy_bullishness once."""
    calls = {"n": 0}

    def _counting(cache_path=None, window=None, refresh=False):
        calls["n"] += 1
        return 90.0

    monkeypatch.setattr(macro, "current_dxy_bullishness", _counting)
    engine, _, _ = _engine(tmp_path, f"sent_cache_{tmp_path.name}",
                           direction="long",
                           sentiment=SentimentConfig(enabled=True),
                           refresh_seconds=3600.0)
    assert engine._sentiment_direction() == "long"
    assert engine._sentiment_direction() == "long"
    assert calls["n"] == 1
