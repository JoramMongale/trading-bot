"""AI backtest harness (plan 03-01, AI-04).

Replays history through the SAME ``run_backtest`` event loop the deterministic
backtest uses, but with a ``setup_veto`` that gates every setup through the AI
proposal gate, plus the once-per-day regime check. The veto is the only new
code path — no duplicated fill/exit loop — so what is AI-gated is exactly what
the deterministic backtest would have traded, minus whatever the AI layer
blocked.

Returns the gated trades AND the raw (ungated) trades so the caller can report
raw vs gated stats side by side — the honest comparison this plan demands,
because a filter that only narrows the sample can flatter a backtest.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Optional

import pandas as pd

from trading_bot.ai.base import AIClient, AIClientError
from trading_bot.ai.context import build_regime_context, build_trade_context
from trading_bot.ai.gate import APPROVED, evaluate_proposal
from trading_bot.ai.schema import AIResponseError
from trading_bot.backtest.engine import run_backtest
from trading_bot.strategy.levels import support_resistance
from trading_bot.strategy.signals import detect_setups
from trading_bot.strategy.swings import detect_swings


def _avg_r(trades: list[dict[str, Any]]) -> float | None:
    """Mean R multiple of closed trades, or None when empty.

    R for a long = (exit - entry) / (entry - sl). Only closed trades (non-null
    exit_price) count — the size-independent number this project actually tracks.
    """
    rs = []
    for t in trades:
        if t.get("exit_price") is None:
            continue
        risk = t["entry"] - t["sl"]
        if risk == 0:
            continue
        rs.append((t["exit_price"] - t["entry"]) / risk)
    if not rs:
        return None
    return sum(rs) / len(rs)


def run_ai_backtest(
    df: pd.DataFrame,
    cfg,
    ai_client: AIClient,
    *,
    on_event: Optional[Callable[[dict], None]] = None,
    recent_window: int = 20,
    **run_kwargs,
) -> dict[str, Any]:
    """Run the deterministic and AI-gated backtests over ``df``.

    Args:
        df:       OHLC frame (datetime index), resampled to the strategy TF.
        cfg:      loaded Config (strategy + [ai] + [risk] tables).
        ai_client: AIClient consulted on each setup + once per day.
        on_event: optional SAFE-02 event sink (receives the strategy events of
                  the gated run plus ``ai_regime`` / ``ai_proposal``).
        recent_window: how many closed trades the regime prompt sees.
        **run_kwargs: overrides passed to ``run_backtest`` (defaults come from
                  ``cfg.strategy``).

    Returns::

        {"raw_trades": [...], "gated_trades": [...],
         "regime_checks": int, "regime_blocks": int,
         "consultations": int, "approved": int, "rejected": int,
         "unavailable": int, "last_avg_r": float|None}
    """
    kwargs = {
        "fractal_left": cfg.strategy.fractal_left,
        "fractal_right": cfg.strategy.fractal_right,
        "sr_lookback": cfg.strategy.sr_lookback,
        "sl_buffer": cfg.strategy.sl_buffer,
        "rr_multiple": cfg.strategy.rr_multiple,
    }
    kwargs.update(run_kwargs)

    # Enrich the frame ONCE so the veto can build contexts (resistance/support)
    # from bars that carry the deterministic levels. run_backtest recomputes the
    # same columns from the same kwargs, so the enriched frame and the loop stay
    # in lockstep — identical strategy, one context path for both runs.
    df = df.copy()
    df = detect_swings(df, kwargs["fractal_left"], kwargs["fractal_right"])
    df = support_resistance(df, kwargs["sr_lookback"])
    df = detect_setups(df)

    state = {
        "day": None,
        "regime": None,
        "closed": [],
        "regime_checks": 0,
        "regime_blocks": 0,
        "consultations": 0,
        "approved": 0,
        "rejected": 0,
        "unavailable": 0,
    }

    def emit(event: dict) -> None:
        if on_event is not None:
            on_event(event)

    def gated_emit(event: dict) -> None:
        """Capture closed trades (for the regime's realized-R read) and forward."""
        if event["event"] == "trade_closed":
            state["closed"].append(event)
        emit(event)

    def veto(bar: pd.Series, entry: float, sl: float, tp: float) -> Optional[str]:
        bar_time = bar.name
        window = df.iloc[: df.index.get_loc(bar_time) + 1]

        # Once-per-day regime read (fail OPEN on transport errors).
        today = bar_time.date()
        if cfg.ai.regime_check_daily and state["day"] != today:
            state["day"] = today
            state["regime_checks"] += 1
            rctx = build_regime_context(
                window, cfg,
                recent_avg_r=_avg_r(state["closed"][-recent_window:]),
                recent_trades=len(state["closed"]),
            )
            try:
                state["regime"] = ai_client.assess_regime(rctx)
            except (AIClientError, AIResponseError) as exc:
                state["regime"] = None
                emit({"event": "ai_regime_failed", "day": str(today),
                      "detail": f"{type(exc).__name__}: {exc}"})
            else:
                emit({"event": "ai_regime", "day": str(today),
                      "regime": state["regime"].regime,
                      "bias": state["regime"].bias,
                      "confidence": state["regime"].confidence,
                      "tradeable": state["regime"].tradeable})
            if (
                cfg.ai.block_when_choppy
                and state["regime"] is not None
                and (state["regime"].is_choppy or not state["regime"].tradeable)
            ):
                state["regime_blocks"] += 1
                return "ai_regime_block"

        # Proposal gate (fail CLOSED on transport/parse errors).
        tctx = build_trade_context(window, cfg, entry, sl, tp, bar_time)
        state["consultations"] += 1
        try:
            proposal = ai_client.propose_trade(tctx)
        except (AIClientError, AIResponseError) as exc:
            state["unavailable"] += 1
            emit({"event": "ai_proposal", "bar": str(bar_time),
                  "verdict": "UNAVAILABLE",
                  "reason": f"{type(exc).__name__}: {exc}"})
            return "ai_unavailable"

        verdict = evaluate_proposal(
            proposal,
            entry=entry, sl=sl, tp=tp, direction="long",
            min_confidence=cfg.ai.min_confidence,
            require_agreement=cfg.ai.require_agreement,
        )
        emit({"event": "ai_proposal", "bar": str(bar_time),
              "bias": proposal.bias, "confidence": proposal.confidence,
              "invalidation": proposal.invalidation,
              "verdict": verdict.verdict, "reason": verdict.reason})
        if verdict.verdict != APPROVED:
            state["rejected"] += 1
            return f"ai_{verdict.reason}"
        state["approved"] += 1
        return None

    raw_trades = run_backtest(df, **kwargs)
    gated_trades = run_backtest(df, on_event=gated_emit, setup_veto=veto, **kwargs)
    return {
        "raw_trades": raw_trades,
        "gated_trades": gated_trades,
        "regime_checks": state["regime_checks"],
        "regime_blocks": state["regime_blocks"],
        "consultations": state["consultations"],
        "approved": state["approved"],
        "rejected": state["rejected"],
        "unavailable": state["unavailable"],
        "last_avg_r": _avg_r(gated_trades),
    }
