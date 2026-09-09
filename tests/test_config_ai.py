"""Tests for the [ai] config table — validation, defaults, and the shipped config."""

import pytest

from trading_bot.config import AIConfig, load_config

_COMMITTED_AI = "config/config-ai.toml"

_AI_DEFAULTS = {
    "enabled": "false",
    "provider": '"mock"',
    "model": '"deepseek-chat"',
    "api_base": '"https://api.deepseek.com"',
    "api_key_env": '"DEEPSEEK_API_KEY"',
    "temperature": "0.2",
    "max_tokens": "500",
    "timeout": "30.0",
    "min_confidence": "70",
    "require_agreement": "true",
    "regime_check_daily": "true",
    "block_when_choppy": "true",
    "record_calls": "true",
    "prompt_dir": '"prompts"',
}


def _write_config(tmp_path, include_ai=True, **ai_overrides):
    live = {
        "enabled": "false", "mode": '"dry-run"', "magic_number": "77100",
        "deviation": "20", "poll_interval": "5.0", "comment": '"x"',
    }
    body = """\
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

[live]
"""
    body += "\n".join(f"{k} = {v}" for k, v in live.items()) + "\n"
    if include_ai:
        ai = {**_AI_DEFAULTS, **ai_overrides}
        body += "\n[ai]\n" + "\n".join(f"{k} = {v}" for k, v in ai.items()) + "\n"
    p = tmp_path / "config.toml"
    p.write_text(body, encoding="utf-8")
    return p


def test_missing_ai_table_defaults_to_inert(tmp_path):
    p = _write_config(tmp_path, include_ai=False)
    cfg = load_config(p)
    assert isinstance(cfg.ai, AIConfig)
    assert cfg.ai.enabled is False
    assert cfg.ai.provider == "mock"
    assert cfg.ai.min_confidence == 70


def test_committed_ai_config_loads():
    cfg = load_config(_COMMITTED_AI)
    # The committed AI-backtest config runs the real provider (deepseek); mock
    # is the OFFLINE DEFAULT for new configs, not this file's value.
    assert cfg.ai.provider == "deepseek"
    assert cfg.ai.model == "deepseek-chat"
    assert cfg.ai.min_confidence == 70
    assert cfg.ai.require_agreement is True
    assert cfg.ai.regime_check_daily is True
    assert cfg.ai.block_when_choppy is True
    assert cfg.ai.record_calls is True
    assert cfg.ai.prompt_dir == "prompts"


@pytest.mark.parametrize(
    ("override", "bad_key"),
    [
        ({"provider": '"anthropic"'}, "ai.provider"),
        ({"provider": '"claude"'}, "ai.provider"),
        ({"temperature": "-0.1"}, "ai.temperature"),
        ({"temperature": "1.5"}, "ai.temperature"),
        ({"max_tokens": "0"}, "ai.max_tokens"),
        ({"timeout": "-5"}, "ai.timeout"),
        ({"timeout": "0"}, "ai.timeout"),
        ({"min_confidence": "101"}, "ai.min_confidence"),
        ({"min_confidence": "-1"}, "ai.min_confidence"),
        ({"api_key_env": '""'}, "ai.api_key_env"),
        ({"prompt_dir": '""'}, "ai.prompt_dir"),
    ],
)
def test_invalid_ai_values_raise_naming_key(tmp_path, override, bad_key):
    p = _write_config(tmp_path, **override)
    with pytest.raises(ValueError, match=bad_key):
        load_config(p)


def test_valid_ai_provider_values_accepted(tmp_path):
    p = _write_config(tmp_path, provider='"deepseek"')
    assert load_config(p).ai.provider == "deepseek"


def test_config_ai_toml_keeps_safe_live_defaults():
    cfg = load_config(_COMMITTED_AI)
    assert cfg.live.enabled is False
    assert cfg.live.mode == "dry-run"
    assert cfg.risk.max_loss_pct_per_trade == 1.0
