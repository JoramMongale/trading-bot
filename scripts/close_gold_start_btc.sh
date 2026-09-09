#!/usr/bin/env bash
# Do the whole Friday handover NOW instead of at 20:01/20:02.
#
#   1. cancel every pending timer      (else they fire again later)
#   2. stop the gold bot               (BEFORE the close -- see below)
#   3. close the gold position
#   4. start the BTCUSDc bot
#   5. re-arm the Sunday-morning stop
#
# Order is not cosmetic. Closing while the gold bot is still polling would let
# it see no open position on the next M5 bar, find its one-position guard
# satisfied, and place a FRESH gold order -- leaving an unattended position over
# a weekend when gold is shut. The bot dies first, and we verify it is dead.
#
# Cancelling matters just as much: the 20:02 timer would start a SECOND BTC bot
# on magic 77021 in an hour. Two bots sharing a magic each mistake the other's
# position for their own and defeat both dedup guards.

set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
PY="$ROOT/.venv/bin/python"
TICKET=433789109

echo "== 1. cancelling pending timers"
pkill -f wait_until 2>/dev/null && echo "   wait_until timers cancelled" || echo "   none were running"
# The gold bot's original stopper is a plain `sleep`, not a wait_until loop.
for p in $(pgrep -f "scheduled stop fired" 2>/dev/null); do
  kill "$p" 2>/dev/null && echo "   cancelled gold stopper $p"
done
if [ -f output/live_cent.pid ]; then
  GPID=$(cat output/live_cent.pid)
  for p in $(pgrep -f "sleep 15551" 2>/dev/null); do
    kill "$p" 2>/dev/null && echo "   cancelled gold sleeper $p"
  done
fi

echo
echo "== 2. stopping the gold bot"
if [ -f output/live_cent.pid ]; then
  GPID=$(cat output/live_cent.pid)
  if kill -0 "$GPID" 2>/dev/null; then
    kill "$GPID" 2>/dev/null
    for i in 1 2 3 4 5 6 7 8 9 10; do
      kill -0 "$GPID" 2>/dev/null || break
      sleep 1
    done
    if kill -0 "$GPID" 2>/dev/null; then
      echo "   REFUSING TO CONTINUE: gold bot $GPID did not die."
      echo "   Closing now could let it place a fresh order. Investigate first."
      exit 1
    fi
    echo "   gold bot $GPID stopped"
  else
    echo "   gold bot $GPID was already stopped"
  fi
else
  echo "   no pidfile -- assuming no gold bot"
fi

echo
echo "== 3. closing the gold position"
"$PY" scripts/close_position.py --ticket "$TICKET" --confirm | tee -a output/close_gold.out
CLOSE_RC=${PIPESTATUS[0]}
if [ "$CLOSE_RC" -ne 0 ]; then
  echo "   close FAILED (rc=$CLOSE_RC) -- NOT starting the BTC bot."
  echo "   Sort the gold position out first."
  exit 1
fi

echo
echo "== 4. starting the BTCUSDc bot"
"$PY" -c '
import os, sys
os.setsid()
os.execv(sys.executable, [sys.executable, "-m", "trading_bot.cli", "live",
                          "--mode", "live",
                          "--config", "config/config-btc.toml",
                          "--log", "live_btc.log"])
' >> output/live_btc.out 2>&1 < /dev/null &
echo $! > output/live_btc.pid
disown 2>/dev/null || true
sleep 6
BPID=$(cat output/live_btc.pid)
if kill -0 "$BPID" 2>/dev/null; then
  echo "   BTC bot started pid $BPID"
else
  echo "   BTC bot FAILED to start:"
  tail -5 output/live_btc.out
  exit 1
fi
echo "   first log lines:"
tail -3 output/live_btc.log 2>/dev/null | sed 's/^/     /'

echo
echo "== 5. re-arming the Sunday stop (06:00 UTC / 08:00 SAST)"
wait_until() { while [[ "$(date -u +%Y%m%d%H%M)" < "$1" ]]; do sleep 20; done; }
nohup bash -c "
  $(declare -f wait_until)
  wait_until 202608230600
  P=\$(cat '$ROOT/output/live_btc.pid' 2>/dev/null)
  [ -n \"\$P\" ] && kill \$P 2>/dev/null
  echo \"\$(date -u +%FT%H:%MZ) scheduled stop fired (pid \$P)\" >> '$ROOT/output/live_btc.out'
" >> "$ROOT/output/live_btc.out" 2>&1 &
echo "   stop armed for 202608230600 UTC (pid $!)"

echo
echo "== done"
echo "   watch it     tail -f output/live_btc.log"
echo "   stop early   kill \$(cat output/live_btc.pid)"
