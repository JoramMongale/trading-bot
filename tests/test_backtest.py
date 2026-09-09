"""Tests for src/trading_bot/backtest/{engine,stats}.py — event-loop backtest + stats.

Covers the VERIFIED event-loop conventions from RESEARCH.md RQ2:
  - fill from bar t+1 (never the signal bar), fill = max(entry, open) with
    gap-open fills at open
  - exact 1:1 R:R on the armed order (tp = entry + (entry - sl))
  - pessimistic intrabar ordering: SL checked before TP
  - one active trade at a time (new setups skipped while open)
  - signal on the final bar produces zero trades (no lookahead fill)
  - OPEN exit at the last close for trades still open at end of data
  - trade_stats() aggregate math on known-by-hand trades
  - golden integration: one small frame -> two known-by-hand records

All expected values are hand-computed (see frame docstrings); floats are
compared with pytest.approx because 2-dp gold prices are not exact in binary.
"""

import numpy as np
import pandas as pd
import pytest

from trading_bot.backtest.engine import run_backtest
from trading_bot.backtest.stats import trade_stats
from trading_bot.strategy.levels import support_resistance
from trading_bot.strategy.signals import detect_setups
from trading_bot.strategy.swings import detect_swings

T = pd.Timestamp


def make_m5(opens, highs, lows, closes, start="2021-02-01"):
    """Build a 5-minute DataFrame (datetime index, name 'time') from OHLC lists."""
    n = len(closes)
    index = pd.date_range(start, periods=n, freq="5min", name="time")
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes},
        index=index,
    )


def pipeline(df):
    """The exact Pass-A chain run_backtest uses, for direct signal assertions."""
    return detect_setups(support_resistance(detect_swings(df)))


# ---------------------------------------------------------------------------
# Golden integration frame: two trades, fully hand-computed.
#
#  Swing high 101.00 at idx 2 confirms at idx 4   -> resistance 101.00
#  Swing low  100.10 at idx 4 confirms at idx 6   -> support    100.10
#  Setup fires at idx 6 (close 101.05 > 101.00, prior close 100.70 <= 101.00)
#  Fill at idx 7: max(101.00, open 101.10) = 101.10 ; sl=100.09, tp=101.91
#  TP exit at idx 9 (high 102.05 >= 101.91) -> exit_price 101.91
#
#  Trade 1 closes. Swing high 102.05 at idx 9 confirms at idx 11 -> res 102.05.
#  Pullback forms swing low 100.70 at idx 12 (confirms idx 14; support stays
#  100.10 because the rolling min keeps the older lower swing).
#  Setup fires at idx 14 (close 102.60 > 102.05, prior close 101.30 <= 102.05)
#  Fill at idx 15: max(102.05, open 102.60) = 102.60 ; sl=100.09, tp=104.01
#  Never hits SL/TP -> OPEN exit at last close 102.20 (idx 18).
# ---------------------------------------------------------------------------
GOLDEN_OPENS = [
    100.00, 100.10, 100.60, 100.90, 100.50, 100.15, 100.80, 101.10, 101.60,
    101.90, 101.80, 101.20, 100.90, 100.90, 101.30, 102.60, 102.80, 102.50,
    102.20,
]
GOLDEN_HIGHS = [
    100.00, 100.50, 101.00, 100.90, 100.50, 100.70, 101.05, 101.50, 101.85,
    102.05, 101.80, 101.20, 100.90, 101.30, 102.60, 103.00, 102.80, 102.50,
    102.20,
]
GOLDEN_LOWS = [
    100.00, 100.10, 100.60, 100.50, 100.10, 100.15, 100.80, 101.10, 101.60,
    101.90, 101.60, 100.90, 100.70, 101.00, 102.00, 102.60, 102.40, 102.10,
    101.90,
]
GOLDEN_CLOSES = [
    100.00, 100.50, 101.00, 100.50, 100.10, 100.70, 101.05, 101.50, 101.85,
    102.05, 101.60, 100.90, 100.70, 101.30, 102.60, 103.00, 102.80, 102.50,
    102.20,
]

GOLDEN_TRADES = [
    {
        "entry_time": T("2021-02-01 00:35"),
        "entry": 101.10,
        "sl": 100.09,
        "tp": 101.91,
        "exit_time": T("2021-02-01 00:45"),
        "exit_price": 101.91,
        "exit_reason": "TP",
    },
    {
        "entry_time": T("2021-02-01 01:15"),
        "entry": 102.60,
        "sl": 100.09,
        "tp": 104.01,
        "exit_time": T("2021-02-01 01:30"),
        "exit_price": 102.20,
        "exit_reason": "OPEN",
    },
]


def test_golden_integration_full_records():
    df = make_m5(GOLDEN_OPENS, GOLDEN_HIGHS, GOLDEN_LOWS, GOLDEN_CLOSES)
    trades = run_backtest(df)

    assert len(trades) == 2
    for got, exp in zip(trades, GOLDEN_TRADES):
        assert got["entry_time"] == exp["entry_time"]
        assert got["exit_time"] == exp["exit_time"]
        assert got["exit_reason"] == exp["exit_reason"]
        for field in ("entry", "sl", "tp", "exit_price"):
            assert got[field] == pytest.approx(exp[field])
    # tp/sl are frozen from the SIGNAL bar's levels, so the exact 1:1 identity
    # tp == entry + (entry - sl) holds against the armed entry (resistance), not
    # the fill entry (which gaps here). The record-level 1:1 is covered by
    # test_exact_one_to_one_rr_on_record with a non-gap fill.
    assert trades[0]["tp"] - trades[0]["sl"] == pytest.approx(
        2 * (101.00 - trades[0]["sl"])
    )


def test_golden_stats_open_trade_included_in_net_pnl():
    df = make_m5(GOLDEN_OPENS, GOLDEN_HIGHS, GOLDEN_LOWS, GOLDEN_CLOSES)
    trades = run_backtest(df)
    stats = trade_stats(trades)

    # Trade 1 is closed (TP win); trade 2 is OPEN (excluded from wins/losses,
    # but its P&L is included in the net). net = 0.81 + (102.20 - 102.60) = 0.41
    assert stats["total_trades"] == 1
    assert stats["open_trades"] == 1
    assert stats["wins"] == 1
    assert stats["losses"] == 0
    assert stats["win_rate"] == pytest.approx(1.0)
    assert stats["net_pnl_points"] == pytest.approx(0.41)
    assert stats["net_pnl_usd"] == pytest.approx(0.41)  # 0.41 * 100 * 0.01
    # r_multiple uses the RECORD entry (fill price 101.10): 0.81 / (101.10 - 100.09)
    assert stats["avg_r"] == pytest.approx(0.81 / 1.01)
    # bar count: trade 1 holds idx 7->9 (2), trade 2 holds idx 15->18 (3)
    assert stats["avg_trade_bars"] == pytest.approx(2.5)


def test_fill_timing_signal_bar_never_enters_next_bar_fills():
    # Bars 0-9 of the golden frame: setup at idx 6, fill at idx 7, TP at idx 9.
    df = make_m5(
        GOLDEN_OPENS[:10], GOLDEN_HIGHS[:10], GOLDEN_LOWS[:10], GOLDEN_CLOSES[:10]
    )
    trades = run_backtest(df)

    assert len(trades) == 1
    assert trades[0]["exit_reason"] == "TP"
    # The signal fires at the close of idx 6; the trade must NOT enter at idx 6.
    assert trades[0]["entry_time"] == T("2021-02-01 00:35")  # idx 7
    assert trades[0]["entry_time"] != T("2021-02-01 00:30")  # idx 6 (signal bar)


def test_gap_open_fill_price_equals_open():
    # Bar idx 7 opens at 101.10, ABOVE the armed entry (resistance 101.00).
    # Buy Stop convention: a gap-open bar fills at open, not at the level.
    df = make_m5(
        GOLDEN_OPENS[:10], GOLDEN_HIGHS[:10], GOLDEN_LOWS[:10], GOLDEN_CLOSES[:10]
    )
    trades = run_backtest(df)

    assert len(trades) == 1
    assert trades[0]["entry"] == pytest.approx(101.10)
    assert trades[0]["entry"] == pytest.approx(df["open"].iloc[7])
    assert trades[0]["entry"] > 101.00  # > the armed Buy Stop level


def test_exact_one_to_one_rr_on_record():
    # Non-gap fill (idx 7 opens AT resistance 101.00) so the record's own
    # entry/sl/tp satisfy the 1:1 identity exactly: tp == entry + (entry - sl).
    opens = [100.00, 100.10, 100.60, 100.90, 100.50, 100.15, 100.80, 101.00, 101.20, 101.60]
    highs = [100.00, 100.50, 101.00, 100.90, 100.50, 100.70, 101.05, 101.20, 101.80, 102.00]
    lows = [100.00, 100.10, 100.60, 100.50, 100.10, 100.15, 100.80, 101.00, 101.40, 101.80]
    closes = [100.00, 100.50, 101.00, 100.50, 100.10, 100.70, 101.05, 101.00, 101.80, 102.00]
    df = make_m5(opens, highs, lows, closes)
    trades = run_backtest(df)

    assert len(trades) == 1
    t = trades[0]
    assert t["entry"] == pytest.approx(101.00)
    assert t["tp"] == pytest.approx(t["entry"] + (t["entry"] - t["sl"]))
    assert t["tp"] == pytest.approx(101.91)
    assert t["exit_reason"] == "TP"
    assert t["exit_price"] == pytest.approx(101.91)


def test_rr_multiple_arms_farther_tp():
    # Same non-gap frame as test_exact_one_to_one_rr_on_record: the setup arms
    # entry 101.00, sl 100.09. rr_multiple scales ONLY the target —
    # tp = entry + rr_multiple * (entry - sl) — while sl and the entry are
    # untouched. With a 2.0 target the trade may not reach it in this short
    # frame (possibly exits OPEN), so assert the ARMED tp and unchanged sl,
    # never the exit.
    opens = [100.00, 100.10, 100.60, 100.90, 100.50, 100.15, 100.80, 101.00, 101.20, 101.60]
    highs = [100.00, 100.50, 101.00, 100.90, 100.50, 100.70, 101.05, 101.20, 101.80, 102.00]
    lows = [100.00, 100.10, 100.60, 100.50, 100.10, 100.15, 100.80, 101.00, 101.40, 101.80]
    closes = [100.00, 100.50, 101.00, 100.50, 100.10, 100.70, 101.05, 101.00, 101.80, 102.00]
    df = make_m5(opens, highs, lows, closes)

    rr2 = run_backtest(df, rr_multiple=2.0)[0]
    assert rr2["entry"] == pytest.approx(101.00)
    assert rr2["sl"] == pytest.approx(100.09)
    assert rr2["tp"] == pytest.approx(101.00 + 2 * (101.00 - 100.09))  # 102.82

    rr15 = run_backtest(df, rr_multiple=1.5)[0]
    assert rr15["entry"] == pytest.approx(101.00)
    assert rr15["sl"] == pytest.approx(100.09)
    assert rr15["tp"] == pytest.approx(101.00 + 1.5 * (101.00 - 100.09))  # 102.365

    # The default reproduces the exact 1:1 target.
    rr1 = run_backtest(df)[0]
    assert rr1["tp"] == pytest.approx(101.91)


def test_pessimistic_sl_before_tp_within_one_bar():
    # Bar idx 8 touches BOTH levels (low 100.05 <= sl 100.09 AND high 102.50
    # >= tp 101.91). Pessimistic convention: the SL exit wins.
    opens = [100.00, 100.10, 100.60, 100.90, 100.50, 100.15, 100.80, 101.10, 101.60]
    highs = [100.00, 100.50, 101.00, 100.90, 100.50, 100.70, 101.05, 101.50, 102.50]
    lows = [100.00, 100.10, 100.60, 100.50, 100.10, 100.15, 100.80, 101.10, 100.05]
    closes = [100.00, 100.50, 101.00, 100.50, 100.10, 100.70, 101.05, 101.50, 101.60]
    df = make_m5(opens, highs, lows, closes)
    trades = run_backtest(df)

    assert len(trades) == 1
    t = trades[0]
    assert t["exit_reason"] == "SL"
    assert t["exit_price"] == pytest.approx(t["sl"])
    assert t["exit_price"] == pytest.approx(100.09)
    # prove the same bar really did touch both levels
    assert df["high"].iloc[8] >= t["tp"]
    assert df["low"].iloc[8] <= t["sl"]


def test_one_trade_at_a_time_second_setup_skipped():
    # Setup at idx 6 (fill idx 7) and a SECOND setup at idx 8 while the first
    # trade is still open. The engine skips it -> exactly one trade.
    opens = [100.00, 100.10, 100.60, 100.90, 100.50, 100.15, 100.80, 101.10, 100.60]
    highs = [100.00, 100.50, 101.00, 100.90, 100.50, 100.70, 101.05, 101.10, 101.30]
    lows = [100.00, 100.10, 100.60, 100.50, 100.10, 100.15, 100.80, 100.40, 100.50]
    closes = [100.00, 100.50, 101.00, 100.50, 100.10, 100.70, 101.05, 100.60, 101.20]
    df = make_m5(opens, highs, lows, closes)

    # The frame genuinely produces TWO setups (idx 6 and idx 8)...
    out = pipeline(df)
    assert out["setup"].sum() == 2
    assert bool(out["setup"].iloc[6]) and bool(out["setup"].iloc[8])

    # ...but the event loop only opens one trade (idx 8's setup is skipped).
    trades = run_backtest(df)
    assert len(trades) == 1
    assert trades[0]["entry_time"] == T("2021-02-01 00:35")
    # the skipped setup is why the trade is still open at the last bar
    assert trades[0]["exit_reason"] == "OPEN"


def test_signal_on_final_bar_produces_zero_trades():
    # Bars 0-6 of the golden frame: the setup fires on the LAST bar (idx 6),
    # so the armed Buy Stop never fills -> no lookahead-fill trade record.
    df = make_m5(
        GOLDEN_OPENS[:7], GOLDEN_HIGHS[:7], GOLDEN_LOWS[:7], GOLDEN_CLOSES[:7]
    )
    out = pipeline(df)
    assert bool(out["setup"].iloc[6])  # signal genuinely on the final bar
    assert run_backtest(df) == []


def test_open_exit_at_last_close_stats():
    # Fill at idx 7 (entry 101.10); never touches SL/TP through idx 8. At end of
    # data the trade closes at the last close (101.00) with exit_reason OPEN.
    opens = [100.00, 100.10, 100.60, 100.90, 100.50, 100.15, 100.80, 101.10, 101.00]
    highs = [100.00, 100.50, 101.00, 100.90, 100.50, 100.70, 101.05, 101.30, 101.20]
    lows = [100.00, 100.10, 100.60, 100.50, 100.10, 100.15, 100.80, 100.80, 100.90]
    closes = [100.00, 100.50, 101.00, 100.50, 100.10, 100.70, 101.05, 101.00, 101.00]
    df = make_m5(opens, highs, lows, closes)
    trades = run_backtest(df)

    assert len(trades) == 1
    t = trades[0]
    assert t["exit_reason"] == "OPEN"
    assert t["exit_time"] == df.index[-1]
    assert t["exit_price"] == pytest.approx(float(df["close"].iloc[-1]))
    assert t["exit_price"] == pytest.approx(101.00)

    stats = trade_stats(trades)
    assert stats["total_trades"] == 0
    assert stats["open_trades"] == 1
    assert stats["wins"] == 0
    assert stats["losses"] == 0
    assert stats["win_rate"] == 0.0
    # OPEN trades are excluded from wins/losses but INCLUDED in net P&L.
    assert stats["net_pnl_points"] == pytest.approx(-0.10)  # 101.00 - 101.10
    assert stats["net_pnl_usd"] == pytest.approx(-0.10)
    assert stats["profit_factor"] == 0.0  # no closed trades -> 0.0, not inf
    assert stats["max_drawdown_usd"] == 0.0
    assert stats["avg_trade_bars"] == pytest.approx(1.0)  # idx 7 -> idx 8


def test_stats_math_on_known_trades():
    trades = [
        {
            "entry_time": T("2021-02-01 00:00"), "entry_idx": 0,
            "entry": 100.00, "sl": 99.90, "tp": 100.10,
            "exit_time": T("2021-02-01 00:10"), "exit_idx": 2,
            "exit_price": 100.10, "exit_reason": "TP",
        },
        {
            "entry_time": T("2021-02-01 00:00"), "entry_idx": 0,
            "entry": 100.00, "sl": 99.90, "tp": 100.10,
            "exit_time": T("2021-02-01 00:05"), "exit_idx": 1,
            "exit_price": 99.90, "exit_reason": "SL",
        },
        {
            "entry_time": T("2021-02-01 00:00"), "entry_idx": 0,
            "entry": 101.00, "sl": 100.90, "tp": 101.10,
            "exit_time": T("2021-02-01 00:10"), "exit_idx": 2,
            "exit_price": 101.10, "exit_reason": "TP",
        },
    ]
    stats = trade_stats(trades)

    assert stats["total_trades"] == 3
    assert stats["open_trades"] == 0
    assert stats["wins"] == 2
    assert stats["losses"] == 1
    assert stats["win_rate"] == pytest.approx(2 / 3)
    assert stats["net_pnl_points"] == pytest.approx(0.10)   # +0.10 -0.10 +0.10
    assert stats["net_pnl_usd"] == pytest.approx(0.10)      # 0.10 * 100 * 0.01
    assert stats["avg_r"] == pytest.approx(1 / 3)           # (1 + -1 + 1) / 3
    assert stats["profit_factor"] == pytest.approx(2.0)     # 0.20 / 0.10
    # equity curve in USD: [0.10, 0.00, 0.10]; peak [0.10, 0.10, 0.10]
    assert stats["max_drawdown_usd"] == pytest.approx(0.10)
    assert stats["avg_trade_bars"] == pytest.approx(5 / 3)  # (2 + 1 + 2) / 3


def test_stats_empty_trades_all_zero():
    stats = trade_stats([])
    assert stats == {
        "total_trades": 0,
        "open_trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "net_pnl_points": 0.0,
        "net_pnl_usd": 0.0,
        "avg_r": 0.0,
        "profit_factor": 0.0,  # NOT inf for an empty list
        "max_drawdown_usd": 0.0,
        "avg_trade_bars": 0.0,
    }


def test_input_frame_never_mutated_by_engine():
    df = make_m5(GOLDEN_OPENS, GOLDEN_HIGHS, GOLDEN_LOWS, GOLDEN_CLOSES)
    columns_before = list(df.columns)
    run_backtest(df)
    assert list(df.columns) == columns_before
    assert "setup" not in df.columns
    assert "resistance" not in df.columns


def test_setup_with_incomplete_support_is_never_armed():
    """A swing HIGH can confirm while no swing LOW has, so `setup` fires with
    support still NaN -> sl=nan, tp=nan. Every NaN comparison is False, so
    `low <= sl` and `high >= tp` can never fire: the trade would be armed,
    filled, and then carried to the end of the data, booking the entire drift
    as one un-exitable win. Sliced 2025-03-24 onward, the real histdata frame
    did exactly that — 1 trade, +$1,016, exit_reason OPEN."""
    # Rising staircase: swing highs confirm, no swing low ever does.
    n = 40
    close = np.linspace(100.0, 130.0, n)
    df = pd.DataFrame(
        {"open": close, "high": close + 0.5, "low": close - 0.5, "close": close},
        index=pd.date_range("2025-01-01", periods=n, freq="5min", name="time"),
    )
    df.loc[df.index[10], ["high", "close"]] = [140.0, 139.0]  # a swing high
    df.loc[df.index[11], ["high", "close"]] = [120.0, 119.0]

    events = []
    trades = run_backtest(df, 2, 2, 60, 0.01, on_event=events.append)

    armed = [e for e in events if e["event"] == "setup_detected"]
    for e in armed:
        assert np.isfinite(e["sl"]) and np.isfinite(e["tp"]), e
    for t in trades:
        assert np.isfinite(t["sl"]) and np.isfinite(t["tp"]), t
    skipped = [e for e in events if e.get("reason") == "incomplete_levels"]
    for e in skipped:
        assert not np.isfinite(e["sl"])


# -- session filter and time stop --------------------------------------------


def _session_frame():
    """36 hourly-ish M5 bars spanning two UTC days, rising into a breakout."""
    n = 400
    idx = pd.date_range("2025-01-01 00:00", periods=n, freq="5min", name="time")
    close = 100 + np.sin(np.arange(n) / 7) * 2 + np.arange(n) * 0.02
    return pd.DataFrame(
        {"open": close, "high": close + 0.3, "low": close - 0.3, "close": close},
        index=idx,
    )


def test_session_filter_only_suppresses_ACTING_not_the_levels():
    """The filter must decide when to trade, never what the market did. If it
    masked the frame instead, a swing confirmed at 07:55 would vanish for the
    08:00 bar that should trade it."""
    df = _session_frame()
    full = run_backtest(df, 2, 2, 60, 0.01)
    win = run_backtest(df, 2, 2, 60, 0.01, session_hours=(8, 21))

    assert len(win) <= len(full)
    for t in win:
        assert 8 <= t["entry_time"].hour < 21, t["entry_time"]
    # Entries inside the window must price identically to the unfiltered run —
    # same levels, so the same trade, not a recomputed one.
    by_time = {t["entry_time"]: t for t in full}
    for t in win:
        if t["entry_time"] in by_time:
            assert t["sl"] == pytest.approx(by_time[t["entry_time"]]["sl"])


def test_session_filter_can_wrap_midnight():
    df = _session_frame()
    t = run_backtest(df, 2, 2, 60, 0.01, session_hours=(21, 8))
    for x in t:
        assert x["entry_time"].hour >= 21 or x["entry_time"].hour < 8


def test_time_stop_closes_a_stalled_trade_and_frees_the_slot():
    """Holds run 6.7h median and 10 days at worst on real data, so one trade
    can occupy the single slot across whole sessions."""
    df = _session_frame()
    slow = run_backtest(df, 2, 2, 60, 0.01)
    fast = run_backtest(df, 2, 2, 60, 0.01, max_hold_bars=12)

    assert len(fast) >= len(slow)  # freeing the slot admits more trades
    for t in fast:
        assert t["exit_idx"] - t["entry_idx"] <= 12
    assert any(t["exit_reason"] == "TIME" for t in fast)


def test_sl_and_tp_still_beat_the_time_stop_on_the_same_bar():
    """A bar that touches a level resolves AT that level, however long the
    trade has run — the time stop must not steal an exit from SL or TP."""
    df = _session_frame()
    for t in run_backtest(df, 2, 2, 60, 0.01, max_hold_bars=1):
        if t["exit_reason"] == "SL":
            assert t["exit_price"] == pytest.approx(t["sl"])
        elif t["exit_reason"] == "TP":
            assert t["exit_price"] == pytest.approx(t["tp"])


def test_neither_filter_changes_anything_when_unset():
    df = _session_frame()
    a = run_backtest(df, 2, 2, 60, 0.01)
    b = run_backtest(df, 2, 2, 60, 0.01, session_hours=None, max_hold_bars=None)
    assert [x["entry_time"] for x in a] == [x["entry_time"] for x in b]
    assert [x["exit_price"] for x in a] == [x["exit_price"] for x in b]


# ---------------------------------------------------------------------------
# Strategy variant seam (2026-08-28) — candle_reversal is a TEST strategy.
# Default variant="breakout" must stay byte-identical to the pre-seam engine.
# ---------------------------------------------------------------------------

def _reversal_frame():
    """Bars engineered so a green-after-red candle reversal at idx 4 arms a
    Buy Stop at its high. idx3 red (close 10.0 < open 10.4), idx4 green
    (close 10.9 > open 10.2), high 11.0 -> entry 11.0, sl 9.9 (its low).
    """
    opens = [10.0, 10.1, 10.3, 10.4, 10.2, 10.0, 10.5, 11.2]
    highs = [10.2, 10.3, 10.5, 10.4, 11.0, 10.8, 11.1, 11.3]
    lows = [9.9, 10.0, 10.2, 10.0, 9.9, 9.8, 10.4, 11.0]
    closes = [10.1, 10.2, 10.4, 10.0, 10.9, 10.1, 11.0, 11.2]
    return make_m5(opens, highs, lows, closes)


def test_default_variant_is_breakout_byte_identical():
    """variant defaults to 'breakout' — the pre-existing engine path unchanged."""
    df = make_m5(GOLDEN_OPENS, GOLDEN_HIGHS, GOLDEN_LOWS, GOLDEN_CLOSES)
    a = run_backtest(df)
    b = run_backtest(df, variant="breakout")
    assert a == b  # identical trade records


def test_candle_reversal_variant_arms_from_the_signal_candle():
    """The candle variant's entry/SL come from the signal candle's wicks, NOT
    swing S/R. idx4 green after idx3 red -> entry=11.0 (high), sl=9.9 (low)."""
    df = _reversal_frame()
    trades = run_backtest(df, variant="candle_reversal")
    assert len(trades) >= 1
    t = trades[0]
    assert t["entry"] == pytest.approx(11.0)   # top of the upper wick
    assert t["sl"] == pytest.approx(9.9)       # below the bottom wick
    # rr_multiple=1.0 (default) -> tp = entry + (entry - sl) = 11.0 + 1.1
    assert t["tp"] == pytest.approx(12.1)


def test_candle_reversal_rr_multiple_scales_the_target():
    df = _reversal_frame()
    t = run_backtest(df, variant="candle_reversal", rr_multiple=2.5)[0]
    # entry - sl = 11.0 - 9.9 = 1.1; tp = 11.0 + 2.5*1.1
    assert t["tp"] == pytest.approx(11.0 + 2.5 * (11.0 - 9.9))


def test_candle_reversal_rejects_short_direction():
    df = _reversal_frame()
    with pytest.raises(ValueError, match="long"):
        run_backtest(df, variant="candle_reversal", direction="short")


def test_candle_reversal_does_not_need_swing_columns():
    """The candle variant never computes swings/levels — it must work on a
    frame too short for fractal confirmation (which would NaN the breakout
    path's levels). Fill needs a later bar reaching the entry high (idx6:
    high 11.1 >= 11.0)."""
    df = _reversal_frame().iloc[:7]
    trades = run_backtest(df, variant="candle_reversal")
    # idx4 fires regardless of any swing needing 2 right-confirming bars
    assert any(t["entry"] == pytest.approx(11.0) for t in trades)


def test_setup_override_replaces_the_signal():
    """setup_override (research seam) swaps the trigger while the engine runs
    identically — a coin-flip setup must produce trades that differ from the
    pattern's, proving the override is actually consumed."""
    df = _reversal_frame()
    pattern = run_backtest(df, variant="candle_reversal")
    # force a signal on a bar the pattern would NOT fire on (idx2, flat-ish)
    override = pd.Series([False] * len(df), index=df.index)
    override.iloc[2] = True
    forced = run_backtest(df, variant="candle_reversal", setup_override=override)
    assert len(forced) >= 1
    assert forced[0]["entry_time"] != pattern[0]["entry_time"]


def test_setup_override_rejects_length_mismatch():
    df = _reversal_frame()
    with pytest.raises(ValueError, match="setup_override has"):
        run_backtest(
            df, variant="candle_reversal",
            setup_override=pd.Series([True, False], index=df.index[:2]),
        )
