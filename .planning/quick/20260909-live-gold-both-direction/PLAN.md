---
phase: 20260909-live-gold-both-direction
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/trading_bot/broker/base.py
  - src/trading_bot/broker/simulated.py
  - src/trading_bot/broker/dry_run.py
  - src/trading_bot/broker/mt5.py
  - src/trading_bot/config.py
  - src/trading_bot/live/engine.py
  - src/trading_bot/ai/engine.py
  - src/trading_bot/cli.py
  - config/config-cent.toml
  - tests/test_broker_sell.py
  - tests/test_config.py
  - tests/test_live_engine_both.py
  - tests/test_broker_simulated.py
  - .planning/quick/20260909-live-gold-both-direction/SUMMARY.md
  - .planning/STATE.md
autonomous: false
requirements: [STRAT-02, STRAT-03, EXEC-01, EXEC-02, SAFE-02, SAFE-03]
user_setup: []

must_haves:
  truths:
    - "The live engine trades the SAME swing S/R breakout on BOTH sides on the gold cent account (XAUUSDc, magic 77020): a bearish close below support arms a SHORT whose stop sits above resistance and whose target is rr_multiple x the stop BELOW the reference support, and the sell crosses the BID."
    - "With direction=\"long\" (the default) every existing live/broker/test path is byte-identical — golden tests unchanged and green, the long-only MT5 buy path untouched."
    - "A SHORT setup fired through the real engine into DryRunBroker produces an order_plan/order_placed decision trail carrying side=short with sell geometry and places NOTHING (empty inner ledger) — the sell path is proven before any real order."
    - "SAFE-03, weekend guard (weekend_stop_hour=19), session filter, min_rr, daily-loss halt, pending-equivalent dedup and the max_concurrent slot guard all gate SHORT setups exactly as they gate longs; nothing is weakened."
    - "The supervised cent bot is swapped last: config-cent.toml (rr_multiple 1.0, direction=\"both\") is live only after stop sentinel -> taskkill -> schtasks /Run, and post-start logs confirm direction=both rr_multiple=1.0 on magic 77020 mode=live."
  artifacts:
    - path: "src/trading_bot/broker/base.py"
      provides: "OrderRequest.side ('long' default) carried into to_log_fields; risk_per_unit side-agnostic stop distance; BrokerClient.place_market_sell abstract"
      contains: "place_market_sell"
    - path: "src/trading_bot/broker/mt5.py"
      provides: "place_market_sell: ORDER_TYPE_SELL at the BID, sl/tp above/below, _check_stop_distance mirrored; buy path untouched"
      contains: "ORDER_TYPE_SELL"
    - path: "src/trading_bot/broker/simulated.py"
      provides: "place_market_sell fills at the bid and opens a position (single-slot guard sees it)"
    - path: "src/trading_bot/broker/dry_run.py"
      provides: "place_market_sell NEVER sends: logs event=order_plan side=short, returns placed=False/ticket=0, zero references to inner"
    - path: "src/trading_bot/live/engine.py"
      provides: "direction='both' detection union with per-bar setup_dir, per-side geometry, bid-priced short risk, side-aware levels_are_tradable, buy/sell dispatch, side on setup/order log lines"
    - path: "src/trading_bot/config.py"
      provides: "StrategyConfig.direction ('long' default | 'both'); validate_config rejects anything else naming strategy.direction"
    - path: "config/config-cent.toml"
      provides: "the ONLY live config changed: rr_multiple 2.0 -> 1.0, direction='both'; mode/enabled/magic/terminal untouched"
    - path: "tests/test_live_engine_both.py"
      provides: "mirrored-golden SHORT dry-run E2E through the real engine + DryRunBroker; long-default byte-identity; bid-priced short risk"
  key_links:
    - from: "src/trading_bot/live/engine.py"
      to: "src/trading_bot/broker/mt5.py"
      via: "place_market_sell(request) for side='short' (place_market_buy unchanged for 'long')"
    - from: "src/trading_bot/live/engine.py"
      to: "src/trading_bot/strategy/signals.py"
      via: "detect_setups(df, 'long')['setup'] | detect_setups(df, 'short')['setup'] under one levels frame (direction='both')"
    - from: "config/config-cent.toml"
      to: "src/trading_bot/live/engine.py"
      via: "cfg.strategy.direction and cfg.strategy.rr_multiple read at poll time; live_start log echoes both for post-deploy verification"
---

<objective>
Wire the MEASURED both-direction single-slot M5 breakout variant (direction="both", rr_multiple=1.0, max_concurrent=1) into the LIVE path for the real gold cent account 161693049 (XAUUSDc, magic 77020), replacing the running long-only bot on the SAME magic/symbol.

Purpose: The user reviewed quick task 20260909-gold-both-scalper (measured, clears no bar: best config OOS t≈0.46, best-of-8 noise P=10.3%) and, after repeated explicit warnings, has knowingly chosen to deploy the both rr1.0 book on their own cent account. Per the project's "warn loudly, do not block" convention this plan builds it CORRECTLY and keeps every mechanical safety rail intact. The live engine and broker adapters are long-only today; this is a real sell/short path plus a side-aware live engine, NOT a config flag. D-5 is absolute: direction="long" (default) stays byte-identical everywhere; golden tests untouched. D-6: the running bot stays up until the build is committed and tested; the supervised swap is the FINAL, gated task.

The backtest measurement is DONE (engine direction="both" already exists in run_backtest with per-trade sides — quick 20260909-gold-both-scalper). This plan does NOT re-run it; it mirrors the same pure detection chain and single-slot semantics into the live engine.

Output: broker sell path; strategy.direction config key; side-aware live engine with a short dry-run E2E gate; config-cent.toml live change; supervised deployment swap; SUMMARY.md.
</objective>

<execution_context>
@C:\Users\joram\.config\opencode\get-shit-done\workflows\execute-plan.md
@C:\Users\joram\.config\opencode\get-shit-done\templates\summary.md
</execution_context>

<context>
@.planning/STATE.md  (decisions D-2, D-5, D-6 in <planning_context>; live-account reality 161693049 @ Exness-MT5Real21, XAUUSDc magic 77020, supervised by Task Scheduler task trading-bot-cent -> scripts\supervise_live.bat; stop = output\live_cent.stop sentinel + taskkill per gold_weekend_stop.bat/tune_risk._restart_windows; start = schtasks /Run /TN trading-bot-cent)
@.planning/quick/20260909-gold-both-scalper/SUMMARY.md  (the measured both rr1.0 row: R +0.0810 t=+1.94, long leg R +0.1260, short leg R +0.0228; verdict clears no bar — user chose to deploy anyway)
@config/config-cent.toml
@src/trading_bot/live/engine.py
@src/trading_bot/broker/base.py
@src/trading_bot/broker/mt5.py
@src/trading_bot/broker/simulated.py
@src/trading_bot/broker/dry_run.py
@src/trading_bot/config.py
@src/trading_bot/ai/engine.py
@src/trading_bot/cli.py
@scripts/supervise_live.bat
@scripts/gold_weekend_stop.bat
@scripts/run_with_pidfile.py

Python on this Windows box: `.venv\Scripts\python.exe`. pytest needs
`-p no:cacheprovider --basetemp "C:\Users\joram\AppData\Local\Temp\opencode\pytest-bot"`.
Repo is local-only git, HEAD b2d1896; commit atomically per task (identity is set).

<interfaces>
Backtest both-mode reference (src/trading_bot/backtest/engine.py, ALREADY SHIPPED — do NOT modify):
```python
# pass A for direction="both": one levels frame, union of the two side signals
df = support_resistance(detect_swings(df, fl, fr), lookback)
long_sig  = detect_setups(df, direction="long")["setup"]
short_sig = detect_setups(df, direction="short")["setup"]
df["setup"] = long_sig | short_sig
df["setup_dir"] = "";  df.loc[long_sig, "setup_dir"] = "long";  df.loc[short_sig, "setup_dir"] = "short"
# per-side geometry (levels_at): long -> (resistance, support-sl_buffer); short -> (support, resistance+sl_buffer)
# tp = entry + rr_multiple * (entry - sl)  # negative distance for shorts puts tp BELOW entry
```
LiveEngine poll chain today (src/trading_bot/live/engine.py lines ~290-378): detect_swings -> support_resistance -> detect_setups(df) [long], act on last CLOSED bar: entry=resistance, sl=support-sl_buffer, tp=entry+rr_multiple*(entry-sl), then on_setup(entry, sl, tp, bar_time). on_setup order: levels_are_tradable(entry>sl) -> pending-equivalent dedup -> slot guard -> self._ai_gate(entry, sl, tp, bar_time) -> SAFE-03 -> quote+symbol_risk (risk_at_market = q.ask - sl, reward = tp - q.ask) -> min_rr -> daily-loss -> position_size -> sr.money_risk cap -> broker.place_market_buy(req).

Broker ABC (base.py): OrderRequest{symbol, volume, entry, sl, tp, magic, deviation, comment} with `risk_per_unit = entry - sl` and `to_log_fields()` returning {symbol, volume, entry, sl, tp, magic}; BrokerClient has ONE placement method `place_market_buy(request)`. MT5Broker.place_market_buy (mt5.py ~432) reads the ASK, rounds to digits, `"type": mt5.ORDER_TYPE_BUY`, checks `_check_stop_distance(price, sl, tp, stops_points*point)` where the checks are `ask-sl` and `tp-ask`, filling-mode fallback on 10030. SimulatedBroker.place_market_buy fills at quote().ask, appends a ledger entry, opens a Position (slot guard). DryRunBroker.place_market_buy logs `event=order_plan` with `request.to_log_fields()` + mode=dry-run and returns placed=False/ticket=0 with ZERO inner-broker references.

Config (config.py): StrategyConfig(frozen) is built via StrategyConfig(**raw["strategy"]); validate_config `_validate` raises ValueError naming the bad key. Live engine reads cfg.strategy.rr_multiple already; nothing reads a direction key yet.

SHORT mirror arithmetic (mirror the golden long frame — see Task 3): reflect every price about a constant M (y = 2M - x, high<->low swapped). A short setup fires on the LAST bar when close < support and prior close >= prior support. Hand-computed short golden at M=150: entry = support' = 2M - 101.00 = 199.00; sl = resistance' + 0.01 = (2M - 100.10) + 0.01 = 199.91; tp = entry - (sl - entry) = 198.09; market bid = last close' = 2M - 101.05 = 198.95 -> risk_at_market = 199.91 - 198.95 = 0.96 (symmetric with the long golden MARKET_RISK 0.96).
</interfaces>

<tasks>

<task type="auto" tdd="true">
  <name>task 1: broker sell path — OrderRequest.side + place_market_sell on the ABC and all three adapters</name>
  <files>src/trading_bot/broker/base.py</files>
  <files>src/trading_bot/broker/simulated.py</files>
  <files>src/trading_bot/broker/dry_run.py</files>
  <files>src/trading_bot/broker/mt5.py</files>
  <files>tests/test_broker_sell.py</files>
  <files>tests/test_broker_simulated.py</files>
  <behavior>
    - Test 1 (sell translation, fake MT5): `place_market_sell(request)` sends one order_send whose request dict is {"action": 1, "type": 1 (ORDER_TYPE_SELL), "price": the BID rounded to digits, "sl" above the bid, "tp" below the bid, volume floored, magic/comment/deviation passed through, type_time 0, type_filling IOC-first}. The buy path dict (test_place_market_buy_sends_a_deal_at_the_ask...) is unchanged.
    - Test 2 (bid not ask): with FakeMT5 tick bid=101.30 ask=101.50, place_market_sell fills at price 101.30 and reports fill_price 101.30.
    - Test 3 (mirrored stop-distance guard): a sell whose sl is INSIDE the broker's minimum distance above the bid raises BrokerRejectedError naming the stop; a sell whose tp is inside the minimum below the bid raises too; a sell with both outside passes. The buy-side guard tests stay green (byte-identical for sell=False).
    - Test 4 (dry-run sell): DryRunBroker.place_market_sell returns placed=False/ticket=0, logs event=order_plan containing side=short, and the inner broker ledger stays empty.
    - Test 5 (simulated sell): SimulatedBroker.place_market_sell appends a ledger entry whose side is 'short', opens a Position (so the slot guard sees it), and fills at quote().bid (with a spread set, bid != ask).
    - Test 6 (risk_per_unit side-agnostic): an OrderRequest with sl>entry (short geometry) reports risk_per_unit = sl - entry; a long geometry reports entry - sl; both equal abs(entry-sl).
  </behavior>
  <action>
    Do NOT refactor the buy path; add to it.

    base.py:
    - OrderRequest (frozen dataclass, ~line 31): add a trailing field `side: str = "long"` (every existing keyword construction stays valid). Update the class docstring: `entry` is the broken REFERENCE level (resistance for long, SUPPORT for short); `sl`/`tp` keep strategy geometry (long: entry>sl, tp>entry; short: sl>entry, tp<entry).
    - `risk_per_unit` (~line 54): return the stop distance regardless of side — `abs(self.entry - self.sl)` — documented as "distance from the reference entry to the stop, in quote units (positive for both sides)". For long geometry this is numerically identical to today.
    - `to_log_fields` (~line 59): add `"side": self.side`. (SAFE-02: the decision line must record which side fired.)
    - BrokerClient (~line 203): add `@abstractmethod def place_market_sell(self, request: OrderRequest) -> OrderResult` with a docstring: sell at market with SL/TP attached; raise BrokerRejectedError on a failure retcode. Because it is abstract, ALL THREE adapters must implement it in this same commit (MT5Broker, SimulatedBroker, DryRunBroker; ReplayBroker inherits).

    simulated.py (~line 110, mirror place_market_buy exactly):
    - `place_market_sell`: same ledger/position behaviour as place_market_buy but fill at the BID — `fill_price=self.quote(request.symbol).bid` — so the engine's short risk is honoured. Ledger entry carries side via to_log_fields.

    dry_run.py (~line 68, mirror place_market_buy exactly):
    - `place_market_sell`: structurally identical no-send — `log_decision(logger, "order_plan", **request.to_log_fields(), mode="dry-run")` then `OrderResult(ticket=0, placed=False, retcode=0, comment="dry-run: no order sent")`. ZERO references to `self._inner`.

    mt5.py:
    - `_check_stop_distance` (~line 155): add a keyword-only `sell: bool = False`. For sell=True the market reference is the BID and stops must be FURTHER ABOVE (sl) / BELOW (tp): refuse when `sl - price < min_dist` or `price - tp < min_dist`. Default sell=False keeps the two existing comparisons exactly as written (buy byte-identical).
    - New `place_market_sell(self, request)` (model it line-for-line on place_market_buy at ~line 432): read the BID (`tick.bid`, reject BrokerRejectedError when <= 0), `price = round(bid, digits)`, round sl/tp to digits, `_resolve_volume`, the same non-finite NaN refusal, `_check_stop_distance(price, sl, tp, stops_points * point, sell=True)`, then the request dict is byte-for-byte the buy shape EXCEPT `"type": mt5.ORDER_TYPE_SELL` and `"price": price` (the bid). Same filling-candidates 10030 fallback and same DONE/PLACED retcode handling.

    Tests — create `tests/test_broker_sell.py` implementing the six behaviours. It must NOT import across test files (tests dir is not a package): copy the ~15-line namedtuple block (_SymbolInfo, _Tick, _OrderSendResult) and write a minimal local FakeMT5 module injected via monkeypatch.setitem(sys.modules, "MetaTrader5", fake) — the fake needs initialize/terminal_info/symbol_select/symbol_info/symbol_info_tick/order_send/last_error plus constants ORDER_TYPE_SELL=1, ORDER_TYPE_BUY=0, TRADE_ACTION_DEAL=1, ORDER_FILLING_IOC=1, ORDER_TIME_GTC=0, TRADE_RETCODE_DONE=10009, TRADE_RETCODE_INVALID_FILL=10030. Reuse the `_request()`/`_broker()` helper shape from tests/test_mt5_broker.py (copy locally). Use `.venv\Scripts\python.exe -m pytest` with the flags below.

    tests/test_broker_simulated.py: update ONE stale assertion — `test_to_log_fields_contains_safe02_keys` asserts `set(...) == {"symbol","volume","entry","sl","tp","magic"}`; add "side" so it reads `{"symbol","volume","entry","sl","tp","magic","side"}`. This is the deliberate field addition (SAFE-02 side recording); flag it in the SUMMARY as a one-line intentional test update, matching the f42fa40 precedent. No other existing test is modified.

    Commit: `git add src/trading_bot/broker/base.py src/trading_bot/broker/simulated.py src/trading_bot/broker/dry_run.py src/trading_bot/broker/mt5.py tests/test_broker_sell.py tests/test_broker_simulated.py` then `feat(broker): place_market_sell + OrderRequest.side (buy path untouched)`.
  </action>
  <verify>
    <automated>.venv\Scripts\python.exe -m pytest tests/test_broker_sell.py tests/test_broker_simulated.py tests/test_mt5_broker.py -q -p no:cacheprovider --basetemp "C:\Users\joram\AppData\Local\Temp\opencode\pytest-bot"</automated>
  </verify>
  <done>
    BrokerClient now has place_market_sell implemented by MT5Broker (ORDER_TYPE_SELL at the bid, mirrored stop-distance guard), SimulatedBroker (fill at bid, opens a position) and DryRunBroker (no-send order_plan); OrderRequest carries side and risk_per_unit is side-agnostic; all pre-existing buy/dry-run/fake-MT5 tests green with only the one to_log_fields set updated; committed.
  </done>
</task>

<task type="auto" tdd="true">
  <name>task 2: config schema — StrategyConfig.direction + validate_config</name>
  <files>src/trading_bot/config.py</files>
  <files>tests/test_config.py</files>
  <behavior>
    - Test 1 (default): a config without strategy.direction loads with direction == "long" (legacy configs byte-identical).
    - Test 2 (readable): a config with `direction = "both"` loads and load_config(...).strategy.direction == "both".
    - Test 3 (reject): direction "short", "sideways", "" each raise ValueError whose message names "strategy.direction".
    - Test 4 (live cent config untouched by this task): load_config("config/config-cent.toml") still passes (rr_multiple 2.0 today) — regression guard for the Task 4 edit.
  </behavior>
  <action>
    config.py only:
    - StrategyConfig (~line 27): add a trailing field `direction: str = "long"` with the comment: which SIDE(s) the LIVE engine trades. "long" (default) is the only value every existing config uses and must stay byte-identical; "both" runs the long and short swing S/R breakouts through the same single slot. A "short"-only live mode is deliberately NOT supported — the backtester can measure it, but the live need is "both", and the locked config is the union. (Mirror the `variant` field comment style.)
    - `_validate` (~after the variant check at ~line 420): add
      ```python
      if cfg.strategy.direction not in ("long", "both"):
          raise ValueError(
              f"strategy.direction={cfg.strategy.direction!r} is invalid: must be "
              "'long' (default) or 'both' ('short'-only live is unsupported; "
              "'both' trades both sides through the single slot)"
          )
      ```
    Do NOT touch anything else in config.py.

    tests/test_config.py: add test functions following the `variant` test style at ~line 151 (write a tmp TOML, insert `direction = "..."` after the `sl_buffer = 0.01` line, load, assert). Add: default-is-long, both-is-readable, and a parametrized reject of ("short", "sideways", "") naming strategy.direction. Do NOT modify existing tests.

    Commit: `git add src/trading_bot/config.py tests/test_config.py` then `feat(config): strategy.direction ('long' default | 'both') with validation`.
  </action>
  <verify>
    <automated>.venv\Scripts\python.exe -m pytest tests/test_config.py tests/test_config_ai.py tests/test_config_backtest_templates.py -q -p no:cacheprovider --basetemp "C:\Users\joram\AppData\Local\Temp\opencode\pytest-bot"</automated>
  </verify>
  <done>
    StrategyConfig.direction exists with "long" default and only "long"/"both" validate; every committed config (including config-cent.toml at rr_multiple=2.0) still loads; new config tests green; committed.
  </done>
</task>

<task type="auto" tdd="true">
  <name>task 3: side-aware live engine (both-direction detection + short risk/placement + AI gate side) with the SHORT dry-run E2E gate</name>
  <files>src/trading_bot/live/engine.py</files>
  <files>src/trading_bot/ai/engine.py</files>
  <files>tests/test_live_engine_both.py</files>
  <behavior>
    - Test 1 (SHORT dry-run E2E — the pre-deploy sell-path gate): mirror the golden 12-bar frame about M=150 (high<->low swapped, y=2M-x) so the mirrored bar idx 6 closes BELOW its support with the prior close above. Build a config with strategy.direction="both", rr_multiple=1.0. Walk LiveEngine over a DryRunBroker(SimulatedBroker) exactly like test_cli_live._walk. The idx-6 poll returns {"event":"order_placed","side":"short", ticket=0, entry≈199.00, sl≈199.91, tp≈198.09}; the decision log contains event=order_plan with side=short and event=setup_detected with side=short; the inner broker ledger stays EMPTY (dry-run places nothing).
    - Test 2 (long default byte-identity): a SimulatedBroker walk of the UNMIRRORED golden frame through a direction="long" (default) engine produces the exact long order event (entry 101.00/sl 100.09/tp 101.91) and — critically — running the SAME frame under direction="long" before vs after is pinned by the untouched golden suite (tests/test_live_engine.py, tests/test_cli_live.py stay green unchanged).
    - Test 3 (real sell through SimulatedBroker): with a spread set on the inner broker (bid != ask), a short setup on the mirrored frame PLACES via the broker, the ledger entry carries side="short", the position opens (slot guard), and the recorded fill equals the BID, not the ask.
    - Test 4 (bid-priced risk): a short setup whose quote BID has run up to within min_rr of the stop is refused reason=rr_degraded (reward measured as bid - tp over sl - bid); a short whose bid is AT/ABOVE the stop is refused reason=invalid_levels.
    - Test 5 (levels_are_tradable side-aware): levels_are_tradable(e, sl, tp) with side="long" accepts entry>sl and rejects sl>=entry (today's rule unchanged); with side="short" accepts sl>entry>tp and rejects sl<=entry or tp>=entry; NaN still rejected on both.
    - Test 6 (union detection): on a mixed long+short frame with direction="both", polls fire whichever side the bar signals and no bar can produce both (each poll returns one order event).
  </behavior>
  <action>
    Edit live/engine.py and ai/engine.py only. The DETECTION defaults stay byte-identical (D-5).

    live/engine.py:
    1. `levels_are_tradable(self entry, sl, tp, side="long")` (~line 51): keep the finite check; then `return entry > sl if side == "long" else (sl > entry and entry > tp)`. Update the docstring: a long needs sl below entry (today); a short needs the stop ABOVE the reference support and the target BELOW it (sl > entry > tp). A non-positive stop distance or inverted levels fails on both sides.
    2. `poll_once` strategy chain (~lines 290-299): read `direction = cfg.strategy.direction`. After `df = support_resistance(detect_swings(...), ...)`:
       - `direction == "both"`: compute the union exactly like backtest engine pass A — `long_sig = detect_setups(df, direction="long")["setup"]`, `short_sig = detect_setups(df, direction="short")["setup"]`, `df["setup"] = long_sig | short_sig`, `df["setup_dir"] = ""`, `df.loc[long_sig, "setup_dir"] = "long"`, `df.loc[short_sig, "setup_dir"] = "short"` (short overwrites in the pathological overlap, matching run_backtest).
       - otherwise (long|short single): `df = detect_setups(df, direction=direction)` exactly as today — the default long path must NOT add a setup_dir column (byte-identical AI-context frame).
    3. Setup branch (~lines 362-378): resolve the side BEFORE the arithmetic — `side = str(df["setup_dir"].iloc[-1]) if direction == "both" else direction`. Geometry per side (mirror of backtest levels_at): long -> entry = resistance, sl = support - sl_buffer; short -> entry = support, sl = resistance + sl_buffer. Then ONE tp formula for both: `tp = entry + cfg.strategy.rr_multiple * (entry - sl)` (negative distance for a short puts tp below entry — STRAT-03 parity with run_backtest). Log `setup_detected` with `side=side` added to the existing fields. Call `return self.on_setup(entry, sl, tp, new_bar_time, side=side)`.
    4. `on_setup(self, entry, sl, tp, bar_time, side="long")` (~line 380): default keeps every existing caller byte-identical. Build the OrderRequest with `side=side`. The invalid_levels log `detail` becomes side-aware ("stop not below entry" long / "short needs sl > entry > tp" short) — keep the reason key `invalid_levels`. Levels check becomes `levels_are_tradable(entry, sl, tp, side=side)`.
    5. `self._ai_gate(entry, sl, tp, bar_time)` call (~line 468): pass `side=side`. Base method signature (line 247) becomes `def _ai_gate(self, entry, sl, tp, bar_time, side="long")` — returns None unchanged.
    6. Market pricing block (~lines 505-539): `entry_at_market = q.bid if side == "short" else q.ask`; `risk_at_market = (sl - entry_at_market) if side == "short" else (entry_at_market - sl)`; `reward_at_market = (entry_at_market - tp) if side == "short" else (tp - entry_at_market)`. The `risk_at_market <= 0` refusal detail becomes side-aware ("market is already at or above the stop" for short). Keep `rr = reward/risk` and the min_rr guard unchanged; log `ask`/`bid` and slippage per side — slippage = `entry - entry_at_market` for short (positive when the market is below the reference support), `entry_at_market - entry` for long (keep today's sign for long; for the log field compute `_round2((entry - entry_at_market) if side == "short" else (entry_at_market - entry))`). Daily-loss, position_size, sr.money_risk cap and lot handling are side-agnostic — do NOT touch them (SAFE-03 unchanged).
    7. Placement (~line 644): `result = self._broker.place_market_sell(req) if side == "short" else self._broker.place_market_buy(req)`. order_placed log keeps `**log_fields` (now includes side= via to_log_fields) and reports `slippage` as above. The returned event dict gains `"side": side` (additive; no consumer asserts exact order_placed dict equality — verified).

    ai/engine.py:
    - `_ai_gate` (~line 58): signature becomes `(self, entry, sl, tp, bar_time, side="long")` and pass `direction=side` to `evaluate_proposal(...)` where "long" is hard-coded today (~line 103). For direction="long" this is byte-identical (gate already has a short-direction mirror at the pure level — test_ai_gate). Nothing else changes.

    Tests — create `tests/test_live_engine_both.py` (do NOT modify tests/test_live_engine.py or tests/test_cli_live.py — they are the byte-identity proof). Copy the golden _OPENS/_HIGHS/_LOWS/_CLOSES lists, `_golden_df()`, `_config(live, risk, direction="long", rr_multiple=1.0)` and a `_walk` helper locally from tests/test_cli_live.py (same conventions; tests dir is not a package). Add a local `_mirror(df, m=150.0)` helper (high<->low swap, y=2m-x). Use StrategyConfig(..., direction=direction) via the `replace` pattern. For Test 3 set `inner._spread = 0.20` before the setup poll so bid != ask. Hand-compute the mirrored short golden (given in <interfaces>): entry 199.00 / sl 199.91 / tp 198.09 / risk 0.96, and assert with pytest.approx.
    Note: the short E2E engine config must be mode="dry-run"/demo so the SAFE-03 gate passes; use the same _DEMO-style LiveConfig as test_live_engine.py.

    Commit: `git add src/trading_bot/live/engine.py src/trading_bot/ai/engine.py tests/test_live_engine_both.py` then `feat(live): direction='both' — side-aware detection, bid-priced short risk, sell dispatch + short dry-run E2E`.
  </action>
  <verify>
    <automated>.venv\Scripts\python.exe -m pytest tests/test_live_engine_both.py tests/test_live_engine.py tests/test_cli_live.py tests/test_ai_hooks.py tests/test_ai_engine.py tests/test_ai_gate.py -q -p no:cacheprovider --basetemp "C:\Users\joram\AppData\Local\Temp\opencode\pytest-bot"</automated>
  </verify>
  <done>
    direction="both" live engine fires SHORT setups through the real detection chain with sell geometry and bid-priced risk, dispatches to place_market_sell, and logs the side on setup_detected/order_placed; the mirrored-golden short dry-run E2E passes with an empty inner ledger; every pre-existing live/AI/golden test is green UNMODIFIED (byte-identity); committed.
  </done>
</task>

<task type="auto">
  <name>task 4: live config change (rr_multiple 1.0 + direction both) and live_start echo — no restart</name>
  <files>config/config-cent.toml</files>
  <files>src/trading_bot/cli.py</files>
  <action>
    config/config-cent.toml (the ONLY live config changed, D-3):
    - `[strategy]` `rr_multiple = 2.0` -> `rr_multiple = 1.0` and fix the stale trailing comment (`# 1:1 risk-reward` was already wrong at 2.0) to: `# measured both-direction single-slot config (quick 20260909-gold-both-scalper): TP = 1x the stop distance, both sides share the one slot`.
    - Add under `[strategy]`: `direction = "both"      # long (default) | both — trade the short swing-S/R mirror in the same single slot (D-2)`.
    - Do NOT touch [live] (enabled=true, mode="live", magic_number=77020, weekend_stop_hour=19), [risk] (cap 20%, percent sizing, daily 6%, min_rr 0.5, max_concurrent=1) or terminal/bridge settings. The running bot keeps its in-memory config until the Task 5 restart — an on-disk edit does not disturb it (config is read once at process start; verified D-6 ordering).
    src/trading_bot/cli.py `_run_live` live_start block (~lines 369-381): add `direction=cfg.strategy.direction` and `rr_multiple=cfg.strategy.rr_multiple` to the existing log_decision fields so the post-deploy verification can grep the loaded values off the actual run (mode/symbol/magic stay as-is).

    Verify the edit loads BEFORE committing:
    `.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'src'); from trading_bot.config import load_config; c=load_config('config/config-cent.toml'); print(c.strategy.direction, c.strategy.rr_multiple, c.live.mode, c.live.enabled, c.live.magic_number)"`
    must print `both 1.0 live True 77020`.

    Commit: `git add config/config-cent.toml src/trading_bot/cli.py` then `feat(config): cent live bot -> direction='both' rr_multiple=1.0 (deploy is the next, separate task)`.
  </action>
  <verify>
    <automated>.venv\Scripts\python.exe -m pytest tests/test_cli_live.py tests/test_config.py tests/test_tune_risk.py tests/test_bank_profits.py tests/test_short_and_filters.py -q -p no:cacheprovider --basetemp "C:\Users\joram\AppData\Local\Temp\opencode\pytest-bot"</automated>
  </verify>
  <done>
    config-cent.toml is the only config changed and shows direction="both" rr_multiple=1.0 (with [live]/[risk] untouched); load_config prints both/1.0/live/True/77020; live_start now logs direction and rr_multiple; the running bot is UNTOUCHED (no stop, no restart); committed.
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>task 5: supervised swap on the real cent bot — stop, start, and post-start verification (deployment is the FINAL step)</name>
  <what-built>
    The full both-direction live build is committed (Tasks 1-4) and the suite is green. This task swaps the RUNNING long-only cent bot (rr=2.0, in memory) for the new both rr1.0 build on the SAME account/symbol/magic (161693049 / XAUUSDc / 77020, D-1), using the battle-tested sentinel + taskkill + schtasks sequence from gold_weekend_stop.bat / tune_risk._restart_windows. Then it verifies the new process from its logs and writes the SUMMARY.
  </what-built>
  <how-to-verify>
    Do all of the following IN ORDER. Stop on the first failure and report (do NOT start a bot that did not clear its gate).

    1. DEPLOY GATE (must all pass before anything is stopped):
       - `.venv\Scripts\python.exe -m pytest tests/ -q -p no:cacheprovider --basetemp "C:\Users\joram\AppData\Local\Temp\opencode\pytest-bot"` -> full suite green.
       - Re-run the sell-path gate by name: `.venv\Scripts\python.exe -m pytest tests/test_live_engine_both.py -q -p no:cacheprovider --basetemp "C:\Users\joram\AppData\Local\Temp\opencode\pytest-bot"` -> green.
       - `git status --short` clean; `git log --oneline -5` shows the four feature commits.
       - Record the pre-swap identity: `schtasks /Query /TN trading-bot-cent` (task present), read `output\live_cent.pid`, and tail `output\live_cent.log` — the OLD bot is running long-only rr=2.0 (its live_start line shows no direction key). This is the bot being replaced.

    2. STOP (sentinel + kill, the gold_weekend_stop.bat ordering):
       - `New-Item -ItemType File -Force output\live_cent.stop | Out-Null` (sentinel: the supervisor exits cleanly once the bot process is gone and deletes the sentinel itself).
       - Read the pid: `$bpid = (Get-Content output\live_cent.pid -ErrorAction SilentlyContinue)`; if set, `taskkill /PID $bpid /F`; if the pidfile is absent, stop and report (nothing to kill is a problem, not a blessing).
       - Wait (up to ~60s) for the pidfile to disappear AND `schtasks /Query /TN trading-bot-cent` to show the task not Running (poll every 2s). Confirm no python process is left running config-cent (`Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'config-cent' }` -> none). Do NOT proceed to start until this is true — two supervisors on one bot is the failure mode this sequence exists to prevent.

    3. START:
       - `schtasks /Run /TN trading-bot-cent`.
       - Poll (up to ~300s) for a NEW pid in `output\live_cent.pid` different from the old one.

    4. POST-START VERIFICATION (this is the acceptance evidence):
       - `output\supervise_cent.log` tail: preflight ran against config-cent.toml and printed `[ ok ]` READY (terminal reachable, REAL account acknowledged, bars available, feed fresh) before the bot started.
       - `output\live_cent.log` tail: find the `event=live_start` line and confirm it carries `mode=live symbol=XAUUSDc magic=77020 direction=both rr_multiple=1.0` (this is why Task 4 added those fields). Also confirm no `live_stop`/`connect_failed` line after it.
       - Keep tailing until the first `event=bar_check` (new_bar True or False is fine — market dependent) or a graceful `bar_fetch_failed`/`setup_skipped`, proving the loop polls the broker. A short setup firing is NOT required for acceptance — the sell path was proven in Task 3.
       - Optional confirm via `preflight_live.py`: `.venv\Scripts\python.exe scripts\preflight_live.py --config config\config-cent.toml --real-account` exit 0.

    5. Write `.planning\quick\20260909-live-gold-both-direction\SUMMARY.md` on the model of the scalper SUMMARY: locked user decision and the measured context it overrides (both rr1.0 R +0.0810 / t +1.94 / clears no bar — deployed anyway on the user's informed call), what was built (sell path seams, direction config, side-aware engine, log side fields), the one intentional test update (to_log_fields "side"), the deploy timeline (old pid -> new pid, stop/start timestamps), the live_start verification line VERBATIM, the safety rails confirmed intact, and an honest status line: LIVE now runs direction=both rr_multiple=1.0 on 161693049/XAUUSDc/77020; every mechanical guard unchanged; the edge remains unproven per the measurement.
       Update `.planning\STATE.md` Quick Tasks table with the completion row (mirroring the scalper task's b2d1896 update).
       Commit: `git add .planning/quick/20260909-live-gold-both-direction/SUMMARY.md .planning/STATE.md` then `docs(quick): deploy direction=both rr1.0 to the live gold cent bot`.
  </how-to-verify>
  <resume-signal>
    Type "approved" once the live_start line shows direction=both rr_multiple=1.0 and the first bar_check/graceful poll appears, or describe what failed and at which numbered step.
  </resume-signal>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| config TOML -> live engine | `strategy.direction`/`rr_multiple` are trusted inputs deciding which side(s) real orders take; only validated values may reach the loop |
| live engine -> broker adapter | the engine dispatches real BUY/SELL market orders with SL/TP; a mis-priced or mis-sided request risks an unprotected or oversized position |
| broker adapter -> MT5 order_send | rounding, lot-grid, stop-distance and filling-mode validation happen here; a wrong price family (ask on a sell) is a broker rejection or worse |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-bd-01 | E | config strategy.direction | mitigate | validate_config whitelist ("long"\|"both") raises ValueError naming the key; live_start log echoes the loaded value so a wrong config is visible in the decision trail before any poll |
| T-bd-02 | E | engine short geometry/pricing | mitigate | single shared tp formula (tp = entry + rr×(entry−sl), STRAT-03) already direction-general; side-aware levels_are_tradable requires sl > entry > tp for shorts; risk measured at the BID (sl − bid) with rr/min_rr/daily-loss gates side-agnostic; short dry-run E2E pins entry 199.00/sl 199.91/tp 198.09 before deployment |
| T-bd-03 | E | MT5 sell translation | mitigate | place_market_sell reads the BID only, ORDER_TYPE_SELL, sl/tp rounded to digits, NaN refusal duplicated, `_check_stop_distance(..., sell=True)` mirrored so a stop inside trade_stops_level is refused not widened; pinned by fake-MT5 tests asserting the exact order_send dict |
| T-bd-04 | E | DryRunBroker sell leak | mitigate | place_market_sell contains ZERO references to the inner broker (structural, same as buy); order_plan carries side; E2E asserts inner ledger stays empty |
| T-bd-05 | T | SAFE-03 / guards on the new side | mitigate | SAFE-03 gate, weekend guard, session filter, min_rr, daily-loss halt, pending-equivalent dedup and the max_concurrent slot guard run BEFORE side dispatch on a shared code path — none were made side-conditional; full existing guard test matrix stays green unmodified |
| T-bd-06 | D | decision-log side ambiguity | mitigate | OrderRequest.side flows into to_log_fields and setup_detected/order_placed log lines (SAFE-02); watch_closes/trade_ledger key=value parsers ignore unknown additive tokens (verified regex/token shapes) |
| T-bd-07 | E | swap race on deployment | accept (mitigated by ordering) | stop sentinel + taskkill + verified process death BEFORE schtasks /Run, mirroring the battle-tested tune_risk/gold_weekend_stop sequence; two supervisors on one bot is prevented by waiting for the old pidfile to clear and the task to leave Running state |
</threat_model>

<verification>
- Full suite green at the end of every task; the golden long-path tests (test_backtest.py, test_live_engine.py, test_cli_live.py, test_mt5_broker.py, test_short_and_filters.py) are UNMODIFIED and green — the byte-identity proof for D-5.
- Task 3's mirrored-golden SHORT dry-run E2E is the sell-path gate: it must pass before Task 5 may stop the running bot.
- config-cent.toml loads with direction=both rr_multiple=1.0 mode=live enabled=true magic=77020 (Task 4 prints it).
- No backtest measurement is re-run (the scalper measurement stands as the reference).
- Task 5's post-start log shows the new live_start line VERBATIM with direction=both rr_multiple=1.0 and the supervisor log shows a READY preflight against the REAL account.
- One atomic git commit per task (Tasks 1-4 feature commits + Task 5 docs commit); git status clean at the deploy gate.
</verification>

<success_criteria>
- [ ] Broker sell path exists on the ABC and all three adapters; buy path byte-identical; OrderRequest carries side and side-agnostic risk_per_unit (Task 1, committed)
- [ ] strategy.direction validates to "long" (default) | "both" only; all committed configs still load (Task 2, committed)
- [ ] Live engine detects and trades SHORT setups in direction="both" with sell geometry and bid-priced risk; SHORT dry-run E2E through DryRunBroker proves the sell path places nothing; AIEngine gates shorts on the actual side (Task 3, committed)
- [ ] config-cent.toml is the only live config changed: rr_multiple 1.0 + direction="both"; live_start echoes both values (Task 4, committed)
- [ ] The running cent bot (161693049 / XAUUSDc / magic 77020) was swapped LAST via sentinel -> taskkill -> schtasks /Run only after full-suite green + short E2E; post-start logs confirm direction=both rr_multiple=1.0 mode=live (Task 5)
- [ ] Every mechanical safety rail intact: SAFE-03, weekend guard 19, session filter, min_rr, daily-loss halt, dedup, single-slot guard — none weakened for either side
- [ ] SUMMARY.md written with the deploy evidence and the honest note that the edge remains unproven; all commits atomic
</success_criteria>

<output>
After completion, SUMMARY.md lives at `.planning/quick/20260909-live-gold-both-direction/SUMMARY.md` (written by Task 5).
</output>
