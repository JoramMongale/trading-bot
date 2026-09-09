# Gold 5m Breakout Bot

## Current Milestone: v1.1 JPY-Cross Breakout Investigation

**Goal:** Settle whether the resistance-breakout strategy has a real edge on EURJPY/GBPJPY — the only instruments positive in both halves of the v1.0 cross-instrument split test — via instrument-correct backtests run through the project's rigorous falsification battery.

**Target features:**
- Instrument-correct backtest machinery for JPY crosses (point/contract/spread handling + fresh broker-native EURJPY + GBPJPY M5 data)
- Rigorous verdict on the breakout edge: beat noise (|t| calibration), survive walk-forward fit→test, beat random-entry controls, monthly stability
- Quick-TP scalp variant (same breakout signal + SL, TP at rr_multiple 0.25/0.5) pre-registered and judged as a DISTINCT hypothesis alongside the 1:1 arm (added 2026-09-07)
- Both crosses in scope; BACKTEST-ONLY — no live/demo wiring, no live-layer prep this milestone

**Key context:** v1.0 measured EURJPY +0.135R / GBPJPY +0.121R (both halves positive) but t≈1.95 at ~100 trades — inside the noise bar. Every later candidate (short side, sessions/ORB, volatility, HTF pullback) failed its controls. Distinguish "fails because noise/front-loaded" from "real but too small" — different conclusions for what to do next.

## Current State

**Shipped:** v1.0 (2026-08-28) — Backtested, demo-traded breakout bot + AI trading layer
**In progress:** v1.1 Phase 5 complete (2026-09-08) — Instrument-correct backtest machinery shipped (INST-01..04)
**Live:** Two real-money bots on Exness cent accounts — gold `config-cent.toml` (XAUUSDc, magic 77020) and BTC `config-btc.toml` (BTCUSDc, magic 77021). Both launchd-supervised on macOS; as of 2026-09-07 running on a Windows machine (see STATE.md).
**Stack:** Python + MetaTrader5 API + pandas/numpy · DuckDB + dbt · Next.js + Tailwind dashboard · DeepSeek (mock/deepseek providers, stdlib HTTP)
**Tests:** 534 passed + 2 skipped (2026-09-08, Phase 5 complete)
**Where to look:** strategy/backtest in `src/trading_bot/`; warehouse in `warehouse/` + `dbt/`; dashboard in `web/`; ops scripts in `scripts/`.

The one thing this bot must do — detect the resistance breakout setup and place
correctly-priced Buy Stop orders — is built, verified, and running against real
money. What is NOT yet proven is that the strategy makes money: across 6,541
trades the measured edge is negative/at the noise bar. The machinery is real; the
edge is unproven.

## What This Is

A personal Python trading bot that executes a "high probability setup" on Gold (XAUUSD) and BTC using 5-minute candles. It marks support and resistance from dynamic swing points, waits for a bullish candle close above resistance, and fires a Buy Stop with a configurable risk-reward (TP = entry + rr_multiple × (entry − sl), default 1:1). A DeepSeek advisor reasons over each setup and the daily market regime; a pure deterministic gate validates every proposal before the battle-tested execution path can act. It runs against the trader's own MetaTrader 5 terminal(s), validated first on a backtester and demo account before any live trading.

## Core Value

Detect the resistance breakout setup accurately and place correctly-priced Buy Stop orders — no missed setups, no false triggers, sensible risk. If everything else fails, this must work. (Unchanged — shipping confirmed it remains the right priority.)

## Requirements

### Validated

- ✓ Instrument-correct JPY-cross backtest machinery: pure `InstrumentSpec` sidecar loader, spec-driven money (value_per_point) + per-trade spread netting, digit-aware output, [live]-refusal + dedicated backtest templates — v1.1 (Phase 5, INST-01..04)
- ✓ Dynamic support/resistance detection from swing highs/lows — v1.0 (Phase 1)
- ✓ Buy setup detection: bullish candle close above resistance, prior close ≤ resistance — v1.0 (Phase 1)
- ✓ Buy Stop order placed with SL below support and TP at configured risk-reward — v1.0 (Phase 1/2)
- ✓ Bot connects to MT5 and fetches live 5m bars — v1.0 (Phase 2; live on Windows)
- ✓ Demo-only enforcement (SAFE-03) — v1.0 (Phase 2)
- ✓ Backtester over historical data using the same strategy code — v1.0 (Phase 1)
- ✓ Structured logging of every decision — v1.0 (Phase 1/2/3)
- ✓ Config-driven symbol/timeframe/lot/magic/risk — v1.0 (Phase 1/2)
- ✓ Reconnect, weekend guard, market-closure survival, merged trade ledger — v1.0 (Phase 3)
- ✓ DeepSeek (mock/deepseek) advisor + pure deterministic gate + daily regime — v1.0 (Phase 4)
- ✓ AI backtest (raw vs gated) — v1.0 (Phase 4)
- ✓ DuckDB warehouse + dbt marts — v1.0 (Phase 4)
- ✓ Keyless RSS news/sentiment, fail-open into regime — v1.0 (Phase 4)
- ✓ Read-only Next.js dashboard (ledger/AI/risk/news/status) — v1.0 (Phase 4)

### Active

- [ ] EURJPY/GBPJPY breakout edge verdict — instrument-correct backtest + rigorous controls (v1.1)
- [ ] Prove or disprove the live edge (6,541-trade study: negative/at-noise; best |t|=2.46 vs 42%-noise-beats-it calibration)
- [ ] Security: bind the MT5 RPC bridge to 127.0.0.1 / SSH-tunnel; complete credential rotation after the 2026-08-19 malware incident
- [ ] Dashboard: consume the orphaned `/api/*` routes or delete them; decide whether to add an account-balance card
- [ ] Automated tests for the dbt mart layer and the Next.js app
- [ ] Fix `trade_ledger.py` glob to include the CLI default `live.log`; decide raw_ledger mart consumer

### Out of Scope

- Sell signals / short side — user specified a buy-only strategy for v1; short mirror was investigated and falsified out-of-sample (2026-08-22)
- Multi-timeframe confirmation / session ORB / volatility-compression / HTF-pullback / candle-reversal — each candidate investigated and falsified (2026-08-28 research battery); retained only as backtest test strategies
- Telegram/email notifications — logging only for v1 (candidate for next milestone)
- Risk-based lot sizing — replaced by tick-value-based risk sizing from the broker symbol (built)
- MT5 Strategy Tester integration — building our own backtester instead

## Context

- v1.0 shipped 2026-08-28: full hybrid system running real-money on Exness cent accounts (gold 161693049, BTC 161700182). As of 2026-09-07 both bots run on a Windows machine (poll loop healthy; this was the deferred 02-06 real-MT5 environment).
- The AI layer is deliberately conservative: `[ai] enabled` + `[live] enabled` are separate human opt-ins; configs default offline/mock/demo.
- The strategy's edge is the open question. Every structural candidate (short side, sessions, ORB, volatility, HTF pullback) has been falsified with proper controls. Distinguish "fails because noise/front-loaded" from "real but too small" (HTF pullback) — different conclusions for what to do next.
- Workspace is NOT a git repository — all planning updates are direct file edits (commit/tag steps in the workflow are skipped).

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Dynamic S/R (swing points) | Naive min/max fails in ranging markets | ✓ Good — verified 12/12 |
| S/R expiry window-bounded (no ffill) | ffill carried 2021 levels into 2025 data | ✓ Good — durable fix |
| Own backtester, shared pure strategy chain | Same code backtest + live; scriptable | ✓ Good |
| BrokerClient ABC; MT5 guarded lazy import | macOS-testable; single import site | ✓ Good |
| Risk priced at ask − sl, tick-value sizing | Reference-entry risk exceeded cap | ✓ Good |
| Demo-first, live = explicit opt-in (SAFE-03) | Live never accidental | ✓ Good |
| AI proposes, deterministic gate disposes | Gate fail-CLOSED; regime/news fail-open | ✓ Good |
| rr_multiple default 1.0, aggressive tiers warn-not-block | Measured evidence + user's informed risk choice | ⚠️ Revisit — live risk now 20%/10% caps |
| Weekend guard in code (gold stop 19/resume 21) | Self-imposed; no reliance on external timers | ✓ Good |
| Strategy variants = backtest-only | Candle-reversal etc. falsified; live engine stays breakout | ✓ Good |

## Constraints

- **Tech stack**: Python + MetaTrader5 API + pandas/numpy; DuckDB + dbt; Next.js + Tailwind; DeepSeek via stdlib HTTP.
- **Platform**: MT5 must be running and logged in; MetaTrader5 pip package is Windows-only (macOS dev used the silicon bridge / simulated brokers).
- **Execution**: Buy-only gold/BTC breakout, M5, fixed 0.01 lot base with risk-driven sizing; one bot per config/magic.
- **Safety**: Demo-first; live and AI are separate deliberate opt-ins.
- **Validation order**: backtest → demo → live. Evidence over hope — every claim is measured against a noise calibration.

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-09-08 after Phase 5 execution*
