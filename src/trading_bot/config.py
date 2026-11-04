"""Typed configuration loading from config/config.toml.

Uses stdlib ``tomllib`` (Python >= 3.11) — zero third-party dependency.
Field names mirror the TOML table keys exactly so Phase 2 can grow the
schema without touching this loader.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class DataConfig:
    source: str
    raw_dir: str
    symbol: str
    timeframe: str
    start: str
    end: str
    spec_file: str = ""     # path to the broker spec sidecar JSON (STACK seam 2); "" = legacy no-spec backtest


@dataclass(frozen=True)
class StrategyConfig:
    fractal_left: int
    fractal_right: int
    sr_lookback: int
    rr_multiple: float
    sl_buffer: float = 0.0          # legacy raw-price buffer; 0.0 = unset when sl_buffer_points is used
    sl_buffer_points: float = 0.0   # buffer in POINTS x spec.point when >0; 0 = unset (legacy sl_buffer path)
    # Which strategy the backtester runs. "breakout" (default) is the original
    # swing S/R breakout — the only one wired into the live engine. 
    # "candle_reversal" is a TEST strategy (two-candle reversal, entry at the
    # candle wick top) available to measure and compare in the backtester only.
    variant: str = "breakout"
    # Which SIDE(s) the LIVE engine trades. "long" (default) is the only value
    # every existing config uses and must stay byte-identical; "both" runs the
    # long and short swing S/R breakouts through the same single slot. A
    # "short"-only live mode is deliberately NOT supported — the backtester
    # can measure it, but the live need is "both", and the locked config is
    # the union.
    direction: str = "long"


@dataclass(frozen=True)
class TradingConfig:
    lot: float
    contract_size: int


@dataclass(frozen=True)
class BacktestConfig:
    output_dir: str


@dataclass(frozen=True)
class RiskConfig:
    """Hard ceiling on what a single trade may cost the account.

    The strategy sizes its stop from market structure, not from the account, so
    the loss on a trade is whatever the swing low happens to be — a median of
    $24.30 per 0.01 lot across the recorded backtest, with a p95 of $59.78. On
    a small account that is not a drawdown, it is the account. This cap is the
    only thing standing between a structurally-sized stop and a balance that
    cannot survive it, so it is checked before every placement and blocks
    rather than resizes (the broker's minimum lot is already the floor).
    """

    max_loss_pct_per_trade: float = 2.0

    # "fixed"   — always trade [trading] lot, and BLOCK when that risks more
    #             than the cap. Safe, but on a small account it blocks
    #             everything, because 0.01 lots is the broker's floor.
    # "percent" — size the position so the stop costs exactly the cap. This is
    #             what makes the cap a risk POLICY rather than a veto, and it
    #             is the only mode in which the account compounds: as equity
    #             grows the size grows with it, and after a loss it shrinks.
    sizing: str = "fixed"

    # Stop trading for the rest of the day once the day is down this much.
    # Measured against the balance at the first poll of each day, so it counts
    # REALISED losses only — an open position moving against you does not trip
    # it, and a stop-out does. 0 disables.
    max_daily_loss_pct: float = 0.0

    # Lot grid used when sizing. These must match the broker's symbol limits;
    # the MT5 adapter re-checks against the real ones and refuses rather than
    # rounding up, so a wrong value here costs a skipped trade, never an
    # oversized position.
    lot_min: float = 0.01
    lot_step: float = 0.01

    # Ceiling on NOTIONAL exposure, as a multiple of balance. Distinct from
    # max_loss_pct_per_trade, which bounds the STOP: a tight stop lets percent
    # sizing buy an enormous position for the same 2% risk (a $5.86 stop on a
    # $5,000 account sizes to 17 lots of gold — $7.7M notional). The stop is
    # what fails in exactly the case that matters: a weekend gap or a flash
    # move jumps straight past it, and the loss is set by POSITION SIZE, not by
    # where the stop was. 0 disables. EU retail caps gold at 1:20.
    max_leverage: float = 20.0
    max_concurrent: int = 1

    # Refuse a setup whose reward:risk has already decayed below this by the
    # time we can act. The strategy's levels imply exactly 1:1, but a market
    # buy fills at the ask, which is above the reference entry — so the stop is
    # further away and the target closer before the trade even starts. A live
    # M1 trade on 2026-08-20 was booked at 1.00R by the backtest and opened at
    # 0.72R. Past some point the trade on offer is simply not the trade that
    # was tested, and taking it is chasing. 0 disables.
    min_rr: float = 0.5


@dataclass(frozen=True)
class LiveConfig:
    """Live-execution settings (EXEC-03).

    ``enabled`` is the explicit opt-in that permits REAL-account execution
    (SAFE-03); mode narrows it further to dry-run/demo/live. Everything else
    is order-placement plumbing used by the MT5 adapter.
    """

    enabled: bool = False
    mode: str = "dry-run"  # "dry-run" | "demo" | "live"
    magic_number: int = 77001
    deviation: int = 20  # max slippage in points for order_send
    poll_interval: float = 5.0  # seconds between live bar checks
    comment: str = "gold-breakout-bot"
    # How MT5Broker reaches a terminal. "native" is the Windows-only
    # MetaTrader5 pip package; "silicon" is the siliconmetatrader5 RPC bridge
    # to a containerised terminal (the only route on Apple Silicon, where no
    # MetaTrader5 wheel exists); "auto" prefers native and falls back.
    # Broker's name for the traded instrument, when it differs from the
    # data vendor's. [data] symbol names the histdata CSVs (XAUUSD); brokers
    # rename the same instrument per account type (Exness quotes gold as
    # XAUUSDm on Standard). Empty = use [data] symbol unchanged.
    symbol: str = ""
    bridge: str = "auto"  # "auto" | "native" | "silicon"
    bridge_host: str = "localhost"
    bridge_port: int = 8001
    # Which terminal INSTALL to attach to, for running several accounts on one
    # machine. Empty = let MetaTrader5 pick, which is correct only when exactly
    # one terminal is running.
    #
    # On macOS the accounts are separated by CONTAINER, and each container's
    # bridge_port names exactly one terminal holding exactly one account. There
    # is no such separator on Windows: three portable installs on one box are
    # three terminals visible to the same pip package, and an argument-less
    # initialize() attaches to whichever it finds first. That is the "bridge may
    # attach to the wrong one" failure this codebase has already eliminated
    # three times — silent, and it trades the wrong account's balance.
    #
    # So on Windows this is REQUIRED once a second terminal exists. Point it at
    # the terminal64.exe of that account's own install, e.g.
    #   terminal_path = 'C:\\MT5-Gold\\terminal64.exe'
    # and run that install with /portable so its Config/accounts.dat stays its
    # own. Leaving this empty with three installs running is not a config style
    # choice; it is an account-selection bug waiting for a restart to expose it.
    terminal_path: str = ""
    # Passed to initialize() alongside terminal_path. Portable mode keeps each
    # install's settings and saved account inside its own folder instead of the
    # shared %APPDATA% tree — which is what stops three terminals sharing one
    # accounts.dat and logging each other out.
    terminal_portable: bool = True
    # Dry-run only: how many bars of history to rewind before replaying, so a
    # dry-run poll loop walks real bars instead of idling on a static frame.
    replay_bars: int = 500

    # How many bars of history to fetch each poll. 0 = the strategy minimum
    # (sr_lookback + fractal windows + margin), which is what every existing
    # config gets — byte-identical legacy behavior. >0 widens the window the
    # AI layer reasons over: the regime check resamples to DAILY bars, and 69
    # M5 bars (~6h) is too thin to judge a market regime honestly. The
    # strategy chain is unaffected — S/R expiry is window-bounded, so extra
    # history never changes detection, only the context handed to the model.
    fetch_bars: int = 0

    # Only act on setups whose bar falls inside [start, end) hours. Empty
    # disables. Hours are read off the BAR INDEX's own clock, which for the MT5
    # feed is the broker's server time (UTC on Exness) — NOT the host's local
    # time, and not SAST. Wrapping past midnight is allowed: [21, 8] means the
    # off-hours window.
    #
    # This suppresses ACTING only. Swings and levels are still built from every
    # bar, exactly as backtest/engine.py does it — filtering the data instead
    # would tear holes in the lookback window and a level confirmed at 07:55
    # would vanish for the 08:00 bar that should trade it.
    session_hours: list[int] = field(default_factory=list)

    # Weekend guard (04-01): refuse NEW entries once the week is closing, so a
    # fresh position is never opened into a market about to shut. Gold is shut
    # Friday 21:00 -> Sunday 21:00 UTC and a broker-side stop cannot protect a
    # Sunday opening gap that jumps straight through it; the bot's scheduled
    # Friday stop is the first line of defence, and this guard is the
    # self-imposed one that still holds if the task is late or missed.
    #
    # `weekend_stop_hour` is the UTC hour (bar-clock, like session_hours) of
    # FRIDAY after which new entries are refused. 0 disables. Give it margin
    # before the actual 21:00 UTC shut — the existing scheduled stop fires at
    # 19:00 UTC, so 19 is the documented value. `weekend_resume_hour` is the
    # UTC hour of SUNDAY at which entries resume (default 21 = the gold market
    # reopen; BTC's 24/7 market ignores this by leaving the guard off).
    weekend_stop_hour: int = 0
    weekend_resume_hour: int = 21

    # Reconnect (04-01): after `reconnect_after` consecutive failed polls
    # (`bar_fetch_failed`), tear down and re-establish the broker connection.
    # 0 disables reconnection (bot stays up, keeps polling, never reconnects).
    # Between failed reconnect attempts sleep `reconnect_backoff` seconds so a
    # long terminal outage does not hammer it. Empty frames (market closed) are
    # NOT failures — a closure must never trigger reconnect churn.
    reconnect_after: int = 3
    reconnect_backoff: float = 30.0


# Defaults for the [live] table — applied when a config omits the table
# entirely so phase-1-era configs keep loading (backward compatibility).
DEFAULT_LIVE = {
    "enabled": False,
    "mode": "dry-run",
    "magic_number": 77001,
    "deviation": 20,
    "poll_interval": 5.0,
    "comment": "gold-breakout-bot",
    "symbol": "",
    "bridge": "auto",
    "bridge_host": "localhost",
    "bridge_port": 8001,
    "terminal_path": "",
    "terminal_portable": True,
    "replay_bars": 500,
    "fetch_bars": 0,
    "session_hours": [],
    "weekend_stop_hour": 0,
    "weekend_resume_hour": 21,
    "reconnect_after": 3,
    "reconnect_backoff": 30.0,
}


# Defaults for the [risk] table — applied when a config omits it entirely.
DEFAULT_RISK = {
    "max_loss_pct_per_trade": 2.0,
    "sizing": "fixed",
    "max_daily_loss_pct": 0.0,
    "lot_min": 0.01,
    "lot_step": 0.01,
    "max_leverage": 20.0,
    "max_concurrent": 1,
    "min_rr": 0.5,
}


@dataclass(frozen=True)
class AIConfig:
    """The non-deterministic half of the hybrid system (Phase 4, plan 03-01).

    The model REASONS; the deterministic risk/execution stack DISPOSES. DeepSeek
    is consulted for trade-idea reasoning on every deterministic setup and once
    per day for a market-regime read; each proposal must pass a pure gate
    (``ai/gate.py``) before the existing execution path can act on it.

    ``enabled`` is the opt-in for the AI layer inside the live engine. ``mock``
    is the offline default — zero API keys, zero network — so every AI feature
    is testable and demoable before a single paid call. The API key is read from
    the environment named by ``api_key_env`` (never from config): the repo's
    history includes an infostealer, so secrets live outside TOML by policy.
    """

    enabled: bool = False
    provider: str = "mock"  # "mock" | "deepseek"
    model: str = "deepseek-chat"
    api_base: str = "https://api.deepseek.com"
    api_key_env: str = "DEEPSEEK_API_KEY"
    temperature: float = 0.2
    max_tokens: int = 500
    timeout: float = 30.0
    # A proposal below this confidence is BLOCKED by the gate. 0..100.
    min_confidence: int = 70
    # When True, a proposal whose bias does not match the deterministic setup's
    # direction (LONG setup vs bias=SHORT) is BLOCKED by the gate.
    require_agreement: bool = True
    # Ask for the daily regime assessment (cadence: once per UTC day).
    regime_check_daily: bool = True
    # When the daily regime says CHOPPY (and tradeable=false), suppress setups.
    block_when_choppy: bool = True
    # Write every prompt+response to output/ai_calls_<log>.jsonl for offline
    # audit of model output quality (SAFE-02 for the AI half).
    record_calls: bool = True
    # Directory holding the prompt templates (trade_idea.txt, regime_check.txt).
    prompt_dir: str = "prompts"


DEFAULT_AI = {
    "enabled": False,
    "provider": "mock",
    "model": "deepseek-chat",
    "api_base": "https://api.deepseek.com",
    "api_key_env": "DEEPSEEK_API_KEY",
    "temperature": 0.2,
    "max_tokens": 500,
    "timeout": 30.0,
    "min_confidence": 70,
    "require_agreement": True,
    "regime_check_daily": True,
    "block_when_choppy": True,
    "record_calls": True,
    "prompt_dir": "prompts",
}


@dataclass(frozen=True)
class NewsConfig:
    """Free, keyless news/sentiment pipeline (plan 03-04, NEWS-01/NEWS-02).

    ``enabled`` is the opt-in: fetching is NEVER automatic. The pipeline is
    RSS-based and deterministic (lexicon scoring, not a second model call), so
    it costs nothing and needs no API key. Network failures degrade to "no news
    today" — the AI regime check consumes an optional daily snapshot and fails
    OPEN when it is absent (03-04 task 3).
    """

    enabled: bool = False
    feeds: list[str] = field(
        default_factory=lambda: [
            "https://www.kitco.com/rss/news",
            "https://www.goldprice.com/rss/gold-news/",
            "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        ]
    )
    max_items: int = 50
    user_agent: str = "trading-bot/0.1 (+personal research)"
    db_path: str = "data/analytics/trading.duckdb"
    snapshot_file: str = "output/news_sentiment.json"
    fetch_timeout: float = 15.0


DEFAULT_NEWS = {
    "enabled": False,
    "feeds": [
        "https://www.kitco.com/rss/news",
        "https://www.goldprice.com/rss/gold-news/",
        "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    ],
    "max_items": 50,
    "user_agent": "trading-bot/0.1 (+personal research)",
    "db_path": "data/analytics/trading.duckdb",
    "snapshot_file": "output/news_sentiment.json",
    "fetch_timeout": 15.0,
}


@dataclass(frozen=True)
class SentimentConfig:
    """Direction signal for the live engine (DXY macro regime for gold).

    ``enabled`` is the opt-in: when False the live engine never reads the
    signal and trades exactly as before (byte-identical). When True, each poll
    resolves the current DXY macro regime to a trade direction — a weak dollar
    (bullish gold) -> long only, a strong dollar (bearish gold) -> short only,
    and a neutral band (or an unavailable signal) -> the configured
    ``[strategy] direction``. This is the live half of the backtest
    ``sentiment`` seam; it was measured first (STATE quick task 260928-dxy) and
    is deliberately conservative — the fallback is the operator's configured
    direction, never a forced short.

    Distinct from ``[news]`` (the RSS lexicon scorer feeding the AI regime
    prompt): this is a single deterministic macro number that DIRECTLY selects
    the trade side, no model involved.
    """

    enabled: bool = False
    source: str = "dxy"               # only "dxy" today
    band: float = 10.0                # neutral band around 50 (0-100 bullishness)
    window: int = 200                 # DXY trailing-MA window, days
    cache_path: str = "data/processed/dxy.json"
    refresh_seconds: float = 3600.0   # recompute cadence; the fetch itself is daily


DEFAULT_SENTIMENT = {
    "enabled": False,
    "source": "dxy",
    "band": 10.0,
    "window": 200,
    "cache_path": "data/processed/dxy.json",
    "refresh_seconds": 3600.0,
}


@dataclass(frozen=True)
class Config:
    data: DataConfig
    strategy: StrategyConfig
    trading: TradingConfig
    backtest: BacktestConfig
    live: LiveConfig
    # Defaulted so configs written before the [risk] table keep loading; the
    # default is a cap, not a permission, and applies whether or not the table
    # is present.
    risk: RiskConfig = RiskConfig()
    # Defaulted so configs written before the [ai] table keep loading; the AI
    # layer is inert (disabled, mock provider) unless explicitly configured.
    ai: AIConfig = AIConfig()
    # Defaulted so configs written before the [news] table keep loading; the
    # news pipeline is off (never automatic) unless explicitly enabled.
    news: NewsConfig = NewsConfig()
    # Defaulted so configs written before the [sentiment] table keep loading;
    # the live direction signal is off (never automatic) unless enabled.
    sentiment: SentimentConfig = SentimentConfig()


def live_symbol(cfg: Config) -> str:
    """The symbol the BROKER knows, for every live/demo call.

    Dry-run is deliberately excluded: it replays the histdata CSVs, which are
    keyed by the VENDOR's name, so the broker override must not apply there.
    Otherwise falls back to ``[data] symbol`` so configs that never set the
    override behave exactly as before.
    """
    if cfg.live.mode == "dry-run":
        return cfg.data.symbol
    return cfg.live.symbol or cfg.data.symbol


def _validate(cfg: Config) -> None:
    """Raise ValueError with a clear message naming the bad key."""
    if cfg.data.timeframe not in {"M1", "M5"}:
        raise ValueError(
            f"data.timeframe={cfg.data.timeframe!r} is invalid: must be 'M1' or 'M5'"
        )
    if cfg.strategy.fractal_left < 1:
        raise ValueError(
            f"strategy.fractal_left={cfg.strategy.fractal_left} is invalid: must be >= 1"
        )
    if cfg.strategy.fractal_right < 1:
        raise ValueError(
            f"strategy.fractal_right={cfg.strategy.fractal_right} is invalid: must be >= 1"
        )
    if cfg.strategy.sr_lookback < cfg.strategy.fractal_left + cfg.strategy.fractal_right + 1:
        raise ValueError(
            "strategy.sr_lookback must be >= fractal_left + fractal_right + 1 "
            f"(got {cfg.strategy.sr_lookback} vs "
            f"{cfg.strategy.fractal_left + cfg.strategy.fractal_right + 1})"
        )
    # Exactly ONE buffer source (PITFALLS D2): the buffer is expressed either
    # as a raw price (sl_buffer, legacy) or in points x spec.point
    # (sl_buffer_points, spec-driven) — never both, and never neither. This
    # REPLACES the legacy `sl_buffer must be > 0` rule, which the both-zero
    # check below subsumes for legacy configs (they always set sl_buffer > 0).
    if cfg.strategy.sl_buffer < 0 or cfg.strategy.sl_buffer_points < 0:
        raise ValueError(
            "strategy.sl_buffer and strategy.sl_buffer_points must be >= 0 (0 = unset)")
    if cfg.strategy.sl_buffer > 0 and cfg.strategy.sl_buffer_points > 0:
        raise ValueError(
            "strategy.sl_buffer and strategy.sl_buffer_points are both set: express the buffer "
            "in ONE unit — sl_buffer (raw price, legacy) or sl_buffer_points (points, spec-driven), not both")
    if cfg.strategy.sl_buffer == 0.0 and cfg.strategy.sl_buffer_points == 0.0:
        raise ValueError(
            "strategy.sl_buffer and strategy.sl_buffer_points are both 0: set exactly one "
            "(sl_buffer = raw-price buffer, legacy; sl_buffer_points = buffer in points)")
    if cfg.strategy.rr_multiple <= 0:
        raise ValueError(
            f"strategy.rr_multiple={cfg.strategy.rr_multiple} is invalid: must be > 0"
        )
    if cfg.strategy.variant not in ("breakout", "candle_reversal"):
        raise ValueError(
            f"strategy.variant={cfg.strategy.variant!r} is invalid: must be "
            "'breakout' or 'candle_reversal'"
        )
    if cfg.strategy.direction not in ("long", "both"):
        raise ValueError(
            f"strategy.direction={cfg.strategy.direction!r} is invalid: must be "
            "'long' (default) or 'both' ('short'-only live is unsupported; "
            "'both' trades both sides through the single slot)"
        )
    if not isinstance(cfg.data.spec_file, str):
        raise ValueError("data.spec_file must be a string path or empty")
    if cfg.trading.lot <= 0:
        raise ValueError(f"trading.lot={cfg.trading.lot} is invalid: must be > 0")
    if cfg.trading.contract_size <= 0:
        raise ValueError(
            f"trading.contract_size={cfg.trading.contract_size} is invalid: must be > 0"
        )
    if cfg.live.mode not in {"dry-run", "demo", "live"}:
        raise ValueError(
            f"live.mode={cfg.live.mode!r} is invalid: must be one of 'dry-run', 'demo', 'live'"
        )
    if not isinstance(cfg.live.magic_number, int) or cfg.live.magic_number < 0:
        raise ValueError(
            f"live.magic_number={cfg.live.magic_number} is invalid: must be an int >= 0"
        )
    if not isinstance(cfg.live.deviation, int) or cfg.live.deviation < 0:
        raise ValueError(
            f"live.deviation={cfg.live.deviation} is invalid: must be an int >= 0"
        )
    if cfg.live.poll_interval <= 0:
        raise ValueError(
            f"live.poll_interval={cfg.live.poll_interval} is invalid: must be > 0"
        )
    if cfg.live.bridge not in {"auto", "native", "silicon"}:
        raise ValueError(
            f"live.bridge={cfg.live.bridge!r} is invalid: must be one of "
            "'auto', 'native', 'silicon'"
        )
    if not isinstance(cfg.live.bridge_port, int) or not 1 <= cfg.live.bridge_port <= 65535:
        raise ValueError(
            f"live.bridge_port={cfg.live.bridge_port} is invalid: must be an int in 1..65535"
        )
    sh = cfg.live.session_hours
    if sh:
        if len(sh) != 2 or not all(isinstance(h, int) and 0 <= h <= 24 for h in sh):
            raise ValueError(
                f"live.session_hours={sh} is invalid: must be [] or two ints "
                "in 0..24, e.g. [8, 21]"
            )
        if sh[0] == sh[1]:
            raise ValueError(
                f"live.session_hours={sh} is invalid: start == end selects "
                "nothing; use [] to disable"
            )
    if not isinstance(cfg.live.replay_bars, int) or cfg.live.replay_bars < 1:
        raise ValueError(
            f"live.replay_bars={cfg.live.replay_bars} is invalid: must be an int >= 1"
        )
    if not isinstance(cfg.live.fetch_bars, int) or cfg.live.fetch_bars < 0:
        raise ValueError(
            f"live.fetch_bars={cfg.live.fetch_bars} is invalid: must be an int >= 0 "
            "(0 = strategy-minimum window, legacy behavior)"
        )
    if not isinstance(cfg.live.weekend_stop_hour, int) or not 0 <= cfg.live.weekend_stop_hour <= 24:
        raise ValueError(
            f"live.weekend_stop_hour={cfg.live.weekend_stop_hour} is invalid: "
            "must be an int in 0..24 (0 disables the weekend guard)"
        )
    if not isinstance(cfg.live.weekend_resume_hour, int) or not 0 <= cfg.live.weekend_resume_hour <= 24:
        raise ValueError(
            f"live.weekend_resume_hour={cfg.live.weekend_resume_hour} is invalid: "
            "must be an int in 0..24"
        )
    if not isinstance(cfg.live.reconnect_after, int) or cfg.live.reconnect_after < 0:
        raise ValueError(
            f"live.reconnect_after={cfg.live.reconnect_after} is invalid: "
            "must be an int >= 0 (0 disables reconnection)"
        )
    if cfg.live.reconnect_backoff < 0:
        raise ValueError(
            f"live.reconnect_backoff={cfg.live.reconnect_backoff} is invalid: "
            "must be >= 0"
        )
    # 100% is allowed but means "one loss may take the whole account"; above
    # that the cap could never bind and the gate would be decorative.
    if not 0 < cfg.risk.max_loss_pct_per_trade <= 100:
        raise ValueError(
            f"risk.max_loss_pct_per_trade={cfg.risk.max_loss_pct_per_trade} is "
            "invalid: must be > 0 and <= 100"
        )
    if cfg.risk.sizing not in {"fixed", "percent"}:
        raise ValueError(
            f"risk.sizing={cfg.risk.sizing!r} is invalid: must be 'fixed' or 'percent'"
        )
    if not 0 <= cfg.risk.max_daily_loss_pct <= 100:
        raise ValueError(
            f"risk.max_daily_loss_pct={cfg.risk.max_daily_loss_pct} is invalid: "
            "must be >= 0 (0 disables) and <= 100"
        )
    if cfg.risk.min_rr < 0:
        raise ValueError(
            f"risk.min_rr={cfg.risk.min_rr} is invalid: must be >= 0 (0 disables)"
        )
    if cfg.risk.max_concurrent < 1:
        raise ValueError(
            f"risk.max_concurrent={cfg.risk.max_concurrent} is invalid: must be >= 1. "
            "It must also match what the backtest was measured at, or every "
            "statistic that backtest produced understates the live exposure."
        )
    if cfg.risk.max_leverage < 0:
        raise ValueError(
            f"risk.max_leverage={cfg.risk.max_leverage} is invalid: must be >= 0 "
            "(0 disables)"
        )
    if cfg.risk.lot_min <= 0 or cfg.risk.lot_step <= 0:
        raise ValueError(
            f"risk.lot_min={cfg.risk.lot_min} / lot_step={cfg.risk.lot_step} are "
            "invalid: both must be > 0"
        )
    if cfg.ai.provider not in {"mock", "deepseek"}:
        raise ValueError(
            f"ai.provider={cfg.ai.provider!r} is invalid: must be 'mock' or 'deepseek'"
        )
    if not 0 <= cfg.ai.temperature <= 1:
        raise ValueError(
            f"ai.temperature={cfg.ai.temperature} is invalid: must be in 0..1"
        )
    if cfg.ai.max_tokens < 1:
        raise ValueError(
            f"ai.max_tokens={cfg.ai.max_tokens} is invalid: must be >= 1"
        )
    if cfg.ai.timeout <= 0:
        raise ValueError(
            f"ai.timeout={cfg.ai.timeout} is invalid: must be > 0"
        )
    if not 0 <= cfg.ai.min_confidence <= 100:
        raise ValueError(
            f"ai.min_confidence={cfg.ai.min_confidence} is invalid: must be in 0..100"
        )
    if not cfg.ai.api_key_env:
        raise ValueError("ai.api_key_env must not be empty")
    if not cfg.ai.prompt_dir:
        raise ValueError("ai.prompt_dir must not be empty")
    if not isinstance(cfg.news.feeds, list) or not cfg.news.feeds:
        raise ValueError("news.feeds must be a non-empty list of RSS URLs")
    for feed in cfg.news.feeds:
        if not (str(feed).startswith("http://") or str(feed).startswith("https://")):
            raise ValueError(
                f"news.feeds contains a non-http(s) URL: {feed!r}"
            )
    if not isinstance(cfg.news.max_items, int) or cfg.news.max_items < 1:
        raise ValueError(
            f"news.max_items={cfg.news.max_items} is invalid: must be an int >= 1"
        )
    if not cfg.news.user_agent:
        raise ValueError("news.user_agent must not be empty")
    if not isinstance(cfg.news.db_path, str) or not cfg.news.db_path:
        raise ValueError("news.db_path must be a non-empty path")
    if not isinstance(cfg.news.snapshot_file, str) or not cfg.news.snapshot_file:
        raise ValueError("news.snapshot_file must be a non-empty path")
    if cfg.news.fetch_timeout <= 0:
        raise ValueError(
            f"news.fetch_timeout={cfg.news.fetch_timeout} is invalid: must be > 0"
        )
    if cfg.sentiment.source not in ("dxy",):
        raise ValueError(
            f"sentiment.source={cfg.sentiment.source!r} is invalid: must be 'dxy'"
        )
    if cfg.sentiment.band < 0:
        raise ValueError(
            f"sentiment.band={cfg.sentiment.band} is invalid: must be >= 0"
        )
    if cfg.sentiment.window < 1:
        raise ValueError(
            f"sentiment.window={cfg.sentiment.window} is invalid: must be >= 1"
        )
    if not cfg.sentiment.cache_path:
        raise ValueError("sentiment.cache_path must be a non-empty path")
    if cfg.sentiment.refresh_seconds <= 0:
        raise ValueError(
            f"sentiment.refresh_seconds={cfg.sentiment.refresh_seconds} is invalid: "
            "must be > 0"
        )


def load_config(path: str | Path = "config/config.toml") -> Config:
    """Load and validate the TOML config file.

    Raises:
        FileNotFoundError: if the file does not exist at the resolved path.
        ValueError: if a config value fails validation (message names the bad key).
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path.resolve()}")

    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    trading_raw = dict(raw.get("trading", {}))
    trading_raw.pop("spread_assumption", None)   # retired knob (INST-03) — tolerate, never model
    trading = TradingConfig(**trading_raw)

    cfg = Config(
        data=DataConfig(**raw["data"]),
        strategy=StrategyConfig(**raw["strategy"]),
        trading=trading,
        backtest=BacktestConfig(**raw["backtest"]),
        live=LiveConfig(**{**DEFAULT_LIVE, **raw.get("live", {})}),
        risk=RiskConfig(**{**DEFAULT_RISK, **raw.get("risk", {})}),
        ai=AIConfig(**{**DEFAULT_AI, **raw.get("ai", {})}),
        news=NewsConfig(**{**DEFAULT_NEWS, **raw.get("news", {})}),
        sentiment=SentimentConfig(**{**DEFAULT_SENTIMENT, **raw.get("sentiment", {})}),
    )
    _validate(cfg)
    return cfg
