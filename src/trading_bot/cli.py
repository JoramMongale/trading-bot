"""Command-line entry point: ``python -m trading_bot.cli {backtest,live}``.

``backtest`` runs the Phase 1 backtest end to end on historical bars only (no
MT5 anywhere in the path): load config -> load histdata M1 CSVs -> resample to
M5 -> run the shared strategy engine -> write per-trade CSV + aggregate stats
+ a structured decision log (SAFE-01, SAFE-02, EXEC-03).

``live`` runs the Phase 2 live bot: load config -> pick the broker by
``[live] mode`` (dry-run -> DryRunBroker wrapping a ReplayBroker seeded with
historical bars; demo/live -> MT5Broker) -> run the LiveEngine on an interval
-> write every decision to ``output/<--log>`` (SAFE-02). MT5 unavailable is a graceful,
actionable error, never a crash (EXEC-01).

Exit codes: 0 on success, 1 on no-data/config/broker-connect errors, 2 on
bad arguments.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import replace
from pathlib import Path

import pandas as pd

from trading_bot.ai.backtest import run_ai_backtest
from trading_bot.ai.deepseek import DeepSeekClient
from trading_bot.ai.engine import AIEngine
from trading_bot.ai.mock import MockAIClient, RecordingAIClient
from trading_bot.backtest.engine import run_backtest
from trading_bot.backtest.stats import trade_stats
from trading_bot.broker import DryRunBroker, MT5Broker, ReplayBroker
from trading_bot.broker.base import (
    BrokerClient,
    BrokerRejectedError,
    BrokerUnavailableError,
)
from trading_bot.config import live_symbol, load_config
from trading_bot.data.loader import (
    base_symbol,
    load_histdata_csv,
    load_instrument_spec,
)
from trading_bot.data.resample import resample_to_m5
from trading_bot.live.engine import LiveEngine
from trading_bot.logging_utils import get_logger, log_decision

HISTDATA_URL = (
    "https://www.histdata.com/download-free-forex-data/?/ascii/1-minute-bar-quotes"
)

# Files are monthly, gold M1 has ~1h daily breaks and ~2-day weekend gaps, so
# any gap > 3 days between consecutive M1 bars means missing file(s)/a silent
# stale region. A warning knob, not a config key (not worth schema churn).
MAX_M1_GAP = pd.Timedelta("3D")

TRADE_COLUMNS = [
    "entry_time",
    "entry",
    "sl",
    "tp",
    "exit_time",
    "exit_price",
    "exit_reason",
    "pnl_points",
    "r_multiple",
]

STAT_LABELS = [
    ("total_trades", "Total trades (closed)"),
    ("open_trades", "Open trades"),
    ("wins", "Wins"),
    ("losses", "Losses"),
    ("win_rate", "Win rate"),
    ("net_pnl_points", "Net P&L (points)"),
    ("net_pnl_usd", "Net P&L (USD)"),
    ("avg_r", "Avg R multiple"),
    ("profit_factor", "Profit factor"),
    ("max_drawdown_usd", "Max drawdown (USD)"),
    ("avg_trade_bars", "Avg trade duration (bars)"),
]


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m trading_bot.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    bt = sub.add_parser("backtest", help="run the backtest over historical bars")
    bt.add_argument(
        "--config",
        default="config/config.toml",
        help="path to the TOML config file (default: config/config.toml)",
    )
    bt.add_argument(
        "--data-dir",
        default=None,
        help="directory with histdata M1 CSV files (default: config [data] raw_dir)",
    )
    bt.add_argument(
        "--m5-csv",
        default=None,
        help="backtest an already-M5 OHLC CSV (e.g. fetch_broker_history.py "
             "output) instead of histdata M1 files. Columns: open,high,low,"
             "close, datetime index named 'time'.",
    )
    bt.add_argument(
        "--start", default=None, help="start date YYYY-MM-DD, inclusive (optional)"
    )
    bt.add_argument(
        "--end", default=None, help="end date YYYY-MM-DD, exclusive (optional)"
    )
    bt.add_argument(
        "--quick",
        type=int,
        default=None,
        help="backtest only the first N resampled M5 bars (signal-count sanity check)",
    )
    live = sub.add_parser("live", help="run the live bot (dry-run/demo/live)")
    live.add_argument(
        "--config",
        default="config/config.toml",
        help="path to the TOML config file (default: config/config.toml)",
    )
    live.add_argument(
        "--once",
        action="store_true",
        help="run one poll and exit",
    )
    live.add_argument(
        "--mode",
        choices=["dry-run", "demo", "live"],
        default=None,
        help="override [live] mode from config",
    )
    live.add_argument(
        "--log",
        default="live.log",
        help=(
            "decision-log filename inside the output dir (default: live.log). "
            "Two bots running side by side MUST use different names and "
            "different [live] magic_number values: they share one account, so "
            "interleaved logs and a shared magic would make their trades "
            "indistinguishable and defeat each other's dedup guards."
        ),
    )
    live.add_argument(
        "--provider",
        choices=["mock", "deepseek"],
        default=None,
        help="override [ai] provider for this run (mock is offline, no key)",
    )
    ai = sub.add_parser(
        "ai-backtest",
        help="replay history with the AI proposal gate (plan 03-01); reports raw vs gated",
    )
    ai.add_argument(
        "--config",
        default="config/config.toml",
        help="path to the TOML config file (default: config/config.toml)",
    )
    ai.add_argument(
        "--data-dir",
        default=None,
        help="directory with histdata M1 CSV files (default: config [data] raw_dir)",
    )
    ai.add_argument(
        "--start", default=None, help="start date YYYY-MM-DD, inclusive (optional)"
    )
    ai.add_argument(
        "--end", default=None, help="end date YYYY-MM-DD, exclusive (optional)"
    )
    ai.add_argument(
        "--provider",
        choices=["mock", "deepseek"],
        default=None,
        help="override [ai] provider for this run (mock is offline, no key)",
    )
    ai.add_argument(
        "--log",
        default="ai_backtest.log",
        help="decision-log filename inside the output dir (default: ai_backtest.log)",
    )
    return parser.parse_args(argv)


def list_histdata_csves(data_dir: Path, symbol: str) -> list[Path]:
    """List histdata M1 ASCII CSVs for ``symbol`` in ``data_dir``.

    histdata.com names real files ``DAT_ASCII_{SYMBOL}_M1_{YYYYMM}.csv``;
    restricting the glob to that prefix (using the configured symbol) means
    the default command ignores the synthetic sample and any other stray CSV
    no matter what else sits in the data dir.
    """
    return sorted(data_dir.glob(f"DAT_ASCII_{symbol}_M1_*.csv"))


def find_data_gaps(
    m1: pd.DataFrame, max_gap: pd.Timedelta = MAX_M1_GAP
) -> list[dict]:
    """Return one dict per >``max_gap`` timestamp gap in the M1 frame.

    Each dict: ``{"gap_from": ts, "gap_to": ts, "gap_hours": float}`` where
    ``gap_hours`` is the elapsed hours between the last bar before the gap and
    the first bar after it. Pure (DataFrame -> list, pandas only); the input
    frame is expected sorted+deduped (``_load_all`` output) but any unsorted
    input still yields a well-defined per-adjacent-diff result.
    """
    max_gap_hours = max_gap.total_seconds() / 3600.0
    diffs = pd.Series(m1.index).diff().dropna()
    gaps = []
    for offset, delta in enumerate(diffs, start=1):
        hours = delta.total_seconds() / 3600.0
        if hours > max_gap_hours:
            # diffs[offset-1] spans m1.index[offset-1] -> m1.index[offset]
            # (offset counts the dropped NaT first diff)
            gaps.append(
                {
                    "gap_from": m1.index[offset - 1],
                    "gap_to": m1.index[offset],
                    "gap_hours": hours,
                }
            )
    return gaps


def _load_all(csvs: list[Path]) -> pd.DataFrame:
    """Load + concat + dedupe + sort histdata M1 CSVs into one frame."""
    frames = [load_histdata_csv(str(path)) for path in csvs]
    df = pd.concat(frames)
    df = df[~df.index.duplicated(keep="first")]
    return df.sort_index()


def _print_stats(stats: dict) -> None:
    print("Backtest stats:")
    for key, label in STAT_LABELS:
        value = stats[key]
        if key == "win_rate":
            text = f"{value:.1%}"
        elif isinstance(value, float):
            text = "inf" if value == float("inf") else f"{value:.2f}"
        else:
            text = str(value)
        print(f"  {label:<26} {text}")


def _stat_for_log(value):
    if isinstance(value, float) and value != float("inf"):
        return round(value, 2)
    return value


def _dry_run_rates(cfg) -> pd.DataFrame | None:
    """Load the configured histdata CSVs as M5 bars for a dry-run replay.

    Returns ``None`` when no data is on disk — dry-run must still start and
    report ``bar_fetch_failed`` gracefully rather than refusing to run.
    """
    csvs = list_histdata_csves(Path(cfg.data.raw_dir), cfg.data.symbol)
    if not csvs:
        return None
    return resample_to_m5(_load_all(csvs))


def build_broker(cfg, logger=None) -> BrokerClient:
    """Return the broker for the configured ``[live] mode`` (EXEC-03).

    dry-run -> DryRunBroker wrapping a ReplayBroker seeded with the historical
    bars the backtest uses (phase success criterion 4: logs exactly what would
    be sent, places nothing). The cursor is rewound ``live.replay_bars`` bars so
    each poll walks one closed bar forward — the same one-new-bar-per-poll shape
    a real terminal produces, which makes dry-run a genuine offline smoke test.
    With no CSVs on disk the broker has no rates and polls report
    ``bar_fetch_failed``, unchanged. ``logger`` is handed to the DryRunBroker so
    its ``order_plan`` line (SAFE-02: exactly what WOULD be sent) reaches
    ``live.log`` — without it the dry-run audit trail is silently missing.

    demo/live -> the real MT5Broker, reaching the terminal through the
    configured transport (native package or the silicon RPC bridge); the
    engine's SAFE-03 gate plus ``connect()`` failures handle account-mode
    enforcement and availability.
    """
    if cfg.live.mode == "dry-run":
        rates = _dry_run_rates(cfg)
        cursor = None if rates is None else max(0, len(rates) - cfg.live.replay_bars)
        return DryRunBroker(
            ReplayBroker(rates=rates, trade_mode=0, cursor=cursor), logger=logger
        )
    return MT5Broker(
        symbol=live_symbol(cfg),
        bridge=cfg.live.bridge,
        bridge_host=cfg.live.bridge_host,
        bridge_port=cfg.live.bridge_port,
        terminal_path=cfg.live.terminal_path,
        terminal_portable=cfg.live.terminal_portable,
    )


def build_ai_client(cfg, record_path=None):
    """Return an AIClient for the configured ``[ai] provider`` (plan 03-01).

    mock     -> MockAIClient: offline, deterministic, no key, no network.
    deepseek -> DeepSeekClient: stdlib HTTP to the OpenAI-compatible endpoint;
                the key is read from the environment at call time, so no secret
                ever passes through config.
    ``record_path``, when set AND ``[ai] record_calls``, wraps the client in a
    RecordingAIClient that appends every prompt+response to that JSONL file for
    offline audit of model output quality (SAFE-02 for the AI half).
    """
    if cfg.ai.provider == "mock":
        client = MockAIClient()
    else:
        client = DeepSeekClient(cfg)
    if cfg.ai.record_calls and record_path:
        client = RecordingAIClient(client, record_path)
    return client


def _summarize(result: dict) -> str:
    """One-line human summary of a poll result (``--once`` output)."""
    event = result["event"]
    if event == "order_placed":
        return (
            f"order_placed ticket={result['ticket']} "
            f"entry={result['entry']:.2f} sl={result['sl']:.2f} tp={result['tp']:.2f}"
        )
    if event == "order_skipped":
        return f"order_skipped reason={result.get('reason')}"
    if event == "order_rejected":
        return f"order_rejected error={result.get('error')}"
    if event == "bar_fetch_failed":
        return f"bar_fetch_failed error={result.get('error')}"
    if event == "bar_check":
        return (
            f"bar_check new_bar={result.get('new_bar')} "
            f"setup={result.get('setup', False)}"
        )
    return event


def _run_live(args) -> int:
    try:
        cfg = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # --mode overrides the configured [live] mode for this run (frozen config
    # -> rebuild via dataclasses.replace).
    if args.mode is not None:
        cfg = replace(cfg, live=replace(cfg.live, mode=args.mode))

    # --provider overrides the configured [ai] provider for this run (plan
    # 03-02). Applied before the engine is built so it affects both the
    # AIEngine/LiveEngine selection AND build_ai_client below. Lets a user run a
    # real-DeepSeek dry-run without editing config; configs stay the safe default.
    if getattr(args, "provider", None):
        cfg = replace(cfg, ai=replace(cfg.ai, provider=args.provider))

    output_dir = Path(cfg.backtest.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    # Logger NAME is derived from the file, not fixed. Python caches loggers by
    # name, so two instances sharing the name "live" would share handlers and
    # write into each other's file regardless of the path given here.
    log_path = output_dir / args.log
    logger = get_logger(f"live:{args.log}", str(log_path))

    log_decision(
        logger,
        "live_start",
        mode=cfg.live.mode,
        # The BROKER's symbol — what actually goes on the wire. Logging
        # [data] symbol here made the log claim XAUUSD while the adapter
        # fetched XAUUSDm.
        symbol=live_symbol(cfg),
        timeframe=cfg.data.timeframe,
        magic=cfg.live.magic_number,
        lot=cfg.trading.lot,
        enabled=cfg.live.enabled,
    )

    broker = build_broker(cfg, logger)
    if cfg.ai.enabled:
        # AIEngine = LiveEngine + the AI layer (plan 03-01): the deterministic
        # parent still owns detection/dedup/safety/risk/placement; AIEngine
        # consults the model on each setup + once per day and gates the setup
        # through the pure proposal gate before the parent acts.
        record_path = output_dir / f"ai_calls_{args.log}.jsonl"
        ai_client = build_ai_client(cfg, record_path)
        engine = AIEngine(cfg, broker, logger, ai_client)
    else:
        engine = LiveEngine(cfg, broker, logger)

    # EXEC-01: an unavailable terminal is a graceful, actionable error, not a
    # crash. Dry-run never connects (the simulated broker is always connected).
    if cfg.live.mode != "dry-run":
        try:
            broker.connect()
        except BrokerUnavailableError as exc:
            print(f"error: {exc}", file=sys.stderr)
            log_decision(logger, "live_stop", reason="connect_failed")
            return 1

    try:
        if args.once:
            print(_summarize(engine.poll_once()))
            return 0
        # Consecutive failed polls (04-01). `bar_fetch_failed` counts as a
        # failure; a clean bar_check/order event resets the counter. When it
        # reaches [live] reconnect_after, the connection is torn down and
        # re-established. Empty frames (market closed) are NOT failures — a
        # closure must not churn the connection.
        consecutive_failures = 0
        while True:
            # An unexpected error in ONE poll must not kill the loop. The
            # adapter crashed on AttributeError mid-placement on 2026-08-19 and
            # took the bot down with it, so it stopped watching the market
            # entirely — strictly worse than skipping a poll. Log and continue;
            # the decision log keeps the failure visible.
            try:
                result = engine.poll_once()
            except (KeyboardInterrupt, SystemExit):
                raise
            except BrokerUnavailableError as exc:
                # A poll that raised broker-unavailable (e.g. inside on_setup's
                # account/quote calls, not just fetch) is the same disconnect as
                # bar_fetch_failed — count it so reconnect fires. The engine
                # converts fetch failures to events, but not all paths do.
                log_decision(logger, "bar_fetch_failed", reason=str(exc))
                consecutive_failures += 1
            except Exception as exc:  # noqa: BLE001 - deliberately broad
                log_decision(
                    logger,
                    "poll_error",
                    error=f"{type(exc).__name__}: {exc}",
                )
                print(f"poll error: {type(exc).__name__}: {exc}", file=sys.stderr)
            else:
                if result.get("event") == "bar_fetch_failed":
                    consecutive_failures += 1
                else:
                    consecutive_failures = 0

            if (
                cfg.live.reconnect_after > 0
                and consecutive_failures >= cfg.live.reconnect_after
            ):
                log_decision(
                    logger,
                    "reconnect_attempt",
                    failures=consecutive_failures,
                )
                try:
                    broker.reconnect()
                except (BrokerUnavailableError, BrokerRejectedError) as exc:
                    log_decision(logger, "reconnect_failed", error=str(exc))
                    # A long terminal outage must not hammer it: sleep the
                    # backoff before the next poll/retry.
                    time.sleep(cfg.live.reconnect_backoff)
                else:
                    log_decision(logger, "reconnected")
                    consecutive_failures = 0

            time.sleep(cfg.live.poll_interval)
    except KeyboardInterrupt:
        log_decision(logger, "live_stop", reason="keyboard_interrupt")
        print("stopped")
        return 0
    except (BrokerUnavailableError, BrokerRejectedError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        log_decision(logger, "live_stop", reason="exception")
        return 1


def _run_ai_backtest(args) -> int:
    """``ai-backtest``: replay history with the AI gate; report raw vs gated.

    The deterministic backtest runs twice over the same bars — once ungated
    (raw_trades) and once through the AI proposal gate (gated_trades) — so the
    honest comparison the plan demands is reported side by side. Offline with
    ``provider = "mock"`` (AI-04); every AI decision lands in the decision log.
    """
    try:
        cfg = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.provider is not None:
        cfg = replace(cfg, ai=replace(cfg.ai, provider=args.provider))

    data_dir = Path(args.data_dir) if args.data_dir else Path(cfg.data.raw_dir)
    csvs = list_histdata_csves(data_dir, cfg.data.symbol)
    if not csvs:
        print(
            f"no CSV files found in {data_dir}.",
            file=sys.stderr,
        )
        print(
            "Download XAUUSD M1 ASCII CSVs from histdata.com and unzip them here "
            f"(see README): {HISTDATA_URL}",
            file=sys.stderr,
        )
        return 1

    output_dir = Path(cfg.backtest.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    logger = get_logger(f"ai-backtest:{args.log}", str(output_dir / args.log))
    log_decision(
        logger,
        "ai_backtest_run",
        provider=cfg.ai.provider,
        model=cfg.ai.model,
        symbol=cfg.data.symbol,
        timeframe=cfg.data.timeframe,
        min_confidence=cfg.ai.min_confidence,
        require_agreement=cfg.ai.require_agreement,
        regime_check_daily=cfg.ai.regime_check_daily,
        block_when_choppy=cfg.ai.block_when_choppy,
    )

    m1 = _load_all(csvs)
    for gap in find_data_gaps(m1):
        log_decision(
            logger, "data_gap_detected",
            gap_from=gap["gap_from"], gap_to=gap["gap_to"],
            gap_hours=round(gap["gap_hours"], 2),
        )
    if args.start:
        m1 = m1[m1.index >= pd.Timestamp(args.start)]
    if args.end:
        m1 = m1[m1.index < pd.Timestamp(args.end)]
    m5 = resample_to_m5(m1)
    if m5.empty:
        print("no bars left after filtering/resampling — nothing to backtest",
              file=sys.stderr)
        return 1

    def emit(event: dict) -> None:
        fields = {
            k: (round(v, 2) if k in ("entry", "sl", "tp", "exit_price",
                                     "invalidation") else v)
            for k, v in event.items()
            if k != "event"
        }
        log_decision(logger, event["event"], **fields)

    record_path = output_dir / f"ai_calls_{args.log}.jsonl"
    ai_client = build_ai_client(cfg, record_path)
    result = run_ai_backtest(m5, cfg, ai_client, on_event=emit)

    def stats(trades):
        return trade_stats(
            trades, contract_size=cfg.trading.contract_size, lot=cfg.trading.lot
        )

    raw_stats = stats(result["raw_trades"])
    gated_stats = stats(result["gated_trades"])

    print("AI-gated backtest (plan 03-01):")
    print(f"  provider={cfg.ai.provider}  model={cfg.ai.model}")
    print(
        f"  AI consultations={result['consultations']}  approved={result['approved']}  "
        f"rejected={result['rejected']}  unavailable={result['unavailable']}"
    )
    print(
        f"  regime checks={result['regime_checks']}  regime blocks={result['regime_blocks']}"
    )
    print()
    for label, s in (("Raw deterministic", raw_stats), ("AI-gated", gated_stats)):
        print(f"  {label:<17} trades={s['total_trades']:<5} "
              f"win={s['win_rate']:.1%}  netR={s['avg_r']:.3f}  "
              f"PF={s['profit_factor']:.2f}  DD={s['max_drawdown_usd']:.2f}")

    if result["gated_trades"]:
        df_trades = pd.DataFrame(result["gated_trades"])[TRADE_COLUMNS]
        for col in ("entry", "sl", "tp", "exit_price", "pnl_points"):
            df_trades[col] = df_trades[col].round(2)
        df_trades["r_multiple"] = df_trades["r_multiple"].round(4)
    else:
        df_trades = pd.DataFrame(columns=TRADE_COLUMNS)
    df_trades.to_csv(output_dir / "ai_trades.csv", index=False)

    log_decision(
        logger, "ai_backtest_stats",
        consultations=result["consultations"],
        approved=result["approved"],
        rejected=result["rejected"],
        unavailable=result["unavailable"],
        regime_checks=result["regime_checks"],
        regime_blocks=result["regime_blocks"],
        raw_trades=raw_stats["total_trades"],
        gated_trades=gated_stats["total_trades"],
        raw_net_r=round(raw_stats["avg_r"], 4),
        gated_net_r=round(gated_stats["avg_r"], 4),
    )
    return 0


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.command == "live":
        return _run_live(args)
    if args.command == "ai-backtest":
        return _run_ai_backtest(args)
    if args.command != "backtest":
        return 2

    try:
        cfg = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # Backtest-only is structural (INST-04): the backtest CLI must never run a
    # config that permits live execution. A dedicated *-backtest config exists
    # for every instrument; loading a live config here is a mistake, not a mode.
    if cfg.live.enabled:
        print(
            f"error: backtest refuses [live] enabled=true configs "
            f"(SAFE-03 / INST-04); use a dedicated *-backtest config",
            file=sys.stderr,
        )
        return 1

    # Instrument spec sidecar (05-01): offline broker facts that key digit
    # rounding, money conversion, spread netting, and the symbol-identity
    # guard. Absent = legacy path, byte-identical to the pre-spec CLI.
    spec = None
    if cfg.data.spec_file:
        try:
            spec = load_instrument_spec(cfg.data.spec_file)
        except (FileNotFoundError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        # Symbol identity (INST-02, PITFALLS C4): a config whose [data] symbol
        # does not match the spec's broker symbol (e.g. gold-labelled EURJPY)
        # would silently label every bar and trade with the wrong instrument.
        # base_symbol() strips the trailing account-type letter so EURJPYc and
        # EURJPY compare equal.
        if base_symbol(cfg.data.symbol) != base_symbol(spec.symbol):
            print(
                f"error: config [data] symbol={cfg.data.symbol} does not match "
                f"spec file symbol {spec.symbol} ({cfg.data.spec_file}); "
                f"the backtest would silently label {spec.symbol} bars as {cfg.data.symbol}",
                file=sys.stderr,
            )
            return 1
    # A1/D2 seam: sl_buffer_points is expressed in broker POINTS and only gains
    # a price meaning through the spec's point. Refuse the points form when no
    # spec is present rather than misreading points as raw price.
    if cfg.strategy.sl_buffer_points > 0 and spec is None:
        print(
            f"error: strategy.sl_buffer_points is set but no [data] spec_file "
            f"is configured; points-form buffer needs a spec whose point "
            f"converts it to price",
            file=sys.stderr,
        )
        return 1

    # Output precision (PITFALLS A3): every price written to the trades CSV and
    # the decision log rounds at the instrument's own digits. Legacy no-spec
    # runs keep the historical 2-dp gold/BTC boundary.
    digits = spec.digits if spec is not None else 2

    data_dir = Path(args.data_dir) if args.data_dir else Path(cfg.data.raw_dir)
    csvs = list_histdata_csves(data_dir, cfg.data.symbol)
    if not csvs and not args.m5_csv:
        print(
            f"no CSV files found in {data_dir}.",
            file=sys.stderr,
        )
        print(
            "Download XAUUSD M1 ASCII CSVs from histdata.com and unzip them here "
            f"(see README): {HISTDATA_URL}",
            file=sys.stderr,
        )
        return 1

    output_dir = Path(cfg.backtest.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    logger = get_logger("backtest", str(output_dir / "backtest.log"))

    log_decision(
        logger,
        "backtest_run",
        source=cfg.data.source,
        symbol=cfg.data.symbol,
        timeframe=cfg.data.timeframe,
        raw_csvs=len(csvs),
        data_dir=str(data_dir),
        fractal_left=cfg.strategy.fractal_left,
        fractal_right=cfg.strategy.fractal_right,
        sr_lookback=cfg.strategy.sr_lookback,
        sl_buffer=cfg.strategy.sl_buffer,
        rr_multiple=cfg.strategy.rr_multiple,
        lot=cfg.trading.lot,
        contract_size=cfg.trading.contract_size,
        spec_symbol=spec.symbol if spec is not None else cfg.data.symbol,
        spec_digits=spec.digits if spec is not None else 2,
    )

    if args.m5_csv:
        # Broker-fetched M5 frame (fetch_broker_history.py output): already the
        # strategy timeframe, so no resample — the broker's own instrument and
        # pricing, which is what the bot actually trades.
        m1_path = Path(args.m5_csv)
        if not m1_path.exists():
            print(f"error: --m5-csv file not found: {m1_path}", file=sys.stderr)
            return 1
        # SC2 fallback when no spec is present: the broker CSV filename carries
        # the real symbol (EURJPYc_M5_broker.csv), so a gold config pointed at a
        # JPY CSV cannot silently mislabel it.
        if spec is None:
            stem = Path(args.m5_csv).stem                       # e.g. "EURJPYc_M5_broker"
            file_symbol = stem.split("_M5_")[0] if "_M5_" in stem else ""
            if file_symbol and base_symbol(file_symbol) != base_symbol(cfg.data.symbol):
                print(
                    f"error: data file {Path(args.m5_csv).name} encodes symbol {file_symbol}, "
                    f"which does not match config [data] symbol={cfg.data.symbol}",
                    file=sys.stderr,
                )
                return 1
        m5 = pd.read_csv(m1_path, index_col=0, parse_dates=True)
        m5.index.name = "time"
        m5 = m5[["open", "high", "low", "close"]].astype(float)
        csvs = [m1_path]
    else:
        m1 = _load_all(csvs)
        gaps = find_data_gaps(m1)
        for gap in gaps:
            log_decision(
                logger,
                "data_gap_detected",
                gap_from=gap["gap_from"],
                gap_to=gap["gap_to"],
                gap_hours=round(gap["gap_hours"], 2),
            )
        if gaps:
            print(
                f"warning: {len(gaps)} data gap(s) > 3 days detected "
                "(missing histdata file(s) possible) — see backtest.log",
                file=sys.stderr,
            )
        if args.start:
            m1 = m1[m1.index >= pd.Timestamp(args.start)]
        if args.end:
            m1 = m1[m1.index < pd.Timestamp(args.end)]
        m5 = resample_to_m5(m1)
    if args.quick:
        m5 = m5.head(args.quick)
    if m5.empty:
        print("no bars left after filtering/resampling — nothing to backtest", file=sys.stderr)
        return 1

    def emit(event: dict) -> None:
        fields = {
            k: (round(v, digits) if k in ("entry", "sl", "tp", "exit_price") else v)
            for k, v in event.items()
            if k != "event"
        }
        log_decision(logger, event["event"], **fields)

    # A1/D2: sl_buffer_points is expressed in broker POINTS; convert via the
    # spec's point so the stop distance is symbol-correct. Legacy sl_buffer
    # (raw price) is the default when sl_buffer_points is unset.
    sl_buffer = (
        cfg.strategy.sl_buffer_points * spec.point
        if (spec is not None and cfg.strategy.sl_buffer_points > 0)
        else cfg.strategy.sl_buffer
    )

    trades = run_backtest(
        m5,
        fractal_left=cfg.strategy.fractal_left,
        fractal_right=cfg.strategy.fractal_right,
        sr_lookback=cfg.strategy.sr_lookback,
        sl_buffer=sl_buffer,
        rr_multiple=cfg.strategy.rr_multiple,
        variant=cfg.strategy.variant,
        on_event=emit,
    )
    # Spec economics into stats (INST-01 money per point, INST-03 spread
    # netting). With no spec this is the legacy contract_size path — None/0.0
    # are behaviorally identical to the pre-spec positional call.
    stats = trade_stats(
        trades,
        contract_size=cfg.trading.contract_size,
        lot=cfg.trading.lot,
        value_per_point=(spec.value_per_point if spec is not None else None),
        spread_price=(spec.spread_price if spec is not None else 0.0),
    )

    # Per-trade CSV at the instrument's own quoting precision (spec.digits for
    # a spec run; legacy gold/BTC stays 2 dp).
    if trades:
        df_trades = pd.DataFrame(trades)[TRADE_COLUMNS]
        for col in ("entry", "sl", "tp", "exit_price", "pnl_points"):
            df_trades[col] = df_trades[col].round(digits)
        df_trades["r_multiple"] = df_trades["r_multiple"].round(4)
    else:
        df_trades = pd.DataFrame(columns=TRADE_COLUMNS)
    df_trades.to_csv(output_dir / "trades.csv", index=False)

    _print_stats(stats)
    log_decision(
        logger, "backtest_stats", **{k: _stat_for_log(v) for k, v in stats.items()}
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
