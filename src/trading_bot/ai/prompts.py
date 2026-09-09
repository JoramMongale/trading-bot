"""Prompt templates for the AI layer (plan 03-01).

Templates live as plain files in the configured ``[ai] prompt_dir`` so editing
a prompt never touches code. Each file is rendered with a context dataclass
from ``ai/context.py``. When a template file is missing, a built-in copy
(module constant below) is used, so the system still runs from a fresh checkout
with no prompts directory — offline-first by construction.

The model is explicitly told it only knows what is in the prompt and must not
claim live data — the rule from the reference book that stops a model from
hallucinating a price it cannot actually see.
"""

from __future__ import annotations

from pathlib import Path

from trading_bot.ai.context import RegimeContext, TradeContext

TRADE_TEMPLATE = """You are the reasoning half of a hybrid gold-breakout trading system. A
deterministic strategy has detected a setup and computed its own entry, stop
and target from market structure. Your job is to give an independent directional
verdict on that setup. You never set prices; the deterministic system owns
execution and risk.

You only know what is in this prompt. Do NOT claim access to live market data.
Your training memory of "current" gold prices is stale and must not be used.

MARKET CONTEXT
{symbol} {timeframe} candles; setup bar {bar_time} (UTC hour {session_hour})
Resistance {resistance}  Support {support}
Deterministic trade: entry {entry}, stop {sl}, target {tp}
Stop distance {stop_distance}; reward:risk on offer {reward_risk}
Move over the last {n_bars} bars: {change_pct}%
ATR estimate: {atr_estimate}
Account balance {balance}; max loss per trade {max_loss_pct}% of balance

LAST BARS (oldest -> newest)
{last_bars}

RULES
- bias is LONG, SHORT or NONE. NONE means "no tradable idea right now".
- confidence is 0..100, your honest conviction.
- invalidation_level is the price at which this idea is dead: for a LONG it
  must be at or below the stop; for a SHORT at or above it. null if you have
  none.
- If the idea is not clearly better than a coin flip, output bias NONE — a
  low-conviction pass costs nothing and protects the account.
- reasoning: 2-3 sentences maximum.

Respond with ONLY this JSON object, no prose, no markdown fences:
{{"ticker": "{symbol}", "bias": "LONG|SHORT|NONE", "confidence": 0-100,
  "invalidation_level": number-or-null, "reasoning": "..."}}
"""

REGIME_TEMPLATE = """You are the daily regime reader of a hybrid gold trading system. Once per day
you judge whether today's gold market is tradeable for a 5-minute breakout
strategy.

You only know what is in this prompt. Do NOT claim access to live news or
economic data.

REGIME CONTEXT
{symbol} — daily snapshot as of {as_of} (UTC)
Recent {n_days} daily bars:
{days}
Up days fraction: {up_days_frac}
Average daily range: {avg_daily_range_pct}% of price
Price change over the window: {price_change_pct}%
Strategy recent performance: {recent_avg_r} R per trade over {recent_trades}
trades

{sentiment_block}
RULES
- regime is TRENDING, RANGING or CHOPPY.
- bias is BULLISH, BEARISH or NEUTRAL.
- tradeable is true only if a 5-minute breakout strategy has a real chance of
  working today. CHOPPY markets are usually NOT tradeable for a breakout.
- confidence is 0..100.
- notes: 1-2 sentences.

Respond with ONLY this JSON object, no prose, no markdown fences:
{{"regime": "TRENDING|RANGING|CHOPPY", "bias": "BULLISH|BEARISH|NEUTRAL",
  "confidence": 0-100, "tradeable": true-or-false, "notes": "..."}}
"""


def load_template(name: str, prompt_dir: str = "prompts") -> str:
    """Load ``name`` from ``prompt_dir``, falling back to the built-in copy.

    The file takes precedence when present so operators can iterate on prompts
    without code changes; the built-in keeps a fresh checkout working.
    """
    path = Path(prompt_dir) / name
    if path.is_file():
        return path.read_text(encoding="utf-8")
    if name == "trade_idea.txt":
        return TRADE_TEMPLATE
    if name == "regime_check.txt":
        return REGIME_TEMPLATE
    raise FileNotFoundError(
        f"no prompt template {name!r} and no built-in copy for it"
    )


def _fmt_bars(bars: list[dict]) -> str:
    return "\n".join(
        f"{b['time']}  O {b['open']:.2f}  H {b['high']:.2f}  "
        f"L {b['low']:.2f}  C {b['close']:.2f}"
        for b in bars
    )


def render_trade_prompt(ctx: TradeContext, prompt_dir: str = "prompts") -> str:
    """Render the trade-idea prompt for ``ctx``."""
    return load_template("trade_idea.txt", prompt_dir).format(
        symbol=ctx.symbol,
        timeframe=ctx.timeframe,
        bar_time=ctx.bar_time,
        session_hour=ctx.session_hour,
        resistance=f"{ctx.resistance:.2f}",
        support=f"{ctx.support:.2f}",
        entry=f"{ctx.entry:.2f}",
        sl=f"{ctx.sl:.2f}",
        tp=f"{ctx.tp:.2f}",
        stop_distance=f"{ctx.stop_distance:.2f}",
        reward_risk=f"{ctx.reward_risk:.2f}",
        change_pct=f"{ctx.change_pct:.2f}",
        atr_estimate=f"{ctx.atr_estimate:.3f}",
        balance="unknown" if ctx.balance is None else f"{ctx.balance:.2f}",
        max_loss_pct=f"{ctx.max_loss_pct:.1f}",
        n_bars=len(ctx.last_bars),
        last_bars=_fmt_bars(ctx.last_bars),
    )


def _fmt_days(days: list[dict]) -> str:
    return "\n".join(
        f"{d['date']}  O {d['open']:.2f}  H {d['high']:.2f}  "
        f"L {d['low']:.2f}  C {d['close']:.2f}"
        f"{'' if d['change_pct'] is None else f'  {d['change_pct']:+.2f}%'}"
        for d in days
    )


def _sentiment_block(sentiment: dict | None) -> str:
    """Render the optional NEWS SENTIMENT paragraph, or an empty string.

    An absent/empty snapshot renders nothing — never "None"/"nan" — so the
    regime prompt stays clean when there is no news today (fail-open, 03-04).
    """
    if not sentiment:
        return ""
    titles = "; ".join(str(t) for t in (sentiment.get("top_titles") or [])[:5])
    return (
        "NEWS SENTIMENT (last update {date})\n"
        "Daily score {score} (range -1..1, positive = bullish news)\n"
        "Articles scored {articles}\n"
        "Headlines: {titles}"
    ).format(
        date=sentiment.get("date", "unknown"),
        score=sentiment.get("score", "unknown"),
        articles=sentiment.get("articles", 0),
        titles=titles or "—",
    )


def render_regime_prompt(ctx: RegimeContext, prompt_dir: str = "prompts") -> str:
    """Render the daily regime prompt for ``ctx``."""
    return load_template("regime_check.txt", prompt_dir).format(
        symbol=ctx.symbol,
        as_of=ctx.as_of,
        n_days=ctx.n_days,
        days=_fmt_days(ctx.days),
        up_days_frac="unknown" if ctx.up_days_frac is None else f"{ctx.up_days_frac:.2f}",
        avg_daily_range_pct=(
            "unknown" if ctx.avg_daily_range_pct is None
            else f"{ctx.avg_daily_range_pct:.2f}"
        ),
        price_change_pct=f"{ctx.price_change_pct:.2f}",
        recent_avg_r="unknown" if ctx.recent_avg_r is None else f"{ctx.recent_avg_r:.3f}",
        recent_trades=ctx.recent_trades,
        sentiment_block=_sentiment_block(ctx.sentiment),
    )
