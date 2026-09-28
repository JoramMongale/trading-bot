---
phase: 20260928-btc-fear-greed-direction-filter
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/trading_bot/news/fear_greed.py
  - src/trading_bot/backtest/engine.py
  - tests/test_fear_greed.py
  - tests/test_engine_sentiment.py
  - scripts/backtest_btc_fng.py
  - scripts/falsify_btc_fng.py
  - .planning/quick/20260928-btc-fear-greed-direction-filter/SUMMARY.md
autonomous: true
user_setup: []

must_haves:
  truths:
    - "A keyless, stdlib-only Crypto Fear & Greed Index fetcher (urllib + json, NO RSS/lexicon pipeline) produces a daily 0-100 value series, cached locally to a JSON file so the backtest is reproducible offline and hits the network at most once; a map_to_bars step applies the no-lookahead rule (daily.shift(1) then forward-fill onto M5 bars) so a bar only ever sees sentiment known at bar time"
    - "run_backtest accepts an OPTIONAL aligned sentiment Series plus a neutral-band half-width; sentiment=None (default) is byte-identical to today (existing 540-test suite stays green with ZERO edits to golden pins), and the gate is direction-aware: bullish (value >= 50+band) permits only longs, bearish (value <= 50-band) permits only shorts, neutral permits both"
    - "A pre-registered BTC grid runs on data/processed/BTCUSDc_M5_broker.csv (~100k broker-native BTCUSDc M5 bars) through the REAL shared engine: long/short/both rr=1.0 baselines (no filter) plus N=5 both-direction sentiment-gated configs sweeping the neutral band {5,10,15,20,25}"
    - "The falsification battery reports coverage/stall, 70/30 train/test, monthly R (front-loading), and best-of-N noise calibration with the N=39 self-check ~2.37, and states plainly whether the sentiment filter improves BTC's measured negative edge (avg R -0.043, t=-1.20 from STATE.md)"
    - "Nothing live or demo is touched: live/engine.py, config-btc.toml, config-cent.toml, every MT5 path and the running bots are unchanged; results are for user review only"
  artifacts:
    - path: "src/trading_bot/news/fear_greed.py"
      provides: "stdlib F&G fetcher + local cache + no-lookahead map_to_bars (mirrors news/fetch.py's urllib pattern, but for the alternative.me API)"
      contains: "alternative.me"
    - path: "src/trading_bot/backtest/engine.py"
      provides: "additive sentiment direction-gate seam (sentiment Series + sentiment_band); sentiment=None default byte-identical"
      contains: "sentiment"
    - path: "tests/test_fear_greed.py"
      provides: "offline fetcher/parse/cache/map tests (monkeypatched urlopen)"
    - path: "tests/test_engine_sentiment.py"
      provides: "engine gate semantics: byte-identity default, bullish/bearish/neutral/NaN masking, single-direction masking, length-mismatch raises"
    - path: "scripts/backtest_btc_fng.py"
      provides: "pre-registered BTC grid driver (baselines + threshold sweep) over BTCUSDc_M5_broker.csv"
    - path: "scripts/falsify_btc_fng.py"
      provides: "falsification battery: coverage, 70/30 train/test, monthly R, best-of-N noise calibration"
    - path: ".planning/quick/20260928-btc-fear-greed-direction-filter/SUMMARY.md"
      provides: "measured tables + honest verdict for user review"
  key_links:
    - from: "src/trading_bot/news/fear_greed.py"
      to: "src/trading_bot/backtest/engine.py"
      via: "driver passes map_to_bars(daily, df.index) as the sentiment= Series; engine masks df['setup'] after setups are built"
    - from: "scripts/backtest_btc_fng.py"
      to: "src/trading_bot/backtest/engine.py"
      via: "run_backtest(m5, direction='both', rr_multiple=1.0, sentiment=..., sentiment_band=...)"
    - from: "src/trading_bot/news/fear_greed.py"
      to: "data/processed/fear_greed.json"
      via: "load_fear_greed writes the fetched daily series once, reads it on every later run"
    - from: "scripts/falsify_btc_fng.py"
      to: "data/processed/BTCUSDc_M5_broker.csv"
      via: "loads the same ~100k broker-native bars the driver measures"
---

<objective>
Measure whether a Crypto Fear & Greed Index sentiment DIRECTION filter improves Bitcoin's measured negative both-direction edge, BACKTEST-FIRST, through the REAL shared engine. Backtest only.

Purpose: BTC's both-direction single-slot book measures negative (STATE.md: avg R -0.043, t=-1.20, PF 0.87, 660 closed trades; the scalper cross-check pinned long -0.0418/t=-0.84, short -0.0055/t=-0.12, both -0.0612/t=-1.25). This task tests ONE new hypothesis — that gating the both book by daily crypto sentiment ("trade with sentiment": bullish → long-only, bearish → short-only, neutral → both) moves the edge toward positive — before ANY live/demo change. The user's three locked decisions are non-negotiable: (1) sentiment source is the keyless alternative.me Fear & Greed API, NOT the existing RSS/lexicon pipeline; (2) the gate is a direction filter, not a signal override; (3) validation order is backtest-first, and live/demo wiring is explicitly OUT OF SCOPE.

Decision rationale (planner's call): the gate is an ENGINE seam, not a standalone research driver. `run_backtest` already supports `direction="both"` with a per-bar `setup_dir` column ("long"/"short") and per-trade `direction`; the single-slot fill/slot mechanics are the only honest place to measure how a direction filter changes the book (the candle-reversal task proved measuring slot mechanics outside the engine produces starved-sample artifacts). The change is purely additive — `sentiment=None` (default) stays byte-identical, pinned by the existing 540-test suite with zero edits to golden pins — and `live/engine.py` never calls `run_backtest`, so it is untouched by construction.

Sentiment semantics (locked decision 2, "trade with sentiment"): the F&G index is 0 = extreme fear, 100 = extreme greed. "Bullish" = high value (greed) → LONG only; "bearish" = low value (fear) → SHORT only; neutral = within a band around 50 → both. This is momentum-with-sentiment (NOT contrarian), implemented exactly as the user specified.

No-lookahead rule (hard constraint): a F&G value for day D is only known from day D+1 onward. The daily series is shifted by one day (`daily.shift(1)`) before being forward-filled onto the M5 index, so an M5 bar at time T sees only the most recent COMPLETED daily value. This is the same `shift(1)` + `reindex(method="ffill")` rule `strategy.filters.htf_trend` already uses, and lives in the well-named `map_to_bars` (caller side), NOT in the engine — the engine just applies the gate given an already-correct aligned Series.

Grid N is PRE-REGISTERED (no post-hoc winner-counting): 3 control rows (long/short/both rr=1.0, no filter) + N=5 sentiment-gated both-direction configs (neutral band sweep {5,10,15,20,25}). The 3 controls are the measured anchors the gated rows must BEAT; the 5 gated rows are the search whose best |t| is judged against best-of-5 noise.

Output: a stdlib F&G fetcher + tests; an additive engine sentiment-gate seam + tests; a reproducible grid driver; a falsification battery; a SUMMARY.md with measured tables and an honest verdict for user review.

Git: repo is local; identity already set. Commit atomically per task, only that task's files.
</objective>

<execution_context>
@$HOME/.config/opencode/get-shit-done/workflows/execute-plan.md
@$HOME/.config/opencode/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@AGENTS.md
@config/config-btc.toml
@config/config-cent.toml
@src/trading_bot/backtest/engine.py
@src/trading_bot/strategy/signals.py
@src/trading_bot/strategy/filters.py
@src/trading_bot/news/fetch.py
@src/trading_bot/news/sentiment.py
@src/trading_bot/config.py
@tests/test_engine_both.py
@tests/test_news_fetch.py
@scripts/backtest_both_scalper.py
@scripts/falsify_both_scalper.py
@.planning/quick/20260909-gold-both-scalper/SUMMARY.md

Data (real broker-native BTCUSDc cent bars — the instrument config-btc.toml actually trades):
@data/processed/BTCUSDc_M5_broker.csv   (~100,000 bars, 2025-09-13 -> 2026-08-27, columns time,open,high,low,close)

Python on this Windows box: `.venv\Scripts\python.exe` (pytest 9.1.1 present; pyproject sets pythonpath=["src"]). Run scripts and pytest with that interpreter.

Prior-art reference numbers to sanity-check the printed tables against (do NOT editorialise — print what is measured):
- BTC baseline (STATE.md 2026-08-27): avg R -0.043, t=-1.20, PF 0.87, win 52.4%, 660 closed trades, max DD $785; rr=2.0 worse (-0.103R). BTC is a known losing machinery test.
- Scalper BTC cross-check (20260909-gold-both-scalper): long rr1.0 n=348 R-0.0418/t-0.84, short rr1.0 n=410 R-0.0055/t-0.12, both rr1.0 n=356 R-0.0612/t-1.25, both rr0.5 n=717 R+0.0172/t+0.76.
- STATE.md noise calibration: best |t| among 39 tries = 2.37 at the median; all-time best |t|=2.46 is beaten by noise 42% of the time. best-of-N helper is pinned by the N=39 ≈ 2.37 self-check.

<interfaces>
Engine contract (src/trading_bot/backtest/engine.py) — what the driver calls, plus THIS task's seam:
```python
run_backtest(
    df,                      # OHLC DataFrame, datetime index named "time"
    fractal_left=2, fractal_right=2, sr_lookback=60, sl_buffer=0.01,
    rr_multiple=1.0, session_hours=None, max_hold_bars=None, tp_from_fill=False,
    direction="long",        # "long" (default) | "short" | "both"
    atr_median_bars=None, atr_period=14, htf_sma=None, htf_rule="1h", require_body=False,
    max_concurrent=1,
    on_event=None, setup_veto=None, variant="breakout", setup_override=None,
    sentiment=None,          # <-- THIS task: Optional[pd.Series] aligned to df.index (0-100)
    sentiment_band=10.0,     # <-- half-width around 50; bullish >= 50+band, bearish <= 50-band
) -> list[dict]
```
Each returned trade record: entry_time, entry, sl, tp, exit_time, exit_price, exit_reason ("SL"|"TP"|"TIME"|"OPEN"), entry_idx, exit_idx, direction.
For a `direction="both"` run, `df["setup_dir"]` ("long"/"short"/"") is built in pass A; the sentiment gate is applied AFTER setups are built (alongside the existing optional filters), never mutating the level frame.

Fear & Greed API (https://api.alternative.me/fng/?limit=0&format=json) — keyless, `limit=0` returns the full daily history, most-recent-first:
```json
{ "name": "Fear and Greed Index",
  "data": [ { "value": "72", "value_classification": "greed", "timestamp": "1724860800", "time_until_update": "12345" }, ... ],
  "metadata": {...} }
```
`value` is a STRING int 0-100; `timestamp` is a STRING unix-seconds (UTC midnight of the day it describes). Parse + sort ascending + dedupe on the normalized date index.

Engine note: `engine.py` currently has NO `import pandas as pd` (its only `pd` references are lazy `from __future__ import annotations` type hints). The sentiment gate needs `import pandas as pd` added (already a project dependency).

Driver pattern (scripts/backtest_both_scalper.py): `sys.path.insert(0, str(ROOT/"src"))`; `load_m5` reads the CSV with parse_dates=["time"], .set_index("time"), slices [["open","high","low","close"]]; `tstat`/`summarize`/`summarize_leg`/`_r` helpers at the bottom are copied by convention. `from trading_bot.news.fear_greed import load_fear_greed, map_to_bars` provides the sentiment input.
</interfaces>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: stdlib F&G fetcher + additive sentiment direction-gate seam in run_backtest + tests</name>
  <files>src/trading_bot/news/fear_greed.py</files>
  <files>src/trading_bot/backtest/engine.py</files>
  <files>tests/test_fear_greed.py</files>
  <files>tests/test_engine_sentiment.py</files>
  <behavior>
    - Fetcher: a keyless GET of the F&G URL parses {"data":[{value(str), timestamp(str), ...}]} into an ASCENDING daily pd.Series (DatetimeIndex = UTC midnight, float values 0-100), dropping duplicate dates (keep last).
    - Cache: load_fear_greed fetches on first call and writes JSON; a second call reads the cache with ZERO network; refresh=True refetches. Unlike the RSS pipeline's fail-open, a fetch failure with no cache RAISES (the F&G series is a backtest INPUT, not a convenience — a silent miss would corrupt the measurement).
    - No-lookahead: map_to_bars(daily, index) returns daily.shift(1).reindex(index, method="ffill") — a bar on day D sees day D-1's value; a leading NaN (before the first shifted day) stays NaN and is treated as neutral/fail-open by the gate.
    - Engine byte-identity: run_backtest(df) == run_backtest(df, sentiment=None) record-for-record (the seam must not touch the default path).
    - Engine gate: in a direction="both" run, an all-bullish sentiment Series produces ZERO short trades and an all-bearish Series produces ZERO long trades; an all-neutral Series (or all-NaN) produces both sides (fail-open). In a direction="long" run, all-bearish sentiment produces ZERO trades; in direction="short", all-bullish produces ZERO trades.
    - Engine validation: a sentiment Series whose length != len(df) raises ValueError naming the lengths.
  </behavior>
  <action>
    Create `src/trading_bot/news/fear_greed.py` (stdlib only: urllib + json; mirrors news/fetch.py's structure). Module docstring states the trust boundary: the remote JSON is untrusted input, parsed with stdlib json (no code execution), bodies > MAX_BODY_BYTES rejected before parsing, non-200 raised. Contents:
    - `FNG_URL = "https://api.alternative.me/fng/?limit=0&format=json"`, `MAX_BODY_BYTES = 2 * 1024 * 1024`, `USER_AGENT = "trading-bot/0.1 (+personal research)"`.
    - `_http_get_json(url, timeout=15.0) -> dict`: urllib.request.Request with the UA header; urlopen; reject non-200; read(MAX_BODY_BYTES+1), reject oversized; json.loads.
    - `_parse(data: dict) -> pd.Series`: take data["data"], for each entry `float(entry["value"])` keyed by `pd.to_datetime(int(entry["timestamp"]), unit="s", utc=True).normalize()`; build Series, `.sort_index()`, `.drop_duplicates(keep="last")`, name it "fng". Raise ValueError if "data" is missing/empty (loud, not silent).
    - `fetch_fear_greed(url=FNG_URL, timeout=15.0) -> pd.Series`: `_parse(_http_get_json(url, timeout))`.
    - `load_fear_greed(cache_path="data/processed/fear_greed.json", url=FNG_URL, timeout=15.0, refresh=False) -> pd.Series`: if the cache exists and not refresh, load the cached raw list (json) and `_parse` it; else fetch, write the raw `data` list to cache (json.dump; `Path(cache_path).parent.mkdir(parents=True, exist_ok=True)`), and return the parsed Series. Network is hit only on a cache miss or refresh.
    - `map_to_bars(daily: pd.Series, index: pd.Index) -> pd.Series`: `return daily.shift(1).reindex(index, method="ffill")` — the no-lookahead rule documented inline.

    Edit `src/trading_bot/backtest/engine.py` ONLY (plus the two new test files). live/engine.py, cli.py, stats.py, config.py, config files and all strategy/news modules are NOT touched.
    - Add `import pandas as pd` after `import math` (line ~26) — currently absent; the gate builds a pd.Series.
    - Signature: add `sentiment: Optional[pd.Series] = None, sentiment_band: float = 10.0` as the last two parameters (after `setup_override=None`).
    - Validation block (after the existing `direction == "both"` guard, ~line 166): add `if sentiment_band < 0: raise ValueError(f"sentiment_band={sentiment_band} must be >= 0")`.
    - Add the gate AFTER the `if require_body:` optional-filter block (~line 209) and BEFORE the session-filter comment (~line 211), so it ANDs with the other masks and never touches the level frame:
      ```python
      # Sentiment direction gate (research seam, quick 20260928-btc-fear-greed):
      # when `sentiment` (a 0-100 Fear & Greed Series aligned to df.index) is
      # provided, mask setups by the value at that bar -- bullish (>= 50+band)
      # permits ONLY longs, bearish (<= 50-band) permits ONLY shorts, and the
      # neutral band permits both. NaN (no information) is fail-open: no mask.
      if sentiment is not None:
          if len(sentiment) != len(df):
              raise ValueError(
                  f"sentiment has {len(sentiment)} entries but the frame has {len(df)} bars")
          vals = pd.Series(sentiment).reindex(df.index)
          bull = vals >= 50.0 + sentiment_band
          bear = vals <= 50.0 - sentiment_band
          if direction == "both":
              side = df["setup_dir"]
          else:
              side = pd.Series(direction, index=df.index)
          is_long = side.eq("long")
          is_short = side.eq("short")
          allow = (is_long & ~bear) | (is_short & ~bull)
          df["setup"] = df["setup"] & allow.astype(bool)
      ```
      (NaN comparisons yield False, so a NaN bar is `~bull & ~bear` = both allowed = neutral/fail-open, matching the project's news fail-open convention.)
    - Docstring: add a paragraph documenting `sentiment` + `sentiment_band` (the seam is backtest-only, never wired into live; the direction-aware mask; the fail-open NaN rule; the caller must pass a no-lookahead-shifted, index-aligned Series — the map_to_bars helper in news/fear_greed.py does that). Note the gate applies to "long"/"short"/"both" alike.

    Tests — create the two new files (do NOT modify any existing test file; the 540-test suite is the byte-identity proof):
    - `tests/test_fear_greed.py` (mirror tests/test_news_fetch.py's monkeypatch-urlopen pattern): a fixture JSON string with 2-3 entries (values as STRINGS, timestamps as unix-seconds strings, deliberately reverse-chronological); patch `fear_greed.urllib.request.urlopen` with a _FakeResp-like object returning the JSON bytes. Tests: (1) `_parse` returns an ascending daily Series with float values and normalized UTC midnight index; (2) `load_fear_greed` writes the cache on first call and a second call reads it without calling urlopen (assert a call counter does not increment), `refresh=True` refetches; (3) `map_to_bars` shift(1) no-lookahead: a synthetic daily Series where the M5 index's day D falls on a known day, asserting the bar sees day D-1's value and that the leading bar is NaN; (4) fetch failure with no cache raises (HTTPError propagates as an exception, not a silent empty Series).
    - `tests/test_engine_sentiment.py` (mirror tests/test_engine_both.py's `_frame`/`_random_walk` builders; import them locally, do NOT import across test files): reuse a `_random_walk(n=12000, seed=7)` builder and a helper `_sent(series_or_scalar)` that broadcasts a constant float to `pd.Series(v, index=df.index)`. Tests: (1) byte-identity — `run_backtest(df) == run_backtest(df, sentiment=None)` record-for-record; (2) all-bullish (value 90) on direction="both" → every trade direction == "long" (n>0) and no "short"; (3) all-bearish (value 10) on direction="both" → every trade "short" (n>0) and no "long"; (4) neutral (value 50) on direction="both" → contains both "long" and "short"; (5) all-NaN sentiment on direction="both" → same trade count as sentiment=None (fail-open = no mask); (6) direction="long" + all-bearish → zero trades; direction="short" + all-bullish → zero trades; (7) length-mismatch raises ValueError with "sentiment" in the message.

    Commit: `git add src/trading_bot/news/fear_greed.py src/trading_bot/backtest/engine.py tests/test_fear_greed.py tests/test_engine_sentiment.py` then commit `feat(engine): additive F&G sentiment direction gate + stdlib fetcher (backtest measurement)`.
  </action>
  <verify>
    <automated>.venv\Scripts\python.exe -m pytest tests/test_fear_greed.py tests/test_engine_sentiment.py tests/test_engine_both.py tests/test_backtest.py tests/test_short_and_filters.py -q</automated>
  </verify>
  <done>
    fear_greed.py fetches/parses/caches the keyless F&G series and maps it onto M5 bars with shift(1) no-lookahead; run_backtest accepts sentiment + sentiment_band with sentiment=None byte-identical (existing tests green, none modified); the gate masks long setups when bearish, short setups when bullish, permits both when neutral/NaN; new test files green; committed.
  </done>
</task>

<task type="auto">
  <name>Task 2: measurement driver — pre-registered BTC grid (baselines + threshold sweep) on BTCUSDc_M5_broker.csv</name>
  <files>scripts/backtest_btc_fng.py</files>
  <action>
    Create `scripts/backtest_btc_fng.py` (committed, reusable), modelled on `scripts/backtest_both_scalper.py`:
    - Header docstring: measure whether a F&G sentiment direction filter improves BTC's both-direction edge, through the REAL shared engine (run_backtest). Research only; nothing here is a live candidate and live/engine.py is untouched.
    - `ROOT = Path(__file__).resolve().parent.parent`; `sys.path.insert(0, str(ROOT / "src"))`.
    - `load_m5(csv)` identical to the scalper driver: `pd.read_csv(csv, parse_dates=["time"]).set_index("time")[["open","high","low","close"]]`.
    - Imports: `from trading_bot.backtest.engine import run_backtest`; `from trading_bot.news.fear_greed import load_fear_greed, map_to_bars`.
    - Copy the `tstat`, `_r`, `summarize`, `summarize_leg` helpers VERBATIM from scripts/backtest_both_scalper.py (they are the project convention; `_r` is sign-corrected per record direction).
    - A `run_config(df, direction, rr=1.0, sentiment=None, band=10.0)` helper that calls `run_backtest(df, direction=direction, rr_multiple=rr, sentiment=sentiment, sentiment_band=band)`. Engine defaults (fractal 2/2, sr_lookback 60, sl_buffer 0.01, max_concurrent 1) are left at default.
    - Load sentiment once: `daily = load_fear_greed(cache_path=ROOT / "data/processed/fear_greed.json")`; `sent = map_to_bars(daily, df.index)`. Print the daily series span (first/last date, n days) as a context line so the run is reproducible from the output alone.
    - THE PRE-REGISTERED BTC GRID (data/processed/BTCUSDc_M5_broker.csv). Print rows in exactly this order with exactly these labels:
      Controls (no filter — the anchors the gated rows must BEAT; expected to reproduce the scalper cross-check numbers):
        1. `long   rr1.0 (no fng) `  → direction="long",  rr=1.0, sentiment=None
        2. `short  rr1.0 (no fng) `  → direction="short", rr=1.0, sentiment=None
        3. `both   rr1.0 (no fng) `  → direction="both",  rr=1.0, sentiment=None
      Sentiment-gated both-direction (N=5 — the neutral-band threshold sweep whose best |t| the noise bar judges):
        4. `both   rr1.0 fng b5   `  → both, rr=1.0, sentiment=sent, band=5.0
        5. `both   rr1.0 fng b10  `  → both, rr=1.0, sentiment=sent, band=10.0
        6. `both   rr1.0 fng b15  `  → both, rr=1.0, sentiment=sent, band=15.0
        7. `both   rr1.0 fng b20  `  → both, rr=1.0, sentiment=sent, band=20.0
        8. `both   rr1.0 fng b25  `  → both, rr=1.0, sentiment=sent, band=25.0
    - For the `both rr1.0 (no fng)` row and every gated `both` row, also print a long/short leg decomposition (`summarize_leg`) so the drift asymmetry and the direction-split effect of the gate are visible.
    - Print the run context line first: data file, bar count, first/last bar time, engine params, the F&G series span, and the exact grid definition (labels), so the run is reproducible from the output alone.
    - Exit non-zero with a naming-path message if the BTC CSV is missing.
    - Do NOT write any output CSV/JSON; the printed tables ARE the deliverable (the SUMMARY transcribes them). Do NOT load config files, do NOT import trading_bot.live, do NOT touch MT5. The ONLY network call is load_fear_greed's first-run fetch (cached thereafter).

    Run it: `.venv\Scripts\python.exe scripts/backtest_btc_fng.py` — capture the full printed output verbatim for the SUMMARY.

    Interpretation aid (do NOT print editorialising): expect the BTC controls to reproduce the negative scalper cross-check (~long -0.042, both -0.061); the question is whether ANY gated row moves R materially toward (or past) zero, and whether the gate's direction-split behaves as specified (bullish days → long-heavy, bearish days → short-heavy). Whatever the numbers, report them.
  </action>
  <verify>
    <automated>.venv\Scripts\python.exe scripts/backtest_btc_fng.py</automated>
  </verify>
  <done>
    The pre-registered 8-row BTC grid (3 controls + 5 gated band sweep) + leg decompositions ran on the real ~100k-bar BTCUSDc_M5_broker.csv through run_backtest (gated rows via the sentiment seam, with no-lookahead map_to_bars); output captured verbatim; script committed (`git add scripts/backtest_btc_fng.py` → `feat(scripts): BTC F&G sentiment direction-filter grid driver`).
  </done>
</task>

<task type="auto">
  <name>Task 3: falsification battery (coverage, 70/30, monthly R, best-of-N noise) + honest SUMMARY</name>
  <files>scripts/falsify_btc_fng.py</files>
  <files>.planning/quick/20260928-btc-fear-greed-direction-filter/SUMMARY.md</files>
  <action>
    Create `scripts/falsify_btc_fng.py` (committed), modelled on `scripts/falsify_both_scalper.py` (which imports the driver's helpers: `sys.path.insert` for both src and scripts, `from backtest_btc_fng import load_m5, run_config, summarize, tstat, _r`). Import ONLY the load_m5/run_config/tstat/_r helpers — the battery drives the REAL engine itself. Load sentiment once via `load_fear_greed`/`map_to_bars` exactly as the driver does. Sections, in this order (all on the BTC CSV):

    1. COVERAGE / stall check (the candle-reversal lesson): for `both rr1.0 fng b10` and `both rr1.0 (no fng)`, report n closed, first entry_time, last exit_time, and span% of the frame. Print `STALL` if span < 95% (the gate must not starve the single slot; breakout levels are reachable so expect ~100%).
    2. TRAIN/TEST 70/30: cut = int(len(df)*0.7); run train and test slices for the PRE-REGISTERED configs `both rr1.0 (no fng)`, `both rr1.0 fng b10`, `both rr1.0 fng b15`, `both rr1.0 fng b20`. Print `train R/t` and `TEST R/t` per config. Rule (as in falsify_both_scalper): OOS must be positive with t > 2.0 to count as passing; print pass/fail per row.
    3. MONTHLY R breakdown (front-loading): for `both rr1.0 (no fng)` and `both rr1.0 fng b10`, group CLOSED trades by `str(entry_time)[:7]` and print month | n | R | t (same shape as falsify_both_scalper.run_monthly). BTC spans 2025-09 → 2026-08; a 2026 collapse IS the finding, print it.
    4. BEST-OF-N NOISE CALIBRATION (the STATE.md methodology): the gated grid is N=5 configs. Implement with stdlib only (copy `tail`, `p_noise_best_ge`, `median_best_of_n` VERBATIM from falsify_both_scalper.py). Print: (a) the observed best full-sample |t| across the 5 gated rows with its row label; (b) `P(noise best |t| >= observed | N=5) = ...`; (c) the median best |t| N=5 produces under pure noise (bisection, tol 1e-4 — a sanity value near ~1.56); (d) a self-check: the same bisection at N=39 must print ≈2.37, matching STATE.md, proving the helper is right.
    5. VERDICT block: strictly factual. Compare: the gated both rows vs the `both (no fng)` control (did the sentiment filter improve BTC's negative edge, and by how much — quote the best gated row's R/t vs the control's R/t); the direction-split sanity (does the gate suppress the "wrong" side — long count rises on bullish days / short count on bearish days); the best gated config's |t| against the best-of-5 noise bar and the project's all-time 2.46 / 42%-beaten reference; the train/test pass/fail; whether the monthly breakdown front-loads. End with one line: `VERDICT: sentiment filter clears no bar / clears the bar only if ALL of [improves both control, OOS t>2.0, not front-loaded, best-of-N above noise] hold` — stating which conditions held and which failed. No hedging, no recommendation to wire anything live/demo.

    Then write `.planning/quick/20260928-btc-fear-greed-direction-filter/SUMMARY.md` — a report for user review, not a filler. Structure it on the scalper SUMMARY's model:
    - Title + hypothesis (F&G sentiment direction filter on BTC's both-direction single-slot book).
    - The full Task-2 BTC table transcribed VERBATIM (controls + 5 gated rows + leg decompositions) plus the F&G series span.
    - The falsification battery results (coverage span, 70/30 train/test table, monthly R table, noise calibration numbers incl. the N=39 self-check ~2.37).
    - A Findings section quoting STATE.md's prior context (BTC negative edge -0.043R/t=-1.20, "BTC is a machinery test, expected to lose", prior falsifications) and stating in plain terms whether the sentiment filter improves BTC's measured negative edge and clears any bar.
    - Status line: BACKTEST ONLY, measured for review; nothing live or demo changed (live/engine.py, config-btc.toml, config-cent.toml, the running bots untouched).
    - Tooling list (the fetcher + engine seam + two scripts).

    Commit: `git add scripts/falsify_btc_fng.py .planning/quick/20260928-btc-fear-greed-direction-filter/SUMMARY.md` → commit `docs(quick): BTC F&G sentiment direction filter measurement + falsification report`.
  </action>
  <verify>
    <automated>.venv\Scripts\python.exe scripts/falsify_btc_fng.py</automated>
  </verify>
  <done>
    The battery ran on the real engine over the BTC file and printed coverage, 70/30 train/test, monthly R, and the best-of-N noise calibration (with the N=39 ≈2.37 self-check matching STATE.md); SUMMARY.md exists with the verbatim measured tables and an honest, non-hedged verdict; both files committed.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| remote API → fetcher | The alternative.me F&G JSON crosses from an untrusted network host into `fear_greed._parse`. A malicious/compromised value could only bias a BACKTEST measurement (this task touches nothing live), so the blast radius is a wrong research number, not money. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|-----------|-----------|-------------|-----------------|
| T-fng-01 | S (Spoofing/Tampering) | news/fear_greed.py `_http_get_json`/`_parse` | mitigate | stdlib `json.loads` only (no code execution); reject non-200 statuses and bodies > 2 MB before parsing; require `data` key non-empty else raise; values coerced to float and dated via normalized UTC timestamps — a hostile body cannot run code or inject a non-numeric value. |
| T-fng-02 | D (DoS / runaway response) | news/fear_greed.py | accept | Single keyless GET with a 15s timeout and a 2 MB body cap; results cached so the network is hit at most once per refresh. Backtest-only, no live availability depends on it. |
| T-fng-03 | I (Information disclosure) | news/fear_greed.py | accept | Keyless public endpoint; no secrets are sent or stored. The cache file holds public sentiment values only. |

Note: the sentiment GATE itself is a pure mask over `df["setup"]` — no new trust boundary, and it cannot widen the existing engine's behaviour beyond suppressing (never adding) setups. The gate is backtest-only by construction (live/engine.py never calls run_backtest).
</threat_model>

<verification>
- Full suite green after Task 1: `.venv\Scripts\python.exe -m pytest tests/ -q` (existing 540 tests untouched + new test_fear_greed.py + test_engine_sentiment.py).
- Byte-identity proof: the pre-existing golden/1:1/single-direction/both tests pass unchanged (no existing test file edited).
- Task 2 driver exits 0 on the real data; its printed tables are captured in the SUMMARY; it hits the network at most once (cache written to data/processed/fear_greed.json).
- Task 3 falsifier exits 0; its noise-calibration N=39 self-check prints ≈2.37 (STATE.md's documented figure).
- live/engine.py, cli.py, config.py, config-btc.toml, config-cent.toml and every config/ are byte-identical at the end (git status shows no changes to them).
- Three atomic git commits exist (Task 1 fetcher+engine+tests, Task 2 driver, Task 3 battery+SUMMARY).
</verification>

<success_criteria>
- [ ] `run_backtest(..., sentiment=<aligned Series>, sentiment_band=...)` gates setups by F&G direction (bullish→long, bearish→short, neutral→both, NaN→fail-open) through the REAL shared engine; sentiment=None default is byte-identical (all existing tests green, none modified)
- [ ] `news/fear_greed.py` fetches the keyless alternative.me API with stdlib urllib, caches to data/processed/fear_greed.json, and maps onto M5 bars with shift(1) no-lookahead
- [ ] The pre-registered grid measured real broker-native BTCUSDc M5 (~100k bars): long/short/both rr=1.0 controls + 5 sentiment-gated band-sweep configs + leg decompositions
- [ ] Falsification battery ran: coverage (no stall), 70/30 train/test on the pre-registered configs, monthly R, best-of-5 noise calibration with an N=39 self-check ≈2.37
- [ ] SUMMARY.md reports the measured numbers verbatim with an honest verdict against the noise bar — no claim that any live/demo wiring is implied or approved
- [ ] Backtest-only end to end: live/engine.py and all configs untouched; three atomic commits
</success_criteria>

<output>
After completion, SUMMARY.md lives at `.planning/quick/20260928-btc-fear-greed-direction-filter/SUMMARY.md` (written by Task 3).
</output>
