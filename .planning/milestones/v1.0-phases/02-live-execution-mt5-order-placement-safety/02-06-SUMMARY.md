---
phase: 02-live-execution-mt5-order-placement-safety
plan: 06
subsystem: live-execution
tags: [mt5, metatrader5, windows, demo-account, safety, live-engine, deferral]

# Dependency graph
requires:
  - phase: 02-05 (CLI live subcommand + E2E dry-run)
    provides: the `live` CLI (dry-run/demo/live modes), DryRunBroker no-send seam, golden-frame E2E
  - phase: 02-04 (LiveEngine poll-setup-place)
    provides: LiveEngine poll loop, dedup (pending-equiv/position/same-bar), SAFE-03 gate, order logging
  - phase: 02-02 (MT5 real adapter + dry-run wrapper)
    provides: MT5Broker adapter (guarded lazy import, start_pos=1 closed bars, order_send Buy Stop) + 30 fake-MT5 unit tests
  - phase: 02-01 (live config + safety guard)
    provides: [live] config schema (enabled/mode/magic_number/...) and pure verify_execution_allowed guard
provides:
  - Documented DEFERRAL of real-terminal verification with the dry-run + fake-MT5 path accepted as Phase 2's verification
  - A runnable Windows verification checklist (steps 1-5 from this plan's how-to-verify) for future execution when a Windows/MT5 environment exists
  - Known state: MT5Broker is code-complete and unit-tested (30 fake-module tests) but NOT round-trip verified against a real terminal
affects: [03-live-or-demo (phase 3: going live with real accounts), future Windows-based integration plans]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Deferred human-verify close: when a platform-locked verification cannot run on the dev machine, the plan closes as DEFERRED with the automatable test path recorded as accepted verification"
    - "Windows-only integration verified via fake-module (sys.modules injection) unit tests + dry-run E2E on macOS; DLL round-trip remains the documented open item"

key-files:
  created:
    - .planning/phases/02-live-execution-mt5-order-placement-safety/02-06-SUMMARY.md
  modified:
    - .planning/STATE.md

key-decisions:
  - "02-06 real-terminal verification DEFERRED (not passed): user has no Windows/MT5 environment (macOS only)"
  - "Accepted verification for Phase 2: dry-run E2E over the golden frame (entry=101.00, sl=100.09, tp=101.91 exact 1:1) + 30 fake-MT5 adapter tests + 8-case SAFE-03 guard matrix + 115-test suite green"
  - "Windows verification steps 1-5 are preserved verbatim in this summary for a future Windows run"

patterns-established:
  - "Deferred plans still produce a SUMMARY.md documenting what was and was not verified, so the open verification item survives into future planning context"

# Metrics
duration: 5 min
completed: 2026-08-11
---

# Phase 2 Plan 6: Real MT5 Verification Summary

**DEFERRED (not passed) — real-terminal round-trip verification of the MT5Broker adapter is closed as deferred on macOS; the dry-run + fake-MT5 verification path is the accepted verification for Phase 2, with the Windows steps preserved for future execution**

## Performance

- **Duration:** 5 min (checkpoint response processing + documentation)
- **Started:** 2026-08-11 (checkpoint presented earlier; user responded "deferred")
- **Completed:** 2026-08-11
- **Tasks:** 1 of 1 (checkpoint:human-verify) — closed via <resume-signal> "deferred"
- **Files modified:** 1 (.planning/STATE.md) + 1 created (this summary)

## Status: DEFERRED

This plan was a human-verify checkpoint for the real MT5 integration, which requires a
Windows machine with the MetaTrader5 Python package and a running MT5 terminal. The user
confirmed they are on macOS with **no Windows/MT5 environment available**, so per the plan's
`<resume-signal>` the dry-run + fake-MT5 verification on macOS is the **accepted verification**
for this phase and this plan is **closed as deferred** — NOT passed.

## What Was Verified Instead (accepted verification)

| Area | Verification | Where |
|------|-------------|-------|
| Adapter logic (DLL-level behavior) | 30 fake-MT5 unit tests — guarded lazy import, start_pos=1 closed-bar fetch, order_send Buy Stop with retcode DONE/PLACED success, IOC→RETURN filling fallback, none→empty-frame handling | `tests/test_mt5_broker.py` |
| Full dry-run E2E over the golden frame | Exactly one order event at idx 6 with entry=101.00 (resistance), sl=100.09, tp=101.91 (exact 1:1 R:R, STRAT-03); DryRunBroker logs `event=order_plan` and places nothing; decision log carries the rounded prices | `tests/test_cli_live.py` |
| SAFE-03 guard | 8-case matrix: dry-run never blocks; demo+REAL refused ("REAL"); live+REAL refused unless `enabled=true`; live+demo always allowed; guard module imports no MetaTrader5 | `tests/test_safety.py` |
| Full suite | 115 tests green (39 phase-1 + 12 config + 9 broker + 30 mt5-broker + 9 safety + 11 live engine + 3 cli-live + 2 cli-live-e2e) | `pytest` |

## What Was NOT Verified (the deferred item)

- **MT5Broker round-trip against a real terminal:** connecting via `initialize()`, receiving real
  XAUUSD 5m bars through `copy_rates_from_pos`, and placing a real pending Buy Stop via
  `order_send` on a demo account. The adapter is **code-complete and unit-tested** but has not
  been exercised against the actual Windows DLL.
- Real-terminal filling-mode observation, server-time offset, and retcode quirks (per the plan's
  `<verification>` note, these would only be captured on an approved Windows run).

## Windows Verification Steps (preserved for future execution)

When a Windows machine with MT5 running on a DEMO account is available:

1. Copy the project, create a venv, `pip install -e ".[dev]"` and `pip install MetaTrader5`.
2. `.venv\Scripts\python -m trading_bot.cli live --once --mode dry-run` — expect exit 0,
   `output/live.log` with `event=live_start` and `event=bar_fetch_failed` or `bar_check` (no crash).
3. `.venv\Scripts\python -m trading_bot.cli live --mode demo` for 1-2 minutes — expect
   `event=live_start`, repeated `event=bar_check new_bar=True setup=False/True` with real prices,
   and on a setup `event=order_placed` with a real ticket OR `event=order_skipped` with a reason;
   verify the pending order appears in the terminal's "Trading" tab with correct entry/SL/TP.
4. Safety-guard check: `[live] mode="live"`, `enabled=false` on a REAL account — expect refusal
   (`order_skipped reason=safety_blocked`) and no order reaching the terminal; `enabled=true`
   allows it (only with explicit user consent for live-account testing).
5. Dedup check: with a Buy Stop already pending at the same entry, a subsequent identical setup
   produces `order_skipped reason=pending_order_equivalent` and no duplicate order.

## Accomplishments

- Phase 2 closed: all 6 plans now complete (5 passed + 1 deferred) — the phase's success criteria are met via the accepted dry-run/fake-MT5 verification path.
- The open verification item (real DLL round-trip) is explicitly documented in STATE.md so a future Windows run is a self-contained follow-up, not a lost thread.
- The Windows checklist survives verbatim in this summary — no re-derivation needed later.

## Task Commits

1. **Task 1: Verify real MT5 connection, live bars, demo order, and safety guard on Windows** — *no commit* (checkpoint:human-verify; closed by user's "deferred" response — no code changes)

**Plan metadata:** (see below — single docs commit for this deferred close)

## Files Created/Modified

- `.planning/phases/02-live-execution-mt5-order-placement-safety/02-06-SUMMARY.md` - Deferred-close documentation; preserves Windows verification steps and accepted-verification record
- `.planning/STATE.md` - Position updated (6/6 plans in phase 2, 02-06 deferred), deferral decision added, blockers updated, session continuity refreshed

## Decisions Made

- **Defer real-terminal verification (user-confirmed, macOS only).** The MetaTrader5 package is Windows-only; no Windows/MT5 environment exists for the user. The plan's `<resume-signal>` explicitly accepts "deferred" as a valid close with the dry-run + fake-MT5 verification as the phase's accepted verification. Documented as a state decision so Phase 3 / future planning knows the DLL round-trip remains unverified.

## Deviations from Plan

None - plan executed as written: the human-verify checkpoint was presented, the user responded
"deferred" per the resume-signal, and the plan is closed as deferred. No code changes were needed.

## Issues Encountered

None — the checkpoint functioned exactly as designed: platform-locked verification surfaced to the
user, the user declared the environment unavailable, and the plan closed via its documented deferral path.

## User Setup Required

**Deferred follow-up — Windows environment needed for real-terminal verification:**

- Windows machine with MT5 terminal installed and logged in to a DEMO account (e.g. MetaQuotes-Demo)
- `pip install MetaTrader5` (Windows wheels available)
- Ensure XAUUSD appears in MarketWatch (or let `symbol_select` add it)
- Then run the 5-step checklist above

No USER-SETUP.md was generated — this plan's setup steps are captured inline (above) and in the
original 02-06-PLAN.md `user_setup` frontmatter.

## Next Phase Readiness

- **Phase 2 is complete** (6/6 plans: 02-01..02-05 passed, 02-06 deferred). The full live-execution
  stack — BrokerClient abstraction, MT5Broker, SimulatedBroker, DryRunBroker, LiveEngine, SAFE-03
  guard, and the `live` CLI — is code-complete, unit-tested (115 tests green), and dry-run E2E verified.
- **Blocking follow-up for going live (Phase 3):** the MT5Broker DLL round-trip
  (connect → real bars → real pending Buy Stop on demo) has NOT been verified against a real
  terminal. Before any real-account demo trading, execute the preserved Windows checklist and record
  filling-mode / server-time / retcode observations in STATE.md decisions.
- No other blockers.

---
*Phase: 02-live-execution-mt5-order-placement-safety*
*Completed: 2026-08-11*
