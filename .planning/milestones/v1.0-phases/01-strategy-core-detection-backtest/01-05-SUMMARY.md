---
phase: 01-strategy-core-detection-backtest
plan: 05
subsystem: backtest, cli
tags: python, pandas, cli, histdata, gap-detection, dat-ascii, gap-closure

# Dependency graph
requires:
  - phase: 01-03
    provides: run_backtest/trade_stats/CLI, clean real-data baseline (339/206/133, +1021.91 pts, 13 months)
  - phase: 01-04
    provides: window-bounded S/R level expiry (no ffill) — the precondition for a clean default run
provides:
  - CLI that loads ONLY histdata DAT_ASCII_{SYMBOL}_M1_*.csv files (immune to sample/stray CSVs)
  - data_gap_detected warnings in the decision log for >3-day M1 gaps (self-diagnosing, never a hard error)
  - find_data_gaps() pure helper + list_histdata_csves() filter helper, both unit/integration tested
  - sample relocation data/raw -> data/sample (gen_sample_data.py updated; sample now a tracked artifact)
  - verified clean default run: 339 closed / 206 W / 133 L / 60.8% / +1021.91 pts / PF 1.29 / DD 271.44 / 340 setups — EXACT baseline reproduction (zero 01-04 delta)
affects: [phase 2 live bot (EXEC-01/02), STRAT-01/02/03 verification, SAFE-01/02 re-verification]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "histdata-only CSV selection: glob('DAT_ASCII_{symbol}_M1_*.csv') at the CLI boundary — the durable code fix (sample relocation alone is an on-disk op)"
    - "data-gap detection: >3-day gaps between consecutive M1 bars -> data_gap_detected warning in the decision log + stderr, never a non-zero exit"

key-files:
  created: [tests/test_cli.py, data/sample/sample_XAUUSD_M1_20210201.csv (tracked)]
  modified: [src/trading_bot/cli.py, scripts/gen_sample_data.py]

key-decisions:
  - "CLI globs only DAT_ASCII_{SYMBOL}_M1_*.csv (histdata naming) using the configured symbol — sample files and any stray CSV in the data dir are never loaded, no matter what else sits there"
  - "MAX_M1_GAP = 3 days as a module constant (not a config key): monthly files + ~1h daily breaks + ~2-day weekend gaps make any >72h M1 gap mean missing file(s); a warning knob, not worth config-schema churn"
  - "Gap detection is a WARNING ONLY — never exit non-zero for a gap (real broker data has legitimate gaps)"
  - "Sample relocated to data/sample/ and now TRACKED in git (data/sample/ is not gitignored; the Task-3 integration fixture copies it — the fixture must run from a clean checkout)"
  - "find_data_gaps computes boundaries from the LOADED sorted M1 index (diffs of consecutive bars) — pure, pandas-only, no CLI/logging coupling"

patterns-established:
  - "CLI is self-diagnosing: any >3-day M1 gap (missing file / silent stale region) surfaces as event=data_gap_detected with gap_from/gap_to/gap_hours in backtest.log"
  - "clean-run test pattern: golden histdata fixture (12 M5 buckets x 5 M1 bars, linear open->close interp + bucket high/low) co-residing with the old contaminated sample; asserts len>=1 (no vacuous green) then sl<entry<tp + exact 1:1 on every record"

# Metrics
duration: 33 min
completed: 2026-08-11
---

# Phase 1 Plan 5: CLI Data-Path Hygiene (gap closure 2/2) Summary

**The default one-command run is now clean and self-diagnosing: the CLI loads only histdata DAT_ASCII_XAUUSD_M1_*.csv files (immune to the 2021 ~$100 sample and any stray CSV), logs data_gap_detected warnings for >3-day M1 gaps instead of silently trading stale levels, and the full 13-month real-data run reproduces the 01-03 baseline EXACTLY — 339 closed / 206 W / 133 L / 60.8% WR / +1021.91 pts / PF 1.29 / DD 271.44 / 340 setups, with zero delta from the 01-04 expiry change.**

## Performance

- **Duration:** 33 min
- **Started:** 2026-08-11T08:25Z
- **Completed:** 2026-08-11T08:58Z
- **Tasks:** 3 (3/3 committed)
- **Files modified:** 4 (cli.py, gen_sample_data.py, test_cli.py, sample CSV)

## Accomplishments
- **Default-run contamination closed.** `data_dir.glob("*.csv")` replaced with `list_histdata_csves(data_dir, cfg.data.symbol)` → `sorted(data_dir.glob(f"DAT_ASCII_{symbol}_M1_*.csv"))`. The pre-fix default run produced 3 impossible trades (e.g. entry 2624.91 / tp 104.01 / pnl −2520.9, plus an 18-month OPEN trade stuck on a stale SL); the post-fix run produces 340 convention-clean records with **zero** `sl < entry < tp` violations and zero sub-$500 SLs. `grep -n "glob(" cli.py` confirms only the DAT_ASCII-prefixed glob remains.
- **Self-diagnosing data gaps.** New pure helper `find_data_gaps(m1, max_gap=MAX_M1_GAP="3D")` returns `{gap_from, gap_to, gap_hours}` per >3-day M1 gap; `main()` logs `event=data_gap_detected` and prints a single stderr warning. Never a hard error — the default run exits 0. Real run logs exactly the known gaps: **2025-12-31 16:57 → 2026-07-01 00:00 (4351h, the 2025→202607 file boundary)** and 2025-04-17 → 2025-04-20 (73.03h, a missing-file hole inside 2025 — precisely the silent-stale-region signature this warns about).
- **Sample relocated + tracked.** `data/sample/sample_XAUUSD_M1_20210201.csv` created (gitignore only covers `data/raw/*.csv`; the file is now a tracked test fixture). `data/raw/` holds only real `DAT_ASCII_*` files. `scripts/gen_sample_data.py` `OUT` and docstring updated to `data/sample/`; regenerated file verified byte-identical.
- **Clean-default integration test (no vacuous green).** `test_default_backtest_produces_only_clean_trades` runs `cli.main()` over a tmp data dir containing a golden histdata M1 fixture **and** the old ~$100 sample co-residing; asserts `len(trades) >= 1` first (an empty trades.csv would pass every per-row check vacuously), then `sl < entry < tp` on every record (catches the old tp=104.01 << entry=2624.91 signature) and exact 1:1 R:R `tp - entry == entry - sl` via a non-gap fill (bucket 7 open overridden to 101.00 = the armed level, mirroring `test_exact_one_to_one_rr_on_record`).
- **13-month real-data re-run reproduces the clean baseline EXACTLY** (see Decisions/evidence below) — the 01-04 expiry change introduced **zero** trade-level delta.

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix CLI CSV selection (DAT_ASCII-only) + relocate sample** - `0ad8a99` (feat)
2. **Task 2: Data-gap detection + warning** - `0ad8a99` (feat, same commit as Task 1 — the gap constant/helper/logging landed with the glob fix as one cli.py change set; verified separately via REPL + real run)
3. **Task 3: Clean default-run integration test + full real-data re-run** - `f1f947b` (test, incl. `find_data_gaps` off-by-one fix)

**Plan metadata:** `docs(01-05)` (this commit)

## Files Created/Modified
- `src/trading_bot/cli.py` - `list_histdata_csves()` DAT_ASCII-only glob; `MAX_M1_GAP = pd.Timedelta("3D")`; `find_data_gaps()` pure helper; `main()` logs `data_gap_detected` + stderr warning; bugfix: gap boundary indices (dropna offset)
- `scripts/gen_sample_data.py` - `OUT` → `data/sample/sample_XAUUSD_M1_20210201.csv`; docstring updated (sample no longer lives in data/raw)
- `tests/test_cli.py` (new, 4 tests) - histdata filter unit test, gap-detection unit tests (96h hole / normal break+weekend), clean default-run integration test
- `data/sample/sample_XAUUSD_M1_20210201.csv` (new, tracked) - sample fixture relocated out of the default data path; regenerable via gen_sample_data.py

## Decisions Made
- **DAT_ASCII-only glob is the durable fix.** `data/raw/*.csv` is gitignored, so the sample relocation is an on-disk op only; the code fix is the CLI's glob restriction to `DAT_ASCII_{SYMBOL}_M1_*.csv` using the configured symbol. Any future stray CSV in the data dir is ignored regardless of name.
- **Gap threshold as a module constant, not a config key.** Gold M1 structure (monthly files, ~1h daily break, ~2-day weekend) makes 3 days the natural "missing file" threshold; a warning knob doesn't justify config-schema churn.
- **Gap detection is warning-only.** Real broker data has legitimate gaps; never exit non-zero on a gap.
- **Sample is now a tracked artifact** (data/sample/ is not gitignored): the integration test fixture copies it from the repo, so the test must run from a clean checkout.
- **No delta from 01-04 expiry on the clean run.** The full real-data run reproduces the 01-03 baseline exactly (339/206/133/60.8%/1021.91/1.29/271.44/340) — the 01-04 NaN-expiry change altered zero signals over the real 2025-26 span (real swing density keeps levels in-window continuously). Nothing to paper over; no contamination.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `find_data_gaps` gap boundary indices off by one**
- **Found during:** Task 3 (integration test authoring)
- **Issue:** After `.diff().dropna()`, diff positions are offset by one from the source index; the pre-fix code reported `gap_from`/`gap_to` one bar late (e.g. `00:58→00:59` instead of `00:59→next-day 00:00`). My earlier REPL checks only asserted `gap_hours` (95.0167 ≈ 96), masking the index shift; the integration test's exact-boundary assertion caught it.
- **Fix:** `enumerate(diffs, start=1)` so `diffs[offset-1]` maps to `m1.index[offset-1] → m1.index[offset]`.
- **Files modified:** src/trading_bot/cli.py
- **Verification:** `tests/test_cli.py` exact-boundary assertions + real run now logs `gap_from="2025-12-31 16:57:00" gap_to="2026-07-01 00:00:00"` (correct file-boundary edges).
- **Committed in:** `f1f947b` (Task 3 commit)

**2. [Rule 1 - Bug] Missing `Path` import in tests/test_cli.py (self-caught before commit)**
- **Found during:** Task 3 (first test run — file would not import)
- **Issue:** `_SAMPLE_TEXT` uses `Path(...)` but `pathlib.Path` was not imported.
- **Fix:** added `from pathlib import Path`.
- **Files modified:** tests/test_cli.py
- **Verification:** `pytest tests/test_cli.py` → 4 passed.
- **Committed in:** `f1f947b` (Task 3 commit)

**3. [Rule 1 - Bug] Test over-assertion: contiguous fixture has no gap to warn about**
- **Found during:** Task 3 (first test run — `event=data_gap_detected` absent)
- **Issue:** The integration fixture is a contiguous 60-minute block; `main()` correctly emits NO gap warning, so asserting its presence was wrong (the pre-fix off-by-one made the log look plausible).
- **Fix:** inverted the assertion — the contiguous clean run must NOT contain `event=data_gap_detected` (no false positives). The positive warning case is covered by the unit tests + the real-data run.
- **Files modified:** tests/test_cli.py
- **Verification:** suite green; real run logs exactly the 2 known gaps.
- **Committed in:** `f1f947b` (Task 3 commit)

---

**Total deviations:** 3 auto-fixed (all Rule 1 — bug/test correctness; zero architectural changes)
**Impact on plan:** All fixes necessary for correct behavior; no scope creep. No Rule 4 decisions required.

## Issues Encountered
- None. The two Task-2/3 REPL probes initially mis-asserted `gap_hours ≈ 96` without checking boundaries; the exact-boundary integration test caught the underlying off-by-one (see deviation 1).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- **Phase success criterion now holds on the DEFAULT command**: every `setup_detected`/`order_filled` record in the 2025-26 region shows entry/SL/TP within the real price band (~2600-4300), matching the rules; trades.csv has zero `sl < entry < tp` violations and zero sub-$500 levels.
- **CLI is self-diagnosing**: `event=data_gap_detected` in backtest.log flags the 2025→202607 file boundary and the intra-2025 missing-file hole (73h), so stale-region risk is surfaced instead of silent.
- **SAFE-01 exact 1:1 R:R verified on the default-run record** via the non-gap-fill integration test.
- **Repo ships clean**: 39 tests green under `-W error::FutureWarning`; default `python -m trading_bot.cli backtest` exits 0 with baseline-matching stats.
- Blockers: none. Note (carried): real-data span is 13 months (2025 full + 2026-07); 2026-08+ acquisition remains a manual histdata.com download if the strategy edge is to be judged over a longer horizon.

---
*Phase: 01-strategy-core-detection-backtest*
*Completed: 2026-08-11*
