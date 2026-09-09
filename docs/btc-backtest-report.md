# BTC Backtest Report — 2026-08-27

**Data:** `data/processed/BTCUSDc_M5_broker.csv` — 100,000 M5 bars, pulled live
from the BTC terminal (account 161700182, symbol BTCUSDc), span **2025-09-13 →
2026-08-27 (347 days)**, 24/7 (no weekend gaps), broker-native pricing.

**Strategy:** the same gold breakout engine (swing S/R, close-above-resistance,
buy at market, structural stop). `sl_buffer` scaled per the multi-instrument
study convention `10 * point` → 0.10 on a 2-dp symbol.

## Results

| measure | value |
|---|---|
| closed trades | 660 |
| win rate | 52.4% |
| **avg R** | **−0.043** |
| t-stat | −1.20 |
| profit factor | 0.87 |
| median stop | 928.8 pts |
| max drawdown | $785.75 (contract 1.0, 0.01 lot) |

Comparisons:

| variant | trades | win% | avg R | PF | t |
|---|---|---|---|---|---|
| **BTCUSDc, sl_buffer 0.10, rr 1.0** | 660 | 52.4% | **−0.043** | 0.87 | −1.20 |
| BTCUSDc, sl_buffer 0.01 (gold default) | 660 | 52.4% | −0.043 | 0.87 | −1.20 |
| BTCUSDc, sl_buffer 0.10, rr 2.0 | 356 | 33.1% | **−0.103** | 0.80 | −1.51 |
| CLI default (max_concurrent=1) | 348 | 52.3% | −0.042 | 0.89 | −0.84 |
| Documented prior (cross-instrument) | ~210 | 52.9% | −0.049 | — | — |

## Verdict

**No edge on Bitcoin.** Every configuration of this strategy on BTCUSDc comes
out **negative net of spread**, and none of them comes close to the noise bar
(|t| ≈ 2.4). The 2026-08-20 cross-instrument study said BTCUSD was "among the
worst of the seventeen tested" at −0.033R; these fresh 660-trade numbers
reproduce that (−0.043R) on the live instrument the bot actually trades.

The config's own header warned *"EXPECT IT TO LOSE"* — it does. A cent account
fixes the *size* problem (the bot can now place trades), not the *edge* problem
(the trades lose). BTC remains a machinery test, not a strategy test.

## What this means for the live bot

- The live BTC bot on account 161700182 will now **place** setups instead of
  skipping them (`below_min_lot` is gone — preflight shows 0.02 lots at the
  median stop, 0.5% cap).
- Expect it to lose slowly, per the measurement. Judge it on R per trade, never
  on balance movement. The one-trade-per-slot guard, daily-loss halt (6%) and
  broker-side SL/TP all still apply.
