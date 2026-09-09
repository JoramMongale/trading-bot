---
phase: 004-tp-sl-ratio
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/trading_bot/backtest/engine.py
  - src/trading_bot/cli.py
  - tests/test_backtest.py
  - scripts/compare_rr_multiple.py
  - src/trading_bot/live/engine.py
  - scripts/tune_risk.py
  - tests/test_live_engine.py
  - tests/test_tune_risk.py
autonomous: false
user_setup: []

must_haves:
  truths:
    - "Backtest TP distance scales with rr_multiple: rr=2.0 arms tp = entry + 2*(entry - sl); rr=1.0 (default) reproduces the existing 1:1 results exactly"
    - "The backtest CLI honours [strategy] rr_multiple from the config and logs it on every run"
    - "A comparison backtest at rr_multiple 1.0 / 1.5 / 2.0 runs on the broker-native XAUUSDm M5 data (data/processed/XAUUSDm_M5_broker.csv) and writes trades.csv + stats per run"
    - "The user is shown a win-rate / net-R / max-drawdown table for 1.0 / 1.5 / 2.0 and decides whether 2:1 is worth wiring live BEFORE any live code changes"
    - "The live engine computes TP from cfg.strategy.rr_multiple — only after the checkpoint approves"
    - "scripts/tune_risk.py can view and edit [strategy] rr_multiple with the same validation and confirmation gates as [risk]"
    - "The running live bot (launchd com.joram.trading-bot-cent) is NOT restarted and its config is NOT changed by this plan; [risk] max_loss_pct_per_trade stays untouched"
  artifacts:
    - path: "src/trading_bot/backtest/engine.py"
      provides: "rr_multiple parameter on run_backtest; tp = entry + rr_multiple*(entry - sl)"
      contains: "rr_multiple"
    - path: "src/trading_bot/cli.py"
      provides: "passes cfg.strategy.rr_multiple into run_backtest and logs it in backtest_run"
      contains: "rr_multiple=cfg.strategy.rr_multiple"
    - path: "scripts/compare_rr_multiple.py"
      provides: "runs run_backtest + trade_stats at 1.0/1.5/2.0 on broker-native gold, prints comparison table, writes per-run CSV+JSON"
    - path: "output/rr_multiple_study/"
      provides: "generated per-run trades_{rr}.csv and stats_{rr}.json"
    - path: "src/trading_bot/live/engine.py"
      provides: "tp = entry + cfg.strategy.rr_multiple * (entry - sl) (post-checkpoint only)"
      contains: "rr_multiple"
    - path: "scripts/tune_risk.py"
      provides: "dotted table.key editing incl. strategy.rr_multiple with validation, --yes gate, load_config check, launchd restart contract"
  key_links:
    - from: "src/trading_bot/cli.py"
      to: "src/trading_bot/backtest/engine.py"
      via: "run_backtest(rr_multiple=cfg.strategy.rr_multiple)"
      pattern: "rr_multiple="
    - from: "src/trading_bot/backtest/engine.py"
      to: "src/trading_bot/live/engine.py"
      via: "identical tp arithmetic tp = entry + rr_multiple*(entry - sl) (STRAT-03 parity)"
      pattern: "rr_multiple.*entry"
    - from: "scripts/compare_rr_multiple.py"
      to: "data/processed/XAUUSDm_M5_broker.csv"
      via: "loads broker-native M5 bars (the instrument the bot trades, freshest span)"
    - from: "scripts/tune_risk.py"
      to: "src/trading_bot/config.py"
      via: "edited in-memory result must pass load_config before any write"
      pattern: "load_config"
---

<objective>
Wire the TP/SL ratio knob (`rr_multiple`) into the engines and decide, on real backtest numbers, whether a 2:1 reward:risk is worth running on the live gold bot.

Purpose: The user's mental model is "TP 40%, SL 20% of stake" — exactly `rr_multiple = 2.0`. `rr_multiple` already exists in config.py (validated, default 1.0) but is used NOWHERE: both the backtest and live engines hardcode `tp = entry + (entry - sl)` (1:1). Before any live change, the honest measurement MUST come first: the TP-from-fill study showed re-anchoring the target further away dropped win rate 58.6% -> 53.9% and net R 0.086 -> 0.069. A 2:1 target is a much bigger move in the same direction and is expected to be materially worse. This plan measures that expectation and stops for a decision before touching the live engine.

Sequencing contract (load-bearing):
1. Wire `rr_multiple` into the BACKTEST engine + CLI only.
2. Run backtests at 1.0 (baseline), 1.5, 2.0 on the best gold data available.
3. STOP at a checkpoint presenting the win-rate / net-R / drawdown table for 1.0 / 1.5 / 2.0.
4. Only after the checkpoint approves: wire `rr_multiple` into the live engine and expose it in `scripts/tune_risk.py`.

Safety constraints (do NOT violate):
- The gold bot is running RIGHT NOW on real money via launchd `com.joram.trading-bot-cent` (config/config-cent.toml). Do NOT restart it. Do NOT write config-cent.toml. Task 4 makes the knob available and tested; applying a new ratio to the live bot stays a user act via tune_risk.py (with its --yes gate and restart contract).
- Do NOT touch `[risk] max_loss_pct_per_trade` (the "SL 20%" half of the user's framing). That stays a user decision via tune_risk.py; this task is about the TP ratio only.
- Do NOT edit `src/trading_bot/live/engine.py` before the checkpoint is passed.

Output: rr_multiple flows through the backtest; a measured 1.0/1.5/2.0 comparison on broker-native gold; a user decision recorded; live engine + tune_risk extended (if approved).

Reference runs and expected shape:
- Baseline (rr=1.0, broker XAUUSDm, all hours): 437 trades, 58.6% win, net R 0.086, max DD $588 (STATE.md). The 1.5/2.0 rows should show a lower win rate, a higher avg win in R, and — per the TP-from-fill precedent — a likely lower net R.
</objective>

<execution_context>
@/Users/joram/.config/opencode/get-shit-done/workflows/execute-plan.md
@/Users/joram/.config/opencode/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/quick/003-risk-tuning-script/003-SUMMARY.md
@src/trading_bot/backtest/engine.py
@src/trading_bot/cli.py
@src/trading_bot/live/engine.py
@scripts/tune_risk.py
@config/config-cent.toml
@tests/test_backtest.py
@tests/test_live_engine.py
@tests/test_tune_risk.py

Data source (broker-native, freshest, and the instrument the bot actually trades — preferred over histdata per task brief):
@data/processed/XAUUSDm_M5_broker.csv

Note on STATE.md: "The edge is thinner on the broker's own data than on histdata. Same strategy, same params: histdata XAUUSD (339 trades) -> PF 1.29, 60.8% win, avg R 0.135; Broker XAUUSDm (437 trades) -> PF 1.22, 58.4% win, avg R 0.091, max DD $588." The comparison below runs on the broker data so the decision measures what the bot actually trades.
</context>

<tasks>

<task type="auto">
  <name>Task 1: Wire rr_multiple through the backtest engine and CLI</name>
  <files>src/trading_bot/backtest/engine.py</files>
  <files>src/trading_bot/cli.py</files>
  <files>tests/test_backtest.py</files>
  <action>
    Backtest engine (src/trading_bot/backtest/engine.py):
    - Add `rr_multiple: float = 1.0` to the `run_backtest` signature, directly after `sl_buffer` (default 1.0 keeps every existing call/behaviour unchanged).
    - Line ~237: replace `tp = entry + (entry - sl)` with `tp = entry + rr_multiple * (entry - sl)`.
    - Update the comment at line ~234 ("exact 1:1 R:R (STRAT-03)") to state the target is `rr_multiple` R:R, default 1:1, configurable via `[strategy] rr_multiple`.
    - Update the docstring: document `rr_multiple` (target distance = rr_multiple x stop distance; the 1:1 default is the only configuration that has been measured live).
    - Leave the `tp_from_fill` branch (line ~216) untouched — it re-anchors on the fill and is orthogonal to rr_multiple. Exit logic already reads `order["tp"]`, so no other loop changes are needed.

    CLI (src/trading_bot/cli.py):
    - Pass `rr_multiple=cfg.strategy.rr_multiple` to the `run_backtest(...)` call (line ~429).
    - Add `rr_multiple=cfg.strategy.rr_multiple` to the `backtest_run` log_decision fields (line ~378) so every backtest run is reproducible from the log.

    Tests (tests/test_backtest.py):
    - Add `test_rr_multiple_arms_farther_tp`: reuse the non-gap frame from `test_exact_one_to_one_rr_on_record` (opens start [100.00, 100.10, 100.60, 100.90, 100.50, 100.15, 100.80, 101.00, ...]) and assert `run_backtest(df, rr_multiple=2.0)` produces `t["tp"] == pytest.approx(101.00 + 2 * (101.00 - 100.09))` i.e. 102.82, and `run_backtest(df, rr_multiple=1.5)` gives tp == 102.365. Do NOT assert the exit — with the far target the trade may exit OPEN; assert only the armed `tp` (and that `sl` is unchanged).
    - Do NOT modify the existing golden/1:1 tests: they must stay green unchanged, proving the default is behaviour-identical.

    Do NOT touch live/engine.py, tune_risk.py, or any config file in this task.
  </action>
  <verify>
    `python -m pytest tests/test_backtest.py tests/test_cli.py -q` passes (new + existing tests, including the default-1:1 golden tests).
    Then full suite: `python -m pytest tests/ -q` stays green (246 existing + new).
  </verify>
  <done>
    `run_backtest` accepts rr_multiple (default 1.0) and arms tp = entry + rr_multiple*(entry - sl); the CLI passes cfg.strategy.rr_multiple and logs it; rr_multiple=1.0 reproduces the exact previous 1:1 outputs; suite green.
  </done>
</task>

<task type="auto">
  <name>Task 2: Backtest comparison 1.0 / 1.5 / 2.0 on broker-native gold</name>
  <files>scripts/compare_rr_multiple.py</files>
  <files>output/rr_multiple_study/</files>
  <action>
    Create `scripts/compare_rr_multiple.py` (committed, reusable):
    - Load `config/config-cent.toml` via `load_config` for the [strategy] params (fractal_left, fractal_right, sr_lookback, sl_buffer) and [trading] contract_size/lot (for USD stats). Import `run_backtest` and `trade_stats` from the same shared modules the CLI uses (SAFE-01 — same strategy code, no copy).
    - Load `data/processed/XAUUSDm_M5_broker.csv` as the M5 DataFrame (broker-native XAUUSDm, 100,000 bars, 2025-03-24 -> 2026-08-20 — the freshest and the instrument the bot actually trades; do NOT use the histdata M1 files or the data range in config, which is the older/coarser histdata span).
    - For each rr in (1.0, 1.5, 2.0):
      - `run_backtest(m5, fractal_left=..., fractal_right=..., sr_lookback=..., sl_buffer=..., rr_multiple=rr)`
      - `trade_stats(trades, contract_size=..., lot=...)`
      - Write `output/rr_multiple_study/trades_{rr}.csv` (same TRADE_COLUMNS shape as the CLI) and `output/rr_multiple_study/stats_{rr}.json`.
    - Print a markdown comparison table, one row per rr: `rr_multiple | trades | win% | avg win R | avg loss R | net R | profit factor | max DD USD`. Compute avg win/loss R from the trade records (exit_reason TP vs SL; OPEN trades excluded from wins/losses exactly as the backtest conventions do — the stats dict's win_rate/net already follow this).
    - Print the run context line (data file, span, config) for reproducibility.
    - Exit non-zero on missing data file (message naming the path and suggesting `scripts/fetch_broker_history.py`).

    Run it. Capture the printed table verbatim — it feeds the Task 3 checkpoint.

    Interpretation aid (from STATE.md): the 1.0 row should land near 437 trades / ~58% win / net R ~0.086 / max DD ~$588. Farther targets should drop win rate and raise avg win; per the TP-from-fill precedent the net R is expected to fall. Do NOT editorialise in the table — the checkpoint presents the numbers, the user decides.
  </action>
  <verify>
    `python scripts/compare_rr_multiple.py` exits 0; `ls output/rr_multiple_study/` shows trades_1.0.csv, trades_1.5.csv, trades_2.0.csv, stats_1.0.json, stats_1.5.json, stats_2.0.json; the 1.0 stats approximately reproduce the STATE.md broker baseline (437 trades, win ~58%, net R ~0.086 — small differences are fine, note them).
  </verify>
  <done>
    A reproducible script exists and three comparison runs are on disk with a printed 1.0/1.5/2.0 table (trades, win%, avg win/loss R, net R, PF, max DD) on broker-native gold data.
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <what-built>
    The rr_multiple comparison backtest: the same strategy (pure Python, shared with live) run over 100,000 broker-native XAUUSDm M5 bars at 1.0 / 1.5 / 2.0 reward:risk. Per-run trades.csv + stats.json are in output/rr_multiple_study/.
  </what-built>
  <how-to-verify>
    Review the table printed by Task 2 (it is reproduced in the SUMMARY):

    | rr_multiple | trades | win% | avg win R | avg loss R | net R | PF | max DD USD |
    |---|---|---|---|---|---|---|---|
    | 1.0 (baseline) | ... | ... | ... | ... | ... | ... | ... |
    | 1.5 | ... | ... | ... | ... | ... | ... | ... |
    | 2.0 | ... | ... | ... | ... | ... | ... | ... |

    Context to weigh the numbers against:
    1. The TP-from-fill precedent — moving the target further away (1.0R realized instead of 0.86R) dropped win rate 58.6% -> 53.9% and net R 0.086 -> 0.069. 2:1 is a much bigger move in the same direction.
    2. Live is REAL MONEY right now (launchd com.joram.trading-bot-cent, XAUUSDc). Wiring rr_multiple live means the bot's next trades carry the new target. The measured edge is thin (net R ~0.09, best-of-39 noise-adjacent).
    3. This plan does NOT touch [risk] max_loss_pct_per_trade — the "SL 20%" half of your framing is a separate decision you can make via `python scripts/tune_risk.py --tag cent --set max_loss_pct_per_trade=... --yes` (or leave it).
    4. Nothing has been changed in the live engine or the live configs; the bot is untouched.
  </how-to-verify>
  <resume-signal>
    Type "approved" to proceed with Task 4 (wire rr_multiple into the live engine + expose it in tune_risk.py). Type "rejected" or "stop" to end the plan here — the backtest knob, study script and measurements stay committed; live wiring is skipped. Either way, note whether you want a different ratio studied (e.g. 1.25/1.75) before proceeding.
  </resume-signal>
</task>

<task type="auto">
  <name>Task 4: Wire rr_multiple into the live engine and tune_risk.py (ONLY after checkpoint approval)</name>
  <files>src/trading_bot/live/engine.py</files>
  <files>scripts/tune_risk.py</files>
  <files>tests/test_live_engine.py</files>
  <files>tests/test_tune_risk.py</files>
  <action>
    Live engine (src/trading_bot/live/engine.py):
    - Line ~294: replace `tp = entry + (entry - sl)` with `tp = entry + cfg.strategy.rr_multiple * (entry - sl)`.
    - Update the comment at line ~290 ("same arithmetic as backtest/engine.py (STRAT-03)") to reflect the rr_multiple scaling and that it must stay identical to the backtest formula.
    - No other changes: `sl` stays `support - sl_buffer`; the OrderRequest path is unchanged.

    tune_risk.py (scripts/tune_risk.py) — extend beyond [risk] to [strategy] rr_multiple with the same safety model:
    - Accept dotted keys in `--set`: `--set strategy.rr_multiple=2.0`. Bare keys (e.g. `max_loss_pct_per_trade`) keep meaning [risk] for backward compatibility with the existing 22 tests. Resolution: key without "." -> "risk.<key>".
    - `_KNOWN_RULES`: key by full dotted name for every rule, adding `strategy.rr_multiple`: ("float", lambda v: v > 0, "must be > 0") — mirroring config.py's StrategyConfig validation (rr_multiple <= 0 raises). Keep the exact same rule strings the current tests assert on for [risk] keys.
    - Generalise the section-scoped edit: `_apply_edits(text, section, edits)` where section comes from the key's prefix ([risk] or [strategy]); a single --set command may touch both tables (apply per-section, sequentially — the sections are disjoint so no conflict). Every other table, comment, blank line and byte layout stays preserved verbatim (the existing line-based `_replace_value` approach, unchanged).
    - In `set_risk` (renamed conceptually to the general editor; keep the function name to minimize test churn if possible): before building changes, verify the dotted key EXISTS in its table in the loaded TOML and reject unknown keys naming the valid set, exactly as today.
    - View mode: print `[strategy] rr_multiple = ...` (via `_format_value`) alongside the [risk] table for each bot.
    - The account-wide cap x slots total stays RISK-ONLY — rr_multiple does not move it, so no mandatory --yes arises from it; the existing interactive prompt path and the leverage warning behaviour are unchanged.
    - The validation gate is unchanged and now covers the whole file automatically: the edited in-memory result must pass `load_config` on a temp file before anything is written. rr_multiple <= 0 or non-float therefore fails there even if it slips past the rule map.
    - Restart contract unchanged: after a confirmed write, launchd agent restart for the tag unless `--no-restart`.

    CRITICAL: Do NOT run tune_risk.py against a live config in this task. Do NOT write config-cent.toml. Do NOT restart com.joram.trading-bot-cent. Task 4 makes the knob available and tested; applying a new ratio to the running bot is the user's confirmed act via tune_risk.py (document the exact command in the SUMMARY, e.g. `python scripts/tune_risk.py --tag cent --set strategy.rr_multiple=2.0 --yes` or with `--no-restart`).

    Tests:
    - tests/test_live_engine.py: add a test where `_config(...)` uses `rr_multiple=2.0` and assert the placed order's `tp == pytest.approx(ENTRY + 2 * (ENTRY - SL))` (101.00 + 2*0.91 = 102.82). Reuse `_walk_to_setup`. The existing rr_multiple=1.0 tests must stay green unchanged.
    - tests/test_tune_risk.py: add tests using the existing tmp-copy BOTS pattern (never the live configs): (a) `--set strategy.rr_multiple=2.0 --yes` on a bot with a [strategy] table edits ONLY that value, preserves comments/other tables, and the result passes load_config (assert cfg.strategy.rr_multiple == 2.0); (b) invalid values (0, -1, "abc") are refused with an error naming `strategy.rr_multiple` and nothing written; (c) unknown dotted key refused; (d) view prints the rr_multiple line. Existing 22 tests must stay green (bare [risk] keys still work).
  </action>
  <verify>
    `python -m pytest tests/test_live_engine.py tests/test_tune_risk.py -q` passes (new + existing).
    Full suite `python -m pytest tests/ -q` green.
    `python scripts/tune_risk.py --tag cent` (READ-ONLY view) prints `rr_multiple = 1.0` for the [strategy] table and does NOT write anything (byte-compare config-cent.toml before/after — it must be identical; the bot keeps running).
  </verify>
  <done>
    live/engine.py computes tp from cfg.strategy.rr_multiple (identical arithmetic to the backtest); tune_risk.py views and edits strategy.rr_multiple with the same validation / --yes / load_config / restart gates; tests green; no live config written, no restart issued.
  </done>
</task>

</tasks>

<verification>
- `python -m pytest tests/ -q` green at the end of Task 1 and again after Task 4.
- Backtest parity: rr_multiple=1.0 output identical to pre-change output (golden tests pin this).
- Live/backtest parity: the tp formula in both engines is `entry + rr_multiple*(entry - sl)`.
- Study artifacts exist: output/rr_multiple_study/{trades,stats}_{1.0,1.5,2.0}.* and the printed table is recorded in the SUMMARY.
- The live bot is untouched end to end: config-cent.toml bytes unchanged, launchd agent not restarted (verify `launchctl list | grep trading-bot-cent` still shows the agent and `output/live_cent.pid` unchanged).
- The checkpoint result (approved/rejected + any requested rerun) is recorded in the SUMMARY.
</verification>

<success_criteria>
- [ ] `rr_multiple` flows from config -> backtest CLI -> engine; 1.0 reproduces the historical baseline
- [ ] A reproducible comparison (1.0/1.5/2.0) ran on broker-native XAUUSDm and its table (trades, win%, avg win/loss R, net R, PF, max DD) is captured
- [ ] The user decided on 2:1 from real numbers, not hope, before any live change
- [ ] If approved: the live engine and tune_risk.py carry the knob, fully tested, live config and bot untouched
- [ ] The decision + the exact user command to apply the chosen ratio live (with --yes and restart semantics) are documented in the SUMMARY
</success_criteria>

<output>
After completion, create `.planning/quick/004-tp-sl-ratio/004-SUMMARY.md`
</output>
