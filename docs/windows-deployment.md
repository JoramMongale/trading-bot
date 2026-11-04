# Windows deployment — three bots, three accounts, one NUC

Windows is the platform this bot was designed for. MetaTrader 5 and its Python
API are Windows software, so the whole macOS apparatus — Docker, colima, Wine,
the `siliconmetatrader5` RPC bridge, noVNC — simply does not exist here. The bot
talks to the terminal directly.

That removes most of the operational failure modes documented in `STATE.md`. It
introduces exactly one new one, and it is the dangerous kind: **quiet**.

## The one thing that will bite you

On macOS each account lives in its own container, and `bridge_port` names
exactly one terminal holding exactly one account. On Windows there is no such
separator. Three terminal installs on one machine are three terminals visible to
the same pip package, and an argument-less `mt5.initialize()` attaches to
whichever it finds first.

Nothing announces this. The gold bot would place gold's orders, sized off gold's
risk percentage, against the bitcoin account's balance, and every log line would
read as healthy.

So each config must name its own terminal:

```toml
[live]
bridge = "native"
terminal_path = 'C:\MT5-Gold\terminal64.exe'
```

`broker/mt5.py` then checks `terminal_info().path` against that directory after
connecting and **refuses to trade on a mismatch** rather than proceeding. Setting
`terminal_path` is not a style preference; leaving it empty with three installs
running is an account-selection bug waiting for a restart to expose it.

## Layout

| bot | account | config | install | magic | symbol |
|---|---|---|---|---|---|
| gold | its own | `config\config-cent.toml` | `C:\MT5-Gold\` | 77020 | `XAUUSDc` |
| bitcoin | its own | `config\config-btc.toml` | `C:\MT5-BTC\` | 77021 | `BTCUSDc` |
| EUR/JPY | its own | `config\config-eurjpy.toml` | `C:\MT5-FX\` | 77022 | `EURJPYc` (unverified) |

Three separate accounts, per the isolation rationale in
`.planning/quick/007-btc-separate-account/007-PLAN.md`: risk caps apply
per-account, nothing sums across bots, and each account's base stake and banking
are tracked independently.

One consequence worth stating plainly, because `config-btc.toml`'s comments
still describe the old shared-account world: with separate accounts you no
longer need to count slots account-wide across bots. Each account carries only
its own bot.

## 0. The short version: run the bootstrap

On a brand-new machine, **right-click → Run as administrator**:

```
scripts\bootstrap_windows.bat
```

It does steps 1–3 and 5 below for you: installs Python 3.11+ 64-bit via winget,
locates or installs MetaTrader 5, creates the three portable installs with
`/portable` desktop launchers, then runs `setup.bat` for the venv, dependencies
and test suite.

It does not self-elevate — it checks for admin and tells you. Doing it
automatically in batch means shelling out to PowerShell or writing a throwaway
VBScript, and a bootstrap that silently relaunches itself in another window is
harder to trust than one that says what it needs.

Everything in the Windows deployment is batch rather than PowerShell, and that
is a deliberate reversal. The first version put the real work in PowerShell —
written on a Mac, where no PowerShell existed to run it, so its first execution
would have been on the machine holding real money. Batch is clumsier, but every
line can be reasoned about without an interpreter to test it against.

It is idempotent — re-running skips whatever is already done. That matters
because it can legitimately stop at MetaTrader and ask you to fetch the Exness
build by hand (the winget package, where it exists at all, is the generic
MetaQuotes build). Download it, run the bootstrap again, and it picks up where
it left off.

What it deliberately will **not** do: log in to an account, or enable Algo
Trading. Both need your password and your eyes on a real balance. Those are
sections 4 and 5.

The rest of this document is the manual path, and the reference for what the
bootstrap is actually doing.

## 1. Prerequisites

- **Python 3.11+, 64-bit**, from python.org, with *"Add Python to PATH"* ticked.
  32-bit Python cannot load the MetaTrader5 package. 3.11 is the floor because
  the config loader uses stdlib `tomllib`.
- The **Exness MT5 terminal** installer.
- Three funded Exness accounts. See `docs/cent-account-setup.md` for why a cent
  account is what makes gold tradeable on a small balance — the structural stop
  at the 0.01-lot broker minimum puts the floor near $1,215 on a standard
  account.

## 2. Unpack and install

Build the zip on the dev machine:

```bash
./scripts/make_windows_zip.sh
```

It refuses a dirty tree by design — the commit id it stamps into `VERSION.txt`
is meant to mean something. Copy the zip over, unzip, then:

```
cd trading-bot
scripts\setup.bat
```

That creates `.venv`, installs the project and MetaTrader5, and runs the test
suite. If the tests fail, stop there.

Note: `data\raw\*.csv` is gitignored and therefore **not** in the zip. Live
trading does not need it; backtesting does.

## 3. Three portable terminal installs

Install the terminal once to `C:\MT5-Gold`, then **copy the whole folder** twice:

```
C:\MT5-Gold\
C:\MT5-BTC\
C:\MT5-FX\
```

Launch each with the `/portable` flag:

```
C:\MT5-Gold\terminal64.exe /portable
```

Portable mode keeps each install's settings and saved account inside its own
folder instead of the shared `%APPDATA%` tree. Without it all three share one
`accounts.dat` and log each other out — which is precisely the failure that
cost a live session on the Mac when a BTC login landed in the gold container.

The bootstrap writes a `.cmd` launcher per install to the shared Desktop —
`MT5 Gold 77020.cmd` and friends — each one a two-line file that starts that
terminal with `/portable`. A `.cmd` rather than a `.lnk` because creating a real
shortcut from batch needs PowerShell or a throwaway VBScript, and this does the
same job with nothing to go wrong.

Always start terminals from those launchers. One started any other way silently
rejoins the shared `%APPDATA%` profile and the isolation is gone.

## 4. Log in and enable Algo Trading

In **each** terminal:

1. **File → Login to Trade Account** — that account's login, password, server.
2. **Tools → Options → Expert Advisors → "Allow algorithmic trading"**.

> **Algo Trading resets every time you switch accounts in a terminal.** This has
> bitten this project repeatedly. `preflight_live.py` checks
> `terminal_info().trade_allowed` and refuses to start the bot when it is false,
> so the failure is loud — but it is still your five minutes.

Watch for modal dialogs. A "Welcome to LiveUpdate" prompt or a "Select a company
to open an account with" wizard sitting on top of the terminal swallows every
keystroke, including the `Ctrl+E` Algo Trading shortcut, and the toolbar button
will not respond. Dismiss them first. Choose **Later**, never **Restart**, while
a position is open.

## 5. Configure

In each of the three configs set:

```toml
[live]
bridge = "native"                              # not "auto" — no bridge exists here
terminal_path = 'C:\MT5-Gold\terminal64.exe'   # that bot's own install
symbol = "XAUUSDc"                             # read from Market Watch, do not guess
mode = "demo"                                  # until you have watched it trade
```

Symbol suffixes are broker- and account-type specific. Read each from Market
Watch.

**EUR/JPY is not ready to trade.** `config-eurjpy.toml` ships `enabled = false`
and `mode = "dry-run"` with a checklist at the top, because three of its numbers
have never been measured on that instrument: the symbol name, the `sl_buffer`
point scaling, and the per-trade risk cap. It was picked because it ranked first
of seventeen instruments (+0.135 avg R) and was one of only two positive in both
halves of the split-sample test — but at t=1.95 its 95% CI still contains zero,
and "best of seventeen" chosen on the same data that measured it is a ranking
artefact until it survives out-of-sample. Work the checklist first.

## 6. Preflight before anything trades

```
.venv\Scripts\python scripts\preflight_live.py --config config\config-cent.toml --real-account
```

Read-only. Checks the terminal is reachable, `trade_allowed` is true, bars are
arriving and fresh, and sizing is affordable — and now also that it attached to
the install you named. Run it once per config.

## 7. Install the scheduled tasks

```
scripts\install_windows_tasks.bat
```

Registers one task per bot via `schtasks`, each running
`scripts\supervise_live.bat` — the port of the macOS supervisor, with the same
preflight-before-every-start, the same exponential backoff, and the same
crash-loop brake (5 failures in 900s and it stops and stays stopped).

`/remove` unregisters them; `/only cent` acts on one.

**Tasks run at LOGON, not at boot**, and that is deliberate. The MetaTrader5
package talks to a terminal in an interactive desktop session; a Windows service
runs in session 0 with no desktop and would find no terminal to attach to.

So the NUC must be set to **auto-logon** to the trading user. The supervisor
disables sleep and hibernate on AC power itself (`powercfg /change
standby-timeout-ac 0`), which is the machine-level stand-in for `caffeinate -w`
on the Mac — coarser, because batch cannot scope that assertion to a process.
Undo with `powercfg /change standby-timeout-ac 30`.

Task Scheduler's own restart-on-failure is deliberately not configured. It would
be the wrong layer: the supervisor knows the difference between "died once" and
"cannot start cleanly", and an outer restarter would defeat the crash-loop brake
by relaunching the supervisor every time it correctly gave up.

## 8. Phone alerts (watchdog + ntfy)

`scripts\watchdog.py` runs every 5 minutes (task `trading-bot-watchdog`) and
pushes to your phone when:

- a bot task is not running, or its startup check is failing (with the reason)
- the crash-loop brake gave up, or a bot died
- no candle check for too long while the market is open (frozen terminal)
- a trade opened, was rejected, or closed (with profit), or the daily loss
  limit hit
- the sentiment side or the gold veto changed, or its data is unavailable

Problems arrive as high-priority notifications, repeat hourly while they last,
and a "back to normal" message follows. A daily summary arrives after 06:00
UTC. It never places or changes anything.

Setup, once (ntfy is free, no account):

1. Install **ntfy** on your phone (App Store / Google Play).
2. On the bot machine: `.venv\Scripts\python scripts\watchdog.py --new-topic`
   — it creates `config\ntfy.toml` and prints a private topic name.
3. In the ntfy app tap **+**, type that topic exactly, **Subscribe**.
4. `.venv\Scripts\python scripts\watchdog.py --test` — the message should
   arrive.

On ntfy.sh anyone who knows a topic can read it, which is why the name is long
and random: keep it private. `config\ntfy.toml` is gitignored. Every alert is
also written to `output\watchdog.log`. Telegram still works as an alternative
(`config\telegram.example.toml`); if both are set up, both get every alert.

## 9. Surviving a reboot

A Windows Update restart or a power cut must not leave the bots off. Four
things make it come back by itself:

1. **Auto-logon.** The tasks run at logon, so Windows must log in on its own.
   Use Sysinternals **Autologon** (`autologon.exe`, from Microsoft) — enter the
   password once; it is stored encrypted. Lock the screen after if you like.
2. **The tasks** (`scripts\install_windows_tasks.bat`, as administrator):
   `trading-bot-terminals` opens both MT5 terminals at logon (BTC with
   `/portable`, gold as a standard install), and the bot tasks start 90 s
   later so the terminals are up when preflight looks for them.
3. **Power-on after power loss.** In the BIOS/UEFI set *Restore on AC power
   loss* (or *AC recovery*) to **Power On**.
4. **Windows Update.** Settings → Windows Update → Advanced options → set
   **Active hours** to cover your trading hours (or *Pause updates* while a
   position is open). Updates still install, but outside those hours.

Algo Trading stays on across a terminal restart as long as the account is not
switched. If it ever comes back off, the watchdog reports
`trade_allowed=False`.

## Operating

```
scripts\restart_bots.bat                      :: restart cent + btc (as administrator)
scripts\restart_bots.bat cent                 :: restart one
scripts\restart_bots.bat stop                 :: stop cent + btc -- do this BEFORE git pull
scripts\restart_bots.bat start                :: start cent + btc after the pull
schtasks /Run   /TN trading-bot-cent          :: start one now
schtasks /Query /TN trading-bot-cent          :: status
type output\supervise_cent.log                :: supervisor log
type output\live_cent.log                     :: bot log
```

**Stopping a bot by hand** takes two steps, as administrator:

```
type nul > output\live_cent.stop              :: tell the supervisor not to restart it
set /p P=<output\live_cent.pid
taskkill /PID %P% /F                          :: stop the bot itself
```

The stop-file alone does nothing while the bot is running: the supervisor only
checks it after the bot exits. `restart_bots.bat` does both steps, checks the
pid really is a running python first, and waits for the task to finish.

Do not use `schtasks /End` on its own: ending the task kills the supervisor and
leaves the bot process orphaned and still trading.

Windows has no SIGTERM convention, so unlike the bash supervisor — which reads
exit code 143/130 as a deliberate stop — the batch one cannot tell a kill from a
crash by exit code. The sentinel file is what distinguishes them.

### The supervisor pid is not recorded, on purpose

`health_check`, `dashboard`, `monitor_trade` and `tune_risk` all read
`output/live_<tag>.pid` and `output/supervise_<tag>.pid`. The **bot** pidfile is
written accurately — from inside the bot's own process by
`scripts\run_with_pidfile.py`, because batch cannot learn a child's pid
reliably.

The **supervisor** pidfile is left unwritten. Batch has no `$$`, and every
workaround is a guess: matching on process name picks the wrong `cmd.exe` when
two bots run, and `for /f` spawns an intermediate shell so a child's `getppid()`
reports a process that dies immediately. A wrong pid is worse than none —
`health_check` would report a dead supervisor as alive the moment Windows reused
that number.

So on Windows, `schtasks /Query /TN trading-bot-<tag>` is the source of truth for
whether the supervisor is alive. Expect the status tools to show the supervisor
as absent while the bot shows as running; that is the known cost, not a fault.

## Known gaps

- **`equivalent_to` dedup tolerance is hardcoded to `0.01`** (`broker/base.py`).
  On gold (~4650) that is 2 ppm; on EURJPY (~172) it is roughly one pip, which is
  tolerable. On a 5-decimal pair like EURUSD it would be 100 pips and would
  over-dedup catastrophically. Scale it by the symbol's `point` before trading
  any pair outside the 3-decimal family.
- **`sl_buffer = 0.01`** is 10 points on a 3-decimal quote. XAUUSDc and EURJPY
  are both 3-decimal, so gold's committed value carries over by coincidence.
  Verify per instrument rather than relying on it.
- **`contract_size`** is backtest-only now; the live risk gate sizes off the
  broker's `trade_tick_value`, which is already in account currency. That is what
  makes a JPY cross safe to size without a conversion step.
