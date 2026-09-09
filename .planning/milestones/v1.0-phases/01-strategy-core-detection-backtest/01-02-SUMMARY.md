---
phase: 01-strategy-core-detection-backtest
plan: 02
subsystem: strategy
tags: python, pandas, numpy, pytest, tdd, strategy, fractal, swings, support-resistance

# Dependency graph
requires:
  - phase: research
    provides: verified algorithm facts (fractal definition, confirmation shift, pandas 3.0 CoW pitfalls, exact code examples)
  - phase: 01-01
    provides: installable src/ package, pytest pythonpath=src, config schema ([strategy] fractal_left/fractal_right/sr_lookback)
provides:
  - detect_swings() — Williams fractal swing points with plateau handling and a no-lookahead confirmation shift
  - support_resistance() — trailing-window S/R from CONFIRMED swings (ffill, lookback expiry)
  - detect_setups() — STRAT-02 bullish breakout boolean (re-trigger self-disabled)
  - 18 new pytest cases incl. an ast-based import-purity test proving SAFE-01 readiness
affects: 01-03 (backtest engine consumes these exact functions), phase 2 (live bot calls same code)

# Tech tracking
tech-stack:
  added: []  # pandas/numpy already present from 01-01
  patterns:
    - "strategy/ is pure pandas/numpy — no logging/config/data/broker imports (SAFE-01 literal)"
    - "no-lookahead discipline: raw markers -> raw.shift(right) confirmed columns; levels/setups read confirmed only"
    - "plateau semantics via >=/<= left window, strict >/< right window"
    - "pure functions: df.copy() at start, single-step column assignment (pandas 3.0 CoW-safe)"
    - "TDD per plan: one RED commit (failing tests), one GREEN commit (implementation), refactor skipped (clean)"

key-files:
  created: [src/trading_bot/strategy/__init__.py, src/trading_bot/strategy/swings.py, src/trading_bot/strategy/levels.py, src/trading_bot/strategy/signals.py, tests/test_swings.py, tests/test_levels.py, tests/test_signals.py]
  modified: []

key-decisions:
  - "Confirmed columns = raw.shift(right): a swing is usable only from bar i+right, exactly when live trading knows it (no lookahead)"
  - "Plateau handling: last bar of an equal-high/low plateau is the swing (>=/<= left, strict right)"
  - "Levels stay NaN until the first CONFIRMED swing of that type; ffill persists them; lookback expiry manifests as a newer swing replacing an expired one"
  - "df.copy() at the start of all three functions (plan-mandated CoW safety; RESEARCH.md only copied in detect_swings)"

patterns-established:
  - "Detection pipeline: detect_swings -> support_resistance -> detect_setups, each pure and chainable"
  - "Synthetic hand-built DataFrames with exact expected values (no real data) for strategy unit tests"
  - "ast-based purity test guards the SAFE-01 import boundary permanently"

# Metrics
duration: 3 min
completed: 2026-08-10
---

# Phase 1 Plan 2: Strategy Core Summary

**Williams-fractal swing detection (STRAT-01) with a no-lookahead confirmation shift, trailing-window S/R from confirmed swings, and the STRAT-02 bullish breakout setup rule — 18 new tests green under pandas 3.0 with FutureWarnings as errors**

## Performance

- **Duration:** 3 min
- **Started:** 2026-08-10T17:25:30Z
- **Completed:** 2026-08-10T17:28:15Z
- **Tasks:** 3 (RED, GREEN, REFACTOR-reviewed)
- **Files modified:** 7 (4 source, 3 test)

## Accomplishments

- `detect_swings(df, left=2, right=2)` — Williams fractal swing highs/lows built with vectorized rolling windows (no row loops): `>=`/`<=` on the left window (the LAST bar of an equal-high/low plateau is the swing), strict `>`/`<` on the right (confirmation stays honest), and `swing_high/swing_low = raw.shift(right)` so a swing is usable exactly when live trading would know it — no lookahead bias
- `support_resistance(df, lookback=60)` — resistance/support from trailing-lookback rolling max/min over the CONFIRMED columns only, ffill'ed forward; NaN until the first confirmed swing of each type exists (unconfirmed swings can never leak into levels)
- `detect_setups(df)` — `setup = (close > resistance) & (close.shift(1) <= resistance.shift(1))` (STRAT-02); the prior-close condition self-disables re-triggers after a breakout
- Pure-function guarantee: every function starts with `df.copy()` and adds columns via single-step assignment (pandas 3.0 CoW-safe), inputs never mutated
- Import-purity test (ast-based) locks in the SAFE-01 boundary: `strategy/` imports ONLY pandas/numpy — Phase 2's live bot will call these exact functions

## Task Commits

Each task was committed atomically:

1. **Task 1: RED — failing tests for swings/levels/signals** - `68e0c7b` (test)
2. **Task 2: GREEN — implement swings.py, levels.py, signals.py** - `d53a080` (feat)
3. **Task 3: REFACTOR — review & cleanup** - no commit (review found the modules already satisfy every refactor criterion; the plan mandates the verified RESEARCH.md code, so no behavior-neutral churn was warranted)

**Plan metadata:** `docs(01-02)` — this commit (execution artifacts: SUMMARY, STATE, ROADMAP)

## Test List (18 new)

**tests/test_swings.py** (7)
1. `test_rising_peak_detects_swing_high_at_peak` — highs `[1,2,3,4,3,2,1]` → raw swing at idx 3 = 4.0, exactly one raw marker
2. `test_confirmation_shift_proves_no_lookahead` — `swing_high` NaN at idx 0–4, = 4.0 at idx 5 (`raw.shift(2)`), NaN at idx 6
3. `test_plateau_last_equal_high_bar_is_the_swing` — highs `[1,2,2,1,0.5]`: idx 1 NOT a swing, idx 2 IS (confirmed at idx 4)
4. `test_symmetric_swing_low` — lows `[5,4,3,4,5]` → raw at idx 2 = 3.0, confirmed at idx 4
5. `test_frame_start_first_left_bars_cannot_be_swings` — first `left` bars NaN via `min_periods`
6. `test_extra_columns_pass_through_unchanged` — `volume` survives; input frame unmutated
7. `test_strategy_modules_import_only_pandas_and_numpy` — ast-based purity check over `strategy/*.py`

**tests/test_levels.py** (6)
1. `test_resistance_nan_until_first_confirmed_swing` — chain proves no lookahead: raw swing at idx 3, resistance NaN until idx 5
2. `test_resistance_persists_via_ffill` — level at bar i still the level at bar i+5 with no newer swing
3. `test_newer_higher_swing_raises_resistance` — 5.0 → 6.0 on confirmation
4. `test_lookback_expiry_newer_lower_swing_replaces` — 5.0 swing (lookback 3) expires; 3.5 swing becomes resistance at idx 8
5. `test_support_uses_min_of_confirmed_swing_lows` — NaN until confirmed; newer higher swing low does NOT raise support (min semantics)
6. `test_support_lookback_expiry_newer_lower_swing_replaces` — symmetric expiry for support (3.0 → 2.0)

**tests/test_signals.py** (5)
1. `test_fires_exactly_on_bullish_close_above_resistance` — close `[10,10,9,9.5,10.5]`, res `[NaN,NaN,10,10,10]` → True ONLY at idx 4
2. `test_retrigger_disabled_after_breakout` — close `[10,10,9,11,11.5]`, res `[10×5]` → True at idx 3, False at idx 4
3. `test_nan_resistance_never_fires` — NaN levels never produce a setup
4. `test_extra_columns_pass_through_unchanged` — `volume` preserved; input unmutated
5. `test_full_pipeline_fires_on_breakout_after_confirmation` — swings → levels → setups chain on a realistic series

## Files Created/Modified

- `src/trading_bot/strategy/__init__.py` - package marker + SAFE-01 purity contract docstring
- `src/trading_bot/strategy/swings.py` - `detect_swings(df, left=2, right=2) -> df`; fractal detection + confirmation shift
- `src/trading_bot/strategy/levels.py` - `support_resistance(df, lookback=60) -> df`; rolling max/min + ffill on confirmed columns
- `src/trading_bot/strategy/signals.py` - `detect_setups(df) -> df`; STRAT-02 boolean
- `tests/test_swings.py` - swing detection + purity tests (128 lines)
- `tests/test_levels.py` - S/R behavior tests (78 lines)
- `tests/test_signals.py` - setup + pipeline tests (64 lines)

## Function Signatures (final)

```python
def detect_swings(df: pd.DataFrame, left: int = 2, right: int = 2) -> pd.DataFrame:
    # adds: swing_high_raw, swing_low_raw, swing_high, swing_low

def support_resistance(df: pd.DataFrame, lookback: int = 60) -> pd.DataFrame:
    # reads swing_high/swing_low (confirmed); adds: resistance, support

def detect_setups(df: pd.DataFrame) -> pd.DataFrame:
    # reads close + resistance; adds: setup (bool)
```

## Decisions Made

- **No-lookahead is structural, not optional:** `swing_high = swing_high_raw.shift(right)` — a swing at bar i becomes usable only at bar i+right, exactly when live trading would know it. Levels and setups read ONLY the confirmed columns, and tests assert this at the pipeline level (resistance stays NaN while unconfirmed raw swings exist).
- **Plateau semantics:** `>=`/`<=` on the left window makes the LAST bar of an equal-high/low plateau the swing; strict `>`/`<` on the right keeps confirmation honest. Verified by the `[1,2,2,1,0.5]` plateau test.
- **`df.copy()` at the start of ALL three functions** — plan-mandated CoW safety; RESEARCH.md only copied in `detect_swings`. This makes every function truly pure (caller's frame never mutated) at zero behavior cost, verified by the "input unmutated" assertions.
- **Lookback expiry semantics:** because of ffill, a level never returns to NaN after a swing has existed (ffill bridges all-NaN windows); the observable effect of `lookback` is that a newer swing's value replaces an expired one even when lower. Tests assert this observable behavior; the plan's "or NaN" phrasing is unobservable by construction of the verified formula.

## Deviations from Plan

None in behavior — all three modules follow the verified RESEARCH.md code and the plan's `<implementation>` guidance exactly. Two documentation-worthy notes:

1. **`df.copy()` in levels.py/signals.py** — the plan's implementation steps mandate `df.copy()` at function start for all three functions; RESEARCH.md only had it in `detect_swings`. Behavior of the returned frames is identical; the caller's input frame is now guaranteed unmutated (asserted in tests).
2. **Refactor task produced no commit** — the review found the modules already satisfy every refactor criterion (locals extracted, spec-exact names, docstrings with plateau/shift rationale, no CoW hazards). The plan explicitly mandates the verified RESEARCH.md structure, so no behavior-neutral churn was made. TDD reference: "commit only if changes made."

**Total deviations:** 0 auto-fixed
**Impact on plan:** None. Success criteria met: STRAT-01 (fractal swings, plateau handling, confirmed no-lookahead columns), STRAT-02 (exact crossover + re-trigger disable), SAFE-01 foundation (pure pandas/numpy strategy module).

## Issues Encountered

None. The vectorized rolling-window approach from RESEARCH.md produced exact expected values on the first run (18/18 green immediately after GREEN implementation).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for `01-03-PLAN.md` (backtest engine) — it consumes `detect_swings` → `support_resistance` → `detect_setups` exactly as chained in `test_full_pipeline_fires_on_breakout_after_confirmation`; RESEARCH.md's verified event-loop pattern is already documented
- The strategy module contract (confirmed columns, no-lookahead, pure imports) is pinned by tests, so the backtester can build on it without re-verification
- Note for Phase 2 (live bot): these exact functions plus config `[strategy] fractal_left=2, fractal_right=2, sr_lookback=60` are the live-trading detection path — SAFE-01 holds by construction

---
*Phase: 01-strategy-core-detection-backtest*
*Completed: 2026-08-10*
