---
id: 260820-pi
slug: raspberry-pi-deployment
date: 2026-08-20
status: complete
---

# Can the bot run on a Raspberry Pi?

**The bot yes, MetaTrader 5 no.** Split them and it works today with no code
changes. Answer + recipe: `docs/raspberry-pi-deployment.md`.

## Measured, not estimated

| | footprint | ARM? |
|---|---|---|
| `trading_bot` | 34 MB RSS, ~0% CPU | yes, pure Python (pandas/numpy ship aarch64 wheels, Pi OS Bookworm has 3.11) |
| MT5 container | 2.86 GiB, **416% CPU** | no |

MT5 is a Windows x86-64 binary. On this arm64 M5 it already runs through two
emulation layers — an x86_64 Colima VM under QEMU, then Wine inside it — which
is where the 416% goes. A Pi would add ARM→x86-64 on top of that.

## The split already works

`[live] bridge_host`/`bridge_port` are config and the bridge listens on
`0.0.0.0:8001`. Verified by running preflight against the LAN address
(10.42.0.248) instead of localhost: account, bars and freshness all resolved.
That is the exact call path a Pi makes.

## Security finding (the important part)

**The bridge has no authentication.** Client signature is
`MetaTrader5(host, port, keepalive, timeout)` — no token, no password, no TLS.
It is an rpyc server (default port 18812) published on `0.0.0.0:8001`, so
anyone who can reach the port can place orders on the account, and with rpyc
possibly execute code in the container.

This was already true before the Pi question — moving the bot off-box just
makes it tempting to expose. Recommendation: SSH tunnel and bind the published
port to 127.0.0.1. Especially given this machine hosted an infostealer until
2026-08-19.

## Caveat

A Pi makes the bot cheaper to leave running. It does not make the strategy
work — measured edge is negative net of spread (see STATE.md).
