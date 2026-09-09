---
phase: 002-launchd-24-7-btc-gold
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - scripts/launchd_run_live.sh
  - scripts/run_demo.sh
  - scripts/com.joram.trading-bot-btc.plist
  - scripts/com.joram.trading-bot-cent.plist
autonomous: false
user_setup: []

must_haves:
  truths:
    - "Both real-money bots (btc, cent) restart automatically when they crash or their agent is killed"
    - "Both agents bring up the full stack (colima → container → account terminal → real-money preflight → bot) without human help"
    - "A deliberate stop is still possible: launchctl bootout kills the agent and nothing respawns it"
    - "monitor_trade.py still reports both bots healthy with the same pidfile contract it uses today"
    - "Never two bots on one magic number: the manual supervise_live.sh path and the launchd agent exclude each other"
    - "Every bot start is gated by preflight_live.py --real-account"
  artifacts:
    - path: "scripts/launchd_run_live.sh"
      provides: "real-money launchd entry: stack bring-up + mutual exclusion + exec supervise_live.sh"
      contains: "preflight_live.py --config"
    - path: "scripts/com.joram.trading-bot-btc.plist"
      provides: "launchd agent for the BTC bot (tag btc)"
      contains: "launchd_run_live.sh"
    - path: "scripts/com.joram.trading-bot-cent.plist"
      provides: "launchd agent for the gold bot (tag cent)"
      contains: "launchd_run_live.sh"
    - path: "scripts/run_demo.sh"
      provides: "LIVE=1 switch that gates on preflight_live --real-account instead of preflight_demo"
      contains: "LIVE"
    - path: "~/Library/LaunchAgents/com.joram.trading-bot-btc.plist"
      provides: "installed agent (created in Task 2)"
    - path: "~/Library/LaunchAgents/com.joram.trading-bot-cent.plist"
      provides: "installed agent (created in Task 2)"
  key_links:
    - from: "scripts/launchd_run_live.sh"
      to: "scripts/run_demo.sh check (LIVE=1)"
      via: "stack bring-up + account terminal + feed freshness + real-money preflight"
      pattern: "run_demo.sh check"
    - from: "scripts/launchd_run_live.sh"
      to: "scripts/supervise_live.sh"
      via: "exec (launchd owns the lifecycle from here)"
      pattern: "exec.*supervise_live"
    - from: "scripts/supervise_live.sh"
      to: "scripts/preflight_live.py"
      via: "--real-account gate before every bot start"
      pattern: "preflight_live.py"
    - from: "output/supervise_{tag}.pid + output/live_{tag}.pid"
      to: "scripts/monitor_trade.py"
      via: "unchanged pidfile contract (supervise pid + bot pid per tag)"
      pattern: "supervise_.*\\.pid"
---

<objective>
Move both live real-money bots — BTC (`config/config-btc.toml`, magic 77021) and
gold (`config/config-cent.toml`, magic 77020) on account 161693049 — from
foreground `supervise_live.sh` processes (supervisor pids 98644/53138) to
permanent launchd agents that survive crashes and reboots unattended.

Purpose: The gold bot only exists today because `start_gold_monday.sh` fired
its one-shot `START_AT=202608240600` timer; nothing restarts either bot after a
crash, a container restart, or a reboot. The demo launchd path
(`launchd_run.sh` + `run_demo.sh check`) already proves the stack-bring-up
pattern (colima → container → account terminal → freshness gate) but its final
gate is `preflight_demo.py`, which REFUSES real accounts by design. This plan
builds the real-money counterpart and installs it for both tags, WITHOUT
touching the `supervise_live.sh` file that two real-money supervisors are
currently executing.

Output: `scripts/launchd_run_live.sh` (foreground entry), two plists, a small
`LIVE=1` switch in `run_demo.sh`, both agents installed and bootstrapped, and
a verified handover from the manual supervisors.
</objective>

<execution_context>
@/Users/joram/.config/opencode/get-shit-done/workflows/execute-plan.md
@/Users/joram/.config/opencode/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@scripts/supervise_live.sh
@scripts/launchd_run.sh
@scripts/run_demo.sh
@scripts/preflight_live.py
@scripts/com.joram.trading-bot-demo.plist
@scripts/monitor_trade.py
@config/config-btc.toml
@config/config-cent.toml
@src/trading_bot/live/engine.py

# Current live state (verified 2026-08-24 09:2x UTC)
- BTC: supervisor 98644, bot 98658, magic 77021, OPEN position ticket 435396825
  (BUY 0.01 BTCUSDc fill 77742.28, sl 76643.98, tp 78450.42)
- gold-cent: supervisor 53138, bot 3885, magic 77020, no position
- No stray timers (`wait_until`/`schedule_weekend` absent), demo agents booted out,
  no stale `.start*` locks in output/

# Design decisions locked for this plan
1. **Do NOT edit `scripts/supervise_live.sh`.** Two supervisors are executing it
   RIGHT NOW; bash re-reads a running script, so editing it live is undefined
   behaviour with real money. The new entry script wraps it unmodified.
2. **Reuse `run_demo.sh check` for bring-up** via a `LIVE=1` env switch that swaps
   `preflight_demo.py` for `preflight_live.py --config "$CONFIG" --real-account`.
   The account-terminal logic (`_ensure_account_terminal`, the grep exclusions)
   and the freshness retry live only there; a second copy would drift (the same
   reason `launchd_run.sh` delegates to it). `run_demo.sh` is not currently
   executing, so editing it is safe.
3. **launchd KeepAlive=true + ThrottleInterval 60**, exactly like the demo plists.
   The supervisor's deliberate-stop exit (rc 143/130/0 → exit 0) does NOT stop
   launchd from respawning — stopping a supervised bot for good means
   `launchctl bootout` (documented in the plist header, as for the demo agents).
4. **Stand-down, never fight**: if `output/live_{tag}.pid` is alive (manual
   supervisor owns the slot), the agent exits 0 and launchd respawns it in 60s;
   it takes over the moment the manual bot is gone. This is the handover
   mechanism and the double-bot protection (same as `launchd_run.sh`).
5. **One stack bring-up at a time**: both agents RunAtLoad at the same login and
   would race colima/docker/terminal bring-up. A shared atomic-mkdir lock
   (`output/.stack-bring-up.lock`, owner pid written inside) serialises them and
   self-heals stale locks left by a SIGKILLed agent (launchd kickstart kills the
   whole job without running traps).
6. **Security (STATE.md)**: the bridge is unauthenticated on 0.0.0.0:8001. This
   plan adds zero exposure — both agents use the existing localhost:8001
   transport exactly as the manual supervisors do today.
7. **BTC needs no weekend guard** (trades 24/7). **Gold's Friday-evening gap
   risk becomes an unattended reality under 24/7 launchd** — that is a
   decision for the human in Task 3, NOT implemented here (engine change would
   violate this plan's atomicity).
</context>

<tasks>

<task type="auto">
  <name>Task 1: Build scripts/launchd_run_live.sh, LIVE=1 in run_demo.sh, and both plists</name>
  <files>
    scripts/launchd_run_live.sh
    scripts/run_demo.sh
    scripts/com.joram.trading-bot-btc.plist
    scripts/com.joram.trading-bot-cent.plist
  </files>
  <action>

Create `scripts/launchd_run_live.sh` — the foreground entry point for a
REAL-money launchd agent. Model it on `scripts/launchd_run.sh` and on the
header comment in `supervise_live.sh` ("Runs in the FOREGROUND and never
detaches, so it can be supervised by launchd ... or simply left in a terminal").
It must NOT detach; launchd owns the lifecycle.

Behavior spec (implement exactly):

```
Usage: scripts/launchd_run_live.sh btc|cent

1.  set -uo pipefail; cd "$(dirname "$0")/.."; export PATH exactly as
    launchd_run.sh does (/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin).
    TAG="${1:?...}"; CONFIG="config/config-$TAG.toml";
    DECISION_LOG="live_$TAG.log"; PIDFILE="output/live_$TAG.pid";
    LOCKDIR="output/.live-$TAG.lock"; STACK_LOCK="output/.stack-bring-up.lock".
    Log lines as "launchd_run_live:$TAG ...".

2.  STAND DOWN if a bot is already running for this tag:
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      log "a bot is already running (pid ...) — standing down"; exit 0; fi
    (launchd respawns us after ThrottleInterval; when the manual bot dies we
    take over. This is the double-bot protection.)

3.  Take the per-tag lock: mkdir -p output; mkdir "$LOCKDIR" (atomic) or stand
    down; trap 'rmdir "$LOCKDIR"' on EXIT INT TERM. Mirror launchd_run.sh.

4.  STACK BRING-UP, serialised across both agents:
    for i in 1..60:
      if mkdir "$STACK_LOCK" 2>/dev/null; then echo $$ > "$STACK_LOCK/pid"; owner=1; break; fi
      else read "$STACK_LOCK/pid"; if owner pid is set and NOT alive (kill -0
      fails) → log "reclaiming stale stack lock (owner ... dead)", rmdir the
      lock, continue (retry immediately). Otherwise log "stack bring-up in
      progress elsewhere — waiting", sleep 30.
    If never acquired in 60 tries (30 min): log FAIL, exit 1.
    Trap now also rmdirs "$STACK_LOCK" on EXIT.

5.  colima VM + container, mirroring launchd_run.sh steps 1-2 verbatim
    (colima status → colima start --arch x86_64 --vm-type=qemu --cpu 4 --memory 6;
    docker context use colima; docker start siliconmt5 if not running).

6.  PER-TAG READINESS LOOP: for i in 1..40:
      if LIVE=1 INSTANCE="$TAG" scripts/run_demo.sh check; then log "stack ready"; break; fi
      if i == 40 → log "FAIL stack never became ready (20 min)" + the noVNC
      hint from launchd_run.sh, exit 1.
      log "not ready (attempt i/40) — retrying in 30s"; sleep 30.
    NOTE: we hold the stack lock for the whole loop so the account terminal is
    launched exactly once even when both agents boot together.

7.  Release "$STACK_LOCK" (rmdir), reset the trap to LOCKDIR only, then
    re-check the pidfile (a manual `supervise_live.sh` may have claimed the
    slot during bring-up) — if alive, log and stand down (exit 0).

8.  Release "$LOCKDIR" (rmdir), then:
    exec bash scripts/supervise_live.sh "$CONFIG" "$DECISION_LOG" "$TAG"
    (supervise_live.sh then preflights with preflight_live.py --real-account
    before EVERY start, holds caffeinate for its own lifetime, writes
    output/supervise_$TAG.pid and output/live_$TAG.pid, and its crash-loop
    brake survives inside the launchd job.)
```

Modify `scripts/run_demo.sh` minimally to support the LIVE switch (this file is
NOT executing — safe to edit):

1. After the INSTANCE/CONFIG block, add:
   `LIVE="${LIVE:-0}"` with a comment: LIVE=1 swaps the preflight gate from
   preflight_demo.py (refuses REAL accounts — that guard stays the default) to
   preflight_live.py --config "$CONFIG" --real-account, for the real-money
   launchd agents.
2. `_preflight()`: build the preflight command into an array from LIVE:
   LIVE=1 → `(.venv/bin/python scripts/preflight_live.py --config "$CONFIG" --real-account)`;
   else → `(.venv/bin/python scripts/preflight_demo.py)`. Invoke as
   `out=$("${PREFLIGHT[@]}" 2>&1)` — everything else (READY grep, 8x15s retry)
   unchanged.
3. `start()`: the python invocation's `--mode` becomes
   `"$([ "$LIVE" = "1" ] && echo live || echo demo)"` so LIVE=1 start cannot
   silently launch a demo-mode bot after a live preflight. Add a comment: even
   if misconfigured, the SAFE-03 gate in live/safety.py (`verify_execution_allowed`)
   refuses mode=demo + REAL account and enabled=false + REAL account, so the
   engine itself is the backstop.
4. Do not change `stop()`, `status()`, `_container_checks()`,
   `_ensure_account_terminal()`, or the locking.

Create `scripts/com.joram.trading-bot-btc.plist` and
`scripts/com.joram.trading-bot-cent.plist`, structurally identical to
`scripts/com.joram.trading-bot-demo.plist` with these differences:

- Label: `com.joram.trading-bot-btc` / `com.joram.trading-bot-cent`
- ProgramArguments: /bin/bash, /Users/joram/projects/trading-bot/scripts/launchd_run_live.sh, then `btc` / `cent`
- WorkingDirectory: /Users/joram/projects/trading-bot
- RunAtLoad true; KeepAlive true; ThrottleInterval 60; ProcessType Background
- StandardOutPath /Users/joram/projects/trading-bot/output/launchd_live_btc.out
  (cent: launchd_live_cent.out); StandardErrorPath likewise (.err)
- Header comment (like the demo plist) stating: REAL MONEY account 161693049;
  entry point is scripts/launchd_run_live.sh {tag}; install = cp + launchctl
  bootstrap; STOP FOR GOOD = launchctl bootout gui/$(id -u)/com.joram.trading-bot-{tag}
  (a plain `kill` on the bot only causes launchd to restart it within ~60s);
  the agent stands down automatically while a manual `supervise_live.sh` bot
  is running, so it is safe to bootstrap while the manual supervisors are up.

Do NOT touch: supervise_live.sh (live-executing), launchd_run.sh, the demo
plists, any src/ code, any config.
  </action>
  <verify>
    - `bash -n scripts/launchd_run_live.sh` passes
    - `plutil -lint scripts/com.joram.trading-bot-btc.plist scripts/com.joram.trading-bot-cent.plist` → both OK
    - `LIVE=1 INSTANCE=btc scripts/run_demo.sh check` → prints preflight lines for
      config/config-btc.toml and ends READY, exit 0 (read-only; stack already up)
    - `LIVE=1 INSTANCE=cent scripts/run_demo.sh check` → same
    - `scripts/run_demo.sh check` (LIVE unset) still FAILS with the REAL-account
      refusal from preflight_demo.py (guard intact), non-zero exit
    - `grep -n "preflight_live.py --config" scripts/launchd_run_live.sh` present
    - Process state unchanged: pids 98644/98658/53138/3885 all still alive
    - `.venv/bin/pytest -q` still green (run once — no src/ touched)
  </verify>
  <done>
    - launchd_run_live.sh, both plists, and the LIVE switch exist and pass every
      check above; the demo guard in run_demo.sh is unchanged for LIVE unset;
      all four live processes are untouched and still logging
  </done>
</task>

<task type="auto">
  <name>Task 2: Install and bootstrap both agents — non-disruptive stand-down verification</name>
  <files>
    ~/Library/LaunchAgents/com.joram.trading-bot-btc.plist
    ~/Library/LaunchAgents/com.joram.trading-bot-cent.plist
  </files>
  <action>
Install the agents WITHOUT stopping anything. Both manual supervisors stay up;
the agents must recognise the running bots and stand down.

1. `cp scripts/com.joram.trading-bot-btc.plist scripts/com.joram.trading-bot-cent.plist ~/Library/LaunchAgents/`
2. `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.joram.trading-bot-btc.plist`
   and the same for cent. If bootstrap reports "service already loaded" from a
   prior attempt, log it and continue (the label is already ours).
3. Verify each agent is loaded: `launchctl print gui/$(id -u)/com.joram.trading-bot-btc`
   (and cent) — expect state `running` with the agent having exited 0 (standing
   down because the manual bot holds the pidfile).
4. CRITICAL — no double bots: `ps aux | grep "trading_bot.cli live"` must show
   EXACTLY the original 4 processes (supervisors 98644, 53138 and bots 98658,
   3885) and no extra bot or supervisor. `cat output/supervise_btc.pid
   output/supervise_cent.pid` still reads 98644/53138.
5. Confirm both live logs are still advancing with fresh timestamps (the agents
   have not interfered): `tail -2 output/live_btc.log output/live_cent.log`.
6. Confirm the agents' own logs show the stand-down decision:
   `tail -5 output/launchd_live_btc.out output/launchd_live_cent.out` → lines
   "a bot is already running ... standing down".
  </action>
  <verify>
    - `launchctl list | grep joram.trading-bot` shows both live agents
    - process count for `trading_bot.cli live` and `supervise_live.sh` is
      unchanged (2 + 2); pidfiles unchanged
    - `tail -1 output/live_btc.log` timestamp is within the last ~5 minutes
    - agent stdout logs show standing down, not "starting supervisor"
  </verify>
  <done>
    - Both agents are loaded and demonstrably standing down in front of the
      manual supervisors — no process, pidfile, or log was disturbed
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <what-built>
    Both real-money launchd agents installed and standing by (Task 1 + Task 2).
    The handover below moves the BTC and gold bots from the foreground manual
    supervisors to launchd supervision, then proves crash recovery.
  </what-built>
  <how-to-verify>
    BTC holds an open position (ticket 435396825, SL/TP at the broker). Killing
    the bot does NOT touch the position; the replacement bot sees it via its
    position-open dedup. Run these in order:

    1. HANDOVER — kill both manual bots (supervisors then exit cleanly):
         kill $(cat output/live_btc.pid) $(cat output/live_cent.pid)
       Expect: output/live_*.pid and supervise_*.pid disappear within seconds;
       within ~60–120 s the agents take over (launchd respawn after the manual
       pidfile cleared). Verify each:
         cat output/supervise_btc.pid   # NEW pid, ≠ 98644
         cat output/supervise_cent.pid  # NEW pid, ≠ 53138
         cat output/live_btc.pid        # NEW bot pid, ≠ 98658
         cat output/live_cent.pid       # NEW bot pid, ≠ 3885
         tail -8 output/supervise_btc.log   # "supervisor starting" → "preflight ok" → "bot started"
         tail -8 output/supervise_cent.log  # same
         launchctl list | grep joram.trading-bot   # both agents show a pid

    2. MONITOR — one-glance health for both:
         .venv/bin/python scripts/monitor_trade.py            # btc
         .venv/bin/python scripts/monitor_trade.py --tag cent
       Both exit 0. BOT section shows the NEW pids, last decision < 10 min.
       The BTC OPEN POSITION section still shows ticket 435396825 with its
       entry/sl/tp — the new bot and the old position coexist, and
       `grep -c order_placed output/live_btc.log` has NOT grown (no duplicate
       placement after takeover).

    3. CRASH RECOVERY (the property 24/7 exists for) — kill the cent agent's
       whole job the way a crash or SIGKILL would:
         launchctl kickstart -k gui/$(id -u)/com.joram.trading-bot-cent
       Expect: launchd respawns the agent; within ~2–4 min a new cent
       supervisor + bot exist with "preflight ok → bot started" in
       supervise_cent.log, and monitor_trade --tag cent is exit 0 again.
       Repeat for btc if you want both proven (optional).

    4. DELIBERATE STOP — the documented "stop for good" path:
         launchctl bootout gui/$(id -u)/com.joram.trading-bot-cent
       Expect: agent unloaded, cent bot dead, and after > 60 s still NOT
       respawned. Then bring it back:
         launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.joram.trading-bot-cent.plist

    5. WEEKEND-GAP DECISION — answer this before closing out (see options in
       the resume signal). Today is Monday; the next Friday close is Aug 28.

    Known-unknown to accept: cold-boot survival (colima start from a launchd
    context after a real reboot) was never executed for the demo agents either.
    The warm kickstart test proves crash respawn; a full reboot test is a
    follow-up you can run when convenient.
  </how-to-verify>
  <resume-signal>
    Type "approved" + your weekend-gap choice, or describe what looked wrong.

    WEEKEND-GAP DECISION (gold/cent agent only — BTC trades 24/7, unaffected):
    Under 24/7 launchd nobody is at the terminal Friday evening to do what you
    did by hand on 2026-08-21 (closed gold at 19:02 UTC, the "weekend-gap
    decision"). The engine only acts on new closed bars, so no NEW gold orders
    can appear after Friday 21:00 UTC — but a setup on a late-Friday bar opens
    a position that rides the Sunday 21:00 UTC reopening gap, and a broker stop
    cannot protect a gap that jumps through it.

      option-a (recommended): add a `[live]` weekend guard to the engine —
        refuse NEW gold entries after Friday ~19:00 UTC (matches your manual
        precedent), pure function + config validation + wiring in poll_once +
        tests. Small follow-up quick task, ~1-2h. The account is safe either
        way; this only decides whether the gold bot keeps trading until the
        Friday close.
      option-b: keep the engine untouched; schedule a launchctl bootout of the
        cent agent Friday ~19:00 UTC and re-bootstrap Monday ~06:00 UTC — the
        old scheduled-close pattern, reintroduced by hand.
      option-c: no guard — accept that a Friday-evening gold setup rides the
        weekend gap.

    Answer: "approved, option-a" (or b/c) — and note whether you want me to
    schedule the follow-up task for the guard.
  </resume-signal>
</task>

</tasks>

<verification>
- Both agents supervise their tags end-to-end with the manual supervisors gone:
  `launchctl list | grep joram.trading-bot` shows btc + cent with pids, and
  `monitor_trade.py` (both tags) exits 0 with fresh logs and the new pids
- Exactly one bot per magic at all times: no duplicate `order_placed` in
  output/live_btc.log after takeover; the open BTC position is still the
  original ticket 435396825
- Crash recovery proven once (kickstart -k on cent): agent, supervisor and bot
  all come back without human help
- Deliberate stop proven: bootout halts the cent agent permanently until
  re-bootstrapped
- No exposure added: both agents use the existing localhost:8001 bridge, and
  no new port binding, network config, or remote client was created
- `supervise_live.sh` was never modified while executing; `.venv/bin/pytest -q`
  green (no src/ changes)
</verification>

<success_criteria>
- BTC and gold both run 24/7 under launchd on real-money account 161693049,
  surviving crashes (proven by kickstart) with the full stack brought up
  unattended (colima → container → account terminal → preflight_live
  --real-account → bot)
- A deliberate stop is a single `launchctl bootout` per agent, documented in
  each plist header
- The manual path still works and is safe: `supervise_live.sh` unchanged,
  `run_demo.sh` demo guard intact, LIVE=1 start launches a correct live-mode
  bot
- monitor_trade.py / health_check.py contract unchanged — the pidfiles the
  agents produce are the ones they already read
- The weekend-gap decision is recorded in the SUMMARY with its chosen option
</success_criteria>

<output>
After completion, create `.planning/quick/002-launchd-24-7-btc-gold/002-SUMMARY.md`
</output>
