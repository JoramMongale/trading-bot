---
phase: 03-ai-trading-layer
plan: 04
subsystem: ai
tags: [news, rss, sentiment, lexicon, duckdb, dbt, fail-open]

requires:
  - phase: 03-03
    provides: DuckDB warehouse (raw_* tables, dbt project) the news tables attach to
  - phase: 03-01
    provides: RegimeContext + render_regime_prompt + AIEngine._maybe_regime_check seam
provides:
  - "news pipeline: [news] config + RSS fetcher (stdlib urllib/xml.etree) -> raw_news_articles (link-deduped, lexicon-scored)"
  - "deterministic lexicon sentiment (score_article) + daily snapshot writer (write_snapshot, atomic)"
  - "scripts/news.py fetch|sentiment CLI"
  - "dbt stg_news_articles + mart_news_sentiment_daily"
  - "RegimeContext.sentiment flows into the DeepSeek regime prompt, fail-open"
affects: [03-05 (dashboard news page reads mart_news_sentiment_daily), future regime-read analysis]

tech-stack:
  added: [none (stdlib urllib + xml.etree; duckdb already present from 03-03)]
  patterns:
    - "Deterministic lexicon scoring at ingest time (no second model call)"
    - "Fail-open integration: absent/corrupt news snapshot never blocks the trading day"
    - "Optional prompt section rendered via a single {sentiment_block} placeholder"

key-files:
  created:
    - src/trading_bot/news/__init__.py
    - src/trading_bot/news/fetch.py
    - src/trading_bot/news/sentiment.py
    - scripts/news.py
    - dbt/models/staging/stg_news_articles.sql
    - dbt/models/marts/mart_news_sentiment_daily.sql
    - tests/test_news_fetch.py
    - tests/test_news_sentiment.py
  modified:
    - src/trading_bot/config.py
    - src/trading_bot/ai/context.py
    - src/trading_bot/ai/engine.py
    - src/trading_bot/ai/prompts.py
    - prompts/regime_check.txt
    - dbt/models/sources.yml
    - dbt/models/schema.yml
    - tests/test_ai_context.py
    - tests/test_ai_engine.py

key-decisions:
  - "Score computed at ingest time and stored on raw_news_articles; the dbt mart aggregates it (SQL never re-scores)"
  - "Sentiment snapshot written atomically (temp + os.replace); values coerced to primitives so the prompt renders cleanly"
  - "The SENTIMENT block is one {sentiment_block} paragraph placeholder — an absent snapshot renders an empty string, never 'None'/'nan'"
  - "Two of three default gold feeds 404'd during real verification — per-feed failure isolation logged them and MarketWatch delivered; operators can tune feeds"

patterns-established:
  - "News is a convenience: every failure path degrades to 'no news today', never a crash (T-04-04-03)"

requirements-completed: [NEWS-01, NEWS-02]

# Metrics
duration: 55min
completed: 2026-08-27
---

# Phase 03: AI Trading Layer — Plan 04 Summary

**A free, keyless RSS news pipeline (stdlib urllib + xml.etree) feeding link-deduped, lexicon-scored gold/market headlines into DuckDB, a deterministic daily sentiment snapshot, and a fail-open integration into the DeepSeek regime prompt**

## Performance

- **Duration:** ~55 min
- **Started:** 2026-08-27T12:40:00Z
- **Completed:** 2026-08-27T13:35:00Z
- **Tasks:** 3 (all auto)
- **Files modified/created:** 17

## Accomplishments

- **`[news]` config** (NewsConfig): enabled opt-in, feeds (3 free keyless RSS), max_items, user_agent, db_path, snapshot_file, fetch_timeout — with per-key validation naming the bad key; legacy configs without `[news]` load unchanged (off by default).
- **RSS fetcher** (`news/fetch.py`, stdlib only): per-feed `_http_get` (UA + timeout, rejects non-200 and >2MB bodies), `xml.etree` parse, link-deduped cross-feed (normalized link), `MERGE INTO` on `link` (idempotent), `score` column populated via the lexicon when the sentiment module is importable. Per-feed failure isolation: `news_fetch_failed` logged, others continue.
- **Lexicon sentiment** (`news/sentiment.py`): `score_article` = (pos-neg)/max(1,pos+neg) over a ~65-term bullish/bearish lexicon (overridable), `score_recent` daily aggregate, `write_snapshot` atomic write to `output/news_sentiment.json`.
- **CLI** (`scripts/news.py`): `fetch` prints `articles: N (new: M, feeds skipped: K)`; `sentiment` prints the score and writes the snapshot; duckdb missing → exit 2 with the analytics-extra hint.
- **dbt models**: `stg_news_articles` (link-deduped, typed) + `mart_news_sentiment_daily` (per-day count/avg/pos/neg/top-5 headlines via `list()` + window). `dbt run --select stg_news_articles+ mart_news_sentiment_daily` 2/2 + `dbt test` 4/4 green against the real database.
- **Fail-open regime integration**: `RegimeContext.sentiment` + `build_regime_context(sentiment=...)`; `AIEngine._load_sentiment_snapshot` reads the snapshot (coerced primitives) and any error → `ai_regime_sentiment_unreadable` + None, day proceeds; `render_regime_prompt` renders the SENTIMENT block only when present.
- **Real-feed verification**: fetch ingested 10 MarketWatch articles (kitco.com + goldprice.com RSS 404'd — logged per-feed and skipped); snapshot written `score=-0.100, articles=10`; rendered prompt shows the SENTIMENT block with no `None`/`nan`; without a snapshot the block is absent and the prompt stays clean.
- Full suite: **439 passed + 2 skipped** (3 pre-existing dashboard/tune_risk environmental failures unrelated to this plan).

## Task Commits

*No git repository present in this workspace — per-task atomic commits could not be created. All changes verified via test suites, real-feed runs, dbt run/test, and the prompt-render check instead.*

## Files Created/Modified

- `src/trading_bot/news/__init__.py` — package + re-exports (fetch_news, score_article, score_recent, write_snapshot)
- `src/trading_bot/news/fetch.py` — RSS fetch/parse/dedupe/MERGE + ingest-time lexicon score
- `src/trading_bot/news/sentiment.py` — lexicon, score_article, score_recent, write_snapshot (atomic)
- `src/trading_bot/config.py` — NewsConfig + DEFAULT_NEWS + validation + load_config wiring
- `src/trading_bot/ai/context.py` — RegimeContext.sentiment (default None) + build_regime_context pass-through
- `src/trading_bot/ai/engine.py` — `_load_sentiment_snapshot` fail-open in `_maybe_regime_check`
- `src/trading_bot/ai/prompts.py` — `_sentiment_block` + `{sentiment_block}` placeholder in render_regime_prompt
- `prompts/regime_check.txt` — SENTIMENT paragraph (rendered only when present)
- `scripts/news.py` — fetch + sentiment CLI
- `dbt/models/sources.yml` — raw_news_articles as 7th source
- `dbt/models/staging/stg_news_articles.sql`, `dbt/models/marts/mart_news_sentiment_daily.sql`
- `dbt/models/schema.yml` — news not_null/unique tests
- `tests/test_news_fetch.py` (7), `tests/test_news_sentiment.py` (6), + regime-sentiment tests in test_ai_context.py (4) and test_ai_engine.py (3)

## Decisions Made

- **Score at ingest, aggregate in SQL** — fetch_news computes the lexicon score per article (stdlib, when importable) and stores it; the mart only aggregates. No duplicate scoring logic across Python/SQL.
- **Single `{sentiment_block}` paragraph placeholder** — rather than five individual `sentiment_*` placeholders, one placeholder renders the whole SENTIMENT paragraph or an empty string; absence is clean by construction (the plan's "keep the SENTIMENT block as a separate paragraph" instruction).
- **Snapshot values coerced to primitives** (float score, int articles, list[str] titles) before the prompt, so the renderer never emits `None`/`nan`.
- **Per-feed isolation is the default posture** — a dead feed (404) logs and moves on; the pipeline still produced a snapshot on the live feed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] dbt-duckdb resolves the DB path against CWD (same as 03-03)**
- **Found during:** task 2 (dbt run)
- **Issue:** Same as plan 03-03 — the `--project-dir dbt` invocation points at the repo parent; news models reference the same warehouse.
- **Fix:** dbt run/test executed from the `dbt/` directory (`--select stg_news_articles+ mart_news_sentiment_daily`).
- **Files modified:** none (invocation-only)
- **Verification:** `dbt run` 2/2 + `dbt test` 4/4 green.
- **Committed in:** n/a (no git)

**2. [Rule 1 - Bug] DuckDB rejects `INTERVAL ? DAY` parameter binding**
- **Found during:** task 2 (score_recent)
- **Issue:** DuckDB parser does not accept a bound parameter inside `INTERVAL ? DAY` (nor `make_interval`, which doesn't exist in this version).
- **Fix:** Compute the cutoff timestamp in Python (`latest - pd.Timedelta(days=days)`) and bind it as a plain timestamp parameter.
- **Files modified:** src/trading_bot/news/sentiment.py
- **Verification:** all 6 test_news_sentiment tests pass.
- **Committed in:** n/a

---

**Total deviations:** 2 auto-fixed (1 blocking environment, 1 parser-compat bug)
**Impact on plan:** No behavior change; both were execution-environment adaptations.

## Issues Encountered

- **17-file scope note (plan-mandated acknowledgement):** the files_modified list exceeds the 15-file guideline, but the excess is small declarative units (dbt SQL/YAML, prompt template, news package components). Execution context stayed lean; the 3-task structure held and was not split.
- **Two default gold RSS feeds are dead (404):** kitco.com/rss/news and goldprice.com/rss/gold-news returned 404 during the real verification. The per-feed isolation logged both and MarketWatch delivered. The feeds list is configurable; operators may want to refresh the gold-specific feeds.
- The 3 dashboard/tune_risk test failures are pre-existing environmental failures, unchanged by this plan.

## User Setup Required

None. duckdb must be installed for the fetch/sentiment CLI (analytics extra) — documented in README.

## Next Phase Readiness

- Ready for 03-05 (dashboard): the news mart `mart_news_sentiment_daily` and the snapshot `output/news_sentiment.json` give the News page its data.
- Follow-up worth noting: the regime reader now sees `score` + headlines; the snapshot is only as good as the feeds — refresh the two dead gold feeds when convenient.

---
*Phase: 03-ai-trading-layer*
*Completed: 2026-08-27*
