"""Close an open position by ticket, on Windows or through the macOS bridge.

One-off operational tool, deliberately NOT wired into the engine: the live
engine has no close path at all (it only places), and this keeps it that way.
Closing is a human decision, so this refuses to guess -- you name the ticket.

    python scripts/close_position.py --ticket 433789109 --dry-run
    python scripts/close_position.py --ticket 433789109 --confirm

A long is closed by an opposing SELL at the bid with the position's own volume
and position id, which is what MT5 requires; there is no "close" order type.

Transport resolution mirrors the adapter's ``bridge`` setting, so this runs
unchanged on both platforms: ``auto`` (default) prefers the native Windows
MetaTrader5 package and falls back to the RPC bridge, which is the only route
on macOS/Linux. Importing ``siliconmetatrader5`` unconditionally would make
this file unusable on the very machine MT5 is native to.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def resolve_mt5(bridge: str, host: str, port: int):
    """Return the MT5 call surface, same precedence as ``MT5Broker._mt5()``."""
    from trading_bot.broker.base import BrokerUnavailableError
    from trading_bot.broker.mt5 import _load_mt5, _load_silicon_bridge

    if bridge == "native":
        return _load_mt5(), "native"
    if bridge == "silicon":
        return _load_silicon_bridge(host, port), f"bridge {host}:{port}"
    try:
        return _load_mt5(), "native"
    except BrokerUnavailableError:
        return _load_silicon_bridge(host, port), f"bridge {host}:{port}"


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--ticket", type=int, required=True)
    p.add_argument("--bridge", choices=["auto", "native", "silicon"], default="auto")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=8001)
    p.add_argument("--deviation", type=int, default=20)
    p.add_argument("--dry-run", action="store_true", help="show the request, send nothing")
    p.add_argument("--confirm", action="store_true", help="actually send the close")
    a = p.parse_args(argv)
    if not a.dry_run and not a.confirm:
        p.error("pass --confirm to send, or --dry-run to preview")

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    from trading_bot.broker.base import BrokerUnavailableError

    try:
        mt5, how = resolve_mt5(a.bridge, a.host, a.port)
    except BrokerUnavailableError as exc:
        print(f"{stamp} FAIL no MT5 transport: {exc}")
        return 2
    print(f"{stamp} transport: {how}")

    if not mt5.initialize():
        print(f"{stamp} FAIL initialize: {mt5.last_error()}")
        return 2

    positions = [x for x in (mt5.positions_get() or []) if x.ticket == a.ticket]
    if not positions:
        print(f"{stamp} ticket {a.ticket} is not open -- nothing to close "
              f"(it likely hit SL or TP already)")
        return 0
    pos = positions[0]

    tick = mt5.symbol_info_tick(pos.symbol)
    # A long closes by SELLING at the bid; a short closes by BUYING at the ask.
    is_long = pos.type == mt5.POSITION_TYPE_BUY
    price = tick.bid if is_long else tick.ask
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "position": pos.ticket,
        "symbol": pos.symbol,
        "volume": pos.volume,
        "type": mt5.ORDER_TYPE_SELL if is_long else mt5.ORDER_TYPE_BUY,
        "price": price,
        "deviation": a.deviation,
        "magic": pos.magic,
        "comment": "manual-close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    print(f"{stamp} position {pos.ticket} {pos.symbol} vol={pos.volume} "
          f"open={pos.price_open} cur={pos.price_current} profit={pos.profit:.2f}")
    print(f"{stamp} close request: {'SELL' if is_long else 'BUY'} "
          f"{pos.volume} {pos.symbol} @ {price}")
    if a.dry_run:
        print(f"{stamp} DRY RUN -- nothing sent")
        return 0

    res = mt5.order_send(req)
    if res is None:
        print(f"{stamp} FAIL order_send returned None: {mt5.last_error()}")
        return 3
    ok = res.retcode in (10009, 10008)
    print(f"{stamp} {'CLOSED' if ok else 'REJECTED'} retcode={res.retcode} "
          f"deal={getattr(res, 'deal', '?')} price={getattr(res, 'price', '?')} "
          f"comment={getattr(res, 'comment', '')}")
    if ok:
        a2 = mt5.account_info()
        print(f"{stamp} account balance={a2.balance:.2f} equity={a2.equity:.2f} {a2.currency}")
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
