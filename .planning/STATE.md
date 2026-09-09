---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: JPY-Cross Breakout Investigation
status: executing
stopped_at: Phase 5 complete — 4/4 plans, 534-test suite green (2026-09-08)
last_updated: "2026-09-08T14:11:30.416Z"
last_activity: 2026-09-08 -- Phase 5 execution complete (Instrument-Correct Backtest Machinery)
progress:
  total_phases: 3
  completed_phases: 1
  total_plans: 4
  completed_plans: 4
  percent: 33
---

# Project State: Gold 5m Breakout Bot

**Updated:** 2026-09-07

## Project Reference

See: .planning/PROJECT.md (updated 2026-09-07 after v1.1 definition)

**Core value:** Detect the resistance breakout setup accurately and place correctly-priced Buy Stop orders — no missed setups, no false triggers, sensible risk.
**Current focus:** Phase 5 complete — next up Phase 6 (Broker-Native JPY Data + Dataset Integrity)

## Workflow State

| Setting | Value |
|---------|-------|
| Mode | yolo |
| Granularity | coarse |
| Parallelization | parallel |
| Commit docs | true (no git repo — direct file edits) |
| Model profile | balanced |

## Current Position

Phase: 05
Plan: 4/4 complete
Status: Phase 5 complete — milestone v1.1 in progress (Phases 6-7 pending)
Last activity: 2026-09-08 -- Phase 5 execution complete

## Deferred Items

Items acknowledged and deferred at milestone v1.0 close on 2026-09-07 (full detail in `.planning/milestones/v1.0-MILESTONE-AUDIT.md` and MILESTONES.md):

| Category | Item | Status |
|----------|------|--------|
| verification | Phase 2 VERIFICATION.md never persisted (accepted = dry-run E2E + 30 fake-MT5 + 8-case SAFE-03) | deferred |
| verification | Phase 3 (dir 04) VERIFICATION.md never persisted | deferred |
| verification | 03-HUMAN-UAT optional item: real-DeepSeek dry-run re-confirmation | pending |
| doc | 04-01-SUMMARY.md missing on disk — backfilled 2026-09-07 from PLAN | resolved |
| security | Unauthenticated MT5 RPC bridge on :8001 — bind 127.0.0.1 / SSH tunnel + credential rotation (post-malware) | open |
| dashboard | 5 orphaned `/api/*` routes duplicating page SQL; overview reads raw tables (DASH-01 wording exceeded) | open |
| testing | No automated tests for dbt mart SQL or the Next.js web app | open |
| ledger | `trade_ledger.py` globs `live_*.log`; CLI default is `live.log`; raw_ledger has no mart consumer | open |
| strategy | Live edge at/under noise bar (best \|t\|=2.46 vs 42% noise); BTC is a machinery test | open |
| risk | Aggressive live caps (rr 2.0, 20% gold / 10% BTC) applied by user — warned, non-blocking | open |

## Decisions

| Phase | Decision | Rationale |
|-------|----------|-----------|
| 1 | Phase 1 runs on historical data only; MT5 package omitted | Windows-only package, cannot install on this macOS machine |
| 1 | TA-Lib dropped from deps | No swing/fractal functions exist; pure pandas/numpy suffices for Phase 1 |
| 1 | pandas 3.0 datetime64[s] resolution (no unit="ns" forcing) | pandas 3.0 infers second resolution from %Y%m%d %H%M%S format |
| 1 | Config validation raises ValueError naming bad key; FileNotFoundError with resolved path | Actionable errors over silent fallbacks |
| 1 | Swing points are confirmed only after their right window closes: confirmed = raw.shift(right); levels/setups read confirmed columns only | No-lookahead bias (verified RESEARCH.md pitfall 1) |
| 1 | Plateau handling: >=/<= on left window, strict >/< on right → last bar of equal-high/low plateau is the swing | Matches verified fractal semantics |
| 1 | df.copy() at start of all strategy functions (incl. levels/signals where RESEARCH only copied in swings) | Plan-mandated pandas 3.0 CoW safety; makes functions truly pure |
| 1 | S/R level expiry is window-bounded: resistance/support = trailing-lookback rolling max/min of CONFIRMED swings, decaying to NaN the first bar the window holds no swing of that type (no .ffill()) — supersedes the 01-02 "ffill never returns to NaN" formula | Gap-closure plan 01-04: ffill-forever carried 2021 levels (~$100 gold) into 2025 data (~$2600 gold), producing economically impossible SL/TP; expiry is a pure function of bar count — no data-gap knowledge, no lookahead |
| 1 | Default-run cleanliness (sample CSV co-residing in data/raw, globbed by CLI) is plan 01-05's scope, not 01-04's | Sample is only 12 M5 bars, so its 2021 swings are legitimately inside the 60-bar window at the first 2025 bar; DAT_ASCII-only glob + sample relocation + data-gap warning land in 01-05 (depends on 01-04) |
| 1 | CLI globs only histdata `DAT_ASCII_{SYMBOL}_M1_*.csv` (using the configured symbol); sample + stray CSVs are never loaded | Durable code fix for the contamination gap — sample relocation alone is an on-disk op (data/raw is gitignored); the glob restriction is the repo-shipped guarantee |
| 1 | Gap threshold is a module constant (MAX_M1_GAP = 3 days), not a config key; `data_gap_detected` is a WARNING, never a hard error | Monthly files + ~1h daily breaks + ~2-day weekend gaps make >72h M1 gaps mean missing file(s); real broker data has legitimate gaps so exit code stays 0 |
| 1 | Sample relocated to data/sample/ and TRACKED in git (data/sample/ not gitignored) | The Task-3 integration fixture copies it from the repo — the clean-default test must run from a fresh checkout |
| 1 | Event loop: one trade at a time, SL-before-TP pessimistic, fill=max(entry,open), signal-on-final-bar = 0 trades, OPEN exit at last close | Verified RESEARCH.md conventions; all locked by tests |
| 1 | OPEN trades are excluded from wins/losses/win_rate but INCLUDED in net P&L (plan test 7 overrode RESEARCH.md's closed-only net) | Plan's Task 1 test list is authoritative; RESEARCH.md code example adapted |
| 1 | CLI rounds trades.csv prices/P&L and printed stats to 2 decimals (XAUUSD 2-dp quoting); log keeps rounded price fields | Binary float (101.91-101.10 != 0.81 exactly); display precision at CLI boundary |
| 1 | avg_trade_bars = mean(exit_idx - entry_idx) from index positions | Exact bar count even with data gaps; plan "compute via index positions" |
| 2 | live.enabled is the explicit opt-in permitting REAL-account execution; mode narrows to dry-run/demo/live | SAFE-03 demo-only enforcement designed into the schema |
| 2 | Legacy configs without [live] load via LiveConfig(**{**DEFAULT_LIVE, **raw.get("live", {})}) | Phase-1-era configs must keep working; schema grows, never breaks |
| 2 | PendingOrder.equivalent_to dedups re-triggers on symbol+magic+entry within 0.01 | XAUUSD 2-dp quoting tolerance; prevents double-placing the same setup |
| 2 | SimulatedBroker._cursor starts at len(rates); fetch_rates returns closed bars ending at cursor; advance() closes next bar | Forming bar excluded like live semantics; drives E2E replay |
| 2 | Every live component programs against BrokerClient ABC, never raw MT5 calls | MT5 pip package is Windows-only; abstraction is what makes Phase 2 testable on macOS |
| 2 | Safety guard is a pure function (live/safety.py): no logging, no broker access, no MT5 import; ACCOUNT_TRADE_MODE_* constants mirrored so the decision stays pure | The ENGINE decides what to do with SafetyError (log + skip); the guard only decides yes/no — keeps SAFE-03 single-purpose and testable on macOS |
| 2 | MetaTrader5 imported ONLY inside _load_mt5(); every MT5Broker method calls it — never at module top level | File imports on macOS where the package is absent; the single import site is what the fake-module (sys.modules injection) tests inject into |
| 2 | fetch_rates uses copy_rates_from_pos(symbol, tf, 1, count): start_pos=1 skips the forming bar | No-lookahead parity with the backtester — the live adapter never acts on a bar still building (RESEARCH.md) |
| 2 | None from copy_rates_from_pos returns an empty OHLC frame, not an error | A no-data poll is normal for a fresh start; error would spam the engine on cold boot |
| 2 | place_buy_stop filling mode from symbol_info() bitmask: IOC preferred → RETURN fallback → ORDER_FILLING_IOC; retcode DONE(10009)/PLACED(10008) = placed, else BrokerRejectedError | XAUUSD is 2-dp gold; explicit retcode handling per RESEARCH.md contract |
| 2 | DryRunBroker is a distinct wrapper type whose place_buy_stop contains ZERO references to the inner broker — logs event=order_plan (SAFE-02), returns placed=False/ticket=0 | Phase success criterion 4: dry-run places no orders but logs exactly what would be sent; a leaked real order is structurally impossible, not just a flag |
| 2 | poll_once() returns the ORDER event for a setup (on_setup result); setup_detected is logged (SAFE-02), not returned | Task-2 contract: the order event carries the detected entry/sl/tp, so detection tests assert prices on it |
| 2 | on_setup check order: pending-equivalent dedup → position-open dedup → SAFE-03 gate → place | Plan-mandated; dedup-before-safety reports skips (pending/position) before account checks |
| 2 | Decision-log prices rounded to 2 dp (XAUUSD quoting, CLI convention); OrderRequest + returned events keep full precision | "Log keeps rounded price fields" convention; wire precision preserved |
| 2 | Broker stubs subclass SimulatedBroker (e.g. _RejectingBroker) instead of reimplementing the ABC | Engine tests stay on the real broker contract with minimal stub surface |
| 2 | build_broker(cfg) factory lives in cli.py (no new module): dry-run → DryRunBroker(fresh SimulatedBroker), demo/live → MT5Broker | One factory, three modes; dry-run structurally cannot touch a real account |
| 2 | Dry-run never connects: SimulatedBroker.connect() is a no-op; empty-broker polls log bar_fetch_failed until data exists (documented dry-run-on-macOS behavior; E2E test seeds data) | A cold dry-run start is a graceful no-data poll, not an error |
| 2 | 02-06 runs on macOS via the siliconmetatrader5 Docker bridge, NOT Windows | The machine is an Apple M5 MacBook; `pip index versions MetaTrader5` confirms no macOS wheel exists for any architecture, so the terminal runs in a linux/amd64 Wine container reached over RPC (:8001) while the bot stays native |
| 2 | MT5Broker transport is per-adapter (`[live] bridge` = auto/native/silicon), resolved once in `_mt5()`; the bridge instance is cached, the native path is NOT | The bridge holds an RPC socket so it must not be rebuilt per call; the native path must keep re-importing so the 30 fake-MT5 tests can swap `sys.modules` between calls |
| 2 | Dry-run seeds a ReplayBroker from the histdata CSVs and advances one bar per fetch | `build_broker` previously passed `rates=None`, so the CLI dry-run path logged `bar_fetch_failed` forever and never ran detection — the suite stayed green because only the E2E test seeded data |
| 2 | `mode="live"` is not supported through the bridge | QEMU x86 emulation plus an RPC hop adds latency the strategy was never measured against; upstream says the same |
| 2 | 02-06 real-terminal verification PENDING (not passed): user has a Windows machine and will run the real-MT5 verification there. Accepted macOS verification so far = dry-run E2E over the golden frame (entry=101.00, sl=100.09, tp=101.91 exact 1:1) + 30 fake-MT5 adapter tests + 8-case SAFE-03 matrix + 115-test suite green. Windows checklist preserved in 02-06-PLAN.md/02-06-SUMMARY.md | MetaTrader5 pip package is Windows-only; plan's <resume-signal> accepts "deferred" as a close, but with a Windows machine now available the verification runs on Windows instead |
| q004 | rr_multiple default 1.0 in `run_backtest` keeps every existing call/behaviour byte-identical; tp = entry + rr_multiple×(entry−sl) in BOTH backtest and live engines (STRAT-03 parity, one formula) | Golden 1:1 tests pin the default; two engines sharing one formula prevents drift |
| q004 | Live wiring of rr_multiple was decided by the USER after the measured 1.0/1.5/2.0 table — the plan stopped at a checkpoint before any live change | The plan's sequencing contract: honest measurement first; live is real money |
| q004 | Aggressive settings WARN loudly but are ALLOWED: rr≥1.5, cap≥10%, account-wide total >5% each print a measured-evidence WARNING banner that accompanies the existing --yes gate, never blocks | User's added requirement: "make it configurable, just with a warning in the UI if a user decides to go for maximum" |
| q004 | tune_risk.py edits only [risk] + [strategy] tables via dotted keys; bare --set keys resolve to risk.<key> (backward compat) | The tool is a risk/strategy editor, not a general TOML editor; 22 prior tests stay green |
| q004 | Test suite stubs tune_risk._restart_agent (autouse) — tests editing tmp config copies must never bootout the real launchd agents | _restart_agent keys off the TAG, not the config path; one early failing test run actually restarted the live cent agent (pid 16117 → 31879, respawned healthy, config md5 unchanged) |
| q004 | The 2.0 net-R rise is front-loaded: full-span net R 0.091→0.230 looks good, but the recent half gives t≈0.7 for EVERY ratio — indistinguishable from zero and from each other | STATE.md noise calibration (best-of-39 |t|=2.46 is beaten by noise 42% of the time); treats the improvement as unproven |
| q005 | Operating model: ONE bot running at a time. Gold = Mon-Fri only (market shut Fri 21:00 → Sun 21:00 UTC); BTC = 24/7 when it is the one running | User directive 2026-08-24: "Gold closes weekends… should only have running one at a time… this week lets try Gold" |
| q005 | Weekend guard (no new gold entries after Friday ~19:00 UTC) NOT built — deferred by the user | Until it exists, closing gold before Friday 21:00 UTC is a manual human action (close_position.py), matching the 2026-08-21 19:02 manual close |
| q006 | bank_profits.py is READ-ONLY against the broker (account_info only; no order_send/position mutation/close anywhere, grep-verified) — the withdrawal is reported and logged, never executed: a MANUAL Exness-portal action | The bot cannot move money; the tool only makes the "trade with the base, not the profit" decision legible and records it |
| q006 | Runtime state lives in gitignored output/ (bank_base.txt pinned base USC; profits_banked.log ledger), never in config/; plain write_text is fine for scratch state | tune_risk's atomic dance exists for editing live config files, not scratch state |
| q006 | USC → R estimate = usc / 100 * usd_rate (health_check.py line-234 formula), --usd-rate default 18.0, labelled as an estimate; MIN_BANKABLE_USC = 1000.0 (~$10) below which the weekly-banking WARNING fires | Same formula as health_check so numbers agree across tools |
| q006 | Run bank_profits.py with `.venv/bin/python` — siliconmetatrader5 is only installed in the venv, not the system python3 (same gotcha as dashboard.py in q005) | The bridge client package is venv-scoped; system python reports `broker unavailable` even with the container up |
| 0302 | `[live] fetch_bars` default 0 is the byte-identical legacy window; only configs that opt in widen it. config-ai.toml + config-ai-live.toml use 5000 (~17 days M5). S/R expiry is window-bounded, so extra history never changes detection — only the model's context | The regime check resamples to DAILY bars; 69 bars ≈ 6h cannot judge a regime honestly |
| 0302 | `live --provider {mock,deepseek}` overrides config per run via dataclasses.replace before engine build (drives both AIEngine selection and build_ai_client); configs stay the safe default | A real-DeepSeek dry-run needs no config edit |
| 0302 | config-ai-live.toml is deliberately conservative paper-trading: `[ai] enabled=true`, `provider=mock`, `[live] mode=demo`, `magic_number=77200`, `[live] enabled=false` (SAFE-03) | Real-account AND real-model execution both stay separate human opt-ins |
| 0302 | Real-DeepSeek verification succeeded with a gate verdict (BLOCKED low_confidence, conf 65 < 70) — a genuine model reply ran the real gate and was vetoed | The gate catching a sub-threshold proposal IS the intended behavior, not a failure |
| 0303 | Warehouse idempotency = MERGE INTO on natural keys: trades (source, entry_time, entry), decisions/closes (source_log, line_number), ai_calls (source_file, ts), bars (source_file, time), ledger (source, row_idx) | Re-running never duplicates; row counts stable (verified twice on fixtures AND real data) |
| 0303 | Raw tables stay source-shaped; dbt staging is the type-cast/dedupe seam (ROW_NUMBER on natural key); marts are the queryable surface | Matches the plan's loader → staging → marts contract; keeps SQL models tiny |
| 0303 | CLI is `scripts/warehouse_cli.py` (not warehouse.py): the module name collided with the warehouse package once test collection injects scripts/ onto sys.path | A script named warehouse.py breaks `import warehouse.load` in full-suite runs |
| 0303 | dbt runs from the dbt/ directory — dbt-duckdb 1.11.0 resolves the DB path against CWD, not profiles.yml; `../data/analytics/trading.duckdb` is correct from dbt/ | Plan's `--project-dir dbt` invocation pointed at the repo parent and failed |
| 0304 | News sentiment is computed at INGEST time (lexicon score stored on raw_news_articles); dbt marts only aggregate — no duplicate scoring across Python/SQL | Score is a fixed deterministic function; storing it keeps SQL trivial and the mart pure |
| 0304 | The regime SENTIMENT block is one `{sentiment_block}` paragraph placeholder rendered to "" when the snapshot is absent — never "None"/"nan" | Clean absence handling per the plan's "separate paragraph" instruction |
| 0304 | News is strictly fail-open: absent/corrupt snapshot → `ai_regime_sentiment_unreadable` + sentiment=None, the day proceeds (T-04-04-03) | A macro input must never block trading; the regime check's own fail-OPEN policy is unchanged |
| 0304 | Two default gold RSS feeds (kitco, goldprice) 404'd during verification — per-feed failure isolation kept the pipeline alive; MarketWatch delivered 10 articles | Feeds are configurable; operators should refresh the gold-specific URLs when convenient |
| 0305 | 03-05 truth "account balance" accepted as PARTIAL — Overview shows poll freshness + open positions but no balance; neither DASH-01 nor roadmap SC6 requires it, and the mart layer has no balance column | User decision 2026-08-28: accept as-is rather than add new ingest work outside the phase |
| 0305 | The dashboard is READ-ONLY by construction: access_mode=read_only on the DuckDB instance, GET-only routes, 127.0.0.1 hard-bind, no broker imports | DASH-02 is structural, not conventional — a browser edit can never bypass what the CLI enforces |
| 0305 | mart_news_sentiment_daily is OPTIONAL for warehouse readiness — /api/news returns 200 + [] when absent, 503 only when the whole warehouse is missing | Keeps verification order-independent under parallel wave-2 execution (03-04 may not have run) |
| fast | 2026-08-28 BTC risk: cap 0.5%→10.0%, max_leverage added 50.0 (was default 20). cap×slots = 10%×2 = 20% account-wide | User decision after three TPs booked R4 at 0.5% cap; tune_risk warns non-blocking (aggressive tier) |
| fast | 2026-08-28 watch_closes.py pins the terminal per config (--config → [live] terminal_path), one watcher per terminal | Multi-terminal box otherwise reports every bot's closes against whichever install MT5 finds first; gold closes were invisible before |
| fast | 2026-08-28 test updates: tune_risk/dashboard/cli_ai tests had hardcoded conservative config values; updated to the live aggressive configs | Config-drift, not regressions — the user's intentional 10%/20% caps and rr2.0 changed the fixtures the tests copy |
| 0305 | 2026-08-28 sweep: no BTC config positive on both halves; gold session-filtered (s9-21 lb60) fits 2025 at t≥3.0 but does NOT generalize to 2026 (best test t=+0.92) | Strictest test (fit 2025 → test 2026) confirms the edge is front-loaded and dead in 2026; matches the documented front-loading finding |
| stratvar | strategy.variant seam (breakout|candle_reversal) + setup_override falsification seam, both default byte-identical | Test strategies are selectable in the backtester and measured through the REAL engine; the live engine never reads variant so both live bots stay on breakout |
| stratvar | setup_override research seam injects a caller setup column (coin flips) before filters | Random-signal controls must run through the same engine mechanics to isolate fill/slot bias from predictive alpha |
| stratvar | Slot-starvation: a never-filled pending Buy Stop permanently locks max_concurrent=1 (candle variant stalled at 58% of gold's bars) | Single-slot models with pending entries need an explicit order TTL/cancellation; not changed here — live breakout never exhibits it because swing levels are reachable |
| orb | Session strategies enter at the NEXT BAR OPEN, not via pending orders | Next-open entry eliminated slot starvation entirely — 100% bar coverage on both instruments; future session strategies must use it |
| orb | Random-time control: real session windows must beat random windows of the same mechanic | Random window r7s9 (R+0.139/t+2.23) beat the real London window (R+0.107/t+1.39) — the "session" timing was not the edge |
| vol | Ablation control: remove the claimed mechanism (squeeze filter) and compare against a plain band-breakout | The stripped strategy matched or BEAT the squeezed one (gold: plain R+0.042/t+1.96 vs squeezed R−0.023/t−0.76) — the state filter was actively harmful, not additive. Test state-filter hypotheses this way, not just vs random |
| htf | H4 EMA50 trend gate on M5 EMA20 pullbacks is NOT lagging bias — it beats both the unfiltered pullback (ablation) and random-bias controls | But the edge is economically negligible (gold R+0.013/t+1.04, OOS t−0.24) — a real-but-negligible signal is still untradeable. Distinguish "fails because noise/front-loaded" from "fails because too small" — different conclusions for what to do next |

## Milestones

| Milestone | Status |
|-----------|--------|
| v1.0 — Backtested, demo-traded breakout bot + AI layer | ✅ SHIPPED 2026-08-28, archived 2026-09-07 (see .planning/MILESTONES.md) |
| v1.1 — JPY-Cross Breakout Investigation | 🚧 Roadmapped (2026-09-07) — Phases 5-7 defined, awaiting /gsd-plan-phase |

## Quick Tasks Completed

| ID | Task | Date | Status |
|----|------|------|--------|
| 260819-nhq | macOS demo path: MT5 RPC bridge + real dry-run replay | 2026-08-19 | partial — code landed, demo run blocked on credential rotation |
| 260820-mkt | Market entry replaces the rejected Buy Stop + hard per-trade risk gate | 2026-08-20 | complete — 167 tests green; bot placed its own first order 16:40 (ticket 3113739731) |
| 260820-pi | Can the bot run on a Raspberry Pi? | 2026-08-20 | complete — yes for the bot, no for MT5; see docs/raspberry-pi-deployment.md |
| 260821-ipad | Can the bot run on an iPad? | 2026-08-21 | complete — no; iPadOS suspends background apps, so the poll loop cannot survive. iPad is a control surface, not a host. See docs/ipad.md |
| 260822-short | Short-side mirror + ATR/H1/body filters, backtest only | 2026-08-22 | complete — 212 tests green. Every proposed filter FAILS out-of-sample; shorts −0.059R vs longs +0.135R, and the gap is gold's +54% drift, not edge. Drift-neutral estimate +0.04R. See .planning/quick/20260822-short-side-and-filters/SUMMARY.md |
| 260824-launchd | 24/7 launchd agents for BTC + gold (real money) | 2026-08-24 | complete — both bots launchd-supervised (`com.joram.trading-bot-btc`, `-cent` via `scripts/launchd_run_live.sh`); handover executed + verified, order_placed counts unchanged. Fixed a stack-lock deadlock found during handover (`21efabb`). See .planning/quick/002-launchd-24-7-btc-gold/SUMMARY.md |
| 260824-risk | Risk-tuning CLI for the live bots | 2026-08-24 | partial — `scripts/tune_risk.py` + 22 tests built (246 green); read-only view verified, live `--set` + launchd-restart path awaiting user verification. See .planning/quick/003-risk-tuning-script/SUMMARY.md |
| 260824-risk | Risk-tuning CLI for both live bots | 2026-08-24 | code + tests complete (246 suite green) — read-only viewer + confirmed/validated `[risk]` editor (`scripts/tune_risk.py`) with account-wide budget gate, leverage warning, and launchd restart; 22 new tests, live configs never written. See .planning/quick/003-risk-tuning-script/003-SUMMARY.md — task 3 real-command verification PENDING |
| 260824-rr | TP/SL ratio (rr_multiple): measured study first, live wiring after approval | 2026-08-24 | complete — 260 tests green. `rr_multiple` flows config → backtest CLI → engine → live engine (tp = entry + rr_multiple×(entry−sl), default 1.0 byte-identical). Measured 1.0/1.5/2.0 on 100k broker-native XAUUSDm M5 bars: net R 0.091/0.147/0.230, win 58.4%/49.3%/43.8%, max DD $589/$782/$990 — but split-sample shows the edge is FRONT-LOADED (recent-half t≈0.7 for EVERY ratio). tune_risk.py now edits `strategy.rr_multiple` via dotted `--set` with loud measured-evidence warnings for aggressive tiers (rr≥1.5, cap≥10%, total>5%); warn, don't block. Live config NOT changed — user applies via `python scripts/tune_risk.py --tag cent --set strategy.rr_multiple=2.0 --yes`. See .planning/quick/004-tp-sl-ratio/004-SUMMARY.md |
| 260824-dash | Local web dashboard (status/risk/account) | 2026-08-24 | complete — `scripts/dashboard.py` (stdlib, 127.0.0.1:8765) + `scripts/dashboard.html` (Status/Risk/Account tabs) + 10 tests (270 green). Read-only by default; writes reuse tune_risk.py's exact warning/--yes gate; loopback-only binding. Server running (pid in output/dashboard.out). Note: 004's test hiccup left a stray BTC position (435655460) at the broker on SL/TP — user left it. See .planning/quick/005-web-dashboard/005-SUMMARY.md |
| 260824-bank | Bank-the-profits helper (read-only banking CLI) | 2026-08-24 | complete — `scripts/bank_profits.py` (stdlib-only, READ-ONLY: account_info only, no order/position calls anywhere): shows balance/pinned base/bankable excess in USC + R estimate, first-run auto-pins the base, `--base` repins, `--confirm` appends one `event=profits_banked` line to output/profits_banked.log and prints the manual Exness-portal withdrawal instruction. 8 tests (278 suite green). Real run verified: balance 3205.64 USC, base pinned 3205.64 USC, bankable 0.00. Run with `.venv/bin/python` (siliconmetatrader5 not in system python). See .planning/quick/006-bank-profits/006-SUMMARY.md |
| 260828-btclev | Raise BTC live risk: cap 0.5%→10%, max_leverage 50 | 2026-08-28 | complete — `config/config-btc.toml` [risk]: max_loss_pct_per_trade 0.5→10.0, max_leverage added =50.0 (was default 20). User decision (three TPs booked R4 at old 0.5% cap; same move at 10% ≈ R80). cap×slots = 10%×2 = 20% account-wide if both stops hit — aggressive, tune_risk warns non-blocking. Config loads clean; NOT yet applied live (bot needs restart to pick it up). |
| 260828-closes | Fix watch_closes.py terminal pinning — gold closes now appear | 2026-08-28 | complete — the watcher called bare `initialize()` so it attached to whichever MT5 install it found first (BTC terminal); gold closes were missing. Added `resolve_mt5_for_cfg` (pins `[live] terminal_path`, mirrors health_check._init_terminal) + `--config` flag; removed the redundant second bare `initialize()`. One watcher per terminal (btc + cent), both running; backfilled closes.log with gold + old shared-account trades incl. today's XAUUSDc TP (+296.80 USC, r=+0.93). |
| 260828-sweep | BTC + gold parameter sweep and walk-forward (research) | 2026-08-28 | complete — 18 BTC configs: none positive on both halves. 12 gold session-filtered configs: all positive OOS walk-forward (best s9-21 lb60 t=+2.72) but front-loaded — monthly breakdown shows 2025 uniformly positive, 2026 noise. Strictest test (fit 2025 → test 2026): best test t=+0.92. Gold's edge died at the 2025→2026 boundary; no live-relevant config found. See `scripts/sweep_btc.py` (also sweeps XAUUSDc). |
| 260828-reversal | Candle-reversal strategy investigation (research) | 2026-08-28 | complete — FALSIFIED (research-script AND proper-engine passes). User's "green-after-red, buy high / fade high" idea measured on 100k M5 bars gold+BTC: buy-breakout loses (mean reversion); mirror sell-stop loses; fade-limit "edge" is pure fill-selection bias (random-signal control beats the pattern). Proper-engine pass (pattern wired as `variant="candle_reversal"`, `setup_override` coin-flip control): gold pattern R+0.033/t+1.18 LOSES to random seed R+0.124/t+3.19; BTC negative. PLUS a structural finding: the variant's Buy Stop at the signal candle's high often never fills, so the never-filled pending permanently locks `max_concurrent=1` and the engine stalls at ~58% of gold's bars (7 months untraded) — the earlier +0.15R CLI metric was a starved-sample artifact. Retained as a backtest-only test strategy for regression testing; live engine unchanged (always `variant="breakout"`). Method note: verify the engine consumed the whole sample (identical train/full rows = stall). See `.planning/quick/20260828-candle-reversal-falsified/SUMMARY.md`. |
| 260828-orb | Liquidity-sweep / session ORB investigation (research) | 2026-08-28 | complete — FALSIFIED. Hypothesis: price sweeping the Asian-range (00:00–06:00) High/Low during London/NY open is a structural edge (breakout-continuation OR failed-sweep reversal). Built pure module (session_range/detect_sweeps, 8 tests), session driver (entry at NEXT open — clean 100% bar coverage, no slot starvation), ran full falsification: full-sample best t=1.66 (below noise bar); train/test FAILS (gold failed rr1.0 train R+0.259/t+2.87 → test R−0.231/t−1.69); random-time control FAILS (random window r7s9 R+0.139/t+2.23 BEATS real London window R+0.107/t+1.39 — session timing carries no alpha); monthly shows 2025-only front-loading (flat/negative from 2026-04). Same 2025 artifact as every prior candidate. Retained as backtest-only test strategy. See `.planning/quick/20260828-liquidity-sweep-or/SUMMARY.md`. |
| 260828-vol | Volatility compression/expansion investigation (research) | 2026-08-28 | complete — FALSIFIED. Hypothesis: entering when volatility first expands out of a Bollinger-bandwidth squeeze captures the start of the move. Pure module (bollinger width, detect_squeezes, 7 tests), driver (next-open entry, 100% coverage). Full-sample best t=−0.76 (nothing positive). Ablation control is the killer: SQUEEZED gold R−0.023/t−0.76 vs PLAIN band-breakout (no squeeze) R+0.042/t+1.96 — the squeeze filter actively SUBTRACTS value on gold; BTC identical either way (t≈0.1). Train/test fails (gold +0.011→−0.106; BTC mirrors −0.043→+0.115 — regime luck). Monthly: no stable edge (gold 2026-05 t=−3.35 against). 4th consecutive candidate falsified. See `.planning/quick/20260828-volatility-compression/SUMMARY.md`. |
| 260828-htf | HTF-aligned M5 pullback investigation (research, gold account target) | 2026-08-28 | complete — FALSIFIED FOR LIVE (5th candidate). Hypothesis: M5 pullbacks to EMA20 gated by H4 EMA50 trend. Pure module (htf_bias shift-by-1 no-lookahead, detect_pullbacks, 5 tests), driver + battery. GOLD (XAUUSDc, the live account instrument): HTF-gated rr1.0 R+0.013/t+1.04, 100% coverage. Controls: HTF ablation (gated +1.04 vs unfiltered −0.65 — the EMA gate genuinely helps) AND random-bias control (EMA +1.04 vs random seeds −1.05/−1.33/−0.13 — EMA beats coin flips) — the FIRST mechanism in the battery to beat its random control, i.e. NOT lagging bias. BUT the edge is economically negligible: fails OOS (train +1.45 → test −0.24), no stable monthly edge, far below the noise bar. Distinction: fails because the signal is real-but-negligible, not because it's noise/front-loaded. Nothing wired live. See `.planning/quick/20260828-htf-pullback/SUMMARY.md`. |

## Blockers/Concerns

- **A $30 account cannot trade this strategy.** The stop is structural
  (`support - sl_buffer`), so its size comes from the market, not the account:
  across the 340 recorded backtest trades the stop distance per 0.01 lot was
  $5.33 min / $24.30 median / $59.78 p95 / $129.76 max. On $30 the median trade
  is 81% of the account and the p95 is a margin call. 0.01 lots is the broker
  minimum, so the position cannot be sized down. At the default 2% cap the
  `[risk]` gate blocks 340/340 setups at $30 (and at $250); the median setup
  needs ~$1,215 of balance to be taken at all, and full coverage of the
  distribution needs ~$6,500. The bot will now refuse these trades and log
  `reason=risk_exceeded` rather than place them — the account is safe, but it
  will also not trade at all until it is funded properly or the cap is
  knowingly raised.

- ~~The market-entry order path has never executed against a live broker.~~
  **Verified 2026-08-20 on demo account 476598932 (Exness-MT5Trial9).** One
  forced entry through the full engine path: `order_placed ticket=3110811764
  placed=True fill=4479.22 slippage=0.24`, closed immediately at 4478.944 for
  −$0.28 (the spread). `[live] mode` is still `dry-run` / `enabled = false`.

- **XAUUSDm quotes to 3 decimals, not 2.** `digits=3`, `point=0.001`. The
  adapter reads this from the symbol at order time so it rounds correctly, but
  `_round2` in the engine/CLI decision logging and the 0.01 equivalence
  tolerance in `PendingOrder.equivalent_to` still assume 2 dp. Cosmetic and
  dedup-only today, worth tidying. Also observed: `trade_stops_level=0` (no
  minimum stop distance), `filling_mode=3` (FOK|IOC), `volume_min/step=0.01`.

- **The container restart on 2026-08-20 broke the bridge, and the cause is
  structural — it will recur on every restart.** There are TWO MT5
  installations in the persistent Wine prefix:

    * `Program Files/MetaTrader 5 EXNESS/` — what `start.sh` auto-launches and
      keeps alive. Its `Config/` has NO `accounts.dat`: no account, so it
      opens the "Select a company to open an account with" wizard, which is a
      modal that blocks the API. `initialize()` returns -10005 IPC timeout.

    * `Program Files/MetaTrader 5/` — holds `Config/accounts.dat` (demo
      476598932 @ Exness-MT5Trial9). This is the one that has served every
      working session. It is NOT auto-started.
  Both were running earlier in the day, which is why the bridge worked and why
  `run_demo.sh` counted "6 terminals". Recovery needs no password — the saved
  session is on disk. Launch the account-holding terminal alongside:

      docker exec -d siliconmt5 bash -c 'cd /opt/wineprefix/drive_c && \
        DISPLAY=:100 exec wine "C:\Program Files\MetaTrader 5\terminal64.exe" /portable'

  then wait ~40s and re-run `./scripts/run_demo.sh check`. Note `mt5cfg.ini`
  stores no Login/Password, so there is no auto-login to fall back on. Two
  gotchas hit while diagnosing: `pkill -f "MetaTrader 5 EXNESS"` also matches
  the shell running it and kills itself, and the terminal reports stale bars
  for the first minute or two while it re-downloads history — preflight run
  too early shows an old `latest` bar.
  **Automated 2026-08-20:** `run_demo.sh` now detects the missing account
  terminal and starts it, then retries preflight until the feed is fresh.
  Verified end to end by killing the terminal: recovered in 58s unattended.

- ~~`run_demo.sh`'s terminal count is inflated~~ **Fixed 2026-08-20.** It
  counted the `start.exe /exec terminal64.exe` launcher wrapper as a terminal.
  That wrapper line also lacks "EXNESS", so it initially defeated the new
  account-terminal detection too — the check reported "running" with nothing
  running. Both now exclude it.

- **Preflight gated only bar COUNT, never bar FRESHNESS.** A just-started
  terminal serves a full 69 bars that are hours old; on 2026-08-20 it reported
  READY on bars 8 hours stale while account, connection and count were all
  green. A bot started then computes S/R from prices that no longer exist.
  Preflight now compares the newest closed bar against the terminal's own
  latest TICK (not the host clock, so no timezone assumption) and fails above
  15 min. Comparing tick-to-bar also cannot false-alarm when the market is
  closed: the tick goes stale alongside the bars, so the lag stays small.

- **SECURITY (2026-08-19): this machine hosted active malware from ~2026-07-04 to 2026-08-19.** A LaunchAgent (`com.luhbmchzztkfbxao`, RunAtLoad + KeepAlive) read its C2 address from a Polygon smart contract (`0xA3a603F8a454a9c905b4c579Bb72628F7C15C2A0`) and piped the response into `osascript` — the EtherHiding technique. Two stage-2 payloads were running. Persistence removed and processes killed; no second mechanism found. **02-06 is blocked until broker credentials, browser passwords, SSH keys, API tokens and wallets are rotated from a different, known-clean device.** Do not log into MT5 on this machine before that.
- Phase 2 is 5/6 plans done, 142 tests green. The remaining item (02-06) is the real-MT5 round-trip, now via the macOS Docker bridge — see `docs/macos-demo-setup.md` and the resume checklist in `.planning/quick/260819-nhq-mac-demo-mt5-bridge/SUMMARY.md`.
- Follow-up for Phase 2: net edge is thin (PF 1.29, avg R ≈ 0.14, fills at max(entry, open)). **Correction 2026-08-19:** the earlier claim that a ~$0.30 spread "would erode most of it" is wrong. Measured over the 339 closed trades, a flat $0.30 costs 9.4% of net (1079 → 978 pts, PF 1.288 → 1.258); median risk/trade is $24.11 so the spread is ~1.2% of risk. NOTE this is a first-order estimate (one spread subtracted per round trip) — win rate stayed pinned at 60.8% across every spread level, which shows it does NOT model SL/TP triggering on the bid, the effect that actually dominates. Treat 9.4% as an optimistic bound; a true figure needs bid/ask data the backtest does not have.
- `trading.spread_assumption` is dead config: declared in config.py and read by nothing in the strategy, backtest, or live engine. Documented as a v1 limitation, but the knob gives a false impression that spread is modelled.
- 2025-04 intra-file gap (73h) detected by the data-gap warning — investigate whether a histdata monthly file portion is missing (does not affect strategy correctness; expiry is window-based).
- ~~Real-data span is 13 months (full 2025 + 2026-07); 2026-08+ acquisition is a manual histdata.com download.~~ **Resolved 2026-08-20** for validation purposes: `scripts/fetch_broker_history.py` pulls M5 bars straight from the connected MT5 terminal — no download, no account, no auth, current to today. It returns XAUUSDm (Exness's own instrument and pricing), which is what the bot actually trades, rather than histdata's generic XAUUSD. 100,000 bars / 514 days (2025-03-24 → 2026-08-20) on the first run; the terminal serves ~50k per call and pages back one step further. histdata remains the only source for pre-2025-03 history.
- **The edge is thinner on the broker's own data than on histdata.** Same strategy, same params: histdata XAUUSD (339 trades) → PF 1.29, 60.8% win, avg R 0.135, max DD $271. Broker XAUUSDm (437 trades, longer and fresher span) → PF 1.22, 58.4% win, avg R 0.091, **max DD $588** on 0.01 lots. Stops are also wider on broker data (median $31.83 vs $24.30). Treat the histdata figures as the optimistic end of the range.

## SECURITY: the MT5 bridge is unauthenticated (2026-08-20)

The `siliconmetatrader5` RPC bridge takes no credentials — its client is
`MetaTrader5(host, port, keepalive, timeout)`, no token, no password, no TLS —
and it is published on `0.0.0.0:8001`. Anyone who can reach that port can place
orders on the account; it is an rpyc server (rpyc's default port is 18812), so
the exposure may extend past the MT5 API to code execution in the container.
Confirmed reachable over the LAN by running preflight against 10.42.0.248
instead of localhost.

This predates the Raspberry Pi question but that is what surfaced it — moving
the bot off-box makes exposing the port tempting. Mitigation: SSH-tunnel it
(`ssh -N -L 8001:localhost:8001 ...`) and bind the published port to
127.0.0.1 in the compose file. Note this machine hosted an infostealer until
2026-08-19.

## Session + time-stop study, and a calibration that reframes everything (2026-08-20)

Tested the London/NY hypothesis on gold. Bar times are server clock = UTC.

| session | trades | /day | win% | net R | R/day | t |
|---------|--------|------|------|-------|-------|---|
| all hours | 437 | 1.19 | 58.6% | 0.086 | 0.103 | 1.96 |
| Asia 00-08 | 303 | 0.83 | 58.7% | 0.080 | 0.066 | 1.51 |
| London 08-17 | 301 | 0.82 | 60.1% | 0.088 | 0.072 | 1.70 |
| NY 13-21 | 241 | 0.66 | 61.0% | 0.111 | 0.073 | 1.91 |
| **Lon+NY 08-21** | 330 | 0.90 | **61.5%** | **0.123** | 0.110 | **2.46** |
| overlap 13-17 | 194 | 0.53 | 59.8% | 0.076 | 0.040 | 1.18 |
| off-hours 21-08 | 362 | 0.99 | 57.5% | 0.053 | 0.053 | 1.11 |

Lon+NY is the best single window and the direction is a-priori sensible
(liquidity), which counts for more than a post-hoc winner. Win rate 58.6% ->
61.5%, gross R +39%.

Holds are long — median 6.7h, mean 12.6h, p90 28h, max 10 DAYS — so one trade
routinely occupies the single slot across whole sessions. A 12h time stop on
all hours gives the best R/day found anywhere (0.1227, t=2.21, n=651).
Combining the session filter WITH a time stop is worse than either alone. A 1h
stop is destructive (win rate 47-50%): the trade needs room to reach TP.

### The calibration that matters

Across this session ~39 configurations have been tried on this data: 17
instruments, 3 timeframes, 7 session windows, 12 session x time-stop. If the
strategy had ZERO edge, the best |t| among 39 tries would be 2.37 at the median
and 2.68 at the 75th percentile.

**Our best anywhere is |t| = 2.46 — pure noise beats that 42% of the time.**

So the entire search has produced nothing more extreme than chance routinely
produces. The instruments are correlated and the session windows overlap, so
the effective number of independent tries is below 39 and the true bar is a
little kinder — not kind enough to rescue 2.46. Treat every "improvement" found
today, including Lon+NY, as unproven.

`session_hours` and `max_hold_bars` are now backtest parameters (defaults
off, nothing changes unless passed). NOT wired into the live engine — there is
no evidence that would justify it.

## BTC on its own cent account + honest backtest (2026-08-27)

**Live:** BTC moved to its own CENT account **161700182 @ Exness-MT5Real21**
(USC, 3138.00, REAL, leverage 2000), its own terminal `C:\MT5-Gold\terminal64.exe`,
trading **BTCUSDc** (magic 77021). This implements quick task 007 on Windows:
risk isolated from gold's 161693049, per-account caps, per-account banking.
`config/config-btc.toml` updated: `symbol="BTCUSDc"`, `contract_size=1.0`
(backtest conversion; live risk reads trade_tick_value), header comments
rewritten for the new account. Preflight READY: median stop affordable at
**0.02 lots / 0.5% cap** — the `below_min_lot` refusal that plagued the old
$31.38 standard account is gone (that account could not carry BTC's ~$700-930
structural stop at minimum size).

`monitor_trade.py` fixed the same wrong-terminal bug as health_check/dashboard:
it now attaches per-config via `health_check._init_terminal`, so btc reports
161700182 and not gold's 161693049.

**Backtest (honest):** `scripts/fetch_broker_history.py` made Windows-native
(native MetaTrader5 first, bridge fallback, per-config terminal_path); pulled
`BTCUSDc` M5 to `data/processed/BTCUSDc_M5_broker.csv` (100,000 bars /
347 days, 24/7 no gaps). Backtest CLI gained `--m5-csv` to feed an already-M5
frame. New `config/config-btc-backtest.toml` (sl_buffer 0.10 = 10*point).

Result over 660 closed trades: **avg R −0.043, t=−1.20, PF 0.87, win 52.4%,
max DD $785** — no edge, reproduces the 2026-08-20 cross-instrument prior
(−0.033R/−0.049R "among the worst of seventeen"). rr=2.0 is worse (−0.103R).
Full report: `docs/btc-backtest-report.md`. The cent account fixes the SIZE
problem, not the EDGE problem — BTC is a machinery test, expected to lose.

## LIVE REAL-MONEY RUN — updated 2026-08-24 12:30 SAST

**Gold (cent) is the only live bot now.** BTC was stopped 2026-08-24 (both
positions closed manually, `com.joram.trading-bot-btc` agent booted out —
killing the bot alone is not enough, launchd respawns it). Current state:

    account   161693049 @ Exness-MT5Real21   ~3203 USC ($32.03)  trade_mode=2 REAL
    running   config/config-cent.toml  XAUUSDc  magic 77020 — launchd
              com.joram.trading-bot-cent (bot pid in output/live_cent.pid)
    stopped   config/config-btc.toml  BTCUSDc  magic 77021 — positions closed
              manually 2026-08-24, agent booted out (re-boot if wanted:
              launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.joram.trading-bot-btc.plist)

**User applied aggressive settings live 2026-08-24 12:32 SAST** (via tune_risk.py, warnings
shown and confirmed): `strategy.rr_multiple = 2.0` (TP = 2x stop) and
`[risk] max_loss_pct_per_trade = 20.0` (SL ≈ 20% of balance ≈ R115). Account-wide exposure if
every stop hits = **21%** (vs the 2% standing policy). This is the user's informed decision after
the measured 1.0/1.5/2.0 table (net R 0.091/0.147/0.230, win 58.4/49.3/43.8%, max DD
$589/$782/$990 — front-loaded, recent-half t≈0.7). The Friday-weekend gap exposure at 2:1 is
tripled (21% of trades hold >2.5 days) and NO weekend/entry guard is active yet (option-a from
quick task 002 still pending).

### First real-money round trip — CLOSED, +0.43R

    DEAL 381064244  BUY  0.01 XAUUSDc @ 4605.799   17:38 UTC   "gold-cent"
    DEAL 381262433  SELL 0.01 XAUUSDc @ 4624.062   19:02 UTC   "manual-close"

    entry 4605.799  sl 4563.311  tp 4645.759   risk 42.49 USC = 1.36% of balance
    exit  +18.263 points = +18.30 USC = R2.93 = +0.43R
    balance 3121.00 -> 3139.30 USC

Closed by hand at +0.43R rather than left to reach TP at 4645.759. That was the
weekend-gap decision, not a signal call: gold shuts Friday 21:00 UTC and a
broker-side stop cannot protect against a Sunday opening gap that jumps through
it. It cost roughly 0.57R of upside that may or may not have arrived.

**One winning trade proves the machinery, not the strategy.** Placement, tick-
value sizing, account-currency risk, the caps, and now the close path have all
executed correctly against a real account. The edge is still measured negative.

### The handover was done manually at 19:02, ~1h early

The original schedule (close 20:01, BTC start 20:02) was executed early via
`scripts/close_gold_start_btc.sh`, which does the same steps in the same order
and cancels the timers that would otherwise have fired later. The ordering is
the whole point of that script — see its header comment.

### How it was started (NOT via run_demo.sh)

`run_demo.sh` calls `preflight_demo.py`, which **refuses REAL accounts by
design** — that guard is intact and should stay that way. The bot was launched
directly, detached, by `/tmp/start_cent.sh`. The equivalent preflight checks
were run read-only first: bridge up, trade_allowed=True, 69/69 bars, feed 5 min
fresh, sizing verified across every stop percentile.

### To stop early

`kill $(cat output/live_cent.pid)` kills the bot, but launchd respawns it
within ~60s. To stop for good (as of 2026-08-24):

    launchctl bootout gui/$(id -u)/com.joram.trading-bot-cent
    # restore: launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.joram.trading-bot-cent.plist

(Use `-btc` for the Bitcoin bot.) No manual pidfile killing stops a
launchd-supervised bot permanently.

**Both bots are now launchd-supervised (2026-08-24, quick task 260824-launchd).**
`com.joram.trading-bot-btc` and `com.joram.trading-bot-cent` run
`scripts/launchd_run_live.sh btc|cent` with RunAtLoad + KeepAlive, so BTC and
gold survive reboots and crashes unattended. Stack bring-up (colima → container
→ ACCOUNT terminal → `preflight_live.py --real-account`) is handled before the
supervisor starts. The notes below ("To stop early", "How it was started") are
the pre-launchd arrangement.

### Guard rails currently active

cap 2%/trade (~62 USC ~ $0.62) · daily halt 6% · min_rr 0.5 · one position at a
time · sizing floors to the broker lot grid and refuses below minimum.

### What is NOT proven

The strategy. Measured edge across 6,541 trades is **negative net of spread**
(-0.0156R), the best of ~39 tested configurations was weaker than noise
typically produces, and today's most promising fix (TP-from-fill) made things
worse. What today proved is that the *machinery* is correct — sizing, currency,
caps — not that this makes money. One green trade is not evidence.

## Weekend schedule — EXECUTED EARLY at 19:02 UTC

Originally four scheduled events; run by hand instead, in the same order, an
hour ahead. What actually happened:

    19:02 UTC  timers cancelled, gold bot killed, position closed, BTC started
    Sun 06:00  BTCUSDc bot killed                  (timer still armed, pid 62061)

Plus `caffeinate -dimsu` (pid 49066) so a closed lid does not kill the overnight
run. The Sunday timer polls the wall clock rather than sleeping once for the
whole interval — a single long `sleep` overruns by however long the machine was
asleep.

**Two orderings in `scripts/close_gold_start_btc.sh` are load-bearing.**

*Bot dies before the close.* An earlier draft scheduled the close for 20:00:00 —
the same second the gold bot's stopper fired, and an M5 bar boundary. If the
close had won that race the bot would still have been alive, seen no open
position, found its one-position guard satisfied, and could have placed a FRESH
gold order seconds before dying, leaving an unattended position over a weekend
when gold is shut. The script now kills the bot first and *verifies it is dead*,
refusing to close if it is not.

*Timers cancelled before anything else.* The 20:02 timer would otherwise have
started a SECOND BTC bot on magic 77021 an hour later. Two bots sharing a magic
each mistake the other's position for their own and defeat both dedup guards.

    cancel everything   pkill -f wait_until
    stop BTC early      kill $(cat output/live_btc.pid)
    check on it         tail output/live_btc.log ; cat output/close_gold.out

`scripts/close_position.py` is the close path. It is deliberately NOT wired into
the engine — the live engine still has no close capability at all, only
placement. Closing stays a human decision, so the script refuses to guess: it
takes an explicit `--ticket` and needs `--confirm` to send anything. If the
position already hit SL or TP it reports "nothing to close" and exits 0.

### Why Bitcoin, and what it does not prove

BTCUSDc trades 24/7, which is the only reason to run it — gold is shut Friday
21:00 to Sunday 21:00 UTC. Verified live: contract 0.01, min lot 0.01,
tick_size 0.01, tick_value 0.01, spread 10.00. Median stop 759 costs 7.59 USC at
minimum size: **0.24% of balance**, four times cheaper than gold.

Backtested on real broker bars, three windows ending 2026-08-21:

| window   | price move | trades | win% | avg R net | P&L 0.01 lot | buy & hold |
|----------|-----------:|-------:|-----:|----------:|-------------:|-----------:|
| 7 days   |     +22.3% |      8 | 100% |   +0.808  |   +86.40 USC | +140.67 USC |
| 69 days  |     +21.4% |     83 | 54.2%|   −0.050  |   +30.69 USC | +135.81 USC |
| 7 months |     −12.9% |    210 | 52.9%|   −0.049  |   −97.04 USC | −114.61 USC |

The 7-day window is a melt-up, not an edge — t=20.8 on n=8. The 210-trade number
is the real one and it reproduces the −0.033R the cross-instrument study found.

The trap worth naming: over the 69-day uptrend the bot made money in POINTS
(+30.69 USC) while its R was negative, because it is long-only and a rising
market pays it without any edge. Buy-and-hold made +135.81 USC over the same
stretch. If the thesis is "bitcoin goes up", holding beats running this on it by
4x with no spread paid 83 times. Judge Sunday's result on R per trade, not on
whether the balance went up.

### Loose ends for the next session

- Bitcoin: now LIVE for the weekend — see "Weekend schedule" above. Still
  expected to lose; it is a machinery test, not an edge test.

- The M1 and Lon+NY demo experiments never completed a session; both configs
  and launchd agents still exist but are booted out.

- Port 8001 collides with a uvicorn dev server on this machine. Consider moving
  the bridge to 18001 (needs recreating the container).

- Algo Trading resets when switching accounts in the terminal — always re-check
  `terminal_info().trade_allowed` after a login.

## TP-from-fill: tested, does NOT work (2026-08-21)

The most promising structural improvement found in this project, proposed off
live fill data rather than parameter search — and it fails.

Winners averaged 0.859R while losers paid 0.986R. The cause is mechanical: TP
is measured from the REFERENCE entry while the fill lands above it, so the
target sits closer than 1R and the stop further. Re-anchoring TP on the fill
restores a true 1:1.

It did exactly that, and lost money anyway:

| XAUUSDm | trades | win% | avgWin | avgLoss | net R | t |
|---|---|---|---|---|---|---|
| TP from reference | 437 | 58.6% | 0.859 | -0.986 | **0.086** | 1.96 |
| TP from fill | 393 | 53.9% | **0.997** | -1.000 | **0.069** | 1.37 |

Winners went to a full 1.000R as predicted. But a target further away is hit
less often — win rate 58.6% -> 53.9% — and the lost win rate outweighs the
gained R per winner. 0.095 -> 0.076 on the raw decomposition.

So the 0.86R "drag" is not a defect to be fixed; it is the price of a target
close enough to be reached. USTEC nudged up (0.047 -> 0.069) but well inside
noise. **The EURJPY row from that run is invalid** — the script applied gold's
$0.26 spread to a JPY cross whose median stop is 0.381, making the cost 68% of
risk instead of ~4%.

`tp_from_fill` stays as a backtest parameter, defaulting False, so the tested
hypothesis is recorded rather than lost. NOT wired into the live engine.

## Cent account: gold IS tradeable at R500 (2026-08-21)

Account **161693049 @ Exness-MT5Real21**, currency **USC**, balance **3121 USC**
($31.21), trade_mode 2 (REAL), leverage 1:2000.

`XAUUSDc` has **trade_contract_size 1.0** (one ounce per lot, not 100) and the
balance is denominated in cents, so the smallest position — 0.01 lot = 0.01 oz
— risks **31.83 USC = 1.02% of balance**, where the same trade on a standard
account was 103% and unplaceable. Confirmed two ways: manual USD->USC
conversion, and the broker's own `trade_tick_value`.

### Risk now comes from tick_value, not contract_size

`[trading] contract_size = 100` was correct only for standard-account gold, and
the engine also compared a USD-denominated loss against a USC balance. Both
100x, in opposite directions. **On XAUUSDc they cancel exactly** — tick_value /
tick_size is 100 USC per 1.0 of price per lot, the same number — which is why
this was invisible. On anything else it is not: BTCUSDc would have been sized
100x wrong.

`SymbolRisk` (tick_size, tick_value, lot grid) is now part of the BrokerClient
contract, and `money_risk()` = (stop / tick_size) x tick_value x lots gives
account currency directly — no contract size, no FX. The lot grid also comes
from the symbol rather than config.

Read-only check against the live account, cap 2% = 62.42 USC:

| stop (USD/oz) | lots | real risk | % balance |
|---|---|---|---|
| min 5.86 | 0.10 | 58.60 USC | 1.88% |
| p25 21.48 | 0.02 | 42.96 USC | 1.38% |
| median 31.83 | 0.01 | 31.83 USC | 1.02% |
| p75 47.10 | 0.01 | 47.10 USC | 1.51% |
| p95 90.03 | — | SKIP, below min lot | — |

So ~90% of setups are tradeable and the widest are correctly refused.

`config/config-cent.toml` holds this, deliberately at **mode="demo"**. The cent
account, tick-value sizing and live mode have none of them executed yet.
Algo Trading has been enabled in the terminal (`trade_allowed: True`).

## Risk is now priced at the MARKET, not the reference level (2026-08-20)

The risk cap was never actually the cap. `position_size` and the gate both
measured risk as `reference_entry - sl`, but a market buy crosses the ASK — and
`detect_setups` only fires once price has closed ABOVE resistance, so the ask
is *always* past the reference. Realised risk therefore exceeded the cap on
every trade, and by more the tighter the stop.

Caught on live M1 trade 3114935513: sized for $49.10 against a $50.42 budget,
actually risked **$56.97 — 13% over its own 1% cap**. The M5 trade was ~4% over
for the same reason. Same ~$1.6 slippage; it is 4% of an M5 stop and 16% of an
M1 one.

Fixed by adding `quote(symbol)` to the BrokerClient contract and pricing both
sizing and the gate off `ask - sl`. Replaying the live trade through it: 0.04
lots risking $45.57, inside budget, where the old path took 0.05 lots at
$56.97. `sl`/`tp` deliberately keep the strategy's levels — the backtest also
books them off the reference and fills at the market, so leaving them alone is
what keeps live and simulated comparable. Only the risk arithmetic moved.

Also added `[risk] min_rr` (default 0.5): refuse a setup whose reward:risk has
already decayed below that by the time we can act. The levels imply 1:1; the M1
trade opened at 0.72R. Past some point the trade on offer is not the trade that
was tested and taking it is chasing. 184 tests.

## Live A/B/C on demo 476598932 (M5 17:52, M1 17:52, Lon+NY 21:14)

Three bots, one account, one instrument. Each isolated by magic number, config,
decision log and pidfile; all three launchd-supervised and each verified by
SIGKILL (recovered in 45s on the correct config).

| | config | tf | magic | log | session | cap |
|---|---|---|---|---|---|---|
| M5 | config.toml | M5 | 77001 | live.log | all | 1% |
| M1 | config-m1.toml | M1 | 77002 | live_m1.log | all | 1% |
| Lon+NY | config-lonny.toml | M5 | 77003 | live_lonny.log | 08-21 UTC | 1% |

    scripts/run_demo.sh start|stop|status                 # M5
    INSTANCE=m1 scripts/run_demo.sh start|stop|status     # M1
    INSTANCE=lonny scripts/run_demo.sh start|stop|status  # Lon+NY

Lon+NY differs from M5 in exactly two places — magic and `session_hours` — so
the comparison isolates the filter and nothing else.

**Account risk is now 3%, not 2%.** Three bots at 1% each, all sizing off the
same balance, all able to hold at once. 1% is the floor that still works: at
0.67% (3 x 0.67 = 2%) an M5 stop of ~$34/unit needs 0.0099 lots on this
balance, which floors to zero and every M5 setup would be skipped as
`below_min_lot`. Fine on demo; must be revisited before real money.

Compare **R per trade**, not P&L — the caps differ from earlier runs and R is
size-independent.

## Live A/B: M1 vs M5, started 2026-08-20 17:52

Two bots now run side by side on demo 476598932, so the timeframe question
gets settled by real fills instead of by backtest argument:

| | config | timeframe | magic | decision log | cap |
|---|---|---|---|---|---|
| M5 | config.toml | M5 | 77001 | output/live.log | 1% |
| M1 | config-m1.toml | M1 | 77002 | output/live_m1.log | 1% |

Both supervised by launchd (`com.joram.trading-bot-demo`, `-m1`), both verified
by SIGKILL: recovered in 45s with the correct config each.

    scripts/run_demo.sh start|stop|status              # M5
    INSTANCE=m1 scripts/run_demo.sh start|stop|status  # M1

**Caps are 1% each, not 2%.** Both bots size off the SAME account balance and
can hold positions simultaneously, so the account's total risk is the SUM of
their caps. Put config.toml back to 2.0 when the experiment ends. The daily
loss limit also reads account balance, so either bot's losses can halt the
other — conservative and correct: the limit is about the account's day.

Expect M1 to lose. The point is a measurement, not a hope; see the finding
below. Compare realised R per trade and R/day between the two logs.

### Concurrency bug found while setting this up

Starting is not atomic. `run_demo.sh start` checked the pidfile, then ran
`check` (tens of seconds: terminal launch, preflight retries), and only then
launched and claimed the pidfile. The launchd agent's KeepAlive started its own
bot inside that window, which left **three bots on magic 77001** at once. No
positions were open so nothing was lost, but two bots on one magic either see
each other's position as their own and both stop trading, or both place before
either notices.

Fixed with an atomic `mkdir` lock shared by both entry points, plus a re-check
of the pidfile immediately after `check` and before claiming the slot.

## Timeframe Finding (2026-08-20): M1 is materially WORSE

Tested M1 / M5 / M15 on one common window (2026-05-11 -> 2026-08-20) so bar
size is not confounded with period — the first pass compared M1 over 36 days
against M15 over 551 and flattered M15 badly.

| TF | trades | /day | med stop | gross R | cost R | net R | **R/day** | t |
|----|--------|------|----------|---------|--------|-------|-----------|---|
| M1 | 370 | 5.13 | $15.73 | **-0.075** | 0.017 | **-0.092** | **-0.472** | -1.93 |
| M5 | 74 | 1.03 | $34.17 | +0.038 | 0.008 | +0.031 | +0.032 | 0.29 |
| M15 | 37 | 0.51 | $68.53 | -0.095 | 0.004 | -0.099 | -0.051 | -0.69 |

M1 fails twice over. Its gross edge is already NEGATIVE before costs (-0.075),
because a "breakout" on a 1-minute bar is mostly noise — there is no structure
there to break. And its stops are half the size ($15.73 vs $34.17), so the same
$0.26 spread costs twice as much per trade (0.017R vs 0.008R). Trading 5x more
often then multiplies the loss: **-0.47 R/day against M5's +0.03**.

Note M1's t = -1.93 on 370 trades is the closest to significant anything has
come in this project — and it points the wrong way. More trades per day cannot
be bought by shortening the bar; the setup frequency is a property of the
signal, and speeding it up destroys what little edge exists.

M15 also flipped negative in this window after being +0.170 over 551 days,
which is more evidence of instability rather than a case for M15.

## Multi-Instrument Finding (2026-08-20)

The signal is instrument-agnostic; the code around it is not. Ran the strategy
across all 17 symbols on the Exness demo (M5, `sl_buffer` scaled per
instrument as `10 * point` — the committed `0.01` is 10 points on gold but 100
PIPS on EURUSD).

Ranked by avg R net of one spread per round trip, the leaders were EURJPY
(+0.135), GBPJPY (+0.121), USTEC (+0.113), US500 (+0.111), with XAUUSD 5th
(+0.056) and 9 instruments negative. **Do not act on that ranking.** At ~100
trades and R-multiple std ~0.9 the standard error on mean R is ~0.09 — the
same size as the edge. Every instrument's 95% CI contains zero; the best
(EURJPY) is t=1.95.

Split-sample test (first half vs second half of each instrument's history):
correlation between halves **+0.27** (needs ~0.53 for significance at n=14),
and **6 of 14 instruments flipped sign**. Close to what shuffling produces.

**XAUUSD itself flipped: +0.092 first half, −0.005 second half.** The
instrument the live plan targets showed no edge in the recent half of its own
data. Consistent with its numbers moving 45% between windows (0.091 over 514
days vs 0.063 over 154). EURJPY and GBPJPY were positive in both halves — the
only candidates worth further work, and still not individually significant.

Switching `[live] symbol` alone would NOT work. `trading.contract_size = 100`
is gold's oz/lot; true contract sizes span 1 to 100,000 and quote currencies
span five. The risk gate would compute $0.38 where the real risk is $2.40
(EURJPY), $0.00 where it is $2.19 (EURUSD), and $209.84 where it is $2.10
(USTEC — blocking a $2 trade). Wrong in both directions on everything except
gold. Genuine multi-instrument support needs: contract size from
`symbol_info.trade_contract_size`, `sl_buffer` scaled by `point`,
quote→account currency conversion for JPY/CHF/CAD crosses, the 2-dp
assumptions in `_round2` and `PendingOrder.equivalent_to` fixed, and
per-symbol magic numbers.

## Session Continuity

Last session: 2026-08-24 (quick task 006 complete — bank-the-profits helper: read-only banking CLI
`scripts/bank_profits.py` + 8 tests, 278 suite green; first-run base pinned to the live balance
3205.64 USC; no ledger write yet — banking events recorded via `--confirm` as profits clear the base)
Stopped at: Quick task 006 done. `python scripts/bank_profits.py` shows balance/base/bankable;
`--base <USC>` repins the base stake; `--confirm` appends one ledger line + prints the manual
Exness-portal withdrawal instruction. Run with `.venv/bin/python`.
Resume file: None

ALL STOPPED 2026-08-21 (user left for the office). Three launchd agents booted
out, three bots stopped, siliconmt5 container stopped, port 8001 free, demo
account FLAT — no positions, no pending orders.

Demo result over the run: **$5,000.00 -> $5,121.13 (+$121.13)** on 4 closed
deals — 3 take-profits and one -$0.28 close probe. n=3 real trades. That is
not evidence of edge; a 58%-win strategy throws off runs like this constantly
while still losing money over a large sample, and the 6,541-trade measurement
still puts the edge negative net of spread.

| closed (UTC) | bot | vol | price | P&L | reason |
|---|---|---|---|---|---|
| 08-20 05:53 | M5 | 0.01 | 4478.944 | -0.28 | close probe |
| 08-20 15:17 | M5 | 0.01 | 4539.382 | +42.73 | TP |
| 08-20 19:13 | M1 | 0.05 | 4526.496 | +41.22 | TP |
| 08-21 04:21 | M1 | 0.02 | 4544.814 | +33.44 | TP |

To resume: `docker start siliconmt5`, wait for health, then
`scripts/run_demo.sh start` (+ `INSTANCE=m1`, `INSTANCE=lonny`), and re-bootstrap
the three agents from ~/Library/LaunchAgents if you want supervision back.

PREVIOUS (superseded) — SUPERVISED BY LAUNCHD as of 2026-08-20. `com.joram.trading-bot-demo` is
installed in ~/Library/LaunchAgents and bootstrapped, so the bot survives
crashes and reboots. Verified by SIGKILLing it: launchd re-ran the full
bring-up (account terminal + freshness gate) and had a new bot polling 45s
later. It also stands down cleanly when a manual `run_demo.sh start` bot is
already running — two bots on the same account and magic would open two
positions per setup, since the one-trade-at-a-time guard only reads the broker.

`run_demo.sh stop` kills the bot but launchd restarts it within ~60s. To stop
for good:  launchctl bootout gui/$(id -u)/com.joram.trading-bot-demo

NOT verified: the `colima start` branch of launchd_run.sh. Colima was already
running for every test, so the true cold-boot path (VM start from a launchd
context, several minutes under QEMU) has never actually executed. That is the
remaining unknown for reboot survival.

PREVIOUS PAUSE STATE (superseded). Bot not running, no launchd agent loaded (nothing will
auto-restart it), demo account 476598932 flat — no positions, no pending
orders, balance $4,999.72. Working tree clean, 167 tests green. The siliconmt5
Docker container is still up; harmless to leave, `docker stop siliconmt5` if
you want it down too.

To resume:
    ./scripts/run_demo.sh check      # preflight: bridge, account, bars
    ./scripts/run_demo.sh start      # detached; survives the shell
    ./scripts/run_demo.sh status     # pid + last 3 log lines
    tail -f output/live.log

Next action — THREE OPEN DECISIONS, in the order they should be taken:

1. **Whether to trade this at all.** Two independent lines of evidence now say
   the edge is thin relative to noise: broker-native gold gives PF 1.22 / avg R
   0.091 (vs histdata's 1.29 / 0.135), and the cross-instrument split test
   scrambles. Gold flipped sign in the recent half of its own data. Worth
   deciding before any funding question.

2. **If yes — funding.** $30 cannot trade this (0/438 setups pass the 2% gate;
   0.01 lots is the broker minimum). Median setup needs ~$1,215. Separately,
   max drawdown on the broker data is **$588 at 0.01 lots**, which the account
   must absorb regardless of the per-trade cap.

3. ~~Still unproven: the bot has never placed an order of its own accord.~~
   **DONE 2026-08-20 16:40.** First unprompted trade, end to end:
   `setup_detected` on bar 14:35 → `order_placed` ticket 3113739731,
   fill 4496.648, slippage +1.77. Closed 15:17:49 at TAKE PROFIT 4539.382 for
   **+$42.73** after 37 minutes. Balance 4999.72 → 5042.45.

   It matched the model closely. The backtest books this trade at exactly
   1.000R; live realised **0.924R** (−7.6%), because SL and TP are placed off
   the REFERENCE entry while the fill lands above it — so slippage pushes the
   stop further away AND the target closer, charging twice. That is not an
   unmodelled divergence: the backtest already fills at max(entry, open) and
   books winners below 1.0R (n=258 winners, mean 0.848R, median 0.903R). The
   live 0.924R sits at the 57th percentile of them.

   **n=1.** This proves the plumbing, not the edge. The 6,541-trade analysis
   still says the edge is negative net of spread.

Optional follow-up: is the EURJPY/GBPJPY result real? Needs longer history and
walk-forward rather than a single split. That decides whether building the
instrument-agnostic contract layer is worth it.
| 260827-btc-tp | BTC live TP raised: strategy.rr_multiple 1.0 -> 1.5 (config-btc.toml), user-chosen 'a bit higher' | 2026-08-27 | done - single-line config edit; takes effect on next placement; restart required if bot running |
