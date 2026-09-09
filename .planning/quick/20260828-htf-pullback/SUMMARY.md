# HTF-Aligned M5 Pullback — Falsified for Live (2026-08-28)

## Hypothesis

Taking M5 pullback entries (to the M5 EMA20) only in the direction of the H4
trend (EMA50) improves the pullback's odds. The HTF trend filter is a genuine
predictive gate, not lagging bias. **Primary test target: the gold account
instrument (XAUUSDc).**

## Spec

`.planning/quick/20260828-htf-pullback/SPEC.md`. Pure module
`src/trading_bot/strategy/htf_pullback.py` (htf_bias with shift-by-one-H4-bar
no-lookahead, detect_pullbacks, trigger_levels; 5 tests). Driver + full battery
`scripts/backtest_htf_pullback.py` (entry at next M5 open).

## Findings — GOLD (XAUUSDc, the live gold account instrument)

### Full sample

| config | n | win% | R | t | PF |
|---|---|---|---|---|---|
| HTF-gated rr1.0 | 6578 | 50.6% | +0.013 | +1.04 | 1.03 |
| HTF-gated rr2.5 | 3083 | 29.2% | +0.022 | +0.76 | 1.03 |
| no-HTF (ablation) rr1.0 | 8181 | 49.6% | −0.007 | −0.65 | 0.99 |

### Controls

| control | result | meaning |
|---|---|---|
| **HTF ablation** | gated +0.013/t+1.04 vs unfiltered −0.007/t−0.65 | the EMA(50) gate genuinely IMPROVES the raw pullback on gold |
| **Random-bias** | EMA +1.04 vs random seeds −1.05/−1.33/−0.13 | the EMA carries information — beats all three coin-flip gates |
| Bar coverage | 100% | next-open model holds |
| Train/test | train +0.022/t+1.45 → **test −0.005/t−0.24** | the small edge does not survive out-of-sample |
| Monthly | best 2025-10 t+2.81; 2026-07 t−1.71 | no stable edge; not front-loaded (unlike prior candidates) but uniformly weak |

### The nuanced verdict

The HTF filter is the FIRST mechanism in this battery to beat its random
control — it is NOT lagging bias, and the ablation shows it adds real (if
small) value over the unfiltered M5 pullback. But the gated edge is
economically meaningless: R +0.013 per trade over 6,578 trades, t +1.04
(below the ~2.4 noise bar), and it flattens to t −0.24 out-of-sample. **A true
positive signal does not need 6,500 trades to show t > 2; this one cannot
reach it.**

**BTC** (contrast): HTF gate neutral (t−0.70 vs unfiltered −1.05; all random
seeds negative) — no evidence the gate helps or hurts there.

## Verdict

**Falsified for live deployment.** The H4-EMA trend filter is directionally
correct and information-bearing, but its effect is far too small to trade —
the gated edge fails out-of-sample on the gold instrument. Fifth consecutive
candidate measured; none clears the bar for the gold account.

Methodological distinction worth recording: unlike the prior four candidates
(which failed because their "edge" was noise or 2025 front-loading), this one
fails because the signal is real but negligible. That is a cleaner negative —
nothing to fix, nothing to rescue; the filter simply does not matter enough.

## Tooling

- `src/trading_bot/strategy/htf_pullback.py` — pure module + 5 tests
- `scripts/backtest_htf_pullback.py` — driver + full falsification battery

## Status

Falsified 2026-08-28 (no live candidate). Nothing wired to the gold account.
The existing `filters.htf_trend` helper and this module remain as tested,
documented research surface.
