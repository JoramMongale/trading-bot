"""Spec-driven money conversion + per-closed-trade spread netting in trade_stats.

Companion to tests/test_backtest.py::test_golden_stats_open_trade_included_in_net_pnl,
which pins the LEGACY byte-identical behavior (that file is untouched and still
passes). These tests cover the two extensions added on top of the legacy path:

  - ``value_per_point`` (InstrumentSpec.tick_value / tick_size — account-currency
    money per 1.0 price-unit move on ONE FULL lot) replaces gold's contract_size
    money assumption when supplied; ``None`` keeps the legacy ``contract_size *
    lot`` product bit-identical.
  - ``spread_price`` is netted exactly once per CLOSED trade (SL/TP) in the
    instrument's own PRICE units, before the r_multiple recompute, so ``avg_r``
    is net of spread; OPEN trades are never netted.

trade_stats mutates each trade dict in place (``pnl_points``/``r_multiple``),
so every call in these tests gets a freshly built fixture.
"""

from datetime import datetime

import pytest

from trading_bot.backtest.stats import trade_stats


def _t(**overrides):
    """A bare engine-shaped trade record with long-side defaults."""
    base = {
        "entry_time": datetime(2021, 2, 1),
        "exit_time": datetime(2021, 2, 1),
        "entry_idx": 0,
        "exit_idx": 1,
        "entry": 100.00,
        "sl": 99.90,
        "tp": 100.10,
        "exit_price": 100.00,
        "exit_reason": "OPEN",
        "direction": "long",
    }
    base.update(overrides)
    return base


def _legacy_trades():
    """3-trade synthetic book: long TP winner, long SL loser, long OPEN.

    Hand-computed gross numbers (risk = entry - sl, all risk 0.10):
      T1 long TP    pnl +0.10  r =  1.0
      T2 long SL    pnl -0.10  r = -1.0
      T3 long OPEN  pnl +0.10  r =  1.0   (excluded from wins/losses, in net P&L)
    """
    return [
        _t(
            entry=100.00, sl=99.90, tp=100.10,
            exit_price=100.10, exit_reason="TP",
            entry_idx=0, exit_idx=2,
        ),
        _t(
            entry=100.00, sl=99.90, tp=100.10,
            exit_price=99.90, exit_reason="SL",
            entry_idx=0, exit_idx=1,
        ),
        _t(
            entry=101.00, sl=100.90, tp=101.10,
            exit_price=101.10, exit_reason="OPEN",
            entry_idx=0, exit_idx=3,
        ),
    ]


def _legacy_expected():
    """Hand-computed trade_stats(_legacy_trades()) at default params."""
    return {
        "total_trades": 2,
        "open_trades": 1,
        "wins": 1,
        "losses": 1,
        "win_rate": pytest.approx(0.5),
        "net_pnl_points": pytest.approx(0.10),   # +0.10 -0.10 +0.10
        "net_pnl_usd": pytest.approx(0.10),      # 0.10 * 100 * 0.01
        "avg_r": pytest.approx(0.0),             # (1.0 + -1.0) / 2
        "profit_factor": pytest.approx(1.0),     # 0.10 / 0.10
        "max_drawdown_usd": pytest.approx(0.10),
        "avg_trade_bars": pytest.approx(2.0),    # (2 + 1 + 3) / 3
    }


def test_legacy_defaults_unchanged():
    """No-arg call reproduces the hand-computed legacy dict (golden pin)."""
    stats = trade_stats(_legacy_trades())
    assert stats == _legacy_expected()


def test_zero_spread_and_none_value_are_legacy():
    """Explicit None/0.0 params return exactly the legacy dict (byte-identical)."""
    stats = trade_stats(_legacy_trades(), value_per_point=None, spread_price=0.0)
    assert stats == _legacy_expected()
    # identical to the plain default call on a fresh fixture
    assert trade_stats(_legacy_trades()) == trade_stats(
        _legacy_trades(), value_per_point=None, spread_price=0.0
    )


def test_spec_money_uses_value_per_point():
    """With value_per_point=910.0 (EURJPYc 0.001 tick / 0.91 tick_value) money
    is pnl_points x 910.0 x lot — NOT the legacy pnl_points x 100 x lot."""
    trades = _legacy_trades()
    stats = trade_stats(trades, value_per_point=910.0)

    assert stats["net_pnl_points"] == pytest.approx(0.10)
    assert stats["net_pnl_usd"] == pytest.approx(
        stats["net_pnl_points"] * 910.0 * 0.01
    )
    assert stats["net_pnl_usd"] == pytest.approx(0.91)   # not 0.10
    assert stats["max_drawdown_usd"] == pytest.approx(0.10 * 910.0 * 0.01)
    assert stats["max_drawdown_usd"] == pytest.approx(0.91)


def test_spread_netted_once_per_closed_trade():
    """spread_price=0.006 nets each CLOSED trade exactly once; the OPEN trade
    stays gross. net_pnl_points == gross_sum - 2 * 0.006."""
    trades = _legacy_trades()
    stats = trade_stats(trades, spread_price=0.006)

    long_tp, long_sl, open_trade = trades
    assert long_tp["pnl_points"] == pytest.approx(0.10 - 0.006)   # netted once
    assert long_sl["pnl_points"] == pytest.approx(-0.10 - 0.006)  # netted once
    assert open_trade["pnl_points"] == pytest.approx(0.10)        # OPEN gross
    assert stats["net_pnl_points"] == pytest.approx(
        0.10 - 2 * 0.006   # closed gross 0.10 - 0.012; OPEN +0.10 included gross
    )


def test_avg_r_is_net_of_spread():
    """r_multiple is recomputed from the NETTED pnl_points, so avg_r is
    net-of-spread. A short TP winner proves direction-sign correctness: its
    netted R is positive and equal to the long winner's."""
    trades = [
        # long TP winner  risk 0.10  gross +0.10
        _t(entry=100.00, sl=99.90, tp=100.10, exit_price=100.10,
           exit_reason="TP", entry_idx=0, exit_idx=2),
        # long SL loser   risk 0.10  gross -0.10
        _t(entry=100.00, sl=99.90, tp=100.10, exit_price=99.90,
           exit_reason="SL", entry_idx=0, exit_idx=1),
        # short TP winner risk -0.10 (sl above entry)  gross +0.10
        _t(direction="short", entry=100.00, sl=100.10, tp=99.90,
           exit_price=99.90, exit_reason="TP", entry_idx=0, exit_idx=2),
    ]
    stats = trade_stats(trades, spread_price=0.006)

    long_win, long_loss, short_win = trades
    assert long_win["r_multiple"] == pytest.approx((0.10 - 0.006) / 0.10)
    assert long_loss["r_multiple"] == pytest.approx((-0.10 - 0.006) / 0.10)
    assert short_win["r_multiple"] == pytest.approx((0.10 - 0.006) / 0.10)
    expected_avg_r = ((0.10 - 0.006) + (-0.10 - 0.006) + (0.10 - 0.006)) / 0.10 / 3
    assert stats["avg_r"] == pytest.approx(expected_avg_r)


def test_open_trade_pnl_untouched():
    """An OPEN trade's pnl_points is NOT reduced by spread; it stays in net P&L
    at gross (existing convention: not a win/loss, included in net P&L)."""
    trades = _legacy_trades()
    stats = trade_stats(trades, spread_price=0.006)

    open_trade = trades[2]
    assert open_trade["exit_reason"] == "OPEN"
    assert open_trade["pnl_points"] == pytest.approx(0.10)  # gross, never netted
    closed_net = (0.10 - 0.006) + (-0.10 - 0.006)
    assert stats["net_pnl_points"] == pytest.approx(closed_net + 0.10)
    assert stats["open_trades"] == 1
