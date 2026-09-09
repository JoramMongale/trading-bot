---
phase: 01-strategy-core-detection-backtest
plan: 01
subsystem: foundation
tags: python, pandas, numpy, pytest, tomllib, logging, histdata

# Dependency graph
requires:
  - phase: research
    provides: verified facts (pandas 3.0 CoW, histdata format, config schema, no TA-Lib/MT5)
provides:
  - Installable src/ package (editable, pytest pythonpath=src)
  - Typed validated config loader (stdlib tomllib)
  - Structured file decision logger (SAFE-02)
  - Histdata M1 CSV loader + M5 resampler (SAFE-01 data foundation)
affects: 01-02 (strategy detection), 01-03 (backtest engine), phase 2 (live bot config)

# Tech tracking
tech-stack:
  added: [pandas>=3.0, numpy>=2.0, pytest>=9]
  patterns:
    - "src/ layout with editable install and pytest pythonpath"
    - "frozen dataclasses mirroring TOML schema, validated at load"
    - "stdlib tomllib for config (zero new deps)"
    - "module-level logger guard for one-time FileHandler config"
    - "structured key=value decision logging (SAFE-02)"

key-files:
  created: [pyproject.toml, .gitignore, README.md, config/config.toml, src/trading_bot/__init__.py, src/trading_bot/config.py, src/trading_bot/logging_utils.py, src/trading_bot/data/__init__.py, src/trading_bot/data/loader.py, src/trading_bot/data/resample.py, tests/test_data.py]
  modified: []

key-decisions:
  - "Phase 1 runs on historical data only — MT5 package omitted (Windows-only, cannot install on macOS)"
  - "TA-Lib dropped from deps (no swing/fractal functions exist; pure pandas suffices)"
  - "pandas 3.0 datetime64[s] resolution — no unit='ns' forcing in loader"
  - "Config validation raises ValueError naming the bad key; FileNotFoundError with resolved path for missing file"

patterns-established:
  - "Strategy logic stays pure Python so backtester and live bot share detection code"
  - "Decision traceability via structured log lines (event= key=value)"

# Metrics
duration: 3 min
completed: 2026-08-10
---

# Phase 1 Plan 1: Foundation Summary

**Installable src/ package with typed TOML config (stdlib tomllib), structured file decision logging (SAFE-02), and the histdata M1→M5 data pipeline — all tests green under pandas 3.0 Copy-on-Write**

## Performance

- **Duration:** 3 min
- **Started:** 2026-08-10T17:19:11Z
- **Completed:** 2026-08-10T17:22:19Z
- **Tasks:** 3
- **Files modified:** 11

## Accomplishments
- PEP 621 `pyproject.toml` with `pandas>=3.0`/`numpy>=2.0` deps, dev pytest extra, and pytest `pythonpath=["src"]`; editable install verified (pandas 3.0.5, numpy 2.5.2, pytest 9.1.1 on Python 3.14.2)
- `config/config.toml` holds the full Phase 1 schema (data/strategy/trading/backtest); `load_config()` returns frozen dataclasses and rejects invalid config with actionable errors naming the bad key
- `get_logger()` + `log_decision()` write structured `key=value` decision lines to `output/backtest.log` (SAFE-02); root logger untouched, log dir auto-created
- `load_histdata_csv()` parses the verified histdata ASCII format (`%Y%m%d %H%M%S`; semicolon-separated; no header) into a datetime-indexed float OHLCV frame; `resample_to_m5()` aggregates with first/max/min/last/sum and keeps partial buckets while dropping empty ones
- `tests/test_data.py` (43 lines) covers loader format + resampler exact aggregates with a hand-computed 12-bar fixture including a 2-bar trading-break bucket

## Task Commits

Each task was committed atomically:

1. **Task 1: Project scaffold** - `74ea7f5` (chore)
2. **Task 2: Config + file logging** - `e36e98a` (feat)
3. **Task 3: Data pipeline** - `538b8f4` (feat)

## Files Created/Modified
- `pyproject.toml` - PEP 621 metadata, deps, pytest pythonpath=src config
- `.gitignore` - venv, caches, raw CSVs, processed data, output
- `README.md` - project purpose, Phase 1 MT5-free note, test instructions
- `config/config.toml` - Phase 1 config schema (data/strategy/trading/backtest tables)
- `src/trading_bot/__init__.py` - package marker (empty)
- `src/trading_bot/config.py` - tomllib loader + validation; exports `load_config`
- `src/trading_bot/logging_utils.py` - file logger; exports `get_logger`, `log_decision`
- `src/trading_bot/data/__init__.py` - package marker (empty)
- `src/trading_bot/data/loader.py` - histdata M1 CSV parser; exports `load_histdata_csv`
- `src/trading_bot/data/resample.py` - M1→M5 resampler; exports `resample_to_m5`
- `tests/test_data.py` - synthetic histdata fixture tests (loader + resampler)

## Config Schema As Built

```toml
[data]
source = "histdata"          # histdata | mt5-csv (mt5-package later)
raw_dir = "data/raw"
symbol = "XAUUSD"
timeframe = "M5"
start = "2024-01-01"
end = "2026-07-31"

[strategy]
fractal_left = 2
fractal_right = 2
sr_lookback = 60            # bars
rr_multiple = 1.0           # 1:1 risk-reward
sl_buffer = 0.01            # one point below support

[trading]
lot = 0.01
contract_size = 100         # oz per lot, for USD conversion
spread_assumption = 0.0     # 0 = ignore spread in v1 (documented limitation)

[backtest]
output_dir = "output"
```

## Test Results

- `pytest -q` (full suite): **3 passed, exit 0**
- `pytest tests/test_data.py -q -W error::FutureWarning`: **3 passed, exit 0** (no pandas 3.0 CoW chained-assignment warnings)
- Coverage: loader format (index name/dtype, exact column order, row count, float dtypes), partial-bucket resampling (3 M5 rows from 12 M1 bars across 3 buckets incl. a 2-bar bucket), exact aggregate values (open=first, high=max, low=min, close=last, volume=sum)

## Decisions Made
- Followed RESEARCH.md verbatim: stdlib `tomllib` for config, pandas 3.0 `datetime64[s]` inference (no `unit="ns"` forcing), histdata M1 CSV as the data path, no MT5/TA-Lib in deps
- Config validation raises `ValueError` naming the offending key and `FileNotFoundError` with the resolved path — actionable errors over silent fallbacks

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- None. Dependency resolution was clean (pandas 3.0.5, numpy 2.5.2, pytest 9.1.1 wheels for cp314/macOS); pytest `--collect-only` exit 5 before tests existed was the expected "no tests collected" state, now exit 0 with tests present.

## User Setup Required

None - no external service configuration required. (histdata.com CSVs are a one-time manual download into `data/raw/` for later plans, not a service config.)

## Next Phase Readiness
- Ready for `01-02-PLAN.md` (strategy detection: swings/levels/signals) — the pyproject pytest `pythonpath=src` setup, config schema, and data pipeline it depends on are in place
- `config.py` validation ensures Phase 2 config growth (extra keys) won't break typed loading
- Note for later plans: `output/backtest.log` is gitignored (output/ is in .gitignore); raw histdata CSVs are gitignored

---
*Phase: 01-strategy-core-detection-backtest*
*Completed: 2026-08-10*
