"""One command that answers the three monitoring questions in one glance.

    python scripts/monitor_trade.py                # live BTC bot (default)
    python scripts/monitor_trade.py --tag cent     # the cent gold bot
    python scripts/monitor_trade.py --quiet        # only WARN/FAIL lines

Exit codes:  0 healthy   1 warnings   2 problems

READ-ONLY observability. This script reads pidfiles, logs, and broker state
and NEVER places, closes, or modifies an order. It cannot: there is no order
request anywhere in it. Closing a position stays the deliberate human action
in close_position.py.

It answers the three questions in one read:

  1. is the bot alive and still polling?   (pidfiles, log staleness, terminal)
  2. is there an open position?            (entry/SL/TP/current/floating/current R)
  3. what is the P&L?                      (closes.log realised + balance/equity)

Staleness logic and severity follow health_check.py, so this is safe to run
from the same cron job: a bot that is alive but no longer polling is the
dangerous state, and it is a FAIL, not a warning.
"""

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

# Reuse the established conventions rather than reinventing them:
# BOTS maps --tag to its config, Report carries the OK/WARN/FAIL severity and
# quiet filtering, pid/liveness/log-staleness helpers are shared verbatim.
from health_check import (  # noqa: E402
    BOTS,
    OK,
    WARN,
    FAIL,
    TF_MINUTES,
    Report,
    pid_alive,
    read_pidfile,
    last_log_time,
)

# closes.log lines carry key=value tokens after a leading timestamp pair;
# r=? means the stop could not be recovered from the decision logs, so the
# R multiple is unknown and must not be summed as zero.
_CLOSE_TOKEN = re.compile(r"(\w+)=(\S+)")
_R_UNKNOWN = "?"


def parse_close_line(line: str) -> dict | None:
    """Extract {ts, how, profit, r} from one closes.log line, or None."""
    if "event=trade_closed" not in line:
        return None
    toks = line.split()
    if len(toks) < 2:
        return None
    fields = {k: v for k, v in (_CLOSE_TOKEN.findall(line))}
    if "symbol" not in fields or "how" not in fields or "profit" not in fields:
        return None
    try:
        return {
            "ts": f"{toks[0]} {toks[1]}",
            "symbol": fields["symbol"],
            "how": fields["how"],
            "profit": float(fields["profit"]),
            "r": fields.get("r", _R_UNKNOWN),
        }
    except ValueError:
        return None


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1].strip())
    p.add_argument("--tag", choices=sorted(BOTS), default="btc",
                   help="which bot to monitor (default: btc)")
    p.add_argument("--quiet", action="store_true",
                   help="print only WARN/FAIL lines")
    a = p.parse_args(argv)

    from trading_bot.broker.base import BrokerUnavailableError
    from trading_bot.config import load_config, live_symbol
    from health_check import _init_terminal

    cfg = load_config(ROOT / BOTS[a.tag])
    sym = live_symbol(cfg)
    magic = cfg.live.magic_number
    bar_min = TF_MINUTES.get(cfg.data.timeframe, 5)

    r = Report(a.quiet)
    if not a.quiet:
        now_utc = datetime.now(timezone.utc)
        print(f"monitor {a.tag}  {now_utc:%Y-%m-%d %H:%M:%S}Z  "
              f"{sym}  magic {magic}")

    # ---- BOT: processes + poll loop ---------------------------------------
    r.section("BOT")
    sup = read_pidfile(ROOT / f"output/supervise_{a.tag}.pid")
    bot = read_pidfile(ROOT / f"output/live_{a.tag}.pid")
    sup_up = sup is not None and pid_alive(sup)
    bot_up = bot is not None and pid_alive(bot)

    if not sup_up and not bot_up:
        # health_check treats a not-running tag as fine because it monitors
        # many; this monitor exists to watch ONE bot, so its absence matters.
        r.add(WARN, f"{a.tag}: not running", "(no supervisor, no bot)")
    else:
        # No supervise pidfile is NORMAL on Windows: supervise_live.bat
        # deliberately never writes one (batch cannot learn a child pid
        # reliably), and the scheduled task is the source of truth there. Only
        # a pidfile pointing at a dead process is a real failure.
        if sup is None:
            r.add(OK, f"{a.tag}: supervisor",
                  "no pidfile (normal on Windows - the scheduled task is the supervisor)")
        else:
            r.add(OK if sup_up else FAIL, f"{a.tag}: supervisor",
                  f"pid {sup}" if sup_up else "PIDFILE PRESENT BUT PROCESS GONE")
        # A bot down while its supervisor is up is normal for a few seconds
        # (backoff between restarts), so it is a warning, not a failure.
        r.add(OK if bot_up else WARN, f"{a.tag}: bot",
              f"pid {bot}" if bot_up else "not running (supervisor may be backing off)")

        # A live process with a stale log is the dangerous state: nothing has
        # died, so nothing restarts it, and it silently stops noticing the
        # market. Two bar intervals of slack absorbs a slow poll.
        last = last_log_time(ROOT / f"output/live_{a.tag}.log")
        if last is None:
            r.add(WARN, f"{a.tag}: last decision", "no timestamped lines yet")
        else:
            age = (datetime.now() - last).total_seconds() / 60
            level = OK if age < bar_min * 2 else FAIL
            r.add(level, f"{a.tag}: last decision",
                  f"{age:.1f} min ago (bar interval {bar_min} min)")

    # ---- broker transport ------------------------------------------------
    # Attach per-config via health_check._init_terminal (native first, bridge
    # fallback, terminal_path from the config) — a bare initialize() on a
    # multi-terminal machine attaches to whichever install it finds first, so
    # this bot's account/positions would be read from the WRONG terminal.
    try:
        mt5 = _init_terminal(cfg)
    except BrokerUnavailableError as exc:
        r.add(FAIL, "broker unreachable", str(exc))
        print("\n".join(r.lines))
        print("\nPROBLEMS FOUND")
        return 2

    ti = mt5.terminal_info()
    r.add(OK if ti.connected else FAIL, "terminal connected")
    r.add(OK if ti.trade_allowed else FAIL, "algorithmic trading allowed",
          "" if ti.trade_allowed
          else "orders WILL be rejected - re-enable in Tools > Options")
    acct = mt5.account_info()

    # ---- OPEN POSITION: this bot's only, filtered by magic -----------------
    r.section("OPEN POSITION")
    positions = [x for x in (mt5.positions_get() or []) if x.magic == magic]
    if not positions:
        r.add(OK, "no open position")
    for pos in positions:
        side = "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL"
        if not pos.sl:
            # The one failure that can take the account: a stop is the only
            # protection when the bot is down, and the bot is never told a
            # position closed. Same severity health_check gives it.
            r.add(FAIL, f"position {pos.ticket} ({pos.symbol})",
                  "HAS NO STOP LOSS - unbounded downside")
            continue
        tick = mt5.symbol_info_tick(pos.symbol)
        if tick is None:
            r.add(FAIL, f"position {pos.ticket} ({pos.symbol})",
                  "no tick for symbol - cannot price the position")
            continue
        # Current R evaluated at the live price instead of the exit:
        # a long marks against the bid, a short against the ask.
        ref = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask
        risk = abs(pos.price_open - pos.sl)
        cur_r = ((ref - pos.price_open) / risk
                 if pos.type == mt5.POSITION_TYPE_BUY
                 else (pos.price_open - ref) / risk)
        to_sl = abs(pos.price_open - pos.sl) / pos.price_open * 100
        to_tp = abs(pos.tp - pos.price_open) / pos.price_open * 100 if pos.tp else 0.0
        open_secs = int(datetime.now(timezone.utc).timestamp() - pos.time)
        open_hhmm = f"{open_secs // 3600}:{open_secs % 3600 // 60:02d}"
        pct = pos.profit / acct.balance * 100 if acct.balance else 0.0
        r.add(OK, f"position {pos.ticket} {side} {pos.volume} {pos.symbol}",
              f"entry {pos.price_open} sl {pos.sl} tp {pos.tp} | "
              f"bid {tick.bid} ask {tick.ask} | floating {pos.profit:+.2f} "
              f"{acct.currency} ({pct:+.2f}%) | R {cur_r:+.2f} | "
              f"SL {to_sl:.2f}% TP {to_tp:.2f}% | open {open_hhmm}")

    # ---- ACCOUNT -----------------------------------------------------------
    r.section("ACCOUNT")
    r.add(OK, "account",
          f"{acct.login} @ {acct.server}  balance {acct.balance:.2f} "
          f"equity {acct.equity:.2f} floating {acct.profit:+.2f} "
          f"{acct.currency}")

    # ---- RECENT CLOSES: realised P&L for THIS symbol ------------------------
    r.section("RECENT CLOSES")
    closes_path = ROOT / "output" / "closes.log"
    if not closes_path.exists():
        r.add(OK, "closes.log", "not present yet - no closed trades recorded")
    else:
        rows = []
        for line in closes_path.read_text(errors="replace").splitlines():
            parsed = parse_close_line(line)
            # Exact symbol token match: symbol=BTCUSDc is this bot's, anything
            # else (XAUUSDc, BTCUSDc5) belongs to another instrument.
            if parsed and parsed["symbol"] == sym:
                rows.append(parsed)
        profit_sum = sum(row["profit"] for row in rows)
        known = [row for row in rows if row["r"] != _R_UNKNOWN]
        r_sum = sum(float(row["r"]) for row in known)
        skipped = len(rows) - len(known)
        if rows:
            for row in rows[-5:]:
                rr = f"{float(row['r']):+.2f}" if row["r"] != _R_UNKNOWN else "r=?"
                r.add(OK, f"close {row['ts']}",
                      f"how={row['how']} profit={row['profit']:+.2f} {rr}R")
            note = "" if skipped == 0 else f"  ({skipped} skipped, r=?)"
            r.add(OK, "totals",
                  f"{len(rows)} closed  profit {profit_sum:+.2f} "
                  f"{acct.currency}  sum R {r_sum:+.2f}{note}")
        else:
            r.add(OK, "no closes yet", f"for {sym}")

    print("\n".join(r.lines))
    if not a.quiet:
        verdict = {OK: "HEALTHY", WARN: "WARNINGS", FAIL: "PROBLEMS FOUND"}[r.worst]
        print(f"\n{verdict}")
    try:
        mt5.shutdown()
    except Exception:  # noqa: BLE001 - a dead terminal may not answer
        pass
    return {OK: 0, WARN: 1, FAIL: 2}[r.worst]


if __name__ == "__main__":
    raise SystemExit(main())
