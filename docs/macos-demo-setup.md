# Running the bot against an MT5 demo account from macOS

The `MetaTrader5` pip package is Windows-only — there is no macOS wheel for
Intel or Apple Silicon (`pip index versions MetaTrader5` returns nothing on a
Mac). The terminal therefore runs inside a Linux/amd64 container under Wine,
and the bot reaches it over RPC through
[`siliconmetatrader5`](https://github.com/bahadirumutiscimen/silicon-metatrader5).

The bot itself keeps running natively on macOS. Only the transport changes:
`[live] bridge = "silicon"` makes `MT5Broker` talk to the container instead of
importing the Windows package.

```
macOS (native python)                    container (linux/amd64 + Wine)
┌────────────────────────┐  RPC :8001   ┌───────────────────────────────┐
│ trading_bot.cli live   │ ───────────► │ MT5 terminal (Wine) + bridge  │
│   MT5Broker            │              │ Xvfb + x11vnc + noVNC :6081   │
│   bridge = "silicon"   │              └───────────────────────────────┘
└────────────────────────┘
```

## Prerequisites

Colima with QEMU **x86_64** emulation. Docker Desktop's own VM is not used —
the container is amd64 and needs QEMU, not Rosetta.

```bash
brew install colima docker qemu lima lima-additional-guestagents
```

Quit Docker Desktop first if it is running: it holds its own VM, and two VMs
plus a Wine desktop will not fit comfortably in 16 GB.

## 1. Start the x86_64 VM

```bash
colima start --arch x86_64 --vm-type=qemu --cpu 4 --memory 8
docker context use colima
```

`colima delete -f` resets a broken state.

## 2. Build and run the MT5 container

```bash
cd ~/projects/silicon-metatrader5/docker
docker compose up --build          # foreground on first run, so you see the logs
```

First build takes 5–10 minutes. The MT5 installer then runs inside Wine on
first boot, which can take a further 25–30 minutes before the UI appears.
Once stable, `docker compose up -d` backgrounds it. The Wine prefix lives in a
named volume, so a restart does not reinstall MT5.

## 3. Log into the demo account

Open <http://localhost:6081/vnc.html>, then in MT5:
**File → Login to Trade Account**, enter the broker server, login, and password.

Add `XAUUSD` to MarketWatch (the bot calls `symbol_select` too, but doing it by
hand confirms the broker actually offers that exact symbol name — some brokers
use `XAUUSD.m`, `GOLD`, etc., in which case set `[data] symbol` to match).

Wait 5–10 minutes after login: historical bars sync in the background, and the
engine needs `sr_lookback + fractal_left + fractal_right + 5` = 69 closed M5
bars before it can evaluate a setup.

## 4. Point the bot at the bridge

```toml
[live]
enabled = false      # keep false — SAFE-03 blocks REAL accounts while it is
mode = "demo"
bridge = "silicon"
bridge_host = "localhost"
bridge_port = 8001
```

```bash
python -m trading_bot.cli live --once --mode demo   # single poll
python -m trading_bot.cli live --mode demo          # poll loop
```

Every decision is appended to `output/live.log`.

## Safety

`enabled = false` with `mode = "demo"` is the safe combination and blocks a
REAL account two ways (`live/safety.py`):

- a REAL account (`trade_mode=2`) is refused unless `enabled = true`
- `mode = "demo"` refuses a REAL account regardless

A blocked setup logs `order_skipped reason=safety_blocked` and places nothing.

Do not run `mode = "live"` through this bridge. Emulated x86 under QEMU plus an
RPC hop adds latency the strategy was never measured against; the upstream
project says the same. Real money belongs on native Windows.

## Offline smoke test (no container needed)

`dry-run` replays the historical CSVs through the live engine, one bar per
poll, and places nothing:

```bash
python -m trading_bot.cli live --once --mode dry-run   # -> bar_check new_bar=True
python -m trading_bot.cli live --mode dry-run          # replays [live] replay_bars
```

`order_plan` lines record exactly what would have been sent; the paired
`order_placed` line carries `placed=False ticket=0`.

## Running it

`scripts/run_demo.sh start|stop|status|check` starts the bot detached (PPID 1,
so it survives the shell that launched it), after running the preflight and the
container checks below.

### Surviving reboots (optional)

`scripts/run_demo.sh start` detaches the bot but does not survive a reboot and
nothing restarts it if it dies. For that, install the launchd agent — it is a
plain plist pointing at `scripts/launchd_run.sh`, which brings the stack up in
dependency order (colima VM -> container -> openbox -> preflight retry) and
then execs the bot in the FOREGROUND so launchd owns the lifecycle.

```bash
cp scripts/com.joram.trading-bot-demo.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.joram.trading-bot-demo.plist
launchctl print gui/$(id -u)/com.joram.trading-bot-demo   # verify
```

Stop `scripts/run_demo.sh` first — two bots against one account is not what the
dedup logic is for.

To remove:

```bash
launchctl bootout gui/$(id -u)/com.joram.trading-bot-demo
rm ~/Library/LaunchAgents/com.joram.trading-bot-demo.plist
```

It starts a 6 GB QEMU VM at login. If that is unwelcome, do not install it and
run `scripts/run_demo.sh start` by hand instead.

## Upstream image bugs (patched locally)

Three defects in `silicon-metatrader5` cost real debugging time. All three are
patched in the local clone at `~/projects/silicon-metatrader5`, so a
`docker compose up --build` keeps the fixes — but they are NOT upstream.

**1. No window manager.** `start.sh` shipped `# openbox &` commented out. Without
a WM, X has no input focus: keystrokes reach nothing, so noVNC typing silently
fails and `xdotool` reports `XGetInputFocus returned the focused window of 1`.
This is almost certainly the "black VNC screen" in the upstream README's
troubleshooting section. Now uncommented.

**2. Algo trading never enabled.** `mt5cfg.ini` used a `[Expert]` section with
`AllowAlgoTrading` / `EnableAlgoTrading` — none of which are real MetaTrader
keys. The terminal ignored the block, so AutoTrading stayed OFF and
`order_send` was rejected until someone clicked the toolbar button by hand.
The failure is nasty because the bot looks healthy: setups are detected and
logged, orders just never place. Corrected to MT5's real `[Experts]` section
with `Enabled=1` / `AllowLiveTrading=1`.

**3. Nondeterministic terminal choice.** `start.sh` located the terminal with a
bare `find ... -print -quit`. With two installs present (a broker-branded one
alongside the stock one), it returns whichever the traversal hits first, so the
terminal holding your logged-in account may not be the one running — and the
Python bridge attaches to the wrong one. Pinned via `MT5_TERMINAL_DIR` in
`compose.yaml`.

## Broker vs vendor symbol names

Exness quotes gold as `XAUUSDm` on a Standard account, not `XAUUSD`. `[data]
symbol` names the histdata CSVs, so it cannot just be changed — set `[live]
symbol` instead. It applies to demo/live only; dry-run keeps the vendor name
because it replays the vendor's CSVs.

## Finding your server

Exness shows customers a short server name (`Exness-MT5Trial9`) while the
MetaQuotes broker directory lists servers under legal-entity prefixes
(`ExnessSC-MT5Trial9`). These are DIFFERENT servers and logging into the wrong
one fails with a bare `Invalid account`. The unprefixed servers belong to
**Exness Technologies Ltd** (identifier `Exness`). That entity's entry in the
Open-an-Account wizard would not advance past Next, so the working route was
installing Exness's own branded terminal, which ships their server list:

```bash
curl -L -o exness5setup.exe \
  https://download.mql5.com/cdn/web/exness.technologies.ltd/mt5/exness5setup.exe
wine exness5setup.exe /auto
```

## Troubleshooting

| Symptom | Cause |
|---|---|
| `could not reach the MT5 bridge at localhost:8001` | container not running, or `docker context` still on `desktop-linux` |
| `siliconmetatrader5 is not installed` | `pip install siliconmetatrader5` in the project venv |
| Black VNC screen | Colima not in QEMU x86_64 mode — check `colima status` |
| `bar_fetch_failed` right after login | bars still syncing; wait 5–10 min |
| `symbol_select(XAUUSD) failed` | broker names gold differently — set `[data] symbol` |
