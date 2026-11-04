# Safety pack, alerts, lower risk, gold long-veto (2026-11-04)

Owner request after the first Windows deployment of the sentiment build
("make it bulletproof"). Picked all four options offered.

## Risk (owner decisions)

- Gold cent: `max_loss_pct_per_trade` 20 -> 10 (percent sizing).
- BTC: `sizing = "fixed"` at the 0.01 minimum lot (10% kept as a ceiling) --
  the BTC breakout measured negative in every backtest variant (260928-fng).

## Gold: longs only + macro veto

`direction = "long"`, `[sentiment] mode = "veto_longs"`: long setups skipped
while DXY bullishness <= 40 (200-day MA) AND ^TNX > its 200-day MA -- the
composite from 260928-dxy (best d200 t200 b10, cleared its weaker no-OOS bar).
Fail-open on missing/stale data. At build time the veto was ACTIVE
(dxy 29.1, yields rising), so the gold bot takes no trades until that flips.

## Safety

- `[live] expected_login`: broker + preflight refuse a terminal logged in to
  another account (seen live: both accounts logged in to one terminal).
  BTC = 161700182; gold = 0 until the owner supplies its number.
- `restart_bots.bat`: waits for the bot's own `live_start`; reports NOT
  STARTED with the preflight `[FAIL]` reason (seen live: "done" while gold
  was blocked by Algo Trading off).
- `scripts/watchdog.py` (task every 5 min, pythonw, no console windows):
  Telegram alerts for task down, preflight failing, GIVING UP, bot died,
  stale decision log while the market is open, order placed/rejected/closed,
  daily loss limit, sentiment/veto change, sentiment unavailable; hourly
  repeat + recovery messages; daily summary; first run baselines (no replay).
  `config/telegram.toml` gitignored.
- `scripts/start_terminals.py` (task at logon): opens each bot's terminal
  (portable iff its install holds Config\accounts.dat), skips running ones.
  Bot tasks get `/DELAY 0001:30`.
- Runbook sections 8 (Telegram) and 9 (surviving a reboot: auto-logon, AC
  power-on, Windows Update active hours).

## Not verifiable here

The .bat files and the Windows-only branches (schtasks/tasklist parsing,
ctypes process list, CREATE_NO_WINDOW) cannot run on the Mac; logic is unit
tested, the Windows calls are not.

## Tests

664 passed, 2 skipped.
