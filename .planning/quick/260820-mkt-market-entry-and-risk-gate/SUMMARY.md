---
id: 260820-mkt
slug: market-entry-and-risk-gate
date: 2026-08-20
status: complete
tests: 162 passed
commits:
  - 09a9739 feat(quick) [risk] per-trade loss cap in config
  - 7e37664 fix(quick) buy at market — the Buy Stop was rejected by construction
  - b314faa docs(quick) record 260820-mkt and flag the $30 sizing problem
---

# Summary

## Delivered

- **Market entry.** `place_buy_stop` → `place_market_buy`
  (`TRADE_ACTION_DEAL` / `ORDER_TYPE_BUY` at the live ask, SL+TP attached in
  the same request). Faithful to the backtest, which filled at the next bar's
  open in 339/340 trades.
- **Request hardening.** Digit rounding, lot-grid floor with refusal rather
  than upsizing, `trade_stops_level` check, IOC/FOK filling with fallback.
- **Risk gate.** `[risk] max_loss_pct_per_trade`, default 2%, checked before
  every placement; blocks and logs, never resizes.
- **Fill visibility.** `order_placed` now logs `fill` and `slippage` alongside
  the reference `entry`.

## Verified

| Check | Result |
|---|---|
| Test suite | 162 passed (was 148) |
| Lint | 3 findings, all pre-existing on HEAD |
| Recorded rejection replayed (ask 4507.65, entry 4505.12) | now a valid DEAL at 4507.65 |
| Dry-run CLI smoke | `bar_check new_bar=True setup=False`, exit 0 |
| 340 backtest setups through the gate @2% | $30 → 0 pass · $1,000 → 135 · $3,000 → 324 · $10,000 → 340 |

## NOT verified

The order path has never executed against a live broker. It is covered by unit
tests and by replaying the recorded rejection — not by an actual fill.

## Open decision for the user

$30 is below what this strategy can be traded at. 0.01 lots is the broker
minimum and the median setup risks $24.30 of it. Options: fund to ~$1,215+ for
the median setup at 2%, or knowingly raise the cap and accept that one loss
takes a large slice of the account.

## Next

Observe a real DEMO fill (`--mode demo`) — `order_placed` with a non-zero
ticket and a sane `fill`/`slippage` in `output/live.log` — before touching
`[live] mode` / `enabled`.
