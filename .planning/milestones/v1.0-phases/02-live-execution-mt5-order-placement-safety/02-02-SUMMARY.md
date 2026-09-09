---
phase: 02-live-execution-mt5-order-placement-safety
plan: 02
subsystem: broker
tags: [mt5, lazy-import, fake-module, dry-run, order-send, safety, pytest]

# Dependency graph
requires:
  - phase: 02-live-execution-mt5-order-placement-safety (plan 02-01)
    provides: BrokerClient ABC, broker dataclasses/errors, SimulatedBroker,
      and the [live] config schema the MT5 adapter's symbol/logger wiring builds on
provides:
  - MT5Broker: real adapter implementing BrokerClient via a guarded lazy
    MetaTrader5 import (connect, closed-bar fetch, account info, order_send
    Buy Stop with SL/TP, pending orders, positions)
  - DryRunBroker: no-send safety wrapper — logs order_plan, returns
    placed=False/ticket=0, structurally cannot reach the inner broker
  - FakeMT5 test double: injected into sys.modules so the Windows-only adapter
    is fully unit-tested on macOS
affects: [02-04-live-engine, 02-05-cli, 02-06-windows-verification] — engine/CLI
  construct MT5Broker (mode=demo/live) or DryRunBroker wrapping SimulatedBroker
  (mode=dry-run)

# Tech tracking
tech-stack:
  added: none (stdlib logging, pandas, numpy already present)
  patterns:
    - Lazy guarded import: _load_mt5() is the single MetaTrader5 import site —
      module imports on macOS, tests inject a fake via sys.modules
    - Fake module injection: FakeMT5 class placed in sys.modules["MetaTrader5"];
      call recording lets tests assert exact invocation args (start_pos, request dict)
    - No-send seam: DryRunBroker.place_buy_stop contains zero references to the
      inner broker — a dry-run run cannot leak a real order by construction

key-files:
  created:
    - src/trading_bot/broker/mt5.py
    - src/trading_bot/broker/dry_run.py
    - tests/test_mt5_broker.py
  modified:
    - src/trading_bot/broker/__init__.py

key-decisions:
  - "MetaTrader5 imported ONLY inside _load_mt5(); every method calls it — the file imports on macOS and the fake-module tests work"
  - "fetch_rates uses copy_rates_from_pos(symbol, tf, 1, count): start_pos=1 skips the forming bar (no-lookahead parity with the backtester)"
  - "None from copy_rates_from_pos returns an empty OHLC frame, not an error — a no-data poll is normal for a fresh start"
  - "place_buy_stop builds the exact RESEARCH.md request dict; filling mode from symbol_info bitmask — IOC preferred, RETURN fallback, ORDER_FILLING_IOC last resort"
  - "retcode DONE(10009)/PLACED(10008) = placed; any other retcode or None raises BrokerRejectedError"
  - "DryRunBroker.place_buy_stop has zero references to self._inner — logs event=order_plan via log_decision (SAFE-02) and returns placed=False/ticket=0"

patterns-established:
  - "Guarded adapter pattern: lazy import + actionable BrokerUnavailableError (Windows hint + dry-run suggestion) instead of crashing at import time"
  - "Fake-module unit testing: the adapter is verified against an injected FakeMT5 with bit-exact constants, recording calls for argument assertions"
  - "Safety wrapper as a distinct BrokerClient implementation — dry-run is not a flag inside MT5Broker, it is a wrapper type that cannot send"

# Metrics
duration: 8min
completed: 2026-08-11
---

# Phase 2 Plan 2: MT5 Real Adapter + Dry-Run Wrapper Summary

**MT5Broker — real adapter over a guarded lazy MetaTrader5 import (closed-bar fetch via start_pos=1, RESEARCH.md-verified order_send Buy Stop dict, explicit retcode handling) — plus DryRunBroker, the no-send seam that logs order_plan and structurally cannot reach a real account**

## Performance

- **Duration:** 8 min
- **Started:** 2026-08-11T07:47:30Z
- **Completed:** 2026-08-11T07:55:17Z
- **Tasks:** 2
- **Files modified:** 4 (3 created source/tests, 1 modified)

## Accomplishments
- `MT5Broker` implements the full `BrokerClient` contract against a lazy-loaded `MetaTrader5` module: `connect()` verifies initialize/terminal_info/symbol_select with actionable `BrokerUnavailableError`s; `disconnect()` shuts down; `fetch_rates()` maps M1/M5, calls `copy_rates_from_pos(symbol, tf, 1, count)` (**start_pos=1 skips the forming bar** — no-lookahead parity with the backtester), converts unix seconds to a datetime index, returns only OHLC columns, and treats `None` as a normal no-data poll (empty frame, logged) rather than an error
- `place_buy_stop()` builds the exact RESEARCH.md request dict (`TRADE_ACTION_PENDING` + `ORDER_TYPE_BUY_STOP`, entry=resistance, sl/tp, GTC, deviation/magic/comment) with filling mode read from `symbol_info().filling_mode` bitmask (IOC preferred → RETURN fallback → `ORDER_FILLING_IOC`); retcode handling is explicit — DONE(10009)/PLACED(10008) → `placed=True` with ticket, any other retcode or a `None` result → `BrokerRejectedError` with `last_error()` context; `pending_orders()`/`positions()` filter by magic (server-side symbol scoping via `orders_get(symbol=...)`/`positions_get(symbol=...)`, `None` → `[]`)
- `DryRunBroker` (phase success criterion 4): delegates read-only methods to the wrapped broker, but `place_buy_stop()` contains **zero references to the inner broker** — it emits an `order_plan` structured decision line via `log_decision` (SAFE-02) and returns `placed=False`/`ticket=0`/`comment="dry-run: no order sent"`. The inner broker's pending/positions state is never touched, so no phantom order can appear
- 30 fake-module tests prove the adapter on macOS: bit-exact request dict, both filling bitmasks + fallback, DONE/PLACED success, failure retcode and None-result errors, magic filtering, `start_pos == 1` closed-bar fetch, healthy/failure connect paths, account mapping, and the Windows hint when the package is absent; an AST-level test guarantees no top-level `import MetaTrader5` anywhere in the module

## Task Commits

Each task was committed atomically:

1. **Task 1: MT5Broker — connect, fetch closed rates, account info** - `8d495ce` (feat)
2. **Task 2: MT5Broker order placement + pending/positions + DryRunBroker** - `b136e01` (feat)

**Plan metadata:** `pending` (docs: complete plan — this commit)

## Files Created/Modified
- `src/trading_bot/broker/mt5.py` - `MT5Broker` (connect/disconnect/fetch_rates/account_info/place_buy_stop/pending_orders/positions) + `_load_mt5()` guarded lazy import raising `BrokerUnavailableError` with a Windows hint
- `src/trading_bot/broker/dry_run.py` - `DryRunBroker`: delegates connect/fetch/account/pending/positions; `place_buy_stop` logs `order_plan` and never touches the inner broker
- `src/trading_bot/broker/__init__.py` - exports `MT5Broker` and `DryRunBroker` alongside the existing contract (still imports cleanly on macOS)
- `tests/test_mt5_broker.py` - 30 tests: `FakeMT5` module double (bit-exact constants, call recording, mutable flags), closed-bar fetch/start_pos, connect error paths, account mapping, request-dict contract, filling modes, retcode handling, pending/positions filtering, DryRunBroker no-send + logging + delegation, Windows-hint and no-top-level-import guards

## Decisions Made
- MetaTrader5 is imported only inside `_load_mt5()` — never at module top level. This makes the file import on macOS and is the seam the fake-module tests inject into (`sys.modules["MetaTrader5"] = FakeMT5`)
- `fetch_rates` uses `start_pos=1` to exclude the currently-forming bar — the live adapter mirrors the backtester's no-lookahead rule (RESEARCH.md)
- A `None` from `copy_rates_from_pos` is a normal fresh-start poll: empty OHLC frame returned (with a logged warning), not an exception
- Filling mode is per-symbol: `symbol_info().filling_mode` bitmask — IOC preferred, RETURN fallback, `ORDER_FILLING_IOC` as last resort (XAUUSD is 2-dp gold)
- Success is defined as retcode DONE(10009) or PLACED(10008); everything else raises `BrokerRejectedError` with the retcode and `last_error()` text
- Dry-run is a distinct wrapper type (`DryRunBroker`), not a mode flag inside MT5Broker — the wrapper's `place_buy_stop` contains zero references to the inner broker, making a leaked real order structurally impossible

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] FakeMT5.symbol-scoping fixed in the test double**
- **Found during:** Task 2 (pending_orders/positions tests)
- **Issue:** The initial FakeMT5 `orders_get`/`positions_get` returned all ledger entries regardless of the `symbol` argument, so the adapter's magic-only filter (correct per plan: real MT5 scopes by symbol server-side) produced unexpected tickets in tests.
- **Fix:** The fake now mirrors real MT5 semantics — `orders_get(symbol=...)`/`positions_get(symbol=...)` return only that symbol's entries (`None` when empty), exactly like the live API.
- **Files modified:** tests/test_mt5_broker.py
- **Verification:** magic-filter tests pass with symbol-scoped input; full suite green.
- **Committed in:** b136e01 (Task 2 commit)

**2. [Rule 3 - Blocking] Temporary abstract-method stubs required mid-plan**
- **Found during:** Task 1 (MT5Broker construction)
- **Issue:** `BrokerClient` declares 7 abstract methods but Task 1 only specified 4; an ABC with unimplemented abstract methods cannot be instantiated, so the Task 1 tests could not construct `MT5Broker`.
- **Fix:** The 3 order-lifecycle methods were stubbed with `NotImplementedError("lands in 02-02 task 2")` in Task 1 and replaced with the real implementations in Task 2.
- **Files modified:** src/trading_bot/broker/mt5.py
- **Verification:** Task 1 tests instantiate and exercise connect/fetch/account; Task 2 replaces the stubs; full suite green throughout.
- **Committed in:** 8d495ce + b136e01 (plan-internal task boundary, no residue)

---

**Total deviations:** 2 auto-fixed (1 test-double bug, 1 mid-plan structural necessity)
**Impact on plan:** None — both fixes serve the plan's own intent (faithful fake-module testing; instantiable ABC across atomic task commits). No scope creep.

## Issues Encountered
- Initial FakeMT5.`terminal_info` didn't record its call (missing `cls.calls.append`), which surfaced as a confusing connect-path test failure — fixed before committing Task 1.
- The wave-2 parallel plan 02-03 landed mid-execution (commit `819ba51`, `src/trading_bot/live/` safety guard + test_safety.py, no file overlap with this plan); the suite baseline moved 60 → 69 tests and ended at 99 total. No conflicts.

## User Setup Required
None - no external service configuration required. (Real-terminal verification of MT5Broker is the 02-06 human checkpoint on a Windows machine, per the phase plan.)

## Next Phase Readiness
- `MT5Broker` and `DryRunBroker` both implement `BrokerClient`, so 02-04 (live engine) can construct the right broker per `cfg.live.mode`: `DryRunBroker(SimulatedBroker)` for dry-run, `MT5Broker` for demo/live — and the safety guard from 02-03 (`verify_execution_allowed`, already landed in parallel) wraps placement
- The fake-module test pattern is reusable for any future MT5-surface additions (e.g., order cancellation for SL/TP management)
- All tests green: 99 total (30 mt5 broker + 9 safety from 02-03 + 60 prior)
- Real-terminal behavior (initialize/terminal_info/symbol_select against an actual Windows MT5 terminal) is deliberately not covered here — that is the 02-06 checkpoint

---
*Phase: 02-live-execution-mt5-order-placement-safety*
*Completed: 2026-08-11*
