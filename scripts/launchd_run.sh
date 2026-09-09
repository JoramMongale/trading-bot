#!/usr/bin/env bash
# Foreground entry point for the launchd agent (com.joram.trading-bot-demo).
#
# launchd supervises and restarts, so this must NOT detach — it execs the bot
# in the foreground. Use scripts/run_demo.sh for a manual, detached run.
#
# Brings the stack up in dependency order, because after a reboot none of it
# is running: colima VM -> container -> openbox -> ACCOUNT TERMINAL -> bot.
#
# Everything from openbox onwards is delegated to `run_demo.sh check` rather
# than repeated here. That matters: the account-terminal launch and the
# bar-freshness gate both live there, and a second copy of that logic would
# drift out of sync with the one people actually run by hand.
set -uo pipefail

cd "$(dirname "$0")/.."
export PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin

# INSTANCE selects which bot this agent supervises; see run_demo.sh. Empty is
# the primary M5 bot, "m1" the sibling. The plist sets it.
INSTANCE="${INSTANCE:-}"
SUFFIX="${INSTANCE:+_$INSTANCE}"
CONFIG="config/config${INSTANCE:+-$INSTANCE}.toml"
PIDFILE="output/live${SUFFIX}.pid"
DECISION_LOG="live${SUFFIX}.log"
LOCKDIR="output/.start${SUFFIX}.lock"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') [launchd_run${SUFFIX}] $*"; }

# Mutual exclusion with the manual path (scripts/run_demo.sh start). Two bots
# on the same account and magic number would open two positions per setup and
# defeat the one-trade-at-a-time guard, which only ever looks at the broker.
# Exit 0, not 1: launchd's KeepAlive respawns us after ThrottleInterval, so
# this stands down now and takes over whenever the manual run stops.
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  log "a bot is already running (pid $(cat "$PIDFILE")) — standing down"
  exit 0
fi

# Take the same lock run_demo.sh uses. Without it, a manual start and this
# agent can both pass the pidfile check and then spend tens of seconds in
# bring-up before either claims the slot — which on 2026-08-20 left three bots
# on one magic number. mkdir is atomic on POSIX.
mkdir -p output
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  log "a start is already in progress ($LOCKDIR) — standing down"
  exit 0
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null || true' EXIT INT TERM

# 1) Colima VM. Not auto-started on login, and docker is useless without it.
if ! colima status >/dev/null 2>&1; then
  log "colima not running — starting (QEMU x86_64, several minutes)"
  colima start --arch x86_64 --vm-type=qemu --cpu 4 --memory 6 \
    || { log "FAIL colima start"; exit 1; }
fi
docker context use colima >/dev/null 2>&1 || true

# 2) Container. compose sets restart:unless-stopped, but a stopped container
#    stays stopped until something starts it.
if ! docker ps --format '{{.Names}}' | grep -qx siliconmt5; then
  log "starting container siliconmt5"
  docker start siliconmt5 >/dev/null 2>&1 || { log "FAIL container start"; exit 1; }
fi

# 3) Openbox, the ACCOUNT terminal, and a fresh feed. `run_demo.sh check` owns
#    all three. The account terminal is the one that bites after a reboot: the
#    container auto-starts the MT5 install WITHOUT accounts.dat, whose
#    new-account wizard is a modal that blocks the API, so every bridge call
#    returns -10005 IPC timeout until the right terminal is launched. Before
#    that was automated this loop would simply have burned its 20 minutes and
#    given up.
#
#    Retried around `check` because a cold MT5 needs minutes: check's own
#    internal retry is sized for a warm machine, this loop for a boot.
for i in $(seq 1 40); do
  if INSTANCE="$INSTANCE" scripts/run_demo.sh check; then
    log "stack ready"
    break
  fi
  if [ "$i" -eq 40 ]; then
    log "FAIL stack never became ready (20 min)."
    log "     If accounts.dat is gone this needs a human: log in at"
    log "     http://localhost:6081/vnc.html and the agent will pick it up."
    exit 1
  fi
  log "not ready (attempt $i/40) — retrying in 30s"
  sleep 30
done

# 4) Foreground: launchd owns the lifecycle from here. `exec` keeps this PID,
#    so the pidfile written now is the bot's own and `run_demo.sh status`
#    reports it like any manual run. Note that `run_demo.sh stop` will kill it
#    and launchd will simply start it again — to stop it for good, bootout the
#    agent (see the plist header).
# Re-check immediately before claiming the slot: `check` above can take
# minutes on a cold boot, and a manual start may have won the race meanwhile.
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  log "another bot claimed the slot during bring-up — standing down"
  exit 0
fi
log "starting bot (mode=demo, config=$CONFIG, log=$DECISION_LOG)"
echo $$ > "$PIDFILE"
rmdir "$LOCKDIR" 2>/dev/null || true   # released before exec replaces us
trap - EXIT INT TERM
exec .venv/bin/python -m trading_bot.cli live --mode demo \
     --config "$CONFIG" --log "$DECISION_LOG"
