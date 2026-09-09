"""Aggregate trade statistics (SAFE-01).

All price math is in raw price points (XAUUSD 2-dp quoting, JPY crosses 3-dp);
account-currency money uses ``contract_size`` (oz/lot) times ``lot`` on the
legacy path, or a spec-derived ``value_per_point`` when one is supplied.
``pnl_points`` and ``r_multiple`` are enriched onto every trade dict in place.

Conventions:
  - closed trades = exit_reason in ("SL", "TP")
  - wins/losses/win_rate/avg_r/profit_factor/max_drawdown come from closed trades
  - OPEN trades are NOT wins/losses but ARE included in net P&L
  - ``avg_trade_bars`` is the mean ``exit_idx - entry_idx`` (index positions,
    so gaps in the bar grid don't inflate the count); 0.0 when no trades
  - an empty trade list returns all zeros (profit_factor 0.0, not inf)
  - ``value_per_point`` (INST-01): account-currency money per 1.0 price-unit
    move on ONE FULL lot (InstrumentSpec.tick_value / tick_size). When
    supplied, money = pnl_points x value_per_point x lot; when None (default)
    the legacy ``contract_size`` x lot product is used -- byte-identical gold/
    BTC runs. Money is NEVER derived from ``contract_size`` when a spec value
    is present (PITFALLS A2).
  - ``spread_price`` (INST-03): one-sided spread cost in the instrument's own
    PRICE units, netted exactly once per CLOSED trade (SL/TP) before the
    r_multiple recompute, so ``avg_r`` is net of spread. OPEN trades are never
    netted. Default 0.0 keeps legacy runs numerically untouched.
"""

from __future__ import annotations

from typing import Any

import numpy as np

_CLOSED_REASONS = ("SL", "TP")


def trade_stats(
    trades: list[dict[str, Any]],
    contract_size: float = 100.0,
    lot: float = 0.01,
    value_per_point: float | None = None,   # INST-01: account-currency money per 1.0 price-unit per FULL lot (tick_value/tick_size). None = legacy contract_size path.
    spread_price: float = 0.0,              # INST-03: one-sided spread cost in instrument PRICE units, netted once per CLOSED trade. 0 = legacy no-spread path.
) -> dict[str, float]:
    """Compute aggregate stats from the engine's trade records.

    Args:
        trades: engine trade records (mutated in place with ``pnl_points`` /
            ``r_multiple``).
        contract_size: legacy money basis (units per lot), used ONLY when
            ``value_per_point`` is None.
        lot: position size in lots.
        value_per_point: account-currency money per 1.0 price-unit on one FULL
            lot (spec tick_value/tick_size). None -> legacy contract_size path.
        spread_price: one-sided spread in instrument price units, netted once
            per CLOSED trade. 0.0 -> legacy no-spread path.
    """
    closed = [t for t in trades if t["exit_reason"] in _CLOSED_REASONS]

    # Enrich every trade with P&L points and R multiple (NaN when risk == 0).
    #
    # `risk` is SIGNED: positive for a long (entry above stop), negative for a
    # short. That makes r_multiple correct for both directions with no special
    # casing — a winning short has exit < entry, so a negative move divided by a
    # negative risk gives positive R.
    #
    # pnl_points is NOT self-correcting the same way: a winning short moves the
    # price DOWN, so the raw difference is negative. Every downstream number
    # here (gross win/loss, win_rate, the equity curve, drawdown) is built from
    # pnl_points, so without the flip a profitable short book would report as a
    # total loss. Direction defaults to "long" for records written before the
    # short side existed.
    for t in trades:
        risk = t["entry"] - t["sl"]
        sgn = 1.0 if t.get("direction", "long") == "long" else -1.0
        t["pnl_points"] = sgn * (t["exit_price"] - t["entry"])
        t["r_multiple"] = (t["exit_price"] - t["entry"]) / risk if risk else np.nan

    # INST-03 spread netting: net the one-sided spread (instrument PRICE units)
    # exactly once per CLOSED trade (SL/TP). OPEN trades are never in `closed`,
    # so their gross enrichment is untouched. r_multiple is recomputed from the
    # NETTED pnl_points so avg_r is net-of-spread. `pnl_points / abs(risk)` with
    # risk = entry - sl is algebraically IDENTICAL to the line above for both
    # directions (for a short: pnl = -(exit-entry) and abs(risk) = -risk, so the
    # signs cancel), so this is the single deterministic recompute; the block is
    # skipped entirely when spread_price == 0.0, keeping legacy runs untouched.
    if spread_price:
        for t in closed:
            risk = t["entry"] - t["sl"]
            t["pnl_points"] -= spread_price                       # net once, in instrument price units
            t["r_multiple"] = (t["pnl_points"] / abs(risk)) if risk else np.nan

    pnls_closed = np.array([t["pnl_points"] for t in closed])
    pnls_all = np.array([t["pnl_points"] for t in trades])

    # INST-01 money basis: with a spec, account-currency money = pnl_points x
    # (tick_value/tick_size) x lot. Legacy (no spec): contract_size x lot,
    # byte-identical at the defaults.
    money_per_point = (value_per_point * lot) if value_per_point is not None else (contract_size * lot)

    gross_win = pnls_closed[pnls_closed > 0].sum()
    gross_loss = -pnls_closed[pnls_closed <= 0].sum()
    equity = pnls_closed.cumsum() * money_per_point
    peak = np.maximum.accumulate(equity)

    if len(pnls_closed):
        wins = int((pnls_closed > 0).sum())
        losses = int((pnls_closed <= 0).sum())
        win_rate = float((pnls_closed > 0).mean())
    else:
        wins = losses = 0
        win_rate = 0.0

    if len(pnls_all):
        net_pnl_points = float(pnls_all.sum())
        net_pnl_usd = net_pnl_points * money_per_point
    else:
        net_pnl_points = net_pnl_usd = 0.0

    bars_held = [
        t["exit_idx"] - t["entry_idx"]
        for t in trades
        if t["exit_idx"] is not None and t["entry_idx"] is not None
    ]

    if gross_loss > 0:
        profit_factor = float(gross_win / gross_loss)
    elif gross_win > 0:
        profit_factor = float("inf")
    else:
        profit_factor = 0.0

    return {
        "total_trades": len(closed),
        "open_trades": len(trades) - len(closed),
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "net_pnl_points": net_pnl_points,
        "net_pnl_usd": float(net_pnl_usd),
        "avg_r": float(np.mean([t["r_multiple"] for t in closed])) if closed else 0.0,
        "profit_factor": profit_factor,
        "max_drawdown_usd": float((peak - equity).max()) if len(equity) else 0.0,
        "avg_trade_bars": float(np.mean(bars_held)) if bars_held else 0.0,
    }
