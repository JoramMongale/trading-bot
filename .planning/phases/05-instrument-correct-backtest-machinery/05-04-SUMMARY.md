---
phase: 05-instrument-correct-backtest-machinery
plan: 04
subsystem: config
tags: [python, toml, instrument-spec, config-templates, backtest-only, eurjpy, gbpjpy, INST-04]

# Dependency graph
requires:
  - phase: 05-01
    provides: DataConfig.spec_file, StrategyConfig.sl_buffer_points, retired spread_assumption tolerance in load_config (legacy-key pop), one-buffer-source + sr_lookback validation
  - phase: 05-03
    provides: backtest CLI guard that refuses [live] enabled=true configs (the structural backstop the templates are shaped around)
provides:
  - "dedicated config-eurjpy-backtest.toml EUR/JPY backtest template (INST-04): per-cross symbol, EURJPYc spec sidecar, buffer in points"
  - "dedicated config-gbpjpy-backtest.toml GBP/JPY backtest template (INST-04): per-cross symbol, GBPJPYc spec sidecar, buffer in points"
  - "tests/test_config_backtest_templates.py regression tripwire: templates load instrument-correct; live gold/BTC configs still load (PITFALLS D3/D5)"
affects: [phase 06 broker-fetch sidecars (data/processed sidecars + M5 CSVs arrive), any JPY-cross backtest milestone, live-wiring milestone that will create dedicated live configs]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "per-cross *-backtest.toml template convention (PITFALLS D3): dedicated backtest-only file per JPY instrument, live gold/BTC configs never edited"
    - "structural backtest-only shape: [live] enabled=false + mode=dry-run baked in, header states the 05-03 CLI refuses enabled=true"
    - "instrument-correct money/buffer seam: [data] spec_file names the Phase-6 broker spec sidecar; [strategy] sl_buffer_points=10 expresses the stop buffer in POINTS (spec.point × 10), not a raw-price coincidence; [trading] contract_size kept but labelled BACKTEST-LEGACY"
    - "honest UNVERIFIED-value comment discipline carried over from config-eurjpy.toml (digits/symbol to be confirmed from symbol_info() in Phase 6)"

key-files:
  created:
    - config/config-eurjpy-backtest.toml
    - config/config-gbpjpy-backtest.toml
    - tests/test_config_backtest_templates.py
  modified: []

key-decisions:
  - "Templates ship AHEAD of the Phase-6 data with empty start/end and the spec sidecar path declared but not yet present — the config must load and validate NOW so an EURJPY/GBPJPY backtest is a one-command act the moment the data lands"
  - "sl_buffer_points=10 (not sl_buffer=0.01): the 3-dp cent-account coincidence (gold 0.01 == 10 × 0.001) is expressed as intent in points so the spec, not luck, sets the buffer (PITFALLS A1/D2)"
  - "sl_buffer_points=10 mirrors the per-instrument study convention already committed in the BTC backtest template and the 05-03 spec-test fixture, keeping one buffer parameterization across instruments"
  - "Per-cross spec sidecar filenames (EURJPYc/GBPJPYc_M5_broker.spec.json) + distinct magic numbers (77022/77023) keep the two JPY templates structurally identical except symbol/comment/magic — diffable at a glance"
  - "No [ai]/[news] tables: config defaults them off (inert mock provider / never-automatic pipeline), matching the plan's 'do not add them' instruction"

patterns-established:
  - "Pattern: repo backtest-config convention extended per instrument — config-btc-backtest.toml structure (mt5-csv source, spec sidecar key, points buffer, live-disabled block, full risk block) is now the shared skeleton for every dedicated backtest template"

requirements-completed: [INST-04]

# Metrics
duration: 2min
completed: 2026-09-08
---

# Phase 05 Plan 04: Dedicated JPY Backtest Config Templates — Summary

**Two dedicated BACKTEST-ONLY config templates (EUR/JPY + GBP/JPY) ship under the Phase-5 schema: each points [data] at its own cross and Phase-6 broker spec sidecar (EURJPYc/GBPJPYc_M5_broker.spec.json), expresses the stop buffer in POINTS (sl_buffer_points=10 × spec.point) instead of a raw-price coincidence, carries [live] enabled=false + mode="dry-run" as a structural shape the 05-03 CLI guard refuses to run live, and leaves every existing config — including live gold config-cent.toml and BTC config-btc.toml — byte-untouched, proven by a four-test template-load tripwire.**

## Performance

- **Duration:** 2 min
- **Started:** 2026-09-08T13:57:10Z
- **Completed:** 2026-09-08T13:58:27Z
- **Tasks:** 2/2
- **Files modified:** 3 created (2 config templates + 1 test module); 0 pre-existing files modified

## Accomplishments

- **EUR/JPY backtest template (config/config-eurjpy-backtest.toml)**: dedicated backtest-only config for EURJPY — `[data] symbol="EURJPY"` + `spec_file="data/processed/EURJPYc_M5_broker.spec.json"`, `[strategy] sl_buffer_points=10` (10 × spec.point = 0.01 price, expressed in points), `[live] enabled=false` / `mode="dry-run"` / magic 77022, full risk block. Header documents the INST-04 structural guarantee (backtest CLI refuses `enabled=true`), spec-sidecar money semantics (never `contract_size`, kept as BACKTEST-LEGACY), and the UNVERIFIED 3-dp/cent-symbol convention that Phase 6 must confirm from `symbol_info()`. Validates cleanly under the Phase-5 schema.
- **GBP/JPY backtest template (config/config-gbpjpy-backtest.toml)**: exact structural copy with only cross-specific values changed — `symbol="GBPJPY"`, `spec_file="data/processed/GBPJPYc_M5_broker.spec.json"`, `comment="gbpjpy-backtest"`, `magic_number=77023`, `symbol="GBPJPYc"`. Same `sl_buffer_points=10`, `enabled=false`, risk block.
- **Regression tripwire (tests/test_config_backtest_templates.py)**: 4 tests — both templates load with per-cross symbol/spec/magic assertions; both are structurally backtest-only (live disabled, no `spread_assumption` attribute); and live gold/BTC account configs (config-cent.toml, config-btc.toml) still load with `live.enabled=True` — proving this plan never drifted a live config (PITFALLS D3/D5).
- **No existing config touched**: mtime scan of `config/*.toml` shows only the two new files written this session; every pre-existing config (config.toml, config-cent.toml, config-btc.toml, config-btc-backtest.toml, config-eurjpy.toml, config-ai*.toml) predates the session.

## task Commits

No git repository in this workspace — each task's changes were made as direct file edits and verified by targeted pytest runs (no commit hashes exist to record).

1. **task 1: config-eurjpy-backtest.toml template** — EUR/JPY backtest-only template created and validated — `.\.venv\Scripts\python.exe -c "from trading_bot.config import load_config; ..."` printed `eurjpy-backtest template OK`; content checks confirmed spec_file/symbol/sl_buffer_points/enabled and absence of `spread_assumption` and `sl_buffer =`
2. **task 2: config-gbpjpy-backtest.toml template + template-load tests** — GBP/JPY template + `tests/test_config_backtest_templates.py` (4 tests) — `.\.venv\Scripts\python.exe -m pytest tests\test_config_backtest_templates.py -q` → `4 passed in 0.06s`

**Plan metadata:** no git repo — planning/state files owned by the orchestrator; no metadata commit made.

## Files Created/Modified

- `config/config-eurjpy-backtest.toml` — created (74 lines): EUR/JPY dedicated backtest template; `[data]` mt5-csv + `spec_file` sidecar path + empty start/end (Phase-6 data lands later), `[strategy] sl_buffer_points=10`, `[trading] contract_size=100` labelled BACKTEST-LEGACY, `[backtest]`, `[live] enabled=false mode="dry-run" magic 77022 comment="eurjpy-backtest" symbol="EURJPYc"`, `[risk]` full block. No `spread_assumption`, no `sl_buffer`, no `[ai]`/`[news]`.
- `config/config-gbpjpy-backtest.toml` — created (74 lines): structural copy of the EURJPY template differing only in header, `[data] symbol="GBPJPY"`, `spec_file="data/processed/GBPJPYc_M5_broker.spec.json"`, `magic_number=77023`, `comment="gbpjpy-backtest"`, `symbol="GBPJPYc"`.
- `tests/test_config_backtest_templates.py` — created (70 lines): 4 template-load + regression tests (see accomplishments).

## Decisions Made

- Templates ship ahead of the Phase-6 data (empty `start`/`end`, sidecar path declared but file absent) so the config machinery is validated now and an instrument-correct run is a one-command act once the data lands — the plan's stated purpose (templates for Phase-6 data; configs load and validate now).
- `sl_buffer_points=10` in points rather than `sl_buffer=0.01` raw price: expresses buffer intent against the spec (`10 × spec.point`), eliminating the gold 0.01 == 10-points 3-dp coincidence as a justification (PITFALLS A1/D2). 10 points matches the committed BTC template and 05-03 spec-fixture parameterization.
- Distinct magic numbers per template (77022 EURJPY / 77023 GBPJPY) continue the gold-77020/bitcoin-77021 dedup convention so the one-trade-at-a-time guards can never confuse two bots' positions.
- No `[ai]`/`[news]` tables added — schema defaults render both inert, per the plan's explicit instruction.

## Deviations from Plan

### Environment adaptations (recorded, no code impact)

1. **[Environment - no git]** This workspace has no git repository. The mandated per-task atomic commits and the final metadata commit could not be created; all work was tracked as direct file edits with per-task pytest verification in place of commit hashes. No behavior change.
2. **[Environment - pytest temp ACL]** The default pytest temp dir and `.pytest_cache` are ACL-locked on this machine (PermissionError WinError 5). Every pytest invocation used `-p no:cacheprovider --basetemp C:\Users\joram\AppData\Local\Temp\gsd-pytest-tmp\{unique-suffix}` with a unique suffix per run, exactly as the environment facts mandate. All runs exited 0.

### Test-authoring note (no deviation from plan behavior)

3. The planned test module was written exactly to spec (four tests, same assertions and file paths); an unused `import pytest` was dropped during authoring since no test uses pytest.raises. Cosmetic only — no test count or assertion changed from the plan's specification.

---

**Total deviations:** 2 environment adaptations (no git, pytest temp ACL); 0 code/config deviations
**Impact on plan:** None — the plan's three new files were created exactly as specified (values/units copied verbatim from the plan's TOML blocks) and all acceptance criteria and verification checks pass. No scope creep.

## Issues Encountered

- None beyond the recorded environment constraints (no git repository; ACL-locked pytest temp/cache dirs). Both were worked around per the environment facts: direct file edits and `-p no:cacheprovider --basetemp <unique>` on every pytest run.

## User Setup Required

None - no external service configuration required. The templates' UNVERIFIED markers (digits=3/point=0.001, cent symbols EURJPYc/GBPJPYc) are resolved in Phase 6 when `scripts/fetch_broker_history.py` reads the real terminal's `symbol_info()`.

## Next Phase Readiness

- **Phase 6 broker-fetch readiness**: both JPY templates declare their spec sidecar paths (`data/processed/EURJPYc_M5_broker.spec.json` / `data/processed/GBPJPYc_M5_broker.spec.json`); when the fetch script writes the sidecars + M5 CSVs, `backtest --config config/config-eurjpy-backtest.toml` becomes a one-command instrument-correct run with no config edit.
- **Structural safety holds now**: even before the data exists, a researcher cannot accidentally turn either template live — the file shape (`enabled=false`/`dry-run`) is the only form the 05-03 CLI accepts, and the regression tests pin that shape.
- **Live gold/BTC untouched**: config-cent.toml and config-btc.toml load unchanged (tripwire green), so the running gold/bitcoin agents are unaffected by this milestone.

---
*Phase: 05-instrument-correct-backtest-machinery*
*Completed: 2026-09-08*

## Self-Check: PASSED

Verified before state hand-off:

- **task 1 acceptance:** `config/config-eurjpy-backtest.toml` exists containing `spec_file = "data/processed/EURJPYc_M5_broker.spec.json"`, `symbol = "EURJPY"`, `sl_buffer_points = 10`, `enabled = false`; file does NOT contain `spread_assumption` or `sl_buffer =`; `load_config` one-liner exits 0 printing `eurjpy-backtest template OK`.
- **task 2 acceptance:** both template files exist with `sl_buffer_points = 10`, `enabled = false`, per-cross `spec_file`; neither contains `spread_assumption` or sets `sl_buffer`; `.\.venv\Scripts\python.exe -m pytest tests\test_config_backtest_templates.py -q -p no:cacheprovider --basetemp C:\Users\joram\AppData\Local\Temp\gsd-pytest-tmp\05-04-t1` → `4 passed in 0.06s`.
- **Plan verification:** (1) template tests `4 passed`; (2) config consumers `tests\test_config.py tests\test_config_instrument.py tests\test_config_ai.py` → `60 passed`; (3) FULL suite `534 passed, 2 skipped` (baseline 530 + 4 new template tests, no regressions); (4) `config/*.toml` mtime scan shows only the two new templates written this session — all pre-existing configs (incl. live config-cent.toml, config-btc.toml) untouched.
- **Key files exist on disk:** `config/config-eurjpy-backtest.toml`, `config/config-gbpjpy-backtest.toml`, `tests/test_config_backtest_templates.py` (70 lines ≥ 25).
- **Forbidden paths clean:** no file under `strategy/`, `backtest/engine.py`, `broker/`, or `live/` modified; no existing config TOML edited.
- **Frontmatter:** `requirements-completed` copies `[INST-04]` verbatim from the plan frontmatter.
