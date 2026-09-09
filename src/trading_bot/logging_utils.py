"""Structured file logging for backtest decisions (SAFE-02).

Every backtest decision is written to a file as a single structured
``key=value`` line so the full decision trace is recoverable after a run.

Uses ONLY stdlib ``logging`` + ``os``/``pathlib``.
"""

from __future__ import annotations

import logging
from pathlib import Path

# Module-level guard: configure each named logger only once.
_LOGGERS: dict[str, logging.Logger] = {}


def get_logger(name: str, log_path: str = "output/backtest.log") -> logging.Logger:
    """Return a file logger that writes structured lines to ``log_path``.

    Configures the logger ONCE per (name, log_path) pair. The root logger is
    never touched. The log directory is created if missing.
    """
    key = (name, str(log_path))
    if key in _LOGGERS:
        return _LOGGERS[key]

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False  # do not leak to the root logger

    # Remove any pre-existing handlers so re-configuration is idempotent.
    logger.handlers.clear()

    log_file = Path(log_path)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter("%(asctime)s level=%(levelname)s %(message)s")
    )
    logger.addHandler(handler)

    _LOGGERS[key] = logger
    return logger


def _format_value(value: object) -> str:
    text = str(value)
    # Quote values containing whitespace so key=value parsing stays unambiguous.
    if any(ch.isspace() for ch in text):
        return f'"{text}"'
    return text


def log_decision(logger: logging.Logger, event: str, **fields: object) -> None:
    """Emit a structured decision line: ``event=<name> key=value ...``.

    Example:
        log_decision(logger, "setup_detected",
                     bar="2024-01-01 00:30", entry=101.0, sl=100.09, tp=101.91)
        # -> level=INFO event=setup_detected bar="2024-01-01 00:30" entry=101.0 ...
    """
    parts = [f"event={event}"]
    parts.extend(f"{k}={_format_value(v)}" for k, v in fields.items())
    logger.info(" ".join(parts))
