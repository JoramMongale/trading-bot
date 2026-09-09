---
phase: 03-ai-trading-layer
plan: 05
subsystem: web
tags: [nextjs, tailwind, duckdb, dashboard, read-only, loopback]

requires:
  - phase: 03-03
    provides: DuckDB warehouse + dbt marts (mart_bot_health, mart_trade_ledger, mart_ai_gate_activity, mart_ai_gate_performance) the dashboard reads
  - phase: 03-04
    provides: mart_news_sentiment_daily for the News page (optional — empty state when absent)
provides:
  - "web/ Next.js (App Router + Tailwind) app — the primary monitoring surface, replacing scripts/dashboard.py"
  - "Read-only DuckDB data layer (web/lib/duckdb.ts, @duckdb/node-api, access_mode READ_ONLY)"
  - "Five GET-only API routes + five pages (Overview/Ledger/AI/Risk/News)"
  - "Start/stop scripts (web_dashboard.ps1/.sh) + docs"
affects: [operational monitoring of the hybrid system]

tech-stack:
  added: [next 16.3.3, react, react-dom, tailwind, "@duckdb/node-api"]
  patterns:
    - "Single read-only DuckDB access point (lazy singleton, always parameterized)"
    - "isWarehouseReady() drives graceful empty states — never a crash"
    - "GET-only API routes; risk editing stays in tune_risk.py, never here"

key-files:
  created:
    - web/package.json
    - web/next.config.ts
    - web/tsconfig.json
    - web/app/layout.tsx
    - web/app/globals.css
    - web/app/page.tsx
    - web/app/ledger/page.tsx
    - web/app/ai/page.tsx
    - web/app/risk/page.tsx
    - web/app/news/page.tsx
    - web/components/StatCard.tsx
    - web/components/DataTable.tsx
    - web/components/Sparkline.tsx
    - web/components/Badge.tsx
    - web/components/RefreshButton.tsx
    - web/components/WarehouseEmpty.tsx
    - web/lib/duckdb.ts
    - web/app/api/status/route.ts
    - web/app/api/ledger/route.ts
    - web/app/api/ai-gate/route.ts
    - web/app/api/news/route.ts
    - web/app/api/risk/route.ts
    - web/.env.local.example
    - web/README.md
    - scripts/web_dashboard.ps1
    - scripts/web_dashboard.sh
    - web/scripts/probe-duckdb.mjs
  modified:
    - README.md

key-decisions:
  - "The dashboard is READ-ONLY by construction: DuckDB opened access_mode=read_only, GET-only API routes, no broker/order code imported anywhere"
  - "Loopback-only binding (127.0.0.1) — adds zero network exposure to the unauthenticated MT5 bridge"
  - "mart_news_sentiment_daily is OPTIONAL for readiness (03-04 may not have run): /api/news returns 200 + [] when the mart is absent, 503 only when the whole warehouse is missing"
  - "Risk editing stays in tune_risk.py's warned --yes CLI path — the Risk page is display-only"

patterns-established:
  - "One read-only DuckDB access point, lazy singleton, parameterized SQL — no string-interpolated user input (T-04-05-03)"
  - "WarehouseEmpty state rendered whenever isWarehouseReady() is false — no stack traces in the browser"

requirements-completed: [DASH-01, DASH-02]

# Metrics
duration: n/a (implementation largely complete before this run; verified + documented 2026-08-28)
completed: 2026-08-28
---

# Phase 03: AI Trading Layer — Plan 05 Summary

**A read-only Next.js + Tailwind dashboard on the DuckDB marts — live bot status, trade ledger, AI-gate activity, risk settings and news sentiment — as the primary monitoring surface of the hybrid system (replaces scripts/dashboard.py), loopback-bound with no write path anywhere**

## Performance

- **Duration:** n/a — the app was scaffolded/built in a prior session; this run (2026-08-28) verified the full build + live routes and completed the documentation record.
- **Completed:** 2026-08-28
- **Tasks:** 3 (scaffold+data layer+API, pages+components, integration+scripts+docs)
- **Files modified/created:** 28

## Accomplishments

- **Next.js app** (`web/`, App Router + Tailwind, dark zinc/slate theme): five pages — Overview (status + open position + AI snapshot), Ledger (trade table with backtest|live badges + stat cards), AI (daily gate activity + 14-day sparkline + regime), Risk (cent/btc `[risk]` tables, read-only), News (sentiment sparkline + headlines, empty state when mart absent).
- **Read-only data layer** (`web/lib/duckdb.ts`): the ONLY DuckDB access point — lazy singleton promise of `DuckDBInstance.create(dbPath, {accessMode: 'READ_ONLY'})` (Neo `@duckdb/node-api`), parameterized `query<T>()` helper, `isWarehouseReady()` gating every page/route. dbPath from `DUCKDB_PATH` (default `../data/analytics/trading.duckdb`).
- **Five GET-only API routes** (`web/app/api/*/route.ts`): status (mart_bot_health + open positions from mart_trade_ledger), ledger (limit param + SQL aggregates), ai-gate (mart_ai_gate_activity + performance), news (mart_news_sentiment_daily — 200 + [] when the mart is absent, 503 only when the warehouse is missing), risk (parses `[risk]` from config-cent/btc TOML, never writes). All routes 503 with a clean `{ error: 'warehouse not loaded' }` on failure.
- **Shared components** (`web/components/`): StatCard, DataTable, Sparkline (hand-rolled SVG polyline), Badge, RefreshButton, WarehouseEmpty.
- **Start/stop scripts** (`scripts/web_dashboard.ps1` + `.sh`): warn (don't block) if the warehouse is missing, then `next start -H 127.0.0.1 -p 3000`, pidfile in web/.next/.
- **Docs**: `web/README.md` (load warehouse → install → run, loopback + read-only guarantees) and root README updated (Next.js dashboard = primary surface; scripts/dashboard.py = stdlib fallback).

## Integration Verification (2026-08-28, real warehouse)

`scripts/web_dashboard.ps1 start` → dashboard on http://127.0.0.1:3000 (pid 9124):

| route | HTTP | note |
|---|---|---|
| `/api/status` | 200 | mart_bot_health rows + ledger open-position data |
| `/api/ledger?limit=5` | 200 | mart_trade_ledger rows (entry/sl/tp/exit) |
| `/api/ai-gate` | 200 | mart_ai_gate_activity (10 consultations, approval 1.0) + performance |
| `/api/news` | 200 | mart_news_sentiment_daily (10 articles, score -0.1, titles) |
| `/api/risk` | 200 | cent (cap 20, slots 1) + btc (cap 10, slots 2) `[risk]` tables |
| `/` | 200 | HTML (dark theme shell) |

`npm run build` passes (Next.js 16.3.3, Turbopack, TypeScript clean, 3 static pages + 8 dynamic routes). No route returned a 500 or a stack trace; empty-state behavior was verified in the build path (news page renders empty state when the mart is absent by design).

## Task Commits

*No git repository present in this workspace — per-task atomic commits could not be created. All changes verified via `npm run build`, the live route matrix above, and the plan's automated build checks.*

## Files Created/Modified

- `web/` app — pages (page, ledger, ai, risk, news), layout, globals.css, API routes (status, ledger, ai-gate, news, risk), components (StatCard, DataTable, Sparkline, Badge, RefreshButton, WarehouseEmpty), lib/duckdb.ts, config (package.json, next.config.ts, tsconfig.json), .env.local.example, README.md, scripts/probe-duckdb.mjs
- `scripts/web_dashboard.ps1` + `scripts/web_dashboard.sh`
- Root `README.md` — dashboard section (primary + fallback surfaces)

## Decisions Made

- **Read-only by construction, not by convention** — `access_mode = 'read_only'` on the DuckDB instance, GET-only routes, no POST/PUT/DELETE anywhere, no broker/order imports. Risk editing stays in `tune_risk.py`'s warned CLI. DASH-02 is structural.
- **Loopback-only** — the server hard-binds 127.0.0.1 (no --host option), so the unauthenticated MT5 bridge exposure is not widened by the dashboard.
- **News mart is optional** — readiness checks only the four 03-03 core marts; `/api/news` returns 200 + [] when mart_news_sentiment_daily is absent so verification is order-independent under parallel wave-2 execution (plan-mandated).
- **No chart library** — Sparkline is a hand-rolled SVG polyline; zero extra UI deps beyond the locked stack.

## Deviations from Plan

None. All three tasks landed as specified; the only execution note is that the scaffold had been produced in a prior session and this run completed verification + records.

## Issues Encountered

- **Missing SUMMARY record**: the implementation had been built in a prior session without the GSD SUMMARY.md being written. This run verified the live routes and wrote the record.
- Pre-existing environmental test failures (dashboard.py/tune_risk on this machine) are unrelated to this plan and unchanged.

## User Setup Required

- Load the warehouse before first run: `python scripts/warehouse_cli.py load` then `(cd dbt; dbt run)` — the start script warns if it is missing but does not block.
- `cd web && npm install` once (deps already installed on this machine).

## Next Phase Readiness

- **Phase 4 (AI Trading Layer) is the final phase of milestone v1.** The dashboard completes the monitoring half of the hybrid system; all AI/WARE/NEWS/DASH requirements are now implemented.
- Ready for milestone completion (archive + record) and, per the security config default, a `/gsd-secure-phase 4` pass before advancing.

---
*Phase: 03-ai-trading-layer*
*Completed: 2026-08-28*
