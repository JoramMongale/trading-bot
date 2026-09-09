---
phase: 02-live-execution-mt5-order-placement-safety
plan: 01
subsystem: broker
tags: [toml, dataclasses, abc, pandas, simulated-broker, mt5]

# Dependency graph
requires:
  - phase: 01-strategy-core-detection-backtest
    provides: pure strategy functions (swings/levels/signals) and the OHLC
      DataFrame shape (columns open/high/low/close, datetime index named
      "time") that the BrokerClient.fetch_rates contract now matches
provides:
  - [live] config table with per-key validation and dry-run-safe defaults (EXEC-03, SAFE-03)
  - BrokerClient ABC + dataclasses (AccountInfo, OrderRequest, OrderResult, PendingOrder, Position) + broker errors
  - SimulatedBroker: in-memory, cursor-based closed-bar broker for tests/dry-run/E2E replay
affects: [mt5-adapter, safety-guard, live-engine, cli, e2e-replay] — every downstream Phase 2 piece programs against BrokerClient

# Tech tracking
tech-stack:
  added: none (stdlib tomllib/abc/dataclasses; pandas already a dependency)
  patterns:
    - Broker abstraction over raw MT5 calls; adapters implement BrokerClient, strategy never touches broker internals
    - Cursor-based simulated time: fetch_rates returns closed bars ending at _cursor; advance() closes the next bar
    - Config growth via DEFAULT_LIVE merged with raw.get("live", {}) — schema grows without breaking legacy configs

key-files:
  created:
    - src/trading_bot/broker/base.py
    - src/trading_bot/broker/simulated.py
    - src/trading_bot/broker/__init__.py
    - tests/test_config.py
    - tests/test_broker_simulated.py
  modified:
    - src/trading_bot/config.py
    - config/config.toml

key-decisions:
  - "live.enabled is the explicit opt-in for REAL accounts; mode narrows to dry-run/demo/live (SAFE-03)"
  - "Legacy configs without [live] load via LiveConfig(**{**DEFAULT_LIVE, **raw.get('live', {})})"
  - "PendingOrder.equivalent_to dedups re-triggers on symbol+magic+entry within 0.01 (XAUUSD 2-dp tolerance)"
  - "SimulatedBroker._cursor starts at len(rates): the forming bar is excluded, matching live closed-bar semantics"

patterns-established:
  - "Broker interface first: every live component (MT5 adapter, safety guard, engine, CLI) programs against BrokerClient"
  - "SimulatedBroker drives dry-run and E2E replay: advance() simulates new closed bars arriving"
  - "Validation errors name the bad key (live.mode=..., live.magic_number=...) — matches Phase 1 config style"

# Metrics
duration: 2min
completed: 2026-08-11
---

# Phase 2 Plan 1: Broker Foundation + Config Schema Summary

**[live] config table with per-key validation plus a BrokerClient ABC and cursor-based SimulatedBroker — the typed broker abstraction every Phase 2 live component (MT5 adapter, safety guard, engine, CLI) programs against, testable on this macOS machine**

## Performance

- **Duration:** 2 min
- **Started:** 2026-08-11T07:47:25Z
- **Completed:** 2026-08-11T07:48:45Z
- **Tasks:** 2
- **Files modified:** 7 (3 created source, 2 created tests, 2 modified)

## Accomplishments
- `[live]` config table (enabled/mode/magic_number/deviation/poll_interval/comment) with frozen `LiveConfig`, dry-run defaults, and ValueError naming the bad key; legacy configs without the table still load (backward compatible — the existing `test_cli.py` tmp configs without `[live]` prove it in the suite)
- `BrokerClient` ABC with the full Phase 2 contract: connect/disconnect/fetch_rates/account_info/place_buy_stop/pending_orders/positions, plus frozen dataclasses (`AccountInfo`, `OrderRequest` with `to_log_fields()`, `OrderResult`, `PendingOrder` with `equivalent_to()`, `Position`) and broker error hierarchy (`BrokerError` → `BrokerUnavailableError`/`BrokerRejectedError`)
- `SimulatedBroker`: in-memory implementation whose `_cursor` simulates "now" — `fetch_rates` returns only closed bars ending at the cursor, `advance()` closes the next bar (drives the E2E replay in later plans), `simulate_fill()`/`simulate_position()` seed dedup and one-trade-at-a-time tests
- Zero references to the Windows-only MT5 package anywhere in the new broker package (verified by grep after docstring wording cleanup)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add [live] config schema + validation (EXEC-03)** - `7097ed2` (feat)
2. **Task 2: Broker abstraction — base types + SimulatedBroker** - `7847dba` (feat)

**Plan metadata:** `pending` (docs: complete plan — this commit)

## Files Created/Modified
- `src/trading_bot/config.py` - `LiveConfig` frozen dataclass + `DEFAULT_LIVE` merged with `raw.get("live", {})`; `_validate` extended with live rules; `Config.live` field
- `config/config.toml` - new `[live]` table with SAFE-03-safe defaults (enabled=false, dry-run)
- `src/trading_bot/broker/base.py` - BrokerClient ABC, dataclasses, error hierarchy
- `src/trading_bot/broker/simulated.py` - SimulatedBroker with cursor/advance/ledger + test helpers
- `src/trading_bot/broker/__init__.py` - public re-exports of the broker contract
- `tests/test_config.py` - 12 tests: committed defaults, per-key errors (mode/magic_number/deviation/poll_interval incl. non-int), valid modes, missing-[live] backward compat
- `tests/test_broker_simulated.py` - 9 tests: closed-bar shape, cursor windowing + advance, unavailable error, ledger tickets, symbol/magic filters, fill expiry, dedup equivalence, log fields, abstractness

## Decisions Made
- `live.enabled` is the explicit opt-in that permits REAL-account execution; `mode` narrows further to dry-run/demo/live (SAFE-03 design preserved in the schema)
- Legacy phase-1 configs must keep loading: `LiveConfig(**{**DEFAULT_LIVE, **raw.get("live", {})})`
- `PendingOrder.equivalent_to` dedups re-triggers on symbol+magic+entry within 0.01 (XAUUSD 2-dp tolerance) — later plans use it to avoid double-placing the same setup
- `SimulatedBroker._cursor` starts at `len(rates)` so the forming bar is excluded exactly like live closed-bar semantics
- `magic_number`/`deviation` validated as `int >= 0` with an isinstance check (TOML floats like `77001.5` rejected)

## Deviations from Plan

### Plan-text discrepancies (no code deviation)

**1. `tests/test_config.py` did not exist — created instead of "extended"**
- **Found during:** Task 1
- **Issue:** The plan's `<files>` list references `tests/test_config.py` and the action says "extend the existing file", but no config test file exists in the repo (config behavior was only covered indirectly via test_cli.py fixtures).
- **Fix:** Created `tests/test_config.py` with the full planned test list (committed defaults, per-key errors, missing-table backward compat) plus two low-cost positives (valid modes accepted, non-int magic/deviation rejected per the "must be an int" rule).
- **Verification:** 12/12 config tests pass; the suite's existing `test_cli.py` tmp-configs (which omit `[live]`) exercise the backward-compat path end-to-end.

**2. Docstring references to "MetaTrader5" removed**
- **Found during:** Task 2 (done-criteria check)
- **Issue:** The done criterion requires the broker package to contain *no MetaTrader5 reference anywhere*, but initial docstrings mentioned the package name in prose explaining why it is not imported.
- **Fix:** Reworded docstrings to "the live MT5 pip package / the live MT5 adapter" — the files now contain zero occurrences of the name (verified by grep).
- **Verification:** `grep MetaTrader5 src/trading_bot/broker/` → no matches; full suite still green.

---

**Total deviations:** 2 plan-text discrepancies handled inline (0 code-behavior deviations)
**Impact on plan:** None — both changes serve the plan's own stated intent (test coverage for the [live] schema; a literally clean broker package).

## Issues Encountered
None — implementation matched the plan on the first pass; no debugging was required.

## User Setup Required
None - no external service configuration required (the MT5 terminal/adapter is a later plan and stays out of scope here).

## Next Phase Readiness
- Config schema supports live execution (`[live]` table + validation) — plan 02-02+ can read `cfg.live` for engine/CLI wiring
- Broker interface + SimulatedBroker are the test backbone for the MT5 adapter (02-03), safety guard (02-04), and live engine (02-05/02-06): everything downstream tests against `BrokerClient`, never raw MT5 calls
- `PendingOrder.equivalent_to` and `positions()` are ready for the re-trigger dedup and one-trade-at-a-time safety rules
- No blockers. Test count 39 → 60 (12 config + 9 broker).

---
*Phase: 02-live-execution-mt5-order-placement-safety*
*Completed: 2026-08-11*
