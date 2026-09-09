"""A safe CLI to view and change the risk settings of the two REAL-MONEY bots.

    python scripts/tune_risk.py                              # view BOTH bots, read-only
    python scripts/tune_risk.py --tag btc                    # view one bot
    python scripts/tune_risk.py --tag btc --set key=value [--set key=value ...]
    python scripts/tune_risk.py --tag btc --set key=value --yes
    python scripts/tune_risk.py --tag btc --set key=value --no-restart

Keys are DOTTED and may reach two tables:
    [risk]     bare keys (max_loss_pct_per_trade, max_concurrent, ...)
    [strategy] strategy.rr_multiple (the TP/SL ratio knob, quick task 004)
A bare key means [risk]; use ``strategy.rr_multiple=2.0`` for the strategy
table. A single --set command may touch both tables.

Exit codes: 0 ok, 2 error/refusal.

Safety model
------------
* READ-ONLY BY DEFAULT. View mode opens the configs, prints the [risk] table
  of each bot plus [strategy] rr_multiple and the account-wide budget
  (cap x slots summed across BOTH bots against the 2.0% standing policy), and
  writes nothing — no config file, no MT5 import, no launchd. Viewing can
  never change a live bot.

* EDITING IS A CONFIRMED, VALIDATED, AUDITED ACT. A --set:
    1. parses each key=value and refuses unknown keys (listing the valid ones
       for that table);
    2. validates every value against the same rules config.py enforces, naming
       the key on any violation;
    3. builds the new file content IN MEMORY with a line-based edit that
       touches ONLY the value token of the key — every comment, blank line
       and other table is preserved byte-for-byte;
    4. passes the in-memory result through the engine's own load_config()
       validator (via a temp file) BEFORE anything is written;
    5. prints the account-wide risk total, the exact per-key diff, and the
       cap-&-slots leverage warning;
    6. requires --yes whenever the account-wide total changes, and prints the
       leverage warning whenever cap or slots move; only then writes the file
       atomically (temp + os.replace, preserving the file mode).

* MANDATORY --yes ON ACCOUNT-WIDE CHANGE. The standing policy is 2.0% of the
  account (btc 0.5% x 2 + cent 1.0% x 1). Any edit that moves cap x slots
  summed across both bots REQUIRES --yes; a new total above 2.0% is called out
  explicitly. Without --yes the command aborts and nothing is written.

* AGGRESSIVE SETTINGS WARN LOUDLY BUT ARE ALLOWED (quick task 004). Settings
  in the 'maximum/aggressive' tier — rr_multiple >= 1.5, a per-trade cap
  >= 10%, or an account-wide total > 5% — print a loud WARNING banner with the
  measured evidence BEFORE the confirmation. The warning never blocks: it
  accompanies the same --yes gate, and --yes proceeds.

* THE LEVERAGE WARNING. The per-trade cap and max_concurrent must move
  TOGETHER: raising slots without cutting the cap doubles the money at risk
  (measured 8.8% -> 15.3% max drawdown for an unchanged edge). The warning
  always accompanies a cap or slots change.

* THE RESTART CONTRACT. After a confirmed write the launchd agent for the tag
  is restarted (launchctl bootout + bootstrap of
  com.joram.trading-bot-<tag>) unless --no-restart, so the change actually
  applies. The restart does NOT touch open positions: SL/TP are broker-side
  and the position-open dedup is intact (verified in quick task 002). On
  --no-restart the config is written and the change applies on the next agent
  start.

This script never imports MetaTrader5 and never talks to the broker — it only
needs the config files on disk.
"""

import argparse
import os
import re
import subprocess
import sys
import time
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

# Reuse the established tag -> config convention (health_check.py). Re-exported
# as a module-level name so tests can monkeypatch tune_risk.BOTS to point at
# tmp copies — the live configs are NEVER written by tests.
from health_check import BOTS  # noqa: E402

# The engine's own validator: the edited in-memory result must pass it BEFORE
# anything is written, so the edit can never produce a config the engine
# refuses to load.
from trading_bot.config import load_config  # noqa: E402

STANDING_POLICY_PCT = 2.0

# The only tables this tool may edit. A dotted --set key must name one of
# these sections — the tool is a risk/strategy editor, not a general TOML
# editor, and editing [data]/[trading]/[backtest]/[live] values is out of
# scope (and out of its safety model).
_EDITABLE_SECTIONS = ("risk", "strategy")

# Per-key validation, mirroring config.py RiskConfig._validate and
# StrategyConfig validation. (kind, ok, rule). kind: how the CLI string is
# parsed before the ok() check runs. Keys are FULL DOTTED names so [risk] and
# [strategy] rules live in one map; a bare --set key resolves to "risk.<key>"
# for backward compatibility.
_KNOWN_RULES = {
    "risk.max_loss_pct_per_trade": (
        "float",
        lambda v: 0 < v <= 100,
        "must be > 0 and <= 100",
    ),
    "risk.max_concurrent": ("int", lambda v: v >= 1, "must be >= 1"),
    "risk.sizing": (
        "str",
        lambda v: v in ("fixed", "percent"),
        "must be 'fixed' or 'percent'",
    ),
    "risk.max_daily_loss_pct": (
        "float",
        lambda v: 0 <= v <= 100,
        "must be >= 0 (0 disables) and <= 100",
    ),
    "risk.min_rr": ("float", lambda v: v >= 0, "must be >= 0 (0 disables)"),
    "risk.lot_min": ("float", lambda v: v > 0, "must be > 0"),
    "risk.lot_step": ("float", lambda v: v > 0, "must be > 0"),
    "risk.max_leverage": ("float", lambda v: v >= 0, "must be >= 0 (0 disables)"),
    # Mirrors config.py StrategyConfig: rr_multiple <= 0 raises there, so an
    # edit that slips past this rule still fails the load_config gate.
    "strategy.rr_multiple": ("float", lambda v: v > 0, "must be > 0"),
}

_LEVERAGE_WARNING = (
    "WARNING: The per-trade cap and max_concurrent must move TOGETHER. "
    "Raising slots without cutting the cap doubles the money at risk — "
    "measured 8.8% -> 15.3% max drawdown for an unchanged edge. "
    "That is leverage, not improvement."
)

# Aggressive-tier warnings (quick task 004). These are loud banners printed
# BEFORE the confirmation; they never block — an aggressive setting still
# requires --yes exactly like a changed account-wide total, and --yes proceeds.
_AGGRESSIVE_RR_WARNING = (
    "WARNING: rr_multiple >= 1.5 is an AGGRESSIVE target — the measured edge "
    "gets thinner, not stronger.\n"
    "  Measured on 100k broker-native XAUUSDm M5 bars "
    "(2025-03-24 -> 2026-08-20):\n"
    "    rr 1.0: 437 trades, 58.4% win, net R +0.091, max DD $589\n"
    "    rr 1.5: 294 trades, 49.3% win, net R +0.147, max DD $782\n"
    "    rr 2.0: 235 trades, 43.8% win, net R +0.230, max DD $990\n"
    "  Full-span net R rises, but split-sample the edge is FRONT-LOADED: the\n"
    "  recent half gives t ~ 0.7 for EVERY ratio — indistinguishable from\n"
    "  zero. Win rate falls to ~44% at 2.0 and weekend-gap exposure triples\n"
    "  (21% of trades hold >2.5 days; gold is shut Fri 21:00 -> Sun 21:00\n"
    "  UTC)."
)

_AGGRESSIVE_LOSS_WARNING = (
    "WARNING: max_loss_pct_per_trade >= 10 is an AGGRESSIVE per-trade cap.\n"
    "  At 10% a 4-loss streak is -35% of the account, and the 6,541-trade\n"
    "  measurement puts net edge at -0.0156R (NEGATIVE net of spread) — the\n"
    "  losses are not subsidised by wins. Raising slots on top of this\n"
    "  doubled measured max drawdown 8.8% -> 15.3% for an unchanged edge."
)

_AGGRESSIVE_TOTAL_WARNING = (
    "WARNING: account-wide risk total > 5% (sum of cap x slots across bots).\n"
    "  The bots share one balance and trade correlated instruments, so the\n"
    "  SUM is the exposure, not each bot's cap in isolation. Above 5% a\n"
    "  correlated stop-out costs 5%+ of the account in one day."
)


def _split_key(key: str) -> tuple[str, str]:
    """'section.name' -> ('section', 'name'); a bare key -> ('risk', key).

    Dotted keys let --set reach [strategy] (e.g. strategy.rr_multiple); bare
    keys keep meaning [risk] so every existing command and test still works.
    """
    if "." in key:
        section, _, name = key.partition(".")
        return section, name
    return "risk", key


def _aggressive_warnings(changes: dict, total_after: float) -> list[str]:
    """Loud banners for 'maximum/aggressive' tiers of the edited settings.

    Warnings never block — they accompany the existing --yes gate (an
    aggressive change requires --yes exactly like a changed account-wide
    total, and --yes proceeds).
    """
    warns = []
    rr = changes.get("strategy.rr_multiple")
    if rr is not None and rr >= 1.5:
        warns.append(_AGGRESSIVE_RR_WARNING)
    cap = changes.get("risk.max_loss_pct_per_trade")
    if cap is not None and cap >= 10:
        warns.append(_AGGRESSIVE_LOSS_WARNING)
    if total_after > 5.0:
        warns.append(_AGGRESSIVE_TOTAL_WARNING)
    return warns


def _resolve(cfg_path):
    """BOTS values are repo-relative; tests point at absolute tmp copies."""
    p = Path(cfg_path)
    return p if p.is_absolute() else ROOT / p


def _read_risk(path):
    """(raw [risk] dict, magic from [live] or "-") via tomllib — no validation."""
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    risk = raw.get("risk", {})
    magic = raw.get("live", {}).get("magic_number", "-")
    return risk, magic


def _read_sections(path):
    """The whole raw TOML as {section: {key: value}} — no validation.

    Lets set_risk check dotted keys against their own table ([risk] or
    [strategy]) instead of assuming everything lives in [risk].
    """
    with open(path, "rb") as f:
        return tomllib.load(f)


def _account_total():
    """Σ over BOTS of (cap x slots) from disk, plus per-tag (cap, slots).

    Returns (total, {tag: (cap, slots)}). Defaults mirror DEFAULT_RISK so a
    config without a [risk] table still sums sanely.
    """
    total = 0.0
    details = {}
    for tag, cfg in BOTS.items():
        risk, _ = _read_risk(_resolve(cfg))
        cap = risk.get("max_loss_pct_per_trade", 2.0)
        slots = risk.get("max_concurrent", 1)
        total += cap * slots
        details[tag] = (cap, slots)
    return total, details


def _format_value(v):
    """Value token formatting: ints as ints (2, never 2.0), floats minimally
    (0.4, 1.0), strings double-quoted like the surrounding file style."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(float(v))
    return f'"{v}"'


def _generic_rule(current):
    """Rule for a [risk] key this script does not special-case: parse with the
    type its current value has and apply a sane positivity rule."""
    if isinstance(current, bool):
        return "bool", lambda v: True, "must be true or false"
    if isinstance(current, int):
        return "int", lambda v: v >= 1, "must be >= 1"
    if isinstance(current, float):
        return "float", lambda v: v > 0, "must be > 0"
    return "str", lambda v: True, ""


def _validate_change(key, raw, current):
    """Return the parsed new value, or raise ValueError naming key + rule.

    ``key`` is the FULL DOTTED name (risk.max_loss_pct_per_trade,
    strategy.rr_multiple) so the error message names the exact key the user
    typed.
    """
    if key in _KNOWN_RULES:
        kind, ok, rule = _KNOWN_RULES[key]
    else:
        kind, ok, rule = _generic_rule(current)
    try:
        if kind == "int":
            value = int(raw)
        elif kind == "float":
            value = float(raw)
        elif kind == "bool":
            low = raw.strip().lower()
            if low not in ("true", "false"):
                raise ValueError("must be true or false")
            value = low == "true"
        else:  # str — strip a user-supplied pair of quotes
            value = raw.strip().strip('"')
    except ValueError:
        raise ValueError(f"{key}={raw!r} is invalid: {rule} (could not parse as {kind})")
    if not ok(value):
        raise ValueError(f"{key}={raw!r} is invalid: {rule}")
    return value


def _replace_value(line, edits):
    """Replace the value token of a `key = value` line, preserving indentation,
    the spacing around `=`, trailing whitespace AND any trailing inline
    comment (`rr_multiple = 1.0  # 1:1 risk-reward` keeps its comment).
    Returns the line untouched when no edited key matches.

    ``[^#]*`` in the value group stops at a trailing comment; a value token
    itself never contains ``#`` (numbers, bools, and quoted strings with no
    comment marker).
    """
    for key, new_val in edits.items():
        pat = re.compile(
            r"^(\s*)" + re.escape(key) + r"(\s*=\s*)([^#]*?)(\s*)(#[^\n]*)?$"
        )
        m = pat.match(line)
        if m:
            indent, sep, _old, tail_ws, comment = m.groups()
            comment = comment or ""
            return f"{indent}{key}{sep}{_format_value(new_val)}{tail_ws}{comment}"
    return line


def _apply_edits(text, section, edits):
    """Line-based edit scoped to ONE TOML section ([risk] or [strategy]): every
    other table, every comment, blank line and the byte layout are preserved
    verbatim. A single --set command may touch both tables — call once per
    section; the sections are disjoint so there is no conflict."""
    lines = text.split("\n")
    cur = None
    out = []
    for line in lines:
        hm = re.match(r"^\s*\[([^\]]+)\]", line)
        if hm:
            cur = hm.group(1)
            out.append(line)
            continue
        if cur == section:
            out.append(_replace_value(line, edits))
        else:
            out.append(line)
    return "\n".join(out)


def _prompt_yes_no(prompt="apply this change? [y/N] "):
    try:
        answer = input(prompt)
    except EOFError:
        return False
    return answer.strip().lower() in ("y", "yes")


def _read_pid(path):
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def _restart_windows(tag):
    """Windows restart: sentinel + schtasks /Run (see _restart_agent docstring).

    The stop sentinel makes the current supervisor exit cleanly (it also
    deletes the sentinel); schtasks /Run then starts a fresh supervised bot
    which reloads the config. If the scheduled task is not registered the
    config is still written — the change applies on the next manual start.
    """
    stopfile = ROOT / "output" / f"live_{tag}.stop"
    pidfile = ROOT / "output" / f"live_{tag}.pid"
    old_pid = _read_pid(pidfile)

    # 1) Tell the running supervisor to exit. It watches for this sentinel and
    #    stops the bot before exiting — the same mechanism gold_weekend_stop.bat
    #    uses, so the ordering (supervisor dies before any new start) is the
    #    battle-tested one.
    stopfile.write_text("", encoding="utf-8")

    # 2) Wait for the old bot to actually die (up to ~60s) so a second
    #    supervisor does not race a still-running bot.
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        cur = _read_pid(pidfile)
        if cur is None or cur != old_pid or not _pid_running(cur):
            break
        time.sleep(2)

    # 3) Trigger the scheduled task. On failure the config change stands and
    #    the change applies on the next scheduled/on-logon start.
    run = subprocess.run(
        ["schtasks", "/Run", "/TN", f"trading-bot-{tag}"],
        capture_output=True,
        text=True,
    )
    if run.returncode != 0:
        print(run.stderr.strip() or f"schtasks /Run failed (exit {run.returncode})",
              file=sys.stderr)
        print("config was already written — the bot was NOT restarted.", file=sys.stderr)
        print("Start it manually: schtasks /Run /TN trading-bot-<tag>", file=sys.stderr)
        return 2

    # 4) Poll for a NEW pid, matching the launchd path's contract.
    deadline = time.monotonic() + 300
    new_pid = None
    while time.monotonic() < deadline:
        time.sleep(10)
        cur = _read_pid(pidfile)
        if cur is not None and cur != old_pid:
            new_pid = cur
            break
    if new_pid is not None:
        print(f"bot restarted — new pid {new_pid}")
    else:
        print(f"restart in progress — confirm with "
              f"`python scripts/monitor_trade.py --tag {tag}`")
    print("Restart does not touch open positions — broker-side SL/TP and "
          "position-open dedup are intact.")
    return 0


def _pid_running(pid):
    if pid is None:
        return False
    if os.name == "nt":
        try:
            r = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True,
            )
        except OSError:
            return False
        return r.returncode == 0
    return subprocess.run(["ps", "-p", str(pid)], capture_output=True).returncode == 0


def _restart_agent(tag):
    """Restart the <tag> bot's supervisor, then poll output/live_<tag>.pid for
    a NEW pid (up to 300s). Never touches positions.

    macOS: launchctl bootout + bootstrap of com.joram.trading-bot-<tag>.
    Windows: the bot is supervised by a scheduled task. There is no in-process
    way to make Task Scheduler re-run the task from inside the process that
    owns it, so the task is triggered via schtasks /Run — which starts a
    SECOND supervisor. To avoid two supervisors racing the same bot, the
    running one is told to exit first via its stop sentinel (output/live_<tag>
    .stop), exactly as scripts/gold_weekend_stop.bat does; the new task run
    picks up the config change on start. The sentinel is cleared by the new
    supervisor itself (supervise_live.bat deletes it on clean exit/start).
    """
    if os.name == "nt":
        return _restart_windows(tag)
    uid = os.getuid()
    label = f"com.joram.trading-bot-{tag}"
    plist = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
    pidfile = ROOT / "output" / f"live_{tag}.pid"
    old_pid = _read_pid(pidfile)

    # bootout may legitimately report "no such process" (agent stopped); the
    # bootstrap below is the operation that matters.
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{label}"], capture_output=True)
    boot = subprocess.run(
        ["launchctl", "bootstrap", f"gui/{uid}", str(plist)],
        capture_output=True,
        text=True,
    )
    if boot.returncode != 0:
        print(boot.stderr.strip() or f"bootstrap failed (exit {boot.returncode})", file=sys.stderr)
        print("config was already written — the agent was NOT restarted.", file=sys.stderr)
        return 2

    deadline = time.monotonic() + 300
    new_pid = None
    while time.monotonic() < deadline:
        time.sleep(10)
        cur = _read_pid(pidfile)
        if cur is not None and cur != old_pid:
            new_pid = cur
            break
    if new_pid is not None:
        print(f"agent restarted — new pid {new_pid}")
    else:
        print(f"restart in progress — confirm with "
              f"`python scripts/monitor_trade.py --tag {tag}`")
    print("Restart does not touch open positions — broker-side SL/TP and "
          "position-open dedup are intact (verified in quick task 002).")
    return 0


def view(tag):
    """Read-only: print each bot's [risk] table + [strategy] rr_multiple + the
    account-wide total."""
    tags = list(BOTS) if tag == "all" else [tag]
    total, _ = _account_total()
    for t in tags:
        risk, magic = _read_risk(_resolve(BOTS[t]))
        sections = _read_sections(_resolve(BOTS[t]))
        print(f"== {t} ==")
        print(f"config: {BOTS[t]}")
        print(f"magic:  {magic}")
        for key, value in risk.items():
            print(f"{key} = {_format_value(value)}")
        strategy = sections.get("strategy", {})
        if "rr_multiple" in strategy:
            print(f"strategy.rr_multiple = {_format_value(strategy['rr_multiple'])}")
        print()
    print(f"account-wide risk if every stop hits: {total:.1f}% "
          f"(standing policy {STANDING_POLICY_PCT:.1f}%)")
    return 0


def set_risk(tag, items, yes, no_restart):
    cfg_rel = BOTS[tag]
    path = _resolve(cfg_rel)
    if not path.exists():
        print(f"error: config not found: {path}", file=sys.stderr)
        return 2
    sections = _read_sections(path)
    risk = sections.get("risk", {})
    if not risk:
        print(f"error: no [risk] table in {cfg_rel}", file=sys.stderr)
        return 2
    text = path.read_text(encoding="utf-8")

    changes = {}       # dotted key -> parsed new value
    errors = []
    for item in items:
        if "=" not in item:
            errors.append(f"{item!r} is not key=value")
            continue
        key, _, value_str = item.partition("=")
        key = key.strip()
        section, name = _split_key(key)
        if section not in _EDITABLE_SECTIONS:
            errors.append(f"unknown section {section!r} — editable: "
                          f"{', '.join(_EDITABLE_SECTIONS)}")
            continue
        table = sections.get(section, {})
        if name not in table:
            errors.append(f"unknown key {key!r} — valid [{section}] keys: "
                          f"{', '.join(table)}")
            continue
        dotted = f"{section}.{name}"
        try:
            changes[dotted] = _validate_change(dotted, value_str, table[name])
        except ValueError as exc:
            errors.append(str(exc))
    if errors:
        for err in errors:
            print(f"error: {err}", file=sys.stderr)
        print("nothing written", file=sys.stderr)
        return 2
    if not changes:
        print("error: no changes to apply", file=sys.stderr)
        return 2

    # Account-wide total before/after: the OTHER bot's on-disk values stay,
    # the edited bot's change set replaces its cap/slots. RISK-ONLY —
    # strategy.rr_multiple does not move the total.
    total_before, details = _account_total()
    old_cap, old_slots = details[tag]
    new_cap = changes.get("risk.max_loss_pct_per_trade", old_cap)
    new_slots = changes.get("risk.max_concurrent", old_slots)
    total_after = total_before - old_cap * old_slots + new_cap * new_slots

    print(f"account-wide risk if every stop hits: {total_before:.1f}% -> "
          f"{total_after:.1f}% (standing policy {STANDING_POLICY_PCT:.1f}%)")
    for dotted, new_val in changes.items():
        section, name = _split_key(dotted)
        print(f"{dotted}: {_format_value(sections[section][name])} -> "
              f"{_format_value(new_val)}  ({cfg_rel})")

    if "risk.max_concurrent" in changes or "risk.max_loss_pct_per_trade" in changes:
        print(_LEVERAGE_WARNING)
        if new_slots > old_slots:
            print("To keep the total constant, halve the cap in the same command.")

    # Aggressive-tier warnings: loud, measured, and NON-BLOCKING — they print
    # before the confirmation and simply require --yes like the account-wide
    # gate (which they may or may not coincide with).
    aggressive = _aggressive_warnings(changes, total_after)
    for warning in aggressive:
        print(warning)

    new_text = text
    for section in sorted({_split_key(k)[0] for k in changes}):
        section_edits = {
            _split_key(k)[1]: v for k, v in changes.items() if k.startswith(section + ".")
        }
        new_text = _apply_edits(new_text, section, section_edits)
    if new_text == text:
        print("no change — values already as requested; nothing written, no restart")
        return 0

    # Confirmation gates. A changed account-wide total OR an aggressive
    # setting is mandatory --yes.
    total_changed = abs(total_before - total_after) > 1e-9
    requires_yes = total_changed or bool(aggressive)
    if requires_yes:
        if not yes:
            reasons = []
            if total_changed:
                msg = "account-wide risk total changes — re-run with --yes to confirm"
                if total_after > STANDING_POLICY_PCT + 1e-9:
                    msg += (f" (new total {total_after:.1f}% EXCEEDS the "
                            f"{STANDING_POLICY_PCT:.1f}% standing policy)")
                reasons.append(msg)
            if aggressive:
                reasons.append("aggressive setting (see WARNING above) — "
                               "re-run with --yes to confirm")
            for reason in reasons:
                print(reason, file=sys.stderr)
            print("nothing written", file=sys.stderr)
            return 2
    elif not yes:
        if not _prompt_yes_no():
            print("aborted — nothing written")
            return 0

    # Validate the in-memory result BEFORE any disk write: load_config on a
    # temp file in the same directory (the engine's own validator).
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(new_text, encoding="utf-8")
    try:
        load_config(tmp)
    except Exception as exc:
        print(f"error: edited config fails validation: {exc}", file=sys.stderr)
        print("nothing written", file=sys.stderr)
        tmp.unlink(missing_ok=True)
        return 2

    # Atomic write: temp file + os.replace, preserving the file mode.
    mode = path.stat().st_mode
    os.replace(tmp, path)
    os.chmod(path, mode)
    print(f"wrote {cfg_rel}")

    if no_restart:
        print("config updated — agent NOT restarted (--no-restart); the change "
              "applies on the next agent start")
        return 0
    return _restart_agent(tag)


def main(argv=None):
    p = argparse.ArgumentParser(
        description="view or safely edit the risk settings of the live bots "
                    "([risk] keys, or strategy.rr_multiple via a dotted key)")
    p.add_argument("--tag", choices=list(BOTS) + ["all"], default="all",
                   help="bot tag (default: all for view; --set requires one tag)")
    p.add_argument("--set", action="append", metavar="KEY=VALUE",
                   help="change a value (repeatable); bare key = [risk], "
                        "strategy.rr_multiple = [strategy]")
    p.add_argument("--yes", action="store_true",
                   help="confirm a change that moves the account-wide total "
                        "or is aggressive (see warnings)")
    p.add_argument("--no-restart", action="store_true",
                   help="write the config but do not restart the agent")
    a = p.parse_args(argv)

    if a.set:
        if a.tag == "all":
            print("error: --set requires a single --tag (btc or cent), not 'all'",
                  file=sys.stderr)
            return 2
        return set_risk(a.tag, a.set, a.yes, a.no_restart)
    return view(a.tag)


if __name__ == "__main__":
    raise SystemExit(main())
