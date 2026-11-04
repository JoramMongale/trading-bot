"""Tests for the small Windows helper scripts (logic only, runs anywhere)."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_under_test",
                                                  ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


wait_for_log = _load("wait_for_log")
start_terminals = _load("start_terminals")
clock = ROOT / "scripts" / "clock.py"


def test_wait_for_log_matches_any_alternative_after_offset(tmp_path):
    log = tmp_path / "x.log"
    log.write_text("old event=macro_veto\n")
    start = log.stat().st_size
    with log.open("a") as fh:
        fh.write("event=bar_check\nevent=sentiment_direction direction=short\n")
    got = wait_for_log.new_matches(log, start, "sentiment_|macro_veto")
    assert got == ["event=sentiment_direction direction=short"]


def test_portable_detection(tmp_path):
    portable = tmp_path / "MT5-Gold" / "terminal64.exe"
    (portable.parent / "Config").mkdir(parents=True)
    (portable.parent / "Config" / "accounts.dat").write_text("")
    assert start_terminals.is_portable_install(portable) is True
    std = Path(r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe")
    assert start_terminals.is_portable_install(std) is False


def test_start_terminals_reports_missing_exe(capsys):
    # On the dev machine the Windows terminal paths do not exist.
    rc = start_terminals.main(["cent"])
    assert rc == 1
    assert "not found" in capsys.readouterr().out


def test_clock_prints_utc_and_epoch():
    import subprocess
    utc = subprocess.run([sys.executable, str(clock), "utc"], capture_output=True,
                         text=True).stdout.strip()
    epoch = subprocess.run([sys.executable, str(clock), "epoch"], capture_output=True,
                           text=True).stdout.strip()
    assert len(utc) == 20 and utc.endswith("Z") and "T" in utc
    assert epoch.isdigit()
