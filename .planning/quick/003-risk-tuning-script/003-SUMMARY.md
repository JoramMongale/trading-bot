# Quick Task 003 — Risk-tuning CLI for the two live bots

**Status:** code + tests complete (246 suite green); real-command human verification PENDING (checkpoint).

## What was built

- `scripts/tune_risk.py` — a stdlib-only CLI (Python ≥ 3.11, tomllib) to view and safely edit
  the `[risk]` settings of the two REAL-MONEY bots (`btc`: config/config-btc.toml, magic 77021;
  `cent`: config/config-cent.toml, magic 77020), both 24/7 launchd-supervised.
- `tests/test_tune_risk.py` — 22 tests covering the editor, validation matrix, account-wide
  budget gate, read-only guarantee, atomicity, and a copy-based end-to-end set. The live config
  files are NEVER written: `tune_risk.BOTS` is monkeypatched to tmp_path copies.

## The safety model

1. **Read-only by default.** `python scripts/tune_risk.py` prints both bots' `[risk]` tables,
   the magic numbers, and the account-wide total (cap x slots summed across BOTH bots) against
   the 2.0% standing policy. Never writes, never imports MT5, never touches launchd.
2. **Confirmed, validated editing.** `--set key=value` (repeatable, single `--tag`) validates
   each value against the same rules config.py enforces (naming the key on any violation),
   builds the new file content in memory via a line-based edit scoped to the `[risk]` section
   (every comment, blank line and other table preserved byte-for-byte), runs the result through
   the engine's own `load_config()` on a temp file BEFORE any write, then writes atomically
   (temp + os.replace, preserving file mode).
3. **Mandatory `--yes` on account-wide change.** Any edit that moves cap x slots summed across
   both bots (currently 2.0%) requires `--yes`; a new total above 2.0% is called out explicitly.
   Total-neutral changes use a y/N prompt (`--yes` skips it).
4. **Leverage warning.** cap or slots changes always print the 8.8% -> 15.3% drawdown warning;
   raising slots appends "halve the cap in the same command".
5. **Restart contract.** After a confirmed write the launchd agent is restarted
   (`launchctl bootout` + `bootstrap gui/$(id -u)/com.joram.trading-bot-<tag>`) unless
   `--no-restart`, with pidfile polling (up to 300s) for the new pid. Restart never touches
   open positions (broker-side SL/TP + position-open dedup intact, verified in quick task 002).

## Interface

    python scripts/tune_risk.py                          # view BOTH bots, read-only
    python scripts/tune_risk.py --tag btc                # view one bot
    python scripts/tune_risk.py --tag btc --set key=value [--set key=value ...]
    python scripts/tune_risk.py --tag btc --set key=value --yes
    python scripts/tune_risk.py --tag btc --set key=value --no-restart

Exit codes: 0 ok, 2 error/refusal.

## Test coverage (22 new, all green)

- **Comment preservation:** editing `max_loss_pct_per_trade` on a copy changes exactly ONE line
  (the value token); every comment including the long policy blocks stays verbatim.
- **Section scoping:** a hand-written config with `max_concurrent = 99` in another table — the
  edit touches only the `[risk]` one.
- **Value formatting:** `max_concurrent=2` writes `2` (not `2.0`); `0.4` writes `0.4`.
- **Validation matrix:** 12 refusals, each naming the key, file left byte-identical
  (cap 0 / -1 / 101, slots 0 / 1.5 / abc, sizing=jumbo, min_rr=-1, lot_min=0,
  max_daily_loss_pct=101, max_leverage=-0.5, unknown key).
- **Budget gate:** btc cap 0.5 -> 0.6 (total 2.0 -> 2.2) refused without `--yes`, with the
  over-policy total called out; compensating 0.25 x 4 slots passes without `--yes` but emits
  the leverage warning; a y/N decline writes nothing.
- **Read-only + atomicity:** view mode leaves copies byte-identical; every refusal leaves the
  file byte-identical.
- **Copy-based e2e:** in-process `main([... "--set", "max_loss_pct_per_trade=0.4", "--yes",
  "--no-restart"])` exits 0, edits only the copy, preserves comments, and the edited copy
  passes the real `load_config()` validator.

Full suite: **246 passed** (224 baseline + 22 new). `git status config/` empty — live configs
untouched by tests.

## Files

- `scripts/tune_risk.py` — the CLI (read-only viewer + confirmed editor + validator + launchd
  restart for one tag)
- `tests/test_tune_risk.py` — the test suite

## Deviations from plan

None of substance — plan executed as written. The no-op shortcut is a deliberate safety
behavior, not a deviation from the documented checkpoint demo: `--set max_concurrent=2` on btc
(already 2) detects "no change" and skips both the write AND the restart, which is exactly why
the plan's step 2 calls it a safe no-op.

## Human verification (pending — checkpoint task 3)

1. Read-only view: `python3 scripts/tune_risk.py` and `--tag btc` print both `[risk]` tables
   (btc cap 0.5 / slots 2, cent cap 1.0 / slots 1) and account-wide total 2.0% vs the 2%
   policy; `git status` shows config/ untouched.
2. Refusal + no-op demo (safe, nothing written): `--set max_concurrent=0` refuses naming the
   key; `--set max_concurrent=2 --yes --no-restart` is a no-op showing diff + leverage warning
   + total with the file unchanged.
3. Full path (only if a real change is wanted): e.g. `--tag btc --set
   max_loss_pct_per_trade=0.5 --yes` restarts the agent; confirm via
   `python scripts/monitor_trade.py --tag btc` (bot healthy, position untouched,
   order_placed counts stable). Otherwise prove the path on a copy.

---
*Quick task 003 — risk-tuning script*
*Completed: 2026-08-24 (tasks 1-2; task 3 verification pending)*
