---
phase: quick-006-bank-profits
plan: 01
subsystem: tooling
tags: [cli, usc, r-estimate, ledger, read-only, mt5-bridge]

# Dependency graph
requires:
  - phase: phase-2-live-execution
    provides: "trading_bot.broker.mt5._load_mt5 / _load_silicon_bridge, broker.base.BrokerUnavailableError, load_config/live_symbol, health_check.BOTS"
  - phase: quick-005-web-dashboard
    provides: "the health_check.BOTS re-export + monitor_trade.py broker-connection convention"
provides:
  - "Read-only banking helper CLI: balance / pinned base / bankable excess in USC + R estimate"
  - "First-run auto-pin of the base stake; --base repin; --confirm appends a ledger line"
  - "8 fake-broker + tmp-file tests (full suite 270 -> 278 green)"
affects: [phase-3-live-verification, future quick tasks touching output/ state files]

# Tech tracking
tech-stack:
  added: [none — stdlib only]
  patterns:
    - "Script broker transport: lazy import inside _connect, native -> silicon bridge fallback via cfg.live.bridge_*, initialize() guard (monitor_trade.py convention)"
    - "Script isolation: BOTS re-exported for monkeypatching, BASE_FILE/LEDGER module constants for tmp_path redirection"

key-files:
  created:
    - scripts/bank_profits.py
    - tests/test_bank_profits.py
    - output/bank_base.txt (runtime, gitignored)
  modified: []

key-decisions:
  - "Tool is READ-ONLY against the broker: reads account_info() only, no order_send/position mutation/close anywhere; the withdrawal is reported as a MANUAL Exness-portal action"
  - "Runtime state lives in gitignored output/bank_base.txt (pinned base, USC) + output/profits_banked.log (ledger), never in config/"
  - "USC -> R estimate uses usc / 100 * usd_rate (health_check.py formula), default --usd-rate 18.0, labelled as an estimate"
  - "First run auto-pins the current balance as the base stake (design truth), so future banking is legible immediately"

patterns-established:
  - "New script-test convention: patch _load_mt5/_load_silicon_bridge ON trading_bot.broker.mt5 (lazy per-call imports pick the patch up), _FakeBroker with settable balance, BOTS/BASE_FILE/LEDGER monkeypatched to tmp_path"
  - "output/ state files are gitignored scratch — plain write_text is fine (tune_risk's atomic dance is only for live config/ files)"

# Metrics
duration: 24min
completed: 2026-08-24
---

# Quick Task 006: Bank-the-Profits Helper — Summary

**`scripts/bank_profits.py`: read-only banking CLI that shows balance / pinned base / bankable excess in USC + an approximate R figure, auto-pins the base on first run, and records each banking decision to a ledger while explicitly deferring the actual transfer to a manual Exness-portal action**

## Performance

- **Duration:** ~24 min
- **Completed:** 2026-08-24
- **Tasks:** 2/2
- **Files modified:** 2 (1 script + 1 test file)

## Accomplishments

- `scripts/bank_profits.py` (174 lines, stdlib-only) — one command answers "how much is bankable right now": `balance X USC  base Y USC  bankable Z USC  (~R…, usd_rate …)`. Imports cleanly with NO MetaTrader5/siliconmetatrader5 package present.
- Connection reuses the repo's broker convention exactly (monitor_trade.py): lazy import inside `_connect`, native → silicon bridge fallback at `cfg.live.bridge_host/port` (never hardcoded), `initialize()` guard, graceful `broker unavailable:` + exit 2.
- First run auto-pins the current balance as the base stake; `--base` repins deliberately; `--confirm` appends ONE `event=profits_banked` key=value line to `output/profits_banked.log` and prints the exact withdrawal amount (`withdraw 2500.00 USC ≈ $25.00`) with the mandatory instruction that the transfer is a MANUAL Exness-portal action the bot cannot perform.
- Sub-minimum excess (< 1000 USC ≈ $10) prints the weekly-banking WARNING.
- `tests/test_bank_profits.py` — 8 tests (fake broker + tmp BASE_FILE/LEDGER/BOTS), all five must-have truths covered; full suite **270 → 278 green**.

## Task Commits

1. **Task 1: Implement scripts/bank_profits.py** — `13abef6` (feat)
2. **Task 2: Write tests/test_bank_profits.py** — `f6c59d5` (test)

**Plan metadata:** `f5500cc` (docs: plan bank-the-profits helper, pre-existing)

## Files Created/Modified

- `scripts/bank_profits.py` — the read-only banking helper CLI (view / `--base` / `--confirm` / `--usd-rate` / `--tag`)
- `tests/test_bank_profits.py` — fake-broker + tmp-file coverage of all five truths (8 tests)
- `output/bank_base.txt` — runtime state, gitignored (created by the real first-run sanity check)

## Decisions Made

- **READ-ONLY against the broker.** The tool calls `account_info()` and nothing else. Grep-verified: no `order_send` / `positions_get` / `order_modify` / close anywhere outside the safety-model docstring. The withdrawal is reported and logged, never executed — the bot cannot move money.
- **State is gitignored scratch in `output/`**, never `config/`: `bank_base.txt` (pinned base, USC, 2 decimals) and `profits_banked.log` (one key=value line per banking event, UTC timestamp, closes.log token style). Plain `write_text` is sufficient — tune_risk's atomic dance exists for editing live config files, not scratch state.
- **USC → R estimate** uses `usc / 100 * usd_rate` (the exact health_check.py line-234 formula), `--usd-rate` defaults to 18.0 and is labelled in the output.
- **`MIN_BANKABLE_USC = 1000.0`** module constant (~$10 practical withdrawal floor) — also module-level `BASE_FILE` / `LEDGER` / `DEFAULT_USD_RATE` so tests monkeypatch them.

## Deviations from Plan

None — plan executed exactly as written. (Both tasks' `files_modified` match; no deviation rules triggered.)

## Issues Encountered

- The real sanity check with the **system** `python3` failed with `broker unavailable: siliconmetatrader5 is not installed` even though the bridge is up — `siliconmetatrader5` only exists in the repo venv (`.venv/bin/python`, the interpreter the live launchers use). Same gotcha as quick task 005's dashboard. Re-run with the venv succeeded. Operational note: run `bank_profits.py` with `.venv/bin/python`, like `dashboard.py`.

## User Setup Required

None — no external service configuration. The tool is runnable immediately: `.venv/bin/python scripts/bank_profits.py`.

## Verification

- `python3 -c "... import bank_profits"` → `imports clean` (no MT5 package needed)
- `python3 scripts/bank_profits.py --help` → exit 0, lists `--tag/--base/--confirm/--usd-rate`
- Grep `order_send|positions_get|order_modify|close` → matches only inside the module docstring
- `python3 -m pytest tests/test_bank_profits.py -q` → 8 passed
- `python3 -m pytest tests/ -q` → **278 passed**, zero failures
- Real read-only sanity run against the live account (bridge up, venv python, no `--confirm`, no `--base`):

```
bank profits  cent  XAUUSDc  2026-08-24 13:43:05Z  account 161693049 @ Exness-MT5Real21  currency USC
first run: pinned base = 3205.64 USC (current balance)
balance 3205.64 USC  base 3205.64 USC  bankable 0.00 USC  (~R0.00, usd_rate 18.0)
nothing to bank
exit=0
```

First-run pin landed in `output/bank_base.txt` (3205.64, gitignored). The open live trade (ticket 435782739) was untouched — the tool never calls anything but `account_info()`. No ledger line was written. The user's next step whenever a profit clears the base: re-pin the base stake with `--base <USC>` (e.g. their R500 base ≈ 3000 USC), then `--confirm` to record each banking event.

## Next Phase Readiness

- The tool is ready for the user's banking workflow; the ledger (`output/profits_banked.log`) becomes the audit trail of "trade with the base, not the profit".
- Follow-up idea (not in scope): a cron-friendly `--quiet` flag or a check that warns when `bankable >= MIN_BANKABLE_USC` so banking is suggested at the right moment.

---
*Phase: quick-006-bank-profits*
*Completed: 2026-08-24*
