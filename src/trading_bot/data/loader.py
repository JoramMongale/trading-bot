"""Histdata ASCII M1 CSV loader (verified format from RESEARCH.md RQ3).

Row format: `20120201 000000;open;high;low;close;volume`
- semicolon-separated, no header
- bid quotes only; timestamps are EST (UTC-5, no DST)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


def load_histdata_csv(path: str) -> pd.DataFrame:
    """Parse a histdata M1 CSV into a DataFrame indexed by time.

    Returns a DataFrame with columns ``["open", "high", "low", "close",
    "volume"]`` (float dtypes) and a datetime index named ``time``.
    """
    df = pd.read_csv(
        path, sep=";", header=None,
        names=["dt", "open", "high", "low", "close", "volume"],
    )
    # pandas 3.0 infers datetime64[s]; do NOT force unit="ns".
    df["time"] = pd.to_datetime(df["dt"], format="%Y%m%d %H%M%S")
    df = df.set_index("time").drop(columns="dt")
    for col in df.columns:
        df[col] = df[col].astype(float)
    return df[["open", "high", "low", "close", "volume"]]


@dataclass(frozen=True)
class InstrumentSpec:
    """Broker-captured symbol facts for one instrument (STACK spec sidecar).

    Pure offline mirror of the live SymbolRisk source (broker/mt5.py symbol_risk):
    money per price-unit per lot is tick_value / tick_size, in ACCOUNT currency —
    the same formula the live risk gate uses, so backtest money and live sizing
    can never disagree. Never derives money from [trading] contract_size when a
    spec is present (PITFALLS A2).
    """

    symbol: str
    digits: int
    point: float
    tick_size: float
    tick_value: float
    contract_size: float
    spread_points: float = 0.0     # median spread in POINTS (sidecar spread_points_median)
    account_currency: str = ""

    @property
    def value_per_point(self) -> float:
        """Account-currency value of a 1.0 price-unit move on ONE FULL LOT."""
        return self.tick_value / self.tick_size

    @property
    def spread_price(self) -> float:
        """One-sided spread cost in the instrument's own PRICE units."""
        return self.spread_points * self.point


def load_instrument_spec(path: str | Path) -> InstrumentSpec:
    """Load a STACK-schema spec sidecar JSON into a frozen InstrumentSpec.

    The sidecar is written by the Phase 6 fetch script from the broker terminal
    (``symbol_info()`` + ``symbol_info_tick()`` + the fetched frame). Field-name
    mapping to InstrumentSpec: trade_tick_size->tick_size, trade_tick_value->
    tick_value, trade_contract_size->contract_size, spread_points_median->
    spread_points.

    Raises:
        FileNotFoundError: if the sidecar path does not exist (names the path).
        ValueError: if a required field is missing or invalid (names the file's
            own key, e.g. ``trade_tick_size``). A JSONDecodeError propagates —
            a malformed sidecar is a hard error, never silently defaulted.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"spec file not found: {path.resolve()}")
    data = json.loads(path.read_text(encoding="utf-8"))

    def _req(key: str):
        """Required sidecar field; missing key -> ValueError naming the key."""
        if key not in data:
            raise ValueError(f"spec {path.name}: missing required field {key}")
        return data[key]

    def _pos(key: str):
        """Required positive-real sidecar field; missing/invalid -> ValueError.

        Mirrors MT5Broker.symbol_risk's zero-refusal: a terminal that has not
        populated specs reports zeros — refuse rather than let a divide-by-zero
        or a nonsense contract size through.
        """
        val = _req(key)
        if isinstance(val, bool) or not isinstance(val, (int, float)) or val <= 0:
            raise ValueError(f"spec {path.name}: invalid {key}")
        return val

    spec_kwargs = {
        "symbol": _req("symbol"),
        "digits": _req("digits"),
        "point": _pos("point"),
        "tick_size": _pos("trade_tick_size"),
        "tick_value": _pos("trade_tick_value"),
        "contract_size": _pos("trade_contract_size"),
        "spread_points": float(data.get("spread_points_median", data.get("spread_points", 0.0))),
        "account_currency": data.get("account_currency", ""),
    }

    symbol = spec_kwargs["symbol"]
    if not isinstance(symbol, str) or not symbol:
        raise ValueError(f"spec {path.name}: invalid symbol")
    digits = spec_kwargs["digits"]
    if isinstance(digits, bool) or not isinstance(digits, int) or digits < 2:
        raise ValueError(f"spec {path.name}: invalid digits")

    return InstrumentSpec(**spec_kwargs)


def base_symbol(symbol: str) -> str:
    """Upper-case symbol with one trailing account-type letter stripped.

    Exness suffixes name the account type, not the instrument: XAUUSDc / XAUUSDm
    are the same gold contract on cent vs standard accounts. A config's [data]
    symbol (EURJPY) and a captured spec's broker symbol (EURJPYc) must compare
    equal for the backtest symbol-identity guard (INST-02) without knowing the
    account type in advance.
    """
    s = symbol.strip().upper()
    if len(s) > 1 and s[-1] in ("C", "M"):
        s = s[:-1]
    return s
