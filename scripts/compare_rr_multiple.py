"""Compare the strategy's outcome across TP/SL ratios (rr_multiple) on broker-native gold.

    python scripts/compare_rr_multiple.py

Runs the SAME pure-Python strategy the live bot uses (SAFE-01 — no copied
logic) over the broker's own XAUUSDm M5 bars at rr_multiple 1.0 / 1.5 / 2.0,
writes per-run trades.csv + stats.json under output/rr_multiple_study/, and
prints a markdown comparison table:

    rr_multiple | trades | win% | avg win R | avg loss R | net R | PF | max DD USD

Why the broker file: config-cent.toml's data span is the older/coarser
histdata range, while data/processed/XAUUSDm_M5_broker.csv is the freshest
broker-native M5 feed (100,000 bars) for the instrument the gold bot actually
trades — the honest substrate for a decision about the live bot.

Data file: data/processed/XAUUSDm_M5_broker.csv (fetch with
scripts/fetch_broker_history.py if missing). Exit code 1 on a missing file.

This script never imports MetaTrader5, never writes a config, and never
touches a live bot — it only reads the config (for the strategy params) and
writes study artifacts to output/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from trading_bot.backtest.engine import run_backtest  # noqa: E402
from trading_bot.backtest.stats import trade_stats  # noqa: E402
from trading_bot.config import load_config  # noqa: E402

CONFIG = ROOT / "config" / "config-cent.toml"
DATA_FILE = ROOT / "data" / "processed" / "XAUUSDm_M5_broker.csv"
OUT_DIR = ROOT / "output" / "rr_multiple_study"
RRS = (1.0, 1.5, 2.0)

# Same shape the CLI writes for trades.csv (see cli.py TRADE_COLUMNS).
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


def load_broker_m5(path: Path) -> pd.DataFrame:
    """Broker CSV -> M5 OHLC frame indexed by time (fetch_broker_history format)."""
    df = pd.read_csv(path)
    df["time"] = pd.to_datetime(df["time"])
    return df.set_index("time")[["open", "high", "low", "close"]]


def avg_r_of(trades: list[dict], reason: str) -> float:
    """Mean R multiple of the closed trades with ``exit_reason`` (TP or SL).

    OPEN trades are excluded exactly as the backtest conventions do (the stats
    dict's win_rate/net follow the same closed-only rule).
    """
    rs = [t["r_multiple"] for t in trades if t["exit_reason"] == reason]
    return sum(rs) / len(rs) if rs else 0.0


def main() -> int:
    if not DATA_FILE.exists():
        print(f"error: data file not found: {DATA_FILE}", file=sys.stderr)
        print(
            "suggest: run `python scripts/fetch_broker_history.py` to pull "
            "XAUUSDm M5 bars from the MT5 terminal",
            file=sys.stderr,
        )
        return 1

    cfg = load_config(str(CONFIG))
    m5 = load_broker_m5(DATA_FILE)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for rr in RRS:
        trades = run_backtest(
            m5,
            fractal_left=cfg.strategy.fractal_left,
            fractal_right=cfg.strategy.fractal_right,
            sr_lookback=cfg.strategy.sr_lookback,
            sl_buffer=cfg.strategy.sl_buffer,
            rr_multiple=rr,
        )
        # Enriches every trade dict in place with pnl_points + r_multiple.
        stats = trade_stats(
            trades, contract_size=cfg.trading.contract_size, lot=cfg.trading.lot
        )

        # Per-run CSV in the CLI's trades.csv shape (rounded at the boundary).
        if trades:
            df_trades = pd.DataFrame(trades)[TRADE_COLUMNS]
            for col in ("entry", "sl", "tp", "exit_price", "pnl_points"):
                df_trades[col] = df_trades[col].round(2)
            df_trades["r_multiple"] = df_trades["r_multiple"].round(4)
        else:
            df_trades = pd.DataFrame(columns=TRADE_COLUMNS)
        df_trades.to_csv(OUT_DIR / f"trades_{rr}.csv", index=False)

        avg_win_r = avg_r_of(trades, "TP")
        avg_loss_r = avg_r_of(trades, "SL")
        stats["avg_win_r"] = avg_win_r
        stats["avg_loss_r"] = avg_loss_r
        with (OUT_DIR / f"stats_{rr}.json").open("w") as fh:
            json.dump(stats, fh, indent=2)
            fh.write("\n")

        rows.append((rr, stats, avg_win_r, avg_loss_r))

    # Run context, for reproducibility.
    print(f"data: {DATA_FILE.relative_to(ROOT)}")
    print(f"span: {m5.index[0]} -> {m5.index[-1]}  ({len(m5):,} bars)")
    print(
        f"config: {CONFIG.relative_to(ROOT)}  "
        f"fractal_left={cfg.strategy.fractal_left} "
        f"fractal_right={cfg.strategy.fractal_right} "
        f"sr_lookback={cfg.strategy.sr_lookback} "
        f"sl_buffer={cfg.strategy.sl_buffer}  "
        f"contract_size={cfg.trading.contract_size} lot={cfg.trading.lot}"
    )
    print()
    print("| rr_multiple | trades | win% | avg win R | avg loss R | net R | PF | max DD USD |")
    print("|---|---|---|---|---|---|---|---|")
    for rr, stats, avg_win_r, avg_loss_r in rows:
        label = f"{rr} (baseline)" if rr == 1.0 else f"{rr}"
        print(
            f"| {label} | {stats['total_trades']} | {stats['win_rate']:.1%} "
            f"| {avg_win_r:.3f} | {avg_loss_r:.3f} | {stats['avg_r']:.3f} "
            f"| {stats['profit_factor']:.2f} | ${stats['max_drawdown_usd']:.0f} |"
        )
    print()
    print(f"artifacts: {OUT_DIR.relative_to(ROOT)}/trades_{{rr}}.csv + stats_{{rr}}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
