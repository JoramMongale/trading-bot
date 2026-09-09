---
phase: quick-006-bank-profits
plan: 01
type: execute
wave: 1
depends_on: []
files_modified: [scripts/bank_profits.py, tests/test_bank_profits.py]
autonomous: true

must_haves:
  truths:
    - "User can see current balance, pinned base stake, and bankable excess (balance − base) in USC and an approximate R figure"
    - "First run auto-pins the current balance as the base stake unless --base is passed; --base updates and prints it clearly"
    - "--confirm appends one ledger line to output/profits_banked.log and prints the exact withdrawal amount with the instruction that the transfer itself is a manual Exness-portal action"
    - "Excess below the practical withdrawal minimum warns and suggests banking weekly"
    - "Broker down reports 'broker unavailable' gracefully (exit 2) and never places, modifies, or closes anything"
  artifacts:
    - path: "scripts/bank_profits.py"
      provides: "Read-only banking helper CLI (view / --base / --confirm)"
      min_lines: 110
    - path: "tests/test_bank_profits.py"
      provides: "Fake-broker + tmp-file coverage of all five truths"
      min_lines: 100
    - path: "output/bank_base.txt"
      provides: "Pinned base stake in USC (gitignored, created at runtime)"
    - path: "output/profits_banked.log"
      provides: "Ledger of banking events (gitignored, created on --confirm)"
  key_links:
    - from: "scripts/bank_profits.py"
      to: "trading_bot.broker.mt5._load_mt5 / _load_silicon_bridge"
      via: "lazy import inside _connect (never module-top), native→bridge fallback using cfg.live.bridge_host/bridge_port, initialize() guard"
      pattern: "_load_mt5|_load_silicon_bridge"
    - from: "scripts/bank_profits.py"
      to: "health_check.BOTS"
      via: "re-exported tag→config map (tests monkeypatch it to tmp copies)"
      pattern: "from health_check import BOTS"
    - from: "scripts/bank_profits.py"
      to: "output/bank_base.txt"
      via: "BASE_FILE module constant (tests monkeypatch to tmp_path); read on view, write on --base or first run"
    - from: "scripts/bank_profits.py"
      to: "output/profits_banked.log"
      via: "LEDGER module constant (tests monkeypatch to tmp_path); append on --confirm"
---

<objective>
Bank-the-profits helper for the live gold cent account.

Purpose: The bot compounds (sizing="percent", max_loss_pct_per_trade=20): after a TP the
balance grows and the NEXT trade re-risks 20% of the LARGER balance — re-risking banked
profit. The user's money rule is "trade with the R500, not with the profit": each trade
risks only the base stake, profits are physically moved out after each trade. This tool
makes the decision legible (how much is bankable right now) and records it (a ledger line),
while making crystal clear that the actual transfer is a manual Exness-portal action the
bot cannot perform.

Output: `scripts/bank_profits.py` (read-only) + `tests/test_bank_profits.py`. Runtime state
lives in gitignored `output/bank_base.txt` (base stake, USC) and `output/profits_banked.log`
(ledger). Live configs untouched, full suite stays green.

Design decisions (locked):
- Connection reuses the established per-script convention from monitor_trade.py / health_check.py
  / dashboard.py — there is NO shared broker helper in the repo; the lazy-import + native→bridge
  fallback try/except IS the pattern. Do not create a new helper module.
- `from trading_bot.broker.mt5 import _load_mt5, _load_silicon_bridge` happens INSIDE functions
  only (mirrors the MetaTrader5-never-at-module-top rule). Module must import cleanly with no
  MT5 package present.
- Default tag is `cent` (the live gold bot). BOTS comes from health_check re-export.
- USC → R estimate uses `usc / 100 * usd_rate` (the exact formula health_check.py line 234 uses),
  default `--usd-rate 18.0`, labelled as an estimate.
- Module-level `BASE_FILE` and `LEDGER` Path constants and module-level `MIN_BANKABLE_USC`
  / `DEFAULT_USD_RATE` so tests monkeypatch them to tmp_path / custom values.
</objective>

<execution_context>
@/Users/joram/.config/opencode/get-shit-done/workflows/execute-plan.md
@/Users/joram/.config/opencode/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/PROJECT.md
@scripts/monitor_trade.py
@scripts/health_check.py
@scripts/tune_risk.py
@config/config-cent.toml
@tests/test_tune_risk.py
@tests/test_dashboard.py
@src/trading_bot/broker/base.py
@src/trading_bot/broker/mt5.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Implement scripts/bank_profits.py</name>
  <files>scripts/bank_profits.py</files>
  <action>
    Create `scripts/bank_profits.py`, a stdlib-only, READ-ONLY banking helper. Module must
    import cleanly with no MetaTrader5 package installed — NO MetaTrader5/siliconmetatrader5
    import at module top level (the only MT5 touches are the lazy imports inside `_connect`).

    Module docstring: purpose (bank the profit so the next trade risks only the base stake),
    usage examples, exit codes (0 ok, 2 error/broker unavailable), and the safety model:
    READ-ONLY against the broker — no order_send, no position modification, no close anywhere
    in the file; the actual withdrawal is a MANUAL action in the Exness portal that this tool
    only reports and logs.

    Structure:
    - `ROOT = Path(__file__).resolve().parent.parent`; `sys.path.insert(0, str(ROOT / "src"))`
      and `(0, str(ROOT / "scripts"))` (same as monitor_trade.py).
    - `from health_check import BOTS` (noqa: E402) — re-exported so tests monkeypatch
      `bank_profits.BOTS` to tmp config copies (tune_risk.py convention).
    - Module constants: `BASE_FILE = ROOT / "output" / "bank_base.txt"`,
      `LEDGER = ROOT / "output" / "profits_banked.log"`, `MIN_BANKABLE_USC = 1000.0`,
      `DEFAULT_USD_RATE = 18.0`.
    - `def _connect(cfg)` -> mt5 handle. LAZILY imports inside the function:
      `from trading_bot.broker.base import BrokerUnavailableError` and
      `from trading_bot.broker.mt5 import _load_mt5, _load_silicon_bridge`. Logic, mirroring
      monitor_trade.py lines 133-146: try `_load_mt5()`; on BrokerUnavailableError fall back
      to `_load_silicon_bridge(cfg.live.bridge_host, cfg.live.bridge_port)` (NOT hardcoded
      localhost — the config is authoritative); then `if not mt5.initialize(): raise
      BrokerUnavailableError("terminal initialize failed")`. Return the handle.
    - `def read_base(path) -> float | None`: return float of file content or None on
      missing/empty/ValueError.
    - `def pin_base(path, value) -> None`: write the value with 2 decimals (e.g.
      `"3000.00\n"`) — plain write_text is fine (tune_risk's atomic dance is for editing
      live CONFIG files; this state file is gitignored scratch).
    - `def r_est(usc: float, rate: float) -> float`: return `usc / 100 * rate`.
    - `def main(argv=None)`:
      - argparse: `--tag` (choices=sorted(BOTS), default="cent"), `--base` (float, USC),
        `--confirm` (store_true), `--usd-rate` (float, default DEFAULT_USD_RATE).
      - Load `cfg = load_config(ROOT / BOTS[a.tag])` (lazy `from trading_bot.config import
        load_config, live_symbol` inside main). Connect via `_connect(cfg)`. On
        BrokerUnavailableError: print a graceful line starting `broker unavailable:` with the
        exception text (mirror monitor_trade's "PROBLEMS FOUND" exit-2 spirit but keep it
        one-line friendly for cron) and `return 2`.
      - `acct = mt5.account_info()`; `balance = acct.balance`; note `acct.currency` for the
        header line (expected USC).
      - Base stake resolution, in this order:
        1. `--base` given → `pin_base(BASE_FILE, value)`, print
           `base pinned = {value:.2f} USC` clearly.
        2. BASE_FILE exists → read it.
        3. First run (no file, no --base) → `pin_base(BASE_FILE, balance)`, print
           `first run: pinned base = {balance:.2f} USC (current balance)`.
      - Print the view block (USC + R estimate labelled with the rate):
        `balance {b:.2f} USC  base {base:.2f} USC  bankable {excess:.2f} USC  (~R{r:.2f}, usd_rate {rate})`
        where `excess = balance - base` (can be negative → print `0.00` for bankable when
        negative/zero and say "nothing to bank").
      - If `excess < MIN_BANKABLE_USC` (and excess > 0): print a WARNING line: excess below
        the practical withdrawal minimum (~$10); frequent small withdrawals may be
        uneconomical — consider banking weekly instead.
      - If `--confirm` and excess > 0: append ONE line to LEDGER (create parent dir):
        `{utc:%Y-%m-%d %H:%M:%S} event=profits_banked base={base:.2f} balance={balance:.2f} excess={excess:.2f} balance_after={base:.2f} usd_rate={rate} r_est={r:.2f}`
        (UTC via `datetime.now(timezone.utc)`, same key=value token style as closes.log).
        Then print the exact withdrawal amount (`withdraw {excess:.2f} USC ≈ ${excess/100:.2f}`)
        and the mandatory instruction, verbatim in spirit: the transfer is a MANUAL action in
        the Exness portal (account {acct.login} @ {acct.server}) — the bot cannot withdraw;
        this tool only records the decision. Do NOT imply the bot can move money.
      - Return 0.
    - `if __name__ == "__main__": raise SystemExit(main())`.

    AVOID: any write path that touches config/, any order/position API call, importing
    MetaTrader5 or siliconmetatrader5 at module top, hardcoding localhost:8001 (use
    cfg.live.bridge_*).
  </action>
  <verify>
    `python3 -c "import sys; sys.path.insert(0, 'src'); sys.path.insert(0, 'scripts'); import bank_profits; print('imports clean')"` succeeds with NO MetaTrader5/siliconmetatrader5 installed import attempt.
    `python3 scripts/bank_profits.py --help` exits 0 and lists --tag/--base/--confirm/--usd-rate.
    Grep the file: no `order_send`, no `positions_get`, no top-level `import MetaTrader5` / `import siliconmetatrader5`.
  </verify>
  <done>
    `scripts/bank_profits.py` exists, imports cleanly on this Mac, exposes the full CLI, and is structurally read-only (no order/position mutation calls anywhere; MT5 imports confined to `_connect`).
  </done>
</task>

<task type="auto">
  <name>Task 2: Write tests/test_bank_profits.py and keep the suite green</name>
  <files>tests/test_bank_profits.py</files>
  <action>
    Create `tests/test_bank_profits.py` following the established script-test conventions of
    tests/test_tune_risk.py and tests/test_dashboard.py:

    Setup:
    - `ROOT = Path(__file__).resolve().parent.parent`; `sys.path.insert(0, str(ROOT / "scripts"))`
      and the src path as the sibling tests do. `import bank_profits` (noqa: E402).
    - `REAL_CENT = ROOT / "config" / "config-cent.toml"`.
    - A `_FakeBroker` class exposing the surface `_connect` consumers use: `initialize() -> True`,
      `last_error() -> "no error"`, `account_info() -> SimpleNamespace(login=161693049,
      server="Exness-MT5Real21", currency="USC", balance=<settable>)`.
    - `@pytest.fixture def env(tmp_path, monkeypatch)`: point `bank_profits.BASE_FILE` and
      `bank_profits.LEDGER` at tmp_path files; point `bank_profits.BOTS` at
      `{"cent": str(tmp_path / "config-cent.toml")}` (copy REAL_CENT bytes); patch
      `trading_bot.broker.mt5._load_mt5` and `trading_bot.broker.mt5._load_silicon_bridge` to
      return a `_FakeBroker` (patch on `trading_bot.broker.mt5` — `_connect` imports them
      lazily from there, so the patch is picked up per call). Since `_connect` falls through
      native→bridge, patching BOTH lets you also test the fallback by making only `_load_mt5`
      raise BrokerUnavailableError.

    Tests (cover the five must-have truths):
    1. `test_first_run_pins_current_balance`: no base file → `main([])` returns 0, stdout
       contains "first run: pinned base" and the balance value; BASE_FILE now contains the
       balance; bankable shows 0.00.
    2. `test_base_flag_pins_and_prints`: `main(["--base", "3000"])` writes 3000.00 to BASE_FILE
       and prints "base pinned"; a subsequent `main([])` shows bankable = balance − 3000.
    3. `test_broker_unavailable_exits_2`: make BOTH `_load_mt5` and `_load_silicon_bridge`
       raise BrokerUnavailableError("nope") → `main([])` returns 2 and prints a line starting
       with "broker unavailable".
    4. `test_bridge_fallback_used`: `_load_mt5` raises, `_load_silicon_bridge` returns the fake
       → `main([])` returns 0 (fallback path works, config host/port read).
    5. `test_sub_minimum_excess_warns`: balance = base + 500 → stdout contains the weekly-banking
       warning.
    6. `test_confirm_appends_ledger_and_prints_instruction`: balance = base + 2500 →
       `main(["--confirm"])` returns 0, LEDGER has exactly ONE line containing
       `event=profits_banked`, `base=`, `excess=2500.00`, `balance_after=` (== base), and stdout
       contains "manual" and the withdrawal amount; base file unchanged by --confirm.
    7. `test_confirm_without_excess_does_nothing`: balance == base → `main(["--confirm"])`
       returns 0 and LEDGER does NOT exist.
    8. `test_usd_rate_changes_r_estimate`: balance = base + 2000 → R estimate at default 18.0
       is 360.00; with `--usd-rate 20` it is 400.00 (assert the printed R value).
    - Use `capsys` for stdout assertions. Never touch the real configs (BOTS is monkeypatched),
    never touch the real output/ dir (BASE_FILE/LEDGER are monkeypatched), no broker network.

    Then run the FULL suite and confirm nothing regressed.
  </action>
  <verify>
    `python3 -m pytest tests/test_bank_profits.py -q` passes (8 tests).
    `python3 -m pytest tests/ -q` stays fully green (270 existing + 8 new = 278).
  </verify>
  <done>
    `tests/test_bank_profits.py` exists with fake-broker + tmp-file coverage of all five truths; full suite green (278 passing), live configs and output/ untouched by tests.
  </done>
</task>

</tasks>

<verification>
- `python3 scripts/bank_profits.py --help` exits 0 (CLI contract intact).
- `python3 -m pytest tests/ -q` green — 278 passed, zero failures (full suite, no stubs left behind).
- Grep `scripts/bank_profits.py` for `order_send|positions_get|order_modify|close` → no matches outside the docstring (structural read-only proof).
- Optional user smoke (NOT required for this plan): with the siliconmt5 container up, run
  `python3 scripts/bank_profits.py` and `python3 scripts/bank_profits.py --confirm` once against
  the real cent account to see live balance/base/bankable and record the first banking decision.
</verification>

<success_criteria>
- User can see balance, pinned base, and bankable excess in USC + R estimate in one command.
- First run pins itself; `--base` repins deliberately.
- `--confirm` appends one ledger line and prints the exact withdrawal amount with the
  explicit manual-transfer instruction (never implies the bot withdraws).
- Sub-minimum excess warns with the weekly-banking suggestion.
- Broker unreachable → graceful "broker unavailable", exit 2, nothing touched.
- Tests cover all five truths with a fake broker + tmp files; full suite stays green.
</success_criteria>

<output>
After completion, create `.planning/quick/006-bank-profits/006-SUMMARY.md`
</output>
