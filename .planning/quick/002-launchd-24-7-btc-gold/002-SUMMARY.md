# Quick Task 002 — Permanent 24/7 launchd agents for BTC + gold

**Status:** complete — both bots launchd-supervised, takeover verified, crash-recovery path documented.

## What was built

- `scripts/launchd_run_live.sh btc|cent` — real-money launchd entry point. Brings the stack up in
  dependency order (colima → siliconmt5 container → openbox → ACCOUNT terminal → `preflight_live.py
  --real-account`) then `exec`s the unmodified `supervise_live.sh` in the foreground. Reuses
  `run_demo.sh check` via a new `LIVE=1` switch that swaps `preflight_demo.py` (refuses REAL) for
  `preflight_live.py --real-account`; the demo guard stays the default. Stands down (exit 0) while a
  manual bot owns the tag pidfile, so installation is non-disruptive.
- `scripts/com.joram.trading-bot-btc.plist`, `scripts/com.joram.trading-bot-cent.plist` — RunAtLoad,
  KeepAlive, ThrottleInterval 60, background, stdio to `output/launchd_live_*.{out,err}`.
- Both agents installed in `~/Library/LaunchAgents/` and bootstrapped.

## Design notes

- **`supervise_live.sh` untouched** — it was live-executing during the build; bash re-reads a running
  script, and editing it live with real money on the account is undefined behaviour. The wrapper
  wraps it unmodified.
- **Stand-down, never fight**: agent exits 0 while a manual bot holds `output/live_<tag>.pid`, so the
  takeover is `kill $(cat output/live_*.pid)`.
- **Shared stack-bring-up lock** serialises both agents at login so the account terminal launches once.

## Bug found + fixed during the handover (commit `21efabb`)

The stack-bring-up lock stored its owner pid **inside** the lock directory, so the release `rmdir`
always failed on a non-empty directory and the second agent deadlocked: the owner (cent) was alive,
so the stale-reclaim never fired, and the btc agent waited out its full 30-minute window. Fixed by
moving the pid to a sibling file (`output/.stack-bring-up.pid`) so the lock dir stays empty and
`rmdir` releases it; reclaim also removes the stale pid file. Verified live: btc agent now completes
bring-up and starts its supervisor/bot.

## Handover — executed and verified 2026-08-24 08:18 UTC

- Manual supervisors killed (`kill $(cat output/live_btc.pid output/live_cent.pid)`).
- Takeover (new pids, all different from the manual ones):

  | tag | launchd agent / supervisor | bot | started |
  |-----|----------------------------|-----|---------|
  | btc | 16586 | 16683 | 08:16:58Z |
  | cent | 16020 | 16117 | 08:13:08Z |

- `launchctl list | grep joram.trading-bot` → both jobs with pids.
- `monitor_trade.py` (both tags) exit 0 / HEALTHY; BTC still sees both open positions
  (434510667, 435396825 — position-open dedup intact), gold flat.
- `order_placed` counts unchanged after takeover: **btc=6, cent=1** — no duplicate placement.
- Stack lock released correctly after the fix (dir empty/absent, no stale pid file).

## Remaining verifications (documented, not blocking)

1. **Crash recovery** (warm): `launchctl kickstart -k gui/$(id -u)/com.joram.trading-bot-cent` →
   expect launchd respawn with a new supervisor + bot within ~2-4 min.
2. **Deliberate stop**: `launchctl bootout gui/$(id -u)/com.joram.trading-bot-cent` → agent unloaded,
   cent bot dead and NOT respawned after >60s; restore with
   `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.joram.trading-bot-cent.plist`.
3. **Cold-boot survival**: never executed for the demo agents either — colima start from a launchd
   context after a real reboot is still the unknown. Warm kickstart proves crash respawn.

## Open decision — weekend-gap guard (gold)

User chose **option-a**: add a `[live]` engine guard refusing NEW gold entries after Friday ~19:00
UTC (matching the manual 19:02 close precedent). This is a follow-up quick task, not built here.
BTC is unaffected (24/7 market). Until the guard lands, a Friday-evening gold setup can still open a
position that rides the Sunday 21:00 UTC reopening gap.
