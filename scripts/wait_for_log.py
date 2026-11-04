"""Wait for new lines matching a pattern in a log file, and print them.

    python scripts/wait_for_log.py <log> <start_byte> <pattern> <timeout_s>

``pattern`` may hold several alternatives separated by ``|`` (any one matches).

Only lines written after byte ``start_byte`` count, so old lines from an
earlier run are ignored. Prints every matching new line once at least one has
appeared (giving the writer a moment to finish the batch), then exits 0.
Exits 1 if nothing matched within ``timeout_s``. Used by restart_bots.bat.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path


def new_matches(path: Path, start: int, pattern: str) -> list[str]:
    if not path.exists():
        return []
    with path.open("rb") as f:
        size = f.seek(0, 2)
        f.seek(start if start <= size else 0)  # file rotated/truncated -> read it all
        lines = f.read().decode("utf-8", "replace").splitlines()
    alts = [p for p in pattern.split("|") if p]
    return [line for line in lines if any(p in line for p in alts)]


def main(argv: list[str]) -> int:
    log, start, pattern, timeout = Path(argv[1]), int(argv[2]), argv[3], float(argv[4])
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if new_matches(log, start, pattern):
            time.sleep(2)
            for line in new_matches(log, start, pattern):
                print("  " + line)
            return 0
        time.sleep(3)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
