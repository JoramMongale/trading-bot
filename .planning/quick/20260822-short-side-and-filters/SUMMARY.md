---
slug: short-side-and-filters
created: 2026-08-22
status: complete
---

# Short side + filters — measured. Every proposed filter fails out-of-sample.

XAUUSD M5, 77,038 bars, 2025-01-01 → 2026-07-31. Train = first 70%, test = last
30%. Filters judged on **test**, which they had no part in choosing. R is net of
the live 0.26 XAUUSDc spread where marked.

## Headline

| config | n | win% | avgR | avgR net | t |
|---|---:|---:|---:|---:|---:|
| **long baseline** | 339 | 60.8 | +0.1352 | +0.1211 | +2.71 |
| **SHORT baseline** | 316 | 51.3 | −0.0593 | −0.0733 | −1.14 |
| long +ATR<median120 | 284 | 62.3 | +0.1606 | +0.1443 | +2.97 |
| long +H1 trend | 59 | 64.4 | +0.1977 | +0.1813 | +1.67 |
| long +body | 333 | 60.4 | +0.1305 | +0.1165 | +2.58 |
| long +ATR+H1+body | 54 | 63.0 | +0.1827 | +0.1658 | +1.45 |

## 1. The edge is NOT symmetric — and that is the problem

Longs **+0.135R**, shorts **−0.059R**. A 0.194R gap.

That looks like the long setup working. The context says otherwise: **gold rose
+54.0% across this sample** (train +48.8%, test +3.4%). A long-only breakout
system in a market that went up by half harvests drift whether or not the setup
carries information.

Average the two directions and the drift roughly cancels, leaving the setup's
own contribution:

| | long | short | mean (drift-neutral) |
|---|---:|---:|---:|
| train | +0.1396 | −0.0702 | **+0.035** |
| test | +0.1279 | −0.0252 | **+0.051** |

So the honest estimate of the setup's direction-neutral edge is **+0.04R, not
+0.14R**. Most of what the long side earns is the market going up, and the short
side is the receipt: it is the same setup, mirrored exactly, losing money in the
same conditions.

This is the answer to "is the negative edge symmetric?" — **no**, and the
asymmetry points at drift rather than skill.

## 2. The ATR filter is a textbook overfit

It produced the single best number in this project's history — and then died.

| | n | avgR | t |
|---|---:|---:|---:|
| train, long +ATR | 200 | **+0.2000** | **+3.14** |
| test, long +ATR | 83 | +0.0572 | +0.56 |
| test, long baseline (for comparison) | 92 | **+0.1279** | +1.34 |

On the training half it beat everything ever tried here. On unseen data it
scored **less than half the unfiltered baseline**. Selecting it on the strength
of that t=3.14 would have made the system worse.

## 3. The H1 trend filter destroys the sample

339 trades → 59 (test: **14**). Its higher R is computed on so few trades that
t drops to 1.67 despite the better average. Fourteen trades cannot support a
decision.

## 4. Candle-body confirmation does nothing

+0.1352 → +0.1305R. Slightly negative, well inside noise. It removed 6 of 339
trades.

## 5. Stacking them is worst of all

`+ATR+H1+body` on test: **11 trades, +0.0358R, t=0.12**. Each filter narrows the
sample, and narrow samples produce confident-looking numbers that mean nothing.

## Verdict

**Nothing here should be wired into the live engine.** All of it stays as
backtest parameters with defaults off, alongside `session_hours` and
`max_hold_bars`.

Against the project's own calibration bar — ~39 configurations searched, best
|t| 2.37 (median) to 2.68 (p75) expected from pure noise — the long baseline's
t=2.71 sits exactly at the bar, and these ten configurations push the effective
search count higher still, which raises the bar rather than clearing it.

The one thing worth carrying forward: the drift-neutral estimate of **+0.04R**.
If that is the real number, it is far too small to survive a 0.26 spread on
anything but the tightest instrument, and it explains why the 6,541-trade
multi-instrument figure came out at −0.0156R while gold alone looks positive.

## What was NOT done

- No live-engine change
- `direction="both"` — two directions competing for one slot is a different
  system with its own selection bias
- News/event gating — needs a feed and a calendar, and stacks a second unproven
  system on an unproven one
