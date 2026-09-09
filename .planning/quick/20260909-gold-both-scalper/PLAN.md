---
phase: 20260909-gold-both-scalper
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/trading_bot/backtest/engine.py
  - tests/test_engine_both.py
  - scripts/backtest_both_scalper.py
  - scripts/falsify_both_scalper.py
  - .planning/quick/20260909-gold-both-scalper/SUMMARY.md
autonomous: true
user_setup: []

must_haves:
  truths:
    - "run_backtest accepts direction='both': long and short S/R breakout setups compete for the single slot (max_concurrent=1 semantics); each trade record carries its own 'long'/'short' direction and the default direction='long' run stays byte-identical to today (golden tests unchanged)"
    - "A backtest-only measurement runs the REAL shared engine over data/processed/XAUUSDc_M5_broker.csv (100k broker-native bars) for a pre-registered grid: long/short/both baselines at rr=1.0 plus 8 both-direction scalp exit configs (rr_multiple<1.0 tight targets, tp_from_fill re-anchors, max_hold_bars time stops) at M5 bar granularity"
    - "The report is honest by the project's noise bar: best-of-N |t| calibration over the pre-registered scalp grid, 70/30 train/test for the headline scalp exits, monthly R breakdown to expose front-loading, and a coverage check proving the engine consumed the whole sample (no candle-reversal-style stall)"
    - "Nothing live or demo is touched: live/engine.py, config-cent.toml, the running cent bot and all MT5 paths are unchanged; results are for user review only"
  artifacts:
    - path: "src/trading_bot/backtest/engine.py"
      provides: "direction='both' single-slot support in run_backtest (per-trade side, not a scalar sgn); direction='long' default byte-identical"
      contains: "direction"
    - path: "tests/test_engine_both.py"
      provides: "pins both-mode semantics: mirror symmetry, per-trade direction labels and geometry, single-slot no-overlap, invalid combos raise"
    - path: "scripts/backtest_both_scalper.py"
      provides: "grid measurement driver: controls + 8 scalp configs on XAUUSDc broker M5, optional BTC cross-check, honest summary table"
    - path: "scripts/falsify_both_scalper.py"
      provides: "falsification battery: coverage, 70/30 train/test, monthly R, best-of-N noise calibration, long-vs-short leg decomposition"
    - path: ".planning/quick/20260909-gold-both-scalper/SUMMARY.md"
      provides: "measured tables + honest verdict for user review (D-01)"
  key_links:
    - from: "src/trading_bot/backtest/engine.py"
      to: "src/trading_bot/strategy/signals.py"
      via: "detect_setups(df, direction='long') | detect_setups(df, direction='short') combined in pass A"
    - from: "scripts/backtest_both_scalper.py"
      to: "src/trading_bot/backtest/engine.py"
      via: "run_backtest(m5, direction='both'|'long'|'short', rr_multiple=..., max_hold_bars=..., tp_from_fill=...)"
    - from: "scripts/falsify_both_scalper.py"
      to: "data/processed/XAUUSDc_M5_broker.csv"
      via: "loads the same 100k broker-native bars the driver measures (BTCUSDc_M5_broker.csv secondary)"
---

<objective>
Measure a both-long-and-short M5 gold "scalper" variant of the swing S/R breakout — REAL shared backtest engine, broker-native XAUUSDc M5 data, honest stats. Backtest only.

Purpose: The single-slot live model (config-cent.toml, XAUUSDc, magic 77020) currently runs long-only breakout at rr=2.0 on an unproven, front-loaded edge (STATE.md: best |t|=2.46 vs a noise bar noise beats 42% of the time; recent-half t≈0.7). This task measures two untested claims BEFORE anything is wired anywhere: (1) letting short-side setups compete for the same single slot changes the book honestly — or just dilutes the long edge with gold's +54% drift (20260822 finding: shorts −0.059R vs longs +0.135R); (2) scalp-style fast exits (tight targets rr<1.0, fill-anchored targets via tp_from_fill, and max_hold_bars time stops at 1h/3h) turn that into a tradeable profile. Every prior short/reversal/scalp-like variant was falsified; the report must state plainly whether this clears any bar.

Decision 6 weigh-in (planner's call, per user framing): an ENGINE change — `direction="both"` in `run_backtest` — is the honest route, not a research driver. Rationale: both-direction single-slot competition IS slot arbitration, and the shared engine is the only place slot/fill mechanics are pinned by tests (fill at max/min(entry, open) gap-open worst price, SL-before-TP pessimism, an order never fills on its own signal bar, slot accounting at bar start, time stops freeing the slot). The candle-reversal investigation proved that measuring a slot mechanic outside the engine produces artifacts (its standalone driver "measured" +0.15R on a sample the engine later showed was 58% starved). The change is purely additive: `direction="long"` (default) stays byte-identical — pinned by the existing golden tests — and the live engine (live/engine.py) never calls run_backtest, so it is untouched by construction. Only the breakout variant supports "both"; the direction-scoped filters (body/htf) and `setup_override` raise a clear ValueError when combined with "both" until a measurement justifies them.

Scalp definition (D-02, D-07): the specific fast-exit parameterizations to measure are named and pre-registered below — engine knobs only, no fabricated geometry:
- `rr_multiple = 0.5` and `0.75`: TP at half/three-quarter the stop distance (level-anchored, the default; note the documented fill-above-entry asymmetry already makes realized R tighter than nominal for longs)
- `tp_from_fill = True` at `rr_multiple 0.5` and `1.0`: re-anchor the target on the actual fill price (true 0.5R / 1.0R scalp instead of the reference-level anchor)
- `max_hold_bars` time stops at 12 / 36 bars (1h / 3h on M5): "shorter holds" for a strategy whose measured median hold is 6.7h and p90 28h
- combinations of tight target + time stop (rr0.5×hold12, rr0.5×hold36)

Grid N for the noise-bar calibration is PRE-REGISTERED (no post-hoc winner-counting): 3 control rows (long/short/both at rr=1.0) + 8 scalp configs on gold. The controls are measured anchors, the 8 scalp rows are the search whose best |t| must be judged against best-of-8 noise.

Output: engine "both" support + tests; a reproducible grid driver; a falsification battery; a SUMMARY.md with measured tables and an honest verdict for user review.

Git: repo is local-only (HEAD 7f37afc baseline + 2 chore commits). Identity is already set (joram <github-joram@users.noreply.github.com>). Commit atomically per task, only that task's files.
</objective>

<execution_context>
@/Users/joram/.config/opencode/get-shit-done/workflows/execute-plan.md
@/Users/joram/.config/opencode/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@AGENTS.md
@config/config-cent.toml
@src/trading_bot/backtest/engine.py
@src/trading_bot/backtest/stats.py
@src/trading_bot/strategy/signals.py
@src/trading_bot/strategy/filters.py
@tests/test_backtest.py
@tests/test_short_and_filters.py
@scripts/backtest_liquidity_sweep.py
@scripts/falsify_liquidity_sweep.py
@scripts/backtest_candle_mirror.py
@scripts/backtest_candle_reversal.py
@.planning/quick/20260828-candle-reversal-falsified/SUMMARY.md

Data (real broker-native cent-instrument bars — the instrument config-cent.toml actually trades; D-05):
@data/processed/XAUUSDc_M5_broker.csv   (100,000 bars, 2025-04-01 → ~2026-03, columns time,open,high,low,close)
@data/processed/BTCUSDc_M5_broker.csv   (secondary cross-check only)

Python on this Windows box: `.venv\Scripts\python.exe` (pytest 9.1.1 present; pyproject sets pythonpath=["src"]). Run scripts and pytest with that interpreter.

Prior-art reference numbers to sanity-check the printed tables against (do NOT editorialise — print what is measured):
- Long-only breakout rr=1.0 on broker-native gold M5 has historically landed near avg R ≈ +0.09 (XAUUSDm, 437 trades, 58% win) — thinner on broker data than histdata.
- 20260822 short-side study: shorts −0.059R vs longs +0.135R on histdata; drift-neutral estimate +0.04R. Gold's measured +54% up-drift is why the short mirror underperforms.
- rr_multiple measured at 1.0/1.5/2.0 (quick 260824): win rate falls and net R is front-loaded (recent-half t≈0.7 for EVERY ratio). rr<1.0 is the unmeasured side of that curve.
- tp_from_fill=True was measured once (long-only, rr=1.0): win rate 58.6→53.9, net R 0.086→0.069 — moving the target away was worse. Re-measuring at rr0.5/1.0 in the both book re-tests it at scalp geometry.
- STATE.md noise bar: best |t| among 39 tries = 2.37 at the median; our all-time best |t|=2.46 is beaten by noise 42% of the time.

<interfaces>
Engine contract (src/trading_bot/backtest/engine.py) — what the driver calls:
```python
run_backtest(
    df,                      # OHLC DataFrame, datetime index named "time" (freq irrelevant; positions used)
    fractal_left=2, fractal_right=2, sr_lookback=60, sl_buffer=0.01,
    rr_multiple=1.0, session_hours=None, max_hold_bars=None, tp_from_fill=False,
    direction="long",        # "long" (default) | "short" | "both"  <- "both" is THIS task
    atr_median_bars=None, atr_period=14, htf_sma=None, htf_rule="1h", require_body=False,
    max_concurrent=1,        # single slot — the model the cent account can carry (D-03)
    on_event=None, setup_veto=None, variant="breakout", setup_override=None,
) -> list[dict]
```
Each returned trade record: entry_time, entry, sl, tp, exit_time, exit_price, exit_reason ("SL"|"TP"|"TIME"|"OPEN"), entry_idx, exit_idx, direction.
stats.py `trade_stats` already flips pnl sign per trade["direction"] (defaults "long"), so mixed-direction books aggregate correctly with no stats change.
Detection (strategy/signals.py): `detect_setups(df, "long")` = close>resistance & prior close<=prior resistance; `detect_setups(df, "short")` = close<support & prior close>=prior support (strict mirror). A bar cannot fire both sides (close cannot be above resistance AND below support when both levels are finite). levels.py `support_resistance(detect_swings(df,2,2),60)` computes both level columns once, direction-agnostically.
Driver pattern (scripts/backtest_liquidity_sweep.py): `sys.path.insert(0, str(ROOT/"src"))`, load_m5 reads the CSV with parse_dates=["time"], .set_index("time"), slices [["open","high","low","close"]]; tstat/report helpers at the bottom of the driver are copied by convention.
</interfaces>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: add direction="both" single-slot support to run_backtest (additive; default byte-identical)</name>
  <files>src/trading_bot/backtest/engine.py</files>
  <files>tests/test_engine_both.py</files>
  <behavior>
    - Test 1 (byte-identity of the long path after the refactor): on a 12,000-bar seeded random walk, `run_backtest(df)` == `run_backtest(df, direction="long")` record-for-record (guards the per-trade-sgn rewrite).
    - Test 2 (mirror symmetry): `run_backtest(df, direction="both")` and `run_backtest(_mirror(df), direction="both")` produce the same number of trades; pairing by entry_time, every trade's direction is flipped, prices are negated (±1e-6), exit_reason identical; trade_stats net/avg_r/win_rate equal. (Mirroring about zero swaps resistance breakouts for support breakdowns — the long/short mirror must be exact, as test_short_and_filters.py::test_short_on_mirrored_data_matches_long_trade_for_trade already demands for the single-direction runs.)
    - Test 3 (labels and geometry): on a random walk, a both-book run contains at least one "long" and one "short" trade, and every long has sl < entry < tp while every short has sl > entry > tp (sanity that sides armed from the right levels).
    - Test 4 (single slot, no overlap): in a both-book run at max_concurrent=1, trades sorted by entry_idx never overlap: each next entry_idx is strictly greater than the previous exit_idx.
    - Test 5 (invalid combos raise ValueError, message names direction="both"): variant="candle_reversal", require_body=True, htf_sma=20, and a non-None setup_override each raise when combined with direction="both". Also direction="sideways" still raises.
  </behavior>
  <action>
    Edit `src/trading_bot/backtest/engine.py` only. live/engine.py, cli.py, stats.py, config files and all strategy modules are NOT touched.

    Validation block (currently lines ~115-128):
    - Accept `direction in ("long", "short", "both")` in the first check.
    - Keep `variant not in ("breakout", "candle_reversal")` raising.
    - The candle_reversal guard already raises for anything but "long"; its message already covers "both" via the existing wording — leave it.
    - Add a new guard when `direction == "both"`: raise ValueError naming the offending kwarg if `variant != "breakout"`, `require_body`, `htf_sma is not None`, or `setup_override is not None`. Rationale to embed in the message/comment: the body and HTF filters are direction-scoped (they take a single direction), and a bare boolean setup_override carries no side, so a "both" run with any of them would gate or trigger incoherently. `session_hours`, `max_hold_bars`, `tp_from_fill`, `rr_multiple`, `atr_median_bars` and `max_concurrent` remain legal with "both" (all are direction-agnostic).

    Pass A (currently lines ~131-138): in the `variant == "breakout"` branch, replace the single `detect_setups(df, direction=direction)` call so that:
    - `direction == "both"`: after `df = support_resistance(detect_swings(df, fractal_left, fractal_right), sr_lookback)`, compute `long_sig = detect_setups(df, direction="long")["setup"]` and `short_sig = detect_setups(df, direction="short")["setup"]` (both derived from the same level frame — detect_setups copies, so df is untouched), then set `df["setup"] = long_sig | short_sig`, initialise `df["setup_dir"] = ""` and assign `df.loc[long_sig, "setup_dir"] = "long"`, `df.loc[short_sig, "setup_dir"] = "short"`. No numpy import: use only these pandas ops. (When both levels are finite a bar cannot satisfy both signals, so setup_dir is unambiguous wherever setup is True.)
    - single direction: keep `df = detect_setups(df, direction=direction)` exactly as today.

    Generalise the loop from one scalar `sgn` to per-trade / per-pending sides (this is the core refactor; the DEFAULT direction="long" run must produce byte-identical records, which the golden tests pin):
    - Delete the closure `sgn = 1.0 if direction == "long" else -1.0`. Add a small helper `def side_sgn(side): return 1.0 if side == "long" else -1.0` (module-level or closure).
    - Change `levels_at(bar)` to `levels_at(bar, side)`: for variant candle_reversal return `candle_levels(bar)` as today; otherwise `if side == "long": return float(bar.resistance), float(bar.support - sl_buffer)` else `return float(bar.support), float(bar.resistance + sl_buffer)`. (side == "short" is the only other value reachable.)
    - Open-trade management loop (currently lines ~240-255): inside the loop over `list(open_trades)`, derive that trade's own extremes instead of the closure ones — `sgn = side_sgn(trade["direction"])`, then `adverse = float(bar.low if sgn > 0 else bar.high)`, `favourable = float(bar.high if sgn > 0 else bar.low)` and keep the three checks EXACTLY as written today (SL before TP, both before TIME, TIME exits at the close). This is identical per trade to the old single-sgn behaviour; only the source of sgn changes.
    - Pending-fill loop (currently lines ~257-291): each pending dict now also carries its side (`"side"`). Inside the loop, `sgn = side_sgn(order["side"])`, derive that order's adverse/favourable from the bar the same way, keep the `armed_idx == t` skip and the comparison `sgn * favourable >= sgn * order["entry"]` unchanged, keep the gap-open fill `max(order["entry"], bar.open) if sgn > 0 else min(order["entry"], bar.open)`, keep the `tp_from_fill` line exactly as written (it is already direction-general: for a short, `fill - order["sl"]` is negative, placing the target below the fill by the stop distance). The trade dict built here must set `"direction": order["side"]` instead of the scalar `direction`.
    - Arming block (currently lines ~297-329): when a setup fires, resolve the side BEFORE levels_at: `side = direction if direction != "both" else str(df["setup_dir"].iloc[t])`. Then `entry, sl = levels_at(bar, side)`, `tp = entry + rr_multiple * (entry - sl)`, and append `{"entry": entry, "sl": sl, "tp": tp, "armed_idx": t, "side": side}` to pendings. The slot-accounting line (`slots_used_at_open = len(open_trades) + len(pendings)` computed at bar start) and every skip reason (open_trade / pending_order / incomplete_levels / veto) stay byte-identical.
    - All event emits stay as they are (do NOT add keys — keeps on_event consumers byte-identical).
    - Trade records keep their existing shape; for "both" runs each record's `direction` is that trade's own side, which is exactly what stats.py's per-trade sign flip consumes.

    Docstring/comment updates:
    - Replace the "``direction="both"`` is deliberately absent..." paragraph (lines ~90-92) with: both-direction single-slot competition IS now implemented, added 2026-09-09 for BACKTEST measurement of a both-side scalp variant (quick task 20260909-gold-both-scalper); it is deliberately NOT used by the live engine, which stays long-only breakout. Keep the sentence that two directions competing for one slot is a system with its own selection bias — that is exactly what the measurement exists to expose.
    - Update the `direction` docstring bullets: "long" (default) or "short" select the strict mirror; "both" detects the union of the two setups (a bar can fire at most one side) and runs them through the SAME single-slot loop, first signal to fire claiming the slot until it closes (max_concurrent=1). Note the guard list (candle_reversal/body/htf/setup_override rejected with "both").

    Tests — create `tests/test_engine_both.py` implementing the five behaviours above, following the file's conventions:
    - Reuse the `make_m5` / `_frame` builder style and import `_mirror` logic locally (copy the 6-line `_mirror` from tests/test_short_and_filters.py; do NOT import across test files).
    - Random-walk builder: copy `_random_walk(n=6000, seed=7)` shape from tests/test_short_and_filters.py (numpy default_rng). Use n=6000-12000 so both sides genuinely fire.
    - Mirror-symmetry test must first run `trade_stats` on both books (it enriches r_multiple/pnl_points) and compare aggregates with pytest.approx; pair trades by `entry_time` (the index survives mirroring unchanged).
    - Add one test asserting direction="both" trades each satisfy their side's geometry (sl/entry/tp ordering) on the walk.
    - Do NOT modify any existing test file. The existing golden + single-direction tests must stay green unchanged — they are the byte-identity proof.

    Commit (D-04): `git add src/trading_bot/backtest/engine.py tests/test_engine_both.py` then commit `feat(engine): direction="both" single-slot support for backtest scalper measurement`.
  </action>
  <verify>
    <automated>.venv\Scripts\python.exe -m pytest tests/test_engine_both.py tests/test_backtest.py tests/test_short_and_filters.py -q</automated>
  </verify>
  <done>
    run_backtest accepts direction="both" and returns mixed-direction single-slot trades; direction="long" (default) output is byte-identical to pre-change (all existing tests green, none modified); "both" rejects candle_reversal / require_body / htf_sma / setup_override with ValueError; new test file green; committed.
  </done>
</task>

<task type="auto">
  <name>Task 2: measurement driver — the pre-registered grid on real broker-native XAUUSDc M5</name>
  <files>scripts/backtest_both_scalper.py</files>
  <action>
    Create `scripts/backtest_both_scalper.py` (committed, reusable), modelled on `scripts/backtest_liquidity_sweep.py`'s structure:
    - Header docstring: measure the both-direction single-slot "scalper" variant of the swing S/R breakout through the REAL shared engine (run_backtest). Research only; nothing here is a live candidate and live/engine.py is untouched.
    - `ROOT = Path(__file__).resolve().parent.parent`; `sys.path.insert(0, str(ROOT / "src"))`.
    - `load_m5(csv)` identical to the liquidity driver: `pd.read_csv(csv, parse_dates=["time"]).set_index("time")[["open","high","low","close"]]`.
    - Imports: `from trading_bot.backtest.engine import run_backtest`. (Engine defaults fractal_left=2, fractal_right=2, sr_lookback=60, sl_buffer=0.01, max_concurrent=1 — identical to config-cent.toml's [strategy], so pass only the exit knobs explicitly.)
    - A `run_config(df, direction, rr=1.0, tp_from_fill=False, max_hold_bars=None)` helper that calls run_backtest once and returns the raw trades. NO grid state, no direction loops inside — the grid is the flat pre-registered list below.
    - A `summarize(trades, label)` helper copied from the liquidity/candle drivers' convention: closed = exit_reason != "OPEN"; n = len(closed); win% = TP/closed; per-trade r_multiple = (exit-entry)/(entry-sl) for longs, (entry-exit)/(sl-entry) for shorts (guard division by ~zero risk like the candle driver: `risk if risk else 0.0`); t = mean/sqrt(var/n); PF = gross win R / gross loss R; print `label | n | win% | R | t | PF | avg_hold_bars`. avg_hold_bars = mean(exit_idx - entry_idx) over ALL trades (the project's index-position convention). Skip the row when n < 2 (print n=0/insufficient).
    - THE PRE-REGISTERED GOLD GRID (data/processed/XAUUSDc_M5_broker.csv; engine max_concurrent=1 default — the single slot). Print rows in exactly this order with exactly these labels:
      Controls (the anchors the scalp rows must beat):
        1. `long   rr1.0        `  → direction="long",  rr=1.0
        2. `short  rr1.0        `  → direction="short", rr=1.0
        3. `both   rr1.0        `  → direction="both",  rr=1.0
      Both-direction scalp configs (N=8 — the search whose best |t| the noise bar judges):
        4. `both   rr0.5        `  → both, rr=0.5
        5. `both   rr0.75       `  → both, rr=0.75
        6. `both   rr0.5 tpffill`  → both, rr=0.5,  tp_from_fill=True
        7. `both   rr1.0 tpffill`  → both, rr=1.0,  tp_from_fill=True
        8. `both   rr1.0 hold12 `  → both, rr=1.0,  max_hold_bars=12   (1h on M5)
        9. `both   rr1.0 hold36 `  → both, rr=1.0,  max_hold_bars=36   (3h)
        10.`both   rr0.5 hold12 `  → both, rr=0.5,  max_hold_bars=12
        11.`both   rr0.5 hold36 `  → both, rr=0.5,  max_hold_bars=36
    - Also print a per-leg decomposition line under the both rr1.0 and both rr0.5 rows: split that run's closed trades by record direction and summarize each leg (`leg long n=... win=... R=... t=...` / `leg short ...`) using the same r_multiple formula — this quantifies the drift asymmetry (prior: shorts −0.059R vs longs +0.135R on histdata).
    - BTC cross-check (SECONDARY only, D-05): if data/processed/BTCUSDc_M5_broker.csv exists, run rows 1,2,3,4,8 (long/short/both rr1.0, both rr0.5, both rr1.0 hold12) and print a compact table under a `== BTC cross-check ==` header. This is a machinery cross-check, not a search.
    - Print the run context line first: data file, bar count, first/last bar time, engine params, and the exact grid definition (labels), so the run is reproducible from the output alone.
    - Exit non-zero with a naming-path message if the gold CSV is missing.
    - Do NOT write any output CSV/JSON; the printed tables ARE the deliverable (the SUMMARY transcribes them). Do NOT load config files, do NOT import trading_bot.live, do NOT touch MT5.

    Run it: `.venv\Scripts\python.exe scripts/backtest_both_scalper.py` — capture the full printed output verbatim for the SUMMARY.

    Interpretation aid (do NOT print editorialising): expect the short book to trail the long book (drift asymmetry), the both rr1.0 book to sit between the two side books, and scalp configs to show higher win% / lower avg R than rr1.0. The 0.5R targets will be hit far more often but pay a fraction of R, so net R is the honest column. Whatever the numbers, report them.
  </action>
  <verify>
    <automated>.venv\Scripts\python.exe scripts/backtest_both_scalper.py</automated>
  </verify>
  <done>
    The pre-registered 11-config gold grid + leg decompositions + optional BTC cross-check ran on the real 100k-bar XAUUSDc broker file through run_backtest with max_concurrent=1; output captured verbatim; script committed (`git add scripts/backtest_both_scalper.py` → `feat(scripts): both-direction scalper grid measurement driver`).
  </done>
</task>

<task type="auto">
  <name>Task 3: falsification battery (noise bar, 70/30, monthly, coverage) + honest SUMMARY</name>
  <files>scripts/falsify_both_scalper.py</files>
  <files>.planning/quick/20260909-gold-both-scalper/SUMMARY.md</files>
  <action>
    Create `scripts/falsify_both_scalper.py` (committed), modelled on `scripts/falsify_liquidity_sweep.py` (which imports the driver's functions the same way: ROOT path setup + `sys.path.insert` for both src and scripts, `from backtest_both_scalper import load_m5, run_config, summarize, tstat`). Import ONLY the load_m5/run_config helpers — the battery drives the REAL engine itself. Sections, in this order (all on the gold CSV unless noted):

    1. COVERAGE / stall check (the candle-reversal lesson): for `both rr1.0` and `both rr0.5 hold36`, report n closed, first entry_time, last exit_time, and span% = bars through the last exit as a share of the whole frame. Print a clear `STALL` warning if span < 95% (an unfilled pending would lock the single slot). Expect ≥100% here — breakout levels are reachable — but verify it.
    2. TRAIN/TEST 70/30 (D-07): cut = int(len(df)*0.7); run train and test slices through run_config for the four headline scalp exits that the full-sample grid will pick as candidates — do NOT pick post-hoc: pre-register `both rr1.0`, `both rr0.5`, `both rr0.5 tp_from_fill`, `both rr1.0 hold36`. Print `train R/t` and `TEST R/t` per config. The battery's rule (as in falsify_liquidity_sweep): OOS must stay positive with t > 2.0 to count as passing; state pass/fail per row in the printed output.
    3. MONTHLY R breakdown (front-loading): for `both rr1.0` and `both rr0.5`, group CLOSED trades by `str(entry_time)[:7]` and print month | n | R | t per month (same shape as falsify_liquidity_sweep.run_monthly). The battery already knows 2025 is the flattering half — a 2026-collapse pattern IS the finding, print it.
    4. BEST-OF-N NOISE CALIBRATION (the STATE.md methodology, D-07): the scalp grid above is N=8 independent configs. Implement with stdlib only:
       ```python
       import math
       def tail(x): return 0.5 * math.erfc(x / math.sqrt(2.0))
       def p_noise_best_ge(observed, n): return 1.0 - (1.0 - 2.0 * tail(observed)) ** n
       ```
       Print: (a) the observed best full-sample |t| across the 8 scalp rows with its row label; (b) `P(noise best |t| >= observed | N=8) = ...`; (c) the median best |t| N=8 produces under pure noise (bisect x on `(1 - 2*tail(x))**8 == 0.5`, tol 1e-4 — a sanity value near ~1.74); (d) a self-check: the same bisection at N=39 must print ≈2.37, matching the documented STATE.md figure, proving the helper is right.
    5. VERDICT block: a final printed paragraph that is strictly factual, comparing: the both rr1.0 book vs its two side books (did adding shorts help or dilute? quote the drift-asymmetry expectation from the 20260822 study); the best scalp config's t against the best-of-8 noise bar and against the project's all-time 2.46 / 42%-beaten reference; the train/test pass/fail; and whether the monthly breakdown front-loads. End with one line: `VERDICT: clears no bar / clears the bar only if ALL of [OOS t>2.0, not front-loaded, best-of-N above noise] hold` — stating which of those conditions held and which failed. No hedging, no recommendation to wire anything live.

    Then write `.planning/quick/20260909-gold-both-scalper/SUMMARY.md` — a report for user review (D-01), not a filler. Structure it on the candle-reversal SUMMARY's model:
    - Title + hypothesis (both-direction single-slot + scalp exits on M5 gold).
    - The full Task-2 gold table transcribed VERBATIM (controls + 8 scalp rows + leg decompositions) plus the BTC cross-check table.
    - The falsification battery results (coverage span, 70/30 train/test table, monthly R table, noise calibration numbers including the N=39 self-check).
    - A Findings section quoting STATE.md's prior context (drift asymmetry, front-loaded edge, prior falsifications of short/reversal/scalp variants) and stating in plain terms whether this clears any bar and why.
    - Status line: BACKTEST ONLY, measured for review; nothing live or demo changed (live/engine.py, config-cent.toml, the running cent bot untouched).
    - Tooling list (the engine seam change + the two scripts).

    Commit (D-04): `git add scripts/falsify_both_scalper.py .planning/quick/20260909-gold-both-scalper/SUMMARY.md` → commit `docs(quick): both-direction scalper measurement + falsification report`.
  </action>
  <verify>
    <automated>.venv\Scripts\python.exe scripts/falsify_both_scalper.py</automated>
  </verify>
  <done>
    The battery ran on the real engine over the gold file and printed coverage, 70/30 train/test, monthly R, and the best-of-N noise calibration (with the N=39 ≈2.37 self-check matching STATE.md); SUMMARY.md exists with the verbatim measured tables and an honest, non-hedged verdict; both files committed.
  </done>
</task>

</tasks>

<verification>
- Full suite green: `.venv\Scripts\python.exe -m pytest tests/ -q` after Task 1 (existing 534 tests untouched + new test_engine_both.py) — run once at the end of Task 1.
- Byte-identity proof: the pre-existing golden/1:1/single-direction tests pass unchanged (no existing test file was edited).
- Task 2 driver exits 0 on the real data and its printed tables are captured in the SUMMARY.
- Task 3 falsifier exits 0; its noise-calibration N=39 self-check prints ≈2.37 (STATE.md's documented figure).
- live/engine.py, cli.py, config-cent.toml and every config/ are byte-identical at the end (git status shows no changes to them).
- Three atomic git commits exist (Task 1 engine+tests, Task 2 driver, Task 3 battery+SUMMARY).
</verification>

<success_criteria>
- [ ] `run_backtest(direction="both")` works with per-trade direction labels through the REAL shared engine at max_concurrent=1; direction="long" default is byte-identical (all existing tests green, none modified)
- [ ] The pre-registered grid measured real broker-native XAUUSDc M5 (100k bars): 3 side controls + 8 named scalp configs (rr0.5/0.75, tp_from_fill at 0.5/1.0, max_hold 12/36 at rr1.0 and rr0.5) + long/short leg decompositions
- [ ] Falsification battery ran: coverage (no stall), 70/30 train/test on the 4 pre-registered scalp exits, monthly R, best-of-8 noise calibration with an N=39 self-check ≈2.37
- [ ] SUMMARY.md reports the measured numbers verbatim with an honest verdict against the noise bar — no claim that any live or demo wiring is implied or approved
- [ ] Backtest-only end to end: live/engine.py and all configs untouched; three atomic commits
</success_criteria>

<output>
After completion, SUMMARY.md lives at `.planning/quick/20260909-gold-both-scalper/SUMMARY.md` (written by Task 3).
</output>
