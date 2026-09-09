#!/usr/bin/env bash
# Bring the gold bot up on Monday morning, under the same supervisor as BTC.
#
#   ./scripts/start_gold_monday.sh
#
# Waits until Monday 06:00 UTC / 08:00 SAST, then hands over to
# supervise_live.sh, which pre-flights and restarts exactly as it does for BTC.
#
# NOT at the weekly open (Sunday ~21:00 UTC), deliberately. Two reasons:
# liquidity is thin and spreads are wide at the open, which is a poor moment for
# a strategy whose entire edge estimate is smaller than a normal spread; and the
# strategy reads a 69-bar M5 window, so starting at the open means most of that
# window is Friday's market. By 06:00 UTC the whole lookback is fresh.
#
# There is no separate market-open check here and none is needed: preflight_live
# refuses a feed older than 15 minutes, so if gold is shut -- holiday, late open,
# broker outage -- the supervisor simply retries with backoff and places nothing.

set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"

START_AT=202608240600   # Monday 2026-08-24 06:00 UTC = 08:00 SAST

wait_until() { while [[ "$(date -u +%Y%m%d%H%M)" < "$1" ]]; do sleep 30; done; }

nohup bash -c "
  $(declare -f wait_until)
  wait_until $START_AT
  cd '$ROOT'
  exec bash scripts/supervise_live.sh config/config-cent.toml live_cent.log cent
" >> "$ROOT/output/supervise_cent.out" 2>&1 &
echo "gold scheduled: supervisor starts at $START_AT UTC (pid $!)"
echo "  cancel:  pkill -f wait_until"
echo "  watch:   tail -f output/supervise_cent.log"
