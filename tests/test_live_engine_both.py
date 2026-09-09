"""direction="both" live engine: SHORT dry-run E2E gate + side-aware guards.

The sell-path gate for the live both-direction build. Mirrors the golden
12-bar frame about M=150 (y = 2M - x, high<->low swapped) so the mirrored
idx-6 bar closes BELOW its support with the prior close above it — a SHORT
swing S/R setup through the REAL detection chain (detect_swings ->
support_resistance -> the direction="both" union), then through the REAL
on_setup guard stack into DryRunBroker / SimulatedBroker.

Hand-computed mirrored short golden (see PLAN.md <interfaces>):

    Swing high 101.00 at idx 2 -> mirrored swing LOW 199.00 -> support 199.00
    Swing low  100.10 at idx 4 -> mirrored swing HIGH 199.90 -> resistance
    Setup fires at idx 6 (close 198.95 < 199.00, prior close 199.30 >= 199.00)
    entry = support 199.00, sl = resistance 199.90 + 0.01 = 199.91,
    tp = 199.00 - (199.91 - 199.00) = 198.09 (exact 1:1, STRAT-03)
    market bid = mirrored close 198.95 -> risk_at_market 199.91-198.95 = 0.96,
    symmetric with the long golden MARKET_RISK 0.96.

Long-default byte-identity is pinned by the UNMODIFIED golden suite
(test_live_engine.py / test_cli_live.py) plus Test 2 here. Helpers are copied
locally — the tests dir is not a package.
"""

import json
from dataclasses import replace

import pandas as pd
import pytest

from trading_bot.broker.base import OrderRequest
from trading_bot.broker.dry_run import DryRunBroker
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

# ---------------------------------------------------------------------------
# Golden 12-bar 5-minute OHLC (identical values to test_cli_live.py / test_live
# _engine.py — copied locally).
# ---------------------------------------------------------------------------
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

# Long golden reference values (unchanged — byte-identity pin).
LONG_ENTRY = 101.00  # resistance at the setup bar (idx 6)
LONG_SL = 100.09  # support - sl_buffer
LONG_TP = 101.91  # entry + (entry - sl)
SETUP_BAR = "2021-02-01T00:30:00"  # idx 6

# Mirrored short golden reference values (M = 150).
MIRROR = 150.0
SHORT_ENTRY = 199.00  # support (mirror of the long resistance)
SHORT_SL = 199.91  # resistance + sl_buffer
SHORT_TP = 198.09  # entry - (sl - entry), exact 1:1
SHORT_MARKET_BID = 198.95  # mirrored setup-bar close
SHORT_MARKET_RISK = round(SHORT_SL - SHORT_MARKET_BID, 10)  # 0.96

# A mixed long+short frame: golden bars 0-8 (long setup at idx 6) followed by
# a crash (bars 9-11) that closes below the 100.10 support at idx 11 with the
# prior close above it — a short setup inside the same walk.
_M_OPENS = [100.00, 100.10, 100.60, 100.90, 100.50, 100.15, 100.80, 101.10,
            101.60, 101.90, 101.50, 100.60]
_M_HIGHS = [100.00, 100.50, 101.00, 100.90, 100.50, 100.70, 101.05, 101.50,
            101.85, 102.00, 101.60, 100.90]
_M_LOWS = [100.00, 100.10, 100.60, 100.50, 100.10, 100.15, 100.80, 101.10,
           101.60, 101.20, 99.50, 99.60]
_M_CLOSES = [100.00, 100.50, 101.00, 100.50, 100.10, 100.70, 101.05, 101.50,
             101.85, 101.30, 100.20, 99.95]
SHORT_BAR_2 = "2021-02-01T00:55:00"  # mixed-frame short setup (idx 11)

_DEMO = LiveConfig(enabled=False, mode="demo")  # demo account, placement allowed
_DRY = LiveConfig(enabled=False, mode="dry-run")  # committed-config default
_MAGIC = 77001


def _golden_df() -> pd.DataFrame:
    index = pd.date_range(
        "2021-02-01 00:00", periods=len(_OPENS), freq="5min", name="time"
    )
    return pd.DataFrame(
        {"open": _OPENS, "high": _HIGHS, "low": _LOWS, "close": _CLOSES},
        index=index,
    )


def _mixed_df() -> pd.DataFrame:
    index = pd.date_range(
        "2021-02-01 00:00", periods=len(_M_OPENS), freq="5min", name="time"
    )
    return pd.DataFrame(
        {"open": _M_OPENS, "high": _M_HIGHS, "low": _M_LOWS, "close": _M_CLOSES},
        index=index,
    )


def _mirror(df: pd.DataFrame, m: float = MIRROR) -> pd.DataFrame:
    """Reflect a price series about ``m``: y = 2m - x, highs become lows and
    vice versa (the short-side mirror of the golden frame)."""
    return pd.DataFrame(
        {
            "open": 2 * m - df["open"],
            "high": 2 * m - df["low"],  # swapped: the mirror of a high is a low
            "low": 2 * m - df["high"],
            "close": 2 * m - df["close"],
        },
        index=df.index,
    )


def _config(
    live: LiveConfig,
    risk: RiskConfig | None = None,
    direction: str = "long",
    rr_multiple: float = 1.0,
) -> Config:
    """Minimal valid Config; strategy.direction/rr_multiple overridable."""
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
        live=live,
        risk=risk if risk is not None else RiskConfig(),
    )
    return replace(
        cfg,
        strategy=replace(cfg.strategy, direction=direction, rr_multiple=rr_multiple),
    )


def _engine(broker, tmp_path, name, live=None, direction="long",
            rr_multiple=1.0, risk=None):
    """Build a LiveEngine + its file logger under tmp_path (logger returned so
    a DryRunBroker can share it and its order_plan lines reach the file)."""
    cfg = _config(live if live is not None else _DEMO, risk=risk,
                  direction=direction, rr_multiple=rr_multiple)
    logger = get_logger(name, str(tmp_path / f"{name}.log"))
    return LiveEngine(cfg, broker, logger), logger


def _walk(engine, dry: DryRunBroker, inner: SimulatedBroker) -> list[dict]:
    """Close every golden bar one at a time, collecting the event dicts.

    Same conventions as test_cli_live._walk: cursor rewound to 0, one poll per
    bar, advancing the INNER broker (advance is SimulatedBroker-specific).
    """
    inner._cursor = 0
    events = []
    for _ in range(len(_OPENS)):
        events.append(engine.poll_once())
        inner.advance()
    return events


# --- Test 1: SHORT dry-run E2E (the pre-deploy sell-path gate) --------------


def test_short_dry_run_e2e_places_nothing_and_logs_side(tmp_path):
    """Mirrored golden frame through direction="both" + DryRunBroker: the idx-6
    poll fires a SHORT with sell geometry (entry 199.00 / sl 199.91 /
    tp 198.09), reports ticket=0, leaves the inner ledger EMPTY, and the
    decision trail carries side=short on setup_detected, order_plan and
    order_placed (SAFE-02)."""
    inner = SimulatedBroker(rates=_mirror(_golden_df()), trade_mode=0)
    cfg = _config(_DRY, direction="both")
    name = f"both_e2e_{tmp_path.name}"
    logger = get_logger(name, str(tmp_path / f"{name}.log"))
    dry = DryRunBroker(inner, logger=logger)
    engine = LiveEngine(cfg, dry, logger)
    events = _walk(engine, dry, inner)

    placed = [e for e in events if e["event"] == "order_placed"]
    assert len(placed) == 1  # only the mirrored idx-6 bar is a setup
    short = placed[0]
    assert short["side"] == "short"
    assert short["ticket"] == 0  # DryRunBroker: placed=False, no ticket
    assert short["entry"] == pytest.approx(SHORT_ENTRY)
    assert short["sl"] == pytest.approx(SHORT_SL)
    assert short["tp"] == pytest.approx(SHORT_TP)
    # Exact 1:1 R:R identity on the short geometry (tp below the entry).
    assert short["tp"] == pytest.approx(short["entry"] - (short["sl"] - short["entry"]))

    # Phase success criterion 4: nothing reached the inner broker.
    assert len(inner._orders) == 0
    assert inner.positions("XAUUSD", _MAGIC) == []

    # SAFE-02: setup_detected + order_plan + order_placed all carry side=short.
    log_text = (tmp_path / f"{name}.log").read_text()
    assert "event=setup_detected" in log_text
    assert "event=order_plan" in log_text
    assert "event=order_placed" in log_text
    assert "side=short" in log_text
    assert "entry=199.0" in log_text
    assert "sl=199.91" in log_text and "tp=198.09" in log_text

    # Every poll result is JSON-serializable.
    for event in events:
        json.dumps(event)


# --- Test 2: long default byte-identity -------------------------------------


def test_long_default_is_byte_identical_to_the_golden_long(tmp_path):
    """The UNMIRRORED golden frame through a direction="long" (default) engine
    still produces the exact golden long order (entry 101.00 / sl 100.09 /
    tp 101.91) with side="long" — the additive side field must not move the
    long path (pinned unchanged by test_live_engine.py / test_cli_live.py)."""
    broker = SimulatedBroker(rates=_golden_df())
    engine, _ = _engine(broker, tmp_path, f"both_long_{tmp_path.name}")
    broker._cursor = 7  # ON the setup bar (idx 6)

    event = engine.poll_once()

    assert event["event"] == "order_placed"
    assert event["side"] == "long"
    assert event["entry"] == pytest.approx(LONG_ENTRY)
    assert event["sl"] == pytest.approx(LONG_SL)
    assert event["tp"] == pytest.approx(LONG_TP)
    assert event["tp"] == pytest.approx(event["entry"] + (event["entry"] - event["sl"]))
    assert len(broker._orders) == 1
    assert broker._orders[0]["side"] == "long"
    assert broker._orders[0]["entry"] == pytest.approx(LONG_ENTRY)


# --- Test 3: real sell through SimulatedBroker -------------------------------


def test_short_places_a_real_sell_at_the_bid_and_opens_the_slot(tmp_path):
    """A short setup on the mirrored frame PLACES through SimulatedBroker with
    a spread set (bid != ask): the ledger entry carries side="short", the
    position opens (the single-slot guard sees it), and the recorded fill is
    the BID, never the ask."""
    broker = SimulatedBroker(rates=_mirror(_golden_df()), trade_mode=0)
    broker._spread = 0.20  # mid 198.95 -> bid 198.85 / ask 199.05
    engine, _ = _engine(broker, tmp_path, f"both_sell_{tmp_path.name}",
                        direction="both")
    broker._cursor = 7  # ON the setup bar

    event = engine.poll_once()

    assert event["event"] == "order_placed"
    assert event["side"] == "short"
    assert event["ticket"] > 0
    bid = broker.quote("XAUUSD").bid
    ask = broker.quote("XAUUSD").ask
    assert bid != ask
    assert event["fill"] == pytest.approx(bid)  # the sell crossed the BID
    assert event["fill"] != pytest.approx(ask)
    # Ledger + slot: a real sell is recorded with its side and opens a position.
    assert broker._orders[-1]["side"] == "short"
    assert broker._orders[-1]["entry"] == pytest.approx(SHORT_ENTRY)
    assert [p.ticket for p in broker.positions("XAUUSD", _MAGIC)] == [event["ticket"]]
    # The decision log shows the bid-priced risk (sl - bid = 1.06 with spread).
    log_text = (tmp_path / f"both_sell_{tmp_path.name}.log").read_text()
    assert "event=order_placed" in log_text
    assert "side=short" in log_text


# --- Test 4: bid-priced risk ------------------------------------------------


def test_short_risk_is_priced_at_the_bid_and_refuses_a_runaway(tmp_path):
    """A short's rr is measured bid - tp over sl - bid. When the BID has moved
    against the setup (the mirror of the long anti-chase case) the trade on
    offer has decayed below min_rr and is refused reason=rr_degraded; a bid at
    or above the stop is refused reason=invalid_levels."""
    # Part A: bid 198.35 (offset -0.60 from the 198.95 setup close).
    #   rr = (198.35 - 198.09) / (199.91 - 198.35) = 0.26/1.56 = 0.167 < 0.5
    broker = SimulatedBroker(rates=_mirror(_golden_df()), trade_mode=0)
    broker._quote_offset = -0.60
    engine, _ = _engine(broker, tmp_path, f"both_rr_{tmp_path.name}",
                        direction="both", risk=RiskConfig(min_rr=0.5))
    broker._cursor = 7

    event = engine.poll_once()
    assert event["event"] == "order_skipped"
    assert event["reason"] == "rr_degraded"
    assert event["rr"] < 0.5
    assert broker._orders == []
    log_text = (tmp_path / f"both_rr_{tmp_path.name}.log").read_text()
    assert "reason=rr_degraded" in log_text
    assert "bid=198.35" in log_text  # priced at the bid, not the ask

    # Part B: bid 199.95 (offset +1.00) is AT/ABOVE the stop 199.91 -> no risk.
    broker2 = SimulatedBroker(rates=_mirror(_golden_df()), trade_mode=0)
    broker2._quote_offset = 1.00
    engine2, logger2 = _engine(broker2, tmp_path, f"both_inv_{tmp_path.name}",
                               direction="both")
    broker2._cursor = 7

    event2 = engine2.poll_once()
    assert event2["event"] == "order_skipped"
    assert event2["reason"] == "invalid_levels"
    assert broker2._orders == []
    log_text2 = (tmp_path / f"both_inv_{tmp_path.name}.log").read_text()
    assert "market is already at or above the stop" in log_text2
    assert "bid=199.95" in log_text2


# --- Test 5: levels_are_tradable side-aware ---------------------------------


def test_levels_are_tradable_is_side_aware():
    from trading_bot.live.engine import levels_are_tradable

    # Long rule (today's, unchanged): stop below the reference entry.
    assert levels_are_tradable(101.0, 100.09, 101.91, side="long") is True
    assert levels_are_tradable(101.0, 101.0, 101.91, side="long") is False  # sl == entry
    assert levels_are_tradable(101.0, 101.5, 101.91, side="long") is False  # sl above
    assert levels_are_tradable(101.0, float("nan"), 101.91, side="long") is False

    # Short rule: the stop ABOVE the reference support, the target BELOW it.
    assert levels_are_tradable(100.10, 101.01, 99.19, side="short") is True
    assert levels_are_tradable(100.10, 100.10, 99.19, side="short") is False  # sl == entry
    assert levels_are_tradable(100.10, 99.0, 99.19, side="short") is False  # sl below
    assert levels_are_tradable(100.10, 101.01, 100.10, side="short") is False  # tp == entry
    assert levels_are_tradable(100.10, 101.01, 101.0, side="short") is False  # tp above
    assert levels_are_tradable(100.10, float("nan"), 99.19, side="short") is False


# --- Test 6: union detection on a mixed long+short frame --------------------


def test_both_union_fires_the_side_each_bar_signals(tmp_path):
    """On a mixed frame with a long setup at idx 6 and a short setup at idx 11,
    direction="both" fires whichever side each bar signals — one order event
    per setup bar, each carrying its own side, and no bar produces both."""
    inner = SimulatedBroker(rates=_mixed_df(), trade_mode=0)
    cfg = _config(_DRY, direction="both")
    name = f"both_mix_{tmp_path.name}"
    logger = get_logger(name, str(tmp_path / f"{name}.log"))
    dry = DryRunBroker(inner, logger=logger)
    engine = LiveEngine(cfg, dry, logger)

    inner._cursor = 0
    events = []
    for _ in range(len(_M_OPENS) + 1):  # cover bar idx 11 too
        events.append(engine.poll_once())
        inner.advance()

    placed = [e for e in events if e["event"] == "order_placed"]
    assert len(placed) == 2, [e.get("bar", e["event"]) for e in events]
    by_side = {e["side"]: e for e in placed}
    assert set(by_side) == {"long", "short"}

    long_ev = by_side["long"]
    assert long_ev["entry"] == pytest.approx(LONG_ENTRY)
    assert long_ev["sl"] == pytest.approx(LONG_SL)
    assert long_ev["tp"] == pytest.approx(LONG_TP)

    short_ev = by_side["short"]
    # The short fires on the crash bar below the 100.10 support.
    assert short_ev["sl"] > short_ev["entry"] > short_ev["tp"]

    # No single poll can produce both sides — each order event carries one.
    for event in events:
        if event["event"] == "order_placed":
            assert event["side"] in {"long", "short"}

    # Dry-run: nothing reached the inner broker.
    assert len(inner._orders) == 0
    log_text = (tmp_path / f"{name}.log").read_text()
    assert log_text.count("event=setup_detected") == 2
    assert "side=long" in log_text and "side=short" in log_text
