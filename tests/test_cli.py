"""Tests for src/trading_bot/cli.py — histdata-only CSV selection, data-gap
detection, and a clean default backtest run.

Covers the gap-closure contract (plan 01-05):
  - the CLI loads ONLY histdata ``DAT_ASCII_{SYMBOL}_M1_*.csv`` files, never
    the synthetic sample or any stray CSV co-residing in the data dir
  - >3-day gaps between consecutive M1 bars are surfaced as
    ``data_gap_detected`` warnings in the decision log (not a hard error)
  - the default one-command run produces only convention-clean records:
    sl < entry < tp and exact 1:1 R:R (SAFE-01), with at least one trade
    (an empty trades.csv would pass every cleanliness assertion vacuously)
"""

import pandas as pd
import pytest
from pathlib import Path

from trading_bot.cli import find_data_gaps, list_histdata_csves, main

# ---------------------------------------------------------------------------
# Golden 5-minute OHLC (bars 0-9 = the golden sample trade; 10-11 = quiet
# filler). Reproduces test_backtest.py's golden frame exactly when resampled
# from M1, so expected values below are hand-computed (same conventions).
# ---------------------------------------------------------------------------
_FIX_OPENS = [
    100.00, 100.10, 100.60, 100.90, 100.50, 100.15, 100.80, 101.10, 101.60,
    101.90, 101.80, 101.20,
]
_FIX_HIGHS = [
    100.00, 100.50, 101.00, 100.90, 100.50, 100.70, 101.05, 101.50, 101.85,
    102.05, 101.80, 101.20,
]
_FIX_LOWS = [
    100.00, 100.10, 100.60, 100.50, 100.10, 100.15, 100.80, 101.10, 101.60,
    101.90, 101.60, 100.90,
]
_FIX_CLOSES = [
    100.00, 100.50, 101.00, 100.50, 100.10, 100.70, 101.05, 101.50, 101.85,
    102.05, 101.60, 100.90,
]

_SAMPLE_TEXT = (
    Path("data/sample/sample_XAUUSD_M1_20210201.csv").read_text()
)


def _write_fixture_csv(tmp_path, dat_ascii_name="DAT_ASCII_XAUUSD_M1_2025.csv"):
    """Write the golden OHLC as a real-format histdata M1 CSV.

    Each M5 bucket is expanded into 5 M1 bars with OHLC interpolated linearly
    from bucket open to bucket close (exactly the trick gen_sample_data.py
    uses), plus the bucket's high/low so resampling reproduces every golden
    bar. Bucket 7's OPEN is overridden to 101.00 (= the armed resistance) so
    the Buy Stop fills AT the level: the record then satisfies exact 1:1
    R:R (tp - entry == entry - sl), unlike the golden gap-open fill.
    """
    opens, highs, lows, closes = (
        list(_FIX_OPENS), list(_FIX_HIGHS), list(_FIX_LOWS), list(_FIX_CLOSES)
    )
    opens[7] = 101.00  # non-gap fill at the armed level
    rows = []
    for bucket in range(len(opens)):
        bo, bh, bl, bc = opens[bucket], highs[bucket], lows[bucket], closes[bucket]
        for k in range(5):
            price = round(bo + (bc - bo) * (k / 4), 2)
            high = round(max(price, bh), 2)
            low = round(min(price, bl), 2)
            minute = bucket * 5 + k
            stamp = f"20210201 {minute // 60:02d}{minute % 60:02d}00"
            rows.append(f"{stamp};{price:.2f};{high:.2f};{low:.2f};{price:.2f};1")
    (tmp_path / dat_ascii_name).write_text("\n".join(rows) + "\n", encoding="utf-8")


def _write_tmp_config(tmp_path, data_dir, out_dir):
    """Write a config.toml pointing raw_dir/output_dir at tmp paths."""
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        f"""[data]
source = "histdata"
raw_dir = "{data_dir.as_posix()}"
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
output_dir = "{out_dir.as_posix()}"

[live]
enabled = false
mode = "dry-run"
magic_number = 77001
deviation = 20
poll_interval = 5.0
comment = "gold-breakout-bot"
""",
        encoding="utf-8",
    )
    return cfg


def test_list_histdata_csves_excludes_sample(tmp_path):
    (tmp_path / "DAT_ASCII_XAUUSD_M1_202501.csv").write_text("x\n")
    (tmp_path / "sample_XAUUSD_M1_20210201.csv").write_text("x\n")
    (tmp_path / "notes.csv").write_text("x\n")

    csvs = list_histdata_csves(tmp_path, "XAUUSD")

    assert csvs == [tmp_path / "DAT_ASCII_XAUUSD_M1_202501.csv"]


def test_find_data_gaps_detects_missing_file(tmp_path):
    # A 4-day hole between contiguous M1 runs -> one gap, ~96 hours.
    idx = list(pd.date_range("2025-01-01 00:00", "2025-01-01 00:59", freq="1min"))
    idx += list(pd.date_range("2025-01-05 00:00", "2025-01-05 00:05", freq="1min"))
    m1 = pd.DataFrame({"open": [1.0] * len(idx)}, index=pd.Index(idx, name="time"))

    gaps = find_data_gaps(m1)

    assert len(gaps) == 1
    assert gaps[0]["gap_from"] == pd.Timestamp("2025-01-01 00:59")
    assert gaps[0]["gap_to"] == pd.Timestamp("2025-01-05 00:00")
    assert gaps[0]["gap_hours"] == pytest.approx(96.0, abs=2.0)


def test_find_data_gaps_normal_break_and_weekend_not_flagged(tmp_path):
    # A ~1h daily break plus a ~2-day weekend (Fri 23:00 -> Mon 00:00) is
    # legitimate gold M1 structure — well under the 3-day threshold.
    idx = list(pd.date_range("2025-01-03 22:00", "2025-01-03 23:00", freq="1min"))
    idx += list(pd.date_range("2025-01-06 00:00", "2025-01-06 00:30", freq="1min"))
    m1 = pd.DataFrame({"open": [1.0] * len(idx)}, index=pd.Index(idx, name="time"))

    assert find_data_gaps(m1) == []


def test_default_backtest_produces_only_clean_trades(tmp_path):
    data_dir = tmp_path / "data"
    out_dir = tmp_path / "out"
    data_dir.mkdir()
    # Real-format histdata file spanning the golden OHLC...
    _write_fixture_csv(data_dir)
    # ...co-residing with the OLD-style contaminated sample (~$100 gold).
    (data_dir / "sample_XAUUSD_M1_20210201.csv").write_text(_SAMPLE_TEXT)
    cfg = _write_tmp_config(tmp_path, data_dir, out_dir)

    rc = main(["backtest", "--config", str(cfg), "--data-dir", str(data_dir)])
    trades = pd.read_csv(out_dir / "trades.csv")

    # Exit 0, and the run produced at least one trade: an empty trades.csv
    # would pass every per-row cleanliness assertion vacuously (false green).
    assert rc == 0
    assert len(trades) >= 1
    # Every record satisfies sl < entry < tp — the pre-fix contamination
    # signature (tp=104.01 << entry=2624.91) fails this immediately.
    assert bool((trades["sl"] < trades["entry"]).all())
    assert bool((trades["tp"] > trades["entry"]).all())
    # SAFE-01 exact 1:1 R:R on the record (non-gap fill at the armed level):
    # tp - entry == entry - sl. 0.021 tolerance absorbs 2-dp rounding.
    assert bool(
        (
            abs((trades["tp"] - trades["entry"]) - (trades["entry"] - trades["sl"]))
            <= 0.021
        ).all()
    )
    # The sample was co-residing in the data dir, so the run must have picked
    # up ONLY the DAT_ASCII file: no ~$100-level prices anywhere.
    assert bool((trades["sl"] > 90.0).all())
    # The fixture is a contiguous 60-minute block: the contiguous clean run
    # must NOT raise a data-gap warning (gap detection is a warning for
    # missing files, not normal M1 structure).
    log_text = (out_dir / "backtest.log").read_text()
    assert "event=data_gap_detected" not in log_text


# ---------------------------------------------------------------------------
# live subcommand (plan 02-05)
# ---------------------------------------------------------------------------


def test_cli_live_bad_mode_rejected():
    """argparse rejects an invalid --mode choice with exit code 2 (SystemExit)."""
    with pytest.raises(SystemExit) as excinfo:
        main(["live", "--mode", "paper"])
    assert excinfo.value.code == 2


def test_cli_live_dry_run_once_no_config_crash(tmp_path):
    """`live --once` in dry-run mode with an empty SimulatedBroker returns 0
    (poll logs bar_fetch_failed, never crashes) and writes a live_start line
    to output/live.log (SAFE-02)."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    out_dir = tmp_path / "out"
    cfg = _write_tmp_config(tmp_path, data_dir, out_dir)

    rc = main(["live", "--once", "--config", str(cfg)])

    assert rc == 0
    log_text = (out_dir / "live.log").read_text()
    assert "event=live_start" in log_text
    assert "event=bar_fetch_failed" in log_text  # empty broker: no data, no crash


def test_cli_live_missing_config(tmp_path, capsys):
    """A missing config file is a config error: exit 1 with `error:` on stderr."""
    rc = main(["live", "--config", str(tmp_path / "does-not-exist.toml")])
    assert rc == 1
    assert capsys.readouterr().err.startswith("error:")
