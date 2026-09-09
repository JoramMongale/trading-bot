"""CLI end-to-end tests for the AI layer (plan 03-01, AI-04).

Runs the real ``main()`` entry point over the golden fixture CSV:
- ``ai-backtest`` replays history through the AI gate with the offline mock and
  reports raw vs gated; every AI decision is in the decision log (SAFE-02).
- ``live --ai`` (config ``[ai] enabled``) with ``--mode dry-run --once`` builds
  an AIEngine and records the daily regime read without placing anything.
"""

import json

import pandas as pd
import pytest
from pathlib import Path

from trading_bot.cli import main

_OPENS = [100.00, 100.10, 100.60, 100.90, 100.50, 100.15, 100.80,
          101.10, 101.60, 101.90, 101.80, 101.20]
_HIGHS = [100.00, 100.50, 101.00, 100.90, 100.50, 100.70, 101.05,
          101.50, 101.85, 102.05, 101.80, 101.20]
_LOWS = [100.00, 100.10, 100.60, 100.50, 100.10, 100.15, 100.80,
         101.10, 101.60, 101.90, 101.60, 100.90]
_CLOSES = [100.00, 100.50, 101.00, 100.50, 100.10, 100.70, 101.05,
           101.50, 101.85, 102.05, 101.60, 100.90]


def _write_fixture_csv(tmp_path):
    opens, highs, lows, closes = _OPENS, _HIGHS, _LOWS, _CLOSES
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
    (tmp_path / "DAT_ASCII_XAUUSD_M1_202102.csv").write_text(
        "\n".join(rows) + "\n", encoding="utf-8"
    )


def _write_config(tmp_path, data_dir, out_dir, ai_table: str,
                  replay_bars: int = 11):
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
magic_number = 77100
deviation = 20
poll_interval = 5.0
comment = "gold-breakout-ai"
replay_bars = {replay_bars}

[risk]
max_loss_pct_per_trade = 1.0
sizing = "percent"
max_daily_loss_pct = 6.0
lot_min = 0.01
lot_step = 0.01
min_rr = 0.5

{ai_table}
""",
        encoding="utf-8",
    )
    return cfg


def test_ai_backtest_cli_reports_raw_vs_gated(tmp_path, capsys):
    _write_fixture_csv(tmp_path)
    out = tmp_path / "out"
    cfg = _write_config(
        tmp_path, tmp_path, out,
        ai_table=(
            '[ai]\nenabled = true\nprovider = "mock"\n'
            'model = "deepseek-chat"\nmin_confidence = 70\n'
            "regime_check_daily = true\nblock_when_choppy = true\n"
            "record_calls = true\nprompt_dir = \"prompts\"\n"
        ),
    )

    code = main(["ai-backtest", "--config", str(cfg), "--log", "ai.log",
                 "--start", "2021-02-01", "--end", "2021-02-02"])
    assert code == 0

    stdout = capsys.readouterr().out
    assert "Raw deterministic" in stdout and "AI-gated" in stdout

    # The gated run kept the golden trade (mock approves); per-trade CSV written.
    trades = pd.read_csv(out / "ai_trades.csv")
    assert len(trades) == 1

    # SAFE-02: every AI decision is in the decision log.
    log_text = (out / "ai.log").read_text(encoding="utf-8")
    assert "event=ai_regime " in log_text
    assert "event=ai_proposal " in log_text
    assert "event=ai_backtest_stats " in log_text
    assert "event=setup_detected " in log_text

    # record_calls: the JSONL audit holds both the regime and the proposal.
    calls = (out / "ai_calls_ai.log.jsonl").read_text(encoding="utf-8").strip()
    kinds = [json.loads(line)["kind"] for line in calls.splitlines()]
    assert "assess_regime" in kinds and "propose_trade" in kinds


def test_ai_backtest_cli_provider_override_to_deepseek(tmp_path, capsys):
    """--provider deepseek must switch the run without touching the config."""
    _write_fixture_csv(tmp_path)
    out = tmp_path / "out"
    cfg = _write_config(
        tmp_path, tmp_path, out,
        ai_table='[ai]\nprovider = "mock"\n',
    )
    code = main(["ai-backtest", "--config", str(cfg), "--log", "ai2.log",
                 "--provider", "deepseek",
                 "--start", "2021-02-01", "--end", "2021-02-02"])
    # No DEEPSEEK_API_KEY in the environment: the proposal gate fails CLOSED
    # (setup skipped, counted unavailable) and the regime check fails OPEN, but
    # the run itself completes honestly with zero gated trades and exit 0 —
    # never a silent half-run, and never a fake approval. With a key present
    # the provider answers and the regime may BLOCK the day instead — either
    # way the run completes with zero gated trades.
    assert code == 0
    log_text = (out / "ai2.log").read_text(encoding="utf-8")
    trades = pd.read_csv(out / "ai_trades.csv")
    assert len(trades) == 0


def test_live_dry_run_with_ai_enabled_records_regime(tmp_path):
    _write_fixture_csv(tmp_path)
    out = tmp_path / "out"
    cfg = _write_config(
        tmp_path, tmp_path, out,
        ai_table=(
            '[ai]\nenabled = true\nprovider = "mock"\n'
            "regime_check_daily = true\nrecord_calls = true\nprompt_dir = \"prompts\"\n"
        ),
    )
    code = main(["live", "--config", str(cfg), "--mode", "dry-run",
                 "--once", "--log", "live_ai.log"])
    assert code == 0
    log_text = (out / "live_ai.log").read_text(encoding="utf-8")
    # One poll = one closed bar = the AIEngine's once-per-day regime read fires.
    assert "event=live_start" in log_text
    assert "event=ai_regime " in log_text
    # Dry-run places nothing.
    assert "event=order_placed" not in log_text
