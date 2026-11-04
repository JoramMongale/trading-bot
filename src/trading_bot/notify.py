"""Phone alerts (stdlib only). Used by scripts/watchdog.py.

Two channels; whichever is configured is used (both, if both are):

- **ntfy** (recommended): free push app, no account. ``config/ntfy.toml``::

      topic = "tb-..."              # create with: watchdog.py --new-topic
      server = "https://ntfy.sh"    # optional

  Subscribe to the same topic in the ntfy app. On ntfy.sh anyone who knows a
  topic name can read it, so the name is long and random -- keep it private.

- **Telegram**: ``config/telegram.toml`` with ``bot_token`` and ``chat_id``.

Both files are gitignored (the repo is public). :func:`send` never raises: an
alert that cannot be delivered is printed and reported as False, so an outage
can never break the caller.
"""

from __future__ import annotations

import json
import secrets
import tomllib
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NTFY_PATH = ROOT / "config" / "ntfy.toml"
TELEGRAM_PATH = ROOT / "config" / "telegram.toml"
DEFAULT_PATH = TELEGRAM_PATH  # kept for callers of the Telegram-only version
NTFY_SERVER = "https://ntfy.sh"
TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
PRIORITIES = ("min", "low", "default", "high", "urgent")


@dataclass(frozen=True)
class Ntfy:
    topic: str
    server: str = NTFY_SERVER


@dataclass(frozen=True)
class Telegram:
    bot_token: str
    chat_id: str


def _read_toml(path: str | Path) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        return tomllib.loads(p.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return None


def load_ntfy(path: str | Path = NTFY_PATH) -> Ntfy | None:
    raw = _read_toml(path)
    if not raw:
        return None
    topic = str(raw.get("topic", "")).strip()
    if not topic:
        return None
    server = str(raw.get("server", NTFY_SERVER)).strip().rstrip("/") or NTFY_SERVER
    return Ntfy(topic, server)


def load(path: str | Path = TELEGRAM_PATH) -> Telegram | None:
    """Telegram credentials, or None when missing or incomplete."""
    raw = _read_toml(path)
    if not raw:
        return None
    token = str(raw.get("bot_token", "")).strip()
    chat = str(raw.get("chat_id", "")).strip()
    if not token or not chat:
        return None
    return Telegram(token, chat)


def new_topic(path: str | Path = NTFY_PATH) -> tuple[str, bool]:
    """Create config/ntfy.toml with a random topic. Returns (topic, created).

    An existing file is never overwritten -- its topic is returned instead,
    so running this twice cannot silently disconnect a subscribed phone.
    """
    existing = load_ntfy(path)
    if existing is not None:
        return existing.topic, False
    topic = "tb-" + secrets.token_urlsafe(18).replace("_", "x").replace("-", "y")
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "# ntfy push alerts for scripts/watchdog.py. Gitignored -- keep the topic\n"
        "# private: on ntfy.sh anyone who knows it can read the alerts.\n"
        f'topic = "{topic}"\n'
        f'server = "{NTFY_SERVER}"\n',
        encoding="utf-8",
    )
    return topic, True


def _post_ntfy(ch: Ntfy, text: str, priority: str, timeout: float) -> bool:
    req = urllib.request.Request(
        f"{ch.server}/{ch.topic}",
        data=text.encode("utf-8"),
        headers={"Title": "trading-bot", "Priority": priority},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return 200 <= resp.status < 300


def _call(token: str, method: str, params: dict, timeout: float = 10.0) -> dict:
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(TELEGRAM_API.format(token=token, method=method), data=data)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read(1_000_000))


def _post_telegram(ch: Telegram, text: str, timeout: float) -> bool:
    out = _call(ch.bot_token, "sendMessage",
                {"chat_id": ch.chat_id, "text": text[:4000],
                 "disable_web_page_preview": "true"}, timeout)
    return bool(out.get("ok"))


def send(text: str, creds=None, timeout: float = 10.0, priority: str = "default") -> bool:
    """Send ``text`` to every configured channel. True if any got it. Never raises.

    ``creds`` pins one channel (an :class:`Ntfy` or :class:`Telegram`);
    otherwise config/ntfy.toml and config/telegram.toml are both tried.
    ``priority`` (ntfy only): min | low | default | high | urgent.
    """
    if priority not in PRIORITIES:
        priority = "default"
    channels = [creds] if creds is not None else [
        c for c in (load_ntfy(NTFY_PATH), load(TELEGRAM_PATH)) if c is not None
    ]
    if not channels:
        print(f"[alert, no phone channel configured] {text}")
        return False
    delivered = False
    for ch in channels:
        try:
            if isinstance(ch, Ntfy):
                ok = _post_ntfy(ch, text[:4000], priority, timeout)
            else:
                ok = _post_telegram(ch, text, timeout)
        except Exception as exc:  # noqa: BLE001 — alerts must never break the caller
            print(f"[alert NOT delivered via {type(ch).__name__}: "
                  f"{type(exc).__name__}: {exc}] {text}")
            ok = False
        delivered = delivered or ok
    return delivered


def find_chat_ids(token: str, timeout: float = 10.0) -> list[tuple[str, str]]:
    """Telegram: (chat_id, name) of everyone who has messaged the bot recently."""
    out = _call(token, "getUpdates", {}, timeout)
    seen: dict[str, str] = {}
    for upd in out.get("result", []):
        msg = upd.get("message") or upd.get("channel_post") or {}
        chat = msg.get("chat") or {}
        if "id" in chat:
            name = chat.get("username") or chat.get("title") or chat.get("first_name") or ""
            seen[str(chat["id"])] = name
    return list(seen.items())
