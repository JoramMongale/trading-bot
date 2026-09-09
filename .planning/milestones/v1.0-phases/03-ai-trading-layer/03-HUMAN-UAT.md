---
status: partial
phase: 03-ai-trading-layer
source: [03-VERIFICATION.md]
started: 2026-08-28
updated: 2026-08-28
---

## Current Test

[awaiting human testing]

## Tests

### 1. Dashboard visual + interactive check (Approved 2026-08-28)
expected: Five pages (Overview, Ledger, AI, Risk, News) render the dark zinc/slate shell, tables, badges and sparklines with real data — Overview shows bot health rows + open positions, Ledger the 349-row trade table, AI the gate activity + sparkline, Risk the cent/btc [risk] tables read-only, News the sentiment score + headlines.
result: approved — user confirmed the five pages render correctly with real data at http://127.0.0.1:3000.

### 2. Real-DeepSeek dry-run (re-confirmation, optional)
expected: With DEEPSEEK_API_KEY set, `python -m trading_bot.cli live --config config/config-ai-live.toml --mode dry-run --once --provider deepseek` parses a genuine model reply through the deterministic gate (03-02 recorded BLOCKED low_confidence 65<70 as the designed outcome); no order placed (dry-run).
result: [pending]

## Summary

total: 2
passed: 1
issues: 0
pending: 1
skipped: 1
blocked: 0

## Gaps
