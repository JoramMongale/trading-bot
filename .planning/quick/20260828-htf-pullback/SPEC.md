# HTF-Aligned M5 Pullback — Module Spec (2026-08-28)

Status: SPEC. Research only, backtest-first (SAFE-01). **Primary target: the
gold account instrument (XAUUSDc).** Broker M5 CSVs start 2025-04 (gold) and
2025-09 (BTC) — a "pre-2025 fit" is impossible; use the 70/30 split.

## Hypothesis

Taking M5 pullback entries only in the direction of the H4 trend (EMA 50)
improves the pullback's odds — the HTF trend filter is a genuine predictive
gate, not lagging bias. This is the most pervasive retail paradigm and the last
candidate in the micro-structure battery.

## Core definitions

- HTF bias: H4 close vs H4 EMA(50). Bullish = close > EMA; Bearish = close < EMA.
  No-lookahead: shift the H4 verdict by one H4 bar, then forward-fill onto M5
  (an M5 bar may only see completed H4 bars — mirrors filters.htf_trend).
- M5 fast EMA(20) for pullback context.
- Long trigger (HTF bullish): M5 bar closes bullish (close>open) AND its low
  touched/traded at-or-below M5 EMA(20) — a pullback into the fast EMA that
  re-accelerates up. Short trigger is the mirror with HTF bearish.

## Execution & risk

- Entry at the NEXT M5 bar open (retained: 100% coverage, no slot starvation).
- SL = trigger bar low (long) / high (short). TP = rr × risk, rr ∈ {1.0, 2.5}.
- One position at a time.

## Falsification battery (falsify_htf_pullback_engine.py)

1. Full-sample run + 100% bar-coverage check, gold (XAUUSDc) primarily, BTC for
   contrast.
2. **HTF ablation control** — identical M5 pullback logic WITHOUT the HTF gate.
   If the unfiltered version matches/beats it, the HTF filter adds no value.
3. **Random-bias control** — the same gated logic but with a coin-flip HTF bias
   every H4 bar. If random gating matches/beats the EMA filter, the trend
   filter adds no predictive alpha.
4. Train/test 70/30 — OOS must hold R > 0 with t > 2.0.
5. Monthly breakdown — expose the recurring 2025 front-loading.

## Pure module surface

src/trading_bot/strategy/htf_pullback.py
- htf_bias(df, ema, rule) -> int Series (+1/-1/0), no-lookahead aligned
- detect_pullbacks(df, ema_fast, ema_htf, htf_rule) -> setup/setup_dir/columns
- trigger_levels(bar) -> (sl anchor, direction)
Driver: scripts/backtest_htf_pullback.py (next-open entry). Falsification:
scripts/falsify_htf_pullback_engine.py.
