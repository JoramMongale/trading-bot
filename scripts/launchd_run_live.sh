#!/usr/bin/env bash
# Foreground entry point for the REAL-money launchd agents
# (com.joram.trading-bot-btc / com.joram.trading-bot-cent).
#
#   scripts/launchd_run_live.sh btc|cent
#
# launchd supervises and restarts, so this must NOT detach — it execs
# scripts/supervise_live.sh in the foreground, which itself never detaches.
#
# Why not scripts/launchd_run.sh: that path calls run_demo.sh check, which calls
# preflight_demo.py, which refuses REAL accounts by design. That guard stays.
# This is the real-money counterpart: the same stack bring-up, but the final
# gate is `preflight_live.py --config <cfg> --real-account` via the LIVE=1
# switch in run_demo.sh.
#
# Brings the stack up in dependency order, because after a reboot none of it is
# running: colima VM -> container -> openbox -> ACCOUNT TERMINAL -> real-money
# preflight -> bot.
#
# Everything from openbox onwards is delegated to `run_demo.sh check` (with
# LIVE=1) rather than repeated here. That matters: the account-terminal launch
# and the bar-freshness gate both live there, and a second copy of that logic
# would drift out of sync with the one people actually run by hand.
#
# Mutual exclusion with the manual path (supervise_live.sh): if the manual bot
# owns output/live_<tag>.pid, this exits 0 and launchd respawns it after
# ThrottleInterval; it takes over the moment the manual bot is gone. Two bots
# on one magic number would each mistake the other's position for their own.
#
# CRITICAL: do NOT edit scripts/supervise_live.sh while a manual supervisor is
# executing it — bash re-reads a running script, and editing it live with real
# money on the account is undefined behaviour. This script wraps it unmodified.
set -uo pipefail

cd "$(dirname "$0")/.."
export PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin

TAG="${1:?usage: scripts/launchd_run_live.sh btc|cent}"
CONFIG="config/config-$TAG.toml"
DECISION_LOG="live_$TAG.log"
PIDFILE="output/live_$TAG.pid"
LOCKDIR="output/.live-$TAG.lock"
STACK_LOCK="output/.stack-bring-up.lock"
STACK_LOCK_PID="output/.stack-bring-up.pid"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') [launchd_run_live:$TAG] $*"; }

# Stand down if a bot is already running for this tag. Exit 0, not 1: launchd's
# KeepAlive respawns us after ThrottleInterval, so this stands down now and
# takes over whenever the manual run stops.
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  log "a bot is already running (pid $(cat "$PIDFILE")) — standing down"
  exit 0
fi

# Per-tag lock, mirroring launchd_run.sh. Without it, a manual start and this
# agent can both pass the pidfile check and then spend tens of seconds in
# bring-up before either claims the slot — which on 2026-08-20 left three bots
# on one magic number. mkdir is atomic on POSIX.
mkdir -p output
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  log "a start is already in progress ($LOCKDIR) — standing down"
  exit 0
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null || true' EXIT INT TERM

# STACK BRING-UP, serialised across both agents. Both RunAtLoad at the same
# login and would race colima/docker/terminal bring-up; the shared atomic-mkdir
# lock serialises them. A SIGKILLed agent leaves no trap behind, so the lock
# self-heals: an owner pid that is not alive reclaims it immediately.
owner=0
for i in $(seq 1 60); do
  if mkdir "$STACK_LOCK" 2>/dev/null; then
    echo $$ > "$STACK_LOCK_PID"
    owner=1
    break
  fi
  if [ -f "$STACK_LOCK_PID" ]; then
    opid=$(cat "$STACK_LOCK_PID" 2>/dev/null || echo "")
    if [ -n "$opid" ] && ! kill -0 "$opid" 2>/dev/null; then
      log "reclaiming stale stack lock (owner $opid dead)"
      rmdir "$STACK_LOCK" 2>/dev/null || true
      rm -f "$STACK_LOCK_PID"
      continue
    fi
  fi
  log "stack bring-up in progress elsewhere — waiting"
  sleep 30
done
if [ "$owner" -ne 1 ]; then
  log "FAIL never acquired stack lock after 60 tries (30 min)"
  exit 1
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null || true; rmdir "$STACK_LOCK" 2>/dev/null || true; rm -f "$STACK_LOCK_PID"' EXIT INT TERM

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

# 3) Openbox, the ACCOUNT terminal, and a fresh feed. `run_demo.sh check` with
#    LIVE=1 owns all three and gates on preflight_live.py --real-account. The
#    account terminal is the one that bites after a reboot: the container
#    auto-starts the MT5 install WITHOUT accounts.dat, whose new-account wizard
#    is a modal that blocks the API, so every bridge call returns -10005 IPC
#    timeout until the right terminal is launched.
#
#    Retried around `check` because a cold MT5 needs minutes: check's own
#    internal retry is sized for a warm machine, this loop for a boot.
#
#    We hold the stack lock for the whole loop so the account terminal is
#    launched exactly once even when both agents boot together.
for i in $(seq 1 40); do
  if LIVE=1 INSTANCE="$TAG" scripts/run_demo.sh check; then
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

# 4) Release the stack lock; a manual `supervise_live.sh` may have claimed the
#    slot during bring-up, so re-check before we take over.
rmdir "$STACK_LOCK" 2>/dev/null || true
rm -f "$STACK_LOCK_PID"
trap 'rmdir "$LOCKDIR" 2>/dev/null || true' EXIT INT TERM
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  log "another bot claimed the slot during bring-up — standing down"
  exit 0
fi

# 5) Foreground: launchd owns the lifecycle from here. `exec` keeps this PID.
#    supervise_live.sh preflights with preflight_live.py --real-account before
#    EVERY start, holds caffeinate for its own lifetime, writes
#    output/supervise_<tag>.pid and output/live_<tag>.pid, and its crash-loop
#    brake survives inside the launchd job.
rmdir "$LOCKDIR" 2>/dev/null || true
trap - EXIT INT TERM
log "starting supervisor (mode=live, config=$CONFIG, log=$DECISION_LOG)"
exec bash scripts/supervise_live.sh "$CONFIG" "$DECISION_LOG" "$TAG"
