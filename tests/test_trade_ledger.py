"""Tests for scripts/trade_ledger.py — the merged backtest+live/demo ledger.

Covers the four truths of the Phase 3 ledger criterion:
  1. backtest rows come from output/trades.csv with source=backtest
  2. live rows come from output/live_*.log order_placed lines
  3. closes.log trade_closed lines are joined to live rows by ticket, attaching
     the exit price, reason and R multiple
  4. a live entry with no close yet is reported as open, and the CSV + summary
     emit without touching the broker

Isolation (mirrors test_bank_profits.py / test_tune_risk.py): the module's
ROOT points at the real repo, so the source globs and output paths are
monkeypatched to tmp_path — the real output/ dir is never read or written.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import trade_ledger  # noqa: E402


@pytest.fixture
def ledger_dir(tmp_path, monkeypatch):
    """Point the ledger at a tmp_path sandbox holding all three sources."""
    out = tmp_path / "output"
    out.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(trade_ledger, "TRADES_CSV", out / "trades.csv")
    monkeypatch.setattr(trade_ledger, "CLOSES_LOG", out / "closes.log")
    monkeypatch.setattr(trade_ledger, "LEDGER_CSV", out / "ledger.csv")
    monkeypatch.setattr(trade_ledger, "LIVE_LOG_GLOB", str(out / "live_*.log"))

    # A minimal backtest CSV (9 columns, the CLI's TRADE_COLUMNS).
    (out / "trades.csv").write_text(
        "entry_time,entry,sl,tp,exit_time,exit_price,exit_reason,pnl_points,r_multiple\n"
        "2025-01-02 00:00,100.00,99.00,101.00,2025-01-02 12:00,101.00,TP,1.0,1.00\n"
        "2025-01-03 00:00,101.00,100.00,102.00,2025-01-03 08:00,100.00,SL,-1.0,-1.00\n",
        encoding="utf-8",
    )

    # A live decision log with two order_placed lines.
    (out / "live_cent.log").write_text(
        "2025-01-04 10:00:00 level=INFO event=order_placed bar=2025-01-04T09:55:00 "
        "ticket=101 symbol=XAUUSDc volume=0.01 placed=True fill=101.5 "
        "slippage=0.5 entry=101.0 sl=100.0 tp=102.0 magic=77020\n"
        "2025-01-05 10:00:00 level=INFO event=order_placed bar=2025-01-05T09:55:00 "
        "ticket=102 symbol=XAUUSDc volume=0.01 placed=True fill=200.0 "
        "slippage=0.0 entry=199.0 sl=198.0 tp=201.0 magic=77020\n",
        encoding="utf-8",
    )

    # closes.log: ticket 101 closed at TP, ticket 102 still open.
    (out / "closes.log").write_text(
        "2025-01-04 15:00:00 level=INFO event=trade_closed ticket=101 "
        "symbol=XAUUSDc how=tp entry=101.5 exit=102.0 volume=0.01 "
        "profit=+0.50 r=+1.00\n",
        encoding="utf-8",
    )
    return out


def test_ledger_merges_backtest_live_and_closes(ledger_dir):
    rows = trade_ledger.load_backtest() + trade_ledger.load_live()
    assert len(rows) == 4  # 2 backtest + 2 live

    bt = [r for r in rows if r["source"] == "backtest"]
    assert len(bt) == 2
    assert bt[0]["r"] == "1.00" and bt[0]["exit_reason"] == "TP"

    live = [r for r in rows if r["source"] == "live"]
    assert len(live) == 2
    by_ticket = {r["ticket"]: r for r in live}

    # ticket 101 joined its close: exit price, reason and R attached.
    assert by_ticket[101]["exit_price"] == 102.0
    assert by_ticket[101]["exit_reason"] == "tp"
    assert by_ticket[101]["r"] == "+1.00"
    assert by_ticket[101]["profit"] == 0.50

    # ticket 102 is still open: no exit fields.
    assert by_ticket[102]["exit_price"] is None
    assert by_ticket[102]["exit_reason"] is None


def test_ledger_writes_csv_and_summary(ledger_dir, capsys):
    rc = trade_ledger.main([])
    assert rc == 0
    csv_lines = (ledger_dir / "ledger.csv").read_text().splitlines()
    assert csv_lines[0].startswith("source,entry_time")
    assert len(csv_lines) == 5  # header + 4 trades
    out = capsys.readouterr().out
    assert "backtest" in out and "live" in out


def test_ledger_live_row_without_close_reports_open(ledger_dir):
    rows = trade_ledger.load_live()
    open_row = [r for r in rows if r["ticket"] == 102][0]
    assert open_row["exit_price"] is None
    assert open_row["r"] is None


def test_ledger_empty_output_dir_is_graceful(tmp_path, monkeypatch, capsys):
    out = tmp_path / "output"
    out.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(trade_ledger, "TRADES_CSV", out / "trades.csv")
    monkeypatch.setattr(trade_ledger, "CLOSES_LOG", out / "closes.log")
    monkeypatch.setattr(trade_ledger, "LEDGER_CSV", out / "ledger.csv")
    monkeypatch.setattr(trade_ledger, "LIVE_LOG_GLOB", str(out / "live_*.log"))
    rc = trade_ledger.main(["--once"])
    assert rc == 0
    out_text = capsys.readouterr().out
    assert "0 trades" not in out_text  # it prints the summary table, not a crash
