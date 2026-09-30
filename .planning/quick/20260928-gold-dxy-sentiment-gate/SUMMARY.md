# Gold DXY Macro-Regime Sentiment Gate — Measured, Clears No Bar (2026-09-28)

## Hypothesis

Gold's both-direction single-slot book is already positive but thin and
long-leg-concentrated (STATE.md + scalper SUMMARY: long rr1.0 R+0.0925/t+2.11,
short R+0.0009/t+0.02, both R+0.0810/t+1.94 — within the both book the long leg
is R+0.1260/t+2.27 vs short R+0.0228/t+0.36). This task tested the research's
ranked recommendation, backtest-first, through the REAL shared engine
(`run_backtest`):

1. **DXY regime gate first** (trade-with-regime: weak dollar → long-only, strong
   dollar → short-only, neutral band → both), gated on the *deviation of DXY
   from its own trailing MA* (never the raw non-stationary index level),
   wired through the EXISTING `sentiment`/`sentiment_band` seam with ZERO engine
   change.
2. **Composite DXY+10Y "macro headwind" no-trade-longs gate** (only because the
   DXY-alone gate failed its bar): suppress LONG setups when BOTH DXY strong AND
   yields rising, wired through the EXISTING `setup_veto` seam.

Pre-registered grid: 3 control rows (long/short/both rr=1.0, no gate) + N=6
DXY-gated both-direction configs (MA window {50,200} × neutral band {0,5,10}).
The composite sweep is a separate pre-registered N=4 (dxy_ma {50,200} ×
tnx_ma {50,200} at band 5 and 10).

## What was measured (full-sample gold grid — driver output verbatim)

```
== GOLD DXY regime gate grid (XAUUSDc_M5_broker.csv) ==
bars=100000  2025-04-01 13:00:00 -> 2026-08-28 18:10:00  (~100k broker-native bars)
DXY daily series: 14154 days, 1971-01-04 -> 2026-09-30 (mapped onto M5 with shift(1) no-lookahead)
engine params: fractal_left=2 fractal_right=2 sr_lookback=60 sl_buffer=0.01 max_concurrent=1 (engine defaults = config-cent.toml [strategy]); sentiment gate per row
bar mix at band=10 (bull/bear/neutral): dxy w50 = 26650/18943/54407 ; dxy w200 = 48271/14529/37200
grid: controls long/short/both rr1.0 (no dxy) ; gated both rr1.0 dxy MA window {50,200} x neutral band {0,5,10} (N=6 gated configs)
label                        n     win%         R       t      PF  avg_hold
long   rr1.0 (no dxy)    n=  438 win= 59.1%  R +0.0925  t=+2.11  PF 1.23  avg_hold 150.6
short  rr1.0 (no dxy)    n=  472 win= 55.9%  R +0.0009  t=+0.02  PF 1.00  avg_hold 116.8
both   rr1.0 (no dxy)    n=  481 win= 58.8%  R +0.0810  t=+1.94  PF 1.20  avg_hold 173.2
  leg long  (both   rr1.0 (no dxy)) n=  271 win= 60.9%  R +0.1260  t=+2.27
  leg short (both   rr1.0 (no dxy)) n=  210 win= 56.2%  R +0.0228  t=+0.36
both   rr1.0 dxy w50 b0  n=  487 win= 59.8%  R +0.0949  t=+2.30  PF 1.24  avg_hold 123.3
  leg long  (both   rr1.0 dxy w50 b0) n=  282 win= 59.9%  R +0.1038  t=+1.90
  leg short (both   rr1.0 dxy w50 b0) n=  205 win= 59.5%  R +0.0826  t=+1.31
both   rr1.0 dxy w50 b5  n=  511 win= 57.9%  R +0.0615  t=+1.52  PF 1.15  avg_hold 131.9
  leg long  (both   rr1.0 dxy w50 b5) n=  311 win= 58.5%  R +0.0825  t=+1.57
  leg short (both   rr1.0 dxy w50 b5) n=  200 win= 57.0%  R +0.0290  t=+0.45
both   rr1.0 dxy w50 b10 n=  504 win= 58.9%  R +0.0855  t=+2.09  PF 1.21  avg_hold 144.7
  leg long  (both   rr1.0 dxy w50 b10) n=  298 win= 60.4%  R +0.1194  t=+2.24
  leg short (both   rr1.0 dxy w50 b10) n=  206 win= 56.8%  R +0.0365  t=+0.57
both   rr1.0 dxy w200 b0  n=  471 win= 60.5%  R +0.1169  t=+2.78  PF 1.30  avg_hold 134.3
  leg long  (both   rr1.0 dxy w200 b0) n=  319 win= 60.5%  R +0.1264  t=+2.45
  leg short (both   rr1.0 dxy w200 b0) n=  152 win= 60.5%  R +0.0969  t=+1.33
both   rr1.0 dxy w200 b5  n=  485 win= 59.6%  R +0.0982  t=+2.36  PF 1.24  avg_hold 138.4
  leg long  (both   rr1.0 dxy w200 b5) n=  325 win= 59.7%  R +0.1121  t=+2.18
  leg short (both   rr1.0 dxy w200 b5) n=  160 win= 59.4%  R +0.0699  t=+0.98
both   rr1.0 dxy w200 b10 n=  494 win= 59.9%  R +0.1042  t=+2.53  PF 1.26  avg_hold 142.2
  leg long  (both   rr1.0 dxy w200 b10) n=  336 win= 61.0%  R +0.1374  t=+2.74
  leg short (both   rr1.0 dxy w200 b10) n=  158 win= 57.6%  R +0.0336  t=+0.47
```

Sanity anchors confirmed: the three controls reproduce the scalper numbers
exactly (long +0.0925/t+2.11, short +0.0009/t+0.02, both +0.0810/t+1.94, leg
long +0.1260/t+2.27, leg short +0.0228/t+0.36). The DXY regime flips often
enough to matter: at band=10 the w200 regime marks 48,271 bull / 14,529 bear /
37,200 neutral M5 bars (weak-dollar regime dominates the 2025-04→2026-08 span,
consistent with gold's +54% up-drift).

## Falsification battery (falsifier output verbatim)

```
== 1. COVERAGE / stall check (gold) ==
both rr1.0 (no dxy)    n_closed=  481  first_entry=2025-04-01 14:15:00  last_exit=2026-08-28 18:10:00  span=100.0%
both rr1.0 dxy w50 b10 n_closed=  504  first_entry=2025-04-01 20:30:00  last_exit=2026-08-28 14:05:00  span=100.0%
both rr1.0 dxy w200 b10 n_closed=  494  first_entry=2025-04-01 14:15:00  last_exit=2026-08-28 18:10:00  span=100.0%

== 2. 70/30 train/test (gold, cut bar 70000; OOS pass = TEST R > 0 with t > 2.0) ==
both rr1.0 (no dxy) train n=  344 win= 58.4%  R +0.0782  t=+1.58  PF 1.19  avg_hold 169.4
both rr1.0 (no dxy) TEST  n=  141 win= 59.6%  R +0.0846  t=+1.10  PF 1.21  avg_hold 175.2
    OOS FAIL: TEST R +0.0846 t=+1.10 (need R > 0 AND t > 2.0)
both rr1.0 dxy w50 b5 train n=  343 win= 56.9%  R +0.0463  t=+0.93  PF 1.11  avg_hold 141.2
both rr1.0 dxy w50 b5 TEST  n=  168 win= 60.7%  R +0.1028  t=+1.48  PF 1.26  avg_hold 112.5
    OOS FAIL: TEST R +0.1028 t=+1.48 (need R > 0 AND t > 2.0)
both rr1.0 dxy w200 b5 train n=  324 win= 59.3%  R +0.1006  t=+1.96  PF 1.25  avg_hold 147.7
both rr1.0 dxy w200 b5 TEST  n=  161 win= 60.9%  R +0.1039  t=+1.46  PF 1.27  avg_hold 119.2
    OOS FAIL: TEST R +0.1039 t=+1.46 (need R > 0 AND t > 2.0)
both rr1.0 dxy w50 b10 train n=  346 win= 57.8%  R +0.0699  t=+1.40  PF 1.17  avg_hold 148.4
both rr1.0 dxy w50 b10 TEST  n=  158 win= 62.0%  R +0.1306  t=+1.83  PF 1.34  avg_hold 136.2
    OOS FAIL: TEST R +0.1306 t=+1.83 (need R > 0 AND t > 2.0)
both rr1.0 dxy w200 b10 train n=  329 win= 60.2%  R +0.1181  t=+2.33  PF 1.30  avg_hold 148.7
both rr1.0 dxy w200 b10 TEST  n=  165 win= 60.0%  R +0.0868  t=+1.23  PF 1.22  avg_hold 128.5
    OOS FAIL: TEST R +0.0868 t=+1.23 (need R > 0 AND t > 2.0)

== 3. MONTHLY R breakdown (gold, closed trades by entry month) ==
-- both rr1.0 (no dxy) --
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
-- both rr1.0 dxy w200 b10 --
  2025-04  n=  32  R +0.212  t=+1.33
  2025-05  n=  33  R +0.023  t=+0.14
  2025-06  n=  31  R -0.108  t=-0.63
  2025-07  n=  29  R +0.117  t=+0.66
  2025-08  n=  19  R +0.295  t=+1.42
  2025-09  n=  32  R +0.174  t=+1.06
  2025-10  n=  25  R +0.299  t=+1.64
  2025-11  n=  28  R +0.040  t=+0.23
  2025-12  n=  26  R -0.060  t=-0.32
  2026-01  n=  34  R +0.203  t=+1.35
  2026-02  n=  21  R -0.011  t=-0.05
  2026-03  n=  23  R +0.186  t=+1.00
  2026-04  n=  24  R +0.253  t=+1.37
  2026-05  n=  23  R +0.202  t=+1.07
  2026-06  n=  36  R +0.122  t=+0.79
  2026-07  n=  40  R -0.019  t=-0.13
  2026-08  n=  38  R +0.010  t=+0.07

== 4. BEST-OF-N NOISE CALIBRATION (gated grid N=6, pre-registered) ==
  both rr1.0 dxy w50 b0  full-sample R +0.0949  t=+2.30  n=487
  both rr1.0 dxy w50 b5  full-sample R +0.0615  t=+1.52  n=511
  both rr1.0 dxy w50 b10 full-sample R +0.0855  t=+2.09  n=504
  both rr1.0 dxy w200 b0 full-sample R +0.1169  t=+2.78  n=471
  both rr1.0 dxy w200 b5 full-sample R +0.0982  t=+2.36  n=485
  both rr1.0 dxy w200 b10 full-sample R +0.1042  t=+2.53  n=494
  observed best full-sample |t| across the 6 gated rows = 2.78  (both rr1.0 dxy w200 b0)
  P(noise best |t| >= 2.78 | N=6) = 3.2%
  median best |t|, N=6, under pure noise = 1.60 (sanity ~1.60)
  SELF-CHECK: median best |t|, N=39, under pure noise = 2.37 (STATE.md documents ~2.37)

== 5. VERDICT (DXY-alone) ==
  control both (no dxy): R +0.0810 t=+1.94 | best gated row (both rr1.0 dxy w200 b0): R +0.1169 t=+2.78 (n=471)
  -> DXY gate raises BOTH the both-book avg R (+0.0810 -> +0.1169) and |t| (1.94 -> 2.78)
  leg attribution (control -> best gated): long n=271 R +0.1260 t=+2.27 -> n=319 R +0.1264 t=+2.45 | short n=210 R +0.0228 t=+0.36 -> n=152 R +0.0969 t=+1.33
  direction-split (w200 band=10 bar mix over span): bull 48271 / bear 14529 / neutral 37200 bars (gate trades with the regime)
  best gated |t|=2.78; best-of-6 noise median is 1.60; P(noise best >= observed) = 3.2%; all-time reference |t|=2.46 is beaten by noise 42% of the time at N=39
  OOS t>2.0 per pre-registered config: both rr1.0 (no dxy) FAIL, both rr1.0 dxy w200 b10 FAIL, both rr1.0 dxy w200 b5 FAIL, both rr1.0 dxy w50 b10 FAIL, both rr1.0 dxy w50 b5 FAIL
  NOTE: best full-sample row (both rr1.0 dxy w200 b0) was NOT in the pre-registered OOS set (band 0 excluded); its OOS stability is unverified by pre-registration
  monthly front-loading: control 2025 weighted R +0.066 vs 2026 +0.101 | best gated (both rr1.0 dxy w200 b0) 2025 +0.111 vs 2026 +0.123 -> best gated not front-loaded
  conditions: raises both control R AND |t| HELD | OOS t>2.0 FAILED | not front-loaded HELD | best-of-N above noise HELD
VERDICT: DXY gate clears no bar (conditions must ALL hold: [raises both control R AND |t|, OOS t>2.0, not front-loaded, best-of-N above noise])
```

## Composite (DXY+10Y "macro headwind" no-trade-longs) — verbatim

The DXY-alone gate cleared no bar, so the composite ran (Task 4).

```
== 6. COMPOSITE DXY+10Y 'macro headwind' no-trade-longs gate (setup_veto seam) ==
^TNX daily series: 14206 days, 1970-01-02 -> 2026-09-30 (mapped shift(1)+ffill)

  -- a. COVERAGE / stall --
    both rr1.0 (no dxy)        n_closed=  481 span=100.0%
    both rr1.0 comp d50 t50 b5 n_closed=  484 span=100.0%
    both rr1.0 comp d50 t50 b10 n_closed=  487 span=100.0%
    both rr1.0 comp d200 t200 b5 n_closed=  505 span=100.0%
    both rr1.0 comp d200 t200 b10 n_closed=  513 span=100.0%

  -- b. LONG-LEG R/t vs control (control long R +0.1260 t=+2.27) --
    control long leg: n=271 R +0.1260 t=+2.27
    both rr1.0 comp d50 t50 b5 n=  484 win= 59.7%  R +0.0942  t=+2.27  PF 1.23  avg_hold 165.2
      leg long  (both rr1.0 comp d50 t50 b5) n=  235 win= 62.6%  R +0.1594  t=+2.68
      leg short (both rr1.0 comp d50 t50 b5) n=  249 win= 57.0%  R +0.0326  t=+0.57
      suppressed long setups: 129 | long leg R +0.1594 t=+2.68 (n=235)
    both rr1.0 comp d50 t50 b10 n=  487 win= 59.5%  R +0.0959  t=+2.32  PF 1.24  avg_hold 165.3
      leg long  (both rr1.0 comp d50 t50 b10) n=  246 win= 62.2%  R +0.1537  t=+2.64
      leg short (both rr1.0 comp d50 t50 b10) n=  241 win= 56.8%  R +0.0369  t=+0.63
      suppressed long setups: 92 | long leg R +0.1537 t=+2.64 (n=246)
    both rr1.0 comp d200 t200 b5 n=  505 win= 59.6%  R +0.0936  t=+2.31  PF 1.23  avg_hold 153.0
      leg long  (both rr1.0 comp d200 t200 b5) n=  226 win= 61.9%  R +0.1517  t=+2.49
      leg short (both rr1.0 comp d200 t200 b5) n=  279 win= 57.7%  R +0.0465  t=+0.86
      suppressed long setups: 167 | long leg R +0.1517 t=+2.49 (n=226)
    both rr1.0 comp d200 t200 b10 n=  513 win= 59.5%  R +0.0893  t=+2.22  PF 1.22  avg_hold 153.7
      leg long  (both rr1.0 comp d200 t200 b10) n=  249 win= 62.7%  R +0.1608  t=+2.79
      leg short (both rr1.0 comp d200 t200 b10) n=  264 win= 56.4%  R +0.0219  t=+0.39
      suppressed long setups: 96 | long leg R +0.1608 t=+2.79 (n=249)

  -- c. MONTHLY long-leg R (best composite: both rr1.0 comp d200 t200 b10) --
    2025-04  n=  21  R +0.168  t=+0.82
    2025-05  n=  14  R +0.177  t=+0.72
    2025-06  n=  16  R -0.327  t=-1.42
    2025-07  n=  19  R +0.294  t=+1.42
    2025-08  n=  11  R +0.231  t=+0.79
    2025-09  n=  20  R +0.087  t=+0.42
    2025-10  n=  21  R +0.271  t=+1.34
    2025-11  n=  18  R +0.211  t=+1.01
    2025-12  n=  16  R +0.071  t=+0.29
    2026-01  n=  25  R +0.276  t=+1.61
    2026-02  n=  16  R +0.098  t=+0.39
    2026-03  n=   3  R +0.195  t=+0.33
    2026-04  n=   9  R +0.278  t=+0.87
    2026-05  n=  11  R +0.154  t=+0.55
    2026-06  n=   8  R -0.276  t=-0.78
    2026-08  n=  21  R +0.369  t=+2.09
    2025 weighted R +0.136 vs 2026 +0.202 -> not front-loaded

  -- d. BEST-OF-N (composite N=4, long-leg |t|) --
    observed best long-leg |t| = 2.79 (both rr1.0 comp d200 t200 b10)
    P(noise best |t| >= 2.79 | N=4) = 2.1%
    median best |t|, N=4, under pure noise = 1.41
    SELF-CHECK: median best |t|, N=39 = 2.37 (STATE.md ~2.37)

  -- COMPOSITE VERDICT --
    conditions: raises long-leg avg R AND |t| vs control HELD | coverage ~100% (no stall) HELD | not front-loaded (2026 long-leg positive) HELD | best-of-4 above noise HELD
    VERDICT: composite no-trade-longs gate clears the bar only if ALL of [raises long-leg avg R AND |t| vs control, coverage ~100%, not front-loaded, best-of-4 above noise] hold -- all four held
```

## Findings

**DXY-alone gate: raises the both control, beats best-of-6 noise, not
front-loaded — but FAILS out-of-sample.** The best gated config (w200 b0)
raises the both book from R+0.0810/t+1.94 to R+0.1169/t+2.78, and the R rise is
genuine (attributable to the *short* leg improving from R+0.0228 to R+0.0969 —
suppressing shorts on weak-dollar days — not to sample shrinkage; n stayed
~481→471). Best-of-6 noise P=3.2% (<5%), not front-loaded (2026 half +0.123 vs
2025 +0.111). But every pre-registered OOS config fails TEST t>2.0 (best TEST
t=+1.83 at w50 b10), and the best full-sample row (w200 b0) was *not* in the
pre-registered OOS set. **Verdict: DXY gate clears no bar.**

**Composite DXY+10Y no-trade-longs gate: raises the long leg where the DXY
direction gate did not.** The DXY-alone gate's long leg was unchanged (+0.1260
→ +0.1264); the composite "cut losing longs" — suppressing 92–167 long setups on
macro-headwind days — lifts the long leg to R+0.1608/t+2.79 (d200 t200 b10),
beats best-of-4 noise (P=2.1%), keeps 100% coverage, and is not front-loaded
(2026 long-leg +0.202). Its own (weaker) bar is "cleared". **But this is a
weaker bar than the DXY-alone bar by construction: the composite battery has NO
70/30 OOS test (none was pre-registered), P=2.1% is marginal, and the long-leg
monthly has a July-2026 gap (zero closed longs that month — the gate suppressed
the entire month's longs) with several 2026 months at n<10.** The long-leg
improvement is real in-sample but unverified out-of-sample and on a thin sample.

**Bottom line (honest): neither gate is proven.** The DXY-alone gate fails the
OOS condition outright. The composite clears only a weaker, no-OOS bar; its
long-leg lift is the "cut losing longs" effect the research predicted, but on a
~17-month sample with a monthly gap and a marginal noise P-value, it is
provisional, not tradeable. Nothing here is wired or approved for live/demo.

## Thin-sample caveat

The gold M5 overlap is only **~17 months** (2025-04-01 → 2026-08-28, 100,000
broker-native bars). A daily macro regime therefore has only ~17 monthly
observations to flip; the monthly-stability and OOS tests above run on that thin
span. Any "pass" (including the composite's weaker-bar clear) must be treated as
provisional, with wide t-bands. The composite's long-leg monthly breakdown
shows a missing 2026-07 and several n<10 months, which is exactly the
thin-sample fragility this caveat warns about.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `range=max` returned 3-month granularity, not daily.**
- **Found during:** Task 2 (first driver run; DXY "168 days, 1985→2026").
- **Issue:** The plan's pinned URL `.../chart/{symbol}?range=max&interval=1d`
  returned `dataGranularity: "3mo"` (168 quarterly points) for a multi-decade
  index, making the 200-day MA all-NaN and the 50-day MA a degenerate
  single-value ffill (bar mix `0/100000/0`).
- **Fix:** `_chart_url` now uses `period1=0&period2=4102444800&interval=1d`
  (deterministic future period2 = 2100-01-01, which Yahoo clamps to "now"),
  returning the full daily history (DXY 14,154 days 1971→2026; ^TNX 14,206 days
  1970→2026) — matching the RESEARCH's "17k daily bars" claim.
- **Files modified:** `src/trading_bot/news/macro.py` (commit `4229bfa`).

**2. [Rule 1 - Wrong sanity figure] Plan's "median best-of-6 ≈ 1.90" is
actually 1.60.**
- **Issue:** The plan/RESEARCH quoted the median best-of-6 noise |t| as "~1.90"
  (and best-of-12 as "~2.2"). The verbatim `median_best_of_n` bisection gives
  1.60 for N=6 (and 1.91 for N=12).
- **Fix:** The battery prints the true value (1.60); the N=39 self-check prints
  2.37, matching STATE.md exactly, proving the helper is correct. The plan's
  "~1.90" was a rough overestimate; the P-value (3.2%) is computed correctly
  either way.

## Status

**BACKTEST ONLY, measured for review.** Nothing live or demo changed:
`live/engine.py`, `engine.py`, `config-cent.toml`, every `config/*.toml`, the
running cent bot and every MT5 path are untouched (git status clean for all of
them). The DXY gate and the composite no-trade-longs gate are backtest-only
seams (`sentiment`/`sentiment_band` and `setup_veto`) that the live engine never
calls. No live/demo wiring is implied or approved.

## Tooling

- `src/trading_bot/news/macro.py` — stdlib Yahoo chart fetcher for DXY + ^TNX
  (UA header, JSON cache `data/processed/{dxy,tnx}.json`, fail-closed) +
  `to_gold_bullishness` (DXY-vs-own-MA deviation → 0-100, 50 neutral) +
  `is_yield_rising`.
- `tests/test_macro.py` — 8 offline tests (monkeypatched urlopen; parse/cache/
  URL-encoding/normalization/yield-regime/fail-closed).
- `scripts/backtest_gold_dxy.py` — the pre-registered 9-row grid driver
  (3 controls + N=6 DXY-gated MA×band sweep + leg decompositions).
- `scripts/falsify_gold_dxy.py` — the falsification battery (coverage, 70/30
  train/test, monthly R, best-of-N noise calibration with N=39 self-check
  ≈2.37) + the conditional composite DXY+10Y no-trade-longs battery.

## Self-Check: PASSED

- Files exist: `src/trading_bot/news/macro.py`, `tests/test_macro.py`,
  `scripts/backtest_gold_dxy.py`, `scripts/falsify_gold_dxy.py`,
  `.planning/quick/20260928-gold-dxy-sentiment-gate/SUMMARY.md`.
- Commits exist: `789ef7c` (Task 1 fetcher+tests), `4229bfa` (Rule-3 daily-
  granularity fix), `3f9f1d4` (Task 2 driver), `c264cae` (Task 3 battery),
  `a4c1b8b` (Task 4 composite).
- Full suite green: **584 passed, 2 skipped** (586 collected; +8 new macro
  tests, zero existing test files edited).
- Protected files untouched: `src/trading_bot/backtest/engine.py`,
  `src/trading_bot/live/`, `config/` — no diffs.
