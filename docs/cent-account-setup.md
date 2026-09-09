# Opening a USC cent account and getting it trading

This is the account type that makes the strategy affordable on a small balance.
Everything below was verified against a live Exness cent account
(`161693049`, server `Exness-MT5Real21`) on 2026-08-21.

---

## Why a cent account at all

The stop in this strategy is **structural** — it sits below the confirmed
support level, so its distance is set by the market, not by what you can
afford. You cannot make a trade cheaper by wanting it to be cheaper. The only
two levers are position size and the value of one price unit.

On a **standard** account, gold is 100 oz per lot. The broker minimum of 0.01
lots is 1 oz, and the median backtested stop of $31.83 therefore costs $31.83.
Against a $31 balance that is **103% risk on one trade** — the sizing gate
refuses it, correctly, and the bot never trades.

On a **cent** account the same $31 balance is denominated in cents, so it reads
as 3,100 USC, and gold is quoted as `XAUUSDc` at 1 oz per lot. The same trade
risks about 42 USC of 3,121 USC: **1.36%**, inside a 2% policy.

Same money. Same market. Same stop. The only thing that changed is the unit the
account is denominated in and the contract size behind the symbol — and that is
the difference between a bot that cannot place a single order and one that can.

| | standard | cent |
|---|---|---|
| balance | $31.21 | 3,121 USC |
| gold symbol | `XAUUSDm` | `XAUUSDc` |
| contract size | 100 oz | 1 oz |
| median stop cost at 0.01 lot | $31.83 | 42.49 USC |
| as % of balance | **103%** | **1.36%** |

> A cent account does **not** reduce risk. It reduces *granularity*. You are
> risking the same fraction of the same money; you are simply able to express a
> position small enough to stay inside your own policy. Nothing here improves
> the strategy's edge, which remains negative.

---

## Steps

### 1. Open the account

In the broker's Personal Area (this project uses Exness; the wording differs
between brokers but the shape does not):

1. **Accounts → Open new account.**
2. Choose account type **Standard Cent**. This is the step that matters — it is
   a different account, not a setting you can toggle on an existing one. If you
   already funded a standard account you will need to open a second account and
   move the funds internally.
3. Set the currency to **USC** (US Cent). Confirm it reads USC, not USD.
4. Choose **MT5**, not MT4 — the Python API in this project is MT5-only.
5. Set a password and note the **login number** and **server name**
   (e.g. `Exness-MT5Real21`). You need all three.
6. Fund it, or transfer internally from an existing account.

### 2. Log the terminal in

- **Windows:** MetaTrader 5 → File → Login to Trade Account, enter login,
  password, server.
- **macOS/Linux:** the terminal runs in the container — see
  `docs/macos-demo-setup.md`. Log in inside the containerised terminal.

Then, in the terminal: **Tools → Options → Expert Advisors → Allow algorithmic
trading.** Without it every order is rejected.

> This resets when you switch accounts in the terminal. After any login change,
> re-check `terminal_info().trade_allowed` before trusting the bot.

### 3. Find the broker's real symbol names

Cent accounts use suffixed symbols and the suffix is broker-specific — `c` here,
but do not assume. Open **Market Watch → right-click → Symbols** and read the
actual name, or let the code tell you:

```python
python -c "from siliconmetatrader5 import MetaTrader5 as S; m=S(); m.initialize(); print([s.name for s in m.symbols_get() if 'XAU' in s.name])"
```

Put the answer in `[live] symbol`. `[data] symbol` stays `XAUUSD` — that names
the histdata CSVs the backtester reads, which have no broker suffix.

### 4. Verify before funding decisions

```bash
.venv/bin/python scripts/preflight_demo.py --config config/config-cent.toml
```

Note this **refuses REAL accounts by design**, and that guard should stay. On a
real account run the equivalent checks read-only instead: bridge reachable,
`trade_allowed=True`, bars arriving, feed fresh, and sizing computed across
every stop percentile.

What a correctly configured cent account looks like:

```
account 161693049  server=Exness-MT5Real21  currency=USC  leverage=1:2000  trade_mode=2
XAUUSDc   contract=1.0    tick_size=0.001  tick_value=0.1   vol_min=0.01  digits=3
BTCUSDc   contract=0.01   tick_size=0.01   tick_value=0.01  vol_min=0.01  digits=2
```

`currency=USC` and `contract=1.0` on gold are the two that confirm you are
actually on a cent account. `trade_mode=2` means REAL — on a demo it is 0.

---

## The rule that makes sizing correct

**Size from the broker's `trade_tick_value`. Never from `contract_size`.**

`trade_tick_value` is already denominated in the account currency, so it
absorbs both the contract size *and* the USD-profit-to-USC-balance conversion in
one number. `contract_size` knows about neither. Using it on a cent account
produces a risk figure that is wrong by a factor of 100 — and wrong in the
dangerous direction, understating what a trade costs.

`[trading] contract_size` survives in the config only for the backtester, which
has no broker to ask.

This is not theoretical. It is why gold at 0.01 lots was computed as 103% risk
and unplaceable until sizing was switched to `tick_value`, after which the same
trade correctly measured 1.36%.

---

## What a cent account does not fix

The **funding floor is structural.** Across 340 recorded backtest trades the
stop distance was $5.33 min / $24.30 median / $59.78 p95 / $129.76 max per 0.01
lot. At a 2% cap, the median trade needs roughly **$1,215** of balance to clear
the gate and about **$3,000** for the p95. Below that the bot correctly refuses
to trade rather than risk the account on one breakout.

A cent account changes the units, not that arithmetic. On a very small balance
you will still see setups skipped with `reason="risk_exceeded"`, and that is the
system working.

And the strategy's measured edge is still negative — −0.0156R over 6,541 gold
trades, −0.049R over 210 BTC trades. Opening the right account type makes it
*possible* to trade this. It does not make it *profitable*.

---

## Related

- `config/config-cent.toml` — the gold cent configuration, with the reasoning
  in its comments
- `config/config-btc.toml` — BTCUSDc, the 24/7 instrument
- `docs/macos-demo-setup.md` — the container route for macOS/Linux
- `.planning/STATE.md` — current live state and the weekend schedule
