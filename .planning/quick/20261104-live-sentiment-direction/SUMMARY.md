# Live sentiment direction for gold, BTC and JPY crosses (2026-11-04)

## What changed

- `news/live_sentiment.py`: one live resolver, `resolve(source, ...)`, for three
  sources. Each maps a daily series to 0-100 bullishness for the traded symbol;
  `>= 50+band` -> long only, `<= 50-band` -> short only, otherwise no override
  (`[strategy] direction` applies).
  - `dxy` (gold): DXY vs its 200-day MA (same mapping as quick 260928-dxy).
  - `fng` (BTC): Crypto Fear & Greed as-is (same mapping as quick 260928-fng).
  - `vix` (JPY crosses): VIX vs its 50-day MA; calm = risk-on = long XXX/JPY.
    New and NOT backtested.
- Fixed: the live DXY signal read its JSON cache forever and never refetched,
  so a running bot would trade on frozen data. The resolver now refetches when
  the cache is older than `cache_max_age_hours` (stale cache kept if the fetch
  fails) and returns no override when the newest completed day is older than
  `max_stale_days`. Today's (unfinished) daily row is dropped, matching the
  backtests' one-day shift.
- `[sentiment]`: `source` accepts dxy | fng | vix; new `cache_max_age_hours`,
  `max_stale_days`; each source defaults to its own cache file.
- Live engine logs `sentiment_direction` (value, as_of day, direction, fallback)
  or `sentiment_unavailable` (reason) each refresh.

## Config state (owner decision 2026-11-04: test on the real accounts)

| Config | Source | Enabled | Fallback direction |
|---|---|---|---|
| config-cent.toml (XAUUSDc, live) | dxy | yes | both |
| config-btc.toml (BTCUSDc, live) | fng | yes | long |
| config-eurjpy.toml (dry-run) | vix | no | config |

Neither the DXY nor the Fear & Greed backtest passed its bar; this is a live
experiment by explicit owner choice. The BTC breakout book measured negative
with and without the F&G filter (260928-fng).

## Readings at build time (completed day 2026-11-03)

dxy 29.1 -> short · fng 26.0 -> short · vix 6.3 -> short

## Tests

623 passed, 2 skipped (16 new in `tests/test_live_sentiment_sources.py`;
engine sentiment tests now stub `live_sentiment.resolve`).
