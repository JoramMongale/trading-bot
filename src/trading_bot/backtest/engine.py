"""Bar-based backtest event loop over the shared strategy module (SAFE-01).

Pass A computes all signals vectorized by chaining the SAME pure-Python
strategy functions the live bot will use:
    support_resistance(detect_swings(df, left, right), lookback) -> detect_setups

Pass B is a per-bar event loop that matches fills and exits against subsequent
bars, emitting one trade record per completed trade. Conventions (verified in
RESEARCH.md RQ2):
  - a signal at bar t arms a stop order; the fill search starts at bar t+1
  - fill when the bar reaches the entry, at the open if it gapped past it
    (long: high >= entry, fill max(entry, open); short: the mirror)
  - a bar that fills a trade may not also arm a new setup
  - one active trade at a time; new setups during an open trade are skipped
  - intrabar exits are pessimistic: SL is checked before TP
  - a trade still open at the last bar closes at the last close (OPEN)
  - a signal on the final bar arms a pending order that never fills -> no record

A trade record is appended EXACTLY ONCE, at exit. If an ``on_event`` callback
is provided, it receives one dict per decision (setup_detected, setup_skipped,
order_filled, trade_closed) for SAFE-02 decision logging.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Optional

from trading_bot.strategy.candle_reversal import candle_levels, detect_candle_reversal
from trading_bot.strategy.filters import atr_below_median, body_confirms, htf_trend
from trading_bot.strategy.levels import support_resistance
from trading_bot.strategy.signals import detect_setups
from trading_bot.strategy.swings import detect_swings


def side_sgn(side: str) -> float:
    """+1 for a long trade, -1 for a short one (mirror generality)."""
    return 1.0 if side == "long" else -1.0


def run_backtest(
    df,
    fractal_left: int = 2,
    fractal_right: int = 2,
    sr_lookback: int = 60,
    sl_buffer: float = 0.01,
    rr_multiple: float = 1.0,
    session_hours: Optional[tuple[int, int]] = None,
    max_hold_bars: Optional[int] = None,
    tp_from_fill: bool = False,
    direction: str = "long",
    atr_median_bars: Optional[int] = None,
    atr_period: int = 14,
    htf_sma: Optional[int] = None,
    htf_rule: str = "1h",
    require_body: bool = False,
    max_concurrent: int = 1,
    on_event: Optional[Callable[[dict], None]] = None,
    setup_veto: Optional[Callable[[pd.Series, float, float, float], Optional[str]]] = None,
    variant: str = "breakout",
    setup_override: Optional[pd.Series] = None,
) -> list[dict[str, Any]]:
    """Run the strategy over ``df`` (OHLC, datetime index) and return trades.

    Each trade record has:
        entry_time, entry, sl, tp, exit_time, exit_price, exit_reason,
        entry_idx, exit_idx, direction
    ``exit_reason`` is ``"SL"``, ``"TP"``, ``"TIME"`` or ``"OPEN"``.

    ``direction`` selects the long breakout (default, unchanged behaviour), its
    strict short mirror, or ``"both"``. The loop below is sign-generalized
    rather than duplicated: ``sgn`` is +1 for longs and -1 for shorts, and
    every price comparison is written as ``sgn * price >= sgn * level`` so one
    body of code expresses every side. In a ``"both"`` run the union of the two
    setups competes for the SAME single-slot loop -- a bar can fire at most one
    side, so the union is unambiguous -- and the first signal to fire claims
    the slot until its trade closes. ``"both"`` is rejected for the
    direction-scoped options (candle_reversal variant, require_body, htf_sma,
    setup_override) because each describes one side only. Duplicating the loop
    would let the two sides drift apart, and the whole value of the short side
    is that it is EXACTLY the mirror -- it measures whether the setup's
    negative edge is symmetric, which only means something if nothing else
    differs.

    ``rr_multiple`` sets the target distance as a multiple of the stop
    distance: ``tp = entry + rr_multiple * (entry - sl)``. The default of 1.0
    reproduces the historical 1:1 behaviour exactly (pinned by golden tests);
    the 1:1 default is the only configuration that has been measured live.
    Higher ratios move the target further away, which is hit less often -- the
    measured win rate and net R both fall (see the TP-from-fill study) -- so a
    non-1.0 ratio should be applied live only after a measured decision, never
    as an experiment on real money.

    ``max_concurrent`` is how many positions (open + armed) may exist at once.
    The default of 1 reproduces the original single-slot loop exactly, and that
    equality is pinned by a golden-trades test. Raising it is NOT free: N
    concurrent trades at the same fractional risk put N times the capital at
    stake, all in one direction on correlated instruments, so a single sharp
    reversal takes every stop together. Measure drawdown, not just R per trade.

    ``direction="both"`` single-slot competition IS implemented (added
    2026-09-09 for BACKTEST measurement of a both-direction scalp variant,
    quick task 20260909-gold-both-scalper); it is deliberately NOT used by the
    live engine, which stays long-only breakout. Two directions competing for
    one slot is a system with its own selection bias -- that is exactly what
    the measurement exists to expose.

    ``setup_veto`` is the AI-layer seam (plan 03-01). Called as
    ``setup_veto(bar, entry, sl, tp)`` exactly when a setup is otherwise about
    to be armed; a returned reason string skips the arm and emits
    ``setup_skipped reason=<reason>``. ``None`` (default) leaves the loop
    byte-identical, pinned by the golden tests. The AI backtester uses it to
    gate every setup through the deterministic AI proposal gate before the
    trade is armed — the backtest half of "AI proposes, deterministic code
    disposes".

    The optional filters (``atr_median_bars``, ``htf_sma``, ``require_body``)
    all default off and are NOT wired into the live engine, exactly as
    ``session_hours`` and ``max_hold_bars`` are not. They exist to be measured.
    Each one narrows the sample, which makes a flattering backtest easier to
    produce -- treat any improvement as unproven until it survives out-of-sample.

    ``setup_override`` (research only) replaces the computed setup column with a
    caller-supplied boolean Series (aligned to ``df.index``) BEFORE the optional
    filters run. It exists for falsification: a coin-flip trigger through the
    same engine measures whether an apparent edge is predictive alpha or just
    the engine's fill/slot mechanics. Default None = unchanged behaviour.
    """
    if direction not in ("long", "short", "both"):
        raise ValueError(
            f"direction={direction!r} must be 'long', 'short' or 'both'")
    if max_concurrent < 1:
        raise ValueError(f"max_concurrent={max_concurrent} must be >= 1")
    if variant not in ("breakout", "candle_reversal"):
        raise ValueError(
            f"variant={variant!r} must be 'breakout' or 'candle_reversal'")
    if variant == "candle_reversal" and direction != "long":
        # The candle-reversal module currently describes the BUY side of the
        # user's spec only (bullish candle after bearish). Silently mirroring a
        # half-specified signal would fabricate an unmeasured strategy — refuse.
        raise ValueError(
            f"variant='candle_reversal' supports direction='long' only, got "
            f"{direction!r}")
    if direction == "both":
        # The body and HTF filters are direction-scoped (they take a single
        # direction), and a bare boolean setup_override carries no side, so a
        # "both" run with any of them would gate or trigger incoherently.
        # session_hours, max_hold_bars, tp_from_fill, rr_multiple,
        # atr_median_bars and max_concurrent stay legal with "both" -- all are
        # direction-agnostic.
        if variant != "breakout":
            raise ValueError(
                f"direction='both' is only defined for variant='breakout', "
                f"got variant={variant!r}")
        if require_body:
            raise ValueError(
                "direction='both' cannot be combined with require_body=True: "
                "the body filter is direction-scoped and takes one direction")
        if htf_sma is not None:
            raise ValueError(
                "direction='both' cannot be combined with htf_sma: the HTF "
                "filter is direction-scoped and takes one direction")
        if setup_override is not None:
            raise ValueError(
                "direction='both' cannot be combined with setup_override: a "
                "bare boolean override carries no side")

    df = df.copy()  # pandas 3.0 Copy-on-Write: never mutate the caller's frame
    if variant == "candle_reversal":
        # Test strategy: the two-candle reversal. Entry/SL come from the signal
        # candle's own high/low (see candle_levels), not swing S/R levels.
        df = detect_candle_reversal(df)
    else:
        df = support_resistance(detect_swings(df, fractal_left, fractal_right), sr_lookback)
        if direction == "both":
            # Union of the two strict mirrors over the SAME level frame. A bar
            # cannot fire both sides (a close cannot sit above resistance AND
            # below support while both levels are finite), so setup_dir is
            # unambiguous wherever setup is True. detect_setups copies, so df
            # keeps its levels for the loop below.
            long_sig = detect_setups(df, direction="long")["setup"]
            short_sig = detect_setups(df, direction="short")["setup"]
            df["setup"] = long_sig | short_sig
            df["setup_dir"] = ""
            df.loc[long_sig, "setup_dir"] = "long"
            df.loc[short_sig, "setup_dir"] = "short"
        else:
            df = detect_setups(df, direction=direction)

    # Research falsification seam: a caller-supplied setup column (e.g. random
    # coin flips) replaces the signal BEFORE any filter, so the engine runs
    # identically with only the trigger changed.
    if setup_override is not None:
        if len(setup_override) != len(df):
            raise ValueError(
                f"setup_override has {len(setup_override)} entries but the frame "
                f"has {len(df)} bars")
        df["setup"] = setup_override.astype(bool).to_numpy()

    # Optional filters, applied AFTER the levels and signal are built, for the
    # same reason the session filter is: masking the frame earlier would tear
    # holes in the swing and lookback windows. A filter decides when to ACT, it
    # never edits what the market did.
    if atr_median_bars is not None:
        df["setup"] = df["setup"] & atr_below_median(df, atr_period, atr_median_bars)
    if htf_sma is not None:
        df["setup"] = df["setup"] & htf_trend(df, htf_sma, htf_rule, direction)
    if require_body:
        df["setup"] = df["setup"] & body_confirms(df, direction)

    # Session filter, applied AFTER the levels are built. Masking the frame
    # instead would tear holes in the swing and lookback windows, so a level
    # confirmed at 07:55 would vanish for the 08:00 bar that should trade it —
    # the filter must decide when to ACT, never what the market did.
    # Half-open [start, end) on the bar index's own clock, which for the broker
    # feed is UTC.
    if session_hours is not None:
        start, end = session_hours
        hours = df.index.hour
        inside = (hours >= start) & (hours < end) if start <= end else (
            (hours >= start) | (hours < end))
        df["setup"] = df["setup"] & inside

    trades: list[dict[str, Any]] = []
    open_trades: list[dict[str, Any]] = []      # newest last
    pendings: list[dict[str, float]] = []       # armed stop orders
    last_idx = len(df) - 1

    def emit(event: str, **fields: Any) -> None:
        if on_event is not None:
            on_event({"event": event, **fields})

    def levels_at(bar, side: str) -> tuple[float, float]:
        """(reference entry, stop) for this bar, in trade terms.

        A long breaks out ABOVE resistance and stops below support; a short
        breaks down BELOW support and stops above resistance -- the "support
        becomes resistance" symmetry. The buffer always sits on the far side of
        the stop level, which is ``-`` for a long and ``+`` for a short.

        The candle-reversal variant replaces both sources with the signal
        candle itself: entry at the wick top, stop below the wick bottom.
        """
        if variant == "candle_reversal":
            return candle_levels(bar)
        if side == "long":
            return float(bar.resistance), float(bar.support - sl_buffer)
        return float(bar.support), float(bar.resistance + sl_buffer)

    def close_trade(trade: dict, exit_idx: int, exit_price: float, reason: str) -> None:
        trade.update(
            exit_time=df.index[exit_idx],
            exit_idx=exit_idx,
            exit_price=float(exit_price),
            exit_reason=reason,
        )
        trades.append(trade)
        emit(
            "trade_closed",
            entry_time=trade["entry_time"],
            entry=trade["entry"],
            sl=trade["sl"],
            tp=trade["tp"],
            exit_time=trade["exit_time"],
            exit_price=trade["exit_price"],
            exit_reason=reason,
        )

    for t in range(len(df)):
        bar = df.iloc[t]  # pandas 3.0: read-only copy, never mutate

        # Slot accounting is taken at the START of the bar, before anything
        # closes or fills. That is what makes max_concurrent=1 reproduce the
        # original single-slot loop EXACTLY: there, a bar holding an open trade
        # or a pending order returned early and could never arm a new setup,
        # even if that trade closed or that order filled on the very same bar.
        slots_used_at_open = len(open_trades) + len(pendings)

        # 1) Manage open trades first. Same-bar ordering: SL before TP, and
        #    both before the time stop -- a bar that touches a level resolves at
        #    that level, not at its close, however long the trade has run.
        #    Each trade's own side sets its extremes: for a long the adverse
        #    extreme is the low and the favourable one is the high; for a short
        #    they swap. Every comparison is written once, in the form
        #    `sgn * price >= sgn * level`, which reads identically for both.
        for trade in list(open_trades):
            sgn = side_sgn(trade["direction"])
            adverse = float(bar.low if sgn > 0 else bar.high)
            favourable = float(bar.high if sgn > 0 else bar.low)
            if sgn * adverse <= sgn * trade["sl"]:
                close_trade(trade, t, trade["sl"], "SL")
                open_trades.remove(trade)
            elif sgn * favourable >= sgn * trade["tp"]:
                close_trade(trade, t, trade["tp"], "TP")
                open_trades.remove(trade)
            elif (
                max_hold_bars is not None
                and t - trade["entry_idx"] >= max_hold_bars
            ):
                # Time stop: give up on a trade that has gone nowhere and free
                # the slot for a fresher setup. Exits at the close, the only
                # price actually available when the decision is time-based.
                close_trade(trade, t, float(bar.close), "TIME")
                open_trades.remove(trade)

        # 2) Fill armed orders (armed on the signal bar, fills t+1 onwards).
        #    Each pending carries its own side, so mixed books fill correctly.
        for order in list(pendings):
            if order["armed_idx"] == t:
                continue  # never fill on the bar that armed it
            sgn = side_sgn(order["side"])
            adverse = float(bar.low if sgn > 0 else bar.high)
            favourable = float(bar.high if sgn > 0 else bar.low)
            if sgn * favourable >= sgn * order["entry"]:
                # Gap-open fills at the open, which is the worse price in
                # both directions: above the buy level, or below the sell one.
                fill = float(max(order["entry"], bar.open) if sgn > 0
                             else min(order["entry"], bar.open))
                # The strategy's levels imply exactly 1:1, but the fill lands
                # ABOVE the reference entry (the setup fires on a close above
                # resistance), so a TP measured from the reference is closer
                # than 1R while the stop is further than 1R. Winners therefore
                # average 0.86R while losers pay the full -0.99R, and that
                # asymmetry costs more per trade than the entire measured edge.
                # tp_from_fill re-anchors the target on what was actually paid,
                # restoring a true 1:1 -- at the cost of a target that is
                # further away and so hit less often.
                tp_here = (fill + (fill - order["sl"])) if tp_from_fill else order["tp"]
                trade = {
                    "entry_time": bar.name,
                    "entry_idx": t,
                    "direction": order["side"],
                    "entry": fill,
                    "sl": order["sl"],
                    "tp": tp_here,
                    "exit_time": None,
                    "exit_idx": None,
                    "exit_price": None,
                    "exit_reason": None,
                }
                open_trades.append(trade)
                emit("order_filled", bar=bar.name, entry=trade["entry"],
                     sl=trade["sl"], tp=trade["tp"])
                pendings.remove(order)

        # 3) New setup -> arm an entry with rr_multiple R:R. The default
        # rr_multiple=1.0 is the historical exact 1:1 (STRAT-03); a higher
        # value scales the target further away and is configurable via
        # [strategy] rr_multiple.
        if bool(bar.setup):
            side = direction if direction != "both" else str(df["setup_dir"].iloc[t])
            entry, sl = levels_at(bar, side)
            tp = entry + rr_multiple * (entry - sl)
            sgn = side_sgn(side)
            if slots_used_at_open >= max_concurrent:
                # Reasons kept distinct because they mean different things: a
                # position is exposed to the market, an unfilled order is not.
                reason = "open_trade" if open_trades else "pending_order"
                emit("setup_skipped", bar=bar.name, reason=reason,
                     entry=entry, sl=sl, tp=tp)
            elif not (math.isfinite(sl) and math.isfinite(tp)
                      and sgn * entry > sgn * sl):
                # `setup` only reads one level, so it can fire while the other
                # is still NaN (no confirmed swing of that type in the window
                # yet). That gives sl=nan/tp=nan, and since every NaN comparison
                # is False the exit tests above could never fire -- the trade
                # would be armed, filled, and then held to the end of the data,
                # booking the whole drift as one un-exitable win. Never arm it.
                emit("setup_skipped", bar=bar.name, reason="incomplete_levels",
                     entry=entry, sl=sl, tp=tp)
            else:
                # AI-layer seam (plan 03-01): a non-None setup_veto reason skips
                # the arm. The veto sees the BAR (all OHLC + levels/setups
                # columns) plus the deterministic entry/sl/tp, and returns a
                # reason string or None. This is the only hook the AI backtester
                # needs to gate every setup without duplicating this loop.
                veto = setup_veto(bar, entry, sl, tp) if setup_veto else None
                if veto is not None:
                    emit("setup_skipped", bar=bar.name, reason=veto,
                         entry=entry, sl=sl, tp=tp)
                    continue
                pendings.append({"entry": entry, "sl": sl, "tp": tp,
                                 "armed_idx": t, "side": side})
                emit("setup_detected", bar=bar.name, entry=entry, sl=sl, tp=tp)

    # Close any trades still open at end of data at the last close (flagged).
    for trade in list(open_trades):
        close_trade(trade, last_idx, float(df["close"].iloc[last_idx]), "OPEN")
        open_trades.remove(trade)

    return trades
