---
phase: 001-monitor-the-live-btc-trade
plan: 01
type: execute
wave: 1
depends_on: []
files_modified: [scripts/monitor_trade.py, README.md]
autonomous: false
user_setup: []

must_haves:
  truths:
    - "User runs one command and sees whether the BTC bot is alive and still polling"
    - "User sees the open position in one glance: entry, SL, TP, current price, floating P&L, current R"
    - "User sees realised P&L from closes.log plus account balance/equity"
    - "The command fails loudly (non-zero exit) when the broker is unreachable or the bot is stale"
  artifacts:
    - path: "scripts/monitor_trade.py"
      provides: "one-glance live trade monitor (bot status + open position + P&L)"
      min_lines: 120
    - path: "README.md"
      provides: "documented monitoring command"
      contains: "monitor_trade.py"
  key_links:
    - from: "scripts/monitor_trade.py"
      to: "output/live_btc.pid + output/live_btc.log"
      via: "pidfile read + last_log_time parse"
      pattern: "live_.*\\.(pid|log)"
    - from: "scripts/monitor_trade.py"
      to: "config/config-btc.toml"
      via: "load_config + cfg.live.magic_number + live_symbol"
      pattern: "load_config"
    - from: "scripts/monitor_trade.py"
      to: "output/closes.log"
      via: "read and filter by symbol="
      pattern: "closes\\.log"
---

<objective>
A single command that answers the three monitoring questions for the live
real-money BTC trade in one glance: **is the bot alive, is there an open
position, what is the P&L.**

Purpose: Real money is trading right now (account 161693049 @ Exness-MT5Real21,
BTCUSDc, magic 77021, pid 98658, supervised by 98644). The existing tooling
covers the parts separately — `health_check.py` answers "is it OK?" (processes,
poll loop, risk, reconciliation), `watch_closes.py` logs broker-side closes,
`account_report.py` reports realised P&L — but nothing shows the OPEN position
itself (entry/SL/TP/current price/floating P&L/current R) next to bot status and
P&L in one read. That is the gap this plan closes.

Output: `scripts/monitor_trade.py` (read-only snapshot command) + a README
section documenting it.
</objective>

<execution_context>
@/Users/joram/.config/opencode/get-shit-done/workflows/execute-plan.md
@/Users/joram/.config/opencode/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@README.md
@scripts/health_check.py
@scripts/account_report.py
@scripts/close_position.py
@config/config-btc.toml

# Conventions to reuse (do not reinvent)
- Transport resolution (native → bridge fallback): scripts/close_position.py
- pidfile/last-log-time parsing + exit-code semantics: scripts/health_check.py
- R-multiple formula + closes.log matching: scripts/account_report.py / watch_closes.py
- Tag → config mapping already exists: `BOTS = {"btc": "config/config-btc.toml", "cent": "config/config-cent.toml"}` in health_check.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Build scripts/monitor_trade.py — the one-glance live trade monitor</name>
  <files>scripts/monitor_trade.py</files>
  <action>
Create a new read-only snapshot script following the established conventions of
scripts/health_check.py and scripts/account_report.py. It must NEVER place,
close, or modify anything — only read (pidfiles, logs, broker state).

Interface:
    .venv/bin/python scripts/monitor_trade.py [--tag btc] [--quiet]

- `--tag` selects the bot via the same mapping health_check.BOTS already uses:
  `btc -> config/config-btc.toml` (default), `cent -> config/config-cent.toml`.
  All derived paths follow the same convention: pidfiles `output/live_{tag}.pid`
  and `output/supervise_{tag}.pid`, decision log `output/live_{tag}.log`.
- `--quiet` prints only WARN/FAIL lines (mirrors health_check).
- Exit codes: 0 healthy, 1 warnings, 2 problems (mirrors health_check, so it
  works in a cron job).

Print five sections, in this order:

1. Header: current UTC time, tag, `live_symbol(cfg)` (the broker symbol,
   BTCUSDc), `cfg.live.magic_number` (77021). Do NOT use `cfg.data.symbol`
   (that is the histdata name, XAUUSD).

2. BOT:
   - bot pid from `output/live_{tag}.pid` + `ps -p` liveness check; supervisor
     pid from `output/supervise_{tag}.pid` + liveness. A bot DOWN while its
     supervisor is UP is a WARN (normal during restart backoff), not a FAIL.
   - last decision from `output/live_{tag}.log` using health_check's
     `last_log_time` regex approach; staleness threshold = 2 × bar interval
     from `cfg.data.timeframe` (M5 -> 10 min). A live bot with a stale log is
     a FAIL — that is the dangerous state (alive but no longer polling).
   - `mt5.terminal_info()`: `connected` (FAIL if not) and `trade_allowed`
     (FAIL if not — orders will be rejected).

3. OPEN POSITION: from `mt5.positions_get()`, filtered to
   `cfg.live.magic_number`. None -> one line "no open position". Otherwise, per
   position:
   - ticket, side (BUY/SELL from pos.type), volume, symbol
   - entry, sl, tp. A position with NO stop loss is a FAIL line ("unbounded
     downside") — same severity health_check gives it.
   - current bid/ask via `mt5.symbol_info_tick(symbol)`; floating P&L =
     `pos.profit` (account currency) plus % of `acct.balance`
   - current R = (bid - entry) / (entry - sl) for a long (mirror
     watch_closes.py's formula, evaluated at the live price instead of the exit)
   - distance to SL and to TP as % of entry
   - time open = now - `pos.time` (unix epoch), rendered as hh:mm

4. ACCOUNT: `acct.balance`, `acct.equity`, floating `acct.profit` from
   `mt5.account_info()`.

5. RECENT CLOSES: parse `output/closes.log` for lines containing
   `symbol=<live_symbol(cfg)>`; print the last 5 (timestamp, how=tp|sl|other,
   profit, r), then a totals line: count, summed profit (USC), summed R
   (treat `r=?` as a skip, and note how many were skipped). Missing file ->
   print a one-line note, not an error.

Robustness:
- Transport resolution identical to scripts/close_position.py: try `_load_mt5()`
  native, on `BrokerUnavailableError` fall back to
  `_load_silicon_bridge(cfg.live.bridge_host, cfg.live.bridge_port)`. On
  initialize failure print a FAIL line and exit 2.
- No new dependencies — stdlib plus the existing trading_bot imports
  (`load_config`, `live_symbol` from trading_bot.config; `_load_mt5`,
  `_load_silicon_bridge`, `BrokerUnavailableError` from trading_bot.broker).
- Module docstring must state clearly this is READ-ONLY observability and
  never touches an order.
  </action>
  <verify>
    - `.venv/bin/python -m py_compile scripts/monitor_trade.py` passes
    - `.venv/bin/python scripts/monitor_trade.py` runs against the live bot and
      exits 0
    - `.venv/bin/python scripts/monitor_trade.py --quiet` prints nothing
      (current state is healthy)
    - FAIL-path spot check: `mv output/live_btc.pid output/live_btc.pid.bak`,
      run the script (expect a WARN/FAIL and non-zero exit for the missing bot),
      then `mv output/live_btc.pid.bak output/live_btc.pid` to restore. Run it
      once more to confirm exit 0 is back.
  </verify>
  <done>
    - Script prints all five sections with real live data: pid 98658 alive,
      supervisor 98644, symbol BTCUSDc, magic 77021, account 161693049,
      balance ~3139 USC, the four 08-22/08-23 BTC closes present in RECENT CLOSES
    - Exit 0 on the healthy state; non-zero when the pidfile is missing
    - `--quiet` emits nothing when healthy
  </done>
</task>

<task type="auto">
  <name>Task 2: Document the monitor in README.md</name>
  <files>README.md</files>
  <action>
Add a subsection "Monitoring the live trade" under the Running area, between
"Is it actually making money?" and "Closing a position". Content:

    ```bash
    python scripts/monitor_trade.py            # one-glance snapshot
    python scripts/monitor_trade.py --quiet    # only problems
    python scripts/monitor_trade.py --tag cent # another bot
    ```

Explain in the project's existing voice:
- It answers the three questions in one read: is the bot alive and polling, is
  there an open position (entry/SL/TP/current price/floating P&L/current R), and
  what is the P&L (realised closes from output/closes.log + balance/equity).
- It is READ-ONLY: it never places, closes, or modifies anything — closing stays
  the human action documented in the next subsection.
- Exit codes 0/1/2 match health_check.py, so it is cron-friendly.
- It deliberately shows only THIS bot's positions (filtered by magic number);
  account-wide risk across bots remains health_check's job.
- The documented invocations must exactly match the implemented arguments.
  </action>
  <verify>
    - README contains the new subsection and the command lines are byte-identical
      to what Task 1 actually accepts (`--tag`, `--quiet`)
    - `grep -n "monitor_trade" README.md` shows the usage block
  </verify>
  <done>
    - README documents `python scripts/monitor_trade.py` with the --tag/--quiet
      flags and the read-only caveat, in the section order described
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <what-built>
    scripts/monitor_trade.py — the one-glance live trade monitor (bot status +
    open position + P&L), plus its README section.
  </what-built>
  <how-to-verify>
    1. Run `.venv/bin/python scripts/monitor_trade.py`. Confirm:
       - BOT: pid 98658 alive, supervisor 98644, last decision within ~10 min
       - OPEN POSITION: "no open position" (or a real one — then verify entry/
         SL/TP match the MT5 terminal and floating P&L matches the account tab)
       - ACCOUNT: balance ≈ 3139 USC matching the Exness app, equity ≈ balance
       - RECENT CLOSES: the 08-22/08-23 BTC closes appear, e.g. TP +57.77
         +1.06R, SL −11.41 −1.00R, TP +10.57 +0.94R, TP +10.57 +0.83R
    2. Run `.venv/bin/python scripts/monitor_trade.py --quiet` — expect no
       output (the current state is healthy).
    3. Cross-check: `ps -p $(cat output/live_btc.pid)` shows the same pid the
       monitor reported as alive.
  </how-to-verify>
  <resume-signal>Type "approved" or describe what looked wrong</resume-signal>
</task>

</tasks>

<verification>
- `.venv/bin/python scripts/monitor_trade.py` runs against the live broker and
  the printed numbers reconcile with reality (Task 3 human check)
- Existing tooling untouched: `health_check.py`, `watch_closes.py`,
  `account_report.py`, `close_position.py` are not modified by this plan
- `.venv/bin/pytest` still green (no production code touched — confirm once)
</verification>

<success_criteria>
- One command answers the three monitoring questions for the live BTC trade in a
  single glance
- The open-position view (entry/SL/TP/current/floating/current-R) — the part no
  existing script showed — exists and matches the MT5 terminal
- Exit codes make the monitor safe to cron alongside health_check.py
- The command is documented in README exactly as implemented
</success_criteria>

<output>
After completion, create `.planning/quick/001-monitor-the-live-btc-trade/001-SUMMARY.md`
</output>
