#!/usr/bin/env bash
# Keep a REAL-money bot running 24/7, with a crash-loop brake.
#
#   ./scripts/supervise_live.sh config/config-btc.toml live_btc.log btc
#
# Runs in the FOREGROUND and never detaches, so it can be supervised by launchd
# (see com.joram.trading-bot-btc.plist) or simply left in a terminal.
#
# Why not scripts/launchd_run.sh: that path calls run_demo.sh check, which calls
# preflight_demo.py, which refuses REAL accounts by design. That guard stays.
# This is the real-money counterpart and uses preflight_live.py, which runs the
# same checks but demands an explicit --real-account acknowledgement.
#
# THE CRASH-LOOP BRAKE IS THE POINT. Unattended restart is the dangerous half of
# 24/7: a bot that dies for a reason that will recur -- bad config, a symbol the
# broker stopped quoting, an expired password -- will otherwise be restarted
# forever, and each restart is a fresh chance to do the wrong thing with real
# money. So: exponential backoff, and a hard stop after too many failures in a
# short window. Stopping and staying stopped is the correct behaviour for a bot
# that cannot start cleanly. The account's own 6% daily-loss halt is the second
# line of defence, not the first.

set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
PY="$ROOT/.venv/bin/python"

CONFIG="${1:-config/config-btc.toml}"
LOGNAME="${2:-live_btc.log}"
TAG="${3:-btc}"
PIDFILE="$ROOT/output/live_${TAG}.pid"
SUPLOG="$ROOT/output/supervise_${TAG}.log"

MAX_FAILURES=5        # rapid failures tolerated ...
FAILURE_WINDOW=900    # ... within this many seconds before giving up
BACKOFF_START=10
BACKOFF_MAX=300

say() { echo "$(date -u +%FT%H:%M:%SZ) $*" | tee -a "$SUPLOG"; }

say "supervisor starting  config=$CONFIG log=$LOGNAME tag=$TAG"
echo $$ > "$ROOT/output/supervise_${TAG}.pid"

# Hold the machine awake for as long as THIS supervisor lives, and no longer.
#
# This used to be a hand-typed `caffeinate -dimsu &`, which died with the
# terminal that launched it and left a bot claiming to run 24/7 on a laptop free
# to sleep. Nothing announced that; it was found only by checking. Tying the
# assertion to the supervisor's own lifetime means the two can no longer
# disagree: if the supervisor is up, sleep is blocked; when it exits, the
# assertion goes with it rather than lingering.
#
# -i idle  -m disk  -s while on AC  -u user-active  -d display
if command -v caffeinate >/dev/null 2>&1; then
    caffeinate -dimsu -w $$ >/dev/null 2>&1 &
    say "caffeinate holding the machine awake for supervisor $$ (pid $!)"
else
    say "WARNING: caffeinate not found -- the machine may sleep and stop the bot"
fi

backoff=$BACKOFF_START
declare -a failures=()

while true; do
  # Pre-flight before EVERY start, not just the first. A restart four hours
  # later is a different world: the terminal may be logged out, the container
  # may have been rebuilt, the feed may be stale. Starting blind into that is
  # how a bot ends up trading on prices from yesterday.
  if ! "$PY" scripts/preflight_live.py --config "$CONFIG" --real-account >>"$SUPLOG" 2>&1; then
    say "preflight FAILED -- not starting; retrying in ${backoff}s"
    sleep "$backoff"
    backoff=$(( backoff * 2 )); [ "$backoff" -gt "$BACKOFF_MAX" ] && backoff=$BACKOFF_MAX
    continue
  fi

  say "preflight ok -- starting bot"
  "$PY" -m trading_bot.cli live --mode live --config "$CONFIG" --log "$LOGNAME" \
      >>"$ROOT/output/live_${TAG}.out" 2>&1 &
  bot=$!
  echo "$bot" > "$PIDFILE"
  say "bot started pid $bot"
  backoff=$BACKOFF_START      # a clean start clears the backoff

  wait "$bot"
  rc=$?
  rm -f "$PIDFILE"

  # A deliberate stop (SIGTERM/SIGINT from `kill`) must NOT be restarted --
  # otherwise there is no way to stop the thing without racing the supervisor.
  if [ "$rc" -eq 143 ] || [ "$rc" -eq 130 ] || [ "$rc" -eq 0 ]; then
    say "bot exited rc=$rc (deliberate stop) -- supervisor exiting"
    exit 0
  fi

  say "bot DIED rc=$rc"
  now=$(date +%s)
  failures+=("$now")
  # Keep only failures inside the window.
  recent=()
  for ts in "${failures[@]}"; do
    [ $(( now - ts )) -le "$FAILURE_WINDOW" ] && recent+=("$ts")
  done
  failures=("${recent[@]}")

  if [ "${#failures[@]}" -ge "$MAX_FAILURES" ]; then
    say "GIVING UP: ${#failures[@]} failures within ${FAILURE_WINDOW}s."
    say "Something is wrong that a restart will not fix. Check $SUPLOG and"
    say "output/live_${TAG}.out, fix it, then start the supervisor again."
    exit 1
  fi

  say "restarting in ${backoff}s (failure ${#failures[@]}/${MAX_FAILURES})"
  sleep "$backoff"
  backoff=$(( backoff * 2 )); [ "$backoff" -gt "$BACKOFF_MAX" ] && backoff=$BACKOFF_MAX
done
