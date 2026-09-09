---
phase: 05-instrument-correct-backtest-machinery
plan: 03
subsystem: backtest-cli
tags: [python, pandas, toml, instrument-spec, digits, symbol-guard, INST-02, INST-04]

# Dependency graph
requires:
  - phase: 05-01
    provides: InstrumentSpec (frozen dataclass), load_instrument_spec(path), base_symbol(symbol), DataConfig.spec_file, StrategyConfig.sl_buffer_points
  - phase: 05-02
    provides: trade_stats(value_per_point=None, spread_price=0.0) spec money + per-closed-trade spread netting
provides:
  - "[live]-enabled configs structurally refused by the backtest CLI (INST-04, SAFE-03)"
  - "loud config/data symbol-mismatch guard naming BOTH symbols via base_symbol() (INST-02, PITFALLS C4)"
  - "digit-aware output boundary: trades.csv + decision log round at spec.digits (3 dp JPY / 2 dp legacy, PITFALLS A3)"
  - "spec.value_per_point / spec.spread_price wired into the backtest trade_stats call (INST-01/INST-03 reachable)"
  - "SC2 no-spec --m5-csv symbol guard from the broker CSV filename"
affects: [phase 06 broker-fetch sidecars, any JPY-cross backtest milestone, warehouse/ledger consumers of trades.csv]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "backtest-branch guard block in main(): [live]-enabled refusal -> spec load + base_symbol identity guard -> sl_buffer_points-without-spec refusal -> digits selection, all before any data load"
    - "digit-aware boundary: one `digits` variable (spec.digits or legacy 2) drives emit-closure rounding and trades.csv column rounding"
    - "A1/D2 conversion at the run_backtest boundary: sl_buffer = sl_buffer_points x spec.point only when a spec exists"

key-files:
  created:
    - tests/test_cli_spec.py
  modified:
    - src/trading_bot/cli.py

key-decisions:
  - "INST-04 refusal and the spec identity guard run immediately after load_config, BEFORE any data-dir/CSV work, so a live or mismatched config never touches the filesystem data path"
  - "symbol identity compares base_symbol(config [data] symbol) vs base_symbol(spec.symbol): EURJPYc and EURJPY are equal, gold-labelled EURJPY fails loudly naming both (fail-closed)"
  - "spec money is threaded as keyword args value_per_point=None/spread_price=0.0 on the no-spec path — behaviorally identical to the legacy positional call (verified by recorder tests + unchanged test_cli.py)"
  - "SC2 broker-CSV filename guard only fires when spec is None, keeping the spec's authoritative symbol ahead of the filename convention"
  - "decision-log price assertion treats a trailing-zero 3-dp value (162.550 -> '162.55') as correct serialization: assert <= 3 decimals everywhere plus at least one retained third digit, rather than a strict 3-character fraction per value"

patterns-established:
  - "Pattern: backtest CLI spec-aware but legacy-default — every new spec branch is gated on `spec is not None`, so no-spec gold/BTC runs keep the identical 2-dp rounding, stats call shape, and log events"

requirements-completed: [INST-01, INST-02, INST-04]

# Metrics
duration: 12min
completed: 2026-09-08
---

# Phase 05 Plan 03: Instrument-Correct Backtest CLI — Summary

**Backtest CLI now loads the instrument spec sidecar: refuses `[live] enabled` configs with an INST-04/SAFE-03 error, fails loudly when the config's `[data] symbol` mismatches the spec's broker symbol (gold-labelled-EURJPY trap named on both sides), rounds trades.csv and the decision log at the instrument's own digits (3-dp JPY spec / 2-dp legacy), and feeds `spec.value_per_point` (910.0) + `spec.spread_price` (0.006) into `trade_stats` — the no-spec path stays byte-identical.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-09-08T15:44:00Z
- **Completed:** 2026-09-08T15:56:00Z
- **Tasks:** 2/2
- **Files modified:** 2 (1 source + 1 test file, 449-line new test module)

## Accomplishments

- **INST-04 live-refusal guard**: `main(["backtest", ...])` returns 1 with `error: backtest refuses [live] enabled=true configs (SAFE-03 / INST-04); use a dedicated *-backtest config` on any `[live] enabled=true` config, before any data load. `ai-backtest` and `live` subcommands are untouched, as the plan mandates.
- **INST-02/C4 symbol-identity guard**: a spec sidecar whose `base_symbol` differs from the config's `[data] symbol` returns 1 naming BOTH symbols and the sidecar path (e.g. `symbol=XAUUSD` vs `spec EURJPYc` → `the backtest would silently label EURJPYc bars as XAUUSD`). Config-eurjpy.toml's gold-labelled `[data] symbol` cannot pass silently once it points at a EURJPYc spec.
- **SC2 no-spec broker-CSV guard**: when no spec exists, `--m5-csv` runs derive the symbol from the `*_M5_broker.csv` basename and refuse a mismatch (BTCUSD config vs `BTCUSDc_M5_broker.csv` still passes via `base_symbol`).
- **PITFALLS A3 digit-aware output boundary**: one `digits` variable (`spec.digits` or legacy `2`) now drives both the decision-log `emit` rounding and the trades.csv price-column rounding; `r_multiple` stays at 4 dp; the ai-backtest path still rounds at hard 2 dp.
- **INST-01/03 spec economics wiring**: the backtest `trade_stats` call passes `value_per_point=spec.value_per_point` and `spread_price=spec.spread_price`; no-spec runs pass `None`/`0.0` — byte-identical to the legacy positional call. A spec run's USD P&L is now driven by tick_value/tick_size (910.0/point x lot) and closed trades are netted once for spread (verified: TP win pnl_points 0.090 gross → 0.084 net of the 0.006 one-sided spread).
- **A1/D2 sl_buffer_points handling**: points-form buffer is converted at the `run_backtest` boundary (`sl_buffer_points × spec.point` when a spec exists) and refused with a naming error when set with no spec.

## task Commits

No git repository in this workspace — each task's changes were made as direct file edits and verified by targeted pytest runs (no commit hashes exist to record).

1. **task 1: live-refusal guard, spec loading, symbol mismatch guard** — `src/trading_bot/cli.py` backtest branch + `tests/test_cli_spec.py` (helpers, fixture, refusal/mismatch/match/points-error/legacy tests) — verified `9 passed` in `tests/test_cli_spec.py`
2. **task 2: digit-aware output boundary + spec money/spread wiring** — `emit`/trades.csv `digits` rounding, spec→stats wiring, `backtest_run` log `spec_symbol=`/`spec_digits=`, digit + recorder tests — verified `27 passed` across `test_cli_spec.py test_cli.py test_cli_ai.py test_cli_live.py test_cli_ai_live.py`

**Plan metadata:** no git repo — planning/state files owned by the orchestrator; no metadata commit made.

## Files Created/Modified

- `src/trading_bot/cli.py` — import of `base_symbol`/`load_instrument_spec`; backtest-branch guard block (INST-04 refusal → spec load + `base_symbol` identity guard → `sl_buffer_points`-without-spec refusal → `digits` selection); `backtest_run` log gains `spec_symbol`/`spec_digits`; SC2 `--m5-csv` filename symbol guard (spec-less runs only); `sl_buffer = sl_buffer_points × spec.point` conversion; `emit` + trades.csv round at `digits`; `trade_stats` receives `value_per_point`/`spread_price`. No other function or subcommand touched.
- `tests/test_cli_spec.py` — created (449 lines): gold M1 histdata fixture helper, spec-aware config helper (no `spread_assumption`, `[live] enabled=false`, optional `spec_file`/`symbol`/`sl_buffer_points`), `_live_config`, `_eurjpy_fixture` (84-bar 3-dp EURJPYc M5 broker CSV + spec sidecar, golden 19-bar pattern mapped to a millipoint grid near 162.345), and 9 tests covering refusal, mismatch, match-with-points-conversion, points-without-spec error, legacy pass, 3-dp artifacts, 2-dp legacy artifacts, and spec/legacy `trade_stats` recorder assertions.

## Decisions Made

- Guard placement ahead of all data work (refusal and identity check before `list_histdata_csves`/CSV reads) so a bad config never touches the data path or emits partial artifacts.
- Symbol comparison via `base_symbol` on BOTH sides so account-type suffixes (`EURJPYc`/`EURJPYm`) never false-positive while any real instrument mismatch fails closed.
- The spec run's test config uses `sl_buffer_points = 10` (points form) so the A1/D2 conversion is exercised end to end; the test asserts per-trade risk < 1.0, which an unconverted raw-price misinterpretation (≈10.0 risk) would blow past.
- The decision-log digit assertion accepts trailing-zero 3-dp serialization (`162.55` == 162.550) — strict per-value "3 characters" falsely failed legitimate values — while still proving 3-dp retention via a global "≥1 genuine third digit" check plus trades.csv `entry != round(entry, 2)`.

## Deviations from Plan

### Environment adaptations (recorded, no code impact)

1. **[Environment - no git]** This workspace has no git repository. The mandated per-task atomic commits and the final metadata commit could not be created; all work was tracked as direct file edits with per-task pytest verification in place of commit hashes. No behavior change.
2. **[Environment - pytest temp ACL]** The default pytest temp dir and `.pytest_cache` are ACL-locked on this machine (PermissionError WinError 5). Every pytest invocation used `-p no:cacheprovider --basetemp C:\Users\joram\AppData\Local\Temp\gsd-pytest-tmp\{unique-suffix}` with a unique suffix per run, exactly as the environment facts mandate. All runs exited 0.

### Test-authoring corrections (within planned task scope)

3. **[Rule 1 - Bug in test assertion]** The planned strict decision-log assertion ("every `entry=`/`sl=`/`tp=` value parses with 3 decimals") false-failed on a legitimate value `162.55` — a 3-dp price whose third digit is zero serializes without the trailing zero. Fixed to "≤ 3 decimals per value + at least one retained third digit across the log" (plus the existing trades.csv `entry != round(entry, 2)` quantization check, which is the discriminating assertion). Tests only; no production-code change.
4. **[Rule 3 - Blocking in test fixture]** Spec sidecar paths were written into TOML as `str(WindowsPath)` (backslash form), which tomllib rejected as `Invalid hex value` on `\U` escapes. Fixed by passing `spec_path.as_posix()` into the config helper. Tests only.

---

**Total deviations:** 2 environment adaptations + 2 auto-fixed test-authoring issues
**Impact on plan:** No scope creep and no production-behavior change beyond the plan's specified cli.py edits. All four deviations were necessary to run tests on this machine and make the new assertions correct.

## Issues Encountered

- Windows `tmp_path` backslashes break TOML basic strings — resolved with `.as_posix()` paths in the test config helper.
- The 19-bar golden M5 pattern does not satisfy the plan's ≥80-bar fixture requirement by itself; the EURJPY frame pads 65 strictly-declining bars after the golden tail. Declining bars form no swing points, so no new setup can fire and the frame deterministically reproduces the golden trades (verified by prototype before the tests were written).
- Test paths under `pytest`'s tmp dir can contain the assertion keywords (e.g. `test_live_enabled...` contains "live"), which made two RED-phase tests pass spuriously via the "no CSV files found" fallback error before the guards existed. The GREEN phase verifies the guards' real messages, so the final green is meaningful; noted for future RED-phase reading.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- A researcher can now run `backtest --config <eurjpy-backtest-config>` against a broker M5 CSV + spec sidecar and get instrument-correct rounding, spec-money stats, and spread-netted results — INST-01/INST-03 are reachable end to end from the CLI.
- The SC2 filename guard is the interim protection until Phase 6 broker-fetch sidecars exist for every instrument; the spec sidecar is the authoritative source once present.
- Legacy gold/BTC CLI runs are byte-identical (2-dp artifacts, `contract_size` money path) and remain fully green; the live/demo gold+bitcoin agents are untouched.

---
*Phase: 05-instrument-correct-backtest-machinery*
*Completed: 2026-09-08*

## Self-Check: PASSED

Verified before state hand-off:

- **task 1 acceptance:** `cli.py` backtest branch contains the `cfg.live.enabled` refusal returning 1 with an INST-04 message; the `base_symbol` mismatch guard prints both symbols and returns 1; `run_backtest` receives `sl_buffer=` computed from `sl_buffer_points × spec.point`; `.\.venv\Scripts\python.exe -m pytest tests\test_cli_spec.py -q` exits 0 (9 passed).
- **task 2 acceptance:** backtest `emit` uses `round(v, digits)` and trades.csv rounds at `digits` (line 758/799); ai-backtest path still `round(v, 2)` (line 541, untouched); backtest `trade_stats` receives `value_per_point`/`spread_price` (None/0.0 without a spec); `pytest tests\test_cli_spec.py tests\test_cli.py tests\test_cli_ai.py -q` exits 0.
- **Plan verification:** `tests\test_cli_spec.py` 9 passed; `tests\test_cli.py tests\test_cli_ai.py tests\test_cli_live.py` (+ ai_live) 27 passed combined; FULL suite `530 passed, 2 skipped` (baseline 521 + 9 new, no regressions); forbidden-path check clean — no file under `strategy/`, `backtest/engine.py`, `broker/`, or `live/` modified this session (mtimes predate the session).
- **Key files exist on disk:** `src/trading_bot/cli.py`, `tests/test_cli_spec.py` (449 lines ≥ 60), `.planning/phases/05-instrument-correct-backtest-machinery/05-03-SUMMARY.md`.
- **Frontmatter:** `requirements-completed` copies `[INST-01, INST-02, INST-04]` verbatim from the plan frontmatter.
