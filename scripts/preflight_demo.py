"""Preflight the MT5 demo connection before running the bot (quick task 260819-nhq).

Answers, in order, the four things that actually block a first demo run:
  1. is the RPC bridge reachable?
  2. is the terminal logged in, and is the account really a DEMO?
  3. does the broker quote the configured symbol under that exact name?
  4. are there enough closed bars for the engine to evaluate a setup?

Read-only: it places nothing and changes nothing.

    python scripts/preflight_demo.py [--config config/config.toml]
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace

import pandas as pd

from trading_bot.broker import MT5Broker
from trading_bot.broker.base import BrokerUnavailableError
from trading_bot.config import live_symbol, load_config
from trading_bot.live.safety import ACCOUNT_TRADE_MODE_DEMO, ACCOUNT_TRADE_MODE_REAL

# Names brokers commonly use for spot gold, tried when the configured one misses.
# How far the newest CLOSED bar may sit behind the live tick before the feed
# counts as stale. A legitimate M5 lag is at most one closed bar plus the
# forming one (~10 min), so 15 leaves headroom without waving through history
# that is hours old.
MAX_BAR_LAG_MIN = 15

GOLD_ALIASES = ["XAUUSD", "XAUUSDm", "XAUUSD.m", "GOLD", "GOLDm", "XAUUSDc"]

TRADE_MODES = {ACCOUNT_TRADE_MODE_DEMO: "DEMO", 1: "CONTEST", ACCOUNT_TRADE_MODE_REAL: "REAL"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/config.toml")
    args = ap.parse_args()
    cfg = load_config(args.config)
    # This script preflights a DEMO connection, so resolve the symbol as demo
    # would. The committed config ships mode="dry-run" (the repo must never
    # default to touching a broker), and live_symbol() deliberately returns the
    # VENDOR name in dry-run — which would have us probing for XAUUSD here.
    cfg = replace(cfg, live=replace(cfg.live, mode="demo"))
    SYMBOL = live_symbol(cfg)

    def _connect(sym: str) -> MT5Broker:
        b = MT5Broker(
            symbol=sym,
            bridge=cfg.live.bridge,
            bridge_host=cfg.live.bridge_host,
            bridge_port=cfg.live.bridge_port,
            terminal_path=cfg.live.terminal_path,
            terminal_portable=cfg.live.terminal_portable,
            expected_login=cfg.live.expected_login,
        )
        b.connect()
        return b

    print(f"1. bridge  {cfg.live.bridge} -> {cfg.live.bridge_host}:{cfg.live.bridge_port}")
    try:
        broker = _connect(SYMBOL)
    except BrokerUnavailableError as exc:
        # connect() calls symbol_select, so a broker that names gold differently
        # (Exness uses XAUUSDm on some account types) fails HERE, before the
        # symbol step below is ever reached. Probe the aliases now or the error
        # is unactionable.
        if "symbol_select" not in str(exc):
            print(f"   FAIL {exc}")
            return 1
        print(f"   {SYMBOL!r} not available — probing common gold symbols")
        for alias in GOLD_ALIASES:
            if alias == SYMBOL:
                continue
            try:
                _connect(alias)
            except BrokerUnavailableError:
                continue
            print(f'   FOUND {alias!r} — set [live] symbol = "{alias}" and re-run')
            return 1
        print("   FAIL no gold symbol found; check MarketWatch in the terminal")
        return 1
    print("   ok — terminal connected, trade allowed")

    acct = broker.account_info()
    mode = TRADE_MODES.get(acct.trade_mode, f"UNKNOWN({acct.trade_mode})")
    print(f"2. account {acct.login} @ {acct.server} — {mode}, {acct.balance:.2f} {acct.currency}")
    if acct.trade_mode != ACCOUNT_TRADE_MODE_DEMO:
        print("   FAIL not a demo account — refusing to go further")
        return 1

    n = cfg.strategy.sr_lookback + cfg.strategy.fractal_left + cfg.strategy.fractal_right + 5
    print(f"3. symbol  {SYMBOL}")
    df = broker.fetch_rates(SYMBOL, cfg.data.timeframe, n)
    if df.empty:
        print(f"   no bars for {SYMBOL!r} — trying common aliases")
        for alias in GOLD_ALIASES:
            if alias == SYMBOL:
                continue
            try:
                if not broker.fetch_rates(alias, cfg.data.timeframe, n).empty:
                    print(f"   FOUND {alias!r} — set [data] symbol = \"{alias}\"")
                    return 1
            except Exception:
                continue
        print("   FAIL no gold symbol found; check MarketWatch")
        return 1

    print(f"4. bars    {len(df)}/{n} closed {cfg.data.timeframe} bars")
    print(f"   latest {df.index[-1]}  close={df['close'].iloc[-1]:.2f}")
    if len(df) < n:
        print("   FAIL not enough history yet — wait for the terminal to sync")
        return 1

    # Bar FRESHNESS, which is a separate failure from bar COUNT. A terminal
    # that has just started serves a full 69 bars of history that is hours
    # old: every other check here passes, and a bot started on it computes
    # support/resistance from prices that no longer exist. Seen on 2026-08-20,
    # bars 8 hours behind while the account, connection and bar count were all
    # green.
    #
    # Measured against the terminal's own latest TICK rather than the host
    # clock, so it needs no assumption about the server's timezone -- and it
    # cannot false-alarm when the market is closed, because the tick goes
    # stale alongside the bars and the LAG between them stays small.
    tick = broker._mt5().symbol_info_tick(SYMBOL)
    tick_epoch = getattr(tick, "time", 0) if tick is not None else 0
    if not tick_epoch:
        print("   FAIL no tick for the symbol — cannot judge whether bars are current")
        return 1
    tick_time = pd.Timestamp(tick_epoch, unit="s")
    lag_min = (tick_time - df.index[-1]).total_seconds() / 60
    print(f"   tick   {tick_time}  (newest bar is {lag_min:.0f} min behind it)")
    if lag_min > MAX_BAR_LAG_MIN:
        print(f"   FAIL bars are {lag_min:.0f} min stale (limit {MAX_BAR_LAG_MIN}) — "
              "the terminal is still downloading history")
        return 1

    print()
    print(f"READY — {SYMBOL} on a demo account, {len(df)} bars.")
    print(f"  lot {cfg.trading.lot} x {cfg.trading.contract_size} oz = "
          f"{cfg.trading.lot * cfg.trading.contract_size:g} oz per trade")
    print("  next: python -m trading_bot.cli live --once --mode demo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
