"""build_broker wiring for dry-run replay and the MT5 transport (260819-nhq)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from trading_bot.broker import DryRunBroker, MT5Broker, ReplayBroker
from trading_bot.cli import build_broker
from trading_bot.config import load_config


def _cfg(**live):
    cfg = load_config("config/config.toml")
    return replace(cfg, live=replace(cfg.live, **live)) if live else cfg


def _has_histdata() -> bool:
    """Are the real histdata CSVs present?

    They are a manual browser download (HISTDATA_URL in cli.py), hundreds of MB,
    and gitignored — so a fresh clone does not have them. The two tests below
    genuinely need real bars: they exist to catch dry-run being handed a
    rates-less broker, which is only observable against real data. Skipping
    beats failing on a clean checkout, and beats weakening them to fixtures
    that could not catch the regression they were written for.
    """
    cfg = load_config("config/config.toml")
    return any(Path(cfg.data.raw_dir).glob(f"*{cfg.data.symbol}*.csv"))


needs_histdata = pytest.mark.skipif(
    not _has_histdata(),
    reason="no histdata CSVs in data/raw (manual download, gitignored)",
)


@needs_histdata
def test_dry_run_broker_is_seeded_with_real_bars():
    """The regression this closes: dry-run used to get a rates-less broker, so
    every poll logged bar_fetch_failed and the strategy never ran."""
    broker = build_broker(_cfg(mode="dry-run"))
    assert isinstance(broker, DryRunBroker)
    inner = broker._inner
    assert isinstance(inner, ReplayBroker)
    assert inner._rates is not None and len(inner._rates) > 0


@needs_histdata
def test_dry_run_cursor_is_rewound_by_replay_bars():
    broker = build_broker(_cfg(mode="dry-run", replay_bars=50))
    inner = broker._inner
    assert inner._cursor == len(inner._rates) - 50


def test_dry_run_cursor_floors_at_zero_when_replay_exceeds_history():
    broker = build_broker(_cfg(mode="dry-run", replay_bars=10**9))
    assert broker._inner._cursor == 0


def test_dry_run_with_no_data_still_builds(tmp_path):
    """No CSVs on disk must stay a graceful no-data broker, not a hard failure."""
    cfg = load_config("config/config.toml")
    cfg = replace(
        cfg,
        data=replace(cfg.data, raw_dir=str(tmp_path)),
        live=replace(cfg.live, mode="dry-run"),
    )
    broker = build_broker(cfg)
    assert broker._inner._rates is None


def test_dry_run_broker_receives_the_logger():
    """Without a logger the DryRunBroker's SAFE-02 ``order_plan`` line — the
    record of exactly what WOULD have been sent — never reaches live.log."""
    sentinel = object()
    broker = build_broker(_cfg(mode="dry-run"), sentinel)
    assert broker._logger is sentinel


@pytest.mark.parametrize("mode", ["demo", "live"])
def test_demo_and_live_get_mt5_broker_with_bridge_settings(mode):
    broker = build_broker(
        _cfg(mode=mode, bridge="silicon", bridge_host="10.0.0.2", bridge_port=9100)
    )
    assert isinstance(broker, MT5Broker)
    assert broker._bridge == "silicon"
    assert (broker._bridge_host, broker._bridge_port) == ("10.0.0.2", 9100)


@pytest.mark.parametrize(
    "live_kwargs, message",
    [
        ({"bridge": "wine"}, "live.bridge"),
        ({"bridge_port": 0}, "live.bridge_port"),
        ({"bridge_port": 70000}, "live.bridge_port"),
        ({"replay_bars": 0}, "live.replay_bars"),
    ],
)
def test_invalid_live_settings_are_rejected(tmp_path, live_kwargs, message):
    """Bad values name the offending key (project convention: actionable errors)."""
    from trading_bot.config import _validate

    cfg = _cfg(**live_kwargs)
    with pytest.raises(ValueError, match=message):
        _validate(cfg)


def test_legacy_config_without_new_keys_still_loads(tmp_path):
    """Configs predating the bridge keys keep working (schema grows, never breaks)."""
    (tmp_path / "c.toml").write_text(
        '[data]\nsource="histdata"\nraw_dir="data/raw"\nsymbol="XAUUSD"\n'
        'timeframe="M5"\nstart="2024-01-01"\nend="2026-07-31"\n'
        "[strategy]\nfractal_left=2\nfractal_right=2\nsr_lookback=60\n"
        "rr_multiple=1.0\nsl_buffer=0.01\n"
        "[trading]\nlot=0.01\ncontract_size=100\nspread_assumption=0.0\n"
        '[backtest]\noutput_dir="output"\n'
    )
    cfg = load_config(tmp_path / "c.toml")
    assert cfg.live.bridge == "auto"
    assert cfg.live.bridge_port == 8001
    assert cfg.live.replay_bars == 500


# -- live.symbol override (broker vs vendor naming) -------------------------


def test_live_symbol_defaults_to_data_symbol():
    """Configs that never set the override behave exactly as before."""
    from trading_bot.config import live_symbol

    assert live_symbol(_cfg(mode="demo", symbol="")) == "XAUUSD"


def test_live_symbol_override_applies_in_demo_and_live():
    """Brokers rename the instrument per account type — Exness quotes gold as
    XAUUSDm on Standard, so the wire symbol must differ from the CSV name."""
    from trading_bot.config import live_symbol

    for mode in ("demo", "live"):
        assert live_symbol(_cfg(mode=mode, symbol="XAUUSDm")) == "XAUUSDm"


def test_live_symbol_override_is_ignored_in_dry_run():
    """Dry-run replays the histdata CSVs, which are keyed by the VENDOR name —
    applying the broker override there would look for bars that do not exist."""
    from trading_bot.config import live_symbol

    assert live_symbol(_cfg(mode="dry-run", symbol="XAUUSDm")) == "XAUUSD"


def test_mt5_broker_is_built_with_the_broker_symbol():
    broker = build_broker(_cfg(mode="demo", symbol="XAUUSDm"))
    assert broker._symbol == "XAUUSDm"
