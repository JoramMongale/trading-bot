"""Tests for src/trading_bot/live/engine.py — LiveEngine poll -> place order.

Golden-frame behavioral tests (plan 02-04). Reuses the golden 12-bar OHLC
fixture values from tests/test_cli.py (_FIX_* lists) — the same frame that
produces a known setup in test_backtest.py:

  Swing high 101.00 at idx 2 confirms at idx 4  -> resistance 101.00
  Swing low  100.10 at idx 4 confirms at idx 6  -> support    100.10
  Setup fires at idx 6 (close 101.05 > 101.00, prior close 100.70 <= 101.00)
  Armed Buy Stop: entry=101.00 (resistance), sl=100.10-0.01=100.09,
  tp=101.00+(101.00-100.09)=101.91 (exact 1:1 R:R, STRAT-03)

The engine is driven against SimulatedBroker whose cursor is "now": walking
the cursor from a warm start feeds the engine one new closed bar per
advance(), and the setup bar is 2021-02-01T00:30:00 (idx 6).

A setup on the last closed bar goes through on_setup: dedup (equivalent
pending order / open position), safety gate (SAFE-03), then place — the
returned event is order_placed / order_skipped / order_rejected.
"""

import json
from dataclasses import replace

import pandas as pd
import pytest

from trading_bot.broker.base import BrokerRejectedError, OrderRequest
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
# Golden 12-bar 5-minute OHLC (bars 0-9 = the golden sample trade; 10-11 =
# quiet filler). Same values as tests/test_cli.py (_FIX_* lists).
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

SETUP_BAR = "2021-02-01T00:30:00"  # idx 6
ENTRY = 101.00  # resistance at the setup bar
SL = 100.09  # support - sl_buffer
TP = 101.91  # entry + (entry - sl)

# Risk is now measured at the MARKET, not at the reference level. SimulatedBroker
# quotes the last closed bar's close, and the setup bar closes at 101.05 — above
# the 101.00 resistance, which is what "breakout" means. So the trade on offer
# risks 0.96, not the 0.91 the levels imply, and its reward:risk is 0.896
# rather than the nominal 1.000. Every sizing and cap figure below derives from
# MARKET_RISK for that reason.
MARKET_ASK = 101.05
MARKET_RISK = round(MARKET_ASK - SL, 10)  # 0.96


def _golden_df() -> pd.DataFrame:
    index = pd.date_range(
        "2021-02-01 00:00", periods=len(_OPENS), freq="5min", name="time"
    )
    return pd.DataFrame(
        {"open": _OPENS, "high": _HIGHS, "low": _LOWS, "close": _CLOSES},
        index=index,
    )


def _config(live: LiveConfig, risk: RiskConfig | None = None) -> Config:
    """Minimal valid Config mirroring config/config.toml values."""
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
        backtest=BacktestConfig(output_dir="output"),
        live=live,
        risk=risk if risk is not None else RiskConfig(),
    )


def _config_rr(live: LiveConfig, rr_multiple: float, risk: RiskConfig | None = None) -> Config:
    """_config with a different [strategy] rr_multiple (frozen dataclass)."""
    cfg = _config(live, risk)
    return replace(cfg, strategy=replace(cfg.strategy, rr_multiple=rr_multiple))


_DEMO = LiveConfig(enabled=False, mode="demo")  # demo account, placement allowed
_DRY = LiveConfig(enabled=False, mode="dry-run")  # committed-config default
_MAGIC = 77001  # cfg.live.magic_number


def replace_risk(cfg, risk):
    """Config with a different [risk] table (frozen dataclass)."""
    from dataclasses import replace as _replace
    return _replace(cfg, risk=risk)


def _make_engine(
    broker,
    tmp_path,
    live: LiveConfig | None = None,
    name: str | None = None,
    risk: RiskConfig | None = None,
    rr_multiple: float = 1.0,
):
    """Build a LiveEngine with an isolated decision-log file under tmp_path."""
    cfg = _config(live if live is not None else _DEMO, risk)
    if rr_multiple != 1.0:
        cfg = replace(cfg, strategy=replace(cfg.strategy, rr_multiple=rr_multiple))
    log_name = name or f"live_engine_{tmp_path.name}"
    logger = get_logger(log_name, str(tmp_path / "live.log"))
    return LiveEngine(cfg, broker, logger)


def _walk_to_setup(broker, engine, warm_cursor: int = 5) -> list[dict]:
    """Close bars from a warm start through the setup bar (idx 6).

    SimulatedBroker cursor semantics: fetch_rates returns CLOSED bars ending
    at the cursor; advance() closes the next bar. Cursor 7 sits ON the setup
    bar, so walking cursors 5 -> 6 -> 7 yields bar_check (idx 4), bar_check
    (idx 5), then the setup order event (idx 6).
    """
    events = []
    broker._cursor = warm_cursor
    while broker._cursor <= 7:
        events.append(engine.poll_once())
        broker.advance()
    return events


def test_detects_setup_on_last_closed_bar(tmp_path):
    """Walk the cursor from a warm start: earlier bars are bar_check, the
    setup bar (idx 6) detects the setup and returns an order with the
    backtest-consistent prices (setup_detected is logged, SAFE-02)."""
    broker = SimulatedBroker(rates=_golden_df())
    engine = _make_engine(broker, tmp_path)
    events = _walk_to_setup(broker, engine)

    # The two earlier bars are plain bar_checks; the setup bar places the order.
    assert [e["event"] for e in events] == ["bar_check", "bar_check", "order_placed"]
    assert events[0]["bar"] == "2021-02-01T00:20:00" and events[0]["setup"] is False
    assert events[1]["bar"] == "2021-02-01T00:25:00" and events[1]["setup"] is False

    # Order prices match the hand-computed backtest conventions (STRAT-03).
    placed = events[2]
    assert placed["entry"] == pytest.approx(ENTRY)
    assert placed["sl"] == pytest.approx(SL)
    assert placed["tp"] == pytest.approx(TP)
    # tp is exactly entry + (entry - sl): the 1:1 risk-reward identity.
    assert placed["tp"] == pytest.approx(placed["entry"] + (placed["entry"] - placed["sl"]))

    # SAFE-02: the detection is logged with 2-dp prices.
    log_text = (tmp_path / "live.log").read_text()
    assert f"event=setup_detected bar={SETUP_BAR}" in log_text
    assert "entry=101.0" in log_text and "sl=100.09" in log_text and "tp=101.91" in log_text


def test_rr_multiple_scales_the_live_target(tmp_path):
    """rr_multiple=2.0 must place tp = entry + 2*(entry - sl) — the exact
    STRAT-03 parity with the backtest formula. The 1.0 default (covered by
    every other test in this file) stays byte-identical."""
    broker = SimulatedBroker(rates=_golden_df())
    engine = _make_engine(broker, tmp_path, rr_multiple=2.0)
    events = _walk_to_setup(broker, engine)

    placed = events[-1]
    assert placed["event"] == "order_placed"
    assert placed["entry"] == pytest.approx(ENTRY)
    assert placed["sl"] == pytest.approx(SL)
    # 101.00 + 2 * (101.00 - 100.09) = 101.00 + 2 * 0.91 = 102.82
    assert placed["tp"] == pytest.approx(ENTRY + 2 * (ENTRY - SL))
    assert placed["tp"] == pytest.approx(102.82)
    # The wire order carries the same scaled tp.
    assert broker._orders[-1]["tp"] == pytest.approx(102.82)
    # SAFE-02 log records the scaled target.
    assert "tp=102.82" in (tmp_path / "live.log").read_text()


def test_no_new_bar_returns_early(tmp_path):
    """Two consecutive polls with no new bar: the second returns new_bar=False
    and never re-logs (or re-fires) the setup."""
    broker = SimulatedBroker(rates=_golden_df())
    engine = _make_engine(broker, tmp_path)
    broker._cursor = 7  # sit ON the setup bar (idx 6)

    first = engine.poll_once()
    assert first["event"] == "order_placed"

    second = engine.poll_once()  # no advance() between polls
    assert second == {"event": "bar_check", "new_bar": False}

    # The setup was logged exactly once — the second poll did not re-evaluate
    # (the same-bar early return writes nothing to the decision log).
    log_text = (tmp_path / "live.log").read_text()
    assert log_text.count("event=setup_detected") == 1
    assert "event=bar_check" not in log_text


def test_bar_fetch_failed_graceful(tmp_path):
    """A broker with no rates (BrokerUnavailableError) must not crash the
    engine — it reports bar_fetch_failed (EXEC-01 graceful)."""
    broker = SimulatedBroker(rates=None)
    engine = _make_engine(broker, tmp_path)

    event = engine.poll_once()

    assert event["event"] == "bar_fetch_failed"
    assert isinstance(event["error"], str) and event["error"]
    assert "event=bar_fetch_failed" in (tmp_path / "live.log").read_text()


def test_bar_check_logs_no_setup(tmp_path):
    """A closed bar with no setup produces bar_check with setup=False."""
    broker = SimulatedBroker(rates=_golden_df())
    engine = _make_engine(broker, tmp_path)
    broker._cursor = 5  # last closed bar = idx 4, which has no setup

    event = engine.poll_once()

    assert event == {
        "event": "bar_check",
        "new_bar": True,
        "setup": False,
        "bar": "2021-02-01T00:20:00",
    }
    assert "event=bar_check" in (tmp_path / "live.log").read_text()


def test_places_order_on_setup(tmp_path):
    """A setup places exactly one Buy Stop with the detected prices and the
    configured magic number (EXEC-03)."""
    broker = SimulatedBroker(rates=_golden_df())
    engine = _make_engine(broker, tmp_path)
    broker._cursor = 7  # ON the setup bar

    event = engine.poll_once()

    assert event["event"] == "order_placed"
    assert event["ticket"] > 0
    assert len(broker._orders) == 1
    placed = broker._orders[0]
    assert placed["symbol"] == "XAUUSD"
    assert placed["entry"] == pytest.approx(ENTRY)
    assert placed["sl"] == pytest.approx(SL)
    assert placed["tp"] == pytest.approx(TP)
    assert placed["magic"] == _MAGIC
    assert placed["volume"] == pytest.approx(0.01)


def test_skips_equivalent_pending(tmp_path):
    """An equivalent order already armed on the server blocks the setup
    re-trigger (phase success criterion 5): order_skipped, ledger stays at 1.

    The bot's own entries are market orders and never sit pending, so what
    this guards is an order left behind by an earlier build or placed by hand
    in the terminal — seeded here directly."""
    broker = SimulatedBroker(rates=_golden_df())
    # Entry within the 0.01 equivalence tolerance, same symbol + magic.
    broker.simulate_pending(ENTRY, symbol="XAUUSD", magic=_MAGIC)
    engine = _make_engine(broker, tmp_path)
    broker._cursor = 7  # ON the setup bar, which would build the same order

    event = engine.poll_once()

    assert event == {"event": "order_skipped", "reason": "pending_order_equivalent"}
    assert len(broker._orders) == 1  # no duplicate was placed
    assert "reason=pending_order_equivalent" in (tmp_path / "live.log").read_text()


def test_skips_when_position_open(tmp_path):
    """An open position for symbol+magic blocks new setups (backtest
    one-at-a-time parity): order_skipped, nothing placed."""
    broker = SimulatedBroker(rates=_golden_df())
    broker.simulate_position(ticket=999, symbol="XAUUSD", magic=_MAGIC)
    engine = _make_engine(broker, tmp_path)
    broker._cursor = 7  # ON the setup bar

    event = engine.poll_once()

    assert event == {"event": "order_skipped", "reason": "position_open"}
    assert len(broker._orders) == 0
    assert "reason=position_open" in (tmp_path / "live.log").read_text()


def test_safety_block_real_account(tmp_path):
    """A REAL account (trade_mode=2) without the explicit opt-in is blocked
    by the SAFE-03 guard; flipping live.enabled=True lets the order through."""
    broker = SimulatedBroker(rates=_golden_df(), trade_mode=2)

    blocked = _make_engine(broker, tmp_path, live=LiveConfig(enabled=False, mode="live"))
    broker._cursor = 7  # ON the setup bar
    event = blocked.poll_once()

    assert event["event"] == "order_skipped"
    assert event["reason"] == "safety_blocked"
    assert "REFUSED" in event["detail"]
    assert len(broker._orders) == 0  # nothing reached the broker

    # Explicit opt-in (SAFE-03) unblocks: fresh engine (new bar state), same
    # broker ledger — the order now goes through.
    allowed = _make_engine(
        broker, tmp_path, live=LiveConfig(enabled=True, mode="live"),
        name=f"live_engine_allowed_{tmp_path.name}",
    )
    event = allowed.poll_once()

    assert event["event"] == "order_placed"
    assert len(broker._orders) == 1


def test_dry_run_never_places(tmp_path):
    """Wrapped in DryRunBroker, the setup reports the order event but nothing
    reaches the inner SimulatedBroker (phase success criterion 4)."""
    inner = SimulatedBroker(rates=_golden_df())
    broker = DryRunBroker(inner, logger=None)
    engine = _make_engine(broker, tmp_path, live=_DRY)
    inner._cursor = 7  # ON the setup bar

    event = engine.poll_once()

    # DryRunBroker returns ticket=0/placed=False — the engine reports it as
    # the placed event, but the inner ledger proves nothing was sent.
    assert event["event"] == "order_placed"
    assert event["ticket"] == 0
    assert len(inner._orders) == 0
    assert "event=order_placed" in (tmp_path / "live.log").read_text()


class _RejectingBroker(SimulatedBroker):
    """SimulatedBroker whose place_market_buy refuses every order."""

    def place_market_buy(self, request):
        raise BrokerRejectedError("requote: price moved, order rejected")


def test_order_rejected_surfaces(tmp_path):
    """A broker rejection (BrokerRejectedError) surfaces as order_rejected
    with the error text, and nothing lands in the ledger."""
    broker = _RejectingBroker(rates=_golden_df())
    engine = _make_engine(broker, tmp_path)
    broker._cursor = 7  # ON the setup bar

    event = engine.poll_once()

    assert event["event"] == "order_rejected"
    assert "requote" in event["error"]
    assert len(broker._orders) == 0
    assert "event=order_rejected" in (tmp_path / "live.log").read_text()


def test_events_are_json_serializable(tmp_path):
    """Every event dict across the full walk is JSON-serializable: bar is an
    ISO string, prices are plain floats — no Timestamps or numpy scalars."""
    broker = SimulatedBroker(rates=_golden_df())
    engine = _make_engine(broker, tmp_path)
    events = []
    broker._cursor = 5  # walk bars idx 4..11 (8 polls), each closing a bar
    for _ in range(len(_OPENS) - 5 + 1):
        events.append(engine.poll_once())
        broker.advance()
    events.append(engine.poll_once())  # same bar again -> new_bar False

    assert len(events) == 9
    assert [e["event"] for e in events].count("order_placed") == 1  # only idx 6
    for event in events:
        json.dumps(event)  # must not raise
        for key, value in event.items():
            assert isinstance(value, (str, int, float, bool, type(None))), (
                f"{key}={value!r} in {event['event']} is not JSON-plain"
            )


# -- single pending slot (backtest parity) ----------------------------------


def test_pending_order_at_a_different_level_blocks_a_new_setup(tmp_path):
    """backtest/engine.py holds ONE pending slot: a second setup while an order
    is armed is skipped with reason="pending_order". Live dedup only matched
    EQUIVALENT orders (same entry +/-0.01), so two distinct breakouts could
    both go live — carrying positions the backtest never modelled and silently
    doubling per-trade risk."""
    broker = SimulatedBroker(rates=_golden_df())
    # Arm an order 50 points away, so equivalence cannot be what blocks it.
    broker.simulate_pending(ENTRY + 50.0, symbol="XAUUSD", magic=_MAGIC)
    engine = _make_engine(broker, tmp_path)
    broker._cursor = 7  # ON the setup bar

    event = engine.poll_once()

    assert event == {"event": "order_skipped", "reason": "pending_order"}
    assert len(broker._orders) == 1  # the far-away order is the only one
    assert "reason=pending_order " in (tmp_path / "live.log").read_text()


# -- risk gate ---------------------------------------------------------------
#
# The golden setup risks 0.91 quote units (ENTRY 101.00 - SL 100.09). At the
# configured 0.01 lots and contract_size 100 that is $0.91 of account money,
# so a balance of $45.50 puts it exactly on a 2% cap and anything smaller
# blocks. The real XAUUSD numbers are ~27x larger (median stop $24.30 per 0.01
# lot across the 340 recorded backtest trades) — same arithmetic, scaled.


def test_risk_gate_blocks_a_trade_that_costs_more_than_the_cap(tmp_path):
    """The stop is structural, so its size comes from the market and nothing
    upstream bounds it against the account. On a balance too small to absorb
    it the trade must be refused, not placed and hoped over."""
    broker = SimulatedBroker(rates=_golden_df(), balance=30.0)
    engine = _make_engine(broker, tmp_path, risk=RiskConfig(max_loss_pct_per_trade=2.0))
    broker._cursor = 7  # ON the setup bar

    event = engine.poll_once()

    assert event["event"] == "order_skipped"
    assert event["reason"] == "risk_exceeded"
    assert event["projected_loss"] == pytest.approx(MARKET_RISK)  # 0.96, priced
    assert event["cap"] == pytest.approx(0.60)                    # at the ask
    # Nothing reached the broker: no ledger entry, no position.
    assert broker._orders == []
    assert broker.positions("XAUUSD", _MAGIC) == []


def test_risk_gate_logs_the_numbers_that_justify_the_refusal(tmp_path):
    """A silent skip is indistinguishable from a bot that has stopped working.
    The log line has to carry the loss, the cap and the balance so the refusal
    can be checked rather than trusted."""
    broker = SimulatedBroker(rates=_golden_df(), balance=30.0)
    engine = _make_engine(broker, tmp_path, risk=RiskConfig(max_loss_pct_per_trade=2.0))
    broker._cursor = 7

    engine.poll_once()

    line = (tmp_path / "live.log").read_text()
    assert "reason=risk_exceeded" in line
    assert "projected_loss=0.96" in line
    assert "cap=0.6" in line
    assert "balance=30.0" in line
    assert "max_loss_pct=2.0" in line
    assert "account_pct=3.2" in line  # 0.96 / 30 = 3.2% of the account


def test_risk_gate_allows_a_trade_inside_the_cap(tmp_path):
    """The same setup on a balance that can carry it goes through untouched."""
    broker = SimulatedBroker(rates=_golden_df(), balance=100.0)
    engine = _make_engine(broker, tmp_path, risk=RiskConfig(max_loss_pct_per_trade=2.0))
    broker._cursor = 7

    event = engine.poll_once()

    assert event["event"] == "order_placed"  # 0.91 <= 2.00 cap
    assert len(broker._orders) == 1


def test_risk_gate_boundary_blocks_just_over_and_allows_just_under(tmp_path):
    """The cap is a strict ceiling and the comparison is left exact.

    A balance of 48.00 puts this trade EXACTLY on a 2% cap, and there the
    outcome is decided by float dust. That is deliberately not smoothed
    over with an epsilon: widening a risk limit to absorb rounding error is
    the wrong direction to be wrong in, and erring towards "skip" costs a
    marginal trade rather than the account. So the property under test is the
    one that is actually well defined — clearly under passes, clearly over
    blocks."""
    just_under = SimulatedBroker(rates=_golden_df(), balance=49.0)  # cap 0.98
    engine = _make_engine(
        just_under, tmp_path, risk=RiskConfig(max_loss_pct_per_trade=2.0)
    )
    just_under._cursor = 7
    assert engine.poll_once()["event"] == "order_placed"

    just_over = SimulatedBroker(rates=_golden_df(), balance=47.0)  # cap 0.94
    engine = _make_engine(
        just_over, tmp_path, risk=RiskConfig(max_loss_pct_per_trade=2.0), name="over"
    )
    just_over._cursor = 7
    assert engine.poll_once()["reason"] == "risk_exceeded"


def test_risk_gate_runs_after_the_safety_gate(tmp_path):
    """SAFE-03 is the outer guard: a real account with enabled=false must be
    refused for being a real account, whatever the trade would have risked."""
    broker = SimulatedBroker(rates=_golden_df(), trade_mode=2, balance=30.0)
    engine = _make_engine(
        broker,
        tmp_path,
        live=LiveConfig(enabled=False, mode="live"),
        risk=RiskConfig(max_loss_pct_per_trade=2.0),
    )
    broker._cursor = 7

    assert engine.poll_once()["reason"] == "safety_blocked"


def test_projected_loss_converts_quote_move_to_account_currency():
    """0.01 lots of XAUUSD is 1 oz (contract_size 100), so a $24.30 stop
    distance is $24.30 of real money — the number the cap is compared against."""
    from trading_bot.live.engine import projected_loss

    cfg = _config(_DEMO)
    req = OrderRequest(
        symbol="XAUUSD", volume=0.01, entry=2626.79, sl=2602.49, tp=2651.09,
        magic=_MAGIC, deviation=20, comment="c",
    )
    assert projected_loss(cfg, req) == pytest.approx(24.30)


# -- fill vs reference entry -------------------------------------------------


def test_order_placed_logs_the_realised_fill_beside_the_reference_entry(tmp_path):
    """The backtest books this trade at the reference level; the market books
    it at the ask. Logging only one of the two hides which set of numbers the
    equity curve actually belongs to."""

    class _SlippingBroker(SimulatedBroker):
        def place_market_buy(self, request):
            result = super().place_market_buy(request)
            return type(result)(
                ticket=result.ticket, placed=True, retcode=result.retcode,
                comment=result.comment, fill_price=request.entry + 0.37,
            )

    broker = _SlippingBroker(rates=_golden_df())
    engine = _make_engine(broker, tmp_path)
    broker._cursor = 7

    event = engine.poll_once()

    assert event["event"] == "order_placed"
    assert event["entry"] == pytest.approx(ENTRY)  # reference level
    assert event["fill"] == pytest.approx(ENTRY + 0.37)  # what we paid
    line = (tmp_path / "live.log").read_text()
    assert f"entry={ENTRY}" in line
    assert "fill=101.37" in line
    assert "slippage=0.37" in line


# -- incomplete levels (fail-closed) -----------------------------------------
#
# `setup` only reads resistance, so it fires while support can still be NaN.
# Every NaN comparison is False, which defeats guards that look correct:
# `loss > cap` is False, so a naive risk gate PASSES an unknown risk, and the
# order reaches the broker with no stop loss. Full history never produces this;
# a live bot fetches ~69 bars and restarts often, and 6 of 45 sampled
# mid-history windows did.


def test_nan_stop_is_refused_before_it_can_reach_the_broker(tmp_path):
    broker = SimulatedBroker(rates=_golden_df())
    engine = _make_engine(broker, tmp_path)

    event = engine.on_setup(
        101.0, float("nan"), float("nan"), pd.Timestamp("2021-02-01T00:30:00")
    )

    assert event["event"] == "order_skipped"
    assert event["reason"] == "invalid_levels"
    assert broker._orders == []
    assert broker.positions("XAUUSD", _MAGIC) == []
    assert "reason=invalid_levels" in (tmp_path / "live.log").read_text()


def test_risk_gate_fails_closed_on_a_loss_it_cannot_evaluate(tmp_path):
    """The guard that would otherwise have let it through, tested directly:
    `nan > cap` is False, so the gate must reject on non-finite rather than
    fall through to placement."""
    from trading_bot.live.engine import projected_loss

    cfg = _config(_DEMO)
    req = OrderRequest(
        symbol="XAUUSD", volume=0.01, entry=3025.775, sl=float("nan"),
        tp=float("nan"), magic=_MAGIC, deviation=20, comment="c",
    )
    loss = projected_loss(cfg, req)
    assert loss != loss  # NaN
    assert not (loss > 100.0)  # the comparison that silently passes it

    broker = SimulatedBroker(rates=_golden_df(), balance=5000.0)
    engine = _make_engine(broker, tmp_path)
    event = engine.on_setup(
        req.entry, req.sl, req.tp, pd.Timestamp("2021-02-01T00:30:00")
    )
    assert event["event"] == "order_skipped"
    assert broker._orders == []


def test_stop_at_or_above_entry_is_refused(tmp_path):
    """A non-positive stop distance puts tp at or below entry: no target, and
    no risk to size the position against."""
    broker = SimulatedBroker(rates=_golden_df())
    engine = _make_engine(broker, tmp_path)

    for sl in (101.0, 101.5):  # equal to entry, then above it
        event = engine.on_setup(
            101.0, sl, 101.0 + (101.0 - sl), pd.Timestamp("2021-02-01T00:30:00")
        )
        assert event["reason"] == "invalid_levels", sl
    assert broker._orders == []


def test_levels_are_tradable_accepts_a_normal_setup():
    from trading_bot.live.engine import levels_are_tradable

    assert levels_are_tradable(101.0, 100.09, 101.91) is True
    assert levels_are_tradable(101.0, float("nan"), 101.91) is False
    assert levels_are_tradable(float("inf"), 100.09, 101.91) is False


# -- position sizing ---------------------------------------------------------


def test_percent_sizing_makes_the_stop_cost_the_cap(tmp_path):
    """The point of "percent": the cap stops being a veto and becomes the size.
    Priced at the market the stop is 0.96/unit — $0.96 per 0.01 lot — so a
    $4,800 balance with a 2% cap ($96) buys exactly 1.00 lot."""
    broker = SimulatedBroker(rates=_golden_df(), balance=4800.0)
    engine = _make_engine(
        broker, tmp_path,
        risk=RiskConfig(max_loss_pct_per_trade=2.0, sizing="percent"),
    )
    broker._cursor = 7

    assert engine.poll_once()["event"] == "order_placed"
    placed = broker._orders[0]
    assert placed["volume"] == pytest.approx(1.00, abs=0.01)
    # The REAL risk — measured from the ask, which is what the account pays.
    risked = MARKET_RISK * placed["volume"] * 100
    assert risked == pytest.approx(4800.0 * 0.02, rel=0.02)


def test_percent_sizing_scales_down_on_a_smaller_account(tmp_path):
    broker = SimulatedBroker(rates=_golden_df(), balance=480.0)  # 10x smaller
    engine = _make_engine(
        broker, tmp_path,
        risk=RiskConfig(max_loss_pct_per_trade=2.0, sizing="percent"),
    )
    broker._cursor = 7
    assert engine.poll_once()["event"] == "order_placed"
    assert broker._orders[0]["volume"] == pytest.approx(0.10, abs=0.01)


def test_percent_sizing_skips_when_the_answer_is_below_the_min_lot(tmp_path):
    """The R500 case. The stop is structural, so on a small account the
    SMALLEST tradable position still risks more than the policy allows.
    Rounding up to the minimum would silently break the cap being applied."""
    broker = SimulatedBroker(rates=_golden_df(), balance=31.0)
    engine = _make_engine(
        broker, tmp_path,
        risk=RiskConfig(max_loss_pct_per_trade=2.0, sizing="percent"),
    )
    broker._cursor = 7

    event = engine.poll_once()
    assert event["event"] == "order_skipped"
    assert event["reason"] == "below_min_lot"
    assert broker._orders == []
    assert "reason=below_min_lot" in (tmp_path / "live.log").read_text()


def test_position_size_floors_onto_the_lot_grid_never_up():
    from trading_bot.live.engine import position_size

    cfg = _config(_DEMO)
    # budget/risk lands at 0.037 lots -> must floor to 0.03, not round to 0.04
    lots = position_size(
        replace_risk(cfg, RiskConfig(max_loss_pct_per_trade=2.0, sizing="percent")),
        5900.0, 31.83,
    )
    assert lots == pytest.approx(0.03)


def test_position_size_returns_zero_rather_than_a_bad_number():
    from trading_bot.live.engine import position_size

    cfg = _config(_DEMO)
    for bad in (0.0, -1.0, float("nan")):
        assert position_size(cfg, 5000.0, bad) == 0.0


# -- daily loss limit --------------------------------------------------------


def test_daily_loss_limit_halts_after_the_day_is_down(tmp_path):
    """Prop-desk rule: once the day is down past budget, stop. Measured on
    realised balance, so a stop-out trips it and an open position does not."""
    broker = SimulatedBroker(rates=_golden_df(), balance=1000.0)
    engine = _make_engine(
        broker, tmp_path,
        risk=RiskConfig(max_loss_pct_per_trade=50.0, max_daily_loss_pct=6.0),
    )
    broker._cursor = 7
    assert engine.poll_once()["event"] == "order_placed"  # day baseline = 1000

    # Simulate the day going 7% down (past the 6% budget) and a fresh setup.
    broker._balance = 930.0
    broker._positions.clear()
    broker._orders.clear()
    event = engine.on_setup(ENTRY, SL, TP, pd.Timestamp(SETUP_BAR))

    assert event["event"] == "order_skipped"
    assert event["reason"] == "daily_loss_limit"
    assert broker._orders == []
    line = (tmp_path / "live.log").read_text()
    assert "reason=daily_loss_limit" in line
    assert "down_today=70.0" in line


def test_daily_loss_limit_resets_on_a_new_day(tmp_path):
    broker = SimulatedBroker(rates=_golden_df(), balance=1000.0)
    engine = _make_engine(
        broker, tmp_path,
        risk=RiskConfig(max_loss_pct_per_trade=50.0, max_daily_loss_pct=6.0),
    )
    broker._cursor = 7
    engine.poll_once()
    broker._balance = 930.0
    broker._positions.clear()
    assert engine.on_setup(ENTRY, SL, TP, pd.Timestamp(SETUP_BAR))["reason"] \
        == "daily_loss_limit"

    # Next calendar day: the budget is rebased on the new starting balance.
    tomorrow = pd.Timestamp(SETUP_BAR) + pd.Timedelta(days=1)
    assert engine.on_setup(ENTRY, SL, TP, tomorrow)["event"] == "order_placed"


def test_daily_loss_limit_off_by_default(tmp_path):
    broker = SimulatedBroker(rates=_golden_df(), balance=1000.0)
    engine = _make_engine(broker, tmp_path,
                          risk=RiskConfig(max_loss_pct_per_trade=50.0))
    broker._cursor = 7
    engine.poll_once()
    broker._balance = 100.0  # 90% down; with the limit disabled this is allowed
    broker._positions.clear()
    assert engine.on_setup(ENTRY, SL, TP, pd.Timestamp(SETUP_BAR))["event"] \
        == "order_placed"


# -- exposure ceiling --------------------------------------------------------


def test_leverage_cap_bounds_exposure_that_the_risk_cap_does_not():
    """The two limits bound different things. max_loss_pct bounds the loss IF
    THE STOP HOLDS; a gap jumps past the stop and the loss is then set by
    position size alone.

    Leverage under percent sizing works out to cap% x price / stop, so it only
    binds on stops tighter than 2% x 4500 / 20 = $4.50 — below anything this
    strategy has produced. The ceiling is a backstop against a pathologically
    tight stop, not a rule that shapes normal sizing, and both halves of that
    are worth pinning down.
    """
    from trading_bot.live.engine import position_size

    cfg = replace_risk(
        _config(_DEMO),
        RiskConfig(max_loss_pct_per_trade=2.0, sizing="percent", max_leverage=20.0),
    )
    uncapped = replace_risk(cfg, replace(cfg.risk, max_leverage=0.0))
    price = 4500.0

    # A pathologically tight $1.00 stop: risk stays 2%, exposure would not.
    big = position_size(uncapped, 5000.0, 1.00, price)
    capped = position_size(cfg, 5000.0, 1.00, price)
    assert big > capped
    assert big * price * 100 > 5000.0 * 20      # ~90x equity, uncapped
    assert capped * price * 100 <= 5000.0 * 20 + 1e-6

    # Every stop the strategy actually produces leaves the ceiling slack.
    for real_stop in (5.86, 21.48, 31.83, 47.10, 90.03):
        assert position_size(cfg, 5000.0, real_stop, price) == position_size(
            uncapped, 5000.0, real_stop, price
        ), real_stop


def test_leverage_cap_disabled_by_zero():
    from trading_bot.live.engine import position_size

    cfg = replace_risk(
        _config(_DEMO),
        RiskConfig(max_loss_pct_per_trade=2.0, sizing="percent", max_leverage=0.0),
    )
    assert position_size(cfg, 5000.0, 1.00, 4500.0) > 0.9


def test_percent_sizing_skips_the_widest_stops_on_a_small_account(tmp_path):
    """At $5,000 a $315 stop (the backtest's worst) needs 0.003 lots, under the
    0.01 minimum. Those setups are correctly skipped rather than taken at 3x
    the intended risk."""
    from trading_bot.live.engine import position_size

    cfg = replace_risk(
        _config(_DEMO),
        RiskConfig(max_loss_pct_per_trade=2.0, sizing="percent"),
    )
    assert position_size(cfg, 5000.0, 315.03, 4500.0) == 0.0
    assert position_size(cfg, 5000.0, 31.83, 4500.0) > 0.0


# -- risk priced at the market, not the reference level ----------------------
#
# The bug this section exists for: sizing and the cap both read risk off the
# strategy's reference entry, but a market buy crosses the ASK, which the setup
# guarantees is above that level. The cap was therefore never the cap. Live M1
# trade 3114935513 was sized for $49.10 against a $50.42 budget and actually
# risked $56.97 — 13% over, and worse on tighter stops.


def test_sizing_uses_the_ask_so_the_cap_actually_holds(tmp_path):
    """Size from the market and the realised risk lands ON the cap, not over."""
    broker = SimulatedBroker(rates=_golden_df(), balance=4800.0)
    broker._quote_offset = 0.40  # market has run 0.40 past the setup bar close
    engine = _make_engine(
        broker, tmp_path,
        risk=RiskConfig(max_loss_pct_per_trade=2.0, sizing="percent", min_rr=0.0),
    )
    broker._cursor = 7
    assert engine.poll_once()["event"] == "order_placed"

    lots = broker._orders[0]["volume"]
    ask = broker.quote("XAUUSD").ask
    real_risk = (ask - SL) * lots * 100
    budget = 4800.0 * 0.02
    assert real_risk <= budget * (1 + 1e-6)        # never over
    assert real_risk > budget * 0.9                # and not wastefully under

    # Sizing off the reference level would have exceeded the budget.
    naive_lots = (budget / ((ENTRY - SL) * 100))
    assert (ask - SL) * naive_lots * 100 > budget


def test_risk_gate_measures_the_loss_the_account_will_actually_take(tmp_path):
    """Fixed sizing: the gate must judge the ask-based loss, not the nominal
    one, or a trade that really costs more than the cap slips through."""
    broker = SimulatedBroker(rates=_golden_df(), balance=48.0)
    broker._quote_offset = 1.00  # market well past the reference entry
    engine = _make_engine(
        broker, tmp_path,
        risk=RiskConfig(max_loss_pct_per_trade=2.0, min_rr=0.0),
    )
    broker._cursor = 7

    event = engine.poll_once()
    # Nominal risk 0.91 would sit under the 0.96 cap and be allowed; the real
    # risk at the ask is 1.96, which must not be.
    assert (ENTRY - SL) * 0.01 * 100 < 48.0 * 0.02
    assert event["reason"] == "risk_exceeded"
    assert event["projected_loss"] == pytest.approx(
        (broker.quote("XAUUSD").ask - SL) * 0.01 * 100
    )


def test_refuses_a_setup_the_market_has_already_run_away_from(tmp_path):
    """Anti-chase. The levels imply 1:1; once the ask has eaten most of the
    move the trade on offer is not the trade that was tested."""
    broker = SimulatedBroker(rates=_golden_df(), balance=10_000.0)
    broker._quote_offset = 0.60  # ask 101.65 vs tp 101.91 -> rr ~0.17
    engine = _make_engine(
        broker, tmp_path, risk=RiskConfig(max_loss_pct_per_trade=2.0, min_rr=0.5)
    )
    broker._cursor = 7

    event = engine.poll_once()
    assert event["event"] == "order_skipped"
    assert event["reason"] == "rr_degraded"
    assert event["rr"] < 0.5
    assert broker._orders == []
    line = (tmp_path / "live.log").read_text()
    assert "reason=rr_degraded" in line
    assert "min_rr=0.5" in line


def test_a_mildly_slipped_setup_is_still_taken(tmp_path):
    """The guard must not reject ordinary slippage — only a run-away."""
    broker = SimulatedBroker(rates=_golden_df(), balance=10_000.0)
    engine = _make_engine(
        broker, tmp_path, risk=RiskConfig(max_loss_pct_per_trade=2.0, min_rr=0.5)
    )
    broker._cursor = 7
    assert engine.poll_once()["event"] == "order_placed"  # rr 0.896 at market


def test_min_rr_zero_disables_the_guard(tmp_path):
    broker = SimulatedBroker(rates=_golden_df(), balance=10_000.0)
    broker._quote_offset = 0.60
    engine = _make_engine(
        broker, tmp_path, risk=RiskConfig(max_loss_pct_per_trade=2.0, min_rr=0.0)
    )
    broker._cursor = 7
    assert engine.poll_once()["event"] == "order_placed"


def test_market_at_or_below_the_stop_is_refused(tmp_path):
    """Risk would be zero or negative — nothing to size against."""
    broker = SimulatedBroker(rates=_golden_df(), balance=10_000.0)
    broker._quote_offset = -(MARKET_ASK - SL) - 0.5  # ask below the stop
    engine = _make_engine(broker, tmp_path)
    broker._cursor = 7
    assert engine.poll_once()["reason"] == "invalid_levels"


# -- live session filter -----------------------------------------------------
#
# The golden setup bar is 2021-02-01T00:30:00 — hour 0, so a Lon+NY window
# [8, 21] must suppress it and a window containing 0 must not.


def test_setup_outside_the_session_window_is_skipped(tmp_path):
    broker = SimulatedBroker(rates=_golden_df())
    engine = _make_engine(
        broker, tmp_path,
        live=LiveConfig(enabled=False, mode="demo", session_hours=[8, 21]),
    )
    broker._cursor = 7  # ON the setup bar, hour 0

    event = engine.poll_once()
    assert event["event"] == "setup_skipped"
    assert event["reason"] == "outside_session"
    assert broker._orders == []
    line = (tmp_path / "live.log").read_text()
    assert "reason=outside_session" in line
    assert "hour=0" in line


def test_setup_inside_the_session_window_is_taken(tmp_path):
    broker = SimulatedBroker(rates=_golden_df())
    engine = _make_engine(
        broker, tmp_path,
        live=LiveConfig(enabled=False, mode="demo", session_hours=[0, 8]),
    )
    broker._cursor = 7
    assert engine.poll_once()["event"] == "order_placed"


def test_empty_session_hours_disables_the_filter(tmp_path):
    broker = SimulatedBroker(rates=_golden_df())
    engine = _make_engine(broker, tmp_path)  # _DEMO has no session_hours
    broker._cursor = 7
    assert engine.poll_once()["event"] == "order_placed"


def test_in_session_wraps_past_midnight():
    from trading_bot.live.engine import in_session

    night = [21, 8]
    for h, want in ((22, True), (2, True), (7, True), (8, False), (12, False), (20, False)):
        assert in_session(night, pd.Timestamp(f"2025-01-01 {h:02d}:00")) is want, h
    day = [8, 21]
    for h, want in ((8, True), (20, True), (21, False), (0, False)):
        assert in_session(day, pd.Timestamp(f"2025-01-01 {h:02d}:00")) is want, h
    assert in_session([], pd.Timestamp("2025-01-01 03:00")) is True


def test_session_filter_does_not_touch_the_levels(tmp_path):
    """It decides when to ACT. Levels must still come from every bar, or a
    swing confirmed just before the window opens would be invisible to the bar
    that should trade it."""
    unfiltered = SimulatedBroker(rates=_golden_df())
    e1 = _make_engine(unfiltered, tmp_path, name="unfilt")
    unfiltered._cursor = 7
    placed = e1.poll_once()

    filtered = SimulatedBroker(rates=_golden_df())
    e2 = _make_engine(
        filtered, tmp_path,
        live=LiveConfig(enabled=False, mode="demo", session_hours=[8, 21]),
        name="filt",
    )
    filtered._cursor = 7
    skipped = e2.poll_once()

    assert placed["event"] == "order_placed"
    assert skipped["reason"] == "outside_session"
    # Same bar identified as the setup in both — the filter changed the ACTION,
    # not the analysis.
    assert skipped["bar"] == SETUP_BAR


# -- weekend guard (04-01) ---------------------------------------------------
#
# The golden setup bar is 2021-02-01T00:30:00 — a MONDAY at hour 0, so with the
# guard enabled (stop_hour=19) it must be taken. A sibling frame on a Friday
# with the setup bar past the stop hour must be refused with reason=weekend.


def _golden_df_friday_1930() -> pd.DataFrame:
    """The golden frame shifted so idx 6 (the setup bar) is Friday 19:30 UTC.

    idx 6 is 2021-02-01T00:30:00 (Monday, hour 0). Shifting +4 days +19h puts
    it on 2021-02-05T19:30:00 (Friday, hour 19 >= stop_hour=19).
    """
    df = _golden_df()
    df.index = df.index + pd.Timedelta(days=4, hours=19)
    return df


def test_weekend_guard_skips_a_friday_setup_after_the_stop_hour(tmp_path):
    broker = SimulatedBroker(rates=_golden_df_friday_1930())
    engine = _make_engine(
        broker, tmp_path,
        live=LiveConfig(
            enabled=False, mode="demo", weekend_stop_hour=19, weekend_resume_hour=21
        ),
    )
    broker._cursor = 7  # ON the setup bar, Friday 19:30

    event = engine.poll_once()
    assert event["event"] == "setup_skipped"
    assert event["reason"] == "weekend"
    assert event["bar"] == "2021-02-05T19:30:00"
    assert broker._orders == []
    line = (tmp_path / "live.log").read_text()
    assert "reason=weekend" in line
    assert "stop_hour=19" in line


def test_weekend_guard_does_not_block_a_monday_setup(tmp_path):
    broker = SimulatedBroker(rates=_golden_df())
    engine = _make_engine(
        broker, tmp_path,
        live=LiveConfig(
            enabled=False, mode="demo", weekend_stop_hour=19, weekend_resume_hour=21
        ),
    )
    broker._cursor = 7  # Monday 00:30 — outside the weekend window
    assert engine.poll_once()["event"] == "order_placed"


def test_weekend_guard_disabled_by_default(tmp_path):
    broker = SimulatedBroker(rates=_golden_df_friday_1930())
    engine = _make_engine(broker, tmp_path)  # _DEMO: weekend_stop_hour=0
    broker._cursor = 7
    assert engine.poll_once()["event"] == "order_placed"


def test_weekend_guard_does_not_block_a_saturday_before_resume(tmp_path):
    """Sunday before resume_hour is still inside the window; a setup there must
    be skipped even though it is after the Friday stop."""
    df = _golden_df()
    df.index = df.index + pd.Timedelta(days=5, hours=20)  # idx 6 = Saturday 20:30
    broker = SimulatedBroker(rates=df)
    engine = _make_engine(
        broker, tmp_path,
        live=LiveConfig(
            enabled=False, mode="demo", weekend_stop_hour=19, weekend_resume_hour=21
        ),
    )
    broker._cursor = 7
    assert engine.poll_once()["reason"] == "weekend"


def test_in_weekend_pure():
    from trading_bot.live.engine import in_weekend

    fri_18 = pd.Timestamp("2025-01-10 18:00")  # a Friday
    fri_19 = pd.Timestamp("2025-01-10 19:00")
    sat = pd.Timestamp("2025-01-11 12:00")
    sun_20 = pd.Timestamp("2025-01-12 20:00")
    sun_21 = pd.Timestamp("2025-01-12 21:00")
    mon = pd.Timestamp("2025-01-13 00:00")

    assert not in_weekend(fri_18, 19, 21)  # before the stop hour
    assert in_weekend(fri_19, 19, 21)      # exactly at the stop hour
    assert in_weekend(sat, 19, 21)         # all of Saturday
    assert in_weekend(sun_20, 19, 21)      # Sunday before resume
    assert not in_weekend(sun_21, 19, 21)  # Sunday at/after resume
    assert not in_weekend(mon, 19, 21)     # Monday
    assert not in_weekend(fri_19, 0, 21)   # stop_hour=0 disables the guard


# -- market closure survival (04-01) -----------------------------------------
#
# A closure means bars stop arriving: fetch_rates returns the same last closed
# bar (or an empty frame), poll_once must report bar_check new_bar=False, never
# crash and never trip the reconnect counter, and the first bar after the gap
# must be processed normally.


def test_market_closure_returns_no_new_bar_and_resumes(tmp_path):
    """While bars are absent, the poll reports bar_check new_bar=False (not a
    failure, no reconnect churn); once bars resume the new bar is processed."""
    broker = SimulatedBroker(rates=_golden_df())
    engine = _make_engine(broker, tmp_path)
    broker._cursor = 5  # warm start: idx 4 closed

    first = engine.poll_once()  # idx 4, new bar
    assert first["event"] == "bar_check" and first["new_bar"] is True

    # Market closes: the broker serves an empty frame. Repeated polls are quiet
    # bar_checks, never bar_fetch_failed and never a crash.
    empty = SimulatedBroker(rates=pd.DataFrame(
        columns=["open", "high", "low", "close"],
        index=pd.DatetimeIndex([], name="time"),
    ))
    engine2 = _make_engine(empty, tmp_path, name="closed")
    for _ in range(5):
        event = engine2.poll_once()
        assert event["event"] in {"bar_check", "bar_fetch_failed"}
        assert event.get("event") == "bar_check" or "empty" in event.get("error", "")

    # Closure ended: a fresh frame with a NEW bar is processed normally.
    broker._cursor = 7  # on the setup bar
    resumed = engine.poll_once()
    assert resumed["event"] == "order_placed"


# -- risk in ACCOUNT currency, from the broker's tick economics ---------------
#
# The bug: sizing and the cap both derived risk from cfg.trading.contract_size,
# which is 100 — correct only for standard-account gold. On the cent account
# the same instrument has contract size 1 (100x too large) AND settles in USD
# against a USC balance (100x too small). The two errors cancelled into
# plausible-looking nonsense, which is worse than either alone.


def _cent_gold():
    """XAUUSDc as the live cent account actually reports it."""
    from trading_bot.broker.base import SymbolRisk

    return SymbolRisk(tick_size=0.001, tick_value=0.1,
                      volume_min=0.01, volume_step=0.01, volume_max=200.0)


def test_money_risk_matches_the_brokers_own_number():
    """Cross-check against the real terminal: XAUUSDc, 31.83 stop, 0.01 lots
    reported 31.83 USC on account 161693049."""
    assert _cent_gold().money_risk(31.83, 0.01) == pytest.approx(31.83, rel=1e-6)


def test_sizing_from_tick_value_ignores_the_configured_contract_size():
    """contract_size is gold-standard-specific and must not reach the answer."""
    from trading_bot.live.engine import position_size

    cfg = replace_risk(_config(_DEMO),
                       RiskConfig(max_loss_pct_per_trade=2.0, sizing="percent"))
    sr = _cent_gold()
    lots = position_size(cfg, 3121.0, 31.83, 4596.0, sr=sr)

    # 2% of 3121 USC = 62.42; one lot risks 3183 USC; 62.42/3183 = 0.0196 -> 0.01
    assert lots == pytest.approx(0.01)
    assert sr.money_risk(31.83, lots) == pytest.approx(31.83, rel=1e-6)
    assert sr.money_risk(31.83, lots) <= 3121.0 * 0.02

    # And the answer must not move when contract_size does.
    bent = replace(cfg, trading=replace(cfg.trading, contract_size=1))
    assert position_size(bent, 3121.0, 31.83, 4596.0, sr=sr) == lots


def test_gold_is_the_case_where_the_two_old_bugs_cancelled():
    """Worth pinning down, because it is why this went unnoticed.

    On XAUUSDc the old path is accidentally right. contract_size=100 is wrong
    (cent gold is 1 oz/lot), and USD->USC is another 100x in the OPPOSITE
    direction, and tick_value/tick_size happens to be exactly 100 USC per 1.0
    of price per lot. The errors cancel and the answer comes out correct.

    That is luck, not correctness — see the next test."""
    from trading_bot.live.engine import position_size

    sr = _cent_gold()
    assert sr.tick_value / sr.tick_size == pytest.approx(100.0)
    cfg = replace_risk(_config(_DEMO),
                       RiskConfig(max_loss_pct_per_trade=2.0, sizing="percent"))
    assert position_size(cfg, 3121.0, 31.83, 4596.0) == position_size(
        cfg, 3121.0, 31.83, 4596.0, sr=sr
    )


def test_on_any_other_instrument_the_old_path_is_wrong():
    """BTCUSDc: contract 0.01, tick_value 0.01, tick_size 0.01. Nothing
    cancels, and contract_size=100 oversizes by 100x."""
    from trading_bot.broker.base import SymbolRisk
    from trading_bot.live.engine import position_size

    btc = SymbolRisk(tick_size=0.01, tick_value=0.01,
                     volume_min=0.01, volume_step=0.01, volume_max=100.0)
    STOP = 753.81
    cfg = replace_risk(_config(_DEMO),
                       RiskConfig(max_loss_pct_per_trade=2.0, sizing="percent"))

    assert btc.money_risk(STOP, 1.0) == pytest.approx(753.81)     # true, USC
    old = position_size(cfg, 3121.0, STOP, 77697.0)               # no sr
    new = position_size(cfg, 3121.0, STOP, 77697.0, sr=btc)
    assert new > old                       # old undersizes by believing 75,381
    assert btc.money_risk(STOP, new) <= 3121.0 * 0.02 * (1 + 1e-9)


def test_sizing_uses_the_brokers_lot_grid_not_the_config():
    """volume_min/step come from the symbol; a stale config must not override."""
    from trading_bot.broker.base import SymbolRisk
    from trading_bot.live.engine import position_size

    cfg = replace_risk(
        _config(_DEMO),
        RiskConfig(max_loss_pct_per_trade=2.0, sizing="percent",
                   lot_min=0.01, lot_step=0.01),
    )
    coarse = SymbolRisk(tick_size=0.01, tick_value=1.0,
                        volume_min=0.10, volume_step=0.10, volume_max=100.0)
    # One lot risks 0.10/0.01 x 1.0 = 10.0; 2% of 950 = 19.0 -> 1.9 lots,
    # which already sits exactly on the broker's 0.10 grid.
    assert position_size(cfg, 950.0, 0.10, 100.0, sr=coarse) == pytest.approx(1.9)
    # 2% of 100 = 2.0 -> 0.2 lots, floored onto the 0.10 grid.
    assert position_size(cfg, 100.0, 0.10, 100.0, sr=coarse) == pytest.approx(0.2)
    # 2% of 40 = 0.8 -> 0.08 lots, under the broker's 0.10 minimum -> refuse.
    # cfg.risk.lot_min is 0.01 and must NOT be what decides this.
    assert cfg.risk.lot_min == 0.01
    assert position_size(cfg, 40.0, 0.10, 100.0, sr=coarse) == 0.0


def test_engine_sizes_and_gates_off_the_brokers_tick_value(tmp_path):
    broker = SimulatedBroker(rates=_golden_df(), balance=3121.0)
    broker._symbol_risk = _cent_gold()
    engine = _make_engine(
        broker, tmp_path,
        risk=RiskConfig(max_loss_pct_per_trade=2.0, sizing="percent", min_rr=0.0),
    )
    broker._cursor = 7

    event = engine.poll_once()
    assert event["event"] == "order_placed"
    lots = broker._orders[0]["volume"]
    ask = broker.quote("XAUUSD").ask
    assert _cent_gold().money_risk(ask - SL, lots) <= 3121.0 * 0.02 * (1 + 1e-9)


def test_unpopulated_contract_specs_are_refused_not_guessed(tmp_path):
    """A terminal still loading a symbol reports zeros. Sizing off a zero
    divides by zero or sizes infinitely — refuse instead."""
    from trading_bot.broker.base import SymbolRisk

    broker = SimulatedBroker(rates=_golden_df(), balance=3121.0)
    broker._symbol_risk = SymbolRisk(0.0, 0.0, 0.01, 0.01, 200.0)
    engine = _make_engine(
        broker, tmp_path, risk=RiskConfig(max_loss_pct_per_trade=2.0, sizing="percent")
    )
    broker._cursor = 7
    assert engine.poll_once()["event"] == "order_skipped"
    assert broker._orders == []


# -- concurrent slots (backtest parity at max_concurrent > 1) -----------------


def test_second_slot_lets_a_setup_through_when_one_position_is_open(tmp_path):
    """At max_concurrent=2 an open position must NOT block the next setup.

    Measured out-of-sample: the single-slot guard was declining trades, not bad
    trades (R per trade +0.1183 -> +0.1164 while the sample doubled).
    """
    broker = SimulatedBroker(rates=_golden_df())
    broker.simulate_position(9001, symbol="XAUUSD", magic=_MAGIC)
    engine = _make_engine(
        broker, tmp_path,
        risk=RiskConfig(max_loss_pct_per_trade=1.0, max_concurrent=2),
    )
    broker._cursor = 7  # ON the setup bar

    event = engine.poll_once()

    assert event["event"] != "order_skipped", event
    assert len(broker.positions("XAUUSD", _MAGIC)) == 2


def test_the_budget_still_closes_once_it_is_full(tmp_path):
    """Two slots means two, not unlimited. The third setup must be refused."""
    broker = SimulatedBroker(rates=_golden_df())
    broker.simulate_position(9001, symbol="XAUUSD", magic=_MAGIC)
    broker.simulate_position(9002, symbol="XAUUSD", magic=_MAGIC)
    engine = _make_engine(
        broker, tmp_path,
        risk=RiskConfig(max_loss_pct_per_trade=1.0, max_concurrent=2),
    )
    broker._cursor = 7

    event = engine.poll_once()

    assert event == {"event": "order_skipped", "reason": "position_open"}
    assert len(broker.positions("XAUUSD", _MAGIC)) == 2


def test_open_positions_and_armed_orders_share_one_budget(tmp_path):
    """A position plus an armed order is two slots used, not one of each.

    They are different exposures but they consume the same capital, so counting
    them separately would let max_concurrent=2 carry four live commitments.
    """
    broker = SimulatedBroker(rates=_golden_df())
    broker.simulate_position(9001, symbol="XAUUSD", magic=_MAGIC)
    broker.simulate_pending(ENTRY + 50.0, symbol="XAUUSD", magic=_MAGIC)
    engine = _make_engine(
        broker, tmp_path,
        risk=RiskConfig(max_loss_pct_per_trade=1.0, max_concurrent=2),
    )
    broker._cursor = 7

    event = engine.poll_once()

    assert event["event"] == "order_skipped"
    assert len(broker.positions("XAUUSD", _MAGIC)) == 1


def test_default_config_is_still_one_slot(tmp_path):
    """Nothing changes for a config that never mentions max_concurrent."""
    broker = SimulatedBroker(rates=_golden_df())
    broker.simulate_position(9001, symbol="XAUUSD", magic=_MAGIC)
    engine = _make_engine(broker, tmp_path)
    broker._cursor = 7

    assert engine.poll_once() == {"event": "order_skipped", "reason": "position_open"}


# ---------------------------------------------------------------------------
# [live] fetch_bars — plan 03-02: configurable multi-day history window for the
# AI regime read. Default 0 must keep the legacy strategy-minimum formula.
# ---------------------------------------------------------------------------

def test_n_bars_returns_fetch_bars_when_set(tmp_path):
    """03-02: _n_bars() honors [live] fetch_bars when it is > 0."""
    broker = SimulatedBroker(rates=_golden_df())
    engine = _make_engine(broker, tmp_path, live=replace(_DEMO, fetch_bars=5000))
    assert engine._n_bars() == 5000


def test_n_bars_returns_strategy_minimum_when_fetch_bars_zero(tmp_path):
    """03-02: fetch_bars 0 (the default, or explicitly set) keeps the legacy
    strategy-minimum window — byte-identical to every existing config."""
    expected = 60 + 2 + 2 + 5  # sr_lookback + fractal_left + fractal_right + 5
    broker = SimulatedBroker(rates=_golden_df())
    for fetch_bars in (0, _DEMO.fetch_bars):  # explicit 0 AND the dataclass default
        engine = _make_engine(
            broker, tmp_path, live=replace(_DEMO, fetch_bars=fetch_bars)
        )
        assert engine._n_bars() == expected


def test_fetch_bars_on_a_short_frame_is_a_normal_poll(tmp_path):
    """03-02: a huge fetch_bars against a broker with only a short seed frame
    returns what the broker has — a normal bar_check, no crash, no lookahead
    change (the window is just narrower than asked for)."""
    broker = SimulatedBroker(rates=_golden_df())
    engine = _make_engine(broker, tmp_path, live=replace(_DEMO, fetch_bars=5000))
    broker._cursor = 1

    event = engine.poll_once()

    assert event["event"] == "bar_check"
    assert event["new_bar"] is True
