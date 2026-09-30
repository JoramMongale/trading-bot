---
phase: 20260928-gold-dxy-sentiment-gate
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/trading_bot/news/macro.py
  - tests/test_macro.py
  - scripts/backtest_gold_dxy.py
  - scripts/falsify_gold_dxy.py
  - .planning/quick/20260928-gold-dxy-sentiment-gate/SUMMARY.md
autonomous: true
user_setup: []

must_haves:
  truths:
    - "A keyless, stdlib-only Yahoo chart fetcher (urllib + json, User-Agent header, NO RSS/lexicon pipeline) produces daily close series for DXY (DX-Y.NYB) and US10Y (^TNX), cached locally to data/processed/dxy.json and tnx.json so the backtest is reproducible offline and hits the network at most once; a pure to_gold_bullishness helper maps the DXY-vs-its-own-MA deviation to a 0-100 gold-bullishness scale (50 = neutral, weak dollar -> >50 -> long), and the existing map_to_bars applies shift(1)+ffill no-lookahead so a bar only ever sees a COMPLETED daily regime"
    - "The DXY regime gate reuses the EXISTING sentiment/sentiment_band seam with ZERO engine change: run_backtest(..., direction='both', sentiment=<gold-bullishness mapped onto bars>, sentiment_band=...) gates long-only when gold-bullish, short-only when gold-bearish, both when neutral/NaN (fail-open)"
    - "A pre-registered gold grid runs on data/processed/XAUUSDc_M5_broker.csv (~100k broker-native bars, 2025-04 -> 2026-08) through the REAL shared engine: long/short/both rr=1.0 controls (no gate) plus N=6 DXY-gated both configs sweeping MA window {50,200} x neutral band {0,5,10}, with long/short leg decompositions"
    - "The falsification battery reports coverage/stall, 70/30 train/test (OOS pass = TEST R > 0 AND t > 2.0), monthly R (front-loading), and best-of-N noise calibration (N=6 PRE-DECLARED) with the N=39 self-check printing ~2.37, and states plainly whether the DXY gate raises the both control (R +0.0810/t +1.94; long leg +0.1260/t +2.27, short +0.0228/t +0.36) and clears the bar"
    - "If (and only if) the DXY-alone verdict is 'clears no bar', a composite DXY+10Y 'macro headwind' no-trade-longs gate is measured via the EXISTING setup_veto seam (suppress LONG setups when BOTH DXY strong AND yields rising), with its own coverage / long-leg R+t / monthly / best-of-N battery — again ZERO engine change"
    - "Nothing live or demo is touched: live/engine.py, all config/*.toml, every MT5 path and the running bots are unchanged; results are for user review only"
  artifacts:
    - path: "src/trading_bot/news/macro.py"
      provides: "stdlib Yahoo chart fetcher for DXY + ^TNX (UA header, JSON cache, fail-closed) + to_gold_bullishness (DXY-vs-MA regime to 0-100) + is_yield_rising helpers"
      contains: "to_gold_bullishness"
    - path: "tests/test_macro.py"
      provides: "offline fetcher/parse/cache/normalization tests (monkeypatched urlopen); NO existing test file is edited"
    - path: "scripts/backtest_gold_dxy.py"
      provides: "pre-registered gold DXY grid driver (3 controls + N=6 DXY-gated band/MA sweep + leg decompositions) over XAUUSDc_M5_broker.csv"
    - path: "scripts/falsify_gold_dxy.py"
      provides: "falsification battery: coverage, 70/30 train/test, monthly R, best-of-N noise calibration (N=6, N=39 self-check) + conditional composite no-trade-longs gate"
    - path: ".planning/quick/20260928-gold-dxy-sentiment-gate/SUMMARY.md"
      provides: "measured tables + honest verdict (incl. the ~17-month thin-sample caveat) for user review"
  key_links:
    - from: "src/trading_bot/news/macro.py"
      to: "src/trading_bot/backtest/engine.py"
      via: "driver passes map_to_bars(dxy_bullishness, df.index) as the sentiment= Series; engine masks df['setup'] by side (bullish->long, bearish->short)"
    - from: "src/trading_bot/news/macro.py"
      to: "src/trading_bot/backtest/engine.py"
      via: "composite gate passes a make_macro_headwind_veto(...) closure as setup_veto=; the engine skips long setups returning 'macro_headwind_long'"
    - from: "scripts/backtest_gold_dxy.py"
      to: "src/trading_bot/backtest/engine.py"
      via: "run_backtest(df, direction='both', rr_multiple=1.0, sentiment=..., sentiment_band=...)"
    - from: "src/trading_bot/news/macro.py"
      to: "data/processed/dxy.json"
      via: "load_dxy writes the fetched daily close series once, reads it on every later run (tnx.json symmetric)"
    - from: "scripts/falsify_gold_dxy.py"
      to: "data/processed/XAUUSDc_M5_broker.csv"
      via: "loads the same ~100k broker-native gold bars the driver measures"
---

<objective>
Measure whether a DXY macro-regime sentiment gate improves gold's both-direction single-slot breakout edge, BACKTEST-FIRST, through the REAL shared engine — then, if the DXY gate alone is weak, measure the sharper DXY+10Y composite "macro headwind" no-trade-longs gate. Backtest only.

Purpose: gold's both-direction book is already positive but thin and long-leg-concentrated (STATE.md + scalper SUMMARY: long rr1.0 R+0.0925/t+2.11, short R+0.0009/t+0.02, both R+0.0810/t+1.94 — within the both book the long leg is R+0.1260/t+2.27 vs short R+0.0228/t+0.36). This task tests the research's ranked recommendation: (1) a DXY regime gate first (trade-with-regime: weak dollar -> long-only, strong dollar -> short-only, neutral band -> both), then (2) only if that fails, the composite DXY+10Y "macro headwind" gate that suppresses LONG setups when both the dollar is strong AND yields are rising. The research (LOCKED, `20260928-gold-sentiment-research/RESEARCH.md`) pins the source (keyless Yahoo chart API `DX-Y.NYB` and `^TNX`, both verified reachable), the gating rule shapes, the no-lookahead rule, and the falsification bar; it also flags the one non-negotiable pitfall — gate on DXY vs its OWN moving average (deviation/regime), never the raw non-stationary index level.

Decision rationale (planner's call): NO engine change is required, because both seams already exist and are pinned by the current 576-test suite. The `sentiment`/`sentiment_band` direction-gate seam (added by the prior FNG task) is exactly the "trade-with-regime" mask the DXY gate needs — it is direction-agnostic, takes any daily Series mapped via `map_to_bars` (shift(1)+ffill), and defaults off byte-identical. The `setup_veto` hook (added for the AI layer) is exactly the per-setup skip the composite no-trade-longs gate needs. So this plan adds a fetcher + a normalization helper + a driver + a battery, and wires them through the EXISTING seams — `live/engine.py` never calls `run_backtest`, and all `config/*.toml` and MT5 paths are untouched by construction.

Regime normalization (locked pitfall): `to_gold_bullishness` operates on the FRACTIONAL DEVIATION of DXY from its own trailing MA, not the raw level, then maps that deviation through a fixed sigmoid to a bounded 0-100 scale where 50 = neutral. Weak dollar (DXY below its MA, negative deviation) -> >50 -> the seam's "bullish" -> long-only; strong dollar -> <50 -> short-only. The exact formula is pinned below so the executor makes zero discretionary choices; the only knob is the MA window (swept {50,200}) and the neutral band (swept {0,5,10}).

Grid N is PRE-REGISTERED (no post-hoc winner-counting): 3 control rows (long/short/both rr=1.0, no gate) + N=6 DXY-gated both-direction configs (MA window {50,200} x band {0,5,10}). The 3 controls are the measured anchors the gated rows must BEAT; the 6 gated rows are the search whose best |t| is judged against best-of-6 noise (median best-of-6 ~1.90). If Task 4 runs, its composite sweep is a SEPARATE, pre-registered N=4 (dxy_ma {50,200} x tnx_ma {50,200} at band 5 and 10), judged on the long-leg criterion first.

Sample caveat (be explicit in the SUMMARY): the gold M5 overlap is only ~17 months (2025-04 -> 2026-08, 100k bars), so a daily macro regime has ~17 monthly observations to flip; treat any "pass" as provisional, wide t-bands.

Output: a stdlib Yahoo fetcher + normalization helpers + tests; a reproducible grid driver; a falsification battery; a SUMMARY.md with measured tables, the ~17-month caveat, and an honest verdict. Nothing live/demo.

Git: repo is local; commit atomically per task, only that task's files.
</objective>

<execution_context>
@$HOME/.config/opencode/get-shit-done/workflows/execute-plan.md
@$HOME/.config/opencode/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@AGENTS.md
@.planning/quick/20260928-gold-sentiment-research/RESEARCH.md
@.planning/quick/20260928-btc-fear-greed-direction-filter/PLAN.md
@.planning/quick/20260928-btc-fear-greed-direction-filter/SUMMARY.md
@.planning/quick/20260909-gold-both-scalper/SUMMARY.md
@src/trading_bot/backtest/engine.py
@src/trading_bot/news/fear_greed.py
@src/trading_bot/news/fetch.py
@scripts/backtest_btc_fng.py
@scripts/falsify_btc_fng.py
@scripts/backtest_both_scalper.py
@scripts/falsify_both_scalper.py
@tests/test_fear_greed.py
@tests/test_engine_sentiment.py

Data (real broker-native cent bars — the instrument config-cent.toml actually trades):
@data/processed/XAUUSDc_M5_broker.csv   (~100,000 bars, 2025-04-01 -> 2026-08-28, columns time,open,high,low,close)

Python on this Windows box: `.venv\Scripts\python.exe` (pytest 9.1.1; pyproject sets pythonpath=["src"]). The default pytest temp root `%TEMP%\pytest-of-joram` has a broken ACL, so ALWAYS run pytest with `-p no:cacheprovider --basetemp="C:\Users\joram\AppData\Local\Temp\opencode\pytest-bt"`.

Prior-art reference numbers to sanity-check against (print what is measured, do NOT editorialise):
- Gold both control (scalper SUMMARY + STATE.md): long rr1.0 n=438 R+0.0925/t+2.11, short rr1.0 n=472 R+0.0009/t+0.02, both rr1.0 n=481 R+0.0810/t+1.94 (leg long +0.1260/t+2.27 n=271, leg short +0.0228/t+0.36 n=210).
- STATE.md noise calibration: best |t| among 39 tries = 2.37 at the median; all-time best |t|=2.46 is beaten by noise 42% of the time. best-of-N helper is pinned by the N=39 ~2.37 self-check.
- RESEARCH.md bar: the gate must RAISE the both control R/t (not merely soften), survive OOS (TEST R>0 AND t>2.0), not be front-loaded (2026 half independently positive), and beat best-of-N noise (N=6 pre-declared -> bar ~1.90-2.0).

<interfaces>
Engine contract (src/trading_bot/backtest/engine.py) — ALREADY EXISTS, do NOT modify it. The two seams this plan uses:
```python
run_backtest(
    df,                      # OHLC DataFrame, datetime index named "time"
    fractal_left=2, fractal_right=2, sr_lookback=60, sl_buffer=0.01,
    rr_multiple=1.0, session_hours=None, max_hold_bars=None, tp_from_fill=False,
    direction="long",        # "long" (default) | "short" | "both"
    atr_median_bars=None, atr_period=14, htf_sma=None, htf_rule="1h", require_body=False,
    max_concurrent=1,
    on_event=None,
    setup_veto=None,         # <-- composite gate: Callable[[bar, entry, sl, tp], Optional[str]]
    variant="breakout", setup_override=None,
    sentiment=None,          # <-- DXY gate: Optional[pd.Series] aligned to df.index (0-100)
    sentiment_band=10.0,     # <-- half-width around 50; bullish >= 50+band, bearish <= 50-band
) -> list[dict]
```
Each returned trade record: entry_time, entry, sl, tp, exit_time, exit_price, exit_reason ("SL"|"TP"|"TIME"|"OPEN"), entry_idx, exit_idx, direction. For `direction="both"`, `df["setup_dir"]` ("long"/"short"/"") is built in pass A and the sentiment gate masks `df["setup"]` AFTER setups are built. The sentiment gate's NaN semantics: a NaN bar (no regime data) is `~bull & ~bear` = both allowed = fail-open.

`setup_veto(bar, entry, sl, tp)` is called exactly when a setup is about to be armed (pass B); a returned non-None reason string skips the arm. `bar` is `df.iloc[t]` (a pd.Series with `bar.name` = the timestamp index); for the breakout variant a LONG setup always has `entry > sl` (entry = resistance, sl = support - sl_buffer) and a SHORT has `entry < sl` — use `entry > sl` as the long test (robust, no reliance on the setup_dir column).

Fetcher pattern to mirror (src/trading_bot/news/fear_greed.py): `_http_get_json(url, timeout)` (urllib.request.Request with a `User-Agent` header, reject non-200, reject bodies > MAX_BODY_BYTES), `_parse(...) -> ascending daily pd.Series`, `fetch_*(url, timeout)`, `load_*(cache_path, url, timeout, refresh=False)` (fetch-once + JSON cache, fail-closed: a fetch failure with no cache RAISES), and `map_to_bars(daily, index)` (shift(1) then tz/resolution-align then reindex(method="ffill")) — `map_to_bars` is generic and is REUSED from `news.fear_greed`, not duplicated.

Yahoo chart API (keyless, verified reachable; needs a User-Agent header, else 401/429):
```
GET https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=max&interval=1d
symbols: DX-Y.NYB  and  ^TNX   (note: ^TNX must be URL-quoted -> %5ETNX)
```
Response shape to parse (untrusted input):
```json
{ "chart": { "result": [ {
      "timestamp": [ 1625097600, 1625184000, ... ],
      "indicators": { "quote": [ { "close": [ 110.2, 110.5, null, ... ] } ] }
  } ], "error": null } }
```
`close` may contain `null` (market holidays) which must be dropped; `timestamp` is unix-seconds -> UTC midnight daily index.

Driver pattern (scripts/backtest_btc_fng.py / backtest_both_scalper.py): `ROOT = Path(__file__).resolve().parent.parent`; `sys.path.insert(0, str(ROOT/"src"))`; `load_m5` reads the CSV with parse_dates=["time"], .set_index("time"), slices [["open","high","low","close"]]; copy `tstat`, `_r`, `summarize`, `summarize_leg` VERBATIM from scripts/backtest_btc_fng.py (they are the project convention; `_r` is sign-corrected per record direction).
</interfaces>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: stdlib Yahoo fetcher (DXY + ^TNX) + gold-bullishness normalization helper + tests</name>
  <files>src/trading_bot/news/macro.py</files>
  <files>tests/test_macro.py</files>
  <behavior>
    - Fetcher parse: a keyless Yahoo chart payload parses `chart.result[0].timestamp` + `indicators.quote[0].close` into an ASCENDING daily pd.Series (DatetimeIndex = UTC midnight, float closes), DROPPING null closes (market holidays) and deduping dates (keep last). A missing/empty `result` or `indicators.quote[0].close` raises (loud, not silent).
    - Cache: load_dxy fetches on first call and writes data/processed/dxy.json; a second call reads the cache with ZERO network; refresh=True refetches. load_tnx symmetric (tnx.json). A fetch failure with no cache RAISES (the series is a backtest INPUT, not a convenience).
    - Normalization: to_gold_bullishness(dxy, window) = 50.0 * (1.0 - tanh(dev / 0.05)) where dev = dxy / dxy.rolling(window, min_periods=window).mean() - 1.0. So: weak dollar (dxy below MA, dev < 0) -> value > 50; strong dollar (dev > 0) -> value < 50; dev == 0 -> exactly 50; bounded (0,100); monotonic decreasing in dev; NaN before the window is full. A constant DXY series (dev == 0 everywhere) returns exactly 50 after the warm-up.
    - Yield regime: is_yield_rising(tnx, window) = tnx > tnx.rolling(window, min_periods=window).mean() (bool Series, NaN before warm-up, treated fail-open downstream).
  </behavior>
  <action>
    Create `src/trading_bot/news/macro.py` (stdlib urllib + json + numpy; mirrors news/fear_greed.py's structure). Module docstring states the trust boundary: the remote Yahoo JSON is untrusted input, parsed with stdlib json (no code execution), bodies > MAX_BODY_BYTES rejected before parsing, non-200 raised. Contents:
    - `import numpy as np`; `MAX_BODY_BYTES = 2 * 1024 * 1024`; `USER_AGENT = "trading-bot/0.1 (+personal research)"`; `GOLD_BULLISH_SCALE = 0.05` (fractional DXY deviation mapping to tanh(1); documented a-priori — DXY rarely deviates >~5% from a 50/200d MA).
    - `DX_SYMBOL = "DX-Y.NYB"`; `TNX_SYMBOL = "^TNX"`.
    - `_chart_url(symbol: str) -> str`: `"https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(symbol, safe="") + "?range=max&interval=1d"` (so `^TNX` -> `%5ETNX`).
    - `_http_get_json(url, timeout=15.0) -> dict`: identical to fear_greed's — Request with the UA header; urlopen; reject non-200; read(MAX_BODY_BYTES+1), reject oversized; json.loads.
    - `_parse_chart(payload: dict, symbol: str) -> pd.Series`: take `payload["chart"]["result"][0]`; zip `timestamp` (unix-seconds) with `indicators["quote"][0]["close"]`; build a Series of floats keyed by `pd.to_datetime(int(ts), unit="s", utc=True).normalize()`; `.dropna()` (drops null closes); `.sort_index()`; dedupe dates keep-last via `s[~s.index.duplicated(keep="last")]`; `.rename(symbol)`. Raise ValueError if `result`/`quote[0]`/`close` is missing or empty (loud).
    - `fetch_dxy(url=None, timeout=15.0) -> pd.Series`: `_parse_chart(_http_get_json(url or _chart_url(DX_SYMBOL), timeout), DX_SYMBOL)`. `fetch_tnx` symmetric with `^TNX`.
    - `load_dxy(cache_path="data/processed/dxy.json", url=None, timeout=15.0, refresh=False) -> pd.Series` and `load_tnx(cache_path="data/processed/tnx.json", ...)`: mirror load_fear_greed — if the cache exists and not refresh, `_parse_chart({"chart":{"result":[json.loads(cache.read_text())]}}, symbol)`; else fetch, write the raw `chart.result[0]` object (timestamp + quote close) to cache (json.dump; `Path(cache_path).parent.mkdir(parents=True, exist_ok=True)`), return parsed. Network only on cache miss or refresh. Fail-closed: a fetch failure with no cache RAISES.
    - `to_gold_bullishness(dxy: pd.Series, window: int) -> pd.Series`: `ma = dxy.rolling(window=window, min_periods=window).mean(); dev = dxy / ma - 1.0; return 50.0 * (1.0 - np.tanh(dev / GOLD_BULLISH_SCALE))`, named "dxy_bullishness". Docstring explains the regime-not-level pitfall and the 0-100/50-neutral mapping.
    - `is_yield_rising(tnx: pd.Series, window: int) -> pd.Series`: `ma = tnx.rolling(window=window, min_periods=window).mean(); return tnx > ma`.

    DO NOT modify engine.py, fear_greed.py, or any existing test file. The `map_to_bars` no-lookahead helper is imported from `news.fear_greed` where it already exists (it already aligns tz/resolution, so a tz-aware Yahoo daily index maps cleanly onto the tz-naive broker M5 index).

    Tests — create the ONE new file `tests/test_macro.py` (mirror tests/test_fear_greed.py's monkeypatch-urlopen pattern; do NOT import across test files). A fixture Yahoo JSON payload with 3-4 entries (one close=null to exercise the holiday-drop; timestamps as unix-seconds strings, deliberately reverse-chronological); patch `macro.urllib.request.urlopen` with a _FakeResp-like object returning the JSON bytes. Tests:
    (1) `_parse_chart` returns an ascending daily Series with float closes and a normalized UTC-midnight index, the null close dropped, duplicate dates keep-last.
    (2) `load_dxy` writes the cache on first call and a second call reads it without calling urlopen (assert a call counter does not increment); `refresh=True` refetches.
    (3) `fetch_dxy` builds the `%5ETNX`-style quoted URL for `^TNX` (assert `_chart_url("^TNX")` contains `%5ETNX` and no raw `^`).
    (4) `to_gold_bullishness` direction + bounds: a strictly-decreasing DXY stretch (below its MA) yields values > 50; strictly-increasing (above MA) yields < 50; a constant DXY series yields exactly 50 (after warm-up) and values are within [0,100]; the leading window-1 rows are NaN.
    (5) `is_yield_rising`: a TNX series above its rolling mean is True, below is False, warm-up rows NaN.
    (6) fetch failure with no cache raises (HTTPError propagates, not a silent empty Series).

    Commit: `git add src/trading_bot/news/macro.py tests/test_macro.py` then commit `feat(news): stdlib Yahoo DXY/^TNX fetcher + gold-bullishness normalization (backtest measurement)`.
  </action>
  <verify>
    <automated>.venv\Scripts\python.exe -m pytest tests/test_macro.py tests/test_fear_greed.py tests/test_engine_sentiment.py -p no:cacheprovider --basetemp="C:\Users\joram\AppData\Local\Temp\opencode\pytest-bt" -q</automated>
  </verify>
  <done>
    macro.py fetches/parses/caches the keyless Yahoo DXY + ^TNX daily close series (UA header, fail-closed) and exposes to_gold_bullishness (regime-not-level, 0-100, 50 neutral) + is_yield_rising; no existing test file or engine file is modified; tests/test_macro.py is green; committed.
  </done>
</task>

<task type="auto">
  <name>Task 2: measurement driver — pre-registered gold DXY gate grid (controls + N=6 MA×band sweep) on XAUUSDc_M5_broker.csv</name>
  <files>scripts/backtest_gold_dxy.py</files>
  <action>
    Create `scripts/backtest_gold_dxy.py` (committed, reusable), modelled on scripts/backtest_btc_fng.py:
    - Header docstring: measure whether a DXY regime gate improves gold's both-direction edge, through the REAL shared engine (run_backtest). Research only; nothing live; live/engine.py untouched.
    - `ROOT = Path(__file__).resolve().parent.parent`; `sys.path.insert(0, str(ROOT/"src"))`.
    - `load_m5(csv)` identical to the scalper/FNG driver: `pd.read_csv(csv, parse_dates=["time"]).set_index("time")[["open","high","low","close"]]`.
    - Imports: `from trading_bot.backtest.engine import run_backtest`; `from trading_bot.news.macro import load_dxy, load_tnx, to_gold_bullishness`; `from trading_bot.news.fear_greed import map_to_bars`.
    - Copy `tstat`, `_r`, `summarize`, `summarize_leg` VERBATIM from scripts/backtest_btc_fng.py (project convention; `_r` sign-corrected per record direction).
    - A `run_config(df, direction, rr=1.0, sentiment=None, band=10.0)` helper calling `run_backtest(df, direction=direction, rr_multiple=rr, sentiment=sentiment, sentiment_band=band)`. Engine defaults (fractal 2/2, sr_lookback 60, sl_buffer 0.01, max_concurrent 1) left at default.
    - Load regime once: `dxy = load_dxy(cache_path=ROOT/"data/processed/dxy.json")`; `dxy50 = to_gold_bullishness(dxy, 50)`; `dxy200 = to_gold_bullishness(dxy, 200)`; map each onto bars with `map_to_bars(series, df.index)`. Print the DXY daily series span (first/last date, n days) and, at band=10, the mapped bar mix (bull / bear / neutral bar counts for window 50 and 200) as a context/diagnostic line — this exposes whether the regime flips often enough to matter (RESEARCH open question 1) and whether the gate over-gates.
    - THE PRE-REGISTERED GOLD DXY GRID (data/processed/XAUUSDc_M5_broker.csv). Print rows in exactly this order with exactly these labels:
      Controls (no gate — the anchors the gated rows must BEAT; expected to reproduce the scalper numbers long +0.0925/short +0.0009/both +0.0810):
        1. `long   rr1.0 (no dxy) `  → direction="long",  rr=1.0, sentiment=None
        2. `short  rr1.0 (no dxy) `  → direction="short", rr=1.0, sentiment=None
        3. `both   rr1.0 (no dxy) `  → direction="both",  rr=1.0, sentiment=None
      DXY-gated both-direction (N=6 — the MA×band sweep whose best |t| the noise bar judges):
        4. `both   rr1.0 dxy w50 b0 `  → both, rr=1.0, sentiment=dxy50_mapped,  band=0.0
        5. `both   rr1.0 dxy w50 b5 `  → both, rr=1.0, sentiment=dxy50_mapped,  band=5.0
        6. `both   rr1.0 dxy w50 b10`  → both, rr=1.0, sentiment=dxy50_mapped,  band=10.0
        7. `both   rr1.0 dxy w200 b0 ` → both, rr=1.0, sentiment=dxy200_mapped, band=0.0
        8. `both   rr1.0 dxy w200 b5 ` → both, rr=1.0, sentiment=dxy200_mapped, band=5.0
        9. `both   rr1.0 dxy w200 b10` → both, rr=1.0, sentiment=dxy200_mapped, band=10.0
    - For the `both rr1.0 (no dxy)` row and EVERY gated `both` row, also print a long/short leg decomposition (`summarize_leg`) so the direction-split effect of the gate (suppressing the wrong side) and any sample-shrinkage vs genuine-suppression attribution are visible.
    - Print the run context line first: data file, bar count, first/last bar time, engine params, the DXY series span, the two mapped-series bar mixes at band=10, and the exact grid definition (labels), so the run is reproducible from the output alone.
    - Exit non-zero with a naming-path message if the gold CSV is missing.
    - Do NOT write any output CSV/JSON; the printed tables ARE the deliverable. Do NOT load config files, do NOT import trading_bot.live, do NOT touch MT5. The ONLY network call is load_dxy's first-run fetch (cached thereafter).

    Run it: `.venv\Scripts\python.exe scripts/backtest_gold_dxy.py` — capture the full printed output verbatim for the SUMMARY.

    Interpretation aid (do NOT print editorialising): expect the 3 controls to reproduce the scalper numbers (both +0.0810/t+1.94, long leg +0.1260). The question is whether ANY gated row raises BOTH the both-book avg R AND |t| over the control, with the improvement attributable to the suppressed side (leg counts), and whether the gate's direction-split behaves as specified (weak-dollar days → long-heavy, strong-dollar days → short-heavy). Report whatever is measured.
  </action>
  <verify>
    <automated>.venv\Scripts\python.exe scripts/backtest_gold_dxy.py</automated>
  </verify>
  <done>
    The pre-registered 9-row gold grid (3 controls + N=6 DXY-gated MA×band sweep) + leg decompositions ran on the real ~100k-bar XAUUSDc_M5_broker.csv through run_backtest (gated rows via the sentiment seam with no-lookahead map_to_bars); DXY series span + bar-mix diagnostic printed; output captured verbatim; script committed (`git add scripts/backtest_gold_dxy.py` → `feat(scripts): gold DXY regime gate grid driver`).
  </done>
</task>

<task type="auto">
  <name>Task 3: falsification battery (coverage, 70/30, monthly, best-of-N w/ N=6 + N=39 self-check) + honest SUMMARY</name>
  <files>scripts/falsify_gold_dxy.py</files>
  <files>.planning/quick/20260928-gold-dxy-sentiment-gate/SUMMARY.md</files>
  <action>
    Create `scripts/falsify_gold_dxy.py` (committed), modelled on scripts/falsify_btc_fng.py (which imports the driver's helpers: `sys.path.insert` for both src and scripts, `from backtest_gold_dxy import load_m5, run_config, summarize, tstat, _r`). Import ONLY load_m5/run_config/tstat/_r — the battery drives the REAL engine itself. Load the DXY regime once via load_dxy/to_gold_bullishness/map_to_bars exactly as the driver does. Sections, in this order (all on the gold CSV):

    1. COVERAGE / stall check (the candle-reversal lesson): for `both rr1.0 (no dxy)`, `both rr1.0 dxy w50 b10` and `both rr1.0 dxy w200 b10`, report n closed, first entry_time, last exit_time, and span% of the frame. Print `STALL` if span < 95% (the gate must not starve the single slot; breakout levels are reachable so expect ~100%).
    2. TRAIN/TEST 70/30: cut = int(len(df)*0.7); run train and test slices (slice the mapped sentiment Series with the same cut, exactly as falsify_btc_fng slices `sent`) for the PRE-REGISTERED configs `both rr1.0 (no dxy)`, `both rr1.0 dxy w50 b5`, `both rr1.0 dxy w200 b5`, `both rr1.0 dxy w50 b10`, `both rr1.0 dxy w200 b10`. Print `train R/t` and `TEST R/t` per config. Rule (as in falsify_both_scalper): OOS pass = TEST R > 0 AND TEST t > 2.0; print pass/fail per row.
    3. MONTHLY R breakdown (front-loading): for `both rr1.0 (no dxy)` and `both rr1.0 dxy w200 b10`, group CLOSED trades by `str(entry_time)[:7]` and print month | n | R | t (same shape as falsify_btc_fng.run_monthly). Gold spans 2025-04 → 2026-08; a 2026 collapse IS the finding, print it.
    4. BEST-OF-N NOISE CALIBRATION (the STATE.md methodology): the DXY-gated grid is N=6 PRE-REGISTERED configs. Implement with stdlib only (copy `tail`, `p_noise_best_ge`, `median_best_of_n` VERBATIM from falsify_btc_fng.py). Print: (a) the observed best full-sample |t| across the 6 gated rows with its row label; (b) `P(noise best |t| >= observed | N=6) = ...`; (c) the median best |t| N=6 produces under pure noise (bisection, tol 1e-4 — a sanity value near ~1.90); (d) a self-check: the same bisection at N=39 must print ≈2.37, matching STATE.md, proving the helper is right.
    5. VERDICT block (DXY-alone): strictly factual. Compare the best gated both row vs the `both (no dxy)` control (did the DXY gate raise BOTH avg R and |t|, and is the improvement attributable to the suppressed side via leg counts rather than sample shrinkage); the direction-split sanity (does the gate suppress the "wrong" side — long count drops on strong-dollar/weak-gold bars, short count drops on weak-dollar bars); the best gated config's |t| against the best-of-6 noise bar (P<0.05) and the project's all-time 2.46 / 42%-beaten reference; the train/test pass/fail; whether the monthly breakdown front-loads. End with one line: `VERDICT: DXY gate clears the bar only if ALL of [raises both control R AND |t|, OOS t>2.0, not front-loaded, best-of-N above noise] hold` — stating which conditions held and which failed. No hedging, no recommendation to wire anything live/demo. This verdict is the gate that decides whether Task 4 runs.

    Then write `.planning/quick/20260928-gold-dxy-sentiment-gate/SUMMARY.md` — a report for user review, structured on the FNG/scalper SUMMARY model:
    - Title + hypothesis (DXY macro-regime sentiment gate on gold's both-direction single-slot book).
    - The full Task-2 grid table transcribed VERBATIM (controls + 6 gated rows + leg decompositions) plus the DXY series span and the band-10 bar mixes.
    - The falsification battery results (coverage span, 70/30 train/test table, monthly R table, noise calibration incl. the N=39 self-check ~2.37).
    - A Findings section quoting STATE.md prior context (gold both +0.0810/t+1.94, long-leg concentration, best-of-39 |t|=2.37 vs 2.46/42%-beaten, front-loading history) and stating in plain terms whether the DXY gate RAISES the both control and clears any bar.
    - An explicit thin-sample caveat: the gold M5 overlap is only ~17 months (2025-04 → 2026-08), so a daily macro regime has ~17 monthly observations; monthly-stability and OOS on 17 months is thin — treat any "pass" as provisional, wide t-bands.
    - Status line: BACKTEST ONLY, measured for review; nothing live or demo changed (live/engine.py, config-cent.toml, all config/*.toml, the running bots untouched).
    - Tooling list (macro.py + test_macro.py + the two scripts).

    Commit: `git add scripts/falsify_gold_dxy.py .planning/quick/20260928-gold-dxy-sentiment-gate/SUMMARY.md` → commit `docs(quick): gold DXY regime gate measurement + falsification report`.
  </action>
  <verify>
    <automated>.venv\Scripts\python.exe scripts/falsify_gold_dxy.py</automated>
  </verify>
  <done>
    The battery ran on the real engine over the gold file and printed coverage, 70/30 train/test, monthly R, and the best-of-N noise calibration (N=6 pre-declared, N=39 self-check ≈2.37 matching STATE.md); SUMMARY.md exists with the verbatim measured tables, the ~17-month thin-sample caveat, and an honest non-hedged DXY-alone verdict; both files committed.
  </done>
</task>

<task type="auto">
  <name>Task 4 (CONDITIONAL): composite DXY+10Y "macro headwind" no-trade-longs gate via setup_veto + its measurement</name>
  <files>scripts/falsify_gold_dxy.py</files>
  <files>.planning/quick/20260928-gold-dxy-sentiment-gate/SUMMARY.md</files>
  <action>
    GATE CONDITION: run this task ONLY if Task 3's DXY-alone verdict printed "clears no bar" (i.e. at least one of [raises both control, OOS t>2.0, not front-loaded, best-of-N above noise] FAILED). If the DXY-alone gate cleared ALL conditions, SKIP this task and record in SUMMARY.md a one-line note: "DXY-alone gate cleared the bar; composite no-trade-longs gate not built."

    When it runs, ADD to scripts/falsify_gold_dxy.py a composite section (and an `--composite` guard or a trailing section after the DXY-alone verdict), and APPEND a composite section to the existing SUMMARY.md. The composite is the research's "sharpest variant": suppress LONG setups when BOTH the dollar is strong AND yields are rising. It uses the EXISTING `setup_veto` seam (NO engine change).

    Implementation in the script:
    - Load `^TNX` via `load_tnx(cache_path=ROOT/"data/processed/tnx.json")`; `tnx_rising = is_yield_rising(tnx, window)` mapped onto bars via map_to_bars.
    - Build, per composite config, a veto closure:
      ```python
      def make_macro_headwind_veto(dxy_strong, yield_rising):
          def veto(bar, entry, sl, tp):
              if entry <= sl:                 # short (or degenerate) setup -- never suppress
                  return None
              if dxy_strong.loc[bar.name] and yield_rising.loc[bar.name]:
                  return "macro_headwind_long"
              return None
          return veto
      ```
      where `dxy_strong = to_gold_bullishness(dxy, dma).map(lambda v: v <= 50.0 - band)` (strong dollar → gold-bearish) and `yield_rising = is_yield_rising(tnx, tma)`, both mapped onto the FULL df.index via map_to_bars (shift(1)+ffill no-lookahead). The closure looks up by `bar.name`, so train/test slices pass the SAME veto (no length constraint on setup_veto); NaN regime (before warm-up) makes `dxy_strong`/`yield_rising` falsy → fail-open (no suppress).
    - PRE-REGISTERED composite sweep (N=4), each run as `run_backtest(df, direction="both", rr_multiple=1.0, setup_veto=veto)`:
      1. `both rr1.0 comp d50 t50 b5`  → dma=50, tma=50,  band=5.0
      2. `both rr1.0 comp d50 t50 b10` → dma=50, tma=50,  band=10.0
      3. `both rr1.0 comp d200 t200 b5`→ dma=200, tma=200, band=5.0
      4. `both rr1.0 comp d200 t200 b10`→ dma=200, tma=200, band=10.0
    - For each, print the both-book row PLUS the long/short leg decomposition (the long count must DROP vs the control's n=271 — that is the "cut losing longs" effect), and print the number of suppressed long setups (count `setup_skipped reason=macro_headwind_long` via an `on_event` callback if convenient, else infer from long-count reduction).
    - Composite battery (focused on the long-leg criterion, which is where the edge lives):
      a. COVERAGE: span% for the control and each composite row; print `STALL` if < 95%.
      b. LONG-LEG R/t: the composite's long leg avg R and |t| vs the control long leg (R+0.1260/t+2.27). The gate must RAISE the long-leg avg R and |t| (not merely cut count), without collapsing coverage.
      c. MONTHLY long-leg R for the best composite config (front-loading check; 2026 half must be independently positive).
      d. BEST-OF-N: N=4 composite configs; print observed best long-leg |t| and `P(noise best >= observed | N=4)`, plus the N=39 self-check ≈2.37 (reuse median_best_of_n).
    - Composite verdict line: `VERDICT: composite no-trade-longs gate clears the bar only if ALL of [raises long-leg avg R AND |t| vs control, coverage ~100%, not front-loaded, best-of-4 above noise] hold` — stating which held and which failed.

    APPEND to SUMMARY.md: the composite measurement tables verbatim (both rows + leg decompositions + suppressed-long counts), the composite battery results, and an updated Findings note (does the composite — cutting losing longs — raise the long leg where the DXY direction gate did not), keeping the ~17-month caveat and the BACKTEST-ONLY status line.

    Commit: `git add scripts/falsify_gold_dxy.py .planning/quick/20260928-gold-dxy-sentiment-gate/SUMMARY.md` → commit `docs(quick): gold composite DXY+10Y no-trade-longs gate measurement`.
  </action>
  <verify>
    <automated>.venv\Scripts\python.exe scripts/falsify_gold_dxy.py</automated>
  </verify>
  <done>
    (If run) the composite DXY+10Y no-trade-longs gate was measured via the existing setup_veto seam over the gold file: N=4 pre-registered configs with leg decompositions and suppressed-long counts; coverage/long-leg/monthly/best-of-4 battery printed; SUMMARY.md appended with the composite tables and an honest verdict; committed. (If skipped) SUMMARY.md records the DXY-alone pass and that the composite was not needed.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| remote Yahoo API → fetcher | The Yahoo chart JSON crosses from an untrusted network host into `news/macro._parse_chart`. A malicious/compromised value could only bias a BACKTEST measurement (this task touches nothing live), so the blast radius is a wrong research number, not money. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|-----------|-----------|-------------|-----------------|
| T-dxy-01 | S (Spoofing/Tampering) | news/macro.py `_http_get_json`/`_parse_chart` | mitigate | stdlib `json.loads` only (no code execution); reject non-200 statuses and bodies > 2 MB before parsing; require `chart.result[0].indicators.quote[0].close` non-empty else raise; closes coerced to float, null closes dropped, dates normalized via UTC timestamps — a hostile body cannot run code or inject a non-numeric value. |
| T-dxy-02 | D (DoS / runaway response) | news/macro.py | accept | Two keyless GETs (DXY, ^TNX) with a 15s timeout and a 2 MB body cap; results cached so the network is hit at most once per refresh. Backtest-only, no live availability depends on it. |
| T-dxy-03 | I (Information disclosure) | news/macro.py | accept | Keyless public endpoints; no secrets are sent or stored. The cache files hold public index/yield values only. |

Note: the DXY gate (sentiment seam) and the composite gate (setup_veto) are BOTH pure suppression paths over existing engine seams — no new trust boundary, and neither can widen the engine's behaviour beyond suppressing (never adding) setups. Both are backtest-only by construction (live/engine.py never calls run_backtest).
</threat_model>

<verification>
- Task 1: `tests/test_macro.py` green and NO existing test file edited (the 576-test suite stays green; run the focused subset as the prove command). No change to engine.py (git status shows it untouched).
- Task 2 driver exits 0 on the real data; its printed tables are captured for the SUMMARY; it hits the network at most once (cache written to data/processed/dxy.json).
- Task 3 falsifier exits 0; its noise-calibration N=39 self-check prints ≈2.37 (STATE.md's documented figure) and its N=6 pre-declared best-of-N line prints the observed best |t| and P-value.
- Task 4 (only if the DXY-alone verdict is "clears no bar"): falsifier exits 0 with the composite section printed; the N=39 self-check is unchanged ≈2.37.
- live/engine.py, cli.py, config.py, every config/*.toml and every MT5 path are byte-identical at the end (git status shows no changes to them).
- Three or four atomic git commits exist (Task 1 macro+tests, Task 2 driver, Task 3 battery+SUMMARY, and Task 4 composite+SUMMARY if it ran).
</verification>

<success_criteria>
- [ ] `news/macro.py` fetches the keyless Yahoo chart API (DX-Y.NYB + ^TNX) with stdlib urllib + UA header, caches to data/processed/{dxy,tnx}.json, exposes `to_gold_bullishness` (DXY-vs-own-MA deviation → 0-100, 50 neutral, weak dollar → >50) and `is_yield_rising`, and reuses `map_to_bars` shift(1) no-lookahead
- [ ] The DXY regime gate reuses the EXISTING `sentiment`/`sentiment_band` seam with ZERO engine change; the composite no-trade-longs gate reuses the EXISTING `setup_veto` seam with ZERO engine change
- [ ] The pre-registered grid measured real broker-native XAUUSDc M5 (~100k bars, 2025-04 → 2026-08): long/short/both rr=1.0 controls + N=6 DXY-gated MA×band configs + leg decompositions
- [ ] Falsification battery ran: coverage (no stall), 70/30 train/test on the pre-registered configs (OOS pass = TEST R>0 AND t>2.0), monthly R, best-of-6 noise calibration with an N=39 self-check ≈2.37
- [ ] (Conditional) If DXY-alone failed, the composite DXY+10Y no-trade-longs gate was measured via setup_veto with its own coverage / long-leg R+t / monthly / best-of-4 battery
- [ ] SUMMARY.md reports the measured numbers verbatim, the ~17-month thin-sample caveat, and an honest verdict against the noise bar — no claim that any live/demo wiring is implied or approved
- [ ] Backtest-only end to end: live/engine.py, engine.py, all config/*.toml and MT5 paths untouched; atomic commits per task
</success_criteria>

<output>
After completion, SUMMARY.md lives at `.planning/quick/20260928-gold-dxy-sentiment-gate/SUMMARY.md` (written by Task 3, appended by Task 4 if the composite runs).
</output>
