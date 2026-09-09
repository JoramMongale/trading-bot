# Volatility Compression / Expansion — Falsified (2026-08-28)

## Hypothesis

Markets alternate between compression (low-vol consolidation) and expansion
(directional impulse). Entering when volatility first expands out of a squeeze
captures the start of the move — the COMPRESSION state is the claimed source of
edge.

## Spec

`.planning/quick/20260828-volatility-compression/SPEC.md`. Pure module
`src/trading_bot/strategy/volatility_compression.py` (bollinger width,
detect_squeezes with one-trigger-per-squeeze discipline, expansion_levels;
7 tests). Driver `scripts/backtest_volatility_compression.py` (entry at next
M5 open, SL = bb_mid, TP = rr × risk). Falsification
`scripts/falsify_volatility_compression.py`.

## Findings (100k M5 bars each, XAUUSDc + BTCUSDc)

### Full sample

| config | GOLD R (t) | BTC R (t) |
|---|---|---|
| pct0.1 rr1.0 | +0.006 (+0.15) | −0.018 (−0.49) |
| pct0.2 rr1.0 | −0.023 (−0.76) | +0.004 (+0.12) |
| pct0.2 rr2.5 | −0.021 (−0.39) | −0.101 (−1.99) |

Nothing positive or significant on the full sample.

### Bar coverage — PASS

100% on both instruments (next-open execution model retained from the ORB
round). No slot starvation.

### Squeeze vs plain-band-breakout control — FAIL (the squeeze adds nothing)

| instrument | SQUEEZED | PLAIN breakout (no squeeze) |
|---|---|---|
| GOLD | R −0.023, t −0.76 | **R +0.042, t +1.96** |
| BTC | R +0.004, t +0.12 | R +0.003, t +0.14 |

On gold the squeeze filter is not merely useless — it is HARMFUL: removing the
compression requirement IMPROVES the result. The specific claim that
compression precedes a tradeable expansion is not supported; a plain Bollinger
band-breakout (no regime claim) does as well or better.

### Train/test — FAIL

Gold pct0.2 rr1.0: train +0.011 → test −0.106. BTC is the mirror (train −0.043
→ test +0.115, t 2.07): opposite signs between instruments/halves = regime
luck, not edge. No config holds positive OOS on both.

### Monthly — FAIL

No stable month-to-month edge. Gold best month t = +1.12; 2026-05 is t = −3.35
AGAINST the strategy. BTC alternates sign across months (+2.24, −3.02, −2.18).

## Verdict

**Falsified.** The compression-state filter does not create edge on M5 gold or
BTC, and the control shows it is actively harmful on gold versus a plain
band-breakout. Fourth consecutive candidate (after the original sweep, candle
reversal, and session ORB) to fail the falsification battery on live-relevant
data.

## Method notes (this round)

- **Ablation control**: the strongest falsifier here was removing the claimed
  mechanism (squeeze) and showing the stripped strategy is no worse — sometimes
  better. Any "state filter" hypothesis should be tested this way, not just
  against random signals/times.
- A plain Bollinger band-breakout at rr1.0 gave gold t=+1.96 full-sample — the
  best single number seen this session, but still below the noise bar and
  unremarkable across halves; not worth pursuing without fresh evidence.

## Tooling

- `src/trading_bot/strategy/volatility_compression.py` — pure module + 7 tests
- `scripts/backtest_volatility_compression.py` — driver (next-open entry)
- `scripts/falsify_volatility_compression.py` — split + ablation + monthly

## Status

Falsified 2026-08-28. Retained as backtest-only test strategy. Nothing live.
