"""End-to-end CLI tests for the instrument-spec backtest path (plan 05-03).

Runs the real ``main()`` over a synthetic 3-dp EURJPY broker fixture + spec
sidecar and a legacy gold histdata fixture:

- ``[live] enabled`` configs are structurally refused by ``backtest`` (INST-04)
- a config/data symbol mismatch with the spec sidecar fails loudly naming BOTH
  symbols (INST-02, PITFALLS C4 gold-labelled trap)
- trades.csv and the decision log round at the instrument's own digits (3 dp
  for the JPY spec, 2 dp on the legacy no-spec path) â€” PITFALLS A3
- ``trade_stats`` receives the spec's ``value_per_point`` and ``spread_price``
  when a spec is present, and the legacy ``None``/``0.0`` otherwise (INST-01/03)
- ``sl_buffer_points`` without a spec is refused (PITFALLS A1/D2 seam)
"""

import json
import re
from pathlib import Path

import pandas as pd

from trading_bot.backtest.stats import trade_stats
from trading_bot.cli import main

# ---------------------------------------------------------------------------
# Legacy gold M1 fixture (mirrors test_cli.py's real-format histdata file: the
# 12 golden M5 buckets expanded into M1 bars with the bucket-7 OPEN override so
# the Buy Stop fills AT the armed resistance level).
# ---------------------------------------------------------------------------
_GOLD_OPENS = [
    100.00, 100.10, 100.60, 100.90, 100.50, 100.15, 100.80, 101.10, 101.60,
    101.90, 101.80, 101.20,
]
_GOLD_HIGHS = [
    100.00, 100.50, 101.00, 100.90, 100.50, 100.70, 101.05, 101.50, 101.85,
    102.05, 101.80, 101.20,
]
_GOLD_LOWS = [
    100.00, 100.10, 100.60, 100.50, 100.10, 100.15, 100.80, 101.10, 101.60,
    101.90, 101.60, 100.90,
]
_GOLD_CLOSES = [
    100.00, 100.50, 101.00, 100.50, 100.10, 100.70, 101.05, 101.50, 101.85,
    102.05, 101.60, 100.90,
]


def _write_gold_fixture(tmp_path, data_dir):
    """Write the golden OHLC as a real-format histdata M1 CSV (2-dp gold)."""
    opens, highs, lows, closes = (
        list(_GOLD_OPENS), list(_GOLD_HIGHS), list(_GOLD_LOWS), list(_GOLD_CLOSES)
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
    (data_dir / "DAT_ASCII_XAUUSD_M1_2025.csv").write_text(
        "\n".join(rows) + "\n", encoding="utf-8"
    )


def _write_tmp_config(tmp_path, data_dir, out_dir, spec_file="", symbol="XAUUSD",
                      sl_buffer_points=None, live=False):
    """Write a config.toml pointing raw_dir/output_dir at tmp paths.

    The config is written WITHOUT ``spread_assumption`` (retired knob, INST-03)
    and with ``[live] enabled=false, mode="dry-run"`` unless ``live=True``.
    Buffer: exactly one source (config validator) â€” legacy ``sl_buffer`` by
    default, or ``sl_buffer_points`` when the caller passes a points value.
    """
    cfg = tmp_path / "config.toml"
    spec_line = f'spec_file = "{spec_file}"' if spec_file else ""
    if sl_buffer_points:
        buffer_lines = f"sl_buffer_points = {sl_buffer_points}"
    else:
        buffer_lines = "sl_buffer = 0.01"
    cfg.write_text(
        f"""[data]
source = "histdata"
raw_dir = "{data_dir.as_posix()}"
symbol = "{symbol}"
timeframe = "M5"
start = "2024-01-01"
end = "2026-07-31"
{spec_line}

[strategy]
fractal_left = 2
fractal_right = 2
sr_lookback = 60
rr_multiple = 1.0
{buffer_lines}

[trading]
lot = 0.01
contract_size = 100

[backtest]
output_dir = "{out_dir.as_posix()}"

[live]
enabled = {str(live).lower()}
mode = "dry-run"
magic_number = 77001
deviation = 20
poll_interval = 5.0
comment = "gold-breakout-bot"
""",
        encoding="utf-8",
    )
    return cfg


def _live_config(tmp_path):
    """A config with ``[live] enabled = true`` (SAFE-03 opt-in flipped)."""
    cfg = tmp_path / "live-config.toml"
    cfg.write_text(
        f"""[data]
source = "histdata"
raw_dir = "{tmp_path.as_posix()}"
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

[backtest]
output_dir = "{tmp_path.as_posix()}/live-out"

[live]
enabled = true
mode = "dry-run"
magic_number = 77001
deviation = 20
poll_interval = 5.0
comment = "gold-breakout-bot"
""",
        encoding="utf-8",
    )
    return cfg


# ---------------------------------------------------------------------------
# Synthetic 3-dp EURJPY broker fixture (spec sidecar + broker M5 CSV). The M5
# frame is test_backtest.py's golden 19-bar pattern mapped onto a 3-dp grid
# near 162.345 (millipoints), followed by 65 quiet declining bars: >= 80 bars,
# and the golden pattern deterministically reproduces its trades through
# run_backtest at any scale (all price arithmetic is affine-preserved on the
# 0.001 grid, buffer stays 0.01 price = 10 millipoints).
# ---------------------------------------------------------------------------
_EURJPY_OPENS = [
    100.00, 100.10, 100.60, 100.90, 100.50, 100.15, 100.80, 101.10, 101.60,
    101.90, 101.80, 101.20, 100.90, 100.90, 101.30, 102.60, 102.80, 102.50,
    102.20,
]
_EURJPY_HIGHS = [
    100.00, 100.50, 101.00, 100.90, 100.50, 100.70, 101.05, 101.50, 101.85,
    102.05, 101.80, 101.20, 100.90, 101.30, 102.60, 103.00, 102.80, 102.50,
    102.20,
]
_EURJPY_LOWS = [
    100.00, 100.10, 100.60, 100.50, 100.10, 100.15, 100.80, 101.10, 101.60,
    101.90, 101.60, 100.90, 100.70, 101.00, 102.00, 102.60, 102.40, 102.10,
    101.90,
]
_EURJPY_CLOSES = [
    100.00, 100.50, 101.00, 100.50, 100.10, 100.70, 101.05, 101.50, 101.85,
    102.05, 101.60, 100.90, 100.70, 101.30, 102.60, 103.00, 102.80, 102.50,
    102.20,
]

_BASE_MP = 162_345  # 162.345 in millipoints (0.001 price units)
_SPEC_FIELDS = {
    "symbol": "EURJPYc",
    "digits": 3,
    "point": 0.001,
    "trade_tick_size": 0.001,
    "trade_tick_value": 0.91,
    "trade_contract_size": 1000.0,
    "spread_points_median": 6.0,
}


def _to_mp(p):
    """Map a 2-dp golden ~100 price onto the 3-dp grid near 162.345."""
    return _BASE_MP + int(round((p - 100.0) * 100.0))


def _eurjpy_fixture(tmp_path):
    """Write the EURJPYc spec sidecar + an 84-bar 3-dp EURJPYc M5 broker CSV.

    Returns ``(spec_path, m5_csv_path)``.
    """
    spec_path = tmp_path / "EURJPYc_M5_broker.spec.json"
    spec_path.write_text(json.dumps(_SPEC_FIELDS), encoding="utf-8")

    bars = []
    for o, h, l, c in zip(_EURJPY_OPENS, _EURJPY_HIGHS, _EURJPY_LOWS, _EURJPY_CLOSES):
        bars.append((_to_mp(o), _to_mp(h), _to_mp(l), _to_mp(c)))
    # 65 quiet, strictly-declining bars below the golden resistance: no swing
    # points, no new setup can fire, and the open second trade can only exit
    # SL/TP/OPEN â€” the frame totals 84 M5 bars (>= 80).
    for k in range(65):
        mp = _to_mp(102.40) - 10 - 2 * k
        bars.append((mp, mp, mp, mp))
    assert len(bars) == 84

    idx = pd.date_range("2026-09-01", periods=len(bars), freq="5min", name="time")
    frame = pd.DataFrame(
        {
            "open": [o / 1000.0 for o, h, l, c in bars],
            "high": [h / 1000.0 for o, h, l, c in bars],
            "low": [l / 1000.0 for o, h, l, c in bars],
            "close": [c / 1000.0 for o, h, l, c in bars],
        },
        index=idx,
    )
    m5_path = tmp_path / "EURJPYc_M5_broker.csv"
    frame.to_csv(m5_path)
    return spec_path, m5_path


_PRICE_COLS = ("entry", "sl", "tp", "exit_price", "pnl_points")


# ---------------------------------------------------------------------------
# task 1: refusal + symbol-identity guard + spec loading
# ---------------------------------------------------------------------------


def test_live_enabled_backtest_refused(tmp_path, capsys):
    """INST-04: backtest refuses any config with [live] enabled=true."""
    cfg = _live_config(tmp_path)

    rc = main(["backtest", "--config", str(cfg)])

    assert rc == 1
    assert "live" in capsys.readouterr().err


def test_symbol_mismatch_refused(tmp_path, capsys):
    """INST-02/C4: gold-labelled [data] symbol + EURJPYc spec -> refuse both."""
    spec_path, _ = _eurjpy_fixture(tmp_path)
    data_dir = tmp_path / "data"
    out_dir = tmp_path / "out"
    data_dir.mkdir()
    cfg = _write_tmp_config(tmp_path, data_dir, out_dir, spec_file=spec_path.as_posix())

    rc = main(["backtest", "--config", str(cfg)])

    assert rc == 1
    err = capsys.readouterr().err
    assert "XAUUSD" in err
    assert "EURJPY" in err


def test_symbol_match_passes(tmp_path):
    """Matching symbols (EURJPY data + EURJPYc spec) reach the engine (rc 0).

    Uses ``sl_buffer_points = 10`` so the A1/D2 conversion (points x spec.point
    = 10 x 0.001 = 0.01) is exercised end to end: a raw-price misinterpretation
    would place the stop ~10.0 below support instead of 0.01, blowing up the
    per-trade risk well past 1.0.
    """
    spec_path, m5_csv = _eurjpy_fixture(tmp_path)
    data_dir = tmp_path / "data"
    out_dir = tmp_path / "out"
    data_dir.mkdir()
    cfg = _write_tmp_config(
        tmp_path, data_dir, out_dir,
        spec_file=spec_path.as_posix(), symbol="EURJPY", sl_buffer_points=10,
    )

    rc = main(["backtest", "--config", str(cfg), "--m5-csv", str(m5_csv)])

    assert rc == 0
    trades = pd.read_csv(out_dir / "trades.csv")
    assert len(trades) >= 1
    # Converted stop: risk = fill - (support - 0.01) ~ 0.11-0.26. An
    # unconverted points=10 stop would risk ~10.0 per trade.
    assert bool(((trades["entry"] - trades["sl"]).abs() < 1.0).all())


def test_sl_buffer_points_without_spec_errors(tmp_path, capsys):
    """A1 seam: points-form buffer with no spec to convert it is refused."""
    spec_path, _ = _eurjpy_fixture(tmp_path)
    data_dir = tmp_path / "data"
    out_dir = tmp_path / "out"
    data_dir.mkdir()
    cfg = _write_tmp_config(
        tmp_path, data_dir, out_dir, spec_file="", symbol="EURJPY",
        sl_buffer_points=10,
    )

    rc = main(["backtest", "--config", str(cfg)])

    assert rc == 1
    assert "sl_buffer_points" in capsys.readouterr().err


def test_legacy_no_spec_backtest_passes(tmp_path):
    """No-spec gold config runs the legacy path unchanged (rc 0, >=1 trade)."""
    data_dir = tmp_path / "data"
    out_dir = tmp_path / "out"
    data_dir.mkdir()
    _write_gold_fixture(tmp_path, data_dir)
    cfg = _write_tmp_config(tmp_path, data_dir, out_dir)

    rc = main(["backtest", "--config", str(cfg), "--data-dir", str(data_dir)])

    assert rc == 0
    trades = pd.read_csv(out_dir / "trades.csv")
    assert len(trades) >= 1


# ---------------------------------------------------------------------------
# task 2: digit-aware output boundary + spec money/spread wiring
# ---------------------------------------------------------------------------


def test_spec_run_rounds_artifacts_at_3dp(tmp_path):
    """A3: trades.csv price columns + decision-log price fields keep 3 dp."""
    spec_path, m5_csv = _eurjpy_fixture(tmp_path)
    data_dir = tmp_path / "data"
    out_dir = tmp_path / "out"
    data_dir.mkdir()
    cfg = _write_tmp_config(
        tmp_path, data_dir, out_dir,
        spec_file=spec_path.as_posix(), symbol="EURJPY", sl_buffer_points=10,
    )

    rc = main(["backtest", "--config", str(cfg), "--m5-csv", str(m5_csv)])

    assert rc == 0
    trades = pd.read_csv(out_dir / "trades.csv")
    assert len(trades) >= 1
    # No 2-dp quantization: every price cell has at most 3 decimals...
    for col in _PRICE_COLS:
        assert bool((trades[col] - trades[col].round(3)).abs().fillna(0).lt(1e-9).all())
    # ...and at least one trade genuinely carries a third decimal (a 2-dp
    # round of the recorded entry differs from the recorded entry).
    assert bool((trades["entry"] != trades["entry"].round(2)).any())

    log_text = (out_dir / "backtest.log").read_text()
    fields = re_log_price_fields(log_text)
    assert len(fields) > 0, "no entry=/sl=/tp= fields in the decision log"
    # Every logged price is a 3-dp value: a trailing zero may serialize with 2
    # characters (162.550 -> "162.55") but a value rounded beyond 3 dp, or to a
    # float with more decimals, must never appear.
    for value in fields:
        assert len(value.split(".")[1]) <= 3, (
            f"decision-log price {value} serialized with > 3 decimals"
        )
    # ...and at least one logged price retains a genuine third digit — a 2-dp
    # emit boundary would leave no 3-character fraction anywhere in the log.
    assert any(len(v.split(".")[1]) == 3 for v in fields), (
        "no decision-log price retains a third decimal"
    )


def test_legacy_run_stays_2dp_in_artifacts(tmp_path):
    """Legacy no-spec artifacts stay 2 dp (pinned by existing test_cli.py too)."""
    data_dir = tmp_path / "data"
    out_dir = tmp_path / "out"
    data_dir.mkdir()
    _write_gold_fixture(tmp_path, data_dir)
    cfg = _write_tmp_config(tmp_path, data_dir, out_dir)

    rc = main(["backtest", "--config", str(cfg), "--data-dir", str(data_dir)])

    assert rc == 0
    trades = pd.read_csv(out_dir / "trades.csv")
    assert len(trades) >= 1
    for col in _PRICE_COLS:
        assert bool((trades[col] - trades[col].round(2)).abs().fillna(0).lt(1e-9).all())


def test_stats_receives_spec_value_per_point_and_spread(tmp_path, monkeypatch):
    """Spec run wires value_per_point (910.0) and spread_price (0.006)."""
    spec_path, m5_csv = _eurjpy_fixture(tmp_path)
    data_dir = tmp_path / "data"
    out_dir = tmp_path / "out"
    data_dir.mkdir()
    cfg = _write_tmp_config(
        tmp_path, data_dir, out_dir,
        spec_file=spec_path.as_posix(), symbol="EURJPY", sl_buffer_points=10,
    )
    calls = []
    real_stats = trade_stats

    def recorder(*args, **kwargs):
        calls.append(kwargs)
        return real_stats(*args, **kwargs)

    monkeypatch.setattr("trading_bot.cli.trade_stats", recorder)

    rc = main(["backtest", "--config", str(cfg), "--m5-csv", str(m5_csv)])

    assert rc == 0
    assert calls, "trade_stats was never called"
    # tick_value 0.91 / tick_size 0.001 = 910.0; spread 6.0 points x 0.001
    assert calls[-1]["value_per_point"] == 910.0
    assert calls[-1]["spread_price"] == 0.006


def test_stats_legacy_run_gets_none_and_zero(tmp_path, monkeypatch):
    """No-spec run keeps the legacy stats call shape (None, 0.0)."""
    data_dir = tmp_path / "data"
    out_dir = tmp_path / "out"
    data_dir.mkdir()
    _write_gold_fixture(tmp_path, data_dir)
    cfg = _write_tmp_config(tmp_path, data_dir, out_dir)
    calls = []
    real_stats = trade_stats

    def recorder(*args, **kwargs):
        calls.append(kwargs)
        return real_stats(*args, **kwargs)

    monkeypatch.setattr("trading_bot.cli.trade_stats", recorder)

    rc = main(["backtest", "--config", str(cfg), "--data-dir", str(data_dir)])

    assert rc == 0
    assert calls
    assert calls[-1]["value_per_point"] is None
    assert calls[-1]["spread_price"] == 0.0


def re_log_price_fields(log_text):
    """Return every entry=/sl=/tp= value string from a decision log."""
    return re.findall(r"\b(?:entry|sl|tp)=(\d+\.\d+)", log_text)
