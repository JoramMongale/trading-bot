"""SAFE-03 demo-only execution guard.

Pure decision function the live engine calls before every order placement.
It encodes the phase's two hard safety rules:

1. A REAL trading account is blocked unless ``[live] enabled = true`` in
   config (explicit opt-in).
2. In ``dry-run`` mode, orders are never sent regardless of account type —
   the DryRunBroker seam from plan 02 is the actual no-send enforcement;
   this guard's early return documents that dry-run bypasses the account
   check.

The guard only decides yes/no. It never logs, never touches the broker, and
never imports MetaTrader5 (Windows-only package, RESEARCH.md) — the MT5 trade
mode values are mirrored as module constants instead. The engine decides what
to do with a :class:`SafetyError` (log + skip the setup).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # type-only imports: no runtime broker/config dependency
    from trading_bot.broker.base import AccountInfo
    from trading_bot.config import Config

# Mirrors of MT5 ACCOUNT_TRADE_MODE_* (0 = demo, 2 = real) so safety.py
# never needs the Windows-only MetaTrader5 package.
ACCOUNT_TRADE_MODE_DEMO = 0
ACCOUNT_TRADE_MODE_REAL = 2


class SafetyError(Exception):
    """Raised when the guard blocks execution (SAFE-03)."""


def verify_execution_allowed(cfg: Config, account: AccountInfo) -> None:
    """Raise :class:`SafetyError` if order placement is not allowed.

    Args:
        cfg: Loaded project config (``.live`` carries ``mode``/``enabled``).
        account: Broker account snapshot (``.trade_mode``: 0=demo, 2=real).

    Returns:
        None when execution is permitted.

    Checks run in order: dry-run first (never sends), then the two
    real-account rules.
    """
    # Rule 1 (dry-run): orders are never sent regardless of account type.
    # DryRunBroker (plan 02) is the enforcement seam; this early return
    # documents that dry-run always passes the guard.
    if cfg.live.mode == "dry-run":
        return

    # Rule 2 (real-account opt-in): a REAL account requires the explicit
    # [live] enabled=true opt-in before any order placement is considered.
    if account.trade_mode == ACCOUNT_TRADE_MODE_REAL and not cfg.live.enabled:
        raise SafetyError(
            "REFUSED: REAL trading account detected (trade_mode=2) but "
            "live.enabled=false. Demo-only enforcement (SAFE-03). Set "
            "[live] enabled=true only to explicitly opt in."
        )

    # Rule 3 (demo mode + real account): mode='demo' means "demo account
    # only"; a REAL account must be traded under mode='live' + enabled.
    if cfg.live.mode == "demo" and account.trade_mode == ACCOUNT_TRADE_MODE_REAL:
        raise SafetyError(
            "REFUSED: mode='demo' but account is REAL. Switch to a demo "
            "account or explicitly set [live] enabled=true."
        )
