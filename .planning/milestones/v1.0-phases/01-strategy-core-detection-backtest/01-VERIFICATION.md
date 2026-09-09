---
phase: 01-strategy-core-detection-backtest
verified: 2026-08-11T06:46:32Z
status: passed
score: 12/12
re_verification:
  previous_status: gaps_found
  previous_score: 11/12
  gaps_closed:
    - "Backtest per-trade records follow the documented conventions — exact 1:1 R:R on every record (SAFE-01), and the phase success criterion 'user can point at any detected signal in the log and see entry/SL/TP that match the rules'"
  gaps_remaining: []
  regressions: []
---

# Phase 1: Strategy Core — Detection + Backtest Verification Report

**Phase Goal:** A working, validated strategy engine that detects the breakout setup on historical XAUUSD data and reports trade stats.
**Verified:** 2026-08-11T06:46:32Z
**Status:** passed
**Re-verification:** Yes — after gap closure (plans 01-04 + 01-05)

## Goal Achievement

### Observable Truths (12 must-haves)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Project installs editable; pytest discovers tests (src/ importable) | ✓ VERIFIED | `.venv/bin/pip show trading-bot` → `Editable project location: /Users/joram/projects/trading-bot`; `.venv/bin/pytest -q -W error::FutureWarning` → **39 passed** (0.49s), up from 33 pre-gap-closure |
| 2 | All strategy parameters editable in config/config.toml → typed validated config | ✓ VERIFIED | `config.toml` has `[data]/[strategy]/[trading]/[backtest]` (sr_lookback=60, rr_multiple=1.0, sl_buffer=0.01, fractal_left/right=2); `load_config()` returns frozen dataclasses; `timeframe="M15"` → `ValueError: data.timeframe='M15' is invalid`; missing file → `FileNotFoundError` (re-tested live) |
| 3 | Every backtest decision written to file by logging utility (SAFE-02) | ✓ VERIFIED | output/backtest.log has **18,341** structured `event=` lines; latest default run logs 340 `setup_detected` + 340 `order_filled` + 340 `trade_closed` + 1,279 `setup_skipped` + 2 `data_gap_detected` + `backtest_run` + `backtest_stats` |
| 4 | histdata M1 CSVs parse and resample to M5 OHLCV exactly | ✓ VERIFIED | `loader.py` (semicolon, `%Y%m%d %H%M%S`, float dtypes) + `resample.py` (5min left/closed, first/max/min/last/sum, dropna); 3 tests pass incl. partial-bucket aggregation; 385k M1 rows → 77k M5 bars on the default run |
| 5 | Swing highs/lows from price structure (Williams fractals), NOT naive min/max (STRAT-01) | ✓ VERIFIED | swings.py: `high >= max(left)` AND `high > max(right)` (plateau last-bar semantics); 7 tests pass incl. `test_plateau_last_equal_high_bar_is_the_swing` |
| 6 | Swing point usable only after confirmation window closes — no lookahead bias | ✓ VERIFIED | `out["swing_high"] = out["swing_high_raw"].shift(right)`; `test_confirmation_shift_proves_no_lookahead` passes; levels/setups read only confirmed columns |
| 7 | Setup fires exactly when close > resistance AND prior close <= resistance (STRAT-02) | ✓ VERIFIED | signals.py: `(close > resistance) & (close.shift(1) <= resistance.shift(1))`; 4 tests pass incl. `test_retrigger_disabled_after_breakout`, `test_nan_resistance_never_fires` |
| 8 | Strategy module imports ONLY pandas/numpy (SAFE-01) | ✓ VERIFIED | `grep -rn "^import\|^from" src/trading_bot/strategy/` → pandas/numpy only; `test_strategy_modules_import_only_pandas_and_numpy` passes |
| 9 | Backtest per-trade records: fill bar t+1, fill=max(entry, open), SL before TP, exact 1:1 R:R (SAFE-01) | ✓ VERIFIED | **PREVIOUSLY FAILED — NOW CLOSED.** Convention tests pass (fill timing, gap-open fill, exact-1:1-on-record, SL-before-TP, one-trade-at-a-time, OPEN exit, golden integration). Default run (real data): **0 records with `sl < 500`, 0 with `tp < entry`**; all **340 armed orders** satisfy exact 1:1 `tp == entry + (entry - sl)` against the raw pipeline (max drift 0.0000). Success criterion: point at any `setup_detected` in the log → entry=resistance, sl=support−0.01, tp=1:1, all in the realistic 2025-26 band (2626.3–4532.85) — verified on the first 2025 setup (2626.3/2621.46/2631.14, exact 1:1) |
| 10 | One command `python -m trading_bot.cli backtest` → per-trade CSV, aggregate stats, decision log | ✓ VERIFIED | **Default command** (real data in data/raw/) → exit 0, trades.csv (340 rows + header, 9 columns), backtest.log populated, stats **match clean baseline EXACTLY**: 339 closed / 206 W / 133 L / 60.8% WR / +1021.91 pts / PF 1.29 / DD 271.44 / 340 setups |
| 11 | Whole run works on historical bars only, no MT5 anywhere (Phase 1 constraint) | ✓ VERIFIED | `grep -rn "MetaTrader5\|mt5\|talib" src/` → no matches; pyproject deps pandas/numpy only |
| 12 | With no data files present, CLI fails with clear instruction (graceful degradation) | ✓ VERIFIED | `.venv/bin/python -m trading_bot.cli backtest --data-dir /tmp/empty_xyz_123` → "no CSV files found in /tmp/empty_xyz_123." + histdata download URL on stderr, **exit 1** |

**Score:** 12/12 must-haves verified

### Gap-Closure Verification (was the contamination fixed on the DEFAULT command?)

The single failing truth from the previous verification is fixed at both root causes, and the fix holds on the default command:

| Check | Command / Evidence | Result |
|-------|--------------------|--------|
| levels.py has NO `.ffill()` | `grep -rn "ffill" src/trading_bot/strategy/` | ✅ no matches — `support_resistance` is now pure window-bounded `rolling(lookback, min_periods=1).max()/.min()` (levels.py:35-36); expired swings decay to NaN |
| Expiry-to-NaN when a swing leaves the window | `tests/test_levels.py::test_resistance_expires_to_nan_when_swing_leaves_window` + `::test_support_expires_to_nan_when_swing_leaves_window` (the previously missing test case) | ✅ both present and passing (part of the 39) |
| CLI globs only histdata files | `grep -rn "glob(" src/trading_bot/cli.py` | ✅ single glob: `data_dir.glob(f"DAT_ASCII_{symbol}_M1_*.csv")` (cli.py:99); `test_list_histdata_csves_excludes_sample` passes |
| Sample NOT in data/raw/ | `ls data/raw/*.csv` | ✅ only `DAT_ASCII_XAUUSD_M1_2025.csv` + `DAT_ASCII_XAUUSD_M1_202607.csv`; sample lives in `data/sample/sample_XAUUSD_M1_20210201.csv` |
| Data-gap warning surfaced, not silent | `grep "event=data_gap_detected" output/backtest.log` (latest run) | ✅ 2 events: `gap_from="2025-04-17 16:58:00" gap_to="2025-04-20 18:00:00" gap_hours=73.03` and `gap_from="2025-12-31 16:57:00" gap_to="2026-07-01 00:00:00" gap_hours=4351.05` — **the 2025→202607 file boundary**; stderr warning printed, exit still 0 (warning knob, not a hard error) |
| DEFAULT command clean on real data | `.venv/bin/python -m trading_bot.cli backtest` | ✅ exit 0; **0 records with `sl < 500`** (min sl = 2621.46), **0 with `tp < entry`**; stats byte-identical to the 01-03 baseline (339/206/133/60.8%/+1021.91/PF 1.29/DD 271.44/340) |
| One-trade-at-a-time no longer blocked | trades.csv `exit_reason` counts | ✅ TP 206 / SL 133 / OPEN 1 = 339 closed + 1 open, no 18-month stale-SL open trade |
| Regression test for the contamination signature | `tests/test_cli.py::test_default_backtest_produces_only_clean_trades` | ✅ co-resides the old ~$100 sample with a golden histdata file, asserts `sl < entry < tp` on every record + exact 1:1 (0.021 tolerance) + non-vacuous (`len(trades) >= 1`) + no gap warning on contiguous data |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pyproject.toml` | PEP 621, pytest pythonpath | ✓ VERIFIED | setuptools, pandas/numpy only, dev pytest, `pythonpath=["src"] testpaths=["tests"]` |
| `config/config.toml` | Phase 1 schema | ✓ VERIFIED | All 4 tables; sr_lookback=60, rr_multiple=1.0, sl_buffer=0.01, lot=0.01 |
| `src/trading_bot/config.py` | tomllib loader + validation | ✓ VERIFIED | 111 lines, frozen dataclasses, `_validate` names the bad key |
| `src/trading_bot/logging_utils.py` | file logger, key=value lines | ✓ VERIFIED | 67 lines, `get_logger` + `log_decision` |
| `src/trading_bot/data/loader.py` | histdata parser | ✓ VERIFIED | 28 lines, correct format, float dtypes |
| `src/trading_bot/data/resample.py` | M1→M5 | ✓ VERIFIED | 31 lines, exact OHLCV agg, dropna |
| `src/trading_bot/strategy/swings.py` | detect_swings | ✓ VERIFIED | 47 lines, fractal logic + confirmation shift |
| `src/trading_bot/strategy/levels.py` | support_resistance | ✓ VERIFIED (was ORPHANED-WRONG) | 37 lines, **`.ffill()` removed** — window-bounded rolling max/min; docstring now matches behaviour (expiry-to-NaN) |
| `src/trading_bot/strategy/signals.py` | detect_setups | ✓ VERIFIED | 26 lines, exact STRAT-02 |
| `src/trading_bot/backtest/engine.py` | run_backtest | ✓ VERIFIED | 151 lines, Pass A vectorized + Pass B event loop, on_event callback |
| `src/trading_bot/backtest/stats.py` | trade_stats | ✓ VERIFIED | 86 lines, all documented aggregates, empty-list guard |
| `src/trading_bot/cli.py` | one-command entry | ✓ VERIFIED | 268 lines (was 208), **DAT_ASCII-only glob** + `find_data_gaps` + gap warning; exit 0/1/2 |
| `tests/` (6 files) | 39 tests | ✓ VERIFIED | 39 pass under `-W error::FutureWarning` (pandas 3.0 clean); +6 vs. previous verification: 2 levels expiry-to-NaN, 1 glob exclusion, 2 gap detection, 1 clean-default integration |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| config.py | config/config.toml | tomllib.load | ✓ WIRED | load_config reads/validates |
| cli.py | engine.py / stats.py | run_backtest + trade_stats | ✓ WIRED | default run reproduces baseline byte-for-byte |
| cli.py | data loader/resampler | load_histdata_csv + resample_to_m5 | ✓ WIRED | 385k M1 rows → 77k M5 bars |
| cli.py | logging_utils | log_decision via on_event + gap loop | ✓ WIRED | all 7 event types incl. `data_gap_detected` |
| engine.py | strategy chain | detect_swings→support_resistance→detect_setups | ✓ WIRED | same pure functions the live bot will use |
| levels.py | swings.py | confirmed swing_high/swing_low columns | ✓ WIRED | reads only confirmed columns; window-bounded expiry |
| signals.py | levels.py | resistance/support columns | ✓ WIRED | exact STRAT-02 expression |
| cli.py | data dir | `glob(DAT_ASCII_{symbol}_M1_*.csv)` | ✓ WIRED | sample + stray CSVs immune by construction |

### Automated Check Results

| Check | Command | Result |
|-------|---------|--------|
| Full test suite | `.venv/bin/pytest -q -W error::FutureWarning` | ✅ **39 passed** (0.49s) |
| MT5/TA-Lib leakage | `grep -rn "MetaTrader5\|mt5\|talib" src/` | ✅ none |
| Strategy purity | `grep "^import\|^from" src/trading_bot/strategy/` | ✅ pandas/numpy only |
| ffill gone | `grep -rn "ffill" src/trading_bot/strategy/` | ✅ no matches |
| Glob restricted | `grep -rn "glob(" src/trading_bot/cli.py` | ✅ single `DAT_ASCII_{symbol}_M1_*.csv` glob |
| DEFAULT command | `.venv/bin/python -m trading_bot.cli backtest` (real data in data/raw/) | ✅ exit 0; 339 closed / 206 W / 133 L / 60.8% / +1021.91 / PF 1.29 / DD 271.44 / 340 setups |
| trades.csv integrity | pandas check on output/trades.csv | ✅ 0 records `sl < 500`; 0 records `tp < entry`; min sl 2621.46 |
| 1:1 R:R on armed orders | 340 `setup_detected` log events vs raw pipeline | ✅ max \|logged_tp − round(res+(res−sl),2)\| = 0.0000 (the one apparent 2-cent drift was float repr: resistance=4085.875 → tp=4176.105 → logs as 4176.1) |
| Data-gap surfaced | `grep "event=data_gap_detected" output/backtest.log` | ✅ 2025-12-31→2026-07-01 (4351h) + 2025-04-17→2025-04-20 (73h); stderr warning; exit 0 |
| Sample relocated | `ls data/raw/` vs `ls data/sample/` | ✅ raw = 2 DAT_ASCII only; sample in data/sample/ |
| Graceful failure | `--data-dir /tmp/empty_xyz_123` | ✅ exit 1, clear histdata message |
| Config validation | bad timeframe / missing file | ✅ ValueError naming key / FileNotFoundError |
| Golden sample | `test_golden_integration_full_records` etc. | ✅ entry=101.10, sl=100.09, tp=101.91, TP, pnl=0.81 (unchanged) |

### Requirements Coverage

| Requirement | Status | Blocking Issue |
|-------------|--------|----------------|
| STRAT-01 (dynamic S/R from swing structure) | ✓ SATISFIED | fractal swings + window-bounded level expiry verified |
| STRAT-02 (bullish close above resistance, prior close ≤ resistance) | ✓ SATISFIED | exact condition + tests |
| STRAT-03 (entry/SL/TP rules) | ✓ SATISFIED | armed orders exact 1:1 on all 340 real-data setups; no economically impossible records |
| SAFE-01 (same strategy in backtest; per-trade records) | ✓ SATISFIED | shared pure strategy module; conventions verified incl. the previously-failing default path |
| SAFE-02 (decision logging) | ✓ SATISFIED | 18,341 structured event lines, 7 event types |
| EXEC-03 partial (config file) | ✓ SATISFIED | all params from config.toml |
| EXEC-01 partial (data fetch) | ✓ SATISFIED | historical bars only, histdata pipeline |

### Anti-Patterns Found

None. No TODO/FIXME/placeholder stubs, no `.ffill()` in strategy, no console.log-only handlers, no hardcoded sample data in the default path.

### Human Verification Required

None blocking. The two human checklist items from the previous verification are now resolved programmatically:
- **Default-run contamination resolution** — both root causes were fixed in code with regression tests (no longer a product decision; the repo ships clean by default).
- **Spot-check a real-data signal against the rules** — done programmatically: every `setup_detected` log line carries entry=resistance, sl=support−0.01, tp=1:1 within the realistic 2025-26 price band (e.g. first 2025 setup: 2626.3/2621.46/2631.14; last 2026 setup: 4085.88/3995.64/4176.1).

## Gaps Summary

**No remaining gaps.** Both gap-closure plans (01-04 levels expiry, 01-05 CLI hygiene) are verified in the actual codebase: `.ffill()` is gone (window-bounded expiry, decay-to-NaN tests added), the CLI globs only `DAT_ASCII_{symbol}_M1_*.csv` (sample relocated to data/sample/), data gaps are surfaced as `event=data_gap_detected` warnings, and the DEFAULT `python -m trading_bot.cli backtest` run on the repo's real data produces 340 convention-clean records with stats byte-identical to the clean baseline (339 closed / 206 W / 133 L / 60.8% WR / +1021.91 pts / PF 1.29 / DD 271.44 / 340 setups) — no `sl < 500`, no `tp < entry`, exact 1:1 R:R on every armed order. 39/39 tests pass under `-W error::FutureWarning`. The phase success criterion ("user can point at any detected signal in the log and see entry/SL/TP that match the rules") holds on the default command.

---

_Verified: 2026-08-11T06:46:32Z_
_Verifier: Claude (gsd-verifier)_
