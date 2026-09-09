# Roadmap: Gold 5m Breakout Bot

**Granularity:** coarse (3-5 phases)
**Mode:** Milestone-grouped — continuous phase numbering across milestones (v1.0 shipped Phases 1-4; v1.1 continues at Phase 5). Never restart at 1.

## Milestones

- ✅ **v1.0 Backtested, Demo-Traded Breakout Bot + AI Trading Layer** — Phases 1-4 (SHIPPED 2026-08-28) — archived to `.planning/milestones/v1.0-ROADMAP.md`
- 🚧 **v1.1 JPY-Cross Breakout Investigation** — Phases 5-7 (roadmapped 2026-09-07) — settle whether the breakout edge is real on EURJPY/GBPJPY via instrument-correct backtests + the falsification battery, including a pre-registered quick-TP scalp variant (VERD-05, added 2026-09-07). BACKTEST-ONLY; live gold/BTC configs and agents untouched.

## Phases

<details>
<summary>✅ v1.0 (Phases 1-4) — SHIPPED 2026-08-28</summary>

- [x] Phase 1: Strategy Core — Detection + Backtest (5/5 plans) — completed 2026-08-11
- [x] Phase 2: Live Execution — MT5 Order Placement + Safety (6/6 plans, 02-06 deferred) — completed 2026-08-11
- [x] Phase 3: Robustness — Monitoring, Recovery, Operational Polish (1/1 plan) — completed 2026-08-27
- [x] Phase 4: AI Trading Layer — DeepSeek advisor + warehouse + news + dashboard (5/5 plans) — completed 2026-08-28

Full v1.0 phase detail lives in `.planning/milestones/v1.0-ROADMAP.md`.

</details>

**🚧 v1.1 JPY-Cross Breakout Investigation (in progress):** Phases 5-7 below. Ordering is research-authoritative — code before data, data before verdict, pre-registration before any confirmatory run.

### Phase 5: Instrument-Correct Backtest Machinery

**Goal**: Researcher can backtest the breakout strategy on EURJPY/GBPJPY M5 bars with instrument-correct money/spread semantics and output rounding — while the legacy gold/BTC path stays byte-identical and every shared seam (pure strategy chain, `run_backtest` event loop, broker ABC, live engine) is untouched.
**Depends on**: v1.0 Phase 4 (existing codebase + 442-test suite as tripwire)
**Requirements**: INST-01, INST-02, INST-03, INST-04
**Success Criteria** (what must be TRUE):
  1. Researcher can backtest on EURJPY/GBPJPY M5 CSVs and get trades CSV + decision log rounded at the instrument's own digits (3-dp JPY), with money per price-unit per lot computed from a broker-captured `InstrumentSpec` (`tick_value / tick_size`) — never gold's `contract_size` assumption.
  2. A config/data symbol mismatch (e.g. an EURJPY backtest whose `[data]` still points at gold) fails loudly with an error naming the mismatch — the gold-labelled-EURJPY trap cannot pass silently.
  3. Spread is netted once per closed trade in the stats layer in the instrument's own price units (replacing the dead `spread_assumption` knob), and the legacy gold/BTC path is unchanged by default.
  4. The backtest CLI refuses any `[live] enabled` config and ships dedicated `config-eurjpy-backtest.toml` / `config-gbpjpy-backtest.toml` templates — backtest-only is structural, not aspirational.
  5. The full 442-test suite is green with zero edits to golden pins or strategy modules, and gold/BTC backtest output is byte-identical (diff-clean, not merely "tests passed") with no diff touching `strategy/*`, `backtest/engine.py`, `broker/*`, or `live/*`.
**Plans**: 4 plans (decomposed via /gsd-plan-phase 2026-09-07)

Plans:
- [x] 05-01-PLAN.md — InstrumentSpec module + spec sidecar loader + config schema growth (spec_file, sl_buffer_points, retire spread_assumption)
- [x] 05-02-PLAN.md — Stats layer: spec value_per_point money conversion + per-closed-trade spread netting (byte-identical legacy defaults)
- [x] 05-03-PLAN.md — Backtest CLI: [live]-enabled refusal, symbol-mismatch guard, digit-aware output rounding, spec→stats wiring
- [x] 05-04-PLAN.md — config-eurjpy-backtest.toml / config-gbpjpy-backtest.toml dedicated backtest templates

Scope walls: the live-layer 2-dp debt (`_round2`, `PendingOrder.equivalent_to`) and any quote→account-currency live fixes are explicitly deferred to a future live-wiring milestone — not smuggled into this backtest-only phase.

### Phase 6: Broker-Native JPY Data + Dataset Integrity

**Goal**: Fresh broker-native EURJPYc + GBPJPYc M5 history fetched to exhaustion with terminal-verified symbol facts, retained per-bar spread, and per-dataset cards — the honest single-vendor substrate every verdict number inherits.
**Depends on**: Phase 5
**Requirements**: DATA-01, DATA-02, DATA-03
**Success Criteria** (what must be TRUE):
  1. Researcher can fetch fresh broker-native EURJPYc and GBPJPYc M5 history to exhaustion (server "Max. bars in chart" raised first), each fetch writing a per-symbol spec sidecar and retaining the per-bar spread column that MT5 already serves.
  2. The real Exness facts — digits, point, contract size, tick value, spread, bar-clock basis, history depth — are verified against the live Windows terminal at a human checkpoint and cross-checked against Market Watch; recorded, never trusted from config comments or this research.
  3. Each acquired dataset has a card recording source, symbol identity, span, bar count, clock anchor (vs a known event), and spread source; bar-consumption through the engine is validated at ~100%, and gold's no-sidecar path is regression-diffed unchanged.
  4. `config-eurjpy-backtest.toml` / `config-gbpjpy-backtest.toml` are finalized from the machine-printed terminal values and an end-to-end smoke run executes on both crosses (gold no-sidecar path unchanged).
**Plans**: TBD (decomposed via /gsd-plan-phase)

### Phase 7: Pre-Registered Falsification Battery & Verdict

**Goal**: A defensible verdict mapping every gate of the falsification battery to the pre-registered CONFIRM / REAL-BUT-NEGLIGIBLE / FALSIFIED / UNDER-POWERED-INCONCLUSIVE taxonomy — deciding what the JPY-cross numbers mean and what to do next. Credibility rests on closing the test set before results exist.
**Depends on**: Phase 6
**Requirements**: VERD-01, VERD-02, VERD-03, VERD-04, VERD-05 (VERD-05 added 2026-09-07: quick-TP scalp variant)
**Success Criteria** (what must be TRUE):
  1. The analysis plan is pre-registered before any confirmatory run — fixed parameters, config grid, split boundary, monthly granularity, seed count, and a calibrated |t| threshold that counts the inherited v1.0 best-of-17 look with EURJPY/GBPJPY treated as ~1 correlated family test (no double-counting two legs of one JPY cross as two confirmations).
  2. Researcher can judge the edge net of spread on both crosses through the full battery — full-sample stats, multiplicity calibration, chronological walk-forward fit→test, random-entry coin-flip controls through the real engine, monthly stability with a noise band, and a buy-and-hold drift benchmark per cross.
  3. Researcher can assess economic meaning — stop-distance distribution, spread as % of risk, and affordability at 0.01 lots on the cent account (real means tradeable at minimum size).
  4. A written verdict cell maps every gate to a taxonomy cell (CONFIRM / REAL-BUT-NEGLIGIBLE / FALSIFIED / UNDER-POWERED-INCONCLUSIVE) with n, SE, and power stated and no metric mixing data sources.
  5. The quick-TP scalp variant (VERD-05) is pre-registered and judged as a DISTINCT hypothesis alongside the 1:1 breakout — same M5 breakout signal and SL, TP at `rr_multiple` 0.25 and 0.5 on both crosses, run through the identical battery and reported to the same taxonomy, explicitly not counted as extra confirmations of the 1:1 arm.
**Plans**: TBD (decomposed via /gsd-plan-phase)

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Strategy Core | v1.0 | 5/5 | Complete | 2026-08-11 |
| 2. Live Execution | v1.0 | 6/6 | Complete | 2026-08-11 |
| 3. Robustness | v1.0 | 1/1 | Complete | 2026-08-27 |
| 4. AI Trading | v1.0 | 5/5 | Complete | 2026-08-28 |
| 5. Instrument-Correct Backtest Machinery | v1.1 | 4/4 | Complete | 2026-09-08 |
| 6. Broker-Native JPY Data + Dataset Integrity | v1.1 | TBD | Not started | - |
| 7. Pre-Registered Falsification Battery & Verdict | v1.1 | TBD | Not started | - |

## Coverage Check (v1.1)

| Requirement | Phase | Status |
|-------------|-------|--------|
| INST-01 | Phase 5 — Instrument-Correct Backtest Machinery | Pending |
| INST-02 | Phase 5 — Instrument-Correct Backtest Machinery | Pending |
| INST-03 | Phase 5 — Instrument-Correct Backtest Machinery | Pending |
| INST-04 | Phase 5 — Instrument-Correct Backtest Machinery | Pending |
| DATA-01 | Phase 6 — Broker-Native JPY Data + Dataset Integrity | Pending |
| DATA-02 | Phase 6 — Broker-Native JPY Data + Dataset Integrity | Pending |
| DATA-03 | Phase 6 — Broker-Native JPY Data + Dataset Integrity | Pending |
| VERD-01 | Phase 7 — Pre-Registered Falsification Battery & Verdict | Pending |
| VERD-02 | Phase 7 — Pre-Registered Falsification Battery & Verdict | Pending |
| VERD-03 | Phase 7 — Pre-Registered Falsification Battery & Verdict | Pending |
| VERD-04 | Phase 7 — Pre-Registered Falsification Battery & Verdict | Pending |
| VERD-05 | Phase 7 — Pre-Registered Falsification Battery & Verdict | Pending |

**Coverage:** 12/12 v1.1 requirements mapped ✓ — no orphans, no duplicates.
