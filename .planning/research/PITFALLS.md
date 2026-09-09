# Pitfalls Research

**Domain:** Adding EURJPY/GBPJPY JPY-cross breakout backtests to an existing single-instrument (gold XAUUSDc) Python/MT5 trading system — v1.1, BACKTEST-ONLY.
**Researched:** 2026-09-07
**Confidence:** HIGH for repo-sourced integration/statistical findings; MEDIUM for FX broker conventions and histdata naming (verify in Phase 2); see Sources for per-claim confidence.

## Critical Pitfalls

Grouped by the four risk classes the milestone must survive, then integration.
Each entry gives the failure mode, root cause, prevention, warning signs, and
the v1.1 phase that should own the prevention (suggested phase names below).

**Suggested v1.1 phase structure this document maps to:**
- **Phase 1 — Instrument-correct backtest machinery** (per-symbol spec: point/digits/contract/value-per-point/spread; buffer in points; stats guard; symbol-consistency assertions)
- **Phase 2 — Broker-native JPY data + dataset integrity** (fetch, clock/spread verification, spec capture, dataset card)
- **Phase 3 — Pre-registered falsification battery & verdict** (noise calibration over the whole experiment, walk-forward, controls, monthly stability, decision rules)

---

### A. Cross-currency risk / quoting mistakes (the 100x class)

### Pitfall A1: `sl_buffer` is a raw price, so its meaning silently changes per symbol (pip/point confusion)

**What goes wrong:**
`sl_buffer` (default `0.01`, validated `> 0` in config.py) is a *price* constant subtracted from support. Its economic size is defined by the symbol's `point`. The committed `0.01` is 10 points on 3-dp gold **and** on a 3-dp JPY cross (1 pip), but **100 pips** on a 5-dp EURUSD — and the multi-instrument study already found the committed value would be catastrophic on EURUSD. A JPY config that "carries gold's value over because both are 3-dp" is relying on a coincidence (config-eurjpy.toml checklist item 2 calls this out explicitly).

**Why it happens:**
The pure strategy chain is price-unit-agnostic, so nothing in detection flags a buffer that is the wrong size. The buffer only matters at the stop, and a stop 100 pips below support on EURUSD never looks "broken" to code that has no symbol concept.

**How to avoid:**
Express the buffer in *points* (or pips) in the instrument spec and convert to price at the backtest boundary: `buffer_price = buffer_points * point`, where `point` comes from the spec. `buffer_points = 10` reproduces gold exactly (10 × 0.001 = 0.01), reproduces the BTC backtest convention (10 × 0.01 = 0.10), and gives the intended 1-pip JPY buffer. Validate per-symbol that the computed stop distance is sane (a few pips to a few hundred pips), never a silent multiple.

**Warning signs:**
- A config's `sl_buffer` value is justified by "same as gold" rather than by the symbol's `point × 10`.
- Stop distances in *price* look identical across symbols with different `digits` (suspicious when they should scale with volatility).
- Backtest `trades.csv`/logs show JPY stops ≥ 1.00 price units (100+ pips) for what should be ~0.3–0.5 (30–50 pip) structural stops.

**Phase to address:** Phase 1 (instrument spec + buffer-in-points). Phase 2 verifies `point`/`digits` from the actual terminal before numbers are trusted.

---

### Pitfall A2: `contract_size`-based money conversion (100 oz/lot gold) applied to FX → wrong-by-100×–1000× "USD" P&L, and the cent-account cancellation that hides it

**What goes wrong:**
`backtest/stats.py` computes `net_pnl_usd`/`max_drawdown_usd` as `pnl_points × contract_size × lot`. `contract_size = 100` is gold's oz-per-lot; a JPY cross is ~100,000 base units per standard lot (and ~1,000 per cent-account lot), and its profit currency is **JPY**, not the account currency. Both factors are wrong at once, in opposite directions, exactly the bug STATE.md documents: on the cent account gold's two 100× errors cancelled into "plausible nonsense" — and the v1.0 cross-instrument study found the same class producing $0.00 vs $2.19 vs $209.84 risk estimates across EURUSD/EURJPY/USTEC. USD money stats for JPY crosses are meaningless until value-per-point comes from the broker.

**Why it happens:**
Gold's number worked by luck (contract=100, USD account, USD profit currency), so every downstream money path was built and tested on it. R-multiple is the safe metric (scale-free: price units cancel) — which is why the cross-instrument study ranked by avg R — but net P&L, drawdown, and any "risk in USD" readout silently carry the poison.

**How to avoid:**
- Keep the **decision metric on R** (avg R, R/day, t over R), which is currency-safe.
- For money stats, require a per-symbol value-per-point supplied from the broker's `trade_tick_value / trade_tick_size` (already in account currency, per `SymbolRisk`) captured at data-fetch time and stored in the dataset card — do **not** derive money from `[trading] contract_size` for FX.
- Label `net_pnl_usd`/`max_drawdown_usd` "not meaningful — no value-per-point spec" when the spec is absent, instead of emitting a confident wrong number. When the live engine later trades JPY it already sizes off tick_value, so the backtest must use the *same* basis to stay comparable.

**Warning signs:**
- Any backtest report showing JPY-cross "net USD P&L" that didn't come from a value-per-point spec.
- Config comments saying `contract_size` is "backtest-only" or "left at gold's value because data is still gold" (both true today in config-eurjpy.toml — a trap waiting for the data to be fixed but the number not to be).

**Phase to address:** Phase 1 (stats guard + spec-driven money conversion).

---

### Pitfall A3: 2-dp assumptions silently corrupt 3-dp JPY prices in backtest artifacts

**What goes wrong:**
`cli.py` rounds emitted decision-log fields and `trades.csv` price columns to 2 dp (`round(v, 2)`), and `_round2` in `live/engine.py` (imported by `ai/engine.py`) is a hard 2-dp round. JPY crosses quote to **3 decimals** (point 0.001). Rounding a 162.345 JPY price to 162.35 is not cosmetic — it quantizes every recorded entry/SL/TP to the pip and destroys the third decimal that *is* the trade's working resolution. Any downstream analysis of the recorded CSV (warehouse, ledger) inherits the quantization.

**Why it happens:**
The 2-dp convention was chosen for gold's quoting and is sprinkled at the *output boundary* (CLI/decision log), not centralized in a symbol-aware formatter. The internal backtest math is full-precision and fine; the artifacts are what corrupt.

**How to avoid:**
Centralize rounding behind the instrument spec's `digits` (round to `digits`, not a hard 2) and apply it at the CLI/CSV boundary only. The engine and stats must keep full precision. Do **not** touch `live/engine.py::_round2` or `PendingOrder.equivalent_to` in this backtest-only milestone (see D4) — add the digit-aware path at the backtest CLI/log boundary and leave live semantics byte-identical.

**Warning signs:**
- A JPY trades.csv where all prices end in two decimals and the third decimal of the raw data is gone.
- A JPY decision log where entry − SL differences are all whole pips (0.01 multiples) even though the data had 0.001 resolution.

**Phase to address:** Phase 1 (digit-aware output boundary). Live `_round2`/`equivalent_to` fix deferred to a future live-wiring milestone (D4).

---

### B. Statistical pitfalls (this exact situation)

### Pitfall B1: Treating the v1.0 ranking winners as a pre-registered hypothesis, then "confirming" on the same sample

**What goes wrong:**
EURJPY (+0.135R) and GBPJPY (+0.121R) were selected because they were positive in **both halves** of the v1.0 split-sample test *of the same 17-instrument scan*. They are ranking winners on the sample that measured them. If v1.1 re-runs the breakout on EURJPY/GBPJPY over 2025–2026-07 broker data — the same calendar window v1.0's histdata covered — and reports the result as confirmation, that is data snooping: the same ~100–200 trades viewed through a corrected spread model is a **re-measurement**, not an out-of-sample test. Every later candidate (short, ORB, vol, HTF) failed its OOS controls; this one must be held to the same standard or it is the first candidate ever exempted.

**Why it happens:**
The instruments genuinely were the only two positive in both halves, so they *feel* a-priori. But the v1.0 magnitudes are also contaminated (see C3: the JPY spread was later shown wrong), so both the selection *and* the effect size came from instrument-incorrect numbers.

**How to avoid:**
- Register the hypothesis and its decision rule *before* running: "long M5 breakout at the default params has mean R > noise bar on EURJPY and GBPJPY" — no further parameter/session selection inside the confirmatory run.
- Treat v1.0 as hypothesis generation and demand genuinely fresh evidence: a chronological walk-forward (fit on early data → test on later, never the reverse), a held-out tail of broker data that v1.0 never saw (2026-08 onward plus any pre-2025 history the terminal serves), and random-entry controls.
- If the only available data overlaps v1.0's window, say so in the verdict and discount the result by the v1.0 look (raise the significance bar, see B2).

**Warning signs:**
- The plan or report uses the word "confirms" about an instrument that was already the ranking winner on the same window.
- No pre-registered decision rule exists and the run is exploratory (params/sessions/symbols being scanned).
- The OOS "test" window begins before the v1.0 data ended.

**Phase to address:** Phase 3 (pre-registration + genuinely out-of-sample test design). Phase 2 must acquire data that actually extends the v1.0 span.

---

### Pitfall B2: Multiple-comparison mining across the new experiment — and treating EURJPY/GBPJPY as two independent tests when they are ~one

**What goes wrong:**
This project's own calibration is the reference: across ~39 configurations the best |t| = 2.46, and pure noise beats that 42% of the time. A v1.1 run that sweeps session windows, lookbacks, buffers, or rr ratios on two instruments and reports the best cell *without recalibrating over the total number of tries* repeats exactly the failure the calibration was built to catch. Worse, EURJPY and GBPJPY are both JPY crosses — highly correlated (same quote currency, overlapping drivers) — so "positive on both instruments" is close to one observation, not two. The v1.0 "both-halves-positive" criterion already suffered this: with correlated instruments, the effective number of independent tests is far below the nominal count.

**Why it happens:**
Every exploratory backtest reports its best cell because that is the interesting one; counting all tries is unnatural. And two instruments *feel* like two tests because they are two files.

**How to avoid:**
- Count the tries: every symbol × parameter combination × session window × split boundary *actually evaluated* (including the v1.0 look on the same window) goes into the max-|t| noise calibration, using the project's existing calibration method. Report the calibration alongside the headline |t|, exactly as the 2026-08-20 note does.
- Explicitly model the correlation: if the hypothesis is "the JPY-cross breakout has an edge", test EURJPY and GBPJPY as a correlated pair (e.g., require both, or require the pooled/cross-sectional mean to clear a threshold computed under the correlation), not each at p<0.05.
- Pre-commit the primary test(s) in Phase 3 before running; anything not pre-committed is a "discovery" that needs its own fresh confirmation.

**Warning signs:**
- A report whose headline config was chosen by inspecting the output (best-of-N reported with N hidden).
- "Both instruments significant" claimed when each is t≈2 — under the correlation that is closer to one t≈2 test.
- No noise-calibration line in the verdict table.

**Phase to address:** Phase 3.

---

### Pitfall B3: Split-sample instability and the XAUUSD flip — one split is not a verdict

**What goes wrong:**
v1.0's split-sample test produced between-halves correlation +0.27 (needs ~0.53 for significance at n=14) and 6 of 14 instruments flipped sign — and **XAUUSD itself went +0.092 → −0.005** between halves. The very instrument the live plan trades showed no edge in the recent half of its own data, and gold's "positive OOS walk-forward" configs were all front-loaded 2025-only (2026 test t=+0.92). Any v1.1 design whose headline is a single train/test split, or whose EURJPY "both halves positive" is re-derived from a split chosen after seeing the data, inherits this instability.

**Why it happens:**
A 50/50 split of a ~500-day M5 sample yields ~100-trade halves; mean-R differences of ±0.09 are the same size as the edges being measured (SE ≈ 0.9/√100 ≈ 0.09). Halves flip on noise, and the boundary choice itself is a free parameter that can be tuned to flatter a result.

**How to avoid:**
- Use chronological walk-forward with multiple folds (train must always precede test) and pre-fixed fold boundaries; report every fold, not the best.
- Report per-month (and per-year) R with the noise band, since front-loading is this sample's dominant failure mode (2025 uniformly positive, 2026 noise on gold).
- Any config that "works" must be positive in the *later* folds, not rescued by the earlier ones.

**Warning signs:**
- A single 70/30 or 50/50 split used as the OOS evidence.
- The test half's start date was adjusted after an initial run.
- Monthly table shows all the R in the first months and noise after.

**Phase to address:** Phase 3.

---

### Pitfall B4: Low power at n≈100–200 — "not significant" ≠ "falsified", and t≈1.95 ≠ "edge"

**What goes wrong:**
EURJPY was t≈1.95 at ~100 trades; at ~200 trades with R std ≈ 0.9 and mean R ≈ 0.13 the study has roughly **~190 trades to reach t≈2 but ~375 for 80% power**. A v1.1 run that lands at n≈100–200 and reports "not significant → falsified" would be wrong (it was simply underpowered); a run that reports t≈1.95–2.1 as "edge confirmed" would repeat v1.0's error (inside the noise bar). The milestone brief already names the required distinction — "fails because noise/front-loaded" vs "real but too small" — and every prior candidate failed *below* its controls, so the discipline exists; the pitfall is letting the two-tailed ~5% threshold do the deciding when the design cannot deliver the power to separate the hypotheses.

**Why it happens:**
Sample size is set by data availability (a terminal serves ~100k M5 bars ≈ ~470 trading days for a 24/5 FX symbol), not by a power calculation. The temptation is to read the p-value as the whole verdict.

**How to avoid:**
- Compute the power/required-n for the effect size of interest (≈0.10–0.15R) *before* fetching, and state it in the plan.
- Pre-commit a three-way decision rule: (1) clears the noise-calibrated bar and survives OOS/controls → positive; (2) clear null with adequate power → falsified; (3) null at n below the power target → "underpowered, inconclusive", a real and publishable outcome that decides *nothing* about live.
- Report effect-size confidence intervals, not just p — the project already knows the SE on mean R (~0.09) is the same size as the edge.

**Warning signs:**
- The verdict table has no n, no SE, no power statement.
- "Falsified" is written next to a t between −1.5 and +1.5 at n < 150.
- The plan promises a yes/no answer the data cannot support.

**Phase to address:** Phase 3 (decision rules). Phase 2 should maximize honest sample (longest broker-native history + any pre-2025 supplement) but must not mix sources (C1).

---

### Pitfall B5: Long-only drift contamination and front-loaded edges on trending JPY crosses

**What goes wrong:**
Gold's long-only R carried a +54% drift premium, and the "edge" died at the 2025→2026 boundary. JPY crosses in 2024–2026 span major JPY regimes (the carry-trade unwind, BoJ policy shifts, GBPJPY's structural volatility and long trends). A long-only M5 breakout on a strongly trending GBPJPY sample books positive R that is **drift, not edge** — v1.0 already warned about this exact trap on BTC (made money in points while R was negative, and buy-and-hold beat the bot 4×). The random-entry/random-bias controls and the short-side mirror are the only things that separate drift from alpha, and the short-side study showed gold's whole "edge" was drift.

**Why it happens:**
Breakouts are long-only; a rising market pays any long trigger. No mechanism in the strategy detrends, so the backtest can't tell drift from setup alpha by itself.

**How to avoid:**
- Run the drift-neutral estimate (long R − short R, or demeaned by the instrument's own trend) and the random-entry control (setup_override coin flips through the same engine) as a mandatory part of the battery — the ORB study's random-time control beat the real London window, and the vol study's ablation beat the hypothesis; this engine already knows how to falsify.
- Report per-year and per-month R so a 2025-only front-loaded result is visible, not buried in a full-sample mean.
- Do not add a session filter that happens to carve out the trending hours; any session claim needs its own random-window control.

**Warning signs:**
- Full-sample R positive but the recent-half/monthly table is flat or negative.
- No random-entry or mirror-side row in the report.
- The instrument's buy-and-hold return over the window is comparable to or better than the strategy's — the edge claim must beat *that*, not zero.

**Phase to address:** Phase 3.

---

### Pitfall B6: t-statistics over overlapping trades overstate significance

**What goes wrong:**
Gold holds were long (median 6.7h, p90 28h, max 10 days) — one trade spans many M5 bars and often entire sessions. The t-stat is computed over closed trades as if independent; a 1:1 breakout book whose trades overlap in time has serially correlated R, so effective n is below the trade count and naive t is inflated. On the *two correlated JPY crosses traded simultaneously* the inflation is worse.

**Why it happens:**
The engine is single-slot per symbol, but time-overlap across *different* trades (and across EURJPY+GBPJPY positions in the same hours) means the returns are not an i.i.d. sample. The existing stats compute n as closed trades.

**How to avoid:**
- Report R per day (or per session) as a secondary t-statistic — the 2026-08-20 session study already used R/day; keep that as the cross-check.
- When pooling EURJPY + GBPJPY, block by time (same calendar day) rather than doubling n.
- Report the max |t| calibration (B2), which is computed under the null and therefore already absorbs much of the dependence — but only if the calibration ran *on the same data structure* (same symbol/session grid).

**Warning signs:**
- t rises materially when trades are aggregated to R/day.
- A claim that "two instruments × 150 trades = 300 independent observations".

**Phase to address:** Phase 3 (stats layer of the battery).

---

### C. Data pitfalls

### Pitfall C1: Broker-native vs vendor data disagree — mixing sources across halves fabricates or destroys edges

**What goes wrong:**
The same strategy on gold measured PF 1.29 / avg R 0.135 on histdata XAUUSD (339 trades) vs PF 1.22 / avg R 0.091 on broker XAUUSDm (437 trades), with different max drawdown and stop widths. The v1.0 JPY ranking ran on histdata through 2026-07; the live account trades Exness's own instrument (EURJPYc/GBPJPYc, cent conventions, broker feed). A v1.1 that trains on histdata EURJPY and "tests" on broker EURJPYc — or backtests broker data but compares the number to v1.0's histdata number — is comparing two different tradable instruments through two different lenses.

**Why it happens:**
histdata EURJPY is a generic aggregated feed; the broker's EURJPYc is Exness's own pricing on the account type the bot would actually trade. The repo already learned broker vs vendor is a first-order difference on gold; there is no reason JPY crosses are exempt.

**How to avoid:**
- Decide the verdict instrument is the broker's own (EURJPYc/GBPJPYc M5 via `fetch_broker_history.py`) and run the entire battery — walk-forward, controls, monthly — on that single source.
- Never mix sources inside one metric (train histdata → test broker is invalid).
- Record a dataset card per CSV: source, symbol, span, bar count, bar-clock basis, spread source/value, point/digits/contract/value-per-point as read from the terminal at fetch time. Recompute v1.0 comparisons only as *reproductions on the same data*, labelled as such.

**Warning signs:**
- A report table whose rows span more than one data source without a source column.
- Verdict numbers quoted against v1.0 histdata magnitudes (B1).
- Two backtests of "the same" instrument differing by more than noise for no documented reason.

**Phase to address:** Phase 2 (fetch + dataset card). Phase 3 consumes only the carded datasets.

---

### Pitfall C2: Bar-clock / server-time assumptions break session and weekend logic

**What goes wrong:**
Session filters and the weekend guard are hour-of-day logic on the bar index (`df.index.hour`; `in_session`/`in_weekend` in live). Gold's findings assumed the broker feed is UTC (measured on the gold terminal). On a JPY-cross backtest: (1) the histdata file clock may not be the broker's server clock — a fixed offset silently shifts every session boundary by hours; (2) Exness server time is not guaranteed UTC on every account/terminal, and MT5 server time is broker-configurable (commonly UTC+2/+3 with DST); (3) FX has a **daily rollover/maintenance break** and a weekend shut (roughly Fri 21:00 → Sun 22:00 UTC, broker-dependent) that differs from gold's Fri 21:00 → Sun 21:00, and *gold's* Friday-19:00/Sunday-21:00 guard settings are gold-specific.

**Why it happens:**
The gold pipeline established "server clock = UTC" once, on one terminal, and the whole session/ORB literature in STATE.md was built on it. Copying the same hours or the same weekend parameters to JPY crosses transfers an unverified clock assumption and a market-schedule assumption at once. A session hypothesis about "Tokyo" is meaningless if the clock is off by 2–3 hours.

**How to avoid:**
- Verify the bar clock *per source* against an anchor (e.g., compare the last Friday bar / first Sunday bar timestamp to the known FX weekend close for that broker; compare a known news event's timestamp). Do this in Phase 2 and record it in the dataset card.
- Treat weekend and session parameters as per-instrument spec fields, not globals. Do not reuse gold's `weekend_stop_hour=19 / resume_hour=21` — JPY crosses trade nearly 24/5 and their closure is broker-scheduled; the v1.1 backtest must decide explicitly whether entries near the FX Friday close are included (the gold weekend-gap rationale — a broker-side stop can't protect a Sunday gap — applies *with more force* to JPY crosses, whose Friday close gaps into Sunday's open are real).
- If a Tokyo-session hypothesis is tested, it needs its own random-window control (the ORB lesson).

**Warning signs:**
- Backtest output shows setup bars at timestamps the FX market is closed (Saturday, or daily maintenance) — data was stitched across a gap without excluding it, or the clock is shifted.
- The "weekend" in the logs starts Friday 19:00 on an FX chart (that's gold's schedule).
- Two data sources' identical calendar dates map to different session hours.

**Phase to address:** Phase 2 (clock verification + per-instrument schedule). Phase 3 session sub-hypotheses run through the controls.

---

### Pitfall C3: Spread modeling — the v1.0 JPY magnitudes are contaminated and the flat-subtraction model is optimistic

**What goes wrong:**
STATE.md (2026-08-21) explicitly invalidates the earlier EURJPY row from the TP-from-fill run: it applied gold's $0.26 spread to a JPY cross whose median stop is ~0.381 price (≈38 pips), making the cost **~68% of risk** instead of ~2–4%. That same class of error — gold-convention costs applied to JPY instruments — is baked into parts of the v1.0 cross-instrument scan, so **v1.0's +0.135R/+0.121R are not trustworthy magnitudes**; they are hypothesis-generating signals at best. Separately, the repo's own first-order spread estimate for gold was flat per-round-trip subtraction, which it documented as optimistic because it does not model SL/TP triggering on the bid. For JPY crosses, spread is session-dependent (wider in the Tokyo afternoon / Sydney hours on Western-broker feeds, tighter in London/NY overlap), and a ~1-pip spread on a ~38-pip stop (~2.6% of risk) is a *larger* per-trade cost than gold's ~1.1%, so modeling quality matters more, not less.

**Why it happens:**
Spread was a single config value (`spread_assumption`, now dead config — declared but read by nothing) and a flat constant in research scripts. JPY-cross spread in *pips* (0.01 units) was never converted into the instrument's price units correctly, and no per-session spread model exists.

**How to avoid:**
- Model spread in the instrument's own units: `spread_price = spread_pips × 0.01` (pip step for JPY crosses) or read the symbol's live spread during the Phase 2 fetch window and record a per-session median spread into the dataset card.
- Keep the documented limitation explicit: flat per-round-trip subtraction is a floor on cost; state it in the verdict. A spread sensitivity table (halve/double the spread) is cheap and tells you whether the verdict survives spread uncertainty.
- Never let a gold-derived spread reach a JPY backtest; make spread a required spec field with a unit assertion (a $0.26 JPY spread is a unit error, not a value).
- Because spread is session-varying, do not let a session filter quietly select the low-spread hours and claim the improvement as alpha (that is a cost artifact; run the random-window control).

**Warning signs:**
- Any report where a JPY-cross cost is quoted in dollars/points that came from gold.
- Net-R changes by >0.02R when the spread assumption is halved (verdict is spread-dominated, not edge-dominated).
- Spread cost per trade > ~5% of the median stop on the report's own numbers.

**Phase to address:** Phase 2 (spread capture). Phase 1 (unit-asserted spread spec). Phase 3 (spread sensitivity as part of the battery).

---

### Pitfall C4: Data acquisition — histdata naming, stale files, and symbol-label contamination

**What goes wrong:**
Three separate traps:
1. **Naming/glob**: the CLI globs `DAT_ASCII_{symbol}_M1_*.csv` (deliberate anti-contamination fix from plan 01-05). Freshly downloaded histdata files are currently named `HISTDATA_COM_ASCII_{SYM}_M1_{YYYY}.csv` (verified on histdata.com 2026-09-07). New EURJPY/GBPJPY downloads therefore match *nothing*, and the CLI errors "no CSV files found" — or worse, if the data dir also holds gold CSVs and the config's symbol is wrong, it loads the wrong instrument.
2. **Symbol-label contamination**: `config/config-eurjpy.toml` still has `[data] symbol = "XAUUSD"` (documented as "UNVERIFIED — still gold"). Running `backtest --config config-eurjpy.toml` against `data/raw` today loads *gold* M1 files and reports them as EURJPY. The CLI glob keys on the config symbol, so a wrong `[data] symbol` + a data dir containing that symbol's files = silent mislabelling.
3. **Staleness**: histdata ends ~2026-07 unless manually refreshed; the v1.1 verdict needs history v1.0 never saw (B1). The broker terminal (`fetch_broker_history.py`, ~100k M5 bars ≈ ~470 trading days on a 24/5 symbol) is the current-to-today source.

**Why it happens:**
The gold data dir is gitignored and was populated under the old naming; the eurjpy config was written as a placeholder and never exercised; nothing asserts that the loaded frame's prices look like the configured symbol.

**How to avoid:**
- Phase 2's fetch path is the primary source (broker-native, correct instrument, current), so prefer `--m5-csv` which bypasses the histdata glob entirely.
- If histdata is used for pre-2025 depth: download fresh files, rename or update the glob to the actual `HISTDATA_COM_ASCII_*` convention, and *assert the loaded frame's symbol identity* — the config's `[data] symbol` must match the glob pattern, and the data directory must not contain other symbols' files.
- Add a symbol-consistency guard in Phase 1: a backtest run labels its output with the symbol that was actually loaded (from the CSV filename / config), and refuses to run when the config symbol doesn't match the file being loaded (config-eurjpy.toml's gold `[data] symbol` must fail loudly, not load gold).
- Re-check `data_gap_detected` warnings (the >3-day M1 gap heuristic) against FX's daily-break + ~46h weekend so real missing files are still caught.

**Warning signs:**
- `backtest` says "no CSV files found" right after a fresh histdata download (naming mismatch).
- A EURJPY backtest whose prices are in the thousands with $ figures (that's gold).
- EURJPY "trades" that match gold's exact bar timestamps (same feed).
- The dataset card is missing the symbol field.

**Phase to address:** Phase 1 (symbol-consistency assertion). Phase 2 (fetch + file naming + freshness).

---

### Pitfall C5: Sample span expectations — 24/5 FX has fewer bars/year than assumed, and the "both crosses" pool is ~1 instrument of evidence

**What goes wrong:**
FX trades near 24/5 but with a daily maintenance break and a weekend shut, so a JPY cross yields ~250–270 M5 bars/day × ~250 days ≈ ~65k bars/year — the terminal's ~100k bars ≈ **~1.5 years**, shorter than gold's 514-day haul for the same page count. With ~1 trade/day that is ~150–300 trades per symbol: squarely in the low-power zone of B4. And pooling EURJPY + GBPJPY does not double the evidence (B2). A plan that promises a definitive verdict without stating n, SE, and power has set itself up to fail honestly.

**Why it happens:**
The gold experience (100k bars / 514 days, 437 trades) is the mental model; a 24/5 clock with daily breaks delivers fewer bars per calendar year than a 23/5 metals session running ~500 days because of the shorter history depth, and the two JPY crosses are near-duplicates of each other's evidence.

**How to avoid:**
- State expected n and the power analysis in the Phase 3 plan *before* running (B4).
- If more history is needed, the only honest sources are (a) deeper broker-terminal history where available and (b) histdata pre-2025 as a *separately-carded, separately-analysed* supplement — never pooled silently with broker data (C1).
- Make the primary hypothesis one *pooled* JPY-cross question with a correlation-aware threshold (B2), so the n is the pooled trade count with effective-n discounting, and the decision rule is calibrated for it.

**Warning signs:**
- The plan promises a verdict with no n/power estimate.
- "More trades" is being bought by pooling EURJPY+GBPJPY as if independent, or by scanning sessions/params (that's B2 mining, not sample).

**Phase to address:** Phase 3 (protocol). Phase 2 (span maximization with source discipline).

---

### D. Integration pitfalls (this existing system)

### Pitfall D1: Touching the pure strategy chain to "support" JPY crosses

**What goes wrong:**
`strategy/swings.py → levels.py → signals.py → backtest/engine.py` is the shared pure chain (SAFE-01), deliberately symbol-agnostic: it operates on OHLC price columns and has no concept of symbol, digits, or currency. It needs **no changes** to detect breakouts on JPY data. The failure mode is "helpful" edits — special-casing JPY, adding a point parameter into `detect_setups`, tweaking level rounding for 3-dp prices, or adjusting `support_resistance` semantics — that silently alter gold behavior and break the 442-test suite, the golden frames (entry 101.00 / sl 100.09 / tp 101.91 exact 1:1, pinned across test_backtest, test_cli, test_live_engine, test_ai_*), and the live gold and BTC bots that run the same code from the same repo on the Windows machine.

**Why it happens:**
The instrument-agnosticism is invisible — the chain *looks* like it needs symbol awareness because the *surrounding* code (buffer, money, rounding) is gold-specific. The boundary is the mistake: all symbol knowledge belongs in the config/spec + CLI/stats layers, never in the chain.

**How to avoid:**
- Hard rule for the milestone: **zero edits inside `src/trading_bot/strategy/**` and `src/trading_bot/backtest/engine.py`'s detection/fill loop unless a JPY golden-frame test fails first** (it won't).
- All instrument knowledge enters as new *parameters with legacy defaults* at the `run_backtest`/stats/CLI boundary.
- Run the full suite after any change; the golden integration tests are the tripwire. Byte-identical gold output is a merge criterion, not a hope.
- Follow the v1.0 pattern: instrument-correct machinery as a new module (like the `stratvar`/ORB modules), never as edits to the shared chain.

**Warning signs:**
- A diff touching `strategy/*.py` or the backtest event loop in a JPY milestone.
- Golden-frame tests (`test_backtest.py::test_golden_integration_full_records`, the 1:1 exactness pins) modified rather than passing unchanged.
- Config `sl_buffer`/`rr_multiple` defaults changed "to make the numbers work".

**Phase to address:** Phase 1 (with full-suite + golden verification as its exit gate). It is also the **top risk section** for every plan in the milestone.

---

### Pitfall D2: Breaking byte-identical defaults while adding point/digits awareness

**What goes wrong:**
`run_backtest(sl_buffer=0.01, rr_multiple=1.0, ...)` and the config defaults are pinned by tests and by the live gold/BTC configs' semantics. If Phase 1 converts `sl_buffer` to a points-based quantity *in place* (e.g., starts interpreting the existing 0.01 as "1 point" or "1 pip"), every gold backtest number, config, and golden pin silently changes meaning. The config-eurjpy.toml comment already notes gold's 0.01 happens to equal 10 points on both gold and JPY 3-dp quotes — that coincidence is precisely why an in-place semantic change is seductive and dangerous (it is *not* true on BTC's 2-dp quote, where 0.01 is 1 point, nor on EURUSD).

**Why it happens:**
The value 0.01 is numerically identical to "10 × point" for 3-dp symbols, so a maintainer can believe the units were always points. They weren't — on 2-dp BTC the committed backtest config already overrode it to 0.10 (10 points), which is the evidence that buffer is symbol-dependent and must be spec-driven, not guessed.

**How to avoid:**
- Introduce `sl_buffer_points` (or a spec-driven buffer) as a *new, optional* field; when absent, behavior is exactly today's price-based `sl_buffer`. Only spec-carrying JPY configs set the points form.
- Assert in tests that gold and BTC configs' backtest output is numerically unchanged.
- Where the two coexist, validate they are never both set inconsistently (a config setting `sl_buffer_points=10` and `sl_buffer=0.05` must fail validation).

**Warning signs:**
- A change to `run_backtest`'s default parameters or to `StrategyConfig` defaults.
- Test fixtures' expected trade records edited to match new engine output (rather than new output matching old fixtures).
- Gold backtest net R changing between "before" and "after" the milestone for identical configs.

**Phase to address:** Phase 1.

---

### Pitfall D3: Overloading `[trading] contract_size` and drifting the backtest config away from the live one

**What goes wrong:**
`cfg.trading.contract_size` is read by backtest stats (money conversion) but **no longer by the live engine** (which uses `SymbolRisk` tick_value). A JPY backtest config that sets `contract_size = 100000` (or 1000 cent) to make money stats "right" inherits the A2 problem; a config that leaves it at 100 quietly produces the A2 nonsense. Meanwhile, editing the *existing* gold/BTC configs (config-cent.toml, config-btc.toml) to experiment would touch the live bots' behavior on the running Windows box. The repo convention is already right: a separate `config-btc-backtest.toml` exists for exactly this reason.

**Why it happens:**
The config is shared between backtest and live for the same symbol, and the field name (`contract_size`) invites the belief that setting it correctly "fixes FX" — when the correct fix is to stop using contract size for money at all (A2) and read value-per-point from the broker.

**How to avoid:**
- Create dedicated backtest configs per JPY instrument (pattern: `config-btc-backtest.toml`), never edit `config-cent.toml`/`config-btc.toml`/live settings in this milestone.
- Deprecate contract-size-derived money in Phase 1 stats in favor of spec value-per-point; treat `contract_size` as backtest-legacy only and say so in the stats output.
- Guard: the backtest CLI must not load a config whose `[live] enabled = true` (belt-and-braces scope guard — see D5).

**Warning signs:**
- A JPY milestone touching `config/config-cent.toml` or `config/config-btc.toml`.
- `contract_size` justified by "we set it to the FX value" in a PR/commit message.
- Live gold/BTC output dirs or logs changing during a backtest-only milestone.

**Phase to address:** Phase 1 (configs + stats). Phase 2 (spec capture makes the field unnecessary).

---

### Pitfall D4: Dragging live-layer 2-dp debt (_round2 / PendingOrder.equivalent_to) into a backtest-only milestone

**What goes wrong:**
`live/engine.py::_round2` (2-dp decision-log rounding) and `broker/base.py::PendingOrder.equivalent_to` (0.01 entry tolerance) are known gold-era 2-dp assumptions, already flagged as debt in STATE.md (XAUUSDm is 3-dp, so even live gold exercises them imperfectly today). On a 3-dp JPY instrument, `equivalent_to`'s 0.01 tolerance is 10× the price granularity, and `_round2` destroys the third decimal. The trap is "fixing" these *while the milestone is open* because they are adjacent to the new per-symbol work: both live gold (magic 77020) and BTC (77021) run from this repo on the Windows machine, and `ai/engine.py` imports `_round2` from `live/engine.py`, so an in-place change ripples into AI-backtest logging and live dedup semantics that this milestone cannot verify (no live layer in scope).

**Why it happens:**
They are the two most visible "2-dp" code smells and the milestone's whole point is 3-dp instruments, so they look in-scope. But they are *live-execution* semantics; a backtest-only milestone has no live terminal verification budget (the 02-06 lesson: live changes need real-terminal verification).

**How to avoid:**
- Keep `_round2` and `equivalent_to` **out of scope** for v1.1; record them as a dependency for the future live-wiring milestone (when EURJPY/GBPJPY would actually trade, `equivalent_to` needs a per-symbol tolerance in points, and rounding needs a per-symbol digits parameter — with gold/BTC byte-identical tests as the gate).
- For the backtest artifacts, solve the *output* side with the digit-aware boundary from A3 (which touches CLI/CSV only, not live modules).
- If a shared helper is truly needed, add a new symbol-aware formatter module and leave the live module untouched.

**Warning signs:**
- A diff touching `live/engine.py`, `broker/base.py::equivalent_to`, or `ai/engine.py` in a backtest milestone.
- The suite's live-engine tests (test_live_engine, test_cli_live) modified rather than passing unchanged.
- "While we're here" appearing in a plan's scope.

**Phase to address:** Deferred (documented dependency for the live-wiring milestone). Backtest artifact rounding → Phase 1.

---

### Pitfall D5: Backtest-only scope creep — accidental live enablement or touching running gold/BTC

**What goes wrong:**
The milestone is backtest-only, but the repo holds real-money configs (gold cent magic 77020, BTC magic 77021), `config-eurjpy.toml` already exists with `[live] enabled=false, mode="dry-run"` and an unverified `symbol = "EURJPYc"`, and the machine runs the live bots. Failure modes: (1) a data-fetch step uses the live terminal and a config whose `[live] mode` was flipped to demo/live for convenience, which can place or risk orders if the engine is ever pointed at it; (2) an experiment writes to the live config or restarts the live agents (the tune_risk suite already had one incident where a test restarted the real cent agent); (3) new JPY "symbols" collide with existing magic numbers.

**Why it happens:**
One repo, one terminal, many configs; backtest and live share the same code path by design (SAFE-01), so the separation is a *config* separation, and configs are easy to edit casually.

**How to avoid:**
- The backtest CLI refuses to run with `[live] enabled = true` (a hard guard in the config validator or CLI, cheap and permanent).
- v1.1 uses its own backtest configs (D3) with `enabled=false`, `mode="dry-run"`, and new comment/magic placeholders; no `EURJPYc` live symbol is *used* anywhere until the live milestone.
- Data fetch for Phase 2 uses `fetch_broker_history.py` with a read-only backtest config (it never places orders — verified pattern), and only against the terminal the config pins (`terminal_path`).
- Never restart or boot-out the gold/BTC launchd agents as part of this milestone.

**Warning signs:**
- A plan step that changes `[live]` in any committed config.
- Any test or script writing to `config/config-cent.toml` or `config/config-btc.toml`.
- A JPY script that imports or exercises the order-placement path.

**Phase to address:** Phase 1 (guard) and every plan's risk section (scope discipline).

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Keep `sl_buffer` as a raw price and "just set it per symbol in the config" | No spec layer needed today | Every new symbol re-derives buffer from a coincidence; the EURUSD 100-pip class returns | Never — buffer-in-points is ~one field and removes the class |
| Set FX `contract_size` "correctly" in the JPY backtest config | Money stats look right today | Enshrines the wrong mental model (A2); stats die when account currency ≠ quote currency | Never — use spec value-per-point or label money stats meaningless |
| Reuse gold's session/weekend hours for FX | Zero new config | Clock/schedule assumptions silently baked into every JPY result (C2) | Never — per-instrument schedule, clock-verified |
| Flat gold spread constant subtracted from JPY trades | One-line cost model | v1.0-style 68%-of-risk contamination (C3); verdict spread-dominated | Only in a *labelled* sensitivity pass, never the headline model |
| "Fix" `_round2`/`equivalent_to` in place while here | Removes visible 2-dp debt | Live gold/BTC dedup + AI logging semantics change unverifiably (D4) | Never in a backtest-only milestone; defer with tests |
| Report the best of N configs with N hidden | Strong-looking headline | Repeats the 42%-noise-beats-best calibration failure (B2) | Never — always report the calibration over all tries |
| Call an underpowered null "falsified" | Clean narrative | Wrong conclusion decides live future (B4) | Never — the three-way verdict rule exists for this |
| Pool EURJPY+GBPJPY as independent evidence | Doubles apparent n | ~1 effective test claimed as 2 (B2/B5) | Only with correlation-aware pooling and effective-n discounting |

## Integration Gotchas

Common mistakes when connecting the JPY work to this existing system.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Shared pure strategy chain (swings→levels→signals→engine) | Adding symbol/JPY special-casing inside the chain | Zero edits; symbol knowledge lives in spec + CLI/stats boundary (D1) |
| Golden 12-bar frame + 442-test suite | Re-baselining golden expected prices to match new engine output | New output must match old pins; defaults stay byte-identical (D2) |
| `run_backtest` signature / config defaults | Changing `sl_buffer` default or semantics | Add `sl_buffer_points` optional; legacy path untouched (D2) |
| Backtest CLI histdata glob (`DAT_ASCII_*`) | Fresh histdata JPY files (now `HISTDATA_COM_ASCII_*`) match nothing; or wrong-symbol CSVs load | Prefer `--m5-csv` broker data; update glob to actual naming; assert symbol identity (C4) |
| `trade_stats` money conversion | FX contract size 100000/1000 fed into the gold `contract_size × lot` path | Value-per-point from broker spec; money stats guarded/labelled (A2) |
| Session/weekend filter logic | Gold `[8,21]` hours / Fri-19/Sun-21 weekend carried to JPY crosses | Per-instrument schedule on a clock-verified bar index (C2) |
| `_round2` / `PendingOrder.equivalent_to` (live) | In-place digit/tolerance fixes during a backtest milestone | Out of scope; digit-aware rounding only at backtest output boundary (A3/D4) |
| Live gold/BTC configs + agents on the same repo/machine | Editing live configs or restarting agents to "test" JPY | Dedicated backtest configs; backtest CLI refuses `[live] enabled` (D3/D5) |
| config-eurjpy.toml (`[data] symbol = "XAUUSD"`) | Running backtest with it loads gold and labels it EURJPY | Symbol-consistency assertion fails loudly (C4) |

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Loading many monthly M1 histdata files for JPY crosses then resampling | Slow CLI start, high RAM on `_load_all` (M1 frames are ~5× the M5 frame) | Prefer broker `--m5-csv` (already M5); cap histdata supplement to the needed span | Multiple 2024–2026 M1 monthlies (~300k+ M1 bars) on a laptop |
| Paging broker history for two symbols with `--pages` defaults | Partial spans, or huge CSVs written per page without dedupe | Reuse `fetch_broker_history.fetch` (drop_duplicates/sort/astype) per symbol; card the span | >8 pages (terminal serves ~50k/call; ~100k bars ≈ 1.5 FX years) |
| Full-sample R/t computed per trade over overlapping, multi-hour holds | t inflation (B6); slow per-trade loops in sweep scripts | Per-day aggregation as the cross-check metric; vectorized stats over the engine's trade list | n > ~50k trades in parameter sweeps |
| Per-config sweeps (params × sessions × 2 instruments) without counting tries | Exploding best-of-N with no calibration (B2) | Pre-register the grid; run calibration over the actual grid size; stop adding cells post-hoc | Any grid beyond ~40 cells (the calibration already shows 42% noise beats at 39) |
| Reading `spread_assumption` from config (dead knob) | False impression spread is modeled | Remove or repurpose it into the spec-driven spread field (C3) | The moment a JPY verdict leans on it |

## Security Mistakes

Domain-specific issues beyond general web security (scope/safety for a backtest milestone sitting beside live money).

| Mistake | Risk | Prevention |
|---------|------|------------|
| Flipping `[live] enabled/mode` on config-eurjpy.toml to "try it" | A demo/live order placed from an unverified instrument config on a real terminal | Backtest CLI refuses `[live] enabled=true`; SAFE-03 stays the gate; eurjpy config stays dry-run (D5) |
| Fetching data with a live-mode config on the shared terminal | Engine/script confusion between the gold and JPY terminals (`terminal_path` pinning is load-bearing) | Phase 2 fetch uses dedicated backtest configs with explicit `terminal_path`; one watcher/terminal discipline (D3/D5) |
| Restarting/booting gold or BTC launchd agents during experiments | Real-money bots stop or double-start (two-bots-one-magic bug class) | Never touch the agents this milestone; tests that could restart agents must stub them (the tune_risk precedent) |
| Running the v1.1 battery on a config pointing at a live account's terminal in demo | Verdict statistics computed while a live position interferes with symbol history | Keep data fetch and live bots on separate terminals/configs; the repo already isolates per-terminal |
| Credential exposure via new scripts | The repo's history includes an infostealer; any new fetch/auth code must not log credentials | No new auth paths in v1.1; broker access is via the already-connected terminal only |

## UX Pitfalls

How the milestone's output can mislead its human reader (the trader/analyst).

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Verdict table quoted in "points" or "USD" across instruments | Reader compares incomparable numbers (A2) | Lead with avg R / R-day / t; money only from spec value-per-point, labelled |
| "Positive on both JPY crosses in both halves" presented as the headline | Overstates evidence that is ~1 correlated test (B2) | Report the pooled test with correlation-aware threshold + calibration line |
| Report with no n/SE/power statement | "Significant"/"falsified" read as definitive at n≈150 (B4) | Verdict template includes n, SE of mean R, power note, and the three-way decision rule |
| Headline full-sample R with no monthly/yearly table | Hides front-loading and drift (B3/B5) | Monthly R table with noise band is a required report section |
| A single 70/30 split labeled "out-of-sample" | Overstates OOS evidence on a noisy 100-trade test half (B3) | Chronological walk-forward, all folds reported |
| v1.0's +0.135R quoted as the target to beat | Anchors on a contaminated magnitude (C3/B1) | Treat v1.0 as hypothesis generation; the target is the noise-calibrated bar, not a v1.0 number |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Instrument spec:** The backtest runs on JPY data but no per-symbol spec (point/digits/value-per-point/spread/session/weekend) exists or is asserted — verify every number a config hardcodes was read from the terminal, not guessed (config-eurjpy.toml's checklist is the model).
- [ ] **Symbol identity:** The EURJPY backtest actually loaded EURJPY bars — verify `config-eurjpy.toml`'s `[data] symbol` was updated from XAUUSD and that the loaded CSV filename matches; a symbol-consistency assertion should enforce it, not a human.
- [ ] **Buffer units:** `sl_buffer` semantics documented per symbol — verify it's expressed in points or validated as `points × point`, never carried over "because same decimals".
- [ ] **Spread unit:** The JPY spread was subtracted in JPY price units, not gold dollars — verify a unit assertion exists and the v1.0 68%-of-risk row is not reproduced silently.
- [ ] **Clock basis:** Session/weekend hours were checked against the data's actual clock (per source) — verify a known-anchor timestamp alignment, not an assumption that "server = UTC" transfers.
- [ ] **Golden tests:** The full 442-test suite passes with zero edits to golden pins or strategy modules — verify by diff, not by "tests passed".
- [ ] **Live configs untouched:** `config-cent.toml`/`config-btc.toml` and the gold/BTC agents are byte-identical/untouched at milestone end.
- [ ] **Calibration count:** The noise calibration covers every config actually tried in v1.1 (plus the v1.0 look on overlapping data) — verify the count in the report matches the grid, not just the survivors.
- [ ] **Decision rule pre-registered:** The three-way verdict rule (positive / falsified / underpowered) and its threshold existed *before* the confirmatory run — verify by timestamp/commit order.
- [ ] **Source separation:** No metric mixes histdata and broker-native bars — verify each dataset card has one source and the verdict's primary instrument is the broker's own.

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| A1 buffer mis-scaled (e.g., 100-pip stops on EURUSD-class data) | LOW | Re-run with buffer-in-points; compare stop-distance distribution to the structural support distances; no strategy change needed |
| A2/C4 money or symbol contamination (gold labelled EURJPY) | LOW | Fix `[data] symbol`, reload from correct CSVs/broker fetch, re-run; discard the contaminated output file explicitly |
| B1/B2 best-of-N or post-hoc confirmation already reported | MEDIUM | Re-frame as exploratory; count all tries into the calibration; require a genuinely fresh OOS tail before any confirmatory language |
| B3 front-loaded / split-flip verdict already drafted | MEDIUM | Re-run the battery with walk-forward + monthly table; the verdict must cite the later folds |
| B4 underpowered null | LOW | Reclassify as "underpowered, inconclusive"; state required n for the effect size; decide whether more (honest) data exists |
| C1 source mixing in a metric | MEDIUM | Split the metric per source; verdict on the broker-native card only; label reproduced v1.0 numbers as reproductions |
| C2 wrong clock/session hours in results | MEDIUM | Re-anchor timestamps to the verified clock; re-run session-sensitive rows; update the dataset card |
| D1-D2 strategy/golden drift | HIGH (if it reaches the live repo) | Revert the strategy diff; re-run the full suite; re-verify gold/BTC config output byte-identical before anything else |
| D4 live-layer 2-dp change landed | HIGH (live semantics, unverifiable here) | Revert; re-run live-engine + AI-backtest tests; schedule the real fix in the live-wiring milestone with terminal verification |
| D5 live config/agent touched | HIGH (real money) | Restore config from the milestone's untouched copy; re-check agent state and magic dedup; verify no duplicate agents (the two-bots-one-magic bug class) |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| A1 sl_buffer price/point confusion | Phase 1 (buffer-in-points spec) | JPY stop distances land in the expected 0.05–2.0 price range; EURUSD-class 100-pip stop test case |
| A2 contract_size/money conversion | Phase 1 (spec value-per-point + stats guard) | Money stats absent/labelled when spec missing; R metric unchanged |
| A3 2-dp artifact corruption | Phase 1 (digit-aware output boundary) | JPY trades.csv retains 3 dp; live `_round2`/`equivalent_to` untouched |
| B1 post-hoc winner as hypothesis | Phase 3 (pre-registration) | Protocol + decision rule committed before confirmatory run; OOS tail is post-v1.0 data |
| B2 multiple comparison / correlated pair | Phase 3 (calibration + pooled test) | Report shows calibration over all tries incl. v1.0 look; correlation-aware threshold |
| B3 split instability / front-loading | Phase 3 (walk-forward + monthly) | All folds + monthly table reported; later folds carry the verdict |
| B4 low power / three-way verdict | Phase 3 (power analysis + decision rules) | Plan states n/SE/power; verdict is positive/falsified/underpowered |
| B5 drift contamination | Phase 3 (random-entry + mirror + drift-neutral) | Random-entry and drift rows present; buy-and-hold comparison shown |
| B6 overlapping-trade t inflation | Phase 3 (R/day cross-check) | R/day t reported alongside per-trade t |
| C1 broker-vs-vendor mixing | Phase 2 (single-source verdict + dataset card) | One source per card; primary verdict on EURJPYc/GBPJPYc |
| C2 clock/session/weekend | Phase 2 (clock verification + per-instrument schedule) | Anchor-timestamp alignment per source; no setup bars during FX closure |
| C3 spread model & v1.0 contamination | Phase 2 (spread capture) + Phase 1 (unit assert) + Phase 3 (sensitivity) | Spread in JPY units; verdict survives halve/double spread |
| C4 data acquisition (naming/staleness/symbol label) | Phase 1 (symbol assert) + Phase 2 (fetch/fresh) | Config with wrong symbol fails loudly; files load under actual naming |
| C5 sample span expectations | Phase 2 (max honest span) + Phase 3 (n/power protocol) | n and power stated; histdata supplement separately carded |
| D1 pure-chain edits | Phase 1 (zero-edit rule) | Full suite + golden pins pass unchanged; strategy/ diff is empty |
| D2 byte-identical defaults | Phase 1 | Gold/BTC config backtest output numerically unchanged |
| D3 config overloading / live-config drift | Phase 1 | Dedicated backtest configs only; live configs untouched |
| D4 live 2-dp debt | Defer to live-wiring milestone | v1.1 diff contains no live-engine/base.py/ai-engine changes |
| D5 backtest-only scope creep | Phase 1 (CLI guard) + all plan risk sections | Backtest CLI refuses `[live] enabled`; no live config/agent touched |

**Research flags for plan-phase risk sections:**
- Phase 1's top risk is D1/D2 (touching the pure chain / re-baselining golden pins) — put the zero-edit rule and byte-identical gold output in the plan's Risks and merge criteria.
- Phase 2's top risks are C2 (clock) and C3 (spread) — both need terminal-side verification steps, not config guesses; budget a human checkpoint reading `symbol_info` (digits/point/contract/tick_value) for EURJPYc/GBPJPYc off the actual Exness terminal, mirroring the config-eurjpy.toml checklist.
- Phase 3's top risks are B1/B2/B4 — pre-registration and the three-way verdict rule are plan requirements, not report styling.
- A future live-wiring milestone inherits A3/D4 (per-symbol `equivalent_to` tolerance and digit-aware rounding) plus per-symbol magics — recorded here as a deferred dependency, not v1.1 scope.

## Sources

- `trading-bot/.planning/STATE.md` (2026-08-20→2026-09-07 entries: multi-instrument finding, 39-config noise calibration, split-sample instability, XAUUSD +0.092→−0.005 flip, JPY invalid-spread row 2026-08-21, broker-vs-histdata PF 1.29/1.22, session/ORB/vol/HTF falsifications, cent-account 100× cancellation, `_round2`/`equivalent_to`/sl_buffer debt) — HIGH (primary project source).
- `trading-bot/.planning/PROJECT.md` (v1.1 goal/scope, backtest-only, current live bots) — HIGH.
- `trading-bot/.planning/milestones/v1.0-ROADMAP.md` (golden tests, SAFE-01 shared chain, issues resolved) — HIGH.
- `trading-bot/src/trading_bot/backtest/engine.py` (sl_buffer default 0.01, pure chain, session filter after levels) — HIGH.
- `trading-bot/src/trading_bot/backtest/stats.py` (`contract_size × lot` money path) — HIGH.
- `trading-bot/src/trading_bot/cli.py` (2-dp rounding at emit/CSV, `DAT_ASCII_*` histdata glob) — HIGH.
- `trading-bot/src/trading_bot/live/engine.py` (`_round2`, `in_session`, `in_weekend` gold schedule) — HIGH.
- `trading-bot/src/trading_bot/broker/base.py` (`PendingOrder.equivalent_to` 0.01, `SymbolRisk` tick_value rationale) — HIGH.
- `trading-bot/config/config-eurjpy.toml` (unverified placeholder: gold `[data] symbol`, 3-dp note, checklist) — HIGH.
- `trading-bot/config/config-btc-backtest.toml` (backtest-config pattern, 10×point buffer convention) — HIGH.
- `scripts/sweep_btc.py` / `scripts/fetch_broker_history.py` (existing research/fetch harnesses) — HIGH.
- histdata.com download page for EURJPY M1 (2026-09-07): current download naming is `HISTDATA_COM_ASCII_EURJPY_M1_<YYYY>.csv/.zip`, not the repo's `DAT_ASCII_*` glob — MEDIUM (observed on the live page; naming schemes have changed over time — verify against the actual files the user downloads).
- Exness help center / trading-conditions pages — attempted; returned only generic content. Broker symbol facts (EURJPYc digits=3/point=0.001, cent contract sizes, server time offset, session close times, spread levels) are NOT confirmed from an authoritative Exness source in this research and must be read off the terminal in Phase 2 (MEDIUM confidence until then). JPY-cross 3-dp/pip-vs-point conventions are standard industry practice (HIGH) but broker/account specifics are not.
- Project's own falsification battery results (short-side, ORB, volatility, HTF, TP-from-fill, BTC backtest) as the statistical-calibration baseline — HIGH (STATE.md, quick-task summaries).

---
*Pitfalls research for: v1.1 JPY-cross breakout investigation on the gold/BTC breakout bot*
*Researched: 2026-09-07*
