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

## Status

Waiting for the user to run `scripts\eurjpy_check.bat` on Windows and paste
`output\eurjpy_backtest.txt`. No live config or bot code changed: only scripts/
and tests. Suite 680 passed, 2 skipped.
