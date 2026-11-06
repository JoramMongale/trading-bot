# Quick task 20261106-carry-unwind-research

**Verdict: no carry-trade signal is tradeable. Nothing live changed.**

The user asked to add yen carry-trade unwind monitoring (USD/JPY, CHF/JPY, VIX,
US-Japan yield gap, CFTC positioning) and maybe open another market.

## Method (rules fixed before the first run)

Free daily data: Yahoo (USDJPY, EUR/CHF/AUD/GBP-JPY, VIX), FRED DGS2 (US 2y),
and CFTC TFF yen futures (leveraged funds, from 2006, used 3 days after the
report date). No free daily Japan 2y yield exists, so US 2y change stands in
for the rate gap.

- UNWIND = USDJPY down 2%+ in 5 days AND (VIX >= 1.2 x 50d MA OR leveraged
  funds' net yen short down 25%+ in 4 weeks)
- CALM = VIX < 50d MA AND USDJPY > 50d MA AND not UNWIND
- Outcome: forward 5d / 20d return of the JPY-cross basket, non-overlapping
  samples, 2003-14 vs 2015-26. A signal passes only if it has the same sign
  in both halves and |t| >= 2 in both.

`python scripts/carry_unwind_research.py fetch|analyse` reproduces it.

## Results (5-day, basket)

| Signal | 2003-14 | 2015-26 |
|---|---|---|
| UNWIND | +0.63%, t=+1.63 (wrong way) | -0.24%, t=-0.92 |
| VIX stress | -0.36%, t=-1.37 | -0.19%, t=-1.67 |
| CFTC cover | -0.05%, t=-0.31 | +0.17%, t=+2.01 (wrong way) |
| US 2y narrowing | -0.52%, t=-1.85 | -0.15%, t=-0.83 |
| CALM | 0.00% | -0.01% |

The 20-day results are similar: nothing passes. VIX stress is the only one
with the right sign in both halves, and it is too weak (t < 2) to trade on.

## Reading

The carry-unwind story explains big episodes after the fact (Aug 2024), but
by the time the daily signs show up, the move is mostly done. They do not
predict the next week in a way a bot can use.

## Another market

EUR/JPY (config-eurjpy.toml) still has no backtest on broker data; phase 6
(broker-native JPY data) was never run. That backtest has to come before any
real money goes on a new market.
