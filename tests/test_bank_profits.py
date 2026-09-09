"""Tests for scripts/bank_profits.py — the read-only banking helper.

Fake-broker + tmp-file coverage of the five must-have truths:
  1. balance / pinned base / bankable excess visible in USC + R estimate
  2. first run auto-pins the balance; --base repins deliberately
  3. --confirm appends exactly one ledger line and prints the withdrawal
     amount with the manual-transfer instruction
  4. sub-minimum excess warns with the weekly-banking suggestion
  5. broker unreachable -> graceful 'broker unavailable', exit 2, nothing touched

Isolation (mirrors test_tune_risk.py / test_dashboard.py): the LIVE configs
are NEVER read or written — bank_profits.BOTS is monkeypatched to a tmp_path
copy of config/config-cent.toml; BASE_FILE and LEDGER are monkeypatched to
tmp_path files (the real output/ dir is never touched); the broker transport
is a local _FakeBroker patched onto trading_bot.broker.mt5 (the lazy imports
inside _connect pick the patch up per call).
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import bank_profits  # noqa: E402
import trading_bot.broker.mt5  # noqa: E402  (patch target for the transports)

from trading_bot.broker.base import BrokerUnavailableError  # noqa: E402

REAL_CENT = ROOT / "config" / "config-cent.toml"


class _FakeBroker:
    """Stand-in for the MT5 module / silicon-bridge call surface bank_profits
    uses: initialize / last_error / account_info, with a settable balance."""

    def __init__(self, balance: float = 3200.0):
        self.balance = balance

    def initialize(self):
        return True

    def last_error(self):
        return "no error"

    def account_info(self):
        return SimpleNamespace(
            login=161693049,
            server="Exness-MT5Real21",
            currency="USC",
            balance=self.balance,
        )


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolate bank_profits from the real world: tmp BASE_FILE/LEDGER, a tmp
    copy of the cent config, and a fake broker on BOTH transport hops (the
    native->bridge fallback is exercised per-test by overriding one of them)."""
    cfg_copy = tmp_path / "config-cent.toml"
    cfg_copy.write_bytes(REAL_CENT.read_bytes())
    monkeypatch.setattr(bank_profits, "BOTS", {"cent": str(cfg_copy)})
    monkeypatch.setattr(bank_profits, "BASE_FILE", tmp_path / "bank_base.txt")
    monkeypatch.setattr(bank_profits, "LEDGER", tmp_path / "profits_banked.log")

    broker = _FakeBroker()
    monkeypatch.setattr(trading_bot.broker.mt5, "_load_mt5", lambda: broker)
    monkeypatch.setattr(
        trading_bot.broker.mt5, "_load_silicon_bridge",
        lambda *a, **k: broker,
    )
    return SimpleNamespace(
        broker=broker,
        base_file=bank_profits.BASE_FILE,
        ledger=bank_profits.LEDGER,
    )


# ---------------------------------------------------------------------------
# 1. First run pins the current balance; nothing to bank yet
# ---------------------------------------------------------------------------

def test_first_run_pins_current_balance(env, capsys):
    env.broker.balance = 3200.0
    rc = bank_profits.main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "first run: pinned base" in out
    assert "3200.00" in out
    assert env.base_file.read_text().strip() == "3200.00"
    assert "bankable 0.00" in out
    assert "nothing to bank" in out


# ---------------------------------------------------------------------------
# 2. --base pins and prints; subsequent views read the pinned file
# ---------------------------------------------------------------------------

def test_base_flag_pins_and_prints(env, capsys):
    env.broker.balance = 3200.0
    rc = bank_profits.main(["--base", "3000"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "base pinned = 3000.00 USC" in out
    assert env.base_file.read_text().strip() == "3000.00"

    # A later view reads the pinned file: bankable = balance - 3000.
    rc = bank_profits.main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "bankable 200.00" in out


# ---------------------------------------------------------------------------
# 3. Broker unreachable -> graceful exit 2, line starts 'broker unavailable'
# ---------------------------------------------------------------------------

def test_broker_unavailable_exits_2(env, monkeypatch, capsys):
    def boom(*a, **k):
        raise BrokerUnavailableError("nope")

    monkeypatch.setattr(trading_bot.broker.mt5, "_load_mt5", boom)
    monkeypatch.setattr(trading_bot.broker.mt5, "_load_silicon_bridge", boom)

    rc = bank_profits.main([])
    assert rc == 2
    out = capsys.readouterr().out
    assert out.strip().startswith("broker unavailable:")
    # nothing pinned, nothing banked
    assert not env.base_file.exists()
    assert not env.ledger.exists()


# ---------------------------------------------------------------------------
# 4. Native fails -> the silicon bridge fallback is used, with cfg's host/port
# ---------------------------------------------------------------------------

def test_bridge_fallback_used(env, monkeypatch, capsys):
    def boom(*a, **k):
        raise BrokerUnavailableError("no native package on macOS")

    calls = []

    def bridge(host, port):
        calls.append((host, port))
        return env.broker

    monkeypatch.setattr(trading_bot.broker.mt5, "_load_mt5", boom)
    monkeypatch.setattr(trading_bot.broker.mt5, "_load_silicon_bridge", bridge)

    rc = bank_profits.main([])
    assert rc == 0
    # the CONFIG's own host/port are read (copy of config-cent.toml), never
    # a hardcoded address
    assert calls == [("localhost", 8001)]
    out = capsys.readouterr().out
    assert "bank profits" in out
    assert "USC" in out


# ---------------------------------------------------------------------------
# 5. Sub-minimum excess warns with the weekly-banking suggestion
# ---------------------------------------------------------------------------

def test_sub_minimum_excess_warns(env, capsys):
    env.broker.balance = 3500.0  # 500 USC above the pinned base: < $10 minimum
    rc = bank_profits.main(["--base", "3000"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "below the practical withdrawal minimum" in out
    assert "banking weekly" in out


# ---------------------------------------------------------------------------
# 6. --confirm appends ONE ledger line and prints the manual instruction
# ---------------------------------------------------------------------------

def test_confirm_appends_ledger_and_prints_instruction(env, capsys):
    env.broker.balance = 5500.0
    assert bank_profits.main(["--base", "3000"]) == 0
    capsys.readouterr()  # discard the pin output

    assert bank_profits.main(["--confirm"]) == 0
    out = capsys.readouterr().out

    lines = env.ledger.read_text().splitlines()
    assert len(lines) == 1
    line = lines[0]
    assert "event=profits_banked" in line
    assert "base=3000.00" in line
    assert "excess=2500.00" in line
    assert "balance_after=3000.00" in line

    assert "withdraw 2500.00 USC" in out
    assert "$25.00" in out
    assert "manual" in out.lower()
    assert "Exness" in out
    # --confirm never touches the pinned base stake
    assert env.base_file.read_text().strip() == "3000.00"


# ---------------------------------------------------------------------------
# 7. --confirm with nothing bankable writes nothing
# ---------------------------------------------------------------------------

def test_confirm_without_excess_does_nothing(env, capsys):
    env.broker.balance = 3000.0
    assert bank_profits.main(["--base", "3000"]) == 0
    capsys.readouterr()

    assert bank_profits.main(["--confirm"]) == 0
    out = capsys.readouterr().out
    assert "withdraw" not in out
    assert not env.ledger.exists()


# ---------------------------------------------------------------------------
# 8. --usd-rate moves the R estimate (USC / 100 * rate)
# ---------------------------------------------------------------------------

def test_usd_rate_changes_r_estimate(env, capsys):
    env.broker.balance = 5000.0
    assert bank_profits.main(["--base", "3000"]) == 0
    capsys.readouterr()

    # bankable 2000 USC at the default 18.0 -> R360.00
    assert bank_profits.main([]) == 0
    out = capsys.readouterr().out
    assert "~R360.00" in out
    assert "usd_rate 18.0" in out

    # same excess at --usd-rate 20 -> R400.00
    assert bank_profits.main(["--usd-rate", "20"]) == 0
    out = capsys.readouterr().out
    assert "~R400.00" in out
    assert "usd_rate 20.0" in out
