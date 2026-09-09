"""Real MetaTrader5 broker adapter (EXEC-02) with a guarded lazy import.

The ``MetaTrader5`` pip package is Windows-only (RESEARCH.md), so this module
must import cleanly on macOS. ``MetaTrader5`` is therefore NEVER imported at
module top level — every method calls :func:`_load_mt5`, the single import
site, which raises :class:`BrokerUnavailableError` (with a Windows hint) when
the package is absent. That single import site is also what lets the unit
tests inject a fake ``MetaTrader5`` module into ``sys.modules`` and exercise
the adapter on any OS.

macOS has no ``MetaTrader5`` wheel at all, so the adapter also speaks to a
containerised terminal through the ``siliconmetatrader5`` RPC bridge. Which
transport is used is chosen per adapter by the ``bridge`` argument and resolved
once in :meth:`MT5Broker._mt5`.

Request/response mapping is a thin translation layer between the
:mod:`trading_bot.broker.base` dataclasses and the raw MT5 API; no strategy
knowledge lives here.
"""

from __future__ import annotations

import logging
import math
import os

import pandas as pd

from trading_bot.broker.base import (
    AccountInfo,
    BrokerClient,
    BrokerRejectedError,
    BrokerUnavailableError,
    OrderRequest,
    OrderResult,
    PendingOrder,
    Position,
    Quote,
    SymbolRisk,
)


def _load_mt5():
    """Import and return the MetaTrader5 module — the ONLY import site.

    Lazy so this file imports on macOS where the package is absent; the fake
    module injected into ``sys.modules`` by the tests is picked up the same
    way. Never ``import MetaTrader5`` at module top level.
    """
    try:
        import MetaTrader5 as mt5

        return mt5
    except ImportError as exc:
        raise BrokerUnavailableError(
            "MetaTrader5 package is not installed (Windows-only). Install on a Windows "
            "machine running the MT5 terminal, or use mode='dry-run' with SimulatedBroker."
        ) from exc


def _load_silicon_bridge(host: str, port: int):
    """Return a ``siliconmetatrader5`` bridge instance (Apple Silicon route).

    No ``MetaTrader5`` wheel exists for macOS on any architecture, so on Apple
    Silicon the terminal runs in a container and is reached over RPC. The
    bridge object exposes the same call surface as the ``MetaTrader5`` module
    (``initialize``, ``copy_rates_from_pos``, ``order_send``, ...), so it drops
    straight into the adapter wherever the module would go.
    """
    try:
        from siliconmetatrader5 import MetaTrader5 as SiliconMT5
    except ImportError as exc:
        raise BrokerUnavailableError(
            "siliconmetatrader5 is not installed. Install it with "
            "'pip install siliconmetatrader5' and start the containerised MT5 "
            "terminal, or use mode='dry-run'."
        ) from exc
    try:
        return SiliconMT5(host=host, port=port, keepalive=True)
    except Exception as exc:  # bridge construction opens the RPC socket
        raise BrokerUnavailableError(
            f"could not reach the MT5 bridge at {host}:{port} ({exc}). "
            "Is the silicon-metatrader5 container running?"
        ) from exc


def _filling_candidates(mt5, si) -> list[int]:
    """Ordered ``type_filling`` values to try for a MARKET order.

    Two distinct constant families are easy to confuse, and conflating them is
    silently wrong rather than loud: ``symbol_info().filling_mode`` is a bitmask
    of SYMBOL_FILLING_* flags (FOK=1, IOC=2), while ``type_filling`` takes an
    ORDER_FILLING_* value (FOK=0, IOC=1, RETURN=2). Feeding the former into the
    latter maps IOC onto RETURN.

    Market execution is the opposite of the pending case: ORDER_FILLING_RETURN
    is for pending orders and most brokers reject it on a DEAL, so the symbol's
    advertised modes lead (IOC first — a partial fill beats no fill on a
    breakout) and RETURN is only a last resort. The caller retries on retcode
    10030 (invalid fill). The mask is read numerically because the
    siliconmetatrader5 bridge does not expose the SYMBOL_FILLING_* constants at
    all (only ORDER_FILLING_*).
    """
    ret = getattr(mt5, "ORDER_FILLING_RETURN", 2)
    ioc = getattr(mt5, "ORDER_FILLING_IOC", 1)
    fok = getattr(mt5, "ORDER_FILLING_FOK", 0)
    mask = int(getattr(si, "filling_mode", 0) or 0)

    out = []
    if mask & 2:  # SYMBOL_FILLING_IOC
        out.append(ioc)
    if mask & 1:  # SYMBOL_FILLING_FOK
        out.append(fok)
    for v in (ioc, fok, ret):  # unadvertised fallbacks, RETURN last
        if v not in out:
            out.append(v)
    return out


def _resolve_volume(si, volume: float) -> float:
    """Snap ``volume`` to the symbol's lot grid, never UPWARDS.

    Size is risk. A broker that quotes ``volume_step=0.01`` will reject 0.013,
    and the tempting fix — round to nearest — can hand the account a larger
    position than the config asked for, silently breaking whatever risk budget
    approved the trade. So the step is floored, and a volume that cannot be
    honoured without increasing it (below ``volume_min``, above ``volume_max``)
    is refused outright rather than quietly adjusted.
    """
    vmin = float(getattr(si, "volume_min", 0.0) or 0.0)
    vmax = float(getattr(si, "volume_max", 0.0) or 0.0)
    step = float(getattr(si, "volume_step", 0.0) or 0.0)

    if vmax and volume > vmax:
        raise BrokerRejectedError(
            f"volume {volume} exceeds the symbol maximum {vmax}; lower [trading] lot"
        )
    if vmin and volume < vmin:
        raise BrokerRejectedError(
            f"volume {volume} is below the symbol minimum {vmin}. The broker cannot "
            f"trade smaller than {vmin} lots, so this position cannot be sized down "
            "any further — the account has to carry that risk or not trade."
        )
    if step:
        steps = math.floor(round((volume - vmin) / step, 9))
        snapped = round(vmin + steps * step, 8)
        if vmin and snapped < vmin:
            raise BrokerRejectedError(
                f"volume {volume} does not fit the lot grid (min {vmin}, step {step})"
            )
        return snapped
    return volume


def _check_stop_distance(ask: float, sl: float, tp: float, min_dist: float, *, sell: bool = False) -> None:
    """Refuse SL/TP the broker will bounce for sitting too close to market.

    ``trade_stops_level`` is the minimum distance (in points) a stop may sit
    from the current price; inside it the server answers 10016 "Invalid stops".
    Widening the levels to comply would silently change the trade the risk gate
    approved — a wider SL is a bigger loss than the one that was signed off —
    so this refuses instead, and the setup is skipped.

    ``sell=True`` mirrors the checks about the BID (the price a short crosses):
    the stop must sit FURTHER ABOVE the market and the target FURTHER BELOW
    it. The default ``sell=False`` keeps the two buy-side comparisons exactly
    as written.
    """
    if min_dist <= 0:
        return
    if sell:
        # Short geometry: sl is above market (resistance + buffer), tp below.
        if sl - ask < min_dist:
            raise BrokerRejectedError(
                f"stop loss {sl} is {sl - ask:.5f} from bid {ask}, inside the broker's "
                f"minimum stop distance of {min_dist:.5f}"
            )
        if ask - tp < min_dist:
            raise BrokerRejectedError(
                f"take profit {tp} is {ask - tp:.5f} from bid {ask}, inside the broker's "
                f"minimum stop distance of {min_dist:.5f}"
            )
        return
    if ask - sl < min_dist:
        raise BrokerRejectedError(
            f"stop loss {sl} is {ask - sl:.5f} from ask {ask}, inside the broker's "
            f"minimum stop distance of {min_dist:.5f}"
        )
    if tp - ask < min_dist:
        raise BrokerRejectedError(
            f"take profit {tp} is {tp - ask:.5f} from ask {ask}, inside the broker's "
            f"minimum stop distance of {min_dist:.5f}"
        )


class MT5Broker(BrokerClient):
    """Real broker adapter speaking the MetaTrader5 Python API.

    ``bridge`` selects how the terminal is reached: ``"native"`` is the
    Windows-only pip package, ``"silicon"`` is the containerised terminal over
    RPC, and ``"auto"`` prefers native and falls back to the bridge. The
    resolved transport is cached for the life of the adapter — the bridge holds
    a socket, so it must not be rebuilt per call.
    """

    _OHLC = ["open", "high", "low", "close"]

    def __init__(
        self,
        symbol: str,
        logger: logging.Logger | None = None,
        bridge: str = "native",
        bridge_host: str = "localhost",
        bridge_port: int = 8001,
        terminal_path: str = "",
        terminal_portable: bool = True,
    ):
        self._symbol = symbol
        self._logger = logger
        self._bridge = bridge
        self._bridge_host = bridge_host
        self._bridge_port = bridge_port
        self._terminal_path = terminal_path
        self._terminal_portable = terminal_portable
        self._mt5_cached = None

    def _mt5(self):
        """Resolve (once) and return the MT5 call surface for this adapter.

        Defaults to ``"native"`` so the module-level :func:`_load_mt5` stays the
        import site the fake-MT5 tests inject into — an adapter built without
        bridge settings behaves exactly as before.
        """
        if self._mt5_cached is not None:
            return self._mt5_cached
        if self._bridge == "native":
            return _load_mt5()  # per-call import: tests swap sys.modules
        if self._bridge == "silicon":
            self._mt5_cached = _load_silicon_bridge(self._bridge_host, self._bridge_port)
            return self._mt5_cached
        # "auto": prefer the native package, fall back to the bridge.
        try:
            return _load_mt5()
        except BrokerUnavailableError:
            self._mt5_cached = _load_silicon_bridge(self._bridge_host, self._bridge_port)
            return self._mt5_cached

    # -- connection ---------------------------------------------------------

    def _assert_expected_terminal(self, ti) -> None:
        """Fail when initialize() attached to a terminal other than the one asked for.

        Passing ``path=`` REQUESTS an install; it does not prove we got it. If
        that install is not running, MetaTrader5 can attach to a terminal that
        is — and the adapter would then place this config's orders, at this
        config's risk percentage, against a different account's balance. The
        run would look completely healthy while doing it.

        ``terminal_info().path`` is the install folder, so it is compared
        against the directory holding the configured ``terminal64.exe``.
        Terminals that do not report a path (the RPC bridge, the fake used in
        tests) are left alone: there is nothing to compare, and inventing a
        failure there would break the macOS route, which separates accounts by
        container rather than by path.
        """
        if not self._terminal_path:
            return
        actual = getattr(ti, "path", None)
        if not actual:
            return
        want = os.path.normcase(os.path.dirname(os.path.abspath(self._terminal_path)))
        got = os.path.normcase(os.path.abspath(str(actual)))
        if got != want:
            raise BrokerUnavailableError(
                f"attached to the WRONG terminal: asked for {want}, got {got}. "
                f"Start the terminal at {self._terminal_path} (with /portable), "
                "or correct [live] terminal_path. Refusing to trade — this "
                "config's orders would go to another account."
            )

    def connect(self) -> None:
        """Attach to the already-running MT5 terminal and verify it is usable."""
        mt5 = self._mt5()
        # The kwargs are passed ONLY when a path is configured. The
        # siliconmetatrader5 bridge's initialize() does not take path/portable,
        # and the fake-MT5 tests inject a zero-argument one — so an unconfigured
        # adapter must still call initialize() exactly as it always did.
        if self._terminal_path:
            ok = mt5.initialize(
                path=self._terminal_path, portable=self._terminal_portable
            )
        else:
            ok = mt5.initialize()
        if not ok:
            code, msg = mt5.last_error()
            where = f" (path={self._terminal_path})" if self._terminal_path else ""
            raise BrokerUnavailableError(f"MT5 initialize() failed: {code} {msg}{where}")
        ti = mt5.terminal_info()
        if not ti.connected:
            raise BrokerUnavailableError("terminal not connected")
        self._assert_expected_terminal(ti)
        if not ti.trade_allowed:
            raise BrokerUnavailableError("trade_allowed=False in terminal settings")
        # Pull the configured symbol into MarketWatch so price/order calls work.
        if not mt5.symbol_select(self._symbol, True):
            code, msg = mt5.last_error()
            raise BrokerUnavailableError(
                f"symbol_select({self._symbol}) failed: {code} {msg}"
            )

    def disconnect(self) -> None:
        """Tear down the terminal connection."""
        mt5 = self._mt5()
        mt5.shutdown()

    def reconnect(self) -> None:
        """Re-establish the connection after a disconnect (04-01).

        Unlike the default disconnect+connect, the cached transport is dropped
        FIRST: for the native package the module is re-imported per call
        anyway, but for the silicon RPC bridge the cached instance holds a dead
        socket that re-``initialize()`` would only reuse. Clearing it makes the
        next ``_mt5()`` build a fresh bridge. ``connect()`` then runs the same
        verification as a first connect (terminal reachable, trade_allowed,
        correct install path), so a reconnect never silently attaches to the
        wrong terminal.
        """
        self._mt5_cached = None
        try:
            self.disconnect()
        except Exception:  # noqa: BLE001 - a dead socket may not answer shutdown()
            pass
        self.connect()

    # -- market data --------------------------------------------------------

    def fetch_rates(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        """Return ``count`` CLOSED bars: OHLC columns, ``"time"`` datetime index.

        ``start_pos=1`` skips the currently-forming bar (RESEARCH.md
        no-lookahead rule) so the engine never acts on a bar that is still
        building. A ``None`` result from MT5 is a normal no-data poll — an
        empty frame with the right shape is returned instead of an error.
        """
        mt5 = self._mt5()
        tf_const = {"M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5}.get(timeframe)
        if tf_const is None:
            raise ValueError(f"unsupported timeframe {timeframe!r} (supported: M1, M5)")
        rates = mt5.copy_rates_from_pos(symbol, tf_const, 1, count)
        if rates is None:
            code, msg = mt5.last_error()
            # Distinguish a terminal that has GONE from one that is connected
            # but has no data yet (fresh start, symbol not loaded). A None here
            # is ambiguous between the two, so ask the terminal itself: a
            # connected terminal returning None is a normal no-data poll; a
            # disconnected one must surface as BrokerUnavailableError so the
            # engine's reconnect path (04-01) can fire. Swallowing the latter
            # as an empty frame is exactly the "alive but never reconnects"
            # failure this plan removes.
            ti = None
            try:
                ti = mt5.terminal_info()
            except Exception:  # noqa: BLE001 - a dead terminal may not answer
                pass
            if ti is None or not getattr(ti, "connected", False):
                raise BrokerUnavailableError(
                    f"terminal disconnected while fetching {symbol} "
                    f"({code} {msg}); reconnect path will re-attach"
                )
            if self._logger is not None:
                self._logger.warning(
                    "copy_rates_from_pos(%s, %s, 1, %d) returned None: %s %s",
                    symbol,
                    timeframe,
                    count,
                    code,
                    msg,
                )
            return pd.DataFrame(
                columns=self._OHLC, index=pd.DatetimeIndex([], name="time")
            )
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = df.set_index("time")
        return df[self._OHLC].astype(float)

    # -- account ------------------------------------------------------------

    def account_info(self) -> AccountInfo:
        mt5 = self._mt5()
        ai = mt5.account_info()
        if ai is None:
            code, msg = mt5.last_error()
            raise BrokerUnavailableError(f"account_info() returned None: {code} {msg}")
        return AccountInfo(
            login=ai.login,
            server=ai.server,
            currency=ai.currency,
            balance=ai.balance,
            trade_mode=ai.trade_mode,
        )

    def quote(self, symbol: str) -> Quote:
        """Live bid/ask from the terminal."""
        mt5 = self._mt5()
        tick = mt5.symbol_info_tick(symbol)
        bid = float(getattr(tick, "bid", 0.0) or 0.0) if tick is not None else 0.0
        ask = float(getattr(tick, "ask", 0.0) or 0.0) if tick is not None else 0.0
        if ask <= 0 or bid <= 0:
            code, msg = mt5.last_error()
            raise BrokerUnavailableError(
                f"no live quote for {symbol} (market closed?): {code} {msg}"
            )
        return Quote(bid=bid, ask=ask)

    def symbol_risk(self, symbol: str) -> SymbolRisk:
        """Tick economics straight from the terminal.

        ``trade_tick_value`` is already in ACCOUNT currency, which is the whole
        point of reading it rather than deriving risk from contract size: it
        absorbs both the instrument's contract size and any conversion between
        the symbol's profit currency and the account's.
        """
        mt5 = self._mt5()
        si = mt5.symbol_info(symbol)
        if si is None:
            code, msg = mt5.last_error()
            raise BrokerUnavailableError(
                f"symbol_info({symbol}) returned None: {code} {msg}"
            )
        tick_size = float(getattr(si, "trade_tick_size", 0.0) or 0.0)
        tick_value = float(getattr(si, "trade_tick_value", 0.0) or 0.0)
        # A terminal that has not finished loading a symbol reports zeros here.
        # Sizing off a zero would divide by zero or size infinitely, so refuse.
        if tick_size <= 0 or tick_value <= 0:
            raise BrokerUnavailableError(
                f"{symbol} reports tick_size={tick_size} tick_value={tick_value}; "
                "the terminal has not populated its contract specs yet"
            )
        return SymbolRisk(
            tick_size=tick_size,
            tick_value=tick_value,
            volume_min=float(getattr(si, "volume_min", 0.0) or 0.0),
            volume_step=float(getattr(si, "volume_step", 0.0) or 0.0),
            volume_max=float(getattr(si, "volume_max", 0.0) or 0.0),
        )

    # -- order lifecycle -----------------------------------------------------

    def place_market_buy(self, request: OrderRequest) -> OrderResult:
        """Buy at market with SL and TP attached, in one ``order_send``.

        This is a MARKET entry, not the Buy Stop the request vocabulary still
        describes, and that is deliberate. ``detect_setups`` fires on a close
        ABOVE resistance, so ``request.entry`` is always behind the market by
        the time we act; a Buy Stop there is rejected with 10015 every single
        time. The backtest was never really trading that level either — it
        filled at ``max(entry, open)`` on the following bar, i.e. the open, in
        339 of its 340 trades. A market buy on the poll after the signal bar is
        the faithful live translation of that, and the price we actually get
        comes back as ``OrderResult.fill_price`` so the drift stays auditable.

        Everything the server validates is checked before sending, because a
        rejection here means a missed breakout: prices rounded to the symbol's
        digits, volume snapped down onto the lot grid, and SL/TP verified
        outside ``trade_stops_level``. Filling mode falls back through the
        symbol's advertised modes on retcode 10030.
        """
        mt5 = self._mt5()
        si = mt5.symbol_info(request.symbol)
        if si is None:
            code, msg = mt5.last_error()
            raise BrokerUnavailableError(
                f"symbol_info({request.symbol}) returned None: {code} {msg}"
            )

        # The ask is the price a BUY crosses, and it must be read fresh: the
        # signal bar has already closed by the time this runs.
        tick = mt5.symbol_info_tick(request.symbol)
        ask = float(getattr(tick, "ask", 0.0) or 0.0) if tick is not None else 0.0
        if ask <= 0:
            code, msg = mt5.last_error()
            raise BrokerRejectedError(
                f"no live ask for {request.symbol} (market closed?): {code} {msg}"
            )

        digits = int(getattr(si, "digits", 2) or 2)
        point = float(getattr(si, "point", 0.0) or 0.0)
        stops_points = int(getattr(si, "trade_stops_level", 0) or 0)

        # Full-precision arithmetic upstream produces prices like 2621.4599999,
        # which a 2-digit symbol rejects as an invalid price (10015).
        price = round(ask, digits)
        sl = round(request.sl, digits)
        tp = round(request.tp, digits)

        volume = _resolve_volume(si, request.volume)
        # Last line of defence. A NaN that reached here would be sent as a
        # missing stop loss — an unprotected position — so the adapter refuses
        # rather than trusting callers to have checked.
        if not all(math.isfinite(v) for v in (price, sl, tp)):
            raise BrokerRejectedError(
                f"refusing to send non-finite prices (price={price} sl={sl} tp={tp}); "
                "a NaN stop loss would open an unprotected position"
            )
        _check_stop_distance(price, sl, tp, stops_points * point)

        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": request.symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY,
            "price": price,  # ask; deviation absorbs the move before it lands
            "sl": sl,  # support - sl_buffer
            "tp": tp,  # entry + (entry - sl), 1:1 R:R off the reference level
            "deviation": request.deviation,
            "magic": request.magic,
            "comment": request.comment,
            "type_time": mt5.ORDER_TIME_GTC,
        }
        invalid_fill = getattr(mt5, "TRADE_RETCODE_INVALID_FILL", 10030)
        candidates = _filling_candidates(mt5, si)
        result = None
        for i, filling in enumerate(candidates):
            req["type_filling"] = filling
            result = mt5.order_send(req)
            if result is None:
                code, msg = mt5.last_error()
                raise BrokerRejectedError(f"order_send returned None: {code} {msg}")
            if result.retcode != invalid_fill:
                break
            if self._logger is not None and i + 1 < len(candidates):
                self._logger.warning(
                    "type_filling=%s rejected (10030); retrying with %s",
                    filling,
                    candidates[i + 1],
                )
        if result.retcode in {mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED}:
            # ``price`` on the result is the executed price, which is not
            # necessarily the ask we asked for — that difference is the
            # slippage the engine logs against the backtest's assumed entry.
            return OrderResult(
                ticket=result.order,
                placed=True,
                retcode=result.retcode,
                comment=result.comment,
                fill_price=float(getattr(result, "price", 0.0) or 0.0),
            )
        raise BrokerRejectedError(
            f"order_send retcode {result.retcode} ({mt5.last_error()[1]}): {result.comment}"
        )

    def place_market_sell(self, request: OrderRequest) -> OrderResult:
        """Sell at market with SL and TP attached, in one ``order_send``.

        The exact mirror of :meth:`place_market_buy`: a MARKET entry (not a
        Sell Stop at ``request.entry`` — a short setup fires on a close BELOW
        support, so that level is already above the market and a stop order
        there is rejected with 10015 every time). A sell crosses the BID, so
        the bid is read fresh and the request is the buy shape byte-for-byte
        EXCEPT ``"type": mt5.ORDER_TYPE_SELL`` and the bid as ``"price"``.

        Same validation before sending — prices rounded to digits, volume
        snapped down onto the lot grid, non-finite prices refused, SL/TP
        checked outside ``trade_stops_level`` about the bid (``sell=True``) —
        and the same 10030 filling-mode fallback and DONE/PLACED handling.
        """
        mt5 = self._mt5()
        si = mt5.symbol_info(request.symbol)
        if si is None:
            code, msg = mt5.last_error()
            raise BrokerUnavailableError(
                f"symbol_info({request.symbol}) returned None: {code} {msg}"
            )

        # The bid is the price a SELL crosses, and it must be read fresh: the
        # signal bar has already closed by the time this runs.
        tick = mt5.symbol_info_tick(request.symbol)
        bid = float(getattr(tick, "bid", 0.0) or 0.0) if tick is not None else 0.0
        if bid <= 0:
            code, msg = mt5.last_error()
            raise BrokerRejectedError(
                f"no live bid for {request.symbol} (market closed?): {code} {msg}"
            )

        digits = int(getattr(si, "digits", 2) or 2)
        point = float(getattr(si, "point", 0.0) or 0.0)
        stops_points = int(getattr(si, "trade_stops_level", 0) or 0)

        # Full-precision arithmetic upstream produces prices like 2621.4599999,
        # which a 2-digit symbol rejects as an invalid price (10015).
        price = round(bid, digits)
        sl = round(request.sl, digits)
        tp = round(request.tp, digits)

        volume = _resolve_volume(si, request.volume)
        # Last line of defence. A NaN that reached here would be sent as a
        # missing stop loss — an unprotected position — so the adapter refuses
        # rather than trusting callers to have checked.
        if not all(math.isfinite(v) for v in (price, sl, tp)):
            raise BrokerRejectedError(
                f"refusing to send non-finite prices (price={price} sl={sl} tp={tp}); "
                "a NaN stop loss would open an unprotected position"
            )
        _check_stop_distance(price, sl, tp, stops_points * point, sell=True)

        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": request.symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_SELL,
            "price": price,  # bid; deviation absorbs the move before it lands
            "sl": sl,  # resistance + sl_buffer
            "tp": tp,  # entry - (sl - entry), 1:1 R:R off the reference level
            "deviation": request.deviation,
            "magic": request.magic,
            "comment": request.comment,
            "type_time": mt5.ORDER_TIME_GTC,
        }
        invalid_fill = getattr(mt5, "TRADE_RETCODE_INVALID_FILL", 10030)
        candidates = _filling_candidates(mt5, si)
        result = None
        for i, filling in enumerate(candidates):
            req["type_filling"] = filling
            result = mt5.order_send(req)
            if result is None:
                code, msg = mt5.last_error()
                raise BrokerRejectedError(f"order_send returned None: {code} {msg}")
            if result.retcode != invalid_fill:
                break
            if self._logger is not None and i + 1 < len(candidates):
                self._logger.warning(
                    "type_filling=%s rejected (10030); retrying with %s",
                    filling,
                    candidates[i + 1],
                )
        if result.retcode in {mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED}:
            # ``price`` on the result is the executed price, which is not
            # necessarily the bid we asked for — that difference is the
            # slippage the engine logs against the backtest's assumed entry.
            return OrderResult(
                ticket=result.order,
                placed=True,
                retcode=result.retcode,
                comment=result.comment,
                fill_price=float(getattr(result, "price", 0.0) or 0.0),
            )
        raise BrokerRejectedError(
            f"order_send retcode {result.retcode} ({mt5.last_error()[1]}): {result.comment}"
        )

    def pending_orders(self, symbol: str, magic: int) -> list[PendingOrder]:
        """Live pending orders for symbol+magic (re-trigger dedup)."""
        mt5 = self._mt5()
        orders = mt5.orders_get(symbol=symbol)
        if orders is None:
            return []
        return [
            PendingOrder(
                ticket=x.ticket,
                symbol=x.symbol,
                entry=x.price,
                sl=x.sl,
                tp=x.tp,
                magic=x.magic,
            )
            for x in orders
            if x.magic == magic
        ]

    def positions(self, symbol: str, magic: int) -> list[Position]:
        """Open positions for symbol+magic (one-trade-at-a-time guard)."""
        mt5 = self._mt5()
        positions = mt5.positions_get(symbol=symbol)
        if positions is None:
            return []
        return [
            Position(ticket=x.ticket, symbol=x.symbol, magic=x.magic)
            for x in positions
            if x.magic == magic
        ]
