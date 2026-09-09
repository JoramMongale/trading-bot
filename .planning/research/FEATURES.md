# Feature Research: JPY-Cross Breakout-Edge Investigation (Milestone v1.1)

**Domain:** Swing-breakout strategy edge verification on EURJPY/GBPJPY M5 (internal research/validation milestone, backtest-only)
**Researched:** 2026-09-07
**Confidence:** MEDIUM-HIGH (methodology + existing-capability claims HIGH from project record; JPY market-microstructure externals MEDIUM; cross-pair correlation LOW-MEDIUM, to be measured on acquired data)

> **Scope note.** The product here is not a user-facing app; it is a *verdict-producing investigation*. "Features" = the analysis elements, machinery changes, and decision gates required to answer "is the breakout edge real on JPY crosses?" to the standard this project already enforces for gold (beat noise via best-of-N |t| calibration, survive fit→test walk-forward, beat random-entry controls, monthly stability, economically meaningful net-of-spread R). The question arrives pre-loaded: EURJPY (+0.135R) and GBPJPY (+0.121R) were the *only* two instruments positive in both halves of the v1.0 17-symbol split test, but both at t≈1.95 with ~100 trades — inside the noise bar. Everything validated and shipped through v1.0 (shared pure strategy chain, backtester, swing S/R + window-bounded expiry, decision-trail logging, `setup_override` random-entry seam, `variant` ablation seam, falsification battery scripts, best-of-N noise calibration) is treated as **existing dependency, not re-research**.

## Feature Landscape

### Table Stakes (the verdict is unattainable without these)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **TS-1. Instrument-correct symbol/config plumbing for both crosses** | `config-eurjpy.toml` explicitly marks `EURJPYc` UNVERIFIED, points `[data]` at gold CSVs, and carries gold's `contract_size=100`; a GBPJPY sibling does not exist. v1.0's own audit: "switching `[live] symbol` alone would NOT work — contract sizes span 1 to 100,000 and quote currencies span five." | MEDIUM | Verify from broker `symbol_info` on the actual cent terminal: digits (JPY crosses are 3-dp → point=0.001, so `sl_buffer=0.01` = 10 points, consistent with gold *by coincidence* — confirm, don't assume), `trade_contract_size`, `trade_tick_value`, lot grid. Set `[data] symbol` per cross and `contract_size` per backtest. Backtest-only milestone — live risk machinery (`SymbolRisk`) is dependency, not deliverable. |
| **TS-2. Fresh broker-native M5 data for EURJPY + GBPJPY, gold-scale depth** | v1.0 lesson: broker-native XAUUSDm measured *weaker* than histdata (avg R 0.091 vs 0.135, wider stops). The freshest, broker-priced substrate is the only honest one; histdata pre-2025 is the optimistic end of the range. | MEDIUM | `scripts/fetch_broker_history.py` is Windows-native and per-config (`terminal_path`), served ~100k M5 bars for XAUUSDm/BTCUSDc. Needs the two JPY symbols to exist on the connected terminal and identical coverage/gap validation. One vendor across train/test and full sample — never mix. |
| **TS-3. Data-continuity/coverage validation for a 24/5 feed** | JPY crosses trade ~121 of 168 hours/week (Fri ~21/22 UTC → Sun ~21/22 UTC close only). Weekly ~48h gaps are *normal* and must not be mistaken for missing files; the gold-era gap threshold (`MAX_M1_GAP = 3 days` ≈ 72h) happens to sit above a 48h weekend but is M1-gold logic — re-check it for M5-JPY, and verify the engine consumed ~100% of bars (the candle-reversal study's 58%-consumption stall fabricated a +0.15R result). | LOW | S/R expiry is bar-count-window-bounded (no ffill), so structural gaps never leak stale levels — the hard part is already solved. Assert identical train/full row counts per the project's own method note. |
| **TS-4. Honest spread model in instrument price units** | The engine has **no cost seam**: `run_backtest` takes no spread, `trade_stats` takes no cost, and `spread_assumption` is dead config read by nothing. Prior studies charged spread *externally* (one spread per round trip). The cost is material here: real EURJPY spread ≈ 4% of risk vs gold's ~1.2% (STATE 2026-08-21). The flat gold `$0.26` spread misapplied to a JPY cross (median stop 0.381) once produced a bogus "68% of risk" row that invalidated an entire study table — that class of error must be structurally impossible. | HIGH | Decide the seam: (a) engine-level per-trade spread charge in the instrument's own price units, or (b) post-engine adjustment of the identical trade records in R terms. Either way, record the mechanism so a gold `$`-spread can never be applied to a JPY cross again. Buy fills at ask (entry + ~spread/2), SL/TP trigger on bid — document the second-order caveat (SL-before-TP pessimism partly covers it) and sweep it (see D-2). |
| **TS-5. Full-sample honest stats on both crosses** | The v1.0 EURJPY/GBPJPY numbers were ~100 trades — standard error ≈ the edge. Fresh full-span data (~100k bars ≈ 13–14 months of 24/5 M5) plus the ~0.85-trades/day gold cadence implies a few hundred trades per cross, enough for the |t| machinery to mean something. | LOW | Existing `trade_stats` output (n, win%, avg win/loss R, net R, PF, max DD) + per-trade `r_multiple`, OPEN excluded from wins/losses but included in net (project convention). Report gross AND net-of-spread; t on net R. |
| **TS-6. Multiplicity-corrected |t| bar (noise calibration)** | This is the project's own standard: best-of-N |t| beats noise routinely (best-of-39 |t|=2.46 beaten by noise 42% of the time). The JPY retest **inherits** selection multiplicity (chosen as best-of-17 in v1.0) and adds every config this investigation runs. Two correlated crosses ≠ 2 independent tries. | MEDIUM | Bookkeeping deliverable: pre-declare the config count, add it to the cumulative project tally, and set the bar before running. Measure realized EURJPY/GBPJPY correlation on the acquired data (shared JPY leg ⇒ high) and count ~1 effective family test. |
| **TS-7. Fit→test walk-forward** | The project's strictest test (fit 2025 → test 2026) is what exposed gold's front-loading (best test t=+0.92 OOS). A verdict on JPY crosses that does not survive the same boundary is not a verdict. | LOW | Pre-register the boundary. Gold's split fits naturally at 2025→2026; an ~13-month JPY span allows the same calendar split or an equivalent fractional split. Existing `falsify_*.py` scripts are the pattern. |
| **TS-8. Random-entry coin-flip control through the real engine** | Established control: random setups via `setup_override` must lose to the real setup or the "edge" is engine fill/slot mechanics, not predictive alpha. Every gold candidate that beat its control was still too small (HTF); every one that lost it was noise. | LOW | Seam exists and is byte-identical-default. Run on both crosses, matching the number of random seeds to the multiplicity bookkeeping. |
| **TS-9. Monthly stability breakdown 2025→2026** | Gold's apparent edge was Jul–Dec 2025 only, flat/negative from 2026-04. The v1.0 JPY ranking was measured on data ending 2026-07 with both halves positive — fresh data must confirm the recent half still carries it. | LOW | Calendar-monthly R/t table per cross, fixed granularity, no re-slicing. Expect thin monthly buckets (tens of trades/month); report power honestly rather than over-reading any single month. |
| **TS-10. Verdict taxonomy with pre-registered thresholds** | The milestone's stated goal is to distinguish "fails because noise/front-loaded" from "real but too small" — different conclusions for what to do next. "Confirm" has never been reached in this project; its definition must be written before results. | MEDIUM | See "Verdict Taxonomy" section. Confirm ≠ t>2 in one window; it is the *whole battery* surviving. |
| **TS-11. Economic-meaning check (net-of-spread R vs account reality)** | The project has twice found an edge that was untradeable anyway: gold's $30 account can't carry the structural stop (0/340 setups pass a 2% gate), and the spread tax on JPY crosses is ~3x gold's. "Real" must mean real *at 0.01 lots on the cent account the user actually runs*. | MEDIUM | Stop-distance distribution per 0.01 lot in USC (min/median/p95/max — gold's blocker analysis is the template), spread cost as % of risk, R/day under the single-slot model, affordability at actual balance. |
| **TS-12. Drift/buy-and-hold benchmark per cross** | Long-only breakout on a drifting pair collects the drift without any edge — measured twice already (BTC: bot +$30.69 vs hold +$135.81 over the same span; gold short-side study: +54% drift, drift-neutral estimate +0.04R). 2025's JPY weakness makes this the first question a skeptic asks. | LOW | Passive-long R over the same span vs strategy net R; report both. R per trade, never points/P&L, as the judgment currency. |

### Differentiators (make the verdict more defensible and more actionable)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **D-1. Pre-registered analysis plan** | The single most effective guard against the "retest the best-of-17 until it graduates" failure mode. Written before results: fixed params (= gold's committed `fractal_*/sr_lookback=60/sl_buffer=10×point`), fixed config grid (`rr_multiple` ∈ {1.0} primary, {1.0, 1.5, 2.0} if the gold rr study's ratios are to be mirrored), fixed split boundary, fixed monthly granularity, fixed number of random seeds, threshold table (Verdict Taxonomy). | LOW | Costs almost nothing and converts every later number into a countable test. Aligns with Core Value's "evidence over hope — every claim is measured against a noise calibration." |
| **D-2. Spread-robustness sweep** | A point spread estimate can be wrong both ways; a verdict that survives spread, 1.5×spread, 2×spread is robust to cost uncertainty. The gold project's flat-$0.30 sweep (9.4% of net, win rate pinned) is the precedent — but JPY needs it in instrument units and preferably per-session percentiles, because spread is a larger fraction of risk there. | MEDIUM | Requires the TS-4 cost seam to be parameterised, not hard-coded. |
| **D-3. Session/liquidity characterisation (descriptive, not a filter)** | JPY crosses have a different liquidity clock than gold (Tokyo + London-overlap concentration; spread widening across the ~21:00–00:00 UTC rollover/Asia-open window — hours the gold bot never traded). Describing *where* setups and fills concentrate and what spread was actually paid there explains the result and informs any future live guard — without re-testing session *filters*, which were falsified on gold (random-time control beat the real London window). | MEDIUM | Deliverable is a report section + spread-by-session table, not a `session_hours` run. If a session hypothesis ever emerges from this, it is a NEW candidate requiring its own full battery. |
| **D-4. Correlation-aware verdict framing** | Answers "are these two confirmations or one?" v1.0 treated EURJPY+GBPJPY as two positive halves; with a shared JPY leg they are closer to one correlated family (~0.8+ expected; measure it). Also the cross-instrument analogue of the between-halves correlation check (+0.27, needed ~0.53). | LOW | Report the realized rolling correlation on the acquired data next to the verdict; if high, the family verdict is one test with two instrument measurements, and disagreement between them is itself informative (mechanical vs regime luck). |
| **D-5. Explicit falsified vs real-but-negligible decision logic** | The HTF study established the vocabulary (real-but-negligible: beats random control AND ablation, fails OOS + economically meaningless). Making the *rule* explicit — which control failures imply "noise" vs "real but too small" — is what lets this milestone answer PROJECT.md's open question instead of just reporting numbers. | LOW | Rule: (a) loses to random-entry control ⇒ engine/mechanics artifact or pure noise; (b) beats random control but fails OOS/monthly ⇒ likely real-but-front-loaded or regime-luck; (c) survives everything but net R is untradeable at 0.01 lots after spread ⇒ real-but-negligible; (d) survives everything with tradeable net R ⇒ confirm. |
| **D-6. Ablation of the claimed mechanism on JPY bars** | The vol-compression study's killer control: strip the claimed mechanism (squeeze filter) and run the plain band-breakout — the stripped version BEAT the filtered one. For the breakout claim, the mechanism is *swing-confirmed S/R + close-above-resistance gating*. Ablation = same engine, same entry mechanics, levels from a naive trailing window (no swing confirmation) or setups at raw N-bar highs — showing the swing-confirmation layer, not just "buy strength", is what carries any edge. | MEDIUM | The `variant` seam pattern applies; needs a small levels-naive variant or a `setup_veto`/level-source parameter. This is the JPY cross-check of the swing-S/R design decision itself. |
| **D-7. Engine-consumption + slot-starvation audit per cross** | Candle-reversal's Buy Stops at unreachable levels stalled the engine at 58% of bars (fake +0.15R). JPY crosses' swing levels may be less reachable than gold's; verify bar coverage AND that never-filled pendings don't silently lock the slot on a 24/5 feed with fewer setups. | LOW | Assert identical train/full rows (existing method note) + pending-fill-rate report. |

### Anti-Features (tempting shortcuts that invalidate the verdict)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **A-1. Per-pair parameter mining until t≈1.95 becomes t>2.5** | "The edge is *almost* there on fresh data — one more lookback/rr/sl_buffer tweak will confirm it." | Every extra config is another test against the same noise distribution; the best-of-N bar rises with each try, and the pair was already selected best-of-17. The v1.1 retest IS the out-of-sample test of that selection — running it until it passes is circular. | Fix params to gold's committed values; if a non-default config is wanted, pre-register the tiny grid (D-1), count every run, and price the bar accordingly. |
| **A-2. Re-sliding the walk-forward boundary / re-running OOS until it looks good** | OOS that fails "because the split hit a bad month" invites boundary nudging. | Choosing the boundary after seeing results is lookahead on the test set — the exact bias the battery exists to kill. | Pre-register fit-2025→test-2026 (or the fractional equivalent). One boundary. |
| **A-3. Ignoring spread, or treating `spread_assumption` as a model** | "Spread is small on FX, it will wash out" / "the config already has a spread field." | `spread_assumption` is read by nothing; the engine is cost-free. Spread is ~4% of risk per trade on JPY crosses — the difference between the v1.0 net R (+0.121…+0.135) being positive or negligible. | TS-4 seam + D-2 sweep. |
| **A-4. Applying gold's dollar spread to a JPY cross** | It was already done once (STATE 2026-08-21) — "the script applied gold's $0.26 spread to a JPY cross whose median stop is 0.381, making the cost 68% of risk instead of ~4%." | Wrong by ~17×; invalidated an entire study table. Unit confusion is the mechanism. | Spread only in the instrument's own price units, read from the broker's symbol spec, asserted sane (< some % of median stop). |
| **A-5. Judging on points or P&L instead of net-of-spread R** | A long-only bot on rising JPY crosses makes money in points without any edge (BTC melt-up: t=20.8 on n=8 while R was negative). | Points/P&L conflate drift with edge; R is the project's judgment currency. | R per trade net of spread + drift benchmark (TS-12). |
| **A-6. Treating EURJPY and GBPJPY as two independent confirmations** | "Two instruments positive = double the evidence." | Shared JPY leg ⇒ highly correlated ⇒ ~one family. Two correlated positives are one observation with two measurements. | D-4: measure correlation, frame as a family verdict. |
| **A-7. Rescue-filtering a failing cross with session/vol filters** | "EURJPY fails all-day but passes in the London window" — each rescued variant looks like progress. | Session (ORB), volatility-compression, and HTF-pullback hypotheses were each falsified on gold with this project's own battery; a rescue-filter on JPY is a brand-new hypothesis needing its own full battery and its own multiplicity count, not a free fix. | Record the variant as a new candidate (SPEC + battery) or defer explicitly. |
| **A-8. Wiring demo/live or a weekend guard before the verdict** | "It's only a demo account / it's nearly 24/5 so no weekend guard needed." | Milestone is backtest-only by decision; gold's weekend-guard hours do not map to FX's Fri 21/22→Sun 21/22 close; demo n is anecdote, not evidence. | Verdict first (TS-10). Live-layer is a separate milestone with its own FX-specific guard work. |
| **A-9. Mixing data vendors across the sample** | histdata gives more history; broker data is fresher — "use both." | Vendor differences changed measured edge on gold (1.29→1.22 PF, stops wider). Mixing vendors across train/test manufactures or hides drift. | One broker-native substrate (TS-2) for every phase of the battery. |
| **A-10. Calendar mining — re-slicing monthly buckets to find a good month** | "If we start the monthly table in March it looks stable." | Post-hoc bucket selection is data dredging at monthly granularity. | Fixed Jan-2025→present monthly table (TS-9). |
| **A-11. Multi-pair live-scale extrapolation** | "If EURJPY confirms, run all JPY crosses / add USDJPY, EURGBP." | Each new instrument is a new test with its own spread/stop economics and correlation to the family; v1.0's 17-symbol sweep is the cautionary tale (best-of-N selection artefact). | One family verdict first; any expansion is its own pre-registered investigation. |

## Feature Dependencies

```
TS-2 fresh broker-native JPY data
   └──requires──> terminal with EURJPYc/GBPJPYc symbols + TS-1 symbol verification
TS-4 honest spread seam
   └──requires──> TS-1 (digits/point/contract) + TS-2 (symbol_info spread read)
TS-5 full-sample stats ──requires──> TS-2, TS-4
TS-7 walk-forward ──requires──> TS-2 (enough span for a 2025→2026-style split)
TS-8 random-entry control ──requires──> TS-2 (existing engine + setup_override seam)
TS-9 monthly stability ──requires──> TS-5 (stats), TS-2 (span)
TS-6 multiplicity bar ──requires──> D-1 (pre-registration) + TS-8 (seed count)
TS-10 verdict taxonomy ──requires──> TS-6/7/8/9 outputs
TS-11 economic check ──requires──> TS-4 (spread %) + TS-5 (stop dist) + broker symbol spec
TS-12 drift benchmark ──requires──> TS-2 (passive-long over same bars)

D-2 spread sweep ──enhances──> TS-4 (needs the seam parameterised)
D-3 session characterisation ──enhances──> TS-9 (explains monthly shape) — descriptive only
D-4 correlation framing ──enhances──> TS-6 (effective test count)
D-5 falsified/negligible rule ──enhances──> TS-10 (decision logic)
D-6 mechanism ablation ──requires──> TS-2; ──conflicts──> A-7 (must be the raw swing-ablation, not a rescue filter)
D-7 consumption audit ──requires──> TS-2 (engine run) ; ──guards──> A-9-variant (stall artifact)

All battery outputs ──feed──> milestone verdict document (TS-10 taxonomy) ──gates──> any v1.2 scope
```

### Dependency Notes

- **[TS-4] requires [TS-1] and [TS-2]:** the spread charge is meaningless without the instrument's real point size (TS-1) and the broker's real current/percentile spread from the connected terminal (TS-2). This is the anti-A-4 constraint made structural.
- **[TS-6] requires [D-1]:** a multiplicity-corrected bar can only be computed if the set of tests is closed *before* results exist; otherwise the count is retrospective and the calibration is theatre.
- **[D-6] conflicts with [A-7]:** the ablation that is *evidence* (strip swing-confirmation → compare) and the rescue-filter that is *mining* (add session/vol to save a failing cross) are easy to confuse. D-6 changes the level *source*; A-7 changes the entry *filter*. Only D-6 is in scope.
- **[D-7] guards every other element:** a stalled engine (never-filled pendings locking the single slot) silently starves the sample and flatters R, exactly as it did for candle-reversal. Run it before trusting any battery output.
- **Everything hinges on TS-2/TS-1:** data and symbol correctness are the load-bearing, least-glamorous features; every downstream number inherits their quality. This mirrors v1.0's lesson that broker-native > vendor data.

## Verdict Taxonomy (conclusion structure — replaces competitor analysis for an internal falsification battery)

| Verdict | Must pass (all of the column) | Net R economics | Consequence |
|---------|-------------------------------|-----------------|-------------|
| **CONFIRM** | Full-sample net-of-spread R positive with \|t\| above the D-1-calibrated bar; OOS walk-forward retains sign and clears a reduced bar; beats random-entry controls; monthly not 2025-only (recent-half positive); D-6 ablation shows swing-confirmation adds value | Tradeable at 0.01 lots on the cent account: spread ≤ ~5% of median stop, median stop affordable at the real balance, positive R/day under single-slot | Justifies a v1.2 milestone (tradeability simulation → demo config → FX-specific live guard work). First confirmed edge in the project. |
| **REAL-BUT-NEGLIGIBLE** | Beats random-entry controls (mechanism is real, not mechanics) AND/OR ablation shows the mechanism adds value; but fails OOS, or monthly is flat/negative recent-half, or net R is positive-but-below the economic floor | Statistically distinguishable from zero but not worth 0.01-lot trading after spread (mirror of HTF: R+0.013, t+1.04) | Clean negative. No live path; record as a tested, understood mechanism. Distinguishes "real signal, wrong instrument/scale" from "no signal." |
| **FALSIFIED (noise/front-loaded)** | Loses to random-entry controls, or full-sample \|t\| below the calibrated bar, or OOS flips sign, or monthly shows the same 2025-only artifact every gold candidate showed | Whatever the gross number, it does not survive the battery | Stop. JPY crosses join the gold candidate list as a falsified family; no further work without a genuinely new mechanism. |

**Pre-registration contract (D-1):** the verdict definition and the threshold values are written into the milestone plan before any of TS-5/6/7/8/9 run. The output artifact is a report (pattern: `.planning/quick/*/SUMMARY.md`) stating which verdict cell was reached and the numbers for each gate.

## MVP Definition

### Launch With (Milestone v1.1 minimum — the "investigation" is not an investigation without these)

- [ ] TS-1 Instrument-correct plumbing + symbol verification (EURJPYc, GBPJPYc) — everything else assumes it
- [ ] TS-2 Fresh broker-native M5 data, both crosses, gold-scale depth + coverage validation — the substrate
- [ ] TS-4 Honest instrument-unit spread seam (net-of-spread R is the judgment currency)
- [ ] TS-5 Full-sample honest stats per cross
- [ ] TS-6 Multiplicity-corrected |t| bar (inherited best-of-17 + pre-declared config count + family correction)
- [ ] TS-7 Fit→test walk-forward
- [ ] TS-8 Random-entry coin-flip control through the real engine
- [ ] TS-9 Monthly stability breakdown 2025→2026
- [ ] TS-10 Verdict taxonomy reached (CONFIRM / REAL-BUT-NEGLIGIBLE / FALSIFIED) with pre-registered thresholds
- [ ] TS-11 Economic-meaning check (stop distribution, spread % of risk, affordability at 0.01 lots)
- [ ] TS-12 Drift/buy-and-hold benchmark per cross
- [ ] D-1 Pre-registered analysis plan (written first — the tool that makes TS-6 honest)
- [ ] D-4 Correlation-aware framing (EURJPY/GBPJPY = one family)
- [ ] D-5 Falsified vs real-but-negligible decision logic
- [ ] D-7 Engine-consumption + slot-starvation audit

### Add After Validation (only reachable if the verdict is CONFIRM)

- [ ] D-2 spread-robustness sweep at broker percentiles (cost-uncertainty check on the confirmed edge)
- [ ] D-3 session/liquidity characterisation write-up (where the edge lives, for a future live guard)
- [ ] D-6 swing-mechanism ablation on JPY bars (already the right cross-check of the S/R design, but its full value is in explaining a CONFIRM)
- [ ] Execution-gate simulation through the real risk gate/lot grid on the confirmed config (the gold blocker-analysis pattern, at 0.01-lot granularity)

### Future Consideration (v2+ — defer; each is a new investigation or a new milestone)

- [ ] Any v1.2 live-layer work (demo config, FX weekend/Fri-close guard — gold's guard hours do NOT transfer to FX's Fri 21/22→Sun 21/22 close)
- [ ] New candidate hypotheses that emerge from D-3 characterisation (each needs its own SPEC + full battery + multiplicity count, per A-7)
- [ ] Wider JPY-cross / instrument-family expansion (USDJPY, EURGBP, …) — pre-registered as its own study, per A-11
- [ ] Tick-level bid/ask data acquisition to replace the TS-4 first-order spread model with true SL/TP trigger-side modeling

## Feature Prioritization Matrix

| Feature | Value | Implementation Cost | Priority |
|---------|-------|---------------------|----------|
| TS-1 Symbol/contract plumbing | HIGH | MEDIUM | P1 |
| TS-2 Broker-native data + coverage | HIGH | MEDIUM | P1 |
| TS-4 Honest spread seam | HIGH | HIGH | P1 |
| TS-5 Full-sample stats | HIGH | LOW | P1 |
| TS-6 Multiplicity-corrected bar | HIGH | MEDIUM | P1 |
| TS-7 Walk-forward | HIGH | LOW | P1 |
| TS-8 Random-entry control | HIGH | LOW | P1 |
| TS-9 Monthly stability | HIGH | LOW | P1 |
| TS-10 Verdict taxonomy | HIGH | MEDIUM | P1 |
| TS-11 Economic-meaning check | HIGH | MEDIUM | P1 |
| TS-12 Drift benchmark | HIGH | LOW | P1 |
| D-1 Pre-registration | HIGH | LOW | P1 (prereq of TS-6) |
| D-4 Correlation framing | MEDIUM | LOW | P1 |
| D-5 Falsified/negligible logic | MEDIUM | LOW | P1 |
| D-7 Consumption/slot audit | HIGH | LOW | P1 |
| D-2 Spread robustness sweep | MEDIUM | MEDIUM | P2 (post-CONFIRM) |
| D-3 Session characterisation | LOW | MEDIUM | P2 |
| D-6 Mechanism ablation | MEDIUM | MEDIUM | P2 |
| v1.2 live/demo wiring | — | HIGH | P3 (blocked on CONFIRM) |
| Instrument-family expansion | — | HIGH | P3 (new investigation) |

**Priority key:** P1 = must have for a defensible verdict (the milestone's whole point); P2 = add once CONFIRM is reached or to explain a CONFIRM; P3 = deferred, each is its own future milestone/investigation.

## JPY-Cross-Specific Reasoning (what changes vs the gold studies)

- **Spread/stop economics are ~3x worse than gold's.** Gold's spread cost measured ~1.2% of risk (flat-$0.30 first-order); the project's own corrected figure for a JPY cross is ~4% of risk, with median structural stop ≈ 0.381 price (~38 pips on a 3-dp quote). The v1.0 +0.121/+0.135R net-of-one-spread ranking therefore has a *gross* edge of roughly +0.16…+0.18 before cost — a cost-sensitivity analysis (D-2) is not decoration, it is the difference between "confirm" and "negligible."
- **24/5 trading vs gold's daily/weekend rhythm.** FX trades continuously Sunday ~22:00 UTC → Friday ~22:00 UTC (high confidence, Wikipedia/BIS; ~21:00/22:00 with DST), i.e. only the weekly ~48h break. No gold-style 1h daily maintenance gap. This changes: (a) bar coverage expectations (24/5 feeds have no weekend-shaped holes to confuse the gap detector), (b) spread behavior — the daily ~21:00–00:00 UTC rollover/Asia-open window where JPY-cross spreads widen is *tradeable time* for a 24/5 bot, unlike gold's off-hours, and (c) any future live guard must be keyed to FX's Friday close, not gold's.
- **Session/volatility character differs from gold.** JPY-cross liquidity concentrates in Tokyo and the London overlap; Japan's own geographic share of FX turnover is small (~3.5% by the 2025 BIS triennial) — the volume that matters is London/NY. M5 swings are proportionally tighter in % price than gold's, so tick-level noise is a bigger fraction of the stop. Characterise (D-3); do NOT filter (A-7 — every session filter hypothesis already falsified on gold).
- **Drift and carry are first-order confounds.** Long EUR/GBP vs JPY paid carry through most of the sample while 2025's JPY weakness drifted both pairs up. A long-only breakout collects both without any edge — the BTC honest-backtest result (+$30.69 vs buy-and-hold +$135.81) and gold's +54% drift are the project's own demonstrations. TS-12 is non-negotiable.
- **EURJPY and GBPJPY are one correlated family.** Shared JPY leg ⇒ high realized correlation (expected ≳0.8; LOW-MEDIUM confidence until measured on acquired data — measure it, D-4). "Positive in both halves" in v1.0 was therefore closer to one observation than two. Also makes any simultaneous long exposure one-directional risk in the event of a JPY spike.
- **Intervention tail risk.** BoJ intervention (and carry-unwind spikes) hit JPY crosses in rare violent moves — fat-tail R, gap-through-stop risk on a ~50h weekend close, and single-month breakage of the monthly table. Not a filter; a reporting obligation (flag intervention months in TS-9) and an argument for the SL-before-TP pessimistic exit already in the engine.
- **Sample-size honesty.** At gold-like setup cadence (~0.85/day ≈ a few hundred trades over ~13 months of 24/5 data) the full-sample t is computable but monthly buckets are thin; the monthly-stability gate should be read as "no 2025-only artifact" rather than over-interpreting any single month's t.

## Sources

| Source | What it supports | Confidence |
|--------|------------------|------------|
| `.planning/STATE.md` (project record, 2026-09-07) | v1.0 multi-instrument results (+0.135R/+0.121R, t≈1.95, both-halves-positive), best-of-39 noise calibration (42% beats \|t\|=2.46), TP-from-fill EURJPY spread-error row (68% vs ~4% of risk), broker-vs-histdata gap, gold blocker analysis, BTC drift trap, dead `spread_assumption`, monthly front-loading pattern, candle-reversal stall method note | HIGH |
| `.planning/PROJECT.md` (2026-09-07) | v1.1 scope (instrument-correct machinery + rigorous verdict, backtest-only), "distinguish noise/front-loaded from real-but-too-small" framing | HIGH |
| `.planning/milestones/v1.0-ROADMAP.md` | Shipped capabilities the investigation depends on (shared pure strategy chain, `setup_override`, `variant`, `rr_multiple`, no-lookahead conventions, decision logging) | HIGH |
| `.planning/quick/20260828-htf-pullback/SUMMARY.md` | Real-but-negligible verdict precedent; control battery structure (ablation, random-bias, train/test, monthly) | HIGH |
| `.planning/quick/20260828-liquidity-sweep-or/SUMMARY.md`, `20260828-volatility-compression/SUMMARY.md`, `20260822-short-side-and-filters/SUMMARY.md` | Random-time/random-signal control patterns; ablation beating filtered strategy; drift-neutral estimation; front-loading artifact across every candidate | HIGH |
| `config/config-eurjpy.toml` | EURJPYc symbol UNVERIFIED, gold-pointed `[data]`, checklist of what instrument-correct plumbing must verify | HIGH |
| `src/trading_bot/backtest/engine.py`, `backtest/stats.py`, `scripts/compare_rr_multiple.py` | No cost/spread seam in engine or stats (cost applied externally in prior studies); `run_backtest` params incl. `setup_override`/`variant`/`rr_multiple`; stats conventions (OPEN handling, R enrichment) | HIGH |
| Wikipedia, "Foreign exchange market" (fetched 2026-09-07) | FX continuous 24h Sunday ~22:00 UTC → Friday ~22:00 UTC except weekends; ~$9.6T/day 2025 BIS triennial; UK 37.8% / US 18.6% / Japan 3.5% of turnover | HIGH (hours); MEDIUM (turnover specifics are BIS-2025-derived) |
| General FX market knowledge (no search tooling available this session — websearch/ctx7/gsd-sdk not installed) | EURJPY/GBPJPY high shared-JPY-leg correlation; BoJ intervention/carry-unwind tail risk on JPY crosses; carry/drift direction of long EUR/GBP vs JPY | LOW-MEDIUM — flagged for verification on acquired data (D-4 measures correlation; TS-9/TS-12 measure drift) |

**Method note on research limits:** no web search tool was available in this environment (no `websearch`/`brave`/`exa`/`gsd-sdk`/`ctx7`); external grounding is limited to one Wikipedia fetch. JPY-microstructure claims are therefore deliberately framed as *to-be-measured-on-acquired-data* items rather than asserted facts, and every project-internal claim cites the planning record above.

---
*Feature research for: Milestone v1.1 JPY-Cross Breakout Investigation*
*Researched: 2026-09-07*
