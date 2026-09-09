"""Tests for the dedicated JPY backtest config templates (plan 05-04, INST-04).

Covers:
  - config/config-eurjpy-backtest.toml loads and is instrument-correct per
    cross (EURJPY symbol, EURJPYc spec sidecar, buffer in POINTS)
  - config/config-gbpjpy-backtest.toml loads and is instrument-correct per
    cross (GBPJPY symbol, GBPJPYc spec sidecar, buffer in POINTS)
  - both templates are structurally BACKTEST-ONLY: [live] enabled=false,
    mode="dry-run", no retired spread_assumption knob
  - the LIVE gold/BTC account configs (config-cent.toml, config-btc.toml)
    still load unchanged — a regression tripwire that this plan never drifted
    them (PITFALLS D3/D5: dedicated backtest configs, never live-config edits)
"""

from trading_bot.config import load_config

_EURJPY_BACKTEST = "config/config-eurjpy-backtest.toml"
_GBPJPY_BACKTEST = "config/config-gbpjpy-backtest.toml"


def test_eurjpy_template_loads():
    """EUR/JPY backtest template: correct cross, spec sidecar, buffer in points."""
    cfg = load_config(_EURJPY_BACKTEST)
    assert cfg.data.symbol == "EURJPY"
    assert cfg.data.spec_file.endswith("EURJPYc_M5_broker.spec.json")
    assert cfg.strategy.sl_buffer_points == 10
    assert cfg.strategy.sl_buffer == 0.0  # unset — points path only
    assert cfg.live.enabled is False
    assert cfg.live.mode == "dry-run"
    assert cfg.live.magic_number == 77022
    assert cfg.live.symbol == "EURJPYc"
    assert cfg.trading.contract_size == 100


def test_gbpjpy_template_loads():
    """GBP/JPY backtest template: correct cross, spec sidecar, buffer in points."""
    cfg = load_config(_GBPJPY_BACKTEST)
    assert cfg.data.symbol == "GBPJPY"
    assert cfg.data.spec_file.endswith("GBPJPYc_M5_broker.spec.json")
    assert cfg.strategy.sl_buffer_points == 10
    assert cfg.strategy.sl_buffer == 0.0  # unset — points path only
    assert cfg.live.enabled is False
    assert cfg.live.mode == "dry-run"
    assert cfg.live.magic_number == 77023
    assert cfg.live.symbol == "GBPJPYc"
    assert cfg.trading.contract_size == 100


def test_templates_are_backtest_only():
    """Both templates: live disabled AND no retired spread_assumption knob."""
    for path in (_EURJPY_BACKTEST, _GBPJPY_BACKTEST):
        cfg = load_config(path)
        assert cfg.live.enabled is False
        assert cfg.live.mode == "dry-run"
        assert not hasattr(cfg.trading, "spread_assumption")


def test_templates_do_not_edit_live_configs():
    """Live gold/BTC account configs still load — this plan never drifted them.

    Tripwire for PITFALLS D3/D5: dedicated backtest configs exist so the live
    configs stay untouched. If either live config stops loading, a schema
    change or config edit in a backtest-only milestone broke the running bots.
    """
    gold = load_config("config/config-cent.toml")
    assert gold.live.enabled is True
    assert gold.trading.contract_size == 100

    btc = load_config("config/config-btc.toml")
    assert btc.live.enabled is True
