"""End-to-end dry-run test over the golden frame (plan 02-05, task 2).

Proves the dry-run path end to end: a full walk of the golden 12-bar frame
through LiveEngine -> DryRunBroker produces a complete, correct decision trail
(setup_detected -> order_placed with the backtest-identical prices), while the
inner SimulatedBroker ledger stays EMPTY (phase success criterion 4: dry-run
places nothing). A second scenario seeds an equivalent pending order inside
the inner broker and proves the setup bar then reports
``order_skipped reason=pending_order_equivalent`` instead of re-triggering
(phase success criterion 5).

Golden frame conventions (identical values to tests/test_cli.py _FIX_* lists
and test_live_engine.py):

  Swing high 101.00 at idx 2 confirms at idx 4  -> resistance 101.00
  Swing low  100.10 at idx 4 confirms at idx 6  -> support    100.10
  Setup fires at idx 6 (close 101.05 > 101.00, prior close 100.70 <= 101.00)
  Armed Buy Stop: entry=101.00 (resistance), sl=100.10-0.01=100.09,
  tp=101.00+(101.00-100.09)=101.91 (exact 1:1 R:R, STRAT-03)

The engine is driven directly (no CLI main()) so the walk is deterministic:
SimulatedBroker's cursor is "now", advance() closes the next bar, and the
setup bar (idx 6, 2021-02-01T00:30:00) is the last closed bar when the cursor
reaches 7.
"""

import json
from dataclasses import replace

import pandas as pd
import pytest

from trading_bot.broker.dry_run import DryRunBroker
from trading_bot.broker.simulated import SimulatedBroker
from trading_bot.config import load_config
from trading_bot.live.engine import LiveEngine
from trading_bot.logging_utils import get_logger

# ---------------------------------------------------------------------------
# Golden 12-bar 5-minute OHLC. Same values as tests/test_cli.py (_FIX_* lists
# — copied locally, not imported, because the tests dir is not a package).
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

ENTRY = 101.00  # resistance at the setup bar (idx 6)
SL = 100.09  # support - sl_buffer
TP = 101.91  # entry + (entry - sl), exact 1:1 R:R
MAGIC = 77001  # config [live] magic_number
SETUP_BAR = "2021-02-01T00:30:00"  # idx 6


def _golden_df() -> pd.DataFrame:
    index = pd.date_range(
        "2021-02-01 00:00", periods=len(_OPENS), freq="5min", name="time"
    )
    return pd.DataFrame(
        {"open": _OPENS, "high": _HIGHS, "low": _LOWS, "close": _CLOSES},
        index=index,
    )


def _dry_broker() -> tuple[DryRunBroker, SimulatedBroker]:
    """A DryRunBroker wrapping a golden-frame SimulatedBroker (dry-run seam).

    The inner broker is returned so tests can prove nothing reached it and
    can seed pending orders for the dedup scenario.
    """
    inner = SimulatedBroker(rates=_golden_df(), trade_mode=0)
    return DryRunBroker(inner, logger=None), inner


def _cfg() -> object:
    """Committed config with [live] mode forced to dry-run."""
    cfg = load_config("config/config.toml")
    if cfg.live.mode != "dry-run":
        cfg = replace(cfg, live=replace(cfg.live, mode="dry-run"))
    return cfg


def _engine(broker, log_path, name="live_test"):
    return LiveEngine(_cfg(), broker, get_logger(name, str(log_path)))


def _walk(engine, dry: DryRunBroker, inner: SimulatedBroker) -> list[dict]:
    """Close every golden bar one at a time, collecting the event dicts.

    The cursor is reset to 0 (empty frame -> no_data bar_check), so every bar
    idx 0..11 becomes the last closed bar exactly once as the walk advances.
    ``advance()`` is SimulatedBroker-specific (not on the BrokerClient ABC),
    so the walk advances the INNER broker directly.
    """
    inner._cursor = 0  # rewind "now" to before the first bar
    events = []
    for _ in range(len(_OPENS)):
        events.append(engine.poll_once())
        inner.advance()
    return events


def test_dry_run_walk_places_nothing_and_logs_full_trail(tmp_path):
    """Walking the golden frame through DryRunBroker yields exactly one order
    event with the backtest-identical prices (STRAT-03), an EMPTY inner
    ledger (criterion 4: dry-run places nothing), and the full decision trail
    in live.log (SAFE-02)."""
    dry, inner = _dry_broker()
    engine = _engine(dry, tmp_path / "live.log")
    events = _walk(engine, dry, inner)

    # Exactly one order event — only idx 6 is a setup bar in the golden frame.
    assert [e["event"] for e in events].count("order_placed") == 1

    # The order event carries the hand-computed golden prices, DryRunBroker's
    # placed=False marker (ticket=0), and the exact 1:1 R:R identity.
    placed = next(e for e in events if e["event"] == "order_placed")
    assert placed["ticket"] == 0  # DryRunBroker: placed=False, no ticket
    assert placed["entry"] == pytest.approx(ENTRY)
    assert placed["sl"] == pytest.approx(SL)
    assert placed["tp"] == pytest.approx(TP)
    assert placed["tp"] == pytest.approx(placed["entry"] + (placed["entry"] - placed["sl"]))

    # Phase success criterion 4: nothing reached the inner broker.
    assert len(inner._orders) == 0
    assert inner.positions("XAUUSD", MAGIC) == []

    # SAFE-02: the decision trail — setup_detected, order_placed, bar_check —
    # is in live.log with prices rounded to 2 dp (XAUUSD quoting).
    log_text = (tmp_path / "live.log").read_text()
    assert "event=setup_detected" in log_text
    assert f"bar={SETUP_BAR}" in log_text
    assert "entry=101.0" in log_text and "sl=100.09" in log_text and "tp=101.91" in log_text
    assert "event=order_placed" in log_text
    assert "ticket=0" in log_text
    assert "event=bar_check" in log_text

    # Every poll result is JSON-serializable (str/int/float/bool/None only).
    for event in events:
        json.dumps(event)
        for key, value in event.items():
            assert isinstance(value, (str, int, float, bool, type(None))), (
                f"{key}={value!r} in {event['event']} is not JSON-plain"
            )


def test_dry_run_dedup_blocks_retrigger(tmp_path):
    """An equivalent order already armed in the INNER broker blocks the setup
    bar: order_skipped reason=pending_order_equivalent, and the ledger stays at
    exactly the seeded order (criterion 5 — no double placement)."""
    dry, inner = _dry_broker()
    # Seed an equivalent armed order directly in the inner broker (dry-run
    # never sends, so the seam would otherwise stay empty).
    inner.simulate_pending(ENTRY, symbol="XAUUSD", magic=MAGIC)
    engine = _engine(dry, tmp_path / "dedup_live.log", name="live_test_dedup")
    events = _walk(engine, dry, inner)

    # The setup bar reports the dedup skip instead of re-triggering.
    skipped = [e for e in events if e["event"] == "order_skipped"]
    assert len(skipped) == 1
    assert skipped[0] == {"event": "order_skipped", "reason": "pending_order_equivalent"}
    assert [e["event"] for e in events].count("order_placed") == 0
    # No additional ledger entry — the seeded order is the only one.
    assert len(inner._orders) == 1
    log_text = (tmp_path / "dedup_live.log").read_text()
    assert "reason=pending_order_equivalent" in log_text


def test_poll_loop_survives_an_unexpected_error(tmp_path, monkeypatch, capsys):
    """A crash inside one poll must not kill the loop.

    On 2026-08-19 the MT5 adapter raised AttributeError while placing the first
    real order; the exception escaped poll_once and killed the process, so the
    bot stopped watching the market entirely. Skipping a poll is recoverable;
    dying silently is not.
    """
    import trading_bot.cli as cli

    calls = {"n": 0}

    class _Boom:
        def poll_once(self):
            calls["n"] += 1
            if calls["n"] == 1:
                raise AttributeError("'MetaTrader5' object has no attribute 'SYMBOL_FILLING_IOC'")
            raise KeyboardInterrupt  # end the loop on the second pass

    monkeypatch.setattr(cli, "LiveEngine", lambda *a, **k: _Boom())
    monkeypatch.setattr(cli, "build_broker", lambda *a, **k: object())
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "c.toml").write_text(
        '[data]\nsource="histdata"\nraw_dir="data/raw"\nsymbol="XAUUSD"\n'
        'timeframe="M5"\nstart="2024-01-01"\nend="2026-07-31"\n'
        "[strategy]\nfractal_left=2\nfractal_right=2\nsr_lookback=60\n"
        "rr_multiple=1.0\nsl_buffer=0.01\n"
        "[trading]\nlot=0.01\ncontract_size=100\nspread_assumption=0.0\n"
        '[backtest]\noutput_dir="output"\n'
        '[live]\nmode="dry-run"\npoll_interval=0.01\n'
    )

    rc = cli.main(["live", "--config", str(tmp_path / "config" / "c.toml")])

    assert rc == 0  # KeyboardInterrupt is a clean stop
    assert calls["n"] == 2  # it kept going after the AttributeError
    log = (tmp_path / "output" / "live.log").read_text()
    assert "event=poll_error" in log
    assert "AttributeError" in log


def test_poll_loop_reconnects_after_consecutive_failures(tmp_path, monkeypatch):
    """04-01: N consecutive bar_fetch_failed polls trigger broker.reconnect(),
    then a clean poll resets the counter. The loop never exits."""
    import trading_bot.cli as cli

    class _Flaky:
        def __init__(self):
            self.fetches = 0
            self.reconnects = 0

        def poll_once(self):
            self.fetches += 1
            if self.fetches <= 3:  # three failures: reconnect_after=3
                return {"event": "bar_fetch_failed", "error": "terminal gone"}
            if self.fetches == 4:
                return {"event": "bar_check", "new_bar": False}
            raise KeyboardInterrupt  # clean stop

    class _ReconnectableBroker:
        def __init__(self, flaky):
            self.flaky = flaky
            self.reconnect_calls = 0

        def connect(self):
            pass

        def reconnect(self):
            self.reconnect_calls += 1

    flaky = _Flaky()
    broker = _ReconnectableBroker(flaky)
    monkeypatch.setattr(cli, "LiveEngine", lambda *a, **k: flaky)
    monkeypatch.setattr(cli, "build_broker", lambda *a, **k: broker)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "c.toml").write_text(
        '[data]\nsource="histdata"\nraw_dir="data/raw"\nsymbol="XAUUSD"\n'
        'timeframe="M5"\nstart="2024-01-01"\nend="2026-07-31"\n'
        "[strategy]\nfractal_left=2\nfractal_right=2\nsr_lookback=60\n"
        "rr_multiple=1.0\nsl_buffer=0.01\n"
        "[trading]\nlot=0.01\ncontract_size=100\nspread_assumption=0.0\n"
        '[backtest]\noutput_dir="output"\n'
        '[live]\nmode="live"\npoll_interval=0.01\nreconnect_after=3\n'
        'reconnect_backoff=0.0\n'
    )

    rc = cli.main(["live", "--config", str(tmp_path / "config" / "c.toml"),
                   "--log", "live_reconn.log"])

    assert rc == 0
    assert broker.reconnect_calls == 1  # exactly one reconnect after 3 failures
    log = (tmp_path / "output" / "live_reconn.log").read_text()
    assert "event=reconnect_attempt" in log
    assert "event=reconnected" in log


def test_poll_loop_reconnect_failure_logs_and_backs_off(tmp_path, monkeypatch):
    """04-01: a reconnect that fails is logged and the loop keeps polling
    (backoff sleep) rather than exiting."""
    import trading_bot.cli as cli

    class _Broker:
        def __init__(self):
            self.polls = 0
            self.reconnect_calls = 0

        def poll_once(self):
            self.polls += 1
            if self.polls <= 3:
                return {"event": "bar_fetch_failed", "error": "gone"}
            if self.polls == 4:
                return {"event": "bar_check", "new_bar": False}  # clean poll resets
            raise KeyboardInterrupt

    class _BrokerNoReconnect:
        def __init__(self):
            self.reconnect_calls = 0

        def connect(self):
            pass

        def reconnect(self):
            self.reconnect_calls += 1
            from trading_bot.broker.base import BrokerUnavailableError

            raise BrokerUnavailableError("still down")

    broker = _BrokerNoReconnect()
    monkeypatch.setattr(cli, "LiveEngine", lambda *a, **k: _Broker())
    monkeypatch.setattr(cli, "build_broker", lambda *a, **k: broker)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "c.toml").write_text(
        '[data]\nsource="histdata"\nraw_dir="data/raw"\nsymbol="XAUUSD"\n'
        'timeframe="M5"\nstart="2024-01-01"\nend="2026-07-31"\n'
        "[strategy]\nfractal_left=2\nfractal_right=2\nsr_lookback=60\n"
        "rr_multiple=1.0\nsl_buffer=0.01\n"
        "[trading]\nlot=0.01\ncontract_size=100\nspread_assumption=0.0\n"
        '[backtest]\noutput_dir="output"\n'
        '[live]\nmode="live"\npoll_interval=0.01\nreconnect_after=3\n'
        'reconnect_backoff=0.01\n'
    )

    rc = cli.main(["live", "--config", str(tmp_path / "config" / "c.toml"),
                   "--log", "live_reconn2.log"])

    assert rc == 0
    assert broker.reconnect_calls == 1  # first reconnect attempt failed
    log = (tmp_path / "output" / "live_reconn2.log").read_text()
    assert "event=reconnect_failed" in log
    assert "still down" in log
