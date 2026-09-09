"""Liquidity-sweep / session open-range detection — pure, research strategy.

Pure pandas/numpy — no I/O, no config, no broker imports (SAFE-01). This is a
session-based strategy that works on DAILY reference ranges, not the swing-based
continuous model of ``signals.py``, so it has its own detection functions and a
session backtest driver (scripts/backtest_liquidity_sweep.py).

See .planning/quick/20260828-liquidity-sweep-or/SPEC.md for the full spec.

Core idea: price "sweeping" the High/Low of an earlier session range (e.g. the
Asian range) during a later window (e.g. the London open) either expands in the
swept direction (breakout-continuation) or reverses back inside the range
(failed sweep). The sweep event is the signal.

No-lookahead contract (identical to the rest of the strategy package):
  - the reference range uses ONLY bars in its own window, which closes before
    the sweep window opens
  - a sweep at bar t is acted on at the close of bar t; entry is the NEXT bar
    open (matching live semantics)
  - the failed-sweep close-back test reads only bars up to the decision bar
"""

import pandas as pd


def session_range(df: pd.DataFrame, start: int, end: int) -> pd.DataFrame:
    """Per-trading-day High/Low of bars whose UTC hour is in [start, end).

    Adds per-bar ``range_high``/``range_low`` columns holding the value of the
    trading DAY's reference window (forward-filled across the day so every bar
    after the window closes can read it), plus ``range_ok`` (True on bars of a
    day whose reference window had at least one bar — a data gap or market
    closure means no range and no trade that day).

    No lookahead: the range for a day is computed from that day's window bars
    only, and is only usable once the window has fully closed (bars at/after
    ``end`` hours). Bars before ``end`` on the same day get NaN so they cannot
    act on a range that is still forming.
    """
    out = df.copy()
    hours = out.index.hour
    date = out.index.normalize()

    # Bars inside the reference window, per day.
    in_win = (hours >= start) & (hours < end)
    daily_high = out.loc[in_win, "high"].groupby(date[in_win]).max()
    daily_low = out.loc[in_win, "low"].groupby(date[in_win]).min()

    # Align back onto every bar of the same day.
    out["_day"] = date
    out["range_high"] = out["_day"].map(daily_high)
    out["range_low"] = out["_day"].map(daily_low)
    out["range_ok"] = out["_day"].isin(daily_high.index)

    # Only usable once the reference window has closed.
    after_win = hours >= end
    out.loc[~after_win, ["range_high", "range_low"]] = float("nan")
    out.loc[~after_win, "range_ok"] = False

    return out.drop(columns=["_day"])


def detect_sweeps(
    df: pd.DataFrame,
    kind: str,
    sweep_start: int = 7,
    sweep_end: int = 9,
) -> pd.DataFrame:
    """Mark bars in the sweep window that poke the session range boundary.

    kind="breakout":  a LONG setup fires on an UP-sweep (high > range_high);
                      a SHORT setup fires on a DN-sweep (low < range_low).
                      setup[t] is True on the bar that pokes the boundary.
    kind="failed":    the reversal flavour. An UP-sweep must then FAIL — a later
                      bar in the same window closes back below range_high. The
                      SHORT setup fires on that failing close bar. A DN-sweep
                      that closes back above range_low fires the LONG. A sweep
                      that never fails inside the window produces no trade.

    Adds: setup (bool), sweep_dir (+1 up / -1 down / 0) and the reference levels
    are already on the frame from session_range(). The input is never mutated.

    Only bars with a valid range (range_ok) and within [sweep_start, sweep_end)
    hours can fire. Bars before the range is usable are excluded by range_ok.
    """
    if kind not in ("breakout", "failed"):
        raise ValueError(f"kind={kind!r} must be 'breakout' or 'failed'")

    out = df.copy()
    hours = out.index.hour
    close = out["close"]
    high = out["high"]
    low = out["low"]
    r_high = out["range_high"]
    r_low = out["range_low"]
    in_sweep = (hours >= sweep_start) & (hours < sweep_end) & out["range_ok"]

    up_sweep = in_sweep & (high > r_high)
    dn_sweep = in_sweep & (low < r_low)
    out["sweep_dir"] = 0
    out.loc[up_sweep, "sweep_dir"] = 1
    out.loc[dn_sweep, "sweep_dir"] = -1

    if kind == "breakout":
        # Long on an up-sweep, short on a down-sweep, one setup column.
        out["setup"] = up_sweep | dn_sweep
        out["setup_dir"] = out["sweep_dir"]
    else:
        # Failed sweep: an up-sweep bar exists in the window, then a LATER bar
        # in the same window CLOSES back below range_high -> the breakout
        # failed, SHORT setup on the failing close. Mirror: a dn-sweep that
        # later closes back above range_low -> LONG. A sweep that never fails
        # inside the window produces no trade. Sequential per-day pass: whether
        # a poke has happened is state that carries across bars of one day.
        setup = pd.Series(False, index=out.index)
        setup_dir = pd.Series(0, index=out.index)
        for day, day_rows in out.groupby(out.index.normalize()):
            saw_up = False
            saw_dn = False
            for ts in day_rows.index:
                if not bool(in_sweep.loc[ts]):
                    continue  # outside the window: no detection, state frozen
                if pd.notna(r_high.loc[ts]) and high.loc[ts] > r_high.loc[ts]:
                    saw_up = True
                elif pd.notna(r_low.loc[ts]) and low.loc[ts] < r_low.loc[ts]:
                    saw_dn = True
                # A failing close-back (only after a poke of the same boundary).
                if saw_up and close.loc[ts] < r_high.loc[ts]:
                    setup.loc[ts] = True
                    setup_dir.loc[ts] = -1  # short the failed up-break
                    saw_up = False  # one failure per poke
                elif saw_dn and close.loc[ts] > r_low.loc[ts]:
                    setup.loc[ts] = True
                    setup_dir.loc[ts] = 1  # long the failed down-break
                    saw_dn = False
        out["setup"] = setup
        out["setup_dir"] = setup_dir

    return out
