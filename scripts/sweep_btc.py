"""Parameter sweep over the BTC M5 broker data (research only, no plan)."""

import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from trading_bot.backtest.engine import run_backtest


def load_m5(csv: Path) -> pd.DataFrame:
    df = pd.read_csv(csv, parse_dates=["time"]).set_index("time")
    return df[["open", "high", "low", "close"]]


def stats(trades, name: str) -> dict:
    if not trades:
        return {"name": name, "n": 0}
    df = pd.DataFrame(trades)
    closed = df[df["exit_reason"] != "OPEN"]
    win = closed["exit_reason"] == "TP"
    net_r = 0.0
    for t in closed.itertuples():
        r = (t.exit_price - t.entry) / (t.entry - t.sl)
        net_r += r
    return {
        "name": name,
        "n": len(closed),
        "win_pct": round(100 * win.mean(), 1) if len(closed) else None,
        "net_r": round(net_r / len(closed), 4) if len(closed) else None,
        "net_r_total": round(net_r, 2),
    }


def main():
    csv = ROOT / "data" / "processed" / "XAUUSDc_M5_broker.csv"
    if len(sys.argv) > 1:
        csv = ROOT / sys.argv[1]
    df = load_m5(csv)
    print(f"bars: {len(df)}  {df.index[0]} -> {df.index[-1]}")
    split = int(len(df) * 0.7)
    train, test = df.iloc[:split], df.iloc[split:]
    print(f"train bars: {len(train)}  test bars: {len(test)}\n")

    combos = []
    for rr in (1.0, 1.5, 2.0):
        for lookback in (30, 60):
            for buffer in (0.01, 0.05):
                combos.append((rr, lookback, buffer))
    for hold in (48, 96, 240):
        combos.append((1.0, 60, 0.01, hold, None))
    for sess in ((0, 24), (8, 21), (12, 20)):
        combos.append((1.0, 60, 0.01, None, sess))

    print(f"{'params':<28} {'tr_n':>4} {'tr_win':>6} {'tr_R':>7} {'te_n':>4} {'te_win':>6} {'te_R':>7}")
    rows = []
    for combo in combos:
        if len(combo) == 3:
            rr, lb, buf = combo
            hold, sess = None, None
        else:
            rr, lb, buf = combo[:3]
            hold, sess = combo[3], combo[4]
        kw = dict(rr_multiple=rr, sr_lookback=lb, sl_buffer=buf,
                  fractal_left=2, fractal_right=2, max_concurrent=1,
                  max_hold_bars=hold, session_hours=sess)
        tr = stats(run_backtest(train, **kw), "train")
        te = stats(run_backtest(test, **kw), "test")
        label = (f"rr{rr} lb{lb} buf{buf}"
                 + (f" hold{hold}" if hold else "")
                 + (f" sess{sess[0]}-{sess[1]}" if sess else ""))
        print(f"{label:<28} {tr['n']:>4} {str(tr['win_pct']):>6} {str(tr['net_r']):>7} "
              f"{te['n']:>4} {str(te['win_pct']):>6} {str(te['net_r']):>7}")
        rows.append((label, tr, te))

    print("\n== train/test both positive R, sorted by test R ==")
    good = [(l, t, e) for l, t, e in rows
            if t["net_r"] is not None and e["net_r"] is not None and t["net_r"] > 0 and e["net_r"] > 0]
    good.sort(key=lambda x: x[2]["net_r"], reverse=True)
    for l, t, e in good[:15]:
        print(f"  {l:<28} train R {t['net_r']:+.4f} (n={t['n']})  test R {e['net_r']:+.4f} (n={e['n']})")
    if not good:
        print("  none — no config is positive on BOTH halves")


if __name__ == "__main__":
    main()
