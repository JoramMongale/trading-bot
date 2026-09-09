# Liquidity-Sweep / Session ORB — Module Spec (2026-08-28)

Status: SPEC — not yet built. Research only, backtest-first (SAFE-01). This
document fixes the mechanics BEFORE code so the falsification is meaningful.

## Hypothesis

London (07:00 UTC) and NY (12:00 UTC) session opens inject institutional
volume. Price frequently "sweeps" the High/Low of an earlier reference range
(e.g. the Asian session) to hunt stops / trap breakout traders, then either
expands in the swept direction (continuation) or reverses back inside the range
(failed sweep). Either way the sweep event itself carries information.

## Data reality (measured)

- XAUUSDc M5 broker CSV: 100,000 bars, 2025-04-01 → 2026-08-28, UTC index,
  440 trading days. Gold trades Mon 00:00 → Fri ~21:00, resumes Sun ~21:00.
- Asian-range (00:00–06:00) High/Low is well-defined on every full day.
- London-window (07:00–09:00) sweeps the Asian High/Low on ~50% of days
  (10-day probe: UP-SWEEP 5×, DN-SWEEP 2×, none 3×) — a workable sample.

## Parameters (defaults to sweep)

| param | meaning | test values |
|---|---|---|
| `range_start`, `range_end` | reference-range window (UTC, [start,end)) | **Asian 00–06**, London-OR 07:00–07:30 |
| `sweep_start`, `sweep_end` | window in which a sweep may fire (UTC) | 07–09 (London), 12–14 (NY), 07–14 |
| `direction` | ORB interpretation | **both tested**: breakout-continuation AND failed-sweep reversal |
| `sweep_mode` | how a sweep is detected | `tick` = any bar high>range_high / low<range_low (intrabar) |
| `entry` | when to enter after a confirmed sweep | **next M5 bar open** (no pending orders → no slot starvation) |
| `rr_multiple` | TP distance as multiple of SL distance | 1.0, 1.5, 2.0, 2.5 |
| `sl_buffer` | cushion beyond the reference level | small, e.g. 0.01% of price |
| `max_trades_per_day` | cap | 1 |

## Trade definitions

**Reference range** over `[range_start, range_end)` UTC on a trading day:
- `range_high` = max(high of bars in window)
- `range_low`  = min(low of bars in window)
- Day skipped entirely if the window is empty (data gap / market closed).

**Sweep** (tick mode): during `[sweep_start, sweep_end)`:
- UP-sweep at bar t if `high[t] > range_high`
- DN-sweep at bar t if `low[t] < range_low`

**Breakout-continuation** (enter WITH the sweep):
- UP-sweep → LONG, entry at next bar open; SL below `range_low` (the swept
  level, so a real continuation never returns to it); TP = entry + rr×(entry−sl)
- DN-sweep → SHORT mirror.

**Failed-sweep reversal** (enter AGAINST the sweep):
- UP-sweep (price pokes above `range_high`) → if price then CLOSES back below
  `range_high` before the window ends, that is the failure → SHORT, entry next
  open; SL above `range_high` (the failed level); TP = entry − rr×(sl−entry).
- DN-sweep mirror. A sweep that does NOT fail within the window produces no trade.

## No-lookahead rules (same as the rest of the strategy package)

- The range uses only bars in its own window (closed before the sweep window).
- A sweep is known at the close of the bar that pokes the boundary (tick mode:
  the poke happened intrabar, but we only ACT once the bar has closed — entry at
  the NEXT bar open, matching live semantics).
- The failed-sweep close-back check reads only bars up to the decision bar.

## Engine integration

- Pure module: `src/trading_bot/strategy/liquidity_sweep.py`
  - `session_range(df, start, end)` → per-day range_high/range_low aligned to bars
  - `detect_sweeps(df, range_high, range_low, sweep_window, kind)` → setup column
- Because entries are at the NEXT BAR OPEN and exits use SL/TP over subsequent
  bars, this maps onto the existing `run_backtest` event loop ONLY if the entry
  price is known at arm time. Next-bar-open entry does NOT fit the pending-order
  model cleanly → this strategy gets its OWN session backtest driver
  (`scripts/backtest_liquidity_sweep.py`) that reuses the strategy's pure
  detection + the engine's SL-before-TP / fill conventions, rather than being
  forced into `run_backtest`'s single-bar arm model.

## Falsification battery (mandatory before any conclusion)

1. **Full-sample run** — gold + BTC; report n, win%, R, t, PF.
2. **Bar/slot coverage check** — confirm trades span the whole time series
   (no stall like the candle-reversal variant).
3. **Random-time control** — same session logic but with the sweep window
   shifted to random non-session times / random range windows, to test whether
   time-of-day provides alpha over arbitrary windows.
4. **Train/test split** — 70/30; report OOS R and t. Robustness bar: OOS R > 0
   and t > 2.0, matching the prior sweep's accepted standard.
5. Monthly R breakdown to expose front-loading.

## Accept / reject

Reject the hypothesis if: random-time control matches the session result, OOS
is flat/negative, or the edge is front-loaded. Accept only provisionally, and
still require a demo/live paper run before real money — consistent with every
strategy this project has measured.
