"""Merge backtest + live/demo trades into one ledger (Phase 3, 04-01).

    python scripts/trade_ledger.py              # writes output/ledger.csv
    python scripts/trade_ledger.py --once       # print-only, no CSV
    python scripts/trade_ledger.py --json       # also dump a JSON summary

Read-only, stdlib-only, never touches the broker. Merges three sources:

  output/trades.csv         backtest run (source=backtest), the per-trade CSV
                            the backtest CLI writes
  output/live_*.log         `event=order_placed` decision lines (source=live),
                            with entry/sl/tp/ticket from the log fields
  output/closes.log         `event=trade_closed` lines written by
                            watch_closes.py, matched to the live entries by
                            ticket to attach the exit price, reason and R

A live entry with no matching close yet is reported as open (exit fields
blank). R is computed the same way account_report.py does it — from the stop
carried in the order_placed line, never guessed. A trade whose log line is
missing shows r="?".

This is the "review a full trade ledger covering backtest and live/demo runs"
criterion of Phase 3. The exit is where the money is decided; the bot logs
every entry but no exits (they fire broker-side), so the closes.log join is
what turns the decision logs into a ledger.
"""

import argparse
import glob
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

TRADES_CSV = ROOT / "output" / "trades.csv"
CLOSES_LOG = ROOT / "output" / "closes.log"
LEDGER_CSV = ROOT / "output" / "ledger.csv"
# Directory scanned for live decision logs. A module constant so tests can
# point it at a sandbox; production never changes it.
LIVE_LOG_GLOB = str(ROOT / "output" / "live_*.log")

ORDER_RE = re.compile(
    r"event=order_placed .*?ticket=(?P<ticket>\d+).*?"
    r"symbol=(?P<symbol>\S+).*?entry=(?P<entry>[-\d.]+) "
    r"sl=(?P<sl>[-\d.]+) tp=(?P<tp>[-\d.]+)"
)
CLOSE_RE = re.compile(
    r"event=trade_closed .*?ticket=(?P<ticket>\d+) .*?"
    r"entry=(?P<entry>[-\d.]+) exit=(?P<exit>[-\d.]+) .*?"
    r"profit=(?P<profit>[+\-\d.]+) r=(?P<r>\S+)"
)


def _parse_close(line: str) -> dict | None:
    m = CLOSE_RE.search(line)
    if not m:
        return None
    return {
        "ticket": int(m.group("ticket")),
        "entry": float(m.group("entry")),
        "exit": float(m.group("exit")),
        "profit": float(m.group("profit")),
        "r": m.group("r"),
        "how": "tp" if "how=tp" in line else "sl" if "how=sl" in line else "other",
    }


def _parse_order(line: str) -> dict | None:
    m = ORDER_RE.search(line)
    if not m:
        return None
    return {
        "ticket": int(m.group("ticket")),
        "symbol": m.group("symbol"),
        "entry": float(m.group("entry")),
        "sl": float(m.group("sl")),
        "tp": float(m.group("tp")),
    }


def load_backtest() -> list[dict]:
    """Rows from output/trades.csv (the backtest CLI's per-trade file)."""
    if not TRADES_CSV.exists():
        return []
    rows = []
    with open(TRADES_CSV, encoding="utf-8") as fh:
        next(fh, None)  # header
        for line in fh:
            parts = line.strip().split(",")
            if len(parts) < 9:
                continue
            rows.append(
                {
                    "source": "backtest",
                    "entry_time": parts[0],
                    "entry": float(parts[1]),
                    "sl": float(parts[2]),
                    "tp": float(parts[3]),
                    "exit_time": parts[4] or None,
                    "exit_price": float(parts[5]) if parts[5] else None,
                    "exit_reason": parts[6] or None,
                    "r": parts[8] if parts[8] else None,
                }
            )
    return rows


def load_live() -> list[dict]:
    """order_placed rows from output/live_*.log, joined to closes.log by ticket."""
    orders: dict[int, dict] = {}
    for path in sorted(glob.glob(LIVE_LOG_GLOB)):
        for line in Path(path).read_text(errors="replace").splitlines():
            order = _parse_order(line)
            if order:
                orders[order["ticket"]] = order

    closes: dict[int, dict] = {}
    if CLOSES_LOG.exists():
        for line in CLOSES_LOG.read_text(errors="replace").splitlines():
            close = _parse_close(line)
            if close:
                closes[close["ticket"]] = close

    rows = []
    for ticket, order in sorted(orders.items()):
        c = closes.get(ticket)
        row = {
            "source": "live",
            "entry_time": None,
            "entry": order["entry"],
            "sl": order["sl"],
            "tp": order["tp"],
            "exit_time": None,
            "exit_price": None,
            "exit_reason": None,
            "r": None,
            "symbol": order["symbol"],
            "ticket": ticket,
        }
        if c:
            row["exit_time"] = None  # closes.log carries no timestamp in the regex
            row["exit_price"] = c["exit"]
            row["exit_reason"] = c["how"]
            row["r"] = c["r"]
            row["profit"] = c["profit"]
        rows.append(row)
    return rows


def summarize(rows: list[dict]) -> dict:
    """Counts, win rate and net R per source, matching account_report's R basis."""
    out = {}
    for source in ("backtest", "live"):
        subset = [r for r in rows if r["source"] == source]
        if not subset:
            continue
        closed = [r for r in subset if r["exit_price"] is not None]
        rs = []
        for r in closed:
            try:
                rs.append(float(r["r"]))
            except (TypeError, ValueError):
                pass
        wins = sum(1 for x in rs if x > 0)
        out[source] = {
            "trades": len(subset),
            "closed": len(closed),
            "open": len(subset) - len(closed),
            "win_rate": f"{wins / len(rs):.1%}" if rs else None,
            "net_r": round(sum(rs), 4) if rs else None,
        }
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--once", action="store_true", help="print only, write no CSV")
    p.add_argument("--json", action="store_true", help="print a JSON summary too")
    a = p.parse_args(argv)

    rows = load_backtest() + load_live()
    rows.sort(key=lambda r: r.get("entry_time") or "", reverse=True)

    def _val(x):
        return "" if x is None else str(x)

    if not a.once:
        TRADES_CSV.parent.mkdir(parents=True, exist_ok=True)
        out = LEDGER_CSV
        header = [
            "source", "entry_time", "entry", "sl", "tp",
            "exit_time", "exit_price", "exit_reason", "r",
        ]
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(",".join(header) + "\n")
            for r in rows:
                fh.write(",".join(_val(r.get(h)) for h in header) + "\n")
        print(f"ledger: {len(rows)} trades -> {out}")

    print(f"{'source':<9} trades closed open  win_rate net_r")
    for source, s in summarize(rows).items():
        print(
            f"{source:<9} {s['trades']:<6} {s['closed']:<6} {s['open']:<4} "
            f"{str(s['win_rate']):<9} {s['net_r']}"
        )
    if a.json:
        print(json.dumps(summarize(rows), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
