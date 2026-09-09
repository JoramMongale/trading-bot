"""Tests for scripts/tune_risk.py — the confirmed, validated [risk] editor.

Pure-function tests for the editor, the per-key validation matrix, the
account-wide budget gate, the read-only guarantee, atomicity, and a
copy-based end-to-end set. The LIVE config files (config/config-*.toml) are
never written: tune_risk.BOTS is monkeypatched to point at tmp_path copies.

The script re-exports BOTS as a module-level name precisely so tests can
swap it — see the module docstring in tune_risk.py.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import tune_risk  # noqa: E402

from trading_bot.config import load_config  # noqa: E402

REAL_BTC = ROOT / "config" / "config-btc.toml"
REAL_CENT = ROOT / "config" / "config-cent.toml"


@pytest.fixture
def bots(tmp_path, monkeypatch):
    """Copy both real configs into tmp_path; point tune_risk.BOTS at the copies."""
    copies = {
        "btc": tmp_path / "config-btc.toml",
        "cent": tmp_path / "config-cent.toml",
    }
    for tag, dest in copies.items():
        src = REAL_BTC if tag == "btc" else REAL_CENT
        dest.write_bytes(src.read_bytes())
    monkeypatch.setattr(tune_risk, "BOTS", {t: str(p) for t, p in copies.items()})
    return copies


@pytest.fixture(autouse=True)
def _no_real_restarts(monkeypatch):
    """Tests must NEVER touch the live launchd agents.

    ``_restart_agent`` keys off the TAG, not the config path, so a test that
    reaches the write path without --no-restart would bootout+bootstrap the
    REAL com.joram.trading-bot-<tag> agent even though BOTS points at tmp
    copies. Every test here edits tmp copies only; stub the restart out so a
    passing test can never restart a live bot.
    """
    monkeypatch.setattr(tune_risk, "_restart_agent", lambda tag: 0)


# ---------------------------------------------------------------------------
# 1. Comment preservation
# ---------------------------------------------------------------------------

def test_edit_preserves_every_comment_and_only_touches_one_token(bots):
    original = (REAL_BTC).read_text()
    rc = tune_risk.main(["--tag", "btc", "--set", "max_loss_pct_per_trade=0.4",
                         "--yes", "--no-restart"])
    assert rc == 0
    edited = bots["btc"].read_text()

    # Same line count, and exactly ONE line differs: the value token of the
    # requested key. Everything else is byte-identical.
    orig_lines = original.splitlines()
    new_lines = edited.splitlines()
    assert len(new_lines) == len(orig_lines)
    diffs = [(i, a, b) for i, (a, b) in enumerate(zip(orig_lines, new_lines)) if a != b]
    assert len(diffs) == 1
    (idx, old, new) = diffs[0]
    assert old == "max_loss_pct_per_trade = 10.0"
    assert new == "max_loss_pct_per_trade = 0.4"

    # Every comment line (including the long policy blocks) verbatim.
    comment_lines = [l for l in orig_lines if l.strip().startswith("#")]
    for c in comment_lines:
        assert c in new_lines
    assert any("# The per-trade cap and max_concurrent must always move TOGETHER." in l
               for l in new_lines)
    assert any("#       2     181  +0.1164  +1.73   15.3%   <- R per trade unchanged, 2x sample" in l
               for l in new_lines)


# ---------------------------------------------------------------------------
# 2. Section scoping
# ---------------------------------------------------------------------------

_HAND_CONFIG = """\
[data]
source = "histdata"
raw_dir = "data/raw"
symbol = "XAUUSD"
timeframe = "M5"
start = "2024-01-01"
end = "2026-07-31"

[strategy]
fractal_left = 2
fractal_right = 2
sr_lookback = 60
rr_multiple = 1.0
sl_buffer = 0.01

[trading]
lot = 0.01
contract_size = 100
spread_assumption = 0.0

[backtest]
output_dir = "output"

[other]
max_concurrent = 99

[risk]
max_loss_pct_per_trade = 2.0
max_concurrent = 1
sizing = "fixed"
max_daily_loss_pct = 0.0
min_rr = 0.5
lot_min = 0.01
lot_step = 0.01
"""


def test_edit_never_touches_other_tables(tmp_path, monkeypatch):
    cfg = tmp_path / "config.toml"
    cfg.write_text(_HAND_CONFIG)
    monkeypatch.setattr(tune_risk, "BOTS", {"btc": str(cfg)})

    rc = tune_risk.main(["--tag", "btc", "--set", "max_concurrent=3",
                         "--yes", "--no-restart"])
    assert rc == 0
    text = cfg.read_text()
    # The [other] table's max_concurrent must be untouched; only [risk]'s.
    assert "max_concurrent = 99" in text
    assert "[risk]\nmax_loss_pct_per_trade = 2.0\nmax_concurrent = 3" in text


# ---------------------------------------------------------------------------
# 3. Value formatting
# ---------------------------------------------------------------------------

def test_int_formatting_writes_int_not_float(bots):
    # cent currently has max_concurrent = 1; writing 2 must produce `2`, not `2.0`
    rc = tune_risk.main(["--tag", "cent", "--set", "max_concurrent=2",
                         "--yes", "--no-restart"])
    assert rc == 0
    text = bots["cent"].read_text()
    assert "max_concurrent = 2\n" in text
    assert "max_concurrent = 2.0" not in text


def test_float_formatting_writes_minimal_float(bots):
    rc = tune_risk.main(["--tag", "btc", "--set", "max_loss_pct_per_trade=0.4",
                         "--yes", "--no-restart"])
    assert rc == 0
    text = bots["btc"].read_text()
    assert "max_loss_pct_per_trade = 0.4" in text
    assert "max_loss_pct_per_trade = 0.40" not in text


# ---------------------------------------------------------------------------
# 4. Validation matrix — refused, key named, file byte-identical
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad",
    [
        "max_loss_pct_per_trade=0",
        "max_loss_pct_per_trade=-1",
        "max_loss_pct_per_trade=101",
        "max_concurrent=0",
        "max_concurrent=1.5",
        "max_concurrent=abc",
        "sizing=jumbo",
        "min_rr=-1",
        "lot_min=0",
        "max_daily_loss_pct=101",
        "max_leverage=-0.5",
        "unknown_key=5",
    ],
)
def test_validation_matrix_refused_with_key_named(bots, bad, capsys):
    key = bad.split("=")[0]
    before = bots["btc"].read_bytes()

    rc = tune_risk.main(["--tag", "btc", "--set", bad, "--yes"])
    assert rc == 2
    assert bots["btc"].read_bytes() == before  # nothing written

    # The CLI error must NAME the offending key.
    err = capsys.readouterr().err
    assert key in err
    assert "nothing written" in err


# ---------------------------------------------------------------------------
# 5. Account-wide total gate
# ---------------------------------------------------------------------------

def test_account_total_change_requires_yes(bots, capsys):
    before = bots["btc"].read_bytes()
    # btc cap 0.5 -> 0.6 pushes the total 2.0 -> 2.2: must be refused without --yes
    rc = tune_risk.main(["--tag", "btc", "--set", "max_loss_pct_per_trade=0.6"])
    assert rc == 2
    assert bots["btc"].read_bytes() == before
    err = capsys.readouterr().err
    assert "account-wide risk total changes" in err
    assert "EXCEEDS" in err  # 2.2% > 2.0% policy is called out explicitly


# Hand-written low-total configs for the --yes gate tests. The LIVE copies
# (via the `bots` fixture) today sit at a deliberately aggressive 21.0% total
# (cent 20.0 x 1 + btc 0.5 x 2), so ANY account-wide change there trips the
# account-wide > 5% aggressive warning and forces --yes — the very path these
# tests must exercise with a total-neutral change. These stay at the 2.0%
# standing policy so the premise (no --yes for a compensating change) holds
# independent of live-config drift.
_HAND_CENT_CONFIG = """\
[data]
source = "histdata"
raw_dir = "data/raw"
symbol = "XAUUSD"
timeframe = "M5"
start = "2024-01-01"
end = "2026-07-31"

[strategy]
fractal_left = 2
fractal_right = 2
sr_lookback = 60
rr_multiple = 1.0
sl_buffer = 0.01

[trading]
lot = 0.01
contract_size = 100
spread_assumption = 0.0

[backtest]
output_dir = "output"

[risk]
max_loss_pct_per_trade = 1.0
max_concurrent = 1
sizing = "fixed"
max_daily_loss_pct = 0.0
min_rr = 0.5
lot_min = 0.01
lot_step = 0.01
"""

_HAND_BTC_CONFIG = _HAND_CENT_CONFIG.replace(
    "max_loss_pct_per_trade = 1.0\nmax_concurrent = 1",
    "max_loss_pct_per_trade = 0.5\nmax_concurrent = 2",
)


@pytest.fixture
def low_total_bots(tmp_path, monkeypatch):
    """cent 1.0 x 1 + btc 0.5 x 2 = the 2.0% standing policy — drift-proof."""
    cent = tmp_path / "cent-low.toml"
    btc = tmp_path / "btc-low.toml"
    cent.write_text(_HAND_CENT_CONFIG)
    btc.write_text(_HAND_BTC_CONFIG)
    monkeypatch.setattr(tune_risk, "BOTS", {"cent": str(cent), "btc": str(btc)})
    return {"cent": cent, "btc": btc}


def test_compensating_change_allowed_without_yes_but_warns(low_total_bots, capsys, monkeypatch):
    # btc cap 0.5 -> 0.25 AND slots 2 -> 4 keeps the total at 2.0 (1.0 from each
    # bot): allowed without --yes, but the leverage warning still fires.
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    rc = tune_risk.main(["--tag", "btc", "--set", "max_loss_pct_per_trade=0.25",
                         "--set", "max_concurrent=4"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "must move TOGETHER" in out
    assert "halve the cap in the same command" in out
    text = low_total_bots["btc"].read_text()
    assert "max_loss_pct_per_trade = 0.25" in text
    assert "max_concurrent = 4" in text


def test_refused_confirmation_writes_nothing(low_total_bots, monkeypatch):
    # A y/N decline on a total-neutral change aborts with nothing written.
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    before = low_total_bots["btc"].read_bytes()
    rc = tune_risk.main(["--tag", "btc", "--set", "max_loss_pct_per_trade=0.25",
                         "--set", "max_concurrent=4"])
    assert rc == 0
    assert low_total_bots["btc"].read_bytes() == before


# ---------------------------------------------------------------------------
# 6. Read-only guarantee
# ---------------------------------------------------------------------------

def test_view_mode_is_read_only(bots):
    before = {t: p.read_bytes() for t, p in bots.items()}
    assert tune_risk.main([]) == 0        # both bots
    assert tune_risk.main(["--tag", "btc"]) == 0
    assert tune_risk.main(["--tag", "cent"]) == 0
    for t, blob in before.items():
        assert bots[t].read_bytes() == blob


# ---------------------------------------------------------------------------
# 7. Atomicity
# ---------------------------------------------------------------------------

def test_validation_failure_leaves_file_byte_identical(bots):
    before = bots["btc"].read_bytes()
    rc = tune_risk.main(["--tag", "btc", "--set", "max_concurrent=0", "--yes"])
    assert rc == 2
    assert bots["btc"].read_bytes() == before


# ---------------------------------------------------------------------------
# 8. End-to-end in-process set on copies
# ---------------------------------------------------------------------------

def test_e2e_set_on_copies_passes_real_validator(bots):
    rc = tune_risk.main(["--tag", "btc", "--set", "max_loss_pct_per_trade=0.4",
                         "--yes", "--no-restart"])
    assert rc == 0

    edited = bots["btc"].read_text()
    assert "max_loss_pct_per_trade = 0.4" in edited
    assert "# The per-trade cap and max_concurrent must always move TOGETHER." in edited
    assert "max_concurrent = 2" in edited

    # The edited copy passes the SAME validator the engine uses.
    cfg = load_config(bots["btc"])
    assert cfg.risk.max_loss_pct_per_trade == 0.4
    assert cfg.risk.max_concurrent == 2

    # The other bot's copy is untouched.
    cent_text = bots["cent"].read_text()
    assert cent_text == REAL_CENT.read_text()


# ---------------------------------------------------------------------------
# 9. Dotted keys — [strategy] rr_multiple via --set strategy.rr_multiple=...
# ---------------------------------------------------------------------------

def test_dotted_strategy_rr_multiple_edits_only_that_value(bots):
    """--set strategy.rr_multiple=3.0 --yes edits ONLY the [strategy] value:
    comments/other tables preserved byte-for-byte and the result passes the
    engine's own load_config gate (cfg.strategy.rr_multiple == 3.0)."""
    original = bots["cent"].read_text()
    rc = tune_risk.main(["--tag", "cent", "--set", "strategy.rr_multiple=3.0",
                         "--yes", "--no-restart"])
    assert rc == 0
    edited = bots["cent"].read_text()

    # Exactly ONE line differs: the rr_multiple value token. The trailing
    # inline comment (`# 1:1 risk-reward`) is preserved verbatim.
    orig_lines = original.splitlines()
    new_lines = edited.splitlines()
    assert len(new_lines) == len(orig_lines)
    diffs = [(i, a, b) for i, (a, b) in enumerate(zip(orig_lines, new_lines)) if a != b]
    assert len(diffs) == 1
    (idx, old, new) = diffs[0]
    assert old == "rr_multiple = 2.0           # 1:1 risk-reward"
    assert new == "rr_multiple = 3.0           # 1:1 risk-reward"

    # [risk] table untouched; comments preserved (incl. the inline one).
    assert "max_loss_pct_per_trade = 20.0" in edited
    assert "# 1:1 risk-reward" in edited
    comment_lines = [l for l in orig_lines if l.strip().startswith("#")]
    for c in comment_lines:
        assert c in new_lines

    # The edited copy passes the SAME validator the engine uses.
    cfg = load_config(bots["cent"])
    assert cfg.strategy.rr_multiple == 3.0
    assert cfg.risk.max_loss_pct_per_trade == 20.0


@pytest.mark.parametrize("bad", ["0", "-1", "abc"])
def test_dotted_strategy_rr_multiple_invalid_values_refused(bots, capsys, bad):
    """Invalid rr_multiple (0, negative, non-numeric) is refused with an error
    naming strategy.rr_multiple and nothing written."""
    before = bots["cent"].read_bytes()
    rc = tune_risk.main(["--tag", "cent", "--set", f"strategy.rr_multiple={bad}",
                         "--yes"])
    assert rc == 2
    assert bots["cent"].read_bytes() == before  # nothing written

    err = capsys.readouterr().err
    assert "strategy.rr_multiple" in err
    assert "nothing written" in err


def test_dotted_unknown_key_refused(bots, capsys):
    """An unknown dotted key names itself and the valid [strategy] keys."""
    before = bots["cent"].read_bytes()
    rc = tune_risk.main(["--tag", "cent", "--set", "strategy.rr_multiplex=2.0",
                         "--yes"])
    assert rc == 2
    assert bots["cent"].read_bytes() == before

    err = capsys.readouterr().err
    assert "strategy.rr_multiplex" in err
    assert "strategy.rr_multiple" in err  # the valid key is named
    assert "nothing written" in err


def test_dotted_unknown_section_refused(bots, capsys):
    before = bots["cent"].read_bytes()
    rc = tune_risk.main(["--tag", "cent", "--set", "backtest.output_dir=out",
                         "--yes"])
    assert rc == 2
    assert bots["cent"].read_bytes() == before
    err = capsys.readouterr().err
    assert "backtest" in err
    assert "nothing written" in err


def test_view_prints_strategy_rr_multiple(bots, capsys):
    """View mode shows the strategy.rr_multiple line next to the [risk] table."""
    rc = tune_risk.main(["--tag", "cent"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "strategy.rr_multiple = 2.0" in out
    assert "max_loss_pct_per_trade = 20.0" in out


def test_single_command_can_edit_both_tables(bots):
    """One --set command may touch [risk] AND [strategy] sequentially — the
    sections are disjoint so both edits land and the result validates."""
    rc = tune_risk.main(["--tag", "cent",
                         "--set", "max_loss_pct_per_trade=1.5",
                         "--set", "strategy.rr_multiple=1.2",
                         "--yes", "--no-restart"])
    assert rc == 0
    cfg = load_config(bots["cent"])
    assert cfg.risk.max_loss_pct_per_trade == 1.5
    assert cfg.strategy.rr_multiple == 1.2
    # rr_multiple 1.2 is BELOW the aggressive tier: no warning required.
    assert "max_loss_pct_per_trade = 1.5" in bots["cent"].read_text()
    assert "rr_multiple = 1.2" in bots["cent"].read_text()


# ---------------------------------------------------------------------------
# 10. Aggressive-tier warnings (quick task 004) — loud, measured, non-blocking
# ---------------------------------------------------------------------------

def test_aggressive_rr_multiple_warns_and_requires_yes(bots, capsys):
    """rr_multiple >= 1.5 prints the measured-evidence WARNING banner, requires
    --yes like the account-wide gate, and --yes proceeds. btc's current
    rr_multiple is 2.0 (user-set 2026-08-27), so raising it to 2.5 is a real
    aggressive change."""
    before = bots["btc"].read_bytes()
    # No --yes: refused.
    rc = tune_risk.main(["--tag", "btc", "--set", "strategy.rr_multiple=2.5"])
    assert rc == 2
    assert bots["btc"].read_bytes() == before
    cap = capsys.readouterr()
    assert "WARNING: rr_multiple >= 1.5" in cap.out
    assert "1.0: 437 trades" in cap.out          # measured table
    assert "recent half gives t ~ 0.7" in cap.out  # split-sample caveat
    assert "aggressive setting" in cap.err
    assert "nothing written" in cap.err

    # With --yes: proceeds (warning printed, then applied).
    rc = tune_risk.main(["--tag", "btc", "--set", "strategy.rr_multiple=2.5",
                         "--yes", "--no-restart"])
    assert rc == 0
    cfg = load_config(bots["btc"])
    assert cfg.strategy.rr_multiple == 2.5


def test_aggressive_loss_pct_warns_and_requires_yes(bots, capsys):
    """max_loss_pct_per_trade >= 10 warns with the streak/net-edge evidence."""
    before = bots["cent"].read_bytes()
    rc = tune_risk.main(["--tag", "cent", "--set", "max_loss_pct_per_trade=10"])
    assert rc == 2
    assert bots["cent"].read_bytes() == before
    cap = capsys.readouterr()
    assert "WARNING: max_loss_pct_per_trade >= 10" in cap.out
    assert "4-loss streak is -35%" in cap.out
    assert "aggressive setting" in cap.err

    rc = tune_risk.main(["--tag", "cent", "--set", "max_loss_pct_per_trade=10",
                         "--yes", "--no-restart"])
    assert rc == 0
    assert load_config(bots["cent"]).risk.max_loss_pct_per_trade == 10.0


def test_aggressive_account_wide_total_warns(bots, capsys):
    """An account-wide total > 5% triggers the total warning banner."""
    # cent cap 1.0 x 1 + btc 0.5 x 2 = 2.0 today. Push cent to 4.0 -> total
    # 4.0 + 1.0 = 5.0 (not > 5); to 4.5 -> 5.5 (> 5, warns).
    rc = tune_risk.main(["--tag", "cent", "--set", "max_loss_pct_per_trade=4.5",
                         "--yes", "--no-restart"])
    assert rc == 0
    cap = capsys.readouterr()
    assert "WARNING: account-wide risk total > 5%" in cap.out
    assert load_config(bots["cent"]).risk.max_loss_pct_per_trade == 4.5


def test_no_warning_below_the_aggressive_tier(bots, capsys):
    """rr_multiple 1.4 / cap 1.4 are NOT aggressive: no WARNING banner. The
    standing configs are aggressive (btc 10% x 2 + cent 20% x 1 = 40%), so
    both tags are reset to benign values first — only then can the edit prove
    that sub-tier values produce no warning. (The account-wide total still
    moves, so --yes is required by the existing gate — that gate is separate
    from the aggressive-tier warnings.)"""
    rc = tune_risk.main(["--tag", "btc",
                         "--set", "max_loss_pct_per_trade=0.5",
                         "--set", "strategy.rr_multiple=1.4",
                         "--yes", "--no-restart"])
    assert rc == 0
    capsys.readouterr()  # drain btc's reset output
    rc = tune_risk.main(["--tag", "cent",
                         "--set", "max_loss_pct_per_trade=1.4",
                         "--set", "strategy.rr_multiple=1.4",
                         "--yes", "--no-restart"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "WARNING: rr_multiple >= 1.5" not in out
    assert "WARNING: max_loss_pct_per_trade >= 10" not in out
    assert "WARNING: account-wide risk total > 5%" not in out
    cfg = load_config(bots["cent"])
    assert cfg.strategy.rr_multiple == 1.4
    assert cfg.risk.max_loss_pct_per_trade == 1.4
