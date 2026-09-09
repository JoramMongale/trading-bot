"""Tests for the histdata M1 loader and M5 resampler.

Covers the verified histdata ASCII format (RQ3):
    `20120201 000000;open;high;low;close;volume`
semicolon-separated, no header, timestamps in %Y%m%d %H%M%S.
"""

import pandas as pd
import pytest

from trading_bot.data.loader import load_histdata_csv
from trading_bot.data.resample import resample_to_m5

# 12 synthetic M1 bars spanning three 5-min buckets. Bucket 3 (00:10-00:14)
# has only 2 bars (00:10 and 00:14) to simulate the daily trading break gap.
# Values are hand-computed so aggregate assertions are exact, and bucket
# opens != bucket closes to catch swapped first/last aggregation bugs.
M1_ROWS = [
    "20120201 000000;100.00;100.10;99.90;100.05;10",
    "20120201 000100;100.05;100.30;100.00;100.25;15",
    "20120201 000200;100.25;100.35;100.15;100.20;12",
    "20120201 000300;100.20;100.40;100.10;100.30;20",
    "20120201 000400;100.30;100.50;100.25;100.45;18",
    "20120201 000500;100.45;100.60;100.40;100.55;11",
    "20120201 000600;100.55;100.70;100.50;100.65;14",
    "20120201 000700;100.65;100.80;100.60;100.70;16",
    "20120201 000800;100.70;100.90;100.65;100.85;13",
    "20120201 000900;100.85;101.00;100.80;100.95;19",
    "20120201 001000;100.95;101.20;100.90;101.10;22",
    "20120201 001400;101.10;101.30;101.00;101.25;25",
]

# Expected M5 aggregates per bucket (hand-computed).
# Bucket label (left edge) -> (open, high, low, close, volume)
EXPECTED_M5 = {
    pd.Timestamp("2012-02-01 00:00"): (100.00, 100.50, 99.90, 100.45, 75),
    pd.Timestamp("2012-02-01 00:05"): (100.45, 101.00, 100.40, 100.95, 73),
    pd.Timestamp("2012-02-01 00:10"): (100.95, 101.30, 100.90, 101.25, 47),
}


@pytest.fixture
def histdata_csv(tmp_path):
    """Write the synthetic histdata M1 CSV to a tmp_path file."""
    path = tmp_path / "XAUUSD_M1_201202.csv"
    path.write_text("\n".join(M1_ROWS) + "\n", encoding="utf-8")
    return path


def test_loader_parses_histdata_format(histdata_csv):
    df = load_histdata_csv(str(histdata_csv))

    # The 6 semicolon-separated histdata fields (dt + OHLCV) map to a
    # "time" index plus the 5 OHLCV columns, all with exact names.
    assert df.index.name == "time"
    assert pd.api.types.is_datetime64_any_dtype(df.index)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 12
    # OHLCV columns are float dtypes.
    assert all(pd.api.types.is_float_dtype(df[col]) for col in df.columns)


def test_resample_partial_bucket_produces_all_three_rows(histdata_csv):
    m1 = load_histdata_csv(str(histdata_csv))
    m5 = resample_to_m5(m1)

    # Bucket 3 has only 2 bars (trading break gap) but still resamples —
    # empty 5-min buckets are dropped by .dropna(), partial ones are kept.
    assert len(m5) == 3
    assert list(m5.index) == list(EXPECTED_M5.keys())


def test_resample_aggregates_exact_values(histdata_csv):
    m1 = load_histdata_csv(str(histdata_csv))
    m5 = resample_to_m5(m1)

    for label, (open_, high, low, close, volume) in EXPECTED_M5.items():
        row = m5.loc[label]
        assert row["open"] == open_
        assert row["high"] == high
        assert row["low"] == low
        assert row["close"] == close
        assert row["volume"] == volume
