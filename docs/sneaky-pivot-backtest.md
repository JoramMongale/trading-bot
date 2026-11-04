# Sneaky Pivot — backtest findings (transcript-verified)

**Verdict: no tradeable edge. Do not deploy.** Under the rules as actually
stated in the video, the strategy is negative *before* costs and worse after.

## Provenance

Transcribed locally with faster-whisper (`scripts/transcribe.py`, distil-large-v3,
26.2 min, 4,785 words) → `output/transcripts/`. Rules below cite timecodes.
Speaker: "Doug", 26 years trading.

An earlier pass tested rules reconstructed from secondhand summaries. That
reconstruction was **wrong on the central point** and its results are void; it
is kept below only to document the correction.

## The rules

**Four "magic lines"** (02:50–04:47)
- range high/low = the **previous day's** high and low
- swing high/low = scanning back through history, the first prior day whose
  high exceeds the range high (resp. low below the range low)

**Location filter** (06:07) — *this is the strategy*
> we are only, I mean only going to buy or sell ... if, and only if it is at one
> of those lines. Anywhere else, leave it alone.

Upper two lines sell-only, lower two buy-only. The system is **mean-reverting**.

**Three candles** (08:37–09:18): c1 opening range (09:30 ET), c2 the "sneaky"
confirmation, c3+ the entry, "in most cases at the 45 minute mark".

**Entry** (13:09) price crossing the sneaky candle's high/low.
**Stop** (13:25) "underneath the big buyer" — beyond the tested level.
**Target** (14:19) the **opposite line**, not a fixed R multiple. R:R is whatever
the geometry gives (median 4.8R here).
**Tolerance** (18:05, 22:00) "technical analysis is not literal ... that's close
enough" — so a level is a zone; swept via `--tol`.

### What the first pass got wrong

| | reconstructed (void) | transcript |
|---|---|---|
| direction | two-sided breakout | **mean reversion** |
| location filter | none | **must be at a level** |
| target | fixed 1–3R | **opposite line** (~4.8R) |
| stop | opposite side of sneaky candle | beyond the level |

## Results — same-session, as taught

| | mean avg_R | positive configs | best |
|---|---|---|---|
| frictionless | **−0.058** | 25/102 | +0.134 |
| with spread | **−0.140** | 8/102 | +0.081 |

Negative before costs — a stronger refutation than the void first pass, which
was at least mildly positive gross (+0.040).

- **Significance:** 0 configs significantly positive. 15 significantly negative
  (1 survives Bonferroni). Best is USTECm tol=0.1 swing at t=0.61, p=0.55.
- **Out-of-sample** (train Mar 2025–Feb 2026, test Feb–Aug 2026): top 8
  in-sample **+0.152 → −0.169** out. **0 of 8** stayed positive. Rank
  correlation train↔test **ρ=+0.05 (p=0.61)** — the ranking carries no
  information forward.

## Why it fails — the premise doesn't hold

`scripts/sneaky_pivot_premise.py` measures the video's two empirical claims
directly over 3,839 setups, with no trading logic involved.

**Claim 1** (07:48) after the open reaches a level, price "visits the swing ...
almost every single time" → measured **54.2%**. A coin flip.

**Claim 2** the target — price travels back to the opposite line:

| | rate |
|---|---|
| opposite range line, **same session** | **6.2%** |
| opposite range line, within 5 days | 49.1% |
| opposite swing line, within 5 days | 35.8% |

The target is a *daily-range-scale* move demanded within a few hours. Exit mix
confirms it: **TP 5.4%, SL 46.8%, EOD 47.8%**. At the median 4.79R geometry the
breakeven hit rate is **17.3%** — the strategy delivers 5.4%.

So the R:R is real but unreachable in the session. Nearly half of all trades
end as untargeted end-of-day closes.

## Steelman: hold longer

Since the target *is* reached 49% of the time within 5 days, `--hold-days 5`
tests holding past the entry day. This is **not his rule** — he is explicitly a
day trader and both live trades in the video close same-session.

Still **−0.113 mean, 32/102 positive**. Short side −0.195 across the board.

One residue worth naming honestly: crypto longs score **+0.530** (n=634 across
overlapping configs) while BTC and ETH *fell* 35% and 47% over the sample, so it
is not simple long beta. But that is "buy dips at prior-day lows, hold a week" —
a different, multi-day strategy, measured on overlapping configs in one
12-month window. It is a hypothesis, not a result.

## Costs

Spread is charged one full round trip per trade; the repo's configs all set
`spread_assumption = 0.0`, which is fine for the structural-stop strategy but
would mislead here. Cost is 0.08 R/trade under these rules — lower than the
0.176 R of the void first pass, because stops are placed beyond a level rather
than inside one candle. **Costs are no longer the binding constraint.** The
strategy fails on its own premise.

## Reproduce

```
.venv/bin/python scripts/sneaky_pivot_v2.py                          # as taught
.venv/bin/python scripts/sneaky_pivot_v2.py --spread-mult 0 --out output/sp2_nospread
.venv/bin/python scripts/sneaky_pivot_v2.py --hold-days 5 --out output/sp2_hold5
.venv/bin/python scripts/sneaky_pivot_premise.py                     # the claims
.venv/bin/python scripts/sneaky_pivot_v2_analyse.py                  # stats
```

## US equities — the instruments he actually trades

The CFD limitation above turned out to matter. Data fetched via yfinance:
3 years daily (`data/equities/daily.csv`, 56 tickers, 40k rows) and 60 days of
15-minute bars (`data/equities/m15.csv`, 87k bars). Universe is built to match
his profile, in three buckets: 2x leveraged single-stock ETFs (his GGLL), volatile
small/mid-caps (his AAOI), and liquid controls including DIA, the ETF twin of the
YM futures he demos on.

### The premise is NOT dead on equities

| target hit, same session | CFDs | US equities |
|---|---|---|
| measured | 6.2% | **21.6%** (upper bound) |

CFDs trade 24h, so their "previous day range" is a 24-hour range — a much larger
distance for one session to cover. That was an artifact of the proxy instruments,
not of the strategy. The 21.6% is an upper bound: daily bars do not record whether
the high or the low printed first.

Two side findings: Claim 1 measures **47.6%** on equities, still a coin flip. And
correlation between "rangeiness" and target rate is **+0.001** — his emphasis on
rangy instruments has no bearing on whether the target prints. SPY, DIA and JPM
score as well as the volatile names.

### Full intraday test (60 sessions, Jun–Aug 2026)

Levels from the 3-year daily file, entries/exits on 15-minute bars, transcript
rules unchanged, costs charged (1–5bp of price, floored at the penny tick).

**Overall avg_R = −0.0001 net, +0.0204 gross.** A flat coin flip — materially
better than the CFD result, and not a losing system.

But nothing is significant: the best config is t=0.74, **p=0.46**. Exit mix is
**EOD 59.9%, SL 29.2%, TP 10.8%**, against a **30.2%** breakeven at the median
2.31R geometry. Resolving intraday ordering roughly halved the daily upper bound,
21.6% → 10.8%, as expected.

Worth noting: **leveraged ETFs are the worst bucket**, every config negative — the
instrument class his own live example comes from.

### What this does and doesn't settle

It rules out the strategy being *catastrophic* on equities, which the CFD run
wrongly implied. It does not establish an edge: 60 sessions is a single regime and
the sample cannot distinguish +0.02R from zero.

A definitive answer needs 1–2 years of intraday equity bars. Yahoo caps 15-minute
data at 60 days. Polygon.io's free tier gives 2 years of consolidated aggregates
(5 calls/min, ample for this universe) and is the natural next step; Alpaca's free
tier is IEX-only, whose thin prints would distort exactly the session highs and
lows the levels depend on.

## Limits

He trades US single stocks and ETFs live and demos on YM Dow futures; the CFD
rows above test whether the level logic generalises, not his book. Equity levels
are built from regular-session daily bars, which is not identical to an
extended-hours-shaded chart. The equity intraday window is 60 sessions.
