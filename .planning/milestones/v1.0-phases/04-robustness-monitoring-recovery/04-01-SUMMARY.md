---
phase: 04-robustness-monitoring-recovery
plan: 01
subsystem: robustness
tags: [reconnect, weekend-guard, market-closure, trade-ledger, live]

# Dependency graph
requires:
  - phase: 01-strategy-core-detection-backtest
    provides: strategy chain (swings/levels/signals) and backtest conventions
  - phase: 02-live-execution-mt5-order-placement-safety
    provides: BrokerClient ABC (connect/disconnect/reconnect/fetch_rates/account_info),
      MT5Broker/SimulatedBroker/DryRunBroker, LiveEngine poll loop, SAFE-03 guard
provides:
  - Reconnect-after-disconnect with backoff ([live] reconnect_after / reconnect_backoff; BrokerClient.reconnect)
  - Weekend guard ([live] weekend_stop_hour / weekend_resume_hour; pure in_weekend helper)
  - Market-closure survival (empty frames stay quiet bar_checks; no reconnect churn)
  - scripts/trade_ledger.py — merged backtest + live/demo trade ledger (output/ledger.csv)
affects: [live trading operations (gold cent + btc), operator visibility via the merged ledger]

# Tech tracking
tech-stack:
  added: none (stdlib; reuses existing broker/live packages)
  patterns:
    - "Reconnect is owned by the CLI poll loop (single source of truth); engine + adapters only report availability"
    - "MT5Broker.fetch_rates raises BrokerUnavailableError when the terminal reports disconnected; a connected terminal returning None stays a normal no-data poll (market closure)"
    - "Reconnect runs the full connect() verification again (reachable, trade_allowed, install path) so the wrong-terminal guard stays loud"
    - "Weekend suppression mirrors the in_session model: detection keeps running, only acting is suppressed (setup_skipped reason=weekend)"
    - "trade_ledger.py reconstructs entry/SL/TP from decision-log order_placed fields (same stops_from_logs idea as account_report.py), joined to closes by ticket"

key-files:
  created:
    - scripts/trade_ledger.py
    - tests/test_trade_ledger.py
  modified:
    - src/trading_bot/live/engine.py (in_weekend, market-closure handling)
    - src/trading_bot/broker/base.py (reconnect on BrokerClient ABC)
    - src/trading_bot/broker/mt5.py (reconnect override, None-while-disconnected raises)
    - src/trading_bot/config.py ([live] reconnect_after/reconnect_backoff/weekend_stop_hour/weekend_resume_hour)
    - config/config-cent.toml (weekend guard enabled: stop 19, resume 21)
    - src/trading_bot/cli.py (consecutive-failure reconnect counter in the live loop)

key-decisions:
  - "Reconnect storms mitigated by reconnect_after gating + reconnect_backoff sleep between failed reconnects"
  - "Reconnect re-verifies the attached terminal path against [live] terminal_path — never silently re-attaches the wrong install"
  - "Weekend guard is config-gated and off by default; enabled for gold (stop 19, resume 21), left off for 24/7 BTC"
  - "A dead terminal is surfaced as BrokerUnavailableError so the reconnect path can see it; empty frames from a connected terminal remain quiet (market closed)"

patterns-established:
  - "A bot that is alive but never reconnects has quietly stopped trading — the reconnect counter closes that class of failure"
  - "Bar timestamps are the broker's clock; the weekend guard reads the bar's own time, not the host clock"
  - "Operational shutdown (weekends, closures) is expressed in code, not just external scheduled tasks"

# Metrics
duration: ~1 session
completed: 2026-08-27
---

# Phase 3 (Roadmap) / Plan 04-01: Robustness — Reconnect, Weekend Guard, Market Closure, Trade Ledger

**A bot you can leave running: detects and recovers from terminal disconnects with backoff, refuses fresh gold entries into the weekend gap, survives extended market closures without error spam, and exposes a single merged backtest + live trade ledger — verified 2026-08-27 (24 new tests; full suite 404 passed + 2 skipped)**

## Performance

- **Status:** COMPLETE — verified 2026-08-27
- **Tasks:** 4 capability areas (reconnect, weekend guard, market closure, trade ledger)
- **Suite:** 24 new tests; full suite 404 passed + 2 skipped (the 1 dashboard failure is pre-existing environmental)

## Accomplishments

- **Reconnect after disconnect:** `[live] reconnect_after` (default 3) + `reconnect_backoff` (default 30.0). The CLI live loop counts consecutive `bar_fetch_failed` polls; at the threshold it calls `broker.reconnect()` — new on the BrokerClient ABC (default disconnect+connect, overridden in MT5Broker to drop the cached transport first). Reconnect re-runs full `connect()` verification. Logged `reconnect_attempt` / `reconnected` / `reconnect_failed`. The engine's `_last_bar_time` dedup boundary survives the drop, so a stale pre-drop bar is never re-traded.
- **Dead-terminal detection:** `MT5Broker.fetch_rates` raises `BrokerUnavailableError` when the terminal reports disconnected (previously returned an empty frame, so reconnect never fired). A connected terminal returning None stays a normal no-data poll — market closures do not churn reconnects.
- **Weekend guard:** `[live] weekend_stop_hour` (default 0 = off) / `weekend_resume_hour` (default 21) with pure `in_weekend(bar_time, stop_hour, resume_hour)`. A setup firing inside the window is logged `setup_skipped reason=weekend` and never placed. Enabled for gold in `config/config-cent.toml` (stop 19, resume 21); BTC (24/7) stays off.
- **Market-closure survival:** repeated empty frames are quiet `bar_check new_bar=False` events (no error spam, no reconnect churn); the first bar after the gap is processed normally.
- **Trade ledger:** `scripts/trade_ledger.py` — read-only merge of `output/trades.csv` (backtest) + `output/live_*.log` `order_placed` lines (live) + `output/closes.log` `trade_closed` lines joined by ticket → `output/ledger.csv` + printed summary. `--once` prints only; `--json` dumps the summary.
- **Config validation** for all four new keys with defaults off/safe.

## Verification

- `tests/test_live_engine.py`: `in_weekend` pure table, Friday-after-stop skip, Monday/Saturday boundaries, guard-off default, market-closure survival.
- `tests/test_cli_live.py`: reconnect after 3 failures then clean poll; failed reconnect logs + backs off.
- `tests/test_mt5_broker.py`: None-rates + disconnected terminal raises; reconnect re-initialises and re-verifies the expected install; a dead shutdown() socket does not block re-attach.
- `tests/test_config.py`: four new keys validated; defaults off.
- `tests/test_trade_ledger.py`: merge, ticket join, open-vs-closed, CSV + summary, empty-dir grace.
- Live smoke: `scripts/trade_ledger.py --once` against the running bots reports the open gold trade correctly.

## Issues Encountered / Notes

- Known glob caveat (recorded in v1.0 milestone audit): `trade_ledger.py` globs `output/live_*.log`; the CLI default log name is `live.log`, so default-named runs are invisible to the merged ledger unless launched with `--log live_*.log`. The warehouse loader glob (`output/*.log`) is unaffected.

---

*Backfilled 2026-09-07 from 04-01-PLAN.md (original SUMMARY.md never persisted). Phase directory: 04-robustness-monitoring-recovery; roadmap Phase 3.*
