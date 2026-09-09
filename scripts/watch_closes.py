"""Turn broker-side closes into log lines, so a log watcher can see them.

    python scripts/watch_closes.py            # follow, polling every 30s
    python scripts/watch_closes.py --once     # backfill and exit

The bot logs ``order_placed`` when it OPENS a trade. It never logs the close,
and cannot: a take-profit or stop-loss fires inside the broker, and the bot is
not told. Anything tailing the decision log therefore sees every entry and no
exits — which is exactly half the story, and the wrong half, because the exit is
where the money is decided.

This polls the deal history, and appends one ``event=trade_closed`` line per
newly-closed position to ``output/closes.log`` in the same key=value shape the
bot uses. A tail on that file now reports both ends of a trade.

R multiple needs the stop that defined the risk, which the deal history does not
carry, so stops are recovered from the bot's own ``order_placed`` lines and
matched by ticket — the same reconstruction ``account_report.py`` performs. A
trade with no recoverable stop is reported with ``r=?`` rather than a guess.
"""

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

DEAL_TYPE_BUY, DEAL_TYPE_SELL = 0, 1
CLOSES_LOG = ROOT / "output" / "closes.log"


def resolve_mt5(host, port):
    from trading_bot.broker.base import BrokerUnavailableError
    from trading_bot.broker.mt5 import _load_mt5, _load_silicon_bridge

    try:
        mt5 = _load_mt5()
    except BrokerUnavailableError:
        mt5 = _load_silicon_bridge(host, port)
    if not mt5.initialize():
        raise BrokerUnavailableError(f"initialize() failed: {mt5.last_error()}")
    return mt5


def resolve_mt5_for_cfg(cfg):
    """Attach to the terminal the CONFIG names, not whichever initialize()
    happens to find first — a multi-terminal box otherwise reports every
    bot's closes against one install (see health_check._init_terminal). Falls
    back to a bare initialize() when the config leaves terminal_path unset."""
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


def seen_tickets() -> set[int]:
    """Positions already reported, so a restart never double-announces."""
    out = set()
    if CLOSES_LOG.exists():
        for line in CLOSES_LOG.read_text(errors="replace").splitlines():
            for token in line.split():
                if token.startswith("ticket="):
                    try:
                        out.add(int(token.split("=", 1)[1]))
                    except ValueError:
                        pass
    return out


def scan(mt5, days: int, already: set[int]) -> list[str]:
    from account_report import stops_from_logs

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    deals = mt5.history_deals_get(now - timedelta(days=days), now + timedelta(days=1)) or []
    by_pos: dict[int, list] = {}
    for d in deals:
        if d.type in (DEAL_TYPE_BUY, DEAL_TYPE_SELL) and d.position_id:
            by_pos.setdefault(d.position_id, []).append(d)

    stops = stops_from_logs(ROOT / "output")
    lines = []
    for pos_id, ds in sorted(by_pos.items(), key=lambda kv: kv[1][-1].time):
        if len(ds) < 2 or pos_id in already:
            continue  # still open, or already announced
        ds.sort(key=lambda d: d.time)
        entry, exit_ = ds[0], ds[-1]
        pnl = sum(x.profit + x.swap + x.commission for x in ds)
        info = stops.get(pos_id)
        if info and (entry.price - info["sl"]) != 0:
            r = f"{(exit_.price - entry.price) / (entry.price - info['sl']):+.2f}"
        else:
            r = "?"
        # "tp"/"sl" appear in the broker's own comment on an automatic close;
        # anything else was closed by hand or by the broker for another reason.
        note = (exit_.comment or "").lower()
        how = "tp" if "tp" in note else "sl" if "sl" in note else "other"
        ts = datetime.fromtimestamp(exit_.time, timezone.utc)
        lines.append(
            f"{ts:%Y-%m-%d %H:%M:%S} level=INFO event=trade_closed "
            f"ticket={pos_id} symbol={entry.symbol} how={how} "
            f"entry={entry.price} exit={exit_.price} volume={entry.volume} "
            f"profit={pnl:+.2f} r={r}"
        )
        already.add(pos_id)
    return lines


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--interval", type=float, default=30.0)
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=8001)
    p.add_argument("--config", default="",
                   help="config TOML whose [live] terminal_path this watcher pins "
                        "(multi-terminal boxes otherwise attach to the wrong install)")
    p.add_argument("--once", action="store_true")
    a = p.parse_args(argv)

    from trading_bot.broker.base import BrokerUnavailableError

    if a.config:
        from trading_bot.config import load_config
        cfg = load_config(a.config)
        make_mt5 = lambda: resolve_mt5_for_cfg(cfg)
    else:
        make_mt5 = lambda: resolve_mt5(a.host, a.port)

    CLOSES_LOG.parent.mkdir(parents=True, exist_ok=True)
    already = seen_tickets()
    # Everything already closed is marked seen WITHOUT emitting, so starting the
    # watcher does not replay the whole history as fresh notifications.
    if not CLOSES_LOG.exists():
        try:
            mt5 = make_mt5()
            for line in scan(mt5, a.days, already):
                CLOSES_LOG.open("a").write(line + "  [backfill]\n")
        except BrokerUnavailableError as exc:
            print(f"cannot reach the terminal: {exc}", file=sys.stderr)
            return 2
        print(f"backfilled {len(already)} closed positions into {CLOSES_LOG}")
        if a.once:
            return 0

    while True:
        try:
            mt5 = make_mt5()
            for line in scan(mt5, a.days, already):
                with CLOSES_LOG.open("a") as fh:
                    fh.write(line + "\n")
                print(line, flush=True)
        except Exception as exc:  # a watcher must never die on a transient error
            print(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} "
                  f"level=WARNING event=watch_closes_error error={exc}", flush=True)
        if a.once:
            return 0
        time.sleep(a.interval)


if __name__ == "__main__":
    raise SystemExit(main())
