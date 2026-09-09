---
phase: 05-instrument-correct-backtest-machinery
reviewed: 2026-09-08T00:00:00Z
depth: standard
files_reviewed: 17
files_reviewed_list:
  - src/trading_bot/data/loader.py
  - src/trading_bot/config.py
  - src/trading_bot/backtest/stats.py
  - src/trading_bot/cli.py
  - tests/test_spec.py
  - tests/test_config_instrument.py
  - tests/test_stats_spec.py
  - tests/test_cli_spec.py
  - tests/test_config_backtest_templates.py
  - tests/test_ai_backtest.py
  - tests/test_ai_context.py
  - tests/test_ai_engine.py
  - tests/test_ai_hooks.py
  - tests/test_live_engine.py
  - tests/test_safety.py
  - config/config-eurjpy-backtest.toml
  - config/config-gbpjpy-backtest.toml
findings:
  critical: 0
  warning: 4
  info: 4
  total: 8
status: issues_found
---

# Phase 05: Code Review Report

**Reviewed:** 2026-09-08
**Depth:** standard
**Files Reviewed:** 17
**Status:** issues_found

## Summary

Reviewed the Phase 5 instrument-correct backtest machinery as its complete on-disk change (no git repo): the `InstrumentSpec`/sidecar loader + `base_symbol()` in `data/loader.py`, config schema growth in `config.py`, spec-money + spread-netting in `backtest/stats.py`, the backtest CLI guard/wiring in `cli.py`, the six mechanical fixture edits, the new spec/config/stats/cli test modules, and the two JPY backtest template configs.

The implementation matches the plan intent closely, the legacy no-spec paths are well pinned (golden tests in `tests/test_backtest.py`, `test_cli.py`, `test_config.py`, and all six AI/live fixtures re-ran green — 172 targeted tests + 54 new spec tests pass), and the forbidden paths (`strategy/`, `backtest/engine.py`, `broker/`, `live/`) are untouched. The loader's `_pos` zero-refusal, the stats legacy `money_per_point` branch, and the CLI symbol-identity guard are all implemented as specified.

No CRITICAL (security/data-loss) defects were proven. The warnings below are real robustness/correctness gaps: NaN/Infinity slip through the loader's "refuse nonsense" validation and silently poison every stat; the SAFE-02 decision log misrecords the stop buffer actually used on points-form runs; the account-currency unit of `net_pnl_usd` is mislabeled and never checked (the exact cent-account trap `broker/base.py` already warns about); and the points-buffer-without-spec rule is enforced only in the `backtest` subcommand, leaving `live`/`ai-backtest` consumers to silently run with a 0.0 buffer.

## Warnings

### WR-01: Loader accepts non-finite (NaN/Infinity) economics — NaN spread silently poisons every stat

**File:** `src/trading_bot/data/loader.py:100-102` (and `:111`)
**Issue:** `_pos` rejects `val <= 0` but Python's lenient `json.loads` accepts the non-standard `NaN`/`Infinity` tokens, and NaN fails every comparison so it passes the check. Verified empirically: a sidecar with `"trade_tick_size":NaN` loads an `InstrumentSpec` with `tick_size=nan` (→ `value_per_point=nan`); a sidecar with `"spread_points_median":NaN` loads `spread_points=nan`. This then corrupts the stats layer silently: `bool(float("nan"))` is `True`, so the netting guard `if spread_price:` in `stats.py:85` fires, `t["pnl_points"] -= nan` turns every closed trade's P&L into NaN, and `net_pnl_points`/`net_pnl_usd`/`avg_r` all report NaN with no error. A median spread computed over an empty/failed tick sample at Phase-6 fetch time is exactly the realistic source of a NaN in this file. A non-numeric string spread also raises a bare `ValueError: could not convert string to float` that names no key. This undercuts the function's own documented contract ("refuse, never divide", zero-refusal mirroring `SymbolRisk`).
**Fix:**
```python
import math

def _pos(key: str):
    val = _req(key)
    if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val) or val <= 0:
        raise ValueError(f"spec {path.name}: invalid {key}")
    return val

# spread: validate finite and >= 0, naming the sidecar's own key
spread_raw = data.get("spread_points_median", data.get("spread_points", 0.0))
if isinstance(spread_raw, bool) or not isinstance(spread_raw, (int, float)) or not math.isfinite(spread_raw) or spread_raw < 0:
    raise ValueError(f"spec {path.name}: invalid spread_points_median")
```

### WR-02: Decision log misrecords the stop buffer on points-form spec runs

**File:** `src/trading_bot/cli.py:695` (vs. the effective buffer at `:767-771`)
**Issue:** The `backtest_run` log line writes `sl_buffer=cfg.strategy.sl_buffer`, but when a config uses the points form (`sl_buffer_points=10`) — exactly what the two new JPY templates ship — `cfg.strategy.sl_buffer` is `0.0` while the value actually passed to `run_backtest` is `sl_buffer_points * spec.point` (`0.01`). The SAFE-02 audit trail therefore records the run as having used no stop buffer at all, and neither `sl_buffer_points` nor `spec.point` is logged, so the logged run is not reproducible from the log. On a gold no-spec run the log is correct; only the new spec path is wrong.
**Fix:** log the effective value and its provenance:
```python
sl_buffer_effective = (cfg.strategy.sl_buffer_points * spec.point
                       if (spec is not None and cfg.strategy.sl_buffer_points > 0)
                       else cfg.strategy.sl_buffer)
# in log_decision: replace sl_buffer=cfg.strategy.sl_buffer with
sl_buffer=sl_buffer_effective,
sl_buffer_points=cfg.strategy.sl_buffer_points,
```

### WR-03: `net_pnl_usd` is denominated in the spec's account currency but hard-labeled USD

**File:** `src/trading_bot/backtest/stats.py:40,138` and `src/trading_bot/cli.py:78` (label "Net P&L (USD)"); `src/trading_bot/data/loader.py:53,112` (`account_currency` captured but never consumed)
**Issue:** `InstrumentSpec.account_currency` is loaded and discarded; `trade_stats` and the CLI never look at it. Money math via `value_per_point = tick_value / tick_size` yields amounts in the *account/deposit* currency — for the fixture this phase itself ships (`EURJPYc`, `account_currency: USC`), results are in USC (cents), i.e. 100x smaller than the printed "USD" label. A researcher comparing a cent-account JPY spec run against a legacy gold run (whose `contract_size=100` path is USD-calibrated) reads both as "USD" on different scales. This is precisely the cent-account trap `broker/base.py:138-152` documents as the reason `SymbolRisk` never hardcodes a currency. At minimum a spec run whose `account_currency != "USD"` should not print a USD-labeled stat without conversion or explicit labeling.
**Fix:** propagate `spec.account_currency` into the CLI/stats boundary and (a) label the printed/logged stat with the actual currency, or (b) convert USC→USD, or (c) refuse a spec run with a non-USD account currency when emitting a `*_usd` key — with a test pinning the chosen convention.

### WR-04: `sl_buffer_points`-without-`spec_file` is refused only by the `backtest` subcommand; `live`/`ai-backtest` silently run a 0.0 buffer

**File:** `src/trading_bot/cli.py:652-659` (the only enforcement point); `src/trading_bot/config.py:405-415` (validation accepts the combination); consumers `src/trading_bot/live/engine.py:368` and `src/trading_bot/ai/backtest.py:83`
**Issue:** `_validate` enforces "exactly one buffer source" but not "points form requires a spec". A config carrying `sl_buffer_points=10` with no `spec_file` loads cleanly, and only the `backtest` subcommand refuses it. The `live` engine and `run_ai_backtest` read only `cfg.strategy.sl_buffer`, which is `0.0` in every points-form config — so if a points-form config (or a copy of the new JPY template with `[live]` flipped) ever reaches those paths, stops are placed exactly on the support/resistance level with zero buffer, and the ai-backtest stats path silently runs the legacy `contract_size` money/2-dp boundary with no symbol guard. The central choke point (`_validate`) has `cfg.data.spec_file` available and is the correct place to close this.
**Fix:** in `config.py _validate`, add `if cfg.strategy.sl_buffer_points > 0 and not cfg.data.spec_file: raise ValueError("strategy.sl_buffer_points requires [data] spec_file ...")`, and keep the CLI error as a second, earlier-and-clearer line for the same case.

## Info

### IN-01: TIME-exited trades are economically closed but never spread-netted

**File:** `src/trading_bot/backtest/stats.py:56,85-89`
**Issue:** `closed` is `exit_reason in ("SL","TP")` (documented convention), so a trade closed by a time stop (`max_hold_bars`, engine `exit_reason="TIME"`) is excluded from wins/losses but included in net P&L at *gross* even when `spread_price>0` — the spread is charged exactly once per SL/TP closed trade but zero times for a TIME close. Latent today (no committed config sets `max_hold_bars`, and the CLI never passes it), but the netting rule "spread netted once per CLOSED trade" is silently violated the moment a spec run uses a time stop. Worth documenting in the netting bullet or extending `_CLOSED_REASONS` consistently.

### IN-02: A *-backtest config cannot name its M5 broker CSV — the promised one-command run still needs `--m5-csv`

**File:** `src/trading_bot/cli.py:703-727`; `config/config-eurjpy-backtest.toml:17-24`
**Issue:** The new templates declare `[data] spec_file` but the CLI only auto-discovers histdata `DAT_ASCII_*` files (`list_histdata_csves` globs `cfg.data.symbol`); the Phase-6 broker CSV (`EURJPYc_M5_broker.csv`) must be passed via `--m5-csv` every run. `[data] source = "mt5-csv"` and `raw_dir` are not consulted for the CSV filename, so the summary's "one-command run with no config edit" is not what the shipped seam delivers. Consider resolving the M5 CSV from the spec path (`<spec_file_stem>.csv` next to the sidecar) when `--m5-csv` is absent.

### IN-03: "No CSV files found" fallback message is gold-specific for JPY/cross configs

**File:** `src/trading_bot/cli.py:673-677`
**Issue:** When a JPY/cross backtest config finds no histdata files (the normal state before Phase-6 data lands), the error prints the histdata.com XAUUSD download hint, which is misleading for an EURJPY/GBPJPY config that should be pointed at a broker-fetched `--m5-csv`. Cosmetic, but this exact path is what a researcher hitting the new templates first sees.

### IN-04: `trades.csv` `pnl_points` is net of spread with no column documenting the debit

**File:** `src/trading_bot/cli.py:798-803`; netting mutation at `src/trading_bot/backtest/stats.py:88`
**Issue:** On spec runs the CSV's `pnl_points` is reduced by the spread, but `entry`/`exit_price` remain gross, so `pnl_points != exit_price - entry` and the debit is invisible to any downstream consumer (the phase summary itself lists warehouse/ledger consumers of `trades.csv`). A reader or tool recomputing P&L from prices gets a different number than the recorded `pnl_points`. Consider writing the spread as an explicit per-trade column (e.g. `spread_cost`) or documenting the convention in the CSV header/README.

---

_Reviewed: 2026-09-08_
_Reviewer: OpenCode (gsd-code-reviewer)_
_Depth: standard_
