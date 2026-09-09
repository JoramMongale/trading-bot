---
phase: 05-instrument-correct-backtest-machinery
plan: 01
subsystem: data
tags: [instrument-spec, sidecar-json, config-schema, dataclass, frozen, stdlib-only]

# Dependency graph
requires:
  - phase: 04 (AI/live config defaults pattern — frozen dataclasses, DEFAULT_* merging)
    provides: config.py conventions this plan extended (optional-field defaults, _validate ValueError naming keys)
provides:
  - InstrumentSpec frozen dataclass + load_instrument_spec() + base_symbol() in src/trading_bot/data/loader.py
  - Config schema growth: DataConfig.spec_file, StrategyConfig.sl_buffer_points, TradingConfig without spread_assumption, legacy-key tolerance in load_config
  - One-buffer-source validation (sl_buffer XOR sl_buffer_points, never neither)
  - tests/test_spec.py (20 tests) + tests/test_config_instrument.py (15 tests)
affects: [05-02 stats layer (spec-driven money/spread), 05-03 CLI wiring + symbol-identity guard, Phase 6 spec-sidecar fetch]

# Tech tracking
tech-stack:
  added: [stdlib only: json, dataclasses, pathlib — NO new packages (STACK constraint)]
  patterns:
    - "frozen dataclass as pure offline mirror of live broker SymbolRisk semantics"
    - "value_per_point = tick_value / tick_size — same formula live risk gate uses, so backtest money and live sizing can never disagree"
    - "required-key validation with ValueError naming the FILE's own key (trade_tick_size, not tick_size)"
    - "zero-refusal on tick economics (mirrors MT5Broker.symbol_risk): refuse, never divide"
    - "retired config knob tolerated via dict .pop before dataclass construction — tolerate, never model"

key-files:
  created:
    - tests/test_spec.py
    - tests/test_config_instrument.py
  modified:
    - src/trading_bot/data/loader.py
    - src/trading_bot/config.py
    - tests/test_ai_backtest.py
    - tests/test_ai_context.py
    - tests/test_ai_engine.py
    - tests/test_ai_hooks.py
    - tests/test_live_engine.py
    - tests/test_safety.py

key-decisions:
  - "InstrumentSpec maps STACK sidecar keys exactly: trade_tick_size->tick_size, trade_tick_value->tick_value, trade_contract_size->contract_size, spread_points_median->spread_points (with plain spread_points accepted as an alias)"
  - "value_per_point property (tick_value/tick_size) is the single money-per-price-unit-per-lot source; InstrumentSpec never derives money from [trading] contract_size (PITFALLS A2)"
  - "spread_assumption removed from the typed TradingConfig; load_config pops it from the raw trading dict so every committed TOML (live gold/BTC included) still loads byte-identically"
  - "sl_buffer gained default 0.0 (=unset) and sl_buffer_points added after it; _validate enforces exactly ONE buffer source (>=0, not both >0, not both 0), replacing the legacy sl_buffer>0 rule"
  - "DataConfig.spec_file appended at END with default '' so positional construction in the six fixture files is untouched"

patterns-established:
  - "Pure offline symbol facts mirror live SymbolRisk: same money formula, same zero-refusal, no contract-size derivation"
  - "Config schema grows by optional trailing fields with legacy defaults; removal of a dead knob goes through pop-tolerance, never through editing committed TOMLs"
  - "Validation raises ValueError naming the config key; spec loader raises ValueError naming the sidecar's own file key"

requirements-completed: [INST-01, INST-03]

# Metrics
duration: 3min
completed: 2026-09-08
---

# Phase 05 Plan 01: InstrumentSpec + Sidecar Loader + Config Schema Growth Summary

**InstrumentSpec frozen dataclass with tick_value/tick_size money semantics and a STACK sidecar JSON loader in data/loader.py, plus config.py schema growth (data.spec_file, strategy.sl_buffer_points, spread_assumption retired from the typed schema via legacy-key pop tolerance) — with all committed configs including live gold/BTC still loading byte-identically**

## Performance

- **Duration:** 3 min
- **Started:** 2026-09-08T15:36:45Z
- **Completed:** 2026-09-08T15:39:49Z
- **Tasks:** 3
- **Files modified:** 9 (2 source, 2 new test files, 6 mechanical fixture edits; 1 existing test file was the TDD RED commit vehicle)

## Accomplishments
- `InstrumentSpec` (frozen) + `load_instrument_spec()` + `base_symbol()` appended to `src/trading_bot/data/loader.py`; `load_histdata_csv` body byte-identical
- STACK sidecar field mapping as built: `trade_tick_size→tick_size`, `trade_tick_value→tick_value`, `trade_contract_size→contract_size`, `spread_points_median→spread_points` (plain `spread_points` accepted as alias); `value_per_point = tick_value/tick_size` (== 910.0 for EURJPYc fixture), `spread_price = spread_points * point`
- Config schema: `TradingConfig` lost `spread_assumption`; `DataConfig.spec_file: str = ""`; `StrategyConfig.sl_buffer: float = 0.0` + `sl_buffer_points: float = 0.0`; `load_config` pops the retired knob; `_validate` enforces exactly-one-buffer-source and `data.spec_file` string typing
- New tests green: `tests/test_spec.py` (20) + `tests/test_config_instrument.py` (15)

## task Commits

Each task was committed atomically:

1. **task 1: InstrumentSpec dataclass + sidecar JSON loader in data/loader.py** — *no git repo — direct file edits* (TDD: RED `tests/test_spec.py` collection-error confirmed, then GREEN loader implementation; 20 passed)
2. **task 2: config.py schema growth — spec_file, sl_buffer_points, retire spread_assumption** — *no git repo — direct file edits* (15 passed + acceptance one-liner OK)
3. **task 3: mechanical test-fixture updates for the removed TradingConfig field** — *no git repo — direct file edits* (exactly 6 constructor edits; 109 passed across the six modules)

**Plan metadata:** *no git repo — direct file edits* (docs: complete plan — SUMMARY.md written to phase dir)

_Note: TDD task 1 followed RED → GREEN in working-file state; commit steps skipped (no git repository in this workspace)._

## Files Created/Modified
- `src/trading_bot/data/loader.py` - Added `InstrumentSpec` frozen dataclass (symbol, digits, point, tick_size, tick_value, contract_size, spread_points=0.0, account_currency="") with `value_per_point`/`spread_price` properties; `load_instrument_spec()` reading the STACK sidecar with `_req`/`_pos` validation (ValueError naming the file's own key, FileNotFoundError naming the path, JSONDecodeError propagates); `base_symbol()` stripping one trailing account-type letter. Imports `json`, `dataclass`, `pathlib.Path`. Existing `load_histdata_csv` byte-identical.
- `src/trading_bot/config.py` - `TradingConfig` down to `lot`/`contract_size`; `DataConfig.spec_file: str = ""` appended; `StrategyConfig.sl_buffer: float = 0.0` + new `sl_buffer_points: float = 0.0`; `load_config` builds trading via `trading_raw.pop("spread_assumption", None)` tolerance; `_validate` buffer-exclusivity block + `data.spec_file` isinstance-str check.
- `tests/test_spec.py` - (new) 20 tests: sidecar field mapping, plain `spread_points` alias, value_per_point/spread_price property math, parameterized missing-required-field and zero-field ValueError cases, FileNotFoundError for missing path, parameterized base_symbol suffix stripping.
- `tests/test_config_instrument.py` - (new) 15 tests: all five committed config TOMLs still load (config.toml, config-cent.toml live-enabled, config-btc.toml live-enabled, config-ai-live.toml, config-ai.toml), no spread_assumption attribute on trading, legacy-key tolerance byte-identical, spec_file round-trip/default/type validation, points-only config, legacy sl_buffer-only config, both-set rejection ("ONE unit"), both-zero rejection ("both 0"), negative sl_buffer_points rejection.
- `tests/test_ai_backtest.py`, `tests/test_ai_context.py`, `tests/test_ai_engine.py`, `tests/test_ai_hooks.py`, `tests/test_live_engine.py`, `tests/test_safety.py` - Exactly one edit each: `TradingConfig(lot=0.01, contract_size=100, spread_assumption=0.0)` → `TradingConfig(lot=0.01, contract_size=100)`. No other token changed.

## Decisions Made
- `value_per_point` (tick_value/tick_size) as the sole offline money-per-unit-per-lot source, mirroring the live `SymbolRisk` formula so backtest money and live sizing can never disagree; InstrumentSpec never derives money from `[trading] contract_size` (PITFALLS A2)
- `load_config` pops the retired `spread_assumption` key rather than editing any committed config TOML (never edit config-cent.toml / config-btc.toml / config.toml — D3/D5)
- Field-ordering preserved: non-default strategy fields precede defaulted `sl_buffer`, `sl_buffer_points`, `variant`; `spec_file` appended at end of DataConfig so positional construction in the six fixture files is unaffected
- Validation messages for the spec loader name the sidecar's own keys (`trade_tick_size`), not the mapped field names

## Deviations from Plan

None - plan executed exactly as written (code + tests + verification all per the plan file).

**Environment adaptations (not plan deviations):**
- **No git repository in this workspace** — every per-task `git commit` was skipped by design; task work is tracked by direct file edits and the per-task pytest results recorded here. `commit-to-subrepo`/`commit` were not run (environment fact: returns committed:false).
- **Mandatory pytest flags** — every pytest invocation appended `-p no:cacheprovider --basetemp C:\Users\joram\AppData\Local\Temp\gsd-pytest-tmp\<unique-suffix>` because the default pytest temp dir and `.pytest_cache` are ACL-locked on this machine (PermissionError WinError 5). Unique basetemp per invocation.

---

**Total deviations:** 0 (plan executed as written)
**Impact on plan:** None.

## Issues Encountered
- **None during planned work.** The float-math pins in the plan (`value_per_point == 910.0`, `spread_price == 0.006`) were verified exact in Python 3.12 before writing the tests (`0.91/0.001 == 910.0` and `6.0*0.001 == 0.006` both True), so the assertions match the plan's spec exactly.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- **05-02 (stats layer):** `InstrumentSpec.value_per_point` and `spread_price` are ready to drive spec-based money conversion and per-trade spread netting in `backtest/stats.py`; `StrategyConfig.sl_buffer_points` is the points-based buffer seam it can consume.
- **05-03 (CLI wiring + mismatch guard):** `data.spec_file` and `load_instrument_spec()` are the seam for loading the spec at the CLI backtest boundary; `base_symbol()` makes config `[data] symbol` vs broker spec symbol comparable for the symbol-identity guard.
- **No blockers.** New config keys are inert by default (`spec_file=""`, `sl_buffer_points=0.0`) so all legacy configs load byte-identically until 05-02/05-03 activate them.

## Self-Check: PASSED

---
*Phase: 05-instrument-correct-backtest-machinery*
*Completed: 2026-09-08*
