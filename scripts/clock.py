"""Print the time for supervise_live.bat.

    python scripts/clock.py utc     -> 2026-11-04T16:50:00Z
    python scripts/clock.py epoch   -> 1793811000

Batch cannot do date arithmetic, and inline ``python -c "..."`` inside
``for /f`` breaks on cmd's quote and parenthesis rules. A script with plain
arguments has nothing for cmd to mis-parse.
"""

import datetime
import sys
import time

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "epoch":
        print(int(time.time()))
    else:
        print(datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
