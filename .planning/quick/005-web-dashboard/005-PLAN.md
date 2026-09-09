---
phase: 005-web-dashboard
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - scripts/dashboard.py
  - scripts/dashboard.html
  - tests/test_dashboard.py
autonomous: false
user_setup: []

must_haves:
  truths:
    - "python3 scripts/dashboard.py serves a page on 127.0.0.1:8765 ONLY (never 0.0.0.0, no --host option) and the page renders three tabs: Status, Risk, Account"
    - "The Status tab shows, per bot, supervisor/bot pid + alive, last-decision age, and any open position (entry/SL/TP/bid/ask/floating USC + %/current R) — the same numbers monitor_trade.py prints for the same moment"
    - "The Account tab shows balance/equity/floating + recent closes parsed from output/closes.log"
    - "The Risk tab shows every [risk] key + strategy.rr_multiple per tag with current values and the account-wide total (cap x slots summed across bots) vs the 2.0% standing policy"
    - "Editing is read-only until Preview renders the SAME warnings the CLI prints (rr>=1.5, cap>=10%, account-wide total >5%, leverage note) and the before/after diff; Confirm & Apply runs tune_risk.set_risk unchanged — the browser confirm IS the --yes, nothing is bypassed"
    - "No write path exists outside the risk apply endpoint; GET endpoints never write and apply never writes unless the user confirmed a preview"
  artifacts:
    - path: "scripts/dashboard.py"
      provides: "stdlib http server (127.0.0.1-only) + JSON API: status, risk, risk preview, risk apply"
      contains: "127.0.0.1"
    - path: "scripts/dashboard.html"
      provides: "three-tab UI with inline warnings and the confirm-before-apply gate"
      contains: "api/risk/preview"
    - path: "tests/test_dashboard.py"
      provides: "endpoint tests over an ephemeral-port server with tmp config copies and a stubbed broker"
      contains: "ephemeral"
  key_links:
    - from: "scripts/dashboard.py"
      to: "scripts/tune_risk.py"
      via: "apply endpoint calls tune_risk.set_risk(tag, items, yes=True, no_restart=...); preview reuses _split_key/_validate_change/_account_total/_aggressive_warnings"
      pattern: "set_risk"
    - from: "scripts/dashboard.py"
      to: "scripts/health_check.py"
      via: "BOTS, Report, pid_alive, read_pidfile, last_log_time, TF_MINUTES imported for the bot sections"
      pattern: "from health_check import"
    - from: "scripts/dashboard.py"
      to: "scripts/monitor_trade.py"
      via: "parse_close_line imported for recent closes; broker reach via the same _load_mt5 -> _load_silicon_bridge fallback"
      pattern: "parse_close_line"
    - from: "scripts/dashboard.html"
      to: "scripts/dashboard.py"
      via: "fetch(/api/status, /api/risk, POST /api/risk/preview then POST /api/risk/apply)"
      pattern: "api/risk"
---

<objective>
A local web dashboard for the Gold 5m breakout bot: bot health, open position,
risk settings (editable through the exact same warned/confirmed gate as the
CLI), and account view — one `python3 scripts/dashboard.py` away.

Purpose: today the user reads `monitor_trade.py`, `health_check.py` and
`tune_risk.py` from three terminals and edits risk by hand-copying CLI
commands. The dashboard puts the same read-only picture in one browser page
and gives the Risk tab the exact `tune_risk.py` edit contract — same
validation, same aggressive warnings (rr>=1.5, cap>=10%, total>5%), same
`--yes` gate — so a browser edit can never bypass what the CLI enforces.

Non-negotiables (from STATE.md):
- REAL MONEY is live on gold (config/config-cent.toml, launchd
  com.joram.trading-bot-cent). Read-only by default; the ONLY write path is
  the risk apply endpoint, which calls `tune_risk.set_risk()` verbatim.
- SECURITY: the MT5 bridge is unauthenticated on 0.0.0.0:8001. The dashboard
  binds 127.0.0.1 ONLY, with no `--host` option at all, and adds zero new
  network exposure. No credentials are stored.
- ZERO new dependencies: pyproject.toml ships only pandas/numpy; the
  dashboard uses the stdlib (`http.server`) plus the existing scripts.

How to run (also printed by the script's docstring):
    python3 scripts/dashboard.py            # binds 127.0.0.1:8765
    python3 scripts/dashboard.py --port 9000  # only the port is configurable
    # open http://127.0.0.1:8765

Output: `scripts/dashboard.py` (server + JSON API), `scripts/dashboard.html`
(single three-tab page), `tests/test_dashboard.py`, and a browser
human-verify checkpoint that also closes the pending monitor human-verify
from quick task 001 by cross-checking dashboard vs monitor output.
</objective>

<execution_context>
@/Users/joram/.config/opencode/get-shit-done/workflows/execute-plan.md
@/Users/joram/.config/opencode/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/quick/003-risk-tuning-script/003-PLAN.md
@scripts/tune_risk.py
@scripts/monitor_trade.py
@scripts/health_check.py
@config/config-cent.toml
@config/config-btc.toml
</context>

<tasks>

<task type="auto">
  <name>Task 1: Implement scripts/dashboard.py — 127.0.0.1-only HTTP server + JSON API</name>
  <files>scripts/dashboard.py</files>
  <action>
Create `scripts/dashboard.py` — stdlib-only (http.server, json, argparse,
contextlib, urllib, tomllib via the imported helpers). Do NOT add any
dependency. Follow the repo conventions exactly:

Module wiring (same as monitor_trade.py / tune_risk.py):
- `ROOT = Path(__file__).resolve().parent.parent`
- `sys.path.insert(0, str(ROOT / "src"))` and `sys.path.insert(0, str(ROOT / "scripts"))`
- `from health_check import BOTS, pid_alive, read_pidfile, last_log_time, TF_MINUTES`
- `from monitor_trade import parse_close_line`
- `from trading_bot.config import load_config, live_symbol`
- `from trading_bot.broker.base import BrokerUnavailableError`
- `from trading_bot.broker.mt5 import _load_mt5, _load_silicon_bridge`
- `import tune_risk` and reuse its functions — do NOT reimplement any gate.

Security (hard requirements):
- `ThreadingHTTPServer(("127.0.0.1", port), _Handler)` — the bind host is
  the literal string "127.0.0.1"; there is NO --host argument, so the
  dashboard can never be exposed beyond loopback. The only network knob is
  `--port` (default 8765).
- Every JSON API response carries `Cache-Control: no-store` and
  `X-Content-Type-Options: nosniff`. Live data must never be cached.
- No credentials, no forwarded state: the dashboard calls the local MT5
  bridge only through the existing localhost path (`_load_mt5` then fallback
  `_load_silicon_bridge(cfg.live.bridge_host, cfg.live.bridge_port)`), exactly
  like monitor_trade.py. It never binds, forwards, or logs anything secret.
- Log one line per request to the console (method, path, status); never log
  request bodies or config values.

HTTP surface:
- `GET /` → serve scripts/dashboard.html (read from disk per request).
- `GET /api/status?tag=all` (default all, or a single tag) → per tag JSON:
    {tag, config, magic, symbol, bot: {supervisor_pid, supervisor_alive,
     bot_pid, bot_alive, last_decision_min_ago, log_level},
     broker: {...}|{error}, position: {...}|null, account: {...}|null,
     closes: {rows:[...], totals:{n, profit_sum, r_sum}}}
  Build it from the same primitives and formulas monitor_trade.py uses:
  - BOT section: read pidfiles ROOT/output/supervise_{tag}.pid and
    ROOT/output/live_{tag}.pid, pid_alive(), last_log_time(
    ROOT/output/live_{tag}.log) with the same OK/WARN/FAIL level logic
    (age < bar_min*2 OK else FAIL) — these are file reads and MUST render
    even when the broker is unreachable.
  - BROKER section: try `_load_mt5()`, except BrokerUnavailableError fall
    back to `_load_silicon_bridge(host, port)`; `initialize()`;
    `terminal_info()` → connected/trade_allowed; `account_info()` →
    login/server/balance/equity/profit/currency; `positions_get()` filtered
    by `pos.magic == magic`; `symbol_info_tick(pos.symbol)` for bid/ask.
    Current R marked against bid for BUY and ask for SELL (monitor's
    formula); floating profit + percent of balance; SL/TP distances; open
    duration. On any BrokerUnavailableError return the section as
    {error: "..."} and KEEP the bot section — the page must degrade
    gracefully when the terminal/container is down (market closed, weekend,
    cold boot). Call `shutdown()` in a finally.
  - CLOSES section: parse ROOT/output/closes.log with monitor_trade's
    parse_close_line, filter by exact symbol == sym (live_symbol(cfg)),
    last 5 rows + totals (n, profit sum, known-R sum, skipped count) — same
    arithmetic as monitor_trade.
- `GET /api/risk` → per tag: {tag, config, magic,
    risk: {key: formatted_value}, strategy_rr_multiple: value|null,
    account_total, standing_policy} using tune_risk._read_risk,
    tune_risk._read_sections, tune_risk._account_total and
    tune_risk._format_value (value formatting must match the CLI: ints as
    ints, floats minimally, strings quoted).
- `POST /api/risk/preview` body {tag, set: ["key=value", ...]} → run the
  SAME pre-write pipeline as tune_risk.set_risk (lines ~419-491 of
  tune_risk.py) WITHOUT writing anything, reusing its functions verbatim:
  `tune_risk._split_key`, `tune_risk._EDITABLE_SECTIONS`,
  `tune_risk._read_sections`, `tune_risk._validate_change`,
  `tune_risk._account_total`, `tune_risk._format_value`,
  `tune_risk._aggressive_warnings`. Mirror the total_after arithmetic
  exactly (total_before - old_cap*old_slots + new_cap*new_slots) and
  `requires_yes = total_changed or bool(aggressive)` — identical to the
  CLI gate. Return JSON:
    {ok: bool, errors: ["..."], changes: [{dotted, old, new}],
     total_before, total_after, requires_yes: bool,
     warnings: ["..."],   # the aggressive banners + leverage warning, same text
     no_change: bool}
  NEVER write, never restart, never prompt. Validation errors return ok:false
  with the key named, exactly as the CLI names it.
- `POST /api/risk/apply` body {tag, set: [...], restart: bool} → calls
  `tune_risk.set_risk(tag, set, yes=True, no_restart=not restart)` with
  stdout+stderr captured via contextlib.redirect_stdout/redirect_stderr into
  a StringIO. Return {exit_code, output}. `yes=True` is deliberate: the
  browser Confirm button the user pressed after seeing the preview warnings
  IS the CLI's --yes. restart=True runs the real launchd bootout+bootstrap
  restart (may take up to 300s polling for a new pid — that is the CLI's
  own behavior, do not change it). This endpoint is the ONLY write path in
  the whole server.
- `GET /api/health` → {ok: true} so the page can detect the server is up.

Docstring: document the safety model (read-only by default; the only write
path goes through tune_risk.set_risk unchanged; 127.0.0.1-only binding;
zero new dependencies) and the run command.

Do NOT touch: tune_risk.py, monitor_trade.py, health_check.py, any config,
the engine, or the launchd agents. This is a new read-mostly frontend that
delegates all writes to tune_risk.py.
  </action>
  <verify>
python3 -m py_compile scripts/dashboard.py && \
python3 scripts/dashboard.py --port 8765 &
sleep 1; curl -s http://127.0.0.1:8765/api/health; \
curl -s http://127.0.0.1:8765/api/risk | head -c 400; \
curl -s 'http://127.0.0.1:8765/api/status?tag=cent' | head -c 400; \
curl -s -X POST http://127.0.0.1:8765/api/risk/preview \
  -d '{"tag":"cent","set":["strategy.rr_multiple=2.0"]}' | head -c 400; \
kill %1; git status --short config/   # empty: nothing wrote to configs
  </verify>
  <done>Server binds 127.0.0.1:8765, serves /api/health, /api/risk,
/api/status and /api/risk/preview with correct JSON; the preview of an
aggressive change returns the rr warning; config/ untouched; no new
dependencies added.</done>
</task>

<task type="auto">
  <name>Task 2: Implement scripts/dashboard.html — three-tab UI with inline warnings</name>
  <files>scripts/dashboard.html</files>
  <action>
Create `scripts/dashboard.html` — ONE self-contained page, no frameworks, no
CDNs, plain HTML/CSS/JS (vanilla fetch). Dark-on-light, readable, compact.
Tabs: Status, Risk, Account. A refresh button re-fetches everything; a 15s
auto-refresh toggle (off by default) is optional.

STATUS TAB:
- Per tag (cent first — it is the live money bot, then btc): a card with
  supervisor pid + alive, bot pid + alive, last decision (min ago), colored
  ok/warn/fail badges matching health_check's severity colors.
- Open position card (or "no open position"): entry / SL / TP / bid / ask /
  floating USC (+%) / current R, SL and TP distances, open duration.
- If broker is {error}: show the error banner and keep the file-based bot
  sections visible.

ACCOUNT TAB:
- Balance / equity / floating / currency / login @ server (per tag that has
  a broker section; dedupe to one account row since both bots share one
  account).
- Recent closes table (last 5 from /api/status closes.rows) with
  ts/symbol/how/profit/R, plus totals (n closed, profit sum, sum R).

RISK TAB:
- Per tag, a form with one input per editable key: every key of the [risk]
  table plus strategy.rr_multiple (from /api/risk). Show current value and
  the account-wide total vs the standing policy up top.
- "Preview changes" button → POST /api/risk/preview with the dotted
  key=value pairs of the CHANGED inputs only. Render the response inline,
  BEFORE any apply is possible:
    * per-key diff (dotted: old -> new),
    * account-wide total before -> after,
    * each warning banner VERBATIM from the response warnings array (the
      aggressive rr/loss/total banners and the leverage note) styled as
      prominent warning boxes — these are the exact CLI texts,
    * errors (ok:false) as red lines naming the key.
  A "requires_yes" notice ("this change requires confirmation — confirm to
  apply") is shown when requires_yes is true.
- "Confirm & Apply" button: enabled ONLY after a successful preview; clicking
  it is the explicit --yes equivalent. A checkbox "Restart the launchd agent
  to apply now (default on, matches the CLI; can take up to 5 minutes)" maps
  to the apply body's restart field. POST /api/risk/apply, then render the
  captured CLI output verbatim in a <pre> block (the same text the CLI
  prints). On ok:false render errors and do NOT enable apply.
- A permanent note on the tab: "Read-only unless you preview and then
  confirm. Edits go through scripts/tune_risk.py unchanged — the same
  validation and warnings as the CLI."

Layout: header with page title + refresh + auto-refresh toggle; tab buttons;
three panels. All fetched data rendered server-side-format consistent (use
the same rounded formats the CLI prints: floats minimal, pct with 2 dp).
  </action>
  <verify>
python3 -m py_compile /dev/null 2>/dev/null; \
curl -s http://127.0.0.1:8765/ | grep -c 'api/risk/preview'  # page served (server from Task 1)
# open http://127.0.0.1:8765 in a browser for the visual check is the checkpoint task;
# here: confirm the HTML has no external references (no http:// script/style/link tags):
grep -c 'src="http\|href="http' scripts/dashboard.html || echo "no external refs"
  </verify>
  <done>scripts/dashboard.html is self-contained (zero external references),
serves through the dashboard, implements the three tabs, renders preview
warnings verbatim, and gates the apply button behind a successful preview +
explicit confirm.</done>
</task>

<task type="auto">
  <name>Task 3: Tests for the dashboard API, edit gate, and loopback binding</name>
  <files>tests/test_dashboard.py</files>
  <action>
Create `tests/test_dashboard.py` following the repo's pytest conventions
(pythonpath=src set in pyproject). Import the module as the repo does
(`sys.path.insert(0, str(ROOT / "scripts"))` then `import dashboard`).
For the endpoint tests, start a real `dashboard._Server` on 127.0.0.1 with
port 0 (ephemeral) in a background thread and hit it with urllib.request —
stdlib end to end, no external test server.

Isolation (mirror test_tune_risk.py):
- Monkeypatch `dashboard.BOTS` AND `tune_risk.BOTS` to point at tmp_path
  copies of config/config-btc.toml and config/config-cent.toml (via a
  fixture that copies both into tmp_path). The live configs are NEVER
  written.
- Monkeypatch `tune_risk._restart_agent` to a recorder that returns 0 (the
  established autouse pattern from test_tune_risk — never bootout the real
  launchd agents).
- Monkeypatch `dashboard._load_mt5` (and `dashboard._load_silicon_bridge`,
  which should never be reached when _load_mt5 succeeds) to return a small
  `_FakeBroker` class in the test file: `.initialize()` True,
  `.terminal_info()` → SimpleNamespace(connected=True, trade_allowed=True),
  `.account_info()` → SimpleNamespace(login=..., server="...",
  balance=3139.30, equity=3140.00, profit=+0.70, currency="USC"),
  `.positions_get()` → [one position with magic matching the cent magic,
  price_open, sl, tp, profit, symbol, type, time], `.symbol_info_tick()`
  → SimpleNamespace(bid=..., ask=...), `.shutdown()` no-op. For the
  degraded-broker test patch `dashboard._load_mt5` to raise
  BrokerUnavailableError.

Tests required:

1. Server binds loopback only: constructing the server class with an
   ephemeral port yields `server_address` starting with "127.0.0.1" (the
   literal bind host from the code — assert "127.0.0.1" appears in
   server.server_address). Assert the dashboard module has no --host
   argument in its argparse parser.
2. GET /api/risk: returns risk keys for both tags from the tmp copies
   (cent max_loss_pct_per_trade == 20.0, strategy.rr_multiple == 2.0; btc
   == 0.5 and 1.0) and the account-wide total 21.0 vs standing policy 2.0.
3. GET /api/status: with the fake broker, returns the open position with
   entry/SL/TP and floating values, account balance 3139.30, and closes
   rows parsed from the repo's output/closes.log (assert at least the
   BTCUSDc rows are filtered by symbol and totals are numeric). The bot
   section (pid alive) is present even though the broker is faked.
4. Degraded broker: with `dashboard._load_mt5` raising
   BrokerUnavailableError, GET /api/status returns HTTP 200 with
   broker.error set and the bot section still present (file reads survive
   a dead bridge).
5. Preview — benign no-op: POST /api/risk/preview {"tag":"cent",
   "set":["strategy.rr_multiple=2.0"]} returns ok:true, warnings empty,
   no_change:true, requires_yes:false.
6. Preview — aggressive: POST /api/risk/preview {"tag":"btc",
   "set":["strategy.rr_multiple=2.0"]} returns ok:true,
   requires_yes:true, and the warnings array CONTAINS the rr>=1.5 banner
   text ("AGGRESSIVE target"). Nothing written (config copy byte-identical).
7. Preview — invalid: POST /api/risk/preview {"tag":"btc",
   "set":["risk.max_concurrent=0"]} returns ok:false with an error naming
   max_concurrent, config copy byte-identical.
8. Apply — the gate, end to end on copies: POST /api/risk/apply
   {"tag":"btc","set":["strategy.rr_multiple=1.5"],"restart":false} returns
   exit_code 0 and output containing "wrote" — the tmp config now has
   rr_multiple = 1.5, comments preserved (assert the big policy comment
   block of the btc copy is still verbatim), the result passes the real
   load_config(), and the restarter was NOT called (restart false). Then
   apply {"restart":true} with a no-op set ("strategy.rr_multiple=1.5"
   again) and assert tune_risk._restart_agent was called with "btc" (the
   recorder) — proving the restart checkbox reaches the CLI contract.
9. No GET ever writes: after all GET calls, git status of the tmp config
   copies is clean (byte-identical) — and `git status --short config/`
   shows nothing (live configs untouched).

Run the full suite last: `pytest -q` must stay fully green (currently 260).
  </action>
  <verify>
pytest tests/test_dashboard.py -q && \
pytest -q && \
git status --short config/     # empty: live configs untouched by tests
  </verify>
  <done>All tests pass (new + full 260+ suite); the write path is proven to
delegate to tune_risk.set_risk unchanged; preview/apply/restart semantics
covered; live configs never written.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <what-built>
    The complete local web dashboard: scripts/dashboard.py (127.0.0.1-only
    server + JSON API), scripts/dashboard.html (three-tab UI), and
    tests/test_dashboard.py green. This also closes the pending monitor
    human-verify from quick task 001 by cross-checking the dashboard's live
    numbers against monitor_trade.py.
  </what-built>
  <how-to-verify>
1. Start it: `python3 scripts/dashboard.py` (binds 127.0.0.1:8765 only).
   Open http://127.0.0.1:8765 in a browser.
2. STATUS cross-check (this is the folded 001 monitor verification): run
   `python3 scripts/monitor_trade.py --tag cent` in a terminal. The
   dashboard Status tab must show the same picture for the same moment:
   bot/supervisor pid, last decision age (within ~1 min), terminal
   connected + algorithmic trading allowed, and — if a position is open —
   entry / SL / TP / bid / ask / floating USC / current R matching the
   monitor's line. If a weekend/market-closed error banner appears instead
   of broker data, confirm the file-based bot sections still render.
3. ACCOUNT tab: balance/equity/floating match the monitor's ACCOUNT line,
   and recent closes match `tail -5 output/closes.log` for the same symbol.
4. RISK tab: shows cent cap 20.0 / slots 1 / rr 2.0 and btc cap 0.5 /
   slots 2 / rr 1.0, with the account-wide total 21.0% (20x1 + 0.5x2) vs
   the 2% standing policy — the current live state, honestly.
5. Write-path gate, ZERO-risk proof: on the Risk tab pick cent, change an
   input to the SAME current value (e.g. type 2.0 into rr_multiple) and
   click Preview — the diff must show no change, warnings empty. Then
   change rr_multiple to 2.0 on the btc tab (btc is STOPPED — no live
   risk): Preview must show the AGGRESSIVE rr banner verbatim, the diff,
   total before->after (21.0% -> 22.0%), and requires_yes. Then click
   Confirm & Apply with the restart checkbox UNCHECKED (btc's agent was
   deliberately booted out — do not let the dashboard re-bootstrap the
   stopped BTC bot): the <pre> output must be identical to what
   `python3 scripts/tune_risk.py --tag btc --set strategy.rr_multiple=2.0 --yes --no-restart` prints, including "wrote". Restore btc's rr_multiple
   back to 1.0 via the same path (or the CLI) afterwards.
6. Security check: `lsof -iTCP:8765 -sTCP:LISTEN` shows the dashboard bound
   to 127.0.0.1 (never *:8765), and the bridge on 8001 remains untouched.
  </how-to-verify>
  <resume-signal>Type "approved" or describe what failed.</resume-signal>
</task>

</tasks>

<verification>
- The dashboard binds the literal host 127.0.0.1 with no --host option; a
  lsof check confirms loopback-only listening.
- Every GET endpoint is read-only (git status on config/ empty after all of
  them); the ONLY write path is POST /api/risk/apply, which calls
  tune_risk.set_risk() unchanged (yes=True = the browser confirm).
- Preview reuses tune_risk's own validation/warning functions so the inline
  warnings are byte-identical to the CLI's.
- Broker access mirrors monitor_trade.py (native -> bridge fallback), and a
  dead bridge degrades to an error banner while file-based bot sections
  still render.
- pytest -q fully green; live configs never written by tests.
</verification>

<success_criteria>
- `python3 scripts/dashboard.py` serves a three-tab dashboard on
  127.0.0.1:8765 with zero new dependencies.
- Status/Account tabs reproduce monitor_trade.py's numbers (verified by the
  human cross-check), and the Risk tab shows the live settings plus the
  account-wide total honestly.
- A risk edit cannot be written without previewing the exact CLI warnings
  and explicitly confirming; the write and any launchd restart run through
  tune_risk.py's unchanged code path.
</success_criteria>

<output>
After completion, create `.planning/quick/005-web-dashboard/005-SUMMARY.md`
</output>
