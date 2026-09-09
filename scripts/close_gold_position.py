"""Close every open position owned by one bot's magic number.

    python scripts/close_gold_position.py --config config/config-cent.toml --confirm
    python scripts/close_gold_position.py --config config/config-cent.toml --dry-run

Runs before the weekend so no gold position is carried through the market close,
where a gap can jump straight past SL/TP. Reads the terminal to attach to and the
magic number from the config, so it always closes the RIGHT bot's positions. This
is an operational tool like close_position.py (a human decision), not part of the
engine -- the engine has no close path on purpose.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from trading_bot.broker.mt5 import _load_mt5
from trading_bot.config import load_config


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config/config-cent.toml")
    p.add_argument("--dry-run", action="store_true", help="show the requests, send nothing")
    p.add_argument("--confirm", action="store_true", help="actually send the closes")
    p.add_argument("--deviation", type=int, default=20)
    a = p.parse_args(argv)
    if not a.dry_run and not a.confirm:
        p.error("pass --confirm to send, or --dry-run to preview")

    cfg = load_config(a.config)
    magic = cfg.live.magic_number
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

    mt5 = _load_mt5()
    if cfg.live.terminal_path:
        ok = mt5.initialize(path=cfg.live.terminal_path, portable=True)
    else:
        ok = mt5.initialize()
    if not ok:
        print(f"{stamp} FAIL initialize: {mt5.last_error()}")
        return 2

    positions = [x for x in (mt5.positions_get() or []) if x.magic == magic]
    if not positions:
        print(f"{stamp} no open positions for magic {magic} -- nothing to close")
        mt5.shutdown()
        return 0

    closed = 0
    for pos in positions:
        tick = mt5.symbol_info_tick(pos.symbol)
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
            "magic": magic,
            "comment": "weekend-close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        print(f"{stamp} position {pos.ticket} {pos.symbol} vol={pos.volume} "
              f"open={pos.price_open} cur={pos.price_current} profit={pos.profit:.2f}")
        print(f"{stamp} close request: {'SELL' if is_long else 'BUY'} "
              f"{pos.volume} {pos.symbol} @ {price}")
        if a.dry_run:
            continue
        res = mt5.order_send(req)
        if res is None:
            print(f"{stamp} FAIL order_send returned None: {mt5.last_error()}")
            continue
        ok = res.retcode in (10009, 10008)
        print(f"{stamp} {'CLOSED' if ok else 'REJECTED'} retcode={res.retcode} "
              f"deal={getattr(res, 'deal', '?')} price={getattr(res, 'price', '?')}")
        if ok:
            closed += 1
    mt5.shutdown()
    print(f"{stamp} closed {closed}/{len(positions)} positions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
