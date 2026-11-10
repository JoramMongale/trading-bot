# Quick task 20261110-scorecard-eurjpy

The user asked whether to raise leverage. The answer was no: gold is already at
10% risk per trade and the live sample is tiny. They chose to build:

1. **Live scorecard** (`scripts/scorecard.py`, appended to the watchdog daily
   summary, `watchdog.py --scorecard`). Per market, live closes since
   2026-11-04 vs backtest: win %, avg R, total R, worst drop, worst losing
   run, last-30 average. Verdicts:
   - too early below 30 trades
   - ⚠️ at once if the drop or losing run beats the backtest's worst, or the
     last-30 average is below the backtest's 5th percentile
   - ✅ only with 30+ trades, a positive average and no warning
   - otherwise ➖
2. **EUR/JPY check** (`scripts/eurjpy_check.bat`):
   - `fetch_broker_history.py --spec` now writes the spec sidecar (symbol
     facts + median spread), fetched from the gold terminal (read-only).
   - `scripts/backtest_market.py` runs the live breakout engine, net of
     spread, with 4 pre-registered rows: long, short, both, both + VIX b10.
   - PASS = avg R > 0, t >= 2 and positive in both halves.

## Gold reference (recomputed 2026-11-10, XAUUSDm M5, 100k bars)

long rr1.0: n=437, win 58.4%, avg +0.091R gross, max drop 8.1R, worst losing run
7, 30-trade average 5th-95th pct -0.12R .. +0.32R. With 160-point spread charged:
avg +0.085R, t=+1.94. **That is a fail under the new-market bar**, so the live gold
long book is itself not proven. This is one more reason not to raise risk. At 10%
risk per trade, the backtest's worst run of 7 losses is about a -52% drawdown.

BTC reference: short rr1.0, win 54.9%, avg -0.006R (no edge found).

## EUR/JPY result (run on Windows 2026-11-10, user-pasted)

```
bars=99,999  2025-07-08 12:10 -> 2026-11-10 07:00  (489 days), EURJPYc, account USC
spread: median 24 points = 0.024 price; median stop 0.407 -> spread is 5.9% of a stop
row                       n   win%    avgR      t    PF  1st half  2nd half  maxDD streak
1 long  rr1.0           351   57.0  +0.009  +0.17  1.02    +0.035    -0.019  19.3R      5
2 short rr1.0           411   50.9  -0.133  -2.97  0.74    -0.118    -0.148  65.6R      8
3 both  rr1.0           352   55.1  -0.016  -0.32  0.97    -0.071    +0.045  29.3R      6
4 both  rr1.0 + VIX b10 367   51.5  -0.099  -2.03  0.80    -0.079    -0.121  37.6R      9
```

**Verdict: EUR/JPY fails. config-eurjpy.toml stays disabled.** Spread costs
~0.06R per trade here (vs ~0.005R on gold), which on its own wipes out a 1:1
breakout's edge. The short leg is clearly negative, but it must NOT be flipped
into a "fade": that rule was not pre-registered, and inverting it pays the
spread again. The VIX direction filter made it worse, which matches the
carry-unwind research (261106-carry).

## Status

EUR/JPY closed. No live config or bot code changed: only scripts/
and tests. Suite 680 passed, 2 skipped.
