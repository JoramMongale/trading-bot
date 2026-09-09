---
phase: 003-risk-tuning-script
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - scripts/tune_risk.py
  - tests/test_tune_risk.py
autonomous: false
user_setup: []

must_haves:
  truths:
    - "python scripts/tune_risk.py shows the current [risk] settings for both live bots (btc + cent) without modifying any file"
    - "A --set shows the exact before/after change and requires confirmation before anything is written"
    - "Editing preserves every comment and leaves all tables other than [risk] untouched"
    - "An invalid value (cap <= 0, slots < 1 or non-int, bad sizing, unknown key) is refused with an error naming the key, before any write"
    - "Changing the account-wide risk total (cap x slots summed across both bots) requires --yes and prints the cap-&-slots leverage warning"
    - "After a confirmed edit the launchd agent is restarted (unless --no-restart) and the bot returns under the new config without touching open positions"
    - "The edited config still passes load_config() validation"
  artifacts:
    - path: "scripts/tune_risk.py"
      provides: "read-only risk viewer + confirmed editor + validator + launchd restart for one tag"
      contains: "BOTS"
    - path: "tests/test_tune_risk.py"
      provides: "pure-function tests for the editor, validation matrix, account-wide budget gate, and a copy-based end-to-end set"
      contains: "max_concurrent"
  key_links:
    - from: "scripts/tune_risk.py"
      to: "scripts/health_check.py"
      via: "BOTS tag->config convention imported (same as monitor_trade.py)"
      pattern: "from health_check import BOTS"
    - from: "scripts/tune_risk.py"
      to: "src/trading_bot/config.py"
      via: "load_config validates the edited in-memory result before any write"
      pattern: "load_config"
    - from: "scripts/tune_risk.py"
      to: "launchctl bootout/bootstrap gui/$(id -u)/com.joram.trading-bot-<tag>"
      via: "restart after a confirmed edit unless --no-restart"
      pattern: "launchctl"
---

<objective>
Give the user a safe CLI to view and change the `[risk]` settings of the two
REAL-MONEY bots (`btc`: config/config-btc.toml, magic 77021; `cent`:
config/config-cent.toml, magic 77020), both 24/7 launchd-supervised on the
same account.

Purpose: today the risk knobs — `max_loss_pct_per_trade`, `max_concurrent`,
`sizing`, `max_daily_loss_pct`, `min_rr`, `lot_min`, `lot_step` — can only be
changed by hand-editing a TOML that carries real money and a launchd-supervised
bot that must be restarted to pick the change up. Every step of that is
forgettable and nothing re-checks the account-wide budget after the edit. This
script makes viewing read-only and editing a confirmed, validated, audited act:
it shows what changes, checks each value against the same rules the engine
already enforces, guards the account-wide total (cap x slots summed across
BOTH bots against the 2% standing policy), warns when the cap and slots move
out of step (measured: 8.8% -> 15.3% max drawdown for unchanged edge), and
restarts the affected agent so the change actually applies.

Output: `scripts/tune_risk.py` (the CLI), `tests/test_tune_risk.py` (tests),
and a user-run verification of the real command.
</objective>

<execution_context>
@/Users/joram/.config/opencode/get-shit-done/workflows/execute-plan.md
@/Users/joram/.config/opencode/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@scripts/health_check.py
@scripts/monitor_trade.py
@src/trading_bot/config.py
@config/config-btc.toml
@config/config-cent.toml
@.planning/quick/002-launchd-24-7-btc-gold/002-SUMMARY.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Implement scripts/tune_risk.py</name>
  <files>scripts/tune_risk.py</files>
  <action>
Create `scripts/tune_risk.py` — a stdlib-only CLI (Python >= 3.11, tomllib
available). Do NOT add any dependency; pyproject.toml has no TOML writer, so
comment-preserving edits are line-based (regex value-token replacement), which
is exactly how to keep the long policy comments in both configs intact.

Interface:

    python scripts/tune_risk.py                         # view BOTH bots, read-only
    python scripts/tune_risk.py --tag btc               # view one bot
    python scripts/tune_risk.py --tag btc --set key=value [--set key=value ...]
    python scripts/tune_risk.py --tag btc --set key=value --yes
    python scripts/tune_risk.py --tag btc --set key=value --no-restart

Exit codes: 0 ok, 2 error/refusal.

Module-level wiring (follow health_check.py / monitor_trade.py exactly):
- `ROOT = Path(__file__).resolve().parent.parent`
- `sys.path.insert(0, str(ROOT / "src"))` and `sys.path.insert(0, str(ROOT / "scripts"))`
- `from health_check import BOTS` — reuse the established tag->config
  convention (monitor_trade.py already does this; health_check's module-level
  imports are stdlib-only, so this is safe). Re-export as a module-level name
  so tests can monkeypatch `tune_risk.BOTS` to point at tmp copies.
- `from trading_bot.config import load_config`

VIEW mode (no --set; default tag "all"):
- For each bot: print tag, config path, magic number (read from [live] if
  present), and every `key = value` line of the [risk] table as loaded via
  tomllib.
- Print the account-wide total = sum over both bots of
  `max_loss_pct_per_trade * max_concurrent` and the standing policy (2.0%).
- Never write, never import MT5, never touch launchd. Exit 0.

SET mode (`--set key=value`, repeatable; requires a single --tag, NOT "all"):
1. Parse each key=value. The key must exist in the config's [risk] table
   (read with tomllib) — otherwise error listing the valid keys, exit 2.
2. Per-key validation (mirror the rules in config.py `_validate`; on any
   violation print an error NAMING the key and the rule, exit 2, nothing
   written):
   - max_loss_pct_per_trade: float, 0 < v <= 100
   - max_concurrent: int, v >= 1
   - sizing: "fixed" | "percent"
   - max_daily_loss_pct: float, 0 <= v <= 100
   - min_rr: float, v >= 0
   - lot_min / lot_step: float, v > 0
   - max_leverage: float, v >= 0 (only if the key is present in the file)
   - any other key already in the [risk] table: parse with the type its
     current value has and apply a sane positivity rule (int >= 1, float > 0,
     str unchanged); reject if it cannot be parsed as that type.
3. Build the new file content IN MEMORY only: line-based edit that touches
   ONLY the value token of `key = value` lines scoped to the [risk] section
   (track section headers while scanning; stop matching after the next
   `[table]` header). Regex per line: `^(\s*)(KEY)(\s*=\s*)(.*?)(\s*)$`.
   Preserve the indentation, spacing around `=`, comments, blank lines, all
   other tables and keys byte-for-byte. Format values: ints as ints
   (`max_concurrent = 2`, never `2.0`), floats minimally (`0.4`, `1.0`),
   strings quoted exactly like the surrounding file style.
4. Validate the in-memory result BEFORE any disk write: write it to a temp
   file in the same directory, call `load_config(temp_path)`, delete the temp
   file. If validation raises, print the error and DO NOT write. This is the
   guard that keeps the edit from ever producing a config the engine refuses.
5. Compute before/after account-wide total =
   Σ over both configs (max_loss_pct_per_trade × max_concurrent), using the
   other bot's current on-disk values. Print:
   "account-wide risk if every stop hits: X% -> Y% (standing policy 2.0%)".
6. Print the exact per-key diff (key, old value -> new value, file path).
7. Leverage warning: whenever max_concurrent or max_loss_pct_per_trade is in
   the change set, print the cap-&-slots warning: "The per-trade cap and
   max_concurrent must move TOGETHER. Raising slots without cutting the cap
   doubles the money at risk — measured 8.8% -> 15.3% max drawdown for an
   unchanged edge. That is leverage, not improvement." If slots are raised,
   append: "To keep the total constant, halve the cap in the same command."
8. Confirmation gates:
   - If the account-wide total CHANGES (before != after): require --yes.
     Print "account-wide risk total changes — re-run with --yes to confirm".
     Without --yes: abort, exit 2, nothing written. If the new total exceeds
     the 2.0% standing policy, the message must say so explicitly.
   - Otherwise (total unchanged): interactive y/N prompt, or --yes skips it.
     Any no / EOF / non-y answer: abort with nothing written, exit 0.
9. Write atomically: temp file in the same directory + os.replace over the
   config path, preserving the file mode.
10. Restart unless --no-restart:
    - label = "com.joram.trading-bot-{tag}",
      plist = ~/Library/LaunchAgents/{label}.plist
    - `launchctl bootout gui/{uid}/{label}` (ignore "no such process" — the
      agent may legitimately be stopped), then
      `launchctl bootstrap gui/{uid} {plist}` — if bootstrap fails, print its
      stderr and exit 2 (the config was already written; say so clearly).
    - Record the pre-restart bot pid from output/live_{tag}.pid, then poll
      every 10s up to 300s for that file to contain a NEW pid. On success
      print the new pid. On timeout print "restart in progress — confirm with
      `python scripts/monitor_trade.py --tag {tag}`".
    - Always print: "Restart does not touch open positions — broker-side
      SL/TP and position-open dedup are intact (verified in quick task 002)."
11. --no-restart: config written, print "config updated — agent NOT restarted
    (--no-restart); the change applies on the next agent start".
12. Docstring at the top documenting the safety model: read-only by default,
    confirmation, the mandatory --yes when the account-wide total changes,
    the leverage warning, and the restart contract.

Do NOT touch: the strategy, the engine, sizing internals, or any config
section other than [risk]. No MT5 imports, no broker calls — this script never
needs the terminal to view or edit config.
  </action>
  <verify>
python3 -m py_compile scripts/tune_risk.py && \
python3 scripts/tune_risk.py && \
python3 scripts/tune_risk.py --tag cent && \
git diff --stat config/   # must be empty: view mode is read-only
  </verify>
  <done>scripts/tune_risk.py exists; view mode prints both bots' [risk] tables
plus the account-wide total vs the 2% policy for --tag btc, --tag cent and
default (both); git confirms config/ untouched.</done>
</task>

<task type="auto">
  <name>Task 2: Tests for the editor, validator, budget gate, and copy-based e2e</name>
  <files>tests/test_tune_risk.py</files>
  <action>
Create `tests/test_tune_risk.py` following the repo's pytest conventions
(pythonpath=src already set in pyproject). Import the script as a module
(`sys.path.insert(0, str(ROOT / "scripts"))` then `import tune_risk`).
Monkeypatch `tune_risk.BOTS` to point at tmp_path copies of the real configs
so the live config files are NEVER written by tests.

Tests required:

1. Comment preservation: copy config/config-btc.toml into tmp_path, edit
   max_loss_pct_per_trade, assert the file is byte-identical to the original
   except the one value token (assert every comment line still present, the
   big policy comment blocks verbatim).
2. Section scoping: a hand-written config where another table contains a
   `max_concurrent = 99` key — the edit must NOT touch the out-of-section
   line (only the [risk] one).
3. Value formatting: max_concurrent=2 writes `2` (not `2.0`),
   max_loss_pct_per_trade=0.4 writes `0.4`.
4. Validation matrix — each must be REFUSED with the key named, and the file
   left byte-identical: max_loss_pct_per_trade=0, =-1, =101; max_concurrent=0,
   =1.5, =abc; sizing=jumbo; min_rr=-1; lot_min=0; unknown key name.
5. Account-wide total gate: with both configs at the real values
   (btc 0.5x2 + cent 1.0x1 = 2.0), changing btc cap to 0.6 (total -> 2.2) is
   flagged as a total change requiring --yes and is refused without --yes;
   a compensating change (cap 0.5 -> 0.25 AND slots 2 -> 4, total unchanged)
   is allowed without --yes but still emits the leverage warning.
6. Read-only guarantee: view mode (no --set) leaves both copied files
   byte-identical.
7. Atomicity: any validation failure or refused confirmation leaves the file
   byte-identical (nothing half-written).
8. End-to-end in-process set on copies: run
   `tune_risk.main(["--tag", "btc", "--set", "max_loss_pct_per_trade=0.4",
   "--yes", "--no-restart"])` with BOTS patched to tmp copies; assert exit 0,
   the copy is edited, comments preserved, and the result passes the real
   `load_config()` (the same validator the engine uses).

Run the full suite last: `pytest -q` must stay fully green (currently 212+).
  </action>
  <verify>
pytest tests/test_tune_risk.py -q && \
pytest -q && \
git status --short config/     # empty: live configs untouched by tests
  </verify>
  <done>All tests pass (new + full suite); every validation case is refused
with the key named and nothing written; the e2e proves the full
view-validate-edit path on a copy.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <what-built>
    The complete risk-tuning CLI (scripts/tune_risk.py) with tests green.
  </what-built>
  <how-to-verify>
1. Read-only view: run `python3 scripts/tune_risk.py` and `python3
   scripts/tune_risk.py --tag btc`. Confirm it prints the full [risk] table
   for both bots (btc cap 0.5 / slots 2, cent cap 1.0 / slots 1) and the
   account-wide total 2.0% vs the 2% policy. Confirm `git status` shows
   config/ untouched.
2. Refusal demo (safe, nothing written): run
   `python3 scripts/tune_risk.py --tag btc --set max_concurrent=0` and
   confirm it refuses naming the key, then
   `python3 scripts/tune_risk.py --tag btc --set max_concurrent=2 --yes
   --no-restart` — this is a NO-OP on btc (already 2), so it is safe: confirm
   it prints the diff + leverage warning + account-wide total and that the
   config file is unchanged afterwards.
3. Full path (only if you actually want a change): pick a real change you
   want, e.g. `python3 scripts/tune_risk.py --tag btc --set
   max_loss_pct_per_trade=0.5 --yes` — since this changes the account-wide
   total it must require --yes, then restart the agent. After the restart
   (~2-4 min stack bring-up), confirm with `python3 scripts/monitor_trade.py
   --tag btc` that the bot is healthy, that any open position is untouched,
   and that `order_placed` counts did not jump (dedup intact). If you do NOT
   want to change anything live yet, instead prove step 3 on a copy:
   `cp config/config-btc.toml /tmp/btc-test.toml`, edit the copy with the
   tool's view/validate path, and skip the real restart.
  </how-to-verify>
  <resume-signal>Type "approved" or describe what failed.</resume-signal>
</task>

</tasks>

<verification>
- View mode is read-only: git diff on config/ is empty after every view.
- Edit mode never writes until the in-memory result passes load_config.
- The account-wide total (cap x slots, both bots) is always printed and any
  change requires --yes.
- The cap-&-slots leverage warning always accompanies cap/slots changes.
- Restart uses launchctl bootout + bootstrap of the exact agent label and
  never touches open positions (broker-side SL/TP + position-open dedup).
- pytest -q fully green; live config files never written by tests.
</verification>

<success_criteria>
- `python3 scripts/tune_risk.py` gives the user a complete read-only picture
  of both live bots' risk settings and the account-wide budget.
- A confirmed, validated `--set` edits only the requested [risk] value,
  preserves every comment, passes the engine's own validator, and applies via
  a launchd restart (or is held with --no-restart).
- Unsafe or budget-changing edits are impossible without an explicit,
  warned confirmation.
</success_criteria>

<output>
After completion, create `.planning/quick/003-risk-tuning-script/003-SUMMARY.md`
</output>
