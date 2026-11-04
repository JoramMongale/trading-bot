"""Telegram alerts (stdlib only). Used by scripts/watchdog.py.

Credentials live in ``config/telegram.toml``, which is gitignored (the repo is
public)::

    bot_token = "123456:ABC..."
    chat_id = "123456789"

:func:`send` never raises: an alert that cannot be delivered is printed and
reported as False, so a Telegram outage can never break the caller.
"""

from __future__ import annotations

import json
import tomllib
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / "config" / "telegram.toml"
API = "https://api.telegram.org/bot{token}/{method}"


@dataclass(frozen=True)
class Telegram:
    bot_token: str
    chat_id: str


def load(path: str | Path = DEFAULT_PATH) -> Telegram | None:
    """Credentials, or None when the file is missing or incomplete."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        raw = tomllib.loads(p.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return None
    token = str(raw.get("bot_token", "")).strip()
    chat = str(raw.get("chat_id", "")).strip()
    if not token or not chat:
        return None
    return Telegram(token, chat)


def _call(token: str, method: str, params: dict, timeout: float = 10.0) -> dict:
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(API.format(token=token, method=method), data=data)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read(1_000_000))


def send(text: str, creds: Telegram | None = None, timeout: float = 10.0) -> bool:
    """Send ``text`` to the configured chat. True on success, never raises."""
    creds = creds if creds is not None else load()
    if creds is None:
        print(f"[alert, telegram not configured] {text}")
        return False
    try:
        out = _call(creds.bot_token, "sendMessage",
                    {"chat_id": creds.chat_id, "text": text[:4000],
                     "disable_web_page_preview": "true"}, timeout)
        return bool(out.get("ok"))
    except Exception as exc:  # noqa: BLE001 — alerts must never break the caller
        print(f"[alert NOT delivered: {type(exc).__name__}: {exc}] {text}")
        return False


def find_chat_ids(token: str, timeout: float = 10.0) -> list[tuple[str, str]]:
    """(chat_id, name) of everyone who has messaged the bot recently."""
    out = _call(token, "getUpdates", {}, timeout)
    seen: dict[str, str] = {}
    for upd in out.get("result", []):
        msg = upd.get("message") or upd.get("channel_post") or {}
        chat = msg.get("chat") or {}
        if "id" in chat:
            name = chat.get("username") or chat.get("title") or chat.get("first_name") or ""
            seen[str(chat["id"])] = name
    return list(seen.items())
