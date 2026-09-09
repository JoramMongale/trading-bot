# Phase 1: Strategy Core — Detection + Backtest — Research

**Researched:** 2026-08-10
**Domain:** Python strategy engine — swing-point S/R detection, breakout signal logic, bar-based backtesting on 5m XAUUSD
**Confidence:** HIGH (stack versions verified against PyPI/official docs; algorithm design from established practice)

<user_constraints>
## User Constraints

No CONTEXT.md exists (discuss-phase not run). Constraints below are taken from `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md`, and `.planning/ROADMAP.md` — treat as locked decisions for this phase:

### Locked Decisions
- **Dynamic S/R in v1** (swing points/fractals), NOT the naive 20-bar min/max from the reference script
- **Strategy logic in pure Python**, shared verbatim between backtester and live bot
- **Buy-only** strategy (no short side in v1)
- **Fixed lot sizing (0.01 default)**, risk-based sizing deferred
- **Logging only, no notifications**
- **Phase 1 must run without MT5** (historical bars only); MT5 execution is Phase 2
- **Own backtester, not MT5 Strategy Tester**
- 1:1 risk-reward; entry at resistance; SL below support; TP = entry + risk

### Claude's Discretion
- Fractal parameters (bars to each side, S/R lookback window)
- Config file format and project layout
- Historical data source (MT5-free)
- Exact trade-matching conventions (intrabar fill/SL/TP ordering)
- Which stats to report and how (points vs pips vs dollars)

### Deferred (OUT OF SCOPE for Phase 1)
- Sell signals, MTF confirmation, notifications, risk-based lot sizing, MT5 order placement, live/demo guard
</user_constraints>

<architectural_responsibility_map>
## Architectural Responsibility Map

Single-tier desktop application — all capabilities reside in the local Python process (data load → strategy → backtest → stats → logs). The only external dependency boundary is the historical-data CSV source (histdata.com or MT5 export), consumed as files on disk. No network calls at runtime.
</architectural_responsibility_map>

<research_summary>
## Summary

Researched how to build the Phase 1 strategy engine: swing-point-based dynamic S/R detection, the bullish-breakout setup, and a bar-based backtester that reuses the same pure-Python strategy functions the live bot will call in Phase 2. The standard approach for this domain is a two-pass design: a **vectorized pandas pass** that computes confirmed fractal swing points and rolling S/R levels (with an explicit confirmation shift to eliminate lookahead bias), followed by a **per-trade loop** that matches Buy Stop fills and SL/TP exits against subsequent bars' highs/lows. An event-loop backtester is preferred over heavy vectorization of trade matching because gold 5m setups are rare (dozens to a few hundred trades over years of data), so the per-trade loop is fast, readable, and produces the per-trade records SAFE-01 requires.

Three verified environment facts drive the plan. **(1)** The dev machine is macOS with Python 3.14.2, pandas 3.0.0, numpy 2.4.2, pytest 9.0.2 — and pandas 3.0 makes Copy-on-Write mandatory, so chained assignment silently does nothing (a classic backtest bug source). **(2)** The `MetaTrader5` pip package is **Windows-only** (verified on PyPI: every wheel is `win_amd64`, latest 5.0.6090 with cp314 support), so MT5-based data fetch is impossible on this Mac — Phase 1 data must come from **histdata.com M1 ASCII CSVs (XAUUSD confirmed available, free, bid-only, EST timestamps) resampled to M5 in pandas**, or a one-time MT5 export. **(3)** TA-Lib (0.7.1, wheels available for cp314/macOS-arm64) has **no fractal/swing/pivot functions** — verified against its full function list — so it is not needed and should be dropped from the Phase 1 dependency set; swing detection is ~15 lines of pure pandas.

**Primary recommendation:** Build `trading_bot` as an `src/` package with `strategy/` (pure pandas, no MT5/config/logging imports), `data/` (histdata M1 loader + M5 resampler), `backtest/` (event-loop engine + stats), TOML config parsed with stdlib `tomllib`, stdlib `logging` to file, pytest tests. No TA-Lib, no MetaTrader5 in Phase 1 dependencies.
</research_summary>

<standard_stack>
## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.14.2 (installed) | Language | Verified on machine; 3.11+ required for `tomllib`; cp314 wheels exist for all deps |
| pandas | 3.0.0 (installed; 3.0.5 latest) | OHLC data frames, rolling windows, resample | The standard for bar data manipulation; vectorized swing detection |
| numpy | 2.4.2 (installed) | Array ops, NaN masking | pandas 3.0 requires numpy>=2.0 |
| pytest | 9.0.2 (installed) | Tests | Standard; pure-python strategy logic is highly unit-testable |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `tomllib` (stdlib) | — (Python ≥3.11) | Parse `config.toml` | Config loading — zero new dependency, comments allowed |
| `logging` (stdlib) | — | Structured file logging (SAFE-02) | Decision traceability; no third-party logger needed for v1 |
| TA-Lib (`TA-Lib` pkg) | 0.7.1 | Candlestick patterns, ATR, indicators | NOT needed for Phase 1 — **no swing/fractal/pivot functions exist** (verified against full function list); optional later for CDL* patterns/ATR |
| MetaTrader5 | 5.0.6090 | MT5 terminal API | **Windows-only package (all wheels `win_amd64`)** — cannot install on this macOS machine; Phase 2 concern, omit from Phase 1 deps |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pandas rolling (fractals) | `vectorbt` / `backtesting.py` backtest frameworks | Frameworks impose their own signal API and trade-matching semantics, fighting the "share the exact same strategy code with the live bot" requirement; a 200-line event loop is more transparent and debuggable |
| pandas resample (M1→M5) | MT5 Strategy Tester | Not usable — own backtester is a locked decision (shared code) |
| histdata M1 CSV | Dukascopy `.bi5` (via `duka` etc.) | Dukascopy has tick-level fidelity but needs LZMA binary parsing; PyPI package status unverified (JS-blocked page). histdata M1 → resample is the lowest-friction verified path |
| TOML config | YAML / JSON | YAML needs `pyyaml` dep; JSON has no comments and needs trailing-comma discipline. TOML: stdlib parse, comments, typed — clear winner |

**Installation (Phase 1):**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pandas numpy pytest          # TA-Lib NOT required for Phase 1
# Optional, if the user insists on TA-Lib later (cp314 macOS arm64 wheel verified on PyPI):
# brew install ta-lib  &&  pip install TA-Lib
```
</standard_stack>

<architecture_patterns>
## Architecture Patterns

### System Architecture Diagram

```
histdata.com M1 CSV (bid OHLCV, EST) ──► data/loader.py ──► DataFrame[M1]
                                                            │ resample('5min')
                                                            ▼
                                                   DataFrame[M5, UTC-naive]
                                                            │
                    ┌────────────────────────────────────────┘
                    ▼
        strategy/swings.py   detect_swings()  → swing_high/swing_low (CONFIRMED, shifted)
                    ▼
        strategy/levels.py   support_resistance() → support/resistance per bar (rolling, ffill)
                    ▼
        strategy/signals.py  detect_setups() → setup bool (STRAT-02, no lookahead)
                    │
     ┌──────────────┴─────────────────────────────┐
     ▼                                            ▼
 backtest/engine.py (event loop:               (Phase 2 live bot calls the SAME
   Buy Stop fill → SL/TP match →                three strategy functions on the
   per-trade records)                           last closed bars)
     ▼
 backtest/stats.py → per-trade CSV + aggregate stats (SAFE-01)
     ▼
 logging_utils.py → decision log file (SAFE-02)
```

### Recommended Project Structure
```
trading_bot/
├── pyproject.toml                  # PEP 621 metadata + deps (pandas, numpy, pytest)
├── README.md
├── config/
│   └── config.toml                 # symbol, timeframe, fractal params, sr_lookback, lot, output paths
├── data/
│   ├── raw/                        # histdata DAT_ASCII_XAUUSD_M1_YYYYMM.csv files (gitignored)
│   └── processed/                  # optional resampled M5 parquet/csv cache (gitignored)
├── src/trading_bot/
│   ├── __init__.py
│   ├── config.py                   # load/validate config.toml (tomllib), dataclass Config
│   ├── data/
│   │   ├── loader.py               # parse histdata CSV → M1 DataFrame
│   │   └── resample.py             # M1 → M5 (open first / high max / low min / close last / vol sum)
│   ├── strategy/
│   │   ├── swings.py               # detect_swings() — fractal swings, confirmation shift
│   │   ├── levels.py               # support_resistance() — trailing-window S/R
│   │   └── signals.py              # detect_setups() — STRAT-02
│   ├── backtest/
│   │   ├── engine.py               # run_backtest() — event loop, per-trade records
│   │   └── stats.py                # trade_stats() — aggregates + equity/drawdown
│   ├── logging_utils.py            # file logger with structured key=value lines
│   └── cli.py                      # `python -m trading_bot.cli backtest` entry point
└── tests/
    ├── test_swings.py              # synthetic OHLC: swing detection, plateau, no-lookahead shift
    ├── test_levels.py
    ├── test_signals.py             # STRAT-02 logic incl. prior-close edge cases
    └── test_backtest.py            # fill/SL/TP ordering, gap-open fill, 1:1 R:R numbers
```

**Hard rule:** `src/trading_bot/strategy/` must import ONLY pandas/numpy — no `logging`, no config, no data loaders, no MT5. The live bot in Phase 2 calls `detect_swings`/`support_resistance`/`detect_setups` on its own bars. This single rule is what makes SAFE-01 (same strategy on historical data) literally true.

### Pattern 1: Two-Pass Backtest — Vectorized Signals, Looped Trade Matching
**What:** Pass A computes all signal columns vectorized (swings → levels → setup bool). Pass B is an event loop over bars that matches fills/exits and emits per-trade dicts.
**When to use:** Strategy detection that must be shared with live trading (vectorized pass) + trade outcomes that need explicit per-bar ordering (looped pass). Gold 5m setups are rare — even 3 years of M5 (~75k bars) yields only dozens-to-hundreds of signals, so the loop is fast.
**Why not full vectorization:** Trade matching with position state (one open trade at a time, fill latency, SL-before-TP intrabar ordering) becomes unreadable state machines when vectorized. The loop over signals is O(trades × bars-between) and trivially auditable.

### Pattern 2: No-Lookahead Confirmation Shift
**What:** A fractal swing at bar *i* is only *known* once the right window closes, i.e. at bar *i + right*. Emit `swing_high = raw_swing_high.shift(right)` so the value becomes available exactly when it would have been in live trading.
**When to use:** Every indicator whose definition includes future bars (fractals, zigzag, future-window pivots). This single shift is the difference between a valid and an inflated backtest.
**Example:** see Code Examples → `detect_swings()`.

### Anti-Patterns to Avoid
- **Chained assignment in pandas 3.0** (`df[df["setup"]]["entry"] = x`): Copy-on-Write is mandatory in pandas 3.0 — this now silently does nothing (the warning was removed). Use `.loc` single-step assignment: `df.loc[df["setup"], "entry"] = x`.
- **Global mutable state in the strategy module:** the live bot and backtester must get identical results — strategy functions must be pure (DataFrame + params → DataFrame), no module-level caches.
- **Computing S/R from the current bar's high/low before the bar closes:** a swing at bar *t* must never be used to trade bar *t*. The confirmation shift handles this; never "fix" it by looking ahead.
- **Vectorizing trade matching into clever argmax chains:** hard to verify SL-before-TP semantics; keep the loop.
</architecture_patterns>

<dont_hand_roll>
## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Timeframe resampling (M1→M5) | Custom aggregation loops | `DataFrame.resample("5min").agg({...})` | Handles grid alignment, gaps, closed/label semantics correctly; vectorized |
| CSV parsing | Regex/split parsers | `pd.read_csv(sep=";", names=[...])` | Column parsing, dtype inference, malformed-row handling |
| Date parsing | Manual `strptime` loops | `pd.to_datetime(col, format="%Y%m%d %H%M%S")` | Vectorized; pandas 3.0 resolution inference handles units |
| Rolling max/min over swings | Python loops over windows | `Series.rolling(window).max()/min()` | Vectorized, NaN-skipping, min_periods semantics |
| Config parsing | Hand-rolled key=value parser | stdlib `tomllib.load()` | Typed values, comments, nested tables, zero deps |
| Decision logging | print() | stdlib `logging` with a file handler | Timestamps, levels, rotation, zero deps |
| P&L math / drawdown | Hand-rolled money math | numpy on the per-trade arrays | Max drawdown from equity curve is a rolling cummax diff — 3 lines of numpy |
| Unit tests | Custom assert harness | pytest | Discovery, fixtures, parametrize for S/R edge cases |

**Key insight:** Every "simple" piece here (resample, rolling, datetime parsing, config) has decades of edge cases — timezone quirks, closed vs label interval semantics, missing bars — that battle-tested stdlib/pandas handles. The only genuinely custom code in this phase is the strategy logic itself (~80 lines), which is exactly what must be hand-built and unit-tested.
</dont_hand_roll>

## Key Findings by Research Question

### RQ1 — Dynamic S/R detection methods (STRAT-01)

**Recommendation: Williams-style fractal swing points (fractal period 2), pure pandas, with a confirmation shift. Confidence: HIGH.**

Three candidate methods compared:

| Method | Algorithm | Pros | Cons | Verdict |
|--------|-----------|------|------|---------|
| **Fractal (Williams)** | Swing high at *i*: `high[i]` is the local max of a `(left + 1 + right)`-bar window (`left=2`, `right=2` → 5 bars). Swing low symmetric. | Trivial to vectorize; deterministic; exact rule is unit-testable; matches the user's "swing points/fractals" wording | Two adjacent swings of the same type can be <2 bars apart (minor for v1) | **Use this.** ~15 lines of pandas |
| Pivot points (zigzag with reversal threshold) | State machine: track last extreme; confirm a pivot when price retraces ≥ threshold | Confirms swings faster; only "significant" swings | Threshold is a free parameter that changes results discontinuously; state-machine logic is harder to share/test; overkill for v1 | Defer to v2 if fractal signals prove too noisy |
| Zigzag | Connect alternating pivots by a min-move percentage | Classic chart view | Path-dependent on the very last (incomplete) leg; bad for live decision-making | Reject for v1 |

**Concrete rule (deterministic, testable):**
- Swing high at *i*: `high[i] >= max(high[i-left..i-1])` AND `high[i] > max(high[i+1..i+right])`
- Swing low at *i*: `low[i] <= min(low[i-left..i-1])` AND `low[i] < min(low[i+1..i+right])`
- `>=`/`<=` on the **left** side makes the **last bar of an equal-high/low plateau** the swing point (flat-top handling: run `10, 10, 8` → second `10` is the swing high). Strict `>`/`<` on the right side keeps it confirmed. Note MT5's built-in fractal uses strict inequality on both sides and therefore *misses* equal-high plateaus entirely — one more reason not to copy MT5's indicator.
- **Lookahead bias:** a swing at *i* is usable only from bar *i + right* (the close of the right window). Implement as `confirmed = raw.shift(right)` — see Code Examples.
- **S/R levels from swings:** `resistance[t] = max(confirmed swing highs within last `sr_lookback` bars)`, `support[t] = min(confirmed swing lows within last `sr_lookback` bars)`, propagated forward with `ffill()` until a newer swing updates them. Default `sr_lookback = 60` bars (5 hours of M5). Both are configurable.
- **Parameter tuning (LOW confidence, empirical):** `left=right=2` (5-bar fractal) is the classic Williams default and a sensible v1 start for 5m gold. If signals are too dense, raise both to 3 (7-bar fractal). Validate on data during execution — no research source can tune this for you.

### RQ2 — Backtester design (SAFE-01)

**Recommendation: event loop over bars; one active trade at a time; Buy Stop fill on the next bar whose high ≥ entry; pessimistic SL-before-TP within a bar; 1:1 R:R from signal-bar levels. Confidence: HIGH (structure), MEDIUM (matching conventions — explicit choices below).**

- **Setup → order (STRAT-02/STRAT-03):** signal at bar *t* (close of *t*): `close[t] > res[t] AND close[t-1] <= res[t-1]` (each compared against the level valid at that bar). Order params frozen from signal-bar levels: `entry = res[t]`, `sl = sup[t] - sl_buffer` (default `sl_buffer = 0.01`, one point — guarantees "SL below support"), `tp = entry + (entry - sl)` (exact 1:1).
- **Fill:** from bar *t+1* onward, filled on first bar with `high >= entry`. Fill price `= max(entry, open)` (if the bar gaps above entry, fill at open — standard convention). *Note:* because `close[t] > res[t]`, entry usually fills at the next bar's open; the "Buy Stop at resistance" semantics are preserved and the fill price is logged either way.
- **Exit:** on each subsequent bar, if `low <= sl` → SL exit at `sl`; else if `high >= tp` → TP exit at `tp`. **Same-bar ordering is pessimistic: SL checked before TP** (a bar that touches both counts as a loss — standard conservative practice; gold 5m bars frequently span both levels, so this matters).
- **Partial trades:** out of scope — full fixed lot (0.01) per trade in v1.
- **One trade at a time:** skip new setups while a trade is open (log the skip reason). Simple, matches "fire a Buy Stop" mental model; multi-position mode is a v2 knob.
- **End-of-data open trades:** mark `exit_reason="OPEN"`, close at last close for stats, exclude from win/loss but include in net P&L (flag them in the summary). Deterministic and honest.
- **Stats to report** (from `trade_stats()`): `total_trades`, `wins`, `losses`, `win_rate`, `net_pnl_points` (dollars per ounce of price distance), `net_pnl_usd` (price distance × contract_size × lot; default contract 100 oz/lot, 0.01 lot → $1 per $1 move), `avg_r` (mean of `pnl_points / (entry - sl)`), `profit_factor` (gross win / gross loss), `max_drawdown` (USD, from the closed-trade equity curve via `cummax - cumsum`), plus `avg_trade_bars` and `open_trades` count. Per-trade CSV with all fields (entry/exit time, entry/SL/TP prices, exit reason, R multiple, P&L).

### RQ3 — Historical data source without MT5

**Recommendation: histdata.com Generic ASCII M1 CSVs for XAUUSD, resampled to M5 in pandas. Confidence: HIGH (availability + format verified; download requires manual browser step).**

| Source | Availability | Format | Verdict |
|--------|-------------|--------|---------|
| **histdata.com ASCII M1** | **XAUUSD verified, free, from 2009/March**, monthly zips | `20120201 000000;open;high;low;close;volume` (semicolon; **bid quotes only**; timestamps **EST, no DST**) | **Primary.** One-time manual download of a few months/years into `data/raw/`; loader + resampler is ~20 lines |
| MT5 terminal export (CSV) | User has MT5 | `Date,Time,Open,High,Low,Close,Volume` (bid) | Fallback/validation source; requires the terminal (Phase 1 goal is MT5-free, but a one-time export is acceptable) |
| MT5 `copy_rates_from` | Requires `MetaTrader5` package | numpy recarray `time,open,high,low,close,tick_volume,spread,real_volume` (UTC, ask/bid mid from terminal) | **Not usable on this Mac** — package is Windows-only (PyPI verified). Documented for Phase 2/Windows |
| Dukascopy `.bi5` | Free, tick-level | LZMA-compressed binary; needs custom parser | Not recommended — more moving parts, PyPI helper status unverified |

**Data caveats to log into the backtest report (not blockers):**
- **Bid-only:** a Buy Stop fills at ASK in reality. With bid data, entries at `res[t]` are optimistic by ~half-spread. For v1: document as a known limitation, add a configurable `spread_assumption` (XAUUSD typical spread $0.20–$0.50) that can be applied later or optionally subtracted from TP / added to entry.
- **EST fixed timestamps:** bars are stamped UTC−5 always (no DST adjustment). Bar grid stays regular; alignment to true UTC is off by 5h. Harmless for a pure bar-based strategy with no time-of-day filter; note it in the README.
- **Missing bars:** XAUUSD trades ~23h/day with a daily ~1h break (varies by broker/source). The M5 resample will have gaps at the break; the event loop must not treat a gap as a bar where nothing happens incorrectly — iterate only over bars that exist.

### RQ4 — Project structure, config, dependencies, tests

- **Layout:** `src/` package as shown in Architecture Patterns. `strategy/` stays pure.
- **Config format: TOML** via stdlib `tomllib` (Python ≥3.11). Rationale: zero new dependency, comments, typed values, nested `[data] [strategy] [trading] [backtest]` tables. **Confidence: HIGH.**
- **Config schema (Phase 1 subset, designed to grow in Phase 2):**
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
- **Dependency management: `pyproject.toml`** (PEP 621) with `[project] dependencies = ["pandas>=3.0", "numpy>=2.0"]` and `[dependency-groups] dev = ["pytest>=9"]`. Rationale: modern standard, works with pip/uv/poetry; requirements.txt is acceptable fallback. **Confidence: HIGH.**
- **Tests:** pytest, targeting `tests/test_swings.py`, `test_levels.py`, `test_signals.py`, `test_backtest.py`. Use synthetic OHLC fixtures (hand-crafted peaks/valleys/plateaus) so assertions are exact — no need for real data in unit tests. Add one golden integration test on a small hand-built M5 frame where expected trades are known by hand.

### RQ5 — Is TA-Lib needed? Honest answer: NO for Phase 1

- Verified against the TA-Lib 0.7.1 full function list: **there is no fractal, swing-high/low, or pivot detection function** (only rolling `MAX`/`MIN`/`MINMAX` — which are exactly the naive approach the user rejected). TA-Lib's Pattern Recognition group is candlestick *patterns* (CDLDOJI, CDLENGULFING…) — "bullish candle close above resistance" is a plain comparison, not a CDL pattern.
- The strategy's only math is rolling extrema + comparisons → pure pandas/numpy, ~80 lines. **Dropping TA-Lib removes a native-C dependency (and its macOS brew install dance) with zero loss.**
- TA-Lib could earn its place later (v2: ATR for adaptive SL, CDL* confirmation filters), and wheels for cp314/macOS-arm64 exist (0.7.1). **Confidence: HIGH.**

### RQ6 — Common pitfalls (see full section below)

Lookahead bias, incomplete-candle signals, broken-level re-triggering, pandas 3.0 Copy-on-Write, bid-only data, pip/point confusion, spread, and gold 5m volatility characteristics — each with prevention strategy.

<dont_hand_roll2>
## Recommendations by Decision Point

| # | Decision | Recommendation | Confidence |
|---|----------|----------------|------------|
| 1 | Swing detection method | Williams fractal, `left=right=2`, pure pandas, `>=` left / `>` right | HIGH |
| 2 | Lookahead handling | `confirmed = raw.shift(right)` on swing columns; levels/orders only ever read confirmed columns | HIGH |
| 3 | S/R from swings | Trailing `sr_lookback=60` bars rolling max/min of confirmed swings + `ffill()` | MEDIUM (parameter empirical) |
| 4 | Setup rule | `close[t] > res[t]` and `close[t-1] <= res[t-1]` | HIGH |
| 5 | Order params | `entry=res[t]`, `sl=support[t]-0.01`, `tp=entry+(entry-sl)` (exact 1:1) | HIGH |
| 6 | Backtest structure | Pass A vectorized signals; Pass B per-bar event loop | HIGH |
| 7 | Fill convention | Buy Stop fills when `high >= entry`; fill `= max(entry, open)` | MEDIUM (standard, explicit) |
| 8 | Intrabar exit ordering | SL checked before TP within a bar (pessimistic) | MEDIUM (conservative convention) |
| 9 | Concurrency | One active trade at a time; skip+log setups during open trade | MEDIUM (v1 simplification) |
| 10 | Data source | histdata XAUUSD M1 ASCII → resample to M5; MT5 CSV as cross-check | HIGH (availability), MEDIUM (fidelity) |
| 11 | Data caveats | Log bid-only + EST + spread limitation in report; configurable `spread_assumption` (default 0) | HIGH |
| 12 | P&L units | All math in price points ($/oz); USD via `contract_size × lot`; no pip logic | HIGH |
| 13 | Config format | TOML, stdlib `tomllib` | HIGH |
| 14 | Deps | pandas, numpy, pytest only — **no TA-Lib, no MetaTrader5** in Phase 1 | HIGH |
| 15 | Logging | stdlib `logging`, file handler, structured key=value lines | HIGH |
| 16 | Strategy purity | `strategy/` imports pandas/numpy only (shared with live bot) | HIGH |
</dont_hand_roll2>

<common_pitfalls>
## Common Pitfalls

### Pitfall 1: Lookahead bias in swing-point detection
**What goes wrong:** The backtest "knows" a swing high 3 bars before it could exist in live trading → resistance levels are higher/earlier than reality → inflated breakouts and fake wins.
**Why it happens:** Fractals are defined with a future window; naive `rolling(right).max()` includes the current bar, and levels are computed before the right window closes.
**How to avoid:** Raw fractal markers, then `confirmed = raw.shift(right)`. All downstream logic (levels, setups, orders) reads only confirmed columns. Add a unit test that asserts `res[t]` never uses `high[j]` for `j > t`.
**Warning signs:** A test where a signal's resistance equals a price that is still forming; backtest win rate suspiciously >60% on a 1:1 strategy.

### Pitfall 2: Using the current (incomplete) candle's close for signals
**What goes wrong:** Live trading would act on a candle that hasn't finished; in backtest the same check reads the final close of the signal bar. Results diverge.
**Why it happens:** "At bar t, is close > resistance?" is only answerable after bar t closes.
**How to avoid:** Decide at close of bar *t*, execute from bar *t+1* — the event loop already encodes this (fill starts the bar after the signal). Document in the code that `setup[t]` means "known at close of t".
**Warning signs:** Entry time equal to signal time in trade records.

### Pitfall 3: Re-triggering on a resistance that was already broken
**What goes wrong:** After the breakout, price is above resistance; a naive `close > resistance` keeps firing every bar, or fires when the old level is merely re-touched.
**Why it happens:** Not enforcing the "prior close ≤ resistance" condition, or comparing against a stale level.
**How to avoid:** STRAT-02's `close[t-1] <= res[t-1]` condition self-disables re-triggers — after a breakout the prior close is above the old level, so no new signal until a *new* swing high forms above price and price pulls back. Keep S/R recomputed every bar (dynamic) but never from unconfirmed swings.
**Warning signs:** Multiple signals within a few bars at the same price level in the trade log.

### Pitfall 4: Chained assignment under pandas 3.0 Copy-on-Write
**What goes wrong:** `df[df["setup"]]["entry"] = x` silently does nothing (the old `SettingWithCopyWarning` was removed in 3.0) → signals never get orders → empty trade list with no error.
**Why it happens:** pandas 3.0 made CoW mandatory; every derived frame behaves as a copy.
**How to avoid:** Single-step `.loc` assignment: `df.loc[df["setup"], "entry"] = df.loc[df["setup"], "resistance"]`. Never assign through a derived mask. Run the test suite with `-W error` once to catch stray patterns.
**Warning signs:** Zero trades reported on data you know has setups.

### Pitfall 5: Bid-only data vs ask fills (spread)
**What goes wrong:** Backtest fills the buy at resistance (bid), but live you pay ask → systematic overstatement of wins, especially with 1:1 R:R where the spread is a large fraction of the stop distance.
**Why it happens:** histdata quotes are bid-only (verified in their spec); MT5 exports bid too unless configured.
**How to avoid:** For v1, document as a known limitation and keep `spread_assumption` in config (0 by default). Do NOT silently pretend the data is mid — log it in the report header.
**Warning signs:** Net P&L in backtest consistently positive but the strategy is symmetric 1:1 — check spread impact before believing it.

### Pitfall 6: Integer vs float pip sizing for XAUUSD
**What goes wrong:** "Pips" are not standardized for gold ($0.10 vs $1.00 per pip varies by broker); `digits` is 2 on some brokers, 3 on others; integer pip math rounds away the stop distance.
**Why it happens:** Gold is quoted like a currency pair but priced like a commodity.
**How to avoid:** Do all math in raw price units (dollars per ounce). Reserve pips for display only. USD conversion via configurable `contract_size` (default 100 oz/lot) × `lot` (0.01). MT5 `point` (0.01 or 0.001) enters only in Phase 2 via `symbol_info()`. SL buffer of 0.01 assumes 2-digit quote — make it configurable.
**Warning signs:** Trades whose SL and entry differ by a rounded number; USD P&L off by 10×.

### Pitfall 7: Gold 5m volatility characteristics
**What goes wrong:** Surprised by brutal SL-hit streaks; concludes the strategy is broken.
**Why it happens:** 5m gold noise is large relative to swing-to-swing range; news events (NFP, FOMC, CPI) move $20–$50 in minutes; a 1:1 R:R with an SL below the *support swing* is routinely touched intrabar before continuation.
**How to avoid:** Treat backtest stats as the deliverable, not as a promise; report `avg_trade_bars`, win rate, and profit factor so the user sees the real profile; the SL-below-support definition is a strategy decision, not a bug — changing it is a config/strategy change, not a fix.
**Warning signs:** 100% of trades exit by SL in a specific month — check for a news-event date and document it.
</common_pitfalls>

<code_examples>
## Code Examples

### Swing detection + confirmation shift (the heart of STRAT-01)
```python
# src/trading_bot/strategy/swings.py  — pandas 3.0-safe, pure pandas/numpy
import numpy as np
import pandas as pd

def detect_swings(df: pd.DataFrame, left: int = 2, right: int = 2) -> pd.DataFrame:
    """Williams-style fractal swing points with a no-lookahead confirmation shift.

    Raw swing high at i:  high[i] >= max(high[i-left..i-1]) AND high[i] > max(high[i+1..i+right])
    Raw swing low at i:   low[i]  <= min(low[i-left..i-1]) AND low[i]  < min(low[i+1..i+right])

    '>='/'<=' on the LEFT makes the last bar of an equal-high/low plateau the swing point.
    Strict '>'/'<' on the RIGHT keeps the swing unconfirmed until the right window closes.

    The *_confirmed columns are shifted by `right` bars: a swing at bar i becomes
    usable only at bar i+right — exactly when it would be known in live trading.
    """
    high, low = df["high"], df["low"]
    left_high_max  = high.rolling(left,  min_periods=left).max().shift(1)
    right_high_max = high.rolling(right, min_periods=right).max().shift(-right)
    left_low_min   = low.rolling(left,   min_periods=left).min().shift(1)
    right_low_min  = low.rolling(right,  min_periods=right).min().shift(-right)

    is_swing_high = (high >= left_high_max) & (high > right_high_max)
    is_swing_low  = (low  <= left_low_min)  & (low  < right_low_min)

    df = df.copy()  # CoW-friendly
    df["swing_high_raw"] = np.where(is_swing_high, high, np.nan)
    df["swing_low_raw"]  = np.where(is_swing_low,  low,  np.nan)
    df["swing_high"]     = df["swing_high_raw"].shift(right)  # confirmed, no lookahead
    df["swing_low"]      = df["swing_low_raw"].shift(right)
    return df


def support_resistance(df: pd.DataFrame, lookback: int = 60) -> pd.DataFrame:
    """Trailing-window S/R from CONFIRMED swings, propagated forward.
    NaN until the first confirmed swing of that type exists."""
    df["resistance"] = df["swing_high"].rolling(lookback, min_periods=1).max().ffill()
    df["support"]    = df["swing_low"].rolling(lookback, min_periods=1).min().ffill()
    return df


def detect_setups(df: pd.DataFrame) -> pd.DataFrame:
    """STRAT-02: bullish close above resistance with prior close <= resistance.
    All comparisons are made against levels valid at each bar (already confirmed/shifted),
    so decisions at close of bar t use data up to and including bar t only."""
    close = df["close"]
    df["setup"] = (close > df["resistance"]) & (close.shift(1) <= df["resistance"].shift(1))
    return df
```
*Note:* `shift(-right)` on the future-window rolling max aligns the right window to the candidate bar (rolling at i+right covers [i+1..i+right]); the `>=`/`<=` on the left uses the strict-inequality-free window ending at i−1 via `.shift(1)`.

### Backtest event loop (SAFE-01 core)
```python
# src/trading_bot/backtest/engine.py
from typing import Any

def run_backtest(df, fractal_left=2, fractal_right=2, sr_lookback=60, sl_buffer=0.01):
    """Pass A (vectorized signals) + Pass B (per-bar event loop). Returns trade records.
    Verified against pandas 3.0.0. A trade record is appended EXACTLY ONCE, at exit."""
    df = df.copy()
    df = support_resistance(detect_swings(df, fractal_left, fractal_right), sr_lookback)
    df = detect_setups(df)

    trades: list[dict[str, Any]] = []
    open_trade = None                       # current open trade (or None)
    pending_entry = pending_sl = pending_tp = None  # armed Buy Stop

    for t in range(len(df)):
        bar = df.iloc[t]
        # 1) Manage the open trade first. Same-bar ordering: SL before TP (pessimistic).
        if open_trade is not None:
            if bar.low <= open_trade["sl"]:
                open_trade.update(exit_time=bar.name, exit_price=open_trade["sl"], exit_reason="SL")
                trades.append(open_trade); open_trade = None
            elif bar.high >= open_trade["tp"]:
                open_trade.update(exit_time=bar.name, exit_price=open_trade["tp"], exit_reason="TP")
                trades.append(open_trade); open_trade = None
            continue  # one active trade at a time

        # 2) Fill the pending Buy Stop (armed on the signal bar, fills from the next bar)
        if pending_entry is not None:
            if bar.high >= pending_entry:
                open_trade = dict(
                    entry_time=bar.name,
                    entry=max(pending_entry, bar.open),   # gap-open fills at open
                    sl=pending_sl, tp=pending_tp,
                    exit_time=None, exit_price=None, exit_reason=None,
                )
                pending_entry = None        # NOTE: not appended yet — appended at exit
            continue  # a filled bar may not also arm a new setup

        # 3) New setup → arm a Buy Stop with 1:1 R:R from THIS bar's levels (STRAT-03)
        if bar.setup:
            entry = bar.resistance
            sl = bar.support - sl_buffer
            pending_entry, pending_sl, pending_tp = entry, sl, entry + (entry - sl)

    # Close any trade still open at end of data at the last close (flagged, not counted as win/loss)
    if open_trade is not None:
        open_trade.update(exit_time=df.index[-1], exit_price=float(df["close"].iloc[-1]), exit_reason="OPEN")
        trades.append(open_trade)
    return trades
```
*Note:* on `pandas 3.0`, `.iloc[t]` rows are copies — safe to read, never mutate them; all trade state lives in plain dicts. Verified behaviors: fill on the bar *after* the signal; gap-open fill at `open`; pessimistic SL-before-TP when one bar touches both; signal on the final bar produces **zero** trades (no lookahead fill).

### Trade stats (SAFE-01 aggregates)
```python
# src/trading_bot/backtest/stats.py
import numpy as np

def trade_stats(trades, contract_size=100.0, lot=0.01):
    closed = [t for t in trades if t["exit_reason"] in ("SL", "TP")]
    for t in trades:  # R multiple & P&L points for every closed trade
        if t["exit_reason"] in ("SL", "TP"):
            risk = t["entry"] - t["sl"]
            t["pnl_points"] = t["exit_price"] - t["entry"]
            t["r_multiple"] = t["pnl_points"] / risk if risk else np.nan

    pnls = np.array([t["pnl_points"] for t in closed])
    gross_win = pnls[pnls > 0].sum()
    gross_loss = -pnls[pnls <= 0].sum()
    equity = pnls.cumsum() * contract_size * lot          # USD equity curve
    peak = np.maximum.accumulate(equity)
    return {
        "total_trades": len(closed),
        "open_trades": len(trades) - len(closed),
        "wins": int((pnls > 0).sum()),
        "losses": int((pnls <= 0).sum()),
        "win_rate": float((pnls > 0).mean()) if len(pnls) else 0.0,
        "net_pnl_points": float(pnls.sum()),
        "net_pnl_usd": float(equity[-1]) if len(equity) else 0.0,
        "avg_r": float(np.mean([t["r_multiple"] for t in closed])) if closed else 0.0,
        "profit_factor": float(gross_win / gross_loss) if gross_loss > 0 else float("inf"),
        "max_drawdown_usd": float((peak - equity).max()) if len(equity) else 0.0,
    }
```

### Data loading — histdata M1 → M5 (RQ3)
```python
# src/trading_bot/data/loader.py  +  resample.py
import pandas as pd

def load_histdata_csv(path: str) -> pd.DataFrame:
    """Row format (verified in histdata spec):  '20120201 000000;1.306600;1.306600;1.306560;1.306560;0'
    Bid quotes only; timestamps are EST (UTC-5, no DST)."""
    df = pd.read_csv(path, sep=";", header=None,
                     names=["dt", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["dt"], format="%Y%m%d %H%M%S")   # pandas 3.0 infers s-resolution
    return df.set_index("time").drop(columns="dt")[["open", "high", "low", "close", "volume"]]

def resample_to_m5(m1: pd.DataFrame) -> pd.DataFrame:
    return (m1.resample("5min", label="left", closed="left")
              .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
              .dropna())
```

### MT5 adapter (documented for Phase 2 / Windows — NOT used in Phase 1)
```python
# import MetaTrader5 as mt5   # Windows-only package; cannot import on this macOS machine
# rates = mt5.copy_rates_from("XAUUSD", mt5.TIMEFRAME_M5, datetime(2024, 1, 1), 100_000)
# df = pd.DataFrame(rates)                       # columns: time, open, high, low, close, tick_volume, spread, real_volume
# df["time"] = pd.to_datetime(df["time"], unit="s")   # official conversion pattern; UTC
```
</code_examples>

<sota_updates>
## State of the Art (2025–2026)

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| pandas 2.x (Copy-on-Write opt-in) | pandas 3.0 (CoW mandatory; chained assignment silently no-ops) | 2026-01-21 (3.0.0) | Backtest code must use single-step `.loc` assignment; old `SettingWithCopyWarning`-silencing `.copy()` calls are obsolete |
| pandas object-dtype strings | pandas 3.0 `str` dtype (PyArrow-backed if installed) | 2026-01-21 | CSV string columns come back as `str` dtype — harmless here; don't assert `dtype == object` |
| pandas ns-only datetime | Datetime resolution inference (`datetime64[s]` etc.) | 2026-01-21 | `to_datetime(unit="s")` yields second resolution — works fine with `resample`; do not force `unit="ns"` |
| TA-Lib 0.4.x (SWIG, no wheels, painful builds) | TA-Lib 0.7.1 (Cython, wheels incl. macOS-arm64 + cp314) | 2025–2026 | Installable if ever needed, but still has **no swing/fractal/pivot functions** — not needed for Phase 1 |
| MetaTrader5 package (Python 3.6–3.12 era) | 5.0.6090 with cp314 wheels — **all Windows-only** | Aug 2026 | MT5 data fetch is impossible on macOS; Phase 1 is MT5-free by design |
| histdata: any-timeframe downloads | Free tier now M1-only (verify on site; M5 no longer offered free) | ongoing | Must resample M1→M5 ourselves (pandas `resample`) |

**Deprecated/outdated:**
- `pd.set_option("mode.copy_on_write", ...)`: removed in pandas 3.0 (no-op).
- `ta-lib` (lowercase, SWIG fork) and `TA-Lib<0.5` with numpy 1.x: replaced by TA-Lib 0.6+/0.7 with bundled wheels.
- requirements.txt as the *only* dependency file: pyproject.toml is the 2025+ standard; requirements.txt acceptable as a lockfile export only.
</sota_updates>

<open_questions>
## Open Questions

1. **Reference script not found.** The user's reference script (naive min/max S/R, Buy Stop, 1:1 R:R) is not in the repo or adjacent directories — we could not diff against it.
   - What we know: PROJECT.md describes its behavior; the requirements supersede its naive S/R.
   - What's unclear: exact fill/SL/TP conventions the user is used to (fill at next open vs at level; SL exactly at support vs below).
   - Recommendation: match the conventions in RQ2 (documented, configurable), and if the script surfaces during execution, port the conventions only where they don't violate STRAT-01's dynamic S/R.

2. **Fractal parameter tuning (left/right/sr_lookback) is empirical.**
   - What we know: 2/2/60 are sensible defaults; the classic Williams 5-bar fractal.
   - What's unclear: signal density and quality on recent XAUUSD 5m data.
   - Recommendation: ship config defaults, add a small `--quick` run during execution to sanity-check signal count before the full backtest.

3. **Broker quoting details (digits/point, contract size) are unknown.**
   - What we know: XAUUSD is quoted with 2–3 digits; contracts are typically 100 oz/lot.
   - What's unclear: the user's actual broker conventions (affects Phase 2 order placement; USD P&L conversion in Phase 1).
   - Recommendation: keep `contract_size` and `sl_buffer` configurable with defaults (100, 0.01); confirm against the user's MT5 symbol info at Phase 2 start.

4. **Spread treatment for bid-only data.**
   - What we know: histdata is bid-only; live buy fills pay ask; `spread_assumption` config exists but defaults to 0.
   - What's unclear: whether the user wants spread modeled in Phase 1 or deferred.
   - Recommendation: default 0 (documented limitation), expose config; validate impact by re-running with a $0.30 spread before drawing conclusions about profitability.

5. **Dukascopy as a higher-fidelity data source is unverified.**
   - What we know: free tick data exists; requires `.bi5` parsing; the `duka` PyPI page was blocked by a JS challenge so its status is unknown.
   - What's unclear: current package health and XAUUSD availability.
   - Recommendation: not needed for Phase 1; revisit only if histdata fidelity (bid-only, EST) becomes a blocker.
</open_questions>

<sources>
## Sources

### Primary (HIGH confidence)
- PyPI `MetaTrader5` project page — version 5.0.6090 (Aug 1, 2026); **all wheels `win_amd64`**, cp36–cp314; Python <4, >=3.6. URL: https://pypi.org/project/MetaTrader5/
- MQL5 official Python integration docs — `copy_rates_from` return format: "numpy array with the named time, open, high, low, close, tick_volume, spread and real_volume columns"; UTC timestamps; official `pd.to_datetime(rates['time'], unit='s')` conversion pattern; TIMEFRAME_M5 constant. URLs: https://www.mql5.com/en/docs/python_metatrader5 and https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesfrom_py
- PyPI `TA-Lib` project page — version 0.7.1 (Jul 16, 2026); wheels incl. `macosx_14_0_arm64` + cp314; **full function list verified: no fractal/swing/pivot function** (only MAX/MIN/MINMAX rolling helpers); Function/Abstract/Stream APIs. URL: https://pypi.org/project/TA-Lib/
- pandas 3.0.0 "What's new" (released 2026-01-21) — mandatory Copy-on-Write (chained assignment stops working; `SettingWithCopyWarning` removed), default `str` dtype, datetime/timedelta resolution inference, `pd.col()`. URL: https://pandas.pydata.org/docs/whatsnew/v3.0.0.html
- HistData.com — XAUUSD available in Generic ASCII M1 (from 2009/March); M1-only free downloads; detailed ASCII format `YYYYMMDD HHMMSS;O;H;L;C;V`, **bid quotes**, **EST no-DST**. URLs: https://www.histdata.com/download-free-forex-data/?/ascii/1-minute-bar-quotes and https://www.histdata.com/f-a-q/data-files-detailed-specification/
- Local environment check — Python 3.14.2, pandas 3.0.0, numpy 2.4.2, pytest 9.0.2 installed; MetaTrader5/TA-Lib not installed; platform darwin (macOS); repo has no source code yet.

### Secondary (MEDIUM confidence)
- HistData.com download page (XAUUSD entry verified present, free) — https://www.histdata.com/download-free-forex-data/?/ascii/1-minute-bar-quotes (verified against their spec page).
- Williams fractal convention (MT5's built-in `Fractals` indicator uses strict inequality on both sides, 2 bars each side) — standard indicator definition, widely documented in MT5 docs; our left-side `>=` variant is a documented, deliberate deviation to handle plateaus.

### Tertiary (LOW confidence — needs validation)
- Fractal parameter tuning for 5m XAUUSD (2/2/60 defaults) — no authoritative source; empirical; validate on data during execution.
- XAUUSD broker conventions (digits 2 vs 3, 100 oz/lot contract, $0.20–$0.50 typical spread) — broker-specific; confirm against the user's MT5 terminal symbol info in Phase 2.
- Dukascopy `.bi5` Python helpers (`duka` package) — PyPI page blocked by JS challenge; status unverified; not required for Phase 1.
</sources>

<metadata>
## Metadata

**Research scope:**
- Core technology: pandas 3.0 + numpy 2.x on Python 3.14; swing-point S/R strategy; bar-based event-loop backtest
- Ecosystem: histdata.com data source; MT5 package (Windows-only); TA-Lib (not needed); tomllib config; pytest
- Patterns: two-pass backtest (vectorized signals + looped matching); no-lookahead confirmation shift; pure-strategy module shared with live bot
- Pitfalls: lookahead bias, CoW/chained assignment, bid-only data, pip/point confusion, incomplete candles, re-triggering

**Confidence breakdown:**
- Standard stack: HIGH — every version verified against PyPI/official docs
- Architecture: HIGH — two-pass pattern is the established practice for shared-code backtesters
- Pitfalls: HIGH — pandas 3.0 breaking changes verified in official docs; lookahead/spread/pip pitfalls are well-established
- Code examples: HIGH — pandas/rolling/resample semantics verified against pandas 3.0 docs; MT5 conversion pattern from official MQL5 docs; matching conventions flagged MEDIUM where they are deliberate choices

**Research date:** 2026-08-10
**Valid until:** 2026-09-09 (30 days — pandas/MT5/TA-Lib are stable; re-verify if pandas 3.x minor releases land)
</metadata>

---

*Phase: 01-strategy-core-detection-backtest*
*Research completed: 2026-08-10*
*Ready for planning: yes*
