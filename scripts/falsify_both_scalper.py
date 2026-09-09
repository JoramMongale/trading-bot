"""Falsification battery for the both-direction single-slot M5 gold "scalper"
variant of the swing S/R breakout (quick task 20260909-gold-both-scalper).

Runs the REAL shared engine (run_backtest via the grid driver's run_config)
over data/processed/XAUUSDc_M5_broker.csv through, in order:

1. COVERAGE / stall check -- the engine must consume the whole sample (the
   candle-reversal lesson: an unfilled pending locks the single slot).
2. 70/30 TRAIN/TEST       -- four PRE-REGISTERED headline scalp exits; OOS
   must stay positive with t > 2.0 to count as passing.
3. MONTHLY R breakdown    -- closed trades by entry month, exposes
   front-loading (2025 is the flattering half; a 2026 collapse IS the finding).
4. BEST-OF-N NOISE BAR    -- the scalp grid is N=8 pre-registered configs; the
   best full-sample |t| is judged against what pure noise produces, with an
   N=39 self-check that must reproduce STATE.md's ~2.37.
5. VERDICT                -- strictly factual closing comparison.

Research only; nothing here is a live candidate and live/engine.py is
untouched.
"""

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from backtest_both_scalper import load_m5, run_config, summarize, tstat

GOLD = ROOT / "data/processed/XAUUSDc_M5_broker.csv"


# --- per-trade R, sign-corrected per the record's own direction -------------


def _r(trade):
    """Matches the driver's per-trade r_multiple formula."""
    if trade["direction"] == "long":
        risk = trade["entry"] - trade["sl"]
        return (trade["exit_price"] - trade["entry"]) / risk if risk else 0.0
    risk = trade["sl"] - trade["entry"]
    return (trade["entry"] - trade["exit_price"]) / risk if risk else 0.0


def closed_rt(trades):
    """(n, mean R, t) over CLOSED trades (exit_reason != OPEN)."""
    rs = [_r(t) for t in trades if t["exit_reason"] != "OPEN"]
    m, t, n = tstat(rs)
    return n, m, t


# --- noise calibration (stdlib only) ----------------------------------------


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


# --- sections ---------------------------------------------------------------


def run_coverage(df):
    print("\n== 1. COVERAGE / stall check (gold) ==")
    for label, kw in [
        ("both rr1.0", dict(direction="both", rr=1.0)),
        ("both rr0.5 hold36", dict(direction="both", rr=0.5, max_hold_bars=36)),
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


def run_split(df):
    cut = int(len(df) * 0.7)
    train, test = df.iloc[:cut], df.iloc[cut:]
    print(f"\n== 2. 70/30 train/test (gold, cut bar {cut}; OOS pass = TEST R > 0 "
          f"with t > 2.0) ==")
    configs = [
        ("both rr1.0", dict(direction="both", rr=1.0)),
        ("both rr0.5", dict(direction="both", rr=0.5)),
        ("both rr0.5 tpffill", dict(direction="both", rr=0.5, tp_from_fill=True)),
        ("both rr1.0 hold36", dict(direction="both", rr=1.0, max_hold_bars=36)),
    ]
    results = {}
    for label, kw in configs:
        summarize(run_config(train, **kw), f"{label} train")
        summarize(run_config(test, **kw), f"{label} TEST ")
        _, m, t = closed_rt(run_config(test, **kw))
        passed = m is not None and m > 0 and t > 2.0
        results[label] = passed
        print(f"    OOS {'PASS' if passed else 'FAIL'}: TEST R {m:+.4f} "
              f"t={t:+.2f} (need R > 0 AND t > 2.0)")
    return results


def run_monthly(df):
    print("\n== 3. MONTHLY R breakdown (gold, closed trades by entry month) ==")
    monthly = {}
    for label, kw in [
        ("both rr1.0", dict(direction="both", rr=1.0)),
        ("both rr0.5", dict(direction="both", rr=0.5)),
    ]:
        trades = run_config(df, **kw)
        by_month = {}
        for x in trades:
            if x["exit_reason"] == "OPEN":
                continue
            by_month.setdefault(str(x["entry_time"])[:7], []).append(_r(x))
        print(f"-- {label} --")
        summary = {}
        for ym in sorted(by_month):
            m, t, n = tstat(by_month[ym])
            summary[ym] = (m, t, n)
            print(f"  {ym}  n={n:>4}  R {m:+.3f}  t={t:+.2f}")
        monthly[label] = summary
    return monthly


def run_noise_calibration(df):
    print("\n== 4. BEST-OF-N NOISE CALIBRATION (scalp grid N=8, pre-registered) ==")
    scalp = [
        ("both rr0.5", dict(direction="both", rr=0.5)),
        ("both rr0.75", dict(direction="both", rr=0.75)),
        ("both rr0.5 tpffill", dict(direction="both", rr=0.5, tp_from_fill=True)),
        ("both rr1.0 tpffill", dict(direction="both", rr=1.0, tp_from_fill=True)),
        ("both rr1.0 hold12", dict(direction="both", rr=1.0, max_hold_bars=12)),
        ("both rr1.0 hold36", dict(direction="both", rr=1.0, max_hold_bars=36)),
        ("both rr0.5 hold12", dict(direction="both", rr=0.5, max_hold_bars=12)),
        ("both rr0.5 hold36", dict(direction="both", rr=0.5, max_hold_bars=36)),
    ]
    best_label, best_abs_t = None, 0.0
    for label, kw in scalp:
        n, m, t = closed_rt(run_config(df, **kw))
        print(f"  {label:<20} full-sample R {m:+.4f}  t={t:+.2f}  n={n}")
        if t is not None and abs(t) > best_abs_t:
            best_abs_t, best_label = abs(t), label
    print(f"  observed best full-sample |t| across the 8 scalp rows = "
          f"{best_abs_t:.2f}  ({best_label})")
    print(f"  P(noise best |t| >= {best_abs_t:.2f} | N=8) = "
          f"{100 * p_noise_best_ge(best_abs_t, 8):.1f}%")
    print(f"  median best |t|, N=8, under pure noise = {median_best_of_n(8):.2f} "
          f"(sanity ~1.74)")
    print(f"  SELF-CHECK: median best |t|, N=39, under pure noise = "
          f"{median_best_of_n(39):.2f} (STATE.md documents ~2.37)")
    return best_label, best_abs_t


def _weighted_r(months):
    """Mean R weighted by trade count over a list of (m, t, n) month stats."""
    total_n = sum(s[2] for s in months)
    if not total_n:
        return None
    return sum(s[0] * s[2] for s in months) / total_n


def run_verdict(df, oos, monthly, best_label, best_abs_t):
    print("\n== 5. VERDICT ==")
    _, m_long, t_long = closed_rt(run_config(df, direction="long", rr=1.0))
    _, m_short, t_short = closed_rt(run_config(df, direction="short", rr=1.0))
    _, m_both, t_both = closed_rt(run_config(df, direction="both", rr=1.0))
    both_trades = run_config(df, direction="both", rr=1.0)
    legs = {"long": [], "short": []}
    for x in both_trades:
        if x["exit_reason"] != "OPEN":
            legs[x["direction"]].append(_r(x))
    leg_stats = {}
    for side, rs in legs.items():
        m, t, n = tstat(rs)
        leg_stats[side] = (m, t, n)

    best_p = p_noise_best_ge(best_abs_t, 8)
    best_oos = oos.get(best_label)
    med8 = median_best_of_n(8)

    # Front-loading: closed trades by entry year on the both rr1.0 book.
    pre = [s for ym, s in monthly["both rr1.0"].items() if ym < "2026-01"]
    post = [s for ym, s in monthly["both rr1.0"].items() if ym >= "2026-01"]
    r25 = _weighted_r(pre)
    r26 = _weighted_r(post)
    front_loaded = r26 is None or r26 <= 0.0

    print(f"  controls (gold full sample, rr=1.0): long-only R {m_long:+.4f} "
          f"t={t_long:+.2f} | short-only R {m_short:+.4f} t={t_short:+.2f} | "
          f"both-book R {m_both:+.4f} t={t_both:+.2f}")
    print(f"  both rr1.0 legs: long R {leg_stats['long'][0]:+.4f} "
          f"t={leg_stats['long'][1]:+.2f} (n={leg_stats['long'][2]}) | short "
          f"R {leg_stats['short'][0]:+.4f} t={leg_stats['short'][1]:+.2f} "
          f"(n={leg_stats['short'][2]})")
    print(f"  (20260822 drift-asymmetry reference: shorts -0.059R vs longs "
          f"+0.135R on histdata; gold's +54% up-drift is why the short mirror "
          f"trails)")
    print(f"  best scalp config: {best_label} |t|={best_abs_t:.2f}; best-of-8 "
          f"noise median is {med8:.2f}; P(noise best >= observed) = "
          f"{100 * best_p:.1f}%; all-time reference |t|=2.46 is beaten by "
          f"noise 42% of the time at N=39")
    print(f"  OOS t>2.0 per pre-registered config: "
          + ", ".join(f"{label} {'PASS' if ok else 'FAIL'}"
                      for label, ok in sorted(oos.items())))
    if best_oos is not None:
        print(f"  -> the full-sample best scalp config ({best_label}) OOS: "
              f"{'PASS' if best_oos else 'FAIL'}")
    else:
        print(f"  -> the full-sample best scalp config ({best_label}) was not "
              f"in the pre-registered train/test set")
    print(f"  monthly front-loading (both rr1.0): 2025 months weighted R "
          f"{r25:+.3f} vs 2026 months {r26:+.3f} -> "
          f"{'front-loaded (2026 collapsed)' if front_loaded else 'not '
          f'front-loaded'}")

    conds = []
    conds.append(f"OOS t>2.0 {'HELD' if (best_oos is True) else 'FAILED'}")
    conds.append(f"not front-loaded {'HELD' if not front_loaded else 'FAILED'}"
                 )
    conds.append(f"best-of-N above noise {'HELD' if best_p < 0.05 else 'FAILED'}"
                 )
    print(f"  conditions: {conds[0]} | {conds[1]} | {conds[2]}")
    clears = best_oos is True and not front_loaded and best_p < 0.05
    if clears:
        print("VERDICT: clears the bar only if ALL of [OOS t>2.0, not "
              "front-loaded, best-of-N above noise] hold -- all three held")
    else:
        print("VERDICT: clears no bar (conditions must ALL hold: [OOS t>2.0, "
              "not front-loaded, best-of-N above noise])")


def main():
    if not GOLD.exists():
        raise SystemExit(f"missing gold data file: {GOLD}")
    df = load_m5(GOLD)
    print(f"== FALSIFY both-direction scalper (gold {GOLD.name}, "
          f"{len(df)} bars, {df.index[0]} -> {df.index[-1]}) ==")
    run_coverage(df)
    oos = run_split(df)
    monthly = run_monthly(df)
    best_label, best_abs_t = run_noise_calibration(df)
    run_verdict(df, oos, monthly, best_label, best_abs_t)


if __name__ == "__main__":
    main()
