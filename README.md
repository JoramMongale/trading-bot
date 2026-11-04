# trading-bot

A Python bot for a breakout setup on 5-minute candles (gold, bitcoin, and
EUR/JPY in progress): find support/resistance from confirmed swing points,
wait for a close through a level, then enter at market with a structural stop
and a fixed reward:risk target.

It trades **both directions**. A close above resistance is a buy; the mirror
image, a close below support, is a sell. Which side is allowed at any moment
can be set by a **sentiment** reading — the US dollar for gold, the Crypto
Fear & Greed index for bitcoin, the VIX for yen crosses. See
[Sentiment: which side to trade](#sentiment-which-side-to-trade).

Backtester and live bot run the **same** strategy code, so what is tested is
what trades.

---

## Platform support

| | backtest | live trading | notes |
|---|---|---|---|
| **Windows** | yes | **yes, natively** | the reference platform — MetaTrader 5 and its Python API are Windows software |
| **macOS** | yes | via Docker bridge | no MetaTrader5 wheel exists; the terminal runs in a linux/amd64 Wine container reached over RPC |
| **Linux** | yes | via Docker bridge | same as macOS — the pip package is Windows-only |

Verified: `pip download MetaTrader5` on macOS returns *No matching distribution
found*. There is no Linux or macOS build of the API.

**If you only want to research the strategy, every platform works the same.**
The backtest has no MetaTrader dependency at all. The split only matters for
placing live orders.

---

## Setup

### Windows

```bat
scripts\setup.bat
```

Creates `.venv`, installs the project plus `MetaTrader5`, and runs the tests.
Needs Python 3.11+ from python.org (tick **Add Python to PATH**) and the
MetaTrader 5 terminal installed and logged in.

### macOS / Linux

```bash
./scripts/setup.sh              # backtest only
./scripts/setup.sh --live       # also install the MT5 bridge client
```

Creates `.venv`, installs the project, and runs the tests. `--live`
additionally installs `siliconmetatrader5`; you also need Docker and the
containerised MT5 terminal — see `docs/macos-demo-setup.md`.

---

### Moving it to the Windows machine

Windows is where live trading is native, so the usual flow is: research on
macOS/Linux, trade on Windows.

**The normal route is git.** GitHub (`JoramMongale/trading-bot`) is the main
copy. Commit and push from the dev machine, then on Windows:

```bat
scripts\restart_bots.bat stop
git pull
scripts\restart_bots.bat start
```

Always stop **before** pulling: cmd re-reads a batch file while it runs, so a
pull that rewrites `supervise_live.bat` under a running supervisor is undefined
behaviour.

`restart_bots.bat` must be run as administrator — see
[Restarting the bots on Windows](#restarting-the-bots-on-windows).

**Without git**, build a transfer zip from the dev machine:

```bash
./scripts/make_windows_zip.sh
```

It writes `dist/trading-bot-windows-<sha>.zip` using `git archive`, so the
archive holds exactly the tracked files at one commit — no `.venv`, no
`output/`, no local clutter, by construction rather than by an exclusion list.
A `VERSION.txt` with the commit id travels inside it.

It **refuses to package a dirty tree**, including untracked files. Commit first
— otherwise the commit id in `VERSION.txt` would be a lie about what's in the
zip.

On the Windows side: unzip, `cd trading-bot`, `scripts\setup.bat`.

`data/raw/*.csv` is gitignored and therefore **not** in the zip. Download the
histdata M1 CSVs on that machine if you want to backtest there.

---

## Configuration

Everything lives in `config/config.toml`.

| file | account | instrument |
|---|---|---|
| `config/config.toml` | standard | gold |
| `config/config-cent.toml` | **cent (USC)** | gold, `XAUUSDc` |
| `config/config-btc.toml` | **cent (USC)** | bitcoin, `BTCUSDc` — trades 24/7 |
| `config/config-eurjpy.toml` | **cent (USC)** | EUR/JPY, `EURJPYc` — dry-run, not live yet |

Select one with `--config`. **If your balance is small, you probably need a cent
account** — the stop in this strategy is structural, so on a standard account
the broker's 0.01-lot minimum in gold can risk over 100% of a small balance and
the bot will correctly refuse every setup. See
[`docs/cent-account-setup.md`](docs/cent-account-setup.md) for how to open one,
the symbol-suffix trap, and why sizing must read `trade_tick_value` and never
`contract_size`.

```toml
[data]      symbol, timeframe, where the CSVs are
[strategy]  swing/level parameters
[trading]   lot size and contract size
[live]      mode, magic number, how to reach the terminal
[risk]      the money controls — read this table before trading
[ai]        optional AI advisor layer (mock by default, off until enabled)
[sentiment] which side to trade (long / short) from a sentiment reading
```

**On Windows set `bridge = "native"`** (or leave `"auto"`, which tries native
first). The `bridge_host`/`bridge_port` settings are only for the macOS/Linux
container route.

### Robustness keys (`[live]`, Phase 3)

| key | what it does |
|---|---|
| `weekend_stop_hour` | UTC hour of Friday after which NEW entries are refused (0 = off). Self-imposed backstop behind the scheduled Friday stop — still holds if that task is late. Gold config sets 19. |
| `weekend_resume_hour` | UTC hour of Sunday at which entries resume (default 21 = gold reopen). BTC leaves the guard off entirely. |
| `reconnect_after` | consecutive failed polls (`bar_fetch_failed`) before the connection is torn down and re-established (default 3, 0 = off). |
| `reconnect_backoff` | seconds slept between failed reconnect attempts so a long outage does not hammer the terminal (default 30). |

A disconnect is now a self-healing state: the loop logs `reconnect_attempt` /
`reconnected` / `reconnect_failed` and keeps polling. Market closures (empty
frames) are deliberately NOT failures, so they never churn reconnects.

### The risk table

| key | what it does |
|---|---|
| `max_loss_pct_per_trade` | hard ceiling on what one trade may cost, as % of balance |
| `sizing` | `"fixed"` uses `[trading] lot`; `"percent"` sizes so the stop costs exactly the cap |
| `max_daily_loss_pct` | stop trading for the day once realised losses reach this (0 disables) |
| `max_leverage` | ceiling on notional exposure — bounds gap risk, which a stop cannot |
| `min_rr` | refuse a setup whose reward:risk has already decayed below this |
| `lot_min`, `lot_step` | the broker's lot grid; sizing floors onto it, never up |

Sizing returns *nothing* rather than rounding up when the answer falls below
`lot_min`. On a small account that means it declines to trade, which is the
honest outcome: the stop distance is set by the market, so the smallest
tradable position can still risk more than the policy allows.

### Sentiment: which side to trade

`[strategy] direction` is the default side: `"long"` or `"both"`. With
`[sentiment] enabled = true`, the bot reads a daily sentiment number once an
hour, puts it on a 0-100 scale (above 50 = bullish for this symbol), and
overrides the side when the reading is clear:

| reading | side traded |
|---|---|
| 60 or more (`50 + band`) | **long only** |
| 40 or less (`50 - band`) | **short only** |
| in between | `[strategy] direction` |
| data unavailable or too old | `[strategy] direction` |

| `source` | used for | bullish when | data |
|---|---|---|---|
| `dxy` | gold | the US dollar is below its 200-day average | Yahoo `DX-Y.NYB`, daily |
| `fng` | bitcoin | the Crypto Fear & Greed index shows greed | alternative.me, daily |
| `vix` | yen crosses (EUR/JPY) | VIX is below its 50-day average (calm, risk-on) | Yahoo `^VIX`, daily |

**Veto mode (gold).** With `mode = "veto_longs"` the reading never picks a
side; `[strategy] direction` applies, but long setups are skipped while the
macro is against gold: the dollar (DXY) strong vs its 200-day average **and**
the US 10-year yield above its 200-day average. Logged as `event=macro_veto`
and `setup_skipped reason=macro_headwind_long`.

Current state:

| bot | side | sentiment |
|---|---|---|
| gold (`config-cent.toml`) | longs only | `dxy`, `veto_longs` |
| bitcoin (`config-btc.toml`) | sentiment picks, default long | `fng`, `direction` |
| EUR/JPY (`config-eurjpy.toml`) | — | `vix`, off |

Keep in mind:

- The gold veto is the one filter that improved the long side in the backtest,
  but it passed a weaker test only (no out-of-sample check).
- Neither the DXY nor the Fear & Greed direction filter passed its backtest bar (see
  `.planning/quick/20260928-*`). Running them on the real accounts is a live
  experiment. The VIX source has not been backtested at all.
- Only **completed** days count: today's unfinished value is ignored, the same
  as in the backtests.
- The data is saved under `data/processed/` and re-downloaded once it is older
  than `cache_max_age_hours` (12). If a download fails, the saved copy is used.
  If the newest day is older than `max_stale_days`, the bot ignores the reading.
- Every reading is logged: `event=sentiment_direction` (value, day, side) or
  `event=sentiment_unavailable` (why). Check with
  `findstr sentiment_ output\live_cent.log` on Windows or
  `grep sentiment_ output/live_cent.log` elsewhere.
- To turn it off, set `enabled = false` and restart that bot.

```toml
[sentiment]
enabled = true
source = "dxy"               # dxy | fng | vix
band = 10.0                  # neutral zone either side of 50
window = 200                 # moving-average days (dxy, vix)
refresh_seconds = 3600.0     # re-read at most once an hour
cache_max_age_hours = 12.0   # re-download the data once the saved copy is older
max_stale_days = 5.0         # newest day older than this -> ignore the reading
```

---

## Running

```bash
# backtest over historical CSVs — no MetaTrader needed anywhere
python -m trading_bot.cli backtest

# one poll against replayed history, places nothing
python -m trading_bot.cli live --mode dry-run --once

# demo account
python -m trading_bot.cli live --mode demo
```

Windows uses `.venv\Scripts\python`; macOS/Linux `.venv/bin/python`.

Useful flags: `--config PATH` to run a different configuration, `--log NAME` to
write a separate decision log. Two bots on one account **must** differ in both,
and in `[live] magic_number` — the duplicate guards filter by magic, so sharing
one makes each bot mistake the other's position for its own.

Every decision is written to `output/<log>` as a structured line:
`setup_detected`, `order_placed`, `order_skipped` with a reason, `order_rejected`.

### AI layer + analytics warehouse (Phase 4)

The AI layer is a DeepSeek advisor in front of the deterministic gate — the
model reasons, deterministic code disposes. Offline-first: `provider = "mock"`
needs no key and no network.

```bash
# AI-gated backtest over history (raw vs gated stats, offline with mock)
python -m trading_bot.cli ai-backtest --config config/config-ai.toml

# one live dry-run poll with the AI layer on (mock, offline)
python -m trading_bot.cli live --config config/config-ai-live.toml --mode dry-run --once

# same, but consult the real DeepSeek model (requires DEEPSEEK_API_KEY in the env)
python -m trading_bot.cli live --config config/config-ai-live.toml --mode dry-run --once --provider deepseek
```

`config/config-ai-live.toml` is the paper-trading AI config: `[ai] enabled`,
`provider = "mock"` by default, `[live] mode = "demo"`, SAFE-03 intact
(`[live] enabled` stays false until real-account execution is a deliberate,
separate decision). `--provider {mock,deepseek}` overrides per run without
editing the file.

**Analytics warehouse** (DuckDB + dbt) turns every bot artifact — trades,
decision logs, closes, AI calls, bars — into one local database:

```bash
# duckdb + dbt are optional dev extras, never base-bot dependencies
.venv\Scripts\pip install -e ".[analytics]"        # duckdb (loader)
.venv\Scripts\pip install "dbt-core>=1.8" "dbt-duckdb>=1.8"   # dbt (dev tool)

# ingest output/ + data/processed/ into data/analytics/trading.duckdb (idempotent)
python scripts/warehouse_cli.py load

# build the queryable marts (run from the dbt/ directory)
cd dbt && dbt run && dbt test
```

Every AI call is audited to `output/ai_calls_<log>.jsonl` (SAFE-02 for the AI
half); the warehouse ingests it into `raw_ai_calls` and the marts expose the
gate activity/performance for the dashboard.

### Dashboard (plan 03-05)

The **primary monitoring surface** is a read-only Next.js + Tailwind dashboard
rendering the DuckDB marts (status, ledger, AI-gate activity, risk, news
sentiment) — loopback-bound, GET-only, zero write path:

```bash
python scripts/warehouse_cli.py load        # load the warehouse first
(cd dbt && dbt run && dbt test)
scripts/web_dashboard.sh start              # or scripts\web_dashboard.ps1 start
# open http://127.0.0.1:3000
scripts/web_dashboard.sh stop
```

The stdlib fallback `scripts/dashboard.py` (quick task 005) remains available
for a no-dependency status view. See `web/README.md` for details.

### Account check

`[live] expected_login` is the account number a bot must be logged in to.
With it set, the bot (and its startup check) refuses to run when its terminal
is logged in to any other account — `terminal_path` alone proves which
install, not which account. Gold is pinned to 161693049, BTC to 161700182.

### Alerts and reboots (Windows)

`scripts\watchdog.py` sends Telegram alerts every 5 minutes: bot down, startup
check failing (with the reason), frozen bot, trades opened/closed, sentiment
changes, plus a daily summary. A reboot brings the terminals and bots back on
their own once auto-logon is set. Setup for both:
[`docs/windows-deployment.md`](docs/windows-deployment.md) sections 8 and 9.

### Restarting the bots on Windows

After a config change, or a code update (stop → `git pull` → start), the bots
need restarting to load it.
Right-click `scripts\restart_bots.bat` → **Run as administrator**, or from an
administrator Command Prompt:

```bat
scripts\restart_bots.bat              :: restart cent and btc
scripts\restart_bots.bat cent         :: restart just one
scripts\restart_bots.bat stop         :: stop cent and btc
scripts\restart_bots.bat start        :: start cent and btc
```

To update code: `stop`, then `git pull`, then `start`. A plain restart is
enough for a config change.

For each bot it stops it cleanly (writes `output\live_<tag>.stop` so the
supervisor exits, then kills the bot process), waits for the
`trading-bot-<tag>` task to finish, starts the task again, waits for the bot
to really start, and shows its first sentiment reading. If the startup check
keeps failing it reports **NOT STARTED** with the reason. It never starts a second copy: a bot that will
not stop is left alone and reported as FAILED. Open trades are safe while the
bot is down, because their stop loss and take profit are held by the broker.

It needs administrator rights because the tasks run with highest privileges,
so a normal prompt gets *Access is denied* when stopping the bot.

The tasks themselves are installed once with `scripts\install_windows_tasks.bat`
— see [`docs/windows-deployment.md`](docs/windows-deployment.md).

### Starting and stopping a live bot

**In the foreground** — you watch it, `Ctrl-C` stops it. Start here the first
time you run any new configuration.

```bash
.venv/bin/python -m trading_bot.cli live \
    --mode live --config config/config-cent.toml --log live_cent.log
```

**Detached**, surviving the terminal closing, with a pidfile to stop it by:

```bash
.venv/bin/python -c '
import os, sys
os.setsid()
os.execv(sys.executable, [sys.executable, "-m", "trading_bot.cli", "live",
                          "--mode", "live",
                          "--config", "config/config-cent.toml",
                          "--log", "live_cent.log"])
' >> output/live_cent.out 2>&1 < /dev/null &
echo $! > output/live_cent.pid
```

`os.setsid()` is what makes it a real detachment — a plain `&` leaves the bot in
the terminal's process group, so closing the window can take it down with you.

**Stop it:**

```bash
kill $(cat output/live_cent.pid)
```

**Is it alive, and what is it doing?**

```bash
ps -p $(cat output/live_cent.pid)       # alive?
tail -f output/live_cent.log            # decisions
cat output/live_cent.out                # crashes, scheduled-stop notices
```

A healthy M5 log shows one `bar_check` every five minutes. Long runs of
`setup=False` are normal — and while a position is open they are *expected*,
because the one-position-at-a-time guard suppresses new entries until it
resolves. Quiet is not broken.

**Stopping at a set time**, independent of any terminal or session:

```bash
./scripts/schedule_weekend.sh           # the full Friday-evening sequence
pkill -f wait_until                     # cancel every pending timer
```

Timers poll the wall clock rather than issuing one long `sleep`: a single long
sleep overruns by however long the machine was asleep. For an overnight run also
hold the machine awake, or the bot dies with the lid:

```bash
caffeinate -dimsu &                     # macOS
```

**On Windows:** substitute `.venv\Scripts\python` and use `Ctrl-C` to stop a
foreground bot, or `taskkill /PID <pid> /F` for a detached one. The `setsid`
and `caffeinate` parts are POSIX-only; on Windows use Task Scheduler if you
need an unattended start or stop.

> **Do not launch a REAL account with `run_demo.sh`.** It calls
> `preflight_demo.py`, which refuses real accounts *by design* — that guard is
> deliberate and should stay. Launch directly, as above, after running the
> equivalent checks read-only: bridge reachable, `trade_allowed=True`, bars
> arriving, feed fresh, sizing computed across every stop percentile.

For unattended real-money runs use the supervisors, not a bare auto-restart:
`scripts/supervise_live.sh` (macOS) or `scripts\supervise_live.bat` via Task
Scheduler (Windows). Both run preflight before every start and stop for good
after 5 failures in 15 minutes, because an unsupervised auto-restart is how one
bad configuration becomes many bad trades. The position's stop and target live
with the broker, so it stays protected while the bot is down.

### Is it OK?

```bash
python scripts/health_check.py          # full report
python scripts/health_check.py --quiet  # only problems
```

Exit `0` healthy, `1` warnings, `2` problems — so it also works in a cron job.

Tailing a log only tells you a process is alive. This checks the things that
cost money and are invisible in a log tail:

| check | the failure it catches |
|---|---|
| **poll loop age** | a bot that is alive but has stopped polling |
| **stop loss present** | a position with unbounded downside |
| **slot budget** | more positions open than `max_concurrent` — a guard failed |
| **account-wide risk** | exposure summed across bots, against the policy |
| **reconciliation** | balance ≠ deposits + trading P&L |
| **crash history** | repeated deaths, or a supervisor that gave up |
| **trade_allowed** | algo trading switched off — every order will be rejected |

The most important of those is the poll-loop age. A *crashed* bot is safe: the
supervisor restarts it, and stops and targets sit with the broker regardless. A
bot that is alive but no longer polling is worse — nothing has died, so nothing
restarts it, and it quietly stops noticing the market.

### Seeing the exits

The bot logs `order_placed` when it OPENS a trade. It never logs the close, and
cannot: a take-profit or stop-loss fires inside the broker and the bot is not
told. Anything tailing the decision log therefore sees every entry and no exits
— the wrong half, since the exit is where the money is decided.

```bash
python scripts/watch_closes.py            # follow, polling every 30s
python scripts/watch_closes.py --once     # backfill and exit
```

It polls the deal history and appends one `event=trade_closed` line per newly
closed position to `output/closes.log`, in the same key=value shape the bot
uses, with `how=tp|sl|other` and the R multiple. Tail that file alongside the
decision log and you see both ends of every trade.

On first run it backfills silently — existing closes are marked seen without
being emitted, so starting the watcher never replays history as fresh alerts.

### Is it actually making money?

Balance cannot answer that while you are funding the account. Deposit weekly into
a system that loses slowly and the balance still climbs.

```bash
python scripts/account_report.py --since 2026-08-01
```

It reconciles the account into its two independent parts —
`balance = deposits − withdrawals + trading P&L` — and reports the trading half
on its own, in account currency, in ZAR, and in **R multiples**.

R is the number that matters, and MT5's deal history cannot produce it: the
history records what was paid and received, never the stop that defined the
risk. So stops are recovered from the bot's own decision logs (`order_placed`
lines carry `sl`/`tp`) and matched to deals by ticket. A trade whose log line is
missing shows `R = ?` rather than a guess.

Below 30 trades it says so explicitly. Per-trade noise is ~0.9R, so even a real
edge of +0.04R needs roughly 2,000 trades before it separates from zero.

### The full trade ledger (backtest + live in one view)

```bash
python scripts/trade_ledger.py              # writes output/ledger.csv + summary
python scripts/trade_ledger.py --once       # print only
python scripts/trade_ledger.py --json       # also dump a JSON summary
```

Read-only, stdlib-only, never touches the broker. Merges the backtest's
`output/trades.csv` with the live/demo `order_placed` lines from the decision
logs and the `trade_closed` lines from `watch_closes.py` (joined by ticket to
attach exit price, reason and R). A live entry with no close yet is reported as
open. This is the single "review a full ledger covering backtest and live/demo
runs" command — the decision logs show every entry, `watch_closes.py` adds the
exits, and the ledger joins them.

### Monitoring the live trade

One command answers the three questions in a single glance: is the bot alive and
still polling, is there an open position, and what is the P&L.

```bash
python scripts/monitor_trade.py            # one-glance snapshot
python scripts/monitor_trade.py --quiet    # only problems
python scripts/monitor_trade.py --tag cent # another bot
```

It shows the bot's own status (pid, supervisor, freshness of the last decision
log line, terminal connection and algorithmic-trading permission), the open
position for **this** bot's magic number — entry, SL, TP, current bid/ask,
floating P&L, current R, distance to SL and TP, time open — and realised P&L
from `output/closes.log` for the broker's symbol plus account balance/equity.
A position with no stop loss is reported as a failure, not a warning: that is
the one state that can take the account while nothing restarts anything.

It is **READ-ONLY**: it never places, closes, or modifies an order — closing
stays the deliberate human action documented in the next subsection.

Exit codes 0/1/2 match `health_check.py`, so it is safe to run from the same
cron job: 0 healthy, 1 warnings (e.g. bot down while its supervisor backs off),
2 problems (stale poll loop, broker unreachable, unbounded position). It shows
only this bot's positions — account-wide risk across several bots remains
`health_check.py`'s job.

### Closing a position

The engine has **no close path** — it only places. Stops and targets live with
the broker, so a position is protected whether or not a bot is running, but
nothing will flatten it early on its own. Closing is a deliberate human action:

```bash
python scripts/close_position.py --ticket 433789109 --dry-run   # preview
python scripts/close_position.py --ticket 433789109 --confirm   # send it
```

It refuses to guess: an explicit ticket, `--confirm` required to send anything,
and a clean "nothing to close" exit if SL or TP already took the position. It
picks its transport the same way the adapter does, so it runs unchanged on
Windows (native) and macOS/Linux (bridge).

This matters most before a weekend. Gold is shut from Friday 21:00 to Sunday
21:00 UTC, and a broker-side stop cannot protect against a Sunday opening gap
that jumps straight through it.

---

## Safety

Live trading on a **real** account requires `[live] enabled = true` *and*
`mode = "live"`. A real account is refused otherwise, in code, before the order
is built. Keep `mode = "demo"` until you have watched it place and close trades
you are happy with.

`--mode dry-run` is enforced by a wrapper that has no reference to the inner
broker at all, so it cannot send an order even by mistake.

**The macOS/Linux bridge has no authentication** — no token, no password, no
TLS — and it listens on all interfaces. Anyone who can reach the port can trade
the account. Bind it to `127.0.0.1` and tunnel over SSH. This does not apply to
Windows, which talks to the terminal directly.

---

## Layout

```
src/trading_bot/
  strategy/     swings, levels, signals — pure functions, no I/O
  backtest/     event loop and statistics
  live/         poll loop, risk gate, safety guard
  broker/       BrokerClient contract + MT5, simulated and dry-run adapters
tests/          201 tests, no network or terminal required
scripts/        setup, preflight, history download, supervision, packaging
docs/           platform setup guides
```

Run the suite any time with `.venv/bin/pytest` (or `.venv\Scripts\pytest`).
