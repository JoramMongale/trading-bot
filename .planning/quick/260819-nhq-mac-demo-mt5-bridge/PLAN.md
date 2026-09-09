---
quick_id: 260819-nhq
slug: mac-demo-mt5-bridge
date: 2026-08-19
type: quick
status: in-progress
---

# Quick Task: Verify Phase 2 + run the bot on an MT5 demo account from macOS

## Context

STATE.md assumed 02-06 (real-MT5 round-trip) would be verified on a Windows
machine. The user is on an Apple M5 MacBook, so that path is replaced.

Verified on macOS before starting:
- 115/115 tests pass
- backtest runs end-to-end on real 2025-2026 XAUUSD data (339 trades, PF 1.29)
- `pip install MetaTrader5` has NO macOS wheel (confirmed via pip index) —
  the package is still Windows-only

Two gaps to close:
1. `live --mode dry-run` is a no-op: `build_broker` hands the engine a
   `SimulatedBroker` with `rates=None`, so every poll logs `bar_fetch_failed`
   and the strategy never runs. Only the E2E test seeds data.
2. No way to reach a demo account from macOS.

## Decisions (user-selected)

| Decision | Choice | Rationale |
|---|---|---|
| MT5-on-Mac path | Docker bridge (`siliconmetatrader5`) | Free; bot stays native macOS Python; API-compatible with MetaTrader5 |
| Demo account | User already has broker demo credentials | No account-opening step needed |
| Dry-run gap | Fix it | Gives a working offline smoke test independent of MT5 |

## Tasks

### Task 1 — Make dry-run actually replay bars
- Add optional `cursor` param to `SimulatedBroker.__init__` (replaces the
  E2E test's private `_cursor = 0` poke).
- Add `ReplayBroker(SimulatedBroker)`: `fetch_rates` returns closed bars then
  advances the cursor one bar, so successive polls walk history forward.
- `build_broker` dry-run branch loads the configured histdata CSVs, resamples
  to M5, and seeds `ReplayBroker` rewound `live.replay_bars` bars.
- Dry-run with no data on disk must stay a graceful `bar_fetch_failed`, not a
  crash.

### Task 2 — Bridge support in MT5Broker
- Add `[live] bridge` (`auto`|`native`|`silicon`), `bridge_host`, `bridge_port`
  to LiveConfig + DEFAULT_LIVE + `_validate`.
- `MT5Broker` gains an `_mt5()` accessor: returns the cached bridge instance
  when configured, else falls through to the existing module-level
  `_load_mt5()`. The 30 fake-MT5 tests inject into `sys.modules` and construct
  MT5Broker without a bridge, so they must keep passing untouched.
- `build_broker` passes bridge settings from cfg.

### Task 3 — Stand up the Docker bridge and connect the demo account
- Colima (QEMU x86_64) + the silicon-metatrader5 container.
- User logs into their demo account in the MT5 GUI over VNC.

### Task 4 — Run the 02-06 verification checklist against the demo account
Adapted from 02-06-PLAN.md: live bars, a demo Buy Stop with correct SL/TP,
SAFE-03 real-account block, and pending-order dedup.

## Verification
- Full test suite green (115 existing + new tests)
- `live --once --mode dry-run` reports a real `bar_check`, not `bar_fetch_failed`
- Demo run logs `bar_check` lines with real XAUUSD prices
