"""ReplayBroker + dry-run wiring (quick task 260819-nhq).

``SimulatedBroker`` holds "now" still, so before this the CLI's dry-run mode
handed the engine a broker with no rates and every poll logged
``bar_fetch_failed`` — the strategy never ran. These tests lock the replay
behaviour and the dry-run broker wiring that makes ``live --mode dry-run`` a
real offline smoke test.
"""

from __future__ import annotations

import pandas as pd
import pytest

from trading_bot.broker import DryRunBroker, ReplayBroker, SimulatedBroker
from trading_bot.broker.base import BrokerUnavailableError


def _frame(n: int = 20) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="5min", name="time")
    base = range(n)
    return pd.DataFrame(
        {
            "open": [100.0 + i for i in base],
            "high": [100.5 + i for i in base],
            "low": [99.5 + i for i in base],
            "close": [100.2 + i for i in base],
        },
        index=idx,
    )


# -- SimulatedBroker cursor -------------------------------------------------


def test_explicit_cursor_rewinds_now():
    """An explicit cursor replaces the private ``_cursor`` poke the E2E walk
    used to need — "now" starts before the end of the frame."""
    b = SimulatedBroker(rates=_frame(), cursor=5)
    df = b.fetch_rates("XAUUSD", "M5", 10)
    assert len(df) == 5  # only 5 closed bars exist behind the cursor
    assert df.index[-1] == _frame().index[4]


def test_cursor_defaults_to_end_of_data():
    """Omitting the cursor keeps the original behaviour."""
    b = SimulatedBroker(rates=_frame())
    assert len(b.fetch_rates("XAUUSD", "M5", 10)) == 10


def test_window_start_clamps_instead_of_wrapping():
    """A cursor with fewer than ``count`` bars behind it must return the bars
    that exist, never wrap around via negative-index slicing."""
    b = SimulatedBroker(rates=_frame(100), cursor=3)
    df = b.fetch_rates("XAUUSD", "M5", 50)
    assert len(df) == 3
    assert df.index[0] == _frame(100).index[0]


# -- ReplayBroker -----------------------------------------------------------


def test_replay_advances_one_bar_per_fetch():
    """Each fetch walks "now" forward exactly one bar, so a polling caller
    sees one new closed bar per poll — the shape a live terminal produces."""
    b = ReplayBroker(rates=_frame(), cursor=10)
    lasts = [b.fetch_rates("XAUUSD", "M5", 5).index[-1] for _ in range(4)]
    assert lasts == list(_frame().index[9:13])


def test_replay_stops_at_end_of_data():
    """Past the last bar the frame stops growing (a quiet-market no-new-bar),
    and the cursor never runs off the end."""
    frame = _frame(12)
    b = ReplayBroker(rates=frame, cursor=11)
    for _ in range(6):
        df = b.fetch_rates("XAUUSD", "M5", 5)
    assert b.exhausted
    assert df.index[-1] == frame.index[-1]


def test_replay_without_rates_is_still_graceful():
    """No data on disk stays a graceful BrokerUnavailableError, not a crash."""
    b = ReplayBroker()
    assert b.exhausted
    with pytest.raises(BrokerUnavailableError):
        b.fetch_rates("XAUUSD", "M5", 5)


def test_replay_under_dry_run_wrapper_still_places_nothing():
    """Replay changes only the data cursor — the no-send guarantee holds."""
    inner = ReplayBroker(rates=_frame(), cursor=5)
    dry = DryRunBroker(inner, logger=None)
    from trading_bot.broker.base import OrderRequest

    result = dry.place_market_buy(
        OrderRequest(
            symbol="XAUUSD",
            volume=0.01,
            entry=101.0,
            sl=100.0,
            tp=102.0,
            magic=77001,
            deviation=20,
            comment="t",
        )
    )
    assert result.placed is False
    assert result.ticket == 0
    assert inner._orders == []
