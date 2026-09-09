---
phase: quick-007-btc-separate-account
plan: 01
type: design
wave: 1
depends_on: []
autonomous: false
status: DESIGN

objective: >
  Run the BTC bot on its OWN Exness account (magic 77021, BTCUSDc) so its risk
  is isolated from the gold cent account — no summed 21% account-wide exposure,
  caps apply per-account, each account's base stake and banking are tracked
  independently. User funds the new account while this design is finalised.
---

<objective>
Design the second-account BTC setup: a dedicated Exness account + its own MT5
terminal + its own siliconmetatrader5 bridge, reached by the existing
`config/config-btc.toml` with only a bridge-port change. Gold's cent account and
its terminal are left byte-identical and untouched. Implementation starts only
after the account is funded and the design is reviewed.
</objective>

## The binding constraint

One `siliconmetatrader5` bridge = one MT5 terminal = **one logged-in account**.
The bridge process (`wine python -m siliconmetatrader5 "C:/Python/python.exe"
--host ... -p 8001` in the container's `start.sh`) attaches to the terminal with
the saved session on disk (`Config/accounts.dat`), which today holds the gold
cent account `161693049`.

MT5's API cannot hold two accounts in one terminal, and the codebase's
account-terminal detection (`run_demo.sh` `_account_terminals`) already carries a
WARNING when more than one account terminal runs — "the bridge may attach to the
wrong one". Reusing one terminal for two accounts is fragile by construction.

**Therefore: a second account needs a second terminal, and that means a second
container.** Each container runs exactly one terminal with exactly one bridge, so
the existing single-terminal assumption that every script makes stays true.

## Recommended architecture

A sibling container `siliconmt5-btc` alongside `siliconmt5`, sharing the same
colima VM (no second VM), with:

| | gold (existing) | btc (new) |
|---|---|---|
| container | `siliconmt5` | `siliconmt5-btc` |
| bridge port | 8001 | 8002 |
| VNC / noVNC | 5901 / 6081 | 5902 / 6082 |
| account | 161693049 (USC cent, XAUUSDc) | new BTC account (BTCUSDc) |
| wine prefix | `wineprefix_persistence` | own volume, own prefix |
| magic | 77020 | 77021 (already in config) |

Why not a second terminal *inside* the existing container: the Wine prefix,
X display and `start.sh` bridge all assume one account terminal; two terminals
reintroduce exactly the "wrong terminal" failure the codebase has spent three
incidents eliminating. Isolation is the point of the separate account.

Cost: one more Wine + MT5 process under QEMU TCG inside the same VM. The colima
VM is sized `--memory 6`; two terminals + two Xvfb/openbox may push it. Raise
the VM to 8 GB before the second container runs. Two details matter:

- `colima start --memory 8` only applies on a fresh create — a running VM keeps
  its old size, so this needs `colima stop` then `colima start` (or `colima
  delete` on first try if it refuses to resize).
- `scripts/launchd_run_live.sh:99` hardcodes `--memory 6` in its cold-start
  `colima start`. That line must move to `--memory 8` too, or the next reboot
  brings the VM back down to 6 GB and the two-container stack starves. Verify
  with `free -h` inside the VM (`docker exec` or `colima ssh`).

## Changes required (all additive, gold path untouched)

### 1. Container / bridge (silicon-metatrader5 repo, outside this repo)

- Parametrise `start.sh`'s hardcoded bridge port and VNC ports via env vars
  (`MT5_BRIDGE_PORT`, defaults to 8001 / 6081) so one image serves both
  containers.
- The compose `healthcheck` also hardcodes port 8001 (`connect_ex(('127.0.0.1',
  8001))`) — parametrise it the same way, or the new service's healthcheck
  probes the wrong port.
- Add a second compose service (or a `compose.btc.yaml`) with container name
  `siliconmt5-btc`, ports `8002`/`5902`/`6082`, and its own named volume.
- **Bind the new bridge to 127.0.0.1, not 0.0.0.0.** STATE.md already flags the
  bridge as unauthenticated RPC on 0.0.0.0:8001; the new one must not repeat
  that. (The existing 8001 exposure is out of scope here but should be fixed the
  same way.)

### 2. Config (this repo)

- `config/config-btc.toml`: set `[live] bridge_port = 8002`. Everything else is
  already correct: `symbol = "BTCUSDc"`, `magic_number = 77021`,
  `mode = "live"`, `enabled = true`, risk `0.5% x 2 slots` (per-account now).
- `[data] symbol` stays `XAUUSD` for the backtest CSV side; only the live symbol
  matters here.
- No change to `config-cent.toml` (gold stays 20% × 1 slot, but now measured
  against its own balance — the earlier 21% summed-cap concern disappears).

### 3. Bring-up scripts (this repo)

- `run_demo.sh`: `CONTAINER`, `ACCOUNTS_DAT`, `ACCOUNT_TERMINAL` and
  `NOVNC_URL` are hardcoded to the gold container. Derive them from `INSTANCE`
  (e.g. `btc` → container `siliconmt5-btc`, bridge 8002, noVNC 6082), keeping
  the default branch byte-identical for gold.
- `launchd_run_live.sh`: `docker start siliconmt5` hardcodes the container name;
  parametrise by `TAG`.
- `preflight_live.py`: already reads `cfg.live.bridge_host/bridge_port` — no
  change needed; it will probe 8002 automatically.

### 4. Status/ops tools (this repo)

- `health_check.py`: the broker section connects once to bridge 8001 and runs
  both tags off it. With two accounts it must connect per-tag (gold→8001,
  btc→8002). The `BOTS` tag→config map already exists; extend the broker section
  to open one connection per distinct `bridge_port`.
- `dashboard.py` and `bank_profits.py`: both already read
  `cfg.live.bridge_host/bridge_port` per config — no code change expected, verify
  only. `bank_base.txt` must become per-tag (gold base vs btc base) so banking
  tracks each account independently.

### 5. Manual, one-time (after funding)

- Create + fund the new Exness account (user, portal).
- Log in once at the new terminal's noVNC (`http://localhost:6082/vnc.html`),
  saved session persists in the new prefix's `accounts.dat` (same as gold).
- Enable Algo Trading in the new terminal; re-check `trade_allowed` after login
  (STATE.md gotcha).

## Sequencing

1. Design review (this doc).
2. User funds the new account.
3. Infra: parametrise `start.sh`, add compose service, bind 127.0.0.1.
4. VM memory to 8 GB, start `siliconmt5-btc`, login once, enable algo trading.
5. This repo: `bridge_port` in btc config, parametrise `run_demo.sh` +
   `launchd_run_live.sh` by tag, per-tag health_check + bank base.
6. Bootstrap `com.joram.trading-bot-btc`; verify BTC polls 8002 and both bots
   report independently in health_check/dashboard.

## Explicit non-goals

- NOT moving gold's terminal, config or agent.
- NOT automating fund transfers between accounts (API cannot; stays manual).
- NOT starting the btc agent until the account is funded and this design is
  reviewed — the one-bot-at-a-time state stays until then.
