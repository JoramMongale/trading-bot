"""Live engine — poll closed bars, detect setups, buy at market.

The phase's core loop (phase success criteria 1, 2, 5 + SAFE-01/SAFE-02).
On each poll the engine fetches only CLOSED bars from the broker (never the
forming bar), runs the SAME pure strategy chain the backtester uses, and when
the last closed bar shows a setup it builds the order with the SAME arithmetic
as ``backtest/engine.py`` (entry=resistance, sl=support−sl_buffer,
tp=entry+rr_multiple×(entry−sl), rr_multiple from ``[strategy]``), then
dedup-checks (equivalent pending order / open position), safety-checks
(SAFE-03), risk-checks the projected loss against the account, and buys at
market via the broker.

The entry is a MARKET buy, not a Buy Stop at ``entry``: the setup fires on a
close ABOVE resistance, so that level is already behind the market and a stop
order there is rejected outright. The backtest filled at the next bar's open in
339 of its 340 trades, and buying on the poll after the signal bar is the
faithful translation of that. ``entry`` remains the REFERENCE level — risk is
measured from it, and the realised fill is logged beside it so the drift from
the backtest stays visible.

Every decision is a ``log_decision`` line (SAFE-02). The engine imports only
pandas, the strategy package, the broker base contract, live.safety, and
logging_utils — never the Windows-only MetaTrader5 package (RESEARCH.md).
"""

from __future__ import annotations

import math
from dataclasses import replace

import pandas as pd

from trading_bot.broker.base import (
    BrokerRejectedError,
    BrokerUnavailableError,
    OrderRequest,
)
from trading_bot.config import live_symbol
from trading_bot.live.safety import SafetyError, verify_execution_allowed
from trading_bot.logging_utils import log_decision
from trading_bot.strategy.levels import support_resistance
from trading_bot.strategy.signals import detect_setups
from trading_bot.strategy.swings import detect_swings


def _round2(value: float) -> float:
    """XAUUSD 2-dp quoting at the decision-log boundary (CLI convention)."""
    return round(value, 2)


def levels_are_tradable(entry: float, sl: float, tp: float) -> bool:
    """True when the three prices describe a trade that can actually be exited.

    ``support``/``resistance`` are NaN until a confirmed swing of that type
    enters the lookback window, and the two sides fill in independently — a
    swing HIGH can confirm while no swing LOW has, which makes ``setup`` fire
    (it only reads resistance) with ``support`` still NaN. That yields
    ``sl = nan``, ``tp = nan``.

    Nothing downstream catches that on its own. Every NaN comparison is False,
    so the backtest's ``low <= sl`` and ``high >= tp`` both fail forever and
    the trade never exits, and the live risk gate's ``loss > cap`` is False too
    — it waves the order through and the broker is asked to open a position
    with no stop loss. On full history this never fires, but a live bot fetches
    only ~69 bars and starts fresh on every restart, and 6 of 45 sampled
    mid-history windows produced such a setup.

    A non-positive stop distance is rejected on the same grounds: it makes
    ``tp <= entry``, so the trade has no target and no risk to size against.
    """
    if not all(math.isfinite(v) for v in (entry, sl, tp)):
        return False
    return entry > sl


def in_session(hours: list[int], bar_time) -> bool:
    """Is this bar inside the configured trading window?

    Hours come off the bar's own clock (broker server time), never the host's.
    Half-open [start, end); a start above the end wraps past midnight.
    """
    if not hours:
        return True
    start, end = hours
    h = bar_time.hour
    return start <= h < end if start <= end else (h >= start or h < end)


def in_weekend(bar_time, stop_hour: int = 0, resume_hour: int = 21) -> bool:
    """True when this bar falls inside the no-new-entries weekend window.

    Gold is shut Friday 21:00 to Sunday 21:00 UTC, and a broker-side stop
    cannot protect a Sunday opening gap that jumps straight through it — so new
    entries must stop before the Friday close and not resume until the market
    reopens. ``stop_hour`` is the UTC hour of FRIDAY after which entries are
    refused (0 = disabled); ``resume_hour`` is the UTC hour of SUNDAY at which
    they resume. Hours come off the bar's own clock (broker server time), the
    same basis as :func:`in_session`. Pure: no broker, no clock, no I/O.
    """
    if not stop_hour:
        return False
    if bar_time.weekday() == 4:  # Friday
        return bar_time.hour >= stop_hour
    if bar_time.weekday() == 5:  # Saturday
        return True
    if bar_time.weekday() == 6:  # Sunday
        return bar_time.hour < resume_hour
    return False


def position_size(
    cfg, balance: float, risk_per_unit: float, price: float | None = None,
    sr=None,
) -> float:
    """Lots to trade so the stop costs ``max_loss_pct_per_trade`` of balance.

    Returns 0.0 when the answer is below the broker's minimum lot, which is a
    real and common outcome rather than an error: the stop distance is set by
    market structure, so on a small account the smallest tradable position
    still risks more than the policy allows. There is nothing to round to, and
    rounding UP to the minimum would silently break the very cap being applied,
    so the caller skips the trade.

    Sizing floors onto the lot grid for the same reason — never up.
    """
    if risk_per_unit <= 0 or not math.isfinite(risk_per_unit):
        return 0.0
    budget = balance * cfg.risk.max_loss_pct_per_trade / 100.0

    # Risk per lot, in ACCOUNT currency. Taken from the broker when available:
    # tick_value already absorbs the instrument's contract size AND any
    # conversion from the symbol's profit currency to the account's. Deriving
    # it from cfg.trading.contract_size instead was wrong in two directions at
    # once on a cent account — 100x too large from the contract size, 100x too
    # small from USD-vs-USC — and the errors cancelled into plausible nonsense.
    if sr is not None:
        per_lot = sr.money_risk(risk_per_unit, 1.0)
        lot_min, lot_step = sr.volume_min, sr.volume_step
    else:
        per_lot = risk_per_unit * cfg.trading.contract_size
        lot_min, lot_step = cfg.risk.lot_min, cfg.risk.lot_step
    if per_lot <= 0 or not math.isfinite(per_lot):
        return 0.0
    raw = budget / per_lot

    # Exposure ceiling, which bounds something the risk cap does not. The cap
    # bounds the loss IF THE STOP HOLDS; a gap jumps past the stop and the loss
    # is then set by position size alone. A tight stop makes those two wildly
    # different: a $5.86 stop on $5,000 sizes to 17 lots of gold, $7.7M
    # notional, where a 1% gap costs 15x the account.
    if cfg.risk.max_leverage > 0 and price and price > 0:
        max_notional = balance * cfg.risk.max_leverage
        if sr is not None:
            # SymbolRisk.notional answers this from tick economics alone, in
            # ACCOUNT currency, so no contract size is involved and there is
            # nothing to convert -- see its docstring.
            #
            # Sizing from the broker used to SKIP this ceiling entirely, on the
            # argument that it had never bound. Measured, that margin is thin:
            # at a 2% cap the ceiling engages below a $4.60 gold stop and the
            # tightest stop this strategy has produced is $5.33 -- 14% away,
            # not the comfortable distance "never bound" implies.
            #
            # It matters because the two limits bound different things. The risk
            # cap bounds the loss IF THE STOP HOLDS. A gap jumps past the stop
            # and the loss is then set by position size alone. The tighter the
            # stop, the larger the position for the same 2%, so the exposure is
            # highest exactly when the stop is least able to contain it: a $5.33
            # stop sizes to 17x gearing, where a 3% gap costs ~51% of the
            # account rather than the 2% the cap promised.
            #
            # An unreported contract size gives NaN, and min(raw, NaN) is NaN in
            # IEEE terms but silently returns `raw` under Python's min(), so it
            # is checked explicitly: unknown exposure must not read as unlimited.
            unit_notional = sr.notional(price, 1.0)
            if math.isfinite(unit_notional) and unit_notional > 0:
                raw = min(raw, max_notional / unit_notional)
        else:
            raw = min(raw, max_notional / (price * cfg.trading.contract_size))
    # round() before floor() absorbs binary representation error: an exact
    # 0.10 lots computes as 0.0999999999999 and would floor a whole step down,
    # systematically under-sizing every trade that lands on a grid point. A
    # genuine 9.7 steps still floors to 9. Same treatment as _resolve_volume.
    steps = math.floor(round(raw / lot_step, 9))
    lots = round(steps * lot_step, 8)
    return lots if lots >= lot_min else 0.0


def projected_loss(cfg, request) -> float:
    """Account-currency loss if this trade stops out, at the configured lot.

    ``contract_size`` converts a quote-currency move into money: XAUUSD is 100
    oz per lot, so 0.01 lots is 1 oz and a $1 adverse move is $1. The stop is
    structural (support − buffer), so this number is set by the market, not by
    the account — which is exactly why it has to be checked against the account
    before the order goes out.
    """
    return request.risk_per_unit * request.volume * cfg.trading.contract_size


class LiveEngine:
    """One poll = fetch bars -> detect setup -> dedup -> safety -> risk -> buy.

    Args:
        cfg:    Loaded project Config (``.data``/``.strategy``/``.trading``/
                ``.live`` tables carry everything the loop needs).
        broker: Any BrokerClient (SimulatedBroker, DryRunBroker wrapper,
                MT5Broker from plan 02-02) — the engine programs against the
                ABC, never raw MT5 calls.
        logger: logging.Logger from ``logging_utils.get_logger`` (SAFE-02).
    """

    def __init__(self, cfg, broker, logger):
        self._cfg = cfg
        self._broker = broker
        self._logger = logger
        # Dedup across polls: a setup must not re-fire on a bar already seen.
        self._last_bar_time: pd.Timestamp | None = None
        # Latest strategy-output frame (plan 03-01): the AI layer's regime check
        # and proposal gate build their context from it.
        self._last_bars_frame: pd.DataFrame | None = None
        # Daily loss limit: balance at the first placement-check of each day.
        # Balance moves only when a trade CLOSES, so this tracks realised P&L —
        # an open position drifting against you does not trip the limit, and a
        # stop-out does. That is the intended reading of "down for the day".
        self._day: object | None = None
        self._day_start_balance: float | None = None

    def _n_bars(self) -> int:
        """Bars of history to fetch on each poll.

        ``[live] fetch_bars`` (plan 03-02) widens the window when set > 0; the
        default 0 keeps the strategy-minimum formula byte-identical for every
        existing config. The extra history only feeds the AI layer's regime
        check — S/R expiry is window-bounded, so detection never changes.
        """
        if self._cfg.live.fetch_bars > 0:
            return self._cfg.live.fetch_bars
        cfg = self._cfg
        return (
            cfg.strategy.sr_lookback
            + cfg.strategy.fractal_left
            + cfg.strategy.fractal_right
            + 5
        )

    def _ai_gate(self, entry: float, sl: float, tp: float, bar_time) -> dict | None:
        """AI-layer seam (plan 03-01). Default: no AI, proceed unchanged.

        Called from :meth:`on_setup` after the dedup/slot guards and before the
        safety gate. The AIEngine subclass overrides it to consult the model and
        gate the setup. Returning a dict short-circuits ``on_setup`` with that
        event; returning ``None`` proceeds to safety/risk/placement unchanged.
        """
        return None

    def poll_once(self) -> dict:
        """Run ONE poll iteration and return the event dict describing it.

        Returns (all JSON-serializable; ``bar`` is an ISO string):
            {"event": "bar_fetch_failed", "error": str}      broker unavailable
            {"event": "bar_check", "new_bar": False}         same bar / no data
            {"event": "bar_check", "new_bar": True, "setup": False,
             "bar": iso}                                     closed bar, no setup
            order event from :meth:`on_setup`                closed bar, setup
        """
        cfg = self._cfg

        # 1) Fetch only CLOSED bars (broker contract, EXEC-01). Graceful when
        #    MT5/the terminal is unavailable — log and report, never crash.
        try:
            df = self._broker.fetch_rates(
                live_symbol(cfg), cfg.data.timeframe, self._n_bars()
            )
        except BrokerUnavailableError as exc:
            log_decision(self._logger, "bar_fetch_failed", reason=str(exc))
            return {"event": "bar_fetch_failed", "error": str(exc)}

        # 2) No data at all -> nothing to check.
        if df.empty:
            log_decision(self._logger, "bar_check", new_bar=False, reason="no_data")
            return {"event": "bar_check", "new_bar": False}

        # 3) Same closed bar as the last poll -> never re-evaluate it.
        new_bar_time = df.index[-1]
        if self._last_bar_time is not None and new_bar_time <= self._last_bar_time:
            return {"event": "bar_check", "new_bar": False}
        self._last_bar_time = new_bar_time

        # 4) Shared strategy chain — the exact Pass-A pipeline from
        #    backtest/engine.py (SAFE-01): swings -> S/R -> setups.
        df = df.copy()  # CoW-friendly; never mutate the broker's frame
        df = detect_swings(df, cfg.strategy.fractal_left, cfg.strategy.fractal_right)
        df = support_resistance(df, cfg.strategy.sr_lookback)
        df = detect_setups(df)

        # Keep the strategy-output frame for the AI layer (plan 03-01): the
        # regime check and the proposal gate both build their context from it.
        self._last_bars_frame = df

        # 5) Decide on the LAST CLOSED bar only (no lookahead).
        setup = bool(df["setup"].iloc[-1])

        # Session filter. Deliberately applied AFTER the whole strategy chain
        # has run, so levels are built from every bar exactly as the backtest
        # builds them; this only decides whether to act. Logged rather than
        # silently dropped, so the decision trail shows what was passed up.
        if setup and not in_session(cfg.live.session_hours, new_bar_time):
            log_decision(
                self._logger,
                "setup_skipped",
                reason="outside_session",
                bar=new_bar_time.isoformat(),
                hour=int(new_bar_time.hour),
                session=list(cfg.live.session_hours),
            )
            return {
                "event": "setup_skipped",
                "reason": "outside_session",
                "bar": new_bar_time.isoformat(),
            }

        # Weekend guard (04-01): refuse a NEW entry inside the closing window
        # even if the scheduled Friday stop is late or missed. Same model as
        # the session filter — suppress ACTING, never the detection chain.
        if setup and in_weekend(
            new_bar_time,
            cfg.live.weekend_stop_hour,
            cfg.live.weekend_resume_hour,
        ):
            log_decision(
                self._logger,
                "setup_skipped",
                reason="weekend",
                bar=new_bar_time.isoformat(),
                weekday=int(new_bar_time.weekday()),
                hour=int(new_bar_time.hour),
                stop_hour=cfg.live.weekend_stop_hour,
                resume_hour=cfg.live.weekend_resume_hour,
            )
            return {
                "event": "setup_skipped",
                "reason": "weekend",
                "bar": new_bar_time.isoformat(),
            }

        if not setup:
            log_decision(
                self._logger,
                "bar_check",
                new_bar=True,
                setup=False,
                bar=new_bar_time.isoformat(),
            )
            return {
                "event": "bar_check",
                "new_bar": True,
                "setup": False,
                "bar": new_bar_time.isoformat(),
            }

        # 6) Setup: same arithmetic as backtest/engine.py (STRAT-03) — the
        #    target is rr_multiple x the stop distance, where rr_multiple comes
        #    from [strategy] (default 1.0 = the exact 1:1 that has been
        #    measured live; 2.0 moves the target twice as far away). The log
        #    gets 2-dp prices; the OrderRequest keeps full precision.
        entry = float(df["resistance"].iloc[-1])
        sl = float(df["support"].iloc[-1] - cfg.strategy.sl_buffer)
        tp = entry + cfg.strategy.rr_multiple * (entry - sl)
        log_decision(
            self._logger,
            "setup_detected",
            bar=new_bar_time.isoformat(),
            entry=_round2(entry),
            sl=_round2(sl),
            tp=_round2(tp),
        )
        return self.on_setup(entry, sl, tp, new_bar_time)

    def on_setup(
        self, entry: float, sl: float, tp: float, bar_time: pd.Timestamp
    ) -> dict:
        """Dedup -> safety gate -> risk gate -> place. Returns the order event dict.

        ``entry``/``sl``/``tp`` carry FULL precision into the OrderRequest
        (the wire); the decision log rounds them to 2 dp (XAUUSD quoting).
        """
        cfg = self._cfg
        req = OrderRequest(
            symbol=live_symbol(cfg),
            volume=cfg.trading.lot,  # replaced below when sizing="percent"
            entry=entry,
            sl=sl,
            tp=tp,
            magic=cfg.live.magic_number,
            deviation=cfg.live.deviation,
            comment=cfg.live.comment,
        )
        bar = bar_time.isoformat()

        # 0) Refuse levels that cannot describe an exitable trade. This runs
        #    FIRST because every later guard reads these numbers and a NaN
        #    silently defeats all of them — see levels_are_tradable.
        if not levels_are_tradable(entry, sl, tp):
            log_decision(
                self._logger,
                "order_skipped",
                reason="invalid_levels",
                bar=bar,
                entry=entry,
                sl=sl,
                tp=tp,
                detail="support/resistance incomplete or stop not below entry",
            )
            return {"event": "order_skipped", "reason": "invalid_levels"}

        # 1) Dedup: an equivalent order is already pending (phase success
        #    criterion 5 — never double-place the same setup). Market entries
        #    leave nothing pending, so this normally finds nothing; it still
        #    runs because an order left armed by an earlier build, or placed by
        #    hand in the terminal, holds the same slot.
        pending = self._broker.pending_orders(live_symbol(cfg), cfg.live.magic_number)
        if any(p.equivalent_to(req) for p in pending):
            log_decision(
                self._logger,
                "order_skipped",
                reason="pending_order_equivalent",
                bar=bar,
                entry=_round2(entry),
            )
            return {"event": "order_skipped", "reason": "pending_order_equivalent"}

        # 1b) Armed orders and open positions share one budget of
        #     cfg.risk.max_concurrent slots, and that number MUST match what the
        #     backtest was measured at. The two are one system: if live runs
        #     more slots than the backtest modelled, every statistic it produced
        #     (PF, max DD, per-trade risk) understates the real exposure.
        #
        #     Measured out-of-sample on gold, 2 slots leaves R per trade
        #     essentially unchanged (+0.1183 -> +0.1164) while doubling the
        #     sample, so t rises 1.25 -> 1.73. The single-slot guard was
        #     declining trades, not bad trades. 3+ slots degrades the edge
        #     materially, which is why this is a small number and not "off".
        open_positions = self._broker.positions(
            live_symbol(cfg), cfg.live.magic_number
        )
        slots_used = len(open_positions) + len(pending)
        if slots_used >= cfg.risk.max_concurrent:
            # Reasons stay distinct because they mean different things: a
            # position is exposed to the market, an unfilled order is not.
            reason = "position_open" if open_positions else "pending_order"
            log_decision(
                self._logger,
                "order_skipped",
                reason=reason,
                bar=bar,
                entry=_round2(entry),
                slots_used=slots_used,
                max_concurrent=cfg.risk.max_concurrent,
            )
            return {"event": "order_skipped", "reason": reason}

        # 2) AI-layer seam (plan 03-01). Runs AFTER dedup/slots so a duplicate
        #    or slot-full setup never costs an API call, and BEFORE the safety
        #    gate. The default implementation is a no-op (returns None); the
        #    AIEngine subclass overrides it to consult the model and gate the
        #    setup. A returned dict short-circuits on_setup with that event.
        ai_decision = self._ai_gate(entry, sl, tp, bar_time)
        if ai_decision is not None:
            return ai_decision

        # 3) Safety gate (SAFE-03): demo-only enforcement before placement.
        #    account_info() is fetched once and reused by the risk gate below —
        #    two round trips would let the balance move between the check that
        #    authorises the trade and the check that sizes it.
        try:
            account = self._broker.account_info()
            verify_execution_allowed(self._cfg, account)
        except SafetyError as exc:
            log_decision(
                self._logger,
                "order_skipped",
                reason="safety_blocked",
                detail=str(exc),
                bar=bar,
            )
            return {
                "event": "order_skipped",
                "reason": "safety_blocked",
                "detail": str(exc),
            }

        # 4) Price the trade against the MARKET, not the reference level.
        #    A market buy crosses the ask, and the setup only fires once price
        #    has closed ABOVE resistance, so the ask is always past the
        #    reference entry. Sizing and the risk cap both read off the
        #    reference understate the real risk, and understate it most when
        #    the stop is tight: a live M1 trade was sized for $49.10 against a
        #    $50.42 budget and actually risked $56.97, 13% over its own cap.
        #
        #    sl/tp keep the levels the strategy computed — the backtest also
        #    books them off the reference and fills at the market, so leaving
        #    them alone is what keeps live and simulated comparable. Only the
        #    RISK ARITHMETIC moves to the ask.
        try:
            q = self._broker.quote(live_symbol(cfg))
            # Tick economics in ACCOUNT currency — the only correct basis for
            # both sizing and the cap on an instrument whose contract size or
            # profit currency differs from what config assumes.
            sr = self._broker.symbol_risk(live_symbol(cfg))
        except BrokerUnavailableError as exc:
            # Covers a missing quote AND a symbol whose contract specs have
            # not loaded. Sizing off either is guesswork with real money.
            log_decision(self._logger, "order_skipped", reason="no_quote",
                         bar=bar, detail=str(exc))
            return {"event": "order_skipped", "reason": "no_quote"}

        entry_at_market = q.ask
        risk_at_market = entry_at_market - sl
        reward_at_market = tp - entry_at_market
        if risk_at_market <= 0 or not math.isfinite(risk_at_market):
            log_decision(self._logger, "order_skipped", reason="invalid_levels",
                         bar=bar, ask=_round2(entry_at_market), sl=_round2(sl),
                         detail="market is already at or below the stop")
            return {"event": "order_skipped", "reason": "invalid_levels"}

        # Has the market already run away from the setup? The levels imply
        # cfg.strategy.rr_multiple:1; if what is actually on offer has decayed
        # past min_rr, this is no longer the trade that was tested and taking
        # it is chasing.
        rr = reward_at_market / risk_at_market
        if cfg.risk.min_rr > 0 and rr < cfg.risk.min_rr:
            log_decision(
                self._logger, "order_skipped", reason="rr_degraded", bar=bar,
                entry=_round2(entry), ask=_round2(entry_at_market),
                slippage=_round2(entry_at_market - entry),
                rr=round(rr, 3), min_rr=cfg.risk.min_rr,
            )
            return {"event": "order_skipped", "reason": "rr_degraded", "rr": rr}

        # 5) Daily loss limit. Checked before sizing, because once the day is
        #    down past its budget the correct size is none. Compared against
        #    the balance at the first placement-check of the day, so it counts
        #    realised losses only.
        day = bar_time.date()
        if self._day != day:
            self._day, self._day_start_balance = day, account.balance
        if cfg.risk.max_daily_loss_pct > 0 and self._day_start_balance:
            down = self._day_start_balance - account.balance
            budget = self._day_start_balance * cfg.risk.max_daily_loss_pct / 100.0
            if down >= budget:
                log_decision(
                    self._logger,
                    "order_skipped",
                    reason="daily_loss_limit",
                    bar=bar,
                    down_today=_round2(down),
                    day_budget=_round2(budget),
                    day_start_balance=_round2(self._day_start_balance),
                    balance=_round2(account.balance),
                )
                return {"event": "order_skipped", "reason": "daily_loss_limit",
                        "down_today": down, "day_budget": budget}

        # 6) Position sizing. In "percent" mode the position is sized so the
        #    stop costs exactly the cap, which is what turns the cap from a
        #    veto into a policy and lets the account compound. In "fixed" mode
        #    the configured lot stands and the gate below can only block.
        if cfg.risk.sizing == "percent":
            lots = position_size(cfg, account.balance, risk_at_market,
                                 entry_at_market, sr=sr)
            if lots <= 0:
                log_decision(
                    self._logger,
                    "order_skipped",
                    reason="below_min_lot",
                    bar=bar,
                    entry=_round2(entry),
                    sl=_round2(sl),
                    risk_per_unit=_round2(risk_at_market),
                    balance=_round2(account.balance),
                    detail=(
                        f"{cfg.risk.max_loss_pct_per_trade}% of "
                        f"{account.balance:.2f} cannot buy {cfg.risk.lot_min} lots "
                        "at this stop distance"
                    ),
                )
                return {"event": "order_skipped", "reason": "below_min_lot"}
            req = replace(req, volume=lots)

        # 7) Risk gate: refuse a trade whose stop-out costs more than the
        #    configured share of the account. The stop is structural, so its
        #    size is decided by the market and nothing upstream bounds it. In
        #    "percent" mode sizing has already satisfied this and the gate is a
        #    backstop; in "fixed" mode it is the only thing standing between a
        #    structural stop and an account that cannot absorb it.
        # Priced at the ask AND in account currency, so this is the loss the
        # account will actually take if the stop is hit — not the one the
        # reference level implies, nor one denominated in the symbol's profit
        # currency when the account is denominated in something else.
        loss = sr.money_risk(risk_at_market, req.volume)
        cap = account.balance * cfg.risk.max_loss_pct_per_trade / 100.0
        # Fail CLOSED on a loss that cannot be compared: `nan > cap` is False,
        # so a naive `if loss > cap` treats an unknown risk as an acceptable
        # one. A gate that cannot evaluate the trade must block it.
        #
        # The 1e-9 is representation error, not risk tolerance. "percent"
        # sizing deliberately targets the cap exactly, and $9.100000000000108
        # vs $9.10 is the same number in binary floating point — without this
        # the gate rejects every percent-sized trade and the mode never places
        # anything. It is a RELATIVE epsilon at dust scale, so it cannot let a
        # meaningfully over-budget trade through: one lot step of risk is many
        # orders of magnitude larger.
        if not math.isfinite(loss) or loss > cap * (1 + 1e-9):
            log_decision(
                self._logger,
                "order_skipped",
                reason="risk_exceeded",
                bar=bar,
                entry=_round2(entry),
                sl=_round2(sl),
                projected_loss=_round2(loss),
                cap=_round2(cap),
                balance=_round2(account.balance),
                max_loss_pct=cfg.risk.max_loss_pct_per_trade,
                account_pct=_round2(loss / account.balance * 100.0)
                if account.balance
                else None,
            )
            return {
                "event": "order_skipped",
                "reason": "risk_exceeded",
                "projected_loss": loss,
                "cap": cap,
            }

        # 8) Buy at market (full-precision prices on the wire; the adapter
        #    rounds to the symbol's digits).
        log_fields = {
            k: _round2(v) if isinstance(v, float) else v
            for k, v in req.to_log_fields().items()
        }
        try:
            result = self._broker.place_market_buy(req)
        except BrokerRejectedError as exc:
            log_decision(
                self._logger,
                "order_rejected",
                bar=bar,
                reason=str(exc),
                **log_fields,
            )
            return {"event": "order_rejected", "error": str(exc)}

        # ``placed`` distinguishes a real fill from a dry-run no-send: the
        # DryRunBroker returns placed=False/ticket=0, and without this field the
        # log line is indistinguishable from a live placement.
        #
        # ``fill`` and ``slippage`` are the live-vs-backtest divergence made
        # explicit. The backtest books this trade at max(entry, open); the
        # market books it at whatever the ask was. Logging only one of the two
        # would hide which set of numbers the equity curve belongs to.
        fill = result.fill_price or None
        log_decision(
            self._logger,
            "order_placed",
            bar=bar,
            ticket=result.ticket,
            placed=result.placed,
            fill=_round2(fill) if fill else None,
            slippage=_round2(fill - entry) if fill else None,
            **log_fields,
        )
        return {
            "event": "order_placed",
            "ticket": result.ticket,
            "entry": entry,
            "fill": result.fill_price,
            "sl": sl,
            "tp": tp,
        }
