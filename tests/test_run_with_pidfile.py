"""Tests for the Windows pidfile launcher.

The launcher is the one piece of the Windows supervisor that is NOT batch, and
therefore the one piece that can be tested on the build machine. Everything it
does is about the pidfile; the CLI itself is covered elsewhere, so ``main`` is
stubbed out.
"""

import os

import pytest

import scripts.run_with_pidfile as launcher


@pytest.fixture
def fake_main(monkeypatch):
    """Replace the CLI entry point, recording the argv it was handed."""
    seen = {}

    def _main(argv):
        seen["argv"] = argv
        seen["pid_on_disk"] = _read(seen["pidfile"])
        return seen.get("rc", 0)

    monkeypatch.setattr(launcher, "main", _main)
    return seen


def _read(path):
    try:
        return path.read_text().strip()
    except OSError:
        return None


def test_writes_own_pid_then_runs_cli(tmp_path, fake_main):
    pidfile = tmp_path / "output" / "live_cent.pid"
    fake_main["pidfile"] = pidfile

    rc = launcher.run([str(pidfile), "live", "--mode", "live"])

    assert rc == 0
    # The pid visible to health_check/dashboard WHILE the bot runs must be this
    # process — that is the whole point of writing it from inside.
    assert fake_main["pid_on_disk"] == str(os.getpid())
    assert fake_main["argv"] == ["live", "--mode", "live"]


def test_creates_the_output_directory(tmp_path, fake_main):
    pidfile = tmp_path / "does" / "not" / "exist" / "live_btc.pid"
    fake_main["pidfile"] = pidfile

    launcher.run([str(pidfile), "live"])

    assert pidfile.parent.is_dir()


def test_removes_its_own_pidfile_on_exit(tmp_path, fake_main):
    pidfile = tmp_path / "live_cent.pid"
    fake_main["pidfile"] = pidfile

    launcher.run([str(pidfile), "live"])

    assert not pidfile.exists()


def test_leaves_a_pidfile_that_a_newer_run_overwrote(tmp_path, fake_main):
    """A fast restart must not have its pidfile deleted by the old process.

    Deleting it would leave the replacement bot invisible to every status tool —
    the exact failure this launcher exists to prevent, arriving by the back door.
    """
    pidfile = tmp_path / "live_cent.pid"
    fake_main["pidfile"] = pidfile

    def _main(argv):
        # A newer supervisor iteration claims the pidfile mid-run.
        pidfile.write_text("999999")
        return 1

    launcher.main = _main
    rc = launcher.run([str(pidfile), "live"])

    assert rc == 1
    assert pidfile.read_text().strip() == "999999"


def test_propagates_the_cli_exit_code(tmp_path, fake_main):
    """The supervisor's crash-loop brake reads this. Swallowing it would make
    every crash look like a clean shutdown and disable the brake."""
    pidfile = tmp_path / "live_cent.pid"
    fake_main["pidfile"] = pidfile
    fake_main["rc"] = 3

    assert launcher.run([str(pidfile), "live"]) == 3


def test_no_arguments_is_a_usage_error(capsys):
    assert launcher.run([]) == 2
    assert "usage:" in capsys.readouterr().err
