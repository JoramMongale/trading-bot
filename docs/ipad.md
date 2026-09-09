# Running the bot on an iPad

Short answer: **no, and for a different reason than the Raspberry Pi.**

The Pi could not host MetaTrader 5 but ran the bot fine, so splitting them
worked. On an iPad *neither* half runs. The iPad is a good control surface for
a bot hosted elsewhere, and that is worth setting up — but it cannot be the
machine that trades.

## Why the bot itself cannot run there

Not resources. The bot is **32 MB RSS at ~0% CPU** — an iPad has more compute
than the Mac hosting it needs.

The blocker is the process model. `cli.py` is:

```python
while True:
    engine.poll_once()
    time.sleep(cfg.live.poll_interval)   # 5s
```

An unbounded loop that must keep running for days. iPadOS suspends an app
shortly after it leaves the foreground; sustained background execution is
granted only to narrow categories (audio, location, VoIP), none of which a
trading loop can honestly claim. So the bot runs only while you are looking at
it, with the screen on, and stops when you switch apps. A bot that stops when
you check your email is not a bot.

There is also no Docker on iPadOS, so the containerised MT5 terminal the whole
setup depends on has nowhere to run either.

## Why the terminal cannot run there

MetaTrader 5 has a good iPad app, but it is a *terminal*, not a host: it
exposes no Python API. The `MetaTrader5` package this project drives is a
desktop product, and on Apple Silicon it already needs an x86_64 VM plus Wine
(see `raspberry-pi-deployment.md`). None of that exists on iPadOS.

## What the iPad IS good for

The split already works — verified on 2026-08-20 by pointing preflight at a LAN
address instead of localhost. Host the bot on the Mac, a spare desktop, or a
Windows VPS, and use the iPad as the control surface:

- **MT5's official iPad app**, logged into the same account: live positions,
  P&L, and a manual close button if you ever need to override the bot. This is
  the one genuinely valuable piece — it works today, no setup on our side.
- **An SSH client** (Termius, Blink) into the host for
  `scripts/run_demo.sh status`, `tail -f output/live.log`, start/stop.

Both are read-and-react, which is the right relationship to have with a bot
anyway.

## Security, if you do this

**Never point an iPad at the bridge port directly.** The `siliconmetatrader5`
RPC bridge has no authentication at all — client signature is
`MetaTrader5(host, port, keepalive, timeout)`, no token, no password, no TLS —
and it is an rpyc server, so exposure may not stop at the MT5 API. Reaching it
from a tablet means putting it on a network.

Use SSH port-forwarding, or just use the MT5 app, which authenticates properly
against the broker. See the security section of `raspberry-pi-deployment.md`.

## Not verified

I have no iPad to test against, so the specifics above are reasoning from the
platform's constraints rather than measurement. The parts I am confident about
are structural: iPadOS suspends background apps, there is no Docker, and the
MT5 Python API is desktop-only. If you want to try a Python environment on iPad
(a-Shell, Pythonista) the thing to check first is not whether Python runs, but
whether a loop survives backgrounding — that is what decides it, and I would
expect the answer to be no. Note the project also needs Python >= 3.11 with
pandas >= 3.0 and numpy >= 2.0, which iPad Python environments may not carry.
