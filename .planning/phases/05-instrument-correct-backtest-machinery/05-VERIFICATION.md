---
phase: 05-instrument-correct-backtest-machinery
verified: 2026-09-08T16:10:18Z
status: passed
score: 9/9 must-haves verified
overrides_applied: 0
overrides: []
re_verification:
  previous_status: null
  previous_score: null
  gaps_closed: []
  gaps_remaining: []
  regressions: []
gaps: []
deferred: []
human_verification: []
---

# Phase 5: Instrument-Correct Backtest Machinery Verification Report

**Phase Goal:** Researcher can backtest the breakout strategy on EURJPY/GBPJPY M5 bars with instrument-correct money/spread semantics and output rounding — while the legacy gold/BTC path stays byte-identical and every shared seam (pure strategy chain, `run_backtest` event loop, broker ABC, live engine) is untouched.
**Verified:** 2026-09-08T16:10:18Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

Must-haves merged from ROADMAP.md Success Criteria (the contract) + the four PLAN frontmatters (05-01/02/03/04). All verified against the on-disk codebase and test results.

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1   | **SC1 — Instrument-correct money + digit output.** Backtest on EURJPY/GBPJPY M5 CSVs yields trades CSV + decision log rounded at the instrument's own digits (3 dp for a JPY spec), with money per price-unit per lot from spec `tick_value / tick_size` — never gold's `contract_size`. | ✓ VERIFIED | `InstrumentSpec.value_per_point`/`spread_price` (loader.py:55-63); `trade_stats` money via single `money_per_point` factor, spec branch only (`stats.py:97`); CLI wires `spec.value_per_point`/`spec.spread_price` and rounds at `spec.digits` (`cli.py:664, 756-800`). End-to-end: `tests/test_spec.py::test_value_per_point_is_tick_value_over_tick_size` (910.0), `test_stats_spec.py::test_spec_money_uses_value_per_point` (0.91 not 0.10), `test_cli_spec.py::test_spec_run_rounds_artifacts_at_3dp` + `test_stats_receives_spec_value_per_point_and_spread` — all pass. |
| 2   | **SC2 — Loud symbol-mismatch failure.** A config/data symbol mismatch (gold-labelled-EURJPY trap) fails loudly with an error naming both symbols. | ✓ VERIFIED | `base_symbol` guard in cli.py:641-648 prints both symbols + sidecar path and returns 1 before any data load; SC2 no-spec `--m5-csv` filename guard at cli.py:714-723. `test_cli_spec.py::test_symbol_mismatch_refused` asserts "XAUUSD" AND "EURJPY" in stderr, rc 1. |
| 3   | **SC3 — Spread netted once per closed trade; dead knob retired; legacy unchanged.** | ✓ VERIFIED | `spread_assumption` removed from typed `TradingConfig` (config.py:41-44); only residue is the `pop` tolerance line (config.py:597). Netting block runs over the `closed` subset only, skipped at `spread_price == 0.0` (stats.py:85-89). `test_stats_spec.py` netting/OPEN/legacy tests + golden pins (`test_backtest.py` untouched, passes). |
| 4   | **SC4 — CLI refuses `[live] enabled` configs; dedicated backtest templates shipped.** | ✓ VERIFIED | INST-04 refusal cli.py:618-624 (returns 1, names SAFE-03/INST-04, before any data work). Templates `config-eurjpy-backtest.toml` + `config-gbpjpy-backtest.toml` exist, load cleanly, `[live] enabled=false`/`dry-run`, `sl_buffer_points=10`, per-cross `spec_file`. Direct run of `main(['backtest','--config','config/config-cent.toml'])` returns rc 1 with the guard message. Template-load tests pass. |
| 5   | **SC5 — Suite green; zero edits to golden pins / strategy / engine / broker / live; legacy gold/BTC byte-identical.** | ✓ VERIFIED | Full suite **534 passed, 2 skipped** (re-run this verification; claim matches). Golden-pin files untouched (mtimes predate session: test_backtest.py 09-02, test_cli.py 08-26, test_config.py 09-02) and pass. Forbidden paths byte-untouched (strategy/* newest 09-03, engine.py 09-02, broker/* 08-27, live/* 08-27). Legacy branch structural identity: spread block skipped at 0.0 and `money_per_point == contract_size*lot` at defaults; legacy no-spec CLI tests assert 2-dp artifacts unchanged. |
| 6   | **05-01 — Spec sidecar JSON loads into a pure InstrumentSpec; money-per-price-unit-per-lot derivable offline.** | ✓ VERIFIED | `load_instrument_spec` (loader.py:66-122) maps `trade_tick_size→tick_size` etc., validates required fields (`ValueError` naming the file's own key, `FileNotFoundError` naming path, `JSONDecodeError` propagates); frozen dataclass with `value_per_point`/`spread_price` properties. 20 `test_spec.py` tests pass incl. field mapping, property math, missing/zero-field refusals. |
| 7   | **05-01 — Every committed config TOML (incl. live gold/BTC) still loads unchanged; exactly-one-buffer-source; legacy no-spec `[data]` byte-identical.** | ✓ VERIFIED | `DataConfig.spec_file=""` optional trailing field; `StrategyConfig.sl_buffer_points`; `_validate` one-buffer-source block (config.py:405-415); legacy-key pop tolerance. config.toml, config-cent.toml, config-btc.toml, config-ai-live.toml, config-ai.toml all load (15 `test_config_instrument.py` tests pass). No pre-existing config TOML modified (mtimes predate session; only the two new templates written 09-08). |
| 8   | **05-03 — Spec present → stats receives `value_per_point` + `spread_price`; no spec → `None`/`0.0` (byte-identical call).** | ✓ VERIFIED | cli.py:786-792 keyword wiring; `test_cli_spec.py::test_stats_receives_spec_value_per_point_and_spread` (recorder asserts 910.0 / 0.006) and `test_stats_legacy_run_gets_none_and_zero`. `sl_buffer = sl_buffer_points × spec.point` conversion at the `run_backtest` boundary (cli.py:767-771), points-without-spec refused (cli.py:652-659). |
| 9   | **05-04 — Templates point at own cross + Phase-6 sidecar path, buffer in points, structurally backtest-only; live gold/BTC configs untouched.** | ✓ VERIFIED | Both templates `symbol=EURJPY`/`GBPJPY`, `spec_file=...EURJPYc/GBPJPYc_M5_broker.spec.json`, `sl_buffer_points=10`, `enabled=false`, `mode="dry-run"`, no `spread_assumption`, no `sl_buffer`. `test_config_backtest_templates.py` (4 tests) incl. live-config regression tripwire. `load_config` one-liners print `eurjpy template OK` / `gbpjpy template OK`. |

**Score:** 9/9 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `src/trading_bot/data/loader.py` | `InstrumentSpec`, `load_instrument_spec`, `base_symbol`; `load_histdata_csv` untouched | ✓ VERIFIED | Exists (137 lines); new pure code at lines 35-137; `load_histdata_csv` (lines 17-32) pre-existing and unmodified. Exported names present and exercised by tests. |
| `src/trading_bot/config.py` | `spec_file`, `sl_buffer_points`, no `spread_assumption` field, pop tolerance, one-buffer validation | ✓ VERIFIED | All present (config.py:23, 32-33, 41-44, 405-415, 596-598, 425-426). Exists, substantive, wired (every config load path). |
| `src/trading_bot/backtest/stats.py` | `trade_stats(value_per_point=None, spread_price=0.0)` spec money + netting | ✓ VERIFIED | Signature and both extensions present (stats.py:36-42); legacy defaults byte-identical; consumed by cli.py. |
| `src/trading_bot/cli.py` | Live-refusal, symbol guard, digit rounding, spec→stats wiring | ✓ VERIFIED | All four present in the backtest branch (cli.py:615-664, 756-800); ai-backtest/live subcommands untouched. |
| `config/config-eurjpy-backtest.toml` | EUR/JPY backtest template | ✓ VERIFIED | Exists (63 lines), correct symbol/spec/points-buffer, `enabled=false`, no forbidden keys. |
| `config/config-gbpjpy-backtest.toml` | GBP/JPY backtest template | ✓ VERIFIED | Exists (63 lines), structural copy with per-cross values, `enabled=false`. |
| `tests/test_spec.py` | Spec + sidecar tests (min 40 lines) | ✓ VERIFIED | 139 lines; all pass (part of 534). |
| `tests/test_config_instrument.py` | Config schema tests | ✓ VERIFIED | 229 lines; all pass. |
| `tests/test_stats_spec.py` | Legacy identity + spec money + netting tests (min 40 lines) | ✓ VERIFIED | 170 lines; all pass. |
| `tests/test_cli_spec.py` | CLI refusal/mismatch/digit/wiring tests (min 60 lines) | ✓ VERIFIED | 449 lines; 9 tests; all pass. |
| `tests/test_config_backtest_templates.py` | Template-load tests (min 25 lines) | ✓ VERIFIED | 70 lines; 4 tests; all pass. |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `config.py` schema → `data/loader.py` spec load | cli backtest path calls `load_instrument_spec(cfg.data.spec_file)` | `load_instrument_spec` import + call | WIRED | cli.py:41-45 imports, 630-635 loads and error-handles; exercised by `test_cli_spec.py`. |
| `cli.py` → `data/loader.py` symbol identity | `base_symbol(cfg.data.symbol) != base_symbol(spec.symbol)` guard | `base_symbol` | WIRED | cli.py:641-648; mismatch test proves refusal naming both symbols. |
| `cli.py` → `backtest/stats.py` money/spread | `trade_stats(..., value_per_point=spec.value_per_point, spread_price=spec.spread_price)` | `value_per_point` / `spread_price` kwargs | WIRED | cli.py:786-792; recorder tests prove 910.0/0.006 on spec runs and None/0.0 on legacy. |
| `InstrumentSpec.value_per_point` → stats money basis | spec `tick_value/tick_size` drives `money_per_point` | `value_per_point` semantics | WIRED | loader.py:55-58 property; stats.py:97 factor; `test_stats_spec.py::test_spec_money_uses_value_per_point`. |
| EURJPY ↔ GBPJPY templates | identical structure; only symbol/comment/magic differ | `sl_buffer_points` | WIRED | Verified on-disk (63 lines each, only per-cross values differ); both load. |
| Templates → `config.py` | `load_config` validates both templates | `spec_file` | WIRED | `test_config_backtest_templates.py`; load one-liners OK. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| CLI spec run | `spec` | `load_instrument_spec(cfg.data.spec_file)` reads real sidecar JSON from disk | Yes — file read, field-validated, typed | ✓ FLOWING |
| CLI spec run | `value_per_point`/`spread_price` into `trade_stats` | `InstrumentSpec` properties → stats kwargs | Yes — recorder test asserts 910.0/0.006 (not default/hardcoded) | ✓ FLOWING |
| CLI spec run | trades CSV + decision log price fields | engine trades → `round(v, digits)` with `digits = spec.digits = 3` | Yes — test proves `trades["entry"] != round(entry, 2)` and a genuine 3rd decimal survives | ✓ FLOWING |
| CLI legacy run | money + rounding | `value_per_point=None, spread_price=0.0`, `digits=2` | Yes — legacy path; 2-dp artifacts asserted; golden pins unchanged | ✓ FLOWING (byte-identical) |
| Config templates | `sl_buffer_points=10` → effective stop buffer | `sl_buffer_points × spec.point` at run_backtest boundary | Yes — test asserts per-trade risk < 1.0 (unconverted points≈10.0 would fail) | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Full test suite green (534 expected) | `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp ...\verify05-full` | `534 passed, 2 skipped in 24.68s` | ✓ PASS |
| New phase-5 tests | `pytest tests\test_spec.py test_config_instrument.py test_stats_spec.py test_cli_spec.py test_config_backtest_templates.py` | `54 passed` | ✓ PASS |
| Golden pins unchanged | `pytest test_backtest.py test_cli.py test_config.py test_ai_backtest.py test_live_engine.py` | `135 passed` | ✓ PASS |
| `[live] enabled` refusal on a real live config | `python -c "from trading_bot.cli import main; rc=main(['backtest','--config','config/config-cent.toml'])"` | rc 1, stderr: `backtest refuses [live] enabled=true configs (SAFE-03 / INST-04)` | ✓ PASS |
| JPY templates load under new schema | `load_config('config/config-eurjpy-backtest.toml')` / `gbpjpy` | `eurjpy template OK` / `gbpjpy template OK` | ✓ PASS |
| NaN refusal (edge check) | sidecar with `trade_tick_size: NaN` | Loads with `tick_size=nan` (no refusal) — **confirms review WR-01**; see Advisories | ✗ FAIL (advisory, non-blocking) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| INST-01 | 05-01, 05-02, 05-03 | Backtest with instrument-correct money/spread via pure `InstrumentSpec` (tick_value/tick_size), no changes to strategy chain or event loop | ✓ SATISFIED | loader.py InstrumentSpec + loader; stats.py `value_per_point` money path; cli.py wiring; engine.py untouched. |
| INST-02 | 05-03 | Round output at instrument digits + loud config/data symbol-mismatch detection | ✓ SATISFIED | cli.py digit boundary (spec.digits=3) + `base_symbol` mismatch guard; `test_cli_spec.py` mismatch + 3-dp tests. |
| INST-03 | 05-01, 05-02 | Net per-instrument spread once per closed trade in instrument price units, replacing dead `spread_assumption`; legacy byte-identical | ✓ SATISFIED | stats.py netting block; `spread_assumption` retired with pop tolerance; legacy tests byte-identical. |
| INST-04 | 05-03, 05-04 | Backtest CLI refuses `[live] enabled`; dedicated EURJPY/GBPJPY backtest templates | ✓ SATISFIED | cli.py:618-624 refusal; both templates shipped + load tests; live configs untouched. |

All four phase requirement IDs (INST-01–04) claimed by the four plans are accounted for and satisfied. No orphaned requirements. (NOTE: `.planning/REQUIREMENTS.md` checkbox/traceability rows for INST-02/INST-04 still read Pending — a planning-doc bookkeeping item owned by the orchestrator, not a code gap.)

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `src/trading_bot/data/loader.py` | 100-102 | `_pos` rejects `val <= 0` but `json.loads` accepts NaN/Infinity, and NaN fails all comparisons → passes validation | ⚠️ Warning (review WR-01, empirically confirmed this session) | A NaN sidecar field silently yields NaN `value_per_point`/`spread_price` and poisons every downstream stat. Only reachable with a malformed/hand-written sidecar; the Phase-6 fetch script is the realistic writer. Not a phase-goal blocker; hardening recommended before/at Phase 6. |
| No other anti-patterns | — | No TODO/FIXME/placeholder/stub/empty-return patterns in any phase-5 source file | — | — |

**Code-review findings (05-REVIEW.md, issues_found) — assessed, none critical to phase goal:**
- **WR-01** (NaN loader validation, above) — advisory; edge-input robustness gap in a phase-created function.
- **WR-02** (cli.py:695 decision log writes `sl_buffer=cfg.strategy.sl_buffer` = 0.0 on points-form runs while the effective buffer is `sl_buffer_points × spec.point` = 0.01) — SAFE-02 log-reproducibility wart on the new spec path only; legacy runs log correctly. Advisory.
- **WR-03** (`net_pnl_usd` denominated in the spec's account currency e.g. USC but hard-labelled USD; `account_currency` loaded but never consumed) — the cent-account labeling trap. Money math itself is spec-correct (SC1 met). Advisory for Phase 6/7 comparisons.
- **WR-04** (points-buffer-without-spec enforced only in the `backtest` subcommand; `live`/`ai-backtest` consumers silently read `sl_buffer=0.0`) — live/ai-backtest paths are out of scope for this backtest-only milestone (ROADMAP scope walls defer live wiring). Advisory.
- Review info items IN-01..IN-04 are documentation/convention notes; none contradicts a success criterion.
These four warnings do not fail any must-have truth; they are carried forward for the orchestrator to schedule as follow-up work (natural home: Phase 6 data-integrity hardening or a dedicated robustness plan).

### Human Verification Required

None. All five ROADMAP success criteria and all plan must-haves were verified programmatically against the on-disk codebase and a full test-suite run. Real EURJPY/GBPJPY broker data and `.spec.json` sidecars do not yet exist (they are Phase 6 deliverables — templates intentionally ship ahead of the data and validate now); an end-to-end run on real broker data is Phase 6's own success criterion, not a Phase 5 gap.

### Gaps Summary

No gaps. All 9/9 must-haves verified:
- Instrument-correct money (tick_value/tick_size), spread netting, and 3-dp output rounding are implemented and proven end-to-end via synthetic 3-dp EURJPY fixtures through the real CLI.
- The gold-labelled-EURJPY trap and `[live] enabled` configs both fail loudly before any data load.
- The legacy gold/BTC path is byte-identical by construction (all new branches gated on `spec is not None`, defaults reproduce legacy numbers exactly) and the full suite is green: **534 passed, 2 skipped** with zero edits to golden pins (`test_backtest.py`/`test_cli.py`/`test_config.py` untouched and passing) and zero diffs touching `strategy/*`, `backtest/engine.py`, `broker/*`, `live/*`, or any pre-existing config.
- The 4 code-review warnings (NaN validation, decision-log buffer provenance, account-currency labeling, central points-form validation) are real but non-blocking robustness/accuracy gaps, none of which contradicts a phase success criterion.

---

_Verified: 2026-09-08T16:10:18Z_
_Verifier: OpenCode (gsd-verifier)_
