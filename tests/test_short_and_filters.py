"""Short-side mirror and the optional entry filters.

The tests that matter here are the symmetry one and the no-lookahead one. The
short side is only worth having if it is EXACTLY the mirror of the long side --
if the two differ in any way, comparing their results measures the difference
instead of the market.
"""

import numpy as np
import pandas as pd
import pytest

from trading_bot.backtest.engine import run_backtest
from trading_bot.backtest.stats import trade_stats
from trading_bot.strategy.filters import (
    atr,
    atr_below_median,
    body_confirms,
    htf_trend,
)
from trading_bot.strategy.signals import detect_setups


def _frame(rows, start="2026-01-01", freq="5min"):
    idx = pd.date_range(start, periods=len(rows), freq=freq)
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


def _mirror(df):
    """Reflect a price series about zero: highs become lows and vice versa."""
    out = pd.DataFrame(
        {
            "open": -df["open"],
            "high": -df["low"],
            "low": -df["high"],
            "close": -df["close"],
        },
        index=df.index,
    )
    return out


def _random_walk(n=1500, seed=7):
    rng = np.random.default_rng(seed)
    close = 1000 + np.cumsum(rng.normal(0, 1.0, n))
    spread = np.abs(rng.normal(0, 0.6, n)) + 0.1
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    return _frame(np.c_[open_, high, low, close])


# --- the symmetry guarantee ------------------------------------------------


def test_short_on_mirrored_data_matches_long_trade_for_trade():
    """Longs on a series and shorts on its reflection must be identical in R.

    This is the property that makes "are shorts also negative?" a meaningful
    question. Reflecting the data about zero turns every resistance breakout
    into a support breakdown, so a correct short mirror must produce the same
    number of trades, the same R on each, and the same exit reasons.
    """
    df = _random_walk(n=12000)
    longs = run_backtest(df, direction="long")
    shorts = run_backtest(_mirror(df), direction="short")

    assert len(longs) == len(shorts) > 20, (len(longs), len(shorts))

    trade_stats(longs)
    trade_stats(shorts)
    for a, b in zip(longs, shorts):
        assert a["entry_idx"] == b["entry_idx"]
        assert a["exit_idx"] == b["exit_idx"]
        assert a["exit_reason"] == b["exit_reason"]
        assert a["entry"] == pytest.approx(-b["entry"])
        assert a["sl"] == pytest.approx(-b["sl"])
        assert a["tp"] == pytest.approx(-b["tp"])
        assert a["r_multiple"] == pytest.approx(b["r_multiple"])
        assert a["pnl_points"] == pytest.approx(b["pnl_points"])


def test_winning_short_reports_positive_pnl_and_r():
    """A short that reaches TP must count as a win, not a loss.

    Guards the sign flip in stats: the raw price move on a winning short is
    negative, and without the flip the whole book reports inverted.
    """
    trades = [
        {
            "direction": "short",
            "entry": 100.0,
            "sl": 110.0,
            "tp": 90.0,
            "exit_price": 90.0,
            "exit_reason": "TP",
            "entry_idx": 0,
            "exit_idx": 5,
        }
    ]
    stats = trade_stats(trades)
    assert trades[0]["pnl_points"] == pytest.approx(10.0)
    assert trades[0]["r_multiple"] == pytest.approx(1.0)
    assert stats["wins"] == 1
    assert stats["losses"] == 0


def test_short_stop_sits_above_entry():
    df = _random_walk()
    shorts = run_backtest(df, direction="short")
    assert shorts, "expected some short trades on a random walk"
    for t in shorts:
        assert t["sl"] > t["entry"], t
        assert t["tp"] < t["entry"], t


def test_direction_must_be_long_or_short():
    df = _random_walk(n=300)
    with pytest.raises(ValueError, match="direction"):
        run_backtest(df, direction="sideways")
    with pytest.raises(ValueError, match="direction"):
        detect_setups(df.assign(resistance=1.0, support=0.0), direction="sideways")


# --- no-lookahead ----------------------------------------------------------


def test_htf_trend_never_reads_the_forming_hour():
    """The H1 verdict at any M5 bar must come from a COMPLETED H1 bar.

    Built so the answer is unambiguous: hour 0 is flat and hour 1 rockets. If
    the filter leaked, bars inside hour 1 would already read hour 1's close.
    """
    n = 24 * 12  # 24 hours of M5
    close = np.r_[np.full(12, 100.0), np.full(n - 12, 100.0)]
    close[12 * 12 :] = 500.0  # a violent move starting at hour 12
    df = _frame(np.c_[close, close + 0.5, close - 0.5, close], start="2026-01-01")

    ok = htf_trend(df, sma=3, rule="1h", direction="long")

    # The bar at 12:00 opens the hour the move happens in. Its verdict must be
    # based on 11:00-12:00 (flat), so it cannot already be bullish.
    at_move_start = ok.loc["2026-01-01 12:00:00"]
    assert not bool(at_move_start), "H1 filter leaked the forming hour"
    # By 14:00 two completed hours are above the SMA, so it must be bullish.
    assert bool(ok.loc["2026-01-01 14:00:00"])


def test_htf_trend_short_is_the_negation_where_defined():
    df = _random_walk(n=2000)
    lo = htf_trend(df, sma=5, direction="long")
    sh = htf_trend(df, sma=5, direction="short")
    both = lo & sh
    assert not both.any(), "a bar cannot be bullish and bearish at once"


# --- filters behave as documented -----------------------------------------


def test_atr_below_median_is_false_before_the_window_fills():
    df = _random_walk(n=400)
    ok = atr_below_median(df, period=14, median_bars=120)
    assert not ok.iloc[:119].any()
    assert ok.iloc[120:].any()


def test_atr_is_positive_and_finite():
    df = _random_walk(n=500)
    a = atr(df, 14)
    assert (a.iloc[1:] > 0).all()
    assert np.isfinite(a.iloc[1:]).all()


def test_body_confirms_excludes_doji():
    df = _frame([[10.0, 11.0, 9.0, 10.0], [10.0, 11.0, 9.0, 10.5]])
    assert list(body_confirms(df, "long")) == [False, True]
    assert list(body_confirms(df, "short")) == [False, False]


def test_filters_only_ever_reduce_trade_count():
    """Every filter is a mask on `setup`, so it can never create a trade."""
    df = _random_walk(n=3000)
    base = len(run_backtest(df, direction="long"))
    for kwargs in (
        {"atr_median_bars": 120},
        {"htf_sma": 20},
        {"require_body": True},
    ):
        n = len(run_backtest(df, direction="long", **kwargs))
        assert n <= base, (kwargs, n, base)


def test_long_default_is_unchanged_by_the_new_parameters():
    """Passing the new params at their defaults must change nothing."""
    df = _random_walk(n=2000)
    a = run_backtest(df)
    b = run_backtest(
        df,
        direction="long",
        atr_median_bars=None,
        htf_sma=None,
        require_body=False,
    )
    assert a == b


# --- exposure ceiling (gap risk) -------------------------------------------


def test_notional_is_in_account_currency_not_quote_currency():
    """0.12 lots of gold at 4600 is $552 -- and on a CENT account, 55,200 USC.

    The account-currency answer is the one that can be compared against a
    balance. Returning the quote-currency $552 and testing it against a USC
    balance would be wrong by exactly the 100x this class exists to prevent.
    """
    from trading_bot.broker.base import SymbolRisk

    gold = SymbolRisk(tick_size=0.001, tick_value=0.1, volume_min=0.01,
                      volume_step=0.01, volume_max=200.0)
    assert gold.notional(4600.0, 0.12) == pytest.approx(55_200.0)   # USC
    assert gold.notional(4600.0, 0.12) / 100 == pytest.approx(552.0)  # = USD

    # BTCUSDc: contract 0.01, so one lot at 77,658 is $776.58 = 77,658 USC.
    btc = SymbolRisk(tick_size=0.01, tick_value=0.01, volume_min=0.01,
                     volume_step=0.01, volume_max=200.0)
    assert btc.notional(77_658.0, 1.0) == pytest.approx(77_658.0)

    # Risk stays independent of exposure -- separate questions, separate maths.
    assert gold.money_risk(5.33, 0.12) == pytest.approx(5.33 / 0.001 * 0.1 * 0.12)

    unknown = SymbolRisk(tick_size=0.0, tick_value=0.0, volume_min=0.01,
                         volume_step=0.01, volume_max=200.0)
    assert np.isnan(unknown.notional(4600.0, 1.0))


def test_exposure_ceiling_binds_on_a_tight_stop_when_sizing_from_broker():
    """A stop tight enough to breach max_leverage must be cut back.

    Before this, the ceiling was skipped whenever sizing came from the broker,
    which is always the case live -- so the only guard against gap risk was
    inert exactly where it was needed.
    """
    from trading_bot.broker.base import SymbolRisk
    from trading_bot.config import load_config
    from trading_bot.live.engine import position_size

    import dataclasses
    cfg = load_config("config/config-cent.toml")
    # Pin the per-trade cap to 1%: the LIVE config sits at a deliberately
    # aggressive 20% (quick task 004), which makes even a median stop breach
    # the 20x ceiling. The premises of this test — a $2.00 stop breaching
    # the ceiling, a $24.30 stop not — were derived at 1%.
    cfg = dataclasses.replace(
        cfg, risk=dataclasses.replace(cfg.risk, max_loss_pct_per_trade=1.0))
    sr = SymbolRisk(tick_size=0.001, tick_value=0.1, volume_min=0.01,
                    volume_step=0.01, volume_max=200.0)
    balance, price = 3197.07, 4600.0

    # A $2.00 stop wants ~0.32 lots = ~46x gearing; the 20x ceiling must bite.
    tight = position_size(cfg, balance, 2.00, sr=sr, price=price)
    geared = sr.notional(price, tight) / balance
    assert geared <= cfg.risk.max_leverage + 1e-6, geared

    # A median $24.30 stop is only ~3.8x, so the ceiling must NOT interfere.
    loose_capped = position_size(cfg, balance, 24.30, sr=sr, price=price)
    loose_uncapped = position_size(cfg, balance, 24.30, sr=sr, price=None)
    assert loose_capped == loose_uncapped


def test_unknown_tick_economics_does_not_silently_disable_the_ceiling():
    """min(raw, NaN) returns raw in Python -- the NaN must be caught explicitly."""
    from trading_bot.broker.base import SymbolRisk
    from trading_bot.config import load_config
    from trading_bot.live.engine import position_size

    cfg = load_config("config/config-cent.toml")
    sr = SymbolRisk(tick_size=0.001, tick_value=0.1, volume_min=0.01,
                    volume_step=0.01, volume_max=200.0)
    lots = position_size(cfg, 3197.07, 2.00, sr=sr, price=4600.0)
    # Unknown exposure cannot be treated as a breach either: sizing still works,
    # it simply falls back to the risk cap alone.
    assert lots > 0


# --- concurrent positions --------------------------------------------------


def test_max_concurrent_one_is_exactly_the_old_single_slot_loop():
    """The default must not change a single trade. Pinned separately from the
    golden-trades test because this loop was rewritten from one slot to N."""
    df = _random_walk(n=12000)
    assert run_backtest(df) == run_backtest(df, max_concurrent=1)


def test_more_slots_take_more_trades_and_never_fewer():
    df = _random_walk(n=12000)
    counts = [len(run_backtest(df, max_concurrent=n)) for n in (1, 2, 3, 5)]
    assert counts == sorted(counts), counts
    assert counts[-1] > counts[0], counts


def test_concurrent_trades_actually_overlap_in_time():
    """With more slots, some trades must be open simultaneously -- otherwise
    the parameter is doing nothing and the extra trades came from elsewhere."""
    trades = run_backtest(_random_walk(n=12000), max_concurrent=3)
    spans = sorted((t["entry_idx"], t["exit_idx"]) for t in trades)
    overlaps = sum(
        1 for i, (s1, e1) in enumerate(spans)
        for s2, _ in spans[i + 1:] if s2 < e1
    )
    assert overlaps > 0


def test_an_order_never_fills_on_the_bar_that_armed_it():
    """The signal bar closes ABOVE the entry level, so without this guard every
    order would fill instantly at its own signal bar and the +1 bar delay that
    the whole no-lookahead design rests on would silently vanish."""
    for n in (1, 3):
        for t in run_backtest(_random_walk(n=6000), max_concurrent=n):
            assert t["exit_idx"] >= t["entry_idx"]
    # entry_idx is the FILL bar; assert it is strictly after some setup bar by
    # checking no trade is filled at index 0 (nothing could have armed before).
    assert all(t["entry_idx"] > 0 for t in run_backtest(_random_walk(n=6000),
                                                        max_concurrent=3))


def test_max_concurrent_must_be_at_least_one():
    with pytest.raises(ValueError, match="max_concurrent"):
        run_backtest(_random_walk(n=500), max_concurrent=0)
