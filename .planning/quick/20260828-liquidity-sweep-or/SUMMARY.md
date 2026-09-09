# Liquidity-Sweep / Session ORB — Falsified (2026-08-28)

## Hypothesis

Price "sweeping" the High/Low of a session reference range (Asian 00:00–06:00
UTC) during a later window (London 07:00–09:00 UTC / NY 12:00–14:00 UTC) is a
structural, cause-based edge: either expansion in the swept direction
(breakout-continuation) or reversal on a failed sweep. Time-of-day liquidity,
not just the price action, was the claimed source of alpha.

## Spec

`.planning/quick/20260828-liquidity-sweep-or/SPEC.md` — range windows, sweep
detection (tick: any bar poking the boundary), entry at the NEXT M5 bar open
(no pending orders → no slot starvation), SL beyond the swept level, TP =
rr_multiple × risk. Pure module `src/trading_bot/strategy/liquidity_sweep.py`
(session_range, detect_sweeps breakout + failed kinds, 8 tests). Session
driver `scripts/backtest_liquidity_sweep.py` (entry-at-next-open does not fit
run_backtest's pending model).

## Findings (100k M5 bars each, broker-native XAUUSDc + BTCUSDc)

### Full sample

| config | GOLD R (t) | BTC R (t) |
|---|---|---|
| breakout rr1.0 | −0.112 (−1.68) | +0.017 (+0.23) |
| breakout rr2.0 | +0.059 (+0.61) | −0.012 (−0.11) |
| **failed rr1.0** | **+0.107 (+1.39)** | +0.008 (+0.09) |
| failed rr2.0 | +0.018 (+0.16) | +0.214 (+1.66) |

Nothing clears the |t|≈2.4 noise bar on the full sample.

### Bar coverage — PASS

Both instruments trade to ~100% of data. Entry-at-next-open avoids the
slot-starvation failure of the candle-reversal variant. (Good — the design fix
worked; this is the architectural point the candle study raised.)

### Train/test split — FAIL (the edge does not generalize)

Gold failed rr1.0: train **R +0.259, t +2.87** (n=116) → test **R −0.231,
t −1.69** (n=52). The in-sample signal flips negative out-of-sample. Every
config's OOS is negative or noise.

### Random-time control — FAIL (time-of-day carries no alpha)

Gold failed rr1.0 with random (non-session) windows: R ranged −0.134 (t −1.69)
to **+0.139 (t +2.23)** — a random window BEAT the real London-open window
(R +0.107, t +1.39). Session timing is not the source of any signal.

### Monthly breakdown — FAIL (front-loading again)

Gold failed-sweep edge is **Jul–Dec 2025 only** (R +0.625 t=+3.10 in 2025-07),
then **flat (0.000) or negative from 2026-04 onward** (2026-06 t=−2.25). The
same front-loading every gold configuration in this project has shown.

## Verdict

**Falsified.** The liquidity-sweep / session-ORB hypothesis fails all three
out-of-sample tests. No configuration beats the noise bar on live-relevant
(recent) data. The apparent gold edge is the 2025-only artifact this project
has now measured across every candidate (breakout, candle-reversal, session
filtering, time-stops, ORB).

## Method notes (this round)

- **Entry-at-next-open** is the right model for session strategies — it
  eliminated the pending-order slot starvation entirely (100% coverage). Any
  future session strategy should use it, not pending stops.
- **Random-time control** is the session-strategy analogue of the random-signal
  control: a real session window must beat random windows of the same mechanic,
  or the "session" timing is not the edge.
- Sample sizes are small (130–340 trades over 440 days ≈ one per 1–2 days); at
  this frequency even a full-sample t≈2 requires years more data to be
  meaningful — another reason 2025-only results cannot be trusted.

## Tooling

- `src/trading_bot/strategy/liquidity_sweep.py` — pure detection (session_range,
  detect_sweeps breakout/failed) + 8 tests
- `scripts/backtest_liquidity_sweep.py` — session driver (entry at next open)
- `scripts/falsify_liquidity_sweep.py` — train/test + random-time + monthly
- `config/config-*.toml` unchanged; live engine untouched (breakout only)

## Status

Falsified 2026-08-28. Retained as a backtest-only test strategy for
regression/future reference. Nothing wired live.
