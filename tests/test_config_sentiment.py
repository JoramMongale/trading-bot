"""Tests for the [sentiment] config table — validation, defaults, opt-in safety."""

import pytest

from trading_bot.config import SentimentConfig, load_config

_SENTIMENT_DEFAULTS = {
    "enabled": "false",
    "source": '"dxy"',
    "band": "10.0",
    "window": "200",
    "cache_path": '"data/processed/dxy.json"',
    "refresh_seconds": "3600.0",
}


def _write_config(tmp_path, include_sentiment=True, **sentiment_overrides):
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
enabled = "false"
mode = "dry-run"
magic_number = 77100
deviation = 20
poll_interval = 5.0
comment = "x"
"""
    if include_sentiment:
        s = {**_SENTIMENT_DEFAULTS, **sentiment_overrides}
        body += "\n[sentiment]\n" + "\n".join(f"{k} = {v}" for k, v in s.items()) + "\n"
    p = tmp_path / "config.toml"
    p.write_text(body, encoding="utf-8")
    return p


def test_missing_sentiment_table_defaults_to_disabled(tmp_path):
    p = _write_config(tmp_path, include_sentiment=False)
    cfg = load_config(p)
    assert isinstance(cfg.sentiment, SentimentConfig)
    assert cfg.sentiment.enabled is False
    assert cfg.sentiment.source == "dxy"
    assert cfg.sentiment.band == 10.0
    assert cfg.sentiment.window == 200


def test_sentiment_table_readable_when_enabled(tmp_path):
    p = _write_config(tmp_path, enabled="true", band="5.0", window="50")
    cfg = load_config(p)
    assert cfg.sentiment.enabled is True
    assert cfg.sentiment.band == 5.0
    assert cfg.sentiment.window == 50


@pytest.mark.parametrize(
    ("override", "bad_key"),
    [
        ({"source": '"news"'}, "sentiment.source"),
        ({"cache_max_age_hours": "0"}, "sentiment.cache_max_age_hours"),
        ({"max_stale_days": "0"}, "sentiment.max_stale_days"),
        ({"source": '""'}, "sentiment.source"),
        ({"band": "-1.0"}, "sentiment.band"),
        ({"window": "0"}, "sentiment.window"),
        ({"cache_path": '""'}, "sentiment.cache_path"),
        ({"refresh_seconds": "0"}, "sentiment.refresh_seconds"),
        ({"refresh_seconds": "-5"}, "sentiment.refresh_seconds"),
    ],
)
def test_invalid_sentiment_values_raise_naming_key(tmp_path, override, bad_key):
    p = _write_config(tmp_path, **override)
    with pytest.raises(ValueError, match=bad_key):
        load_config(p)
