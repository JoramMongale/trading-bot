"""Analytics warehouse CLI (plan 03-03).

    python scripts/warehouse_cli.py load                # ingest output/ + data/processed/
    python scripts/warehouse_cli.py load --db PATH      # different database file
    python scripts/warehouse_cli.py load --include-histdata   # also ingest data/raw M1 CSVs (heavy)

Read-only against the bot; writes only the local analytics DuckDB file.
duckdb is an OPTIONAL extra — without it the loader explains how to install it
and exits 2, so the base bot never depends on it.

NOTE: named ``warehouse_cli`` (not ``warehouse``) so the module never shadows
the ``warehouse`` package on sys.path (test collection injects scripts/ ahead
of the repo root). The plan named this file ``scripts/warehouse.py`` — a
documented deviation (see 03-03-SUMMARY.md).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from warehouse.load import DEFAULT_DB, load  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python scripts/warehouse_cli.py")
    sub = parser.add_subparsers(dest="command", required=True)

    cmd = sub.add_parser("load", help="ingest bot artifacts into the DuckDB warehouse")
    cmd.add_argument("--db", default=str(DEFAULT_DB), help="path to the DuckDB file")
    cmd.add_argument(
        "--include-histdata",
        action="store_true",
        help="also ingest data/raw histdata M1 CSVs (heavy; off by default)",
    )

    args = parser.parse_args(argv)
    if args.command != "load":
        return 2

    try:
        counts = load(db_path=args.db, include_histdata=args.include_histdata)
    except ImportError as exc:
        if "duckdb" in str(exc):
            print(
                "warehouse requires the 'analytics' extra: "
                '.venv\\Scripts\\pip install -e ".[analytics]"',
                file=sys.stderr,
            )
            return 2
        raise

    for table, rows in sorted(counts.items()):
        print(f"{table}: {rows} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
