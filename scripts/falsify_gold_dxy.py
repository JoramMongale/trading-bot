"""Falsification battery for the gold DXY macro-regime sentiment gate (quick
task 20260928-gold-dxy-sentiment-gate).

Runs the REAL shared engine (run_backtest via the grid driver's run_config)
over data/processed/XAUUSDc_M5_broker.csv through, in order:

1. COVERAGE / stall check -- the engine must consume the whole sample (the
   candle-reversal lesson: an unfilled pending locks the single slot).
2. 70/30 TRAIN/TEST       -- five PRE-REGISTERED configs; OOS must stay
   positive with t > 2.0 to count as passing.
3. MONTHLY R breakdown    -- closed trades by entry month, exposes
   front-loading (gold's recurring 2025-only artifact).
4. BEST-OF-N NOISE BAR    -- the gated grid is N=6 pre-registered configs; the
   best full-sample |t| is judged against what pure noise produces, with an
   N=39 self-check that must reproduce STATE.md's ~2.37.
5. VERDICT                -- strictly factual closing comparison (DXY-alone).

Research only; nothing here is a live candidate and live/engine.py is
untouched.
"""

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from backtest_gold_dxy import (
    load_m5,
    run_config,
    summarize,
    summarize_leg,
    tstat,
    _r,
)
from trading_bot.backtest.engine import run_backtest
from trading_bot.news.fear_greed import map_to_bars
from trading_bot.news.macro import (
    load_dxy,
    load_tnx,
    is_yield_rising,
    to_gold_bullishness,
)

GOLD = ROOT / "data/processed/XAUUSDc_M5_broker.csv"


def closed_rt(trades):
    """(n, mean R, t) over CLOSED trades (exit_reason != OPEN)."""
    rs = [_r(t) for t in trades if t["exit_reason"] != "OPEN"]
    m, t, n = tstat(rs)
    return n, m, t


# --- noise calibration (stdlib only, VERBATIM from falsify_btc_fng.py) -------


def tail(x):
    """P(Z > x) for Z ~ N(0,1)."""
    return 0.5 * math.erfc(x / math.sqrt(2.0))


def p_noise_best_ge(observed, n):
    """P(the best |t| of n independent N(0,1) draws >= observed)."""
    return 1.0 - (1.0 - 2.0 * tail(observed)) ** n


def median_best_of_n(n):
    """Median of the largest |t| among n independent N(0,1) draws.

    Bisection on P(all n draws have |t| < x) == 0.5.
    """
    lo, hi = 0.0, 8.0
    while hi - lo > 1e-4:
        mid = (lo + hi) / 2.0
        if (1.0 - 2.0 * tail(mid)) ** n > 0.5:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2.0


def _weighted_r(months):
    """Mean R weighted by trade count over a list of (m, t, n) month stats."""
    total_n = sum(s[2] for s in months)
    if not total_n:
        return None
    return sum(s[0] * s[2] for s in months) / total_n


def _monthly_stats(trades):
    """{ym: (m, t, n)} over CLOSED trades grouped by entry month."""
    by_month = {}
    for x in trades:
        if x["exit_reason"] == "OPEN":
            continue
        by_month.setdefault(str(x["entry_time"])[:7], []).append(_r(x))
    return {ym: tstat(rs) for ym, rs in sorted(by_month.items())}


# --- sections ---------------------------------------------------------------


def run_coverage(df, dxy50, dxy200):
    print("\n== 1. COVERAGE / stall check (gold) ==")
    for label, kw in [
        ("both rr1.0 (no dxy)", dict(direction="both", rr=1.0, sentiment=None)),
        ("both rr1.0 dxy w50 b10", dict(direction="both", rr=1.0,
                                        sentiment=dxy50, band=10.0)),
        ("both rr1.0 dxy w200 b10", dict(direction="both", rr=1.0,
                                         sentiment=dxy200, band=10.0)),
    ]:
        trades = run_config(df, **kw)
        closed = [t for t in trades if t["exit_reason"] != "OPEN"]
        if not trades:
            print(f"{label:<22} no trades at all -- STALL?")
            continue
        first = trades[0]["entry_time"]
        last_e = max(t["exit_time"] for t in trades)
        span = 100.0 * len(df.index[: df.index.get_loc(last_e) + 1]) / len(df)
        flag = "  <-- STALL (unfilled pending locks the single slot)" if span < 95.0 else ""
        print(f"{label:<22} n_closed={len(closed):>5}  first_entry={first}  "
              f"last_exit={last_e}  span={span:5.1f}%{flag}")


def run_split(df, dxy50, dxy200):
    cut = int(len(df) * 0.7)
    train, test = df.iloc[:cut], df.iloc[cut:]
    d50_train, d50_test = dxy50.iloc[:cut], dxy50.iloc[cut:]
    d200_train, d200_test = dxy200.iloc[:cut], dxy200.iloc[cut:]
    print(f"\n== 2. 70/30 train/test (gold, cut bar {cut}; OOS pass = TEST R > 0 "
          f"with t > 2.0) ==")
    # (label, train_kw, test_kw)
    configs = [
        ("both rr1.0 (no dxy)",
         dict(direction="both", rr=1.0),
         dict(direction="both", rr=1.0)),
        ("both rr1.0 dxy w50 b5",
         dict(direction="both", rr=1.0, sentiment=d50_train, band=5.0),
         dict(direction="both", rr=1.0, sentiment=d50_test, band=5.0)),
        ("both rr1.0 dxy w200 b5",
         dict(direction="both", rr=1.0, sentiment=d200_train, band=5.0),
         dict(direction="both", rr=1.0, sentiment=d200_test, band=5.0)),
        ("both rr1.0 dxy w50 b10",
         dict(direction="both", rr=1.0, sentiment=d50_train, band=10.0),
         dict(direction="both", rr=1.0, sentiment=d50_test, band=10.0)),
        ("both rr1.0 dxy w200 b10",
         dict(direction="both", rr=1.0, sentiment=d200_train, band=10.0),
         dict(direction="both", rr=1.0, sentiment=d200_test, band=10.0)),
    ]
    results = {}
    for label, kw_train, kw_test in configs:
        summarize(run_config(train, **kw_train), f"{label} train")
        summarize(run_config(test, **kw_test), f"{label} TEST ")
        _, m, t = closed_rt(run_config(test, **kw_test))
        passed = m is not None and m > 0 and t > 2.0
        results[label] = passed
        print(f"    OOS {'PASS' if passed else 'FAIL'}: TEST R {m:+.4f} "
              f"t={t:+.2f} (need R > 0 AND t > 2.0)")
    return results


def run_monthly(df, dxy200):
    print("\n== 3. MONTHLY R breakdown (gold, closed trades by entry month) ==")
    monthly = {}
    for label, kw in [
        ("both rr1.0 (no dxy)", dict(direction="both", rr=1.0, sentiment=None)),
        ("both rr1.0 dxy w200 b10", dict(direction="both", rr=1.0,
                                         sentiment=dxy200, band=10.0)),
    ]:
        trades = run_config(df, **kw)
        stats = _monthly_stats(trades)
        print(f"-- {label} --")
        for ym, (m, t, n) in stats.items():
            print(f"  {ym}  n={n:>4}  R {m:+.3f}  t={t:+.2f}")
        monthly[label] = stats
    return monthly


def run_noise_calibration(df, dxy50, dxy200):
    print("\n== 4. BEST-OF-N NOISE CALIBRATION (gated grid N=6, pre-registered) ==")
    gated = [
        ("both rr1.0 dxy w50 b0", dict(direction="both", rr=1.0, sentiment=dxy50, band=0.0)),
        ("both rr1.0 dxy w50 b5", dict(direction="both", rr=1.0, sentiment=dxy50, band=5.0)),
        ("both rr1.0 dxy w50 b10", dict(direction="both", rr=1.0, sentiment=dxy50, band=10.0)),
        ("both rr1.0 dxy w200 b0", dict(direction="both", rr=1.0, sentiment=dxy200, band=0.0)),
        ("both rr1.0 dxy w200 b5", dict(direction="both", rr=1.0, sentiment=dxy200, band=5.0)),
        ("both rr1.0 dxy w200 b10", dict(direction="both", rr=1.0, sentiment=dxy200, band=10.0)),
    ]
    best_label, best_abs_t = None, 0.0
    for label, kw in gated:
        n, m, t = closed_rt(run_config(df, **kw))
        print(f"  {label:<22} full-sample R {m:+.4f}  t={t:+.2f}  n={n}")
        if t is not None and abs(t) > best_abs_t:
            best_abs_t, best_label = abs(t), label
    print(f"  observed best full-sample |t| across the 6 gated rows = "
          f"{best_abs_t:.2f}  ({best_label})")
    print(f"  P(noise best |t| >= {best_abs_t:.2f} | N=6) = "
          f"{100 * p_noise_best_ge(best_abs_t, 6):.1f}%")
    print(f"  median best |t|, N=6, under pure noise = {median_best_of_n(6):.2f} "
          f"(sanity ~1.60)")
    print(f"  SELF-CHECK: median best |t|, N=39, under pure noise = "
          f"{median_best_of_n(39):.2f} (STATE.md documents ~2.37)")
    return best_label, best_abs_t


def run_verdict(df, dxy50, dxy200, oos, monthly, best_label, best_abs_t):
    print("\n== 5. VERDICT (DXY-alone) ==")
    _, m_ctrl, t_ctrl = closed_rt(run_config(df, direction="both", rr=1.0,
                                             sentiment=None))
    gated_rt = {}
    for label, sent, band in [
        ("both rr1.0 dxy w50 b0", dxy50, 0.0),
        ("both rr1.0 dxy w50 b5", dxy50, 5.0),
        ("both rr1.0 dxy w50 b10", dxy50, 10.0),
        ("both rr1.0 dxy w200 b0", dxy200, 0.0),
        ("both rr1.0 dxy w200 b5", dxy200, 5.0),
        ("both rr1.0 dxy w200 b10", dxy200, 10.0),
    ]:
        n, m, t = closed_rt(run_config(df, direction="both", rr=1.0,
                                       sentiment=sent, band=band))
        gated_rt[label] = (m, t, n)

    best_r_label = max(gated_rt, key=lambda lb: gated_rt[lb][0])
    m_best, t_best, n_best = gated_rt[best_r_label]

    # leg attribution: control vs the best gated row (is the R rise real, not
    # sample shrinkage, and is it the suppressed side that improves?)
    ctrl_trades = run_config(df, direction="both", rr=1.0, sentiment=None)
    best_sent = dxy200 if best_r_label.endswith("w200 b0") else dxy50
    best_band = 0.0 if best_r_label.endswith("b0") else (
        5.0 if best_r_label.endswith("b5") else 10.0)
    best_trades = run_config(df, direction="both", rr=1.0,
                             sentiment=best_sent, band=best_band)

    def leg_rt(trades, side):
        return closed_rt([t for t in trades if t["direction"] == side])

    ctrl_long = leg_rt(ctrl_trades, "long")
    ctrl_short = leg_rt(ctrl_trades, "short")
    best_long = leg_rt(best_trades, "long")
    best_short = leg_rt(best_trades, "short")

    bull = (dxy200 >= 50.0 + 10.0)
    bear = (dxy200 <= 50.0 - 10.0)
    nb, nbr, nneu = int(bull.sum()), int(bear.sum()), int((~(bull | bear)).sum())

    best_p = p_noise_best_ge(best_abs_t, 6)
    med6 = median_best_of_n(6)
    best_oos = oos.get(best_r_label)  # may be None (b0 not pre-registered OOS)

    # front-loading: 2025 vs 2026 weighted R for the control and the best gated
    def yr_split(stats):
        pre = [s for ym, s in stats.items() if ym < "2026-01"]
        post = [s for ym, s in stats.items() if ym >= "2026-01"]
        return _weighted_r(pre), _weighted_r(post)

    c25, c26 = yr_split(monthly["both rr1.0 (no dxy)"])
    best_stats = _monthly_stats(best_trades)
    b25, b26 = yr_split(best_stats)
    gated_front_loaded = b26 is None or b26 <= 0.0

    improves = m_best > m_ctrl and abs(t_best) > abs(t_ctrl)

    print(f"  control both (no dxy): R {m_ctrl:+.4f} t={t_ctrl:+.2f} | best "
          f"gated row ({best_r_label}): R {m_best:+.4f} t={t_best:+.2f} "
          f"(n={n_best})")
    print(f"  -> DXY gate {'raises' if improves else 'does not raise'} BOTH "
          f"the both-book avg R ({m_ctrl:+.4f} -> {m_best:+.4f}) and |t| "
          f"({abs(t_ctrl):.2f} -> {abs(t_best):.2f})")
    print(f"  leg attribution (control -> best gated): "
          f"long n={ctrl_long[0]} R {ctrl_long[1]:+.4f} t={ctrl_long[2]:+.2f} -> "
          f"n={best_long[0]} R {best_long[1]:+.4f} t={best_long[2]:+.2f} | "
          f"short n={ctrl_short[0]} R {ctrl_short[1]:+.4f} t={ctrl_short[2]:+.2f} -> "
          f"n={best_short[0]} R {best_short[1]:+.4f} t={best_short[2]:+.2f}")
    print(f"  direction-split (w200 band=10 bar mix over span): bull {nb} / "
          f"bear {nbr} / neutral {nneu} bars (gate trades with the regime)")
    print(f"  best gated |t|={best_abs_t:.2f}; best-of-6 noise median is "
          f"{med6:.2f}; P(noise best >= observed) = {100 * best_p:.1f}%; "
          f"all-time reference |t|=2.46 is beaten by noise 42% of the time at N=39")
    print(f"  OOS t>2.0 per pre-registered config: "
          + ", ".join(f"{label} {'PASS' if ok else 'FAIL'}"
                      for label, ok in sorted(oos.items())))
    if best_oos is None:
        print(f"  NOTE: best full-sample row ({best_r_label}) was NOT in the "
              f"pre-registered OOS set (band 0 excluded); its OOS stability is "
              f"unverified by pre-registration")
    print(f"  monthly front-loading: control 2025 weighted R {c25:+.3f} vs 2026 "
          f"{c26:+.3f} | best gated ({best_r_label}) 2025 {b25:+.3f} vs 2026 "
          f"{b26:+.3f} -> best gated "
          f"{'front-loaded (2026 not positive)' if gated_front_loaded else 'not front-loaded'}")

    conds = {
        "raises both control R AND |t|": improves,
        "OOS t>2.0": (best_oos is True) or any(ok for label, ok in oos.items()
                                                if label.startswith("both rr1.0 dxy")),
        "not front-loaded": not gated_front_loaded,
        "best-of-N above noise": best_p < 0.05,
    }
    print("  conditions: " + " | ".join(
        f"{name} {'HELD' if held else 'FAILED'}" for name, held in conds.items()))
    clears = all(conds.values())
    if clears:
        print("VERDICT: DXY gate clears the bar only if ALL of [raises both "
              "control R AND |t|, OOS t>2.0, not front-loaded, best-of-N above "
              "noise] hold -- all four held")
    else:
        print("VERDICT: DXY gate clears no bar (conditions must ALL hold: "
              "[raises both control R AND |t|, OOS t>2.0, not front-loaded, "
              "best-of-N above noise])")
    return clears, conds


# --- composite (DXY + 10Y "macro headwind" no-trade-longs gate) ---------------


def make_macro_headwind_veto(dxy_strong, yield_rising):
    """Suppress LONG setups when BOTH DXY strong AND yields rising.

    ``dxy_strong`` and ``yield_rising`` are bool/NaN Series aligned to the FULL
    df.index (via map_to_bars, shift(1)+ffill no-lookahead). The closure looks
    up by ``bar.name``, so the SAME veto serves any frame (no length constraint
    on setup_veto). A LONG setup always has ``entry > sl`` (entry = resistance,
    sl = support - sl_buffer); ``entry <= sl`` means short/degenerate -> never
    suppress. A NaN regime (before warm-up) is falsy -> fail-open (no suppress).
    """
    def veto(bar, entry, sl, tp):
        if entry <= sl:                 # short (or degenerate) setup
            return None
        if dxy_strong.loc[bar.name] and yield_rising.loc[bar.name]:
            return "macro_headwind_long"
        return None
    return veto


def _run_composite(df, veto):
    counts = {"suppressed": 0}

    def on_event(ev):
        if (ev.get("event") == "setup_skipped"
                and ev.get("reason") == "macro_headwind_long"):
            counts["suppressed"] += 1

    trades = run_backtest(df, direction="both", rr_multiple=1.0,
                          setup_veto=veto, on_event=on_event)
    return trades, counts["suppressed"]


def _monthly_long(trades):
    """{ym: (m, t, n)} over CLOSED LONG trades grouped by entry month."""
    by_month = {}
    for x in trades:
        if x["exit_reason"] == "OPEN" or x["direction"] != "long":
            continue
        by_month.setdefault(str(x["entry_time"])[:7], []).append(_r(x))
    return {ym: tstat(rs) for ym, rs in sorted(by_month.items())}


def run_composite_battery(df, dxy, tnx):
    print("\n== 6. COMPOSITE DXY+10Y 'macro headwind' no-trade-longs gate "
          "(setup_veto seam) ==")
    print(f"^TNX daily series: {len(tnx)} days, "
          f"{tnx.index[0].date()} -> {tnx.index[-1].date()} (mapped shift(1)+ffill)")
    cfgs = [
        ("both rr1.0 comp d50 t50 b5", 50, 50, 5.0),
        ("both rr1.0 comp d50 t50 b10", 50, 50, 10.0),
        ("both rr1.0 comp d200 t200 b5", 200, 200, 5.0),
        ("both rr1.0 comp d200 t200 b10", 200, 200, 10.0),
    ]

    rows = {}
    for label, dma, tma, band in cfgs:
        dxy_strong = map_to_bars(
            to_gold_bullishness(dxy, dma).map(lambda v: v <= 50.0 - band), df.index)
        yield_rising = map_to_bars(is_yield_rising(tnx, tma), df.index)
        veto = make_macro_headwind_veto(dxy_strong, yield_rising)
        trades, suppressed = _run_composite(df, veto)
        rows[label] = (trades, suppressed)

    ctrl = run_config(df, direction="both", rr=1.0, sentiment=None)

    # a. coverage / stall
    print("\n  -- a. COVERAGE / stall --")
    labels = [lb for lb, _, _, _ in cfgs]
    spans = {}
    for label, trades in [("both rr1.0 (no dxy)", ctrl)] + \
            [(lb, rows[lb][0]) for lb in labels]:
        closed = [t for t in trades if t["exit_reason"] != "OPEN"]
        last_e = max(t["exit_time"] for t in trades)
        span = 100.0 * len(df.index[: df.index.get_loc(last_e) + 1]) / len(df)
        spans[label] = span
        flag = "  <-- STALL" if span < 95.0 else ""
        print(f"    {label:<26} n_closed={len(closed):>5} span={span:5.1f}%{flag}")
    composite_spans = [spans[lb] for lb in labels]
    coverage_ok = min(composite_spans) >= 95.0

    # b. long-leg R/t + leg decompositions + suppressed counts
    print("\n  -- b. LONG-LEG R/t vs control (control long R +0.1260 t=+2.27) --")
    ctrl_long = [t for t in ctrl if t["direction"] == "long"]
    cn, cm, ct = closed_rt(ctrl_long)
    print(f"    control long leg: n={cn} R {cm:+.4f} t={ct:+.2f}")
    long_leg = {}
    for label, _dma, _tma, _band in cfgs:
        trades, suppressed = rows[label]
        summarize(trades, f"    {label}")
        summarize_leg(trades, "long", f"      leg long  ({label})")
        summarize_leg(trades, "short", f"      leg short ({label})")
        n, m, t = closed_rt([x for x in trades if x["direction"] == "long"])
        long_leg[label] = (n, m, t, suppressed)
        print(f"      suppressed long setups: {suppressed} | long leg R {m:+.4f} "
              f"t={t:+.2f} (n={n})")

    # best composite config by long-leg avg R
    best_cfg = max(long_leg, key=lambda lb: long_leg[lb][1])
    bn, bm, bt, bsup = long_leg[best_cfg]

    # c. monthly long-leg R for the best composite config
    print(f"\n  -- c. MONTHLY long-leg R (best composite: {best_cfg}) --")
    ml = _monthly_long(rows[best_cfg][0])
    for ym, (m, t, n) in ml.items():
        print(f"    {ym}  n={n:>4}  R {m:+.3f}  t={t:+.2f}")
    w25 = _weighted_r([s for ym, s in ml.items() if ym < "2026-01"])
    w26 = _weighted_r([s for ym, s in ml.items() if ym >= "2026-01"])
    front_loaded = w26 is None or w26 <= 0.0
    print(f"    2025 weighted R {w25:+.3f} vs 2026 {w26:+.3f} -> "
          f"{'front-loaded (2026 not positive)' if front_loaded else 'not front-loaded'}")

    # d. best-of-N (N=4) on the long-leg |t|
    print("\n  -- d. BEST-OF-N (composite N=4, long-leg |t|) --")
    best_t_label = max(long_leg, key=lambda lb: abs(long_leg[lb][2]))
    best_abs = abs(long_leg[best_t_label][2])
    p4 = p_noise_best_ge(best_abs, 4)
    print(f"    observed best long-leg |t| = {best_abs:.2f} ({best_t_label})")
    print(f"    P(noise best |t| >= {best_abs:.2f} | N=4) = {100 * p4:.1f}%")
    print(f"    median best |t|, N=4, under pure noise = {median_best_of_n(4):.2f}")
    print(f"    SELF-CHECK: median best |t|, N=39 = {median_best_of_n(39):.2f} "
          f"(STATE.md ~2.37)")

    # composite verdict
    raises = bm > cm and abs(bt) > abs(ct)
    conds = {
        "raises long-leg avg R AND |t| vs control": raises,
        "coverage ~100% (no stall)": coverage_ok,
        "not front-loaded (2026 long-leg positive)": not front_loaded,
        "best-of-4 above noise": p4 < 0.05,
    }
    print("\n  -- COMPOSITE VERDICT --")
    print("    conditions: " + " | ".join(
        f"{k} {'HELD' if v else 'FAILED'}" for k, v in conds.items()))
    if all(conds.values()):
        print("    VERDICT: composite no-trade-longs gate clears the bar only if "
              "ALL of [raises long-leg avg R AND |t| vs control, coverage ~100%, "
              "not front-loaded, best-of-4 above noise] hold -- all four held")
    else:
        print("    VERDICT: composite no-trade-longs gate clears no bar "
              "(conditions must ALL hold: [raises long-leg avg R AND |t| vs "
              "control, coverage ~100%, not front-loaded, best-of-4 above noise])")
    return all(conds.values())


def main():
    if not GOLD.exists():
        raise SystemExit(f"missing gold data file: {GOLD}")
    df = load_m5(GOLD)
    dxy = load_dxy(cache_path=ROOT / "data/processed/dxy.json")
    dxy50 = map_to_bars(to_gold_bullishness(dxy, 50), df.index)
    dxy200 = map_to_bars(to_gold_bullishness(dxy, 200), df.index)
    print(f"== FALSIFY GOLD DXY regime gate ({GOLD.name}, {len(df)} bars, "
          f"{df.index[0]} -> {df.index[-1]}) ==")
    run_coverage(df, dxy50, dxy200)
    oos = run_split(df, dxy50, dxy200)
    monthly = run_monthly(df, dxy200)
    best_label, best_abs_t = run_noise_calibration(df, dxy50, dxy200)
    clears, _ = run_verdict(df, dxy50, dxy200, oos, monthly, best_label, best_abs_t)
    # Composite runs only when the DXY-alone gate failed to clear the bar.
    if clears:
        print("\nDXY-alone gate cleared the bar; composite no-trade-longs gate "
              "not built.")
    else:
        tnx = load_tnx(cache_path=ROOT / "data/processed/tnx.json")
        run_composite_battery(df, dxy, tnx)


if __name__ == "__main__":
    main()
