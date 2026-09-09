---
slug: short-side-and-filters
created: 2026-08-22
status: in-progress
---

# Short side + directional/volatility filters — BACKTEST ONLY

## Why this scope

The request arrived framed as "great results, 58–66% win rate is a solid
foundation". That framing is wrong and the plan is shaped by correcting it.

Measured on this project's own data: XAUUSDm 437 trades, 58.6% win rate,
avgWin **0.859R**, avgLoss **−0.986R**, net **+0.086R** at t=1.96. Across all
6,541 trades the figure is **−0.0156R**. Because the fill lands above the
reference entry, break-even at nominal 1:1 needs ~53.4%, so 58.6% is worth
almost nothing. A high win rate at 1:1 is the number that makes a losing system
look like a winning one — it already fooled the TP-from-fill experiment, which
restored true 1.000R winners exactly as predicted and *lost money anyway*
because win rate fell 58.6% → 53.9%.

So: **none of this gets wired into the live engine.** It lands as backtest
parameters with defaults off, the same way `session_hours` and `max_hold_bars`
already did — "there is no evidence that would justify it."

The short side is included not as a feature but as a **measurement**. ~39
configurations have already been searched here; the best |t| anywhere was 2.46,
which noise beats 42% of the time. Adding filters slices the sample thinner and
multiplies that search space. The short side is the one addition that *doubles*
the sample instead, and it answers the most valuable open question: is the
negative edge symmetric? If shorts are also negative, the setup itself carries
no information — the single most useful thing this project could learn.

## Tasks

1. **`strategy/signals.py`** — `detect_setups(df, direction="long")`.
   Short mirror: `close < support AND close[t-1] >= support[t-1]`.
   Default preserves current behaviour exactly (live engine must not change).

2. **`strategy/filters.py`** (new) — pure functions, no I/O:
   - `atr(df, period=14)` — Wilder ATR
   - `atr_below_median(df, period=14, median_bars=120)` — the volatility gate
   - `htf_trend(df, sma=20, rule="1h")` — resample to H1, SMA, **shift(1)** so
     the forming H1 bar is never read, reindex back onto M5
   - `body_bullish(df)` / `body_bearish(df)` — candle-close confirmation

3. **`backtest/engine.py`** — sign-generalized loop via `direction`:
   | | long | short |
   |---|---|---|
   | entry ref | resistance | support |
   | stop | support − buffer | resistance + buffer |
   | fills when | high >= entry | low <= entry |
   | fill price | max(entry, open) | min(entry, open) |
   | SL hit | low <= sl | high >= sl |
   | TP hit | high >= tp | low <= tp |

   `tp = entry + (entry - sl)` is unchanged — for a short, `entry - sl` is
   negative, so the same expression yields the correct target. Likewise
   `R = (exit - entry) / (entry - sl)` is already sign-correct.

   New params, all defaulting off: `direction="long"`, `atr_median_bars=None`,
   `htf_sma=None`, `require_body=False`.

   `direction="both"` is deliberately NOT implemented. Two directions competing
   for one position slot is a different system with its own selection bias, and
   nothing yet justifies it.

4. **`backtest/stats.py`** — direction-aware `pnl_points`. R is already correct;
   raw points are not (a winning short has `exit < entry`).

5. **Tests** — mirror-symmetry on synthetic data, no-lookahead on the H1 filter,
   and a regression proving `direction="long"` reproduces the golden trades
   byte-for-byte.

6. **Measure** — long vs short on the same bars, then each filter, with the
   multiple-comparisons bar applied. Report R per trade and t, never win rate
   alone.

## Out of scope

- Any live-engine change
- `direction="both"`
- News / event gating — needs a feed and a calendar, and stacks a second
  unproven system on an unproven one
