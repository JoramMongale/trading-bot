"""Tests for scripts/scorecard.py — live-vs-backtest verdicts from closes.log."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("scorecard_under_test", ROOT / "scripts" / "scorecard.py")
sc = importlib.util.module_from_spec(spec)
sys.modules["scorecard_under_test"] = sc
spec.loader.exec_module(sc)


def _line(day, ticket, symbol, profit, r, extra=""):
    return (f"{day} 12:00:00 level=INFO event=trade_closed ticket={ticket} symbol={symbol} "
            f"how=tp entry=1 exit=2 volume=0.01 profit={profit:+.2f} r={r}{extra}")


def _write(tmp_path, lines):
    p = tmp_path / "closes.log"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_reads_only_since_date_and_dedupes_tickets(tmp_path):
    p = _write(tmp_path, [
        _line("2026-10-01", 1, "XAUUSDc", 10, "+1.00"),      # old setup: ignored
        _line("2026-11-05", 2, "XAUUSDc", 10, "+1.00"),
        _line("2026-11-05", 2, "XAUUSDc", 10, "+1.00", "  [backfill]"),  # repeat
        _line("2026-11-06", 3, "BTCUSDc", -5, "?"),           # unknown R kept for profit
    ])
    trades = sc.read_closes(p, since="2026-11-04")
    assert [t["symbol"] for t in trades] == ["XAUUSDc", "BTCUSDc"]
    assert trades[1]["r"] is None and trades[1]["profit"] == -5


def test_stats_drawdown_and_streak():
    rs = [1, -1, -1, -1, 1, -1]
    s = sc.stats([{"r": r, "profit": r} for r in rs])
    assert s.n == 6 and s.wins == 2
    assert s.max_dd_r == 3 and s.worst_streak == 3
    assert abs(s.total_r - (-2)) < 1e-9 and s.last30_avg_r is None


def test_too_early_below_30_trades():
    s = sc.stats([{"r": 1.0, "profit": 1.0}] * 5)
    assert sc.verdict(s, sc.REFERENCES["XAUUSD"]).startswith("too early")


def test_warns_early_when_streak_beats_backtest_worst():
    ref = sc.REFERENCES["XAUUSD"]
    s = sc.stats([{"r": -1.0, "profit": -1.0}] * (ref.worst_streak + 1))
    v = sc.verdict(s, ref)
    assert v.startswith("⚠️") and "losses in a row" in v and "Do not raise risk" in v


def test_on_track_after_30_positive_trades():
    trades = [{"r": 1.0 if i % 3 else -1.0, "profit": 0.0} for i in range(30)]
    v = sc.verdict(sc.stats(trades), sc.REFERENCES["XAUUSD"])
    assert v.startswith("✅")


def test_flat_after_30_is_not_on_track():
    trades = [{"r": 1.0 if i % 2 else -1.0, "profit": 0.0} for i in range(30)]
    v = sc.verdict(sc.stats(trades), sc.REFERENCES["XAUUSD"])
    assert v.startswith("➖")


def test_scorecard_text_lists_both_markets(tmp_path):
    p = _write(tmp_path, [_line("2026-11-05", 2, "XAUUSDc", 24.3, "+1.00")])
    text = sc.scorecard(sc.read_closes(p, since="2026-11-04"), since="2026-11-04")
    assert "gold: 1 trades" in text and "backtest: win 58%" in text
    assert "bitcoin: no closed trades yet" in text


def test_base_symbol():
    assert sc.base_symbol("XAUUSDc") == "XAUUSD"
    assert sc.base_symbol("BTCUSDm") == "BTCUSD"
    assert sc.base_symbol("XAUUSD") == "XAUUSD"
