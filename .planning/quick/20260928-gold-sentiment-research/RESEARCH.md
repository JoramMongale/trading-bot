# Gold-Applicable Sentiment Signal — Research (quick task)

**Researched:** 2026-09-28
**Domain:** Macro/positioning sentiment as a direction gate on the gold both-direction breakout edge
**Confidence:** MEDIUM (sources verified reachable; a-priori rationale is well-established but untested on this exact book)

## Summary

The gold both-direction single-slot book is **already positive but thin**: long leg
R+0.126/t+2.27, both R+0.081/t+1.94, short ~flat (R+0.023/t+0.36) — full sample on
`XAUUSDc_M5_broker.csv` (100k bars, 2025-04-01 → 2026-08-28). The edge is
**concentrated in the long leg**, so the highest-leverage "improvement" is a filter
that suppresses *long* trades when the macro backdrop is gold-hostile, not one that
tries to rescue the short leg. Crypto F&G is **not** gold-applicable (BTC's filter
merely softened a negative edge; gold's drivers are macro, not crypto crowd
psychology). The `sentiment`/`sentiment_band` seam in `run_backtest` is
direction-agnostic and already takes *any* daily Series mapped via `map_to_bars`
(shift(1)+ffill), so DXY / US10Y / COT / VIX all plug straight in — but the seam only
implements **trade-with-regime** (direction mask), so **contrarian** needs a series
inversion and **no-trade-on-extremes** needs a new seam (or reuse `setup_veto`).

**Primary recommendation:** Build and falsify a **DXY regime gate** first (trade-with:
weak dollar → long-only, strong dollar → short-only), then a **US10Y yield gate**
(same shape), then the sharpest variant — a **DXY+10Y composite "macro headwind"
no-trade-longs gate**. COT managed-money is a defensible *contrarian* third candidate
but is weekly + lagged, which the ~17-month gold overlap makes statistically thin.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Fetch macro series (DXY/yield/COT/VIX) | Backtest data-prep | — | Keyless stdlib fetcher + JSON/CSV/zip cache, mirroring `news/fear_greed.py` |
| Daily→M5 alignment (shift(1)+ffill) | Backtest data-prep | — | Existing `map_to_bars` is generic; reuse as-is |
| Direction/no-trade gating | Backtest engine | — | `sentiment` seam (mask) or `setup_veto` (skip); live engine never reads it |
| Regime computation (MA, net-%OI) | Backtest data-prep | — | Derived in a pure module, not in the engine |

## Candidate Signals (ranked)

| # | Signal | Source (verified) | Granularity | History | Gold rationale | Circular? |
|---|--------|-------------------|-------------|---------|----------------|-----------|
| 1 | **DXY (USD index) regime** | Yahoo `DX-Y.NYB` chart API | Daily | 1971→now (17k bars) | Classic inverse driver of gold (strong dollar = gold headwind) | No — separate instrument |
| 2 | **US10Y yield regime** | Yahoo `^TNX` chart API | Daily | 1970→now (14k bars) | Opportunity cost; rising real/nominal yields = gold headwind | No — separate market |
| 3 | **COT managed-money positioning** | CFTC `com_disagg_txt_{YEAR}.zip` | Weekly (Tue snapshot, Fri release) | 1986→now (yearly zips) | The canonical gold "sentiment"; crowded net-long is contrarian | No — positioning, not price |
| 4 | **DXY+10Y composite headwind** | Combine 1+2 | Daily | 1970→now | Both hostile ⇒ no-trade longs (long leg is where the edge lives) | No |
| — | VIX (risk) | CBOE `VIX_History.csv` | Daily | 1990→now (9k bars) | Weak: gold is not a clean risk-on/off asset | No, but weak a-priori |
| — | GLD ETF holdings/flows | Yahoo `GLD` / SSGA | Daily | 2004→now | Retail/positioning sentiment (dumb-money contrarian) | Partly |
| — | Gold own MA / 20d return | derive from `XAUUSDc_M5_broker.csv` (resample daily) | Daily | on-disk (2025→) | **Not sentiment — price momentum on the same series the breakout trades** | **Yes** |
| — | Existing RSS lexicon pipeline | `news/fetch.py` + `news/sentiment.py` | intraday | DB population date→now only | Gold-specific but no clean historical backtest | No, but not backtestable |

**Prose on the contenders:**

- **DXY (1) — the strongest a-priori.** Gold's inverse correlation to the dollar is one
  of the most robust macro relationships in finance. DXY is a *different* instrument, so
  a DXY regime gate is genuinely external "sentiment/macro", not a second momentum filter
  on gold's own price. [ASSUMED: well-established finance prior, not re-derived this session]
  Fetch is trivial and verified reachable (Yahoo chart API, keyless with a UA header).
- **US10Y (2) — near-tied for the same reason.** Rising yields raise gold's opportunity
  cost (you give up yield to hold gold). Nominal 10Y is the clean proxy; the *theoretically*
  cleaner "real yield" (TIPS, FRED `DFII10`) is **not fetchable from this machine** (FRED
  times out — see Environment Availability), so nominal 10Y is the practical stand-in.
- **COT managed money (3) — the textbook sentiment, but a different *kind* of gate.**
  Managed-money net positioning is the canonical "smart-money" sentiment; its classical use
  is **contrarian** (extreme net long = crowded = fade). Weekly granularity + 3-day
  publication lag (shift by ≥1 week, not 1 day) + only ~75 weekly obs over the 17-month gold
  overlap make this the weakest *statistical* candidate even though its rationale is strong.
- **DXY+10Y composite no-trade (4) — the sharpest variant given the book's shape.** The edge
  is in the long leg, so "skip longs when macro is gold-hostile" is the most direct way to
  raise avg R and t. Needs a *no-trade* gate, not a direction mask (see Integration).
- **VIX — deprioritized.** Gold's response to risk is ambiguous (risk-off can bid *or* hit
  gold depending on whether it's a dollar/liquidity shock). Weak a-priori, include only as a
  negative control.
- **Gold price MA/20d-return — reject as "sentiment".** It's price momentum on the same
  series the breakout already trades (circular). Only defensible as a regime *context* to the
  AI layer, not as an independent direction gate. [ASSUMED: circularity argument is analytic]
- **Crypto F&G for gold — not applicable (confirmed).** Crypto sentiment has no prior for
  gold. The BTC F&G run showed sentiment filtering on the *right* instrument (BTC) softens but
  never reverses a negative edge; applied to gold it would be the wrong instrument twice over.

## Gating Rules

The existing `sentiment` seam implements **trade-with-regime** only (bullish→long,
bearish→short, neutral/NaN→both). The candidates map to three distinct rule shapes:

| Rule | What it does | Fits | A-priori most defensible for gold? |
|------|-------------|------|-------------------------------------|
| **Trade-with-regime** (trend) | Long-only when macro supports gold, short-only when hostile | DXY, US10Y | **Yes** — breakout continuation holds better in a supportive macro regime |
| **Contrarian** (fade extremes) | Fade crowded positioning (extreme net-long → short/no-long) | COT | **Yes for positioning** — the textbook COT use |
| **Trade/no-trade on extremes** | Suppress one or both directions when macro is hostile | DXY+10Y composite | **Yes for the long leg** — highest leverage given long-leg concentration |

**The circularity flag (price-derived "sentiment"):** any gate built from gold's own price
(MA, 20d return) is a momentum filter on the same series the breakout trades. It cannot
improve the edge independently — it can only re-express what the breakout already sees. Keep
it out of the sentiment shortlist; DXY/yields/COT are external and clean.

**Direction of the gold→sentiment mapping** (for the trade-with seam's 0-100 "gold-bullishness"
scale where 50 = neutral): high DXY → *low* gold-bullishness; high yields → *low*
gold-bullishness; high managed-money net-long → *high* positioning (and, contrarian, a
*short/no-long* signal). Each candidate must be normalized to 0-100 before reuse of the seam.

## Integration Notes

- **The seam is direction-agnostic and already built.** `run_backtest(..., sentiment=<Series>,
  sentiment_band=...)` takes any Series aligned to `df.index`; `news.fear_greed.map_to_bars`
  is generic (aligns tz/resolution, `shift(1)`, `ffill`). DXY/US10Y/VIX/COT all express as a
  daily Series → `map_to_bars` → the seam. **Confirmed: no engine change needed for the
  trade-with gate.**
- **Contrarian (COT) is a one-line inversion** of the series (`100 - value`) before passing —
  no engine change.
- **No-trade-on-extremes (candidate 4) is NOT expressible by the current seam.** The seam only
  *masks one side per bar* (longs on bearish, shorts on bullish); it cannot suppress *both*
  directions. Two options: (a) reuse `setup_veto` (already exists, called per-setup, returns a
  skip reason) — cleanest; or (b) add a small additive `sentiment_no_trade` mask parameter.
- **New fetchers needed** (mirror `news/fear_greed.py`: stdlib urllib + cache + fail-closed):
  - `news/macro.py` — Yahoo chart API for DXY + ^TNX (needs a `User-Agent` header; parse
    `chart.result[0].timestamp`/`indicators.quote[0].close`).
  - `news/cot.py` — CFTC yearly zip (`com_disagg_txt_*.zip`), `zipfile` + parse the
    disaggregated TXT for gold (CFTC code `088691`), extract managed-money long/short, net as
    % open interest.
  - `news/vix.py` (optional) — CBOE `VIX_History.csv` (plain CSV, `DATE,OPEN,HIGH,LOW,CLOSE`).
- **Derive, no fetch:** gold's own daily MA/20d-return from the existing
  `XAUUSDc_M5_broker.csv` (resample close to daily) — only if the circular variant is ever
  wanted as a *context* feature.
- **COT lag:** the Tuesday snapshot is published Friday. No-lookahead needs `shift(1)` *week*
  (or shift to the following Monday), not `shift(1)` day. `map_to_bars`'s daily shift is not
  enough on its own for COT — flag in the fetcher.

## Prior / Falsification Requirements

The honest prior, from STATE.md + the two just-completed measurements:

- Gold's edge is **thin and at the noise bar**: long-only |t|=2.11, both |t|=1.94, against the
  all-time reference |t|=2.46 which pure noise beats **42% of the time at N=39**. A sentiment
  gate must *raise* the edge, not merely soften it (BTC F&G "softened but never reversed" is
  **not** the bar — gold is already positive).
- The book's edge is **concentrated in the long leg** (long +0.126/t+2.27 vs short +0.023/t+0.36).
  The most honest target is "cut losing longs", not "improve shorts".
- **Front-loading is the recurring killer.** Most gold configs were 2025-positive/2026-flat.
  (The *specific* both rr1.0 book was the exception — its 2026 half was actually stronger — but
  the project-wide finding is 2025-only artifacts, so treat any gate as unproven until its 2026
  half is independently positive.)

A gold sentiment gate must clear **ALL** of, on `XAUUSDc_M5_broker.csv`:

1. **Improve the both control** (R +0.0810/t+1.94): the gated book's avg R and |t| must exceed
   the ungated both row, with the improvement attributable to the suppressed side (leg counts),
   not to sample shrinkage.
2. **Beat best-of-N noise.** With ~2-4 signals × ~2-3 gates ≈ **N=6-12 configs**, the best |t|
   must clear P<0.05 vs noise (median best-of-6 ≈ 1.9, best-of-12 ≈ 2.2 — near the 2.46
   reference; pre-register the exact N before running).
3. **Survive 70/30 train/test** with TEST R > 0 AND TEST t > 2.0.
4. **Not front-loaded:** the recent half (2026) must be independently positive, monthly-stable.

**Sample-size caveat (be explicit in the driver):** the gold M5 overlap is only ~17 months
(2025-04 → 2026-08). A *daily* macro gate has ~17 monthly observations to flip regime; a
*weekly* COT gate has ~75 weeks. Monthly-stability and OOS on 17 months is thin — expect
wide t-bands and treat any "pass" as provisional.

## Ranked Recommendation

**Build and measure in this order (backtest-first, nothing live/demo):**

1. **DXY regime gate (trade-with).** Fetch `DX-Y.NYB` daily via Yahoo; compute DXY vs 200d (and
   50d) MA; map to 0-100 gold-bullishness (weak dollar → bullish gold); `map_to_bars` → the
   existing `sentiment` seam, `direction="both"`, band sweep {0, 5, 10}. *Falsify:* does gating
   both by DXY regime raise the both control and survive OOS + not-front-loaded + best-of-N?
2. **US10Y regime gate (same shape).** Fetch `^TNX`; yields vs MA; rising yields → gold-hostile;
   same seam and sweep. *Falsify:* same battery.
3. **DXY+10Y composite "macro headwind" no-trade-longs gate (the sharpest variant).** When BOTH
   DXY strong AND yields rising, suppress *long* setups (via `setup_veto` or a small additive
   `sentiment_no_trade` mask). *Falsify:* this is the direct test of "cut losing longs"; must
   raise long-leg avg R and t without collapsing coverage (stall check: span must stay ~100%).
4. **COT managed-money contrarian (only if 1-3 are built and the appetite remains).** Fetch
   `com_disagg_txt_*.zip`; gold managed-money net % OI; invert to contrarian; `shift(1)` *week*
   (not day); `sentiment` seam. *Falsify:* same battery, but pre-declare the thin-sample caveat.

**Considered, deprioritized:** VIX (weak gold link, keep as negative control), GLD flows
(dumb-money, hard to fetch cleanly, lower prior), gold own-price MA/20d-return (circular —
reject as "sentiment"), the in-repo RSS lexicon (not historically backtestable), crypto F&G for
gold (not applicable).

## Environment Availability (verified from this machine)

| Dependency | Required By | Available | Version/depth | Fallback |
|------------|-------------|-----------|---------------|----------|
| Yahoo chart API (DXY `DX-Y.NYB`) | Candidate 1, 4 | ✓ | 1971→now, 17k daily bars | — |
| Yahoo chart API (US10Y `^TNX`) | Candidate 2, 4 | ✓ | 1970→now, 14k daily bars | — |
| CFTC COT `com_disagg_txt_{YEAR}.zip` | Candidate 3 | ✓ | weekly, 1986→now (yearly zips) | — |
| CBOE `VIX_History.csv` | negative control | ✓ | 1990→now, 9k daily bars | — |
| alternative.me F&G | (existing BTC fetcher) | ✓ | in-repo, keyless | — |
| **FRED** `fredgraph.csv` (DGS10/DFII10/real yields) | real-rate candidate | ✗ | times out from this machine | use `^TNX` nominal via Yahoo |
| FRED API | real-rate candidate | ✗ | needs API key (400 on test key) | — |
| Stooq `dx.f` | DXY alternative | ✗ | JS proof-of-work challenge breaks stdlib urllib | use Yahoo |

**Blocking with fallback:** FRED (real yields) is unreachable — nominal `^TNX` via Yahoo is the
accepted substitute (theoretically second-best, practically clean). **No hard blockers**: every
ranked candidate's source was verified reachable keyless from this machine.

## Common Pitfalls

- **Confusing "soften" with "improve":** BTC F&G softened a negative edge and cleared no bar.
  Gold is positive, so the bar is higher — the gate must *raise* R/t, not just reduce losses.
- **COT lag:** weekly Friday publication of a Tuesday snapshot; a daily `shift(1)` leaks up to
  ~3 days of lookahead. Shift by ≥1 week.
- **DXY-level vs DXY-trend:** the raw DXY *level* is not stationary across decades; gate on
  DXY-vs-its-own-MA (deviation/regime), not the absolute index value, or the 0-100
  normalization will be dominated by the long-run dollar trend.
- **Stall via over-gating:** a no-trade gate that kills too many setups can leave the single
  slot starved (the candle-reversal lesson). The falsifier's coverage check (span ~100%) must
  gate every candidate.
- **Circular gold-price "sentiment":** reject gold MA/20d-return as an independent gate — it is
  the same series the breakout already trades.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | DXY-gold inverse correlation is a robust macro prior | Candidate Signals | Low — widely documented; if broken, DXY gate fails its own battery, cheap to learn |
| A2 | Rising nominal 10Y is a gold headwind (real-rate channel) | Candidate Signals | Low-Medium — nominal ≠ real; if the channel is weak, `^TNX` gate fails the battery |
| A3 | Gold's own MA/20d-return is circular (not sentiment) | Candidate Signals / Gating | Low — analytic argument |
| A4 | "Improve the already-positive edge" = raise R/t + survive OOS + not-front-loaded + beat best-of-N | Prior | None — this is the project's standing noise bar, not a new assumption |

## Open Questions

1. **Is 17 months of gold M5 enough to judge a daily macro regime?**
   - What we know: the overlap is 2025-04 → 2026-08 (~17 months, ~17 monthly regime obs).
   - What's unclear: whether a DXY/yield regime flips often enough in-sample to separate signal
     from noise.
   - Recommendation: measure anyway (cheap), but pre-declare the thin-sample caveat and prefer
     the *daily* DXY/10Y gates over *weekly* COT precisely because of it.
2. **Should the no-trade-longs gate be `setup_veto` or a new `sentiment_no_trade` mask?**
   - What we know: `setup_veto` exists and is a clean per-setup skip; the `sentiment` seam can't
     express "suppress both".
   - Recommendation: prototype with `setup_veto` (no engine change); promote to a parameter only
     if candidate 4 shows promise.
3. **Is nominal 10Y a good enough stand-in for real yields?**
   - What we know: real yield (TIPS `DFII10`) is theoretically cleaner but FRED is unreachable.
   - Recommendation: run nominal 10Y; note the caveat; revisit if FRED access is ever restored.

## Sources

### Primary (HIGH confidence — verified reachable this session)
- Yahoo Finance chart API v8 — `query1.finance.yahoo.com/v8/finance/chart/{DX-Y.NYB,^TNX,GLD}`
  (depth confirmed: 17k/14k/5.5k daily bars).
- CFTC Disaggregated COT — `cftc.gov/dea/newcot/deacom.txt` (current week, gold code `088691`)
  and `cftc.gov/files/dea/history/com_disagg_txt_{YEAR}.zip` (full weekly history).
- CBOE — `cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv` (1990→now).
- In-repo: `news/fear_greed.py` (fetcher pattern), `backtest/engine.py` (`sentiment` seam),
  `scripts/backtest_btc_fng.py` + `falsify_btc_fng.py` (driver/battery to adapt).

### Secondary (MEDIUM confidence)
- STATE.md + `20260909-gold-both-scalper/SUMMARY.md` (the both-book control numbers and the
  long-leg-concentration fact).
- `20260928-btc-fear-greed-direction-filter/SUMMARY.md` (the "soften not reverse" precedent).

### Tertiary (LOW confidence — training-data priors, flagged in Assumptions Log)
- DXY-gold inverse correlation strength; real-yield as gold's primary driver (A1/A2).

## Metadata

**Confidence breakdown:**
- Candidate signals: MEDIUM — sources verified reachable; a-priori macro rationale well-known
  but not re-derived this session.
- Integration: HIGH — the seam and `map_to_bars` were read directly; no-lookahead semantics
  confirmed in code.
- Environment availability: HIGH — every source probe ran on this machine with explicit pass/fail.
- Falsification requirements: HIGH — copied from the two just-run batteries and STATE.md's noise
  calibration.

**Research date:** 2026-09-28
**Valid until:** 2026-10-28 (sources are stable; re-check Yahoo/CFTC URLs before building).
