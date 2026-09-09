"""One command that answers "is it actually OK?" — not "is it still printing".

    python scripts/health_check.py
    python scripts/health_check.py --quiet     # only problems
    python scripts/health_check.py --zar 16.0024

Exit codes:  0 healthy   1 warnings   2 problems

Tailing a log tells you a process is alive. It does not tell you the poll loop
has stalled, that a position is sitting without a stop, that the slot budget has
been exceeded, or that the account no longer reconciles. Those are the failures
that cost money, and every one of them is invisible in a log tail.

The check that matters most is STALE_LOG. A crashed bot is safe — the supervisor
restarts it, and the broker still holds every stop and target. A bot that is
alive but no longer polling is worse: nothing restarts it, because nothing has
died, and it will sit there indefinitely not noticing setups or the market.
"""

import argparse
import glob
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

OK, WARN, FAIL = "ok", "WARN", "FAIL"
_ICON = {OK: "  [ok ]", WARN: "  [WARN]", FAIL: "  [FAIL]"}

TF_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "H1": 60}
# tag -> config, by the convention the launchers already use.
BOTS = {"btc": "config/config-btc.toml", "cent": "config/config-cent.toml"}


class Report:
    def __init__(self, quiet: bool):
        self.worst = OK
        self.quiet = quiet
        self.lines: list[str] = []

    def add(self, level, label, detail=""):
        if level == FAIL or (level == WARN and self.worst != FAIL):
            self.worst = level
        if self.quiet and level == OK:
            return
        self.lines.append(f"{_ICON[level]} {label}" + (f"  {detail}" if detail else ""))

    def section(self, title):
        if not self.quiet:
            self.lines.append(f"\n{title}")


def pid_alive(pid: int) -> bool:
    if pid is None:
        return False
    if os.name == "nt":
        # Windows has no `ps`. tasklist exits 1 when the filter matches nothing.
        try:
            r = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True,
            )
        except OSError:
            return False
        return r.returncode == 0
    return subprocess.run(["ps", "-p", str(pid)], capture_output=True).returncode == 0


def read_pidfile(path: Path):
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def last_log_time(path: Path):
    """Timestamp of the final log line, or None. Logs are local time."""
    try:
        lines = path.read_text(errors="replace").strip().splitlines()
    except OSError:
        return None
    for line in reversed(lines[-50:]):
        m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
        if m:
            return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
    return None


def _init_terminal(cfg):
    """Attach to the terminal the CONFIG names, not whichever initialize()
    happens to find first (a multi-terminal box otherwise checks every bot's
    symbol against one install and false-FAILs the rest). Falls back to a bare
    initialize() when the config leaves terminal_path unset (macOS, one
    container per port)."""
    from trading_bot.broker.base import BrokerUnavailableError
    from trading_bot.broker.mt5 import _load_mt5, _load_silicon_bridge

    bridge = getattr(cfg.live, "bridge", "auto")
    path = getattr(cfg.live, "terminal_path", "") or ""
    try:
        mt5 = _load_mt5()
    except BrokerUnavailableError:
        mt5 = _load_silicon_bridge("localhost", getattr(cfg.live, "bridge_port", 8001))
    kwargs = {"path": path, "portable": True} if path else {}
    if not mt5.initialize(**kwargs):
        raise BrokerUnavailableError(f"initialize() failed: {mt5.last_error()}")
    return mt5


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--quiet", action="store_true", help="print only WARN/FAIL")
    p.add_argument("--zar", type=float, default=16.0024)
    a = p.parse_args(argv)

    from trading_bot.broker.base import BrokerUnavailableError
    from trading_bot.broker.mt5 import _load_mt5, _load_silicon_bridge
    from trading_bot.config import live_symbol, load_config

    r = Report(a.quiet)
    now_local = datetime.now()
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    print(f"health check  {now_utc:%Y-%m-%d %H:%M:%S}Z")

    # ---- processes ---------------------------------------------------------
    r.section("PROCESSES")
    running_tags = []
    for tag, cfg_path in BOTS.items():
        sup = read_pidfile(ROOT / f"output/supervise_{tag}.pid")
        bot = read_pidfile(ROOT / f"output/live_{tag}.pid")
        sup_up = sup is not None and pid_alive(sup)
        bot_up = bot is not None and pid_alive(bot)
        if not sup_up and not bot_up:
            r.add(OK, f"{tag}: not running", "(no supervisor, no bot)")
            continue
        running_tags.append((tag, cfg_path))
        # No supervise pidfile is NORMAL on Windows: supervise_live.bat
        # deliberately never writes one (batch cannot learn a child pid
        # reliably) and the scheduled task is the source of truth there. Only a
        # pidfile pointing at a dead process is a real failure. On macOS the
        # bash supervisor writes one, so its absence is a failure as before.
        if sup is None and os.name == "nt":
            r.add(OK, f"{tag}: supervisor",
                  "no pidfile (normal on Windows - the scheduled task is the supervisor)")
        else:
            r.add(OK if sup_up else FAIL, f"{tag}: supervisor",
                  f"pid {sup}" if sup_up else "PIDFILE PRESENT BUT PROCESS GONE")
        # A bot down while its supervisor is up is normal for a few seconds
        # (backoff between restarts), so it is a warning, not a failure.
        r.add(OK if bot_up else WARN, f"{tag}: bot",
              f"pid {bot}" if bot_up else "not running (supervisor may be backing off)")

    # The close watcher is observability, not trading: if it dies you lose
    # notifications, not money. WARN, never FAIL. It exists because a TP or SL
    # fires broker-side and the bot is never told, so the decision log shows
    # every entry and no exits.
    cw = read_pidfile(ROOT / "output/watch_closes.pid")
    cw_up = cw is not None and pid_alive(cw)
    r.add(OK if cw_up else WARN, "close watcher",
          f"pid {cw}" if cw_up else "not running - exits will go unreported")

    caff = None
    if os.name != "nt":
        # pgrep is POSIX-only; on Windows the supervisor disables sleep itself
        # (powercfg /change standby-timeout-ac 0), so this check is a no-op
        # there and must not even attempt the call.
        caff = subprocess.run(["pgrep", "-f", "caffeinate -dimsu"], capture_output=True)
    if os.name == "nt":
        # No caffeinate on Windows: the supervisor disables sleep itself
        # (powercfg /change standby-timeout-ac 0), so this check is a no-op.
        r.add(OK, "machine kept awake", "supervisor disables sleep on AC power")
    else:
        r.add(OK if caff.returncode == 0 else (WARN if running_tags else OK),
              "caffeinate holding the machine awake",
              "" if caff.returncode == 0 else "NOT RUNNING - the Mac may sleep and stop the bots")

    # ---- the poll loop -----------------------------------------------------
    # A live process with a stale log is the dangerous state: nothing has died,
    # so nothing restarts it, and it silently stops noticing the market.
    r.section("POLL LOOP")
    for tag, cfg_path in running_tags:
        cfg = load_config(cfg_path)
        tf = TF_MINUTES.get(cfg.data.timeframe, 5)
        last = last_log_time(ROOT / f"output/live_{tag}.log")
        if last is None:
            r.add(WARN, f"{tag}: decision log", "no timestamped lines yet")
            continue
        age = (now_local - last).total_seconds() / 60
        # Two bar intervals of slack absorbs a slow poll; beyond that the loop
        # has genuinely stopped advancing.
        level = OK if age < tf * 2 else FAIL
        r.add(level, f"{tag}: last decision", f"{age:.1f} min ago (bar interval {tf} min)")

    # ---- broker ------------------------------------------------------------
    # Each config points at ITS OWN terminal install (one bot per account). A
    # bare initialize() attaches to whichever install it finds first, so on a
    # multi-terminal machine checking every tag's symbol against that one is a
    # guaranteed false FAIL for the others. Initialize per-tag with the
    # configured terminal_path; fall back to a bare initialize when a config
    # leaves it unset (macOS, single terminal).
    r.section("BROKER AND FEED")
    if not running_tags:
        r.add(FAIL, "broker", "no running bot to check against")
        print("\n".join(r.lines))
        print("\nPROBLEMS FOUND")
        return 2
    try:
        first_cfg = load_config(running_tags[0][1])
        mt5 = _init_terminal(first_cfg)
        ti = mt5.terminal_info()
        r.add(OK if ti.connected else FAIL, "terminal connected")
        r.add(OK if ti.trade_allowed else FAIL, "algorithmic trading allowed",
              "" if ti.trade_allowed else "orders WILL be rejected - re-enable in Tools > Options")
    except BrokerUnavailableError as exc:
        r.add(FAIL, "broker unreachable", str(exc))
        print("\n".join(r.lines))
        print("\nPROBLEMS FOUND")
        return 2

    acct = mt5.account_info()

    for tag, cfg_path in running_tags:
        cfg = load_config(cfg_path)
        try:
            tag_mt5 = _init_terminal(cfg)
        except BrokerUnavailableError as exc:
            r.add(FAIL, f"{tag}: terminal", str(exc))
            continue
        sym = live_symbol(cfg)
        tag_mt5.symbol_select(sym, True)
        tf_const = {"M1": tag_mt5.TIMEFRAME_M1, "M5": tag_mt5.TIMEFRAME_M5}[cfg.data.timeframe]
        rates = tag_mt5.copy_rates_from_pos(sym, tf_const, 1, 1)
        if rates is None or len(rates) == 0:
            r.add(FAIL, f"{tag}: feed", "no bars returned")
            continue
        bar_t = datetime.fromtimestamp(int(rates[-1][0]), timezone.utc).replace(tzinfo=None)
        age = (now_utc - bar_t).total_seconds() / 60
        tf = TF_MINUTES.get(cfg.data.timeframe, 5)
        # Gold is shut at weekends, so a stale feed there is expected, not broken.
        level = OK if age < tf * 3 else WARN
        r.add(level, f"{tag}: feed freshness",
              f"last bar {age:.1f} min old" + ("" if level == OK else " (market closed?)"))
        if tag_mt5 is not mt5:
            tag_mt5.shutdown()

    # ---- positions: the money questions ------------------------------------
    # Account-wide checks run PER TAG: each bot owns its own terminal and its
    # own account (one bot per account is the deployment model), so summing
    # positions and balances across terminals mixes two accounts into nonsense.
    # The original single-account form is preserved when only one tag runs.
    r.section("POSITIONS AND RISK")
    per_account = {}
    for tag, cfg_path in running_tags:
        cfg = load_config(cfg_path)
        try:
            tag_mt5 = _init_terminal(cfg)
        except BrokerUnavailableError as exc:
            r.add(FAIL, f"{tag}: terminal", str(exc))
            continue
        acct = tag_mt5.account_info()
        positions = tag_mt5.positions_get() or []
        by_magic: dict[int, list] = {}
        for pos in positions:
            by_magic.setdefault(pos.magic, []).append(pos)

        # Slot budget, per bot. Exceeding it means a guard failed.
        held = len(by_magic.get(cfg.live.magic_number, []))
        cap = cfg.risk.max_concurrent
        r.add(OK if held <= cap else FAIL, f"{tag}: slot budget",
              f"{held}/{cap} used" + ("" if held <= cap else "  OVER BUDGET - guard failed"))

        total_risk = 0.0
        for pos in positions:
            si = tag_mt5.symbol_info(pos.symbol)
            # A position with no stop is the one failure that can take the
            # account. Checked on the account's OWN terminal.
            if not pos.sl:
                r.add(FAIL, f"{tag}: position {pos.ticket} ({pos.symbol})",
                      "HAS NO STOP LOSS - unbounded downside")
                continue
            risk = (abs(pos.price_open - pos.sl) / si.trade_tick_size
                    * si.trade_tick_value * pos.volume)
            total_risk += risk
            reward = abs(pos.tp - pos.price_open) if pos.tp else 0.0
            rr = reward / abs(pos.price_open - pos.sl) if pos.tp else 0.0
            r.add(OK if pos.tp else WARN, f"{tag}: position {pos.ticket} ({pos.symbol})",
                  f"risk {risk:.2f} {acct.currency} ({risk/acct.balance*100:.2f}%) "
                  f"RR {rr:.2f}R" + ("" if pos.tp else "  NO TAKE PROFIT"))

        # Exposure is the SUM across THIS account's configs only; each bot
        # sizes off its own balance, so summing across accounts is wrong.
        policy = cfg.risk.max_loss_pct_per_trade * cfg.risk.max_concurrent
        pct = total_risk / acct.balance * 100 if acct.balance else 0.0
        r.add(OK if pct <= policy + 0.01 else FAIL, f"{tag}: risk if every stop hits",
              f"{total_risk:.2f} {acct.currency} = {pct:.2f}% (policy {policy:.2f}%)")

        # ---- reconciliation --------------------------------------------------
        deals = tag_mt5.history_deals_get(
            now_utc - timedelta(days=400), now_utc + timedelta(days=1)
        ) or []
        deposits = sum(d.profit for d in deals if d.type == 2)
        realised = sum(d.profit + d.swap + d.commission
                       for d in deals if d.type in (0, 1) and d.position_id)
        computed = deposits + realised
        matches = abs(computed - acct.balance) < 0.01
        r.add(OK if matches else WARN, f"{tag}: balance reconciles",
              f"deposits {deposits:.2f} + trading {realised:.2f} = {computed:.2f} "
              f"vs actual {acct.balance:.2f}")
        zar = realised / 100 * a.zar if acct.currency == "USC" else realised * a.zar
        r.add(OK, f"{tag}: strategy P&L (balance - deposits)",
              f"{realised:+.2f} {acct.currency} = R{zar:+.2f}")
        r.add(OK, f"{tag}: equity vs balance",
              f"{acct.equity:.2f} vs {acct.balance:.2f} (floating {acct.profit:+.2f})")
        per_account[tag] = acct
        if tag_mt5 is not mt5:
            tag_mt5.shutdown()

    # ---- supervisor stability ----------------------------------------------
    r.section("SUPERVISOR HISTORY")
    for tag, _ in running_tags:
        log = ROOT / f"output/supervise_{tag}.log"
        if not log.exists():
            continue
        text = log.read_text(errors="replace")
        died = text.count("bot DIED")
        gave_up = "GIVING UP" in text
        r.add(FAIL if gave_up else (WARN if died else OK), f"{tag}: crash history",
              f"{died} unexpected death(s)" + (", GAVE UP - not restarting" if gave_up else ""))

    print("\n".join(r.lines))
    verdict = {OK: "HEALTHY", WARN: "WARNINGS", FAIL: "PROBLEMS FOUND"}[r.worst]
    print(f"\n{verdict}")
    return {OK: 0, WARN: 1, FAIL: 2}[r.worst]


if __name__ == "__main__":
    raise SystemExit(main())
