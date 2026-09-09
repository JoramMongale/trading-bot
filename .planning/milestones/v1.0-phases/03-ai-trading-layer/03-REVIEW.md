---
phase: 03-ai-trading-layer
reviewed: 2026-08-28T00:00:00Z
depth: standard
files_reviewed: 41
files_reviewed_list:
  - src/trading_bot/ai/schema.py
  - src/trading_bot/ai/base.py
  - src/trading_bot/ai/mock.py
  - src/trading_bot/ai/deepseek.py
  - src/trading_bot/ai/context.py
  - src/trading_bot/ai/prompts.py
  - src/trading_bot/ai/gate.py
  - src/trading_bot/ai/engine.py
  - src/trading_bot/ai/backtest.py
  - src/trading_bot/ai/__init__.py
  - src/trading_bot/news/fetch.py
  - src/trading_bot/news/sentiment.py
  - src/trading_bot/news/__init__.py
  - src/trading_bot/config.py
  - src/trading_bot/backtest/engine.py
  - src/trading_bot/live/engine.py
  - warehouse/load.py
  - scripts/warehouse_cli.py
  - scripts/news.py
  - web/app/layout.tsx
  - web/app/page.tsx
  - web/app/ledger/page.tsx
  - web/app/ai/page.tsx
  - web/app/risk/page.tsx
  - web/app/news/page.tsx
  - web/app/api/status/route.ts
  - web/app/api/ledger/route.ts
  - web/app/api/ai-gate/route.ts
  - web/app/api/news/route.ts
  - web/app/api/risk/route.ts
  - web/components/StatCard.tsx
  - web/components/DataTable.tsx
  - web/components/Sparkline.tsx
  - web/components/Badge.tsx
  - web/components/RefreshButton.tsx
  - web/components/WarehouseEmpty.tsx
  - web/lib/duckdb.ts
  - scripts/web_dashboard.ps1
  - scripts/web_dashboard.sh
  - web/next.config.ts
findings:
  critical: 0
  warning: 6
  info: 9
  total: 15
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-08-28
**Depth:** standard
**Files Reviewed:** 41
**Status:** issues_found

## Summary

Reviewed the AI trading layer (DeepSeek advisor + deterministic gate), the news/sentiment pipeline, the DuckDB warehouse loader, and the read-only Next.js dashboard. The core security posture holds up well: no hardcoded secrets were found (the DeepSeek key is read from the environment at call time, never from config and never logged), the dashboard is genuinely read-only (`access_mode='read_only'`, GET-only routes, loopback-only binding, no broker imports anywhere in `web/`), all web SQL is static or parameterized (`duckdb.ts` `query()` + `$1` in the ledger route), the RSS parser is entity-safe with a 2 MB body cap, and the sentiment snapshot uses a correct temp-file + `os.replace` atomic write.

The findings concentrate in four areas: (1) the DeepSeek client leaks non-`AIClientError` exceptions (a JSON decode failure on a 200 response escapes the fail-closed contract and hard-crashes `ai-backtest`); (2) the warehouse loader builds `MERGE` SQL from dataframe column names, contradicting its own "no SQL is ever built from file content" threat-model claim; (3) the AI backtest's regime block only suppresses the *first* setup of a choppy day, so later setups are still consulted and can be traded — the live engine blocks the whole day; and (4) the dashboard start/stop scripts kill only the wrapper process, orphaning the Next.js server. Six warnings, nine info items. No critical findings.

## Warnings

### WR-01: DeepSeek transport layer leaks `JSONDecodeError` — breaks the fail-closed contract, hard-crashes `ai-backtest`

**File:** `src/trading_bot/ai/deepseek.py:52` (and `:97-107`)
**Issue:** `_post_json` calls `json.loads(resp.read().decode("utf-8"))` with no guard. A 200 response whose body is not JSON (proxy HTML error page, truncated reply, load balancer page) raises `json.JSONDecodeError` (a `ValueError`), which is **not** caught by the `except (urllib.error.HTTPError, ...)` / `except (urllib.error.URLError, OSError)` clauses in `_chat`. The exception then propagates through `propose_trade`/`assess_regime` to every caller. Both callers catch only `(AIClientError, AIResponseError)`:
- `ai/engine.py:87-96` — the exception escapes `_ai_gate`, so the whole `poll_once` aborts instead of emitting the documented `order_skipped reason=ai_unavailable`. The CLI's broad `except Exception` (cli.py:428) converts this into a `poll_error` line, so a garbage model response silently skips *everything* in that poll (including the regime check) instead of failing closed on just the setup.
- `ai/backtest.py:156-163` — no broad catch anywhere in `run_ai_backtest`, so a single non-JSON reply aborts the entire `ai-backtest` run with a raw traceback.

This is exactly the "model returns garbage" case the plan says must fail cleanly and deterministically. Fix: wrap the `json.loads` in `_post_json` (or catch `ValueError` in `_chat`) and re-raise as `AIClientUnavailableError`.

**Fix:**
```python
def _post_json(url, headers, payload, timeout):
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        body = resp.read()
    try:
        return json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AIClientUnavailableError(f"DeepSeek returned a non-JSON body: {exc}") from exc
```

### WR-02: Warehouse loader builds SQL from dataframe column names — contradicts the documented threat model

**File:** `warehouse/load.py:353-368`
**Issue:** `_upsert` derives the `MERGE` column lists from `cols = list(df.columns)` and interpolates them into the SQL string (`f"{c} = __src.{c}"`, `f"INSERT ({inserts})"`). The dataframe columns come straight from file content — `_ingest_trades` and `_ingest_ledger` pass `pd.read_csv(path)` frames whose headers are whatever the CSV files contain, and `_ingest_bars` passes columns renamed from the CSV (`df.rename(columns=str.lower)`). A corrupted or hostile `output/trades.csv` header (e.g. a column name containing `) VALUES (...` or a backtick-quoted identifier with a semicolon) injects arbitrary SQL into the analytics DuckDB. This directly contradicts the module docstring's claim: "no SQL is ever built from file content — table/column names are fixed literals and all values flow through DuckDB's typed parameters (threat T-04-03-01/02)." The claim is false for column names. Fix: intersect `df.columns` with a fixed allowlist of expected columns per table before building the statement (and fail/`[skip]` on unknown columns).

**Fix:**
```python
# per-table fixed column list; drop any column not in it
_ALLOWED = {
    "raw_trades": {"source", "entry_time", "entry", "sl", "tp", "exit_time",
                   "exit_price", "exit_reason", "pnl_points", "r_multiple", "loaded_at"},
    # ... same for the other five tables
}

def _upsert(con, table, df, key_cols):
    allowed = _ALLOWED[table]
    df = df[[c for c in df.columns if c in allowed]]
    cols = list(df.columns)
    ...
```

### WR-03: AI backtest regime block only vetoes the FIRST setup of a choppy day

**File:** `src/trading_bot/ai/backtest.py:124-151`
**Issue:** The "return `ai_regime_block`" sits *inside* the `if cfg.ai.regime_check_daily and state["day"] != today:` branch, so it fires only on the first setup of each day. Every later setup that day skips the regime check entirely and proceeds to the proposal gate — where a model approval is **traded**, even though the day was declared CHOPPY/untradeable and `block_when_choppy` is set. The live `AIEngine` (engine.py:199-204) checks `_regime_blocked()` for *every* setup via `_ai_gate`, so the backtest misrepresents the live policy exactly in the scenario (regime-blocked days) this plan exists to measure — the raw-vs-gated comparison in `ai-backtest` output is wrong on choppy days, and `state["regime_blocks"]` undercounts (1/day regardless of how many setups were suppressed). It also burns a model consultation per setup on days that should be suppressed. Fix: hoist the blocked check out of the `state["day"] != today` branch.

**Fix:**
```python
if cfg.ai.regime_check_daily and state["day"] != today:
    state["day"] = today
    state["regime_checks"] += 1
    ... assess regime ...
if (
    cfg.ai.block_when_choppy
    and state["regime"] is not None
    and (state["regime"].is_choppy or not state["regime"].tradeable)
):
    state["regime_blocks"] += 1
    return "ai_regime_block"
```

### WR-04: Lexicon scorer uses raw substring counting — "up"/"down" fire inside unrelated words

**File:** `src/trading_bot/news/sentiment.py:61-63` (lexicon `:27,40`)
**Issue:** `lower.count(term)` counts substring occurrences, and the lexicon contains single words `"up"` and `"down"`. Every headline containing "update", "support", "supply" (…"up"…), "downgrade", "downtrend", "downgraded" gets a spurious bullish/bearish hit. "Support for gold" is bullish on this scorer's own lexicon — but the scorer also fires "up" inside "support", double-counting it. Since the score is persisted per article and rolled into the daily snapshot that feeds the AI regime prompt, this systematically biases the sentiment input. Fix: word-boundary matching (regex `\bup\b`/`\bdown\b`, or tokenize and match tokens/phrases), and drop bare "up"/"down" from the lexicon or require phrase forms ("moving up", "heading down").

**Fix:**
```python
import re
def _term_count(lower_text: str, term: str) -> int:
    # words and phrases both; phrase counts via the same regex
    return len(re.findall(rf"(?<![a-z]){re.escape(term)}(?![a-z])", lower_text))
```

### WR-05: Dashboard start/stop scripts orphan the Next.js server process

**File:** `scripts/web_dashboard.ps1:34-40,48-51` and `scripts/web_dashboard.sh:30,42`
**Issue:** `Start-Process cmd.exe ... npm run start` records the PID of the `cmd.exe`/`npm` wrapper; `Stop-Process -Id` / `kill "$pid"` kills only that wrapper. On Windows, killing `cmd.exe` does not terminate the `node` child running `next start`; in the shell script, `npm` spawns node as a child and `kill` on the npm process can orphan it. The orphaned server keeps port 3000 bound, so a subsequent `start` either fails or (via the stale-pidfile check) reports "not running" while the old server still serves — and `stop` then cannot find the real server. Secondary: `start` never verifies `.next` exists (a missing production build makes `next start` fail inside the hidden window; in the PS1 version the missing `.next` directory also makes `-RedirectStandardOutput` throw before the process even starts, and `$ErrorActionPreference = "Stop"` turns it into an unhelpful error). Fix: kill the whole tree (Windows: `taskkill /PID $pid /T /F`; bash: `pkill -P` descendants, or record the node PID by launching `next start` directly and using `kill -- -PGID`), and fail fast with a clear message when `.next/BUILD_ID` is absent.

**Fix (PowerShell):**
```powershell
Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
# kill any surviving child tree that holds the port
taskkill /PID $pidToKill /T /F 2>$null
```
and before starting: `if (-not (Test-Path (Join-Path $Web ".next\BUILD_ID"))) { Write-Error "No production build — run 'npm run build' in web/ first"; exit 1 }`

### WR-06: `_ingest_bars` is not defensive despite the "skip, never raise" contract

**File:** `warehouse/load.py:304-325`
**Issue:** The `try/except` covers only `pd.read_csv`; the coercion steps that follow are outside it. `df[keep].astype(float)` raises `ValueError` on any non-numeric cell, `df.reset_index()` + the `_upsert` TIMESTAMP cast raise on a non-datetime index, so a single malformed `data/processed/*.csv` aborts the **entire** `load()` run and the CLI prints a raw traceback (`warehouse_cli.py` only handles `ImportError`). The module docstring promises "unparseable lines are skipped, never raised." Fix: move the whole per-file body (parse, coerce, upsert) inside the `try`, and also wrap the histdata branch identically.

**Fix:**
```python
for path in processed:
    try:
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        if df.empty:
            continue
        df = df.rename(columns=str.lower)
        keep = [c for c in ("open", "high", "low", "close") if c in df.columns]
        if not keep:
            continue
        df = df[keep].astype(float)
        ...upsert...
    except Exception as exc:  # noqa: BLE001
        print(f"  [skip] {path.name}: unreadable ({exc})")
        continue
```

## Info

### IN-01: NaN values render as literal `nan` in prompts despite the stated design rule

**File:** `src/trading_bot/ai/prompts.py:128,180`; `src/trading_bot/ai/context.py:101-106`
**Issue:** `context.py` goes to lengths to convert `NaN` to `None` for the regime context ("None renders as unknown; NaN would render as 'nan', which a model may read as a number"), but `TradeContext.change_pct`/`reward_risk`/`atr_estimate` can still be `NaN` (`len(df) < n_bars`, zero close, `stop_distance <= 0`), and `render_trade_prompt` formats them with `:.2f` → `"nan"` in the model's input. Same for `price_change_pct` in the regime prompt. Apply the same `"unknown"` guard the regime renderer uses.

### IN-02: `web/app/page.tsx` redefines `WarehouseEmpty` instead of importing it

**File:** `web/app/page.tsx:240-252`
**Issue:** The overview page defines a local `function WarehouseEmpty()` that duplicates `web/components/WarehouseEmpty.tsx` (used by the ledger/AI/news pages). Delete the local copy and import the component, or the two drift.

### IN-03: TOML parser duplicated between the risk page and the risk API route

**File:** `web/app/risk/page.tsx:14-36` and `web/app/api/risk/route.ts:17-40`
**Issue:** `parseToml`/`parseRiskToml` are near-identical copies. Extract one parser into `web/lib/toml.ts` and share it. Note both also leave array values (e.g. `session_hours = [8, 21]`) as raw strings and do not unescape `\"` in quoted values — acceptable for display, but worth centralizing if fixed.

### IN-04: `duckdb.ts` caches a permanently-rejected singleton promise

**File:** `web/lib/duckdb.ts:29-34`
**Issue:** `_instance` stores the promise returned by `DuckDBInstance.create`. If the first `create` rejects (file locked, transient error), `_instance` stays rejected forever, so every subsequent `query`/`isWarehouseReady` fails permanently until the process restarts — even after the cause is fixed. Reset `_instance = null` on rejection so the next call retries.

### IN-05: Link-dedupe normalization mismatch between Python and SQL inflates `new` count

**File:** `src/trading_bot/news/fetch.py:93-95` vs `:179-185`
**Issue:** `_normalize_link` does `strip().lower().rstrip("/")` (strips whitespace), but the SQL `lower(rtrim(link, '/'))` does not strip whitespace. A stored link with leading/trailing whitespace is counted as "new" on every re-fetch even though `MERGE` treats it as a match. Align the SQL to the Python normalization.

### IN-06: Histdata symbol retains the `DAT_ASCII_` prefix

**File:** `warehouse/load.py:164-179`
**Issue:** For `DAT_ASCII_XAUUSD_M1_202102.csv`, `_symbol_timeframe_from_name` yields symbol `"DAT_ASCII_XAUUSD"` instead of `"XAUUSD"` (the regex splits on `_M1_` but does not strip the vendor prefix). `raw_bars.symbol` is then inconsistent between histdata and processed files. Strip the `DAT_ASCII_` prefix (or take the segment before the timeframe token).

### IN-07: `evaluate_proposal` accepts an unused `tp` parameter

**File:** `src/trading_bot/ai/gate.py:41-50`
**Issue:** `tp` is threaded through the signature and both call sites but never read. Either use it (e.g., reject a proposal whose invalidation sits beyond the target, which would be a defensible tightening) or drop it to keep the gate's contract honest.

### IN-08: First setup of the day is gated against stale/absent regime

**File:** `src/trading_bot/ai/engine.py:52-56,141-144`
**Issue:** `poll_once` runs `super().poll_once()` (which can invoke `_ai_gate`) before `_maybe_regime_check()`, and `_regime_day` is stamped *before* the model call. On a fresh process start, the first setup of the day is therefore gated against `self._regime = None` (regime gate silently off for that setup); after a failed regime call, the gate stays off all day. Consistent with the documented fail-open policy for the regime filter, but worth a comment or a reorder (run the regime check before `super().poll_once()` when a new day is detected).

### IN-09: `write_snapshot`/`score_recent` crash with a traceback when the DB or table is absent

**File:** `src/trading_bot/news/sentiment.py:121-136`; `scripts/news.py:62-70`
**Issue:** `duckdb.connect(..., read_only=True)` on a missing file, and the `raw_news_articles` CatalogError when `fetch` was never run, both raise exceptions the CLI does not catch (it handles only `ImportError`). A user running `python scripts/news.py sentiment` before `fetch` gets a raw traceback instead of the friendly "no articles" path. Catch the duckdb errors in `write_snapshot` and return `None` (the caller already prints the "no articles to score" message), or catch them in the CLI.

---

_Reviewed: 2026-08-28_
_Reviewer: OpenCode (gsd-code-reviewer)_
_Depth: standard_
