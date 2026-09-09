# 007 — BTC on its own cent account: EXECUTED on Windows

**Status:** complete — 2026-08-27

The 007 design (a separate account so BTC's risk is isolated from gold) was
written for the macOS container/bridge world. On Windows it landed natively:

| | gold | bitcoin (this task) |
|---|---|---|
| account | 161693049 @ Exness-MT5Real21 (USC) | **161700182 @ Exness-MT5Real21 (USC)** |
| terminal | `C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe` | `C:\MT5-Gold\terminal64.exe` |
| symbol | XAUUSDc | **BTCUSDc** |
| magic | 77020 | 77021 |
| risk | 1% x 1 slot | 0.5% x 2 slots (per-account now) |

## What changed

- `config/config-btc.toml`: `symbol = "BTCUSDc"` (was `BTCUSDm` — the
  Standard-account name; this cent terminal quotes only `BTCUSDc`),
  `contract_size = 1.0` (was gold's 100; backtest money conversion, live risk
  reads `trade_tick_value`), header comments rewritten for the new account.
  `terminal_path` was already correct (`C:\MT5-Gold\terminal64.exe`).
- Live bot restarted on the new account: **preflight READY**, median setup
  affordable at 0.02 lots / 0.5% cap. The `below_min_lot` refusal on the old
  $31.38 standard account (a ~$700–930 stop at 0.01 minimum) is gone.
- `monitor_trade.py` fixed the wrong-terminal bug (same as health_check /
  dashboard): attaches per-config via `health_check._init_terminal`, so btc
  now reports 161700182, not gold's 161693049.

## The backtest (honest)

- `scripts/fetch_broker_history.py` made Windows-native (native package first,
  bridge fallback, per-config terminal_path) — pulled `BTCUSDc` M5 to
  `data/processed/BTCUSDc_M5_broker.csv` (100,000 bars / 347 days).
- Backtest CLI gained `--m5-csv` to feed an already-M5 frame; added
  `config/config-btc-backtest.toml` (sl_buffer 0.10 = 10*point per the
  multi-instrument convention).
- **Result:** 660 closed trades, **avg R −0.043, t=−1.20, PF 0.87**, win 52.4%,
  max DD $785. No edge — reproduces the −0.033R/−0.049R prior. rr=2.0 is worse
  (−0.103R). Report: `docs/btc-backtest-report.md`.

## What it does NOT do

A cent account fixes the size problem, not the edge problem. BTC is a machinery
test — it can now place trades, and the measurement says they lose. Nothing here
claims otherwise.
