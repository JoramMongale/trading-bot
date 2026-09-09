---
phase: 03-ai-trading-layer
plan: 01
subsystem: ai
tags: [deepseek, gate, mock, offline, regime]

requires:
  - phase: 1
    provides: strategy core — swing S/R detection + setup signals
  - phase: 2
    provides: live engine — LiveEngine.on_setup + placement path
provides:
  - "AI layer foundation: config, schema, providers (mock/deepseek), prompts, gate, hooks"
  - "AIEngine(LiveEngine) — daily regime check + on-setup gate"
  - "run_ai_backtest — replay history, gate each setup, report raw vs gated stats"
affects: [03-02 (live AI verification), 03-03 (warehouse AI marts), 03-04 (regime sentiment), 03-05 (dashboard AI page)]

tech-stack:
  added: [none (stdlib urllib for DeepSeek client; pandas/numpy already present)]
  patterns:
    - "Two minimal additive hooks keep backtest + live on one code path (setup_veto / _ai_gate no-op default)"
    - "Pure deterministic gate: evaluate_proposal returns APPROVED/BLOCKED/REJECTED with a reason"

key-files:
  created:
    - src/trading_bot/ai/__init__.py
    - src/trading_bot/ai/schema.py
    - src/trading_bot/ai/base.py
    - src/trading_bot/ai/mock.py
    - src/trading_bot/ai/deepseek.py
    - src/trading_bot/ai/context.py
    - src/trading_bot/ai/prompts.py
    - src/trading_bot/ai/gate.py
    - src/trading_bot/ai/engine.py
    - src/trading_bot/ai/backtest.py
    - prompts/trade_idea.txt
    - prompts/regime_check.txt
    - tests/test_ai_schema.py
    - tests/test_ai_mock.py
    - tests/test_ai_gate.py
    - tests/test_ai_context.py
    - tests/test_ai_deepseek.py
    - tests/test_ai_engine.py
    - tests/test_ai_backtest.py
    - tests/test_ai_hooks.py
  modified:
    - src/trading_bot/config.py
    - src/trading_bot/backtest/engine.py
    - src/trading_bot/live/engine.py

key-decisions:
  - "AI proposes, deterministic code disposes — the gate can veto (no_idea / low_confidence / bias_mismatch / invalid_invalidation) but cannot widen a stop or change order arithmetic"
  - "Cadence: on every deterministic setup (trade idea) + once per day (regime, can suppress setups)"
  - "Offline-first: provider=mock is the default and the whole layer runs with zero API keys / network; RecordingAIClient gives audit"
  - "Two hooks (backtest setup_veto, live _ai_gate) default to no-ops so the existing suite stays byte-identical"

patterns-established:
  - "Gate is pure and deterministic — evaluate_proposal has no logging, no broker access, no provider imports"
  - "DeepSeek client is OpenAI-compatible chat/completions over stdlib urllib — no SDK dependency"

requirements-completed: [AI-01, AI-02, AI-03, AI-04, AI-05]

# Metrics
duration: n/a (backfilled 2026-08-28 from recorded evidence)
completed: 2026-08-26
---

# Phase 03: AI Trading Layer — Plan 01 Summary

**AI-layer foundation, end to end offline: config + schema + providers (mock/deepseek) + prompts + a pure deterministic gate + AIEngine(LiveEngine) regime/on-setup integration + run_ai_backtest — delivered behind `[ai] enabled` with the existing suite unchanged (93 new tests, full suite 380 passed + 2 skipped)**

*Backfilled 2026-08-28 during Phase 4 completion (plan 03-05). The original
SUMMARY.md was never written to disk; this reconstructs the record from the
plan file's own completion status, the in-repo artifacts, and STATE.md/ROADMAP.md
entries.*

## Performance

- **Duration:** n/a (recorded as complete 2026-08-26)
- **Completed:** 2026-08-26
- **Tasks:** (plan-verified) — see the plan's task breakdown
- **Files modified/created:** ~21 (10 ai module files + 2 prompts + 9 test files + 3 modified)

## Accomplishments

- **`[ai]` config** (AIConfig): enabled, provider (mock|deepseek), model, api_base, api_key_env, temperature, max_tokens, timeout, min_confidence, require_agreement, regime_check_daily, block_when_choppy, record_calls, prompt_dir — with per-key validation; legacy configs without `[ai]` load unchanged (off by default).
- **Schema + strict parsing** (`ai/schema.py`): AIProposal / RegimeAssessment dataclasses with strict JSON parsing so a malformed model reply is a recoverable error, never a crash.
- **Providers** (`ai/base.py`, `ai/mock.py`, `ai/deepseek.py`): AIClient ABC (propose_trade / assess_regime) + AIClientError; MockAIClient (offline, deterministic) + RecordingAIClient (audit); DeepSeekClient via OpenAI-compatible chat/completions over stdlib urllib.
- **Context + prompts** (`ai/context.py`, `ai/prompts.py`): TradeContext / RegimeContext builders (pure, from bars+levels) rendering the `prompts/trade_idea.txt` and `prompts/regime_check.txt` templates.
- **Pure gate** (`ai/gate.py`): `evaluate_proposal` → APPROVED/BLOCKED/REJECTED — bias != NONE (else no_idea), confidence >= min_confidence (else low_confidence), bias agrees with setup when require_agreement (else bias_mismatch), invalidation must not widen the stop and must sit on the risk side (else invalid_invalidation).
- **Two minimal additive hooks**: `run_backtest(..., setup_veto=None)` in backtest/engine.py (returned reason skips arming + emits setup_skipped) and `LiveEngine.on_setup` calls `self._ai_gate(...)` (default no-op returns None — unchanged behavior). Hooks are no-ops by default so the pre-AI suite stays green.
- **AIEngine(LiveEngine)**: `_ai_gate` builds the trade context, asks for a proposal, runs the gate, logs `ai_proposal` / `ai_rejected` / `ai_blocked`, returns the skip event or None to proceed; `_maybe_regime_check` runs the daily regime assessment that can suppress setups for the day.
- **`run_ai_backtest`** (`ai/backtest.py`): replay history, gate each setup, report raw vs AI-gated stats.
- Full suite: **380 passed + 2 skipped** with the 93 new AI tests (recorded in the plan's own status line and STATE.md).

## Task Commits

*No git repository present in this workspace — per-task atomic commits could not be created. Verification was via the AI test suite and the full-suite run.*

## Files Created/Modified

- `src/trading_bot/ai/` — schema.py, base.py, mock.py, deepseek.py, context.py, prompts.py, gate.py, engine.py, backtest.py, `__init__.py`
- `prompts/trade_idea.txt`, `prompts/regime_check.txt`
- `src/trading_bot/config.py` — AIConfig + DEFAULT_AI + validation + load_config wiring
- `src/trading_bot/backtest/engine.py` — setup_veto seam
- `src/trading_bot/live/engine.py` — `_ai_gate` hook (default no-op)
- `tests/test_ai_{schema,mock,gate,context,deepseek,engine,backtest,hooks}.py` (93 tests)

## Decisions Made

- **"AI proposes, deterministic code disposes"** — the AI layer is a filter and reasoner over the deterministic setup; it can veto but never widen a stop or change order arithmetic. The deterministic system keeps full authority over risk and execution.
- **Two minimal no-op hooks over a parallel path** — backtest and live share one code path via `setup_veto` / `_ai_gate`; the default None/no-op keeps every existing call byte-identical (SAFE-01).
- **Offline-first** — `provider = "mock"` is the default; the whole layer runs with zero API keys and zero network. Real DeepSeek is an explicit opt-in.
- **Gate purity** — evaluate_proposal is a pure function (no logging, no broker access, no provider import) so it is trivially testable and provably deterministic.

## Deviations from Plan

None recorded. This is a backfilled summary; the plan's status line reported the phase verified with no gap-closure needed.

## Issues Encountered

- The original SUMMARY.md was not persisted when the plan completed on 2026-08-26; this backfill reconstructs it from the plan file, the in-repo `src/trading_bot/ai/` + tests artifacts, and the STATE.md/ROADMAP.md records.

## User Setup Required

None. `[ai] enabled` stays off by default; real-DeepSeek use needs `DEEPSEEK_API_KEY` (or the configured api_key_env).

## Next Phase Readiness

- Ready for 03-02 (live AI verification): the config/provider/gate/hooks all exist; `live --provider {mock,deepseek}` and config-ai-live.toml built on this foundation.
- Ready for 03-03 (warehouse AI marts) and 03-04 (regime sentiment): AIEngine logs `ai_proposal`/`ai_rejected`/`ai_blocked` per SAFE-02 for the loader, and RegimeContext is the seam the news sentiment block extends.

---
*Phase: 03-ai-trading-layer*
*Completed: 2026-08-26 (backfilled 2026-08-28)*
