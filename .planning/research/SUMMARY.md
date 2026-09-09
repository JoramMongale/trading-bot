# Project Research Summary

**Project:** Gold 5m Breakout Bot (multi-instrument extension)
**Milestone:** v1.1 JPY-Cross Breakout Investigation (EURJPY / GBPJPY)
**Domain:** Internal falsification-campaign milestone — BACKTEST-ONLY verdict on whether the swing-breakout edge is real on JPY crosses, using instrument-correct backtests + the project's own rigorous control battery
**Researched:** 2026-09-07
**Confidence:** HIGH on what to build and how to order it (machinery scope, phase structure); MEDIUM on external Exness/FX broker facts that must be verified from the terminal at data-fetch time

## Executive Summary

The "product" of this milestone is not software — it is a **defensible verdict document** that decides whether EURJPY (+0.135R) and GBPJPY (+0.121R), the only two instruments positive in both halves of the v1.0 17-symbol split test, carry a real edge. All four research files converge on one reading of the situation: v1.0's JPY numbers are **hypothesis-generating, not confirmatory** — the pair was selected best-of-17 on the same window, t≈1.95 at ~100 trades sits inside the noise bar, and the magnitudes were measured with an instrument-incorrect spread model (gold's $0.26 on a JPY cross produced a bogus 68%-of-risk cost; the real figure is ~4% of risk vs gold's ~1.2%). The investigation must therefore hold these two instruments to the exact battery that falsified every gold candidate (short-side, ORB, volatility, HTF, candle-reversal): beat a noise calibration that **counts the inherited v1.0 look**, survive chronological walk-forward, beat random-entry controls, show monthly stability, and clear a **buy-and-hold drift benchmark** — because a long-only breakout on 2025's drifting/weak-JPY tape collects drift and carry with no edge at all.

The recommended approach has three parts, and all four research agents independently map them to the same three-phase order. **(1) Machinery first:** a minimal, pure `InstrumentSpec` sidecar captured from the terminal at fetch time, plus an optional stats money/spread seam and CLI rounding at `spec.digits` — with **zero changes** to the pure strategy chain, the `run_backtest` event loop, the broker ABC, or the live engine, and gold/BTC behavior byte-identical (legacy defaults). **(2) Data second:** fresh broker-native EURJPYc/GBPJPYc M5 history (one vendor, one account type, dataset cards, clock/spread verification at a human Windows-terminal checkpoint). **(3) Verdict last:** a pre-registered battery with a three-way verdict taxonomy (CONFIRM / REAL-BUT-NEGLIGIBLE / FALSIFIED) whose thresholds are written before any confirmatory run.

Key risks and mitigations: (i) **selection multiplicity** — treat EURJPY+GBPJPY as ~1 correlated family test (shared JPY leg), recalibrate the |t| bar over the full count of tries including the v1.0 best-of-17 look (best-of-39 |t|=2.46 is beaten by pure noise 42% of the time in this project's own calibration); (ii) **cost error class** — spread must be modeled in JPY price units from the broker spec, structurally incapable of receiving gold's dollar spread; (iii) **drift confound** — buy-and-hold benchmark per cross is non-negotiable; (iv) **scope discipline** — backtest-only means dedicated backtest configs, a CLI guard against `[live] enabled`, live gold/BTC configs and agents untouched, and the known live-layer 2-dp debt (`_round2`, `PendingOrder.equivalent_to`) explicitly deferred to a future live-wiring milestone.

## Key Findings

### Recommended Stack (from STACK.md)

**No new third-party dependencies.** This is a symbol-spec *plumbing* milestone, not a dependency problem. Everything is already in the venv: Python 3.12.10, pandas 3.0.5 (CoW semantics pinned), numpy 2.5.2, MetaTrader5 5.0.6090 (upgrade to **5.0.6180**, PyPI 2026-09-05, at the start of the data-acquisition phase to match the running Exness terminal build).

**Core technologies (unchanged):**
- Python 3.12 + pandas 3.0.5 + numpy 2.5.2 — existing pure strategy chain and backtester; no change
- MetaTrader5 pip 5.0.6090 → **5.0.6180** — broker-native M5 fetch is already the data source; one-build-behind package tracks terminal build
- `scripts/fetch_broker_history.py` (exists) — extend to write a per-symbol spec sidecar + print a ready-to-paste config block
- `SymbolRisk` tick-economics trick from the live layer (`broker/mt5.py`) — the in-repo, battle-tested pattern for quote-currency ≠ account-currency; the backtest money path must copy `tick_value / tick_size` (already account currency), never re-derive USDJPY or trust `contract_size`

**JPY-cross conventions (research answers):**
- 3-dp quoting (`digits=3`, `point=0.001`, `tick_size=0.001`); 1 pip = 0.01 price = 10 points — MEDIUM-HIGH industry rule, **verify via `symbol_info()` at fetch**
- Spread: Exness stable-spread list, "from 0.3 pips" → plan 0.3–1.0 pip = 3–10 points; median JPY stop ~0.381 price → 1 pip spread ≈ **2.6% of risk** (~4% planning figure) vs gold's ~1.2% — **never reuse gold's spread**
- Cent account: EURJPYc/GBPJPYc exist, cent lot = 0.01 standard lot, `trade_contract_size` from the terminal is the authority
- M5 history depth: **empirical** (~100k bars ≈ ~1–1.5 FX years); raise Tools → Options → "Max. bars in chart" before the deep fetch — must be a data-acquisition checkpoint, not an assumption
- Per-bar `spread` column (points) is already in MT5 rate tuples but currently dropped on CSV export — keep it

**What NOT to use:** backtrader/vectorbt/numba/TA-Lib, ccxt/yfinance/Dukascopy/OANDA, hardcoded Exness spec tables, histdata for this milestone (lacks cent symbols + spread, stale), engine-level spread/fill modeling, `_round2`/`equivalent_to` digit fixes (live-layer debt), a warehouse for the verdict, and an optional concurrent USDJPY fetch (only needed if money-accurate cross-year P&L matters — **skip: the verdict battery is R-primary**).

### What the Investigation Must Contain to Be Defensible (from FEATURES.md)

**Table stakes (P1 — the verdict is unattainable without each):**
- **TS-1** Instrument-correct symbol/config plumbing for both crosses (spec from broker `symbol_info`; `config-eurjpy.toml` is currently UNVERIFIED and points `[data]` at gold)
- **TS-2** Fresh broker-native M5 data, gold-scale depth, coverage validation; one vendor across train/test/full sample
- **TS-3** Data-continuity validation on a 24/5 feed (weekly ~48h gaps are *normal*); assert ~100% bar consumption (a 58%-consumption stall once fabricated +0.15R)
- **TS-4** Honest spread model in instrument price units, netted once per round trip — R-net-of-spread is the judgment currency
- **TS-5** Full-sample honest stats per cross (~100k bars → a few hundred trades → |t| machinery becomes meaningful)
- **TS-6** Multiplicity-corrected |t| bar — inherits the v1.0 best-of-17 look + every pre-declared config; EURJPY/GBPJPY counted as ~1 correlated family test
- **TS-7** Fit→test walk-forward (the test that exposed gold's front-loading)
- **TS-8** Random-entry coin-flip control through the real engine (`setup_override` seam exists)
- **TS-9** Monthly stability breakdown (gold's edge was Jul–Dec 2025 only; JPY must not be 2025-only)
- **TS-10** Verdict taxonomy with pre-registered thresholds — "Confirm" has never been reached in this project; it must be defined before results
- **TS-11** Economic-meaning check — real means real at 0.01 lots on the cent account: stop-distance distribution, spread as % of risk, affordability at real balance (gold: 0/340 setups passed the 2% gate)
- **TS-12** Drift/buy-and-hold benchmark per cross (BTC: bot +$30.69 vs hold +$135.81; gold short-side: +54% drift, drift-neutral estimate +0.04R)

**Differentiators / decision hygiene:** D-1 pre-registered analysis plan (prereq of TS-6 — closes the config set before results), D-4 correlation-aware framing (~1 family), D-5 falsified-vs-negligible decision rule, D-7 engine-consumption + slot-starvation audit (P1). Post-CONFIRM only: D-2 spread-robustness sweep (1×/1.5×/2×), D-3 session/liquidity characterisation (descriptive, never a filter), D-6 swing-mechanism ablation.

**Anti-features (each invalidates the verdict):** A-1 per-pair param mining until t≈1.95 becomes t>2.5 (circular — the retest IS the OOS test of the best-of-17 selection); A-2 re-sliding the walk-forward boundary; A-3 ignoring spread / treating dead `spread_assumption` as a model; A-4 gold's $ spread on a JPY cross (~17× wrong); A-5 judging on points/P&L instead of net-of-spread R; A-6 treating the two crosses as two confirmations; A-7 rescue-filtering with session/vol (each rescued variant is a new hypothesis needing its own battery); A-8 demo/live wiring before the verdict; A-9 mixing data vendors; A-10 calendar mining monthly buckets; A-11 multi-pair expansion (each new instrument is a new pre-registered test).

**Verdict taxonomy (pre-registered):** **CONFIRM** = whole battery survives with tradeable net R at 0.01 lots (spread ≤ ~5% of median stop) → justifies a v1.2 tradeability/demo milestone. **REAL-BUT-NEGLIGIBLE** = beats random controls / ablation shows the mechanism, but fails OOS or monthly, or net R below the economic floor (mirror of HTF: R+0.013, t+1.04) → clean negative, no live path. **FALSIFIED (noise/front-loaded)** = loses to random-entry, or |t| below the calibrated bar, or OOS flips sign, or 2025-only monthly → stop, family joins the falsified list. **Plus an honest fourth outcome: UNDER-POWERED, INCONCLUSIVE** if n cannot separate the hypotheses (see pitfalls).

### Architecture Approach (from ARCHITECTURE.md)

**Headline, verified in code:** instrument-correct EURJPY/GBPJPY backtesting does **not** require touching the pure strategy chain, `run_backtest`, the BrokerClient ABC, or the live engine. The strategy chain and event loop are dimensionless in money (raw-price floats, zero rounding in engine.py); only the money conversion (`stats.py`: `pnl_points × contract_size`, gold's 100 oz/lot, assumes quote==account currency) and CLI display rounding (`.round(2)`) encode wrong single-instrument assumptions. Copy the live layer's `SymbolRisk` trick: `money_per_price_unit_per_lot = tick_value / tick_size` — account currency by construction.

**Major components:**
1. **`InstrumentSpec`** (`src/trading_bot/instrument.py`, NEW pure stdlib module) — frozen dataclass (symbol, digits, point, tick_size, tick_value, contract_size, volume grid, currency_profit audit field, spread_snapshot) + `money_per_price_unit_per_lot` property (NaN-guarded) + `round_price` + JSON sidecar codec + validate. Never derived from memory — read from `symbol_info()`/`symbol_info_tick()` at fetch time.
2. **Spec sidecar artifact** (`data/processed/{SYM}_M5_broker.symbol.json`, NEW) — one writer (fetch script), one reader (CLI); travels with its CSV so re-running old data uses specs true at fetch time; sidecar absent ⇒ legacy gold/BTC path byte-identical.
3. **Stats money/spread seam** (`backtest/stats.py`, MODIFIED) — optional `money_per_unit_lot` and `spread` params; defaults `None`/`0.0` preserve legacy exactly; spread netted once per closed trade inside stats (finally consumes the dead `spread_assumption`).
4. **CLI digits seam** (`cli.py`, MODIFIED) — sidecar discovery next to `--m5-csv`, round trades.csv/decision logs at `spec.digits`, symbol-mismatch warning, config-block print; engine stays full-precision.
5. **Fetch tooling** (`scripts/fetch_broker_history.py`, MODIFIED) — after CSV write, snapshot symbol_info + one tick → sidecar + printed TOML config block (`sl_buffer = 10 × point`), keep the per-bar spread column.
6. **Dedicated backtest configs** — `config-eurjpy-backtest.toml` / `config-gbpjpy-backtest.toml` on the `config-btc-backtest.toml` pattern (`source="mt5-csv"`, `[live] enabled=false`) so the histdata glob errors loudly instead of silently backtesting gold under an EURJPY config.

**Must-NOT-change seams (test-guarded invariants):** `strategy/*` (purity grep), `backtest/engine.py` `run_backtest` signature/arithmetic, `broker/*` ABC + live risk, `live/*` (`_round2`, `equivalent_to` — deferred debt for a live-wiring milestone), CLI gold defaults. Boundary-only rounding: rounding is a presentation concern, never inside the loop.

### Critical Pitfalls (from PITFALLS.md)

Top pitfalls to design around (full pitfall-to-phase map in PITFALLS.md):

1. **Statistical: v1.0 ranking winners ≠ pre-registered hypothesis.** Re-running on the same calendar window is re-measurement, not confirmation. Mitigate: pre-register the hypothesis + decision rule; demand a genuinely fresh OOS tail (data v1.0 never saw) or discount by the v1.0 look. *(B1 — Phase 3)*
2. **Statistical: best-of-N mining + correlated family.** "Both crosses t≈2" is ~one t≈2 test under a shared JPY leg (expect corr ≳0.8, measure it). Every config actually tried goes into the max-|t| calibration. *(B2 — Phase 3)*
3. **Statistical: low power and three-way verdict discipline.** n≈100–200 cannot separate hypotheses (need ~375 trades for 80% power at R≈0.13, sd≈0.9); "not significant" ≠ falsified, t≈1.95 ≠ edge. Pre-commit positive / falsified / **underpowered-inconclusive**. *(B4 — Phase 3)*
4. **Quoting/units: JPY 3-dp vs 2-dp artifacts, and the 100× money class.** `contract_size`-money on FX is wrong by 100×–1000× (gold's two 100× errors cancelled on cent — "plausible nonsense"); 2-dp output rounding quantizes the working third decimal. Mitigate: spec-driven value-per-point money (or label money meaningless), round at `spec.digits` only at output boundaries. *(A2/A3 — Phase 1)*
5. **Spread: v1.0 JPY magnitudes are contaminated + flat-subtraction is optimistic.** Gold's $0.26 on a JPY cross made cost 68% of risk instead of ~4%; net-R moving >0.02R when spread is halved means the verdict is spread-dominated. Spread in JPY units with a unit assertion; halve/double sensitivity sweep. *(C3 + A4 — Phase 1/2/3)*
6. **Data: mixing vendors, unverified clocks, and the symbol-label trap.** Broker vs histdata changed gold's PF 1.29→1.22; `config-eurjpy.toml` still carries `[data] symbol = "XAUUSD"` (silent gold-run-under-EURJPY-label trap); bar clock is per-source (Exness server time is not guaranteed UTC). *(C1/C2/C4 — Phase 2)*
7. **Drift/carry confound on trending crosses.** Long-only breakouts book drift as R; 2025's JPY weakness + carry paid longs. Buy-and-hold comparison and random-entry/mirror rows are mandatory report sections. *(B5 — Phase 3)*
8. **Integration: don't touch the pure chain, don't break byte-identical defaults, don't go live.** Zero edits in `strategy/*` + the event loop; new params carry legacy defaults; dedicated backtest configs; CLI refuses `[live] enabled`; never restart gold/BTC agents; `_round2`/`equivalent_to` stay out of a backtest-only milestone. *(D1–D5 — Phase 1 scope)*

## Implications for Roadmap

All four research files converge on the same three-phase skeleton (PITFALLS.md names it explicitly; FEATURES.md's dependency tree orders TS-2/TS-1 first and feeds everything into the verdict; ARCHITECTURE.md's P1–P5 build order groups cleanly into it). **Machinery → data → battery+verdict.**

### Phase 1: Instrument-Correct Backtest Machinery
**Rationale:** Pure, data-independent, backward-compatible code that every later number inherits; the only phase with real regression risk (golden pins, shared chain), so it must land first with the suite as its tripwire. Architecturally it is ARCHITECTURE.md build steps P1, P2, and the code part of P4.
**Delivers:** `src/trading_bot/instrument.py` (`InstrumentSpec` + sidecar codec + `tests/test_instrument.py`); `trade_stats()` optional `money_per_unit_lot`/`spread` seam with hand-computed JPY money/spread cases (legacy path asserted unchanged); CLI sidecar discovery + `spec.digits` rounding + symbol-mismatch warning; a **symbol-consistency assertion** (config symbol must match loaded file — makes the gold-labelled-EURJPY trap fail loudly); **CLI guard refusing `[live] enabled`**; dedicated `config-*-backtest.toml` templates; optional `sl_buffer_points` config form (mutually exclusive with legacy `sl_buffer`, default unchanged).
**Addresses features:** TS-1, TS-4 seam (stats-level), D-7 foundations.
**Avoids pitfalls:** A1, A2, A3 (unit/money/rounding classes), C4 symbol-label, D1, D2, D3, D5.
**Exit gate:** full 442-test suite green with **zero edits to golden pins or strategy modules**; gold/BTC backtest output byte-identical (diff, not "tests passed"); no diff touching `strategy/*`, `backtest/engine.py`, `broker/*`, `live/*`.

### Phase 2: Broker-Native JPY Data + Dataset Integrity
**Rationale:** The verdict is only as honest as its substrate (broker-native beats vendor on gold); fetch tooling extension (ARCHITECTURE P3) plus a **human Windows-terminal checkpoint** is the only way to resolve the MEDIUM/LOW-confidence Exness facts — nothing about EURJPYc/GBPJPYc should be trusted from a config comment or this research.
**Delivers:** fetch script sidecar write + per-bar spread column + printed config block (FakeMT5 tests); MetaTrader5 package upgrade to 5.0.6180; human checkpoint reading `symbol_info`/`symbol_info_tick` off the real terminal (digits/point/contract/tick_value/spread snapshot) and confirming against Market Watch; fetch EURJPYc + GBPJPYc M5 to exhaustion with "Max. bars in chart" raised; **dataset cards** (source, symbol, span, bar count, clock anchor vs a known event, spread source/median); per-instrument schedule/clock verification (FX Fri/Sun close, daily rollover — gold's weekend guard hours do NOT transfer); finalize backtest configs from the machine-printed values; end-to-end smoke on both crosses + gold no-sidecar regression diff.
**Addresses features:** TS-2, TS-3, completes TS-4; inputs TS-11.
**Avoids pitfalls:** C1 (single-source discipline), C2 (clock), C3 (spread capture), C4 (fetch/naming/staleness), C5 (maximize honest span).
**Exit gate:** both crosses carded with verified symbol identity, clock anchor, and spread; configs carry terminal-verified numbers.

### Phase 3: Pre-Registered Falsification Battery & Verdict
**Rationale:** The scientific deliverable; its credibility rests entirely on closing the test set *before* results (TS-6 requires D-1). PITFALLS B1–B6 are all decision-rule failures, not computation failures.
**Delivers:** **D-1 pre-registration first** (fixed params = gold's committed values; config grid; split boundary; monthly granularity; random-seed count; calibrated |t| threshold; the CONFIRM / REAL-BUT-NEGLIGIBLE / FALSIFIED / UNDER-POWERED taxonomy with threshold values). Then the battery on both crosses net of spread: TS-5 full-sample stats; TS-6 multiplicity calibration **counting the inherited v1.0 best-of-17 look + every pre-declared config**, with TS-3-style consumption audit (D-7); D-4 measured EURJPY/GBPJPY correlation and a pooled family verdict; TS-7 chronological walk-forward (all folds reported, later folds carry the verdict); TS-8 random-entry controls via `setup_override`; TS-9 fixed monthly table with noise band (flag intervention months); TS-12 buy-and-hold drift benchmark; TS-11 economic check (stop dist, spread % of risk, affordability at 0.01 lots); D-2 spread-robustness sweep if heading CONFIRM. Output: verdict report mapping each gate to the taxonomy cell.
**Addresses features:** TS-5 through TS-12, D-1, D-4, D-5, D-7 (+D-2 if CONFIRM-tracking).
**Avoids pitfalls:** B1 (pre-registration, fresh OOS), B2 (calibration over all tries), B3 (multi-fold + monthly), B4 (power statement + three-way rule), B5 (drift benchmark + random-entry), B6 (R/day cross-check).
**Exit gate:** a written verdict cell with every gate number, n/SE/power stated, calibration line present, and no metric mixing data sources.

### Phase Ordering Rationale
- **Code before data:** Phase 1 is pure and testable with zero data; its regression risk (shared chain, golden pins) is best isolated first, and Phase 2's checkpoint prints the exact values Phase 1's seams consume.
- **Data before verdict:** every battery element depends on the carded broker-native substrate (FEATURES dependency tree: TS-2 → everything); the human checkpoint in Phase 2 resolves the facts no research agent could confirm.
- **Pre-registration before confirmatory runs:** the single most important ordering constraint inside Phase 3 — the config count, boundary, and threshold table must exist before TS-5/6/7/8/9 execute, or TS-6 is theatre.
- **Scope walls:** Phase 1's zero-edit + byte-identical + `[live]`-refusal guards make "backtest-only" structural rather than aspirational; the live-layer 2-dp debt and any session/filter hypothesis that emerges from D-3 are *named* deferred items, not free fixes.

### Research Flags
Needs targeted verification during planning/execution (terminal-side, not a separate research agent):
- **Phase 2:** Exness EURJPYc/GBPJPYc symbol facts (digits/point/tick_value/contract, cent vs standard), server-time/clock basis, real spread levels, and M5 history depth — unverifiable from any source consulted (Exness pages returned generic content; no web tooling in the research env). Built into the Phase 2 human checkpoint; MEDIUM→HIGH only after the terminal is read.
- **Phase 3:** required-n/power for the effect size of interest (~0.10–0.15R at ~0.85 trades/day) and the realized pair correlation — computable internally on acquired data, not external research.

Phases with well-documented/standard patterns (skip research-phase):
- **Phase 1:** repo-read architecture, existing TDD + golden-test conventions, `SymbolRisk`/`config-btc-backtest.toml` precedents — HIGH confidence, no external unknowns.
- **Phase 3 battery mechanics:** the calibration, control, and monthly-stability methods are the project's own established battery (HTF/ORB/vol/short-side precedents in `.planning/quick/`).

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH (seam) / MEDIUM (Exness numbers) / LOW (M5 depth) | No new deps, seams repo-verified; broker facts & history depth are verify-at-fetch items |
| Features | MEDIUM-HIGH | Methodology + existing-capability claims HIGH (project record); JPY microstructure MEDIUM; pair correlation LOW-MEDIUM, to be measured on acquired data |
| Architecture | HIGH | Code read directly; integration design MEDIUM; instrument numerics LOW **by design** (never asserted from memory — read from `symbol_info`) |
| Pitfalls | HIGH (repo-sourced) / MEDIUM (FX broker conventions) | Statistical/integration findings sourced from the project record; histdata naming & Exness specifics flagged for terminal verification |

**Overall confidence:** HIGH on the roadmap question (what to build, in what order, what must not change); MEDIUM on external FX/Exness facts that Phase 2's human checkpoint is designed to resolve. No area is LOW enough to block requirements definition.

### Gaps to Address
- **Exness symbol facts** (digits/point/tick_value/contract per EURJPYc/GBPJPYc on the actual account): resolve at the Phase 2 terminal checkpoint; the architecture deliberately does not depend on the values.
- **M5 history depth served** (~100k bars ≈ 1–1.5 FX years is an estimate from the gold/BTC fetches): empirical checkpoint; affects whether a 2025→2026-style split and the v1.0-untouched OOS tail are achievable.
- **Realized EURJPY/GBPJPY correlation** (expected ≳0.8, unmeasured): measure in Phase 3 and set the family test threshold under it.
- **Bar-clock basis** per source (Exness server time is not guaranteed UTC): anchor-verify in Phase 2 and record in the dataset card before any session/schedule reasoning.
- **Spread distribution** (per-session median/percentiles, rollover widening): needed for D-2's robustness sweep; capture in Phase 2's fetch window.
- **Power feasibility:** whether ~13–14 months of data can separate the hypotheses at all; "UNDER-POWERED, INCONCLUSIVE" is a legitimate, pre-committed verdict outcome.
- **Dead `spread_assumption` config:** repurpose it into the spec-driven stats spread field (ARCHITECTURE P2) rather than leaving a lying knob.
- **Deferred live debt:** `_round2` / `PendingOrder.equivalent_to` (per-symbol tolerance/digits) belong to a future live-wiring milestone — carry as a named roadmap item so it is not forgotten and not smuggled into v1.1.
- **Points of divergence between research files (all resolved for the roadmap):**
  - *Spread seam placement* — FEATURES left engine-level vs post-engine open; STACK/ARCH resolve to **stats-level netting** (optional `spread` param, engine stays cost-free). Adopt stats-level.
  - *sl_buffer mechanism* — ARCH leans config-authoring from the machine-printed `10 × point` value; PITFALLS/STACK lean a new optional `sl_buffer_points` field. Compatible; adopt the optional spec-driven field with mutual-exclusion validation as the more foolproof form, legacy default untouched.
  - *histdata pre-2025 supplement* — STACK rejects histdata outright for this milestone; PITFALLS allows a separately-carded supplement never pooled. Adopt: broker-native only for the verdict; histdata only as an explicitly separate exploratory card if span is short.
  - *USDJPY concurrent fetch* — STACK optional for money accuracy; FEATURES/A2 deem money secondary. Adopt: skip — money uses `tick_value/tick_size`, verdict is R-primary.
  - *AI-gated runs in the battery* — ARCH open question, default keep AI out of v1.1. Adopt default unless the gated comparison is explicitly wanted.

## Sources

### Primary (HIGH confidence)
- Research files (this directory, 2026-09-07): `STACK.md`, `FEATURES.md`, `ARCHITECTURE.md`, `PITFALLS.md` — the four synthesized reports; per-file sources cited within each
- `.planning/STATE.md` (project record 2026-08-20→09-07): v1.0 multi-instrument results, best-of-39 noise calibration (42% noise beats |t|=2.46), invalid $0.26-JPY-spread row (68% vs ~4% of risk), broker-vs-histdata gap (PF 1.29 vs 1.22), split-sample instability (XAUUSD +0.092→−0.005), cent-account 100× cancellation, front-loading artifact, drift measurements, live 2-dp debt — HIGH
- Repo code read directly (ARCHITECTURE/PITFALLS): `backtest/engine.py`, `backtest/stats.py`, `cli.py`, `config.py`, `broker/{base,mt5}.py`, `live/engine.py`, `data/loader.py`, `scripts/fetch_broker_history.py`, `strategy/*`, `tests/test_backtest.py`, `config/config-eurjpy.toml`, `config/config-btc-backtest.toml`, `data/processed/XAUUSDc_M5_broker.csv` — HIGH
- `.planning/PROJECT.md` (v1.1 scope, backtest-only, live bots), `.planning/milestones/v1.0-ROADMAP.md` (shipped capabilities, golden pins, SAFE-01), `.planning/quick/*` verdict precedents (HTF real-but-negligible, ORB/vol/short-side falsifications) — HIGH
- Exness Help Center (Standard Cent account, Forex, About spread) — HIGH for existence/cent structure; MEDIUM for numeric spread range
- MQL5 docs (CopyRates bar availability + per-bar spread), PyPI metatrader5 5.0.6180 — HIGH

### Secondary (MEDIUM confidence)
- EarnForex 5-dp/3-dp quoting guide — MEDIUM-HIGH (industry convention; verify per broker)
- Wikipedia FX market hours (~24/5 Sun 22:00→Fri 22:00 UTC; turnover geography) — HIGH hours / MEDIUM specifics
- Exness trading-conditions pages — attempted, generic only (no authoritative numeric confirmation) — must be read off the terminal in Phase 2

### Tertiary (LOW confidence)
- fxfinds.com cent contract-size corroboration — LOW (third party; corroborates Exness wording)
- histdata.com current download naming (`HISTDATA_COM_ASCII_*`, not the repo's `DAT_ASCII_*` glob) — MEDIUM observed-on-page; verify against actual downloaded files
- General FX knowledge (pair correlation, BoJ intervention/carry tail risk) — LOW-MEDIUM; deliberately framed as *to-be-measured-on-acquired-data* (D-4 measures correlation; TS-9/TS-12 measure drift/carry)

---
*Research completed: 2026-09-07*
*Ready for roadmap: yes*
*Note: workspace is not a git repository (per PROJECT.md) — commit/tag workflow steps skipped by project convention.*
