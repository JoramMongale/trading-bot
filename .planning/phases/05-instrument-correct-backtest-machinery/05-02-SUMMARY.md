---
phase: 05-instrument-correct-backtest-machinery
plan: 02
subsystem: backtest-stats
tags: [trade_stats, instrument-spec, spread-netting, value-per-point, numpy, pytest, tdd]

# Dependency graph
requires:
  - phase: 05-instrument-correct-backtest-machinery
    provides: InstrumentSpec dataclass with value_per_point (tick_value/tick_size) and spread_price (spread_points x point) properties, plus load_instrument_spec / base_symbol in src/trading_bot/data/loader.py
provides:
  - spec-aware trade_stats: value_per_point-driven account-currency money (never contract_size when a spec is present)
  - per-closed-trade spread netting in instrument price units with net-of-spread avg_r
  - backward-compatible defaults (value_per_point=None, spread_price=0.0) byte-identical to the legacy gold/BTC path
affects: [05-03 (CLI wiring — reads spec sidecar, passes spec.value_per_point + spec.spread_price into trade_stats)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Optional spec-derived money factor (money_per_point) computed once, legacy branch keeps the exact contract_size x lot product for byte-identity"
    - "Spread netting confined to closed trades via the existing `closed` list; r_multiple recomputed from netted pnl_points with pnl/abs(risk) (algebraically identical to legacy formula, skipped at spread_price==0.0)"

key-files:
  created:
    - tests/test_stats_spec.py
  modified:
    - src/trading_bot/backtest/stats.py

key-decisions:
  - "r_multiple recompute uses pnl_points / abs(risk) with risk = entry - sl: identical to the legacy (exit-entry)/risk formula for both directions (signs cancel), and only reached when spread_price != 0 so legacy runs are numerically untouched"
  - "value_per_point is money per 1.0 price-unit per FULL lot (spec tick_value/tick_size), multiplied by lot inside money_per_point — mirrors broker SymbolRisk.money_risk/notional basis (PITFALLS A2)"
  - "Spread netting mutates closed trade pnl_points in place, exactly like the existing gross enrichment, so downstream consumers of the trade dicts see netted values consistently"

patterns-established:
  - "Pattern: single money_per_point factor = (value_per_point * lot) when spec supplied else (contract_size * lot); equity/net_pnl_usd/max_drawdown all scale through it"
  - "Pattern: per-trade spread debit applied post-enrichment only to the closed subset, keeping OPEN gross by construction"

requirements-completed: [INST-01, INST-03]

# Metrics
duration: 14min
completed: 2026-09-08
---

# Phase 05 Plan 02: Stats-Layer Spec Money + Per-Closed-Trade Spread Netting Summary

**`trade_stats` now converts account-currency money from a spec-derived `value_per_point` (tick_value/tick_size) via a single `money_per_point` factor and nets one `spread_price` debit per closed SL/TP trade in instrument price units with r_multiple recomputed net-of-spread — while `value_per_point=None, spread_price=0.0` reproduces the legacy `contract_size`-based gold/BTC output byte-identically (golden tests untouched and green).**

## Performance

- **Duration:** ~14 min
- **Started:** 2026-09-08T15:30:00Z (approx)
- **Completed:** 2026-09-08T13:44:29Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 2 (1 source, 1 test)

## Accomplishments
- Extended `trade_stats` signature with `value_per_point: float | None = None` (INST-01) and `spread_price: float = 0.0` (INST-03); all existing return keys, closed/OPEN rules, `avg_trade_bars`, `profit_factor`, and `win_rate` untouched.
- Introduced a single `money_per_point = (value_per_point * lot) if value_per_point is not None else (contract_size * lot)` factor; `equity`, `net_pnl_usd`, and `max_drawdown_usd` (via the already-scaled equity curve) all flow through it. No `contract_size * lot` product remains in the money path except the legacy branch.
- Spread netting block (`if spread_price:`) runs only over the existing `closed` list — each closed trade's `pnl_points` is reduced by `spread_price` exactly once and `r_multiple` is recomputed as `pnl_points / abs(risk)` (risk = entry − sl), making `avg_r` net of spread; OPEN trades keep gross enrichment by construction.
- Module + function docstrings document the two new params and the "spread netted once per closed trade in instrument price units; money uses spec value_per_point when supplied, else legacy contract_size (byte-identical gold/BTC)" rule.
- New 6-test spec file proves legacy identity, spec money (910.0 value_per_point → 0.91 not 0.10), once-per-closed-trade netting, net-of-spread avg_r including a short trade for direction-sign correctness, and OPEN-trade gross preservation.

## Task Commits

Each task was committed atomically:

1. **task 1: spec-aware money + spread netting in trade_stats** — `no git repo — direct file edits` (TDD: RED test write → GREEN implementation)
   - RED: `tests/test_stats_spec.py` — 5 failed (TypeError: new kwargs absent), 1 passed (legacy identity)
   - GREEN: `src/trading_bot/backtest/stats.py` — 6/6 spec tests pass; `tests/test_backtest.py` golden pin 26/26 unchanged

**Plan metadata:** `no git repo — direct file edits` (no metadata commit possible; orchestrator owns STATE.md/ROADMAP.md/REQUIREMENTS.md)

_Note: TDD RED (test) and GREEN (feat) stages were both executed; atomic commits do not exist because this workspace has no git repository. See TDD Gate Compliance below._

## Files Created/Modified
- `src/trading_bot/backtest/stats.py` - `trade_stats` signature extended with `value_per_point: float | None = None` and `spread_price: float = 0.0`; post-enrichment spread-netting loop over closed trades; single `money_per_point` factor replacing `* contract_size * lot` products; module/function docstrings updated.
- `tests/test_stats_spec.py` - New spec-layer test module (6 tests): `test_legacy_defaults_unchanged`, `test_zero_spread_and_none_value_are_legacy`, `test_spec_money_uses_value_per_point`, `test_spread_netted_once_per_closed_trade`, `test_avg_r_is_net_of_spread`, `test_open_trade_pnl_untouched`.

## Decisions Made
- **r_multiple recompute formula** (`pnl_points / abs(risk)`): the plan mandates this exact shape. For a long, `pnl = +(exit-entry)` and `risk > 0`; for a short, `pnl = -(exit-entry)` and `abs(risk) = -risk`, so both directions reduce to the existing `(exit-entry)/risk` — bit-identical at `spread_price == 0.0` (block skipped entirely then, so legacy is never even recomputed). The golden tests in `tests/test_backtest.py` are the arbiter and pass unchanged.
- **Money basis**: `value_per_point` is spec `tick_value/tick_size` (account-currency per 1.0 price unit per FULL lot); multiplied by `lot` in `money_per_point`. Mirrors `SymbolRisk.money_risk`/`notional` (broker/base.py lines 106-160) so backtest money and live sizing can never disagree (PITFALLS A2). `max_drawdown_usd` needed no extra scaling because the equity curve is already scaled by `money_per_point`.
- **OPEN-trade convention unchanged**: OPEN trades are not netted and not wins/losses, but remain in net P&L at gross — matching the existing module convention and `test_golden_stats_open_trade_included_in_net_pnl`.

## Deviations from Plan

### Environment Adaptations (documented, not code deviations)
- **No git repository** in this workspace: atomic per-task commits and the final metadata commit are impossible. All work tracked as direct file edits. In place of commit hashes, the Task Commits table records "no git repo — direct file edits".
- **pytest ACL workaround**: every pytest invocation appended `-p no:cacheprovider --basetemp C:\Users\joram\AppData\Local\Temp\gsd-pytest-tmp\{unique-suffix}` (unique per run) because the default pytest temp dir and `.pytest_cache` raise PermissionError [WinError 5] on this machine. All runs exited 0.

### Auto-fixed Issues
None — plan executed exactly as written. No Rule 1/2/3 fixes were needed; the implementation matches the plan's specified code shapes verbatim.

---

**Total deviations:** 0 code deviations (2 environment adaptations documented above)
**Impact on plan:** None — all acceptance criteria met without scope creep.

## TDD Gate Compliance

The plan is `tdd="true"` and the RED→GREEN cycle was executed in order:
1. **RED gate** — `tests/test_stats_spec.py` written first and run against the unmodified implementation: 5 failures (TypeError: unexpected keyword arguments `value_per_point`/`spread_price`), 1 pass (legacy-identity test). Failing as expected.
2. **GREEN gate** — `src/trading_bot/backtest/stats.py` extended; rerun: 6/6 new tests pass and the golden `tests/test_backtest.py` legacy pin passes unchanged (32 passed combined).
3. **REFACTOR** — not needed; no cleanup pass required.

**WARNING:** The `test(...)` (RED) and `feat(...)` (GREEN) gate commits required by the TDD gate-sequence check **cannot exist** — the workspace has no git repository (verified `git rev-parse` fails). The RED and GREEN stages were still performed as separate, verifiable steps against the file on disk. This is an environment limitation, not an execution shortcut.

## Issues Encountered
- **pytest PermissionError [WinError 5]**: default pytest temp dir (`.venv`-adjacent) and `.pytest_cache` are ACL-locked. Resolved with per-invocation `--basetemp` under `C:\Users\joram\AppData\Local\Temp\gsd-pytest-tmp\` plus `-p no:cacheprovider` (environment workaround supplied by the orchestrator).
- **No git repo**: all `git` commands fail with "not a git repository" (expected). Work tracked by direct file edits.

## Threat Model Compliance
All four STRIDE registrations from the plan hold in the implementation:
- T-05-02-01 (money_per_point selection): `value_per_point=None` → exact legacy `contract_size * lot` product; spec path activates only when a spec-derived value is passed. Mitigated.
- T-05-02-02 (spread netting scope): netting only inside the `closed` subset (`exit_reason in ("SL","TP")`); OPEN excluded by construction and pinned by `test_open_trade_pnl_untouched`; default 0.0 keeps legacy untouched. Mitigated.
- T-05-02-03 (divide-by-zero): `risk == 0` branch keeps `np.nan` in the recompute, same as the existing enrichment line. Mitigated.
- T-05-02-04 (unit confusion): accepted at this layer by design — `spread_price` is unit-agnostic; unit assertion lands in 05-03.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- 05-03 (CLI wiring) can now pass `spec.value_per_point` and `spec.spread_price` (from the InstrumentSpec sidecar loaded via `load_instrument_spec`) directly into `trade_stats`; the legacy CLI path omits both and stays byte-identical.
- The `key_links` contract (stats.py → loader.py via `value_per_point`) is satisfied at the type level: `InstrumentSpec.value_per_point` and `.spread_price` exist and match the parameter semantics exactly.
- Verification counts: new spec tests 6/6; golden `tests/test_backtest.py` + AI-backtest consumers 32/32; full suite **521 passed, 2 skipped** (baseline 515 + 6 new, no edits to any pinned test).

## Self-Check: PASSED

Verified on disk after writing this summary:
- [x] `src/trading_bot/backtest/stats.py` exists; signature contains `value_per_point: float | None = None` and `spread_price: float = 0.0`; single `money_per_point` factor present; the only `contract_size * lot` product is inside the legacy branch (line 97).
- [x] `tests/test_stats_spec.py` exists, 170 lines (≥ 40 required), 6/6 tests pass.
- [x] `tests/test_backtest.py` golden legacy pin passes UNCHANGED (26/26); `test_ai_backtest.py` stats consumers pass.
- [x] Full suite: **521 passed, 2 skipped** (baseline 515 + 6 new — zero regression, no pinned test edited).
- [x] Forbidden-path check: no files under `strategy/`, `backtest/engine.py`, `broker/`, `live/`, or legacy gold/BTC + live configs modified (only `backtest/stats.py` and the new test file changed).
- [x] No git repository (expected) — per-task commits impossible; direct file edits documented in place of hashes.

---

*Phase: 05-instrument-correct-backtest-machinery*
*Completed: 2026-09-08*
