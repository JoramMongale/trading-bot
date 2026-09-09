#!/usr/bin/env bash
# One-shot setup for macOS and Linux.
#
#   ./scripts/setup.sh           backtest only (no MetaTrader needed)
#   ./scripts/setup.sh --live    also install the MT5 bridge client
#
# Live trading needs a MetaTrader 5 terminal, and there is no macOS or Linux
# build of it or its Python API -- `pip download MetaTrader5` returns "No
# matching distribution found" on both. The terminal therefore runs in a
# linux/amd64 Wine container and is reached over RPC. See docs/.
set -euo pipefail
cd "$(dirname "$0")/.."

LIVE=0
[ "${1:-}" = "--live" ] && LIVE=1

say() { printf '\n== %s\n' "$*"; }
die() { printf '\nFAILED: %s\n' "$*" >&2; exit 1; }

say "checking Python"
PY=""
for c in python3.14 python3.13 python3.12 python3.11 python3 python; do
  command -v "$c" >/dev/null 2>&1 || continue
  # 3.11 is the floor: the config loader uses stdlib tomllib.
  if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
[ -n "$PY" ] || die "need Python 3.11 or newer (tomllib is stdlib from 3.11).
       macOS:  brew install python@3.12
       Debian: sudo apt install python3.12 python3.12-venv"
echo "   using $PY ($("$PY" --version))"

say "creating .venv"
[ -d .venv ] || "$PY" -m venv .venv
VPY=.venv/bin/python
"$VPY" -m pip install --quiet --upgrade pip

say "installing the project"
"$VPY" -m pip install --quiet -e ".[dev]" || die "pip install failed"

if [ "$LIVE" -eq 1 ]; then
  say "installing the MT5 bridge client"
  if "$VPY" -m pip install --quiet siliconmetatrader5; then
    echo "   ok — you still need Docker and the MT5 container running"
  else
    echo "   could not install siliconmetatrader5; backtesting still works" >&2
  fi
fi

say "running the tests"
"$VPY" -m pytest -q || die "tests did not pass — stop here and investigate"

cat <<'NEXT'

== ready

  backtest (no MetaTrader needed):
      .venv/bin/python -m trading_bot.cli backtest

  dry run, places nothing:
      .venv/bin/python -m trading_bot.cli live --mode dry-run --once

  live/demo needs the MT5 container: see docs/macos-demo-setup.md,
  then .venv/bin/python scripts/preflight_demo.py

  Edit config/config.toml before trading. Keep [live] mode = "demo".
NEXT
