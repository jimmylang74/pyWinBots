"""Logging and debug utilities for pyWinBots.

Provides structured logging with both console and file output,
designed for Windows automation runtime diagnostics.
"""

import logging
import sys
from pathlib import Path
from datetime import datetime

# Re-export log level constants
DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
CRITICAL = logging.CRITICAL

_logger: logging.Logger | None = None
_default_log_dir: Path | None = None


def _get_default_log_dir() -> Path:
    """Get the default log directory (~/.pywinbots/logs/)."""
    global _default_log_dir
    if _default_log_dir is None:
        _default_log_dir = Path.home() / ".pywinbots" / "logs"
        _default_log_dir.mkdir(parents=True, exist_ok=True)
    return _default_log_dir


def setup_logger(
    name: str = "pyWinBots",
    level: int | str = logging.DEBUG,
    log_file: str | Path | None = None,
    console: bool = True,
) -> logging.Logger:
    """Configure the main pyWinBots logger.

    Args:
        name: Logger name.
        level: Log level (int or 'DEBUG', 'INFO', etc.).
        log_file: Path to log file. Auto-generated if None.
        console: Whether to also output to stdout.

    Returns:
        Configured logger instance.
    """
    global _logger

    # Resolve level
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03d [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    if console:
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(level)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    # File handler
    if log_file is None:
        log_dir = _get_default_log_dir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"pywinbots_{timestamp}.log"
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    fh = logging.FileHandler(str(log_path), encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    logger.info(f"Logger initialized. Log file: {log_path}")
    _logger = logger
    return logger


def get_logger() -> logging.Logger:
    """Return the current logger, creating a default one if none exists."""
    global _logger
    if _logger is None:
        return setup_logger()
    return _logger


class TraceLogger:
    """Context manager for tracing block execution."""

    def __init__(self, label: str, logger: logging.Logger | None = None):
        self.label = label
        self.log = logger or get_logger()

    def __enter__(self):
        self.log.debug(f">>> {self.label}")
        return self

    def __exit__(self, *args):
        self.log.debug(f"<<< {self.label}")
