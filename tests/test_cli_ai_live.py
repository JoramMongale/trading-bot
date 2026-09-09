"""CLI tests for live AI verification (plan 03-02).

Covers the two 03-02 additions to the ``live`` path:
- ``live --provider {mock,deepseek}`` overrides the configured [ai] provider
  for the run without touching the config file;
- ``config/config-ai-live.toml`` is the paper-trading AI config: [ai] enabled,
  provider=mock (offline first), [live] mode=demo, fetch_bars=5000, SAFE-03
  ([live] enabled=false) intact.

Provider introspection is done by stubbing the client constructors at the
``cli`` module seam and recording instantiation, so no real network call and
no API key is ever involved.
"""

import pytest

from trading_bot import cli
from trading_bot.ai.mock import MockAIClient
from trading_bot.config import load_config

_OPENS = [100.00, 100.10, 100.60, 100.90, 100.50, 100.15, 100.80,
          101.10, 101.60, 101.90, 101.80, 101.20]
_HIGHS = [100.00, 100.50, 101.00, 100.90, 100.50, 100.70, 101.05,
          101.50, 101.85, 102.05, 101.80, 101.20]
_LOWS = [100.00, 100.10, 100.60, 100.50, 100.10, 100.15, 100.80,
         101.10, 101.60, 101.90, 101.60, 100.90]
_CLOSES = [100.00, 100.50, 101.00, 100.50, 100.10, 100.70, 101.05,
           101.50, 101.85, 102.05, 101.60, 100.90]


def _write_fixture_csv(tmp_path):
    rows = []
    for bucket in range(len(_OPENS)):
        bo, bh, bl, bc = _OPENS[bucket], _HIGHS[bucket], _LOWS[bucket], _CLOSES[bucket]
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
magic_number = 77200
deviation = 20
poll_interval = 5.0
comment = "gold-ai-demo"
replay_bars = {replay_bars}
fetch_bars = 5000

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


def _stub_client_factory(registry, kind):
    """Return a client-constructor stub that records instantiations.

    The stub is a MockAIClient subclass, so the offline heuristic answers the
    regime/proposal calls without any network — plumbing proof only.
    """

    def factory(*args, **kwargs):
        registry.append(kind)
        return MockAIClient()

    return factory


def test_live_provider_override_to_deepseek(tmp_path, monkeypatch, capsys):
    """--provider deepseek must build a DeepSeekClient even when the config
    says provider=mock, and the dry-run completes without placing anything."""
    _write_fixture_csv(tmp_path)
    out = tmp_path / "out"
    cfg = _write_config(
        tmp_path, tmp_path, out,
        ai_table=(
            '[ai]\nenabled = true\nprovider = "mock"\n'
            'model = "deepseek-chat"\nregime_check_daily = true\n'
            "record_calls = true\nprompt_dir = \"prompts\"\n"
        ),
    )
    created = []
    monkeypatch.setattr(
        cli, "DeepSeekClient", _stub_client_factory(created, "deepseek")
    )

    code = cli.main(["live", "--config", str(cfg), "--mode", "dry-run",
                     "--once", "--provider", "deepseek", "--log", "ai_live.log"])
    assert code == 0
    # The override flowed through build_ai_client: a DeepSeekClient was built
    # (the stub), which would never happen with provider=mock from config.
    assert created == ["deepseek"]

    log_text = (out / "ai_live.log").read_text(encoding="utf-8")
    assert "event=ai_regime " in log_text
    assert "event=order_placed" not in log_text  # dry-run places nothing


def test_live_no_provider_uses_config_provider(tmp_path, monkeypatch):
    """Without --provider the configured provider (mock) is used unchanged —
    no DeepSeekClient is ever built."""
    _write_fixture_csv(tmp_path)
    out = tmp_path / "out"
    cfg = _write_config(
        tmp_path, tmp_path, out,
        ai_table=(
            '[ai]\nenabled = true\nprovider = "mock"\n'
            "regime_check_daily = true\nprompt_dir = \"prompts\"\n"
        ),
    )
    created = []
    monkeypatch.setattr(
        cli, "DeepSeekClient", _stub_client_factory(created, "deepseek")
    )
    monkeypatch.setattr(
        cli, "MockAIClient", _stub_client_factory(created, "mock")
    )

    code = cli.main(["live", "--config", str(cfg), "--mode", "dry-run",
                     "--once", "--log", "ai_live2.log"])
    assert code == 0
    assert created == ["mock"]  # config's provider honored, no deepseek


def test_config_ai_live_toml_loads_as_paper_trading_config():
    """config/config-ai-live.toml is the paper-trading AI config: AI enabled
    with the offline mock default, demo mode, a 5000-bar window, and SAFE-03
    ([live] enabled=false) intact."""
    cfg = load_config("config/config-ai-live.toml")
    assert cfg.ai.enabled is True
    assert cfg.ai.provider == "mock"
    assert cfg.ai.model == "deepseek-chat"
    assert cfg.ai.record_calls is True
    assert cfg.live.mode == "demo"
    assert cfg.live.magic_number == 77200
    assert cfg.live.fetch_bars == 5000
    assert cfg.live.enabled is False  # SAFE-03: no real-account execution
