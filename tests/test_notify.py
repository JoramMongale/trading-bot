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
    monkeypatch.setattr(notify, "DEFAULT_PATH", tmp_path / "nope.toml")
    assert notify.send("hello") is False
    assert "hello" in capsys.readouterr().out


def test_send_never_raises(monkeypatch, capsys):
    def boom(*a, **k):
        raise OSError("network down")
    monkeypatch.setattr(notify, "_call", boom)
    assert notify.send("hi", creds=notify.Telegram("t", "c")) is False
    assert "NOT delivered" in capsys.readouterr().out
