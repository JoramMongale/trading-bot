# Trading Bot Dashboard (plan 03-05)

A read-only Next.js + Tailwind window on the trading system, rendering the
DuckDB marts (03-03/03-04) via the official `@duckdb/node-api`.

**Read-only guarantee (DASH-02):** the DuckDB instance is opened with
`access_mode = 'read_only'`, there are GET-only API routes (no POST/PUT/DELETE
anywhere), no broker/order code is imported, and the app binds loopback only
(127.0.0.1). Risk editing stays in `scripts/tune_risk.py`'s warned CLI — never
here.

## Prerequisites

1. Load the analytics warehouse (the database the dashboard reads):

   ```bash
   python scripts/warehouse_cli.py load     # ingest output/ + data/processed/
   cd dbt && dbt run && dbt test            # build the marts
   cd ..
   ```

2. Install the web app:

   ```bash
   cd web
   npm install
   ```

## Run

```bash
# Production (requires `npm run build` first)
npm run build
cd web && npm run start -- -H 127.0.0.1 -p 3000

# Development (hot reload, also loopback-only by default)
cd web && npm run dev
```

Or use the wrapper scripts:

```bash
scripts/web_dashboard.sh start      # POSIX
scripts/web_dashboard.sh stop
powershell -File scripts/web_dashboard.ps1 start   # Windows
powershell -File scripts/web_dashboard.ps1 stop
```

Open http://127.0.0.1:3000. If the warehouse is missing or the marts are not
loaded, every page shows a friendly "Warehouse not loaded" state instead of
crashing. `/api/news` returns 200 + `[]` (not an error) when the news mart
hasn't been built yet — run `python scripts/news.py fetch` +
`python scripts/news.py sentiment` + `dbt run --select stg_news_articles+ mart_news_sentiment_daily`
to populate it.

## Configuration

- `DUCKDB_PATH` env var overrides the warehouse path (default
  `../data/analytics/trading.duckdb` relative to `web/`). See `.env.local.example`.

## Pages

| Route | Reads from |
|-------|-----------|
| `/` | `mart_bot_health` + `mart_trade_ledger` (open positions) + `mart_ai_gate_activity` |
| `/ledger` | `mart_trade_ledger` |
| `/ai` | `mart_ai_gate_activity` + `mart_ai_gate_performance` |
| `/risk` | `config/config-cent.toml` + `config/config-btc.toml` `[risk]`/`[live]` tables (read-only TOML parse) |
| `/news` | `mart_news_sentiment_daily` |

## Security notes

- Loopback-bound: exposing it would reach the same data surface as the machine
  user (T-04-05-02) — do not publish it.
- No credentials live in the web app: `DUCKDB_PATH` is the only env var.
- All SQL is parameterized; the `?limit=` value is coerced to a bounded
  integer (T-04-05-03).
