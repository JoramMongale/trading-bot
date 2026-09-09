"""Tests for the analytics warehouse loader (plan 03-03, WARE-01/WARE-02).

Builds a tiny fixture tree (trades CSV, decision log, closes log, ai_calls
JSONL, processed bars) and proves the loader is idempotent: loading twice
yields identical row counts, missing files are skipped silently, and the
natural-key MERGE never duplicates rows. No network anywhere.

Requires the ``analytics`` extra (duckdb) — the loader and this test share it.
"""

import json

import duckdb
import pytest

from warehouse.load import load

FIXTURE_TRADES = (
    "entry_time,entry,sl,tp,exit_time,exit_price,exit_reason,pnl_points,r_multiple\n"
    "2025-09-14 00:10:00,116046.52,115862.30,116229.82,2025-09-14 01:00:00,115862.30,SL,-184.22,-1.0\n"
    "2025-09-14 00:20:00,116100.00,115900.00,116300.00,2025-09-14 02:00:00,116300.00,TP,200.00,1.0\n"
)

FIXTURE_DECISIONS = (
    "2026-08-26 18:08:25,264 level=INFO event=live_start mode=live symbol=XAUUSDc magic=77020 lot=0.01\n"
    "2026-08-26 18:10:05,344 level=INFO event=bar_check new_bar=True setup=False bar=2026-08-26T16:05:00\n"
    "2026-08-27 00:20:06,100 level=INFO event=ai_proposal bar=2026-08-26T22:15:00 bias=LONG confidence=90 "
    "invalidation=4583.804 verdict=APPROVED reason=ok\n"
)

FIXTURE_CLOSES = (
    "2026-08-27 12:00:00,001 level=INFO event=trade_closed ticket=12345 symbol=XAUUSDc "
    "how=tp r_multiple=1.0 profit=18.30\n"
)

FIXTURE_AI_CALLS = [
    {
        "ts": "2026-08-26T22:20:06.100676+00:00",
        "kind": "propose_trade",
        "as_of": "2026-08-26 22:15:00",
        "context": {"symbol": "XAUUSD", "entry": 101.0, "sl": 100.09},
        "result": {"bias": "LONG", "confidence": 90, "reasoning": "mock"},
    },
    {
        "ts": "2026-08-26T22:21:00.200123+00:00",
        "kind": "assess_regime",
        "as_of": "2026-08-26 22:15:00",
        "context": {"symbol": "XAUUSD", "n_days": 1},
        "result": {"regime": "RANGING", "tradeable": True},
    },
]


def _write_fixture(root, with_closes: bool = True) -> None:
    out = root / "output"
    processed = root / "data" / "processed"
    out.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)

    (out / "trades.csv").write_text(FIXTURE_TRADES, encoding="utf-8")
    (out / "backtest.log").write_text(FIXTURE_DECISIONS, encoding="utf-8")
    if with_closes:
        (out / "closes.log").write_text(FIXTURE_CLOSES, encoding="utf-8")
    (out / "ai_calls_ai_watch.log.jsonl").write_text(
        "\n".join(json.dumps(row) for row in FIXTURE_AI_CALLS) + "\n",
        encoding="utf-8",
    )
    bars = "time,open,high,low,close\n" + "".join(
        f"2026-08-{d:02d} 00:00:00,100.0,101.0,99.5,100.5\n" for d in range(1, 11)
    )
    (processed / "XAUUSDm_M5_broker.csv").write_text(bars, encoding="utf-8")


def _row_counts(db_path: str) -> dict[str, int]:
    con = duckdb.connect(db_path, read_only=True)
    try:
        tables = ["raw_trades", "raw_ledger", "raw_decisions", "raw_closes",
                  "raw_ai_calls", "raw_bars"]
        out = {}
        for t in tables:
            out[t] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        return out
    finally:
        con.close()


def test_load_is_idempotent(tmp_path):
    _write_fixture(tmp_path)
    db = tmp_path / "trading.duckdb"

    first = load(db_path=db, roots=[tmp_path])
    second = load(db_path=db, roots=[tmp_path])

    assert first["raw_trades"] == 2
    assert first["raw_closes"] == 1
    assert first["raw_decisions"] == 3
    assert first["raw_ai_calls"] == 2
    assert first["raw_bars"] == 10

    # Idempotency: second run loads the same number of rows, and the DB holds
    # exactly those counts (no duplicates from MERGE).
    assert second == first
    assert _row_counts(db) == {**first, "raw_ledger": 0}


def test_raw_bars_has_ten_rows_with_symbol_and_timeframe(tmp_path):
    _write_fixture(tmp_path)
    db = tmp_path / "trading.duckdb"
    load(db_path=db, roots=[tmp_path])

    con = duckdb.connect(str(db), read_only=True)
    try:
        n = con.execute("SELECT COUNT(*) FROM raw_bars").fetchone()[0]
        assert n == 10
        row = con.execute(
            "SELECT symbol, timeframe FROM raw_bars LIMIT 1"
        ).fetchone()
        assert row == ("XAUUSDm", "M5")
    finally:
        con.close()


def test_missing_files_are_skipped_silently(tmp_path):
    """No closes.log in the tree -> raw_closes stays empty, no crash."""
    _write_fixture(tmp_path, with_closes=False)
    db = tmp_path / "trading.duckdb"
    counts = load(db_path=db, roots=[tmp_path])

    assert counts.get("raw_closes", 0) == 0
    assert counts["raw_trades"] == 2


def test_reload_after_data_change_updates_not_duplicates(tmp_path):
    """Re-running after a row edit updates in place, never duplicates."""
    _write_fixture(tmp_path)
    db = tmp_path / "trading.duckdb"
    load(db_path=db, roots=[tmp_path])

    # Change one trade's exit reason, then reload.
    trades_path = tmp_path / "output" / "trades.csv"
    edited = FIXTURE_TRADES.replace("TP,200.00,1.0", "TP,200.00,1.0").replace("SL", "TP")
    trades_path.write_text(edited, encoding="utf-8")
    load(db_path=db, roots=[tmp_path])

    counts = _row_counts(db)
    assert counts["raw_trades"] == 2  # still 2 rows — updated, not appended
