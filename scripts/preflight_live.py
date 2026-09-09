"""Read-only pre-flight for a REAL account. Places nothing, changes nothing.

    python scripts/preflight_live.py --config config/config-btc.toml --real-account

``preflight_demo.py`` refuses any account that is not DEMO, and that guard is
deliberate and stays. This is the real-money counterpart: it runs the SAME
checks, but instead of refusing a REAL account it requires you to say so out
loud with ``--real-account``. Automation can pass that flag; a person running
the wrong command by hand cannot pass it by accident.

Every check is a read. Nothing here can open, modify or close a position.

Exit codes:  0 ready   1 not ready   2 cannot reach the terminal
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

TRADE_MODES = {0: "DEMO", 1: "CONTEST", 2: "REAL"}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config/config-btc.toml")
    p.add_argument("--real-account", action="store_true",
                   help="acknowledge that this account trades real money")
    p.add_argument("--max-bar-age", type=float, default=15.0,
                   help="minutes; a feed staler than this is not ready")
    a = p.parse_args(argv)

    from trading_bot.broker import MT5Broker
    from trading_bot.broker.base import BrokerUnavailableError
    from trading_bot.config import live_symbol, load_config

    cfg = load_config(a.config)
    symbol = live_symbol(cfg)
    ok = True

    def check(label, passed, detail=""):
        nonlocal ok
        ok = ok and passed
        print(f"  [{'ok ' if passed else 'FAIL'}] {label}{'  ' + detail if detail else ''}")

    print(f"preflight {a.config}  symbol={symbol}  mode={cfg.live.mode}")

    broker = MT5Broker(symbol, bridge=cfg.live.bridge,
                       bridge_host=cfg.live.bridge_host,
                       bridge_port=cfg.live.bridge_port,
                       terminal_path=cfg.live.terminal_path,
                       terminal_portable=cfg.live.terminal_portable)
    try:
        broker.connect()
    except BrokerUnavailableError as exc:
        print(f"  [FAIL] terminal unreachable: {exc}")
        return 2
    check("terminal reachable and trade_allowed", True)

    acct = broker.account_info()
    mode = TRADE_MODES.get(acct.trade_mode, f"UNKNOWN({acct.trade_mode})")
    print(f"         account {acct.login}  {mode}  "
          f"{acct.balance:.2f} {acct.currency}")
    if mode == "REAL" and not a.real_account:
        check("REAL account acknowledged", False,
              "pass --real-account to proceed; this trades real money")
        return 1
    check(f"account type {mode} accepted", True)

    # The feed is the check that actually catches a wedged terminal: it can be
    # connected and trade_allowed while serving hours-old bars, and a bot
    # started against that will act on stale prices.
    df = broker.fetch_rates(symbol, cfg.data.timeframe, 10)
    check("bars available", not df.empty, f"{len(df)} fetched")
    if df.empty:
        return 1
    age = datetime.now(timezone.utc).replace(tzinfo=None) - df.index[-1].to_pydatetime()
    fresh = age < timedelta(minutes=a.max_bar_age)
    check("feed is fresh", fresh, f"last bar {age.total_seconds()/60:.1f} min old")

    sr = broker.symbol_risk(symbol)
    check("tick economics populated", sr.tick_size > 0 and sr.tick_value > 0,
          f"tick_size={sr.tick_size} tick_value={sr.tick_value}")

    # Sizing must produce a tradable lot at the CURRENT balance, or the bot
    # will run all day and refuse every setup -- which looks identical to a bot
    # that is broken.
    from trading_bot.live.engine import position_size
    quote = broker.quote(symbol)
    med_stop = {"XAUUSDc": 24.30, "BTCUSDc": 759.0}.get(symbol)
    if med_stop:
        lots = position_size(cfg, acct.balance, med_stop, sr=sr, price=quote.ask)
        check("median setup is affordable", lots > 0,
              f"{lots} lots at a {med_stop} stop")

    total = cfg.risk.max_loss_pct_per_trade * cfg.risk.max_concurrent
    print(f"         risk {cfg.risk.max_loss_pct_per_trade}% x "
          f"{cfg.risk.max_concurrent} slots = {total}% of balance on this bot")

    print("READY" if ok else "NOT READY")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
