# Quick Task 005 — Local Web Dashboard

**Status:** complete — server running on 127.0.0.1:8765, verified against the live gold bot.

## What was built

- `scripts/dashboard.py` (497 lines, stdlib-only) — `http.server` bound to the literal
  `127.0.0.1:8765`. JSON API:
  - `/api/health` — ok
  - `/api/status` — per-tag bot sections (supervisor/bot pids, last-decision age), broker
    connection, account, open position (entry/SL/TP/bid/ask/floating/R), recent closes
  - `/api/risk` — per-tag `[risk]` + `strategy.rr_multiple` + account-wide total vs policy
  - `/api/risk/preview` — the exact `tune_risk.py` validation + aggressive warnings, never writes
  - `/api/risk/apply` — the ONLY write path; calls `tune_risk.set_risk()` verbatim (browser
    Confirm = the `--yes`); restart checkbox default OFF
- `scripts/dashboard.html` (354 lines, vanilla JS) — three tabs: **Status / Risk / Account**.
- `tests/test_dashboard.py` — 10 tests (ephemeral-port endpoints, tmp config copies, restarter
  recorder, loopback-only binding asserted). Full suite: **270 green** (260 + 10).

## Key properties

- **Read-only by default**; every write goes through the exact `tune_risk.py` validation /
  warning / `--yes` gate — no bypass exists.
- **Loopback-only** (`lsof`: `localhost:ultraseek-http`, never `*:8765`) — adds zero exposure on
  a machine where the MT5 bridge on 0.0.0.0:8001 is already unauthenticated.
- **Zero new dependencies** — stdlib only; no build step.

## Bugs fixed during execution (Rule 1/3 deviations)

1. **Server was started with the system Python**, not the venv — `siliconmetatrader5` isn't in
   the system interpreter, so the Status tab showed "broker unreachable" while the live bot was
   clearly connected. Fixed by restarting with `.venv/bin/python scripts/dashboard.py`. Start
   command documented as `.venv/bin/python scripts/dashboard.py --port 8765`.
2. 6 pre-existing test failures from the 004 live config apply (config-cent now has
   rr_multiple=2.0 / cap=20) — fixed in tests to match the live-committed config.
3. Plan prose said an rr_multiple change moves the account total (21.0%→22.0%) — wrong; rr never
   moves cap×slots. Total stays 21.0%. The plan's test-8 (no-op set + restart calls restarter)
   contradicted `set_risk`'s no-change early return — proven with a real change instead.

## BTC position incident (from quick task 004's test hiccup)

A pre-existing test bug re-bootstrapped the BTC launchd agent during 004 testing; the briefly
alive BTC bot placed a fresh position (ticket **435655460**, BUY 0.01 BTCUSDc, entry 77837.77)
after the user's manual closes, because the position-open dedup found nothing. Bot killed again
immediately; root cause fixed (autouse `_restart_agent` stubs in both test files). The position
was left at the broker on SL/TP per the user's decision — closing stays a human action by design.

## Verification state

- Server running (pid 44415, venv python), all endpoints respond, broker connected
  (`trade_allowed: true`), account 161693049, balance 3202.71 USC.
- Dashboard Status/Risk/Account cross-checked against `monitor_trade.py --tag cent` and
  `tune_risk.py` — matches.
- Live configs byte-identical (`git status config/` clean at build time).

## Operational note

- Restart the dashboard after a reboot: `.venv/bin/python scripts/dashboard.py --port 8765`
  (detached; output in `output/dashboard.out`). It is NOT launchd-supervised.
