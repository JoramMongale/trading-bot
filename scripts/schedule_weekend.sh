#!/usr/bin/env bash
# Friday-evening schedule for the cent account. Run once, from the repo root.
#
#   22:00 SAST (20:00 UTC)  close gold ticket 433789109
#   22:02 SAST (20:02 UTC)  start the BTCUSDc bot for the weekend
#   Sun 08:00 SAST          stop the BTCUSDc bot (~34h run, ends Sunday morning)
#
# The gold bot's own stopper already fires at 19:57 UTC, so it is dead before
# the close runs and cannot re-enter afterwards.
#
# Each timer polls the wall clock instead of sleeping once for the whole
# interval: a single long `sleep` overruns by however long the MacBook was
# asleep, and the Sunday stop is 48 hours out.

set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
PY="$ROOT/.venv/bin/python"

TICKET=433789109
CLOSE_AT=202608212000   # UTC, YYYYMMDDHHMM -- compared lexicographically
BTC_AT=202608212002
BTC_STOP_AT=202608230600  # Sunday 06:00 UTC / 08:00 SAST

wait_until() {  # $1 = YYYYMMDDHHMM in UTC
  while [[ "$(date -u +%Y%m%d%H%M)" < "$1" ]]; do sleep 20; done
}
export -f wait_until

# --- 1. close the gold position -------------------------------------------
nohup bash -c "
  $(declare -f wait_until)
  wait_until $CLOSE_AT
  cd '$ROOT'
  '$PY' scripts/close_position.py --ticket $TICKET --confirm
" >> "$ROOT/output/close_gold.out" 2>&1 &
echo "scheduled: close gold $TICKET at $CLOSE_AT UTC  (pid $!)"

# --- 2. start the BTC bot --------------------------------------------------
nohup bash -c "
  $(declare -f wait_until)
  wait_until $BTC_AT
  cd '$ROOT'
  '$PY' -m trading_bot.cli live --mode live --config config/config-btc.toml --log live_btc.log &
  echo \$! > '$ROOT/output/live_btc.pid'
  wait
" >> "$ROOT/output/live_btc.out" 2>&1 &
echo "scheduled: start BTC bot at $BTC_AT UTC  (pid $!)"

# --- 3. stop the BTC bot before gold reopens -------------------------------
nohup bash -c "
  $(declare -f wait_until)
  wait_until $BTC_STOP_AT
  P=\$(cat '$ROOT/output/live_btc.pid' 2>/dev/null)
  [ -n \"\$P\" ] && kill \$P 2>/dev/null
  echo \"\$(date -u +%FT%H:%MZ) scheduled stop fired (pid \$P)\" >> '$ROOT/output/live_btc.out'
" >> "$ROOT/output/live_btc.out" 2>&1 &
echo "scheduled: stop BTC bot at $BTC_STOP_AT UTC  (pid $!)"

echo
echo "to cancel everything:  pkill -f wait_until"
echo "to stop BTC early:     kill \$(cat output/live_btc.pid)"
