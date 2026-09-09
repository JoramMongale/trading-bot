---
phase: 03-ai-trading-layer
plan: 03
subsystem: database
tags: [duckdb, dbt, sql, warehouse, analytics, idempotent]

requires:
  - phase: 03-01
    provides: ai_calls_*.jsonl audit format, [ai] schema
  - phase: 03-02
    provides: live decision logs + ai_calls_*.jsonl artifacts the warehouse ingests
provides:
  - "warehouse/load.py: idempotent DuckDB loader (MERGE INTO on natural keys) for trades/ledger/decisions/closes/ai_calls/bars"
  - "data/analytics/trading.duckdb: one local database queryable by all downstream plans"
  - "dbt project (dbt-duckdb): 5 staging views + 4 marts (trade ledger, AI-gate activity/performance, bot health)"
  - "scripts/warehouse_cli.py: `python scripts/warehouse_cli.py load` CLI"
  - "analytics extra (duckdb) — base bot stays dependency-light; dbt is a dev tool"
affects: [03-04 (news pipeline reads raw tables), 03-05 (dashboard reads marts), future analysis]

tech-stack:
  added: [duckdb (analytics extra), dbt-core 1.12.3, dbt-duckdb 1.11.0]
  patterns:
    - "MERGE INTO ... ON natural key for idempotent loads"
    - "raw_* tables stay close to source; staging casts types + dedupes; marts are the queryable surface"

key-files:
  created:
    - warehouse/__init__.py
    - warehouse/load.py
    - scripts/warehouse_cli.py
    - dbt/profiles.yml
    - dbt/dbt_project.yml
    - dbt/models/sources.yml
    - dbt/models/staging/stg_trades.sql
    - dbt/models/staging/stg_decisions.sql
    - dbt/models/staging/stg_ai_calls.sql
    - dbt/models/staging/stg_closes.sql
    - dbt/models/staging/stg_bars.sql
    - dbt/models/marts/mart_trade_ledger.sql
    - dbt/models/marts/mart_ai_gate_activity.sql
    - dbt/models/marts/mart_ai_gate_performance.sql
    - dbt/models/marts/mart_bot_health.sql
    - dbt/models/schema.yml
    - tests/test_warehouse.py
  modified:
    - pyproject.toml
    - .gitignore
    - README.md

key-decisions:
  - "Natural keys drive idempotency: (source, entry_time, entry) for trades, (source_log, line_number) for decisions/closes, (source_file, ts) for ai_calls, (source_file, time) for bars, (source, row_idx) for ledger"
  - "dbt-duckdb resolves the database path against the CWD, not the profile location — dbt runs from the dbt/ directory so ../data/analytics/trading.duckdb resolves to the repo"
  - "CLI script named warehouse_cli.py (not warehouse.py): the module name collided with the warehouse/ package when test collection injects scripts/ onto sys.path"
  - "Missing artifact files are skipped with a notice, never an error — the warehouse is a convenience, not load-bearing"

patterns-established:
  - "Raw tables stay source-shaped; dbt staging is the type-cast/dedupe seam; marts answer questions (ledger, gate activity/performance, bot health)"

requirements-completed: [WARE-01, WARE-02]

# Metrics
duration: 75min
completed: 2026-08-27
---

# Phase 03: AI Trading Layer — Plan 03 Summary

**An idempotent DuckDB warehouse (raw_* tables) plus a dbt project (5 staging views, 4 marts) turning every bot artifact — 349 trades, 4,549 decisions, 10 AI calls, 100,000 bars — into one locally queryable database**

## Performance

- **Duration:** ~75 min
- **Started:** 2026-08-27T11:20:00Z
- **Completed:** 2026-08-27T12:35:00Z
- **Tasks:** 3 (all auto)
- **Files modified/created:** 19

## Accomplishments

- **Idempotent loader** (`warehouse/load.py`, ~330 lines): `MERGE INTO ... WHEN MATCHED THEN UPDATE ... WHEN NOT MATCHED THEN INSERT` on natural keys for all six raw tables; verified by running twice (identical row counts on fixtures AND on real data). Missing files skipped with a notice; unparseable lines skipped, never raised; no SQL built from file content.
- **CLI** (`scripts/warehouse_cli.py`): `load [--db PATH] [--include-histdata]`, prints per-table counts, exit 0; without duckdb prints the `.venv\Scripts\pip install -e ".[analytics]"` message and exits 2.
- **dbt project** (`dbt/`, dbt-duckdb): sources.yml declares the six raw tables; 5 staging views (typed, deduped by natural key, `ROW_NUMBER() OVER (PARTITION BY ...)`); 4 marts: `mart_trade_ledger` (backtest + live closes union), `mart_ai_gate_activity` (per-day consultations/approved/blocked/rejected/unavailable + approval rate), `mart_ai_gate_performance` (gated vs raw days), `mart_bot_health` (per-log freshness: last event, last bar, bar_fetch_failed in last 24h, orders). `dbt run` 9/9 + `dbt test` 17/17 green.
- **Real-data verification:** loader ingests the live repo artifacts (raw_trades 349, raw_ledger 4, raw_decisions 4,549, raw_ai_calls 10, raw_bars 100,000). Sanity checks hold: `mart_trade_ledger` 349 ≥ 349 raw trades; `mart_ai_gate_activity` has the AI day (2026-08-27, consultations=10, approved=10, approval_rate=1.0 — day derived from actual log timestamps); `mart_bot_health` one row per log file (5 files, incl. live_cent orders=1, live_btc orders=2).
- **Base bot stays dependency-light:** duckdb only in the `analytics` extra; dbt is a dev tool (both installed into the venv). Same duckdb wheel (1.5.5) shared by loader and dbt-duckdb per the plan's pinning note.
- Full suite: **419 passed + 2 skipped** (3 pre-existing dashboard/tune_risk environmental failures unrelated to this plan).

## Task Commits

*No git repository present in this workspace — per-task atomic commits could not be created. All changes verified via test suite, loader idempotency runs, dbt run/test, and the sanity queries instead.*

## Files Created/Modified

- `warehouse/__init__.py` — package docstring + re-export of `load()`
- `warehouse/load.py` — the idempotent loader (DDL, parsers, MERGE upsert)
- `scripts/warehouse_cli.py` — CLI wrapper (stdlib-only; catches duckdb ImportError → exit 2)
- `dbt/profiles.yml` — `trading_bot` profile, type duckdb, path `../data/analytics/trading.duckdb`
- `dbt/dbt_project.yml` — `trading_bot_analytics`, staging=view, marts=table
- `dbt/models/sources.yml` — six raw_* sources
- `dbt/models/staging/*.sql` — 5 typed/deduped staging views
- `dbt/models/marts/*.sql` — 4 queryable marts
- `dbt/models/schema.yml` — not_null + unique tests (17 total)
- `tests/test_warehouse.py` — 4 tests: idempotency, bars count/symbol/tf, missing-file skip, update-not-duplicate
- `pyproject.toml` — `analytics = ["duckdb>=1.2"]` extra
- `.gitignore` — `data/analytics/`, `dbt/target/`, `dbt/logs/`
- `README.md` — new "AI layer + analytics warehouse" section

## Decisions Made

- **Natural-key MERGE** as the idempotency mechanism (per plan): row counts stable across re-runs, updates land in place.
- **dbt runs from `dbt/`** — dbt-duckdb 1.11.0 resolves the relative DB path against the CWD, not profiles.yml; the plan's `--project-dir dbt` invocation was adapted (deviation below).
- **CLI renamed to `warehouse_cli.py`** to avoid shadowing the `warehouse` package (deviation below).
- **Histdata M1 ingestion is opt-in** (`--include-histdata`) per plan — heavy by default off.
- **Mart AI day is data-derived**: the consultation day is 2026-08-27 (the actual ai_proposal timestamps), not the plan's expected 08-26 — the mart is correct, the plan's date was approximate.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `scripts/warehouse.py` name collides with the `warehouse` package**
- **Found during:** task 2 (full-suite collection)
- **Issue:** `scripts/warehouse.py` is itself a module named `warehouse`. Pre-existing test modules (`test_bank_profits.py` etc.) inject `scripts/` at `sys.path[0]` at collection time, so `import warehouse.load` resolved to the script module → `'warehouse' is not a package`. Broke every full-suite run.
- **Fix:** Renamed the CLI to `scripts/warehouse_cli.py` (package name is plan-locked: `warehouse/load.py`). Updated the docstring + CLI prog name; README references it.
- **Files modified:** scripts/warehouse.py → scripts/warehouse_cli.py
- **Verification:** full suite 419 passed + 2 skipped; CLI runs `load` to exit 0.
- **Committed in:** n/a (no git)

**2. [Rule 3 - Blocking] dbt-duckdb resolves the database path against CWD, not the profile file**
- **Found during:** task 2 (first `dbt run`)
- **Issue:** The plan asserted relative paths resolve from profiles.yml's directory; the installed dbt-duckdb 1.11.0 resolves them from the CWD, so `--project-dir dbt` from the repo root pointed at `../data/...` (repo parent) and failed with `Cannot open file`.
- **Fix:** Run dbt with the CWD inside `dbt/` (verified: path `../data/analytics/trading.duckdb` then resolves to the repo database). The `dbt run`/`dbt test` commands in the plan were adapted accordingly.
- **Files modified:** none (invocation-only)
- **Verification:** `dbt run` 9/9 + `dbt test` 17/17 green.
- **Committed in:** n/a

---

**Total deviations:** 2 auto-fixed (both blocking, both environmental — no plan behavior changed)
**Impact on plan:** Both fixes are execution-environment adaptations; the loader, schema, and marts match the plan exactly.

## Issues Encountered

- **19-file scope note (plan-mandated acknowledgement):** the files_modified list exceeds the 15-file guideline because 14 of them are small declarative dbt units (SQL/YAML). Execution context stayed lean (orchestrator routed; each model file is <30 lines); no split into its own plan was necessary this run, but a future revision could group the dbt model block if it grows.
- The dashboard/tune_risk test failures (3) are pre-existing environmental failures, unchanged by this plan.
- Real `closes.log` does not exist in `output/` on this machine — `raw_closes`/`stg_closes` are empty and correct (missing files are skipped by design). `mart_trade_ledger`'s live half will populate once watch_closes.py runs.

## User Setup Required

None. duckdb + dbt are dev-extra installs (documented in README).

## Next Phase Readiness

- Ready for 03-04 (news/sentiment pipeline) and 03-05 (dashboard): 03-04 writes `raw_news_articles` + news marts alongside the existing raw tables; 03-05 reads `mart_bot_health` / `mart_trade_ledger` / `mart_ai_gate_activity` via `@duckdb/node-api`.
- The database file `data/analytics/trading.duckdb` is gitignored and rebuildable from `output/` + `data/processed/` at any time.

---
*Phase: 03-ai-trading-layer*
*Completed: 2026-08-27*
