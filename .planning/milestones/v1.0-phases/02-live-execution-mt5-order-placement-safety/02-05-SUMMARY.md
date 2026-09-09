---
phase: 02-live-execution-mt5-order-placement-safety
plan: 05
subsystem: cli
tags: cli, live-bot, dry-run, broker-factory, e2e, decision-log, polling-loop

# Dependency graph
requires:
  - phase: 02-01 (broker foundation)
    provides: SimulatedBroker cursor semantics, OrderRequest/OrderResult, BrokerClient ABC
  - phase: 02-02 (MT5 adapter + dry-run)
    provides: MT5Broker (lazy guarded import), DryRunBroker no-send seam (ticket=0/placed=False)
  - phase: 02-03 (safety guard)
    provides: verify_execution_allowed — SAFE-03 demo-only enforcement at the engine boundary
  - phase: 02-04 (LiveEngine)
    provides: poll_once()/on_setup() event contract (order_placed/order_skipped/order_rejected) and the golden-frame walk conventions
provides:
  - `python -m trading_bot.cli live` subcommand: --once, --mode override, config-driven params, interval loop with clean KeyboardInterrupt stop
  - build_broker(cfg) broker-by-mode factory: dry-run -> DryRunBroker(SimulatedBroker); demo/live -> MT5Broker
  - Graceful MT5-unavailable: actionable stderr message + live_stop log + exit 1 (EXEC-01)
  - Decision log output/live.log: live_start/live_stop + engine trail (SAFE-02)
  - E2E dry-run proof over the golden frame: one order event with backtest-identical prices, empty inner ledger, dedup blocks re-trigger
affects: [02-06 real-terminal verification (human checkpoint, Windows), phase 3 if CLI-driven]

# Tech tracking
tech-stack:
  added: none
  patterns:
    - "Broker-by-mode factory in the CLI (build_broker): dry-run wraps a fresh SimulatedBroker; demo/live use MT5Broker — no new module"
    - "dataclasses.replace to apply a --mode override onto the frozen Config"
    - "E2E walk rewinds SimulatedBroker._cursor to 0 and advances the INNER broker (advance() is not on the ABC)"

key-files:
  created:
    - tests/test_cli_live.py
  modified:
    - src/trading_bot/cli.py
    - tests/test_cli.py

key-decisions:
  - "build_broker lives in cli.py (module-level function), not a new module — one factory, three modes"
  - "Dry-run never connects: SimulatedBroker.connect() is a no-op and bar_fetch_failed until data exists is the documented dry-run-on-macOS behavior; the E2E test seeds the golden frame"

patterns-established:
  - "live --once prints a one-line poll summary via _summarize(result)"
  - "Clean stop: KeyboardInterrupt -> live_stop reason=keyboard_interrupt + 'stopped' + exit 0; broker errors -> live_stop + exit 1"

# Metrics
duration: 5 min
completed: 2026-08-11
---

# Phase 2 Plan 5: CLI `live` Subcommand + E2E Dry-Run Summary

**`python -m trading_bot.cli live` with a broker-by-mode factory (dry-run → DryRunBroker no-send seam, demo/live → MT5Broker), interval poll loop with clean stop, structured live.log decision trail, and an E2E golden-frame dry-run proving correct prices, empty real ledger, and dedup-blocked re-triggers**

## Performance

- **Duration:** 5 min
- **Started:** 2026-08-11T08:06:36Z
- **Completed:** 2026-08-11T08:10:11Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- `live` CLI subcommand with `--once`, `--mode {dry-run,demo,live}` override, and config-driven params (symbol, timeframe, magic, lot, poll_interval) — phase success criterion 1
- `build_broker(cfg)` factory: dry-run wraps a fresh `SimulatedBroker` in the `DryRunBroker` no-send seam (criterion 4); demo/live use `MT5Broker` — graceful `BrokerUnavailableError` on connect → actionable stderr message + `live_stop` + exit 1 (EXEC-01)
- Interval loop with clean `KeyboardInterrupt` stop (`stopped` + exit 0) and every decision written to `output/live.log` (SAFE-02)
- E2E dry-run test over the golden frame: exactly one `order_placed` (ticket=0) with the hand-computed backtest prices (entry=101.00, sl=100.09, tp=101.91), empty inner ledger, full `setup_detected`/`order_placed`/`bar_check` decision trail at 2-dp prices, and a seeded-equivalent-pending dedup scenario proving `order_skipped` blocks re-triggering (criterion 5)

## Task Commits

Each task was committed atomically:

1. **Task 1: CLI `live` subcommand + broker factory** - `a271e10` (feat)
2. **Task 2: E2E dry-run over golden frame + decision-log assertions** - `e6ec1f1` (test)

**Plan metadata:** `docs(02-05)` (this commit)

## Files Created/Modified

- `src/trading_bot/cli.py` - `live` subparser (--config/--once/--mode), `build_broker(cfg)` factory, `_run_live` with graceful MT5-unavailable + clean stop, `_summarize` one-line poll summary; `backtest` path untouched (exit codes 0/1/2 preserved)
- `tests/test_cli.py` - `[live]` table added to tmp-config helper; 3 new tests: bad `--mode` → SystemExit(2), dry-run `--once` → 0 with `live_start` + `bar_fetch_failed` in log, missing config → 1 with `error:` on stderr
- `tests/test_cli_live.py` - E2E golden-frame dry-run walk (no-send + full trail + JSON-plain events) and the dedup-blocked scenario

## Decisions Made

- `build_broker` lives in cli.py as a module-level function (plan-mandated: no new module); dry-run uses a fresh `SimulatedBroker(trade_mode=0)` so the seam structurally cannot touch a real account
- Dry-run on macOS polls against an empty broker: `bar_fetch_failed` is the documented, expected first-poll outcome (only the E2E test seeds data)
- `--mode` override rebuilds the frozen config via `dataclasses.replace(cfg, live=replace(cfg.live, mode=...))` — verified live via `live --once --mode demo` → graceful connect failure + exit 1

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] E2E walk started at cursor 12 (end of frame), not the start**

- **Found during:** Task 2 (E2E dry-run walk)
- **Issue:** `SimulatedBroker._cursor` initializes to `len(rates)`, so the plan's bare `for _ in range(len(golden_df)): poll; advance()` loop never replayed the setup bar — the last closed bar stayed idx 11 and no `order_placed` ever fired
- **Fix:** `_walk` rewinds `inner._cursor = 0` before the loop (same convention as test_live_engine's `_walk_to_setup` warm-cursor seeding)
- **Files modified:** tests/test_cli_live.py
- **Verification:** walk now emits exactly one `order_placed` at idx 6 with the golden prices; both E2E tests green
- **Committed in:** e6ec1f1 (Task 2 commit)

**2. [Rule 1 - Bug] E2E walk called `broker.advance()` on DryRunBroker**

- **Found during:** Task 2 (E2E dry-run walk)
- **Issue:** `advance()` is SimulatedBroker-specific and not on the BrokerClient ABC, so DryRunBroker has no such attribute — `AttributeError`
- **Fix:** the walk advances the INNER broker directly (`inner.advance()`), keeping the ABC wrapper decoupled from simulated-only semantics
- **Files modified:** tests/test_cli_live.py
- **Verification:** both E2E tests pass; no ABC change needed
- **Committed in:** e6ec1f1 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs in the new test's walk driver)
**Impact on plan:** Both were test-driver issues, not product-code issues; zero scope creep, zero product code changed beyond the plan.

## Issues Encountered

- Shell background-job SIGINT is ignored (POSIX `&` semantics), so the interactive clean-stop check needed an in-process `SIGALRM`-raised KeyboardInterrupt harness — verified `stopped` + exit 0 + `live_stop reason=keyboard_interrupt` in `output/live.log`

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase success criteria 1 and 4 met: a person can run the bot (`live --once` / interval loop) and dry-run provably places nothing while logging the full decision trail
- EXEC-01 graceful degradation proven on macOS (MT5 absent → actionable message, exit 1)
- Ready for 02-06: the real-terminal human checkpoint (Windows) — `live` in demo/live mode calls `MT5Broker.connect()` and the engine's SAFE-03 gate, both already exercised by tests

---
*Phase: 02-live-execution-mt5-order-placement-safety*
*Completed: 2026-08-11*
