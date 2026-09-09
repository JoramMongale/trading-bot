# Architecture Research — Instrument-Correct JPY-Cross Backtesting (v1.1, BACKTEST-ONLY)

**Domain:** multi-instrument backtest extension of an existing single-instrument trading bot (gold/XAUUSD + BTC precedent)
**Researched:** 2026-09-07
**Confidence:** HIGH for all claims about the existing codebase (read directly); MEDIUM for integration design; LOW for any hardcoded instrument numeric (digits/point/tick) — the whole point of this design is that those numbers are read from `symbol_info`, never asserted from memory.

## Executive Verdict (read this first)

**Instrument-correct EURJPY/GBPJPY backtesting does NOT require touching the pure strategy
chain, the shared `run_backtest` loop, the BrokerClient ABC, or the live engine.**

That statement is the single most important architecture finding. It is true for three structural
reasons, verified in the code:

1. **The strategy chain and the backtest event loop are dimensionless in money.** `strategy/swings|levels|signals`
   consume OHLC only and emit raw prices. `backtest/engine.py` freezes `entry=resistance`,
   `sl=support−sl_buffer`, `tp=entry+rr×(entry−sl)`, and books every trade as raw quote-price
   floats with zero rounding (verified: no `round()` anywhere in `engine.py`). R-multiple, win rate,
   PF, t-stat — the entire falsification battery — are scale-free price ratios. A ¥-quoted cross at
   ~160 needs no different *engine*, only an honest *money/display boundary*.
2. **The engine's one instrument-typed input — `sl_buffer` — is an absolute price distance, and is
   already authored per-instrument by convention**, not computed in code. `config-btc-backtest.toml`
   sets `sl_buffer = 0.10` with the comment "10 * point = 10 * 0.01" (STATE.md 2026-08-20 convention:
   `sl_buffer = 10 × point`). `config-eurjpy.toml` already ships `sl_buffer = 0.01` for a 3-dp quote.
   So "sl_buffer scaled by point" is today a **config-authoring** concern, and should stay one —
   extending it via the fetch tool printing the verified value removes the human-arithmetic risk.
3. **The two places that DO encode wrong single-instrument assumptions for JPY are the stats money
   conversion and the CLI display rounding** — `backtest/stats.py` multiplies `pnl_points ×
   contract_size` (contract_size = gold's 100 oz/lot, and it silently assumes quote currency ==
   account currency), and `cli.py` writes `trades.csv` / decision logs at `.round(2)` (XAUUSD 2-dp
   assumption — itself stale: the committed broker-native `XAUUSDc_M5_broker.csv` holds 3-dp prices
   like `3133.287`).

Both wrong spots already have an in-repo, battle-tested correct pattern to copy: **the live layer's
`SymbolRisk` tick-economics trick** (`broker/base.py`): one tick's value `tick_value` is already in
ACCOUNT currency, so `(stop/tick_size) × tick_value × lots` needs no contract size and no FX rate.
The v1.1 backtest needs exactly that ratio — `money_per_price_unit_per_lot = tick_value / tick_size` —
injected as an **optional** parameter that defaults to the legacy `contract_size` path, so gold/golden
runs stay byte-identical.

Design that results from these three facts: **one new pure `InstrumentSpec` type + a fetch-time
sidecar file** feeding **two modified seams** (`stats.py` money conversion, `cli.py` digits) — and
nothing else. Full seam map in "New vs Modified vs Must-Not-Change", build order at the end.

---

## System Overview — target data flow (fetch → processed → backtest)

```
scripts/fetch_broker_history.py --config config/config-eurjpy.toml [--symbol EURJPYc]
    │   (native MetaTrader5 first, silicon bridge fallback, per-config terminal_path)
    │   paged M5 bars from symbol_info-backed terminal
    ▼
data/processed/EURJPYc_M5_broker.csv            ◄── UNCHANGED shape: time index + open/high/low/close
data/processed/EURJPYc_M5_broker.symbol.json    ◄── NEW sidecar: symbol_info snapshot at fetch time
    │   (digits, point, trade_contract_size, trade_tick_size, trade_tick_value,
    │    volume_min/step/max, currency_profit, spread snapshot)  + printed config block
    ▼
python -m trading_bot.cli backtest \
        --config config/config-eurjpy-backtest.toml \
        --m5-csv data/processed/EURJPYc_M5_broker.csv
    │   cli auto-discovers the *.symbol.json sidecar next to the CSV (config unchanged)
    │   → InstrumentSpec.money_per_price_unit_per_lot feeds stats money conversion
    │   → InstrumentSpec.digits feeds trades.csv / decision-log / per-trade rounding
    ▼
run_backtest(df, ...)                           ◄── UNCHANGED (sl_buffer absolute; raw-price records)
    ▼
trade_stats(trades, lot=…, money_per_unit_lot=spec…, spread=…)
    │   NEW optional params; default None/0.0 = legacy path byte-identical
    ▼
output/trades.csv  (3-dp for JPY, spec.digits)  + stats + backtest.log
```

Deliberate property: the CSV on-disk contract and the `run_backtest` signature do not change, so
every existing script, golden test, and the BTC/gold precedent keep working untouched.

---

## (a) Where instrument metadata lives — the InstrumentSpec sidecar

### Decision: new pure `src/trading_bot/instrument.py` + fetch-time sidecar JSON

**Recommended layout** (new file, dependency-free like `config.py`):

```
src/trading_bot/instrument.py        # NEW, pure (stdlib + dataclasses only)

@dataclass(frozen=True)
class InstrumentSpec:
    symbol: str
    digits: int                 # broker price decimals (XAUUSDc=3, EURJPYc=3?, BTCUSDc=2 …)
    point: float                # symbol_info.point — the price unit buffers are counted in
    tick_size: float            # trade_tick_size
    tick_value: float           # trade_tick_value — value of ONE tick_size move on ONE lot,
                                # already in ACCOUNT currency (the SymbolRisk insight)
    contract_size: float        # trade_contract_size (recorded for audit; NOT used for money)
    volume_min: float = 0.0
    volume_step: float = 0.0
    volume_max: float = 0.0
    currency_profit: str = ""   # e.g. "JPY" — audit field, never used in math
    spread_snapshot: float = 0.0  # symbol_info_tick ask−bid at fetch time (audit + default
                                  # spread assumption for net-of-spread stats)

    @property
    def money_per_price_unit_per_lot(self) -> float:
        """ACCOUNT-currency value of a one-price-unit move on one lot = tick_value / tick_size.
        NaN-guarded: unknown tick economics must read as unknown, never as zero cost."""
        return self.tick_value / self.tick_size if self.tick_size > 0 else float("nan")

    def round_price(self, x: float) -> float: ...   # round(x, digits)
    # + to_sidecar()/from_sidecar() JSON codec + validate() raising on digits<=0/point<=0/tick_size<=0
```

**Sidecar carrier file**, written by the fetch script next to the CSV at the exact moment bars are
pulled:

```
data/processed/{SYMBOL}_M5_broker.symbol.json     # e.g. EURJPYc_M5_broker.symbol.json
```

Fields come **from the broker's own `symbol_info()` / `symbol_info_tick()`** (`trade_tick_size`,
`trade_tick_value`, `digits`, `point`, `trade_contract_size`, `currency_profit`, `volume_*`) — the
same source `MT5Broker.symbol_risk()` already trusts (mt5.py:398-428). Never from memory, config
comments, or this document.

**Why a sidecar file and not a config table:**
- **One source of truth is the terminal.** `[data]`/`[live]` symbols already rename per account type
  (XAUUSD vs XAUUSDc); a hand-typed `[instrument]` table would be a second, drifiable copy of the
  same facts — the exact class of bug the repo has fixed three times around terminals.
- **Reproducibility.** A backtest of a CSV is a pure function of that CSV + its sidecar. Re-running
  an old CSV months later uses the specs that were true at fetch time, not whatever the terminal
  reports today.
- **The CSV contract stays untouched** — `run_backtest` consumers (`cli`, `ai/backtest.py`, research
  scripts, golden tests) never see the metadata.
- **Backward compatibility for free.** The two committed broker CSVs (`XAUUSDc`, `BTCUSDc`) have no
  sidecar → CLI falls back to the legacy path → gold/BTC behavior byte-identical.

**Deliberately NOT done here** (rejected alternatives): an `[instrument]` TOML table (duplicated
truth, schema + DEFAULT churn); metadata in the CSV filename/columns (breaks the OHLC frame contract
every consumer assumes); a warehouse/registry table (overkill for three instruments).

### What the backtester actually consumes from the spec

| Concern | Consumed by | Notes |
|---|---|---|
| `point`, `digits` | CLI config-block print + **authoring** of `sl_buffer` | Keep `sl_buffer` absolute-price; author it as `10 × point` per the 2026-08-20 convention |
| `money_per_price_unit_per_lot` | `trade_stats()` money conversion | Replaces the `contract_size` USD path only when present |
| `digits` | CLI trades.csv + decision-log rounding | Replaces `.round(2)` only when present |
| `spread_snapshot` | audit + default net-of-spread assumption | Engine keeps ignoring spread; stats subtracts it once per round trip |
| `currency_profit`, `contract_size` | audit/log only | Never used in math — prevents "quote currency labelled as USD" bugs |

### sl_buffer: the one instrument-typed strategy input stays absolute (no engine change)

`sl = support − sl_buffer` is pinned by golden tests, the live engine's identical arithmetic
(SAFE-01), and every research script. **Do not reinterpret `sl_buffer` as points inside the shared
engine.** Instead the new per-symbol backtest configs follow the existing `config-btc-backtest.toml`
precedent exactly:

```toml
[strategy]
sl_buffer = 0.010        # 10 points × point(0.001) for a 3-dp JPY cross — value PRINTED by
                         # fetch_broker_history.py from the sidecar, then human-confirmed
```

The fetch script prints a ready-to-paste TOML block after writing the sidecar
(`sl_buffer = 10 × point`, the `tick_value`-derived note, spread snapshot), so the "scale by point"
arithmetic is done by the machine that read the point, not by a human reading a comment. The
existing `config-eurjpy.toml` sl_buffer comment ("verify rather than rely on the coincidence") shows
exactly the failure this removes.

> Consequence for the v1.0 documented gap (STATE.md:695): "sl_buffer scaled by point" is satisfied at
> the **config-authoring seam with symbol_info as the authority**, not by a new engine parameter.
> The engine arithmetic and the shared strategy contract are preserved — which is the (e) constraint.

---

## (b) Data-flow changes for EURJPY + GBPJPY M5 history

Pipeline is already 80% built — v1.0 shipped `fetch_broker_history.py` → `data/processed/*_M5_broker.csv`
→ `backtest --m5-csv`. The JPY work **extends** it with the sidecar and adds two configs.

1. **Fetch** (Windows terminal, native package; per-config `terminal_path` already supported):
   ```
   .venv\Scripts\python scripts\fetch_broker_history.py --config config\config-eurjpy.toml
   .venv\Scripts\python scripts\fetch_broker_history.py --config config\config-gbpjpy.toml
   ```
   - `config-eurjpy.toml` exists but carries `UNVERIFIED` markers (broker symbol `EURJPYc` is
     *inferred*, `[data].symbol` is still gold, `terminal_path` unset, and `[live].mode` is off).
     v1.1 needs a verified, backtest-focused config (see pitfall 1 in the data section below — the
     current file can silently run a GOLD backtest if `--m5-csv` is omitted). Fetching EURJPYc/GBPJPYc
     requires the symbol present in the terminal's Market Watch on the connected Exness account.
   - **New:** after the CSV write, snapshot `symbol_info` + one `symbol_info_tick` and write
     `data/processed/{SYMBOL}_M5_broker.symbol.json`, then print the config block:
     ```
     saved N bars -> data/processed/EURJPYc_M5_broker.csv
     symbol_info : digits=3 point=0.001 tick=0.001/0.01(per-lot-USDc?) contract=100000 cur=JPY
     suggested backtest config:
       [strategy] sl_buffer = 0.010          # 10 * point
       [trading]  spread_assumption = 0.0007  # ask-bid snapshot at fetch
     ```
   - JPY FX calendars: crosses trade ~Sun 22:00→Fri 21:00 UTC. The `--m5-csv` path performs no gap
     detection today (that check lives only on the histdata-M1 path); weekend gaps are expected and
     harmless (strategy is bar-window based). Optional: reuse the session gap-warning only if a
     *weekday* hole is found. LOW priority.
2. **Author two backtest configs** modeled verbatim on `config/config-btc-backtest.toml` (the
   project's own template for "broker-native M5, backtest-only"):
   `config/config-eurjpy-backtest.toml`, `config/config-gbpjpy-backtest.toml`, with
   `[data] source="mt5-csv"`, `raw_dir="data/processed"`, `[live] enabled=false`, per-symbol
   `magic_number`, `sl_buffer = 10 × sidecar.point`, and `spread_assumption` from the printed value.
   Setting `[data].symbol` to a non-histdata name + `raw_dir=data/processed` makes the *histdata
   fallback branch* of the CLI glob nothing and error cleanly (see data pitfall 1).
3. **Backtest:**
   ```
   python -m trading_bot.cli backtest --config config/config-eurjpy-backtest.toml \
       --m5-csv data/processed/EURJPYc_M5_broker.csv
   ```
   CLI auto-loads the sibling `*.symbol.json`; with it present, money conversion and price rounding
   are spec-driven; without it, exactly today's behavior. A warning fires when the sidecar `symbol`
   differs from the config's data/live symbol (catches the gold-labelled-EURJPY trap).

**Scale note baked into the flow:** JPY price ~150–200 vs gold ~2600 and XAUUSD 3-dp broker quotes
mean **stop/TP arithmetic must never be authored in "pips" or cross-instrument constants** — only in
price units derived from the sidecar. R-multiple needs no scale. Money needs `tick_value/tick_size`,
not `price × contract_size`. This is what the diagram's separation enforces.

---

## (c) New vs Modified vs Must-Not-Change seam map

### New components

| Component | Responsibility | Why a new seam |
|---|---|---|
| `src/trading_bot/instrument.py` | frozen `InstrumentSpec`; `money_per_price_unit_per_lot`; `round_price`; JSON sidecar codec; `validate()` | Pure metadata type shared by fetch script (write), CLI (load), stats (money); importing `broker/base.SymbolRisk` into the backtest path would couple backtest → broker ABC. Sits next to `config.py` (stdlib-only, pure) |
| `data/processed/{SYMBOL}_M5_broker.symbol.json` | machine-readable symbol_info snapshot at fetch time | data artifact (gitignored like the CSVs) |
| `config/config-eurjpy-backtest.toml`, `config/config-gbpjpy-backtest.toml` | per-symbol backtest configs, `config-btc-backtest.toml` pattern | no schema change required |
| sidecar loader helper (in `instrument.py` or `cli.py`) | `load_sidecar_for(csv_path) -> InstrumentSpec \| None` | centralizes "discover or fall back" |
| New tests | `test_instrument.py` (codec/validation/money property), stats money+spread cases on hand-computed JPY-style trades, FakeMT5 fetch-script sidecar test, CLI-with-sidecar test | guard every new seam |

### Modified components (defaults preserve legacy behavior byte-for-byte)

| Component | Change | Backward-compat mechanism |
|---|---|---|
| `backtest/stats.py` `trade_stats()` | add optional `money_per_unit_lot: float \| None = None` and `spread: float = 0.0`. Money path: multiplier = `money_per_unit_lot * lot` when given, else `contract_size * lot` (equity, net_pnl_usd, drawdown). `spread` subtracted once per closed trade from `pnl_points` before wins/losses/R aggregates | `None`/`0.0` defaults ⇒ existing calls and the gold golden-stats tests unchanged |
| `cli.py` backtest + ai-backtest | when a sidecar exists: pass `money_per_unit_lot` and `spread` to stats; round trades.csv and decision-log prices at `spec.digits` instead of `.round(2)`; log the stats path used (legacy vs spec) | sidecar absent ⇒ today's code path exactly |
| `scripts/fetch_broker_history.py` | after saving CSV: `symbol_info`/`symbol_info_tick` snapshot → sidecar JSON + printed config block | no change to CSV output or CLI args |
| `config/config-eurjpy.toml` (+ new gbpjpy twin) | fill the `UNVERIFIED` checklist (verified broker symbol, `terminal_path`, backtest block) | editing config files only |

### Must-Not-Change seams (the (e) contract — tested by existing suite)

| Seam | Files | Why frozen |
|---|---|---|
| Pure strategy chain | `strategy/swings.py`, `levels.py`, `signals.py`, `filters.py`, `candle_reversal.py` | SAFE-01 shared backtest+live; pandas/numpy-only purity (verified: only pandas/numpy imports); untouched by any design above |
| Shared backtest+live order contract | `backtest/engine.py` (`run_backtest` signature & event-loop arithmetic), `live/engine.py` setup arithmetic (`entry=resistance, sl=support−sl_buffer, tp=…`) | golden 1:1 tests (`test_backtest.py` GOLDEN_*, `test_live_engine.py` golden frame 101.00/100.09/101.91), AI backtest reuse, ~10 research scripts call `run_backtest` |
| Broker ABC + risk semantics | `broker/base.py`, `mt5.py`, `simulated.py`, `dry_run.py` | live/demo contract; `SymbolRisk` already instrument-correct — nothing to fix here |
| CLI defaults for gold | histdata-M1 path, `list_histdata_csves`, gold runs with no sidecar | byte-identical legacy behavior pinned by `test_cli*.py` |
| Live-only JPY gaps, deferred to a LATER milestone | `live/engine.py _round2`, `broker/base.py PendingOrder.equivalent_to` (0.01 tolerance) | explicitly flagged in STATE.md:698 as live-layer 2-dp fixes; **BACKTEST-ONLY v1.1 must not touch them** (fixing them changes live dedup/rounding semantics and belongs to a live multi-instrument milestone). Note them in the roadmap as deferred debt, do not "sneak" them in |

---

## Patterns to follow

### Pattern 1: Tick-economics money conversion (copy the live layer's own fix)
`SymbolRisk` (broker/base.py:106-159) already solved "quote currency ≠ account currency" for live
risk. Its docstring shows `tick_value / tick_size` = account-currency value of a one-unit move on
one lot — no contract size, no FX table. The v1.1 stats money path must use the **same identity** for
`net_pnl_usd`/drawdown rather than re-deriving a USDJPY rate series or trusting `contract_size`.
Example of the intended stats change:

```python
def trade_stats(trades, contract_size=100.0, lot=0.01,
                money_per_unit_lot=None, spread=0.0):
    per_unit = money_per_unit_lot if money_per_unit_lot is not None else contract_size
    unit = per_unit * lot
    # pnl_points already net of `spread` once per closed trade
    equity = pnls_closed.cumsum() * unit        # legacy identical when money_per_unit_lot is None
```

### Pattern 2: Fetch-time sidecar metadata (spec travels with the data it describes)
One writer (fetch script), one reader (CLI), pure JSON, default-absent. Same philosophy as the repo's
"symbols.json"-less history: never derive contract facts from config comments or other CSVs.

### Pattern 3: Boundary-only rounding
No rounding inside the engine (raw-price records — verified none exists today). Rounding is a
**presentation-layer** concern: decision logs, per-trade CSV, stats print. `digits` from the sidecar
replaces the hard-coded `2` at exactly those boundaries. `live/engine.py._round2` stays as-is this
milestone (live seam, see must-not-change).

---

## Anti-Patterns to avoid (specific to this domain)

1. **Adding a scaling knob to the shared engine.** `run_backtest` is the most-pinned function in the
   repo (golden integration, exact-1:1, concurrency, no-lookahead, every research script). Changing
   `sl_buffer` semantics there forks backtest-vs-live arithmetic and ripples through ~10 call sites.
   The absolute-price engine is correct as-is; scale at the config/seam boundaries.
2. **Hand-typing digits/point from memory.** The codebase is *internally inconsistent* about gold
   today — `cli.py`/`stats.py` docstrings say "XAUUSD 2-dp", yet the committed broker-native
   `XAUUSDc_M5_broker.csv` holds 3-dp prices (`3133.287`) and `config-eurjpy.toml` claims gold is
   3-decimal. Never resolve that by fiat; `symbol_info` is the only authority, which is why the
   sidecar exists.
3. **`--m5-csv` fallback trap.** `config-eurjpy.toml` still points `[data].symbol = "XAUUSD"` at
   `data/raw` (gold histdata present). If a user runs the backtest **without** `--m5-csv`, the CLI
   silently backtests GOLD under an EURJPY config. The new backtest configs must use the
   `config-btc-backtest.toml` shape (`source="mt5-csv"`, `raw_dir="data/processed"`) so the histdata
   branch globs nothing and errors loudly.
4. **Treating quote-currency pnl as account currency.** `pnl_points × 100,000` on EURJPY is *yen*;
   labelling it USD is wrong by ~155× (and by 100× again on cent accounts). Only
   `tick_value/tick_size` (account currency by construction) or an explicit USDJPY conversion is
   honest. `currency_profit` is recorded for audit precisely so this never has to be guessed.
5. **Netting spread twice or not at all.** Engine ignores spread (documented limitation); the v1.0
   sweep netted "one spread per round trip" *externally*. v1.1 must net it inside stats (optional
   `spread` param), or the JPY verdict — where spread per stop-distance can be larger than gold's —
   is systematically flattering. Do not also hand-subtract in the analysis scripts.
6. **Reusing gold's `config.toml` strategy numbers as-is for JPY.** `rr_multiple`/fractal/sr_lookback
   are dimensionless and transfer; `sl_buffer` and `spread_assumption` are instrument-typed and must
   come from the sidecar print.

---

## Recommended structure (delta on the existing tree)

```
scripts/fetch_broker_history.py              MODIFIED  + sidecar write + config-block print
src/trading_bot/instrument.py                NEW       InstrumentSpec + sidecar codec
src/trading_bot/backtest/stats.py            MODIFIED  + money_per_unit_lot, spread (defaulted)
src/trading_bot/cli.py                       MODIFIED  sidecar discovery, spec.digits rounding
config/config-eurjpy-backtest.toml           NEW       (config-btc-backtest.toml pattern)
config/config-gbpjpy-backtest.toml           NEW
data/processed/{EURJPYc,GBPJPYc}_M5_broker.csv           (fetched artifact)
data/processed/{...}.symbol.json             NEW       (fetched artifact)
tests/test_instrument.py                     NEW
tests/test_backtest.py / test_stats          MODIFIED  add money/spread spec cases (defaults unchanged)
tests/test_mt5_broker.py (or new)            MODIFIED  FakeMT5 sidecar capture test for fetch path
```

Not touched: `src/trading_bot/strategy/*`, `backtest/engine.py`, `broker/*`, `live/*`, `ai/backtest.py`
(unless the v1.1 battery wants AI-gated JPY runs — see build order note).

---

## (d) Suggested build order (respects dependencies; each step leaves the suite green)

1. **P1 — InstrumentSpec core (pure, no data, no I/O).** Add `src/trading_bot/instrument.py`
   (+`tests/test_instrument.py`): dataclass, `money_per_price_unit_per_lot`, `round_price`, JSON
   codec, validation. Nothing else consumes it yet. *Suite stays green.*
2. **P2 — Stats correctness seam.** Extend `trade_stats()` with optional `money_per_unit_lot` and
   `spread` (defaults `None`/`0.0`); add hand-computed JPY-style cases (e.g. EURJPY 3-dp prices,
   entry 162.123 → verify account-currency pnl via the tick ratio; spread-netting flips a marginal
   win to a loss). Assert the legacy path is **unchanged** (existing gold stats tests already pin it).
3. **P3 — Fetch tooling + human data run.** Extend `fetch_broker_history.py` to snapshot
   `symbol_info`/`symbol_info_tick`, write the sidecar, print the config block (FakeMT5 test). Then
   a **human checkpoint on the Windows terminal**: fetch EURJPYc and GBPJPYc M5 into
   `data/processed/` (CSV + sidecar), confirm the printed block's symbol/digits/point against Market
   Watch. Write `config-eurjpy-backtest.toml` / `config-gbpjpy-backtest.toml` from the printed block.
4. **P4 — CLI wiring + end-to-end smoke.** Sidecar discovery in the `--m5-csv` path (and ai-backtest
   if the battery needs it), spec-driven digits rounding + money passing, symbol-mismatch warning.
   Smoke: run both crosses end-to-end; **re-run the committed gold backtest (no sidecar) and diff
   output against pre-change** as the regression gate; confirm 442-test suite stays green.
5. **P5 — Verdict battery (the v1.1 scientific deliverable, analysis-heavy).** Run the project's
   falsification battery on both crosses using the existing research-script pattern (noise
   calibration on |t|, walk-forward fit→test, random-entry `setup_override` coin-flip controls,
   monthly stability) *net of spread*, plus the half-split reproduction of the v1.0 numbers. This is
   where the "real but too small" vs "noise" verdict is produced. If AI-gated comparison is wanted,
   add `--m5-csv` to the `ai-backtest` subcommand (currently missing — a small CLI delta) before P5.

**Dependency logic:** P1→P2→P4 are pure/backward-compatible code layers that can each land with tests
independent of any data; P3 needs the human/terminal checkpoint and unblocks real runs; P5 needs all
four. Nothing in P1–P4 depends on strategy/live/broker changes, which is why those stay frozen.

---

## (e) Seams that must NOT change (restated as test-guarded invariants)

- `src/trading_bot/strategy/*`: pandas/numpy-only; no instrument inputs added; no data/broker/logging
  imports. (Purity grep test exists and must keep passing.)
- `backtest/engine.py`: `run_backtest` signature and all event-loop conventions unchanged; no new
  kwargs for instrument metadata; raw-price records; no rounding introduced.
- Golden tests: `test_backtest.py` `GOLDEN_*` two-trade frame and exact 1:1; `test_live_engine.py`
  golden-frame 101.00/100.09/101.91; `test_cli*.py` gold runs — all byte-identical, because they
  exercise the default (`None`/no-sidecar) paths only.
- `broker/*` ABC + `live/*`: untouched this milestone. `_round2` (live engine) and
  `PendingOrder.equivalent_to`'s 0.01 tolerance remain gold-era — **explicitly deferred** to a live
  multi-instrument milestone, and noted as debt in the roadmap rather than silently changed.

---

## Open questions / research flags for the roadmap

- **Actual EURJPYc/GBPJPYc contract numbers** (digits, point, tick_value, symbol suffix on the
  connected Exness account) are unverifiable from the repo — `config-eurjpy.toml` marks `EURJPYc`
  UNVERIFIED. P3's human checkpoint answers this; the architecture deliberately does not depend on
  the values. **MEDIUM confidence** until then.
- **Whether the v1.1 battery includes AI-gated runs on JPY** decides if `ai-backtest` gains
  `--m5-csv`. Default recommendation: the verdict is about the deterministic breakout edge — keep
  AI out of v1.1 scope unless a gated comparison is explicitly wanted.
- **`spread_assumption` is currently dead config** (declared in `[trading]`, never read by code —
  verified by grep). P2 is the natural place to finally consume it (net-of-spread stats).
- **JPY weekend gaps in the `--m5-csv` path** are not currently gap-checked; expected and harmless
  for a window-bounded strategy — decide whether to warn on weekday-only holes (LOW priority).
- **`_round2`/`equivalent_to` live fixes**: deliberately out of scope; carry them on the roadmap as a
  named follow-up so they are not forgotten when the live layer eventually trades JPY.

## Sources

- Repo (read directly, HIGH): `src/trading_bot/backtest/engine.py`, `backtest/stats.py`,
  `cli.py`, `config.py`, `broker/base.py`, `broker/mt5.py`, `broker/simulated.py`,
  `live/engine.py`, `data/loader.py`, `scripts/fetch_broker_history.py`, `strategy/{swings,levels,signals}.py`,
  `tests/test_backtest.py`, `config/config-eurjpy.toml`, `config/config-btc-backtest.toml`,
  `data/processed/XAUUSDc_M5_broker.csv` (3-dp evidence).
- Planning docs (HIGH): `.planning/STATE.md` §Multi-Instrument Finding (2026-08-20) — the documented
  gap list (lines ~690-699); `.planning/PROJECT.md` v1.1 milestone; `.planning/quick/007-btc-separate-account`
  (BTC 10×point precedent).
- Instrument numeric parameters (digits/point/tick per EURJPYc/GBPJPYc): **LOW / verify at P3** via
  `symbol_info` — deliberately not asserted here.

---
*Architecture research for: instrument-correct EURJPY/GBPJPY M5 backtesting integration (v1.1, backtest-only)*
*Researched: 2026-09-07*
