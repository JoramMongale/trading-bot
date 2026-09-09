"""Tests for src/trading_bot/config.py — typed [live] config schema (EXEC-03).

Covers:
  - the committed config/config.toml loads unchanged with safe dry-run defaults
  - per-key validation errors name the bad key (live.mode, live.magic_number,
    live.deviation, live.poll_interval)
  - phase-1-era configs WITHOUT a [live] table still load (backward compat)
"""

import pytest

from trading_bot.config import LiveConfig, load_config

_COMMITTED = "config/config.toml"

_LIVE_DEFAULTS = {
    "enabled": "false",
    "mode": '"dry-run"',
    "magic_number": "77001",
    "deviation": "20",
    "poll_interval": "5.0",
    "comment": '"gold-breakout-bot"',
}


def _write_config(tmp_path, include_live=True, **live_overrides):
    """Write a valid full TOML; [live] values are overridable or droppable."""
    live = {**_LIVE_DEFAULTS, **live_overrides}
    body = f"""\
[data]
source = "histdata"
raw_dir = "data/raw"
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
output_dir = "output"
"""
    if include_live:
        body += "\n[live]\n" + "\n".join(f"{k} = {v}" for k, v in live.items()) + "\n"
    p = tmp_path / "config.toml"
    p.write_text(body, encoding="utf-8")
    return p


def test_committed_config_loads_with_dry_run_defaults():
    cfg = load_config(_COMMITTED)
    assert cfg.live.enabled is False
    assert cfg.live.mode == "dry-run"
    assert cfg.live.magic_number == 77001
    assert cfg.live.deviation == 20
    assert cfg.live.poll_interval == 5.0
    assert cfg.live.comment == "gold-breakout-bot"


@pytest.mark.parametrize(
    ("override", "bad_key"),
    [
        ({"mode": '"paper"'}, "live.mode"),
        ({"mode": '"LIVE"'}, "live.mode"),
        ({"magic_number": "-1"}, "live.magic_number"),
        ({"magic_number": "1.5"}, "live.magic_number"),
        ({"deviation": "-5"}, "live.deviation"),
        ({"deviation": "2.5"}, "live.deviation"),
        ({"poll_interval": "0"}, "live.poll_interval"),
        ({"weekend_stop_hour": "25"}, "live.weekend_stop_hour"),
        ({"weekend_stop_hour": "-1"}, "live.weekend_stop_hour"),
        ({"weekend_stop_hour": "19.5"}, "live.weekend_stop_hour"),
        ({"weekend_resume_hour": "25"}, "live.weekend_resume_hour"),
        ({"reconnect_after": "-1"}, "live.reconnect_after"),
        ({"reconnect_after": "1.5"}, "live.reconnect_after"),
        ({"reconnect_backoff": "-1"}, "live.reconnect_backoff"),
        ({"fetch_bars": "-1"}, "live.fetch_bars"),
        ({"fetch_bars": "1.5"}, "live.fetch_bars"),
    ],
)
def test_invalid_live_values_raise_naming_key(tmp_path, override, bad_key):
    p = _write_config(tmp_path, **override)
    with pytest.raises(ValueError, match=bad_key):
        load_config(p)


@pytest.mark.parametrize("mode", ["dry-run", "demo", "live"])
def test_valid_modes_accepted(tmp_path, mode):
    p = _write_config(tmp_path, mode=f'"{mode}"')
    assert load_config(p).live.mode == mode


def test_missing_live_table_still_validates(tmp_path):
    p = _write_config(tmp_path, include_live=False)
    cfg = load_config(p)
    assert isinstance(cfg.live, LiveConfig)
    assert cfg.live.enabled is False
    assert cfg.live.mode == "dry-run"
    assert cfg.live.magic_number == 77001
    assert cfg.live.deviation == 20
    assert cfg.live.poll_interval == 5.0


def test_phase3_defaults_are_off_and_safe(tmp_path):
    """04-01: weekend guard off, reconnect on but harmless by default."""
    p = _write_config(tmp_path)
    cfg = load_config(p)
    assert cfg.live.weekend_stop_hour == 0
    assert cfg.live.weekend_resume_hour == 21
    assert cfg.live.reconnect_after == 3
    assert cfg.live.reconnect_backoff == 30.0


def test_phase3_keys_are_readable_when_set(tmp_path):
    p = _write_config(
        tmp_path,
        weekend_stop_hour="19",
        weekend_resume_hour="21",
        reconnect_after="5",
        reconnect_backoff="45.0",
    )
    cfg = load_config(p)
    assert cfg.live.weekend_stop_hour == 19
    assert cfg.live.weekend_resume_hour == 21
    assert cfg.live.reconnect_after == 5
    assert cfg.live.reconnect_backoff == 45.0


def test_fetch_bars_defaults_to_zero_for_legacy_configs(tmp_path):
    """03-02: a config without [live] fetch_bars loads the default 0 (legacy
    byte-identical window: strategy minimum)."""
    p = _write_config(tmp_path)
    assert load_config(p).live.fetch_bars == 0


def test_fetch_bars_is_readable_when_set(tmp_path):
    p = _write_config(tmp_path, fetch_bars="5000")
    assert load_config(p).live.fetch_bars == 5000


def test_strategy_variant_defaults_to_breakout(tmp_path):
    """2026-08-28: a config without strategy.variant loads the breakout default —
    legacy configs stay byte-identical."""
    p = _write_config(tmp_path)
    assert load_config(p).strategy.variant == "breakout"


def test_strategy_variant_readable_when_set(tmp_path):
    p = _write_config(tmp_path)
    body = p.read_text(encoding="utf-8")
    p.write_text(body.replace("sl_buffer = 0.01\n",
                              "sl_buffer = 0.01\nvariant = \"candle_reversal\"\n"),
                 encoding="utf-8")
    assert load_config(p).strategy.variant == "candle_reversal"


@pytest.mark.parametrize("bad", ["momentum", "breakout-v2", ""])
def test_invalid_strategy_variant_raises_naming_key(tmp_path, bad):
    p = _write_config(tmp_path)
    body = p.read_text(encoding="utf-8")
    p.write_text(body.replace("sl_buffer = 0.01\n",
                              f"sl_buffer = 0.01\nvariant = \"{bad}\"\n"),
                 encoding="utf-8")
    with pytest.raises(ValueError, match="strategy.variant"):
        load_config(p)


def test_strategy_direction_defaults_to_long(tmp_path):
    """A config without strategy.direction loads the "long" default — legacy
    configs (including every committed one) stay byte-identical."""
    p = _write_config(tmp_path)
    assert load_config(p).strategy.direction == "long"


def test_strategy_direction_readable_when_both(tmp_path):
    p = _write_config(tmp_path)
    body = p.read_text(encoding="utf-8")
    p.write_text(body.replace("sl_buffer = 0.01\n",
                              "sl_buffer = 0.01\ndirection = \"both\"\n"),
                 encoding="utf-8")
    assert load_config(p).strategy.direction == "both"


@pytest.mark.parametrize("bad", ["short", "sideways", ""])
def test_invalid_strategy_direction_raises_naming_key(tmp_path, bad):
    """"short"-only live mode is deliberately unsupported — the locked live
    config is the union ("both"), and anything else must fail loudly."""
    p = _write_config(tmp_path)
    body = p.read_text(encoding="utf-8")
    p.write_text(body.replace("sl_buffer = 0.01\n",
                              f"sl_buffer = 0.01\ndirection = \"{bad}\"\n"),
                 encoding="utf-8")
    with pytest.raises(ValueError, match="strategy.direction"):
        load_config(p)


def test_live_cent_config_still_loads():
    """Regression guard for the Task 4 edit: config-cent.toml must load at
    every step of this build (rr_multiple 2.0 today, direction="both" after
    Task 4 — both are valid values)."""
    cfg = load_config("config/config-cent.toml")
    assert cfg.strategy.direction in ("long", "both")
    assert cfg.live.magic_number == 77020
