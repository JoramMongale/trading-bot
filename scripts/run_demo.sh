#!/usr/bin/env bash
# Start the demo bot so it survives this shell, and fail loudly on the
# conditions that silently broke it before.
#
#   scripts/run_demo.sh start|stop|status|check
#
# Why each check exists (all of these cost real debugging time):
#   * no window manager  -> X has no input focus, nobody can type in noVNC
#   * algo trading off   -> setups are DETECTED but order_send is rejected,
#                           so the log looks healthy while nothing is placed
#   * wrong terminal     -> see ACCOUNT TERMINAL below; this is the one that
#                           breaks on every container restart
set -euo pipefail

cd "$(dirname "$0")/.."

# INSTANCE selects which bot this invocation manages. Empty (the default) is
# the primary M5 bot; any other value runs a sibling with its OWN config,
# pidfile, stdout file and decision log, so several can share the container and
# the account without colliding:
#
#     scripts/run_demo.sh start              # M5,  magic 77001, live.log
#     INSTANCE=m1 scripts/run_demo.sh start  # M1,  magic 77002, live_m1.log
#
# Each instance's config MUST carry its own magic_number — the dedup and
# one-trade-at-a-time guards filter by it, so a shared magic makes each bot
# treat the other's position as its own and stop trading.
INSTANCE="${INSTANCE:-}"
SUFFIX="${INSTANCE:+_$INSTANCE}"
CONFIG="config/config${INSTANCE:+-$INSTANCE}.toml"
PIDFILE="output/live${SUFFIX}.pid"
LOGFILE="output/live${SUFFIX}.out"
DECISION_LOG="live${SUFFIX}.log"
LOCKDIR="output/.start${SUFFIX}.lock"
CONTAINER="siliconmt5"

# LIVE=1 swaps the preflight gate from preflight_demo.py (refuses REAL accounts
# — that guard stays the default) to preflight_live.py --config "$CONFIG"
# --real-account, for the real-money launchd agents (launchd_run_live.sh).
LIVE="${LIVE:-0}"

# Starting is not atomic: the pidfile check is followed by `check`, which takes
# tens of seconds (terminal launch, preflight retries), and only then does the
# bot launch and claim the pidfile. That gap is wide enough for the launchd
# agent's KeepAlive to start its own bot in the middle of a manual start —
# which is exactly what happened on 2026-08-20 and left THREE bots on magic
# 77001. mkdir is atomic on POSIX, so it serialises the whole sequence.
_lock() {
  mkdir "$LOCKDIR" 2>/dev/null || {
    echo "another start is already in progress ($LOCKDIR)" >&2; return 1; }
  trap '_unlock' EXIT INT TERM
}
_unlock() { rmdir "$LOCKDIR" 2>/dev/null || true; }

# --- ACCOUNT TERMINAL --------------------------------------------------------
# Two MT5 installs share the container's persistent Wine prefix, and the one
# the container auto-starts is NOT the one holding the account:
#
#   Program Files/MetaTrader 5 EXNESS/  <- start.sh launches and keeps this
#                                          alive. No Config/accounts.dat, so it
#                                          boots the "Select a company to open
#                                          an account with" wizard. That modal
#                                          blocks the API and every bridge call
#                                          returns -10005 IPC timeout.
#   Program Files/MetaTrader 5/         <- holds Config/accounts.dat. This is
#                                          the terminal that actually serves
#                                          the bot. Nothing starts it.
#
# So a container restart reliably kills the bridge, with a symptom (IPC
# timeout) that points nowhere near the cause. Recovery needs no password --
# the saved session is on disk, the terminal just has to be running -- so this
# script starts it rather than making a human rediscover that. mt5cfg.ini
# stores no Login/Password, so there is no auto-login to fall back on: if
# accounts.dat is gone, a human really does have to log in at noVNC.
ACCOUNT_TERMINAL='C:\Program Files\MetaTrader 5\terminal64.exe'
ACCOUNTS_DAT="/opt/wineprefix/drive_c/Program Files/MetaTrader 5/Config/accounts.dat"
NOVNC_URL="http://localhost:6081/vnc.html"

# Count the account terminal's real processes. Three exclusions, each earned:
#   [t]           - stops grep matching its own command line
#   -v EXNESS     - the other install, which has no account
#   -v start.exe  - the "start.exe /exec terminal64.exe" launcher wrapper. It
#                   matches terminal64.exe AND lacks "EXNESS", so without this
#                   it reads as a live account terminal and the check passes
#                   while nothing is actually running.
#   -vi webview   - MT5's embedded browser spawns EdgeWebView children carrying
#                   "--webview-exe-name=terminal64.exe", which matches too. Four
#                   of them turned a count of 1 into 5. Worse than a bad warning:
#                   they can outlive the terminal, so without this the check
#                   reports "running" over a dead terminal and never relaunches.
_account_terminals() {
  docker exec "$CONTAINER" sh -c \
    'ps -eo args | grep "[t]erminal64.exe" | grep -v EXNESS | grep -v "start.exe" | grep -vi webview | wc -l' \
    2>/dev/null | tr -d '[:space:]'
}

_account_terminal_running() {
  local n; n=$(_account_terminals); [ "${n:-0}" -ge 1 ]
}

_ensure_account_terminal() {
  if _account_terminal_running; then
    echo "  account terminal: running"
    return 0
  fi
  if ! docker exec "$CONTAINER" test -f "$ACCOUNTS_DAT" 2>/dev/null; then
    echo "FAIL: no saved account -- accounts.dat is missing." >&2
    echo "      This is the one case that needs a human: log in to the demo" >&2
    echo "      account at $NOVNC_URL, then re-run this." >&2
    return 1
  fi
  echo "  account terminal: not running -- starting it"
  # Deliberately not `docker exec ... pkill -f "MetaTrader 5 EXNESS"` anywhere:
  # that pattern also matches the shell running it, so the script kills itself
  # mid-command. Leave the EXNESS terminal alone; both can coexist.
  docker exec -d "$CONTAINER" bash -c \
    'cd /opt/wineprefix/drive_c && DISPLAY=:100 exec wine "C:\Program Files\MetaTrader 5\terminal64.exe" /portable >> /siliconmt5/logs/mt5_account.log 2>&1'
  local i
  for i in $(seq 1 15); do
    sleep 5
    if _account_terminal_running; then
      echo "  account terminal: started"
      return 0
    fi
  done
  echo "FAIL: account terminal did not come up." >&2
  echo "      Check: docker exec $CONTAINER tail /siliconmt5/logs/mt5_account.log" >&2
  return 1
}

# Preflight, retried. A terminal that has just started serves STALE bars for a
# minute or two while it re-downloads history, so a single early attempt
# reports an old `latest` bar or an outright failure and tells you nothing.
_preflight() {
  local i out
  local -a PREFLIGHT
  if [ "$LIVE" = "1" ]; then
    PREFLIGHT=(.venv/bin/python scripts/preflight_live.py --config "$CONFIG" --real-account)
  else
    PREFLIGHT=(.venv/bin/python scripts/preflight_demo.py)
  fi
  for i in $(seq 1 8); do
    if out=$("${PREFLIGHT[@]}" 2>&1) \
       && printf '%s\n' "$out" | grep -q READY; then
      printf '%s\n' "$out"
      return 0
    fi
    if [ "$i" -lt 8 ]; then
      echo "  preflight not ready (attempt $i/8) -- terminal still syncing history"
      sleep 15
    fi
  done
  printf '%s\n' "$out" >&2
  return 1
}

_container_checks() {
  docker ps --format '{{.Names}}' | grep -qx "$CONTAINER" || {
    echo "FAIL: container '$CONTAINER' is not running" >&2; return 1; }

  if ! docker exec "$CONTAINER" pgrep -x openbox >/dev/null 2>&1; then
    echo "  openbox not running — starting it (keyboard input needs a WM)"
    docker exec -d -e DISPLAY=:100 "$CONTAINER" \
      sh -c 'openbox >/siliconmt5/logs/openbox.log 2>&1'
    sleep 3
  fi

  _ensure_account_terminal || return 1

  # Duplicates of the ACCOUNT terminal are the ambiguous case -- the bridge
  # would pick one arbitrarily. Counted with wc -l, not grep -c: grep exits 1
  # on no match, so `grep -c ... || echo 0` printed BOTH grep's "0" and the
  # fallback "0", giving a two-line value that fails every integer test.
  local n; n=$(_account_terminals)
  [ "${n:-0}" -le 1 ] || echo "  WARNING: $n account terminals running — the bridge may attach to the wrong one" >&2
}

check() {
  _container_checks
  _preflight
}

start() {
  mkdir -p output
  _lock || return 1
  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "already running (pid $(cat "$PIDFILE"))"; return 0
  fi
  check
  # Re-check AFTER check(): the lock stops a competing run_demo.sh, but the
  # launchd agent execs the bot directly and never takes it. Two bots on one
  # magic would each see the other's position as their own and both stop
  # trading — or worse, both place before either sees the other.
  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "another bot claimed the slot while we were starting "\
         "(pid $(cat "$PIDFILE")) — standing down"; return 0
  fi
  # Detach into a new session so the bot outlives the shell (or agent) that
  # launched it. macOS has no setsid(1), so os.setsid() is called in-process
  # and the interpreter then execs the bot — same effect, no extra process.
  # --mode follows LIVE so LIVE=1 start cannot silently launch a demo-mode bot
  # after a live preflight. Even if misconfigured, the SAFE-03 gate in
  # live/safety.py (verify_execution_allowed) refuses mode=demo + REAL account
  # and enabled=false + REAL account, so the engine itself is the backstop.
  MODE="$([ "$LIVE" = "1" ] && echo live || echo demo)"
  CONFIG="$CONFIG" DECISION_LOG="$DECISION_LOG" MODE="$MODE" .venv/bin/python -c '
import os, sys
os.setsid()
os.execv(sys.executable, [sys.executable, "-m", "trading_bot.cli", "live",
                          "--mode", os.environ["MODE"],
                          "--config", os.environ["CONFIG"],
                          "--log", os.environ["DECISION_LOG"]])
' >> "$LOGFILE" 2>&1 < /dev/null &
  echo $! > "$PIDFILE"
  disown 2>/dev/null || true
  sleep 3
  kill -0 "$(cat "$PIDFILE")" 2>/dev/null \
    && echo "started (pid $(cat "$PIDFILE")) -> output/$DECISION_LOG" \
    || { echo "FAILED to start; see $LOGFILE" >&2; tail -5 "$LOGFILE" >&2; return 1; }
}

stop() {
  [ -f "$PIDFILE" ] || { echo "not running"; return 0; }
  kill "$(cat "$PIDFILE")" 2>/dev/null || true
  rm -f "$PIDFILE"
  echo "stopped"
}

status() {
  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "running (pid $(cat "$PIDFILE"))"
  else
    echo "not running"
  fi
  tail -3 "output/$DECISION_LOG" 2>/dev/null || true
}

case "${1:-status}" in
  start) start ;;
  stop) stop ;;
  status) status ;;
  check) check ;;
  *) echo "usage: $0 start|stop|status|check" >&2; exit 2 ;;
esac
