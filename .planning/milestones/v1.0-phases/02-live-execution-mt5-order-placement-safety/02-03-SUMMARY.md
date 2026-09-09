---
phase: 02-live-execution-mt5-order-placement-safety
plan: 03
subsystem: safety
tags: safety, demo-enforcement, mt5, trade-mode, dry-run, opt-in

# Dependency graph
requires:
  - phase: 02-01 (broker foundation)
    provides: Config with [live] enabled/mode schema + AccountInfo.trade_mode from broker.base
provides:
  - SAFE-03 execution guard: verify_execution_allowed(cfg, account) — dry-run early return, REAL-account opt-in, demo-mode block
  - live/ package scaffold (engine.py deferred to 02-04)
affects: [02-04 live engine, 02-05 E2E demo replay, 02-06 real-terminal verification]

# Tech tracking
tech-stack:
  added: none
  patterns:
    - "Pure guard function: no logging, no broker access, no MetaTrader5 import (TYPE_CHECKING-only type refs)"
    - "MT5 ACCOUNT_TRADE_MODE_* values mirrored as module constants so safety.py stays macOS-importable"

key-files:
  created:
    - src/trading_bot/live/__init__.py
    - src/trading_bot/live/safety.py
    - tests/test_safety.py
  modified: none

key-decisions:
  - "Safety guard is a pure yes/no function; the engine decides what to do with SafetyError (log + skip)"
  - "Check order: dry-run first (never sends), then REAL-account opt-in, then demo-mode block"
  - "No-import contract tested by grepping source for import statements (docstring may name MetaTrader5 to explain the rationale)"

patterns-established:
  - "Guard purity: safety.py imports nothing at runtime beyond stdlib; type-only imports via TYPE_CHECKING"
  - "8-case parametrized decision matrix — every mode x account combination locked by tests"

# Metrics
duration: 5 min
completed: 2026-08-11
---

# Phase 2 Plan 3: SAFE-03 Demo-Only Execution Guard Summary

**Pure, single-function demo/live safety guard (`verify_execution_allowed`) that the engine calls before every order placement — dry-run never sends, REAL accounts require the explicit `[live] enabled=true` opt-in, and mode='demo' blocks real accounts, with 8-case parametrized coverage and zero MetaTrader5 import**

## Performance

- **Duration:** 5 min
- **Started:** 2026-08-11T07:47:00Z (approx.)
- **Completed:** 2026-08-11T07:52:14Z
- **Tasks:** 1
- **Files modified:** 3 created

## Accomplishments
- `live/safety.py`: `SafetyError` + `ACCOUNT_TRADE_MODE_DEMO/REAL` constants + `verify_execution_allowed(cfg, account)` encoding all three SAFE-03 rules in one pure function
- Check ordering: dry-run early return first (DryRunBroker is the actual no-send seam from plan 02), then REAL-account opt-in (Rule 2), then demo-mode block (Rule 3)
- Error messages name the exact config key to change (`live.enabled=false`, `[live] enabled=true`) for actionable operator feedback
- `tests/test_safety.py`: 8 parametrized mode × account combinations + a purity test asserting safety.py never imports MetaTrader5 (grep for `import MetaTrader5`/`from MetaTrader5` — the docstring may name it to explain why it's absent)
- Full suite grew 60 → 69 tests, all green on macOS

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement verify_execution_allowed safety guard** - `819ba51` (feat)

**Plan metadata:** `docs(02-03)` commit follows with SUMMARY + STATE.

## Files Created/Modified
- `src/trading_bot/live/__init__.py` - Package scaffold (docstring only; engine.py is plan 02-04's)
- `src/trading_bot/live/safety.py` - SAFE-03 guard: SafetyError, trade-mode constants, verify_execution_allowed
- `tests/test_safety.py` - 8-case parametrized decision matrix + no-MetaTrader5-import purity test

## Decisions Made
- Safety guard is a **pure yes/no function**: no logging, no broker access, no MetaTrader5 import (TYPE_CHECKING-only type references). The ENGINE decides what to do with `SafetyError` (log + skip); the guard only decides. Keeps SAFE-03 single-purpose and macOS-testable.
- Check order is dry-run → REAL-opt-in → demo-block, per plan; Rule 2 precedes Rule 3 so `mode=demo + REAL + enabled=false` reports the opt-in gate first.
- No-import contract is enforced by grepping the source for import statements rather than the bare word "MetaTrader5", so the docstring can document *why* the package is never imported.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- The purity test initially failed because the module docstring contains the word "MetaTrader5" (explaining the Windows-only rationale). The test was tightened to assert on import statements specifically (`import MetaTrader5` / `from MetaTrader5` absent) — this still satisfies the plan's "does not import MetaTrader5" contract and the success criterion "No MetaTrader5 import in safety.py".

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- 02-04 (live engine) can import `verify_execution_allowed` and call it before every `place_buy_stop`; the guard's early return documents the dry-run path where DryRunBroker (02-02) is the no-send seam.
- 02-02 (MT5Broker + DryRunBroker) was executing in parallel (wave 2) — its Summary should be consulted when the engine plan lands so the seams line up.
- Real-terminal verification remains deferred to 02-06 human checkpoint (Windows), unchanged.

---
*Phase: 02-live-execution-mt5-order-placement-safety*
*Completed: 2026-08-11*
