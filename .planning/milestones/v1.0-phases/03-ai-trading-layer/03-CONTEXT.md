# Phase 4: AI Trading Layer — Context (continuation)

**Gathered:** 2026-08-27
**Status:** Ready for planning
**Source:** User request at plan-phase invocation (no discuss-phase run)

<domain>
## Phase Boundary

Continue Phase 4 (AI Trading Layer). Plan 03-01 delivered the AI-layer
foundation (DeepSeek advisor + deterministic gate, offline-first). This
continuation upgrades the bot toward the full hybrid system described in the
user's `updrade.txt` (based on "Everything I've Learned Trading With Claude In
18 Minutes"): live AI verification / paper trading, a news & sentiment data
pipeline, and the monitoring surface — all on the user's chosen stack.

Mapping to `updrade.txt` phases:
- Ph1 Architecture (dual-system) — done (deterministic engine + AI layer, 03-01)
- Ph2 Data access — MT5 + historical bars done; **news/sentiment = plan 03-04**
- Ph2 AI provider — **DeepSeek, not Claude (D-02)**; client done in 03-01
- Ph3 Prompts + deterministic risk — done (03-01 gate + prompts + risk table)
- Ph4 Historical simulation — done (ai-backtest, 03-01)
- Ph4 Paper trading — **live AI verification = plan 03-02**
- Ph5 Deployment — stays behind [ai] enabled + SAFE-03 (human opt-in)
- Ph5 Monitoring & learning — **DuckDB+dbt warehouse (03-03), dashboard (03-05)**

</domain>

<decisions>
## Implementation Decisions

### Provider (D-02)
- **D-01**: Upgrade the bot per `updrade.txt` — the hybrid system where the AI
  proposes (trade idea + daily regime) and deterministic code disposes (gate,
  risk, execution). No live-account AI trading without an explicit human opt-in.
- **D-02**: Use **DeepSeek** as the AI provider — NEVER Claude/Anthropic. This
  is already the codebase provider (03-01: `deepseek-chat`, `deepseek-reasoner`,
  OpenAI-compatible endpoint via stdlib). All plans keep DeepSeek; nothing new
  may introduce an Anthropic dependency.
- **D-03**: Web dashboard stack = **Tailwind + Next.js** (App Router). It
  replaces `scripts/dashboard.py` as the primary monitoring surface.
- **D-04**: Data platform = **DuckDB + DBT** (dbt-duckdb adapter). One local
  analytics database; dbt owns the transforms.

### OpenCode's Discretion
- News/sentiment source: free, keyless RSS feeds (no paid news API) with a
  deterministic lexicon scorer — chosen for the repo's offline-first, zero-cost
  ethos (plan 03-04).
- Dashboard ↔ DuckDB bridge: official `@duckdb/node-api` (Neo client — the old
  `duckdb` npm package is deprecated, verified 2026-08-27) in read-only mode.
- Warehouse scope: ingest every existing artifact (trades, decisions, closes,
  AI calls JSONL, bars); missing files are skipped, never errors.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The upgrade source
- `updrade.txt` (repo root) — the hybrid-system upgrade plan this phase implements

### Existing AI layer (03-01) — the foundation this continuation builds on
- `src/trading_bot/ai/base.py` — AIClient contract (propose_trade / assess_regime)
- `src/trading_bot/ai/engine.py` — AIEngine(LiveEngine): regime gate + proposal gate, fail-open/fail-closed policy
- `src/trading_bot/ai/deepseek.py` — DeepSeek client (stdlib HTTP, env key)
- `src/trading_bot/ai/context.py` — TradeContext/RegimeContext builders
- `src/trading_bot/ai/gate.py` — pure deterministic gate (confidence/bias/stop-integrity)
- `src/trading_bot/ai/mock.py` — offline MockAIClient + RecordingAIClient
- `config/config-ai.toml` — [ai] table, all defaults
- `.planning/phases/03-ai-trading-layer/03-01-PLAN.md` — design decisions + risks (thin live window = follow-up)

### Deterministic core (must stay byte-identical)
- `src/trading_bot/live/engine.py` — LiveEngine (detection/dedup/safety/risk/placement)
- `src/trading_bot/cli.py` — live + ai-backtest subcommands, build_ai_client
- `src/trading_bot/config.py` — config schema (add [news] and [live] fetch_bars)
- `.planning/STATE.md` — decisions table (SAFE-03, magic numbers, risk conventions)

### Data platform (03-03) — the dashboard/news pipelines read it
- `.planning/phases/03-ai-trading-layer/03-03-PLAN.md` — warehouse loader + dbt marts contract

</canonical_refs>

<specifics>
## Specific Ideas

- Live AI paper trading: dry-run/demo with `[ai] enabled`, mock offline default,
  `--provider deepseek` for real calls with `DEEPSEEK_API_KEY` from the env.
- AI monitoring surface (upgrade.txt Ph5 "monitor Claude's outputs for
  hallucination"): the dashboard's AI page renders gate verdicts and regime
  reads so unexpected model behavior is visible.
- The regime context stays honest: bars + (optionally) news sentiment; the
  model never sees "current" prices from its training memory.

</specifics>

<deferred>
## Deferred Ideas

- Live real-account deployment of AI-augmented trading (upgrade.txt Ph5 "launch
  with a small capital allocation") — requires the user to enable [ai] + SAFE-03
  live mode as a separate, explicit decision after paper-trading evidence.
- Brokers beyond MT5 (upgrade.txt names IB/Alpaca/MetaTrader) — the project
  standardizes on MT5; no new broker adapters in this phase.
- Sentiment via a second model call (e.g., DeepSeek scoring news) — deliberately
  NOT used; lexicon scoring keeps the pipeline free and deterministic.

</deferred>

---

*Phase: 03-ai-trading-layer (roadmap Phase 4)*
*Context gathered: 2026-08-27 at plan-phase invocation*
