"""Bank-the-profits helper for the live gold cent account.

One command that shows balance, pinned base, and bankable excess in USC + R.

The bot compounds (sizing="percent", max_loss_pct_per_trade=20): after a
take-profit the balance grows and the NEXT trade re-risks a percentage of the
LARGER balance — including the profit that was supposed to be banked. The
user's money rule is "trade with the R500 base, not with the profit", so this
tool makes the banking decision legible and records it:

    python scripts/bank_profits.py                 # view balance/base/bankable
    python scripts/bank_profits.py --base 3000     # re-pin the base stake (USC)
    python scripts/bank_profits.py --confirm       # record one banking event
    python scripts/bank_profits.py --tag btc       # another bot's config
    python scripts/bank_profits.py --usd-rate 18.5 # USC->ZAR rate for the R est

Exit codes: 0 ok, 2 error/broker unavailable.

SAFETY MODEL: this tool is READ-ONLY against the broker. It reads
account_info() and nothing else — there is no order_send, no position
modification, and no order-close call anywhere in this file, so it cannot
place, move, or exit a trade. The actual withdrawal is a MANUAL action in the
Exness portal that this tool only reports and logs: after --confirm it appends
one key=value line to output/profits_banked.log recording the decision and
prints the exact withdrawal amount with the instruction to transfer it by hand.
The bot cannot move money; only the user can, in the portal.

Runtime state is gitignored scratch under output/:
    output/bank_base.txt       the pinned base stake in USC (written on first
                               run or by --base; read on every view)
    output/profits_banked.log  one line per banking event (appended by
                               --confirm)
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

# Reuse the established tag -> config convention (health_check.py). Re-exported
# as a module-level name so tests can monkeypatch bank_profits.BOTS to point at
# tmp copies — the live configs and the real output/ dir are never touched.
from health_check import BOTS  # noqa: E402

BASE_FILE = ROOT / "output" / "bank_base.txt"
LEDGER = ROOT / "output" / "profits_banked.log"
MIN_BANKABLE_USC = 1000.0  # ~$10 — below this, withdrawals are uneconomical
DEFAULT_USD_RATE = 18.0  # USC -> ZAR estimate (same formula as health_check.py)


def _connect(cfg):
    """Attach to the terminal following the repo's transport convention.

    Mirrors monitor_trade.py: lazy import inside the function (never at module
    top — MetaTrader5 is Windows-only and absent on this Mac), native package
    preferred, the siliconmetatrader5 RPC bridge as the fallback at the
    CONFIG's host/port (never a hardcoded address), then an initialize() guard.
    Raises BrokerUnavailableError when no terminal can be reached.
    """
    from trading_bot.broker.base import BrokerUnavailableError
    from trading_bot.broker.mt5 import _load_mt5, _load_silicon_bridge

    try:
        mt5 = _load_mt5()
    except BrokerUnavailableError:
        mt5 = _load_silicon_bridge(cfg.live.bridge_host, cfg.live.bridge_port)
    if not mt5.initialize():
        raise BrokerUnavailableError("terminal initialize failed")
    return mt5


def read_base(path) -> float | None:
    """The pinned base stake in USC, or None when absent/empty/unparsable."""
    try:
        return float(path.read_text().strip())
    except (OSError, ValueError):
        return None


def pin_base(path, value) -> None:
    """Pin ``value`` USC as the base stake (2 decimals).

    A plain write is fine: this is gitignored scratch state, not a live config
    being edited (tune_risk's atomic dance exists for config/ files only).
    """
    path.write_text(f"{value:.2f}\n")


def r_est(usc: float, rate: float) -> float:
    """Approximate Rand value of ``usc`` USC units: USC / 100 * usd_rate."""
    return usc / 100 * rate


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1].strip())
    p.add_argument("--tag", choices=sorted(BOTS), default="cent",
                   help="which bot's config to read (default: cent)")
    p.add_argument("--base", type=float, metavar="USC",
                   help="re-pin the base stake to this many USC")
    p.add_argument("--confirm", action="store_true",
                   help="record one banking event in output/profits_banked.log")
    p.add_argument("--usd-rate", type=float, default=DEFAULT_USD_RATE,
                   help=f"USC->ZAR rate for the R estimate "
                        f"(default: {DEFAULT_USD_RATE})")
    a = p.parse_args(argv)

    from trading_bot.broker.base import BrokerUnavailableError
    from trading_bot.config import load_config, live_symbol

    cfg = load_config(ROOT / BOTS[a.tag])

    try:
        mt5 = _connect(cfg)
    except BrokerUnavailableError as exc:
        print(f"broker unavailable: {exc}")
        return 2

    acct = mt5.account_info()
    balance = float(acct.balance)
    now_utc = datetime.now(timezone.utc)
    print(f"bank profits  {a.tag}  {live_symbol(cfg)}  "
          f"{now_utc:%Y-%m-%d %H:%M:%S}Z  "
          f"account {acct.login} @ {acct.server}  currency {acct.currency}")

    # Base stake resolution: --base repins deliberately; else read the file;
    # else (first run) pin the current balance so future banking is legible.
    if a.base is not None:
        pin_base(BASE_FILE, a.base)
        base = a.base
        print(f"base pinned = {base:.2f} USC")
    else:
        base = read_base(BASE_FILE)
        if base is None:
            base = balance
            pin_base(BASE_FILE, balance)
            print(f"first run: pinned base = {balance:.2f} USC (current balance)")

    excess = balance - base
    bankable = max(0.0, excess)
    r = r_est(bankable, a.usd_rate)
    print(f"balance {balance:.2f} USC  base {base:.2f} USC  "
          f"bankable {bankable:.2f} USC  (~R{r:.2f}, usd_rate {a.usd_rate})")
    if bankable <= 0:
        print("nothing to bank")
    elif excess < MIN_BANKABLE_USC:
        print(f"WARNING: bankable {excess:.2f} USC is below the practical "
              f"withdrawal minimum (${MIN_BANKABLE_USC / 100:.2f}); frequent "
              "small withdrawals may be uneconomical — consider banking weekly "
              "instead")

    if a.confirm and excess > 0:
        line = (
            f"{now_utc:%Y-%m-%d %H:%M:%S} event=profits_banked "
            f"base={base:.2f} balance={balance:.2f} excess={excess:.2f} "
            f"balance_after={base:.2f} usd_rate={a.usd_rate} r_est={r:.2f}\n"
        )
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(line)
        print(f"withdraw {excess:.2f} USC ≈ ${excess / 100:.2f}")
        print("MANUAL ACTION REQUIRED — the withdrawal is a MANUAL transfer in "
              f"the Exness portal (account {acct.login} @ {acct.server}). The "
              "bot cannot withdraw money; this tool only recorded the decision "
              "in the ledger.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
