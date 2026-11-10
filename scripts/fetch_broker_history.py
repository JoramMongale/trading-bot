"""Pull M5 history straight from the connected MT5 terminal.

The histdata.com CSVs in data/raw/ are a manual browser download (see
HISTDATA_URL in cli.py), which is why the set went stale at 2026-07 and why a
73h gap in 2025-04 went unnoticed. The broker already has the data and the
terminal is already connected, so this needs no download, no account, and no
auth — and it returns the BROKER's instrument (XAUUSDm, BTCUSDc, ...), the one
the bot actually trades, rather than histdata's generic XAUUSD.

    .venv\\Scripts\\python scripts\\fetch_broker_history.py [--out PATH] [--pages N]
    .venv\\Scripts\\python scripts\\fetch_broker_history.py --config config\\config-btc.toml

The terminal serves at most ~50k bars per call and rejects larger counts
outright ("Invalid params"), so history is paged backwards from an anchor
until it stops returning new bars.

Transport: native MetaTrader5 package first (Windows), falling back to the
siliconmetatrader5 RPC bridge (macOS/Linux). The terminal is selected by the
config's [live] terminal_path, exactly like the live adapter — a bare
initialize() on a multi-terminal machine attaches to whichever install it
finds first, which would silently fetch the WRONG account's data.
"""

import argparse
import json
from pathlib import Path

import pandas as pd

from trading_bot.config import load_config


def _init_mt5(cfg):
    """Return an initialized MetaTrader5 module/bridge for the config's own
    terminal: native package first, silicon RPC bridge fallback."""
    from trading_bot.broker.base import BrokerUnavailableError
    from trading_bot.broker.mt5 import _load_mt5, _load_silicon_bridge

    bridge = getattr(cfg.live, "bridge", "auto")
    path = getattr(cfg.live, "terminal_path", "") or ""
    try:
        mt5 = _load_mt5()
    except BrokerUnavailableError:
        if bridge == "native":
            raise
        mt5 = _load_silicon_bridge(cfg.live.bridge_host, cfg.live.bridge_port)
    kwargs = {"path": path, "portable": True} if path else {}
    if not mt5.initialize(**kwargs):
        raise BrokerUnavailableError(
            f"initialize() failed: {mt5.last_error()}"
        )
    return mt5


def _page(mt5, symbol, anchor, chunk):
    """One page of M5 bars; retries transient terminal failures once.

    A persistent ("Terminal: Call failed") result is how MT5 reports that no
    history exists before the anchor — the terminal's data simply runs out.
    Returns the raw recarray (or None when genuinely exhausted).
    """
    if anchor is None:
        raw = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 1, chunk)
    else:
        raw = mt5.copy_rates_from(symbol, mt5.TIMEFRAME_M5, anchor, chunk)
    if raw is None or len(raw) == 0:
        import time

        time.sleep(3)
        if anchor is None:
            raw = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 1, chunk)
        else:
            raw = mt5.copy_rates_from(symbol, mt5.TIMEFRAME_M5, anchor, chunk)
    return raw


def spec_from_terminal(mt5, symbol: str, spreads: pd.Series) -> dict:
    """The spec sidecar the backtest reads (data/loader.py load_instrument_spec):
    broker symbol facts plus the median bar spread, in points."""
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"symbol_info({symbol}) returned None: {mt5.last_error()}")
    acct = mt5.account_info()
    spreads = pd.to_numeric(spreads, errors="coerce").dropna()
    spreads = spreads[spreads > 0]
    return {
        "symbol": info.name,
        "digits": int(info.digits),
        "point": float(info.point),
        "trade_tick_size": float(info.trade_tick_size),
        "trade_tick_value": float(info.trade_tick_value),
        "trade_contract_size": float(info.trade_contract_size),
        "volume_min": float(info.volume_min),
        "volume_step": float(info.volume_step),
        "spread_points_median": float(spreads.median()) if len(spreads) else float(info.spread),
        "account_currency": getattr(acct, "currency", "") if acct is not None else "",
    }


def fetch(cfg, symbol: str, pages: int, chunk: int = 50_000,
          spec_path: str | None = None) -> pd.DataFrame:
    """Page back through ``symbol`` M5 history on the config's terminal.

    With ``spec_path``, also writes the spec sidecar JSON there."""
    from trading_bot.broker.base import BrokerUnavailableError

    mt5 = _init_mt5(cfg)
    try:
        if not mt5.symbol_select(symbol, True):
            code, msg = mt5.last_error()
            raise BrokerUnavailableError(
                f"symbol_select({symbol}) failed: {code} {msg}"
            )
        frames, anchor = [], None
        for i in range(pages):
            raw = _page(mt5, symbol, anchor, chunk)
            if raw is None or len(raw) == 0:
                print(f"  page {i}: exhausted ({mt5.last_error()})")
                break
            df = pd.DataFrame(raw)
            df["time"] = pd.to_datetime(df["time"], unit="s")
            frames.append(df)
            oldest = df["time"].iloc[0]
            print(f"  page {i}: {len(df):>6,} bars  {oldest} -> {df['time'].iloc[-1]}")
            if anchor is not None and oldest >= anchor:
                print("  (no further history)")
                break
            anchor = oldest - pd.Timedelta(minutes=5)
            if len(df) < chunk:
                break
        if spec_path and frames:
            spreads = pd.concat(frames).get("spread", pd.Series(dtype=float))
            spec = spec_from_terminal(mt5, symbol, spreads)
            Path(spec_path).write_text(json.dumps(spec, indent=2), encoding="utf-8")
            print(f"  spec: {spec}")
    finally:
        try:
            mt5.shutdown()
        except Exception:  # noqa: BLE001 - a dead terminal may not answer
            pass

    out = (
        pd.concat(frames)
        .drop_duplicates(subset="time")
        .sort_values("time")
        .set_index("time")[["open", "high", "low", "close"]]
        .astype(float)
    )
    out.index.name = "time"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/config.toml",
                    help="which bot config drives the terminal/symbol "
                         "(default config/config.toml)")
    ap.add_argument("--symbol", default=None,
                    help="override the broker symbol (default: [live] symbol, "
                         "falling back to [data] symbol)")
    ap.add_argument("--out", default=None,
                    help="output CSV path (default: data/processed/<SYMBOL>_M5_broker.csv)")
    ap.add_argument("--pages", type=int, default=8)
    ap.add_argument("--spec", action="store_true",
                    help="also write <out>.spec.json (symbol facts + median spread) "
                         "for the backtest's [data] spec_file")
    args = ap.parse_args()

    cfg = load_config(args.config)
    # The BROKER's name for the instrument, not the vendor's. Not
    # live_symbol(cfg): that returns the vendor name in dry-run mode, and the
    # committed config sits in dry-run.
    symbol = args.symbol or cfg.live.symbol or cfg.data.symbol
    out = args.out or f"data/processed/{symbol}_M5_broker.csv"
    terminal = cfg.live.terminal_path or f"{cfg.live.bridge_host}:{cfg.live.bridge_port}"
    print(f"fetching {symbol} M5 via {terminal}")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    spec_path = str(Path(out).with_suffix(".spec.json")) if args.spec else None
    df = fetch(cfg, symbol, args.pages, spec_path=spec_path)
    if df.empty:
        print("no bars fetched — is the terminal logged in and the symbol listed?",
              file=__import__("sys").stderr)
        return 1
    df.to_csv(out)
    print(f"\nsaved {len(df):,} bars -> {out}")
    if spec_path:
        print(f"saved spec -> {spec_path}")
    print(f"span  {df.index[0]} -> {df.index[-1]} "
          f"({(df.index[-1] - df.index[0]).days} days)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
