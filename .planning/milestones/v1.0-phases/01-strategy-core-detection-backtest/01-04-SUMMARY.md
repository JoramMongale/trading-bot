---
phase: 01-strategy-core-detection-backtest
plan: 04
subsystem: strategy
tags: [pandas, rolling-window, support-resistance, expiry, tdd, gap-closure]

# Dependency graph
requires:
  - phase: 01-strategy-core-detection-backtest
    provides: swings.py detect_swings (confirmed swing_high/swing_low columns), original ffill-based support_resistance from plan 01-02
provides:
  - support_resistance() with window-bounded expiry: resistance/support = trailing-lookback rolling max/min of CONFIRMED swings, decaying to NaN the first bar the window holds no swing of that type (no .ffill())
  - Two new expiry-to-NaN tests (resistance AND support — the previously failing case) + two reconciled replacement tests encoding the corrected window-gap semantics
  - levels.py docstring and code agreeing for the first time (contract: level expiry is a pure function of the lookback window)
affects: [01-05 gap closure (CLI hygiene), phase 2 live bot (SHARED detection code per SAFE-01), STRAT-01 robustness]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Window-bounded level expiry: rolling(lookback, min_periods=1).max()/.min() over CONFIRMED swing columns — no forward-fill; expiry is a pure function of bar count (no data-gap knowledge, no lookahead)"
    - "TDD RED-GREEN-REFACTOR on a gap-closure bug: failing test pinned the decay-to-NaN contract before the fix"

key-files:
  created: []
  modified:
    - src/trading_bot/strategy/levels.py
    - tests/test_levels.py

key-decisions:
  - "Drop .ffill() from support_resistance: resistance = swing_high.rolling(lookback, min_periods=1).max(), support = swing_low.rolling(lookback, min_periods=1).min() — levels decay to NaN when the lookback window holds no confirmed swing (was: ffill-forever)"
  - "Level expiry is a pure function of the lookback window (bar-count based): it requires no knowledge of data gaps by design — a swing up to `lookback` bars old is legitimately in-window even across a time gap; the CLI-side sample exclusion + gap warning is plan 01-05's scope"

patterns-established:
  - "S/R level = trailing-lookback max/min of CONFIRMED swings; NaN until the first confirmed swing; persists while in-window; decays to NaN on window exit; newer swing updates level immediately"

# Metrics
duration: 4min
completed: 2026-08-11
---

# Phase 1 Plan 4: Window-Bounded S/R Level Expiry Summary

**Fixed the stale-level contamination root cause: `support_resistance()` no longer ffill's expired swings forever — levels are now a pure trailing-window max/min of CONFIRMED swings and decay to NaN the first bar the lookback window holds no swing of that type (docstring and code finally agree).**

## Performance

- **Duration:** 4 min
- **Started:** 2026-08-11T06:32:22Z
- **Completed:** 2026-08-11T06:36:22Z
- **Tasks:** 2 (RED test commit, GREEN+REFACTOR feat commit)
- **Files modified:** 2

## Accomplishments
- **Root-cause fix (STRAT-01/SAFE-01):** removed `.ffill()` from both rolling lines in `support_resistance`. `resistance = swing_high.rolling(lookback, min_periods=1).max()`, `support = swing_low.rolling(lookback, min_periods=1).min()`. A swing stops contributing the first bar it leaves the window; the level decays to NaN when no confirmed swing of that type is inside the window — never carried forward past it.
- **Contract restored:** module + function docstrings rewritten to state the window-bounded expiry contract precisely; the code now matches the docstring for the first time (the original contradiction from 01-02).
- **Failing case pinned by TDD:** two new tests (`test_resistance_expires_to_nan_when_swing_leaves_window`, `test_support_expires_to_nan_when_swing_leaves_window`) failed on the old ffill code and pass now — the decay-to-NaN case the verifier flagged as untested.
- **Two ffill-forever tests reconciled:** replacement tests now assert NaN in the window gap between the expired swing and the next confirmed swing (their replacement-bar assertions kept unchanged); `test_resistance_persists_via_ffill` renamed to `test_resistance_persists_within_lookback_window` (the old name encoded the bug).
- **Purity/no-lookahead preserved:** levels.py imports only `pandas as pd`, keeps `df.copy()` at the top, and reads only the confirmed `swing_high`/`swing_low` columns. No changes to engine.py, signals.py, or swings.py.

## Task Commits

Each task was committed atomically:

1. **Task 1: RED — write the failing expiry-to-NaN tests** - `9a86561` (test)
2. **Task 2: GREEN + REFACTOR — fix levels.py + reconcile tests** - `aa85904` (feat)

**Plan metadata:** pending (docs commit follows)

## Files Created/Modified
- `src/trading_bot/strategy/levels.py` - `support_resistance()`: dropped `.ffill()` from both rolling lines (lines 35-36); rewritten module + function docstrings stating the window-bounded contract
- `tests/test_levels.py` - added 2 expiry-to-NaN tests (resistance + support); reconciled 2 replacement tests to the corrected window-gap semantics; renamed `test_resistance_persists_via_ffill` → `test_resistance_persists_within_lookback_window`; updated header docstring

## Decisions Made
- **Drop `.ffill()`; window-bounded expiry.** `resistance = swing_high.rolling(lookback, min_periods=1).max()` and `support = swing_low.rolling(lookback, min_periods=1).min()`. Rationale: ffill-forever let a swing from years-old data (2021 sample, ~$100 gold) survive into 2025 data (~$2600 gold), producing economically impossible SL/TP; the rolling max/min of confirmed swings is a pure function of the trailing window.
- **Semantic deviation from the ORIGINAL 01-02 formula.** Plan 01-02 implemented `rolling(lookback, min_periods=1).max().ffill()` / `.min().ffill()`; 01-04 deliberately drops the `.ffill()` suffix. Observable change: when a swing leaves the lookback window and no newer swing of that type appears, the level decays to NaN (was: persisted forever). Replacement behavior (newer swing updates level immediately) is unchanged; NaN until the first confirmed swing is unchanged. 01-02-SUMMARY's decision "ffill means a level never returns to NaN after a swing exists" is superseded by this plan.
- **Expiry is bar-count based by design** (must-have: "requires no knowledge of data gaps"). A swing up to `lookback` bars old is legitimately in-window even across a 4-year timestamp gap; the default run's remaining first-day contamination (sample CSV co-residing in `data/raw/`, globbed by the CLI) is closed by plan 01-05 (DAT_ASCII-only glob + sample relocation + data-gap warning), which depends on this plan.

## Deviations from Plan

None - plan executed exactly as written (two deviations-from-01-02 semantics noted above are the plan's intended fix, not unplanned work).

## Issues Encountered
- **Real-data spot check nuance (documented, not a failure):** with the fix in place, `python -m trading_bot.cli backtest` on the default data dir (sample still in `data/raw/`) still produces the verifier's two 2025-01-01 trades (18:05 and 19:30) with 2021-level SL/TP. Cause: the sample is only 12 M5 bars (1 hour) and the 2025 file starts at 18:00, so the 2021 swings are still *inside* the 60-bar lookback window at the first 2025 bar — window-bounded expiry correctly keeps them until the window flushes (~60 bars in). Armed orders carry fixed SL/TP, so trade #2 (sl=100.09) still hangs OPEN. This is exactly why plan 01-05 (sample exclusion from the glob + gap warning + clean default-run test) depends on this plan. The ffill-forever root cause is dead: an expiry probe with a >lookback bar-count gap confirmed the level decays to NaN and setups cannot fire on expired levels (the only setup in the probe fired on a fresh 2025 level at ~$2624, not the stale ~$102 level).
- **Probe assertion miscalibration (self-corrected):** the first contamination probe asserted NaN at the first 2025 bar with only 10 bridging bars — wrong, because the 2021 swing was still inside the 60-bar window. Corrected to assert decay exactly at window flush (bar 66 of 70) and at the first 2025 bar when the bridge exceeds the lookback. No code change needed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `support_resistance` now implements the documented window-bounded contract — the Phase 2 live bot inherits correct level-expiry semantics (SAFE-01 shared detection code).
- Full suite: **35/35 tests green** under `.venv/bin/pytest -q -W error::FutureWarning` (33 existing + 2 new); golden backtest integration tests pass unchanged (all swings inside lookback=60).
- **Ready for 01-05-PLAN.md** (CLI hygiene: DAT_ASCII-only glob, sample relocation, data-gap warning, clean default-run test) — it depends on this plan's levels fix.
- Blocker for default-run cleanliness: `sample_XAUUSD_M1_20210201.csv` still sits in `data/raw/` and is globbed by the CLI; 01-05 removes/excludes it.

---
*Phase: 01-strategy-core-detection-backtest*
*Completed: 2026-08-11*
