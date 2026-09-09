# Volatility Compression / Expansion — Module Spec (2026-08-28)

Status: SPEC. Research only, backtest-first (SAFE-01). Mechanics fixed before
code so the falsification is meaningful. Data: XAUUSDc/BTCUSDc M5 broker CSVs
start 2025-04 / 2025-09 — a "pre-2025 fit" is impossible; use 70/30 split.

## Hypothesis

Markets alternate between compression (low-vol consolidation) and expansion
(directional impulse). Entering when volatility first expands out of a squeeze
captures the start of the move. The regime state (compression) is the claimed
source of edge, not any fixed time window or single-bar shape.

## Core definitions

- Bollinger(period=20, n_std=2.0): mid = SMA(close,20), upper/lower = mid ± 2σ
  (population std, ddof=0). Normalised width BBW = (upper−lower)/mid.
- Squeeze[t]: BBW[t] ≤ its K-period (100) rolling P-th percentile (20%) — a
  trailing, CLOSED window. NaN/inert before K widths exist.
- Trigger (while squeezed): close > upper → LONG; close < lower → SHORT.
- One trigger per squeeze episode: after firing, silent until BBW un-squeezes
  and a new squeeze begins (no stacking entries on one regime move).

## Execution & risk (retained from ORB round — next-open entry)

- Entry at the NEXT M5 bar open (100% coverage, no slot starvation — the fix
  validated by the ORB study).
- SL = the opposite band midpoint (bb_mid) at trigger time: for a long, SL just
  below bb_mid (a real expansion should not collapse back through the mean).
- TP = rr_multiple × risk (rr ∈ {1.0, 2.5} as specified), or optionally an
  exit-on-recompression rule measured separately.

## Falsification battery

1. Full-sample run, gold + BTC; n, win%, R, t, PF.
2. Bar-coverage check — 100% consumption, no stall.
3. Train/test 70/30 — OOS R > 0 with t > 2.0 to pass.
4. Random-squeeze control — triggers on uncompressed band-breaks / random
   volatility states, to test whether the SQUEEZE state adds predictive power
   over a plain band-breakout (which has no regime claim).
5. Monthly breakdown — expose the recurring 2025 front-loading.

## Pure module surface

`src/trading_bot/strategy/volatility_compression.py`
- bollinger(df, period, n_std) -> bb_mid/upper/lower/width
- detect_squeezes(df, k, pct, period, n_std) -> squeeze, setup, setup_dir
- expansion_levels(bar) -> (bb_mid anchor, direction)
Driver: scripts/backtest_volatility_compression.py (next-open entry).
Falsification: scripts/falsify_volatility_compression.py.
