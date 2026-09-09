---
id: 260820-mkt
slug: market-entry-and-risk-gate
date: 2026-08-20
status: complete
---

# Market entry + hard risk gate, before any real money

## Why

Two things stood between the bot and a real-money test, and only one of them
was known.

**Known:** every order was rejected with retcode 10015 (Invalid price). The
adapter placed a Buy Stop at `resistance`, but `detect_setups` fires on a close
*above* resistance — so the level is behind the market by construction and the
order sits below it. Not intermittently: always. The bot could detect setups,
log them, and never trade.

**Not known until measured:** the strategy's stop is structural
(`support - sl_buffer`), so its size is set by the market and nothing bounds it
against the account. Across the 340 recorded backtest trades the stop distance
per 0.01 lot was:

| | stop distance | as % of a $30 account |
|---|---|---|
| min | $5.33 | 18% |
| median | $24.30 | 81% |
| p95 | $59.78 | 199% |
| max | $129.76 | 433% |

The intended $30 live test would have been ended by the first median trade.

## What was done

1. **Market entry replaces the Buy Stop.** This is not a strategy change. The
   backtest armed the level and filled at `max(entry, open)` on the following
   bar — which was the bar's *open* in 339 of its 340 trades, because the level
   was already behind the market. The pending-order framing was vestigial; a
   market buy on the poll after the signal bar is what was actually backtested.
   `entry` survives as the reference level so risk is still measured from it and
   the realised fill can be logged beside it.

2. **The MT5 request hardened** against everything else that would bounce a
   first live order: prices rounded to the symbol's `digits`, volume snapped
   *down* onto the lot grid (never up — size is risk), SL/TP checked against
   `trade_stops_level`, and market filling modes (IOC/FOK) instead of RETURN,
   which is the pending-order mode.

3. **A hard per-trade risk gate** (`[risk] max_loss_pct_per_trade`, default 2%).
   Projected loss is `(entry - sl) * lot * contract_size`; over budget is
   skipped and logged with the numbers, never resized — 0.01 lots is already
   the broker minimum, so there is nothing smaller to fall back to.

4. **Config left on demo.** `mode = "dry-run"`, `enabled = false` unchanged.
   The order path has not yet executed against any live broker.

## Verification

- 162 tests green (was 148); 14 new, covering market execution, digit
  rounding, volume floor/ceiling, stops-level refusal, filling fallback, the
  risk gate, and fill-vs-reference logging.
- The reported live rejection replayed against the new adapter: ask 4507.65,
  entry 4505.12 → now sends `TRADE_ACTION_DEAL` / `ORDER_TYPE_BUY` at 4507.65.
- All 340 backtest setups run through the gate at 2%: 0 pass at $30, 0 at $250,
  135 at $1,000, 324 at $3,000, 340 at $10,000.

## Known limitation

The gate uses `balance`, not free margin, and does not model the spread. Both
make it slightly optimistic, in the same direction as the existing documented
`spread_assumption` limitation.
