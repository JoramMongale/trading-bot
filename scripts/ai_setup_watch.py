"""Read-only AI setup watcher (plan 03-01).

Watches the live terminal for the deterministic breakout setup and reports what
the AI layer makes of it — WITHOUT placing any order. READ-ONLY by contract:
the only BrokerClient calls this script makes are connect, fetch_rates, quote
and account_info. There is no order/position call anywhere (grep-verify that
before changing it).

Why it exists: the running gold-cent bot (magic 77020) already owns the
account, and the AI filter is new. It must be observed against real data before
it is ever allowed to gate real orders. This watcher is that observation tool:
every bar it sees, every proposal, every gate verdict goes to the decision log.

Usage:
    .venv\\Scripts\\python scripts\\ai_setup_watch.py --once
    .venv\\Scripts\\python scripts\\ai_setup_watch.py                # keep watching
    ... --provider deepseek                                          # needs DEEPSEEK_API_KEY
    ... --terminal-path "C:\\Program Files\\MetaTrader 5 EXNESS\\terminal64.exe" --symbol XAUUSDc

Exit codes: 0 ok, 1 broker/config unavailable, 2 bad arguments.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import replace

from trading_bot.ai.gate import APPROVED, evaluate_proposal
from trading_bot.ai.context import build_trade_context
from trading_bot.broker import MT5Broker
from trading_bot.broker.base import BrokerUnavailableError
from trading_bot.cli import build_ai_client
from trading_bot.config import load_config
from trading_bot.live.engine import levels_are_tradable
from trading_bot.logging_utils import get_logger, log_decision
from trading_bot.strategy.levels import support_resistance
from trading_bot.strategy.signals import detect_setups
from trading_bot.strategy.swings import detect_swings

DEFAULT_TERMINAL = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="scripts/ai_setup_watch.py")
    p.add_argument("--config", default="config/config-ai.toml")
    p.add_argument("--once", action="store_true", help="check once and exit")
    p.add_argument("--interval", type=float, default=30.0,
                   help="seconds between checks (default 30)")
    p.add_argument("--provider", choices=["mock", "deepseek"], default=None,
                   help="override [ai] provider")
    p.add_argument("--symbol", default="XAUUSDc",
                   help="broker symbol to watch (default XAUUSDc, the cent gold)")
    p.add_argument("--terminal-path", default=DEFAULT_TERMINAL,
                   help="terminal64.exe of the account's own install")
    p.add_argument("--bars", type=int, default=100, help="bars of history to fetch")
    p.add_argument("--log", default="ai_watch.log", help="decision log filename")
    return p.parse_args(argv)


def detect(df, cfg):
    """The shared strategy chain — swings -> S/R -> setups (SAFE-01)."""
    df = df.copy()
    df = detect_swings(df, cfg.strategy.fractal_left, cfg.strategy.fractal_right)
    df = support_resistance(df, cfg.strategy.sr_lookback)
    df = detect_setups(df)
    return df


def _report(args, cfg, ai_client, logger) -> None:
    broker = MT5Broker(
        symbol=args.symbol,
        bridge="native",
        terminal_path=args.terminal_path,
        terminal_portable=True,
    )
    broker.connect()
    df = broker.fetch_rates(args.symbol, cfg.data.timeframe, args.bars)
    if df.empty:
        log_decision(logger, "watch_check", setup=False, reason="no_data")
        print("no bars from the terminal yet")
        return

    bar_time = df.index[-1]
    df = detect(df, cfg)
    setup = bool(df["setup"].iloc[-1])
    if not setup:
        log_decision(logger, "watch_check", bar=bar_time.isoformat(), setup=False)
        print(f"{bar_time.isoformat()}  no setup")
        return

    entry = float(df["resistance"].iloc[-1])
    sl = float(df["support"].iloc[-1] - cfg.strategy.sl_buffer)
    tp = entry + cfg.strategy.rr_multiple * (entry - sl)
    if not levels_are_tradable(entry, sl, tp):
        log_decision(logger, "watch_check", bar=bar_time.isoformat(), setup=True,
                     reason="invalid_levels", entry=round(entry, 2),
                     sl=round(sl, 2), tp=round(tp, 2))
        print(f"{bar_time.isoformat()}  setup but levels incomplete (entry={entry:.2f} "
              f"sl={sl:.2f} tp={tp:.2f})")
        return

    log_decision(logger, "setup_detected", bar=bar_time.isoformat(),
                 entry=round(entry, 2), sl=round(sl, 2), tp=round(tp, 2))
    print(f"SETUP on {bar_time.isoformat()}  entry={entry:.2f} sl={sl:.2f} tp={tp:.2f}")

    try:
        balance = broker.account_info().balance
    except BrokerUnavailableError:
        balance = None
    ctx = build_trade_context(df, cfg, entry, sl, tp, bar_time, balance=balance)
    try:
        proposal = ai_client.propose_trade(ctx)
    except Exception as exc:  # noqa: BLE001 - report, don't crash the watcher
        print(f"  AI unavailable: {type(exc).__name__}: {exc}")
        log_decision(logger, "ai_unavailable", bar=bar_time.isoformat(),
                     detail=f"{type(exc).__name__}: {exc}")
        return

    verdict = evaluate_proposal(
        proposal,
        entry=entry, sl=sl, tp=tp, direction="long",
        min_confidence=cfg.ai.min_confidence,
        require_agreement=cfg.ai.require_agreement,
    )
    log_decision(logger, "ai_proposal", bar=bar_time.isoformat(),
                 bias=proposal.bias, confidence=proposal.confidence,
                 invalidation=proposal.invalidation,
                 verdict=verdict.verdict, reason=verdict.reason)
    print(
        f"  AI: bias={proposal.bias}  confidence={proposal.confidence}  "
        f"invalidation={proposal.invalidation}  "
        f"gate={verdict.verdict} ({verdict.reason})"
    )


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        cfg = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.provider is not None:
        cfg = replace(cfg, ai=replace(cfg.ai, provider=args.provider))

    output_dir = cfg.backtest.output_dir
    logger = get_logger(f"ai-watch:{args.log}", f"{output_dir}/{args.log}")
    log_decision(logger, "watch_start", symbol=args.symbol,
                 provider=cfg.ai.provider, model=cfg.ai.model,
                 timeframe=cfg.data.timeframe)

    try:
        ai_client = build_ai_client(cfg, f"{output_dir}/ai_calls_{args.log}.jsonl")
        while True:
            try:
                _report(args, cfg, ai_client, logger)
            except BrokerUnavailableError as exc:
                print(f"broker unavailable: {exc}", file=sys.stderr)
                log_decision(logger, "watch_error",
                             detail=f"{type(exc).__name__}: {exc}")
            if args.once:
                return 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        log_decision(logger, "watch_stop", reason="keyboard_interrupt")
        print("stopped")
        return 0
    except (BrokerUnavailableError,) as exc:
        print(f"error: {exc}", file=sys.stderr)
        log_decision(logger, "watch_stop", reason="exception")
        return 1


if __name__ == "__main__":
    sys.exit(main())
