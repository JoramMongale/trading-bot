"""Separate what the STRATEGY earned from what you DEPOSITED.

    python scripts/account_report.py
    python scripts/account_report.py --zar 16.0024 --since 2026-08-01

While you are funding an account weekly, balance is a useless progress measure:
deposit R500 a week into a system that loses slowly and the balance still climbs.
This reconciles the account into its two independent parts --

    balance  =  deposits - withdrawals  +  trading P&L

-- so the only number that reflects the strategy is isolated and reported on its
own, in USC, in ZAR, and in R multiples.

R multiple is the number that matters, and it cannot be computed from MT5's deal
history alone: the history records what was paid and received, never the stop
that defined the risk. So stops are recovered from the bot's own decision logs
(``order_placed`` lines carry sl/tp/entry) and matched to deals by ticket. A
trade whose log line cannot be found is reported with R as "?" rather than
guessed -- an unknown R is honest, an invented one is not.
"""

import argparse
import glob
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# MT5 deal types. BALANCE covers deposits, withdrawals, credits and corrections
# -- every movement of money that is not a trade.
DEAL_TYPE_BUY = 0
DEAL_TYPE_SELL = 1
DEAL_TYPE_BALANCE = 2

LOG_RE = re.compile(
    r"event=order_placed .*?ticket=(?P<ticket>\d+).*?"
    r"fill=(?P<fill>[-\d.]+).*?symbol=(?P<symbol>\S+).*?"
    r"entry=(?P<entry>[-\d.]+) sl=(?P<sl>[-\d.]+) tp=(?P<tp>[-\d.]+)"
)


def stops_from_logs(log_dir: Path) -> dict[int, dict]:
    """ticket -> {fill, sl, tp} recovered from the bot's decision logs."""
    out: dict[int, dict] = {}
    for path in sorted(glob.glob(str(log_dir / "live*.log"))):
        for line in Path(path).read_text(errors="replace").splitlines():
            m = LOG_RE.search(line)
            if m:
                out[int(m.group("ticket"))] = {
                    "fill": float(m.group("fill")),
                    "sl": float(m.group("sl")),
                    "tp": float(m.group("tp")),
                    "log": Path(path).name,
                }
    return out


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--zar", type=float, default=16.0024,
                   help="USD/ZAR rate for the ZAR column (default: 16.0024)")
    p.add_argument("--since", default=None, help="YYYY-MM-DD (default: 400 days back)")
    p.add_argument("--bridge", choices=["auto", "native", "silicon"], default="auto")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=8001)
    a = p.parse_args(argv)

    from trading_bot.broker.base import BrokerUnavailableError
    from trading_bot.broker.mt5 import _load_mt5, _load_silicon_bridge

    try:
        if a.bridge == "native":
            mt5 = _load_mt5()
        elif a.bridge == "silicon":
            mt5 = _load_silicon_bridge(a.host, a.port)
        else:
            try:
                mt5 = _load_mt5()
            except BrokerUnavailableError:
                mt5 = _load_silicon_bridge(a.host, a.port)
    except BrokerUnavailableError as exc:
        print(f"no MT5 transport: {exc}")
        return 2
    if not mt5.initialize():
        print(f"initialize failed: {mt5.last_error()}")
        return 2

    acct = mt5.account_info()
    start = (
        datetime.strptime(a.since, "%Y-%m-%d")
        if a.since
        else datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=400)
    )
    deals = mt5.history_deals_get(start, datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1))
    deals = sorted(deals or [], key=lambda d: d.time)

    # -- money in and out, which is NOT performance --------------------------
    funding = [d for d in deals if d.type == DEAL_TYPE_BALANCE]
    deposits = sum(d.profit for d in funding if d.profit > 0)
    withdrawals = -sum(d.profit for d in funding if d.profit < 0)

    # -- trades: group deals by position, entry first, exit last -------------
    by_pos: dict[int, list] = defaultdict(list)
    for d in deals:
        if d.type in (DEAL_TYPE_BUY, DEAL_TYPE_SELL) and d.position_id:
            by_pos[d.position_id].append(d)

    stops = stops_from_logs(ROOT / "output")
    rows, trading_pnl, rs = [], 0.0, []
    for pos_id, ds in sorted(by_pos.items(), key=lambda kv: kv[1][0].time):
        entry = ds[0]
        exits = ds[1:]
        if not exits:
            continue  # still open: not realised, so it is not performance yet
        pnl = sum(x.profit + x.swap + x.commission for x in ds)
        trading_pnl += pnl
        # entry.type is the OPENING side: BUY opens a long.
        direction = "long" if entry.type == DEAL_TYPE_BUY else "short"
        exit_price = exits[-1].price
        info = stops.get(pos_id)
        if info and (entry.price - info["sl"]) != 0:
            r = (exit_price - entry.price) / (entry.price - info["sl"])
            rs.append(r)
            r_txt = f"{r:+.2f}"
        else:
            r_txt = "?"
        rows.append((
            datetime.fromtimestamp(entry.time, timezone.utc).strftime("%m-%d %H:%M"),
            pos_id, entry.symbol, direction, entry.volume,
            entry.price, exit_price, pnl, r_txt,
            exits[-1].comment or "",
        ))

    cur = acct.currency
    usc_to_zar = (1 / 100.0) * a.zar if cur == "USC" else a.zar

    def zar(v):
        return v * usc_to_zar

    print(f"account {acct.login} @ {acct.server}   currency {cur}   "
          f"USD/ZAR {a.zar}")
    print(f"period  {start.date()} -> today\n")

    print("FUNDING (your money, not performance)")
    for d in funding:
        ts = datetime.fromtimestamp(d.time, timezone.utc).strftime("%Y-%m-%d %H:%M")
        kind = "deposit " if d.profit > 0 else "withdraw"
        print(f"  {ts}  {kind} {d.profit:>+12.2f} {cur}  = R{zar(d.profit):>+9.2f}")
    print(f"  {'total deposited':<28}{deposits:>+12.2f} {cur}  = R{zar(deposits):>+9.2f}")
    if withdrawals:
        print(f"  {'total withdrawn':<28}{-withdrawals:>+12.2f} {cur}  = R{zar(-withdrawals):>+9.2f}")

    print("\nCLOSED TRADES (this is the strategy)")
    if rows:
        print(f"  {'when':<12}{'ticket':>11}{'symbol':>9}{'dir':>6}{'vol':>6}"
              f"{'entry':>11}{'exit':>11}{'P&L':>9}{'R':>7}  note")
        for when, pid, sym, d_, vol, en, ex, pnl, r_txt, note in rows:
            print(f"  {when:<12}{pid:>11}{sym:>9}{d_:>6}{vol:>6.2f}"
                  f"{en:>11.3f}{ex:>11.3f}{pnl:>+9.2f}{r_txt:>7}  {note[:22]}")
    else:
        print("  (none yet)")

    n = len(rows)
    wins = sum(1 for r in rows if r[7] > 0)
    print(f"\n  trades {n}   wins {wins}   losses {n - wins}"
          + (f"   win rate {100*wins/n:.1f}%" if n else ""))
    if rs:
        avg = sum(rs) / len(rs)
        print(f"  avg R {avg:+.3f} over {len(rs)} trades with a known stop")
        if len(rs) < 30:
            print(f"  -- {len(rs)} trades says nothing. Per-trade noise is ~0.9R, so "
                  f"even a real\n     edge of +0.04R needs ~2,000 trades to separate "
                  f"from zero.")

    print("\nRECONCILIATION")
    print(f"  deposits            {deposits:>+12.2f} {cur}")
    if withdrawals:
        print(f"  withdrawals         {-withdrawals:>+12.2f} {cur}")
    print(f"  trading P&L         {trading_pnl:>+12.2f} {cur}  = R{zar(trading_pnl):>+9.2f}")
    computed = deposits - withdrawals + trading_pnl
    print(f"  {'-'*44}")
    print(f"  computed balance    {computed:>+12.2f} {cur}")
    print(f"  actual balance      {acct.balance:>+12.2f} {cur}"
          + ("   OK" if abs(computed - acct.balance) < 0.01
             else f"   MISMATCH {acct.balance - computed:+.2f} (open trades or "
                  f"deals before --since)"))

    growth = acct.balance - deposits + withdrawals
    print(f"\nTHE ONLY NUMBER THAT MEASURES THE STRATEGY")
    print(f"  balance - deposits  {growth:>+12.2f} {cur}  = R{zar(growth):>+9.2f}")
    if deposits:
        print(f"  return on deposits  {100*growth/deposits:>+11.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
