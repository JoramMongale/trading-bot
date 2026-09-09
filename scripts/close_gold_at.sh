#!/usr/bin/env bash
# Re-arm ONLY the gold close, one minute later than the original schedule.
#
# The gold bot's stopper fires at 20:00:00 UTC exactly -- the same second the
# first close timer was set for, and an M5 bar boundary. If the close won that
# race the bot would still be alive, see no open position, and could place a
# fresh order on the 20:00 bar seconds before dying. 20:01 puts the close
# safely after the bot is dead and still before the BTC bot starts at 20:02.

set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
PY="$ROOT/.venv/bin/python"

TICKET=433789109
CLOSE_AT=202608212001   # UTC

wait_until() {  # $1 = YYYYMMDDHHMM in UTC
  while [[ "$(date -u +%Y%m%d%H%M)" < "$1" ]]; do sleep 20; done
}

nohup bash -c "
  $(declare -f wait_until)
  wait_until $CLOSE_AT
  cd '$ROOT'
  '$PY' scripts/close_position.py --ticket $TICKET --confirm
" >> "$ROOT/output/close_gold.out" 2>&1 &
echo "re-armed: close gold $TICKET at $CLOSE_AT UTC  (pid $!)"
