---
quick_id: 260819-nhq
slug: mac-demo-mt5-bridge
date: 2026-08-19
type: quick
status: incomplete
---

# Quick Task Summary: Verify Phase 2 + macOS demo-account path

## Verification performed (macOS, Apple M5, Python 3.14.2)

| Check | Result |
|---|---|
| Full test suite | 115/115 green before changes, 142/142 after |
| Backtest end-to-end on real 2025-2026 XAUUSD data | 339 closed trades, 60.8% win rate, PF 1.29, avg R 0.14, max DD $271.44 |
| `live --once --mode dry-run` | exits 0 |
| `MetaTrader5` pip availability on macOS | **none** — no wheel for any macOS architecture (`pip index versions` returns nothing) |
| ruff | 3 pre-existing findings in untouched test files; no new ones |

## Defects found and fixed

1. **Dry-run never ran the strategy.** `build_broker` handed the engine a
   `SimulatedBroker` with `rates=None`, so every poll logged `bar_fetch_failed`
   and detection never executed. Only the E2E test seeded data, which is why
   the suite stayed green over a CLI path that did nothing.
   Fixed with `ReplayBroker` + histdata seeding: a 15s run now walks 497 bars
   and finds 4 setups.

2. **`SimulatedBroker.fetch_rates` wrapped on a rewound cursor.**
   `iloc[cursor - count : cursor]` with `cursor < count` indexes from the end of
   the frame instead of returning the bars that exist. Window start clamped
   at 0. (Latent — the golden frame was short enough that pandas' bounds
   clamping masked it.)

3. **The dry-run audit trail was missing outside tests.** `build_broker` passed
   `logger=None` to `DryRunBroker`, so its SAFE-02 `order_plan` line never
   reached `live.log`. The live logger is now wired through.

4. **`order_placed` was indistinguishable from a real placement in dry-run.**
   The engine ignored `result.placed`, logging `order_placed ticket=0` either
   way. Now carries `placed=`.

## Delivered

- `ReplayBroker`, public `cursor` arg on `SimulatedBroker`
- `[live] bridge` / `bridge_host` / `bridge_port` / `replay_bars` config keys
- `MT5Broker._mt5()` transport resolver: native package, `siliconmetatrader5`
  RPC bridge, or auto. Native stays uncached so the 30 fake-MT5 tests keep
  injecting through the module-level `_load_mt5` import site.
- 27 new tests (`test_replay_broker.py`, `test_mt5_bridge.py`,
  `test_build_broker.py`)
- `docs/macos-demo-setup.md`
- Colima + QEMU + Lima installed; `siliconmetatrader5==1.2.3` in the venv;
  `silicon-metatrader5` cloned to `~/projects/silicon-metatrader5`

## NOT delivered — demo run paused

The demo-account verification (02-06 equivalent) was **not** performed.

While setting up the bridge, a `ps` listing surfaced active malware on this
machine: a LaunchAgent (`com.luhbmchzztkfbxao`, RunAtLoad + KeepAlive, present
since 2026-07-04, running since 2026-08-04) reading its C2 address from a
Polygon smart contract and piping the response into `osascript` — the
EtherHiding technique. Two stage-2 `osascript` processes were running.

Persistence removed and processes killed on 2026-08-19; evidence preserved in
the session scratchpad. No second persistence mechanism found.

Logging into a broker account on a machine that hosted a credential stealer for
six weeks would expose those credentials, so the MT5 login step was deliberately
not taken. **Resume only after credentials are rotated from a clean device.**

## Resume checklist

1. Rotate credentials from a different machine (broker, browser-saved
   passwords, SSH keys, API tokens, wallets)
2. Quit Docker Desktop
3. `colima start --arch x86_64 --vm-type=qemu --cpu 4 --memory 8`
4. `docker context use colima`
5. `cd ~/projects/silicon-metatrader5/docker && docker compose up --build`
6. Log into the demo account at <http://localhost:6081/vnc.html>
7. Set `[live] mode = "demo"`, `bridge = "silicon"`, keep `enabled = false`
8. Run the 4-step 02-06 checklist (live bars, demo Buy Stop with 1:1 SL/TP,
   SAFE-03 real-account block, pending-order dedup)
