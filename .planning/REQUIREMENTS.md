# Requirements: Gold 5m Breakout Bot — v1.1

**Defined:** 2026-09-07
**Core Value:** Detect the resistance breakout setup accurately and place correctly-priced Buy Stop orders — no missed setups, no false triggers, sensible risk.

## v1.1 Requirements

Requirements for milestone v1.1 (JPY-Cross Breakout Investigation). Backtest-only —
no demo/live wiring, no live-engine changes. The deliverable is a defensible
verdict on whether the breakout edge is real on EURJPY/GBPJPY.

### Instrument-Correct Backtest Machinery

- [x] **INST-01**: Researcher can backtest the breakout strategy on EURJPY and GBPJPY M5 bars with instrument-correct money/spread semantics — a pure `InstrumentSpec` (symbol, digits, point, tick_size, tick_value, contract_size, spread) captured from the broker terminal, with no changes to the pure strategy chain or the backtest event loop
- [x] **INST-02**: Researcher can round backtest output (trades CSV, decision log) at the instrument's own digits and detect a symbol mismatch between config and loaded data, so a gold-labelled-EURJPY trap fails loudly instead of silently
- [x] **INST-03**: Researcher can net a per-instrument spread cost (in the instrument's own price units) once per closed trade in the stats layer, replacing the dead `spread_assumption` knob — while the legacy gold/BTC path stays byte-identical by default
- [x] **INST-04**: The backtest CLI refuses `[live] enabled` configs and ships dedicated `config-eurjpy-backtest.toml` / `config-gbpjpy-backtest.toml` templates, making backtest-only structural rather than aspirational

### Broker-Native JPY Data + Dataset Integrity

- [ ] **DATA-01**: Researcher can fetch fresh broker-native EURJPYc and GBPJPYc M5 history to exhaustion with a per-symbol spec sidecar and a retained per-bar spread column
- [ ] **DATA-02**: The real Exness facts (digits, point, contract size, tick value, spread, bar-clock basis, history depth) are verified against a live terminal at a human checkpoint — not trusted from config comments or research
- [ ] **DATA-03**: Each acquired dataset has a card recording source, symbol identity, span, bar count, clock anchor, and spread source — with bar-consumption validated and gold's no-sidecar path regression-diffed unchanged

### Pre-Registered Falsification Battery & Verdict

- [ ] **VERD-01**: The analysis plan is pre-registered before any confirmatory run — fixed parameters, config grid, split boundary, monthly granularity, seed count, and a calibrated |t| threshold that counts the inherited v1.0 best-of-17 look (EURJPY/GBPJPY treated as ~1 correlated family test)
- [ ] **VERD-02**: Researcher can judge the edge net of spread via the full battery — full-sample stats, multiplicity calibration, chronological walk-forward fit→test, random-entry coin-flip controls through the real engine, monthly stability with noise band, and a buy-and-hold drift benchmark per cross
- [ ] **VERD-03**: Researcher can assess economic meaning — stop-distance distribution, spread as % of risk, and affordability at 0.01 lots on the cent account
- [ ] **VERD-04**: The milestone ends with a written verdict mapping every gate to a pre-registered taxonomy cell (CONFIRM / REAL-BUT-NEGLIGIBLE / FALSIFIED / UNDER-POWERED-INCONCLUSIVE) with n, SE, and power stated
- [ ] **VERD-05**: The quick-TP scalp variant is pre-registered and judged alongside the 1:1 breakout — same M5 breakout signal and SL (below support) with TP taken at `rr_multiple` 0.25 and 0.5 on both crosses, run through the identical battery (multiplicity calibration, walk-forward, random-entry, monthly, buy-and-hold, spread) and reported to the same verdict taxonomy as a distinct hypothesis (not as extra confirmations of the 1:1 arm)

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

- **LIVE-01**: Multi-instrument live wiring — per-symbol magic numbers, `_round2`/`PendingOrder.equivalent_to` digit-aware fixes, quote→account-currency conversion in the live risk path (deferred from v1.1; only if VERD confirms tradeable)
- **TRADE-01**: Demo/paper-trade a JPY-cross configuration on a dedicated account (only after CONFIRM verdict)
- **SEC-01**: MT5 RPC bridge hardening — bind 127.0.0.1 / SSH tunnel, credential rotation follow-through (carried from v1.0 deferred items)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Demo/live trading of JPY crosses | Verdict milestone — live wiring is structurally refused; nothing trades until VERD confirms an economically meaningful edge |
| Touching the pure strategy chain or `run_backtest` event loop | Shared backtest+live contract; golden 1:1 gold pins must stay byte-identical |
| Modifying live gold/BTC configs or restarting live agents | Live bots keep running untouched through this milestone |
| histdata as the verdict data source | Broker-native only (single vendor across train/test/full); histdata lacks cent symbols + spread and shifted gold PF 1.29→1.22 |
| Engine-level spread/fill modeling | Research resolved to stats-level netting (once per closed trade) |
| Concurrent USDJPY fetch | Money uses tick_value/tick_size; verdict is R-primary |
| AI-gated runs in the battery | AI stays out of the v1.1 verdict by default |
| Rescue-filtering with session/vol hypothesis | Each rescued variant is a new hypothesis needing its own battery |
| Parameter mining per pair | The retest IS the OOS test of the best-of-17 selection; circular |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INST-01 | Phase 5 | Complete |
| INST-02 | Phase 5 | Complete |
| INST-03 | Phase 5 | Complete |
| INST-04 | Phase 5 | Complete |
| DATA-01 | Phase 6 | Pending |
| DATA-02 | Phase 6 | Pending |
| DATA-03 | Phase 6 | Pending |
| VERD-01 | Phase 7 | Pending |
| VERD-02 | Phase 7 | Pending |
| VERD-03 | Phase 7 | Pending |
| VERD-04 | Phase 7 | Pending |
| VERD-05 | Phase 7 | Pending |

**Coverage:**
- v1.1 requirements: 12 total
- Mapped to phases: 12
- Unmapped: 0 ✓

---
*Requirements defined: 2026-09-07*
*Last updated: 2026-09-07 after adding scalp variant (VERD-05)*
