# Stack Research

**Domain:** JPY-cross (EURJPY / GBPJPY) swing-breakout backtest on the existing Exness/MT5 + pandas stack
**Researched:** 2026-09-07
**Confidence:** HIGH on the seam; MEDIUM on Exness-specific symbol numbers (verify-at-fetch); LOW on Exness M5 history depth (empirical)

## Headline finding

**No new third-party dependencies.** This milestone is code changes to modules that
already exist, plus one small data artifact (a per-symbol spec captured from the
terminal at fetch time). Everything required is already in the venv
(`pandas 3.0.5`, `numpy 2.5.2`, `MetaTrader5 5.0.6090`, Python 3.12). The v1.0
multi-instrument finding ("contract size from symbol_info, sl_buffer scaled by
point, quote→account conversion for JPY crosses, spread modeling, 2-dp fixes")
is not a dependency problem — it is a **symbol-spec plumbing** problem, and the
codebase already solved the live half of it (`SymbolRisk` from
`trade_tick_size`/`trade_tick_value` in `broker/mt5.py`). The backtest half needs
the same numbers made available offline.

## Recommended Stack

### Core Technologies (already installed — no change)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12.10 (requires ≥3.11) | runtime | In use; pyproject floor is ≥3.11 |
| pandas | 3.0.5 (>=3.0) | bars, resample, vectorized S/R | In use; strategy chain is pure pandas 3.0 CoW semantics |
| numpy | 2.5.2 (>=2.0) | stats, arrays | In use |
| MetaTrader5 (pip) | 5.0.6090 → upgrade to **5.0.6180** (PyPI 2026-09-05) | broker-native M5 fetch | Already the data source; package version tracks the terminal build. Upgrade at the start of the data-acquisition phase to match the running Exness terminal. Windows-only wheels — already satisfied |

### Supporting "Libraries" (code additions to existing modules — no pip installs)

| Addition | Where | Purpose | Notes |
|----------|-------|---------|-------|
| Per-symbol **spec sidecar** captured from the terminal at fetch time | `scripts/fetch_broker_history.py` + `data/processed/<SYMBOL>_M5_broker.spec.json` | Makes the backtest instrument- and account-type-correct without hardcoding Exness specs | Fields: `symbol, account_currency, digits, point, trade_tick_size, trade_tick_value, trade_contract_size, volume_min/step/max, captured_at, bars, first_bar, last_bar, spread_points_median`. Read from `symbol_info()` + `symbol_info_tick()` + the fetched frame — the exact fields `MT5Broker.symbol_risk()` already consumes live |
| Keep the per-bar **`spread` column** (in points) when exporting the M5 CSV | `fetch_broker_history.py` (currently drops it) | Spread modeling that is instrument-real, not gold's `$0.26` | MT5 rate tuples carry `spread` per bar in points (MQL5 docs). Median → `spread_points_median` in the sidecar; the sidecar is the offline replacement for a broker quote |
| Optional concurrent **USDJPY M5 fetch** (same account, same batch) | `fetch_broker_history.py` | True JPY→account-currency conversion per trade date | Only needed if money P&L accuracy across years matters; the R-based verdict does not need it. `merge_asof` on time, offline. Skip for v1.1 if verdict battery is R-primary |
| `load_broker_m5_csv()` + spec loader | `data/loader.py` | Parse the broker CSV (OHLC ± spread) and the sidecar into a `SymbolRisk`-shaped object | Reuses the frozen `SymbolRisk` dataclass so backtest money math is the same formula live sizing uses |
| Optional tick-based money conversion in `trade_stats()` | `backtest/stats.py` | `net_pnl`/drawdown in account currency (USC) for JPY crosses | Replace `contract_size*lot*pnl_points` with `pnl_points * (tick_value/tick_size) * lot` when a spec is supplied; **keep the legacy path default so gold runs stay byte-identical** (pinned by golden tests) |
| Optional `sl_buffer` in **points** (multiplied by `point` from the spec) | `config.py` + CLI backtest entry | Fixes the v1.0 bug where a committed price buffer means 10 points on 3-dp gold but 100 pips on EURUSD | Default (no spec / legacy key) reproduces current behaviour exactly; JPY configs set `sl_buffer_points` |
| Display/rounding follows symbol `digits` (3 dp for JPY crosses) | `cli.py` (emit + trades.csv rounding) | Stop losing a digit on 3-dp quotes in logs/exports | Cosmetic, not verdict-critical; `_round2`/`PendingOrder.equivalent_to` live-side 2-dp fixes are **NOT** in scope (backtest-only milestone) |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `scripts/fetch_broker_history.py` | Page M5 history out of the connected terminal (exists, works, pages at 50k bars/call) | Raise **Tools → Options → Charts → "Max. bars in chart"** before the deep fetch — MT5 docs bound copy-function availability by that setting (default ~100k bars is exactly why the existing gold/broker CSVs are ~100k bars ≈ 1 year) |
| Terminal GUI + Market Watch | Confirm exact cent symbols (`EURJPYc`, `GBPJPYc`) and their `digits` before trusting any config | config-eurjpy.toml checklist item 1; do not guess suffixes |

## JPY-Cross Conventions (research answers)

| Convention | Value | Confidence / Source |
|------------|-------|---------------------|
| Quote precision on Exness MT5 | **3 digits** (`digits=3`, `point=0.001`, `tick_size=0.001`) | MEDIUM-HIGH: industry 5-dp majors / 3-dp JPY rule (EarnForex), Exness 5-digit-style quoting; **verify at fetch via `symbol_info().digits`** |
| Pip definition | **1 pip = 0.01 price = 10 points** (2nd decimal), tick/pipette = 0.001 | MEDIUM-HIGH: JPY pairs price convention; Exness help "pip size 0.0001–0.01" for forex |
| Spread (EURJPY / GBPJPY) | Stable spreads (Exness lists both), account page: "from 0.3 pips"; planning range **0.3–1.0 pip** = 3–10 points = 0.003–0.010 price | MEDIUM: Exness help (stable-spread list, account features); use the captured per-bar median for modeling |
| Spread cost vs risk | Median JPY stop measured ~0.381 price (38 pips) → 1 pip spread ≈ 2.6% of risk, 0.5 pip ≈ 1.3% | MEDIUM (from STATE.md stop note + arithmetic). Contrast: gold $0.26 spread ≈ 4–9% of risk — **never reuse gold's spread** |
| Contract size — Standard account | 100,000 base currency / lot (EURJPY 100,000 EUR) | HIGH: Exness forex contract spec (100,000) |
| Contract size — Standard Cent account | Cent lot = 0.01 standard lot (official: "1 cent lot = 100,000 cents or 1,000 USD"); MT5 `trade_contract_size` for FX c-symbols ≈ 1,000 base units | MEDIUM: Exness help + third-party; **the terminal's `trade_contract_size`/`trade_tick_value` at fetch time is the authority** |
| Cent symbols & balances | `EURJPYc` / `GBPJPYc` exist on cent (Exness instrument list); balance `USC`; min volume 0.01 | HIGH: Exness Standard Cent article (updated 2026-08-24) |
| P&L currency | JPY crosses settle in **JPY** → account-currency conversion is the whole point of reading `trade_tick_value` (already account-currency) | HIGH: mechanism verified live in this repo (XAUUSDc pays USD into USC; tick_value absorbs it) |
| M5 history depth served | Exact span **EMPIRICAL** — existing cent-terminal fetches returned ~100k M5 bars (~1 year). Raise "Max. bars in chart", select symbol, let it sync, page to exhaustion, record span | MEDIUM for mechanism / LOW for Exness JPY depth. Must be a data-acquisition checkpoint, not assumed |

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Broker-native MT5 fetch + spec sidecar (offline) | histdata.com M1 CSVs (current gold path) | Never for this milestone — histdata lacks Exness cent symbols, spread, and is stale |
| R-primary verdict battery, money secondary | Full per-trade USD conversion across years | Only if the milestone demands money-accurate P&L; needs concurrent USDJPY history fetch (adds a merge, no new dep) |
| Capture specs at fetch time | Hardcode Exness contract/tick tables in config or code | Never — account-type suffixes and tick values drift; the codebase's own rule is "read the broker's numbers, never guess" |
| Keep one-spread analysis-side net subtraction (v1.0 method) | Engine-level ask/bid fill modeling | The v1.0 gold note says SL/TP-on-bid effects dominate and need tick data the backtest lacks; out of scope, same limitation applies to JPY |

## What NOT to Use / Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `backtrader`, `vectorbt`, `numba`, TA-Lib | Heavy deps, different execution paradigm, TA-Lib already dropped (no swing functions); strategy engine must stay the shared pure chain (SAFE-01) | Existing `run_backtest` + stats, extended with the spec sidecar |
| `ccxt`, `yfinance`, Dukascopy, OANDA/`oandapy`, scraping | Not the Exness MT5 feed; network at research time; account-type and spread wrong; offline-first violated | MetaTrader5 pip package against the user's own logged-in terminal (Windows) |
| Hardcoded Exness spread/contract/pip tables | Numbers drift and are account-type-specific; silently wrong is worse than absent | Spec sidecar captured from `symbol_info()` at fetch time |
| `_round2` / `PendingOrder.equivalent_to` digit fixes | Backtest-only milestone — no live wiring | Defer to a live-wiring milestone; only make CLI display rounding follow `digits` |
| New database / DuckDB work for the verdict | Warehouse is for analytics post-hoc; verdict is a script battery | Existing backtest CLI + output/ |
| Engine-level spread/ask fills | Bid-only M5 bars can't model SL/TP-on-ask truthfully (v1.0 finding); would change gold behavior | v1.0 analysis-side "net of one spread per round trip", with the JPY-correct spread in points |

## Integration Points (config / broker / backtest seam)

1. **Broker seam (already correct):** `MT5Broker.symbol_risk()` reads
   `trade_tick_size`, `trade_tick_value`, volume grid from `symbol_info()` — the
   live source of truth. The data-acquisition phase reuses this call surface to
   write the sidecar; no broker code changes needed.
2. **Config seam:** `config-eurjpy.toml` exists with UNVERIFIED values flagged.
   Add a `[data] spec_file` (or derive path from the CSV) + optional
   `[strategy] sl_buffer_points` + JPY spread assumption. All new keys optional →
   legacy gold configs load byte-identical.
3. **Backtest seam:** `cli.py` already accepts `--m5-csv` for broker frames and
   bypasses histdata resampling. Extend it to also load the spec and pass tick
   economics into `trade_stats()`; `run_backtest` engine logic is unchanged
   (levels/setups are pure price math — nothing in the loop is 2-dp or
   contract-aware except sl_buffer scaling and display rounding).
4. **Account-type consistency rule:** fetch the JPY M5 data on the SAME account
   type the backtest models (cent `EURJPYc`/`GBPJPYc` if the verdict targets a
   cent bot) because `trade_tick_value`/`trade_contract_size` are
   account-type-specific. Data + sidecar must move together.

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| MetaTrader5 5.0.6180 (upgrade) | Python 3.12 win_amd64 wheel; current Exness terminal build family | Package release tracks terminal build; 5.0.6180 released 2026-09-05; installed 5.0.6090 (2026-08-01) is fine but one build behind |
| pandas 3.0.5 | numpy 2.x, strategy modules (CoW semantics already pinned) | No change |
| Python ≥3.11 | pyproject floor; 3.12.10 in venv | No change |

## Sources

- Exness Help Center — *Standard Cent account* (updated 2026-08-24): cent lot = 1,000 USD = 0.01 standard lot; `-c` suffixes; USC balance; `EURJPYc`/`GBPJPYc`/`XAUUSDc`/`BTCUSDc` listed; min 0.01 lot; spread "from 0.3 pips". https://get.exness.help/hc/en-us/articles/17537782786588-Standard-Cent-account — HIGH
- Exness Help Center — *Forex* (updated 2026-07-10): contract size 100,000; pip size 0.0001–0.01; Standard Cent included in account list; EURJPY/GBPJPY listed as minor pairs. https://get.exness.help/hc/en-us/articles/17854278192284-Forex — HIGH
- Exness Help Center — *About spread* (updated 2026-08-22): EURJPY and GBPJPY on the stable-spread list; spread in pips. https://get.exness.help/hc/en-us/articles/360014690880-About-spread — MEDIUM (presence HIGH, numeric range not stated)
- MQL5 — *copy_rates_from_pos / CopyRates*: bars available bounded by terminal "Max. bars in chart" setting; rate records carry a per-bar `spread` (points); download continues across calls. https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesfrompos_py and https://www.mql5.com/en/docs/series/copyrates — HIGH
- PyPI — `metatrader5` 5.0.6180 (2026-09-05), Windows-only wheels, Python <4, ≥3.6. https://pypi.org/project/MetaTrader5/ — HIGH
- EarnForex — 5-dp majors / 3-dp JPY quoting guide (JPY pairs 3 decimals when majors are 5). https://www.earnforex.com/guides/forex-quotes-with-5-vs-4-decimal-places-in-metatrader-expert-advisors/ — MEDIUM
- fxfinds.com — Exness cent contract size = 1,000 units vs 100,000 standard (pip value 100× smaller). https://fxfinds.com/exness-account-types/ — LOW (third party; corroborates Exness official wording)
- Project STATE.md (2026-08-20/21 findings): cent-account tick-value risk mechanics, XAUUSDc `trade_contract_size=1.0`, EURJPY median stop 0.381, the invalid `$0.26`-spread EURJPY row, and the "genuine multi-instrument support needs" list. — HIGH (repo-measured)

---
*Stack research for: v1.1 JPY-cross breakout investigation (backtest-only)*
*Researched: 2026-09-07*
