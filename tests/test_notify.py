"""Tests for trading_bot.notify — no network."""

from trading_bot import notify


def test_missing_file_means_not_configured(tmp_path):
    assert notify.load(tmp_path / "nope.toml") is None


def test_incomplete_file_means_not_configured(tmp_path):
    p = tmp_path / "t.toml"
    p.write_text('bot_token = "abc"\n')
    assert notify.load(p) is None


def test_complete_file_loads(tmp_path):
    p = tmp_path / "t.toml"
    p.write_text('bot_token = "abc"\nchat_id = 123\n')
    assert notify.load(p) == notify.Telegram("abc", "123")


def test_send_without_credentials_prints_and_returns_false(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(notify, "NTFY_PATH", tmp_path / "nope.toml")
    monkeypatch.setattr(notify, "TELEGRAM_PATH", tmp_path / "nope2.toml")
    assert notify.send("hello") is False
    assert "hello" in capsys.readouterr().out


def test_send_never_raises(monkeypatch, capsys):
    def boom(*a, **k):
        raise OSError("network down")
    monkeypatch.setattr(notify, "_call", boom)
    assert notify.send("hi", creds=notify.Telegram("t", "c")) is False
    assert "NOT delivered" in capsys.readouterr().out


# --- ntfy ---------------------------------------------------------------------


def test_new_topic_creates_once_and_never_overwrites(tmp_path):
    p = tmp_path / "ntfy.toml"
    topic, created = notify.new_topic(p)
    assert created and topic.startswith("tb-") and len(topic) >= 20
    assert all(c.isalnum() or c == "-" for c in topic)
    again, created2 = notify.new_topic(p)
    assert (again, created2) == (topic, False)
    assert notify.load_ntfy(p) == notify.Ntfy(topic, "https://ntfy.sh")


def test_send_posts_to_ntfy_with_priority(tmp_path, monkeypatch):
    p = tmp_path / "ntfy.toml"
    p.write_text('topic = "tb-abc"\n')
    monkeypatch.setattr(notify, "NTFY_PATH", p)
    monkeypatch.setattr(notify, "TELEGRAM_PATH", tmp_path / "none.toml")
    seen = {}

    class _Resp:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        seen["body"] = req.data.decode()
        seen["priority"] = req.get_header("Priority")
        return _Resp()

    monkeypatch.setattr(notify.urllib.request, "urlopen", fake_urlopen)
    assert notify.send("🔴 cent down", priority="high") is True
    assert seen == {"url": "https://ntfy.sh/tb-abc", "body": "🔴 cent down",
                    "priority": "high"}


def test_ntfy_failure_never_raises(tmp_path, monkeypatch, capsys):
    def boom(*a, **k):
        raise OSError("offline")
    monkeypatch.setattr(notify.urllib.request, "urlopen", boom)
    assert notify.send("x", creds=notify.Ntfy("tb-abc")) is False
    assert "NOT delivered via Ntfy" in capsys.readouterr().out
