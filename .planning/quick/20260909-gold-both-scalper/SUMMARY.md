# Both-Direction Single-Slot M5 Gold "Scalper" — Measured, Clears No Bar (2026-09-09)

## Hypothesis

Two untested claims, measured backtest-only through the REAL shared engine
(`run_backtest` gained `direction="both"`) on real broker-native
XAUUSDc M5 bars (100k, 2025-04-01 → 2026-08-28):

1. Letting short-side swing S/R setups compete for the SAME single slot the
   live cent bot runs (XAUUSDc, magic 77020, currently long-only breakout at
   rr=2.0) changes the book honestly — or just dilutes the long edge with
   gold's +54% drift (20260822 prior: shorts −0.059R vs longs +0.135R on
   histdata).
2. Scalp-style fast exits — tight targets (rr<1.0), fill-anchored targets
   (`tp_from_fill`), and `max_hold_bars` time stops at 1h/3h on M5 — turn
   that into a tradeable profile.

Pre-registered grid: 3 control rows (long/short/both at rr=1.0) + 8 scalp
configs on gold. The controls are measured anchors; the 8 scalp rows are the
search whose best |t| is judged against best-of-8 noise.

## What was measured (full-sample gold grid — driver output verbatim)

```
== GOLD grid (XAUUSDc_M5_broker.csv) ==
bars=100000  2025-04-01 13:00:00 -> 2026-08-28 18:10:00  (100k broker-native bars)
engine params: fractal_left=2 fractal_right=2 sr_lookback=60 sl_buffer=0.01 max_concurrent=1 (engine defaults = config-cent.toml [strategy]); exit knobs per row
grid: controls long/short/both rr1.0 ; scalp both rr0.5, rr0.75, rr0.5+tp_from_fill, rr1.0+tp_from_fill, rr1.0+hold12/36, rr0.5+hold12/36 (N=8 scalp configs)
label                        n     win%         R       t      PF  avg_hold
long   rr1.0             n=  438 win= 59.1%  R +0.0925  t=+2.11  PF 1.23  avg_hold 150.6
short  rr1.0             n=  472 win= 55.9%  R +0.0009  t=+0.02  PF 1.00  avg_hold 116.8
both   rr1.0             n=  481 win= 58.8%  R +0.0810  t=+1.94  PF 1.20  avg_hold 173.2
  leg long  (both   rr1.0) n=  271 win= 60.9%  R +0.1260  t=+2.27
  leg short (both   rr1.0) n=  210 win= 56.2%  R +0.0228  t=+0.36
both   rr0.5             n=  945 win= 72.6%  R +0.0021  t=+0.10  PF 1.01  avg_hold 72.8
  leg long  (both   rr0.5) n=  530 win= 72.8%  R +0.0197  t=+0.72
  leg short (both   rr0.5) n=  415 win= 72.3%  R -0.0204  t=-0.67
both   rr0.75            n=  616 win= 66.4%  R +0.0697  t=+2.24  PF 1.21  avg_hold 127.6
both   rr0.5 tpffill     n=  416 win= 55.8%  R +0.1154  t=+2.37  PF 1.26  avg_hold 205.1
both   rr1.0 tpffill     n=  416 win= 55.8%  R +0.1154  t=+2.37  PF 1.26  avg_hold 205.1
both   rr1.0 hold12      n= 2413 win= 11.3%  R +0.0143  t=+1.73  PF 1.10  avg_hold 11.1
both   rr1.0 hold36      n= 1694 win= 25.0%  R +0.0355  t=+2.47  PF 1.16  avg_hold 28.6
both   rr0.5 hold12      n= 2526 win= 31.7%  R -0.0037  t=-0.55  PF 0.97  avg_hold 9.5
both   rr0.5 hold36      n= 1925 win= 50.9%  R +0.0059  t=+0.56  PF 1.03  avg_hold 21.7

== BTC cross-check == (BTCUSDc_M5_broker.csv)
bars=100000  2025-09-13 19:45:00 -> 2026-08-27 02:30:00
label                        n     win%         R       t      PF  avg_hold
long   rr1.0             n=  348 win= 52.3%  R -0.0418  t=-0.84  PF 0.91  avg_hold 197.5
short  rr1.0             n=  410 win= 54.9%  R -0.0055  t=-0.12  PF 0.99  avg_hold 158.9
both   rr1.0             n=  356 win= 51.4%  R -0.0612  t=-1.25  PF 0.87  avg_hold 245.6
both   rr0.5             n=  717 win= 74.3%  R +0.0172  t=+0.76  PF 1.07  avg_hold 104.9
both   rr1.0 hold12      n= 2215 win= 11.4%  R +0.0024  t=+0.28  PF 1.02  avg_hold 11.1
```

Sanity anchors confirmed: long-only rr=1.0 on broker-native gold (n=438, 59.1%
win, R +0.0925) sits exactly on the historical ~+0.09 / 437-trade / 58%-win
reference. No stall: both rr1.0 spans 100.0% of the frame.

> **tp_from_fill row duplication (honest note).** `both rr0.5 tpffill` and
> `both rr1.0 tpffill` printed IDENTICAL books (n=416, R +0.1154, t=+2.37).
> That is engine semantics, not a driver bug: `tp_from_fill` re-anchors the
> target at exactly one stop-distance from the fill (`fill + (fill - sl)`) and
> never reads `rr_multiple`. The plan's pre-registration premise — a "true
> 0.5R-from-fill scalp" at rr=0.5 — does not hold in the engine implementation
> (which the plan mandated leaving byte-identical). Rows 6 and 7 therefore
> measure ONE config twice; the scalp search is effectively N=7 independent
> configs, not N=8. The noise calibration below still uses the pre-registered
> N=8 (no post-hoc winner-count adjustments).

## Falsification battery (falsifier output verbatim)

```
== 1. COVERAGE / stall check (gold) ==
both rr1.0             n_closed=  481  first_entry=2025-04-01 14:15:00  last_exit=2026-08-28 18:10:00  span=100.0%
both rr0.5 hold36      n_closed= 1925  first_entry=2025-04-01 14:15:00  last_exit=2026-08-28 16:20:00  span=100.0%

== 2. 70/30 train/test (gold, cut bar 70000; OOS pass = TEST R > 0 with t > 2.0) ==
both rr1.0 train         n=  344 win= 58.4%  R +0.0782  t=+1.58  PF 1.19  avg_hold 169.4
both rr1.0 TEST          n=  141 win= 59.6%  R +0.0846  t=+1.10  PF 1.21  avg_hold 175.2
    OOS FAIL: TEST R +0.0846 t=+1.10 (need R > 0 AND t > 2.0)
both rr0.5 train         n=  660 win= 72.0%  R -0.0058  t=-0.24  PF 0.98  avg_hold 73.3
both rr0.5 TEST          n=  285 win= 74.0%  R +0.0200  t=+0.55  PF 1.08  avg_hold 71.9
    OOS FAIL: TEST R +0.0200 t=+0.55 (need R > 0 AND t > 2.0)
both rr0.5 tpffill train n=  293 win= 55.3%  R +0.1058  t=+1.82  PF 1.24  avg_hold 203.1
both rr0.5 tpffill TEST  n=  126 win= 57.1%  R +0.1429  t=+1.61  PF 1.33  avg_hold 202.8
    OOS FAIL: TEST R +0.1429 t=+1.61 (need R > 0 AND t > 2.0)
both rr1.0 hold36 train  n= 1192 win= 25.2%  R +0.0448  t=+2.64  PF 1.20  avg_hold 28.9
both rr1.0 hold36 TEST   n=  502 win= 24.5%  R +0.0124  t=+0.46  PF 1.05  avg_hold 27.9
    OOS FAIL: TEST R +0.0124 t=+0.46 (need R > 0 AND t > 2.0)

== 3. MONTHLY R breakdown (gold, closed trades by entry month) ==
-- both rr1.0 --
  2025-04  n=  33  R +0.118  t=+0.74
  2025-05  n=  30  R +0.119  t=+0.70
  2025-06  n=  30  R -0.224  t=-1.34
  2025-07  n=  37  R +0.224  t=+1.48
  2025-08  n=  20  R +0.153  t=+0.71
  2025-09  n=  32  R -0.087  t=-0.53
  2025-10  n=  37  R +0.096  t=+0.63
  2025-11  n=  29  R +0.068  t=+0.40
  2025-12  n=  25  R +0.124  t=+0.66
  2026-01  n=  37  R +0.193  t=+1.35
  2026-02  n=  19  R +0.092  t=+0.41
  2026-03  n=  16  R +0.067  t=+0.27
  2026-04  n=  20  R +0.208  t=+1.02
  2026-05  n=  23  R +0.202  t=+1.07
  2026-06  n=  31  R -0.018  t=-0.10
  2026-07  n=  24  R +0.101  t=+0.55
  2026-08  n=  38  R +0.010  t=+0.07
-- both rr0.5 --
  2025-04  n=  61  R -0.026  t=-0.31
  2025-05  n=  50  R +0.017  t=+0.19
  2025-06  n=  62  R -0.058  t=-0.69
  2025-07  n=  68  R +0.023  t=+0.31
  2025-08  n=  42  R -0.135  t=-1.26
  2025-09  n=  60  R +0.040  t=+0.51
  2025-10  n=  56  R +0.110  t=+1.46
  2025-11  n=  54  R -0.029  t=-0.35
  2025-12  n=  64  R -0.006  t=-0.07
  2026-01  n=  50  R +0.110  t=+1.40
  2026-02  n=  46  R -0.009  t=-0.09
  2026-03  n=  56  R -0.111  t=-1.23
  2026-04  n=  50  R -0.112  t=-1.18
  2026-05  n=  58  R +0.131  t=+1.77
  2026-06  n=  57  R +0.050  t=+0.64
  2026-07  n=  53  R -0.072  t=-0.79
  2026-08  n=  58  R +0.065  t=+0.84

== 4. BEST-OF-N NOISE CALIBRATION (scalp grid N=8, pre-registered) ==
  both rr0.5           full-sample R +0.0021  t=+0.10  n=945
  both rr0.75          full-sample R +0.0697  t=+2.24  n=616
  both rr0.5 tpffill   full-sample R +0.1154  t=+2.37  n=416
  both rr1.0 tpffill   full-sample R +0.1154  t=+2.37  n=416
  both rr1.0 hold12    full-sample R +0.0143  t=+1.73  n=2413
  both rr1.0 hold36    full-sample R +0.0355  t=+2.47  n=1694
  both rr0.5 hold12    full-sample R -0.0037  t=-0.55  n=2526
  both rr0.5 hold36    full-sample R +0.0059  t=+0.56  n=1925
  observed best full-sample |t| across the 8 scalp rows = 2.47  (both rr1.0 hold36)
  P(noise best |t| >= 2.47 | N=8) = 10.3%
  median best |t|, N=8, under pure noise = 1.73 (sanity ~1.74)
  SELF-CHECK: median best |t|, N=39, under pure noise = 2.37 (STATE.md documents ~2.37)

== 5. VERDICT ==
  controls (gold full sample, rr=1.0): long-only R +0.0925 t=+2.11 | short-only R +0.0009 t=+0.02 | both-book R +0.0810 t=+1.94
  both rr1.0 legs: long R +0.1260 t=+2.27 (n=271) | short R +0.0228 t=+0.36 (n=210)
  (20260822 drift-asymmetry reference: shorts -0.059R vs longs +0.135R on histdata; gold's +54% up-drift is why the short mirror trails)
  best scalp config: both rr1.0 hold36 |t|=2.47; best-of-8 noise median is 1.73; P(noise best >= observed) = 10.3%; all-time reference |t|=2.46 is beaten by noise 42% of the time at N=39
  OOS t>2.0 per pre-registered config: both rr0.5 FAIL, both rr0.5 tpffill FAIL, both rr1.0 FAIL, both rr1.0 hold36 FAIL
  -> the full-sample best scalp config (both rr1.0 hold36) OOS: FAIL
  monthly front-loading (both rr1.0): 2025 months weighted R +0.066 vs 2026 months +0.101 -> not front-loaded
  conditions: OOS t>2.0 FAILED | not front-loaded HELD | best-of-N above noise FAILED
VERDICT: clears no bar (conditions must ALL hold: [OOS t>2.0, not front-loaded, best-of-N above noise])
```

## Findings

Against STATE.md's prior context — the single-slot live edge is unproven and
front-loaded (best |t|=2.46 vs a noise bar noise beats 42% of the time at
N=39; recent-half t≈0.7), and every prior short/reversal/scalp-like variant
was falsified — the measured numbers say:

- **Adding shorts neither helps nor much hurts — it dilutes mildly.** Both
  rr=1.0 (R +0.0810, t=+1.94) sits between long-only (R +0.0925, t=+2.11) and
  short-only (R +0.0009, t=+0.02). The 20260822 drift-asymmetry expectation
  was shorts ≈ −0.059R; on THIS broker sample the short leg is ~flat (+0.0228R
  inside the both book, t=+0.36), so the dilution is small. Claim (1) answers:
  the short side competes without collapsing the book, but contributes no
  measured edge — the both book is the long book diluted by flat shorts.
- **Scalp exits trade more often for less; none survive out-of-sample.** Tight
  targets raise win rate exactly as expected (rr0.5: 72.6% win) but net R
  ~0.00 (t=+0.10); the 1h/3h time stops multiply trade count (hold12: n=2413)
  but their R is marginal. The full-sample best scalp row (both rr1.0 hold36,
  |t|=2.47, n=1694) collapses out-of-sample (train t=+2.64 → TEST t=+0.46).
  All four pre-registered exits FAIL the OOS t>2.0 rule.
- **The best-of-8 search does not beat its own noise bar.** Best scalp
  |t|=2.47; pure noise produces a best |t| ≥ 2.47 with P=10.3% at the
  pre-registered N=8 (median best-of-8 = 1.73). 2.47 is exactly the project's
  all-time 2.46 reference, which noise beats 42% of the time at N=39. (The
  tp_from_fill duplication above means the real search was N=7, which would
  only RAISE that p-value.) Claim (2) answers: no.
- **Not front-loaded, for once** — the 2026 half of the both rr1.0 book
  (weighted R +0.101) is if anything stronger than 2025 (+0.066). The failure
  is not the familiar 2025-only artifact; it is plain statistical weakness
  (no single month is significant, and the OOS tail tapers to ~0).

**Verdict: clears no bar.** OOS t>2.0 FAILED for all four pre-registered
exits; best-of-N-above-noise FAILED (P=10.3%); only the not-front-loaded
condition held. Nothing here is wired or approved for any live or demo change.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1/3 - Stale assertion directly contradicted by this task]**
`tests/test_short_and_filters.py::test_direction_must_be_long_or_short`
asserted `run_backtest(df, direction="both")` raises ValueError. Task 1
deliberately makes `"both"` legal, so that assertion could not stay green with
the full suite requirement (plan internal contradiction: "accept both" vs
"existing tests green, none modified"). Minimal fix: the test now asserts a
genuinely invalid direction (`"sideways"`) raises on `run_backtest`, keeping
the test's direction-validation intent. Golden/symmetry/byte-identity tests
were NOT modified. Full suite: **540 passed, 2 skipped** (534 baseline + 6
new). Commit f42fa40.

### Measurement-noted findings (not plan deviations)

- `both rr0.5 tpffill` ≡ `both rr1.0 tpffill` (identical books): the engine's
  `tp_from_fill` is rr-agnostic by design (the plan mandated the engine line
  stay as written), so the pre-registered "0.5R-from-fill" scalp is not
  measurable with the current engine. Reported verbatim; noise calibration
  keeps the pre-registered N=8.
- Long-only rr1.0 broker sample (n=438, R +0.0925) confirms the thin-edge
  reference; BTC machinery cross-check is uniformly negative/near-zero as
  expected for the secondary instrument.

## Status

**BACKTEST ONLY, measured for review.** Nothing live or demo changed:
`live/engine.py`, `config-cent.toml`, the running cent bot and every MT5 path
are untouched (git status clean for all of them). `direction="both"` is a
backtest-only engine seam, deliberately not used by the live engine.

## Tooling

- `src/trading_bot/backtest/engine.py` — `direction="both"` single-slot
  support (additive; default `direction="long"` byte-identical, pinned by
  unchanged golden tests).
- `tests/test_engine_both.py` — 6 tests pinning both-mode semantics
  (byte-identity, mirror symmetry, per-trade labels/geometry, single-slot
  no-overlap, invalid-combo raises).
- `scripts/backtest_both_scalper.py` — the pre-registered grid driver
  (11-row gold grid + leg decompositions + BTC cross-check).
- `scripts/falsify_both_scalper.py` — the falsification battery (coverage,
  70/30 train/test, monthly R, best-of-N noise calibration with N=39
  self-check ≈2.37).
