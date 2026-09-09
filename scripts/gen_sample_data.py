"""Generate deterministic synthetic histdata M1 data for the sample backtest.

Writes ``data/sample/sample_XAUUSD_M1_20210201.csv``: 60 1-minute bars
(20210201 00:00:00 .. 20210201 00:59:00) in histdata Generic ASCII format::

    YYYYMMDD HHMMSS;open;high;low;close;volume

Note: the sample lives in ``data/sample/`` (NOT ``data/raw/``) so the default
CLI run never loads it — the CLI glob is restricted to histdata
``DAT_ASCII_{SYMBOL}_M1_*.csv`` in the raw dir.

Each 5-minute bucket of the target M5 table below is expanded into 5 M1 bars
with open=high=low=close interpolated linearly from bucket open to bucket close
(volume 1 each). Resampling the M1 file back to M5 reproduces every bucket's
open and close, so the strategy run is fully deterministic and hand-checkable.

Verified expectation (defaults left=right=2, sr_lookback=60, sl_buffer=0.01):
  - swing high 101.00 at M5 idx 2 confirms at idx 4  -> resistance 101.00
  - swing low  100.10 at M5 idx 4 confirms at idx 6  -> support    100.10
  - setup fires at idx 6 (close 101.05 > 101.00, prior close 100.70 <= 101.00)
  - fill at idx 7: max(entry 101.00, open 101.10) = 101.10
  - TP exit at idx 9 (high 102.05 >= tp 101.91) -> exit_price 101.91
  - exactly ONE trade: entry 101.10, sl 100.09, tp 101.91, pnl_points 0.81
  - no other setups fire (the prior-close condition self-disables re-triggers)
"""

from __future__ import annotations

from pathlib import Path

# Target 5-minute table: (open, close) per bucket. Interior highs/lows are
# intentionally NOT reproduced by the linear interpolation — only the bucket
# opens/closes (and therefore the strategy outcome) are exact.
M5_BUCKETS = [
    (100.00, 100.00),  # 00:00
    (100.10, 100.50),  # 00:05
    (100.60, 101.00),  # 00:10
    (100.90, 100.50),  # 00:15
    (100.50, 100.10),  # 00:20
    (100.15, 100.70),  # 00:25
    (100.80, 101.05),  # 00:30
    (101.10, 101.50),  # 00:35
    (101.60, 101.85),  # 00:40
    (101.90, 102.05),  # 00:45
    (102.00, 101.95),  # 00:50
    (101.90, 101.75),  # 00:55
]

OUT = Path(__file__).resolve().parents[1] / "data" / "sample" / "sample_XAUUSD_M1_20210201.csv"


def main() -> None:
    """Write the 60-row synthetic histdata M1 CSV."""
    lines: list[str] = []
    for bucket, (bucket_open, bucket_close) in enumerate(M5_BUCKETS):
        for k in range(5):
            price = bucket_open + (bucket_close - bucket_open) * (k / 4)
            minute = bucket * 5 + k
            stamp = f"20210201 {minute // 60:02d}{minute % 60:02d}00"
            lines.append(f"{stamp};{price:.2f};{price:.2f};{price:.2f};{price:.2f};1")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {len(lines)} M1 bars -> {OUT}")


if __name__ == "__main__":
    main()
