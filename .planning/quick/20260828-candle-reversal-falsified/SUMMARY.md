# Candle-Reversal & Fade Investigation — Falsified (2026-08-28)

## Hypothesis

The "green candle after red candle" reversal pattern provides a directional
edge on M5 XAUUSDc / BTCUSDc:
- Buy the high of the bullish candle (Buy Stop), SL below the wick
- Or fade it: sell the high (limit) targeting the candle midpoint

## Findings (100k M5 bars each, broker-native XAUUSDc + BTCUSDc)

| variant | geometry | win% | R | t |
|---|---|---|---|---|
| Buy breakout of candle high | entry=high, sl=low, TP=0.25x | 56% | −0.29 | −70 |
| Buy breakout, TP=1.0x range | 1:1 | 37% | −0.26 | −34 |
| Buy breakout, TP=2.5x range | 2.5:1 | 22% | −0.23 | −14 |
| Mirror short: sell-stop @ candle low | entry=low, sl=high | 14% | −0.70..−0.73 | −96..−153 |
| Fade: sell-limit @ candle high | sl=+0.25x, tp=−0.5x | 66-69% | **+0.30..+1.04** | +30..+101 |

### The kill-shot: random-signal control

The fade result (R+1.04, t=+101) was tested against a **coin-flip control** —
identical limit-fill mechanics, random entry bars:

| signal | win% | R | t |
|---|---|---|---|
| green-after-red (the pattern) | 68.6% | +1.035 | +101 |
| **random coin flip, seed 1** | **78.3%** | **+1.316** | +109 |
| random, seed 2 | 78.2% | +1.310 | +93 |
| random, seed 3 | 78.4% | +1.314 | +165 |

**Random entries beat the pattern.** The apparent fade edge is a pure
fill-selection artifact: the sell-limit sits at high+0.2x and only fills when
price *rallies into it*, so every fill is a short at a local rally-top with a
near stop and far target. The geometry "wins" regardless of what triggered the
order; the candle pattern actually subtracts value vs. noise.

## Verdict

**Falsified & retained for regression testing only.** Neither direction of the
candle-reversal idea has a real, cause-based signal on M5 gold or BTC:
- Momentum/breakout entries lose to short-term mean reversion.
- Limit-fade "profits" are an artifact of always filling at local
  overextensions — proven by random-signal control beating the pattern.
- The proper-engine pass (below) reproduces the falsification AND exposes a
  structural engine-artifact: the variant's Buy Stop geometry starves the
  single position slot, truncating the sample the naive CLI metric was built on.

## Proper-engine falsification (2026-08-28)

The research scripts use an approximation event loop. The variant was then
wired into the REAL engine (`run_backtest(..., variant="candle_reversal")`,
strategy-variant seam, default `"breakout"` byte-identical) and re-run through
the same protocols. A `setup_override` seam lets a coin-flip trigger replace
the pattern so the engine mechanics are identical in both arms.

**GOLD, pattern vs random coin flips (same engine):**

| trigger | n | win% | R | t | PF |
|---|---|---|---|---|---|
| **pattern** | 1258 | 51.9% | +0.033 | +1.18 | 1.07 |
| random seed 1 | 722 | 51.2% | +0.016 | +0.43 | 1.03 |
| **random seed 2** | 644 | 56.8% | **+0.124** | **+3.19** | **1.29** |
| random seed 3 | 739 | 52.5% | +0.041 | +1.12 | 1.09 |
| random seed 4 | 687 | 52.5% | +0.041 | +1.08 | 1.09 |
| random seed 5 | 787 | 50.2% | −0.007 | −0.19 | 0.99 |

**BTC:** pattern R −0.112, t=−1.62 (negative). Same conclusion.

**Random coin flips beat the pattern.** The pattern's best engine result
(R +0.033, t +1.18) is worse than one random seed (R +0.124, t +3.19). No
predictive alpha over noise — this is the engine-level reproduction of the
research-script falsification.

### The slot-starvation finding (architectural)

The train/full rows were *identical* (same n, same R), which was the tell.
Digging in:

- The gold pattern run **stalls at bar idx 58,603 of 100,000** — the last
  41,400 bars (~2026-01-29 → 2026-08-28, seven months) are never traded.
- Cause: a candle-reversal Buy Stop rests at the *signal candle's high*, a
  price the market often **never revisits**. The armed pending never fills,
  and under `max_concurrent=1` the never-filled pending **permanently occupies
  the single slot**, starving every later setup.
- Proof it is variant-specific: the breakout variant consumes **100%** of the
  data on both instruments; the candle variant consumes ~58% and fills just
  1258 of 25,311 setups (~5%).
- Consequence: the earlier CLI metric (+0.15R, win 33%) was measured on a
  **starved, truncated sample** — it is NOT a real strategy result.

**Architectural takeaway:** single-slot position models with pending-entry
orders require an explicit **order time-to-live (TTL) / cancellation** policy.
An unfilled pending that persists forever is not "waiting for the trade" — it
is a lock on the only slot. (Noted as a possible engine improvement; not
changed here — the live breakout variant never exhibits it because its entries
are swing levels price demonstrably reaches.)

## Method note (for future research)

Always run a **random-signal control** on any limit-order backtest. A strategy
whose limit orders only fill on one-sided price action can show a huge,
t-statistically-overwhelming "edge" that is entirely structural selection bias.
This is the same lesson as the session/time-stop and TP-from-fill studies: an
honest control separates the fill mechanic from the signal. And: **verify the
engine consumed the whole sample** — a stall (identical train/full rows) means
the metric is measuring a truncated market, not the strategy.

## Tooling

- `scripts/backtest_candle_reversal.py` — buy-breakout + TP sweep (long, research approximation)
- `scripts/backtest_candle_mirror.py` — short mirrors (research approximation)
- `scripts/verify_fade_edge.py` — fade plateau + split + random control
- `scripts/falsify_candle_reversal_engine.py` — the REAL-engine falsification
  (pattern vs random via `setup_override`), gold + BTC
- `src/trading_bot/strategy/candle_reversal.py` — pure detection + `candle_levels`
- `src/trading_bot/backtest/engine.py` — `variant` seam (default `"breakout"`) +
  `setup_override` falsification seam
- `config/config-candle-test.toml` — runnable test config for the variant

## Status

Falsified 2026-08-28 (research-script AND proper-engine passes). Retained as a
selectable **test strategy** (`strategy.variant = "candle_reversal"`,
backtest-only) for regression testing and to keep the findings reproducible.
The live engine always runs `variant = "breakout"` and is unaffected.
