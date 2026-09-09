"""Tests for InstrumentSpec + the STACK spec-sidecar JSON loader (plan 05-01).

Covers (INST-01):
  - load_instrument_spec() maps a STACK-schema sidecar (broker-captured at
    fetch time) onto a frozen InstrumentSpec: trade_tick_size -> tick_size,
    trade_tick_value -> tick_value, trade_contract_size -> contract_size,
    spread_points_median -> spread_points
  - the value_per_point property (account-currency money per 1.0 price-unit
    move on one full lot = tick_value / tick_size, the SAME formula the live
    SymbolRisk risk gate uses)
  - the spread_price property (one-sided spread in the instrument's own price
    units = spread_points * point)
  - missing required sidecar fields raise ValueError naming the missing key
  - zero-valued required fields raise ValueError naming the field (mirrors
    MT5Broker.symbol_risk's zero-refusal: never divide)
  - a nonexistent sidecar path raises FileNotFoundError naming the path
  - base_symbol() strips one trailing account-type letter ('c'/'m') and
    upper-cases, so a config [data] symbol and a broker spec symbol compare
    equal without knowing the account type in advance (INST-02 guard)
"""

import json

import pytest

from trading_bot.data.loader import InstrumentSpec, base_symbol, load_instrument_spec

# STACK.md lines 30-41 sidecar schema: broker symbol EURJPYc on a cent
# account (USC). value_per_point = 0.91 / 0.001 = 910.0 USC per 1.0 price-unit
# move on one lot; spread_price = 6 points x 0.001 = 0.006 price units.
SIDECAR = {
    "symbol": "EURJPYc",
    "account_currency": "USC",
    "digits": 3,
    "point": 0.001,
    "trade_tick_size": 0.001,
    "trade_tick_value": 0.91,
    "trade_contract_size": 1000.0,
    "volume_min": 0.01,
    "volume_step": 0.01,
    "volume_max": 100.0,
    "spread_points_median": 6.0,
}

REQUIRED_FIELDS = [
    "symbol",
    "digits",
    "point",
    "trade_tick_size",
    "trade_tick_value",
    "trade_contract_size",
]


@pytest.fixture
def sidecar_file(tmp_path):
    """A STACK-schema sidecar JSON on disk, as Phase 6's fetch would write it."""
    path = tmp_path / "EURJPYc_M5_broker.spec.json"
    path.write_text(json.dumps(SIDECAR), encoding="utf-8")
    return path


def test_load_instrument_spec_maps_sidecar_fields(sidecar_file):
    spec = load_instrument_spec(sidecar_file)
    assert isinstance(spec, InstrumentSpec)
    assert spec.symbol == "EURJPYc"
    assert spec.digits == 3
    assert spec.point == 0.001
    assert spec.tick_size == 0.001
    assert spec.tick_value == 0.91
    assert spec.contract_size == 1000.0
    assert spec.spread_points == 6.0
    assert spec.account_currency == "USC"


def test_load_instrument_spec_accepts_plain_spread_points_alias(tmp_path):
    body = dict(SIDECAR)
    del body["spread_points_median"]
    body["spread_points"] = 6.0
    path = tmp_path / "EURJPYc.spec.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    assert load_instrument_spec(path).spread_points == 6.0


def test_value_per_point_is_tick_value_over_tick_size(sidecar_file):
    """Money per 1.0 price-unit move per 1.0 lot, in ACCOUNT currency."""
    spec = load_instrument_spec(sidecar_file)
    assert spec.value_per_point == spec.tick_value / spec.tick_size
    assert spec.value_per_point == 910.0


def test_spread_price_is_spread_points_times_point(sidecar_file):
    """One-sided spread in the instrument's own PRICE units."""
    spec = load_instrument_spec(sidecar_file)
    assert spec.spread_price == spec.spread_points * spec.point
    assert spec.spread_price == 0.006


@pytest.mark.parametrize("missing", REQUIRED_FIELDS)
def test_missing_required_field_raises_value_error_naming_key(tmp_path, missing):
    body = {k: v for k, v in SIDECAR.items() if k != missing}
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(ValueError, match="missing required field"):
        load_instrument_spec(path)


@pytest.mark.parametrize(
    "zero_key",
    ["point", "trade_tick_size", "trade_tick_value", "trade_contract_size"],
)
def test_zero_required_field_raises_value_error_naming_key(tmp_path, zero_key):
    """Zero-refusal mirrors MT5Broker.symbol_risk: refuse, never divide."""
    body = dict(SIDECAR)
    body[zero_key] = 0
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(ValueError, match=zero_key):
        load_instrument_spec(path)


def test_missing_spec_file_raises_file_not_found_naming_path(tmp_path):
    missing = tmp_path / "does_not_exist.spec.json"
    with pytest.raises(FileNotFoundError, match="spec file not found"):
        load_instrument_spec(missing)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("EURJPYc", "EURJPY"),
        ("EURJPY", "EURJPY"),
        ("XAUUSDm", "XAUUSD"),
        ("BTCUSDc", "BTCUSD"),
        ("eurjpyc", "EURJPY"),
    ],
)
def test_base_symbol_strips_trailing_account_type_letter(raw, expected):
    assert base_symbol(raw) == expected
