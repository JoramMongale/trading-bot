"""Tests for plan 05-01 config-schema growth — spec_file, sl_buffer_points,
and the retired spread_assumption knob (INST-01 / INST-03).

Covers:
  - every committed config TOML (config.toml, live gold config-cent.toml, live
    BTC config-btc.toml, config-ai-live.toml, config-ai.toml) STILL loads after
    spread_assumption leaves the typed TradingConfig — the legacy-key tolerance
    proves the schema removal never breaks a running bot's config (PITFALLS
    D3/D5 tripwire)
  - [data] spec_file is optional and round-trips
  - the strategy buffer is expressed in exactly ONE unit: legacy sl_buffer
    (raw price) or spec-driven sl_buffer_points (points x spec.point), never
    both and never neither (PITFALLS D2)
"""

import pytest

from trading_bot.config import load_config

_COMMITTED = "config/config.toml"

# Defaults for the _write_config helper. Values are pre-rendered TOML.
_DATA_DEFAULTS = {
    "source": '"histdata"',
    "raw_dir": '"data/raw"',
    "symbol": '"XAUUSD"',
    "timeframe": '"M5"',
    "start": '"2024-01-01"',
    "end": '"2026-07-31"',
}

_STRATEGY_DEFAULTS = {
    "fractal_left": "2",
    "fractal_right": "2",
    "sr_lookback": "60",
    "rr_multiple": "1.0",
    "sl_buffer": "0.01",  # legacy raw-price buffer; committed configs always set it
}

_TRADING_DEFAULTS = {
    "lot": "0.01",
    "contract_size": "100",
    # NOTE: no spread_assumption — this helper writes NEW-STYLE configs.
}

_LIVE_DEFAULTS = {
    "enabled": "false",
    "mode": '"dry-run"',
    "magic_number": "77001",
    "deviation": "20",
    "poll_interval": "5.0",
    "comment": '"gold-breakout-bot"',
}


def _render(defaults, overrides):
    """Merge table dicts; a None value OMITS that key from the TOML table."""
    merged = {**defaults, **overrides}
    lines = [f"{k} = {v}" for k, v in merged.items() if v is not None]
    return "\n".join(lines)


def _write_config(
    tmp_path,
    *,
    data_overrides=None,
    strategy_overrides=None,
    trading_overrides=None,
    include_live=True,
    live_overrides=None,
):
    """Write a valid new-style full TOML config (no spread_assumption).

    ``overrides`` dicts add/replace table keys; a None value drops the key
    (e.g. strategy_overrides={"sl_buffer": None, "sl_buffer_points": "10"}
    writes a points-only config with no sl_buffer key at all).
    """
    data = _render(_DATA_DEFAULTS, data_overrides or {})
    strategy = _render(_STRATEGY_DEFAULTS, strategy_overrides or {})
    trading = _render(_TRADING_DEFAULTS, trading_overrides or {})
    body = f"""\
[data]
{data}

[strategy]
{strategy}

[trading]
{trading}

[backtest]
output_dir = "output"
"""
    if include_live:
        live = _render(_LIVE_DEFAULTS, live_overrides or {})
        body += f"\n[live]\n{live}\n"
    p = tmp_path / "config.toml"
    p.write_text(body, encoding="utf-8")
    return p


# --- committed-config legacy compatibility (spread_assumption in the TOML) ---

def test_committed_gold_config_still_loads_without_dead_knob():
    """config/config.toml carries spread_assumption = 0.0 — tolerance proves it."""
    cfg = load_config(_COMMITTED)
    assert cfg.trading.lot == 0.01
    assert cfg.trading.contract_size == 100
    assert not hasattr(cfg.trading, "spread_assumption")


def test_live_gold_config_still_loads():
    """config-cent.toml: spread_assumption AND [live] enabled = true both load."""
    cfg = load_config("config/config-cent.toml")
    assert cfg.live.enabled is True
    assert not hasattr(cfg.trading, "spread_assumption")
    assert cfg.trading.contract_size == 100


def test_live_btc_config_still_loads():
    cfg = load_config("config/config-btc.toml")
    assert cfg.live.enabled is True
    assert not hasattr(cfg.trading, "spread_assumption")


def test_ai_live_config_still_loads_with_live_disabled():
    """config-ai-live.toml: its [ai] table, not [live], is the enabled half."""
    cfg = load_config("config/config-ai-live.toml")
    assert cfg.live.enabled is False
    assert not hasattr(cfg.trading, "spread_assumption")


def test_ai_config_still_loads():
    cfg = load_config("config/config-ai.toml")
    assert cfg.live.enabled is False
    assert not hasattr(cfg.trading, "spread_assumption")


# --- the retired knob is gone from the typed schema ---

def test_trading_config_has_no_spread_assumption_attribute(tmp_path):
    cfg = load_config(_write_config(tmp_path))
    assert not hasattr(cfg.trading, "spread_assumption")
    assert hasattr(cfg.trading, "lot")
    assert hasattr(cfg.trading, "contract_size")


def test_legacy_config_with_spread_assumption_tolerated_byte_identical(tmp_path):
    """A TOML still carrying spread_assumption loads with UNCHANGED values."""
    p = _write_config(
        tmp_path,
        trading_overrides={"spread_assumption": "0.0"},  # legacy key in the file
    )
    cfg = load_config(p)
    assert cfg.trading.lot == 0.01
    assert cfg.trading.contract_size == 100
    assert not hasattr(cfg.trading, "spread_assumption")
    assert cfg.strategy.sl_buffer == 0.01
    assert cfg.strategy.sl_buffer_points == 0.0


# --- [data] spec_file (optional, STACK seam 2) ---

def test_spec_file_round_trips_when_set(tmp_path):
    p = _write_config(
        tmp_path,
        data_overrides={"spec_file": '"data/processed/EURJPYc_M5_broker.spec.json"'},
    )
    cfg = load_config(p)
    assert cfg.data.spec_file == "data/processed/EURJPYc_M5_broker.spec.json"


def test_spec_file_defaults_to_empty_when_omitted(tmp_path):
    cfg = load_config(_write_config(tmp_path))
    assert cfg.data.spec_file == ""


def test_spec_file_must_be_a_string(tmp_path):
    p = _write_config(tmp_path, data_overrides={"spec_file": "5"})
    with pytest.raises(ValueError, match="data.spec_file"):
        load_config(p)


# --- strategy buffer: EXACTLY ONE source (PITFALLS D2) ---

def test_points_only_config_loads_with_sl_buffer_unset(tmp_path):
    """sl_buffer_points = 10 and NO sl_buffer key: default 0.0 means unset."""
    p = _write_config(
        tmp_path,
        strategy_overrides={"sl_buffer": None, "sl_buffer_points": "10"},
    )
    cfg = load_config(p)
    assert cfg.strategy.sl_buffer_points == 10.0
    assert cfg.strategy.sl_buffer == 0.0


def test_legacy_sl_buffer_only_config_loads_byte_identical(tmp_path):
    """ONLY sl_buffer = 0.01 (no sl_buffer_points key): legacy path unchanged."""
    cfg = load_config(_write_config(tmp_path))
    assert cfg.strategy.sl_buffer == 0.01
    assert cfg.strategy.sl_buffer_points == 0.0


def test_both_buffer_keys_set_is_rejected(tmp_path):
    p = _write_config(
        tmp_path,
        strategy_overrides={"sl_buffer": "0.01", "sl_buffer_points": "10"},
    )
    with pytest.raises(ValueError, match="ONE unit"):
        load_config(p)


def test_both_buffer_keys_zero_is_rejected(tmp_path):
    """sl_buffer explicitly 0 and no sl_buffer_points: nothing would buffer."""
    p = _write_config(
        tmp_path,
        strategy_overrides={"sl_buffer": "0.0", "sl_buffer_points": None},
    )
    with pytest.raises(ValueError, match="both 0"):
        load_config(p)


def test_negative_sl_buffer_points_is_rejected(tmp_path):
    p = _write_config(
        tmp_path,
        strategy_overrides={"sl_buffer": None, "sl_buffer_points": "-1"},
    )
    with pytest.raises(ValueError, match="sl_buffer"):
        load_config(p)
