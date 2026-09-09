# Phase 2: Live Execution — MT5 Order Placement + Safety — Research

**Researched:** 2026-08-11
**Domain:** MT5 Python API integration — live bar subscription, Buy Stop placement, demo/live safety
**Confidence:** HIGH for the abstraction/architecture + macOS-verifiable parts; MEDIUM for real-terminal behavior (cannot execute the Windows-only package on this machine)

## Platform Constraint (LOCKED — from Phase 1 research, verified against PyPI + mql5.com)

- The `MetaTrader5` pip package is **Windows-only** — every published wheel is `win_amd64`. It cannot be installed on this macOS dev machine, and the MT5 terminal itself only runs under Windows.
- **Consequence for this phase:** the live-execution layer MUST be a broker abstraction:
  1. `BrokerClient` interface + typed dataclasses (testable everywhere)
  2. `MT5Broker` — the real adapter, with a **guarded/lazy import** so the module loads on macOS; methods raise `BrokerUnavailableError` when `MetaTrader5` is not importable. Unit-tested on macOS by injecting a fake `MetaTrader5` module into `sys.modules` (exercises request-building, retcode parsing, bar conversion — everything except the actual DLL round-trip).
  3. `SimulatedBroker` — in-memory rates + order ledger, so the engine + dry-run + E2E replay run fully on macOS.
  4. `DryRunBroker` — wraps any broker, overrides `place_buy_stop` to log the exact request instead of sending (SAFE-03 "dry-run places no orders but logs exactly what would be sent").
- Real-terminal verification (connect, live bars, demo order) is therefore a **human checkpoint on Windows** (plan 02-06). Everything else is verified on macOS.

## MT5 Python API contract (from mql5.com python_metatrader5 docs)

### Connection / status
- `mt5.initialize(path=None, login=0, password="", server="", timeout=None)` → bool. `mt5.shutdown()`.
- `mt5.terminal_info()` → namedtuple: `.connected`, `.trade_allowed`, `.tradeapi_disabled`.
- `mt5.account_info()` → namedtuple: `.login`, `.server`, `.currency`, `.balance`, `.trade_mode`.
  - `trade_mode`: `ACCOUNT_TRADE_MODE_DEMO` (0), `ACCOUNT_TRADE_MODE_CONTEST` (1), `ACCOUNT_TRADE_MODE_REAL` (2) — **this is the demo/live discriminator for SAFE-03**.
- `mt5.last_error()` → `(code, message)` — always call after a failed call for the log.

### Bars (EXEC-01)
- `mt5.copy_rates_from_pos(symbol, timeframe, start_pos, count)` → numpy recarray (fields `time, open, high, low, close, tick_volume, spread, real_volume`) or `None` on failure.
  - `time` is **unix seconds** → `pd.to_datetime(rates["time"], unit="s")`.
  - **Position 0 is the currently-forming bar.** Use `start_pos=1` to get only CLOSED bars — the engine must never act on a forming bar (same no-lookahead rule as the backtester).
  - Timeframe constants: `TIMEFRAME_M1`, `TIMEFRAME_M5` — map from `cfg.data.timeframe`.
  - MT5 server time is typically UTC+2/+3 for gold brokers. The live engine uses ONLY MT5 bars (never mixes with histdata EST bars), so naive timestamps are fine — documented, not converted.
- `mt5.symbol_select(symbol, True)` — must be called before rates/orders so the symbol is in MarketWatch.

### Orders (EXEC-02)
- `mt5.orders_get(symbol=...)` → tuple of TradeOrder namedtuples (active pending orders): `.ticket`, `.type` (`ORDER_TYPE_BUY_STOP` = 4), `.price`, `.sl`, `.tp`, `.volume`, `.magic`, `.symbol`, `.time_setup`. `None` if none.
- `mt5.positions_get(symbol=...)` → tuple of Position namedtuples: `.ticket`, `.symbol`, `.magic`, `.volume`, `.price_open`. `None` if none.
- `mt5.order_send(request)` → OrderSendResult: `.retcode`, `.order` (ticket), `.comment`, `.request`.

### order_send request dict for a pending Buy Stop (STRAT-03 + EXEC-02)
```python
request = {
    "action": mt5.TRADE_ACTION_PENDING,      # 5 — place a pending order
    "symbol": symbol,                        # e.g. "XAUUSD"
    "volume": lot,                           # cfg.trading.lot
    "type": mt5.ORDER_TYPE_BUY_STOP,         # 4
    "price": entry,                          # resistance (must be > current ask)
    "sl": sl,                                # support - sl_buffer
    "tp": tp,                                # entry + (entry - sl)  — exact 1:1 R:R
    "deviation": deviation,                  # max slippage, points (cfg.live.deviation)
    "magic": magic,                          # cfg.live.magic_number (EXEC-03)
    "comment": comment,                      # bot identifier
    "type_time": mt5.ORDER_TIME_GTC,         # 0 — good till cancelled
    "type_filling": filling,                 # from symbol_info().filling_mode: IOC(2) else RETURN(4)
}
result = mt5.order_send(request)
```
- Success retcodes: `TRADE_RETCODE_DONE` (10009) and `TRADE_RETCODE_PLACED` (10008). Anything else → raise `BrokerRejectedError` carrying retcode + comment for the decision log (`order_rejected`).
- `mt5.symbol_info(symbol).filling_mode` is a bitmask: `SYMBOL_FILLING_IOC` = 2, `SYMBOL_FILLING_RETURN` = 4. Prefer IOC, fall back to RETURN.
- Buy Stop `price` must exceed current ask by at least the symbol's stop level; XAUUSD is quoted to 2 decimals (`digits=2`) — deviation in points (1 point = 0.01).

## Architecture

```
cli.py (live subcommand)
  └─ create_broker(cfg) ── mode=dry-run → DryRunBroker(MT5Broker if importable else SimulatedBroker)
                           mode=demo/live → MT5Broker (safety guard may block)
  └─ LiveEngine(cfg, broker, logger)
        run_once(): fetch CLOSED bars (start_pos=1) → shared strategy
                    (detect_swings → support_resistance → detect_setups)
                    → setup on LAST closed bar?
                    → dedup (pending-equivalent / open position / same-bar)
                    → safety.verify_execution_allowed() (SAFE-03)
                    → broker.place_buy_stop() → log order_placed/rejected/skipped
broker/base.py        BrokerClient ABC + OrderRequest/OrderResult/PendingOrder/Position/AccountInfo + exceptions
broker/mt5.py         MT5Broker (guarded import; fake-MT5 unit tests)
broker/simulated.py   SimulatedBroker (seeded rates, cursor, order ledger)
broker/dry_run.py     DryRunBroker wrapper (logs would-send, never sends)
live/safety.py        verify_execution_allowed(cfg, account) — SAFE-03
```

## Key conventions carried from Phase 1 (must match the backtester exactly)

- **Order arithmetic is copied from `backtest/engine.py` verbatim**: `entry = resistance`, `sl = support - sl_buffer`, `tp = entry + (entry - sl)` — SAFE-01 (same strategy, same order math).
- **No-lookahead**: swings are confirmed only after the right window closes (already inside `detect_swings`); engine reads only the LAST CLOSED bar's `setup` flag.
- **One-at-a-time semantics** (backtest parity): skip a setup if an equivalent Buy Stop is already pending, or a position for this magic is open, or the same bar was already processed (tracked via `last_seen_time`).
- **Decision logging** via existing `log_decision` (SAFE-02): events `live_start`, `bar_checked`, `setup_detected`, `order_skipped`, `order_placed`, `order_rejected`, `safety_blocked`, `live_stop`.
- **Graceful unavailability** (EXEC-01): MT5 not importable / terminal not connected → clear `BrokerUnavailableError` message + non-zero exit (mirrors the backtest CLI's "no CSV files found" pattern).

## Decisions for this phase

| Decision | Rationale |
|----------|-----------|
| Broker abstraction + SimulatedBroker + DryRunBroker | MT5 package is Windows-only (locked); engine/E2E must be fully testable on macOS |
| Adapter unit-tested via fake `MetaTrader5` module in `sys.modules` | Only way to test request-building/retcode logic on this machine |
| `copy_rates_from_pos(..., start_pos=1, ...)` — closed bars only | No-lookahead parity with backtester; never act on forming bar |
| `order_send` success = retcode in {DONE, PLACED}; else `BrokerRejectedError` + log | Explicit failure surfacing for the decision log |
| Live engine uses ONLY MT5 bars (naive server time), never mixes with histdata | Timezone consistency; relative strategy math unaffected |
| `safety.verify_execution_allowed`: real account blocked unless `live.enabled`; mode=demo + real account blocked; dry-run never sends | SAFE-03 demo-only enforcement, explicit opt-in to live |
| Real-terminal verification = human checkpoint on Windows (plan 02-06) | Physically impossible on macOS; deferred to user's MT5 environment |
| Live bar subscription = polling `copy_rates_from_pos` every `poll_interval` | Pragmatic MT5-Python pattern; no tick plumbing needed for M5 setups |
