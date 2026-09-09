"""Tests for src/trading_bot/strategy/swings.py — fractal swing detection (STRAT-01).

Covers: rising peak, equal-high plateau (last bar wins), symmetric low,
frame-start NaN guards, the no-lookahead confirmation shift, extra-column
preservation, and the strategy/ import-purity rule (pandas/numpy only).
"""

from pathlib import Path

import numpy as np
import pandas as pd

from trading_bot.strategy.swings import detect_swings


def make_frame(highs=None, lows=None, closes=None, opens=None, **extra):
    """Synthetic OHLC frame. Missing columns default to the highs (price structure)."""
    n = len(highs if highs is not None else lows)
    data = {
        "open": opens if opens is not None else (highs if highs is not None else [0.0] * n),
        "high": highs if highs is not None else [0.0] * n,
        "low": lows if lows is not None else [0.0] * n,
        "close": closes if closes is not None else (highs if highs is not None else [0.0] * n),
    }
    data.update(extra)
    return pd.DataFrame(data)


def test_rising_peak_detects_swing_high_at_peak():
    out = detect_swings(make_frame(highs=[1.0, 2.0, 3.0, 4.0, 3.0, 2.0, 1.0]))
    assert out["swing_high_raw"].iloc[3] == 4.0
    # exactly one raw swing high in this series
    assert out["swing_high_raw"].notna().sum() == 1


def test_confirmation_shift_proves_no_lookahead():
    out = detect_swings(make_frame(highs=[1.0, 2.0, 3.0, 4.0, 3.0, 2.0, 1.0]))
    # swing_high is NaN at indices 0-4 (raw swing at 3 not yet confirmed)...
    assert out["swing_high"].iloc[0:5].isna().all()
    # ...equals 4.0 at index 5, exactly `right` bars after the raw swing
    assert out["swing_high"].iloc[5] == 4.0
    # and is NaN again at index 6
    assert np.isnan(out["swing_high"].iloc[6])


def test_plateau_last_equal_high_bar_is_the_swing():
    out = detect_swings(make_frame(highs=[1.0, 2.0, 2.0, 1.0, 0.5]))
    # first plateau bar (index 1) is NOT a swing; the LAST equal-high bar (index 2) IS
    assert np.isnan(out["swing_high_raw"].iloc[1])
    assert out["swing_high_raw"].iloc[2] == 2.0
    # confirmed two bars later (index 4)
    assert out["swing_high"].iloc[4] == 2.0


def test_symmetric_swing_low():
    out = detect_swings(
        make_frame(highs=[6.0, 6.0, 6.0, 6.0, 6.0], lows=[5.0, 4.0, 3.0, 4.0, 5.0])
    )
    assert out["swing_low_raw"].iloc[2] == 3.0
    assert out["swing_low"].iloc[4] == 3.0
    assert out["swing_low"].notna().sum() == 1


def test_frame_start_first_left_bars_cannot_be_swings():
    out = detect_swings(
        make_frame(
            highs=[1.0, 2.0, 3.0, 4.0, 3.0, 2.0, 1.0],
            lows=[0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5],
        )
    )
    # first `left` (2) bars have no completed left window -> NaN, never swings
    assert out["swing_high_raw"].iloc[0:2].isna().all()
    assert out["swing_low_raw"].iloc[0:2].isna().all()


def test_extra_columns_pass_through_unchanged():
    df = make_frame(
        highs=[1.0, 2.0, 3.0, 4.0, 3.0, 2.0, 1.0],
        lows=[0.5] * 7,
        closes=[0.9, 1.9, 2.9, 3.9, 2.9, 1.9, 0.9],
        opens=[1.0] * 7,
        volume=[100, 200, 150, 300, 250, 180, 90],
    )
    out = detect_swings(df)
    assert "volume" in out.columns
    assert out["volume"].tolist() == [100, 200, 150, 300, 250, 180, 90]
    # pure function: input frame is never mutated
    assert "swing_high" not in df.columns


def test_strategy_modules_import_only_pandas_and_numpy():
    import ast

    strategy_dir = Path(__file__).resolve().parents[1] / "src" / "trading_bot" / "strategy"
    allowlist = {"pandas", "numpy"}

    modules = sorted(strategy_dir.glob("*.py"))
    assert modules, f"no strategy modules found in {strategy_dir}"

    for path in modules:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] in allowlist, (
                        f"{path.name} must import only pandas/numpy, got 'import {alias.name}'"
                    )
            elif isinstance(node, ast.ImportFrom):
                assert node.module is not None, f"{path.name} contains a relative import"
                assert node.module.split(".")[0] in allowlist, (
                    f"{path.name} must import only pandas/numpy, got 'from {node.module}'"
                )
