# Running the bot on a Raspberry Pi

Short answer: **the bot yes, MetaTrader 5 no.** Split them and it works today,
with no code changes — but read the security section before putting the bridge
on a network.

## Why the split

The two halves have completely different requirements.

| | footprint | portable to ARM? |
|---|---|---|
| the bot (`trading_bot`) | **34 MB RSS, ~0% CPU** | yes — pure Python |
| the MT5 stack (container) | **2.86 GiB, 416% CPU** | no |

Those numbers are measured, not estimated: `docker stats` on the M5 while the
bot was idle-polling.

**The bot** is pandas + numpy on Python ≥3.11. Both ship aarch64 wheels, and Pi
OS Bookworm ships 3.11. It polls one small request every 5 seconds and holds
69 bars in memory. A Pi Zero 2 would not notice it.

**MetaTrader 5** has no Linux or ARM build — it is a Windows x86-64 binary. On
this Mac it already runs through two layers of emulation: an x86_64 Colima VM
under QEMU (the host is arm64), then Wine inside that. Hence 416% CPU: four
cores of an M5 spent emulating. Stacking that on a Pi's Cortex-A76 — ARM →
x86-64 via box64/QEMU, then Wine — is possible to get booting and useless in
practice for a live feed.

So do not try to move the terminal. Move only the bot.

## The split, which already works

`[live] bridge_host` / `bridge_port` are config, and the bridge already listens
on `0.0.0.0:8001`, so nothing needs writing. On the Pi:

```toml
[live]
mode = "demo"
bridge = "silicon"          # not "auto": there is no native MT5 to fall back to
bridge_host = "10.42.0.248" # the machine running the container
bridge_port = 8001
```

Verified on 2026-08-20 by pointing preflight at the LAN address instead of
localhost — account, bars and freshness all resolved normally. That is exactly
the call path a Pi makes.

The terminal host can be this Mac, a spare desktop, or the usual answer for
MT5: a cheap Windows VPS, which removes the emulation entirely.

## SECURITY — read before exposing port 8001

**The bridge has no authentication.** Its client is
`MetaTrader5(host, port, keepalive, timeout)` — no token, no password, no TLS.
It is an rpyc server (default port 18812) published on `0.0.0.0:8001`.

Anyone who can reach that port can place orders on the account. With rpyc that
may extend well past the MT5 API to arbitrary code execution in the container.
On a machine that hosted an infostealer until 2026-08-19, do not put this on a
network in the clear.

Tunnel it instead. On the Pi:

```bash
ssh -N -L 8001:localhost:8001 joram@<terminal-host>
```

then leave `bridge_host = "localhost"` in the Pi's config — the bot talks to
the local end of the tunnel and the port is never exposed. Bind the published
port to `127.0.0.1:8001` in the compose file as well, so it cannot be reached
directly even by accident.

## What the Pi does not fix

The bot is not the bottleneck in this project. A Pi makes it cheaper to leave
running; it does not make the strategy work. As of 2026-08-20 the measured edge
across 17 instruments and 6,541 trades is **negative net of spread**
(mean R −0.0156), and no instrument survives multiple-comparison correction.
See STATE.md.
