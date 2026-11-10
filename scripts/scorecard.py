"""Live scorecard: how the real trades compare with the backtest.

    python scripts/scorecard.py                 print it
    python scripts/scorecard.py --since 2026-11-04

Read-only. Reads output/closes.log (written by watch_closes.py) and, for each
market, compares the live closed trades with what the backtest says is
normal. The watchdog adds this to the daily phone summary.

The question it answers: "is it safe to raise risk yet?" The answer stays
"too early" until MIN_TRADES trades have closed. After that it is only "on
track" when the live average is positive AND the worst drop and losing streak
are no worse than the backtest's.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLOSES_LOG = ROOT / "output" / "closes.log"
# The current setup (Windows, account pins, 10% gold risk, BTC minimum lot)
# went live on this date. Older closes in the log were a different setup.
SINCE = "2026-11-04"
MIN_TRADES = 30


@dataclass(frozen=True)
class Reference:
    """Backtest numbers for one market, at the strategy the live bot runs."""
    name: str
    win_pct: float
    avg_r: float
    max_dd_r: float | None      # deepest peak-to-trough drop, in R
    worst_streak: int | None    # most losses in a row
    p5_30: float | None         # 5th percentile of 30-trade average R
    source: str


# Gold: long rr1.0 on 100k broker XAUUSD M5 bars (2025-03 -> 2026-09),
# measured 2026-11-10 with scripts/backtest_both_scalper.py's engine settings.
# BTC: short rr1.0 from quick task 20260928-btc-fear-greed-direction-filter;
# no BTC variant was profitable, so "about break-even" is the honest target.
REFERENCES = {
    "XAUUSD": Reference("gold", 58.4, 0.091, 8.1, 7, -0.123,
                        "backtest long rr1.0, 437 trades"),
    "BTCUSD": Reference("bitcoin", 54.9, -0.006, None, None, None,
                        "backtest short rr1.0, 410 trades (no edge found)"),
}


def base_symbol(symbol: str) -> str:
    """XAUUSDc / XAUUSDm -> XAUUSD (Exness suffix = account type)."""
    s = symbol.strip().upper()
    return s[:-1] if len(s) > 6 and s[-1] in ("C", "M") else s


def kv(line: str) -> dict[str, str]:
    out = {}
    for tok in line.split():
        if "=" in tok:
            k, _, v = tok.partition("=")
            out[k] = v
    return out


def read_closes(path: Path = CLOSES_LOG, since: str = SINCE) -> list[dict]:
    """trade_closed lines on or after ``since`` (UTC date), oldest first."""
    if not path.exists():
        return []
    seen, out = set(), []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "event=trade_closed" not in line or line[:10] < since:
            continue
        d = kv(line)
        key = (d.get("ticket"), d.get("symbol"))
        if key in seen:  # a re-run backfill can repeat a ticket
            continue
        seen.add(key)
        try:
            profit = float(d.get("profit", "0"))
        except ValueError:
            profit = 0.0
        try:
            r = float(d["r"])
        except (KeyError, ValueError):
            r = None
        out.append({"time": line[:19], "symbol": d.get("symbol", "?"),
                    "profit": profit, "r": r})
    out.sort(key=lambda t: t["time"])
    return out


@dataclass(frozen=True)
class Stats:
    n: int
    n_r: int
    wins: int
    avg_r: float | None
    total_r: float
    max_dd_r: float
    worst_streak: int
    last30_avg_r: float | None
    profit: float


def stats(trades: list[dict]) -> Stats:
    rs = [t["r"] for t in trades if t["r"] is not None]
    wins = sum(1 for t in trades if (t["r"] if t["r"] is not None else t["profit"]) > 0)
    cum = peak = dd = 0.0
    streak = worst = 0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
        streak = streak + 1 if r < 0 else 0
        worst = max(worst, streak)
    last30 = rs[-MIN_TRADES:]
    return Stats(
        n=len(trades), n_r=len(rs), wins=wins,
        avg_r=sum(rs) / len(rs) if rs else None,
        total_r=sum(rs), max_dd_r=dd, worst_streak=worst,
        last30_avg_r=sum(last30) / len(last30) if len(last30) == MIN_TRADES else None,
        profit=sum(t["profit"] for t in trades),
    )


def verdict(s: Stats, ref: Reference | None) -> str:
    if s.n == 0:
        return "no closed trades yet"
    worse = []
    if ref and ref.max_dd_r is not None and s.max_dd_r > ref.max_dd_r:
        worse.append(f"drop {s.max_dd_r:.1f}R is deeper than the backtest's worst {ref.max_dd_r:.1f}R")
    if ref and ref.worst_streak is not None and s.worst_streak > ref.worst_streak:
        worse.append(f"{s.worst_streak} losses in a row is more than the backtest's worst {ref.worst_streak}")
    if (ref and ref.p5_30 is not None and s.last30_avg_r is not None
            and s.last30_avg_r < ref.p5_30):
        worse.append(f"last {MIN_TRADES} trades average {s.last30_avg_r:+.2f}R, "
                     f"below the backtest's normal range ({ref.p5_30:+.2f}R)")
    if worse:
        return "⚠️ worse than the backtest: " + "; ".join(worse) + ". Do not raise risk."
    if s.n_r < MIN_TRADES:
        return f"too early to judge ({s.n_r}/{MIN_TRADES} trades). Keep risk as it is."
    if s.avg_r is not None and s.avg_r > 0:
        return "✅ on track: positive and within the backtest's range. A small risk step-up can be considered."
    return "➖ within the backtest's range but not profitable yet. Keep risk as it is."


def scorecard(trades: list[dict] | None = None, since: str = SINCE) -> str:
    trades = read_closes(since=since) if trades is None else trades
    lines = [f"📊 Scorecard since {since} (live vs backtest)"]
    by_market: dict[str, list[dict]] = {}
    for t in trades:
        by_market.setdefault(base_symbol(t["symbol"]), []).append(t)
    for sym in list(REFERENCES) + sorted(set(by_market) - set(REFERENCES)):
        ref = REFERENCES.get(sym)
        market = by_market.get(sym, [])
        if not market and ref is None:
            continue
        s = stats(market)
        name = ref.name if ref else sym
        if s.n == 0:
            lines.append(f"• {name}: {verdict(s, ref)}")
            continue
        avg = f"{s.avg_r:+.2f}R" if s.avg_r is not None else "n/a"
        win = 100 * s.wins / s.n
        line = (f"• {name}: {s.n} trades, win {win:.0f}%, avg {avg}/trade, "
                f"total {s.total_r:+.1f}R, profit {s.profit:+.2f}, "
                f"worst drop {s.max_dd_r:.1f}R, worst losing run {s.worst_streak}")
        if ref:
            line += f"\n  backtest: win {ref.win_pct:.0f}%, avg {ref.avg_r:+.2f}R"
            if ref.max_dd_r is not None:
                line += f", worst drop {ref.max_dd_r:.1f}R, worst losing run {ref.worst_streak}"
        line += f"\n  {verdict(s, ref)}"
        lines.append(line)
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--since", default=SINCE, help="UTC date YYYY-MM-DD (default %(default)s)")
    a = p.parse_args(argv)
    print(scorecard(since=a.since))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
