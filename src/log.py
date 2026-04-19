from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from typing import Callable

LEVELS = {
    "debug":   logging.DEBUG,
    "info":    logging.INFO,
    "warn":    logging.WARNING,
    "warning": logging.WARNING,
    "error":   logging.ERROR,
    "success": logging.INFO,
}

_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"

_COL = {
    "debug":   "\033[96m",   # bright cyan
    "info":    "\033[97m",   # bright white
    "warning": "\033[93m",   # bright yellow
    "error":   "\033[91m",   # bright red
    "success": "\033[92m",   # bright green
}
_BADGE = {
    "debug":   " DBG ",
    "info":    " INF ",
    "warning": " WRN ",
    "error":   " ERR ",
    "success": " ✓OK ",
}

PACKAGE_ROOT = "spcrawler"

_external_hooks: list[Callable[[dict], None]] = []


def add_hook(fn: Callable[[dict], None]) -> None:
    _external_hooks.append(fn)


def remove_hook(fn: Callable[[dict], None]) -> None:
    _external_hooks.remove(fn)


class _PrettyFormatter(logging.Formatter):
    _MODULE_WIDTH = 10

    def format(self, record: logging.LogRecord) -> str:
        is_success = getattr(record, "success", False)

        if is_success:
            level_key = "success"
        else:
            level_key = record.levelname.lower()
            if level_key not in _COL:
                level_key = "info"

        col   = _COL[level_key]
        badge = _BADGE[level_key]

        ts     = datetime.now(timezone.utc).strftime("%H:%M:%S")
        module = record.name.replace(f"{PACKAGE_ROOT}.", "").replace(PACKAGE_ROOT, "root")
        module = module[:self._MODULE_WIDTH].ljust(self._MODULE_WIDTH)

        msg = record.getMessage()

        return (
            f"{_DIM}{ts}{_RESET}  "
            f"{_DIM}[{module}]{_RESET}  "
            f"{_BOLD}{col}{badge}{_RESET}  "
            f"{col}┤ {msg}{_RESET}"
        )


class _HookHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if not _external_hooks:
            return
        payload = {
            "ts":      datetime.now(timezone.utc).isoformat(),
            "module":  record.name,
            "level":   "success" if getattr(record, "success", False) else record.levelname.lower(),
            "message": record.getMessage(),
        }
        for fn in _external_hooks:
            try:
                fn(payload)
            except Exception:
                pass


def _build_stream_handler() -> logging.Handler:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(_PrettyFormatter())
    return h


_stream_handler = _build_stream_handler()
_hook_handler   = _HookHandler()


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.addHandler(_stream_handler)
        logger.addHandler(_hook_handler)
        logger.propagate = False
    return logger


def setup(level: str = "info") -> None:
    numeric = LEVELS.get(level.lower(), logging.INFO)
    root = logging.getLogger(PACKAGE_ROOT)
    root.setLevel(numeric)
    _stream_handler.setLevel(numeric)
    _hook_handler.setLevel(numeric)


def success(logger: logging.Logger, message: str, *args) -> None:
    if args:
        message = message % args
    record = logger.makeRecord(
        logger.name, logging.INFO, "(unknown)", 0, message, (), None,
    )
    record.success = True 
    logger.handle(record)