"""Record this process's pid, then run the bot CLI in the SAME process.

    python scripts/run_with_pidfile.py output/live_cent.pid live --mode live \
        --config config/config-cent.toml --log live_cent.log

Why this exists. The Windows supervisor is a batch file, and batch cannot learn
a child process's pid without either ``wmic`` (deprecated in Windows 11) or
PowerShell (which this deployment deliberately avoids, having no way to test it
before the machine that holds real money runs it). Four scripts —
``health_check``, ``dashboard``, ``monitor_trade`` and ``tune_risk`` — read
``output/live_<tag>.pid``, so a supervisor that silently skipped it would
degrade all four to reporting "not running" on a perfectly healthy bot.

Writing the pid from inside the bot's own process removes the guesswork
entirely: the pid recorded is, by construction, the pid running the trade loop.
Guessing it from the outside — matching on process name, or on a config path in
a command line — is exactly the kind of near-enough identification that this
codebase has already been bitten by when picking terminals.

The bash supervisor keeps writing the pidfile itself; ``$!`` is unambiguous
there, so there is nothing to fix on that side.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from trading_bot.cli import main


def run(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(
            "usage: run_with_pidfile.py PIDFILE [cli args...]",
            file=sys.stderr,
        )
        return 2

    pidfile = Path(args[0])
    pidfile.parent.mkdir(parents=True, exist_ok=True)
    pidfile.write_text(str(os.getpid()))

    try:
        return main(args[1:])
    finally:
        # Clear the pidfile only if it is still OURS. A supervisor that
        # restarted quickly may already have written a newer pid over it, and
        # deleting that would leave the replacement bot invisible to every
        # status tool — the failure this script exists to prevent, arriving by
        # the back door.
        try:
            if pidfile.read_text().strip() == str(os.getpid()):
                pidfile.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(run())
