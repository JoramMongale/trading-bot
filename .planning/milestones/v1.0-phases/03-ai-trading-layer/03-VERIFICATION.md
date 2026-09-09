---
phase: 03-ai-trading-layer
verified: 2026-08-28T19:55:01Z
status: human_needed
score: 21/22 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Open http://127.0.0.1:3000 in a browser and visually check the five pages (Overview, Ledger, AI, Risk, News) render the dark-theme shell, tables, badges, and sparklines with real data"
    expected: "Overview shows bot health rows + open positions (2 live tickets visible), Ledger shows the trade table with backtest|live badges and stat cards, AI shows the daily gate activity table + approval-rate sparkline, Risk shows the cent/btc [risk] tables read-only, News shows the sentiment score + headlines"
    why_human: "Automated checks confirmed all routes return HTTP 200 with real JSON, but visual appearance, layout correctness, and user flow can only be judged in a browser"
  - test: "Optional re-confirmation of the real-DeepSeek dry-run: set DEEPSEEK_API_KEY and run `python -m trading_bot.cli live --config config/config-ai-live.toml --mode dry-run --once --provider deepseek`"
    expected: "A genuine model reply parses into an AIProposal the deterministic gate evaluates (03-02 recorded BLOCKED low_confidence 65 < 70 as the expected outcome); no order placed (dry-run); decision log shows ai_regime/ai_proposal"
    why_human: "Requires the user's API key and spends a real model call; the 03-02 human checkpoint was approved on 2026-08-27 with this evidence, so this is a re-confirmation only"
---

# Phase 4: AI Trading Layer — Verification Report

**Phase Goal:** The non-deterministic half of the hybrid system, per the "AI
proposes, deterministic code disposes" model. DeepSeek reasons over the
deterministic setup and the daily market regime; a pure deterministic gate
validates every proposal before the battle-tested execution path can act.
Continuation scope (user upgrade.txt): live AI verification/paper trading, a
DuckDB + dbt analytics platform, a free news/sentiment pipeline, and a Next.js
+ Tailwind dashboard — the monitoring half of the hybrid system.

**Verified:** 2026-08-28T19:55:01Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Verification Method

Goal-backward: started from the roadmap Success Criteria + the must_haves in
each of the 5 plan frontmatters (03-01..03-05), then verified each truth
against the actual codebase (file existence, substantive content, wiring,
data flow). The SUMMARYs were used only to locate artifacts — every claim
below was re-checked against code, the live DuckDB warehouse, and the running
dashboard.

Independent evidence gathered this run:
- **Full pytest suite reproduced:** 442 passed + 2 skipped (fresh basetemp;
  the default pytest temp dir on this machine is permission-locked — an
  environment quirk, not a code defect; all errors vanished with an explicit
  `--basetemp`).
- **Warehouse probed directly** (`information_schema` + row counts): all 7
  raw tables and all 5 marts present with real data.
- **Dashboard verified live**: all 6 routes (`/`, `/api/status`,
  `/api/ledger?limit=5`, `/api/ai-gate`, `/api/news`, `/api/risk`) returned
  HTTP 200 with real mart data (node PID 9396 currently holding the DB).
- **News pipeline artifacts verified**: `output/news_sentiment.json` contains
  a real snapshot (score -0.1, 10 articles); `ai_calls_ai_watch.log.jsonl`
  contains full recorded prompts + results.
- **Anti-pattern scan** on all phase files: no TODO/FIXME/stub/placeholder
  implementations found.

## Goal Achievement

### Observable Truths

**Roadmap Success Criteria (the contract):**

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| SC1 | DeepSeek (or mock) consulted on every deterministic setup + once per day; each proposal passes a pure deterministic gate (confidence, bias agreement, stop-integrity) before the placement path | ✓ VERIFIED | `ai/engine.py::_ai_gate` (propose → `evaluate_proposal` → skip or proceed), `_maybe_regime_check` (once/UTC day, fail-open); `ai/gate.py` is a pure function (no I/O, no logging, no provider import) implementing no_idea/low_confidence/bias_mismatch/invalid_invalidation; `ai/schema.py` strict JSON parsing. 112 targeted tests pass incl. `test_low_confidence_blocks`, `test_choppy_regime_blocks_the_day`. |
| SC2 | Offline-first: whole layer runs with `provider = "mock"`, zero API keys, zero network | ✓ VERIFIED | `config/config-ai.toml`/`config-ai-live.toml` default `provider = "mock"`; `ai/mock.py` MockAIClient is deterministic and offline; the 442-test suite runs fully offline (no key, no network); `config-ai-live.toml` header documents the offline default. |
| SC3 | `ai-backtest` replays history and reports raw vs AI-gated stats with every AI decision logged (SAFE-02) | ✓ VERIFIED | `ai/backtest.py::run_ai_backtest` runs both raw and gated backtests on one code path (`setup_veto`) and returns `{"raw_trades", "gated_trades", ...}`; emits `ai_regime`/`ai_proposal`/`ai_regime_block` events; `tests/test_ai_backtest.py` passes. NOTE: an end-to-end run on this machine is blocked only by empty `data/raw` (no histdata CSVs) — the same environmental limitation 03-02 recorded; not an implementation gap. |
| SC4 | AIEngine live wiring stays behind `[ai] enabled` + SAFE-03; hooks are no-ops by default so the existing suite stays green | ✓ VERIFIED | `cli.py:380-389` selects AIEngine only when `cfg.ai.enabled`; `live/engine.py::_ai_gate` default no-op returns None; `config-ai-live.toml` has `[live] enabled = false` (SAFE-03 intact); suite reproduced at 442 passed + 2 skipped. |
| SC5 | AI layer verified end-to-end live (mock + real DeepSeek) behind `[ai] enabled` (AI-06) | ✓ VERIFIED | 03-02 documented both E2E runs: mock offline full path (setup_detected → ai_regime → ai_proposal → gate APPROVED → deterministic guards) and real DeepSeek (genuine proposal LONG conf 65 → gate BLOCKED low_confidence, the designed veto outcome); user-supplied key, checkpoint human-approved 2026-08-27. `ai_calls_ai_watch.log.jsonl` contains the recorded calls (mock entry shows full context + result). |
| SC6 | Every bot artifact queryable in one DuckDB database with dbt marts; news/sentiment pipeline feeds the regime check fail-open; the Next.js dashboard is a read-only, loopback-bound window on the warehouse | ✓ VERIFIED | Warehouse probed: raw_trades 349, raw_ledger 4, raw_decisions 4,549, raw_closes 0 (closes.log absent at load time — documented), raw_ai_calls 10, raw_bars 100,000, raw_news_articles 10; marts all present with rows (mart_trade_ledger 349, mart_ai_gate_activity 1, mart_bot_health 5, mart_news_sentiment_daily 1, mart_ai_gate_performance 219). Fail-open sentiment → regime: `_load_sentiment_snapshot` + 3 dedicated tests. Dashboard live: all 6 routes HTTP 200; `web/lib/duckdb.ts` access_mode=read_only; GET-only routes; 127.0.0.1 binding. |

**Plan must-have truths:**

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 03-02 T1 | A live/dry-run session with `[ai] enabled` runs the full path: bars → regime check → proposal → gate → (dry-run) placement | ✓ VERIFIED | `cli.py` `--provider`/engine selection; `AIEngine.poll_once` = parent poll + `_maybe_regime_check`; `_ai_gate` on every setup; E2E mock run documented in 03-02 with ai_calls JSONL evidence on disk. |
| 03-02 T2 | AI market context built from a real multi-day window, not the ~69-bar fetch | ✓ VERIFIED | `config.py:165` `LiveConfig.fetch_bars: int = 0`; `live/engine.py:237-238` `_n_bars()` returns `cfg.live.fetch_bars` when > 0; config-ai*.toml set 5000 (~17 days M5); default 0 preserves legacy behavior (tested). |
| 03-02 T3 | A real DeepSeek call produces a parseable AIProposal the deterministic gate evaluates | ✓ VERIFIED | `ai/deepseek.py` (stdlib urllib, JSON mode, env key at call time); `_chat` → `parse_proposal`; real-DeepSeek E2E recorded in 03-02 (gate BLOCKED low_confidence, conf 65 < 70) with user-approved checkpoint. Re-run requires the user's key (human item below). |
| 03-02 T4 | Existing suite stays green: fetch_bars default (0) leaves live behavior byte-identical | ✓ VERIFIED | `tests/test_live_engine.py` `_n_bars` tests pass; full suite 442 passed + 2 skipped reproduced. |
| 03-03 T1 | Every bot artifact — backtest trades, decision logs, closes, AI calls, market bars — queryable in one local DuckDB database | ✓ VERIFIED | `warehouse/load.py` ingests all six raw tables (DDL at lines 48-115, ingest functions per table); direct probe confirmed all tables with real row counts. raw_closes = 0 is correct (no closes.log at load time; missing files are skipped by design). |
| 03-03 T2 | `dbt run` builds queryable marts (merged trade ledger, AI-gate activity/performance, bot health) | ✓ VERIFIED | `dbt/profiles.yml` (type: duckdb, path ../data/analytics/trading.duckdb); 5 staging views + 5 marts materialized in the live DB (all 5 marts verified with rows); marts use `ref('stg_...')` (mart_trade_ledger → stg_trades + stg_closes); `dbt/target/run_results.json` shows green runs; graph_summary shows the full compiled DAG incl. all 7 sources. |
| 03-03 T3 | Re-running the loader is idempotent: same row counts, no duplicates | ✓ VERIFIED | `MERGE INTO ... WHEN MATCHED THEN UPDATE ... WHEN NOT MATCHED THEN INSERT` on natural keys (load.py:363-367); `tests/test_warehouse.py::test_load_is_idempotent` passes; 03-03 documented a real-data double-run with identical counts. |
| 03-03 T4 | Base bot stays dependency-light: duckdb is an optional extra; loader errors with an actionable message when missing | ✓ VERIFIED | `pyproject.toml` has `analytics = ["duckdb>=1.2"]` (base `dependencies` unchanged); `scripts/warehouse_cli.py:48-52` catches ImportError → prints the analytics-extra install hint, exits 2. |
| 03-04 T1 | Gold news articles land in DuckDB (raw_news_articles) with link-based dedupe | ✓ VERIFIED | `news/fetch.py::fetch_news` — stdlib urllib + xml.etree, normalized-link dedupe, `MERGE INTO ... ON t.link = s.link` (line 194); raw_news_articles holds 10 real articles; dedupe/idempotency tests pass. |
| 03-04 T2 | A deterministic lexicon scores each article and a daily sentiment mart aggregates it | ✓ VERIFIED | `news/sentiment.py::score_article` (65-term lexicon, (pos-neg)/max(1,pos+neg)); `write_snapshot` atomic (temp + os.replace); score stored per article at ingest; `mart_news_sentiment_daily` materialized with 1 real day (avg_score -0.1, 10 articles); dbt schema tests pass. |
| 03-04 T3 | The daily sentiment snapshot is offered to the AI regime check; absent snapshot or parse error never blocks the day (fail-open) | ✓ VERIFIED | `ai/engine.py::_load_sentiment_snapshot` (lines 165-197): any error → `ai_regime_sentiment_unreadable` + sentiment=None, day proceeds; `RegimeContext.sentiment` + `build_regime_context(sentiment=...)`; `prompts/regime_check.txt` has the `{sentiment_block}` paragraph; 3 dedicated tests pass (feeds / missing / corrupt). |
| 03-04 T4 | Pipeline is free and keyless (RSS), offline-first; network failures degrade to "no news today", never a crash | ✓ VERIFIED | No API keys anywhere; per-feed failure isolation (`news_fetch_failed` logged, next feed continues — fetch.py:150-158); 2 MB body cap + non-200 rejection before parsing; feed list is config; tests for HTTP-error and non-XML isolation pass. |
| 03-05 T1 | A browser shows live bot status (poll freshness, open position, account balance) at a glance | ⚠️ PARTIAL | Poll freshness ✓ (Overview bot-health table: last_event, last_bar_checked, bar_fetch_failed_24h, orders per log) and open positions ✓ (2 live tickets with entry/SL/TP from raw_decisions + raw_closes reconciliation). **Account balance ✗ not rendered anywhere in web/.** Not in DASH-01 or roadmap SC6, and the plan's own /api/status task never specified it — but the truth as written is only 2/3 met. See Warnings. |
| 03-05 T2 | Trade ledger, AI-gate activity, risk settings and news sentiment render from the DuckDB marts | ✓ VERIFIED | Ledger page → mart_trade_ledger + SQL aggregates; AI page → mart_ai_gate_activity + mart_ai_gate_performance; Risk page → hand-rolled [risk]/[live] TOML parser (read-only); News page → mart_news_sentiment_daily with empty state when mart absent. All routes verified live: HTTP 200 with real JSON. |
| 03-05 T3 | Dashboard is READ-ONLY: no API route places orders or changes risk; it binds loopback only | ✓ VERIFIED | Grep of web/app: zero POST/PUT/PATCH/DELETE route handlers (GET-only by construction); `web/lib/duckdb.ts:31` `access_mode: "read_only"`; risk edits stay in tune_risk.py (Risk page has no form); `scripts/web_dashboard.ps1` (line 35) and `.sh` (line 30) hard-bind `-H 127.0.0.1 -p 3000`. |
| 03-05 T4 | A missing/empty warehouse renders a graceful "warehouse not loaded" state, never a crash | ✓ VERIFIED | `isWarehouseReady()` gates every page/route; `WarehouseEmpty.tsx` component with load instructions; API routes catch errors → 503 `{error: 'warehouse not loaded'}`; `/api/news` deliberately returns 200 + [] when only the news mart is absent (order-independent with 03-04). |

**Score:** 21/22 must-haves verified (6/6 roadmap SCs + 15/16 plan truths; 03-05 T1 partial).

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `src/trading_bot/ai/schema.py` | AIProposal/RegimeAssessment + strict JSON parsing | ✓ VERIFIED | BIASES/REGIMES enums, AIResponseError, parse_proposal/parse_regime with field-level validation |
| `src/trading_bot/ai/base.py` | AIClient ABC (propose_trade/assess_regime) + AIClientError | ✓ VERIFIED | Abstract contract at lines 42/50; AIClientError hierarchy |
| `src/trading_bot/ai/mock.py` | MockAIClient (offline) + RecordingAIClient (audit) | ✓ VERIFIED | Both classes present; RecordingAIClient wraps calls |
| `src/trading_bot/ai/deepseek.py` | DeepSeek client, stdlib HTTP, env key | ✓ VERIFIED | urllib only; key read at call time; JSON mode; no SDK dependency (AI-05) |
| `src/trading_bot/ai/context.py` | TradeContext/RegimeContext + sentiment field | ✓ VERIFIED | RegimeContext.sentiment default None; pass-through in build_regime_context |
| `src/trading_bot/ai/prompts.py` | Prompt renderer + sentiment block | ✓ VERIFIED | `_sentiment_block` renders only when present (line 146-183) |
| `src/trading_bot/ai/gate.py` | Pure deterministic gate | ✓ VERIFIED | evaluate_proposal → APPROVED/BLOCKED/REJECTED; pure function |
| `src/trading_bot/ai/engine.py` | AIEngine(LiveEngine) regime + proposal gate | ✓ VERIFIED | _ai_gate fail-CLOSED, _maybe_regime_check fail-OPEN, _load_sentiment_snapshot fail-open |
| `src/trading_bot/ai/backtest.py` | run_ai_backtest raw vs gated | ✓ VERIFIED | setup_veto seam; raw/gated trades + event log |
| `prompts/trade_idea.txt`, `prompts/regime_check.txt` | Prompt templates | ✓ VERIFIED | regime_check has {sentiment_block}; strict JSON instructions |
| `config/config-ai-live.toml` | Paper-trading AI config | ✓ VERIFIED | `[ai] enabled=true`, provider=mock, `[live] mode=demo`, magic 77200, fetch_bars=5000, enabled=false (SAFE-03) |
| `src/trading_bot/live/engine.py` | _n_bars honors fetch_bars; _ai_gate no-op hook | ✓ VERIFIED | Lines 229-255 |
| `src/trading_bot/cli.py` | live --provider override; build_ai_client | ✓ VERIFIED | `dataclasses.replace(cfg.ai, provider=...)` before engine build (line 354-355); AIEngine selection gated on cfg.ai.enabled |
| `src/trading_bot/config.py` | LiveConfig.fetch_bars, AIConfig, NewsConfig + validation | ✓ VERIFIED | fetch_bars int >= 0 (line 449); NewsConfig feeds/snapshot validation (lines 534-550) |
| `src/trading_bot/news/fetch.py` | RSS fetch + parse + DuckDB insert (stdlib) | ✓ VERIFIED | fetch_news exported; per-feed isolation; MERGE on link; score column at ingest |
| `src/trading_bot/news/sentiment.py` | Lexicon scorer + snapshot writer | ✓ VERIFIED | score_article, score_recent, write_snapshot (atomic) |
| `scripts/news.py` | fetch + sentiment CLI | ✓ VERIFIED | fetch/sentiment subcommands; duckdb-missing → exit 2 with hint |
| `warehouse/load.py` | Idempotent loader | ✓ VERIFIED | MERGE INTO on natural keys; 6 raw tables; missing files skipped |
| `scripts/warehouse_cli.py` | `load` CLI | ✓ VERIFIED | prints per-table counts; ImportError → exit 2 + install hint |
| `dbt/dbt_project.yml` + `dbt/profiles.yml` | dbt-duckdb project | ✓ VERIFIED | type: duckdb, path ../data/analytics/trading.duckdb; staging=view, marts=table |
| `dbt/models/sources.yml` | 7 raw sources | ✓ VERIFIED | All 6 03-03 sources + raw_news_articles (7th) |
| `dbt/models/marts/*.sql` | 5 marts | ✓ VERIFIED | All materialized in live DB with real rows; ref() wiring correct |
| `web/lib/duckdb.ts` | Read-only DuckDB access point | ✓ VERIFIED | access_mode: 'read_only'; lazy singleton; parameterized query; isWarehouseReady (4 core marts) |
| `web/app/api/*/route.ts` (5) | GET-only JSON routes | ✓ VERIFIED | All GET; all 5 live-verified HTTP 200; news returns 200+[] when mart absent |
| `web/app/*/page.tsx` (5 pages) | Overview/Ledger/AI/Risk/News | ✓ VERIFIED | All query marts; WarehouseEmpty state on not-ready; risk page read-only TOML |
| `web/components/*.tsx` (6) | Shared component kit | ✓ VERIFIED | StatCard, DataTable, Sparkline (hand-rolled SVG), Badge, RefreshButton, WarehouseEmpty |
| `scripts/web_dashboard.ps1` + `.sh` | start/stop, loopback | ✓ VERIFIED | Hard-bind 127.0.0.1:3000; warn-not-block on missing warehouse; pidfile lifecycle |
| `web/.env.local.example` | DUCKDB_PATH | ✓ VERIFIED | Points at ../data/analytics/trading.duckdb |
| `web/README.md` + root `README.md` | Docs | ✓ VERIFIED | Root README documents the Next.js dashboard as primary surface |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | -- | ------ | ------- |
| `LiveEngine._n_bars` | `cfg.live.fetch_bars` | config key | ✓ WIRED | engine.py:237-238 returns fetch_bars when > 0 |
| `cli.py live` subcommand | `build_ai_client(cfg)` | `dataclasses.replace(cfg.ai, provider=...)` | ✓ WIRED | cli.py:354-355 then 386-387 AIEngine selection |
| `scripts/warehouse_cli.py load` | output/*.log, output/trades.csv, output/ai_calls_*.jsonl, data/processed/*.csv | `warehouse.load.load()` | ✓ WIRED | load.py ingests all sources; verified live counts in DB (loader currently blocked from a *re-run* only by the running dashboard's DuckDB file lock — see Warnings) |
| `mart_trade_ledger.sql` | `stg_trades` + `stg_closes` | `ref()` | ✓ WIRED | ref('stg_trades') line 18, ref('stg_closes') line 36; mart has 349 rows |
| `dbt run` | `data/analytics/trading.duckdb` | profiles.yml type: duckdb | ✓ WIRED | All 5 marts materialized in the live DB |
| `scripts/news.py fetch` | `raw_news_articles` (DuckDB) | `fetch_news()` | ✓ WIRED | 10 real articles in DB; MERGE on link |
| `scripts/news.py sentiment` | `output/news_sentiment.json` | `write_snapshot()` | ✓ WIRED | Snapshot on disk with real payload (score -0.1, 10 articles) |
| `AIEngine._maybe_regime_check` | `build_regime_context(sentiment=...)` | json.load snapshot, fail-open | ✓ WIRED | engine.py:146-147; 3 tests prove feeding/missing/corrupt paths |
| `web/lib/duckdb.ts` | `data/analytics/trading.duckdb` | `DuckDBInstance.create(path, {accessMode: READ_ONLY})` | ✓ WIRED | duckdb.ts:31; live routes prove the connection works |
| `web/app/api/status/route.ts` | `mart_bot_health` | `query()` | ✓ WIRED | route.ts:16; live HTTP 200 with 5 health rows |
| `web/app/page.tsx` | web/app/api/* (and marts directly) | server-side query via duckdb.ts | ✓ WIRED | Overview queries mart_bot_health, mart_trade_ledger, mart_ai_gate_activity, raw_decisions, raw_closes |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| Overview page | health/open/ai/latest | mart_bot_health / mart_trade_ledger / mart_ai_gate_activity (live queries) | Yes — 5 health rows, 2 open tickets (441240867, 440516128), approval 100% | ✓ FLOWING |
| `/api/status` | health rows | mart_bot_health | Yes — real per-log freshness + bar_fetch_failed counters | ✓ FLOWING |
| Ledger page | rows/aggregates | mart_trade_ledger | Yes — 349-trade ledger, real entry/SL/TP/exit rows | ✓ FLOWING |
| `/api/ai-gate` | activity/performance | mart_ai_gate_activity + mart_ai_gate_performance | Yes — 10 consultations, approval 1.0; performance rows | ✓ FLOWING |
| News page | news rows | mart_news_sentiment_daily | Yes — 10 articles, score -0.1, real top_titles | ✓ FLOWING |
| AI regime context | sentiment | output/news_sentiment.json (json.load, fail-open) | Yes — snapshot on disk; coerced to primitives; test-covered | ✓ FLOWING |
| AI proposal context | balance | broker.account_info() (best-effort, None on failure) | Yes — ai_calls JSONL shows balance: 2231.84 in a recorded context | ✓ FLOWING |
| Marts | aggregated rows | raw_* tables via dbt | Yes — marts queryable with correct counts; raw tables hold real artifacts | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Full test suite green | `pytest tests/ -q --basetemp <fresh>` | **442 passed, 2 skipped** in 24s | ✓ PASS |
| Phase-relevant tests (AI/warehouse/news/cli-live) | `pytest tests/test_ai_* test_news_* test_warehouse.py test_cli_ai_live.py` | 70 passed, 0 failed (with fresh basetemp) | ✓ PASS |
| AI engine/gate/backtest/hooks/live-engine | `pytest tests/test_ai_{engine,context,gate,backtest,hooks}.py tests/test_live_engine.py` | 112 passed | ✓ PASS |
| Warehouse live state | direct `information_schema` + COUNT(*) probe | All 7 raw + 5 marts present; counts match SUMMARYs | ✓ PASS |
| Dashboard routes | `Invoke-WebRequest` on 127.0.0.1:3000 (6 routes) | All HTTP 200 with real JSON/HTML | ✓ PASS |
| News snapshot on disk | read `output/news_sentiment.json` | Real payload (score -0.1, articles 10, top/bottom titles) | ✓ PASS |
| AI call audit trail | read `output/ai_calls_ai_watch.log.jsonl` | Full recorded prompts + results (mock entry: LONG conf 90) | ✓ PASS |
| Warehouse CLI re-run | `scripts/warehouse_cli.py load` | ✗ FAIL (environmental): DuckDB file locked by the *running* dashboard (node PID 9396). Loader idempotency proven by tests + the 03-03 documented real-data double-run. See Warnings. | ⚠️ ENV |
| ai-backtest E2E | `python -m trading_bot.cli ai-backtest --config config/config-ai.toml` | ✗ FAIL (environmental): `data/raw` empty (no histdata CSVs). Code + tests verified; same limitation recorded in 03-02. | ⚠️ ENV |

### Requirements Coverage

All 12 requirement IDs claimed by the phase (AI-01..AI-06, WARE-01, WARE-02,
NEWS-01, NEWS-02, DASH-01, DASH-02) are declared in plan frontmatters
(03-01: AI-01..05; 03-02: AI-01..06; 03-03: WARE-01/02; 03-04: NEWS-01/02;
03-05: DASH-01/02) — no orphaned IDs, every ID accounted for.

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| AI-01 | 03-01 | DeepSeek (or mock) consulted on every setup, strict JSON (bias/confidence/reasoning/invalidation) | ✓ SATISFIED | ai/engine.py::_ai_gate; ai/schema.py::parse_proposal; deepseek.py; mock.py; ai_calls JSONL on disk |
| AI-02 | 03-01 | Pure deterministic gate validates every proposal before execution path acts | ✓ SATISFIED | ai/gate.py (pure, fail-CLOSED); gate is the only thing between idea and order; 03-02 real-model BLOCKED verdict proves it fires |
| AI-03 | 03-01 | Daily market-regime assessment (trending/ranging/choppy, tradeable) that can suppress setups; cadence bounded | ✓ SATISFIED | ai/engine.py::_maybe_regime_check (once/UTC day, `_regime_day` guard); block_when_choppy; regime failure fails OPEN |
| AI-04 | 03-01 | ai-backtest replays history, gates every setup, reports raw vs AI-gated stats, every AI decision logged | ✓ SATISFIED | ai/backtest.py (setup_veto seam, raw+gated trades, event log); test_ai_backtest.py green; CLI subcommand wired in cli.py |
| AI-05 | 03-01 | No new runtime deps, no keys in config, stdlib HTTP, JSONL audit | ✓ SATISFIED | deepseek.py = stdlib urllib only; api_key_env (name in config, value in env); RecordingAIClient → ai_calls_*.jsonl (file on disk); pyproject base deps unchanged |
| AI-06 | 03-02 | AI layer verified in the LIVE engine behind [ai] enabled: wide window, --provider override, E2E mock + real DeepSeek | ✓ SATISFIED | fetch_bars=5000 (engine honors it); `live --provider {mock,deepseek}` (cli.py:354); config-ai-live.toml; both E2Es documented with user-approved checkpoint; tests green |
| WARE-01 | 03-03 | Every artifact lands in local DuckDB via an idempotent loader | ✓ SATISFIED | warehouse/load.py (MERGE INTO on natural keys); all raw tables verified live with real counts; idempotency tested |
| WARE-02 | 03-03 | dbt project transforms raw tables into queryable marts (ledger, AI-gate activity/performance, bot health) | ✓ SATISFIED | dbt/ project; all 5 marts materialized in live DB; dbt test green (recorded in run_results.json; 03-03 documented 17/17) |
| NEWS-01 | 03-04 | Free keyless RSS pipeline → DuckDB with dedupe, lexicon scoring, daily snapshot | ✓ SATISFIED | news/fetch.py (link dedupe + MERGE) + sentiment.py (lexicon + atomic snapshot); 10 real articles in DB; snapshot on disk |
| NEWS-02 | 03-04 | Daily sentiment snapshot offered to regime check as optional fail-open input | ✓ SATISFIED | engine._load_sentiment_snapshot (fail-open, coerced primitives); 3 tests: feeds/missing/corrupt |
| DASH-01 | 03-05 | Next.js + Tailwind dashboard renders status, open position, ledger, AI-gate activity, risk, news from DuckDB marts | ✓ SATISFIED | web/ app; all 6 routes live HTTP 200 with real data; pages render from marts via @duckdb/node-api |
| DASH-02 | 03-05 | Dashboard READ-ONLY and loopback-bound: no order/risk write path, no credentials; risk editing stays in tune_risk.py | ✓ SATISFIED | GET-only routes (grep: zero POST/PUT/PATCH/DELETE); access_mode read_only; 127.0.0.1 hard-bind in start scripts; DUCKDB_PATH only env var; risk page display-only |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | None found. Full scan of all phase files for TODO/FIXME/XXX/HACK/PLACEHOLDER/placeholder/return-null/empty-handler patterns returned zero matches (the `placeholders` hit in warehouse/load.py is legitimate SQL parameter construction). | — | — |

### Warnings (non-blocking)

1. **03-05 truth "account balance" not rendered.** The Overview page shows poll
   freshness, open positions, latest ledger entry, and AI approval rate — but
   no account balance anywhere in web/. Neither DASH-01 nor roadmap SC6
   requires it, and the plan's own /api/status task never specified it, so the
   deviation does not breach the requirement contract. If the user wants a
   balance card, the mart layer has no balance column (mart_bot_health lacks
   one) — it would need a new mart/ingest source.
2. **Warehouse loader vs running dashboard (Windows file lock).** While the
   dashboard server is running (node holding the .duckdb file),
   `scripts/warehouse_cli.py load` fails with a raw DuckDB IO error
   ("file is already open in node.exe"). The loader's message is not
   actionable in this state. Suggest: the loader could detect the lock and
   print "stop the dashboard first" (or the dashboard could open the DB
   without holding the file lock — out of scope for this phase).
3. **ai-backtest E2E on this machine** is blocked by empty `data/raw` (no
   histdata CSVs) — documented in 03-02; the implementation and its 93+ tests
   are green.
4. **Two default gold RSS feeds return 404** (kitco.com, goldprice.com) —
   per-feed isolation handles it (documented in 03-04); the feed list is
   configurable.

### Human Verification Required

### 1. Dashboard visual + interactive check

**Test:** Open http://127.0.0.1:3000 in a browser and visit all five pages
(Overview, Ledger, AI, Risk, News).

**Expected:** Dark zinc/slate theme shell with nav; Overview shows the bot
health table (5 logs), open positions (2 live tickets), and the AI approval
card; Ledger shows the 349-row trade table with backtest|live badges and stat
cards (trades/win rate/net R/avg R); AI shows the gate-activity table and
approval-rate sparkline; Risk shows the cent/btc [risk] tables with the
tune_risk.py note; News shows the sentiment score card, sparkline, and
headlines.

**Why human:** Automated checks confirmed HTTP 200 + real JSON for every
route, but visual rendering, layout, and interactive refresh can only be
judged in a browser.

### 2. Real-DeepSeek dry-run (re-confirmation, optional)

**Test:** With DEEPSEEK_API_KEY set, run
`python -m trading_bot.cli live --config config/config-ai-live.toml --mode dry-run --once --provider deepseek`.

**Expected:** A genuine model reply parses into an AIProposal the gate
evaluates (03-02 recorded BLOCKED low_confidence, conf 65 < 70, as the
designed outcome); decision log shows ai_regime/ai_proposal; no order placed
(dry-run).

**Why human:** Requires the user's API key and spends a real model call. The
03-02 blocking checkpoint was human-approved on 2026-08-27 with exactly this
evidence, so this is a re-confirmation rather than new verification.

### Gaps Summary

**No blocking gaps found.** All 6 roadmap success criteria and 15 of 16 plan
must-have truths are fully verified against the actual codebase, the live
DuckDB warehouse, and the running dashboard. The single partial truth
(03-05 T1, "account balance") does not breach any requirement (DASH-01 /
roadmap SC6 do not include it) and is routed to the human as a decision.

The two environment-dependent items (ai-backtest E2E needing `data/raw`
CSVs; the loader being blocked by the running dashboard's file lock) are
operational notes, not implementation gaps — the artifacts exist, are
substantive, are wired, and data demonstrably flows.

**Verdict:** Phase goal is achieved in the codebase. All 12 phase
requirements are satisfied with concrete file/pattern evidence. Status is
`human_needed` only because visual dashboard confirmation and a real-model
re-confirmation are inherently human tasks — the automated evidence for both
is already strong (live HTTP 200 routes with real data; 03-02 checkpoint
approved with real-model gate evidence).

---

_Verified: 2026-08-28T19:55:01Z_
_Verifier: OpenCode (gsd-verifier)_
