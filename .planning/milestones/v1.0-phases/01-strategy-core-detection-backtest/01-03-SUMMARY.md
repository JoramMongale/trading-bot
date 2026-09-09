---
phase: 01-strategy-core-detection-backtest
plan: 03
subsystem: backtest
tags: python, pandas, numpy, pytest, backtest, event-loop, stats, cli, histdata

# Dependency graph
requires:
  - phase: research
    provides: verified event-loop conventions (RQ2), stats design, histdata M1 format, no MT5/TA-Lib
  - phase: 01-01
    provides: config loader ([strategy]/[trading] params), file logger (SAFE-02), load_histdata_csv + resample_to_m5
  - phase: 01-02
    provides: detect_swings / support_resistance / detect_setups (shared pure strategy module)
provides:
  - run_backtest() — two-pass event-loop backtest over the SHARED strategy module (SAFE-01)
  - trade_stats() — per-trade P&L + aggregate stats (SAFE-01)
  - `python -m trading_bot.cli backtest` — one-command backtest: per-trade CSV + stats + decision log (SAFE-01/02, EXEC-03)
  - scripts/gen_sample_data.py — deterministic synthetic histdata M1 CSV (1 known winning trade)
  - 12 event-loop convention tests incl. golden integration + real-data run (340 trades, 2025-01 → 2026-07, 13 months)
affects: phase 2 (live bot reuses run_backtest conventions + strategy chain; EXEC-01/02)

# Tech tracking
tech-stack:
  added: []  # pandas/numpy/pytest already present from 01-01/01-02
  patterns:
    - "Pass A vectorized signals -> Pass B per-bar event loop (RESEARCH.md Pattern 1)"
    - "one active trade at a time; skip+log setups during open trade/pending order"
    - "pessimistic intrabar ordering: SL checked before TP"
    - "fill = max(entry, open) on first bar with high >= entry (gap-open fills at open)"
    - "signal on final bar -> pending order never fills -> no trade record (no lookahead)"
    - "trade record appended EXACTLY ONCE at exit; OPEN trade closed at last close"
    - "trade state in plain dicts; pandas 3.0 .iloc[t] rows read-only, never mutated"
    - "on_event callback emits every decision (setup_detected/setup_skipped/order_filled/trade_closed) for SAFE-02"

key-files:
  created: [src/trading_bot/backtest/__init__.py, src/trading_bot/backtest/engine.py, src/trading_bot/backtest/stats.py, src/trading_bot/cli.py, scripts/gen_sample_data.py, tests/test_backtest.py]
  modified: []

key-decisions:
  - "OPEN trades excluded from wins/losses/win_rate but INCLUDED in net P&L (plan test 7 overrode RESEARCH.md's closed-only net)"
  - "CLI rounds trades.csv prices/P&L to 2 dp and r_multiple to 4 dp; printed stats to 2 dp — display precision at the CLI boundary only; engine/stats math stays at binary float precision"
  - "avg_trade_bars = mean(exit_idx - entry_idx) from index positions (exact bar count even with data gaps)"
  - "engine emits events via optional on_event callback; CLI wires it to log_decision (SAFE-02)"
  - "real-data run = 13 months (full 2025 + 2026-07): 340 setups → ~18/month (≈215/yr), squarely in RESEARCH.md OQ2's 'dozens to hundreds'; earlier 1-month run (17 setups, July 2026) superseded — defaults unchanged, no parameter-tuning action taken"

patterns-established:
  - "CLI flow: load_config -> glob *.csv -> load_histdata_csv each -> concat/dedupe/sort -> slice -> resample_to_m5 -> run_backtest -> trade_stats -> trades.csv + stdout stats + backtest.log"
  - "decision log events: backtest_run, setup_detected, setup_skipped, order_filled, trade_closed, backtest_stats"
  - "graceful failure: no CSVs -> exit 1 with 'download histdata' message; no bars after filter -> exit 1"

# Metrics
duration: 2 sessions (engine/stats/CLI + real-data run)
completed: 2026-08-10
---

# Phase 1 Plan 3: Backtest Engine, Stats, CLI + Real-Data Validation Summary

**Event-loop backtester over the shared strategy module, aggregate stats, one-command CLI, and a real-data run on 13 months of XAUUSD M1 (full 2025 + July 2026) — 12 new convention tests + 33 total green; validated end-to-end with no MT5 anywhere in the path**

## Performance

- **Started:** 2026-08-10T19:35Z (Task 1)
- **Completed:** 2026-08-10T20:10Z (Task 3 — real-data run)
- **Tasks:** 3 (engine+stats test-first; CLI+sample E2E; real-data checkpoint)
- **Files modified:** 6 (4 source, 1 script, 1 test)
- **Commits:** `3401d48` (engine+stats+tests), `5a0a79c` (CLI+sample), `2cef4ce` (docs progress), `917c97a` (docs summary, 1-month run), `<(summary commit>` (docs summary, full-year run)

## Implementation Summary

### `src/trading_bot/backtest/engine.py` — `run_backtest()`

```python
def run_backtest(
    df,                          # OHLCV DataFrame, datetime index
    fractal_left: int = 2,
    fractal_right: int = 2,
    sr_lookback: int = 60,
    sl_buffer: float = 0.01,
    on_event: Optional[Callable[[dict], None]] = None,
) -> list[dict[str, Any]]
```

- **Pass A** (vectorized, no lookahead): `df.copy()` → `support_resistance(detect_swings(df, left, right), sr_lookback)` → `detect_setups(df)` — the SAME pure strategy chain the live bot calls (SAFE-01 literal).
- **Pass B** (per-bar event loop, one trade at a time):
  1. Manage the open trade first — SL before TP intrabar (pessimistic).
  2. Fill the pending Buy Stop from bar t+1 onward when `high >= entry`, at `max(entry, open)` (gap-open fills at open); a filled/attempted bar never also arms a new setup.
  3. New setup → arm `entry = resistance`, `sl = support - sl_buffer`, `tp = entry + (entry - sl)` (exact 1:1, STRAT-03).
- Trade record: `entry_time, entry, sl, tp, exit_time, exit_price, exit_reason` (+ internal `entry_idx/exit_idx` used for `avg_trade_bars`; not exported to CSV). Appended **exactly once, at exit**.
- End of data: open trade → `exit_reason="OPEN"`, `exit_price = last close`.
- Signal on the final bar arms a pending order that never fills → **no trade record** (no lookahead fill).
- `on_event` callback emits `setup_detected` / `setup_skipped` (reason=`open_trade`|`pending_order`) / `order_filled` / `trade_closed` dicts for SAFE-02 logging. (Addition beyond the plan's field list — required to wire the CLI decision log.)

### `src/trading_bot/backtest/stats.py` — `trade_stats()`

```python
def trade_stats(trades: list[dict], contract_size: float = 100.0, lot: float = 0.01) -> dict[str, float]
```

- Enriches each trade with `pnl_points = exit_price - entry` and `r_multiple = pnl_points / (entry - sl)` (NaN when risk == 0).
- Returns: `total_trades` (closed), `open_trades`, `wins`, `losses`, `win_rate`, `net_pnl_points`, `net_pnl_usd` (points × contract × lot), `avg_r`, `profit_factor` (gross_win/gross_loss; `inf` when gross_loss == 0), `max_drawdown_usd` (closed-trade equity `cumsum` vs `cummax`), `avg_trade_bars` (mean `exit_idx - entry_idx`).
- Empty trade list → all zeros (`profit_factor` 0.0, not inf).
- Conventions: wins/losses/win_rate/avg_r/profit_factor/max_drawdown from **closed** trades; OPEN trades counted in **net P&L** only.

### `src/trading_bot/cli.py` — `python -m trading_bot.cli backtest`

```python
def main(argv=None) -> int   # exit 0 success, 1 no-data/config error, 2 bad args
```

- Flags: `--config` (default `config/config.toml`), `--data-dir` (default config `[data] raw_dir`), `--start/--end` (inclusive start, exclusive end), `--quick N` (first N resampled M5 bars).
- Flow: `load_config` → glob `*.csv` in data dir → none: print "Download XAUUSD M1 ASCII CSVs from histdata.com…" + `exit(1)` → load each with `load_histdata_csv`, concat, drop duplicated index, sort → optional date slice → optional `--quick` slice → `resample_to_m5` → `run_backtest` (params from `[strategy]`) → `trade_stats` (params from `[trading]`).
- Outputs: `output/trades.csv` (entry_time, entry, sl, tp, exit_time, exit_price, exit_reason, pnl_points, r_multiple; prices/P&L rounded 2 dp, r_multiple 4 dp), aligned stats table to stdout, full decision log to `output/backtest.log`.
- No MT5 imports anywhere (verified, see verification).

### `scripts/gen_sample_data.py`

Deterministic synthetic histdata M1 CSV (60 M1 rows → 12 M5 buckets, `YYYYMMDD HHMMSS;O;H;L;C;V`) engineered to produce exactly ONE known winning trade.

## Golden Sample — Expected vs Actual (matched exactly)

| Field | Expected (plan) | Actual | Match |
|-------|-----------------|--------|-------|
| Trades | 1 | 1 | ✓ |
| Entry | 101.10 | 101.10 | ✓ |
| SL | 100.09 | 100.09 | ✓ |
| TP | 101.91 | 101.91 | ✓ |
| Exit price | 101.91 | 101.91 | ✓ |
| Exit reason | TP | TP | ✓ |
| pnl_points | 0.81 | 0.81 | ✓ |
| net_pnl_usd | 0.81 (0.81 × 100 × 0.01) | 0.81 | ✓ |
| Wins | 1 | 1 | ✓ |
| Setup bars | setup at M5 idx 6, fill at idx 7 | same | ✓ |

Swing confirmation matched the hand-trace: swing high 101.00 confirmed at idx 4 → resistance 101.00; swing low 100.10 confirmed at idx 6 → support 100.10; setup fired at idx 6 (close 101.05 > 101.00, prior close 100.70 ≤ 101.00); gap-open fill at idx 7 `max(101.00, 101.10) = 101.10`; TP at idx 9 (high 102.05 ≥ 101.91). No other setups fired (re-trigger self-disabled).

## Real-Data Run (DAT_ASCII_XAUUSD_M1_2025.csv + DAT_ASCII_XAUUSD_M1_202607.csv)

Single clean run (sample CSV moved out of `data/raw/` so only real data was loaded; restored afterwards). Exit 0.

| Stat | Value |
|------|-------|
| Data span | **2025-01-01 18:00 → 2026-07-31 16:55** (full 2025 + July 2026 = 13 months) |
| M1 rows loaded | 385,089 |
| M5 bars | 77,038 |
| Signals (`setup_detected`) | **340** |
| Setups skipped (open trade / pending order) | 1,279 |
| Orders filled | 340 |
| Total trades (closed) | 339 (206 TP / 133 SL) |
| Open trades | 1 (OPEN at last close) |
| Win rate | 60.8% |
| Net P&L (points) | +1,021.91 |
| Net P&L (USD) | +1,021.91 (× 100 oz × 0.01 lot) |
| Avg R multiple | 0.14 |
| Profit factor | 1.29 |
| Max drawdown (USD) | 271.44 |
| Avg trade duration (bars) | 159.07 (~13 hours) |

`output/trades.csv` = 340 rows (339 closed + 1 OPEN); `output/backtest.log` populated with `event=backtest_run/setup_detected/setup_skipped/order_filled/trade_closed/backtest_stats`.

### Sanity check — RESEARCH.md open question #2 (signal count)

**Resolved.** 340 setups over 13 months (2025-01 → 2026-07) → ~18/month, ≈215/year — squarely in the "dozens to hundreds over 12-24 months" range RESEARCH.md expected, and consistent with the earlier 1-month run's projection (~17/month → ~200/year). The 2/2/60 fractal defaults produce a plausible, non-trivial signal density on real XAUUSD M5. **No parameter-tuning action taken; defaults unchanged.** The earlier 1-month run (July 2026 only) is superseded by this 13-month run.

### Real-data observations (recorded, no code change)

- **60.8% win rate with a modestly positive edge (PF 1.29, +1,021.91 pts) over the full year** — a material reversal from the 1-month run's -94.49 pts, confirming the 1-month sample was too short to judge edge. The win-rate/R asymmetry from the 1-month run persists and explains the modest magnitude: `avg_r ≈ 0.14` because TP exits fill at `max(entry, open)` — often above resistance, so most winners capture 0.44–1.0R — while SL exits are always exactly -1R. Consistent math: `0.608 × ~0.87R − 0.392 × 1R ≈ +0.14R`.
- **Interpretation: a real, but thin, positive edge.** PF 1.29 and +1,021.91 points on 339 closed trades (~3.0 pts/trade) is consistent across 13 months but should not be read as strong — it does not model spread (histdata is bid-only; `spread_assumption=0`, RESEARCH.md open question #4). A realistic ~$0.30 broker spread would erode most of the edge.
- **One trade open at end of data** (2026-07-29 entry, closed at last close 2026-07-31) is included in net P&L per the plan's test-7 convention.
- **1-month run superseded:** the earlier July-2026-only run (16 closed trades, -94.49 pts) is no longer representative; this 13-month run replaces it.

## Test Results

- `tests/test_backtest.py`: **12 tests** — fill timing (no entry at signal bar; fill at t+1), gap-open fill at open, exact 1:1 R:R on every record, pessimistic SL-before-TP on a both-touched bar, one-trade-at-a-time (second setup skipped → 1 trade), signal-on-final-bar → 0 trades, OPEN exit at last close (included in net P&L, excluded from win/loss), stats math (points/USD/win_rate/profit_factor/max_drawdown exact), golden integration (full hand-known record list).
- Full suite: `.venv/bin/pytest -q -W error::FutureWarning` → **33 passed, exit 0** (0.33s), no pandas 3.0 FutureWarnings.
- `grep -rn "MetaTrader5\|mt5\|talib" src/` → **nothing found** (Phase 1 is MT5-free by construction).
- Graceful no-data path verified in Task 2: empty data dir → exit 1 with the human-readable "download histdata" message.

## Deviations from Plan / RESEARCH.md

1. **OPEN trades included in net P&L** (RESEARCH.md code example computed net from closed trades only). Plan Task 1 test #7 mandates OPEN counted in net P&L; plan test list is authoritative — stats.py computes `net_pnl_*` over ALL trades, all other aggregates over closed. Documented in STATE.md decisions.
2. **trades.csv / printed stats rounded to 2 dp, r_multiple 4 dp (CLI only)** — display precision at the CLI boundary; engine/stats math stays full precision. XAUUSD quotes to 2 dp; binary-float artifacts (101.91 − 101.10 ≠ 0.81) never appear in output.
3. **`on_event` callback added to `run_backtest()`** (not in the plan's field list) — required for the CLI's SAFE-02 decision log; zero effect on trade records. Internal `entry_idx`/`exit_idx` fields added for `avg_trade_bars`; not written to CSV.
4. ~~Real-data span was 1 month (2026-07 only)~~ **Resolved** — user supplied the full 2025 file plus 2026-07, bringing coverage to 13 months (within the 12-24 target). The 13-month run supersedes the original 1-month run; the earlier numbers (17 setups, 16 closed trades, -94.49 pts) are retained only as history.

## Issues Encountered

- None in code. The only operational wrinkle was the sample CSV co-residing in `data/raw/` (CLI globs all `*.csv`); resolved by moving it out for the real-data run and restoring it afterwards.

## User Setup Required

- Done: full 2025 + 2026-07 XAUUSD M1 downloaded (13 months, within the 12-24 month target) and validated in the real-data run above. Optional follow-up: extend coverage into 2024 to reach 24 months, and re-run with a `spread_assumption` > 0 before Phase 2 to test edge robustness (RESEARCH.md open question #4).

## Next Phase Readiness

- Phase 1 deliverable complete: one command (`python -m trading_bot.cli backtest`) runs the SAME strategy module over historical bars → per-trade CSV + aggregate stats (SAFE-01) + full decision log (SAFE-02), all params from config (EXEC-03 partial), no MT5.
- Phase 2 (live bot) reuses the exact `detect_swings → support_resistance → detect_setups` chain and the event-loop fill/SL/TP conventions from engine.py.

---
*Phase: 01-strategy-core-detection-backtest*
*Completed: 2026-08-10*
