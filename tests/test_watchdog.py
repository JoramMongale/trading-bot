"""Tests for scripts/watchdog.py — alert logic only, no Telegram, no Windows."""

import importlib.util
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("watchdog_under_test", ROOT / "scripts" / "watchdog.py")
wd = importlib.util.module_from_spec(spec)
sys.modules["watchdog_under_test"] = wd
spec.loader.exec_module(wd)


@pytest.fixture
def out(tmp_path, monkeypatch):
    monkeypatch.setattr(wd, "OUTPUT", tmp_path)
    monkeypatch.setattr(wd, "STATE_PATH", tmp_path / "watchdog_state.json")
    monkeypatch.setattr(wd, "WATCHDOG_LOG", tmp_path / "watchdog.log")
    monkeypatch.setattr(wd, "CLOSES_LOG", tmp_path / "closes.log")
    monkeypatch.setattr(wd, "SUMMARY_HOUR_UTC", 99)  # no daily summary in tests
    monkeypatch.setattr(wd.notify, "send", lambda text, *a, **k: True)
    return tmp_path


def _append(path: Path, *lines: str):
    with path.open("a", encoding="utf-8") as fh:
        for ln in lines:
            fh.write(ln + "\n")


def _run():
    return wd.run_once([wd.BOTS["cent"], wd.BOTS["btc"]], dry=False)


def test_first_run_does_not_replay_history(out):
    _append(out / "live_cent.log",
            "2026-11-04 10:00:00,000 level=INFO event=order_placed side=long symbol=XAUUSDc")
    _append(out / "supervise_cent.log", "x preflight FAILED -- not starting")
    sent = _run()
    assert len(sent) == 1 and sent[0].startswith("👀 Watchdog started")
    assert _run() == []


def test_new_trade_opened_alerts(out):
    _run()
    _append(out / "live_cent.log",
            "2026-11-04 10:05:00,000 level=INFO event=order_placed bar=x ticket=1 "
            "placed=True fill=4001.2 slippage=0.2 symbol=XAUUSDc volume=0.02 "
            "entry=4001.0 sl=3980.0 tp=4022.0 magic=77020 side=long")
    sent = _run()
    assert len(sent) == 1
    assert "opened LONG XAUUSDc" in sent[0] and "lots=0.02" in sent[0]


def test_preflight_failure_alerts_once_per_hour_then_recovers(out):
    _run()
    _append(out / "supervise_cent.log",
            "preflight config\\config-cent.toml  symbol=XAUUSDc  mode=live",
            "  [FAIL] terminal unreachable: trade_allowed=False in terminal settings",
            "2026-11-04T17:13:55Z preflight FAILED -- not starting; retrying in 80s")
    sent = _run()
    assert len(sent) == 1 and "trade_allowed=False" in sent[0]
    _append(out / "supervise_cent.log", "2026-11-04T17:15:16Z preflight FAILED -- retrying")
    assert _run() == []  # still failing, already alerted this hour
    _append(out / "supervise_cent.log", "2026-11-04T17:20:00Z preflight ok -- starting bot")
    sent = _run()
    assert len(sent) == 1 and "startup check passed" in sent[0]


def test_giving_up_alerts(out):
    _run()
    _append(out / "supervise_btc.log",
            "2026-11-04T17:20:00Z GIVING UP: 5 failures within 900s.")
    sent = _run()
    assert any("GAVE UP" in s for s in sent)


def test_sentiment_change_alerts_only_on_change(out):
    _run()
    line = ("2026-11-04 19:15:59,000 level=INFO event=sentiment_direction source=fng "
            "bullishness=26.0 as_of=2026-11-03 direction=short fallback=None")
    _append(out / "live_btc.log", line)
    sent = _run()
    assert len(sent) == 1 and "sentiment now short" in sent[0]
    _append(out / "live_btc.log", line)
    assert _run() == []
    _append(out / "live_btc.log", line.replace("direction=short", "direction=long"))
    assert "sentiment now long" in _run()[0]


def test_macro_veto_change_alerts(out):
    _run()
    _append(out / "live_cent.log",
            "t level=INFO event=macro_veto veto_longs=True dxy_bullishness=29.14 "
            "yield_rising=True as_of=2026-11-03")
    sent = _run()
    assert len(sent) == 1 and "longs PAUSED" in sent[0]


def test_daily_loss_limit_alerts(out):
    _run()
    _append(out / "live_cent.log",
            "2026-11-04 12:00:00,000 level=INFO event=order_skipped reason=daily_loss_limit "
            "bar=x down_today=60.0")
    sent = _run()
    assert len(sent) == 1 and "daily loss limit" in sent[0]


def test_closed_trades_alert_and_backfill_is_ignored(out):
    _run()
    _append(out / "closes.log",
            "2026-11-04 12:00:00 level=INFO event=trade_closed ticket=1 symbol=XAUUSDc "
            "how=tp entry=1 exit=2 volume=0.01 profit=+24.30 r=+1.00",
            "2026-11-01 12:00:00 level=INFO event=trade_closed ticket=0 symbol=XAUUSDc "
            "how=sl entry=1 exit=0 volume=0.01 profit=-20.00 r=-1.00  [backfill]")
    sent = _run()
    assert len(sent) == 1 and sent[0].startswith("✅ closed XAUUSDc by tp: profit +24.30")


def test_alerts_are_written_to_the_watchdog_log(out):
    _run()
    assert "Watchdog started" in (out / "watchdog.log").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("when", "is_open"),
    [
        ("2026-11-06 20:59", True),    # Friday before the close
        ("2026-11-06 21:30", False),   # Friday after the close
        ("2026-11-07 12:00", False),   # Saturday
        ("2026-11-08 21:00", False),   # Sunday before the open
        ("2026-11-08 22:30", True),    # Sunday after the open
        ("2026-11-04 03:00", True),    # Wednesday
    ],
)
def test_gold_market_hours(when, is_open):
    assert wd.market_open("gold", datetime.fromisoformat(when)) is is_open
    assert wd.market_open("crypto", datetime.fromisoformat(when)) is True


def test_kv_parses_structured_lines():
    d = wd.kv("2026 level=INFO event=order_placed side=short entry=4000.5")
    assert d["event"] == "order_placed" and d["side"] == "short" and d["entry"] == "4000.5"
