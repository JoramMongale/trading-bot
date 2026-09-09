# AGENTS.md

## Project

Gold 5m Breakout Bot

## Workflow

This project uses the GSD workflow. Planning artifacts live in `.planning/`:

- `PROJECT.md` — project context and goals
- `REQUIREMENTS.md` — v1/v2 requirements with REQ-IDs and traceability
- `ROADMAP.md` — phases and success criteria
- `STATE.md` — current phase and progress

Follow the GSD workflow for all work: discuss → plan → execute → verify per phase. Commit planning docs to git as they change.

## Project Context

A personal Python trading bot that executes a "high probability setup" on Gold (XAUUSD) on 5-minute candles: detect support/resistance from dynamic swing points, wait for a bullish candle close above resistance, and fire a Buy Stop with 1:1 risk-reward.

- **Stack:** Python + MetaTrader5 API + pandas/numpy + TA-Lib
- **Validation order:** backtest → MT5 demo → (later) live. Live trading is a deliberate opt-in, never an accident.
- **Strategy logic lives in pure Python** so the same detection code is shared between the backtester and the live bot.

## Requirements (Active v1)

- **STRAT-01**: Dynamic support/resistance from swing highs/lows (not naive min/max)
- **STRAT-02**: Buy setup = bullish candle close above resistance, prior close ≤ resistance
- **STRAT-03**: Entry at resistance, SL below support, TP at 1:1 risk-reward
- **EXEC-01**: Connect to MT5, fetch live 5m XAUUSD bars, graceful when MT5 unavailable
- **EXEC-02**: Place Buy Stop orders with SL/TP via the MT5 API
- **EXEC-03**: Symbol, timeframe, lot, magic number, risk configurable via config file
- **SAFE-01**: Backtester runs the same strategy over historical data with trade stats
- **SAFE-02**: Structured logging of every decision to a file
- **SAFE-03**: Demo-only trading enforced unless live is explicitly enabled

## Current Focus

Phase 1 — Strategy Core: Detection + Backtest
