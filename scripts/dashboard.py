"""Local web dashboard for the Gold 5m breakout bot — read-mostly, loopback-only.

    python3 scripts/dashboard.py                # binds 127.0.0.1:8765
    python3 scripts/dashboard.py --port 9000    # only the port is configurable
    # open http://127.0.0.1:8765

One page, three tabs: Status (bot health + open position), Risk (editable
through the exact same warned/confirmed gate as the CLI), Account (balance +
recent closes). It puts the read-only picture that today lives in
monitor_trade.py / health_check.py / tune_risk.py into a single browser page,
reusing those scripts' own primitives so the numbers match what the CLI prints
for the same moment.

Safety model
------------
* READ-ONLY BY DEFAULT. Every GET endpoint reads pidfiles, logs, config files
  and the broker — it never writes a file, never places an order and never
  touches launchd. Live data is never cached (Cache-Control: no-store).

* THE ONLY WRITE PATH IS POST /api/risk/apply, which calls
  tune_risk.set_risk() UNCHANGED with yes=True — the browser Confirm button the
  user pressed after seeing the preview warnings IS the CLI's --yes. Preview
  (POST /api/risk/preview) runs the same validation and warning pipeline
  WITHOUT writing, so a browser edit can never bypass what the CLI enforces.

* 127.0.0.1-ONLY. The server binds the literal loopback host and has no --host
  option at all, so it can never be exposed beyond this machine. The MT5 bridge
  it reads through is unauthenticated on the LAN (see STATE.md); this server
  adds zero new network exposure and stores no credentials.

* ZERO NEW DEPENDENCIES. Stdlib only (http.server) plus the repo's existing
  scripts and src packages.
"""

import argparse
import contextlib
import json
import sys
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

# Reuse the established conventions rather than reinventing them: tag -> config
# mapping, pid/liveness/log-staleness helpers, the close-line parser, the
# broker transport fallback and the whole risk-edit contract.
from health_check import (  # noqa: E402
    BOTS,
    TF_MINUTES,
    pid_alive,
    read_pidfile,
    last_log_time,
    _init_terminal,
)
from monitor_trade import parse_close_line  # noqa: E402
from trading_bot.config import load_config, live_symbol  # noqa: E402
from trading_bot.broker.base import BrokerUnavailableError  # noqa: E402
import tune_risk  # noqa: E402


# ---------------------------------------------------------------------------
# JSON payload builders — pure functions over the same primitives the CLIs use
# ---------------------------------------------------------------------------

def _tag_order():
    """cent first — it is the live-money bot — then btc (BOTS order otherwise)."""
    return sorted(BOTS, key=lambda t: (t != "cent", t))


def _bot_section(tag, cfg):
    """File-based bot health: pidfiles + log staleness, exactly like
    health_check/monitor_trade — rendered even when the broker is down."""
    bar_min = TF_MINUTES.get(cfg.data.timeframe, 5)
    sup = read_pidfile(ROOT / f"output/supervise_{tag}.pid")
    bot = read_pidfile(ROOT / f"output/live_{tag}.pid")
    last = last_log_time(ROOT / f"output/live_{tag}.log")
    if last is None:
        last_decision_min_ago = None
        log_level = "WARN"  # monitor: "no timestamped lines yet"
    else:
        age = (datetime.now() - last).total_seconds() / 60
        last_decision_min_ago = round(age, 1)
        log_level = "ok" if age < bar_min * 2 else "FAIL"
    # No supervise pidfile is NORMAL on Windows: supervise_live.bat deliberately
    # never writes one (batch cannot learn a child pid reliably) and the
    # scheduled task is the source of truth. Only a pidfile pointing at a dead
    # process is a real failure. Mirrors health_check/monitor_trade.
    if sup is None:
        supervisor_alive = True  # assumed — on Windows the task is the supervisor
        supervisor_note = "no pidfile (normal on Windows - scheduled task)"
    else:
        supervisor_alive = sup is not None and pid_alive(sup)
        supervisor_note = f"pid {sup}" if supervisor_alive else "PIDFILE PRESENT BUT PROCESS GONE"
    return {
        "supervisor_pid": sup,
        "supervisor_alive": supervisor_alive,
        "supervisor_note": supervisor_note,
        "bot_pid": bot,
        "bot_alive": bot is not None and pid_alive(bot),
        "last_decision_min_ago": last_decision_min_ago,
        "log_level": log_level,
    }


def _broker_section(tag, cfg, magic):
    """Broker + this bot's position, mirroring monitor_trade.py: native import
    first, bridge fallback, positions filtered by magic, current R marked
    against bid for BUY / ask for SELL. A dead bridge returns {error} and the
    caller keeps the file-based bot section.

    The terminal is attached per-config via health_check._init_terminal: a bare
    initialize() on a multi-terminal machine attaches to whichever install it
    finds first, so this bot's symbol/account would be read from the WRONG
    terminal and the position silently reported as missing. The config's
    terminal_path (or bridge port, on macOS) selects the right one."""
    try:
        mt5 = _init_terminal(cfg)
        try:
            ti = mt5.terminal_info()
            acct = mt5.account_info()
            broker = {
                "connected": bool(ti.connected),
                "trade_allowed": bool(ti.trade_allowed),
            }
            account = {
                "login": acct.login,
                "server": acct.server,
                "balance": acct.balance,
                "equity": acct.equity,
                "floating": acct.profit,
                "currency": acct.currency,
            }
            position = None
            for pos in (mt5.positions_get() or []):
                if pos.magic != magic:
                    continue
                side = "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL"
                tick = mt5.symbol_info_tick(pos.symbol)
                p = {
                    "ticket": pos.ticket,
                    "symbol": pos.symbol,
                    "side": side,
                    "volume": pos.volume,
                    "entry": pos.price_open,
                    "sl": pos.sl,
                    "tp": pos.tp,
                    "bid": tick.bid if tick is not None else None,
                    "ask": tick.ask if tick is not None else None,
                    "floating": pos.profit,
                    "floating_pct": (pos.profit / acct.balance * 100
                                     if acct.balance else 0.0),
                    "current_r": None,
                    "sl_pct": None,
                    "tp_pct": None,
                    "open_secs": int(datetime.now(timezone.utc).timestamp() - pos.time),
                }
                if tick is not None and pos.sl:
                    risk = abs(pos.price_open - pos.sl)
                    ref = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask
                    if pos.type == mt5.POSITION_TYPE_BUY:
                        p["current_r"] = (ref - pos.price_open) / risk
                    else:
                        p["current_r"] = (pos.price_open - ref) / risk
                if pos.sl:
                    p["sl_pct"] = abs(pos.price_open - pos.sl) / pos.price_open * 100
                if pos.tp:
                    p["tp_pct"] = abs(pos.tp - pos.price_open) / pos.price_open * 100
                position = p
                break
            return {"broker": broker, "account": account, "position": position}
        finally:
            try:
                mt5.shutdown()
            except Exception:
                pass
    except BrokerUnavailableError as exc:
        return {"broker": {"error": str(exc)}, "account": None, "position": None}


def _closes_section(sym):
    """Recent closes for exactly this symbol, same arithmetic as monitor_trade."""
    closes_path = ROOT / "output" / "closes.log"
    empty = {"rows": [], "totals": {"n": 0, "profit_sum": 0.0, "r_sum": 0.0, "skipped": 0}}
    if not closes_path.exists():
        return empty
    rows = []
    for line in closes_path.read_text(errors="replace").splitlines():
        parsed = parse_close_line(line)
        if parsed and parsed["symbol"] == sym:
            rows.append(parsed)
    if not rows:
        return empty
    profit_sum = sum(row["profit"] for row in rows)
    known = [row for row in rows if row["r"] != "?"]
    r_sum = sum(float(row["r"]) for row in known)
    skipped = len(rows) - len(known)
    return {
        "rows": rows[-5:],
        "totals": {"n": len(rows), "profit_sum": profit_sum, "r_sum": r_sum,
                   "skipped": skipped},
    }


def status_payload(tag="all"):
    """GET /api/status — per-tag health, position, account and closes."""
    tags = _tag_order() if tag == "all" else [tag]
    out = {}
    for t in tags:
        if t not in BOTS:
            out[t] = {"tag": t, "error": f"unknown tag {t!r}"}
            continue
        cfg = load_config(tune_risk._resolve(BOTS[t]))
        magic = cfg.live.magic_number
        sym = live_symbol(cfg)
        brk, acct, pos = (
            _broker_section(t, cfg, magic).values()
        )
        out[t] = {
            "tag": t,
            "config": BOTS[t],
            "magic": magic,
            "symbol": sym,
            "bot": _bot_section(t, cfg),
            "broker": brk,
            "account": acct,
            "position": pos,
            "closes": _closes_section(sym),
        }
    return {"tags": out}


def risk_payload():
    """GET /api/risk — per-tag [risk] table + strategy.rr_multiple + the
    account-wide total vs the standing policy, formatted like the CLI."""
    total, _ = tune_risk._account_total()
    out = {}
    for t in _tag_order():
        cfg_path = tune_risk._resolve(BOTS[t])
        risk, magic = tune_risk._read_risk(cfg_path)
        sections = tune_risk._read_sections(cfg_path)
        rr = sections.get("strategy", {}).get("rr_multiple")
        out[t] = {
            "tag": t,
            "config": BOTS[t],
            "magic": magic,
            "risk": {k: tune_risk._format_value(v) for k, v in risk.items()},
            "strategy_rr_multiple": (tune_risk._format_value(rr)
                                     if rr is not None else None),
        }
    return {
        "tags": out,
        "account_total": round(total, 2),
        "standing_policy": tune_risk.STANDING_POLICY_PCT,
    }


# ---------------------------------------------------------------------------
# Risk edit gate — preview mirrors set_risk's pre-write pipeline verbatim;
# apply IS set_risk unchanged.
# ---------------------------------------------------------------------------

def _preview_err(errors, total_before, total_after):
    return {
        "ok": False,
        "errors": errors,
        "changes": [],
        "total_before": total_before,
        "total_after": total_after,
        "requires_yes": False,
        "warnings": [],
        "no_change": False,
    }


def _preview(tag, items):
    """POST /api/risk/preview — the SAME validation, total arithmetic and
    warnings as tune_risk.set_risk (lines ~419-491), writing nothing."""
    if tag not in tune_risk.BOTS:
        return _preview_err([f"unknown tag {tag!r}"], None, None)
    cfg_rel = tune_risk.BOTS[tag]
    path = tune_risk._resolve(cfg_rel)
    if not path.exists():
        return _preview_err([f"config not found: {path}"], None, None)
    sections = tune_risk._read_sections(path)
    risk = sections.get("risk", {})
    if not risk:
        return _preview_err([f"no [risk] table in {cfg_rel}"], None, None)
    text = path.read_text(encoding="utf-8")

    total_before, details = tune_risk._account_total()
    old_cap, old_slots = details[tag]

    changes = {}
    errors = []
    for item in items:
        if "=" not in item:
            errors.append(f"{item!r} is not key=value")
            continue
        key, _, value_str = item.partition("=")
        key = key.strip()
        section, name = tune_risk._split_key(key)
        if section not in tune_risk._EDITABLE_SECTIONS:
            errors.append(f"unknown section {section!r} — editable: "
                          f"{', '.join(tune_risk._EDITABLE_SECTIONS)}")
            continue
        table = sections.get(section, {})
        if name not in table:
            errors.append(f"unknown key {key!r} — valid [{section}] keys: "
                          f"{', '.join(table)}")
            continue
        dotted = f"{section}.{name}"
        try:
            changes[dotted] = tune_risk._validate_change(dotted, value_str, table[name])
        except ValueError as exc:
            errors.append(str(exc))
    if errors:
        return _preview_err(errors, total_before, total_before)

    if not changes:
        return _preview_err(["no changes to apply"], total_before, total_before)

    new_cap = changes.get("risk.max_loss_pct_per_trade", old_cap)
    new_slots = changes.get("risk.max_concurrent", old_slots)
    total_after = total_before - old_cap * old_slots + new_cap * new_slots

    change_list = []
    for dotted, new_val in changes.items():
        section, name = tune_risk._split_key(dotted)
        change_list.append({
            "dotted": dotted,
            "old": tune_risk._format_value(sections[section][name]),
            "new": tune_risk._format_value(new_val),
        })

    # Mirror the CLI's no-change early return: values already as requested, so
    # nothing would be written, nothing confirmed and no warnings shown.
    new_text = text
    for section in sorted({tune_risk._split_key(k)[0] for k in changes}):
        section_edits = {
            tune_risk._split_key(k)[1]: v for k, v in changes.items()
            if k.startswith(section + ".")
        }
        new_text = tune_risk._apply_edits(new_text, section, section_edits)
    if new_text == text:
        return {
            "ok": True,
            "errors": [],
            "changes": change_list,
            "total_before": total_before,
            "total_after": total_after,
            "requires_yes": False,
            "warnings": [],
            "no_change": True,
        }

    warnings = []
    if "risk.max_concurrent" in changes or "risk.max_loss_pct_per_trade" in changes:
        warnings.append(tune_risk._LEVERAGE_WARNING)
    aggressive = tune_risk._aggressive_warnings(changes, total_after)
    warnings.extend(aggressive)

    total_changed = abs(total_before - total_after) > 1e-9
    return {
        "ok": True,
        "errors": [],
        "changes": change_list,
        "total_before": total_before,
        "total_after": total_after,
        "requires_yes": total_changed or bool(aggressive),
        "warnings": warnings,
        "no_change": False,
    }


def _apply(tag, items, restart):
    """POST /api/risk/apply — the ONLY write path. Calls tune_risk.set_risk
    unchanged; yes=True because the browser Confirm after a preview IS the
    CLI's --yes. restart=True runs the real launchd bootout+bootstrap (the
    CLI's own behaviour, up to 300s polling for a new pid)."""
    if tag not in tune_risk.BOTS:
        return {"exit_code": 2, "output": f"error: unknown tag {tag!r}"}
    out, err = StringIO(), StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = tune_risk.set_risk(tag, items, yes=True, no_restart=not restart)
        except Exception as exc:  # noqa: BLE001 — report any failure to the page
            code = 2
            print(f"error: {exc}", file=sys.stderr)
    return {"exit_code": code, "output": out.getvalue() + err.getvalue()}


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class _Handler(BaseHTTPRequestHandler):
    server_version = "TradingBotDashboard/1.0"

    def log_message(self, fmt, *args):
        pass  # _respond logs one line per request; never log bodies/configs

    def _origin_ok(self):
        """Reject cross-origin writes (CSRF). The server is loopback-only, so a
        request that got here either came from this machine's own browser or
        from a scripted client — the only ones that may change live risk are
        the ones carrying this origin. A browser tab pointed at a malicious
        page cannot forge the Origin header (browsers set it; scripts can't)."""
        origin = self.headers.get("Origin")
        if origin is None:
            # No browser involved (curl, Python, the repo's own tests): the
            # loopback bind is the only exposure, so allow.
            return True
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        o = origin.lower().rstrip("/")
        # Accept only http://127.0.0.1:<port> or http://localhost:<port>.
        return o in {f"http://{host}:{self.server.server_port}",
                     f"http://127.0.0.1:{self.server.server_port}",
                     f"http://localhost:{self.server.server_port}"}

    def _respond(self, status, payload, content_type="application/json"):
        body = (json.dumps(payload).encode("utf-8")
                if not isinstance(payload, bytes) else payload)
        print(f"[dashboard] {self.command} {self.path} {status}")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            body = {}
        return body if isinstance(body, dict) else {}

    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/":
                html = ROOT / "scripts" / "dashboard.html"
                try:
                    self._respond(200, html.read_bytes(), "text/html; charset=utf-8")
                except OSError:
                    self._respond(500, {"error": "scripts/dashboard.html not found"})
            elif parsed.path == "/api/health":
                self._respond(200, {"ok": True})
            elif parsed.path == "/api/status":
                qs = urllib.parse.parse_qs(parsed.query)
                self._respond(200, status_payload(qs.get("tag", ["all"])[0]))
            elif parsed.path == "/api/risk":
                self._respond(200, risk_payload())
            else:
                self._respond(404, {"error": f"not found: {parsed.path}"})
        except Exception as exc:  # noqa: BLE001 — a bad request must not kill a request
            self._respond(500, {"error": f"{type(exc).__name__}: {exc}"})

    def do_POST(self):
        try:
            if not self._origin_ok():
                self._respond(403, {"error": "cross-origin write refused"})
                return
            parsed = urllib.parse.urlparse(self.path)
            body = self._json_body()
            if parsed.path == "/api/risk/preview":
                items = body.get("set") or []
                if not isinstance(items, list) or not all(
                        isinstance(i, str) for i in items):
                    self._respond(400, _preview_err(
                        ["set must be a list of key=value strings"], None, None))
                    return
                self._respond(200, _preview(body.get("tag"), items))
            elif parsed.path == "/api/risk/apply":
                items = body.get("set") or []
                if not isinstance(items, list) or not all(
                        isinstance(i, str) for i in items):
                    self._respond(400, {"exit_code": 2,
                                        "output": "set must be a list of key=value strings"})
                    return
                self._respond(200, _apply(body.get("tag"), items,
                                          bool(body.get("restart", False))))
            else:
                self._respond(404, {"error": f"not found: {parsed.path}"})
        except Exception as exc:  # noqa: BLE001
            self._respond(500, {"error": f"{type(exc).__name__}: {exc}"})


def build_parser():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1].strip())
    p.add_argument("--port", type=int, default=8765,
                   help="port to listen on 127.0.0.1 (default 8765) — the "
                        "bind host is fixed to loopback and cannot be changed")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    print(f"dashboard on http://127.0.0.1:{args.port}")
    print("read-only by default; the ONLY write path is POST /api/risk/apply, "
          "which calls tune_risk.set_risk() unchanged (browser Confirm = --yes)")
    server = _Server(("127.0.0.1", args.port), _Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
