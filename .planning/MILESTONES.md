# Milestones

## v1.0 — Backtested, Demo-Traded Breakout Bot + AI Trading Layer

**Shipped:** 2026-08-28 (audited 2026-09-07)
**Status:** ✅ SHIPPED
**Phases:** 4 | **Plans:** 17 (16 passed + 02-06 deferred) | **Tasks:** ~60
**Audit:** tech_debt — 21/21 requirements, 4/4 phases, integration 10/10, flows 3/3 (see `.planning/milestones/v1.0-MILESTONE-AUDIT.md`)

**Delivered:** A validated strategy/backtest core, real MT5 Buy-Stop placement behind
a demo-safety guard, operational robustness (reconnect, weekend guard, merged
ledger), and the AI half of the hybrid system — DeepSeek advisor + pure
deterministic gate, DuckDB/dbt warehouse, keyless news/sentiment pipeline, and a
read-only Next.js dashboard. Both a gold (XAUUSDc) and BTC (BTCUSDc) bot run
real-money on Exness cent accounts.

**Key accomplishments:**

1. Strategy core with dynamic swing S/R, window-bounded level expiry, and a shared pure-python chain driving both backtester and live engine (39 tests; re-verified 12/12).
2. Real MT5 order placement via a BrokerClient ABC (MT5Broker/SimulatedBroker/DryRunBroker), SAFE-03 demo-only guard, and dry-run no-send E2E (115 tests). First unprompted live trade 2026-08-20: ticket 3113739731, +$42.73.
3. Robustness: auto-reconnect with backoff, pure weekend guard, market-closure survival, and a merged trade ledger (404 suite green).
4. DeepSeek advisor behind a pure deterministic gate — verified E2E with a genuine real-model gate veto (BLOCKED low_confidence 65<70); offline-first mock provider (442 tests passed + 2 skipped).
5. DuckDB + dbt warehouse (idempotent MERGE loader, 5 marts) + keyless RSS news/sentiment feeding the regime check fail-open (dbt run 9/9, test 17/17).
6. Read-only Next.js + Tailwind dashboard on the warehouse marts — all 6 routes HTTP 200 live, visually approved 2026-08-28.

**Known gaps at close (see audit):**
- No persisted VERIFICATION.md for Phases 2 & 3 (accepted verification documented in summaries); 04-01-SUMMARY.md backfilled 2026-09-07.
- 03-HUMAN-UAT partial — optional real-DeepSeek dry-run re-confirmation pending.
- Dashboard `/api/*` routes orphaned; no automated tests for dbt marts or the Next.js app.
- Live strategy edge at/under the noise bar; BTC is a machinery test.

**Archives:**
- `.planning/milestones/v1.0-ROADMAP.md`
- `.planning/milestones/v1.0-REQUIREMENTS.md`
- `.planning/milestones/v1.0-MILESTONE-AUDIT.md`
- `.planning/milestones/v1.0-phases/` (phase execution history)
