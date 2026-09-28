"""Falsification battery for the BTC Fear & Greed sentiment direction filter
(quick task 20260928-btc-fear-greed).

Runs the REAL shared engine (run_backtest via the grid driver's run_config)
over data/processed/BTCUSDc_M5_broker.csv through, in order:

1. COVERAGE / stall check -- the engine must consume the whole sample (the
   candle-reversal lesson: an unfilled pending locks the single slot).
2. 70/30 TRAIN/TEST       -- four PRE-REGISTERED configs; OOS must stay
   positive with t > 2.0 to count as passing.
3. MONTHLY R breakdown    -- closed trades by entry month, exposes
   front-loading (BTC is a known losing machinery test).
4. BEST-OF-N NOISE BAR    -- the gated grid is N=5 pre-registered configs; the
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

from backtest_btc_fng import load_m5, run_config, summarize, tstat, _r
from trading_bot.news.fear_greed import load_fear_greed, map_to_bars

BTC = ROOT / "data/processed/BTCUSDc_M5_broker.csv"


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


def _weighted_r(months):
    """Mean R weighted by trade count over a list of (m, t, n) month stats."""
    total_n = sum(s[2] for s in months)
    if not total_n:
        return None
    return sum(s[0] * s[2] for s in months) / total_n


# --- sections ---------------------------------------------------------------


def run_coverage(df, sent):
    print("\n== 1. COVERAGE / stall check (BTC) ==")
    for label, kw in [
        ("both rr1.0 (no fng)", dict(direction="both", rr=1.0, sentiment=None)),
        ("both rr1.0 fng b10", dict(direction="both", rr=1.0, sentiment=sent,
                                    band=10.0)),
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


def run_split(df, sent):
    cut = int(len(df) * 0.7)
    train, test = df.iloc[:cut], df.iloc[cut:]
    s_train, s_test = sent.iloc[:cut], sent.iloc[cut:]
    print(f"\n== 2. 70/30 train/test (BTC, cut bar {cut}; OOS pass = TEST R > 0 "
          f"with t > 2.0) ==")
    results = {}
    for label, band in [
        ("both rr1.0 (no fng)", None),
        ("both rr1.0 fng b10", 10.0),
        ("both rr1.0 fng b15", 15.0),
        ("both rr1.0 fng b20", 20.0),
    ]:
        kw_train = (dict(direction="both", rr=1.0) if band is None
                    else dict(direction="both", rr=1.0, sentiment=s_train, band=band))
        kw_test = (dict(direction="both", rr=1.0) if band is None
                   else dict(direction="both", rr=1.0, sentiment=s_test, band=band))
        summarize(run_config(train, **kw_train), f"{label} train")
        summarize(run_config(test, **kw_test), f"{label} TEST ")
        _, m, t = closed_rt(run_config(test, **kw_test))
        passed = m is not None and m > 0 and t > 2.0
        results[label] = passed
        print(f"    OOS {'PASS' if passed else 'FAIL'}: TEST R {m:+.4f} "
              f"t={t:+.2f} (need R > 0 AND t > 2.0)")
    return results


def run_monthly(df, sent):
    print("\n== 3. MONTHLY R breakdown (BTC, closed trades by entry month) ==")
    monthly = {}
    for label, kw in [
        ("both rr1.0 (no fng)", dict(direction="both", rr=1.0, sentiment=None)),
        ("both rr1.0 fng b10", dict(direction="both", rr=1.0, sentiment=sent,
                                    band=10.0)),
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


def run_noise_calibration(df, sent):
    print("\n== 4. BEST-OF-N NOISE CALIBRATION (gated grid N=5, pre-registered) ==")
    gated = [
        ("both rr1.0 fng b5", dict(direction="both", rr=1.0, sentiment=sent, band=5.0)),
        ("both rr1.0 fng b10", dict(direction="both", rr=1.0, sentiment=sent, band=10.0)),
        ("both rr1.0 fng b15", dict(direction="both", rr=1.0, sentiment=sent, band=15.0)),
        ("both rr1.0 fng b20", dict(direction="both", rr=1.0, sentiment=sent, band=20.0)),
        ("both rr1.0 fng b25", dict(direction="both", rr=1.0, sentiment=sent, band=25.0)),
    ]
    best_label, best_abs_t = None, 0.0
    for label, kw in gated:
        n, m, t = closed_rt(run_config(df, **kw))
        print(f"  {label:<20} full-sample R {m:+.4f}  t={t:+.2f}  n={n}")
        if t is not None and abs(t) > best_abs_t:
            best_abs_t, best_label = abs(t), label
    print(f"  observed best full-sample |t| across the 5 gated rows = "
          f"{best_abs_t:.2f}  ({best_label})")
    print(f"  P(noise best |t| >= {best_abs_t:.2f} | N=5) = "
          f"{100 * p_noise_best_ge(best_abs_t, 5):.1f}%")
    print(f"  median best |t|, N=5, under pure noise = {median_best_of_n(5):.2f} "
          f"(sanity ~1.56)")
    print(f"  SELF-CHECK: median best |t|, N=39, under pure noise = "
          f"{median_best_of_n(39):.2f} (STATE.md documents ~2.37)")
    return best_label, best_abs_t


def run_verdict(df, sent, oos, monthly, best_label, best_abs_t):
    print("\n== 5. VERDICT ==")
    bands = [5.0, 10.0, 15.0, 20.0, 25.0]
    _, m_ctrl, t_ctrl = closed_rt(run_config(df, direction="both", rr=1.0,
                                             sentiment=None))
    gated_rt = {}
    for band in bands:
        label = f"both rr1.0 fng b{int(band)}"
        n, m, t = closed_rt(run_config(df, direction="both", rr=1.0,
                                       sentiment=sent, band=band))
        gated_rt[label] = (m, t, n)
    best_r_label = max(gated_rt, key=lambda lb: gated_rt[lb][0])
    m_best_r, t_best_r, n_best_r = gated_rt[best_r_label]

    # direction-split sanity: sentiment mix over the BTC span + leg counts
    bull = (sent >= 50.0 + 10.0)
    bear = (sent <= 50.0 - 10.0)
    nb, nbr, nneu = int(bull.sum()), int(bear.sum()), int((~(bull | bear)).sum())
    ctrl_trades = run_config(df, direction="both", rr=1.0, sentiment=None)
    g10_trades = run_config(df, direction="both", rr=1.0, sentiment=sent, band=10.0)
    ctrl_long = sum(1 for t in ctrl_trades if t["exit_reason"] != "OPEN"
                    and t["direction"] == "long")
    ctrl_short = sum(1 for t in ctrl_trades if t["exit_reason"] != "OPEN"
                     and t["direction"] == "short")
    g10_long = sum(1 for t in g10_trades if t["exit_reason"] != "OPEN"
                   and t["direction"] == "long")
    g10_short = sum(1 for t in g10_trades if t["exit_reason"] != "OPEN"
                    and t["direction"] == "short")

    best_p = p_noise_best_ge(best_abs_t, 5)
    med5 = median_best_of_n(5)
    best_oos = oos.get(best_label)

    pre = [s for ym, s in monthly["both rr1.0 (no fng)"].items() if ym < "2026-01"]
    post = [s for ym, s in monthly["both rr1.0 (no fng)"].items() if ym >= "2026-01"]
    r25 = _weighted_r(pre)
    r26 = _weighted_r(post)
    front_loaded = r26 is None or r26 <= 0.0

    improves_control = m_best_r > m_ctrl

    print(f"  control both (no fng): R {m_ctrl:+.4f} t={t_ctrl:+.2f} | best "
          f"gated row ({best_r_label}): R {m_best_r:+.4f} t={t_best_r:+.2f} "
          f"(n={n_best_r})")
    print(f"  -> sentiment filter {'improves' if improves_control else 'does not improve'} "
          f"the both control (R {m_ctrl:+.4f} -> {m_best_r:+.4f}, still "
          f"{'negative' if m_best_r < 0 else 'non-negative'})")
    print(f"  direction-split sanity: sentiment mix over span = bull {nb} / "
          f"bear {nbr} / neutral {nneu} bars")
    print(f"    control legs: long n={ctrl_long} short n={ctrl_short} | b10 gated "
          f"legs: long n={g10_long} short n={g10_short}")
    print(f"    -> gate {'suppresses the wrong side (longs cut on a bearish span)'
                      if g10_long < ctrl_long and g10_short > ctrl_short
                      else 'does not visibly suppress the wrong side'}")
    print(f"  best gated |t|={best_abs_t:.2f}; best-of-5 noise median is "
          f"{med5:.2f}; P(noise best >= observed) = {100 * best_p:.1f}%; "
          f"all-time reference |t|=2.46 is beaten by noise 42% of the time at N=39")
    print(f"  OOS t>2.0 per pre-registered config: "
          + ", ".join(f"{label} {'PASS' if ok else 'FAIL'}"
                      for label, ok in sorted(oos.items())))
    print(f"  monthly front-loading (both no fng): 2025 months weighted R "
          f"{r25:+.3f} vs 2026 months {r26:+.3f} -> "
          f"{'front-loaded (recent half not positive)' if front_loaded else 'not front-loaded'}")

    conds = [
        f"improves both control {'HELD' if improves_control else 'FAILED'}",
        f"OOS t>2.0 {'HELD' if best_oos is True else 'FAILED'}",
        f"not front-loaded {'HELD' if not front_loaded else 'FAILED'}",
        f"best-of-N above noise {'HELD' if best_p < 0.05 else 'FAILED'}",
    ]
    print(f"  conditions: {conds[0]} | {conds[1]} | {conds[2]} | {conds[3]}")
    clears = improves_control and best_oos is True and not front_loaded and best_p < 0.05
    if clears:
        print("VERDICT: sentiment filter clears the bar only if ALL of [improves "
              "both control, OOS t>2.0, not front-loaded, best-of-N above noise] "
              "hold -- all four held")
    else:
        print("VERDICT: sentiment filter clears no bar (conditions must ALL "
              "hold: [improves both control, OOS t>2.0, not front-loaded, "
              "best-of-N above noise])")


def main():
    if not BTC.exists():
        raise SystemExit(f"missing BTC data file: {BTC}")
    df = load_m5(BTC)
    daily = load_fear_greed(cache_path=ROOT / "data/processed/fear_greed.json")
    sent = map_to_bars(daily, df.index)
    print(f"== FALSIFY BTC F&G sentiment direction filter ({BTC.name}, "
          f"{len(df)} bars, {df.index[0]} -> {df.index[-1]}) ==")
    run_coverage(df, sent)
    oos = run_split(df, sent)
    monthly = run_monthly(df, sent)
    best_label, best_abs_t = run_noise_calibration(df, sent)
    run_verdict(df, sent, oos, monthly, best_label, best_abs_t)


if __name__ == "__main__":
    main()
