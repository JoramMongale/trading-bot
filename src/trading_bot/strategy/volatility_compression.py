"""Volatility compression / expansion detection — pure, research strategy.

Pure pandas/numpy — no I/O, no config, no broker imports (SAFE-01). This is a
regime-change strategy: it waits for volatility to compress (a Bollinger
bandwidth squeeze) and then trades the first close OUTSIDE the band — the
presumed start of a directional expansion.

Spec (2026-08-28, see .planning/quick/20260828-volatility-compression/SPEC.md):

  BBW_t = (upper_t - lower_t) / SMA_t(N)              # normalised bandwidth
  squeeze_t = BBW_t below its K-period rolling percentile P
  trigger (while squeezed):
      close > upper  -> LONG setup
      close < lower  -> SHORT setup
  entry at the NEXT bar open; SL opposite band / mid SMA; TP = rr x risk.

No-lookahead contract (same as the whole strategy package):
  - every indicator at bar t uses only bars up to and including t
  - a trigger at bar t is acted on at the close of t; entry is the NEXT bar
    open (matching live semantics)
"""

import pandas as pd


def bollinger(df: pd.DataFrame, period: int = 20, n_std: float = 2.0) -> pd.DataFrame:
    """Bollinger bands: mid = SMA(close, period), upper/lower = mid ± n_std*std.

    Adds: bb_mid, bb_upper, bb_lower, bb_width (normalised bandwidth
    (upper-lower)/mid). std is the population std (ddof=0), matching the common
    TA definition. Bars before ``period`` has elapsed have NaN and are inert.
    """
    out = df.copy()
    mid = out["close"].rolling(period, min_periods=period).mean()
    sd = out["close"].rolling(period, min_periods=period).std(ddof=0)
    out["bb_mid"] = mid
    out["bb_upper"] = mid + n_std * sd
    out["bb_lower"] = mid - n_std * sd
    width = (out["bb_upper"] - out["bb_lower"]) / mid
    out["bb_width"] = width
    return out


def detect_squeezes(
    df: pd.DataFrame,
    k: int = 100,
    pct: float = 0.20,
    period: int = 20,
    n_std: float = 2.0,
) -> pd.DataFrame:
    """Mark bars in a volatility squeeze and the first expansion close.

    squeeze[t] = bb_width[t] <= its rolling K-period P-th percentile. The
    percentile window is trailing and CLOSED at t (rolling quantile of bars
    <= t). Before K bars of width exist the comparison is impossible -> False.

    trigger = a bar, WHILE squeezed, whose close leaves the band:
        long_trigger: close > bb_upper
        short_trigger: close < bb_lower
    Re-entry discipline: after a trigger fires (long or short) the squeeze is
    considered USED and further closes outside the band in the same squeeze do
    not re-fire until BBW first un-squeezes (rises back above the threshold).
    This is the sequential "armed -> fired -> disarmed" state the spec implies.

    Adds: bb_* columns, squeeze (bool), setup (bool), setup_dir (+1/-1/0).
    The input frame is never mutated.
    """
    bb = bollinger(df, period, n_std)
    out = bb.copy()
    width = bb["bb_width"]

    thr = width.rolling(k, min_periods=k).quantile(pct)
    squeezed = (width <= thr).fillna(False)
    out["squeeze"] = squeezed

    close = out["close"]
    setup = pd.Series(False, index=out.index)
    setup_dir = pd.Series(0, index=out.index)

    # State machine over one squeeze episode: entering a squeeze arms the
    # trigger; the first close outside the band fires it; once fired it stays
    # silent until the squeeze ends (BBW back above threshold) and a new one
    # begins. This prevents a string of band-exceeding closes in one squeeze
    # from stacking multiple entries on the same regime move.
    in_squeeze = False
    fired = False
    for ts in out.index:
        now_sq = bool(squeezed.loc[ts])
        if now_sq and not in_squeeze:
            in_squeeze = True
            fired = False  # fresh squeeze -> trigger armed
        elif not now_sq:
            in_squeeze = False
            fired = False  # squeeze over -> fully reset

        if not in_squeeze or fired:
            continue
        up = pd.notna(bb["bb_upper"].loc[ts]) and close.loc[ts] > bb["bb_upper"].loc[ts]
        dn = pd.notna(bb["bb_lower"].loc[ts]) and close.loc[ts] < bb["bb_lower"].loc[ts]
        if up:
            setup.loc[ts] = True
            setup_dir.loc[ts] = 1
            fired = True
        elif dn:
            setup.loc[ts] = True
            setup_dir.loc[ts] = -1
            fired = True

    out["setup"] = setup
    out["setup_dir"] = setup_dir
    return out


def expansion_levels(bar) -> tuple[float, float, float]:
    """(entry_reference, sl, direction) for a triggered expansion.

    Long: SL just below bb_mid (mean reversion to the band mid is the natural
    failure); Short: SL just above bb_mid. The actual entry price is the next
    bar open, supplied by the session driver; this returns the SL anchor and
    direction so risk can be computed at fill time.
    """
    if bar.setup_dir > 0:
        return bar.bb_mid, 1
    return bar.bb_mid, -1
