---
phase: 004-tp-sl-ratio
plan: 01
subsystem: strategy
tags: [rr_multiple, reward-risk, backtest, live-engine, tune_risk, tp-sl, gold, xauusd]

requires:
  - phase: "003-risk-tuning-script"
    provides: "tune_risk.py line-based TOML editor with --yes gate, load_config validation, launchd restart contract"
  - phase: "260820-mkt-market-entry-and-risk-gate"
    provides: "live engine market-entry path, per-trade risk gate, min_rr guard"
provides:
  - "rr_multiple flows config -> backtest CLI -> backtest engine -> live engine (tp = entry + rr_multiple*(entry - sl))"
  - "Measured 1.0/1.5/2.0 comparison on 100k broker-native XAUUSDm M5 bars with per-run trades.csv + stats.json"
  - "tune_risk.py dotted-key editing for [strategy] rr_multiple with aggressive-tier warnings"
affects: [live gold bot tuning, risk decisions, future strategy measurement]

tech-stack:
  added: []
  patterns:
    - "Backtest/live parity: identical tp arithmetic in both engines, parameterised by config"
    - "Dotted-key config editing with per-section scoping, load_config temp-file gate"
    - "Aggressive-tier warnings: loud, measured, non-blocking (accompany the --yes gate)"

key-files:
  created:
    - "scripts/compare_rr_multiple.py"
  modified:
    - "src/trading_bot/backtest/engine.py"
    - "src/trading_bot/cli.py"
    - "src/trading_bot/live/engine.py"
    - "scripts/tune_risk.py"
    - "tests/test_backtest.py"
    - "tests/test_live_engine.py"
    - "tests/test_tune_risk.py"

key-decisions:
  - "rr_multiple default 1.0 keeps every existing call/behaviour byte-identical (golden tests pin this)"
  - "Live wiring approved by user AFTER the measured table, with an added requirement: aggressive settings must WARN loudly but remain allowed (--yes gate, never a block)"
  - "Warnings carry measured evidence: rr>=1.5 -> study table + split-sample caveat; cap>=10 -> 4-loss streak -35% + -0.0156R net edge; account-wide total >5% -> correlated stop-out exposure"
  - "tune_risk.py edits only [risk] and [strategy] tables; dotted keys resolve bare -> risk.<key> for backward compat"
  - "test suite stubs _restart_agent (autouse) so tests editing tmp config copies can never restart the real launchd agents"

patterns-established:
  - "Two engines, one formula: tp = entry + rr_multiple * (entry - sl) in both backtest and live, driven by [strategy] rr_multiple"
  - "Warn-don't-block: aggressive tiers print measured-evidence banners; --yes proceeds"

# Metrics
duration: 35min
completed: 2026-08-24
---

# Quick Task 004 — TP/SL ratio (rr_multiple): measured study first, live wiring after approval

**rr_multiple wired through the backtest CLI + engine and (post-approval) the live engine with tune_risk dotted-key support and measured-evidence aggressive-tier warnings; the 1.0/1.5/2.0 study on 100k broker-native XAUUSDm M5 bars was presented for a human decision before any live change**

## Performance

- **Duration:** 35 min
- **Started:** 2026-08-24T09:49:32Z
- **Completed:** 2026-08-24T10:24:41Z
- **Tasks:** 3 executed (Task 3 = human-verify checkpoint; Task 4 approved)
- **Commits:** 4 (Tasks 1, 2, 4-live, 4-tune-risk)
- **Tests:** 260 green (246 baseline + 14 new)

## Accomplishments

1. **Backtest knob (Task 1):** `run_backtest` gained `rr_multiple: float = 1.0` (default = exact historical 1:1, pinned by untouched golden tests); the backtest CLI passes and logs `cfg.strategy.rr_multiple`. Suite 247 green.
2. **Measured study (Task 2):** `scripts/compare_rr_multiple.py` runs the shared strategy over 100k broker-native XAUUSDm M5 bars (2025-03-24 → 2026-08-20) at 1.0/1.5/2.0 and writes per-run `output/rr_multiple_study/trades_{rr}.csv` + `stats_{rr}.json`.
3. **Checkpoint decision (Task 3):** the measured table was presented with robustness evidence. **The result contradicted the plan's expectation** (net R ROSE with rr_multiple instead of falling), so the evidence was stress-tested before presentation: split-sample, concentration, hold times, weekend-gap exposure, and the STATE.md noise calibration.
4. **Live wiring (Task 4, user-approved with added requirement):** live engine computes `tp = entry + cfg.strategy.rr_multiple * (entry - sl)` (STRAT-03 parity); `tune_risk.py` accepts `--set strategy.rr_multiple=2.0` with the same comment-preserving, validated, atomic, --yes-gated edit; aggressive settings (rr>=1.5, cap>=10%, total>5%) print loud measured WARNING banners that never block — --yes proceeds.
5. **Test-safety fix:** the suite now stubs `_restart_agent` (autouse) so tests can never bootout the real launchd agents (see Deviations — this was actively biting).

## Measured Study (the checkpoint table)

Broker-native XAUUSDm M5, config-cent strategy params (fractal 2/2, lookback 60, sl_buffer 0.01), contract 100 × lot 0.01:

| rr_multiple | trades | win% | avg win R | avg loss R | net R | PF | max DD USD |
|---|---|---|---|---|---|---|---|
| 1.0 (baseline) | 437 | 58.4% | 0.848 | −1.000 | 0.091 | 1.22 | $589 |
| 1.5 | 294 | 49.3% | 1.310 | −1.000 | 0.147 | 1.31 | $782 |
| 2.0 | 235 | 43.8% | 1.779 | −1.000 | 0.230 | 1.31 | $990 |

Sanity anchor: the 1.0 row reproduces STATE.md's broker figures exactly (437 trades, 58.4% win, avg R 0.091, PF 1.22, max DD ~$588).

**Robustness findings presented with the table (why the plan's "expect 2.0 to be worse" did not hold, and why the rise is still not evidence of a better edge):**

- **Split-sample — the 2.0 edge is front-loaded:** first half 1.0 avgR +0.126 (t=2.11) / 2.0 +0.340 (t=2.71); **second half 1.0 +0.049 (t=0.74) / 2.0 +0.096 (t=0.73)** — on the freshest data every ratio is indistinguishable from zero and from each other.
- **Noise calibration:** full-sample t rises 2.07 → 2.52, but STATE.md's own calibration says best-of-39 |t|=2.46 is beaten by noise 42% of the time; this is best-of-3 on the same window.
- **Max DD nearly doubles** $589 → $990 on 0.01 lots (~32% of the R3,121 cent account).
- **Halved sample:** the far target holds the single slot ~2× longer (median 7.5h → 15.7h, p90 53h → 102h) → 0.46 trades/day vs 0.85; net USD over the span +9% despite +153% net R.
- **Weekend-gap exposure triples:** trades holding >2.5 days 37/438 (8%) → 49/236 (21%); p90 hold 4+ days on a market shut Fri 21:00 → Sun 21:00 UTC.
- **Concentration:** top-10 winners at 2.0 = 37% of total net R.

**User decision: APPROVED Task 4** (wire live) **with added requirement:** "make it configurable, just with a warning in the UI if a user decides to go for maximum" — warn loudly, still allow.

## Task Commits

Each task was committed atomically:

1. **Task 1: rr_multiple through backtest engine + CLI** - `a1d8c53` (feat)
2. **Task 2: compare_rr_multiple.py study script** - `e34a722` (feat)
3. **Task 4a: live engine rr_multiple parity** - `f76db76` (feat)
4. **Task 4b: tune_risk.py dotted keys + aggressive warnings** - `e598d0f` (feat)

## Files Created/Modified

- `src/trading_bot/backtest/engine.py` - `rr_multiple: float = 1.0` param; `tp = entry + rr_multiple * (entry - sl)`; docstring/comment updates; default 1.0 behaviour byte-identical (golden tests unchanged)
- `src/trading_bot/cli.py` - passes + logs `rr_multiple=cfg.strategy.rr_multiple` in `backtest_run`
- `src/trading_bot/live/engine.py` - `tp = entry + cfg.strategy.rr_multiple * (entry - sl)`; min_rr comment reflects configurable ratio; module docstring updated
- `scripts/compare_rr_multiple.py` - reproducible 1.0/1.5/2.0 study on broker-native gold; per-run trades.csv (CLI shape) + stats.json; markdown table + run context; exits 1 on missing data file
- `scripts/tune_risk.py` - dotted-key `--set` (bare → `risk.`); `_KNOWN_RULES` by full dotted name incl. `strategy.rr_multiple`; per-section `_apply_edits`; trailing-inline-comment-preserving `_replace_value`; view prints `strategy.rr_multiple`; aggressive-tier warning banners (rr>=1.5, cap>=10%, total>5%); `_EDITABLE_SECTIONS = ("risk", "strategy")`
- `tests/test_backtest.py` - `test_rr_multiple_arms_farther_tp` (tp 102.82 @ 2.0, 102.365 @ 1.5, sl untouched)
- `tests/test_live_engine.py` - `test_rr_multiple_scales_the_live_target` (order + log carry tp 102.82); `_make_engine(rr_multiple=...)`
- `tests/test_tune_risk.py` - dotted set edits only that value (inline comment preserved), invalid 0/-1/abc refused, unknown key/section refused, view prints rr_multiple, one command edits both tables, each warning tier + --yes gate, no warning below tier; **autouse `_no_real_restarts` fixture stubs `_restart_agent`**

## Decisions Made

1. **rr_multiple default 1.0** keeps every existing call and behaviour unchanged — golden 1:1 tests stay green unmodified.
2. **Measurement before live change** — the plan's sequencing contract was honored: live engine untouched until the checkpoint approved.
3. **User's added requirement:** aggressive settings WARN loudly (measured evidence) but are ALLOWED — warnings accompany the existing --yes gate, never block.
4. **`tune_risk.py` editable sections restricted to `[risk]` + `[strategy]`** — it is a risk/strategy editor, not a general TOML editor; unknown sections refused.
5. **Test suite must never restart live agents** — `_restart_agent` stubbed in tests (autouse); it keys off the tag, so a test writing a tmp config copy must not bootout the real launchd agent.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `_replace_value` destroyed trailing inline comments**
- **Found during:** Task 4b (tune_risk dotted keys) — new test `test_dotted_strategy_rr_multiple_edits_only_that_value` failed because cent's `rr_multiple = 1.0  # 1:1 risk-reward` lost its comment after edit.
- **Issue:** the regex `(.*?)(\s*)$` captured the trailing comment into the "value" group, so `--set strategy.rr_multiple=2.0` rewrote the line as `rr_multiple = 2.0`, deleting `# 1:1 risk-reward`. Violates the tool's comment-preservation contract (and the plan's "comments preserved verbatim").
- **Fix:** regex now stops the value at `#` and preserves the trailing comment: `([^#]*?)(\s*)(#[^\n]*)?$`, rebuilt with the comment appended.
- **Files modified:** scripts/tune_risk.py, tests/test_tune_risk.py
- **Verification:** existing comment-preservation tests + new assertion `rr_multiple = 2.0  # 1:1 risk-reward`; suite green.
- **Committed in:** e598d0f

**2. [Rule 3 - Blocking] Tests could restart the REAL launchd agents**
- **Found during:** Task 4b — an early failing test run reached `_restart_agent("cent")` after writing a tmp copy, booting out + re-bootstrapping the live `com.joram.trading-bot-cent` (pid 16117 → 31879; launchd respawned it healthy with the untouched real config).
- **Issue:** `_restart_agent` keys off the TAG, not the config path, so any test reaching the write path without `--no-restart` restarted a live bot. The pre-existing `test_compensating_change_allowed_without_yes_but_warns` had been doing exactly this to the BTC agent on every suite run.
- **Fix:** autouse `_no_real_restarts` fixture stubs `tune_risk._restart_agent` → tests can never touch launchd. Live configs stay never-written (verified byte-identical md5).
- **Files modified:** tests/test_tune_risk.py
- **Verification:** full suite green; `launchctl list | grep trading-bot-cent` shows the agent; cent config md5 unchanged.
- **Committed in:** e598d0f

**3. [Rule 1 - Bug] `test_dotted_unknown_section_refused` initially allowed editing `[backtest]`**
- **Found during:** Task 4b — `--set backtest.output_dir=out` was accepted (rc 0) because any existing TOML section was editable.
- **Issue:** the tool is a risk/strategy editor; editing `[data]/[trading]/[backtest]/[live]` values is out of scope and outside its safety model.
- **Fix:** `_EDITABLE_SECTIONS = ("risk", "strategy")`; unknown sections refused with the editable list.
- **Files modified:** scripts/tune_risk.py, tests/test_tune_risk.py
- **Verification:** `test_dotted_unknown_section_refused` now passes (rc 2, nothing written).
- **Committed in:** e598d0f

---

**Total deviations:** 3 auto-fixed (2 Rule 1 bugs, 1 Rule 3 blocker)
**Impact on plan:** All fixes necessary for correctness and safety; no scope creep. One planned change also differed in KIND from the plan's prediction (see below).

### Result-vs-expectation deviation (not a code deviation)

The plan expected 1.5/2.0 to be materially WORSE than 1.0 (TP-from-fill precedent: net R 0.086 → 0.069). Measured instead: net R 0.091 → 0.147 → 0.230 and PF 1.22 → 1.31. The checkpoint presented both the measured table and the robustness evidence (split-sample front-loading, t-calibration, doubled max DD, halved sample, weekend-gap exposure, concentration) — the numbers were presented without editorializing and the user decided.

## Issues Encountered

- **Plan's expectation contradicted by measurement.** The TP-from-fill precedent predicted a lower net R at farther targets; the full-span numbers moved the other way. Resolved by stress-testing the finding (split-sample, concentration, hold/DD/weekend exposure) and presenting the complete evidence at the checkpoint rather than the single net-R column.
- **Unplanned live-agent restart during test development.** One early failing test run booted out + re-bootstrapped `com.joram.trading-bot-cent` via the real `_restart_agent` path (pid 16117 → 31879). The real config was never written (md5 unchanged) and launchd respawned the bot healthy (polling `bar_check` minutes after). Root cause fixed with the autouse stub; the agent remains live and untouched going forward.

## Live-bot status (end of plan)

- `com.joram.trading-bot-cent` RUNNING (launchd pid 31769, bot pid in output/live_cent.pid, polling every 5 min).
- `config/config-cent.toml` byte-identical (md5 96add29a896070ba5681c3f0e39254d3) — **rr_multiple still 1.0 live**, `[risk] max_loss_pct_per_trade` untouched.
- No config was written and no planned restart was issued by this plan.

## User Command(s) to Apply a Ratio Live (if/when decided)

After this plan the knob is fully supported. Applying 2.0 to the live gold bot (user act only):

    python scripts/tune_risk.py --tag cent --set strategy.rr_multiple=2.0 --yes

- Prints the aggressive WARNING banner (measured table + split-sample caveat + weekend-gap exposure), then writes `config/config-cent.toml` atomically, validates via `load_config`, and restarts the launchd agent (`--no-restart` to write without restarting; the change applies on next agent start).
- The restart does not touch open positions (broker-side SL/TP + position-open dedup intact).
- To revert: `python scripts/tune_risk.py --tag cent --set strategy.rr_multiple=1.0 --yes`.
- The "SL 20%" half of the original framing is a separate decision: `python scripts/tune_risk.py --tag cent --set max_loss_pct_per_trade=... --yes` (warns at >= 10%).
- Read-only check anytime: `python scripts/tune_risk.py --tag cent` (prints `strategy.rr_multiple = 1.0`).

## Next Phase Readiness

- Backtest and live engines both carry `rr_multiple` with identical arithmetic; the knob is test-covered end to end (260 suite green).
- `scripts/compare_rr_multiple.py` is reusable for any future ratio grid (e.g. 1.25/1.75) or data refresh.
- The decision itself (whether 2:1 goes live) remains open with the measured evidence on record — the split-sample result (recent-half t≈0.7 for every ratio) is the strongest argument against rushing it.
- Follow-up worth noting: `[risk] max_loss_pct_per_trade` ("SL 20%" framing) is still a separate, untaken decision via the same tool.

---
*Phase: 004-tp-sl-ratio*
*Completed: 2026-08-24*
