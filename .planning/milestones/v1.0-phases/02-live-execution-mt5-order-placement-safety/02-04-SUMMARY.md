---
phase: 02-live-execution-mt5-order-placement-safety
plan: 04
subsystem: engine
tags: live-engine, buy-stop, dedup, safety, polling, simbroker, dry-run

# Dependency graph
requires:
  - phase: 02-01 (broker foundation)
    provides: BrokerClient ABC, SimulatedBroker cursor semantics, PendingOrder.equivalent_to (0.01 tolerance), OrderRequest/OrderResult
  - phase: 02-02 (MT5 adapter + dry-run)
    provides: DryRunBroker no-send seam (ticket=0/placed=False) — provable dry-run at engine level
  - phase: 02-03 (safety guard)
    provides: verify_execution_allowed(cfg, account) + SafetyError — called before every placement (SAFE-03)
provides:
  - LiveEngine: poll_once() fetch closed bars -> shared strategy chain -> setup -> dedup -> safety -> place
  - on_setup() with pending-equivalent + position-open dedup and BrokerRejectedError surfacing
  - 11 golden-frame behavioral tests (setup walk, same-bar dedup, graceful fetch failure, placement, both dedup paths, real-account safety block + opt-in flip, dry-run no-send, rejection, JSON-serializability)
affects: [02-05 CLI live subcommand (engine loop), 02-06 real-terminal verification]

# Tech tracking
tech-stack:
  added: none
  patterns:
    - "Engine programs against the BrokerClient ABC only — never raw MT5 calls (macOS-testable, RESEARCH.md)"
    - "poll_once runs the exact backtest Pass-A chain: detect_swings -> support_resistance -> detect_setups (SAFE-01)"
    - "Event dicts JSON-serializable: bar as ISO string, plain float prices; 2-dp rounding at the decision-log boundary only"

key-files:
  created:
    - src/trading_bot/live/engine.py
    - tests/test_live_engine.py
  modified: none

key-decisions:
  - "poll_once returns the ORDER event for a setup (order_placed/order_skipped/order_rejected from on_setup); setup_detected is logged, not returned (Task 2 contract)"
  - "on_setup order: pending-equivalent dedup -> position-open dedup -> SAFE-03 gate -> place (full precision on the wire)"
  - "Decision log prices rounded to 2 dp (XAUUSD quoting, CLI convention); OrderRequest and returned events keep full precision"

patterns-established:
  - "Golden-frame walk: set SimulatedBroker._cursor to a warm start, then advance() closes bars one at a time — cursor 7 sits ON the setup bar (idx 6)"
  - "Broker stubs subclass SimulatedBroker (e.g. _RejectingBroker raising BrokerRejectedError) instead of reimplementing the ABC"

# Metrics
duration: 9 min
completed: 2026-08-11
---

# Phase 2 Plan 4: LiveEngine Poll→Setup→Place Loop Summary

**LiveEngine polling loop that fetches only closed bars, runs the backtester's exact strategy chain (SAFE-01), and on a setup builds the Buy Stop with backtest-identical arithmetic (entry=101.00, sl=100.09, tp=101.91 on the golden frame), then dedups (equivalent pending + open position), gates on SAFE-03, and places via any BrokerClient — 110 tests green, dry-run provably never reaches the inner broker**

## Performance

- **Duration:** 9 min
- **Started:** 2026-08-11T07:55:00Z (approx.)
- **Completed:** 2026-08-11T08:03:34Z
- **Tasks:** 2
- **Files modified:** 2 created

## Accomplishments
- `LiveEngine.poll_once()`: fetch closed bars via `BrokerClient.fetch_rates` with graceful `BrokerUnavailableError` → `bar_fetch_failed` (EXEC-01); same-bar dedup via `_last_bar_time` (a setup never re-fires on a processed bar); empty-frame and no-setup `bar_check` paths
- `LiveEngine.on_setup()`: dedup equivalent pending order (`PendingOrder.equivalent_to`, 0.01 tolerance) and open position (backtest one-at-a-time parity) → `verify_execution_allowed` SAFE-03 gate → `place_buy_stop` with `BrokerRejectedError` surfacing as `order_rejected`
- Order math matches `backtest/engine.py` exactly: entry=resistance, sl=support−sl_buffer, tp=entry+(entry−sl) — golden setup produces 101.00/100.09/101.91 (1:1 R:R, STRAT-03)
- Every decision logged via `log_decision` (SAFE-02): `bar_check` / `setup_detected` / `order_placed` / `order_skipped` / `order_rejected` / `bar_fetch_failed`, prices at 2-dp (XAUUSD quoting)
- Event dicts JSON-serializable: `bar` as ISO string, plain float prices, no Timestamps
- `tests/test_live_engine.py`: 11 golden-frame behavioral tests; full suite grew 99 → 110 tests, all green on macOS

## Task Commits

Each task was committed atomically:

1. **Task 1: LiveEngine bar polling + setup detection** - `bbe3f84` (feat)
2. **Task 2: Order placement — dedup, safety gate, place, log** - `7705a17` (feat)

**Plan metadata:** `docs(02-04)` commit follows with SUMMARY + STATE.

## Files Created/Modified
- `src/trading_bot/live/engine.py` - `LiveEngine` (`poll_once`, `on_setup`, `_n_bars`, `_last_bar_time` dedup) — imports only pandas/strategy/broker.base/live.safety/logging_utils, never MetaTrader5
- `tests/test_live_engine.py` - Golden `_FIX_*` frame reuse; warm-start cursor walk; dedup/safety/dry-run/reject/serializability tests

## Decisions Made
- **`poll_once()` returns the ORDER event for a setup** (Task 2 contract: `return self.on_setup(...)`); `setup_detected` remains a logged decision line (SAFE-02). The order event carries the detected entry/sl/tp, so the detection test asserts prices on it.
- **`on_setup` check order** is exactly as planned: pending-equivalent dedup first, then position-open dedup, then the safety gate, then place. (Dedup before safety means a blocked/duplicate scenario is reported as a skip even on a real account.)
- **Rounding split**: decision logs round float prices to 2 dp (project CLI convention, "log keeps rounded price fields"); `OrderRequest` and returned event dicts carry full precision.
- **Broker stubs subclass `SimulatedBroker`** (`_RejectingBroker`) rather than reimplementing the ABC — keeps every engine test on the real broker contract.

## Deviations from Plan

### Plan-Interpretation Notes (no rule violations)

**1. Warm-start cursor walk vs. "seed full frame + advance()"**
- **Found during:** Task 1 (test construction)
- **Issue:** The plan's simpler suggestion — seed the full 12-bar frame and `advance()` until `setup_detected` — is not achievable: `SimulatedBroker._cursor` starts at `len(rates)` (12) and only grows, so the setup bar (idx 6) can never again be the last closed bar; advancing past the data re-returns bar idx 11 (`bar_check`, no setup).
- **Fix:** Set `broker._cursor = 5` (warm start, 5 bars of history) and walk `advance()` + `poll_once()` through cursors 5→6→7 — exactly the plan's stated intent ("walk the cursor from a warm start"). Tests touch the private cursor the same way the plan sanctions touching `_orders`/`_positions` for seeding.
- **Verification:** Walk yields `bar_check` (idx 4), `bar_check` (idx 5), then the setup order event (idx 6) with 101.00/100.09/101.91.
- **Committed in:** `bbe3f84`, `7705a17`

**2. Task-1 detection tests adapted to the Task-2 return contract**
- **Found during:** Task 2 (final engine contract)
- **Issue:** Task 1's test spec asserts `poll_once()` returns `setup_detected`; Task 2's spec changes step 8 to `return self.on_setup(...)` (order event). Both tests must pass in the final suite.
- **Fix:** `test_detects_setup_on_last_closed_bar` and `test_no_new_bar_returns_early` assert the final contract: the setup bar returns the `order_placed` event whose entry/sl/tp equal the hand-computed values, and `event=setup_detected` is asserted in the decision log (still the SAFE-02 detection record).
- **Verification:** Full suite green at both the Task-1 commit and the final commit.
- **Committed in:** `7705a17`

---

**Total deviations:** 2 plan-interpretation notes (no Rule 1-4 triggers — no bugs, no missing critical functionality, no blocking issues, no architectural changes)
**Impact on plan:** None — both notes realize the plan's stated intent under the actual SimulatedBroker cursor semantics; no scope creep.

## Issues Encountered
- `test_no_new_bar_returns_early` initially asserted a `bar_check` log line on the same-bar early return; the plan's step 3 specifies no log for that path, so the assertion was corrected to expect zero `bar_check` lines (setup logged exactly once).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- 02-05 (CLI `live` subcommand) can construct `LiveEngine(cfg, broker, logger)` and call `poll_once()` in its loop; dry-run E2E will wrap `SimulatedBroker` in `DryRunBroker` and expect the `order_placed` event with `ticket == 0` and an empty inner ledger — exactly the engine behavior proven here.
- Real-terminal verification remains deferred to the 02-06 human checkpoint (Windows), unchanged.
- Net-edge caveat from 02-02 still stands (thin edge under realistic spread) — revisit before live.

---
*Phase: 02-live-execution-mt5-order-placement-safety*
*Completed: 2026-08-11*
