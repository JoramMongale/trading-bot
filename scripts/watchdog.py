"""Watch the live bots and send phone alerts. Run every 5 minutes.

    python scripts/watchdog.py              one check (what Task Scheduler runs)
    python scripts/watchdog.py --new-topic  create config/ntfy.toml, print the topic
    python scripts/watchdog.py --test       send a test message
    python scripts/watchdog.py --summary    send the daily summary now
    python scripts/watchdog.py --scorecard  print live-vs-backtest results
    python scripts/watchdog.py --dry        print alerts instead of sending them
    python scripts/watchdog.py --find-chat <bot_token>
                                            Telegram only: print your chat id

Alerts go to ntfy (config/ntfy.toml) and/or Telegram (config/telegram.toml);
with neither configured they are only written to output/watchdog.log:
  - bot task not running, startup check (preflight) failing and why,
    crash-loop brake tripped, bot died
  - no candle check for too long while the market is open (frozen bot/terminal)
  - trade opened, rejected, closed (with profit), daily loss limit hit
  - sentiment side or gold veto changed, sentiment data unavailable
  - a daily summary, so silence never has to mean "probably fine", with the
    live-vs-backtest scorecard (scripts/scorecard.py)

Down-type alerts repeat every hour while the problem lasts, and a "back to
normal" message follows when it clears. State lives in
output/watchdog_state.json; every alert is also appended to output/watchdog.log.
The first run only records where the logs end, so it never replays history.

Read-only: it never places, changes or closes anything.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import scorecard  # noqa: E402
from trading_bot import notify  # noqa: E402

OUTPUT = ROOT / "output"
STATE_PATH = OUTPUT / "watchdog_state.json"
WATCHDOG_LOG = OUTPUT / "watchdog.log"
CLOSES_LOG = OUTPUT / "closes.log"
HOUR = 3600
SUMMARY_HOUR_UTC = 6
# Run under pythonw by Task Scheduler: without this every schtasks/tasklist/
# python child would flash a console window every 5 minutes.
NO_WINDOW = {"creationflags": 0x08000000} if os.name == "nt" else {}


@dataclass(frozen=True)
class Bot:
    tag: str
    config: str
    stale_minutes: int   # no decision-log line for this long (market open) -> alert
    market: str          # "gold" (closed weekends) | "crypto" (24/7)

    @property
    def log(self) -> Path:
        return OUTPUT / f"live_{self.tag}.log"

    @property
    def suplog(self) -> Path:
        return OUTPUT / f"supervise_{self.tag}.log"

    @property
    def pidfile(self) -> Path:
        return OUTPUT / f"live_{self.tag}.pid"


# 75 min for gold covers its daily one-hour break; BTC never closes.
BOTS = {
    "cent": Bot("cent", "config/config-cent.toml", 75, "gold"),
    "btc": Bot("btc", "config/config-btc.toml", 20, "crypto"),
}


# --- small helpers -------------------------------------------------------------


def kv(line: str) -> dict[str, str]:
    """key=value tokens of a structured log line."""
    out = {}
    for tok in line.split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            out[k] = v
    return out


def read_new(path: Path, state: dict) -> list[str]:
    """Lines appended to ``path`` since the last call (offset kept in state)."""
    offsets = state.setdefault("offsets", {})
    key = str(path)
    if not path.exists():
        offsets[key] = 0  # read a file that appears later from its first line
        return []
    size = path.stat().st_size
    start = offsets.get(key, size)
    if start > size:  # truncated / rotated
        start = 0
    with path.open("rb") as f:
        f.seek(start)
        data = f.read()
    offsets[key] = start + len(data)
    return data.decode("utf-8", "replace").splitlines()


def market_open(market: str, now: datetime) -> bool:
    """Rough market hours (UTC). Gold: closed Fri 21:00 -> Sun 22:00."""
    if market != "gold":
        return True
    wd, h = now.weekday(), now.hour
    if wd == 5:
        return False
    if wd == 4 and h >= 21:
        return False
    if wd == 6 and h < 22:
        return False
    return True


def task_status(tag: str) -> str | None:
    """Scheduled-task status ("Running", "Ready", ...), None off Windows."""
    if os.name != "nt":
        return None
    try:
        r = subprocess.run(
            ["schtasks", "/Query", "/TN", f"trading-bot-{tag}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=30, **NO_WINDOW,
        )
    except Exception:  # noqa: BLE001
        return None
    if r.returncode != 0:
        return "missing"
    last = [ln for ln in r.stdout.splitlines() if ln.strip()]
    if not last:
        return None
    return last[-1].split('","')[-1].strip().strip('"')


def bot_pid_alive(bot: Bot) -> bool | None:
    """Is the pid in output/live_<tag>.pid a running python? None off Windows."""
    if os.name != "nt" or not bot.pidfile.exists():
        return None if os.name != "nt" else False
    try:
        pid = int(bot.pidfile.read_text().strip())
        r = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FI", "IMAGENAME eq python.exe", "/NH"],
            capture_output=True, text=True, timeout=30, **NO_WINDOW,
        )
        return "python.exe" in r.stdout.lower()
    except Exception:  # noqa: BLE001
        return None


# --- alerting ------------------------------------------------------------------


class Alerts:
    def __init__(self, state: dict, now: float, dry: bool):
        self.state = state
        self.now = now
        self.dry = dry
        self.sent: list[str] = []

    def send(self, text: str, key: str | None = None, repeat: float | None = None):
        """Send now; with ``key``, at most once per ``repeat`` seconds."""
        if key is not None:
            last = self.state.setdefault("alerted", {}).get(key)
            if last is not None and (repeat is None or self.now - last < repeat):
                return
            self.state["alerted"][key] = self.now
        self.sent.append(text)

    def clear(self, key: str, text: str | None = None):
        """Problem ``key`` is over; announce it if it had been alerted."""
        if self.state.setdefault("alerted", {}).pop(key, None) is not None and text:
            self.sent.append(text)

    def flush(self):
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
        OUTPUT.mkdir(parents=True, exist_ok=True)
        with WATCHDOG_LOG.open("a", encoding="utf-8") as fh:
            for text in self.sent:
                fh.write(f"{stamp} {text.replace(chr(10), ' | ')}\n")
        if not self.sent:
            return
        body = "\n\n".join(self.sent)
        # Problems ring louder on the phone than routine news.
        urgent = any(t.startswith(("🔴", "🛑", "⚠️", "🟠")) for t in self.sent)
        if self.dry:
            print(body)
        else:
            notify.send(body, priority="high" if urgent else "default")


# --- checks --------------------------------------------------------------------


def check_supervisor(bot: Bot, lines: list[str], alerts: Alerts, state: dict):
    failing = state.setdefault("preflight_failing", {})
    for line in lines:
        s = line.strip()
        if "[FAIL]" in s:
            failing[bot.tag] = s.split("[FAIL]", 1)[1].strip()
        elif "preflight FAILED" in s:
            failing.setdefault(bot.tag, "see output\\supervise_" + bot.tag + ".log")
        elif "preflight ok" in s:
            failing.pop(bot.tag, None)
            alerts.clear(f"preflight:{bot.tag}",
                         f"🟢 {bot.tag}: startup check passed, bot starting")
        elif "GIVING UP" in s:
            alerts.send(f"🛑 {bot.tag}: supervisor GAVE UP after repeated crashes. "
                        f"The bot is stopped until you fix it and run "
                        f"scripts\\restart_bots.bat start.\n{s}")
        elif "bot DIED" in s:
            alerts.send(f"⚠️ {bot.tag}: bot died, supervisor is restarting it.\n{s}")
    if bot.tag in failing:
        alerts.send(f"🔴 {bot.tag}: startup check failing, NOT trading.\n"
                    f"Reason: {failing[bot.tag]}\n"
                    f"Usual fixes: Algo Trading on (Ctrl+E), right account logged in, "
                    f"terminal connected, no pop-ups.",
                    key=f"preflight:{bot.tag}", repeat=HOUR)


def check_decisions(bot: Bot, lines: list[str], alerts: Alerts, state: dict):
    last = state.setdefault("last", {}).setdefault(bot.tag, {})
    for line in lines:
        d = kv(line)
        ev = d.get("event")
        if ev == "order_placed":
            alerts.send(f"📈 {bot.tag}: opened {d.get('side', 'long').upper()} "
                        f"{d.get('symbol', '')} entry={d.get('entry')} sl={d.get('sl')} "
                        f"tp={d.get('tp')} lots={d.get('volume', '?')} fill={d.get('fill')}")
        elif ev == "order_rejected":
            alerts.send(f"⚠️ {bot.tag}: order REJECTED by the broker.\n{line.strip()}")
        elif ev == "order_skipped" and d.get("reason") == "daily_loss_limit":
            day = line[:10]
            alerts.send(f"🛑 {bot.tag}: daily loss limit hit, no new trades today.\n"
                        f"{line.strip()}", key=f"dll:{bot.tag}:{day}")
        elif ev in ("poll_error", "reconnect_failed"):
            alerts.send(f"⚠️ {bot.tag}: {ev}\n{line.strip()}",
                        key=f"{ev}:{bot.tag}", repeat=HOUR / 2)
        elif ev == "sentiment_direction":
            new = d.get("direction")
            if last.get("direction", "?") != new:
                side = new if new not in (None, "None") else f"default ({d.get('fallback')})"
                alerts.send(f"🧭 {bot.tag}: sentiment now {side} "
                            f"[{d.get('source')} {d.get('bullishness')} as of {d.get('as_of')}]")
                last["direction"] = new
            alerts.clear(f"sent_na:{bot.tag}")
        elif ev == "macro_veto":
            new = d.get("veto_longs")
            if last.get("veto", "?") != new:
                what = ("longs PAUSED (dollar strong + yields rising)" if new == "True"
                        else "longs allowed")
                alerts.send(f"🧭 {bot.tag}: gold macro veto: {what} "
                            f"[dxy {d.get('dxy_bullishness')} as of {d.get('as_of')}]")
                last["veto"] = new
            alerts.clear(f"sent_na:{bot.tag}")
        elif ev == "sentiment_unavailable":
            alerts.send(f"⚠️ {bot.tag}: sentiment data unavailable, using the default "
                        f"direction.\n{line.strip()}", key=f"sent_na:{bot.tag}",
                        repeat=6 * HOUR)


def check_running(bot: Bot, alerts: Alerts, now: datetime):
    status = task_status(bot.tag)
    key = f"down:{bot.tag}"
    if status is not None and status != "Running":
        alerts.send(f"🔴 {bot.tag}: bot task is '{status}', NOT trading.\n"
                    f"Fix: right-click scripts\\restart_bots.bat -> Run as administrator.",
                    key=key, repeat=HOUR)
        return False
    if status == "Running":
        alerts.clear(key, f"🟢 {bot.tag}: bot task running again")
    # Frozen: alive but no decision-log line for too long while the market is open.
    skey = f"stale:{bot.tag}"
    if bot.log.exists() and market_open(bot.market, now) and bot_pid_alive(bot) is not False:
        age_min = (time.time() - bot.log.stat().st_mtime) / 60
        if age_min > bot.stale_minutes:
            alerts.send(f"🟠 {bot.tag}: no candle check for {age_min:.0f} min while the "
                        f"market is open. Terminal frozen or disconnected? Check it, then "
                        f"run restart_bots.bat.", key=skey, repeat=HOUR)
            return True
    alerts.clear(skey, f"🟢 {bot.tag}: candle checks flowing again")
    return True


def run_close_watchers(bots: list[Bot]):
    """Append newly closed trades to output/closes.log (one terminal at a time)."""
    if os.name != "nt":
        return
    py = ROOT / ".venv" / "Scripts" / "python.exe"
    for bot in bots:
        try:
            subprocess.run([str(py), str(ROOT / "scripts" / "watch_closes.py"), "--once",
                            "--config", str(ROOT / bot.config)],
                           cwd=str(ROOT), capture_output=True, timeout=90, **NO_WINDOW)
        except Exception:  # noqa: BLE001 — a close watcher failure is not fatal
            pass


def check_closes(lines: list[str], alerts: Alerts):
    for line in lines:
        if "event=trade_closed" not in line or "[backfill]" in line:
            continue
        d = kv(line)
        profit = d.get("profit", "?")
        icon = "✅" if profit.startswith("+") and profit != "+0.00" else "❌"
        alerts.send(f"{icon} closed {d.get('symbol')} by {d.get('how')}: profit {profit} "
                    f"(R {d.get('r')}) entry={d.get('entry')} exit={d.get('exit')}")


def last_reading(bot: Bot) -> str:
    """Latest sentiment/veto reading from the tail of the decision log."""
    if not bot.log.exists():
        return "no log"
    with bot.log.open("rb") as f:
        f.seek(max(0, bot.log.stat().st_size - 200_000))
        tail = f.read().decode("utf-8", "replace").splitlines()
    for line in reversed(tail):
        d = kv(line)
        if d.get("event") == "sentiment_direction":
            return f"sentiment {d.get('direction')} ({d.get('source')} {d.get('bullishness')})"
        if d.get("event") == "macro_veto":
            return "longs paused (macro veto)" if d.get("veto_longs") == "True" else "longs allowed"
    return "no reading yet"


def summary(bots: list[Bot]) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [f"📋 Daily summary {today}"]
    for bot in bots:
        status = task_status(bot.tag) or "n/a"
        opens = 0
        if bot.log.exists():
            with bot.log.open("rb") as f:
                f.seek(max(0, bot.log.stat().st_size - 2_000_000))
                for ln in f.read().decode("utf-8", "replace").splitlines():
                    if "event=order_placed" in ln and ln[:10] >= _yesterday():
                        opens += 1
        lines.append(f"• {bot.tag}: task {status}, {last_reading(bot)}, "
                     f"{opens} trade(s) opened in 24h")
    if CLOSES_LOG.exists():
        total, n = 0.0, 0
        for ln in CLOSES_LOG.read_text(errors="replace").splitlines():
            if "event=trade_closed" in ln and ln[:10] >= _yesterday():
                try:
                    total += float(kv(ln).get("profit", "0"))
                    n += 1
                except ValueError:
                    pass
        lines.append(f"• closed in 24h: {n} trade(s), profit {total:+.2f} (account currency)")
    try:
        lines.append("")
        lines.append(scorecard.scorecard(scorecard.read_closes(CLOSES_LOG)))
    except Exception as exc:  # noqa: BLE001 -- the summary must still go out
        lines.append(f"(scorecard unavailable: {type(exc).__name__}: {exc})")
    return "\n".join(lines)


def _yesterday() -> str:
    return datetime.fromtimestamp(time.time() - 86400, timezone.utc).strftime("%Y-%m-%d")


# --- main ----------------------------------------------------------------------


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
    os.replace(tmp, STATE_PATH)


def run_once(bots: list[Bot], dry: bool = False) -> list[str]:
    state = load_state()
    first_run = "offsets" not in state
    now = datetime.now(timezone.utc)
    alerts = Alerts(state, time.time(), dry)

    run_close_watchers(bots)
    if first_run:
        # Baseline: remember where every log ends, alert on nothing old.
        for bot in bots:
            read_new(bot.log, state)
            read_new(bot.suplog, state)
        read_new(CLOSES_LOG, state)
        alerts.send("👀 Watchdog started: watching " + ", ".join(b.tag for b in bots)
                    + ". You'll get alerts here.")
    else:
        for bot in bots:
            check_supervisor(bot, read_new(bot.suplog, state), alerts, state)
            check_decisions(bot, read_new(bot.log, state), alerts, state)
            check_running(bot, alerts, now)
        check_closes(read_new(CLOSES_LOG, state), alerts)

    day = now.strftime("%Y-%m-%d")
    if now.hour >= SUMMARY_HOUR_UTC and state.get("summary_day") != day:
        alerts.send(summary(bots))
        state["summary_day"] = day

    save_state(state)
    alerts.flush()
    return alerts.sent


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--bots", default="cent,btc", help="comma-separated tags")
    p.add_argument("--dry", action="store_true", help="print alerts, do not send")
    p.add_argument("--test", action="store_true", help="send a test message")
    p.add_argument("--summary", action="store_true", help="send the daily summary now")
    p.add_argument("--scorecard", action="store_true",
                   help="print the live-vs-backtest scorecard and exit")
    p.add_argument("--find-chat", metavar="BOT_TOKEN", help="Telegram: print chat ids")
    p.add_argument("--new-topic", action="store_true",
                   help="create config/ntfy.toml with a private topic and print it")
    a = p.parse_args(argv)

    if a.new_topic:
        topic, created = notify.new_topic()
        print(("Created config\\ntfy.toml." if created else
               "config\\ntfy.toml already exists -- keeping its topic."))
        print()
        print(f"  Your topic:  {topic}")
        print()
        print("In the ntfy app: tap +, enter this topic exactly, Subscribe.")
        print("Keep it private: anyone who knows it can read your alerts.")
        print("Then run:  .venv\\Scripts\\python scripts\\watchdog.py --test")
        return 0

    if a.scorecard:
        print(scorecard.scorecard(scorecard.read_closes(CLOSES_LOG)))
        return 0

    if a.find_chat:
        chats = notify.find_chat_ids(a.find_chat)
        if not chats:
            print("No messages yet. Open your bot in Telegram, press Start, send 'hi', "
                  "then run this again.")
            return 1
        for cid, name in chats:
            print(f"chat_id = \"{cid}\"   ({name})")
        return 0

    bots = [BOTS[t.strip()] for t in a.bots.split(",") if t.strip()]
    if a.test:
        ok = notify.send("✅ trading-bot watchdog test message. Alerts will arrive here.")
        print("sent" if ok else "NOT sent -- run --new-topic first, or check config\\ntfy.toml")
        return 0 if ok else 1
    if a.summary:
        text = summary(bots)
        print(text) if a.dry else notify.send(text)
        return 0
    for text in run_once(bots, dry=a.dry):
        if not a.dry:
            print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
