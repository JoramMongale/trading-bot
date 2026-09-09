#!/usr/bin/env bash
# Start/stop the Next.js dashboard (plan 03-05, DASH-01/DASH-02).
#
#   ./scripts/web_dashboard.sh start
#   ./scripts/web_dashboard.sh stop
#
# The dashboard is READ-ONLY and hard-binds 127.0.0.1 (loopback only). It reads
# the DuckDB marts (data/analytics/trading.duckdb) via @duckdb/node-api; load
# the warehouse first with `python scripts/warehouse_cli.py load` + `dbt run`
# (the start script warns, does not block).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WEB="$ROOT/web"
PIDFILE="$WEB/.next/.dashboard.pid"
OUT="$WEB/.next/dashboard.out"
ERR="$WEB/.next/dashboard.err"
ACTION="${1:-start}"

start() {
  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "Dashboard already running (pid $(cat "$PIDFILE")) on http://127.0.0.1:3000"
    return
  fi
  if [ ! -f "$ROOT/data/analytics/trading.duckdb" ]; then
    echo "WARNING: warehouse not found."
    echo "  Run: python scripts/warehouse_cli.py load   then: (cd dbt; dbt run)"
    echo "  Starting anyway — pages will show the empty state."
  fi
  (cd "$WEB" && npm run start -- -H 127.0.0.1 -p 3000 >"$OUT" 2>"$ERR" & echo $! >"$PIDFILE")
  echo "Dashboard starting on http://127.0.0.1:3000 (pid $(cat "$PIDFILE"))"
}

stop() {
  if [ ! -f "$PIDFILE" ]; then
    echo "Dashboard not running (no pidfile)"
    return
  fi
  local pid
  pid="$(cat "$PIDFILE")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" && echo "Dashboard stopped (pid $pid)"
  else
    echo "Dashboard pidfile stale — nothing to stop"
  fi
  rm -f "$PIDFILE"
}

case "$ACTION" in
  start) start ;;
  stop) stop ;;
  *) echo "usage: $0 [start|stop]"; exit 2 ;;
esac
