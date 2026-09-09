"""Tests for scripts/dashboard.py — the loopback-only web dashboard.

Endpoint tests run a real ``dashboard._Server`` on 127.0.0.1 with an ephemeral
port (port 0) in a background thread and hit it with urllib.request — stdlib
end to end, no external test server.

Isolation (mirrors test_tune_risk.py): the LIVE config files are NEVER
written. ``dashboard.BOTS`` AND ``tune_risk.BOTS`` are monkeypatched to point
at tmp_path copies of config/config-btc.toml and config/config-cent.toml;
``tune_risk._restart_agent`` is stubbed to a recorder (so a passing test can
never bootout a real launchd agent); the broker transport is a local
``_FakeBroker``.
"""

import json
import sys
import threading
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import dashboard  # noqa: E402
import tune_risk  # noqa: E402

from trading_bot.broker.base import BrokerUnavailableError  # noqa: E402
from trading_bot.config import load_config  # noqa: E402

REAL_BTC = ROOT / "config" / "config-btc.toml"
REAL_CENT = ROOT / "config" / "config-cent.toml"


class _FakeBroker:
    """Stand-in for the MT5 module / silicon-bridge call surface the dashboard
    uses: initialize/terminal_info/account_info/positions_get/
    symbol_info_tick/shutdown, plus the POSITION_TYPE_* constants."""

    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1

    def __init__(self):
        self.shutdown_calls = 0

    def initialize(self):
        return True

    def last_error(self):
        return "no error"

    def terminal_info(self):
        return SimpleNamespace(connected=True, trade_allowed=True)

    def account_info(self):
        return SimpleNamespace(
            login=161693049,
            server="Exness-MT5Real21",
            balance=3139.30,
            equity=3140.00,
            profit=0.70,
            currency="USC",
        )

    def positions_get(self):
        return [SimpleNamespace(
            ticket=434510667,
            magic=77020,          # the cent magic — filtered out for btc
            symbol="XAUUSDc",
            type=self.POSITION_TYPE_BUY,
            volume=0.01,
            price_open=4605.799,
            sl=4563.311,
            tp=4645.759,
            profit=0.70,
            time=1750000000,
        )]

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=4606.0, ask=4606.2)

    def shutdown(self):
        self.shutdown_calls += 1


@pytest.fixture
def bots(tmp_path, monkeypatch):
    """Copy both real configs into tmp_path; point BOTH dashboard and
    tune_risk at the copies (the live configs are NEVER written)."""
    copies = {
        "btc": tmp_path / "config-btc.toml",
        "cent": tmp_path / "config-cent.toml",
    }
    for tag, dest in copies.items():
        src = REAL_BTC if tag == "btc" else REAL_CENT
        dest.write_bytes(src.read_bytes())
    patched = {t: str(p) for t, p in copies.items()}
    monkeypatch.setattr(dashboard, "BOTS", patched)
    monkeypatch.setattr(tune_risk, "BOTS", patched)
    return copies


@pytest.fixture(autouse=True)
def restarts(monkeypatch):
    """Tests must NEVER touch the real launchd agents: record and return 0."""
    calls = []

    def recorder(tag):
        calls.append(tag)
        return 0

    monkeypatch.setattr(tune_risk, "_restart_agent", recorder)
    return calls


@pytest.fixture
def fake_broker(monkeypatch):
    """Replace the broker transport with the fake. The dashboard attaches per
    config via health_check._init_terminal (per-tag terminal_path), so that is
    what is patched — a bare _load_mt5 is no longer in the dashboard's path."""
    broker = _FakeBroker()
    monkeypatch.setattr(dashboard, "_init_terminal", lambda cfg: broker)
    return broker


@pytest.fixture
def client(bots, fake_broker):
    """Real dashboard._Server on 127.0.0.1 with an ephemeral port (port 0),
    in a background thread; yield the base URL."""
    server = dashboard._Server(("127.0.0.1", 0), dashboard._Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    base = f"http://127.0.0.1:{port}"
    yield base
    server.shutdown()
    thread.join(timeout=5)
    server.server_close()


@pytest.fixture
def closes_log(tmp_path, monkeypatch):
    """A sample output/closes.log (one cent + one btc close) and dashboard.ROOT
    repointed at tmp_path, so the endpoint reads it instead of the gitignored
    real output/ dir that is absent from the zip."""
    out = tmp_path / "output"
    out.mkdir()
    (out / "closes.log").write_text(
        "2026-08-20 14:35:00 event=trade_closed symbol=XAUUSDc ticket=1 how=tp profit=12.50 r=1.00\n"
        "2026-08-20 15:10:00 event=trade_closed symbol=BTCUSDc ticket=2 how=tp profit=-3.20 r=0.75\n"
    )
    monkeypatch.setattr(dashboard, "ROOT", tmp_path)
    return out


def _get(base, path):
    with urllib.request.urlopen(base + path, timeout=10) as resp:
        assert resp.status == 200
        return json.loads(resp.read().decode())


def _post(base, path, body):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert resp.status == 200
        return json.loads(resp.read().decode())


# ---------------------------------------------------------------------------
# 1. Loopback-only binding, no --host option
# ---------------------------------------------------------------------------

def test_server_binds_loopback_only(bots, fake_broker):
    server = dashboard._Server(("127.0.0.1", 0), dashboard._Handler)
    try:
        # the literal bind host from the code — never 0.0.0.0
        assert server.server_address[0] == "127.0.0.1"
        assert "127.0.0.1" in str(server.server_address)
    finally:
        server.server_close()


def test_no_host_argument():
    """The dashboard has no --host option: the only network knob is --port."""
    help_text = dashboard.build_parser().format_help()
    assert "--host" not in help_text
    assert "--port" in help_text


# ---------------------------------------------------------------------------
# 2. GET /api/risk
# ---------------------------------------------------------------------------

def test_risk_endpoint_shows_both_tags(client):
    payload = _get(client, "/api/risk")
    tags = payload["tags"]
    assert set(tags) == {"cent", "btc"}
    assert tags["cent"]["risk"]["max_loss_pct_per_trade"] == "20.0"
    assert tags["cent"]["strategy_rr_multiple"] == "1.0"
    assert tags["btc"]["risk"]["max_loss_pct_per_trade"] == "10.0"
    assert tags["btc"]["strategy_rr_multiple"] == "2.0"
    # account-wide: 20 x 1 (cent) + 10 x 2 (btc) = 40.0 vs the 2.0 policy
    assert payload["account_total"] == 40.0
    assert payload["standing_policy"] == 2.0


# ---------------------------------------------------------------------------
# 3. GET /api/status with the fake broker
# ---------------------------------------------------------------------------

def test_status_endpoint_position_account_closes(client, closes_log):
    payload = _get(client, "/api/status")
    tags = payload["tags"]
    assert set(tags) == {"cent", "btc"}

    cent = tags["cent"]
    assert cent["magic"] == 77020
    assert cent["symbol"] == "XAUUSDc"
    # broker section from the fake
    assert cent["broker"]["connected"] is True
    assert cent["broker"]["trade_allowed"] is True
    # account
    assert cent["account"]["balance"] == 3139.30
    assert cent["account"]["equity"] == 3140.00
    assert cent["account"]["currency"] == "USC"
    # the open position for cent's magic
    pos = cent["position"]
    assert pos is not None
    assert pos["entry"] == 4605.799
    assert pos["sl"] == 4563.311
    assert pos["tp"] == 4645.759
    assert pos["floating"] == 0.70
    assert pos["bid"] == 4606.0
    assert pos["ask"] == 4606.2
    # btc's magic (77021) has no position
    assert tags["btc"]["position"] is None
    # the file-based bot section is present even though the broker is faked
    assert "last_decision_min_ago" in cent["bot"]
    assert isinstance(cent["bot"]["supervisor_alive"], bool)
    # closes parsed from the repo's closes.log, filtered by exact symbol
    cent_closes = cent["closes"]
    assert all(r["symbol"] == "XAUUSDc" for r in cent_closes["rows"])
    btc_closes = tags["btc"]["closes"]
    assert all(r["symbol"] == "BTCUSDc" for r in btc_closes["rows"])
    assert btc_closes["totals"]["n"] >= 1
    assert isinstance(btc_closes["totals"]["profit_sum"], (int, float))
    assert isinstance(btc_closes["totals"]["r_sum"], (int, float))


# ---------------------------------------------------------------------------
# 4. Degraded broker: dead bridge, file-based bot section survives
# ---------------------------------------------------------------------------

def test_degraded_broker_keeps_bot_section(client, monkeypatch):
    def boom(*a, **k):
        raise BrokerUnavailableError("terminal down")

    # override the fixture's fake broker: the per-config terminal attach is dead
    monkeypatch.setattr(dashboard, "_init_terminal", boom)

    payload = _get(client, "/api/status")
    cent = payload["tags"]["cent"]
    assert cent["broker"]["error"] == "terminal down"
    assert cent["account"] is None
    assert cent["position"] is None
    # file reads (pidfiles + log staleness) survive a dead bridge
    assert "last_decision_min_ago" in cent["bot"]
    assert isinstance(cent["bot"]["supervisor_alive"], bool)


# ---------------------------------------------------------------------------
# 5. Preview — benign no-op (values already as requested)
# ---------------------------------------------------------------------------

def test_preview_benign_noop(client, bots):
    before = bots["cent"].read_bytes()
    payload = _post(client, "/api/risk/preview",
                    {"tag": "cent", "set": ["strategy.rr_multiple=1.0"]})
    assert payload["ok"] is True
    assert payload["no_change"] is True
    assert payload["requires_yes"] is False
    assert payload["warnings"] == []
    assert bots["cent"].read_bytes() == before  # nothing written


# ---------------------------------------------------------------------------
# 6. Preview — aggressive (the CLI banner verbatim, nothing written)
# ---------------------------------------------------------------------------

def test_preview_aggressive_warns_with_cli_banner(client, bots):
    before = bots["btc"].read_bytes()
    payload = _post(client, "/api/risk/preview",
                    {"tag": "btc", "set": ["strategy.rr_multiple=2.5"]})
    assert payload["ok"] is True
    assert payload["no_change"] is False
    assert payload["requires_yes"] is True
    joined = "\n".join(payload["warnings"])
    assert "AGGRESSIVE target" in joined      # the rr >= 1.5 banner text
    assert bots["btc"].read_bytes() == before  # nothing written


# ---------------------------------------------------------------------------
# 7. Preview — invalid (ok:false, key named, nothing written)
# ---------------------------------------------------------------------------

def test_preview_invalid_refused_key_named(client, bots):
    before = bots["btc"].read_bytes()
    payload = _post(client, "/api/risk/preview",
                    {"tag": "btc", "set": ["risk.max_concurrent=0"]})
    assert payload["ok"] is False
    assert any("max_concurrent" in e for e in payload["errors"])
    assert bots["btc"].read_bytes() == before  # nothing written


# ---------------------------------------------------------------------------
# 8. Apply — the gate end to end on copies: write, no-restart, restart
# ---------------------------------------------------------------------------

def test_apply_writes_then_restart_contract(client, bots, restarts):
    # 1) restart:false — the write path through set_risk unchanged, no restart
    payload = _post(client, "/api/risk/apply",
                    {"tag": "btc", "set": ["strategy.rr_multiple=1.5"],
                     "restart": False})
    assert payload["exit_code"] == 0
    assert "wrote" in payload["output"]
    assert restarts == []          # restart false -> restarter never called

    text = bots["btc"].read_text()
    assert "rr_multiple = 1.5" in text
    # the big policy comment block is preserved verbatim
    assert "# The per-trade cap and max_concurrent must always move TOGETHER." in text
    # the result passes the engine's own validator
    assert load_config(bots["btc"]).strategy.rr_multiple == 1.5

    # 2) restart:true with a real change — reaches the CLI restart contract
    payload = _post(client, "/api/risk/apply",
                    {"tag": "btc", "set": ["strategy.rr_multiple=2.0"],
                     "restart": True})
    assert payload["exit_code"] == 0
    assert "wrote" in payload["output"]
    assert restarts == ["btc"]     # the recorder proves the restart ran


# ---------------------------------------------------------------------------
# 9. No GET ever writes
# ---------------------------------------------------------------------------

def test_gets_never_write(client, bots):
    before = {t: p.read_bytes() for t, p in bots.items()}
    _get(client, "/api/status")
    _get(client, "/api/status?tag=cent")
    _get(client, "/api/risk")
    _get(client, "/api/health")
    for t, blob in before.items():
        assert bots[t].read_bytes() == blob


# ---------------------------------------------------------------------------
# 10. CSRF: a cross-origin write is refused before it can touch anything
# ---------------------------------------------------------------------------

def test_cross_origin_post_is_refused(client, bots, restarts):
    """A browser tab on a malicious page would carry a foreign Origin; the
    write path must refuse it outright and write nothing."""
    before = {t: p.read_bytes() for t, p in bots.items()}
    req = urllib.request.Request(
        client + "/api/risk/apply",
        data=json.dumps({"tag": "btc", "set": ["strategy.rr_multiple=3.0"],
                         "restart": False}).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "Origin": "http://evil.example"},
    )
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(req, timeout=10)
    assert excinfo.value.code == 403
    for t, blob in before.items():
        assert bots[t].read_bytes() == blob
    assert restarts == []  # no write, no restart


def test_cross_origin_preview_is_refused(client, bots):
    """Preview is read-only, but the same rule applies so a hostile page
    cannot even probe it."""
    before = bots["btc"].read_bytes()
    req = urllib.request.Request(
        client + "/api/risk/preview",
        data=json.dumps({"tag": "btc", "set": ["strategy.rr_multiple=3.0"]}).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "Origin": "http://evil.example"},
    )
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(req, timeout=10)
    assert excinfo.value.code == 403
    assert bots["btc"].read_bytes() == before


def test_same_origin_post_is_accepted(client, bots):
    """A browser served FROM this dashboard carries Origin http://127.0.0.1:<port>;
    that must pass the check and reach the normal write path."""
    from urllib.parse import urlparse

    port = urlparse(client).port
    before = bots["btc"].read_bytes()
    req = urllib.request.Request(
        client + "/api/risk/preview",
        data=json.dumps({"tag": "btc", "set": ["strategy.rr_multiple=1.5"]}).encode(),
        method="POST",
        headers={"Content-Type": "application/json",
                 "Origin": f"http://127.0.0.1:{port}"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert resp.status == 200
        payload = json.loads(resp.read().decode())
    assert payload["ok"] is True
    assert bots["btc"].read_bytes() == before  # preview still writes nothing
